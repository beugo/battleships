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
all_player_logins = {}

# ─── Player Class ────────────────────────────────────────────────────────────
class Player:
    def __init__(self, conn, addr):
        self.conn = conn
        self.addr = addr
        self.username = None
        self.pin = None
        self.my_turn = False
        self.latest_coord = None
        self.msg_lock = threading.Lock()
        self.connected = True

# ─── Game State Class ────────────────────────────────────────────────────────
class GameState:
    def __init__(self, p1_addr, p2_addr, board1 = None, board2 = None, current_player = None):
        self.players = {p1_addr, p2_addr} # Stores the addresses of the two players in this game state.
        self.board1 = board1
        self.board2 = board2
        self.current_player = current_player
    
    def update_gamestate(self, board1, board2, current_player):
        self.board1 = board1
        self.board2 = board2
        self.current_player = current_player

    def replace_addr(self, old, new):
        """Update internal sets when a player reconnects with a
        different (ip,port)."""
        if old in self.players:
            self.players.remove(old)
            self.players.add(new)
        if self.current_player == old:
            self.current_player = new


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
                
                threading.Thread(target=client_handler, args=(player,), daemon=True).start()
                print(f"[INFO] A client-handler has been assigned to {addr}, now trying to log this client in.")
                
        time.sleep(0.5)

# ─── Client Handler Thread ────────────────────────────────────────────────────
def client_handler(player: Player):
    """
    1) Ask the client to log in (username).
    2) Once logged in, push them onto player_queue.
    3) Then sit in a loop:
       • CHAT  -> broadcast immediately.
       • In-game commands -> accept only if this player is one of the first two
         in player_queue **and** it is currently their turn.
       • Anything else -> polite 'wait your turn' message.
    """
    global running, current_state

    try:
        # ── 1.  Login / Register ────────────────────────────────────────────
        while running and player.username is None and player.pin is None:
            package = receive_package(player.conn)
            if not package:
                raise ConnectionError("Lost during login")

            cmd, username = package.get("coord").split(maxsplit=1)

            if cmd == "REGISTER":
                if username in all_player_logins:
                    send_package(player.conn, MessageTypes.S_MESSAGE, "USERNAME_TAKEN")
                    continue
                send_package(player.conn, MessageTypes.S_MESSAGE, "USERNAME_OK")
                pin_package = receive_package(player.conn)
                pin = pin_package.get("coord").split()[-1]
                all_player_logins[username] = pin
                send_package(player.conn, MessageTypes.S_MESSAGE, "REGISTRATION_SUCCESS")
                player.username, player.pin = username, pin


            elif cmd == "LOGIN":
                if username not in all_player_logins:
                    send_package(player.conn, MessageTypes.S_MESSAGE, "USER_NOT_FOUND")
                    continue
                send_package(player.conn, MessageTypes.S_MESSAGE, "USERNAME_OK")
                for _ in range(3):
                    pin_package = receive_package(player.conn)
                    pin_try = pin_package.get("coord").split()[-1]
                    if pin_try == all_player_logins[username]:
                        send_package(player.conn, MessageTypes.S_MESSAGE, "LOGIN_SUCCESS")
                        player.username, player.pin = username, pin_try
                        break
                    send_package(player.conn, MessageTypes.S_MESSAGE, "LOGIN_FAILURE")
                else:
                    continue
            

            else:
                send_package(player.conn, MessageTypes.S_MESSAGE, "You must either login or register before joining")

        role_msg = (
            "Success! Waiting for your opponent…" if len(player_queue) < 2
            else f"You are number {len(player_queue)-1} in the queue - you'll see live updates."
        )
        send_package(player.conn, MessageTypes.WAITING, role_msg)



        # ── 2.  Join the queue ──────────────────────────────────────────────
        with t_lock:
            player_queue.append(player)

        # ── 3.  Main receive loop ───────────────────────────────────────────
        while running and player.connected:
            package = receive_package(player.conn)
            if not package:
                raise ConnectionError("disconnect")

            p_type = package.get("type")

            # --- CHAT ------------------------------------------------------
            if p_type == "chat":
                msg = f"{player.username}: {package.get('msg')}"
                send_announcement(MessageTypes.CHAT, msg)
                continue

            # --- NON-CHAT (commands / coords) -----------------------------
            with t_lock:
                actively_playing = current_state and player.addr in current_state.players
                placement_phase  = actively_playing and (
                    current_state and (current_state.board1 is None or current_state.board2 is None)
                )
                turn_phase       = current_state and current_state.current_player == player.addr

            # NEW ─ let prompts such as ship-placement and rematch through
            accepting_prompt = player.my_turn       

            if not (placement_phase or turn_phase or accepting_prompt):
                send_package(player.conn, MessageTypes.S_MESSAGE,
                            "Please wait, it isn't your turn.")
                continue

            # It's their turn and they sent a coord
            coord = package.get("coord")
            if coord:
                with player.msg_lock:
                    player.latest_coord = coord
            else:
                send_package(player.conn, MessageTypes.S_MESSAGE,
                             "Invalid move payload.")

    except ConnectionError:
        print(f"[INFO] {player.addr} disconnected.")
    finally:
        player.connected = False
        # Remove from queue if they’re still there
        with t_lock:
            if player in player_queue:
                player_queue.remove(player)
        resend_queue_pos()
        try:
            player.conn.close()
        except:
            pass

# ─── Match & Rematch Logic ───────────────────────────────────────────────────
def start_match(p1: Player, p2: Player, current_state: GameState) -> str:
    """
    Start a single match between p1 and p2. Returns 'done' or 'early_exit'.
    """

    game_starting_message = f"Starting match between {p1.username} and {p2.username}"

    print("[INFO] " + game_starting_message)
    send_announcement(MessageTypes.WAITING, game_starting_message)

    time.sleep(2)

    return run_two_player_game_online(p1, p2, current_state, notify_spectators)

def ask_for_rematch(p1: Player, p2: Player,
                    timeout: float = 15.0) -> tuple[str, str]:
    """
    Prompt both players for a rematch.
    Uses the same COMMAND channel + latest_coord mechanism as gameplay.
    Anything but YES counts as NO. 15 s overall timeout.
    """
    # 1) prompt
    for p in (p1, p2):
        try:
            send_package(p.conn, MessageTypes.PROMPT,
                         "Play again? (yes/no)")
        except ConnectionError:
            pass

    # 2) collect replies
    replies = {}
    for p in (p1, p2):
        try:
            ans = wait_for_message(p, timeout=timeout,
                                   allowed=("YES", "NO"))
        except ConnectionError:
            ans = None
        replies[p] = "YES" if ans == "YES" else "NO"

        try:
            send_package(p.conn, MessageTypes.WAITING,
                         "Waiting for your opponent…")
        except ConnectionError:
            pass

    return replies[p1], replies[p2]

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

    print(f"[INFO] Removing disconnected player {loser.username}")

    with t_lock:
        if loser in player_queue:
            player_queue.remove(loser)

    for _ in range(0, 30):
        with t_lock:
            for p in player_queue:
                if p.username == loser.username:
                    player_queue.remove(p)
                    idx = 0 if p1.username == loser.username else 1
                    player_queue.insert(idx, p)
                    if current_state is not None:
                        current_state.replace_addr(loser.addr, p.addr)
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
