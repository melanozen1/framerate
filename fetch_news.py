#!/usr/bin/env python3
"""
FrameRate News Fetcher
Pulls animation news from free RSS feeds and rebuilds index.html daily.
"""

import urllib.request
import xml.etree.ElementTree as ET
import json
import re
import os
from datetime import datetime, timezone
from html import unescape

# ── RSS sources (all free, no API key needed) ──────────────────────────────
FEEDS = [
    {
        "url": "https://www.cartoonbrew.com/feed",
        "name": "Cartoon Brew",
        "tag": "Industry",
    },
    {
        "url": "https://www.awn.com/rss.xml",
        "name": "AWN",
        "tag": "Film",
    },
    {
        "url": "https://feeds.feedburner.com/deadline/animation",
        "name": "Deadline",
        "tag": "Industry",
    },
    {
        "url": "https://variety.com/v/animation/feed/",
        "name": "Variety",
        "tag": "Film",
    },
    {
        "url": "https://www.animationmagazine.net/feed/",
        "name": "Animation Magazine",
        "tag": "Industry",
    },
]

# Fallback stories shown if all feeds fail (keeps site looking good offline)
FALLBACK_STORIES = [
    {
        "title": "Welcome to FrameRate — Your Daily Animation Digest",
        "excerpt": "Stories are fetched automatically every morning. Check back soon for today's latest animation news from Cartoon Brew, AWN, Deadline, Variety, and more.",
        "link": "#",
        "source": "FrameRate",
        "tag": "Welcome",
        "date": datetime.now(timezone.utc).strftime("%B %d, %Y"),
    },
    {
        "title": "Animation Industry Continues to Evolve in 2026",
        "excerpt": "From AI-assisted pipelines to new streaming deals, the animation landscape is shifting rapidly. FrameRate tracks it all so you don't have to.",
        "link": "#",
        "source": "FrameRate",
        "tag": "Industry",
        "date": datetime.now(timezone.utc).strftime("%B %d, %Y"),
    },
    {
        "title": "The Golden Age of Animated Series Isn't Over Yet",
        "excerpt": "Despite industry headwinds, original animated series continue to find passionate audiences across every platform and genre.",
        "link": "#",
        "source": "FrameRate",
        "tag": "TV & Streaming",
        "date": datetime.now(timezone.utc).strftime("%B %d, %Y"),
    },
]

TAG_KEYWORDS = {
    "Anime": ["anime", "manga", "crunchyroll", "shonen", "seinen", "studio ghibli", "mappa", "ufotable", "trigger"],
    "TV & Streaming": ["netflix", "disney+", "hbo", "hulu", "apple tv", "amazon", "series", "season", "episode", "streaming", "show"],
    "Film": ["film", "movie", "box office", "theatrical", "feature", "pixar", "dreamworks", "disney", "illumination", "sony pictures"],
    "Festivals": ["festival", "annecy", "ottowa", "cannes", "sundance", "award", "oscar", "annie", "emmy"],
    "Technology": ["ai", "artificial intelligence", "software", "pipeline", "render", "unreal", "blender", "toon boom", "adobe"],
    "Indie": ["independent", "indie", "kickstarter", "short film", "student"],
}


def strip_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text)
    text = unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def truncate(text: str, max_chars: int = 160) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rsplit(" ", 1)[0] + "…"


def guess_tag(title: str, excerpt: str, default: str) -> str:
    combined = (title + " " + excerpt).lower()
    for tag, keywords in TAG_KEYWORDS.items():
        if any(k in combined for k in keywords):
            return tag
    return default


def parse_date(raw: str) -> str:
    """Try several common RSS date formats and return a readable string."""
    formats = [
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S GMT",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%SZ",
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(raw.strip(), fmt)
            return dt.strftime("%B %d, %Y")
        except (ValueError, AttributeError):
            continue
    return datetime.now(timezone.utc).strftime("%B %d, %Y")


def fetch_feed(feed: dict) -> list:
    stories = []
    headers = {"User-Agent": "FrameRate/1.0 (personal animation news digest)"}
    try:
        req = urllib.request.Request(feed["url"], headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read()
        root = ET.fromstring(raw)

        # Handle both RSS (<item>) and Atom (<entry>) formats
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        items = root.findall(".//item") or root.findall(".//atom:entry", ns)

        for item in items[:8]:
            def txt(tag, ns_tag=None):
                el = item.find(tag)
                if el is None and ns_tag:
                    el = item.find(ns_tag, ns)
                return (el.text or "").strip() if el is not None else ""

            title = strip_html(txt("title"))
            link = txt("link") or txt("atom:link", "atom:link")
            # Atom <link> is an attribute, not text
            if not link:
                link_el = item.find("link")
                if link_el is not None:
                    link = link_el.get("href", "")

            raw_desc = txt("description") or txt("summary") or txt("content:encoded")
            excerpt = truncate(strip_html(raw_desc), 180)
            pub_date = parse_date(txt("pubDate") or txt("published") or txt("updated"))
            tag = guess_tag(title, excerpt, feed["tag"])

            if title and link:
                stories.append({
                    "title": title,
                    "excerpt": excerpt,
                    "link": link,
                    "source": feed["name"],
                    "tag": tag,
                    "date": pub_date,
                })
    except Exception as e:
        print(f"  [warn] Could not fetch {feed['name']}: {e}")
    return stories


def build_ticker(stories: list) -> str:
    titles = [s["title"] for s in stories[:12]]
    doubled = titles * 2  # duplicate for seamless loop
    items_html = "".join(f"<span>{t}</span>" for t in doubled)
    return items_html


def build_hero(story: dict) -> str:
    return f"""
      <span class="hero-tag">{story['tag']}</span>
      <h1 class="hero-title">{story['title']}</h1>
      <p class="hero-excerpt">{story['excerpt']}</p>
      <div class="hero-meta">
        <span>{story['source']}</span>
        <span class="hero-meta-dot"></span>
        <span>{story['date']}</span>
        <span class="hero-meta-dot"></span>
        <a class="hero-link" href="{story['link']}" target="_blank" rel="noopener">Read full story →</a>
      </div>
    """


def build_sidebar(stories: list) -> str:
    html = ""
    for s in stories:
        html += f"""
    <div class="sidebar-story">
      <div class="sidebar-tag">{s['tag']}</div>
      <div class="sidebar-title">{s['title']}</div>
      <div class="sidebar-meta">{s['source']} · {s['date']} · <a class="sidebar-link" href="{s['link']}" target="_blank" rel="noopener">Read →</a></div>
    </div>"""
    return html


def build_cards(stories: list) -> str:
    if not stories:
        return '<div class="no-news">No stories found — check back after the next update.</div>'
    html = ""
    for s in stories:
        html += f"""
  <div class="card" data-tag="{s['tag']}">
    <div class="card-source-badge">{s['source']}</div>
    <div class="card-tag">{s['tag']}</div>
    <div class="card-title">{s['title']}</div>
    <div class="card-excerpt">{s['excerpt']}</div>
    <div class="card-meta">
      <span>{s['date']}</span>
      <a class="card-link" href="{s['link']}" target="_blank" rel="noopener">Read full story →</a>
    </div>
  </div>"""
    return html


def build_wide(stories: list) -> str:
    if not stories:
        return '<div class="no-news">More stories coming after the next update.</div>'
    html = ""
    for s in stories:
        html += f"""
  <div class="wide-story" data-tag="{s['tag']}">
    <div class="wide-story-tag">{s['tag']}</div>
    <div class="wide-story-title">{s['title']}</div>
    <div class="wide-story-meta">
      <span>{s['source']} · {s['date']}</span>
      <a class="wide-story-link" href="{s['link']}" target="_blank" rel="noopener">Read →</a>
    </div>
  </div>"""
    return html


def main():
    print("FrameRate — fetching animation news…")
    all_stories = []

    for feed in FEEDS:
        print(f"  Fetching {feed['name']}…")
        stories = fetch_feed(feed)
        print(f"    → {len(stories)} stories")
        all_stories.extend(stories)

    if not all_stories:
        print("  No stories fetched — using fallback content.")
        all_stories = FALLBACK_STORIES

    # Deduplicate by title
    seen = set()
    unique = []
    for s in all_stories:
        key = s["title"].lower()[:60]
        if key not in seen:
            seen.add(key)
            unique.append(s)

    print(f"  Total unique stories: {len(unique)}")

    hero = unique[0]
    sidebar = unique[1:5]
    cards = unique[5:8]
    wide = unique[8:16]

    # Read template
    template_path = os.path.join(os.path.dirname(__file__), "index.html")
    with open(template_path, "r", encoding="utf-8") as f:
        html = f.read()

    # Inject content
    html = html.replace("<!-- TICKER_ITEMS -->", build_ticker(unique))
    html = html.replace("<!-- HERO_CONTENT -->", build_hero(hero))
    html = html.replace("<!-- SIDEBAR_STORIES -->", build_sidebar(sidebar))
    html = html.replace("<!-- CARDS -->", build_cards(cards))
    html = html.replace("<!-- WIDE_STORIES -->", build_wide(wide))

    with open(template_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"  index.html updated successfully — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")


if __name__ == "__main__":
    main()
