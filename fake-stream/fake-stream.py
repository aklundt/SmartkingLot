"""
fake-stream.py

Run as server:
    python3 fake-stream.py [initial_image.jpg]

Switch frame while running:
    python3 fake-stream.py some_image.jpg
"""

import sys
import os
import time
import socket
import threading
import requests
import cv2

HOST         = 'localhost'
PORT         = 8080
CONTROL_PORT = 8081
FPS          = 1

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


def run_control_server():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((HOST, CONTROL_PORT))
    server.listen(5)
    while True:
        conn, _ = server.accept()
        try:
            data = b''
            while True:
                chunk = conn.recv(4096)
                data += chunk
                if b'\r\n\r\n' in data:
                    break
            body = data.split(b'\r\n\r\n', 1)[1].decode().strip()
            switch_frame(body)
            conn.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nOK")
        except Exception as e:
            print(f'[fake-stream] Control error: {e}')
            conn.sendall(b"HTTP/1.1 500 Error\r\nContent-Length: 5\r\n\r\nERROR")
        finally:
            conn.close()


def is_server_running():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.connect((HOST, CONTROL_PORT))
        s.close()
        return True
    except ConnectionRefusedError:
        return False


def send_switch(path):
    path = os.path.abspath(path)
    r = requests.post(f'http://{HOST}:{CONTROL_PORT}/switch', data=path, timeout=5)
    if r.status_code == 200:
        print(f'[fake-stream] Switched stream to {path}')
    else:
        print(f'[fake-stream] Server returned error')


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Usage: python3 fake-stream.py <image>')
        sys.exit(1)

    image_path = sys.argv[1]

    if is_server_running():
        send_switch(image_path)
        sys.exit(0)

    switch_frame(image_path)
    threading.Thread(target=run_control_server, daemon=True).start()
    run_mjpeg_server()
