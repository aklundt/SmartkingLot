import os
import time
import requests
import cv2
import numpy as np
from ultralytics import YOLO
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).parent.parent / '.env')

STREAM_URL = os.getenv('STREAM_URL',   'http://localhost:8080/feed')
API_URL    = os.getenv('API_URL',      'http://localhost:5000/api/snapshot')
MODEL_PATH = os.getenv('MODEL_PATH',   'models/best_320x12n.pt')
CONFIDENCE = float(os.getenv('CONFIDENCE', 0.35))
INTERVAL   = int(os.getenv('INTERVAL', 60))

# resolve model path relative to project root
MODEL_PATH = Path(__file__).parent.parent / MODEL_PATH

model = YOLO(MODEL_PATH)
print(f'[detector] Model loaded: {MODEL_PATH}')
print(f'[detector] Stream:       {STREAM_URL}')
print(f'[detector] API:          {API_URL}')
print(f'[detector] Interval:     {INTERVAL}s')


def grab_frame():
    """Pull one JPEG frame from the MJPEG stream."""
    r = requests.get(STREAM_URL, stream=True, timeout=10)
    buf = b''
    for chunk in r.iter_content(chunk_size=1024):
        buf += chunk
        start = buf.find(b'\xff\xd8')
        end   = buf.find(b'\xff\xd9')
        if start != -1 and end != -1:
            return buf[start:end+2]
    raise RuntimeError('Could not find a complete JPEG frame in stream')


def detect(frame_bytes):
    """Run YOLO on raw JPEG bytes, return list of detection dicts."""
    frame = cv2.imdecode(np.frombuffer(frame_bytes, np.uint8), cv2.IMREAD_COLOR)
    h, w  = frame.shape[:2]

    results = model.predict(frame, conf=CONFIDENCE, verbose=False)

    detections = []
    for box in results[0].boxes:
        x1, y1, x2, y2 = map(int, box.xyxy[0])
        detections.append({
            'cx':         (x1 + x2) / 2,
            'cy':         (y1 + y2) / 2,
            'occupied':   int(box.cls[0]) == 0,
            'confidence': round(float(box.conf[0]), 3),
        })

    return detections, w, h


def post_snapshot(detections, img_width, img_height):
    payload = {
        'img_width':  img_width,
        'img_height': img_height,
        'detections': detections,
    }
    r = requests.post(API_URL, json=payload, timeout=10)
    r.raise_for_status()
    return r.json()


def run():
    while True:
        try:
            print(f'[detector] Grabbing frame...')
            frame_bytes = grab_frame()

            detections, w, h = detect(frame_bytes)
            print(f'[detector] {len(detections)} detections ({w}x{h})')

            if detections:
                result = post_snapshot(detections, w, h)
                print(f'[detector] Posted snapshot {result["snapshot_id"]} — '
                      f'{result["occupied"]} occupied / {result["open"]} open')
            else:
                print(f'[detector] No detections above threshold, skipping post')

        except Exception as e:
            print(f'[detector] Error: {e}')

        print(f'[detector] Sleeping {INTERVAL}s...')
        time.sleep(INTERVAL)


if __name__ == '__main__':
    run()
