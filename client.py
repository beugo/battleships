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

# ─── Global State ──────────────────────────────────────────────────────────────
running = True

# ─── Login / Registration Helpers ─────────────────────────────────────────────

def ask_input(label: str) -> str:
    """Wrapper around prompt-toolkit so we keep stdout patched."""
    with patch_stdout():
        return prompt(label)


def register_user(s) -> bool:
    """Interactive registration loop. Returns True if successful."""
    while True:
        print_boxed("Choose a username:", style="green")
        username = ask_input(">> ")
        send_package(s, MessageTypes.COMMAND, f"REGISTER {username}")
        reply = receive_package(s)
        if not reply:
            return False
        status = reply.get("msg")
        if status == "USERNAME_OK":
            break
        elif status == "USERNAME_TAKEN":
            print_boxed("Username already taken. Try another one.", style="red")
            continue
        else:
            print_boxed(f"Unexpected reply: {status}", style="red")
            return False

    # PIN setup
    while True:
        print_boxed("Enter a 4-6 digit PIN:", style="green")
        pin = ask_input(">> ")
        if not pin.isdigit() or not (4 <= len(pin) <= 6):
            print_boxed("PIN must be 4-6 digits.", style="red")
            continue
        send_package(s, MessageTypes.COMMAND, f"{pin}")
        print_boxed("Registration complete!", style="cyan")
        return True



def login_user(s) -> bool:
    """Interactive login loop. Returns True if login succeeds."""
    while True:
        print_boxed("Username:", style="green")
        username = ask_input(">> ")
        send_package(s, MessageTypes.COMMAND, f"LOGIN {username}")
        reply = receive_package(s)
        if not reply:
            return False
        status = reply.get("msg")
        if status == "USER_NOT_FOUND":
            print_boxed("No such user. Try again.", style="red")
            continue
        if status != "USERNAME_OK":
            print_boxed(f"Woah hold up there sussy baka, no logins exist yet...", style="red")
            return False
        # username recognised – ask for PIN
        for _ in range(3):  # allow 3 attempts
            print_boxed("PIN:", style="green")
            pin = ask_input(">> ")
            send_package(s, MessageTypes.COMMAND, f"{pin}")
            reply = receive_package(s)
            if not reply:
                return False
            if reply.get("msg") == "LOGIN_SUCCESS":
                print_boxed("Login successful!", style="cyan")
                return True
            else:
                print_boxed("Incorrect PIN. Try again.", style="red")
        print_boxed("Too many failed attempts. Sussy baka.", style="red")


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
                print()  # blank line
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

    src_port = int(sys.argv[1]) if len(sys.argv) > 1 else 0

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", src_port))
        s.connect((HOST, PORT))

        # ── Login / Registration ────────────────────────────────────────────
        print_boxed("Welcome to Battleships!", style="cyan")
        print_boxed("Are you a new player? (y/n)", style="green")
        is_new = ask_input(">> ").lower().startswith("y")

        logged_in = register_user(s) if is_new else login_user(s)
        if not logged_in:
            print_boxed("Could not authenticate. Exiting…", style="red")
            return

        # ── Start receiver thread once authenticated ───────────────────────
        recv_thread = threading.Thread(target=receive_messages, args=(s,), daemon=True)
        recv_thread.start()

        # ── Gameplay / Chat Loop ────────────────────────────────────────────
        try:
            while running:
                with patch_stdout():
                    user_input = prompt(">> ")

                if user_input.startswith("CHAT "):
                    msg_type = MessageTypes.CHAT
                    payload = user_input[5:]
                else:
                    msg_type = MessageTypes.COMMAND
                    payload = user_input

                send_package(s, msg_type, payload)
        except KeyboardInterrupt:
            print()
            print_boxed("[INFO] Ctrl+C pressed. Quitting game…", style="yellow")
            try:
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
