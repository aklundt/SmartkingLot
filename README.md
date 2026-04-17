# SmartkingLot

AI parking lot occupancy monitoring. A camera streams footage, YOLOv8 detects occupied and open spaces, and a dashboard displays live status and history.

## Components

- **fake-stream** — simulates an IoT edge device camera by serving a static image as an MJPEG stream. In a real deployment this would be a Raspberry Pi or similar device mounted over the lot.
- **detector** — pulls a frame every 20 seconds, runs YOLOv8 inference, and posts detections to the API.
- **api** — Flask + SQLite. Maintains spot registry, occupancy state, and history. Also serves the UI.
- **ui** — single-page dashboard showing a live annotated feed, occupancy stats, and spot map.

## Running

**1. Start the fake stream** (simulates the edge device — run this on the host, not in Docker):

```bash
cd fake-stream
python3 fake-stream.py lotEmpty.jpg
```

Type a filename at the `>` prompt to switch between lot images at any time.

**2. Start everything else:**

```bash
git clone https://github.com/aklundt/SmartkingLot.git
cd SmartkingLot
cp .env.example .env   # edit if needed
docker compose up
```

Dashboard at `http://localhost:5000`.

## Configuration

Copy `.env.example` to `.env` and adjust:

```
API_PORT=5000
DB_PATH=parking.db
MAX_DIST_PX=60        # pixel distance for matching detections to registered spots
NMS_IOU=0.30          # overlap threshold for suppressing duplicate detections

CONFIDENCE=0.35       # yolo detection threshold (recommended: 0.35-0.5)
INTERVAL=20           # seconds between detection cycles
```

## Reset

If you switch lot images, reset the registered spots so they re-register from the new frame:

```bash
curl -X POST http://localhost:5000/api/reset
```
