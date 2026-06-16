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

            if published is None or published == today:
                articles.append({
                    "title": entry.get("title", "No title"),
                    "summary": entry.get("summary", "")[:500],
                    "link": entry.get("link", ""),
                    "source": feed.feed.get("title", feed_url),
                    "published": str(published) if published else "unknown"
                })

    print(f"Fetched {len(articles)} articles from ({today})")
    return articles


# --- Step 2: Gemini picks Top 5 ---
def select_top5(articles):
    if not articles:
        print("No articles found for today.")
        return []

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
      "summary": "1 sentence. What happened and why it matters.",
      "insight": "1 sentence. A sharp perspective on what it means for everyday people.",
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
        print(f"  What it means  : {card['insight']}")
        print(f"  Source   : {card['source']}")

    with open("top5_cards.json", "w") as f:
        json.dump(cards, f, indent=2)
    print("\nSaved to top5_cards.json")