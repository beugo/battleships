import sys
import socket
import signal
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
console = Console()
global_socket_reference = None
input_timeout = None

# ─── Signal Handler ────────────────────────────────────────────────────────────
def handle_sigint(signum, frame):
    global running
    print('\n')
    print_boxed("[INFO] Ctrl+C pressed. Quitting game...", style="yellow")
    try:
        if global_socket_reference:
            send_package(global_socket_reference, MessageTypes.COMMAND, "quit", False)
    except:
        pass
    running = False
    sys.exit(0)

# ─── Receiver Thread ───────────────────────────────────────────────────────────
def receive_messages(s):
    """Continuously receive and display messages from the server."""
    global running, input_timeout

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
                input_timeout = package.get("timeout")

            elif msg_type == "waiting":
                print_boxed(package.get("msg"))

            elif msg_type == "result":
                print_boxed(package.get("msg"), style="bold magenta")

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
    global running, global_socket_reference

    signal.signal(signal.SIGINT, handle_sigint)

    source_port = int(sys.argv[1]) if len(sys.argv) > 1 else 0

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", source_port))
        global_socket_reference = s
        s.connect((HOST, PORT))

        receiving_thread = threading.Thread(target=receive_messages, args=(s,), daemon=True)
        receiving_thread.start()

        try:
            while running:

                if not running:
                    break

                with patch_stdout():
                    user_input = prompt(">> ")

                send_package(s, MessageTypes.COMMAND, user_input, False)

        except KeyboardInterrupt:
            print('\n')
            print_boxed("[INFO] Client exiting.", style="yellow")
            running = False

        finally:
            s.close()
            print_boxed("[INFO] Client has shut down.", style="green")

# ─── Entry Point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    main()
