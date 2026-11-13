"""Pin venues the calendar lists by name only (no street address) using public geocoders.

Reads a scraped events.json, finds NYC-looking venue names that still have no map pin, and looks each
one up once: NYC Planning's GeoSearch (venue layer) first, then OpenStreetMap Nominatim (1 request/second,
descriptive User-Agent, per its usage policy). A hit is kept only when the place's name matches the
venue's name and the point is inside the five boroughs, so a wrong pin is worse than none.
Results (and misses) accumulate in venue_pins.json, which venues_geo.py reads as hand-checked pins.
Pins derived from OpenStreetMap are (c) OpenStreetMap contributors, ODbL.

usage:
  python3 scripts/geocode_venues.py events.json [--limit N] [--dry-run] [--retry-misses]
"""
import argparse
import collections
import json
import os
import re
import sys
import time
from datetime import date
from urllib.parse import quote

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import nyc_geo  # noqa: E402
import template as T  # noqa: E402
import venues_geo  # noqa: E402

PINS_FILE = os.path.join(ROOT, "venue_pins.json")
UA = "nycfunevents-venue-pins/1.0 (open-source NYC events calendar; github.com/BehlV10/nyc_events)"
SKIP_RE = re.compile(r"fever|secret|rides|walks|events$|runners|run club|meetup|group|socials?|classes|tours|tba\b|tbd\b|pop-?up|calendar|various|multiple|\(list\)|community events|online|virtual|zoom|private|"
                     r"location (tbd|tba)|your (home|place)|\bnyc (parks|park)\b|^new york(,| \(|$)|^(brooklyn|queens|bronx|manhattan)$", re.I)
STOP = {"the", "of", "and", "at", "nyc", "new", "york", "ny", "in", "a", "club", "center", "centre"}
BOROUGH_HINT = {"brooklyn": "Brooklyn", "queens": "Queens", "bronx": "Bronx", "staten_island": "Staten Island", "manhattan": "Manhattan"}


def _tokens(s):
    return {t for t in re.findall(r"[a-z0-9]+", s.lower()) if t not in STOP and len(t) > 1}


def clean_name(venue):
    return re.sub(r"\s+", " ", venue.split("(")[0]).strip(" ,-–|")


def name_matches(venue, place):
    """The place is the venue: nearly all of each name's distinctive words are shared, and the venue
    name has at least two (so a bare neighbourhood like "Chinatown" never matches)."""
    a, b = _tokens(clean_name(venue)), _tokens(place)
    if len(a) < 2 or not b:
        return False
    shared = len(a & b)
    return shared / len(a) >= 0.75 and shared / len(b) >= 0.9


def candidates(events_json):
    with open(events_json, encoding="utf-8") as f:
        data = json.load(f)
    dated, ongoing, _ = T.group_by_date(data["venues"])
    seen = collections.Counter()
    for e in [x for _, es in dated for x in es] + list(ongoing or []):
        v = (e.get("venue") or "").strip()
        if not v or T_resolved(e):
            continue
        text = f"{v.lower()} {(e.get('address') or '').lower()}"
        if nyc_geo.outside_nyc_text(text) or SKIP_RE.search(v) or len(clean_name(v)) < 4 or _not_a_venue(v):
            continue
        if nyc_geo.extract_address(f"{e.get('address') or ''} {v}"):
            continue  # the address geocoder handles these
        seen[v] += 1
    return seen


_NEIGHBORHOOD_WORDS = {w for _b, ws in venues_geo._BOROUGH_WORDS for w in ws}
_NYC_TOWNS = {"new york", "nyc", "new york city", "brooklyn", "queens", "bronx", "the bronx", "staten island", "manhattan"}


def _not_a_venue(v):
    """A bare neighbourhood ("Chinatown"), or an address in a town outside the five boroughs."""
    name = clean_name(v).lower()
    for w in sorted(_NEIGHBORHOOD_WORDS, key=len, reverse=True):
        name = re.sub(r"\b" + re.escape(w) + r"\b", " ", name)
    if not _tokens(name) or len(_tokens(clean_name(v))) < 2:
        return True
    m = re.search(r",\s*([^,()]+?)\s*,?\s*(?:NY|NJ|New York|New Jersey)\b", v.split("(", 1)[1] if "(" in v else "", re.I)
    return bool(m and m.group(1).strip().lower() not in _NYC_TOWNS and not venues_geo._named_borough(f" {m.group(1).lower()} "))


def T_resolved(e):
    return T.resolve_event_geo(e) is not None


def geosearch(name, sess):
    r = sess.get("https://geosearch.planninglabs.nyc/v2/search", params={"text": name, "size": 3, "layers": "venue"}, timeout=15)
    r.raise_for_status()
    for f in r.json().get("features") or []:
        p = f["properties"]
        lng, lat = f["geometry"]["coordinates"]
        if name_matches(name, p.get("name") or "") and venues_geo.MIN_LAT <= lat <= venues_geo.MAX_LAT and nyc_geo.in_nyc(lat, lng):
            return lat, lng, p.get("name"), p.get("neighbourhood") or p.get("borough") or "", p.get("label") or "", "nyc-geosearch"
    return None


def nominatim(name, sess):
    r = sess.get("https://nominatim.openstreetmap.org/search",
                 params={"format": "jsonv2", "limit": 3, "countrycodes": "us", "viewbox": "-74.27,40.49,-73.68,40.92",
                         "bounded": 1, "addressdetails": 1, "q": name}, timeout=20)
    r.raise_for_status()
    for x in r.json():
        lat, lng = float(x["lat"]), float(x["lon"])
        if x.get("category") in ("place", "boundary", "highway") or x.get("class") in ("place", "boundary", "highway"):
            continue
        if name_matches(name, x.get("name") or "") and nyc_geo.in_nyc(lat, lng):
            a = x.get("address") or {}
            return (lat, lng, x.get("name"), a.get("neighbourhood") or a.get("suburb") or "",
                    ", ".join(p for p in (a.get("house_number"), a.get("road"), a.get("city") or a.get("borough")) if p), "osm")
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("events_json")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--retry-misses", action="store_true")
    args = ap.parse_args()
    try:
        pins = json.load(open(PINS_FILE, encoding="utf-8"))
    except (OSError, ValueError):
        pins = {"pins": {}, "misses": {}}
    names = candidates(args.events_json)
    todo = [n for n, _ in names.most_common() if n.lower() not in pins["pins"] and (args.retry_misses or n.lower() not in pins["misses"])]
    if args.limit:
        todo = todo[:args.limit]
    print(f"{len(names)} unmapped NYC-looking venue names; {len(todo)} to look up", flush=True)
    sess = requests.Session()
    sess.headers["User-Agent"] = UA
    hits = 0
    try:
        for n in todo:
            try:
                hit = geosearch(clean_name(n), sess)
                time.sleep(0.3)
                if not hit:
                    hit = nominatim(clean_name(n), sess)
                    time.sleep(1.1)
            except (requests.RequestException, ValueError) as ex:
                print(f"  ! {n}: {type(ex).__name__}", flush=True)
                time.sleep(5)
                continue
            if hit:
                lat, lng, pname, neigh, addr, src = hit
                pins["pins"][n.lower()] = {"lat": round(lat, 5), "lng": round(lng, 5), "name": clean_name(n), "neighborhood": neigh,
                                           "address": addr, "source": src, "added": date.today().isoformat(), "matched": pname}
                hits += 1
                print(f"  + {n[:50]:50} -> {pname[:40]} ({src}) {lat:.4f},{lng:.4f}", flush=True)
            else:
                pins["misses"][n.lower()] = date.today().isoformat()
    except KeyboardInterrupt:
        pass
    print(f"{hits} pinned, {len(todo) - hits} not found")
    if not args.dry_run:
        with open(PINS_FILE, "w", encoding="utf-8") as f:
            json.dump(pins, f, indent=1, ensure_ascii=False, sort_keys=True)
            f.write("\n")


if __name__ == "__main__":
    main()
