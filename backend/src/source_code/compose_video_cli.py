"""
PNG Sequence to MP4 Compositor with CLI Arguments
Quick testing of different folders and background colors/images

Usage:
    python compose_video_cli.py output_smart
    python compose_video_cli.py output_smart --bg 40 40 40
    python compose_video_cli.py output_smart --bg-image background.jpg
    python compose_video_cli.py output_pro_v2 --bg 255 255 255 --fps 60
"""

import cv2
import numpy as np
import os
import sys
import argparse
from pathlib import Path


def find_png_files(folder):
    """Find all PNG files in folder, sorted by name."""
    png_files = sorted(Path(folder).glob('frame_*.png'))
    if not png_files:
        png_files = sorted(Path(folder).glob('*.png'))
    return [str(f) for f in png_files]


def resize_background(bg_image, target_width, target_height, mode='stretch'):
    """
    Resize/fit background image to target dimensions.

    Modes:
        stretch - Stretch to fit (may distort)
        fit     - Fit inside maintaining aspect ratio (letterbox)
        fill    - Fill frame maintaining aspect ratio (crop)
        tile    - Tile the image to fill frame
    """
    bg_h, bg_w = bg_image.shape[:2]

    if mode == 'stretch':
        # Simple resize (may distort)
        return cv2.resize(bg_image, (target_width, target_height))

    elif mode == 'fit':
        # Fit inside frame, maintain aspect ratio
        scale = min(target_width / bg_w, target_height / bg_h)
        new_w = int(bg_w * scale)
        new_h = int(bg_h * scale)

        resized = cv2.resize(bg_image, (new_w, new_h))

        # Create canvas and center the image
        canvas = np.zeros((target_height, target_width, 3), dtype=np.uint8)
        y_offset = (target_height - new_h) // 2
        x_offset = (target_width - new_w) // 2
        canvas[y_offset:y_offset+new_h, x_offset:x_offset+new_w] = resized

        return canvas

    elif mode == 'fill':
        # Fill frame, maintain aspect ratio (crop edges)
        scale = max(target_width / bg_w, target_height / bg_h)
        new_w = int(bg_w * scale)
        new_h = int(bg_h * scale)

        resized = cv2.resize(bg_image, (new_w, new_h))

        # Crop to target size (center crop)
        y_offset = (new_h - target_height) // 2
        x_offset = (new_w - target_width) // 2
        cropped = resized[y_offset:y_offset+target_height, x_offset:x_offset+target_width]

        return cropped

    elif mode == 'tile':
        # Tile the image to fill frame
        canvas = np.zeros((target_height, target_width, 3), dtype=np.uint8)

        for y in range(0, target_height, bg_h):
            for x in range(0, target_width, bg_w):
                # Calculate how much of the tile to copy
                h_copy = min(bg_h, target_height - y)
                w_copy = min(bg_w, target_width - x)

                canvas[y:y+h_copy, x:x+w_copy] = bg_image[:h_copy, :w_copy]

        return canvas

    return bg_image


def composite_frame(png_path, bg_color_bgr=None, bg_image=None):
    """
    Composite transparent PNG onto colored background or image.

    Args:
        png_path: Path to PNG with alpha channel
        bg_color_bgr: (B, G, R) tuple for solid color background
        bg_image: numpy array of background image (BGR format)

    Returns:
        Composited BGR image
    """
    frame = cv2.imread(png_path, cv2.IMREAD_UNCHANGED)

    if frame is None:
        return None

    if frame.shape[2] == 4:
        # Has alpha channel
        b, g, r, alpha = cv2.split(frame)
        alpha_norm = alpha.astype(np.float32) / 255.0

        # Create background
        height, width = frame.shape[:2]

        if bg_image is not None:
            # Use background image (already resized to match)
            background = bg_image.copy()
        else:
            # Use solid color
            background = np.full((height, width, 3), bg_color_bgr, dtype=np.uint8)

        # Alpha blend
        foreground = frame[:, :, :3].astype(np.float32)
        background = background.astype(np.float32)
        alpha_3ch = np.stack([alpha_norm, alpha_norm, alpha_norm], axis=2)
        composited = foreground * alpha_3ch + background * (1 - alpha_3ch)

        result = composited.astype(np.uint8)
    else:
        result = frame

    return result


def main():
    parser = argparse.ArgumentParser(
        description='Compose PNG sequence with alpha channel into MP4 with background',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Solid color backgrounds
  python compose_video_cli.py output_smart
  python compose_video_cli.py output_smart --bg 40 40 40
  python compose_video_cli.py output_smart --bg 255 255 255

  # Background images
  python compose_video_cli.py output_smart --bg-image beach.jpg
  python compose_video_cli.py output_smart --bg-image office.png --bg-mode fill
  python compose_video_cli.py output_smart --bg-image pattern.jpg --bg-mode tile

  # Advanced
  python compose_video_cli.py output_pro_v2 --bg 255 255 255 --fps 30
  python compose_video_cli.py output_diagnostic --bg-image sky.jpg --output final.mp4

Background color presets:
  Dark gray:    40 40 40
  Black:        0 0 0
  White:        255 255 255
  Slate blue:   50 70 90
  Dark red:     139 0 0
  Navy blue:    0 0 50

Background image modes:
  stretch - Stretch to fit (fastest, may distort)
  fit     - Fit inside maintaining aspect ratio (letterbox/pillarbox)
  fill    - Fill frame maintaining aspect ratio (crop edges)
  tile    - Tile the image to fill frame (good for patterns)
        """
    )

    parser.add_argument('input_folder', help='Folder containing PNG sequence')
    parser.add_argument('--bg', nargs=3, type=int, metavar=('R', 'G', 'B'),
                       default=[40, 40, 40],
                       help='Background color RGB (default: 40 40 40)')
    parser.add_argument('--bg-image', dest='bg_image', default=None,
                       help='Background image file (JPG, PNG, etc.) - overrides --bg')
    parser.add_argument('--bg-mode', dest='bg_mode',
                       choices=['stretch', 'fit', 'fill', 'tile'],
                       default='stretch',
                       help='How to fit background image (default: stretch)')
    parser.add_argument('--fps', type=float, default=30.0,
                       help='Frames per second (default: 30.0)')
    parser.add_argument('--output', '-o', default=None,
                       help='Output video filename (default: auto-generated)')
    parser.add_argument('--codec', default='mp4v',
                       choices=['mp4v', 'avc1', 'XVID'],
                       help='Video codec (default: mp4v)')

    args = parser.parse_args()

    input_folder = args.input_folder
    bg_color_rgb = tuple(args.bg)
    bg_color_bgr = (bg_color_rgb[2], bg_color_rgb[1], bg_color_rgb[0])
    fps = args.fps
    bg_image_path = args.bg_image
    bg_mode = args.bg_mode

    # Auto-generate output filename if not specified
    if args.output is None:
        output_video = f"{input_folder}_composed.mp4"
    else:
        output_video = args.output

    # Validate input folder
    if not os.path.exists(input_folder):
        print(f"Error: Input folder '{input_folder}' does not exist!")
        print(f"\nAvailable output folders:")
        for item in sorted(os.listdir('.')):
            if os.path.isdir(item) and item.startswith('output'):
                num_pngs = len(list(Path(item).glob('*.png')))
                print(f"  - {item} ({num_pngs} PNGs)")
        sys.exit(1)

    # Find PNG files
    png_files = find_png_files(input_folder)

    if not png_files:
        print(f"Error: No PNG files found in '{input_folder}'")
        sys.exit(1)

    # Load and validate background image if provided
    bg_image = None
    if bg_image_path:
        if not os.path.exists(bg_image_path):
            print(f"Error: Background image '{bg_image_path}' not found!")
            sys.exit(1)

        bg_image_raw = cv2.imread(bg_image_path)
        if bg_image_raw is None:
            print(f"Error: Could not load background image '{bg_image_path}'")
            sys.exit(1)

        print(f"Loaded background image: {bg_image_path}")
        print(f"  Original size: {bg_image_raw.shape[1]}x{bg_image_raw.shape[0]}")

    print(f"╔═══════════════════════════════════════════╗")
    print(f"║   PNG Sequence to MP4 Compositor         ║")
    print(f"╚═══════════════════════════════════════════╝")
    print(f"\nInput:      {input_folder}")
    print(f"Frames:     {len(png_files)} PNG files")

    if bg_image_path:
        print(f"Background: Image '{bg_image_path}' (mode: {bg_mode})")
    else:
        print(f"Background: RGB{bg_color_rgb}")

    print(f"FPS:        {fps}")
    print(f"Codec:      {args.codec}")
    print(f"Output:     {output_video}\n")

    # Read first frame to get dimensions
    first_frame_raw = cv2.imread(png_files[0], cv2.IMREAD_UNCHANGED)
    if first_frame_raw is None:
        print("Error: Could not read first frame")
        sys.exit(1)

    target_height, target_width = first_frame_raw.shape[:2]

    # Resize/process background image if provided
    if bg_image_path:
        bg_image = resize_background(bg_image_raw, target_width, target_height, bg_mode)
        print(f"  Resized to: {target_width}x{target_height} ({bg_mode} mode)")

    # Composite first frame for validation
    first_frame = composite_frame(png_files[0], bg_color_bgr, bg_image)
    if first_frame is None:
        print("Error: Could not composite first frame")
        sys.exit(1)

    height, width = first_frame.shape[:2]
    print(f"Resolution: {width}x{height}")
    print(f"Duration:   ~{len(png_files) / fps:.2f} seconds\n")

    # Initialize video writer
    fourcc = cv2.VideoWriter_fourcc(*args.codec)
    out = cv2.VideoWriter(output_video, fourcc, fps, (width, height))

    if not out.isOpened():
        print(f"Error: Could not open video writer with codec '{args.codec}'")
        print("Try: python compose_video_cli.py <folder> --codec mp4v")
        sys.exit(1)

    print("Compositing...")

    # Process all frames
    frame_count = 0
    for i, png_path in enumerate(png_files):
        composited = composite_frame(png_path, bg_color_bgr, bg_image)

        if composited is None:
            print(f"Warning: Skipping {png_path}")
            continue

        out.write(composited)
        frame_count += 1

        # Progress bar
        progress = (i + 1) / len(png_files)
        bar_length = 40
        filled = int(bar_length * progress)
        bar = '█' * filled + '░' * (bar_length - filled)
        print(f'\r[{bar}] {progress*100:.1f}% ({i+1}/{len(png_files)})', end='', flush=True)

    print()  # New line after progress bar

    # Cleanup
    out.release()

    file_size_mb = os.path.getsize(output_video) / (1024*1024)

    print(f"\n✓ Success!")
    print(f"  Created:   {output_video}")
    print(f"  Frames:    {frame_count}")
    print(f"  Duration:  {frame_count / fps:.2f}s")
    print(f"  Size:      {file_size_mb:.2f} MB")
    print(f"\nPlay with: vlc {output_video}")
    print(f"           open {output_video}")


if __name__ == "__main__":
    main()
