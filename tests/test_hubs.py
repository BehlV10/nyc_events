"""The Kids & Family and Markets & Festivals pages."""
import os
import re
import sys
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import edm_hub  # noqa: E402
import kids_hub  # noqa: E402
import scrapers  # noqa: E402
import seo  # noqa: E402
import template as T  # noqa: E402
from scrapers import EASTERN, category_bucket, is_market_or_festival  # noqa: E402


def _day_at(days, hour, minute=0):
    return (datetime.now(EASTERN) + timedelta(days=days)).replace(hour=hour, minute=minute, second=0, microsecond=0)


def _dated(sources):
    """{source name: [(title, when, extra fields)]} through the real render pipeline."""
    venues = []
    for name, rows in sources.items():
        events = [dict({"name": t, "date": w.astimezone(timezone.utc).isoformat(), "url": f"https://x.example/{name[:3]}{i}",
                        "venue": "Somewhere"}, **extra) for i, (t, w, extra) in enumerate(rows)]
        venues.append({"venue": name, "url": "https://x.example/", "error": None, "events": events})
    ctx = {}
    T.render_page({"generated_at": datetime.now(timezone.utc).isoformat(), "venues": venues}, split_deferred=True, context_out=ctx)
    return ctx["dated"]


class MarketClassification(unittest.TestCase):
    def test_markets_fairs_and_festivals(self):
        for name in ("Union Square Greenmarket", "Smorgasburg Williamsburg", "Brooklyn Flea @ DUMBO Archway", "Queens Night Market",
                     "9th Annual Wallabout Wonderland Holiday Market", "Grand Bazaar NYC: One of a Kind Bazaar",
                     "Hester Street Fair", "Craft Fair at the Armory", "NYC Halal Fest"):
            self.assertTrue(is_market_or_festival(name), name)

    def test_job_fairs_film_fests_and_calls_for_vendors_are_not(self):
        for name in ("Tech Job Fair", "College Fair at Baruch", "Brooklyn Film Festival Screening",
                     "Call for Vendors: Holiday Market", "Health Fair"):
            self.assertFalse(is_market_or_festival(name), name)

    def test_concert_feeds_dont_count(self):
        self.assertFalse(is_market_or_festival("All Ohio Balloon Festival 2026", "Songkick NYC Concerts"))
        self.assertFalse(is_market_or_festival("COLTRANE FESTIVAL I: Melissa Aldana", "Smoke Jazz Club"))
        self.assertTrue(is_market_or_festival("Hester Street Fair", "AllEvents NYC"))

    def test_is_a_default_on_bucket(self):
        self.assertEqual(category_bucket("markets"), "Markets & Festivals")
        self.assertNotIn("Markets & Festivals", T.DEFAULT_UNCHECKED_BUCKETS)
        self.assertIn("markets", scrapers.CATEGORY_STYLES)

    def test_classified_at_render_time_but_a_jazz_festival_stays_music(self):
        when = _day_at(3, 11)
        dated = _dated({"Some Feed": [("Union Square Greenmarket", when, {"category": "food"}),
                                      ("Jazz Festival at Birdland", when, {"category": "music"})]})
        cats = {e["name"]: e["category"] for _, evs in dated for e in evs}
        self.assertEqual(cats["Union Square Greenmarket"], "markets")
        self.assertEqual(cats["Jazz Festival at Birdland"], "music")


class MarketsHub(unittest.TestCase):
    def test_a_repeating_market_is_one_card_with_its_other_dates(self):
        rows = [("Union Square Greenmarket", _day_at(d, 8), {"category": "food", "venue": "Union Square"}) for d in (1, 3, 5, 8, 10, 12)]
        dated = _dated({"GrowNYC": rows})
        html = seo.render_hub_page("markets-festivals-nyc", dated)
        self.assertEqual(html.count('class="card'), 1)
        self.assertRegex(html, r"Also \w+, \w+ \d+ · \w+, \w+ \d+ · \w+, \w+ \d+ and 2 more dates\.")

    def test_is_listed_with_the_other_hubs(self):
        self.assertIn("markets-festivals-nyc", seo.HUBS)
        self.assertIn("kids-family-events-nyc", seo.HUBS)


class KidTags(unittest.TestCase):
    def test_ages_and_activity_from_the_title(self):
        self.assertEqual(kids_hub._kid_tags({"name": "Toddler Tales (ages 1.5-3)"}), (["toddler"], "story", "📚", "Ages 1.5–3"))
        self.assertEqual(kids_hub._kid_tags({"name": "Baby Laptime (prewalkers)"})[:2], (["baby"], "story"))
        self.assertEqual(kids_hub._kid_tags({"name": "Family Night Hike and Owl Prowl"})[:2], (["family"], "nature"))
        self.assertEqual(kids_hub._kid_tags({"name": "LEGO Club Grades 3-5"})[0], ["bigkid"])

    def test_from_the_description_when_the_title_says_nothing(self):
        self.assertEqual(kids_hub._kid_tags({"name": "Saturday Fun", "description": "For ages 3-5 and caregivers."})[0], ["preschool"])


class KidsHub(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        when = _day_at(2, 10, 30)
        family = {"category": "family"}
        cls.html = seo.render_hub_page("kids-family-events-nyc", _dated({"Brooklyn Children's Museum": [
            ("Toddler Tales (ages 1.5-3)", when, dict(family, venue="Brooklyn Children's Museum", address="145 Brooklyn Ave, Brooklyn, NY 11213")),
            ("Family Night Hike and Owl Prowl", when, dict(family, venue="Prospect Park Audubon Center", address="Prospect Park, Brooklyn, NY 11215", price="Free")),
            ("Puppet Show in Hoboken", when, dict(family, venue="Hoboken Library", address="500 Park Ave, Hoboken, NJ 07030")),
        ]}))

    def test_uses_the_kids_design_with_filters(self):
        self.assertIn('<body class="kids-hub">', self.html)
        self.assertIn('class="kids-filters"', self.html)

    def test_cards_carry_what_the_filters_need(self):
        self.assertRegex(self.html, r'data-age="toddler" data-kind="story" data-price="paid"')
        self.assertRegex(self.html, r'data-age="family" data-kind="nature" data-price="free"')

    def test_chips_only_for_what_exists(self):
        self.assertIn('data-val="toddler"', self.html)
        self.assertNotIn('data-val="bigkid"', self.html)
        self.assertIn('data-val="brooklyn"', self.html)
        self.assertNotIn('data-val="manhattan"', self.html)

    def test_outside_nyc_is_left_out_so_the_counts_agree(self):
        self.assertNotIn("Puppet Show in Hoboken", self.html)
        self.assertIn("2 activities", self.html)

    def test_filter_script_runs_after_the_cards(self):
        self.assertLess(self.html.rindex('class="hub-card'), self.html.index("var chips = document.querySelectorAll('.kid-chip')"))


class DjHub(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        when = _day_at(2, 23)
        cls.html = seo.render_hub_page("dj-techno-nights-nyc", _dated({"Nowadays": [
            ("Hard Techno All Night", when, {"category": "clubbing", "venue": "Nowadays", "address": "56-06 Cooper Ave, Queens, NY 11385"}),
            ("Reggaeton Rooftop Fridays", when, {"category": "clubbing", "venue": "Elsewhere", "address": "599 Johnson Ave, Brooklyn, NY 11237"}),
            ("Comedy Open Mic", when, {"category": "comedy", "venue": "Elsewhere", "address": "599 Johnson Ave, Brooklyn, NY 11237"}),
        ]}))

    def test_uses_the_neon_design_with_filters(self):
        self.assertIn('<body class="edm-hub">', self.html)
        self.assertIn('class="edm-filters"', self.html)
        self.assertNotIn("BOSTON", self.html.upper().replace("BOSTON_EVENTS", ""))

    def test_vibes_include_nyc_club_styles(self):
        self.assertIn('data-genre="techno" data-area="queens"', self.html)
        self.assertIn('data-genre="latin" data-area="brooklyn"', self.html)

    def test_comedy_stays_out(self):
        self.assertNotIn("Comedy Open Mic", self.html)

    def test_area_chips_only_for_boroughs_with_events(self):
        self.assertIn('data-group="area" data-val="queens"', self.html)
        self.assertNotIn('data-group="area" data-val="bronx"', self.html)

    def test_what_counts(self):
        self.assertTrue(edm_hub.is_edm_event({"name": "Some Party", "category": "clubbing"}))
        self.assertTrue(edm_hub.is_edm_event({"name": "Boiler Room", "category": "music", "genre": "electronic"}))
        self.assertFalse(edm_hub.is_edm_event({"name": "Blue Note Trio", "category": "music", "genre": "jazz_blues"}))
        self.assertFalse(edm_hub.is_edm_event({"name": "Karaoke Night", "category": "clubbing"}))


if __name__ == "__main__":
    unittest.main()
