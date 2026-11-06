"""Polite crawling: per-site limits, backing off when a site says no, never dodging a refusal."""
import inspect
import io
import os
import sys
import threading
import time
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import scrapers  # noqa: E402
import source_health  # noqa: E402
from scrapers import HOST_GATE, SiteRefused, _host_policy  # noqa: E402


def _resp(status, headers=None):
    r = requests.Response()
    r.status_code = status
    r.headers.update(headers or {})
    r._content = b""
    r.raw = io.BytesIO(b"")
    return r


class _FakeNetwork:
    """Stands in for requests.Session.request: records concurrency and answers from a script."""

    def __init__(self, answers=None, delay=0.02):
        self.answers = list(answers or [])
        self.delay = delay
        self.calls = []
        self.active = {}
        self.peak = {}
        self.lock = threading.Lock()

    def __call__(self, method, url, *a, **kw):
        host = scrapers._host_of(url)
        with self.lock:
            self.calls.append((time.monotonic(), host))
            self.active[host] = self.active.get(host, 0) + 1
            self.peak[host] = max(self.peak.get(host, 0), self.active[host])
        time.sleep(self.delay)
        with self.lock:
            self.active[host] -= 1
            status = self.answers.pop(0) if self.answers else 200
        return status if isinstance(status, requests.Response) else _resp(status)


class PoliteSessionTest(unittest.TestCase):
    def setUp(self):
        HOST_GATE.reset()
        self.sleeps = []
        # Keep the real pacing but shrink it so the test is fast.
        self.policy = mock.patch.dict(scrapers.HOST_POLICY, {"eventbrite.com": (1, 0.03)})
        self.policy.start()
        self.default = mock.patch.object(scrapers, "HOST_POLICY_DEFAULT", (2, 0.0))
        self.default.start()

    def tearDown(self):
        self.policy.stop()
        self.default.stop()
        HOST_GATE.reset()

    def _fetch_all(self, urls):
        threads = [threading.Thread(target=lambda u=u: scrapers._SESSION.get(u)) for u in urls]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

    def test_one_at_a_time_and_spaced_for_bot_protected_sites(self):
        net = _FakeNetwork()
        with mock.patch.object(requests.Session, "request", net):
            self._fetch_all([f"https://www.eventbrite.com/api/v3/organizers/{i}/events/" for i in range(5)])
        self.assertEqual(net.peak["www.eventbrite.com"], 1)
        starts = sorted(t for t, _ in net.calls)
        gaps = [b - a for a, b in zip(starts, starts[1:])]
        self.assertTrue(all(g >= 0.02 for g in gaps), gaps)  # 30ms apart, less thread wake-up jitter

    def test_at_most_two_at_a_time_elsewhere(self):
        net = _FakeNetwork(delay=0.05)
        with mock.patch.object(requests.Session, "request", net):
            self._fetch_all([f"https://www.bkmag.com/events/e{i}" for i in range(8)])
        self.assertEqual(net.peak["www.bkmag.com"], 2)

    def test_policy_matches_subdomains(self):
        self.assertEqual(_host_policy("www.meetup.com"), scrapers.HOST_POLICY["meetup.com"])
        self.assertEqual(_host_policy("www.nycgovparks.org"), (1, 1.0))
        self.assertEqual(_host_policy("example.org"), scrapers.HOST_POLICY_DEFAULT)

    def test_429_waits_retry_after_then_stops_asking(self):
        net = _FakeNetwork([_resp(429, {"Retry-After": "7"}), 429])
        with mock.patch.object(requests.Session, "request", net), \
                mock.patch.object(scrapers.time, "sleep", side_effect=self.sleeps.append):
            r = scrapers._SESSION.get("https://www.meetup.com/find/?page=1")
            self.assertEqual(r.status_code, 429)
            self.assertIn(7, self.sleeps)
            with self.assertRaises(SiteRefused):
                scrapers._SESSION.get("https://www.meetup.com/find/?page=2")
        self.assertEqual(len(net.calls), 2, "one retry, then no more requests to that site")

    def test_403_is_never_retried(self):
        net = _FakeNetwork([403])
        with mock.patch.object(requests.Session, "request", net):
            self.assertEqual(scrapers._SESSION.get("https://www.strandbooks.com/events").status_code, 403)
            with self.assertRaises(SiteRefused):
                scrapers._SESSION.get("https://www.strandbooks.com/events/2026/12")
        self.assertEqual(len(net.calls), 1)
        # Other sites are unaffected, and the next crawl asks again.
        with mock.patch.object(requests.Session, "request", _FakeNetwork([200])):
            self.assertEqual(scrapers._SESSION.get("https://www.mcnallyeditions.com/events").status_code, 200)
        HOST_GATE.reset()
        with mock.patch.object(requests.Session, "request", _FakeNetwork([200])):
            self.assertEqual(scrapers._SESSION.get("https://www.strandbooks.com/events").status_code, 200)

    def test_overloaded_site_gets_one_retry_then_a_rest(self):
        net = _FakeNetwork([504, 200])
        with mock.patch.object(requests.Session, "request", net), \
                mock.patch.object(scrapers.time, "sleep", side_effect=self.sleeps.append):
            self.assertEqual(scrapers._SESSION.get("https://www.cmom.org/events/a").status_code, 200)
        self.assertEqual(len(net.calls), 2)
        net = _FakeNetwork([504] * 2 * scrapers.OVERLOADED_AFTER)
        with mock.patch.object(requests.Session, "request", net), \
                mock.patch.object(scrapers.time, "sleep", side_effect=self.sleeps.append):
            for i in range(scrapers.OVERLOADED_AFTER):
                scrapers._SESSION.get(f"https://www.cmom.org/events/{i}")
            with self.assertRaises(SiteRefused):
                scrapers._SESSION.get("https://www.cmom.org/events/next")


class RefusedSourceKeepsDataTest(unittest.TestCase):
    def tearDown(self):
        HOST_GATE.reset()

    def _source(self, scraper):
        return {"name": "Strand", "url": "https://www.strandbooks.com/events", "ua": "UA",
                "scraper": scraper, "default_category": "books"}

    def _old(self):
        when = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
        return [{"name": "Author Talk", "date": when, "url": "https://www.strandbooks.com/e/1", "venue": "Strand"}]

    def test_last_good_events_survive_a_refusal(self):
        def blocked_scraper(url, ua):
            HOST_GATE.refuse("www.strandbooks.com", "403")
            return []

        with mock.patch.object(scrapers, "_load_venue_cache", side_effect=[None, {"events": self._old()}]), \
                mock.patch.object(scrapers, "_save_venue_cache") as save:
            res = scrapers._scrape_one(self._source(blocked_scraper))
        self.assertEqual([e["name"] for e in res["events"]], ["Author Talk"])
        self.assertTrue(res["fallback"])
        self.assertIsNone(res["error"])
        save.assert_not_called()

    def test_later_sources_on_a_refused_site_are_not_errors(self):
        def blocked_scraper(url, ua):
            raise SiteRefused("www.strandbooks.com refused us earlier this run (403)")

        with mock.patch.object(scrapers, "_load_venue_cache", side_effect=[None, {"events": self._old()}]), \
                mock.patch.object(scrapers, "_save_venue_cache") as save:
            res = scrapers._scrape_one(self._source(blocked_scraper))
        self.assertIsNone(res["error"])
        self.assertTrue(res["fallback"])
        self.assertEqual(len(res["events"]), 1)
        save.assert_not_called()


class CacheCodeHashTest(unittest.TestCase):
    def test_fresh_cache_from_other_code_is_ignored_but_fallback_keeps_it(self):
        import json
        import tempfile

        def scraper_a(url, ua):
            return []

        def scraper_b(url, ua):
            return []

        with tempfile.TemporaryDirectory() as d, mock.patch.object(scrapers, "CACHE_DIR", d):
            scrapers._save_venue_cache("X", [{"name": "A"}], src="u|s", code=scrapers._code_hash(scraper_a))
            self.assertIsNotNone(scrapers._load_venue_cache("X", max_age=999, src="u|s", code=scrapers._code_hash(scraper_a)))
            self.assertIsNone(scrapers._load_venue_cache("X", max_age=999, src="u|s", code=scrapers._code_hash(scraper_b)))
            self.assertIsNotNone(scrapers._load_venue_cache("X", max_age=None, src="u|s"), "error fallback ignores code")


class NoDodgingTest(unittest.TestCase):
    def test_no_curl_retries(self):
        src = inspect.getsource(scrapers)
        self.assertNotIn('"curl"', src)
        self.assertNotIn("subprocess", src)

    def test_every_request_goes_through_the_gate(self):
        self.assertIsInstance(scrapers._SESSION, scrapers._PoliteSession)
        self.assertNotRegex(inspect.getsource(scrapers), r"(?<![\w.])requests\.(get|post)\(")


class SourceHealthTests(unittest.TestCase):
    def test_statuses(self):
        now = datetime(2026, 11, 5, 17, 0, tzinfo=timezone.utc)
        soon, later = "2026-11-08T00:00:00+00:00", "2026-12-20T00:00:00+00:00"
        venues = [
            {"venue": "Good", "url": "https://good.example/", "events": [{"date": soon}]},
            {"venue": "Seasonal", "url": "https://later.example/", "events": [{"date": later}]},
            {"venue": "Broken", "url": "https://broken.example/", "events": [], "error": "HTTP 500"},
            {"venue": "Blocked", "url": "https://www.blocked.example/x", "events": [{"date": soon}]},
        ]
        rows = source_health.source_status(venues, refused={"blocked.example": "403 Forbidden"}, now=now)
        got = {r["source"]: (r["status"], r["next_two_weeks"], r["next_event"]) for r in rows}
        self.assertEqual(got, {"Broken": ("error", 0, None), "Blocked": ("refused", 1, "2026-11-08"),
                               "Seasonal": ("empty", 0, "2026-12-20"), "Good": ("ok", 1, "2026-11-08")})
        self.assertEqual([r["source"] for r in rows], ["Broken", "Blocked", "Seasonal", "Good"])

    def test_report_written_to_cache_and_summary(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            summary = os.path.join(d, "summary.md")
            with mock.patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": summary}), mock.patch("builtins.print"):
                source_health.write_report([{"venue": "Quiet", "url": "https://q.example/", "events": []}],
                                           path=os.path.join(d, "status.json"))
            md = open(summary, encoding="utf-8").read()
            self.assertIn("| [Quiet](https://q.example/) | empty |", md)
            self.assertIn("Venues we can't read", md)
            self.assertTrue(os.path.exists(os.path.join(d, "status.json")))


if __name__ == "__main__":
    unittest.main()
