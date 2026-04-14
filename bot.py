import json
import os
import re
import requests
import time
from playwright.sync_api import sync_playwright

URL = "https://www.firstcry.com/hot-wheels/0/0/113?sort=newarrivals"
SEEN_FILE = "seen.json"

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}


def send_telegram(message: str) -> None:
    api_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    response = requests.post(
        api_url,
        data={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "disable_web_page_preview": True,
        },
        timeout=20,
    )
    response.raise_for_status()


def load_seen() -> set[str]:
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            try:
                return set(json.load(f))
            except json.JSONDecodeError:
                return set()
    return set()


def save_seen(items: set[str]) -> None:
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(items), f, indent=2)


def normalize_url(url: str) -> str:
    url = url.strip()
    if url.startswith("/"):
        url = "https://www.firstcry.com" + url
    return url.split("?")[0].split("#")[0]


def fetch_products() -> dict[str, str]:
    """
    Returns:
        dict of {product_url: product_title}
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(user_agent=HEADERS["User-Agent"])

        page.goto(URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(5000)

        links = page.eval_on_selector_all(
            "a[href]",
            "els => els.map(e => ({href: e.href, text: e.innerText || ''}))"
        )

        browser.close()

    products = {}
    for item in links:
        href = normalize_url(item.get("href", ""))
        text = re.sub(r"\s+", " ", item.get("text", "")).strip()

        if not href:
            continue

        # Keep only likely product detail links
        if "firstcry.com" in href.lower() and ("hot-wheels" in href.lower() or "product" in href.lower()):
            # filter out obvious non-product links if needed
            if len(text) < 3:
                text = "New Hot Wheels product"

            products[href] = text

    return products


def main() -> None:
    seen = load_seen()
    current = fetch_products()

    current_links = set(current.keys())
    new_links = current_links - seen

    if new_links:
        lines = ["🚨 New Hot Wheels listing(s) found:"]
        for link in sorted(new_links):
            title = current.get(link, "New product")
            lines.append(f"\n{title}\n{link}")

        send_telegram("\n".join(lines))
        print("\n".join(lines))
    else:
        print("No new listings.")

    save_seen(current_links)

if __name__ == "__main__":
    while True:
        main()
        time.sleep(900)  # 15 minutes

if __name__ == "__main__":
    main()
