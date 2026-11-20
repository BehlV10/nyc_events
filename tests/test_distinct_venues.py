"""Same title, same time, two different places: don't merge them into one card."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import template as T  # noqa: E402
import scrapers as S  # noqa: E402
from unittest import mock  # noqa: E402

SMALLSLIVE_HTML = """
<div class="event-row tonight-events upcoming-carousel">
  <div class="item"><a href="/events/1-jam-in-the-cafe/">Jam</a>
    <div class="jazzcultural-color title5 venue">Live at Jazzcultural</div><span>Fri Nov 20</span> <span>2:00 PM</span></div>
  <div class="item"><a href="/events/2-steve-slagle-quartet/">Steve</a>
    <div class="smalls-color title5 venue">Live at Smalls</div><span>Fri Nov 20</span> <span>9:00 PM</span></div>
</div>
<div class="event-display-today-and-tomorrow item"><a href="/events/3-kenny-davis-quartet/">Kenny</a>
  <div class="mezzrow-color title5 venue">Live at Mezzrow</div><span>Sat Nov 21</span> <span>6:00 PM</span></div>
"""


def _ev(venue, lat=None, lng=None):
    e = {"venue": venue}
    if lat is not None:
        e.update(lat=lat, lng=lng)
    return e


class DistinctVenues(unittest.TestCase):
    def test_sister_rooms_never_merge(self):
        self.assertTrue(T._distinct_venues("smalls jazz club", "mezzrow (new york, ny)", _ev("Smalls Jazz Club"), _ev("Mezzrow")))
        self.assertTrue(T._distinct_venues("mezzrow", "smalls jazz club (west village)", None, None))

    def test_far_apart_pins_are_different_places(self):
        birdland = _ev("Birdland", 40.7593, -73.9897)
        radio_city = _ev("Radio City Music Hall", 40.7600, -73.9800)
        self.assertTrue(T._distinct_venues("birdland", "radio city music hall (new york, ny)", birdland, radio_city))

    def test_same_place_aliases_still_merge(self):
        ballet = _ev("New York City Ballet", 40.7725, -73.9835)
        koch = _ev("David H. Koch Theater (Lincoln Center)", 40.7726, -73.9834)
        self.assertFalse(T._distinct_venues("new york city ballet", "david h. koch theater (lincoln center)", ballet, koch))
        self.assertFalse(T._distinct_venues("bar lunàtico", "lunatico", _ev("Bar LunÀtico"), _ev("Lunatico")))
        self.assertFalse(T._distinct_venues("jazz cultural", "jazzcultural (new york, ny)", None, None))
        self.assertFalse(T._distinct_venues("birdland", "birdland jazz club", None, None))

    def test_unpinned_listings_are_left_to_the_old_rules(self):
        self.assertFalse(T._distinct_venues("hotel chantelle", "the concord nyc", _ev("Hotel Chantelle"), {"venue": "The Concord NYC", "_venue_unknown": True}))


class SmallsLiveRooms(unittest.TestCase):
    def test_each_show_at_its_own_room(self):
        with mock.patch.object(S._SESSION, "get", return_value=mock.Mock(status_code=200, text=SMALLSLIVE_HTML)):
            evs = S.scrape_smalls_live("https://www.smallslive.com/", "ua")
        got = {e["url"].split("/")[-2]: (e["venue"], e["name"], e["date"][11:16]) for e in evs}
        self.assertEqual(got["1-jam-in-the-cafe"][0], "Jazzcultural")
        self.assertEqual(got["2-steve-slagle-quartet"], ("Smalls Jazz Club (West Village)", "Smalls Jazz: Steve Slagle Quartet", "21:00"))
        self.assertEqual(got["3-kenny-davis-quartet"], ("Mezzrow", "Kenny Davis Quartet", "18:00"))
        mezz = next(e for e in evs if e["venue"] == "Mezzrow")
        self.assertIn("163 W 10th", mezz["address"])
        self.assertNotIn("lat", mezz)  # not Smalls' pin


if __name__ == "__main__":
    unittest.main()
