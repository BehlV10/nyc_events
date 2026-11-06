#!/usr/bin/env python3
"""Write a ready-to-post weekend roundup (Reddit Markdown) to reddit_roundup.md.

Ported from Boston events. Picks the weekend's standout events per section using the same
scoring as scripts/curate_highlights.py (cross-listed shows, venue's own calendar, flagship
rooms, prime time, free), deduplicated across sources, labeled by borough, and linking the
landing pages from seo.py. Check each subreddit's self-promotion rules before posting.

Usage:
    python scripts/generate_reddit_roundup.py              # upcoming Fri-Sun
    python scripts/generate_reddit_roundup.py --per-section 8
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from curate_highlights import score_event  # noqa: E402
from scrapers import EASTERN  # noqa: E402
from seo import get_site_url, page_url  # noqa: E402
from template import CITY_LABELS, _event_city, _is_event_free, compute_recurring, group_by_date  # noqa: E402
from venues_geo import resolve_event_geo  # noqa: E402

SECTIONS = [
    ("🎵 Concerts & live music", {"music"}),
    ("🪩 DJ nights & dance parties", {"clubbing", "dance"}),
    ("🎭 Comedy & theater", {"comedy", "theater"}),
    ("🌿 Run clubs, hikes & outdoors", {"outdoors", "sports"}),
    ("🎨 Art, film & books", {"art", "film", "books"}),
    ("🎲 Games, food & community", {"gaming", "food", "community"}),
]


def weekend_dates(now):
    days_to_fri = (4 - now.weekday()) % 7
    if now.weekday() in (5, 6):  # already the weekend: cover the rest of it
        days_to_fri = -(now.weekday() - 4)
    fri = (now + timedelta(days=days_to_fri)).date()
    return [fri, fri + timedelta(days=1), fri + timedelta(days=2)]


def _line(e, free_note=False):
    t = e["_time"]
    city = _event_city(e.get("venue"), e.get("_source_venue"), geo=resolve_event_geo(e), event=e)
    where = e.get("venue") or e.get("_source_venue") or ""
    if city in CITY_LABELS and city not in ("other", "citywide"):
        where = f"{where} ({CITY_LABELS[city]})"
    price = " — free" if free_note else (f" — {e['price']}" if e.get("price") else "")
    when = f"{t.strftime('%a')} {t.strftime('%-I:%M %p')}"
    name = (e.get("name") or "").replace("[", "(").replace("]", ")")
    return f"* **[{name}]({e.get('url') or page_url('')})** @ {where} · {when}{price}"


def build_post(dated, per_section=6, now=None):
    now = now or datetime.now(EASTERN)
    days = set(weekend_dates(now))
    recurring = compute_recurring(dated)
    scored = []
    for day, events in dated:
        if day not in days:
            continue
        for e in events:
            if e.get("_time") and e["_time"] < now:
                continue
            s, _reasons = score_event(e, recurring)
            if s is not None and s > 0:
                scored.append((s, e))
    scored.sort(key=lambda x: -x[0])

    used = set()
    fri, sun = min(days), max(days)
    label = f"{fri.strftime('%b')} {fri.day}–{sun.strftime('%b') + ' ' if sun.month != fri.month else ''}{sun.day}"
    lines = [
        f"# NYC weekend roundup: {label}",
        "",
        "Some of the most-listed concerts, parties, shows, run clubs, and free things happening across the five boroughs this weekend:",
        "",
    ]
    for title, cats in SECTIONS:
        picks = []
        for s, e in scored:
            key = (e.get("name") or "").strip().lower()
            if e.get("category") in cats and key not in used:
                picks.append(e)
                used.add(key)
            if len(picks) >= per_section:
                break
        if picks:
            lines.append(f"### {title}")
            lines += [_line(e) for e in sorted(picks, key=lambda e: e["_time"])]
            lines.append("")
    free = []
    for s, e in scored:
        key = (e.get("name") or "").strip().lower()
        if _is_event_free(e) and key not in used:
            free.append(e)
            used.add(key)
        if len(free) >= per_section + 2:
            break
    if free:
        lines.append("### 🆓 Free")
        lines += [_line(e, free_note=True) for e in sorted(free, key=lambda e: e["_time"])]
        lines.append("")
    lines += [
        "---",
        f"*Pulled from [NYC Events]({page_url('')}), a free, ad-free calendar of upcoming NYC events from 600+ venue "
        f"calendars and community feeds, updated twice a day. More: [this weekend]({page_url('things-to-do-nyc-this-weekend/')}) · "
        f"[free this weekend]({page_url('free-events-nyc-this-weekend/')}) · [run clubs]({page_url('run-clubs-nyc/')}) · "
        f"[DJ nights]({page_url('dj-techno-nights-nyc/')}).*",
    ]
    return "\n".join(lines) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--per-section", type=int, default=6)
    ap.add_argument("--events", default=os.path.join(ROOT, "events.json"))
    ap.add_argument("--out", default=os.path.join(ROOT, "reddit_roundup.md"))
    args = ap.parse_args(argv)
    with open(args.events, encoding="utf-8") as f:
        payload = json.load(f)
    dated, _tba, _ongoing = group_by_date(payload.get("venues") if isinstance(payload, dict) else payload)
    post = build_post(dated, args.per_section)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(post)
    print(f"wrote {args.out} ({len(post.splitlines())} lines) for {get_site_url()}")


if __name__ == "__main__":
    main()
