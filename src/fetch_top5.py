import feedparser
import os
import json
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from google import genai

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
        for entry in feed.entries:
            published = None
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                published = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc).astimezone(SGT).date()

            yesterday = (datetime.now(SGT) - timedelta(days=1)).date()
            if published is None or published == today or published == yesterday:
                articles.append({
                    "title": entry.get("title", "No title"),
                    "summary": entry.get("summary", "")[:500],
                    "link": entry.get("link", ""),
                    "source": feed.feed.get("title", feed_url),
                    "published": str(published) if published else "unknown"
                })

    print(f"Fetched {len(articles)} articles from today ({today})")
    return articles


# --- Seen stories log ---
SEEN_LOG = "seen_stories.json"

def load_seen():
    if os.path.exists(SEEN_LOG):
        with open(SEEN_LOG, "r") as f:
            return set(json.load(f))
    return set()

def save_seen(headlines):
    existing = load_seen()
    updated = list(existing | set(headlines))
    # Keep only last 50 to avoid unbounded growth
    updated = updated[-50:]
    with open(SEEN_LOG, "w") as f:
        json.dump(updated, f, indent=2)


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
    articles = fresh

    client = genai.Client(api_key=GEMINI_API_KEY)

    articles_text = ""
    for i, a in enumerate(articles):
        articles_text += f"\n[{i+1}] Title: {a['title']}\nSource: {a['source']}\nSummary: {a['summary']}\nURL: {a['link']}\n"

    prompt = f"""You are an AI news editor curating content for a general public Instagram account.

From the articles below, select the 5 most significant AI stories for today.
Prioritise: novelty, real-world impact, and diversity of topics. Avoid duplicates on the same story.

For each selected story, write Instagram card copy in this exact JSON format:
{{
  "cards": [
    {{
      "headline": "Short punchy headline, max 8 words",
      "summary": "Exactly 2 short sentences only. What happened. No more than 30 words total.",
      "insight": "Exactly 2 short sentences only. A sharp perspective on why it matters for everyday people. No more than 30 words total.",
      "source": "Publication name only"
    }}
  ]
}}

Return ONLY valid JSON. No preamble, no markdown backticks.

Articles:
{articles_text}
"""

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt
    )

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

    # Mark selected headlines as seen
    save_seen([c["headline"] for c in cards])

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

    with open("top5_cards.json", "w") as f:
        json.dump(cards, f, indent=2)
    print("\nSaved to top5_cards.json")