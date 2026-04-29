import os
import time
import requests
import cv2
import numpy as np
from ultralytics import YOLO
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).parent.parent / '.env')

STREAM_URL = os.getenv('STREAM_URL', 'http://localhost:8080/feed')
API_URL    = os.getenv('API_URL',    'http://localhost:5000/api/snapshot')
CONFIDENCE = float(os.getenv('CONFIDENCE', 0.35))
INTERVAL   = int(os.getenv('INTERVAL', 60))           # baseline scan interval
CHECK_EVERY      = int(os.getenv('CHECK_EVERY', 3))   # quick-check cadence (seconds)
CHANGE_THRESHOLD = float(os.getenv('CHANGE_THRESHOLD', 8.0))  # mean abs diff in grayscale 0-255

MODEL_PATH = Path(__file__).parent.parent / 'models' / 'best_320x12n.pt'

model = YOLO(MODEL_PATH)
print(f'[detector] Model:        {MODEL_PATH}')
print(f'[detector] Stream:       {STREAM_URL}')
print(f'[detector] API:          {API_URL}')
print(f'[detector] Full scan:    every {INTERVAL}s')
print(f'[detector] Quick check:  every {CHECK_EVERY}s (threshold {CHANGE_THRESHOLD})')


def grab_frame():
    r = requests.get(STREAM_URL, stream=True, timeout=10)
    buf = b''
    for chunk in r.iter_content(chunk_size=1024):
        buf += chunk
        start = buf.find(b'\xff\xd8')
        end   = buf.find(b'\xff\xd9')
        if start != -1 and end != -1:
            return buf[start:end+2]
    raise RuntimeError('Could not find a complete JPEG frame in stream')


def fingerprint(frame_bytes):
    """
    Cheap perceptual fingerprint: decode, downscale to 32x32 grayscale.
    Comparing two of these with mean absolute difference is robust against
    JPEG noise and minor lighting flicker but sensitive to actual movement.
    """
    img = cv2.imdecode(np.frombuffer(frame_bytes, np.uint8), cv2.IMREAD_GRAYSCALE)
    return cv2.resize(img, (32, 32), interpolation=cv2.INTER_AREA)


def detect(frame_bytes):
    frame = cv2.imdecode(np.frombuffer(frame_bytes, np.uint8), cv2.IMREAD_COLOR)
    h, w  = frame.shape[:2]
    results = model.predict(frame, conf=CONFIDENCE, verbose=False)

    detections = []
    for box in results[0].boxes:
        x1, y1, x2, y2 = map(int, box.xyxy[0])
        detections.append({
            'cx':         (x1 + x2) / 2,
            'cy':         (y1 + y2) / 2,
            'w':          x2 - x1,
            'h':          y2 - y1,
            'occupied':   int(box.cls[0]) == 0,
            'confidence': round(float(box.conf[0]), 3),
        })

    return detections, w, h


def post_snapshot(detections, img_width, img_height):
    r = requests.post(API_URL, json={
        'img_width':  img_width,
        'img_height': img_height,
        'detections': detections,
    }, timeout=10)
    r.raise_for_status()
    return r.json()


def full_scan(frame_bytes, reason):
    detections, w, h = detect(frame_bytes)
    print(f'[detector] [{reason}] {len(detections)} detections ({w}x{h})')
    if detections:
        result = post_snapshot(detections, w, h)
        print(f'[detector] Snapshot {result["snapshot_id"]} — '
              f'{result["occupied"]} occupied / {result["open"]} open')
    else:
        print('[detector] No detections, skipping post')


def run():
    last_scan_at  = 0
    last_print    = ''  # short-circuit repeat printing of "no change" lines
    baseline_fp   = None  # fingerprint at time of last full scan

    while True:
        try:
            frame_bytes = grab_frame()
            now = time.time()

            time_since_scan = now - last_scan_at
            do_scan         = False
            reason          = None

            if baseline_fp is None:
                # first run: always scan
                do_scan, reason = True, 'initial'
            elif time_since_scan >= INTERVAL:
                # baseline timer elapsed
                do_scan, reason = True, 'interval'
            else:
                # quick check: compare current fingerprint to baseline
                current_fp = fingerprint(frame_bytes)
                diff = float(np.mean(cv2.absdiff(baseline_fp, current_fp)))
                if diff > CHANGE_THRESHOLD:
                    do_scan, reason = True, f'change detected (diff={diff:.1f})'
                else:
                    msg = f'[detector] quick check: no significant change (diff={diff:.2f}, {time_since_scan:.0f}s since scan)'
                    if msg != last_print:
                        print(msg)
                        last_print = msg

            if do_scan:
                full_scan(frame_bytes, reason)
                baseline_fp  = fingerprint(frame_bytes)
                last_scan_at = now
                last_print   = ''

        except Exception as e:
            print(f'[detector] Error: {e}')

        time.sleep(CHECK_EVERY)


if __name__ == '__main__':
    run()
