#!/usr/bin/env python3
"""
Fetches HPP-relevant RSS feeds and inlines article data into index.html.
Run by GitHub Actions on a schedule; no runtime network calls needed in browser.
"""
import json
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

FEEDS = [
    {"label": "Food Safety News",        "url": "https://www.foodsafetynews.com/feed/"},
    {"label": "Food Technology Magazine", "url": "https://www.ift.org/news-and-publications/food-technology-magazine/rss"},
    {"label": "Food Processing",          "url": "https://www.foodprocessing.com/rss/articles.xml"},
    {"label": "FoodNavigator USA",        "url": "https://www.foodnavigator-usa.com/rss/feed"},
    {"label": "Food Dive",                "url": "https://www.fooddive.com/feeds/news/"},
]

ATOM_NS = "http://www.w3.org/2005/Atom"
MAX_PER_FEED = 20
MAX_TOTAL = 20


def strip_html(text):
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)
    text = (text
            .replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
            .replace("&quot;", '"').replace("&#39;", "'").replace("&nbsp;", " "))
    return " ".join(text.split())


def parse_date(pub_date):
    for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S %Z",
                "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            return datetime.strptime(pub_date.strip()[:31], fmt)
        except Exception:
            pass
    return datetime.min.replace(tzinfo=timezone.utc)


def fetch_feed(feed):
    req = urllib.request.Request(
        feed["url"],
        headers={"User-Agent": "Mozilla/5.0 (compatible; HPPFeedBot/1.0)",
                 "Accept": "application/rss+xml, application/xml, text/xml, */*"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        raw = resp.read()

    # Strip XML declaration / BOM to avoid ElementTree namespace issues
    text = raw.decode("utf-8", errors="replace").lstrip("\ufeff")
    root = ET.fromstring(text)

    items = []

    # ── RSS 2.0 ──────────────────────────────────────────────────────────────
    for item in root.findall(".//item"):
        title = strip_html(item.findtext("title") or "")
        link  = (item.findtext("link") or "").strip()
        desc  = strip_html(item.findtext("description") or "")
        pub   = item.findtext("pubDate") or ""
        if title and link:
            items.append({"source": feed["label"], "title": title,
                          "link": link, "description": desc[:400], "pubDate": pub})

    # ── Atom ─────────────────────────────────────────────────────────────────
    if not items:
        for entry in root.findall(f".//{{{ATOM_NS}}}entry"):
            title = strip_html(entry.findtext(f"{{{ATOM_NS}}}title") or "")
            link_el = entry.find(f"{{{ATOM_NS}}}link")
            link  = (link_el.get("href", "") if link_el is not None else "").strip()
            desc  = strip_html(entry.findtext(f"{{{ATOM_NS}}}summary") or
                               entry.findtext(f"{{{ATOM_NS}}}content") or "")
            pub   = entry.findtext(f"{{{ATOM_NS}}}published") or ""
            if title and link:
                items.append({"source": feed["label"], "title": title,
                              "link": link, "description": desc[:400], "pubDate": pub})

    return items[:MAX_PER_FEED]


# ── Fetch all feeds ───────────────────────────────────────────────────────────
all_articles = []
errors = []

for feed in FEEDS:
    try:
        articles = fetch_feed(feed)
        all_articles.extend(articles)
        print(f"  OK  {feed['label']}: {len(articles)} articles")
    except Exception as exc:
        errors.append(f"{feed['label']}: {exc}")
        print(f"  ERR {feed['label']}: {exc}", file=sys.stderr)

# Sort newest-first and cap total
all_articles.sort(key=lambda a: parse_date(a["pubDate"]), reverse=True)
all_articles = all_articles[:MAX_TOTAL]

payload = {
    "updated": datetime.now(timezone.utc).isoformat(),
    "articles": all_articles,
}

print(f"\n  Total: {len(all_articles)} articles, {len(errors)} feed errors")

# ── Write feeds.json ──────────────────────────────────────────────────────────
with open("feeds.json", "w", encoding="utf-8") as f:
    json.dump(payload, f, ensure_ascii=False, indent=2)
print("  Wrote feeds.json")

# ── Inline into index.html ───────────────────────────────────────────────────
MARKER_START = "/* __FEEDS_DATA_START__ */"
MARKER_END   = "/* __FEEDS_DATA_END__ */"

with open("index.html", "r", encoding="utf-8") as f:
    html = f.read()

inline_js = (
    f"{MARKER_START}\n"
    f"  var __FEEDS__ = {json.dumps(payload, ensure_ascii=False)};\n"
    f"  {MARKER_END}"
)

# Replace between markers (handles first run and updates)
pattern = re.compile(
    re.escape(MARKER_START) + r".*?" + re.escape(MARKER_END),
    re.DOTALL,
)
if pattern.search(html):
    html = pattern.sub(inline_js, html)
else:
    print("  WARNING: markers not found in index.html — skipping inline", file=sys.stderr)
    sys.exit(1)

with open("index.html", "w", encoding="utf-8") as f:
    f.write(html)
print("  Updated index.html inline data")
