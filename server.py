import socket
import threading
import time
from battleship import BOARD_SIZE, Board, run_two_player_game_online
from utils import *

HOST = '127.0.0.1'
PORT = 5000
CLIENT_LIMIT = 5

players = []
players_lock = threading.Lock()

class Player:
    def __init__(self, conn, addr):
        self.conn = conn
        self.addr = addr

def remove_player(player):
    with players_lock:
        if player in players:
            try:
                player.conn.close()
            except:
                pass
            players.remove(player)
            print(f"[INFO] Player {player.addr} has been removed.")
            send_queue_pos()

def send_queue_pos():
    num_players = len(players)
    if num_players == 1:
        send_package(players[0].conn, MessageTypes.WAITING, "Please wait whilst we find you an opponent.")
        return
    for i in range(2, num_players): #Skip 1st and 2nd player as they are in the game already.
        player = players[i]
        send_package(player.conn, MessageTypes.S_MESSAGE, f"You are in position ({i-1}) of the queue to play battleship.")
        send_package(player.conn, MessageTypes.WAITING, "Waiting...")

def connect_with_clients(s: socket.socket):
    s.bind((HOST, PORT))
    s.listen(CLIENT_LIMIT)
    while True:
        while len(players) < CLIENT_LIMIT:
            conn, addr = s.accept()
            print(f"[INFO] Client connected from {addr}")
            with players_lock:
                players.append(Player(conn, addr))
            send_queue_pos()
        time.sleep(1)

def play_game(p1: Player, p2: Player):
    try:
        run_two_player_game_online(p1.conn, p2.conn)

        send_package(p1.conn, MessageTypes.S_MESSAGE, "Game over. Please wait 5 seconds for the next game...")
        send_package(p2.conn, MessageTypes.S_MESSAGE, "Game over. Please wait 5 seconds for the next game...")
        time.sleep(5)

        send_package(p1.conn, MessageTypes.PROMPT, "Want to play again ? (yes/no)", None)
        send_package(p2.conn, MessageTypes.PROMPT, "Want to play again ? (yes/no)", None)

        response1 = receive_package(p1.conn).get("coord").upper()
        response2 = receive_package(p2.conn).get("coord").upper()

        if response1 == "YES" and response2 == "YES":
            print("[INFO] Starting game again with the same players.")
        else:
            print("[INFO] At least one player has declined. Closing the appropriate connections.")
            if response1 != "YES":
                remove_player(p1)
            if response2 != "YES":
                remove_player(p2)
            
    except Exception as e:
        print(f"[ERROR] Exception during game: {e}")
        print("[INFO] Closing connections...")
        remove_player(p1)
        remove_player(p2)

def main():
    print(f"[INFO] Server listening on {HOST}:{PORT}")

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        client_connecting_thread = threading.Thread(target=connect_with_clients, args=(s,), daemon=True)
        client_connecting_thread.start()

        try:
            while True:
                if len(players) >= 2:
                    print(players)
                    p1 = players[0]
                    p2 = players[1]

                    print(f"[INFO] Two players ready. Starting game thread.")

                    play_game(p1, p2)
                time.sleep(1)
        except KeyboardInterrupt:
            print(f"[INFO] Server shutting down.")

if __name__ == "__main__":
    main()
