"""
Integration tests: parking lot occupancy

Each test loads a different lot image, runs it through the real YOLO model,
posts detections to the API, and asserts the expected occupancy range.

Run from the project root:
    pytest tests/ -v -s
"""
import os

IMAGES = os.path.join(os.path.dirname(__file__), '..', 'fake-stream')


def run_detection_and_post(api_client, filename):
    path = os.path.join(IMAGES, filename)
    assert os.path.exists(path), f"Test image not found: {path}"

    with open(path, 'rb') as f:
        frame_bytes = f.read()

    from detector import detect
    detections, img_w, img_h = detect(frame_bytes)
    assert len(detections) > 0, "YOLO returned no detections"

    response = api_client.post('/api/snapshot', json={
        'img_width':  img_w,
        'img_height': img_h,
        'detections': detections,
    })
    assert response.status_code == 201, f"Snapshot POST failed: {response.get_json()}"

    state = api_client.get('/api/state').get_json()
    assert state and 'total' in state, "No state returned from API"
    assert state['total'] > 0, "API registered zero spots"
    return state


def test_empty_lot(api_client):
    state = run_detection_and_post(api_client, 'lotEmpty.jpg')
    pct = state['occupied'] / state['total'] * 100
    print(f"\n  image:    lotEmpty.jpg")
    print(f"  total:    {state['total']} spots")
    print(f"  occupied: {state['occupied']} spots")
    print(f"  open:     {state['open']} spots")
    print(f"  result:   {pct:.1f}% occupied  (expected <= 2%)")
    assert pct <= 2.0, f"FAIL: got {pct:.1f}%, expected <= 2%"


def test_half_full_lot(api_client):
    state = run_detection_and_post(api_client, 'lotHalfFull.jpg')
    pct = state['occupied'] / state['total'] * 100
    print(f"\n  image:    lotHalfFull.jpg")
    print(f"  total:    {state['total']} spots")
    print(f"  occupied: {state['occupied']} spots")
    print(f"  open:     {state['open']} spots")
    print(f"  result:   {pct:.1f}% occupied  (expected 44-56%)")
    assert 44.0 <= pct <= 56.0, f"FAIL: got {pct:.1f}%, expected 44-56%"


def test_full_lot(api_client):
    state = run_detection_and_post(api_client, 'lotFull.jpg')
    pct = state['occupied'] / state['total'] * 100
    print(f"\n  image:    lotFull.jpg")
    print(f"  total:    {state['total']} spots")
    print(f"  occupied: {state['occupied']} spots")
    print(f"  open:     {state['open']} spots")
    print(f"  result:   {pct:.1f}% occupied  (expected >= 96%)")
    assert pct >= 96.0, f"FAIL: got {pct:.1f}%, expected >= 96%"
