"""NYC Events — RSS 2.0 and iCalendar (.ics) feeds.

feed.xml   the next upcoming events for feed readers
events.ics subscribable calendar of the next week's events for Apple / Google / Outlook

Both are built from group_by_date()'s deduplicated events, so every entry has a real local
start time. iCal UIDs are derived from the event itself (not Python's per-process hash()),
so subscribed calendars update entries in place instead of duplicating them each refresh.
"""

import hashlib
import os
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from html import escape

from scrapers import EASTERN
from seo import SITE_NAME, _upcoming, get_site_url, page_url


def _event_uid(e):
    raw = f"{(e.get('name') or '').strip().lower()}|{(e.get('venue') or '').strip().lower()}|{e['_time'].isoformat()}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]


def feed_events(dated, days=7, limit=150):
    """The next upcoming events in start order (services and family listings left out)."""
    upcoming = [e for e in _upcoming(dated, days=days, start=datetime.now(EASTERN))
                if (e.get("category") or "") not in ("services", "family")]
    return upcoming[:limit]


def build_rss(events, site_url=None):
    site_url = site_url or get_site_url()
    now = format_datetime(datetime.now(timezone.utc))
    items = []
    for e in events:
        t = e["_time"]
        venue = e.get("venue") or e.get("_source_venue") or "New York"
        when = "time TBA" if e.get("_time_unknown") else t.strftime("%-I:%M %p")
        title = f"{e.get('name')} — {venue} ({t.strftime('%a %b')} {t.day}, {when})"
        desc = e.get("description") or f"{e.get('name')} at {venue}."
        if e.get("price"):
            desc = f"{desc} Price: {e['price']}."
        items.append(f"""    <item>
      <title>{escape(title)}</title>
      <link>{escape(e.get('url') or page_url('', site_url))}</link>
      <guid isPermaLink="false">{_event_uid(e)}</guid>
      <pubDate>{format_datetime(t.astimezone(timezone.utc))}</pubDate>
      <category>{escape(e.get('category') or 'event')}</category>
      <description>{escape(desc)}</description>
    </item>""")
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>{SITE_NAME} · upcoming events</title>
    <link>{page_url('', site_url)}</link>
    <description>Notable concerts, DJ nights, comedy, theater, run clubs, and free events coming up in New York City.</description>
    <language>en-us</language>
    <ttl>30</ttl>
    <lastBuildDate>{now}</lastBuildDate>
    <atom:link href="{page_url('feed.xml', site_url)}" rel="self" type="application/rss+xml" />
{chr(10).join(items)}
  </channel>
</rss>
"""


def _ics_text(s):
    s = " ".join(str(s or "").split())
    return s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")


def _ics_fold(line):
    """RFC 5545: lines longer than 75 octets are folded with CRLF + space."""
    raw = line.encode("utf-8")
    if len(raw) <= 75:
        return line
    parts, cur = [], b""
    for ch in line:
        b = ch.encode("utf-8")
        if len(cur) + len(b) > (75 if not parts else 74):
            parts.append(cur.decode("utf-8"))
            cur = b""
        cur += b
    parts.append(cur.decode("utf-8"))
    return "\r\n ".join(parts)


def build_ics(events, site_url=None):
    site_url = site_url or get_site_url()
    host = site_url.split("://", 1)[-1].split("/")[0]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR", "VERSION:2.0", f"PRODID:-//{SITE_NAME}//Live Calendar//EN",
        "CALSCALE:GREGORIAN", "METHOD:PUBLISH", f"X-WR-CALNAME:{SITE_NAME} events",
        "X-WR-TIMEZONE:America/New_York", "REFRESH-INTERVAL;VALUE=DURATION:PT6H",
        "X-WR-CALDESC:Notable upcoming concerts\\, comedy\\, nightlife\\, and free events in NYC.",
    ]
    for e in events:
        t = e["_time"]
        start = t.astimezone(timezone.utc)
        venue = e.get("venue") or e.get("_source_venue") or "New York"
        location = venue if not e.get("address") or e["address"] in venue else f"{venue}, {e['address']}"
        url = e.get("url") or page_url("", site_url)
        desc = " · ".join(x for x in (e.get("description"), e.get("price") and f"Price: {e['price']}", url) if x)
        lines += [
            "BEGIN:VEVENT",
            f"UID:{_event_uid(e)}@{host}",
            f"DTSTAMP:{stamp}",
            *([f"DTSTART;VALUE=DATE:{t.strftime('%Y%m%d')}"] if e.get("_time_unknown") else [
                f"DTSTART:{start.strftime('%Y%m%dT%H%M%SZ')}",
                f"DTEND:{(start + timedelta(hours=2)).strftime('%Y%m%dT%H%M%SZ')}",
            ]),
            f"SUMMARY:{_ics_text(e.get('name'))}",
            f"LOCATION:{_ics_text(location)}",
            f"DESCRIPTION:{_ics_text(desc)}",
            f"URL:{url}",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return "\r\n".join(_ics_fold(line) for line in lines) + "\r\n"


def write_feeds(base_dir, dated, site_url=None):
    events = feed_events(dated)
    out = []
    for name, content in (("feed.xml", build_rss(events, site_url)), ("events.ics", build_ics(events, site_url))):
        path = os.path.join(base_dir, name)
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(content)
        out.append(path)
    return out
