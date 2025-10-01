# Gemini Veo 3 Video Generator UI

A React application for generating videos using Google's Gemini Veo 3 model via AWS Lambda.

## Setup

1. Install dependencies:
```bash
npm install
```

2. Create a `.env` file based on `.env.example`:
```bash
cp .env.example .env
```

3. Update the `.env` file with your Lambda function URL:
```
VITE_API_URL=https://your-lambda-function-url.amazonaws.com
```

## Development

Run the development server:
```bash
npm run dev
```

The app will be available at `http://localhost:5173`

## Building for Production

Build the app:
```bash
npm run build
```

The build output will be in the `dist` folder, ready to deploy to AWS Amplify.

## Deploying to AWS Amplify

1. Push your code to a Git repository (GitHub, GitLab, etc.)
2. In AWS Amplify Console, connect your repository
3. Configure build settings (Amplify will auto-detect Vite settings)
4. Set environment variables in Amplify:
   - `VITE_API_URL`: Your Lambda function URL
5. Deploy!

## Features

- Upload images (1280x720, JPG/PNG)
- Submit text prompts for video generation
- View list of generated videos
- Monitor video processing status
- Download completed videos from S3
