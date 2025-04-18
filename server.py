"""
server.py

Serves a single-player Battleship session to one connected client.
Game logic is handled entirely on the server using battleship.py.
Client sends FIRE commands, and receives game feedback.

TODO: For Tier 1, item 1, you don't need to modify this file much. 
The core issue is in how the client handles incoming messages.
However, if you want to support multiple clients (i.e. progress through further Tiers), you'll need concurrency here too.
"""

import socket
import threading
import select
from battleship import run_single_player_game_online

HOST = '127.0.0.1'
PORT = 5000
NUM_PLAYERS = 2

def handle_client(conn, addr):

    try:
        with conn:
            rfile = conn.makefile('r')
            wfile = conn.makefile('w')
            run_single_player_game_online(rfile, wfile)

    except Exception as e:
        print(f"[ERROR] Unexpected error with client {addr}: {e}")

    finally:
        print(f"[INFO] Client from address {addr} disconnected.")

def main():

    print(f"[INFO] Server listening on {HOST}:{PORT}")

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((HOST, PORT))
        s.listen(2)

        players = []

        while len(players) < NUM_PLAYERS:
            player = s.accept()
            players.append(player)
            print(f"[INFO] Client {len(players)} connected from {player[1]}")

        print(f"[INFO] {NUM_PLAYERS} clients have connected. Starting game...")

        for player in players:
            client_thread = threading.Thread(target=handle_client, args=(player[0], player[1]))
            client_thread.start()

if __name__ == "__main__":
    main()