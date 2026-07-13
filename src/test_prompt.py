"""
Test the Gemini insight-writing prompt against a fixed set of sample articles,
without touching real RSS feeds, real seen_stories.json, or posting anything.

Usage:
    cd ai_fomonomo
    python src/test_prompt.py

Run this after any prompt edit in fetch_top5.py to see the new output before
running the real pipeline. Uses the SAME select_top5() function as production,
so what you see here is exactly what the real prompt would produce.
"""

import sys
import os
import shutil

sys.path.insert(0, os.path.dirname(__file__))

from fetch_top5 import select_top5, SEEN_LOG

# Fixed sample articles — deliberately varied (funding, research, product,
# policy) to stress-test the insight prompt across different story types.
# Edit this list to add cases you want to specifically check.
SAMPLE_ARTICLES = [
    {
        "title": "Voice AI Startup Raises $120M Series C",
        "summary": "The startup, which builds real-time voice cloning for call centers, raised at a $1.4B valuation led by a top-tier VC. This is its fourth raise in two years.",
        "link": "https://example.com/1",
        "source": "TechCrunch",
        "published": "test",
    },
    {
        "title": "New Study Finds LLMs Struggle With Long Division",
        "summary": "Researchers tested 12 frontier models on multi-digit long division and found accuracy dropped below 40% past 4 digits, despite strong performance on other math benchmarks.",
        "link": "https://example.com/2",
        "source": "MIT Technology Review",
        "published": "test",
    },
    {
        "title": "Meta Ships On-Device AI Chip for Smart Glasses",
        "summary": "The new chip runs a 3B parameter model locally, cutting cloud inference costs by an estimated 80% for Meta and enabling offline voice assistant features.",
        "link": "https://example.com/3",
        "source": "The Verge",
        "published": "test",
    },
    {
        "title": "EU Proposes New AI Transparency Rules for Chatbots",
        "summary": "Draft rules would require companies to disclose when a user is talking to an AI, with fines up to 4% of global revenue for non-compliance, starting 2027.",
        "link": "https://example.com/4",
        "source": "TechCrunch",
        "published": "test",
    },
    {
        "title": "Open Source Model Matches GPT-4 on Coding Benchmark",
        "summary": "A new 70B open-weights model released by a research lab matched GPT-4's score on HumanEval, the first open model to do so, and can run on a single high-end GPU.",
        "link": "https://example.com/5",
        "source": "MIT Technology Review",
        "published": "test",
    },
]


def main():
    # Back up the real seen log so this test run can't pollute production dedup.
    # Track whether it existed BEFORE this run — if it didn't, we need to
    # delete it afterward (not just skip backup), or repeated test runs will
    # progressively mark all sample titles as "seen" and filter themselves out.
    existed_before = os.path.exists(SEEN_LOG)
    backup_path = None
    if existed_before:
        backup_path = SEEN_LOG + ".test_backup"
        shutil.copy(SEEN_LOG, backup_path)
        print(f"Backed up {SEEN_LOG} -> {backup_path}\n")
    else:
        print(f"No existing {SEEN_LOG} found — will remove the test-created one afterward.\n")

    try:
        cards = select_top5(SAMPLE_ARTICLES)

        print("\n" + "=" * 60)
        print(f"RESULT: {len(cards)} cards generated")
        print("=" * 60)
        for i, c in enumerate(cards, start=1):
            print(f"\n[{i}] {c.get('headline', '(missing headline)')}")
            print(f"    Summary: {c.get('summary', '(missing)')}")
            print(f"    Insight: {c.get('insight', '(missing)')}")
            print(f"    Source:  {c.get('source', '(missing)')}")

    finally:
        if existed_before and backup_path and os.path.exists(backup_path):
            shutil.move(backup_path, SEEN_LOG)
            print(f"\nRestored original {SEEN_LOG}")
        elif not existed_before and os.path.exists(SEEN_LOG):
            os.remove(SEEN_LOG)
            print(f"\nRemoved test-created {SEEN_LOG} (none existed before this run)")


if __name__ == "__main__":
    main()