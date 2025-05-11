import socket
import threading
import time
from battleship import run_two_player_game_online
from utils import *

HOST = '127.0.0.1'
PORT = 5000
CLIENT_LIMIT = 5

players = []
players_lock = threading.Lock()
running = False

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
    for i in range(2, num_players): # Skip 1st and 2nd player as they are in the game already.
        player = players[i]
        send_package(player.conn, MessageTypes.WAITING, f"You are in position ({i-1}) of the queue to play battleship.")

def accept_clients(s: socket.socket):
    s.bind((HOST, PORT))
    s.listen()
    print(f"[INFO] Server listening on {HOST}:{PORT}")
    while True:
        while len(players) < CLIENT_LIMIT:
            conn, addr = s.accept()
            player = Player(conn, addr)
            with players_lock:
                players.append(player)
                index = len(players)
            print(f"[INFO] Client {index} connected from {addr}")
            send_queue_pos()

def handle_match(p1: Player, p2: Player):
    """
    Run exactly one match between p1 and p2, then dispatch
    based on how it returned.
    """
    global running
    for opp1, opp2 in ((p1, p2), (p2, p1)):
        send_package(opp1.conn, MessageTypes.S_MESSAGE, f"Connected. You are playing against: {opp2.addr}") #TODO: We will change this to usernames when we need to.
    result = run_two_player_game_online(p1.conn, p2.conn)
    if result == "done":
        handle_rematch(p1, p2)
    elif result == "early_exit":
        handle_early_exit(p1, p2)
    running = False

def handle_rematch(p1: Player, p2: Player):
    """
    Ask both players if they want a rematch.
    If both say YES, recurse back into handle_match.
    Otherwise shut down any 'no' players and leave
    survivors in the lobby.
    """
    time.sleep(3)

    # ask each
    send_package(p1.conn, MessageTypes.PROMPT, "Want to play again? (yes/no)", None)
    send_package(p2.conn, MessageTypes.PROMPT, "Want to play again? (yes/no)", None)

    resp1 = receive_package(p1.conn).get("coord", "").strip().upper() # need to account for client disconnecting here
    resp2 = receive_package(p2.conn).get("coord", "").strip().upper()

    if resp1 == "YES" and resp2 == "YES":
        print("[INFO] Both want rematch — starting again")
        handle_match(p1, p2)
        return

    print("[INFO] Rematch declined by at least one player.")
    # shut down those who said no
    for player, resp in ((p1, resp1), (p2, resp2)):
        if resp != "YES":
            send_package(player.conn, MessageTypes.SHUTDOWN, "Bye! Thanks for playing.")
            player.conn.close()
            with players_lock:
                remove_player(player) 

    with players_lock:
        for survivor in players:
            send_package(survivor.conn, MessageTypes.WAITING, "Waiting for a new opponent...")

def handle_early_exit(p1: Player, p2: Player):
    """
    One client bailed mid-match. Figure out who, remove them,
    and let the other wait for someone new.
    """
    for exiting, survivor in ((p1, p2), (p2, p1)):
        try:
            send_package(exiting.conn, MessageTypes.S_MESSAGE, "")
        except:
            print(f"[INFO] Detected exit of {exiting.addr}")
            # clean up exit
            try: exiting.conn.close()
            except: pass
            if exiting in players:
                remove_player(exiting)
            send_package(survivor.conn, MessageTypes.WAITING,
                         "Your opponent disconnected. Waiting for someone new...")
            return

def main():
    global running
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1) # so that there's no longer a cool down
    accept_thread = threading.Thread(target=accept_clients,
                                     args=(s,), daemon=True)
    accept_thread.start()

    try:
        while True:
            if not running:
                with players_lock:
                    ready = len(players) >= 2
                    if ready:
                        p1, p2 = players[0], players[1]
                    else:
                        p1 = p2 = None

                if p1 and p2:
                    print("[INFO] Two players ready — launching match thread")
                    game_thread = threading.Thread(target=handle_match, args=(p1, p2), daemon=True)
                    game_thread.start()
                    running = True
            time.sleep(1)

    except KeyboardInterrupt:
        print("[INFO] Server shutting down via Ctrl+C")
        with players_lock:
            for p in players:
                try:
                    send_package(p.conn, MessageTypes.SHUTDOWN,
                                 "Server is shutting down.")
                    p.conn.close()
                except:
                    print("[INFO] Was unable to send shutdown message to clients")
                    pass
    finally:
        s.close()

if __name__ == "__main__":
    main()
