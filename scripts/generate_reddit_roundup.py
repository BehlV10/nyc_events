#!/usr/bin/env python3
"""Write a ready-to-post roundup (Reddit Markdown) to reddit_roundup.md.

Ported from Boston events. Picks standout events using the scoring in scripts/curate_highlights.py
(cross-listed shows, venue's own calendar, flagship rooms, prime time, free), one listing per show,
labeled by borough, and linking the landing pages from seo.py. Check each subreddit's
self-promotion rules before posting.

Usage:
    python scripts/generate_reddit_roundup.py                    # upcoming Fri-Sun, by section
    python scripts/generate_reddit_roundup.py --weekday          # Mon-Fri evenings, top picks per day
    python scripts/generate_reddit_roundup.py --borough brooklyn # a borough-only post (either mode)
    python scripts/generate_reddit_roundup.py --per-section 8

A "New on the site" block from roundup_news.json follows the intro for a week after each item's date.
"""

import argparse
import json
import os
import sys
from datetime import date, datetime, timedelta

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


def weekday_dates(now):
    """Monday to Friday of this week; the coming week once it's the weekend."""
    monday = (now + timedelta(days=(7 - now.weekday()) % 7 if now.weekday() >= 5 else -now.weekday())).date()
    return [monday + timedelta(days=i) for i in range(5)]


NEWS_PATH = os.path.join(ROOT, "roundup_news.json")
NEWS_DAYS = 7


def load_news(today, path=None):
    """Markdown lines for items dated within the last NEWS_DAYS days."""
    try:
        with open(path or NEWS_PATH, encoding="utf-8") as f:
            items = json.load(f).get("items") or []
    except (OSError, ValueError):
        return []
    out = []
    for it in items:
        try:
            age = (today - date.fromisoformat(it["date"])).days
        except (KeyError, ValueError):
            continue
        if 0 <= age <= NEWS_DAYS and it.get("text"):
            out.append(f"* {it['text']}")
    return out


def _in_borough(e, borough):
    return _event_city(e.get("venue"), e.get("_source_venue"), geo=resolve_event_geo(e), event=e) == borough


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


def _footer():
    return [
        "---",
        f"*Pulled from [NYC Events]({page_url('')}), a free, ad-free calendar of upcoming NYC events from 600+ venue "
        f"calendars and community feeds, updated twice a day. More: [this weekend]({page_url('things-to-do-nyc-this-weekend/')}) · "
        f"[free this weekend]({page_url('free-events-nyc-this-weekend/')}) · [run clubs]({page_url('run-clubs-nyc/')}) · "
        f"[DJ nights]({page_url('dj-techno-nights-nyc/')}).*",
    ]


def _scored(dated, days, now, borough=None, evenings_only=False):
    recurring = compute_recurring(dated)
    out = []
    for day, events in dated:
        if day not in days:
            continue
        for e in events:
            if e.get("_time") and e["_time"] < now:
                continue
            if borough and not _in_borough(e, borough):
                continue
            if evenings_only and (e.get("_time_unknown") or not e.get("_time") or e["_time"].hour < 17):
                continue
            s, _reasons = score_event(e, recurring)
            if s is not None and s > 0:
                out.append((s, e))
    out.sort(key=lambda x: -x[0])
    return out


def build_post(dated, per_section=6, now=None, mode="weekend", borough=None, per_day=5, news=None):
    now = now or datetime.now(EASTERN)
    where = CITY_LABELS.get(borough, "NYC") if borough else "NYC"
    lines = []
    if mode == "weekday":
        days = weekday_dates(now)
        mon, fri = days[0], days[-1]
        label = f"{mon.strftime('%b')} {mon.day}–{fri.strftime('%b') + ' ' if fri.month != mon.month else ''}{fri.day}"
        lines += [f"# {where} weeknight roundup: {label}", "",
                  f"Top picks for each weeknight ({'in ' + where if borough else 'across the five boroughs'}), evenings only:", ""]
    else:
        days = weekend_dates(now)
        fri, sun = min(days), max(days)
        label = f"{fri.strftime('%b')} {fri.day}–{sun.strftime('%b') + ' ' if sun.month != fri.month else ''}{sun.day}"
        lines += [f"# {where} weekend roundup: {label}", "",
                  f"Some of the most-listed concerts, parties, shows, run clubs, and free things happening "
                  f"{'in ' + where if borough else 'across the five boroughs'} this weekend:", ""]
    news = load_news(now.date()) if news is None else news
    if news:
        lines += ["**New on the site:**", ""] + news + [""]
    days_set = set(days)
    scored = _scored(dated, days_set, now, borough, evenings_only=(mode == "weekday"))
    used = set()
    if mode == "weekday":
        for day in days:
            picks = []
            for s, e in scored:
                key = (e.get("name") or "").strip().lower()
                if e["_time"].date() == day and key not in used:
                    picks.append(e)
                    used.add(key)
                if len(picks) >= per_day:
                    break
            if picks:
                lines.append(f"### {day.strftime('%A, %b')} {day.day}")
                lines += [_line(e).replace(f"{e['_time'].strftime('%a')} ", "", 1) for e in sorted(picks, key=lambda e: e["_time"])]
                lines.append("")
        return "\n".join(lines + _footer()) + "\n"
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
    return "\n".join(lines + _footer()) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--per-section", type=int, default=6)
    ap.add_argument("--weekday", action="store_true", help="Mon-Fri evenings, top picks per day")
    ap.add_argument("--per-day", type=int, default=5)
    ap.add_argument("--borough", choices=["manhattan", "brooklyn", "queens", "bronx", "staten_island"])
    ap.add_argument("--events", default=os.path.join(ROOT, "events.json"))
    ap.add_argument("--out", default=os.path.join(ROOT, "reddit_roundup.md"))
    args = ap.parse_args(argv)
    with open(args.events, encoding="utf-8") as f:
        payload = json.load(f)
    dated, _tba, _ongoing = group_by_date(payload.get("venues") if isinstance(payload, dict) else payload)
    post = build_post(dated, args.per_section, mode="weekday" if args.weekday else "weekend", borough=args.borough, per_day=args.per_day)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(post)
    print(f"wrote {args.out} ({len(post.splitlines())} lines) for {get_site_url()}")


if __name__ == "__main__":
    main()
