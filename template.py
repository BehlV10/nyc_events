"""NYC Events — HTML rendering and template logic."""

import hashlib
import json
import os
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from functools import lru_cache
import html
from html import escape, unescape
from urllib.parse import quote, quote_plus, urlparse

from scrapers import (
    EASTERN,
    CATEGORY_BUCKETS,
    CATEGORY_STYLES,
    DEAL_LINKS,
    STATIC_LINKS,
    category_bucket,
    guess_category,
    infer_music_genre,
    MUSIC_CATEGORIES,
    MUSIC_GENRES,
    fetch_nyc_weather,
    fetch_luckyseat_nyc,
    is_closed_show,
    is_placeholder_or_closed_event,
    is_standing_exhibit,
    is_utility_event,
    is_kid_family_event,
    is_deal_event,
    is_service_ad,
    fix_doubled_url,
    sanitize_event_url,
    BROADWAY_THEATRES,
)
from holiday_themes import HOLIDAY_KEYS, greeting_html, holiday_calendar, holiday_on, holiday_theme_css
from lgbtq import is_lgbtq_event
from light_theme import LIGHT_THEME_CSS
from scrapers import admission_price, mentions_free
from venues_geo import resolve_event_geo
from nyc_geo import TRISTATE_NEEDLES, borough_at, outside_area

# Buckets hidden until the visitor opts in (library ESL classes, job fairs, toddler storytimes).
DEFAULT_UNCHECKED_BUCKETS = {"Classes & Services", "Kids & Family", "Deals & Specials", "Tech & Startups"}


CITY_RULES = [
    ("bronx", (
        "yankee stadium", "bronx zoo", "new york botanical garden", "nybg",
        "wave hill", "woodlawn", "bronx brewery",
        "lehman center for the performing arts", "lehman center", "lehman college",
        "clinton hall bronx", "the bronx", "south bronx", "riverdale", "concourse",
        "fordham", "pelham", "mott haven", "city island", "bronx",
    )),
    ("staten_island", (
        "snug harbor", "st. george theatre", "richmond county bank", "richmond county",
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
        "paragon", "honey's", "honeys", "gabriela", "mood ring", "prospect park alliance", "brooklyn bridge park",
        "brooklyn trivia", "265 4th ave", "269 4th ave", "prospect park board", "jalsa",
        "nyc resistor", "twenty sided store", "twenty sided", "brooklan", "spritzenhaus33", "spritzenhaus",
        "kent ale house", "old stone house", "ethical culture", "whoopsie daisy", "ange noir",
        "city league coffee", "center for fiction", "sip & play", "sip and play", "farm.one", "kings county",
        "royal palms", "barcade brooklyn", "jackbar", "sunshine laundromat", "chilo's", "chilos",
        "brooklyn", "bklyn", "williamsburg", "bushwick", "greenpoint", "dumbo",
        "bed-stuy", "bedford-stuyvesant", "crown heights", "prospect heights",
        "park slope", "gowanus", "red hook", "flatbush", "bay ridge",
        "fort greene", "clinton hill", "cobble hill", "carroll gardens",
        "boerum hill", "prospect park", "sunset park", "coney island", "downtown brooklyn",
    )),
    ("queens", (
        "knockdown center", "tv eye", "trans-pecos", "nowadays", "basement ny", "basement",
        "h0l0", "bar freda", "the windjammer", "windjammer", "gottscheer hall", "gottscheer",
        "topos bookstore", "topos",
        "forest hills stadium", "forest hills", "citi field", "flushing meadows",
        "moma ps1", "museum of the moving image", "socrates sculpture", "noguchi museum", "noguchi",
        "culture lab lic", "culture lab", "fifth hammer", "focal point beer", "focal point",
        "rockaway brewing", "gantry plaza",
        "kaufman astoria", "terraza 7", "terrasa 7", "queens public library", "qpl",
        "q.e.d.", "qed astoria", "qed", "grove 34", "bohemian hall", "bohemian beer garden",
        "the last word", "last word", "astoria swing", "astoria bookshop", "astoria park",
        "the gaf astoria", "the gaf", "small change", "the ditty", "albatross bar", "albatross",
        "sek'end sun", "sekend sun", "madam marie's", "madam marie", "heart of gold",
        "sweet afton", "the wolfhound", "wolfhound", "diamond dogs", "dominie's", "dominies",
        "judy & punch", "judy and punch", "mosaic", "31st avenue open street", "corner bistro east", "on the 7",
        "mom's astoria", "mom’s astoria", "oliver's astoria", "oliver’s astoria",
        "the bier & cheese collective", "bar dalia", "singlecut beersmiths", "singlecut",
        "sanger hall", "the skillman", "sunswick astoria", "sunswick", "alewife brewing", "alewife",
        "donovan's pub", "donovans pub", "claran's", "clarans",
        "34th avenue open street", "diversity plaza", "world's borough bookshop", "worlds borough",
        "flushing town hall", "queens museum", "queens theatre", "queens botanical garden", "queens botanical",
        "queens county farm", "queens farm", "louis armstrong house", "louis armstrong",
        "kupferberg center", "kupferberg", "colden auditorium", "lefrak concert hall",
        "new york hall of science", "hall of science", "nysci", "queens night market",
        "jamaica center for arts", "jcal", "jamaica performing arts", "jpac", "king manor",
        "hunters point south park", "hunters point waterfront", "hunters point",
        "kew & willow", "kew and willow", "astoria food pantry", "cobblestones pub",
        "pete's grill", "the queensboro", "bratwurst und bier", "queens college",
        "cucala dance", "cucala", "queens county", "break bar", "pig beach",
        "astoria trivia", "queens trivia",
        "queens", "astoria", "long island city", "lic", "flushing",
        "ridgewood", "sunnyside", "jackson heights", "woodside",
        "elmhurst", "east elmhurst", "corona", "rego park", "kew gardens", "briarwood",
        "maspeth", "middle village", "glendale", "woodhaven", "ozone park", "richmond hill",
        "howard beach", "broad channel", "fresh meadows", "oakland gardens", "floral park", "glen oaks",
        "college point", "whitestone", "douglaston", "little neck", "bellerose",
        "hollis", "st. albans", "queens village", "laurelton", "rosedale", "cambria heights",
        "bayside", "jamaica, ny", "jamaica ave", "rockaway", "far rockaway", "arverne", "jacob riis", "fort totten",
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
        "lily's", "lily’s", "ella's cafe", "ella’s cafe",
        "broadway", "off-broadway", "theater district", "theatre district",
        "gonzalez y gonzalez", "swing 46", "the back room", "back room",
        "mona's", "monas", "pieces bar", "the stonewall inn", "stonewall inn", "stonewall",
        "trivia a.d.", "trivia ad", "barcade", "galway hooker", "cellar dog", "juilliard",
        "somewhere nowhere", "the dl", "harbor nyc", "harbor new york", "230 fifth", "slate nyc", "slate ny", "nebula",
        "taj lounge", "taj ii", "club cache", "cache", "iguana nyc", "iguana",
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
        "riverside park", "riverside drive", "79th street greenmarket", "amnh",
        "harlem", "morningside heights", "washington heights", "inwood",
        "battery park", "financial district", "fidi", "governors island",
        "columbus circle", "lincoln square", "meatpacking district",
        "manhattan", "new york, ny", "new york city", "new york", "nyc",
    )),
]

# Outer-borough parks and neighborhoods that NYC Parks / Meetup listings name without an address.
_EXTRA_CITY_NEEDLES = {
    "brooklyn": ("canarsie", "flatlands", "marine park", "sheepshead", "dyker", "bensonhurst", "gravesend",
                 "brighton beach", "east new york", "brownsville", "bergen beach", "mill basin", "owls head",
                 "mccarren", "fort greene park", "sunset park", "kaiser park", "floyd bennett"),
    "queens": ("forest park", "alley pond", "cunningham park", "kissena", "fort totten", "juniper valley",
               "baisley", "rockaway beach", "jacob riis", "astoria park", "gantry plaza"),
    "bronx": ("van cortlandt", "crotona", "orchard beach", "soundview", "pelham bay", "ferry point",
              "bronx park", "st. mary's park", "claremont park", "starlight park", "concrete plant park"),
    "staten_island": ("greenbelt", "high rock", "clove lakes", "great kills", "wolfe's pond", "wolfes pond",
                      "tottenville", "silver lake park", "conference house", "freshkills", "fresh kills",
                      "willowbrook park", "lemon creek", "blue heron park", "staten island"),
    "manhattan": ("fort tryon", "highbridge park", "randall's island", "randalls island", "marcus garvey",
                  "tompkins square", "inwood hill", "morningside park", "riverside park", "carl schurz"),
}
CITY_RULES = [(city, tuple(needles) + _EXTRA_CITY_NEEDLES.get(city, ())) for city, needles in CITY_RULES]

CITY_LABELS = {
    "manhattan": "Manhattan",
    "brooklyn": "Brooklyn",
    "queens": "Queens",
    "bronx": "The Bronx",
    "staten_island": "Staten Island",
    "citywide": "Citywide / Location TBA",
    "other": "Outside NYC",
}

CITY_COLORS = {
    "manhattan": "#5d9bff",
    "brooklyn": "#e05a6b",
    "queens": "#f29e4c",
    "bronx": "#4ade80",
    "staten_island": "#a78bfa",
    "citywide": "#7dd3c0",
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
        ("jh_sunnyside", "Jackson Heights, Sunnyside & Woodside", "🌮"),
        ("forest_hills_rockaway", "Forest Hills, Jamaica & Rockaways", "🌳"),
        ("queens_other", "Other Queens", "📍"),
    ],
    "bronx": [
        ("south_bronx", "South Bronx & Concourse", "🎺"),
        ("bronx_other", "Other Bronx", "📍"),
    ],
    "staten_island": [
        ("staten_island_all", "Staten Island", "🚢"),
    ],
    "citywide": [
        ("citywide_all", "Location TBA", "📍"),
    ],
    "other": [
        ("nj", "New Jersey", "🌉"),
        ("long_island", "Long Island", "🏖️"),
        ("westchester_hv", "Westchester & Hudson Valley", "🍂"),
        ("ct", "Connecticut", "⛵"),
        ("outside_other", "Elsewhere", "📍"),
    ]
}

# Shown by default; "other" (outside the five boroughs) is opt-in via its chip.
# "citywide" = in NYC but no borough known (e.g. Meetups that show the venue to members only).
DEFAULT_CITIES = ("manhattan", "brooklyn", "queens", "bronx", "staten_island", "citywide")
_NO_BOROUGH = ("citywide", "other")
_OUTSIDE_LABELS = {slug: name for slug, name, _ in SUBAREAS_BY_CITY["other"]}


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
        if any(k in blob for k in ["greenwich village", "west village", "soho", "noho", "nolita", "comedy cellar", "le poisson rouge", "lpr", "village vanguard", "blue note", "cafe wha", "pubkey", "houston hall", "bleecker", "the bitter end", "duane park", "angelika", "galway hooker", "cellar dog"]):
            return ("Greenwich Village & SoHo", "village_soho")
        if any(k in blob for k in ["midtown", "chelsea", "hell's kitchen", "times square", "broadway", "hudson yards", "the shed", "high line", "madison square garden", "msg", "radio city", "carnegie hall", "sony hall", "town hall", "terminal 5", "irving plaza", "bryant park", "caveat", "asylum", "magnet", "cutting room", "james earl jones", "cort theatre", "lena horne", "helen hayes", "hayes theater", "palace theatre", "barcade chelsea"]):
            return ("Midtown & Chelsea", "midtown_chelsea")
        if any(k in blob for k in ["upper west side", "uws", "lincoln center", "lincoln square", "columbus circle", "david geffen", "alice tully", "merkin", "symphony space", "central park", "summerstage", "beacon theatre", "american folk art", "library for the performing arts", "juilliard"]):
            return ("Upper West & Lincoln Sq", "uws_lincoln")
        if any(k in blob for k in ["upper east side", "ues", "metropolitan museum", "the met", "guggenheim", "comic strip", "hungarian house", "frick", "cooper hewitt", "92ny", "92nd street y"]):
            return ("Upper East & Museums", "ues_museums")
        if any(k in blob for k in ["harlem", "apollo", "washington heights", "inwood", "united palace", "morningside", "columbia university", "smoke jazz"]):
            return ("Harlem & Uptown", "harlem_uptown")
        if any(k in blob for k in ["fidi", "financial district", "tribeca", "battery park", "brookfield", "pier 17", "governors island", "roxy cinema"]):
            return ("FiDi & Tribeca", "fidi_tribeca")
        return ("Other Manhattan", "manhattan_other")

    elif city == "brooklyn":
        if any(k in blob for k in ["williamsburg", "greenpoint", "brooklyn steel", "brooklyn bowl", "music hall of williamsburg", "baby's all right", "warsaw", "pete's candy store", "skinny dennis", "union pool", "nitehawk", "flop house", "national sawdust", "barcade brooklyn", "jackbar", "sunshine laundromat"]):
            return ("Williamsburg & Greenpoint", "williamsburg_gp")
        if any(k in blob for k in ["bushwick", "east williamsburg", "elsewhere", "avant gardner", "brooklyn mirage", "house of yes", "market hotel", "sultan room", "brooklyn monarch", "the meadows"]):
            return ("Bushwick & E. Williamsburg", "bushwick_ew")
        if any(k in blob for k in ["dumbo", "downtown brooklyn", "fort greene", "brooklyn navy yard", "brooklyn academy of music", "bam", "st. ann's", "transit museum", "barclays center"]):
            return ("DUMBO & Downtown BK", "dumbo_downtown")
        if any(k in blob for k in ["park slope", "gowanus", "prospect heights", "the bell house", "littlefield", "union hall", "public records", "brooklyn museum", "prospect park", "barbes", "royal palms"]):
            return ("Park Slope & Gowanus", "park_slope_gowanus")
        if any(k in blob for k in ["bed-stuy", "bedstuy", "crown heights", "flatbush", "kings theatre", "c'mon everybody", "chilo's", "chilos"]):
            return ("Bed-Stuy & Crown Heights", "bedstuy_crown")
        if any(k in blob for k in ["coney island", "bay ridge", "sunset park", "industry city", "ford amphitheater"]):
            return ("Coney Island & Bay Ridge", "south_bk")
        return ("Other Brooklyn", "brooklyn_other")

    elif city == "queens":
        if any(k in blob for k in ["astoria", "lic", "long island city", "q.e.d.", "qed", "moma ps1", "museum of the moving image", "moving image", "socrates", "noguchi", "grove 34", "culture lab", "bohemian hall", "fifth hammer", "focal point", "singlecut", "hunters point", "gantry", "albatross", "the ditty", "judy & punch", "sek'end sun", "madam marie", "sunswick", "last word", "31st avenue", "break bar", "pig beach"]):
            return ("Astoria & Long Island City", "astoria_lic")
        if any(k in blob for k in ["flushing", "ridgewood", "maspeth", "corona", "citi field", "tv eye", "trans-pecos", "nowadays", "h0l0", "knockdown center", "basement", "bar freda", "windjammer", "gottscheer", "topos", "flushing town hall", "queens museum", "queens theatre", "queens botanical", "hall of science", "queens night market", "louis armstrong", "kupferberg"]):
            return ("Flushing & Ridgewood", "flushing_ridgewood")
        if any(k in blob for k in ["jackson heights", "sunnyside", "woodside", "elmhurst", "terraza 7", "terrasa 7", "alewife", "sanger hall", "the skillman", "donovan's", "34th avenue", "diversity plaza", "world's borough"]):
            return ("Jackson Heights, Sunnyside & Woodside", "jh_sunnyside")
        if any(k in blob for k in ["forest hills", "rego park", "kew gardens", "jamaica", "jcal", "rockaway", "far rockaway", "arverne", "bayside", "floral park", "queens farm", "queens county farm", "alley pond", "fort totten"]):
            return ("Forest Hills, Jamaica & Rockaways", "forest_hills_rockaway")
        return ("Other Queens", "queens_other")

    elif city == "bronx":
        if any(k in blob for k in ["south bronx", "concourse", "yankee stadium"]):
            return ("South Bronx & Concourse", "south_bronx")
        return ("Other Bronx", "bronx_other")

    elif city == "staten_island":
        return ("Staten Island", "staten_island_all")

    elif city == "citywide":
        return ("Location TBA", "citywide_all")

    area = outside_area(blob, (geo or {}).get("lat"), (geo or {}).get("lng"))
    return (_OUTSIDE_LABELS[area], area)


def _event_stable_id(e):
    title = (e.get("name") or "").strip().lower()
    venue = (e.get("venue") or e.get("_source_venue") or "").strip().lower()
    date_str = (e.get("date") or "")[:10]
    raw = f"{venue}|{title}|{date_str}"
    return "ev_" + hashlib.md5(raw.encode("utf-8")).hexdigest()[:12]


def _is_tristate(hay):
    # Strip "long island city" so Long Island City, Queens is never mistaken for Long Island (Nassau/Suffolk)
    h = f" {hay.lower()} ".replace("long island city", "")
    for n in TRISTATE_NEEDLES:
        if n in h:
            return True
    return False


def _city_from_zip(hay):
    m = re.search(r"\b(10[0-2]\d{2}|103\d{2}|104\d{2}|112\d{2}|1100[45]|11[1346]\d{2})\b", hay)
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


def _event_city(venue, source, geo=None, event=None):
    """Borough for an event. A map pin decides it when there is one (point-in-polygon against
    the borough boundaries; a pin outside the city is "other"). Without a pin, the event's own
    venue/address/neighborhood text is matched first and the source's name only as a last
    resort (a feed called "NYC Parks ..." used to put every unaddressed park event in
    Manhattan via the "nyc" needle)."""
    if geo and geo.get("lat") is not None and geo.get("lng") is not None:
        own = f"{venue or ''} {(event or {}).get('address') or ''}".lower()
        if not _is_tristate(own):
            zc = _city_from_zip(own)
            if zc:
                return zc  # an explicit ZIP beats a pin a few meters across a border (Wyckoff Ave)
            m = re.search(r"\b(brooklyn|queens|bronx|staten island|manhattan)\s*,\s*(?:ny|new york)\b", own)
            if m:
                return m.group(1).replace(" ", "_")  # "Knockdown Center (Queens, NY)"
        return borough_at(geo["lat"], geo["lng"]) or "other"
    city = _event_city_from(venue, "", geo, event)
    if city == "citywide" and (event or {}).get("borough") in CITY_LABELS:
        return event["borough"]  # the feed's own borough/area (DoNYC venue area, geocoded address)
    if city == "citywide" and source:
        city = _event_city_from(venue, source, geo, event)
    return city


def _event_city_from(venue, source, geo=None, event=None):
    v = (venue or "").strip().lower()
    hay = f"{v} {(source or '').strip().lower()}"
    if geo:
        hay = f"{hay} {(geo.get('neighborhood') or '').lower()} {(geo.get('address') or '').lower()}"
    if event:
        hay = f"{hay} {(event.get('neighborhood') or '').lower()} {(event.get('address') or '').lower()} {(event.get('location') or '').lower()}"
        if not v or v in ("nyc community location", "tba", "tbd", "various") or v.startswith("nyc meetup"):
            hay = f"{hay} {(event.get('name') or '').lower()}"
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
    return "citywide"  # in NYC as far as we know, borough unknown


def _maps_link(venue, city):
    if not venue:
        return ""
    if city in _NO_BOROUGH:
        return f"https://www.google.com/maps/search/?api=1&query={quote(venue)}"
    label = CITY_LABELS.get(city)
    v_lower = venue.lower()
    # If the venue already contains address components or borough names, do not append redundant labels
    if not label or f", {label.lower()}" in v_lower or f"({label.lower()})" in v_lower or ", ny" in v_lower or " new york" in v_lower:
        return f"https://www.google.com/maps/search/?api=1&query={quote(venue)}"
    return f"https://www.google.com/maps/search/?api=1&query={quote(f'{venue}, {label}, NY')}"


# Activities that are usually free ("open mic", "board games", "run club"). Only a hint: the venue
# may still charge, so a listed price, a ticket link or an admission-only venue outweighs it.
_FREE_ACTIVITY_RE = re.compile(
    r"\b("
    r"guestlist|"
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
    r"run clubs?"
    r")\b",
    re.IGNORECASE,
)

# Sites that sell paid tickets, so a missing price there never means free ("Iliza Shlesinger:
# Free Nights & Weekends" is a tour name).
_PAID_SELLER_RE = re.compile(
    r"(?:^|[/.])(?:ticketmaster|livenation|axs|ticketweb|etix|seetickets|dice\.fm|tixr|showclix|prekindle|"
    r"holdmyticket|eventim|seatgeek|stubhub|vividseats|telecharge|ovationtix)\.",
    re.IGNORECASE,
)
# Any ticketing page, free or paid; enough to doubt a free guess drawn from an activity word.
_TICKET_LINK_RE = re.compile(
    r"(?:^|[/.])(?:eventbrite|tickettailor|simpletix|ticketleap|brownpapertickets|humanitix|universe|ludus|"
    r"seatengine|eventcombo|withfriends)\.|//tickets?\.|/tickets?(?:[/?#-]|$)|/checkout|/buy-tickets",
    re.IGNORECASE,
)
# Places where an activity is included with paid admission (storytime at a children's museum).
_ADMISSION_VENUES = ("children's museum", "childrens museum", "museum of natural history", "hall of science",
                     "aquarium", "zoo", "botanic", "intrepid", "legoland")

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

    # Another listing of the same event names a price ("$5" on the venue's page).
    alts = e.get("_alt_sources") or []
    if not price and any(re.search(r"\$\s?[1-9]", a.get("price") or "") for a in alts):
        return False

    name = (e.get("name") or "").lower()
    desc = (e.get("description") or "").lower()
    source = (e.get("_source_venue") or "").lower()
    venue = (e.get("venue") or "").lower()
    urls = [e.get("url") or ""] + [a.get("url") or "" for a in alts]

    if any(_PAID_SELLER_RE.search(u) for u in urls):
        return False

    if any(k in source or k in venue for k in [
        "library", "nypl", "bpl", "parks free", "summerstage", "bryant park",
        "greenmarket", "union square greenmarket", "garibaldi plaza", "sunset salsa",
        "pa' la calle", "pa la calle", "open streets", "abolitionist place",
        "hunters point waterfront", "domino park waterfront"
    ]):
        return True

    if mentions_free(name):
        return True

    if any(p in desc for p in _FREE_DESC_PHRASES):
        return True

    if _FREE_ACTIVITY_RE.search(name):
        sells_tickets = any(_TICKET_LINK_RE.search(u) for u in urls)
        charges_admission = any(k in venue or k in source for k in _ADMISSION_VENUES)
        return not (admission_price(desc) or sells_tickets or charges_admission)

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
    elif city in _NO_BOROUGH:
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
      <stop offset="0%" style="stop-color: var(--sky1, #0c0926)"/>
      <stop offset="35%" style="stop-color: var(--sky2, #31124d)"/>
      <stop offset="65%" style="stop-color: var(--sky3, #b8325a)"/>
      <stop offset="85%" style="stop-color: var(--sky4, #f5793a)"/>
      <stop offset="100%" style="stop-color: var(--sky5, #ffc355)"/>
    </linearGradient>
    <radialGradient id="moon" cx="0.5" cy="0.5" r="0.5">
      <stop offset="0%" stop-color="#fff8e7"/>
      <stop offset="100%" stop-color="#fff8e7" stop-opacity="0"/>
    </radialGradient>
    <linearGradient id="water" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" style="stop-color: var(--water1, #142852)"/>
      <stop offset="100%" style="stop-color: var(--water2, #071124)"/>
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
    if e.get("_time_unknown"):
        return "Time TBA"
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
            # Venue is part of the key: a group posting the same title at a different bar each
            # week isn't one recurring event.
            key = (name, e.get("_source_venue") or "", (e.get("venue") or "").strip().lower())
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
    t = unescape(title or "").lower().strip()

    # 1. Strip venue name from title if title starts with venue
    if venue:
        v_clean = re.sub(r"[^a-z0-9]+", " ", venue.lower()).strip()
        v_core = re.sub(r"^the\s+", "", v_clean).strip()
        t_clean = re.sub(r"[^a-z0-9]+", " ", t).strip()
        for v_cand in [v_clean, v_core]:
            if v_cand and len(v_cand) >= 4 and t_clean.startswith(v_cand):
                t = t_clean[len(v_cand):].strip()
                break

    # 2. Strip leading generic words and prefixes
    t = re.sub(r"^(?:an evening with|an evening of|a night with|in conversation with)\s+", "", t, flags=re.I)
    t = re.sub(r"^(?:no cover\s+(?:drag\s+)?|free\s+)", "", t, flags=re.I)
    t = re.sub(r"^(?:live|traditional|weekly|annual)\s+", "", t, flags=re.I)
    t = re.sub(r"^(?:a|an)\s+", "", t, flags=re.I)

    # Strip leading author/creator possessives when the remainder is a real title
    # ("Harper Lee's To Kill a Mockingbird" -> "to kill a mockingbird")
    m_poss = re.match(r"^(?:[a-z\.\'\-]+\s+){0,3}[a-z\.\'\-]+(?:'s|’s|')\s+(.+)$", t, flags=re.I)
    if m_poss:
        rem = m_poss.group(1).strip()
        if len(rem.split()) >= 2 or len(rem) >= 8:
            t = rem

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
            if sep in (":", " - ", " – ", " — ") and any(left.endswith(suff) for suff in GENERIC_CATEGORY_SUFFIXES):
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
    t = re.sub(r"^(?:a|an)\s+", "", t, flags=re.I)
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
    primary_url = (e.get("url") or "").lower()
    alts = e.get("_alt_sources") or []
    has_seatgeek = "seatgeek.com" in primary_url or any("seatgeek.com" in (a.get("url") or "").lower() for a in alts)
    links = []
    if not has_seatgeek:
        sg_url = f"https://seatgeek.com/search?search={encoded_q}"
        links.append(f'<a href="{escape(sg_url)}" target="_blank" rel="noopener">SeatGeek</a>')
    sh_url = f"https://www.stubhub.com/search?q={encoded_q}"
    links.append(f'<a href="{escape(sh_url)}" target="_blank" rel="noopener">StubHub</a>')
    tp_url = f"https://www.tickpick.com/search/?q={encoded_q}"
    links.append(f'<a href="{escape(tp_url)}" target="_blank" rel="noopener">TickPick</a>')
    label = "compare prices" if e.get("price") else "tickets"
    return f'<span class="compare-tickets">{label}: {" · ".join(links)}</span>'


def _url_priority(url, source=None):
    """Calculate priority score for selecting primary event link.

    Hierarchy:
      10 = Direct venue websites & primary box offices (thestonenyc.com, boweryballroom.com,
           dice.fm, axs.com, telecharge.com, shotgun.live, seetickets.us, etix.com, tixr.com,
           ovationtix.com, ra.co, etc.)
       8 = Ticketmaster / Live Nation / Ticketweb / Universe official ticketing
       5 = Eventbrite
       3 = Meetup
       2 = SeatGeek (resale / secondary aggregator)
       1 = Aggregators / search fallbacks (doNYC, google search)
       0 = Blank / missing
    """
    if not url:
        return 0
    u = url.lower()
    s = (source or "").lower()
    if "donyc.com" in u or "google.com/search" in u:
        return 1
    if "seatgeek.com" in u or "seatgeek" in s:
        return 2
    if "meetup.com" in u or "meetup" in s:
        return 3
    if "eventbrite.com" in u or "eventbrite" in s:
        return 5
    if "lu.ma" in u or "luma" in s:
        return 7
    if any(k in u for k in ("ticketmaster.com", "livenation.com", "ticketweb.com", "universe.com")) or "ticketmaster" in s:
        return 8
    return 10


def _source_priority(s):
    return _url_priority(None, source=s)


def _source_display_label(src, url=None):
    if url:
        ts = _ticket_source_name(url)
        if ts != "Official Site":
            return ts
    s = (src or "").strip()
    s_low = s.lower()
    if "ticketmaster" in s_low:
        return "Ticketmaster"
    if "seatgeek" in s_low:
        return "SeatGeek"
    if "eventbrite" in s_low:
        return "Eventbrite"
    if "luma" in s_low or "lu.ma" in s_low:
        return "Luma"
    if "donyc" in s_low:
        return "doNYC"
    return s or "Tickets"


# Query parameters that name the event itself ("book?perfcode=931", "?eventid=206566108"). Without
# them every event on such a site has the same URL and they'd all merge.
_EVENT_ID_PARAMS = {"evt", "eid", "eventid", "event_id", "event", "id", "perfcode", "performance", "showid",
                    "show_id", "occurrence", "e"}


def _clean_event_url(u):
    if not u or not isinstance(u, str):
        return ""
    try:
        q = urlparse(u.strip()).query
    except ValueError:
        q = ""
    keep = sorted(p for p in q.split("&") if p.split("=", 1)[0].lower() in _EVENT_ID_PARAMS)
    u = re.sub(r"[?#].*$", "", u).strip().rstrip("/")
    if keep and u:
        return u + "?" + "&".join(keep)
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
        return "Official Site"
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
    if "lu.ma" in low or "luma" in low:
        return "Luma"
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
    if "tickpick.com" in low:
        return "TickPick"
    if "stubhub.com" in low:
        return "StubHub"
    if "donyc.com" in low:
        return "doNYC"
    if "skipthesmalltalk.com" in low:
        return "Skip the Small Talk"
    return "Official Site"


_TITLE_FILLER = {"w", "with", "and", "the", "a", "an", "live", "feat", "ft", "presents", "presented", "by"}
_GENERIC_TITLE_VARIANTS = {"nyc", "newyork", "brooklyn", "queens", "manhattan", "tour", "usa", "concert", "show", "live"}
_VENUE_GENERIC_WORDS = {
    "the", "at", "in", "of", "and", "new", "york", "nyc", "ny", "manhattan", "brooklyn", "queens", "bronx",
    "staten", "island", "public", "library", "branch", "main", "central", "west", "east", "north", "south",
    "university", "college", "school", "church", "museum", "theatre", "theater", "hall", "center", "centre",
    "club", "bar", "pub", "cafe", "café", "lounge", "room", "house", "studio", "brewing", "brewery", "company",
    "co", "downtown", "presented", "by", "music", "arts", "art", "park", "street", "st", "ave", "avenue",
    # building-type and neighborhood words shared by unrelated places
    "square", "sq", "arena", "stadium", "gymnasium", "gym", "ice", "rink", "field",
}


def _title_variants(title):
    """Compact spellings of a title for cross-source duplicate detection: the full title and,
    when it has an organizer/series prefix ("MoMA: ...", "X presents: ...", "BAM - ..."),
    the part after it. Each variant is lowercase alphanumerics with filler words removed."""
    t = unescape(title or "").lower()
    t = re.sub(r"[\(\[][^\)\]]*[\)\]]", " ", t)          # (18+), [SOLD OUT]
    t = re.sub(r"\s+(?:at|@)\s+(?:the\s+)?[\w'\s\.&-]+$", "", t)  # trailing "at Brooklyn Steel"
    t = re.sub(r"\s*[-–—|,]\s*(?:nyc|new york(?: city)?|brooklyn|queens|manhattan)(?:,?\s*ny)?\s*$", "", t)
    # Broadway listings: "MJ - The Musical - New York", "Six: The Musical", "Hamilton on Broadway"
    t = re.sub(r"\s*[-–—:|,]?\s*(?:the\s+|a\s+new\s+)?musical\s*$", "", t)
    t = re.sub(r"\s+(?:on\s+)?broadway\s*$|\s+tickets\s*$", "", t)
    pieces = [t]
    m = re.search(r"\bpresents?:?\s+(.+)$", t)
    if m:
        pieces.append(m.group(1))
    for sep in (":", " - ", " – ", " — ", " | "):
        if sep in t:
            # Only the part after the prefix: the prefix itself is shared by unrelated events.
            pieces.append(t.split(sep, 1)[1])
    out = []
    for piece in pieces:
        toks = [w for w in re.findall(r"[^\W_]+", piece) if w not in _TITLE_FILLER]  # keeps "qué"
        c = "".join(toks)
        if c and c not in _GENERIC_TITLE_VARIANTS:
            out.append(c)
    return out


# Per-event memo for the O(n^2) duplicate scan. Keys are dropped when a merge rewrites an
# event's name/venue and stripped from events when _merge_duplicates returns.
_MEMO_KEYS = ("_m_geo", "_m_vwords", "_m_head", "_m_variants")


def _memo(e, key, fn):
    if key not in e:
        e[key] = fn()
    return e[key]


def _cached_geo(e):
    return _memo(e, "_m_geo", lambda: resolve_event_geo(e))


def _venue_words(e):
    return _memo(e, "_m_vwords", lambda: {re.sub(r"s$", "", x) for x in re.findall(r"\w+", (e.get("venue") or "").lower()) if len(x) >= 2} - _VENUE_GENERIC_WORDS)


def _cached_head(e):
    return _memo(e, "_m_head", lambda: _normalize_title_head(e.get("name") or "", venue=e.get("venue")))


def _cached_variants(e):
    return _memo(e, "_m_variants", lambda: _title_variants(e.get("name") or ""))


def _same_physical_venue(e1, e2):
    """Stricter venue check than _merge_duplicates' _venue_match: same geo pin, or a shared
    distinctive word ("Nowadays", "Elsewhere") — not just "Public Library" or "Music Hall"."""
    if e1.get("_venue_unknown") or e2.get("_venue_unknown"):
        return True
    if _venue_words(e1) & _venue_words(e2):
        return True
    g1, g2 = _cached_geo(e1), _cached_geo(e2)
    if g1 and g2:
        return abs(g1["lat"] - g2["lat"]) < 0.0015 and abs(g1["lng"] - g2["lng"]) < 0.0015
    return False


_RSVP_HOSTS = ("lu.ma", "luma.com", "eventbrite.", "meetup.com", "partiful.com", "heylo.com",
               "dice.fm", "posh.vip", "ticketmaster.", "seatgeek.com", "axs.com", "tixr.com")


def _is_event_specific_link(url):
    """An RSVP/ticket page for one event (lu.ma/8ugz1m1n, eventbrite.com/e/...)."""
    try:
        u = urlparse((url or "").strip())
    except ValueError:
        return False
    path = u.path.strip("/")
    return any(h in u.netloc.lower() for h in _RSVP_HOSTS) and len(path) >= 6 and bool(re.search(r"\d|/", path))


def _is_generic_link(url):
    """A site root or listing page rather than an event page: "x.com", "x.com/events/"."""
    try:
        u = urlparse((url or "").strip())
    except ValueError:
        return True
    if not u.netloc:
        return True
    path = u.path.strip("/").lower()
    return path in ("", "events", "calendar", "event-calendar", "upcoming-events", "whats-on") and not u.query


def _titles_equivalent(a, b):
    """True when any variant pair is identical, or one is a prefix of the other (>= 6 chars)."""
    for x in a:
        for y in b:
            if x == y and len(x) >= 2:  # "MJ" vs "MJ (NY)"; callers already require same venue/time
                return True
            short, long_ = (x, y) if len(x) <= len(y) else (y, x)
            if len(short) >= 6 and long_.startswith(short):
                return True
    return False


_ATTRACTION_TOUR_RE = re.compile(
    r"\b(museum|stadium|brewery|distillery|historic(?:al)?|walking|architecture|neighborhood|food|ghost|harbor|backstage)\s+tours?\b", re.I)


def _is_attraction_tour(e):
    """Hourly-departure tours (museum, walking, brewery...) that should collapse to one daily listing."""
    if (e.get("category") or "").lower() in ("music", "comedy", "clubbing"):
        return False
    return bool(_ATTRACTION_TOUR_RE.search(e.get("name") or ""))


def _event_local_time(e):
    t = e.get("_time")
    if t is None and e.get("date"):
        try:
            t = datetime.fromisoformat(str(e["date"]).replace("Z", "+00:00"))
        except ValueError:
            return None
    if t is None:
        return None
    t = t.replace(tzinfo=EASTERN) if t.tzinfo is None else t.astimezone(EASTERN)
    e["_time"] = t
    return t


_TICKET_SELLER_RE = re.compile(r"ticketmaster\.com|seatgeek\.com|axs\.com|livenation\.com|telecharge\.com|stubhub\.com|tickpick\.com|vividseats\.com", re.I)
_RSVP_HOST_RE = re.compile(r"meetup\.com|partiful\.com|lu\.ma|luma\.com", re.I)
_STEP4_STOPWORDS = {
    "free", "night", "show", "shows", "live", "session", "comedy", "party", "dance", "dancing", "class",
    "social", "meetup", "open", "with", "presents", "featuring", "late", "early", "edition", "special",
}


_AGGREGATOR_SOURCE_NAMES = {
    "donyc citywide", "the skint nyc", "ticketmaster nyc", "seatgeek nyc", "dice.fm nyc",
    "resident advisor nyc", "nyc parks department", "nyc parks free public events", "meetup nyc",
    "nyc broadway lotteries", "luckyseat nyc broadway lotteries", "songkick nyc concerts",
    "partiful nyc", "luma nyc", "nyc parks hikes, rangers & outdoor programs", "secret nyc",
    "greenpointers brooklyn", "nyc for free (pop-ups & experiences)", "community submissions",
}


def _is_aggregator_source(source, venue_url=None):
    """True for citywide feeds and keyword searches, which list events but don't present them,
    so their names must never appear as a "presented by" tag."""
    s = (source or "").strip().lower()
    u = (venue_url or "").lower()
    return (s in _AGGREGATOR_SOURCE_NAMES or s.startswith(("eventbrite: ", "meetup: "))
            or "/d/ny--" in u or "/find/?keywords=" in u or "donyc.com/events" in u)


_TITLE_WORD_STOP = {"the", "a", "an", "at", "and", "of", "in", "with", "for", "live", "nyc", "new", "york", "presents",
                    "feat", "ft", "w", "tickets", "event", "i", "to", "on", "by"}


def _title_words(title):
    t = re.sub(r"[\(\[][^\)\]]*[\)\]]", " ", unescape(title or "").lower())
    return {w for w in re.findall(r"[^\W_]+", t) if w not in _TITLE_WORD_STOP and len(w) > 1}


_UNRELATED_STOP = {"night", "show", "tour", "featuring", "events"}


def _titles_unrelated(t1, t2):
    """No meaningful word in common, and not just a spacing/punctuation variant ("half•alive"/"halfalive")."""
    if not t1 or not t2:
        return False
    w1 = {w for w in _title_words(t1) if len(w) > 2} - _UNRELATED_STOP
    w2 = {w for w in _title_words(t2) if len(w) > 2} - _UNRELATED_STOP
    if not w1 or not w2 or (w1 & w2):
        return False
    squash = lambda t: re.sub(r"[^a-z0-9]+", "", unescape(t).lower())
    s1, s2 = squash(t1), squash(t2)
    return not (s1 and s2 and (s1 in s2 or s2 in s1))


_SHARED_WORD_STOP = _TITLE_WORD_STOP | _UNRELATED_STOP | {
    "this", "that", "your", "our", "you", "all", "from", "day", "edition", "special", "guest", "guests", "sold",
    "out", "free", "party", "series", "club", "group", "meeting", "session", "nights", "music", "concert",
    "festival", "celebration", "annual", "part", "vs", "mens", "womens", "presented", "conversation", "talk",
    "book", "author", "premiere", "world", "american", "brooklyn", "manhattan", "queens", "bronx", "class",
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday", "weekly", "monthly",
}


@lru_cache(maxsize=None)
def _fold(t):
    return unicodedata.normalize("NFKD", unescape(t or "")).encode("ascii", "ignore").decode().lower()


def _distinctive_words(title, venue_words=()):
    return {w for w in re.findall(r"[a-z]+", _fold(title))
            if len(w) >= 3 and w not in _SHARED_WORD_STOP and w not in venue_words}


# Numbers that describe the night rather than the show: door ages ("18+", "21 and over"), dates
# ("11/06", "December 11th") and times ("7:30", "8pm").
_NOT_A_TITLE_NUMBER = re.compile(
    r"\b\d{2}\s*(?:\+|and (?:over|up)|& (?:over|up))|\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b|\b\d{1,2}(?:st|nd|rd|th)\b|"
    r"\b\d{1,2}(?::\d{2})?\s*(?:am|pm)\b|\b\d{1,2}:\d{2}\b")


@lru_cache(maxsize=None)
def _title_numbers(title):
    """Numbers in a title other than years: "Round 3", "Day 2", "No. 5"."""
    return frozenset(n for n in re.findall(r"\d+", _NOT_A_TITLE_NUMBER.sub(" ", _fold(title)))
            if not re.fullmatch(r"(?:19|20)\d\d", n))


def _numbers_conflict(t1, t2):
    """Both titles carry numbers and they differ: "Ages 27-37" vs "Ages 36-48", "Round 3" vs "Round 5"."""
    n1, n2 = _title_numbers(t1), _title_numbers(t2)
    # Neither contains the other: "Brutalismus 3000" vs "Brutalismus 3000 (18+)" is the same show
    # with an extra detail, not a different one.
    return bool(n1 and n2 and not (n1 <= n2 or n2 <= n1))


def title_word_freq(events):
    """How many distinct titles each distinctive word appears in, across the whole calendar."""
    freq = Counter()
    for t in {_fold(e.get("name")).strip() for e in events}:
        freq.update(_distinctive_words(t))
    return freq


def _same_event_retitled(e1, e2, freq):
    """Two sources, same venue, same time, titled differently: "A Conversation with Ada Limon"
    (the venue) and "SOLD OUT! Ada Limon: The Hurting Kind" (the bookstore). Requires shared words
    that are rare across the calendar, so "Sunday Jazz Brunch" and "Sunday Drag Brunch" never merge."""
    t1, t2 = e1.get("_time"), e2.get("_time")
    if not t1 or not t2 or abs((t1 - t2).total_seconds()) > 30 * 60:
        return False
    if (e1.get("_source_venue") or "") == (e2.get("_source_venue") or ""):
        return False
    if (t1.hour, t1.minute) == (0, 0) or (t2.hour, t2.minute) == (0, 0):
        return False
    vw1, vw2 = _venue_words(e1), _venue_words(e2)
    if not (vw1 & vw2) or _numbers_conflict(e1.get("name"), e2.get("name")):
        return False
    vw = vw1 | vw2 | {w.rstrip("s") for w in vw1 | vw2}
    shared = _distinctive_words(e1.get("name"), vw) & _distinctive_words(e2.get("name"), vw)
    if len(shared) >= 3:
        return True
    rare = [w for w in shared if freq.get(w, 0) <= 6]
    if len(shared) == 2 and rare:
        return True
    return len(shared) == 1 and len(rare) == 1 and len(rare[0]) >= 5 and freq.get(rare[0], 0) <= 4


def _pill_slug(cat):
    return re.sub(r"[^a-z0-9]+", "-", (cat or "other").lower()).strip("-") or "other"


def _compact_li(html_str):
    """Drop the source indentation between an event's block-level children."""
    return re.sub(r"\n\s*", "", html_str)


def _pill_css():
    """One rule per category/genre colour instead of an inline style on ~20k pills."""
    rules = []
    for cat, (color, _icon) in CATEGORY_STYLES.items():
        rules.append(f".pc-c-{_pill_slug(cat)}{{--cat-c:{color};background:{color}18;border-color:{color}33;color:{color}}}")
    for key, info in MUSIC_GENRES.items():
        c = info["color"]
        rules.append(f".pc-g-{key}{{--cat-c:{c};background:{c}18;border-color:{c}33;color:{c}}}")
    return "".join(rules)


def _merge_duplicates(events, word_freq=None):
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

    def _is_generic_feed(ev):
        if not isinstance(ev, dict):
            return False
        v_url = (ev.get("venue_url") or "").lower()
        if "/find/?keywords=" in v_url or "/d/ny--" in v_url or "donyc.com/events" in v_url:
            return True
        src = (ev.get("_source_venue") or ev.get("source") or "").strip().lower()
        if src in generic_sources:
            return True
        if any(src.startswith(p) for p in ("meetup: nyc", "meetup: brooklyn", "meetup: queens")) and ("/find" in v_url or not v_url):
            return True
        return False

    def _source_score(ev):
        spec = 0 if _is_generic_feed(ev) else 20
        prio = _url_priority(ev.get("url"), ev.get("_source_venue") or ev.get("source"))
        return spec + prio

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
        # Noon vs an evening show is a broker's untimed placeholder (e.g. SeatGeek 12 PM default)
        if ((t1.hour == 12 and t1.minute == 0 and t2.hour >= 16) or
                (t2.hour == 12 and t2.minute == 0 and t1.hour >= 16)):
            return False
        # Hourly departures of the same attraction tour collapse into one daily listing
        if _is_attraction_tour(e1) and _is_attraction_tour(e2):
            return False
        diff_mins = abs((t1 - t2).total_seconds()) / 60.0
        s1 = (e1.get("_source_venue") or e1.get("source") or "").lower()
        s2 = (e2.get("_source_venue") or e2.get("source") or "").lower()
        # Same source >= 45 min apart: separate sets (7:00 and 9:30), unless one listing comes from a
        # ticket reseller, whose times are often doors or off by an hour.
        resale = any(h in f"{e1.get('url')} {e2.get('url')}".lower() for h in (
            "eventschaser.com", "vividseats.com", "stubhub.com", "ticketnetwork.com", "tickpick.com"))
        if s1 and s1 == s2 and diff_mins >= 45 and not resale:
            return True
        if s1 != s2 and diff_mins <= 90:
            return False
        if diff_mins > 90:
            return True
        return False

    def _separate_listings(e1, e2):
        """A source's own calendar with a page for each: it lists them as two events, so never
        merge them on loose venue/time/keyword similarity. Citywide feeds and promoters do post
        one event twice ("Wicked" / "Wicked New York Tickets"), so this doesn't apply to them."""
        s1 = (e1.get("_source_venue") or "").lower()
        u1, u2 = (e1.get("url") or "").rstrip("/"), (e2.get("url") or "").rstrip("/")
        if not (s1 and s1 == (e2.get("_source_venue") or "").lower() and u1 and u2 and u1 != u2):
            return False
        if (_is_generic_feed(e1) or _is_aggregator_source(s1, e1.get("venue_url"))
                or s1.startswith(("allevents", "luma", "songkick"))):
            return False
        if {(e1.get("category") or "").lower(), (e2.get("category") or "").lower()} <= {"clubbing", "party"}:
            return False
        # A shared fallback (the source's calendar page) is not an event page
        return u1 != (e1.get("venue_url") or "").rstrip("/") and u2 != (e2.get("venue_url") or "").rstrip("/")

    def _far_apart(e1, e2):
        """Same title at two places we can locate, over half a mile apart: separate events
        ("Trivia Night" at two bars, a citywide program at two museums)."""
        g1, g2 = _cached_geo(e1), _cached_geo(e2)
        if not (g1 and g2) or g1.get("lat") is None or g2.get("lat") is None:
            return False
        dlat = (g1["lat"] - g2["lat"]) * 69.0
        dlng = (g1["lng"] - g2["lng"]) * 52.5  # miles per degree of longitude at NYC's latitude
        return (dlat * dlat + dlng * dlng) ** 0.5 > 0.5

    def _venue_match(v1, v2, e1, e2):
        if not v1 or not v2:
            return True
        v1_low = v1.lower()
        v2_low = v2.lower()
        if v1_low in generic_sources or v2_low in generic_sources or _is_generic_feed(e1) or _is_generic_feed(e2):
            return True
        if v1_low == v2_low:
            return True
        generic_vwords = {
            "the", "at", "in", "of", "and", "new", "york", "nyc", "manhattan", "brooklyn", "queens", "bronx",
            "theatre", "theater", "tavern", "pub", "bar", "lounge", "brewery",
            "brewing", "cafe", "café", "center", "hall", "club", "studio", "house", "room",
            # every library shares these; branches are told apart by their own names
            "public", "library", "branch", "main", "central", "square", "sq", "arena", "stadium",
        }
        # len >= 2: the "s" of "Rudy's" / "Lou's" is not a shared venue word
        w1 = {re.sub(r"s$", "", w) for w in re.findall(r"\w+", v1_low) if len(w) >= 2} - generic_vwords
        w2 = {re.sub(r"s$", "", w) for w in re.findall(r"\w+", v2_low) if len(w) >= 2} - generic_vwords
        if w1 and w2 and (w1 & w2):
            return True
        if e1 and e2:
            g1 = _cached_geo(e1)
            g2 = _cached_geo(e2)
            if g1 and g2:
                if g1.get("venue") and g1.get("venue") == g2.get("venue"):
                    return True
                if abs(g1["lat"] - g2["lat"]) < 0.0015 and abs(g1["lng"] - g2["lng"]) < 0.0015:
                    return True
        return False

    for e in events:
        # Normalize ticket_url
        t_url = e.get("ticket_url")
        if t_url and t_url != e.get("url"):
            p_ticket = _url_priority(t_url)
            p_curr = _url_priority(e.get("url"), e.get("_source_venue") or e.get("source"))
            raw_src = e.get("_source_venue") or e.get("source") or e.get("venue") or "source"
            if p_ticket > p_curr:
                old_u = e.get("url")
                old_s = _source_display_label(raw_src, old_u)
                e["url"] = t_url
                e.setdefault("_alt_sources", [])
                if old_u and not any(a.get("url") == old_u for a in e["_alt_sources"]):
                    e["_alt_sources"].append({"venue": old_s, "source": raw_src, "url": old_u, "price": e.get("price")})
            else:
                src_label = _source_display_label(raw_src, t_url)
                e.setdefault("_alt_sources", [])
                if not any(a.get("url") == t_url for a in e["_alt_sources"]):
                    e["_alt_sources"].append({"venue": src_label, "source": raw_src, "url": t_url, "price": e.get("price")})

        raw_name = unescape(e.get("name") or "").strip()
        e["name"] = raw_name
        full = re.sub(r"[^a-z0-9]+", " ", raw_name.lower()).strip()
        venue_str = e.get("venue") or ""
        head = _cached_head(e)
        venue = venue_str.lower()
        curl = _clean_event_url(e.get("url"))
        # A link that is just the source's listing page (calendar fallback) identifies the
        # source, not the event: many distinct events share it, so it can't anchor a match.
        if curl and curl == _clean_event_url(e.get("venue_url")):
            curl = ""

        match = None
        # 0. Canonical specific URL match check
        if curl and curl in seen_url:
            for cand in seen_url[curl]:
                s_cand = (cand.get("_source_venue") or cand.get("source") or "").lower()
                s_cur = (e.get("_source_venue") or e.get("source") or "").lower()
                if s_cand != s_cur or not _is_different_show(e, cand):
                    match = cand
                    break

        # 1. Exact match check
        if not match and full and len(full) >= 4 and full in seen_exact:
            for cand in seen_exact[full]:
                if not _is_different_show(e, cand) and not _far_apart(e, cand):
                    match = cand
                    break

        # 2. Normalized head match check
        if not match and head and len(head) >= 4 and head not in GENERIC_HEADS and head in seen_head:
            for cand in seen_head[head]:
                c_venue = (cand.get("venue") or "").lower()
                if _numbers_conflict(raw_name, cand.get("name")) or _separate_listings(e, cand):
                    continue
                if _venue_match(venue, c_venue, e, cand):
                    if not _is_different_show(e, cand):
                        match = cand
                        break

        # 3. Same physical venue title prefix/containment match
        if not match and head and len(head) >= 4 and head not in GENERIC_HEADS:
            for cand in out:
                c_venue = (cand.get("venue") or "").lower()
                if _numbers_conflict(raw_name, cand.get("name")) or _separate_listings(e, cand):
                    continue
                if _venue_match(venue, c_venue, e, cand) and not _is_different_show(e, cand):
                    cand_head = _cached_head(cand)
                    if cand_head and cand_head not in GENERIC_HEADS:
                        if (cand_head.startswith(head) or head.startswith(cand_head)) and min(len(head), len(cand_head)) >= 6:
                            match = cand
                            break
                        # Looser containment / shared two-word prefix only at the same physical
                        # venue: generic feeds match any venue, and two different "run club" or
                        # "open mic" listings at 7pm must not collapse into one.
                        if not _same_physical_venue(e, cand):
                            continue
                        if (cand_head in head or head in cand_head) and min(len(head), len(cand_head)) >= 6:
                            match = cand
                            break
                        h_words = head.split()
                        c_words = cand_head.split()
                        if len(h_words) >= 2 and len(c_words) >= 2 and h_words[:2] == c_words[:2]:
                            prefix2 = " ".join(h_words[:2])
                            if prefix2 not in GENERIC_HEADS and len(prefix2) >= 6:
                                match = cand
                                break

        # 4. Same physical venue & start within 15 min, same comedy/theater/dance/community
        #    category, and a shared distinctive title word. Words from the venue name don't
        #    count, so concurrent rooms ("Comedy Cellar MacDougal" / "Comedy Cellar Village
        #    Underground") stay separate.
        if not match and venue and len(venue) >= 4:
            t_e = e.get("_time")
            cat_e = (e.get("category") or "").lower()
            for cand in out if cat_e in ("comedy", "theater", "dance", "community") else ():
                t_c = cand.get("_time")
                if not t_e or not t_c or abs((t_e - t_c).total_seconds()) > 15 * 60:
                    continue
                if cat_e != (cand.get("category") or "").lower():
                    continue
                if _separate_listings(e, cand) or _numbers_conflict(raw_name, cand.get("name")):
                    continue
                if not _same_physical_venue(e, cand) or _is_different_show(e, cand):
                    continue
                stop = _STEP4_STOPWORDS | set(re.findall(r"\w+", venue)) | set(re.findall(r"\w+", (cand.get("venue") or "").lower()))
                words_e = {w for w in re.findall(r"\w+", raw_name.lower()) if len(w) >= 4} - stop
                words_c = {w for w in re.findall(r"\w+", (cand.get("name") or "").lower()) if len(w) >= 4} - stop
                if words_e & words_c:
                    match = cand
                    break

        # 5. Same venue, start within 90 min, titles that differ only in formatting
        #    ("half•alive"/"halfalive", "MoMA: Free Friday"/"Free Friday", "X presents: Y"/"Y")
        if not match:
            keys_e = _cached_variants(e)
            t_e = e.get("_time")
            for cand in out:
                t_c = cand.get("_time")
                if not t_e or not t_c or abs((t_e - t_c).total_seconds()) > 90 * 60:
                    continue
                if not _same_physical_venue(e, cand) or _is_different_show(e, cand):
                    continue
                if _numbers_conflict(raw_name, cand.get("name")):
                    continue  # "Ages 27-37" vs "Ages 36-48", "Round 3" vs "Round 5"
                keys_c = _cached_variants(cand)
                if _separate_listings(e, cand) and not (
                        (t_e == t_c and keys_e[:1] == keys_c[:1])
                        or (_is_generic_feed(e) and _titles_equivalent(keys_e, keys_c))):
                    # Same source, two pages: separate events, except the same title at the same
                    # minute ("X" / "X (21 and Over)") or a citywide feed listing one show twice
                    continue
                if _titles_equivalent(keys_e, keys_c):
                    match = cand
                    break

        # 6. A promoter's double posting of one club night: same source, same venue string,
        #    same start minute, both nightlife/party ("#1 REGGAETON BAR in Manhattan" and
        #    "#1 LATIN THURSDAY Party in Manhattan" at San Antonios, 10 PM). Classes and
        #    shows at multi-room venues keep their separate listings.
        if not match and venue and (e.get("category") or "").lower() in ("clubbing", "party"):
            t_e = e.get("_time")
            s_e = (e.get("_source_venue") or "").lower()
            for cand in out:
                if (t_e and cand.get("_time") == t_e and (cand.get("venue") or "").lower() == venue
                        and (cand.get("_source_venue") or "").lower() == s_e
                        and (cand.get("category") or "").lower() in ("clubbing", "party")):
                    match = cand
                    break

        # 7. Cross-listed by different organizers: same physical venue, same start minute and
        #    3/4 of the distinctive title words shared ("Speed Dating for Single Professionals
        #    Ages 40s & 50s" / "Single Professionals Ages 40s & 50s Speed Dating"). Intermediate
        #    vs Advanced Hip-Hop at one studio (2/3 shared) stays two listings.
        if not match and venue:
            t_e = e.get("_time")
            w_e = _title_words(raw_name)
            if t_e and len(w_e) >= 2:
                for cand in out:
                    if cand.get("_time") != t_e or not _same_physical_venue(e, cand):
                        continue
                    w_c = _title_words(cand.get("name"))
                    if (len(w_c) >= 2 and len(w_e & w_c) >= 0.75 * len(w_e | w_c)
                            and not _numbers_conflict(raw_name, cand.get("name"))):
                        match = cand
                        break

        # 8. Same venue and time from two sources under different titles (see _same_event_retitled)
        if not match and word_freq:
            for cand in out:
                if _same_event_retitled(e, cand, word_freq):
                    match = cand
                    break

        if match:
            # Consolidate hourly tour departures into a single daily listing
            if _is_attraction_tour(match) or _is_attraction_tour(e):
                t_m, t_new = _event_local_time(match), _event_local_time(e)
                times = match.setdefault("_tour_times", [])
                for t in (t_m, t_new):
                    if t and t not in times:
                        times.append(t)
                if t_m and t_new and t_new < t_m:
                    match["_time"] = t_new
                    if e.get("date"):
                        match["date"] = e["date"]
                times.sort()
                if len(times) > 1:
                    match["description"] = (f"Departures from {times[0].strftime('%-I:%M %p')} to "
                                            f"{times[-1].strftime('%-I:%M %p')} at {match.get('venue') or 'the venue'}.")

            # Upgrade a placeholder time (midnight / noon) once a confirmed evening showtime arrives
            m_time, e_time = match.get("_time"), e.get("_time")
            if (m_time and e_time and not e.get("_time_unknown")
                    and (match.get("_time_unknown") or (e_time.hour >= 16
                         and (m_time.hour == 0 or (m_time.hour == 12 and m_time.minute == 0))))):
                match["_time"] = e_time
                match["_time_unknown"] = False
                if e.get("date"):
                    match["date"] = e["date"]

            match.setdefault("_alt_sources", [])
            src_url = e.get("url")
            raw_src = e.get("_source_venue") or e.get("source") or e.get("venue") or "source"
            src_label = _source_display_label(raw_src, src_url)
            if src_url and not any(a.get("url") == src_url for a in match["_alt_sources"]) and src_url != match.get("url"):
                match["_alt_sources"].append({"venue": src_label, "source": raw_src, "url": src_url, "price": e.get("price"), "name": e.get("name")})

            if match.get("_venue_unknown") and not e.get("_venue_unknown") and e.get("venue"):
                match["venue"] = e["venue"]
                match.pop("_venue_unknown", None)
                for k in ("lat", "lng", "address"):
                    if e.get(k):
                        match[k] = e[k]
                for k in _MEMO_KEYS:
                    match.pop(k, None)

            cand_t_url = e.get("ticket_url")
            if cand_t_url and cand_t_url != match.get("url"):
                t_label = _source_display_label(raw_src, cand_t_url)
                if not any(a.get("url") == cand_t_url for a in match["_alt_sources"]):
                    match["_alt_sources"].append({"venue": t_label, "source": raw_src, "url": cand_t_url, "price": e.get("price")})

            # Upgrade primary source if newly arrived event has higher source specificity or URL priority
            cur_prio = _source_score(match)
            new_prio = _source_score(e)
            # Equal rank: the venue's own listing beats another organization's
            own = lambda x: bool(_venue_words({"venue": x.get("_source_venue")}) & _venue_words(x))
            if new_prio == cur_prio and own(e) and not own(match):
                new_prio += 1
            if new_prio > cur_prio:
                old_url = match.get("url")
                old_src = match.get("_source_venue") or match.get("source") or "source"
                old_label = _source_display_label(old_src, old_url)
                if old_url and not any(a.get("url") == old_url for a in match["_alt_sources"]):
                    match["_alt_sources"].append({"venue": old_label, "source": old_src, "url": old_url, "price": match.get("price"), "name": match.get("name")})
                match["url"] = e.get("url")
                match["name"] = e.get("name")
                for k in _MEMO_KEYS:
                    match.pop(k, None)
                if (match.get("venue", "").lower() in generic_sources or _is_generic_feed(match) or (e.get("venue") and not _is_generic_feed(e))) \
                        and (not e.get("_venue_unknown") or match.get("_venue_unknown")):
                    match["venue"] = e.get("venue")  # never replace a real venue with a placeholder
                match["_source_venue"] = e.get("_source_venue") or e.get("source")
                if e.get("venue_url"):
                    match["venue_url"] = e.get("venue_url")
                if e.get("_time") and (e["_time"].hour != 0 or e["_time"].minute != 0):
                    match["_time"] = e["_time"]
                # Clean up _alt_sources so match["url"] is not duplicated in its own alt list
                match["_alt_sources"] = [a for a in match["_alt_sources"] if a.get("url") != match.get("url")]

            # A venue feed may link only an organizer homepage or /events page; an RSVP page for
            # this specific event (Luma, Eventbrite, Meetup, ...) is the better primary link.
            if _is_generic_link(match.get("url")):
                rsvp = next((a for a in match["_alt_sources"] if _is_event_specific_link(a.get("url"))), None)
                if rsvp:
                    old_url = match.get("url")
                    match["_alt_sources"] = [a for a in match["_alt_sources"] if a is not rsvp]
                    if old_url and not any(a.get("url") == old_url for a in match["_alt_sources"]):
                        old_src = match.get("_source_venue") or "source"
                        match["_alt_sources"].append({"venue": _source_display_label(old_src, old_url), "source": old_src, "url": old_url, "price": match.get("price"), "name": match.get("name")})
                    match["url"] = rsvp["url"]

            # If match has 19:00:00 (Eventbrite discovery fallback) while e has a real/earlier time, prefer e
            m_time = match.get("_time")
            e_time = e.get("_time")
            m_src = (match.get("_source_venue") or match.get("venue") or "").lower()
            if "eventbrite" in m_src and m_time and m_time.hour == 19 and m_time.minute == 0 and e_time and not (e_time.hour == 19 and e_time.minute == 0):
                match["_time"] = e_time
                if e.get("date"):
                    match["date"] = e["date"]

            # Presenter tag resolution: only real non-generic co-presenters
            cand_src = (match.get("_source_venue") or "").strip()
            e_src = (e.get("_source_venue") or "").strip()
            v_name = (match.get("venue") or "").strip().lower()
            if e_src and not _is_generic_feed(e) and e_src.lower() not in generic_sources and e_src.lower() not in v_name and e_src.lower() != cand_src.lower():
                match["_presenter"] = e_src
            elif cand_src and not _is_generic_feed(match) and cand_src.lower() not in generic_sources and cand_src.lower() not in v_name and cand_src.lower() != (e_src or "").lower():
                if cand_src.lower() != (match.get("_source_venue") or "").lower():
                    match["_presenter"] = cand_src
                else:
                    match["_presenter"] = None
            else:
                match["_presenter"] = None

            # The venue's own price beats a listings site's ("$5 + fee" over "Free").
            if e.get("price") and (not match.get("price") or new_prio > cur_prio):
                # A free Meetup/RSVP listing for a group outing doesn't make a ticketed show free.
                free_claim = bool(re.search(r"\bfree\b|^\$?0(\.00)?$", str(e["price"]).strip(), re.I))
                if not (free_claim and _TICKET_SELLER_RE.search(match.get("url") or "")):
                    match["price"] = e["price"]
            if (not match.get("lat") or not match.get("lng")) and e.get("lat") and e.get("lng"):
                match["lat"] = e["lat"]
                match["lng"] = e["lng"]
            if (not match.get("category") or match.get("category") in ("other", "community")) and e.get("category") and e.get("category") not in ("other", "community"):
                match["category"] = e["category"]
            elif match.get("category") == "music" and e.get("category") == "theater":
                m_venue = (match.get("venue") or "").lower()
                e_url = (e.get("url") or "").lower()
                if any(bt in m_venue for bt in BROADWAY_THEATRES) or "theatre" in m_venue or "theater" in m_venue or "broadway" in m_venue or "broadway" in e_url:
                    match["category"] = "theater"
            if not match.get("description") and e.get("description"):
                match["description"] = e["description"]
            if not match.get("genre") and e.get("genre"):
                match["genre"] = e["genre"]
        else:
            if curl:
                seen_url.setdefault(curl, []).append(e)
            if full and len(full) >= 4:
                seen_exact.setdefault(full, []).append(e)
            if head and len(head) >= 4 and head not in GENERIC_HEADS:
                seen_head.setdefault(head, []).append(e)
            out.append(e)

    for ev in out:
        for k in _MEMO_KEYS:
            ev.pop(k, None)
        # An RSVP-platform group outing ("Free" on Meetup) merged with a ticketed show must not
        # advertise the show itself as free.
        if re.search(r"\bfree\b", str(ev.get("price") or ""), re.I):
            urls = [ev.get("url") or ""] + [a.get("url") or "" for a in ev.get("_alt_sources") or []]
            if any(_RSVP_HOST_RE.search(u) for u in urls) and any(_TICKET_SELLER_RE.search(u) for u in urls):
                ev["price"] = None
    return out


# A start at exactly midnight is believable for these; anywhere else it means "no time given".
_REAL_MIDNIGHT_CATEGORIES = {"clubbing", "party", "music", "comedy", "film"}


def _is_date_only_feed(events):
    """True when nearly all of a feed's events sit at local midnight, i.e. it publishes dates
    without times (AllEvents, DanceUS) and its midnights mean nothing."""
    total = midnight = 0
    for e in events:
        try:
            t = datetime.fromisoformat(str(e.get("date")).replace("Z", "+00:00")).astimezone(EASTERN)
        except (TypeError, ValueError):
            continue
        total += 1
        midnight += t.hour == 0 and t.minute == 0
    return total >= 3 and midnight >= 0.8 * total


def _day_order(e):
    """Timed events by start time, then events with no known time."""
    t = e.get("_time")
    return (bool(e.get("_time_unknown")), t or datetime.max.replace(tzinfo=EASTERN), (e.get("name") or "").lower())


def group_by_date(results):
    today = datetime.now(EASTERN).date()
    buckets = {}
    tba = []
    ongoing = []
    for r in results:
        date_only_feed = _is_date_only_feed(r.get("events", []))
        for e in r.get("events", []):
            if is_placeholder_or_closed_event(e.get("name")) or is_closed_show(e.get("venue")) or is_standing_exhibit(e):
                continue
            if is_service_ad(e.get("name"), e.get("venue")):
                continue
            entry = {"venue_url": r.get("url", ""), **e, "_source_venue": r.get("venue", "")}
            entry["url"] = sanitize_event_url(fix_doubled_url(entry.get("url")), fallback=r.get("url") or None)
            entry["venue"] = e.get("venue") or r.get("venue", "")
            if e.get("venue_unknown") or not (e.get("venue") or "").strip():
                # The source hid the venue (Meetup does for non-members), so "venue" is only the
                # group name. Dedup may adopt the real venue from another listing.
                entry["_venue_unknown"] = True
            existing_cat = e.get("category")
            if is_utility_event(e.get("name")):
                entry["category"] = "services"
            elif is_kid_family_event(e.get("name"), entry["venue"]):
                entry["category"] = "family"
            elif is_deal_event(e.get("name")):
                entry["category"] = "deals"
            elif existing_cat == "theater":
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
                    if dt.hour == 0 and dt.minute == 0 and (date_only_feed or entry["category"] not in _REAL_MIDNIGHT_CATEGORIES):
                        entry["_time_unknown"] = True
                except (TypeError, ValueError):
                    pass
            if key is None:
                tba.append(entry)
            elif key < today:
                ongoing.append(entry)
            else:
                buckets.setdefault(key, []).append(entry)
    word_freq = title_word_freq([e for evs in buckets.values() for e in evs])
    for date_key, events in list(buckets.items()):
        events.sort(key=lambda e: e.get("_time", datetime.min.replace(tzinfo=EASTERN)))
        # Merging can give a listing a real time, so the day's final order is set afterwards.
        buckets[date_key] = sorted(_merge_duplicates(events, word_freq), key=_day_order)
    ongoing.sort(key=lambda e: e.get("_time") or datetime.min.replace(tzinfo=EASTERN), reverse=True)
    return sorted(buckets.items()), tba, ongoing


def get_seasonal_theme(dt):
    """(theme_key, icon, label) for the holiday on dt's date, or (None, None, None).
    The holiday list, dates and palettes live in holiday_themes.py."""
    h = holiday_on(dt.date() if isinstance(dt, datetime) else dt)
    return (h["key"], h["emoji"], h["label"]) if h else (None, None, None)


def _load_highlights():
    """Editor's picks from highlights.json (written by scripts/curate_highlights.py or by hand).
    Each entry: {"match": {"name_contains", "venue_contains"}, "badge", "note", "start_date", "expires"}."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "highlights.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return []
    today = datetime.now(EASTERN).date().isoformat()
    return [h for h in data if isinstance(h, dict) and not (h.get("expires") and h["expires"] < today)] if isinstance(data, list) else []


def _get_event_highlight(e, highlights):
    if not highlights:
        return None
    name = (e.get("name") or "").lower()
    venue = f"{e.get('venue') or ''} {e.get('_source_venue') or ''}".lower()
    t = e.get("_time")
    date_str = t.date().isoformat() if t else (e.get("date") or "")[:10]
    for h in highlights:
        m = h.get("match") or {}
        nc = (m.get("name_contains") or "").lower()
        vc = (m.get("venue_contains") or "").lower()
        if not nc and not vc:
            continue
        if (nc and nc not in name) or (vc and vc not in venue):
            continue
        if h.get("start_date") and date_str and h["start_date"] > date_str:
            continue
        if h.get("expires") and date_str and h["expires"] < date_str:
            continue
        return h
    return None


def event_genre(e):
    """Music subgenre id for music/club/dance events (memoized on the event), else None."""
    cat = e.get("category") or "other"
    if cat not in MUSIC_CATEGORIES:
        return None
    if "_genre" not in e:
        g = e.get("genre")
        if g not in MUSIC_GENRES:
            g = infer_music_genre(e.get("name"), e.get("venue"), description=e.get("description"),
                                  native_genre=g if isinstance(g, str) else None, category=cat)
        e["_genre"] = g
    return e["_genre"]


DEFERRED_CHUNK_DAYS = 7


def render_page(results, split_deferred=False, context_out=None):
    """Render the full page. If context_out is a dict, it receives the deduplicated `dated`
    events plus totals, so the exporter can build SEO pages and feeds without re-merging. With split_deferred=True, days beyond the first week are left
    out of the HTML and returned separately as (page_html, [(filename, html), ...]), one file per
    week of days; the page fetches
    them from deferred_days.html after first paint, keeping index.html small."""
    if isinstance(results, dict):
        venue_list = results.get("venues", [])
    else:
        venue_list = results or []
    dated, tba, ongoing = group_by_date(venue_list)
    highlights = _load_highlights()
    picks_chip_html = ('<button type="button" class="chip-picks" id="quick-picks-chip" aria-pressed="false" title="Editor\'s picks for each day">'
                       '<span class="chip-icon">⭐ </span>Picks</button>') if highlights else ""
    recurring_keys = compute_recurring(dated)
    total = sum(len(v) for _, v in dated) + len(tba)
    seasonal_key, seasonal_icon, seasonal_label = get_seasonal_theme(datetime.now(EASTERN))
    default_theme = seasonal_key or "classic"
    seasonal_btn_html = (
        f'<button type="button" class="theme-pill-btn active" data-theme="{seasonal_key}" role="radio" '
        f'aria-checked="true" title="{escape(seasonal_label)} theme">{seasonal_icon}</button>'
    ) if seasonal_key else ""
    import seo  # local import: seo lazily imports template helpers
    site_url = seo.get_site_url()
    seo_head = seo.build_seo_meta_tags(description=seo.default_description(total), site_url=site_url)
    json_ld = seo.build_json_ld(dated, total, site_url=site_url)
    seo_directory_html = seo.build_seo_directory_html()
    if isinstance(context_out, dict):
        context_out.update({"dated": dated, "total": total, "n_sources": len(venue_list), "site_url": site_url})
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
        genre = event_genre(e)
        genre_attr = f' data-genre="{genre}"' if genre else ""
        if genre:
            ginfo = MUSIC_GENRES[genre]
            gcolor = ginfo["color"]
            cat_tag = f'<button type="button" class="cat-pill genre-pill pc-g-{genre}" data-genre="{genre}">{escape(ginfo["label"])}</button>'
        else:
            color, icon = CATEGORY_STYLES.get(cat, CATEGORY_STYLES["other"])
            cat_tag = f'<span class="cat-pill pc-c-{_pill_slug(cat if cat in CATEGORY_STYLES else "other")}"><span class="chip-icon">{icon} </span>{escape(cat)}</span>'
        venue = e.get("venue") or ""
        source = e.get("_source_venue") or ""
        geo = resolve_event_geo(e)
        geo_attrs = ""
        geo_btn = ""
        if geo:
            geo_attrs = f' data-lat="{geo["lat"]}" data-lng="{geo["lng"]}" data-venue-name="{escape(geo["venue"])}" data-neighborhood="{escape(geo["neighborhood"])}"'
            geo_btn = ' <button type="button" class="venue-map-jump" aria-label="Show on map">📍</button>'

        city = _event_city(venue, source, geo=geo, event=e)
        sub_name, sub_slug = resolve_subarea(city, e, geo=geo)
        subarea_tag = f' <span class="subarea-tag">· {escape(sub_name)}</span>' if sub_name and not sub_name.startswith("Other ") else ""
        recurring = is_recurring(e)
        recur_flag = "weekly" if recurring else "once"
        is_hourly = len(e.get("_tour_times") or []) > 1
        recur_badge = '<span class="recur">↻ hourly</span>' if is_hourly else ('<span class="recur">↻ weekly</span>' if recurring else "")
        alt_html = ""
        # One link per provider label: the same listing reached through several topic feeds
        # (Eventbrite run-club / 5K / outdoor searches) only needs to be offered once.
        alts, other_titles, seen_alt_urls, seen_alt_labels = [], [], {_clean_event_url(e.get("url")) or e.get("url")}, set()
        for a in e.get("_alt_sources") or []:
            a_url = a.get("url")
            a_key = _clean_event_url(a_url) or a_url
            if not a_url or a_key in seen_alt_urls:
                continue
            if _titles_unrelated(raw_title, a.get("name")):
                # Merged as the same time and place but titled differently: maybe a different event
                # (or a tour name vs the band). Show its title so it's never hidden.
                seen_alt_urls.add(a_key)
                other_titles.append(f'<a href="{escape(a_url)}" target="_blank" rel="noopener">{escape(a["name"])}</a>'
                                    f' <span class="also-src">({escape(a.get("venue") or "source")})</span>')
                continue
            label = (a.get("venue") or "").strip().lower()
            if label in seen_alt_labels:
                continue
            seen_alt_urls.add(a_key)
            seen_alt_labels.add(label)
            alts.append(a)
        if alts:
            alt_links = " · ".join(
                f'<a href="{escape(a["url"])}" target="_blank" rel="noopener">{escape(a["venue"])}</a>'
                for a in alts
            )
            if alt_links:
                alt_html = f'<span class="alt-sources">also on {alt_links}</span>'
        if other_titles:
            alt_html += f'<span class="also-listed">Also listed: {" · ".join(other_titles)}</span>'

        compare_html = _build_compare_links(e, raw_title)

        presenter = e.get("_presenter") or ""
        if presenter and _is_aggregator_source(presenter):
            presenter = ""
        if not presenter and source and venue and not _is_aggregator_source(source, e.get("venue_url")):
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

        cal_html = '<span class="cal-links"><button type="button" class="cal-btn gcal-btn">+ GCal</button> <button type="button" class="cal-btn ics-btn">+ .ics</button></span>' if e.get("date") else ""

        raw_desc = (e.get("description") or "").replace("***", "").replace("**", "").replace("__", "").replace("`", "").strip()
        if "[" in raw_desc:
            raw_desc = re.sub(r'\[/?[a-zA-Z0-9_-]+[^\]]*\]?', ' ', raw_desc)
            raw_desc = re.sub(r'\[(?:>>\s*)?(?:please\s+)?(?:register|rsvp|ticket)[^\]]*\]\([^)]+\)', '', raw_desc, flags=re.I)
            raw_desc = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', raw_desc)
        if "<" in raw_desc:
            raw_desc = re.sub(r'<[^>]+>', ' ', raw_desc)
        raw_desc = unescape(raw_desc)
        raw_desc = re.sub(r'\s+', ' ', raw_desc).strip()
        desc = raw_desc[:180]
        desc_html = f'<div class="desc">{escape(desc)}</div>' if desc else ""
        is_guestlist = _is_event_guestlist(e)
        guestlist_flag = "true" if is_guestlist else "false"
        guestlist_badge = '<span class="badge-guestlist" title="Free club guestlist or RSVP entry">🎟️ Guestlist</span>' if is_guestlist else ""
        free_flag = "true" if (is_free or is_guestlist) else "false"
        # No epoch for an unknown time: it would read as "started at midnight" and hide the event.
        epoch_attr = f' data-epoch="{int(e["_time"].timestamp())}"' if e.get("_time") and not e.get("_time_unknown") else ''
        t_obj = e.get("_time")
        raw_date = e.get("date") or ""
        is_date_only = len(raw_date) == 10 or ("T00:00:00" in raw_date and not (t_obj and (t_obj.hour != 0 or t_obj.minute != 0)))
        if t_obj and not is_date_only and not e.get("_time_unknown"):
            time_mins = t_obj.hour * 60 + t_obj.minute
            time_attr = f' data-time-mins="{time_mins}"'
        else:
            time_attr = ' data-time-mins="-1"'
        extra_html = f' · {compare_html}' if compare_html else ''
        pres_attr = f' data-presenter="{escape(presenter)}"' if presenter else ''
        ev_id = _event_stable_id(e)
        hl = _get_event_highlight(e, highlights)
        hl_class = " highlighted" if hl else ""
        hl_attr = ' data-highlight="true"' if hl else ""
        hl_badge = ""
        note_html = ""
        if hl:
            b_text = hl.get("badge") or "Editor's Pick"
            note = hl.get("note")
            tooltip = f"{b_text} — {note}" if note else b_text
            hl_badge = f' <span class="badge-highlight" title="{escape(tooltip)}">{escape(b_text)}</span>'
            if note:
                note_html = f'<div class="curator-note"><span class="note-label">Why it\'s a pick:</span> {escape(note)}</div>'
        # Flags are emitted only when true (the page tests `=== 'true'`), and nothing that the
        # page can derive (subarea name, HH:MM) is repeated per event: deferred days are ~17k <li>s.
        flag_attrs = (' data-free="true"' if free_flag == "true" else "") + (' data-guestlist="true"' if guestlist_flag == "true" else "") + (' data-lgbtq="true"' if is_lgbtq_event(e) else "")
        return _compact_li(f'''<li class="event{hl_class}" data-cat="{escape(cat)}" data-bucket="{escape(bucket)}"{genre_attr} data-venue="{escape(source)}"{pres_attr} data-city="{escape(city)}" data-subarea="{escape(sub_slug)}" data-recur="{recur_flag}"{flag_attrs}{hl_attr}{epoch_attr}{time_attr}{geo_attrs}>
          <div class="when">{escape(format_when(e))}</div>
          <div class="what"><button type="button" class="star-btn" aria-label="Add to My Schedule">☆</button>{link}{price_tag}{guestlist_badge}{hl_badge}{recur_badge}
            <div class="venue-tag">{cat_tag} · {venue_html}{(" · " + alt_html) if alt_html else ""}{extra_html}{cal_html}</div>
            {note_html}{desc_html}
          </div>
        </li>''')

    bucket_name_order = [b for b, _ in CATEGORY_BUCKETS]
    city_day_order = ["manhattan", "brooklyn", "queens", "bronx", "staten_island", "citywide", "other"]

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
            <div class="bucket" data-bucket="{escape(bname)}" style="--accent:{accent};">
              <div class="bucket-head">
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
            c = _event_city(e.get("venue"), e.get("_source_venue"), geo=geo, event=e)
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
          <div class="near-me-stream" style="display: none;"></div>
          <div class="cities">{"".join(city_blocks)}</div>
        </section>'''

    initial_sections = []
    # Days after the first three load after first paint, in weekly files, so a visitor who
    # looks at next Saturday fetches and parses one week rather than all five.
    deferred_chunks = []  # [{"dates": [...], "html": [...]}]
    for idx, (date_obj, events) in enumerate(dated):
        sec_html = _render_day_section(escape(format_date_heading(date_obj)), events, date_obj.isoformat())
        if idx < 3:  # today + next two days inline
            initial_sections.append(sec_html)
            continue
        if not deferred_chunks or len(deferred_chunks[-1]["dates"]) >= DEFERRED_CHUNK_DAYS:
            deferred_chunks.append({"dates": [], "html": []})
        deferred_chunks[-1]["dates"].append(date_obj.isoformat())
        deferred_chunks[-1]["html"].append(sec_html)
    if tba:
        if not deferred_chunks:
            deferred_chunks.append({"dates": [], "html": []})
        deferred_chunks[-1]["dates"].append("tba")
        deferred_chunks[-1]["html"].append(_render_day_section("Date TBA", tba, "tba"))

    all_event_dates = [d.isoformat() for d, _ in dated]

    deferred_html = "".join(h for c in deferred_chunks for h in c["html"])
    deferred_files = []
    if split_deferred:
        manifest = []
        for n, chunk in enumerate(deferred_chunks, 1):
            body = "".join(chunk["html"])
            name = f"deferred_days_{n}.html"
            deferred_files.append((name, body))
            manifest.append({"src": f"{name}?v={hashlib.sha1(body.encode('utf-8')).hexdigest()[:10]}", "dates": chunk["dates"]})
        deferred_tag = f"<template id=\"deferred-days\" data-chunks='{escape(json.dumps(manifest), quote=True)}'></template>"
    else:
        deferred_tag = f'<template id="deferred-days">{deferred_html}</template>'

    useful_sidebar = ""
    if STATIC_LINKS or DEAL_LINKS:
        deals_block = ""
        lucky_shows = fetch_luckyseat_nyc()
        if DEAL_LINKS or lucky_shows:
            lucky_html = ""
            if lucky_shows:
                def _lucky_li(s):
                    price = s.get("price")
                    price_str = f" · ${price:.0f}" if isinstance(price, (int, float)) else ""
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

    genre_counts = {g: 0 for g in MUSIC_GENRES}
    for e in all_events_flat:
        g = event_genre(e)
        if g:
            genre_counts[g] += 1
    genre_boxes = "\n".join(
        f'''<label class="chk chk-subgenre">
              <input type="checkbox" class="genre-chk" value="{gid}" checked>
              <span><span class="genre-swatch" style="background:{ginfo['color']}"></span>{escape(ginfo['label'])} <span class="count">{genre_counts[gid]}</span></span>
            </label>'''
        for gid, ginfo in MUSIC_GENRES.items()
    )
    subgenres_html = f'''
          <div class="subgenre-container" id="subgenre-container">
            <div class="subgenre-header">
              <span>Subgenres</span><span class="spacer"></span>
              <button type="button" id="genre-all" class="subgenre-btn" title="Select all subgenres">all</button>
              <button type="button" id="genre-none" class="subgenre-btn" title="Deselect all subgenres">none</button>
            </div>
            <div class="subgenre-grid">{genre_boxes}</div>
          </div>'''
    bucket_boxes = "\n".join(
        f'''<label class="chk">
            <input type="checkbox" class="cat-chk" value="{escape(b)}"{"" if b in DEFAULT_UNCHECKED_BUCKETS else " checked"}>
            <span><span class="chip-icon">{_bucket_icon_row(b)} </span>{escape(b)} <span class="count">{bucket_counts.get(b, 0)}</span></span>
          </label>''' + (subgenres_html if b == "Music & nightlife" else "")
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

    city_order = ["manhattan", "brooklyn", "queens", "bronx", "staten_island", "citywide", "other"]
    city_counts = {c: 0 for c in city_order}
    for e in all_events_flat:
        geo = resolve_event_geo(e)
        c = _event_city(e.get("venue"), e.get("_source_venue"), geo=geo, event=e)
        city_counts[c] = city_counts.get(c, 0) + 1

    city_boxes = "\n".join(
        f'''<label class="chk">
            <input type="checkbox" class="city-chk" value="{escape(c)}"{" checked" if c in DEFAULT_CITIES else ""}>
            <span><span class="city-swatch" style="background:{CITY_COLORS[c]}"></span>{escape(CITY_LABELS[c])} <span class="count">{city_counts.get(c, 0)}</span></span>
          </label>'''
        for c in city_order
    )

    page_html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=5.0">
{seo_head}
{json_ld}
<script>
  // Seasonal themes switch on automatically unless the visitor picked one today.
  var HOLIDAY_CALENDAR = {json.dumps(holiday_calendar(datetime.now(EASTERN).date() - timedelta(days=2), 400))};
  var HOLIDAY_KEYS = {json.dumps(HOLIDAY_KEYS)};
  var BASE_THEMES = ['classic', 'light', 'indie', 'anime'];
  function localISODate(dt) {{
    return dt.getFullYear() + '-' + String(dt.getMonth() + 1).padStart(2, '0') + '-' + String(dt.getDate()).padStart(2, '0');
  }}
  function getClientSeasonalTheme(dt) {{
    return HOLIDAY_CALENDAR[localISODate(dt)] || null;
  }}
  // Visitors who haven't picked a theme get their device's setting: light or dark.
  function systemTheme() {{
    try {{
      return (window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches) ? 'light' : 'classic';
    }} catch (e) {{ return 'classic'; }}
  }}
  // Which theme to show: a ?theme= preview; else today's holiday, unless the visitor picked a
  // theme today; else the visitor's last regular theme; else their device's light/dark setting.
  function pickTheme() {{
    var preview = new URLSearchParams(location.search).get('theme');
    if (preview && (BASE_THEMES.indexOf(preview) !== -1 || HOLIDAY_KEYS.indexOf(preview) !== -1)) return preview;
    var now = new Date(), today = localISODate(now), holiday = getClientSeasonalTheme(now), stored = null, pickedOn = null;
    try {{
      stored = localStorage.getItem('nyc_events_theme');
      pickedOn = localStorage.getItem('nyc_events_theme_manual');
    }} catch (e) {{}}
    if (holiday) return (pickedOn === today && stored) ? stored : holiday;
    return (stored && BASE_THEMES.indexOf(stored) !== -1) ? stored : systemTheme();
  }}
  try {{
    document.documentElement.setAttribute('data-theme', pickTheme());
  }} catch (e) {{}}
</script>
<style>
  {_pill_css()}
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
  .badge-highlight {{
    display: inline-flex; align-items: center; gap: 4px; padding: 2px 8px; border-radius: 999px;
    font-size: 11px; font-weight: 700; letter-spacing: 0.02em; vertical-align: middle; margin-left: 6px;
    background: rgba(255, 184, 0, 0.16); border: 1px solid rgba(255, 184, 0, 0.45); color: #ffd866;
  }}
  .event.highlighted {{ box-shadow: inset 3px 0 0 #ffd866; }}
  .curator-note {{
    font-size: 12.5px; color: #ffebb8; background: rgba(255, 184, 0, 0.08);
    border: 1px solid rgba(255, 184, 0, 0.2); border-radius: 8px; padding: 6px 10px; margin-top: 6px;
  }}
  .curator-note .note-label {{ font-weight: 700; color: #ffd866; }}
  .week-nav button.chip-picks.active {{ background: rgba(255, 184, 0, 0.2); border-color: #ffd866; color: #ffd866; }}
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
  .day {{ background: var(--card); border: 1px solid var(--border); border-radius: var(--radius-lg); padding: 14px 18px 12px; content-visibility: auto; contain-intrinsic-size: auto 500px; }}
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
  .city-section[data-city="citywide"]      {{ --city-color: #7dd3c0; }}
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
  .also-listed {{ display: block; color: var(--muted); font-size: 11px; margin-top: 2px; }}
  .also-listed a {{ color: var(--accent); text-decoration: none; }}
  .also-listed a:hover {{ text-decoration: underline; }}
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
  .subgenre-container {{ margin: 2px 0 6px 14px; padding: 6px 8px 6px 10px; background: rgba(255,255,255,0.02); border-left: 2px solid rgba(255,255,255,0.12); border-radius: 0 6px 6px 0; transition: opacity 0.2s ease; }}
  .subgenre-container.disabled {{ opacity: 0.4; pointer-events: none; }}
  .subgenre-header {{ display: flex; align-items: center; gap: 6px; font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.07em; color: var(--muted); margin-bottom: 4px; }}
  .subgenre-header .spacer {{ flex: 1; }}
  .subgenre-btn {{ background: none; border: none; color: var(--muted); font-size: 10px; font-weight: 600; cursor: pointer; padding: 0 4px; border-radius: 3px; font-family: inherit; }}
  .subgenre-btn:hover {{ color: var(--fg); background: rgba(255,255,255,0.1); }}
  .subgenre-grid {{ display: flex; flex-direction: column; gap: 1px; }}
  .chk-subgenre {{ font-size: 11.5px; padding: 2px 4px; }}
  .genre-swatch {{ display: inline-block; width: 7px; height: 7px; border-radius: 50%; margin-right: 6px; vertical-align: middle; }}
  button.genre-pill {{ font-family: inherit; cursor: pointer; }}
  button.genre-pill:hover {{ filter: brightness(1.2); }}
  .chk > span {{ display: flex; align-items: center; gap: 6px; flex: 1; min-width: 0; }}
  .chk > span > .count {{ margin-left: auto; }}
  .city-swatch {{ display: inline-block; width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }}
  .free-toggle {{ display: flex; align-items: center; gap: 8px; font-size: 12px; font-weight: 600; cursor: pointer; color: var(--green); user-select: none; }}
  .free-toggle input {{ accent-color: var(--green); width: 14px; height: 14px; cursor: pointer; margin: 0; }}
  .lgbtq-toggle {{ display: flex; align-items: center; gap: 8px; margin-top: 6px; font-size: 12px; font-weight: 600; cursor: pointer; color: #a855f7; user-select: none; }}
  .lgbtq-toggle input {{ accent-color: #a855f7; width: 14px; height: 14px; cursor: pointer; margin: 0; }}

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
  .mini-cal-grid .d.range-start {{ background: var(--accent); color: #0c0e14; font-weight: 700; border-radius: 6px 0 0 6px; }}
  .mini-cal-grid .d.range-end {{ background: var(--accent); color: #0c0e14; font-weight: 700; border-radius: 0 6px 6px 0; }}
  .mini-cal-grid .d.range-start.range-end {{ border-radius: 6px; }}
  .mini-cal-grid .d.range-start::after, .mini-cal-grid .d.range-end::after {{ background: #0c0e14; }}
  .mini-cal-grid .d.in-range {{ background: rgba(93,155,255,0.22); color: var(--fg); border-radius: 0; }}
  .mini-cal-hint {{ font-size: 11px; color: var(--muted); text-align: center; margin-top: 8px; padding-top: 6px; border-top: 1px solid var(--border); }}
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
  .view-actions {{
    display: inline-flex;
    align-items: center;
    gap: 10px;
  }}
  .map-toggle-btn {{
    background: rgba(255, 255, 255, 0.05);
    border: 1px solid var(--border);
    color: var(--muted);
    font-size: 12.5px;
    font-weight: 600;
    padding: 5px 14px;
    min-width: 64px;
    border-radius: 999px;
    cursor: pointer;
    font-family: inherit;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
    transition: all 0.15s ease;
  }}
  .map-toggle-btn:hover {{
    color: var(--fg);
    border-color: var(--accent);
  }}
  .map-toggle-btn.active {{
    background: var(--accent-glow);
    border-color: var(--accent);
    color: var(--accent);
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
  .dist-badge {{
    display: inline-flex;
    align-items: center;
    gap: 3px;
    font-size: 11px;
    font-weight: 700;
    padding: 1px 7px;
    border-radius: 999px;
    background: rgba(46, 160, 67, 0.15);
    color: #3fb950;
    border: 1px solid rgba(46, 160, 67, 0.35);
    margin-left: 6px;
    vertical-align: middle;
  }}
  [data-theme="indie"] .dist-badge {{
    background: rgba(56, 189, 248, 0.12);
    color: #38bdf8;
    border-color: rgba(56, 189, 248, 0.3);
  }}
  [data-theme="anime"] .dist-badge {{
    background: rgba(255, 75, 147, 0.15);
    color: #ff79c6;
    border-color: rgba(255, 75, 147, 0.35);
  }}
  [data-theme="halloween"] .dist-badge {{
    background: rgba(255, 121, 63, 0.18);
    color: #ff9f43;
    border-color: rgba(255, 121, 63, 0.4);
    box-shadow: 0 0 8px rgba(255, 121, 63, 0.2);
  }}
  .near-stream-banner {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    background: var(--card);
    border: 1px solid var(--border);
    border-left: 3px solid var(--accent);
    padding: 10px 14px;
    border-radius: var(--radius-md);
    margin-bottom: 12px;
    font-size: 13px;
    gap: 10px;
    flex-wrap: wrap;
  }}
  .near-stream-actions {{
    display: flex;
    gap: 6px;
    flex-wrap: wrap;
  }}
  .pin-hint {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
    flex-wrap: wrap;
    padding: 8px 12px;
    border: 1px dashed var(--accent);
    border-radius: var(--radius-sm);
    font-size: 12px;
    color: var(--fg);
  }}
  .pin-hint[hidden] {{ display: none; }}
  .leaflet-map.placing-pin,
  .leaflet-map.placing-pin .leaflet-interactive {{ cursor: crosshair; }}
  .drop-pin-marker {{ background: none; border: none; }}
  .drop-pin-marker span {{
    font-size: 28px;
    line-height: 1;
    filter: drop-shadow(0 2px 3px rgba(0, 0, 0, 0.6));
    cursor: grab;
  }}
  .near-stream-info {{
    display: flex;
    align-items: center;
    gap: 8px;
    color: var(--fg);
  }}
  .near-stream-clear-btn {{
    background: rgba(255, 255, 255, 0.08);
    border: 1px solid var(--border);
    color: var(--fg);
    border-radius: 999px;
    padding: 4px 10px;
    font-size: 11px;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.15s ease;
  }}
  .near-stream-clear-btn:hover {{
    background: var(--accent);
    color: #0c0e14;
  }}
  .near-events-list {{
    list-style: none;
    padding: 0;
    margin: 0;
    display: flex;
    flex-direction: column;
    gap: 8px;
  }}
  .time-select-row {{
    display: flex;
    align-items: center;
    gap: 6px;
  }}
  .time-input-wrap {{
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 3px;
  }}
  .time-input-wrap label {{
    font-size: 10px;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 0.05em;
    font-weight: 600;
  }}
  .time-dropdown {{
    width: 100%;
    background: var(--bg);
    border: 1px solid var(--border);
    color: var(--fg);
    padding: 5px 6px;
    border-radius: var(--radius-sm);
    font-size: 11.5px;
    font-family: inherit;
    cursor: pointer;
    transition: border-color 0.15s ease;
  }}
  .time-dropdown:focus {{
    outline: none;
    border-color: var(--accent);
    box-shadow: 0 0 0 2px var(--accent-glow);
  }}
  .time-range-arrow {{
    color: var(--muted);
    font-size: 13px;
    padding-top: 14px;
    user-select: none;
  }}
  .time-range-active-indicator {{
    margin-top: 6px;
    font-size: 11px;
    color: var(--accent);
    font-weight: 600;
    line-height: 1.3;
  }}
  .chip-time-custom {{
    background: rgba(255, 121, 63, 0.15) !important;
    border-color: #ff793f !important;
    color: #ff9f43 !important;
  }}

  /* Classic Dark: remove distracting emojis from category badges and category filters */
  :root .cat-pill .chip-icon,
  [data-theme="classic"] .cat-pill .chip-icon,
  :root .cat-pill.genre-pill .chip-icon,
  [data-theme="classic"] .cat-pill.genre-pill .chip-icon,
  :root .chk-grid .cat-chk ~ span .chip-icon,
  [data-theme="classic"] .chk-grid .cat-chk ~ span .chip-icon {{
    display: none !important;
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
  .seo-directory {{ margin-top: 18px; padding-top: 14px; border-top: 1px solid var(--border); line-height: 1.9; }}
  .seo-directory h2 {{ font-size: 12px; letter-spacing: 0.08em; text-transform: uppercase; margin: 0 0 6px; color: var(--fg); }}
  .seo-directory p {{ margin: 0 auto; max-width: 980px; }}
  .seo-directory a {{ color: var(--muted); text-decoration: none; white-space: nowrap; }}
  .seo-directory a:hover {{ color: var(--accent); text-decoration: underline; }}

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
    .chip {{
      flex-shrink: 0;
      padding: 5px 12px;
      font-size: 12px;
    }}

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

  .star-btn {{
    background: none;
    border: none;
    color: var(--muted);
    cursor: pointer;
    font-size: 15px;
    line-height: 1;
    padding: 0 6px 0 0;
    vertical-align: baseline;
  }}
  .star-btn:hover {{ color: #ffd866; }}
  .star-btn.starred {{ color: #ffd866; text-shadow: 0 0 8px rgba(255, 216, 102, 0.45); }}
  @media (pointer: coarse) {{
    .star-btn {{ font-size: 18px; padding: 8px 10px 8px 2px; }}
  }}
  .schedule-bar {{
    position: fixed;
    left: 50%;
    transform: translateX(-50%);
    bottom: calc(14px + env(safe-area-inset-bottom, 0px));
    z-index: 9000;
    display: flex;
    gap: 4px;
    padding: 4px;
    background: var(--card);
    border: 1px solid var(--border-hover, var(--border));
    border-radius: 999px;
    box-shadow: 0 8px 28px rgba(0, 0, 0, 0.35);
    max-width: calc(100vw - 32px);
  }}
  .schedule-bar button {{
    border: 0;
    border-radius: 999px;
    padding: 8px 14px;
    font: inherit;
    font-size: 13px;
    font-weight: 700;
    cursor: pointer;
    white-space: nowrap;
  }}
  .schedule-bar-view {{ background: transparent; color: var(--fg); }}
  .schedule-bar-view[aria-pressed="true"] {{ background: rgba(127, 127, 127, 0.18); }}
  .schedule-bar-share {{ background: var(--accent); color: #0c0e14; }}
  .schedule-bar button:focus-visible {{ outline: 2px solid var(--accent); outline-offset: 2px; }}
  .schedule-share-card {{ max-width: 460px; display: grid; gap: 8px; }}
  .schedule-share-label {{ font-size: 13px; font-weight: 600; color: var(--muted); margin-top: 6px; }}
  .schedule-share-card input {{
    width: 100%;
    box-sizing: border-box;
    padding: 9px 10px;
    border-radius: var(--radius-sm);
    border: 1px solid var(--border);
    background: rgba(127, 127, 127, 0.1);
    color: var(--fg);
    font: inherit;
    font-size: 14px;
  }}
  .schedule-share-actions {{ display: flex; flex-wrap: wrap; align-items: center; gap: 10px; margin-top: 10px; }}
  .schedule-share-copy, .schedule-share-send {{
    border: 0;
    border-radius: var(--radius-sm);
    padding: 9px 16px;
    font: inherit;
    font-weight: 700;
    cursor: pointer;
  }}
  .schedule-share-copy {{ background: var(--accent); color: #0c0e14; }}
  .schedule-share-send {{ background: rgba(127, 127, 127, 0.18); color: var(--fg); }}
  .schedule-share-open {{ color: var(--accent); font-size: 14px; }}
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
  /* ---- Visual themes (ported from Boston events) ---- */
  .banner-theme-slot {{ position: absolute; top: 14px; right: 16px; z-index: 5; }}
  .theme-toggle-wrap {{
    display: inline-flex;
    align-items: center;
    background: rgba(15, 18, 25, 0.7);
    backdrop-filter: blur(10px);
    -webkit-backdrop-filter: blur(10px);
    border: 1px solid rgba(255, 255, 255, 0.12);
    border-radius: 999px;
    padding: 2px;
    margin-left: auto;
  }}
  .theme-toggle-label {{
    display: none;
  }}
  .theme-toggle-pills {{
    display: inline-flex;
    gap: 1px;
    background: transparent;
    border-radius: 999px;
    padding: 0;
  }}
  .theme-pill-btn {{
    border: none;
    background: transparent;
    color: var(--muted);
    font-size: 11px;
    font-weight: 600;
    padding: 2px 7px;
    border-radius: 999px;
    cursor: pointer;
    transition: all 0.15s ease;
    font-family: inherit;
    line-height: 1.35;
  }}
  .theme-pill-btn:hover {{
    color: #fff;
  }}
  .theme-pill-btn.active {{
    background: #f4f5f8;
    color: #0c0e14;
    font-weight: 700;
    box-shadow: 0 1px 4px rgba(0,0,0,0.3);
  }}

  [data-theme="light"] {{
    color-scheme: light;
    --bg: #f5f6fa;
    --card: #ffffff;
    --card-hover: #f0f2f8;
    --fg: #161a24;
    --muted: #5b6475;
    --accent: #2563eb;
    --accent-glow: rgba(37, 99, 235, 0.16);
    --border: rgba(15, 23, 42, 0.11);
    --border-hover: rgba(15, 23, 42, 0.24);
    --green: #15803d;
    --green-bg: rgba(22, 163, 74, 0.10);
    --green-border: rgba(22, 163, 74, 0.35);
    --warn: #c2410c;
  }}
  [data-theme="indie"] {{
    --bg: #0e1014;
    --card: #15181e;
    --card-hover: #1c2028;
    --fg: #f4f5f8;
    --muted: #8c93a4;
    --accent: #e2a85a;
    --accent-glow: transparent;
    --border: rgba(255, 255, 255, 0.08);
    --border-hover: rgba(255, 255, 255, 0.16);
    --green: #48bb78;
    --green-bg: rgba(72, 187, 120, 0.12);
    --green-border: rgba(72, 187, 120, 0.25);
    --warn: #e07a5f;
    --radius-lg: 10px;
    --radius-md: 6px;
    --radius-sm: 4px;
  }}
  [data-theme="anime"] {{
    --bg: #0d0a1c;
    --card: #17122e;
    --card-hover: #211a42;
    --fg: #f5f0ff;
    --muted: #a49abf;
    --accent: #ff4b93;
    --accent-glow: rgba(255, 75, 147, 0.4);
    --border: rgba(255, 107, 181, 0.22);
    --border-hover: rgba(0, 240, 255, 0.45);
    --green: #00f0ff;
    --green-bg: rgba(0, 240, 255, 0.14);
    --green-border: rgba(0, 240, 255, 0.38);
    --warn: #ff758f;
    --radius-lg: 18px;
    --radius-md: 12px;
    --radius-sm: 8px;
  }}
  [data-theme="indie"] .dist-badge {{
    background: rgba(56, 189, 248, 0.12);
    color: #38bdf8;
    border-color: rgba(56, 189, 248, 0.3);
  }}
  [data-theme="anime"] .dist-badge {{
    background: rgba(255, 75, 147, 0.15);
    color: #ff79c6;
    border-color: rgba(255, 75, 147, 0.35);
  }}
  [data-theme="halloween"] .dist-badge {{
    background: rgba(255, 121, 63, 0.18);
    color: #ff9f43;
    border-color: rgba(255, 121, 63, 0.4);
    box-shadow: 0 0 8px rgba(255, 121, 63, 0.2);
  }}
  [data-theme="anime"] .theme-pill-btn.active {{
    background: linear-gradient(135deg, #ff4b93 0%, #a855f7 100%);
    color: #ffffff;
    box-shadow: 0 0 10px rgba(255, 75, 147, 0.5);
  }}
  [data-theme="halloween"] .theme-pill-btn.active {{
    background: linear-gradient(135deg, #ff793f 0%, #ff4757 100%);
    color: #ffffff;
    box-shadow: 0 0 10px rgba(255, 121, 63, 0.5);
  }}
  [data-theme="election"] .theme-pill-btn.active {{
    background: linear-gradient(135deg, #2563eb 0%, #dc2626 100%);
    color: #ffffff;
    box-shadow: 0 0 10px rgba(37, 99, 235, 0.5);
  }}
  [data-theme="veterans"] .theme-pill-btn.active {{
    background: linear-gradient(135deg, #d4af37 0%, #1e3a8a 100%);
    color: #ffffff;
    box-shadow: 0 0 10px rgba(212, 175, 55, 0.5);
  }}
  [data-theme="thanksgiving"] .theme-pill-btn.active {{
    background: linear-gradient(135deg, #ea580c 0%, #be123c 100%);
    color: #ffffff;
    box-shadow: 0 0 10px rgba(234, 88, 12, 0.5);
  }}
  [data-theme="blackfriday"] .theme-pill-btn.active {{
    background: linear-gradient(135deg, #facc15 0%, #eab308 100%);
    color: #000000;
    box-shadow: 0 0 10px rgba(250, 204, 21, 0.5);
  }}
  [data-theme="cybermonday"] .theme-pill-btn.active {{
    background: linear-gradient(135deg, #06b6d4 0%, #9333ea 100%);
    color: #ffffff;
    box-shadow: 0 0 10px rgba(6, 182, 212, 0.5);
  }}
  [data-theme="indie"] .chip-icon,
  [data-theme="indie"] .live-pulse {{
    display: none !important;
  }}
  [data-theme="indie"] .banner {{
    background-color: #0b0d11;
    background-image:
      linear-gradient(180deg, rgba(11, 13, 17, 0.35) 0%, rgba(11, 13, 17, 0.82) 60%, rgba(11, 13, 17, 0.98) 100%);
    min-height: 250px;
    padding: 34px 24px 26px;
  }}
  [data-theme="indie"] .banner-top-tag {{
    color: #cbd5e1;
    font-size: 11px;
    letter-spacing: 0.16em;
    font-weight: 650;
    text-shadow: none;
  }}
  [data-theme="indie"] .banner-title {{
    font-size: 42px;
    letter-spacing: -0.04em;
    font-weight: 850;
  }}
  [data-theme="indie"] .banner-meta-pill {{
    background: rgba(18, 21, 28, 0.88);
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 8px;
    padding: 6px 14px;
    box-shadow: 0 2px 12px rgba(0,0,0,0.4);
  }}
  [data-theme="indie"] .pill-submit-btn {{
    background: rgba(255, 255, 255, 0.08);
    border: 1px solid rgba(255, 255, 255, 0.2);
    color: #f4f5f8;
    box-shadow: none;
    border-radius: 6px;
    font-weight: 600;
    padding: 4px 11px;
  }}
  [data-theme="indie"] .pill-submit-btn:hover {{
    background: rgba(255, 255, 255, 0.16);
    border-color: rgba(255, 255, 255, 0.35);
    transform: none;
    filter: none;
    box-shadow: none;
  }}
  [data-theme="indie"] .chip,
  [data-theme="indie"] .loc-chip,
  [data-theme="indie"] .genre-chip,
  [data-theme="indie"] .transit-chip,
  [data-theme="indie"] .sub-chip {{
    border-radius: 6px;
    font-size: 12px;
    font-weight: 500;
    letter-spacing: 0.01em;
    background: rgba(255, 255, 255, 0.03);
    border: 1px solid rgba(255, 255, 255, 0.08);
    padding: 6px 13px;
  }}
  [data-theme="indie"] .chip.active,
  [data-theme="indie"] .loc-chip.active,
  [data-theme="indie"] .genre-chip.active,
  [data-theme="indie"] .sub-chip.active {{
    background: rgba(226, 168, 90, 0.14);
    border-color: #e2a85a;
    color: #f6c888;
    font-weight: 600;
  }}
  [data-theme="indie"] .chip:hover,
  [data-theme="indie"] .loc-chip:hover,
  [data-theme="indie"] .genre-chip:hover,
  [data-theme="indie"] .transit-chip:hover,
  [data-theme="indie"] .sub-chip:hover {{
    background: rgba(255, 255, 255, 0.07);
    border-color: rgba(255, 255, 255, 0.18);
    color: #fff;
  }}
  [data-theme="indie"] .day {{
    border-radius: 8px;
    padding: 16px 18px 14px;
    background: var(--card);
  }}
  [data-theme="indie"] .day h2 {{
    font-size: 16px;
    font-weight: 700;
    letter-spacing: -0.01em;
    border-bottom: 1px solid rgba(255, 255, 255, 0.06);
    padding-bottom: 8px;
    margin-bottom: 12px;
  }}
  [data-theme="indie"] .event {{
    padding: 9px 12px;
    border-radius: 4px;
    background: transparent;
    border: 1px solid transparent;
    border-bottom: 1px solid rgba(255, 255, 255, 0.04);
    margin-bottom: 2px;
  }}
  [data-theme="indie"] .event:hover {{
    background: rgba(255, 255, 255, 0.035);
    border-color: rgba(255, 255, 255, 0.08);
    transform: none;
    box-shadow: none;
  }}
  [data-theme="indie"] .event .when {{
    font-variant-numeric: tabular-nums;
    font-size: 12px;
    color: #9aa1b2;
    font-weight: 500;
  }}
  [data-theme="indie"] .event .what a {{
    color: #f4f5f8;
    font-weight: 600;
  }}
  [data-theme="indie"] .event .what a:hover {{
    color: #e2a85a;
    text-decoration: underline;
  }}
  [data-theme="indie"] .cat-pill {{
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    border-radius: 3px;
    padding: 2px 6px;
    background: rgba(255, 255, 255, 0.05) !important;
    border: 1px solid rgba(255, 255, 255, 0.1) !important;
    color: #b5bcc9 !important;
  }}
  [data-theme="indie"] .cal-btn {{
    border-radius: 4px;
    font-size: 11px;
    padding: 1px 7px;
    border: 1px solid rgba(255, 255, 255, 0.12);
    background: transparent;
    color: var(--muted);
  }}
  [data-theme="indie"] .cal-btn:hover {{
    background: rgba(255, 255, 255, 0.08);
    color: #fff;
    border-color: rgba(255, 255, 255, 0.25);
  }}
  [data-theme="indie"] .view-toggle {{
    background: rgba(255, 255, 255, 0.04);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 6px;
    padding: 2px;
  }}
  [data-theme="indie"] .view-btn {{
    border-radius: 4px;
    font-size: 12px;
    font-weight: 500;
    padding: 5px 12px;
  }}
  [data-theme="indie"] .view-btn.active {{
    background: rgba(255, 255, 255, 0.1);
    color: #fff;
    box-shadow: none;
  }}
  [data-theme="indie"] .share-filter-btn {{
    border-radius: 6px;
    background: rgba(255, 255, 255, 0.04);
    border: 1px solid rgba(255, 255, 255, 0.08);
    font-size: 12px;
  }}
  [data-theme="indie"] .past-events-banner {{
    background: rgba(255, 255, 255, 0.03);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 6px;
    box-shadow: none;
    color: var(--muted);
  }}
  [data-theme="indie"] .past-banner-badge {{
    background: rgba(255, 255, 255, 0.08);
    color: #e2a85a;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.06em;
    border-radius: 3px;
    padding: 2px 7px;
  }}
  [data-theme="indie"] .past-banner-btn {{
    background: rgba(255, 255, 255, 0.06);
    border: 1px solid rgba(255, 255, 255, 0.15);
    border-radius: 4px;
    color: #eef1f8;
    font-weight: 500;
  }}
  [data-theme="indie"] .past-banner-btn:hover {{
    background: rgba(255, 255, 255, 0.12);
  }}
  [data-theme="indie"] .indie-jump-label {{
    display: inline-block;
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    color: var(--muted);
    border: 1px solid rgba(255, 255, 255, 0.12);
    border-radius: 3px;
    padding: 1px 5px;
    line-height: 1.2;
    vertical-align: middle;
  }}
  [data-theme="indie"] .venue-map-jump:hover .indie-jump-label {{
    color: #fff;
    border-color: rgba(255, 255, 255, 0.3);
  }}
  [data-theme="anime"] .banner {{
    background-color: #110d28;
    background-image:
      linear-gradient(180deg, rgba(30, 15, 60, 0.45) 0%, rgba(18, 12, 40, 0.78) 58%, rgba(13, 10, 28, 0.98) 100%);
    border-bottom: 2px solid rgba(255, 75, 147, 0.3);
    box-shadow: 0 4px 30px rgba(168, 85, 247, 0.18);
  }}
  [data-theme="anime"] .banner-top-tag {{
    color: #00f0ff;
    text-shadow: 0 0 12px rgba(0, 240, 255, 0.7);
    letter-spacing: 0.18em;
    font-weight: 700;
  }}
  [data-theme="anime"] .banner-title {{
    background: linear-gradient(135deg, #ffffff 20%, #ff79c6 60%, #00f0ff 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    filter: drop-shadow(0 0 25px rgba(255, 75, 147, 0.35));
    letter-spacing: -0.02em;
  }}
  [data-theme="anime"] .banner-meta-pill {{
    background: rgba(28, 20, 56, 0.85);
    border: 1px solid rgba(255, 107, 181, 0.35);
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.4), 0 0 18px rgba(255, 75, 147, 0.22);
    border-radius: 999px;
  }}
  [data-theme="anime"] .pill-submit-btn {{
    background: linear-gradient(135deg, #ff4b93 0%, #9333ea 100%);
    border: 1px solid rgba(255, 255, 255, 0.3);
    color: #fff;
    box-shadow: 0 0 12px rgba(255, 75, 147, 0.45);
    font-weight: 700;
    border-radius: 999px;
  }}
  [data-theme="anime"] .pill-submit-btn:hover {{
    filter: brightness(1.2);
    box-shadow: 0 0 20px rgba(255, 75, 147, 0.7);
    transform: translateY(-1px) scale(1.02);
  }}
  [data-theme="anime"] .live-pulse {{
    background: #00f0ff;
    box-shadow: 0 0 10px #00f0ff, 0 0 20px #00f0ff;
  }}
  [data-theme="anime"] .chip,
  [data-theme="anime"] .loc-chip,
  [data-theme="anime"] .genre-chip,
  [data-theme="anime"] .transit-chip,
  [data-theme="anime"] .sub-chip {{
    border-radius: 999px;
    background: rgba(30, 22, 60, 0.65);
    border: 1px solid rgba(255, 107, 181, 0.22);
    color: #d1c7e8;
    backdrop-filter: blur(8px);
    -webkit-backdrop-filter: blur(8px);
    transition: all 0.2s cubic-bezier(0.34, 1.56, 0.64, 1);
  }}
  [data-theme="anime"] .chip:hover,
  [data-theme="anime"] .loc-chip:hover,
  [data-theme="anime"] .genre-chip:hover,
  [data-theme="anime"] .transit-chip:hover,
  [data-theme="anime"] .sub-chip:hover {{
    border-color: #00f0ff;
    color: #fff;
    box-shadow: 0 0 12px rgba(0, 240, 255, 0.4);
    transform: translateY(-2px);
  }}
  [data-theme="anime"] .chip.active,
  [data-theme="anime"] .loc-chip.active,
  [data-theme="anime"] .genre-chip.active,
  [data-theme="anime"] .sub-chip.active {{
    background: linear-gradient(135deg, rgba(255, 75, 147, 0.3) 0%, rgba(168, 85, 247, 0.3) 100%);
    border-color: #ff4b93;
    color: #fff;
    box-shadow: 0 0 14px rgba(255, 75, 147, 0.4);
    font-weight: 700;
  }}
  [data-theme="anime"] .day {{
    background: rgba(23, 18, 46, 0.7);
    border: 1px solid rgba(255, 107, 181, 0.18);
    box-shadow: 0 4px 24px rgba(0, 0, 0, 0.3);
    border-radius: var(--radius-lg);
  }}
  [data-theme="anime"] .day h2 {{
    color: #fce7f3;
    border-bottom: 1px solid rgba(255, 107, 181, 0.18);
  }}
  [data-theme="anime"] .day h2 .count {{
    background: rgba(255, 75, 147, 0.2);
    border: 1px solid rgba(255, 75, 147, 0.45);
    color: #ff85be;
    border-radius: 999px;
  }}
  [data-theme="anime"] .event {{
    background: rgba(30, 24, 62, 0.55);
    border: 1px solid rgba(255, 107, 181, 0.15);
    border-radius: var(--radius-md);
    transition: all 0.2s cubic-bezier(0.34, 1.56, 0.64, 1);
  }}
  [data-theme="anime"] .event:hover {{
    background: rgba(42, 34, 88, 0.85);
    border-color: rgba(255, 75, 147, 0.5);
    box-shadow: 0 6px 20px rgba(0, 0, 0, 0.35), 0 0 14px rgba(255, 75, 147, 0.3);
    transform: translateY(-2px);
  }}
  [data-theme="anime"] .event .what a {{
    color: #f5f0ff;
  }}
  [data-theme="anime"] .event .what a:hover {{
    color: #00f0ff;
    text-shadow: 0 0 10px rgba(0, 240, 255, 0.6);
  }}
  [data-theme="anime"] .cat-pill {{
    border-radius: 999px;
    font-weight: 700;
    box-shadow: 0 0 8px rgba(0, 0, 0, 0.2);
  }}
  [data-theme="anime"] .star-btn:hover,
  [data-theme="anime"] .star-btn.starred {{
    color: #ff4b93;
    text-shadow: 0 0 12px rgba(255, 75, 147, 0.8);
  }}
  [data-theme="anime"] .view-toggle {{
    border-radius: 999px;
    background: rgba(30, 22, 60, 0.65);
    border: 1px solid rgba(255, 107, 181, 0.25);
    padding: 3px;
  }}
  [data-theme="anime"] .view-btn {{
    border-radius: 999px;
  }}
  [data-theme="anime"] .view-btn.active {{
    background: linear-gradient(135deg, #ff4b93 0%, #9333ea 100%);
    color: #fff;
    box-shadow: 0 0 12px rgba(255, 75, 147, 0.45);
  }}
  [data-theme="anime"] .share-filter-btn {{
    border-radius: 999px;
    background: rgba(30, 22, 60, 0.65);
    border: 1px solid rgba(255, 107, 181, 0.25);
  }}
  [data-theme="halloween"] {{
    --bg: #09050e;
    --card: #130a1c;
    --card-hover: #1c1028;
    --fg: #fffcf6;
    --muted: #a395b5;
    --accent: #ff793f;
    --accent-glow: rgba(255, 121, 63, 0.35);
    --border: rgba(255, 121, 63, 0.22);
    --border-hover: rgba(255, 121, 63, 0.45);
    --green: #00d2d3;
    --green-bg: rgba(0, 210, 211, 0.14);
    --green-border: rgba(0, 210, 211, 0.35);
    --warn: #ff9f43;
    --radius-lg: 16px;
    --radius-md: 10px;
    --radius-sm: 6px;
  }}
  [data-theme="halloween"] body {{
    background-color: var(--bg);
    background-image:
      radial-gradient(ellipse 80% 50% at 50% -10%, rgba(255, 121, 63, 0.08) 0%, transparent 70%),
      radial-gradient(ellipse 60% 40% at 90% 40%, rgba(142, 68, 173, 0.06) 0%, transparent 60%);
    background-attachment: fixed;
    color: var(--fg);
  }}
  [data-theme="halloween"] .banner {{
    background-color: #0d0617;
    background-image:
      linear-gradient(180deg, rgba(13, 6, 23, 0.45) 0%, rgba(20, 9, 34, 0.75) 55%, rgba(9, 5, 14, 0.98) 100%);
    background-position: center 85%;
    background-size: cover;
    border-bottom: 2px solid rgba(255, 121, 63, 0.45);
    box-shadow: 0 4px 30px rgba(0, 0, 0, 0.5), 0 0 20px rgba(255, 121, 63, 0.15);
  }}
  [data-theme="halloween"] .banner-top-tag {{
    color: #ff9f43;
    text-shadow: 0 0 14px rgba(255, 159, 67, 0.7);
    letter-spacing: 0.18em;
    font-weight: 800;
  }}
  [data-theme="halloween"] .live-pulse {{
    background: #ff793f;
    box-shadow: 0 0 10px #ff793f, 0 0 20px #ff793f;
  }}
  [data-theme="halloween"] .banner-title {{
    background: linear-gradient(135deg, #ffffff 15%, #ff9f43 55%, #ff5252 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    filter: drop-shadow(0 0 25px rgba(255, 121, 63, 0.4));
    letter-spacing: -0.02em;
  }}
  [data-theme="halloween"] .banner-meta-pill {{
    background: rgba(22, 11, 36, 0.88);
    border: 1px solid rgba(255, 121, 63, 0.4);
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.5), 0 0 16px rgba(255, 121, 63, 0.18);
    border-radius: 999px;
    backdrop-filter: blur(10px);
  }}
  [data-theme="halloween"] .pill-submit-btn {{
    background: linear-gradient(135deg, #ff4757 0%, #ff793f 60%, #f39c12 100%);
    border: 1px solid rgba(255, 255, 255, 0.35);
    color: #fff;
    box-shadow: 0 0 14px rgba(255, 121, 63, 0.5);
    font-weight: 800;
    border-radius: 999px;
  }}
  [data-theme="halloween"] .pill-submit-btn:hover {{
    filter: brightness(1.15);
    box-shadow: 0 0 22px rgba(255, 121, 63, 0.75);
    transform: translateY(-1px) scale(1.02);
  }}
  [data-theme="halloween"] .chip,
  [data-theme="halloween"] .loc-chip,
  [data-theme="halloween"] .genre-chip,
  [data-theme="halloween"] .transit-chip,
  [data-theme="halloween"] .sub-chip {{
    border-radius: 999px;
    background: rgba(26, 14, 42, 0.7);
    border: 1px solid rgba(255, 121, 63, 0.25);
    color: #d8cde8;
    backdrop-filter: blur(8px);
    transition: all 0.2s cubic-bezier(0.34, 1.56, 0.64, 1);
  }}
  [data-theme="halloween"] .chip:hover,
  [data-theme="halloween"] .loc-chip:hover,
  [data-theme="halloween"] .genre-chip:hover,
  [data-theme="halloween"] .transit-chip:hover,
  [data-theme="halloween"] .sub-chip:hover {{
    border-color: #ff9f43;
    color: #ffffff;
    box-shadow: 0 0 14px rgba(255, 159, 67, 0.4);
    transform: translateY(-2px);
  }}
  [data-theme="halloween"] .chip.active,
  [data-theme="halloween"] .loc-chip.active,
  [data-theme="halloween"] .genre-chip.active,
  [data-theme="halloween"] .sub-chip.active {{
    background: linear-gradient(135deg, rgba(255, 121, 63, 0.4) 0%, rgba(224, 86, 253, 0.28) 100%);
    border-color: #ff793f;
    color: #ffeaa7;
    box-shadow: 0 0 14px rgba(255, 121, 63, 0.4);
    font-weight: 700;
  }}
  [data-theme="halloween"] .day {{
    background: rgba(19, 10, 31, 0.75);
    border: 1px solid rgba(255, 121, 63, 0.22);
    box-shadow: 0 4px 24px rgba(0, 0, 0, 0.4);
    border-radius: var(--radius-lg);
  }}
  [data-theme="halloween"] .day h2 {{
    color: #fff2df;
    border-bottom: 1px solid rgba(255, 121, 63, 0.22);
  }}
  [data-theme="halloween"] .day h2 .count {{
    background: rgba(255, 121, 63, 0.2);
    border: 1px solid rgba(255, 121, 63, 0.5);
    color: #ff9f43;
    border-radius: 999px;
  }}
  [data-theme="halloween"] .event {{
    background: rgba(26, 14, 42, 0.6);
    border: 1px solid rgba(255, 121, 63, 0.18);
    border-radius: var(--radius-md);
    transition: all 0.2s cubic-bezier(0.34, 1.56, 0.64, 1);
  }}
  [data-theme="halloween"] .event:hover {{
    background: rgba(36, 20, 58, 0.9);
    border-color: rgba(255, 121, 63, 0.6);
    box-shadow: 0 6px 20px rgba(0, 0, 0, 0.4), 0 0 16px rgba(255, 121, 63, 0.3);
    transform: translateY(-2px);
  }}
  [data-theme="halloween"] .event .what a {{
    color: #ffffff;
  }}
  [data-theme="halloween"] .event .what a:hover {{
    color: #ff9f43;
    text-shadow: 0 0 10px rgba(255, 159, 67, 0.6);
  }}
  [data-theme="halloween"] .filter-group {{
    background: rgba(19, 10, 31, 0.85);
    border: 1px solid rgba(255, 121, 63, 0.25);
  }}
  [data-theme="halloween"] .badge-highlight {{
    background: linear-gradient(135deg, rgba(255, 121, 63, 0.25) 0%, rgba(243, 156, 18, 0.35) 100%);
    border: 1px solid #ff793f;
    color: #ffeaa7;
    box-shadow: 0 0 10px rgba(255, 121, 63, 0.25);
  }}
  [data-theme="election"] {{
    --bg: #090d16;
    --card: #121826;
    --card-hover: #1b2438;
    --fg: #f1f5f9;
    --muted: #94a3b8;
    --accent: #3b82f6;
    --accent-glow: rgba(59, 130, 246, 0.35);
    --border: rgba(59, 130, 246, 0.22);
    --border-hover: rgba(59, 130, 246, 0.45);
    --green: #22c55e;
    --green-bg: rgba(34, 197, 94, 0.14);
    --green-border: rgba(34, 197, 94, 0.35);
    --warn: #ef4444;
    --radius-lg: 14px;
    --radius-md: 8px;
    --radius-sm: 5px;
  }}
  [data-theme="election"] body {{
    background-color: var(--bg);
    background-image:
      radial-gradient(ellipse 80% 50% at 20% -10%, rgba(59, 130, 246, 0.10) 0%, transparent 65%),
      radial-gradient(ellipse 70% 40% at 85% 20%, rgba(239, 68, 68, 0.08) 0%, transparent 60%);
    background-attachment: fixed;
  }}
  [data-theme="election"] .banner {{
    background-color: #0c1220;
    border-bottom: 2px solid rgba(59, 130, 246, 0.45);
    box-shadow: 0 4px 30px rgba(0, 0, 0, 0.5), 0 0 20px rgba(59, 130, 246, 0.15);
  }}
  [data-theme="election"] .banner-top-tag {{
    color: #60a5fa;
    text-shadow: 0 0 12px rgba(96, 165, 250, 0.6);
  }}
  [data-theme="election"] .live-pulse {{
    background: #3b82f6;
    box-shadow: 0 0 10px #3b82f6, 0 0 20px #3b82f6;
  }}
  [data-theme="election"] .banner-title {{
    background: linear-gradient(135deg, #ffffff 15%, #93c5fd 60%, #fca5a5 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    filter: drop-shadow(0 0 20px rgba(59, 130, 246, 0.35));
  }}
  [data-theme="election"] .pill-submit-btn {{
    background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 50%, #dc2626 100%);
    color: #fff;
    box-shadow: 0 0 14px rgba(37, 99, 235, 0.45);
    border-radius: 999px;
  }}
  [data-theme="election"] .chip.active,
  [data-theme="election"] .loc-chip.active,
  [data-theme="election"] .genre-chip.active,
  [data-theme="election"] .sub-chip.active {{
    background: linear-gradient(135deg, rgba(37, 99, 235, 0.35) 0%, rgba(220, 38, 38, 0.25) 100%);
    border-color: #3b82f6;
    color: #ffffff;
    box-shadow: 0 0 12px rgba(59, 130, 246, 0.35);
  }}
  [data-theme="veterans"] {{
    --bg: #090d18;
    --card: #111a2e;
    --card-hover: #182542;
    --fg: #f8fafc;
    --muted: #94a3b8;
    --accent: #d4af37;
    --accent-glow: rgba(212, 175, 55, 0.35);
    --border: rgba(212, 175, 55, 0.25);
    --border-hover: rgba(212, 175, 55, 0.50);
    --green: #38bdf8;
    --green-bg: rgba(56, 189, 248, 0.14);
    --green-border: rgba(56, 189, 248, 0.35);
    --warn: #f59e0b;
    --radius-lg: 14px;
    --radius-md: 8px;
    --radius-sm: 5px;
  }}
  [data-theme="veterans"] body {{
    background-color: var(--bg);
    background-image:
      radial-gradient(ellipse 80% 50% at 50% -10%, rgba(212, 175, 55, 0.08) 0%, transparent 70%),
      radial-gradient(ellipse 60% 40% at 90% 40%, rgba(30, 58, 138, 0.16) 0%, transparent 60%);
    background-attachment: fixed;
  }}
  [data-theme="veterans"] .banner {{
    background-color: #0c1322;
    border-bottom: 2px solid rgba(212, 175, 55, 0.45);
    box-shadow: 0 4px 30px rgba(0, 0, 0, 0.5), 0 0 20px rgba(212, 175, 55, 0.15);
  }}
  [data-theme="veterans"] .banner-top-tag {{
    color: #fbbf24;
    text-shadow: 0 0 12px rgba(251, 191, 36, 0.6);
  }}
  [data-theme="veterans"] .live-pulse {{
    background: #d4af37;
    box-shadow: 0 0 10px #d4af37, 0 0 20px #d4af37;
  }}
  [data-theme="veterans"] .banner-title {{
    background: linear-gradient(135deg, #ffffff 20%, #fde047 65%, #60a5fa 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    filter: drop-shadow(0 0 20px rgba(212, 175, 55, 0.35));
  }}
  [data-theme="veterans"] .pill-submit-btn {{
    background: linear-gradient(135deg, #b45309 0%, #d97706 50%, #1e3a8a 100%);
    color: #fff;
    box-shadow: 0 0 14px rgba(212, 175, 55, 0.45);
    border-radius: 999px;
  }}
  [data-theme="veterans"] .chip.active,
  [data-theme="veterans"] .loc-chip.active,
  [data-theme="veterans"] .genre-chip.active,
  [data-theme="veterans"] .sub-chip.active {{
    background: linear-gradient(135deg, rgba(212, 175, 55, 0.35) 0%, rgba(30, 58, 138, 0.35) 100%);
    border-color: #d4af37;
    color: #fef08a;
    box-shadow: 0 0 12px rgba(212, 175, 55, 0.35);
  }}
  [data-theme="thanksgiving"] {{
    --bg: #100b08;
    --card: #1a120c;
    --card-hover: #261b12;
    --fg: #fef7ed;
    --muted: #bfa094;
    --accent: #ea580c;
    --accent-glow: rgba(234, 88, 12, 0.35);
    --border: rgba(234, 88, 12, 0.22);
    --border-hover: rgba(234, 88, 12, 0.45);
    --green: #84cc16;
    --green-bg: rgba(132, 204, 22, 0.14);
    --green-border: rgba(132, 204, 22, 0.35);
    --warn: #f59e0b;
    --radius-lg: 16px;
    --radius-md: 10px;
    --radius-sm: 6px;
  }}
  [data-theme="thanksgiving"] body {{
    background-color: var(--bg);
    background-image:
      radial-gradient(ellipse 80% 50% at 50% -10%, rgba(234, 88, 12, 0.09) 0%, transparent 70%),
      radial-gradient(ellipse 60% 40% at 85% 35%, rgba(190, 18, 60, 0.07) 0%, transparent 60%);
    background-attachment: fixed;
  }}
  [data-theme="thanksgiving"] .banner {{
    background-color: #170f0a;
    border-bottom: 2px solid rgba(234, 88, 12, 0.45);
    box-shadow: 0 4px 30px rgba(0, 0, 0, 0.5), 0 0 20px rgba(234, 88, 12, 0.15);
  }}
  [data-theme="thanksgiving"] .banner-top-tag {{
    color: #fb923c;
    text-shadow: 0 0 12px rgba(251, 146, 60, 0.6);
  }}
  [data-theme="thanksgiving"] .live-pulse {{
    background: #ea580c;
    box-shadow: 0 0 10px #ea580c, 0 0 20px #ea580c;
  }}
  [data-theme="thanksgiving"] .banner-title {{
    background: linear-gradient(135deg, #fffbeb 20%, #fb923c 60%, #e11d48 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    filter: drop-shadow(0 0 20px rgba(234, 88, 12, 0.35));
  }}
  [data-theme="thanksgiving"] .pill-submit-btn {{
    background: linear-gradient(135deg, #c2410c 0%, #ea580c 50%, #be123c 100%);
    color: #fff;
    box-shadow: 0 0 14px rgba(234, 88, 12, 0.5);
    border-radius: 999px;
  }}
  [data-theme="thanksgiving"] .chip.active,
  [data-theme="thanksgiving"] .loc-chip.active,
  [data-theme="thanksgiving"] .genre-chip.active,
  [data-theme="thanksgiving"] .sub-chip.active {{
    background: linear-gradient(135deg, rgba(234, 88, 12, 0.4) 0%, rgba(190, 18, 60, 0.3) 100%);
    border-color: #ea580c;
    color: #ffedd5;
    box-shadow: 0 0 12px rgba(234, 88, 12, 0.4);
  }}
  [data-theme="blackfriday"] {{
    --bg: #050608;
    --card: #0f1116;
    --card-hover: #181c24;
    --fg: #fafafa;
    --muted: #a1a1aa;
    --accent: #facc15;
    --accent-glow: rgba(250, 204, 21, 0.35);
    --border: rgba(250, 204, 21, 0.22);
    --border-hover: rgba(250, 204, 21, 0.45);
    --green: #22c55e;
    --green-bg: rgba(34, 197, 94, 0.14);
    --green-border: rgba(34, 197, 94, 0.35);
    --warn: #f97316;
    --radius-lg: 12px;
    --radius-md: 8px;
    --radius-sm: 4px;
  }}
  [data-theme="blackfriday"] body {{
    background-color: var(--bg);
    background-image:
      radial-gradient(ellipse 80% 50% at 50% -10%, rgba(250, 204, 21, 0.08) 0%, transparent 70%),
      radial-gradient(ellipse 60% 40% at 10% 40%, rgba(239, 68, 68, 0.06) 0%, transparent 60%);
    background-attachment: fixed;
  }}
  [data-theme="blackfriday"] .banner {{
    background-color: #07090f;
    border-bottom: 2px solid rgba(250, 204, 21, 0.5);
    box-shadow: 0 4px 30px rgba(0, 0, 0, 0.6), 0 0 20px rgba(250, 204, 21, 0.2);
  }}
  [data-theme="blackfriday"] .banner-top-tag {{
    color: #facc15;
    text-shadow: 0 0 14px rgba(250, 204, 21, 0.7);
  }}
  [data-theme="blackfriday"] .live-pulse {{
    background: #facc15;
    box-shadow: 0 0 10px #facc15, 0 0 20px #facc15;
  }}
  [data-theme="blackfriday"] .banner-title {{
    background: linear-gradient(135deg, #ffffff 20%, #fde047 60%, #f97316 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    filter: drop-shadow(0 0 22px rgba(250, 204, 21, 0.4));
  }}
  [data-theme="blackfriday"] .pill-submit-btn {{
    background: linear-gradient(135deg, #ca8a04 0%, #eab308 50%, #dc2626 100%);
    color: #000;
    font-weight: 800;
    box-shadow: 0 0 16px rgba(250, 204, 21, 0.5);
    border-radius: 999px;
  }}
  [data-theme="blackfriday"] .chip.active,
  [data-theme="blackfriday"] .loc-chip.active,
  [data-theme="blackfriday"] .genre-chip.active,
  [data-theme="blackfriday"] .sub-chip.active {{
    background: linear-gradient(135deg, rgba(250, 204, 21, 0.35) 0%, rgba(249, 115, 22, 0.25) 100%);
    border-color: #facc15;
    color: #fef08a;
    box-shadow: 0 0 12px rgba(250, 204, 21, 0.35);
  }}
  [data-theme="cybermonday"] {{
    --bg: #050811;
    --card: #0c1222;
    --card-hover: #131c35;
    --fg: #f0fdf4;
    --muted: #7dd3fc;
    --accent: #06b6d4;
    --accent-glow: rgba(6, 182, 212, 0.45);
    --border: rgba(6, 182, 212, 0.25);
    --border-hover: rgba(6, 182, 212, 0.55);
    --green: #10b981;
    --green-bg: rgba(16, 185, 129, 0.14);
    --green-border: rgba(16, 185, 129, 0.35);
    --warn: #ec4899;
    --radius-lg: 14px;
    --radius-md: 8px;
    --radius-sm: 5px;
  }}
  [data-theme="cybermonday"] body {{
    background-color: var(--bg);
    background-image:
      radial-gradient(ellipse 80% 50% at 50% -10%, rgba(6, 182, 212, 0.12) 0%, transparent 70%),
      radial-gradient(ellipse 60% 40% at 85% 30%, rgba(168, 85, 247, 0.10) 0%, transparent 60%);
    background-attachment: fixed;
  }}
  [data-theme="cybermonday"] .banner {{
    background-color: #070e1c;
    border-bottom: 2px solid rgba(6, 182, 212, 0.5);
    box-shadow: 0 4px 30px rgba(0, 0, 0, 0.6), 0 0 20px rgba(6, 182, 212, 0.2);
  }}
  [data-theme="cybermonday"] .banner-top-tag {{
    color: #22d3ee;
    text-shadow: 0 0 14px rgba(34, 211, 238, 0.7);
  }}
  [data-theme="cybermonday"] .live-pulse {{
    background: #06b6d4;
    box-shadow: 0 0 10px #06b6d4, 0 0 20px #06b6d4;
  }}
  [data-theme="cybermonday"] .banner-title {{
    background: linear-gradient(135deg, #ffffff 20%, #22d3ee 60%, #c084fc 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    filter: drop-shadow(0 0 20px rgba(6, 182, 212, 0.4));
  }}
  [data-theme="cybermonday"] .pill-submit-btn {{
    background: linear-gradient(135deg, #0891b2 0%, #06b6d4 50%, #9333ea 100%);
    color: #fff;
    box-shadow: 0 0 16px rgba(6, 182, 212, 0.5);
    border-radius: 999px;
  }}
  [data-theme="cybermonday"] .chip.active,
  [data-theme="cybermonday"] .loc-chip.active,
  [data-theme="cybermonday"] .genre-chip.active,
  [data-theme="cybermonday"] .sub-chip.active {{
    background: linear-gradient(135deg, rgba(6, 182, 212, 0.35) 0%, rgba(168, 85, 247, 0.25) 100%);
    border-color: #06b6d4;
    color: #cffafe;
    box-shadow: 0 0 12px rgba(6, 182, 212, 0.4);
  }}
  [data-theme="classic"] .theme-pill-btn.active {{
    background: var(--accent);
    color: #0c0e14;
  }}

  /* Holiday themes generated from holiday_themes.py: skyline colors, greeting, palettes */
  {holiday_theme_css()}

  /* Light theme overrides (light_theme.py) */
{LIGHT_THEME_CSS}
</style>
</head>
<body>
  <div class="banner">
    <div class="banner-theme-slot">
      <div class="theme-toggle-wrap">
        <div class="theme-toggle-pills" role="radiogroup" aria-label="Visual theme">
          {seasonal_btn_html}
          <button type="button" class="theme-pill-btn{' active' if default_theme == 'classic' else ''}" data-theme="classic" role="radio" aria-checked="{'true' if default_theme == 'classic' else 'false'}" title="Classic dark theme">🌙</button>
          <button type="button" class="theme-pill-btn" data-theme="light" role="radio" aria-checked="false" title="Light theme">☀️</button>
          <button type="button" class="theme-pill-btn" data-theme="indie" role="radio" aria-checked="false" title="Indie guide theme">📰</button>
          <button type="button" class="theme-pill-btn" data-theme="anime" role="radio" aria-checked="false" title="Anime theme">🌸</button>
        </div>
      </div>
    </div>
    <div class="banner-svg-wrap">
      {BANNER_SVG}
    </div>
    <div class="banner-gradient-overlay"></div>
    <div class="banner-inner">
      <div class="banner-top-tag"><span class="live-pulse"></span> NYC LIVE EVENTS &amp; SHOWS</div>
      {greeting_html()}
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
          <span><span class="chip-icon">✨ </span>Free events only</span>
        </label>
        <label class="free-toggle" for="guestlist-only-chk" style="margin-top:6px;">
          <input type="checkbox" id="guestlist-only-chk">
          <span><span class="chip-icon">🎟️ </span>Free club guestlists only</span>
        </label>
        <label class="lgbtq-toggle" for="lgbtq-only-chk">
          <input type="checkbox" id="lgbtq-only-chk">
          <span><span class="chip-icon">🏳️‍🌈 </span>LGBTQ+ events only</span>
        </label>
        <div class="timeframe-toggle-wrap" style="margin-top: 10px; padding-top: 10px; border-top: 1px dashed var(--border);">
          <label class="timeframe-toggle" for="timeframe-enable-chk">
            <input type="checkbox" id="timeframe-enable-chk">
            <span><span class="chip-icon">⏱️ </span>Set timeframe window</span>
          </label>
          <div class="custom-time-range" id="custom-time-range" style="display: none; margin-top: 10px;">
            <div class="time-select-row">
              <div class="time-input-wrap">
                <label for="time-from-select">From</label>
                <select id="time-from-select" class="time-dropdown"></select>
              </div>
              <div class="time-range-arrow">→</div>
              <div class="time-input-wrap">
                <label for="time-to-select">To</label>
                <select id="time-to-select" class="time-dropdown"></select>
              </div>
            </div>
            <div class="time-range-active-indicator" id="time-range-active-indicator" style="display:none;"></div>
          </div>
        </div>
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
        <div class="view-toggle" role="group" aria-label="Feed presentation">
          <button type="button" class="view-btn active" id="btn-view-list" data-view="list" title="Browse events grouped by category and borough">
            <span>Category</span>
          </button>
          <button type="button" class="view-btn" id="btn-near-me" data-view="near" title="Sort events by distance to your current location">
            <span id="near-me-btn-label">Near Me</span>
          </button>
          <button type="button" class="view-btn" id="btn-drop-pin" data-view="pin" title="Tap the map to drop a pin and sort events by distance from it">
            <span id="drop-pin-btn-label">Drop Pin</span>
          </button>
        </div>
        <div class="view-actions">
          <span id="map-venue-stat" class="map-venue-stat" style="display: none;">
            <strong id="map-venue-count">0</strong> venues
          </span>
          <button type="button" class="map-toggle-btn" id="btn-view-map" title="Toggle interactive venue map">
            <span id="map-btn-label">Map</span>
          </button>
        </div>
      </div>
      <div class="location-chips-bar" id="location-chips">
        <button type="button" class="loc-chip active" data-city="all">📍 All Boroughs</button>
        <button type="button" class="loc-chip" data-city="manhattan"><span class="city-dot" style="background:#5d9bff"></span>Manhattan</button>
        <button type="button" class="loc-chip" data-city="brooklyn"><span class="city-dot" style="background:#e05a6b"></span>Brooklyn</button>
        <button type="button" class="loc-chip" data-city="queens"><span class="city-dot" style="background:#f29e4c"></span>Queens</button>
        <button type="button" class="loc-chip" data-city="bronx"><span class="city-dot" style="background:#4ade80"></span>The Bronx</button>
        <button type="button" class="loc-chip" data-city="staten_island"><span class="city-dot" style="background:#a78bfa"></span>Staten Island</button>
        <button type="button" class="loc-chip" data-city="other" title="New Jersey, Long Island, Westchester &amp; more"><span class="city-dot" style="background:#9aa3b2"></span>Outside NYC</button>
      </div>
      <div class="subarea-chips-bar" id="subarea-chips-bar" style="display: none;"></div>
      <div class="week-nav" id="week-nav">
        <button type="button" id="week-prev" aria-label="Previous">← prev</button>
        <span id="week-label">Today, {today.strftime("%b %d")}</span>
        <button type="button" id="week-next" aria-label="Next">next →</button>
        <button type="button" id="week-today">today</button>
        <button type="button" id="cal-toggle" aria-expanded="false">📅 pick date</button>
        {picks_chip_html}
        <button type="button" class="chip chip-time-custom" id="quick-custom-time-chip" style="display:none;" title="Click to clear timeframe filter"><span id="active-timeframe-label"></span> <span class="chip-icon" style="margin-left:4px;">✕</span></button>
      </div>
      <div class="mini-cal" id="mini-cal" hidden>
        <div class="mini-cal-head">
          <button type="button" id="cal-prev-month" aria-label="Previous month">‹</button>
          <span id="cal-month-label"></span>
          <button type="button" id="cal-next-month" aria-label="Next month">›</button>
        </div>
        <div class="mini-cal-grid" id="mini-cal-grid"></div>
        <div class="mini-cal-hint" id="cal-hint">Pick a date, or click a second date for a range</div>
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
        <div id="pin-hint" class="pin-hint" hidden>
          <span><span class="chip-icon">📌 </span><strong>Tap the map to drop your pin.</strong> Events will be sorted by distance from it.</span>
          <button type="button" id="pin-cancel-btn" class="map-tool-btn">Cancel</button>
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
      {"".join(initial_sections)}
      {deferred_tag}
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
    {seo_directory_html}
  </footer>

  <!-- Community Event & Venue Submission Modal -->
  <div id="schedule-bar" class="schedule-bar" style="display:none;">
    <button type="button" class="schedule-bar-view" id="schedule-view" aria-pressed="false">★ My Schedule <span id="schedule-count"></span></button>
    <button type="button" class="schedule-bar-share" id="schedule-share">Share</button>
  </div>
  <div id="schedule-share-modal" class="modal-overlay" role="dialog" aria-modal="true" aria-labelledby="schedule-share-title" style="display:none;">
    <div class="modal-card schedule-share-card">
      <div class="modal-header">
        <div>
          <h2 class="modal-title" id="schedule-share-title">Share your schedule</h2>
          <p class="modal-sub" id="schedule-share-sub"></p>
        </div>
        <button type="button" class="modal-close-btn" id="schedule-share-close" aria-label="Close">✕</button>
      </div>
      <label class="schedule-share-label" for="schedule-share-name">Your name (optional)</label>
      <input type="text" id="schedule-share-name" maxlength="40" placeholder="Shows as “Sam's weekend”" autocomplete="given-name">
      <label class="schedule-share-label" for="schedule-share-link">Link to send</label>
      <input type="text" id="schedule-share-link" readonly>
      <div class="schedule-share-actions">
        <button type="button" class="schedule-share-copy" id="schedule-share-copy">Copy link</button>
        <button type="button" class="schedule-share-send" id="schedule-share-send" style="display:none;">Send</button>
        <a class="schedule-share-open" id="schedule-share-open" href="schedule/" target="_blank" rel="noopener">Preview</a>
      </div>
    </div>
  </div>
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
    const genreBoxes = document.querySelectorAll('.genre-chk');
    const MUSIC_BUCKET = 'Music & nightlife';
    const syncSubgenreUI = () => {{
      const box = document.getElementById('subgenre-container');
      const music = Array.from(catBoxes).find(b => b.value === MUSIC_BUCKET);
      if (box && music) box.classList.toggle('disabled', !music.checked);
    }};
    const defaultUncheckedCats = new Set({json.dumps(sorted(DEFAULT_UNCHECKED_BUCKETS))});
    const isDefaultCat = (b) => !defaultUncheckedCats.has(b.value);
    const isCatFilteredFn = () => Array.from(catBoxes).some(b => b.checked !== isDefaultCat(b));
    const venueBoxes = document.querySelectorAll('.venue-chk');
    const recurBoxes = document.querySelectorAll('.recur-chk');
    const cityBoxes = document.querySelectorAll('.city-chk');
    // The five boroughs are the default view; events outside the city are opt-in.
    const DEFAULT_CITIES = new Set({json.dumps(list(DEFAULT_CITIES))});
    function isDefaultCities(checked) {{
      return checked.length === DEFAULT_CITIES.size && checked.every(c => DEFAULT_CITIES.has(c));
    }}
    function setDefaultCities() {{
      cityBoxes.forEach(b => {{ b.checked = DEFAULT_CITIES.has(b.value); }});
    }}
    const searchInput = document.getElementById('search-input');
    const searchKbd = document.getElementById('search-kbd');
    const searchClear = document.getElementById('search-clear');
    const searchStatus = document.getElementById('search-status');
    const searchCount = document.getElementById('search-count');
    const freeOnlyChk = document.getElementById('free-only-chk');
    const guestlistOnlyChk = document.getElementById('guestlist-only-chk');
    const lgbtqOnlyChk = document.getElementById('lgbtq-only-chk');

    const locChips = document.querySelectorAll('#location-chips .loc-chip');
    const subareaBar = document.getElementById('subarea-chips-bar');
    const SUBAREAS_DATA = {json.dumps(SUBAREAS_BY_CITY)};
    function subareaLabel(li) {{
      const hit = (SUBAREAS_DATA[li.dataset.city] || []).find(s => s[0] === li.dataset.subarea);
      return hit ? hit[1] : '';
    }}
    const CITY_LABELS_MAP = {json.dumps(CITY_LABELS)};
    let activeSubarea = 'all';
    let renderedSubareaCity = null;
    const quickPicksChip = document.getElementById('quick-picks-chip');
    let picksOnly = false;
    // My Schedule: starred cards, kept in this browser. Keys are built from the card itself
    // (day|start|title), so the page doesn't carry an id on every event.
    let starredOnly = false;
    let starredEvents = new Set();
    const scheduleBar = document.getElementById('schedule-bar');
    const scheduleCount = document.getElementById('schedule-count');
    const scheduleView = document.getElementById('schedule-view');
    const quickCustomTimeChip = document.getElementById('quick-custom-time-chip');
    const activeTimeframeLabel = document.getElementById('active-timeframe-label');
    const timeFromSelect = document.getElementById('time-from-select');
    const timeToSelect = document.getElementById('time-to-select');
    const timeframeEnableChk = document.getElementById('timeframe-enable-chk');
    const customTimeRangeDiv = document.getElementById('custom-time-range');
    const timeRangeIndicator = document.getElementById('time-range-active-indicator');
    let timeFrom = null;
    let timeTo = null;
    let timeFilter = 'today';
    let currentView = 'list';
    let showPastToday = false;
    let leafletMap = null;
    let markersLayer = null;
    let mapLoading = false;
    let nearMeActive = false;
    // A dropped pin works like Near Me, measured from wherever the pin is instead of from you.
    let pinCoords = null;
    let pinPlacing = false;
    let pinMarker = null;
    let userCoords = null;

    function nearOrigin() {{
      if (pinCoords) return {{ lat: pinCoords.lat, lng: pinCoords.lng, kind: 'pin' }};
      if (userCoords && userCoords.lat && userCoords.lng) return {{ lat: userCoords.lat, lng: userCoords.lng, kind: 'me' }};
      return null;
    }}

    function updatePinUI() {{
      const hint = document.getElementById('pin-hint');
      if (hint) hint.hidden = !pinPlacing;
      const mapEl = document.getElementById('leaflet-map');
      if (mapEl) mapEl.classList.toggle('placing-pin', pinPlacing);
      const pinBtn = document.getElementById('btn-drop-pin');
      if (pinBtn) pinBtn.classList.toggle('active', pinPlacing || (nearMeActive && !!pinCoords));
      const nearBtn = document.getElementById('btn-near-me');
      if (nearBtn) nearBtn.classList.toggle('active', nearMeActive && !pinCoords);
      const label = document.getElementById('drop-pin-btn-label');
      if (label) label.textContent = pinPlacing ? 'Tap the map…' : (pinCoords ? 'Move Pin' : 'Drop Pin');
    }}

    function drawPin() {{
      if (!leafletMap || typeof L === 'undefined') return;
      if (!pinCoords) {{
        if (pinMarker) {{ leafletMap.removeLayer(pinMarker); pinMarker = null; }}
        return;
      }}
      if (!pinMarker) {{
        pinMarker = L.marker([pinCoords.lat, pinCoords.lng], {{
          icon: L.divIcon({{ className: 'drop-pin-marker', html: '<span>📌</span>', iconSize: [32, 32], iconAnchor: [9, 30] }}),
          draggable: true,
          zIndexOffset: 1000,
          title: 'Your pin: drag to move it',
        }}).addTo(leafletMap);
        pinMarker.on('dragend', () => {{
          const p = pinMarker.getLatLng();
          placePin(p.lat, p.lng);
        }});
      }} else {{
        pinMarker.setLatLng([pinCoords.lat, pinCoords.lng]);
      }}
    }}

    function startPinDrop() {{
      pinPlacing = true;
      updatePinUI();
      toggleMap(true);
      const mapWrapper = document.getElementById('map-view-wrapper');
      if (mapWrapper && mapWrapper.scrollIntoView) mapWrapper.scrollIntoView({{ behavior: 'smooth', block: 'start' }});
    }}

    function cancelPinDrop() {{
      pinPlacing = false;
      updatePinUI();
    }}

    function placePin(lat, lng) {{
      pinCoords = {{ lat: Math.round(lat * 1e5) / 1e5, lng: Math.round(lng * 1e5) / 1e5 }};
      pinPlacing = false;
      drawPin();
      setNearMe(true);
    }}

    function clearPin() {{
      pinCoords = null;
      pinPlacing = false;
      drawPin();
      updatePinUI();
    }}

    const HOURLY_TIMES = [
      {{ val: '00:00', mins: 0, label: '12:00 AM (Midnight)' }},
      {{ val: '01:00', mins: 60, label: '1:00 AM' }},
      {{ val: '02:00', mins: 120, label: '2:00 AM' }},
      {{ val: '03:00', mins: 180, label: '3:00 AM' }},
      {{ val: '04:00', mins: 240, label: '4:00 AM' }},
      {{ val: '05:00', mins: 300, label: '5:00 AM' }},
      {{ val: '06:00', mins: 360, label: '6:00 AM' }},
      {{ val: '07:00', mins: 420, label: '7:00 AM' }},
      {{ val: '08:00', mins: 480, label: '8:00 AM' }},
      {{ val: '09:00', mins: 540, label: '9:00 AM' }},
      {{ val: '10:00', mins: 600, label: '10:00 AM' }},
      {{ val: '11:00', mins: 660, label: '11:00 AM' }},
      {{ val: '12:00', mins: 720, label: '12:00 PM (Noon)' }},
      {{ val: '13:00', mins: 780, label: '1:00 PM' }},
      {{ val: '14:00', mins: 840, label: '2:00 PM' }},
      {{ val: '15:00', mins: 900, label: '3:00 PM' }},
      {{ val: '16:00', mins: 960, label: '4:00 PM' }},
      {{ val: '17:00', mins: 1020, label: '5:00 PM' }},
      {{ val: '18:00', mins: 1080, label: '6:00 PM' }},
      {{ val: '19:00', mins: 1140, label: '7:00 PM' }},
      {{ val: '20:00', mins: 1200, label: '8:00 PM' }},
      {{ val: '21:00', mins: 1260, label: '9:00 PM' }},
      {{ val: '22:00', mins: 1320, label: '10:00 PM' }},
      {{ val: '23:00', mins: 1380, label: '11:00 PM' }},
      {{ val: '24:00', mins: 1440, label: '12:00 AM (Next Midnight)' }},
      {{ val: '26:00', mins: 1560, label: '2:00 AM (Late Night)' }}
    ];

    function initTimeDropdowns() {{
      if (!timeFromSelect) return;
      timeFromSelect.innerHTML = '';
      HOURLY_TIMES.slice(0, 24).forEach(item => {{
        const opt = document.createElement('option');
        opt.value = item.val;
        opt.textContent = item.label;
        if (item.val === '20:00') opt.selected = true;
        timeFromSelect.appendChild(opt);
      }});
      syncToOptions(timeFromSelect.value, '24:00');
    }}

    function syncToOptions(fromVal, preferredToVal) {{
      if (!timeToSelect) return;
      const fromMins = parseTimeToMinutes(fromVal) ?? 1200;
      const targetToMins = parseTimeToMinutes(preferredToVal);

      let validOptions = HOURLY_TIMES.filter(item => item.mins > fromMins);
      if (validOptions.length === 0) {{
        validOptions = HOURLY_TIMES.slice(24);
      }}

      timeToSelect.innerHTML = '';
      validOptions.forEach(item => {{
        const opt = document.createElement('option');
        opt.value = item.val;
        opt.textContent = item.label;
        timeToSelect.appendChild(opt);
      }});

      const hasTarget = validOptions.some(item => item.mins === targetToMins);
      if (hasTarget && targetToMins !== null) {{
        timeToSelect.value = formatMinutesToHHMM(targetToMins);
      }} else {{
        timeToSelect.value = validOptions[0].val;
      }}
    }}

    function parseTimeToMinutes(str) {{
      if (!str || typeof str !== 'string') return null;
      str = str.trim().toLowerCase();
      if (str === 'midnight' || str === '24:00') return 1440;
      if (str === 'noon' || str === '12:00') return 720;

      const ampmMatch = str.match(/^(\\d{{1,2}})(?::(\\d{{2}}))?\\s*(am|pm)$/);
      if (ampmMatch) {{
        let h = parseInt(ampmMatch[1], 10);
        const m = ampmMatch[2] ? parseInt(ampmMatch[2], 10) : 0;
        const ampm = ampmMatch[3];
        if (ampm === 'pm' && h < 12) h += 12;
        if (ampm === 'am' && h === 12) h = 0;
        return h * 60 + m;
      }}

      const colonMatch = str.match(/^(\\d{{1,2}}):(\\d{{2}})$/);
      if (colonMatch) {{
        const h = parseInt(colonMatch[1], 10);
        const m = parseInt(colonMatch[2], 10);
        return h * 60 + m;
      }}

      const numMatch = str.match(/^(\\d{{1,2}})$/);
      if (numMatch) {{
        const n = parseInt(numMatch[1], 10);
        return n * 60;
      }}

      return null;
    }}

    function formatMinutesToHHMM(mins) {{
      if (mins === null || mins === undefined) return '';
      if (mins === 1440) return '24:00';
      if (mins === 1560) return '26:00';
      const h = Math.floor(mins / 60);
      const m = mins % 60;
      return `${{String(h).padStart(2, '0')}}:${{String(m).padStart(2, '0')}}`;
    }}

    function formatMinutesToLabel(mins) {{
      if (mins === null || mins === undefined) return '';
      if (mins === 1440) return 'Midnight';
      if (mins === 1560) return '2:00 AM';
      if (mins === 720) return '12:00 PM';
      const h24 = Math.floor(mins / 60) % 24;
      const m = mins % 60;
      const ampm = (Math.floor(mins / 60) >= 12 && Math.floor(mins / 60) < 24) ? 'PM' : 'AM';
      let h12 = h24 % 12;
      if (h12 === 0) h12 = 12;
      return m > 0 ? `${{h12}}:${{String(m).padStart(2, '0')}} ${{ampm}}` : `${{h12}} ${{ampm}}`;
    }}

    function updateTimeUI() {{
      const isCustomActive = (timeFrom !== null || timeTo !== null);
      if (timeframeEnableChk) {{
        timeframeEnableChk.checked = isCustomActive;
      }}
      if (customTimeRangeDiv) {{
        customTimeRangeDiv.style.display = isCustomActive ? 'block' : 'none';
      }}

      if (timeFromSelect && timeFrom !== null) {{
        timeFromSelect.value = formatMinutesToHHMM(timeFrom);
      }}
      const curFrom = (timeFromSelect && timeFromSelect.value) ? timeFromSelect.value : (timeFrom !== null ? formatMinutesToHHMM(timeFrom) : '20:00');
      const curTo = (timeTo !== null) ? formatMinutesToHHMM(timeTo) : (timeToSelect ? timeToSelect.value : '24:00');
      syncToOptions(curFrom, curTo);

      if (timeToSelect && timeTo !== null) {{
        timeToSelect.value = formatMinutesToHHMM(timeTo);
      }}

      if (timeRangeIndicator) {{
        if (isCustomActive) {{
          let desc = '';
          if (timeFrom !== null && timeTo !== null) {{
            desc = `Active: ${{formatMinutesToLabel(timeFrom)}} – ${{formatMinutesToLabel(timeTo)}}`;
          }} else if (timeFrom !== null) {{
            desc = `Active: From ${{formatMinutesToLabel(timeFrom)}} onwards`;
          }} else if (timeTo !== null) {{
            desc = `Active: Until ${{formatMinutesToLabel(timeTo)}}`;
          }}
          timeRangeIndicator.textContent = desc;
          timeRangeIndicator.style.display = 'block';
        }} else {{
          timeRangeIndicator.style.display = 'none';
        }}
      }}

      if (quickCustomTimeChip && activeTimeframeLabel) {{
        if (isCustomActive) {{
          let label = '';
          if (timeFrom !== null && timeTo !== null) {{
            label = `${{formatMinutesToLabel(timeFrom)}} – ${{formatMinutesToLabel(timeTo)}}`;
          }} else if (timeFrom !== null) {{
            label = `From ${{formatMinutesToLabel(timeFrom)}}`;
          }} else if (timeTo !== null) {{
            label = `Until ${{formatMinutesToLabel(timeTo)}}`;
          }}
          activeTimeframeLabel.textContent = `⏱️ ${{label}}`;
          quickCustomTimeChip.style.display = 'inline-flex';
        }} else {{
          quickCustomTimeChip.style.display = 'none';
        }}
      }}
    }}

    function setTimeRange(fromVal, toVal, skipApply = false) {{
      timeFrom = parseTimeToMinutes(fromVal);
      timeTo = parseTimeToMinutes(toVal);
      if (timeFrom !== null && timeTo !== null && timeTo <= timeFrom) {{
        timeTo = (timeFrom < 1440) ? 1440 : timeFrom + 60;
      }}
      if (timeFrom !== null && timeFrom < 720 && timeFilter === 'today') {{
        showPastToday = true;
      }}
      updateTimeUI();
      if (!skipApply) {{
        apply();
        stateToHash();
      }}
    }}

    function haversineMiles(lat1, lon1, lat2, lon2) {{
      const R = 3958.8;
      const dLat = (lat2 - lat1) * Math.PI / 180;
      const dLon = (lon2 - lon1) * Math.PI / 180;
      const a = Math.sin(dLat / 2) * Math.sin(dLat / 2) +
                Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) *
                Math.sin(dLon / 2) * Math.sin(dLon / 2);
      const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
      return R * c;
    }}

    function toggleNearMe() {{
      if (nearMeActive && !pinCoords) {{
        setNearMe(false);
        return;
      }}
      if (pinCoords) {{  // Near Me measures from you, not the pin
        clearPin();
        setNearMe(false);
      }}
      if (userCoords && userCoords.lat && userCoords.lng) {{
        setNearMe(true);
        return;
      }}
      const label = document.getElementById('near-me-btn-label');
      if (label) label.textContent = 'Locating...';
      if (!navigator.geolocation) {{
        alert('Geolocation is not supported by your browser.');
        if (label) label.textContent = 'Near Me';
        return;
      }}
      navigator.geolocation.getCurrentPosition(
        (pos) => {{
          userCoords = {{ lat: pos.coords.latitude, lng: pos.coords.longitude }};
          if (label) label.textContent = 'Near Me';
          setNearMe(true);
        }},
        (err) => {{
          if (label) label.textContent = 'Near Me';
          alert('Could not determine your location (' + (err.message || 'permission denied') + '). Please ensure location permissions are allowed in your browser.');
        }},
        {{ timeout: 10000, enableHighAccuracy: false, maximumAge: 60000 }}
      );
    }}

    function setNearMe(active) {{
      nearMeActive = !!active;
      const nearBtn = document.getElementById('btn-near-me');
      const listBtn = document.getElementById('btn-view-list');
      if (nearBtn) nearBtn.classList.toggle('active', nearMeActive);
      if (listBtn) listBtn.classList.toggle('active', !nearMeActive);
      if (!nearMeActive && pinCoords) clearPin();
      updatePinUI();
      apply();
      stateToHash();
    }}

    const mobileToggle = document.getElementById('mobile-filter-toggle');
    const mobileClose = document.getElementById('mobile-filter-close');
    const sidebarFilters = document.getElementById('sidebar-filters');
    const mobileBadge = document.getElementById('mobile-filter-badge');

    let daySections = Array.from(document.querySelectorAll('.day[data-date]'));
    const ALL_EVENT_DATES = {json.dumps(all_event_dates)};
    const eventDates = new Set(ALL_EVENT_DATES);

    // Days past the first three are inlined in <template> (live server) or split into weekly
    // deferred_days_N.html files (static export). A view fetches only the weeks it shows; the
    // next week is prefetched on idle; "all dates" and search load every week.
    let deferredHydrated = false;
    const deferredTmpl = document.getElementById('deferred-days');
    let deferredChunks = [];
    try {{ deferredChunks = JSON.parse((deferredTmpl && deferredTmpl.dataset.chunks) || '[]'); }} catch (_) {{}}
    deferredChunks.forEach(c => {{ c.state = 'idle'; }});
    if (!deferredTmpl) deferredHydrated = true;
    function insertDayFragment(fragment) {{
      const bottomNav = document.querySelector('.week-nav.bottom');
      const days = Array.from(fragment.querySelectorAll ? fragment.querySelectorAll('.day[data-date]') : []);
      const first = days.length ? days[0].dataset.date : null;
      // Keep days in date order whatever order the weeks arrive in ("tba" sorts last).
      const later = first ? Array.from(document.querySelectorAll('.day[data-date]'))
        .find(d => d.dataset.date !== 'tba' && (first === 'tba' ? false : d.dataset.date > first)) : null;
      const before = later || bottomNav;
      days.forEach(markStars);
      if (before && before.parentNode) before.parentNode.insertBefore(fragment, before);
      daySections = Array.from(document.querySelectorAll('.day[data-date]'));
      updateDayHeadings();
    }}
    function fetchChunk(c) {{
      if (!c.fetch) c.fetch = fetch(c.src).then(r => r.ok ? r.text() : '').catch(() => '');
      return c.fetch;
    }}
    function ensureDeferredDaysHydrated(wantedDates) {{
      if (deferredHydrated) return;
      if (!deferredChunks.length) {{
        // Live server: everything is inline in the <template>.
        if (deferredTmpl) {{ insertDayFragment(deferredTmpl.content); deferredTmpl.remove(); }}
        deferredHydrated = true;
        return;
      }}
      const want = wantedDates ? new Set(wantedDates) : null;
      deferredChunks.forEach(c => {{
        if (c.state !== 'idle') return;
        if (want && !c.dates.some(d => want.has(d))) return;
        c.state = 'loading';
        fetchChunk(c).then(text => {{
          const holder = document.createElement('template');
          holder.innerHTML = text || '';
          insertDayFragment(holder.content);
          c.state = 'done';
          if (deferredChunks.every(x => x.state === 'done')) {{
            deferredHydrated = true;
            if (deferredTmpl) deferredTmpl.remove();
          }}
          apply();
        }});
      }});
    }}
    (function prefetchNextWeek() {{
      const next = deferredChunks[0];
      if (!next) return;
      if ('requestIdleCallback' in window) requestIdleCallback(() => fetchChunk(next), {{ timeout: 4000 }});
      else setTimeout(() => fetchChunk(next), 2000);
    }})();
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
    // Date range from the mini calendar: first click picks a day, a second click sets the range.
    let rangeStart = null;
    let rangeEnd = null;
    function clearRange() {{ rangeStart = null; rangeEnd = null; }}
    function rangeDates() {{
      const out = [];
      if (!rangeStart || !rangeEnd) return out;
      for (let d = parseISO(rangeStart); fmtISO(d) <= rangeEnd; d = addDays(d, 1)) out.push(fmtISO(d));
      return out;
    }}

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
        // "Today · Thursday, Nov 5", but just "Saturday, Nov 7" for other days (not "Saturday · Saturday")
        const prefix = diffDays === 0 ? 'Today' : diffDays === 1 ? 'Tomorrow' : diffDays === -1 ? 'Yesterday' : '';
        h2.innerHTML = `${{prefix ? prefix + ' · ' : ''}}${{dayName}}, ${{shortStr}}${{countHtml}}`;
        day._countEl = null;  // the heading was rebuilt, so the cached count element is gone
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
      }} else if (timeFilter === 'range' && rangeStart && rangeEnd) {{
        const rs = parseISO(rangeStart), re_ = parseISO(rangeEnd);
        label = `${{fmtShort(rs)}} – ${{fmtShort(re_)}}, ${{re_.getFullYear()}}`;
      }} else if (timeFilter === 'day') {{
        label = `${{DAYS_FULL[anchor.getDay()]}}, ${{fmtShort(anchor)}}, ${{anchor.getFullYear()}}`;
      }} else {{
        label = `${{fmtShort(anchor)}} – ${{fmtShort(end)}}, ${{end.getFullYear()}}`;
      }}
      document.getElementById('week-label').textContent = label;
      const calToggle = document.getElementById('cal-toggle');
      if (calToggle) {{
        const picked = (timeFilter === 'range' && rangeStart && rangeEnd)
          ? `${{fmtShort(parseISO(rangeStart))}} – ${{fmtShort(parseISO(rangeEnd))}}`
          : (timeFilter === 'day' ? fmtShort(anchor) : '');
        calToggle.textContent = picked ? `📅 ${{picked}}` : '📅 pick date';
        calToggle.classList.toggle('active', !!picked);
      }}
      const b = document.getElementById('week-label-b');
      if (b) b.textContent = label;
      const todayBtn = document.getElementById('week-today');
      if (todayBtn) todayBtn.classList.toggle('active', !showAll && timeFilter === 'today');
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
      leafletMap.on('click', (ev) => {{
        if (pinPlacing) placePin(ev.latlng.lat, ev.latlng.lng);
      }});
      drawPin();
      if (pinCoords) leafletMap.setView([pinCoords.lat, pinCoords.lng], 14);  // a shared pin link opens on the pin
    }}

    // The map opens above the feed and is independent of the Category / Near Me choice.
    function toggleMap(forcedState) {{
      switchView((typeof forcedState === 'boolean' ? forcedState : currentView !== 'map') ? 'map' : 'list');
    }}

    function switchView(mode) {{
      currentView = mode;
      if (mode !== 'map' && pinPlacing) cancelPinDrop();
      const mapBtn = document.getElementById('btn-view-map');
      const mapWrapper = document.getElementById('map-view-wrapper');
      const mapStat = document.getElementById('map-venue-stat');

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
          // Unchecked boroughs/categories collapse their section (.empty) without hiding each event
          if (li.closest('.empty')) return;
          const lat = parseFloat(li.dataset.lat);
          const lng = parseFloat(li.dataset.lng);
          if (isNaN(lat) || isNaN(lng)) return;

          const vName = li.dataset.venueName || li.dataset.venue || 'Venue';
          const key = `${{lat.toFixed(4)}},${{lng.toFixed(4)}}`;
          if (!venueMap.has(key)) {{
            venueMap.set(key, {{
              lat, lng,
              name: vName,
              neighborhood: li.dataset.neighborhood || subareaLabel(li) || '',
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
      if (quickPicksChip) {{
        quickPicksChip.classList.toggle('active', picksOnly);
        quickPicksChip.setAttribute('aria-pressed', picksOnly ? 'true' : 'false');
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
      const checkedCities = Array.from(cityBoxes).filter(b => b.checked).map(b => b.value);
      locChips.forEach(chip => {{
        const city = chip.dataset.city;
        if (city === 'all') {{
          chip.classList.toggle('active', isDefaultCities(checkedCities) || checkedCities.length === 0);
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
          const matched = document.querySelectorAll('.day:not(.out-of-week) .event:not(.hidden)').length;
          searchCount.textContent = matched;
          searchStatus.hidden = false;
        }} else {{
          searchStatus.hidden = true;
        }}
      }}
    }}

    function updateMobileBadge() {{
      const isCatFiltered = isCatFilteredFn();
      const allVenues = venueBoxes.length;
      const chkVenues = Array.from(venueBoxes).filter(b => b.checked).length;
      const citiesDefault = isDefaultCities(Array.from(cityBoxes).filter(b => b.checked).map(b => b.value));
      const allRecurs = recurBoxes.length;
      const chkRecurs = Array.from(recurBoxes).filter(b => b.checked).length;
      const isFree = freeOnlyChk && freeOnlyChk.checked;
      const isGuestlist = guestlistOnlyChk && guestlistOnlyChk.checked;
      const isLgbtq = lgbtqOnlyChk && lgbtqOnlyChk.checked;
      const isTimeFiltered = (timeFrom !== null || timeTo !== null);
      const isGenreFiltered = Array.from(genreBoxes).some(b => !b.checked);
      const isFiltered = isCatFiltered || isGenreFiltered || (chkVenues < allVenues) || !citiesDefault || (chkRecurs < allRecurs) || isFree || isGuestlist || isLgbtq || starredOnly || picksOnly || isTimeFiltered || (activeSubarea !== 'all') || (searchInput && !!searchInput.value.trim());

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
      if (nearMeActive && pinCoords) params.set('pin', `${{pinCoords.lat}},${{pinCoords.lng}}`);

      if (isCatFilteredFn()) {{
        const checkedCats = Array.from(catBoxes).filter(b => b.checked).map(b => b.value);
        if (checkedCats.length === catBoxes.length) params.set('cat', 'all');
        else params.set('cat', checkedCats.length ? checkedCats.join(',') : 'none');
      }}
      const checkedGenres = Array.from(genreBoxes).filter(b => b.checked).map(b => b.value);
      if (checkedGenres.length < genreBoxes.length) params.set('genre', checkedGenres.length ? checkedGenres.join(',') : 'none');

      const checkedCities = Array.from(cityBoxes).filter(b => b.checked).map(b => b.value);
      if (checkedCities.length > 0 && !isDefaultCities(checkedCities)) params.set('city', checkedCities.join(','));
      if (activeSubarea && activeSubarea !== 'all') params.set('sub', activeSubarea);

      const allRecurs = Array.from(recurBoxes).map(b => b.value);
      const checkedRecurs = Array.from(recurBoxes).filter(b => b.checked).map(b => b.value);
      if (checkedRecurs.length > 0 && checkedRecurs.length < allRecurs.length) params.set('recur', checkedRecurs.join(','));

      const allVenues = Array.from(venueBoxes).map(b => b.value);
      const checkedVenues = Array.from(venueBoxes).filter(b => b.checked).map(b => b.value);
      if (checkedVenues.length > 0 && checkedVenues.length < allVenues.length) params.set('venues', checkedVenues.join(';'));

      if (freeOnlyChk && freeOnlyChk.checked) params.set('free', '1');
      if (guestlistOnlyChk && guestlistOnlyChk.checked) params.set('guestlist', '1');
      if (lgbtqOnlyChk && lgbtqOnlyChk.checked) params.set('lgbtq', '1');
      if (picksOnly) params.set('picks', '1');
      if (starredOnly) params.set('saved', '1');
      if (timeFrom !== null || timeTo !== null) {{
        if (timeFrom !== null) params.set('from', formatMinutesToHHMM(timeFrom));
        if (timeTo !== null) params.set('to', formatMinutesToHHMM(timeTo));
      }}

      if (timeFilter !== 'today') params.set('t', timeFilter);
      if (timeFilter === 'range' && rangeStart && rangeEnd) {{
        params.set('d', rangeStart);
        params.set('d_end', rangeEnd);
      }} else if ((timeFilter === 'day' || timeFilter === 'week') && fmtISO(anchor) !== todayISO) {{
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
        if (params.get('lgbtq') === '1' && lgbtqOnlyChk) lgbtqOnlyChk.checked = true;
        if (params.get('picks') === '1') picksOnly = true;
        if (params.get('saved') === '1') starredOnly = true;
        if (params.get('past') === '1') showPastToday = true;
        if (params.get('v') === 'map') {{
          switchView('map');
        }}
        const pinParam = params.has('pin') ? params.get('pin').split(',').map(Number) : null;
        if (pinParam && pinParam.length === 2 && pinParam.every(n => isFinite(n)) &&
            Math.abs(pinParam[0]) <= 90 && Math.abs(pinParam[1]) <= 180) {{
          pinCoords = {{ lat: pinParam[0], lng: pinParam[1] }};
          nearMeActive = true;
          updatePinUI();
          switchView('map');
        }}

        if (params.has('from') || params.has('tfrom') || params.has('to') || params.has('tto')) {{
          const f = params.get('from') || params.get('tfrom');
          const t = params.get('to') || params.get('tto');
          setTimeRange(f, t, true);
        }} else {{
          setTimeRange(null, null, true);
        }}

        if (params.has('t')) {{
          timeFilter = params.get('t');
          showAll = (timeFilter === 'all');
        }}

        if (params.has('cat')) {{
          const catVal = params.get('cat');
          if (catVal === 'all') catBoxes.forEach(b => {{ b.checked = true; }});
          else if (catVal === 'none') catBoxes.forEach(b => {{ b.checked = false; }});
          else {{
            const vals = new Set(catVal.split(','));
            catBoxes.forEach(b => {{ b.checked = vals.has(b.value); }});
          }}
        }}
        {{
          const gVal = params.get('genre');
          const gVals = gVal ? new Set(gVal.split(',')) : null;
          genreBoxes.forEach(b => {{ b.checked = !gVals || gVals.has(b.value); }});
          syncSubgenreUI();
        }}

        if (params.has('city')) {{
          const vals = new Set(params.get('city').split(','));
          cityBoxes.forEach(b => {{ b.checked = vals.has(b.value); }});
        }} else {{
          setDefaultCities();
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
          }} else if (params.has('d_end')) {{
            rangeStart = d;
            rangeEnd = params.get('d_end');
            timeFilter = 'range';
            showAll = false;
            anchor = parseISO(rangeStart);
            calMonth = new Date(anchor.getFullYear(), anchor.getMonth(), 1);
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
      // My Schedule shows everything saved, whatever the category and borough boxes say.
      const boxOn = b => starredOnly || b.checked;
      const cats = new Set(Array.from(catBoxes).filter(boxOn).map(b => b.value));
      const genres = new Set(Array.from(genreBoxes).filter(boxOn).map(b => b.value));
      const allGenresOn = genres.size === genreBoxes.length;
      const genreOkFor = (bucket, genre) => allGenresOn || bucket !== MUSIC_BUCKET || (!!genre && genres.has(genre));
      const venues = new Set(Array.from(venueBoxes).filter(boxOn).map(b => b.value));
      const recurs = new Set(Array.from(recurBoxes).filter(boxOn).map(b => b.value));
      const cities = new Set(Array.from(cityBoxes).filter(boxOn).map(b => b.value));
      const starDates = starredOnly ? new Set(Array.from(starredEvents).map(k => k.split('|')[0])) : null;
      const searchText = searchInput.value.trim().toLowerCase();
      const freeOnly = freeOnlyChk ? freeOnlyChk.checked : false;
      const guestlistOnly = guestlistOnlyChk ? guestlistOnlyChk.checked : false;
      const lgbtqOnly = lgbtqOnlyChk ? lgbtqOnlyChk.checked : false;
      const week = new Set(weekDates());

      const nowEpoch = Math.floor(Date.now() / 1000);
      const twoHoursAgoEpoch = nowEpoch - 7200;
      const cutoffDate = new Date(Date.now() - 7200 * 1000);
      const cutoffTimeStr = cutoffDate.toLocaleTimeString('en-US', {{
        timeZone: 'America/New_York',
        hour: 'numeric',
        minute: '2-digit'
      }});

      const todayDate = parseISO(todayISO);
      const dayOfWeek = todayDate.getDay();
      let daysToSat = (6 - dayOfWeek + 7) % 7;
      if (dayOfWeek === 0) daysToSat = -1;
      const satISO = fmtISO(addDays(todayDate, daysToSat));
      const sunISO = fmtISO(addDays(todayDate, daysToSat + 1));
      const tomorrowISO = fmtISO(addDays(todayDate, 1));
      const anchorISO = fmtISO(anchor);

      let hiddenPastCount = 0;
      let totalTodayEventsCount = 0;
      let visibleTonightCount = 0;

      // Load the deferred weeks this view needs ("all dates" and search need every week)
      if (!deferredHydrated) {{
        if (starredOnly) {{
          const loaded = new Set(daySections.map(d => d.dataset.date));
          const missing = Array.from(starDates).filter(dt => eventDates.has(dt) && !loaded.has(dt));
          if (missing.length) ensureDeferredDaysHydrated(missing);
        }} else if (timeFilter === 'all' || showAll || searchText.length > 0) {{
          ensureDeferredDaysHydrated(null);
        }} else {{
          const wanted = timeFilter === 'today' ? [todayISO]
            : timeFilter === 'tomorrow' ? [tomorrowISO]
            : timeFilter === 'weekend' ? [satISO, sunISO]
            : timeFilter === 'day' ? [anchorISO]
            : timeFilter === 'range' ? rangeDates()
            : Array.from(week || []);
          const loaded = new Set(daySections.map(d => d.dataset.date));
          const missing = wanted.filter(dt => eventDates.has(dt) && !loaded.has(dt));
          if (missing.length) ensureDeferredDaysHydrated(missing);
        }}
      }}

      // Determine active days first so we only filter DOM nodes inside visible days
      const activeDays = daySections.filter(day => {{
        const date = day.dataset.date;
        let inTime = true;
        if (starredOnly) {{
          inTime = starDates.has(date);
        }} else if (timeFilter === 'today') {{
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
          inTime = (timeFilter === 'range' && rangeStart && rangeEnd)
            ? (date >= rangeStart && date <= rangeEnd)
            : (showAll || date === 'tba' || week.has(date));
        }}
        day.classList.toggle('out-of-week', !inTime);
        return inTime;
      }});

      activeDays.forEach(day => {{
        const date = day.dataset.date;
        const isToday = (date === todayISO);
        const isPastDay = Boolean(date && date !== 'tba' && date < todayISO);

        // Walk day -> borough section -> category bucket, skipping whole containers that are
        // filtered out, caching each card's parsed attributes, and touching the DOM only when a
        // card's visibility or a count actually changes.
        const setCount = (el, n) => {{ if (el && el._val !== n) {{ el._val = n; el.textContent = n; }} }};
        const pruneEvents = (container, events) => {{
          if (container._pruned) return;
          container._pruned = true;
          events.forEach(li => {{ if (li._meta && !li._meta.hidden) {{ li._meta.hidden = true; li.classList.add('hidden'); }} else if (!li._meta) li.classList.add('hidden'); }});
        }};
        let dayVisible = 0;
        const citySections = day._citySections || (day._citySections = Array.from(day.querySelectorAll('.cities .city-section')));
        citySections.forEach(sec => {{
          const buckets = sec._buckets || (sec._buckets = Array.from(sec.querySelectorAll('.bucket')));
          const secEvents = sec._events || (sec._events = Array.from(sec.querySelectorAll('.event')));
          const secCity = sec.dataset.city;
          if (secCity && !cities.has(secCity)) {{
            pruneEvents(sec, secEvents);
            buckets.forEach(b => {{ b._pruned = true; b.classList.add('empty'); setCount(b._countEl || (b._countEl = b.querySelector('.bucket-head .count')), 0); }});
            sec.classList.add('empty');
            setCount(sec._countEl || (sec._countEl = sec.querySelector('.city-head .count')), 0);
            return;
          }}
          sec._pruned = false;
          let cityVisible = 0;
          buckets.forEach(b => {{
            const events = b._events || (b._events = Array.from(b.querySelectorAll('.event')));
            const countEl = b._countEl || (b._countEl = b.querySelector('.bucket-head .count'));
            if (!cats.has(b.dataset.bucket)) {{
              pruneEvents(b, events);
              b.classList.add('empty');
              setCount(countEl, 0);
              return;
            }}
            b._pruned = false;
            let bucketVisible = 0;
            events.forEach(li => {{
              let m = li._meta;
              if (!m) {{
                const tm = li.dataset.timeMins;
                m = li._meta = {{
                  bucket: li.dataset.bucket,
                  genre: li.dataset.genre || '',
                  venue: li.dataset.venue,
                  presenter: li.dataset.presenter || '',
                  recur: li.dataset.recur,
                  city: li.dataset.city,
                  subarea: li.dataset.subarea,
                  free: li.dataset.free === 'true',
                  guestlist: li.dataset.guestlist === 'true',
                  lgbtq: li.dataset.lgbtq === 'true',
                  featured: li.dataset.highlight === 'true',
                  timeMins: tm ? parseInt(tm, 10) : -1,
                  epoch: li.dataset.epoch ? parseInt(li.dataset.epoch, 10) : 0,
                  text: null,
                  hidden: li.classList.contains('hidden'),
                  past: li.classList.contains('past-time'),
                }};
              }}
              const venueOk = venues.has(m.venue) || (m.presenter && venues.has(m.presenter));
              const recurOk = recurs.has(m.recur);
              const cityOk = cities.has(m.city);
              const subareaOk = (activeSubarea === 'all') || (m.subarea === activeSubarea);
              const freeOk = !freeOnly || m.free;
              const guestlistOk = !guestlistOnly || m.guestlist;
              const lgbtqOk = !lgbtqOnly || m.lgbtq;
              const picksOk = !picksOnly || m.featured;
              const starOk = !starredOnly || starredEvents.has(eventKey(li));
              const searchOk = !searchText || (m.text || (m.text = li.textContent.toLowerCase())).includes(searchText);

              let todOk = true;
              if (timeFrom !== null || timeTo !== null) {{
                if (m.timeMins >= 0) {{
                  if (timeFrom !== null && m.timeMins < timeFrom) todOk = false;
                  if (timeTo !== null && m.timeMins > timeTo) todOk = false;
                }} else {{
                  todOk = false;
                }}
              }}

              const isPastTime = isToday && m.epoch > 0 && m.epoch < twoHoursAgoEpoch;
              const isPast = isPastDay || isPastTime;
              if (isToday && m.epoch > 0) totalTodayEventsCount++;
              if (m.past !== isPast) {{ m.past = isPast; li.classList.toggle('past-time', isPast); }}

              let timePastOk = true;
              if (isPast && !showPastToday && !starredOnly) {{
                timePastOk = false;
                hiddenPastCount++;
              }}

              const genreOk = genreOkFor(m.bucket, m.genre);
              const isVisible = genreOk && venueOk && recurOk && cityOk && subareaOk && searchOk && freeOk && guestlistOk && lgbtqOk && picksOk && starOk && todOk && timePastOk;
              if (m.hidden === isVisible) {{ m.hidden = !isVisible; li.classList.toggle('hidden', !isVisible); }}
              if (isVisible) {{
                bucketVisible++;
                if (isToday && !isPast) visibleTonightCount++;
              }}
            }});
            b.classList.toggle('empty', bucketVisible === 0);
            setCount(countEl, bucketVisible);
            cityVisible += bucketVisible;
          }});
          sec.classList.toggle('empty', cityVisible === 0);
          setCount(sec._countEl || (sec._countEl = sec.querySelector('.city-head .count')), cityVisible);
          dayVisible += cityVisible;
        }});

        const visible = dayVisible;
        day.classList.toggle('empty', visible === 0);
        setCount(day._countEl || (day._countEl = day.querySelector('h2 .count')), visible);

        // Proximity calculation & Near Me sorting (only when Near Me button was clicked)
        const nearStream = day.querySelector('.near-me-stream');
        const citiesDiv = day.querySelector('.cities');

        if (nearStream && citiesDiv) {{
          const origin = nearMeActive ? nearOrigin() : null;
          if (origin) {{
            citiesDiv.style.display = 'none';
            nearStream.style.display = 'block';

            // Always query the master list of visible events in citiesDiv
            const visibleEvents = Array.from(citiesDiv.querySelectorAll('.event:not(.hidden)')).filter(ev => !ev.closest('.empty'));

            const eventDistances = [];
            visibleEvents.forEach(ev => {{
              const lat = parseFloat(ev.dataset.lat);
              const lng = parseFloat(ev.dataset.lng);
              let dist = 99999;
              if (!isNaN(lat) && !isNaN(lng)) {{
                dist = haversineMiles(origin.lat, origin.lng, lat, lng);
              }}
              const timeMins = parseInt(ev.dataset.timeMins || '9999', 10);
              eventDistances.push({{ ev: ev, dist: dist, timeMins: timeMins }});
            }});

            eventDistances.sort((a, b) => {{
              if (a.dist !== b.dist) return a.dist - b.dist;
              return a.timeMins - b.timeMins;
            }});

            const locatedCount = eventDistances.filter(item => item.dist < 9999).length;

            let banner = nearStream.querySelector('.near-stream-banner');
            if (!banner) {{
              banner = document.createElement('div');
              banner.className = 'near-stream-banner';
              nearStream.appendChild(banner);
            }}
            const fromPin = origin.kind === 'pin';
            banner.innerHTML = `
              <div class="near-stream-info">
                <span class="chip-icon">${{fromPin ? '📌' : '📍'}} </span>
                <span><strong>Sorted by distance from ${{fromPin ? 'your pin' : 'your location'}}</strong> (${{locatedCount}} events nearby)</span>
              </div>
              <div class="near-stream-actions">
                ${{fromPin ? '<button type="button" class="near-stream-clear-btn" id="btn-move-pin">Move Pin</button>' : ''}}
                <button type="button" class="near-stream-clear-btn" id="btn-reset-near">Reset to Category View</button>
              </div>
            `;

            let list = nearStream.querySelector('.near-events-list');
            if (!list) {{
              list = document.createElement('ul');
              list.className = 'near-events-list';
              nearStream.appendChild(list);
            }}
            list.innerHTML = '';

            eventDistances.forEach(item => {{
              // Clone the element so the master list in citiesDiv remains 100% intact
              const clone = item.ev.cloneNode(true);
              clone.classList.remove('hidden');

              if (item.dist < 9999) {{
                const away = origin.kind === 'pin' ? 'from pin' : 'away';
                const dStr = item.dist < 0.1 ? `< 0.1 mi ${{away}}` : `${{item.dist.toFixed(1)}} mi ${{away}}`;
                let badge = clone.querySelector('.dist-badge');
                if (!badge) {{
                  badge = document.createElement('span');
                  badge.className = 'dist-badge';
                  const vTag = clone.querySelector('.venue-tag');
                  if (vTag) vTag.appendChild(badge);
                }}
                badge.title = `${{item.dist.toFixed(2)}} miles ${{away}}`;
                badge.innerHTML = `<span class="chip-icon">📍 </span>${{dStr}}`;
              }}

              list.appendChild(clone);
            }});
          }} else {{
            nearStream.style.display = 'none';
            nearStream.innerHTML = '';
            citiesDiv.style.display = 'block';
          }}
        }}
      }});

      daySections.filter(d => !activeDays.includes(d)).forEach(day => {{
        const nearStream = day.querySelector('.near-me-stream');
        const citiesDiv = day.querySelector('.cities');
        if (nearStream && citiesDiv) {{
          nearStream.style.display = 'none';
          nearStream.innerHTML = '';
          citiesDiv.style.display = 'block';
        }}
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

      const ongoingEl = document.querySelector('.ongoing');
      if (ongoingEl) {{
        const showOngoing = (timeFilter === 'all' || showAll);
        ongoingEl.style.display = showOngoing ? '' : 'none';
        if (showOngoing) {{
          ongoingEl.querySelectorAll('.event').forEach(li => {{
            const catOk = cats.has(li.dataset.bucket);
            const venueOk = venues.has(li.dataset.venue) || (li.dataset.presenter && venues.has(li.dataset.presenter));
            const recurOk = recurs.has(li.dataset.recur);
            const cityOk = cities.has(li.dataset.city);
            const subareaOk = (activeSubarea === 'all') || (li.dataset.subarea === activeSubarea);
            const freeOk = !freeOnly || li.dataset.free === 'true';
            const guestlistOk = !guestlistOnly || li.dataset.guestlist === 'true';
            const lgbtqOk = !lgbtqOnly || li.dataset.lgbtq === 'true';
            const searchOk = !searchText || li.textContent.toLowerCase().includes(searchText);
            const genreOk = genreOkFor(li.dataset.bucket, li.dataset.genre);
            const isVisible = catOk && genreOk && venueOk && recurOk && cityOk && subareaOk && searchOk && freeOk && guestlistOk && lgbtqOk;
            li.classList.toggle('hidden', !isVisible);
          }});
        }}
      }}

      const visibleDays = daySections.filter(d => !d.classList.contains('out-of-week') && !d.classList.contains('empty')).length;
      const noEventsEl = document.getElementById('no-events-msg');
      if (noEventsEl) {{
        noEventsEl.style.display = (visibleDays === 0) ? 'block' : 'none';
      }}

      renderCal();
      updateWeekLabel();
      updateQuickChipsUI();
      updateScheduleBar();
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
        if (timeFilter === 'range' && rangeStart && rangeEnd) {{
          if (iso === rangeStart) classes.push('range-start');
          if (iso === rangeEnd) classes.push('range-end');
          if (iso > rangeStart && iso < rangeEnd) classes.push('in-range');
        }} else {{
          if (!showAll && timeFilter === 'week' && week.has(iso)) classes.push('in-week');
          if (iso === fmtISO(anchor)) classes.push(rangeStart && !rangeEnd ? 'range-start' : 'anchor');
        }}
        html += `<div class="${{classes.join(' ')}}" data-date="${{iso}}">${{d}}</div>`;
      }}
      grid.innerHTML = html;
      const hint = document.getElementById('cal-hint');
      if (hint) {{
        if (timeFilter === 'range' && rangeStart && rangeEnd) hint.textContent = `${{fmtShort(parseISO(rangeStart))}} – ${{fmtShort(parseISO(rangeEnd))}} · click any date to start over`;
        else if (rangeStart && !rangeEnd) hint.textContent = `${{fmtShort(parseISO(rangeStart))}} selected · click a second date for a range`;
        else hint.textContent = 'Pick a date, or click a second date for a range';
      }}
    }}

    function shiftNav(delta) {{
      if (timeFilter === 'range' && rangeStart && rangeEnd) {{
        const span = rangeDates().length;
        rangeStart = fmtISO(addDays(parseISO(rangeStart), delta * span));
        rangeEnd = fmtISO(addDays(parseISO(rangeEnd), delta * span));
        anchor = parseISO(rangeStart);
        showAll = false;
        calMonth = new Date(anchor.getFullYear(), anchor.getMonth(), 1);
        apply();
        return;
      }}
      clearRange();
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

    if (quickPicksChip) quickPicksChip.addEventListener('click', () => {{ picksOnly = !picksOnly; apply(); stateToHash(); }});
    if (guestlistOnlyChk) guestlistOnlyChk.addEventListener('change', apply);
    if (lgbtqOnlyChk) lgbtqOnlyChk.addEventListener('change', apply);

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
      clearRange();
      timeFilter = 'today';
      showAll = false;
      anchor = parseISO(todayISO);
      calMonth = new Date(anchor.getFullYear(), anchor.getMonth(), 1);
      apply();
    }});
    const weekAllBtn = document.getElementById('week-all');
    if (weekAllBtn) weekAllBtn.addEventListener('click', () => {{
      clearRange();
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
      const iso = cell.dataset.date;
      if (rangeStart && !rangeEnd && iso !== rangeStart) {{
        rangeEnd = iso > rangeStart ? iso : rangeStart;
        rangeStart = iso > rangeStart ? rangeStart : iso;
        timeFilter = 'range';
        showAll = false;
        anchor = parseISO(rangeStart);
        apply();
        return;
      }}
      rangeStart = iso;
      rangeEnd = null;
      setAnchor(iso);
    }});

    if (freeOnlyChk) freeOnlyChk.addEventListener('change', apply);
    catBoxes.forEach(b => b.addEventListener('change', () => {{
      if (b.value === MUSIC_BUCKET) genreBoxes.forEach(g => {{ g.checked = b.checked; }});
      syncSubgenreUI();
      apply();
    }}));
    genreBoxes.forEach(g => g.addEventListener('change', () => {{
      const music = Array.from(catBoxes).find(b => b.value === MUSIC_BUCKET);
      if (music) music.checked = Array.from(genreBoxes).some(x => x.checked);
      syncSubgenreUI();
      apply();
    }}));
    const setAllGenres = (on) => {{
      genreBoxes.forEach(g => {{ g.checked = on; }});
      const music = Array.from(catBoxes).find(b => b.value === MUSIC_BUCKET);
      if (music) music.checked = on;
      syncSubgenreUI();
      apply();
    }};
    const genreAllBtn = document.getElementById('genre-all');
    if (genreAllBtn) genreAllBtn.addEventListener('click', () => setAllGenres(true));
    const genreNoneBtn = document.getElementById('genre-none');
    if (genreNoneBtn) genreNoneBtn.addEventListener('click', () => setAllGenres(false));
    // Clicking a genre pill on a card shows only that genre; clicking it again shows all.
    document.addEventListener('click', (e) => {{
      const pill = e.target.closest && e.target.closest('button.genre-pill');
      if (!pill) return;
      e.preventDefault();
      e.stopPropagation();
      const gid = pill.dataset.genre;
      const onlyThis = Array.from(genreBoxes).every(g => g.checked === (g.value === gid));
      genreBoxes.forEach(g => {{ g.checked = onlyThis ? true : (g.value === gid); }});
      const music = Array.from(catBoxes).find(b => b.value === MUSIC_BUCKET);
      if (music) music.checked = true;
      syncSubgenreUI();
      apply();
    }});
    venueBoxes.forEach(b => b.addEventListener('change', apply));
    recurBoxes.forEach(b => b.addEventListener('change', apply));
    cityBoxes.forEach(b => b.addEventListener('change', apply));
    searchInput.addEventListener('input', apply);
    document.getElementById('cat-all').addEventListener('click', () => {{ catBoxes.forEach(b => b.checked = true); genreBoxes.forEach(g => g.checked = true); syncSubgenreUI(); apply(); }});
    document.getElementById('cat-none').addEventListener('click', () => {{ catBoxes.forEach(b => b.checked = false); genreBoxes.forEach(g => g.checked = false); syncSubgenreUI(); apply(); }});
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
      if (lgbtqOnlyChk) lgbtqOnlyChk.checked = false;
      picksOnly = false;
      starredOnly = false;
      clearRange();
      timeFrom = null;
      timeTo = null;
      if (timeframeEnableChk) timeframeEnableChk.checked = false;
      if (customTimeRangeDiv) customTimeRangeDiv.style.display = 'none';
      updateTimeUI();
      activeSubarea = 'all';
      catBoxes.forEach(b => b.checked = isDefaultCat(b));
      genreBoxes.forEach(g => g.checked = true);
      syncSubgenreUI();
      setDefaultCities();
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
          setDefaultCities();
        }} else {{
          const checked = Array.from(cityBoxes).filter(b => b.checked).map(b => b.value);
          if (checked.length === 1 && checked[0] === targetCity) {{
            setDefaultCities();
          }} else {{
            cityBoxes.forEach(b => {{
              b.checked = (b.value === targetCity);
            }});
          }}
        }}
        apply();
      }});
    }});

    if (quickCustomTimeChip) {{
      quickCustomTimeChip.addEventListener('click', () => {{
        if (timeframeEnableChk) timeframeEnableChk.checked = false;
        if (customTimeRangeDiv) customTimeRangeDiv.style.display = 'none';
        setTimeRange(null, null);
      }});
    }}

    if (timeframeEnableChk) {{
      timeframeEnableChk.addEventListener('change', () => {{
        if (timeframeEnableChk.checked) {{
          if (customTimeRangeDiv) customTimeRangeDiv.style.display = 'block';
          const f = (timeFromSelect && timeFromSelect.value) ? timeFromSelect.value : '20:00';
          const t = (timeToSelect && timeToSelect.value) ? timeToSelect.value : '24:00';
          setTimeRange(f, t);
        }} else {{
          if (customTimeRangeDiv) customTimeRangeDiv.style.display = 'none';
          setTimeRange(null, null);
        }}
      }});
    }}

    if (timeFromSelect) {{
      timeFromSelect.addEventListener('change', () => {{
        const f = timeFromSelect.value;
        const currentTo = timeToSelect ? timeToSelect.value : '24:00';
        syncToOptions(f, currentTo);
        const t = timeToSelect ? timeToSelect.value : '24:00';
        if (timeframeEnableChk) timeframeEnableChk.checked = true;
        setTimeRange(f, t);
      }});
    }}
    if (timeToSelect) {{
      timeToSelect.addEventListener('change', () => {{
        const f = timeFromSelect ? timeFromSelect.value : '20:00';
        const t = timeToSelect.value;
        if (timeframeEnableChk) timeframeEnableChk.checked = true;
        setTimeRange(f, t);
      }});
    }}

    const btnViewList = document.getElementById('btn-view-list');
    if (btnViewList) btnViewList.addEventListener('click', () => {{ if (nearMeActive) setNearMe(false); }});

    const btnViewMap = document.getElementById('btn-view-map');
    if (btnViewMap) btnViewMap.addEventListener('click', () => toggleMap());

    const btnNearMe = document.getElementById('btn-near-me');
    if (btnNearMe) btnNearMe.addEventListener('click', () => toggleNearMe());
    const btnDropPin = document.getElementById('btn-drop-pin');
    if (btnDropPin) {{
      btnDropPin.addEventListener('click', () => {{
        if (pinPlacing) cancelPinDrop();
        else startPinDrop();
      }});
    }}
    const pinCancelBtn = document.getElementById('pin-cancel-btn');
    if (pinCancelBtn) pinCancelBtn.addEventListener('click', cancelPinDrop);

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
        const pinLi = jumpBtn.closest('li') || jumpBtn;
        const lat = parseFloat(jumpBtn.dataset.lat || pinLi.dataset.lat);
        const lng = parseFloat(jumpBtn.dataset.lng || pinLi.dataset.lng);
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
      if (e.target && e.target.id === 'btn-reset-near') {{
        setNearMe(false);
      }} else if (e.target && e.target.id === 'btn-move-pin') {{
        startPinDrop();
      }} else if (e.target && e.target.id === 'btn-toggle-past') {{
        showPastToday = !showPastToday;
        apply();
      }} else if (e.target && e.target.id === 'btn-banner-tomorrow') {{
        clearRange();
        timeFilter = 'tomorrow';
        showAll = false;
        anchor = addDays(parseISO(todayISO), 1);
        calMonth = new Date(anchor.getFullYear(), anchor.getMonth(), 1);
        apply();
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

    function extractEventMetaFromLi(li) {{
      const a = li.querySelector('.what a');
      const title = a ? a.textContent.trim() : 'Event';
      const url = a ? a.href : '';
      const vLink = li.querySelector('.venue-link');
      const venue = vLink ? vLink.textContent.trim() : (li.dataset.venue || '');
      const city = li.dataset.city || 'nyc';
      const daySec = li.closest('.day');
      const dayDate = daySec ? daySec.dataset.date : '';
      const whenText = (li.querySelector('.when')?.textContent || '').trim();
      let dt = null;
      if (dayDate && dayDate !== 'tba') {{
        const timeMatch = whenText.match(/(\\d{{1,2}})(?::(\\d{{2}}))?\\s*(am|pm)/i);
        let h = 19, m = 0;
        if (timeMatch) {{
          h = parseInt(timeMatch[1], 10);
          m = timeMatch[2] ? parseInt(timeMatch[2], 10) : 0;
          const ap = timeMatch[3].toLowerCase();
          if (ap === 'pm' && h < 12) h += 12;
          if (ap === 'am' && h === 12) h = 0;
        }}
        const [y, mo, da] = dayDate.split('-').map(Number);
        dt = new Date(y, mo - 1, da, h, m);
      }}
      return {{ title, url, venue, city, dt, dayDate }};
    }}

    function toCalUTC(d) {{
      function p(n) {{ return String(n).padStart(2, '0'); }}
      return d.getUTCFullYear() + p(d.getUTCMonth()+1) + p(d.getUTCDate()) + 'T' +
             p(d.getUTCHours()) + p(d.getUTCMinutes()) + p(d.getUTCSeconds()) + 'Z';
    }}

    document.addEventListener('click', (e) => {{
      const gBtn = e.target.closest('.gcal-btn');
      if (gBtn) {{
        e.preventDefault();
        const li = gBtn.closest('.event');
        if (!li) return;
        const m = extractEventMetaFromLi(li);
        if (!m.dt) return;
        const start = toCalUTC(m.dt);
        const end = toCalUTC(new Date(m.dt.getTime() + 2 * 3600 * 1000));
        const loc = `${{m.venue}}, ${{m.city.charAt(0).toUpperCase() + m.city.slice(1)}}, NY`;
        const nl = String.fromCharCode(10);
        const details = `Details & Tickets: ${{m.url}}` + nl + nl + `Discovered on NYC Events`;
        const gUrl = `https://calendar.google.com/calendar/render?action=TEMPLATE&text=${{encodeURIComponent(m.title)}}&dates=${{start}}/${{end}}&details=${{encodeURIComponent(details)}}&location=${{encodeURIComponent(loc)}}`;
        window.open(gUrl, '_blank', 'noopener');
        return;
      }}

      const icsBtn = e.target.closest('.ics-btn');
      if (icsBtn) {{
        e.preventDefault();
        const li = icsBtn.closest('.event');
        if (!li) return;
        const m = extractEventMetaFromLi(li);
        if (!m.dayDate) return;
        downloadICS(m.title, m.dayDate, m.venue, m.url);
        return;
      }}
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
    initTimeDropdowns();
    const THEME_KEY = 'nyc_events_theme';
    const THEME_MANUAL_KEY = 'nyc_events_theme_manual';
    const VALID_THEMES = BASE_THEMES.concat(HOLIDAY_KEYS);
    function setTheme(t, save) {{
      const theme = VALID_THEMES.includes(t) ? t : 'classic';
      document.documentElement.setAttribute('data-theme', theme);
      document.querySelectorAll('.theme-pill-btn').forEach(b => {{
        const on = b.dataset.theme === theme;
        b.classList.toggle('active', on);
        b.setAttribute('aria-checked', on ? 'true' : 'false');
      }});
      if (save) {{
        try {{ localStorage.setItem(THEME_KEY, theme); localStorage.setItem(THEME_MANUAL_KEY, localISODate(new Date())); }} catch (_) {{}}
      }}
    }}
    document.querySelectorAll('.theme-pill-btn').forEach(btn => btn.addEventListener('click', () => setTheme(btn.dataset.theme, true)));
    setTheme(document.documentElement.getAttribute('data-theme') || '{default_theme}', false);
    // Until the visitor picks a theme, follow their device when it switches (e.g. at sunset).
    try {{
      const schemeQuery = window.matchMedia('(prefers-color-scheme: light)');
      const followDevice = () => {{
        let picked = null;
        try {{ picked = localStorage.getItem(THEME_KEY); }} catch (_) {{}}
        if (!picked) setTheme(pickTheme(), false);
      }};
      if (schemeQuery.addEventListener) schemeQuery.addEventListener('change', followDevice);
      else if (schemeQuery.addListener) schemeQuery.addListener(followDevice);
    }} catch (_) {{}}

    // My Schedule. Sharing puts the event details in the link itself, so a shared schedule needs no
    // account or server and keeps working after its events roll off the site.
    const scheduleModal = document.getElementById('schedule-share-modal');
    const scheduleName = document.getElementById('schedule-share-name');
    const scheduleLink = document.getElementById('schedule-share-link');
    const scheduleSub = document.getElementById('schedule-share-sub');
    const scheduleCopy = document.getElementById('schedule-share-copy');
    const scheduleSend = document.getElementById('schedule-share-send');
    const scheduleOpen = document.getElementById('schedule-share-open');
    const STARRED_KEY = 'nyc_starred_events';
    const SCHEDULE_DETAILS_KEY = 'nyc_schedule_events';
    const SCHEDULE_NAME_KEY = 'nyc_schedule_name';
    let scheduleEvents = [];

    function eventKey(li) {{
      const day = li.closest('.day');
      const a = li.querySelector('.what a');
      return `${{day ? day.dataset.date : ''}}|${{li.dataset.epoch || ''}}|${{a ? a.textContent.trim() : ''}}`;
    }}

    function setStar(btn, on) {{
      btn.classList.toggle('starred', on);
      btn.textContent = on ? '★' : '☆';
      btn.setAttribute('aria-label', on ? 'Remove from My Schedule' : 'Add to My Schedule');
    }}

    function markStars(root) {{
      if (!starredEvents.size) return;
      root.querySelectorAll('.event').forEach(li => {{
        const btn = li.querySelector('.star-btn');
        if (btn && starredEvents.has(eventKey(li))) setStar(btn, true);
      }});
    }}

    function updateScheduleBar() {{
      if (!scheduleBar) return;
      const n = starredEvents.size;
      scheduleBar.style.display = n > 0 ? 'flex' : 'none';
      scheduleCount.textContent = n > 0 ? `(${{n}})` : '';
      scheduleView.setAttribute('aria-pressed', starredOnly ? 'true' : 'false');
      if (!n && starredOnly) {{ starredOnly = false; apply(); stateToHash(); }}
    }}

    function scheduleDetails() {{
      try {{
        const d = JSON.parse(localStorage.getItem(SCHEDULE_DETAILS_KEY) || '{{}}');
        return (d && typeof d === 'object') ? d : {{}};
      }} catch (_) {{ return {{}}; }}
    }}

    function scheduleRow(li) {{
      const m = extractEventMetaFromLi(li);
      if (!m.dt || isNaN(m.dt.getTime())) return null;
      const epoch = li.dataset.epoch ? parseInt(li.dataset.epoch, 10) : Math.floor(m.dt.getTime() / 1000);
      // The last field marks a listing with a date but no time, so it isn't shown at a made-up hour
      return [m.title, epoch, m.venue, m.url, li.dataset.epoch ? 0 : 1];
    }}

    function saveStars(details) {{
      try {{
        localStorage.setItem(STARRED_KEY, JSON.stringify(Array.from(starredEvents)));
        localStorage.setItem(SCHEDULE_DETAILS_KEY, JSON.stringify(details));
      }} catch (_) {{}}
    }}

    // My Schedule keeps an event for 24 hours after it starts
    function loadStarredState() {{
      try {{
        const raw = JSON.parse(localStorage.getItem(STARRED_KEY) || '[]');
        if (Array.isArray(raw)) starredEvents = new Set(raw);
      }} catch (_) {{}}
      const details = scheduleDetails();
      const cutoff = Math.floor(Date.now() / 1000) - 86400;
      const past = Object.keys(details).filter(k => Array.isArray(details[k]) && details[k][1] < cutoff);
      if (past.length) {{
        past.forEach(k => {{ delete details[k]; starredEvents.delete(k); }});
        saveStars(details);
      }}
      markStars(document);
    }}

    document.addEventListener('click', e => {{
      const btn = e.target.closest && e.target.closest('.star-btn');
      if (!btn) return;
      e.preventDefault();
      const li = btn.closest('.event');
      if (!li) return;
      const key = eventKey(li);
      const nowStarred = !starredEvents.has(key);
      const details = scheduleDetails();
      if (nowStarred) {{
        starredEvents.add(key);
        const row = scheduleRow(li);
        if (row) details[key] = row;
      }} else {{
        starredEvents.delete(key);
        delete details[key];
      }}
      saveStars(details);
      // A Near Me list holds copies of the cards, so update every copy of this one
      const day = li.closest('.day');
      (day || document).querySelectorAll('.event').forEach(other => {{
        if (eventKey(other) === key) {{
          const b = other.querySelector('.star-btn');
          if (b) setStar(b, nowStarred);
        }}
      }});
      updateScheduleBar();
      if (starredOnly) apply();
    }});

    async function encodeSchedule(obj) {{
      let bytes = new TextEncoder().encode(JSON.stringify(obj));
      let tag = 'j';
      if (window.CompressionStream) {{
        try {{
          const stream = new Blob([bytes]).stream().pipeThrough(new CompressionStream('deflate-raw'));
          bytes = new Uint8Array(await new Response(stream).arrayBuffer());
          tag = 'z';
        }} catch (_) {{}}
      }}
      let bin = '';
      bytes.forEach(b => {{ bin += String.fromCharCode(b); }});
      return tag + btoa(bin).split('+').join('-').split('/').join('_').split('=').join('');
    }}

    async function refreshScheduleLink() {{
      const name = scheduleName.value.trim();
      try {{ localStorage.setItem(SCHEDULE_NAME_KEY, name); }} catch (_) {{}}
      const hash = await encodeSchedule({{ v: 1, n: name, e: scheduleEvents }});
      // Relative to this page: the site lives under /nyc_events/ on GitHub Pages
      const link = `${{new URL('schedule/', location.href).href}}#${{hash}}`;
      scheduleLink.value = link;
      scheduleOpen.href = link;
    }}

    async function openScheduleShare() {{
      const saved = scheduleDetails();
      const cutoff = Math.floor(Date.now() / 1000) - 86400;
      scheduleEvents = Array.from(starredEvents).map(k => saved[k]).filter(r => Array.isArray(r) && r[1] >= cutoff)
        .sort((a, b) => a[1] - b[1]);
      const left = starredEvents.size - scheduleEvents.length;
      scheduleSub.textContent = `${{scheduleEvents.length}} upcoming ${{scheduleEvents.length === 1 ? 'event' : 'events'}}` +
        (left > 0 ? `. ${{left}} past or undated ${{left === 1 ? 'event is' : 'events are'}} left out.` : '.');
      try {{ scheduleName.value = localStorage.getItem(SCHEDULE_NAME_KEY) || ''; }} catch (_) {{}}
      await refreshScheduleLink();
      scheduleSend.style.display = navigator.share ? 'inline-block' : 'none';
      scheduleCopy.disabled = scheduleEvents.length === 0;
      scheduleModal.style.display = 'flex';
      scheduleCopy.focus();
    }}

    function closeScheduleShare() {{
      scheduleModal.style.display = 'none';
    }}

    if (scheduleBar) {{
      scheduleView.addEventListener('click', () => {{
        starredOnly = !starredOnly;
        apply();
        stateToHash();
        if (starredOnly) window.scrollTo({{ top: 0 }});
      }});
      document.getElementById('schedule-share').addEventListener('click', openScheduleShare);
      document.getElementById('schedule-share-close').addEventListener('click', closeScheduleShare);
      scheduleModal.addEventListener('click', e => {{ if (e.target === scheduleModal) closeScheduleShare(); }});
      document.addEventListener('keydown', e => {{
        if (e.key === 'Escape' && scheduleModal.style.display !== 'none') closeScheduleShare();
      }});
      scheduleName.addEventListener('input', refreshScheduleLink);
      scheduleCopy.addEventListener('click', async () => {{
        try {{
          await navigator.clipboard.writeText(scheduleLink.value);
        }} catch (_) {{
          scheduleLink.select();
          document.execCommand('copy');
        }}
        scheduleCopy.textContent = 'Copied';
        setTimeout(() => {{ scheduleCopy.textContent = 'Copy link'; }}, 1500);
      }});
      scheduleSend.addEventListener('click', () => {{
        navigator.share({{ title: 'My schedule', url: scheduleLink.value }}).catch(() => {{}});
      }});
    }}

    loadStarredState();
    hashToState();
    apply();
  </script>
</body>
</html>"""
    if split_deferred:
        return page_html, deferred_files
    return page_html
