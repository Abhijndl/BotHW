import json
import os
import re
from pathlib import Path
from urllib.parse import urlparse

import requests
from playwright.sync_api import sync_playwright

URL = "https://www.firstcry.com/hot-wheels/0/0/113?sort=newarrivals"
SEEN_FILE = Path("seen.json")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()


def load_seen() -> set[str]:
    if not SEEN_FILE.exists():
        return set()

    try:
        with SEEN_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return set(data if isinstance(data, list) else [])
    except Exception:
        return set()


def save_seen(items: set[str]) -> None:
    with SEEN_FILE.open("w", encoding="utf-8") as f:
        json.dump(sorted(items), f, indent=2)


def normalize_url(url: str) -> str:
    url = (url or "").strip()
    if url.startswith("/"):
        url = "https://www.firstcry.com" + url
    return url.split("?")[0].split("#")[0].rstrip("/")


def is_hotwheels_product(url: str) -> bool:
    url = normalize_url(url).lower()

    if "firstcry.com" not in url:
        return False

    parsed = urlparse(url)
    path = parsed.path.rstrip("/")

    if not path.startswith("/hot-wheels/"):
        return False

    # Block the category page and similar generic pages
    blocked_exact = {
        "/hot-wheels/0/0/113",
    }
    if path in blocked_exact:
        return False

    segments = [seg for seg in path.split("/") if seg]
    if len(segments) < 3:
        return False

    # After /hot-wheels/, we want at least one slug segment containing letters,
    # and the last segment should be a numeric product id.
    tail = segments[1:]
    has_letter_segment = any(re.search(r"[a-z]", seg) for seg in tail[:-1])
    ends_with_numeric_id = re.fullmatch(r"\d{3,}", tail[-1]) is not None

    return has_letter_segment and ends_with_numeric_id


def fetch_products() -> dict[str, str]:
    """
    Returns:
        dict of {product_url: product_title}
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(
            viewport={"width": 1440, "height": 2200},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        )

        page.goto(URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(5000)

        anchors = page.locator("a[href]").evaluate_all(
            """els => els.map(e => ({
                href: e.href || '',
                text: (e.innerText || e.textContent || '').trim()
            }))"""
        )

        browser.close()

    products: dict[str, str] = {}

    for item in anchors:
        href = normalize_url(item.get("href", ""))
        text = re.sub(r"\s+", " ", item.get("text", "")).strip()

        if is_hotwheels_product(href):
            products[href] = text if text else "Hot Wheels product"

    return products


def send_telegram(message: str) -> None:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram config missing. Check GitHub Secrets.")
        return

    if len(message) > 3500:
        message = message[:3500] + "\n\n...truncated"

    api_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    response = requests.post(
        api_url,
        data={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "disable_web_page_preview": True,
        },
        timeout=30,
    )

    print("Telegram response:", response.status_code, response.text[:400])
    response.raise_for_status()


def main() -> None:
    seen = load_seen()
    current = fetch_products()
    current_links = set(current.keys())

    # First run: store baseline only, do not alert.
    if not seen:
        save_seen(current_links)
        print(f"Baseline saved with {len(current_links)} Hot Wheels links.")
        return

    new_links = sorted(current_links - seen)

    if new_links:
        lines = ["🚨 New Hot Wheels listing added:"]
        for link in new_links[:3]:
            title = current.get(link, "Hot Wheels product")
            lines.append(f"{title}\n{link}")

        message = "\n\n".join(lines)
        print(message)
        send_telegram(message)
    else:
        print("No new listings.")

    save_seen(current_links)


if __name__ == "__main__":
    main()
