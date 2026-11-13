#!/usr/bin/env python3
"""Draft a weekly NYC post: things to do Monday–Sunday across the five boroughs.

Day-by-day headliners as "Title @ Venue @ Time", a one-line blurb on the notable ones, an "all
week" section for runs, plus free picks, kids & family, ways to meet people, prices and
neighborhoods. Ported from boston_events. scripts/generate_reddit_roundup.py is the weekend version.

Built from the site's merged, deduplicated events, so times and prices match the site.

    python3 scripts/generate_reddit_week.py              # next Monday–Sunday
    python3 scripts/generate_reddit_week.py 2026-11-09   # the week starting that Monday

Writes reddit/week-of-YYYY-MM-DD.md (title in the first line) and lists the headliners that
have no blurb yet; write a blurb for each by hand, then read the post through and check
the subreddit's self-promotion rules before posting. Picks are automatic.
"""
import copy
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from html import unescape

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from seo import page_url  # noqa: E402
from template import (  # noqa: E402
    CITY_LABELS, EASTERN, _event_city, _get_event_highlight, _is_event_free, _load_highlights,
    compute_recurring, group_by_date,
)
from scrapers import TECH_EVENT_RE, category_bucket  # noqa: E402
from venues_geo import resolve_event_geo  # noqa: E402

BOROUGHS = ("manhattan", "brooklyn", "queens", "bronx", "staten_island")
PER_DAY = 12
RUN_PICKS = 10
FREE_PICKS = 12
KIDS_PICKS = 10
SOCIAL_PICKS = 8
PER_VENUE_WEEK = 2
SKIP_BUCKETS = {"Classes & Services", "Deals & Specials", "Tech & Startups"}
STAGE = "Theater"

# The places that weekly list leans on: arenas, theaters, the big rock clubs, comedy clubs,
# museums. Their shows are what most readers are scanning for.
MAJOR_VENUES = (
    "madison square garden", "barclays center", "radio city", "beacon theatre", "kings theatre", "apollo theater",
    "carnegie hall", "lincoln center", "david geffen hall", "metropolitan opera", "brooklyn academy", "bam ",
    "terminal 5", "webster hall", "brooklyn steel", "brooklyn paramount", "irving plaza", "bowery ballroom",
    "music hall of williamsburg", "knockdown center", "elsewhere", "forest hills stadium", "the town hall", "sony hall",
    "le poisson rouge", "blue note", "village vanguard", "birdland", "city winery", "joe's pub", "bell house",
    "comedy cellar", "gotham comedy", "new york comedy club", "the stand", "caroline's",
    "yankee stadium", "citi field", "ubs arena", "prudential center", "the shed", "park avenue armory",
    "whitney museum", "guggenheim", "museum of the moving image", "film forum", "metrograph", "bryant park",
)
# Big-name signal for the list's top slots
MUSEUM_NIGHT_RE = re.compile(r"(?i)\b(?:after dark|late nites?|at night|third thursday|first friday|night at the)\b")

SOCIAL_SOURCES = ("luma", "partiful", "meetup", "heylo", "skip the small talk", "make friends")
# Keyword feeds find plenty of day trips and hikes well outside the city
OUT_OF_TOWN_RE = re.compile(r"(?i)\b(?:day trip|bus trip|weekend trip|getaway|upstate)\b")
SKIP_TITLE_RE = re.compile(
    r"(?i)\b(?:class|classes|course|workshop|intro to|bootcamp|training|certification|summit|"
    r"conference|strategy|leadership|founders?|investors?|webinar|yoga|early bird|field trips?|"
    r"pre-?show|q&a ticket|vip|parking|upgrade|recital|seminar|prep|students?|member morning|"
    r"members? only|camp|courtyard & historic|general admission|vision board(?:ing)?|"
    r"preliminary round|contest round|semifinal|figure drawing)\b")


def _week_start(arg):
    if arg:
        d = date.fromisoformat(arg)
        return d - timedelta(days=d.weekday())
    today = datetime.now(EASTERN).date()
    return today + timedelta(days=(7 - today.weekday()) or 7)  # next Monday


def _clean_title(name):
    t = re.sub(r"\s+", " ", unescape(name or "")).strip()
    t = re.sub(r"^(?:The )?Bowery Presents:?\s+", "", t)
    t = re.sub(r"\s+[-–]\s+New York\b.*$", "", t)
    return t if len(t) <= 80 else t[:77].rstrip() + "…"


def _link(text, url):
    text = text.replace("[", "(").replace("]", ")")
    if not url or not url.startswith("http"):
        return f"**{text}**"
    return f"**[{text}]({url.replace(')', '%29').replace(' ', '%20')})**"


def _price(e):
    if _is_event_free(e):
        return "Free"
    p = str(e.get("price") or "").strip()
    if not p or re.fullmatch(r"\$?0(?:\.00)?", p) or len(p) > 20 or not re.search(r"\d", p):
        return ""  # "Check link", "Tickets", "TBA"
    return re.sub(r"\.00\b", "", p)


def _time(e):
    t = e["_time"]
    return "" if (t.hour, t.minute) == (0, 0) else t.strftime("%-I:%M%p").replace(":00", "")


def _venue(e):
    v = re.sub(r"\s+", " ", e.get("venue") or e.get("_source_venue") or "").strip()
    v = re.sub(r"\s+presented by .*$", "", v, flags=re.I)
    v = re.sub(r"\s*\((?:New York|Brooklyn|Queens|Bronx|Manhattan|Staten Island)(?:, NY)?(?:[, ]+\d{5})?\)$", "", v, flags=re.I)
    v = re.sub(r",\s*(?:New York|Brooklyn|Queens),? NY.*$", "", v)
    return v


def _area(e):
    """Neighborhood from this venue's own pin, else the borough."""
    venue = _venue(e)
    g = resolve_event_geo(e)
    city = _event_city(e.get("venue"), e.get("_source_venue"), geo=g, event=e)
    area = (g or {}).get("neighborhood") or CITY_LABELS.get(city, "")
    return "" if not area or area in ("Citywide / Location TBA", "Outside NYC") or area.lower() in venue.lower() else area


def _line(e, day_prefix=False, when=None):
    """* **[Title](url)** @ Venue @ 7PM · $25 · Harvard Sq
         Blurb."""
    head = f"{e['_time'].strftime('%a')} · " if day_prefix else ""
    parts = [f"{head}{_link(_clean_title(e['name']), e.get('url'))} @ {_venue(e)}"]
    t = when if when is not None else _time(e)
    if t:
        parts[0] += f" @ {t}"
    extra = [x for x in (_price(e), _area(e)) if x]
    s = "* " + parts[0] + (" · " + " · ".join(extra) if extra else "")
    note = (e.get("_highlight") or {}).get("note")
    if note:
        s += f"  \n  {note}"
    return s


def _in_area(e):
    return _event_city(e.get("venue"), e.get("_source_venue"), geo=resolve_event_geo(e), event=e) in BOROUGHS


def _is_kids(e):
    """The site's own classification. Matching on words here picks up "Big Ass Kids" and "Baby
    Shoes Comedy Show"."""
    return e.get("category") == "family" and not re.search(r"(?i)\badults?\b", e.get("name") or "")


def _is_library(e):
    return "library" in f"{e.get('venue')} {e.get('_source_venue')}".lower()


def _is_social(e):
    src = (e.get("_source_venue") or "").lower()
    return any(k in src for k in SOCIAL_SOURCES)


def _is_major(e):
    blob = f"{e.get('venue')} {e.get('_source_venue')}".lower()
    return any(v in blob for v in MAJOR_VENUES)


def build(week_start):
    with open(os.path.join(ROOT, "events.json"), encoding="utf-8") as f:
        venues = json.load(f)["venues"]
    dated, _, _ = group_by_date(copy.deepcopy(venues))
    dated = [(d.date() if isinstance(d, datetime) else d, evs) for d, evs in dated]
    recurring = compute_recurring(dated)
    highlights = _load_highlights()
    week = [week_start + timedelta(days=i) for i in range(7)]
    by_day = {d: evs for d, evs in dated if d in week}
    total = sum(len(v) for v in by_day.values())

    def is_recurring(e):
        return ((e.get("name") or "").strip().lower(), e.get("_source_venue") or "",
                (e.get("venue") or "").strip().lower()) in recurring

    # Group each show's nights: 3+ nights is a run ("All week"), otherwise list it on its first night
    runs = defaultdict(list)
    for d in week:
        for e in by_day.get(d, []):
            key = re.sub(r"\s+[-–]\s+new york\b.*$", "", e["name"].lower())   # "Hadestown - New York"
            runs[(re.sub(r"\W+", " ", key).strip(), _venue(e).lower())].append(e)

    pool, run_pool = [], []
    for evs in runs.values():
        e = evs[0]
        nights = sorted({x["_time"].date() for x in evs})
        e["_nights"] = nights
        bucket = category_bucket(e.get("category"))
        if bucket in SKIP_BUCKETS:
            continue
        e["_bucket"] = bucket
        # Automatic picks' notes are scoring reasons ("listed on 4 calendars"), not blurbs
        hl = _get_event_highlight(e, highlights)
        e["_highlight"] = None if (hl or {}).get("auto") else hl
        t = e["_time"]
        if not e["_highlight"]:
            if SKIP_TITLE_RE.search(e["name"]) or TECH_EVENT_RE.search(e["name"]) or OUT_OF_TOWN_RE.search(e["name"]):
                continue
            if "rsvp for address" in (e.get("venue") or "").lower() or e.get("_venue_unknown"):
                continue
            if (t.hour, t.minute) != (0, 0) and t.hour < 7:
                continue
            m = re.search(r"\$(\d+)", str(e.get("price") or ""))
            if m and int(m.group(1)) > 100 and bucket not in ("Music & nightlife", STAGE):
                continue
        e["_kids"] = _is_kids(e)
        if not _in_area(e):
            continue
        if len(nights) >= 3 and bucket in (STAGE, "Arts & culture") and not is_recurring(e):
            run_pool.append(e)
        else:
            pool.append(e)

    def score(e):
        s = 0
        if e.get("_highlight"):
            s += 60
        if _is_major(e):
            s += 40
        if MUSEUM_NIGHT_RE.search(e["name"]):
            s += 25
        if not is_recurring(e):
            s += 20
        if _is_social(e):
            s -= 30          # meetups get their own section
        src = (e.get("_source_venue") or "").lower()
        if src not in ("ticketmaster nyc", "seatgeek nyc", "donyc citywide") and not src.startswith(("eventbrite", "allevents")):
            s += 5
        s += 2 * min(len(e.get("_alt_sources") or []), 3)   # listed by several sources: more notable
        if not _time(e):
            s -= 15
        return s

    pool.sort(key=lambda e: (-score(e), e["_time"]))
    run_pool.sort(key=lambda e: (-score(e), e["_time"]))
    used, venue_count = set(), Counter()

    def take(e):
        used.add(id(e))
        venue_count[_venue(e).lower()] += 1

    def ok_venue(e, cap=PER_VENUE_WEEK):
        return venue_count[_venue(e).lower()] < cap

    runs_pick = []
    for e in run_pool:
        if len(runs_pick) < RUN_PICKS and ok_venue(e):
            runs_pick.append(e); take(e)

    kids = sorted((e for e in pool if e["_kids"]), key=lambda e: (_is_library(e), -score(e), e["_time"]))
    kids_pick, n_lib = [], 0
    for e in kids:
        if len(kids_pick) < KIDS_PICKS and ok_venue(e) and not (_is_library(e) and n_lib >= 3):
            kids_pick.append(e); take(e); n_lib += _is_library(e)

    social_pick = []
    for e in pool:
        if len(social_pick) >= SOCIAL_PICKS:
            break
        if id(e) not in used and _is_social(e) and not e["_kids"] and ok_venue(e, 1):
            social_pick.append(e); take(e)

    days = {}
    for d in week:
        picks, per_bucket = [], Counter()
        for e in pool:
            if len(picks) >= PER_DAY:
                break
            if e["_time"].date() != d or id(e) in used or _is_library(e) or e["_kids"] or _is_social(e):
                continue
            cap = 5 if e["_bucket"] == "Music & nightlife" else 3
            if per_bucket[e["_bucket"]] >= cap or not ok_venue(e):
                continue
            picks.append(e); take(e); per_bucket[e["_bucket"]] += 1
        days[d] = sorted(picks, key=lambda e: e["_time"])

    free_pick, free_kind = [], Counter()
    for e in pool:
        if len(free_pick) >= FREE_PICKS:
            break
        if id(e) in used or not _is_event_free(e) or _is_library(e) or e["_kids"] or is_recurring(e):
            continue
        kind = "trivia" if re.search(r"(?i)trivia|bingo", e["name"]) else e["_bucket"]
        if ok_venue(e) and free_kind[kind] < (1 if kind == "trivia" else 4):
            free_pick.append(e); take(e); free_kind[kind] += 1

    end = week[-1]
    span = f"{week_start.strftime('%b %-d')}–{end.strftime('%-d') if end.month == week_start.month else end.strftime('%b %-d')}"
    title = f"Things to do in NYC this week ({span}): concerts, comedy, free stuff, kids & more"

    def nights_label(e):
        ds = e["_nights"]
        return f"{ds[0].strftime('%a')}–{ds[-1].strftime('%a')}" if len(ds) > 1 else ds[0].strftime("%a")

    out = [
        f"Hi New York! Here's what's on **Monday {week_start.strftime('%b %-d')} through Sunday "
        f"{end.strftime('%b %-d')}** across the five boroughs: the big shows, plus free stuff, kids' "
        f"events and ways to meet people. Please add anything I missed below!",
        "",
    ]
    for d in week:
        if days[d]:
            out += [f"**{d.strftime('%A').upper()}, {d.strftime('%b %-d').upper()}**", ""]
            out += [_line(e) for e in days[d]]
            out.append("")
    if runs_pick:
        out += ["**🎭 RUNNING ALL WEEK**", ""]
        out += [_line(e, when=nights_label(e)) for e in sorted(runs_pick, key=lambda e: e["_time"])]
        out.append("")
    if free_pick:
        out += ["**🆓 FREE THIS WEEK**", ""]
        out += [_line(e, day_prefix=True) for e in sorted(free_pick, key=lambda e: e["_time"])]
        out.append("")
    if kids_pick:
        out += ["**👶 KIDS & FAMILIES**", ""]
        out += [_line(e, day_prefix=True) for e in sorted(kids_pick, key=lambda e: e["_time"])]
        out += ["", f"Story times, playgroups & more: [kids & family calendar]({page_url('kids-family-events-nyc/')})", ""]
    if social_pick:
        out += ["**🤝 MEET PEOPLE**", ""]
        out += [_line(e, day_prefix=True) for e in sorted(social_pick, key=lambda e: e["_time"])]
        out.append("")
    shown = len(used)
    out += [
        "---",
        "",
        f"That's {shown} of the {total:,} events on this week. Everything else is searchable by "
        f"borough, neighborhood, free or kids at **[NYC Events]({page_url('')})** "
        f"(independent and ad-free; it pulls from 1,000 venue and community calendars and is updated twice a day).",
    ]
    body = "\n".join(out) + "\n"
    needs_blurb = [e for d in week for e in days[d] if _is_major(e) and not e.get("_highlight")]
    return title, body, needs_blurb


def main():
    week_start = _week_start(sys.argv[1] if len(sys.argv) > 1 else None)
    title, body, needs_blurb = build(week_start)
    out_dir = os.path.join(ROOT, "reddit")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"week-of-{week_start.isoformat()}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"<!-- Title: {title} -->\n\n{body}")
    print(f"Title: {title}")
    print(f"Body:  {path} ({len(body):,} characters; Reddit allows 40,000)")
    if needs_blurb:
        print(f"\n{len(needs_blurb)} headliners have no blurb yet (add to highlights.json and rerun):")
        for e in needs_blurb:
            print(f"  {e['_time'].strftime('%a %m-%d')}  {_clean_title(e['name'])} @ {_venue(e)}")


if __name__ == "__main__":
    main()
