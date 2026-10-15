"""NYC Events — HTML rendering and template logic."""

import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from html import escape
from urllib.parse import quote

from scrapers import (
    EASTERN,
    CATEGORY_BUCKETS,
    CATEGORY_STYLES,
    DEAL_LINKS,
    STATIC_LINKS,
    category_bucket,
    fetch_nyc_weather,
    fetch_luckyseat_nyc,
)


CITY_RULES = [
    ("brooklyn", (
        "brooklyn bowl", "elsewhere", "good room", "public records",
        "the bell house", "bell house", "littlefield", "music hall of williamsburg",
        "brooklyn steel", "warsaw", "brooklyn museum", "bric", "brooklyn flea",
        "smorgasburg (williamsburg)", "smorgasburg (prospect park)", "industry city",
        "baby's all right", "babys all right", "sultan room", "c'mon everybody",
        "market hotel", "our wicked lady", "barclays center", "barclays", "kings theatre",
        "brooklyn academy of music", "bam", "st. ann's warehouse", "pioneer works",
        "pete's candy store", "skinny dennis", "carmelo's", "union pool",
        "books are magic", "greenlight bookstore", "greenlight",
        "brooklyn public library", "bpl", "nitehawk cinema", "nitehawk", "union hall",
        "wonderville", "smashville", "the tiny cupboard", "tiny cupboard",
        "brooklyn comedy collective", "bcc",
        "house of yes", "brooklyn strategist", "the brooklyn strategist", "brooklyn brainery",
        "3 dollar bill", "three dollar bill",
        "superior ingredients", "bossa nova civic club", "bossa nova", "jupiter disco",
        "salsa salsa dance", "salsa salsa",
        "brooklyn trivia",
        "brooklyn", "bklyn", "williamsburg", "bushwick", "greenpoint", "dumbo",
        "bed-stuy", "bedford-stuyvesant", "crown heights", "prospect heights",
        "park slope", "gowanus", "red hook", "flatbush", "bay ridge",
        "fort greene", "clinton hill", "cobble hill", "carroll gardens",
        "boerum hill", "prospect park", "sunset park", "coney island",
    )),
    ("queens", (
        "knockdown center", "tv eye", "trans-pecos", "nowadays",
        "forest hills stadium", "forest hills", "citi field", "flushing meadows",
        "moma ps1", "museum of the moving image", "socrates sculpture",
        "kaufman astoria", "terrasa 7", "queens public library", "qpl",
        "q.e.d.", "qed astoria", "qed",
        "astoria trivia", "queens trivia",
        "queens", "astoria", "long island city", "lic", "flushing",
        "ridgewood", "sunnyside", "jackson heights", "woodside",
        "bayside", "jamaica, ny", "rockaway", "far rockaway",
    )),
    ("bronx", (
        "yankee stadium", "bronx zoo", "new york botanical garden", "nybg",
        "wave hill", "woodlawn", "bronx brewery",
        "bronx", "the bronx", "south bronx", "riverdale", "concourse",
        "fordham", "pelham", "mott haven", "city island",
    )),
    ("staten_island", (
        "snug harbor", "st. george theatre", "richmond county bank",
        "conference house",
        "staten island", "st. george", "tompkinsville", "new brighton",
    )),
    ("manhattan", (
        "bowery ballroom", "mercury lounge", "webster hall", "terminal 5",
        "irving plaza", "racket nyc", "racket", "le poisson rouge", "lpr",
        "blue note", "caveat", "apollo theater", "apollo",
        "madison square garden", "msg", "radio city", "beacon theatre",
        "carnegie hall", "lincoln center", "village vanguard", "dizzy's",
        "comedy cellar", "central park", "summerstage", "the skint",
        "union square greenmarket", "union square", "grand bazaar nyc", "grand bazaar",
        "the met", "metropolitan museum", "moma", "whitney", "guggenheim",
        "high line", "pier 17", "pier 57", "little island", "chelsea market",
        "town hall", "sony hall", "city winery nyc", "city winery",
        "cutting room", "joe's pub", "public theater", "film forum",
        "strand book store", "strand bookstore", "strand", "mcnally jackson",
        "bluestockings", "p&t knitwear", "housing works",
        "kgb bar", "the bitter end", "bitter end", "arlene's grocery", "arlenes grocery",
        "nublu", "drom", "terra blues", "symphony space", "new york comedy club",
        "tight pants comedy", "tight pants", "greenwich village comedy", "grisly pear", "st. marks comedy",
        "hex & company", "hex and company", "the uncommons", "uncommons",
        "chelsea art gallery", "chelsea gallery", "japan fes", "midnight runners",
        "magnet theater", "asylum nyc", "asylum",
        "new york public library", "nypl",
        "ifc center", "smalls jazz club", "smalls jazz", "manhattan trivia",
        "os nyc", "sobs", "s.o.b.",
        "gonzalez y gonzalez", "swing 46", "the back room", "back room",
        "mona's", "monas", "pieces bar", "the stonewall inn", "stonewall inn", "stonewall",
        "trivia a.d.", "trivia ad", "barcade",
        "somewhere nowhere", "the dl", "harbor nyc", "harbor new york", "230 fifth", "slate nyc", "slate ny", "nebula",
        "taj lounge", "taj ii", "club cache", "cache", "iguana nyc", "iguana", "cucala dance", "cucala",
        "soho", "tribeca", "noho", "nolita", "chinatown", "lower east side", "les",
        "east village", "west village", "greenwich village", "chelsea",
        "meatpacking", "gramercy", "flatiron", "midtown", "times square",
        "hell's kitchen", "upper west side", "uws", "upper east side", "ues",
        "harlem", "morningside heights", "washington heights", "inwood",
        "battery park", "financial district", "fidi",
        "manhattan", "new york, ny", ", ny", "new york", "nyc",
    )),
]

CITY_LABELS = {
    "manhattan": "Manhattan",
    "brooklyn": "Brooklyn",
    "queens": "Queens",
    "bronx": "The Bronx",
    "staten_island": "Staten Island",
    "other": "Tri-State / Other",
}

CITY_COLORS = {
    "manhattan": "#5d9bff",
    "brooklyn": "#e05a6b",
    "queens": "#f29e4c",
    "bronx": "#4ade80",
    "staten_island": "#a78bfa",
    "other": "#9aa3b2",
}


def _event_city(venue, source):
    v = (venue or "").strip().lower()
    hay = v if v else (source or "").strip().lower()
    for city, needles in CITY_RULES:
        for n in needles:
            if n in hay:
                return city
    return "other"


def _maps_link(venue, city):
    if not venue:
        return ""
    label = CITY_LABELS.get(city)
    query = venue if city == "other" or not label else f"{venue}, {label}, NY"
    return f"https://www.google.com/maps/search/?api=1&query={quote(query)}"


_FREE_TITLE_RE = re.compile(
    r"\b("
    r"free|"
    r"guestlist|"
    r"free guestlist|"
    r"free rsvp|"
    r"rsvp free|"
    r"free entry|"
    r"complimentary|"
    r"parade|"
    r"car-free|"
    r"open streets?|"
    r"open studios?|"
    r"summerstage|"
    r"celebrate brooklyn|"
    r"bryant park|"
    r"farmers? markets?|"
    r"greenmarket|"
    r"artisan markets?|"
    r"flea markets?|"
    r"craft markets?|"
    r"vintage markets?|"
    r"clothing swaps?|"
    r"book swaps?|"
    r"clean-?ups?|"
    r"book clubs?|"
    r"open mics?|"
    r"board games?|"
    r"storytimes?|"
    r"fun runs?|"
    r"run clubs?|"
    r"no cover"
    r")\b",
    re.IGNORECASE,
)

_FREE_DESC_PHRASES = [
    "admission: free",
    "admission is free",
    "free admission",
    "free event",
    "free and open",
    "free to attend",
    "free to the public",
    "all events are free",
    "no cover",
    "free entry",
    "complimentary admission",
    "complimentary entry",
    "free outdoor",
    "no tickets required",
    "free dance class",
    "free guestlist",
    "free rsvp",
    "free with rsvp",
    "free w/ rsvp",
    "free before 11",
    "free before 12",
    "free before midnight",
    "free entry before",
]


def _is_event_free(e):
    price = (e.get("price") or "").strip().lower()
    if price:
        if any(k in price for k in ["free", "no cover", "complimentary", "pay what you can"]):
            return True
        if price in ("0", "$0", "$0.00", "0.00"):
            return True
        if re.search(r"\$[1-9]", price):
            return False

    name = (e.get("name") or "").lower()
    desc = (e.get("description") or "").lower()
    source = (e.get("_source_venue") or "").lower()
    venue = (e.get("venue") or "").lower()

    if any(k in source or k in venue for k in [
        "library", "nypl", "bpl", "parks free", "summerstage", "bryant park",
        "greenmarket", "union square greenmarket"
    ]):
        return True

    if _FREE_TITLE_RE.search(name):
        return True

    if any(p in desc for p in _FREE_DESC_PHRASES):
        return True

    return False


_GUESTLIST_RE = re.compile(
    r"\b(guestlist|guest-list|free rsvp|rsvp free|free with rsvp|free w/ rsvp|free before|free entry before|complimentary ticket|vip guestlist)\b",
    re.IGNORECASE,
)


def _is_event_guestlist(e):
    source = (e.get("_source_venue") or "").lower()
    if any(k in source for k in [
        "guestlist", "free rsvp", "somewhere nowhere", "the dl", "harbor nyc",
        "230 fifth", "slate nyc", "nebula", "superior ingredients", "bossa nova", "jupiter disco"
    ]):
        return True
    name = (e.get("name") or "").lower()
    price = (e.get("price") or "").lower()
    desc = (e.get("description") or "").lower()
    if _GUESTLIST_RE.search(name) or _GUESTLIST_RE.search(price) or _GUESTLIST_RE.search(desc):
        return True
    return False


def _build_gcal_link(e, title, venue, city):
    raw_date = e.get("date")
    if not raw_date:
        return None
    try:
        dt = datetime.fromisoformat(raw_date.replace("Z", "+00:00")).astimezone(timezone.utc)
        start_str = dt.strftime("%Y%m%dT%H%M%SZ")
        end_dt = dt + timedelta(hours=2)
        end_str = end_dt.strftime("%Y%m%dT%H%M%SZ")
    except (ValueError, TypeError, AttributeError):
        return None
    loc = f"{venue}, {CITY_LABELS.get(city, 'New York')}, NY" if venue else "New York, NY"
    details = f"Details & Tickets: {e.get('url') or ''}\n\nDiscovered on NYC Events"
    return f"https://calendar.google.com/calendar/render?action=TEMPLATE&text={quote(title)}&dates={start_str}/{end_str}&details={quote(details)}&location={quote(loc)}"


BANNER_SVG = """
<svg viewBox="0 0 1200 240" xmlns="http://www.w3.org/2000/svg" preserveAspectRatio="xMidYMid slice" aria-hidden="true">
  <defs>
    <linearGradient id="sky" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%"   stop-color="#0c0926"/>
      <stop offset="35%"  stop-color="#31124d"/>
      <stop offset="65%"  stop-color="#b8325a"/>
      <stop offset="85%"  stop-color="#f5793a"/>
      <stop offset="100%" stop-color="#ffc355"/>
    </linearGradient>
    <radialGradient id="moon" cx="0.5" cy="0.5" r="0.5">
      <stop offset="0%" stop-color="#fff8e7"/>
      <stop offset="100%" stop-color="#fff8e7" stop-opacity="0"/>
    </radialGradient>
    <linearGradient id="water" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#142852"/>
      <stop offset="100%" stop-color="#071124"/>
    </linearGradient>
    <linearGradient id="chrysler_crown" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#ffffff"/>
      <stop offset="100%" stop-color="#4a6fa5"/>
    </linearGradient>
  </defs>

  <rect width="1200" height="240" fill="url(#sky)"/>
  <!-- stars -->
  <g fill="#ffffff" opacity="0.85">
    <circle cx="70" cy="24" r="1.2"/><circle cx="140" cy="48" r="1"/><circle cx="220" cy="20" r="1.3"/>
    <circle cx="330" cy="55" r="1"/><circle cx="440" cy="16" r="1.2"/><circle cx="560" cy="38" r="1"/>
    <circle cx="690" cy="22" r="1.3"/><circle cx="810" cy="52" r="1"/><circle cx="890" cy="16" r="1.2"/>
    <circle cx="1040" cy="44" r="1"/><circle cx="1120" cy="28" r="1.3"/>
  </g>
  <!-- moon -->
  <circle cx="1070" cy="72" r="46" fill="url(#moon)"/>
  <circle cx="1070" cy="72" r="24" fill="#fff8e7"/>

  <!-- Statue of Liberty silhouette (far left) -->
  <g transform="translate(45, 140)" fill="#18233c" opacity="0.95">
    <rect x="-10" y="55" width="20" height="25" rx="1"/>
    <rect x="-7" y="40" width="14" height="15"/>
    <!-- body / robes -->
    <path d="M -5 40 L -7 20 L 7 20 L 5 40 Z"/>
    <!-- head & crown rays -->
    <circle cx="0" cy="15" r="4"/>
    <line x1="-3" y1="12" x2="-6" y2="9" stroke="#18233c" stroke-width="1.5"/>
    <line x1="0" y1="11" x2="0" y2="7" stroke="#18233c" stroke-width="1.5"/>
    <line x1="3" y1="12" x2="6" y2="9" stroke="#18233c" stroke-width="1.5"/>
    <!-- raised arm & torch -->
    <path d="M 4 20 L 11 8 L 9 7 L 3 18 Z"/>
    <polygon points="11,5 14,8 10,9" fill="#ffd866"/>
  </g>

  <!-- One World Trade Center (Freedom Tower) -->
  <g transform="translate(180, 220)">
    <!-- base & chamfered tower -->
    <polygon points="-28,0 28,0 18,-175 -18,-175" fill="#223963"/>
    <polygon points="0,0 28,0 18,-175 0,-175" fill="#325088"/>
    <!-- parapet ring & spire -->
    <rect x="-10" y="-180" width="20" height="5" fill="#cbd5e1"/>
    <line x1="0" y1="-180" x2="0" y2="-218" stroke="#f1f5f9" stroke-width="2.5"/>
    <circle cx="0" cy="-219" r="2" fill="#ff4d4d"/>
    <!-- window glints -->
    <g fill="#ffe8a3" opacity="0.6">
      <rect x="-10" y="-140" width="2" height="4"/><rect x="8" y="-120" width="2" height="4"/>
      <rect x="-4" y="-80" width="2" height="4"/><rect x="12" y="-50" width="2" height="4"/>
    </g>
  </g>

  <!-- Mid-downtown skyline buildings -->
  <g fill="#1a1c38">
    <rect x="235" y="125" width="24" height="95"/>
    <rect x="265" y="105" width="30" height="115"/>
    <rect x="300" y="135" width="22" height="85"/>
  </g>

  <!-- Empire State Building -->
  <g transform="translate(390, 220)">
    <!-- tiered base -->
    <rect x="-42" y="-70" width="84" height="70" fill="#202b4d"/>
    <!-- mid tower -->
    <rect x="-30" y="-130" width="60" height="60" fill="#263660"/>
    <!-- upper setbacks -->
    <rect x="-20" y="-165" width="40" height="35" fill="#2f4273"/>
    <rect x="-12" y="-185" width="24" height="20" fill="#384f88"/>
    <!-- mooring mast & antenna -->
    <rect x="-6" y="-198" width="12" height="13" fill="#cbd5e1"/>
    <line x1="0" y1="-198" x2="0" y2="-218" stroke="#f1f5f9" stroke-width="2.5"/>
    <circle cx="0" cy="-219" r="2" fill="#ff4d4d"/>
    <!-- lit windows -->
    <g fill="#ffd866" opacity="0.6">
      <rect x="-15" y="-125" width="2" height="4"/><rect x="-5" y="-125" width="2" height="4"/><rect x="5" y="-125" width="2" height="4"/><rect x="15" y="-125" width="2" height="4"/>
      <rect x="-15" y="-105" width="2" height="4"/><rect x="-5" y="-105" width="2" height="4"/><rect x="5" y="-105" width="2" height="4"/><rect x="15" y="-105" width="2" height="4"/>
      <rect x="-10" y="-155" width="2" height="4"/><rect x="0" y="-155" width="2" height="4"/><rect x="10" y="-155" width="2" height="4"/>
    </g>
  </g>

  <!-- Chrysler Building -->
  <g transform="translate(490, 220)">
    <rect x="-25" y="-120" width="50" height="120" fill="#1e2848"/>
    <rect x="-18" y="-150" width="36" height="30" fill="#283863"/>
    <!-- art deco terraced arches / crown -->
    <path d="M -16 -150 Q -8 -166 0 -166 Q 8 -166 16 -150 Z" fill="url(#chrysler_crown)"/>
    <path d="M -12 -166 Q -6 -180 0 -180 Q 6 -180 12 -166 Z" fill="url(#chrysler_crown)"/>
    <path d="M -8 -180 Q -4 -192 0 -192 Q 4 -192 8 -180 Z" fill="url(#chrysler_crown)"/>
    <line x1="0" y1="-192" x2="0" y2="-214" stroke="#ffffff" stroke-width="2"/>
    <!-- triangular windows in crown -->
    <polygon points="0,-186 3,-181 -3,-181" fill="#ffd866"/>
    <polygon points="0,-174 4,-169 -4,-169" fill="#ffd866"/>
  </g>

  <!-- Mid-Manhattan buildings -->
  <g fill="#271d4a">
    <rect x="540" y="115" width="28" height="105"/>
    <rect x="575" y="90" width="34" height="130"/>
    <polygon points="575,90 592,72 609,90" fill="#3b2b6e"/>
    <rect x="618" y="130" width="26" height="90"/>
    <rect x="652" y="110" width="32" height="110"/>
  </g>

  <!-- Brooklyn Bridge (spanning across the right foreground) -->
  <g transform="translate(820, 220)">
    <!-- West Tower -->
    <rect x="-95" y="-135" width="30" height="135" fill="#474052"/>
    <!-- Gothic double arches -->
    <path d="M -90 -45 L -90 -105 Q -80 -125 -70 -105 L -70 -45 Z" fill="#0c0926" opacity="0.75"/>
    <path d="M -90 -105 Q -80 -125 -70 -105" stroke="#cbd5e1" stroke-width="1" fill="none"/>
    <rect x="-97" y="-138" width="34" height="5" fill="#645d70"/>

    <!-- East Tower -->
    <rect x="85" y="-135" width="30" height="135" fill="#474052"/>
    <!-- Gothic double arches -->
    <path d="M 90 -45 L 90 -105 Q 100 -125 110 -105 L 110 -45 Z" fill="#0c0926" opacity="0.75"/>
    <path d="M 90 -105 Q 100 -125 110 -105" stroke="#cbd5e1" stroke-width="1" fill="none"/>
    <rect x="83" y="-138" width="34" height="5" fill="#645d70"/>

    <!-- Bridge Deck roadway -->
    <rect x="-180" y="-45" width="380" height="8" fill="#1b1d28"/>
    <line x1="-180" y1="-41" x2="200" y2="-41" stroke="#ffcc00" stroke-width="0.8" stroke-dasharray="8,6"/>

    <!-- Main Suspension Cables -->
    <path d="M -180 -15 Q -130 -85 -80 -135 Q 10 -40 100 -135 Q 150 -85 200 -15" stroke="#f1f5f9" stroke-width="2" fill="none" opacity="0.95"/>
    <!-- Diagonal stay cables from towers -->
    <g stroke="#ffffff" stroke-width="0.7" opacity="0.55">
      <!-- West tower stays -->
      <line x1="-80" y1="-135" x2="-160" y2="-45"/>
      <line x1="-80" y1="-135" x2="-130" y2="-45"/>
      <line x1="-80" y1="-135" x2="-105" y2="-45"/>
      <line x1="-80" y1="-135" x2="-55"  y2="-45"/>
      <line x1="-80" y1="-135" x2="-30"  y2="-45"/>
      <line x1="-80" y1="-135" x2="-5"   y2="-45"/>
      <!-- East tower stays -->
      <line x1="100" y1="-135" x2="25"   y2="-45"/>
      <line x1="100" y1="-135" x2="50"   y2="-45"/>
      <line x1="100" y1="-135" x2="75"   y2="-45"/>
      <line x1="100" y1="-135" x2="125"  y2="-45"/>
      <line x1="100" y1="-135" x2="150"  y2="-45"/>
      <line x1="100" y1="-135" x2="175"  y2="-45"/>
    </g>
  </g>

  <!-- NYC Taxi yellow pin accent -->
  <g transform="translate(1120, 202)">
    <rect x="-18" y="-7" width="36" height="14" rx="3" fill="#ffcc00"/>
    <rect x="-8" y="-12" width="16" height="5" rx="1" fill="#1a1a1a"/>
    <text x="0" y="4" text-anchor="middle" font-family="Helvetica, Arial, sans-serif" font-weight="900" font-size="9" fill="#1a1a1a">NYC</text>
  </g>

  <!-- East River foreground water strip -->
  <rect x="0" y="220" width="1200" height="20" fill="url(#water)"/>
  <g stroke="#5ea5ff" stroke-width="0.6" opacity="0.45" fill="none">
    <path d="M 0 228 q 30 -3 60 0 t 60 0 t 60 0 t 60 0 t 60 0 t 60 0 t 60 0 t 60 0 t 60 0 t 60 0 t 60 0 t 60 0 t 60 0 t 60 0 t 60 0 t 60 0 t 60 0 t 60 0 t 60 0 t 60 0"/>
    <path d="M 0 234 q 30 -2 60 0 t 60 0 t 60 0 t 60 0 t 60 0 t 60 0 t 60 0 t 60 0 t 60 0 t 60 0 t 60 0 t 60 0 t 60 0 t 60 0 t 60 0 t 60 0 t 60 0 t 60 0 t 60 0 t 60 0"/>
  </g>

  <!-- City lights sparkle confetti -->
  <g opacity="0.85">
    <circle cx="110" cy="115" r="2" fill="#ffd866"/>
    <circle cx="340" cy="85"  r="2" fill="#7ae3ff"/>
    <circle cx="630" cy="135" r="2" fill="#ff77aa"/>
    <circle cx="740" cy="75"  r="2" fill="#ffd866"/>
    <circle cx="980" cy="65"  r="2" fill="#9cf0a0"/>
    <circle cx="1030" cy="140" r="2" fill="#7ae3ff"/>
  </g>
</svg>
"""


def format_time(s):
    if not s:
        return "TBA"
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return s
    return dt.astimezone(EASTERN).strftime("%-I:%M %p")


def format_when(e):
    if not e.get("date") and e.get("ends"):
        try:
            end = datetime.strptime(e["ends"], "%Y-%m-%d")
        except ValueError:
            return format_time(e.get("date"))
        return f"thru {end.month}/{end.day}"
    return format_time(e.get("date"))


def format_date_heading(date_obj):
    today = datetime.now(EASTERN).date()
    delta = (date_obj - today).days
    if delta == 0:
        prefix = "Today"
    elif delta == 1:
        prefix = "Tomorrow"
    else:
        prefix = date_obj.strftime("%A")
    return f"{prefix} · {date_obj.strftime('%b %-d')}"


def compute_recurring(dated):
    """Return set of (normalized_name, source_venue) keys for events that appear
    on the same weekday roughly a week apart — treated as weekly recurring."""
    groups = defaultdict(list)
    for _, events in dated:
        for e in events:
            t = e.get("_time")
            name = (e.get("name") or "").strip().lower()
            if not t or not name:
                continue
            key = (name, e.get("_source_venue") or "")
            groups[key].append(t)
    recurring = set()
    for key, times in groups.items():
        if len(times) < 2:
            continue
        times.sort()
        for i in range(len(times) - 1):
            delta = (times[i + 1].date() - times[i].date()).days
            if 5 <= delta <= 9:
                recurring.add(key)
                break
    return recurring


def _dedup_key(e):
    name = (e.get("name") or "").strip().lower()
    name = re.sub(r"[^a-z0-9]+", " ", name).strip()
    if not name or len(name) < 4:
        return None
    return name


def _merge_duplicates(events):
    """Collapse events sharing a normalized name within the same day bucket."""
    seen = {}
    out = []
    for e in events:
        key = _dedup_key(e)
        if key is None:
            out.append(e)
            continue
        if key in seen:
            primary = seen[key]
            primary.setdefault("_alt_sources", [])
            src_url = e.get("url")
            src_name = e.get("_source_venue") or e.get("venue") or "source"
            if src_url and not any(a.get("url") == src_url for a in primary["_alt_sources"]) and src_url != primary.get("url"):
                primary["_alt_sources"].append({"venue": src_name, "url": src_url})
            if not primary.get("price") and e.get("price"):
                primary["price"] = e["price"]
        else:
            seen[key] = e
            out.append(e)
    return out


def group_by_date(results):
    today = datetime.now(EASTERN).date()
    buckets = {}
    tba = []
    ongoing = []
    for r in results:
        for e in r.get("events", []):
            entry = {"venue_url": r.get("url", ""), **e, "_source_venue": r.get("venue", "")}
            entry["venue"] = e.get("venue") or r.get("venue", "")
            raw = e.get("date")
            key = None
            if raw:
                try:
                    dt = datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(EASTERN)
                    key = dt.date()
                    entry["_time"] = dt
                except (TypeError, ValueError):
                    pass
            if key is None:
                tba.append(entry)
            elif key < today:
                ongoing.append(entry)
            else:
                buckets.setdefault(key, []).append(entry)
    for date_key, events in list(buckets.items()):
        events.sort(key=lambda e: e.get("_time", datetime.min.replace(tzinfo=EASTERN)))
        buckets[date_key] = _merge_duplicates(events)
    ongoing.sort(key=lambda e: e.get("_time") or datetime.min.replace(tzinfo=EASTERN), reverse=True)
    return sorted(buckets.items()), tba, ongoing


def render_page(results):
    if isinstance(results, dict):
        venue_list = results.get("venues", [])
    else:
        venue_list = results or []
    dated, tba, ongoing = group_by_date(venue_list)
    recurring_keys = compute_recurring(dated)
    total = sum(len(v) for _, v in dated) + len(tba)
    failed = [r for r in venue_list if r.get("error")]
    all_venue_names = sorted(list({r["venue"] for r in venue_list if r.get("venue")}))

    weather = fetch_nyc_weather()
    weather_pill_html = ""
    if weather:
        weather_pill_html = f'<span class="pill-weather" title="{weather.get("label", "")} in NYC (Central Park)">{weather.get("icon", "🌤️")} {weather.get("temp", "--")}°F <span class="weather-label">{weather.get("label", "")}</span></span>'

    def is_recurring(e):
        return (
            (e.get("name") or "").strip().lower(),
            e.get("_source_venue") or "",
        ) in recurring_keys

    def render_event(e):
        raw_title = e.get("name") or "Untitled"
        title = escape(raw_title)
        link = (
            f'<a href="{escape(e["url"])}" target="_blank" rel="noopener">{title}</a>'
            if e.get("url") else title
        )
        is_free = _is_event_free(e)
        price_raw = escape(e["price"]) if e.get("price") else ""
        if price_raw:
            if "free" in price_raw.lower() or price_raw in ("$0", "0"):
                price_tag = f'<span class="price free">{price_raw}</span>'
            else:
                price_tag = f'<span class="price">{price_raw}</span>'
        elif is_free:
            price_tag = '<span class="price free">Free</span>'
        else:
            price_tag = ""

        cat = e.get("category") or "other"
        bucket = category_bucket(cat)
        color, icon = CATEGORY_STYLES.get(cat, CATEGORY_STYLES["other"])
        cat_tag = f'<span class="cat-pill" style="--cat-c:{color}; background:{color}18; border-color:{color}33; color:{color}">{icon} {escape(cat)}</span>'
        venue = e.get("venue") or ""
        source = e.get("_source_venue") or ""
        city = _event_city(venue, source)
        recurring = is_recurring(e)
        recur_flag = "weekly" if recurring else "once"
        recur_badge = '<span class="recur">↻ weekly</span>' if recurring else ""
        alts = e.get("_alt_sources") or []
        alt_html = ""
        if alts:
            alt_links = " · ".join(
                f'<a href="{escape(a["url"])}" target="_blank" rel="noopener">{escape(a["venue"])}</a>'
                for a in alts if a.get("url")
            )
            if alt_links:
                alt_html = f'<span class="alt-sources">also on {alt_links}</span>'
        if venue:
            maps_url = _maps_link(venue, city)
            venue_html = f'<a class="venue-link" href="{escape(maps_url)}" target="_blank" rel="noopener">{escape(venue)}</a>'
        else:
            venue_html = ""

        gcal_url = _build_gcal_link(e, raw_title, venue, city)
        cal_actions = []
        if gcal_url:
            cal_actions.append(f'<a class="cal-btn" href="{escape(gcal_url)}" target="_blank" rel="noopener" title="Add to Google Calendar">+ GCal</a>')
        if e.get("date"):
            cal_actions.append(f'<button type="button" class="cal-btn ics-btn" data-title="{escape(raw_title)}" data-date="{escape(e["date"])}" data-venue="{escape(venue)}" data-url="{escape(e.get("url") or "")}" title="Download .ics for Apple/Outlook">+ .ics</button>')
        cal_html = f'<span class="cal-links">{" ".join(cal_actions)}</span>' if cal_actions else ""

        raw_desc = (e.get("description") or "").replace("***", "").replace("**", "").replace("__", "").replace("`", "").strip()
        desc = raw_desc[:180]
        desc_html = f'<div class="desc">{escape(desc)}</div>' if desc else ""
        is_guestlist = _is_event_guestlist(e)
        guestlist_flag = "true" if is_guestlist else "false"
        guestlist_badge = '<span class="badge-guestlist" title="Free club guestlist or RSVP entry">🎟️ Guestlist</span>' if is_guestlist else ""
        free_flag = "true" if (is_free or is_guestlist) else "false"
        return f'''<li class="event" data-cat="{escape(cat)}" data-bucket="{escape(bucket)}" data-venue="{escape(source)}" data-city="{escape(city)}" data-recur="{recur_flag}" data-free="{free_flag}" data-guestlist="{guestlist_flag}">
          <div class="when">{escape(format_when(e))}</div>
          <div class="what">{link}{price_tag}{guestlist_badge}{recur_badge}
            <div class="venue-tag">{cat_tag} · {venue_html}{(" · " + alt_html) if alt_html else ""}{cal_html}</div>
            {desc_html}
          </div>
        </li>'''

    bucket_name_order = [b for b, _ in CATEGORY_BUCKETS]
    city_day_order = ["manhattan", "brooklyn", "queens", "bronx", "staten_island", "other"]

    def _render_buckets(events):
        by_bucket = {b: [] for b in bucket_name_order}
        for e in events:
            by_bucket.setdefault(category_bucket(e.get("category")), []).append(e)
        bucket_blocks = []
        for bname in bucket_name_order:
            bucket_events = by_bucket.get(bname) or []
            if not bucket_events:
                continue
            cats = dict(CATEGORY_BUCKETS).get(bname, [])
            accent = CATEGORY_STYLES.get(cats[0], CATEGORY_STYLES["other"])[0] if cats else CATEGORY_STYLES["other"][0]
            items = "\n".join(render_event(e) for e in bucket_events)
            bucket_blocks.append(f'''
            <div class="bucket" data-bucket="{escape(bname)}">
              <div class="bucket-head" style="--accent:{accent}">
                <span class="bucket-name">{escape(bname)}</span>
                <span class="count">{len(bucket_events)}</span>
              </div>
              <ul>{items}</ul>
            </div>''')
        return "".join(bucket_blocks)

    def _render_day_section(heading_html, events, date_attr=""):
        by_city = {c: [] for c in city_day_order}
        for e in events:
            c = _event_city(e.get("venue"), e.get("_source_venue"))
            by_city.setdefault(c, []).append(e)
        city_blocks = []
        for cname in city_day_order:
            city_events = by_city.get(cname) or []
            if not city_events:
                continue
            city_blocks.append(f'''
          <div class="city-section" data-city="{escape(cname)}">
            <h3 class="city-head"><span>{escape(CITY_LABELS[cname])}</span><span class="count">{len(city_events)}</span></h3>
            <div class="buckets">{_render_buckets(city_events)}</div>
          </div>''')
        return f'''
        <section class="day" data-date="{date_attr}">
          <h2>{heading_html}<span class="count">{len(events)}</span></h2>
          <div class="cities">{"".join(city_blocks)}</div>
        </section>'''

    sections = []
    for date_obj, events in dated:
        sections.append(_render_day_section(escape(format_date_heading(date_obj)), events, date_obj.isoformat()))
    if tba:
        sections.append(_render_day_section("Date TBA", tba, "tba"))

    useful_sidebar = ""
    if STATIC_LINKS or DEAL_LINKS:
        deals_block = ""
        lucky_shows = fetch_luckyseat_nyc()
        if DEAL_LINKS or lucky_shows:
            lucky_html = ""
            if lucky_shows:
                def _lucky_li(s):
                    price = s.get("price")
                    price_str = f" · ${price:.0f} all-in" if isinstance(price, (int, float)) else ""
                    return (
                        f'<li><a href="{escape(s["url"])}" target="_blank" rel="noopener">'
                        f'<span class="deal-name">{escape(s["name"] or "Show")}</span>'
                        f'<span class="deal-meta">{escape(s["venue"] or "")}{escape(price_str)}</span>'
                        f'</a></li>'
                    )
                lucky_items = "".join(_lucky_li(s) for s in lucky_shows)
                lucky_html = f'''
          <div class="deals-sub">
            <div class="deals-sub-head"><a href="https://www.luckyseat.com/" target="_blank" rel="noopener">LuckySeat — Broadway NYC</a></div>
            <ul class="deals-list">{lucky_items}</ul>
          </div>'''
            elif DEAL_LINKS:
                lucky_html = '''
          <div class="deals-sub">
            <div class="deals-sub-head">LuckySeat — Broadway NYC</div>
            <p class="hint">Check lotteries for daily $39–$49 rush tickets.</p>
          </div>'''
            guestlist_deals = [
                ("Somewhere Nowhere NYC", "https://somewherenowherenyc.com/", "Free VIP Guestlist (before 11:30 PM)", "Chelsea Rooftop"),
                ("The DL NYC", "https://thedl-nyc.com/", "Free Guestlist Entry (before 11:00 PM)", "Lower East Side"),
                ("Harbor NYC Rooftop", "https://harbornewyorkcity.com/", "Free RSVP & Sunset Parties", "Hell's Kitchen"),
                ("230 Fifth Rooftop", "https://www.230-fifth.com/", "Free Admission & Heated Igloos", "Flatiron Rooftop"),
                ("Superior Ingredients", "https://superioringredientsnyc.com/", "Free RSVP Dance Series (before 11 PM)", "Williamsburg"),
                ("Bossa Nova Civic Club", "https://bossanovacivicclub.com/", "Free Entry Before 11:00 PM Nightly", "Bushwick Techno"),
                ("Jupiter Disco", "https://www.jupiterdisco.com/", "No Cover / Always Free Retro DJs", "Bushwick Synth"),
                ("Slate NYC", "https://slatenyc.com/", "Free RSVP Club & Games Lounge", "Chelsea"),
                ("Nebula NYC", "https://nebulanewyork.com/", "Kinetic Mega-Club Guestlist Draws", "Midtown"),
                ("Eventbrite NYC Guestlists", "https://www.eventbrite.com/d/ny--new-york/free-guestlist/", "Live Rotating Club Guestlists", "Citywide"),
            ]
            gl_items = "".join(
                f'<li><a href="{escape(u)}" target="_blank" rel="noopener">'
                f'<span class="deal-name">{escape(n)}</span>'
                f'<span class="deal-meta">{escape(m)} · {escape(loc)}</span>'
                f'</a></li>'
                for n, u, m, loc in guestlist_deals
            )
            guestlist_deals_html = f'''
          <div class="deals-sub">
            <div class="deals-sub-head"><a href="https://www.eventbrite.com/d/ny--new-york/free-guestlist/" target="_blank" rel="noopener">🎟️ Free Club Guestlists &amp; RSVPs</a></div>
            <ul class="deals-list">{gl_items}</ul>
          </div>'''
            other_deals_html = ""
            others = [(n, u) for n, u in DEAL_LINKS if "luckyseat" not in u.lower() and "guestlist" not in u.lower() and "somewhere nowhere" not in u.lower() and "the dl" not in u.lower() and "harbor nyc" not in u.lower() and "230 fifth" not in u.lower() and "superior ingredients" not in u.lower() and "bossa nova" not in u.lower() and "jupiter disco" not in u.lower()]
            if others:
                other_items = "".join(
                    f'<li><a href="{escape(u)}" target="_blank" rel="noopener">{escape(n)}</a></li>'
                    for n, u in others
                )
                other_deals_html = f'<ul class="deals-list">{other_items}</ul>'
            deals_block = f'''
        <div class="useful-inner">
          <h3>Deals &amp; lotteries</h3>
          {guestlist_deals_html}
          {lucky_html}
          {other_deals_html}
        </div>'''

        useful_block = ""
        if STATIC_LINKS:
            by_cat = {}
            for cat, name, link in STATIC_LINKS:
                by_cat.setdefault(cat, []).append((name, link))
            parts = []
            for cat, pairs in by_cat.items():
                color, icon = CATEGORY_STYLES.get(cat, CATEGORY_STYLES["other"])
                link_items = "".join(
                    f'<li><a href="{escape(u)}" target="_blank" rel="noopener">{escape(n)}</a></li>'
                    for n, u in pairs
                )
                parts.append(
                    f'<div class="useful-cat"><div class="useful-cat-head" style="color:{color}">{icon} {escape(cat)}</div><ul>{link_items}</ul></div>'
                )
            useful_block = f'''
        <div class="useful-inner">
          <h3>Useful links</h3>
          <p class="hint">Venues without a scrapable calendar.</p>
          {"".join(parts)}
        </div>'''

        useful_sidebar = f'''
      <aside class="useful">{deals_block}{useful_block}
      </aside>'''

    ongoing_section = ""
    if ongoing:
        items = "\n".join(render_event(e) for e in ongoing)
        ongoing_section = f'''
      <section class="ongoing">
        <h2>Ongoing &amp; evergreen<span class="count">{len(ongoing)}</span></h2>
        <p class="hint">Listings dated before today (long-running or pinned by the source).</p>
        <ul>{items}</ul>
      </section>'''

    bucket_order = [b for b, _ in CATEGORY_BUCKETS]
    bucket_counts = {b: 0 for b in bucket_order}
    other_count = 0
    recurring_count = 0
    once_count = 0
    all_events_flat = [e for _, es in dated for e in es] + list(tba)
    for e in all_events_flat:
        bucket_counts[category_bucket(e.get("category"))] = bucket_counts.get(category_bucket(e.get("category")), 0) + 1
        if (e.get("category") or "other") == "other":
            other_count += 1
        if is_recurring(e):
            recurring_count += 1
        else:
            once_count += 1

    def _bucket_icon_row(bucket_name):
        cats = dict(CATEGORY_BUCKETS).get(bucket_name, [])
        return " ".join(CATEGORY_STYLES.get(c, CATEGORY_STYLES["other"])[1] for c in cats)

    bucket_boxes = "\n".join(
        f'''<label class="chk">
            <input type="checkbox" class="cat-chk" value="{escape(b)}" checked>
            <span>{_bucket_icon_row(b)} {escape(b)} <span class="count">{bucket_counts.get(b, 0)}</span></span>
          </label>'''
        for b in bucket_order
    )

    recur_boxes = f'''
        <label class="chk">
          <input type="checkbox" class="recur-chk" value="once" checked>
          <span>One-time <span class="count">{once_count}</span></span>
        </label>
        <label class="chk">
          <input type="checkbox" class="recur-chk" value="weekly" checked>
          <span>↻ Weekly recurring <span class="count">{recurring_count}</span></span>
        </label>'''

    venue_counts = {v: 0 for v in all_venue_names}
    for e in all_events_flat:
        venue_counts[e.get("_source_venue", "")] = venue_counts.get(e.get("_source_venue", ""), 0) + 1

    venue_boxes = "\n".join(
        f'''<label class="chk">
            <input type="checkbox" class="venue-chk" value="{escape(v)}" checked>
            <span>{escape(v)} <span class="count">{venue_counts.get(v, 0)}</span></span>
          </label>'''
        for v in all_venue_names
    )

    city_order = ["manhattan", "brooklyn", "queens", "bronx", "staten_island", "other"]
    city_counts = {c: 0 for c in city_order}
    for e in all_events_flat:
        c = _event_city(e.get("venue"), e.get("_source_venue"))
        city_counts[c] = city_counts.get(c, 0) + 1

    city_boxes = "\n".join(
        f'''<label class="chk">
            <input type="checkbox" class="city-chk" value="{escape(c)}" checked>
            <span><span class="city-swatch" style="background:{CITY_COLORS[c]}"></span>{escape(CITY_LABELS[c])} <span class="count">{city_counts.get(c, 0)}</span></span>
          </label>'''
        for c in city_order
    )

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>NYC Events</title>
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=5.0">
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Crect width='64' height='64' rx='16' fill='%230c0e14'/%3E%3Crect x='3' y='3' width='58' height='58' rx='13' fill='none' stroke='%23ffcc00' stroke-width='3'/%3E%3Ctext x='32' y='46' font-family='Impact, Arial Black, sans-serif' font-weight='900' font-size='34' fill='%235d9bff' text-anchor='middle'%3ENYC%3C/text%3E%3C/svg%3E">
<style>
  :root {{
    --bg: #0c0e14;
    --card: #151822;
    --card-hover: #1c202e;
    --fg: #eef1f8;
    --muted: #8e96a8;
    --accent: #5d9bff;
    --accent-glow: rgba(93, 155, 255, 0.25);
    --border: rgba(255, 255, 255, 0.08);
    --border-hover: rgba(255, 255, 255, 0.16);
    --green: #4ade80;
    --green-bg: rgba(74, 222, 128, 0.14);
    --green-border: rgba(74, 222, 128, 0.32);
    --warn: #f0a07a;
    --radius-lg: 16px;
    --radius-md: 10px;
    --radius-sm: 6px;
  }}
  *, *::before, *::after {{ box-sizing: border-box; }}
  html, body {{
    margin: 0;
    padding: 0;
    width: 100%;
    max-width: 100vw;
    overflow-x: hidden;
    -webkit-text-size-adjust: 100%;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    background: var(--bg);
    color: var(--fg);
    line-height: 1.5;
    -webkit-font-smoothing: antialiased;
  }}

  /* Modern Hero Banner */
  .banner {{
    position: relative;
    min-height: 270px;
    display: flex;
    align-items: flex-end;
    background-color: #0c0926;
    border-bottom: 1px solid var(--border);
    padding: 40px 24px 28px;
    overflow: hidden;
  }}
  .banner-svg-wrap {{
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    pointer-events: none;
    z-index: 0;
  }}
  .banner-svg-wrap svg {{
    width: 100%;
    height: 100%;
    object-fit: cover;
  }}
  .banner-gradient-overlay {{
    position: absolute;
    inset: 0;
    background: linear-gradient(180deg, rgba(12, 14, 20, 0.15) 0%, rgba(12, 14, 20, 0.65) 60%, rgba(12, 14, 20, 0.98) 100%);
    pointer-events: none;
    z-index: 1;
  }}
  .banner-inner {{
    position: relative;
    z-index: 2;
    max-width: 1320px;
    width: 100%;
    margin: 0 auto;
    display: flex;
    flex-direction: column;
    gap: 12px;
  }}
  .banner-top-tag {{
    display: inline-flex;
    align-items: center;
    gap: 8px;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: #ffd866;
    text-shadow: 0 1px 8px rgba(0,0,0,0.6);
  }}
  .live-pulse {{
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: #4ade80;
    box-shadow: 0 0 0 0 rgba(74, 222, 128, 0.7);
    animation: livepulse 2s infinite;
  }}
  @keyframes livepulse {{
    0% {{ box-shadow: 0 0 0 0 rgba(74, 222, 128, 0.7); }}
    70% {{ box-shadow: 0 0 0 8px rgba(74, 222, 128, 0); }}
    100% {{ box-shadow: 0 0 0 0 rgba(74, 222, 128, 0); }}
  }}
  .banner-title {{
    margin: 0;
    font-size: 44px;
    font-weight: 850;
    letter-spacing: -0.035em;
    color: #ffffff;
    line-height: 1.05;
    text-shadow: 0 2px 20px rgba(0,0,0,0.6);
  }}
  .banner-meta-pill {{
    display: inline-flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 10px;
    align-self: flex-start;
    background: rgba(18, 21, 31, 0.75);
    backdrop-filter: blur(14px);
    -webkit-backdrop-filter: blur(14px);
    border: 1px solid rgba(255, 255, 255, 0.14);
    border-radius: 999px;
    padding: 6px 16px;
    font-size: 13px;
    color: var(--fg);
    box-shadow: 0 4px 20px rgba(0,0,0,0.35);
  }}
  .pill-weather {{ display: inline-flex; align-items: center; gap: 4px; font-weight: 600; color: #fff; }}
  .weather-label {{ font-weight: 400; color: var(--muted); }}
  .pill-dot {{ color: var(--muted); opacity: 0.6; }}
  .pill-stat {{ color: var(--fg); }}
  .pill-refresh {{ color: #ffd866; text-decoration: none; font-weight: 600; font-size: 12px; }}
  .pill-refresh:hover {{ text-decoration: underline; }}

  /* Layout */
  .layout {{
    max-width: 1320px;
    margin: 0 auto;
    padding: 20px 24px 48px;
    display: grid;
    grid-template-columns: 240px minmax(0, 1fr) 240px;
    gap: 18px;
    align-items: start;
  }}
  aside.filters {{
    position: sticky;
    top: 12px;
    max-height: calc(100vh - 24px);
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 12px;
    padding-right: 4px;
  }}
  aside.filters::-webkit-scrollbar, aside.useful::-webkit-scrollbar {{ width: 6px; }}
  aside.filters::-webkit-scrollbar-thumb, aside.useful::-webkit-scrollbar-thumb {{ background: var(--border); border-radius: 3px; }}
  aside.useful {{
    position: sticky;
    top: 12px;
    max-height: calc(100vh - 24px);
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 12px;
  }}
  aside.useful .useful-inner {{
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
    padding: 12px 14px;
  }}
  aside.useful .deals-list {{ list-style: none; margin: 0; padding: 0; }}
  aside.useful .deals-list li {{ margin: 6px 0; }}
  aside.useful .deals-list a {{ color: var(--accent); text-decoration: none; display: block; }}
  aside.useful .deals-list a:hover {{ text-decoration: underline; }}
  aside.useful .deal-name {{ display: block; font-weight: 500; }}
  aside.useful .deal-meta {{ display: block; color: var(--muted); font-size: 11px; margin-top: 2px; }}
  aside.useful .deals-sub {{ margin-top: 8px; }}
  aside.useful .deals-sub:first-child {{ margin-top: 0; }}
  aside.useful .deals-sub-head {{ font-size: 11px; letter-spacing: 0.04em; text-transform: uppercase; color: var(--muted); margin-bottom: 4px; }}
  aside.useful .deals-sub-head a {{ color: var(--muted); text-decoration: none; }}
  aside.useful .deals-sub-head a:hover {{ color: var(--accent); }}
  aside.useful h3 {{ margin: 0 0 4px; font-size: 11px; letter-spacing: 0.06em; text-transform: uppercase; color: var(--muted); }}
  aside.useful p.hint {{ margin: 0 0 10px; color: var(--muted); font-size: 11px; }}
  .useful-cat {{ margin-top: 10px; }}
  .useful-cat:first-of-type {{ margin-top: 4px; }}
  .useful-cat-head {{ font-size: 11px; font-weight: 600; letter-spacing: 0.02em; margin-bottom: 4px; }}
  .useful-cat ul {{ list-style: none; padding: 0; margin: 0; display: flex; flex-direction: column; gap: 2px; }}
  .useful-cat li a {{ color: var(--accent); text-decoration: none; font-size: 12px; display: block; padding: 2px 0; }}
  .useful-cat li a:hover {{ text-decoration: underline; }}

  main {{ display: flex; flex-direction: column; gap: 14px; min-width: 0; }}

  /* Top-Level Location Bar */
  .location-chips-bar {{
    display: flex;
    align-items: center;
    gap: 8px;
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
    padding: 8px 12px;
    overflow-x: auto;
    white-space: nowrap;
    -webkit-overflow-scrolling: touch;
    scrollbar-width: none;
    -ms-overflow-style: none;
    max-width: 100%;
  }}
  .location-chips-bar::-webkit-scrollbar {{
    display: none;
  }}
  .loc-chip {{
    background: rgba(255, 255, 255, 0.04);
    border: 1px solid var(--border);
    color: var(--fg);
    padding: 5px 13px;
    border-radius: 999px;
    font-size: 13px;
    font-weight: 500;
    cursor: pointer;
    font-family: inherit;
    display: inline-flex;
    align-items: center;
    gap: 6px;
    flex-shrink: 0;
    white-space: nowrap;
    transition: all 0.15s ease;
  }}
  .loc-chip:hover {{
    background: rgba(255, 255, 255, 0.08);
    border-color: var(--accent);
    color: #fff;
  }}
  .loc-chip.active {{
    background: rgba(255, 255, 255, 0.12);
    border-color: rgba(255, 255, 255, 0.35);
    color: #fff;
    font-weight: 700;
  }}
  .loc-chip.active[data-city="manhattan"] {{
    border-color: #5d9bff;
    background: rgba(93, 155, 255, 0.18);
    color: #79aeff;
  }}
  .loc-chip.active[data-city="brooklyn"] {{
    border-color: #e05a6b;
    background: rgba(224, 90, 107, 0.18);
    color: #ff7a8a;
  }}
  .loc-chip.active[data-city="queens"] {{
    border-color: #f29e4c;
    background: rgba(242, 158, 76, 0.18);
    color: #ffb169;
  }}
  .loc-chip.active[data-city="bronx"] {{
    border-color: #4ade80;
    background: rgba(74, 222, 128, 0.18);
    color: #86efac;
  }}
  .loc-chip.active[data-city="staten_island"] {{
    border-color: #a78bfa;
    background: rgba(167, 139, 250, 0.18);
    color: #c4b5fd;
  }}
  .city-dot {{
    width: 8px;
    height: 8px;
    border-radius: 50%;
    display: inline-block;
    flex-shrink: 0;
  }}

  /* Quick-Access Chips Bar */
  .quick-chips-bar {{
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
    padding: 8px 12px;
  }}
  .chip {{
    background: rgba(255, 255, 255, 0.04);
    border: 1px solid var(--border);
    color: var(--fg);
    padding: 5px 13px;
    border-radius: 999px;
    font-size: 12px;
    font-weight: 500;
    cursor: pointer;
    font-family: inherit;
    transition: all 0.15s ease;
  }}
  .chip:hover {{
    background: rgba(255, 255, 255, 0.08);
    border-color: var(--accent);
    color: #fff;
  }}
  .chip.active {{
    background: var(--accent);
    color: #0c0e14;
    border-color: var(--accent);
    font-weight: 700;
    box-shadow: 0 2px 10px var(--accent-glow);
  }}
  .chip-free {{
    color: var(--green);
    border-color: var(--green-border);
    background: var(--green-bg);
  }}
  .chip-free.active {{
    background: var(--green);
    color: #08200f;
    border-color: var(--green);
    font-weight: 700;
    box-shadow: 0 2px 10px rgba(74, 222, 128, 0.3);
  }}
  .chip-guestlist {{
    color: #ff76ac;
    border-color: rgba(255, 118, 172, 0.35);
    background: rgba(255, 118, 172, 0.12);
    margin-left: auto;
  }}
  .chip-guestlist.active {{
    background: #ff76ac;
    color: #1a0612;
    border-color: #ff76ac;
    font-weight: 700;
    box-shadow: 0 2px 10px rgba(255, 118, 172, 0.35);
  }}
  .badge-guestlist {{
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 2px 8px;
    border-radius: 999px;
    font-size: 11px;
    font-weight: 700;
    color: #ff76ac;
    background: rgba(255, 118, 172, 0.15);
    border: 1px solid rgba(255, 118, 172, 0.35);
    letter-spacing: 0.02em;
    vertical-align: middle;
    margin-left: 6px;
  }}

  /* Day Section */
  .day {{ background: var(--card); border: 1px solid var(--border); border-radius: var(--radius-lg); padding: 14px 18px 12px; }}
  .day h2 {{ margin: 0 0 12px; font-size: 17px; font-weight: 700; display:flex; align-items:center; gap:8px; color: var(--fg); position: sticky; top: 0; background: var(--card); padding: 4px 0 8px; z-index: 2; }}
  .count {{ background: rgba(255, 255, 255, 0.06); color: var(--muted); font-size: 11px; padding: 2px 8px; border-radius: 999px; font-weight: 500; }}
  .cities {{ display: flex; flex-direction: column; gap: 14px; }}
  .city-section {{ --city-color: var(--accent); border-top: 1px solid var(--border); padding-top: 12px; padding-left: 10px; border-left: 3px solid var(--city-color); }}
  .city-section:first-child {{ border-top: none; padding-top: 0; }}
  .city-section.empty {{ display: none; }}
  .city-section[data-city="manhattan"]     {{ --city-color: #5d9bff; }}
  .city-section[data-city="brooklyn"]      {{ --city-color: #e05a6b; }}
  .city-section[data-city="queens"]        {{ --city-color: #f29e4c; }}
  .city-section[data-city="bronx"]         {{ --city-color: #4ade80; }}
  .city-section[data-city="staten_island"] {{ --city-color: #a78bfa; }}
  .city-section[data-city="other"]         {{ --city-color: #9aa3b2; }}
  .city-head {{ margin: 0 0 8px; font-size: 12px; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; color: var(--city-color); display: flex; align-items: center; gap: 8px; }}
  .city-head .count {{ background: transparent; color: var(--muted); font-weight: 500; letter-spacing: 0; }}
  .buckets {{ display: flex; flex-direction: column; gap: 10px; }}
  .bucket {{ border-left: 3px solid var(--accent, #444); padding: 2px 0 2px 12px; border-left-color: var(--accent); }}
  .bucket-head {{ display: flex; align-items: center; gap: 8px; margin-bottom: 6px; font-size: 11px; letter-spacing: 0.08em; text-transform: uppercase; color: var(--accent); font-weight: 600; }}
  .bucket-head .count {{ background: transparent; color: var(--muted); }}
  .bucket ul {{ list-style: none; padding: 0; margin: 0; }}

  /* Event Cards */
  .event {{
    padding: 10px 14px;
    border-radius: var(--radius-sm);
    background: rgba(255, 255, 255, 0.015);
    border: 1px solid rgba(255, 255, 255, 0.04);
    margin-bottom: 6px;
    display: grid;
    grid-template-columns: 78px minmax(0, 1fr);
    gap: 12px;
    font-size: 14px;
    min-width: 0;
    transition: background 0.15s ease, border-color 0.15s ease, transform 0.15s ease, box-shadow 0.15s ease;
  }}
  .event:hover {{
    background: rgba(255, 255, 255, 0.04);
    border-color: rgba(93, 155, 255, 0.3);
    transform: translateY(-1px);
    box-shadow: 0 4px 14px rgba(0, 0, 0, 0.22);
  }}
  .when {{ color: var(--muted); font-size: 12px; font-variant-numeric: tabular-nums; padding-top: 2px; font-weight: 500; }}
  .what {{ min-width: 0; overflow-wrap: break-word; word-break: break-word; }}
  .what a {{ color: #79aeff; text-decoration: none; font-weight: 500; }}
  .what a:hover {{ text-decoration: underline; color: #a5caff; }}
  .venue-tag {{ color: var(--muted); font-size: 11px; margin-top: 4px; display: flex; align-items: center; flex-wrap: wrap; gap: 6px; }}
  .venue-link {{ color: var(--muted); text-decoration: none; border-bottom: 1px dotted rgba(154,163,178,0.4); }}
  .venue-link:hover {{ color: var(--fg); border-bottom-color: var(--fg); }}
  .cat-pill {{ display: inline-flex; align-items: center; gap: 4px; padding: 2px 7px; border-radius: 5px; font-size: 11px; font-weight: 600; line-height: 1.3; border: 1px solid; }}
  .price {{ display:inline-block; background: rgba(255,255,255,0.06); color: var(--muted); font-size: 11px; padding: 2px 7px; border-radius: 5px; font-weight: 500; }}
  .price.free {{ background: var(--green-bg); color: var(--green); border: 1px solid var(--green-border); font-weight: 700; }}
  .cal-links {{ display: inline-flex; align-items: center; gap: 4px; margin-left: 4px; }}
  .cal-btn {{ background: rgba(255,255,255,0.04); border: 1px solid var(--border); color: var(--muted); padding: 2px 7px; border-radius: 5px; font-size: 10px; font-weight: 500; text-decoration: none; cursor: pointer; line-height: 1.3; display: inline-flex; align-items: center; gap: 3px; font-family: inherit; transition: all 0.15s ease; }}
  .cal-btn:hover {{ color: #fff; border-color: var(--accent); background: rgba(93,155,255,0.15); }}
  .recur {{ display:inline-block; margin-left: 8px; background: rgba(255,122,178,0.14); color: #ff7ab2; font-size: 10px; padding: 2px 6px; border-radius: 4px; letter-spacing: 0.02em; }}
  .alt-sources {{ color: var(--muted); font-size: 11px; }}
  .alt-sources a {{ color: var(--accent); text-decoration: none; }}
  .alt-sources a:hover {{ text-decoration: underline; }}
  .desc {{
    color: var(--muted);
    font-size: 12px;
    margin-top: 5px;
    line-height: 1.45;
    word-break: break-word;
    overflow-wrap: break-word;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
    max-width: 100%;
  }}
  .bucket.empty {{ display: none; }}

  /* Filter Groups */
  .filter-group {{ background: var(--card); border: 1px solid var(--border); border-radius: var(--radius-md); padding: 10px 12px; }}
  .filter-group h3 {{ margin: 0 0 8px; font-size: 11px; letter-spacing: 0.06em; text-transform: uppercase; color: var(--muted); display: flex; align-items:center; gap:8px; flex-wrap:wrap; }}
  .filter-group h3 .spacer {{ flex:1; }}
  .filter-group h3 button {{ background: none; border: 1px solid var(--border); color: var(--muted); font-size: 10px; padding: 1px 8px; border-radius: 999px; cursor: pointer; font-family: inherit; letter-spacing: 0; text-transform: none; }}
  .filter-group h3 button:hover {{ color: var(--fg); border-color: var(--fg); }}
  .filter-group.venues .chk-grid {{ max-height: 280px; overflow-y: auto; }}
  .chk-grid {{ display:flex; flex-direction: column; gap:2px; }}
  .chk {{ display: flex; align-items: center; gap: 6px; font-size: 12px; cursor: pointer; padding: 3px 4px; border-radius: 6px; }}
  .chk:hover {{ background: rgba(255,255,255,0.03); }}
  .chk input {{ accent-color: var(--accent); margin: 0; flex-shrink: 0; }}
  .chk > span {{ display: flex; align-items: center; gap: 6px; flex: 1; min-width: 0; }}
  .chk > span > .count {{ margin-left: auto; }}
  .city-swatch {{ display: inline-block; width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }}
  .free-toggle {{ display: flex; align-items: center; gap: 8px; font-size: 12px; font-weight: 600; cursor: pointer; color: var(--green); user-select: none; }}
  .free-toggle input {{ accent-color: var(--green); width: 14px; height: 14px; cursor: pointer; margin: 0; }}

  /* Search Box */
  .search-input-wrap {{ position: relative; display: flex; align-items: center; }}
  #search-input {{ width:100%; background:var(--bg); border:1px solid var(--border); color:var(--fg); padding:8px 36px 8px 10px; border-radius:var(--radius-sm); font-size:13px; font-family:inherit; transition: border-color 0.15s ease, box-shadow 0.15s ease; }}
  #search-input:focus {{ outline:none; border-color:var(--accent); box-shadow: 0 0 0 3px var(--accent-glow); }}
  #search-input::placeholder {{ color:var(--muted); }}
  .search-kbd {{ position: absolute; right: 10px; background: rgba(255, 255, 255, 0.08); color: var(--muted); font-size: 11px; padding: 1px 6px; border-radius: 4px; pointer-events: none; font-family: monospace; border: 1px solid rgba(255,255,255,0.06); }}
  .search-clear-btn {{ position: absolute; right: 8px; background: none; border: none; color: var(--muted); font-size: 16px; cursor: pointer; padding: 2px 6px; line-height: 1; }}
  .search-clear-btn:hover {{ color: var(--fg); }}
  .search-status {{ margin-top: 6px; font-size: 11px; color: var(--accent); font-weight: 500; }}

  /* Week navigation */
  .week-nav {{ display:flex; align-items:center; gap:8px; flex-wrap:wrap; background: var(--card); border: 1px solid var(--border); border-radius: var(--radius-md); padding: 8px 12px; }}
  .week-nav.bottom {{ justify-content: center; }}
  .week-nav button {{ background: transparent; color: var(--fg); border: 1px solid var(--border); border-radius: 999px; padding: 4px 12px; font-size: 12px; cursor: pointer; font-family: inherit; }}
  .week-nav button:hover {{ border-color: var(--accent); color: var(--accent); }}
  .week-nav button[aria-pressed="true"], .week-nav button.active {{ background: var(--accent); color: #0c0e14; border-color: var(--accent); font-weight: 600; }}
  #week-label, #week-label-b {{ font-size: 13px; font-weight: 600; color: var(--fg); flex: 1; text-align: center; min-width: 160px; }}
  .week-nav.bottom #week-label-b {{ flex: 0; padding: 0 12px; }}
  .mini-cal {{ background: var(--card); border: 1px solid var(--border); border-radius: var(--radius-md); padding: 10px 12px; }}
  .mini-cal-head {{ display:flex; align-items:center; gap:8px; margin-bottom: 6px; }}
  .mini-cal-head button {{ background: transparent; color: var(--fg); border: 1px solid var(--border); border-radius: 6px; padding: 2px 10px; font-size: 14px; cursor: pointer; font-family: inherit; line-height: 1; }}
  .mini-cal-head button:hover {{ border-color: var(--accent); color: var(--accent); }}
  #cal-month-label {{ flex: 1; text-align: center; font-size: 13px; font-weight: 600; }}
  .mini-cal-grid {{ display: grid; grid-template-columns: repeat(7, 1fr); gap: 2px; font-size: 11px; }}
  .mini-cal-grid .dow {{ text-align: center; color: var(--muted); font-size: 10px; padding: 2px 0; letter-spacing: 0.04em; }}
  .mini-cal-grid .d {{ text-align: center; padding: 5px 0; border-radius: 6px; cursor: pointer; color: var(--muted); background: transparent; border: 1px solid transparent; position: relative; }}
  .mini-cal-grid .d.has-events {{ color: var(--fg); }}
  .mini-cal-grid .d.has-events::after {{ content:''; position:absolute; bottom: 2px; left: 50%; transform: translateX(-50%); width: 4px; height: 4px; border-radius: 50%; background: var(--accent); }}
  .mini-cal-grid .d.today {{ border-color: var(--border); }}
  .mini-cal-grid .d.in-week {{ background: rgba(93,155,255,0.12); color: var(--fg); }}
  .mini-cal-grid .d.anchor {{ background: var(--accent); color: #0c0e14; font-weight: 700; }}
  .mini-cal-grid .d.anchor::after {{ background: #0c0e14; }}
  .mini-cal-grid .d.blank {{ cursor: default; }}
  .mini-cal-grid .d:not(.blank):hover {{ border-color: var(--accent); }}
  .event.hidden {{ display: none; }}
  .day.empty, .day.out-of-week {{ display: none; }}
  .ongoing {{ margin-top: 4px; }}
  .ongoing h2 {{ margin: 0 0 4px; font-size: 15px; font-weight: 600; display:flex; align-items:center; gap:8px; color: var(--fg); }}
  .ongoing .hint {{ margin: 0 0 10px; color: var(--muted); font-size: 12px; }}
  .ongoing ul {{ list-style: none; padding: 14px 18px; margin: 0; background: var(--card); border: 1px solid var(--border); border-radius: var(--radius-md); max-height: 420px; overflow-y: auto; }}
  .ongoing .event {{ padding: 8px 12px; }}
  footer {{ max-width: 1320px; margin: 0 auto; padding: 0 24px 32px; color: var(--muted); font-size: 12px; text-align: center; }}

  /* Mobile Responsive */
  .mobile-filter-bar {{ display: none; }}
  .mobile-filter-close {{ display: none; }}
  @media (max-width: 1100px) {{
    .layout {{ grid-template-columns: 240px minmax(0, 1fr); }}
    aside.useful {{ position: static; grid-column: 1 / -1; max-height: none; }}
  }}
  @media (max-width: 860px) {{
    .banner-title {{ font-size: 28px; }}
    .banner {{ min-height: 190px; padding: 24px 16px 16px; width: 100%; max-width: 100vw; }}
    .banner-meta-pill {{
      border-radius: var(--radius-md);
      font-size: 12px;
      padding: 6px 12px;
      gap: 6px 10px;
      max-width: 100%;
    }}
    .layout {{
      grid-template-columns: minmax(0, 1fr);
      padding: 12px;
      gap: 12px;
      width: 100%;
      max-width: 100vw;
      box-sizing: border-box;
      overflow-x: hidden;
    }}
    .mobile-filter-bar {{ display: block; margin-bottom: 8px; }}
    .mobile-filter-btn {{
      width: 100%;
      background: var(--card);
      border: 1px solid var(--border);
      color: var(--fg);
      padding: 10px 14px;
      border-radius: var(--radius-md);
      font-size: 13px;
      font-weight: 600;
      display: flex;
      align-items: center;
      justify-content: space-between;
      cursor: pointer;
      font-family: inherit;
    }}
    aside.filters {{ display: none; }}
    aside.filters.mobile-open {{
      display: flex;
      position: fixed;
      inset: 0;
      z-index: 999;
      background: var(--bg);
      padding: 20px;
      max-height: 100vh;
      overflow-y: auto;
    }}
    .mobile-filter-close {{
      display: block;
      background: var(--accent);
      color: #0c0e14;
      border: none;
      padding: 10px;
      border-radius: var(--radius-sm);
      font-weight: 700;
      font-size: 14px;
      cursor: pointer;
      font-family: inherit;
      margin-bottom: 12px;
    }}
    .location-chips-bar {{
      padding: 6px 10px;
      gap: 6px;
    }}
    .loc-chip {{
      padding: 5px 12px;
      font-size: 12px;
    }}
    .quick-chips-bar {{
      flex-wrap: nowrap;
      overflow-x: auto;
      white-space: nowrap;
      -webkit-overflow-scrolling: touch;
      scrollbar-width: none;
      -ms-overflow-style: none;
      padding: 8px 10px;
      gap: 6px;
    }}
    .quick-chips-bar::-webkit-scrollbar {{
      display: none;
    }}
    .chip {{
      flex-shrink: 0;
      padding: 5px 12px;
      font-size: 12px;
    }}
    .chip-free {{ margin-left: 0; }}

    .week-nav {{
      justify-content: space-between;
      gap: 6px;
      padding: 8px 10px;
      flex-wrap: wrap;
    }}
    #week-label, #week-label-b {{
      min-width: 0;
      width: 100%;
      flex-basis: 100%;
      order: -1;
      margin-bottom: 4px;
      font-size: 12px;
      text-align: center;
    }}

    .event {{
      grid-template-columns: 66px minmax(0, 1fr);
      gap: 8px;
      padding: 8px 10px;
    }}
    .what {{
      min-width: 0;
      overflow-wrap: break-word;
      word-break: break-word;
    }}
    .venue-tag {{
      font-size: 11px;
      gap: 4px;
    }}
    .cal-links {{
      margin-left: 0;
      margin-top: 2px;
    }}
    .day {{
      padding: 12px 14px 10px;
    }}
    .day h2 {{
      font-size: 15px;
    }}
    aside.useful {{
      grid-column: 1 / -1;
      width: 100%;
      max-width: 100%;
      box-sizing: border-box;
    }}
  }}
</style>
</head>
<body>
  <div class="banner">
    <div class="banner-svg-wrap">
      {BANNER_SVG}
    </div>
    <div class="banner-gradient-overlay"></div>
    <div class="banner-inner">
      <div class="banner-top-tag"><span class="live-pulse"></span> NYC LIVE EVENTS &amp; SHOWS</div>
      <h1 class="banner-title">NYC Events</h1>
      <div class="banner-meta-pill">
        {weather_pill_html}
        <span class="pill-dot">·</span>
        <span class="pill-stat"><strong>{total:,}</strong> events · <strong>{len(venue_list)}</strong> venues &amp; feeds</span>
        <span class="pill-dot">·</span>
        <a href="?refresh=1" class="pill-refresh" title="Force refresh live feeds">↻ Refresh</a>
      </div>
    </div>
  </div>
  <div class="layout">
    <div class="mobile-filter-bar">
      <button type="button" id="mobile-filter-toggle" class="mobile-filter-btn">
        <span>⚙️ Filter Venues &amp; Categories</span>
        <span id="mobile-filter-badge" class="count">All</span>
      </button>
    </div>
    <aside class="filters" id="sidebar-filters">
      <button type="button" id="mobile-filter-close" class="mobile-filter-close">✕ Done Filtering</button>
      <div class="filter-group">
        <h3>Search</h3>
        <div class="search-input-wrap">
          <input type="text" id="search-input" placeholder="Search events, venues, performers…" autocomplete="off">
          <span class="search-kbd" id="search-kbd" title="Press / or Cmd+K to search">/</span>
          <button type="button" id="search-clear" class="search-clear-btn" aria-label="Clear search" hidden>×</button>
        </div>
        <div id="search-status" class="search-status" hidden>
          <span id="search-count">0</span> events found
        </div>
      </div>
      <div class="filter-group">
        <label class="free-toggle" for="free-only-chk">
          <input type="checkbox" id="free-only-chk">
          <span>✨ Free events only</span>
        </label>
        <label class="free-toggle" for="guestlist-only-chk" style="margin-top:6px;">
          <input type="checkbox" id="guestlist-only-chk">
          <span>🎟️ Free club guestlists only</span>
        </label>
      </div>
      <div class="filter-group">
        <h3>Category <span class="spacer"></span> <button type="button" id="cat-all">all</button> <button type="button" id="cat-none">none</button></h3>
        <div class="chk-grid">{bucket_boxes}</div>
      </div>
      <div class="filter-group">
        <h3>Borough / Area <span class="spacer"></span> <button type="button" id="city-all">all</button> <button type="button" id="city-none">none</button></h3>
        <div class="chk-grid">{city_boxes}</div>
      </div>
      <div class="filter-group">
        <h3>Recurrence</h3>
        <div class="chk-grid">{recur_boxes}</div>
      </div>
      <div class="filter-group venues">
        <h3>Venue <span class="spacer"></span> <button type="button" id="venue-all">all</button> <button type="button" id="venue-none">none</button></h3>
        <div class="chk-grid">{venue_boxes}</div>
      </div>
    </aside>
    <main>
      <div class="location-chips-bar" id="location-chips">
        <button type="button" class="loc-chip active" data-city="all">📍 All Boroughs</button>
        <button type="button" class="loc-chip" data-city="manhattan"><span class="city-dot" style="background:#5d9bff"></span>Manhattan</button>
        <button type="button" class="loc-chip" data-city="brooklyn"><span class="city-dot" style="background:#e05a6b"></span>Brooklyn</button>
        <button type="button" class="loc-chip" data-city="queens"><span class="city-dot" style="background:#f29e4c"></span>Queens</button>
        <button type="button" class="loc-chip" data-city="bronx"><span class="city-dot" style="background:#4ade80"></span>The Bronx</button>
        <button type="button" class="loc-chip" data-city="staten_island"><span class="city-dot" style="background:#a78bfa"></span>Staten Island</button>
        <button type="button" class="loc-chip" data-city="other"><span class="city-dot" style="background:#9aa3b2"></span>Tri-State</button>
      </div>
      <div class="quick-chips-bar" id="quick-chips">
        <button type="button" class="chip active" data-time="all">All Upcoming</button>
        <button type="button" class="chip" data-time="today">⚡ Today</button>
        <button type="button" class="chip" data-time="tomorrow">Tomorrow</button>
        <button type="button" class="chip" data-time="weekend">🎉 This Weekend</button>
        <button type="button" class="chip" data-time="week">📅 Next 7 Days</button>
        <button type="button" class="chip chip-guestlist" id="quick-guestlist-chip">🎟️ Guestlists</button>
        <button type="button" class="chip chip-free" id="quick-free-chip">✨ Free Only</button>
      </div>
      <div class="week-nav" id="week-nav">
        <button type="button" id="week-prev" aria-label="Previous week">← prev</button>
        <span id="week-label">Loading…</span>
        <button type="button" id="week-next" aria-label="Next week">next →</button>
        <button type="button" id="week-today">today</button>
        <button type="button" id="week-all" data-mode="week">show all</button>
        <button type="button" id="cal-toggle" aria-expanded="false">📅 pick date</button>
      </div>
      <div class="mini-cal" id="mini-cal" hidden>
        <div class="mini-cal-head">
          <button type="button" id="cal-prev-month" aria-label="Previous month">‹</button>
          <span id="cal-month-label"></span>
          <button type="button" id="cal-next-month" aria-label="Next month">›</button>
        </div>
        <div class="mini-cal-grid" id="mini-cal-grid"></div>
      </div>
      {"".join(sections)}
      <div class="week-nav bottom">
        <button type="button" id="week-prev-b" aria-label="Previous week">← prev</button>
        <span id="week-label-b"></span>
        <button type="button" id="week-next-b" aria-label="Next week">next →</button>
      </div>
      {ongoing_section}
    </main>
    {useful_sidebar}
  </div>
  <footer>Scraped live from each venue's site. Times shown in Eastern.</footer>
  <script>
    const catBoxes = document.querySelectorAll('.cat-chk');
    const venueBoxes = document.querySelectorAll('.venue-chk');
    const recurBoxes = document.querySelectorAll('.recur-chk');
    const cityBoxes = document.querySelectorAll('.city-chk');
    const searchInput = document.getElementById('search-input');
    const searchKbd = document.getElementById('search-kbd');
    const searchClear = document.getElementById('search-clear');
    const searchStatus = document.getElementById('search-status');
    const searchCount = document.getElementById('search-count');
    const freeOnlyChk = document.getElementById('free-only-chk');
    const guestlistOnlyChk = document.getElementById('guestlist-only-chk');

    const locChips = document.querySelectorAll('#location-chips .loc-chip');
    const quickChips = document.querySelectorAll('#quick-chips .chip[data-time]');
    const quickFreeChip = document.getElementById('quick-free-chip');
    const quickGuestlistChip = document.getElementById('quick-guestlist-chip');
    let timeFilter = 'all';

    const mobileToggle = document.getElementById('mobile-filter-toggle');
    const mobileClose = document.getElementById('mobile-filter-close');
    const sidebarFilters = document.getElementById('sidebar-filters');
    const mobileBadge = document.getElementById('mobile-filter-badge');

    const daySections = Array.from(document.querySelectorAll('.day[data-date]'));
    const eventDates = new Set(
      daySections.map(d => d.dataset.date).filter(s => s && s !== 'tba')
    );
    function parseISO(s) {{ const [y, m, d] = s.split('-').map(Number); return new Date(y, m - 1, d); }}
    function fmtISO(d) {{
      const y = d.getFullYear(), m = String(d.getMonth() + 1).padStart(2, '0'), da = String(d.getDate()).padStart(2, '0');
      return `${{y}}-${{m}}-${{da}}`;
    }}
    function addDays(d, n) {{ const c = new Date(d); c.setDate(c.getDate() + n); return c; }}
    const MONTHS = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
    function fmtShort(d) {{ return MONTHS[d.getMonth()] + ' ' + d.getDate(); }}
    function fmtMonth(d) {{ return d.toLocaleString('en-US', {{ month: 'long', year: 'numeric' }}); }}

    const todayISO = fmtISO(new Date());
    let anchor = parseISO(todayISO);
    let showAll = true;
    let calMonth = new Date(anchor.getFullYear(), anchor.getMonth(), 1);

    function weekDates() {{
      const out = [];
      for (let i = 0; i < 7; i++) out.push(fmtISO(addDays(anchor, i)));
      return out;
    }}
    function updateWeekLabel() {{
      const end = addDays(anchor, 6);
      const label = (timeFilter === 'all' || showAll)
        ? 'Showing all upcoming'
        : `${{fmtShort(anchor)}} – ${{fmtShort(end)}}, ${{end.getFullYear()}}`;
      document.getElementById('week-label').textContent = label;
      const b = document.getElementById('week-label-b');
      if (b) b.textContent = label;
      const btn = document.getElementById('week-all');
      btn.textContent = (timeFilter === 'all' || showAll) ? 'week view' : 'show all';
      btn.setAttribute('aria-pressed', (timeFilter === 'all' || showAll) ? 'true' : 'false');
    }}

    function updateQuickChipsUI() {{
      quickChips.forEach(chip => {{
        chip.classList.toggle('active', chip.dataset.time === timeFilter);
      }});
      if (quickFreeChip) {{
        quickFreeChip.classList.toggle('active', freeOnlyChk ? freeOnlyChk.checked : false);
      }}
      if (quickGuestlistChip) {{
        quickGuestlistChip.classList.toggle('active', guestlistOnlyChk ? guestlistOnlyChk.checked : false);
      }}
    }}

    function updateLocChipsUI() {{
      const allCities = cityBoxes.length;
      const checkedCities = Array.from(cityBoxes).filter(b => b.checked).map(b => b.value);
      locChips.forEach(chip => {{
        const city = chip.dataset.city;
        if (city === 'all') {{
          chip.classList.toggle('active', checkedCities.length === allCities || checkedCities.length === 0);
        }} else {{
          chip.classList.toggle('active', checkedCities.length === 1 && checkedCities[0] === city);
        }}
      }});
    }}

    function updateSearchUI() {{
      const val = searchInput.value.trim();
      if (searchClear) searchClear.hidden = !val;
      if (searchKbd) searchKbd.hidden = !!val;
      if (searchStatus && searchCount) {{
        if (val) {{
          const matched = document.querySelectorAll('.event:not(.hidden)').length;
          searchCount.textContent = matched;
          searchStatus.hidden = false;
        }} else {{
          searchStatus.hidden = true;
        }}
      }}
    }}

    function updateMobileBadge() {{
      if (!mobileBadge) return;
      const allCats = catBoxes.length;
      const chkCats = Array.from(catBoxes).filter(b => b.checked).length;
      const allVenues = venueBoxes.length;
      const chkVenues = Array.from(venueBoxes).filter(b => b.checked).length;
      const isFree = freeOnlyChk && freeOnlyChk.checked;
      const isGuestlist = guestlistOnlyChk && guestlistOnlyChk.checked;
      const isFiltered = (chkCats < allCats) || (chkVenues < allVenues) || isFree || isGuestlist || searchInput.value.trim();
      mobileBadge.textContent = isFiltered ? 'Active' : 'All';
      mobileBadge.style.color = isFiltered ? 'var(--accent)' : '';
    }}

    function stateToHash() {{
      const params = new URLSearchParams();
      const q = searchInput.value.trim();
      if (q) params.set('q', q);

      const allCats = Array.from(catBoxes).map(b => b.value);
      const checkedCats = Array.from(catBoxes).filter(b => b.checked).map(b => b.value);
      if (checkedCats.length > 0 && checkedCats.length < allCats.length) params.set('cat', checkedCats.join(','));

      const allCities = Array.from(cityBoxes).map(b => b.value);
      const checkedCities = Array.from(cityBoxes).filter(b => b.checked).map(b => b.value);
      if (checkedCities.length > 0 && checkedCities.length < allCities.length) params.set('city', checkedCities.join(','));

      if (freeOnlyChk && freeOnlyChk.checked) params.set('free', '1');
      if (guestlistOnlyChk && guestlistOnlyChk.checked) params.set('guestlist', '1');

      if (timeFilter !== 'all') params.set('t', timeFilter);
      if (!showAll && fmtISO(anchor) !== todayISO) params.set('d', fmtISO(anchor));

      const hash = params.toString();
      history.replaceState(null, '', hash ? '#' + hash : location.pathname + location.search);
    }}

    function hashToState() {{
      const hash = location.hash.slice(1);
      if (!hash) return;
      const params = new URLSearchParams(hash);

      if (params.has('q')) searchInput.value = params.get('q');
      if (params.get('free') === '1' && freeOnlyChk) freeOnlyChk.checked = true;
      if (params.get('guestlist') === '1' && guestlistOnlyChk) guestlistOnlyChk.checked = true;

      if (params.has('t')) {{
        timeFilter = params.get('t');
        showAll = (timeFilter === 'all');
      }}

      if (params.has('cat')) {{
        const vals = new Set(params.get('cat').split(','));
        catBoxes.forEach(b => {{ b.checked = vals.has(b.value); }});
      }}

      if (params.has('city')) {{
        const vals = new Set(params.get('city').split(','));
        cityBoxes.forEach(b => {{ b.checked = vals.has(b.value); }});
      }}

      if (params.has('d')) {{
        const d = params.get('d');
        if (d === 'all') {{ showAll = true; timeFilter = 'all'; }}
        else {{ anchor = parseISO(d); calMonth = new Date(anchor.getFullYear(), anchor.getMonth(), 1); }}
      }}
    }}

    function apply() {{
      const cats = new Set(Array.from(catBoxes).filter(b => b.checked).map(b => b.value));
      const venues = new Set(Array.from(venueBoxes).filter(b => b.checked).map(b => b.value));
      const recurs = new Set(Array.from(recurBoxes).filter(b => b.checked).map(b => b.value));
      const cities = new Set(Array.from(cityBoxes).filter(b => b.checked).map(b => b.value));
      const searchText = searchInput.value.trim().toLowerCase();
      const freeOnly = freeOnlyChk ? freeOnlyChk.checked : false;
      const guestlistOnly = guestlistOnlyChk ? guestlistOnlyChk.checked : false;
      const week = new Set(weekDates());

      document.querySelectorAll('.event').forEach(li => {{
        const catOk = cats.has(li.dataset.bucket);
        const venueOk = venues.has(li.dataset.venue);
        const recurOk = recurs.has(li.dataset.recur);
        const cityOk = cities.has(li.dataset.city);
        const freeOk = !freeOnly || li.dataset.free === 'true';
        const guestlistOk = !guestlistOnly || li.dataset.guestlist === 'true';
        const searchOk = !searchText || li.textContent.toLowerCase().includes(searchText);
        li.classList.toggle('hidden', !(catOk && venueOk && recurOk && cityOk && searchOk && freeOk && guestlistOk));
      }});

      document.querySelectorAll('.bucket').forEach(b => {{
        const visible = b.querySelectorAll('.event:not(.hidden)').length;
        b.classList.toggle('empty', visible === 0);
      }});
      document.querySelectorAll('.city-section').forEach(sec => {{
        const visible = sec.querySelectorAll('.event:not(.hidden)').length;
        sec.classList.toggle('empty', visible === 0);
      }});

      const todayDate = parseISO(todayISO);
      const dayOfWeek = todayDate.getDay();
      let daysToSat = (6 - dayOfWeek + 7) % 7;
      if (dayOfWeek === 0) daysToSat = -1;
      const satISO = fmtISO(addDays(todayDate, daysToSat));
      const sunISO = fmtISO(addDays(todayDate, daysToSat + 1));
      const tomorrowISO = fmtISO(addDays(todayDate, 1));

      daySections.forEach(day => {{
        const date = day.dataset.date;
        let inTime = true;
        if (timeFilter === 'today') {{
          inTime = (date === todayISO);
        }} else if (timeFilter === 'tomorrow') {{
          inTime = (date === tomorrowISO);
        }} else if (timeFilter === 'weekend') {{
          inTime = (date === satISO || date === sunISO);
        }} else if (timeFilter === 'week') {{
          inTime = (date === 'tba' || week.has(date));
        }} else {{
          inTime = showAll || date === 'tba' || week.has(date);
        }}
        day.classList.toggle('out-of-week', !inTime);
        const visible = day.querySelectorAll('.event:not(.hidden)').length;
        day.classList.toggle('empty', visible === 0);
      }});

      renderCal();
      updateWeekLabel();
      updateQuickChipsUI();
      updateLocChipsUI();
      updateSearchUI();
      updateMobileBadge();
      stateToHash();
    }}

    function renderCal() {{
      const grid = document.getElementById('mini-cal-grid');
      if (!grid) return;
      const year = calMonth.getFullYear(), month = calMonth.getMonth();
      document.getElementById('cal-month-label').textContent = fmtMonth(calMonth);
      const first = new Date(year, month, 1);
      const startPad = first.getDay();
      const daysInMonth = new Date(year, month + 1, 0).getDate();
      const week = new Set(weekDates());
      let html = ['Su','Mo','Tu','We','Th','Fr','Sa'].map(d => `<div class="dow">${{d}}</div>`).join('');
      for (let i = 0; i < startPad; i++) html += '<div class="d blank"></div>';
      for (let d = 1; d <= daysInMonth; d++) {{
        const iso = fmtISO(new Date(year, month, d));
        const classes = ['d'];
        if (eventDates.has(iso)) classes.push('has-events');
        if (iso === todayISO) classes.push('today');
        if (!showAll && week.has(iso)) classes.push('in-week');
        if (iso === fmtISO(anchor)) classes.push('anchor');
        html += `<div class="${{classes.join(' ')}}" data-date="${{iso}}">${{d}}</div>`;
      }}
      grid.innerHTML = html;
    }}

    function shiftWeek(delta) {{
      timeFilter = 'week';
      showAll = false;
      anchor = addDays(anchor, delta);
      calMonth = new Date(anchor.getFullYear(), anchor.getMonth(), 1);
      apply();
    }}
    function setAnchor(iso) {{
      timeFilter = 'week';
      showAll = false;
      anchor = parseISO(iso);
      apply();
    }}

    quickChips.forEach(chip => {{
      chip.addEventListener('click', () => {{
        timeFilter = chip.dataset.time;
        const todayDate = parseISO(todayISO);
        const dayOfWeek = todayDate.getDay();
        let daysToSat = (6 - dayOfWeek + 7) % 7;
        if (dayOfWeek === 0) daysToSat = -1;

        if (timeFilter === 'all') {{
          showAll = true;
        }} else if (timeFilter === 'today') {{
          showAll = false;
          anchor = parseISO(todayISO);
          calMonth = new Date(anchor.getFullYear(), anchor.getMonth(), 1);
        }} else if (timeFilter === 'tomorrow') {{
          showAll = false;
          anchor = addDays(parseISO(todayISO), 1);
          calMonth = new Date(anchor.getFullYear(), anchor.getMonth(), 1);
        }} else if (timeFilter === 'weekend') {{
          showAll = false;
          anchor = addDays(todayDate, daysToSat);
          calMonth = new Date(anchor.getFullYear(), anchor.getMonth(), 1);
        }} else if (timeFilter === 'week') {{
          showAll = false;
          anchor = parseISO(todayISO);
          calMonth = new Date(anchor.getFullYear(), anchor.getMonth(), 1);
        }}
        apply();
      }});
    }});

    if (quickFreeChip && freeOnlyChk) {{
      quickFreeChip.addEventListener('click', () => {{
        freeOnlyChk.checked = !freeOnlyChk.checked;
        apply();
      }});
    }}
    if (quickGuestlistChip && guestlistOnlyChk) {{
      quickGuestlistChip.addEventListener('click', () => {{
        guestlistOnlyChk.checked = !guestlistOnlyChk.checked;
        apply();
      }});
    }}
    if (guestlistOnlyChk) guestlistOnlyChk.addEventListener('change', apply);

    document.addEventListener('keydown', (e) => {{
      if ((e.key === '/' || ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k')) &&
          document.activeElement !== searchInput &&
          !['input', 'textarea'].includes((document.activeElement.tagName || '').toLowerCase())) {{
        e.preventDefault();
        searchInput.focus();
        searchInput.select();
      }} else if (e.key === 'Escape' && document.activeElement === searchInput) {{
        searchInput.value = '';
        searchInput.blur();
        apply();
      }}
    }});

    if (searchClear) {{
      searchClear.addEventListener('click', () => {{
        searchInput.value = '';
        apply();
        searchInput.focus();
      }});
    }}

    if (mobileToggle && sidebarFilters) {{
      mobileToggle.addEventListener('click', () => {{
        sidebarFilters.classList.add('mobile-open');
        document.body.style.overflow = 'hidden';
      }});
    }}
    if (mobileClose && sidebarFilters) {{
      mobileClose.addEventListener('click', () => {{
        sidebarFilters.classList.remove('mobile-open');
        document.body.style.overflow = '';
      }});
    }}

    document.getElementById('week-prev').addEventListener('click', () => shiftWeek(-7));
    document.getElementById('week-next').addEventListener('click', () => shiftWeek(7));
    document.getElementById('week-prev-b').addEventListener('click', () => shiftWeek(-7));
    document.getElementById('week-next-b').addEventListener('click', () => shiftWeek(7));
    document.getElementById('week-today').addEventListener('click', () => {{ setAnchor(todayISO); calMonth = new Date(anchor.getFullYear(), anchor.getMonth(), 1); apply(); }});
    document.getElementById('week-all').addEventListener('click', () => {{
      if (showAll || timeFilter === 'all') {{
        showAll = false;
        timeFilter = 'week';
        anchor = parseISO(todayISO);
      }} else {{
        showAll = true;
        timeFilter = 'all';
      }}
      apply();
    }});
    document.getElementById('cal-toggle').addEventListener('click', (e) => {{
      const cal = document.getElementById('mini-cal');
      const open = cal.hasAttribute('hidden');
      if (open) cal.removeAttribute('hidden'); else cal.setAttribute('hidden', '');
      e.currentTarget.setAttribute('aria-expanded', open ? 'true' : 'false');
    }});
    document.getElementById('cal-prev-month').addEventListener('click', () => {{
      calMonth = new Date(calMonth.getFullYear(), calMonth.getMonth() - 1, 1);
      renderCal();
    }});
    document.getElementById('cal-next-month').addEventListener('click', () => {{
      calMonth = new Date(calMonth.getFullYear(), calMonth.getMonth() + 1, 1);
      renderCal();
    }});
    document.getElementById('mini-cal-grid').addEventListener('click', (e) => {{
      const cell = e.target.closest('.d:not(.blank)');
      if (!cell || !cell.dataset.date) return;
      setAnchor(cell.dataset.date);
    }});

    if (freeOnlyChk) freeOnlyChk.addEventListener('change', apply);
    catBoxes.forEach(b => b.addEventListener('change', apply));
    venueBoxes.forEach(b => b.addEventListener('change', apply));
    recurBoxes.forEach(b => b.addEventListener('change', apply));
    cityBoxes.forEach(b => b.addEventListener('change', apply));
    searchInput.addEventListener('input', apply);
    document.getElementById('cat-all').addEventListener('click', () => {{ catBoxes.forEach(b => b.checked = true); apply(); }});
    document.getElementById('cat-none').addEventListener('click', () => {{ catBoxes.forEach(b => b.checked = false); apply(); }});
    document.getElementById('venue-all').addEventListener('click', () => {{ venueBoxes.forEach(b => b.checked = true); apply(); }});
    document.getElementById('venue-none').addEventListener('click', () => {{ venueBoxes.forEach(b => b.checked = false); apply(); }});
    document.getElementById('city-all').addEventListener('click', () => {{ cityBoxes.forEach(b => b.checked = true); apply(); }});
    document.getElementById('city-none').addEventListener('click', () => {{ cityBoxes.forEach(b => b.checked = false); apply(); }});

    locChips.forEach(chip => {{
      chip.addEventListener('click', () => {{
        const targetCity = chip.dataset.city;
        if (targetCity === 'all') {{
          cityBoxes.forEach(b => {{ b.checked = true; }});
        }} else {{
          const checked = Array.from(cityBoxes).filter(b => b.checked).map(b => b.value);
          if (checked.length === 1 && checked[0] === targetCity) {{
            cityBoxes.forEach(b => {{ b.checked = true; }});
          }} else {{
            cityBoxes.forEach(b => {{
              b.checked = (b.value === targetCity);
            }});
          }}
        }}
        apply();
      }});
    }});

    function downloadICS(title, dateStr, venue, url) {{
      if (!dateStr) return;
      let dt;
      try {{ dt = new Date(dateStr); }} catch(e) {{ return; }}
      if (isNaN(dt.getTime())) return;
      function pad(n) {{ return n < 10 ? '0' + n : n; }}
      function toICS(d) {{
        return d.getUTCFullYear() + pad(d.getUTCMonth()+1) + pad(d.getUTCDate()) + 'T' +
               pad(d.getUTCHours()) + pad(d.getUTCMinutes()) + pad(d.getUTCSeconds()) + 'Z';
      }}
      const start = toICS(dt);
      const end = toICS(new Date(dt.getTime() + 2 * 3600 * 1000));
      function cleanText(str) {{
        return (str || '').split(String.fromCharCode(10)).join(' ')
                          .split(String.fromCharCode(13)).join('')
                          .split(',').join('\\\\,');
      }}
      const cleanTitle = cleanText(title || 'Event');
      const cleanVenue = cleanText(venue || 'New York, NY');
      const cleanUrl = (url || '').split(String.fromCharCode(10)).join('')
                                  .split(String.fromCharCode(13)).join('');
      const ics = [
        'BEGIN:VCALENDAR',
        'VERSION:2.0',
        'PRODID:-//NYC Events//EN',
        'BEGIN:VEVENT',
        'SUMMARY:' + cleanTitle,
        'DTSTART:' + start,
        'DTEND:' + end,
        'LOCATION:' + cleanVenue,
        'DESCRIPTION:' + cleanUrl,
        'END:VEVENT',
        'END:VCALENDAR'
      ].join(String.fromCharCode(13, 10));
      const blob = new Blob([ics], {{ type: 'text/calendar;charset=utf-8' }});
      const link = document.createElement('a');
      link.href = URL.createObjectURL(blob);
      link.download = (title.replace(/[^a-zA-Z0-9]/g, '_') || 'event') + '.ics';
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    }}

    document.addEventListener('click', (e) => {{
      const btn = e.target.closest('.ics-btn');
      if (!btn) return;
      e.preventDefault();
      downloadICS(btn.dataset.title, btn.dataset.date, btn.dataset.venue, btn.dataset.url);
    }});

    hashToState();
    apply();
  </script>
</body>
</html>"""
