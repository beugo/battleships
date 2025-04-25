import subprocess
import time
import socket
import threading
from utils import send_package, receive_package, MessageTypes

HOST = '127.0.0.1'
PORT = 5000

def start_server():
    return subprocess.Popen(["python3", "server.py"])

def simulate_client(name, moves, placements):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect((HOST, PORT))
    print(f"[{name}] Connected")
    finished_placing = False
    game_over = False

    def wait_for_prompt_and_respond(expected, response):
        nonlocal game_over
        while True:
            msg = receive_package(s)
            if msg["type"] == "prompt" and expected in msg["msg"]:
                send_package(s, MessageTypes.COMMAND, response)
                print(f"{name} responding to '{msg['msg']}' with '{response}'")
                break
            elif msg["type"] == "s_msg":
                print(f"{name}: {msg['msg']}")
            elif msg["type"] == "board":
                if msg["ships"] and not finished_placing:
                    print(f"{name} has now set up ships as follows:\n{msg['data']}")
                elif not msg["ships"]:
                    print(f"{name} sees updated board:\n{msg['data']}")
            elif msg["type"] == "result":
                print(f"{name} received game result: {msg['msg']}")
                if any(word in msg["msg"].lower() for word in ["win", "lost", "forfeit"]):
                    game_over = True
                    break

    for coord in placements:
        wait_for_prompt_and_respond("coordinate", coord)
    finished_placing = True
    print(f"{name} has finished placing ships.\n")

    for coord in moves:
        if game_over:
            break
        wait_for_prompt_and_respond("fire", coord)
        print(f"{name} has fired at {coord}.")
        time.sleep(0.5)

    while not game_over:
        try:
            msg = receive_package(s)
            if msg["type"] == "result":
                print(f"{name}: {msg['msg']}")
                if any(word in msg["msg"].lower() for word in ["win", "lost", "forfeit"]):
                    break
        except:
            break

    print(f"{name} is disconnecting...\n")
    s.close()

if __name__ == "__main__":
    print("Starting server...\n")
    server_proc = start_server()
    time.sleep(1)  # Allow server time to start

    player1_placements = ["A1 H", "B1 H", "C1 H", "D1 H", "E1 H"]
    player2_placements = ["J1 H", "I1 H", "H1 H", "G1 H", "F1 H"]

    player1_moves = [
        "J1", "I1", "H1", "G1", "F1",  # Carrier
        "J2", "I2", "H2", "G2",  # Battleship
        "J3", "I3", "H3",  # Cruiser
        "J4", "I4", "H4",  # Submarine
        "J5", "I5"  # Destroyer
    ]

    player2_moves = [
        "A1", "A2", "A3", "A4", "A5",  # Carrier
        "B1", "B2", "B3", "B4",  # Battleship
        "C1", "C2", "C3",  # Cruiser
        "D1", "D2", "D3",  # Submarine
        "E1", "E2"  # Destroyer
    ]

    p1_thread = threading.Thread(target=simulate_client, args=("Player 1", player1_moves, player1_placements), daemon=True)
    p2_thread = threading.Thread(target=simulate_client, args=("Player 2", player2_moves, player2_placements), daemon=True)

    p1_thread.start()
    p2_thread.start()

    p1_thread.join()
    p2_thread.join()

    print("\nBoth players disconnected.")
    print("Shutting down server...")
    server_proc.terminate()
    server_proc.wait()
    print("Server shut down cleanly.")
