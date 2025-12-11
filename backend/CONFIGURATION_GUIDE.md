# Background Replacement - Configuration Guide

## Chroma Key (Green Screen) Configuration

### Default Value

The default green screen color `RGB(0, 171, 69)` is defined in **one place**:

**Backend Module** (`background_processor.py` line 18):
```python
DEFAULT_CHROMA_KEY_RGB = (0, 171, 69)
```

### How to Override for Testing

To test with a different chroma key value, edit `api.js`:

```javascript
// In frontend/src/services/api.js

// Default (uses backend value)
export const CHROMA_KEY_RGB = null;

// Override for testing (e.g., pure green)
export const CHROMA_KEY_RGB = [0, 255, 0];

// Override for testing (e.g., blue screen)
export const CHROMA_KEY_RGB = [0, 0, 255];
```

**That's it!** No environment variables or template changes needed.

## Async Processing & Polling

### How It Works

The background replacement now uses **async processing** similar to video generation:

1. **User submits request** → API returns immediately with `status: 'processing'`
2. **Main Lambda** creates DB entry and invokes **BackgroundProcessorFunction** asynchronously
3. **BackgroundProcessorFunction** processes video (may take 5-15 minutes)
4. **Frontend polls** via existing video list refresh to check status

### Polling Implementation

**Already Built-In!** The existing `VideoList` component automatically polls:

```javascript
// VideoList.jsx already has refresh functionality
const fetchVideos = async () => {
    const data = await getVideos();
    setVideos(data.videos || []);
};

// User can manually refresh or set up auto-refresh
```

### Status Flow

```
User clicks "Submit"
    ↓
Frontend calls API
    ↓
API returns: { videoId: "new-id", status: "processing" }
    ↓
User sees: "Background replacement started! Check your video list."
    ↓
User refreshes video list (manually or auto)
    ↓
Status updates: processing → completed (or failed)
    ↓
Video appears with new background
```

### Auto-Polling (Optional Enhancement)

If you want automatic polling, add this to `VideoList.jsx`:

```javascript
useEffect(() => {
    // Auto-refresh every 10 seconds if there are processing videos
    const hasProcessing = videos.some(v => v.status === 'processing');
    
    if (hasProcessing) {
        const interval = setInterval(fetchVideos, 10000);
        return () => clearInterval(interval);
    }
}, [videos]);
```

## Architecture Diagram

```
┌─────────────┐
│  Frontend   │
└──────┬──────┘
       │ POST /videos/{id}/replace-background
       │ { bgColor, bgImage, chromaKey }
       ↓
┌──────────────────────┐
│ VideoGeneratorFunction│ (Main Handler)
│  - Validates input    │
│  - Creates DB entry   │
│  - Returns immediately│
└──────┬───────────────┘
       │ Async invoke
       ↓
┌─────────────────────────────┐
│ BackgroundProcessorFunction │ (Async Worker)
│  - Downloads video          │
│  - Extracts chroma key      │
│  - Composes with background │
│  - Uploads to S3            │
│  - Updates DB status        │
└─────────────────────────────┘
       │
       ↓
┌──────────────┐
│  DynamoDB    │ status: processing → completed
└──────────────┘
       │
       ↓ (User polls)
┌─────────────┐
│  Frontend   │ Refreshes video list
└─────────────┘
```

## Environment Variables Summary

### VideoGeneratorFunction (Main Handler)
- `VIDEOS_BUCKET` - S3 bucket for videos
- `VIDEOS_TABLE` - DynamoDB table
- `GEMINI_API_KEY` - Google Gemini API key
- `POLLER_FUNCTION_NAME` - Video poller Lambda
- `BACKGROUND_PROCESSOR_FUNCTION_NAME` - Background processor Lambda
- `CHROMA_KEY_RGB` - Default chroma key (e.g., '0,171,69')

### BackgroundProcessorFunction (Async Worker)
- `VIDEOS_BUCKET` - S3 bucket for videos
- `VIDEOS_TABLE` - DynamoDB table
- `CHROMA_KEY_DEFAULT_RGB` - Default chroma key (e.g., '0,171,69')

## Deployment Checklist

- [ ] Add OpenCV Lambda Layer to BackgroundProcessorFunction
- [ ] Update Lambda memory to 3008 MB (already in template)
- [ ] Update Lambda timeout to 900 seconds (already in template)
- [ ] Update ephemeral storage to 2048 MB (already in template)
- [ ] Set CHROMA_KEY_RGB environment variable if different from default
- [ ] Deploy updated template.yaml
- [ ] Test with a green screen video
