import json
import os
import requests
from concurrent.futures import ThreadPoolExecutor
from playwright.sync_api import sync_playwright

URL_API = "https://www.firstcry.com/api/product/listing"
SEEN_FILE = "seen.json"

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


# ================= TELEGRAM =================
def send_telegram(message):
    requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
        data={"chat_id": TELEGRAM_CHAT_ID, "text": message}
    )


# ================= STORAGE =================
def load_seen():
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE, "r") as f:
            return json.load(f)
    return {}


def save_seen(data):
    with open(SEEN_FILE, "w") as f:
        json.dump(data, f)


# ================= FAST API =================
def fetch_api():
    params = {"category": "113", "sort": "newarrivals", "page": 1}
    res = requests.get(URL_API, params=params)
    data = res.json()

    links = []
    for item in data.get("products", []):
        link = "https://www.firstcry.com" + item.get("url", "")
        links.append(link)

    return links[:8]  # 🔥 only top 8 (faster)


# ================= CHECK ONE =================
def check_one(page, link):
    try:
        page.goto(link, timeout=20000)
        html = page.content().lower()

        if "add to cart" in html:
            return link, "in_stock"
        elif "out of stock" in html:
            return link, "out_of_stock"
        else:
            return link, "unknown"

    except:
        return link, "unknown"


# ================= PARALLEL CHECK =================
def check_live(links):
    results = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        pages = [browser.new_page() for _ in range(len(links))]

        with ThreadPoolExecutor(max_workers=len(links)) as executor:
            futures = [
                executor.submit(check_one, pages[i], link)
                for i, link in enumerate(links)
            ]

            for f in futures:
                link, stock = f.result()
                results[link] = stock

        browser.close()

    return results


# ================= MAIN =================
def main():
    seen = load_seen()

    # ⚡ fast fetch
    links = fetch_api()

    # ⚡ parallel verification
    current = check_live(links)

    new_items = []
    restocks = []

    for link, stock in current.items():

        if link not in seen and stock == "in_stock":
            new_items.append(link)

        elif seen.get(link) == "out_of_stock" and stock == "in_stock":
            restocks.append(link)

    # ================= ALERT =================
    if new_items or restocks:
        message = "🚨 FAST DROP 🇮🇳\n\n"

        for link in new_items:
            message += f"🆕 {link}\n"

        for link in restocks:
            message += f"🔥 {link}\n"

    else:
        message = "⚡ Checked\nNo real change."

    send_telegram(message)
    print(message)

    save_seen(current)


if __name__ == "__main__":
    main()
