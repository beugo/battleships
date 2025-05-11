from rich.console import Console
from rich.panel import Panel
from rich.spinner import Spinner
from rich.live import Live
from rich.table import Table
from rich.align import Align
import threading
import time

console = Console()
spinner_active = threading.Event()
spinner_thread = None
spinner_msg = "Waiting for opponent..."

def print_boxed(msg, title=None, style="cyan"):
    console.print(Panel(msg, title=title, expand=False, style=style), justify="center")

def create_spinner_render():
    spinner = Spinner("dots", spinner_msg)
    panel = Panel(spinner, border_style="cyan", expand=False)
    layout = Align.center(panel)
    return layout

def spinner_worker():
    layout = create_spinner_render()

    with Live(layout, refresh_per_second=10) as live:
        while spinner_active.is_set():
            live.update(create_spinner_render())
            time.sleep(0.1)
        
        live.update(Align.center(""))

def start_spinner(msg="Waiting for opponent..."):
    global spinner_thread, spinner_msg
    spinner_msg = msg
    if spinner_active.is_set():
        return  # already running
    spinner_active.set()
    spinner_thread = threading.Thread(target=spinner_worker, daemon=True)
    spinner_thread.start()

def stop_spinner():
    spinner_active.clear()
    if spinner_thread:
        spinner_thread.join()

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
    console.print(panel, justify="center")