#!/usr/bin/env python3
"""
Hot Wheels Collector Tracker v3
Sites  : FirstCry · Blinkit · Hamleys India
Pincode: 248001 (Dehradun)

Core strategy
─────────────
Playwright loads each page (works on GitHub Actions — proven by v1).
Then we extract window.__NEXT_DATA__ / window.__REDUX_STATE__ as raw JSON
from inside the page — bypassing every CSS selector / layout change.
Hamleys uses Magento 2, so we fall back to well-known Magento selectors.
"""

import asyncio, json, os, re, subprocess, sys, requests
from urllib.parse import quote
from playwright.async_api import async_playwright


def ensure_browser() -> None:
    """
    Guarantee Chromium is installed and on a path Playwright can actually find.

    Root cause: on Render (and some other hosts) the default browser cache dir
    is /opt/render/.cache/ms-playwright, but after a fresh deploy that directory
    may not exist yet, or a Playwright version bump changes the expected
    subdirectory name, leaving a dangling path.  We pin PLAYWRIGHT_BROWSERS_PATH
    to a location inside the repo working directory so it is always writable and
    always consistent between install and launch.
    """
    # Pin the browser cache to a stable, writable location in the working dir.
    browsers_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".pw-browsers")
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = browsers_path

    # Check whether Chromium's executable is actually present under that path.
    needs_install = True
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            exe = p.chromium.executable_path
        needs_install = not os.path.isfile(exe)
    except Exception:
        pass  # If even the check fails, we definitely need to install.

    if needs_install:
        print(f"[*] Chromium not found under {browsers_path} — installing …")
        result = subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium", "--with-deps"],
            check=False,
        )
        if result.returncode != 0:
            print("[!] playwright install exited with code", result.returncode)
    else:
        print(f"[*] Chromium found — skipping install.")

# ── Config ─────────────────────────────────────────────────────────────────────
PINCODE = "248001"
CITY    = "Dehradun"
LAT, LON = 30.3165, 78.0322

FIRSTCRY_URLS = [
    "https://www.firstcry.com/hot-wheels/0/0/113",          # all HW, default sort
    "https://www.firstcry.com/hot-wheels/0/0/113?sort=new", # newest first
]
BLINKIT_TERMS  = ["hot wheels", "hotwheels"]
HAMLEYS_URLS   = [
    "https://www.hamleys.in/catalogsearch/result/?q=hot+wheels",
    "https://www.hamleys.in/toys/die-cast-and-model-cars.html",
]

SEEN_FILE = "seen.json"
DEBUG  = os.getenv("DEBUG",  "false").lower() == "true"
SILENT = os.getenv("SILENT", "true" ).lower() == "true"

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID")

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
STEALTH = (
    "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
    "window.chrome={runtime:{}};"
)
BARGS = ["--no-sandbox","--disable-dev-shm-usage",
         "--disable-blink-features=AutomationControlled"]


# ── Telegram ───────────────────────────────────────────────────────────────────
def tg(msg: str) -> None:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            data={"chat_id": TELEGRAM_CHAT_ID, "text": msg,
                  "parse_mode": "HTML", "disable_web_page_preview": "true"},
            timeout=15)
        if not r.ok:
            print(f"[TG] {r.status_code}: {r.text[:120]}")
    except Exception as e:
        print(f"[TG] {e}")


def tg_file(path: str, caption: str = "") -> None:
    """Send a file (screenshot) to Telegram for debugging."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        with open(path, "rb") as f:
            requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto",
                data={"chat_id": TELEGRAM_CHAT_ID, "caption": caption[:1024]},
                files={"photo": f}, timeout=30)
    except Exception as e:
        print(f"[TG file] {e}")


# ── Persistence ────────────────────────────────────────────────────────────────
def load_seen():
    if os.path.exists(SEEN_FILE):
        try:
            with open(SEEN_FILE, encoding="utf-8") as f: return json.load(f)
        except: pass
    return {}

def save_seen(data):
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# ── JSON product extraction ────────────────────────────────────────────────────
def _walk(obj, _d=0):
    """Yield every dict in a JSON tree (DFS)."""
    if _d > 20 or obj is None: return
    if isinstance(obj, list):
        for i in obj: yield from _walk(i, _d+1)
    elif isinstance(obj, dict):
        yield obj
        for v in obj.values(): yield from _walk(v, _d+1)


def extract_products_from_json(data, source: str, fallback_url: str) -> list[dict]:
    """
    Walk any JSON blob and pull out objects that look like products.
    Works for FirstCry's __NEXT_DATA__, Blinkit's API responses, etc.
    """
    out, seen = [], set()
    for obj in _walk(data):
        kl = {k.lower(): k for k in obj}

        # ── Identify product object ────────────────────────────────────────────
        id_key    = next((kl[k] for k in ("productid","pid","itemid","product_id","id") if k in kl), None)
        name_key  = next((kl[k] for k in ("productname","itemname","product_name","name","title","display_name") if k in kl), None)
        price_key = next((kl[k] for k in ("saleprice","sellingprice","sale_price","sp","price","offerprice","selling_price") if k in kl), None)
        mrp_key   = next((kl[k] for k in ("mrp","listprice","list_price","original_price") if k in kl), None)
        avail_key = next((kl[k] for k in ("isavailable","instock","is_available","in_stock","available","isstock") if k in kl), None)
        url_key   = next((kl[k] for k in ("producturl","product_url","url","pdpurl","slug") if k in kl), None)

        if not (id_key and name_key and price_key): continue

        try:
            raw_id = str(obj[id_key])
            name   = str(obj[name_key]).strip()
            price  = obj[price_key]
            mrp    = obj.get(mrp_key, price) if mrp_key else price
            avail  = bool(obj[avail_key]) if avail_key else False
            url    = str(obj[url_key]) if url_key else ""

            if not raw_id or not name or len(name) < 4: continue
            if raw_id in seen: continue

            # For blinkit/hamleys — filter to Hot Wheels only
            brand = str(obj.get("brand") or obj.get("brand_name") or "").lower()
            if source != "firstcry":
                nl = name.lower()
                if not ("hot wheel" in nl or "hotwheels" in nl or brand in ("hot wheels","hotwheels","mattel")):
                    continue

            # Normalise URL
            if url.startswith("/"):
                base = {"firstcry":"https://www.firstcry.com",
                        "blinkit": "https://blinkit.com",
                        "hamleys": "https://www.hamleys.in"}.get(source,"")
                url = base + url
            if not url:
                url = fallback_url

            prefix = {"firstcry":"fc","blinkit":"bl","hamleys":"hm"}.get(source,"x")

            seen.add(raw_id)
            out.append({
                "id":       f"{prefix}_{raw_id}",
                "name":     name,
                "url":      url,
                "price":    f"₹{int(float(price))}" if price else "",
                "mrp":      f"₹{int(float(mrp))}"   if mrp   else "",
                "stock":    "in_stock" if avail else "out_of_stock",
                "leftCount": None,
                "source":   source,
            })
        except Exception:
            continue

    return out


# ── Page helpers ───────────────────────────────────────────────────────────────
_EXTRACT_JS = r"""
() => {
    // 1. window.__NEXT_DATA__ (Next.js)
    if (window.__NEXT_DATA__) return {src:"__NEXT_DATA__", data: window.__NEXT_DATA__};

    // 2. <script id="__NEXT_DATA__"> tag
    const nd = document.getElementById('__NEXT_DATA__');
    if (nd && nd.textContent) {
        try { return {src:"__NEXT_DATA__tag", data: JSON.parse(nd.textContent)}; }
        catch(e){}
    }

    // 3. window.__REDUX_STATE__ (some React apps)
    if (window.__REDUX_STATE__) return {src:"__REDUX_STATE__", data: window.__REDUX_STATE__};

    // 4. Scan all <script> tags for a JSON blob containing product data
    const scripts = Array.from(document.scripts);
    for (const s of scripts) {
        const t = s.textContent || '';
        if ((t.includes('ProductId') || t.includes('productId') || t.includes('"price"'))
            && t.includes('"name"') && t.length > 500) {
            // Extract the first {...} JSON object
            const m = t.match(/window\.__[A-Z_]+\s*=\s*(\{[\s\S]+?\});\s*(?:window|<\/script>|$)/);
            if (m) try { return {src:"window_var", data: JSON.parse(m[1])}; } catch(e){}

            // Try finding a JSON array that looks like products
            const am = t.match(/\[\s*\{[^[]{200,}\}\s*\]/);
            if (am) try { return {src:"array", data: JSON.parse(am[0])}; } catch(e){}
        }
    }

    return null;
}
"""

_DOM_PRODUCTS_JS = r"""
() => {
    const results = [];
    const seen    = new Set();

    function isProductUrl(h) {
        if (!h || h.includes('store-locator') || h.includes('javascript')) return false;
        if (h.includes('firstcry.com')) {
            return h.includes('/product-detail') || /\/\d{5,}\//.test(h) || /\/\d{5,}$/.test(h);
        }
        if (h.includes('blinkit.com') || h.includes('hamleys.in')) return true;
        return false;
    }

    // ── Find product cards ────────────────────────────────────────────────────
    const CARD_SELECTORS = [
        // FirstCry
        "li[class*='product']","div[class*='product-box']","div[class*='prd-box']",
        "div[class*='ProductBox']","div[class*='item-box']","div[class*='prod_listing']",
        "[data-product-id]","[data-pid]",
        // Blinkit
        "[class*='UpdatedPlpProduct']","[class*='plp-product']","[class*='ProductCard']",
        "[data-testid*='product']",
        // Hamleys (Magento 2)
        ".product-item",".product-item-info","article.product",
        ".product-item-details",
    ];

    let cards = [];
    for (const sel of CARD_SELECTORS) {
        const found = Array.from(document.querySelectorAll(sel));
        if (found.length >= 2) { cards = found; break; }
    }

    // Anchor fallback — any link that looks like a product page
    if (cards.length === 0) {
        Array.from(document.querySelectorAll('a[href]'))
            .filter(a => isProductUrl(a.href))
            .forEach(a => {
                let el = a;
                for (let i = 0; i < 12; i++) {
                    if (!el.parentElement) break;
                    el = el.parentElement;
                    const t = (el.innerText||'');
                    if (t.includes('₹') || t.includes('Rs.') || t.toUpperCase().includes('ADD TO CART')) {
                        cards.push(el); break;
                    }
                }
            });
    }

    for (const card of cards) {
        // ── Link ─────────────────────────────────────────────────────────────
        const anchor = card.querySelector('a[href*="product-detail"]') ||
            card.querySelector('.product-item-name a') ||
            card.querySelector('a[href]');
        if (!anchor) continue;

        const href = anchor.href || '';
        if (!href || href.includes('javascript')) continue;

        // ── ID ────────────────────────────────────────────────────────────────
        const idM = href.match(/\/(\d{5,})/);
        const id  = idM ? idM[1] : href.split('?')[0].split('/').pop().replace(/\W+/g,'_').slice(0,40);
        if (!id || seen.has(id)) continue;

        // Skip obvious non-product pages
        if (/store.locator|\/brands?\//i.test(href)) continue;

        // ── Name ──────────────────────────────────────────────────────────────
        const nameEl =
            card.querySelector("[class*='prod-name']") ||
            card.querySelector("[class*='prd-name']") ||
            card.querySelector("[class*='product-name']") ||
            card.querySelector("[class*='ProductName']") ||
            card.querySelector('.product-item-name') ||
            card.querySelector('h2,h3,h4,h5');
        let name = (nameEl||anchor).innerText?.trim().split('\n')[0] || '';
        if (!name) name = anchor.title || anchor.getAttribute('aria-label') || '';
        if (!name || name.length < 4 || name.includes('₹')) continue;

        // Skip if not Hot Wheels (for Blinkit/Hamleys)
        const domain = (new URL(href)).hostname;
        if (!domain.includes('firstcry') && !/hot.?wheel/i.test(name+href)) continue;

        // ── Price ─────────────────────────────────────────────────────────────
        const ct   = card.innerText || '';
        const pArr = (ct.match(/₹\s*[\d,]+|Rs\.?\s*[\d,]+/g)||[])
            .map(s=>parseInt(s.replace(/[^\d]/g,''),10)).filter(n=>n>0).sort((a,b)=>a-b);
        const price = pArr[0] ? '₹'+pArr[0] : '';
        const mrp   = pArr[1] ? '₹'+pArr[1] : price;

        // ── Low stock ─────────────────────────────────────────────────────────
        const lm = ct.match(/(\d+)\s+[Ll]eft/);
        const leftCount = lm ? +lm[1] : null;

        // ── Stock ─────────────────────────────────────────────────────────────
        const up = ct.toUpperCase();
        let stock;
        if (/ADD TO CART|ADD TO BAG|BUY NOW|GET IT BY|IN STOCK/.test(up))
            stock = leftCount ? 'low_stock' : 'in_stock';
        else if (/NOTIFY ME|OUT OF STOCK|SOLD OUT|UNAVAILABLE/.test(up))
            stock = 'out_of_stock';
        else if (price)
            stock = 'in_stock'; // has a price → assume in stock
        else
            continue;

        seen.add(id);
        results.push({id, name, url:href, price, mrp, stock, leftCount});
    }

    return results;
}
"""


async def _load_page(page, url: str, wait: str = "networkidle"):
    """Load a URL with fallback strategies."""
    try:
        await page.goto(url, timeout=60_000, wait_until=wait)
    except Exception:
        try:
            await page.goto(url, timeout=60_000, wait_until="domcontentloaded")
            await asyncio.sleep(5)
        except Exception as e:
            print(f"  [!] Failed to load {url}: {e}")
            return False
    return True


async def _scroll(page, steps=8, delay=1.0):
    for _ in range(steps):
        await page.evaluate("window.scrollBy(0, window.innerHeight * 1.3)")
        await asyncio.sleep(delay)


# ── FirstCry ───────────────────────────────────────────────────────────────────
async def scrape_firstcry() -> list[dict]:
    out, seen_ids = [], set()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=BARGS)
        ctx = await browser.new_context(
            user_agent=UA, viewport={"width":1280,"height":900}, locale="en-IN",
            extra_http_headers={"Accept-Language":"en-IN,en;q=0.9"})
        await ctx.add_init_script(STEALTH)
        await ctx.add_cookies([
            {"name":"pn",      "value":PINCODE, "domain":".firstcry.com","path":"/"},
            {"name":"pincode", "value":PINCODE, "domain":".firstcry.com","path":"/"},
            {"name":"CityId",  "value":CITY,    "domain":".firstcry.com","path":"/"},
        ])
        page = await ctx.new_page()

        for url in FIRSTCRY_URLS:
            print(f"  [FC] Loading {url}")
            ok = await _load_page(page, url)
            if not ok: continue

            await _scroll(page, steps=10, delay=1.0)

            # ── Strategy 1: __NEXT_DATA__ ──────────────────────────────────────
            result = await page.evaluate(_EXTRACT_JS)
            if result:
                prods = extract_products_from_json(result["data"], "firstcry", url)
                print(f"  [FC] {result['src']} → {len(prods)} products")
                if DEBUG and prods:
                    print(f"  [FC] Sample: {prods[0]}")
                for p in prods:
                    if p["id"] not in seen_ids:
                        out.append(p); seen_ids.add(p["id"])
            else:
                print("  [FC] No JSON data blob found")

            # ── Strategy 2: DOM scrape ─────────────────────────────────────────
            dom = await page.evaluate(_DOM_PRODUCTS_JS)
            for d in dom:
                uid = f"fc_{d['id']}"
                if uid not in seen_ids:
                    d["id"] = uid; d["source"] = "firstcry"
                    out.append(d); seen_ids.add(uid)
            print(f"  [FC] DOM fallback added {sum(1 for d in dom if 'fc_'+d['id'] in seen_ids)} more")

            # ── Debug screenshot ───────────────────────────────────────────────
            if DEBUG:
                shot = f"fc_{url.rstrip('/').split('/')[-1]}.png"
                await page.screenshot(path=shot, full_page=True)
                tg_file(shot, f"FC debug: {url} — {len(out)} total products so far")

            # ── If still 0, send diagnostic ────────────────────────────────────
            if not out:
                title = await page.title()
                body_snippet = (await page.evaluate("document.body.innerText"))[:400]
                print(f"  [FC] Page title: {title!r}")
                print(f"  [FC] Body snippet: {body_snippet[:200]!r}")
                if DEBUG:
                    tg(f"⚠️ FC 0 products\nTitle: {title}\nBody: {body_snippet[:300]}")

        await browser.close()
    return out


# ── Blinkit ────────────────────────────────────────────────────────────────────
async def scrape_blinkit() -> list[dict]:
    out, seen_ids = [], set()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=BARGS)
        ctx = await browser.new_context(
            user_agent=UA, viewport={"width":1280,"height":900}, locale="en-IN",
            geolocation={"latitude":LAT,"longitude":LON},
            permissions=["geolocation"])
        await ctx.add_init_script(STEALTH)
        page = await ctx.new_page()

        for term in BLINKIT_TERMS:
            url = f"https://blinkit.com/s/?q={quote(term)}"
            print(f"  [BL] Loading {url}")
            ok = await _load_page(page, url, wait="domcontentloaded")
            if not ok: continue
            await asyncio.sleep(3)

            # Dismiss any location prompt
            for btn_txt in ["Allow","Use my location","Detect","Skip","Continue"]:
                try:
                    b = page.get_by_text(btn_txt, exact=True).first
                    if await b.is_visible(timeout=800):
                        await b.click(); await asyncio.sleep(1)
                except: pass

            await _scroll(page, steps=5, delay=1.0)

            # Strategy 1: __NEXT_DATA__
            result = await page.evaluate(_EXTRACT_JS)
            if result:
                prods = extract_products_from_json(result["data"], "blinkit", url)
                print(f"  [BL] {result['src']} → {len(prods)} products")
                for p in prods:
                    if p["id"] not in seen_ids:
                        out.append(p); seen_ids.add(p["id"])
            else:
                print("  [BL] No JSON data blob found")

            # Strategy 2: DOM
            dom = await page.evaluate(_DOM_PRODUCTS_JS)
            for d in dom:
                uid = f"bl_{d['id']}"
                if uid not in seen_ids:
                    d["id"]=uid; d["source"]="blinkit"; d["url"]=url
                    out.append(d); seen_ids.add(uid)

            if DEBUG:
                shot = f"bl_{term.replace(' ','_')}.png"
                await page.screenshot(path=shot, full_page=True)
                tg_file(shot, f"BL debug: '{term}' — {len(out)} products")

            if not out:
                title = await page.title()
                body  = (await page.evaluate("document.body.innerText"))[:300]
                print(f"  [BL] title={title!r} body={body[:150]!r}")

        await browser.close()
    return out


# ── Hamleys India ──────────────────────────────────────────────────────────────
async def scrape_hamleys() -> list[dict]:
    out, seen_ids = [], set()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=BARGS)
        ctx = await browser.new_context(
            user_agent=UA, viewport={"width":1280,"height":900}, locale="en-IN")
        await ctx.add_init_script(STEALTH)
        page = await ctx.new_page()

        for url in HAMLEYS_URLS:
            print(f"  [HM] Loading {url}")
            ok = await _load_page(page, url)
            if not ok: continue
            await _scroll(page, steps=6, delay=0.8)

            # Strategy 1: __NEXT_DATA__ or JSON (if it's Next.js)
            result = await page.evaluate(_EXTRACT_JS)
            if result:
                prods = extract_products_from_json(result["data"], "hamleys", url)
                print(f"  [HM] JSON {result['src']} → {len(prods)} products")
                for p in prods:
                    if p["id"] not in seen_ids:
                        out.append(p); seen_ids.add(p["id"])

            # Strategy 2: Magento 2 DOM selectors
            hm_dom = await page.evaluate(r"""
            () => {
                const results = [];
                const seen = new Set();

                // Magento 2 product cards
                const cards = Array.from(document.querySelectorAll(
                    '.product-item, .product-item-info, li.item.product, ' +
                    'article.product, .product-grid-item'
                ));

                for (const card of cards) {
                    const link = card.querySelector(
                        '.product-item-name a, a.product-item-link, ' +
                        'a[href*=".html"], a[href]'
                    );
                    if (!link) continue;

                    const href = link.href || '';
                    if (!href || !/hamleys\.in/.test(href)) continue;

                    // Hot Wheels check
                    const ct = (card.innerText||'').toLowerCase();
                    if (!ct.includes('hot wheel') && !ct.includes('hotwheels')) continue;

                    // ID from URL
                    const slug = href.split('?')[0].split('/').pop().replace('.html','');
                    const id   = 'hm_' + slug.slice(0,50);
                    if (seen.has(id)) continue;

                    // Name
                    const nameEl = card.querySelector(
                        '.product-item-name, .product-name, h2, h3, [class*="name"]'
                    );
                    let name = (nameEl||link).innerText?.trim().split('\n')[0] || '';
                    if (!name || name.length < 4) continue;

                    // Price — Magento uses .price class
                    const priceEl = card.querySelector('.price,.price-wrapper,.final-price');
                    const priceT  = (priceEl||{}).innerText?.trim() || '';
                    const priceM  = (priceT + ct).match(/₹\s*[\d,]+|Rs\.?\s*[\d,]+/);
                    const price   = priceM ? '₹' + priceM[0].replace(/[^\d]/g,'') : '';

                    // Stock — Magento uses .stock.available / .stock.unavailable
                    const isAvail  = !!card.querySelector('.stock.available,.tocart');
                    const isOos    = !!card.querySelector('.stock.unavailable') ||
                                     ct.includes('out of stock') || ct.includes('notify');
                    let stock = isOos ? 'out_of_stock' : (isAvail || price) ? 'in_stock' : 'unknown';
                    if (stock === 'unknown') continue;

                    seen.add(id);
                    results.push({id, name, url:href, price, mrp:price, stock, leftCount:null, source:'hamleys'});
                }
                return results;
            }
            """)
            for d in hm_dom:
                if d["id"] not in seen_ids:
                    out.append(d); seen_ids.add(d["id"])

            print(f"  [HM] DOM → {len(hm_dom)} products")

            if DEBUG:
                shot = f"hm_{url.rstrip('/').split('/')[-1][:20]}.png"
                await page.screenshot(path=shot, full_page=True)
                tg_file(shot, f"HM debug: {url} — {len(out)} products")

            if not out:
                title = await page.title()
                body  = (await page.evaluate("document.body.innerText"))[:300]
                print(f"  [HM] title={title!r} body={body[:150]!r}")

            if out: break  # Got products from first URL, don't try others

        await browser.close()
    return out


# ── Diff ───────────────────────────────────────────────────────────────────────
def compute_changes(current: dict, seen: dict) -> dict:
    new_listings, restocks, low_stocks, price_drops, went_oos = [], [], [], [], []
    for pid, d in current.items():
        stock      = d["stock"]
        prev       = seen.get(pid)
        prev_stock = prev.get("stock") if prev else None
        prev_price = prev.get("price") if prev else None

        if stock in ("in_stock","low_stock"):
            if prev is None:
                (low_stocks if stock=="low_stock" else new_listings).append(d)
            elif prev_stock == "out_of_stock":
                (low_stocks if stock=="low_stock" else restocks).append(d)
            elif prev_stock == "in_stock" and stock == "low_stock":
                low_stocks.append(d)
            # Price drop
            if prev_price and d.get("price") and prev_price != d["price"]:
                try:
                    if int(re.sub(r"\D","",d["price"])) < int(re.sub(r"\D","",prev_price)):
                        price_drops.append({**d,"prev_price":prev_price})
                except: pass
        elif stock == "out_of_stock" and prev_stock in ("in_stock","low_stock"):
            went_oos.append(d)

    return dict(new_listings=new_listings, restocks=restocks,
                low_stocks=low_stocks, price_drops=price_drops, went_oos=went_oos)


SRC_LABEL = {"firstcry":"🛒 FC","blinkit":"⚡ BL","hamleys":"🏪 HM"}

def build_alert(ch: dict) -> str | None:
    lines = ["🚨 <b>Hot Wheels Alert!</b> 🏎️\n"]
    def tag(d): return SRC_LABEL.get(d.get("source",""),"")

    if ch["new_listings"]:
        lines.append("🆕 <b>NEW listing — in stock:</b>")
        for d in ch["new_listings"]:
            lines.append(f"  [{tag(d)}] <b>{d['name']}</b>  {d['price']}\n  {d['url']}")

    if ch["restocks"]:
        lines.append("\n🔥 <b>Back in stock:</b>")
        for d in ch["restocks"]:
            lines.append(f"  [{tag(d)}] <b>{d['name']}</b>  {d['price']}\n  {d['url']}")

    if ch["low_stocks"]:
        lines.append("\n⚠️ <b>Almost gone — grab now:</b>")
        for d in ch["low_stocks"]:
            badge = f" ({d['leftCount']} left!)" if d.get("leftCount") else " (low stock)"
            lines.append(f"  [{tag(d)}] <b>{d['name']}</b>{badge}  {d['price']}\n  {d['url']}")

    if ch["price_drops"]:
        lines.append("\n💸 <b>Price drop:</b>")
        for d in ch["price_drops"]:
            lines.append(f"  [{tag(d)}] <b>{d['name']}</b>  <s>{d['prev_price']}</s> → <b>{d['price']}</b>\n  {d['url']}")

    return "\n".join(lines) if len(lines) > 1 else None


def build_status(products: list, ch: dict) -> str:
    by_src = {}
    for p in products: by_src.setdefault(p.get("source","?"),[]).append(p)
    lines = [f"📊 <b>Hot Wheels Status</b> — {CITY} {PINCODE}\n"]
    for src, label in [("firstcry","🛒 FirstCry"),("blinkit","⚡ Blinkit"),("hamleys","🏪 Hamleys")]:
        sp = by_src.get(src,[])
        ins = sum(1 for p in sp if p["stock"] in ("in_stock","low_stock"))
        lines.append(f"{label}: <b>{ins}</b> in stock · {len(sp)-ins} OOS · {len(sp)} total")
    if ch.get("went_oos"):
        lines.append("\n🔴 Just went OOS: " + ", ".join(d["name"][:35] for d in ch["went_oos"]))
    return "\n".join(lines)


# ── Main ───────────────────────────────────────────────────────────────────────
async def main_async():
    ensure_browser()

    seen = load_seen()
    all_products: list[dict] = []
    errors: list[str] = []

    scrapers = [
        ("FirstCry",   scrape_firstcry),
        ("Blinkit",    scrape_blinkit),
        ("Hamleys",    scrape_hamleys),
    ]

    for name, fn in scrapers:
        print(f"\n[*] Scraping {name} …")
        try:
            prods = await fn()
            print(f"[*] {name} → {len(prods)} products")
            all_products.extend(prods)
        except Exception as exc:
            msg = f"{name}: {exc}"
            print(f"[!] {msg}")
            errors.append(msg)
            if DEBUG:
                tg(f"⚠️ Scrape error — {msg[:300]}")

    if not all_products:
        err_txt = "\n".join(errors) if errors else "No detailed errors captured."
        tg(
            "⚠️ <b>Hot Wheels Tracker — 0 products found</b>\n\n"
            "All 3 sources returned nothing.\n"
            "Please set DEBUG=true in the workflow and re-run — "
            "screenshots will be sent here.\n\n"
            f"<code>{err_txt[:400]}</code>"
        )
        return

    current = {p["id"]: p for p in all_products}
    changes = compute_changes(current, seen)

    alert = build_alert(changes)
    if alert:
        tg(alert)
        print("\n" + alert)
    elif not SILENT:
        status = build_status(all_products, changes)
        tg(status)
        print("\n" + status)
    else:
        # Log only — don't spam Telegram
        by_src = {}
        for p in all_products: by_src.setdefault(p.get("source","?"),[]).append(p)
        parts = [f"{s}: {sum(1 for x in v if x['stock'] in ('in_stock','low_stock'))}/{len(v)}"
                 for s,v in by_src.items()]
        print(f"[=] No changes. {' | '.join(parts)}")

    save_seen({
        pid: {"stock":d["stock"],"name":d["name"],"price":d.get("price",""),"source":d.get("source","")}
        for pid,d in current.items()
    })


def main():
    asyncio.run(main_async())

if __name__ == "__main__":
    main()
