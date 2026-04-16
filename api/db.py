import os
import sqlite3
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / '.env')
DB_PATH = os.getenv('DB_PATH', 'api/parking.db')


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
            cx         REAL    NOT NULL,
            cy         REAL    NOT NULL,
            created_at TEXT    DEFAULT (datetime('now'))
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS snapshots (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT    DEFAULT (datetime('now')),
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
        'INSERT INTO spots (cx, cy) VALUES (?, ?)',
        [(d['cx'], d['cy']) for d in detections]
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
        SELECT s.id, s.cx, s.cy, ss.occupied
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
