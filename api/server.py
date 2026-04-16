import os
from dotenv import load_dotenv
from flask import Flask, request, jsonify
from flask_cors import CORS
import db

load_dotenv()
HOST        = os.getenv('HOST', '0.0.0.0')
PORT        = int(os.getenv('PORT', 5000))
MAX_DIST_PX = int(os.getenv('MAX_DIST_PX', 60))

app = Flask(__name__)
CORS(app)  # allow the frontend (different port) to call the API


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def match_detections_to_spots(detections, registered_spots):
    """
    For each incoming detection, find the nearest registered spot centroid.
    Returns {spot_id: occupied_bool} for every detection that matched within
    MAX_DIST_PX pixels.  Unmatched detections are ignored (shouldn't happen
    after registration, but protects against camera shifts).
    """
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


# ---------------------------------------------------------------------------
# routes
# ---------------------------------------------------------------------------

@app.route('/api/snapshot', methods=['POST'])
def post_snapshot():
    """
    Receives detections from detector.py.

    Expected body:
    {
        "img_width":  1280,
        "img_height": 720,
        "detections": [
            {"cx": 145, "cy": 230, "occupied": true, "confidence": 0.87},
            ...
        ]
    }
    """
    body = request.get_json(force=True)
    detections = body.get('detections', [])
    img_width  = body.get('img_width',  1280)
    img_height = body.get('img_height', 720)

    if not detections:
        return jsonify({'error': 'no detections in payload'}), 400

    # always keep camera config up to date
    db.set_camera_config(img_width, img_height)

    # first time: register spots from this snapshot
    if not db.spots_registered():
        registered = db.register_spots(detections)
        print(f'[api] Registered {len(registered)} spots for the first time')
    else:
        registered = db.get_all_spots()

    spot_states = match_detections_to_spots(detections, registered)
    snapshot_id = db.save_snapshot(spot_states)

    occ  = sum(1 for v in spot_states.values() if v)
    open_ = len(spot_states) - occ
    print(f'[api] Snapshot {snapshot_id}: {occ} occupied / {open_} open')

    return jsonify({'snapshot_id': snapshot_id, 'occupied': occ, 'open': open_}), 201


@app.route('/api/state', methods=['GET'])
def get_state():
    """
    Returns the most recent snapshot with per-spot positions and occupancy.
    The frontend uses img_width/img_height to scale dot positions.
    """
    state = db.get_latest_state()
    if not state:
        return jsonify({'error': 'no data yet'}), 404

    cam = db.get_camera_config()
    state['img_width']  = cam['img_width']
    state['img_height'] = cam['img_height']

    return jsonify(state)


@app.route('/api/history', methods=['GET'])
def get_history():
    """
    Returns aggregate occupancy over time.
    Optional query param: ?hours=24  (default 24)
    """
    hours = request.args.get('hours', 24, type=int)
    rows  = db.get_history(hours)
    return jsonify(rows)


@app.route('/api/reset', methods=['POST'])
def reset_spots():
    """
    DEV ONLY: clears registered spots so the next snapshot re-registers.
    Useful when you move the camera or swap to a different lot.
    """
    import sqlite3
    conn = sqlite3.connect(os.getenv('DB_PATH', 'parking.db'))
    conn.execute('DELETE FROM spot_states')
    conn.execute('DELETE FROM snapshots')
    conn.execute('DELETE FROM spots')
    conn.commit()
    conn.close()
    print('[api] Spots and history cleared')
    return jsonify({'status': 'cleared'})


# ---------------------------------------------------------------------------
# startup
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    db.init_db()
    print(f'[api] Starting on http://{HOST}:{PORT}')
    app.run(host=HOST, port=PORT, debug=True)
