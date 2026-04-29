import os
import sqlite3
from pathlib import Path
from dotenv import load_dotenv

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
        CREATE INDEX IF NOT EXISTS idx_spot_states_spot_snapshot
        ON spot_states (spot_id, snapshot_id)
    ''')

    c.execute('''
        CREATE INDEX IF NOT EXISTS idx_spot_states_snapshot
        ON spot_states (snapshot_id)
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


def get_spot_stats():
    """
    Per-spot statistics computed from spot_states + snapshots history.

    Returns a list of dicts: [{
        id, cx, cy, w, h,
        observations,        # number of snapshots this spot appeared in
        occupied_count,      # number of those where it was occupied
        occupied_pct,        # occupied_count / observations * 100
        turnover,            # number of state changes (occupied -> open or vice versa)
    }, ...]
    """
    conn = get_conn()

    # base spot info
    spots = {r['id']: dict(r) for r in conn.execute('SELECT * FROM spots').fetchall()}
    for s in spots.values():
        s['observations']   = 0
        s['occupied_count'] = 0
        s['turnover']       = 0

    # walk through every spot_state ordered by snapshot time, tracking transitions
    rows = conn.execute('''
        SELECT ss.spot_id, ss.occupied, s.timestamp
        FROM spot_states ss
        JOIN snapshots s ON s.id = ss.snapshot_id
        ORDER BY ss.spot_id, s.id
    ''').fetchall()

    last_state = {}  # spot_id -> last seen occupied value (0 or 1)
    for r in rows:
        sid = r['spot_id']
        occ = r['occupied']
        if sid not in spots:
            continue

        spots[sid]['observations']   += 1
        spots[sid]['occupied_count'] += occ

        if sid in last_state and last_state[sid] != occ:
            spots[sid]['turnover'] += 1
        last_state[sid] = occ

    conn.close()

    # compute percentages
    result = []
    for s in spots.values():
        s['occupied_pct'] = (
            s['occupied_count'] / s['observations'] * 100
            if s['observations'] > 0 else 0
        )
        result.append(s)

    return result


def normalize_spot_ids():
    """
    Reassign spot IDs in left-to-right, top-to-bottom reading order based on
    each spot's centroid. Rows are clustered by cy proximity (within half the
    average spot height) so that spots in the same physical row share a row
    index even if their cy values differ slightly.

    Updates spots and spot_states atomically so all foreign key references
    stay consistent. Safe to call repeatedly; idempotent if order is already
    normalized.
    """
    conn = get_conn()
    spots = [dict(r) for r in conn.execute('SELECT * FROM spots').fetchall()]

    if not spots:
        conn.close()
        return 0

    # cluster spots into rows: sort by cy, then walk through and break a new
    # row whenever cy jumps by more than half the average spot height
    avg_h = sum(s['h'] for s in spots) / len(spots)
    row_threshold = avg_h * 0.5

    spots.sort(key=lambda s: s['cy'])
    rows = [[spots[0]]]
    for s in spots[1:]:
        if s['cy'] - rows[-1][-1]['cy'] > row_threshold:
            rows.append([s])  # new row
        else:
            rows[-1].append(s)

    # within each row, sort left-to-right
    ordered = []
    for row in rows:
        row.sort(key=lambda s: s['cx'])
        ordered.extend(row)

    # assign new IDs starting at 1 — but to avoid collisions during update,
    # first remap to negative IDs, then to final positive IDs
    id_map = {s['id']: i + 1 for i, s in enumerate(ordered)}

    # phase 1: shift everything to negative space (no collisions possible)
    conn.execute('UPDATE spots SET id = -id')
    conn.execute('UPDATE spot_states SET spot_id = -spot_id')

    # phase 2: assign final positive IDs
    for old_id, new_id in id_map.items():
        conn.execute('UPDATE spots SET id = ? WHERE id = ?', (new_id, -old_id))
        conn.execute('UPDATE spot_states SET spot_id = ? WHERE spot_id = ?', (new_id, -old_id))

    # reset autoincrement sequence so future inserts continue from the new max
    conn.execute(
        "UPDATE sqlite_sequence SET seq = ? WHERE name = 'spots'",
        (len(ordered),)
    )

    conn.commit()
    conn.close()
    return len(ordered)


def get_last_states():
    """
    For every registered spot, return its most recently recorded occupancy.
    Returns dict {spot_id: 0|1}. Spots that have never been observed are not
    included.
    """
    conn = get_conn()
    rows = conn.execute('''
        SELECT ss.spot_id, ss.occupied
        FROM spot_states ss
        JOIN (
            SELECT spot_id, MAX(snapshot_id) AS snapshot_id
            FROM spot_states
            GROUP BY spot_id
        ) latest
          ON latest.spot_id = ss.spot_id
         AND latest.snapshot_id = ss.snapshot_id
    ''').fetchall()
    conn.close()
    return {r['spot_id']: r['occupied'] for r in rows}
