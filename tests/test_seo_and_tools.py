"""Tests for the SEO layer, feeds, curator, themes, and the ported Boston scripts."""

import json
import os
import re
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in (BASE_DIR, os.path.join(BASE_DIR, "scripts")):
    if p not in sys.path:
        sys.path.insert(0, p)

import scrapers  # noqa: E402
import seo  # noqa: E402
import template  # noqa: E402
from export_feeds import _ics_fold, build_ics, build_rss  # noqa: E402
from scrapers import EASTERN  # noqa: E402


def _at(days, hour, minute=0):
    d = (datetime.now(EASTERN) + timedelta(days=days)).date()
    return datetime(d.year, d.month, d.day, hour, minute, tzinfo=EASTERN)


def _ev(name, t, venue="Elsewhere Brooklyn", category="music", **kw):
    e = {"name": name, "venue": venue, "_source_venue": kw.pop("source", venue), "category": category,
         "_time": t, "date": t.astimezone(timezone.utc).isoformat(), "url": kw.pop("url", f"https://x.com/{abs(hash(name))}")}
    e.update(kw)
    return e


def _dated(events):
    by = {}
    for e in events:
        by.setdefault(e["_time"].date(), []).append(e)
    return sorted(by.items())


class TestSiteUrl(unittest.TestCase):
    def test_cname_then_env_then_github_pages(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(seo, "ROOT", tmp), patch.dict(os.environ, {}, clear=False):
                os.environ.pop("SITE_URL", None)
                self.assertEqual(seo.get_site_url(), "https://behlv10.github.io/nyc_events")
                with patch.dict(os.environ, {"SITE_URL": "https://preview.example/"}):
                    self.assertEqual(seo.get_site_url(), "https://preview.example")
                with open(os.path.join(tmp, "CNAME"), "w") as f:
                    f.write("nycevents.example\n")
                with patch.dict(os.environ, {"SITE_URL": "https://preview.example"}):
                    self.assertEqual(seo.get_site_url(), "https://nycevents.example")

    def test_meta_tags_follow_site_url(self):
        tags = seo.build_seo_meta_tags(title="T & U", description="D", path="comedy-nyc/",
                                       image_path="og-comedy-nyc.jpg", site_url="https://nycevents.example")
        self.assertIn('<link rel="canonical" href="https://nycevents.example/comedy-nyc/">', tags)
        self.assertIn('content="https://nycevents.example/og-comedy-nyc.jpg"', tags)
        self.assertIn("<title>T &amp; U</title>", tags)

    def test_crawler_files(self):
        site = "https://nycevents.example"
        sitemap = ET.fromstring(seo.build_sitemap(site))
        locs = [el.text for el in sitemap.iter("{http://www.sitemaps.org/schemas/sitemap/0.9}loc")]
        self.assertEqual(len(locs), 1 + len(seo.HUBS))
        self.assertIn(f"{site}/run-clubs-nyc/", locs)
        self.assertIn(f"Sitemap: {site}/sitemap.xml", seo.build_robots(site))
        self.assertIn(f"{site}/events.ics", seo.build_llms_txt(12345, 600, site))

    def test_every_hub_output_is_gitignored(self):
        with open(os.path.join(BASE_DIR, ".gitignore")) as f:
            ignored = f.read()
        for slug in seo.HUBS:
            self.assertIn(f"/{slug}/", ignored, slug)


class TestStructuredData(unittest.TestCase):
    def test_event_schema_has_offset_start_and_offer(self):
        e = _ev("Boy Harsher", _at(2, 21), venue="Knockdown Center", price="$35", address="52-19 Flushing Ave, Maspeth, NY 11378")
        sch = seo.event_schema(e, "https://nycevents.example")
        start = datetime.fromisoformat(sch["startDate"])
        self.assertIsNotNone(start.tzinfo)
        self.assertEqual(start.hour, 21)
        self.assertEqual(sch["offers"]["price"], "35")
        self.assertEqual(sch["location"]["address"]["addressRegion"], "NY")

    def test_hub_filters(self):
        events = [
            _ev("Prospect Park Run Club", _at(1, 19), venue="Prospect Park", category="sports"),
            _ev("Bushwick Techno Night", _at(1, 23), venue="Bossa Nova Civic Club (1271 Myrtle Ave, Brooklyn)", category="clubbing"),
            _ev("Toddler Storytime", _at(1, 10), venue="Brooklyn Public Library", category="family"),
            _ev("Free Jazz in the Park", _at(1, 18), venue="Bryant Park", category="music", price="Free"),
        ]
        dated = _dated(events)
        names = lambda slug: [e["name"] for e in seo.hub_events(seo.HUBS[slug], dated)]
        self.assertEqual(names("run-clubs-nyc"), ["Prospect Park Run Club"])
        self.assertEqual(names("dj-techno-nights-nyc"), ["Bushwick Techno Night"])
        self.assertIn("Free Jazz in the Park", names("free-events-nyc"))
        self.assertNotIn("Toddler Storytime", names("brooklyn"))

    def test_hub_page_renders_json_ld(self):
        dated = _dated([_ev("Comedy Cellar Showcase", _at(1, 20), venue="Comedy Cellar", category="comedy")])
        page = seo.render_hub_page("comedy-nyc", dated, "https://nycevents.example")
        blocks = [json.loads(b) for b in re.findall(r'<script type="application/ld\+json">(.*?)</script>', page, re.S)]
        self.assertEqual([b["@type"] for b in blocks], ["ItemList", "BreadcrumbList"])
        self.assertEqual(blocks[0]["itemListElement"][0]["item"]["name"], "Comedy Cellar Showcase")
        self.assertIn('href="https://nycevents.example/comedy-nyc/"', page)


class TestFeeds(unittest.TestCase):
    def test_ics_uids_stable_and_lines_folded(self):
        events = [_ev("A very long event title " * 6, _at(2, 20), description="x" * 300)]
        first, second = build_ics(events, "https://nycevents.example"), build_ics(events, "https://nycevents.example")
        uid = lambda s: re.search(r"UID:(\S+)", s).group(1)
        self.assertEqual(uid(first), uid(second))
        self.assertTrue(all(len(line.encode()) <= 75 for line in first.split("\r\n")))
        self.assertRegex(first, r"DTSTART:\d{8}T\d{6}Z")
        parsed = scrapers._ical_events(first)
        self.assertEqual(len(parsed), 1)

    def test_fold_handles_multibyte(self):
        line = "SUMMARY:" + "é" * 80
        self.assertTrue(all(len(p.encode()) <= 75 for p in _ics_fold(line).split("\r\n")))

    def test_rss_is_valid_xml(self):
        root = ET.fromstring(build_rss([_ev("Show & Tell <live>", _at(1, 20))], "https://nycevents.example"))
        self.assertEqual(len(list(root.iter("item"))), 1)


class TestCuratorAndHighlights(unittest.TestCase):
    def test_curator_scores_and_caps(self):
        from curate_highlights import curate

        t = _at(1, 20)
        events = [_ev(f"Concert {i}", t, venue="Brooklyn Steel", _alt_sources=[{"url": "u1"}, {"url": "u2"}]) for i in range(8)]
        events += [_ev("ESL Class", t, category="services"), _ev("NJ Show", t, venue="Starland Ballroom, Sayreville, NJ")]
        picks = curate(_dated(events), days=3, per_day=15, recurring_keys=set())
        names = [p["match"]["name_contains"] for p in picks]
        self.assertEqual(len(names), 4)  # MAX_PER_BUCKET for Music & nightlife
        self.assertNotIn("ESL Class", names)
        self.assertNotIn("NJ Show", names)
        self.assertTrue(picks[0]["note"].startswith("Listed on 3 calendars"))

    def test_manual_highlights_preserved(self):
        import curate_highlights

        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "highlights.json")
            with open(out, "w") as f:
                json.dump([{"id": "hand", "match": {"name_contains": "Moth"}, "badge": "Pick"},
                           {"id": "old", "auto": True, "match": {"name_contains": "x"}}], f)
            events = os.path.join(tmp, "events.json")
            with open(events, "w") as f:
                json.dump({"venues": []}, f)
            curate_highlights.main(["--events", events, "--out", out])
            with open(out) as f:
                ids = [h["id"] for h in json.load(f)]
            self.assertEqual(ids, ["hand"])

    def test_highlight_date_window(self):
        t = _at(2, 20)
        hl = [{"match": {"name_contains": "moth", "venue_contains": "bell house"},
               "start_date": t.date().isoformat(), "expires": t.date().isoformat()}]
        self.assertIsNotNone(template._get_event_highlight(_ev("The Moth StorySLAM", t, venue="The Bell House"), hl))
        self.assertIsNone(template._get_event_highlight(_ev("The Moth StorySLAM", t + timedelta(days=1), venue="The Bell House"), hl))


class TestThemesAndBoroughs(unittest.TestCase):
    def test_seasonal_site_themes_2026(self):
        g = lambda m, d: template.get_seasonal_theme(datetime(2026, m, d))[0]
        self.assertEqual(g(10, 31), "halloween")
        self.assertEqual(g(11, 3), "election")       # Tuesday after the first Monday
        self.assertEqual(g(11, 11), "veterans")
        self.assertEqual(g(11, 26), "thanksgiving")  # 4th Thursday
        self.assertEqual(g(11, 27), "blackfriday")
        self.assertEqual(g(11, 30), "cybermonday")
        self.assertIsNone(g(11, 4))

    def test_flyer_seasons(self):
        from themes import get_theme

        self.assertEqual(get_theme(date(2026, 10, 30))["id"], "halloween")
        self.assertEqual(get_theme(date(2026, 11, 9))["id"], "fall")
        self.assertEqual(get_theme(date(2026, 6, 20))["id"], "pride")
        self.assertEqual(get_theme(date(2026, 7, 20))["id"], "summer")

    def test_venue_beats_source_name_for_borough(self):
        city = template._event_city("Canarsie Park (Canarsie Park House)", "NYC Parks Free Public Events", None, {})
        self.assertEqual(city, "brooklyn")
        self.assertEqual(template._event_city("Some Bar", "NYC Trivia League", None, {}), "manhattan")


class TestTopicCategories(unittest.TestCase):
    def test_off_topic_search_results_are_not_forced_into_topic_category(self):
        when = _at(3, 20).astimezone(timezone.utc).isoformat()
        v = {"name": "Eventbrite: Outdoor Adventures", "url": "https://www.eventbrite.com/d/ny--new-york/outdoor-adventure/",
             "ua": "x", "default_category": "outdoors", "topic_terms": scrapers._topic_terms("outdoor-adventure"),
             "scraper": lambda url, ua: [{"name": "Friday Night Lights at Mama Taco", "date": when},
                                         {"name": "Outdoor Adventure Day: Bear Mountain", "date": when},
                                         {"name": "Bottomless Brunch", "date": when}]}
        with patch("scrapers._save_venue_cache"):
            res = scrapers._scrape_one(v, force=True)
        cats = {e["name"]: e["category"] for e in res["events"]}
        self.assertEqual(cats["Friday Night Lights at Mama Taco"], "community")
        self.assertEqual(cats["Outdoor Adventure Day: Bear Mountain"], "outdoors")

    def test_run_terms_do_not_match_brunch(self):
        terms = scrapers._topic_terms("run-club")
        on = lambda t: any(re.search(r"\b" + re.escape(x), t.lower()) for x in terms)
        self.assertTrue(on("Sunday Runners Social"))
        self.assertFalse(on("Bottomless Brunch"))

    def test_eventbrite_challenge_page_raises_for_visible_fallback(self):
        from unittest.mock import MagicMock

        blocked = MagicMock(text="<html>Just a moment...</html>", status_code=200)
        blocked.raise_for_status = MagicMock()
        with patch("scrapers._SESSION.get", return_value=blocked), patch("scrapers.time.sleep"):
            with self.assertRaises(RuntimeError):
                scrapers.scrape_eventbrite_jsonld("https://www.eventbrite.com/d/ny--new-york/dj/", "x")


class TestRsvpFreeClaim(unittest.TestCase):
    def test_meetup_outing_does_not_make_ticketed_show_free(self):
        t = _at(1, 19)
        out = template._merge_duplicates([
            _ev("Christmas Spectacular Starring the Radio City Rockettes", t, venue="Radio City Music Hall",
                source="Meetup: Borough Hoppers", url="https://www.meetup.com/borough-hoppers/events/1/", price="Free"),
            _ev("Christmas Spectacular Starring the Radio City Rockettes", t, venue="Radio City Music Hall",
                source="Radio City Music Hall", url="https://www.ticketmaster.com/event/abc"),
        ])
        self.assertEqual(len(out), 1)
        self.assertIsNone(out[0].get("price"))


class TestScripts(unittest.TestCase):
    def test_indexnow_payload(self):
        from ping_indexnow import build_payload

        p = build_payload("https://behlv10.github.io/nyc_events", "abc123")
        self.assertEqual(p["host"], "behlv10.github.io")
        self.assertEqual(p["keyLocation"], "https://behlv10.github.io/nyc_events/abc123.txt")
        self.assertTrue(all(u.startswith("https://behlv10.github.io/nyc_events/") for u in p["urlList"]))

    def test_reddit_roundup_sections(self):
        from generate_reddit_roundup import build_post, weekend_dates

        now = datetime(2026, 11, 4, 12, tzinfo=EASTERN)
        fri = weekend_dates(now)[0]
        t = datetime(fri.year, fri.month, fri.day, 20, tzinfo=EASTERN)
        dated = _dated([
            _ev("Japanese Breakfast", t, venue="Brooklyn Steel", _alt_sources=[{"url": "a"}]),
            _ev("Prospect Park Run Club", t.replace(hour=9), venue="Prospect Park", category="sports", price="Free"),
        ])
        post = build_post(dated, now=now)
        self.assertIn("### 🎵 Concerts & live music", post)
        self.assertIn("Japanese Breakfast", post)
        self.assertIn("Prospect Park Run Club", post)

    def test_audit_parses_headings_and_links(self):
        from audit_coverage import parse_items

        items = parse_items("FRIDAY, NOVEMBER 6\n[Lime Garden @ Elsewhere](https://e.x)\nALL WEEKEND\nSmorgasburg @ Marsha P. Johnson", 2026)
        self.assertEqual(items[0]["date"], "2026-11-06")
        self.assertEqual((items[0]["title"], items[0]["venue"]), ("Lime Garden", "Elsewhere"))
        self.assertIsNone(items[1]["date"])


if __name__ == "__main__":
    unittest.main()


class TestFetchResilience(unittest.TestCase):
    def test_trickling_server_hits_wall_clock_deadline(self):
        import time as _time

        import requests

        class Trickle:
            def read(self, amt=None, decode_content=True):
                _time.sleep(0.02)
                return b"x" * 10

            def close(self):
                pass

            def release_conn(self):
                pass

        resp = requests.Response()
        resp.status_code = 200
        resp.raw = Trickle()
        with patch("scrapers._SESSION.get", return_value=resp):
            start = _time.monotonic()
            with self.assertRaises(scrapers.FetchDeadlineExceeded):
                scrapers.fetch_text("https://slow.example", max_seconds=0.3)
            self.assertLess(_time.monotonic() - start, 2)

    def test_host_circuit_breaker_fails_fast(self):
        calls = []

        def failing(url, ua):
            calls.append(url)
            raise RuntimeError("throttled")

        v = {"url": "https://www.eventbrite.com/d/ny--new-york/dj/", "ua": "x", "scraper": failing}
        scrapers._reset_host_breakers()
        for _ in range(scrapers.HOST_FAILURE_LIMIT + 3):
            with self.assertRaises(RuntimeError):
                scrapers._run_scraper(v)
        self.assertEqual(len(calls), scrapers.HOST_FAILURE_LIMIT)
        scrapers._reset_host_breakers()
