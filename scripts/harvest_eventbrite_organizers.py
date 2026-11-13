"""Turn Eventbrite events we already list (from other sources: AllEvents, DoNYC, Meetup, ...) into
tracked organizers in eventbrite_organizers.json.

For each Eventbrite event URL in a scraped events.json whose organizer isn't tracked yet, ask the public
event API who the organizer is (one request per event, EVENTBRITE_API_GAP apart), then verify each new
organizer once through its feed (2+ upcoming in-window NYC events) and append the keepers.

usage:
  python3 scripts/harvest_eventbrite_organizers.py events.json [--dry-run] [--limit N]
"""
import argparse
import collections
import json
import os
import sys
import time
from datetime import date

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import scrapers  # noqa: E402
import discover_eventbrite as disc  # noqa: E402


def snapshot_event_ids(path):
    """{event_id: [categories]} for Eventbrite event URLs listed by sources other than tracked organizer feeds."""
    tracked = {name for _k, _i, name, _c in scrapers._load_eventbrite_organizers()}
    out = collections.defaultdict(list)
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    for v in data["venues"]:
        if v["venue"] in tracked:
            continue
        for e in v["events"]:
            m = scrapers._EB_EVENT_ID_RE.search(e.get("url") or "")
            if m:
                out[m.group(1)].append(e.get("category") or "community")
    return out


def organizer_of(event_id):
    r = requests.get(f"https://www.eventbrite.com/api/v3/events/{event_id}/?expand=organizer",
                     headers={"User-Agent": scrapers.UA_CHROME, "Accept": "application/json"}, timeout=15)
    if r.status_code in (403, 405, 429):
        return "refused"
    if r.status_code != 200:
        return None
    org = r.json().get("organizer") or {}
    return (str(org["id"]), (org.get("name") or "").strip()) if org.get("id") else None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("events_json")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=0, help="look up at most this many events")
    args = ap.parse_args()

    path = scrapers.EVENTBRITE_ORGANIZERS_FILE
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    have = disc.known_ids(data)
    ids = snapshot_event_ids(args.events_json)
    print(f"{len(ids)} Eventbrite events in snapshot", flush=True)

    seen_path = os.path.join(ROOT, ".cache", "eventbrite_harvest_seen.json")  # events already looked up, so reruns resume
    try:
        seen = set(json.load(open(seen_path)))
    except (OSError, ValueError):
        seen = set()
    orgs = {}  # organizer id -> (name, [categories])
    looked = 0
    for event_id, cats in ids.items():
        if event_id in seen:
            continue
        if args.limit and looked >= args.limit:
            break
        try:
            res = organizer_of(event_id)
        except (requests.RequestException, ValueError):
            res = None
        if res != "refused":
            seen.add(event_id)
        looked += 1
        if res == "refused":
            print("Eventbrite refused; stopping lookups.", flush=True)
            break
        if res and res[0] not in have:
            oid, name = res
            orgs.setdefault(oid, (name, []))[1].extend(cats)
        time.sleep(scrapers.EVENTBRITE_API_GAP)
    if not args.dry_run:
        os.makedirs(os.path.dirname(seen_path), exist_ok=True)
        json.dump(sorted(seen), open(seen_path, "w"))
    print(f"{looked} looked up -> {len(orgs)} new organizers to verify", flush=True)

    added = []
    try:
        for oid, (name, cats) in orgs.items():
            try:
                res = disc.verify("organizer", oid)
            except (requests.RequestException, ValueError):
                time.sleep(disc.API_GAP * 3)
                continue
            if res is None:
                print("Eventbrite refused the feed request; stopping.", flush=True)
                break
            upcoming, vname = res
            name = vname or name
            if upcoming >= 2 and name:
                cat = collections.Counter(cats).most_common(1)[0][0]
                added.append({"id": oid, "kind": "organizer", "name": name, "category": cat,
                              "added": date.today().isoformat(), "upcoming_when_added": upcoming})
                print(f"  + {oid:>14} {upcoming:3} upcoming {cat:9} {name}", flush=True)
            time.sleep(disc.API_GAP)
    except KeyboardInterrupt:
        print("Interrupted; saving what was verified so far.")
    finally:
        disc.save(data, added, path, args.dry_run)


if __name__ == "__main__":
    main()
