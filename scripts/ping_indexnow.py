#!/usr/bin/env python3
"""Tell IndexNow search engines (Bing, Yandex, Seznam, Naver...) that pages were refreshed.

Host and key location come from seo.get_site_url(), so this follows a future custom domain
(CNAME) automatically. On github.io the key file lives under /nyc_events/, which scopes
submissions to that path — which is exactly the set of URLs we submit.

The workflow calls this after every deploy; it only actually pings every 6 hours (UTC hours
0, 6, 12, 18) since the same URLs are refreshed every 30 minutes. Use --force to ping now.
"""

import argparse
import glob
import os
import sys
from datetime import datetime, timezone

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from seo import HUBS, get_site_url, page_url  # noqa: E402

ENDPOINT = "https://api.indexnow.org/indexnow"


def find_key():
    for path in glob.glob(os.path.join(ROOT, "*.txt")):
        name = os.path.basename(path)[:-4]
        if len(name) == 32 and all(c in "0123456789abcdef" for c in name):
            with open(path, encoding="utf-8") as f:
                if f.read().strip() == name:
                    return name
    return None


def build_payload(site_url, key):
    host = site_url.split("://", 1)[-1].split("/")[0]
    urls = [page_url("", site_url)] + [page_url(f"{slug}/", site_url) for slug in HUBS]
    return {"host": host, "key": key, "keyLocation": page_url(f"{key}.txt", site_url), "urlList": urls}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--force", action="store_true", help="ping regardless of the 6-hour schedule")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    now = datetime.now(timezone.utc)
    if not args.force and not (now.hour % 6 == 0 and now.minute < 30):
        print("IndexNow: not a 6-hour boundary; skipping (use --force to ping now)")
        return 0
    key = find_key()
    if not key:
        print("IndexNow: no <key>.txt key file at the repo root; skipping")
        return 0
    payload = build_payload(get_site_url(), key)
    if args.dry_run:
        print(payload)
        return 0
    try:
        resp = requests.post(ENDPOINT, json=payload, timeout=15,
                             headers={"Content-Type": "application/json; charset=utf-8"})
        print(f"IndexNow: HTTP {resp.status_code} for {len(payload['urlList'])} URLs on {payload['host']}")
    except requests.RequestException as exc:
        print(f"IndexNow: request failed: {exc}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
