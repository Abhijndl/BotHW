import asyncio
import json
import os
import requests
from playwright.async_api import async_playwright

# ── Config ────────────────────────────────────────────────────────────────────
LISTING_URL = "https://www.firstcry.com/Hot%20Wheels/0/0/113?q=as_hotwhe&asid=48299"
SEEN_FILE   = "seen.json"
DEBUG       = os.getenv("DEBUG", "false").lower() == "true"

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID")


# ── Telegram ──────────────────────────────────────────────────────────────────
def send_telegram(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("[Telegram] Token or Chat ID missing — skipping send.")
        return
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            data={
                "chat_id":    TELEGRAM_CHAT_ID,
                "text":       message,
                "parse_mode": "HTML",
            },
            timeout=10,
        )
        if not resp.ok:
            print(f"[Telegram] Error {resp.status_code}: {resp.text}")
    except Exception as e:
        print(f"[Telegram] Exception: {e}")


# ── State storage ─────────────────────────────────────────────────────────────
def load_seen():
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE) as f:
            return json.load(f)
    return {}


def save_seen(data):
    with open(SEEN_FILE, "w") as f:
        json.dump(data, f, indent=2)


# ── Scraper ───────────────────────────────────────────────────────────────────
async def scrape_listing():
    """
    One single browser visit to the listing page.
    Extracts every product card: name, URL, price, and in/out-of-stock status.
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 900},
            locale="en-IN",
        )

        # Hide Playwright's webdriver flag so the site doesn't block us
        await context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )

        page = await context.new_page()

        print(f"[*] Loading listing page …")
        try:
            await page.goto(LISTING_URL, timeout=30000, wait_until="networkidle")
        except Exception:
            # networkidle can time-out on heavy pages — domcontentloaded is fine too
            await page.goto(LISTING_URL, timeout=30000, wait_until="domcontentloaded")
            await asyncio.sleep(3)

        # Scroll down a few times to trigger lazy-loaded product cards
        for _ in range(4):
            await page.evaluate("window.scrollBy(0, window.innerHeight * 1.5)")
            await asyncio.sleep(1.2)

        # Save a debug screenshot so you can verify the page looks right
        if DEBUG:
            await page.screenshot(path="debug_listing.png", full_page=True)
            print("[DEBUG] Screenshot saved → debug_listing.png")

        # Extract everything we need in one JS evaluation (fast — no round-trips)
        products = await page.evaluate("""
        () => {
            const results = [];

            // ── Find product cards ──────────────────────────────────────────
            // Try selectors from most-specific to most-generic.
            // The first one that gives more than 2 elements wins.
            const CARD_SELECTORS = [
                '[class*="prod-box"]',
                '[class*="prd-box"]',
                '[class*="product-card"]',
                '[class*="ProductCard"]',
                '[class*="prd-grid-sec"] > div',
                '[class*="item-card"]',
                '[class*="item-box"]',
                '[class*="col-box"]',
                '[class*="product-item"]',
            ];

            let cards = [];
            for (const sel of CARD_SELECTORS) {
                const found = document.querySelectorAll(sel);
                if (found.length > 2) { cards = found; break; }
            }

            // Fallback: look for anchors that point to product pages
            if (cards.length === 0) {
                cards = document.querySelectorAll('a[href*="/toys/"]');
            }

            cards.forEach(card => {
                // ── URL ─────────────────────────────────────────────────────
                const anchor = card.querySelector('a[href]') || (card.tagName === 'A' ? card : null);
                if (!anchor) return;
                const url = anchor.href;
                if (!url || url === window.location.href) return;

                // ── Name ────────────────────────────────────────────────────
                const nameEl = card.querySelector(
                    '[class*="prod-name"], [class*="prd-name"], [class*="product-name"], ' +
                    '[class*="ProductName"], [class*="item-name"], h3, h4'
                );
                const name = nameEl ? nameEl.innerText.trim() : '';
                if (!name || name.length < 3) return;

                // ── Price ───────────────────────────────────────────────────
                // Grab the first price-looking element (sale price)
                const priceEl = card.querySelector(
                    '[class*="price"]:not([class*="strike"]):not([class*="mrp"]), ' +
                    '[class*="Price"]:not([class*="Strike"]):not([class*="Mrp"])'
                );
                const price = priceEl ? priceEl.innerText.trim().replace(/\\s+/g, ' ') : '';

                // ── Stock status ─────────────────────────────────────────────
                const text = card.innerText.toLowerCase();
                let stock = 'unknown';
                if (text.includes('add to cart') || text.includes('add to bag') || text.includes('buy now')) {
                    stock = 'in_stock';
                } else if (text.includes('out of stock') || text.includes('notify me') || text.includes('sold out')) {
                    stock = 'out_of_stock';
                }

                // Use the clean URL path as a stable ID (no query params)
                const id = url.split('?')[0].replace(/\\/$/, '');

                // Deduplicate
                if (!results.find(r => r.id === id)) {
                    results.push({ id, name, url, price, stock });
                }
            });

            return results;
        }
        """)

        await browser.close()

    return products


# ── Main ──────────────────────────────────────────────────────────────────────
async def main_async():
    seen = load_seen()

    print("[*] Checking Hot Wheels on FirstCry …")
    products = await scrape_listing()
    print(f"[*] Found {len(products)} products")

    if DEBUG and products:
        for prod in products[:5]:
            print(f"[DEBUG] {prod}")

    # ── No products at all → something went wrong ─────────────────────────────
    if not products:
        msg = (
            "⚠️ <b>Hot Wheels bot warning</b>\n"
            "0 products found on the listing page.\n"
            "The site may have changed its HTML structure.\n"
            "Run with DEBUG=true locally to take a screenshot."
        )
        print("[!] " + msg.replace("\n", " "))
        send_telegram(msg)
        return

    # ── Detect new items and restocks ─────────────────────────────────────────
    current   = {p["id"]: p for p in products}
    new_items = []
    restocks  = []

    for pid, data in current.items():
        stock      = data["stock"]
        prev       = seen.get(pid, {})
        prev_stock = prev.get("stock") if isinstance(prev, dict) else None

        if stock == "in_stock":
            if pid not in seen:
                new_items.append(data)
            elif prev_stock == "out_of_stock":
                restocks.append(data)

    # ── Build alert message ───────────────────────────────────────────────────
    if new_items or restocks:
        lines = ["🚨 <b>Hot Wheels Alert!</b> 🏎️\n"]

        if new_items:
            lines.append("🆕 <b>New — just listed &amp; in stock:</b>")
            for d in new_items:
                price_str = f"  ·  {d['price']}" if d["price"] else ""
                lines.append(f"• <b>{d['name']}</b>{price_str}\n  {d['url']}\n")

        if restocks:
            lines.append("🔥 <b>Back in stock:</b>")
            for d in restocks:
                price_str = f"  ·  {d['price']}" if d["price"] else ""
                lines.append(f"• <b>{d['name']}</b>{price_str}\n  {d['url']}\n")

        message = "\n".join(lines)

    else:
        in_stock_count = sum(1 for p in products if p["stock"] == "in_stock")
        oos_count      = sum(1 for p in products if p["stock"] == "out_of_stock")
        message = (
            f"⚡ Checked {len(products)} Hot Wheels — "
            f"{in_stock_count} in stock, {oos_count} out of stock. No new drops."
        )

    send_telegram(message)
    print(message)

    # ── Save state ────────────────────────────────────────────────────────────
    save_seen({
        pid: {"stock": d["stock"], "name": d["name"]}
        for pid, d in current.items()
    })


def main():
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
