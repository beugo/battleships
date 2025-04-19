"""
client.py

Connects to a Battleship server which runs the single-player game.
Simply pipes user input to the server, and prints all server responses.
"""

import socket
import threading
import time

HOST = '127.0.0.1'
PORT = 5000

running = True
# printing_ready = threading.Event()

def receive_messages(rfile):
    """Continuously receive and display messages from the server"""

    global running

    while running:
        try:
            line = rfile.readline()
            if not line:
                print("[INFO] Server disconnected.")
                running = False
                break

            line = line.strip()

            if line == "GRID":
                print("\n[Board]")
                while True:
                    board_line = rfile.readline()
                    if not board_line or board_line.strip() == "":
                        break
                    print(board_line.strip())
            else:
                print(line)

            # if line == "Enter coordinate to fire at (e.g. B5):":
            #     printing_ready.set()

        except Exception as e:
            print(f"[ERROR] Receiver thread: {e}")
            running = False
            break


def main():

    global running

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.connect((HOST, PORT))
        rfile = s.makefile('r')
        wfile = s.makefile('w')

        receiving_thread = threading.Thread(target=receive_messages, args=(rfile,), daemon=True)
        receiving_thread.start()

        try:
            while running:
                # printing_ready.wait()
                user_input = input(">> ")
                # printing_ready.clear()

                wfile.write(user_input + '\n')
                wfile.flush()

        except KeyboardInterrupt:
            print("\n[INFO] Client exiting.")
            running = False

        finally:
            print("[INFO] Shutting everything down...")

            try:
                wfile.write("quit\n")
                wfile.flush()
            except:
                pass

            s.close()
            print("[INFO] Client has shut down nice and gracefully.")

if __name__ == "__main__":
    main()