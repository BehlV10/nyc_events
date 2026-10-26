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
from urllib.parse import parse_qs, quote, quote_plus, urlencode, urljoin, urlparse, urlunparse
from zoneinfo import ZoneInfo
import warnings

import requests
from requests.adapters import HTTPAdapter
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

CACHE_SECONDS = 15 * 60
EASTERN = ZoneInfo("America/New_York")
HORIZON_DAYS = 35

CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".cache", "venues")
os.makedirs(CACHE_DIR, exist_ok=True)

DEFAULT_VENUE_TTL = 3 * 3600    # 3 hours for standard venue feeds
FAST_VENUE_TTL = 1 * 3600       # 1 hour for high-turnover feeds (Ticketmaster, SeatGeek, RA, Dice, DoNYC)
SLOW_VENUE_TTL = 12 * 3600      # 12 hours for evergreen/slow feeds (NYC Parks XML, Trivia, Bookstores)
EVENTBRITE_TTL = 6 * 3600       # 6 hours for Eventbrite feeds to prevent Cloudflare bot blocking


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


def _get_venue_ttl(vname, v=None):
    low = (vname or "").lower()
    url = (v.get("url") if isinstance(v, dict) else "") or ""
    if "eventbrite.com" in url or "eventbrite" in low:
        return EVENTBRITE_TTL
    if any(k in low for k in ["ticketmaster", "seatgeek", "resident advisor", "dice.fm", "donyc", "the skint", "secret nyc", "greenpointers", "flop house", "sesh comedy", "luma"]):
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
        # Upgrade any legacy cached events that still point to donyc.com
        for ev in cached.get("events", []):
            u = ev.get("url") or ""
            if "donyc.com" in u:
                t = ev.get("ticket_url")
                if t and "donyc.com" not in t:
                    ev["url"] = t
                else:
                    v_str = ev.get("venue") or vname or ""
                    q_str = f"{ev.get('name', '')} {v_str} NYC".strip()
                    ev["url"] = f"https://www.google.com/search?q={quote_plus(q_str)}"
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
    "lincoln center theater", "new york city center", "city center",
    "james earl jones", "james earl jones theatre", "cort theatre",
    "lena horne", "lena horne theatre", "brooks atkinson",
    "helen hayes", "hayes theater", "helen hayes theatre",
    "palace theatre", "the palace theatre"
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
    ("community", [r"\b(talk|lecture|panel|discussion|networking|farmers market|flea market|artisan market|expo|festival|parade|sample sale|fashion|symposium|speed-dating|skip the small talk|tech|ai|hackathon|startup|pitch|coworking|founder|mixer)\b"]),
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


def is_placeholder_or_closed_event(title: str) -> bool:
    """Detect dummy calendar placeholders, cancellations, closures, and private events."""
    if not title:
        return True
    t = title.strip()
    if is_closed_show(t):
        return True

    # 1. Explicit cancellation or postponement at start of title
    if re.match(r"^\s*(\*{1,3}|\[|\()?\s*(canceled|cancelled|postponed)\b", t, re.I):
        return True

    # 2. "No event / no show / no music / no jam / no gypsy jazz"
    if re.search(r"\bno\s+([\w\s]+\s+)?(event|events|show|shows|live\s+music|music|performance|performances|band|bands|jam|jams|open\s+mic|dancing|dance|jazz)\b", t, re.I):
        # Guard against band/show names like "No Cover", "No Bad Chords", "No Static", "No Pressure", "No Friends"
        if not re.search(r"\bno\s+(cover|bad|pressure|static|relation|doubt|friends|more|guarantee|limit|worries|regrets|stopping)\b", t, re.I):
            return True

    # 3. Check calendar placeholder
    if re.search(r"\bcheck\s+(our\s+)?calendar\b", t, re.I):
        return True

    # 4. Standalone or holiday closures: "club closed", "closed for Thanksgiving", "closed for private event"
    if re.search(r"\b(closed|closing)\b.*(for\s+.*(holiday|thanksgiving|christmas|new\s+year|private)|private\s+(event|party))", t, re.I):
        return True
    if re.search(r"^\s*(club|venue|room|lounge|bar|taproom|brewery|kitchen)?\s*closed(\s+today|\s+tonight)?\s*$", t, re.I):
        return True
    if re.search(r"\bclosed\s+for\s+(the\s+)?holiday\b", t, re.I):
        return True

    # 5. Standalone Private event / Private party
    if re.search(r"^\s*(\*{1,3}|\[|\()?\s*private\s+(event|party|rental|function)\s*(\*{1,3}|\]|\))?\s*$", t, re.I):
        return True
    if re.search(r"\bclosed\s+for\s+(a\s+)?private\s+(event|party)\b", t, re.I):
        return True

    # 6. Generic single-word / short placeholder
    if t.lower() in ("tba", "tbd", "to be announced", "placeholder", "no title", "closed", "dark"):
        return True

    return False


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
    """DoNYC venue & category scraper — parses Schema.org microdata with Cloudflare error shielding.
    Resolves direct ticket links and official venue websites to prevent linking through doNYC.
    """
    try:
        soup = fetch_soup(url, ua)
    except Exception:
        return []
    events = []
    now = datetime.now(timezone.utc)
    seen = set()

    # Discover official venue website if available on venue landing page
    venue_site = None
    site_el = soup.select_one(".ds-detail-website a, [itemprop='sameAs']")
    if site_el and site_el.get("href"):
        cand_site = site_el["href"].strip()
        if cand_site.startswith("http") and not any(d in cand_site for d in ["donyc.com", "doubleclick.net"]):
            venue_site = cand_site

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

        # Extract direct ticketing/source link
        ticket_url = None
        offer_el = card.find(itemprop="offers")
        tix_btn = card.select_one(".ds-buy-tix, a[class*='buy-tix'], a[class*='ticket']")
        raw_tix = ""
        if offer_el:
            meta_url = offer_el.find("meta", itemprop="url")
            if meta_url and meta_url.get("content"):
                raw_tix = meta_url.get("content")
        if not raw_tix and tix_btn:
            raw_tix = tix_btn.get("href") or ""

        if raw_tix:
            try:
                parsed = urlparse(raw_tix)
                qs = parse_qs(parsed.query)
                for dest_key in ("u", "url", "redirect", "dest", "target"):
                    if dest_key in qs and qs[dest_key] and qs[dest_key][0].startswith("http"):
                        raw_tix = qs[dest_key][0]
                        parsed = urlparse(raw_tix)
                        qs = parse_qs(parsed.query)
                        break
                clean_qs = {k: v for k, v in qs.items() if not k.startswith("utm_") and k not in ("cid", "pid", "SharedId")}
                new_q = urlencode(clean_qs, doseq=True)
                cleaned = urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_q, parsed.fragment))
                if cleaned.startswith("http") and not any(d in cleaned for d in ["donyc.com", "doubleclick.net"]):
                    ticket_url = cleaned
            except Exception:
                if raw_tix.startswith("http") and not any(d in raw_tix for d in ["donyc.com", "doubleclick.net"]):
                    ticket_url = raw_tix

        # Direct reference priority: direct ticket link > venue official website > search link
        primary_url = ticket_url or venue_site
        if not primary_url:
            v_label = venue_name or ""
            q_str = f"{name} {v_label} NYC".strip()
            primary_url = f"https://www.google.com/search?q={quote_plus(q_str)}"

        key = (name.lower(), dt.date().isoformat())
        if key in seen:
            continue
        seen.add(key)
        ev_dict = {
            "name": name,
            "date": dt.isoformat(),
            "url": primary_url,
            "venue": venue_name,
            "price": None,
        }
        if ticket_url:
            ev_dict["ticket_url"] = ticket_url
        events.append(ev_dict)
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
        resp = _SESSION.get("https://seshcomedy.com/showcases.php", headers={"User-Agent": ua}, timeout=10)
        if not resp.ok:
            raise RuntimeError(f"HTTP {resp.status_code}")
        soup = BeautifulSoup(resp.content, "html.parser")
    except Exception:
        raise

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
    headers = {
        "User-Agent": ua or UA_CHROME,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Sec-Ch-Ua": '"Chromium";v="124", "Google Chrome";v="124"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"macOS"',
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
    }
    resp = _SESSION.get(url, headers=headers, timeout=12)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    for s in soup.find_all("script", type="application/ld+json"):
        if not s.string:
            continue
        try:
            data = json.loads(s.string)
            items_to_check = []
            if isinstance(data, dict):
                if data.get("@type") == "ItemList":
                    items_to_check.append(data)
                elif "@graph" in data and isinstance(data["@graph"], list):
                    for g in data["@graph"]:
                        if isinstance(g, dict) and g.get("@type") == "ItemList":
                            items_to_check.append(g)
            elif isinstance(data, list):
                for g in data:
                    if isinstance(g, dict) and g.get("@type") == "ItemList":
                        items_to_check.append(g)

            for d_item in items_to_check:
                for el in d_item.get("itemListElement", []):
                    item = el.get("item", {}) if isinstance(el, dict) else {}
                    if not item and isinstance(el, dict) and el.get("@type") == "Event":
                        item = el
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
                    vname = None
                    lat = None
                    lng = None
                    addr_str = None
                    neigh_str = None
                    if isinstance(loc, dict):
                        vname = loc.get("name")
                        geo = loc.get("geo")
                        if isinstance(geo, dict):
                            lat = geo.get("latitude")
                            lng = geo.get("longitude")
                        addr = loc.get("address")
                        if isinstance(addr, dict):
                            street = addr.get("streetAddress", "")
                            city = addr.get("addressLocality", "")
                            region = addr.get("addressRegion", "")
                            addr_str = f"{street}, {city}, {region}".strip(", ")
                            neigh_str = city

                    ev_dict = {
                        "name": name,
                        "date": dt.isoformat(),
                        "url": event_url,
                        "venue": vname,
                        "price": price,
                    }
                    if lat is not None and lng is not None:
                        ev_dict["lat"] = lat
                        ev_dict["lng"] = lng
                    if addr_str:
                        ev_dict["address"] = addr_str
                    if neigh_str:
                        ev_dict["neighborhood"] = neigh_str
                    events.append(ev_dict)
        except Exception:
            continue
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
    headers = {
        "User-Agent": ua or UA_CHROME,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": f"https://www.eventbrite.com/o/{org_id}",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
    }
    resp = _SESSION.get(api_url, headers=headers, timeout=12)
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
    return events


def scrape_lincoln_square_bid(url, ua):
    """Scrape official Lincoln Square BID & Columbus Circle district events."""
    events = []
    seen = set()
    now = datetime.now(timezone.utc)
    horizon = now + timedelta(days=14)
    try:
        resp = _SESSION.get(url, headers={"User-Agent": ua}, timeout=12)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        for item in soup.select(".event-item"):
            title_el = item.select_one(".event-item-content h3 a")
            if not title_el:
                continue
            name = title_el.get_text(strip=True)
            ev_url = title_el.get("href") or url

            ps = item.select(".event-item-content p")
            date_text = ps[0].get_text(strip=True) if ps else ""
            venue_text = ps[1].get_text(strip=True) if len(ps) > 1 else "Lincoln Square / Columbus Circle"

            matches = re.findall(r"(\d{1,2})/(\d{1,2})(?:/(\d{4}))?", date_text)
            if not matches:
                continue
            m_start = matches[0]
            s_m, s_d = int(m_start[0]), int(m_start[1])
            s_y = int(m_start[2]) if m_start[2] else now.year
            try:
                start_dt = datetime(s_y, s_m, s_d, 18, 0, tzinfo=EASTERN).astimezone(timezone.utc)
            except Exception:
                continue

            end_dt = start_dt
            if len(matches) > 1:
                m_end = matches[1]
                e_m, e_d = int(m_end[0]), int(m_end[1])
                e_y = int(m_end[2]) if m_end[2] else now.year
                try:
                    end_dt = datetime(e_y, e_m, e_d, 18, 0, tzinfo=EASTERN).astimezone(timezone.utc)
                except Exception:
                    end_dt = start_dt

            if end_dt < now:
                continue
            ev_dt = start_dt if start_dt >= now else now
            if ev_dt > horizon:
                continue

            key = (name.lower(), ev_dt.date().isoformat())
            if key in seen:
                continue
            seen.add(key)
            events.append({
                "name": name,
                "date": ev_dt.isoformat(),
                "url": ev_url,
                "venue": venue_text or "Lincoln Square / Columbus Circle",
                "price": "Free" if "free" in item.get("class", []) or "free" in name.lower() else None,
                "category": "theater" if any(k in name.lower() for k in ["opera", "theatre", "theater", "play", "dance"]) else "art",
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


def scrape_skip_the_small_talk(url, ua):
    """Skip the Small Talk official NYC events calendar from their Squarespace store."""
    api_url = "https://www.skipthesmalltalk.com/store?format=json"
    headers = {"User-Agent": ua or UA_CHROME}
    events = []
    seen = set()
    now = datetime.now(EASTERN)

    try:
        resp = _SESSION.get(api_url, headers=headers, timeout=12)
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return []

    for it in data.get("items") or []:
        cats = it.get("categories") or []
        if "New York City" not in cats or "Online" in cats:
            continue
        raw_title = (it.get("title") or "").strip()
        if not raw_title or raw_title.startswith("[RESCHEDULED") or raw_title.startswith("[CANCELLED"):
            continue

        dm = re.search(r":\s*([A-Za-z]+,\s+[A-Za-z]+\s+\d{1,2},\s+\d{4})", raw_title)
        if not dm:
            dm = re.search(r"([A-Za-z]+,\s+[A-Za-z]+\s+\d{1,2},\s+\d{4})", raw_title)
        if not dm:
            continue
        date_str = dm.group(1)

        clean_title = raw_title[:dm.start()].strip().rstrip(":")
        if not clean_title:
            clean_title = raw_title

        excerpt = it.get("excerpt") or ""
        soup = BeautifulSoup(excerpt, "html.parser")
        text = soup.get_text(separator="\n")

        tm = re.search(r"EVENT START-END TIME\s*\|\s*(\d{1,2}):(\d{2})\s*(am|pm)", text, re.IGNORECASE)
        wm = re.search(r"WHERE\s*\|\s*(.+)", text, re.IGNORECASE)

        hour, minute = 19, 0
        if tm:
            h = int(tm.group(1))
            m = int(tm.group(2))
            ampm = tm.group(3).lower()
            if ampm == "pm" and h != 12:
                h += 12
            elif ampm == "am" and h == 12:
                h = 0
            hour, minute = h, m

        try:
            dt_naive = datetime.strptime(date_str, "%A, %B %d, %Y")
            dt = dt_naive.replace(hour=hour, minute=minute, tzinfo=EASTERN)
        except Exception:
            continue

        if dt < now - timedelta(hours=3):
            continue

        venue = "Skip the Small Talk NYC"
        address = None
        if wm:
            raw_where = wm.group(1).split("(")[0].strip()
            parts = [p.strip() for p in raw_where.split(",") if p.strip()]
            if parts:
                venue = parts[0]
                address = raw_where

        price = "$15"
        cents = it.get("salePriceCents") or it.get("priceCents")
        if cents:
            price = f"${cents / 100:.2f}".rstrip("0").rstrip(".")
        else:
            vars_list = it.get("variants") or []
            if vars_list:
                vp = vars_list[0].get("salePrice") or vars_list[0].get("price")
                if vp:
                    price = f"${vp / 100:.2f}".rstrip("0").rstrip(".")

        full_url = "https://www.skipthesmalltalk.com" + it.get("fullUrl", "")
        key = (clean_title.lower(), dt.strftime("%Y-%m-%d"))
        if key in seen:
            continue
        seen.add(key)

        ev_dict = {
            "name": clean_title,
            "date": dt.astimezone(timezone.utc).isoformat(),
            "url": full_url,
            "venue": venue,
            "price": price,
            "category": "community",
            "description": f"Skip the Small Talk social connection event at {venue}. {price}.",
        }
        if address:
            ev_dict["address"] = address
        events.append(ev_dict)

    return events


def scrape_meetup(url, ua):
    """Meetup.com — in-person community events (search pages and direct group pages)."""
    events = []
    seen = set()
    now = datetime.now(timezone.utc)
    spam_words = [
        "zoom", "webinar", "virtual", "online event", "from home",
        "speed dating from home", "instant zoom", "match from home"
    ]
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

        def _format_meetup_venue(vname, street, city_hint, region_hint, org_name):
            vname = (vname or "").strip()
            street = (street or "").strip()
            city_hint = (city_hint or "").strip()
            region_hint = (region_hint or "").strip()
            org_name = (org_name or "").strip()

            full_addr_parts = [p for p in (street, city_hint, region_hint) if p]
            full_addr = ", ".join(full_addr_parts)

            invalid_v = not vname or vname.lower() in [
                "none", "see event description", "view point", "null", "needs a location", "tbd", "tba"
            ]
            if invalid_v:
                if street:
                    vname = f"{street}, {city_hint}" if city_hint and city_hint.lower() not in street.lower() else street
                elif org_name and city_hint:
                    vname = f"{org_name} ({city_hint})"
                elif org_name:
                    vname = org_name
                elif city_hint:
                    vname = f"NYC Meetup ({city_hint})"
                else:
                    vname = "NYC Community Location"
            else:
                if street and street.lower() not in vname.lower():
                    if city_hint and city_hint.lower() not in ("new york", "new york city", "nyc") and city_hint.lower() not in street.lower() and city_hint.lower() not in vname.lower():
                        vname = f"{vname} ({street}, {city_hint})"
                    else:
                        vname = f"{vname} ({street})"
                elif city_hint and city_hint.lower() not in ("new york", "new york city", "nyc") and city_hint.lower() not in vname.lower():
                    vname = f"{vname} ({city_hint})"

            if not full_addr and org_name:
                full_addr = org_name
            return vname, full_addr

        # 1. Parse Schema.org JSON-LD blocks
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

                    mode = (ev.get("eventAttendanceMode") or "").lower()
                    if "online" in mode:
                        continue

                    loc = ev.get("location", {})
                    if not isinstance(loc, dict) or loc.get("@type") == "VirtualLocation":
                        continue

                    name = (ev.get("name") or "").strip()
                    if not name:
                        continue

                    name_lower = name.lower()
                    if any(w in name_lower for w in spam_words):
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

                    key = (name_lower, dt.isoformat()[:10])
                    if key in seen:
                        continue
                    seen.add(key)

                    vname_raw = (loc.get("name") or "").strip()
                    addr = loc.get("address")
                    city_hint = ""
                    region_hint = ""
                    street = ""
                    if isinstance(addr, dict):
                        street = (addr.get("streetAddress") or "").strip()
                        city_hint = (addr.get("addressLocality") or "").strip()
                        region_hint = (addr.get("addressRegion") or "").strip()

                    org = ev.get("organizer")
                    org_name = org.get("name", "") if isinstance(org, dict) else ""
                    vname, full_addr = _format_meetup_venue(vname_raw, street, city_hint, region_hint, org_name)

                    lat = None
                    lng = None
                    geo = loc.get("geo")
                    if isinstance(geo, dict):
                        try:
                            lat = float(geo.get("latitude"))
                            lng = float(geo.get("longitude"))
                        except Exception:
                            pass

                    price = "Free"
                    offers = ev.get("offers")
                    if isinstance(offers, dict):
                        p = str(offers.get("price", "")).strip()
                        if p and p not in ["0", "0.00", "0.0"]:
                            price = f"${p}"
                    elif isinstance(offers, list) and offers:
                        p = str(offers[0].get("price", "")).strip()
                        if p and p not in ["0", "0.00", "0.0"]:
                            price = f"${p}"

                    desc = (ev.get("description") or "").strip()[:250]
                    event_url = ev.get("url") or url

                    events.append({
                        "name": name,
                        "date": dt.isoformat(),
                        "url": event_url,
                        "venue": vname,
                        "address": full_addr,
                        "lat": lat,
                        "lng": lng,
                        "price": price,
                        "description": desc,
                    })
            except Exception:
                pass

        # 2. Parse __NEXT_DATA__ Apollo state (captures group event pages & additional search results)
        nd = soup.find("script", id="__NEXT_DATA__")
        if nd and nd.string:
            try:
                apollo = json.loads(nd.string).get("props", {}).get("pageProps", {}).get("__APOLLO_STATE__", {})
                for k, ev in apollo.items():
                    if not k.startswith("Event:") or not isinstance(ev, dict):
                        continue
                    if ev.get("eventType") != "PHYSICAL":
                        continue

                    name = (ev.get("title") or "").strip()
                    if not name:
                        continue
                    name_lower = name.lower()
                    if any(w in name_lower for w in spam_words):
                        continue

                    raw_date = ev.get("dateTime")
                    if not raw_date:
                        continue
                    try:
                        dt = datetime.fromisoformat(raw_date.replace("Z", "+00:00")).astimezone(timezone.utc)
                    except Exception:
                        continue
                    if dt < now:
                        continue

                    key = (name_lower, dt.isoformat()[:10])
                    if key in seen:
                        continue
                    seen.add(key)

                    v_obj = ev.get("venue") or {}
                    if isinstance(v_obj, dict) and "__ref" in v_obj:
                        v_obj = apollo.get(v_obj["__ref"], {}) or {}
                    g_obj = ev.get("group") or {}
                    if isinstance(g_obj, dict) and "__ref" in g_obj:
                        g_obj = apollo.get(g_obj["__ref"], {}) or {}

                    vname_raw = (v_obj.get("name") or "").strip() if isinstance(v_obj, dict) else ""
                    street = (v_obj.get("address") or "").strip() if isinstance(v_obj, dict) else ""
                    city_hint = (v_obj.get("city") or "").strip() if isinstance(v_obj, dict) else ""
                    region_hint = (v_obj.get("state") or "").strip() if isinstance(v_obj, dict) else ""
                    org_name = (g_obj.get("name") or "").strip() if isinstance(g_obj, dict) else ""

                    vname, full_addr = _format_meetup_venue(vname_raw, street, city_hint, region_hint, org_name)

                    lat = None
                    lng = None
                    if isinstance(v_obj, dict):
                        try:
                            if v_obj.get("lat") is not None and v_obj.get("lng") is not None:
                                lat = float(v_obj["lat"])
                                lng = float(v_obj["lng"])
                            elif v_obj.get("lat") is not None and v_obj.get("lon") is not None:
                                lat = float(v_obj["lat"])
                                lng = float(v_obj["lon"])
                        except Exception:
                            pass

                    price = "Free"
                    fee = ev.get("feeSettings")
                    if isinstance(fee, dict) and fee.get("amount"):
                        price = f"${fee['amount']}"

                    desc = (ev.get("description") or "").strip()[:250]
                    event_url = ev.get("eventUrl") or url

                    events.append({
                        "name": name,
                        "date": dt.isoformat(),
                        "url": event_url,
                        "venue": vname,
                        "address": full_addr,
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



def scrape_luma(url, ua):
    """Scrape curated NYC tech, AI, startup, and community events from Luma."""
    api_url = "https://api.lu.ma/discover/get-paginated-events?discover_place_api_id=discplace-Izx1rQVSh8njYpP"
    headers = {
        "User-Agent": ua,
        "Accept": "application/json",
    }
    events = []
    seen = set()
    now = datetime.now(timezone.utc)
    cursor = None

    for _ in range(5):
        req_url = api_url
        if cursor:
            req_url += f"&pagination_cursor={cursor}"
        try:
            resp = _SESSION.get(req_url, headers=headers, timeout=15)
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            break

        entries = data.get("entries") or []
        for entry in entries:
            ev = entry.get("event") or {}
            name = (ev.get("name") or "").strip()
            if not name or is_placeholder_or_closed_event(name):
                continue

            start_at = ev.get("start_at")
            if not start_at:
                continue
            try:
                dt = datetime.fromisoformat(start_at.replace("Z", "+00:00"))
                if dt.astimezone(timezone.utc) < now:
                    continue
                iso_date = dt.astimezone(timezone.utc).isoformat()
            except Exception:
                continue

            slug = ev.get("url") or ""
            link = slug if slug.startswith("http") else f"https://lu.ma/{slug}"

            key = (name.lower(), iso_date[:10])
            if key in seen:
                continue
            seen.add(key)

            geo = ev.get("geo_address_info") or {}
            cal = entry.get("calendar") or {}

            if geo.get("mode") == "shown" and (geo.get("address") or geo.get("short_address")):
                addr = geo.get("address") or geo.get("short_address")
                city = geo.get("city") or "New York"
                venue = addr if city.lower() in addr.lower() else f"{addr}, {city}"
            elif geo.get("sublocality") or geo.get("city"):
                subloc = geo.get("sublocality") or geo.get("city")
                venue = f"{subloc} (RSVP for address)"
            elif cal.get("name") and cal.get("name").lower() != "personal":
                venue = cal.get("name")
            else:
                venue = "New York"

            coord = ev.get("coordinate") or geo.get("place_coordinate") or {}
            lat = coord.get("latitude")
            lng = coord.get("longitude")
            address = geo.get("full_address") or geo.get("address") or ""
            neighborhood = geo.get("sublocality") or ""

            t_info = entry.get("ticket_info") or {}
            price = None
            if t_info.get("is_free"):
                price = "Free"
            elif t_info.get("price"):
                cents = t_info["price"].get("cents")
                if cents == 0:
                    price = "Free"
                elif cents is not None:
                    price = f"${cents / 100:.2f}".rstrip("0").rstrip(".")

            hosts = [h.get("name") for h in (entry.get("hosts") or []) if h.get("name")]
            cal_desc = cal.get("description_short")
            desc_parts = []
            if hosts:
                h_str = ", ".join(hosts[:3])
                desc_parts.append(f"Hosted by {h_str}")
            if cal_desc:
                desc_parts.append(cal_desc)
            desc = " • ".join(desc_parts)[:250] if desc_parts else None

            cat = guess_category(name, default="community", venue=venue)

            ev_dict = {
                "name": name,
                "date": iso_date,
                "url": link,
                "venue": venue,
                "price": price,
                "category": cat,
                "description": desc,
            }
            if lat is not None and lng is not None:
                ev_dict["lat"] = lat
                ev_dict["lng"] = lng
            if address:
                ev_dict["address"] = address
            if neighborhood:
                ev_dict["neighborhood"] = neighborhood

            events.append(ev_dict)

        if not data.get("has_more") or not data.get("next_cursor"):
            break
        cursor = data.get("next_cursor")

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


def scrape_sobs(url, ua):
    """S.O.B.'s (Sounds of Brazil) — Direct official calendar scraper from sobs.com/calendar/."""
    events = []
    seen = set()
    month_map = {
        "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
        "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12
    }
    now = datetime.now(EASTERN)
    urls = [url or "https://sobs.com/calendar/"]
    if now.day >= 15:
        next_month = now.month % 12 + 1
        next_year = now.year + (1 if now.month == 12 else 0)
        urls.append(f"https://sobs.com/calendar/?dir=next&view=grid&month={next_year}{next_month:02d}")

    for target_url in urls:
        try:
            resp = _SESSION.get(target_url, headers={"User-Agent": ua or UA_CHROME}, timeout=12)
            if resp.status_code != 200:
                continue
            soup = BeautifulSoup(resp.text, "html.parser")
            cards = soup.select(".ecard")
            for card in cards:
                titu_el = card.select_one(".ecard_titu")
                if not titu_el:
                    continue
                title = titu_el.get_text(strip=True)
                if not title:
                    continue

                event_url = card.get("data-link") or ""
                link_el = card.select_one("a.btn-line, a[href*='/events/']")
                if not event_url and link_el:
                    event_url = link_el.get("href") or ""

                date_el = card.select_one(".ecard_date")
                time_el = card.select_one(".ecard_time")
                date_text = date_el.get_text(strip=True) if date_el else ""
                time_text = time_el.get_text(strip=True) if time_el else ""

                m_date = re.search(r"([A-Za-z]{3,9})\s+(\d{1,2})(?:,?\s*(\d{4}))?", date_text)
                if not m_date:
                    continue
                mon_str = m_date.group(1).lower()[:3]
                if mon_str not in month_map:
                    continue
                month = month_map[mon_str]
                day = int(m_date.group(2))
                year = int(m_date.group(3)) if m_date.group(3) else now.year

                hr, mn = 20, 0
                m_time = re.search(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)", time_text, re.I)
                if m_time:
                    hr = int(m_time.group(1))
                    mn = int(m_time.group(2) or 0)
                    ampm = m_time.group(3).lower()
                    if ampm == "pm" and hr < 12:
                        hr += 12
                    elif ampm == "am" and hr == 12:
                        hr = 0

                try:
                    dt = datetime(year, month, day, hr, mn, tzinfo=EASTERN)
                except ValueError:
                    continue

                dt_utc = dt.astimezone(timezone.utc)
                key = (title.lower(), dt_utc.date().isoformat())
                if key in seen:
                    continue
                seen.add(key)

                img_el = card.select_one(".ecard-image")
                img_url = ""
                if img_el and "background-image" in img_el.get("style", ""):
                    m_img = re.search(r"url\(([^)]+)\)", img_el.get("style", ""))
                    if m_img:
                        img_url = m_img.group(1).strip("'\"")

                events.append({
                    "name": title,
                    "date": dt_utc.isoformat(),
                    "url": event_url or "https://sobs.com/calendar/",
                    "venue": "S.O.B.'s",
                    "lat": 40.7282,
                    "lng": -74.0049,
                    "price": None,
                    "image": img_url or None,
                    "category": guess_category(title, "music", venue="S.O.B.'s"),
                })
        except Exception:
            continue
    return events


def scrape_warsaw(url, ua):
    """Warsaw Brooklyn — Live Nation venue direct JSON-LD scraper from warsawconcerts.com."""
    events = []
    seen = set()
    now = datetime.now(timezone.utc)
    target_url = url or "https://www.warsawconcerts.com/"
    try:
        resp = _SESSION.get(target_url, headers={"User-Agent": ua or UA_CHROME}, timeout=12)
        if resp.status_code != 200:
            return []
        soup = BeautifulSoup(resp.text, "html.parser")
        for s in soup.find_all("script", type="application/ld+json"):
            if not s.string:
                continue
            try:
                data = json.loads(s.string)
                items = data if isinstance(data, list) else [data] if isinstance(data, dict) else []
                for it in items:
                    if it.get("@type") in ("Event", "MusicEvent"):
                        name = (it.get("name") or "").strip()
                        start = it.get("startDate")
                        event_url = it.get("url") or target_url
                        if not name or not start:
                            continue
                        dt = datetime.fromisoformat(start.replace("Z", "+00:00")).astimezone(timezone.utc)
                        if dt < now:
                            continue
                        key = (name.lower(), dt.date().isoformat())
                        if key in seen:
                            continue
                        seen.add(key)

                        img = it.get("image")
                        if isinstance(img, list) and img:
                            img = img[0]
                        elif isinstance(img, dict):
                            img = img.get("url")

                        events.append({
                            "name": name,
                            "date": dt.isoformat(),
                            "url": event_url,
                            "venue": "Warsaw Brooklyn",
                            "lat": 40.7224,
                            "lng": -73.9489,
                            "price": None,
                            "image": img if isinstance(img, str) else None,
                            "category": "music"
                        })
            except Exception:
                continue
    except Exception:
        pass
    return events


def scrape_diwali_times_square(url, ua):
    """Diwali at Times Square — Official flagship cultural festival scraper."""
    events = []
    target_url = url or "https://diwalitimessquare.com/"
    now = datetime.now(timezone.utc)
    try:
        resp = _SESSION.get(target_url, headers={"User-Agent": ua or UA_CHROME}, timeout=12)
        if resp.status_code != 200:
            return []
        soup = BeautifulSoup(resp.text, "html.parser")
        text = soup.get_text()

        m_date = re.search(r"Event Date\s*([A-Za-z]+ \d{1,2}, \d{4})", text)
        if not m_date:
            m_date = re.search(r"(?:returns|back on)\s*([A-Za-z]+ \d{1,2},? \d{4})", text, re.I)

        if m_date:
            raw_date = m_date.group(1).replace(",", "")
            dt_date = datetime.strptime(raw_date, "%B %d %Y").date()
            event_dt = datetime(dt_date.year, dt_date.month, dt_date.day, 13, 0, tzinfo=EASTERN).astimezone(timezone.utc)
            if event_dt >= now - timedelta(days=1):
                og_img = soup.find("meta", property="og:image")
                img_url = og_img.get("content") if og_img else None

                events.append({
                    "name": f"Diwali at Times Square {dt_date.year} (Free Cultural Festival)",
                    "date": event_dt.isoformat(),
                    "url": target_url,
                    "venue": "Times Square (46th-48th St)",
                    "price": "Free",
                    "category": "community",
                    "image": img_url,
                    "lat": 40.7589,
                    "lng": -73.9851,
                    "address": "Broadway between 46th & 48th St, Times Square, New York, NY",
                    "neighborhood": "Times Square",
                    "description": "The largest Diwali festival outside India featuring cultural performances, Diwali Bazaar, Kids Zone, live concerts, and the signature Diya lighting countdown on One Times Square.",
                })
    except Exception as e:
        print(f"Error scraping Diwali at Times Square: {e}")
    return events


def scrape_clearview_festivals(url, ua):
    """Clearview Festival Productions — Official NYC weekend street fairs and avenue festivals."""
    events = []
    target_url = url or "https://vendors.clearviewfestival.com"
    now = datetime.now(timezone.utc)
    try:
        resp = _SESSION.get(target_url, headers={"User-Agent": ua or UA_CHROME}, timeout=12)
        if resp.status_code != 200:
            return []
        soup = BeautifulSoup(resp.text, "html.parser")
        sponsors = soup.select("span.sponsor")
        for sp in sponsors:
            text = sp.get_text(strip=True)
            m = re.match(r"(\d{1,2}/\d{1,2}/\d{4})\s+(.+)", text)
            if not m:
                continue
            d_str, name = m.group(1), m.group(2).strip()
            # Skip non-NYC suburban events if any (e.g. Islip Long Island)
            if any(suburb in name.lower() for suburb in ("islip", "huntington", "smithtown", "oyster bay", "patchogue")):
                continue

            tr = sp.find_parent("tr")
            venue_parts = []
            if tr:
                cur = tr.find_next_sibling("tr")
                for _ in range(2):
                    if cur:
                        td = cur.find("td", class_="uctest")
                        if td:
                            venue_parts.append(td.get_text(" ", strip=True))
                        cur = cur.find_next_sibling("tr")
            street = venue_parts[0] if len(venue_parts) > 0 else ""
            cross = venue_parts[1] if len(venue_parts) > 1 else ""
            loc_str = f"{street} ({cross})".strip(" ()") or "NYC Street Fair"

            dt_date = datetime.strptime(d_str, "%m/%d/%Y").date()
            # NYC street fairs run ~10:00 AM - 6:00 PM Eastern
            event_dt = datetime(dt_date.year, dt_date.month, dt_date.day, 10, 0, tzinfo=EASTERN).astimezone(timezone.utc)
            if event_dt < now - timedelta(days=1):
                continue

            lat, lng, neigh, borough = None, None, "", "other"
            low_loc = f"{name} {street} {cross}".lower()
            if "broadway" in low_loc and ("96" in low_loc or "106" in low_loc):
                lat, lng, neigh, borough = 40.7975, -73.9698, "Upper West Side", "manhattan"
            elif "broadway" in low_loc and ("110" in low_loc or "116" in low_loc):
                lat, lng, neigh, borough = 40.8068, -73.9645, "Morningside Heights", "manhattan"
            elif "jerome" in low_loc or "mosholu" in low_loc:
                lat, lng, neigh, borough = 40.8795, -73.8845, "Bedford Park / Norwood", "bronx"
            elif "rego park" in low_loc or "63rd dr" in low_loc:
                lat, lng, neigh, borough = 40.7295, -73.8615, "Rego Park", "queens"
            elif "8th ave" in low_loc or "eighth ave" in low_loc:
                lat, lng, neigh, borough = 40.7455, -73.9985, "Chelsea", "manhattan"
            elif "3rd ave" in low_loc or "third ave" in low_loc:
                lat, lng, neigh, borough = 40.7685, -73.9595, "Upper East Side", "manhattan"
            elif "columbus" in low_loc:
                lat, lng, neigh, borough = 40.7815, -73.9775, "Upper West Side", "manhattan"

            events.append({
                "name": f"{name} (NYC Street Fair)",
                "date": event_dt.isoformat(),
                "url": "https://www.clearviewfestival.com",
                "venue": f"{name} ({street})",
                "price": "Free",
                "category": "community",
                "lat": lat,
                "lng": lng,
                "address": loc_str,
                "neighborhood": neigh,
                "city": borough,
                "description": f"Outdoor NYC street fair on {street} between {cross}. Free and open to the public featuring local food, merchandise, artisans, and family activities.",
            })
    except Exception as e:
        print(f"Error scraping Clearview festivals: {e}")
    return events



def scrape_miller_theatre(url, ua):
    """Miller Theatre at Columbia University — Official performing arts and concert calendar."""
    events = []
    target_url = url or "https://www.millertheatre.com/events"
    now_utc = datetime.now(timezone.utc)
    try:
        resp = _SESSION.get(target_url, headers={"User-Agent": ua or UA_CHROME}, timeout=12)
        if resp.status_code != 200:
            return []
        import html as html_lib
        m = re.search(r"<events\s+:events=\"([^\"]+)\"", resp.text)
        if not m:
            return []
        raw_json = html_lib.unescape(m.group(1))
        items = json.loads(raw_json)
        for it in items:
            t = (it.get("title") or "").strip()
            sub = (it.get("subtitle") or "").strip()
            name = f"{t}: {sub}" if sub else t
            if not name:
                continue
            ev_url = it.get("url") or target_url
            price = it.get("price") or "$30"
            cat_obj = it.get("category") or {}
            cat_name = (cat_obj.get("title") or "music").lower()
            category = "music"
            if "jazz" in cat_name:
                category = "music"
            elif "opera" in cat_name or "theatre" in cat_name:
                category = "theater"
            elif "community" in cat_name:
                category = "community"

            unix_ts = it.get("date", {}).get("unix")
            if not unix_ts:
                continue
            try:
                dt = datetime.fromtimestamp(int(unix_ts), tz=timezone.utc)
            except Exception:
                continue
            if dt < now_utc - timedelta(hours=6):
                continue

            events.append({
                "name": name,
                "date": dt.isoformat(),
                "url": ev_url,
                "venue": "Miller Theatre at Columbia University",
                "price": price,
                "category": category,
                "lat": 40.8082,
                "lng": -73.9634,
                "address": "2960 Broadway, New York, NY",
                "neighborhood": "Morningside Heights",
                "description": f"Live performance at Columbia University's Miller Theatre ({cat_obj.get('title') or 'Concert'}). {price}.",
            })
    except Exception as e:
        print(f"Error scraping Miller Theatre: {e}")
    return events


def scrape_the_stone(url, ua):
    """The Stone at The New School — Official experimental music calendar curated by John Zorn."""
    events = []
    target_url = url or "http://thestonenyc.com/calendar.php"
    now = datetime.now(EASTERN)
    current_year = now.year
    try:
        resp = _SESSION.get(target_url, headers={"User-Agent": ua or UA_CHROME}, timeout=12)
        if resp.status_code != 200:
            return []
        soup = BeautifulSoup(resp.text, "html.parser")
        header = soup.find("span", class_="header")
        if header:
            m_yr = re.search(r"(\d{4})", header.get_text())
            if m_yr:
                current_year = int(m_yr.group(1))

        for d_el in soup.find_all("span", class_="date"):
            txt = d_el.get_text(strip=True)
            m = re.match(r"(\d{1,2})/(\d{1,2})", txt)
            if not m:
                continue
            month, day = int(m.group(1)), int(m.group(2))
            curr = d_el.next_sibling
            title = None
            time_str = "8:30 pm"
            musicians = ""
            while curr:
                if getattr(curr, "name", None) == "span":
                    cls = curr.get("class", [])
                    if "date" in cls:
                        break
                    if "time" in cls:
                        time_str = curr.get_text(strip=True)
                    elif "calendarname" in cls:
                        title = curr.get_text(strip=True)
                    elif "text" in cls and not musicians:
                        musicians = curr.get_text(strip=True)
                curr = curr.next_sibling
            if not title:
                continue

            hour, minute = 20, 30
            tm = re.search(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)", time_str, re.I)
            if tm:
                h = int(tm.group(1))
                minute = int(tm.group(2) or 0)
                ampm = tm.group(3).lower()
                if ampm == "pm" and h != 12:
                    h += 12
                elif ampm == "am" and h == 12:
                    h = 0
                hour = h

            try:
                dt = datetime(current_year, month, day, hour, minute, tzinfo=EASTERN)
            except Exception:
                continue

            name = f"{title} ({musicians[:40]})" if musicians else title
            events.append({
                "name": name,
                "date": dt.isoformat(),
                "url": target_url,
                "venue": "The Stone (The New School)",
                "price": "$20",
                "category": "music",
                "lat": 40.7355,
                "lng": -73.9961,
                "address": "55 W 13th St, New York, NY",
                "neighborhood": "Greenwich Village",
            })
    except Exception as e:
        print(f"Error scraping The Stone: {e}")
    return events


def scrape_grand_bazaar_nyc(url, ua):
    """Grand Bazaar NYC — Official weekly curated artisanal and street market on Upper West Side."""
    events = []
    target_url = url or "https://grandbazaarnyc.org/"
    now = datetime.now(EASTERN)
    month_map = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}
    seen = set()
    try:
        resp = _SESSION.get(target_url, headers={"User-Agent": ua or UA_CHROME}, timeout=12)
        if resp.status_code != 200:
            return []
        soup = BeautifulSoup(resp.text, "html.parser")
        for a in soup.find_all("a", href=re.compile(r"/events/")):
            txt = a.get_text(" ", strip=True)
            href = a["href"]
            if not href.startswith("http"):
                href = f"https://grandbazaarnyc.org{href}"
            m = re.search(r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s*(\d{1,2})\s*(.+)", txt, re.I)
            if not m:
                continue
            mon_str, day_str, title = m.group(1), m.group(2), m.group(3).strip()
            month = month_map.get(mon_str.lower()[:3])
            if not month:
                continue
            day = int(day_str)
            yr = now.year if month >= now.month else now.year + 1
            try:
                dt = datetime(yr, month, day, 10, 0, tzinfo=EASTERN)
            except Exception:
                continue
            key = (title.lower(), dt.date().isoformat())
            if key in seen:
                continue
            seen.add(key)
            events.append({
                "name": f"Grand Bazaar NYC: {title}",
                "date": dt.isoformat(),
                "url": href,
                "venue": "Grand Bazaar NYC (Upper West Side)",
                "price": "Free",
                "category": "community",
                "lat": 40.7806,
                "lng": -73.9767,
                "address": "100 W 77th St at Columbus Ave, New York, NY",
                "neighborhood": "Upper West Side",
            })
    except Exception as e:
        print(f"Error scraping Grand Bazaar NYC: {e}")
    return events


def scrape_queens_night_market(url, ua):
    """Queens Night Market — Official open-air Saturday food and cultural market at Flushing Meadows Corona Park."""
    events = []
    target_url = url or "https://queensnightmarket.com/"
    now = datetime.now(EASTERN)
    month_map = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}
    try:
        resp = _SESSION.get(target_url, headers={"User-Agent": ua or UA_CHROME}, timeout=12)
        if resp.status_code != 200:
            return []
        soup = BeautifulSoup(resp.text, "html.parser")
        txt = soup.get_text(" ", strip=True)
        m = re.search(r"NEXT NIGHT MARKET:\s*(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s*(\d{1,2})", txt, re.I)
        if m:
            mon = month_map.get(m.group(1).lower()[:3])
            day = int(m.group(2))
            yr = now.year
            try:
                dt = datetime(yr, mon, day, 16, 0, tzinfo=EASTERN)
                if dt >= now - timedelta(hours=12):
                    events.append({
                        "name": "Queens Night Market (Flushing Meadows Corona Park)",
                        "date": dt.isoformat(),
                        "url": target_url,
                        "venue": "New York Hall of Science (Flushing Meadows)",
                        "price": "Free",
                        "category": "food",
                        "lat": 40.7476,
                        "lng": -73.8519,
                        "address": "47-01 111th St, Queens, NY",
                        "neighborhood": "Flushing Meadows",
                        "description": "NYC's flagship family-friendly outdoor night market featuring 100+ independent food vendors, cultural performances, and games.",
                    })
            except Exception:
                pass
    except Exception as e:
        print(f"Error scraping Queens Night Market: {e}")
    return events


def scrape_bryant_park(url, ua):
    """Bryant Park Events — Official calendar of activities, concerts, classes, and celebrations."""
    events = []
    target_url = url or "https://bryantpark.org/calendar"
    now = datetime.now(EASTERN)
    seen = set()
    try:
        resp = _SESSION.get(target_url, headers={"User-Agent": ua or UA_CHROME}, timeout=12)
        if resp.status_code != 200:
            return []
        soup = BeautifulSoup(resp.text, "html.parser")
        for a in soup.find_all("a", href=re.compile(r"/calendar/event/[^/]+/\d{4}-\d{2}-\d{2}")):
            href = a["href"]
            name = a.get_text(strip=True)
            if not name or len(name) < 3 or name in ("Learn More", "Details", "View"):
                continue
            m = re.search(r"(\d{4}-\d{2}-\d{2})", href)
            if not m:
                continue
            date_str = m.group(1)
            full_url = f"https://bryantpark.org{href}" if href.startswith("/") else href
            key = (name.lower(), date_str)
            if key in seen:
                continue
            seen.add(key)
            try:
                dt = datetime.fromisoformat(f"{date_str}T12:00:00").replace(tzinfo=EASTERN)
                if dt.date() >= now.date():
                    events.append({
                        "name": f"Bryant Park: {name}",
                        "date": dt.isoformat(),
                        "url": full_url,
                        "venue": "Bryant Park (Midtown Manhattan)",
                        "price": "Free",
                        "category": "outdoors",
                        "lat": 40.7536,
                        "lng": -73.9832,
                        "address": "Bryant Park, New York, NY",
                        "neighborhood": "Midtown",
                    })
            except Exception:
                continue
    except Exception as e:
        print(f"Error scraping Bryant Park: {e}")
    return events


def scrape_symphony_space(url, ua):
    """Symphony Space — Official Upper West Side theater, literature, and concert calendar."""
    events = []
    target_url = url or "https://www.symphonyspace.org/events"
    month_map = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}
    seen = set()
    try:
        resp = _SESSION.get(target_url, headers={"User-Agent": ua or UA_CHROME}, timeout=12)
        if resp.status_code != 200:
            return []
        soup = BeautifulSoup(resp.text, "html.parser")
        for a in soup.select("a[href*='/events/']"):
            href = a.get("href", "")
            txt = a.get_text(" ", strip=True)
            if not href or href.endswith("/events") or "/calendar" in href:
                continue
            m = re.search(r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{1,2}),?\s+(\d{4})(?:\s*\|\s*(\d{1,2})(?::(\d{2}))?\s*(am|pm))?", txt, re.I)
            if not m:
                continue
            mon = month_map.get(m.group(1).lower()[:3])
            if not mon:
                continue
            day = int(m.group(2))
            yr = int(m.group(3))
            hour = 19
            minute = 30
            if m.group(4):
                h = int(m.group(4))
                minute = int(m.group(5) or 0)
                ampm = (m.group(6) or "pm").lower()
                if ampm == "pm" and h != 12:
                    h += 12
                elif ampm == "am" and h == 12:
                    h = 0
                hour = h

            title = txt[:m.start()].strip()
            title = re.sub(r"^Symphony Space\s*", "", title)
            title = re.sub(r"^(Revelry|Broadway on Screen|Theater on Screen|Artists in Exile|Silent Clowns Film Series|Selected Shorts Pop-Up):\s*", "", title)
            if not title:
                continue

            try:
                dt = datetime(yr, mon, day, hour, minute, tzinfo=EASTERN)
            except Exception:
                continue

            full_url = href if href.startswith("http") else f"https://www.symphonyspace.org{href}"
            key = (title.lower(), dt.date().isoformat())
            if key in seen:
                continue
            seen.add(key)
            events.append({
                "name": title,
                "date": dt.isoformat(),
                "url": full_url,
                "venue": "Symphony Space (Upper West Side)",
                "price": None,
                "category": "theater",
                "lat": 40.7946,
                "lng": -73.9723,
                "address": "2537 Broadway, New York, NY",
                "neighborhood": "Upper West Side",
            })
    except Exception as e:
        print(f"Error scraping Symphony Space: {e}")
    return events


def scrape_smalls_live(url, ua):
    """Smalls Jazz Club & Mezzrow — Official West Village live jazz schedule from SmallsLIVE."""
    events = []
    target_url = url or "https://www.smallslive.com/"
    now = datetime.now(EASTERN)
    month_map = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}
    seen = set()
    try:
        resp = _SESSION.get(target_url, headers={"User-Agent": ua or UA_CHROME}, timeout=12)
        if resp.status_code != 200:
            return []
        soup = BeautifulSoup(resp.text, "html.parser")
        for a in soup.find_all("a", href=re.compile(r"/events/\d+-")):
            href = a["href"]
            parent = a.find_parent("article") or a.find_parent("div", class_=lambda c: c and any(k in c.lower() for k in ["event", "schedule", "item"])) or a.parent
            txt = parent.get_text(" | ", strip=True) if parent else a.get_text(" ", strip=True)
            slug = re.sub(r"^/events/\d+-", "", href).rstrip("/").replace("-", " ").title()

            m_date = re.search(r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{1,2})", txt, re.I)
            m_time = re.search(r"(\d{1,2})(?::(\d{2}))?\s*(AM|PM)", txt, re.I)

            if m_date:
                mon = month_map.get(m_date.group(1).lower()[:3], now.month)
                day = int(m_date.group(2))
                yr = now.year
            else:
                mon = now.month
                day = now.day
                yr = now.year

            hour, minute = 19, 30
            if m_time:
                h = int(m_time.group(1))
                minute = int(m_time.group(2) or 0)
                ampm = m_time.group(3).lower()
                if ampm == "pm" and h != 12:
                    h += 12
                elif ampm == "am" and h == 12:
                    h = 0
                hour = h

            try:
                dt = datetime(yr, mon, day, hour, minute, tzinfo=EASTERN)
            except Exception:
                continue

            full_url = f"https://www.smallslive.com{href}" if href.startswith("/") else href
            key = (slug.lower(), dt.date().isoformat())
            if key in seen:
                continue
            seen.add(key)
            events.append({
                "name": f"Smalls Jazz: {slug}",
                "date": dt.isoformat(),
                "url": full_url,
                "venue": "Smalls Jazz Club (West Village)",
                "price": "$25",
                "category": "music",
                "lat": 40.7344,
                "lng": -74.0033,
                "address": "183 W 10th St, New York, NY",
                "neighborhood": "Greenwich Village",
            })
    except Exception as e:
        print(f"Error scraping Smalls Live: {e}")
    return events


def scrape_film_forum(url, ua):
    """Film Forum — Official Greenwich Village repertory cinema and filmmaker event schedule."""
    events = []
    target_url = url or "https://filmforum.org/films/now_playing"
    now = datetime.now(EASTERN)
    month_map = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}
    seen = set()
    try:
        resp = _SESSION.get(target_url, headers={"User-Agent": ua or UA_CHROME}, timeout=12)
        if resp.status_code != 200:
            return []
        soup = BeautifulSoup(resp.text, "html.parser")
        for a in soup.find_all("a", href=re.compile(r"/events/event/[^/]+")):
            href = a["href"]
            txt = a.get_text(" ", strip=True)
            if not txt or len(txt) < 3:
                continue
            m_slug = re.search(r"/events/event/(.+)-(january|february|march|april|may|june|july|august|september|october|november|december)-(\d{1,2})", href, re.I)
            if m_slug:
                slug_title = m_slug.group(1).replace("-", " ").title()
                mon = month_map.get(m_slug.group(2).lower()[:3])
                if not mon:
                    continue
                day = int(m_slug.group(3))
                yr = now.year
                try:
                    dt = datetime(yr, mon, day, 19, 0, tzinfo=EASTERN)
                except Exception:
                    continue
                title = txt.split("Post-film")[0].split("Introduced")[0].strip() or slug_title
                key = (title.lower(), dt.date().isoformat())
                if key in seen:
                    continue
                seen.add(key)
                events.append({
                    "name": f"Film Forum: {title}",
                    "date": dt.isoformat(),
                    "url": f"https://filmforum.org{href}" if href.startswith("/") else href,
                    "venue": "Film Forum (Greenwich Village)",
                    "price": "$17",
                    "category": "film",
                    "lat": 40.7283,
                    "lng": -74.0039,
                    "address": "209 W Houston St, New York, NY",
                    "neighborhood": "Greenwich Village",
                })
    except Exception as e:
        print(f"Error scraping Film Forum: {e}")
    return events


def scrape_qed_astoria(url, ua):
    """Scrape Q.E.D. Astoria's Evey Events calendar JSON API."""
    import subprocess
    events = []
    seen = set()
    now_et = datetime.now(EASTERN)
    start_str = now_et.strftime("%Y-%m-%d")
    end_str = (now_et + timedelta(days=HORIZON_DAYS)).strftime("%Y-%m-%d")
    api_url = (
        f"https://api.eveyevents.com/production-v2/storefront/calendar"
        f"?shop=qed-astoria.myshopify.com&startDate={start_str}&endDate={end_str}&currentDate={start_str}&lang=en"
    )
    try:
        try:
            resp = _SESSION.get(api_url, headers={"User-Agent": ua}, timeout=12)
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            out = subprocess.check_output(["curl", "-sL", api_url], timeout=12)
            data = json.loads(out.decode("utf-8", errors="ignore"))

        sched = data.get("schedule", []) if isinstance(data, dict) else []
        for item in sched:
            raw_title = (item.get("title") or "").strip()
            title = html.unescape(raw_title)
            if not title or is_placeholder_or_closed_event(title):
                continue
            start_iso = item.get("start")
            if not start_iso:
                continue
            try:
                dt = datetime.fromisoformat(start_iso.replace("Z", "+00:00"))
            except Exception:
                continue

            key = (title.lower(), dt.strftime("%Y-%m-%d %H:%M"))
            if key in seen:
                continue
            seen.add(key)

            ev_url = (item.get("url") or "https://qedastoria.com/apps/events/calendar").strip()
            if ev_url.startswith("http://qedastoria.com"):
                ev_url = "https://" + ev_url[len("http://"):]

            src_data = item.get("source_data") or {}
            min_p = src_data.get("min_price")
            max_p = src_data.get("max_price")
            price = None
            if "free" in title.lower():
                price = "Free"
            elif min_p is not None:
                try:
                    fmin = float(min_p)
                    fmax = float(max_p) if max_p is not None else fmin
                    price = "Free" if fmax == 0 else _format_price_range(fmin, fmax)
                except Exception:
                    pass

            desc_html = src_data.get("description") or ""
            desc = ""
            if desc_html:
                desc = BeautifulSoup(desc_html, "html.parser").get_text(" ", strip=True)[:240]

            events.append({
                "name": title,
                "date": dt.astimezone(timezone.utc).isoformat(),
                "url": ev_url,
                "venue": "Q.E.D. Astoria",
                "price": price,
                "category": guess_category(f"{title} {desc}", "comedy"),
                "description": desc,
                "lat": 40.7749,
                "lng": -73.9118,
                "address": "27-16 23rd Ave, Queens, NY",
                "neighborhood": "Astoria",
            })
    except Exception as e:
        print(f"Error scraping Q.E.D. Astoria: {e}")
    return events


_TRIBE_VENUE_DEFAULTS = {
    "movingimage.org": ("Museum of the Moving Image", "36-01 35th Ave, Queens, NY", "Astoria", 40.7563, -73.9239, "film"),
    "queensbotanical.org": ("Queens Botanical Garden", "43-50 Main St, Queens, NY", "Flushing", 40.7510, -73.8290, "outdoors"),
    "queensfarm.org": ("Queens County Farm Museum", "73-50 Little Neck Pkwy, Queens, NY", "Floral Park / Glen Oaks", 40.7478, -73.7244, "outdoors"),
    "louisarmstronghouse.org": ("Louis Armstrong House Museum", "34-56 107th St, Queens, NY", "Corona", 40.7556, -73.8614, "music"),
}


def scrape_tribe_events_api(url, ua):
    """Scrape WordPress Tribe Events v1 REST API endpoints (/wp-json/tribe/events/v1/events)."""
    events = []
    seen = set()
    now_et = datetime.now(EASTERN)
    req_url = url
    if "start_date=" not in req_url:
        sep = "&" if "?" in req_url else "?"
        req_url = f"{req_url}{sep}start_date={now_et.strftime('%Y-%m-%d')}"

    default_vname = "Queens Cultural Center"
    default_addr = "Queens, NY"
    default_hood = "Queens"
    default_lat = None
    default_lng = None
    default_cat = "community"
    for dom, meta in _TRIBE_VENUE_DEFAULTS.items():
        if dom in url:
            default_vname, default_addr, default_hood, default_lat, default_lng, default_cat = meta
            break

    try:
        resp = _SESSION.get(req_url, headers={"User-Agent": ua}, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        raw_events = data.get("events", []) if isinstance(data, dict) else []
        for item in raw_events:
            raw_title = item.get("title") or ""
            title = BeautifulSoup(html.unescape(raw_title), "html.parser").get_text(" ", strip=True)
            if not title or is_placeholder_or_closed_event(title):
                continue

            start_str = item.get("start_date") or ""
            if not start_str:
                continue
            try:
                dt_naive = datetime.strptime(start_str[:19], "%Y-%m-%d %H:%M:%S")
                dt = dt_naive.replace(tzinfo=EASTERN)
            except Exception:
                continue

            key = (title.lower(), dt.strftime("%Y-%m-%d %H:%M"))
            if key in seen:
                continue
            seen.add(key)

            ev_url = (item.get("url") or url).strip()
            cost = BeautifulSoup(html.unescape(str(item.get("cost") or "")), "html.parser").get_text(" ", strip=True)
            if cost.lower() in ("free", "$0", "0", "$0.00", "free with admission"):
                price = "Free"
            else:
                price = cost or None

            desc_raw = item.get("excerpt") or item.get("description") or ""
            desc = BeautifulSoup(html.unescape(desc_raw), "html.parser").get_text(" ", strip=True)[:240]

            v_obj = item.get("venue")
            v_name = default_vname
            if isinstance(v_obj, dict) and v_obj.get("venue"):
                cand_v = BeautifulSoup(html.unescape(v_obj["venue"]), "html.parser").get_text(" ", strip=True)
                if cand_v and default_vname.lower() not in cand_v.lower():
                    v_name = f"{default_vname} ({cand_v})"

            ev_dict = {
                "name": title,
                "date": dt.astimezone(timezone.utc).isoformat(),
                "url": ev_url,
                "venue": v_name,
                "price": price,
                "category": guess_category(f"{title} {desc}", default_cat, venue=default_vname),
                "description": desc,
                "address": default_addr,
                "neighborhood": default_hood,
            }
            if default_lat is not None and default_lng is not None:
                ev_dict["lat"] = default_lat
                ev_dict["lng"] = default_lng
            events.append(ev_dict)
    except Exception as e:
        print(f"Error scraping Tribe Events API ({url}): {e}")
    return events


def scrape_queens_theatre(url, ua):
    """Scrape Queens Theatre in Flushing Meadows Corona Park (https://queenstheatre.org/events/)."""
    events = []
    seen = set()
    now_et = datetime.now(EASTERN)

    def _parse_qt_dt(date_text, time_text):
        # e.g. date_text="Thu Oct  29" or "Oct 29", time_text="8:00 PM"
        m_d = re.search(r"([A-Za-z]{3})\s+(\d{1,2})", date_text or "")
        if not m_d:
            return None
        mon_str, day_str = m_d.group(1), m_d.group(2)
        hour, minute = 19, 30
        m_t = re.search(r"(\d{1,2}):(\d{2})\s*(AM|PM)", time_text or "", re.I)
        if m_t:
            hour = int(m_t.group(1))
            minute = int(m_t.group(2))
            ampm = m_t.group(3).upper()
            if ampm == "PM" and hour != 12:
                hour += 12
            elif ampm == "AM" and hour == 12:
                hour = 0
        try:
            cand = datetime.strptime(f"{now_et.year} {mon_str} {int(day_str)}", "%Y %b %d")
            if cand.date() < (now_et.date() - timedelta(days=30)):
                cand = datetime.strptime(f"{now_et.year + 1} {mon_str} {int(day_str)}", "%Y %b %d")
            return datetime(cand.year, cand.month, cand.day, hour, minute, tzinfo=EASTERN)
        except Exception:
            return None

    try:
        resp = _SESSION.get(url, headers={"User-Agent": ua}, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        for wrapper in soup.select(".listItemWrapper"):
            a_desc = wrapper.select_one("a.desc")
            if not a_desc:
                continue
            t_el = a_desc.select_one("h3.title")
            if not t_el:
                continue
            title = t_el.get_text(" ", strip=True)
            if not title or is_placeholder_or_closed_event(title):
                continue

            sub_el = a_desc.select_one(".subtitle")
            subtitle = sub_el.get_text(" ", strip=True) if sub_el else ""
            href = a_desc.get("href") or "/events/"
            ev_url = urljoin("https://queenstheatre.org", href)

            genres = " ".join(g.get_text(" ", strip=True) for g in wrapper.select(".genres__link"))
            cat = guess_category(f"{title} {subtitle} {genres}", "theater")

            # Check if multi-date subshows exist via button[aria-controls]
            btn = wrapper.select_one("button[aria-controls]")
            sub_id = btn.get("aria-controls") if btn else None
            sub_container = soup.find(id=sub_id) if sub_id else None
            sub_items = sub_container.select("li.subshow") if sub_container else []

            dt_list = []
            if sub_items:
                for sub in sub_items:
                    d_el = sub.select_one(".date .start")
                    tm_el = sub.select_one(".time .start")
                    dt_val = _parse_qt_dt(
                        d_el.get_text(" ", strip=True) if d_el else "",
                        tm_el.get_text(" ", strip=True) if tm_el else "",
                    )
                    if dt_val:
                        dt_list.append(dt_val)
            if not dt_list:
                d_el = a_desc.select_one(".top-date .start")
                tm_el = a_desc.select_one(".top-date .time")
                dt_val = _parse_qt_dt(
                    d_el.get_text(" ", strip=True) if d_el else "",
                    tm_el.get_text(" ", strip=True) if tm_el else "",
                )
                if dt_val:
                    dt_list.append(dt_val)

            for dt in dt_list:
                key = (title.lower(), dt.strftime("%Y-%m-%d %H:%M"))
                if key in seen:
                    continue
                seen.add(key)
                events.append({
                    "name": title,
                    "date": dt.astimezone(timezone.utc).isoformat(),
                    "url": ev_url,
                    "venue": "Queens Theatre",
                    "price": None,
                    "category": cat,
                    "description": subtitle,
                    "lat": 40.7443,
                    "lng": -73.8444,
                    "address": "14 United Nations Ave S, Flushing Meadows Corona Park, Queens, NY",
                    "neighborhood": "Flushing Meadows",
                })
    except Exception as e:
        print(f"Error scraping Queens Theatre: {e}")
    return events


def scrape_brooklyn_brainery(url, ua):
    """Scrape in-person community classes and workshops from Brooklyn Brainery (Prospect Heights, Brooklyn)."""
    events = []
    seen = set()
    ny_tz = ZoneInfo("America/New_York")
    now = datetime.now(ny_tz)
    try:
        resp = _SESSION.get(url, headers={"User-Agent": ua}, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        for info in soup.select("div.course-info"):
            h3 = info.find("h3")
            p = info.find("p")
            if not h3 or not p:
                continue
            a = h3.find("a", href=True)
            if not a:
                continue
            title = (a.get_text(" ", strip=True) or "").strip()
            href = a["href"]
            if not title or "online" in title.lower() or "-online" in href.lower():
                continue

            dt_text = p.get_text(" ", strip=True)
            m = re.search(r"([A-Za-z]+)\s+(\d{1,2}),\s*(\d{1,2})(?::(\d{2}))?\s*(am|pm)", dt_text, re.I)
            if not m:
                continue
            mon_str, day_str, hr_str, min_str, ampm = m.groups()
            try:
                mon_num = datetime.strptime(mon_str[:3], "%b").month
            except ValueError:
                continue
            hr = int(hr_str)
            mn = int(min_str or 0)
            if ampm.lower() == "pm" and hr != 12:
                hr += 12
            elif ampm.lower() == "am" and hr == 12:
                hr = 0
            yr = now.year
            try:
                dt = datetime(yr, mon_num, int(day_str), hr, mn, tzinfo=ny_tz)
                if (now - dt).days > 60:
                    dt = datetime(yr + 1, mon_num, int(day_str), hr, mn, tzinfo=ny_tz)
            except ValueError:
                continue
            if dt < now:
                continue

            iso_dt = dt.astimezone(timezone.utc).isoformat()
            key = (title.lower(), iso_dt[:10])
            if key in seen:
                continue
            seen.add(key)

            ev_url = href if href.startswith("http") else f"https://brooklynbrainery.com{href}"
            events.append({
                "name": title,
                "date": iso_dt,
                "url": ev_url,
                "venue": "Brooklyn Brainery",
                "address": "190 Underhill Ave, Brooklyn, NY 11238",
                "neighborhood": "Prospect Heights",
                "lat": 40.6761,
                "lng": -73.9652,
                "price": None,
                "category": "community",
            })
    except Exception as e:
        print(f"Error scraping Brooklyn Brainery: {e}")
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

    # === NEIGHBORHOOD RUN CLUBS & SOCIAL WALKS ===
    ("North Brooklyn Runners", "https://northbrooklynrunners.org/", "sports", [
        ("NBR McCarren Park Track Tuesday Workout", "https://northbrooklynrunners.org/schedule/", 1, 19, 0, "Free"),
        ("NBR Williamsburg Bridge Run & Social", "https://northbrooklynrunners.org/schedule/", 3, 19, 0, "Free"),
        ("NBR Saturday Morning Long Run @ McCarren", "https://northbrooklynrunners.org/schedule/", 5, 8, 30, "Free"),
    ]),
    ("Midnight Runners NYC", "https://www.midnightrunners.com/cities/new-york", "sports", [
        ("Midnight Runners 10K Music Run & Social (Tuesday Night)", "https://www.midnightrunners.com/cities/new-york", 1, 19, 0, "Free"),
    ]),
    ("City Girls Who Walk NYC", "https://www.instagram.com/citygirlswhowalk/", "outdoors", [
        ("City Girls Who Walk Sunday Central Park Social Walk", "https://www.instagram.com/citygirlswhowalk/", 6, 12, 0, "Free"),
    ]),
    ("Queens Distance Runners", "https://qdrunners.org/", "sports", [
        ("QDR Track Tuesday @ Astoria Park Track", "https://qdrunners.org/", 1, 19, 0, "Free"),
        ("QDR Saturday Morning Queens Social Run", "https://qdrunners.org/", 5, 8, 0, "Free"),
    ]),
    ("Crown Heights Run Club", "https://www.instagram.com/crownheightsrunclub/", "sports", [
        ("Crown Heights Tuesday Prospect Park Loop Run", "https://www.instagram.com/crownheightsrunclub/", 1, 18, 30, "Free"),
        ("Crown Heights Saturday Morning Community Run", "https://www.instagram.com/crownheightsrunclub/", 5, 9, 0, "Free"),
    ]),
    ("Chinatown Runners", "https://www.instagram.com/chinatownrunners/", "sports", [
        ("Chinatown Runners Thursday Evening Social Run", "https://www.instagram.com/chinatownrunners/", 3, 18, 30, "Free"),
    ]),

    # === INDEPENDENT BOOKSHOP BOOK CLUBS & READING CIRCLES ===
    ("The Strand Book Store", "https://www.strandbooks.com/events", "books", [
        ("Strand Fiction & Non-Fiction Book Club", "https://www.strandbooks.com/events", 2, 19, 0, "Free RSVP"),
    ]),
    ("Books Are Magic", "https://www.booksaremagic.net/events", "books", [
        ("Books Are Magic Monthly Book Club (Cobble Hill)", "https://www.booksaremagic.net/events", 2, 19, 0, "Free RSVP"),
        ("Speculative Fiction Book Club (Montague)", "https://www.booksaremagic.net/events", 3, 19, 0, "Free RSVP"),
    ]),
    ("Greenlight Bookstore", "https://www.greenlightbookstore.com/events", "books", [
        ("Greenlight Fiction Book Club (Fort Greene)", "https://www.greenlightbookstore.com/events", 1, 19, 30, "Free"),
        ("Greenlight Non-Fiction Book Club (Fort Greene)", "https://www.greenlightbookstore.com/events", 3, 19, 30, "Free"),
    ]),
    ("The Astoria Bookshop", "https://astoriabookshop.com/events", "books", [
        ("Astoria Bookshop General Fiction Book Club", "https://astoriabookshop.com/events", 1, 19, 0, "Free"),
        ("Astoria Bookshop Feminist Book Club", "https://astoriabookshop.com/events", 3, 19, 0, "Free"),
    ]),
    ("Community Bookstore", "https://www.communitybookstore.net/events", "books", [
        ("Park Slope Community Book Club", "https://www.communitybookstore.net/events", 1, 19, 30, "Free"),
    ]),
    ("Yu & Me Books", "https://www.yuandmebooks.com/events", "books", [
        ("Yu & Me Community Book Club & Discussion", "https://www.yuandmebooks.com/events", 2, 18, 30, "Free RSVP"),
    ]),
    ("Bluestockings Cooperative", "https://bluestockings.com/events/", "books", [
        ("Bluestockings Queer & Feminist Reading Group", "https://bluestockings.com/events/", 3, 19, 0, "Free / Donation"),
    ]),

    # === BOARD GAME CLUBS, D&D & CHESS ===
    ("Hex & Company", "https://www.hexnyc.com/", "gaming", [
        ("Monday Night Open Board Game Social @ Hex & Co", "https://www.hexnyc.com/", 0, 18, 30, "$10 Game Pass"),
        ("D&D Adventurers League Night", "https://www.hexnyc.com/", 2, 18, 30, "$15"),
        ("Open Tabletop & RPG Social Night", "https://www.hexnyc.com/", 3, 18, 30, "$10"),
    ]),
    ("The Uncommons", "https://uncommonsnyc.com/", "gaming", [
        ("Casual Open Board Games & Social Night", "https://uncommonsnyc.com/", 1, 18, 0, "$10"),
        ("Magic: The Gathering Commander Night", "https://uncommonsnyc.com/", 3, 18, 30, "$10"),
    ]),
    ("The Brooklyn Strategist", "https://www.thebrooklynstrategist.com/", "gaming", [
        ("Adult Board Game Social Night", "https://www.thebrooklynstrategist.com/", 2, 19, 0, "$10"),
        ("Dungeons & Dragons Campaign Night", "https://www.thebrooklynstrategist.com/", 3, 19, 0, "$15"),
        ("Brooklyn Chess Club Open Play", "https://www.thebrooklynstrategist.com/", 4, 18, 30, "$10"),
    ]),
    ("Sip & Play", "https://www.sipnplaynyc.com/", "gaming", [
        ("Boba & Board Games Social Mixer", "https://www.sipnplaynyc.com/", 2, 18, 30, "$10"),
        ("D&D One-Shot Adventures @ Sip & Play", "https://www.sipnplaynyc.com/", 3, 19, 0, "$15"),
    ]),
    ("Washington Square Park", "https://www.nycgovparks.org/parks/washington-square-park", "gaming", [
        ("Washington Square Park Speed Chess & Casual Open Play", "https://www.nycgovparks.org/parks/washington-square-park", 5, 12, 0, "Free"),
        ("Washington Square Park Speed Chess & Casual Open Play", "https://www.nycgovparks.org/parks/washington-square-park", 6, 12, 0, "Free"),
    ]),
    ("Bryant Park", "https://bryantpark.org/activities/games", "gaming", [
        ("Bryant Park Outdoor Board Games & Ping Pong", "https://bryantpark.org/activities/games", 1, 12, 0, "Free"),
        ("Bryant Park Outdoor Board Games & Ping Pong", "https://bryantpark.org/activities/games", 3, 12, 0, "Free"),
        ("Bryant Park Outdoor Board Games & Ping Pong", "https://bryantpark.org/activities/games", 5, 12, 0, "Free"),
    ]),

    # === NYC PUB TRIVIA NIGHTS ===
    ("Pete's Candy Store", "https://www.petescandystore.com/", "gaming", [
        ("Pete's Quizzical Trivia Night (Williamsburg)", "https://www.petescandystore.com/", 2, 19, 30, "Free"),
    ]),
    ("The Craic", "https://www.thecraicbrooklyn.com/", "gaming", [
        ("The Craic Irish Pub Trivia Night (Williamsburg)", "https://www.thecraicbrooklyn.com/", 1, 20, 0, "Free"),
    ]),
    ("Sunswick 35/35", "https://www.sunswick3535bar.com/", "gaming", [
        ("Astoria Craft Beer Trivia @ Sunswick 35/35", "https://www.sunswick3535bar.com/", 2, 19, 30, "Free"),
    ]),
    ("The Boobie Trap", "https://www.instagram.com/theboobietrapbushwick/", "gaming", [
        ("Bushwick Monday Night Bar Trivia", "https://www.instagram.com/theboobietrapbushwick/", 0, 20, 0, "Free"),
    ]),
    ("The Dead Poet", "https://www.thedeadpoet.com/", "gaming", [
        ("Upper West Side Literary & Pop Trivia", "https://www.thedeadpoet.com/", 0, 20, 0, "Free"),
    ]),
    ("Slattery's Midtown Pub", "https://slatterysmidtownpub.com/", "gaming", [
        ("Midtown Thursday Pop Culture Trivia", "https://slatterysmidtownpub.com/", 3, 20, 0, "Free"),
    ]),

    # === TRADITIONAL IRISH SESSIONS & OPEN JAZZ JAMS ===
    ("The 11th St Bar", "https://11thstbar.com/", "music", [
        ("Sunday Night Traditional Irish Session (since 2006)", "https://11thstbar.com/", 6, 21, 0, "Free"),
    ]),
    ("Paddy Reilly's Music Bar", "https://paddyreillysmusicbar.us/", "music", [
        ("Thursday Night Live Irish Music Session", "https://paddyreillysmusicbar.us/", 3, 21, 0, "Free"),
        ("Sunday Afternoon Traditional Irish Session", "https://paddyreillysmusicbar.us/", 6, 17, 0, "Free"),
    ]),
    ("Hartley's", "https://hartleysbrooklyn.com/", "music", [
        ("Hartley's Sunday Traditional Irish Session (Clinton Hill)", "https://hartleysbrooklyn.com/", 6, 17, 0, "Free"),
    ]),
    ("An Beal Bocht Cafe", "https://anbealbochtcafe.com/", "music", [
        ("Sunday Traditional Irish Music Session (Riverdale)", "https://anbealbochtcafe.com/", 6, 16, 0, "Free"),
        ("Wednesday Night Open Mic Night", "https://anbealbochtcafe.com/", 2, 20, 0, "Free"),
    ]),
    ("The Ear Inn", "https://theearinn.com/", "music", [
        ("The EarRegulars Classic Sunday Jazz Session", "https://theearinn.com/", 6, 20, 0, "No Cover"),
        ("Wednesday Night Live Roots & Blues @ The Ear", "https://theearinn.com/", 2, 20, 0, "No Cover"),
    ]),
    ("Arthur's Tavern", "https://arthurstavern.nyc/", "music", [
        ("Arthur's Historic Live Jazz & Blues Hang", "https://arthurstavern.nyc/", 0, 19, 0, "No Cover"),
        ("Arthur's Historic Live Jazz & Blues Hang", "https://arthurstavern.nyc/", 1, 19, 0, "No Cover"),
        ("Arthur's Historic Live Jazz & Blues Hang", "https://arthurstavern.nyc/", 2, 19, 0, "No Cover"),
        ("Arthur's Historic Live Jazz & Blues Hang", "https://arthurstavern.nyc/", 3, 19, 0, "No Cover"),
        ("Arthur's Historic Live Jazz & Blues Hang", "https://arthurstavern.nyc/", 4, 19, 0, "No Cover"),
        ("Arthur's Historic Live Jazz & Blues Hang", "https://arthurstavern.nyc/", 5, 19, 0, "No Cover"),
        ("Arthur's Historic Live Jazz & Blues Hang", "https://arthurstavern.nyc/", 6, 19, 0, "No Cover"),
    ]),

    # === GROWNYC NEIGHBORHOOD GREENMARKETS ===
    ("Grand Army Plaza Greenmarket", "https://www.grownyc.org/greenmarket/brooklyn-grand-army-plaza", "food", [
        ("Grand Army Plaza Greenmarket (Prospect Park)", "https://www.grownyc.org/greenmarket/brooklyn-grand-army-plaza", 5, 8, 0, "Free"),
    ]),
    ("Fort Greene Park Greenmarket", "https://www.grownyc.org/greenmarket/brooklyn/fort-greene", "food", [
        ("Fort Greene Park Greenmarket", "https://www.grownyc.org/greenmarket/brooklyn/fort-greene", 5, 8, 0, "Free"),
    ]),
    ("Tompkins Square Greenmarket", "https://www.grownyc.org/greenmarket/manhattan/tompkins-square", "food", [
        ("Tompkins Square Greenmarket (East Village)", "https://www.grownyc.org/greenmarket/manhattan/tompkins-square", 6, 9, 0, "Free"),
    ]),
    ("Columbia University Greenmarket", "https://www.grownyc.org/greenmarket/manhattan/columbia-thurs", "food", [
        ("Columbia University Greenmarket (Broadway & 114th St)", "https://www.grownyc.org/greenmarket/manhattan/columbia-thurs", 3, 8, 0, "Free"),
        ("Columbia University Greenmarket (Broadway & 114th St)", "https://www.grownyc.org/greenmarket/manhattan/columbia-sun", 6, 8, 0, "Free"),
    ]),
    ("Jackson Heights Greenmarket", "https://www.grownyc.org/greenmarket/queens/jackson-heights", "food", [
        ("Jackson Heights Greenmarket (Travers Park)", "https://www.grownyc.org/greenmarket/queens/jackson-heights", 6, 8, 0, "Free"),
    ]),
    ("Sunnyside Greenmarket", "https://www.grownyc.org/greenmarket/queens/sunnyside", "food", [
        ("Sunnyside Greenmarket (Skillman Ave)", "https://www.grownyc.org/greenmarket/queens/sunnyside", 5, 8, 0, "Free"),
    ]),
    ("Forest Hills Greenmarket", "https://www.grownyc.org/greenmarket/queens/forest-hills", "food", [
        ("Forest Hills Greenmarket (71st Ave)", "https://www.grownyc.org/greenmarket/queens/forest-hills", 6, 8, 0, "Free"),
    ]),
    ("Brooklyn Borough Hall Greenmarket", "https://www.grownyc.org/greenmarket/brooklyn/borough-hall-sat", "food", [
        ("Brooklyn Borough Hall Greenmarket (Downtown Brooklyn)", "https://www.grownyc.org/greenmarket/brooklyn/borough-hall-sat", 5, 8, 0, "Free"),
        ("Brooklyn Borough Hall Greenmarket (Downtown Brooklyn)", "https://www.grownyc.org/greenmarket/brooklyn/borough-hall-tue", 1, 8, 0, "Free"),
    ]),
    ("79th Street Greenmarket", "https://www.grownyc.org/greenmarket/manhattan/79th-street", "food", [
        ("79th Street Greenmarket (Upper West Side @ AMNH)", "https://www.grownyc.org/greenmarket/manhattan/79th-street", 6, 9, 0, "Free"),
    ]),

    # === QUEENS NEIGHBORHOOD SPOTS: LIVE MUSIC, BREWERIES, COMEDY, BOOKSHOPS & OPEN STREETS ===
    ("Terraza 7", "https://terraza7.com/", "music", [
        ("Terraza 7 Open Mic Poetry & Acoustic Jam (Elmhurst / Jackson Heights)", "https://terraza7.com/", 1, 20, 0, "$10"),
        ("Terraza 7 Afro-Colombian & Latin Jazz Night", "https://terraza7.com/", 4, 21, 0, "$15–$20"),
        ("Terraza 7 Live Cumbia & Latin Folklore Night", "https://terraza7.com/", 5, 21, 0, "$15–$20"),
        ("Terraza 7 Sunday Jazz Jam Session", "https://terraza7.com/", 6, 20, 30, "$15"),
    ]),
    ("Bohemian Hall & Beer Garden", "https://bohemianhall.com/", "community", [
        ("Bohemian Hall Beer Garden Trivia Night (Astoria)", "https://bohemianhall.com/", 3, 19, 30, "Free"),
        ("Bohemian Hall Weekend Live Music in the Garden", "https://bohemianhall.com/", 5, 18, 0, "Free entry"),
        ("Bohemian Hall Sunday Beer Garden Hang & Acoustic Music", "https://bohemianhall.com/", 6, 15, 0, "Free entry"),
    ]),
    ("Grove 34", "https://www.grove34.com/", "comedy", [
        ("Grove 34 Astoria Stand-Up Comedy Showcase", "https://www.grove34.com/", 3, 20, 0, "$12–$15"),
        ("Grove 34 Friday Night Astoria Headliner Comedy", "https://www.grove34.com/", 4, 20, 0, "$15–$20"),
        ("Grove 34 Saturday Night Astoria Stand-Up & Improv", "https://www.grove34.com/", 5, 20, 0, "$15–$20"),
    ]),
    ("Fifth Hammer Brewing Co.", "https://www.fifthhammerbrewing.com/", "gaming", [
        ("Fifth Hammer LIC Taproom Run Club (Long Island City)", "https://www.fifthhammerbrewing.com/", 1, 19, 0, "Free"),
        ("Fifth Hammer Brewing Wednesday Taproom Trivia (LIC)", "https://www.fifthhammerbrewing.com/", 2, 19, 0, "Free"),
        ("Fifth Hammer Thursday Live Taproom Jazz & Funk Jam", "https://www.fifthhammerbrewing.com/", 3, 19, 0, "Free"),
    ]),
    ("Focal Point Beer Co.", "https://www.focalpointbeer.com/", "gaming", [
        ("Focal Point Beer Co. Taproom Trivia Night (Long Island City)", "https://www.focalpointbeer.com/", 3, 19, 0, "Free"),
    ]),
    ("SingleCut Beersmiths QNS", "https://singlecut.com/", "gaming", [
        ("SingleCut Beersmiths Rock & Pop Culture Trivia (Astoria)", "https://singlecut.com/", 3, 19, 30, "Free"),
        ("SingleCut QNS Saturday Taproom Live Vinyl & Bands", "https://singlecut.com/", 5, 17, 0, "Free"),
    ]),
    ("Alewife Brewing", "https://www.alewife.beer/", "gaming", [
        ("Alewife Brewing Sunnyside Taproom Trivia Night", "https://www.alewife.beer/", 2, 19, 0, "Free"),
        ("Alewife Brewing Friday Live Music & Craft Beer Night (Sunnyside)", "https://www.alewife.beer/", 4, 19, 30, "Free"),
    ]),
    ("Bar Freda", "https://www.instagram.com/barfredanyc/", "comedy", [
        ("Bar Freda Ridgewood Stand-Up Comedy & Drink Specials", "https://www.instagram.com/barfredanyc/", 2, 20, 0, "Free"),
        ("Bar Freda Ridgewood Underground DJ & Dance Party", "https://www.instagram.com/barfredanyc/", 4, 22, 0, "No Cover / $10"),
        ("Bar Freda Ridgewood Karaoke & Late Night Party", "https://www.instagram.com/barfredanyc/", 6, 21, 0, "Free"),
    ]),
    ("Nowadays", "https://nowadays.nyc/", "clubbing", [
        ("Nowadays Nonstop Saturday Night Dance Marathon (Ridgewood)", "https://nowadays.nyc/", 5, 22, 0, "$20–$30"),
        ("Mister Sunday @ Nowadays Backyard (Ridgewood)", "https://nowadays.nyc/", 6, 15, 0, "$20–$30"),
    ]),
    ("The Windjammer", "https://www.instagram.com/thewindjammerny/", "music", [
        ("The Windjammer Ridgewood Indie & Punk Showcase", "https://www.instagram.com/thewindjammerny/", 4, 20, 30, "$10–$15"),
        ("The Windjammer Ridgewood Late-Night Karaoke", "https://www.instagram.com/thewindjammerny/", 6, 21, 30, "Free"),
    ]),
    ("Albatross Bar", "https://www.albatrossastoria.com/", "theater", [
        ("Albatross Astoria Drag Bingo & Trivia Night", "https://www.albatrossastoria.com/", 3, 20, 30, "Free"),
        ("Albatross Astoria Weekend Drag Show & Karaoke", "https://www.albatrossastoria.com/", 4, 21, 30, "No Cover"),
        ("Albatross Astoria Saturday Night Drag Spectacular", "https://www.albatrossastoria.com/", 5, 22, 0, "No Cover"),
    ]),
    ("Donovan's Pub", "https://donovansny.com/", "music", [
        ("Woodside Traditional Irish Music & Pub Session @ Donovan's", "https://donovansny.com/", 3, 20, 0, "Free"),
    ]),
    ("The Wolfhound", "https://wolfhoundbar.com/", "gaming", [
        ("The Wolfhound Astoria Pub Trivia Night", "https://wolfhoundbar.com/", 1, 20, 0, "Free"),
        ("The Wolfhound Live Irish & Indie Music Night (Astoria)", "https://wolfhoundbar.com/", 5, 21, 0, "No Cover"),
    ]),
    ("The World's Borough Bookshop", "https://www.theworldsboroughbookshop.com/", "books", [
        ("World's Borough Bookshop Jackson Heights Reading Group", "https://www.theworldsboroughbookshop.com/", 3, 19, 0, "Free RSVP"),
        ("Saturday Bilingual Storytime & Author Talk @ World's Borough Bookshop", "https://www.theworldsboroughbookshop.com/", 5, 11, 0, "Free"),
    ]),
    ("Topos Bookstore Cafe", "https://www.toposbookstore.com/", "books", [
        ("Topos Bookstore Ridgewood Poetry & Author Reading Night", "https://www.toposbookstore.com/", 3, 19, 30, "Free"),
    ]),
    ("34th Avenue Open Street", "https://34aveopenstreets.com/", "community", [
        ("34th Ave Open Street Community Zumba & Fitness (Jackson Heights)", "https://34aveopenstreets.com/", 5, 10, 30, "Free"),
        ("34th Ave Open Street Chess, Crafts & Family Programming", "https://34aveopenstreets.com/", 6, 12, 0, "Free"),
    ]),
    ("31st Avenue Open Street", "https://31staveopenstreet.org/", "community", [
        ("31st Ave Open Street Astoria Weekend Market & Lawn Games", "https://31staveopenstreet.org/", 5, 12, 0, "Free"),
        ("31st Ave Open Street Astoria Community Music & Social", "https://31staveopenstreet.org/", 6, 13, 0, "Free"),
    ]),
    ("Woodside-Sunnyside Runners", "https://www.woodsidesunnysiderunners.com/", "sports", [
        ("Woodside-Sunnyside Runners Tuesday Evening Group Run", "https://www.woodsidesunnysiderunners.com/", 1, 19, 0, "Free"),
        ("Woodside-Sunnyside Runners Thursday Skillman Ave Social Run", "https://www.woodsidesunnysiderunners.com/", 3, 19, 0, "Free"),
        ("Woodside-Sunnyside Runners Saturday Morning Queens Bridge Run", "https://www.woodsidesunnysiderunners.com/", 5, 8, 30, "Free"),
    ]),
    ("Hellgate Road Runners", "https://www.hrronline.org/", "sports", [
        ("Hellgate Road Runners Astoria Park Evening Workout", "https://www.hrronline.org/", 2, 19, 0, "Free"),
        ("Hellgate Road Runners Saturday Astoria Park Long Run", "https://www.hrronline.org/", 5, 8, 0, "Free"),
    ]),
    ("Rockaway Track Club", "https://www.rockawaytc.org/", "sports", [
        ("Rockaway Beach Boardwalk Saturday Morning 5K & Social Run", "https://www.rockawaytc.org/", 5, 8, 30, "Free"),
    ]),
    ("NYC Resistor", "https://www.nycresistor.com/", "community", [
        ("NYC Resistor Hackerspace Public Craft Night (Boerum Hill)", "https://www.nycresistor.com/", 0, 19, 0, "Free"),
        ("NYC Resistor Open Make & Electronics Night (Brooklyn)", "https://www.nycresistor.com/", 3, 19, 0, "Free"),
    ]),
    ("Twenty Sided Store", "https://twentysidedstore.com/", "gaming", [
        ("Twenty Sided Store Williamsburg Board Game & RPG Meetup", "https://twentysidedstore.com/", 2, 18, 30, "$10"),
        ("Twenty Sided Store Friday Night Magic & Tabletop Social", "https://twentysidedstore.com/", 4, 18, 30, "$10–$15"),
        ("Twenty Sided Store Weekend Dungeons & Dragons One-Shots", "https://twentysidedstore.com/", 5, 13, 0, "$15"),
    ]),
    ("BrookLAN", "https://www.brooklan.com/", "gaming", [
        ("BrookLAN Bushwick Smash Bros & Fighting Game Community Night", "https://www.brooklan.com/", 2, 19, 0, "$10"),
        ("BrookLAN Bushwick Board Games, Trivia & Esports Social", "https://www.brooklan.com/", 3, 19, 30, "Free"),
    ]),
    ("Nook", "https://www.nookbk.com/", "gaming", [
        ("Nook Bushwick Community Board Game & Chess Meetup", "https://www.nookbk.com/", 1, 19, 0, "Free"),
        ("Nook Bushwick Neighborhood Trivia Night", "https://www.nookbk.com/", 2, 20, 0, "Free"),
    ]),
    ("McCarren Parkhouse", "https://www.mccarrenparkhouse.com/", "gaming", [
        ("North Brooklyn Chess Club Meetup @ McCarren Parkhouse", "https://www.mccarrenparkhouse.com/", 2, 18, 0, "Free"),
        ("McCarren Parkhouse Williamsburg Social Run & Coffee Club", "https://www.mccarrenparkhouse.com/", 5, 9, 30, "Free"),
    ]),
    ("The Center for Fiction", "https://centerforfiction.org/", "books", [
        ("Center for Fiction Fort Greene Literary Discussion & Reading", "https://centerforfiction.org/", 1, 19, 0, "Free RSVP"),
        ("Center for Fiction Bookstore Cafe Community Writing & Reading", "https://centerforfiction.org/", 3, 19, 0, "Free RSVP"),
    ]),
    ("Kew & Willow Books", "https://www.kewandwillow.com/", "books", [
        ("Kew & Willow Books Queens Indie Book Club Meetup (Kew Gardens)", "https://www.kewandwillow.com/", 2, 19, 0, "Free"),
    ]),
    ("Astoria Food Pantry", "https://www.astoriafoodpantry.com/", "gaming", [
        ("Astoria Food Pantry Thursday Community Board Game Night", "https://www.astoriafoodpantry.com/", 3, 18, 45, "Free"),
    ]),
    ("Cobblestones Pub", "https://cobblestonespub.com/", "gaming", [
        ("Queens Board Gamers Weekly Game Night @ Cobblestones Pub (Forest Hills)", "https://cobblestonespub.com/", 1, 18, 0, "Free"),
    ]),
]

ANNUAL_LANDMARK_EVENTS = [
    {
        "name": "53rd Annual Village Halloween Parade",
        "date": "2026-10-31T19:00:00-04:00",
        "venue": "Greenwich Village (6th Ave & Spring St)",
        "url": "https://halloween-nyc.com/",
        "price": "Free",
        "category": "party",
        "description": "NYC's iconic world-famous Halloween parade along 6th Avenue from Spring St to 16th St. Costumed participants join open marching.",
    },
    {
        "name": "Macy's Thanksgiving Day Balloon Inflation Event",
        "date": "2026-11-26T12:00:00-05:00",
        "venue": "American Museum of Natural History (Upper West Side)",
        "url": "https://www.macys.com/s/parade/",
        "price": "Free",
        "category": "community",
        "description": "Watch giant character balloons come to life the afternoon before the parade around the Museum of Natural History (77th to 81st St).",
    },
    {
        "name": "100th Annual Macy's Thanksgiving Day Parade",
        "date": "2026-11-27T08:30:00-05:00",
        "venue": "Upper West Side to Herald Square (6th Ave)",
        "url": "https://www.macys.com/s/parade/",
        "price": "Free",
        "category": "community",
        "description": "The historic 100th anniversary of Macy's Thanksgiving Day Parade, stepping off at 77th & Central Park West down to 34th St.",
    },
    {
        "name": "Rockefeller Center Christmas Tree Lighting Ceremony",
        "date": "2026-12-02T19:00:00-05:00",
        "venue": "Rockefeller Plaza",
        "url": "https://www.rockefellercenter.com/events/rockefeller-center-christmas-tree-lighting/",
        "price": "Free",
        "category": "community",
        "description": "Live musical performances and the ceremonial lighting of the world-famous Rockefeller Center Christmas Tree.",
    },
    {
        "name": "Times Square New Year's Eve Ball Drop & Celebration",
        "date": "2026-12-31T18:00:00-05:00",
        "venue": "Times Square Plaza",
        "url": "https://www.timessquarenyc.org/events/new-years-eve",
        "price": "Free",
        "category": "party",
        "description": "The global New Year's Eve celebration featuring live star performances, commercial hourly countdowns, and the midnight crystal ball drop.",
    },
    {
        "name": "Lunar New Year Chinatown Firecracker Ceremony & Cultural Festival",
        "date": "2027-02-17T11:00:00-05:00",
        "venue": "Sara D. Roosevelt Park (Chinatown)",
        "url": "https://betterchinatown.com/",
        "price": "Free",
        "category": "community",
        "description": "Traditional firecrackers to ward off evil spirits, lion dance troupes, martial arts, and cultural performances welcoming the New Year.",
    },
    {
        "name": "266th New York City St. Patrick's Day Parade",
        "date": "2027-03-17T11:00:00-04:00",
        "venue": "Fifth Avenue (44th St to 79th St)",
        "url": "https://www.nycstpatricksparade.org/",
        "price": "Free",
        "category": "community",
        "description": "The world's oldest and largest civilian parade, marching up Fifth Avenue past St. Patrick's Cathedral with bands, bagpipes, and Irish societies.",
    },
    {
        "name": "Museum Mile Festival 2027",
        "date": "2027-06-08T18:00:00-04:00",
        "venue": "Fifth Avenue (82nd St to 110th St)",
        "url": "https://www.museummilefestival.org/",
        "price": "Free",
        "category": "art",
        "description": "Fifth Avenue is closed to traffic for 28 blocks as 8 world-class museums (The Met, Guggenheim, Cooper Hewitt, El Museo, etc.) open free to the public.",
    },
    {
        "name": "45th Annual Coney Island Mermaid Parade",
        "date": "2027-06-19T13:00:00-04:00",
        "venue": "Coney Island (Surf Ave)",
        "url": "https://www.coneyisland.com/mermaidparade",
        "price": "Free",
        "category": "party",
        "description": "The nation's largest art parade celebrating marine mythology and artistic self-expression on the historic Coney Island Boardwalk.",
    },
    {
        "name": "NYC Pride March 2027",
        "date": "2027-06-27T12:00:00-04:00",
        "venue": "Fifth Avenue & Greenwich Village",
        "url": "https://www.nycpride.org/",
        "price": "Free",
        "category": "community",
        "description": "The monumental annual civil rights march from 25th St down 5th Ave past the Stonewall National Monument to 16th St.",
    },
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

    # Append upcoming landmark annual NYC events
    now_utc = datetime.now(timezone.utc)
    annual_evs = []
    for a in ANNUAL_LANDMARK_EVENTS:
        try:
            dt = datetime.fromisoformat(a["date"].replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=EASTERN)
            if dt.astimezone(timezone.utc) >= now_utc:
                annual_evs.append(a.copy())
        except Exception:
            continue
    if annual_evs:
        results.append({
            "venue": "NYC Landmark Celebrations & Annual Parades",
            "url": "https://www.nycgo.com/events/",
            "events": annual_evs,
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
    {"name": "Warsaw Brooklyn", "url": "https://www.warsawconcerts.com/", "ua": UA_CHROME, "scraper": scrape_warsaw, "default_category": "music"},
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
    {"name": "The Brooklyn Monarch", "url": "https://donyc.com/venues/the-brooklyn-monarch", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "music"},
    {"name": "The Meadows Brooklyn", "url": "https://donyc.com/venues/the-meadows", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "music"},
    {"name": "Brooklyn Paramount", "url": "https://donyc.com/venues/brooklyn-paramount", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "music"},
    {"name": "Under the K Bridge Park", "url": "https://donyc.com/venues/under-the-k-bridge-park", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "music"},
    {"name": "Roulette Intermedium", "url": "https://donyc.com/venues/roulette", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "music"},
    {"name": "National Sawdust", "url": "https://donyc.com/venues/national-sawdust", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "music"},
    {"name": "Xanadu Roller Arts", "url": "https://donyc.com/venues/xanadu", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "party"},
    {"name": "Saint Vitus Bar", "url": "https://donyc.com/venues/saint-vitus-bar", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "music"},
    {"name": "Bar LunÀtico", "url": "https://donyc.com/venues/lunatico", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "music"},
    {"name": "Alphaville", "url": "https://donyc.com/venues/alphaville", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "music"},
    {"name": "The Broadway (Bushwick)", "url": "https://donyc.com/venues/the-broadway", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "music"},
    {"name": "Sleepwalk", "url": "https://donyc.com/venues/sleepwalk", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "music"},
    {"name": "The Red Pavilion", "url": "https://donyc.com/venues/the-red-pavilion", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "theater"},
    {"name": "Purgatory", "url": "https://donyc.com/venues/purgatory", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "music"},
    {"name": "Mood Ring", "url": "https://donyc.com/venues/mood-ring", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "clubbing"},
    {"name": "Starr Bar", "url": "https://donyc.com/venues/starr-bar", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "clubbing"},
    {"name": "Eris Deep Space", "url": "https://donyc.com/venues/eris-deep-space", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "clubbing"},
    {"name": "St. Mazie", "url": "https://donyc.com/venues/st-mazie", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "music"},
    {"name": "Old Man Hustle BKLYN Comedy Club", "url": "https://donyc.com/venues/old-man-hustle-bklyn-comedy-club", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "comedy"},
    {"name": "Brooklyn Comedy Collective Pig Pen", "url": "https://donyc.com/venues/brooklyn-comedy-collective-pig-pen", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "comedy"},
    {"name": "Brooklyn Art Haus", "url": "https://donyc.com/venues/brooklyn-art-haus", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "theater"},
    {"name": "Crown Hill Theater", "url": "https://donyc.com/venues/crown-hill-theater", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "music"},
    {"name": "Mama Tried", "url": "https://donyc.com/venues/mama-tried", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "music"},
    {"name": "Brooklyn Storehouse", "url": "https://donyc.com/venues/brooklyn-storehouse", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "music"},
    {"name": "Liz's Book_Bar", "url": "https://donyc.com/venues/liz-s-book_bar", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "books"},
    {"name": "Alamo Drafthouse Cinema (Brooklyn)", "url": "https://donyc.com/venues/alamo-drafthouse", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "film"},

    # Queens
    {"name": "Forest Hills Stadium", "url": "https://donyc.com/venues/forest-hills-stadium", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "music"},
    {"name": "Noguchi Museum", "url": "https://donyc.com/venues/noguchi-museum", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "art"},
    {"name": "Museum of the Moving Image", "url": "https://movingimage.org/wp-json/tribe/events/v1/events?per_page=50", "ua": UA_CHROME, "scraper": scrape_tribe_events_api, "default_category": "film"},
    {"name": "Queens Botanical Garden", "url": "https://queensbotanical.org/wp-json/tribe/events/v1/events?per_page=50", "ua": UA_CHROME, "scraper": scrape_tribe_events_api, "default_category": "outdoors"},
    {"name": "Queens County Farm Museum", "url": "https://www.queensfarm.org/wp-json/tribe/events/v1/events?per_page=50", "ua": UA_CHROME, "scraper": scrape_tribe_events_api, "default_category": "outdoors"},
    {"name": "Louis Armstrong House Museum", "url": "https://www.louisarmstronghouse.org/wp-json/tribe/events/v1/events?per_page=50", "ua": UA_CHROME, "scraper": scrape_tribe_events_api, "default_category": "music"},
    {"name": "Queens Theatre", "url": "https://queenstheatre.org/events/", "ua": UA_CHROME, "scraper": scrape_queens_theatre, "default_category": "theater"},
    {"name": "Flushing Town Hall", "url": "https://donyc.com/venues/flushing-town-hall", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "music"},
    {"name": "MoMA PS1", "url": "https://donyc.com/venues/moma-ps1", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "art"},
    {"name": "Grove 34 Astoria", "url": "https://www.eventbrite.com/d/ny--astoria/grove-34/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "comedy"},
    {"name": "Culture Lab LIC", "url": "https://www.eventbrite.com/d/ny--long-island-city/culture-lab-lic/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "music"},
    {"name": "Bohemian Hall & Beer Garden (Astoria)", "url": "https://www.eventbrite.com/d/ny--astoria/bohemian-hall/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "community"},
    {"name": "Astoria Queens Events", "url": "https://www.eventbrite.com/d/ny--new-york/astoria-queens/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "community"},
    {"name": "Long Island City Queens Events", "url": "https://www.eventbrite.com/d/ny--new-york/long-island-city/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "community"},
    {"name": "Ridgewood Queens Events", "url": "https://www.eventbrite.com/d/ny--new-york/ridgewood-queens/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "community"},
    {"name": "Jackson Heights & Elmhurst Events", "url": "https://www.eventbrite.com/d/ny--new-york/jackson-heights/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "community"},
    {"name": "Sunnyside & Woodside Queens Events", "url": "https://www.eventbrite.com/d/ny--new-york/sunnyside-queens/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "community"},
    {"name": "Forest Hills Queens Events", "url": "https://www.eventbrite.com/d/ny--new-york/forest-hills-queens/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "community"},

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
    {"name": "Cafe Wha? (Greenwich Village)", "url": "https://donyc.com/venues/cafe-wha", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "music"},
    {"name": "Club Cumming (East Village)", "url": "https://donyc.com/venues/club-cumming", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "theater"},
    {"name": "Rough Trade NYC", "url": "https://donyc.com/venues/rough-trade-nyc", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "music"},
    {"name": "Bryant Park NYC", "url": "https://bryantpark.org/calendar", "ua": UA_CHROME, "scraper": scrape_bryant_park, "default_category": "outdoors"},
    {"name": "Bowery Palace", "url": "https://donyc.com/venues/bowery-palace", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "music"},
    {"name": "Pianos NYC (Lower East Side)", "url": "https://donyc.com/venues/pianos", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "music"},
    {"name": "The Rooftop at Pier 17", "url": "https://donyc.com/venues/the-rooftop-at-pier-17", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "music"},
    {"name": "Palladium Times Square", "url": "https://donyc.com/venues/palladium-times-square", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "music"},
    {"name": "Sid Gold's Request Room", "url": "https://donyc.com/venues/sid-gold-s-request-room", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "music"},
    {"name": "Marquee New York", "url": "https://donyc.com/venues/marquee-new-york", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "clubbing"},
    {"name": "The Stone", "url": "http://thestonenyc.com/calendar.php", "ua": UA_CHROME, "scraper": scrape_the_stone, "default_category": "music"},
    {"name": "The Center (LGBTQ+ Community Center)", "url": "https://donyc.com/venues/the-center", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "community"},
    {"name": "Groove", "url": "https://donyc.com/venues/groove", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "music"},
    {"name": "SoHo Playhouse", "url": "https://donyc.com/venues/soho-playhouse-nyc", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "theater"},
    {"name": "Duane Park", "url": "https://donyc.com/venues/duane-park", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "theater"},
    {"name": "Berlin Under A", "url": "https://donyc.com/venues/berlin", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "music"},
    {"name": "New York Comedy Club East Village", "url": "https://donyc.com/venues/new-york-comedy-club-east-village", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "comedy"},
    {"name": "The Cooper Union", "url": "https://donyc.com/venues/the-cooper-union", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "community"},
    {"name": "Somewhere Nowhere", "url": "https://donyc.com/venues/somewhere-nowhere", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "clubbing"},
    {"name": "The High Line", "url": "https://donyc.com/venues/the-high-line", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "outdoors"},
    {"name": "City Winery NYC", "url": "https://donyc.com/venues/city-winery", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "music"},
    {"name": "New York Comedy Club Midtown", "url": "https://donyc.com/venues/new-york-comedy-club-midtown", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "comedy"},
    {"name": "Nebula", "url": "https://donyc.com/venues/nebula", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "clubbing"},
    {"name": "The Broadway Comedy Club", "url": "https://donyc.com/venues/the-broadway-comedy-club", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "comedy"},
    {"name": "Don't Tell Mama", "url": "https://donyc.com/venues/donttellmama", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "music"},
    {"name": "The Paley Center for Media", "url": "https://donyc.com/venues/the-paley-center-for-media", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "art"},
    {"name": "The Sheen Center", "url": "https://donyc.com/venues/the-sheen-center-for-thought-culture", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "theater"},
    {"name": "Kaufman Music Center", "url": "https://donyc.com/venues/kaufman-music-center", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "music"},
    {"name": "Chamber Music Society of Lincoln Center", "url": "https://donyc.com/venues/chamber-music-society-of-lincoln-center", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "music"},
    {"name": "New York City Ballet", "url": "https://donyc.com/venues/new-york-city-ballet", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "dance"},
    {"name": "Lincoln Center Theater", "url": "https://donyc.com/venues/lincoln-center-theater", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "theater"},
    {"name": "Grand Bazaar NYC", "url": "https://grandbazaarnyc.org/", "ua": UA_CHROME, "scraper": scrape_grand_bazaar_nyc, "default_category": "community"},
    {"name": "New York Comedy Club Upper West Side", "url": "https://donyc.com/venues/new-york-comedy-club-upper-west-side", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "comedy"},
    {"name": "Comic Strip Live NYC", "url": "https://donyc.com/venues/comic-strip-live-nyc", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "comedy"},
    {"name": "Miller Theatre at Columbia University", "url": "https://www.millertheatre.com/events", "ua": UA_CHROME, "scraper": scrape_miller_theatre, "default_category": "music"},
    {"name": "Shrine Harlem", "url": "https://donyc.com/venues/shrine", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "music"},
    {"name": "Silvana NYC", "url": "https://donyc.com/venues/silvana-nyc", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "music"},
    {"name": "United Palace", "url": "https://donyc.com/venues/united-palace", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "theater"},

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
    {"name": "Film Forum", "url": "https://filmforum.org/films/now_playing", "ua": UA_CHROME, "scraper": scrape_film_forum, "default_category": "film"},
    {"name": "Nitehawk Cinema", "url": "https://donyc.com/venues/nitehawk-cinema", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "film"},
    {"name": "IFC Center", "url": "https://donyc.com/venues/ifc-center", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "film"},
    {"name": "Film at Lincoln Center", "url": "https://donyc.com/venues/film-at-lincoln-center", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "film"},
    {"name": "NYC Indie Film & Screenings", "url": "https://www.eventbrite.com/d/ny--new-york/indie-film/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "film"},
    {"name": "Metrograph NYC Screenings", "url": "https://www.eventbrite.com/d/ny--new-york/metrograph/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "film"},
    {"name": "Rooftop Films & Outdoor Cinema", "url": "https://www.eventbrite.com/d/ny--new-york/rooftop-films/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "film"},
    {"name": "Union Hall Brooklyn", "url": "https://www.eventbrite.com/api/v3/organizers/17899496497/events/?order_by=start_asc", "ua": UA_CHROME, "scraper": scrape_eventbrite_organizer, "default_category": "comedy"},
    {"name": "Smalls Jazz Club", "url": "https://www.smallslive.com/", "ua": UA_CHROME, "scraper": scrape_smalls_live, "default_category": "music"},

    # Legendary Greenwich Village & Lower East Side Music Halls
    {"name": "Joe's Pub (The Public Theater)", "url": "https://donyc.com/venues/joes-pub", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "music"},
    {"name": "The Bitter End (Greenwich Village)", "url": "https://donyc.com/venues/the-bitter-end", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "music"},
    {"name": "Arlene's Grocery (LES Rock & Karaoke)", "url": "https://donyc.com/venues/arlenes-grocery", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "music"},
    {"name": "Nublu 151 (Alphabet City)", "url": "https://donyc.com/venues/nublu-151", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "music"},
    {"name": "Drom NYC (East Village Global Music)", "url": "https://donyc.com/venues/drom", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "music"},
    {"name": "Terra Blues (Bleecker St)", "url": "https://donyc.com/venues/terra-blues", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "music"},
    {"name": "Symphony Space (Upper West Side)", "url": "https://www.symphonyspace.org/events", "ua": UA_CHROME, "scraper": scrape_symphony_space, "default_category": "theater"},

    # Comedy Clubs & Queens Performance Spaces
    {"name": "The Stand NYC", "url": "https://thestandnyc.com/shows", "ua": UA_CHROME, "scraper": scrape_the_stand_nyc, "default_category": "comedy"},
    {"name": "Tight Pants Comedy", "url": "https://www.eventbrite.com/api/v3/organizers/58671695943/events/?order_by=start_asc", "ua": UA_CHROME, "scraper": scrape_eventbrite_organizer, "default_category": "comedy"},
    {"name": "Broadway Comedy Club", "url": "https://www.eventbrite.com/d/ny--new-york/broadway-comedy-club/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "comedy"},
    {"name": "EastVille Comedy Club", "url": "https://donyc.com/venues/eastville-comedy-club", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "comedy"},
    {"name": "Greenwich Village Comedy Club", "url": "https://www.eventbrite.com/d/ny--new-york/greenwich-village-comedy-club/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "comedy"},
    {"name": "The Grisly Pear Comedy Club", "url": "https://www.eventbrite.com/d/ny--new-york/grisly-pear-comedy/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "comedy"},
    {"name": "St. Marks Comedy Club", "url": "https://www.eventbrite.com/d/ny--new-york/st-marks-comedy-club/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "comedy"},
    {"name": "Q.E.D. Astoria (Comedy & Arts)", "url": "https://qedastoria.com/apps/events/calendar", "ua": UA_CHROME, "scraper": scrape_qed_astoria, "default_category": "comedy"},
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
    {"name": "Meetup: NYC Running Clubs & 5K Socials", "url": "https://www.meetup.com/find/?keywords=running&location=us--ny--New%20York&source=EVENTS", "ua": UA_CHROME, "scraper": scrape_meetup, "default_category": "sports"},

    # Fashion, Sample Sales, Talks & Social Connection
    {"name": "NYC Fashion Events & Sample Sales", "url": "https://www.eventbrite.com/d/ny--new-york/sample-sale/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "community"},
    {"name": "NYC Fashion Shows & Runway", "url": "https://www.eventbrite.com/d/ny--new-york/fashion-show/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "community"},
    {"name": "NYC Talks & Lectures", "url": "https://www.eventbrite.com/d/ny--new-york/talks/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "community"},
    {"name": "NYC Panel Discussions & Symposiums", "url": "https://www.eventbrite.com/d/ny--new-york/panel-discussion/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "community"},
    {"name": "Skip the Small Talk NYC", "url": "https://www.skipthesmalltalk.com/store?format=json", "ua": UA_CHROME, "scraper": scrape_skip_the_small_talk, "default_category": "community"},

    # Literary Cafes, Book Bars, Breweries & Neighborhood Hubs
    {"name": "Bibliothèque Wine & Book Bar", "url": "https://www.eventbrite.com/d/ny--new-york/bibliotheque/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "books"},
    {"name": "Liz's Book Bar (Carroll Gardens)", "url": "https://www.eventbrite.com/d/ny--brooklyn/lizs-book-bar/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "books"},
    {"name": "Meetup: NYC Book Clubs & Literature Discussions", "url": "https://www.meetup.com/find/?keywords=book%20club&location=us--ny--New%20York&source=EVENTS", "ua": UA_CHROME, "scraper": scrape_meetup, "default_category": "books"},
    {"name": "Meetup: NYC Writers & Creative Storytelling", "url": "https://www.meetup.com/find/?keywords=writing&location=us--ny--New%20York&source=EVENTS", "ua": UA_CHROME, "scraper": scrape_meetup, "default_category": "books"},
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
    {"name": "Meetup: NYC Tech, AI & Developer Meetups", "url": "https://www.meetup.com/find/?keywords=tech&location=us--ny--New%20York&source=EVENTS", "ua": UA_CHROME, "scraper": scrape_meetup, "default_category": "community"},
    {"name": "Luma NYC", "url": "https://lu.ma/nyc", "ua": UA_CHROME, "scraper": scrape_luma, "default_category": "community"},
    {"name": "Meetup: NYC Language Exchange & Polyglot Socials", "url": "https://www.meetup.com/find/?keywords=language%20exchange&location=us--ny--New%20York&source=EVENTS", "ua": UA_CHROME, "scraper": scrape_meetup, "default_category": "community"},

    # Nightlife, Immersive Spectacle & Theatrical Circus
    {"name": "House of Yes (Circus & Dance)", "url": "https://donyc.com/venues/house-of-yes", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "party"},
    {"name": "House of Yes (Brooklyn Spectacle)", "url": "https://www.eventbrite.com/d/ny--brooklyn/house-of-yes/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "theater"},
    {"name": "The Slipper Room (NYC Burlesque)", "url": "https://donyc.com/venues/the-slipper-room", "ua": UA_CHROME, "scraper": scrape_donyc, "default_category": "theater"},
    {"name": "NYC Burlesque Shows & Cabaret", "url": "https://www.eventbrite.com/d/ny--new-york/burlesque/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "theater"},

    # Art Galleries, Food Festivals & Community Learning
    {"name": "Chelsea Art Gallery Openings", "url": "https://www.eventbrite.com/d/ny--new-york/chelsea-art-gallery/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "art"},
    {"name": "Japan Fes NYC (Street Food)", "url": "https://www.eventbrite.com/d/ny--new-york/japan-fes/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "food"},
    {"name": "Midnight Runners NYC (Social Run Club)", "url": "https://www.eventbrite.com/d/ny--new-york/midnight-runners/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "sports"},
    {"name": "Brooklyn Brainery (Community Classes)", "url": "https://brooklynbrainery.com/courses", "ua": UA_CHROME, "scraper": scrape_brooklyn_brainery, "default_category": "community"},
    {"name": "Meetup: NYC Photography Walks & Photo Tours", "url": "https://www.meetup.com/find/?keywords=photography&location=us--ny--New%20York&source=EVENTS", "ua": UA_CHROME, "scraper": scrape_meetup, "default_category": "art"},
    {"name": "Meetup: NYC Art Gallery Crawls & Openings", "url": "https://www.meetup.com/find/?keywords=art%20gallery&location=us--ny--New%20York&source=EVENTS", "ua": UA_CHROME, "scraper": scrape_meetup, "default_category": "art"},

    # Long-Form Improv, Sketch & Alternative Comedy
    {"name": "Magnet Theater (Improv & Sketch)", "url": "https://www.eventbrite.com/d/ny--new-york/magnet-theater/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "comedy"},
    {"name": "Asylum NYC (Alternative Comedy)", "url": "https://www.eventbrite.com/d/ny--new-york/asylum-nyc/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "comedy"},
    {"name": "Meetup: NYC Comedy, Improv & Open Mics", "url": "https://www.meetup.com/find/?keywords=improv&location=us--ny--New%20York&source=EVENTS", "ua": UA_CHROME, "scraper": scrape_meetup, "default_category": "comedy"},

    # Historic Cultural Music Halls
    {"name": "S.O.B.'s (Sounds of Brazil)", "url": "https://sobs.com/calendar/", "ua": UA_CHROME, "scraper": scrape_sobs, "default_category": "music"},

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
    {"name": "Meetup: NYC Live Jazz & Acoustic Sessions", "url": "https://www.meetup.com/find/?keywords=jazz&location=us--ny--New%20York&source=EVENTS", "ua": UA_CHROME, "scraper": scrape_meetup, "default_category": "music"},

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

    # Free Street Fairs, Cultural Fests & Outdoor Celebrations
    {"name": "Diwali at Times Square Festival", "url": "https://diwalitimessquare.com/", "ua": UA_CHROME, "scraper": scrape_diwali_times_square, "default_category": "community"},
    {"name": "Clearview Festival Productions (NYC Street Fairs)", "url": "https://vendors.clearviewfestival.com", "ua": UA_CHROME, "scraper": scrape_clearview_festivals, "default_category": "community"},
    {"name": "Diwali & South Asian Cultural Festivals", "url": "https://www.eventbrite.com/d/ny--new-york/diwali/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "community"},
    {"name": "Holi & Spring Heritage Festivals", "url": "https://www.eventbrite.com/d/ny--new-york/holi/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "community"},
    {"name": "Lunar New Year & Asian Heritage Fests", "url": "https://www.eventbrite.com/d/ny--new-york/lunar-new-year/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "community"},
    {"name": "NYC Parades & Processions", "url": "https://www.eventbrite.com/d/ny--new-york/parade/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "community"},
    {"name": "Latin & Caribbean Cultural Festivals", "url": "https://www.eventbrite.com/d/ny--new-york/latin-festival/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "community"},
    {"name": "Asia Society NYC Cultural Events", "url": "https://www.eventbrite.com/d/ny--new-york/asia-society/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "art"},
    {"name": "Japan Society NYC Cultural Programs", "url": "https://www.eventbrite.com/d/ny--new-york/japan-society/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "art"},
    {"name": "NYC Free Festivals & Celebrations", "url": "https://www.eventbrite.com/d/ny--new-york/free--festivals/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "community"},
    {"name": "NYC Street Fairs & Block Parties", "url": "https://www.eventbrite.com/d/ny--new-york/free--street-fair/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "community"},
    {"name": "NYC Free Community Festivals", "url": "https://www.eventbrite.com/d/ny--new-york/free--community--events/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "community"},
    {"name": "NYC Cultural & Heritage Festivals", "url": "https://www.eventbrite.com/d/ny--new-york/cultural-festival/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "community"},
    {"name": "NYC Free Food & Night Markets", "url": "https://www.eventbrite.com/d/ny--new-york/free--food-and-drink--festivals/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "food"},
    {"name": "Brooklyn Free Festivals & Fairs", "url": "https://www.eventbrite.com/d/ny--brooklyn/brooklyn-free-festivals/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "community"},
    {"name": "Queens Free Festivals & Markets", "url": "https://www.eventbrite.com/d/ny--queens/queens-free-festivals/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "community"},
    {"name": "Bronx Cultural & Community Events", "url": "https://www.eventbrite.com/d/ny--bronx/bronx-free-events/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "community"},
    {"name": "NYC Night Markets & Bazaars", "url": "https://www.eventbrite.com/d/ny--new-york/night-market/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "food"},
    {"name": "Queens Night Market", "url": "https://queensnightmarket.com/", "ua": UA_CHROME, "scraper": scrape_queens_night_market, "default_category": "food"},
    {"name": "NYC Street Fairs & Avenue Festivals", "url": "https://www.eventbrite.com/d/ny--new-york/street-fair/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "community"},
    {"name": "NYC Neighborhood Block Parties", "url": "https://www.eventbrite.com/d/ny--new-york/block-party/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "community"},
    {"name": "NYC Public Parties & Nightlife", "url": "https://www.eventbrite.com/d/ny--new-york/parties/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "party"},
    {"name": "NYC Halloween Celebrations & Parades", "url": "https://www.eventbrite.com/d/ny--new-york/halloween-parties/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "party"},
    {"name": "NYC Food & Wine Festivals", "url": "https://www.eventbrite.com/d/ny--new-york/food-festivals/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "food"},
    {"name": "NYC Art Festivals & Open Studios", "url": "https://www.eventbrite.com/d/ny--new-york/art-festivals/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "art"},
    {"name": "NYC Indie Craft Fairs & Pop-up Markets", "url": "https://www.eventbrite.com/d/ny--new-york/craft-fair/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "community"},

    # Area BIDs, Public Conservancies & Government Feeds
    {"name": "Lincoln Square BID (Columbus Circle)", "url": "https://www.lincolnsquarebid.org/events", "ua": UA_CHROME, "scraper": scrape_lincoln_square_bid, "default_category": "art"},
    {"name": "Columbus Circle District Events", "url": "https://www.eventbrite.com/d/ny--new-york/columbus-circle/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "community"},
    {"name": "Downtown Brooklyn Partnership", "url": "https://www.eventbrite.com/d/ny--brooklyn/downtown-brooklyn-partnership/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "community"},
    {"name": "Meatpacking District Events", "url": "https://www.eventbrite.com/d/ny--new-york/meatpacking-district/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "community"},
    {"name": "Governors Island Events", "url": "https://www.eventbrite.com/d/ny--new-york/governors-island/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "outdoors"},
    {"name": "Times Square District Events", "url": "https://www.eventbrite.com/d/ny--new-york/times-square/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "community"},
    {"name": "Battery Park City Events", "url": "https://www.eventbrite.com/d/ny--new-york/battery-park-city/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "outdoors"},

    # Off-Broadway Theaters, Plays & Musicals
    {"name": "NYC Off-Broadway Shows", "url": "https://www.eventbrite.com/d/ny--new-york/off-broadway/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "theater"},
    {"name": "NYC Musicals & Musical Theatre", "url": "https://www.eventbrite.com/d/ny--new-york/musical/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "theater"},
    {"name": "NYC Plays & Drama", "url": "https://www.eventbrite.com/d/ny--new-york/plays/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "theater"},
    {"name": "NYC Improv & Alternative Comedy", "url": "https://www.eventbrite.com/d/ny--new-york/improv/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "comedy"},

    # Board Game Clubs, Tabletop RPGs & Social Meetups
    {"name": "Chess Place NYC", "url": "https://www.eventbrite.com/api/v3/organizers/115357260611/events/?order_by=start_asc&expand=venue", "ua": UA_CHROME, "scraper": scrape_eventbrite_organizer, "default_category": "gaming"},
    {"name": "NYC Board Games & Tabletop", "url": "https://www.eventbrite.com/d/ny--new-york/board-games/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "gaming"},
    {"name": "Brooklyn Board Games & Socials", "url": "https://www.eventbrite.com/d/ny--brooklyn/brooklyn-board-games/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "gaming"},
    {"name": "NYC Tabletop RPG & D&D", "url": "https://www.eventbrite.com/d/ny--new-york/tabletop/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "gaming"},
    {"name": "NYC Social Meetups & Mixers", "url": "https://www.eventbrite.com/d/ny--new-york/meetup/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "community"},
    {"name": "NYC Language Exchange & Culture Meetups", "url": "https://www.eventbrite.com/d/ny--new-york/language-exchange/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "community"},

    # Live Jazz Clubs, Acoustic Sessions & Historic Bars
    {"name": "NYC Live Jazz Sessions", "url": "https://www.eventbrite.com/d/ny--new-york/jazz/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "music"},
    {"name": "Brooklyn Live Jazz & Blues", "url": "https://www.eventbrite.com/d/ny--brooklyn/brooklyn-jazz/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "music"},
    {"name": "NYC Speakeasy & Acoustic Sessions", "url": "https://www.eventbrite.com/d/ny--new-york/acoustic/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "music"},

    # Brooklyn & Queens Local Meetups, Book Clubs, Board Games & Community Groups
    {"name": "Brooklyn Social Meetups & Mixers", "url": "https://www.eventbrite.com/d/ny--brooklyn/brooklyn-meetup/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "community"},
    {"name": "Brooklyn Book Clubs & Literary Nights", "url": "https://www.eventbrite.com/d/ny--brooklyn/brooklyn-book-club/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "books"},
    {"name": "Brooklyn Run Clubs & Fitness Meetups", "url": "https://www.eventbrite.com/d/ny--brooklyn/brooklyn-run-club/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "sports"},
    {"name": "Brooklyn Bar Trivia & Game Nights", "url": "https://www.eventbrite.com/d/ny--brooklyn/brooklyn-trivia/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "gaming"},
    {"name": "Queens Social Meetups & Mixers", "url": "https://www.eventbrite.com/d/ny--queens/queens-meetup/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "community"},
    {"name": "Queens Trivia & Game Nights", "url": "https://www.eventbrite.com/d/ny--queens/queens-trivia/", "ua": UA_CHROME, "scraper": scrape_eventbrite_jsonld, "default_category": "gaming"},
    {"name": "Meetup: Brooklyn Social & Neighborhood Mixers", "url": "https://www.meetup.com/find/?keywords=Brooklyn&location=us--ny--Brooklyn&source=EVENTS", "ua": UA_CHROME, "scraper": scrape_meetup, "default_category": "community"},
    {"name": "Meetup: Brooklyn Book Clubs & Reading Groups", "url": "https://www.meetup.com/find/?keywords=Brooklyn%20book%20club&location=us--ny--Brooklyn&source=EVENTS", "ua": UA_CHROME, "scraper": scrape_meetup, "default_category": "books"},
    {"name": "Meetup: Brooklyn Board Games & Tabletop", "url": "https://www.meetup.com/find/?keywords=Brooklyn%20board%20games&location=us--ny--Brooklyn&source=EVENTS", "ua": UA_CHROME, "scraper": scrape_meetup, "default_category": "gaming"},
    {"name": "Meetup: Brooklyn Running & Walking Clubs", "url": "https://www.meetup.com/find/?keywords=Brooklyn%20run&location=us--ny--Brooklyn&source=EVENTS", "ua": UA_CHROME, "scraper": scrape_meetup, "default_category": "sports"},
    {"name": "Meetup: Brooklyn Tech, AI & Developers", "url": "https://www.meetup.com/find/?keywords=Brooklyn%20tech&location=us--ny--Brooklyn&source=EVENTS", "ua": UA_CHROME, "scraper": scrape_meetup, "default_category": "community"},
    {"name": "Meetup: Williamsburg & Greenpoint Socials", "url": "https://www.meetup.com/find/?keywords=Williamsburg&location=us--ny--Brooklyn&source=EVENTS", "ua": UA_CHROME, "scraper": scrape_meetup, "default_category": "community"},
    {"name": "Meetup: Park Slope & Prospect Park Community", "url": "https://www.meetup.com/find/?keywords=Park%20Slope&location=us--ny--Brooklyn&source=EVENTS", "ua": UA_CHROME, "scraper": scrape_meetup, "default_category": "community"},
    {"name": "Meetup: Bushwick Creative & Social Meetups", "url": "https://www.meetup.com/find/?keywords=Bushwick&location=us--ny--Brooklyn&source=EVENTS", "ua": UA_CHROME, "scraper": scrape_meetup, "default_category": "community"},
    {"name": "Meetup: Queens Neighborhood Socials & Mixers", "url": "https://www.meetup.com/find/?keywords=Queens&location=us--ny--Astoria&source=EVENTS", "ua": UA_CHROME, "scraper": scrape_meetup, "default_category": "community"},
    {"name": "Meetup: Astoria Community & Social Meetups", "url": "https://www.meetup.com/find/?keywords=Astoria&location=us--ny--Astoria&source=EVENTS", "ua": UA_CHROME, "scraper": scrape_meetup, "default_category": "community"},
    {"name": "Meetup: Flushing Tech, Food & Language Meetups", "url": "https://www.meetup.com/find/?keywords=Flushing&location=us--ny--Flushing&source=EVENTS", "ua": UA_CHROME, "scraper": scrape_meetup, "default_category": "community"},
    {"name": "Meetup: Sunnyside, Woodside & Jackson Heights", "url": "https://www.meetup.com/find/?keywords=Sunnyside&location=us--ny--Sunnyside&source=EVENTS", "ua": UA_CHROME, "scraper": scrape_meetup, "default_category": "community"},
    {"name": "Meetup: Queens Board Gamers Group", "url": "https://www.meetup.com/queens-board-gamers-group/events/", "ua": UA_CHROME, "scraper": scrape_meetup, "default_category": "gaming"},
    {"name": "Meetup: Tabletop Tuesday Sunnyside Game Night", "url": "https://www.meetup.com/tabletop-tuesday/events/", "ua": UA_CHROME, "scraper": scrape_meetup, "default_category": "gaming"},
    {"name": "Meetup: Prospect Park Board Gaming Club", "url": "https://www.meetup.com/prospect-park-board-gaming-club/events/", "ua": UA_CHROME, "scraper": scrape_meetup, "default_category": "gaming"},
    {"name": "Meetup: The Brooklyn Board Games Group", "url": "https://www.meetup.com/the-brooklyn-board-games-meetup-group/events/", "ua": UA_CHROME, "scraper": scrape_meetup, "default_category": "gaming"},
    {"name": "Meetup: Brooklyn Strategist Evening Games", "url": "https://www.meetup.com/Brooklyn-Strategist-Evening-Events-Games-Meetup/events/", "ua": UA_CHROME, "scraper": scrape_meetup, "default_category": "gaming"},
    {"name": "Meetup: Astoria Runners", "url": "https://www.meetup.com/astoriarunners/events/", "ua": UA_CHROME, "scraper": scrape_meetup, "default_category": "sports"},
    {"name": "Meetup: RUN LIC (Long Island City Runners)", "url": "https://www.meetup.com/longislandcity-runners/events/", "ua": UA_CHROME, "scraper": scrape_meetup, "default_category": "sports"},
    {"name": "Meetup: Woodside-Sunnyside Runners", "url": "https://www.meetup.com/woodside-sunnyside-runners/events/", "ua": UA_CHROME, "scraper": scrape_meetup, "default_category": "sports"},
    {"name": "Meetup: CALLEFUT Queens Soccer Community", "url": "https://www.meetup.com/new-york-nyc-soccer-meetup-group/events/", "ua": UA_CHROME, "scraper": scrape_meetup, "default_category": "sports"},
    {"name": "Meetup: Queens Futsal Club", "url": "https://www.meetup.com/queensfutsalclub/events/", "ua": UA_CHROME, "scraper": scrape_meetup, "default_category": "sports"},
    {"name": "Meetup: Brooklyn / Queens Coed Soccer Club", "url": "https://www.meetup.com/Bushwick-Inlet-Brooklyn-Coed-Soccer-Meetup/events/", "ua": UA_CHROME, "scraper": scrape_meetup, "default_category": "sports"},
    {"name": "Meetup: Flushing Tech Hackathons & Meetups", "url": "https://www.meetup.com/flushingtech/events/", "ua": UA_CHROME, "scraper": scrape_meetup, "default_category": "community"},
    {"name": "Meetup: Astoria Tech Meetup", "url": "https://www.meetup.com/astoria-tech-meetup/events/", "ua": UA_CHROME, "scraper": scrape_meetup, "default_category": "community"},
    {"name": "Meetup: Brooklyn Women's Writing Group", "url": "https://www.meetup.com/bkwomenswritinggroup/events/", "ua": UA_CHROME, "scraper": scrape_meetup, "default_category": "books"},
    {"name": "Meetup: Bushwick Writers Group", "url": "https://www.meetup.com/Bushwick-Writers-Meetup/events/", "ua": UA_CHROME, "scraper": scrape_meetup, "default_category": "books"},
    {"name": "Meetup: Forest Hills Book Group", "url": "https://www.meetup.com/forest-hills-book-group/events/", "ua": UA_CHROME, "scraper": scrape_meetup, "default_category": "books"},
    {"name": "Meetup: Silent Book Club NYC & Brooklyn", "url": "https://www.meetup.com/silentbookclubnyc/events/", "ua": UA_CHROME, "scraper": scrape_meetup, "default_category": "books"},
    {"name": "Meetup: Shut Up & Write! NYC (Brooklyn & Queens)", "url": "https://www.meetup.com/shutupandwritenyc/events/", "ua": UA_CHROME, "scraper": scrape_meetup, "default_category": "books"},
    {"name": "Meetup: Williamsburg French & Spanish Conversations", "url": "https://www.meetup.com/williamsburg-french-conversation-meetup/events/", "ua": UA_CHROME, "scraper": scrape_meetup, "default_category": "community"},
    {"name": "Meetup: Conversation française à Brooklyn", "url": "https://www.meetup.com/conversation-francaise-a-brooklyn/events/", "ua": UA_CHROME, "scraper": scrape_meetup, "default_category": "community"},
    {"name": "Meetup: Brooklyn Traditional Slow Jam (Park Slope)", "url": "https://www.meetup.com/brooklyn-traditional-slow-jam/events/", "ua": UA_CHROME, "scraper": scrape_meetup, "default_category": "music"},
    {"name": "Meetup: Brooklyn Ethical Culture Community (Park Slope)", "url": "https://www.meetup.com/brooklyn-society-for-ethical-culture/events/", "ua": UA_CHROME, "scraper": scrape_meetup, "default_category": "community"},
    {"name": "Meetup: Mindful Astoria Meditation Community", "url": "https://www.meetup.com/Mindful-Astoria/events/", "ua": UA_CHROME, "scraper": scrape_meetup, "default_category": "community"},
    {"name": "Meetup: Friends from Bayside & Queens Socials", "url": "https://www.meetup.com/hangout-in-queens/events/", "ua": UA_CHROME, "scraper": scrape_meetup, "default_category": "community"},
    {"name": "Meetup: Cucala Dance LIC Salsa Classes & Socials", "url": "https://www.meetup.com/cucala-dance-company/events/", "ua": UA_CHROME, "scraper": scrape_meetup, "default_category": "dance"},
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
_last_known_good = {}
_cache = {"ts": 0, "data": None}


def _init_warm_cache():
    """Warm last-known-good map and disk venue cache from events.json on disk if available."""
    json_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "events.json")
    if not os.path.exists(json_path):
        return

    try:
        with open(json_path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        venues = payload.get("venues") if isinstance(payload, dict) else payload
        generated_at = payload.get("generated_at") if isinstance(payload, dict) else None

        file_ts = os.path.getmtime(json_path)
        if generated_at:
            try:
                dt = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
                file_ts = dt.timestamp()
            except Exception:
                pass

        if venues and isinstance(venues, list):
            for v in venues:
                vname = v.get("venue")
                evs = v.get("events")
                if vname and evs is not None:
                    valid_evs = [e for e in evs if not is_placeholder_or_closed_event(e.get("name"))]
                    _last_known_good[vname] = valid_evs
                    # If venue cache does not exist on disk, seed it with events and timestamp from events.json
                    cpath = _venue_cache_path(vname)
                    if not os.path.exists(cpath):
                        try:
                            with open(cpath, "w", encoding="utf-8") as cf:
                                json.dump({
                                    "ts": file_ts,
                                    "venue": vname,
                                    "duration": v.get("duration", 0.0),
                                    "events": valid_evs
                                }, cf, ensure_ascii=False)
                        except Exception:
                            pass
    except Exception:
        pass


_init_warm_cache()


def _scrape_one(v, force=False):
    vname = v["name"]
    ttl = _get_venue_ttl(vname, v=v)

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
        events = [e for e in events if not is_placeholder_or_closed_event(e.get("name"))]
        for e in events:
            if not e.get("venue"):
                e["venue"] = vname
            existing_cat = e.get("category")
            if not existing_cat or existing_cat == "other":
                e["category"] = guess_category(e.get("name"), v.get("default_category") or "community", venue=e.get("venue"))
            else:
                e["category"] = guess_category(e.get("name"), existing_cat, venue=e.get("venue"))

        dur = round(time.time() - t0, 2)
        if events:
            _last_known_good[vname] = events
            _save_venue_cache(vname, events, duration=dur)
        else:
            # Scraper returned 0 events: preserve previous cached events if available
            stale_cache = _load_venue_cache(vname, max_age=None)
            prev = (stale_cache.get("events") if stale_cache else None) or _last_known_good.get(vname, [])
            prev_evs = [e for e in prev if not is_placeholder_or_closed_event(e.get("name")) and _is_within_horizon(e, max_days=HORIZON_DAYS)]
            if prev_evs:
                events = prev_evs
            else:
                _save_venue_cache(vname, events, duration=dur)

        # Filter events to rolling horizon window
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
        # Error resilience: fall back to existing cache or last known good if network/Cloudflare fails
        stale_cache = _load_venue_cache(vname, max_age=None)
        prev = (stale_cache.get("events") if stale_cache else None) or _last_known_good.get(vname, [])
        if prev:
            events = [e for e in prev if _is_within_horizon(e, max_days=HORIZON_DAYS) and not is_placeholder_or_closed_event(e.get("name"))]
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


def _load_community_events():
    """Load community-submitted events from community_events.json."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "community_events.json")
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list) or not data:
            return []

        events = []
        for e in data:
            if not e.get("name") or not e.get("venue"):
                continue
            name = str(e["name"]).strip()
            if is_placeholder_or_closed_event(name):
                continue
            venue = str(e["venue"]).strip()
            cat = e.get("category") or guess_category(name, "community", venue=venue)
            events.append({
                "name": name,
                "date": e.get("date"),
                "url": e.get("url") or "",
                "venue": venue,
                "price": e.get("price"),
                "category": cat,
                "_is_community": True,
                "_source_venue": "Community Submission",
                "address": e.get("address") or "",
            })
        if not events:
            return []
        return [{"venue": "Community Submissions", "url": "", "events": events, "error": None}]
    except Exception as err:
        print(f"Warning: could not load community events: {err}")
        return []


def get_all_events(force=False):
    now = time.time()
    if not force and _cache["data"] and (now - _cache["ts"] < CACHE_SECONDS):
        return _cache["data"]

    def _worker(v):
        return _scrape_one(v, force=force)

    with ThreadPoolExecutor(max_workers=10) as ex:
        results = list(ex.map(_worker, VENUES))

    # Add recurring events (expanded for 8 weeks / 56 days)
    results.extend(_expand_manual_recurring(weeks=8))
    results.extend(_load_community_events())

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "venues": results,
        "weather": fetch_nyc_weather(),
        "luckyseat": fetch_luckyseat_nyc(),
    }
    _cache["ts"] = now
    _cache["data"] = payload
    return payload
