import os
import smtplib
import traceback
from email.mime.text import MIMEText
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

load_dotenv()

# --- Config (reuses the same Gmail SMTP secrets already used for the old daily email) ---
GMAIL_SENDER    = os.environ.get("GMAIL_SENDER")
GMAIL_PASSWORD  = os.environ.get("GMAIL_APP_PASSWORD")
GMAIL_RECIPIENT = os.environ.get("GMAIL_RECIPIENT")
SGT             = timezone(timedelta(hours=8))


def send_failure_email(error: Exception, stage: str):
    """Send a failure-only notification email. Called when any pipeline stage
    raises — this is the only email the pipeline sends now that daily emails
    have been replaced by direct Instagram publishing."""
    if not all([GMAIL_SENDER, GMAIL_PASSWORD, GMAIL_RECIPIENT]):
        print("  Warning: Gmail secrets not fully set — cannot send failure email.")
        return

    today = datetime.now(SGT).strftime("%d %b %Y")
    tb = traceback.format_exc()

    body = f"""AI Digest Daily pipeline FAILED on {today}.

Stage: {stage}
Error: {error}

Traceback:
{tb}

No Instagram post was made for today. Check the GitHub Actions run log for full details.
"""

    msg = MIMEText(body, "plain")
    msg["From"] = GMAIL_SENDER
    msg["To"] = GMAIL_RECIPIENT
    msg["Subject"] = f"⚠️ AI Digest Daily FAILED — {today}"

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_SENDER, GMAIL_PASSWORD)
            server.sendmail(GMAIL_SENDER, GMAIL_RECIPIENT, msg.as_string())
        print(f"  Failure notification sent to {GMAIL_RECIPIENT}")
    except Exception as e:
        # Don't let a failed notification email mask the original error
        print(f"  Warning: failed to send failure notification email: {e}")