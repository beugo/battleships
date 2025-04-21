import struct
import json
import enum

class Frame:
    def __init__(self):
        self.type = None
        self.seq = 0
        self.length = 0
        self.checksum = 0
        self.jsonmsg = b''

    def pack(self):
        # c - character (1 byte)
        # H - unsigned short (2 bytes)
        # I - unsigned int (4 bytes)
        # {size}s - char[] (variable bytes according to size)

        return struct.pack(f'cHHI{len(self.jsonmsg)}s', self.type, self.seq, self.length, self.checksum, self.jsonmsg)

    def unpack(self, bytes):
        payloadlen = len(bytes) - struct.calcsize('cHHI')
        self.type, self.seq, self.length, self.checksum, self.jsonmsg = struct.unpack_from(f'cHHI{payloadlen}s', bytes)

class MessageTypes(enum.Enum):
    # server -> client
    RESULT = 1 # forfeit, game win, hit/miss
    BOARD = 2 # when placing ships, or when playing
    PROMPT = 3 # request for: placing ship, next coordinate

    # client -> server
    COMMAND = 0 # place ship, shoot

def _build_result(msg: str):
    return {"type": "result", "msg": msg}

def _build_board(show_ships: bool, board):
    return {"type": "board", "ships": show_ships, "data": board}

def _build_prompt(msg):
    return {"type": "prompt", "msg": msg}

def _build_command(data):
    return {"type": "command", "coord": data}

_builders = {
    MessageTypes.RESULT: _build_result,
    MessageTypes.BOARD: _build_board,
    MessageTypes.PROMPT: _build_prompt,
    MessageTypes.COMMAND: _build_command
}

def build_json(type: MessageTypes, *args):
    return _builders[type](*args)

def send(wfile, msg):
    wfile.write(msg + '\n')
    wfile.flush()

def send_board(wfile, board, setup=False):
    wfile.write("GRID\n")
    wfile.write("  " + " ".join(str(i + 1).rjust(2) for i in range(board.size)) + '\n')
    for r in range(board.size):
        row_label = chr(ord('A') + r)

        if setup:
            row_str = " ".join(board.hidden_grid[r][c] for c in range(board.size))
        else:
            row_str = " ".join(board.display_grid[r][c] for c in range(board.size))

        wfile.write(f"{row_label:2} {row_str}\n")
    wfile.write('\n')
    wfile.flush()

def receive(rfile):
    return rfile.readline().strip()