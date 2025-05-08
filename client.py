import sys
import socket
import signal
import threading
from utils import *
from client_ui import *
from inputimeout import inputimeout, TimeoutOccurred

HOST = '127.0.0.1'
PORT = 5000

running = True
printing_ready = threading.Event()
console = Console()

global_socket_reference = None

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

def receive_messages(s):
    """Continuously receive and display messages from the server"""

    global running

    while running:
        try:
            package = receive_package(s)
            if not package:
                running = False
                break

            type = package.get("type")

            if type != "waiting":
                stop_spinner()

            if type == "board":
                print_board_as_table(package.get("data"))

            elif type == "prompt":
                print_boxed(package.get("msg"), style="green")
                global input_timeout
                input_timeout = package.get("timeout")
                printing_ready.set()

            elif type == "waiting":
                start_spinner(package.get("msg"))

            elif type == "result":
                print_boxed(package.get("msg"), style="bold magenta")
                printing_ready.clear()
            
            elif type == "quit":
                print('\n')
                print_boxed(package.get("msg"), style="red")
                running = False
                printing_ready.set()
                break

            else:
                print_boxed(package.get("msg"), style="cyan")

        except Exception as e:
            print_boxed(f"[ERROR] Receiver thread: {e}", title="Error", style="red")
            running = False
            printing_ready.set()
            break

def main():
    global running

    signal.signal(signal.SIGINT, handle_sigint)

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:

        global global_socket_reference
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
                    user_input = console.input("[bold green]>> [/bold green]")
                else:
                    try:
                        user_input = inputimeout(">> ", input_timeout)
                    except TimeoutOccurred:
                        send_package(s, MessageTypes.COMMAND, "", True) # Empty command with True flag for timeout - that way the user cannot replicate it artificially.
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

if __name__ == "__main__":
    main()
