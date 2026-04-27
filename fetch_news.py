#!/usr/bin/env python3
"""
LUMINA News Fetcher
- Pulls VFX/CG/pipeline/compositing/lighting news from RSS feeds
- Extracts real thumbnail images from each story
- Fetches real artwork from ArtStation's public GraphQL API
- Rebuilds index.html daily
"""

import urllib.request
import urllib.parse
import urllib.error
import xml.etree.ElementTree as ET
import json
import re
import os
from datetime import datetime, timezone
from html import unescape

# ── RSS FEEDS ──────────────────────────────────────────────────────────────
FEEDS = [
    {"url": "https://www.fxguide.com/feed/",             "name": "FXGuide",          "default_tag": "VFX"},
    {"url": "https://beforesandafters.com/feed/",         "name": "befores & afters", "default_tag": "VFX"},
    {"url": "https://www.cgchannel.com/feed/",            "name": "CG Channel",       "default_tag": "Software"},
    {"url": "https://www.creativebloq.com/feed",          "name": "Creative Bloq",    "default_tag": "Industry"},
    {"url": "https://deadline.com/category/film/feed/",   "name": "Deadline",         "default_tag": "Industry"},
    {"url": "https://variety.com/feed/",                  "name": "Variety",          "default_tag": "Industry"},
    {"url": "https://www.awn.com/rss.xml",                "name": "AWN",              "default_tag": "Industry"},
    {"url": "https://www.cartoonbrew.com/feed",           "name": "Cartoon Brew",     "default_tag": "Industry"},
    {"url": "https://www.blendernation.com/feed/",        "name": "BlenderNation",    "default_tag": "Software"},
    {"url": "https://80.lv/feed/",                        "name": "80.lv",            "default_tag": "Pipeline"},
]

TAG_KEYWORDS = {
    "Lighting":    ["lighting", "light rig", "illumination", "hdri", "lut", "look dev", "lookdev",
                    "shading", "pbr", "physically based", "arnold", "karma", "renderman", "vray",
                    "katana", "gaffer", "octane", "redshift", "mantra"],
    "Compositing": ["compositing", "compositor", "nuke", "fusion", "comp", "keying", "rotoscop",
                    "matte painting", "colour grade", "color grade", "davinci", "colour correct",
                    "despill", "deep comp", "cg integration", "plate"],
    "VFX":         ["vfx", "visual effects", "cgi", "cg supervisor", "creature", "digital human",
                    "simulation", "fluid sim", "destruction", "pyro", "volumetric", "digital double",
                    "previz", "previs", "matchmove", "tracking", "lidar", "photogrammetry"],
    "Pipeline":    ["pipeline", "workflow", "rigging", "td ", "technical director",
                    "usd ", "universal scene description", "openexr", "aces",
                    "render farm", "cloud render", "gpu render", "houdini", "procedural", "automation", "plugin"],
    "Software":    ["software", "release", "update", "version", "blender", "houdini", "maya",
                    "cinema 4d", "unreal engine", "unity", "substance", "zbrush",
                    "after effects", "adobe", "foundry", "sidefx", "autodesk", "blackmagic", "maxon"],
    "Labour":      ["strike", "union", "iatse", "vfx union", "animation guild", "wage", "salary",
                    "layoff", "redundanc", "job cut", "studio clos", "acquisition",
                    "merger", "deal", "contract", "residual", "ai replac", "workforce"],
    "Awards":      ["oscar", "vfx oscar", "academy award", "bafta", "emmy", "ves award",
                    "visual effects society", "annie award", "siggraph", "shortlist", "nominated", "winner"],
    "Breakdown":   ["breakdown", "behind the scene", "making of", "how we made", "vfx breakdown",
                    "art of", "production design", "concept art", "look development"],
}

BREAKDOWN_PICKS = [
    {"title": "How ILM Built the Lighting Pipeline for a Recent Blockbuster",
     "tools": ["Katana", "Arnold", "Python", "USD"], "type": "Lighting · Pipeline",
     "source": "FXGuide", "link": "https://www.fxguide.com", "date": "This week"},
    {"title": "Deep Nuke Comp: Integrating CG Crowds into Practical Plates",
     "tools": ["Nuke", "Ocula", "Keyer", "Roto"], "type": "Compositing",
     "source": "befores & afters", "link": "https://beforesandafters.com", "date": "This week"},
    {"title": "Houdini Pyro Sim Workflow: From Destruction to Final Render",
     "tools": ["Houdini", "Karma", "Redshift", "OpenVDB"], "type": "FX · Pipeline",
     "source": "CG Channel", "link": "https://www.cgchannel.com", "date": "This week"},
]

HEADERS = {"User-Agent": "LUMINA/1.0 (personal VFX industry digest; contact via github)"}

# ── IMAGE EXTRACTION ────────────────────────────────────────────────────────

def extract_image_from_item(item, raw_xml_text: str) -> str:
    """
    Try multiple strategies to find a usable image URL from an RSS item.
    Returns URL string or empty string if none found.
    """
    # Strategy 1: <media:content url="..."> or <media:thumbnail url="...">
    for tag in ["media:content", "media:thumbnail"]:
        # ElementTree drops namespace prefixes sometimes — search both ways
        el = item.find(tag)
        if el is None:
            # Try with explicit namespace
            el = item.find("{http://search.yahoo.com/mrss/}" + tag.split(":")[1])
        if el is not None:
            url = el.get("url", "")
            if url and is_valid_image_url(url):
                return url

    # Strategy 2: <enclosure url="..." type="image/...">
    enc = item.find("enclosure")
    if enc is not None:
        url = enc.get("url", "")
        mime = enc.get("type", "")
        if url and ("image" in mime or is_valid_image_url(url)):
            return url

    # Strategy 3: first <img src="..."> inside description/content
    for field in ["description", "content:encoded", "summary"]:
        el = item.find(field)
        if el is None:
            el = item.find("{http://purl.org/rss/1.0/modules/content/}encoded")
        if el is not None and el.text:
            img = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', el.text, re.IGNORECASE)
            if img:
                url = img.group(1)
                if is_valid_image_url(url):
                    return url

    # Strategy 4: og:image or twitter:image style meta scraped from raw feed bytes
    og = re.search(r'<og:image[^>]*>([^<]+)</og:image>', raw_xml_text or "", re.IGNORECASE)
    if og and is_valid_image_url(og.group(1).strip()):
        return og.group(1).strip()

    return ""


def is_valid_image_url(url: str) -> bool:
    if not url or not url.startswith("http"):
        return False
    # Exclude tiny tracking pixels and svg icons
    low = url.lower()
    if any(x in low for x in ["1x1", "pixel", "tracking", "blank", "spacer"]):
        return False
    return True


# ── ARTSTATION API ──────────────────────────────────────────────────────────

ARTSTATION_QUERY = """
{
  projects(first: 20, sorting: trending, tags: ["VFX", "Lighting", "Compositing", "CGI", "3D", "Render"]) {
    edges {
      node {
        id
        title
        cover_url
        url
        user {
          full_name
          username
        }
      }
    }
  }
}
"""

def fetch_artstation_projects() -> list:
    """
    Fetch trending CG/VFX artwork from ArtStation's public GraphQL API.
    Returns list of dicts with artist, title, image_url, link.
    Falls back to empty list gracefully.
    """
    # ArtStation public API — no auth required for trending
    url = "https://www.artstation.com/api/v2/community/posts.json?dimension=trending&page=1"
    try:
        req = urllib.request.Request(url, headers={**HEADERS, "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())

        picks = []
        for item in data.get("data", [])[:20]:
            # Filter for CG/VFX relevant categories
            categories = [c.get("name", "").lower() for c in item.get("categories", [])]
            mediums = [m.get("name", "").lower() for m in item.get("mediums", [])]
            all_cats = " ".join(categories + mediums)

            relevant_terms = ["3d", "vfx", "cgi", "lighting", "render", "compositing",
                              "environment", "character", "fx", "simulation", "concept"]
            if not any(t in all_cats for t in relevant_terms):
                continue

            cover = item.get("cover", {})
            image_url = (cover.get("medium_image_url") or
                         cover.get("small_image_url") or
                         cover.get("image_url") or "")

            if not image_url or not image_url.startswith("http"):
                continue

            user = item.get("user", {})
            username = user.get("username", "")
            full_name = user.get("full_name", username)

            picks.append({
                "artist": full_name or username,
                "title": item.get("title", "Untitled"),
                "image_url": image_url,
                "link": f"https://www.artstation.com/{username}" if username else "https://www.artstation.com/trending",
                "platform": "ArtStation",
            })

            if len(picks) >= 8:
                break

        print(f"  ArtStation: {len(picks)} artwork picks")
        return picks

    except Exception as e:
        print(f"  [warn] ArtStation API: {e}")
        return []


# ── HELPERS ─────────────────────────────────────────────────────────────────

def strip_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text)
    text = unescape(text)
    return re.sub(r"\s+", " ", text).strip()


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
    for fmt in ["%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S GMT",
                "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ"]:
        try:
            return datetime.strptime(raw.strip(), fmt).strftime("%B %d, %Y")
        except (ValueError, AttributeError):
            continue
    return datetime.now(timezone.utc).strftime("%B %d, %Y")


def fetch_feed(feed: dict) -> list:
    stories = []
    try:
        req = urllib.request.Request(feed["url"], headers=HEADERS)
        with urllib.request.urlopen(req, timeout=12) as resp:
            raw = resp.read()

        raw_text = raw.decode("utf-8", errors="replace")

        # Register all common namespaces so ET doesn't choke
        namespaces = {
            "media":   "http://search.yahoo.com/mrss/",
            "content": "http://purl.org/rss/1.0/modules/content/",
            "atom":    "http://www.w3.org/2005/Atom",
            "dc":      "http://purl.org/dc/elements/1.1/",
        }
        for prefix, uri in namespaces.items():
            try:
                ET.register_namespace(prefix, uri)
            except Exception:
                pass

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

            raw_desc = txt("description") or txt("summary")
            content_el = item.find("{http://purl.org/rss/1.0/modules/content/}encoded")
            if content_el is not None and content_el.text:
                raw_desc = raw_desc or content_el.text

            excerpt = truncate(strip_html(raw_desc), 200)
            pub_date = parse_date(txt("pubDate") or txt("published") or txt("updated"))
            tag = guess_tag(title, excerpt, feed["default_tag"])
            image_url = extract_image_from_item(item, raw_text)

            if title and link:
                stories.append({
                    "title":     title,
                    "excerpt":   excerpt,
                    "link":      link,
                    "source":    feed["name"],
                    "tag":       tag,
                    "date":      pub_date,
                    "image_url": image_url,
                })
    except Exception as e:
        print(f"  [warn] {feed['name']}: {e}")
    return stories


# ── PLACEHOLDER GRADIENTS (fallback when no image) ─────────────────────────

GRADIENTS = [
    "linear-gradient(135deg,#0a1628,#1a3a5c)",
    "linear-gradient(135deg,#1a0a28,#3c1a5c)",
    "linear-gradient(135deg,#0a2818,#1a5c3a)",
    "linear-gradient(135deg,#281a0a,#5c3a1a)",
    "linear-gradient(135deg,#28080a,#5c1a1e)",
    "linear-gradient(135deg,#0a2828,#1a5c5a)",
    "linear-gradient(135deg,#180a28,#401a5c)",
    "linear-gradient(135deg,#0a1820,#1a4050)",
]


def img_or_gradient(url: str, index: int = 0) -> str:
    """Return either an <img> tag or a gradient div as the card visual."""
    if url:
        return f'<img src="{url}" alt="" style="width:100%;height:100%;object-fit:cover;display:block;" loading="lazy" onerror="this.parentElement.style.background=\'{GRADIENTS[index % len(GRADIENTS)]}\';this.remove();">'
    return f'<div style="width:100%;height:100%;background:{GRADIENTS[index % len(GRADIENTS)]};"></div>'


# ── HTML BUILDERS ────────────────────────────────────────────────────────────

def build_ticker(stories: list) -> str:
    titles = [s["title"] for s in stories[:14]]
    return "".join(f"<span>{t}</span>" for t in titles * 2)


def build_hero(story: dict) -> str:
    bg_style = ""
    if story.get("image_url"):
        bg_style = f'style="background-image:url(\'{story["image_url"]}\');background-size:cover;background-position:center;"'
    return f"""
      <div class="hero-img-wrap" {bg_style}></div>
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
        thumb = ""
        if s.get("image_url"):
            thumb = f'<img src="{s["image_url"]}" alt="" style="width:64px;height:48px;object-fit:cover;border-radius:3px;flex-shrink:0;" loading="lazy">'
        html += f"""
    <div class="sidebar-story">
      <div style="display:flex;gap:10px;align-items:flex-start;">
        {thumb}
        <div>
          <div class="sidebar-tag">{s['tag']}</div>
          <div class="sidebar-title">{s['title']}</div>
          <div class="sidebar-meta">{s['source']} · {s['date']} · <a class="sidebar-link" href="{s['link']}" target="_blank" rel="noopener">Read →</a></div>
        </div>
      </div>
    </div>"""
    return html


def build_cards(stories: list) -> str:
    if not stories:
        return '<div class="no-news">No stories found — check back after the next update.</div>'
    html = ""
    for i, s in enumerate(stories):
        visual = img_or_gradient(s.get("image_url", ""), i)
        html += f"""
  <div class="card" data-tag="{s['tag']}">
    <div class="card-img">{visual}</div>
    <div class="card-body">
      <div class="card-source">{s['source']}</div>
      <div class="card-tag">{s['tag']}</div>
      <div class="card-title">{s['title']}</div>
      <div class="card-excerpt">{s['excerpt']}</div>
      <div class="card-meta">
        <span>{s['date']}</span>
        <a class="card-link" href="{s['link']}" target="_blank" rel="noopener">Read →</a>
      </div>
    </div>
  </div>"""
    return html


def build_wide(stories: list) -> str:
    if not stories:
        return '<div class="no-news">More stories coming soon.</div>'
    html = ""
    for i, s in enumerate(stories):
        thumb_html = ""
        if s.get("image_url"):
            thumb_html = f'<img src="{s["image_url"]}" alt="" style="width:90px;height:60px;object-fit:cover;border-radius:4px;flex-shrink:0;" loading="lazy" onerror="this.remove();">'
        else:
            thumb_html = f'<div style="width:90px;height:60px;border-radius:4px;flex-shrink:0;background:{GRADIENTS[i%len(GRADIENTS)]};"></div>'
        html += f"""
  <div class="wide-story" data-tag="{s['tag']}">
    <div style="display:flex;gap:12px;align-items:flex-start;">
      {thumb_html}
      <div>
        <div class="wide-story-tag">{s['tag']}</div>
        <div class="wide-story-title">{s['title']}</div>
        <div class="wide-story-meta">
          <span>{s['source']} · {s['date']}</span>
          <a class="wide-story-link" href="{s['link']}" target="_blank" rel="noopener">Read →</a>
        </div>
      </div>
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
    if not picks:
        # Fallback gradient cards if API failed
        fallback = [
            {"artist":"ArtStation Trending","title":"Browse top CG & VFX artwork","image_url":"","link":"https://www.artstation.com/trending","platform":"ArtStation"},
        ] * 8
        picks = fallback

    html = ""
    for i, art in enumerate(picks[:8]):
        if art.get("image_url"):
            img_html = f'<img src="{art["image_url"]}" alt="{art["title"]}" style="width:100%;height:100%;object-fit:cover;display:block;transition:transform 0.4s ease;" loading="lazy" onerror="this.parentElement.style.background=\'{GRADIENTS[i%len(GRADIENTS)]}\';this.remove();">'
        else:
            img_html = f'<div style="width:100%;height:100%;background:{GRADIENTS[i%len(GRADIENTS)]};"></div>'

        html += f"""
  <a class="artwork-card" href="{art['link']}" target="_blank" rel="noopener">
    <div class="artwork-img-wrap">{img_html}</div>
    <div class="artwork-overlay">
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
        now = datetime.now(timezone.utc).strftime("%B %d, %Y")
        all_stories = [
            {"title": "Welcome to LUMINA — Your VFX & CG Industry Digest", "excerpt": "Stories update automatically every morning from FXGuide, befores & afters, CG Channel, and more.", "link": "#", "source": "LUMINA", "tag": "Industry", "date": now, "image_url": ""},
            {"title": "Lighting Artists: The Pipeline Shifts You Need to Know in 2026", "excerpt": "From USD adoption to cloud rendering, the role of the lighting TD is evolving faster than ever.", "link": "#", "source": "LUMINA", "tag": "Lighting", "date": now, "image_url": ""},
            {"title": "Nuke 16 — What Compositors Actually Think of the New Features", "excerpt": "We surveyed working comps at major studios about the real-world impact of Nuke's latest update.", "link": "#", "source": "LUMINA", "tag": "Compositing", "date": now, "image_url": ""},
        ]

    # Deduplicate
    seen, unique = set(), []
    for s in all_stories:
        key = s["title"].lower()[:60]
        if key not in seen:
            seen.add(key)
            unique.append(s)

    print(f"  Total unique stories: {len(unique)}")

    # Fetch ArtStation artwork
    print("  Fetching ArtStation artwork…")
    artwork = fetch_artstation_projects()

    hero    = unique[0]
    sidebar = unique[1:5]
    cards   = unique[5:8]
    wide    = unique[8:18]

    template_path = os.path.join(os.path.dirname(__file__), "index.html")
    with open(template_path, "r", encoding="utf-8") as f:
        html = f.read()

    html = html.replace("<!-- TICKER_ITEMS -->",   build_ticker(unique))
    html = html.replace("<!-- HERO_CONTENT -->",   build_hero(hero))
    html = html.replace("<!-- SIDEBAR_STORIES -->",build_sidebar(sidebar))
    html = html.replace("<!-- CARDS -->",          build_cards(cards))
    html = html.replace("<!-- WIDE_STORIES -->",   build_wide(wide))
    html = html.replace("<!-- BREAKDOWN_CARDS -->",build_breakdowns(BREAKDOWN_PICKS))
    html = html.replace("<!-- ARTWORK_CARDS -->",  build_artwork(artwork))

    with open(template_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"  Done — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")


if __name__ == "__main__":
    main()
