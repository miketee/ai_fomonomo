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

        if feed.bozo:
            print(f"  WARNING: feed fetch issue for {feed_url}: {feed.bozo_exception}")
        print(f"  {feed_url}: {len(feed.entries)} entries returned")

        for entry in feed.entries:
            published = None
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                published = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc).astimezone(SGT).date()

            yesterday = (datetime.now(SGT) - timedelta(days=1)).date()
            if published is None or published == today or published == yesterday:
                # NOTE: currently testing insight quality AS-IS against this 200-char cap.
                # If "meat mode" (surfacing a specific technical detail from the article)
                # comes back weak/generic in testing, this is the first thing to revisit --
                # 200 chars of an RSS teaser may just not contain real specifics often enough.
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
    if os.path.exists(SEEN_LOG):
        with open(SEEN_LOG, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def load_seen():
    return set(_load_seen_list())

def save_seen(headlines):
    existing = _load_seen_list()
    existing_set = set(existing)
    new_titles = [h for h in headlines if h not in existing_set]
    combined = existing + new_titles
    combined = combined[-200:]
    with open(SEEN_LOG, "w", encoding="utf-8") as f:
        json.dump(combined, f, indent=2)


# --- Step 2: Gemini picks Top 5 ---
def select_top5(articles):
    if not articles:
        print("No articles found for today.")
        return []

    seen = load_seen()
    fresh = [a for a in articles if a["title"] not in seen]
    print(f"After dedup: {len(fresh)} fresh articles (filtered {len(articles) - len(fresh)} seen)")
    if not fresh:
        print("All articles already seen. Nothing to send.")
        return []

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
      "insight": "ONE sharp sentence, max 15 words. See insight rules below.",
      "insight_shape": "One of: consequence_first, comparison_dash, question_lead, expect_forward, contrast_not_new, meat",
      "source": "Publication name only"
    }}
  ]
}}

AUDIENCE: Your reader already understands AI basics — they know what an LLM, inference, fine-tuning, and open-weights mean. Don't explain jargon or write for a beginner. But they're not a researcher either — they read AI news casually and want to understand where things fit in the bigger picture. Write like a sharp, well-informed friend explaining the significance to someone who follows the space but doesn't live in it. Confident and precise, not academic, not hype-y.

INSIGHT FIELD RULES (read carefully — this is the most important part of the card):

The insight answers ONE question: "what can the reader expect, going forward, because of this?" Not a restatement of what happened (that's the summary's job) — a forward-looking read on where this leads or fits into a pattern already in motion.

There are TWO valid ways to answer this. Pick whichever the story actually supports — do not force the first one if the story doesn't have a real precedent:

MODE 1 — TREND (preferred when a real pattern exists):
Describe a real pattern or shift already in motion. This can be EITHER:
(a) A specific named anchor (a company, product, event, or year) — preferred when a genuinely strong one exists, since it's more concrete and memorable.
Example: "Same boom-then-bust pattern as 2010s crypto mining — regulators were slow then too."
(b) A real macro-level pattern with no single named example, when that's honestly the more accurate framing — not every trend needs a specific case to be true. BUT a macro-pattern claim MUST still include at least ONE of these three concrete anchors, or it doesn't count as (b) — it's filler wearing a trend costume:
   - a specific time period ("2010s," "the last two years," "post-2022")
   - a specific mechanism (the actual thing that changes — "jobs shift," "prices drop," "platforms add disclosure," not "adapt" or "evolve")
   - a specific, non-generic consequence (something that would be false of most other tech stories, not true of nearly all of them)
Example: "Like previous tech shifts, companies restructure for AI, meaning jobs will shift or disappear." — passes: has a concrete mechanism (jobs shift/disappear).
Example that FAILS despite sounding similar: "Expect new security players to emerge tackling AI agent vulnerabilities." — no time period, the "mechanism" (new players emerge) is true of literally any funded startup in any category, and "tackling AI agent vulnerabilities" just repeats the story's own subject rather than adding a consequence. This is filler, not (b).
Do NOT force a weak or generic named anchor just to satisfy (a) — a clear, true macro-pattern claim beats an unconvincing forced comparison. But (a) and (b) are NOT the same as empty filler — see the filler test below.

FILLER TEST (apply this even after checking the (b) requirements above): could this exact sentence be pasted onto almost any other tech story unchanged and still sound plausible? If yes, it's filler — rewrite it to say something specifically true of this kind of shift, not tech news in general. "Cybersecurity will face increasing pressure to adapt to sophisticated attacks" fails — it could follow almost any security story ever written, in any year, about any threat. "Remember cybersecurity's early high-profile breaches?" also fails — "early high-profile breaches" names nothing (which breach? what year?) and the follow-up ("model safety will likely define AI platform trust for years") is boilerplate that fits any AI-safety story whatsoever. "Companies restructure for AI, meaning jobs will shift or disappear" passes — specific mechanism, not a placeholder phrase.

MODE 2 — MEAT (use when the story has no strong precedent — do NOT force a weak comparison just to have one):
Surface the single sharpest, most specific technical or concrete detail about THIS story that got cut from the summary for space — a number, spec, or capability — and state its forward implication. The detail must come from the article summary provided below. Do NOT invent a number, spec, or capability that isn't in the source text — if the summary doesn't contain a usable specific, fall back to Mode 1 with a hedged anchor rather than making one up.
Example (illustrative only — the real detail must come from the actual article): "Gemini 3.6 cuts token usage while improving context handling — a real efficiency jump."

BANNED IN BOTH MODES:
- Advocacy or prescriptive language: no "should," "must," "need to address," "companies need to." State what IS happening or WILL likely happen — never what someone OUGHT to do about it. This is a news account, not an op-ed.
- Normative judgment on contested, live political/policy questions (e.g. whether a sanctions policy was a good idea, whether a country "benefited"). Describe the pattern; do not grade it. If the story touches active geopolitics, stay descriptive: name the parallel, not the verdict.
- Restating a number/fact already in the summary, even reworded.
- Restating the obvious implication of the finding as if it were new (e.g. if the summary says "accuracy drops on hard problems," writing "this affects its reliability" is the same fact in future tense — discard it).
- Vague filler with no real specific behind it: "growing concerns," "sustainability challenges," "accelerating innovation," "significant implications." If you can't name the actual thing, don't gesture at it.
- BANNED WORDS, including any variant/inflection of them (e.g. "significant" AND "significantly" AND "significance" are all banned, not just the exact string): "huge", "massive", "game-changing", "significant", "exciting", "revolutionary", "unprecedented", "big step", "democratizes", "accelerating innovation".
- Do NOT start the insight with the word "This". It is the generic default and produces a templated batch even when the underlying content is good. Every shape below has its own required opener instead.

CONFIDENCE: If you're not fully confident a historical comparison or forecast is accurate, hedge it ("echoes...", "if this follows a similar pattern...") rather than stating it as fact. A hedged true claim beats a confident wrong one.

YEAR / DATE ACCURACY: If you name a specific year for a real historical event (e.g. "the 2019 Huawei ban"), you must be genuinely confident that year is correct — stating a wrong year as fact is worse than not naming one at all. If you are not fully certain of the exact year, either drop the year and describe the event without it ("the Huawei ban" instead of "the 2018 Huawei ban"), or hedge it ("around 2019") rather than stating a bare date with false confidence.

SENTENCE SHAPE — ASSIGN EACH CARD A DIFFERENT ONE. THE OPENER IS MANDATORY, NOT A SUGGESTION:
You are writing all 5 insights in one response. Assign each card a distinct shape from this list. Each shape has a REQUIRED literal opening pattern — the shape label alone does not satisfy the rule; the actual sentence must start the specified way, or the diversity requirement isn't really being met even if the label says otherwise. Do not reuse a shape across the batch of 5.
- consequence_first: MUST open with the consequence itself, not "This" — e.g. start with "Power grids...", "Prices...", "Developers...", the affected thing/person as the subject. ("Power grids could strain the way they did during 2010s crypto-mining booms.")
- comparison_dash: MUST open with "Same as..." or "Like [X]...". ("Same playbook as the 2019 Huawei ban — now aimed at models instead of hardware.")
- question_lead: MUST open with a short question ending in "?". ("Remember Bard's rocky 2023 debut? This looks like déjà vu.")
- expect_forward: MUST open with the word "Expect". ("Expect construction robotics to follow automotive manufacturing's curve: slow start, then fast scale.")
- contrast_not_new: MUST open with "Not new" or "Not the first". ("Not new — YouTube's 2024 AI-label policy came from the same demand for authenticity.")
- meat: open directly with the specific number/spec/capability itself as the subject, not "This". (e.g. "3B parameters running locally cuts...")

REQUIRED FIELD — DO NOT SKIP: Every card MUST include a non-empty "insight_shape" field naming exactly which shape you used for that card, from the six names above (consequence_first, comparison_dash, question_lead, expect_forward, contrast_not_new, meat). This is not optional and not just internal bookkeeping — a card missing this field is treated as an invalid response. Fill it in for all 5 cards, with no repeats.

Hard rules:
- Max 15 words.
- "article_index" must be the exact bracketed number (e.g. [3] -> 3) of the source article from the list below.

Return ONLY valid JSON. No preamble, no markdown backticks.

Articles:
{articles_text}
"""

    last_error = None
    response = None
    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model="gemini-3.6-flash",
                contents=prompt
            )
            break
        except (genai_errors.APIError, genai_errors.ServerError) as e:
            last_error = e
            wait = 30 * (attempt + 1)
            print(f"  API rate limit or server error encountered. Retrying in {wait}s (attempt {attempt + 1}/3)...")
            time.sleep(wait)
    else:
        print("❌ All API retry validation attempts failed.")
        raise last_error

    raw = response.text.strip()

    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    parsed = json.loads(raw)
    cards = parsed.get("cards", [])[:5]
    print(f"Gemini selected {len(cards)} cards")

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
        print(f"  Insight  : {card['insight']}  [{card.get('insight_shape', '?')}]")
        print(f"  Source   : {card['source']}")

    with open("top5_cards.json", "w", encoding="utf-8") as f:
        json.dump(cards, f, indent=2)
    print("\nSaved to top5_cards.json")