from brawlmap.api import get_player


def compare_players(tags: list[str]):
    """Fetch and compare multiple players."""
    players = []
    for tag in tags:
        print(f"Fetching {tag}...")
        try:
            data = get_player(tag)
            players.append(data)
        except Exception as e:
            print(f"  Error fetching {tag}: {e}")

    if len(players) < 2:
        print("Not enough valid players to compare.")
        return

    print("\n--- Player Comparison ---")
    fields = [
        ("Name",          lambda p: p.get("name", "?")),
        ("Trophies",      lambda p: p.get("trophies", 0)),
        ("Highest",       lambda p: p.get("highestTrophies", 0)),
        ("Level (XP)",    lambda p: p.get("expLevel", 0)),
        ("3v3 Wins",      lambda p: p.get("3vs3Victories", 0)),
        ("Solo Wins",     lambda p: p.get("soloVictories", 0)),
        ("Duo Wins",      lambda p: p.get("duoVictories", 0)),
        ("Club",          lambda p: p.get("club", {}).get("name", "None")),
        ("Brawlers",      lambda p: len(p.get("brawlers", []))),
    ]

    col_width = 16
    header = f"{'Stat':<20}" + "".join(f"{p.get('name', '?'):<{col_width}}" for p in players)
    print(header)
    print("-" * len(header))

    for label, fn in fields:
        row = f"{label:<20}" + "".join(f"{str(fn(p)):<{col_width}}" for p in players)
        print(row)

    # Simple winner determination by trophies
    best = max(players, key=lambda p: p.get("trophies", 0))
    print(f"\n🏆 Best by trophies: {best.get('name')} ({best.get('trophies')} trophies)")
