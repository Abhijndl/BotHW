#!/usr/bin/env python3
"""Probe #19: raw Hot Wheels case checklists for the case/TH/STH feature.

164custom.com: year pages + every case page (/hot-wheels/case-<letter>/<year>.html)
for 2024-2027, and whatever TH / STH checklist pages they link to.
orangetrackdiecast.com: the WordPress REST API for the "case contents checklist"
posts (TH / STH / new-model markers per case).
Everything is saved gzipped + base64 in probe_report.json. Polite: one request
at a time, a short pause between them. Nothing touches any store.
"""
import base64, gzip, json, re, time
from curl_cffi import requests as http

T0 = time.time()
IMP = {"impersonate": "chrome124"}
H = {"User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
     "Accept-Language": "en-US,en;q=0.9"}
FILES, LOG = {}, []


def get(url, key=None, accept=None):
    time.sleep(0.4)
    try:
        r = http.get(url, headers={**H, **({"Accept": accept} if accept else {})}, timeout=25, **IMP)
    except Exception as e:
        print(f"  ERR {url}: {e}")
        return None
    print(f"  {r.status_code} {len(r.text):7d} b  {url}")
    if r.status_code == 200 and key:
        FILES[key] = base64.b64encode(gzip.compress(r.text.encode("utf-8", "replace"))).decode()
    return r if r.status_code == 200 else None


print("== 164custom: year pages ==")
links = set()
for y in (2024, 2025, 2026, 2027):
    r = get(f"https://164custom.com/hot-wheels/year/{y}.html", f"164/year/{y}.html")
    if r:
        for h in re.findall(r'href="([^"]+)"', r.text):
            if re.search(r"treasure|sth|super|chase|case-", h, re.I):
                links.add(h)
print("links of interest on year pages:", len(links))
for h in sorted(links)[:80]:
    print("   ", h)

print("== 164custom: case pages ==")
letters = "ABCDEFGHJKLMNPQRSTUVWXYZ"
for y in (2024, 2025, 2026, 2027):
    misses = 0
    for L in letters:
        r = get(f"https://164custom.com/hot-wheels/case-{L.lower()}/{y}.html", f"164/case/{y}-{L}.html")
        if not r:
            misses += 1
            if misses >= 3 and L > "Q":
                break
        else:
            for h in re.findall(r'href="([^"]+)"', r.text):
                if re.search(r"treasure|sth|super|chase", h, re.I):
                    links.add(h)

print("== 164custom: TH / STH / chase pages ==")
done = set()
for h in sorted(links):
    if not re.search(r"treasure|sth|super|chase", h, re.I):
        continue
    url = h if h.startswith("http") else "https://164custom.com" + (h if h.startswith("/") else "/" + h)
    if url in done or "164custom.com" not in url:
        continue
    done.add(url)
    get(url, "164/special/" + re.sub(r"[^A-Za-z0-9._-]+", "_", url.split("164custom.com/")[-1]))
    if len(done) > 30:
        break

print("== orangetrackdiecast: WordPress API ==")
posts = []
for page in range(1, 6):
    r = get("https://orangetrackdiecast.com/wp-json/wp/v2/posts?search=case%20contents%20checklist"
            f"&per_page=100&page={page}&_fields=id,date,link,title,content", None, "application/json")
    if not r:
        break
    try:
        batch = r.json()
    except Exception:
        print("   not JSON:", r.text[:200])
        break
    if not isinstance(batch, list) or not batch:
        break
    posts += batch
    if len(batch) < 100:
        break
print("posts:", len(posts))
for p in posts:
    print("   ", p.get("date"), (p.get("title") or {}).get("rendered", "")[:90], p.get("link"))
FILES["otd/posts.json"] = base64.b64encode(gzip.compress(json.dumps(posts).encode())).decode()

json.dump(FILES, open("probe_report.json", "w"))
print(f"saved {len(FILES)} files; done in {time.time() - T0:.0f}s")
