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
    out += ["### Venues we can't read", "", "| Venue | Why | Next step |", "|---|---|---|"]
    out += [f"| [{k['venue']}]({k['url']}) | {k['reason']} | {k['next_step']} |" for k in KNOWN_UNSCRAPABLE]
    return "\n".join(out) + "\n"


def write_report(venues, refused=None, path=os.path.join(".cache", "source_status.json")):
    rows = source_status(venues, refused)
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
