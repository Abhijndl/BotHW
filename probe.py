#!/usr/bin/env python3
"""Probe #74: read The Scent Stories' newest miniatures the way the watcher will."""
import gzip, html, re, time, urllib.error, urllib.request

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36")


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html", "Accept-Encoding": "gzip"})
    with urllib.request.urlopen(req, timeout=25) as r:
        code, data, enc = r.status, r.read(), r.headers.get("Content-Encoding", "")
    if "gzip" in enc.lower():
        data = gzip.decompress(data)
    return code, data.decode("utf-8", "replace")


def money(s):
    try:
        return float(s.replace(",", ""))
    except (AttributeError, ValueError):
        return None


T = "https://thescentstories.com"
code, page = get(f"{T}/shop/category/miniatures-58?order=create_date+desc&ppg=40")
cards = re.split(r'<form[^>]+class="[^"]*oe_product_cart', page)[1:]
print("cards", len(cards))
c = cards[0]
i = c.find("product_price")
print("--- price part of card 1 ---")
print(re.sub(r"\s+", " ", c[i - 50: i + 1600]))
for c in cards[:40]:
    tid = re.search(r'name="product_template_id"[^>]*value="(\d+)"', c)
    href = re.search(r'itemprop="url"[^>]*href="([^"?]+)', c)
    name = re.search(r'itemprop="name"[^>]*content="([^"]*)"', c)
    price = re.search(r'oe_currency_value">([\d,\.]+)<', c)
    was = re.search(r'<del[^>]*>(?:(?!</del>).)*?oe_currency_value">([\d,\.]+)<', c, re.S)
    stock = re.findall(r'(?i)out of stock|sold out|unavailable', c)
    print(tid and tid.group(1), "|", html.unescape(name.group(1)) if name else None, "|", money(price.group(1)) if price else None,
          "| was", money(was.group(1)) if was else None, "|", href and href.group(1), "|", stock)
