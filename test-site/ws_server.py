"""WebSocket echo server for testing. Run: python test-site/ws_server.py

Handles the WebSocket handshake and echoes messages back.
No external dependencies -- uses only stdlib.
"""
import hashlib
import base64
import socket
import struct
import threading

HOST = "0.0.0.0"
PORT = 8765
MAGIC = "258EAFA5-E914-47DA-95CA-5AB9FFE11285"


def accept_key(key: str) -> str:
    digest = hashlib.sha1((key + MAGIC).encode()).digest()
    return base64.b64encode(digest).decode()


def handshake(conn: socket.socket) -> bool:
    data = conn.recv(4096).decode()
    if "Upgrade: websocket" not in data:
        conn.close()
        return False

    key = ""
    for line in data.split("\r\n"):
        if line.lower().startswith("sec-websocket-key:"):
            key = line.split(":", 1)[1].strip()

    if not key:
        conn.close()
        return False

    response = (
        "HTTP/1.1 101 Switching Protocols\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        f"Sec-WebSocket-Accept: {accept_key(key)}\r\n"
        "\r\n"
    )
    conn.send(response.encode())
    return True


def read_frame(conn: socket.socket) -> tuple:
    header = conn.recv(2)
    if len(header) < 2:
        return None, None

    opcode = header[0] & 0x0F
    masked = header[1] & 0x80
    length = header[1] & 0x7F

    if length == 126:
        length = struct.unpack(">H", conn.recv(2))[0]
    elif length == 127:
        length = struct.unpack(">Q", conn.recv(8))[0]

    if masked:
        mask = conn.recv(4)
        data = bytearray(conn.recv(length))
        for i in range(len(data)):
            data[i] ^= mask[i % 4]
        data = bytes(data)
    else:
        data = conn.recv(length)

    return opcode, data


def send_frame(conn: socket.socket, data: str) -> None:
    payload = data.encode("utf-8")
    frame = bytearray()
    frame.append(0x81)
    length = len(payload)
    if length < 126:
        frame.append(length)
    elif length < 65536:
        frame.append(126)
        frame.extend(struct.pack(">H", length))
    else:
        frame.append(127)
        frame.extend(struct.pack(">Q", length))
    frame.extend(payload)
    conn.send(bytes(frame))


def handle_client(conn: socket.socket, addr: tuple) -> None:
    print(f"[WS] Connection from {addr}")
    if not handshake(conn):
        print(f"[WS] Handshake failed for {addr}")
        return

    print(f"[WS] Handshake complete for {addr}")
    try:
        while True:
            opcode, data = read_frame(conn)
            if opcode is None or opcode == 0x8:
                print(f"[WS] Client {addr} disconnected")
                break
            if opcode == 0x1:
                msg = data.decode("utf-8")
                print(f"[WS] Received: {msg}")
                echo = f"Echo: {msg}"
                send_frame(conn, echo)
                print(f"[WS] Sent: {echo}")
            elif opcode == 0x9:
                conn.send(b"\x8a\x00")
    except (ConnectionResetError, BrokenPipeError, OSError):
        pass
    finally:
        conn.close()


def main() -> None:
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((HOST, PORT))
    server.listen(5)
    print(f"[WS] WebSocket echo server running on ws://localhost:{PORT}/")
    print(f"[WS] Connect from JS: new WebSocket('ws://localhost:{PORT}/')")

    try:
        while True:
            conn, addr = server.accept()
            thread = threading.Thread(target=handle_client, args=(conn, addr), daemon=True)
            thread.start()
    except KeyboardInterrupt:
        print("\n[WS] Server stopped")
    finally:
        server.close()


if __name__ == "__main__":
    main()
