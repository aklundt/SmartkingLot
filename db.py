import os
import sqlite3
from pathlib import Path
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash, check_password_hash

load_dotenv(Path(__file__).parent.parent / '.env')
DB_PATH = os.getenv('DB_PATH', 'parking.db')


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    c = conn.cursor()

    c.execute('''
        CREATE TABLE IF NOT EXISTS spots (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            cx         REAL NOT NULL,
            cy         REAL NOT NULL,
            w          REAL NOT NULL DEFAULT 0,
            h          REAL NOT NULL DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now'))
        )
    ''')

    # migrate existing db that may not have w/h columns
    try:
        c.execute('ALTER TABLE spots ADD COLUMN w REAL NOT NULL DEFAULT 0')
        c.execute('ALTER TABLE spots ADD COLUMN h REAL NOT NULL DEFAULT 0')
    except:
        pass

    c.execute('''
        CREATE TABLE IF NOT EXISTS snapshots (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT DEFAULT (datetime('now')),
            total     INTEGER NOT NULL,
            occupied  INTEGER NOT NULL,
            open      INTEGER NOT NULL
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS spot_states (
            snapshot_id INTEGER NOT NULL REFERENCES snapshots(id),
            spot_id     INTEGER NOT NULL REFERENCES spots(id),
            occupied    INTEGER NOT NULL
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS camera_config (
            id         INTEGER PRIMARY KEY CHECK (id = 1),
            img_width  INTEGER NOT NULL,
            img_height INTEGER NOT NULL
        )
    ''')

    # User management tables
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            username      TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            email         TEXT,
            is_admin      INTEGER NOT NULL DEFAULT 0,
            created_at    TEXT DEFAULT (datetime('now'))
        )
    ''')

    # Migrate existing users table if email column doesn't exist
    try:
        c.execute('ALTER TABLE users ADD COLUMN email TEXT')
    except:
        pass
    
    try:
        c.execute('ALTER TABLE users ADD COLUMN is_admin INTEGER NOT NULL DEFAULT 0')
    except:
        pass

    conn.commit()
    conn.close()


def spots_registered():
    conn = get_conn()
    count = conn.execute('SELECT COUNT(*) FROM spots').fetchone()[0]
    conn.close()
    return count > 0


def register_spots(detections):
    conn = get_conn()
    conn.executemany(
        'INSERT INTO spots (cx, cy, w, h) VALUES (?, ?, ?, ?)',
        [(d['cx'], d['cy'], d['w'], d['h']) for d in detections]
    )
    conn.commit()
    all_spots = [dict(r) for r in conn.execute('SELECT * FROM spots').fetchall()]
    conn.close()
    return all_spots


def get_all_spots():
    conn = get_conn()
    spots = [dict(r) for r in conn.execute('SELECT * FROM spots').fetchall()]
    conn.close()
    return spots


def set_camera_config(width, height):
    conn = get_conn()
    conn.execute('''
        INSERT INTO camera_config (id, img_width, img_height) VALUES (1, ?, ?)
        ON CONFLICT(id) DO UPDATE SET img_width=excluded.img_width, img_height=excluded.img_height
    ''', (width, height))
    conn.commit()
    conn.close()


def get_camera_config():
    conn = get_conn()
    row = conn.execute('SELECT * FROM camera_config WHERE id=1').fetchone()
    conn.close()
    return dict(row) if row else {'img_width': 1280, 'img_height': 720}


def save_snapshot(spot_states):
    total    = len(spot_states)
    occupied = sum(1 for v in spot_states.values() if v)
    open_    = total - occupied

    conn = get_conn()
    cur  = conn.execute(
        'INSERT INTO snapshots (total, occupied, open) VALUES (?, ?, ?)',
        (total, occupied, open_)
    )
    snapshot_id = cur.lastrowid

    conn.executemany(
        'INSERT INTO spot_states (snapshot_id, spot_id, occupied) VALUES (?, ?, ?)',
        [(snapshot_id, spot_id, 1 if occ else 0) for spot_id, occ in spot_states.items()]
    )
    conn.commit()
    conn.close()
    return snapshot_id


def get_latest_state():
    conn = get_conn()
    snap = conn.execute('SELECT * FROM snapshots ORDER BY id DESC LIMIT 1').fetchone()
    if not snap:
        conn.close()
        return None

    snap = dict(snap)
    spot_rows = conn.execute('''
        SELECT s.id, s.cx, s.cy, s.w, s.h, ss.occupied
        FROM spot_states ss
        JOIN spots s ON s.id = ss.spot_id
        WHERE ss.snapshot_id = ?
    ''', (snap['id'],)).fetchall()

    snap['spots'] = [dict(r) for r in spot_rows]
    conn.close()
    return snap


def get_history(hours=24):
    conn = get_conn()
    rows = conn.execute('''
        SELECT id, timestamp, total, occupied, open
        FROM snapshots
        WHERE timestamp >= datetime('now', ?)
        ORDER BY timestamp ASC
    ''', (f'-{hours} hours',)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ============================================================
# User management functions
# ============================================================

def create_user(username, password, email=None, is_admin=False):
    """Create a new user account"""
    conn = get_conn()
    try:
        conn.execute(
            'INSERT INTO users (username, password_hash, email, is_admin) VALUES (?, ?, ?, ?)',
            (username, generate_password_hash(password), email, 1 if is_admin else 0)
        )
        conn.commit()
        user_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
        user = get_user_by_id(user_id)
        conn.close()
        return user
    except sqlite3.IntegrityError:
        conn.close()
        return None


def get_user_by_username(username):
    """Get user by username"""
    conn = get_conn()
    row = conn.execute(
        'SELECT * FROM users WHERE username = ?', (username,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_user_by_id(user_id):
    """Get user by ID"""
    conn = get_conn()
    row = conn.execute(
        'SELECT * FROM users WHERE id = ?', (user_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_all_users():
    """Get all users (without password hashes)"""
    conn = get_conn()
    rows = conn.execute(
        'SELECT id, username, email, is_admin, created_at FROM users ORDER BY created_at DESC'
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_user(user_id, username=None, email=None, password=None, is_admin=None):
    """Update user information"""
    conn = get_conn()
    updates = []
    params = []
    
    if username is not None:
        updates.append('username = ?')
        params.append(username)
    if email is not None:
        updates.append('email = ?')
        params.append(email)
    if password is not None:
        updates.append('password_hash = ?')
        params.append(generate_password_hash(password))
    if is_admin is not None:
        updates.append('is_admin = ?')
        params.append(1 if is_admin else 0)
    
    if not updates:
        conn.close()
        return False
    
    params.append(user_id)
    
    try:
        conn.execute(
            f'UPDATE users SET {", ".join(updates)} WHERE id = ?',
            params
        )
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        conn.close()
        return False


def delete_user(user_id):
    """Delete a user"""
    conn = get_conn()
    conn.execute('DELETE FROM users WHERE id = ?', (user_id,))
    conn.commit()
    conn.close()


def verify_password(user, password):
    """Verify a user's password"""
    return check_password_hash(user['password_hash'], password)
