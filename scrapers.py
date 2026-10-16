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
HORIZON_DAYS = 14

CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".cache", "venues")
os.makedirs(CACHE_DIR, exist_ok=True)

DEFAULT_VENUE_TTL = 3 * 3600    # 3 hours for standard venue feeds
FAST_VENUE_TTL = 1 * 3600       # 1 hour for high-turnover feeds (Ticketmaster, SeatGeek, RA, Dice, DoNYC)
SLOW_VENUE_TTL = 12 * 3600      # 12 hours for evergreen/slow feeds (NYC Parks XML, Trivia, Bookstores)


def _is_within_horizon(e, max_days=HORIZON_DAYS):
    """Check if event start date is between today and max_days ahead."""
    raw = e.get("date")
    if not raw:
        return True
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(EASTERN)
        today = datetime.now(EASTERN).date()
        max_date = today + timedelta(days=max_days)
        return today <= dt.date() <= max_date
    except Exception:
        return True


def _get_venue_ttl(vname):
    low = vname.lower()
    if any(k in low for k in ["ticketmaster", "seatgeek", "resident advisor", "dice.fm", "donyc", "the skint", "secret nyc", "greenpointers", "flop house", "sesh comedy"]):
        return FAST_VENUE_TTL
    if any(k in low for k in ["parks", "trivia", "library", "flea", "greenmarket"]):
        return SLOW_VENUE_TTL
    return DEFAULT_VENUE_TTL


def _venue_cache_path(vname):
    slug = re.sub(r"[^a-zA-Z0-9_\-]+", "_", vname).strip("_").lower()
    return os.path.join(CACHE_DIR, f"{slug}.json")


def _load_venue_cache(vname, max_age=None):
    path = _venue_cache_path(vname)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            cached = json.load(f)
        if max_age is not None:
            age = time.time() - cached.get("ts", 0)
            if age > max_age:
                return None
        return cached
    except Exception:
        return None


def _save_venue_cache(vname, events, duration=0.0):
    path = _venue_cache_path(vname)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"ts": time.time(), "venue": vname, "duration": duration, "events": events}, f, ensure_ascii=False)
    except Exception:
        pass

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


BROADWAY_THEATRES = {
    "broadhurst", "gershwin", "minskoff", "amsterdam theatre", "new amsterdam",
    "winter garden", "richard rodgers", "al hirschfeld", "st. james theatre",
    "st james theatre", "walter kerr", "neil simon", "august wilson",
    "lyric theatre", "marquis theatre", "imperial theatre", "shubert theatre",
    "music box theatre", "belasco theatre", "eugene o'neill", "booth theatre",
    "schoenfeld", "bernard b. jacobs", "barrymore theatre", "ethel barrymore",
    "broadway theatre", "lunt-fontanne", "new world stages", "vivian beaumont",
    "mitzi e. newhouse", "hudson theatre", "samuel j. friedman", "todd haimes",
    "studio 54", "stephen sondheim", "nederlander theatre", "john golden theatre",
    "lyceum theatre", "majestic theatre", "ambassador theatre", "circle in the square",
    "longacre theatre", "st. ann's warehouse", "lucille lortel", "minetta lane",
    "cherry lane theatre", "daryl roth", "astor place theatre", "orpheum theatre",
    "westside theatre", "playwrights horizons", "signature theatre", "atlantic theater",
    "classic stage", "soho rep", "irish rep", "second stage", "manhattan theatre club",
    "lincoln center theater", "new york city center", "city center"
}

COMEDY_VENUES = {
    "comedy cellar", "the stand", "gotham comedy", "broadway comedy", "eastville comedy",
    "greenwich village comedy", "grisly pear", "st. marks comedy", "tight pants comedy",
    "new york comedy club", "magnet theater", "the pit", "peoples improv theater",
    "caveat", "flop house comedy", "brooklyn comedy collective", "tiny cupboard"
}

CATEGORY_KEYWORDS = [
    ("theater",   [r"\b(theater|theatre|musical|the musical|broadway|off-broadway|playwright|stage play|cabaret|drama|drag show|drag queen|drag cabaret|drag brunch|burlesque|curtain call|cats: the jellicle ball|hamilton|hadestown|moulin rouge|aladdin|lion king|the outsiders|great gatsby|buena vista social club|stereophonic|sunset boulevard|book of mormon|little shop of horrors|maybe happy ending|operation mincemeat|swept away|death becomes her|sweeney todd|into the woods|west side story|mamma mia|les miserables|phantom of the opera|rent|funny girl|waitress|kinky boots|dear evan hansen|in the heights|spring awakening|titanique|play that goes wrong|cursed child|water for elephants|illinoise|suffs|our town|romeo and juliet|mcneal|yellow face|left on tenth|hills of california|cult of love|gypsy|amaze)\b"]),
    ("comedy",    [r"\b(comedy|stand-?up|improv|open mic comedy|comic|roast|laugh)\b"]),
    ("clubbing",  [r"\b(dj|rave|techno|house music|edm|club night|dance party|nightclub|party|afters|guestlist|free guestlist|rooftop party|clubbing|nightlife)\b"]),
    ("dance",     [r"\b(salsa|bachata|tango|swing dance|swing dancing|lindy hop|lindy|contra dance|ballroom|dance class|social dance|milonga|cumbia)\b"]),
    ("music",     [r"\b(concert|band|orchestra|jazz|symphony|quartet|choir|acoustic|live music|dj set|indie rock|punk|metal|folk|hip-hop|r&b|brass band|honky-tonk|bar concert|live band)\b"]),
    ("film",      [r"\b(screening|film|movie|cinema|documentary|35mm|q&a screening|indie film)\b"]),
    ("art",       [r"\b(exhibit|gallery|museum|reception|sculpture|painting|open studios?|installation)\b"]),
    ("books",     [r"\b(book launch|author talk|poetry|reading|bookstore|book signing|literary)\b"]),
    ("food",      [r"\b(tasting|wine dinner|beer release|food tour|brewery|pop-up dinner|pairing|culinary)\b"]),
    ("outdoors",  [r"\b(hike|walking tour|nature walk|birding|trail|kayak|park tour|outdoor)\b"]),
    ("sports",    [r"\b(yankees|mets|knicks|nets|rangers|islanders|soccer|5k|10k|marathon|hockey|basketball)\b"]),
    ("gaming",    [r"\b(board games?|trivia|arcade|esports|chess|magic the gathering|d&d|tabletop|video game|smash bros|gaming tournament|smash ultimate|melee|lan)\b"]),
    ("community", [r"\b(talk|lecture|panel|discussion|networking|farmers market|flea market|artisan market|expo|festival|parade|sample sale|fashion|symposium|speed-dating|skip the small talk)\b"]),
]

CATEGORY_BUCKETS = [
    ("Music & nightlife",  ["music", "clubbing", "dance"]),
    ("Arts & culture",     ["film", "art", "books", "comedy"]),
    ("Outdoors & active",  ["outdoors", "sports"]),
    ("Social & community", ["community", "food", "gaming", "other"]),
    ("Theater",            ["theater"]),
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


def guess_category(text, default="community", venue=None):
    if venue:
        v_low = venue.lower()
        if any(cv in v_low for cv in COMEDY_VENUES):
            return "comedy"
        if any(bt in v_low for bt in BROADWAY_THEATRES) and not any(k in v_low for k in ["comedy", "film", "cinema"]):
            return "theater"
    if default == "theater":
        return "theater"
    if not text:
        return default
    t = text.lower()
    for cat, patterns in CATEGORY_KEYWORDS:
        for p in patterns:
            if re.search(p, t):
                return cat
    return default


# Shows or productions that have closed or concluded their runs but whose
# future ticketing stubs remain in Ticketmaster / SeatGeek feeds.
CLOSED_SHOWS = (
    "heathers",  # Closed Oct 11, 2026 at New World Stages
    "swing 46",  # Closed Jan 2, 2026 permanently on Restaurant Row
)


def is_closed_show(name):
    if not name:
        return False
    low = name.lower()
    return any(c in low for c in CLOSED_SHOWS)


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
    """DoNYC venue & category scraper — parses Schema.org microdata with Cloudflare error shielding."""
    try:
        soup = fetch_soup(url, ua)
    except Exception:
        return []
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
    """DoNYC multi-day event calendar — fetches next 14 days of citywide listings with pacing & pagination."""
    events = []
    now = datetime.now(EASTERN)
    seen = set()
    for i in range(HORIZON_DAYS):
        d = now.date() + timedelta(days=i)
        for page in (1, 2):
            day_url = f"https://donyc.com/events/{d.year}/{d.month:02d}/{d.day:02d}"
            if page > 1:
                day_url = f"{day_url}?page={page}"
            try:
                time.sleep(0.3)  # Gentle pacing to avoid DoStuff origin server 521 rate limits
                day_events = scrape_donyc(day_url, ua)
                if not day_events:
                    break
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
    events = []
    seen = set()
    now = datetime.now(EASTERN)
    try:
        resp = _SESSION.get("https://theskint.com/feed/", headers={"User-Agent": ua}, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.content, "html.parser")
    except Exception:
        return events

    day_map = {
        "mon": 0, "monday": 0,
        "tue": 1, "tues": 1, "tuesday": 1,
        "wed": 2, "wednesday": 2,
        "thu": 3, "thur": 3, "thurs": 3, "thursday": 3,
        "fri": 4, "friday": 4,
        "sat": 5, "saturday": 5,
        "sun": 6, "sunday": 6,
    }

    def _parse_time(time_str):
        m = re.search(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)", time_str, re.I)
        if not m:
            m_range = re.search(r"(\d{1,2})\s*-\s*\d{1,2}\s*(am|pm)", time_str, re.I)
            if m_range:
                hour = int(m_range.group(1))
                ampm = m_range.group(2).lower()
                if ampm == "pm" and hour != 12 and hour < 8:
                    hour += 12
                return hour, 0
            return 19, 0
        hour = int(m.group(1))
        minute = int(m.group(2)) if m.group(2) else 0
        ampm = m.group(3).lower()
        if ampm == "pm" and hour != 12:
            hour += 12
        elif ampm == "am" and hour == 12:
            hour = 0
        return hour, minute

    def _clean_title(t):
        t = (t or "").strip()
        t = re.sub(r"^(?:►\s*)?(?:the\s+)?", "", t, flags=re.I)
        t = t.rstrip(" :.-")
        if not t:
            return ""
        return t[:1].upper() + t[1:]

    def _extract_venue(rest, ev_title):
        low_t = ev_title.lower()
        low_r = rest.lower()
        if "tompkins square" in low_t or "tompkins square" in low_r:
            return "Tompkins Square Park (East Village)"
        if "washington square" in low_t or "washington square" in low_r:
            return "Garibaldi Plaza, Washington Square Park (Greenwich Village)"
        if "carl schurz" in low_t or "carl schurz" in low_r:
            return "Carl Schurz Park (Upper East Side)"
        if "smorgasburg" in low_t or "smorgasburg" in low_r:
            return "Smorgasburg (Williamsburg / Prospect Park)"
        if "gowanus open studios" in low_t:
            return "Gowanus Open Studios (Gowanus)"
        if "metropolitan pavilion" in low_r:
            return "Metropolitan Pavilion (Chelsea)"
        if "industry city" in low_r:
            return "Industry City (Sunset Park)"
        if "royal palms" in low_r:
            return "Royal Palms Shuffleboard Club (Gowanus)"
        if "littlefield" in low_r:
            return "Littlefield (Gowanus)"
        if "caveat" in low_r:
            return "Caveat (Lower East Side)"
        if "p+t knitwear" in low_r or "p&t knitwear" in low_r:
            return "P&T Knitwear (Lower East Side)"
        if "pete’s candy store" in low_r or "petes candy store" in low_r:
            return "Pete's Candy Store (Williamsburg)"
        if "halyards" in low_r:
            return "Halyards (Gowanus)"
        if "union hall" in low_r:
            return "Union Hall (Park Slope)"
        if "young ethel" in low_r:
            return "Young Ethel's (Park Slope)"
        if "the brick theater" in low_r or "brick theater" in low_r:
            return "The Brick Theater (Williamsburg)"
        if "mayday space" in low_r:
            return "Mayday Space (Bushwick)"
        if "cloud city" in low_r:
            return "Cloud City (Williamsburg)"
        if "secret pour" in low_r:
            return "Secret Pour (Bushwick)"
        if "cobra club" in low_r:
            return "The Cobra Club (Bushwick)"
        if "lucky 13 saloon" in low_r:
            return "Lucky 13 Saloon (Gowanus)"
        if "culture lab" in low_r:
            return "Culture Lab LIC (Long Island City)"
        if "sisters" in low_r:
            return "Sisters (Clinton Hill)"
        if "hudson yards" in low_r:
            return "Hudson Yards Public Square & Gardens"
        if "100 sutton" in low_r:
            return "100 Sutton (Greenpoint)"
        if "st. marks theatre" in low_r or "under st. marks" in low_r:
            return "Under St. Marks Theatre (East Village)"
        if "kgb bar" in low_r or "red room" in low_r:
            return "The Red Room at KGB Bar (East Village)"
        if "maria hernandez park" in low_r:
            return "Maria Hernandez Park (Bushwick)"
        if "coney island usa" in low_r or "freak bar" in low_r:
            return "Freak Bar at Coney Island USA"
        if "old stone house" in low_r:
            return "Old Stone House (Park Slope)"
        if "fashion industries" in low_r:
            return "High School of Fashion Industries (Chelsea)"
        if "st. mary the virgin" in low_r:
            return "Church of St. Mary the Virgin (Midtown)"
        if "tishman auditorium" in low_r or "new school" in low_r:
            return "The New School Tishman Auditorium (Greenwich Village)"
        if "open house new york" in low_t:
            return "Citywide (300+ Locations Across NYC)"
        if "flop house" in low_t or "flop house" in low_r:
            return "Flop House Comedy Club (Williamsburg / East Village)"
        if "hoboken" in low_t or "hoboken" in low_r:
            return "Church Square Park (Hoboken, NJ)"
        if "disability pride" in low_t:
            return "Madison Sq Park to Union Sq Park"
        if "brownstone boys" in low_t:
            return "375 Vanderbilt Ave (Clinton Hill)"
        if "muddy paws" in low_t:
            return "W 54th St between 9th & 10th Ave (Hell's Kitchen)"
        if "brooklyn navy yard" in low_t:
            return "Brooklyn Navy Yard (Building 77)"
        if "moving body" in low_t:
            return "Lincoln Center (David Rubenstein Atrium)"
        if "howl-o-ween" in low_t and "smith st" in low_r:
            return "Smith St & Union St (Carroll Gardens)"
        if "smith street neighbors" in low_t:
            return "Smith St between Bergen & Union (Carroll Gardens)"
        if "good neighbors bake sale" in low_t:
            return "Index Space (Greenpoint)"
        if "objects of times past" in low_t:
            return "432 E 9th St (East Village)"
        if "indigenous peoples" in low_t:
            return "Madison Ave & 23rd St to Broadway & 17th St (Flatiron)"
        
        m = re.search(r"([A-Za-z0-9\s&’'\.-]+?)\s*\(([^)]+)\)", rest)
        if m:
            cand_v = m.group(1).strip()
            cand_hood = m.group(2).strip()
            if not any(skip in cand_v.lower() for skip in ("weather", "note", "save", "reg", "weather permitting", "doors")):
                cand_v = re.sub(r"^.*?\b(?:at|in|inside)\s+", "", cand_v, flags=re.I).strip()
                if len(cand_v) > 3 and not cand_v.lower().startswith("the line"):
                    return f"{cand_v} ({cand_hood})"
                elif cand_hood:
                    return f"NYC ({cand_hood})"

        m_at = re.search(r"\b(?:at|@)\s+([A-Z0-9][A-Za-z0-9\s&’'\.-]+?)(?:\.|\,|\;|$)", rest)
        if m_at:
            v = m_at.group(1).strip()
            if len(v) > 3:
                return v

        return "NYC / The Skint"

    for item in soup.find_all("item")[:10]:
        post_title = item.find("title").get_text(strip=True) if item.find("title") else ""
        pub_el = item.find("pubdate") or item.find("pubDate")
        pub_str = pub_el.get_text(strip=True) if pub_el else ""
        try:
            pub_dt = datetime.strptime(pub_str[:16], "%a, %d %b %Y").replace(tzinfo=EASTERN)
        except Exception:
            pub_dt = now

        encoded = item.find("content:encoded")
        if not encoded:
            continue

        body_soup = BeautifulSoup(encoded.text, "html.parser")
        current_day = None

        if "SPONSORED" in post_title.upper() and not any(k in post_title.upper() for k in ("WEEKEND", "TUES-THURS", "MON-WED")):
            links = [a.get("href") for a in body_soup.find_all("a") if a.get("href") and not a.get("href").startswith("mailto:") and "buymeacoffee" not in a.get("href")]
            if links:
                ev_name = _clean_title(post_title.replace("(SPONSORED)", "").strip())
                ev_link = links[0]
                text_content = body_soup.get_text(" ", strip=True)
                venue = _extract_venue(text_content, ev_name)
                price = "Special Offer"
                m_p = re.search(r"(\$\d+(?:\.\d+)?|\bfree\b)", text_content, re.I)
                if m_p:
                    price = m_p.group(1).capitalize()
                cat = "theater" if any(w in ev_name.lower() for w in ("broadway", "play", "theater", "theatre")) else "community"
                key = (ev_name.lower(), pub_dt.strftime("%Y-%m-%d"))
                if key not in seen:
                    seen.add(key)
                    events.append({
                        "name": ev_name,
                        "date": pub_dt.astimezone(timezone.utc).isoformat(),
                        "venue": venue,
                        "url": ev_link,
                        "price": price,
                        "category": cat
                    })
            continue

        for el in body_soup.find_all(["p", "div", "h2", "h3", "h4"]):
            txt = el.get_text(" ", strip=True)
            lower_txt = txt.lower()

            if lower_txt in ("friday", "saturday", "sunday", "monday", "tuesday", "wednesday", "thursday"):
                current_day = lower_txt[:3]
                continue

            m_bullet = re.match(
                r"^(?:►\s*)?(?:sponsored\s*:\s*)?(fri|sat|sun|mon|tue|wed|thu|friday|saturday|sunday|monday)"
                r"(?:\s*(?:thru|\+|-)\s*(?:fri|sat|sun|mon|tue|wed|thu|friday|saturday|sunday|monday|[0-9/]+))?"
                r"\s*(.*?):(.*)$",
                txt, re.I
            )
            if not m_bullet and not ("►" in txt):
                continue

            day_prefix = None
            time_part = ""
            rest = ""

            if m_bullet:
                day_prefix = m_bullet.group(1).lower()[:3]
                time_part = m_bullet.group(2).strip()
                rest = m_bullet.group(3).strip()
            else:
                parts = txt.split(":", 2)
                if len(parts) >= 2:
                    time_part = parts[0].replace("►", "").strip()
                    rest = ":".join(parts[1:]).strip()

            event_day = day_prefix or current_day
            if not event_day:
                for d_cand in ("sat", "sun", "fri", "mon", "tue", "wed", "thu"):
                    if d_cand in time_part.lower():
                        event_day = d_cand
                        break

            if event_day in day_map:
                target_weekday = day_map[event_day]
                diff = (target_weekday - pub_dt.weekday()) % 7
                event_date = (pub_dt + timedelta(days=diff)).date()
            else:
                event_date = pub_dt.date()

            hour, minute = _parse_time(time_part)
            dt = datetime(event_date.year, event_date.month, event_date.day, hour, minute, tzinfo=EASTERN)

            b_tags = [b.get_text(strip=True) for b in el.find_all("b") if b.get_text(strip=True).lower() not in (">>", "here", "saturday", "sunday", "monday", "friday", "ongoing", "sponsored")]
            if b_tags:
                ev_title = b_tags[0]
                if any(hdr in ev_title.lower() for hdr in ("halloween dog parades", "cultural fests", "ongoing")):
                    if len(b_tags) > 1:
                        ev_title = b_tags[1]
            else:
                ev_title = rest.split(":")[0].strip()

            if not ev_title or len(ev_title) < 3 or any(hdr in ev_title.lower() for hdr in ("halloween dog parades", "cultural fests", "roundup of", "buymeacoffee")):
                continue

            ev_title = _clean_title(ev_title)

            links = [a.get("href") for a in el.find_all("a") if a.get("href") and not a.get("href").startswith("mailto:") and "buymeacoffee" not in a.get("href")]
            ev_link = links[-1] if links else "https://theskint.com"

            price = "Free / Cheap"
            m_price = re.search(r"(\$\d+(?:-\d+)?(?:\s*(?:adv|door|general|students))?|free\s*admission|free\b)", rest, re.I)
            if m_price:
                price = m_price.group(1).capitalize()

            cat = "community"
            low = (ev_title + " " + rest).lower()
            if any(w in low for w in ("comedy", "stand up", "standup", "improv", "comic")):
                cat = "comedy"
            elif any(w in low for w in ("concert", "music", "orchestra", "synth", "band", "quartet")):
                cat = "music"
            elif any(w in low for w in ("film", "movie", "screening", "cinema")):
                cat = "film"
            elif any(w in low for w in ("theatre", "theater", "musical", "play")):
                cat = "theater"
            elif any(w in low for w in ("dance party", "dj", "nightclub")):
                cat = "nightlife"
            elif any(w in low for w in ("art", "market", "bazaar", "parade", "contest", "expo", "festival")):
                cat = "community"

            venue = _extract_venue(rest, ev_title)

            days_to_add = [dt]
            if "sat + sun" in lower_txt or "sat and sun" in lower_txt:
                sun_dt = dt + timedelta(days=1)
                days_to_add.append(sun_dt)

            for event_dt in days_to_add:
                key = (ev_title.lower(), event_dt.strftime("%Y-%m-%d"))
                if key not in seen:
                    seen.add(key)
                    events.append({
                        "name": ev_title,
                        "date": event_dt.astimezone(timezone.utc).isoformat(),
                        "venue": venue,
                        "url": ev_link,
                        "price": price,
                        "category": cat
                    })

    return events


def scrape_secret_nyc(url, ua):
    """Secret NYC — trending pop-ups, immersive exhibits, and curated weekend roundups."""
    events = []
    seen = set()
    now = datetime.now(EASTERN)
    try:
        resp = _SESSION.get("https://secretnyc.co/feed/", headers={"User-Agent": ua}, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.content, "html.parser")
    except Exception:
        return events

    month_map = {
        "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
        "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12
    }

    for item in soup.find_all("item")[:10]:
        t = item.find("title").get_text(strip=True) if item.find("title") else ""
        post_link = item.find("link").get_text(strip=True) if item.find("link") else "https://secretnyc.co"
        if not post_link:
            guid = item.find("guid")
            post_link = guid.get_text(strip=True) if guid else "https://secretnyc.co"

        enc = item.find("content:encoded")
        if not enc:
            continue

        bs = BeautifulSoup(enc.text, "html.parser")

        if "things to do in nyc this weekend" in t.lower() or "things to do this weekend" in t.lower():
            m_month = re.search(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+(\d{1,2})", t, re.I)
            weekend_start = now.date()
            if m_month:
                mo_num = month_map.get(m_month.group(1).lower()[:3], now.month)
                day_num = int(m_month.group(2))
                try:
                    weekend_start = datetime(now.year, mo_num, day_num).date()
                except ValueError:
                    pass

            heading_rows = bs.find_all("div", class_="module-heading-row")
            for hr in heading_rows:
                h_el = hr.find(["h2", "h3"])
                raw_title = h_el.get_text(strip=True) if h_el else hr.get_text(strip=True)
                if not raw_title or len(raw_title) < 5:
                    continue

                p_texts = []
                links = []
                curr = hr.find_next_sibling()
                while curr and not ("module-heading-row" in (curr.get("class") or [])):
                    if curr.name == "p":
                        txt = curr.get_text(" ", strip=True)
                        if txt:
                            p_texts.append(txt)
                        for a in curr.find_all("a"):
                            href = a.get("href")
                            if href and not href.startswith("mailto:") and "instagram" not in href:
                                links.append(href)
                    curr = curr.find_next_sibling()

                full_desc = " ".join(p_texts)
                ev_date = weekend_start
                if "saturday" in full_desc.lower() or "saturday" in raw_title.lower():
                    ev_date = weekend_start + timedelta(days=(5 - weekend_start.weekday()) % 7)
                elif "sunday" in full_desc.lower() or "sunday" in raw_title.lower():
                    ev_date = weekend_start + timedelta(days=(6 - weekend_start.weekday()) % 7)
                elif "friday" in full_desc.lower() or "friday" in raw_title.lower():
                    ev_date = weekend_start + timedelta(days=(4 - weekend_start.weekday()) % 7)

                dt = datetime(ev_date.year, ev_date.month, ev_date.day, 12, 0, tzinfo=EASTERN)

                clean_name = raw_title
                clean_name = re.sub(
                    r"^(?:celebrate|check out|enjoy|go behind the scenes of|explore|grab a free|see|dive into|dive 12,000 feet underwater in|stroll through|glide into|join us in making|create your own|track|plan a day trip for the)\s+",
                    "", clean_name, flags=re.I
                ).strip(" !.")
                clean_name = clean_name[:1].upper() + clean_name[1:]

                ev_link = links[0] if links else post_link
                low = (clean_name + " " + full_desc).lower()
                cat = "community"
                if any(k in low for k in ("exhibit", "art", "museum", "gallery")):
                    cat = "art"
                elif any(k in low for k in ("concert", "music", "live set", "orchestra", "dj")):
                    cat = "music"
                elif any(k in low for k in ("parade", "dog", "halloween", "festival", "fair", "market")):
                    cat = "community"

                venue = "NYC / Secret NYC"
                m_at = re.search(r"\b(?:at|in)\s+([A-Z0-9][A-Za-z0-9\s&’'\.-]+?)(?:\.|\,|\;|$)", full_desc)
                if m_at:
                    v_cand = m_at.group(1).strip()
                    if 3 < len(v_cand) < 40 and not any(skip in v_cand.lower() for skip in ("october", "this", "addition", "order", "fact")):
                        venue = v_cand

                key = (clean_name.lower(), ev_date.strftime("%Y-%m-%d"))
                if key not in seen:
                    seen.add(key)
                    ev_obj = {
                        "name": clean_name,
                        "date": dt.astimezone(timezone.utc).isoformat(),
                        "venue": venue,
                        "url": ev_link,
                        "price": "Free / Various",
                        "category": cat
                    }
                    if _is_within_horizon(ev_obj):
                        events.append(ev_obj)
        else:
            if any(k in t.lower() for k in ("live set", "exhibition", "opens", "market", "festival", "parade", "fair", "concert", "tour")):
                dt = datetime(now.year, now.month, now.day, 19, 0, tzinfo=EASTERN)
                key = (t.lower(), dt.strftime("%Y-%m-%d"))
                if key not in seen:
                    seen.add(key)
                    ev_obj = {
                        "name": t,
                        "date": dt.astimezone(timezone.utc).isoformat(),
                        "venue": "NYC / Secret NYC",
                        "url": post_link,
                        "price": "Check link",
                        "category": "community"
                    }
                    if _is_within_horizon(ev_obj):
                        events.append(ev_obj)

    return events


def scrape_greenpointers(url, ua):
    """Greenpointers — local North Brooklyn community events, pop-ups, and weekly happenings."""
    events = []
    seen = set()
    now = datetime.now(EASTERN)
    try:
        resp = _SESSION.get("https://greenpointers.com/category/events/", headers={"User-Agent": ua}, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.content, "html.parser")
    except Exception:
        return events

    for art in soup.find_all("article")[:10]:
        h_el = art.find(["h1", "h2", "h3"])
        if not h_el:
            continue
        title = h_el.get_text(strip=True)
        a_el = art.find("a")
        link = a_el.get("href") if a_el else "https://greenpointers.com"
        time_el = art.find("time")
        date_str = time_el.get("datetime") if time_el else ""
        
        dt = now
        m = re.search(r"\((\d{1,2})/(\d{1,2})\s*-\s*(\d{1,2})\)", title)
        if m:
            mo = int(m.group(1))
            start_d = int(m.group(2))
            end_d = int(m.group(3))
            start_date = datetime(now.year, mo, start_d).date()
            end_date = datetime(now.year, mo, end_d).date()
            if start_date <= now.date() <= end_date:
                dt = now
            elif now.date() <= start_date:
                dt = datetime(now.year, mo, start_d, 12, 0, tzinfo=EASTERN)
            else:
                continue
        elif date_str:
            try:
                art_dt = datetime.fromisoformat(date_str).astimezone(EASTERN)
                if art_dt.date() >= now.date():
                    dt = art_dt
                elif (now.date() - art_dt.date()).days <= 3:
                    dt = now
                else:
                    continue
            except Exception:
                dt = now

        venue = "Greenpoint & Williamsburg (Brooklyn)"
        low = title.lower()
        if "hotel" in low or "moxy" in low:
            venue = "Moxy Hotel (Williamsburg)"
        elif "park" in low or "mcgolrick" in low:
            venue = "McGolrick Park (Greenpoint)"
        elif "mccarren" in low:
            venue = "McCarren Park (Greenpoint / Williamsburg)"

        cat = "community"
        if any(k in low for k in ("dance party", "dj", "concert", "music")):
            cat = "music"
        elif any(k in low for k in ("market", "fair", "pierogi", "food", "pumpkin")):
            cat = "community"

        key = (title.lower(), dt.strftime("%Y-%m-%d"))
        if key not in seen:
            seen.add(key)
            ev_obj = {
                "name": title,
                "date": dt.astimezone(timezone.utc).isoformat(),
                "venue": venue,
                "url": link,
                "price": "Free / Various",
                "category": cat
            }
            if _is_within_horizon(ev_obj):
                events.append(ev_obj)

    return events


def scrape_flophouse(url, ua):
    """Flop House Comedy Club — Williamsburg & East Village intimate indie comedy showcases via official JSON API."""
    events = []
    seen = set()
    venue_endpoints = [
        ("Flop House Comedy (Williamsburg)", "362 Grand St, Brooklyn, NY", "d4746cdc-a0b5-45ce-b897-afcb896b1851"),
        ("Flop House Comedy (East Village)", "201 Allen St, New York, NY", "d2a2a158-e9fa-4b6e-af68-a8bd9b57a375"),
    ]
    for loc_name, addr, vid in venue_endpoints:
        endpoint = f"https://flophousecomedy.com/venues/{vid}_events.json"
        try:
            resp = _SESSION.get(endpoint, headers={"User-Agent": ua}, timeout=10)
            if not resp.ok:
                continue
            data = resp.json()
            for show_item in data:
                show_info = show_item.get("show") or {}
                title = (show_info.get("title") or "Flop House Comedy").replace("^", "'")
                desc = show_info.get("description") or ""
                for ev in show_item.get("events") or []:
                    start_ms = ev.get("startTime")
                    if not start_ms:
                        continue
                    dt = datetime.fromtimestamp(start_ms / 1000.0, tz=timezone.utc)
                    eb_id = ev.get("eventbriteId")
                    ticket_url = f"https://www.eventbrite.com/e/tickets-{eb_id}" if eb_id else "https://flophousecomedy.com/"
                    key = (title.lower(), dt.strftime("%Y-%m-%dT%H"))
                    if key not in seen:
                        seen.add(key)
                        ev_obj = {
                            "name": title,
                            "date": dt.isoformat(),
                            "venue": loc_name,
                            "url": ticket_url,
                            "price": "$15 - $20",
                            "category": "comedy",
                        }
                        if _is_within_horizon(ev_obj):
                            events.append(ev_obj)
        except Exception:
            continue
    return events


def scrape_sesh_comedy(url, ua):
    """Sesh Comedy — Lower East Side / Chinatown live stand-up comedy club & speakeasy."""
    events = []
    seen = set()
    now = datetime.now(EASTERN)
    try:
        resp = _SESSION.get("https://seshcomedy.com/showcases.php", headers={"User-Agent": ua}, timeout=12)
        if not resp.ok:
            return events
        soup = BeautifulSoup(resp.content, "html.parser")
    except Exception:
        return events

    for card in soup.find_all("div", class_="show"):
        title = card.get("data-title") or ""
        when_str = card.get("data-when") or ""
        rel_url = card.get("data-url") or ""
        is_sold_out = card.get("data-soldout") == "true" or "sold out" in title.lower()

        if not title or not when_str:
            continue

        m = re.search(r"([A-Za-z]+),\s+([A-Za-z]+)\s+(\d{1,2})\s*—\s*(\d{1,2}):(\d{2})\s*(AM|PM)", when_str, re.I)
        if m:
            mo_str = m.group(2)[:3].lower()
            day = int(m.group(3))
            hr = int(m.group(4))
            mn = int(m.group(5))
            ampm = m.group(6).upper()
            if ampm == "PM" and hr != 12:
                hr += 12
            elif ampm == "AM" and hr == 12:
                hr = 0
            try:
                mo_num = datetime.strptime(mo_str, "%b").month
                dt = datetime(now.year, mo_num, day, hr, mn, tzinfo=EASTERN)
            except Exception:
                continue
        else:
            continue

        clean_title = re.sub(r"^\d+/\d+\s*", "", title).strip()
        ev_url = f"https://seshcomedy.com/{rel_url}" if rel_url else "https://seshcomedy.com/"
        price = "Sold Out" if is_sold_out else "$20.00 – $30.00 (BYOB)"
        key = (clean_title.lower(), dt.strftime("%Y-%m-%dT%H"))
        if key not in seen:
            seen.add(key)
            ev_obj = {
                "name": clean_title,
                "date": dt.astimezone(timezone.utc).isoformat(),
                "venue": "Sesh Comedy (Chinatown / LES)",
                "url": ev_url,
                "price": price,
                "category": "comedy",
            }
            if _is_within_horizon(ev_obj):
                events.append(ev_obj)

    return events


def scrape_ticketmaster_nyc(_url, _ua):
    """Ticketmaster Discovery API for NYC venues (MSG, Barclays, Webster Hall, Bowery, etc.)."""
    key = os.environ.get("TICKETMASTER_API_KEY") or "oo1qd0wzLe7WJpm61ALQuUCTMXGK7U5z"
    events = []
    seen = set()
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for page in range(3):
        try:
            resp = _SESSION.get(
                "https://app.ticketmaster.com/discovery/v2/events.json",
                params={
                    "apikey": key,
                    "latlong": "40.7128,-74.0060",
                    "radius": 20,
                    "unit": "miles",
                    "size": 100,
                    "page": page,
                    "sort": "date,asc",
                    "startDateTime": now_str,
                },
                timeout=15,
            )
            resp.raise_for_status()
            batch = resp.json().get("_embedded", {}).get("events", [])
            if not batch:
                break
            for ev in batch:
                name = ev.get("name")
                if is_closed_show(name):
                    continue
                status_code = (ev.get("dates", {}).get("status", {}) or {}).get("code", "").lower()
                if status_code in ("cancelled", "canceled", "postponed"):
                    continue
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
                vobj = venues[0] if venues else {}
                vname = vobj.get("name") or "NYC Venue"
                city_name = (vobj.get("city") or {}).get("name") or ""
                state_code = (vobj.get("state") or {}).get("stateCode") or ""
                if city_name and city_name.lower() not in vname.lower():
                    venue = f"{vname} ({city_name}, {state_code})" if state_code else f"{vname} ({city_name})"
                else:
                    venue = vname

                lat = None
                lng = None
                loc_coords = vobj.get("location")
                if isinstance(loc_coords, dict) and loc_coords.get("latitude") and loc_coords.get("longitude"):
                    try:
                        lat = float(loc_coords["latitude"])
                        lng = float(loc_coords["longitude"])
                    except Exception:
                        pass

                price = None
                prs = ev.get("priceRanges") or []
                if prs:
                    price = _format_price_range(prs[0].get("min"), prs[0].get("max"), prs[0].get("currency", "USD"))

                cat = "music"
                v_low = venue.lower()
                if any(cv in v_low for cv in COMEDY_VENUES):
                    cat = "comedy"
                elif any(bt in v_low for bt in BROADWAY_THEATRES) and not any(k in v_low for k in ["comedy", "film", "cinema"]):
                    cat = "theater"
                else:
                    for c in ev.get("classifications") or []:
                        seg = (c.get("segment") or {}).get("name", "").lower()
                        gnr = (c.get("genre") or {}).get("name", "").lower()
                        sub = (c.get("subGenre") or {}).get("name", "").lower()
                        combined = f"{seg} {gnr} {sub}"
                        if any(k in combined for k in ["theatre", "theater", "broadway", "musical", "play", "cabaret", "drama"]):
                            cat = "theater"
                            break
                        elif "comedy" in combined or "stand-up" in combined:
                            cat = "comedy"
                            break
                        elif "sport" in combined:
                            cat = "sports"
                            break
                        elif "dance" in combined:
                            cat = "dance"
                            break
                        elif "film" in combined or "movie" in combined:
                            cat = "film"
                            break
                        elif "art" in combined:
                            cat = "art"
                            break

                key = (ev.get("name", "").lower(), (iso or "")[:10])
                if key in seen:
                    continue
                seen.add(key)

                events.append({
                    "name": ev.get("name"),
                    "date": iso,
                    "url": ev.get("url"),
                    "venue": venue,
                    "lat": lat,
                    "lng": lng,
                    "price": price,
                    "category": guess_category(ev.get("name"), cat, venue=venue),
                })
        except Exception:
            break
    return events


def scrape_carnegie_hall_tm(_url, _ua):
    """Ticketmaster Discovery API for Carnegie Hall (Stern Auditorium, Zankel Hall, Weill Recital Hall)."""
    key = os.environ.get("TICKETMASTER_API_KEY") or "oo1qd0wzLe7WJpm61ALQuUCTMXGK7U5z"
    events = []
    seen = set()
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        resp = _SESSION.get(
            "https://app.ticketmaster.com/discovery/v2/events.json",
            params={
                "apikey": key,
                "venueId": "KovZpZA1dnJA,ZFr9jZ7kvA,ZFr9jZ117e,ZFr9jZ1kvA",
                "size": 100,
                "sort": "date,asc",
                "startDateTime": now_str,
            },
            timeout=15,
        )
        resp.raise_for_status()
        batch = resp.json().get("_embedded", {}).get("events", [])
        for ev in batch:
            name = ev.get("name")
            if not name or is_closed_show(name):
                continue
            status_code = (ev.get("dates", {}).get("status", {}) or {}).get("code", "").lower()
            if status_code in ("cancelled", "canceled", "postponed"):
                continue
            start = ev.get("dates", {}).get("start", {})
            iso = start.get("dateTime")
            if not iso and start.get("localDate"):
                try:
                    iso = datetime.fromisoformat(f"{start['localDate']}T20:00:00").replace(
                        tzinfo=EASTERN,
                    ).astimezone(timezone.utc).isoformat()
                except ValueError:
                    iso = None
            if not iso:
                continue

            venues = ev.get("_embedded", {}).get("venues") or []
            vobj = venues[0] if venues else {}
            vname = vobj.get("name") or "Carnegie Hall"
            if "carnegie hall" not in vname.lower():
                vname = f"{vname} at Carnegie Hall"

            lat = 40.7651
            lng = -73.9799
            loc_coords = vobj.get("location")
            if isinstance(loc_coords, dict) and loc_coords.get("latitude") and loc_coords.get("longitude"):
                try:
                    lat = float(loc_coords["latitude"])
                    lng = float(loc_coords["longitude"])
                except Exception:
                    pass

            price = None
            prs = ev.get("priceRanges") or []
            if prs:
                price = _format_price_range(prs[0].get("min"), prs[0].get("max"), prs[0].get("currency", "USD"))

            key_tup = (name.lower(), iso[:10])
            if key_tup in seen:
                continue
            seen.add(key_tup)

            cat = "music"
            for c in ev.get("classifications") or []:
                seg = (c.get("segment") or {}).get("name", "").lower()
                gnr = (c.get("genre") or {}).get("name", "").lower()
                if "comedy" in seg or "comedy" in gnr:
                    cat = "comedy"
                    break
                elif "theatre" in seg or "theater" in seg or "theatre" in gnr or "theater" in gnr:
                    cat = "theater"
                    break

            events.append({
                "name": name,
                "date": iso,
                "url": ev.get("url") or "https://www.carnegiehall.org/",
                "venue": vname,
                "lat": lat,
                "lng": lng,
                "price": price,
                "category": guess_category(name, cat, venue=vname),
            })
    except Exception as exc:
        print(f"Error scraping Carnegie Hall TM: {exc}")
    return events


def scrape_the_stand_nyc(url, ua):
    """Scrape live shows from The Stand NYC (thestandnyc.com/shows)."""
    soup = fetch_soup(url, ua)
    events = []
    seen = set()
    for h2 in soup.select("h2.showtitle"):
        a = h2.find("a", href=True)
        if not a:
            continue
        title = a.get_text(strip=True)
        href = a["href"].strip()
        m = re.search(r"(\d{4})-(\d{2})-(\d{2})-(\d{2})(\d{2})\d{2}", href)
        if not m or not title:
            continue
        y, mo, d, h, mi = map(int, m.groups())
        try:
            dt = datetime(y, mo, d, h, mi, tzinfo=EASTERN)
            iso = dt.astimezone(timezone.utc).isoformat()
        except ValueError:
            continue
        clean_url = href.replace("https://thestandnyc.com//", "https://thestandnyc.com/")
        if not clean_url.startswith("http"):
            clean_url = f"https://thestandnyc.com{clean_url}"
        key = (title.lower(), iso)
        if key in seen:
            continue
        seen.add(key)
        events.append({
            "name": title,
            "date": iso,
            "url": clean_url,
            "venue": "The Stand NYC",
            "lat": 40.7358,
            "lng": -73.9877,
            "price": None,
            "category": "comedy",
        })
    return events


def scrape_elsewhere_brooklyn(url, ua):
    """Elsewhere Brooklyn — multi-room live music, rooftop, and club schedules."""
    try:
        resp = _SESSION.get(url or "https://www.elsewherebrooklyn.com/calendar", headers={"User-Agent": ua or UA_CHROME}, timeout=12)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        articles = soup.find_all("article", class_=lambda c: c and "listing-compact" in c)
        events = []
        now = datetime.now(timezone.utc)
        current_year = datetime.now(EASTERN).year

        for a in articles:
            text = a.get_text(separator=" | ", strip=True)
            parts = [p.strip() for p in text.split(" | ")]
            date_str = None
            time_str = None
            title = None
            room = None

            for p in parts:
                m_date = re.search(r"\b(Mon|Tue|Wed|Thu|Fri|Sat|Sun),\s+([A-Za-z]+)\s+(\d{1,2})", p)
                if m_date:
                    date_str = p
                elif re.search(r"\b\d{1,2}:\d{2}\s*(?:AM|PM)\b", p, re.I):
                    time_str = p
                elif any(r in p.lower() for r in ["rooftop", "the hall", "zone one", "full venue"]):
                    room = p

            if len(parts) >= 2:
                title = parts[1]
            if not title or not date_str:
                continue

            time_clean = time_str if time_str else "8:00 PM"
            try:
                m_d = re.search(r"([A-Za-z]+)\s+(\d{1,2})", date_str)
                month_name, day_num = m_d.group(1), int(m_d.group(2))
                dt_raw = datetime.strptime(f"{month_name} {day_num} {current_year} {time_clean}", "%b %d %Y %I:%M %p")
                dt = dt_raw.replace(tzinfo=EASTERN).astimezone(timezone.utc)
                if dt < now:
                    continue
            except Exception:
                continue

            btn = a.find("a", href=True)
            link = btn["href"] if btn else "https://www.elsewherebrooklyn.com/calendar"
            if not link.startswith("http"):
                link = f"https://www.elsewherebrooklyn.com{link}"

            venue_label = f"Elsewhere Brooklyn ({room})" if room else "Elsewhere Brooklyn"
            events.append({
                "name": title,
                "date": dt.isoformat(),
                "url": link,
                "venue": venue_label,
                "lat": 40.7093,
                "lng": -73.9232,
                "price": None,
                "category": "clubbing",
            })
        return events
    except Exception:
        return []


def scrape_bell_house(url, ua):
    """The Bell House — Gowanus live music, podcast tapings, comedy showcases via Schema.org JSON-LD."""
    events = []
    now = datetime.now(timezone.utc)
    seen = set()
    try:
        resp = _SESSION.get(url or "https://www.thebellhouseny.com/shows", headers={"User-Agent": ua or UA_CHROME}, timeout=12)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        for s in soup.find_all("script", type="application/ld+json"):
            if not s.string:
                continue
            try:
                data = json.loads(s.string)
                if data.get("@type") in ("MusicEvent", "Event", "ComedyEvent"):
                    name = data.get("name")
                    start = data.get("startDate")
                    event_url = data.get("url") or "https://www.thebellhouseny.com/shows"
                    if not name or not start:
                        continue
                    dt = datetime.fromisoformat(start.replace("Z", "+00:00")).astimezone(timezone.utc)
                    if dt < now:
                        continue
                    key = (name.lower(), dt.date().isoformat())
                    if key in seen:
                        continue
                    seen.add(key)
                    events.append({
                        "name": name,
                        "date": dt.isoformat(),
                        "url": event_url,
                        "venue": "The Bell House",
                        "lat": 40.6738,
                        "lng": -73.9897,
                        "price": None,
                        "category": guess_category(name, "comedy", venue="The Bell House"),
                    })
            except Exception:
                continue
    except Exception:
        pass
    return events


def scrape_tiny_cupboard(url, ua):
    """The Tiny Cupboard — Bushwick indie comedy club & board game bar via Schema.org JSON-LD."""
    events = []
    now = datetime.now(timezone.utc)
    seen = set()
    try:
        resp = _SESSION.get(url or "https://www.thetinycupboard.com/calendar", headers={"User-Agent": ua or UA_CHROME}, timeout=12)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        for s in soup.find_all("script", type="application/ld+json"):
            if not s.string:
                continue
            try:
                data = json.loads(s.string)
                items = data if isinstance(data, list) else [data] if isinstance(data, dict) else []
                for it in items:
                    if it.get("@type") in ("ComedyEvent", "Event", "MusicEvent"):
                        name = it.get("name")
                        start = it.get("startDate")
                        event_url = it.get("url") or "https://www.thetinycupboard.com/calendar"
                        if not name or not start:
                            continue
                        dt = datetime.fromisoformat(start.replace("Z", "+00:00")).astimezone(timezone.utc)
                        if dt < now:
                            continue
                        key = (name.lower(), dt.isoformat())
                        if key in seen:
                            continue
                        seen.add(key)
                        events.append({
                            "name": name,
                            "date": dt.isoformat(),
                            "url": event_url,
                            "venue": "The Tiny Cupboard",
                            "lat": 40.6865,
                            "lng": -73.9098,
                            "price": None,
                            "category": "comedy",
                        })
            except Exception:
                continue
    except Exception:
        pass
    return events


def scrape_seatgeek_nyc(_url, _ua):
    """SeatGeek Discovery API for NYC — Broadway shows, major concerts, comedy, sports."""
    cid = os.environ.get("SEATGEEK_CLIENT_ID") or "MTg5NjE5MzZ8MTc3NjcwMTYxNS4yODM3MDE3"
    events = []
    seen = set()
    for page in range(1, 3):
        try:
            resp = _SESSION.get(
                "https://api.seatgeek.com/2/events",
                params={
                    "client_id": cid,
                    "lat": 40.7128,
                    "lon": -74.0060,
                    "range": "20mi",
                    "per_page": 100,
                    "page": page,
                    "sort": "datetime_local.asc",
                    "datetime_utc.gte": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
                },
                timeout=15,
            )
            resp.raise_for_status()
            batch = resp.json().get("events", [])
            if not batch:
                break
            for ev in batch:
                title = ev.get("title")
                iso = ev.get("datetime_utc")
                if not title or not iso:
                    continue
                if is_closed_show(title):
                    continue
                status = (ev.get("status") or "").lower()
                if status in ("cancelled", "canceled", "postponed"):
                    continue
                if not iso.endswith("Z") and "+" not in iso:
                    iso = iso + "Z"
                stats = ev.get("stats") or {}
                lo = stats.get("lowest_price")
                hi = stats.get("highest_price")
                price = _format_price_range(lo, hi) if lo else None
                v_obj = ev.get("venue") or {}
                vname = v_obj.get("name") or "NYC Venue"
                city = v_obj.get("city")
                state = v_obj.get("state")
                venue = f"{vname} ({city}, {state})" if city and city.lower() not in vname.lower() else vname
                v_loc = v_obj.get("location") or {}
                lat = v_loc.get("lat")
                lng = v_loc.get("lon")

                tax_names = [t.get("name", "").lower() for t in ev.get("taxonomies", [])]
                ev_type = (ev.get("type") or "").lower()
                all_tags = set(tax_names + [ev_type])
                cat = "music"
                v_low = venue.lower()
                if any(cv in v_low for cv in COMEDY_VENUES):
                    cat = "comedy"
                elif any(bt in v_low for bt in BROADWAY_THEATRES) and not any(k in v_low for k in ["comedy", "film", "cinema"]):
                    cat = "theater"
                elif any(s in all_tags for s in ["theater", "broadway", "musical", "play", "comedy_club"]):
                    if "comedy" in all_tags:
                        cat = "comedy"
                    else:
                        cat = "theater"
                elif any(s in all_tags for s in ["sports", "nba", "mlb", "nhl", "nfl", "soccer", "basketball", "baseball", "hockey"]):
                    cat = "sports"
                elif any(s in all_tags for s in ["concert", "music_festival"]):
                    cat = "music"

                key = (title.lower(), iso[:10])
                if key in seen:
                    continue
                seen.add(key)
                events.append({
                    "name": title,
                    "date": iso,
                    "url": ev.get("url"),
                    "venue": venue,
                    "lat": lat,
                    "lng": lng,
                    "price": price,
                    "category": guess_category(title, cat, venue=venue),
                })
        except Exception:
            break
    return events


def scrape_resident_advisor(url, ua):
    """Resident Advisor GraphQL API — underground electronic music, DJ sets & nightlife across NYC clubs."""
    now = datetime.now(timezone.utc)
    today_str = now.strftime("%Y-%m-%dT00:00:00.000Z")
    month_str = (now + timedelta(days=HORIZON_DAYS)).strftime("%Y-%m-%dT23:59:59.999Z")

    query = '''
    query GetEvents($pageSize: Int, $filters: FilterInputDtoInput) {
      eventListings(pageSize: $pageSize, filters: $filters) {
        totalResults
        data {
          event {
            id
            title
            startTime
            cost
            contentUrl
            venue { name address }
          }
        }
      }
    }
    '''
    headers = {
        "User-Agent": ua or UA_CHROME,
        "Content-Type": "application/json",
        "Referer": "https://ra.co/events/us/newyorkcity"
    }
    events = []
    seen = set()
    for page in range(1, 3):
        try:
            r = _SESSION.post(
                "https://ra.co/graphql",
                json={
                    "query": query,
                    "variables": {
                        "pageSize": 100,
                        "page": page,
                        "filters": {
                            "areas": {"eq": 8},
                            "listingDate": {"gte": today_str, "lte": month_str}
                        }
                    }
                },
                headers=headers,
                timeout=12
            )
            r.raise_for_status()
            data = r.json().get("data", {}).get("eventListings", {})
            for item in data.get("data", []):
                ev = item.get("event") or {}
                title = (ev.get("title") or "").strip()
                start = ev.get("startTime")
                if not title or not start:
                    continue
                v_obj = ev.get("venue") or {}
                vname = (v_obj.get("name") or "").strip() or "NYC Nightclub"
                vaddr = (v_obj.get("address") or "").strip()
                if vaddr and vname not in vaddr:
                    venue = f"{vname} ({vaddr.split(';')[0]})"
                else:
                    venue = vname

                cost = (ev.get("cost") or "").strip()
                if cost in ["0", "0.00", "0.0", "Free", "free", "Free RSVP"]:
                    price = "Free"
                elif cost and cost.lower() != "null":
                    price = cost if cost.startswith("$") else f"${cost}"
                else:
                    price = None

                content_url = ev.get("contentUrl") or ""
                ev_url = f"https://ra.co{content_url}" if content_url.startswith("/") else (content_url or "https://ra.co/events/us/newyorkcity")

                iso = start
                if not iso.endswith("Z") and "+" not in iso:
                    iso = iso + "Z"

                key = (title.lower(), iso[:10])
                if key in seen:
                    continue
                seen.add(key)

                events.append({
                    "name": title,
                    "date": iso,
                    "url": ev_url,
                    "venue": venue,
                    "price": price,
                    "category": guess_category(title, "clubbing"),
                })
        except Exception:
            break
    return events


def scrape_dice_nyc(url, ua):
    """Dice.fm — curated NYC live concerts, underground electronic, and club events."""
    events = []
    seen = set()
    try:
        resp = _SESSION.get(url or "https://dice.fm/browse/new-york", headers={"User-Agent": ua or UA_CHROME}, timeout=12)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        tag = soup.find("script", id="__NEXT_DATA__")
        if not tag or not tag.string:
            return []
        data = json.loads(tag.string)
        props = data.get("props", {}).get("pageProps", {})
        raw_events = props.get("events", [])
        for ev in raw_events:
            name = (ev.get("name") or "").strip()
            dates = ev.get("dates") or {}
            start = dates.get("event_start_date")
            if not name or not start:
                continue

            venues = ev.get("venues") or []
            vobj = venues[0] if venues else {}
            vname = (vobj.get("name") or "NYC Venue").strip()
            vcity_raw = vobj.get("city")
            if isinstance(vcity_raw, dict):
                vcity = (vcity_raw.get("name") or "").strip()
            elif isinstance(vcity_raw, str):
                vcity = vcity_raw.strip()
            else:
                vcity = ""
            venue = f"{vname} ({vcity})" if vcity and vcity.lower() not in vname.lower() else vname

            price = None
            pr_obj = ev.get("price") or {}
            amt = pr_obj.get("amount") or pr_obj.get("amount_from")
            if amt == 0 or amt == "0":
                price = "Free"
            elif amt:
                price = f"${amt / 100:.2f}".rstrip("0").rstrip(".") if isinstance(amt, (int, float)) and amt > 100 else f"${amt}"

            perm_name = ev.get("perm_name")
            event_url = f"https://dice.fm/event/{perm_name}" if perm_name else (url or "https://dice.fm/browse/new-york")

            key = (name.lower(), start[:10])
            if key in seen:
                continue
            seen.add(key)

            events.append({
                "name": name,
                "date": start,
                "url": event_url,
                "venue": venue,
                "price": price,
                "category": guess_category(name, "music"),
            })
    except Exception:
        pass
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
    api_url = f"https://www.eventbrite.com/api/v3/organizers/{org_id}/events/?order_by=start_asc&expand=venue"
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
            lat = None
            lng = None
            vobj = ev.get("venue")
            if isinstance(vobj, dict):
                vname = vobj.get("name")
                addr_obj = vobj.get("address") or {}
                loc_disp = addr_obj.get("localized_area_display") or addr_obj.get("city")
                if vname and loc_disp and loc_disp.lower() not in vname.lower():
                    vname = f"{vname} ({loc_disp})"
                if vobj.get("latitude"):
                    try:
                        lat = float(vobj["latitude"])
                        lng = float(vobj["longitude"])
                    except Exception:
                        pass
            if not vname:
                m_at = re.search(r"\bat\s+([A-Z0-9][^|(,\n]+)", name)
                if m_at:
                    vname = m_at.group(1).strip()
            events.append({
                "name": name,
                "date": dt.isoformat(),
                "url": event_url or f"https://www.eventbrite.com/o/{org_id}",
                "venue": vname,
                "lat": lat,
                "lng": lng,
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
        weeks = 2
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
            data_cat = (a.get("data-categories") or "").lower()
            lat_str = a.get("data-latitude")
            lng_str = a.get("data-longitude")
            borough_name = None
            if "brooklyn" in data_cat:
                borough_name = "Brooklyn"
            elif "queens" in data_cat:
                borough_name = "Queens"
            elif "manhattan" in data_cat:
                borough_name = "Manhattan"
            elif "bronx" in data_cat:
                borough_name = "The Bronx"
            elif "staten" in data_cat:
                borough_name = "Staten Island"

            venue_display = f"{bar_name} ({borough_name})" if borough_name else bar_name
            lat_val = None
            lng_val = None
            if lat_str and lng_str:
                try:
                    lat_val = float(lat_str)
                    lng_val = float(lng_str)
                except Exception:
                    pass

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
                    "venue": venue_display,
                    "lat": lat_val,
                    "lng": lng_val,
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


def scrape_meetup(url, ua):
    """Meetup.com — in-person community events (board games, hikes, salsa, swing, trivia)."""
    events = []
    seen = set()
    now = datetime.now(timezone.utc)
    try:
        resp = _SESSION.get(
            url,
            headers={
                "User-Agent": ua,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            },
            timeout=15,
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        for s in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(s.string)
                if not isinstance(data, list):
                    if isinstance(data, dict) and data.get("@type") == "Event":
                        data = [data]
                    else:
                        continue

                for ev in data:
                    if not isinstance(ev, dict) or ev.get("@type") != "Event":
                        continue

                    # Strict filter for in-person physical events only
                    mode = (ev.get("eventAttendanceMode") or "").lower()
                    if "online" in mode:
                        continue

                    loc = ev.get("location", {})
                    if not isinstance(loc, dict) or loc.get("@type") == "VirtualLocation":
                        continue

                    name = (ev.get("name") or "").strip()
                    if not name:
                        continue

                    # Filter out spam / virtual events masquerading as offline
                    name_lower = name.lower()
                    if any(w in name_lower for w in [
                        "zoom", "webinar", "virtual", "online event", "from home",
                        "speed dating from home", "instant zoom", "match from home"
                    ]):
                        continue

                    raw_date = ev.get("startDate")
                    if not raw_date:
                        continue
                    try:
                        dt = datetime.fromisoformat(raw_date.replace("Z", "+00:00")).astimezone(timezone.utc)
                    except Exception:
                        continue

                    if dt < now:
                        continue

                    key = (name_lower, raw_date[:10])
                    if key in seen:
                        continue
                    seen.add(key)

                    vname = (loc.get("name") or "").strip()
                    addr = loc.get("address")
                    city_hint = ""
                    region_hint = ""
                    street = ""
                    if isinstance(addr, dict):
                        street = (addr.get("streetAddress") or "").strip()
                        city_hint = (addr.get("addressLocality") or "").strip()
                        region_hint = (addr.get("addressRegion") or "").strip()
                        if not vname and street:
                            vname = f"{street}, {city_hint}" if city_hint else street
                        elif vname and street and street not in vname:
                            vname = f"{vname} ({street})"

                    if not vname or vname.lower() in ["none", "see event description", "view point", "null"]:
                        vname = f"NYC Meetup ({city_hint})" if city_hint else "NYC Community Location"

                    lat = None
                    lng = None
                    geo = loc.get("geo")
                    if isinstance(geo, dict):
                        try:
                            lat = float(geo.get("latitude"))
                            lng = float(geo.get("longitude"))
                        except Exception:
                            pass

                    # Price extraction
                    price = None
                    offers = ev.get("offers")
                    if isinstance(offers, dict):
                        p = str(offers.get("price", "")).strip()
                        if p in ["0", "0.00", "0.0", ""]:
                            price = "Free"
                        elif p:
                            price = f"${p}"
                    elif isinstance(offers, list) and offers:
                        p = str(offers[0].get("price", "")).strip()
                        if p in ["0", "0.00", "0.0", ""]:
                            price = "Free"
                        elif p:
                            price = f"${p}"
                    else:
                        price = "Free"

                    desc = (ev.get("description") or "").strip()[:250]
                    event_url = ev.get("url") or url

                    events.append({
                        "name": name,
                        "date": dt.isoformat(),
                        "url": event_url,
                        "venue": vname,
                        "lat": lat,
                        "lng": lng,
                        "price": price,
                        "description": desc,
                    })
            except Exception:
                pass
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
    ("Comedy Cellar", "https://www.comedycellar.com/new-york-line-up/", "comedy", [
        ("Comedy Cellar Showcase", "https://www.comedycellar.com/new-york-line-up/", 0, 20, 0),
        ("Comedy Cellar Showcase", "https://www.comedycellar.com/new-york-line-up/", 1, 20, 0),
        ("Comedy Cellar Showcase", "https://www.comedycellar.com/new-york-line-up/", 2, 20, 0),
        ("Comedy Cellar Showcase", "https://www.comedycellar.com/new-york-line-up/", 3, 20, 0),
        ("Comedy Cellar Showcase", "https://www.comedycellar.com/new-york-line-up/", 4, 20, 0),
        ("Comedy Cellar Showcase", "https://www.comedycellar.com/new-york-line-up/", 5, 20, 0),
        ("Comedy Cellar Showcase", "https://www.comedycellar.com/new-york-line-up/", 6, 20, 0),
    ]),
    ("Gotham Comedy Club", "https://www.gothamcomedyclub.com/", "comedy", [
        ("Gotham Comedy Live Showcase", "https://www.gothamcomedyclub.com/", 3, 20, 0),
        ("Gotham All-Stars Showcase", "https://www.gothamcomedyclub.com/", 4, 20, 0),
        ("Gotham All-Stars Showcase", "https://www.gothamcomedyclub.com/", 5, 20, 0),
        ("Gotham All-Stars Showcase", "https://www.gothamcomedyclub.com/", 6, 19, 30),
    ]),
    ("Gonzalez y Gonzalez", "https://www.gygnyc.com/", "dance", [
        ("Live Salsa Band & Dance Party", "https://www.gygnyc.com/", 3, 21, 0, "Free Lesson"),
        ("Live Salsa Band & Dance Party", "https://www.gygnyc.com/", 4, 21, 0, "Live Band"),
        ("Live Salsa Band & Dance Party", "https://www.gygnyc.com/", 5, 21, 0, "Live Band"),
    ]),
    ("Taj Lounge (OOO)", "https://www.ooonewyork.com/", "dance", [
        ("Taj Monday Night Salsa & Bachata Social", "https://www.ooonewyork.com/", 0, 19, 0, "Dance Lesson & Social"),
    ]),
    ("Club Cache", "https://www.instagram.com/clubcachenyc/", "dance", [
        ("Club Cache Thursday Salsa & Bachata Social", "https://www.instagram.com/clubcachenyc/", 3, 20, 0, "Dance Class & Social"),
        ("Club Cache Saturday Latin Dance Party", "https://www.instagram.com/clubcachenyc/", 5, 20, 0, "Dance Class & Social"),
    ]),
    ("Iguana NYC", "https://www.iguananewyork.com/", "dance", [
        ("Iguana Latin Dance & Salsa Lounge", "https://www.iguananewyork.com/", 2, 20, 0, "No Cover / Latin Lounge"),
        ("Iguana Latin Dance & Salsa Lounge", "https://www.iguananewyork.com/", 3, 20, 0, "No Cover / Latin Lounge"),
        ("Iguana Latin Dance & Salsa Lounge", "https://www.iguananewyork.com/", 4, 20, 0, "Latin Dance Upstairs"),
        ("Iguana Latin Dance & Salsa Lounge", "https://www.iguananewyork.com/", 5, 20, 0, "Latin Dance Upstairs"),
    ]),
    ("S.O.B.'s (Sounds of Brazil)", "https://sobs.com/", "dance", [
        ("Live Salsa Orchestra & Latin Dance Party", "https://sobs.com/", 4, 22, 0, "Live Band & Dancing"),
        ("Live Salsa Orchestra & Latin Dance Party", "https://sobs.com/", 5, 22, 0, "Live Band & Dancing"),
    ]),
    ("Cucala Dance Company", "https://www.cucaladance.com/", "dance", [
        ("Friday Night Salsa Social & Workshops", "https://www.cucaladance.com/", 4, 20, 0, "Dance Lesson & Social"),
    ]),
    ("Salsa Salsa Dance Studios", "https://www.instagram.com/salsasalsanyc/", "dance", [
        ("Brooklyn Salsa Social & Practice Party", "https://www.instagram.com/salsasalsanyc/", 4, 20, 0, "Practice Social"),
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
    ("Vanderbilt Open Streets (Brooklyn)", "https://www.instagram.com/salsasalsanyc/", "dance", [
        ("Salsa Salsa on Vanderbilt Open Streets (Free Class & Social)", "https://www.instagram.com/salsasalsanyc/", 5, 17, 0, "Free"),
    ]),
    ("Abolitionist Place Park (Downtown Brooklyn)", "https://www.instagram.com/salsasalsanyc/", "dance", [
        ("Abolitionist Place Park Outdoor Salsa & Bachata Social", "https://www.instagram.com/salsasalsanyc/", 6, 16, 0, "Free"),
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
    ("You Should Be Dancing (YSBD)", "https://www.instagram.com/youshouldbedancingnyc/", "dance", [
        ("Frim Fram Jam (Intro Swing Lesson & Social Dance)", "http://www.frimframjam.com/", 3, 20, 30, "$15–$25"),
        ("Saturday Night Swings (Live Big Band & Lesson)", "https://www.instagram.com/youshouldbedancingnyc/", 5, 19, 15, "$25–$30"),
        ("Social Swing Dance & Practice Session", "https://www.instagram.com/youshouldbedancingnyc/", 1, 19, 0, "$5"),
    ]),
    ("Danznik Studios", "https://midtownswings.com/", "dance", [
        ("Midtown Swings (Intro Lindy Hop & DJ Social)", "https://midtownswings.com/", 1, 21, 0, "$15–$25"),
    ]),
    ("The Keep (Bushwick)", "https://thisweekinswingnyc.com/", "dance", [
        ("Positively Swingin' (Live Band & Warm-up Lesson)", "https://thisweekinswingnyc.com/", 2, 19, 30, "No Cover"),
    ]),
    ("Hungarian House (Blues Dance NY)", "https://www.bluesdancenewyork.com/", "dance", [
        ("Friday Night Blues (Live Blues Band & Lesson)", "https://www.bluesdancenewyork.com/", 4, 20, 0, "$20–$35"),
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
    ("Bossa Nova Civic Club", "https://www.instagram.com/bossanovacivicclub/", "clubbing", [
        ("Techno & House Sessions (Free Before 11PM)", "https://www.instagram.com/bossanovacivicclub/", 0, 22, 0, "Free before 11PM"),
        ("Techno & House Sessions (Free Before 11PM)", "https://www.instagram.com/bossanovacivicclub/", 1, 22, 0, "Free before 11PM"),
        ("Techno & House Sessions (Free Before 11PM)", "https://www.instagram.com/bossanovacivicclub/", 2, 22, 0, "Free before 11PM"),
        ("Techno & House Sessions (Free Before 11PM)", "https://www.instagram.com/bossanovacivicclub/", 3, 22, 0, "Free before 11PM"),
        ("Techno & House Sessions (Free Before 11PM)", "https://www.instagram.com/bossanovacivicclub/", 4, 22, 0, "Free before 11PM"),
        ("Techno & House Sessions (Free Before 11PM)", "https://www.instagram.com/bossanovacivicclub/", 5, 22, 0, "Free before 11PM"),
        ("Techno & House Sessions (Free Before 11PM)", "https://www.instagram.com/bossanovacivicclub/", 6, 22, 0, "Free before 11PM"),
    ]),
    ("Jupiter Disco", "https://www.jupiterdisco.com/", "clubbing", [
        ("Analog Synth & Underground DJ Night", "https://www.jupiterdisco.com/", 3, 20, 0, "No Cover"),
        ("Analog Synth & Underground DJ Night", "https://www.jupiterdisco.com/", 4, 20, 0, "No Cover"),
        ("Analog Synth & Underground DJ Night", "https://www.jupiterdisco.com/", 5, 20, 0, "No Cover"),
        ("Analog Synth & Underground DJ Night", "https://www.jupiterdisco.com/", 6, 20, 0, "No Cover"),
    ]),
]


def _expand_manual_recurring(weeks=2):
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
    {"name": "Secret NYC", "url": "https://secretnyc.co/", "ua": UA_CHROME, "scraper": scrape_secret_nyc, "default_category": "community"},
    {"name": "Greenpointers Brooklyn", "url": "https://greenpointers.com/", "ua": UA_CHROME, "scraper": scrape_greenpointers, "default_category": "community"},
    {"name": "Ticketmaster NYC", "url": "https://www.ticketmaster.com/", "ua": UA_CHROME, "scraper": scrape_ticketmaster_nyc, "default_category": "music"},
    {"name": "SeatGeek NYC", "url": "https://api.seatgeek.com/2/events", "ua": UA_CHROME, "scraper": scrape_seatgeek_nyc, "default_category": None},
    {"name": "Resident Advisor NYC", "url": "https://ra.co/events/us/newyorkcity", "ua": UA_CHROME, "scraper": scrape_resident_advisor, "default_category": "clubbing"},
    {"name": "Dice.fm NYC", "url": "https://dice.fm/browse/new-york", "ua": UA_CHROME, "scraper": scrape_dice_nyc, "default_category": "music"},

    # Brooklyn Music & Nightlife
    {"name": "Brooklyn Bowl", "url": "https://donyc.com/venues/brooklyn-bowl", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "music"},
    {"name": "Elsewhere Brooklyn", "url": "https://www.elsewherebrooklyn.com/calendar", "ua": UA_CHROME, "scraper": scrape_elsewhere_brooklyn, "default_category": "clubbing"},
    {"name": "Knockdown Center", "url": "https://donyc.com/venues/knockdown-center", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "music"},
    {"name": "Good Room Greenpoint", "url": "https://donyc.com/venues/good-room", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "clubbing"},
    {"name": "TV Eye Ridgewood", "url": "https://donyc.com/venues/tv-eye", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "music"},
    {"name": "Public Records Gowanus", "url": "https://donyc.com/venues/public-records", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "clubbing"},
    {"name": "The Bell House", "url": "https://www.thebellhouseny.com/shows", "ua": UA_CHROME, "scraper": scrape_bell_house, "default_category": "comedy"},
    {"name": "Littlefield Brooklyn", "url": "https://www.eventbrite.com/api/v3/organizers/18046024060/events/?order_by=start_asc", "ua": UA_CHROME, "scraper": scrape_eventbrite_organizer, "default_category": "comedy"},
    {"name": "Music Hall of Williamsburg", "url": "https://donyc.com/venues/music-hall-of-williamsburg", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "music"},
    {"name": "Brooklyn Steel", "url": "https://donyc.com/venues/brooklyn-steel", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "music"},
    {"name": "Warsaw Brooklyn", "url": "https://donyc.com/venues/warsaw", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "music"},
    {"name": "Barclays Center", "url": "https://donyc.com/venues/barclays-center", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "sports"},
    {"name": "Kings Theatre Flatbush", "url": "https://donyc.com/venues/kings-theatre", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "music"},
    {"name": "Baby's All Right Williamsburg", "url": "https://donyc.com/venues/baby-s-all-right", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "music"},
    {"name": "The Sultan Room Bushwick", "url": "https://donyc.com/venues/the-sultan-room", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "music"},
    {"name": "Pioneer Works Red Hook", "url": "https://donyc.com/venues/pioneer-works", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "art"},
    {"name": "C'mon Everybody Bed-Stuy", "url": "https://donyc.com/venues/c-mon-everybody", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "music"},
    {"name": "Brooklyn Made", "url": "https://www.eventbrite.com/d/ny--brooklyn/brooklyn-made/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "music"},
    {"name": "Market Hotel", "url": "https://donyc.com/venues/market-hotel", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "music"},
    {"name": "SILO Brooklyn", "url": "https://donyc.com/venues/silo-brooklyn", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "clubbing"},
    {"name": "Avant Gardner", "url": "https://donyc.com/venues/avant-gardner", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "clubbing"},
    {"name": "Brooklyn Mirage", "url": "https://donyc.com/venues/the-brooklyn-mirage", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "clubbing"},
    {"name": "Basement NY", "url": "https://donyc.com/venues/basement-ny", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "clubbing"},

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
    {"name": "Carnegie Hall", "url": "https://www.carnegiehall.org/Events", "ua": UA_CHROME, "scraper": scrape_carnegie_hall_tm, "default_category": "music"},
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

    # Indie Cinemas, Micro-Theaters & Film Programs
    {"name": "Film Forum", "url": "https://donyc.com/venues/film-forum", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "film"},
    {"name": "Nitehawk Cinema", "url": "https://donyc.com/venues/nitehawk-cinema", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "film"},
    {"name": "IFC Center", "url": "https://donyc.com/venues/ifc-center", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "film"},
    {"name": "Film at Lincoln Center", "url": "https://donyc.com/venues/film-at-lincoln-center", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "film"},
    {"name": "NYC Indie Film & Screenings", "url": "https://www.eventbrite.com/d/ny--new-york/indie-film/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "film"},
    {"name": "Metrograph NYC Screenings", "url": "https://www.eventbrite.com/d/ny--new-york/metrograph/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "film"},
    {"name": "Rooftop Films & Outdoor Cinema", "url": "https://www.eventbrite.com/d/ny--new-york/rooftop-films/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "film"},
    {"name": "Union Hall Brooklyn", "url": "https://www.eventbrite.com/api/v3/organizers/17899496497/events/?order_by=start_asc", "ua": UA_CHROME, "scraper": scrape_eventbrite_organizer, "default_category": "comedy"},
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
    {"name": "The Stand NYC", "url": "https://thestandnyc.com/shows", "ua": UA_CHROME, "scraper": scrape_the_stand_nyc, "default_category": "comedy"},
    {"name": "Tight Pants Comedy", "url": "https://www.eventbrite.com/api/v3/organizers/58671695943/events/?order_by=start_asc", "ua": UA_CHROME, "scraper": scrape_eventbrite_organizer, "default_category": "comedy"},
    {"name": "Broadway Comedy Club", "url": "https://www.eventbrite.com/d/ny--new-york/broadway-comedy-club/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "comedy"},
    {"name": "EastVille Comedy Club", "url": "https://donyc.com/venues/eastville-comedy-club", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "comedy"},
    {"name": "Greenwich Village Comedy Club", "url": "https://www.eventbrite.com/d/ny--new-york/greenwich-village-comedy-club/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "comedy"},
    {"name": "The Grisly Pear Comedy Club", "url": "https://www.eventbrite.com/d/ny--new-york/grisly-pear-comedy/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "comedy"},
    {"name": "St. Marks Comedy Club", "url": "https://www.eventbrite.com/d/ny--new-york/st-marks-comedy-club/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "comedy"},
    {"name": "Q.E.D. Astoria (Comedy & Arts)", "url": "https://www.eventbrite.com/d/ny--astoria/qed/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "comedy"},
    {"name": "New York Comedy Club", "url": "https://www.eventbrite.com/d/ny--new-york/new-york-comedy-club/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "comedy"},
    {"name": "The Tiny Cupboard (Bushwick Rooftop Comedy)", "url": "https://www.thetinycupboard.com/calendar", "ua": UA_CHROME, "scraper": scrape_tiny_cupboard, "default_category": "comedy"},
    {"name": "Brooklyn Comedy Collective (Eris Mainstage)", "url": "https://www.eventbrite.com/api/v3/organizers/27620063469/events/?order_by=start_asc", "ua": UA_CHROME, "scraper": scrape_eventbrite_organizer, "default_category": "comedy"},

    # Free Events Aggregators & Citywide Parks
    {"name": "NYC Parks Free Public Events", "url": "https://www.nycgovparks.org/xml/events_300_rss.xml", "ua": UA_CHROME, "scraper": scrape_nyc_parks, "default_category": "outdoors"},
    {"name": "Central Park Conservancy Events", "url": "https://www.eventbrite.com/d/ny--new-york/central-park/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "outdoors"},
    {"name": "Prospect Park Alliance Events", "url": "https://www.eventbrite.com/d/ny--brooklyn/prospect-park/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "outdoors"},
    {"name": "Brooklyn Bridge Park Events", "url": "https://www.eventbrite.com/d/ny--brooklyn/brooklyn-bridge-park/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "outdoors"},
    {"name": "Hudson River Park Events", "url": "https://www.eventbrite.com/d/ny--new-york/hudson-river-park/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "outdoors"},
    {"name": "NYC for FREE (Pop-ups & Experiences)", "url": "https://www.nycforfree.co/events", "ua": UA_CHROME, "scraper": scrape_nyc_for_free, "default_category": "community"},
    {"name": "NYC Pop-Up Experiences & Activations", "url": "https://www.eventbrite.com/d/ny--new-york/pop-up/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "community"},
    {"name": "Hudson Yards Events & Activations", "url": "https://www.eventbrite.com/d/ny--new-york/hudson-yards/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "community"},
    {"name": "The Shed (Hudson Yards)", "url": "https://www.eventbrite.com/d/ny--new-york/the-shed/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "theater"},
    {"name": "Union Square Events & Gatherings", "url": "https://www.eventbrite.com/d/ny--new-york/union-square/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "community"},
    {"name": "Lincoln Center Events & Tours", "url": "https://www.eventbrite.com/d/ny--new-york/lincoln-center/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "theater"},
    {"name": "Jazz at Lincoln Center", "url": "https://www.eventbrite.com/d/ny--new-york/jazz-at-lincoln-center/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "music"},
    {"name": "Meetup: NYC Hikes & Nature Walks", "url": "https://www.meetup.com/find/?keywords=hiking&location=us--ny--New%20York&source=EVENTS", "ua": UA_CHROME, "scraper": scrape_meetup, "default_category": "outdoors"},
    {"name": "Meetup: Outdoor Hikes & Trails", "url": "https://www.meetup.com/find/?keywords=hike&location=us--ny--New%20York&source=EVENTS", "ua": UA_CHROME, "scraper": scrape_meetup, "default_category": "outdoors"},

    # Fashion, Sample Sales, Talks & Social Connection
    {"name": "NYC Fashion Events & Sample Sales", "url": "https://www.eventbrite.com/d/ny--new-york/sample-sale/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "community"},
    {"name": "NYC Fashion Shows & Runway", "url": "https://www.eventbrite.com/d/ny--new-york/fashion-show/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "community"},
    {"name": "NYC Talks & Lectures", "url": "https://www.eventbrite.com/d/ny--new-york/talks/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "community"},
    {"name": "NYC Panel Discussions & Symposiums", "url": "https://www.eventbrite.com/d/ny--new-york/panel-discussion/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "community"},
    {"name": "Skip the Small Talk NYC", "url": "https://www.eventbrite.com/d/ny--new-york/skip-the-small-talk/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "community"},

    # Literary Cafes, Book Bars, Breweries & Neighborhood Hubs
    {"name": "Bibliothèque Wine & Book Bar", "url": "https://www.eventbrite.com/d/ny--new-york/bibliotheque/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "books"},
    {"name": "Liz's Book Bar (Carroll Gardens)", "url": "https://www.eventbrite.com/d/ny--brooklyn/lizs-book-bar/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "books"},
    {"name": "Threes Brewing (Gowanus & Greenpoint)", "url": "https://www.eventbrite.com/d/ny--brooklyn/threes-brewing/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "food"},
    {"name": "Flop House Comedy Club", "url": "https://flophousecomedy.com/", "ua": UA_CHROME, "scraper": scrape_flophouse, "default_category": "comedy"},
    {"name": "Sesh Comedy (Chinatown / LES)", "url": "https://seshcomedy.com/showcases.php", "ua": UA_CHROME, "scraper": scrape_sesh_comedy, "default_category": "comedy"},

    # Super Smash Bros (SSB), Arcades & Tabletop Gaming
    {"name": "OS NYC (Super Smash Bros & Gaming)", "url": "https://www.os-nyc.com/events?format=json", "ua": UA_CHROME, "scraper": scrape_squarespace_calendar, "default_category": "gaming"},
    {"name": "Wonderville (Indie Arcade & Smashville)", "url": "https://www.wonderville.nyc/events?format=json", "ua": UA_CHROME, "scraper": scrape_squarespace_calendar, "default_category": "gaming"},
    {"name": "Hex & Company (Board Games & RPG)", "url": "https://www.eventbrite.com/d/ny--new-york/hex-and-company/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "gaming"},
    {"name": "The Uncommons (Board Game Cafe)", "url": "https://www.eventbrite.com/d/ny--new-york/the-uncommons/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "gaming"},
    {"name": "The Brooklyn Strategist", "url": "https://www.eventbrite.com/d/ny--brooklyn/the-brooklyn-strategist/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "gaming"},
    {"name": "Meetup: NYC Board Game Nights", "url": "https://www.meetup.com/find/?keywords=board%20games&location=us--ny--New%20York&source=EVENTS", "ua": UA_CHROME, "scraper": scrape_meetup, "default_category": "gaming"},
    {"name": "Meetup: Tabletop & RPG Games", "url": "https://www.meetup.com/find/?keywords=tabletop%20games&location=us--ny--New%20York&source=EVENTS", "ua": UA_CHROME, "scraper": scrape_meetup, "default_category": "gaming"},
    {"name": "Meetup: NYC Bar Trivia Nights", "url": "https://www.meetup.com/find/?keywords=trivia&location=us--ny--New%20York&source=EVENTS", "ua": UA_CHROME, "scraper": scrape_meetup, "default_category": "gaming"},

    # Nightlife, Immersive Spectacle & Theatrical Circus
    {"name": "House of Yes (Circus & Dance)", "url": "https://donyc.com/venues/house-of-yes", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "party"},
    {"name": "House of Yes (Brooklyn Spectacle)", "url": "https://www.eventbrite.com/d/ny--brooklyn/house-of-yes/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "theater"},
    {"name": "The Slipper Room (NYC Burlesque)", "url": "https://donyc.com/venues/the-slipper-room", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "theater"},
    {"name": "NYC Burlesque Shows & Cabaret", "url": "https://www.eventbrite.com/d/ny--new-york/burlesque/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "theater"},

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
    {"name": "Meetup: NYC Social Dance & Salsa", "url": "https://www.meetup.com/find/?keywords=salsa%20dancing&location=us--ny--New%20York&source=EVENTS", "ua": UA_CHROME, "scraper": scrape_meetup, "default_category": "dance"},

    # Swing Dancing, Lindy Hop & Blues
    {"name": "This Week in Swing NYC", "url": "https://thisweekinswingnyc.com/wp-json/wp/v2/posts?per_page=5", "ua": UA_CHROME, "scraper": scrape_thisweekinswingnyc, "default_category": "dance"},
    {"name": "NYC Swing Dancing & Lindy Hop", "url": "https://www.eventbrite.com/d/ny--new-york/swing-dancing/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "dance"},
    {"name": "Frim Fram Jam (YSBD Swing)", "url": "https://www.eventbrite.com/d/ny--new-york/frim-fram-jam/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "dance"},
    {"name": "Prohibition Productions (Gotham Jazz)", "url": "https://www.eventbrite.com/d/ny--new-york/prohibition-productions/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "dance"},
    {"name": "Meetup: NYC Swing Dancing", "url": "https://www.meetup.com/find/?keywords=swing%20dance&location=us--ny--New%20York&source=EVENTS", "ua": UA_CHROME, "scraper": scrape_meetup, "default_category": "dance"},

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
    ("outdoors","Meetup NYC Hiking & Trail Groups", "https://www.meetup.com/find/?keywords=hiking&location=us--ny--New%20York&source=EVENTS"),
    ("gaming",  "Meetup NYC Board Games & Tabletop", "https://www.meetup.com/find/?keywords=board%20games&location=us--ny--New%20York&source=EVENTS"),
    ("dance",   "Meetup NYC Salsa & Social Dance Groups", "https://www.meetup.com/find/?keywords=salsa%20dancing&location=us--ny--New%20York&source=EVENTS"),
    ("comedy",  "Comedy Cellar Nightly Lineups", "https://www.comedycellar.com/new-york-line-up/"),
    ("comedy",  "The Stand NYC Live Lineups & Dinners", "https://thestandnyc.com/shows"),
    ("comedy",  "Gotham Comedy Club Lineups & Headliners", "https://www.gothamcomedyclub.com/"),
    ("comedy",  "EastVille Comedy Club Lineups (Brooklyn)", "https://www.eastvillecomedy.com/"),
    ("comedy",  "Broadway Comedy Club Lineups (Times Square)", "https://broadwaycomedyclub.com/"),
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
    ("dance",   "Taj Lounge (Monday Night Salsa & Bachata Social)", "https://www.ooonewyork.com/"),
    ("dance",   "Club Cache (Thursday & Saturday Salsa Socials)", "https://www.instagram.com/clubcachenyc/"),
    ("dance",   "Iguana NYC (Latin Dance & Salsa Lounge)", "https://www.iguananewyork.com/"),
    ("dance",   "Cucala Dance Company (East Village Salsa Classes)", "https://www.cucaladance.com/"),
    ("dance",   "Salsa Salsa Dance Studios (Brooklyn Latin Dance)", "https://www.instagram.com/salsasalsanyc/"),
    ("dance",   "Hudson River Park Sunset Salsa (Pier 45 & Pier 76)", "https://hudsonriverpark.org/event-series/dance-in-hrpk/"),
    ("dance",   "Washington Square Park Garibaldi Plaza Salsa Social", "https://www.nycgovparks.org/events/dance"),
    ("dance",   "Bryant Park Dance Party (Outdoor Salsa & Latin)", "https://bryantpark.org/activities/dance-party"),
    ("dance",   "Pa' La Calle NYC (Bella Abzug Park Hudson Yards Salsa)", "https://www.somoslatindance.com/palacallenyc"),
    ("dance",   "Salsa Salsa Outdoor Series (Vanderbilt Open Streets & Abolitionist Place)", "https://www.instagram.com/salsasalsanyc/"),
    ("dance",   "Hunters Point South Park Waterfront Salsa", "https://www.hunterspointparks.org/"),
    ("dance",   "Domino Park Waterfront Salsa & Latin Nights", "https://www.dominopark.com/"),
    ("dance",   "The Back Room (Monday Night Live Jazz & Swing)", "https://www.backroomnyc.com/"),
    ("dance",   "This Week in Swing NYC (Weekly Lindy Hop & Blues Calendar)", "https://thisweekinswingnyc.com/"),
    ("dance",   "Frim Fram Jam / YSBD (Thursday Weekly Swing Dance)", "http://www.frimframjam.com/"),
    ("dance",   "Midtown Swings at Danznik Studios (Tuesday Lindy Hop)", "https://midtownswings.com/"),
    ("dance",   "Swing Remix (Upper West Side Live Big Bands)", "https://swingremix.com/"),
    ("dance",   "Blues Dance New York (Hungarian House Blues)", "https://www.bluesdancenewyork.com/"),
    ("dance",   "Harlem Swing Dance Society", "http://www.theharlemswingdancesociety.org/"),
    ("dance",   "Prohibition Productions (Gotham Jazz & The Salon)", "https://prohibitionproductions.com/"),
    ("dance",   "The Keep Bushwick (Positively Swingin' Wednesdays)", "https://thisweekinswingnyc.com/"),
    ("dance",   "The Last Word Astoria (Astoria Swing Dance)", "https://thisweekinswingnyc.com/"),
    ("theater", "3 Dollar Bill (Bushwick Queer & Drag Hall)", "https://www.3dollarbillbk.com/"),
    ("gaming",  "Trivia A.D. (NYC Bar Pop Culture Trivia Nights)", "https://triviaad.com/"),
    ("clubbing","Somewhere Nowhere NYC (Chelsea Rooftop Club & Lounge)", "https://somewherenowherenyc.com/"),
    ("clubbing","The DL (LES Multi-Level Rooftop Club)", "https://thedl-nyc.com/"),
    ("clubbing","Harbor NYC (Hell's Kitchen Rooftop Nightclub)", "https://harbornewyorkcity.com/"),
    ("clubbing","Superior Ingredients (Williamsburg Roof & Room)", "https://si-bk.com/"),
    ("clubbing","Bossa Nova Civic Club (Bushwick Underground Techno)", "https://www.instagram.com/bossanovacivicclub/"),
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
    ("Superior Ingredients (Free RSVP House & Techno before 11 PM)", "https://si-bk.com/"),
    ("Bossa Nova Civic Club (Free Entry Before 11 PM Nightly)", "https://www.instagram.com/bossanovacivicclub/"),
    ("Jupiter Disco (Always Free / No Cover Retro DJs)", "https://www.jupiterdisco.com/"),
    ("NYC Club Guestlists (Live Eventbrite Free Guestlists)", "https://www.eventbrite.com/d/ny--new-york/free-guestlist/"),
    ("NYC Ferry Tickets ($4.00 per ride)", "https://www.ferry.nyc/"),
]


# --- Cache & Scraper Aggregator ---
_cache = {"ts": 0, "data": None}


def _scrape_one(v, force=False):
    vname = v["name"]
    ttl = _get_venue_ttl(vname)

    # 1. Check if cached data exists and is within TTL
    if not force:
        cached = _load_venue_cache(vname, max_age=ttl)
        if cached and cached.get("events") is not None:
            events = [e for e in cached["events"] if _is_within_horizon(e, max_days=HORIZON_DAYS) and not is_closed_show(e.get("name"))]
            return {
                "venue": vname,
                "url": v["url"],
                "events": events,
                "error": None,
                "duration": cached.get("duration", 0.0),
                "cached": True,
            }

    # 2. Scrape live from external endpoint
    t0 = time.time()
    try:
        events = v["scraper"](v["url"], v["ua"])
        events = [e for e in events if not is_closed_show(e.get("name"))]
        for e in events:
            if not e.get("venue"):
                e["venue"] = vname
            existing_cat = e.get("category")
            if not existing_cat or existing_cat == "other":
                e["category"] = guess_category(e.get("name"), v.get("default_category") or "community", venue=e.get("venue"))
            else:
                e["category"] = guess_category(e.get("name"), existing_cat, venue=e.get("venue"))

        dur = round(time.time() - t0, 2)
        # Save raw parsed events to cache before horizon filtering
        _save_venue_cache(vname, events, duration=dur)

        # Filter events to 14-day rolling window
        events = [e for e in events if _is_within_horizon(e, max_days=HORIZON_DAYS)]
        return {
            "venue": vname,
            "url": v["url"],
            "events": events,
            "error": None,
            "duration": dur,
            "cached": False,
        }
    except Exception as exc:
        # Error resilience: fall back to existing cache if network/Cloudflare fails
        stale_cache = _load_venue_cache(vname, max_age=None)
        if stale_cache and stale_cache.get("events"):
            events = [e for e in stale_cache["events"] if _is_within_horizon(e, max_days=HORIZON_DAYS) and not is_closed_show(e.get("name"))]
            return {
                "venue": vname,
                "url": v["url"],
                "events": events,
                "error": f"{exc} (serving stale cache)",
                "duration": round(time.time() - t0, 2),
                "cached": True,
            }
        return {
            "venue": vname,
            "url": v["url"],
            "events": [],
            "error": str(exc),
            "duration": round(time.time() - t0, 2),
            "cached": False,
        }


def get_all_events(force=False):
    now = time.time()
    if not force and _cache["data"] and (now - _cache["ts"] < CACHE_SECONDS):
        return _cache["data"]

    def _worker(v):
        return _scrape_one(v, force=force)

    with ThreadPoolExecutor(max_workers=10) as ex:
        results = list(ex.map(_worker, VENUES))

    # Add recurring events (expanded for 2 weeks / 14 days)
    results.extend(_expand_manual_recurring(weeks=2))

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "venues": results,
        "weather": fetch_nyc_weather(),
        "luckyseat": fetch_luckyseat_nyc(),
    }
    _cache["ts"] = now
    _cache["data"] = payload
    return payload
