"""
Smart Chroma Key - Uses intelligent color discrimination
Distinguishes between green screen and dark/blue clothing
"""

import cv2
import numpy as np
import sys
import os

# --- CONFIGURATION ---
VIDEO_FILE = 'dl.mp4'
OUTPUT_FOLDER = 'output_smart'

# Target green screen color (RGB)
KEY_COLOR_RGB = (0, 171, 69)

# Core keying parameters
SIMILARITY_THRESHOLD = 0.25    # Base threshold
SMOOTHNESS = 0.12              # Edge softness # 12

# Smart discrimination settings
USE_SMART_KEYING = True        # Enable intelligent green detection
GREEN_HUE_CENTER = 72          # Hue value for green (will be auto-calculated)
GREEN_HUE_TOLERANCE = 20       # How much hue variation to accept # 18
MIN_GREEN_SATURATION = 0.15    # Green screen must be at least this saturated

# Spill removal
SPILL_SUPPRESSION = 0.60        # Strength of green spill removal # 0.65

# Edge refinement
EDGE_BLUR_AMOUNT = 2           # Increased for smoother edges
ENABLE_EDGE_DILATION = False    # Recover edge detail before blurring
DILATION_AMOUNT = 1            # Pixels to dilate before blur

# --- SETUP ---
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

cap = cv2.VideoCapture(VIDEO_FILE)
if not cap.isOpened():
    print(f"Error: Cannot open {VIDEO_FILE}")
    sys.exit(1)

fps = cap.get(cv2.CAP_PROP_FPS)
width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

# Calculate the actual green hue from the key color
key_color_bgr = np.array(
    [[[KEY_COLOR_RGB[2], KEY_COLOR_RGB[1], KEY_COLOR_RGB[0]]]], dtype=np.uint8)
key_color_hsv = cv2.cvtColor(key_color_bgr, cv2.COLOR_BGR2HSV)
GREEN_HUE_CENTER = int(key_color_hsv[0, 0, 0])

print(f"Processing: {width}x{height} @ {fps} FPS")
print(f"Key Color: RGB{KEY_COLOR_RGB} → Hue: {GREEN_HUE_CENTER}")
print(f"Smart Keying: {'Enabled' if USE_SMART_KEYING else 'Disabled'}")
print(f"Output: {OUTPUT_FOLDER}/\n")

frame_count = 0

key_color_bgr_norm = np.array(
    [KEY_COLOR_RGB[2], KEY_COLOR_RGB[1], KEY_COLOR_RGB[0]], dtype=np.float32) / 255.0


def smart_green_detection(image):
    """
    Intelligent green screen detection that WON'T confuse:
    - Dark blue jeans with green
    - Dark clothing with green
    - Skin tones with green

    Uses BOTH color distance AND hue discrimination.
    """
    # Normalize image
    img_norm = image.astype(np.float32) / 255.0

    # Convert to HSV for hue analysis
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    hue = hsv[:, :, 0].astype(np.float32)
    saturation = hsv[:, :, 1].astype(np.float32) / 255.0
    value = hsv[:, :, 2].astype(np.float32) / 255.0

    # STEP 1: Compute RGB color distance
    diff = img_norm - key_color_bgr_norm
    color_distance = np.sqrt(np.sum(diff ** 2, axis=2))
    color_distance = color_distance / np.sqrt(3.0)

    if USE_SMART_KEYING:
        # STEP 2: Compute hue distance (circular distance for hue)
        hue_diff = np.abs(hue - GREEN_HUE_CENTER)
        # Handle wraparound (hue is circular: 0-180 in OpenCV)
        hue_diff = np.minimum(hue_diff, 180 - hue_diff)

        # Normalize hue difference (0 = exact match, 1 = opposite color)
        hue_distance = hue_diff / 90.0  # 90 degrees = opposite on color wheel

        # STEP 3: Create hue-based mask
        # Only consider pixels within the green hue range
        is_green_hue = hue_diff < GREEN_HUE_TOLERANCE

        # STEP 4: Check saturation
        # Green screen should be reasonably saturated
        is_saturated = saturation > MIN_GREEN_SATURATION

        # STEP 5: Combine criteria
        # A pixel is green screen if:
        # - It has green hue AND is saturated AND has similar color distance
        # OR it's very close in color distance (fallback for edge cases)

        # Create a weighted distance map
        # If pixel is NOT green hue or NOT saturated, push distance to 1.0 (keep it)
        green_candidate = is_green_hue & is_saturated

        # For non-green candidates, force distance to 1.0 (fully opaque)
        final_distance = np.where(green_candidate, color_distance, 1.0)

        # Also use hue distance to refine: if hue is way off, keep the pixel
        final_distance = np.where(hue_distance > 0.3, 1.0, final_distance)
    else:
        # Standard distance-based keying
        final_distance = color_distance

    return final_distance


def create_alpha_from_distance(distance, threshold, smoothness):
    """Convert distance map to alpha channel with smooth transitions."""
    lower = threshold
    upper = threshold + smoothness
    alpha = np.clip((distance - lower) / (upper - lower), 0, 1)
    return (alpha * 255).astype(np.uint8)


def suppress_green_spill(image, alpha, strength=0.5):
    """Remove green color cast from edges."""
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
    """
    Advanced edge refinement for smooth, anti-aliased edges.
    Multi-stage process to remove jaggedness while preserving detail.
    """
    # Stage 1: Remove small noise/holes
    kernel_small = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    cleaned = cv2.morphologyEx(
        alpha, cv2.MORPH_OPEN, kernel_small, iterations=1)
    cleaned = cv2.morphologyEx(
        cleaned, cv2.MORPH_CLOSE, kernel_small, iterations=1)

    # Stage 2: Optional edge dilation to recover detail lost in keying
    # This helps smooth out the transition zone
    if ENABLE_EDGE_DILATION and DILATION_AMOUNT > 0:
        kernel_dilate = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        cleaned = cv2.dilate(cleaned, kernel_dilate,
                             iterations=DILATION_AMOUNT)

    # Stage 3: Gaussian blur for smooth anti-aliased edges
    # Larger kernel = smoother edges but may lose fine detail
    if EDGE_BLUR_AMOUNT > 0:
        kernel_size = EDGE_BLUR_AMOUNT * 2 + 1
        cleaned = cv2.GaussianBlur(cleaned, (kernel_size, kernel_size), 0)

    # Stage 4: Optional bilateral filter for edge-preserving smoothing
    # Smooths flat areas while keeping sharp transitions
    # Uncomment if you need even better edge quality:
    # cleaned = cv2.bilateralFilter(cleaned, 5, 50, 50)

    return cleaned


def chroma_key_frame(frame):
    """Main keying function."""
    # Detect green screen using smart algorithm
    distance = smart_green_detection(frame)

    # Generate alpha matte
    alpha = create_alpha_from_distance(
        distance, SIMILARITY_THRESHOLD, SMOOTHNESS)

    # Refine edges
    alpha = refine_edge_detail(alpha)

    # Suppress green spill
    if SPILL_SUPPRESSION > 0:
        frame = suppress_green_spill(frame, alpha, SPILL_SUPPRESSION)

    # Create BGRA output
    b, g, r = cv2.split(frame)
    rgba = cv2.merge([b, g, r, alpha])

    return rgba


# --- MAIN LOOP ---
print("Processing frames...\n")

while True:
    ret, frame = cap.read()
    if not ret:
        break

    result = chroma_key_frame(frame)

    frame_count += 1
    filename = os.path.join(OUTPUT_FOLDER, f'frame_{frame_count:05d}.png')
    cv2.imwrite(filename, result)

    if frame_count % 30 == 0:
        print(f"  Processed: {frame_count} frames")

cap.release()

print(f"\n✓ Done! {frame_count} frames saved to {OUTPUT_FOLDER}/")
print("\n--- Fine-Tuning Guide ---")
print("\nIf jeans/dark clothing are transparent:")
print("  → Increase MIN_GREEN_SATURATION to 0.20-0.30")
print("  → Increase GREEN_HUE_TOLERANCE to 20-25")
print("\nIf green screen not fully removed:")
print("  → Decrease MIN_GREEN_SATURATION to 0.10-0.12")
print("  → Increase GREEN_HUE_TOLERANCE to 25-30")
print("  → Decrease SIMILARITY_THRESHOLD to 0.20-0.22")
print("\nFor smoother edges (less jagged):")
print("  → Increase EDGE_BLUR_AMOUNT to 6-8 (currently: {})".format(EDGE_BLUR_AMOUNT))
print("  → Increase DILATION_AMOUNT to 2-3 (currently: {})".format(DILATION_AMOUNT))
print("  → Increase SMOOTHNESS to 0.15-0.18 (currently: {})".format(SMOOTHNESS))
print("  → Enable bilateral filter (uncomment line 179 in code)")
print("\nFor sharper edges (more detail):")
print("  → Decrease EDGE_BLUR_AMOUNT to 2-3")
print("  → Set ENABLE_EDGE_DILATION to False")
print("  → Decrease SMOOTHNESS to 0.08-0.10")
