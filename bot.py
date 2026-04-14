import json
import os
import time
import requests

# CONFIG
URL = "https://www.firstcry.com/api/product/listing"
SEEN_FILE = "seen.json"

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    requests.post(url, data={
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message
    })


def load_seen():
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE, "r") as f:
            return set(json.load(f))
    return set()


def save_seen(data):
    with open(SEEN_FILE, "w") as f:
        json.dump(list(data), f)


def fetch_products():
    params = {
        "category": "113",   # Hot Wheels
        "sort": "newarrivals",
        "page": 1
    }

    response = requests.get(URL, params=params)
    data = response.json()

    products = {}

    for item in data.get("products", []):
        name = item.get("productName")
        link = "https://www.firstcry.com" + item.get("url", "")

        products[link] = name

    return products


def main():
    seen = load_seen()
    current = fetch_products()

    current_links = set(current.keys())
    new_links = current_links - seen

    if new_links:
        msg = "🚨 New Hot Wheels listing!\n\n"

        for link in new_links:
            msg += f"{current[link]}\n{link}\n\n"

        send_telegram(msg)
        print(msg)
    else:
        print("No new listings.")

    save_seen(current_links)


if __name__ == "__main__":
    while True:
        main()
        time.sleep(900)  # 15 mins
