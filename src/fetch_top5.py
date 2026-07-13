import feedparser
import os
import json
import time
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from google import genai
from google.genai import errors as genai_errors  # Added for error handling

load_dotenv()

# --- Config ---
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
SGT = timezone(timedelta(hours=8))

RSS_FEEDS = [
    "https://techcrunch.com/category/artificial-intelligence/feed/",
    "https://www.theverge.com/ai-artificial-intelligence/rss/index.xml",
    "https://www.technologyreview.com/feed/",
]

# --- Step 1: Fetch articles from today ---
def fetch_todays_articles():
    today = datetime.now(SGT).date()
    articles = []

    for feed_url in RSS_FEEDS:
        feed = feedparser.parse(feed_url)

        # feedparser doesn't raise on network/parse failures — it silently
        # sets bozo=True and returns zero entries. Without logging this,
        # a fetch failure is indistinguishable from "genuinely no news
        # today" in the output, which makes debugging a zero-article day
        # a guessing game. Surface it explicitly instead.
        if feed.bozo:
            print(f"  WARNING: feed fetch issue for {feed_url}: {feed.bozo_exception}")
        print(f"  {feed_url}: {len(feed.entries)} entries returned")

        for entry in feed.entries:
            published = None
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                published = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc).astimezone(SGT).date()

            yesterday = (datetime.now(SGT) - timedelta(days=1)).date()
            if published is None or published == today or published == yesterday:
                # OPTIMIZATION: Reduce text footprint right at ingestion (200 chars is plenty)
                clean_summary = entry.get("summary", "")[:200].replace('\n', ' ').strip()
                articles.append({
                    "title": entry.get("title", "No title").strip(),
                    "summary": clean_summary,
                    "link": entry.get("link", ""),
                    "source": feed.feed.get("title", feed_url),
                    "published": str(published) if published else "unknown"
                })

    print(f"Fetched {len(articles)} articles from today ({today})")
    return articles


# --- Seen stories log ---
SEEN_LOG = "seen_stories.json"

def _load_seen_list():
    """Returns the seen log as an ORDERED list (oldest first), as stored on disk."""
    if os.path.exists(SEEN_LOG):
        # FIX: Explicitly enforce UTF-8 for Windows compatibility to prevent silent cp1252 corruption
        with open(SEEN_LOG, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def load_seen():
    """Returns the seen log as a set, for fast membership checks (order doesn't matter here)."""
    return set(_load_seen_list())

def save_seen(headlines):
    # Preserve insertion order so the 50-item cap is a real FIFO trim (oldest dropped first),
    # not an arbitrary subset — a plain set union has no defined order, so `list(set)[-50:]`
    # was silently dropping random entries rather than the oldest ones.
    existing = _load_seen_list()
    existing_set = set(existing)
    new_titles = [h for h in headlines if h not in existing_set]
    combined = existing + new_titles
    combined = combined[-200:]  # more headroom since stories can resurface in RSS feeds over ~2 days
    # FIX: Explicitly enforce UTF-8 for Windows compatibility
    with open(SEEN_LOG, "w", encoding="utf-8") as f:
        json.dump(combined, f, indent=2)


# --- Step 2: Gemini picks Top 5 ---
def select_top5(articles):
    if not articles:
        print("No articles found for today.")
        return []

    # Filter out already-seen stories
    seen = load_seen()
    fresh = [a for a in articles if a["title"] not in seen]
    print(f"After dedup: {len(fresh)} fresh articles (filtered {len(articles) - len(fresh)} seen)")
    if not fresh:
        print("All articles already seen. Nothing to send.")
        return []
        
    # OPTIMIZATION: Cap absolute maximum processing array size to protect TPM quota limits
    articles = fresh[:12] 
    if len(fresh) > 12:
        print(f"Capping input payload from {len(fresh)} down to the top 12 items to save API tokens.")

    client = genai.Client(api_key=GEMINI_API_KEY)

    articles_text = ""
    for i, a in enumerate(articles):
        articles_text += f"\n[{i+1}] Title: {a['title']}\nSource: {a['source']}\nSummary: {a['summary']}\n"

    prompt = f"""You are an AI news editor curating content for a general public Instagram account.

From the articles below, select the 5 most significant AI stories for today.
Prioritise: novelty, real-world impact, and diversity of topics. Avoid duplicates on the same story.

For each selected story, write Instagram card copy in this exact JSON format:
{{
  "cards": [
    {{
      "article_index": 1,
      "headline": "Short punchy headline, max 8 words",
      "summary": "Exactly 2 short sentences only. Summary of what happened. No more than 30 words total.",
      "insight": "Exactly 2 short sentences only. A sharp perspective and why it matters for everyday people. No more than 30 words total.",
      "source": "Publication name only"
    }}
  ]
}}

"article_index" must be the exact bracketed number (e.g. [3] -> 3) of the source article from the list below.

Return ONLY valid JSON. No preamble, no markdown backticks.

Articles:
{articles_text}
"""

    # OPTIMIZATION: Robust exponential backoff wrapper handling both 429 and 503 limits
    last_error = None
    response = None
    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt
            )
            break
        except (genai_errors.APIError, genai_errors.ServerError) as e:
            last_error = e
            # If hit by a 429 or 503, back off progressively (30s, 60s)
            wait = 30 * (attempt + 1)
            print(f"  API rate limit or server error encountered. Retrying in {wait}s (attempt {attempt + 1}/3)...")
            time.sleep(wait)
    else:
        print("❌ All API retry validation attempts failed.")
        raise last_error

    raw = response.text.strip()

    # Strip markdown fences if present
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    parsed = json.loads(raw)
    cards = parsed.get("cards", [])[:5]
    print(f"Gemini selected {len(cards)} cards")

    # Mark selected ORIGINAL article titles as seen (not Gemini's rewritten headlines —
    # those never match against fresh article titles on subsequent runs, so dedup silently
    # never fires). article_index maps back to the numbered list we sent in the prompt.
    selected_titles = []
    for c in cards:
        idx = c.get("article_index")
        if isinstance(idx, int) and 1 <= idx <= len(articles):
            selected_titles.append(articles[idx - 1]["title"])
        else:
            print(f"  Warning: card '{c.get('headline', '?')}' missing/invalid article_index — not marking as seen")

    save_seen(selected_titles)

    return cards


# --- Main ---
if __name__ == "__main__":
    articles = fetch_todays_articles()
    cards = select_top5(articles)

    print("\n--- TOP 5 AI NEWS CARDS ---")
    for i, card in enumerate(cards):
        print(f"\nCard {i+1}:")
        print(f"  Headline : {card['headline']}")
        print(f"  Summary  : {card['summary']}")
        print(f"  Insight  : {card['insight']}")
        print(f"  Source   : {card['source']}")

    # FIX: Explicitly enforce UTF-8 for Windows file writing compatibility
    with open("top5_cards.json", "w", encoding="utf-8") as f:
        json.dump(cards, f, indent=2)
    print("\nSaved to top5_cards.json")