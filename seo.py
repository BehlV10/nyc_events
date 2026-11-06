"""NYC Events — search, social, and answer-engine metadata.

Everything URL-shaped flows from get_site_url(), so moving to a custom domain is one step:
put the bare domain (e.g. "nycevents.example") in a CNAME file at the repo root. GitHub
Pages serves the domain from that file, and canonical tags, OpenGraph images, JSON-LD,
sitemap.xml, robots.txt, llms.txt, feeds, and IndexNow pings all switch over with it.

Outputs written by write_seo_files() during `python server.py export html`:
  <hub>/index.html   landing pages for high-intent searches (HUBS)
  sitemap.xml        every page, with lastmod
  robots.txt         allow-all incl. AI crawlers, pointing at the sitemap
  llms.txt           summary for AI answer engines (llmstxt.org)
"""

import json
import os
import re
from datetime import datetime, timedelta, timezone
from html import escape

from scrapers import EASTERN, category_bucket

ROOT = os.path.dirname(os.path.abspath(__file__))
SITE_NAME = "NYC Events"
GITHUB_PAGES_URL = "https://behlv10.github.io/nyc_events"
DEFAULT_TITLE = "NYC Events · Concerts, DJ Nights, Comedy, Theater, Run Clubs & Free Things to Do in New York"
DEFAULT_DESCRIPTION = (
    "Live calendar of {count} concerts, DJ nights, comedy, theater, run clubs, hikes, meetups, and free "
    "events across Manhattan, Brooklyn, Queens, the Bronx, and Staten Island. Updated twice a day."
)


def get_site_url():
    """Canonical base URL with no trailing slash: CNAME file > SITE_URL env > GitHub Pages."""
    try:
        with open(os.path.join(ROOT, "CNAME"), encoding="utf-8") as f:
            domain = f.read().strip()
        if domain:
            domain = re.sub(r"^https?://", "", domain).strip("/")
            return f"https://{domain}"
    except OSError:
        pass
    return (os.environ.get("SITE_URL") or GITHUB_PAGES_URL).rstrip("/")


def page_url(path="", site_url=None):
    base = (site_url or get_site_url()).rstrip("/")
    path = path.lstrip("/")
    return f"{base}/{path}" if path else f"{base}/"


def _rounded_count(n):
    """'10,000+' style counts so descriptions and OG cards don't churn every refresh."""
    if n >= 1000:
        return f"{(n // 1000) * 1000:,}+"
    if n >= 100:
        return f"{(n // 100) * 100:,}+"
    return str(n)


def default_description(total_events):
    return DEFAULT_DESCRIPTION.format(count=_rounded_count(total_events) if total_events else "thousands of")


def build_seo_meta_tags(title=None, description=None, path="", image_path="og-image.jpg", site_url=None):
    """<title>, description, canonical, OpenGraph and Twitter card tags."""
    site_url = site_url or get_site_url()
    canonical = page_url(path, site_url)
    img = page_url(image_path, site_url)
    t = escape(title or DEFAULT_TITLE)
    d = escape(description or default_description(0))
    return f"""<title>{t}</title>
<meta name="description" content="{d}">
<meta name="robots" content="index, follow, max-snippet:-1, max-image-preview:large, max-video-preview:-1">
<link rel="canonical" href="{escape(canonical)}">
<link rel="alternate" type="application/rss+xml" title="{SITE_NAME} — upcoming picks" href="{escape(page_url('feed.xml', site_url))}">
<meta property="og:locale" content="en_US">
<meta property="og:type" content="website">
<meta property="og:site_name" content="{SITE_NAME}">
<meta property="og:title" content="{t}">
<meta property="og:description" content="{d}">
<meta property="og:url" content="{escape(canonical)}">
<meta property="og:image" content="{escape(img)}">
<meta property="og:image:secure_url" content="{escape(img)}">
<meta property="og:image:type" content="image/jpeg">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:alt" content="{SITE_NAME} — live New York City event calendar">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{t}">
<meta name="twitter:description" content="{d}">
<meta name="twitter:image" content="{escape(img)}">
<link rel="icon" href="{escape(page_url('favicon.ico', site_url))}" sizes="48x48">
<link rel="icon" href="{escape(page_url('favicon.svg', site_url))}" type="image/svg+xml">
<link rel="apple-touch-icon" href="{escape(page_url('apple-touch-icon.png', site_url))}">
<link rel="manifest" href="{escape(page_url('site.webmanifest', site_url))}">"""


# --- schema.org ---

def _price_number(price):
    m = re.search(r"\$\s?(\d+(?:\.\d{1,2})?)", str(price or ""))
    return m.group(1) if m else None


def event_schema(e, site_url=None):
    """schema.org Event for one deduplicated event (needs _time from group_by_date)."""
    from template import CITY_LABELS, _event_city, _is_event_free
    from venues_geo import resolve_event_geo

    t = e.get("_time")
    name = (e.get("name") or "").strip()
    if not t or not name:
        return None
    site_url = site_url or get_site_url()
    venue = e.get("venue") or e.get("_source_venue") or "New York City"
    geo = resolve_event_geo(e)
    city = _event_city(venue, e.get("_source_venue"), geo=geo, event=e)
    locality = CITY_LABELS.get(city, "New York") if city not in ("other", "citywide") else "New York"
    address = {"@type": "PostalAddress", "addressLocality": locality, "addressRegion": "NY", "addressCountry": "US"}
    street = (geo or {}).get("address") or e.get("address")
    if street:
        address["streetAddress"] = street
    place = {"@type": "Place", "name": venue, "address": address}
    if geo:
        place["geo"] = {"@type": "GeoCoordinates", "latitude": geo["lat"], "longitude": geo["lng"]}
    url = e.get("url") or page_url("", site_url)
    item = {
        "@type": "Event",
        "name": name,
        "startDate": t.date().isoformat() if e.get("_time_unknown") else t.isoformat(),
        "eventStatus": "https://schema.org/EventScheduled",
        "eventAttendanceMode": "https://schema.org/OfflineEventAttendanceMode",
        "location": place,
        "image": [page_url("og-image.jpg", site_url)],
        "url": url,
        "description": (e.get("description") or f"{name} at {venue}, {locality}.")[:300],
        "organizer": {"@type": "Organization", "name": e.get("_presenter") or venue, "url": url},
    }
    offer = {"@type": "Offer", "url": url, "priceCurrency": "USD", "availability": "https://schema.org/InStock"}
    if _is_event_free(e):
        offer["price"] = "0"
    elif _price_number(e.get("price")):
        offer["price"] = _price_number(e.get("price"))
    if "price" in offer:
        item["offers"] = offer
    return item


def _upcoming(dated, days=None, start=None):
    now = datetime.now(EASTERN)
    start = start or now - timedelta(hours=2)
    end = now + timedelta(days=days) if days else None
    out = []
    for _day, events in dated:
        for e in events:
            t = e.get("_time")
            if t and t >= start and (end is None or t <= end):
                out.append(e)
    out.sort(key=lambda e: e["_time"])
    return out


def build_json_ld(dated, total_events, site_url=None, limit=60):
    """WebSite (+ sitelinks search box) and an ItemList of the next notable events."""
    from template import _get_event_highlight, _load_highlights

    site_url = site_url or get_site_url()
    website = {
        "@context": "https://schema.org",
        "@type": "WebSite",
        "name": SITE_NAME,
        "url": page_url("", site_url),
        "description": default_description(total_events),
        "inLanguage": "en-US",
        "potentialAction": {
            "@type": "SearchAction",
            "target": page_url("", site_url) + "#q={search_term_string}",
            "query-input": "required name=search_term_string",
        },
    }
    highlights = _load_highlights()
    upcoming = _upcoming(dated, days=7)
    picks = [e for e in upcoming if _get_event_highlight(e, highlights)]
    rest = [e for e in upcoming if e not in picks]
    items = []
    for e in picks + rest:
        sch = event_schema(e, site_url)
        if sch:
            items.append(sch)
        if len(items) >= limit:
            break
    item_list = {
        "@context": "https://schema.org",
        "@type": "ItemList",
        "name": "Upcoming events in New York City",
        "itemListElement": [{"@type": "ListItem", "position": i + 1, "item": it} for i, it in enumerate(items)],
    }
    blocks = [website, item_list]
    return "\n".join(
        f'<script type="application/ld+json">{json.dumps(b, ensure_ascii=False)}</script>' for b in blocks
    )


# --- Landing pages ("hubs") for high-intent searches ---

def _weekend_dates(today):
    wd = today.weekday()
    fri = today + timedelta(days=(4 - wd) % 7) if wd <= 4 else today - timedelta(days=wd - 4)
    return {fri, fri + timedelta(days=1), fri + timedelta(days=2)}


HUBS = {
    # High-intent time + intent pages
    "things-to-do-nyc-this-weekend": {
        "title": "Things to Do in NYC This Weekend", "time": "weekend",
        "subtitle": "Concerts, comedy, DJ nights, markets, run clubs, and free events across all five boroughs this weekend.",
        "badge": "THIS WEEKEND", "query": "#t=weekend",
    },
    "free-events-nyc-this-weekend": {
        "title": "Free Events in NYC This Weekend", "time": "weekend", "free": True,
        "subtitle": "Free concerts, park programs, gallery openings, guestlists, and community events this weekend.",
        "badge": "FREE THIS WEEKEND", "query": "#t=weekend&free=1",
    },
    "nyc-events-today": {
        "title": "NYC Events Today & Tonight", "time": "today",
        "subtitle": "What's happening in New York City today and tonight: shows, parties, comedy, and free things to do.",
        "badge": "TODAY IN NYC", "query": "",
    },
    "brooklyn-events-tonight": {
        "title": "Brooklyn Events Tonight", "time": "today", "city": "brooklyn",
        "subtitle": "Tonight in Brooklyn: live music, DJ sets, comedy, and parties from Williamsburg to Bushwick to Park Slope.",
        "badge": "BROOKLYN TONIGHT", "query": "#city=brooklyn",
    },
    "free-events-nyc": {
        "title": "Free Events & Things to Do in NYC", "free": True,
        "subtitle": "Free concerts, NYC Parks programs, museum nights, library talks, open mics, and club guestlists.",
        "badge": "FREE EVENTS", "query": "#free=1",
    },
    # Activity guides
    "live-music-nyc": {
        "title": "Live Music & Concerts in NYC", "bucket": "Music & nightlife", "cats": {"music"},
        "subtitle": "Concerts at Brooklyn Steel, Webster Hall, Terminal 5, jazz clubs, and indie rooms across the city.",
        "badge": "LIVE MUSIC", "query": "#cat=Music+%26+nightlife",
    },
    "dj-techno-nights-nyc": {
        "title": "DJ Nights, Techno & Dance Parties in NYC", "cats": {"clubbing"},
        "subtitle": "Techno, house, and dance parties at Nowadays, Elsewhere, Knockdown Center, Bossa Nova Civic Club, and more.",
        "badge": "DJ & NIGHTLIFE", "query": "#cat=Music+%26+nightlife",
    },
    "comedy-nyc": {
        "title": "Stand-Up Comedy Shows in NYC", "cats": {"comedy"},
        "subtitle": "Stand-up, improv, and open mics at the Comedy Cellar, The Stand, Caveat, The Bell House, and more.",
        "badge": "COMEDY", "query": "#cat=Arts+%26+culture",
    },
    "theater-nyc": {
        "title": "Broadway, Off-Broadway & Theater in NYC", "bucket": "Theater",
        "subtitle": "Broadway and off-Broadway performances, cabaret, drag, and dance across New York City.",
        "badge": "THEATER", "query": "#cat=Theater",
    },
    "run-clubs-nyc": {
        "title": "Run Clubs & Group Runs in NYC",
        "keywords": ("run club", "running club", "group run", "social run", "5k", "10k", "half marathon", "runners", "track club"),
        "subtitle": "Free social run clubs, track nights, and races in Central Park, Prospect Park, and along the waterfront.",
        "badge": "RUN CLUBS", "query": "#q=run",
    },
    "hiking-outdoors-nyc": {
        "title": "Hikes, Nature Walks & Outdoor Events in NYC", "cats": {"outdoors"},
        "keywords": ("hike", "hiking", "nature walk", "birding", "kayak", "urban park ranger", "trail"),
        "subtitle": "Urban Park Ranger hikes, birding walks, kayaking, and outdoor adventures across the five boroughs.",
        "badge": "OUTDOORS", "query": "#cat=Outdoors+%26+active",
    },
    "board-games-trivia-nyc": {
        "title": "Board Game Nights & Bar Trivia in NYC", "cats": {"gaming"},
        "keywords": ("trivia", "board game", "game night", "tabletop", "chess", "d&d"),
        "subtitle": "Weekly bar trivia, board game cafés, tabletop meetups, and arcade nights.",
        "badge": "GAMES & TRIVIA", "query": "#q=trivia",
    },
    # Borough directories
    "manhattan": {"title": "Manhattan Events Calendar", "city": "manhattan",
                  "subtitle": "Shows, parties, and things to do from the Village to Harlem.", "badge": "MANHATTAN", "query": "#city=manhattan"},
    "brooklyn": {"title": "Brooklyn Events Calendar", "city": "brooklyn",
                 "subtitle": "Williamsburg, Bushwick, Greenpoint, Park Slope, DUMBO, and beyond.", "badge": "BROOKLYN", "query": "#city=brooklyn"},
    "queens": {"title": "Queens Events Calendar", "city": "queens",
               "subtitle": "Astoria, Long Island City, Ridgewood, Jackson Heights, Flushing, and the Rockaways.", "badge": "QUEENS", "query": "#city=queens"},
    "bronx": {"title": "Bronx Events Calendar", "city": "bronx",
              "subtitle": "Concerts, parks, and culture across the Bronx.", "badge": "THE BRONX", "query": "#city=bronx"},
    "staten-island": {"title": "Staten Island Events Calendar", "city": "staten_island",
                      "subtitle": "Greenbelt hikes, Snug Harbor, and local events on Staten Island.", "badge": "STATEN ISLAND", "query": "#city=staten_island"},
}


def hub_events(hub, dated, limit=None):
    """Deduplicated upcoming events matching a hub's filters, in start order."""
    from template import _event_city, _is_event_free
    from venues_geo import resolve_event_geo

    today = datetime.now(EASTERN).date()
    time_rule = hub.get("time")
    keywords = tuple(k.lower() for k in hub.get("keywords") or ())
    out = []
    for e in _upcoming(dated):
        d = e["_time"].date()
        if time_rule == "today" and d != today:
            continue
        if time_rule == "weekend" and d not in _weekend_dates(today):
            continue
        cat = e.get("category") or "other"
        if cat in ("services", "family"):
            continue
        cat_ok = True
        if hub.get("cats") or hub.get("bucket"):
            cat_ok = cat in (hub.get("cats") or set()) or (hub.get("bucket") and category_bucket(cat) == hub["bucket"])
        kw_ok = bool(keywords) and any(k in (e.get("name") or "").lower() for k in keywords)
        if (hub.get("cats") or hub.get("bucket")) and keywords:
            if not (cat_ok or kw_ok):
                continue
        elif keywords and not kw_ok:
            continue
        elif not cat_ok:
            continue
        if hub.get("free") and not _is_event_free(e):
            continue
        if hub.get("city"):
            city = _event_city(e.get("venue"), e.get("_source_venue"), geo=resolve_event_geo(e), event=e)
            if city != hub["city"]:
                continue
        out.append(e)
        if limit and len(out) >= limit:
            break
    return out


_HUB_CSS = """
  :root { --bg:#0c0e14; --card:#151822; --card-hover:#1c202e; --fg:#eef1f8; --muted:#8e96a8; --accent:#5d9bff;
          --border:rgba(255,255,255,0.08); --green:#4ade80; --gold:#ffd866; }
  * { box-sizing: border-box; }
  body { margin:0; background:var(--bg); color:var(--fg); line-height:1.5;
         font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif; }
  header { background:var(--card); border-bottom:1px solid var(--border); padding:12px 16px; }
  .logo { font-weight:800; color:var(--fg); text-decoration:none; font-size:16px; }
  .logo span { color:var(--accent); }
  .hub-nav { display:flex; gap:6px 12px; flex-wrap:wrap; font-size:13px; margin-top:8px; }
  .hub-nav a { color:var(--muted); text-decoration:none; }
  .hub-nav a:hover, .hub-nav a.active { color:var(--accent); font-weight:600; }
  main { max-width:900px; margin:0 auto; padding:28px 16px 56px; }
  .hero { text-align:center; padding-bottom:22px; margin-bottom:22px; border-bottom:1px solid var(--border); }
  .hero h1 { font-size:clamp(24px,5vw,32px); margin:0 0 8px; }
  .hero p { color:var(--muted); margin:0 auto 16px; max-width:640px; }
  .count { color:var(--muted); font-size:13px; margin-bottom:14px; }
  .cta { display:inline-block; background:var(--accent); color:#0c0e14; padding:10px 20px; border-radius:999px;
         font-weight:700; font-size:14px; text-decoration:none; }
  h2.day { font-size:13px; text-transform:uppercase; letter-spacing:.08em; color:var(--accent); margin:26px 0 10px; }
  .grid { display:grid; grid-template-columns:minmax(0,1fr); gap:10px; }
  @media (min-width:640px) { .grid { grid-template-columns:repeat(2,minmax(0,1fr)); } }
  .card { background:var(--card); border:1px solid var(--border); border-radius:12px; padding:12px 14px; min-width:0; }
  .card:hover { background:var(--card-hover); }
  .card.pick { border-color:rgba(255,184,0,.45); }
  .meta { display:flex; justify-content:space-between; gap:8px; font-size:12px; color:var(--muted); }
  .badge { font-size:11px; padding:1px 8px; border-radius:999px; font-weight:600; white-space:nowrap; }
  .free { background:rgba(74,222,128,.16); color:var(--green); }
  .price { background:rgba(255,255,255,.08); }
  .pickb { background:rgba(255,184,0,.16); color:var(--gold); }
  .card h3 { font-size:15px; margin:6px 0 4px; line-height:1.35; overflow-wrap:anywhere; }
  .card h3 a { color:var(--fg); text-decoration:none; }
  .card h3 a:hover { color:var(--accent); text-decoration:underline; }
  .venue { font-size:12.5px; color:var(--muted); overflow-wrap:anywhere; }
  footer { border-top:1px solid var(--border); padding:22px 16px; text-align:center; font-size:12px; color:var(--muted); }
  footer a { color:var(--accent); text-decoration:none; }
"""


def _hub_nav(active_slug):
    links = ['<a href="../">All events</a>']
    for slug, hub in HUBS.items():
        cls = ' class="active"' if slug == active_slug else ""
        label = hub["title"].replace(" in NYC", "").replace(" Calendar", "")
        links.append(f'<a href="../{slug}/"{cls}>{escape(label)}</a>')
    return "\n    ".join(links)


def render_hub_page(slug, dated, site_url=None, max_events=120):
    from template import CITY_LABELS, _event_city, _get_event_highlight, _is_event_free, _load_highlights
    from venues_geo import resolve_event_geo

    hub = HUBS[slug]
    site_url = site_url or get_site_url()
    events = hub_events(hub, dated)
    shown = events[:max_events]
    highlights = _load_highlights()
    meta = build_seo_meta_tags(
        title=f"{hub['title']} · {SITE_NAME}",
        description=f"{hub['subtitle']} {len(events):,} upcoming listings, updated twice a day.",
        path=f"{slug}/",
        image_path=f"og-{slug}.jpg",
        site_url=site_url,
    )
    items = [s for s in (event_schema(e, site_url) for e in shown[:50]) if s]
    ld = {
        "@context": "https://schema.org", "@type": "ItemList", "name": hub["title"],
        "url": page_url(f"{slug}/", site_url),
        "itemListElement": [{"@type": "ListItem", "position": i + 1, "item": it} for i, it in enumerate(items)],
    }
    crumbs = {
        "@context": "https://schema.org", "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": SITE_NAME, "item": page_url("", site_url)},
            {"@type": "ListItem", "position": 2, "name": hub["title"], "item": page_url(f"{slug}/", site_url)},
        ],
    }

    sections = []
    cur_day = None
    cards = []
    for e in shown:
        d = e["_time"].date()
        if d != cur_day:
            if cards:
                sections.append(f'<div class="grid">{"".join(cards)}</div>')
                cards = []
            sections.append(f'<h2 class="day">{e["_time"].strftime("%A, %B")} {d.day}</h2>')
            cur_day = d
        geo = resolve_event_geo(e)
        city = _event_city(e.get("venue"), e.get("_source_venue"), geo=geo, event=e)
        where = e.get("venue") or e.get("_source_venue") or ""
        if city not in ("other", "citywide"):
            where = f"{where} · {CITY_LABELS.get(city, '')}"
        if _is_event_free(e):
            badge = '<span class="badge free">Free</span>'
        elif e.get("price"):
            badge = f'<span class="badge price">{escape(str(e["price"]))[:24]}</span>'
        else:
            badge = ""
        hl = _get_event_highlight(e, highlights)
        if hl:
            badge = f'<span class="badge pickb">{escape(hl.get("badge") or "Pick")}</span>' + badge
        when = e["_time"].strftime("%-I:%M %p") if (e["_time"].hour or e["_time"].minute) else "All day"
        cards.append(
            f'<article class="card{" pick" if hl else ""}"><div class="meta"><time datetime="{e["_time"].isoformat()}">{when}</time>'
            f'<span>{badge}</span></div><h3><a href="{escape(e.get("url") or "../")}" target="_blank" rel="noopener">'
            f'{escape(e.get("name") or "Event")}</a></h3><div class="venue">{escape(where)}</div></article>'
        )
    if cards:
        sections.append(f'<div class="grid">{"".join(cards)}</div>')
    body = "\n".join(sections) or "<p>No upcoming listings match right now — the full calendar has everything.</p>"
    more = f"Showing {len(shown):,} of {len(events):,} upcoming listings." if len(events) > len(shown) else f"{len(events):,} upcoming listings."

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
{meta}
<script type="application/ld+json">{json.dumps(ld, ensure_ascii=False)}</script>
<script type="application/ld+json">{json.dumps(crumbs, ensure_ascii=False)}</script>
<style>{_HUB_CSS}</style>
</head>
<body>
<header>
  <a href="../" class="logo"><span>NYC</span> Events</a>
  <nav class="hub-nav">
    {_hub_nav(slug)}
  </nav>
</header>
<main>
  <div class="hero">
    <h1>{escape(hub['title'])}</h1>
    <p>{escape(hub['subtitle'])}</p>
    <a class="cta" href="../{hub['query']}">Open the interactive calendar &amp; map →</a>
  </div>
  <div class="count">{more} Updated {datetime.now(EASTERN).strftime('%b %-d, %-I:%M %p')} ET.</div>
  {body}
</main>
<footer><a href="../">{SITE_NAME}</a> · independent, ad-free calendar of New York City events ·
  <a href="../feed.xml">RSS</a> · <a href="../events.ics">Subscribe (iCal)</a></footer>
</body>
</html>"""


def build_seo_directory_html():
    """Crawlable footer links to every landing page (internal linking for search engines)."""
    links = " · ".join(f'<a href="{slug}/">{escape(h["title"])}</a>' for slug, h in HUBS.items())
    return f"""<nav class="seo-directory" aria-label="NYC event guides">
  <h2>NYC event guides</h2>
  <p>{links}</p>
  <p class="seo-feeds"><a href="feed.xml">RSS feed</a> · <a href="events.ics">Subscribe in your calendar (iCal)</a> · <a href="events.json">JSON data</a></p>
</nav>"""


# --- Crawler files ---

def build_sitemap(site_url=None, lastmod=None):
    site_url = site_url or get_site_url()
    lastmod = lastmod or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")
    urls = [("", "hourly", "1.0")] + [(f"{s}/", "hourly", "0.9" if HUBS[s].get("time") else "0.8") for s in HUBS]
    rows = "\n".join(
        f"  <url><loc>{escape(page_url(p, site_url))}</loc><lastmod>{lastmod}</lastmod>"
        f"<changefreq>{cf}</changefreq><priority>{pr}</priority></url>"
        for p, cf, pr in urls
    )
    return f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n{rows}\n</urlset>\n'


AI_CRAWLERS = ("GPTBot", "ChatGPT-User", "OAI-SearchBot", "ClaudeBot", "Claude-User", "PerplexityBot",
               "Applebot", "Applebot-Extended", "Google-Extended", "Bingbot", "Googlebot")


def build_robots(site_url=None):
    """Note: crawlers only read robots.txt at a host's root, so this takes effect once the site
    is on its own domain (on github.io the sitemap is submitted via Search Console instead)."""
    site_url = site_url or get_site_url()
    agents = "\n\n".join(f"User-agent: {a}\nAllow: /" for a in AI_CRAWLERS)
    return f"User-agent: *\nAllow: /\n\n{agents}\n\nSitemap: {page_url('sitemap.xml', site_url)}\n"


def build_llms_txt(total_events, n_sources, site_url=None):
    site_url = site_url or get_site_url()
    hubs = "\n".join(f"- [{h['title']}]({page_url(s + '/', site_url)}): {h['subtitle']}" for s, h in HUBS.items())
    return f"""# {SITE_NAME}

> Independent, ad-free live calendar of {_rounded_count(total_events)} upcoming New York City events — concerts, DJ nights, comedy, theater, run clubs, hikes, meetups, and free events across all five boroughs — aggregated from {n_sources}+ venue calendars and community feeds and refreshed twice a day. Listings link to the venue's or organizer's own page.

## Data
- [Interactive calendar]({page_url('', site_url)}): filter by borough, neighborhood, category, price, and time; map and "near me" views.
- [events.json]({page_url('events.json', site_url)}): machine-readable export of every listing with venue, time, price, and coordinates.
- [RSS feed]({page_url('feed.xml', site_url)}): upcoming editor's picks and notable events.
- [iCalendar feed]({page_url('events.ics', site_url)}): subscribe in Apple, Google, or Outlook calendar.

## Guides
{hubs}
"""


def write_seo_files(base_dir, dated, total_events, n_sources, site_url=None):
    """Write hub pages, sitemap.xml, robots.txt, and llms.txt into base_dir."""
    site_url = site_url or get_site_url()
    written = []
    for slug in HUBS:
        os.makedirs(os.path.join(base_dir, slug), exist_ok=True)
        path = os.path.join(base_dir, slug, "index.html")
        with open(path, "w", encoding="utf-8") as f:
            f.write(render_hub_page(slug, dated, site_url))
        written.append(path)
    for name, content in (
        ("sitemap.xml", build_sitemap(site_url)),
        ("robots.txt", build_robots(site_url)),
        ("llms.txt", build_llms_txt(total_events, n_sources, site_url)),
    ):
        path = os.path.join(base_dir, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        written.append(path)
    return written
