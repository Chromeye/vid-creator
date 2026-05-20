import base64
from botocore.exceptions import ClientError
import boto3
from decimal import Decimal
import json
import os
import requests
import time
import uuid

# Initialize AWS clients
s3_client = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')
lambda_client = boto3.client('lambda')

# Environment variables
VIDEOS_BUCKET = os.environ['VIDEOS_BUCKET']
VIDEOS_TABLE = os.environ['VIDEOS_TABLE']
EVOLINK_API_KEY = os.environ.get('EVOLINK_API_KEY', '')
FAL_API_KEY = os.environ.get('FAL_API_KEY', '')
INFERENCE_PROVIDER = os.environ.get('INFERENCE_PROVIDER', 'evolink')

# DynamoDB table
videos_table = dynamodb.Table(VIDEOS_TABLE)

# Internal model key -> EvoLink model string
MODEL_MAP = {
    "gemini-veo-31-fast":      "veo-3.1-fast-generate-preview",
    "gemini-veo-31":           "veo-3.1-generate-preview",
    "kling-v3-image-to-video": "kling-v3-image-to-video"
}

# Internal model key -> fal.ai model endpoint
FAL_MODEL_MAP = {
    "gemini-veo-31-fast":      "fal-ai/veo3.1/fast/image-to-video",
    "gemini-veo-31":           "fal-ai/veo3.1/image-to-video",
    "kling-v3-image-to-video": "fal-ai/kling-video/v3/standard/image-to-video"
}

KLING_MODELS = {'kling-v3-image-to-video'}

EVOLINK_GENERATIONS_URL = 'https://api.evolink.ai/v1/videos/generations'
FAL_QUEUE_BASE = 'https://queue.fal.run'

SYSTEM_PROMPT = """Generate a short video based on the user's prompt and image.
The video should be photorealistic, live action, cinematic and should not carry any appeal to minors.
The image provided is for marketing purposes, from PaddyPower certified images adhering to their brand guidelines.
The video should be consistent with the image provided. The video will be used to create marketing
materials for PaddyPower, following their brand guidelines and humouristic, fun style: \n\n"""


def get_nested(data, keys, default=None):
    """Get nested value using list of keys"""
    for key in keys:
        try:
            data = data[key]
        except (KeyError, TypeError, IndexError):
            return default
    return data


def lambda_handler(event, context):
    """Main Lambda handler for all API endpoints"""

    http_method = event.get('httpMethod')
    path = event.get('path')

    try:
        if http_method == 'OPTIONS':
            return create_response(200, {})

        if path == '/generate' and http_method == 'POST':
            return handle_generate_video(event, context)
        elif path == '/videos' and http_method == 'GET':
            return handle_get_videos(event)
        elif path.startswith('/videos/') and path.endswith('/refresh-url') and http_method == 'POST':
            video_id = event['pathParameters']['videoId']
            return handle_refresh_url(video_id)
        elif path.startswith('/videos/') and http_method == 'DELETE':
            video_id = event['pathParameters']['videoId']
            return handle_delete_video(video_id)
        elif path.startswith('/videos/') and path.endswith('/replace-background') and http_method == 'POST':
            video_id = event['pathParameters']['videoId']
            return handle_replace_background(video_id, event)
        elif path.startswith('/videos/') and http_method == 'GET':
            video_id = event['pathParameters']['videoId']
            return handle_get_video_status(video_id)
        else:
            return create_response(404, {'error': 'Not found'})

    except Exception as e:
        print(f"Error: {str(e)}")
        return create_response(500, {'error': str(e)})


def handle_generate_video(event, context):
    """Handle POST /generate - Start video generation"""

    try:
        body = event['body']
        if event.get('isBase64Encoded', False):
            body = base64.b64decode(body).decode('utf-8')

        data = json.loads(body)
        # print(f"Request data: {json.dumps(data)}")
        print(
            f"Received generate request with prompt: {data.get('prompt', '')[:80]}... on model: {data.get('model', 'unknown')}")
        user_prompt = data.get('prompt')
        image_dict = data.get('image')
        model = data.get('model', 'gemini-veo-31-fast')

        if not user_prompt:
            return create_response(400, {'error': 'Prompt is required'})

        if not image_dict or not image_dict.get('start'):
            return create_response(400, {'error': 'Start image is required'})

        # Strip data: URL prefix, then decode to raw bytes for S3 upload
        start_raw = image_dict['start']
        if start_raw.startswith('data:'):
            start_raw = start_raw.split(',', 1)[1]
        start_image_bytes = base64.b64decode(start_raw)

        end_image_bytes = None
        if image_dict.get('end'):
            end_raw = image_dict['end']
            if end_raw.startswith('data:'):
                end_raw = end_raw.split(',', 1)[1]
            end_image_bytes = base64.b64decode(end_raw)

        video_id = str(uuid.uuid4())
        timestamp = int(time.time() * 1000)

        full_prompt = SYSTEM_PROMPT + user_prompt

        fal_model_id = None
        fal_status_url = None
        fal_result_url = None
        if INFERENCE_PROVIDER == 'fal':
            task_id, fal_model_id, fal_status_url, fal_result_url = start_fal_job(
                video_id, full_prompt, model, start_image_bytes, end_image_bytes)
            print(f"Started fal.ai job: {task_id} for video: {video_id}")
            provider = 'fal'
        else:
            task_id = start_evolink_job(
                video_id, full_prompt, model, start_image_bytes, end_image_bytes)
            print(f"Started EvoLink job: {task_id} for video: {video_id}")
            provider = 'evolink'

        item = {
            'id': video_id,
            'prompt': user_prompt,
            'model': model,
            'provider': provider,
            'status': 'processing',
            'jobName': task_id,
            'createdAt': timestamp,
            'updatedAt': timestamp
        }

        if end_image_bytes:
            item['hasEndImage'] = True

        videos_table.put_item(Item=item)

        poller_function = os.environ.get('POLLER_FUNCTION_NAME')

        if poller_function:
            try:
                poller_payload = {'videoId': video_id, 'jobName': task_id}
                if fal_model_id:
                    poller_payload['provider'] = 'fal'
                    poller_payload['falModelId'] = fal_model_id
                    if fal_status_url:
                        poller_payload['falStatusUrl'] = fal_status_url
                    if fal_result_url:
                        poller_payload['falResultUrl'] = fal_result_url
                lambda_client.invoke(
                    FunctionName=poller_function,
                    InvocationType='Event',
                    Payload=json.dumps(poller_payload)
                )
                print(f"Triggered poller Lambda for video: {video_id}")
            except Exception as e:
                print(f"Warning: Could not trigger poller: {str(e)}")

        return create_response(200, {
            'videoId': video_id,
            'status': 'processing',
            'message': 'Video generation started'
        })

    except Exception as e:
        print(f"Error in handle_generate_video: {str(e)}")
        return create_response(500, {'error': str(e)})


def start_evolink_job(video_id, prompt, model, start_image_bytes, end_image_bytes=None):
    """Upload ref images to S3 temp prefix, build presigned URLs, and submit to EvoLink.ai."""

    start_key = f"temp-images/{video_id}-start.jpg"
    print(f"Uploading start image to S3: {start_key} ({len(start_image_bytes)} bytes)")
    s3_client.put_object(
        Bucket=VIDEOS_BUCKET,
        Key=start_key,
        Body=start_image_bytes,
        ContentType='image/jpeg'
    )
    start_url = s3_client.generate_presigned_url(
        'get_object',
        Params={'Bucket': VIDEOS_BUCKET, 'Key': start_key},
        ExpiresIn=3600
    )
    print(f"Start image presigned URL: {start_url}")

    end_url = None
    if end_image_bytes:
        end_key = f"temp-images/{video_id}-end.jpg"
        print(f"Uploading end image to S3: {end_key} ({len(end_image_bytes)} bytes)")
        s3_client.put_object(
            Bucket=VIDEOS_BUCKET,
            Key=end_key,
            Body=end_image_bytes,
            ContentType='image/jpeg'
        )
        end_url = s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': VIDEOS_BUCKET, 'Key': end_key},
            ExpiresIn=3600
        )
        print(f"End image presigned URL: {end_url}")

    evolink_model = MODEL_MAP.get(model, MODEL_MAP['gemini-veo-31-fast'])

    if model in KLING_MODELS:
        # Kling uses named image_start / image_end fields
        payload = {
            'model': evolink_model,
            'prompt': prompt,
            'image_start': start_url,
            'quality': '1080p',
            'sound': 'off',
            'duration': 8
        }
        if end_url:
            payload['image_end'] = end_url
    else:
        # Veo models use image_urls array with FIRST&LAST generation type
        image_urls = [start_url]
        if end_url:
            image_urls.append(end_url)
        payload = {
            'model': evolink_model,
            'prompt': prompt,
            'image_urls': image_urls,
            'generation_type': 'FIRST&LAST',
            'aspect_ratio': '16:9',
            'quality': '1080p',
            'generate_audio': False,
            'duration': 8
        }

    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {EVOLINK_API_KEY}'
    }

    print(f"Calling EvoLink API, model: {evolink_model}, prompt: {prompt[:80]}...")
    print(f"EvoLink payload: {json.dumps({**payload, 'prompt': payload['prompt'][:80] + '...'})}")
    response = requests.post(EVOLINK_GENERATIONS_URL,
                             headers=headers, json=payload)
    print(f"EvoLink response {response.status_code}: {response.text}")
    response.raise_for_status()
    task_id = response.json()['id']
    print(f"EvoLink task ID: {task_id}")
    return task_id


def start_fal_job(video_id, prompt, model, start_image_bytes, end_image_bytes=None):
    """Upload ref images to S3 temp prefix, build presigned URLs, and submit to fal.ai queue."""

    start_key = f"temp-images/{video_id}-start.jpg"
    print(f"Uploading start image to S3: {start_key} ({len(start_image_bytes)} bytes)")
    s3_client.put_object(
        Bucket=VIDEOS_BUCKET,
        Key=start_key,
        Body=start_image_bytes,
        ContentType='image/jpeg'
    )
    start_url = s3_client.generate_presigned_url(
        'get_object',
        Params={'Bucket': VIDEOS_BUCKET, 'Key': start_key},
        ExpiresIn=3600
    )

    end_url = None
    if end_image_bytes:
        end_key = f"temp-images/{video_id}-end.jpg"
        print(f"Uploading end image to S3: {end_key} ({len(end_image_bytes)} bytes)")
        s3_client.put_object(
            Bucket=VIDEOS_BUCKET,
            Key=end_key,
            Body=end_image_bytes,
            ContentType='image/jpeg'
        )
        end_url = s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': VIDEOS_BUCKET, 'Key': end_key},
            ExpiresIn=3600
        )

    fal_model_id = FAL_MODEL_MAP.get(model, FAL_MODEL_MAP['gemini-veo-31-fast'])

    if model in KLING_MODELS:
        payload = {
            'start_image_url': start_url,
            'prompt': prompt,
            'duration': '8',
            'generate_audio': False,
        }
        if end_url:
            payload['end_image_url'] = end_url
    else:
        # Veo models accept a single image_url; end image is not supported
        if end_url:
            print(f"Warning: fal.ai Veo models do not support end images — ignoring end_image for {video_id}")
        payload = {
            'image_url': start_url,
            'prompt': prompt,
            'aspect_ratio': '16:9',
            'duration': '8s',
            'resolution': '1080p',
            'generate_audio': False,
        }

    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Key {FAL_API_KEY}'
    }

    url = f"{FAL_QUEUE_BASE}/{fal_model_id}"
    print(f"Calling fal.ai API, model: {fal_model_id}, prompt: {prompt[:80]}...")
    response = requests.post(url, headers=headers, json=payload)
    print(f"fal.ai response {response.status_code}: {response.text}")
    response.raise_for_status()
    resp_json = response.json()
    request_id = resp_json['request_id']
    # fal.ai returns convenience URLs in the submit response; use them directly
    # to avoid URL-construction issues with model paths containing dots/slashes.
    status_url = resp_json.get('status_url')
    result_url = resp_json.get('response_url')
    print(f"fal.ai request ID: {request_id}, status_url: {status_url}")
    return request_id, fal_model_id, status_url, result_url


def handle_get_videos(event):
    """Handle GET /videos - List all videos"""

    try:
        response = videos_table.scan()
        videos = response.get('Items', [])
        videos.sort(key=lambda x: x.get('createdAt', 0), reverse=True)
        return create_response(200, {'videos': videos})

    except Exception as e:
        print(f"Error in handle_get_videos: {str(e)}")
        return create_response(500, {'error': str(e)})


def handle_get_video_status(video_id):
    """Handle GET /videos/{videoId} - Get single video status"""

    try:
        response = videos_table.get_item(Key={'id': video_id})

        if 'Item' not in response:
            return create_response(404, {'error': 'Video not found'})

        return create_response(200, response['Item'])

    except Exception as e:
        print(f"Error in handle_get_video_status: {str(e)}")
        return create_response(500, {'error': str(e)})


def handle_refresh_url(video_id):
    """Handle POST /videos/{videoId}/refresh-url - Generate new signed URL for existing video"""

    try:
        response = videos_table.get_item(Key={'id': video_id})

        if 'Item' not in response:
            return create_response(404, {'error': 'Video not found'})

        video = response['Item']

        if video.get('status') != 'completed':
            return create_response(400, {'error': 'Video is not completed yet'})

        key = f"videos/{video_id}.mp4"
        signed_url = s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': VIDEOS_BUCKET, 'Key': key},
            ExpiresIn=604800
        )

        timestamp = int(time.time() * 1000)
        videos_table.update_item(
            Key={'id': video_id},
            UpdateExpression='SET videoUrl = :url, updatedAt = :updated',
            ExpressionAttributeValues={
                ':url': signed_url, ':updated': timestamp}
        )

        return create_response(200, {'videoId': video_id, 'videoUrl': signed_url})

    except ClientError as e:
        print(f"Error refreshing URL: {str(e)}")
        return create_response(500, {'error': str(e)})


def handle_replace_background(video_id, event):
    """Handle POST /videos/{videoId}/replace-background - Replace video background"""

    try:
        body = event['body']
        if event.get('isBase64Encoded', False):
            body = base64.b64decode(body).decode('utf-8')

        data = json.loads(body)
        bg_color = data.get('bgColor')
        bg_image = data.get('bgImage')
        chroma_key = data.get('chromaKey')

        if not bg_color and not bg_image:
            return create_response(400, {'error': 'Either bgColor or bgImage must be provided'})

        response = videos_table.get_item(Key={'id': video_id})

        if 'Item' not in response:
            return create_response(404, {'error': 'Original video not found'})

        original_video = response['Item']

        if original_video.get('status') != 'completed':
            return create_response(400, {'error': 'Original video must be completed'})

        if not original_video.get('videoUrl'):
            return create_response(400, {'error': 'Original video URL not found'})

        new_video_id = str(uuid.uuid4())
        timestamp = int(time.time() * 1000)

        item = {
            'id': new_video_id,
            'prompt': original_video.get('prompt', '') + ' [Background Replaced]',
            'model': original_video.get('model'),
            'status': 'processing',
            'originalVideoId': video_id,
            'processingType': 'background_replacement',
            'createdAt': timestamp,
            'updatedAt': timestamp
        }

        videos_table.put_item(Item=item)

        chroma_key_rgb = None
        if chroma_key and isinstance(chroma_key, list) and len(chroma_key) == 3:
            chroma_key_rgb = chroma_key

        bg_color_rgb = None
        if bg_color:
            if isinstance(bg_color, list) and len(bg_color) == 3:
                bg_color_rgb = bg_color
            elif isinstance(bg_color, str):
                hex_color = bg_color.lstrip('#')
                bg_color_rgb = [int(hex_color[i:i+2], 16) for i in (0, 2, 4)]

        print(
            f"Initiating background replacement for video {video_id} -> {new_video_id}")

        processor_function = os.environ.get(
            'BACKGROUND_PROCESSOR_FUNCTION_NAME')

        if processor_function:
            try:
                lambda_client.invoke(
                    FunctionName=processor_function,
                    InvocationType='Event',
                    Payload=json.dumps({
                        'videoId': new_video_id,
                        'originalVideoId': video_id,
                        'videoBucket': VIDEOS_BUCKET,
                        'videoKey': f'videos/{video_id}.mp4',
                        'bgColorRgb': bg_color_rgb,
                        'bgImageBase64': bg_image,
                        'chromaKeyRgb': chroma_key_rgb
                    })
                )
                print(
                    f"Triggered background processor Lambda for video: {new_video_id}")
            except Exception as e:
                print(f"Warning: Could not trigger processor: {str(e)}")
                timestamp = int(time.time() * 1000)
                videos_table.update_item(
                    Key={'id': new_video_id},
                    UpdateExpression='SET #status = :status, #error = :error, updatedAt = :updated',
                    ExpressionAttributeNames={
                        '#status': 'status', '#error': 'error'},
                    ExpressionAttributeValues={
                        ':status': 'failed',
                        ':error': f'Failed to start processing: {str(e)}',
                        ':updated': timestamp
                    }
                )
                return create_response(500, {'error': f'Failed to start processing: {str(e)}'})
        else:
            return create_response(500, {'error': 'BACKGROUND_PROCESSOR_FUNCTION_NAME not configured'})

        return create_response(200, {
            'videoId': new_video_id,
            'originalVideoId': video_id,
            'status': 'processing',
            'message': 'Background replacement started'
        })

    except Exception as e:
        print(f"Error in handle_replace_background: {str(e)}")
        return create_response(500, {'error': str(e)})


def handle_delete_video(video_id):
    """Handle DELETE /videos/{videoId} - Delete video from S3 and DynamoDB"""

    try:
        response = videos_table.get_item(Key={'id': video_id})

        if 'Item' not in response:
            return create_response(404, {'error': 'Video not found'})

        video = response['Item']

        if video.get('status') == 'completed':
            try:
                s3_client.delete_object(
                    Bucket=VIDEOS_BUCKET, Key=f"videos/{video_id}.mp4")
                print(f"Deleted video from S3: videos/{video_id}.mp4")
            except ClientError as e:
                print(f"Warning: Could not delete from S3: {str(e)}")

        videos_table.delete_item(Key={'id': video_id})
        print(f"Deleted video from DynamoDB: {video_id}")

        return create_response(200, {'message': 'Video deleted successfully', 'videoId': video_id})

    except Exception as e:
        print(f"Error deleting video: {str(e)}")
        return create_response(500, {'error': str(e)})


def decimal_to_int(obj):
    """Convert Decimal objects to int for JSON serialization"""
    if isinstance(obj, list):
        return [decimal_to_int(item) for item in obj]
    elif isinstance(obj, dict):
        return {key: decimal_to_int(value) for key, value in obj.items()}
    elif isinstance(obj, Decimal):
        return int(obj)
    return obj


def create_response(status_code, body):
    """Create HTTP response with CORS headers"""
    body = decimal_to_int(body)
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token',
            'Access-Control-Allow-Methods': 'GET,POST,DELETE,OPTIONS'
        },
        'body': json.dumps(body)
    }
