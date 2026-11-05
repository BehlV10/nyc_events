"""Find new NYC Eventbrite organizers/venues and add them to eventbrite_organizers.json.

Eventbrite search pages are blocked from CI runners and rate-limit quick crawls, so this runs
occasionally (say monthly) from a home connection, slowly:

  1. Crawl Eventbrite search pages one at a time, GAP seconds apart (default 20). On a
     403/405/429 it pauses 10 minutes; a second refusal ends the crawl.
  2. Tally the organizer and venue behind every in-person NYC event the pages list.
  3. Verify each new candidate once through its JSON feed (one request, 3s apart) and keep it
     if it has 2+ upcoming in-window NYC events.
  4. Append the keepers to eventbrite_organizers.json (review the printed list; move anything
     unwanted to "excluded" so it is never re-added).

The scheduled scrape then reads those organizer feeds, which CI can reach.

usage:
  python3 scripts/discover_eventbrite.py               # crawl + verify + write
  python3 scripts/discover_eventbrite.py --dry-run     # crawl + verify, print only
  python3 scripts/discover_eventbrite.py --rows rows.jsonl   # reuse rows from an earlier crawl
"""
import argparse
import collections
import json
import os
import re
import sys
import time
from datetime import date, timedelta

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import nyc_geo  # noqa: E402
import scrapers  # noqa: E402

API_GAP = 3
PLACES = ["ny--new-york", "ny--brooklyn", "ny--queens", "ny--bronx", "ny--staten-island"]
CATEGORY_PAGES = ["all-events", "music--events", "nightlife--events", "performing-arts--events",
                  "food-and-drink--events", "community--events", "sports-and-fitness--events",
                  "family-and-education--events", "hobbies--events", "arts--events", "health--events",
                  "film-and-media--events", "holiday--events", "dating--events", "classes--events",
                  "parties--events", "festivals--events", "charity-and-causes--events"]

CAT_RULES = [
    ("comedy", r"comedy|standup|stand-up|improv"),
    ("clubbing", r"nightlife|club|\bdj\b|techno|house music|rave|reggaeton|afrobeats"),
    ("dance", r"\bdance|salsa|bachata|swing|tango|ballroom"),
    ("music", r"music|concert|jazz|hiphop|livemusic|\bband\b"),
    ("film", r"film|screening|cinema"),
    ("food", r"food|drink|wine|beer|cocktail|tasting"),
    ("sports", r"sports|fitness|\brun\b|running|yoga|workout|pickleball"),
    ("outdoors", r"travel & outdoor|\btour\b|walk|hike|historic"),
    ("family", r"family|kids|children"),
    ("books", r"\bbook|reading|poetry|author"),
    ("art", r"fine art|visual arts|gallery|\bart\b"),
    ("theater", r"theatre|theater|performing|drag|burlesque|cabaret"),
    ("gaming", r"\bgame|trivia|chess"),
    ("party", r"party|social gathering"),
]


def category_for(tags):
    text = " ".join(tags).lower()
    best = None
    for cat, pat in CAT_RULES:
        n = len(re.findall(pat, text))
        if n and (best is None or n > best[1]):
            best = (cat, n)
    return best[0] if best else "community"


def in_nyc(lat, lng):
    return nyc_geo.in_nyc(lat, lng)


def search_urls():
    urls = list(scrapers.EVENTBRITE_DISCOVERY_SEARCHES)
    for place in PLACES:
        for cat in CATEGORY_PAGES:
            urls.append(f"https://www.eventbrite.com/d/{place}/{cat}/")
    return list(dict.fromkeys(urls))


def _server_data(html):
    m = re.search(r"window\.__SERVER_DATA__\s*=\s*", html)
    if not m:
        return {}
    try:
        return json.JSONDecoder().raw_decode(html[m.end():])[0]
    except ValueError:
        return {}


def crawl(urls, gap, out_path):
    """Yield one row per event listed on each search page; rows are also appended to out_path."""
    strikes = 0
    with open(out_path, "a", encoding="utf-8") as out:
        for i, url in enumerate(urls):
            try:
                r = requests.get(url, headers={"User-Agent": scrapers.UA_CHROME}, timeout=25)
            except requests.RequestException as e:
                print(f"[{i + 1}/{len(urls)}] error {e}", flush=True)
                time.sleep(gap)
                continue
            if r.status_code in (403, 405, 429):
                strikes += 1
                print(f"[{i + 1}/{len(urls)}] {r.status_code} (strike {strikes})", flush=True)
                if strikes >= 2:
                    print("Eventbrite refused twice; stopping the crawl here.", flush=True)
                    return
                time.sleep(600)
                continue
            strikes = 0
            results = (((_server_data(r.text).get("search_data") or {}).get("events") or {}).get("results")) or []
            for e in results:
                pv = e.get("primary_venue") or {}
                addr = pv.get("address") or {}
                row = {"src": url, "eid": e.get("eventbrite_event_id") or e.get("id"), "name": e.get("name"),
                       "org": e.get("primary_organizer_id"), "venue_id": e.get("primary_venue_id"),
                       "venue": pv.get("name"), "lat": addr.get("latitude"), "lng": addr.get("longitude"),
                       "online": e.get("is_online_event"),
                       "tags": [t.get("display_name") for t in (e.get("tags") or []) if isinstance(t, dict)]}
                out.write(json.dumps(row) + "\n")
                yield row
            print(f"[{i + 1}/{len(urls)}] {len(results)} events  {url}", flush=True)
            time.sleep(gap)


def tally(rows):
    orgs = collections.defaultdict(lambda: {"eids": set(), "tags": collections.Counter()})
    venues = collections.defaultdict(lambda: {"eids": set(), "orgs": set(), "name": None, "tags": collections.Counter()})
    for r in rows:
        if r.get("online") or not in_nyc(r.get("lat"), r.get("lng")):
            continue
        if r.get("org"):
            orgs[str(r["org"])]["eids"].add(r["eid"])
            orgs[str(r["org"])]["tags"].update(r.get("tags") or [])
        if r.get("venue_id"):
            v = venues[str(r["venue_id"])]
            v["eids"].add(r["eid"])
            v["orgs"].add(str(r.get("org")))
            v["name"] = v["name"] or r.get("venue")
            v["tags"].update(r.get("tags") or [])
    return orgs, venues


def known_ids(data):
    ids = {str(s["id"]) for s in data.get("sources", [])} | {str(s["id"]) for s in data.get("excluded", [])}
    for v in scrapers.VENUES:
        m = scrapers._EB_API_RE.search(v.get("url") or "") if "/api/v3/" in (v.get("url") or "") else None
        if m:
            ids.add(m.group(2))
    return ids


def verify(kind, obj_id):
    """(upcoming in-window NYC events, display name) from one feed request, or None if refused."""
    today = date.today()
    end = today + timedelta(days=scrapers.HORIZON_DAYS + 1)
    url = (f"https://www.eventbrite.com/api/v3/{kind}s/{obj_id}/events/?status=live&expand=venue,organizer"
           f"&start_date.range_start={today}T00:00:00&start_date.range_end={end}T00:00:00")
    r = requests.get(url, headers={"User-Agent": scrapers.UA_CHROME, "Accept": "application/json"}, timeout=15)
    if r.status_code in (403, 405, 429):
        return None
    if r.status_code != 200:
        return 0, ""
    events = r.json().get("events") or []
    keep = [e for e in events if not e.get("online_event")
            and (not isinstance(e.get("venue"), dict) or scrapers._eb_venue_in_nyc(e["venue"]))]
    sample = (keep or events or [{}])[0]
    name = ((sample.get("organizer") or {}).get("name") if kind == "organizer" else (sample.get("venue") or {}).get("name")) or ""
    return len(keep), name.strip()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rows", help="reuse rows (JSONL) from an earlier crawl instead of crawling")
    ap.add_argument("--gap", type=float, default=20, help="seconds between search pages (default 20)")
    ap.add_argument("--max-pages", type=int, default=0, help="crawl at most this many search pages")
    ap.add_argument("--min-seen", type=int, default=2, help="organizer must appear on 2+ listed events")
    ap.add_argument("--venue-min-orgs", type=int, default=3, help="venue feed needs events from 3+ organizers")
    ap.add_argument("--dry-run", action="store_true", help="print what would be added; don't write")
    args = ap.parse_args()

    path = scrapers.EVENTBRITE_ORGANIZERS_FILE
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    if args.rows:
        rows = [json.loads(line) for line in open(args.rows, encoding="utf-8") if line.strip()]
    else:
        urls = search_urls()
        if args.max_pages:
            urls = urls[:args.max_pages]
        rows_path = os.path.join(ROOT, ".cache", f"eventbrite_discovery_{date.today()}.jsonl")
        os.makedirs(os.path.dirname(rows_path), exist_ok=True)
        print(f"Crawling {len(urls)} search pages, {args.gap:.0f}s apart (~{len(urls) * (args.gap + 3) / 60:.0f} min). Rows: {rows_path}")
        rows = list(crawl(urls, args.gap, rows_path))

    orgs, venues = tally(rows)
    have = known_ids(data)
    cands = [("organizer", oid, len(o["eids"]), o["tags"]) for oid, o in orgs.items()
             if len(o["eids"]) >= args.min_seen and oid not in have]
    cands += [("venue", vid, len(v["eids"]), v["tags"]) for vid, v in venues.items()
              if len(v["orgs"]) >= args.venue_min_orgs and vid not in have]
    cands.sort(key=lambda c: -c[2])
    print(f"{len(rows)} listed events -> {len(orgs)} NYC organizers, {len(venues)} venues; {len(cands)} new candidates to verify")

    added = []
    net_errors = 0
    try:
        for kind, obj_id, seen, tags in cands:
            try:
                res = verify(kind, obj_id)
            except (requests.RequestException, ValueError) as e:
                net_errors += 1
                print(f"  ! {kind} {obj_id}: {type(e).__name__}; skipped", flush=True)
                if net_errors >= 3:
                    print("Three network errors in a row; stopping verification (rerun later to continue).")
                    break
                time.sleep(API_GAP * 5)
                continue
            net_errors = 0
            if res is None:
                print("Eventbrite refused the feed request; stopping verification.")
                break
            upcoming, name = res
            if upcoming >= 2 and name:
                entry = {"id": obj_id, "kind": kind, "name": name, "category": category_for(list(tags.elements())),
                         "added": date.today().isoformat(), "upcoming_when_added": upcoming}
                added.append(entry)
                print(f"  + {kind:9} {obj_id:>14}  {upcoming:3} upcoming  {entry['category']:9} {name}", flush=True)
            time.sleep(API_GAP)
    except KeyboardInterrupt:
        print("Interrupted; saving what was verified so far.")
    finally:
        save(data, added, path, args.dry_run)


def save(data, added, path, dry_run):
    """Write verified finds even when verification stops early (rerunning skips them)."""
    taken = {s["name"] for s in data["sources"]} | {v["name"] for v in scrapers.VENUES}
    for entry in added:
        if entry["name"] in taken:
            entry["name"] += " (Eventbrite)"
        taken.add(entry["name"])
    if dry_run:
        print(f"dry run: {len(added)} would be added")
        return
    data["sources"].extend(added)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1, ensure_ascii=False)
        f.write("\n")
    print(f"Added {len(added)} to {os.path.relpath(path, ROOT)}. Review the names and categories, move anything "
          f"unwanted to \"excluded\" with a reason, then commit.")


if __name__ == "__main__":
    main()
