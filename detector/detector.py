import os
import time
import requests
import cv2
import numpy as np
import threading
from datetime import datetime, timezone
from ultralytics import YOLO
from flask import Flask, jsonify
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).parent.parent / '.env')

STREAM_URL = os.getenv('STREAM_URL', 'http://localhost:8080/feed')
API_URL    = os.getenv('API_URL',    'http://localhost:5000/api/snapshot')
CONFIDENCE = float(os.getenv('CONFIDENCE', 0.35))
INTERVAL   = int(os.getenv('INTERVAL', 60))
DETECTOR_PORT = int(os.getenv('DETECTOR_PORT', 5001))
SNAPSHOT_TIMEOUT = int(os.getenv('SNAPSHOT_TIMEOUT', 60))

MODEL_PATH = Path(__file__).parent.parent / 'models' / 'best_320x12n.pt'

model = YOLO(MODEL_PATH)
print(f'[detector] Model:    {MODEL_PATH}')
print(f'[detector] Stream:   {STREAM_URL}')
print(f'[detector] API:      {API_URL}')
print(f'[detector] Interval: {INTERVAL}s')
print(f'[detector] Snapshot timeout: {SNAPSHOT_TIMEOUT}s')

control = Flask(__name__)
rescan_requested = threading.Event()
status_lock = threading.Lock()
status = {
    'phase': 'starting',
    'pending_rescan': False,
    'last_scan_started_at': None,
    'last_scan_finished_at': None,
    'last_snapshot_id': None,
    'last_detections': None,
    'last_error': None,
    'last_message': None,
}


def now_utc():
    return datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')


def update_status(**kwargs):
    with status_lock:
        status.update(kwargs)


@control.route('/rescan', methods=['POST'])
def request_rescan():
    rescan_requested.set()
    update_status(pending_rescan=True, last_message='manual rescan queued')
    return jsonify({'status': 'queued'}), 202


@control.route('/status', methods=['GET'])
def detector_status():
    with status_lock:
        return jsonify(dict(status))


def run_control_server():
    control.run(host='0.0.0.0', port=DETECTOR_PORT, debug=False, use_reloader=False, threaded=True)


def grab_frame():
    r = requests.get(STREAM_URL, stream=True, timeout=10)
    buf = b''
    for chunk in r.iter_content(chunk_size=1024):
        buf += chunk
        start = buf.find(b'\xff\xd8')
        if start == -1:
            continue
        end = buf.find(b'\xff\xd9', start + 2)
        if end != -1:
            return buf[start:end+2]
    raise RuntimeError('Could not find a complete JPEG frame in stream')


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
    }, timeout=SNAPSHOT_TIMEOUT)
    r.raise_for_status()
    return r.json()


def run():
    threading.Thread(target=run_control_server, daemon=True).start()

    while True:
        try:
            update_status(
                phase='scanning',
                last_scan_started_at=now_utc(),
                last_error=None,
                last_message='grabbing frame',
            )
            print('[detector] Grabbing frame...')
            frame_bytes = grab_frame()

            update_status(last_message='running model')
            detections, w, h = detect(frame_bytes)
            update_status(last_detections=len(detections), last_message=f'{len(detections)} detections')
            print(f'[detector] {len(detections)} detections ({w}x{h})')

            if detections:
                update_status(phase='posting', last_message='posting snapshot')
                result = post_snapshot(detections, w, h)
                update_status(
                    last_snapshot_id=result.get('snapshot_id'),
                    last_message=f'snapshot {result.get("snapshot_id")} posted',
                )
                print(f'[detector] Snapshot {result["snapshot_id"]} - '
                      f'{result["occupied"]} occupied / {result["open"]} open')
            else:
                update_status(last_message='no detections above threshold, snapshot skipped')
                print('[detector] No detections above threshold, skipping post')

        except Exception as e:
            update_status(last_error=str(e), last_message='scan failed')
            print(f'[detector] Error: {e}')
        finally:
            update_status(phase='sleeping', last_scan_finished_at=now_utc())

        print(f'[detector] Sleeping {INTERVAL}s...')
        if rescan_requested.wait(INTERVAL):
            rescan_requested.clear()
            update_status(pending_rescan=False, last_message='manual rescan starting')
            print('[detector] Manual rescan requested')


if __name__ == '__main__':
    run()
