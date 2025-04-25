import socket
import time
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
        while True:
            while len(players) < NUM_PLAYERS:
                conn, addr = s.accept()
                print(f"[INFO] Client {len(players) + 1} connected from {addr}")
                send_package(conn, MessageTypes.S_MESSAGE, "Connected. You may have to wait some time.")
                players.append((conn, addr))

            p1_conn, p1_addr = players[0]
            p2_conn, p2_addr = players[1]

            print(f"[INFO] {NUM_PLAYERS} clients are connected. Starting game...")

            try:
                run_two_player_game_online(p1_conn, p2_conn)

                send_package(p1_conn, MessageTypes.S_MESSAGE, "Game over. Please wait 5 seconds for the next game...")
                send_package(p2_conn, MessageTypes.S_MESSAGE, "Game over. Please wait 5 seconds for the next game...")
                time.sleep(5)

                send_package(p1_conn, MessageTypes.PROMPT, "Want to play again ? (yes/no)")
                send_package(p2_conn, MessageTypes.PROMPT, "Want to play again ? (yes/no)")

                response1 = receive_package(p1_conn).get("coord").upper()
                response2 = receive_package(p2_conn).get("coord").upper()

                if response1 == "YES" and response2 == "YES":
                    print("[INFO] Starting game again with the same players.")
                else:
                    print("[INFO] At least one player has declined. Closing the appropriate connections.")
                    if response1 != "YES":
                        p1_conn.close()
                        players.remove((p1_conn, p1_addr))
                    if response2 != "YES":
                        p2_conn.close()
                        players.remove((p2_conn, p2_addr))
                    for player in players:
                        send_package(player[0], MessageTypes.S_MESSAGE, "Please wait whilst we find another player...")

            except Exception as e:
                print(f"[ERROR] Exception during game: {e}")
                print("[INFO] Closing connections...")
                p1_conn.close()
                p2_conn.close()
                break


if __name__ == "__main__":
    main()
