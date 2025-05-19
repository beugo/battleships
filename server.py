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
        self.seq = 0

# ─── Game State Class ────────────────────────────────────────────────────────
class GameState:
    def __init__(self, p1: "Player", p2: "Player"):
        self.players        = {p1.username, p2.username}      
        self.boards         = {p1.username: None,             
                               p2.username: None}
        self.current_player = None            

    # convenience helpers
    def board_of(self, user):      return self.boards[user]
    def set_board(self, user, b):  self.boards[user] = b

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
            package = receive_package(player)
            if not package:
                raise ConnectionError("Lost during login")

            cmd, username = package.get("coord").split(maxsplit=1)

            if cmd == "REGISTER":
                if username in all_player_logins:
                    send_package(player, MessageTypes.S_MESSAGE, "USERNAME_TAKEN")
                    continue
                send_package(player, MessageTypes.S_MESSAGE, "USERNAME_OK")
                pin_package = receive_package(player)
                pin = pin_package.get("coord").split()[-1]
                all_player_logins[username] = pin
                send_package(player, MessageTypes.S_MESSAGE, "REGISTRATION_SUCCESS")
                player.username, player.pin = username, pin


            elif cmd == "LOGIN":
                if username not in all_player_logins:
                    send_package(player, MessageTypes.S_MESSAGE, "USER_NOT_FOUND")
                    continue
                send_package(player, MessageTypes.S_MESSAGE, "USERNAME_OK")
                for _ in range(3):
                    pin_package = receive_package(player)
                    pin_try = pin_package.get("coord").split()[-1]
                    if pin_try == all_player_logins[username]:
                        send_package(player, MessageTypes.S_MESSAGE, "LOGIN_SUCCESS")
                        player.username, player.pin = username, pin_try
                        break
                    send_package(player, MessageTypes.S_MESSAGE, "LOGIN_FAILURE")
                else:
                    continue
            

            else:
                send_package(player, MessageTypes.S_MESSAGE, "You must either login or register before joining")

        role_msg = (
            "Success! Waiting for your opponent…" if len(player_queue) < 2
            else f"You are number {len(player_queue)-1} in the queue - you'll see live updates."
        )
        send_package(player, MessageTypes.WAITING, role_msg)



        # ── 2.  Join the queue ──────────────────────────────────────────────
        with t_lock:
            player_queue.append(player)

        # ── 3.  Main receive loop ───────────────────────────────────────────
        while running and player.connected:
            package = receive_package(player)
            if not package:
                raise ConnectionError("disconnect")

            p_type = package.get("type")

            # --- CHAT ------------------------------------------------------
            if p_type == "chat":
                msg = f"{player.username}: {package.get('msg')}"
                broadcast(msg=msg, msg_type=MessageTypes.CHAT)
                continue

            # --- NON-CHAT (commands / coords) -----------------------------
            with t_lock:
                actively_playing = current_state and player.username in current_state.players
                placement_phase  = actively_playing and (
                    current_state.board_of(player.username) is None
                )
                turn_phase       = current_state and current_state.current_player == player.username

            accepting_prompt = player.my_turn       

            if not (placement_phase or turn_phase or accepting_prompt):
                send_package(player, MessageTypes.S_MESSAGE,
                            "Please wait, it isn't your turn.")
                continue

            # It's their turn and they sent a coord
            coord = package.get("coord")
            if coord:
                with player.msg_lock:
                    player.latest_coord = coord
            else:
                send_package(player, MessageTypes.S_MESSAGE,
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
    broadcast(msg=game_starting_message, msg_type=MessageTypes.S_MESSAGE)

    time.sleep(2)

    return run_two_player_game_online(p1, p2, current_state, notify_spectators, broadcast)

def handle_connection_lost(p1, p2):
    """
    Probes both p1 and p2 to find who left (loser) and who stayed (winner).
    Over the next 30 seconds, once every second (roughly), we look through the player queue.
    If the player who left is in the queue, we insert them into their spot, and return true.
    If they are not found in time, the queue remains unchanged and we return false.
    """
    winner, loser = determine_winner_and_loser(p1, p2)

    send_package(
        winner, 
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

def disconnect_player(player: Player, message: str = "You are being disconnected..."):
    with t_lock:
        if player in player_queue:
            player_queue.remove(player)
    try:
        send_package(player, MessageTypes.SHUTDOWN, message)
        player.conn.close()
    except:
        pass # doesn't really matter if we can't reach the client to shut them down


# ─── Announcements ─────────────────────────────────────────────────────
def _safe_send(player, *args):
    try:
        send_package(player, *args)
        return True
    except ConnectionError:
        with t_lock:
            if player in player_queue:
                player_queue.remove(player)
        print(f"[INFO] Removed unreachable player {player.username}")
        return False
    
def broadcast(
        *,
        msg=None,
        msg_type=MessageTypes.S_MESSAGE,
        board=None,
        show_ships=False,
        spectators_only=False):
    """
    Fan-out a message (and optionally a board) to the desired audience.

    Parameters
    ----------
    msg_type     - Enum code (S_MESSAGE, BOARD, WAITING, …).
    msg              - Text payload (ignored for BOARD unless you want both).
    board / show_ships
                     - If board is given we send a MessageTypes.BOARD first,
                       using the supplied `show_ships` flag.
    spectators_only  - If True we skip the first two queue slots.
    """
    with t_lock:
        targets = player_queue[2:] if spectators_only else player_queue[:]

    for p in list(targets):
        if board is not None:
            _safe_send(p, MessageTypes.BOARD, board, show_ships)
        if msg is not None:
            _safe_send(p, msg_type, msg)

def notify_spectators(defender_board, result, ships_sunk, attacker):
    """
    Computes the right message(s) then delegates to broadcast().
    """
    if ships_sunk:
        broadcast(
            msg=f"{attacker.username} has won!",
            msg_type=MessageTypes.S_MESSAGE,
            spectators_only=True
        )
        return

    if result == "timeout":
        text = f"{attacker.username} timed out; turn skipped."
    else:
        verb = {"hit": "HIT", "miss": "MISSED", "already_shot": "ALREADY SHOT"}[result]
        text = f"{attacker.username} has {verb} the defender."

    # message + updated defender board
    broadcast(msg=text,
              msg_type=MessageTypes.S_MESSAGE,
              board=defender_board,
              show_ships=False,
              spectators_only=True)

    # finally refresh queue positions (spinner)
    resend_queue_pos()

def resend_queue_pos():
    with t_lock:
        spectators = list(player_queue[2:])

    position = 1
    for spec in spectators:
        if _safe_send(
            spec,
            MessageTypes.WAITING,
            f"You are number {position} in the queue"
        ):
            position += 1


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

            if (current_state is None) or (current_state.players != {p1.username, p2.username}): # (no game) OR (different players)
                current_state = GameState(p1, p2)

            # Play a match
            result, winner = start_match(p1, p2, current_state)
            conn_lost = (result == "connection_lost")
            conn_found = conn_lost and handle_connection_lost(p1, p2)

            if not conn_found:
                current_state = None

            if conn_lost:
                continue

            # this logic will execute if the game successfully finishes
            loser = p2 if winner is p1 else p1
            with t_lock:
                for player in (p1, p2):
                    if player in player_queue:
                        player_queue.remove(player)

                player_queue.insert(0, winner)
                player_queue.append(loser)

            broadcast(msg="A new game will start soon!", msg_type=MessageTypes.WAITING)
            resend_queue_pos()
            time.sleep(3)

    except KeyboardInterrupt:
        print("[INFO] Ctrl+C received. Shutting down...")
        running = False

        # Notify all waiting/incoming players
        broadcast(msg="Server is shutting down.", msg_type=MessageTypes.SHUTDOWN)
        # Also notify those not yet in queue
        with t_lock:
            for conn, addr in incoming_connections:
                try:
                    temp_p = Player(conn, addr)
                    send_package(temp_p, MessageTypes.SHUTDOWN, "Server is shutting down.")
                    conn.close()
                except:
                    pass

    finally:
        server_sock.close()
        print("[INFO] Server socket closed. Exiting.")


if __name__ == "__main__":
    main()