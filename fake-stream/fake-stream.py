import cv2
import time
import socket
import threading

VIDEO_PATH = 'lot_slow.mp4'
HOST = 'localhost'
PORT = 8080

def stream_client(conn, addr):
    cap = cv2.VideoCapture(VIDEO_PATH)
    try:
        conn.sendall(
            b"HTTP/1.1 200 OK\r\n"
            b"Content-Type: multipart/x-mixed-replace; boundary=frame\r\n\r\n"
        )
        while True:
            ret, frame = cap.read()
            if not ret:
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                continue
            _, jpg = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
            data = jpg.tobytes()
            header = (
                f"--frame\r\n"
                f"Content-Type: image/jpeg\r\n"
                f"Content-Length: {len(data)}\r\n\r\n"
            ).encode()
            conn.sendall(header + data + b"\r\n")
            time.sleep(1/30)
    except:
        pass
    finally:
        cap.release()
        conn.close()

server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server.bind((HOST, PORT))
server.listen(5)
print(f"Streaming {VIDEO_PATH} at http://{HOST}:{PORT}/feed")

while True:
    conn, addr = server.accept()
    threading.Thread(target=stream_client, args=(conn, addr), daemon=True).start()
