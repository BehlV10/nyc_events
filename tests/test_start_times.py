"""Listings whose source gives no start time get it from the event's own page, or show no time."""
import os
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import scrapers  # noqa: E402
import template as T  # noqa: E402

DAY = date(2030, 11, 18)


class StartTimeFromPage(unittest.TestCase):
    def test_json_ld_for_that_day(self):
        page = '{"startDate":"2030-11-18T19:30:00-05:00"} {"startDate":"2030-11-19T14:00:00-05:00"}'
        self.assertEqual(scrapers.start_time_from_page(page, DAY), (19, 30))

    def test_time_element_and_utc_stamp(self):
        self.assertEqual(scrapers.start_time_from_page('<time datetime="2030-11-18T18:00:00-05:00">6pm</time>', DAY), (18, 0))
        self.assertEqual(scrapers.start_time_from_page('"startDate": "2030-11-19T00:30:00Z"', DAY), (19, 30))

    def test_clock_written_after_the_date(self):
        page = "<p>Open daily 11 am to 6 pm.</p><h2>Monday, November 18, 2030 at 7:30 PM</h2><p>Doors 6:30 PM</p>"
        self.assertEqual(scrapers.start_time_from_page(page, DAY), (19, 30))

    def test_several_showtimes_or_only_opening_hours_stay_unknown(self):
        films = '{"startDate":"2030-11-18T16:35:00-05:00"}{"startDate":"2030-11-18T19:25:00-05:00"}'
        self.assertIsNone(scrapers.start_time_from_page(films, DAY))
        self.assertIsNone(scrapers.start_time_from_page("<p>Gallery hours: 11 am</p><p>Nov 18</p>" + "x" * 80, DAY))
        self.assertIsNone(scrapers.start_time_from_page('{"startDate":"2030-11-18"}', DAY))


class FillMissingTimes(unittest.TestCase):
    def test_placeholder_times_are_replaced_cached_or_left_unknown(self):
        when = (datetime.now(scrapers.EASTERN) + timedelta(days=3)).replace(hour=12, minute=0, second=0, microsecond=0)
        iso = when.astimezone(timezone.utc).isoformat()
        stamp = when.replace(hour=19, minute=30).isoformat()
        known = {"name": "Quartet", "date": iso, "url": "https://hall.example/e/1", "time_unknown": True}
        film = {"name": "Film", "date": iso, "url": "https://hall.example/e/2", "time_unknown": True}
        real_noon = {"name": "Lunch Concert", "date": iso, "url": "https://hall.example/e/3"}
        agg = {"name": "Party", "date": iso, "url": "https://allevents.in/x/1", "time_unknown": True}
        results = [{"venue": "Hall (own calendar)", "url": "https://hall.example/", "events": [known, film, real_noon]},
                   {"venue": "AllEvents NYC", "url": "https://allevents.in", "events": [agg]}]
        pages = {"https://hall.example/e/1": f'{{"startDate":"{stamp}"}}', "https://hall.example/e/2": "<p>no times here</p>"}
        asked = []
        fetch = lambda u: asked.append(u) or pages[u]
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "t.json")
            self.assertEqual(scrapers._fill_missing_times(results, path=path, fetch=fetch), 1)
            self.assertEqual(sorted(asked), ["https://hall.example/e/1", "https://hall.example/e/2"])  # not the aggregator, not the real noon
            again = []
            scrapers._fill_missing_times(results, path=path, fetch=lambda u: again.append(u) or pages[u])
            self.assertEqual(again, [])  # answers and misses are cached
        self.assertEqual(datetime.fromisoformat(known["date"]).astimezone(scrapers.EASTERN).strftime("%H:%M"), "19:30")
        self.assertNotIn("time_unknown", known)
        self.assertTrue(film["time_unknown"])
        self.assertEqual(real_noon["date"], iso)

    def test_unknown_time_reaches_the_card(self):
        results = [{"venue": "Hall (own calendar)", "url": "https://hall.example/", "events": [
            {"name": "Mystery Film", "date": "2030-01-08T12:00:00-05:00", "url": "https://hall.example/e/2", "time_unknown": True},
            {"name": "Lunch Concert", "date": "2030-01-08T12:00:00-05:00", "url": "https://hall.example/e/3"}]}]
        dated, _t, _o = T.group_by_date(results)
        flags = {e["name"]: bool(e.get("_time_unknown")) for _d, evs in dated for e in evs}
        self.assertEqual(flags, {"Mystery Film": True, "Lunch Concert": False})


if __name__ == "__main__":
    unittest.main()
