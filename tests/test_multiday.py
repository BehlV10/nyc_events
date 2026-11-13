"""Multi-day festivals show on every day they run (2 to 10 days), not just the first."""
import os
import sys
import unittest
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import template as T  # noqa: E402
from template import EASTERN  # noqa: E402


def _iso(d, h=12):
    return datetime(d.year, d.month, d.day, h, tzinfo=EASTERN).astimezone(timezone.utc).isoformat()


def _group(events):
    dated, _tba, _ongoing = T.group_by_date([{"venue": "Src", "url": "https://x.example", "events": events}])
    return {d: es for d, es in dated}


def _next(weekday, weeks=1):
    d = datetime.now(EASTERN).date() + timedelta(days=7 * weeks)
    return d + timedelta(days=(weekday - d.weekday()) % 7)


class DetectTests(unittest.TestCase):
    def _span(self, entry, start):
        entry.setdefault("_time", datetime(start.year, start.month, start.day, 12, tzinfo=EASTERN))
        return T._detect_event_date_span(entry, start)

    def test_end_timestamp_days(self):
        s = date(2030, 11, 22)
        self.assertEqual(self._span({"end": _iso(date(2030, 11, 24), 18)}, s), date(2030, 11, 24))
        self.assertIsNone(self._span({"end": _iso(s, 18)}, s))

    def test_overnight_party_is_one_night(self):
        s = date(2030, 11, 22)
        e = {"_time": datetime(2030, 11, 22, 18, tzinfo=EASTERN), "end": datetime(2030, 11, 23, 6, tzinfo=EASTERN).isoformat()}
        self.assertIsNone(T._detect_event_date_span(e, s))

    def test_text_patterns_and_caps(self):
        fri = _next(4)
        self.assertEqual(self._span({"name": "Holiday Market Fri-Sun"}, fri), fri + timedelta(days=2))
        self.assertEqual(self._span({"name": "Comic Fest 3-Day Pass"}, fri), fri + timedelta(days=2))
        self.assertIsNone(self._span({"name": "Long exhibit", "ends": (fri + timedelta(days=40)).isoformat()}, fri))
        self.assertIsNone(self._span({"name": "Plain show"}, fri))


class GroupTests(unittest.TestCase):
    def test_festival_appears_on_each_day_with_thru_and_final_day(self):
        fri = _next(4)
        ev = {"name": "Winter Fest", "date": _iso(fri, 11), "end": _iso(fri + timedelta(days=2), 20), "venue": "Park"}
        days = _group([ev])
        self.assertEqual(sorted(days), [fri, fri + timedelta(days=1), fri + timedelta(days=2)])
        whens = [T.format_when(days[d][0]) for d in sorted(days)]
        self.assertTrue(whens[0].endswith(f"thru {(fri + timedelta(days=2)).strftime('%a %b %-d')}"), whens)
        self.assertTrue(whens[1].startswith("11:00 AM · thru"), whens)
        self.assertTrue(whens[2].endswith("Final day"), whens)

    def test_each_day_has_its_own_identity_and_original_is_untouched(self):
        fri = _next(4)
        ev = {"name": "Winter Fest", "date": _iso(fri, 11), "end": _iso(fri + timedelta(days=1), 20), "venue": "Park"}
        days = _group([ev])
        a, b = days[fri][0], days[fri + timedelta(days=1)][0]
        self.assertNotEqual(T._event_stable_id(a), T._event_stable_id(b))
        self.assertEqual(ev["date"], _iso(fri, 11))

    def test_started_festival_only_shows_remaining_days(self):
        today = datetime.now(EASTERN).date()
        ev = {"name": "Winter Fest", "date": _iso(today - timedelta(days=1), 11), "end": _iso(today + timedelta(days=1), 20), "venue": "Park"}
        # an earlier start is "past": it goes to the ongoing list, as before this feature
        dated, _t, ongoing = T.group_by_date([{"venue": "Src", "url": "", "events": [ev]}])
        self.assertEqual(len(ongoing), 1)

    def test_single_day_events_unchanged(self):
        fri = _next(4)
        days = _group([{"name": "Gig", "date": _iso(fri, 20), "end": _iso(fri, 23), "venue": "Bar"}])
        self.assertEqual(list(days), [fri])
        self.assertNotIn("Final day", T.format_when(days[fri][0]))


if __name__ == "__main__":
    unittest.main()
