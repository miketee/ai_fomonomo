import sys
import os
import json
import argparse

sys.path.insert(0, os.path.dirname(__file__))

from fetch_top5 import fetch_todays_articles, select_top5
from generate_cards import generate_cards
from publish_instagram import publish_instagram_carousel, InstagramPublishError
from send_failure_email import send_failure_email

# Local scratch file used only to pass today's date string and run_id from
# `prepare` to `publish` within the same workflow job — not committed to git.
RUN_DATE_FILE = "run_date.txt"
RUN_ID_FILE = "run_id.txt"


def _set_github_output(key, value):
    """Write a step output so the workflow YAML can conditionally skip
    downstream steps (e.g. 'nothing to publish today') instead of those
    steps blindly running and crashing on missing files."""
    gh_output_path = os.environ.get("GITHUB_OUTPUT")
    if gh_output_path:
        with open(gh_output_path, "a", encoding="utf-8") as f:
            f.write(f"{key}={value}\n")


def prepare():
    """Stage 1: fetch articles, select top 5, generate card images.
    Leaves docs/*.png and top5_cards.json ready for the workflow to
    commit + push before Pages serves them publicly."""
    print("=== AI Digest Daily — Prepare ===\n")

    print("Step 1: Fetching today's articles...")
    articles = fetch_todays_articles()
    cards = select_top5(articles)

    if not cards:
        print("No cards generated today (nothing fresh to post). Not a failure.")
        _set_github_output("cards_found", "false")
        sys.exit(0)

    _set_github_output("cards_found", "true")

    with open("top5_cards.json", "w", encoding="utf-8") as f:
        json.dump(cards, f, indent=2)
    print(f"Saved {len(cards)} cards to top5_cards.json\n")

    print("Step 2: Generating card images...")
    _, date_str, run_id = generate_cards()

    # Persist the date + run_id used for filenames so `publish` uses the exact
    # same values, guaranteeing filenames can never collide across runs.
    with open(RUN_DATE_FILE, "w", encoding="utf-8") as f:
        f.write(date_str)
    with open(RUN_ID_FILE, "w", encoding="utf-8") as f:
        f.write(run_id)

    print("\n=== Prepare done ===")


def publish():
    """Stage 2: publish the already-generated cards as an Instagram carousel.
    Run only after the workflow has committed + pushed docs/ and given
    GitHub Pages time to redeploy."""
    print("=== AI Digest Daily — Publish ===\n")

    with open("top5_cards.json", "r", encoding="utf-8") as f:
        cards = json.load(f)

    if not cards:
        print("No cards to publish today. Skipping.")
        sys.exit(0)

    with open(RUN_DATE_FILE, "r", encoding="utf-8") as f:
        date_str = f.read().strip()
    with open(RUN_ID_FILE, "r", encoding="utf-8") as f:
        run_id = f.read().strip()

    image_filenames = [
        f"card_{i:02d}_{date_str}_{run_id}.png" for i in range(1, len(cards) + 1)
    ]

    print(f"Publishing carousel with {len(cards)} cards...")
    publish_instagram_carousel(cards, image_filenames, date_str)

    print("\n=== Publish done ===")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=["prepare", "publish"])
    args = parser.parse_args()

    try:
        if args.stage == "prepare":
            prepare()
        else:
            publish()
    except Exception as e:
        stage_name = "Prepare (fetch/select/generate)" if args.stage == "prepare" else "Publish (Instagram)"
        print(f"\n❌ Pipeline failed at stage: {stage_name}\nError: {e}")
        send_failure_email(e, stage_name)
        sys.exit(1)


if __name__ == "__main__":
    main()