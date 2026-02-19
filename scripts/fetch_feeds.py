#!/usr/bin/env python3
"""
Fetches HPP-relevant RSS feeds and inlines article data into index.html.
Run by GitHub Actions on a schedule; no runtime network calls needed in browser.
Requires: pip install feedparser
"""
import json
import re
import sys
import traceback
from datetime import datetime, timezone

try:
    import feedparser  # pip install feedparser
except ImportError as _e:
    print(f"FATAL: feedparser not installed: {_e}", file=sys.stderr)
    sys.exit(1)

FEEDS = [
    {"label": "Food Safety News",         "url": "https://www.foodsafetynews.com/feed/"},
    {"label": "Food Technology Magazine",  "url": "https://www.ift.org/news-and-publications/food-technology-magazine/rss"},
    {"label": "Food Processing",           "url": "https://www.foodprocessing.com/rss/articles.xml"},
    {"label": "FoodNavigator USA",         "url": "https://www.foodnavigator-usa.com/rss/feed"},
    {"label": "Food Dive",                 "url": "https://www.fooddive.com/feeds/news/"},
]

MAX_PER_FEED = 20
MAX_TOTAL    = 20


def strip_html(text):
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)
    for old, new in [("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"),
                     ("&quot;", '"'), ("&#39;", "'"), ("&nbsp;", " ")]:
        text = text.replace(old, new)
    return " ".join(text.split())


def parse_date(pub):
    if not pub:
        return datetime.min.replace(tzinfo=timezone.utc)
    for fmt in ("%a, %d %b %Y %H:%M:%S %z",
                "%a, %d %b %Y %H:%M:%S %Z",
                "%Y-%m-%dT%H:%M:%S%z",
                "%Y-%m-%dT%H:%M:%SZ"):
        try:
            return datetime.strptime(str(pub).strip()[:31], fmt)
        except Exception:
            pass
    return datetime.min.replace(tzinfo=timezone.utc)


def fetch_feed(feed):
    print(f"  Fetching {feed['label']} ...")
    d = feedparser.parse(feed["url"])
    status = getattr(d, "status", "?")
    bozo   = getattr(d, "bozo", False)
    bozo_e = getattr(d, "bozo_exception", None)
    print(f"    status={status} bozo={bozo} entries={len(d.entries)}"
          + (f" bozo_exc={bozo_e}" if bozo_e else ""))
    if not d.entries:
        raise ValueError(f"no entries returned (HTTP {status})")
    items = []
    for entry in d.entries[:MAX_PER_FEED]:
        title = strip_html(entry.get("title", ""))
        link  = entry.get("link", "#")
        desc  = strip_html(entry.get("summary", "") or entry.get("description", ""))
        pub   = (entry.get("published") or entry.get("updated") or
                 entry.get("pubDate") or "")
        if title and link:
            items.append({
                "source":      feed["label"],
                "title":       title,
                "link":        link,
                "description": desc[:400],
                "pubDate":     pub,
            })
    return items


# ── Fetch all feeds ───────────────────────────────────────────────────────────
all_articles, errors = [], []

for f in FEEDS:
    try:
        arts = fetch_feed(f)
        all_articles.extend(arts)
        print(f"  OK  {f['label']}: {len(arts)} articles")
    except Exception as exc:
        errors.append(f"{f['label']}: {exc}")
        print(f"  ERR {f['label']}: {exc}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)

all_articles.sort(key=lambda a: parse_date(a.get("pubDate", "")), reverse=True)
all_articles = all_articles[:MAX_TOTAL]

print(f"\n  Total: {len(all_articles)} articles, {len(errors)} feed errors")

payload = {
    "updated":  datetime.now(timezone.utc).isoformat(),
    "articles": all_articles,
}

# ── Write feeds.json ──────────────────────────────────────────────────────────
try:
    with open("feeds.json", "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    print("  Wrote feeds.json")
except Exception as exc:
    print(f"  WARNING: could not write feeds.json: {exc}", file=sys.stderr)

# ── Inline into index.html ────────────────────────────────────────────────────
MARKER_START = "/* __FEEDS_DATA_START__ */"
MARKER_END   = "/* __FEEDS_DATA_END__ */"

try:
    with open("index.html", encoding="utf-8") as fh:
        html = fh.read()

    if MARKER_START not in html or MARKER_END not in html:
        print("ERROR: markers not found in index.html", file=sys.stderr)
        print(f"  MARKER_START present: {MARKER_START in html}", file=sys.stderr)
        print(f"  MARKER_END   present: {MARKER_END in html}", file=sys.stderr)
        sys.exit(1)

    inline_js = (
        f"{MARKER_START}\n"
        f"  var __FEEDS__ = {json.dumps(payload, ensure_ascii=False)};\n"
        f"  {MARKER_END}"
    )

    pattern = re.compile(
        re.escape(MARKER_START) + r".*?" + re.escape(MARKER_END),
        re.DOTALL,
    )
    # Use lambda to prevent re.sub from interpreting backslashes in replacement
    html = pattern.sub(lambda _: inline_js, html)

    with open("index.html", "w", encoding="utf-8") as fh:
        fh.write(html)
    print("  Updated index.html inline data")

except SystemExit:
    raise
except Exception as exc:
    print(f"  ERROR updating index.html: {exc}", file=sys.stderr)
    traceback.print_exc(file=sys.stderr)
    sys.exit(1)
