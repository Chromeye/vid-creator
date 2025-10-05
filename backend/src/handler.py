import json
import os
import uuid
import base64
import time
from datetime import datetime
from decimal import Decimal
import boto3
from botocore.exceptions import ClientError
import requests

# Initialize AWS clients
s3_client = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')
lambda_client = boto3.client('lambda')

# Environment variables
VIDEOS_BUCKET = os.environ['VIDEOS_BUCKET']
VIDEOS_TABLE = os.environ['VIDEOS_TABLE']
GEMINI_API_KEY = os.environ['GEMINI_API_KEY']
USE_MOCK_GEMINI = os.environ.get('USE_MOCK_GEMINI', 'false').lower() == 'true'

# DynamoDB table
videos_table = dynamodb.Table(VIDEOS_TABLE)

MODEL_ID = "veo-3.0-fast-generate-001"
API_ENDPOINT = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_ID}:predictLongRunning"
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
    """Main Lambda handler for all API endpoints"""
    print(f"Event: {json.dumps(event)}")

    http_method = event.get('httpMethod')
    path = event.get('path')

    try:
        # Route requests to appropriate handlers
        if path == '/generate' and http_method == 'POST':
            return handle_generate_video(event, context)
        elif path == '/videos' and http_method == 'GET':
            return handle_get_videos(event)
        elif path.startswith('/videos/') and path.endswith('/refresh-url') and http_method == 'POST':
            video_id = event['pathParameters']['videoId']
            return handle_refresh_url(video_id)
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
        # Parse multipart form data
        content_type = event['headers'].get('content-type', '')

        if 'multipart/form-data' in content_type:
            body = event['body']
            is_base64 = event.get('isBase64Encoded', False)

            if is_base64:
                body = base64.b64decode(body)

            # Parse form data (simplified - you may want to use a library)
            # For now, expecting JSON body with base64 encoded image
            data = json.loads(event['body'])
            prompt = data.get('prompt')
            image_data = data.get('image')  # base64 encoded image
        else:
            # JSON body
            data = json.loads(event['body'])
            prompt = data.get('prompt')
            image_data = data.get('image')

        if not prompt:
            return create_response(400, {'error': 'Prompt is required'})

        if not image_data:
            return create_response(400, {'error': 'Image is required'})

        # Decode base64 image (remove data URL prefix if present)
        if image_data.startswith('data:'):
            # Remove "data:image/jpeg;base64," prefix
            image_data = image_data.split(',', 1)[1]

        # Generate unique video ID
        video_id = str(uuid.uuid4())
        # Convert to milliseconds for JavaScript
        timestamp = int(time.time() * 1000)

        # Start Gemini job (just initiate, don't wait)
        job_name = start_gemini_job(prompt, image_data)
        print(f"Started Gemini job: {job_name} for video: {video_id}")

        # Store initial metadata in DynamoDB with job name
        videos_table.put_item(
            Item={
                'id': video_id,
                'prompt': prompt,
                'status': 'processing',
                'jobName': job_name,
                'createdAt': timestamp,
                'updatedAt': timestamp
            }
        )

        # Get poller Lambda function name from environment
        poller_function = os.environ.get('POLLER_FUNCTION_NAME')

        if poller_function:
            try:
                # Invoke poller Lambda asynchronously
                lambda_client.invoke(
                    FunctionName=poller_function,
                    InvocationType='Event',  # Async invocation
                    Payload=json.dumps({
                        'videoId': video_id,
                        'jobName': job_name
                    })
                )
                print(f"Triggered poller Lambda for video: {video_id}")
            except Exception as e:
                print(f"Warning: Could not trigger poller: {str(e)}")
                # Continue anyway - frontend can poll manually

        return create_response(200, {
            'videoId': video_id,
            'status': 'processing',
            'message': 'Video generation started'
        })

    except Exception as e:
        print(f"Error in handle_generate_video: {str(e)}")
        return create_response(500, {'error': str(e)})


def start_gemini_job(prompt, image_base64):
    """Start Gemini video generation job and return job name"""

    # Mock mode for testing
    use_mock = os.environ.get('USE_MOCK_GEMINI', 'false').lower() == 'true'
    print(
        f"DEBUG: USE_MOCK_GEMINI={os.environ.get('USE_MOCK_GEMINI')}, use_mock={use_mock}")
    if use_mock:
        job_name = f"mock-job-{uuid.uuid4()}"
        print(f"[MOCK MODE] Created mock job: {job_name} for prompt: {prompt}")
        return job_name

    # Real Gemini API call
    headers = {
        'Content-Type': 'application/json',
        'x-goog-api-key': GEMINI_API_KEY
    }
    instances = [{"prompt": prompt,
                  "image": {
                      "bytesBase64Encoded": image_base64,
                      "mimeType": "image/png"
                  }
                  }]
    parameters = {
        "aspectRatio": "16:9",
    }

    print(f"Calling Gemini API with prompt: {prompt}")
    # Truncate for logging
    response = requests.post(API_ENDPOINT,
                             headers=headers,
                             json={"instances": instances,
                                   "parameters": parameters})

    print(f"Gemini response status: {response.status_code}")
    print(f"Gemini response body: {response.text}")
    response.raise_for_status()
    job_name = json.loads(response.content)["name"]
    print(f"Job name: {job_name}")

    return job_name


def handle_get_videos(event):
    """Handle GET /videos - List all videos"""

    try:
        # Scan DynamoDB table (in production, use pagination)
        response = videos_table.scan()
        videos = response.get('Items', [])

        # Sort by createdAt (newest first)
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
        # Get video from DynamoDB
        response = videos_table.get_item(Key={'id': video_id})

        if 'Item' not in response:
            return create_response(404, {'error': 'Video not found'})

        video = response['Item']

        # Only refresh URL for completed videos
        if video.get('status') != 'completed':
            return create_response(400, {'error': 'Video is not completed yet'})

        # Generate new pre-signed URL (valid for 7 days)
        key = f"videos/{video_id}.mp4"
        signed_url = s3_client.generate_presigned_url(
            'get_object',
            Params={
                'Bucket': VIDEOS_BUCKET,
                'Key': key
            },
            ExpiresIn=604800  # 7 days in seconds
        )

        # Update DynamoDB with new URL
        timestamp = int(time.time() * 1000)
        videos_table.update_item(
            Key={'id': video_id},
            UpdateExpression='SET videoUrl = :url, updatedAt = :updated',
            ExpressionAttributeValues={
                ':url': signed_url,
                ':updated': timestamp
            }
        )

        return create_response(200, {
            'videoId': video_id,
            'videoUrl': signed_url
        })

    except ClientError as e:
        print(f"Error refreshing URL: {str(e)}")
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

    # Convert Decimals to ints
    body = decimal_to_int(body)

    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token',
            'Access-Control-Allow-Methods': 'GET,POST,OPTIONS'
        },
        'body': json.dumps(body)
    }
