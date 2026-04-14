import json
import os
import time
import requests
from playwright.sync_api import sync_playwright

URL = "https://www.firstcry.com/hot-wheels/0/0/113?sort=newarrivals"
SEEN_FILE = "seen.json"

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


# ================= TELEGRAM =================
def send_telegram(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("❌ Telegram config missing")
        return

    if len(message) > 3500:
        message = message[:3500]

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

    response = requests.post(url, data={
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message
    })

    print("Telegram:", response.text)


# ================= STORAGE =================
def load_seen():
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE, "r") as f:
            return set(json.load(f))
    return set()


def save_seen(data):
    with open(SEEN_FILE, "w") as f:
        json.dump(list(data), f)


# ================= FETCH PRODUCTS =================
def fetch_products():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        page.goto(URL, timeout=60000)
        page.wait_for_timeout(5000)

        anchors = page.locator("a").all()

        products = {}

        for a in anchors:
            try:
                href = a.get_attribute("href")
                text = a.inner_text().strip()

                if not href:
                    continue

                # normalize URL
                if href.startswith("/"):
                    href = "https://www.firstcry.com" + href

                href = href.split("?")[0]

                # ✅ STRICT FILTER (ONLY HOT WHEELS PRODUCTS)
                if (
                    "hot-wheels" in href.lower()
                    and href.count("/") > 5
                    and any(char.isdigit() for char in href.split("/")[-1])
                    and len(text) > 5
                ):
                    products[href] = text

            except:
                continue

        browser.close()

    return products


# ================= MAIN =================
def main():
    seen = load_seen()
    current = fetch_products()

    current_links = set(current.keys())

    # First run → save baseline + send test msg
    if not seen:
        save_seen(current_links)
        print(f"Baseline saved with {len(current_links)} products")

        send_telegram("✅ Hot Wheels bot is now active!")
        return

    new_links = list(current_links - seen)

    if new_links:
        msg = "🚨 New Hot Wheels listing!\n\n"

        for link in new_links[:3]:
            msg += f"{current[link]}\n{link}\n\n"

        send_telegram(msg)
        print(msg)
    else:
        print("No new listings.")

    save_seen(current_links)


if __name__ == "__main__":
    main()
