import os
import smtplib
import glob
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

load_dotenv()

# --- Config ---
GMAIL_SENDER   = os.environ.get("GMAIL_SENDER")
GMAIL_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD")
GMAIL_RECIPIENT= os.environ.get("GMAIL_RECIPIENT")
SGT            = timezone(timedelta(hours=8))
TODAY          = datetime.now(SGT).strftime("%d %b %Y")
OUTPUT_DIR     = "docs"


def send_cards():
    # Find all card PNGs in order
    card_files = sorted(glob.glob(f"{OUTPUT_DIR}/card_*.png"))

    if not card_files:
        print("No card images found in output/. Run generate_cards.py first.")
        return

    print(f"Found {len(card_files)} cards to send.")

    # Build email
    msg = MIMEMultipart()
    msg["From"]    = GMAIL_SENDER
    msg["To"]      = GMAIL_RECIPIENT
    msg["Subject"] = f"AI Digest Daily — {TODAY}"

    # Email body
    body = f"""Your AI Digest Daily cards for {TODAY} are attached.

{len(card_files)} cards ready to upload to Instagram.

— AI Digest Bot
"""
    msg.attach(MIMEText(body, "plain"))

    # Attach each card
    for card_path in card_files:
        with open(card_path, "rb") as f:
            img_data = f.read()
        filename = os.path.basename(card_path)
        image = MIMEImage(img_data, name=filename)
        image.add_header("Content-Disposition", "attachment", filename=filename)
        msg.attach(image)
        print(f"Attached: {filename}")

    # Send via Gmail SMTP
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_SENDER, GMAIL_PASSWORD)
        server.sendmail(GMAIL_SENDER, GMAIL_RECIPIENT, msg.as_string())

    print(f"\nEmail sent to {GMAIL_RECIPIENT}")


if __name__ == "__main__":
    send_cards()