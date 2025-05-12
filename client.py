import sys
import socket
import signal
import threading
from inputimeout import inputimeout, TimeoutOccurred
from utils import *
from client_ui import *

# ─── Configuration ─────────────────────────────────────────────────────────────
HOST = '127.0.0.1'
PORT = 5000

# ─── Global State ──────────────────────────────────────────────────────────────
running = True
printing_ready = threading.Event()
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
    printing_ready.set()
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

            stop_spinner()

            if msg_type == "board":
                print_board_as_table(package.get("data"))

            elif msg_type == "prompt":
                print_boxed(package.get("msg"), style="green")
                input_timeout = package.get("timeout")
                printing_ready.set()

            elif msg_type == "waiting":
                start_spinner(package.get("msg"))

            elif msg_type == "result":
                print_boxed(package.get("msg"), style="bold magenta")
                printing_ready.clear()

            elif msg_type == "shutdown":
                print('\n')
                print_boxed(package.get("msg"), style="red")
                printing_ready.set()
                running = False
                break

            else:
                print_boxed(package.get("msg"), style="cyan")

        except Exception as e:
            print_boxed(f"[ERROR] Receiver thread: {e}", title="Error", style="red")
            running = False
            printing_ready.set()
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
                printing_ready.wait()

                if not running:
                    break

                if input_timeout is None:
                    user_input = console.input(">> ")
                else:
                    try:
                        user_input = inputimeout(">> ", input_timeout)
                    except TimeoutOccurred:
                        send_package(s, MessageTypes.COMMAND, "", True)
                        printing_ready.clear()
                        continue

                printing_ready.clear()
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
