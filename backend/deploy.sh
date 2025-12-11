#!/bin/bash

# Load environment variables from .env file
if [ -f .env ]; then
    echo "Loading environment variables from .env file..."
    export $(cat .env | grep -v '^#' | xargs)
else
    echo "Error: .env file not found!"
    exit 1
fi

# Set default region if not specified
export AWS_DEFAULT_REGION=${AWS_REGION:-us-east-1}

echo "AWS Region: $AWS_DEFAULT_REGION"
echo "Building SAM application..."

# Build the SAM application using container (required when local Python version differs)
sam build --use-container

if [ $? -ne 0 ]; then
    echo "Error: SAM build failed!"
    exit 1
fi

echo "Deploying SAM application..."

# Deploy the SAM application
sam deploy \
    --stack-name vid-maker-backend \
    --resolve-s3 \
    --parameter-overrides \
        Environment=${ENVIRONMENT:-prod} \
        GeminiApiKey=$GEMINI_API_KEY \
    --capabilities CAPABILITY_IAM

if [ $? -eq 0 ]; then
    echo "Deployment successful!"
    echo ""
    echo "Getting API Gateway URL..."
    sam list stack-outputs --stack-name vid-maker-backend
else
    echo "Error: Deployment failed!"
    exit 1
fi