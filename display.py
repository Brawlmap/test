from rich.console import Console

console = Console()


def show_result(result: dict):
    """Render the comparison result to the terminal."""
    p1 = result["player1"]
    p2 = result["player2"]
    console.print(f"\n[bold cyan]{p1['name']}[/] vs [bold magenta]{p2['name']}[/]\n")
    console.print("[yellow]Full comparison coming soon...[/]")
