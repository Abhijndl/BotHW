import json
import os
import requests
import time
from datetime import datetime

# ================= CONFIG =================
URL = "https://www.firstcry.com/api/product/listing"
SEEN_FILE = "seen.json"
STATE_FILE = "state.json"

PINCODE = "248001"

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


# ================= TELEGRAM =================
def send_telegram(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return

    requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
        data={"chat_id": TELEGRAM_CHAT_ID, "text": message}
    )


# ================= STORAGE =================
def load_json(file, default):
    if os.path.exists(file):
        with open(file, "r") as f:
            return json.load(f)
    return default


def save_json(file, data):
    with open(file, "w") as f:
        json.dump(data, f)


# ================= FETCH =================
def fetch_products(max_pages=3):
    all_products = {}

    headers = {"User-Agent": "Mozilla/5.0"}

    for page in range(1, max_pages + 1):
        params = {
            "category": "113",
            "sort": "newarrivals",
            "page": page,
            "pincode": PINCODE
        }

        res = requests.get(URL, params=params, headers=headers)
        data = res.json()

        products = data.get("products", [])
        if not products:
            break

        for item in products:
            link = "https://www.firstcry.com" + item.get("url", "")
            stock = "in_stock"

            if item.get("isOutOfStock") or item.get("stock") == 0:
                stock = "out_of_stock"

            all_products[link] = stock

    return all_products


# ================= MAIN =================
def main():
    seen = load_json(SEEN_FILE, {})
    state = load_json(STATE_FILE, {"last_changes": 0})

    # ⚡ burst scanning
    scan1 = fetch_products(2)
    time.sleep(2)
    scan2 = fetch_products(2)

    # detect change
    if scan1 != scan2:
        current = fetch_products(5)
    else:
        current = scan2

    new_items = []
    restocks = []

    for link, stock in current.items():
        if link not in seen and stock == "in_stock":
            new_items.append(link)

        elif seen.get(link) == "out_of_stock" and stock == "in_stock":
            restocks.append(link)

    total = len(new_items) + len(restocks)

    # ================= PRIORITY =================
    if total >= 5:
        priority = "🚨 HIGH PRIORITY DROP"
    elif total >= 2:
        priority = "🔥 ACTIVE DROP WINDOW"
    elif total == 1:
        priority = "⚡ MINOR UPDATE"
    else:
        priority = None

    # ================= MESSAGE =================
    if priority:
        message = f"{priority} 🇮🇳 ({datetime.now().strftime('%H:%M')})\n"
        message += f"📦 Changes: {total}\n\n"

        for link in new_items[:3]:
            message += f"🆕 {link}\n"

        for link in restocks[:3]:
            message += f"🔥 {link}\n"

    else:
        message = f"⚡ Checked ({datetime.now().strftime('%H:%M')})\nNo trading signals."

    send_telegram(message)
    print(message)

    # save
    save_json(SEEN_FILE, current)
    save_json(STATE_FILE, {"last_changes": total})


if __name__ == "__main__":
    main()
