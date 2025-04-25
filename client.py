import socket
import threading
from utils import *
from client_ui import *

HOST = '127.0.0.1'
PORT = 5000

running = True
printing_ready = threading.Event()
console = Console()

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
                printing_ready.set()
                print_boxed(package.get("msg"), style="green") 
            elif type == "waiting":
                start_spinner()
            else:
                print_boxed(package.get("msg"), style="cyan")

        except Exception as e:
            print_boxed(f"[ERROR] Receiver thread: {e}", title="Error", style="red")
            running = False
            printing_ready.set()
            break

def main():
    global running

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.connect((HOST, PORT))

        receiving_thread = threading.Thread(target=receive_messages, args=(s,), daemon=True)
        receiving_thread.start()

        try:
            while running:
                printing_ready.wait()
                if not running:
                    break
                user_input = console.input("[bold green]>> [/bold green]")
                printing_ready.clear()

                send_package(s, MessageTypes.COMMAND, user_input)

        except KeyboardInterrupt:
            print_boxed("[INFO] Client exiting.", style="yellow")
            running = False

        finally:
            print_boxed("[INFO] Shutting everything down...", style="yellow")

            try:
                send_package(s, MessageTypes.COMMAND, "quit")
            except Exception as e:
                print_boxed(f"[WARN] Could not send quit: {e}", title="Warning", style="magenta")

            s.close()
            print_boxed("[INFO] Client has shut down nice and gracefully.", style="green")

if __name__ == "__main__":
    main()
