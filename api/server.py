import os
from pathlib import Path
from dotenv import load_dotenv
from flask import Flask, request, jsonify, send_from_directory, Response
import requests as req
import db

load_dotenv(Path(__file__).parent.parent / '.env')

API_PORT    = int(os.getenv('API_PORT', 5000))
MAX_DIST_PX = int(os.getenv('MAX_DIST_PX', 60))
NMS_IOU     = float(os.getenv('NMS_IOU', 0.30))
STREAM_URL  = os.getenv('STREAM_URL', 'http://localhost:8080/feed')

app = Flask(__name__)


def filter_by_size(detections):
    """
    Drop detections whose area is a statistical outlier using modified Z-score
    (median absolute deviation). Robust against the outliers themselves skewing
    the calculation, unlike mean/stddev. Needs at least 4 detections to be meaningful.
    """
    if len(detections) < 4:
        return detections

    areas  = [d['w'] * d['h'] for d in detections]
    median = sorted(areas)[len(areas) // 2]
    mad    = sorted([abs(a - median) for a in areas])[len(areas) // 2]

    if mad == 0:
        return detections  # all same size, nothing to filter

    kept    = [d for d in detections if 0.6745 * abs(d['w'] * d['h'] - median) / mad <= 3.5]
    removed = len(detections) - len(kept)
    if removed:
        print(f'[api] Size filter removed {removed} outliers '
              f'(median area {median:.0f}px², MAD {mad:.0f}px²)')
    return kept


def iou(a, b):
    ax1, ay1 = a['cx'] - a['w'] / 2, a['cy'] - a['h'] / 2
    ax2, ay2 = a['cx'] + a['w'] / 2, a['cy'] + a['h'] / 2
    bx1, by1 = b['cx'] - b['w'] / 2, b['cy'] - b['h'] / 2
    bx2, by2 = b['cx'] + b['w'] / 2, b['cy'] + b['h'] / 2

    inter_w = max(0, min(ax2, bx2) - max(ax1, bx1))
    inter_h = max(0, min(ay2, by2) - max(ay1, by1))
    inter   = inter_w * inter_h

    union = (ax2 - ax1) * (ay2 - ay1) + (bx2 - bx1) * (by2 - by1) - inter
    return inter / union if union > 0 else 0


def nms(detections):
    sorted_dets = sorted(detections, key=lambda d: d['confidence'], reverse=True)
    kept = []
    for det in sorted_dets:
        if all(iou(det, k) <= NMS_IOU for k in kept):
            kept.append(det)
    return kept


def match_detections_to_spots(detections, registered_spots):
    states = {}
    for det in detections:
        best = min(
            registered_spots,
            key=lambda s: (s['cx'] - det['cx'])**2 + (s['cy'] - det['cy'])**2
        )
        dist = ((best['cx'] - det['cx'])**2 + (best['cy'] - det['cy'])**2) ** 0.5
        if dist < MAX_DIST_PX:
            states[best['id']] = det['occupied']
    return states


@app.route('/')
def index():
    return send_from_directory('../frontend', 'index.html')


@app.route('/stream')
def stream():
    r = req.get(STREAM_URL, stream=True, timeout=10)
    return Response(r.iter_content(chunk_size=1024),
                    content_type=r.headers['Content-Type'])


@app.route('/api/snapshot', methods=['POST'])
def post_snapshot():
    body       = request.get_json(force=True)
    detections = body.get('detections', [])
    img_width  = body.get('img_width',  1280)
    img_height = body.get('img_height', 720)

    if not detections:
        return jsonify({'error': 'no detections in payload'}), 400

    detections = filter_by_size(detections)

    before     = len(detections)
    detections = nms(detections)
    after      = len(detections)
    if before != after:
        print(f'[api] NMS removed {before - after} overlapping detections ({before} → {after})')

    if not detections:
        return jsonify({'error': 'no detections survived filtering'}), 400

    db.set_camera_config(img_width, img_height)

    if not db.spots_registered():
        registered = db.register_spots(detections)
        print(f'[api] Registered {len(registered)} spots for the first time')
    else:
        registered = db.get_all_spots()

    spot_states = match_detections_to_spots(detections, registered)
    snapshot_id = db.save_snapshot(spot_states)

    occ   = sum(1 for v in spot_states.values() if v)
    open_ = len(spot_states) - occ
    print(f'[api] Snapshot {snapshot_id}: {occ} occupied / {open_} open')

    return jsonify({'snapshot_id': snapshot_id, 'occupied': occ, 'open': open_}), 201


@app.route('/api/state', methods=['GET'])
def get_state():
    state = db.get_latest_state()
    if not state:
        return jsonify({'error': 'no data yet'}), 404

    cam = db.get_camera_config()
    state['img_width']  = cam['img_width']
    state['img_height'] = cam['img_height']
    return jsonify(state)


@app.route('/api/history', methods=['GET'])
def get_history():
    hours = request.args.get('hours', 24, type=int)
    return jsonify(db.get_history(hours))


@app.route('/api/reset', methods=['POST'])
def reset_spots():
    import sqlite3
    conn = sqlite3.connect(os.getenv('DB_PATH', 'parking.db'))
    conn.execute('DELETE FROM spot_states')
    conn.execute('DELETE FROM snapshots')
    conn.execute('DELETE FROM spots')
    conn.commit()
    conn.close()
    print('[api] Spots and history cleared')
    return jsonify({'status': 'cleared'})


if __name__ == '__main__':
    db.init_db()
    print(f'[api] Starting on http://0.0.0.0:{API_PORT}')
    app.run(host='0.0.0.0', port=API_PORT, debug=True)
