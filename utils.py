import socket
import struct
import json
import enum
import zlib
import functools

# ─── Frame Class ───────────────────────────────────────────────────────────────

class Frame:
    def __init__(self):
        self.type = None
        self.length = 0
        self.checksum = 0
        self.jsonmsg = b''

    def pack(self):
        # H = unsigned short (2 bytes), I = unsigned int (4 bytes), s = string of length jsonmsg
        return struct.pack(f'HHI{len(self.jsonmsg)}s', self.type, self.length, self.checksum, self.jsonmsg)

    def unpack_header(self, header):
        self.type, self.length, self.checksum = struct.unpack_from('HHI', header)

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
    f = Frame()
    f.type = type.value

    if type == MessageTypes.BOARD:
        board_obj, show_ships = args
        board_string = _create_board(board_obj, show_ships)
        json_dict = _build_json(type, show_ships, board_string)
    else:
        json_dict = _build_json(type, *args)

    f.jsonmsg = json.dumps(json_dict).encode()
    f.length = len(f.jsonmsg)

    packed = f.pack()
    f.checksum = zlib.crc32(packed)
    packed = f.pack()

    try:
        s.sendall(packed)
    except (BrokenPipeError, ConnectionResetError, OSError) as e:
        # wrap any socket failure as ConnectionError
        raise ConnectionError(f"send_package failed: {e}")
    
def receive_package(s) -> dict:
    f = Frame()
    header = _recv_exact(s, 8)
    f.unpack_header(header)
    f.jsonmsg = _recv_exact(s, f.length)

    expected_checksum = f.checksum
    f.checksum = 0
    if expected_checksum != zlib.crc32(f.pack()):
        raise ValueError("Corrupted packet received.")

    return json.loads(f.jsonmsg.decode())

def determine_winner_and_loser(p1, p2):
    """
    Probe p1's connection: if it's still good, p1 is the winner; otherwise p2 is.
    Returns (winner, loser).
    """
    try:
        send_package(p1.conn, MessageTypes.S_MESSAGE, "")
    except ConnectionError:
        return p2, p1
    else:
        return p1, p2