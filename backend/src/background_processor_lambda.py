"""
Background Replacement Processor Lambda (Async)
Invoked asynchronously to process video background replacement
"""

import json
import os
import boto3
import shutil
import tempfile
from background_processor import process_background_replacement
import time

s3_client = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')

VIDEOS_BUCKET = os.environ['VIDEOS_BUCKET']
VIDEOS_TABLE = os.environ['VIDEOS_TABLE']

videos_table = dynamodb.Table(VIDEOS_TABLE)


def lambda_handler(event, context):
    """
    Async Lambda handler for background replacement processing
    
    Event format:
    {
        "videoId": "new-video-id",
        "originalVideoId": "original-video-id",
        "videoBucket": "bucket-name",
        "videoKey": "videos/original-id.mp4",
        "bgColorRgb": [40, 40, 40] or null,
        "bgImageBase64": "base64..." or null,
        "chromaKeyRgb": [0, 171, 69] or null
    }
    """
    print(f"Background processor invoked: {json.dumps(event)}")
    
    video_id = event['videoId']
    original_video_id = event['originalVideoId']
    video_bucket = event['videoBucket']
    video_key = event['videoKey']
    bg_color_rgb = event.get('bgColorRgb')
    bg_image_base64 = event.get('bgImageBase64')
    chroma_key_rgb = event.get('chromaKeyRgb')
    
    try:
        # Download video from S3
        print(f"Downloading video from S3: {video_bucket}/{video_key}")
        temp_dir = tempfile.mkdtemp(prefix='bg_replace_')
        video_path = os.path.join(temp_dir, 'original.mp4')
        
        s3_client.download_file(video_bucket, video_key, video_path)
        print(f"Downloaded video to {video_path}")
        
        # Process the video
        print(f"Processing video {video_id}...")
        output_path = process_background_replacement(
            video_path=video_path,
            bg_color_rgb=tuple(bg_color_rgb) if bg_color_rgb else None,
            bg_image_base64=bg_image_base64,
            chroma_key_rgb=tuple(chroma_key_rgb) if chroma_key_rgb else None
        )
        
        # Upload to S3
        s3_key = f"videos/{video_id}.mp4"
        print(f"Uploading to S3: {s3_key}")
        s3_client.upload_file(output_path, VIDEOS_BUCKET, s3_key)
        
        # Generate pre-signed URL (valid for 7 days)
        signed_url = s3_client.generate_presigned_url(
            'get_object',
            Params={
                'Bucket': VIDEOS_BUCKET,
                'Key': s3_key
            },
            ExpiresIn=604800  # 7 days
        )
        
        # Update DynamoDB with success
        timestamp = int(time.time() * 1000)
        videos_table.update_item(
            Key={'id': video_id},
            UpdateExpression='SET #status = :status, videoUrl = :url, updatedAt = :updated',
            ExpressionAttributeNames={
                '#status': 'status'
            },
            ExpressionAttributeValues={
                ':status': 'completed',
                ':url': signed_url,
                ':updated': timestamp
            }
        )
        
        # Clean up temp files
        temp_dir = os.path.dirname(output_path)
        shutil.rmtree(temp_dir, ignore_errors=True)
        
        print(f"✓ Background replacement completed for {video_id}")
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'videoId': video_id,
                'status': 'completed',
                'videoUrl': signed_url
            })
        }
        
    except Exception as e:
        print(f"✗ Error processing background: {str(e)}")
        
        # Update DynamoDB with failure
        timestamp = int(time.time() * 1000)
        videos_table.update_item(
            Key={'id': video_id},
            UpdateExpression='SET #status = :status, #error = :error, updatedAt = :updated',
            ExpressionAttributeNames={
                '#status': 'status',
                '#error': 'error'
            },
            ExpressionAttributeValues={
                ':status': 'failed',
                ':error': str(e),
                ':updated': timestamp
            }
        )
        
        raise e
