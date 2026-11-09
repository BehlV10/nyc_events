"""Date-only listings get the start time from the event's own page."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import scrapers  # noqa: E402


class EnrichEventTimes(unittest.TestCase):
    def run_enrich(self, events, pages, **kw):
        calls = []

        def fetch(url, ua):
            calls.append(url)
            return pages.get(url)

        with tempfile.TemporaryDirectory() as d:
            scrapers._enrich_event_times([{"venue": "DanceUS: NYC Salsa", "events": events}],
                                         path=os.path.join(d, "t.json"), fetch=fetch, **kw)
        return calls

    def test_midnight_listing_gets_the_page_time(self):
        e = {"name": "Beginner Tango", "date": "2099-11-09T05:00:00+00:00",
             "url": "https://www.danceus.org/event/1/beginner-tango/"}
        self.run_enrich([e], {e["url"]: "2099-11-09T18:30:00-05:00"})
        self.assertEqual(e["date"], "2099-11-09T23:30:00+00:00")

    def test_a_weekly_class_keeps_its_listed_day(self):
        e = {"name": "Class", "date": "2099-11-09T05:00:00+00:00", "url": "https://www.danceus.org/event/2/x/"}
        self.run_enrich([e], {e["url"]: "2099-11-16T18:30:00-05:00"})  # next Monday
        self.assertEqual(e["date"], "2099-11-09T23:30:00+00:00")

    def test_a_page_time_on_another_weekday_is_ignored(self):
        e = {"name": "Class", "date": "2099-11-09T05:00:00+00:00", "url": "https://www.danceus.org/event/2/x/"}
        self.run_enrich([e], {e["url"]: "2099-11-12T18:30:00-05:00"})
        self.assertEqual(e["date"], "2099-11-09T05:00:00+00:00")

    def test_past_days_are_not_fetched(self):
        e = {"name": "Old", "date": "2020-01-06T05:00:00+00:00", "url": "https://www.danceus.org/event/9/old/"}
        self.assertEqual(self.run_enrich([e], {}), [])

    def test_only_listed_hosts_and_untimed_events_are_fetched(self):
        timed = {"name": "A", "date": "2026-11-09T23:00:00+00:00", "url": "https://www.danceus.org/event/3/a/"}
        other = {"name": "B", "date": "2099-11-09T05:00:00+00:00", "url": "https://allevents.in/new-york/b/1"}
        self.assertEqual(self.run_enrich([timed, other], {}), [])

    def test_per_run_limit(self):
        events = [{"name": str(i), "date": "2099-11-09T05:00:00+00:00", "url": f"https://www.danceus.org/event/{i}/"}
                  for i in range(5)]
        self.assertEqual(len(self.run_enrich(events, {}, limit=2)), 2)


class ClosureNotices(unittest.TestCase):
    def test_closures_are_not_events(self):
        for t in ("Museum Closed", "Thanksgiving Day – Garden is CLOSED"):
            self.assertTrue(scrapers.is_placeholder_or_closed_event(t), t)
        self.assertFalse(scrapers.is_placeholder_or_closed_event("Closed Captioned Screening: Wicked"))


if __name__ == "__main__":
    unittest.main()
