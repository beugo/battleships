from io import StringIO
from prompt_toolkit import ANSI, print_formatted_text
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

def rich_to_ansi(rich_object):
    buf = StringIO()
    console = Console(file=buf, force_terminal=True)
    console.print(rich_object)
    return buf.getvalue()

def print_boxed(msg, title=None, style="cyan"):
    panel = Panel(msg, title=title, expand=False, style=style)
    ansi = rich_to_ansi(panel)
    print_formatted_text(ANSI(ansi))

def print_board_as_table(board_str: str):

    lines = board_str.strip().splitlines()

    if not lines:
        return

    col_labels = lines[0].split()
    table = Table(show_header=True, header_style="bold white", box=None)

    table.add_column(" ", style="bold white") 
    for col in col_labels:
        table.add_column(col, justify="center")

    for line in lines[1:]:
        parts = line.strip().split()
        if not parts:
            continue
        row_label = parts[0]
        row_cells = parts[1:]
        table.add_row(row_label, *row_cells)

    panel = Panel(table, border_style="cyan", expand=False)
    ansi = rich_to_ansi(panel)
    print_formatted_text(ANSI(ansi))