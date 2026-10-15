"""NYC Events — venue scrapers and data definitions."""

import html
import json
import os
import re
import ssl
import threading
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from urllib.parse import quote, urljoin
from zoneinfo import ZoneInfo
import warnings

import requests
from requests.adapters import HTTPAdapter
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

CACHE_SECONDS = 15 * 60
EASTERN = ZoneInfo("America/New_York")

UA_SAFARI = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
)
UA_CHROME = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
UA_CURL = "curl/8.4.0"

_HS_CERTIFI = "/opt/homebrew/var/hs-certifi/cacert.pem"


def _make_session():
    ca = _HS_CERTIFI if os.path.exists(_HS_CERTIFI) else True
    ctx = ssl.create_default_context(cafile=ca if isinstance(ca, str) else None)
    if hasattr(ssl, "VERIFY_X509_STRICT"):
        ctx.verify_flags &= ~ssl.VERIFY_X509_STRICT

    class _Adapter(HTTPAdapter):
        def init_poolmanager(self, *args, **kwargs):
            kwargs["ssl_context"] = ctx
            super().init_poolmanager(*args, **kwargs)

    s = requests.Session()
    s.mount("https://", _Adapter())
    return s


_SESSION = _make_session()


def fetch_soup(url, ua=UA_CHROME, timeout=15):
    resp = _SESSION.get(
        url,
        headers={
            "User-Agent": ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        },
        timeout=timeout,
    )
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def _format_price_range(lo, hi, curr="USD"):
    sym = "$" if curr in ("USD", "$", None) else f"{curr} "
    def _fmt(val):
        if val is None:
            return None
        return f"{val:.2f}".rstrip("0").rstrip(".")
    lo_s = _fmt(lo)
    hi_s = _fmt(hi)
    if lo_s is None and hi_s is None:
        return None
    if lo_s is None:
        return f"{sym}{hi_s}"
    if hi_s is None or lo_s == hi_s:
        return f"{sym}{lo_s}"
    return f"{sym}{lo_s}–{hi_s}"


CATEGORY_KEYWORDS = [
    ("music",     [r"\b(concert|band|orchestra|jazz|symphony|quartet|choir|acoustic|live music|dj set|indie rock|punk|metal|folk|hip-hop|r&b|brass band|honky-tonk|bar concert|live band)\b"]),
    ("comedy",    [r"\b(comedy|stand-?up|improv|open mic comedy|comic|roast|laugh)\b"]),
    ("clubbing",  [r"\b(dj|rave|techno|house music|edm|club night|dance party|nightclub|party|afters|guestlist|free guestlist|rooftop party|clubbing|nightlife)\b"]),
    ("dance",     [r"\b(salsa|bachata|tango|swing dance|swing dancing|lindy hop|lindy|contra dance|ballroom|dance class|social dance|milonga|cumbia)\b"]),
    ("theater",   [r"\b(theater|theatre|musical|play|broadway|off-broadway|stage|cabaret|drama|drag|drag show|drag queen|drag brunch|burlesque)\b"]),
    ("film",      [r"\b(screening|film|movie|cinema|documentary|35mm|q&a screening)\b"]),
    ("art",       [r"\b(exhibit|gallery|museum|reception|sculpture|painting|open studios?|installation)\b"]),
    ("books",     [r"\b(book launch|author talk|poetry|reading|bookstore|book signing|literary)\b"]),
    ("food",      [r"\b(tasting|wine dinner|beer release|food tour|brewery|pop-up dinner|pairing|culinary)\b"]),
    ("outdoors",  [r"\b(hike|walking tour|nature walk|birding|trail|kayak|park tour|outdoor)\b"]),
    ("sports",    [r"\b(yankees|mets|knicks|nets|rangers|islanders|soccer|5k|10k|marathon|hockey|basketball)\b"]),
    ("gaming",    [r"\b(board games?|trivia|arcade|esports|chess|magic the gathering|d&d|tabletop|video game|smash bros|gaming tournament|smash ultimate|melee|lan)\b"]),
    ("community", [r"\b(talk|lecture|panel|discussion|networking|farmers market|flea market|artisan market|expo|festival|parade)\b"]),
]

CATEGORY_BUCKETS = [
    ("Music & nightlife", ["music", "clubbing", "dance"]),
    ("Arts & culture",    ["theater", "film", "art", "books", "comedy"]),
    ("Outdoors & active", ["outdoors", "sports"]),
    ("Social & community",["community", "food", "gaming", "other"]),
]

CATEGORY_STYLES = {
    "music":     ("#7aa2f7", "♪"),
    "comedy":    ("#bb9af7", "ツ"),
    "clubbing":  ("#f7768e", "⚡"),
    "dance":     ("#ff7ab2", "💃"),
    "theater":   ("#e0af68", "🎭"),
    "film":      ("#7dcfff", "🎬"),
    "art":       ("#ffd866", "✦"),
    "books":     ("#9ece6a", "📖"),
    "food":      ("#ff9e64", "🍴"),
    "outdoors":  ("#73daca", "🌿"),
    "sports":    ("#2ac3de", "⚽"),
    "gaming":    ("#b4f9f8", "🎲"),
    "community": ("#c0caf5", "👥"),
    "other":     ("#6b7280", "·"),
}


def category_bucket(cat):
    for bucket_name, members in CATEGORY_BUCKETS:
        if cat in members:
            return bucket_name
    return "Social & community"


def guess_category(text, default="community"):
    if not text:
        return default
    t = text.lower()
    for cat, patterns in CATEGORY_KEYWORDS:
        for p in patterns:
            if re.search(p, t):
                return cat
    return default


# --- NYC Weather ---
_weather_cache = {"ts": 0, "data": None}
_WMO_ICON = {
    0: ("☀️", "Clear"),
    1: ("🌤️", "Mainly clear"), 2: ("⛅", "Partly cloudy"), 3: ("☁️", "Overcast"),
    45: ("🌫️", "Fog"), 48: ("🌫️", "Depositing rime fog"),
    51: ("🌦️", "Light drizzle"), 53: ("🌦️", "Drizzle"), 55: ("🌧️", "Dense drizzle"),
    61: ("🌧️", "Slight rain"), 63: ("🌧️", "Rain"), 65: ("🌧️", "Heavy rain"),
    71: ("🌨️", "Slight snow"), 73: ("🌨️", "Snow"), 75: ("🌨️", "Heavy snow"),
    77: ("🌨️", "Snow grains"),
    80: ("🌦️", "Slight showers"), 81: ("🌧️", "Showers"), 82: ("🌧️", "Violent showers"),
    85: ("🌨️", "Snow showers"), 86: ("🌨️", "Heavy snow showers"),
    95: ("⛈️", "Thunderstorm"), 96: ("⛈️", "Thunderstorm with hail"), 99: ("⛈️", "Heavy thunderstorm"),
}


def fetch_nyc_weather():
    """Current NYC (Central Park) temp + condition."""
    if _weather_cache["data"] is not None and time.time() - _weather_cache["ts"] < 30 * 60:
        return _weather_cache["data"]
    out = None
    try:
        r = _SESSION.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": 40.78, "longitude": -73.96,
                "current": "temperature_2m,weather_code",
                "temperature_unit": "fahrenheit",
                "timezone": "America/New_York",
            },
            timeout=8,
        )
        r.raise_for_status()
        cur = r.json().get("current") or {}
        temp = cur.get("temperature_2m")
        code = cur.get("weather_code")
        icon, label = _WMO_ICON.get(code, ("🌡️", "—"))
        if temp is not None:
            out = {"temp": round(temp), "icon": icon, "label": label}
    except Exception:
        out = None
    _weather_cache["data"] = out
    _weather_cache["ts"] = time.time()
    return out


# --- NYC Broadway Lotteries ---
_luckyseat_cache = {"ts": 0, "data": None}


def fetch_luckyseat_nyc():
    """Fetch LuckySeat Broadway lotteries for NYC."""
    if _luckyseat_cache["data"] is not None and time.time() - _luckyseat_cache["ts"] < CACHE_SECONDS:
        return _luckyseat_cache["data"]
    shows = []
    try:
        resp = _SESSION.get(
            "https://www.luckyseat.com/api/showmanagement/getshowlist",
            headers={"User-Agent": UA_SAFARI, "Accept": "application/json"},
            timeout=10,
        )
        resp.raise_for_status()
        for s in resp.json():
            city = (s.get("city") or "").lower()
            if "new york" not in city and "broadway" not in city and "ny" not in city:
                continue
            if not s.get("isActive") or s.get("isTempClosed"):
                continue
            shows.append({
                "name": s.get("showName"),
                "venue": s.get("eventLocation"),
                "price": s.get("priceAndFeesTotal"),
                "url": f"https://www.luckyseat.com/shows/{s.get('showAlias')}" if s.get("showAlias") else "https://www.luckyseat.com/",
            })
    except Exception:
        shows = []
    _luckyseat_cache["data"] = shows
    _luckyseat_cache["ts"] = time.time()
    return shows


# --- Scrapers ---

def scrape_donyc(url, ua):
    """DoNYC venue & category scraper — parses Schema.org microdata."""
    soup = fetch_soup(url, ua)
    events = []
    now = datetime.now(timezone.utc)
    seen = set()
    for card in soup.select('[itemprop="event"]'):
        name_el = card.find(itemprop="name")
        date_el = card.find(itemprop="startDate")
        loc_el = card.find(itemprop="location")
        if not name_el or not date_el:
            continue
        name = name_el.get_text(strip=True)
        iso = date_el.get("content", "")
        iso = re.sub(r"([+-]\d{2})(\d{2})$", r"\1:\2", iso)
        try:
            dt = datetime.fromisoformat(iso).astimezone(timezone.utc)
        except (ValueError, AttributeError):
            continue
        if dt < now:
            continue
        venue_name = None
        if loc_el:
            vn = loc_el.find(itemprop="name")
            venue_name = vn.get_text(strip=True) if vn else None
        permalink = card.get("data-permalink", "")
        event_url = f"https://donyc.com{permalink}" if permalink else url
        key = (name.lower(), dt.date().isoformat())
        if key in seen:
            continue
        seen.add(key)
        events.append({
            "name": name,
            "date": dt.isoformat(),
            "url": event_url,
            "venue": venue_name,
            "price": None,
        })
    return events


def scrape_donyc_calendar(url, ua):
    """DoNYC multi-day event calendar — fetches next 10 days of citywide listings."""
    events = []
    now = datetime.now(EASTERN)
    seen = set()
    for i in range(10):
        d = now.date() + timedelta(days=i)
        day_url = f"https://donyc.com/events/{d.year}/{d.month:02d}/{d.day:02d}"
        try:
            day_events = scrape_donyc(day_url, ua)
            for e in day_events:
                key = (e["name"].lower(), (e.get("date") or "")[:10])
                if key not in seen:
                    seen.add(key)
                    events.append(e)
        except Exception:
            continue
    return events


def scrape_the_skint(url, ua):
    """The Skint — NYC's legendary daily free and cheap cultural events blog."""
    resp = _SESSION.get("https://theskint.com/feed/", headers={"User-Agent": ua}, timeout=12)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    events = []
    now = datetime.now(EASTERN)
    for item in soup.find_all("item")[:15]:
        title_el = item.find("title")
        title = title_el.get_text(strip=True) if title_el else ""
        link_el = item.find("link")
        link = link_el.get_text(strip=True) if link_el else url
        pub_el = item.find("pubdate") or item.find("pubDate")
        pub_str = pub_el.get_text(strip=True) if pub_el else ""
        
        # Parse publication date or match date in title
        try:
            pub_dt = datetime.strptime(pub_str[:16], "%a, %d %b %Y").replace(tzinfo=EASTERN)
        except Exception:
            pub_dt = now

        events.append({
            "name": title,
            "date": pub_dt.astimezone(timezone.utc).isoformat(),
            "url": link,
            "venue": "The Skint NYC",
            "price": "Free / Cheap",
            "category": "community",
        })
    return events


def scrape_ticketmaster_nyc(_url, _ua):
    """Ticketmaster Discovery API for NYC venues (MSG, Barclays, Webster Hall, Bowery, etc.)."""
    key = os.environ.get("TICKETMASTER_API_KEY") or "oo1qd0wzLe7WJpm61ALQuUCTMXGK7U5z"
    resp = _SESSION.get(
        "https://app.ticketmaster.com/discovery/v2/events.json",
        params={
            "apikey": key,
            "latlong": "40.7128,-74.0060",
            "radius": 20,
            "unit": "miles",
            "size": 100,
            "sort": "date,asc",
            "startDateTime": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
        timeout=15,
    )
    resp.raise_for_status()
    events = []
    for ev in resp.json().get("_embedded", {}).get("events", []):
        start = ev.get("dates", {}).get("start", {})
        iso = start.get("dateTime")
        if not iso and start.get("localDate"):
            try:
                iso = datetime.fromisoformat(f"{start['localDate']}T19:00:00").replace(
                    tzinfo=EASTERN,
                ).astimezone(timezone.utc).isoformat()
            except ValueError:
                iso = None
        venues = ev.get("_embedded", {}).get("venues") or []
        venue = venues[0]["name"] if venues and venues[0].get("name") else "NYC Venue"
        price = None
        prs = ev.get("priceRanges") or []
        if prs:
            price = _format_price_range(prs[0].get("min"), prs[0].get("max"), prs[0].get("currency", "USD"))
        events.append({
            "name": ev.get("name"),
            "date": iso,
            "url": ev.get("url"),
            "venue": venue,
            "price": price,
            "category": guess_category(ev.get("name"), "music"),
        })
    return events


def scrape_tablelist(url, ua):
    """Tablelist Next.js ticketing embed for nightclubs."""
    resp = _SESSION.get(url, headers={"User-Agent": ua}, timeout=12)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    tag = soup.find("script", id="__NEXT_DATA__")
    if not tag or not tag.string:
        return []
    try:
        data = json.loads(tag.string)
    except Exception:
        return []
    props = data.get("props", {}).get("pageProps", {})
    venue_info = props.get("venue", {})
    default_venue = venue_info.get("name") or "Nightclub"
    raw_events = props.get("events", {}).get("data", [])
    events = []
    for item in raw_events:
        name = item.get("name")
        start = item.get("dateStart")
        if not name or not start:
            continue
        try:
            dt = datetime.fromisoformat(start.replace("Z", "+00:00")).astimezone(timezone.utc)
            iso = dt.isoformat()
        except Exception:
            iso = None
        vname = item.get("venueName") or default_venue
        events.append({
            "name": name,
            "date": iso,
            "url": item.get("externalSellingLink") or url,
            "venue": vname,
            "price": None,
            "category": "clubbing",
        })
    return events


def scrape_eventbrite_jsonld(url, ua):
    """Scrape Eventbrite search and organizer pages using Schema.org ItemList JSON-LD."""
    events = []
    seen = set()
    now = datetime.now(timezone.utc)
    try:
        resp = _SESSION.get(url, headers={"User-Agent": ua}, timeout=12)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        for s in soup.find_all("script", type="application/ld+json"):
            if not s.string:
                continue
            try:
                data = json.loads(s.string)
                if not isinstance(data, dict) or data.get("@type") != "ItemList":
                    continue
                for el in data.get("itemListElement", []):
                    item = el.get("item", {})
                    name = item.get("name")
                    start = item.get("startDate")
                    event_url = item.get("url") or url
                    if not name or not start:
                        continue
                    try:
                        if "T" in start:
                            dt = datetime.fromisoformat(start.replace("Z", "+00:00")).astimezone(timezone.utc)
                        else:
                            dt = datetime.fromisoformat(f"{start}T19:00:00").replace(tzinfo=EASTERN).astimezone(timezone.utc)
                    except Exception:
                        continue
                    if dt < now:
                        continue
                    key = (name.lower(), dt.date().isoformat())
                    if key in seen:
                        continue
                    seen.add(key)

                    offers = item.get("offers")
                    price = None
                    if isinstance(offers, dict):
                        p = offers.get("price") or offers.get("lowPrice")
                        if p is not None:
                            price = "Free" if str(p) in ("0", "0.0", "0.00") else f"${p}"
                    elif isinstance(offers, list) and offers:
                        p = offers[0].get("price") or offers[0].get("lowPrice")
                        if p is not None:
                            price = "Free" if str(p) in ("0", "0.0", "0.00") else f"${p}"

                    loc = item.get("location", {})
                    vname = loc.get("name") if isinstance(loc, dict) else None
                    events.append({
                        "name": name,
                        "date": dt.isoformat(),
                        "url": event_url,
                        "venue": vname,
                        "price": price,
                    })
            except Exception:
                continue
    except Exception:
        pass
    return events


def scrape_eventbrite_organizer(url, ua):
    """Scrape official Eventbrite organizer API for complete venue event schedules."""
    m = re.search(r"(\d{8,14})", url)
    if not m:
        return []
    org_id = m.group(1)
    events = []
    seen = set()
    now = datetime.now(timezone.utc)
    api_url = f"https://www.eventbrite.com/api/v3/organizers/{org_id}/events/?order_by=start_asc"
    try:
        resp = _SESSION.get(api_url, headers={"User-Agent": ua}, timeout=12)
        resp.raise_for_status()
        data = resp.json()
        for ev in data.get("events", []):
            name = (ev.get("name") or {}).get("text")
            start = (ev.get("start") or {}).get("utc")
            event_url = ev.get("url")
            if not name or not start:
                continue
            try:
                dt = datetime.fromisoformat(start.replace("Z", "+00:00")).astimezone(timezone.utc)
            except Exception:
                continue
            if dt < now:
                continue
            key = (name.lower(), dt.date().isoformat())
            if key in seen:
                continue
            seen.add(key)
            is_free = ev.get("is_free", False)
            price = "Free" if is_free else None
            desc = (ev.get("summary") or "").strip()
            vname = None
            if isinstance(ev.get("venue"), dict):
                vname = ev.get("venue", {}).get("name")
            if not vname:
                m_at = re.search(r"\bat\s+([A-Z0-9][^|(,\n]+)", name)
                if m_at:
                    vname = m_at.group(1).strip()
            events.append({
                "name": name,
                "date": dt.isoformat(),
                "url": event_url or f"https://www.eventbrite.com/o/{org_id}",
                "venue": vname,
                "price": price,
                "description": desc,
            })
    except Exception:
        pass
    return events


def scrape_petes_candy_store(url, ua):
    """Pete's Candy Store — iconic Williamsburg backroom music, open mics, & comedy."""
    events = []
    now = datetime.now(timezone.utc)
    try:
        resp = _SESSION.get(url, headers={"User-Agent": ua}, timeout=12)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        wrappers = soup.find_all("div", class_=lambda c: c and ("wrapper" in (c or "").lower() or "event" in (c or "").lower()))
        for w in wrappers:
            date_text = ""
            for tag in w.find_all(["h2", "h3", "h4", "div", "span"]):
                txt = tag.get_text(strip=True)
                m = re.search(r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2})(?:st|nd|rd|th)?", txt, re.IGNORECASE)
                if m:
                    date_text = m.group(0)
                    break
            content = w.find("div", class_=lambda c: c and "styledContentContainer" in c)
            if not content:
                continue
            title_el = content.find(class_=lambda c: c and "styledTitle" in c)
            title = title_el.get_text(strip=True) if title_el else ""
            if not title:
                continue
            time_el = content.find(class_=lambda c: c and ("styledTime" in c or "time" in (c or "").lower()))
            time_str = time_el.get_text(strip=True) if time_el else "8:00pm"
            if not date_text:
                cur = w.previous_sibling
                while cur and not date_text:
                    if hasattr(cur, "get_text"):
                        m = re.search(r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2})(?:st|nd|rd|th)?", cur.get_text(), re.IGNORECASE)
                        if m:
                            date_text = m.group(0)
                    cur = cur.previous_sibling
            if not date_text:
                continue
            cleaned_date = re.sub(r"(st|nd|rd|th)", "", date_text, flags=re.IGNORECASE)
            now_dt = datetime.now(EASTERN)
            year = now_dt.year
            dt_str = f"{cleaned_date} {year} {time_str}"
            try:
                dt = datetime.strptime(dt_str, "%B %d %Y %I:%M%p").replace(tzinfo=EASTERN).astimezone(timezone.utc)
                if dt < now:
                    continue
            except Exception:
                continue
            events.append({
                "name": title,
                "date": dt.isoformat(),
                "url": "https://www.petescandystore.com/calendar/",
                "venue": "Pete's Candy Store",
                "price": "Free / 1-drink min",
                "category": "music",
            })
    except Exception:
        pass
    return events


def scrape_squarespace_calendar(url, ua):
    """Squarespace native JSON calendar API scraper."""
    events = []
    now = datetime.now(timezone.utc)
    try:
        json_url = url if "format=json" in url else (url + ("&" if "?" in url else "?") + "format=json")
        resp = _SESSION.get(json_url, headers={"User-Agent": ua}, timeout=12)
        resp.raise_for_status()
        data = resp.json()
        for item in data.get("upcoming", []) or data.get("items", []):
            title = item.get("title")
            start_ms = item.get("startDate")
            if not title or not start_ms:
                continue
            try:
                dt = datetime.fromtimestamp(start_ms / 1000.0, tz=timezone.utc)
                if dt < now:
                    continue
                iso = dt.isoformat()
            except Exception:
                continue
            full_url = item.get("fullUrl")
            if full_url and not full_url.startswith("http"):
                domain = "/".join(url.split("/")[:3])
                full_url = f"{domain}{full_url}"
            events.append({
                "name": title,
                "date": iso,
                "url": full_url or url,
                "venue": None,
                "price": "Free / No Cover",
                "category": "music",
            })
    except Exception:
        pass
    return events


_WEEKDAYS = {
    "monday": 0, "mondays": 0,
    "tuesday": 1, "tuesdays": 1,
    "wednesday": 2, "wednesdays": 2,
    "thursday": 3, "thursdays": 3,
    "friday": 4, "fridays": 4,
    "saturday": 5, "saturdays": 5,
    "sunday": 6, "sundays": 6,
}


def scrape_nyc_trivia_league(_url, ua):
    """NYC Trivia League — 70+ neighborhood pubs & breweries across 5 boroughs."""
    events = []
    try:
        resp = _SESSION.post(
            "https://nyctrivialeague.com/jm-ajax/get_listings/",
            data={"per_page": 100, "page": 1},
            headers={"User-Agent": ua},
            timeout=12,
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.json().get("html", ""), "html.parser")
        today = datetime.now(EASTERN).date()
        weeks = 4
        for a in soup.select("article"):
            title_el = a.select_one(".card__title")
            tagline_el = a.select_one(".card__tagline")
            link_el = a.select_one("a[href]")
            if not title_el or not tagline_el:
                continue
            bar_name = title_el.get_text(strip=True)
            tagline = tagline_el.get_text(strip=True)
            event_url = link_el.get("href") if link_el else "https://nyctrivialeague.com/"
            m_day = re.search(r"\b(mondays?|tuesdays?|wednesdays?|thursdays?|fridays?|saturdays?|sundays?)\b", tagline, re.IGNORECASE)
            m_time = re.search(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)", tagline, re.IGNORECASE)
            if not m_day:
                continue
            weekday = _WEEKDAYS.get(m_day.group(1).lower())
            if weekday is None:
                continue
            hour = 19
            minute = 0
            if m_time:
                hour = int(m_time.group(1))
                minute = int(m_time.group(2) or 0)
                ampm = m_time.group(3).lower()
                if ampm == "pm" and hour != 12:
                    hour += 12
                elif ampm == "am" and hour == 12:
                    hour = 0
            ahead = (weekday - today.weekday()) % 7
            first_day = today + timedelta(days=ahead)
            is_bingo = "bingo" in tagline.lower()
            title_prefix = "Mixtape Bingo" if is_bingo else "NYC Trivia Night"
            full_title = f"{title_prefix} @ {bar_name}"
            for w in range(weeks):
                d = first_day + timedelta(weeks=w)
                dt = datetime(d.year, d.month, d.day, hour, minute, tzinfo=EASTERN)
                events.append({
                    "name": full_title,
                    "date": dt.astimezone(timezone.utc).isoformat(),
                    "url": event_url,
                    "venue": bar_name,
                    "price": "Free / No Cover",
                    "category": "gaming",
                })
    except Exception:
        pass
    return events


def scrape_nyc_parks(url, ua):
    """NYC Parks Department official XML feed — 800+ free public events across all 5 boroughs."""
    events = []
    seen = set()
    now = datetime.now(timezone.utc)
    ns = {"event": "http://www.nycgovparks.org/eventsrss_ns/"}
    try:
        resp = _SESSION.get(url, headers={"User-Agent": ua}, timeout=15)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
        for item in root.findall(".//item"):
            title_el = item.find("title")
            raw_title = title_el.text.strip() if title_el is not None and title_el.text else ""
            if not raw_title:
                continue
            title = html.unescape(raw_title)

            link_el = item.find("link")
            link = link_el.text.strip() if link_el is not None and link_el.text else "https://www.nycgovparks.org/events"

            startdate_el = item.find("event:startdate", ns)
            starttime_el = item.find("event:starttime", ns)
            park_el = item.find("event:parknames", ns)
            loc_el = item.find("event:location", ns)
            cat_el = item.find("event:categories", ns)

            startdate = startdate_el.text.strip() if startdate_el is not None and startdate_el.text else ""
            starttime = starttime_el.text.strip() if starttime_el is not None and starttime_el.text else "10:00 am"
            park = park_el.text.strip() if park_el is not None and park_el.text else "NYC Park"
            loc = loc_el.text.strip() if loc_el is not None and loc_el.text else park
            cats_raw = cat_el.text.strip() if cat_el is not None and cat_el.text else ""

            if not startdate:
                continue

            m_time = re.search(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)", starttime, re.IGNORECASE)
            hour = 10
            minute = 0
            if m_time:
                hour = int(m_time.group(1))
                minute = int(m_time.group(2) or 0)
                ampm = m_time.group(3).lower()
                if ampm == "pm" and hour != 12:
                    hour += 12
                elif ampm == "am" and hour == 12:
                    hour = 0
            try:
                dt = datetime.fromisoformat(f"{startdate}T{hour:02d}:{minute:02d}:00").replace(tzinfo=EASTERN).astimezone(timezone.utc)
            except Exception:
                continue

            if dt < now:
                continue

            key = (title.lower(), startdate, park.lower())
            if key in seen:
                continue
            seen.add(key)

            venue_str = f"{park} ({loc})" if loc and loc != park and len(loc) < 40 else park

            cat_lower = (cats_raw + " " + title).lower()
            if any(w in cat_lower for w in ["salsa", "bachata", "tango", "swing dance", "social dance", "lindy hop", "ballroom"]):
                cat = "dance"
            elif any(w in cat_lower for w in ["concert", "music", "dance", "performance"]):
                cat = "music"
            elif any(w in cat_lower for w in ["art", "crafts", "exhibit", "gallery"]):
                cat = "art"
            elif any(w in cat_lower for w in ["fitness", "yoga", "run", "sport", "cardio", "zumba"]):
                cat = "sports"
            elif any(w in cat_lower for w in ["movie", "film", "cinema"]):
                cat = "film"
            elif any(w in cat_lower for w in ["talk", "lecture", "tour", "history", "book"]):
                cat = "community"
            else:
                cat = "outdoors"

            events.append({
                "name": title,
                "date": dt.isoformat(),
                "url": link,
                "venue": venue_str,
                "price": "Free",
                "category": cat,
            })
    except Exception:
        pass
    return events


def scrape_nyc_for_free(url, ua):
    """NYC for FREE — curated free pop-up experiences, brand activations, and giveaways."""
    events = []
    seen = set()
    now = datetime.now(timezone.utc)
    today = datetime.now(EASTERN).date()
    try:
        resp = _SESSION.get(url, headers={"User-Agent": ua}, timeout=12)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        for item in soup.select(".w-dyn-item"):
            link_el = item.select_one("a[href^='/events/']")
            if not link_el:
                continue
            href = link_el.get("href")
            full_url = f"https://www.nycforfree.co{href}" if href.startswith("/") else href

            head = item.find(["h2", "h3", "h4", "h5"])
            title = head.get_text(strip=True) if head else ""
            if not title:
                parts = [p.strip() for p in link_el.get_text(separator="|").split("|") if p.strip()]
                if len(parts) >= 2:
                    title = parts[1]
                elif parts:
                    title = parts[0]
            if not title or len(title) < 4:
                continue

            raw_text = item.get_text(separator=" | ", strip=True)
            stamp_matches = re.findall(r"(\d{4}-\d{2}-\d{2})\|(\d{2}:\d{2})", raw_text)
            date_matches = re.findall(r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),\s+(\d{4})", raw_text, re.IGNORECASE)

            time_m = re.search(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)", raw_text, re.IGNORECASE)
            hour = 12
            minute = 0
            if time_m:
                hour = int(time_m.group(1))
                minute = int(time_m.group(2) or 0)
                ampm = time_m.group(3).lower()
                if ampm == "pm" and hour != 12:
                    hour += 12
                elif ampm == "am" and hour == 12:
                    hour = 0

            addr_m = re.search(r"(\d+[^|]+(?:St|Ave|Rd|Blvd|Way|Dr|Lane|Place|Pl|Square|Sq|Parkway|Pkwy)[^|]*(?:NY|USA)?)", raw_text)
            venue = addr_m.group(1).strip() if addr_m else "NYC Pop-up / Experience"
            if len(venue) > 60:
                venue = venue[:60]

            target_dates = []
            if stamp_matches:
                for d_str, t_str in stamp_matches:
                    try:
                        th, tm = map(int, t_str.split(":"))
                        dt = datetime.fromisoformat(f"{d_str}T{th:02d}:{tm:02d}:00").replace(tzinfo=EASTERN).astimezone(timezone.utc)
                        if dt >= now:
                            target_dates.append(dt)
                    except Exception:
                        pass
            elif date_matches:
                parsed_d = []
                for m, d, y in date_matches:
                    try:
                        dt = datetime.strptime(f"{m} {d} {y}", "%B %d %Y").replace(tzinfo=EASTERN)
                        parsed_d.append(dt)
                    except Exception:
                        pass
                if len(parsed_d) >= 2:
                    start_d, end_d = parsed_d[0].date(), parsed_d[1].date()
                    if end_d >= today:
                        active_d = max(today, start_d)
                        dt = datetime(active_d.year, active_d.month, active_d.day, hour, minute, tzinfo=EASTERN).astimezone(timezone.utc)
                        target_dates.append(dt)
                elif len(parsed_d) == 1:
                    dt = datetime(parsed_d[0].year, parsed_d[0].month, parsed_d[0].day, hour, minute, tzinfo=EASTERN).astimezone(timezone.utc)
                    if dt >= now:
                        target_dates.append(dt)

            if not target_dates:
                continue

            for dt in target_dates:
                key = (title.lower(), dt.date().isoformat())
                if key in seen:
                    continue
                seen.add(key)
                events.append({
                    "name": title,
                    "date": dt.isoformat(),
                    "url": full_url,
                    "venue": venue,
                    "price": "Free",
                    "category": guess_category(title, "community"),
                })
    except Exception:
        pass
    return events


def scrape_thisweekinswingnyc(url, ua):
    """This Week in Swing NYC — comprehensive weekly calendar of Lindy Hop, Swing, Balboa & Blues dances."""
    events = []
    now = datetime.now(timezone.utc)
    now_eastern = datetime.now(EASTERN)
    min_date = now_eastern.date() - timedelta(days=1)

    month_map = {
        "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
        "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12
    }

    known_venues = [
        (["frim fram", "ysbd", "you should be dancing", "saturday night swings", "white heat"], "You Should Be Dancing (YSBD)"),
        (["midtown swings", "danznik"], "Danznik Studios"),
        (["back room"], "The Back Room"),
        (["swing 46"], "Swing 46 Jazz & Supper Club"),
        (["gotham jazz", "somewhere nowhere"], "Somewhere Nowhere NYC"),
        (["terra blues"], "Terra Blues"),
        (["friday night blues", "hungarian house"], "Hungarian House (Blues Dance NY)"),
        (["swing remix", "good shepherd"], "Good Shepherd Church"),
        (["the keep", "positively swingin"], "The Keep (Bushwick)"),
        (["young ethel"], "Young Ethel's (South Brooklyn)"),
        (["the box house", "box house hotel"], "The Box House Hotel (Greenpoint)"),
        (["the last word", "astoria swing"], "The Last Word (Astoria)"),
        (["harlem swing dance", "street dance"], "Harlem Swing Dance Society"),
        (["connolly", "sock hop"], "Connolly's Pub (Times Square)"),
        (["kilowatt", "lindy lab"], "Kilowatt Dance Studio"),
        (["mehanata", "jazz on ludlow"], "Mehanata (Lower East Side)"),
        (["pangea"], "Pangea (East Village)"),
        (["estonian house", "shanghai mermaid"], "Estonian House (Murray Hill)"),
        (["mona"], "Mona's (East Village)"),
        (["ripley-grier", "queer jazz"], "Ripley-Grier Studios"),
        (["prince george ballroom"], "Prince George Ballroom"),
        (["the dl"], "The DL Rooftop"),
        (["transit museum", "subway swing"], "New York Transit Museum"),
        (["sara d roosevelt", "chinatown swing"], "Sara D. Roosevelt Park"),
        (["java street"], "Java Street Community Garden"),
        (["central park swings"], "Central Park (King Jagiello Plaza)"),
    ]

    try:
        resp = _SESSION.get(
            url,
            headers={
                "User-Agent": ua,
                "Accept": "application/json, text/html, */*",
            },
            timeout=15,
        )
        resp.raise_for_status()

        posts = []
        try:
            posts = resp.json()
            if not isinstance(posts, list):
                posts = [posts]
        except Exception:
            posts = []

        date_regex = re.compile(
            r"^(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),\s+([A-Za-z]+)\s+(\d{1,2})(?:[a-z]{2})?(?:,?\s*(\d{4}))?(?:\s*[-–].*)?$",
            re.I,
        )

        for post in posts:
            post_url = post.get("link") or "https://thisweekinswingnyc.com/"
            content_html = post.get("content", {}).get("rendered", "")
            if not content_html:
                continue
            soup = BeautifulSoup(content_html, "html.parser")
            text = soup.get_text("\n")
            lines = [l.strip() for l in text.split("\n") if l.strip()]

            sections = []
            cur_date_info = None
            cur_lines = []

            for line in lines:
                m = date_regex.match(line)
                if m:
                    if cur_date_info and cur_lines:
                        if len(cur_lines) == 1 and len(cur_lines[0]) < 80 and not any(k in cur_lines[0].lower() for k in ["cancelled", "postponed"]):
                            saved_title = cur_lines[0]
                        else:
                            saved_title = None
                            sections.append((cur_date_info, cur_lines))
                    else:
                        saved_title = None

                    day_name, mon_name, day_num, yr = m.group(1), m.group(2).lower(), int(m.group(3)), m.group(4)
                    year = int(yr) if yr else now_eastern.year
                    if mon_name in month_map:
                        mon = month_map[mon_name]
                        if mon < 10 and year == now_eastern.year and now_eastern.month >= 10:
                            year = now_eastern.year + 1
                        cur_date_info = (year, mon, day_num, day_name)
                        cur_lines = [saved_title] if saved_title else []
                    else:
                        cur_lines.append(line)
                else:
                    if cur_date_info:
                        cur_lines.append(line)
            if cur_date_info and cur_lines:
                sections.append((cur_date_info, cur_lines))

            for (year, mon, day_num, day_name), blines in sections:
                if not blines:
                    continue
                title = blines[0]
                full_text = " ".join(blines)
                if "this event has been postponed" in full_text.lower() or "no fram" in full_text.lower():
                    continue
                if len(title) > 90 or title.lower().startswith("eileen") or title.lower().startswith("many thanks"):
                    continue
                if re.search(r"^\d+\s+[A-Za-z]|^\d+:\d+", title):
                    if len(blines) > 1 and len(blines[1]) < 80:
                        title = blines[1]

                time_m = re.search(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)", full_text, re.I)
                hr, mn = 19, 0
                if time_m:
                    hr = int(time_m.group(1))
                    mn = int(time_m.group(2) or 0)
                    ampm = time_m.group(3).lower()
                    if ampm == "pm" and hr < 12:
                        hr += 12
                    elif ampm == "am" and hr == 12:
                        hr = 0

                try:
                    event_date = datetime(year, mon, day_num, hr, mn, tzinfo=EASTERN)
                except ValueError:
                    continue

                if event_date.date() < min_date:
                    continue

                venue = None
                for patterns, vname in known_venues:
                    if any(p in title.lower() for p in patterns) or any(p in full_text.lower() for p in patterns):
                        venue = vname
                        break
                if not venue:
                    venue = "This Week in Swing NYC"

                price = None
                m_price = re.search(r"(\$\d+(?:\s*[-–/]\s*\$?\d+)?|\bfree\b|no cover)", full_text, re.I)
                if m_price:
                    price = m_price.group(1).title()

                desc = " ".join(blines[1:5])[:250]
                dt_utc = event_date.astimezone(timezone.utc)

                events.append({
                    "name": title,
                    "date": dt_utc.isoformat(),
                    "url": post_url,
                    "venue": venue,
                    "price": price,
                    "description": desc,
                    "category": "dance",
                })
    except Exception:
        pass
    return events


# --- Curated Recurring NYC Events ---
MANUAL_RECURRING_EVENTS = [
    ("Union Square Greenmarket", "https://www.grownyc.org/greenmarket/manhattan-union-square-m", "food", [
        ("Union Square Greenmarket", "https://www.grownyc.org/greenmarket/manhattan-union-square-m", 0, 8, 0, "Free"),
        ("Union Square Greenmarket", "https://www.grownyc.org/greenmarket/manhattan-union-square-w", 2, 8, 0, "Free"),
        ("Union Square Greenmarket", "https://www.grownyc.org/greenmarket/manhattan-union-square-f", 4, 8, 0, "Free"),
        ("Union Square Greenmarket", "https://www.grownyc.org/greenmarket/manhattan-union-square-s", 5, 8, 0, "Free"),
    ]),
    ("Grand Bazaar NYC", "https://grandbazaarnyc.org/", "community", [
        ("Grand Bazaar NYC (Upper West Side)", "https://grandbazaarnyc.org/", 6, 10, 0, "Free"),
    ]),
    ("Brooklyn Flea", "https://brooklynflea.com/", "community", [
        ("Brooklyn Flea @ DUMBO Archway", "https://brooklynflea.com/", 5, 10, 0, "Free"),
        ("Brooklyn Flea @ DUMBO Archway", "https://brooklynflea.com/", 6, 10, 0, "Free"),
    ]),
    ("Smorgasburg NYC", "https://www.smorgasburg.com/", "food", [
        ("Smorgasburg Williamsburg", "https://www.smorgasburg.com/", 5, 11, 0, "Free entry"),
        ("Smorgasburg Prospect Park", "https://www.smorgasburg.com/", 6, 11, 0, "Free entry"),
    ]),
    ("Comedy Cellar", "https://www.comedycellar.com/line-up/", "comedy", [
        ("Comedy Cellar Showcase", "https://www.comedycellar.com/line-up/", 0, 20, 0),
        ("Comedy Cellar Showcase", "https://www.comedycellar.com/line-up/", 1, 20, 0),
        ("Comedy Cellar Showcase", "https://www.comedycellar.com/line-up/", 2, 20, 0),
        ("Comedy Cellar Showcase", "https://www.comedycellar.com/line-up/", 3, 20, 0),
        ("Comedy Cellar Showcase", "https://www.comedycellar.com/line-up/", 4, 20, 0),
        ("Comedy Cellar Showcase", "https://www.comedycellar.com/line-up/", 5, 20, 0),
        ("Comedy Cellar Showcase", "https://www.comedycellar.com/line-up/", 6, 20, 0),
    ]),
    ("Gonzalez y Gonzalez", "https://www.gygnyc.com/", "dance", [
        ("Live Salsa Band & Dance Party", "https://www.gygnyc.com/", 3, 21, 0, "Free Lesson"),
        ("Live Salsa Band & Dance Party", "https://www.gygnyc.com/", 4, 21, 0, "Live Band"),
        ("Live Salsa Band & Dance Party", "https://www.gygnyc.com/", 5, 21, 0, "Live Band"),
    ]),
    ("Taj Lounge", "https://tajloungenyc.com/", "dance", [
        ("Taj Monday Night Salsa & Bachata Social", "https://tajloungenyc.com/", 0, 19, 0, "Dance Lesson & Social"),
    ]),
    ("Club Cache", "https://www.clubcachenyc.com/", "dance", [
        ("Club Cache Thursday Salsa & Bachata Social", "https://www.clubcachenyc.com/", 3, 20, 0, "Dance Class & Social"),
        ("Club Cache Saturday Latin Dance Party", "https://www.clubcachenyc.com/", 5, 20, 0, "Dance Class & Social"),
    ]),
    ("Iguana NYC", "https://www.iguananyc.com/", "dance", [
        ("Iguana Latin Dance & Salsa Lounge", "https://www.iguananyc.com/", 2, 20, 0, "No Cover / Latin Lounge"),
        ("Iguana Latin Dance & Salsa Lounge", "https://www.iguananyc.com/", 3, 20, 0, "No Cover / Latin Lounge"),
        ("Iguana Latin Dance & Salsa Lounge", "https://www.iguananyc.com/", 4, 20, 0, "Latin Dance Upstairs"),
        ("Iguana Latin Dance & Salsa Lounge", "https://www.iguananyc.com/", 5, 20, 0, "Latin Dance Upstairs"),
    ]),
    ("S.O.B.'s (Sounds of Brazil)", "https://sobs.com/", "dance", [
        ("Live Salsa Orchestra & Latin Dance Party", "https://sobs.com/", 4, 22, 0, "Live Band & Dancing"),
        ("Live Salsa Orchestra & Latin Dance Party", "https://sobs.com/", 5, 22, 0, "Live Band & Dancing"),
    ]),
    ("Cucala Dance Company", "https://www.cucaladance.com/", "dance", [
        ("Friday Night Salsa Social & Workshops", "https://www.cucaladance.com/", 4, 20, 0, "Dance Lesson & Social"),
    ]),
    ("Salsa Salsa Dance Studios", "https://www.salsasalsadance.com/", "dance", [
        ("Brooklyn Salsa Social & Practice Party", "https://www.salsasalsadance.com/", 4, 20, 0, "Practice Social"),
    ]),
    ("Washington Square Park (Garibaldi Plaza)", "https://www.nycgovparks.org/events/dance", "dance", [
        ("Garibaldi Plaza Salsa Social (Free Lesson & Open Dance)", "https://www.nycgovparks.org/events/dance", 2, 18, 0, "Free"),
        ("Washington Square Park Sunday Salsa & Latin Social", "https://www.nycgovparks.org/events/dance", 6, 16, 0, "Free"),
    ]),
    ("Hudson River Park (Pier 45 & Pier 76)", "https://hudsonriverpark.org/event-series/dance-in-hrpk/", "dance", [
        ("Sunset Salsa with Talía Castro-Pozo @ Pier 45", "https://hudsonriverpark.org/event-series/dance-in-hrpk/", 3, 18, 30, "Free"),
        ("Sunset Salsa @ Pier 76 (Waterfront Social & Lesson)", "https://hudsonriverpark.org/event-series/dance-in-hrpk/", 1, 18, 30, "Free"),
    ]),
    ("Bryant Park", "https://bryantpark.org/activities/dance-party", "dance", [
        ("Bryant Park Dance Party (Live Band & Outdoor Salsa)", "https://bryantpark.org/activities/dance-party", 2, 18, 0, "Free"),
    ]),
    ("Bella Abzug Park (Hudson Yards)", "https://www.somoslatindance.com/palacallenyc", "dance", [
        ("Pa' La Calle NYC Latin Dance Social (Intro Lesson & Open Dancing)", "https://www.somoslatindance.com/palacallenyc", 6, 16, 0, "Free"),
    ]),
    ("Vanderbilt Open Streets (Brooklyn)", "https://www.salsasalsadance.com/", "dance", [
        ("Salsa Salsa on Vanderbilt Open Streets (Free Class & Social)", "https://www.salsasalsadance.com/", 5, 17, 0, "Free"),
    ]),
    ("Abolitionist Place Park (Downtown Brooklyn)", "https://www.salsasalsadance.com/", "dance", [
        ("Abolitionist Place Park Outdoor Salsa & Bachata Social", "https://www.salsasalsadance.com/", 6, 16, 0, "Free"),
    ]),
    ("Hunters Point South Park (Long Island City)", "https://www.hunterspointparks.org/", "dance", [
        ("Hunters Point Waterfront Salsa Social (Free Lesson & Sunset Dance)", "https://www.hunterspointparks.org/", 6, 17, 0, "Free"),
    ]),
    ("Domino Park (Williamsburg Waterfront)", "https://www.dominopark.com/", "dance", [
        ("Domino Park Waterfront Latin & Salsa Social", "https://www.dominopark.com/", 5, 17, 0, "Free"),
    ]),
    ("The Back Room", "https://www.backroomnyc.com/", "dance", [
        ("Monday Night Live Jazz & Swing Dancing", "https://www.backroomnyc.com/", 0, 20, 30, "No Cover"),
    ]),
    ("Swing 46 Jazz & Supper Club", "https://swing46.nyc/", "dance", [
        ("Big Band Swing Dance & Lessons", "https://swing46.nyc/", 2, 20, 30, "Dance Lesson & Band"),
        ("Big Band Swing Dance & Lessons", "https://swing46.nyc/", 3, 20, 30, "Dance Lesson & Band"),
        ("Big Band Swing Dance & Lessons", "https://swing46.nyc/", 4, 20, 30, "Dance Lesson & Band"),
        ("Big Band Swing Dance & Lessons", "https://swing46.nyc/", 5, 20, 30, "Dance Lesson & Band"),
        ("Big Band Swing Dance & Lessons", "https://swing46.nyc/", 6, 20, 30, "Dance Lesson & Band"),
    ]),
    ("You Should Be Dancing (YSBD)", "https://youshouldbedancing.live/", "dance", [
        ("Frim Fram Jam (Intro Swing Lesson & Social Dance)", "http://www.frimframjam.com/", 3, 20, 30, "$15–$25"),
        ("Saturday Night Swings (Live Big Band & Lesson)", "https://youshouldbedancing.live/", 5, 19, 15, "$25–$30"),
        ("Social Swing Dance & Practice Session", "https://youshouldbedancing.live/", 1, 19, 0, "$5"),
    ]),
    ("Danznik Studios", "https://midtownswings.com/", "dance", [
        ("Midtown Swings (Intro Lindy Hop & DJ Social)", "https://midtownswings.com/", 1, 21, 0, "$15–$25"),
    ]),
    ("The Keep (Bushwick)", "https://thisweekinswingnyc.com/", "dance", [
        ("Positively Swingin' (Live Band & Warm-up Lesson)", "https://thisweekinswingnyc.com/", 2, 19, 30, "No Cover"),
    ]),
    ("Hungarian House (Blues Dance NY)", "https://bluesdancenewyork.com/", "dance", [
        ("Friday Night Blues (Live Blues Band & Lesson)", "https://bluesdancenewyork.com/", 4, 20, 0, "$20–$35"),
    ]),
    ("Somewhere Nowhere NYC", "https://prohibitionproductions.com/gothamjazz", "dance", [
        ("Gotham Jazz (Live Hot Toddies Band, Dance Lesson & Burlesque)", "https://prohibitionproductions.com/gothamjazz", 2, 19, 15, "Free RSVP"),
    ]),
    ("Harlem Swing Dance Society", "http://www.theharlemswingdancesociety.org/", "dance", [
        ("Street Dance Harlem (Free Lindy Hop Lesson & Social)", "http://www.theharlemswingdancesociety.org/", 5, 15, 0, "Free"),
    ]),
    ("Terra Blues", "https://www.terrablues.com/", "dance", [
        ("Terra Blues Meet-up (Live Blues Band & Dancing)", "https://www.terrablues.com/", 0, 21, 30, "$20"),
    ]),
    ("Good Shepherd Church", "https://swingremix.com/", "dance", [
        ("Swing Remix Big Band Dance & Workshop", "https://swingremix.com/", 5, 19, 30, "$20–$30"),
    ]),
    ("Connolly's Pub (Times Square)", "https://thisweekinswingnyc.com/", "dance", [
        ("Sock Hop Sundays (50s/60s Rock-n-Roll & Swing Dance)", "https://thisweekinswingnyc.com/", 6, 18, 0, "$25"),
    ]),
    ("Kilowatt Dance Studio", "https://thisweekinswingnyc.com/", "dance", [
        ("Lindy Lab (Self-Directed Practice Session)", "https://thisweekinswingnyc.com/", 5, 17, 0, "Free"),
    ]),
    ("The Last Word (Astoria)", "https://thisweekinswingnyc.com/", "dance", [
        ("Astoria Swing Dance (Free Lesson & DJ Social)", "https://thisweekinswingnyc.com/", 3, 19, 30, "Free"),
    ]),
    ("Mehanata (Lower East Side)", "https://thisweekinswingnyc.com/", "dance", [
        ("Jazz on Ludlow (Swing Lesson & Live Band)", "https://thisweekinswingnyc.com/", 6, 18, 30, "No Cover"),
    ]),
    ("Pieces Bar", "https://www.piecesbar.com/", "theater", [
        ("Nightly West Village Drag Show", "https://www.piecesbar.com/", 0, 21, 0, "No Cover"),
        ("Nightly West Village Drag Show", "https://www.piecesbar.com/", 1, 21, 0, "No Cover"),
        ("Nightly West Village Drag Show", "https://www.piecesbar.com/", 2, 21, 0, "No Cover"),
        ("Nightly West Village Drag Show", "https://www.piecesbar.com/", 3, 21, 0, "No Cover"),
        ("Nightly West Village Drag Show", "https://www.piecesbar.com/", 4, 21, 0, "No Cover"),
        ("Nightly West Village Drag Show", "https://www.piecesbar.com/", 5, 21, 0, "No Cover"),
        ("Nightly West Village Drag Show", "https://www.piecesbar.com/", 6, 21, 0, "No Cover"),
    ]),
    ("The Stonewall Inn", "https://thestonewallinnnyc.com/", "theater", [
        ("Stonewall Upstairs Drag & Cabaret", "https://thestonewallinnnyc.com/", 4, 22, 0, "$5–$10"),
        ("Stonewall Upstairs Drag & Cabaret", "https://thestonewallinnnyc.com/", 5, 22, 0, "$5–$10"),
    ]),
    ("Mona's", "https://www.facebook.com/monasbar/", "music", [
        ("Monday Night Irish Trad Music Session", "https://www.facebook.com/monasbar/", 0, 21, 0, "Free"),
        ("Mona's Tuesday Night Hot Jazz & Swing Jam", "https://www.facebook.com/MonasTuesdayJazz", 1, 21, 0, "No Cover"),
    ]),
    ("Bossa Nova Civic Club", "https://bossanovacivicclub.com/", "clubbing", [
        ("Techno & House Sessions (Free Before 11PM)", "https://bossanovacivicclub.com/", 0, 22, 0, "Free before 11PM"),
        ("Techno & House Sessions (Free Before 11PM)", "https://bossanovacivicclub.com/", 1, 22, 0, "Free before 11PM"),
        ("Techno & House Sessions (Free Before 11PM)", "https://bossanovacivicclub.com/", 2, 22, 0, "Free before 11PM"),
        ("Techno & House Sessions (Free Before 11PM)", "https://bossanovacivicclub.com/", 3, 22, 0, "Free before 11PM"),
        ("Techno & House Sessions (Free Before 11PM)", "https://bossanovacivicclub.com/", 4, 22, 0, "Free before 11PM"),
        ("Techno & House Sessions (Free Before 11PM)", "https://bossanovacivicclub.com/", 5, 22, 0, "Free before 11PM"),
        ("Techno & House Sessions (Free Before 11PM)", "https://bossanovacivicclub.com/", 6, 22, 0, "Free before 11PM"),
    ]),
    ("Jupiter Disco", "https://www.jupiterdisco.com/", "clubbing", [
        ("Analog Synth & Underground DJ Night", "https://www.jupiterdisco.com/", 3, 20, 0, "No Cover"),
        ("Analog Synth & Underground DJ Night", "https://www.jupiterdisco.com/", 4, 20, 0, "No Cover"),
        ("Analog Synth & Underground DJ Night", "https://www.jupiterdisco.com/", 5, 20, 0, "No Cover"),
        ("Analog Synth & Underground DJ Night", "https://www.jupiterdisco.com/", 6, 20, 0, "No Cover"),
    ]),
]


def _expand_manual_recurring(weeks=8):
    today = datetime.now(EASTERN).date()
    results = []
    for venue, venue_url, default_cat, items in MANUAL_RECURRING_EVENTS:
        events = []
        for item in items:
            name, url, weekday, hour, minute = item[:5]
            price = item[5] if len(item) > 5 else None
            ahead = (weekday - today.weekday()) % 7
            first_day = today + timedelta(days=ahead)
            for w in range(weeks):
                d = first_day + timedelta(weeks=w)
                dt = datetime(d.year, d.month, d.day, hour, minute, tzinfo=EASTERN)
                events.append({
                    "name": name,
                    "date": dt.astimezone(timezone.utc).isoformat(),
                    "url": url,
                    "venue": venue,
                    "price": price,
                    "category": default_cat,
                })
        results.append({
            "venue": venue,
            "url": venue_url,
            "events": events,
            "error": None,
        })
    return results


# --- Registered Venues ---
_ALL_VENUES = [
    # Megasites & Aggregators
    {"name": "DoNYC Citywide", "url": "https://donyc.com/events", "ua": UA_CHROME, "scraper": scrape_donyc_calendar, "default_category": None},
    {"name": "The Skint NYC", "url": "https://theskint.com/", "ua": UA_CHROME, "scraper": scrape_the_skint, "default_category": "community"},
    {"name": "Ticketmaster NYC", "url": "https://www.ticketmaster.com/", "ua": UA_CHROME, "scraper": scrape_ticketmaster_nyc, "default_category": "music"},

    # Brooklyn Music & Nightlife
    {"name": "Brooklyn Bowl", "url": "https://donyc.com/venues/brooklyn-bowl", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "music"},
    {"name": "Elsewhere Brooklyn", "url": "https://donyc.com/venues/elsewhere", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "clubbing"},
    {"name": "Knockdown Center", "url": "https://donyc.com/venues/knockdown-center", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "music"},
    {"name": "Good Room Greenpoint", "url": "https://donyc.com/venues/good-room", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "clubbing"},
    {"name": "TV Eye Ridgewood", "url": "https://donyc.com/venues/tv-eye", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "music"},
    {"name": "Public Records Gowanus", "url": "https://donyc.com/venues/public-records", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "clubbing"},
    {"name": "The Bell House", "url": "https://donyc.com/venues/the-bell-house", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "comedy"},
    {"name": "Littlefield Brooklyn", "url": "https://donyc.com/venues/littlefield", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "comedy"},
    {"name": "Music Hall of Williamsburg", "url": "https://donyc.com/venues/music-hall-of-williamsburg", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "music"},
    {"name": "Brooklyn Steel", "url": "https://donyc.com/venues/brooklyn-steel", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "music"},
    {"name": "Warsaw Brooklyn", "url": "https://donyc.com/venues/warsaw", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "music"},
    {"name": "Barclays Center", "url": "https://donyc.com/venues/barclays-center", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "sports"},
    {"name": "Kings Theatre Flatbush", "url": "https://donyc.com/venues/kings-theatre", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "music"},
    {"name": "Baby's All Right Williamsburg", "url": "https://donyc.com/venues/baby-s-all-right", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "music"},
    {"name": "The Sultan Room Bushwick", "url": "https://donyc.com/venues/the-sultan-room", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "music"},
    {"name": "Pioneer Works Red Hook", "url": "https://donyc.com/venues/pioneer-works", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "art"},
    {"name": "C'mon Everybody Bed-Stuy", "url": "https://donyc.com/venues/c-mon-everybody", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "music"},

    # Queens
    {"name": "Forest Hills Stadium", "url": "https://donyc.com/venues/forest-hills-stadium", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "music"},

    # The Bronx
    {"name": "Yankee Stadium", "url": "https://donyc.com/venues/yankee-stadium", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "sports"},
    {"name": "Lehman Center for the Performing Arts", "url": "https://donyc.com/venues/lehman-center-for-the-performing-arts", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "theater"},

    # Staten Island
    {"name": "St. George Theatre Staten Island", "url": "https://donyc.com/venues/st-george-theatre", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "theater"},

    # Manhattan Music, Clubs & Comedy
    {"name": "Bowery Ballroom", "url": "https://donyc.com/venues/bowery-ballroom", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "music"},
    {"name": "Mercury Lounge", "url": "https://donyc.com/venues/mercury-lounge", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "music"},
    {"name": "Webster Hall", "url": "https://donyc.com/venues/webster-hall", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "music"},
    {"name": "Terminal 5", "url": "https://donyc.com/venues/terminal-5", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "music"},
    {"name": "Irving Plaza", "url": "https://donyc.com/venues/irving-plaza", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "music"},
    {"name": "Racket NYC", "url": "https://donyc.com/venues/racket-nyc", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "music"},
    {"name": "Le Poisson Rouge", "url": "https://donyc.com/venues/le-poisson-rouge", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "music"},
    {"name": "Blue Note Jazz Club", "url": "https://donyc.com/venues/blue-note-jazz-club", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "music"},
    {"name": "Caveat NYC", "url": "https://donyc.com/venues/caveat", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "comedy"},
    {"name": "Apollo Theater", "url": "https://donyc.com/venues/apollo-theater", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "theater"},
    {"name": "Madison Square Garden", "url": "https://donyc.com/venues/madison-square-garden", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "music"},
    {"name": "Radio City Music Hall", "url": "https://donyc.com/venues/radio-city-music-hall", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "music"},
    {"name": "Beacon Theatre", "url": "https://donyc.com/venues/beacon-theatre", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "music"},
    {"name": "Carnegie Hall", "url": "https://donyc.com/venues/carnegie-hall", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "music"},
    {"name": "The Town Hall", "url": "https://donyc.com/venues/the-town-hall", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "music"},
    {"name": "Sony Hall", "url": "https://donyc.com/venues/sony-hall", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "music"},
    {"name": "Gramercy Theatre", "url": "https://donyc.com/venues/gramercy-theatre", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "music"},

    # Independent Bookstores & Literary Spaces
    {"name": "Strand Book Store", "url": "https://www.eventbrite.com/api/v3/organizers/30058841244/events/?order_by=start_asc", "ua": UA_CHROME, "scraper": scrape_eventbrite_organizer, "default_category": "books"},
    {"name": "Books Are Magic", "url": "https://www.eventbrite.com/api/v3/organizers/17671794664/events/?order_by=start_asc", "ua": UA_CHROME, "scraper": scrape_eventbrite_organizer, "default_category": "books"},
    {"name": "Greenlight Bookstore", "url": "https://www.eventbrite.com/api/v3/organizers/13064382976/events/?order_by=start_asc", "ua": UA_CHROME, "scraper": scrape_eventbrite_organizer, "default_category": "books"},
    {"name": "P&T Knitwear Books & Podcasts", "url": "https://www.eventbrite.com/api/v3/organizers/41790821233/events/?order_by=start_asc", "ua": UA_CHROME, "scraper": scrape_eventbrite_organizer, "default_category": "books"},
    {"name": "Housing Works Bookstore Cafe", "url": "https://www.eventbrite.com/api/v3/organizers/6548340747/events/?order_by=start_asc", "ua": UA_CHROME, "scraper": scrape_eventbrite_organizer, "default_category": "books"},
    {"name": "McNally Jackson Books", "url": "https://www.eventbrite.com/d/ny--new-york/mcnally-jackson/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "books"},
    {"name": "Bluestockings Cooperative", "url": "https://www.eventbrite.com/d/ny--new-york/bluestockings/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "books"},
    {"name": "KGB Bar (Literary Readings)", "url": "https://donyc.com/venues/kgb-bar", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "books"},

    # NYC Public Libraries (Free Marquee Author Talks & Community Series)
    {"name": "New York Public Library", "url": "https://www.eventbrite.com/d/ny--new-york/nypl/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "community"},
    {"name": "Brooklyn Public Library", "url": "https://www.eventbrite.com/d/ny--brooklyn/brooklyn-public-library/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "community"},
    {"name": "Queens Public Library", "url": "https://www.eventbrite.com/d/ny--queens/queens-public-library/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "community"},

    # Local Neighborhood Bars, Live Jams, Open Mics & Pub Trivia
    {"name": "Pete's Candy Store", "url": "https://www.petescandystore.com/calendar/", "ua": UA_CHROME, "scraper": scrape_petes_candy_store, "default_category": "music"},
    {"name": "Skinny Dennis", "url": "https://skinnydennisbrooklyn.com/calendar?format=json", "ua": UA_CHROME, "scraper": scrape_squarespace_calendar, "default_category": "music"},
    {"name": "NYC Trivia League", "url": "https://nyctrivialeague.com/jm-ajax/get_listings/", "ua": UA_CHROME, "scraper": scrape_nyc_trivia_league, "default_category": "gaming"},

    # Indie Cinemas, Micro-Theaters & Historic Jazz
    {"name": "Film Forum", "url": "https://donyc.com/venues/film-forum", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "film"},
    {"name": "Nitehawk Cinema", "url": "https://donyc.com/venues/nitehawk-cinema", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "film"},
    {"name": "IFC Center", "url": "https://donyc.com/venues/ifc-center", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "film"},
    {"name": "Union Hall Brooklyn", "url": "https://donyc.com/venues/union-hall", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "comedy"},
    {"name": "Smalls Jazz Club", "url": "https://donyc.com/venues/smalls-jazz-club", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "music"},

    # Legendary Greenwich Village & Lower East Side Music Halls
    {"name": "Joe's Pub (The Public Theater)", "url": "https://donyc.com/venues/joes-pub", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "music"},
    {"name": "The Bitter End (Greenwich Village)", "url": "https://donyc.com/venues/the-bitter-end", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "music"},
    {"name": "Arlene's Grocery (LES Rock & Karaoke)", "url": "https://donyc.com/venues/arlenes-grocery", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "music"},
    {"name": "Nublu 151 (Alphabet City)", "url": "https://donyc.com/venues/nublu-151", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "music"},
    {"name": "Drom NYC (East Village Global Music)", "url": "https://donyc.com/venues/drom", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "music"},
    {"name": "Terra Blues (Bleecker St)", "url": "https://donyc.com/venues/terra-blues", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "music"},
    {"name": "Symphony Space (Upper West Side)", "url": "https://donyc.com/venues/symphony-space", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "theater"},

    # Comedy Clubs & Queens Performance Spaces
    {"name": "Tight Pants Comedy", "url": "https://www.eventbrite.com/api/v3/organizers/58671695943/events/?order_by=start_asc", "ua": UA_CHROME, "scraper": scrape_eventbrite_organizer, "default_category": "comedy"},
    {"name": "Greenwich Village Comedy Club", "url": "https://www.eventbrite.com/d/ny--new-york/greenwich-village-comedy-club/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "comedy"},
    {"name": "The Grisly Pear Comedy Club", "url": "https://www.eventbrite.com/d/ny--new-york/grisly-pear-comedy/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "comedy"},
    {"name": "St. Marks Comedy Club", "url": "https://donyc.com/venues/st-marks-comedy-club", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "comedy"},
    {"name": "Q.E.D. Astoria (Comedy & Arts)", "url": "https://donyc.com/venues/qed", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "comedy"},
    {"name": "New York Comedy Club Midtown", "url": "https://donyc.com/venues/new-york-comedy-club-midtown", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "comedy"},
    {"name": "New York Comedy Club East Village", "url": "https://donyc.com/venues/new-york-comedy-club-east-village", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "comedy"},
    {"name": "The Tiny Cupboard (Bushwick Rooftop Comedy)", "url": "https://donyc.com/venues/the-tiny-cupboard", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "comedy"},
    {"name": "Brooklyn Comedy Collective (Eris Mainstage)", "url": "https://donyc.com/venues/brooklyn-comedy-collective", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "comedy"},

    # Free Events Aggregators & Citywide Parks
    {"name": "NYC Parks Free Public Events", "url": "https://www.nycgovparks.org/xml/events_300_rss.xml", "ua": UA_CHROME, "scraper": scrape_nyc_parks, "default_category": "outdoors"},
    {"name": "NYC for FREE (Pop-ups & Experiences)", "url": "https://www.nycforfree.co/events", "ua": UA_CHROME, "scraper": scrape_nyc_for_free, "default_category": "community"},

    # Super Smash Bros (SSB), Arcades & Tabletop Gaming
    {"name": "OS NYC (Super Smash Bros & Gaming)", "url": "https://www.os-nyc.com/events?format=json", "ua": UA_CHROME, "scraper": scrape_squarespace_calendar, "default_category": "gaming"},
    {"name": "Wonderville (Indie Arcade & Smashville)", "url": "https://www.wonderville.nyc/events?format=json", "ua": UA_CHROME, "scraper": scrape_squarespace_calendar, "default_category": "gaming"},
    {"name": "Hex & Company (Board Games & RPG)", "url": "https://www.eventbrite.com/d/ny--new-york/hex-and-company/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "gaming"},
    {"name": "The Uncommons (Board Game Cafe)", "url": "https://www.eventbrite.com/d/ny--new-york/the-uncommons/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "gaming"},
    {"name": "The Brooklyn Strategist", "url": "https://www.eventbrite.com/d/ny--brooklyn/the-brooklyn-strategist/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "gaming"},

    # Nightlife, Immersive Spectacle & Theatrical Circus
    {"name": "House of Yes (Circus & Dance)", "url": "https://donyc.com/venues/house-of-yes", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "party"},

    # Art Galleries, Food Festivals & Community Learning
    {"name": "Chelsea Art Gallery Openings", "url": "https://www.eventbrite.com/d/ny--new-york/chelsea-art-gallery/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "art"},
    {"name": "Japan Fes NYC (Street Food)", "url": "https://www.eventbrite.com/d/ny--new-york/japan-fes/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "food"},
    {"name": "Midnight Runners NYC (Social Run Club)", "url": "https://www.eventbrite.com/d/ny--new-york/midnight-runners/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "sports"},
    {"name": "Brooklyn Brainery (Community Classes)", "url": "https://www.eventbrite.com/d/ny--brooklyn/brooklyn-brainery/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "community"},

    # Long-Form Improv, Sketch & Alternative Comedy
    {"name": "Magnet Theater (Improv & Sketch)", "url": "https://www.eventbrite.com/d/ny--new-york/magnet-theater/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "comedy"},
    {"name": "Asylum NYC (Alternative Comedy)", "url": "https://www.eventbrite.com/d/ny--new-york/asylum-nyc/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "comedy"},

    # Historic Cultural Music Halls
    {"name": "S.O.B.'s (Sounds of Brazil)", "url": "https://donyc.com/venues/sobs", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "music"},

    # Salsa, Bachata & Latin Social Dancing
    {"name": "NYC Salsa & Bachata Socials", "url": "https://www.eventbrite.com/d/ny--new-york/salsa-dancing/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "dance"},
    {"name": "NYC Bachata & Latin Socials", "url": "https://www.eventbrite.com/d/ny--new-york/bachata/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "dance"},
    {"name": "Taj Lounge (Salsa & Latin Socials)", "url": "https://www.eventbrite.com/d/ny--new-york/taj-lounge-salsa/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "dance"},
    {"name": "Club Cache (Salsa & Bachata Socials)", "url": "https://www.eventbrite.com/d/ny--new-york/club-cache-salsa/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "dance"},
    {"name": "NYC Salsa Socials & Dance Parties", "url": "https://www.eventbrite.com/d/ny--new-york/salsa-social/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "dance"},
    {"name": "Washington Square Park (Garibaldi Plaza Salsa)", "url": "https://www.eventbrite.com/d/ny--new-york/washington-square-park-salsa/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "dance"},
    {"name": "Hudson River Park (Sunset Salsa Pier 45 & 76)", "url": "https://www.eventbrite.com/d/ny--new-york/sunset-salsa/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "dance"},
    {"name": "Pa' La Calle NYC (Bella Abzug Park Salsa)", "url": "https://www.eventbrite.com/d/ny--new-york/pa-la-calle/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "dance"},
    {"name": "NYC Outdoor Salsa & Latin Socials", "url": "https://www.eventbrite.com/d/ny--new-york/outdoor-salsa/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "dance"},

    # Swing Dancing, Lindy Hop & Blues
    {"name": "This Week in Swing NYC", "url": "https://thisweekinswingnyc.com/wp-json/wp/v2/posts?per_page=5", "ua": UA_CHROME, "scraper": scrape_thisweekinswingnyc, "default_category": "dance"},
    {"name": "NYC Swing Dancing & Lindy Hop", "url": "https://www.eventbrite.com/d/ny--new-york/swing-dancing/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "dance"},
    {"name": "Frim Fram Jam (YSBD Swing)", "url": "https://www.eventbrite.com/d/ny--new-york/frim-fram-jam/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "dance"},
    {"name": "Prohibition Productions (Gotham Jazz)", "url": "https://www.eventbrite.com/d/ny--new-york/prohibition-productions/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "dance"},

    # Queer Nightlife, Drag Shows & Cabaret
    {"name": "3 Dollar Bill (Queer & Drag Venue)", "url": "https://donyc.com/venues/3-dollar-bill", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "theater"},
    {"name": "NYC Drag Shows & Brunches", "url": "https://www.eventbrite.com/d/ny--new-york/drag-show/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "theater"},
    {"name": "The Stonewall Inn (Events)", "url": "https://www.eventbrite.com/d/ny--new-york/the-stonewall-inn/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "theater"},
    {"name": "Pieces Bar (West Village Drag)", "url": "https://www.eventbrite.com/d/ny--new-york/pieces-bar/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "theater"},

    # Video Games, Super Smash Bros Tournaments & Arcades
    {"name": "NYC Video Game Tournaments", "url": "https://www.eventbrite.com/d/ny--new-york/video-game-tournament/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "gaming"},
    {"name": "NYC Smash Bros Tournaments", "url": "https://www.eventbrite.com/d/ny--new-york/smash-bros/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "gaming"},
    {"name": "Barcade (Arcade & Craft Beer)", "url": "https://www.eventbrite.com/d/ny--new-york/barcade/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "gaming"},

    # Neighborhood Bar Concerts, Live Music Bars & Pop Culture Pub Trivia
    {"name": "Union Pool (Williamsburg Live Music Bar)", "url": "https://donyc.com/venues/union-pool", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "music"},
    {"name": "Our Wicked Lady (Bushwick Live Music)", "url": "https://www.eventbrite.com/d/ny--brooklyn/our-wicked-lady/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "music"},
    {"name": "NYC Bar Concerts & Live Music", "url": "https://www.eventbrite.com/d/ny--new-york/live-music-bar/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "music"},
    {"name": "Trivia A.D. (NYC Bar Trivia)", "url": "https://www.eventbrite.com/api/v3/organizers/4701927701/events/?order_by=start_asc", "ua": UA_CHROME, "scraper": scrape_eventbrite_organizer, "default_category": "gaming"},

    # Free Club Guestlists, Rooftop Lounges & Nightlife RSVPs
    {"name": "NYC Free Club Guestlists", "url": "https://www.eventbrite.com/d/ny--new-york/free-guestlist/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "clubbing"},
    {"name": "NYC Nightclub Guestlists", "url": "https://www.eventbrite.com/d/ny--new-york/nightclub-guestlist/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "clubbing"},
    {"name": "NYC Free RSVP Nightlife", "url": "https://www.eventbrite.com/d/ny--new-york/free-rsvp-party/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "clubbing"},
    {"name": "NYC Rooftop Club Parties", "url": "https://www.eventbrite.com/d/ny--new-york/rooftop-party/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "clubbing"},
    {"name": "Somewhere Nowhere Rooftop Club", "url": "https://www.eventbrite.com/d/ny--new-york/somewhere-nowhere/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "clubbing"},
    {"name": "The DL (LES Rooftop Club)", "url": "https://www.eventbrite.com/d/ny--new-york/the-dl/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "clubbing"},
    {"name": "Harbor NYC Rooftop Club", "url": "https://www.eventbrite.com/d/ny--new-york/harbor-nyc/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "clubbing"},
    {"name": "230 Fifth Rooftop Nightclub", "url": "https://www.eventbrite.com/d/ny--new-york/230-fifth/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "clubbing"},
    {"name": "Slate NYC (Chelsea Lounge & Club)", "url": "https://www.eventbrite.com/d/ny--new-york/slate-nyc/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "clubbing"},
    {"name": "Nebula NYC (Midtown Nightclub)", "url": "https://www.eventbrite.com/d/ny--new-york/nebula/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "clubbing"},
    {"name": "Superior Ingredients (Williamsburg)", "url": "https://donyc.com/venues/superior-ingredients", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "clubbing"},
]

VENUES = _ALL_VENUES


# Static "useful links" — venues & discount programs worth linking
STATIC_LINKS = [
    ("theater", "TodayTix NYC Broadway & Off-Broadway", "https://www.todaytix.com/nyc"),
    ("theater", "Broadway Direct Digital Lotteries", "https://lottery.broadwaydirect.com/"),
    ("theater", "Lucky Seat Broadway Lotteries ($39–$49)", "https://www.luckyseat.com/"),
    ("theater", "TKTS Discount Booths (Times Square & Lincoln Center)", "https://www.tdf.org/tkts"),
    ("art",     "NYC Culture Pass (Free Museums with Library Card)", "https://www.culturepass.nyc/"),
    ("outdoors","NYC Parks Free Events Directory", "https://www.nycgovparks.org/events"),
    ("outdoors","NYC Ferry ($4.00 harbor routes)", "https://www.ferry.nyc/"),
    ("comedy",  "Comedy Cellar Nightly Lineups", "https://www.comedycellar.com/line-up/"),
    ("art",     "The Metropolitan Museum of Art (The Met)", "https://www.metmuseum.org/events"),
    ("art",     "Museum of Modern Art (MoMA)", "https://www.moma.org/calendar/events"),
    ("art",     "Whitney Museum of American Art", "https://whitney.org/events"),
    ("art",     "Brooklyn Museum First Saturdays & Programs", "https://www.brooklynmuseum.org/programs"),
    ("music",   "Lincoln Center Events & Free Series", "https://www.lincolncenter.org/series/lincoln-center-presents"),
    ("music",   "Carnegie Hall Season Calendar", "https://www.carnegiehall.org/Events"),
    ("music",   "Central Park SummerStage", "https://cityparksfoundation.org/summerstage/"),
    ("music",   "BRIC Celebrate Brooklyn! Festival", "https://bricartsmedia.org/celebrate-brooklyn/"),
    ("music",   "Village Vanguard (West Village Jazz)", "https://villagevanguard.com/"),
    ("music",   "Dizzy's Club Jazz at Lincoln Center", "https://jazz.org/dizzys/"),
    ("film",    "Film Forum (West Village Independent Cinema)", "https://filmforum.org/"),
    ("theater", "BAM (Brooklyn Academy of Music)", "https://www.bam.org/"),
    ("books",   "New York Public Library (NYPL) Events", "https://www.nypl.org/events"),
    ("books",   "Brooklyn Public Library (BPL) Events", "https://www.bklynlibrary.org/calendar"),
    ("gaming",  "start.gg (NYC Super Smash Bros Tournaments)", "https://www.start.gg/"),
    ("dance",   "Gonzalez y Gonzalez (Live Salsa & Latin Socials)", "https://www.gygnyc.com/"),
    ("dance",   "Taj Lounge (Monday Night Salsa & Bachata Social)", "https://tajloungenyc.com/"),
    ("dance",   "Club Cache (Thursday & Saturday Salsa Socials)", "https://www.clubcachenyc.com/"),
    ("dance",   "Iguana NYC (Latin Dance & Salsa Lounge)", "https://www.iguananyc.com/"),
    ("dance",   "Cucala Dance Company (East Village Salsa Classes)", "https://www.cucaladance.com/"),
    ("dance",   "Salsa Salsa Dance Studios (Brooklyn Latin Dance)", "https://www.salsasalsadance.com/"),
    ("dance",   "Hudson River Park Sunset Salsa (Pier 45 & Pier 76)", "https://hudsonriverpark.org/event-series/dance-in-hrpk/"),
    ("dance",   "Washington Square Park Garibaldi Plaza Salsa Social", "https://www.nycgovparks.org/events/dance"),
    ("dance",   "Bryant Park Dance Party (Outdoor Salsa & Latin)", "https://bryantpark.org/activities/dance-party"),
    ("dance",   "Pa' La Calle NYC (Bella Abzug Park Hudson Yards Salsa)", "https://www.somoslatindance.com/palacallenyc"),
    ("dance",   "Salsa Salsa Outdoor Series (Vanderbilt Open Streets & Abolitionist Place)", "https://www.salsasalsadance.com/"),
    ("dance",   "Hunters Point South Park Waterfront Salsa", "https://www.hunterspointparks.org/"),
    ("dance",   "Domino Park Waterfront Salsa & Latin Nights", "https://www.dominopark.com/"),
    ("dance",   "Swing 46 Jazz & Supper Club (Lindy Hop & Big Band)", "https://swing46.nyc/"),
    ("dance",   "The Back Room (Monday Night Live Jazz & Swing)", "https://www.backroomnyc.com/"),
    ("dance",   "This Week in Swing NYC (Weekly Lindy Hop & Blues Calendar)", "https://thisweekinswingnyc.com/"),
    ("dance",   "Frim Fram Jam / YSBD (Thursday Weekly Swing Dance)", "http://www.frimframjam.com/"),
    ("dance",   "Midtown Swings at Danznik Studios (Tuesday Lindy Hop)", "https://midtownswings.com/"),
    ("dance",   "Swing Remix (Upper West Side Live Big Bands)", "https://swingremix.com/"),
    ("dance",   "Blues Dance New York (Hungarian House Blues)", "https://bluesdancenewyork.com/"),
    ("dance",   "Harlem Swing Dance Society", "http://www.theharlemswingdancesociety.org/"),
    ("dance",   "Prohibition Productions (Gotham Jazz & The Salon)", "https://prohibitionproductions.com/"),
    ("dance",   "The Keep Bushwick (Positively Swingin' Wednesdays)", "https://thisweekinswingnyc.com/"),
    ("dance",   "The Last Word Astoria (Astoria Swing Dance)", "https://thisweekinswingnyc.com/"),
    ("theater", "3 Dollar Bill (Bushwick Queer & Drag Hall)", "https://www.3dollarbillbk.com/"),
    ("gaming",  "Trivia A.D. (NYC Bar Pop Culture Trivia Nights)", "https://triviaad.com/"),
    ("clubbing","Somewhere Nowhere NYC (Chelsea Rooftop Club & Lounge)", "https://somewherenowherenyc.com/"),
    ("clubbing","The DL (LES Multi-Level Rooftop Club)", "https://thedl-nyc.com/"),
    ("clubbing","Harbor NYC (Hell's Kitchen Rooftop Nightclub)", "https://harbornewyorkcity.com/"),
    ("clubbing","Superior Ingredients (Williamsburg Roof & Room)", "https://superioringredientsnyc.com/"),
    ("clubbing","Bossa Nova Civic Club (Bushwick Underground Techno)", "https://bossanovacivicclub.com/"),
]

DEAL_LINKS = [
    ("TodayTix NYC (Broadway & Off-Bway discounts)", "https://www.todaytix.com/nyc"),
    ("Broadway Direct Lotteries (Hamilton, Wicked, Lion King)", "https://lottery.broadwaydirect.com/"),
    ("Lucky Seat Broadway Lotteries ($39–$49)", "https://www.luckyseat.com/"),
    ("NYC Culture Pass (Free museums for NY library cardholders)", "https://www.culturepass.nyc/"),
    ("Somewhere Nowhere NYC (Free VIP Guestlist before 11:30 PM)", "https://somewherenowherenyc.com/"),
    ("The DL Rooftop (Free Guestlist Entry before 11 PM)", "https://thedl-nyc.com/"),
    ("Harbor NYC (Free RSVP & Sunset Rooftop Parties)", "https://harbornewyorkcity.com/"),
    ("230 Fifth Rooftop (Free General Admission & Igloos)", "https://www.230-fifth.com/"),
    ("Superior Ingredients (Free RSVP House & Techno before 11 PM)", "https://superioringredientsnyc.com/"),
    ("Bossa Nova Civic Club (Free Entry Before 11 PM Nightly)", "https://bossanovacivicclub.com/"),
    ("Jupiter Disco (Always Free / No Cover Retro DJs)", "https://www.jupiterdisco.com/"),
    ("NYC Club Guestlists (Live Eventbrite Free Guestlists)", "https://www.eventbrite.com/d/ny--new-york/free-guestlist/"),
    ("NYC Ferry Tickets ($4.00 per ride)", "https://www.ferry.nyc/"),
]


# --- Cache & Scraper Aggregator ---
_cache = {"ts": 0, "data": None}


def _scrape_one(v):
    t0 = time.time()
    try:
        events = v["scraper"](v["url"], v["ua"])
        for e in events:
            if not e.get("venue"):
                e["venue"] = v["name"]
            if not e.get("category"):
                e["category"] = guess_category(e.get("name"), v.get("default_category") or "community")
        return {
            "venue": v["name"],
            "url": v["url"],
            "events": events,
            "error": None,
            "duration": round(time.time() - t0, 2),
        }
    except Exception as exc:
        return {
            "venue": v["name"],
            "url": v["url"],
            "events": [],
            "error": str(exc),
            "duration": round(time.time() - t0, 2),
        }


def get_all_events(force=False):
    now = time.time()
    if not force and _cache["data"] and (now - _cache["ts"] < CACHE_SECONDS):
        return _cache["data"]

    with ThreadPoolExecutor(max_workers=10) as ex:
        results = list(ex.map(_scrape_one, VENUES))

    # Add recurring events
    results.extend(_expand_manual_recurring(weeks=8))

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "venues": results,
        "weather": fetch_nyc_weather(),
        "luckyseat": fetch_luckyseat_nyc(),
    }
    _cache["ts"] = now
    _cache["data"] = payload
    return payload
