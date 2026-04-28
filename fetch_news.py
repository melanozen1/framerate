#!/usr/bin/env python3
"""
LUMINA News Fetcher
- Pulls VFX/CG/pipeline/compositing/lighting news from RSS feeds
- Extracts real thumbnail images from each story
- Fetches artwork from ArtStation's per-user public JSON (no auth needed)
- Rebuilds index.html daily
"""

import urllib.request
import xml.etree.ElementTree as ET
import json
import re
import os
from datetime import datetime, timezone
from html import unescape

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; LUMINA/1.0; personal VFX digest)"}

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

# ── CURATED ARTSTATION ARTISTS ─────────────────────────────────────────────
# ArtStation's trending/community API requires auth and is not public.
# Instead we use the per-user public endpoint:
#   artstation.com/users/{username}/projects.json
# which returns their recent portfolio projects with cover image URLs.
# These are stable, publicly accessible, and no API key is needed.

CURATED_ARTISTS = [
    {"username": "maciejkuciara", "name": "Maciej Kuciara",  "specialty": "Concept Art · Environment Lighting"},
    {"username": "ashthorp",      "name": "Ash Thorp",       "specialty": "Motion Design · CG Direction"},
    {"username": "yoannlaulan",   "name": "Yoann Laulan",    "specialty": "Character Lookdev · Grooming"},
    {"username": "benmauro",      "name": "Ben Mauro",       "specialty": "CG Design · Hard Surface"},
    {"username": "jama",          "name": "Jama Jurabaev",   "specialty": "Concept · 3D Illustration"},
    {"username": "felipeauge",    "name": "Felipe Auge",     "specialty": "Environment Art · Lighting"},
    {"username": "andreasrocha",  "name": "Andreas Rocha",   "specialty": "Matte Painting · Environment"},
    {"username": "sergeymusin",   "name": "Sergey Musin",    "specialty": "Houdini FX · Simulation"},
    {"username": "gilles",        "name": "Gilles Beloeil",  "specialty": "Environment Concept · Lighting"},
    {"username": "matheuscantos", "name": "Matheus Cantos",  "specialty": "VFX · Compositing"},
]

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


# ── IMAGE HELPERS ──────────────────────────────────────────────────────────

def is_valid_image_url(url: str) -> bool:
    if not url or not url.startswith("http"):
        return False
    low = url.lower()
    if any(x in low for x in ["1x1", "pixel", "tracking", "blank", "spacer", ".svg"]):
        return False
    return True


def extract_image_from_item(item, raw_text: str) -> str:
    # 1. media:content or media:thumbnail
    for ns_uri in ["http://search.yahoo.com/mrss/"]:
        for local in ["content", "thumbnail"]:
            el = item.find(f"{{{ns_uri}}}{local}")
            if el is not None:
                url = el.get("url", "")
                if is_valid_image_url(url):
                    return url

    # 2. enclosure
    enc = item.find("enclosure")
    if enc is not None:
        url = enc.get("url", "")
        if url and is_valid_image_url(url):
            return url

    # 3. <img> inside description / content:encoded
    for ns_uri in ["", "{http://purl.org/rss/1.0/modules/content/}"]:
        for tag in ["description", f"{ns_uri}encoded", "summary"]:
            el = item.find(tag)
            if el is not None and el.text:
                m = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', el.text, re.I)
                if m and is_valid_image_url(m.group(1)):
                    return m.group(1)

    return ""


# ── RSS FETCHER ────────────────────────────────────────────────────────────

def strip_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text)
    text = unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def truncate(text: str, n: int = 200) -> str:
    return text if len(text) <= n else text[:n].rsplit(" ", 1)[0] + "…"


def guess_tag(title: str, excerpt: str, default: str) -> str:
    combined = (title + " " + excerpt).lower()
    for tag, kws in TAG_KEYWORDS.items():
        if any(k in combined for k in kws):
            return tag
    return default


def parse_date(raw: str) -> str:
    for fmt in ["%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S GMT",
                "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ"]:
        try:
            return datetime.strptime(raw.strip(), fmt).strftime("%B %d, %Y")
        except Exception:
            continue
    return datetime.now(timezone.utc).strftime("%B %d, %Y")


def fetch_feed(feed: dict) -> list:
    stories = []
    try:
        req = urllib.request.Request(feed["url"], headers=HEADERS)
        with urllib.request.urlopen(req, timeout=12) as resp:
            raw = resp.read()
        raw_text = raw.decode("utf-8", errors="replace")

        for prefix, uri in [("media","http://search.yahoo.com/mrss/"),
                             ("content","http://purl.org/rss/1.0/modules/content/"),
                             ("atom","http://www.w3.org/2005/Atom")]:
            try: ET.register_namespace(prefix, uri)
            except Exception: pass

        root = ET.fromstring(raw)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        items = root.findall(".//item") or root.findall(".//atom:entry", ns)

        for item in items[:10]:
            def txt(tag):
                el = item.find(tag)
                return (el.text or "").strip() if el is not None else ""

            title = strip_html(txt("title"))
            link  = txt("link")
            if not link:
                el = item.find("link")
                if el is not None:
                    link = el.get("href", "")

            content_el = item.find("{http://purl.org/rss/1.0/modules/content/}encoded")
            raw_desc = txt("description") or txt("summary") or (content_el.text if content_el is not None else "")
            excerpt  = truncate(strip_html(raw_desc or ""), 200)
            pub_date = parse_date(txt("pubDate") or txt("published") or txt("updated"))
            tag      = guess_tag(title, excerpt, feed["default_tag"])
            image    = extract_image_from_item(item, raw_text)

            if title and link:
                stories.append({"title": title, "excerpt": excerpt, "link": link,
                                 "source": feed["name"], "tag": tag,
                                 "date": pub_date, "image_url": image})
    except Exception as e:
        print(f"  [warn] {feed['name']}: {e}")
    return stories


# ── ARTSTATION ─────────────────────────────────────────────────────────────

def fetch_artist_thumbnail(username: str) -> str:
    """
    artstation.com/users/{username}/projects.json is a publicly accessible
    endpoint that returns the artist's portfolio with cover image URLs.
    No API key or auth required.
    """
    url = f"https://www.artstation.com/users/{username}/projects.json?per_page=4&page=1"
    try:
        req = urllib.request.Request(url, headers={**HEADERS, "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        for project in data.get("data", []):
            cover = project.get("cover", {})
            for key in ["medium_image_url", "small_image_url", "thumb_url", "image_url"]:
                img = cover.get(key, "")
                if img and img.startswith("http"):
                    return img
    except Exception as e:
        print(f"      [warn] artstation/{username}: {e}")
    return ""


def fetch_artstation_projects() -> list:
    week_num = datetime.now(timezone.utc).isocalendar()[1]
    offset   = week_num % len(CURATED_ARTISTS)
    rotated  = CURATED_ARTISTS[offset:] + CURATED_ARTISTS[:offset]

    picks = []
    for artist in rotated[:8]:
        print(f"    artstation/{artist['username']}…")
        image_url = fetch_artist_thumbnail(artist["username"])
        picks.append({
            "artist":    artist["name"],
            "title":     artist["specialty"],
            "image_url": image_url,
            "link":      f"https://www.artstation.com/{artist['username']}",
            "platform":  "ArtStation",
        })

    got = sum(1 for p in picks if p["image_url"])
    print(f"  ArtStation done: {got}/8 images fetched")
    return picks


# ── HTML BUILDERS ──────────────────────────────────────────────────────────

def img_tag(url: str, idx: int = 0, cls: str = "") -> str:
    grad = GRADIENTS[idx % len(GRADIENTS)]
    if url:
        return (f'<img src="{url}" alt="" class="{cls}" loading="lazy" '
                f'onerror="this.parentElement.style.background=\'{grad}\';this.remove();">')
    return f'<div style="width:100%;height:100%;background:{grad};"></div>'


def build_ticker(stories: list) -> str:
    titles = [s["title"] for s in stories[:14]]
    return "".join(f"<span>{t}</span>" for t in titles * 2)


def build_hero(story: dict) -> str:
    bg = f'style="background-image:url(\'{story["image_url"]}\');background-size:cover;background-position:center;"' if story.get("image_url") else ""
    return f"""
      <div class="hero-img-wrap" {bg}></div>
      <span class="hero-tag">{story['tag']}</span>
      <h1 class="hero-title">{story['title']}</h1>
      <p class="hero-excerpt">{story['excerpt']}</p>
      <div class="hero-meta">
        <span>{story['source']}</span><span class="hero-meta-dot"></span>
        <span>{story['date']}</span><span class="hero-meta-dot"></span>
        <a class="hero-link" href="{story['link']}" target="_blank" rel="noopener">Read full story →</a>
      </div>"""


def build_sidebar(stories: list) -> str:
    html = ""
    for s in stories:
        thumb = (f'<img src="{s["image_url"]}" alt="" '
                 f'style="width:64px;height:46px;object-fit:cover;border-radius:3px;flex-shrink:0;" '
                 f'loading="lazy" onerror="this.remove();">')  if s.get("image_url") else ""
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
        visual = img_tag(s.get("image_url",""), i, "card-img-el")
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
        if s.get("image_url"):
            thumb = (f'<img src="{s["image_url"]}" alt="" '
                     f'style="width:88px;height:60px;object-fit:cover;border-radius:4px;flex-shrink:0;" '
                     f'loading="lazy" onerror="this.remove();">')
        else:
            thumb = f'<div style="width:88px;height:60px;border-radius:4px;flex-shrink:0;background:{GRADIENTS[i%len(GRADIENTS)]};"></div>'
        html += f"""
  <div class="wide-story" data-tag="{s['tag']}">
    <div style="display:flex;gap:12px;align-items:flex-start;">
      {thumb}
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
    html = ""
    for i, art in enumerate(picks[:8]):
        grad = GRADIENTS[i % len(GRADIENTS)]
        if art.get("image_url"):
            img_html = (f'<img src="{art["image_url"]}" alt="{art["title"]}" '
                        f'style="width:100%;height:100%;object-fit:cover;display:block;transition:transform 0.4s ease;" '
                        f'loading="lazy" onerror="this.parentElement.style.background=\'{grad}\';this.remove();">')
        else:
            img_html = f'<div style="width:100%;height:100%;background:{grad};"></div>'

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


# ── MAIN ──────────────────────────────────────────────────────────────────

def main():
    print("LUMINA — fetching VFX & CG industry news…")
    all_stories = []

    for feed in FEEDS:
        print(f"  Fetching {feed['name']}…")
        stories = fetch_feed(feed)
        print(f"    → {len(stories)} stories")
        all_stories.extend(stories)

    if not all_stories:
        now = datetime.now(timezone.utc).strftime("%B %d, %Y")
        all_stories = [
            {"title": "Welcome to LUMINA — Your VFX & CG Industry Digest",
             "excerpt": "Stories update automatically every morning from FXGuide, befores & afters, CG Channel, and more.",
             "link": "#", "source": "LUMINA", "tag": "Industry", "date": now, "image_url": ""},
            {"title": "Lighting Artists: The Pipeline Shifts You Need to Know in 2026",
             "excerpt": "From USD adoption to cloud rendering, the role of the lighting TD is evolving faster than ever.",
             "link": "#", "source": "LUMINA", "tag": "Lighting", "date": now, "image_url": ""},
            {"title": "Nuke — What Compositors Actually Think of the Latest Features",
             "excerpt": "We surveyed working comps at major studios about the real-world impact of Nuke's latest update.",
             "link": "#", "source": "LUMINA", "tag": "Compositing", "date": now, "image_url": ""},
        ]

    seen, unique = set(), []
    for s in all_stories:
        key = s["title"].lower()[:60]
        if key not in seen:
            seen.add(key); unique.append(s)

    print(f"  Total unique stories: {len(unique)}")
    print("  Fetching ArtStation artwork…")
    artwork = fetch_artstation_projects()

    template_path = os.path.join(os.path.dirname(__file__), "index.html")
    with open(template_path, "r", encoding="utf-8") as f:
        html = f.read()

    html = html.replace("<!-- TICKER_ITEMS -->",    build_ticker(unique))
    html = html.replace("<!-- HERO_CONTENT -->",    build_hero(unique[0]))
    html = html.replace("<!-- SIDEBAR_STORIES -->", build_sidebar(unique[1:5]))
    html = html.replace("<!-- CARDS -->",           build_cards(unique[5:8]))
    html = html.replace("<!-- WIDE_STORIES -->",    build_wide(unique[8:18]))
    html = html.replace("<!-- BREAKDOWN_CARDS -->", build_breakdowns(BREAKDOWN_PICKS))
    html = html.replace("<!-- ARTWORK_CARDS -->",   build_artwork(artwork))

    with open(template_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"  Done — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")


if __name__ == "__main__":
    main()
