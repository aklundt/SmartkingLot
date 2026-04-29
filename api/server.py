import os
from pathlib import Path
from dotenv import load_dotenv
from flask import Flask, request, jsonify, send_from_directory, Response
from flask_login import (
    LoginManager, UserMixin, login_user,
    logout_user, login_required, current_user
)
import requests as req
import db

load_dotenv(Path(__file__).parent.parent / '.env')

API_PORT    = int(os.getenv('API_PORT', 5000))
MAX_DIST_PX = int(os.getenv('MAX_DIST_PX', 60))
NMS_IOU     = float(os.getenv('NMS_IOU', 0.30))
STREAM_URL  = os.getenv('STREAM_URL', 'http://localhost:8080/feed')

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'dev-secret-change-me-in-production')

# Flask-Login setup
login_manager = LoginManager(app)
login_manager.login_view = '/'

class User(UserMixin):
    def __init__(self, data):
        self.id         = data['id']
        self.username   = data['username']
        self.email      = data.get('email')
        self.is_admin   = bool(data.get('is_admin', 0))

@login_manager.user_loader
def load_user(user_id):
    data = db.get_user_by_id(int(user_id))
    return User(data) if data else None


# ============================================================
# Auth helpers
# ============================================================

def admin_required(f):
    """Decorator to require admin privileges"""
    from functools import wraps
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if not current_user.is_admin:
            return jsonify({'error': 'Admin privileges required'}), 403
        return f(*args, **kwargs)
    return decorated_function


def api_key_required(f):
    """Decorator to require valid API key (for detector endpoints)"""
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        api_key = request.headers.get('X-API-Key') or request.headers.get('Authorization', '').replace('Bearer ', '')
        
        if not api_key:
            return jsonify({'error': 'API key required'}), 401
        
        key_data = db.verify_api_key(api_key)
        if not key_data:
            return jsonify({'error': 'Invalid API key'}), 401
        
        # Store key info in request context for logging
        request.api_key_name = key_data['name']
        return f(*args, **kwargs)
    
    return decorated_function


# ============================================================
# Detection utility functions
# ============================================================

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


# ============================================================
# Public routes
# ============================================================

@app.route('/health')
def health():
    return 'ok', 200


@app.route('/')
def index():
    FRONTEND = Path(__file__).parent.parent / "frontend"
    return send_from_directory(str(FRONTEND), "index.html")


@app.route('/stream')
def stream():
    r = req.get(STREAM_URL, stream=True, timeout=10)
    return Response(r.iter_content(chunk_size=1024),
                    content_type=r.headers['Content-Type'])


# ============================================================
# Auth routes
# ============================================================

@app.route('/login', methods=['POST'])
def login():
    body = request.get_json()
    user_data = db.get_user_by_username(body.get('username', ''))
    
    if user_data and db.verify_password(user_data, body.get('password', '')):
        login_user(User(user_data))
        return jsonify({
            'success': True,
            'user': {
                'id': user_data['id'],
                'username': user_data['username'],
                'email': user_data.get('email'),
                'is_admin': bool(user_data.get('is_admin', 0))
            }
        })
    
    return jsonify({'success': False, 'message': 'Invalid credentials'}), 401


@app.route('/logout', methods=['POST'])
@login_required
def logout():
    logout_user()
    return jsonify({'success': True})


@app.route('/me', methods=['GET'])
@login_required
def get_current_user():
    """Get current logged-in user info"""
    return jsonify({
        'id': current_user.id,
        'username': current_user.username,
        'email': current_user.email,
        'is_admin': current_user.is_admin
    })


@app.route('/me', methods=['PUT'])
@login_required
def update_current_user():
    """Update current user's email or password"""
    body = request.get_json()
    
    email = body.get('email')
    current_password = body.get('current_password')
    new_password = body.get('new_password')
    
    # Get current user data to verify password
    user_data = db.get_user_by_id(current_user.id)
    
    # If changing password, verify current password first
    if new_password:
        if not current_password:
            return jsonify({'error': 'Current password required to change password'}), 400
        
        if not db.verify_password(user_data, current_password):
            return jsonify({'error': 'Current password is incorrect'}), 401
    
    # Update email and/or password
    success = db.update_user(
        current_user.id,
        email=email,
        password=new_password if new_password else None
    )
    
    if not success:
        return jsonify({'error': 'Failed to update profile'}), 400
    
    # Return updated user info
    updated_user = db.get_user_by_id(current_user.id)
    return jsonify({
        'id': updated_user['id'],
        'username': updated_user['username'],
        'email': updated_user.get('email'),
        'is_admin': bool(updated_user.get('is_admin', 0))
    })


# ============================================================
# User management routes (admin only)
# ============================================================

@app.route('/api/users', methods=['GET'])
@admin_required
def get_users():
    """List all users"""
    users = db.get_all_users()
    return jsonify(users)


@app.route('/api/users', methods=['POST'])
@admin_required
def create_user():
    """Create a new user"""
    body = request.get_json()
    
    username = body.get('username', '').strip()
    password = body.get('password', '')
    email = body.get('email', '').strip() or None
    is_admin = body.get('is_admin', False)
    
    if not username or not password:
        return jsonify({'error': 'Username and password required'}), 400
    
    user = db.create_user(username, password, email, is_admin)
    
    if not user:
        return jsonify({'error': 'Username already exists'}), 409
    
    return jsonify({
        'id': user['id'],
        'username': user['username'],
        'email': user.get('email'),
        'is_admin': bool(user.get('is_admin', 0))
    }), 201


@app.route('/api/users/<int:user_id>', methods=['PUT'])
@admin_required
def update_user(user_id):
    """Update a user"""
    body = request.get_json()
    
    username = body.get('username')
    email = body.get('email')
    password = body.get('password')
    is_admin = body.get('is_admin')
    
    success = db.update_user(
        user_id,
        username=username,
        email=email,
        password=password,
        is_admin=is_admin
    )
    
    if not success:
        return jsonify({'error': 'Update failed or username taken'}), 400
    
    user = db.get_user_by_id(user_id)
    return jsonify({
        'id': user['id'],
        'username': user['username'],
        'email': user.get('email'),
        'is_admin': bool(user.get('is_admin', 0))
    })


@app.route('/api/users/<int:user_id>', methods=['DELETE'])
@admin_required
def delete_user(user_id):
    """Delete a user"""
    # Prevent deleting yourself
    if user_id == current_user.id:
        return jsonify({'error': 'Cannot delete your own account'}), 400
    
    db.delete_user(user_id)
    return jsonify({'success': True})


# ============================================================
# API Key management routes (admin only)
# ============================================================

@app.route('/api/keys', methods=['GET'])
@admin_required
def get_api_keys():
    """List all API keys"""
    keys = db.get_all_api_keys()
    return jsonify(keys)


@app.route('/api/keys', methods=['POST'])
@admin_required
def create_api_key():
    """Create a new API key"""
    body = request.get_json()
    
    name = body.get('name', '').strip()
    description = body.get('description', '').strip() or None
    
    if not name:
        return jsonify({'error': 'Name is required'}), 400
    
    api_key = db.create_api_key(name, description)
    
    if not api_key:
        return jsonify({'error': 'Failed to create API key'}), 500
    
    return jsonify({
        'api_key': api_key,
        'name': name,
        'description': description,
        'warning': 'Save this key now - it will not be shown again!'
    }), 201


@app.route('/api/keys/<int:key_id>', methods=['DELETE'])
@admin_required
def delete_api_key(key_id):
    """Delete an API key"""
    db.delete_api_key(key_id)
    return jsonify({'success': True})


@app.route('/api/keys/<int:key_id>/revoke', methods=['POST'])
@admin_required
def revoke_api_key(key_id):
    """Revoke (deactivate) an API key"""
    db.revoke_api_key(key_id)
    return jsonify({'success': True})


# ============================================================
# Parking API routes (protected)
# ============================================================

@app.route('/api/snapshot', methods=['POST'])
@api_key_required
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
    print(f'[api] Snapshot {snapshot_id} from [{request.api_key_name}]: {occ} occupied / {open_} open')

    return jsonify({'snapshot_id': snapshot_id, 'occupied': occ, 'open': open_}), 201


@app.route('/api/state', methods=['GET'])
@login_required
def get_state():
    state = db.get_latest_state()
    if not state:
        return jsonify({'error': 'no data yet'}), 404

    cam = db.get_camera_config()
    state['img_width']  = cam['img_width']
    state['img_height'] = cam['img_height']
    return jsonify(state)


@app.route('/api/history', methods=['GET'])
@login_required
def get_history():
    hours = request.args.get('hours', 24, type=int)
    return jsonify(db.get_history(hours))


@app.route('/api/reset', methods=['POST'])
@admin_required
def reset_spots():
    """Reset all parking spot data (admin only)"""
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
