import json
import os
import re
from pathlib import Path

import requests
from playwright.sync_api import sync_playwright

URL = "https://www.firstcry.com/hot-wheels/0/0/113?sort=newarrivals"
SEEN_FILE = Path("seen.json")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}


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


def send_telegram(message: str) -> None:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        raise RuntimeError("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID")

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
    response.raise_for_status()


def normalize_url(url: str) -> str:
    url = url.strip()
    if url.startswith("/"):
        url = "https://www.firstcry.com" + url
    return url.split("#")[0].split("?")[0]


def looks_like_product_link(href: str) -> bool:
    h = href.lower()

    if not h.startswith("https://www.firstcry.com/"):
        return False

    # Ignore obvious non-product links
    blocked = (
        "/cart",
        "/login",
        "/register",
        "/wishlist",
        "/search",
        "/help",
        "/terms",
        "/policy",
        "/faq",
        "/checkout",
    )
    if any(b in h for b in blocked):
        return False

    # Product-ish URLs usually have the brand/category plus an ID-like pattern
    if "hot-wheels" in h:
        return True

    if re.search(r"/\d{3,}(/|$)", h):
        return True

    return False


def fetch_products() -> dict[str, str]:
    """
    Returns:
        dict[str, str]: {product_url: product_title}
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 2200})
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

        if not href:
            continue

        if looks_like_product_link(href):
            # Keep a readable title if available
            title = text if len(text) >= 4 else "New Hot Wheels product"
            products[href] = title

    return products


def main() -> None:
    seen = load_seen()
    current = fetch_products()

    current_links = set(current.keys())
    new_links = current_links - seen

    if new_links:
        lines = ["🚨 New Hot Wheels listing found:"]
        for link in sorted(new_links):
            lines.append(f"\n{current.get(link, 'New Hot Wheels product')}\n{link}")

        message = "\n".join(lines)
        print(message)
        send_telegram(message)
    else:
        print("No new listings.")

    save_seen(current_links)


if __name__ == "__main__":
    main()