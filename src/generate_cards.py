import json
import os
from datetime import datetime, timezone, timedelta
from PIL import Image, ImageDraw, ImageFont

# --- Config ---
WIDTH, HEIGHT = 1080, 1080
BG_COLOR = "#2d3561"
WHITE = "#FFFFFF"
WHITE_75 = (255, 255, 255, 191)   # 75% opacity
WHITE_45 = (255, 255, 255, 115)   # 45% opacity
WHITE_40 = (255, 255, 255, 102)   # 40% opacity
WHITE_15 = (255, 255, 255, 38)    # 15% opacity (divider)
ACCENT   = "#a0b0e8"              # light blue for "What it means to you" label + insight
RULE     = "#7b8fd4"              # short rule under branding line

PADDING  = 90
SGT      = timezone(timedelta(hours=8))
TODAY    = datetime.now(SGT).strftime("%-d %b %Y") if os.name != "nt" else datetime.now(SGT).strftime("%d %b %Y").lstrip("0")

OUTPUT_DIR = "output"


# --- Font loader ---
# Bundled directly in the repo (assets/fonts/) so rendering is byte-identical on Windows,
# macOS, and the Ubuntu GitHub Actions runner. Previously this fell back through system font
# paths like "arial.ttf" — which resolves locally on Windows but silently fails on the CI
# runner, meaning the cards you visually approved locally didn't match daily production output.
FONT_DIR = os.path.join(os.path.dirname(__file__), "..", "assets", "fonts")
FONT_BOLD = os.path.join(FONT_DIR, "DejaVuSans-Bold.ttf")
FONT_REGULAR = os.path.join(FONT_DIR, "DejaVuSans.ttf")

def load_font(size, bold=False):
    path = FONT_BOLD if bold else FONT_REGULAR
    try:
        return ImageFont.truetype(path, size)
    except (IOError, OSError) as e:
        raise FileNotFoundError(
            f"Bundled font not found at {path}. Expected assets/fonts/ to contain "
            f"DejaVuSans.ttf and DejaVuSans-Bold.ttf — check they were committed to the repo."
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


# --- Draw a single card ---
def draw_card(card, index, total):
    img = Image.new("RGB", (WIDTH, HEIGHT), BG_COLOR)
    draw = ImageDraw.Draw(img, "RGBA")

    # Fonts
    f_brand_bold   = load_font(32, bold=True)
    f_brand_regular= load_font(32, bold=False)
    f_counter = load_font(32, bold=False)
    f_headline= load_font(64, bold=True)
    f_body    = load_font(38, bold=False)
    f_label   = load_font(28, bold=True)
    f_source  = load_font(28, bold=False)

    inner_width = WIDTH - (PADDING * 2)
    y = PADDING

    # --- Top row: bold brand + non-bold date + counter ---
    brand_bold = "AI Digest Daily"
    brand_bbox = draw.textbbox((0, 0), brand_bold, font=f_brand_bold)
    draw.text((PADDING, y), brand_bold, font=f_brand_bold, fill=WHITE_45)
    date_text = f" - {TODAY}"
    draw.text((PADDING + brand_bbox[2], y), date_text, font=f_brand_regular, fill=WHITE_45)
    counter_text = f"{index:02d} / {total:02d}"
    counter_bbox = draw.textbbox((0, 0), counter_text, font=f_counter)
    counter_x = WIDTH - PADDING - (counter_bbox[2] - counter_bbox[0])
    draw.text((counter_x, y), counter_text, font=f_counter, fill=WHITE_45)

    y += 72

    # --- Short rule ---
    draw.rectangle([PADDING, y, PADDING + 64, y + 4], fill=RULE)
    y += 28

    # --- Headline ---
    headline_lines = wrap_text(draw, card["headline"], f_headline, inner_width)
    for line in headline_lines:
        draw.text((PADDING, y), line, font=f_headline, fill=WHITE)
        y += 78
    y += 16

    # --- Summary (max 4 lines to prevent overflow) ---
    summary_lines = wrap_text(draw, card["summary"], f_body, inner_width)[:4]
    for line in summary_lines:
        draw.text((PADDING, y), line, font=f_body, fill=WHITE_75)
        y += 52
    y += 24

    # --- Divider ---
    draw.rectangle([PADDING, y, WIDTH - PADDING, y + 1], fill=WHITE_15)
    y += 32

    # --- "What it means to you" label ---
    draw.text((PADDING, y), "WHAT IT MEANS TO YOU", font=f_label, fill=ACCENT)
    y += 48

    # --- Insight (max 3 lines to prevent overflow) ---
    insight_lines = wrap_text(draw, card["insight"], f_body, inner_width)[:4]
    for line in insight_lines:
        draw.text((PADDING, y), line, font=f_body, fill=WHITE_75)
        y += 52
    y += 24

    # --- Bottom row: source only ---
    bottom_y = HEIGHT - PADDING - 36
    draw.text((PADDING, bottom_y), f"Source: {card['source']}", font=f_source, fill=WHITE_40)

    return img


# --- Main ---
def generate_cards(json_path="top5_cards.json"):
    # Clear old cards first to avoid stale files being picked up
    if os.path.exists(OUTPUT_DIR):
        for old_file in os.listdir(OUTPUT_DIR):
            if old_file.endswith(".png"):
                os.remove(os.path.join(OUTPUT_DIR, old_file))
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    with open(json_path, "r") as f:
        cards = json.load(f)

    total = len(cards)
    output_paths = []

    for i, card in enumerate(cards, start=1):
        img = draw_card(card, i, total)
        filename = f"{OUTPUT_DIR}/card_{i:02d}.png"
        img.save(filename, "PNG")
        print(f"Saved: {filename}")
        output_paths.append(filename)

    print(f"\nDone. {total} cards saved to /{OUTPUT_DIR}/")
    return output_paths


if __name__ == "__main__":
    generate_cards()