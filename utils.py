import time
import struct
import json
import enum
import zlib
import functools
from Crypto.Cipher import AES
import hashlib

# ─── Global Variables ──────────────────────────────────────────────────────────

key = None

# ─── Frame Class ───────────────────────────────────────────────────────────────

class Frame:
    def __init__(self):
        self.type = None
        self.length = 0
        self.checksum = 0
        self.nonce = b''
        self.jsonmsg = b''

    def pack(self):
        # H = unsigned short (2 bytes), I = unsigned int (4 bytes), s = bytes
        return struct.pack(f'HHI8s{len(self.jsonmsg)}s', self.type, self.length, self.checksum, self.nonce, self.jsonmsg)

    def unpack_header(self, header):
        self.type, self.length, self.checksum, self.nonce = struct.unpack_from(f'HHI8s', header)

# ─── Encryption: AES-CTR ────────────────────────────────────────────────────────

def derive_key(password):
    global key
    key = hashlib.sha256(password.encode()).digest()

def aes_ctr_encrypt(data):
    global key
    cipher = AES.new(key, AES.MODE_CTR)
    ct_bytes = cipher.encrypt(data)
    return (ct_bytes, cipher.nonce)

def aes_ctr_decrypt(ciphertext, nonce):
    global key
    cipher = AES.new(key, AES.MODE_CTR, nonce=nonce)
    pt = cipher.decrypt(ciphertext)
    return pt

# ─── Message Types ─────────────────────────────────────────────────────────────

class MessageTypes(enum.Enum):
    # server -> client
    RESULT = 2      # Game over
    BOARD = 3       # Board state (for placing or playing)
    PROMPT = 4      # Input request (e.g., place ship, fire)
    S_MESSAGE = 5   # General server messages
    WAITING = 6     # Show spinner / wait screen
    SHUTDOWN = 7    # Tell client to shut down

    # client -> server
    COMMAND = 0     # Send input (e.g., fire, place ship)
    CHAT = 1        # Send chat message to all other players

# ─── Message Builders ──────────────────────────────────────────────────────────

def _build_result(msg): return {"type": "result", "msg": msg}
def _build_board(show_ships, board): return {"type": "board", "ships": show_ships, "data": board}
def _build_prompt(msg): return {"type": "prompt", "msg": msg}
def _build_command(data): return {"type": "command", "coord": data}
def _build_s_message(msg): return {"type": "s_msg", "msg": msg}
def _build_waiting(msg): return {"type": "waiting", "msg": msg}
def _build_shutdown(msg): return {"type": "shutdown", "msg": msg}
def _build_chat(msg): return {"type": "chat", "msg": msg}

_builders = {
    MessageTypes.RESULT: _build_result,
    MessageTypes.BOARD: _build_board,
    MessageTypes.PROMPT: _build_prompt,
    MessageTypes.COMMAND: _build_command,
    MessageTypes.S_MESSAGE: _build_s_message,
    MessageTypes.WAITING: _build_waiting,
    MessageTypes.SHUTDOWN: _build_shutdown,
    MessageTypes.CHAT: _build_chat
}

def _build_json(type: MessageTypes, *args):
    return _builders[type](*args)

# ─── Board Creation ────────────────────────────────────────────────────────────

def _create_board(board, setup=False):
    output = ["  " + " ".join(str(i + 1).rjust(2) for i in range(board.size)) + '\n']
    for r in range(board.size):
        row_label = chr(ord('A') + r)
        row_str = " ".join(
            board.hidden_grid[r][c] if setup else board.display_grid[r][c]
            for c in range(board.size)
        )
        output.append(f"{row_label:2} {row_str}\n")
    output.append('\n')
    return "".join(output)

# ─── Reliable Receive ──────────────────────────────────────────────────────────

def _recv_exact(s, size):
    buffer = b''
    while len(buffer) < size:
        block = s.recv(size - len(buffer))
        if not block:
            raise ConnectionError("Connection closed.")
        buffer += block
    return buffer

# ─── Connection-Safe Send Wrapper ──────────────────────────────────────────────

def detects_lost_connection(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except (BrokenPipeError, ConnectionResetError, OSError) as e:
            return "connection_lost"
    return wrapper

# ─── Send and Receive Functions ────────────────────────────────────────────────

def send_package(s, type: MessageTypes, *args):
    """
    `s`: 'Player' or 'Server' object.
    """
    f = Frame()
    f.type = type.value

    # Create JSON dictionary
    if type == MessageTypes.BOARD:
        board_obj, show_ships = args
        board_string = _create_board(board_obj, show_ships)
        json_dict = _build_json(type, show_ships, board_string)
    else:
        json_dict = _build_json(type, *args)

    # Encrpyt
    plaintext = json.dumps({
        "data" : json_dict,
        "seq": s.seq
    }).encode()

    ciphertext, nonce = aes_ctr_encrypt(plaintext)
    f.jsonmsg = ciphertext
    f.nonce = nonce

    # Checksum
    f.length = len(f.jsonmsg)

    packed = f.pack()
    f.checksum = zlib.crc32(packed)
    packed = f.pack()

    # Send
    try:
        s.conn.sendall(packed)
        s.seq += 1
    except (BrokenPipeError, ConnectionResetError, OSError) as e:
        # wrap any socket failure as ConnectionError
        raise ConnectionError(f"send_package failed: {e}")
    
def receive_package(s) -> dict:
    """
    `s`: 'Player' or 'Server' object.
    """
    while True:
        f = Frame()
        try:
            # Receive and unpack
            header = _recv_exact(s.conn, 16)
            f.unpack_header(header)
            f.jsonmsg = _recv_exact(s.conn, f.length)

            # Checksum
            expected_checksum = f.checksum
            f.checksum = 0
            if expected_checksum != zlib.crc32(f.pack()):
                raise ValueError("Corrupted packet received.")
            
            # Decrypt
            plaintext = aes_ctr_decrypt(f.jsonmsg, f.nonce)
            payload = json.loads(plaintext.decode())
            
            data = payload['data']
            seq_incoming = payload['seq']

            # Seq check
            if seq_incoming != s.seq:
                raise ValueError(f"Bad seq: expected {s.seq} got {seq_incoming}")
            s.seq += 1

            return data
        
        except (ValueError, KeyError) as e:
            print(f"[WARNING] Ignored a bad package: {e}")
            continue

# ─── Miscellaneous Utility ─────────────────────────────────────────────────────

def determine_winner_and_loser(p1, p2):
    """
    Probe p1's connection: if it's still good, p1 is the winner; otherwise p2 is.
    Returns (winner, loser).
    """
    try:
        send_package(p1, MessageTypes.S_MESSAGE, "")
    except ConnectionError:
        return p2, p1
    else:
        return p1, p2
    
def wait_for_message(player,
                     timeout: float = 30.0,
                     allowed: tuple[str, ...] | None = None) -> str | None:
    """
    Block (with polling) until the player has typed something or the
    timeout elapses.

    * `allowed` – optional tuple of accepted replies (case-insensitive).
                  If given, the first match (UPPER-CASE) is returned;
                  anything else is treated as 'invalid' and we keep
                  waiting.  If the timer expires we return None.

    Returns the raw input string (or the validated UPPER-CASE variant
    if `allowed` was supplied), or None on timeout.

    Raises ConnectionError if the socket drops.
    """
    player.my_turn = True          # opens the gate in client_handler
    start = time.time()

    while time.time() - start < timeout:
        if not player.connected:
            raise ConnectionError

        with player.msg_lock:
            if player.latest_coord is not None:
                raw = player.latest_coord.strip()
                player.latest_coord = None

                if allowed is None:
                    player.my_turn = False
                    return raw            # normal gameplay / placement

                cand = raw.upper()
                if cand in allowed:
                    player.my_turn = False
                    return cand           # validated prompt reply
                # else: garbage – keep looping until timeout

        time.sleep(0.05)

    player.my_turn = False
    return None