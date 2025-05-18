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
current_state = None

# ─── Player Class ────────────────────────────────────────────────────────────
class Player:
    def __init__(self, conn, addr):
        self.conn = conn
        self.addr = addr
        self.username = None
        self.my_turn = False
        self.latest_coord = None
        self.msg_lock = threading.Lock()
        self.connected = True

# ─── Game State Class ────────────────────────────────────────────────────────
class GameState:
    def __init__(self, p1, p2, board1 = None, board2 = None, current_player = None):
        self.players = {p1, p2} # Stores the addresses of the two players in this game state.
        self.board1 = board1
        self.board2 = board2
        self.current_player = current_player
    
    def update_gamestate(self, board1, board2, current_player):
        self.board1 = board1
        self.board2 = board2
        self.current_player = current_player


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
                    queue_num = len(player_queue) - 1
                    if queue_num > 0:
                        send_package(
                            player.conn,
                            MessageTypes.WAITING,
                            f"You are number {queue_num} in the queue"
                        )
                except (BrokenPipeError, ConnectionResetError, OSError) as e:
                    print(f"[INFO] Player at {addr} has disconnected before joining the queue")
                    continue
                
                player_queue.append(player)
                threading.Thread(target=listen_to_client, args=(player,), daemon=True).start()
                print(f"[INFO] Added {addr} to player_queue (position {len(player_queue)})")
                
        time.sleep(0.5)

# ─── Client Listening Thread ─────────────────────────────────────────────────
def listen_to_client(player):
    """
    Ask the client for their username.
    Constantly listen to a given client.
    Broadcast CHAT message to all.
    Store other commands for use in the game at the appropriate time.
    """
    try:
        while running:
            send_package(player.conn, MessageTypes.PROMPT, "Please enter your username")
            package = receive_package(player.conn)

            if package.get("type") == "chat":
                send_package(player.conn, MessageTypes.S_MESSAGE, "You are not able to chat until you have a username. Please try again.")
                continue

            desired_user = package.get("coord")
            with t_lock:
                if any(p.username == desired_user for p in player_queue):
                    send_package(player.conn, MessageTypes.S_MESSAGE, "Another player already has this username. Please try again.")
                    continue
    
            player.username = desired_user
            send_package(player.conn, MessageTypes.S_MESSAGE, f"Username set to: {player.username}")
            break
        
        while running:
            package = receive_package(player.conn)
            if package.get("type") == "chat":
                msg = f"{player.username}: {package.get('msg')}"
                send_announcement(MessageTypes.CHAT, msg)
            elif player.my_turn and player.latest_coord is None:
                with player.msg_lock:
                    player.latest_coord = package.get("coord")
            else:
                send_package(player.conn, MessageTypes.S_MESSAGE, "Please wait for your turn.")
            
    except ConnectionError:
        print(f"[INFO] Could not send/receive from {player.addr}.")
        player.connected = False
        try:
            if player.username is None:
                with t_lock:
                    player_queue.remove(player)
                resend_queue_pos()
                print(f"[INFO] {player.addr} left before choosing their username. Releasing them from the queue.")

            elif (player_queue.index(player) > 1 or current_state is None):
                with t_lock:
                    player_queue.remove(player)
                resend_queue_pos()
                print(f"[INFO] Leaving player ({player.addr}) were not in the game yet. Released them from the queue.")
        except ValueError:
            print(f"[INFO] {player.addr} was already removed from the queue.")

# ─── Match & Rematch Logic ───────────────────────────────────────────────────
def start_match(p1: Player, p2: Player, current_state: GameState) -> str:
    """
    Start a single match between p1 and p2. Returns 'done' or 'early_exit'.
    """

    game_starting_message = f"Starting match between {p1.addr} and {p2.addr}"

    print("[INFO] " + game_starting_message)
    send_announcement(MessageTypes.WAITING, game_starting_message)

    return run_two_player_game_online(p1, p2, current_state, notify_spectators)

def ask_for_rematch(p1: Player, p2: Player, timeout: float = 15.0) -> tuple[str, str]:
    """
    Prompt p1 and p2 simultaneously for a rematch.
    Each has `timeout` seconds to reply with "YES" or "NO".
    As soon as one replies, they get a WAITING message.
    Any socket error or timeout yields "NO".
    Returns (resp1, resp2) in uppercase.
    """
    players = [p1, p2]
    responses = {p1: "NO", p2: "NO"}

    for p in players:
        try:
            send_package(
                p.conn,
                MessageTypes.PROMPT,
                "Want to play again? (yes/no)",
            )
        except ConnectionError:
            print(f"[INFO] Could not prompt {p.addr}, defaulting to NO")

    start = time.time()

    for p in players:
        remaining = timeout - (time.time() - start)
        if remaining <= 0:
            continue

        p.conn.settimeout(remaining)
        try:
            pkg = receive_package(p.conn)
            resp = pkg.get("coord", "").strip().upper()
            if resp not in ("YES", "NO"):
                resp = "NO"
        except socket.timeout:
            resp = "NO"
        except ConnectionError:
            resp = "NO"
        finally:
            # restore blocking mode
            p.conn.settimeout(None)

        responses[p] = resp

        try:
            send_package(
                p.conn,
                MessageTypes.WAITING,
                "Waiting for your opponent to decide..."
            )
        except ConnectionError:
            pass

    return (responses[p1], responses[p2])

def handle_connection_lost(p1, p2):
    """
    Probes both p1 and p2 to find who left (loser) and who stayed (winner).
    Over the next 30 seconds, once every second (roughly), we look through the player queue.
    If the player who left is in the queue, we insert them into their spot, and return true.
    If they are not found in time, the queue remains unchanged and we return false.
    """
    winner, loser = determine_winner_and_loser(p1, p2)

    send_package(
        winner.conn, 
        MessageTypes.WAITING, 
        "Your opponent has disconnected, please wait whilst we try to reconnect them."
    )

    print(f"[INFO] Removing disconnected player {loser.addr}")

    with t_lock:
        if loser in player_queue:
            player_queue.remove(loser)

    for _ in range(0, 30):
        with t_lock:
            for p in player_queue:
                if p.addr == loser.addr:
                    player_queue.remove(p)
                    player_queue.insert(0, p) if p1.addr == loser.addr else player_queue.insert(1, p)
                    return True
        time.sleep(1)

    return False

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

def notify_spectators(defender_board, result, ships_sunk, attacker):
    """
    Send live updates to any spectators waiting beyond the first two in queue.

    - If ships_sunk is True, announce victory and return immediately.
    - If result == "timeout", tell them whose turn was skipped.
    - Otherwise (hit/miss/already_shot), announce the event.
    - In all non-end cases, send the defender's updated board next.
    - Finally, send a WAITING spinner message with their queue position.
    """
    with t_lock:
        spectators = player_queue[2:]

    for idx, spec in enumerate(spectators, start=1):
        try:
            # 1) Header
            send_package(spec.conn, MessageTypes.S_MESSAGE, "Incoming Live Game Update:")

            # 2) End-of-game?
            if ships_sunk:
                send_package(
                    spec.conn,
                    MessageTypes.S_MESSAGE,
                    f"{attacker.addr} has won!"
                )
                return

            # 3) Timeout
            if result == "timeout":
                send_package(
                    spec.conn,
                    MessageTypes.S_MESSAGE,
                    f"{attacker.addr} timed out; turn skipped."
                )
            else:
                # 4) Hit / Miss / Already shot
                verb = {
                    "hit": "has HIT the defender.",
                    "miss": "has MISSED the defender.",
                    "already_shot": "has ALREADY SHOT at the defender."
                }.get(result)
                if verb:
                    send_package(
                        spec.conn,
                        MessageTypes.S_MESSAGE,
                        f"{attacker.addr} {verb}"
                    )

            # 5) Send the defender's updated board
            if defender_board is not None:
                send_package(spec.conn, MessageTypes.BOARD, defender_board, False)

            # 6) Spinner / queue position
            send_package(
                spec.conn,
                MessageTypes.WAITING,
                f"You are number {idx} in the queue"
            )

        except ConnectionError:
            with t_lock:
                if spec in player_queue:
                    player_queue.remove(spec)

def resend_queue_pos():
    with t_lock:
        spectators = player_queue[2:]
    for i, spec in enumerate(spectators):
        try:
            send_package(spec.conn, MessageTypes.WAITING, f"You are number {i+1} in the queue")
        except ConnectionError:
            print(f"[INFO] Removing unreachable player {spec.addr} from queue")
            player_queue.remove(spec)

# ─── Main Server Loop ─────────────────────────────────────────────────────────
def main():
    global running, current_state

    # Set key
    derive_key('we_love_cs')

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

            if not (p1 and p2) or (p1.username == None or p2.username == None):
                time.sleep(1)
                continue

            if (current_state is None) or (current_state.players != {p1.addr, p2.addr}): # (no game) OR (different players)
                current_state = GameState(p1.addr, p2.addr)

            # Play a match
            result = start_match(p1, p2, current_state)
            conn_lost = (result == "connection_lost")
            conn_found = conn_lost and handle_connection_lost(p1, p2)

            if not conn_found:
                current_state = None

            if conn_lost:
                continue

            r1, r2 = ask_for_rematch(p1, p2)
            with t_lock:
                if r1 != "YES" and p1 in player_queue:
                    player_queue.remove(p1)
                if r2 != "YES" and p2 in player_queue:
                    player_queue.remove(p2)

            send_announcement(MessageTypes.WAITING, "A new game will start soon!")
            resend_queue_pos()
            time.sleep(3)

    except KeyboardInterrupt:
        print("[INFO] Ctrl+C received. Shutting down...")
        running = False

        # Notify all waiting/incoming players
        send_announcement(MessageTypes.SHUTDOWN, "Server is shutting down.")
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
