"""
client.py

Connects to a Battleship server which runs the single-player game.
Simply pipes user input to the server, and prints all server responses.
"""

import socket
import threading
from utils import *

HOST = '127.0.0.1'
PORT = 5000

running = True
printing_ready = threading.Event()

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
            
            if type == "board":
                print(package.get("data"))
            else:
                print(package.get("msg"))

            if type == "prompt":
                printing_ready.set() 

        except Exception as e:
            print(f"[ERROR] Receiver thread: {e}")
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
                if running == False: 
                    break
                user_input = input(">> ")
                printing_ready.clear()

                send_package(s, MessageTypes.COMMAND, user_input)

        except KeyboardInterrupt:
            print("\n[INFO] Client exiting.")
            running = False

        finally:
            print("[INFO] Shutting everything down...")

            try:
                send_package(s, MessageTypes.COMMAND, "quit")
            except Exception as e:
                print(f"[WARN] Could not send quit: {e}")

            s.close()
            print("[INFO] Client has shut down nice and gracefully.")

if __name__ == "__main__":
    main()