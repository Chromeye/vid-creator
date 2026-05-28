#!/usr/bin/env python3
"""
Build a sam local invoke event JSON from a raw base64 image file.

Usage (run from anywhere):
    python3 build-event.py                     # Veo 3.1 Fast (default)
    python3 build-event.py kling               # Kling 3.0 Standard
    python3 build-event.py gemini-veo-31       # Veo 3.1

Output is written to backend/events/generate-local.json
"""
import json
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
EVENTS_DIR = os.path.join(SCRIPT_DIR, '../../events')
IMAGE_FILE = os.path.join(SCRIPT_DIR, 'base64.txt')

MODEL_ARG = sys.argv[1] if len(sys.argv) > 1 else 'gemini-veo-31-fast'

MODEL_MAP = {
    'kling':              'kling-v3-image-to-video',
    'gemini-veo-31-fast': 'gemini-veo-31-fast',
    'gemini-veo-31':      'gemini-veo-31',
}
model = MODEL_MAP.get(MODEL_ARG, MODEL_ARG)

if not os.path.exists(IMAGE_FILE):
    print(f"Error: base64.txt not found at {IMAGE_FILE}")
    sys.exit(1)

with open(IMAGE_FILE) as f:
    image_b64 = f.read().strip()

event = {
    "httpMethod": "POST",
    "path": "/generate",
    "headers": {"content-type": "application/json"},
    "body": json.dumps({
        "prompt": "A girl looks suspiciously turning her eyes from left to right. At one point her expression changes to happiness and joy. Her favourite team in the World Cup have won! She throws the baguette in the air in celebration and jumps up and down with excitement.",
        "model": model,
        "image": {"start": image_b64}
    }),
    "isBase64Encoded": False
}

out = os.path.join(EVENTS_DIR, 'generate-local.json')
with open(out, 'w') as f:
    json.dump(event, f, indent=2)

print(f"Written: {out}")
print(f"Model:   {model}")
print(f"\nRun from backend/:")
print(f"  sam local invoke VideoGeneratorFunction --event events/generate-local.json --env-vars env.json")
