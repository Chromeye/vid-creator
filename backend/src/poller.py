import json
import os
import time
import boto3
import requests
from botocore.exceptions import ClientError

# Initialize AWS clients
s3_client = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')

# Environment variables
VIDEOS_BUCKET = os.environ['VIDEOS_BUCKET']
VIDEOS_TABLE = os.environ['VIDEOS_TABLE']
GEMINI_API_KEY = os.environ['GEMINI_API_KEY']

# DynamoDB table
videos_table = dynamodb.Table(VIDEOS_TABLE)

STATUS_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/"


def get_nested(data, keys, default=None):
    """Get nested value using list of keys"""
    for key in keys:
        try:
            data = data[key]
        except (KeyError, TypeError, IndexError):
            return default
    return data


def lambda_handler(event, context):
    """Poll Gemini job status and update DynamoDB when complete"""

    print(f"Poller event: {json.dumps(event)}")

    video_id = event['videoId']
    job_name = event['jobName']

    # Check if we're in mock mode
    use_mock = os.environ.get('USE_MOCK_GEMINI', 'false').lower() == 'true'

    try:
        if use_mock:
            # Mock mode: simulate video generation
            print(f"[MOCK MODE] Simulating video generation for {video_id}")
            time.sleep(8)  # Simulate 8 seconds of processing

            # Create fake S3 URL (don't actually upload in mock mode)
            s3_url = f"https://{VIDEOS_BUCKET}.s3.amazonaws.com/videos/{video_id}.mp4"
            print(f"[MOCK MODE] Generated fake video URL: {s3_url}")

            # Update DynamoDB
            timestamp = int(time.time() * 1000)
            videos_table.update_item(
                Key={'id': video_id},
                UpdateExpression='SET #status = :status, videoUrl = :url, updatedAt = :updated',
                ExpressionAttributeNames={'#status': 'status'},
                ExpressionAttributeValues={
                    ':status': 'completed',
                    ':url': s3_url,
                    ':updated': timestamp
                }
            )

            print(f"[MOCK MODE] Video completed and uploaded: {s3_url}")
            return {'statusCode': 200, 'videoId': video_id, 'status': 'completed'}

        # Real mode: Poll Gemini job status
        max_polls = 60  # 5 minutes max (60 * 5 seconds)
        poll_count = 0

        while poll_count < max_polls:
            status = check_job_status(job_name)

            if status.get('done'):
                print(f"Job completed for video: {video_id}")

                # Extract video URL
                video_url = get_nested(
                    status,
                    ['response', 'generateVideoResponse',
                        'generatedSamples', 0, 'video', 'uri'],
                    default=None
                )

                if video_url:
                    print(f"Video URL: {video_url}")

                    # Download video from Gemini
                    video_data = download_video(video_url)

                    # Upload to S3
                    s3_url = upload_video_to_s3(video_id, video_data)

                    # Update DynamoDB
                    timestamp = int(time.time() * 1000)
                    videos_table.update_item(
                        Key={'id': video_id},
                        UpdateExpression='SET #status = :status, videoUrl = :url, updatedAt = :updated',
                        ExpressionAttributeNames={'#status': 'status'},
                        ExpressionAttributeValues={
                            ':status': 'completed',
                            ':url': s3_url,
                            ':updated': timestamp
                        }
                    )

                    print(f"Video completed and uploaded: {s3_url}")
                    return {'statusCode': 200, 'videoId': video_id, 'status': 'completed'}
                else:
                    # Job done but no video URL (error case)
                    error_msg = get_nested(
                        status, ['error', 'message'], 'Unknown error')
                    print(f"Job failed: {error_msg}")

                    timestamp = int(time.time() * 1000)
                    videos_table.update_item(
                        Key={'id': video_id},
                        UpdateExpression='SET #status = :status, #error = :error, updatedAt = :updated',
                        ExpressionAttributeNames={
                            '#status': 'status', '#error': 'error'},
                        ExpressionAttributeValues={
                            ':status': 'failed',
                            ':error': error_msg,
                            ':updated': timestamp
                        }
                    )

                    return {'statusCode': 500, 'videoId': video_id, 'status': 'failed', 'error': error_msg}

            # Job still processing, wait and retry
            poll_count += 1
            if poll_count < max_polls:
                time.sleep(5)

        # Timeout - mark as failed
        print(f"Job timed out for video: {video_id}")
        timestamp = int(time.time() * 1000)
        videos_table.update_item(
            Key={'id': video_id},
            UpdateExpression='SET #status = :status, #error = :error, updatedAt = :updated',
            ExpressionAttributeNames={'#status': 'status', '#error': 'error'},
            ExpressionAttributeValues={
                ':status': 'failed',
                ':error': 'Video generation timed out',
                ':updated': timestamp
            }
        )

        return {'statusCode': 408, 'videoId': video_id, 'status': 'timeout'}

    except Exception as e:
        print(f"Error in poller: {str(e)}")

        # Update DynamoDB with error
        try:
            timestamp = int(time.time() * 1000)
            videos_table.update_item(
                Key={'id': video_id},
                UpdateExpression='SET #status = :status, #error = :error, updatedAt = :updated',
                ExpressionAttributeNames={
                    '#status': 'status', '#error': 'error'},
                ExpressionAttributeValues={
                    ':status': 'failed',
                    ':error': str(e),
                    ':updated': timestamp
                }
            )
        except Exception as update_error:
            print(f"Failed to update DynamoDB: {str(update_error)}")

        return {'statusCode': 500, 'error': str(e)}


def check_job_status(job_name):
    """Check the status of a Gemini video generation job"""
    headers = {
        'Content-Type': 'application/json',
        'x-goog-api-key': GEMINI_API_KEY
    }
    url = STATUS_ENDPOINT + job_name
    print(f"Checking job status at: {url}")
    response = requests.get(url, headers=headers)
    print(f"Status response code: {response.status_code}")
    print(f"Status response body: {response.text}")
    return json.loads(response.content)


def download_video(video_url):
    """Download video from Gemini URL"""
    print(f"Downloading video from: {video_url}")
    headers = {
        'Content-Type': 'application/json',
        'x-goog-api-key': GEMINI_API_KEY
    }
    response = requests.get(video_url, headers=headers)
    response.raise_for_status()
    return response.content


def upload_video_to_s3(video_id, video_data):
    """Upload generated video to S3 and return pre-signed URL"""
    try:
        key = f"videos/{video_id}.mp4"

        s3_client.put_object(
            Bucket=VIDEOS_BUCKET,
            Key=key,
            Body=video_data,
            ContentType='video/mp4'
        )

        # Generate pre-signed URL (valid for 7 days)
        url = s3_client.generate_presigned_url(
            'get_object',
            Params={
                'Bucket': VIDEOS_BUCKET,
                'Key': key
            },
            ExpiresIn=604800  # 7 days in seconds
        )

        return url

    except ClientError as e:
        print(f"Error uploading to S3: {str(e)}")
        raise
