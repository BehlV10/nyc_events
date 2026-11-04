#!/usr/bin/env python3
"""Pick each day's standout events and write them to highlights.json as editor's picks.

Ports the idea behind Boston's hand-curated highlights to an automatic curator. Each
deduplicated event is scored on signals the data actually carries:

  * how many independent sources list it (cross-listed shows are the ones people talk about)
  * whether a venue's own calendar lists it (vs. only a citywide aggregator or keyword search)
  * flagship venues (the commercial ticketed rooms in template.COMMERCIAL_VENUES)
  * prime-time starts, weekend daytime, and free entry

and penalized when it is a weekly repeat, outside the five boroughs, or a class/kids listing.
The top picks per day are chosen with a per-category cap so a day isn't all DJ sets.

Hand-written entries (without "auto": true) in highlights.json are kept as-is; previous
automatic picks are replaced on every run.

Usage:
    python scripts/curate_highlights.py                  # 9 days, 15 picks/day
    python scripts/curate_highlights.py --days 7 --per-day 10
"""

import argparse
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from scrapers import EASTERN, category_bucket  # noqa: E402
from template import (  # noqa: E402
    COMMERCIAL_VENUES,
    _event_city,
    _is_aggregator_source,
    _is_event_free,
    compute_recurring,
    group_by_date,
)
from venues_geo import resolve_event_geo  # noqa: E402

HIGHLIGHTS_FILE = os.path.join(ROOT, "highlights.json")

BADGES = {
    "music": "🎸 Music Pick", "clubbing": "🪩 Nightlife Pick", "dance": "💃 Dance Pick",
    "comedy": "😂 Comedy Pick", "theater": "🎭 Stage Pick", "film": "🎬 Film Pick",
    "art": "🖼️ Art Pick", "books": "📚 Lit Pick", "food": "🍜 Food Pick",
    "outdoors": "🌿 Outdoors Pick", "sports": "🏃 Active Pick", "gaming": "🎲 Game Night Pick",
    "community": "🤝 Community Pick",
}
EXCLUDED_CATEGORIES = {"services", "family", "kids"}
GENERIC_TITLE_RE = re.compile(
    r"\b(open play|drop[- ]in|practice|office hours|class(es)?|lesson|clinic|orientation|"
    r"meeting|registration|volunteer shift|tour departure)\b", re.I)
MAX_PER_BUCKET = 4


def _flagship(venue):
    v = (venue or "").lower()
    return any(cv in v for cv in COMMERCIAL_VENUES)


def score_event(e, recurring_keys):
    """Return (score, reasons) for one deduplicated event."""
    cat = e.get("category") or "other"
    if cat in EXCLUDED_CATEGORIES:
        return None, []
    city = _event_city(e.get("venue"), e.get("_source_venue"), resolve_event_geo(e), e)
    if city == "other":
        return None, []
    name = e.get("name") or ""
    reasons = []
    score = 0.0

    sources = 1 + len(e.get("_alt_sources") or [])
    if sources > 1:
        score += min(sources - 1, 3) * 4
        reasons.append(f"listed on {sources} calendars")
    if not _is_aggregator_source(e.get("_source_venue"), e.get("venue_url")):
        score += 3
    venue = e.get("venue") or ""
    if _flagship(venue):
        score += 3
        reasons.append(f"headline room at {venue}")

    t = e.get("_time")
    if t:
        if 18 <= t.hour <= 23:
            score += 2
            reasons.append("prime-time start")
        elif t.weekday() >= 5 and 10 <= t.hour < 18:
            score += 1.5
            reasons.append("weekend daytime")
        elif t.hour < 7 and t.hour != 0:
            score -= 2

    if _is_event_free(e):
        score += 2
        reasons.insert(0, "free")
    if e.get("description"):
        score += 0.5
    if (name.strip().lower(), e.get("_source_venue") or "") in recurring_keys:
        score -= 4
    if GENERIC_TITLE_RE.search(name):
        score -= 3
    if len(name) < 4:
        score -= 5
    return score, reasons


def curate(dated, days, per_day, recurring_keys):
    today = datetime.now(EASTERN).date()
    picks = []
    for day, events in dated:
        if not (today <= day < today + timedelta(days=days)):
            continue
        scored = []
        for e in events:
            s, reasons = score_event(e, recurring_keys)
            if s is not None and s > 0:
                scored.append((s, reasons, e))
        scored.sort(key=lambda x: (-x[0], x[2].get("name") or ""))
        per_bucket = Counter()
        seen_names = set()
        chosen = 0
        for s, reasons, e in scored:
            bucket = category_bucket(e.get("category"))
            key = re.sub(r"[^a-z0-9]+", " ", (e.get("name") or "").lower()).strip()
            if per_bucket[bucket] >= MAX_PER_BUCKET or key in seen_names:
                continue
            per_bucket[bucket] += 1
            seen_names.add(key)
            venue = e.get("venue") or ""
            note = (lambda t: t[:1].upper() + t[1:] + ".")("; ".join(reasons)) if reasons else None
            picks.append({
                "id": f"auto-{day.isoformat()}-{len(picks)}",
                "auto": True,
                "match": {
                    "name_contains": e.get("name") or "",
                    "venue_contains": re.split(r"\s*[\(,]", venue)[0].strip() if venue else "",
                },
                "badge": BADGES.get(e.get("category"), "⭐ Pick"),
                "note": note,
                "score": round(s, 1),
                "start_date": day.isoformat(),
                "expires": day.isoformat(),
            })
            chosen += 1
            if chosen >= per_day:
                break
    return picks


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--days", type=int, default=9)
    ap.add_argument("--per-day", type=int, default=15)
    ap.add_argument("--events", default=os.path.join(ROOT, "events.json"))
    ap.add_argument("--out", default=HIGHLIGHTS_FILE)
    args = ap.parse_args(argv)

    with open(args.events, encoding="utf-8") as f:
        payload = json.load(f)
    venues = payload.get("venues") if isinstance(payload, dict) else payload
    dated, _tba, _ongoing = group_by_date(venues)
    recurring_keys = compute_recurring(dated)

    manual = []
    if os.path.exists(args.out):
        try:
            with open(args.out, encoding="utf-8") as f:
                manual = [h for h in json.load(f) if isinstance(h, dict) and not h.get("auto")]
        except (OSError, ValueError):
            manual = []
    picks = curate(dated, args.days, args.per_day, recurring_keys)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(manual + picks, f, ensure_ascii=False, indent=2)
    print(f"wrote {args.out}: {len(manual)} hand-curated + {len(picks)} automatic picks")


if __name__ == "__main__":
    main()
