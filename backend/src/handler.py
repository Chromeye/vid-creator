import base64
from botocore.exceptions import ClientError
import boto3
from datetime import datetime
from decimal import Decimal
import json
import os
import requests
import time
import uuid
import shutil

# Initialize AWS clients
s3_client = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')
lambda_client = boto3.client('lambda')

# Environment variables
VIDEOS_BUCKET = os.environ['VIDEOS_BUCKET']
VIDEOS_TABLE = os.environ['VIDEOS_TABLE']
GEMINI_API_KEY = os.environ['GEMINI_API_KEY']

# DynamoDB table
videos_table = dynamodb.Table(VIDEOS_TABLE)

MODEL_MAP = {"gemini-veo-31-fast": "veo-3.1-fast-generate-preview",
             "gemini-veo-31": "veo-3.1-generate-preview"}

# API_ENDPOINT = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_ID}:predictLongRunning"
STATUS_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/"
SYSTEM_PROMPT = """Generate a short video based on the user's prompt and image. 
The video should be photorealistic, live action, cinematic and should not carry any appeal to minors. 
The image provided is for marketing purposes, from PaddyPower certified images adhering to their brand guidelines. 
The video should be consistent with the image provided. The video will be used to create marketing 
materials for PaddyPower, following their brand guidelines and humouristic, fun style: \n\n"""


def get_api_endpoint(model):
    """Get API endpoint based on model"""
    model_id = MODEL_MAP.get(model, MODEL_MAP["gemini-veo-31-fast"])
    return f"https://generativelanguage.googleapis.com/v1beta/models/{model_id}:predictLongRunning"


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
        # Handle OPTIONS for CORS preflight
        if http_method == 'OPTIONS':
            return create_response(200, {})

        # Route requests to appropriate handlers
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
        # Handle base64 encoded body (API Gateway may encode the entire request body)
        body = event['body']
        if event.get('isBase64Encoded', False):
            body = base64.b64decode(body).decode('utf-8')

        # Parse JSON body
        data = json.loads(body)
        print(f"Request data: {json.dumps(data)}")
        user_prompt = data.get('prompt')
        # object with 'start' and optional 'end'
        image_dict = data.get('image')
        model = data.get('model', 'gemini-veo-31-fast')  # default model

        if not user_prompt:
            return create_response(400, {'error': 'Prompt is required'})

        if not image_dict or not image_dict.get('start'):
            return create_response(400, {'error': 'Start image is required'})

        # Decode base64 images (remove data URL prefix if present)
        start_image_base64 = image_dict.get('start')
        end_image_base64 = image_dict.get('end')  # optional

        if start_image_base64.startswith('data:'):
            # Remove "data:image/jpeg;base64," prefix
            start_image_base64 = start_image_base64.split(',', 1)[1]

        if end_image_base64 and end_image_base64.startswith('data:'):
            # Remove "data:image/jpeg;base64," prefix
            end_image_base64 = end_image_base64.split(',', 1)[1]

        # Generate unique video ID
        video_id = str(uuid.uuid4())
        # Convert to milliseconds for JavaScript
        timestamp = int(time.time() * 1000)

        # Combine system prompt with user prompt for Gemini
        full_prompt = SYSTEM_PROMPT + user_prompt

        # Start Gemini job (just initiate, don't wait)
        job_name = start_gemini_job(
            full_prompt, model, start_image_base64, end_image_base64)
        print(f"Started Gemini job: {job_name} for video: {video_id}")

        # Store only user prompt in DynamoDB (not system prompt)
        item = {
            'id': video_id,
            'prompt': user_prompt,
            'model': model,
            'status': 'processing',
            'jobName': job_name,
            'createdAt': timestamp,
            'updatedAt': timestamp
        }

        # Store whether end image was provided
        if end_image_base64:
            item['hasEndImage'] = True

        videos_table.put_item(Item=item)

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


def start_gemini_job(prompt, model, start_image_base64, end_image_base64=None):
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

    # Build instance with required start image
    instance = {
        "prompt": prompt,
        "image": {
            "bytesBase64Encoded": start_image_base64,
            "mimeType": "image/png"
        }
    }

    # Add optional end image (lastFrame)
    if end_image_base64:
        instance["lastFrame"] = {
            "bytesBase64Encoded": end_image_base64,
            "mimeType": "image/png"
        }

    instances = [instance]
    parameters = {
        "aspectRatio": "16:9",
        "negativePrompt": "cartoon, drawing, low quality, 3D",
        "resolution": "720p"
    }

    print(
        f"Calling Gemini API with prompt: {prompt}, has_end_image: {bool(end_image_base64)}")
    response = requests.post(get_api_endpoint(model),
                             headers=headers,
                             json={"instances": instances,
                                   "parameters": parameters})

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



def handle_replace_background(video_id, event):
    """Handle POST /videos/{videoId}/replace-background - Replace video background"""
    
    try:
        # Parse request body
        body = event['body']
        if event.get('isBase64Encoded', False):
            body = base64.b64decode(body).decode('utf-8')
        
        data = json.loads(body)
        bg_color = data.get('bgColor')  # RGB tuple or null
        bg_image = data.get('bgImage')  # base64 or null
        chroma_key = data.get('chromaKey')  # RGB tuple or null
        
        # Validate at least one background option is provided
        if not bg_color and not bg_image:
            return create_response(400, {'error': 'Either bgColor or bgImage must be provided'})
        
        # Get original video from DynamoDB
        response = videos_table.get_item(Key={'id': video_id})
        
        if 'Item' not in response:
            return create_response(404, {'error': 'Original video not found'})
        
        original_video = response['Item']
        
        # Only process completed videos
        if original_video.get('status') != 'completed':
            return create_response(400, {'error': 'Original video must be completed'})
        
        if not original_video.get('videoUrl'):
            return create_response(400, {'error': 'Original video URL not found'})
        
        # Generate new video ID for the processed video
        new_video_id = str(uuid.uuid4())
        timestamp = int(time.time() * 1000)
        
        # Create new video entry in DynamoDB
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
        
        # Parse chroma key if provided
        chroma_key_rgb = None
        if chroma_key:
            if isinstance(chroma_key, list) and len(chroma_key) == 3:
                chroma_key_rgb = chroma_key
        
        # Parse bg_color if provided
        bg_color_rgb = None
        if bg_color:
            if isinstance(bg_color, list) and len(bg_color) == 3:
                bg_color_rgb = bg_color
            elif isinstance(bg_color, str):
                # Handle hex color
                bg_color = bg_color.lstrip('#')
                bg_color_rgb = [int(bg_color[i:i+2], 16) for i in (0, 2, 4)]
        
        print(f"Initiating background replacement for video {video_id}")
        print(f"  New video ID: {new_video_id}")
        print(f"  BG Color: {bg_color_rgb}")
        print(f"  BG Image: {'provided' if bg_image else 'none'}")
        print(f"  Chroma Key: {chroma_key_rgb}")
        
        # Invoke background processor Lambda asynchronously
        processor_function = os.environ.get('BACKGROUND_PROCESSOR_FUNCTION_NAME')
        
        if processor_function:
            try:
                lambda_client.invoke(
                    FunctionName=processor_function,
                    InvocationType='Event',  # Async invocation
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
                print(f"Triggered background processor Lambda for video: {new_video_id}")
            except Exception as e:
                print(f"Warning: Could not trigger processor: {str(e)}")
                # Update status to failed
                timestamp = int(time.time() * 1000)
                videos_table.update_item(
                    Key={'id': new_video_id},
                    UpdateExpression='SET #status = :status, #error = :error, updatedAt = :updated',
                    ExpressionAttributeNames={
                        '#status': 'status',
                        '#error': 'error'
                    },
                    ExpressionAttributeValues={
                        ':status': 'failed',
                        ':error': f'Failed to start processing: {str(e)}',
                        ':updated': timestamp
                    }
                )
                return create_response(500, {'error': f'Failed to start processing: {str(e)}'})
        else:
            print("Warning: BACKGROUND_PROCESSOR_FUNCTION_NAME not set, processing inline (may timeout)")
            # Fallback to inline processing (not recommended for production)
            try:
                output_path = process_background_replacement(
                    video_url=original_video['videoUrl'],
                    bg_color_rgb=tuple(bg_color_rgb) if bg_color_rgb else None,
                    bg_image_base64=bg_image,
                    chroma_key_rgb=tuple(chroma_key_rgb) if chroma_key_rgb else None
                )
                
                # Upload to S3
                s3_key = f"videos/{new_video_id}.mp4"
                s3_client.upload_file(output_path, VIDEOS_BUCKET, s3_key)
                
                # Generate pre-signed URL
                signed_url = s3_client.generate_presigned_url(
                    'get_object',
                    Params={'Bucket': VIDEOS_BUCKET, 'Key': s3_key},
                    ExpiresIn=604800
                )
                
                # Update DynamoDB
                timestamp = int(time.time() * 1000)
                videos_table.update_item(
                    Key={'id': new_video_id},
                    UpdateExpression='SET #status = :status, videoUrl = :url, updatedAt = :updated',
                    ExpressionAttributeNames={'#status': 'status'},
                    ExpressionAttributeValues={
                        ':status': 'completed',
                        ':url': signed_url,
                        ':updated': timestamp
                    }
                )
                
                # Clean up
                temp_dir = os.path.dirname(output_path)
                shutil.rmtree(temp_dir, ignore_errors=True)
            except Exception as e:
                print(f"Error in inline processing: {str(e)}")
                timestamp = int(time.time() * 1000)
                videos_table.update_item(
                    Key={'id': new_video_id},
                    UpdateExpression='SET #status = :status, #error = :error, updatedAt = :updated',
                    ExpressionAttributeNames={'#status': 'status', '#error': 'error'},
                    ExpressionAttributeValues={
                        ':status': 'failed',
                        ':error': str(e),
                        ':updated': timestamp
                    }
                )
                return create_response(500, {'error': f'Processing failed: {str(e)}'})
        
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
        # Get video from DynamoDB to check if it exists
        response = videos_table.get_item(Key={'id': video_id})

        if 'Item' not in response:
            return create_response(404, {'error': 'Video not found'})

        video = response['Item']

        # Delete from S3 if video is completed
        if video.get('status') == 'completed':
            try:
                key = f"videos/{video_id}.mp4"
                s3_client.delete_object(
                    Bucket=VIDEOS_BUCKET,
                    Key=key
                )
                print(f"Deleted video from S3: {key}")
            except ClientError as e:
                print(f"Warning: Could not delete from S3: {str(e)}")
                # Continue with DynamoDB deletion even if S3 fails

        # Delete from DynamoDB
        videos_table.delete_item(Key={'id': video_id})
        print(f"Deleted video from DynamoDB: {video_id}")

        return create_response(200, {
            'message': 'Video deleted successfully',
            'videoId': video_id
        })

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

    # Convert Decimals to ints
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
