"""Which NYC borough a coordinate falls in, from the official borough boundaries.

Uses the water-inclusive boundaries (nyc_boroughs.json), so piers, boats and island venues
resolve to the borough that governs them, and anything outside the city (Hoboken, Jersey
City, Yonkers, Nassau) resolves to None. A lat/lng rectangle can't tell those apart.
"""

import json
import os
import re
import time
from functools import lru_cache

import requests

_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "nyc_boroughs.json")


@lru_cache(maxsize=1)
def _boroughs():
    with open(_PATH, "r", encoding="utf-8") as f:
        raw = json.load(f)["boroughs"]
    out = []
    for name, polys in raw.items():
        for poly in polys:
            ring = poly[0]
            xs = [p[0] for p in ring]
            ys = [p[1] for p in ring]
            out.append((name, (min(xs), min(ys), max(xs), max(ys)), poly))
    return out


def _in_ring(x, y, ring):
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


@lru_cache(maxsize=50000)
def borough_at(lat, lng):
    """'manhattan' | 'brooklyn' | 'queens' | 'bronx' | 'staten_island', or None outside NYC."""
    try:
        y, x = float(lat), float(lng)
    except (TypeError, ValueError):
        return None
    for name, (x0, y0, x1, y1), poly in _boroughs():
        if not (x0 <= x <= x1 and y0 <= y <= y1):
            continue
        if _in_ring(x, y, poly[0]) and not any(_in_ring(x, y, hole) for hole in poly[1:]):
            return name
    return None


def in_nyc(lat, lng):
    return borough_at(lat, lng) is not None


# Out-of-city places that NYC feeds list (text markers; matched as substrings, lowercase).
TRISTATE_NEEDLES = (
    # New Jersey markers & towns
    "new jersey", ", nj", " nj ", " nj,", "hoboken", "jersey city", "newark", "asbury park",
    "montclair", "paramus", "hackensack", "westwood", "maywood", "weehawken", "secaucus",
    "englewood", "fort lee", "edgewater", "morristown", "lyndhurst", "wanaque", "loch arbour",
    "wyckoff, nj", "wyckoff nj", "ridgewood, nj", "ridgewood nj",
    "west orange", "paterson", "clifton", "passaic", "teaneck", "ridgefield",
    # Connecticut markers & towns
    "connecticut", ", ct", " ct ", " ct,", "stamford", "greenwich, ct", "greenwich ct",
    "norwalk", "new haven", "bridgeport", "darien", "westport",
    # Westchester, Hudson Valley & Upstate NY
    "new rochelle", "white plains", "yonkers", "port chester", "tarrytown", "nyack",
    "scarsdale", "mount vernon, ny", "mount vernon ny", "peekskill", "ossining", "mamaroneck", "rye, ny", "rye ny",
    "bethel woods", "hudson valley", "woodbury", "poughkeepsie", "beacon, ny", "sleepy hollow",
    # Long Island (Nassau / Suffolk)
    "long island", "nassau county", "suffolk county", "huntington", "garden city", "hempstead",
    "patchogue", "babylon", "montauk", "hamptons", "riverhead", "westbury, ny",
    "mineola", "rockville centre", "nassau coliseum", "tilles center", "stephen talkhouse", "amagansett",
    # Venues outside the city that city feeds list by name only
    "metlife stadium", "wellmont theater", "count basie", "prudential center", "njpac",
    "new jersey performing arts", "klein memorial", "atlantic city", "catskills", "tarrytown",
)


def outside_nyc_text(text):
    """True when venue/address text names a place outside the five boroughs."""
    h = f" {(text or '').lower()} ".replace("long island city", "")
    if any(n in h for n in TRISTATE_NEEDLES):
        return True
    m = re.search(r"\b(\d{5})(?:-\d{4})?\b", h)
    if m and not re.match(r"1(?:0[0-4]|1[0-46])\d{2}$", m.group(1)):
        return True  # a ZIP outside 100xx-104xx / 110xx-114xx / 116xx
    return False


# Coordinates some feeds use when they only know "New York, NY" (City Hall).
_PLACEHOLDERS = ((40.7128, -74.0060), (40.7127, -74.0059))


def is_placeholder(lat, lng):
    try:
        y, x = float(lat), float(lng)
    except (TypeError, ValueError):
        return False
    return any(abs(y - py) < 0.0003 and abs(x - px) < 0.0003 for py, px in _PLACEHOLDERS)


_CITY_WORDS = {"new", "york", "ny", "nyc", "city", "united", "states", "usa", "us", "of", "america", "manhattan",
               "brooklyn", "queens", "bronx", "the", "staten", "island", "astoria", "flushing", "long", "harlem",
               "williamsburg", "bushwick", "county", "kings", "richmond", "area", "metro", "greater"}


def city_level_only(address, venue=""):
    """True for an address that names only a city/borough ("Misse Tango, New York City, United
    States"). Some feeds geocode those to an arbitrary point, so their coordinates mean nothing."""
    a = (address or "").lower()
    if not a.strip():
        return False
    for part in sorted(re.split(r"[,()]", (venue or "").lower()), key=len, reverse=True):
        part = part.strip()
        if len(part) > 2:
            a = a.replace(part, " ")
    words = re.findall(r"[a-z0-9]+", a)
    return not any(w not in _CITY_WORDS for w in words)


_SUFFIX = (r"st|street|ave|avenue|av|blvd|boulevard|rd|road|pl|place|pkwy|parkway|dr|drive|ln|lane|"
           r"ter|terrace|sq|square|way|plaza|plz|hwy|highway|ct|court|tpke|turnpike|broadway|bowery|loop|walk|slip|row")
_ADDR_RE = re.compile(
    r"\b(\d{1,5}(?:-\d{1,4})?)\s+((?:[nsew]\.?\s+|north\s+|south\s+|east\s+|west\s+)?"
    r"(?:broadway|bowery|avenue of the americas|ave(?:nue)?\.? [a-z](?![a-z])|(?:[a-z0-9.'&]+\s+){1,4}?(?:" + _SUFFIX + r")))\b\.?"
    r"(?:\s*(?:#|suite|ste\.?|fl\.?|floor|unit|apt\.?)\s*[\w-]+)?"
    r"(?:\s*,\s*([a-z .'-]{3,30}))?", re.I)
_LOCALITY_OK = re.compile(r"new york|nyc|\bny\s*,\s*ny\b|(?:kings|queens|bronx|richmond|new york) county|manhattan|brooklyn|queens|bronx|staten island|astoria|flushing|long island city|"
                          r"ridgewood|jamaica|forest hills|jackson heights|elmhurst|woodside|sunnyside|corona|bayside|"
                          r"harlem|williamsburg|bushwick|greenpoint|maspeth|rockaway|kew gardens|rego park|whitestone", re.I)


def extract_address(text):
    """'358 w 44th st, new york' from venue/address text, or None when there is no street
    address or nothing marks it as NYC (GeoSearch confidently matches any address to the
    nearest NYC street, so non-NYC text must never reach it)."""
    t = (text or "").replace("\n", " ")
    if outside_nyc_text(t):
        return None
    m = _ADDR_RE.search(t)
    if not m:
        return None
    house, street, locality = m.group(1), m.group(2), (m.group(3) or "").strip(" .")
    zipm = re.search(r"\b(1(?:0[0-4]|1[0-46])\d{2})\b", t)
    if not (zipm or _LOCALITY_OK.search(t)):
        return None
    where = locality if locality and _LOCALITY_OK.search(locality) else (zipm.group(1) if zipm else "new york")
    return re.sub(r"\s+", " ", f"{house} {street}, {where}".lower()).strip()


_STREET_WORDS = {"street": "st", "avenue": "ave", "av": "ave", "boulevard": "blvd", "road": "rd", "place": "pl",
                 "parkway": "pkwy", "drive": "dr", "lane": "ln", "terrace": "ter", "square": "sq", "plaza": "plz",
                 "highway": "hwy", "court": "ct", "turnpike": "tpke", "north": "n", "south": "s", "east": "e", "west": "w"}


def _street_key(street):
    street = re.sub(r"\bb'?way\b", "broadway", (street or "").lower())  # GeoSearch spells it B'WAY
    street = street.replace("avenue of the americas", "6 avenue")
    words = re.sub(r"[^a-z0-9 ]", " ", street).split()
    words = [_STREET_WORDS.get(w, w) for w in words]
    words = [re.sub(r"^(\d+)(st|nd|rd|th)$", r"\1", w) for w in words]
    core = [w for w in words if w not in ("st", "ave", "blvd", "rd", "pl", "pkwy", "dr", "ln", "ter", "sq", "plz", "hwy", "ct", "tpke", "n", "s", "e", "w")]
    return core or words  # "Court St" -> ["ct", "st"], not [] (every Court St used to be rejected)


GEOSEARCH_URL = "https://geosearch.planninglabs.nyc/v2/search"


def geocode(address, session=None, timeout=10):
    """(lat, lng, borough) for an NYC street address via NYC Planning's GeoSearch, or None.

    GeoSearch always answers with its closest match, so the result is kept only when its
    house number and street name agree with the request."""
    m = _ADDR_RE.search(address or "")
    if not m:
        return None
    house, street = m.group(1), m.group(2)
    r = (session or requests).get(GEOSEARCH_URL, params={"text": address, "size": 1}, timeout=timeout)
    r.raise_for_status()
    feats = r.json().get("features") or []
    if not feats:
        return None
    props = feats[0].get("properties") or {}
    got_house = str(props.get("housenumber") or "")
    if not got_house or (got_house != house and got_house not in house.split("-")):
        return None
    want, got = _street_key(street), _street_key(props.get("street") or "")
    if not want or not got or want[0] != got[0]:
        return None
    lng, lat = feats[0]["geometry"]["coordinates"][:2]
    borough = borough_at(lat, lng)
    if not borough:
        return None
    return round(lat, 6), round(lng, 6), borough


GEOCODE_CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "geocode_cache.json")


def load_geocode_cache(path=GEOCODE_CACHE_FILE):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_geocode_cache(cache, path=GEOCODE_CACHE_FILE):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(dict(sorted(cache.items())), f, indent=0, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, path)


def geocode_missing(addresses, cache, limit=400, gap=0.25, session=None):
    """Look up addresses not yet in `cache` (misses are cached as None too), one request at a
    time, `gap` seconds apart, at most `limit` per call. Returns how many were looked up."""
    todo = [a for a in dict.fromkeys(addresses) if a not in cache][:limit]
    for n, addr in enumerate(todo):
        if n:
            time.sleep(gap)
        try:
            hit = geocode(addr, session=session)
        except (requests.RequestException, ValueError, KeyError):
            break  # service trouble: stop for this run, try the rest next time
        cache[addr] = list(hit) if hit else None
    return len(todo)


_PARKS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "nyc_parks.json")


@lru_cache(maxsize=1)
def _parks():
    try:
        with open(_PARKS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)["parks"]
    except (OSError, ValueError, KeyError):
        return {}


def _norm_name(text):
    t = (text or "").lower().replace("&", " and ")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", t)).strip()


def park_pin(name, context=""):
    """(lat, lng, borough) for the NYC Parks property named in `name` (longest match, 2+ words),
    e.g. "Juniper Valley Park Tennis Courts" -> Juniper Valley Park. A name that exists in several
    boroughs needs the borough in `name`/`context`, else None."""
    words = _norm_name(name).split()
    parks = _parks()
    best = None
    for size in range(min(6, len(words)), 1, -1):
        for i in range(len(words) - size + 1):
            key = " ".join(words[i:i + size])
            # "Park Slope" is also the name of a Queens property: only names ending in a
            # park word count, so neighborhoods don't match
            if key in parks and words[i + size - 1] in _PARK_WORDS:
                best = parks[key]
                break
        if best:
            break
    if not best:
        return None
    hay = f" {_norm_name(name)} {_norm_name(context)} "
    named = [b for b in ("manhattan", "brooklyn", "queens", "bronx", "staten_island") if f" {b.replace('_', ' ')} " in hay]
    for lat, lng, borough in best:
        if (len(best) == 1 and not named) or borough in named:
            return lat, lng, borough
    return None


_PARK_WORDS = {"park", "playground", "garden", "gardens", "triangle", "square", "plaza", "mall", "malls", "field",
               "fields", "green", "pool", "grove", "woods", "island", "oval", "pier", "ballfield", "ballfields",
               "beach", "preserve", "reservation", "wetlands", "lawn", "meadow", "meadows", "promenade", "esplanade"}


def pin_contradicts_address(event):
    """True when the event's own address (its address field, or the "(...)" part of the venue)
    names exactly one borough and the feed's coordinates fall in another. The venue *name* is
    not used: "Brooklyn Diner" is in Manhattan."""
    venue = event.get("venue") or ""
    paren = venue[venue.find("("):] if "(" in venue else ""
    text = f" {_norm_name(event.get('address'))} {_norm_name(paren)} "
    named = {b for b in ("manhattan", "brooklyn", "queens", "bronx", "staten_island") if f" {b.replace('_', ' ')} " in text}
    if len(named) != 1:
        return False
    at = borough_at(event.get("lat"), event.get("lng"))
    return at is not None and at not in named
