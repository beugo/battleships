"""
battleship.py

Contains core data structures and logic for Battleship, including:
 - Board class for storing ship positions, hits, misses
 - Utility function parse_coordinate for translating e.g. 'B5' -> (row, col)
 - A test harness run_single_player_game() to demonstrate the logic in a local, single-player mode

"""

import time
import random
from utils import *

BOARD_SIZE = 10
SHIPS = [
    ("Carrier", 5),
    ("Battleship", 4),
    ("Cruiser", 3),
    ("Submarine", 3),
    ("Destroyer", 2)
]


class Board:
    """
    Represents a single Battleship board with hidden ships.
    We store:
      - self.hidden_grid: tracks real positions of ships ('S'), hits ('X'), misses ('o')
      - self.display_grid: the version we show to the player ('.' for unknown, 'X' for hits, 'o' for misses)
      - self.placed_ships: a list of dicts, each dict with:
          {
             'name': <ship_name>,
             'positions': set of (r, c),
          }
        used to determine when a specific ship has been fully sunk.

    In a full 2-player networked game:
      - Each player has their own Board instance.
      - When a player fires at their opponent, the server calls
        opponent_board.fire_at(...) and sends back the result.
    """

    def __init__(self, size=BOARD_SIZE):
        self.size = size
        # '.' for empty water
        self.hidden_grid = [['.' for _ in range(size)] for _ in range(size)]
        # display_grid is what the player or an observer sees (no 'S')
        self.display_grid = [['.' for _ in range(size)] for _ in range(size)]
        self.placed_ships = []  # e.g. [{'name': 'Destroyer', 'positions': {(r, c), ...}}, ...]

    def place_ships_randomly(self, ships=SHIPS):
        """
        Randomly place each ship in 'ships' on the hidden_grid, storing positions for each ship.
        In a networked version, you might parse explicit placements from a player's commands
        (e.g. "PLACE A1 H BATTLESHIP") or prompt the user for board coordinates and placement orientations; 
        the self.place_ships_manually() can be used as a guide.
        """
        for ship_name, ship_size in ships:
            placed = False
            while not placed:
                orientation = random.randint(0, 1)  # 0 => horizontal, 1 => vertical
                row = random.randint(0, self.size - 1)
                col = random.randint(0, self.size - 1)

                if self.can_place_ship(row, col, ship_size, orientation):
                    occupied_positions = self.do_place_ship(row, col, ship_size, orientation)
                    self.placed_ships.append({
                        'name': ship_name,
                        'positions': occupied_positions
                    })
                    placed = True


    def place_ships_manually(self, ships=SHIPS):
        """
        Prompt the user for each ship's starting coordinate and orientation (H or V).
        Validates the placement; if invalid, re-prompts.
        """
        print("\nPlease place your ships manually on the board.")
        for ship_name, ship_size in ships:
            while True:
                self.print_display_grid(show_hidden_board=True)
                print(f"\nPlacing your {ship_name} (size {ship_size}).")
                coord_str = input("  Enter starting coordinate (e.g. A1): ").strip()
                orientation_str = input("  Orientation? Enter 'H' (horizontal) or 'V' (vertical): ").strip().upper()

                try:
                    row, col = parse_coordinate(coord_str)
                except ValueError as e:
                    print(f"  [!] Invalid coordinate: {e}")
                    continue

                # Convert orientation_str to 0 (horizontal) or 1 (vertical)
                if orientation_str == 'H':
                    orientation = 0
                elif orientation_str == 'V':
                    orientation = 1
                else:
                    print("  [!] Invalid orientation. Please enter 'H' or 'V'.")
                    continue

                # Check if we can place the ship
                if self.can_place_ship(row, col, ship_size, orientation):
                    occupied_positions = self.do_place_ship(row, col, ship_size, orientation)
                    self.placed_ships.append({
                        'name': ship_name,
                        'positions': occupied_positions
                    })
                    break
                else:
                    print(f"  [!] Cannot place {ship_name} at {coord_str} (orientation={orientation_str}). Try again.")


    def can_place_ship(self, row, col, ship_size, orientation):
        """
        Check if we can place a ship of length 'ship_size' at (row, col)
        with the given orientation (0 => horizontal, 1 => vertical).
        Returns True if the space is free, False otherwise.
        """
        if orientation == 0:  # Horizontal
            if col + ship_size > self.size:
                return False
            for c in range(col, col + ship_size):
                if self.hidden_grid[row][c] != '.':
                    return False
        else:  # Vertical
            if row + ship_size > self.size:
                return False
            for r in range(row, row + ship_size):
                if self.hidden_grid[r][col] != '.':
                    return False
        return True

    def do_place_ship(self, row, col, ship_size, orientation):
        """
        Place the ship on hidden_grid by marking 'S', and return the set of occupied positions.
        """
        occupied = set()
        if orientation == 0:  # Horizontal
            for c in range(col, col + ship_size):
                self.hidden_grid[row][c] = 'S'
                occupied.add((row, c))
        else:  # Vertical
            for r in range(row, row + ship_size):
                self.hidden_grid[r][col] = 'S'
                occupied.add((r, col))
        return occupied

    def fire_at(self, row, col):
        """
        Fire at (row, col). Return a tuple (result, sunk_ship_name).
        Possible outcomes:
          - ('hit', None)          if it's a hit but not sunk
          - ('hit', <ship_name>)   if that shot causes the entire ship to sink
          - ('miss', None)         if no ship was there
          - ('already_shot', None) if that cell was already revealed as 'X' or 'o'

        The server can use this result to inform the firing player.
        """
        cell = self.hidden_grid[row][col]
        if cell == 'S':
            # Mark a hit
            self.hidden_grid[row][col] = 'X'
            self.display_grid[row][col] = 'X'
            # Check if that hit sank a ship
            sunk_ship_name = self._mark_hit_and_check_sunk(row, col)
            if sunk_ship_name:
                return ('hit', sunk_ship_name)  # A ship has just been sunk
            else:
                return ('hit', None)
        elif cell == '.':
            # Mark a miss
            self.hidden_grid[row][col] = 'o'
            self.display_grid[row][col] = 'o'
            return ('miss', None)
        elif cell == 'X' or cell == 'o':
            return ('already_shot', None)
        else:
            # In principle, this branch shouldn't happen if 'S', '.', 'X', 'o' are all possibilities
            return ('already_shot', None)

    def _mark_hit_and_check_sunk(self, row, col):
        """
        Remove (row, col) from the relevant ship's positions.
        If that ship's positions become empty, return the ship name (it's sunk).
        Otherwise return None.
        """
        for ship in self.placed_ships:
            if (row, col) in ship['positions']:
                ship['positions'].remove((row, col))
                if len(ship['positions']) == 0:
                    return ship['name']
                break
        return None

    def all_ships_sunk(self):
        """
        Check if all ships are sunk (i.e. every ship's positions are empty).
        """
        for ship in self.placed_ships:
            if len(ship['positions']) > 0:
                return False
        return True

    def print_display_grid(self, show_hidden_board=False):
        """
        Print the board as a 2D grid.
        
        If show_hidden_board is False (default), it prints the 'attacker' or 'observer' view:
        - '.' for unknown cells,
        - 'X' for known hits,
        - 'o' for known misses.
        
        If show_hidden_board is True, it prints the entire hidden grid:
        - 'S' for ships,
        - 'X' for hits,
        - 'o' for misses,
        - '.' for empty water.
        """
        # Decide which grid to print
        grid_to_print = self.hidden_grid if show_hidden_board else self.display_grid

        # Column headers (1 .. N)
        print("  " + "".join(str(i + 1).rjust(2) for i in range(self.size)))
        # Each row labeled with A, B, C, ...
        for r in range(self.size):
            row_label = chr(ord('A') + r)
            row_str = " ".join(grid_to_print[r][c] for c in range(self.size))
            print(f"{row_label:2} {row_str}")


def parse_coordinate(coord_str):
    """
    Convert something like 'B5' into zero-based (row, col).
    Example: 'A1' => (0, 0), 'C10' => (2, 9)
    HINT: you might want to add additional input validation here...
    """
    coord_str = coord_str.strip().upper()

    if len(coord_str) not in [2, 3]:
        raise ValueError("Coordinate is not the right size.")
    
    row_letter = coord_str[0]
    col_digits = coord_str[1:]

    if not row_letter.isalpha() or not col_digits.isdigit():
        raise ValueError("Incorrect coordinate format.")

    row = ord(row_letter) - ord('A')
    col = int(col_digits) - 1  # zero-based

    if not (0 <= row < BOARD_SIZE):
        raise ValueError("Row value not within board.")
    if not (0 <= col < BOARD_SIZE):
        raise ValueError("Column value not within board.")

    return (row, col)


def run_single_player_game_locally():
    """
    A test harness for local single-player mode, demonstrating two approaches:
     1) place_ships_manually()
     2) place_ships_randomly()

    Then the player tries to sink them by firing coordinates.
    """
    board = Board(BOARD_SIZE)

    # Ask user how they'd like to place ships
    choice = input("Place ships manually (M) or randomly (R)? [M/R]: ").strip().upper()
    if choice == 'M':
        board.place_ships_manually(SHIPS)
    else:
        board.place_ships_randomly(SHIPS)

    print("\nNow try to sink all the ships!")
    moves = 0
    while True:
        board.print_display_grid()
        guess = input("\nEnter coordinate to fire at (or 'quit'): ").strip()
        if guess.lower() == 'quit':
            print("Thanks for playing. Exiting...")
            return

        try:
            row, col = parse_coordinate(guess)
            result, sunk_name = board.fire_at(row, col)
            moves += 1

            if result == 'hit':
                if sunk_name:
                    print(f"  >> HIT! You sank the {sunk_name}!")
                else:
                    print("  >> HIT!")
                if board.all_ships_sunk():
                    board.print_display_grid()
                    print(f"\nCongratulations! You sank all ships in {moves} moves.")
                    break
            elif result == 'miss':
                print("  >> MISS!")
            elif result == 'already_shot':
                print("  >> You've already fired at that location. Try again.")

        except ValueError as e:
            print("  >> Invalid input:", e)
    
# ─── TESTING SHIP PLACEMENT ────────────────────────────────────────────────────
def testing_place_ships(board, player):
    TESTING_SHIPS = [
        ("Dinghy", 2),
        ("Single Guy in the Water With Some Floaties", 1)
    ]

    send_package(player.conn, MessageTypes.S_MESSAGE, "Please place your ships manually on the board.")

    for ship_name, ship_size in TESTING_SHIPS:
        while True:
            send_package(player.conn, MessageTypes.BOARD, board, True)
            send_package(player.conn, MessageTypes.S_MESSAGE, f"Placing your {ship_name} (size {ship_size})")
            send_package(player.conn, MessageTypes.PROMPT, "Enter starting coordinate followed by orientation (e.g. A1 V):")

            while True:
                placement = wait_for_message(player)
                if placement is None:
                    continue
                placement = placement.strip().upper()
                break

            try:
                coord_str, orientation_str = placement.split()
                row, col = parse_coordinate(coord_str)

                if orientation_str not in ("H", "V"):
                    raise ValueError("Orientation must be either 'H' or 'V'.")

                orientation = 0 if orientation_str == "H" else 1

            except ValueError as e:
                send_package(player.conn, MessageTypes.S_MESSAGE, f"[!] Invalid coordinate: {e}")
                continue

            if board.can_place_ship(row, col, ship_size, orientation):
                occupied_positions = board.do_place_ship(row, col, ship_size, orientation)
                board.placed_ships.append({
                    'name': ship_name,
                    'positions': occupied_positions
                })
                break
            else:
                send_package(player.conn, MessageTypes.S_MESSAGE, f"[!] Cannot place {ship_name} at {coord_str} (orientation={orientation_str}). Try again.")
                

# ─── ACTUAL NETWORK SHIP PLACEMENT ─────────────────────────────────────────────
def network_place_ships(board, player):
    send_package(player.conn, MessageTypes.S_MESSAGE, "Please place your ships manually on the board.")

    for ship_name, ship_size in SHIPS:
        while True:
            send_package(player.conn, MessageTypes.BOARD, board, True)
            send_package(player.conn, MessageTypes.S_MESSAGE, f"Placing your {ship_name} (size {ship_size})")
            send_package(player.conn, MessageTypes.PROMPT, "Enter starting coordinate followed by orientation (e.g. A1 V):")

            while True:
                placement = wait_for_message(player)
                if placement is None:
                    continue
                placement = placement.strip().upper()
                break

            try:
                coord_str, orientation_str = placement.split()
                row, col = parse_coordinate(coord_str)

                if orientation_str not in ("H", "V"):
                    raise ValueError("Orientation must be either 'H' or 'V'.")

                orientation = 0 if orientation_str == "H" else 1

            except ValueError as e:
                send_package(player.conn, MessageTypes.S_MESSAGE, f"[!] Invalid coordinate: {e}")
                continue

            if board.can_place_ship(row, col, ship_size, orientation):
                occupied_positions = board.do_place_ship(row, col, ship_size, orientation)
                board.placed_ships.append({
                    'name': ship_name,
                    'positions': occupied_positions
                })
                break
            else:
                send_package(player.conn, MessageTypes.S_MESSAGE, f"[!] Cannot place {ship_name} at {coord_str} (orientation={orientation_str}). Try again.")
                

# ─── MAIN GAME LOGIC ───────────────────────────────────────────────────────────
@detects_lost_connection
def run_two_player_game_online(p1, p2, gamestate, notify_spectators, broadcast):

    for player in (p1, p2):
        if gamestate.board_of(player.username) is None:
            board = Board(BOARD_SIZE)

            opponent = p2 if player is p1 else p1
            send_package(opponent.conn, MessageTypes.WAITING, "Please wait for your opponent to place their ships...")

            broadcast(
                msg=f"{player.username} is placing their ships...",
                msg_type=MessageTypes.S_MESSAGE,
                board=None,
                show_ships=False,
                spectators_only=True
            )
            testing_place_ships(board, player)
            gamestate.set_board(player.username, board)
            broadcast(
                msg=f"{player.username} has finished placing their ships...",
                msg_type=MessageTypes.S_MESSAGE,
                board=None,
                show_ships=False,
                spectators_only=True
            )

    if gamestate.current_player is None:
        gamestate.current_player = p1.username

    while True:
        attacker, defender = (
            (p1, p2) if gamestate.current_player == p1.username else (p2, p1)
        )
        defender_board = gamestate.board_of(defender.username)

        send_package(attacker.conn, MessageTypes.PROMPT, "Enter coordinate to fire at (e.g. B5) or 'Ctrl + C' to forfeit:")
        send_package(defender.conn, MessageTypes.WAITING, "Waiting for opponent to fire...")

        guess = wait_for_message(attacker)
        
        if guess is None:
            send_package(attacker.conn, MessageTypes.S_MESSAGE, "You took too long. Skipping your turn.")
            send_package(defender.conn, MessageTypes.S_MESSAGE, "Opponent time out. It is now your turn.")
            gamestate.current_player = p2.username if gamestate.current_player == p1.username else p1.username
            notify_spectators(defender_board, "timeout", False, attacker)
            continue

        guess = guess.strip().upper()

        try:
            row, col = parse_coordinate(guess)
            result, sunk_name = defender_board.fire_at(row, col)

            send_package(attacker.conn, MessageTypes.BOARD, defender_board, False)

            if result == "hit":
                if sunk_name:
                    send_package(attacker.conn, MessageTypes.S_MESSAGE, f"HIT! You blew up the {sunk_name}!")
                    send_package(defender.conn, MessageTypes.S_MESSAGE, f"HIT! The other player has blown up your {sunk_name}!")
                else:
                    send_package(attacker.conn, MessageTypes.S_MESSAGE, "HIT!")
                    send_package(defender.conn, MessageTypes.S_MESSAGE, "You were HIT!")

            elif result == "miss":
                send_package(attacker.conn, MessageTypes.S_MESSAGE, "MISS!")
                send_package(defender.conn, MessageTypes.S_MESSAGE, "The attacker MISSED!")

            elif result == "already_shot":
                send_package(attacker.conn, MessageTypes.S_MESSAGE, "Already fired there.")
                notify_spectators(defender_board, result, False, attacker)
                continue

            ships_sunk = defender_board.all_ships_sunk()
            notify_spectators(defender_board, result, ships_sunk, attacker)

            if ships_sunk:
                send_package(attacker.conn, MessageTypes.RESULT, "Congratulations! You win.")
                send_package(defender.conn, MessageTypes.RESULT, "You lost.")
                return "done"

            gamestate.current_player = defender.username

        except ValueError as e:
            send_package(attacker.conn, MessageTypes.S_MESSAGE, f"Invalid input: {e}")
            continue
        

if __name__ == "__main__":
    run_single_player_game_locally()
