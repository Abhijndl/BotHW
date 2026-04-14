import json
import os
import requests

# ================= CONFIG =================
URL = "https://www.firstcry.com/api/product/listing"
SEEN_FILE = "seen.json"

PINCODE = "248001"

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


# ================= FETCH (API FAST) =================
def fetch_products():
    all_products = {}

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json"
    }

    # 🔥 scan multiple pages
    for page in range(1, 4):  # page 1–3
        params = {
            "category": "113",
            "sort": "newarrivals",
            "page": page,
            "pincode": PINCODE
        }

        response = requests.get(URL, params=params, headers=headers)
        data = response.json()

        products = data.get("products", [])

        if not products:
            break

        for item in products:
            name = item.get("productName", "").lower()
            link = "https://www.firstcry.com" + item.get("url", "")

            # stock detection
            stock = "in_stock"
            if item.get("isOutOfStock") or item.get("stock") == 0:
                stock = "out_of_stock"

            all_products[link] = {
                "title": name[:60],
                "stock": stock
            }

    return all_products


# ================= MAIN =================
def main():
    seen = load_seen()
    current = fetch_products()

    updates = []
    restocks = []

    for link, data in current.items():
        stock = data["stock"]
        title = data["title"]

        # NEW
        if link not in seen:
            if stock == "in_stock":
                updates.append(f"🆕 {title}\n{link}")

        # RESTOCK
        elif seen.get(link) == "out_of_stock" and stock == "in_stock":
            restocks.append(f"🔥 {title}\n{link}")

    # 🔥 SMART MESSAGE
    if updates or restocks:
        message = "🚗 HOT WHEELS DROP 🇮🇳\n\n"

        if updates:
            message += "🆕 NEW:\n" + "\n\n".join(updates[:3]) + "\n\n"

        if restocks:
            message += "🔥 RESTOCK:\n" + "\n\n".join(restocks[:3])

    else:
        message = "⚡ Checked (Dehradun)\nNo updates."

    send_telegram(message)
    print(message)

    # save state
    new_state = {link: data["stock"] for link, data in current.items()}
    save_seen(new_state)


if __name__ == "__main__":
    main()
