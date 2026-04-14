import json
import os
import requests
from playwright.sync_api import sync_playwright

# ================= CONFIG =================
URL = "https://www.firstcry.com/hot-wheels/0/0/113?sort=newarrivals"
SEEN_FILE = "seen.json"

PINCODE = "248001"  # Dehradun

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


# ================= TELEGRAM =================
def send_telegram(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram config missing")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

    requests.post(url, data={
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message
    })


# ================= STORAGE =================
def load_seen():
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE, "r") as f:
            return json.load(f)
    return {}


def save_seen(data):
    with open(SEEN_FILE, "w") as f:
        json.dump(data, f)


# ================= FETCH (FAST VERSION) =================
def fetch_products():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        context = browser.new_context(
            locale="en-IN",
            user_agent="Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 Chrome/120 Mobile Safari/537.36"
        )

        # India pincode
        context.add_cookies([
            {
                "name": "fc_city",
                "value": PINCODE,
                "domain": ".firstcry.com",
                "path": "/"
            }
        ])

        page = context.new_page()

        page.goto(URL, timeout=60000)
        page.wait_for_timeout(2500)  # ⚡ faster

        products = {}

        anchors = page.locator("a").all()

        for a in anchors:
            try:
                href = a.get_attribute("href")

                if not href:
                    continue

                if "/hot-wheels/" not in href:
                    continue

                # normalize
                if href.startswith("/"):
                    href = "https://www.firstcry.com" + href

                href = href.split("?")[0]

                # must have product ID
                last = href.split("/")[-1]
                if not last.isdigit():
                    continue

                # minimal text extraction (fast)
                text = a.inner_text().lower()

                # stock detection
                if "out of stock" in text:
                    stock = "out_of_stock"
                else:
                    stock = "in_stock"

                products[href] = {
                    "title": text[:60],
                    "stock": stock
                }

            except:
                continue

        browser.close()

    return products


# ================= MAIN =================
def main():
    seen = load_seen()
    current = fetch_products()

    updates = []

    for link, data in current.items():
        stock = data["stock"]
        title = data["title"]

        # NEW
        if link not in seen:
            if stock == "in_stock":
                updates.append(f"🆕 NEW\n{title}\n{link}")

        # RESTOCK
        elif seen.get(link) == "out_of_stock" and stock == "in_stock":
            updates.append(f"🔥 RESTOCK\n{title}\n{link}")

    # ALWAYS SEND
    if updates:
        message = "🚗 HOT WHEELS UPDATE 🇮🇳\n\n" + "\n\n".join(updates[:5])
    else:
        message = "✅ Checked (Dehradun)\nNo updates."

    send_telegram(message)
    print(message)

    # save state
    new_state = {link: data["stock"] for link, data in current.items()}
    save_seen(new_state)


if __name__ == "__main__":
    main()
