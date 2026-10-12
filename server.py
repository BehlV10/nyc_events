#!/usr/bin/env python3
"""NYC Events — scrape venue sites across all 5 boroughs and serve at localhost:3001."""

import json
import os
import sys
import threading
import time
from datetime import datetime, timezone

from flask import Flask, jsonify, request, send_from_directory


def _load_dotenv():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                k, v = k.strip(), v.strip().strip('"').strip("'")
                if k and k not in os.environ:
                    os.environ[k] = v
    except FileNotFoundError:
        pass


_load_dotenv()

from scrapers import (  # noqa: E402
    VENUES,
    get_all_events,
    fetch_nyc_weather,
    fetch_luckyseat_nyc,
)
from template import render_page  # noqa: E402

PORT = int(os.environ.get("PORT", 3001))

app = Flask(__name__)


@app.get("/banner.jpg")
@app.get("/static/banner.jpg")
def banner_img():
    banner_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "banner.jpg")
    if os.path.exists(banner_path):
        return send_from_directory(os.path.dirname(os.path.abspath(__file__)), "banner.jpg")
    return "", 404


@app.get("/")
def index():
    return render_page(get_all_events(force="refresh" in request.args))


@app.get("/api/events")
def api_events():
    return jsonify(get_all_events(force="refresh" in request.args))


def export_json(dest="events.json"):
    data = get_all_events(force=True)
    with open(dest, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    total = sum(len(v.get("events", [])) for v in data.get("venues", []))
    print(f"wrote {dest}: {total} events across {len(data.get('venues', []))} venues")


def export_html(dest="index.html", source_json="events.json"):
    data = None
    if os.path.exists(source_json):
        try:
            with open(source_json, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            print(f"Warning: could not read {source_json} ({e}), re-scraping...")
            data = None
    if not data:
        data = get_all_events(force=True)
    if "weather" not in data or not data["weather"]:
        data["weather"] = fetch_nyc_weather()
    if "luckyseat" not in data:
        data["luckyseat"] = fetch_luckyseat_nyc()
    html = render_page(data)
    with open(dest, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"wrote {dest}: {len(html.encode('utf-8')):,} bytes")


def run_diagnostics(filter_name=None):
    targets = VENUES
    if filter_name:
        targets = [v for v in VENUES if filter_name.lower() in v["name"].lower()]
        if not targets:
            print(f"No venues matched '{filter_name}'. Available: {', '.join(v['name'] for v in VENUES)}")
            return

    print(f"\n{'Venue':<44} {'Status':<9} {'Events':<8} {'Time':<8} Notes")
    print("=" * 85)
    total_events = 0
    ok_count = 0
    err_count = 0
    empty_count = 0
    t_start = time.time()

    for v in targets:
        t0 = time.time()
        try:
            evs = v["scraper"](v["url"], v["ua"])
            dur = time.time() - t0
            count = len(evs)
            total_events += count
            if count > 0:
                ok_count += 1
                status = "OK"
                note = ""
            else:
                empty_count += 1
                status = "EMPTY"
                note = "No upcoming events parsed"
        except Exception as e:
            dur = time.time() - t0
            err_count += 1
            count = 0
            status = "ERROR"
            note = str(e)[:30]

        print(f"{v['name'][:42]:<44} {status:<9} {count:<8} {dur:.2f}s   {note}")

    total_time = time.time() - t_start
    print("=" * 85)
    print(f"Summary: {ok_count} OK | {empty_count} EMPTY | {err_count} ERROR | {total_events} Events | {total_time:.1f}s Total\n")


def _start_background_refresher():
    def _loop():
        while True:
            time.sleep(30 * 60)
            try:
                get_all_events(force=True)
            except Exception:
                pass

    t = threading.Thread(target=_loop, daemon=True)
    t.start()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] in ("test", "check"):
        filter_arg = sys.argv[2] if len(sys.argv) > 2 else None
        run_diagnostics(filter_arg)
    elif len(sys.argv) > 1 and sys.argv[1] == "export":
        out = sys.argv[2] if len(sys.argv) > 2 else "events.json"
        if out.endswith(".html") or (len(sys.argv) > 2 and sys.argv[2] == "html"):
            target = sys.argv[3] if len(sys.argv) > 3 else "events.html"
            export_html(target)
        else:
            export_json(out)
    else:
        _start_background_refresher()
        host = "0.0.0.0" if os.environ.get("PORT") else "127.0.0.1"
        print(f"NYC Events → http://{host}:{PORT}")
        app.run(host=host, port=PORT, debug=False)
