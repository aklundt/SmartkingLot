import sys
import os
import time
import socket
import threading
import cv2

HOST = 'localhost'
PORT = 8080
FPS  = 1

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
    print(f'[fake-stream] Type a filename to switch frames')
    while True:
        conn, _ = server.accept()
        threading.Thread(target=stream_client, args=(conn,), daemon=True).start()


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Usage: python3 fake-stream.py <image>')
        sys.exit(1)

    switch_frame(sys.argv[1])
    threading.Thread(target=run_mjpeg_server, daemon=True).start()

    while True:
        path = input('> ').strip()
        if path:
            try:
                switch_frame(path)
            except Exception as e:
                print(f'Error: {e}')
