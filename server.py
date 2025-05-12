import socket
import threading
import time
from battleship import run_two_player_game_online
from utils import *

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

                try:
                    send_package(
                        player.conn,
                        MessageTypes.WAITING,
                        f"You are number {len(player_queue) + 1} in the queue"
                    )
                except (BrokenPipeError, ConnectionResetError, OSError) as e:
                    print(f"[INFO] Player at {addr} has disconnected before joining the queue")
                    continue
                
                player_queue.append(player)
                print(f"[INFO] Added {addr} to player_queue (position {len(player_queue)})")
                
        time.sleep(0.5)

# ─── Match & Rematch Logic ───────────────────────────────────────────────────
def start_match(p1: Player, p2: Player) -> str:
    """
    Start a single match between p1 and p2. Returns 'done' or 'early_exit'.
    """
    print(f"[INFO] Starting match between {p1.addr} and {p2.addr}")
    return run_two_player_game_online(p1, p2, spectator_broadcast)

def ask_for_rematch(p: Player) -> str:
    """
    Ask both players if they want a rematch. Returns (resp).
    """
    try:
        send_package(p.conn, MessageTypes.PROMPT, "Want to play again? (yes/no)", None)
        response = receive_package(p.conn).get("coord", "").strip().upper()
        return response
    except (BrokenPipeError, ConnectionResetError, OSError):
        return "NO"

# ─── Announcements ─────────────────────────────────────────────────────
def send_announcement(message_type:MessageTypes, msg: str):
    """
    Broadcast a message to every player in the queue, removing any unreachable.
    """
    with t_lock:
        for player in list(player_queue):
            try:
                send_package(player.conn, message_type, msg)
            except ConnectionError:
                print(f"[INFO] Removing unreachable player {player.addr} from queue")
                player_queue.remove(player)

def spectator_broadcast(board1, board2, result, ships_sunk, attacker_conn):
    """
    Send live updates to any spectators waiting beyond the first two in queue.
    """
    with t_lock:
        # get current players for addr lookup
        active = player_queue[:2]
    # determine attacker address
    attacker_addr = next((p.addr for p in active if p.conn == attacker_conn), None)
    spectators = []
    with t_lock:
        if len(player_queue) > 2:
            spectators = player_queue[2:]

    for idx, spec in enumerate(spectators, start=1):
        try:
            send_package(spec.conn, MessageTypes.S_MESSAGE, "Incoming Live Game Update:")
            if ships_sunk:
                send_package(spec.conn, MessageTypes.S_MESSAGE, f"{attacker_addr} has won.")
                return
            send_package(spec.conn, MessageTypes.BOARD, board1, False)
            send_package(spec.conn, MessageTypes.BOARD, board2, False)
            msg = {
                'hit':   f"{attacker_addr} has HIT the defender.",
                'miss':  f"{attacker_addr} has MISSED the defender.",
                'already_shot': f"{attacker_addr} has ALREADY SHOT at the defender."
            }.get(result, '')
            if msg:
                send_package(spec.conn, MessageTypes.S_MESSAGE, msg)
            send_package(
                spec.conn,
                MessageTypes.WAITING,
                f"You are number {idx + 2} in the queue"
            )
        except ConnectionError:
            # prune disconnected spectator
            with t_lock:
                if spec in player_queue:
                    player_queue.remove(spec)


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
    threading.Thread(target=receiver_thread, args=(server_sock,), daemon=True).start()
    threading.Thread(target=queue_maintainer_thread, daemon=True).start()

    try:
        while running:
            with t_lock:
                if len(player_queue) >= 2:
                    p1, p2 = player_queue[0], player_queue[1]
                else:
                    p1 = p2 = None

            if not (p1 and p2):
                time.sleep(1)
                continue

            # Play a match
            result = start_match(p1, p2)

            if result == "connection_lost":
                # find and remove the disconnected player
                winner, loser = determine_winner_and_loser(p1, p2)

                send_package(
                    winner.conn, 
                    MessageTypes.WAITING, 
                    "Your opponent has disconnected, please wait for another"
                
                )
                print(f"[INFO] Removing disconnected player {loser.addr}")

                with t_lock:
                    if loser in player_queue:
                        player_queue.remove(loser)

                continue

            # Normal finish: ask both for rematch
            r1 = ask_for_rematch(p1)
            r2 = ask_for_rematch(p2)
            with t_lock:
                if r1 != "YES" and p1 in player_queue:
                    player_queue.remove(p1)
                if r2 != "YES" and p2 in player_queue:
                    player_queue.remove(p2)

            send_announcement("A new game will start soon!")
            time.sleep(1)

    except KeyboardInterrupt:
        print("[INFO] Ctrl+C received. Shutting down...")
        running = False

        # Notify all waiting/incoming players
        send_announcement(MessageTypes.S_MESSAGE, "Server is shutting down.")
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
