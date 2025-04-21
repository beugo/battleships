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

    def unpack(self, bytes):
        payloadlen = len(bytes) - struct.calcsize('HHI')
        self.type, self.length, self.checksum, self.jsonmsg = struct.unpack_from(f'HHHI{payloadlen}s', bytes)

class MessageTypes(enum.Enum):
    # server -> client
    RESULT = 1 # forfeit, game win, hit/miss
    BOARD = 2 # board for: placing, playing
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

def send_package(s, type: MessageTypes, json_dict: dict):
    """
    s = socket object of the individual you want to send to.
    """
    f = Frame()
    f.type = type.value
    json_msg = json.dumps(json_dict).encode('utf-8')
    f.jsonmsg = json_msg
    f.length = len(json_msg)

    packed = f.pack()
    f.checksum = zlib.crc32(packed)
    packed = f.pack()

    s.sendall(packed)


def receive_package(s) -> dict:
    """
    s = socket object of the individual you are receiving from.
    """
    f = Frame()
    byte_msg = s.recv(2048) #Receiving maximum 2kB. Unsure how large packages can be so this may need adjusting. Also note this is a blocking function.
    f.unpack(byte_msg)

    # TODO Check the checksum:
    checksum = f.checksum
    f.checksum = 0
    if (checksum != zlib.crc32(f.pack)):
        pass
    
    return json.loads(f.jsonmsg.decode('utf-8'))

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