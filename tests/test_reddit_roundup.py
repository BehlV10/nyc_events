import json
import os
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import generate_reddit_roundup as R  # noqa: E402
from scrapers import EASTERN  # noqa: E402


def _ev(name, day, hour, venue, cat="music"):
    t = datetime(day.year, day.month, day.day, hour, 0, tzinfo=EASTERN)
    return {"name": name, "_time": t, "date": t.isoformat(), "venue": venue, "_source_venue": venue, "venue_url": "https://venue.example",
            "category": cat, "url": "https://venue.example/e", "description": "x"}


MON = date(2030, 11, 11)  # a Monday
NOW = datetime(2030, 11, 11, 9, 0, tzinfo=EASTERN)


class DateTests(unittest.TestCase):
    def test_weekday_dates(self):
        self.assertEqual(R.weekday_dates(NOW), [MON + timedelta(days=i) for i in range(5)])
        sat = datetime(2030, 11, 16, 12, tzinfo=EASTERN)
        self.assertEqual(R.weekday_dates(sat)[0], date(2030, 11, 18))  # the weekend looks ahead to next week
        wed = datetime(2030, 11, 13, 12, tzinfo=EASTERN)
        self.assertEqual(R.weekday_dates(wed)[0], MON)


class NewsTests(unittest.TestCase):
    def test_only_recent_items_are_shown(self):
        with tempfile.TemporaryDirectory() as t:
            p = os.path.join(t, "n.json")
            json.dump({"items": [{"date": "2030-11-10", "text": "Fresh [thing](https://x)"},
                                 {"date": "2030-10-01", "text": "Old"}, {"date": "2030-11-20", "text": "Future"}, {"text": "No date"}]}, open(p, "w"))
            self.assertEqual(R.load_news(MON, p), ["* Fresh [thing](https://x)"])
        self.assertEqual(R.load_news(MON, "/nonexistent.json"), [])


class PostTests(unittest.TestCase):
    def setUp(self):
        d = MON
        self.dated = [
            (d, [_ev("Matinee Jam", d, 13, "Brooklyn Steel"), _ev("Monday Gig", d, 20, "Brooklyn Steel")]),
            (d + timedelta(days=1), [_ev("Monday Gig", d + timedelta(days=1), 20, "Brooklyn Steel"),
                                     _ev("Bowery Night", d + timedelta(days=1), 21, "Bowery Ballroom")]),
        ]

    def test_weekday_post_is_evenings_only_one_listing_per_show_grouped_by_day(self):
        post = R.build_post(self.dated, mode="weekday", now=NOW, news=[])
        self.assertIn("weeknight roundup", post)
        self.assertNotIn("Matinee Jam", post)  # before 5 PM
        self.assertEqual(post.count("Monday Gig"), 1)
        self.assertIn("### Monday, Nov 11", post)
        self.assertIn("Bowery Night", post)

    def test_borough_post_keeps_only_that_borough(self):
        post = R.build_post(self.dated, mode="weekday", now=NOW, borough="brooklyn", news=[])
        self.assertIn("Brooklyn weeknight roundup", post)
        self.assertIn("Monday Gig", post)
        self.assertNotIn("Bowery Night", post)

    def test_news_block_tops_the_post(self):
        post = R.build_post(self.dated, mode="weekday", now=NOW, news=["* Something new"])
        self.assertLess(post.index("New on the site"), post.index("### "))


if __name__ == "__main__":
    unittest.main()
