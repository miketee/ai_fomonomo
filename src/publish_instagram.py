import os
import time
from datetime import datetime, timezone, timedelta
import requests

# --- Config ---
META_PAGE_ID = os.environ.get("META_PAGE_ID")
META_IG_USER_ID = os.environ.get("META_IG_USER_ID")
META_SYSTEM_USER_TOKEN = os.environ.get("META_SYSTEM_USER_TOKEN")

SGT = timezone(timedelta(hours=8))

GRAPH_API_VERSION = "v21.0"
GRAPH_API_BASE = f"https://graph.facebook.com/{GRAPH_API_VERSION}"

# Public base URL where card images are served from GitHub Pages.
# e.g. https://miketee.github.io/ai_fomonomo/card_01.png
PAGES_BASE_URL = os.environ.get(
    "PAGES_BASE_URL", "https://miketee.github.io/ai_fomonomo"
)

# Polling config for container readiness
POLL_INTERVAL_SECONDS = 5
POLL_TIMEOUT_SECONDS = 120

# Polling config for GitHub Pages propagation (after docs/ is pushed, the
# public URL can take a short while to actually resolve)
PAGES_POLL_INTERVAL_SECONDS = 5
PAGES_POLL_TIMEOUT_SECONDS = 90


class InstagramPublishError(Exception):
    """Raised when any step of the carousel publish process fails."""
    pass


def _check_env():
    missing = [
        name
        for name, val in [
            ("META_IG_USER_ID", META_IG_USER_ID),
            ("META_SYSTEM_USER_TOKEN", META_SYSTEM_USER_TOKEN),
        ]
        if not val
    ]
    if missing:
        raise InstagramPublishError(
            f"Missing required environment variable(s): {', '.join(missing)}. "
            f"Check they're set as GitHub Actions secrets."
        )


def build_caption(cards):
    """Build the IG caption: date + fixed intro line + numbered headlines.

    Saturday, 11 July 2026. Here are the top AI news you should know today:

    1. <headline 1>
    2. <headline 2>
    ...
    """
    today_str = datetime.now(SGT).strftime("%A, %d %B %Y")
    intro = f"{today_str}. Here are the top AI news you should know today:"
    lines = [intro, ""]
    for i, card in enumerate(cards, start=1):
        lines.append(f"{i}. {card['headline']}")
    return "\n".join(lines)


def _image_url_for(filename):
    return f"{PAGES_BASE_URL}/{filename}"


def _wait_for_pages_propagation(image_filenames):
    """Block until every image URL actually resolves (HTTP 200) on GitHub Pages.
    Pages can take a short while to redeploy after a push, and Instagram's API
    will fail container creation if it can't fetch the image yet — so this is
    a real poll/retry, not a fixed sleep."""
    for filename in image_filenames:
        url = _image_url_for(filename)
        elapsed = 0
        while elapsed < PAGES_POLL_TIMEOUT_SECONDS:
            try:
                resp = requests.head(url, timeout=10, allow_redirects=True)
                if resp.status_code == 200:
                    break
            except requests.RequestException:
                pass
            time.sleep(PAGES_POLL_INTERVAL_SECONDS)
            elapsed += PAGES_POLL_INTERVAL_SECONDS
        else:
            raise InstagramPublishError(
                f"GitHub Pages URL never became available: {url} "
                f"(waited {PAGES_POLL_TIMEOUT_SECONDS}s). Was docs/ committed and pushed?"
            )
        print(f"  Confirmed live: {url}")


def _create_carousel_item_container(image_url):
    """Create a single carousel item (child) container from a public image URL."""
    resp = requests.post(
        f"{GRAPH_API_BASE}/{META_IG_USER_ID}/media",
        data={
            "image_url": image_url,
            "is_carousel_item": "true",
            "access_token": META_SYSTEM_USER_TOKEN,
        },
        timeout=30,
    )
    data = resp.json()
    if resp.status_code != 200 or "id" not in data:
        raise InstagramPublishError(
            f"Failed to create carousel item container for {image_url}: {data}"
        )
    return data["id"]


def _create_carousel_container(child_ids, caption):
    """Create the parent CAROUSEL container referencing all child item containers."""
    resp = requests.post(
        f"{GRAPH_API_BASE}/{META_IG_USER_ID}/media",
        data={
            "media_type": "CAROUSEL",
            "caption": caption,
            "children": ",".join(child_ids),
            "access_token": META_SYSTEM_USER_TOKEN,
        },
        timeout=30,
    )
    data = resp.json()
    if resp.status_code != 200 or "id" not in data:
        raise InstagramPublishError(f"Failed to create carousel container: {data}")
    return data["id"]


def _poll_container_status(container_id):
    """Poll a media container until its status_code is FINISHED.

    Raises InstagramPublishError on ERROR status or on timeout — this is a real
    poll loop (not a fixed sleep), since container processing time is variable
    and a fixed sleep either wastes time or isn't long enough.
    """
    elapsed = 0
    while elapsed < POLL_TIMEOUT_SECONDS:
        resp = requests.get(
            f"{GRAPH_API_BASE}/{container_id}",
            params={
                "fields": "status_code",
                "access_token": META_SYSTEM_USER_TOKEN,
            },
            timeout=30,
        )
        data = resp.json()
        status = data.get("status_code")

        if status == "FINISHED":
            return
        if status == "ERROR":
            raise InstagramPublishError(
                f"Container {container_id} failed processing: {data}"
            )
        # IN_PROGRESS or EXPIRED or missing — keep polling until timeout
        time.sleep(POLL_INTERVAL_SECONDS)
        elapsed += POLL_INTERVAL_SECONDS

    raise InstagramPublishError(
        f"Container {container_id} did not reach FINISHED status within "
        f"{POLL_TIMEOUT_SECONDS}s (last status: {status})"
    )


def _publish_container(container_id):
    resp = requests.post(
        f"{GRAPH_API_BASE}/{META_IG_USER_ID}/media_publish",
        data={
            "creation_id": container_id,
            "access_token": META_SYSTEM_USER_TOKEN,
        },
        timeout=30,
    )
    data = resp.json()
    if resp.status_code != 200 or "id" not in data:
        raise InstagramPublishError(f"Failed to publish carousel: {data}")
    return data["id"]


def publish_instagram_carousel(cards, image_filenames):
    """
    Publish a single carousel post to Instagram containing all card images.

    Args:
        cards: list of card dicts (each with 'headline', used to build the caption)
        image_filenames: list of filenames (e.g. ['card_01.png', ...]) already
            committed to docs/ and live on GitHub Pages, in display order.

    Returns:
        The published media id (str).

    Raises:
        InstagramPublishError on any failure — caller (main.py) is expected to
        catch this and trigger the failure-notification email.
    """
    _check_env()

    if len(cards) != len(image_filenames):
        raise InstagramPublishError(
            f"cards ({len(cards)}) and image_filenames ({len(image_filenames)}) "
            f"count mismatch — refusing to publish a mismatched carousel."
        )
    if not (2 <= len(image_filenames) <= 10):
        raise InstagramPublishError(
            f"Instagram carousels require 2-10 items, got {len(image_filenames)}."
        )

    caption = build_caption(cards)

    # Step 0: confirm the images are actually live on GitHub Pages before
    # asking Instagram to fetch them
    print("  Waiting for GitHub Pages propagation...")
    _wait_for_pages_propagation(image_filenames)

    # Step 1: create a child container per image
    child_ids = []
    for filename in image_filenames:
        image_url = _image_url_for(filename)
        print(f"  Creating carousel item container for {image_url}...")
        child_id = _create_carousel_item_container(image_url)
        child_ids.append(child_id)

    # Step 2: create the parent carousel container
    print("  Creating parent carousel container...")
    carousel_id = _create_carousel_container(child_ids, caption)

    # Step 3: poll until Instagram has finished processing all images
    print(f"  Polling container {carousel_id} for readiness...")
    _poll_container_status(carousel_id)

    # Step 4: publish
    print("  Publishing carousel...")
    media_id = _publish_container(carousel_id)
    print(f"  Published. Media ID: {media_id}")

    return media_id