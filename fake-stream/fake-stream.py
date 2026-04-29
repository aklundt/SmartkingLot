"""
fake-stream.py

Two modes:

  1. Manual:
       python3 fake-stream.py lotEmpty.jpg
     Type a filename at the > prompt to swap frames.

  2. Auto-rotate (random image every N seconds):
       python3 fake-stream.py --auto
     Picks a random image from lot1.jpg-lot11.jpg every 2 minutes.
"""

import sys
import os
import time
import random
import socket
import threading
import cv2

HOST = '0.0.0.0'
PORT = 8080
FPS  = 1

# auto mode config
AUTO_INTERVAL  = 40
AUTO_PATTERNS  = [f'lot{i}.jpg' for i in range(1, 12)]

current_frame = None
frame_lock    = threading.Lock()


def load_image(path):
    img = cv2.imread(path)
    if img is None:
        raise ValueError(f'Could not load image: {path}')
    _, jpg = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return jpg.tobytes()


def switch_frame(path):
    global current_frame
    path = os.path.abspath(path)
    jpg = load_image(path)
    with frame_lock:
        current_frame = jpg
    print(f'[fake-stream] Switched to {path}')


def stream_client(conn):
    try:
        conn.sendall(
            b"HTTP/1.1 200 OK\r\n"
            b"Content-Type: multipart/x-mixed-replace; boundary=frame\r\n\r\n"
        )
        while True:
            with frame_lock:
                data = current_frame
            if data:
                header = (
                    f"--frame\r\nContent-Type: image/jpeg\r\n"
                    f"Content-Length: {len(data)}\r\n\r\n"
                ).encode()
                conn.sendall(header + data + b"\r\n")
            time.sleep(1 / FPS)
    except:
        pass
    finally:
        conn.close()


def run_mjpeg_server():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((HOST, PORT))
    server.listen(5)
    print(f'[fake-stream] MJPEG at http://{HOST}:{PORT}/feed')
    while True:
        conn, _ = server.accept()
        threading.Thread(target=stream_client, args=(conn,), daemon=True).start()


def auto_rotate_loop():
    """Pick a random image from AUTO_PATTERNS every AUTO_INTERVAL seconds."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    available  = [f for f in AUTO_PATTERNS if os.path.exists(os.path.join(script_dir, f))]

    if not available:
        print(f'[fake-stream] No images found matching {AUTO_PATTERNS} in {script_dir}')
        return

    print(f'[fake-stream] Auto-rotating every {AUTO_INTERVAL}s among: {available}')
    last = None
    while True:
        # pick a random image, but try not to repeat the same one twice in a row
        choices = [f for f in available if f != last] or available
        pick = random.choice(choices)
        try:
            switch_frame(os.path.join(script_dir, pick))
            last = pick
        except Exception as e:
            print(f'[fake-stream] Auto-rotate error: {e}')
        time.sleep(AUTO_INTERVAL)


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Usage: python3 fake-stream.py <image>')
        print('       python3 fake-stream.py --auto')
        sys.exit(1)

    if sys.argv[1] == '--auto':
        # show first available image immediately so the stream isn't blank
        script_dir = os.path.dirname(os.path.abspath(__file__))
        first = next((f for f in AUTO_PATTERNS if os.path.exists(os.path.join(script_dir, f))), None)
        if first:
            switch_frame(os.path.join(script_dir, first))

        threading.Thread(target=auto_rotate_loop, daemon=True).start()
        run_mjpeg_server()
    else:
        switch_frame(sys.argv[1])
        run_mjpeg_server()
