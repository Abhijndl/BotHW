import asyncio
import json
import os
import requests
from playwright.async_api import async_playwright

# ── Config ────────────────────────────────────────────────────────────────────
LISTING_URL = "https://www.firstcry.com/hot-wheels/5/0/113"
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
            data={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"},
            timeout=10,
        )
        if not resp.ok:
            print(f"[Telegram] Error {resp.status_code}: {resp.text}")
    except Exception as e:
        print(f"[Telegram] Exception: {e}")


# ── State ─────────────────────────────────────────────────────────────────────
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
        await context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )

        page = await context.new_page()

        print("[*] Loading FirstCry Hot Wheels page …")
        try:
            await page.goto(LISTING_URL, timeout=40000, wait_until="networkidle")
        except Exception:
            await page.goto(LISTING_URL, timeout=40000, wait_until="domcontentloaded")
            await asyncio.sleep(4)

        # Wait for at least one price to appear (proves products are rendered)
        try:
            await page.wait_for_selector("text=₹", timeout=15000)
        except Exception:
            print("[!] Price elements not found — page may not have loaded products.")

        # Scroll slowly to trigger lazy-loaded cards
        for _ in range(6):
            await page.evaluate("window.scrollBy(0, window.innerHeight)")
            await asyncio.sleep(1.2)

        # Scroll back to top so full-page screenshot captures everything
        await page.evaluate("window.scrollTo(0, 0)")
        await asyncio.sleep(0.5)

        if DEBUG:
            await page.screenshot(path="debug_listing.png", full_page=True)
            html = await page.content()
            with open("debug_listing.html", "w", encoding="utf-8") as fh:
                fh.write(html)
            print("[DEBUG] Saved debug_listing.png and debug_listing.html")

        products = await page.evaluate("""
        () => {
            const results = [];
            const seenIds = new Set();

            // ── STRATEGY 1: window.__NEXT_DATA__ (fastest, most reliable) ──
            // Many React/Next.js sites embed all product data as JSON in the page.
            try {
                const nd = window.__NEXT_DATA__;
                if (nd) {
                    // Walk the props tree to find product arrays
                    const json = JSON.stringify(nd);
                    // Look for objects with url + price + (addToCart or outOfStock)
                    // This is a signal the site uses Next.js data embedding
                    console.log('[DEBUG] __NEXT_DATA__ found, keys:', Object.keys(nd).join(','));
                }
            } catch(e) {}

            // ── STRATEGY 2: Walk every link on the page ───────────────────
            // Any anchor pointing to a firstcry product page is a candidate.
            // We then read the card around it for name, price, and stock.
            const allAnchors = Array.from(document.querySelectorAll('a[href]'));
            const productAnchors = allAnchors.filter(a => {
                const h = a.href || '';
                // firstcry product URLs contain numeric IDs like /12345/ or end with item codes
                return (
                    h.includes('firstcry.com') &&
                    !h.includes('/brands/') &&
                    !h.includes('/category/') &&
                    !h.includes('javascript') &&
                    (h.match(/\\/\\d{5,}/) || h.match(/[a-z0-9]+-[a-z0-9]+-\\d/i))
                );
            });

            productAnchors.forEach(anchor => {
                const url = anchor.href;
                const id  = url.split('?')[0].replace(/\\/$/, '');
                if (!id || seenIds.has(id)) return;

                // Walk up from the anchor to find the card root.
                // Card root = ancestor that has BOTH a ₹ price AND a button.
                let card = anchor;
                let found = false;
                for (let i = 0; i < 12; i++) {
                    if (!card.parentElement) break;
                    card = card.parentElement;
                    const t = card.innerText || '';
                    const hasPrice  = t.includes('₹');
                    const hasButton = card.querySelector('button') ||
                                      t.toUpperCase().includes('ADD TO CART') ||
                                      t.toUpperCase().includes('NOTIFY ME');
                    if (hasPrice && hasButton) { found = true; break; }
                }
                if (!found) return;

                const cardText = (card.innerText || '').toUpperCase();

                // ── Name ─────────────────────────────────────────────────
                // Prefer elements with "name" in class, fall back to headings.
                const nameSelectors = [
                    '[class*="prod-name"]', '[class*="prd-name"]',
                    '[class*="product-name"]', '[class*="ProductName"]',
                    '[class*="item-name"]', '[class*="title"]',
                    'h2', 'h3', 'h4', 'h5', 'p'
                ];
                let name = '';
                for (const sel of nameSelectors) {
                    const el = card.querySelector(sel);
                    if (el) {
                        const t = el.innerText.trim();
                        // A product name: at least 5 chars, contains "Hot Wheels" or similar
                        if (t.length >= 5 && !t.includes('₹')) { name = t; break; }
                    }
                }
                if (!name) {
                    // Last resort: first text node longer than 10 chars inside the card
                    const walker = document.createTreeWalker(card, NodeFilter.SHOW_TEXT);
                    let node;
                    while ((node = walker.nextNode())) {
                        const t = node.textContent.trim();
                        if (t.length > 10 && !t.includes('₹') && !t.includes('★')) {
                            name = t; break;
                        }
                    }
                }
                if (!name || name.length < 4) return;

                // ── Price ─────────────────────────────────────────────────
                // Grab first ₹ occurrence that looks like a current price
                const priceMatch = (card.innerText || '').match(/₹\s*[\d,]+(\.\d+)?/);
                const price = priceMatch ? priceMatch[0].replace(/\s+/, '') : '';

                // ── Low-stock badge ("1 Left", "2 Left" …) ───────────────
                const leftMatch = (card.innerText || '').match(/(\d+)\s+Left/i);
                const leftCount = leftMatch ? parseInt(leftMatch[1], 10) : null;

                // ── Stock status ──────────────────────────────────────────
                let stock = 'unknown';
                if (cardText.includes('ADD TO CART') || cardText.includes('ADD TO BAG')) {
                    stock = leftCount !== null ? 'low_stock' : 'in_stock';
                } else if (
                    cardText.includes('NOTIFY ME') ||
                    cardText.includes('OUT OF STOCK') ||
                    cardText.includes('SOLD OUT')
                ) {
                    stock = 'out_of_stock';
                }

                // Skip completely unknown stock (no button found = probably not a product card)
                if (stock === 'unknown') return;

                seenIds.add(id);
                results.push({ id, name, url, price, stock, leftCount });
            });

            // ── STRATEGY 3: Button-text scan (fallback) ────────────────────
            // If strategy 2 found nothing, scan for buttons directly.
            if (results.length === 0) {
                const allEls = Array.from(document.querySelectorAll('button, div, span, a'));
                allEls.forEach(btn => {
                    const t = (btn.innerText || '').trim().toUpperCase();
                    if (t !== 'ADD TO CART' && t !== 'NOTIFY ME') return;

                    let card = btn;
                    for (let i = 0; i < 10; i++) {
                        if (!card.parentElement) break;
                        card = card.parentElement;
                        if ((card.innerText || '').includes('₹')) break;
                    }

                    const anchor = card.querySelector('a[href*="firstcry"]') ||
                                   card.querySelector('a[href^="/"]');
                    if (!anchor) return;

                    const url = anchor.href;
                    const id  = url.split('?')[0].replace(/\\/$/, '');
                    if (seenIds.has(id)) return;

                    const priceMatch = (card.innerText || '').match(/₹\s*[\d,]+/);
                    const price = priceMatch ? priceMatch[0] : '';

                    const nameEl = card.querySelector('h2,h3,h4,h5,p,[class*="name"],[class*="title"]');
                    const name   = nameEl ? nameEl.innerText.trim() : '';
                    if (!name || name.length < 4) return;

                    const leftMatch = (card.innerText || '').match(/(\\d+)\\s+Left/i);
                    const leftCount = leftMatch ? parseInt(leftMatch[1], 10) : null;

                    const stock = t === 'ADD TO CART'
                        ? (leftCount ? 'low_stock' : 'in_stock')
                        : 'out_of_stock';

                    seenIds.add(id);
                    results.push({ id, name, url, price, stock, leftCount });
                });
            }

            return results;
        }
        """)

        if DEBUG:
            print(f"[DEBUG] Raw JS returned {len(products)} products")
            for prod in products[:5]:
                print(f"[DEBUG] {prod}")

        await browser.close()

    return products


# ── Main ──────────────────────────────────────────────────────────────────────
async def main_async():
    seen = load_seen()

    print("[*] Checking Hot Wheels on FirstCry …")
    products = await scrape_listing()
    print(f"[*] Found {len(products)} products")

    if not products:
        msg = (
            "⚠️ <b>Hot Wheels bot warning</b>\n"
            "0 products scraped. FirstCry may have changed its HTML.\n"
            "Run locally with <code>DEBUG=true</code> to inspect."
        )
        print("[!] 0 products found — check selectors.")
        send_telegram(msg)
        return

    current   = {p["id"]: p for p in products}
    new_items = []
    restocks  = []
    low_stock = []

    for pid, data in current.items():
        stock      = data["stock"]
        prev       = seen.get(pid, {})
        prev_stock = prev.get("stock") if isinstance(prev, dict) else None

        if stock in ("in_stock", "low_stock"):
            if pid not in seen:
                (low_stock if stock == "low_stock" else new_items).append(data)
            elif prev_stock == "out_of_stock":
                (low_stock if stock == "low_stock" else restocks).append(data)
            elif prev_stock == "in_stock" and stock == "low_stock":
                low_stock.append(data)

    if low_stock or restocks or new_items:
        lines = ["🚨 <b>Hot Wheels Alert!</b> 🏎️\n"]

        if low_stock:
            lines.append("🔴 <b>HURRY — ALMOST GONE:</b>")
            for d in low_stock:
                n     = d.get("leftCount")
                badge = f" <b>({n} Left!)</b>" if n else " <b>(Low stock!)</b>"
                price = f"  ·  {d['price']}" if d["price"] else ""
                lines.append(f"• <b>{d['name']}</b>{badge}{price}\n  {d['url']}\n")

        if restocks:
            lines.append("🔥 <b>Back in stock:</b>")
            for d in restocks:
                price = f"  ·  {d['price']}" if d["price"] else ""
                lines.append(f"• <b>{d['name']}</b>{price}\n  {d['url']}\n")

        if new_items:
            lines.append("🆕 <b>New listing — in stock now:</b>")
            for d in new_items:
                price = f"  ·  {d['price']}" if d["price"] else ""
                lines.append(f"• <b>{d['name']}</b>{price}\n  {d['url']}\n")

        message = "\n".join(lines)
    else:
        in_stk = sum(1 for p in products if p["stock"] in ("in_stock", "low_stock"))
        oos    = sum(1 for p in products if p["stock"] == "out_of_stock")
        message = (
            f"⚡ Checked {len(products)} Hot Wheels — "
            f"{in_stk} in stock, {oos} out of stock. No new drops."
        )

    send_telegram(message)
    print(message)

    save_seen({
        pid: {"stock": d["stock"], "name": d["name"]}
        for pid, d in current.items()
    })


def main():
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
