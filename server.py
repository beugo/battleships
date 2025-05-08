import socket
import threading
import time
from battleship import run_two_player_game_online
from utils import *

HOST = '127.0.0.1'
PORT = 5000
NUM_PLAYERS = 2

players = []
players_lock = threading.Lock()

class Player:
    def __init__(self, conn, addr):
        self.conn = conn
        self.addr = addr

def accept_clients(server_sock: socket.socket):
    server_sock.bind((HOST, PORT))
    server_sock.listen()
    print(f"[INFO] Server listening on {HOST}:{PORT}")
    while True:
        conn, addr = server_sock.accept()
        player = Player(conn, addr)
        with players_lock:
            players.append(player)
            idx = len(players)
        print(f"[INFO] Client {idx} connected from {addr}")
        # If they’re the first of two, tell them to wait
        if idx < NUM_PLAYERS:
            send_package(conn, MessageTypes.WAITING, "Waiting for an opponent to connect...")

def handle_match(p1: Player, p2: Player):
    """
    Run exactly one match between p1 and p2, then dispatch
    based on how it returned.
    """
    result = run_two_player_game_online(p1.conn, p2.conn)
    if result == "done":
        handle_rematch(p1, p2)
    elif result == "early_exit":
        handle_early_exit(p1, p2)

def handle_rematch(p1: Player, p2: Player):
    """
    Ask both players if they want a rematch.
    If both say YES, recurse back into handle_match.
    Otherwise shut down any 'no' players and leave
    survivors in the lobby.
    """
    # give players 5s to see final S_MESSAGE
    time.sleep(5)

    # ask each
    send_package(p1.conn, MessageTypes.PROMPT, "Want to play again? (yes/no)", None)
    send_package(p2.conn, MessageTypes.PROMPT, "Want to play again? (yes/no)", None)

    resp1 = receive_package(p1.conn).get("coord", "").strip().upper()
    resp2 = receive_package(p2.conn).get("coord", "").strip().upper()

    if resp1 == "YES" and resp2 == "YES":
        print("[INFO] Both want rematch — starting again")
        handle_match(p1, p2)
        return

    print("[INFO] Rematch declined by at least one player.")
    # shut down those who said no
    for player, resp in ((p1, resp1), (p2, resp2)):
        if resp != "YES":
            send_package(player.conn, MessageTypes.QUIT, "Bye! Thanks for playing.")
            player.conn.close()
            with players_lock:
                players.remove(player)

    # anyone left stays in lobby
    with players_lock:
        for survivor in players:
            send_package(survivor.conn, MessageTypes.S_MESSAGE, "Waiting for a new opponent...")

def handle_early_exit(p1: Player, p2: Player):
    """
    One client bailed mid-match. Figure out who, remove them,
    and let the other wait for someone new.
    """
    # (You could have run_two_player_game_online tell you *which* one exited,
    #  but if not, you can detect via socket errors on send_package.)
    # Here we’ll try both:
    for exiting, survivor in ((p1, p2), (p2, p1)):
        try:
            send_package(exiting.conn, MessageTypes.S_MESSAGE, "")
        except:
            print(f"[INFO] Detected exit of {exiting.addr}")
            # clean up exit
            try: exiting.conn.close()
            except: pass
            with players_lock:
                if exiting in players:
                    players.remove(exiting)
            # tell survivor
            send_package(survivor.conn, MessageTypes.WAITING,
                         "Your opponent disconnected. Waiting for someone new...")
            return

def main():
    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    accept_thread = threading.Thread(target=accept_clients,
                                     args=(server_sock,), daemon=True)
    accept_thread.start()

    try:
        while True:
            with players_lock:
                ready = len(players) >= NUM_PLAYERS
                if ready:
                    p1, p2 = players[0], players[1]
                else:
                    p1 = p2 = None

            if p1 and p2:
                print("[INFO] Two players ready — launching match thread")
                handle_match(p1, p2)
            else:
                time.sleep(1)

    except KeyboardInterrupt:
        print("[INFO] Server shutting down via Ctrl+C")
        with players_lock:
            for p in players:
                try:
                    send_package(p.conn, MessageTypes.QUIT,
                                 "Server is shutting down.")
                    p.conn.close()
                except:
                    pass
    finally:
        server_sock.close()

if __name__ == "__main__":
    main()
