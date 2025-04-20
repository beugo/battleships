def send(wfile, msg):
    wfile.write(msg + '\n')
    wfile.flush()

def send_board(wfile, board, setup=False):
    wfile.write("GRID\n")
    wfile.write("  " + " ".join(str(i + 1).rjust(2) for i in range(board.size)) + '\n')
    for r in range(board.size):
        row_label = chr(ord('A') + r)

        if setup:
            row_str = " ".join(board.hidden_grid[r][c] for c in range(board.size))
        else:
            row_str = " ".join(board.display_grid[r][c] for c in range(board.size))

        wfile.write(f"{row_label:2} {row_str}\n")
    wfile.write('\n')
    wfile.flush()

def receive(rfile):
    return rfile.readline().strip()