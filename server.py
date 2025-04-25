import socket
from battleship import run_two_player_game_online
from utils import *

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
            if len(players) < NUM_PLAYERS:
                send_package(conn, MessageTypes.WAITING)

        p1_conn, _ = players[0]
        p2_conn, _ = players[1]

        print(f"[INFO] {NUM_PLAYERS} clients have connected. Starting game...")

        try:
            run_two_player_game_online(p1_conn, p2_conn)
        except Exception as e:
            print(f"[ERROR] Exception during game: {e}")
        finally:
            print("[INFO] Closing connections...")
            p1_conn.close()
            p2_conn.close()

if __name__ == "__main__":
    main()
