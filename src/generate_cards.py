import json
import os
from datetime import datetime, timezone, timedelta
from PIL import Image, ImageDraw, ImageFont

# --- Config ---
WIDTH, HEIGHT = 1080, 1080

# Light editorial palette (cream / warm brown accent). Replaces the previous
# navy card. All colors are solid hex, not alpha-blended white, because on a
# light background alpha-over-white reads as "faded" rather than "muted" --
# using distinct solid shades for the text hierarchy gives cleaner contrast.
BG_COLOR     = "#F7F3EC"  # cream
TEXT_DARK    = "#211F1B"  # headline
TEXT_BODY    = "#3F3B34"  # summary / insight
TEXT_MUTED   = "#8A7C68"  # source / meta
ACCENT       = "#7A5230"  # rule + "WHAT IT MEANS TO YOU" label + kicker date
DIVIDER      = "#DDD3C2"  # hairline rules

PADDING  = 90
SGT      = timezone(timedelta(hours=8))
TODAY    = datetime.now(SGT).strftime("%-d %b %Y") if os.name != "nt" else datetime.now(SGT).strftime("%d %b %Y").lstrip("0")

OUTPUT_DIR = "docs"


# --- Font loader ---
# Bundled directly in the repo (assets/fonts/) so rendering is byte-identical on Windows,
# macOS, and the Ubuntu GitHub Actions runner.
#
# Two typefaces: Source Serif 4 (Bold) for the headline, Inter (Regular/Medium/SemiBold)
# for everything else. Both are static instances extracted from Google's variable-font
# releases (OFL licensed) -- plain .ttf files, loaded the same simple way as the previous
# DejaVu setup. No variable-font API used at render time, to keep this identical in
# complexity to what was already here.
FONT_DIR = os.path.join(os.path.dirname(__file__), "..", "assets", "fonts")
FONT_HEADLINE   = os.path.join(FONT_DIR, "SourceSerif4-Bold.ttf")
FONT_REGULAR    = os.path.join(FONT_DIR, "Inter-Regular.ttf")
FONT_MEDIUM     = os.path.join(FONT_DIR, "Inter-Medium.ttf")
FONT_SEMIBOLD   = os.path.join(FONT_DIR, "Inter-SemiBold.ttf")

_FONT_PATHS = {
    "headline": FONT_HEADLINE,
    "regular":  FONT_REGULAR,
    "medium":   FONT_MEDIUM,
    "semibold": FONT_SEMIBOLD,
}

def load_font(size, weight="regular"):
    path = _FONT_PATHS[weight]
    try:
        return ImageFont.truetype(path, size)
    except (IOError, OSError) as e:
        raise FileNotFoundError(
            f"Bundled font not found at {path}. Expected assets/fonts/ to contain "
            f"SourceSerif4-Bold.ttf, Inter-Regular.ttf, Inter-Medium.ttf and "
            f"Inter-SemiBold.ttf -- check they were committed to the repo."
        ) from e



# --- Text wrapper ---
def wrap_text(draw, text, font, max_width):
    """Wrap text to fit max_width, return list of lines."""
    words = text.split()
    lines = []
    current = ""
    for word in words:
        test = f"{current} {word}".strip()
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _cap_lines_with_ellipsis(lines, max_lines):
    """Truncate to max_lines, appending '...' to the last line if anything was cut.
    This is the hard backstop: even if Gemini ignores the word-count instruction in the
    prompt and returns unusually long text, rendered height is guaranteed bounded.
    In normal operation this should never fire -- fit_text_block already shrinks the
    font down through every candidate size before falling back to this."""
    if len(lines) <= max_lines:
        return lines
    kept = lines[:max_lines]
    kept[-1] = kept[-1].rstrip() + "..."
    return kept


def fit_text_block(draw, text, max_width, max_lines, candidate_sizes, weight="regular", line_height_ratio=1.37):
    """Find the largest font size (from candidate_sizes, largest first) that fits `text`
    within max_lines at max_width. Falls back to the smallest size + ellipsis truncation
    only if the text genuinely doesn't fit even at the smallest size -- this should be rare.
    Returns (font, lines, size, line_height)."""
    for size in candidate_sizes:
        font = load_font(size, weight=weight)
        lines = wrap_text(draw, text, font, max_width)
        if len(lines) <= max_lines:
            line_height = int(size * line_height_ratio)
            return font, lines, size, line_height

    # Nothing fit even at the smallest size -- last-resort truncation
    smallest = candidate_sizes[-1]
    font = load_font(smallest, weight=weight)
    lines = _cap_lines_with_ellipsis(wrap_text(draw, text, font, max_width), max_lines)
    line_height = int(smallest * line_height_ratio)
    return font, lines, smallest, line_height


# --- Draw a single card ---
def draw_card(card, index, total):
    img = Image.new("RGB", (WIDTH, HEIGHT), BG_COLOR)
    draw = ImageDraw.Draw(img, "RGBA")

    # Fonts (headline size is now dynamic -- see below -- everything else is fixed)
    f_brand_bold    = load_font(32, weight="semibold")
    f_brand_regular = load_font(32, weight="regular")
    f_counter       = load_font(32, weight="regular")
    f_label         = load_font(28, weight="semibold")
    f_source        = load_font(28, weight="regular")

    inner_width = WIDTH - (PADDING * 2)
    y = PADDING

    # --- Top row: bold brand + regular date + counter ---
    brand_bold = "AI Digest Daily"
    brand_bbox = draw.textbbox((0, 0), brand_bold, font=f_brand_bold)
    draw.text((PADDING, y), brand_bold, font=f_brand_bold, fill=TEXT_MUTED)
    date_text = f" - {TODAY}"
    draw.text((PADDING + brand_bbox[2], y), date_text, font=f_brand_regular, fill=TEXT_MUTED)
    counter_text = f"{index:02d} / {total:02d}"
    counter_bbox = draw.textbbox((0, 0), counter_text, font=f_counter)
    counter_x = WIDTH - PADDING - (counter_bbox[2] - counter_bbox[0])
    draw.text((counter_x, y), counter_text, font=f_counter, fill=TEXT_MUTED)

    y += 72

    # --- Short rule ---
    draw.rectangle([PADDING, y, PADDING + 64, y + 4], fill=ACCENT)
    y += 28

    # --- Headline (auto-fits: shrinks font before ever truncating text) ---
    # Previously fixed at 64px with no line cap -- a long headline could grow
    # downward indefinitely and collide with the summary. Now uses the same
    # fit_text_block system as summary/insight so it's bounded the same way.
    HEADLINE_SIZE_CANDIDATES = [64, 58, 52, 46, 40]
    f_headline, headline_lines, _, headline_line_height = fit_text_block(
        draw, card["headline"], inner_width, max_lines=3,
        candidate_sizes=HEADLINE_SIZE_CANDIDATES, weight="headline", line_height_ratio=1.22
    )
    for line in headline_lines:
        draw.text((PADDING, y), line, font=f_headline, fill=TEXT_DARK)
        y += headline_line_height
    y += 16

    # --- Summary (auto-fits: shrinks font before ever truncating text) ---
    BODY_SIZE_CANDIDATES = [38, 34, 30, 26]
    f_summary, summary_lines, _, summary_line_height = fit_text_block(
        draw, card["summary"], inner_width, max_lines=4, candidate_sizes=BODY_SIZE_CANDIDATES, weight="regular"
    )
    for line in summary_lines:
        draw.text((PADDING, y), line, font=f_summary, fill=TEXT_BODY)
        y += summary_line_height
    y += 24

    # --- Divider ---
    draw.rectangle([PADDING, y, WIDTH - PADDING, y + 1], fill=DIVIDER)
    y += 32

    # --- "What it means to you" label ---
    draw.text((PADDING, y), "WHAT IT MEANS TO YOU", font=f_label, fill=ACCENT)
    y += 48

    # --- Insight (auto-fits: shrinks font before ever truncating text) ---
    f_insight, insight_lines, _, insight_line_height = fit_text_block(
        draw, card["insight"], inner_width, max_lines=4, candidate_sizes=BODY_SIZE_CANDIDATES, weight="regular"
    )
    for line in insight_lines:
        draw.text((PADDING, y), line, font=f_insight, fill=TEXT_BODY)
        y += insight_line_height
    y += 24

    # --- Bottom row: source only (no category tag) ---
    # Dynamic, not fixed: takes whichever is LOWER between the standard bottom anchor
    # (for short cards, keeps consistent visual balance) and the actual content end + gap
    # (for long cards, guarantees the source line never collides with insight text).
    draw.rectangle([PADDING, y, WIDTH - PADDING, y + 1], fill=DIVIDER)
    y += 24
    standard_bottom_y = HEIGHT - PADDING - 36
    bottom_y = max(standard_bottom_y, y)
    draw.text((PADDING, bottom_y), f"Source: {card['source']}", font=f_source, fill=TEXT_MUTED)

    return img


# --- Main ---
def generate_cards(json_path="top5_cards.json", date_str=None, run_id=None):
    """Generate card PNGs with unique-per-run filenames (e.g. card_01_20260711_5821093.png).

    Filenames need to be unique per *execution*, not just per calendar day.
    A date-only suffix still collides if the workflow runs more than once on
    the same day (e.g. a manual re-trigger) -- two different article
    selections would render the same date text and the same filename, and
    whichever push happened to be cached by GitHub Pages' CDN at the moment
    Instagram fetched it would silently win, regardless of which run's
    caption was actually built. GITHUB_RUN_ID (set automatically by GitHub
    Actions, unique per workflow run) closes that gap. Falls back to a
    wall-clock timestamp for local/non-Actions runs.
    """
    if date_str is None:
        date_str = datetime.now(SGT).strftime("%Y%m%d")
    if run_id is None:
        run_id = os.environ.get("GITHUB_RUN_ID") or str(int(datetime.now(SGT).timestamp()))

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    with open(json_path, "r") as f:
        cards = json.load(f)

    total = len(cards)
    output_paths = []

    for i, card in enumerate(cards, start=1):
        img = draw_card(card, i, total)
        filename = f"{OUTPUT_DIR}/card_{i:02d}_{date_str}_{run_id}.png"
        img.save(filename, "PNG")
        print(f"Saved: {filename}")
        output_paths.append(filename)

    print(f"\nDone. {total} cards saved to /{OUTPUT_DIR}/")
    return output_paths, date_str, run_id


if __name__ == "__main__":
    generate_cards()