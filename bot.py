#!/usr/bin/env python3
"""
Hot Wheels Collector Tracker v2
• Monitors FirstCry + Blinkit for Hot Wheels drops in Dehradun (248001)
• Uses network-request interception as the primary data source (much more
  reliable than DOM scraping)
• Alerts on: new listings, restocks, low-stock, price drops
• Silent by default — only notifies when something actually changes
  (set SILENT=false to always get a status summary)
"""

import asyncio
import json
import os
import re
import requests
from urllib.parse import quote
from playwright.async_api import async_playwright

# ── Config ─────────────────────────────────────────────────────────────────────
PINCODE = "248001"
CITY    = "Dehradun"
LAT     = 30.3165
LON     = 78.0322

# FirstCry pages to monitor — covers all Hot Wheels listings
FIRSTCRY_URLS = [
    "https://www.firstcry.com/hot-wheels/0/0/113",          # relevance (default)
    "https://www.firstcry.com/hot-wheels/0/0/113?sort=new", # newest first
]

# Blinkit search queries
BLINKIT_TERMS = ["hot wheels", "hotwheels"]

SEEN_FILE = "seen.json"
DEBUG     = os.getenv("DEBUG",  "false").lower() == "true"
# SILENT=true  → only send Telegram when something changes (recommended for CI)
# SILENT=false → also send a summary every run
SILENT    = os.getenv("SILENT", "true").lower() == "true"

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID")

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
STEALTH_JS = (
    "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
    "window.chrome={runtime:{}};"
)
BROWSER_ARGS = [
    "--no-sandbox",
    "--disable-dev-shm-usage",
    "--disable-blink-features=AutomationControlled",
]


# ── Telegram ───────────────────────────────────────────────────────────────────
def send_telegram(msg: str) -> None:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("[Telegram] Credentials missing — skipping.")
        return
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            data={
                "chat_id":                  TELEGRAM_CHAT_ID,
                "text":                     msg,
                "parse_mode":               "HTML",
                "disable_web_page_preview": "true",
            },
            timeout=15,
        )
        if not r.ok:
            print(f"[Telegram] {r.status_code}: {r.text[:200]}")
    except Exception as exc:
        print(f"[Telegram] {exc}")


# ── Persistence ────────────────────────────────────────────────────────────────
def load_seen() -> dict:
    if os.path.exists(SEEN_FILE):
        try:
            with open(SEEN_FILE, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_seen(data: dict) -> None:
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# ── FirstCry ───────────────────────────────────────────────────────────────────
async def scrape_firstcry() -> list[dict]:
    """
    Scrape FirstCry Hot Wheels listing.
    Primary strategy  : intercept XHR/fetch JSON responses (clean, structured data).
    Fallback strategy : DOM extraction with strict product-URL filtering.
    """
    collected: list[dict] = []
    seen_ids:  set[str]   = set()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=BROWSER_ARGS)

        for listing_url in FIRSTCRY_URLS:
            api_hits: list[dict] = []

            ctx = await browser.new_context(
                user_agent=UA,
                viewport={"width": 1280, "height": 900},
                locale="en-IN",
                extra_http_headers={"Accept-Language": "en-IN,en;q=0.9"},
            )
            await ctx.add_init_script(STEALTH_JS)

            # ── Inject pincode BEFORE the page loads ──────────────────────────
            await ctx.add_cookies([
                {"name": "pn",      "value": PINCODE, "domain": ".firstcry.com", "path": "/"},
                {"name": "pincode", "value": PINCODE, "domain": ".firstcry.com", "path": "/"},
                {"name": "CityId",  "value": CITY,    "domain": ".firstcry.com", "path": "/"},
            ])

            page = await ctx.new_page()

            # ── Network interception ──────────────────────────────────────────
            async def capture(resp):
                try:
                    rl = resp.url.lower()
                    ct = resp.headers.get("content-type", "")
                    if (
                        resp.status == 200
                        and "json" in ct
                        and "firstcry.com" in rl
                        and any(k in rl for k in ("listing", "brand", "search", "product", "/api"))
                    ):
                        data = await resp.json()
                        api_hits.append({"url": resp.url, "data": data})
                        if DEBUG:
                            print(f"[DEBUG][FC] Captured: {resp.url[:80]}")
                except Exception:
                    pass

            page.on("response", capture)

            print(f"[*] FirstCry → {listing_url}")
            try:
                await page.goto(listing_url, timeout=60_000, wait_until="networkidle")
            except Exception:
                try:
                    await page.goto(listing_url, timeout=60_000, wait_until="domcontentloaded")
                    await asyncio.sleep(6)
                except Exception as exc:
                    print(f"[!] FC load failed: {exc}")
                    await ctx.close()
                    continue

            # Slow scroll → triggers lazy-loaded product cards
            for _ in range(10):
                await page.evaluate("window.scrollBy(0, window.innerHeight * 1.2)")
                await asyncio.sleep(1.0)

            if DEBUG:
                slug = listing_url.rstrip("/").split("/")[-1]
                await page.screenshot(path=f"debug_fc_{slug}.png", full_page=True)

            # ── Parse intercepted API data ─────────────────────────────────────
            api_products: list[dict] = []
            for hit in api_hits:
                api_products.extend(_parse_fc_json(hit["data"]))
            if DEBUG:
                print(f"[DEBUG][FC] {len(api_hits)} API hits → {len(api_products)} products")

            # ── DOM fallback ───────────────────────────────────────────────────
            dom_products: list[dict] = await page.evaluate(r"""
            () => {
                const results = [];
                const seen    = new Set();

                function isProductHref(h) {
                    return (
                        h && h.includes("firstcry.com") &&
                        !h.includes("store-locator") &&
                        !h.includes("/brands/") &&
                        !h.includes("/category/") &&
                        !h.includes("javascript") &&
                        !h.includes("#") &&
                        (h.includes("/product-detail") || /\/\d{6,}/.test(h))
                    );
                }

                // Try specific card containers first
                let cards = [];
                for (const sel of [
                    "li[class*='product']","li[class*='Product']",
                    "div[class*='product-box']","div[class*='ProductBox']",
                    "div[class*='prd-box']","div[class*='item-box']",
                    "div[class*='prod_listing']",
                    "[data-product-id]","[data-pid]",
                ]) {
                    const found = [...document.querySelectorAll(sel)];
                    if (found.length >= 4) { cards = found; break; }
                }

                // Anchor-based fallback
                if (!cards.length) {
                    [...document.querySelectorAll("a[href]")]
                        .filter(a => isProductHref(a.href))
                        .forEach(a => {
                            let el = a;
                            for (let i = 0; i < 10; i++) {
                                if (!el.parentElement) break;
                                el = el.parentElement;
                                const t = (el.innerText||"").toUpperCase();
                                if ((el.innerText||"").includes("₹") &&
                                    (t.includes("ADD TO CART")||t.includes("NOTIFY ME")||t.includes("GET IT BY"))) {
                                    cards.push(el); break;
                                }
                            }
                        });
                }

                for (const card of cards) {
                    const anchor = card.querySelector("a[href*='product-detail']") ||
                        [...card.querySelectorAll("a[href]")].find(a => isProductHref(a.href));
                    if (!anchor) continue;
                    const href = anchor.href;
                    if (!isProductHref(href)) continue;

                    const m   = href.match(/\/(\d{5,})\//);
                    const id  = "fc_" + (m ? m[1] : href.split("?")[0].split("/").pop());
                    if (seen.has(id)) continue;

                    const ct = card.innerText || "";
                    if (!ct.includes("₹")) continue;

                    // Name
                    const nameEl = card.querySelector(
                        "[class*='prod-name'],[class*='prd-name'],[class*='product-name']," +
                        "[class*='ProductName'],[class*='prod_name'],h3,h4,h5"
                    );
                    let name = nameEl ? nameEl.innerText.trim().split("\n")[0] : "";
                    if (!name) name = anchor.title || anchor.getAttribute("aria-label") || "";
                    if (!name || name.length < 5 || name.includes("₹")) continue;

                    // Prices (sorted ascending → first = sale price)
                    const prices = (ct.match(/₹\s*[\d,]+/g)||[])
                        .map(s => parseInt(s.replace(/[^\d]/g,""),10))
                        .filter(n => n > 0).sort((a,b) => a-b);
                    const price = prices[0] ? "₹"+prices[0] : "";
                    const mrp   = prices[1] ? "₹"+prices[1] : price;

                    // Low-stock badge
                    const leftM = ct.match(/(\d+)\s+[Ll]eft/);
                    const leftCount = leftM ? parseInt(leftM[1],10) : null;

                    // Stock
                    const up = ct.toUpperCase();
                    let stock;
                    if (up.includes("ADD TO CART")||up.includes("ADD TO BAG")||
                        up.includes("BUY NOW")||up.includes("GET IT BY")) {
                        stock = leftCount !== null ? "low_stock" : "in_stock";
                    } else if (up.includes("NOTIFY ME")||up.includes("OUT OF STOCK")||up.includes("SOLD OUT")) {
                        stock = "out_of_stock";
                    } else {
                        continue;
                    }

                    seen.add(id);
                    results.push({id, name, url: href, price, mrp, stock, leftCount, source:"firstcry"});
                }
                return results;
            }
            """)

            # Merge: API data takes precedence
            api_ids = {p["id"] for p in api_products}
            merged  = list(api_products)
            for p in dom_products:
                if p["id"] not in api_ids:
                    merged.append(p)

            for p in merged:
                if p["id"] not in seen_ids:
                    collected.append(p)
                    seen_ids.add(p["id"])

            await ctx.close()

        await browser.close()

    return collected


def _parse_fc_json(obj, _d=0) -> list[dict]:
    """Walk FirstCry JSON tree and pull out product objects."""
    out = []
    if _d > 14 or obj is None:
        return out
    if isinstance(obj, list):
        for item in obj:
            out.extend(_parse_fc_json(item, _d + 1))
    elif isinstance(obj, dict):
        kl = {k.lower() for k in obj}
        if (
            any(k in kl for k in ("productid","pid","itemid"))
            and any(k in kl for k in ("productname","name","title","itemname"))
            and any(k in kl for k in ("price","saleprice","sellingprice","mrp","offerprice"))
        ):
            try:
                raw_id  = (obj.get("ProductId") or obj.get("productId") or
                           obj.get("pid") or obj.get("ItemId") or obj.get("id") or "")
                name    = (obj.get("ProductName") or obj.get("productName") or
                           obj.get("ItemName") or obj.get("name") or obj.get("title") or "")
                sale_p  = (obj.get("SalePrice") or obj.get("salePrice") or
                           obj.get("SellingPrice") or obj.get("price") or 0)
                mrp_v   = obj.get("MRP") or obj.get("mrp") or sale_p
                avail   = (obj.get("IsAvailable") or obj.get("isAvailable") or
                           obj.get("InStock") or obj.get("inStock") or False)
                url_p   = (obj.get("ProductUrl") or obj.get("productUrl") or
                           obj.get("Url") or obj.get("url") or "")
                if isinstance(url_p, str) and url_p.startswith("/"):
                    url_p = "https://www.firstcry.com" + url_p

                if raw_id and name:
                    out.append({
                        "id":       f"fc_{raw_id}",
                        "name":     str(name).strip(),
                        "url":      url_p or "https://www.firstcry.com/hot-wheels/0/0/113",
                        "price":    f"₹{int(sale_p)}" if sale_p else "",
                        "mrp":      f"₹{int(mrp_v)}"  if mrp_v  else "",
                        "stock":    "in_stock" if avail else "out_of_stock",
                        "leftCount": None,
                        "source":   "firstcry",
                    })
                    return out  # Don't recurse into a product node
            except Exception:
                pass
        for v in obj.values():
            out.extend(_parse_fc_json(v, _d + 1))
    return out


# ── Blinkit ────────────────────────────────────────────────────────────────────
async def scrape_blinkit() -> list[dict]:
    """
    Scrape Blinkit for Hot Wheels availability.
    Sets GPS to Dehradun coordinates so Blinkit returns correct local stock.
    """
    collected: list[dict] = []
    seen_ids:  set[str]   = set()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=BROWSER_ARGS)

        for term in BLINKIT_TERMS:
            api_hits: list[dict] = []

            ctx = await browser.new_context(
                user_agent=UA,
                viewport={"width": 1280, "height": 900},
                locale="en-IN",
                geolocation={"latitude": LAT, "longitude": LON},
                permissions=["geolocation"],
            )
            await ctx.add_init_script(STEALTH_JS)

            page = await ctx.new_page()

            async def bl_capture(resp):
                try:
                    rl = resp.url.lower()
                    ct = resp.headers.get("content-type", "")
                    if resp.status == 200 and "json" in ct and "blinkit.com" in rl:
                        data = await resp.json()
                        api_hits.append({"url": resp.url, "data": data})
                        if DEBUG:
                            print(f"[DEBUG][BL] Captured: {resp.url[:80]}")
                except Exception:
                    pass

            page.on("response", bl_capture)

            url = f"https://blinkit.com/s/?q={quote(term)}"
            print(f"[*] Blinkit → {url}")
            try:
                await page.goto(url, timeout=45_000, wait_until="networkidle")
            except Exception:
                await page.goto(url, timeout=45_000, wait_until="domcontentloaded")
                await asyncio.sleep(5)

            await asyncio.sleep(2)

            # Dismiss location/cookie popups
            for txt in ["Allow", "Use my location", "Detect", "Skip", "Continue", "Allow location"]:
                try:
                    btn = page.get_by_text(txt, exact=True).first
                    if await btn.is_visible(timeout=800):
                        await btn.click()
                        await asyncio.sleep(1)
                except Exception:
                    pass

            for _ in range(5):
                await page.evaluate("window.scrollBy(0, window.innerHeight)")
                await asyncio.sleep(1)

            if DEBUG:
                await page.screenshot(path=f"debug_bl_{term.replace(' ','_')}.png", full_page=True)

            # Parse API data
            api_products: list[dict] = []
            for hit in api_hits:
                api_products.extend(_parse_bl_json(hit["data"], term))
            if DEBUG:
                print(f"[DEBUG][BL] {len(api_hits)} API hits → {len(api_products)} products")

            # DOM fallback
            dom_products: list[dict] = await page.evaluate(r"""
            (term) => {
                const results = [];
                const cards = [...document.querySelectorAll(
                    "[class*='Product__UpdatedPlpProductContainer']," +
                    "[class*='plp-product'],[class*='ProductCard']," +
                    "[data-testid*='product-card'],[data-testid*='plp-product']"
                )];

                cards.forEach((card, idx) => {
                    const nameEl = card.querySelector(
                        "[class*='Product__PLPName'],[class*='product-name']," +
                        "[class*='ProductName'],[class*='name']"
                    );
                    const name = (nameEl||{}).innerText?.trim() || "";
                    if (!name) return;

                    const priceEl = card.querySelector("[class*='Price'],[class*='price']");
                    const priceText = (priceEl||{}).innerText?.trim() || "";
                    const priceM = priceText.match(/[\d,]+/);
                    const price  = priceM ? "₹" + priceM[0].replace(",","") : "";

                    const ct  = (card.innerText||"").toUpperCase();
                    const oos = ct.includes("OUT OF STOCK") || ct.includes("NOT AVAILABLE");
                    const atc = ct.includes("ADD") || !!card.querySelector("button");

                    let stock = oos ? "out_of_stock" : (atc ? "in_stock" : "unknown");
                    if (stock === "unknown") return;

                    results.push({
                        id:       `blinkit_dom_${name.toLowerCase().replace(/\W+/g,"_")}_${idx}`,
                        name,
                        url:      "https://blinkit.com/s/?q=hot+wheels",
                        price,
                        mrp:      price,
                        stock,
                        leftCount: null,
                        source:   "blinkit",
                    });
                });
                return results;
            }
            """, term)

            api_ids = {p["id"] for p in api_products}
            merged  = list(api_products)
            for p in dom_products:
                if p["id"] not in api_ids:
                    merged.append(p)

            for p in merged:
                if p["id"] not in seen_ids:
                    collected.append(p)
                    seen_ids.add(p["id"])

            await ctx.close()

        await browser.close()

    return collected


def _parse_bl_json(obj, term: str, _d=0) -> list[dict]:
    """Walk Blinkit JSON tree and pull out Hot Wheels product objects."""
    out = []
    if _d > 16 or obj is None:
        return out
    if isinstance(obj, list):
        for item in obj:
            out.extend(_parse_bl_json(item, term, _d + 1))
    elif isinstance(obj, dict):
        kl = {k.lower() for k in obj}
        if (
            any(k in kl for k in ("id","product_id","item_id"))
            and any(k in kl for k in ("name","product_name","display_name"))
            and any(k in kl for k in ("price","mrp","sale_price","selling_price"))
        ):
            try:
                raw_id  = obj.get("id") or obj.get("product_id") or obj.get("item_id") or ""
                name    = (obj.get("name") or obj.get("product_name") or
                           obj.get("display_name") or "")
                price_v = (obj.get("price") or obj.get("sale_price") or
                           obj.get("selling_price") or 0)
                mrp_v   = obj.get("mrp") or price_v
                avail   = (obj.get("in_stock") or obj.get("available") or
                           obj.get("is_available") or False)
                brand   = str(obj.get("brand","") or obj.get("brand_name","")).lower()

                nl = str(name).lower()
                is_hw = (
                    "hot wheel" in nl or "hotwheels" in nl or "hot_wheel" in nl
                    or brand in ("hot wheels","hotwheels","mattel")
                )
                if raw_id and name and is_hw:
                    out.append({
                        "id":       f"blinkit_{raw_id}",
                        "name":     str(name).strip(),
                        "url":      f"https://blinkit.com/s/?q={quote(term)}",
                        "price":    f"₹{int(price_v)}" if price_v else "",
                        "mrp":      f"₹{int(mrp_v)}"   if mrp_v   else "",
                        "stock":    "in_stock" if avail else "out_of_stock",
                        "leftCount": None,
                        "source":   "blinkit",
                    })
                    return out
            except Exception:
                pass
        for v in obj.values():
            out.extend(_parse_bl_json(v, term, _d + 1))
    return out


# ── Diff ───────────────────────────────────────────────────────────────────────
def compute_changes(current: dict, seen: dict) -> dict:
    new_listings, restocks, low_stocks, price_drops, went_oos = [], [], [], [], []

    for pid, data in current.items():
        stock      = data["stock"]
        prev       = seen.get(pid)
        prev_stock = prev.get("stock") if prev else None
        prev_price = prev.get("price") if prev else None

        if stock in ("in_stock", "low_stock"):
            if prev is None:
                (low_stocks if stock == "low_stock" else new_listings).append(data)
            elif prev_stock == "out_of_stock":
                (low_stocks if stock == "low_stock" else restocks).append(data)
            elif prev_stock == "in_stock" and stock == "low_stock":
                low_stocks.append(data)

            # Price drop
            if prev_price and data.get("price") and prev_price != data["price"]:
                try:
                    old = int(re.sub(r"[^\d]", "", prev_price))
                    new = int(re.sub(r"[^\d]", "", data["price"]))
                    if new < old:
                        price_drops.append({**data, "prev_price": prev_price})
                except Exception:
                    pass

        elif stock == "out_of_stock" and prev_stock in ("in_stock", "low_stock"):
            went_oos.append(data)

    return {
        "new_listings": new_listings,
        "restocks":     restocks,
        "low_stocks":   low_stocks,
        "price_drops":  price_drops,
        "went_oos":     went_oos,
    }


# ── Message builders ───────────────────────────────────────────────────────────
def _src(d: dict) -> str:
    return "🛒 FC" if d.get("source") == "firstcry" else "⚡ BL"


def build_alert(changes: dict) -> str | None:
    lines = ["🚨 <b>Hot Wheels Alert!</b> 🏎️\n"]

    if changes["new_listings"]:
        lines.append("🆕 <b>NEW listing — in stock now:</b>")
        for d in changes["new_listings"]:
            lines.append(f"  [{_src(d)}] <b>{d['name']}</b>  {d['price']}\n  {d['url']}")

    if changes["restocks"]:
        lines.append("\n🔥 <b>Back in stock:</b>")
        for d in changes["restocks"]:
            lines.append(f"  [{_src(d)}] <b>{d['name']}</b>  {d['price']}\n  {d['url']}")

    if changes["low_stocks"]:
        lines.append("\n⚠️ <b>Almost gone — grab it now:</b>")
        for d in changes["low_stocks"]:
            badge = f" ({d['leftCount']} left!)" if d.get("leftCount") else " (low stock)"
            lines.append(f"  [{_src(d)}] <b>{d['name']}</b>{badge}  {d['price']}\n  {d['url']}")

    if changes["price_drops"]:
        lines.append("\n💸 <b>Price drop:</b>")
        for d in changes["price_drops"]:
            lines.append(
                f"  [{_src(d)}] <b>{d['name']}</b>  "
                f"<s>{d['prev_price']}</s> → <b>{d['price']}</b>\n  {d['url']}"
            )

    if len(lines) == 1:   # only header
        return None

    return "\n".join(lines)


def build_status(products: list[dict], changes: dict) -> str:
    fc = [p for p in products if p.get("source") == "firstcry"]
    bl = [p for p in products if p.get("source") == "blinkit"]

    lines = [f"📊 <b>Hot Wheels Status</b> — {CITY} {PINCODE}\n"]

    for label, src in [("🛒 FirstCry", fc), ("⚡ Blinkit", bl)]:
        if src:
            ins  = sum(1 for p in src if p["stock"] in ("in_stock","low_stock"))
            oos  = len(src) - ins
            lines.append(f"{label}: <b>{ins} in stock</b>  |  {oos} out of stock  (total {len(src)})")
        else:
            lines.append(f"{label}: no data")

    went = changes.get("went_oos", [])
    if went:
        lines.append(f"\n🔴 Just went out of stock: {', '.join(d['name'][:40] for d in went)}")

    return "\n".join(lines)


# ── Main ───────────────────────────────────────────────────────────────────────
async def main_async() -> None:
    seen = load_seen()

    all_products: list[dict] = []

    # ── FirstCry ───────────────────────────────────────────────────────────────
    print("[*] Scraping FirstCry …")
    try:
        fc = await scrape_firstcry()
        print(f"[*] FirstCry → {len(fc)} products")
        all_products.extend(fc)
    except Exception as exc:
        print(f"[!] FirstCry: {exc}")
        send_telegram(f"⚠️ <b>FirstCry scrape error</b>\n<code>{str(exc)[:200]}</code>")

    # ── Blinkit ────────────────────────────────────────────────────────────────
    print("[*] Scraping Blinkit …")
    try:
        bl = await scrape_blinkit()
        print(f"[*] Blinkit → {len(bl)} products")
        all_products.extend(bl)
    except Exception as exc:
        print(f"[!] Blinkit: {exc}")
        send_telegram(f"⚠️ <b>Blinkit scrape error</b>\n<code>{str(exc)[:200]}</code>")

    # Nothing at all scraped → warn
    if not all_products:
        send_telegram(
            "⚠️ <b>Hot Wheels Tracker — 0 products found</b>\n\n"
            "Both FirstCry and Blinkit returned nothing.\n"
            "Causes: bot detection, layout change, network error.\n\n"
            "Run locally: <code>DEBUG=true python bot.py</code>"
        )
        return

    # ── Diff ───────────────────────────────────────────────────────────────────
    current = {p["id"]: p for p in all_products}
    changes = compute_changes(current, seen)

    # ── Notify ─────────────────────────────────────────────────────────────────
    alert = build_alert(changes)
    if alert:
        send_telegram(alert)
        print("\n" + alert)
    elif not SILENT:
        status = build_status(all_products, changes)
        send_telegram(status)
        print("\n" + status)
    else:
        # Silent mode: print summary to logs but don't Telegram
        fc_in = sum(1 for p in all_products if p["source"]=="firstcry" and p["stock"] in ("in_stock","low_stock"))
        bl_in = sum(1 for p in all_products if p["source"]=="blinkit"  and p["stock"] in ("in_stock","low_stock"))
        print(f"[=] No changes. FC: {fc_in} in stock | BL: {bl_in} in stock")

    # ── Persist ────────────────────────────────────────────────────────────────
    save_seen({
        pid: {
            "stock":  d["stock"],
            "name":   d["name"],
            "price":  d.get("price", ""),
            "source": d.get("source", ""),
        }
        for pid, d in current.items()
    })


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
