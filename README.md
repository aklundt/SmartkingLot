# SmartkingLot

CV parking lot occupancy monitoring. YOLOv8 detects occupied/open spaces from a camera stream and serves live status through a REST API.

## Components

- **fake-stream/** — serves a static image as an MJPEG stream. Type a filename at the prompt to swap images.
- **detector/** — grabs a frame every 60s, runs YOLOv8, posts detections to the API.
- **api/** — Flask + SQLite. Maintains spot registry, occupancy state, and history.
- **models/** — YOLOv8 nano model, included in repo.

## Setup

```bash
git clone https://github.com/aklundt/SmartkingLot.git
cd SmartkingLot
uv venv
source .venv/bin/activate
uv pip install -r requirements.txt
```

Create `.env` in the project root:

```
# api
API_PORT=5000           # port the flask server listens on
DB_PATH=parking.db      # sqlite file, created in api/ when running server.py
MAX_DIST_PX=60          # max pixels between a detection and its registered spot

# detector
API_URL=http://localhost:5000/api/snapshot  # where to POST detections
STREAM_URL=http://localhost:8080/feed       # mjpeg stream to pull frames from
CONFIDENCE=0.35         # yolo detection threshold (recommended: 0.35-0.5)
INTERVAL=60             # seconds between detection cycles (recommended: 60)
```

## Running

Three terminals, venv activated in each.

```bash
# terminal 1
cd fake-stream && python3 fake-stream.py lotEmpty.jpg
# type a filename at > to switch frames

# terminal 2
cd api && python3 server.py

# terminal 3
cd detector && python3 detector.py
```

To reset registered spots after switching lot images:
```bash
curl -X POST http://localhost:5000/api/reset
```
