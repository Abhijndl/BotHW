#!/usr/bin/env python3
"""Probe #69: where Sovereign Scents' own code mentions 'Partials' (a section? a filter?)."""
import gzip, json, re, urllib.error, urllib.request

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36")


def get(url, accept="*/*"):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": accept, "Accept-Encoding": "gzip"})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            code, data, hdr = r.status, r.read(), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, ""
    if "gzip" in (hdr.get("Content-Encoding") or "").lower():
        data = gzip.decompress(data)
    return code, data.decode("utf-8", "replace")


S = "https://www.sovereignscents.in"
seen = set()
for page in ("/shop", "/", "/about", "/authenticity", "/shipping", "/returns", "/terms"):
    code, html = get(S + page, "text/html")
    text = re.sub(r"<[^>]+>", " ", html)
    for m in re.finditer(r"(?i)partial", text):
        ctx = re.sub(r"\s+", " ", text[max(0, m.start() - 150): m.end() + 150])
        if ctx not in seen:
            seen.add(ctx)
            print(f"[{page} page text] …{ctx}…")
    for c in sorted(set(re.findall(r'(/_next/static/chunks/[^"\']+\.js)', html))):
        if c in seen:
            continue
        seen.add(c)
        c2, js = get(S + c)
        for m in re.finditer(r"partials|Partials|PARTIAL", js):
            ctx = js[max(0, m.start() - 220): m.end() + 220].replace("\n", " ")
            print(f"[{c.rsplit('/', 1)[-1]}] …{ctx}…\n")
for q in ("?type=Partials", "?type=Partial", "?category=Partial", "?partial=true", "?isPartial=true", "?collection=partials"):
    code, b = get(f"{S}/api/products{q}&limit=5" if "?" in q else f"{S}/api/products{q}", "application/json")
    try:
        d = json.loads(b)
        print(q, "->", code, len(d.get("products") or []), d.get("pagination", {}).get("totalCount"))
    except Exception:
        print(q, "->", code, b[:120])
