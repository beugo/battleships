import socket
import struct
import json
import enum
import zlib

class Frame:
    def __init__(self):
        self.type = None
        self.length = 0
        self.checksum = 0
        self.jsonmsg = b''

    def pack(self):
        # H - unsigned short (2 bytes)
        # I - unsigned int (4 bytes)
        # {size}s - char[] (variable bytes according to size)

        return struct.pack(f'HHI{len(self.jsonmsg)}s', self.type, self.length, self.checksum, self.jsonmsg)
    
    def unpack_header(self, header):
        self.type, self.length, self.checksum = struct.unpack_from('HHI', header)

class MessageTypes(enum.Enum):
    # server -> client
    RESULT = 1 # forfeit, game win, hit/miss
    BOARD = 2 # board for: placing, playing
    PROMPT = 3 # request for: placing ship, next coordinate
    S_MESSAGE = 4 # for general server to client msgs
    WAITING = 5 # tell client to show spinner

    # client -> server
    COMMAND = 0 # place ship, shoot

def _build_result(msg: str):
    return {"type": "result", "msg": msg}

def _build_board(show_ships: bool, board):
    return {"type": "board", "ships": show_ships, "data": board}

def _build_prompt(msg, timeout):
    return {"type": "prompt", "timeout": timeout, "msg": msg}

def _build_command(data, timeout: bool):
    return {"type": "command", "timeout": timeout, "coord": data}

def _build_s_message(msg):
    return {"type": "s_msg", "msg": msg}

def _build_waiting(msg):
    return {"type": "waiting", "msg": msg}

_builders = {
    MessageTypes.RESULT: _build_result,
    MessageTypes.BOARD: _build_board,
    MessageTypes.PROMPT: _build_prompt,
    MessageTypes.COMMAND: _build_command,
    MessageTypes.S_MESSAGE: _build_s_message,
    MessageTypes.WAITING: _build_waiting
}

def _build_json(type: MessageTypes, *args):
    return _builders[type](*args)

def _create_board(board, setup=False):
    output = []
    output.append("  " + " ".join(str(i + 1).rjust(2) for i in range(board.size)) + '\n')
    for r in range(board.size):
        row_label = chr(ord('A') + r)

        if setup:
            row_str = " ".join(board.hidden_grid[r][c] for c in range(board.size))
        else:
            row_str = " ".join(board.display_grid[r][c] for c in range(board.size))

        output.append(f"{row_label:2} {row_str}\n")
    output.append('\n')
    return "".join(output)

# recv(s) returns up to s bytes (not guarenteed).
# this is not ideal as we need to ensure each frame is complete and whole - excluding everything else that may or may not follow.
# we therefore need to place each read of recv into a buffer until we have the size we are expecting (function below).
def _recv_exact(s, size):
    buffer = b''
    while len(buffer) < size:
        block = s.recv(size - len(buffer))
        if not block:
            raise ConnectionError("Connection closed.")
        buffer += block
    return buffer

def send_package(s, type: MessageTypes, *args):
    """
    s = socket object of the individual you want to send to.
    """
    f = Frame()
    f.type = type.value

    if type == MessageTypes.BOARD: # Special case for when we are sending a board.
        board_obj = args[0]
        show_ships = args[1]

        board_string = _create_board(board_obj, show_ships) 
        json_dict = _build_json(type, show_ships, board_string)
    else:
        json_dict = _build_json(type, *args)

    f.jsonmsg = json.dumps(json_dict).encode()
    f.length = len(f.jsonmsg)

    packed = f.pack()
    f.checksum = zlib.crc32(packed)
    packed = f.pack()

    s.sendall(packed)

def receive_package(s) -> dict:
    """
    s = socket object of the individual you are receiving from.
    """
    f = Frame()
    header = _recv_exact(s, 8) # 8 bytes is the size of our header.
    f.unpack_header(header)
    f.jsonmsg = _recv_exact(s, f.length)

    # TODO:
    checksum = f.checksum
    f.checksum = 0
    if (checksum != zlib.crc32(f.pack())):
        pass
    
    return json.loads(f.jsonmsg.decode())