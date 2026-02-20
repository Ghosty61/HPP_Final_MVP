#!/usr/bin/env python3
"""
Fetches HPP-relevant RSS feeds and inlines article data into index.html.
Run by GitHub Actions on a schedule — no external dependencies required.

Two feed types:
  filtered=False  Google News queries (already targeted by search term)
  filtered=True   Direct publication RSS feeds (broad content — keyword-filtered)
"""
import json
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

# ── Relevance filter ──────────────────────────────────────────────────────────
# Articles from direct RSS feeds must contain at least one of these terms
# (case-insensitive, checked in title + description combined).
RELEVANCE_KEYWORDS = [
    # HPP technology
    "high pressure processing", " hpp ", "hpp-", "hpp:", "hpp—",
    "pascalization", "ultra-high pressure", "cold pressed", "hyperbaric",
    # Manufacturers
    "hiperbaric", "quintus", "avure", "nc hyperbaric", "stansted fluid",
    # Food safety — shown even without HPP mention (illustrates HPP's value)
    "listeria", "salmonella", "e. coli", "e.coli", "campylobacter",
    "food recall", "food safety alert", "food contamination",
    "contamination recall", "outbreak", "pathogen", "foodborne",
]


def is_relevant(title, description):
    """Return True if the article mentions any HPP or food-safety keyword."""
    haystack = (title + " " + description).lower()
    return any(kw in haystack for kw in RELEVANCE_KEYWORDS)


# ── Feed definitions ──────────────────────────────────────────────────────────
_GN_US = "https://news.google.com/rss/search?hl=en-US&gl=US&ceid=US:en&q="
_GN_UK = "https://news.google.com/rss/search?hl=en-GB&gl=GB&ceid=GB:en&q="

FEEDS = [
    # ━━ Direct industry & manufacturer RSS feeds (filtered=True) ━━━━━━━━━━━━
    # Hiperbaric blog — the world's leading HPP manufacturer publishes frequently
    {"label": "Hiperbaric Blog",
     "url": "https://www.hiperbaric.com/en/hpp-technology/hpp-blog/rss.xml",
     "filtered": False,   # every post is HPP-relevant
     "fetch_limit": 10},

    # Food Safety News — daily recall/outbreak reporting
    {"label": "Food Safety News",
     "url": "https://www.foodsafetynews.com/feed",
     "filtered": True,
     "fetch_limit": 20},

    # New Food Magazine — UK/EU-leaning, strong HPP and food tech coverage
    {"label": "New Food Magazine",
     "url": "https://www.newfoodmagazine.com/feed",
     "filtered": True,
     "fetch_limit": 20},

    # Food Dive — US industry news, frequent HPP & food safety stories
    {"label": "Food Dive",
     "url": "https://www.fooddive.com/feeds/news/",
     "filtered": True,
     "fetch_limit": 20},

    # FoodNavigator — Europe edition (William Reed)
    {"label": "FoodNavigator EU",
     "url": "https://www.foodnavigator.com/Info/FoodNavigator-RSS",
     "filtered": True,
     "fetch_limit": 20},

    # FoodNavigator USA
    {"label": "FoodNavigator USA",
     "url": "https://www.foodnavigator-usa.com/Info/FoodNavigator-USA-RSS",
     "filtered": True,
     "fetch_limit": 20},

    # Food Manufacture UK (William Reed)
    {"label": "Food Manufacture UK",
     "url": "https://www.foodmanufacture.co.uk/Info/FoodManufacture-RSS",
     "filtered": True,
     "fetch_limit": 20},

    # EFSA — EU food safety authority press releases
    {"label": "EFSA Food Safety",
     "url": "https://www.efsa.europa.eu/en/news/rss",
     "filtered": True,
     "fetch_limit": 20},

    # UK FSA — food alerts and recalls
    {"label": "UK Food Standards Agency",
     "url": "https://www.food.gov.uk/news-alerts/feed",
     "filtered": True,
     "fetch_limit": 20},

    # ━━ Google News targeted searches (filtered=False — query already focused) ━
    # Manufacturers
    {"label": "Hiperbaric News",
     "url": _GN_US + "Hiperbaric+%22high+pressure%22",
     "filtered": False, "fetch_limit": 5},
    {"label": "Quintus Technologies",
     "url": _GN_US + "%22Quintus+Technologies%22+%22high+pressure%22",
     "filtered": False, "fetch_limit": 5},
    {"label": "HPP Equipment Makers",
     "url": _GN_US + "%22Avure%22+OR+%22NC+Hyperbaric%22+OR+%22Stansted+Fluid%22+%22high+pressure%22",
     "filtered": False, "fetch_limit": 5},
    {"label": "HPP Manufacturers",
     "url": _GN_US + "%22high+pressure+processing%22+manufacturer+OR+equipment+OR+machine",
     "filtered": False, "fetch_limit": 5},

    # Food safety (Google News — pre-filtered by query)
    {"label": "Listeria Outbreaks",
     "url": _GN_US + "listeria+outbreak+food+recall+contamination",
     "filtered": False, "fetch_limit": 5},
    {"label": "Salmonella Outbreaks",
     "url": _GN_US + "salmonella+outbreak+food+recall+contamination",
     "filtered": False, "fetch_limit": 5},

    # HPP by sector
    {"label": "HPP Healthcare & Medical",
     "url": _GN_US + "%22high+pressure+processing%22+medical+OR+healthcare+OR+pharmaceutical+OR+biotech",
     "filtered": False, "fetch_limit": 5},
    {"label": "HPP Cosmetics & Beauty",
     "url": _GN_US + "%22high+pressure+processing%22+cosmetics+OR+skincare+OR+beauty+OR+%22personal+care%22",
     "filtered": False, "fetch_limit": 5},
    {"label": "HPP Dairy",
     "url": _GN_US + "%22high+pressure%22+dairy+OR+milk+OR+cheese+OR+yogurt+processing",
     "filtered": False, "fetch_limit": 5},
    {"label": "HPP Seafood",
     "url": _GN_US + "%22high+pressure%22+seafood+OR+shellfish+OR+oyster+OR+shrimp+processing",
     "filtered": False, "fetch_limit": 5},
    {"label": "HPP Juices & Beverages",
     "url": _GN_US + "%22high+pressure%22+juice+OR+beverage+OR+smoothie+OR+cold-pressed",
     "filtered": False, "fetch_limit": 5},
    {"label": "HPP Meat & Deli",
     "url": _GN_US + "%22high+pressure%22+meat+OR+deli+OR+charcuterie+OR+%22ready-to-eat%22+processing",
     "filtered": False, "fetch_limit": 5},
    {"label": "HPP Soups & Meals",
     "url": _GN_US + "%22high+pressure%22+soup+OR+%22ready+meal%22+OR+%22prepared+food%22+processing",
     "filtered": False, "fetch_limit": 5},
    {"label": "HPP Innovation & Research",
     "url": _GN_US + "%22high+pressure+processing%22+innovation+OR+research+OR+study+OR+technology",
     "filtered": False, "fetch_limit": 5},

    # UK & EU (Google News UK locale)
    {"label": "UK HPP Industry",
     "url": _GN_UK + "%22high+pressure+processing%22+UK+OR+Britain+OR+England",
     "filtered": False, "fetch_limit": 5},
    {"label": "UK & EU Food Safety",
     "url": _GN_UK + "food+safety+recall+contamination+UK+OR+Europe+OR+EFSA",
     "filtered": False, "fetch_limit": 5},
    {"label": "EU HPP & Food Tech",
     "url": _GN_UK + "%22high+pressure%22+food+technology+Europe+OR+EU+OR+European",
     "filtered": False, "fetch_limit": 5},
    {"label": "UK Food Industry News",
     "url": _GN_UK + "food+drink+industry+UK+processing+innovation",
     "filtered": False, "fetch_limit": 5},
]

MAX_RELEVANT_PER_FILTERED_FEED = 5   # cap after keyword filtering
MAX_TOTAL = 50

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
    limit    = feed.get("fetch_limit", 10)
    filtered = feed.get("filtered", False)

    req = urllib.request.Request(feed["url"], headers=HEADERS)
    with urllib.request.urlopen(req, timeout=15) as resp:
        raw = resp.read()

    root = ET.fromstring(raw)
    ns   = {"atom": "http://www.w3.org/2005/Atom"}
    items = []

    # ── RSS 2.0 ──────────────────────────────────────────────────────
    for item in root.findall(".//item")[:limit]:
        title = strip_html(item.findtext("title") or "")
        link  = (item.findtext("link") or "").strip()
        desc  = strip_html(item.findtext("description") or "")
        pub   = (item.findtext("pubDate") or
                 item.findtext("dc:date",
                               namespaces={"dc": "http://purl.org/dc/elements/1.1/"}) or "")
        if title and link:
            if not filtered or is_relevant(title, desc):
                items.append({"source": feed["label"], "title": title,
                              "link": link, "description": desc[:400], "pubDate": pub})
                if filtered and len(items) >= MAX_RELEVANT_PER_FILTERED_FEED:
                    break

    # ── Atom ─────────────────────────────────────────────────────────
    if not items:
        for entry in root.findall("atom:entry", ns)[:limit]:
            title = strip_html(entry.findtext("atom:title", namespaces=ns) or "")
            link_el = entry.find("atom:link[@rel='alternate']", ns) or entry.find("atom:link", ns)
            link  = (link_el.get("href", "") if link_el is not None else "").strip()
            desc  = strip_html(entry.findtext("atom:summary", namespaces=ns) or
                                entry.findtext("atom:content", namespaces=ns) or "")
            pub   = (entry.findtext("atom:published", namespaces=ns) or
                     entry.findtext("atom:updated", namespaces=ns) or "")
            if title and link:
                if not filtered or is_relevant(title, desc):
                    items.append({"source": feed["label"], "title": title,
                                  "link": link, "description": desc[:400], "pubDate": pub})
                    if filtered and len(items) >= MAX_RELEVANT_PER_FILTERED_FEED:
                        break

    return items


# ── Fetch all feeds ───────────────────────────────────────────────────────────
all_articles = []
ok_count  = 0
err_count = 0

for f in FEEDS:
    try:
        arts = fetch_rss(f)
        all_articles.extend(arts)
        tag = "(filtered)" if f.get("filtered") else ""
        print(f"  OK  {f['label']}: {len(arts)} articles {tag}")
        ok_count += 1
    except Exception as exc:
        print(f"  ERR {f['label']}: {exc}", file=sys.stderr)
        err_count += 1

# Deduplicate by link
seen  = set()
dedup = []
for a in all_articles:
    key = a["link"].split("?")[0].rstrip("/")   # ignore query-string variants
    if key not in seen:
        seen.add(key)
        dedup.append(a)

dedup.sort(key=lambda a: parse_date(a.get("pubDate", "")), reverse=True)
dedup = dedup[:MAX_TOTAL]

print(f"\n  Total: {len(dedup)} unique articles | feeds OK={ok_count} ERR={err_count}")

payload = {
    "updated":  datetime.now(timezone.utc).isoformat(),
    "articles": dedup,
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
