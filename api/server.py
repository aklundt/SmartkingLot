import os
from pathlib import Path
from dotenv import load_dotenv
from flask import Flask, request, jsonify
from flask_cors import CORS
import db

load_dotenv(Path(__file__).parent.parent / '.env')

HOST        = os.getenv('HOST', '0.0.0.0')
PORT        = int(os.getenv('PORT', 5000))
MAX_DIST_PX = int(os.getenv('MAX_DIST_PX', 60))

app = Flask(__name__)
CORS(app)


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


@app.route('/api/snapshot', methods=['POST'])
def post_snapshot():
    body       = request.get_json(force=True)
    detections = body.get('detections', [])
    img_width  = body.get('img_width',  1280)
    img_height = body.get('img_height', 720)

    if not detections:
        return jsonify({'error': 'no detections in payload'}), 400

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
    conn = sqlite3.connect(os.getenv('DB_PATH', 'api/parking.db'))
    conn.execute('DELETE FROM spot_states')
    conn.execute('DELETE FROM snapshots')
    conn.execute('DELETE FROM spots')
    conn.commit()
    conn.close()
    print('[api] Spots and history cleared')
    return jsonify({'status': 'cleared'})


if __name__ == '__main__':
    db.init_db()
    print(f'[api] Starting on http://{HOST}:{PORT}')
    app.run(host=HOST, port=PORT, debug=True)
