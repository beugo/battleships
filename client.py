import sys
import socket
import threading
from prompt_toolkit import prompt
from prompt_toolkit.patch_stdout import patch_stdout
from utils import *
from client_ui import *

# ─── Configuration ─────────────────────────────────────────────────────────────
HOST = '127.0.0.1'
PORT = 5000

# ─── Global State ──────────────────────────────────────────────────────────────
running = True

# ─── Receiver Thread ───────────────────────────────────────────────────────────

def receive_messages(s):
    """Continuously receive and display messages from the server."""
    global running

    while running:
        try:
            package = receive_package(s)
            if not package:
                running = False
                break

            msg_type = package.get("type")

            if msg_type == "board":
                print_board_as_table(package.get("data"))

            elif msg_type == "prompt":
                print_boxed(package.get("msg"), style="green")

            elif msg_type == "waiting":
                print_boxed(package.get("msg"), style="dark_blue")

            elif msg_type == "result":
                print_boxed(package.get("msg"), style="bold magenta")

            elif msg_type == "chat":
                print_boxed(package.get("msg"), style="magenta")

            elif msg_type == "shutdown":
                print('\n')
                print_boxed(package.get("msg"), style="red")
                running = False
                break

            else:
                print_boxed(package.get("msg"), style="cyan")

        except Exception as e:
            print_boxed(f"[ERROR] Receiver thread: {e}", title="Error", style="red")
            running = False
            break

# ─── Main Client Loop ──────────────────────────────────────────────────────────

def main():
    global running

    source_port = int(sys.argv[1]) if len(sys.argv) > 1 else 0

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", source_port))
        s.connect((HOST, PORT))

        receiving_thread = threading.Thread(target=receive_messages, args=(s,), daemon=True)
        receiving_thread.start()

        try:
            while running:
                if not running:
                    break

                with patch_stdout():
                    user_input = prompt(">> ")

                if user_input.startswith("CHAT "):
                    msg_type = MessageTypes.CHAT
                    msg = user_input[5:]
                else:
                    msg_type = MessageTypes.COMMAND
                    msg = user_input

                send_package(s, msg_type, msg)

        except KeyboardInterrupt:
            print('\n')
            print_boxed("[INFO] Ctrl+C pressed. Quitting game...", style="yellow")
            try:
                # this might be a bit useless at the moment cause the server doesn't pick it up, although if we beef up the client handler thread in future then it could catch this
                send_package(s, MessageTypes.COMMAND, "quit", False)   
            except Exception:                                         
                pass
            running = False

        finally:
            s.close()
            print_boxed("[INFO] Client has shut down.", style="green")

# ─── Entry Point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    main()
