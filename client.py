import sys
import socket
import threading
from prompt_toolkit import prompt
from prompt_toolkit.patch_stdout import patch_stdout
from utils import *
from client_ui import *


# ─── Configuration ─────────────────────────────────────────────────────────────
HOST = "127.0.0.1"
PORT = 5000

# ─── Server Class ──────────────────────────────────────────────────────────────

class Server:
    def __init__(self, conn, seq):
        self.conn = conn
        self.seq = seq

# ─── Global State ──────────────────────────────────────────────────────────────
running = True

# ─── Input Helper ─────────────────────────────────────────────────────────────
def ask(label: str) -> str:
    """Prompt-toolkit wrapper that plays nicely with the receiver thread."""
    with patch_stdout():
        return prompt(label)


# ─── Auth Helpers ─────────────────────────────────────────────────────────────
def register(s) -> bool:
    """Client-side registration handshake. Returns True on success."""
    while True:
        print_boxed("Choose a username:", style="green")
        username = ask(">> ").strip()
        if len(username.split()) != 1 or username == "":
            print_boxed("Please enter exactly one word as your username (no spaces).", style="red")
            continue
        send_package(s, MessageTypes.COMMAND, f"REGISTER {username}")
        reply = receive_package(s)
        if not reply:
            return False
        match reply.get("msg"):
            case "USERNAME_TAKEN":
                print_boxed("Username taken — try another.", style="red")
                continue
            case "USERNAME_OK":
                break
            case other:
                print_boxed(f"Unexpected reply: {other}", style="red")
                return False

    while True:
        print_boxed("Pick a 4-6 digit PIN:", style="green")
        pin = ask(">> ")
        if not pin.isdigit() or not 4 <= len(pin) <= 6:
            print_boxed("PIN must be 4-6 digits.", style="red")
            continue
        send_package(s, MessageTypes.COMMAND, f"SETPIN {pin}")
        reply = receive_package(s)
        if reply and reply.get("msg") == "REGISTRATION_SUCCESS":
            print_boxed("Registration complete!", style="cyan")
            return True
        print_boxed("Server rejected that PIN — try again.", style="red")

def login(s) -> bool:
    """Client-side login handshake. Returns True on success."""
    while True:
        print_boxed("Username:", style="green")
        username = ask(">> ")
        send_package(s, MessageTypes.COMMAND, f"LOGIN {username}")
        reply = receive_package(s)
        if not reply:
            return False
        status = reply.get("msg")
        if status == "USER_NOT_FOUND":
            print_boxed("No such user — try again.", style="red")
            continue
        if status != "USERNAME_OK":
            print_boxed(f"Unexpected reply: {status}", style="red")
            return False

        # now ask for PIN, up to 3 attempts
        for attempt in range(1, 4):
            print_boxed("PIN:", style="green")
            pin = ask(">> ")
            send_package(s, MessageTypes.COMMAND, f"PIN {pin}")
            reply = receive_package(s)
            if not reply:
                return False
            if reply.get("msg") == "LOGIN_SUCCESS":
                print_boxed("Login successful!", style="cyan")
                return True
            print_boxed(f"Incorrect PIN ({attempt}/3).", style="red")
        print_boxed("Sussy baka...", style="red")
        return False


# ─── Receiver Thread ───────────────────────────────────────────────────────────
def receiver(s):
    global running
    while running:
        try:
            package = receive_package(s)
            if not package:
                running = False
                break
            type = package.get("type")
            if type == "board":
                print_board_as_table(package.get("data"))
            elif type == "prompt":
                print_boxed(package.get("msg"), style="green")
            elif type == "waiting":
                print_boxed(package.get("msg"), style="dark_blue")
            elif type == "result":
                print_boxed(package.get("msg"), style="bold magenta")
            elif type == "chat":
                print_boxed(package.get("msg"), style="magenta")
            elif type == "shutdown":
                print_boxed(package.get("msg"), style="red")
                running = False
                break
            else:
                print_boxed(package.get("msg"), style="cyan")
        except (ConnectionError, OSError):
            break
        except Exception as e:
            print_boxed(f"[ERROR] Receiver: {e}", style="red")
            break
    running = False


# ─── Main ─────────────────────────────────────────────────────────────────────
def main():
    global running
    derive_key('we_love_cs')
    src_port = int(sys.argv[1]) if len(sys.argv) > 1 else 0

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", src_port))
        s.connect((HOST, PORT))
        s = Server(s, 0)
        
        try:
            # Auth
            print_boxed("Welcome to Battleships!", style="cyan")
            print_boxed("Are you a new player? (y/n)", style="green")
            is_new = ask(">> ").lower().startswith("y")
            if not (register(s) if is_new else login(s)):
                print_boxed("Could not authenticate — exiting.", style="red")
                return

            # Start receiver thread
            receiver_thread = threading.Thread(target=receiver, args=(s,))
            receiver_thread.start()

            # Chat / command loop
            while running:
                cmd = ask(">> ")
                if cmd.startswith("CHAT "):
                    send_package(s, MessageTypes.CHAT, cmd[5:])
                else:
                    send_package(s, MessageTypes.COMMAND, cmd)
        except KeyboardInterrupt:
            print_boxed("[INFO] Ctrl+C pressed — quitting…", style="yellow")
            try:
                send_package(s, MessageTypes.COMMAND, "quit")
            except Exception:
                pass
            running = False
        finally:
            try:
                s.conn.shutdown(socket.SHUT_RDWR)
                receiver_thread.join(timeout=2)
            except OSError:
                pass
            s.conn.close()
            print_boxed("[INFO] Client shut down.", style="green")

if __name__ == "__main__":
    main()
