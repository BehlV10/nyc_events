#!/usr/bin/env python3
"""Weekly "best events" carousel (two 1080x1350 PNG slides for Instagram / LinkedIn / Threads).

Ported from Boston events:
  slide 1  Monday–Friday picks           instagram/this_week_slide1.png
  slide 2  Saturday & Sunday + markets   instagram/this_week_slide2.png

Differences from the Boston version: events come from group_by_date() (deduplicated across
sources), are ranked with the same scoring as scripts/curate_highlights.py plus a boost for
editor's picks, the headline count is the real number of listings shown (no rounding up), and
empty sections are left out rather than filled with placeholder events. Colors and the eyebrow
line follow the season from themes.py.

Rendering uses headless Chrome (CHROME_BIN env var, else the macOS app path, else
google-chrome on PATH). Without Chrome it still writes the .html slides.

Usage:
    python scripts/generate_this_week_flyer.py                    # this week (next week from Thursday on)
    python scripts/generate_this_week_flyer.py --date 2026-11-09  # the week containing that date
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timedelta
from html import escape, unescape

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from curate_highlights import score_event  # noqa: E402
from scrapers import EASTERN  # noqa: E402
from seo import get_site_url  # noqa: E402
from template import (  # noqa: E402
    CITY_LABELS, _event_city, _get_event_highlight, _load_highlights, compute_recurring, group_by_date,
)
from themes import get_theme  # noqa: E402
from venues_geo import resolve_event_geo  # noqa: E402

OUTPUT_DIR = os.path.join(ROOT, "instagram")
DAY_QUOTAS = {0: 6, 1: 6, 2: 7, 3: 9, 4: 11, 5: 17, 6: 10}
MARKET_WORDS = ("market", "bazaar", "flea", "festival", "fair", "parade", "smorgasburg", "open studios", "expo")
DAY_NAMES = ["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY"]


def chrome_bin():
    for cand in (os.environ.get("CHROME_BIN"), "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                 shutil.which("google-chrome"), shutil.which("chromium")):
        if cand and os.path.exists(cand):
            return cand
    return None


def clean_title(title, limit=40):
    t = unescape((title or "").strip())
    t = re.sub(r"\s*[\(\[](?:18\+|21\+|all ages|sold out|free w/ ?rsvp|doors[^\)\]]*)[\)\]]", "", t, flags=re.I)
    t = re.sub(r"\s*[-|]\s*(?:18\+|21\+|all ages|sold out|nyc|new york).*$", "", t, flags=re.I)
    t = re.sub(r"\s+", " ", t).strip(" -–:|")
    if len(t) > limit:
        t = t[: limit - 1].rsplit(" ", 1)[0].rstrip(" -–:,") + "…"
    return t


def _ordinal(n):
    return "th" if 11 <= n % 100 <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")


def week_bounds(target=None):
    today = datetime.now(EASTERN).date()
    if target is None:
        target = today if today.weekday() <= 2 else today + timedelta(days=7 - today.weekday())
    monday = target - timedelta(days=target.weekday())
    return monday, monday + timedelta(days=6)


def select_week(dated, monday, sunday):
    highlights = _load_highlights()
    recurring = compute_recurring(dated)
    by_day = {i: [] for i in range(7)}
    markets = []
    for day, events in dated:
        if not (monday <= day <= sunday):
            continue
        scored = []
        for e in events:
            s, _ = score_event(e, recurring)
            if s is None or s <= 0:
                continue
            if _get_event_highlight(e, highlights):
                s += 10
            scored.append((s, e))
            if day.weekday() >= 5 and any(w in (e.get("name") or "").lower() for w in MARKET_WORDS):
                markets.append((s, e))
        scored.sort(key=lambda x: -x[0])
        seen_venues, seen_titles, picked = set(), set(), []
        for s, e in scored:
            venue = (e.get("venue") or e.get("_source_venue") or "").strip()
            title = clean_title(e.get("name"))
            v_key, t_key = venue.lower(), re.sub(r"[^a-z0-9]", "", title.lower())[:18]
            if not venue or v_key in seen_venues or t_key in seen_titles:
                continue
            seen_venues.add(v_key)
            seen_titles.add(t_key)
            geo = resolve_event_geo(e)
            city = _event_city(venue, e.get("_source_venue"), geo=geo, event=e)
            where = (geo or {}).get("venue") or venue
            where = re.split(r"\s*\(", where)[0]
            if city in CITY_LABELS and city not in ("other", "citywide"):
                where = f"{where} • {CITY_LABELS[city]}"
            t = e["_time"]
            picked.append({"dt": t, "time": t.strftime("%-I:%M %p").replace(":00", ""), "title": title, "venue": where})
            if len(picked) >= DAY_QUOTAS[day.weekday()]:
                break
        by_day[day.weekday()] = sorted(picked, key=lambda x: x["dt"])
    markets.sort(key=lambda x: -x[0])
    seen, market_items = set(), []
    for _s, e in markets:
        key = re.sub(r"[^a-z0-9]", "", (e.get("name") or "").lower())[:14]
        if key in seen:
            continue
        seen.add(key)
        t = e["_time"]
        market_items.append(f"{clean_title(e.get('name'), 44).upper()} • {t.strftime('%a').upper()} {t.strftime('%-I %p')}")
        if len(market_items) >= 3:
            break
    return by_day, market_items


def slide_data(monday, sunday, by_day, market_items, theme, site_label):
    def day_block(i, bg, fg):
        d = monday + timedelta(days=i)
        return {"day": f"{DAY_NAMES[i]} • {d.strftime('%b').upper()} {d.day}", "bg": bg, "fg": fg, "events": by_day.get(i, [])}

    p, a, soft = theme["primary"], theme["accent"], theme["soft"]
    weekday_count = sum(len(by_day[i]) for i in range(5))
    weekend_count = len(by_day[5]) + len(by_day[6])
    sat = monday + timedelta(days=5)
    span = f"{monday.strftime('%B').upper()} {monday.day}{_ordinal(monday.day)}–{sunday.day}{_ordinal(sunday.day)}, {sunday.year}"
    s1 = {
        "eyebrow": theme["eyebrow"], "title_top": f"{weekday_count} PICKS THIS WEEK" if weekday_count else "THIS WEEK",
        "title_box": "NYC THIS WEEK", "subtitle": f"{span} • 1/2",
        "left": [day_block(0, p, "#fff"), day_block(1, a, "#fff"), day_block(2, p, "#fff")],
        "right": [day_block(3, soft, "#000"), day_block(4, p, "#fff")],
        "badge": "SWIPE FOR THE WEEKEND ➔", "markets": [], "soft": soft, "site": site_label,
    }
    s2 = {
        "eyebrow": theme["eyebrow"], "title_top": f"{weekend_count} WEEKEND PICKS" if weekend_count else "NYC THIS WEEK",
        "title_box": "THE WEEKEND",
        "subtitle": f"{sat.strftime('%B').upper()} {sat.day}{_ordinal(sat.day)}–{sunday.day}{_ordinal(sunday.day)}, {sunday.year} • 2/2",
        "left": [day_block(5, p, "#fff")], "right": [day_block(6, "#111827", "#fff")],
        "badge": site_label, "markets": market_items, "soft": soft, "site": site_label,
    }
    for s in (s1, s2):
        s["left"] = [b for b in s["left"] if b["events"]]
        s["right"] = [b for b in s["right"] if b["events"]]
    return s1, s2


def slide_html(d):
    def col(blocks):
        out = []
        for b in blocks:
            items = "".join(
                f'<div class="event-item"><div class="event-main"><span class="event-time">{escape(ev["time"])}</span>'
                f'<span class="event-dash">—</span><span class="event-title">{escape(ev["title"])}</span></div>'
                f'<div class="event-venue">{escape(ev["venue"])}</div></div>'
                for ev in b["events"]
            )
            out.append(f'<div class="day-group"><div class="day-pill" style="background:{b["bg"]};color:{b["fg"]}">'
                       f'{escape(b["day"])}</div><div class="events-list">{items}</div></div>')
        return "".join(out)

    markets = ""
    if d["markets"]:
        items = "".join(f'<div class="hl-item">{escape(m)}</div>' for m in d["markets"])
        markets = (f'<div class="highlights-box"><div class="hl-header"><span>MARKETS, FAIRS &amp; FESTIVALS</span><span>✦</span></div>'
                   f'<div class="hl-list">{items}</div><div class="hl-note">Check the organizer page for weather updates</div></div>')
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ width: 1080px; height: 1350px; background: #fff; color: #000; overflow: hidden; display: flex; flex-direction: column;
         font-family: -apple-system, "Helvetica Neue", Arial, sans-serif; -webkit-font-smoothing: antialiased; }}
  .header {{ padding: 22px 38px 8px; display: flex; flex-direction: column; align-items: center; text-align: center; }}
  .eyebrow {{ font-size: 13px; font-weight: 800; letter-spacing: 2px; color: #6b7280; margin-bottom: 8px; }}
  .title-top {{ font-size: 32px; font-weight: 900; letter-spacing: 2px; line-height: 1.1; margin-bottom: 6px; }}
  .title-box {{ background: #000; color: #fff; font-size: 42px; font-weight: 900; letter-spacing: 1.5px; padding: 8px 32px;
                border-radius: 4px; margin-bottom: 8px; }}
  .subtitle {{ font-size: 16px; font-weight: 800; letter-spacing: 2.5px; color: #111827; }}
  .grid {{ flex: 1; display: grid; grid-template-columns: minmax(0,1fr) minmax(0,1fr); gap: 28px; padding: 8px 38px 12px; overflow: hidden; }}
  .col {{ display: flex; flex-direction: column; gap: 12px; min-width: 0; }}
  .day-group {{ display: flex; flex-direction: column; gap: 4px; }}
  .day-pill {{ align-self: flex-start; font-size: 14px; font-weight: 900; letter-spacing: 1.2px; padding: 4px 14px; border-radius: 14px; margin-bottom: 4px; }}
  .event-item {{ padding: 3.5px 0; border-bottom: 1px solid {d["soft"]}; display: flex; flex-direction: column; gap: 1.5px; }}
  .event-main {{ font-size: 14px; line-height: 1.22; display: flex; align-items: baseline; overflow: hidden; }}
  .event-time {{ font-weight: 800; white-space: nowrap; margin-right: 4px; }}
  .event-dash {{ color: #6b7280; margin-right: 5px; font-weight: 600; }}
  .event-title {{ font-weight: 700; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
  .event-venue {{ font-size: 11.5px; font-weight: 600; color: #64748b; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
  .highlights-box {{ background: #000; border-radius: 12px; padding: 14px 18px 12px; color: #fff; display: flex; flex-direction: column; gap: 8px; margin-top: 6px; }}
  .hl-header {{ display: flex; justify-content: space-between; font-size: 15px; font-weight: 900; letter-spacing: 1.5px; color: {d["soft"]};
               border-bottom: 1px solid #374151; padding-bottom: 5px; }}
  .hl-list {{ display: flex; flex-direction: column; gap: 5px; }}
  .hl-item {{ font-size: 12.5px; font-weight: 800; letter-spacing: 0.5px; line-height: 1.25; }}
  .hl-note {{ font-size: 10.5px; font-weight: 600; color: #9ca3af; padding-top: 5px; border-top: 1px dashed #374151; }}
  .footer {{ padding: 10px 38px 18px; display: flex; align-items: center; justify-content: space-between; border-top: 2px solid #f1f5f9; }}
  .footer-brand {{ font-size: 15px; font-weight: 900; letter-spacing: 1px; }}
  .footer-center {{ font-size: 11px; font-weight: 600; color: #94a3b8; letter-spacing: 0.8px; }}
  .footer-badge {{ background: #000; color: #fff; font-size: 13px; font-weight: 800; padding: 7px 18px; border-radius: 20px; }}
</style></head><body>
  <div class="header">
    <div class="eyebrow">{escape(d["eyebrow"])}</div>
    <div class="title-top">{escape(d["title_top"])}</div>
    <div class="title-box">{escape(d["title_box"])}</div>
    <div class="subtitle">{escape(d["subtitle"])}</div>
  </div>
  <div class="grid"><div class="col">{col(d["left"])}</div><div class="col">{col(d["right"])}{markets}</div></div>
  <div class="footer">
    <div class="footer-brand">NYC EVENTS</div>
    <div class="footer-center">TIMES ET • CHECK VENUE PAGES BEFORE YOU GO</div>
    <div class="footer-badge">{escape(d["badge"])}</div>
  </div>
</body></html>
"""


def render_png(html_path, png_path):
    chrome = chrome_bin()
    if not chrome:
        print(f"Chrome not found; wrote {html_path} only (set CHROME_BIN to render PNGs)")
        return False
    subprocess.run([chrome, "--headless=new", "--disable-gpu", "--no-sandbox", "--hide-scrollbars",
                    "--window-size=1080,1350", f"--screenshot={png_path}", f"file://{os.path.abspath(html_path)}"],
                   check=True, capture_output=True)
    print(f"rendered {png_path}")
    return True


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--date", help="any date in the target week (YYYY-MM-DD)")
    ap.add_argument("--events", default=os.path.join(ROOT, "events.json"))
    ap.add_argument("--out-dir", default=OUTPUT_DIR)
    args = ap.parse_args(argv)

    target = datetime.strptime(args.date, "%Y-%m-%d").date() if args.date else None
    monday, sunday = week_bounds(target)
    with open(args.events, encoding="utf-8") as f:
        payload = json.load(f)
    dated, _tba, _ongoing = group_by_date(payload.get("venues") if isinstance(payload, dict) else payload)
    by_day, markets = select_week(dated, monday, sunday)
    site_label = get_site_url().split("://", 1)[-1]
    s1, s2 = slide_data(monday, sunday, by_day, markets, get_theme(monday), site_label)
    os.makedirs(args.out_dir, exist_ok=True)
    print(f"week {monday} – {sunday}: " + ", ".join(f"{DAY_NAMES[i][:3].title()} {len(by_day[i])}" for i in range(7)))
    for n, data in ((1, s1), (2, s2)):
        html_path = os.path.join(args.out_dir, f"this_week_slide{n}.html")
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(slide_html(data))
        render_png(html_path, os.path.join(args.out_dir, f"this_week_slide{n}.png"))


if __name__ == "__main__":
    main()
