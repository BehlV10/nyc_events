"""NYC Events — HTML rendering and template logic."""

import hashlib
import json
import os
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from html import escape
from urllib.parse import quote, quote_plus

from scrapers import (
    EASTERN,
    CATEGORY_BUCKETS,
    CATEGORY_STYLES,
    DEAL_LINKS,
    STATIC_LINKS,
    category_bucket,
    guess_category,
    fetch_nyc_weather,
    fetch_luckyseat_nyc,
    is_closed_show,
    is_placeholder_or_closed_event,
)
from venues_geo import resolve_event_geo


TRISTATE_NEEDLES = (
    # New Jersey markers & towns
    "new jersey", ", nj", " nj ", " nj,", "hoboken", "jersey city", "newark", "asbury park",
    "montclair", "paramus", "hackensack", "westwood", "maywood", "weehawken", "secaucus",
    "englewood", "fort lee", "edgewater", "morristown", "lyndhurst", "wanaque", "loch arbour",
    "wyckoff", "west orange", "paterson", "clifton", "passaic", "teaneck", "ridgefield",
    # Connecticut markers & towns
    "connecticut", ", ct", " ct ", " ct,", "stamford", "greenwich, ct", "greenwich ct",
    "norwalk", "new haven", "bridgeport", "darien", "westport",
    # Westchester, Hudson Valley & Upstate NY
    "new rochelle", "white plains", "yonkers", "port chester", "tarrytown", "nyack",
    "scarsdale", "mount vernon", "peekskill", "ossining", "mamaroneck", "rye, ny", "rye ny",
    "bethel woods", "hudson valley", "woodbury", "poughkeepsie", "beacon, ny", "sleepy hollow",
    # Long Island (Nassau / Suffolk)
    "long island", "nassau", "suffolk", "huntington", "garden city", "hempstead",
    "patchogue", "babylon", "montauk", "hamptons", "riverhead", "westbury, ny",
)

CITY_RULES = [
    ("bronx", (
        "yankee stadium", "bronx zoo", "new york botanical garden", "nybg",
        "wave hill", "woodlawn", "bronx brewery",
        "lehman center for the performing arts", "lehman center", "lehman college",
        "clinton hall bronx", "the bronx", "south bronx", "riverdale", "concourse",
        "fordham", "pelham", "mott haven", "city island", "bronx",
    )),
    ("staten_island", (
        "snug harbor", "st. george theatre", "richmond county bank",
        "conference house",
        "staten island", "st. george", "tompkinsville", "new brighton",
    )),
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
        "xanadu roller arts", "xanadu",
        "eastville comedy club", "eastville comedy",
        "montague diner", "sweet catch bk", "vacations bar", "conor's goat", "conor’s goat",
        "keg & lantern", "brooklyn brewery", "other half brewing", "the wheelhouse",
        "vineapple café", "vineapple cafe", "gowanus gardens", "fancyfree", "nook",
        "superior ingredients", "bossa nova civic club", "bossa nova", "jupiter disco",
        "salsa salsa dance", "salsa salsa",
        "the keep", "young ethel", "box house hotel", "the box house", "transit museum", "java street", "brooklyn swings",
        "vanderbilt open streets", "vanderbilt ave open streets", "abolitionist place", "abolitionist place park", "domino park",
        "mccarren parkhouse", "flop house", "flop house comedy", "liz's book bar", "lizs book bar", "threes brewing",
        "silo brooklyn", "silo", "avant gardner", "brooklyn mirage", "the brooklyn mirage", "brooklyn made", "spectacle theater",
        "h0l0", "paragon", "honey's", "honeys", "gabriela", "mood ring", "prospect park alliance", "brooklyn bridge park",
        "brooklyn trivia", "4th ave", "prospect park board", "jalsa",
        "brooklyn", "bklyn", "williamsburg", "bushwick", "greenpoint", "dumbo",
        "bed-stuy", "bedford-stuyvesant", "crown heights", "prospect heights",
        "park slope", "gowanus", "red hook", "flatbush", "bay ridge",
        "fort greene", "clinton hill", "cobble hill", "carroll gardens",
        "boerum hill", "prospect park", "sunset park", "coney island", "downtown brooklyn",
    )),
    ("queens", (
        "knockdown center", "tv eye", "trans-pecos", "nowadays", "basement ny", "basement",
        "forest hills stadium", "forest hills", "citi field", "flushing meadows",
        "moma ps1", "museum of the moving image", "socrates sculpture",
        "kaufman astoria", "terrasa 7", "queens public library", "qpl",
        "q.e.d.", "qed astoria", "qed",
        "the last word", "last word", "astoria swing",
        "the gaf astoria", "the gaf", "small change", "the ditty",
        "judy & punch", "judy and punch", "mosaic", "31st avenue open street", "corner bistro east", "on the 7",
        "mom's astoria", "mom’s astoria", "oliver's astoria", "oliver’s astoria",
        "the bier & cheese collective", "bar dalia", "singlecut beersmiths", "singlecut",
        "sanger hall", "the skillman", "sunswick astoria",
        "hunters point south park", "hunters point waterfront", "hunters point",
        "astoria trivia", "queens trivia",
        "queens", "astoria", "long island city", "lic", "flushing",
        "ridgewood", "sunnyside", "jackson heights", "woodside",
        "bayside", "jamaica, ny", "rockaway", "far rockaway",
    )),
    ("manhattan", (
        "bowery ballroom", "mercury lounge", "webster hall", "terminal 5",
        "irving plaza", "racket nyc", "racket", "le poisson rouge", "lpr",
        "blue note", "caveat", "apollo theater", "apollo",
        "madison square garden", "msg", "radio city", "beacon theatre",
        "carnegie hall", "lincoln center", "david geffen hall", "alice tully hall", "jazz at lincoln center",
        "the slipper room", "slipper room", "bibliotheque", "the shed", "hudson yards",
        "metrograph", "roxy cinema", "angelika", "le bain", "skip the small talk",
        "village vanguard", "dizzy's",
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
        "os nyc", "sobs", "s.o.b.", "sob's", "s.o.b.'s",
        "cafe wha?", "cafe wha", "pubkey", "houston hall", "bleecker street bar",
        "berlin", "night club 101", "culture club", "the culture club",
        "new world stages", "lena horne theatre", "lena horne",
        "chelsea bell", "the chelsea bell",
        "overlook", "american whiskey", "dolly's hell's kitchen", "dolly’s hell’s kitchen",
        "the broadway tavern", "t-squared social", "the hamilton", "faces & names",
        "talea beer co. — bryant park", "talea beer co.", "talea bryant park",
        "draught 55", "bareburger — hell’s kitchen", "bareburger hell's kitchen",
        "dutch fred's", "dutch fred’s", "the district", "due west", "motel no tell", "the high note",
        "reilly's plates & pours", "reilly’s plates & pours", "rocco's sports&rec", "rocco’s sports&rec",
        "ace bar", "milk & hops", "the dakota bar", "lion's head tavern", "lion’s head tavern",
        "the vale public house", "bardough", "the gaf east", "mom's midtown", "mom’s midtown",
        "lexington publick", "the factory 380", "valhalla bar", "the alvin public house",
        "drop off service", "the westbury", "the long hall", "bubby's", "bubby’s",
        "maiden lane", "cooper's craft", "cooper’s craft", "saluggi's east", "saluggi’s east",
        "triona's", "triona’s", "the mayfly", "mad dog & beans", "mama's bar", "mama’s bar",
        "mess hall – harlem", "mess hall harlem", "phil hughes", "blondie's sports", "blondie’s sports",
        "gramercy ale house", "e's bar", "e’s bar", "captain's bar", "captain’s bar",
        "phoenix bar", "the hunterian", "the five lamps", "the hairy lemon", "ryan maguire's", "ryan maguire’s",
        "the winslow", "scrappleland", "rose's r&r bar", "roses r&r bar", "sadie's ward", "sadie’s ward",
        "lily's", "lily’s", "ella's cafe", "ella’s cafe", "farm.one",
        "broadway", "off-broadway", "theater district", "theatre district",
        "gonzalez y gonzalez", "swing 46", "the back room", "back room",
        "mona's", "monas", "pieces bar", "the stonewall inn", "stonewall inn", "stonewall",
        "trivia a.d.", "trivia ad", "barcade",
        "somewhere nowhere", "the dl", "harbor nyc", "harbor new york", "230 fifth", "slate nyc", "slate ny", "nebula",
        "taj lounge", "taj ii", "club cache", "cache", "iguana nyc", "iguana", "cucala dance", "cucala",
        "ysbd", "you should be dancing", "frim fram", "danznik", "midtown swings", "hungarian house", "estonian house",
        "good shepherd", "kilowatt", "mehanata", "pangea", "connolly's", "connollys", "connolly",
        "ripley-grier", "prince george ballroom", "sara d roosevelt", "harlem swing dance", "harlem swing",
        "blues dance new york", "this week in swing nyc", "this week in swing",
        "washington square park", "garibaldi plaza", "hudson river park", "pier 45", "pier 76", "sunset salsa",
        "bella abzug park", "bella abzug", "pa' la calle", "pa la calle", "bryant park dance", "bryant park",
        "brookfield place", "port authority", "penn station", "gw bridge", "george washington bridge",
        "the hugh", "pearl studios", "adelante studios", "adelante", "nomad",
        "soho", "tribeca", "noho", "nolita", "chinatown", "lower east side", "les",
        "east village", "west village", "greenwich village", "chelsea",
        "meatpacking", "gramercy", "flatiron", "midtown", "times square",
        "hell's kitchen", "upper west side", "uws", "upper east side", "ues",
        "harlem", "morningside heights", "washington heights", "inwood",
        "battery park", "financial district", "fidi", "governors island",
        "columbus circle", "lincoln square", "meatpacking district",
        "manhattan", "new york, ny", "new york city", "new york", "nyc",
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

SUBAREAS_BY_CITY = {
    "manhattan": [
        ("les_ev", "East Village & LES", "🎸"),
        ("village_soho", "Greenwich Village & SoHo", "🍸"),
        ("midtown_chelsea", "Midtown & Chelsea", "🎭"),
        ("uws_lincoln", "Upper West & Lincoln Sq", "🌳"),
        ("ues_museums", "Upper East & Museums", "🏛️"),
        ("harlem_uptown", "Harlem & Uptown", "🎷"),
        ("fidi_tribeca", "FiDi & Tribeca", "⛵"),
        ("manhattan_other", "Other Manhattan", "📍"),
    ],
    "brooklyn": [
        ("williamsburg_gp", "Williamsburg & Greenpoint", "🎸"),
        ("bushwick_ew", "Bushwick & E. Williamsburg", "🎨"),
        ("dumbo_downtown", "DUMBO & Downtown BK", "🌳"),
        ("park_slope_gowanus", "Park Slope & Gowanus", "☕"),
        ("bedstuy_crown", "Bed-Stuy & Crown Heights", "🎺"),
        ("south_bk", "Coney Island & Bay Ridge", "🌊"),
        ("brooklyn_other", "Other Brooklyn", "📍"),
    ],
    "queens": [
        ("astoria_lic", "Astoria & Long Island City", "🍺"),
        ("flushing_ridgewood", "Flushing & Ridgewood", "🍜"),
        ("queens_other", "Other Queens", "📍"),
    ],
    "bronx": [
        ("south_bronx", "South Bronx & Concourse", "🎺"),
        ("bronx_other", "Other Bronx", "📍"),
    ],
    "staten_island": [
        ("staten_island_all", "Staten Island", "🚢"),
    ],
    "other": [
        ("tristate_other", "Tri-State Area", "🌲"),
    ]
}


def resolve_subarea(city, event, geo=None):
    if not geo:
        geo = resolve_event_geo(event)
    vn = (event.get("venue") or "").lower()
    src = (event.get("_source_venue") or "").lower()
    title = (event.get("title") or event.get("name") or "").lower()
    loc = (event.get("location") or event.get("address") or "").lower()
    neigh = (geo.get("neighborhood") or "").lower() if geo else ""
    blob = f"{vn} {src} {title} {loc} {neigh}"

    if city == "manhattan":
        if any(k in blob for k in ["east village", "lower east side", "les", "bowery", "mercury lounge", "rockwood", "pianos", "drom", "nublu", "berlin", "webster hall", "st. marks"]):
            return ("East Village & LES", "les_ev")
        if any(k in blob for k in ["greenwich village", "west village", "soho", "noho", "nolita", "comedy cellar", "le poisson rouge", "lpr", "village vanguard", "blue note", "cafe wha", "pubkey", "houston hall", "bleecker", "the bitter end", "duane park", "angelika"]):
            return ("Greenwich Village & SoHo", "village_soho")
        if any(k in blob for k in ["midtown", "chelsea", "hell's kitchen", "times square", "broadway", "hudson yards", "the shed", "high line", "madison square garden", "msg", "radio city", "carnegie hall", "sony hall", "town hall", "terminal 5", "irving plaza", "bryant park", "caveat", "asylum", "magnet", "cutting room"]):
            return ("Midtown & Chelsea", "midtown_chelsea")
        if any(k in blob for k in ["upper west side", "uws", "lincoln center", "lincoln square", "columbus circle", "david geffen", "alice tully", "merkin", "symphony space", "central park", "summerstage", "beacon theatre", "american folk art", "library for the performing arts"]):
            return ("Upper West & Lincoln Sq", "uws_lincoln")
        if any(k in blob for k in ["upper east side", "ues", "metropolitan museum", "the met", "guggenheim", "comic strip", "hungarian house", "frick", "cooper hewitt", "92ny", "92nd street y"]):
            return ("Upper East & Museums", "ues_museums")
        if any(k in blob for k in ["harlem", "apollo", "washington heights", "inwood", "united palace", "morningside", "columbia university", "smoke jazz"]):
            return ("Harlem & Uptown", "harlem_uptown")
        if any(k in blob for k in ["fidi", "financial district", "tribeca", "battery park", "brookfield", "pier 17", "governors island", "roxy cinema"]):
            return ("FiDi & Tribeca", "fidi_tribeca")
        return ("Other Manhattan", "manhattan_other")

    elif city == "brooklyn":
        if any(k in blob for k in ["williamsburg", "greenpoint", "brooklyn steel", "brooklyn bowl", "music hall of williamsburg", "baby's all right", "warsaw", "pete's candy store", "skinny dennis", "union pool", "nitehawk", "flop house", "national sawdust"]):
            return ("Williamsburg & Greenpoint", "williamsburg_gp")
        if any(k in blob for k in ["bushwick", "east williamsburg", "elsewhere", "avant gardner", "brooklyn mirage", "house of yes", "market hotel", "sultan room", "brooklyn monarch", "the meadows", "tv eye", "h0l0"]):
            return ("Bushwick & E. Williamsburg", "bushwick_ew")
        if any(k in blob for k in ["dumbo", "downtown brooklyn", "fort greene", "brooklyn navy yard", "brooklyn academy of music", "bam", "st. ann's", "transit museum", "barclays center"]):
            return ("DUMBO & Downtown BK", "dumbo_downtown")
        if any(k in blob for k in ["park slope", "gowanus", "prospect heights", "the bell house", "littlefield", "union hall", "public records", "brooklyn museum", "prospect park", "barbes"]):
            return ("Park Slope & Gowanus", "park_slope_gowanus")
        if any(k in blob for k in ["bed-stuy", "bedstuy", "crown heights", "flatbush", "kings theatre", "c'mon everybody"]):
            return ("Bed-Stuy & Crown Heights", "bedstuy_crown")
        if any(k in blob for k in ["coney island", "bay ridge", "sunset park", "industry city", "ford amphitheater"]):
            return ("Coney Island & Bay Ridge", "south_bk")
        return ("Other Brooklyn", "brooklyn_other")

    elif city == "queens":
        if any(k in blob for k in ["astoria", "lic", "long island city", "knockdown center", "q.e.d.", "qed", "moma ps1", "museum of the moving image", "socrates"]):
            return ("Astoria & Long Island City", "astoria_lic")
        if any(k in blob for k in ["flushing", "ridgewood", "forest hills", "citi field"]):
            return ("Flushing & Ridgewood", "flushing_ridgewood")
        return ("Other Queens", "queens_other")

    elif city == "bronx":
        if any(k in blob for k in ["south bronx", "concourse", "yankee stadium"]):
            return ("South Bronx & Concourse", "south_bronx")
        return ("Other Bronx", "bronx_other")

    elif city == "staten_island":
        return ("Staten Island", "staten_island_all")

    return ("Tri-State Area", "tristate_other")


def _event_stable_id(e):
    title = (e.get("name") or "").strip().lower()
    venue = (e.get("venue") or e.get("_source_venue") or "").strip().lower()
    date_str = (e.get("date") or "")[:10]
    raw = f"{venue}|{title}|{date_str}"
    return "ev_" + hashlib.md5(raw.encode("utf-8")).hexdigest()[:12]


def _is_tristate(hay):
    h = f" {hay.lower()} "
    for n in TRISTATE_NEEDLES:
        if n in h:
            return True
    return False


def _city_from_zip(hay):
    m = re.search(r"\b(10[0-2]\d{2}|103\d{2}|104\d{2}|112\d{2}|11[1346]\d{2})\b", hay)
    if not m:
        return None
    zip_code = int(m.group(1))
    if 10001 <= zip_code <= 10282:
        return "manhattan"
    if 10301 <= zip_code <= 10314:
        return "staten_island"
    if 10451 <= zip_code <= 10475:
        return "bronx"
    if 11201 <= zip_code <= 11256:
        return "brooklyn"
    if 11004 <= zip_code <= 11697:
        return "queens"
    return None


def _event_city(venue, source, geo=None):
    v = (venue or "").strip().lower()
    hay = f"{v} {(source or '').strip().lower()}"
    if geo:
        hay = f"{hay} {(geo.get('neighborhood') or '').lower()} {(geo.get('address') or '').lower()}"
    # 1. Definitively outside NYC
    if _is_tristate(hay):
        return "other"
    # 2. Match standard NYC Postal Codes
    zc = _city_from_zip(hay)
    if zc:
        return zc
    # 3. Match borough needle rules
    for city, needles in CITY_RULES:
        for n in needles:
            if len(n) <= 4:
                if re.search(r"\b" + re.escape(n) + r"\b", hay):
                    return city
            elif n in hay:
                return city
    return "other"


def _maps_link(venue, city):
    if not venue:
        return ""
    if city == "other":
        return f"https://www.google.com/maps/search/?api=1&query={quote(venue)}"
    label = CITY_LABELS.get(city)
    v_lower = venue.lower()
    # If the venue already contains address components or borough names, do not append redundant labels
    if not label or f", {label.lower()}" in v_lower or f"({label.lower()})" in v_lower or ", ny" in v_lower or " new york" in v_lower:
        return f"https://www.google.com/maps/search/?api=1&query={quote(venue)}"
    return f"https://www.google.com/maps/search/?api=1&query={quote(f'{venue}, {label}, NY')}"


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
        "greenmarket", "union square greenmarket", "garibaldi plaza", "sunset salsa",
        "pa' la calle", "pa la calle", "open streets", "abolitionist place",
        "hunters point waterfront", "domino park waterfront"
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
    if not venue:
        loc = "New York, NY"
    elif city == "other":
        loc = venue
    else:
        label = CITY_LABELS.get(city)
        v_lower = venue.lower()
        if not label or f", {label.lower()}" in v_lower or f"({label.lower()})" in v_lower or ", ny" in v_lower or " new york" in v_lower:
            loc = venue
        else:
            loc = f"{venue}, {label}, NY"
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


GENERIC_HEADS = {
    "trivia", "story hour", "open mic", "board games", "run club", "farmers market",
    "salsa", "bachata", "yoga", "live music", "comedy night", "book club",
    "happy hour", "karaoke", "jazz night", "reunion", "tour", "tours", "market"
}

COMMERCIAL_VENUES = {
    "madison square garden", "msg", "barclays center", "barclays", "radio city", "radio city music hall",
    "beacon theatre", "carnegie hall", "lincoln center", "bowery ballroom", "mercury lounge", "webster hall",
    "terminal 5", "irving plaza", "racket nyc", "racket", "brooklyn steel", "music hall of williamsburg",
    "warsaw", "kings theatre", "forest hills stadium", "yankee stadium", "citi field", "le poisson rouge",
    "lpr", "blue note", "sony hall", "town hall", "the town hall", "city winery", "apollo theater",
    "apollo", "symphony space", "comedy cellar", "gramercy theatre", "somewhere nowhere",
    "superior ingredients", "house of yes", "knockdown center"
}

EXCLUDE_VENUES_OR_SOURCES = {
    "museum", "library", "bookstore", "strand", "greenmarket", "farmers market",
    "board games", "trivia", "run club", "hiking", "volunteer", "central park",
    "church", "cathedral", "parks", "meetup"
}

GENERIC_DESCRIPTOR_PREFIXES = {
    "recital", "concert", "workshop", "screening", "lecture", "class",
    "showcase", "exhibition", "panel", "presentation", "meeting",
    "discussion", "reception", "webinar", "seminar", "film", "movie",
    "book launch", "reading"
}


def _normalize_title_head(title, venue=None):
    t = (title or "").lower().strip()

    # 1. Strip venue name from title if title starts with venue
    if venue:
        v_clean = re.sub(r"[^a-z0-9]+", " ", venue.lower()).strip()
        v_core = re.sub(r"^the\s+", "", v_clean).strip()
        t_clean = re.sub(r"[^a-z0-9]+", " ", t).strip()
        for v_cand in [v_clean, v_core]:
            if v_cand and len(v_cand) >= 4 and t_clean.startswith(v_cand):
                t = t_clean[len(v_cand):].strip()
                break

    # 2. Strip leading generic words
    t = re.sub(r"^(?:live|traditional|weekly|annual)\s+", "", t, flags=re.I)

    # 3. Strip parentheses / brackets with openers, support, guest, tour, age limits
    t = re.sub(r"\s*[\(\[][^\)\]]*(?:touring|18\+|21\+|sold out|ages|rescheduled|presale|preseason|preview|week\s*\d+|opens|opener|support|guest|special guest|featuring)[^\)\]]*[\)\]]", "", t, flags=re.I)

    # 4. Standard prefixes & suffixes
    t = re.sub(r"^(?:broadway in nyc|presents|live nation presents|bowery presents):\s*", "", t)
    t = re.sub(r"^(?:nba\s+|mlb\s+|nhl\s+|nfl\s+|wnba\s+)?(?:preseason|rescheduled|postponed):\s*", "", t)
    t = re.sub(r"\s+at\s+(?:the\s+)?[a-z0-9\x27\s\.\&\-]+$", "", t)
    t = re.sub(r"\s*-\s*202\d\s+tour.*$", "", t)
    t = re.sub(r"\s*-\s*tour.*$", "", t)
    t = re.sub(r"\s*-\s*(?:nyc|new york)(\b.*)?$", "", t)

    # If title starts with a generic descriptor prefix like "Recital:", strip it
    for p in GENERIC_DESCRIPTOR_PREFIXES:
        if t.startswith(p + ":") or t.startswith(p + " -"):
            t = t[len(p) + 1:].strip()
            break

    GENERIC_CATEGORY_SUFFIXES = (
        "workshop", "class", "clinic", "tour", "screening", "recital",
        "lecture", "discussion", "series", "market", "night", "trivia", "brunch", "show"
    )

    for sep in [":", " @ ", " @", " with ", " feat. ", " feat ", " ft. ", " ft ", " - ", " – ", " — ", " “", " \"", "”", "“", "\""]:
        if sep in t:
            parts = t.split(sep, 1)
            left = parts[0].strip()
            if any(left.endswith(suff) for suff in GENERIC_CATEGORY_SUFFIXES):
                if len(parts[1].strip()) >= 3:
                    t = parts[1].strip()
                    continue
            if len(left) >= 3 and left not in GENERIC_DESCRIPTOR_PREFIXES and not any(gen in left for gen in ["an evening", "a night", "special"]):
                t = left
                break
    if "," in t:
        parts = t.split(",", 1)
        if len(parts[0].strip()) >= 3:
            t = parts[0].strip()

    t = re.sub(r"^(?:live|traditional|weekly|annual)\s+", "", t, flags=re.I)
    t = re.sub(r"\bmusic\s+", "", t, flags=re.I)
    t = re.sub(r"[^a-z0-9]+", " ", t).strip()
    return t


def _clean_ticket_query(title):
    if not title:
        return ""
    q = title
    q = re.sub(r"^(?:broadway in nyc|presents|live nation presents|bowery presents):\s*", "", q, flags=re.IGNORECASE)
    q = re.sub(r"^(?:nba\s+|mlb\s+|nhl\s+|nfl\s+|wnba\s+)?(?:preseason|rescheduled|postponed):\s*", "", q, flags=re.IGNORECASE)
    q = re.sub(r"\s*[\(\[](?:18\+|21\+|all ages|sold out|matinee|late show|early show|touring|preseason)[^\)\]]*[\)\]]", "", q, flags=re.IGNORECASE)
    if ":" in q:
        head, _ = q.split(":", 1)
        if len(head.strip()) >= 3 and not any(gen in head.lower() for gen in ["tour", "special", "an evening", "night", "live"]):
            q = head.strip()
    for q_sep in [" “", " \"", " - ", " – ", " — "]:
        if q_sep in q:
            head, _ = q.split(q_sep, 1)
            if len(head.strip()) >= 4:
                q = head.strip()
                break
    q = re.sub(r"\s*-\s*New York\b.*", "", q, flags=re.IGNORECASE)
    q = re.sub(r"[\"“”]", "", q)
    q = re.sub(r"\s+", " ", q).strip()
    return q


def _is_commercial_ticketed(e):
    p = (e.get("price") or "").lower()
    if "free" in p or p in ("$0", "0"):
        return False
    source = (e.get("_source_venue") or "").lower()
    venue = (e.get("venue") or "").lower()
    name = (e.get("name") or "").lower()
    cat = (e.get("category") or "").lower()
    if any(ex in source or ex in venue for ex in EXCLUDE_VENUES_OR_SOURCES):
        return False
    if "museum tour" in name or "walking tour" in name or "historical tour" in name:
        return False
    if any(s in source for s in ["ticketmaster", "seatgeek", "donyc"]):
        return True
    if any(cv in venue or cv in source for cv in COMMERCIAL_VENUES):
        return True
    if cat in ("music", "sports", "comedy", "theater") and e.get("price"):
        return True
    return False


def _build_compare_links(e, raw_title):
    if not _is_commercial_ticketed(e):
        return ""
    q = _clean_ticket_query(raw_title)
    if not q or len(q) < 3:
        return ""
    encoded_q = quote_plus(q)
    gt_url = f"https://gametime.co/search?q={encoded_q}"
    sh_url = f"https://www.stubhub.com/search?q={encoded_q}"
    label = "compare prices" if e.get("price") else "tickets"
    return f'<span class="compare-tickets">{label}: <a href="{escape(gt_url)}" target="_blank" rel="noopener">Gametime</a> · <a href="{escape(sh_url)}" target="_blank" rel="noopener">StubHub</a></span>'


def _source_priority(s):
    s = (s or "").lower()
    if any(agg in s for agg in ("ticketmaster", "seatgeek", "eventbrite")):
        return 1
    if any(agg in s for agg in ("donyc", "the skint", "dice.fm", "resident advisor", "nyc parks", "meetup", "lottery", "lotteries")):
        return 5
    return 10


def _clean_event_url(u):
    if not u or not isinstance(u, str):
        return ""
    u = re.sub(r"[?#].*$", "", u).strip().rstrip("/")
    generic = {
        "https://donyc.com",
        "https://theskint.com",
        "https://www.nycgovparks.org",
        "https://www.eventbrite.com",
        "https://boweryballroom.com/events",
        "https://sobs.com/calendar",
        "https://facebook.com",
        "https://instagram.com",
    }
    if u in generic or len(u.split("/")) <= 3:
        return ""
    return u


def _ticket_source_name(url):
    if not url:
        return "Official Tickets"
    low = url.lower()
    if "ticketmaster.com" in low:
        return "Ticketmaster"
    if "livenation.com" in low:
        return "Live Nation"
    if "dice.fm" in low or "kyd.to" in low:
        return "Dice.fm"
    if "seetickets.us" in low or "seetickets" in low:
        return "SeeTickets"
    if "eventbrite.com" in low:
        return "Eventbrite"
    if "ticketweb.com" in low:
        return "Ticketweb"
    if "axs.com" in low:
        return "AXS"
    if "ovationtix.com" in low:
        return "OvationTix"
    if "ra.co" in low or "residentadvisor" in low:
        return "Resident Advisor"
    if "etix.com" in low:
        return "Etix"
    if "tixr.com" in low:
        return "Tixr"
    if "telecharge.com" in low:
        return "Telecharge"
    if "seatgeek.com" in low:
        return "SeatGeek"
    return "Official Tickets"


def _merge_duplicates(events):
    """Collapse events sharing a normalized name or head title within the same day bucket.

    Preserves the best physical venue, merges prices across primary and alt sources,
    and attaches alt sources so users can compare providers. Preserves distinct
    showtimes from the same primary source (e.g. 7:00 PM and 9:30 PM performances),
    while merging cross-source postings of the same show.
    """
    seen_exact = {}
    seen_head = {}
    seen_url = {}
    out = []
    generic_sources = {
        "ticketmaster", "seatgeek", "donyc citywide", "the skint nyc",
        "ticketmaster nyc", "seatgeek nyc", "dice.fm nyc", "resident advisor nyc",
        "nyc parks department", "meetup nyc", "nyc broadway lotteries", "luckyseat nyc broadway lotteries"
    }

    def _is_different_show(e1, e2):
        t1 = e1.get("_time")
        t2 = e2.get("_time")
        if not t1 and e1.get("date"):
            try:
                t1 = datetime.fromisoformat(str(e1["date"]).replace("Z", "+00:00"))
            except Exception:
                pass
        if not t2 and e2.get("date"):
            try:
                t2 = datetime.fromisoformat(str(e2["date"]).replace("Z", "+00:00"))
            except Exception:
                pass
        if not t1 or not t2:
            return False
        if t1.tzinfo is None:
            t1 = t1.replace(tzinfo=EASTERN)
        else:
            t1 = t1.astimezone(EASTERN)
        if t2.tzinfo is None:
            t2 = t2.replace(tzinfo=EASTERN)
        else:
            t2 = t2.astimezone(EASTERN)
        if (t1.hour == 0 and t1.minute == 0) or (t2.hour == 0 and t2.minute == 0):
            return False
        diff_mins = abs((t1 - t2).total_seconds()) / 60.0
        s1 = (e1.get("_source_venue") or e1.get("source") or "").lower()
        s2 = (e2.get("_source_venue") or e2.get("source") or "").lower()
        if s1 and s1 == s2 and diff_mins >= 45:
            return True
        if s1 != s2 and diff_mins <= 90:
            return False
        if diff_mins > 90:
            return True
        return False

    def _venue_match(v1, v2, e1, e2):
        if not v1 or not v2:
            return True
        v1_low = v1.lower()
        v2_low = v2.lower()
        if v1_low in generic_sources or v2_low in generic_sources:
            return True
        if v1_low == v2_low:
            return True
        generic_vwords = {
            "the", "at", "in", "of", "and", "new", "york", "nyc", "manhattan", "brooklyn", "queens", "bronx",
            "theatre", "theater", "tavern", "pub", "bar", "lounge", "brewery",
            "brewing", "cafe", "café", "center", "hall", "club", "studio", "house", "room"
        }
        w1 = {re.sub(r"s$", "", w) for w in re.findall(r"\w+", v1_low)} - generic_vwords
        w2 = {re.sub(r"s$", "", w) for w in re.findall(r"\w+", v2_low)} - generic_vwords
        if w1 and w2 and (w1 & w2):
            return True
        if e1 and e2:
            g1 = resolve_event_geo(e1)
            g2 = resolve_event_geo(e2)
            if g1 and g2 and g1.get("venue") and g1.get("venue") == g2.get("venue"):
                return True
        return False

    for e in events:
        # Normalize ticket_url
        t_url = e.get("ticket_url")
        if t_url and t_url != e.get("url"):
            src_label = _ticket_source_name(t_url)
            e.setdefault("_alt_sources", [])
            if not any(a.get("url") == t_url for a in e["_alt_sources"]):
                e["_alt_sources"].append({"venue": src_label, "url": t_url, "price": e.get("price")})

        raw_name = e.get("name") or ""
        full = re.sub(r"[^a-z0-9]+", " ", raw_name.lower()).strip()
        venue_str = e.get("venue") or ""
        head = _normalize_title_head(raw_name, venue=venue_str)
        venue = venue_str.lower()
        curl = _clean_event_url(e.get("url"))

        match = None
        # 0. Canonical specific URL match check
        if curl and curl in seen_url:
            for cand in seen_url[curl]:
                if not _is_different_show(e, cand):
                    match = cand
                    break

        # 1. Exact match check
        if not match and full and len(full) >= 4 and full in seen_exact:
            for cand in seen_exact[full]:
                if not _is_different_show(e, cand):
                    match = cand
                    break

        # 2. Normalized head match check
        if not match and head and len(head) >= 4 and head not in GENERIC_HEADS and head in seen_head:
            for cand in seen_head[head]:
                c_venue = (cand.get("venue") or "").lower()
                if _venue_match(venue, c_venue, e, cand):
                    if not _is_different_show(e, cand):
                        match = cand
                        break

        # 3. Same physical venue title prefix/containment match
        if not match and head and len(head) >= 4 and head not in GENERIC_HEADS:
            for cand in out:
                c_venue = (cand.get("venue") or "").lower()
                if _venue_match(venue, c_venue, e, cand) and not _is_different_show(e, cand):
                    cand_head = _normalize_title_head(cand.get("name") or "", venue=cand.get("venue"))
                    if cand_head and cand_head not in GENERIC_HEADS:
                        if (cand_head.startswith(head) or head.startswith(cand_head)) and min(len(head), len(cand_head)) >= 6:
                            match = cand
                            break

        if match:
            match.setdefault("_alt_sources", [])
            src_url = e.get("url")
            src_name = e.get("_source_venue") or e.get("source") or e.get("venue") or "source"
            if src_url and not any(a.get("url") == src_url for a in match["_alt_sources"]) and src_url != match.get("url"):
                match["_alt_sources"].append({"venue": src_name, "source": src_name, "url": src_url, "price": e.get("price")})

            cand_t_url = e.get("ticket_url")
            if cand_t_url and cand_t_url != match.get("url"):
                t_label = _ticket_source_name(cand_t_url)
                if not any(a.get("url") == cand_t_url for a in match["_alt_sources"]):
                    match["_alt_sources"].append({"venue": t_label, "source": t_label, "url": cand_t_url, "price": e.get("price")})

            # Upgrade primary source if newly arrived event has higher priority
            cur_prio = _source_priority(match.get("_source_venue") or match.get("source"))
            new_prio = _source_priority(e.get("_source_venue") or e.get("source"))
            if new_prio > cur_prio:
                old_url = match.get("url")
                old_src = match.get("_source_venue") or match.get("source")
                if old_url and not any(a.get("url") == old_url for a in match["_alt_sources"]):
                    match["_alt_sources"].append({"venue": old_src, "source": old_src, "url": old_url, "price": match.get("price")})
                match["url"] = e.get("url")
                match["name"] = e.get("name")
                match["venue"] = e.get("venue")
                match["_source_venue"] = e.get("_source_venue") or e.get("source")
                if e.get("_time") and (e["_time"].hour != 0 or e["_time"].minute != 0):
                    match["_time"] = e["_time"]

            # Presenter tag resolution
            cand_src = (match.get("_source_venue") or "").strip()
            e_src = (e.get("_source_venue") or "").strip()
            v_name = (match.get("venue") or "").strip().lower()
            if e_src and e_src.lower() not in generic_sources and e_src.lower() not in v_name:
                match["_presenter"] = e_src
            elif cand_src and cand_src.lower() not in generic_sources and cand_src.lower() not in v_name:
                match["_presenter"] = cand_src

            if not match.get("price") and e.get("price"):
                match["price"] = e["price"]
            if not match.get("lat") and e.get("lat"):
                match["lat"] = e["lat"]
                match["lng"] = e.get("lng")
            if (not match.get("category") or match.get("category") in ("other", "community")) and e.get("category") and e.get("category") not in ("other", "community"):
                match["category"] = e["category"]
            if not match.get("description") and e.get("description"):
                match["description"] = e["description"]
        else:
            if curl:
                seen_url.setdefault(curl, []).append(e)
            if full and len(full) >= 4:
                seen_exact.setdefault(full, []).append(e)
            if head and len(head) >= 4 and head not in GENERIC_HEADS:
                seen_head.setdefault(head, []).append(e)
            out.append(e)

    return out


def group_by_date(results):
    today = datetime.now(EASTERN).date()
    max_date = today + timedelta(days=14)
    buckets = {}
    tba = []
    ongoing = []
    for r in results:
        for e in r.get("events", []):
            if is_placeholder_or_closed_event(e.get("name")) or is_closed_show(e.get("venue")):
                continue
            entry = {"venue_url": r.get("url", ""), **e, "_source_venue": r.get("venue", "")}
            entry["venue"] = e.get("venue") or r.get("venue", "")
            existing_cat = e.get("category")
            if existing_cat == "theater":
                entry["category"] = "theater"
            else:
                entry["category"] = guess_category(e.get("name"), existing_cat or r.get("default_category") or "community", venue=entry["venue"])
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
            elif key <= max_date:
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
        geo = resolve_event_geo(e)
        geo_attrs = ""
        geo_btn = ""
        if geo:
            geo_attrs = f' data-lat="{geo["lat"]}" data-lng="{geo["lng"]}" data-venue-name="{escape(geo["venue"])}" data-neighborhood="{escape(geo["neighborhood"])}"'
            geo_btn = f' <button type="button" class="venue-map-jump" data-lat="{geo["lat"]}" data-lng="{geo["lng"]}" data-venue="{escape(geo["venue"])}" title="View {escape(geo["venue"])} on Map">📍</button>'

        city = _event_city(venue, source, geo=geo)
        sub_name, sub_slug = resolve_subarea(city, e, geo=geo)
        subarea_tag = f' <span class="subarea-tag">· {escape(sub_name)}</span>' if sub_name and not sub_name.startswith("Other ") else ""
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

        compare_html = _build_compare_links(e, raw_title)

        GENERIC_AGGREGATORS = {
            "donyc citywide", "the skint nyc", "ticketmaster nyc", "seatgeek nyc",
            "dice.fm nyc", "resident advisor nyc", "nyc parks department", "meetup nyc",
            "nyc broadway lotteries", "luckyseat nyc broadway lotteries"
        }
        presenter = e.get("_presenter") or ""
        if not presenter and source and venue and source.strip().lower() not in GENERIC_AGGREGATORS:
            s_clean = source.strip().lower()
            v_clean = venue.strip().lower()
            if s_clean not in v_clean and v_clean not in s_clean:
                presenter = source

        presenter_html = f' <span class="presenter-tag" title="Presented by {escape(presenter)}">presented by {escape(presenter)}</span>' if presenter else ""
        community_badge = ' <span class="badge-community" title="Community submitted event">👤 Community</span>' if e.get("_is_community") else ""

        if venue:
            maps_url = _maps_link(venue, city)
            venue_html = f'<a class="venue-link" href="{escape(maps_url)}" target="_blank" rel="noopener">{escape(venue)}</a>{geo_btn}{presenter_html}{community_badge}{subarea_tag}'
        elif presenter_html:
            venue_html = f'{presenter_html}{community_badge}{subarea_tag}'
        else:
            venue_html = f'{community_badge}{subarea_tag}'.strip()

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
        epoch_attr = f' data-epoch="{int(e["_time"].timestamp())}"' if e.get("_time") else ''
        extra_html = f' · {compare_html}' if compare_html else ''
        pres_attr = f' data-presenter="{escape(presenter)}"' if presenter else ''
        ev_id = _event_stable_id(e)
        return f'''<li class="event" data-cat="{escape(cat)}" data-bucket="{escape(bucket)}" data-venue="{escape(source)}"{pres_attr} data-city="{escape(city)}" data-subarea="{escape(sub_slug)}" data-subarea-name="{escape(sub_name)}" data-recur="{recur_flag}" data-free="{free_flag}" data-guestlist="{guestlist_flag}" data-event-id="{ev_id}"{epoch_attr}{geo_attrs}>
          <div class="when">{escape(format_when(e))}</div>
          <div class="what">{link}{price_tag}{guestlist_badge}{recur_badge}
            <div class="venue-tag">{cat_tag} · {venue_html}{(" · " + alt_html) if alt_html else ""}{extra_html}{cal_html}</div>
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

    today = datetime.now(EASTERN).date()
    today_iso = today.isoformat()

    def _render_day_section(heading_html, events, date_attr=""):
        by_city = {c: [] for c in city_day_order}
        for e in events:
            geo = resolve_event_geo(e)
            c = _event_city(e.get("venue"), e.get("_source_venue"), geo=geo)
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
        is_today = (date_attr == today_iso)
        day_class = "day" if is_today else "day out-of-week"
        past_banner_html = '''
          <div class="past-events-banner" id="past-events-banner" style="display: none;">
            <div class="past-banner-info">
              <span class="past-banner-badge" id="past-banner-badge">⏱️ Live Tonight</span>
              <span class="past-banner-text" id="past-banner-text"></span>
            </div>
            <div class="past-banner-actions">
              <button type="button" class="past-banner-btn" id="btn-toggle-past">Show earlier today</button>
              <button type="button" class="past-banner-btn btn-tomorrow" id="btn-banner-tomorrow" style="display: none;">See Tomorrow →</button>
            </div>
          </div>''' if is_today else ""
        return f'''
        <section class="{day_class}" data-date="{date_attr}">
          <h2>{heading_html}<span class="count">{len(events)}</span></h2>
          {past_banner_html}
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
                ("Superior Ingredients", "https://si-bk.com/", "Free RSVP Dance Series (before 11 PM)", "Williamsburg"),
                ("Bossa Nova Civic Club", "https://www.instagram.com/bossanovacivicclub/", "Free Entry Before 11:00 PM Nightly", "Bushwick Techno"),
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
        src = e.get("_source_venue", "")
        if src in venue_counts:
            venue_counts[src] += 1
        pres = e.get("_presenter", "")
        if pres and pres in venue_counts and pres != src:
            venue_counts[pres] += 1

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
        geo = resolve_event_geo(e)
        c = _event_city(e.get("venue"), e.get("_source_venue"), geo=geo)
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
  .pill-submit-btn {{
    display: inline-flex;
    align-items: center;
    gap: 4px;
    background: linear-gradient(135deg, #ffd866 0%, #f29e4c 100%);
    color: #0c0e14;
    border: none;
    border-radius: 999px;
    padding: 3px 12px;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.02em;
    cursor: pointer;
    font-family: inherit;
    box-shadow: 0 2px 8px rgba(255, 216, 102, 0.3);
    transition: transform 0.15s ease, box-shadow 0.15s ease, filter 0.15s ease;
    line-height: 1.3;
    vertical-align: middle;
  }}
  .pill-submit-btn:hover {{
    transform: translateY(-1px) scale(1.02);
    box-shadow: 0 4px 12px rgba(255, 216, 102, 0.45);
    filter: brightness(1.06);
  }}
  .pill-submit-btn:active {{
    transform: translateY(1px);
  }}

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

  /* Secondary Subarea Chips Bar */
  .subarea-chips-bar {{
    display: flex;
    align-items: center;
    gap: 6px;
    background: rgba(255, 255, 255, 0.02);
    border: 1px dashed var(--border);
    border-radius: var(--radius-md);
    padding: 6px 10px;
    overflow-x: auto;
    white-space: nowrap;
    -webkit-overflow-scrolling: touch;
    scrollbar-width: none;
    -ms-overflow-style: none;
    max-width: 100%;
  }}
  .subarea-chips-bar::-webkit-scrollbar {{
    display: none;
  }}
  .sub-chip {{
    background: rgba(255, 255, 255, 0.04);
    border: 1px solid var(--border);
    color: var(--muted);
    padding: 4px 11px;
    border-radius: 999px;
    font-size: 12px;
    font-weight: 500;
    cursor: pointer;
    font-family: inherit;
    display: inline-flex;
    align-items: center;
    gap: 5px;
    flex-shrink: 0;
    white-space: nowrap;
    transition: all 0.15s ease;
  }}
  .sub-chip:hover {{
    background: rgba(255, 255, 255, 0.08);
    border-color: rgba(255, 255, 255, 0.3);
    color: #fff;
  }}
  .sub-chip.active {{
    background: rgba(93, 155, 255, 0.16);
    border-color: var(--accent);
    color: #fff;
    font-weight: 700;
    box-shadow: 0 1px 6px rgba(0, 0, 0, 0.3);
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
  .chip-theater {{
    color: #f7d794;
    border-color: rgba(224, 175, 104, 0.4);
    background: rgba(224, 175, 104, 0.12);
  }}
  .chip-theater:hover {{
    background: rgba(224, 175, 104, 0.22);
    border-color: #e0af68;
    color: #fff;
  }}
  .chip-theater.active {{
    background: #e0af68;
    color: #1a1406;
    border-color: #e0af68;
    font-weight: 700;
    box-shadow: 0 2px 10px rgba(224, 175, 104, 0.35);
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
  .subarea-tag {{ color: var(--accent); font-weight: 500; font-size: 11px; }}
  .cat-pill {{ display: inline-flex; align-items: center; gap: 4px; padding: 2px 7px; border-radius: 5px; font-size: 11px; font-weight: 600; line-height: 1.3; border: 1px solid; }}
  .price {{ display:inline-block; margin-left: 8px; background: rgba(255,255,255,0.06); color: var(--muted); font-size: 11px; padding: 2px 7px; border-radius: 5px; font-weight: 500; }}
  .price.free {{ background: var(--green-bg); color: var(--green); border: 1px solid var(--green-border); font-weight: 700; }}
  .price.ticketed {{ background: rgba(139, 178, 255, 0.12); color: #8bb2ff; border: 1px solid rgba(139, 178, 255, 0.3); font-weight: 600; font-size: 10px; }}
  .compare-tickets {{ font-size: 11px; color: var(--muted); }}
  .compare-tickets a {{ color: var(--accent); text-decoration: none; }}
  .compare-tickets a:hover {{ text-decoration: underline; }}
  .cal-links {{ display: inline-flex; align-items: center; gap: 4px; margin-left: 4px; }}
  .cal-btn {{ background: rgba(255,255,255,0.04); border: 1px solid var(--border); color: var(--muted); padding: 2px 7px; border-radius: 5px; font-size: 10px; font-weight: 500; text-decoration: none; cursor: pointer; line-height: 1.3; display: inline-flex; align-items: center; gap: 3px; font-family: inherit; transition: all 0.15s ease; }}
  .cal-btn:hover {{ color: #fff; border-color: var(--accent); background: rgba(93,155,255,0.15); }}
  .recur {{ display:inline-block; margin-left: 8px; background: rgba(255,122,178,0.14); color: #ff7ab2; font-size: 10px; padding: 2px 6px; border-radius: 4px; letter-spacing: 0.02em; }}
  .presenter-tag {{ display: inline-block; color: #ff9e64; font-size: 11px; font-weight: 600; background: rgba(255,158,100,0.12); padding: 1px 6px; border-radius: 4px; border: 1px solid rgba(255,158,100,0.25); }}
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
  .filter-badge {{ background: var(--accent); color: #0d1117; font-size: 10px; font-weight: 700; padding: 1px 7px; border-radius: 999px; text-transform: none; letter-spacing: 0; }}
  .reset-filters-bar {{ margin-bottom: 8px; }}
  .btn-reset-filters {{
    width: 100%;
    background: rgba(224, 90, 107, 0.12);
    border: 1px solid rgba(224, 90, 107, 0.35);
    color: #ff7b72;
    font-size: 11px;
    font-weight: 600;
    padding: 6px 12px;
    border-radius: var(--radius-sm);
    cursor: pointer;
    font-family: inherit;
    transition: all 0.15s ease;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 6px;
  }}
  .btn-reset-filters:hover {{
    background: rgba(224, 90, 107, 0.22);
    border-color: #ff7b72;
    color: #ffffff;
  }}
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
  .no-events-msg {{
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
    padding: 36px 20px;
    text-align: center;
    color: var(--muted);
    margin: 8px 0 16px;
  }}
  .no-events-msg p {{
    margin: 0 0 14px;
    font-size: 14px;
    color: var(--fg);
  }}

  /* Past Events Filter Banner */
  .past-events-banner {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 10px;
    background: rgba(255, 255, 255, 0.03);
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
    padding: 8px 12px;
    margin: 8px 0 16px;
  }}
  .past-banner-info {{
    display: flex;
    align-items: center;
    gap: 10px;
    flex-wrap: wrap;
    font-size: 13px;
    color: var(--fg);
  }}
  .past-banner-badge {{
    background: rgba(93, 155, 255, 0.15);
    color: var(--accent);
    border: 1px solid rgba(93, 155, 255, 0.3);
    padding: 2px 8px;
    border-radius: 999px;
    font-size: 11px;
    font-weight: 700;
  }}
  .past-banner-badge.badge-all {{
    background: rgba(255, 255, 255, 0.08);
    color: var(--fg);
    border-color: var(--border);
  }}
  .past-banner-badge.badge-done {{
    background: rgba(242, 158, 76, 0.15);
    color: #f29e4c;
    border-color: rgba(242, 158, 76, 0.35);
  }}
  .past-banner-text strong {{
    color: #fff;
  }}
  .past-banner-actions {{
    display: flex;
    align-items: center;
    gap: 8px;
  }}
  .past-banner-btn {{
    background: rgba(255, 255, 255, 0.06);
    border: 1px solid var(--border);
    color: var(--fg);
    padding: 4px 12px;
    border-radius: 999px;
    font-size: 11px;
    font-weight: 600;
    cursor: pointer;
    font-family: inherit;
    transition: all 0.15s ease;
  }}
  .past-banner-btn:hover {{
    background: rgba(255, 255, 255, 0.12);
    border-color: var(--accent);
    color: #fff;
  }}
  .past-banner-btn.btn-tomorrow {{
    background: var(--accent);
    color: #0c0e14;
    border-color: var(--accent);
    font-weight: 700;
  }}
  .past-banner-btn.btn-tomorrow:hover {{
    box-shadow: 0 2px 8px var(--accent-glow);
  }}
  .event.past-time {{
    opacity: 0.55;
    transition: opacity 0.15s ease;
  }}
  .event.past-time:hover {{
    opacity: 0.95;
  }}
  .event.past-time .when::after {{
    content: " (earlier)";
    font-size: 10px;
    opacity: 0.7;
    font-weight: 400;
  }}

  /* View Switcher */
  .view-switch-bar {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
    padding: 6px 12px;
  }}
  .view-toggle {{
    display: inline-flex;
    align-items: center;
    background: rgba(255, 255, 255, 0.05);
    border: 1px solid var(--border);
    border-radius: 999px;
    padding: 2px;
    gap: 2px;
  }}
  .view-btn {{
    background: transparent;
    border: none;
    color: var(--muted);
    font-size: 12px;
    font-weight: 600;
    padding: 5px 14px;
    border-radius: 999px;
    cursor: pointer;
    font-family: inherit;
    display: inline-flex;
    align-items: center;
    gap: 6px;
    transition: all 0.15s ease;
  }}
  .view-btn:hover {{
    color: var(--fg);
  }}
  .view-btn.active {{
    background: var(--accent);
    color: #0c0e14;
    font-weight: 700;
    box-shadow: 0 2px 8px var(--accent-glow);
  }}
  .share-filter-btn {{
    background: transparent;
    border: 1px solid var(--border);
    color: var(--muted);
    font-size: 11px;
    font-weight: 600;
    padding: 4px 10px;
    border-radius: 999px;
    cursor: pointer;
    font-family: inherit;
    display: inline-flex;
    align-items: center;
    gap: 5px;
    transition: all 0.15s ease;
  }}
  .share-filter-btn:hover {{
    color: var(--fg);
    border-color: var(--accent);
  }}
  .share-filter-btn.copied {{
    background: rgba(35, 134, 54, 0.2);
    border-color: #238636;
    color: #3fb950;
  }}
  .map-venue-stat {{
    font-size: 12px;
    color: var(--muted);
  }}
  .map-venue-stat strong {{
    color: var(--accent);
  }}

  /* Map View Wrapper */
  .map-view-wrapper {{
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
    padding: 12px;
    display: flex;
    flex-direction: column;
    gap: 10px;
    position: relative;
  }}
  .map-header {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 8px;
    padding: 0 4px;
  }}
  .map-header-title {{
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 13px;
    color: var(--fg);
  }}
  .map-hint {{
    color: var(--muted);
    font-size: 11px;
  }}
  .map-tool-btn {{
    background: rgba(255, 255, 255, 0.05);
    border: 1px solid var(--border);
    color: var(--fg);
    border-radius: var(--radius-sm);
    padding: 3px 10px;
    font-size: 11px;
    cursor: pointer;
    font-family: inherit;
    transition: all 0.15s ease;
  }}
  .map-tool-btn:hover {{
    border-color: var(--accent);
    color: var(--accent);
  }}
  .leaflet-map {{
    width: 100%;
    height: 520px;
    border-radius: var(--radius-md);
    border: 1px solid var(--border);
    background: #0c0e14;
    z-index: 1;
  }}
  .leaflet-container.osm-dark-tiles,
  .leaflet-container.osm-dark-tiles .leaflet-tile-container {{
    background: #0c0e14 !important;
  }}
  .leaflet-container.osm-dark-tiles .leaflet-tile-pane {{
    filter: invert(100%) hue-rotate(180deg) brightness(88%) contrast(95%);
  }}
  .leaflet-control-attribution {{
    background: rgba(12, 14, 20, 0.85) !important;
    color: var(--muted) !important;
    border-radius: var(--radius-sm);
    font-size: 10px !important;
    padding: 2px 6px !important;
  }}
  .leaflet-control-attribution a {{
    color: var(--accent) !important;
    text-decoration: none !important;
  }}
  .leaflet-control-attribution a:hover {{
    text-decoration: underline !important;
  }}
  .leaflet-bar a {{
    background-color: #141824 !important;
    color: #eef1f8 !important;
    border: 1px solid var(--border) !important;
    border-bottom: 1px solid var(--border) !important;
  }}
  .leaflet-bar a:hover {{
    background-color: #1e2436 !important;
    color: var(--accent) !important;
  }}

  /* Venue Map Pin in Leaflet */
  .custom-venue-icon {{
    background: transparent !important;
    border: none !important;
  }}
  .venue-marker {{
    background: #141824;
    border: 1.5px solid var(--accent);
    color: #eef1f8;
    border-radius: 999px;
    padding: 3px 8px;
    font-size: 11px;
    font-weight: 600;
    display: inline-flex;
    align-items: center;
    gap: 5px;
    box-shadow: 0 4px 14px rgba(0,0,0,0.7), 0 0 10px rgba(93, 155, 255, 0.35);
    cursor: pointer;
    white-space: nowrap;
    transition: transform 0.15s ease, background 0.15s ease, box-shadow 0.15s ease;
    transform: translate(-50%, -50%);
    user-select: none;
  }}
  .venue-marker:hover, .venue-marker.highlighted {{
    transform: translate(-50%, -50%) scale(1.12);
    background: var(--accent);
    color: #0c0e14;
    border-color: #fff;
    box-shadow: 0 6px 20px rgba(93, 155, 255, 0.6);
    z-index: 9999 !important;
  }}
  .venue-marker .pin-count {{
    background: var(--accent);
    color: #0c0e14;
    border-radius: 999px;
    font-size: 10px;
    padding: 1px 6px;
    font-weight: 800;
    line-height: 1.2;
  }}
  .venue-marker:hover .pin-count, .venue-marker.highlighted .pin-count {{
    background: #0c0e14;
    color: #fff;
  }}
  /* Compact numbers-only mode */
  .leaflet-map.hide-pin-names .venue-marker {{
    min-width: 24px;
    height: 24px;
    padding: 0 4px;
    border-radius: 999px;
    justify-content: center;
    gap: 0;
  }}
  .leaflet-map.hide-pin-names .venue-marker .pin-name {{
    display: none !important;
  }}
  .leaflet-map.hide-pin-names .venue-marker .pin-count {{
    background: transparent;
    color: var(--accent);
    padding: 0;
    font-size: 11px;
    font-weight: 800;
  }}
  .leaflet-map.hide-pin-names .venue-marker:hover .pin-count,
  .leaflet-map.hide-pin-names .venue-marker.highlighted .pin-count {{
    color: #0c0e14;
  }}
  .venue-map-jump {{
    background: none;
    border: none;
    cursor: pointer;
    font-size: 12px;
    padding: 0 2px;
    line-height: 1;
    opacity: 0.75;
    transition: transform 0.12s ease, opacity 0.12s ease;
    display: inline-block;
    vertical-align: middle;
  }}
  .venue-map-jump:hover {{
    opacity: 1;
    transform: scale(1.3);
  }}

  /* Dark theme Leaflet Popups */
  .leaflet-popup-content-wrapper, .leaflet-popup-tip {{
    background: #151822 !important;
    color: #eef1f8 !important;
    border: 1px solid rgba(255, 255, 255, 0.15) !important;
    box-shadow: 0 16px 36px rgba(0, 0, 0, 0.85) !important;
    border-radius: 12px !important;
  }}
  .leaflet-popup-content {{
    margin: 12px 14px !important;
    line-height: 1.4 !important;
    font-family: inherit !important;
  }}
  .leaflet-container a.leaflet-popup-close-button {{
    color: var(--muted) !important;
    padding: 8px 10px !important;
  }}
  .leaflet-container a.leaflet-popup-close-button:hover {{
    color: #fff !important;
  }}
  .map-popup {{
    min-width: 220px;
    max-width: 280px;
  }}
  .popup-head {{
    display: flex;
    flex-direction: column;
    gap: 2px;
    margin-bottom: 8px;
    padding-bottom: 6px;
    border-bottom: 1px solid var(--border);
  }}
  .popup-head strong {{
    font-size: 13px;
    color: #fff;
  }}
  .popup-neighborhood {{
    font-size: 11px;
    color: var(--accent);
    font-weight: 500;
  }}
  .popup-events {{
    display: flex;
    flex-direction: column;
    gap: 6px;
    max-height: 220px;
    overflow-y: auto;
  }}
  .popup-event-item {{
    font-size: 12px;
    display: flex;
    flex-direction: column;
    gap: 2px;
    padding: 4px 6px;
    border-radius: 6px;
    background: rgba(255, 255, 255, 0.03);
  }}
  .popup-time {{
    font-size: 10px;
    color: var(--muted);
  }}
  .popup-title {{
    color: var(--fg);
    text-decoration: none;
    font-weight: 500;
  }}
  .popup-title:hover {{
    color: var(--accent);
    text-decoration: underline;
  }}
  .popup-price {{
    font-size: 10px;
    color: var(--muted);
  }}
  .popup-price.free {{
    color: var(--green);
    font-weight: 600;
  }}
  .popup-more {{
    font-size: 11px;
    color: var(--muted);
    text-align: center;
    padding: 4px 0 2px;
  }}
  .popup-foot {{
    margin-top: 8px;
    padding-top: 6px;
    border-top: 1px solid var(--border);
    text-align: right;
  }}
  .popup-dir-link {{
    font-size: 11px;
    color: var(--accent);
    text-decoration: none;
  }}
  .popup-dir-link:hover {{
    text-decoration: underline;
  }}

  /* Slide-down venue card below map */
  .map-venue-card {{
    background: rgba(255, 255, 255, 0.02);
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
    padding: 12px 14px;
  }}
  .map-venue-card-head {{
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 10px;
    margin-bottom: 8px;
    padding-bottom: 6px;
    border-bottom: 1px solid var(--border);
  }}
  .map-venue-card-head h3 {{
    margin: 0;
    font-size: 15px;
    color: #fff;
  }}
  .panel-sub {{
    margin: 2px 0 0;
    font-size: 12px;
    color: var(--muted);
  }}
  .panel-close {{
    background: none;
    border: none;
    color: var(--muted);
    font-size: 16px;
    cursor: pointer;
    padding: 2px 6px;
    line-height: 1;
  }}
  .panel-close:hover {{
    color: #fff;
  }}
  .panel-events {{
    list-style: none;
    padding: 0;
    margin: 0;
    display: flex;
    flex-direction: column;
    gap: 6px;
    max-height: 240px;
    overflow-y: auto;
  }}
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
    .subarea-chips-bar {{
      padding: 5px 8px;
      gap: 5px;
    }}
    .sub-chip {{
      padding: 3px 9px;
      font-size: 11px;
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
    .leaflet-map {{
      height: 380px;
    }}
    .map-header {{
      flex-direction: column;
      align-items: flex-start;
      gap: 6px;
    }}
    /* Mobile: Default to compact numbers-only pins to prevent clutter */
    .venue-marker {{
      min-width: 24px;
      height: 24px;
      padding: 0 4px;
      border-radius: 999px;
      justify-content: center;
      gap: 0;
    }}
    .venue-marker .pin-name {{
      display: none;
    }}
    .venue-marker .pin-count {{
      background: transparent;
      color: var(--accent);
      padding: 0;
      font-size: 11px;
      font-weight: 800;
    }}
    .venue-marker:hover .pin-count,
    .venue-marker.highlighted .pin-count {{
      color: #0c0e14;
    }}
    /* Mobile: If user toggles names on */
    .leaflet-map.show-pin-names-mobile .venue-marker {{
      min-width: auto;
      height: auto;
      padding: 3px 8px;
      border-radius: 999px;
      gap: 5px;
    }}
    .leaflet-map.show-pin-names-mobile .venue-marker .pin-name {{
      display: inline !important;
    }}
    .leaflet-map.show-pin-names-mobile .venue-marker .pin-count {{
      background: var(--accent);
      color: #0c0e14;
      padding: 1px 6px;
    }}
  }}

  /* Community Badge */
  .badge-community {{
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 2px 7px;
    border-radius: 999px;
    font-size: 10px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    background: rgba(93, 155, 255, 0.15);
    border: 1px solid rgba(93, 155, 255, 0.3);
    color: #5d9bff;
    vertical-align: middle;
  }}

  /* Submission Modal Overlay */
  .modal-overlay {{
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(6, 8, 12, 0.78);
    backdrop-filter: blur(8px);
    -webkit-backdrop-filter: blur(8px);
    z-index: 99999;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 16px;
    overflow-y: auto;
    animation: modalFadeIn 0.2s ease-out;
  }}
  @keyframes modalFadeIn {{
    from {{ opacity: 0; }}
    to {{ opacity: 1; }}
  }}
  .modal-card {{
    background: #141722;
    border: 1px solid var(--border-hover);
    border-radius: var(--radius-lg);
    box-shadow: 0 24px 64px rgba(0, 0, 0, 0.7), 0 0 0 1px rgba(255, 255, 255, 0.05);
    width: 100%;
    max-width: 580px;
    max-height: 90vh;
    overflow-y: auto;
    padding: 28px 24px;
    position: relative;
    animation: modalCardPop 0.22s cubic-bezier(0.16, 1, 0.3, 1);
  }}
  @keyframes modalCardPop {{
    from {{ transform: scale(0.95) translateY(12px); opacity: 0; }}
    to {{ transform: scale(1) translateY(0); opacity: 1; }}
  }}
  .modal-header {{
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 16px;
    margin-bottom: 16px;
    padding-bottom: 14px;
    border-bottom: 1px solid var(--border);
  }}
  .modal-tabs {{
    display: flex;
    gap: 6px;
    margin-bottom: 18px;
    background: rgba(255, 255, 255, 0.05);
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
    padding: 4px;
  }}
  .modal-tab {{
    flex: 1;
    background: transparent;
    border: none;
    color: var(--muted);
    font-size: 13px;
    font-weight: 700;
    padding: 8px 12px;
    border-radius: var(--radius-sm);
    cursor: pointer;
    font-family: inherit;
    transition: all 0.15s ease;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 6px;
  }}
  .modal-tab:hover {{
    color: #ffffff;
  }}
  .modal-tab.active {{
    background: var(--accent);
    color: #0c0e14;
    box-shadow: 0 2px 8px var(--accent-glow);
  }}
  .modal-title {{
    margin: 0;
    font-size: 20px;
    font-weight: 800;
    color: #ffffff;
    letter-spacing: -0.02em;
  }}
  .modal-sub {{
    margin: 6px 0 0;
    font-size: 13px;
    color: var(--muted);
    line-height: 1.4;
  }}
  .modal-close-btn {{
    background: rgba(255, 255, 255, 0.06);
    border: 1px solid var(--border);
    color: var(--muted);
    font-size: 16px;
    width: 32px;
    height: 32px;
    border-radius: 50%;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    transition: all 0.15s ease;
    flex-shrink: 0;
  }}
  .modal-close-btn:hover {{
    background: rgba(255, 255, 255, 0.15);
    color: #ffffff;
  }}
  .modal-form {{
    display: flex;
    flex-direction: column;
    gap: 14px;
  }}
  .form-row {{
    display: flex;
    flex-direction: column;
    gap: 6px;
  }}
  .form-grid-2 {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 12px;
  }}
  @media (max-width: 520px) {{
    .form-grid-2 {{
      grid-template-columns: 1fr;
    }}
  }}
  .form-label {{
    font-size: 12px;
    font-weight: 700;
    color: #c9d1d9;
    letter-spacing: 0.02em;
  }}
  .form-label .req {{
    color: #e05a6b;
  }}
  .form-label .hint {{
    font-weight: 400;
    color: var(--muted);
  }}
  .form-input, .form-select, .form-textarea {{
    width: 100%;
    box-sizing: border-box;
    background: rgba(255, 255, 255, 0.04);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    padding: 9px 12px;
    color: #ffffff;
    font-size: 13px;
    font-family: inherit;
    transition: border-color 0.15s ease, background 0.15s ease;
  }}
  .form-input:focus, .form-select:focus, .form-textarea:focus {{
    outline: none;
    border-color: var(--accent);
    background: rgba(93, 155, 255, 0.08);
  }}
  .form-select option {{
    background: #151822;
    color: #ffffff;
  }}
  .price-input-row {{
    display: flex;
    gap: 8px;
    align-items: center;
  }}
  .btn-pill-free {{
    background: rgba(74, 222, 128, 0.14);
    border: 1px solid rgba(74, 222, 128, 0.35);
    color: #4ade80;
    font-weight: 700;
    font-size: 12px;
    padding: 8px 12px;
    border-radius: var(--radius-sm);
    cursor: pointer;
    white-space: nowrap;
    transition: all 0.15s ease;
  }}
  .btn-pill-free:hover {{
    background: rgba(74, 222, 128, 0.25);
  }}
  .form-status {{
    padding: 10px 14px;
    border-radius: var(--radius-sm);
    font-size: 13px;
    font-weight: 600;
    line-height: 1.4;
  }}
  .form-status.success {{
    background: rgba(74, 222, 128, 0.15);
    border: 1px solid rgba(74, 222, 128, 0.4);
    color: #4ade80;
  }}
  .form-status.error {{
    background: rgba(224, 90, 107, 0.15);
    border: 1px solid rgba(224, 90, 107, 0.4);
    color: #ff7b8b;
  }}
  .form-actions {{
    display: flex;
    align-items: center;
    justify-content: flex-end;
    gap: 10px;
    margin-top: 8px;
    padding-top: 14px;
    border-top: 1px solid var(--border);
  }}
  .btn-cancel {{
    background: transparent;
    border: 1px solid var(--border);
    color: var(--muted);
    font-weight: 600;
    font-size: 13px;
    padding: 9px 16px;
    border-radius: var(--radius-sm);
    cursor: pointer;
  }}
  .btn-cancel:hover {{
    color: #ffffff;
    border-color: var(--border-hover);
  }}
  .btn-primary-submit {{
    background: linear-gradient(135deg, #5d9bff 0%, #3b82f6 100%);
    border: none;
    color: #ffffff;
    font-weight: 700;
    font-size: 13px;
    padding: 10px 20px;
    border-radius: var(--radius-sm);
    cursor: pointer;
    box-shadow: 0 4px 14px rgba(59, 130, 246, 0.35);
    transition: all 0.15s ease;
  }}
  .btn-primary-submit:hover {{
    box-shadow: 0 6px 20px rgba(59, 130, 246, 0.5);
    filter: brightness(1.08);
  }}
  .form-footer-note {{
    font-size: 11px;
    color: var(--muted);
    text-align: center;
    margin-top: 4px;
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
        <button type="button" class="pill-submit-btn" id="btn-open-submit-modal" aria-haspopup="dialog" aria-expanded="false">
          <span>＋ Add Event</span>
        </button>
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
      <div id="reset-filters-bar" class="reset-filters-bar" style="display: none;">
        <button type="button" id="btn-reset-filters" class="btn-reset-filters">↺ Reset All Filters</button>
      </div>
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
        <h3>Venue <span id="venue-filter-count" class="filter-badge" style="display:none;"></span><span class="spacer"></span> <button type="button" id="venue-all">all</button> <button type="button" id="venue-none">none</button></h3>
        <div class="chk-grid">{venue_boxes}</div>
      </div>
    </aside>
    <main>
      <div class="view-switch-bar">
        <div class="view-toggle" role="group" aria-label="View mode">
          <button type="button" class="view-btn active" id="btn-view-list" data-view="list">
            <span>📋</span> List View
          </button>
          <button type="button" class="view-btn" id="btn-view-map" data-view="map">
            <span>🗺️</span> Map View
          </button>
        </div>
        <div class="view-switch-right">
          <button type="button" id="btn-share-filter" class="share-filter-btn" title="Copy shareable link with current filters">
            <span>🔗</span> <span id="share-btn-text">Share View</span>
          </button>
          <span id="map-venue-stat" class="map-venue-stat" style="display: none;">
            <strong id="map-venue-count">0</strong> venues on map
          </span>
        </div>
      </div>
      <div class="location-chips-bar" id="location-chips">
        <button type="button" class="loc-chip active" data-city="all">📍 All Boroughs</button>
        <button type="button" class="loc-chip" data-city="manhattan"><span class="city-dot" style="background:#5d9bff"></span>Manhattan</button>
        <button type="button" class="loc-chip" data-city="brooklyn"><span class="city-dot" style="background:#e05a6b"></span>Brooklyn</button>
        <button type="button" class="loc-chip" data-city="queens"><span class="city-dot" style="background:#f29e4c"></span>Queens</button>
        <button type="button" class="loc-chip" data-city="bronx"><span class="city-dot" style="background:#4ade80"></span>The Bronx</button>
        <button type="button" class="loc-chip" data-city="staten_island"><span class="city-dot" style="background:#a78bfa"></span>Staten Island</button>
        <button type="button" class="loc-chip" data-city="other"><span class="city-dot" style="background:#9aa3b2"></span>Tri-State</button>
      </div>
      <div class="subarea-chips-bar" id="subarea-chips-bar" style="display: none;"></div>
      <div class="quick-chips-bar" id="quick-chips">
        <button type="button" class="chip active" data-time="today">⚡ Today</button>
        <button type="button" class="chip" data-time="tomorrow">Tomorrow</button>
        <button type="button" class="chip" data-time="weekend">🎉 This Weekend</button>
        <button type="button" class="chip" data-time="week">📅 Next 7 Days</button>
        <button type="button" class="chip" data-time="all">All Upcoming</button>
        <button type="button" class="chip chip-guestlist" id="quick-guestlist-chip">🎟️ Guestlists</button>
        <button type="button" class="chip chip-free" id="quick-free-chip">✨ Free Only</button>
        <button type="button" class="chip chip-theater" id="quick-theater-chip">🎭 Theater</button>
      </div>
      <div class="week-nav" id="week-nav">
        <button type="button" id="week-prev" aria-label="Previous">← prev</button>
        <span id="week-label">Today, {today.strftime("%b %d")}</span>
        <button type="button" id="week-next" aria-label="Next">next →</button>
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
      <div id="map-view-wrapper" class="map-view-wrapper" style="display: none;">
        <div class="map-header">
          <div class="map-header-title">
            <span class="live-pulse"></span>
            <strong>NYC Live Map</strong>
            <span class="map-hint">· OpenStreetMap · Pins update with your date &amp; filters</span>
          </div>
          <div class="map-header-actions">
            <button type="button" id="map-label-toggle-btn" class="map-tool-btn" title="Toggle between venue names and numbers only">🏷️ Names: On</button>
            <button type="button" id="map-recenter-btn" class="map-tool-btn" title="Center map on NYC">🎯 Center NYC</button>
          </div>
        </div>
        <div id="leaflet-map" class="leaflet-map"></div>
        <div id="map-selected-venue" class="map-venue-card" style="display: none;">
          <div class="map-venue-card-head">
            <div>
              <h3 id="panel-venue-name"></h3>
              <p id="panel-venue-sub" class="panel-sub"></p>
            </div>
            <button type="button" id="panel-close-btn" class="panel-close" aria-label="Close panel">✕</button>
          </div>
          <ul id="panel-events-list" class="panel-events"></ul>
        </div>
      </div>
      <div id="no-events-msg" class="no-events-msg" style="display: none;">
        <p>No events found for this selection.</p>
        <div style="display:flex; justify-content:center; gap:8px; flex-wrap:wrap;">
          <button type="button" class="chip" id="no-events-week-btn">📅 View Next 7 Days</button>
          <button type="button" class="chip" id="no-events-all-btn">All Upcoming</button>
          <button type="button" class="chip" id="no-events-reset-btn" style="display: none;">↺ Reset All Filters</button>
        </div>
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
  <footer>
    <p>NYC Events · Live local music, comedy, arts, outdoors &amp; community events across New York City.</p>
    <p style="margin-top:6px; font-size:11px; opacity:0.85;">Data compiled directly from venue calendars and official local community feeds. Not affiliated with any commercial ticketing broker.</p>
  </footer>

  <!-- Community Event & Venue Submission Modal -->
  <div id="submit-event-modal" class="modal-overlay" role="dialog" aria-modal="true" aria-labelledby="modal-submit-title" style="display:none;">
    <div class="modal-card" id="submit-modal-card">
      <div class="modal-header">
        <div>
          <h2 class="modal-title" id="modal-submit-title">Add to NYC Events</h2>
          <p class="modal-sub" id="modal-submit-sub">Share an event or suggest a new venue / space for automatic tracking.</p>
        </div>
        <button type="button" class="modal-close-btn" id="btn-close-submit-modal" aria-label="Close modal">✕</button>
      </div>

      <div class="modal-tabs" role="tablist">
        <button type="button" class="modal-tab active" id="tab-btn-event" role="tab" aria-selected="true">
          <span>📅</span> Add an Event
        </button>
        <button type="button" class="modal-tab" id="tab-btn-venue" role="tab" aria-selected="false">
          <span>📍</span> Suggest a Venue
        </button>
      </div>

      <!-- Tab 1: Submit an Event Form -->
      <div id="modal-view-event">
        <form id="community-event-form" class="modal-form" novalidate>
          <input type="text" name="_hp_company" class="hp-field" tabindex="-1" autocomplete="off" aria-hidden="true" style="display:none !important;">

          <div class="form-row">
            <label for="ev-title" class="form-label">
              Event Title <span class="req">*</span>
            </label>
            <input type="text" id="ev-title" name="name" class="form-input" placeholder="e.g., Live Jazz Trio, Rooftop Party, Brooklyn Comedy Showcase" required maxlength="150">
          </div>

          <div class="form-grid-2">
            <div class="form-row">
              <label for="ev-venue" class="form-label">
                Venue / Location <span class="req">*</span>
              </label>
              <input type="text" id="ev-venue" name="venue" class="form-input" placeholder="e.g., Blue Note, Brooklyn Steel, Central Park" required maxlength="150">
            </div>
            <div class="form-row">
              <label for="ev-city" class="form-label">
                Borough / Area <span class="req">*</span>
              </label>
              <select id="ev-city" name="city" class="form-select" required>
                <option value="manhattan" selected>Manhattan (East Village, LES, SoHo, Midtown, UWS, UES, Harlem, FiDi)</option>
                <option value="brooklyn">Brooklyn (Williamsburg, Bushwick, DUMBO, Park Slope, Gowanus, Bed-Stuy)</option>
                <option value="queens">Queens (Astoria, Long Island City, Flushing, Ridgewood)</option>
                <option value="bronx">The Bronx</option>
                <option value="staten_island">Staten Island</option>
                <option value="other">Tri-State Area / Suburbs</option>
              </select>
            </div>
          </div>

          <div class="form-row">
            <label for="ev-address" class="form-label">
              Street Address / Neighborhood <span class="hint">(optional, helps map accurately)</span>
            </label>
            <input type="text" id="ev-address" name="address" class="form-input" placeholder="e.g., 131 W 3rd St, Greenwich Village" maxlength="150">
          </div>

          <div class="form-grid-2">
            <div class="form-row">
              <label for="ev-date" class="form-label">
                Date <span class="req">*</span>
              </label>
              <input type="date" id="ev-date" name="date" class="form-input" required>
            </div>
            <div class="form-row">
              <label for="ev-time" class="form-label">
                Start Time <span class="hint">(optional)</span>
              </label>
              <input type="time" id="ev-time" name="time" class="form-input" value="19:00">
            </div>
          </div>

          <div class="form-grid-2">
            <div class="form-row">
              <label for="ev-category" class="form-label">
                Category <span class="req">*</span>
              </label>
              <select id="ev-category" name="category" class="form-select" required>
                <option value="music">🎵 Music / Concert</option>
                <option value="comedy">🎙️ Comedy</option>
                <option value="theater">🎭 Stage &amp; Theater</option>
                <option value="dance">💃 Dance / Social</option>
                <option value="clubbing">🪩 Clubbing &amp; DJ</option>
                <option value="art">🎨 Art &amp; Gallery</option>
                <option value="food">🍷 Food &amp; Drink</option>
                <option value="fitness">🏃 Fitness &amp; Outdoors</option>
                <option value="books">📚 Books &amp; Talks</option>
                <option value="gaming">🎲 Trivia &amp; Games</option>
                <option value="community">🤝 Community &amp; Pop-up</option>
                <option value="other" selected>✨ Other</option>
              </select>
            </div>
            <div class="form-row">
              <label for="ev-price" class="form-label">
                Price <span class="hint">(e.g., Free, $15, $20-$30)</span>
              </label>
              <div class="price-input-row">
                <input type="text" id="ev-price" name="price" class="form-input" placeholder="e.g., Free or $15">
                <button type="button" id="btn-quick-free" class="btn-pill-free">✨ Free</button>
              </div>
            </div>
          </div>

          <div class="form-row">
            <label for="ev-url" class="form-label">
              Event Website / Ticket URL <span class="req">*</span>
            </label>
            <input type="url" id="ev-url" name="url" class="form-input" placeholder="https://..." required>
          </div>

          <div class="form-row">
            <label for="ev-desc" class="form-label">
              Short Description / Notes <span class="hint">(optional)</span>
            </label>
            <textarea id="ev-desc" name="description" class="form-textarea" rows="2" placeholder="Brief note about the performers, dress code, RSVP details..." maxlength="400"></textarea>
          </div>

          <div class="form-status" id="form-submit-status" style="display:none;"></div>

          <div class="form-actions">
            <button type="button" class="btn-cancel" id="btn-cancel-submit">Cancel</button>
            <button type="submit" class="btn-primary-submit" id="btn-submit-action">
              <span class="btn-text">Publish Event ↗</span>
              <span class="btn-spinner" style="display:none;">⏳ Adding...</span>
            </button>
          </div>

          <div class="form-footer-note">
            <span>🛡️ Submissions are instantly verified and added to the live schedule.</span>
          </div>
        </form>
      </div>

      <!-- Tab 2: Suggest a Venue Form -->
      <div id="modal-view-venue" style="display:none;">
        <form id="suggest-venue-form" class="modal-form" novalidate>
          <input type="text" name="_hp_company" class="hp-field" tabindex="-1" autocomplete="off" aria-hidden="true" style="display:none !important;">

          <div class="form-row">
            <label for="vn-name" class="form-label">
              Venue / Space Name <span class="req">*</span>
            </label>
            <input type="text" id="vn-name" name="name" class="form-input" placeholder="e.g., S.O.B.'s, Flop House, Baby's All Right" required maxlength="150">
          </div>

          <div class="form-row">
            <label for="vn-url" class="form-label">
              Venue Website or Calendar Page <span class="req">*</span>
            </label>
            <input type="url" id="vn-url" name="url" class="form-input" placeholder="https://..." required>
          </div>

          <div class="form-grid-2">
            <div class="form-row">
              <label for="vn-city" class="form-label">
                Borough / Area <span class="req">*</span>
              </label>
              <select id="vn-city" name="city" class="form-select" required>
                <option value="manhattan" selected>Manhattan (East Village, LES, SoHo, Midtown, UWS, UES, Harlem, FiDi)</option>
                <option value="brooklyn">Brooklyn (Williamsburg, Bushwick, DUMBO, Park Slope, Gowanus, Bed-Stuy)</option>
                <option value="queens">Queens (Astoria, Long Island City, Flushing, Ridgewood)</option>
                <option value="bronx">The Bronx</option>
                <option value="staten_island">Staten Island</option>
                <option value="other">Tri-State Area / Suburbs</option>
              </select>
            </div>
            <div class="form-row">
              <label for="vn-category" class="form-label">
                Primary Genre / Type
              </label>
              <select id="vn-category" name="category" class="form-select">
                <option value="music" selected>🎵 Live Music &amp; Concerts</option>
                <option value="comedy">🎙️ Comedy</option>
                <option value="theater">🎭 Stage &amp; Theater</option>
                <option value="dance">💃 Dance / Social</option>
                <option value="clubbing">🪩 Clubbing &amp; DJ</option>
                <option value="food">🍺 Brewery / Bar / Food</option>
                <option value="books">📚 Books &amp; Talks</option>
                <option value="art">🎨 Gallery &amp; Art Space</option>
                <option value="community">🤝 Community &amp; Pop-up</option>
                <option value="other">✨ Other</option>
              </select>
            </div>
          </div>

          <div class="form-row">
            <label for="vn-address" class="form-label">
              Address / Neighborhood <span class="hint">(optional)</span>
            </label>
            <input type="text" id="vn-address" name="address" class="form-input" placeholder="e.g., 204 Varick St, SoHo" maxlength="150">
          </div>

          <div class="form-row">
            <label for="vn-notes" class="form-label">
              Notes / Events to Scrape <span class="hint">(optional)</span>
            </label>
            <textarea id="vn-notes" name="notes" class="form-textarea" rows="2" placeholder="e.g., Live salsa every Friday and comedy on weekends..." maxlength="400"></textarea>
          </div>

          <div class="form-status" id="form-venue-status" style="display:none;"></div>

          <div class="form-actions">
            <button type="button" class="btn-cancel" id="btn-cancel-venue">Cancel</button>
            <button type="submit" class="btn-primary-submit" id="btn-submit-venue">
              <span class="btn-text">Submit Suggestion ↗</span>
              <span class="btn-spinner" style="display:none;">⏳ Submitting...</span>
            </button>
          </div>

          <div class="form-footer-note">
            <span>💡 Suggested venues are reviewed and plugged into our automated 30-minute scrapers!</span>
          </div>
        </form>
      </div>
    </div>
  </div>
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
    const subareaBar = document.getElementById('subarea-chips-bar');
    const SUBAREAS_DATA = {json.dumps(SUBAREAS_BY_CITY)};
    const CITY_LABELS_MAP = {json.dumps(CITY_LABELS)};
    let activeSubarea = 'all';
    let renderedSubareaCity = null;
    const quickChips = document.querySelectorAll('#quick-chips .chip[data-time]');
    const quickFreeChip = document.getElementById('quick-free-chip');
    const quickGuestlistChip = document.getElementById('quick-guestlist-chip');
    const quickTheaterChip = document.getElementById('quick-theater-chip');
    let timeFilter = 'today';
    let currentView = 'list';
    let showPastToday = false;
    let leafletMap = null;
    let markersLayer = null;
    let mapLoading = false;

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
    const DAYS_FULL = ['Sunday','Monday','Tuesday','Wednesday','Thursday','Friday','Saturday'];
    function fmtShort(d) {{ return MONTHS[d.getMonth()] + ' ' + d.getDate(); }}
    function fmtMonth(d) {{ return d.toLocaleString('en-US', {{ month: 'long', year: 'numeric' }}); }}

    function getEasternTodayISO() {{
      try {{
        const formatter = new Intl.DateTimeFormat('en-CA', {{
          timeZone: 'America/New_York',
          year: 'numeric',
          month: '2-digit',
          day: '2-digit'
        }});
        return formatter.format(new Date());
      }} catch (e) {{
        return "{today_iso}";
      }}
    }}

    let todayISO = getEasternTodayISO();
    let anchor = parseISO(todayISO);
    let showAll = false;
    let calMonth = new Date(anchor.getFullYear(), anchor.getMonth(), 1);

    function updateDayHeadings() {{
      const tDate = parseISO(todayISO);
      daySections.forEach(day => {{
        const dStr = day.dataset.date;
        if (!dStr || dStr === 'tba') return;
        const dObj = parseISO(dStr);
        const diffDays = Math.round((dObj - tDate) / 86400000);
        const h2 = day.querySelector('h2');
        if (!h2) return;
        const countSpan = h2.querySelector('.count');
        const countHtml = countSpan ? countSpan.outerHTML : '';
        const dayName = DAYS_FULL[dObj.getDay()];
        const shortStr = `${{MONTHS[dObj.getMonth()]}} ${{dObj.getDate()}}`;
        let prefix = dayName;
        if (diffDays === 0) {{
          prefix = 'Today';
        }} else if (diffDays === 1) {{
          prefix = 'Tomorrow';
        }} else if (diffDays === -1) {{
          prefix = 'Yesterday';
        }}
        h2.innerHTML = `${{prefix}} · ${{dayName}}, ${{shortStr}}${{countHtml}}`;
      }});
    }}

    function repositionPastBanner() {{
      let pastBanner = document.getElementById('past-events-banner');
      const todaySec = document.querySelector(`.day[data-date="${{todayISO}}"]`);
      if (!todaySec) return;
      const h2 = todaySec.querySelector('h2');
      if (!h2) return;
      if (!pastBanner) {{
        pastBanner = document.createElement('div');
        pastBanner.className = 'past-events-banner';
        pastBanner.id = 'past-events-banner';
        pastBanner.style.display = 'none';
        pastBanner.innerHTML = `
          <div class="past-banner-info">
            <span class="past-banner-badge" id="past-banner-badge">⏱️ Live Tonight</span>
            <span class="past-banner-text" id="past-banner-text"></span>
          </div>
          <div class="past-banner-actions">
            <button type="button" class="past-banner-btn" id="btn-toggle-past">Show earlier today</button>
            <button type="button" class="past-banner-btn btn-tomorrow" id="btn-banner-tomorrow" style="display: none;">See Tomorrow →</button>
          </div>
        `;
        h2.insertAdjacentElement('afterend', pastBanner);
      }} else if (pastBanner.parentElement !== todaySec) {{
        h2.insertAdjacentElement('afterend', pastBanner);
      }}
    }}

    function msUntilEasternMidnight() {{
      try {{
        const now = new Date();
        const parts = new Intl.DateTimeFormat('en-US', {{
          timeZone: 'America/New_York',
          hour12: false,
          hour: 'numeric',
          minute: 'numeric',
          second: 'numeric'
        }}).formatToParts(now);
        const h = parseInt(parts.find(p => p.type === 'hour').value, 10) % 24;
        const m = parseInt(parts.find(p => p.type === 'minute').value, 10);
        const s = parseInt(parts.find(p => p.type === 'second').value, 10);
        const ms = now.getMilliseconds();
        const secondsPassed = h * 3600 + m * 60 + s;
        const secondsUntilMidnight = 86400 - secondsPassed;
        return Math.max(1000, (secondsUntilMidnight * 1000) - ms + 1000);
      }} catch (e) {{
        return 60000;
      }}
    }}

    function checkDayRollover() {{
      const currentEasternISO = getEasternTodayISO();
      if (currentEasternISO && currentEasternISO !== todayISO) {{
        const wasToday = (timeFilter === 'today');
        todayISO = currentEasternISO;
        if (wasToday) {{
          anchor = parseISO(todayISO);
          calMonth = new Date(anchor.getFullYear(), anchor.getMonth(), 1);
        }}
        repositionPastBanner();
        updateDayHeadings();
        apply();
      }}
    }}

    function scheduleMidnightRefresh() {{
      const ms = msUntilEasternMidnight();
      setTimeout(() => {{
        checkDayRollover();
        scheduleMidnightRefresh();
      }}, Math.min(ms, 2147483647));
    }}

    function weekDates() {{
      const out = [];
      for (let i = 0; i < 7; i++) out.push(fmtISO(addDays(anchor, i)));
      return out;
    }}
    function updateWeekLabel() {{
      const end = addDays(anchor, 6);
      let label = '';
      if (timeFilter === 'all' || showAll) {{
        label = 'Showing all upcoming';
      }} else if (timeFilter === 'today') {{
        label = `Today, ${{fmtShort(anchor)}}`;
      }} else if (timeFilter === 'tomorrow') {{
        label = `Tomorrow, ${{fmtShort(anchor)}}`;
      }} else if (timeFilter === 'weekend') {{
        const todayDate = parseISO(todayISO);
        const dayOfWeek = todayDate.getDay();
        let daysToSat = (6 - dayOfWeek + 7) % 7;
        if (dayOfWeek === 0) daysToSat = -1;
        const sat = addDays(todayDate, daysToSat);
        const sun = addDays(sat, 1);
        label = `Weekend: ${{fmtShort(sat)}} – ${{fmtShort(sun)}}`;
      }} else if (timeFilter === 'day') {{
        label = `${{DAYS_FULL[anchor.getDay()]}}, ${{fmtShort(anchor)}}, ${{anchor.getFullYear()}}`;
      }} else {{
        label = `${{fmtShort(anchor)}} – ${{fmtShort(end)}}, ${{end.getFullYear()}}`;
      }}
      document.getElementById('week-label').textContent = label;
      const b = document.getElementById('week-label-b');
      if (b) b.textContent = label;
      const btn = document.getElementById('week-all');
      if (btn) {{
        btn.textContent = (timeFilter === 'all' || showAll) ? 'today view' : 'show all';
        btn.setAttribute('aria-pressed', (timeFilter === 'all' || showAll) ? 'true' : 'false');
      }}
    }}

    function escapeHTML(str) {{
      if (!str) return '';
      return String(str)
        .split('&').join('&amp;')
        .split('<').join('&lt;')
        .split('>').join('&gt;')
        .split('"').join('&quot;')
        .split("'").join('&#39;');
    }}

    function loadLeaflet(callback) {{
      if (window.L) {{ callback(); return; }}
      if (mapLoading) {{
        const interval = setInterval(() => {{
          if (window.L) {{ clearInterval(interval); callback(); }}
        }}, 50);
        return;
      }}
      mapLoading = true;
      const css = document.createElement('link');
      css.rel = 'stylesheet';
      css.href = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css';
      document.head.appendChild(css);

      const script = document.createElement('script');
      script.src = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js';
      script.onload = () => {{
        mapLoading = false;
        callback();
      }};
      document.head.appendChild(script);
    }}

    function initMap() {{
      if (leafletMap) return;
      const mapEl = document.getElementById('leaflet-map');
      if (!mapEl) return;

      leafletMap = L.map(mapEl, {{
        center: [40.7300, -73.9900],
        zoom: 12,
        minZoom: 10,
        maxZoom: 18,
      }});

      mapEl.classList.add('osm-dark-tiles');
      const osmUrl = (location.protocol === 'file:')
        ? 'https://tile.openstreetmap.de/{{z}}/{{x}}/{{y}}.png'
        : 'https://tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png';

      const tiles = L.tileLayer(osmUrl, {{
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a> contributors',
        maxZoom: 19
      }});

      tiles.on('tileerror', function(error) {{
        if (error.tile && error.tile.src && error.tile.src.includes('openstreetmap.org')) {{
          error.tile.src = error.tile.src.replace('tile.openstreetmap.org', 'tile.openstreetmap.de');
        }}
      }});

      tiles.addTo(leafletMap);
      markersLayer = L.layerGroup().addTo(leafletMap);
      updateMapMarkers();
    }}

    function switchView(mode) {{
      currentView = mode;
      const listBtn = document.getElementById('btn-view-list');
      const mapBtn = document.getElementById('btn-view-map');
      const mapWrapper = document.getElementById('map-view-wrapper');
      const mapStat = document.getElementById('map-venue-stat');

      if (listBtn) listBtn.classList.toggle('active', mode === 'list');
      if (mapBtn) mapBtn.classList.toggle('active', mode === 'map');
      if (mapWrapper) mapWrapper.style.display = (mode === 'map') ? 'flex' : 'none';
      if (mapStat) mapStat.style.display = (mode === 'map') ? 'inline-block' : 'none';

      if (mode === 'map') {{
        loadLeaflet(() => {{
          initMap();
          if (leafletMap) {{
            leafletMap.invalidateSize();
            updateMapMarkers();
          }}
        }});
      }}
      stateToHash();
    }}

    function shortenVenueName(name) {{
      if (!name) return '';
      const OVERRIDES = {{
        'Lincoln Center for the Performing Arts': 'Lincoln Center',
        'David Geffen Hall at Lincoln Center': 'David Geffen Hall',
        'Alice Tully Hall at Lincoln Center': 'Alice Tully Hall',
        'Metropolitan Museum of Art': 'The Met',
        'The Metropolitan Museum of Art': 'The Met',
        'Museum of Modern Art (MoMA)': 'MoMA',
        'Museum of the Moving Image': 'Moving Image',
        'American Folk Art Museum': 'Folk Art Museum',
        'Brooklyn Academy of Music': 'BAM',
        'Music Hall of Williamsburg': 'Music Hall of Wmsburg',
        'Brooklyn Paramount Theater': 'BK Paramount',
        'Brooklyn Museum': 'BK Museum',
        'New York Public Library': 'NYPL',
        'New York Botanical Garden': 'NYBG',
        'Brooklyn Botanic Garden': 'BK Botanic',
        'Madison Square Garden': 'MSG',
        'Radio City Music Hall': 'Radio City',
        'The Bell House': 'Bell House',
        "Pete's Candy Store": "Pete's Candy",
        "Baby's All Right": "Baby's All Right",
        'Skinny Dennis': 'Skinny Dennis',
        'Flop House Comedy Club': 'Flop House',
        'Comedy Cellar': 'Comedy Cellar',
        'Village Vanguard': 'Village Vanguard',
        'Blue Note Jazz Club': 'Blue Note',
        'Smalls Jazz Club': 'Smalls Jazz',
        'Mezzrow Jazz Club': 'Mezzrow',
        "S.O.B.'s": "S.O.B.'s",
        'House of Yes': 'House of Yes',
        'Brooklyn Steel': 'BK Steel',
        'Brooklyn Monarch': 'BK Monarch',
        'Webster Hall': 'Webster Hall',
        'Mercury Lounge': 'Mercury Lounge',
        'Bowery Ballroom': 'Bowery Ballroom',
        'Irving Plaza': 'Irving Plaza',
        'Gramercy Theatre': 'Gramercy',
        'Kings Theatre': 'Kings Theatre',
        'Knockdown Center': 'Knockdown Center',
        'Carnegie Hall': 'Carnegie Hall',
      }};
      if (OVERRIDES[name]) return OVERRIDES[name];
      let s = name;
      s = s.replace(/\\s*\\((?:via\\s+[^)]+|NYC|New York)\\)/gi, '');
      s = s.replace(/,?\\s*(?:New York|NYC|Brooklyn|Queens|Manhattan|Bronx|Staten Island)(?:,\\s*NY)?$/gi, '');
      s = s.replace(/\\s+(?:Brewing(?:\\s+Co\\.?)?|Brewery|Booksellers(?:\\s*&\\s*Cafe)?|Music\\s+Hall|Jazz\\s+Club|Center\\s+for\\s+the\\s+Arts)$/gi, '');
      s = s.trim();
      if (s.length > 18 && s.startsWith('The ')) {{
        s = s.slice(4).trim();
      }}
      if (s.length > 18) {{
        s = s.slice(0, 16).trim() + '…';
      }}
      return s;
    }}

    function updateMapMarkers() {{
      if (!leafletMap || !markersLayer) return;
      markersLayer.clearLayers();

      const visibleDaySecs = daySections.filter(d => !d.classList.contains('out-of-week') && !d.classList.contains('empty'));
      const venueMap = new Map();

      visibleDaySecs.forEach(day => {{
        const dayDate = day.dataset.date;
        day.querySelectorAll('.event:not(.hidden)').forEach(li => {{
          const lat = parseFloat(li.dataset.lat);
          const lng = parseFloat(li.dataset.lng);
          if (isNaN(lat) || isNaN(lng)) return;

          const vName = li.dataset.venueName || li.dataset.venue || 'Venue';
          const key = `${{lat.toFixed(4)}},${{lng.toFixed(4)}}`;
          if (!venueMap.has(key)) {{
            venueMap.set(key, {{
              lat, lng,
              name: vName,
              neighborhood: li.dataset.neighborhood || li.dataset.subareaName || '',
              events: []
            }});
          }}

          const linkEl = li.querySelector('.what a');
          const title = linkEl ? linkEl.textContent.trim() : (li.querySelector('.what')?.textContent || '');
          const url = linkEl ? linkEl.getAttribute('href') : '';
          const when = li.querySelector('.when')?.textContent.trim() || '';
          const price = li.querySelector('.price')?.textContent.trim() || '';
          const isFree = li.dataset.free === 'true';

          venueMap.get(key).events.push({{
            title, url, when, price, isFree, date: dayDate
          }});
        }});
      }});

      const countBadge = document.getElementById('map-venue-count');
      if (countBadge) countBadge.textContent = venueMap.size;

      venueMap.forEach(v => {{
        const count = v.events.length;
        const shortName = shortenVenueName(v.name);
        const icon = L.divIcon({{
          className: 'custom-venue-icon',
          html: `<div class="venue-marker" title="${{escapeHTML(v.name)}} (${{count}} event${{count === 1 ? '' : 's'}})"><span class="pin-name">${{escapeHTML(shortName)}}</span><span class="pin-count">${{count}}</span></div>`,
          iconSize: null,
          iconAnchor: [0, 0],
        }});

        const marker = L.marker([v.lat, v.lng], {{ icon: icon }});

        let popupHtml = `<div class="map-popup">
          <div class="popup-head">
            <strong>${{escapeHTML(v.name)}}</strong>
            ${{v.neighborhood ? `<span class="popup-neighborhood">📍 ${{escapeHTML(v.neighborhood)}}</span>` : ''}}
          </div>
          <div class="popup-events">`;

        v.events.slice(0, 5).forEach(ev => {{
          popupHtml += `<div class="popup-event-item">
            <span class="popup-time">${{escapeHTML(ev.when)}}</span>
            <a href="${{escapeHTML(ev.url)}}" target="_blank" rel="noopener" class="popup-title">${{escapeHTML(ev.title)}}</a>
            ${{ev.price ? `<span class="popup-price ${{ev.isFree ? 'free' : ''}}">${{escapeHTML(ev.price)}}</span>` : ''}}
          </div>`;
        }});
        if (v.events.length > 5) {{
          popupHtml += `<div class="popup-more">+ ${{v.events.length - 5}} more events</div>`;
        }}
        const mapsQuery = encodeURIComponent(`${{v.name}}, New York NY`);
        popupHtml += `</div>
          <div class="popup-foot">
            <a href="https://www.google.com/maps/search/?api=1&query=${{mapsQuery}}" target="_blank" rel="noopener" class="popup-dir-link">Google Maps Directions ↗</a>
          </div>
        </div>`;

        marker.bindPopup(popupHtml, {{ maxWidth: 300 }});
        marker.on('click', () => {{
          showVenuePanel(v);
        }});
        markersLayer.addLayer(marker);
      }});
    }}

    function showVenuePanel(v) {{
      const panel = document.getElementById('map-selected-venue');
      if (!panel) return;
      document.getElementById('panel-venue-name').textContent = v.name;
      document.getElementById('panel-venue-sub').textContent = v.neighborhood ? `📍 ${{v.neighborhood}} · ${{v.events.length}} event(s)` : `${{v.events.length}} event(s)`;

      const list = document.getElementById('panel-events-list');
      list.innerHTML = v.events.map(ev => `
        <li class="popup-event-item">
          <span class="popup-time">${{escapeHTML(ev.when)}}</span>
          <a href="${{escapeHTML(ev.url)}}" target="_blank" rel="noopener" class="popup-title">${{escapeHTML(ev.title)}}</a>
          ${{ev.price ? `<span class="popup-price ${{ev.isFree ? 'free' : ''}}">${{escapeHTML(ev.price)}}</span>` : ''}}
        </li>
      `).join('');
      panel.style.display = 'block';
    }}

    function updateQuickChipsUI() {{
      quickChips.forEach(chip => {{
        chip.classList.toggle('active', chip.dataset.time === timeFilter);
      }});
      if (quickTheaterChip) {{
        const checked = Array.from(catBoxes).filter(b => b.checked).map(b => b.value);
        quickTheaterChip.classList.toggle('active', checked.length === 1 && checked[0] === 'Theater');
      }}
      if (quickFreeChip) {{
        quickFreeChip.classList.toggle('active', freeOnlyChk ? freeOnlyChk.checked : false);
      }}
      if (quickGuestlistChip) {{
        quickGuestlistChip.classList.toggle('active', guestlistOnlyChk ? guestlistOnlyChk.checked : false);
      }}
    }}

    function renderSubareaChips(city) {{
      if (!subareaBar) return;
      if (!city || city === 'all' || !SUBAREAS_DATA[city]) {{
        subareaBar.style.display = 'none';
        subareaBar.innerHTML = '';
        renderedSubareaCity = null;
        activeSubarea = 'all';
        return;
      }}

      if (renderedSubareaCity === city) {{
        subareaBar.querySelectorAll('.sub-chip').forEach(b => {{
          b.classList.toggle('active', b.dataset.subarea === activeSubarea);
        }});
        return;
      }}

      renderedSubareaCity = city;
      const subs = SUBAREAS_DATA[city] || [];
      const cityLabel = (CITY_LABELS_MAP && CITY_LABELS_MAP[city]) || city;
      let html = `<button type="button" class="sub-chip ${{activeSubarea === 'all' ? 'active' : ''}}" data-subarea="all">📍 All ${{cityLabel}}</button>`;
      subs.forEach(s => {{
        const slug = s[0];
        const name = s[1];
        const icon = s[2] || '📍';
        const isAct = (activeSubarea === slug);
        html += `<button type="button" class="sub-chip ${{isAct ? 'active' : ''}}" data-subarea="${{slug}}">${{icon}} ${{name}}</button>`;
      }});
      subareaBar.innerHTML = html;
      subareaBar.style.display = 'flex';

      subareaBar.querySelectorAll('.sub-chip').forEach(btn => {{
        btn.addEventListener('click', () => {{
          const targetSub = btn.dataset.subarea;
          if (activeSubarea === targetSub && targetSub !== 'all') {{
            activeSubarea = 'all';
          }} else {{
            activeSubarea = targetSub;
          }}
          subareaBar.querySelectorAll('.sub-chip').forEach(b => {{
            b.classList.toggle('active', b.dataset.subarea === activeSubarea);
          }});
          apply();
        }});
      }});
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
      if (checkedCities.length === 1) {{
        renderSubareaChips(checkedCities[0]);
      }} else {{
        renderSubareaChips('all');
      }}
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
      const allCats = catBoxes.length;
      const chkCats = Array.from(catBoxes).filter(b => b.checked).length;
      const allVenues = venueBoxes.length;
      const chkVenues = Array.from(venueBoxes).filter(b => b.checked).length;
      const allCities = cityBoxes.length;
      const chkCities = Array.from(cityBoxes).filter(b => b.checked).length;
      const allRecurs = recurBoxes.length;
      const chkRecurs = Array.from(recurBoxes).filter(b => b.checked).length;
      const isFree = freeOnlyChk && freeOnlyChk.checked;
      const isGuestlist = guestlistOnlyChk && guestlistOnlyChk.checked;
      const isFiltered = (chkCats < allCats) || (chkVenues < allVenues) || (chkCities < allCities) || (chkRecurs < allRecurs) || isFree || isGuestlist || (activeSubarea !== 'all') || (searchInput && !!searchInput.value.trim());

      if (mobileBadge) {{
        mobileBadge.textContent = isFiltered ? 'Active' : 'All';
        mobileBadge.style.color = isFiltered ? 'var(--accent)' : '';
      }}

      const resetBar = document.getElementById('reset-filters-bar');
      if (resetBar) {{
        resetBar.style.display = isFiltered ? 'block' : 'none';
      }}
      const noEventsResetBtn = document.getElementById('no-events-reset-btn');
      if (noEventsResetBtn) {{
        noEventsResetBtn.style.display = isFiltered ? 'inline-block' : 'none';
      }}

      const venueFilterCount = document.getElementById('venue-filter-count');
      if (venueFilterCount) {{
        if (chkVenues > 0 && chkVenues < allVenues) {{
          venueFilterCount.textContent = `${{chkVenues}} selected`;
          venueFilterCount.style.display = 'inline';
        }} else {{
          venueFilterCount.style.display = 'none';
        }}
      }}
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
      if (activeSubarea && activeSubarea !== 'all') params.set('sub', activeSubarea);

      const allRecurs = Array.from(recurBoxes).map(b => b.value);
      const checkedRecurs = Array.from(recurBoxes).filter(b => b.checked).map(b => b.value);
      if (checkedRecurs.length > 0 && checkedRecurs.length < allRecurs.length) params.set('recur', checkedRecurs.join(','));

      const allVenues = Array.from(venueBoxes).map(b => b.value);
      const checkedVenues = Array.from(venueBoxes).filter(b => b.checked).map(b => b.value);
      if (checkedVenues.length > 0 && checkedVenues.length < allVenues.length) params.set('venues', checkedVenues.join(';'));

      if (freeOnlyChk && freeOnlyChk.checked) params.set('free', '1');
      if (guestlistOnlyChk && guestlistOnlyChk.checked) params.set('guestlist', '1');

      if (timeFilter !== 'today') params.set('t', timeFilter);
      if ((timeFilter === 'day' || timeFilter === 'week') && fmtISO(anchor) !== todayISO) {{
        params.set('d', fmtISO(anchor));
      }}
      if (currentView !== 'list') params.set('v', currentView);
      if (showPastToday) params.set('past', '1');

      const hash = params.toString();
      history.replaceState(null, '', hash ? '#' + hash : location.pathname + location.search);
    }}

    function hashToState() {{
      const hash = location.hash.slice(1);
      const params = hash ? new URLSearchParams(hash) : null;

      if (params) {{
        if (params.has('q')) searchInput.value = params.get('q');
        if (params.get('free') === '1' && freeOnlyChk) freeOnlyChk.checked = true;
        if (params.get('guestlist') === '1' && guestlistOnlyChk) guestlistOnlyChk.checked = true;
        if (params.get('past') === '1') showPastToday = true;
        if (params.get('v') === 'map') {{
          switchView('map');
        }}

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

        if (params.has('sub')) {{
          activeSubarea = params.get('sub');
        }} else {{
          activeSubarea = 'all';
        }}

        if (params.has('recur')) {{
          const vals = new Set(params.get('recur').split(','));
          recurBoxes.forEach(b => {{ b.checked = vals.has(b.value); }});
        }}

        if (params.has('venues')) {{
          const rawVenues = params.get('venues').split(';').map(s => s.trim()).filter(Boolean);
          const vals = new Set(rawVenues);
          venueBoxes.forEach(b => {{ b.checked = vals.has(b.value); }});
          try {{
            localStorage.setItem('nyc_saved_venues', JSON.stringify(Array.from(vals)));
          }} catch (_) {{}}
        }}

        if (params.has('d')) {{
          const d = params.get('d');
          if (d === 'all') {{
            showAll = true;
            timeFilter = 'all';
          }} else {{
            anchor = parseISO(d);
            calMonth = new Date(anchor.getFullYear(), anchor.getMonth(), 1);
            if (!params.has('t')) {{
              if (d === todayISO) {{
                timeFilter = 'today';
                showAll = false;
              }} else if (d === fmtISO(addDays(parseISO(todayISO), 1))) {{
                timeFilter = 'tomorrow';
                showAll = false;
              }} else {{
                timeFilter = 'day';
                showAll = false;
              }}
            }}
          }}
        }}
      }}

      if (!params || !params.has('venues')) {{
        try {{
          const saved = JSON.parse(localStorage.getItem('nyc_saved_venues') || 'null');
          if (Array.isArray(saved) && saved.length > 0 && saved.length < venueBoxes.length) {{
            const savedSet = new Set(saved);
            venueBoxes.forEach(b => {{ b.checked = savedSet.has(b.value); }});
          }}
        }} catch (_) {{}}
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

      const nowEpoch = Math.floor(Date.now() / 1000);
      const twoHoursAgoEpoch = nowEpoch - 7200;
      const cutoffDate = new Date(Date.now() - 7200 * 1000);
      const cutoffTimeStr = cutoffDate.toLocaleTimeString('en-US', {{
        timeZone: 'America/New_York',
        hour: 'numeric',
        minute: '2-digit'
      }});

      let hiddenPastCount = 0;
      let totalTodayEventsCount = 0;
      let visibleTonightCount = 0;

      document.querySelectorAll('.event').forEach(li => {{
        const catOk = cats.has(li.dataset.bucket);
        const venueOk = venues.has(li.dataset.venue) || (li.dataset.presenter && venues.has(li.dataset.presenter));
        const recurOk = recurs.has(li.dataset.recur);
        const cityOk = cities.has(li.dataset.city);
        const subareaOk = (activeSubarea === 'all') || (li.dataset.subarea === activeSubarea);
        const freeOk = !freeOnly || li.dataset.free === 'true';
        const guestlistOk = !guestlistOnly || li.dataset.guestlist === 'true';
        const searchOk = !searchText || li.textContent.toLowerCase().includes(searchText);

        const daySec = li.closest('.day');
        const dayDate = daySec ? daySec.dataset.date : '';
        const isToday = daySec && dayDate === todayISO;
        const isPastDay = dayDate && dayDate !== 'tba' && dayDate < todayISO;
        const epoch = li.dataset.epoch ? parseInt(li.dataset.epoch, 10) : 0;
        const isPastTime = isToday && epoch > 0 && epoch < twoHoursAgoEpoch;
        const isPast = isPastDay || isPastTime;

        if (isToday && epoch > 0) {{
          totalTodayEventsCount++;
        }}

        li.classList.toggle('past-time', isPast);

        let timePastOk = true;
        if (isPast) {{
          if (!showPastToday) {{
            timePastOk = false;
            hiddenPastCount++;
          }}
        }}

        const isVisible = catOk && venueOk && recurOk && cityOk && subareaOk && searchOk && freeOk && guestlistOk && timePastOk;
        li.classList.toggle('hidden', !isVisible);

        if (isToday && isVisible && !isPast) {{
          visibleTonightCount++;
        }}
      }});

      document.querySelectorAll('.bucket').forEach(b => {{
        const visible = b.querySelectorAll('.event:not(.hidden)').length;
        b.classList.toggle('empty', visible === 0);
        const countSpan = b.querySelector('.bucket-head .count');
        if (countSpan) countSpan.textContent = visible;
      }});
      document.querySelectorAll('.city-section').forEach(sec => {{
        const visible = sec.querySelectorAll('.event:not(.hidden)').length;
        sec.classList.toggle('empty', visible === 0);
        const countSpan = sec.querySelector('.city-head .count');
        if (countSpan) countSpan.textContent = visible;
      }});

      // Update past events notice banner
      const pastBanner = document.getElementById('past-events-banner');
      if (pastBanner) {{
        const showBanner = (timeFilter === 'today' || (timeFilter === 'all' && showAll)) && (hiddenPastCount > 0 || showPastToday);
        if (showBanner && (hiddenPastCount > 0 || (showPastToday && totalTodayEventsCount > 0))) {{
          pastBanner.style.display = 'flex';
          const badge = document.getElementById('past-banner-badge');
          const text = document.getElementById('past-banner-text');
          const toggleBtn = document.getElementById('btn-toggle-past');
          const tomorrowBtn = document.getElementById('btn-banner-tomorrow');

          if (!showPastToday) {{
            if (visibleTonightCount === 0 && hiddenPastCount > 0) {{
              if (badge) {{ badge.textContent = 'Tonight Wrapped Up'; badge.className = 'past-banner-badge badge-done'; }}
              if (text) {{ text.innerHTML = `All scheduled events for today have started (<strong>${{hiddenPastCount}}</strong> earlier event${{hiddenPastCount === 1 ? '' : 's'}} hidden)`; }}
              if (toggleBtn) {{ toggleBtn.textContent = 'Show earlier today'; }}
              if (tomorrowBtn) {{ tomorrowBtn.style.display = 'inline-block'; }}
            }} else {{
              if (badge) {{ badge.textContent = '⏱️ Live Tonight'; badge.className = 'past-banner-badge'; }}
              if (text) {{ text.innerHTML = `Showing events from <strong>${{cutoffTimeStr}}</strong> onward (<strong>${{hiddenPastCount}}</strong> earlier event${{hiddenPastCount === 1 ? '' : 's'}} hidden)`; }}
              if (toggleBtn) {{ toggleBtn.textContent = 'Show earlier today'; }}
              if (tomorrowBtn) {{ tomorrowBtn.style.display = 'none'; }}
            }}
          }} else {{
            if (badge) {{ badge.textContent = 'All Day'; badge.className = 'past-banner-badge badge-all'; }}
            if (text) {{ text.innerHTML = `Showing all events for today (including earlier events before ${{cutoffTimeStr}})`; }}
            if (toggleBtn) {{ toggleBtn.textContent = 'Hide earlier events'; }}
            if (tomorrowBtn) {{ tomorrowBtn.style.display = 'none'; }}
          }}
        }} else {{
          pastBanner.style.display = 'none';
        }}
      }}

      const todayDate = parseISO(todayISO);
      const dayOfWeek = todayDate.getDay();
      let daysToSat = (6 - dayOfWeek + 7) % 7;
      if (dayOfWeek === 0) daysToSat = -1;
      const satISO = fmtISO(addDays(todayDate, daysToSat));
      const sunISO = fmtISO(addDays(todayDate, daysToSat + 1));
      const tomorrowISO = fmtISO(addDays(todayDate, 1));
      const anchorISO = fmtISO(anchor);

      daySections.forEach(day => {{
        const date = day.dataset.date;
        let inTime = true;
        if (timeFilter === 'today') {{
          inTime = (date === todayISO);
        }} else if (timeFilter === 'tomorrow') {{
          inTime = (date === tomorrowISO);
        }} else if (timeFilter === 'weekend') {{
          inTime = (date === satISO || date === sunISO);
        }} else if (timeFilter === 'day') {{
          inTime = (date === anchorISO);
        }} else if (timeFilter === 'week') {{
          inTime = (date === 'tba' || week.has(date));
        }} else {{
          inTime = showAll || date === 'tba' || week.has(date);
        }}
        day.classList.toggle('out-of-week', !inTime);
        const visible = day.querySelectorAll('.event:not(.hidden)').length;
        day.classList.toggle('empty', visible === 0);
        const headingCount = day.querySelector('h2 .count');
        if (headingCount) headingCount.textContent = visible;
      }});

      const ongoingEl = document.querySelector('.ongoing');
      if (ongoingEl) {{
        ongoingEl.style.display = (timeFilter === 'all' || showAll) ? '' : 'none';
      }}

      const visibleDays = daySections.filter(d => !d.classList.contains('out-of-week') && !d.classList.contains('empty')).length;
      const noEventsEl = document.getElementById('no-events-msg');
      if (noEventsEl) {{
        noEventsEl.style.display = (visibleDays === 0) ? 'block' : 'none';
      }}

      renderCal();
      updateWeekLabel();
      updateQuickChipsUI();
      updateLocChipsUI();
      updateSearchUI();

      const allVenues = venueBoxes.length;
      const checkedVenuesList = Array.from(venueBoxes).filter(b => b.checked).map(b => b.value);
      if (checkedVenuesList.length > 0 && checkedVenuesList.length < allVenues) {{
        try {{
          localStorage.setItem('nyc_saved_venues', JSON.stringify(checkedVenuesList));
        }} catch (_) {{}}
      }} else if (checkedVenuesList.length === allVenues) {{
        try {{
          localStorage.removeItem('nyc_saved_venues');
        }} catch (_) {{}}
      }}

      updateMobileBadge();
      if (currentView === 'map' && leafletMap) {{
        updateMapMarkers();
      }}
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
        if (!showAll && timeFilter === 'week' && week.has(iso)) classes.push('in-week');
        if (iso === fmtISO(anchor)) classes.push('anchor');
        html += `<div class="${{classes.join(' ')}}" data-date="${{iso}}">${{d}}</div>`;
      }}
      grid.innerHTML = html;
    }}

    function shiftNav(delta) {{
      if (timeFilter === 'week') {{
        anchor = addDays(anchor, delta * 7);
      }} else if (timeFilter === 'today' || timeFilter === 'tomorrow' || timeFilter === 'day') {{
        anchor = addDays(anchor, delta);
        const iso = fmtISO(anchor);
        if (iso === todayISO) {{
          timeFilter = 'today';
        }} else if (iso === fmtISO(addDays(parseISO(todayISO), 1))) {{
          timeFilter = 'tomorrow';
        }} else {{
          timeFilter = 'day';
        }}
      }} else if (timeFilter === 'weekend') {{
        anchor = addDays(anchor, delta * 7);
      }} else {{
        // 'all'
        anchor = addDays(parseISO(todayISO), delta > 0 ? 1 : 0);
        const iso = fmtISO(anchor);
        timeFilter = (iso === todayISO) ? 'today' : (iso === fmtISO(addDays(parseISO(todayISO), 1)) ? 'tomorrow' : 'day');
      }}
      showAll = false;
      calMonth = new Date(anchor.getFullYear(), anchor.getMonth(), 1);
      apply();
    }}

    function setAnchor(iso) {{
      if (iso === todayISO) {{
        timeFilter = 'today';
      }} else if (iso === fmtISO(addDays(parseISO(todayISO), 1))) {{
        timeFilter = 'tomorrow';
      }} else {{
        timeFilter = 'day';
      }}
      showAll = false;
      anchor = parseISO(iso);
      calMonth = new Date(anchor.getFullYear(), anchor.getMonth(), 1);
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

    if (quickTheaterChip) {{
      quickTheaterChip.addEventListener('click', () => {{
        const checked = Array.from(catBoxes).filter(b => b.checked).map(b => b.value);
        if (checked.length === 1 && checked[0] === 'Theater') {{
          catBoxes.forEach(b => {{ b.checked = true; }});
        }} else {{
          catBoxes.forEach(b => {{
            b.checked = (b.value === 'Theater');
          }});
        }}
        apply();
        stateToHash();
      }});
    }}

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

    document.getElementById('week-prev').addEventListener('click', () => shiftNav(-1));
    document.getElementById('week-next').addEventListener('click', () => shiftNav(1));
    const prevB = document.getElementById('week-prev-b');
    if (prevB) prevB.addEventListener('click', () => shiftNav(-1));
    const nextB = document.getElementById('week-next-b');
    if (nextB) nextB.addEventListener('click', () => shiftNav(1));
    document.getElementById('week-today').addEventListener('click', () => {{
      timeFilter = 'today';
      showAll = false;
      anchor = parseISO(todayISO);
      calMonth = new Date(anchor.getFullYear(), anchor.getMonth(), 1);
      apply();
    }});
    document.getElementById('week-all').addEventListener('click', () => {{
      if (showAll || timeFilter === 'all') {{
        showAll = false;
        timeFilter = 'today';
        anchor = parseISO(todayISO);
      }} else {{
        showAll = true;
        timeFilter = 'all';
      }}
      calMonth = new Date(anchor.getFullYear(), anchor.getMonth(), 1);
      apply();
    }});

    const noEventsWeek = document.getElementById('no-events-week-btn');
    if (noEventsWeek) {{
      noEventsWeek.addEventListener('click', () => {{
        timeFilter = 'week';
        showAll = false;
        anchor = parseISO(todayISO);
        calMonth = new Date(anchor.getFullYear(), anchor.getMonth(), 1);
        apply();
      }});
    }}
    const noEventsAll = document.getElementById('no-events-all-btn');
    if (noEventsAll) {{
      noEventsAll.addEventListener('click', () => {{
        timeFilter = 'all';
        showAll = true;
        calMonth = new Date(anchor.getFullYear(), anchor.getMonth(), 1);
        apply();
      }});
    }}
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
    document.getElementById('venue-all').addEventListener('click', () => {{
      venueBoxes.forEach(b => b.checked = true);
      try {{ localStorage.removeItem('nyc_saved_venues'); }} catch (_) {{}}
      apply();
    }});
    document.getElementById('venue-none').addEventListener('click', () => {{ venueBoxes.forEach(b => b.checked = false); apply(); }});
    document.getElementById('city-all').addEventListener('click', () => {{ activeSubarea = 'all'; cityBoxes.forEach(b => b.checked = true); apply(); }});
    document.getElementById('city-none').addEventListener('click', () => {{ activeSubarea = 'all'; cityBoxes.forEach(b => b.checked = false); apply(); }});

    function resetAllFilters() {{
      if (searchInput) searchInput.value = '';
      if (freeOnlyChk) freeOnlyChk.checked = false;
      if (guestlistOnlyChk) guestlistOnlyChk.checked = false;
      activeSubarea = 'all';
      catBoxes.forEach(b => b.checked = true);
      cityBoxes.forEach(b => b.checked = true);
      recurBoxes.forEach(b => b.checked = true);
      venueBoxes.forEach(b => b.checked = true);
      try {{ localStorage.removeItem('nyc_saved_venues'); }} catch (_) {{}}
      apply();
    }}

    const btnResetFilters = document.getElementById('btn-reset-filters');
    if (btnResetFilters) btnResetFilters.addEventListener('click', resetAllFilters);

    const noEventsResetBtn = document.getElementById('no-events-reset-btn');
    if (noEventsResetBtn) noEventsResetBtn.addEventListener('click', resetAllFilters);

    const btnShareFilter = document.getElementById('btn-share-filter');
    if (btnShareFilter) {{
      btnShareFilter.addEventListener('click', async () => {{
        try {{
          await navigator.clipboard.writeText(location.href);
          const shareText = document.getElementById('share-btn-text');
          if (shareText) shareText.textContent = '✓ Copied Link!';
          btnShareFilter.classList.add('copied');
          setTimeout(() => {{
            if (shareText) shareText.textContent = 'Share View';
            btnShareFilter.classList.remove('copied');
          }}, 2000);
        }} catch (_) {{
          prompt('Copy this link to share your filtered view:', location.href);
        }}
      }});
    }}

    window.addEventListener('hashchange', () => {{
      hashToState();
      apply();
    }});

    locChips.forEach(chip => {{
      chip.addEventListener('click', () => {{
        const targetCity = chip.dataset.city;
        activeSubarea = 'all';
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

    const btnViewList = document.getElementById('btn-view-list');
    if (btnViewList) btnViewList.addEventListener('click', () => switchView('list'));

    const btnViewMap = document.getElementById('btn-view-map');
    if (btnViewMap) btnViewMap.addEventListener('click', () => switchView('map'));

    const mapRecenterBtn = document.getElementById('map-recenter-btn');
    if (mapRecenterBtn) {{
      mapRecenterBtn.addEventListener('click', () => {{
        if (leafletMap) {{
          leafletMap.setView([40.7300, -73.9900], 12, {{ animate: true }});
        }}
      }});
    }}

    const mapLabelToggleBtn = document.getElementById('map-label-toggle-btn');
    const mapEl = document.getElementById('leaflet-map');

    function updateLabelToggleState() {{
      if (!mapLabelToggleBtn || !mapEl) return;
      const isMobile = window.innerWidth <= 860;
      if (isMobile) {{
        const namesOn = mapEl.classList.contains('show-pin-names-mobile');
        mapLabelToggleBtn.textContent = namesOn ? '🏷️ Names: On' : '🔢 Numbers Only';
        mapLabelToggleBtn.title = namesOn ? 'Switch to compact numbers only' : 'Show venue names on pins';
      }} else {{
        const namesOff = mapEl.classList.contains('hide-pin-names');
        mapLabelToggleBtn.textContent = namesOff ? '🔢 Numbers Only' : '🏷️ Names: On';
        mapLabelToggleBtn.title = namesOff ? 'Show venue names on pins' : 'Switch to compact numbers only';
      }}
    }}

    if (mapLabelToggleBtn && mapEl) {{
      mapLabelToggleBtn.addEventListener('click', () => {{
        const isMobile = window.innerWidth <= 860;
        if (isMobile) {{
          mapEl.classList.toggle('show-pin-names-mobile');
        }} else {{
          mapEl.classList.toggle('hide-pin-names');
        }}
        updateLabelToggleState();
      }});
      window.addEventListener('resize', updateLabelToggleState);
      updateLabelToggleState();
    }}

    const panelCloseBtn = document.getElementById('panel-close-btn');
    if (panelCloseBtn) {{
      panelCloseBtn.addEventListener('click', () => {{
        const p = document.getElementById('map-selected-venue');
        if (p) p.style.display = 'none';
      }});
    }}

    document.addEventListener('click', (e) => {{
      const jumpBtn = e.target.closest('.venue-map-jump');
      if (jumpBtn) {{
        e.preventDefault();
        const lat = parseFloat(jumpBtn.dataset.lat);
        const lng = parseFloat(jumpBtn.dataset.lng);
        if (isNaN(lat) || isNaN(lng)) return;
        switchView('map');
        loadLeaflet(() => {{
          initMap();
          if (leafletMap) {{
            leafletMap.setView([lat, lng], 15, {{ animate: true }});
            const mapWrap = document.getElementById('map-view-wrapper');
            if (mapWrap) mapWrap.scrollIntoView({{ behavior: 'smooth', block: 'start' }});
          }}
        }});
      }}
    }});

    document.addEventListener('click', (e) => {{
      if (e.target && e.target.id === 'btn-toggle-past') {{
        showPastToday = !showPastToday;
        apply();
      }} else if (e.target && e.target.id === 'btn-banner-tomorrow') {{
        const tomorrowChip = document.querySelector('#quick-chips .chip[data-time="tomorrow"]');
        if (tomorrowChip) {{
          tomorrowChip.click();
        }}
      }}
    }});

    window.addEventListener('focus', () => {{
      checkDayRollover();
      if (timeFilter === 'today' && !showPastToday) {{
        apply();
      }}
    }});

    document.addEventListener('visibilitychange', () => {{
      if (document.visibilityState === 'visible') {{
        checkDayRollover();
      }}
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

    // --- Community Event & Venue Submission Modal Logic ---
    const submitModal = document.getElementById('submit-event-modal');
    const btnOpenSubmit = document.getElementById('btn-open-submit-modal');
    const btnCloseSubmit = document.getElementById('btn-close-submit-modal');
    const btnCancelSubmit = document.getElementById('btn-cancel-submit');
    const communityForm = document.getElementById('community-event-form');
    const evDateInput = document.getElementById('ev-date');
    const btnQuickFree = document.getElementById('btn-quick-free');
    const evPriceInput = document.getElementById('ev-price');
    const formStatus = document.getElementById('form-submit-status');
    const btnSubmitAction = document.getElementById('btn-submit-action');

    const tabBtnEvent = document.getElementById('tab-btn-event');
    const tabBtnVenue = document.getElementById('tab-btn-venue');
    const modalViewEvent = document.getElementById('modal-view-event');
    const modalViewVenue = document.getElementById('modal-view-venue');
    const modalSubmitTitle = document.getElementById('modal-submit-title');
    const modalSubmitSub = document.getElementById('modal-submit-sub');
    const formVenueStatus = document.getElementById('form-venue-status');
    const suggestVenueForm = document.getElementById('suggest-venue-form');
    const btnCancelVenue = document.getElementById('btn-cancel-venue');
    const btnSubmitVenue = document.getElementById('btn-submit-venue');

    function switchModalTab(tab) {{
      if (tab === 'venue') {{
        if (tabBtnVenue) {{ tabBtnVenue.classList.add('active'); tabBtnVenue.setAttribute('aria-selected', 'true'); }}
        if (tabBtnEvent) {{ tabBtnEvent.classList.remove('active'); tabBtnEvent.setAttribute('aria-selected', 'false'); }}
        if (modalViewVenue) modalViewVenue.style.display = 'block';
        if (modalViewEvent) modalViewEvent.style.display = 'none';
        if (modalSubmitTitle) modalSubmitTitle.textContent = 'Suggest a Venue to Track';
        if (modalSubmitSub) modalSubmitSub.textContent = 'Know a music venue, comedy club, theater, or community space we should automatically scrape?';
        const vnInput = document.getElementById('vn-name');
        if (vnInput) setTimeout(() => vnInput.focus(), 60);
      }} else {{
        if (tabBtnEvent) {{ tabBtnEvent.classList.add('active'); tabBtnEvent.setAttribute('aria-selected', 'true'); }}
        if (tabBtnVenue) {{ tabBtnVenue.classList.remove('active'); tabBtnVenue.setAttribute('aria-selected', 'false'); }}
        if (modalViewEvent) modalViewEvent.style.display = 'block';
        if (modalViewVenue) modalViewVenue.style.display = 'none';
        if (modalSubmitTitle) modalSubmitTitle.textContent = 'Add an Event to NYC Events';
        if (modalSubmitSub) modalSubmitSub.textContent = 'Hosting a show, party, dance, meetup, or know of an event we missed? Submit it below.';
        const evInput = document.getElementById('ev-title');
        if (evInput) setTimeout(() => evInput.focus(), 60);
      }}
    }}

    if (tabBtnEvent) tabBtnEvent.addEventListener('click', () => switchModalTab('event'));
    if (tabBtnVenue) tabBtnVenue.addEventListener('click', () => switchModalTab('venue'));

    function openSubmitModal(initialTab) {{
      if (!submitModal) return;
      submitModal.style.display = 'flex';
      document.body.style.overflow = 'hidden';
      switchModalTab(initialTab === 'venue' ? 'venue' : 'event');
      if (evDateInput && !evDateInput.value) {{
        evDateInput.value = todayISO;
      }}
      if (formStatus) {{
        formStatus.style.display = 'none';
        formStatus.className = 'form-status';
      }}
      if (formVenueStatus) {{
        formVenueStatus.style.display = 'none';
        formVenueStatus.className = 'form-status';
      }}
    }}

    function closeSubmitModal() {{
      if (!submitModal) return;
      submitModal.style.display = 'none';
      document.body.style.overflow = '';
      if (formStatus) formStatus.style.display = 'none';
      if (formVenueStatus) formVenueStatus.style.display = 'none';
    }}

    if (btnOpenSubmit) btnOpenSubmit.addEventListener('click', () => openSubmitModal('event'));
    if (btnCloseSubmit) btnCloseSubmit.addEventListener('click', closeSubmitModal);
    if (btnCancelSubmit) btnCancelSubmit.addEventListener('click', closeSubmitModal);
    if (btnCancelVenue) btnCancelVenue.addEventListener('click', closeSubmitModal);

    if (submitModal) {{
      submitModal.addEventListener('click', (e) => {{
        if (e.target === submitModal) {{
          closeSubmitModal();
        }}
      }});
    }}

    document.addEventListener('keydown', (e) => {{
      if (e.key === 'Escape' && submitModal && submitModal.style.display === 'flex') {{
        closeSubmitModal();
      }}
    }});

    if (btnQuickFree && evPriceInput) {{
      btnQuickFree.addEventListener('click', () => {{
        evPriceInput.value = 'Free';
      }});
    }}

    function injectUserEventIntoDOM(ev) {{
      const dateKey = (ev.date || todayISO).slice(0, 10);
      let daySection = document.querySelector(`.day[data-date="${{dateKey}}"]`);
      if (!daySection) {{
        daySection = document.querySelector(`.day[data-date="${{todayISO}}"]`) || document.querySelector('.day');
      }}
      if (!daySection) return;

      const city = ev.city || 'manhattan';
      let citySection = daySection.querySelector(`.city-section[data-city="${{city}}"]`);
      if (!citySection) {{
        citySection = daySection.querySelector('.city-section') || daySection;
      }}

      let bucketSection = citySection.querySelector('.bucket');
      let targetUl = bucketSection ? bucketSection.querySelector('ul') : null;
      if (!targetUl) {{
        targetUl = daySection.querySelector('ul');
      }}
      if (!targetUl) return;

      let timeStr = 'TBA';
      try {{
        const dt = new Date(ev.date);
        if (!isNaN(dt)) {{
          let h = dt.getHours();
          const m = dt.getMinutes();
          const ampm = h >= 12 ? 'pm' : 'am';
          h = h % 12 || 12;
          timeStr = `${{h}}:${{String(m).padStart(2, '0')}}${{ampm}}`;
        }}
      }} catch (_) {{}}

      const priceTag = ev.price ? `<span class="price ticketed">${{escapeHTML(ev.price)}}</span>` : '<span class="price free">Free</span>';
      const mapsUrl = `https://www.google.com/maps/search/?api=1&query=${{encodeURIComponent(ev.venue + ', NY')}}`;

      let evId = ev.id;
      if (!evId) {{
        const raw = `${{ev.venue || ''}}|${{ev.name || ''}}|${{dateKey}}`.toLowerCase();
        let hash = 0;
        for (let i = 0; i < raw.length; i++) {{
          hash = ((hash << 5) - hash) + raw.charCodeAt(i);
          hash |= 0;
        }}
        evId = 'ev_' + (hash >>> 0).toString(16);
      }}

      const li = document.createElement('li');
      li.className = 'event';
      li.dataset.cat = ev.category || 'other';
      li.dataset.bucket = 'Other';
      li.dataset.venue = ev.venue;
      li.dataset.city = city;
      li.dataset.recur = 'once';
      li.dataset.free = (!ev.price || ev.price.toLowerCase().includes('free')) ? 'true' : 'false';
      li.dataset.guestlist = 'false';
      li.dataset.eventId = evId;

      li.innerHTML = `
        <div class="when">${{timeStr}}</div>
        <div class="what">
          <a href="${{escapeHTML(ev.url || '#')}}" target="_blank" rel="noopener">${{escapeHTML(ev.name)}}</a>
          ${{priceTag}}
          <span class="cat-pill" style="--cat-c:#4ade80; background:#4ade8018; border-color:#4ade8033; color:#4ade80">✨ Added Just Now</span>
          <div class="venue-tag">
            <a class="venue-link" href="${{mapsUrl}}" target="_blank" rel="noopener">${{escapeHTML(ev.venue)}}</a>
            <span class="badge-community">👤 Community</span>
          </div>
        </div>
      `;

      targetUl.prepend(li);
    }}

    function loadLocalCommunityEvents() {{
      try {{
        const raw = localStorage.getItem('nyc_community_events');
        if (!raw) return;
        const events = JSON.parse(raw);
        if (!Array.isArray(events)) return;
        const nowMs = Date.now();
        events.forEach(ev => {{
          try {{
            const evMs = new Date(ev.date).getTime();
            if (evMs >= nowMs - (24 * 3600 * 1000)) {{
              injectUserEventIntoDOM(ev);
            }}
          }} catch (_) {{}}
        }});
      }} catch (_) {{}}
    }}

    if (communityForm) {{
      communityForm.addEventListener('submit', async (e) => {{
        e.preventDefault();

        const hp = communityForm.querySelector('input[name="_hp_company"]');
        if (hp && hp.value) {{
          closeSubmitModal();
          return;
        }}

        const nameInput = document.getElementById('ev-title');
        const venueInput = document.getElementById('ev-venue');
        const dateInput = document.getElementById('ev-date');
        const timeInput = document.getElementById('ev-time');
        const citySelect = document.getElementById('ev-city');
        const categorySelect = document.getElementById('ev-category');
        const priceInput = document.getElementById('ev-price');
        const urlInput = document.getElementById('ev-url');
        const descInput = document.getElementById('ev-desc');

        const name = (nameInput.value || '').trim();
        const venue = (venueInput.value || '').trim();
        const dateVal = (dateInput.value || '').trim();
        const timeVal = (timeInput.value || '19:00').trim();
        const city = citySelect ? citySelect.value : 'manhattan';
        const category = categorySelect ? categorySelect.value : 'other';
        const price = (priceInput.value || '').trim();
        const url = (urlInput.value || '').trim();
        const desc = (descInput.value || '').trim();

        const addressInput = document.getElementById('ev-address');
        const address = (addressInput ? addressInput.value : '').trim();

        if (!name || name.length < 2) {{
          showFormStatus('Please enter an event title (at least 2 characters).', 'error');
          nameInput.focus();
          return;
        }}
        if (!venue || venue.length < 2) {{
          showFormStatus('Please enter a venue or location.', 'error');
          venueInput.focus();
          return;
        }}
        if (!dateVal) {{
          showFormStatus('Please choose an event date.', 'error');
          dateInput.focus();
          return;
        }}
        if (!url || !url.startsWith('http')) {{
          showFormStatus('Please enter a valid website link (starting with http:// or https://).', 'error');
          urlInput.focus();
          return;
        }}

        const isoDate = `${{dateVal}}T${{timeVal}}:00-04:00`;

        const newEvent = {{
          name: name,
          venue: venue,
          date: isoDate,
          url: url,
          category: category,
          city: city,
          address: address,
          price: price || null,
          description: desc,
          _is_community: true,
          submitted_at: new Date().toISOString(),
        }};

        if (btnSubmitAction) {{
          btnSubmitAction.disabled = true;
          const btnText = btnSubmitAction.querySelector('.btn-text');
          const btnSpinner = btnSubmitAction.querySelector('.btn-spinner');
          if (btnText) btnText.style.display = 'none';
          if (btnSpinner) btnSpinner.style.display = 'inline';
        }}

        try {{
          const stored = JSON.parse(localStorage.getItem('nyc_community_events') || '[]');
          stored.push(newEvent);
          localStorage.setItem('nyc_community_events', JSON.stringify(stored.slice(-20)));
        }} catch (_) {{}}

        injectUserEventIntoDOM(newEvent);
        apply();

        const submitEndpoint = window.EVENT_SUBMISSION_ENDPOINT || '';
        if (submitEndpoint) {{
          try {{
            await fetch(submitEndpoint, {{
              method: 'POST',
              headers: {{ 'Content-Type': 'application/json' }},
              body: JSON.stringify(newEvent),
            }});
          }} catch (err) {{
            console.warn('Backend submission failed, kept locally:', err);
          }}
        }}

        showFormStatus('🎉 Event successfully added! It is now live in your feed.', 'success');

        setTimeout(() => {{
          closeSubmitModal();
          communityForm.reset();
          if (btnSubmitAction) {{
            btnSubmitAction.disabled = false;
            const btnText = btnSubmitAction.querySelector('.btn-text');
            const btnSpinner = btnSubmitAction.querySelector('.btn-spinner');
            if (btnText) btnText.style.display = 'inline';
            if (btnSpinner) btnSpinner.style.display = 'none';
          }}
        }}, 1400);
      }});
    }}

    function showFormStatus(msg, type) {{
      if (!formStatus) return;
      formStatus.textContent = msg;
      formStatus.className = `form-status ${{type}}`;
      formStatus.style.display = 'block';
    }}

    function showVenueFormStatus(msg, type) {{
      if (!formVenueStatus) return;
      formVenueStatus.textContent = msg;
      formVenueStatus.className = `form-status ${{type}}`;
      formVenueStatus.style.display = 'block';
    }}

    if (suggestVenueForm) {{
      suggestVenueForm.addEventListener('submit', async (e) => {{
        e.preventDefault();

        const hp = suggestVenueForm.querySelector('input[name="_hp_company"]');
        if (hp && hp.value) {{
          closeSubmitModal();
          return;
        }}

        const nameInput = document.getElementById('vn-name');
        const urlInput = document.getElementById('vn-url');
        const citySelect = document.getElementById('vn-city');
        const catSelect = document.getElementById('vn-category');
        const addrInput = document.getElementById('vn-address');
        const notesInput = document.getElementById('vn-notes');

        const name = (nameInput.value || '').trim();
        const url = (urlInput.value || '').trim();
        const city = citySelect ? citySelect.value : 'manhattan';
        const category = catSelect ? catSelect.value : 'music';
        const address = (addrInput ? addrInput.value : '').trim();
        const notes = (notesInput ? notesInput.value : '').trim();

        if (!name || name.length < 2) {{
          showVenueFormStatus('Please enter a venue or space name.', 'error');
          nameInput.focus();
          return;
        }}
        if (!url || !url.startsWith('http')) {{
          showVenueFormStatus('Please enter a valid website link (starting with http:// or https://).', 'error');
          urlInput.focus();
          return;
        }}

        const newVenue = {{
          type: 'suggest_venue',
          name: name,
          url: url,
          city: city,
          category: category,
          address: address,
          notes: notes,
          submitted_at: new Date().toISOString(),
        }};

        if (btnSubmitVenue) {{
          btnSubmitVenue.disabled = true;
          const btnText = btnSubmitVenue.querySelector('.btn-text');
          const btnSpinner = btnSubmitVenue.querySelector('.btn-spinner');
          if (btnText) btnText.style.display = 'none';
          if (btnSpinner) btnSpinner.style.display = 'inline';
        }}

        try {{
          const stored = JSON.parse(localStorage.getItem('nyc_suggested_venues') || '[]');
          stored.push(newVenue);
          localStorage.setItem('nyc_suggested_venues', JSON.stringify(stored.slice(-20)));
        }} catch (_) {{}}

        const submitEndpoint = window.EVENT_SUBMISSION_ENDPOINT || '';
        if (submitEndpoint) {{
          try {{
            await fetch(submitEndpoint, {{
              method: 'POST',
              headers: {{ 'Content-Type': 'application/json' }},
              body: JSON.stringify(newVenue),
            }});
          }} catch (err) {{
            console.warn('Backend venue submission failed, kept locally:', err);
          }}
        }}

        showVenueFormStatus('🎉 Venue suggestion received! Thank you for helping NYC Events grow.', 'success');

        setTimeout(() => {{
          closeSubmitModal();
          suggestVenueForm.reset();
          if (btnSubmitVenue) {{
            btnSubmitVenue.disabled = false;
            const btnText = btnSubmitVenue.querySelector('.btn-text');
            const btnSpinner = btnSubmitVenue.querySelector('.btn-spinner');
            if (btnText) btnText.style.display = 'inline';
            if (btnSpinner) btnSpinner.style.display = 'none';
          }}
        }}, 1600);
      }});
    }}

    repositionPastBanner();
    updateDayHeadings();
    scheduleMidnightRefresh();
    setInterval(checkDayRollover, 60000);

    loadLocalCommunityEvents();
    hashToState();
    apply();
  </script>
</body>
</html>"""
