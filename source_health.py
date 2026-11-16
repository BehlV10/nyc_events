"""Which sources are working, written after every crawl so a broken or quiet venue gets noticed.

The report lists sources that errored, sites that refused us this run, and sources with nothing
in the next two weeks (with each one's next event, so a seasonal venue is easy to tell from a
broken one), plus the sites we know about but can't read. In GitHub Actions it goes on the run's
summary page; locally it's printed and saved to .cache/source_status.json (not published).
"""
import json
import os
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

WINDOW_DAYS = 14

# Sites with real events that we can't read, and why. Kept by hand; re-check now and then.
KNOWN_UNSCRAPABLE = [
    {"venue": "The Met", "url": "https://www.metmuseum.org/events", "reason": "403/429 to scripts",
     "next_step": "Ask for a calendar feed"},
    {"venue": "American Museum of Natural History", "url": "https://www.amnh.org/calendar", "reason": "403 to scripts",
     "next_step": "Ask for a calendar feed"},
    {"venue": "MoMA", "url": "https://www.moma.org/calendar/", "reason": "403 to scripts",
     "next_step": "Ask for a calendar feed"},
    {"venue": "Brooklyn Museum", "url": "https://www.brooklynmuseum.org/calendar", "reason": "429 to scripts",
     "next_step": "Ask for a calendar feed"},
    {"venue": "Hudson River Park", "url": "https://hudsonriverpark.org/events/",
     "reason": "403 to scripts", "next_step": "Ask for a calendar feed"},
    {"venue": "New-York Historical", "url": "https://www.nyhistory.org/programs", "reason": "403 to scripts",
     "next_step": "Ask for a calendar feed"},
    {"venue": "The Morgan Library", "url": "https://www.themorgan.org/exhibitions/current", "reason": "403 to scripts",
     "next_step": "Ask for a calendar feed"},
    {"venue": "The Frick Collection", "url": "https://www.frick.org/exhibitions", "reason": "418 to scripts",
     "next_step": "Ask for a calendar feed"},
    {"venue": "El Museo del Barrio", "url": "https://www.elmuseo.org/exhibitions/", "reason": "403 to scripts",
     "next_step": "Ask for a calendar feed"},
    {"venue": "New York Public Library", "url": "https://www.nypl.org/events/calendar", "reason": "Incapsula bot check",
     "next_step": "Ask NYPL for a calendar feed"},
    {"venue": "92NY", "url": "https://www.92ny.org/", "reason": "Incapsula bot check",
     "next_step": "Ask for a calendar feed"},
    {"venue": "Queens Public Library", "url": "https://www.queenslibrary.org/calendar", "reason": "Captcha",
     "next_step": "Ask for a calendar feed"},
    {"venue": "Brooklyn Public Library", "url": "https://www.bklynlibrary.org/calendar", "reason": "API access denied, calendar is JS-only",
     "next_step": "Ask for a calendar feed"},
    {"venue": "NYC.gov events", "url": "https://www.nyc.gov/events/", "reason": "Calendar API needs a key",
     "next_step": "Request a key from NYC's developer portal"},
    {"venue": "Reddit r/nycevents", "url": "https://www.reddit.com/r/nycevents/", "reason": "403 without API credentials",
     "next_step": "Needs a Reddit OAuth app"},
]


def _when(e):
    try:
        t = datetime.fromisoformat(str(e.get("date")).replace("Z", "+00:00"))
        return t if t.tzinfo else t.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def source_status(venues, refused=None, now=None, days=WINDOW_DAYS):
    """One row per source: events overall, in the next `days`, the next event, and a status."""
    now = now or datetime.now(timezone.utc)
    soon = now + timedelta(days=days)
    refused = refused or {}
    rows = []
    for v in venues:
        times = sorted(t for t in (_when(e) for e in v.get("events") or []) if t and t >= now - timedelta(hours=6))
        near = sum(1 for t in times if t <= soon)
        host = urlparse(v.get("url") or "").netloc.lower()
        refusal = next((r for h, r in refused.items() if host == h or host.endswith("." + h) or h.endswith("." + host)), None)
        if v.get("error"):
            status = "error"
        elif refusal:
            status = "refused"
        elif near == 0:
            status = "empty"
        else:
            status = "ok"
        rows.append({
            "source": v.get("venue"), "url": v.get("url"), "status": status,
            "events": len(v.get("events") or []), "next_two_weeks": near,
            "next_event": times[0].date().isoformat() if times else None,
            "error": (v.get("error") or refusal or "")[:200] or None,
            "from_cache": bool(v.get("cached")), "kept_last_good": bool(v.get("fallback")),
        })
    order = {"error": 0, "refused": 1, "empty": 2, "ok": 3}
    rows.sort(key=lambda r: (order[r["status"]], (r["source"] or "").lower()))
    return rows


HISTORY_PATH = os.path.join(".cache", "venues", "_source_history.json")  # in the CI-cached folder
ALERTS_PATH = os.path.join(".cache", "source_alerts.md")
HISTORY_RUNS = 20        # crawls remembered per source (ten days at two a day)
SHRINK_MIN_RUNS = 5      # history needed before a drop means anything
SHRINK_MIN_MEDIAN = 8    # small calendars swing too much to judge
SHRINK_RATIO = 0.5       # at or under half the usual count


def track_history(rows, path=HISTORY_PATH):
    """Compare each source's event count with its own recent crawls and mark the ones that
    shrank to half or less (row["shrunk_from"] = usual count). A scraper that half-breaks keeps
    returning *something*, so it never shows up as an error or as empty: the Town Hall parser
    once lost two-thirds of its calendar, and Birdland returned one page of eighteen. Returns
    the rows that shrank since the previous crawl (already-flagged ones are not repeated)."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            history = json.load(f)
    except (OSError, ValueError):
        history = {}
    fresh = []
    for r in rows:
        name = r.get("source")
        if not name or r["status"] in ("error", "refused") or r.get("from_cache") or r.get("kept_last_good"):
            continue  # those crawls say nothing about the source's real size
        h = history.setdefault(name, {"counts": [], "flagged": False})
        past = sorted(h["counts"])
        usual = past[len(past) // 2] if past else 0
        if len(past) >= SHRINK_MIN_RUNS and usual >= SHRINK_MIN_MEDIAN and r["events"] <= SHRINK_RATIO * usual:
            r["shrunk_from"] = usual
            if not h["flagged"]:
                fresh.append(r)
            h["flagged"] = True
        else:
            h["flagged"] = False
        h["counts"] = (h["counts"] + [r["events"]])[-HISTORY_RUNS:]
    seen = {r.get("source") for r in rows}
    history = {k: v for k, v in history.items() if k in seen}
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(history, f)
    except OSError:
        pass
    return fresh


def _markdown(rows):
    count = lambda s: sum(1 for r in rows if r["status"] == s)
    out = ["## Source health", "",
           f"{len(rows)} sources: **{count('ok')} OK**, {count('error')} errored, {count('refused')} refused us, "
           f"{count('empty')} with nothing in the next {WINDOW_DAYS} days.", ""]
    problems = [r for r in rows if r["status"] != "ok"]
    if problems:
        out += ["| Source | Status | Events | Next event | Note |", "|---|---|---|---|---|"]
        for r in problems:
            note = r["error"] or ("kept last good data" if r["kept_last_good"] else "")
            out.append(f"| [{r['source']}]({r['url']}) | {r['status']} | {r['events']} | {r['next_event'] or '—'} | {note} |")
        out.append("")
    shrunk = [r for r in rows if r.get("shrunk_from")]
    if shrunk:
        out += ["### Sources that shrank", "", "Returning half or less of their usual number of events. Check the scraper.", "",
                "| Source | Events now | Usually |", "|---|---|---|"]
        out += [f"| [{r['source']}]({r['url']}) | {r['events']} | {r['shrunk_from']} |" for r in shrunk]
        out.append("")
    out += ["### Venues we can't read", "", "| Venue | Why | Next step |", "|---|---|---|"]
    out += [f"| [{k['venue']}]({k['url']}) | {k['reason']} | {k['next_step']} |" for k in KNOWN_UNSCRAPABLE]
    return "\n".join(out) + "\n"


def write_report(venues, refused=None, path=os.path.join(".cache", "source_status.json"), history_path=HISTORY_PATH,
                 alerts_path=ALERTS_PATH):
    rows = source_status(venues, refused)
    fresh = track_history(rows, history_path)
    # Newly shrunk sources go in a file the scrape workflow turns into a GitHub issue.
    try:
        if fresh:
            os.makedirs(os.path.dirname(alerts_path) or ".", exist_ok=True)
            with open(alerts_path, "w", encoding="utf-8") as f:
                f.write("These sources returned half or less of their usual number of events in the last crawl. "
                        "The scraper may be partly broken.\n\n| Source | Events now | Usually |\n|---|---|---|\n"
                        + "".join(f"| [{r['source']}]({r['url']}) | {r['events']} | {r['shrunk_from']} |\n" for r in fresh))
        elif os.path.exists(alerts_path):
            os.remove(alerts_path)
    except OSError:
        pass
    for r in fresh:
        print(f"source shrank  {r['source']}: {r['events']} events, usually {r['shrunk_from']}")
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"generated_at": datetime.now(timezone.utc).isoformat(), "window_days": WINDOW_DAYS,
                   "sources": rows, "known_unscrapable": KNOWN_UNSCRAPABLE}, f, indent=1)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write(_markdown(rows))
    for r in rows:
        if r["status"] != "ok":
            print(f"source {r['status']:7s} {r['source']}: {r['events']} events, next {r['next_event'] or 'none'}"
                  + (f" ({r['error']})" if r["error"] else ""))
    return rows
