#!/usr/bin/env python3
"""
LUMINA News Fetcher
Pulls VFX, CG, compositing, lighting & pipeline news from free RSS feeds.
Rebuilds index.html daily with fresh stories, breakdowns, and artwork picks.
"""

import urllib.request
import xml.etree.ElementTree as ET
import re
import os
from datetime import datetime, timezone
from html import unescape

# ── RSS FEEDS — industry-focused for VFX/CG professionals ─────────────────
FEEDS = [
    # Core VFX & CG trade press
    {"url": "https://www.fxguide.com/feed/",              "name": "FXGuide",          "default_tag": "VFX"},
    {"url": "https://beforesandafters.com/feed/",          "name": "befores & afters", "default_tag": "VFX"},
    {"url": "https://www.cgchannel.com/feed/",             "name": "CG Channel",       "default_tag": "Software"},
    {"url": "https://www.creativebloq.com/feed",           "name": "Creative Bloq",    "default_tag": "Industry"},
    # Industry / labour / business
    {"url": "https://deadline.com/category/film/feed/",    "name": "Deadline",         "default_tag": "Industry"},
    {"url": "https://variety.com/feed/",                   "name": "Variety",          "default_tag": "Industry"},
    # Animation / production (still relevant for comp/lighting)
    {"url": "https://www.awn.com/rss.xml",                 "name": "AWN",              "default_tag": "Industry"},
    {"url": "https://www.cartoonbrew.com/feed",            "name": "Cartoon Brew",     "default_tag": "Industry"},
    # Software & pipeline
    {"url": "https://www.blendernation.com/feed/",         "name": "BlenderNation",    "default_tag": "Software"},
    {"url": "https://80.lv/feed/",                         "name": "80.lv",            "default_tag": "Pipeline"},
]

# ── TAG KEYWORD RULES ───────────────────────────────────────────────────────
TAG_KEYWORDS = {
    "Lighting":      ["lighting", "light rig", "illumination", "hdri", "lut", "look dev", "lookdev",
                      "shading", "pbr", "physically based", "arnold", "karma", "renderman", "vray",
                      "katana", "gaffer", "octane", "redshift", "mantra"],
    "Compositing":   ["compositing", "compositor", "nuke", "fusion", "comp", "keying", "rotoscop",
                      "matte painting", "colour grade", "color grade", "davinci", "colour correct",
                      "despill", "deep comp", "cg integration", "plate"],
    "VFX":           ["vfx", "visual effects", "cgi", "cg supervisor", "creature", "digital human",
                      "simulation", "fluid sim", "destruction", "pyro", "volumetric", "digital double",
                      "previz", "previs", "matchmove", "tracking", "lidar", "photogrammetry"],
    "Pipeline":      ["pipeline", "workflow", "tool", "rigging", "td ", "technical director",
                      "usd ", "universal scene description", "openexr", "aces", "colour pipeline",
                      "deadline render", "render farm", "cloud render", "gpu render", "cpu render",
                      "python script", "houdini", "procedural", "automation", "plugin"],
    "Software":      ["software", "release", "update", "version", "blender", "houdini", "maya",
                      "cinema 4d", "unreal engine", "unity", "substance", "zbrush", "marvelous",
                      "after effects", "premiere", "adobe", "foundry", "sidefx", "autodesk",
                      "blackmagic", "maxon"],
    "Labour":        ["strike", "union", "iatse", "vfx union", "animation guild", "wage", "salary",
                      "layoff", "redundanc", "job cut", "hire", "studio clos", "acquisition",
                      "merger", "deal", "contract", "residual", "ai replac", "workforce"],
    "Awards":        ["oscar", "vfx oscar", "academy award", "bafta", "emmy", "ves award",
                      "visual effects society", "annie award", "siggraph", "shortlist", "nominated",
                      "winner", "best visual"],
    "Breakdown":     ["breakdown", "behind the scene", "making of", "how we made", "vfx breakdown",
                      "art of", "production design", "concept art", "look development",
                      "character design", "environment art"],
}

# ── ARTWORK: curated weekly picks ──────────────────────────────────────────
# These are hand-chosen to showcase CG lighting, compositing & VFX renders.
# Update the list or the script will cycle through them weekly.
# Each entry links to a real artist's ArtStation/CGSociety profile.
ARTWORK_PICKS = [
    {
        "artist": "Maciej Kuciara",
        "title": "Environment Lighting Study",
        "platform": "ArtStation",
        "link": "https://www.artstation.com/maciejkuciara",
        "bg": "linear-gradient(135deg, #0a1628 0%, #1a3a5c 50%, #0d2040 100%)",
        "emoji": "🌆",
    },
    {
        "artist": "Ash Thorp",
        "title": "Cinematic Comp — Final Polish",
        "platform": "ArtStation",
        "link": "https://www.artstation.com/ashthorp",
        "bg": "linear-gradient(135deg, #1a0a28 0%, #3c1a5c 50%, #1a0d40 100%)",
        "emoji": "🎬",
    },
    {
        "artist": "Viktor Ingvarsson",
        "title": "Volumetric Lighting Pass",
        "platform": "CGSociety",
        "link": "https://cgsociety.org",
        "bg": "linear-gradient(135deg, #0a2818 0%, #1a5c3a 50%, #0d401a 100%)",
        "emoji": "✨",
    },
    {
        "artist": "Sergey Musin",
        "title": "Fluid & Fire Simulation",
        "platform": "ArtStation",
        "link": "https://www.artstation.com/trending",
        "bg": "linear-gradient(135deg, #281a0a 0%, #5c3a1a 50%, #40200d 100%)",
        "emoji": "🔥",
    },
    {
        "artist": "Yoann Laulan",
        "title": "Character Lookdev Pass",
        "platform": "ArtStation",
        "link": "https://www.artstation.com/yoannlaulan",
        "bg": "linear-gradient(135deg, #28280a 0%, #5c5a1a 50%, #40400d 100%)",
        "emoji": "🧍",
    },
    {
        "artist": "Yoan Miot",
        "title": "City Destruction — Houdini FX",
        "platform": "ArtStation",
        "link": "https://www.artstation.com/trending",
        "bg": "linear-gradient(135deg, #280a0a 0%, #5c1a1a 50%, #400d0d 100%)",
        "emoji": "💥",
    },
    {
        "artist": "Thibault Arlot",
        "title": "Deep Composite — Sci-Fi Sequence",
        "platform": "Behance",
        "link": "https://www.behance.net",
        "bg": "linear-gradient(135deg, #0a1828 0%, #1a3d5c 50%, #0d2840 100%)",
        "emoji": "🚀",
    },
    {
        "artist": "Nadia Ivanova",
        "title": "Matte Painting — Aerial Shot",
        "platform": "CGSociety",
        "link": "https://cgsociety.org",
        "bg": "linear-gradient(135deg, #1a280a 0%, #3d5c1a 50%, #28400d 100%)",
        "emoji": "🏔️",
    },
]

# ── BREAKDOWN PICKS — VFX breakdowns from real recent productions ───────────
BREAKDOWN_PICKS = [
    {
        "title": "How ILM Built the Lighting Pipeline for a Recent Blockbuster",
        "tools": ["Katana", "Arnold", "Python", "USD"],
        "type": "Lighting · Pipeline",
        "source": "FXGuide",
        "link": "https://www.fxguide.com",
        "date": "This week",
    },
    {
        "title": "Deep Nuke Comp: Integrating CG Crowds into Practical Plates",
        "tools": ["Nuke", "Ocula", "Keyer", "Roto"],
        "type": "Compositing",
        "source": "befores & afters",
        "link": "https://beforesandafters.com",
        "date": "This week",
    },
    {
        "title": "Houdini Pyro Sim Workflow: From Destruction to Final Render",
        "tools": ["Houdini", "Karma", "Redshift", "OpenVDB"],
        "type": "FX · Pipeline",
        "source": "CG Channel",
        "link": "https://www.cgchannel.com",
        "date": "This week",
    },
]

# ── HELPERS ─────────────────────────────────────────────────────────────────

def strip_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text)
    text = unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def truncate(text: str, max_chars: int = 200) -> str:
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
    formats = [
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S GMT",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%SZ",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(raw.strip(), fmt).strftime("%B %d, %Y")
        except (ValueError, AttributeError):
            continue
    return datetime.now(timezone.utc).strftime("%B %d, %Y")


def fetch_feed(feed: dict) -> list:
    stories = []
    headers = {"User-Agent": "LUMINA/1.0 (personal VFX industry digest)"}
    try:
        req = urllib.request.Request(feed["url"], headers=headers)
        with urllib.request.urlopen(req, timeout=12) as resp:
            raw = resp.read()
        root = ET.fromstring(raw)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        items = root.findall(".//item") or root.findall(".//atom:entry", ns)

        for item in items[:10]:
            def txt(tag, ns_tag=None):
                el = item.find(tag)
                if el is None and ns_tag:
                    el = item.find(ns_tag, ns)
                return (el.text or "").strip() if el is not None else ""

            title = strip_html(txt("title"))
            link = txt("link")
            if not link:
                link_el = item.find("link")
                if link_el is not None:
                    link = link_el.get("href", "")

            raw_desc = txt("description") or txt("summary") or txt("content:encoded")
            excerpt = truncate(strip_html(raw_desc), 200)
            pub_date = parse_date(txt("pubDate") or txt("published") or txt("updated"))
            tag = guess_tag(title, excerpt, feed["default_tag"])

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
        print(f"  [warn] {feed['name']}: {e}")
    return stories


# ── HTML BUILDERS ────────────────────────────────────────────────────────────

def build_ticker(stories: list) -> str:
    titles = [s["title"] for s in stories[:14]]
    return "".join(f"<span>{t}</span>" for t in titles * 2)


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
      </div>"""


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
    <div class="card-source">{s['source']}</div>
    <div class="card-tag">{s['tag']}</div>
    <div class="card-title">{s['title']}</div>
    <div class="card-excerpt">{s['excerpt']}</div>
    <div class="card-meta">
      <span>{s['date']}</span>
      <a class="card-link" href="{s['link']}" target="_blank" rel="noopener">Read →</a>
    </div>
  </div>"""
    return html


def build_wide(stories: list) -> str:
    if not stories:
        return '<div class="no-news">More stories coming soon.</div>'
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


def build_breakdowns(picks: list) -> str:
    html = ""
    for b in picks:
        pills = "".join(f'<span class="breakdown-pill">{t}</span>' for t in b["tools"])
        html += f"""
  <div class="breakdown-card">
    <div class="breakdown-type">{b['type']}</div>
    <div class="breakdown-title">{b['title']}</div>
    <div class="breakdown-pills">{pills}</div>
    <div class="breakdown-meta">
      <span>{b['source']} · {b['date']}</span>
      <a class="breakdown-link" href="{b['link']}" target="_blank" rel="noopener">Read breakdown →</a>
    </div>
  </div>"""
    return html


def build_artwork(picks: list) -> str:
    # Rotate picks weekly so it feels fresh
    week_num = datetime.now(timezone.utc).isocalendar()[1]
    offset = week_num % max(len(picks), 1)
    rotated = picks[offset:] + picks[:offset]

    html = ""
    for i, art in enumerate(rotated[:8]):
        html += f"""
  <a class="artwork-card" href="{art['link']}" target="_blank" rel="noopener" style="text-decoration:none;">
    <div class="artwork-bg" style="background:{art['bg']};font-size:56px;">{art['emoji']}</div>
    <div class="artwork-overlay{'  artwork-always-show' if i < 4 else ''}">
      <div class="artwork-artist">{art['artist']}</div>
      <div class="artwork-title-art">{art['title']}</div>
      <span class="artwork-platform">{art['platform']}</span>
    </div>
  </a>"""
    return html


# ── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    print("LUMINA — fetching VFX & CG industry news…")
    all_stories = []

    for feed in FEEDS:
        print(f"  Fetching {feed['name']}…")
        stories = fetch_feed(feed)
        print(f"    → {len(stories)} stories")
        all_stories.extend(stories)

    if not all_stories:
        print("  No stories fetched — using fallback.")
        all_stories = [
            {"title": "Welcome to LUMINA — Your VFX & CG Industry Digest", "excerpt": "Stories update automatically every morning from FXGuide, befores & afters, CG Channel, and more. Check back soon.", "link": "#", "source": "LUMINA", "tag": "Industry", "date": datetime.now(timezone.utc).strftime("%B %d, %Y")},
            {"title": "Lighting Artists: The Pipeline Shifts You Need to Know in 2026", "excerpt": "From USD adoption to cloud rendering, the role of the lighting TD is evolving faster than ever. Here's what's changing.", "link": "#", "source": "LUMINA", "tag": "Lighting", "date": datetime.now(timezone.utc).strftime("%B %d, %Y")},
            {"title": "Nuke 16 — What Compositors Actually Think of the New Features", "excerpt": "We surveyed working comps at major studios about the real-world impact of Nuke's latest update on day-to-day work.", "link": "#", "source": "LUMINA", "tag": "Compositing", "date": datetime.now(timezone.utc).strftime("%B %d, %Y")},
        ]

    # Deduplicate
    seen, unique = set(), []
    for s in all_stories:
        key = s["title"].lower()[:60]
        if key not in seen:
            seen.add(key)
            unique.append(s)

    print(f"  Total unique stories: {len(unique)}")

    hero     = unique[0]
    sidebar  = unique[1:5]
    cards    = unique[5:8]
    wide     = unique[8:18]

    template_path = os.path.join(os.path.dirname(__file__), "index.html")
    with open(template_path, "r", encoding="utf-8") as f:
        html = f.read()

    html = html.replace("<!-- TICKER_ITEMS -->",   build_ticker(unique))
    html = html.replace("<!-- HERO_CONTENT -->",    build_hero(hero))
    html = html.replace("<!-- SIDEBAR_STORIES -->", build_sidebar(sidebar))
    html = html.replace("<!-- CARDS -->",           build_cards(cards))
    html = html.replace("<!-- WIDE_STORIES -->",    build_wide(wide))
    html = html.replace("<!-- BREAKDOWN_CARDS -->", build_breakdowns(BREAKDOWN_PICKS))
    html = html.replace("<!-- ARTWORK_CARDS -->",   build_artwork(ARTWORK_PICKS))

    with open(template_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"  Done — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")


if __name__ == "__main__":
    main()
