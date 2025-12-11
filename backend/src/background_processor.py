"""
Background Replacement Processor for Lambda
Adapts smart_chroma_key.py and compose_video_cli.py for Lambda execution
"""

import cv2
import numpy as np
import os
import boto3
import tempfile
import shutil
from pathlib import Path
import requests

s3_client = boto3.client('s3')

# Default chroma key color (green screen)
# Override from frontend api.js if testing different values
DEFAULT_CHROMA_KEY_RGB = (0, 171, 69)

# Chroma key parameters (from smart_chroma_key.py)
SIMILARITY_THRESHOLD = 0.25
SMOOTHNESS = 0.12
USE_SMART_KEYING = True
GREEN_HUE_TOLERANCE = 18
MIN_GREEN_SATURATION = 0.15
SPILL_SUPPRESSION = 0.65
EDGE_BLUR_AMOUNT = 2
ENABLE_EDGE_DILATION = False
DILATION_AMOUNT = 1


def download_video_from_url(video_url, local_path):
    """Download video from URL (S3 presigned URL) to local path"""
    print(f"Downloading video from {video_url[:50]}...")
    response = requests.get(video_url, stream=True)
    response.raise_for_status()
    
    with open(local_path, 'wb') as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)
    
    print(f"Downloaded to {local_path}")
    return local_path


def smart_green_detection(image, key_color_bgr_norm, green_hue_center):
    """Intelligent green screen detection (from smart_chroma_key.py)"""
    img_norm = image.astype(np.float32) / 255.0
    
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    hue = hsv[:, :, 0].astype(np.float32)
    saturation = hsv[:, :, 1].astype(np.float32) / 255.0
    value = hsv[:, :, 2].astype(np.float32) / 255.0
    
    # RGB color distance
    diff = img_norm - key_color_bgr_norm
    color_distance = np.sqrt(np.sum(diff ** 2, axis=2))
    color_distance = color_distance / np.sqrt(3.0)
    
    if USE_SMART_KEYING:
        hue_diff = np.abs(hue - green_hue_center)
        hue_diff = np.minimum(hue_diff, 180 - hue_diff)
        hue_distance = hue_diff / 90.0
        
        is_green_hue = hue_diff < GREEN_HUE_TOLERANCE
        is_saturated = saturation > MIN_GREEN_SATURATION
        green_candidate = is_green_hue & is_saturated
        
        final_distance = np.where(green_candidate, color_distance, 1.0)
        final_distance = np.where(hue_distance > 0.3, 1.0, final_distance)
    else:
        final_distance = color_distance
    
    return final_distance


def create_alpha_from_distance(distance, threshold, smoothness):
    """Convert distance map to alpha channel"""
    lower = threshold
    upper = threshold + smoothness
    alpha = np.clip((distance - lower) / (upper - lower), 0, 1)
    return (alpha * 255).astype(np.uint8)


def suppress_green_spill(image, alpha, strength=0.5):
    """Remove green color cast from edges"""
    if strength <= 0:
        return image
    
    result = image.copy().astype(np.float32)
    b, g, r = cv2.split(result / 255.0)
    
    max_rb = np.maximum(r, b)
    spill_amount = np.maximum(0, g - max_rb)
    
    alpha_norm = alpha.astype(np.float32) / 255.0
    suppression_mask = spill_amount * strength * (1.0 - alpha_norm * 0.5)
    
    g = g - suppression_mask
    
    result = cv2.merge([b, g, r]) * 255.0
    return np.clip(result, 0, 255).astype(np.uint8)


def refine_edge_detail(alpha):
    """Edge refinement for smooth anti-aliased edges"""
    kernel_small = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    cleaned = cv2.morphologyEx(alpha, cv2.MORPH_OPEN, kernel_small, iterations=1)
    cleaned = cv2.morphologyEx(cleaned, cv2.MORPH_CLOSE, kernel_small, iterations=1)
    
    if ENABLE_EDGE_DILATION and DILATION_AMOUNT > 0:
        kernel_dilate = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        cleaned = cv2.dilate(cleaned, kernel_dilate, iterations=DILATION_AMOUNT)
    
    if EDGE_BLUR_AMOUNT > 0:
        kernel_size = EDGE_BLUR_AMOUNT * 2 + 1
        cleaned = cv2.GaussianBlur(cleaned, (kernel_size, kernel_size), 0)
    
    return cleaned


def chroma_key_frame(frame, key_color_bgr_norm, green_hue_center):
    """Main keying function for a single frame"""
    distance = smart_green_detection(frame, key_color_bgr_norm, green_hue_center)
    alpha = create_alpha_from_distance(distance, SIMILARITY_THRESHOLD, SMOOTHNESS)
    alpha = refine_edge_detail(alpha)
    
    if SPILL_SUPPRESSION > 0:
        frame = suppress_green_spill(frame, alpha, SPILL_SUPPRESSION)
    
    b, g, r = cv2.split(frame)
    rgba = cv2.merge([b, g, r, alpha])
    
    return rgba


def extract_chroma_key(video_path, output_folder, chroma_key_rgb=None):
    """
    Extract chroma key from video and save as PNG sequence
    Returns: (frame_count, fps, width, height)
    """
    if chroma_key_rgb is None:
        chroma_key_rgb = DEFAULT_CHROMA_KEY_RGB
    
    os.makedirs(output_folder, exist_ok=True)
    
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise ValueError(f"Cannot open video: {video_path}")
    
    fps = cap.get(cv2.CAP_PROP_FPS)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    
    # Calculate green hue from key color
    key_color_bgr = np.array([[[chroma_key_rgb[2], chroma_key_rgb[1], chroma_key_rgb[0]]]], dtype=np.uint8)
    key_color_hsv = cv2.cvtColor(key_color_bgr, cv2.COLOR_BGR2HSV)
    green_hue_center = int(key_color_hsv[0, 0, 0])
    
    key_color_bgr_norm = np.array([chroma_key_rgb[2], chroma_key_rgb[1], chroma_key_rgb[0]], dtype=np.float32) / 255.0
    
    print(f"Processing: {width}x{height} @ {fps} FPS")
    print(f"Key Color: RGB{chroma_key_rgb} → Hue: {green_hue_center}")
    
    frame_count = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        
        result = chroma_key_frame(frame, key_color_bgr_norm, green_hue_center)
        
        frame_count += 1
        filename = os.path.join(output_folder, f'frame_{frame_count:05d}.png')
        cv2.imwrite(filename, result)
        
        if frame_count % 30 == 0:
            print(f"  Processed: {frame_count} frames")
    
    cap.release()
    print(f"Extracted {frame_count} frames to {output_folder}")
    
    return frame_count, fps, width, height


def resize_background(bg_image, target_width, target_height, mode='stretch'):
    """Resize/fit background image to target dimensions"""
    bg_h, bg_w = bg_image.shape[:2]
    
    if mode == 'stretch':
        return cv2.resize(bg_image, (target_width, target_height))
    elif mode == 'fill':
        scale = max(target_width / bg_w, target_height / bg_h)
        new_w = int(bg_w * scale)
        new_h = int(bg_h * scale)
        resized = cv2.resize(bg_image, (new_w, new_h))
        y_offset = (new_h - target_height) // 2
        x_offset = (new_w - target_width) // 2
        cropped = resized[y_offset:y_offset+target_height, x_offset:x_offset+target_width]
        return cropped
    
    return bg_image


def composite_frame(png_path, bg_color_bgr=None, bg_image=None):
    """Composite transparent PNG onto colored background or image"""
    frame = cv2.imread(png_path, cv2.IMREAD_UNCHANGED)
    
    if frame is None:
        return None
    
    if frame.shape[2] == 4:
        b, g, r, alpha = cv2.split(frame)
        alpha_norm = alpha.astype(np.float32) / 255.0
        
        height, width = frame.shape[:2]
        
        if bg_image is not None:
            background = bg_image.copy()
        else:
            background = np.full((height, width, 3), bg_color_bgr, dtype=np.uint8)
        
        foreground = frame[:, :, :3].astype(np.float32)
        background = background.astype(np.float32)
        alpha_3ch = np.stack([alpha_norm, alpha_norm, alpha_norm], axis=2)
        composited = foreground * alpha_3ch + background * (1 - alpha_3ch)
        
        result = composited.astype(np.uint8)
    else:
        result = frame
    
    return result


def compose_video(png_folder, output_path, bg_color_rgb=None, bg_image_path=None, fps=30.0, original_video_path=None):
    """
    Compose PNG sequence with background into final video
    bg_image_path takes precedence over bg_color_rgb
    original_video_path: path to original video for audio extraction
    """
    # Find PNG files
    png_files = sorted(Path(png_folder).glob('frame_*.png'))
    if not png_files:
        raise ValueError(f"No PNG files found in {png_folder}")
    
    png_files = [str(f) for f in png_files]
    
    # Convert RGB to BGR for OpenCV
    bg_color_bgr = None
    if bg_color_rgb:
        bg_color_bgr = (bg_color_rgb[2], bg_color_rgb[1], bg_color_rgb[0])
    
    # Load background image if provided
    bg_image = None
    if bg_image_path and os.path.exists(bg_image_path):
        bg_image_raw = cv2.imread(bg_image_path)
        if bg_image_raw is None:
            raise ValueError(f"Could not load background image: {bg_image_path}")
        print(f"Loaded background image: {bg_image_path}")
    
    # Get dimensions from first frame
    first_frame_raw = cv2.imread(png_files[0], cv2.IMREAD_UNCHANGED)
    if first_frame_raw is None:
        raise ValueError("Could not read first frame")
    
    target_height, target_width = first_frame_raw.shape[:2]
    
    # Resize background image if provided
    if bg_image_path and bg_image_raw is not None:
        bg_image = resize_background(bg_image_raw, target_width, target_height, 'fill')
        print(f"Resized background to {target_width}x{target_height}")
    
    # Composite first frame for validation
    first_frame = composite_frame(png_files[0], bg_color_bgr, bg_image)
    if first_frame is None:
        raise ValueError("Could not composite first frame")
    
    height, width = first_frame.shape[:2]
    print(f"Compositing {len(png_files)} frames at {width}x{height}, {fps} FPS")
    
    # Try H.264 codecs first (custom OpenCV should support these)
    # Then fallback to mp4v if H.264 not available
    codecs_to_try = [
        ('avc1', 'H.264 (avc1)'),
        ('h264', 'H.264 (h264)'),
        ('H264', 'H.264 (H264)'),
        ('X264', 'H.264 (X264)'),
        ('mp4v', 'MPEG-4 (mp4v)')
    ]
    
    out = None
    used_codec = None
    
    for fourcc_str, codec_name in codecs_to_try:
        try:
            fourcc = cv2.VideoWriter_fourcc(*fourcc_str)
            test_out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))
            
            if test_out.isOpened():
                out = test_out
                used_codec = codec_name
                print(f"✓ Using codec: {codec_name}")
                break
            else:
                test_out.release()
        except Exception as e:
            print(f"  Codec {fourcc_str} failed: {e}")
            continue
    
    if out is None or not out.isOpened():
        raise ValueError("Could not open video writer with any supported codec")
    
    # Process all frames
    frame_count = 0
    for i, png_path in enumerate(png_files):
        composited = composite_frame(png_path, bg_color_bgr, bg_image)
        
        if composited is None:
            print(f"Warning: Skipping {png_path}")
            continue
        
        out.write(composited)
        frame_count += 1
        
        if (i + 1) % 30 == 0:
            print(f"  Composited: {i + 1}/{len(png_files)} frames")
    
    out.release()
    
    # Note: Audio is not preserved with this approach
    # To add audio support, FFmpeg binaries would need to be included in the layer
    if original_video_path:
        print("Note: Audio from original video is not preserved (FFmpeg not available)")
    
    file_size_mb = os.path.getsize(output_path) / (1024*1024)
    print(f"Created video: {output_path} ({file_size_mb:.2f} MB, {frame_count} frames, codec: {used_codec})")
    
    return frame_count


def process_background_replacement(video_path, bg_color_rgb=None, bg_image_base64=None, chroma_key_rgb=None):
    """
    Main processing function for background replacement
    
    Args:
        video_path: Local path to video file
        bg_color_rgb: (R, G, B) tuple for solid color background
        bg_image_base64: Base64 encoded background image
        chroma_key_rgb: (R, G, B) tuple for chroma key color (default: green screen)
    
    Returns:
        Path to final processed video
    """
    # Create temp directories
    temp_dir = tempfile.mkdtemp(prefix='bg_replace_')
    png_folder = os.path.join(temp_dir, 'frames')
    
    try:
        # Extract chroma key to PNG sequence
        print("Step 1: Extracting chroma key...")
        frame_count, fps, width, height = extract_chroma_key(video_path, png_folder, chroma_key_rgb)
        
        # Prepare background image if provided
        bg_image_path = None
        if bg_image_base64:
            print("Step 2: Processing background image...")
            import base64
            
            # Remove data URL prefix if present
            if bg_image_base64.startswith('data:'):
                bg_image_base64 = bg_image_base64.split(',', 1)[1]
            
            # Decode and save
            bg_image_data = base64.b64decode(bg_image_base64)
            bg_image_path = os.path.join(temp_dir, 'background.jpg')
            with open(bg_image_path, 'wb') as f:
                f.write(bg_image_data)
        
        # Compose final video
        print("Step 3: Compositing final video...")
        output_path = os.path.join(temp_dir, 'final.mp4')
        compose_video(png_folder, output_path, bg_color_rgb, bg_image_path, fps, original_video_path=video_path)
        
        print("Background replacement complete!")
        return output_path
        
    except Exception as e:
        # Clean up on error
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise e
