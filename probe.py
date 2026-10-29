#!/usr/bin/env python3
"""Probe #45: Karz & Dolls — do links open for IN-STOCK cars whose own slug has
unusual characters (non-breaking spaces, '?', '#', '%', '&', '+', '/', '*',
accents)? Tries the tracker's link and a few other ways for each, across every
shelf the tracker reads. Read-only."""
import json, re, html, collections
from urllib.parse import quote
from curl_cffi import requests as http
IMP = {"impersonate": "chrome124"}
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
     "Accept-Language": "en-IN,en;q=0.9", "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"}
KD = "https://www.karzanddolls.com"
NEXT = re.compile(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.S)
SHELVES = ["/hot-wheels/mainlines", "/hot-wheels/pop-culture", "/hot-wheels/card-art-premiums", "/hot-wheels/car-culture",
           "/hot-wheels/fast-and-furious", "/hot-wheels/team-transport", "/mini-gt/mini-gt", "/mini-gt/mini-gt-blister-pack",
           "/mini-gt/kaido-house", "/pre-orders/pre-order-minigt", "/specials/chase-car", "/specials/special-stocks-64-43-scale", "/"]


def get(url):
    try:
        r = http.get(url, headers=H, timeout=25, allow_redirects=True, **IMP)
        return r.status_code, r.text
    except Exception as e:
        return None, ""


def products(page):
    m = NEXT.search(page or "")
    if not m:
        return []
    props = (json.loads(m.group(1)).get("props") or {}).get("pageProps") or {}
    found, stack = [], [props]
    while stack:
        n = stack.pop()
        if isinstance(n, list):
            stack.extend(n)
        elif isinstance(n, dict):
            if "pid" in n and "pro_name" in n:
                found.append(n)
            else:
                stack.extend(n.values())
    return found


allp, own_links = {}, {}
for s in SHELVES:
    code, page = get(KD + s)
    for p in products(page):
        allp[str(p["pid"])] = p
    for mm in re.finditer(r'href="(/details/[^"]*?pid=([^"&]+))"', page or ""):
        own_links[mm.group(2)] = html.unescape(mm.group(1))
print(f"{len(allp)} products on {len(SHELVES)} shelves")
odd = [p for p in allp.values() if re.search(r"[^a-z0-9\-]", str(p.get("slug") or ""))]
c = collections.Counter(ch for p in odd for ch in set(re.sub(r"[a-z0-9\-]", "", str(p.get("slug")))))
print(f"{len(odd)} have a slug with other characters: {dict(c)}")
inst = [p for p in odd if str(p.get("in_stock")) in ("1", "True", "true")]
print(f"…{len(inst)} of them in stock now\n")
seen_chars = set()
for p in inst:
    chars = frozenset(re.sub(r"[a-z0-9\-]", "", str(p.get("slug"))))
    if chars in seen_chars and len(seen_chars) > 6:
        continue
    seen_chars.add(chars)
    slug, pid, nm = str(p["slug"]), str(p["pid"]), str(p["pro_name"])
    probe_word = re.sub(r"[^A-Z0-9 ]", " ", nm.upper()).split()[2:4] or nm.upper().split()[:1]
    def shows(page):
        return all(w in (page or "").upper() for w in probe_word) and "Page not found" not in (page or "")
    tries = [("tracker's link", f"{KD}/details/{quote(slug, safe='-_.~')}?pid={quote(pid, safe='')}"),
             ("raw slug", f"{KD}/details/{slug}?pid={pid}"),
             ("KND's own href", KD + own_links[pid] if pid in own_links else None),
             ("slug trimmed+NBSP→space→-", f"{KD}/details/{quote(re.sub(r'-+', '-', re.sub(r'[^a-z0-9]+', '-', slug.lower())).strip('-'))}?pid={pid}")]
    print(f"--- {nm[:60]!r} slug={slug!r} chars={sorted(chars)}")
    for label, url in tries:
        if not url:
            print(f"    {label:26} (none on the shelf page)")
            continue
        code, page = get(url)
        print(f"    {label:26} HTTP {code}  opens it: {shows(page)}   {url[len(KD):][:100]!r}")
    if len(seen_chars) > 8:
        break
