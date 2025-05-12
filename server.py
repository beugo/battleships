import socket
import threading
import time
from battleship import run_two_player_game_online
from utils import send_package, receive_package, MessageTypes, safe_send

# ─── Shared State ───────────────────────────────────────────────────────────
incoming_connections = []   # List of (conn, addr)
player_queue = []           # List of Player instances
t_lock = threading.Lock()  # Protects both lists
running = False

# ─── Player Class ────────────────────────────────────────────────────────────
class Player:
    def __init__(self, conn, addr):
        self.conn = conn
        self.addr = addr

# ─── Receiver Thread ─────────────────────────────────────────────────────────
def receiver_thread(server_sock):
    """
    Accept new connections and append them to incoming_connections.
    """
    global running
    while running:
        try:
            conn, addr = server_sock.accept()
            with t_lock:
                incoming_connections.append((conn, addr))
            print(f"[INFO] New connection from {addr}")
        except OSError:
            break

# ─── Queue Maintainer Thread ─────────────────────────────────────────────────
def queue_maintainer_thread():
    """
    Move sockets from incoming_connections into the player_queue for matching.
    """
    global running
    while running:
        with t_lock:
            if incoming_connections:
                conn, addr = incoming_connections.pop(0)
                player = Player(conn, addr)
                player_queue.append(player)
                print(f"[INFO] Added {addr} to player_queue (position {len(player_queue)})")
        time.sleep(0.5)

# ─── Match & Rematch Logic ───────────────────────────────────────────────────
@safe_send
def start_match(p1: Player, p2: Player) -> str:
    """
    Start a single match between p1 and p2. Returns 'done' or 'early_exit'.
    """
    print(f"[INFO] Starting match between {p1.addr} and {p2.addr}")
    return run_two_player_game_online(p1.conn, p2.conn, spectator_broadcast)

@safe_send
def ask_for_rematch(p1: Player, p2: Player) -> tuple:
    """
    Ask both players if they want a rematch. Returns (resp1, resp2).
    """
    send_package(p1.conn, MessageTypes.PROMPT, "Want to play again? (yes/no)", None)
    send_package(p2.conn, MessageTypes.PROMPT, "Want to play again? (yes/no)", None)

    resp1 = receive_package(p1.conn).get("coord", "").strip().upper()
    resp2 = receive_package(p2.conn).get("coord", "").strip().upper()
    return resp1, resp2

# ─── Announcements ─────────────────────────────────────────────────────
def send_announcement(msg: str):
    """
    Broadcast a message to every player in the queue, removing any unreachable.
    """
    with t_lock:
        for player in list(player_queue):
            try:
                send_package(player.conn, MessageTypes.S_MESSAGE, msg)
            except ConnectionError:
                print(f"[INFO] Removing unreachable player {player.addr} from queue")
                player_queue.remove(player)

def spectator_broadcast(board1, board2, result, ships_sunk, attacker): # this is currently not safe sending
    with t_lock:
        for p in player_queue[:2]:
            if p.conn == attacker:
                attacker_address = p.addr
        spectators = player_queue[2:]
    for index, s in enumerate(spectators):
        send_package(s.conn, MessageTypes.S_MESSAGE, "Incoming Live Game Update:")
        if ships_sunk:
            send_package(s.conn, MessageTypes.S_MESSAGE, f"{attacker_address} has won.")
            return
        send_package(s.conn, MessageTypes.BOARD, board1, False)
        send_package(s.conn, MessageTypes.BOARD, board2, False)
        if result == "hit":
            send_package(s.conn, MessageTypes.S_MESSAGE, f"{attacker_address} has HIT the defender.")
        elif result == "miss":
            send_package(s.conn, MessageTypes.S_MESSAGE, f"{attacker_address} has MISSED the defender.")
        elif result == "already_shot":
            send_package(s.conn, MessageTypes.S_MESSAGE, f"{attacker_address} has ALREADY SHOT at the defenders position.")
        send_package(s.conn, MessageTypes.WAITING, f"You are in position ({index + 1}) of the queue to play battleship.")


# ─── Main Server Loop ─────────────────────────────────────────────────────────
def main():
    global running

    # Set up listening socket
    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_sock.bind(( '127.0.0.1', 5000 ))
    server_sock.listen()

    running = True
    print("[INFO] Server started, listening for connections...")

    # Start helper threads
    recv_thread = threading.Thread(target=receiver_thread, args=(server_sock,), daemon=True)
    queue_thread = threading.Thread(target=queue_maintainer_thread, daemon=True)
    recv_thread.start()
    queue_thread.start()

    try:
        # Main matchmaking loop
        while running:
            p1 = p2 = None
            with t_lock:
                if len(player_queue) >= 2:
                    p1 = player_queue.pop(0)
                    p2 = player_queue.pop(0)

            if not (p1 and p2):
                time.sleep(1)
                continue

            # Play a match
            result = start_match(p1, p2)

            if result == "early_exit":
                # Find who disconnected
                try:
                    send_package(p1.conn, MessageTypes.S_MESSAGE, "")
                    exiting, survivor = p2, p1
                except ConnectionError:
                    exiting, survivor = p1, p2

                print(f"[INFO] Player {exiting.addr} exited early. Looking for replacement...")
                # Pick next player
                with t_lock:
                    replacement = player_queue.pop(0) if player_queue else None
                if replacement:
                    print(f"[INFO] Replacing with {replacement.addr}")
                    # Start new match immediately
                    p1, p2 = survivor, replacement
                    continue
                else:
                    print("[INFO] No replacement available; ending match.")
                    continue

            # Normal finish: ask for rematch
            resp1, resp2 = ask_for_rematch(p1, p2)
            to_remove = []
            if resp1 != "YES":
                to_remove.append(p1)
            if resp2 != "YES":
                to_remove.append(p2)

            for player in to_remove:
                print(f"[INFO] Player {player.addr} declined rematch or disconnected.")

            # Announce to rest of queue
            send_announcement("A new game will start soon!")

            # Loop will pull next two players

    except KeyboardInterrupt:
        print("[INFO] Ctrl+C received. Shutting down...")
        running = False

        # Notify all waiting/incoming players
        send_announcement("Server is shutting down.")
        # Also notify those not yet in queue
        with t_lock:
            for conn, addr in incoming_connections:
                try:
                    send_package(conn, MessageTypes.SHUTDOWN, "Server is shutting down.")
                    conn.close()
                except:
                    pass

    finally:
        server_sock.close()
        print("[INFO] Server socket closed. Exiting.")

if __name__ == "__main__":
    main()
