#!/usr/bin/env python3
"""
Fetches HPP-relevant RSS feeds and inlines article data into index.html.
Run by GitHub Actions on a schedule — no external dependencies required.
"""
import json
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

# Google News RSS — specific search queries ensure only relevant HPP/food content.
_GN = "https://news.google.com/rss/search?hl=en-US&gl=US&ceid=US:en&q="
FEEDS = [
    {"label": "HPP Industry",
     "url": _GN + "%22high+pressure+processing%22+food"},
    {"label": "Food Safety News",
     "url": _GN + "food+safety+technology+2024+OR+2025"},
    {"label": "Food Technology",
     "url": _GN + "food+technology+innovation+processing"},
    {"label": "HPP Applications",
     "url": _GN + "%22high+pressure%22+%22food+processing%22"},
    {"label": "Food & Drink Industry",
     "url": _GN + "food+drink+industry+news"},
]

MAX_PER_FEED = 8
MAX_TOTAL    = 20

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; HPPFeedBot/1.0; +https://github.com/Ghosty61/HPP_Final_MVP)",
}


def strip_html(text):
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)
    for old, new in [("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"),
                     ("&quot;", '"'), ("&#39;", "'"), ("&nbsp;", " ")]:
        text = text.replace(old, new)
    return " ".join(text.split())


def parse_date(s):
    if not s:
        return datetime.min.replace(tzinfo=timezone.utc)
    s = s.strip()[:31]
    for fmt in ("%a, %d %b %Y %H:%M:%S %z",
                "%a, %d %b %Y %H:%M:%S %Z",
                "%Y-%m-%dT%H:%M:%S%z",
                "%Y-%m-%dT%H:%M:%SZ"):
        try:
            return datetime.strptime(s, fmt)
        except Exception:
            pass
    return datetime.min.replace(tzinfo=timezone.utc)


def fetch_rss(feed):
    """Fetch and parse an RSS/Atom feed; return list of article dicts."""
    req = urllib.request.Request(feed["url"], headers=HEADERS)
    with urllib.request.urlopen(req, timeout=15) as resp:
        raw = resp.read()

    root = ET.fromstring(raw)
    ns   = {"atom": "http://www.w3.org/2005/Atom"}
    items = []

    # ── RSS 2.0 ──────────────────────────────────────────────────────
    for item in root.findall(".//item")[:MAX_PER_FEED]:
        title = strip_html(item.findtext("title") or "")
        link  = (item.findtext("link") or "").strip()
        desc  = strip_html(item.findtext("description") or "")
        pub   = (item.findtext("pubDate") or
                 item.findtext("dc:date",
                               namespaces={"dc": "http://purl.org/dc/elements/1.1/"}) or "")
        if title and link:
            items.append({"source": feed["label"], "title": title,
                          "link": link, "description": desc[:400], "pubDate": pub})

    # ── Atom ─────────────────────────────────────────────────────────
    if not items:
        for entry in root.findall("atom:entry", ns)[:MAX_PER_FEED]:
            title = strip_html(entry.findtext("atom:title", namespaces=ns) or "")
            link_el = entry.find("atom:link[@rel='alternate']", ns) or entry.find("atom:link", ns)
            link  = (link_el.get("href", "") if link_el is not None else "").strip()
            desc  = strip_html(entry.findtext("atom:summary", namespaces=ns) or
                                entry.findtext("atom:content", namespaces=ns) or "")
            pub   = (entry.findtext("atom:published", namespaces=ns) or
                     entry.findtext("atom:updated", namespaces=ns) or "")
            if title and link:
                items.append({"source": feed["label"], "title": title,
                              "link": link, "description": desc[:400], "pubDate": pub})

    return items


# ── Fetch all feeds ───────────────────────────────────────────────────────────
all_articles = []

for f in FEEDS:
    try:
        arts = fetch_rss(f)
        all_articles.extend(arts)
        print(f"  OK  {f['label']}: {len(arts)} articles")
    except Exception as exc:
        print(f"  ERR {f['label']}: {exc}", file=sys.stderr)

all_articles.sort(key=lambda a: parse_date(a.get("pubDate", "")), reverse=True)
all_articles = all_articles[:MAX_TOTAL]

print(f"\n  Total: {len(all_articles)} articles from {len(FEEDS)} feeds")

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
        print("WARNING: feed markers not found in index.html — skipping inline update",
              file=sys.stderr)
        sys.exit(0)

    inline_js = (
        f"{MARKER_START}\n"
        f"  var __FEEDS__ = {json.dumps(payload, ensure_ascii=False)};\n"
        f"  {MARKER_END}"
    )

    pattern = re.compile(
        re.escape(MARKER_START) + r".*?" + re.escape(MARKER_END),
        re.DOTALL,
    )
    html = pattern.sub(lambda _: inline_js, html)

    with open("index.html", "w", encoding="utf-8") as fh:
        fh.write(html)
    print("  Updated index.html inline data")

except SystemExit:
    raise
except Exception as exc:
    print(f"  WARNING: could not update index.html: {exc}", file=sys.stderr)

# Always exit 0 — feed fetching is best-effort, never block CI
sys.exit(0)
