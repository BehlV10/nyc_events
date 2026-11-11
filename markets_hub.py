"""Markets & Festivals hub (and Christmas & Holiday Markets subpage) for NYC Events.

Includes:
- Market & vendor festival classification (`is_market`, `is_vendor_festival`, `market_type`)
- "Open every day" strip (`_markets_split`) for daily markets like Bryant Park Winter Village,
  Union Square Holiday Market, Columbus Circle Holiday Market, and Grand Central Holiday Fair
- Start–end hours formatting (`_market_hours`)
- Borough-grouped daily sections, Near Me distance sorting within each day, and interactive Leaflet map
"""

import re
from datetime import datetime, timedelta
from html import escape
from urllib.parse import quote_plus

from scrapers import EASTERN, NOT_MARKET_FESTIVAL_RE

CARD_LIMIT = 600

# ---------------------------------------------------------------------------------------------
# Market & vendor festival classification
# ---------------------------------------------------------------------------------------------

_MARKET_RE = re.compile(
    r"(?i)\b(?:markets?|marketplace|bazaars?|flea|swap\s+meet|yard\s+sale|craft\s+shows?|makers?\s+mart|"
    r"winter\s+village|holiday\s+(?:pop[- ]?up|shop(?:ping)?\s+(?:night|stroll|event)|stroll|shoppes?|shops?)(?!\s*bar)|"
    r"sip\s*(?:&|and)\s*shop|julbutik|julemarked|christkindlmarkt|smorgasburg|greenmarket|"
    r"(?:artisan|craft|crafts|holiday|christmas|vintage|antiques?|record|maker'?s?|handmade|art|artists'?|street|"
    r"(?:art\s+|grown[- ]up\s+)?book)\s+fairs?|plant\s+(?:shows?|sales?|swaps?)|small\s+business\s+saturday|shop\s+small|"
    r"thrift\s+(?:festival|fest|sale|market|pop[- ]?up))\b"
)

# Permanent places named "market": an event held there isn't a market ("Chelsea Market Food Tour",
# "Show at Market Hotel"). Removed before matching, so "Holiday Market at Chelsea Market" still counts.
_MARKET_PLACE_RE = re.compile(
    r"(?i)\b(?:chelsea\s+market|time\s+out\s+market|dekalb\s+market(?:\s+hall)?|essex\s+(?:street\s+)?market|"
    r"la\s+marqueta|arthur\s+avenue\s+retail\s+market|tin\s+building|canal\s+street\s+market|"
    r"urban\s+hawker|turnstyle\s+underground\s+market|market\s+hotel|market\s+line|"
    r"boston\s+public\s+market|quincy\s+market|faneuil\s+hall\s+marketplace|"
    r"novo\s+marketplace|deluca'?’?s\s+market|bow\s+market|select\s+markets|haymarket\s+(?:station|square)|"
    r"market\s+(?:st|street|square|basket))\b"
)

_NOT_MARKET_RE = re.compile(
    r"(?i)\b(?:market\s+(?:st|street|square|basket|research|analysis|update|outlook|hotel)|stock\s+markets?|"
    r"job\s+markets?|housing\s+markets?|super\s*markets?|marketing|marketplace\s+of\s+ideas|"
    r"market\s+(?:days?\s+)?(?:volunteer|vendor\s+(?:application|sign))|"
    r"\btours?\b|tastings?|language\s+exchange|market\s+visit|a\s+visit\s+to|tree\s+(?:arrives|lighting)|"
    r"montreal|quebec|flea\s+(?:and\s+tick|treatment)|bazaar\s+magazine|haymarket\s+(?:station|square))\b"
)

# First match wins: "Winter Farmers Market" is a farmers market, "Holiday Craft Fair" a holiday one.
_MARKET_TYPES = (
    ("farmers", "🥕 Farmers & Produce", re.compile(
        r"(?i)\b(?:farmers'?|farm\s+stand|farm\s+market|farmstand|produce|fruit|apples?|orchard|berr(?:y|ies)|"
        r"harvest|greenmarket|youthmarket|down\s+to\s+earth|haymarket|csa)\b")),
    ("holiday", "🎄 Holiday & Winter", re.compile(
        r"(?i)\b(?:holiday|christmas|xmas|winter|snow|yule|julbutik|julemarked|julmarknad|julebazar|christkindlmarkt|"
        r"norwegian\s+seamen|church\s+of\s+sweden|danish\s+seamen|"
        r"hanukkah|chanukah|kwanzaa|diwali|lunar\s+new\s+year|"
        r"santa|jingle|festive|gift|merry|noel|advent|solstice|mistletoe|thanksgiving|stocking|wonderland|holiday-topia)\b")),
    ("flea", "🧺 Flea, Vintage & Thrift", re.compile(
        r"(?i)\b(?:flea|vintage|antiques?|thrift|swap|yard\s+sale|record|vinyl|secondhand|second-hand|"
        r"used\s+books?|collectibles?|estate|free\s+market|oddities|grand\s+bazaar)\b")),
    ("craft", "🎨 Craft, Art & Makers", re.compile(
        r"(?i)\b(?:craft|crafts|artisan|makers?|maker's|handmade|art|artists'?|design|zine|jewelry|ceramics|"
        r"pottery|indie|small\s+business|local\s+business|shop\s+small|book\s+fair|plants?|pop[- ]?up|fad\s+market|renegade)\b")),
    ("night", "🌙 Night & Food Markets", re.compile(
        r"(?i)\b(?:night|food|eats|dumplings?|asian|street\s+food|cultural|bazaar|souk|smorgasburg|dragon\s+fest|japan\s+fes)\b")),
)
_FESTIVAL_TYPE = ("festival", "🎪 Festivals & Fairs")
_MARKET_OTHER = ("other", "🛍️ Other markets")


def is_market(e):
    name = e.get("name") or e.get("title") or ""
    bare = _MARKET_PLACE_RE.sub(" ", name)
    if not bool(_MARKET_RE.search(bare)):
        return False
    if _NOT_MARKET_RE.search(name) and not re.search(r"(?i)\bholiday\s+stroll\b", name):
        return False
    return not NOT_MARKET_FESTIVAL_RE.search(name)


# A festival or fair, by title (MARKET_FESTIVAL_RE without the market words is_market covers).
_FESTIVAL_RE = re.compile(
    r"(?i)\b(?:festival|fest|fair|faire|street\s+party|block\s+party|snowport|winter\s+village|oktoberfest)\b"
)
# Festivals that are a show, a tasting or a ceremony rather than stalls to wander
_NOT_VENDOR_FESTIVAL_RE = re.compile(
    r"(?i)(?:\b(?:music|jazz|blues|folk|fiddle|bluegrass|rock|punk|metal|hip[- ]?hop|edm|dj|techno|trance|house\s+music|"
    r"orchestra|symphony|choir|chamber|piano|guitar|song|songwriters?|opera|concerts?|film|films|movie|cinema|"
    r"shorts|documentary|comedy|improv|dance|ballet|theat(?:er|re)|play|plays|fringe|poetry|storytelling|"
    r"beer|beers|lagers?|ales?|brew(?:s|fest)?|wine|cider|spirits|whiske?y|cocktails?|tequila|bourbon|"
    r"tree\s+lighting|tree\s+arrives|pass|passes|ticket\s+package|lineup|presents|tour|science|stem|"
    r"fair\s+(?:trade|housing|share|game)|state\s+fair|social|meet(?:up)?|let'?s\s+meet|speed\s+dating|"
    r"5k|10k|run|race|walk|marathon|tournament|hackathon|conference|summit|book|books|authors?|lecture|"
    r"potluck|ages\s+\d+)\b|\b21\+)"
)
_VENDOR_FESTIVAL_CATEGORIES = {"markets", "community", "other", "food", "art", "arts", ""}


def is_vendor_festival(e):
    name = e.get("name") or e.get("title") or ""
    if not _FESTIVAL_RE.search(name) or _NOT_VENDOR_FESTIVAL_RE.search(name):
        return False
    if NOT_MARKET_FESTIVAL_RE.search(name):  # job, college, resource fairs
        return False
    return (e.get("category") or "").lower() in _VENDOR_FESTIVAL_CATEGORIES


def market_type(e):
    name = e.get("name") or e.get("title") or ""
    if not is_market(e) and is_vendor_festival(e):
        return "holiday" if _MARKET_TYPES[1][2].search(name) else _FESTIVAL_TYPE[0]
    for key, _label, rx in _MARKET_TYPES:
        if rx.search(name):
            return key
    return _MARKET_OTHER[0]


# ---------------------------------------------------------------------------------------------
# Daily strip vs. dated sections and hours formatting
# ---------------------------------------------------------------------------------------------

MARKET_DAILY_MIN_DATES = 5      # a series on at least this many days...
MARKET_DAILY_MIN_SHARE = 0.7    # ...covering this share of the days between its first and last


def _series_key(e):
    title = e.get("name") or e.get("title") or ""
    name = re.sub(r"\b20\d\d\b|[^a-z0-9 ]+", " ", title.lower())
    venue = re.sub(r"^the |[^a-z0-9 ]+", " ", (e.get("venue") or e.get("_source_venue") or "").lower())
    return " ".join(name.split()), (venue.split() or [""])[0]


def _markets_split(events):
    """(daily, dated): series open (nearly) every day become one entry each in `daily`, with
    `_daily_dates` (its open days, in order) and `_daily_hours` (date -> event); everything
    else stays one card per day it's on, in `dated`. Events must be date-sorted."""
    groups, order = {}, []
    for e in events:
        k = _series_key(e)
        if k not in groups:
            groups[k] = []
            order.append(k)
        groups[k].append(e)
    daily, dated_keys = [], set()
    for k in order:
        by_day = {}
        for e in groups[k]:
            t = e.get("_time")
            if isinstance(t, datetime):
                by_day.setdefault(t.date(), e)
        days = sorted(by_day)
        if len(days) >= MARKET_DAILY_MIN_DATES and \
                len(days) / ((days[-1] - days[0]).days + 1) >= MARKET_DAILY_MIN_SHARE:
            daily.append({**by_day[days[0]], "_daily_dates": days, "_daily_hours": by_day})
        else:
            dated_keys.add(k)
    dated, seen = [], set()
    for e in events:
        k = _series_key(e)
        if k not in dated_keys:
            continue
        t = e.get("_time")
        day = t.date() if isinstance(t, datetime) else None
        if (k, day) in seen:
            continue  # two sources' copies of one market day
        seen.add((k, day))
        dated.append(e)
    return daily, dated


def _short_clock(dt):
    """10 am, 3:30 pm."""
    return dt.strftime("%-I %p" if dt.minute == 0 else "%-I:%M %p").lower()


def _market_hours(e):
    """"10 am – 4 pm" when the end is known, "10 am" otherwise, "Time TBA"/"All day" as on other hubs."""
    t = e.get("_time")
    if not isinstance(t, datetime):
        return ""
    if e.get("_time_unknown") or re.fullmatch(r"\d{4}-\d{2}-\d{2}", e.get("date") or ""):
        return "Time TBA"
    start = t.astimezone(EASTERN)
    end = None
    try:
        if e.get("end"):
            end = datetime.fromisoformat(str(e["end"]).replace("Z", "+00:00"))
            end = (end if end.tzinfo else end.replace(tzinfo=EASTERN)).astimezone(EASTERN)
    except ValueError:
        end = None
    if (start.hour, start.minute) == (0, 0) and not end:
        return "All day"
    if end and timedelta(0) < end - start <= timedelta(hours=16):
        a, b = _short_clock(start), _short_clock(end)
        if a[-2:] == b[-2:]:
            a = a[:-3]  # "10 – 11 am" style when both share am/pm
        return f"{a} – {b}"
    return _short_clock(start)


def _market_kind_label(kind):
    for k, lbl, _rx in _MARKET_TYPES:
        if k == kind:
            return lbl
    return dict([_FESTIVAL_TYPE, _MARKET_OTHER]).get(kind, "")


_GENERIC_VENUE_RE = re.compile(
    r"(?i)^(?:the\s+skint(?:\s+nyc)?|nyc\s*/\s*the\s+skint|secret\s+nyc|nyc\s*/\s*secret\s+nyc|"
    r"partiful(?:\s+nyc)?|allevents(?:\s+nyc)?|luma(?:\s+nyc)?|eventbrite(?:\s+nyc)?|"
    r"new\s+york(?:,\s*ny)?|nyc|manhattan|brooklyn|queens|the\s+bronx|bronx|staten\s+island|"
    r"greenmarket(?:\s*\(new\s+york,\s*ny\))?|venue|tba|multiple\s+locations|various\s+locations)$"
)

# Specific spot mapping: (regex matching title/desc/venue, spot_name, gmaps_query, city, lat, lng, neighborhood)
_KNOWN_MARKET_SPOTS = (
    (re.compile(r"(?i)\b(?:bryant\s+park|winter\s+village\s+at\s+bryant\s+park)"),
     "Bryant Park", "Bryant Park, New York, NY 10018", "manhattan", 40.7536, -73.9832, "Midtown"),
    (re.compile(r"(?i)\bunion\s+square\s+holiday\s+market\b"),
     "Union Square Park (South Plaza)", "Union Square Park, New York, NY 10003", "manhattan", 40.7359, -73.9911, "Union Square"),
    (re.compile(r"(?i)\bunion\s+square\s+greenmarket\b"),
     "Union Square Park (North & West Plazas)", "Union Square W & E 17th St, New York, NY 10003", "manhattan", 40.7359, -73.9911, "Union Square"),
    (re.compile(r"(?i)\bcolumbus\s+circle\s+holiday\s+market\b"),
     "Columbus Circle (Central Park SW & 59th St)", "Columbus Circle, New York, NY 10019", "manhattan", 40.7681, -73.9819, "Midtown West"),
    (re.compile(r"(?i)\bgrand\s+central\s+holiday\s+fair\b"),
     "Vanderbilt Hall at Grand Central Terminal", "89 E 42nd St, New York, NY 10017", "manhattan", 40.7527, -73.9772, "Midtown East"),
    (re.compile(r"(?i)\bgrand\s+central\s+holiday\s+train\s+show\b"),
     "NY Transit Museum Gallery at Grand Central Terminal", "89 E 42nd St, New York, NY 10017", "manhattan", 40.7527, -73.9772, "Midtown East"),
    (re.compile(r"(?i)\bmacy'?s\s+holiday\s+square\b"),
     "Macy's Herald Square (151 W 34th St)", "151 W 34th St, New York, NY 10001", "manhattan", 40.7505, -73.9878, "Herald Square"),
    (re.compile(r"(?i)\b(?:34th\s+street|herald\s+square)\s+holiday\s+market\b"),
     "Herald Square Plaza (Broadway & W 34th St)", "Herald Square, New York, NY 10001", "manhattan", 40.7505, -73.9878, "Herald Square"),
    (re.compile(r"(?i)\boculus\s+holiday\s+market|shops\s+at\s+the\s+oculus\b"),
     "Westfield World Trade Center Oculus", "185 Greenwich St, New York, NY 10007", "manhattan", 40.7115, -74.0115, "Financial District"),
    (re.compile(r"(?i)\bchinatown\s+holiday\s+market\b"),
     "Kam Man Market (200 Canal St, 2nd Fl)", "200 Canal St, New York, NY 10013", "manhattan", 40.7169, -73.9973, "Chinatown"),
    (re.compile(r"(?i)\brenegade\s+craft\b"),
     "Metropolitan Pavilion (125 W 18th St)", "125 W 18th St, New York, NY 10011", "manhattan", 40.7408, -73.9949, "Chelsea"),
    (re.compile(r"(?i)\b175th\s+street\s+greenmarket\b"),
     "175th St & Broadway Plaza", "W 175th St & Broadway, New York, NY 10033", "manhattan", 40.8460, -73.9383, "Washington Heights"),
    (re.compile(r"(?i)\b79th\s+street\s+greenmarket\b"),
     "Columbus Ave & W 79th St", "Columbus Ave & W 79th St, New York, NY 10024", "manhattan", 40.7818, -73.9756, "Upper West Side"),
    (re.compile(r"(?i)\btompkins\s+square\s+greenmarket\b"),
     "Tompkins Square Park (Ave A & E 7th St)", "Tompkins Square Park, New York, NY 10009", "manhattan", 40.7265, -73.9815, "East Village"),
    (re.compile(r"(?i)\bgrand\s+army\s+plaza\s+greenmarket\b"),
     "Prospect Park West & Grand Army Plaza", "Grand Army Plaza, Brooklyn, NY 11238", "brooklyn", 40.6725, -73.9698, "Park Slope"),
    (re.compile(r"(?i)\bfort\s+greene\s+park\s+greenmarket\b"),
     "Fort Greene Park (Washington Park & DeKalb Ave)", "Fort Greene Park, Brooklyn, NY 11205", "brooklyn", 40.6894, -73.9739, "Fort Greene"),
    (re.compile(r"(?i)\bmccarren\s+park\s+greenmarket\b"),
     "McCarren Park (Union Ave & Driggs Ave)", "McCarren Park, Brooklyn, NY 11211", "brooklyn", 40.7196, -73.9517, "Williamsburg"),
    (re.compile(r"(?i)\bjackson\s+heights\s+greenmarket\b"),
     "Travers Park (34th Ave & 79th St)", "78-02 34th Ave, Jackson Heights, NY 11372", "queens", 40.7538, -73.8881, "Jackson Heights"),
    (re.compile(r"(?i)\bforest\s+hills\s+greenmarket\b"),
     "Queens Blvd & 70th Ave", "107-29 70th Rd, Forest Hills, NY 11375", "queens", 40.7209, -73.8448, "Forest Hills"),
    (re.compile(r"(?i)\bchurch\s+of\s+sweden|swedish\s+christmas|julmarknad|julbutik\b"),
     "Church of Sweden (5 E 48th St)", "5 E 48th St, New York, NY 10017", "manhattan", 40.7573, -73.9776, "Midtown"),
    (re.compile(r"(?i)\bnorwegian\s+seamen|julemarked\b"),
     "Norwegian Seamen's Church (317 E 52nd St)", "317 E 52nd St, New York, NY 10022", "manhattan", 40.7556, -73.9660, "Midtown East"),
    (re.compile(r"(?i)\bdanish\s+seamen|denmark.*christmas|julebazar\b"),
     "Danish Seamen's Church (102 Willow St)", "102 Willow St, Brooklyn, NY 11201", "brooklyn", 40.6989, -73.9961, "Brooklyn Heights"),
    (re.compile(r"(?i)\bcrafts\s+at\s+(?:the\s+cathedral|st\.?\s*john\s+the\s+divine)\b"),
     "Cathedral of St. John the Divine (1047 Amsterdam Ave)", "1047 Amsterdam Ave, New York, NY 10025", "manhattan", 40.8038, -73.9619, "Morningside Heights"),
    (re.compile(r"(?i)\bwallabout\s+wonderland\b"),
     "Brooklyn Navy Yard (Building 77, 141 Flushing Ave)", "141 Flushing Ave, Brooklyn, NY 11205", "brooklyn", 40.6991, -73.9720, "Brooklyn Navy Yard"),
    (re.compile(r"(?i)\bbrooklyn\s+borough\s+hall\s+holiday\b"),
     "Brooklyn Borough Hall Plaza (209 Joralemon St)", "209 Joralemon St, Brooklyn, NY 11201", "brooklyn", 40.6928, -73.9903, "Downtown Brooklyn"),
    (re.compile(r"(?i)\bfad\s+market.*cobble\s+hill|st\.?\s*paul'?s\s+church\b"),
     "St. Paul's Church (199 Carroll St)", "199 Carroll St, Brooklyn, NY 11231", "brooklyn", 40.6808, -73.9958, "Cobble Hill"),
    (re.compile(r"(?i)\bfad\s+market.*invisible\s+dog|invisible\s+dog\b"),
     "The Invisible Dog Art Center (51 Bergen St)", "51 Bergen St, Brooklyn, NY 11201", "brooklyn", 40.6865, -73.9911, "Boerum Hill"),
    (re.compile(r"(?i)\bfad\s+market|empire\s+stores\b"),
     "Empire Stores (55 Water St)", "55 Water St, Brooklyn, NY 11201", "brooklyn", 40.7035, -73.9912, "DUMBO"),
    (re.compile(r"(?i)\b(?:brooklyn|dumbo)\s+flea\b"),
     "DUMBO Archway (80 Pearl St)", "80 Pearl St, Brooklyn, NY 11201", "brooklyn", 40.7026, -73.9882, "DUMBO"),
    (re.compile(r"(?i)\bchelsea\s+flea\b"),
     "Chelsea Flea (29 W 25th St)", "29 W 25th St, New York, NY 10010", "manhattan", 40.7438, -73.9907, "Chelsea"),
    (re.compile(r"(?i)\bgrand\s+bazaar\s+nyc\b"),
     "Grand Bazaar NYC (100 W 77th St)", "100 W 77th St, New York, NY 10024", "manhattan", 40.7808, -73.9765, "Upper West Side"),
    (re.compile(r"(?i)\bastoria\s+(?:holiday\s+)?market\b"),
     "Bohemian Hall & Beer Garden (29-19 24th Ave)", "29-19 24th Ave, Astoria, NY 11102", "queens", 40.7728, -73.9158, "Astoria"),
    (re.compile(r"(?i)\bqueens\s+craft\s+brigade\b"),
     "Katch Astoria (31-14 Newtown Ave)", "31-14 Newtown Ave, Astoria, NY 11102", "queens", 40.7669, -73.9212, "Astoria"),
    (re.compile(r"(?i)\bqueens\s+night\s+market\b"),
     "New York Hall of Science (Flushing Meadows Corona Park)", "47-01 111th St, Corona, NY 11368", "queens", 40.7471, -73.8515, "Corona"),
    (re.compile(r"(?i)\bqueens\s+county\s+farm\b"),
     "Queens County Farm Museum (73-50 Little Neck Pkwy)", "73-50 Little Neck Pkwy, Floral Park, NY 11004", "queens", 40.7478, -73.7235, "Floral Park"),
    (re.compile(r"(?i)\bflushing\s+town\s+hall\b"),
     "Flushing Town Hall (137-35 Northern Blvd)", "137-35 Northern Blvd, Flushing, NY 11354", "queens", 40.7634, -73.8295, "Flushing"),
    (re.compile(r"(?i)\bculture\s+lab\s+lic\b"),
     "Culture Lab LIC (5-25 46th Ave)", "5-25 46th Ave, Long Island City, NY 11101", "queens", 40.7469, -73.9547, "Long Island City"),
    (re.compile(r"(?i)\bbronx\s+night\s+market|holiday[- ]?topia\b"),
     "1 Fordham Plaza", "1 Fordham Plaza, Bronx, NY 10458", "bronx", 40.8615, -73.8906, "Fordham"),
    (re.compile(r"(?i)\bbartow[- ]?pell\b"),
     "Bartow-Pell Mansion Museum (895 Shore Rd)", "895 Shore Rd, Bronx, NY 10464", "bronx", 40.8717, -73.8056, "Pelham Bay Park"),
    (re.compile(r"(?i)\bpoe\s+park\b"),
     "Poe Park Visitor Center (2640 Grand Concourse)", "2640 Grand Concourse, Bronx, NY 10458", "bronx", 40.8647, -73.8950, "Fordham"),
    (re.compile(r"(?i)\bwave\s+hill\b"),
     "Wave Hill (4900 Independence Ave)", "4900 Independence Ave, Bronx, NY 10471", "bronx", 40.8979, -73.9114, "Riverdale"),
    (re.compile(r"(?i)\bnew\s+york\s+botanical\s+garden|nybg\b"),
     "New York Botanical Garden (2900 Southern Blvd)", "2900 Southern Blvd, Bronx, NY 10458", "bronx", 40.8624, -73.8772, "Bedford Park"),
    (re.compile(r"(?i)\bsnug\s+harbor\b"),
     "Snug Harbor Cultural Center (1000 Richmond Ter)", "1000 Richmond Ter, Staten Island, NY 10301", "staten_island", 40.6433, -74.1025, "Randall Manor"),
    (re.compile(r"(?i)\bempire\s+outlets\b"),
     "Empire Outlets (55 Richmond Ter)", "55 Richmond Ter, Staten Island, NY 10301", "staten_island", 40.6438, -74.0764, "St. George"),
    (re.compile(r"(?i)\bhistoric\s+richmond\s+town\b"),
     "Historic Richmond Town (441 Clarke Ave)", "441 Clarke Ave, Staten Island, NY 10306", "staten_island", 40.5707, -74.1456, "Richmond Town"),
    (re.compile(r"(?i)\bmoravian\s+(?:church|christmas)\b"),
     "Vanderbilt Moravian Church (2205 Richmond Rd)", "2205 Richmond Rd, Staten Island, NY 10306", "staten_island", 40.5812, -74.1132, "Grant City"),
    (re.compile(r"(?i)\bharlem\s+night\s+market|la\s+marqueta\b"),
     "La Marqueta (1590 Park Ave)", "1590 Park Ave, New York, NY 10029", "manhattan", 40.7982, -73.9442, "East Harlem"),
    (re.compile(r"(?i)\bmuseum\s+of\s+the\s+city\s+of\s+new\s+york|mcny\b"),
     "Museum of the City of New York (1220 Fifth Ave)", "1220 Fifth Ave, New York, NY 10029", "manhattan", 40.7925, -73.9519, "East Harlem"),
    (re.compile(r"(?i)\bcity\s+point\b"),
     "City Point BKLYN (445 Albee Square W)", "445 Albee Square W, Brooklyn, NY 11201", "brooklyn", 40.6911, -73.9829, "Downtown Brooklyn"),
    (re.compile(r"(?i)\barts\s+gowanus\b"),
     "Gowanus Dredgers Boathouse (165 2nd St)", "165 2nd St, Brooklyn, NY 11231", "brooklyn", 40.6766, -73.9912, "Gowanus"),
    (re.compile(r"(?i)\bred\s+hook\s+holiday\b"),
     " Brooklyn Waterfront Artists Coalition (481 Van Brunt St)", "481 Van Brunt St, Brooklyn, NY 11231", "brooklyn", 40.6744, -74.0177, "Red Hook"),
    (re.compile(r"(?i)\bmade\s+at\s+bush\s+terminal|bush\s+terminal\b"),
     "MADE Bush Terminal (10 43rd St)", "10 43rd St, Brooklyn, NY 11232", "brooklyn", 40.6548, -74.0149, "Sunset Park"),
    (re.compile(r"(?i)\bjapan\s+village|industry\s+city\b"),
     "Industry City / Japan Village (934 3rd Ave)", "934 3rd Ave, Brooklyn, NY 11232", "brooklyn", 40.6562, -74.0076, "Sunset Park"),
    (re.compile(r"(?i)\bwilliamsburg\s+winter\s+village|westlight|the\s+william\s+vale\b"),
     "The William Vale (111 N 12th St)", "111 N 12th St, Brooklyn, NY 11249", "brooklyn", 40.7222, -73.9569, "Williamsburg"),
    (re.compile(r"(?i)\bartists\s*(?:&|and)\s*fleas.*williamsburg\b"),
     "Artists & Fleas Williamsburg (70 N 7th St)", "70 N 7th St, Brooklyn, NY 11249", "brooklyn", 40.7196, -73.9602, "Williamsburg"),
    (re.compile(r"(?i)\bartists\s*(?:&|and)\s*fleas\b"),
     "Artists & Fleas Chelsea Market (88 10th Ave)", "88 10th Ave, New York, NY 10011", "manhattan", 40.7424, -74.0061, "Chelsea"),
    (re.compile(r"(?i)\beast\s+village\s+vintage|japanese\s+holiday\s+art\b"),
     "St. Marks Place & Astor Place Plaza", "Astor Place, New York, NY 10003", "manhattan", 40.7300, -73.9910, "East Village"),
    (re.compile(r"(?i)\broebling\s+rink|brooklyn\s+bridge\s+park\b"),
     "Emily Warren Roebling Plaza at Brooklyn Bridge Park", "27A Furman St, Brooklyn, NY 11201", "brooklyn", 40.7031, -73.9936, "DUMBO"),
    (re.compile(r"(?i)\bwollman\s+rink\b"),
     "Wollman Rink in Central Park", "830 5th Ave, New York, NY 10065", "manhattan", 40.7677, -73.9744, "Central Park"),
    (re.compile(r"(?i)\bluminiscence|st\.?\s*patrick'?s\s+cathedral\b"),
     "St. Patrick's Cathedral (5th Ave & 50th St)", "5th Ave & E 50th St, New York, NY 10022", "manhattan", 40.7585, -73.9760, "Midtown"),
    (re.compile(r"(?i)\bchristmas\s+cocktail\s+carol|the\s+arches\b"),
     "The Arches (2266 Atlantic Ave)", "2266 Atlantic Ave, Brooklyn, NY 11233", "brooklyn", 40.6758, -73.9086, "Crown Heights"),
)

_AT_SPOT_RE = re.compile(
    r"(?i)\b(?:at|@)\s+([A-Z0-9][\w'’&\-. ]{2,48}?)(?=\s*(?:\(|—|–|-|,|\.|;|\bfrom\b|\bon\b|\bin\b|\bwith\b|$))"
)


def _enrich_market_event(e):
    """Resolve generic/aggregator venue names ('NYC / The Skint', 'New York', etc.) to their
    specific physical spot and attach a Google Maps search URL."""
    raw_venue = (e.get("venue") or e.get("_source_venue") or "").strip()
    title = (e.get("title") or e.get("name") or "").strip()
    desc = (e.get("description") or "").strip()
    combined = f"{title} {raw_venue} {desc}"

    is_generic = not raw_venue or bool(_GENERIC_VENUE_RE.match(raw_venue))
    for rx, spot_name, gmaps_q, city, lat, lng, neigh in _KNOWN_MARKET_SPOTS:
        if rx.search(combined):
            ev = dict(e)
            if is_generic or raw_venue.lower() in ("greenmarket (new york, ny)", "fad market", "brooklyn flea"):
                ev["venue"] = spot_name
            ev.setdefault("lat", lat)
            ev.setdefault("lng", lng)
            ev.setdefault("neighborhood", neigh)
            ev["_resolved_city"] = city
            ev["_gmaps_query"] = gmaps_q
            return ev

    if is_generic:
        ev = dict(e)
        m = _AT_SPOT_RE.search(title) or _AT_SPOT_RE.search(desc)
        if m:
            cand = m.group(1).strip(" -–—,.")
            if cand and not _GENERIC_VENUE_RE.match(cand):
                ev["venue"] = cand
                ev["_gmaps_query"] = f"{cand}, New York, NY"
                return ev
        # Fall back to specific market title + NYC so Google Maps still pinpoints the market
        clean_title = re.sub(r"\s*\([^)]*\)\s*", " ", title).strip() or "New York Market"
        ev["venue"] = clean_title
        ev["_gmaps_query"] = f"{clean_title}, New York, NY"
        return ev

    return e


def _place_label(city, e, city_labels, geo=None):
    city_label = city_labels.get(city, city.replace("_", " ").title())
    neigh = (geo or {}).get("neighborhood") or e.get("neighborhood") or ""
    if neigh and neigh.lower() != city_label.lower():
        return f"{neigh}, {city_label}"
    try:
        from template import resolve_subarea
        sub, _ = resolve_subarea(city, e, geo=geo)
        if sub and not sub.startswith("Other ") and sub != city_label:
            return f"{sub}, {city_label}"
    except Exception:
        pass
    return city_label


def _render_market_card(e, day_attr, city_of=None, is_free=None, city_labels=None, today=None):
    from venues_geo import resolve_event_geo

    e = _enrich_market_event(e)
    if city_of is None or is_free is None or city_labels is None:
        from template import CITY_LABELS, _event_city, _is_event_free
        city_labels = city_labels or CITY_LABELS
        is_free = is_free or _is_event_free
        if city_of is None:
            city_of = lambda ev: ev.get("_resolved_city") or _event_city(ev.get("venue"), ev.get("_source_venue"), geo=resolve_event_geo(ev), event=ev)

    raw_title = e.get("title") or e.get("name") or "Event"
    raw_venue = (e.get("venue") or e.get("_source_venue") or "Venue").strip()
    title = escape(raw_title)
    venue = escape(raw_venue)
    url = escape(e.get("url") or e.get("link") or "#")
    geo = resolve_event_geo(e)
    city = e.get("_resolved_city") or city_of(e)
    raw_place = _place_label(city, e, city_labels, geo=geo)
    place = escape(raw_place)
    gmaps_query = e.get("_gmaps_query") or f"{raw_venue}, {raw_place}, NY"
    gmaps_url = escape(f"https://www.google.com/maps/search/?api=1&query={quote_plus(gmaps_query)}")
    kind = market_type(e)
    price_txt = str(e.get("price") or "").strip()
    if re.fullmatch(r"\d+(?:\.\d+)?", price_txt):
        price_txt = "$" + price_txt
    if is_free(e):
        price_badge = '<span class="badge badge-free">Free</span>'
    else:
        price_badge = f'<span class="badge badge-price">{escape(price_txt)}</span>' if price_txt else ""
    kind_label = _market_kind_label(kind)
    kind_badge = f'<span class="mk-kind mk-k-{kind}">{escape(kind_label)}</span>' if kind_label else ""

    lat = str(geo["lat"]) if geo and "lat" in geo else (str(e.get("lat")) if e.get("lat") else "")
    lng = str(geo["lng"]) if geo and "lng" in geo else (str(e.get("lng")) if e.get("lng") else "")

    dates = e.get("_daily_dates")
    if dates:
        hours = e["_daily_hours"]
        through = dates[-1].strftime("%b %-d")
        closed = [d for d in (dates[0] + timedelta(days=i) for i in range((dates[-1] - dates[0]).days + 1)) if d not in hours]
        span = f"Daily through {through}" if not closed else f"Most days through {through}"
        today = today or datetime.now(EASTERN).date()
        if today in hours:
            when = f"Today {_market_hours(hours[today])}"
        else:
            nxt = next((d for d in dates if d >= today), dates[0])
            when = f"Opens {nxt.strftime('%a, %b %-d')} · {_market_hours(hours[nxt])}"
        if closed:
            when += f" · closed {', '.join(d.strftime('%b %-d') for d in closed[:3])}"
        time_html = f'<span class="mk-hours">{escape(when)}</span><span class="mk-span">{escape(span)}</span>'
        raw_when = f"{span} · {when}"
    else:
        hrs = _market_hours(e)
        time_html = f'<span class="mk-hours">{escape(hrs)}</span>'
        raw_when = hrs
    desc_html = ""
    if e.get("description"):
        d_txt = re.sub(r"\s+", " ", str(e["description"])).strip()
        desc_html = f'<p class="hub-desc">{escape(d_txt[:160] + ("…" if len(d_txt) > 160 else ""))}</p>'
    return f"""<article class="hub-card mk-card mk-k-{kind}" data-city="{escape(city)}" data-day="{day_attr}" data-mtype="{kind}" data-lat="{lat}" data-lng="{lng}" data-title="{title}" data-venue="{venue}" data-gmaps="{gmaps_url}" data-url="{url}" data-when="{escape(raw_when)}">
  <div class="mk-time-col">
    <div class="mk-when">{time_html}</div>
  </div>
  <div class="mk-content-col">
    <div class="mk-card-top">
      <h3 class="hub-title"><a href="{url}" target="_blank" rel="noopener">{title}</a></h3>
      <div class="mk-badges">
        {kind_badge}
        <div class="hub-badges">{price_badge}</div>
        <span class="mk-dist-badge" hidden></span>
      </div>
    </div>
    <div class="hub-meta"><a class="hub-venue hub-venue-link" href="{gmaps_url}" target="_blank" rel="noopener" title="Open {venue} in Google Maps">📍 {venue}</a> <span class="hub-city">({place})</span></div>
    {desc_html}
  </div>
</article>"""


_MARKET_CITY_ORDER = ("manhattan", "brooklyn", "queens", "bronx", "staten_island", "citywide", "other")
_MARKET_CITY_LABELS = {
    "manhattan": "Manhattan",
    "brooklyn": "Brooklyn",
    "queens": "Queens",
    "bronx": "The Bronx",
    "staten_island": "Staten Island",
    "citywide": "Citywide",
    "other": "Nearby",
}
_HUB_CITY_CHIPS = (
    ("all", "All Boroughs"),
    ("manhattan", "Manhattan"),
    ("brooklyn", "Brooklyn"),
    ("queens", "Queens"),
    ("bronx", "The Bronx"),
    ("staten_island", "Staten Island"),
    ("citywide", "Citywide"),
)


def _render_market_sections(daily, dated, card_limit, city_of=None, is_free=None, city_labels=None, today=None):
    """HTML for the "Open every day" strip, then each day, split by borough."""
    from venues_geo import resolve_event_geo

    if city_of is None or is_free is None or city_labels is None:
        from template import CITY_LABELS, _event_city, _is_event_free
        city_labels = city_labels or CITY_LABELS
        is_free = is_free or _is_event_free
        if city_of is None:
            city_of = lambda ev: ev.get("_resolved_city") or _event_city(ev.get("venue"), ev.get("_source_venue"), geo=resolve_event_geo(ev), event=ev)

    def _ev_city(ev):
        enriched = _enrich_market_event(ev)
        return enriched.get("_resolved_city") or city_of(enriched)

    out = []
    if daily:
        out.append('<section class="mk-daily" data-day="daily">')
        out.append(f'<h2 class="hub-day mk-daily-head" id="daily" data-day="daily">✨ Open every day <span class="mk-count">{len(daily)}</span></h2>')
        by_daily_city = {}
        for e in daily:
            by_daily_city.setdefault(_ev_city(e), []).append(e)
        for city in _MARKET_CITY_ORDER:
            cevs = by_daily_city.get(city)
            if not cevs:
                continue
            pill_label = _MARKET_CITY_LABELS.get(city, city.title())
            out.append(
                f'<div class="mk-city" data-city="{city}" data-day="daily">'
                f'<h3 class="mk-city-head"><span class="mk-city-pill mk-c-{city}">{escape(pill_label)}</span></h3>'
                '<div class="mk-grid">' + "".join(
                    _render_market_card(e, "daily", city_of, is_free, city_labels, today) for e in cevs
                ) + "</div></div>"
            )
        out.append('<div class="mk-day-dist-grid mk-grid" hidden></div>')
        out.append("</section>")
    by_day = {}
    for e in dated[:card_limit]:
        t = e.get("_time")
        by_day.setdefault(t.date() if isinstance(t, datetime) else None, []).append(e)
    for day in sorted((d for d in by_day if d), key=lambda d: d) + ([None] if None in by_day else []):
        day_iso = day.isoformat() if day else "tba"
        label = day.strftime("%A, %B %-d") if day else "Date TBA"
        evs = by_day[day]
        out.append(f'<section class="mk-day-section" data-day="{day_iso}">')
        out.append(f'<h2 class="hub-day" id="{day_iso}" data-day="{day_iso}">{label} <span class="mk-count">{len(evs)}</span></h2>')
        by_city = {}
        for e in evs:
            by_city.setdefault(_ev_city(e), []).append(e)
        for city in _MARKET_CITY_ORDER:
            cevs = by_city.get(city)
            if not cevs:
                continue
            cevs.sort(key=lambda ev: ev.get("_time") or datetime.max.replace(tzinfo=EASTERN))
            pill_label = _MARKET_CITY_LABELS.get(city, city.title())
            out.append(
                f'<div class="mk-city" data-city="{city}" data-day="{day_iso}">'
                f'<h3 class="mk-city-head"><span class="mk-city-pill mk-c-{city}">{escape(pill_label)}</span></h3>'
                '<div class="mk-grid">' + "".join(
                    _render_market_card(e, day_iso, city_of, is_free, city_labels, today) for e in cevs
                ) + "</div></div>"
            )
        out.append('<div class="mk-day-dist-grid mk-grid" hidden></div>')
        out.append("</section>")
    return out


_MARKETS_HERO_ART = """<svg class="mk-hero-art" viewBox="0 0 900 200" aria-hidden="true" preserveAspectRatio="xMidYMid slice" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="mk-sky" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#2a3560"/><stop offset="55%" stop-color="#a8566e"/><stop offset="100%" stop-color="#f2a65a"/>
    </linearGradient>
    <radialGradient id="mk-glow"><stop offset="0%" stop-color="#ffe7a3" stop-opacity="0.9"/><stop offset="100%" stop-color="#ffe7a3" stop-opacity="0"/></radialGradient>
  </defs>
  <rect width="900" height="200" fill="url(#mk-sky)"/>
  <g fill="#3a2f52" opacity="0.55"><rect x="0" y="111" width="32" height="49"/><rect x="35" y="117" width="42" height="43"/><rect x="77" y="86" width="48" height="74"/><rect x="125" y="83" width="33" height="77"/><rect x="158" y="107" width="38" height="53"/><rect x="196" y="93" width="24" height="67"/><rect x="223" y="105" width="24" height="55"/><rect x="247" y="93" width="39" height="67"/><rect x="286" y="84" width="48" height="76"/><rect x="334" y="80" width="29" height="80"/><rect x="368" y="117" width="40" height="43"/><rect x="412" y="95" width="40" height="65"/><rect x="452" y="118" width="29" height="42"/><rect x="485" y="102" width="26" height="58"/><rect x="514" y="86" width="26" height="74"/><rect x="540" y="101" width="40" height="59"/><rect x="584" y="77" width="48" height="83"/><rect x="633" y="83" width="25" height="77"/><rect x="662" y="108" width="42" height="52"/><rect x="706" y="85" width="25" height="75"/><rect x="736" y="84" width="24" height="76"/><rect x="760" y="107" width="41" height="53"/><rect x="804" y="86" width="43" height="74"/><rect x="850" y="100" width="46" height="60"/><rect x="899" y="91" width="40" height="69"/></g>
  <g fill="#ffd98a" opacity="0.5"><rect x="311" y="95" width="3" height="4"/><rect x="818" y="91" width="3" height="4"/><rect x="720" y="129" width="3" height="4"/><rect x="254" y="85" width="3" height="4"/><rect x="593" y="99" width="3" height="4"/><rect x="542" y="111" width="3" height="4"/><rect x="356" y="126" width="3" height="4"/><rect x="464" y="98" width="3" height="4"/><rect x="628" y="84" width="3" height="4"/><rect x="125" y="112" width="3" height="4"/><rect x="433" y="90" width="3" height="4"/><rect x="780" y="101" width="3" height="4"/><rect x="160" y="139" width="3" height="4"/><rect x="505" y="106" width="3" height="4"/><rect x="45" y="122" width="3" height="4"/><rect x="84" y="128" width="3" height="4"/><rect x="576" y="116" width="3" height="4"/><rect x="813" y="136" width="3" height="4"/><rect x="842" y="100" width="3" height="4"/><rect x="353" y="124" width="3" height="4"/><rect x="363" y="118" width="3" height="4"/><rect x="513" y="117" width="3" height="4"/><rect x="821" y="109" width="3" height="4"/><rect x="75" y="133" width="3" height="4"/><rect x="100" y="140" width="3" height="4"/><rect x="281" y="110" width="3" height="4"/><rect x="718" y="122" width="3" height="4"/><rect x="71" y="83" width="3" height="4"/><rect x="753" y="124" width="3" height="4"/><rect x="322" y="121" width="3" height="4"/><rect x="596" y="123" width="3" height="4"/><rect x="846" y="108" width="3" height="4"/><rect x="296" y="125" width="3" height="4"/><rect x="400" y="136" width="3" height="4"/><rect x="689" y="102" width="3" height="4"/><rect x="28" y="140" width="3" height="4"/><rect x="477" y="102" width="3" height="4"/><rect x="177" y="119" width="3" height="4"/><rect x="124" y="111" width="3" height="4"/><rect x="65" y="93" width="3" height="4"/></g>
  <rect x="0" y="168" width="900" height="32" fill="#3b2a22"/>
  <rect x="0" y="168" width="900" height="3" fill="#5a4033"/>
  <g transform="translate(22,0)"><rect x="6" y="110" width="5" height="60" fill="#5b3a29"/><rect x="109" y="110" width="5" height="60" fill="#5b3a29"/><rect x="0" y="140" width="120" height="28" rx="2" fill="#7a4e33"/><rect x="0" y="140" width="120" height="5" fill="#94613f"/><rect x="8" y="129" width="9" height="11" rx="2" fill="#e4572e"/><circle cx="27" cy="135" r="5.5" fill="#f2c14e"/><circle cx="42" cy="135" r="5.5" fill="#7fb069"/><rect x="53" y="129" width="9" height="11" rx="2" fill="#e4572e"/><circle cx="72" cy="135" r="5.5" fill="#f2a65a"/><circle cx="87" cy="135" r="5.5" fill="#9b5de5"/><rect x="98" y="129" width="9" height="11" rx="2" fill="#e4572e"/><path d="M -6 112 L 126 112 L 116 92 L 4 92 Z" fill="#fbf1e1"/><path d="M -6.0 112 L 10.5 112 L 18.0 92 L 4.0 92 Z" fill="#c8402e"/><path d="M 27.0 112 L 43.5 112 L 46.0 92 L 32.0 92 Z" fill="#c8402e"/><path d="M 60.0 112 L 76.5 112 L 74.0 92 L 60.0 92 Z" fill="#c8402e"/><path d="M 93.0 112 L 109.5 112 L 102.0 92 L 88.0 92 Z" fill="#c8402e"/><path d="M -6.0 112 A 8.2 6.9 0 0 0 10.5 112 Z" fill="#c8402e"/><path d="M 10.5 112 A 8.2 6.9 0 0 0 27.0 112 Z" fill="#fbf1e1"/><path d="M 27.0 112 A 8.2 6.9 0 0 0 43.5 112 Z" fill="#c8402e"/><path d="M 43.5 112 A 8.2 6.9 0 0 0 60.0 112 Z" fill="#fbf1e1"/><path d="M 60.0 112 A 8.2 6.9 0 0 0 76.5 112 Z" fill="#c8402e"/><path d="M 76.5 112 A 8.2 6.9 0 0 0 93.0 112 Z" fill="#fbf1e1"/><path d="M 93.0 112 A 8.2 6.9 0 0 0 109.5 112 Z" fill="#c8402e"/><path d="M 109.5 112 A 8.2 6.9 0 0 0 126.0 112 Z" fill="#fbf1e1"/><rect x="2" y="88" width="116" height="5" rx="2" fill="#5b3a29"/></g>
  <g transform="translate(168,0)"><rect x="6" y="110" width="5" height="60" fill="#5b3a29"/><rect x="109" y="110" width="5" height="60" fill="#5b3a29"/><rect x="0" y="140" width="120" height="28" rx="2" fill="#7a4e33"/><rect x="0" y="140" width="120" height="5" fill="#94613f"/><circle cx="12" cy="135" r="5.5" fill="#f2c14e"/><circle cx="27" cy="135" r="5.5" fill="#7fb069"/><rect x="38" y="129" width="9" height="11" rx="2" fill="#e4572e"/><circle cx="57" cy="135" r="5.5" fill="#f2a65a"/><circle cx="72" cy="135" r="5.5" fill="#9b5de5"/><rect x="83" y="129" width="9" height="11" rx="2" fill="#e4572e"/><circle cx="102" cy="135" r="5.5" fill="#f2c14e"/><path d="M -6 112 L 126 112 L 116 92 L 4 92 Z" fill="#fbf1e1"/><path d="M -6.0 112 L 10.5 112 L 18.0 92 L 4.0 92 Z" fill="#2f6f4f"/><path d="M 27.0 112 L 43.5 112 L 46.0 92 L 32.0 92 Z" fill="#2f6f4f"/><path d="M 60.0 112 L 76.5 112 L 74.0 92 L 60.0 92 Z" fill="#2f6f4f"/><path d="M 93.0 112 L 109.5 112 L 102.0 92 L 88.0 92 Z" fill="#2f6f4f"/><path d="M -6.0 112 A 8.2 6.9 0 0 0 10.5 112 Z" fill="#2f6f4f"/><path d="M 10.5 112 A 8.2 6.9 0 0 0 27.0 112 Z" fill="#fbf1e1"/><path d="M 27.0 112 A 8.2 6.9 0 0 0 43.5 112 Z" fill="#2f6f4f"/><path d="M 43.5 112 A 8.2 6.9 0 0 0 60.0 112 Z" fill="#fbf1e1"/><path d="M 60.0 112 A 8.2 6.9 0 0 0 76.5 112 Z" fill="#2f6f4f"/><path d="M 76.5 112 A 8.2 6.9 0 0 0 93.0 112 Z" fill="#fbf1e1"/><path d="M 93.0 112 A 8.2 6.9 0 0 0 109.5 112 Z" fill="#2f6f4f"/><path d="M 109.5 112 A 8.2 6.9 0 0 0 126.0 112 Z" fill="#fbf1e1"/><rect x="2" y="88" width="116" height="5" rx="2" fill="#5b3a29"/></g>
  <g transform="translate(314,0)"><rect x="6" y="110" width="5" height="60" fill="#5b3a29"/><rect x="109" y="110" width="5" height="60" fill="#5b3a29"/><rect x="0" y="140" width="120" height="28" rx="2" fill="#7a4e33"/><rect x="0" y="140" width="120" height="5" fill="#94613f"/><circle cx="12" cy="135" r="5.5" fill="#7fb069"/><rect x="23" y="129" width="9" height="11" rx="2" fill="#e4572e"/><circle cx="42" cy="135" r="5.5" fill="#f2a65a"/><circle cx="57" cy="135" r="5.5" fill="#9b5de5"/><rect x="68" y="129" width="9" height="11" rx="2" fill="#e4572e"/><circle cx="87" cy="135" r="5.5" fill="#f2c14e"/><circle cx="102" cy="135" r="5.5" fill="#7fb069"/><path d="M -6 112 L 126 112 L 116 92 L 4 92 Z" fill="#fbf1e1"/><path d="M -6.0 112 L 10.5 112 L 18.0 92 L 4.0 92 Z" fill="#e0a32a"/><path d="M 27.0 112 L 43.5 112 L 46.0 92 L 32.0 92 Z" fill="#e0a32a"/><path d="M 60.0 112 L 76.5 112 L 74.0 92 L 60.0 92 Z" fill="#e0a32a"/><path d="M 93.0 112 L 109.5 112 L 102.0 92 L 88.0 92 Z" fill="#e0a32a"/><path d="M -6.0 112 A 8.2 6.9 0 0 0 10.5 112 Z" fill="#e0a32a"/><path d="M 10.5 112 A 8.2 6.9 0 0 0 27.0 112 Z" fill="#fbf1e1"/><path d="M 27.0 112 A 8.2 6.9 0 0 0 43.5 112 Z" fill="#e0a32a"/><path d="M 43.5 112 A 8.2 6.9 0 0 0 60.0 112 Z" fill="#fbf1e1"/><path d="M 60.0 112 A 8.2 6.9 0 0 0 76.5 112 Z" fill="#e0a32a"/><path d="M 76.5 112 A 8.2 6.9 0 0 0 93.0 112 Z" fill="#fbf1e1"/><path d="M 93.0 112 A 8.2 6.9 0 0 0 109.5 112 Z" fill="#e0a32a"/><path d="M 109.5 112 A 8.2 6.9 0 0 0 126.0 112 Z" fill="#fbf1e1"/><rect x="2" y="88" width="116" height="5" rx="2" fill="#5b3a29"/></g>
  <g transform="translate(460,0)"><rect x="6" y="110" width="5" height="60" fill="#5b3a29"/><rect x="109" y="110" width="5" height="60" fill="#5b3a29"/><rect x="0" y="140" width="120" height="28" rx="2" fill="#7a4e33"/><rect x="0" y="140" width="120" height="5" fill="#94613f"/><rect x="8" y="129" width="9" height="11" rx="2" fill="#e4572e"/><circle cx="27" cy="135" r="5.5" fill="#f2a65a"/><circle cx="42" cy="135" r="5.5" fill="#9b5de5"/><rect x="53" y="129" width="9" height="11" rx="2" fill="#e4572e"/><circle cx="72" cy="135" r="5.5" fill="#f2c14e"/><circle cx="87" cy="135" r="5.5" fill="#7fb069"/><rect x="98" y="129" width="9" height="11" rx="2" fill="#e4572e"/><path d="M -6 112 L 126 112 L 116 92 L 4 92 Z" fill="#fbf1e1"/><path d="M -6.0 112 L 10.5 112 L 18.0 92 L 4.0 92 Z" fill="#2d5d8a"/><path d="M 27.0 112 L 43.5 112 L 46.0 92 L 32.0 92 Z" fill="#2d5d8a"/><path d="M 60.0 112 L 76.5 112 L 74.0 92 L 60.0 92 Z" fill="#2d5d8a"/><path d="M 93.0 112 L 109.5 112 L 102.0 92 L 88.0 92 Z" fill="#2d5d8a"/><path d="M -6.0 112 A 8.2 6.9 0 0 0 10.5 112 Z" fill="#2d5d8a"/><path d="M 10.5 112 A 8.2 6.9 0 0 0 27.0 112 Z" fill="#fbf1e1"/><path d="M 27.0 112 A 8.2 6.9 0 0 0 43.5 112 Z" fill="#2d5d8a"/><path d="M 43.5 112 A 8.2 6.9 0 0 0 60.0 112 Z" fill="#fbf1e1"/><path d="M 60.0 112 A 8.2 6.9 0 0 0 76.5 112 Z" fill="#2d5d8a"/><path d="M 76.5 112 A 8.2 6.9 0 0 0 93.0 112 Z" fill="#fbf1e1"/><path d="M 93.0 112 A 8.2 6.9 0 0 0 109.5 112 Z" fill="#2d5d8a"/><path d="M 109.5 112 A 8.2 6.9 0 0 0 126.0 112 Z" fill="#fbf1e1"/><rect x="2" y="88" width="116" height="5" rx="2" fill="#5b3a29"/></g>
  <g transform="translate(606,0)"><rect x="6" y="110" width="5" height="60" fill="#5b3a29"/><rect x="109" y="110" width="5" height="60" fill="#5b3a29"/><rect x="0" y="140" width="120" height="28" rx="2" fill="#7a4e33"/><rect x="0" y="140" width="120" height="5" fill="#94613f"/><circle cx="12" cy="135" r="5.5" fill="#f2a65a"/><circle cx="27" cy="135" r="5.5" fill="#9b5de5"/><rect x="38" y="129" width="9" height="11" rx="2" fill="#e4572e"/><circle cx="57" cy="135" r="5.5" fill="#f2c14e"/><circle cx="72" cy="135" r="5.5" fill="#7fb069"/><rect x="83" y="129" width="9" height="11" rx="2" fill="#e4572e"/><circle cx="102" cy="135" r="5.5" fill="#f2a65a"/><path d="M -6 112 L 126 112 L 116 92 L 4 92 Z" fill="#fbf1e1"/><path d="M -6.0 112 L 10.5 112 L 18.0 92 L 4.0 92 Z" fill="#b8457a"/><path d="M 27.0 112 L 43.5 112 L 46.0 92 L 32.0 92 Z" fill="#b8457a"/><path d="M 60.0 112 L 76.5 112 L 74.0 92 L 60.0 92 Z" fill="#b8457a"/><path d="M 93.0 112 L 109.5 112 L 102.0 92 L 88.0 92 Z" fill="#b8457a"/><path d="M -6.0 112 A 8.2 6.9 0 0 0 10.5 112 Z" fill="#b8457a"/><path d="M 10.5 112 A 8.2 6.9 0 0 0 27.0 112 Z" fill="#fbf1e1"/><path d="M 27.0 112 A 8.2 6.9 0 0 0 43.5 112 Z" fill="#b8457a"/><path d="M 43.5 112 A 8.2 6.9 0 0 0 60.0 112 Z" fill="#fbf1e1"/><path d="M 60.0 112 A 8.2 6.9 0 0 0 76.5 112 Z" fill="#b8457a"/><path d="M 76.5 112 A 8.2 6.9 0 0 0 93.0 112 Z" fill="#fbf1e1"/><path d="M 93.0 112 A 8.2 6.9 0 0 0 109.5 112 Z" fill="#b8457a"/><path d="M 109.5 112 A 8.2 6.9 0 0 0 126.0 112 Z" fill="#fbf1e1"/><rect x="2" y="88" width="116" height="5" rx="2" fill="#5b3a29"/></g>
  <g transform="translate(752,0)"><rect x="6" y="110" width="5" height="60" fill="#5b3a29"/><rect x="109" y="110" width="5" height="60" fill="#5b3a29"/><rect x="0" y="140" width="120" height="28" rx="2" fill="#7a4e33"/><rect x="0" y="140" width="120" height="5" fill="#94613f"/><circle cx="12" cy="135" r="5.5" fill="#9b5de5"/><rect x="23" y="129" width="9" height="11" rx="2" fill="#e4572e"/><circle cx="42" cy="135" r="5.5" fill="#f2c14e"/><circle cx="57" cy="135" r="5.5" fill="#7fb069"/><rect x="68" y="129" width="9" height="11" rx="2" fill="#e4572e"/><circle cx="87" cy="135" r="5.5" fill="#f2a65a"/><circle cx="102" cy="135" r="5.5" fill="#9b5de5"/><path d="M -6 112 L 126 112 L 116 92 L 4 92 Z" fill="#fbf1e1"/><path d="M -6.0 112 L 10.5 112 L 18.0 92 L 4.0 92 Z" fill="#c8402e"/><path d="M 27.0 112 L 43.5 112 L 46.0 92 L 32.0 92 Z" fill="#c8402e"/><path d="M 60.0 112 L 76.5 112 L 74.0 92 L 60.0 92 Z" fill="#c8402e"/><path d="M 93.0 112 L 109.5 112 L 102.0 92 L 88.0 92 Z" fill="#c8402e"/><path d="M -6.0 112 A 8.2 6.9 0 0 0 10.5 112 Z" fill="#c8402e"/><path d="M 10.5 112 A 8.2 6.9 0 0 0 27.0 112 Z" fill="#fbf1e1"/><path d="M 27.0 112 A 8.2 6.9 0 0 0 43.5 112 Z" fill="#c8402e"/><path d="M 43.5 112 A 8.2 6.9 0 0 0 60.0 112 Z" fill="#fbf1e1"/><path d="M 60.0 112 A 8.2 6.9 0 0 0 76.5 112 Z" fill="#c8402e"/><path d="M 76.5 112 A 8.2 6.9 0 0 0 93.0 112 Z" fill="#fbf1e1"/><path d="M 93.0 112 A 8.2 6.9 0 0 0 109.5 112 Z" fill="#c8402e"/><path d="M 109.5 112 A 8.2 6.9 0 0 0 126.0 112 Z" fill="#fbf1e1"/><rect x="2" y="88" width="116" height="5" rx="2" fill="#5b3a29"/></g>
  <path d="M -20.0 40.0 L -8.0 43.3 L 4.0 46.5 L 16.0 49.4 L 28.0 52.2 L 40.0 54.9 L 52.0 57.3 L 64.0 59.6 L 76.0 61.8 L 88.0 63.7 L 100.0 65.5 L 112.0 67.1 L 124.0 68.6 L 136.0 69.8 L 148.0 70.9 L 160.0 71.9 L 172.0 72.6 L 184.0 73.2 L 196.0 73.7 L 208.0 73.9 L 220.0 74.0 L 232.0 73.9 L 244.0 73.7 L 256.0 73.2 L 268.0 72.6 L 280.0 71.9 L 292.0 70.9 L 304.0 69.8 L 316.0 68.6 L 328.0 67.1 L 340.0 65.5 L 352.0 63.7 L 364.0 61.8 L 376.0 59.6 L 388.0 57.3 L 400.0 54.9 L 412.0 52.2 L 424.0 49.4 L 436.0 46.5 L 448.0 43.3 L 460.0 40.0" fill="none" stroke="#2a2233" stroke-width="1.3"/><path d="M 440.0 36.0 L 452.0 38.9 L 464.0 41.7 L 476.0 44.3 L 488.0 46.8 L 500.0 49.1 L 512.0 51.3 L 524.0 53.3 L 536.0 55.2 L 548.0 56.9 L 560.0 58.5 L 572.0 59.9 L 584.0 61.2 L 596.0 62.3 L 608.0 63.3 L 620.0 64.1 L 632.0 64.8 L 644.0 65.3 L 656.0 65.7 L 668.0 65.9 L 680.0 66.0 L 692.0 65.9 L 704.0 65.7 L 716.0 65.3 L 728.0 64.8 L 740.0 64.1 L 752.0 63.3 L 764.0 62.3 L 776.0 61.2 L 788.0 59.9 L 800.0 58.5 L 812.0 56.9 L 824.0 55.2 L 836.0 53.3 L 848.0 51.3 L 860.0 49.1 L 872.0 46.8 L 884.0 44.3 L 896.0 41.7 L 908.0 38.9 L 920.0 36.0" fill="none" stroke="#2a2233" stroke-width="1.3"/>
  <circle cx="4.0" cy="51.5" r="9" fill="url(#mk-glow)"/><circle cx="4.0" cy="51.5" r="3" fill="#ffe08a"/><circle cx="28.0" cy="57.2" r="9" fill="url(#mk-glow)"/><circle cx="28.0" cy="57.2" r="3" fill="#ffe08a"/><circle cx="52.0" cy="62.3" r="9" fill="url(#mk-glow)"/><circle cx="52.0" cy="62.3" r="3" fill="#ffe08a"/><circle cx="76.0" cy="66.8" r="9" fill="url(#mk-glow)"/><circle cx="76.0" cy="66.8" r="3" fill="#ffe08a"/><circle cx="100.0" cy="70.5" r="9" fill="url(#mk-glow)"/><circle cx="100.0" cy="70.5" r="3" fill="#ffe08a"/><circle cx="124.0" cy="73.6" r="9" fill="url(#mk-glow)"/><circle cx="124.0" cy="73.6" r="3" fill="#ffe08a"/><circle cx="148.0" cy="75.9" r="9" fill="url(#mk-glow)"/><circle cx="148.0" cy="75.9" r="3" fill="#ffe08a"/><circle cx="172.0" cy="77.6" r="9" fill="url(#mk-glow)"/><circle cx="172.0" cy="77.6" r="3" fill="#ffe08a"/><circle cx="196.0" cy="78.7" r="9" fill="url(#mk-glow)"/><circle cx="196.0" cy="78.7" r="3" fill="#ffe08a"/><circle cx="220.0" cy="79.0" r="9" fill="url(#mk-glow)"/><circle cx="220.0" cy="79.0" r="3" fill="#ffe08a"/><circle cx="244.0" cy="78.7" r="9" fill="url(#mk-glow)"/><circle cx="244.0" cy="78.7" r="3" fill="#ffe08a"/><circle cx="268.0" cy="77.6" r="9" fill="url(#mk-glow)"/><circle cx="268.0" cy="77.6" r="3" fill="#ffe08a"/><circle cx="292.0" cy="75.9" r="9" fill="url(#mk-glow)"/><circle cx="292.0" cy="75.9" r="3" fill="#ffe08a"/><circle cx="316.0" cy="73.6" r="9" fill="url(#mk-glow)"/><circle cx="316.0" cy="73.6" r="3" fill="#ffe08a"/><circle cx="340.0" cy="70.5" r="9" fill="url(#mk-glow)"/><circle cx="340.0" cy="70.5" r="3" fill="#ffe08a"/><circle cx="364.0" cy="66.8" r="9" fill="url(#mk-glow)"/><circle cx="364.0" cy="66.8" r="3" fill="#ffe08a"/><circle cx="388.0" cy="62.3" r="9" fill="url(#mk-glow)"/><circle cx="388.0" cy="62.3" r="3" fill="#ffe08a"/><circle cx="412.0" cy="57.2" r="9" fill="url(#mk-glow)"/><circle cx="412.0" cy="57.2" r="3" fill="#ffe08a"/><circle cx="436.0" cy="51.5" r="9" fill="url(#mk-glow)"/><circle cx="436.0" cy="51.5" r="3" fill="#ffe08a"/><circle cx="464.0" cy="46.7" r="9" fill="url(#mk-glow)"/><circle cx="464.0" cy="46.7" r="3" fill="#ffe08a"/><circle cx="488.0" cy="51.8" r="9" fill="url(#mk-glow)"/><circle cx="488.0" cy="51.8" r="3" fill="#ffe08a"/><circle cx="512.0" cy="56.3" r="9" fill="url(#mk-glow)"/><circle cx="512.0" cy="56.3" r="3" fill="#ffe08a"/><circle cx="536.0" cy="60.2" r="9" fill="url(#mk-glow)"/><circle cx="536.0" cy="60.2" r="3" fill="#ffe08a"/><circle cx="560.0" cy="63.5" r="9" fill="url(#mk-glow)"/><circle cx="560.0" cy="63.5" r="3" fill="#ffe08a"/><circle cx="584.0" cy="66.2" r="9" fill="url(#mk-glow)"/><circle cx="584.0" cy="66.2" r="3" fill="#ffe08a"/><circle cx="608.0" cy="68.3" r="9" fill="url(#mk-glow)"/><circle cx="608.0" cy="68.3" r="3" fill="#ffe08a"/><circle cx="632.0" cy="69.8" r="9" fill="url(#mk-glow)"/><circle cx="632.0" cy="69.8" r="3" fill="#ffe08a"/><circle cx="656.0" cy="70.7" r="9" fill="url(#mk-glow)"/><circle cx="656.0" cy="70.7" r="3" fill="#ffe08a"/><circle cx="680.0" cy="71.0" r="9" fill="url(#mk-glow)"/><circle cx="680.0" cy="71.0" r="3" fill="#ffe08a"/><circle cx="704.0" cy="70.7" r="9" fill="url(#mk-glow)"/><circle cx="704.0" cy="70.7" r="3" fill="#ffe08a"/><circle cx="728.0" cy="69.8" r="9" fill="url(#mk-glow)"/><circle cx="728.0" cy="69.8" r="3" fill="#ffe08a"/><circle cx="752.0" cy="68.3" r="9" fill="url(#mk-glow)"/><circle cx="752.0" cy="68.3" r="3" fill="#ffe08a"/><circle cx="776.0" cy="66.2" r="9" fill="url(#mk-glow)"/><circle cx="776.0" cy="66.2" r="3" fill="#ffe08a"/><circle cx="800.0" cy="63.5" r="9" fill="url(#mk-glow)"/><circle cx="800.0" cy="63.5" r="3" fill="#ffe08a"/><circle cx="824.0" cy="60.2" r="9" fill="url(#mk-glow)"/><circle cx="824.0" cy="60.2" r="3" fill="#ffe08a"/><circle cx="848.0" cy="56.3" r="9" fill="url(#mk-glow)"/><circle cx="848.0" cy="56.3" r="3" fill="#ffe08a"/><circle cx="872.0" cy="51.8" r="9" fill="url(#mk-glow)"/><circle cx="872.0" cy="51.8" r="3" fill="#ffe08a"/><circle cx="896.0" cy="46.7" r="9" fill="url(#mk-glow)"/><circle cx="896.0" cy="46.7" r="3" fill="#ffe08a"/>
  <g transform="translate(450, 22)">
    <rect x="-112" y="-12" width="224" height="24" rx="12" fill="#fbf1e1" stroke="#c8402e" stroke-width="1.5"/>
    <text x="0" y="4" text-anchor="middle" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif" font-size="11" font-weight="800" fill="#a8321f" letter-spacing="1.5">MARKETS &amp; FESTIVALS</text>
  </g>
</svg>"""


_MARKETS_CSS = """
  .markets-hub {
    --bg: #fbf6ee; --card: #ffffff; --card-hover: #ffffff; --fg: #2a1f1a; --muted: #6b5a4e;
    --accent: #b23a26; --border: #eadfce;
    background: var(--bg) !important; color: var(--fg) !important;
  }
  .markets-hub header { background: #fbf6ee !important; border-bottom: 1px solid var(--border) !important; }
  .markets-hub .logo { color: #2a1f1a !important; }
  .markets-hub .hub-nav a { color: var(--muted); }
  .markets-hub .hub-nav a.active { color: #fff; background: var(--accent); padding: 2px 8px; border-radius: 999px; }
  .markets-hub .hero { border: 0; padding: 0; margin-bottom: 18px; background: #fff; border-radius: 22px;
    overflow: hidden; box-shadow: 0 10px 30px rgba(90, 50, 30, 0.12); text-align: left; }
  .mk-hero-art { display: block; width: 100%; height: 200px; }
  .mk-hero-copy { padding: 20px 24px 24px; }
  .markets-hub .hero h1 { font-size: clamp(30px, 6vw, 46px); line-height: 1.05; margin: 0 0 8px; color: #7a2617;
    letter-spacing: -0.015em; font-weight: 800; }
  .markets-hub .hero h1 small { display: block; font-size: 0.42em; color: #a8693a; font-weight: 700; margin-top: 6px; letter-spacing: 0; }
  .markets-hub .hero p { color: var(--muted); font-size: 16px; margin: 0 0 14px; max-width: 760px; }
  .mk-hero-bar { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 12px; margin: 0 0 16px; }
  .mk-stats { display: flex; flex-wrap: wrap; gap: 8px; margin: 0; }
  .mk-stat { background: #fdf0e3; color: #7a3a1c; border: 1px solid #f1d9bf; border-radius: 999px;
    padding: 5px 12px; font-size: 14px; font-weight: 700; }
  .markets-hub .cta-btn { display: inline-block; background: var(--accent); color: #fff; padding: 9px 18px;
    border-radius: 999px; font-weight: 700; font-size: 14px; text-decoration: none; margin-left: auto; white-space: nowrap; }

  /* Controls & Filter Bar */
  .mk-controls-bar { margin: 0 0 20px; }
  .mk-filters-row { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
  .mk-select {
    appearance: none;
    -webkit-appearance: none;
    background: #ffffff url("data:image/svg+xml;charset=utf-8,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='8' viewBox='0 0 12 8'%3E%3Cpath fill='%236b5a4e' d='M1.4 1.4L6 6l4.6-4.6' stroke='%236b5a4e' stroke-width='1.5' stroke-linecap='round' stroke-linejoin='round' fill='none'/%3E%3C/svg%3E") no-repeat right 10px center;
    border: 1px solid var(--border);
    border-radius: 999px;
    padding: 6px 30px 6px 12px;
    font: inherit;
    font-size: 13px;
    font-weight: 600;
    color: var(--fg);
    cursor: pointer;
    box-shadow: 0 1px 2px rgba(90, 50, 30, 0.05);
    transition: all 0.15s ease;
  }
  .mk-select:hover { border-color: var(--accent); }
  .mk-select:focus { outline: none; border-color: var(--accent); box-shadow: 0 0 0 3px rgba(178, 58, 38, 0.15); }
  .mk-near-btn {
    background: #ffffff;
    border: 1px solid var(--border);
    border-radius: 999px;
    padding: 6px 12px;
    font: inherit;
    font-size: 13px;
    font-weight: 600;
    color: var(--fg);
    cursor: pointer;
    transition: all 0.15s ease;
  }
  .mk-near-btn:hover { border-color: var(--accent); color: var(--accent); }
  .mk-view-toggle {
    display: inline-flex;
    align-items: center;
    background: #f1e5d5;
    border: 1px solid var(--border);
    border-radius: 999px;
    padding: 2px;
    gap: 2px;
    margin-left: auto;
  }
  .mk-view-btn {
    background: transparent;
    border: none;
    padding: 4px 10px;
    border-radius: 999px;
    font: inherit;
    font-size: 12px;
    font-weight: 600;
    color: var(--muted);
    cursor: pointer;
    transition: all 0.15s ease;
  }
  .mk-view-btn.active {
    background: var(--accent);
    color: #ffffff;
    font-weight: 700;
  }
  .mk-reset-btn {
    background: none;
    border: none;
    color: var(--accent);
    font: inherit;
    font-size: 12.5px;
    font-weight: 600;
    cursor: pointer;
    text-decoration: underline;
    padding: 4px 6px;
  }
  .mk-near-info {
    margin-top: 6px;
    font-size: 12px;
    color: #2f6f4f;
    font-weight: 600;
  }

  /* Map View */
  .mk-map-wrap {
    margin: 0 0 22px;
    background: #ffffff;
    border: 1px solid var(--border);
    border-radius: 14px;
    overflow: hidden;
    box-shadow: 0 4px 18px rgba(90, 50, 30, 0.08);
  }
  .mk-map-toolbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 8px 14px;
    background: #fdfaf5;
    border-bottom: 1px solid var(--border);
    font-size: 12.5px;
    font-weight: 600;
    color: var(--fg);
  }
  .mk-map-close-btn {
    background: none;
    border: 1px solid var(--border);
    border-radius: 999px;
    padding: 2px 8px;
    font: inherit;
    font-size: 11px;
    cursor: pointer;
    color: var(--muted);
  }
  .mk-map-close-btn:hover { color: var(--accent); border-color: var(--accent); }
  .markets-hub .leaflet-map { width: 100%; height: 420px; }

  /* Day headers */
  .markets-hub .hub-day { display: flex; align-items: baseline; gap: 10px; font-size: 20px; color: #2a1f1a;
    margin: 24px 0 8px; padding-bottom: 6px; border-bottom: 2px solid #eadfce; text-decoration: none; }
  .mk-count { font-size: 12px; font-weight: 700; color: var(--muted); background: #f3e8da; border-radius: 999px; padding: 2px 8px; }
  .markets-hub .hub-grid { display: flex; flex-direction: column; gap: 12px; }
  .mk-daily { background: linear-gradient(135deg, #2a3560, #7a3f5e); border-radius: 14px; padding: 4px 14px 14px; margin: 4px 0 10px; }
  .markets-hub .mk-daily .hub-day { color: #ffe7a3; border-bottom-color: rgba(255, 231, 163, 0.25); margin-top: 10px; }
  .markets-hub .mk-daily .mk-count { background: rgba(255, 231, 163, 0.2); color: #ffe7a3; }
  .markets-hub .mk-daily .mk-city-pill { border: 1px solid rgba(255, 255, 255, 0.28); box-shadow: 0 1px 4px rgba(0, 0, 0, 0.2); }
  .mk-city { margin: 2px 0 10px; }
  .mk-city-head { margin: 10px 0 6px; font-size: 13px; }
  .mk-city-pill { display: inline-block; padding: 2px 10px; border-radius: 999px; font-weight: 800; color: #fff;
    letter-spacing: 0.02em; font-size: 12px; }
  .mk-c-manhattan { background: #2d5d8a; } .mk-c-brooklyn { background: #b23a26; }
  .mk-c-queens { background: #2f6f4f; } .mk-c-bronx { background: #8a5a10; }
  .mk-c-staten_island { background: #5d3f8a; } .mk-c-citywide, .mk-c-other { background: #8a6a3a; }

  /* Streamlined List Layout */
  .mk-grid { display: flex; flex-direction: column; gap: 6px; }
  .markets-hub .mk-card {
    background: #ffffff;
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 10px 14px;
    display: grid;
    grid-template-columns: 140px minmax(0, 1fr);
    align-items: center;
    gap: 14px;
    box-shadow: 0 1px 3px rgba(90, 50, 30, 0.03);
    transition: all 0.15s ease;
  }
  .markets-hub .mk-card:hover {
    border-color: #d1bfa9;
    box-shadow: 0 3px 10px rgba(90, 50, 30, 0.07);
    transform: translateY(-1px);
  }
  .markets-hub .mk-card[hidden], .mk-city[hidden], .mk-daily[hidden], .mk-day-section[hidden], .mk-day-dist-grid[hidden] { display: none !important; }
  .mk-day-section { display: flex; flex-direction: column; }
  .mk-time-col { display: flex; flex-direction: column; gap: 2px; }
  .mk-when { display: flex; flex-direction: column; gap: 2px; font-size: 13px; }
  .mk-hours { font-weight: 800; color: #b23a26; font-variant-numeric: tabular-nums; font-size: 13px; line-height: 1.25; }
  .mk-span { font-weight: 700; color: #2f6f4f; font-size: 11.5px; line-height: 1.25; }
  .mk-content-col { min-width: 0; display: flex; flex-direction: column; gap: 3px; }
  .mk-card-top { display: flex; align-items: flex-start; justify-content: space-between; gap: 10px; flex-wrap: nowrap; }
  .markets-hub .mk-card .hub-title { margin: 0; font-size: 15.5px; font-weight: 700; line-height: 1.3; min-width: 0; }
  .markets-hub .mk-card .hub-title a { color: #2a1f1a; text-decoration: none; }
  .markets-hub .mk-card .hub-title a:hover { color: var(--accent); text-decoration: underline; }
  .mk-badges { display: inline-flex; align-items: center; gap: 6px; flex-shrink: 0; white-space: nowrap; }
  .mk-kind { font-size: 11.5px; font-weight: 700; color: #7a3a1c; background: #fdf0e3; border-radius: 999px; padding: 2px 8px; }
  .mk-k-farmers { background: #e8f3e6; color: #2f6f4f; } .mk-k-holiday { background: #fbe6e2; color: #a8321f; }
  .mk-k-flea { background: #efe7f6; color: #5d3f8a; } .mk-k-craft { background: #fdf0d8; color: #8a5a10; }
  .mk-k-festival { background: #e3eef8; color: #2d5d8a; }
  .mk-dist-badge { display: inline-flex; align-items: center; gap: 3px; font-size: 11px; font-weight: 700; padding: 1px 6px; border-radius: 999px; background: #e8f3e6; color: #2f6f4f; border: 1px solid #c2e2be; }
  .markets-hub .badge-free {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    background: #e8f5e9;
    color: #1b5e20;
    border: 1.5px solid #66bb6a;
    border-radius: 999px;
    padding: 2px 10px;
    font-weight: 800;
    font-size: 11.5px;
    line-height: 1.2;
  }
  .markets-hub .badge-price {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    background: #f3e8da;
    color: #6b5a4e;
    border: 1px solid #dfd1be;
    border-radius: 999px;
    padding: 2px 9px;
    font-weight: 700;
    font-size: 11.5px;
    line-height: 1.2;
  }
  .markets-hub .mk-card .hub-meta { display: flex; align-items: center; gap: 6px; font-size: 13px; color: var(--muted); flex-wrap: wrap; }
  .markets-hub .hub-venue-link {
    color: #554438;
    font-weight: 600;
    text-decoration: none;
    border-bottom: 1px dotted #b8a390;
    transition: color 0.15s ease, border-color 0.15s ease;
  }
  .markets-hub .hub-venue-link:hover { color: var(--accent); border-bottom-color: var(--accent); }
  .markets-hub .hub-desc { font-size: 13px; color: var(--muted); margin: 2px 0 0; line-height: 1.4; }
  .markets-hub .no-hub-events { text-align: center; color: var(--muted); font-size: 16px; padding: 30px 0; }

  @media (max-width: 680px) {
    .mk-hero-art { height: 140px; }
    .mk-hero-copy { padding: 16px 16px 20px; }
    .mk-view-toggle { margin-left: 0; }
    .markets-hub .mk-card { grid-template-columns: 1fr; gap: 6px; padding: 10px 12px; }
    .mk-card-top { flex-wrap: wrap; }
    .mk-time-col { border-bottom: 1px dashed #eddac8; padding-bottom: 5px; margin-bottom: 2px; }
    .mk-daily { padding: 2px 12px 12px; }
  }
"""


_HUB_MARKET_JS = """<script>
(function () {
  var chips = document.querySelectorAll('.hub-city-chip, .hub-type-chip');
  if (!chips.length && !document.querySelector('.mk-select')) return;
  var cards = document.querySelectorAll('.hub-card');
  var heads = document.querySelectorAll('.hub-day');
  var groups = document.querySelectorAll('.mk-city');
  var state = {city: 'all', type: 'all'};
  var sorting_dist = false;
  var lastCoords = null;
  var leafletMap = null;
  var markersLayer = null;

  cards.forEach(function (c) {
    c._origParent = c.parentNode;
    c._origNext = c.nextSibling;
  });

  var kindSelect = document.getElementById('mk-kind-select');
  var citySelect = document.getElementById('mk-city-select');
  var nearBtn = document.getElementById('mk-near-btn');
  var originSelect = document.getElementById('mk-origin-select');
  var nearInfo = document.getElementById('mk-near-info');
  var resetBtn = document.getElementById('mk-reset-btn');
  var viewListBtn = document.getElementById('mk-view-list');
  var viewMapBtn = document.getElementById('mk-view-map');
  var mapWrap = document.getElementById('mk-map-wrap');
  var mapCloseBtn = document.getElementById('mk-map-close');
  var mapStatus = document.getElementById('mk-map-status');

  function haversineMiles(lat1, lon1, lat2, lon2) {
    var R = 3958.8;
    var dLat = (lat2 - lat1) * Math.PI / 180;
    var dLon = (lon2 - lon1) * Math.PI / 180;
    var a = Math.sin(dLat / 2) * Math.sin(dLat / 2) +
            Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) *
            Math.sin(dLon / 2) * Math.sin(dLon / 2);
    return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  }

  function formatDist(m) {
    if (m < 10) return m.toFixed(1) + ' mi';
    return Math.round(m) + ' mi';
  }

  function loadLeaflet(callback) {
    if (window.L && window.L.map) {
      callback();
      return;
    }
    if (!document.querySelector('link[href*="leaflet"]')) {
      var css = document.createElement('link');
      css.rel = 'stylesheet';
      css.href = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css';
      document.head.appendChild(css);
    }
    if (window._leafletLoading) {
      var interval = setInterval(function () {
        if (window.L && window.L.map) {
          clearInterval(interval);
          callback();
        }
      }, 50);
      return;
    }
    window._leafletLoading = true;
    var script = document.createElement('script');
    script.src = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js';
    script.onload = function () {
      window._leafletLoading = false;
      callback();
    };
    document.head.appendChild(script);
  }

  function updateMapMarkers() {
    if (!leafletMap || !markersLayer) return;
    markersLayer.clearLayers();
    var bounds = [];
    var count = 0;
    cards.forEach(function (c) {
      if (c.hidden) return;
      var lat = parseFloat(c.dataset.lat), lng = parseFloat(c.dataset.lng);
      if (isNaN(lat) || isNaN(lng)) return;
      var title = c.dataset.title || (c.querySelector('.hub-title a') ? c.querySelector('.hub-title a').textContent : 'Market');
      var venue = c.dataset.venue || '';
      var gmaps = c.dataset.gmaps || '#';
      var url = c.dataset.url || '#';
      var timeText = c.querySelector('.mk-when') ? c.querySelector('.mk-when').textContent.trim() : '';

      var marker = L.marker([lat, lng]);
      var popupHtml = '<div style="font-family:sans-serif;font-size:13px;line-height:1.4;">' +
                      '<strong style="font-size:14px;"><a href="' + url + '" target="_blank" rel="noopener" style="color:#b23a26;text-decoration:none;">' + title + '</a></strong><br>' +
                      (venue ? '<a href="' + gmaps + '" target="_blank" rel="noopener" style="color:#6b5a4e;text-decoration:underline;">📍 ' + venue + '</a><br>' : '') +
                      (timeText ? '<span style="color:#2f6f4f;font-weight:700;">' + timeText + '</span><br>' : '') +
                      '<a href="' + url + '" target="_blank" rel="noopener" style="display:inline-block;margin-top:4px;color:#b23a26;font-size:12px;font-weight:600;">Event Info →</a>' +
                      '</div>';
      marker.bindPopup(popupHtml);
      markersLayer.addLayer(marker);
      bounds.push([lat, lng]);
      count++;
    });
    if (mapStatus) mapStatus.textContent = '📍 Showing ' + count + ' markets & festivals on map';
    if (bounds.length) {
      leafletMap.fitBounds(bounds, { padding: [30, 30], maxZoom: 15 });
    }
  }

  function initMap() {
    if (leafletMap) {
      updateMapMarkers();
      leafletMap.invalidateSize();
      return;
    }
    var mapEl = document.getElementById('mk-leaflet-map');
    if (!mapEl) return;
    leafletMap = L.map(mapEl, { center: [40.7359, -73.9911], zoom: 12 });
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a> contributors',
      maxZoom: 19
    }).addTo(leafletMap);
    markersLayer = L.layerGroup().addTo(leafletMap);
    updateMapMarkers();
  }

  function sortByDistance(userLat, userLng, originLabel) {
    sorting_dist = true;
    cards.forEach(function (c) {
      var lat = parseFloat(c.dataset.lat), lng = parseFloat(c.dataset.lng);
      var badge = c.querySelector('.mk-dist-badge');
      if (!isNaN(lat) && !isNaN(lng)) {
        var d = haversineMiles(userLat, userLng, lat, lng);
        c._dist = d;
        if (badge) {
          badge.textContent = '📍 ' + formatDist(d);
          badge.hidden = false;
        }
      } else {
        c._dist = 999999;
        if (badge) badge.hidden = true;
      }
    });

    var dailySec = document.querySelector('.mk-daily');
    if (dailySec) {
      var dailyDistGrid = dailySec.querySelector('.mk-day-dist-grid');
      var dCards = Array.prototype.slice.call(dailySec.querySelectorAll('.hub-card'));
      dCards.sort(function (a, b) { return (a._dist || 0) - (b._dist || 0); });
      if (dailyDistGrid) {
        dCards.forEach(function (c) { dailyDistGrid.appendChild(c); });
        dailyDistGrid.hidden = false;
      }
      dailySec.querySelectorAll('.mk-city').forEach(function (g) { g.hidden = true; });
    }

    document.querySelectorAll('.mk-day-section').forEach(function (sec) {
      var distGrid = sec.querySelector('.mk-day-dist-grid');
      var dayCards = Array.prototype.slice.call(sec.querySelectorAll('.hub-card'));
      dayCards.sort(function (a, b) { return (a._dist || 0) - (b._dist || 0); });
      if (distGrid) {
        dayCards.forEach(function (c) { distGrid.appendChild(c); });
        distGrid.hidden = false;
      }
      sec.querySelectorAll('.mk-city').forEach(function (g) { g.hidden = true; });
    });

    if (nearInfo) {
      nearInfo.textContent = '📍 Sorted by date, closest first from ' + originLabel;
      nearInfo.hidden = false;
    }
  }

  function restoreInitialOrder() {
    sorting_dist = false;
    cards.forEach(function (c) {
      var badge = c.querySelector('.mk-dist-badge');
      if (badge) badge.hidden = true;
      if (c._origParent) {
        c._origParent.insertBefore(c, c._origNext || null);
      }
    });
    document.querySelectorAll('.mk-day-dist-grid').forEach(function (g) {
      g.hidden = true;
    });
    document.querySelectorAll('.mk-city').forEach(function (g) {
      g.hidden = false;
    });
    if (nearInfo) {
      nearInfo.textContent = '';
      nearInfo.hidden = true;
    }
  }

  function activateNear(val) {
    if (originSelect) originSelect.hidden = false;
    if (val === 'here') {
      if (navigator.geolocation) {
        if (nearInfo) { nearInfo.textContent = '📍 Getting your location...'; nearInfo.hidden = false; }
        navigator.geolocation.getCurrentPosition(
          function (pos) {
            lastCoords = { lat: pos.coords.latitude, lng: pos.coords.longitude };
            if (originSelect) originSelect.value = 'here';
            sortByDistance(lastCoords.lat, lastCoords.lng, 'Your Location');
            show();
          },
          function () {
            lastCoords = { lat: 40.7536, lng: -73.9832 };
            if (originSelect) originSelect.value = '40.7536,-73.9832';
            sortByDistance(lastCoords.lat, lastCoords.lng, 'Midtown / Bryant Park');
            show();
          },
          { timeout: 7000 }
        );
        return;
      }
      val = '40.7536,-73.9832';
    }
    var parts = val.split(',');
    var lat = parseFloat(parts[0]), lng = parseFloat(parts[1]);
    var label = 'New York City';
    if (originSelect && originSelect.selectedIndex >= 0) {
      label = originSelect.options[originSelect.selectedIndex].text;
    }
    lastCoords = { lat: lat, lng: lng };
    sortByDistance(lat, lng, label);
    show();
  }

  function show() {
    var days = {};
    cards.forEach(function (c) {
      var on = (state.city === 'all' || c.dataset.city === state.city) &&
               (state.type === 'all' || c.dataset.mtype === state.type);
      c.hidden = !on;
      if (on) days[c.dataset.day] = 1;
    });

    heads.forEach(function (h) {
      var d = h.dataset.day;
      h.hidden = !days[d];
    });
    document.querySelectorAll('.mk-day-section').forEach(function (sec) {
      sec.hidden = !days[sec.dataset.day];
    });
    document.querySelectorAll('.mk-daily').forEach(function (sec) {
      sec.hidden = !days['daily'];
    });

    if (!sorting_dist) {
      groups.forEach(function (g) {
        g.hidden = !g.querySelector('.hub-card:not([hidden])');
      });
      document.querySelectorAll('.mk-city-head').forEach(function (h) { h.hidden = false; });
    }

    if (kindSelect) kindSelect.value = state.type;
    if (citySelect) citySelect.value = state.city;
    document.querySelectorAll('.hub-city-chip:not(.hub-type-chip)').forEach(function (b) { b.classList.toggle('active', b.dataset.city === state.city); });
    document.querySelectorAll('.hub-type-chip').forEach(function (b) { b.classList.toggle('active', b.dataset.mtype === state.type); });

    var isFiltered = state.city !== 'all' || state.type !== 'all' || sorting_dist;
    if (resetBtn) resetBtn.hidden = !isFiltered;

    var none = document.getElementById('hub-none');
    if (none) none.hidden = Object.keys(days).length > 0;

    var h = [];
    if (state.type !== 'all') h.push('type=' + state.type);
    if (state.city !== 'all') h.push('city=' + state.city);
    history.replaceState(null, '', h.length ? '#' + h.join('&') : location.pathname);

    if (leafletMap && mapWrap && mapWrap.style.display !== 'none') {
      updateMapMarkers();
    }
  }

  chips.forEach(function (b) {
    b.addEventListener('click', function () {
      if (b.dataset.mtype) state.type = b.dataset.mtype; else state.city = b.dataset.city;
      show();
    });
  });

  if (kindSelect) {
    kindSelect.addEventListener('change', function () {
      state.type = kindSelect.value;
      show();
    });
  }

  if (citySelect) {
    citySelect.addEventListener('change', function () {
      state.city = citySelect.value;
      show();
    });
  }

  if (nearBtn) {
    nearBtn.addEventListener('click', function () {
      activateNear('here');
    });
  }

  if (originSelect) {
    originSelect.addEventListener('change', function () {
      activateNear(originSelect.value);
    });
  }

  if (resetBtn) {
    resetBtn.addEventListener('click', function () {
      state = {city: 'all', type: 'all'};
      sorting_dist = false;
      if (originSelect) {
        originSelect.hidden = true;
        originSelect.selectedIndex = 0;
      }
      restoreInitialOrder();
      show();
    });
  }

  if (viewMapBtn) {
    viewMapBtn.addEventListener('click', function () {
      if (mapWrap) mapWrap.style.display = 'block';
      viewMapBtn.classList.add('active');
      viewMapBtn.setAttribute('aria-pressed', 'true');
      if (viewListBtn) {
        viewListBtn.classList.remove('active');
        viewListBtn.setAttribute('aria-pressed', 'false');
      }
      loadLeaflet(function () {
        initMap();
      });
    });
  }

  function hideMap() {
    if (mapWrap) mapWrap.style.display = 'none';
    if (viewListBtn) {
      viewListBtn.classList.add('active');
      viewListBtn.setAttribute('aria-pressed', 'true');
    }
    if (viewMapBtn) {
      viewMapBtn.classList.remove('active');
      viewMapBtn.setAttribute('aria-pressed', 'false');
    }
  }

  if (viewListBtn) viewListBtn.addEventListener('click', hideMap);
  if (mapCloseBtn) mapCloseBtn.addEventListener('click', hideMap);

  var t = location.hash.match(/type=(\\w+)/), c = location.hash.match(/city=(\\w+)/);
  if (t && document.querySelector('.hub-type-chip[data-mtype="' + t[1] + '"]')) state.type = t[1];
  if (c && document.querySelector('.hub-city-chip[data-city="' + c[1] + '"]')) state.city = c[1];
  show();
})();
</script>"""


def render_body(events, city_of, is_free, query, title, subtitle, city_labels, today=None):
    """Return (hero_html, filters_html, body_html) for a markets-style hub."""
    from venues_geo import resolve_event_geo

    today = today or datetime.now(EASTERN).date()
    mk_daily, mk_dated = _markets_split(events)
    cards_html = _render_market_sections(mk_daily, mk_dated, CARD_LIMIT, city_of, is_free, city_labels, today=today)
    joined = "".join(cards_html)

    present = {c for c, _ in _HUB_CITY_CHIPS if c != "all" and f'data-city="{c}"' in joined}
    kinds = [(k, lbl) for k, lbl, _rx in _MARKET_TYPES] + [_FESTIVAL_TYPE, _MARKET_OTHER]
    counts = {k: joined.count(f'data-mtype="{k}"') for k, _ in kinds}
    kind_options = (
        '<option class="hub-city-chip hub-type-chip active" data-mtype="all" value="all">🛍️ All Types</option>'
        + "".join(
            f'<option class="hub-city-chip hub-type-chip" data-mtype="{k}" value="{k}">{lbl} ({counts[k]})</option>'
            for k, lbl in kinds if counts[k]
        )
    )
    city_options = (
        '<option class="hub-city-chip active" data-city="all" value="all">📍 All Boroughs</option>'
        + "".join(
            f'<option class="hub-city-chip" data-city="{k}" value="{k}">{lbl}</option>'
            for k, lbl in _HUB_CITY_CHIPS if k != "all" and k in present
        )
    )

    filters_html = ""
    if cards_html:
        filters_html = f"""<div class="mk-controls-bar" role="group" aria-label="Filter markets and festivals">
  <div class="mk-filters-row">
    <select id="mk-kind-select" class="mk-select" aria-label="Filter by kind of market or festival">
      {kind_options}
    </select>
    <select id="mk-city-select" class="mk-select" aria-label="Filter by borough">
      {city_options}
    </select>
    <button type="button" id="mk-near-btn" class="mk-near-btn" title="Sort by distance from your location">📍 Near Me</button>
    <select id="mk-origin-select" class="mk-select mk-origin-select" aria-label="Choose starting point" hidden>
      <option value="here">📍 My Current Location</option>
      <option value="40.7536,-73.9832">Midtown / Bryant Park</option>
      <option value="40.7359,-73.9911">Union Square / Downtown</option>
      <option value="40.7181,-73.9571">Williamsburg / Greenpoint</option>
      <option value="40.7032,-73.9892">Downtown Brooklyn / DUMBO</option>
      <option value="40.7644,-73.9235">Astoria / Long Island City</option>
      <option value="40.7812,-73.9745">Upper West Side / Harlem</option>
    </select>
    <div class="mk-view-toggle" role="group" aria-label="View mode">
      <button type="button" id="mk-view-list" class="mk-view-btn active" aria-pressed="true">📋 List</button>
      <button type="button" id="mk-view-map" class="mk-view-btn" aria-pressed="false">🗺️ Map</button>
    </div>
    <button type="button" id="mk-reset-btn" class="mk-reset-btn" hidden>✕ Reset</button>
  </div>
  <div id="mk-near-info" class="mk-near-info" hidden></div>
  <div id="mk-map-wrap" class="mk-map-wrap" style="display:none;">
    <div class="mk-map-toolbar">
      <span id="mk-map-status" class="mk-map-status">📍 Loading markets map...</span>
      <button type="button" id="mk-map-close" class="mk-map-close-btn" aria-label="Close Map">✕ Close Map</button>
    </div>
    <div id="mk-leaflet-map" class="mk-leaflet-map" style="height:440px; width:100%;"></div>
  </div>
</div>"""

    week_end = today + timedelta(days=7)
    open_today = sum(1 for e in mk_daily if today in e["_daily_hours"]) + sum(
        1 for e in mk_dated if isinstance(e.get("_time"), datetime) and e["_time"].date() == today
    )
    this_week = len(mk_daily) + len({
        _series_key(e) for e in mk_dated
        if isinstance(e.get("_time"), datetime) and e["_time"].date() < week_end
    })
    places = {
        _place_label(city_of(e), e, city_labels, geo=resolve_event_geo(e))
        for e in mk_daily + mk_dated
    }

    hero_html = f"""<div class="hero">
    {_MARKETS_HERO_ART}
    <div class="mk-hero-copy">
      <h1>{escape(title)}<small>Manhattan · Brooklyn · Queens · The Bronx · Staten Island</small></h1>
      <p>{escape(subtitle)}</p>
      <div class="mk-hero-bar">
        <div class="mk-stats"><span class="mk-stat">🛍️ {this_week} this week</span>{f'<span class="mk-stat">☀️ {open_today} open today</span>' if open_today else ''}<span class="mk-stat">📍 {len(places)} neighborhoods &amp; boroughs</span></div>
        <a href="../{query}" class="cta-btn">Full calendar →</a>
      </div>
    </div>
  </div>"""

    body_html = "\n".join(cards_html) or '<p class="no-hub-events">No markets or festivals are listed right now.</p>'
    none_html = '<p id="hub-none" class="no-hub-events" hidden>No markets match those filters.</p>'
    return hero_html, filters_html, f"{body_html}\n{none_html}"
