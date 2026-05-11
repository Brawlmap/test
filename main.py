from brawlmap.compare import compare_players


def main():
    print("=== Brawlmap ===")
    tags = []
    print("Enter player tags (type 'done' when finished, min 2 players):")
    while True:
        tag = input("Player tag (e.g. #ABC123): ").strip()
        if tag.lower() == "done":
            if len(tags) < 2:
                print("Please enter at least 2 players.")
                continue
            break
        if not tag.startswith("#"):
            tag = "#" + tag
        tags.append(tag)

    compare_players(tags)


if __name__ == "__main__":
    main()
