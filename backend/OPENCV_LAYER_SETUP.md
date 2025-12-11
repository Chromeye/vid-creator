# OpenCV Lambda Layer Setup Guide

## Overview
The background replacement feature requires OpenCV (cv2) and numpy to be available in the Lambda environment. This guide explains how to set up the necessary Lambda Layer.

## Option 1: Use Pre-built Public Layer (Recommended)

### KLayers - Community Maintained OpenCV Layers

KLayers provides pre-built Lambda layers for various Python packages including OpenCV.

**For Python 3.11:**
```
arn:aws:lambda:us-east-1:770693421928:layer:Klayers-p311-opencv-python-headless:1
```

**For Python 3.10:**
```
arn:aws:lambda:us-east-1:770693421928:layer:Klayers-p311-opencv-python-headless:1
```

> **Note**: Replace `us-east-1` with your AWS region. Visit [https://github.com/keithrozario/Klayers](https://github.com/keithrozario/Klayers) for the latest ARNs.

### Steps to Add Layer:
1. Go to AWS Lambda Console
2. Select your function
3. Scroll to "Layers" section
4. Click "Add a layer"
5. Choose "Specify an ARN"
6. Paste the ARN above
7. Click "Add"

## Option 2: Build Custom Layer

If you need a specific version or customization:

### Prerequisites
- Docker installed locally
- AWS CLI configured

### Build Script

```bash
#!/bin/bash

# Create build directory
mkdir -p lambda-layer/python
cd lambda-layer

# Use Amazon Linux 2 Docker image (matches Lambda environment)
docker run -v "$PWD":/var/task "public.ecr.aws/sam/build-python3.11" /bin/sh -c "
    pip install opencv-python-headless numpy -t python/
"

# Create zip file
zip -r opencv-layer.zip python

# Upload to AWS (replace YOUR_BUCKET with your S3 bucket)
aws s3 cp opencv-layer.zip s3://YOUR_BUCKET/lambda-layers/

# Publish layer
aws lambda publish-layer-version \
    --layer-name opencv-python \
    --description \"OpenCV and numpy for Python 3.11\" \
    --content S3Bucket=YOUR_BUCKET,S3Key=lambda-layers/opencv-layer.zip \
    --compatible-runtimes python3.11
```

## Lambda Configuration Updates

### Environment Variables
Add these to your Lambda function:

```
VIDEOS_BUCKET=your-videos-bucket
VIDEOS_TABLE=your-videos-table
GEMINI_API_KEY=your-api-key
```

### Memory & Timeout
Update Lambda configuration:
- **Memory**: 3008 MB (recommended for video processing)
- **Timeout**: 900 seconds (15 minutes - maximum allowed)
- **Ephemeral Storage**: 2048 MB (2 GB for temporary video files)

### IAM Permissions
Ensure Lambda execution role has:
```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "s3:GetObject",
                "s3:PutObject"
            ],
            "Resource": "arn:aws:s3:::your-videos-bucket/*"
        },
        {
            "Effect": "Allow",
            "Action": [
                "dynamodb:GetItem",
                "dynamodb:PutItem",
                "dynamodb:UpdateItem"
            ],
            "Resource": "arn:aws:dynamodb:*:*:table/your-videos-table"
        }
    ]
}
```

## Deployment Checklist

- [ ] Add OpenCV Lambda Layer to function
- [ ] Update Lambda memory to 3008 MB
- [ ] Update Lambda timeout to 900 seconds
- [ ] Update ephemeral storage to 2048 MB
- [ ] Verify IAM permissions
- [ ] Deploy updated handler.py and background_processor.py
- [ ] Test with a sample green screen video

## Testing

### Test Event
```json
{
    "httpMethod": "POST",
    "path": "/videos/test-video-id/replace-background",
    "pathParameters": {
        "videoId": "test-video-id"
    },
    "body": "{\"bgColor\":[40,40,40],\"chromaKey\":null}"
}
```

## Troubleshooting

### "No module named 'cv2'"
- Verify Lambda Layer is attached
- Check layer ARN matches your Python runtime version

### "Task timed out after 15.00 seconds"
- Increase Lambda timeout to 900 seconds
- Check video file size (very large videos may need optimization)

### "No space left on device"
- Increase ephemeral storage to 2048 MB or higher
- Ensure temp files are cleaned up after processing

### Memory Issues
- Increase Lambda memory to 3008 MB
- Monitor CloudWatch Logs for memory usage patterns
