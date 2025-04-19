import socket
import threading
from battleship import run_two_player_game_online

HOST = '127.0.0.1'
PORT = 5000
NUM_PLAYERS = 2

def main():
    print(f"[INFO] Server listening on {HOST}:{PORT}")

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((HOST, PORT))
        s.listen(NUM_PLAYERS)

        players = []

        while len(players) < NUM_PLAYERS:
            conn, addr = s.accept()
            print(f"[INFO] Client {len(players) + 1} connected from {addr}")
            players.append((conn, addr))

        # Extract rfile/wfile from both players
        p1_conn, p1_addr = players[0]
        p2_conn, p2_addr = players[1]

        p1_rfile = p1_conn.makefile('r')
        p1_wfile = p1_conn.makefile('w')

        p2_rfile = p2_conn.makefile('r')
        p2_wfile = p2_conn.makefile('w')

        print(f"[INFO] {NUM_PLAYERS} clients have connected. Starting game...")

        try:
            run_two_player_game_online(p1_rfile, p1_wfile, p2_rfile, p2_wfile)
        except Exception as e:
            print(f"[ERROR] Exception during game: {e}")
        finally:
            print("[INFO] Closing connections...")
            p1_conn.close()
            p2_conn.close()

if __name__ == "__main__":
    main()
