import json
import os
import time
import boto3
import requests

# Initialize AWS clients
s3_client = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')

# Environment variables
VIDEOS_BUCKET = os.environ['VIDEOS_BUCKET']
VIDEOS_TABLE = os.environ['VIDEOS_TABLE']
EVOLINK_API_KEY = os.environ.get('EVOLINK_API_KEY', '')
FAL_API_KEY = os.environ.get('FAL_API_KEY', '')

# DynamoDB table
videos_table = dynamodb.Table(VIDEOS_TABLE)

EVOLINK_TASKS_URL = "https://api.evolink.ai/v1/tasks/"
FAL_QUEUE_BASE = "https://queue.fal.run"


def lambda_handler(event, context):
    """Poll EvoLink job status and update DynamoDB when complete"""

    print(f"Poller event: {json.dumps(event)}")

    video_id = event['videoId']
    task_id = event['jobName']
    provider = event.get('provider', 'evolink')
    model = event.get('model', '')
    fal_model_id = event.get('falModelId')
    fal_status_url = event.get('falStatusUrl')
    fal_result_url = event.get('falResultUrl')

    # 10 minute ceiling (120 x 5 s); covers Kling at max 15 s video + queue time
    max_polls = 120
    poll_count = 0

    try:
        while poll_count < max_polls:
            if provider == 'fal':
                status = _check_fal_status(fal_model_id, task_id, fal_status_url, fal_result_url)
            else:
                status = check_evolink_job_status(task_id)
            job_status = status.get('status')
            print(f"Poll {poll_count + 1}: task {task_id} status={job_status}")

            if job_status == 'completed':
                results = status.get('results') or []
                video_url = results[0] if results else None

                if video_url:
                    video_data = download_video(video_url)
                    s3_url = upload_video_to_s3(video_id, video_data)
                    cleanup_temp_images(video_id, model)

                    timestamp = int(time.time() * 1000)
                    videos_table.update_item(
                        Key={'id': video_id},
                        UpdateExpression='SET #status = :status, videoUrl = :url, updatedAt = :updated REMOVE #error',
                        ExpressionAttributeNames={'#status': 'status', '#error': 'error'},
                        ExpressionAttributeValues={
                            ':status': 'completed',
                            ':url': s3_url,
                            ':updated': timestamp
                        }
                    )
                    print(f"Video completed and uploaded: {s3_url}")
                    return {'statusCode': 200, 'videoId': video_id, 'status': 'completed'}

                # Completed signal but no video URL — treat as failure
                error_msg = status.get('error') or 'No video URL in completed response'
                print(f"Job completed with no video URL: {error_msg}")
                _mark_failed(video_id, error_msg)
                cleanup_temp_images(video_id, model)
                return {'statusCode': 500, 'videoId': video_id, 'status': 'failed', 'error': error_msg}

            if job_status == 'failed':
                error_msg = status.get('error') or 'Video generation failed'
                print(f"Job failed: {error_msg}")
                _mark_failed(video_id, error_msg)
                cleanup_temp_images(video_id, model)
                return {'statusCode': 500, 'videoId': video_id, 'status': 'failed', 'error': error_msg}

            # pending / processing — wait and retry
            poll_count += 1
            if poll_count < max_polls:
                time.sleep(5)

        # Timed out
        print(f"Job timed out for video: {video_id}")
        _mark_failed(video_id, 'Video generation timed out')
        cleanup_temp_images(video_id, model)
        return {'statusCode': 408, 'videoId': video_id, 'status': 'timeout'}

    except Exception as e:
        print(f"Error in poller: {str(e)}")
        _mark_failed(video_id, str(e))
        cleanup_temp_images(video_id, model)
        return {'statusCode': 500, 'error': str(e)}


def check_evolink_job_status(task_id):
    """GET task status from EvoLink"""
    headers = {'Authorization': f'Bearer {EVOLINK_API_KEY}'}
    response = requests.get(EVOLINK_TASKS_URL + task_id, headers=headers)
    response.raise_for_status()
    return response.json()


def download_video(video_url):
    """Download video from EvoLink CDN (no auth required on result URLs)"""
    print(f"Downloading video from: {video_url}")
    response = requests.get(video_url, stream=True)
    response.raise_for_status()
    return response.content


def upload_video_to_s3(video_id, video_data):
    """Upload video bytes to S3 and return a 7-day presigned URL"""
    key = f"videos/{video_id}.mp4"
    s3_client.put_object(
        Bucket=VIDEOS_BUCKET,
        Key=key,
        Body=video_data,
        ContentType='video/mp4'
    )
    url = s3_client.generate_presigned_url(
        'get_object',
        Params={'Bucket': VIDEOS_BUCKET, 'Key': key},
        ExpiresIn=604800  # 7 days
    )
    return url


def cleanup_temp_images(video_id, model=''):
    """Delete the short-lived reference images uploaded to S3 before the EvoLink call"""
    if os.environ.get('DEBUG_KEEP_TEMP_IMAGES'):
        print(f"DEBUG_KEEP_TEMP_IMAGES set — skipping cleanup for video {video_id}")
        return
    if model.startswith('gemini-veo'):
        print(f"Skipping cleanup for veo model inspection — video {video_id}")
        return
    for suffix in ('start', 'end'):
        key = f"temp-images/{video_id}-{suffix}.jpg"
        try:
            s3_client.delete_object(Bucket=VIDEOS_BUCKET, Key=key)
            print(f"Deleted temp image: {key}")
        except Exception as e:
            print(f"Warning: could not delete {key}: {e}")


def _check_fal_status(fal_model_id, request_id, fal_status_url=None, fal_result_url=None):
    """Poll fal.ai queue and return a normalized status dict matching evolink shape."""
    status_url = fal_status_url or f"{FAL_QUEUE_BASE}/{fal_model_id}/requests/{request_id}/status"
    headers = {'Authorization': f'Key {FAL_API_KEY}'}
    response = requests.get(status_url, headers=headers)
    print(f"fal.ai status {response.status_code} for {request_id}: {response.text[:500]}")
    response.raise_for_status()
    raw = response.json()
    fal_status = raw.get('status')

    if fal_status == 'COMPLETED':
        result_url = fal_result_url or f"{FAL_QUEUE_BASE}/{fal_model_id}/requests/{request_id}"
        result_response = requests.get(result_url, headers=headers)
        body_text = result_response.text
        print(f"fal.ai result {result_response.status_code} for {request_id}: {body_text[:1000]}")

        if not result_response.ok:
            try:
                detail = result_response.json()
            except Exception:
                detail = body_text[:500]
            err_msg = f'fal result {result_response.status_code}: {detail}'
            # 422 on the result endpoint almost always means moderation/policy rejection
            if result_response.status_code == 422:
                err_msg = f'[likely content policy rejection] {err_msg}'
            return {'status': 'failed', 'error': err_msg}

        result_json = result_response.json()
        video_url = (result_json.get('video') or {}).get('url')
        if not video_url:
            print(f"fal.ai completed with no video URL. Full payload: {result_json}")
            return {'status': 'failed', 'error': f'fal completed without video URL: {result_json}'}
        return {'status': 'completed', 'results': [video_url]}

    if fal_status in ('IN_QUEUE', 'IN_PROGRESS'):
        return {'status': 'processing'}

    error = raw.get('error') or f'Unexpected fal.ai status: {fal_status} (full response: {raw})'
    print(f"fal.ai non-terminal/unexpected status for {request_id}: {raw}")
    return {'status': 'failed', 'error': error}


def _mark_failed(video_id, error_msg):
    """Write a failed status to DynamoDB"""
    try:
        timestamp = int(time.time() * 1000)
        videos_table.update_item(
            Key={'id': video_id},
            UpdateExpression='SET #status = :status, #error = :error, updatedAt = :updated',
            ExpressionAttributeNames={'#status': 'status', '#error': 'error'},
            ExpressionAttributeValues={
                ':status': 'failed',
                ':error': error_msg,
                ':updated': timestamp
            }
        )
    except Exception as update_error:
        print(f"Failed to update DynamoDB for {video_id}: {str(update_error)}")
