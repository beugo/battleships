import socket
import threading
import time
from battleship import BOARD_SIZE, Board, run_two_player_game_online
from utils import *

HOST = '127.0.0.1'
PORT = 5000
NUM_PLAYERS = 2

players = []

class Player:
    def __init__(self, conn, addr):
        self.conn = conn
        self.addr = addr
        self.playing = False

def connect_with_clients(s: socket.socket):
    s.bind((HOST, PORT))
    s.listen(NUM_PLAYERS)
    while True:
        while len(players) < NUM_PLAYERS:
            conn, addr = s.accept()
            print(f"[INFO] Client {len(players) + 1} connected from {addr}")
            players.append(Player(conn, addr))
            if len(players) < NUM_PLAYERS:
                send_package(conn, MessageTypes.WAITING, "Waiting for an opponent to connect...")

def play_game(p1: Player, p2: Player):
    try:
        run_two_player_game_online(p1.conn, p2.conn)

        send_package(p1.conn, MessageTypes.S_MESSAGE, "Game over. Please wait 5 seconds for the next game...")
        send_package(p2.conn, MessageTypes.S_MESSAGE, "Game over. Please wait 5 seconds for the next game...")
        time.sleep(5)

        send_package(p1.conn, MessageTypes.PROMPT, "Want to play again ? (yes/no)")
        send_package(p2.conn, MessageTypes.PROMPT, "Want to play again ? (yes/no)")

        response1 = receive_package(p1.conn).get("coord").upper()
        response2 = receive_package(p2.conn).get("coord").upper()

        if response1 == "YES" and response2 == "YES":
            print("[INFO] Starting game again with the same players.")
        else:
            print("[INFO] At least one player has declined. Closing the appropriate connections.")
            if response1 != "YES":
                p1.conn.close()
                players.remove(p1)
            if response2 != "YES":
                p2.conn.close()
                players.remove(p2)
            for player in players:
                send_package(player.conn, MessageTypes.S_MESSAGE, "Please wait whilst we find another player...")

    except Exception as e:
        print(f"[ERROR] Exception during game: {e}")
        print("[INFO] Closing connections...")
        p1.conn.close()
        p2.conn.close()
        if p1 in players: players.remove(p1)
        if p2 in players: players.remove(p2)

def main():
    print(f"[INFO] Server listening on {HOST}:{PORT}")

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:

        client_connecting_thread = threading.Thread(target=connect_with_clients, args=(s,), daemon=True)
        client_connecting_thread.start()

        try:
            while True:
                if len(players) >= 2:
                    p1 = players[0]
                    p2 = players[1]

                    print(f"[INFO] Two players ready. Starting game thread.")

                    play_game(p1, p2)
                time.sleep(1)
        except KeyboardInterrupt:
            print(f"[INFO] Server shutting down.")

if __name__ == "__main__":
    main()
