#!/usr/bin/env python3
"""Check how many events from an outside list (a newsletter, The Skint, a friend's
recommendations...) the calendar already has, and which venues to add next.

Generalized from Boston's one-off audit_newsletter.py (which read /tmp/user_events.txt and
compared against hard-coded git snapshots). Input is a plain text file:

    FRIDAY, NOVEMBER 6                          <- day headings set the date for lines below
    [Boy Harsher @ Knockdown Center](https://...)   <- markdown links, or
    Comedy Cellar Showcase @ Comedy Cellar @ 8pm    <- "title @ venue @ time" lines
    ALL WEEKEND / ONGOING                       <- clears the date (match any day)

Each line is matched against the deduplicated calendar on that date (±1 day) by title tokens,
title containment, and venue. Prints found / missing, plus the venues that show up most
among misses.

Usage:
    python scripts/audit_coverage.py newsletter.txt
    python scripts/audit_coverage.py newsletter.txt --json report.json
"""

import argparse
import json
import os
import re
import sys
from collections import Counter
from datetime import date, datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from scrapers import EASTERN  # noqa: E402
from template import group_by_date  # noqa: E402

MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august",
     "september", "october", "november", "december"], 1)}
STOP = {"the", "a", "an", "at", "in", "on", "and", "with", "presents", "live", "show", "tour", "night",
        "party", "edition", "nyc", "new", "york", "feat", "featuring", "free", "w", "of", "for", "to"}
DAY_HEADING_RE = re.compile(r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday|all weekend|ongoing)\b", re.I)


def _norm(s):
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", (s or "").lower())).strip()


def _tokens(s):
    return {w for w in _norm(s).split() if len(w) > 2 and w not in STOP}


def parse_heading_date(line, year):
    m = re.search(r"\b(" + "|".join(MONTHS) + r")\s+(\d{1,2})\b", line, re.I)
    if not m:
        return None
    return date(year, MONTHS[m.group(1).lower()], int(m.group(2)))


def parse_items(text, year):
    items, current = [], None
    for raw in text.splitlines():
        line = raw.strip().lstrip("-*• ").strip()
        if not line:
            continue
        if DAY_HEADING_RE.search(line) and not line.startswith("[") and "@" not in line:
            current = parse_heading_date(line, year)
            continue
        m = re.match(r"\[(.*?)\]\((.*?)\)(.*)", line)
        label, url = (m.group(1), m.group(2)) if m else (line, "")
        parts = [p.strip() for p in label.split("@")]
        items.append({"title": parts[0], "venue": parts[1] if len(parts) > 1 else "",
                      "date": current.isoformat() if current else None, "url": url, "raw": raw.strip()})
    return items


def match_item(item, by_date, all_events):
    pool = all_events
    if item["date"]:
        d = date.fromisoformat(item["date"])
        pool = [e for k in (d - timedelta(days=1), d, d + timedelta(days=1)) for e in by_date.get(k, [])]
    it_tokens, it_title, it_venue = _tokens(item["title"]), _norm(item["title"]), _norm(item["venue"])
    best, best_score = None, 0.0
    for e in pool:
        title = _norm(e.get("name"))
        overlap = len(it_tokens & _tokens(e.get("name"))) / max(len(it_tokens), 1)
        contained = bool(it_title and len(it_title) > 5 and (it_title in title or (len(title) > 6 and title in it_title)))
        venue = _norm(e.get("venue"))
        venue_ok = bool(it_venue and venue and (it_venue in venue or venue in it_venue))
        score = max(overlap, 0.9 if contained else 0) + (0.2 if venue_ok else 0)
        if score > best_score:
            best, best_score = e, score
    return (best, best_score) if best_score >= 0.6 else (None, best_score)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("input", help="text file of event lines")
    ap.add_argument("--events", default=os.path.join(ROOT, "events.json"))
    ap.add_argument("--year", type=int, default=datetime.now(EASTERN).year)
    ap.add_argument("--json", help="write a machine-readable report here")
    args = ap.parse_args(argv)

    with open(args.input, encoding="utf-8") as f:
        items = parse_items(f.read(), args.year)
    with open(args.events, encoding="utf-8") as f:
        payload = json.load(f)
    dated, tba, _ongoing = group_by_date(payload.get("venues") if isinstance(payload, dict) else payload)
    by_date = {d: es for d, es in dated}
    all_events = [e for _, es in dated for e in es] + list(tba)

    found, missing = [], []
    for it in items:
        ev, score = match_item(it, by_date, all_events)
        if ev:
            found.append({**it, "match": ev.get("name"), "match_venue": ev.get("venue"),
                          "source": ev.get("_source_venue"), "score": round(score, 2)})
        else:
            missing.append({**it, "best_score": round(score, 2)})

    total = len(items) or 1
    print(f"{len(found)}/{len(items)} found ({100 * len(found) // total}%), {len(missing)} missing\n")
    for m in missing:
        print(f"  MISSING  {m['date'] or 'any day':10}  {m['title'][:60]}" + (f"  @ {m['venue']}" if m['venue'] else ""))
    gaps = Counter(m["venue"] for m in missing if m["venue"])
    if gaps:
        print("\nVenues most often missing (candidates for new sources):")
        for venue, n in gaps.most_common(15):
            print(f"  {n:3}  {venue}")
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump({"found": found, "missing": missing}, f, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    main()
