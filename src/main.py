import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from fetch_top5 import fetch_todays_articles, select_top5
from generate_cards import generate_cards
from send_email import send_cards
import json


def main():
    print("=== AI Digest Daily Pipeline ===\n")

    # Step 1: Fetch + select top 5
    print("Step 1: Fetching today's articles...")
    articles = fetch_todays_articles()
    cards = select_top5(articles)

    if not cards:
        print("No cards generated. Aborting.")
        sys.exit(1)

    # Save JSON
    with open("top5_cards.json", "w") as f:
        json.dump(cards, f, indent=2)
    print(f"Saved {len(cards)} cards to top5_cards.json\n")

    # Step 2: Generate images
    print("Step 2: Generating card images...")
    generate_cards()
    print()

    # Step 3: Send email
    print("Step 3: Sending email...")
    send_cards()

    print("\n=== Done ===")


if __name__ == "__main__":
    main()