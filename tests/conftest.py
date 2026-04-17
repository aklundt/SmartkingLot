import os
import sys
import tempfile
import pytest

# make api/ and detector/ importable
ROOT = os.path.join(os.path.dirname(__file__), '..')
sys.path.insert(0, os.path.join(ROOT, 'api'))
sys.path.insert(0, os.path.join(ROOT, 'detector'))


@pytest.fixture
def api_client():
    """
    Spins up the Flask app against a temporary SQLite database.
    Tears it down and deletes the db file after the test.
    """
    tmp = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
    tmp.close()

    # set env vars before importing db/server so they pick up the temp db
    os.environ['DB_PATH']      = tmp.name
    os.environ['MAX_DIST_PX']  = '60'
    os.environ['NMS_IOU']      = '0.30'
    os.environ['STREAM_URL']   = 'http://localhost:8080/feed'  # not called in these tests

    import db
    import server

    db.init_db()
    server.app.config['TESTING'] = True

    with server.app.test_client() as client:
        yield client

    os.unlink(tmp.name)
