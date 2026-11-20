"""Tests for data-quality features ported from boston_events (#133, #135, #142, #149)."""
import os
import sys
import unittest
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import scrapers as S  # noqa: E402
import template as T  # noqa: E402


class TestKidsByAge(unittest.TestCase):
    def test_kids_classes(self):
        for name in (
            "Primary Ballet I (Ages 4-6)",
            "Ballet I/II (Ages 8+)",
            "Creative Movement (Ages 6-7)",
            "Art Lab (Ages 6–12)",
            "Drawing Workshop (Ages 8-14)",
            "Robotics for Grades K-2",
        ):
            self.assertTrue(S.is_kid_family_event(name), name)

    def test_teen_and_adult_ranges_stay_put(self):
        for name in (
            "Ballet IV/V (Ages 14+)",
            "Contemporary (Ages 13+)",
            "Jazz (Ages 11+)",
            "Svdden Death (Ages 18+)",
            "Comedy Night - Ages 21+",
            "Tour Stage Ages 21 and up",
        ):
            self.assertFalse(S.is_kid_family_event(name), name)


class TestWithSupport(unittest.TestCase):
    def test_appends_openers(self):
        self.assertEqual(
            S._with_support("Sweet Pill", "Heart to Gold, Stereosity"),
            "Sweet Pill with Heart to Gold, Stereosity",
        )

    def test_skips_acts_already_in_title_and_empty(self):
        self.assertEqual(S._with_support("Jessie Mazin, Anya True", ["Jessie Mazin", "Anya True "]), "Jessie Mazin, Anya True")
        self.assertEqual(S._with_support("Elysium", ""), "Elysium")
        self.assertEqual(S._with_support("Crazy Train", ["Crazy Train", "Wolf's Blood"]), "Crazy Train with Wolf's Blood")

    def test_cleans_with_and_opening_words(self):
        self.assertEqual(
            S._with_support("UNMUTED - a benefit concert", "Illiterate Light, with Twice-A-Day Ray opening"),
            "UNMUTED - a benefit concert with Illiterate Light, Twice-A-Day Ray",
        )

    def test_overlong_lineup_left_off(self):
        self.assertEqual(S._with_support("Fest", [f"Band {i} Long Name Here" for i in range(8)]), "Fest")

    def test_still_merges_with_plain_title(self):
        self.assertEqual(
            T._normalize_title_head("Sweet Pill with Heart to Gold, Stereosity", venue="Bowery Ballroom"),
            T._normalize_title_head("Sweet Pill", venue="Bowery Ballroom"),
        )


class TestMisdatedAggregator(unittest.TestCase):
    @staticmethod
    def _ev(name, venue, source):
        return {"name": name, "venue": venue, "_source_venue": source}

    def test_drops_misdated_aggregator_when_own_calendar_contradicts(self):
        d16, d23 = date(2026, 11, 16), date(2026, 11, 23)
        buckets = {
            d16: [
                self._ev("Drag Bingo", "Club Cumming", "Club Cumming"),
                self._ev("Queer Line & Partner Dancing", "Club Cumming", "DoNYC Citywide"),
                self._ev("Some Show Venue Doesn't List", "Club Cumming", "DoNYC Citywide"),
            ],
            d23: [
                self._ev("Queer Line & Partner Dancing", "Club Cumming (Main Room)", "Club Cumming"),
                self._ev("Queer Line & Partner Dancing", "Club Cumming", "DoNYC Citywide"),
            ],
        }
        self.assertEqual(T._drop_misdated_aggregator_listings(buckets), 1)
        self.assertEqual([e["name"] for e in buckets[d16]], ["Drag Bingo", "Some Show Venue Doesn't List"])
        self.assertEqual(len(buckets[d23]), 2)

    def test_renamed_same_day_listing_is_kept(self):
        d1, d2 = date(2026, 11, 24), date(2026, 11, 17)
        buckets = {
            d1: [
                self._ev("Comedy Gold w/ host Sarah Fitz", "The Bell House", "The Bell House"),
                self._ev("Comedy Gold Stand-Up Showcase", "The Bell House", "DoNYC Citywide"),
            ],
            d2: [
                self._ev("Comedy Gold Stand-Up Showcase", "The Bell House", "The Bell House"),
            ],
        }
        self.assertEqual(T._drop_misdated_aggregator_listings(buckets), 0)

    def test_meetup_untouched(self):
        d1, d2 = date(2026, 11, 16), date(2026, 11, 23)
        buckets = {
            d1: [
                self._ev("Other Show", "The Bell House", "The Bell House"),
                self._ev("Queer Line & Partner Dancing", "The Bell House", "Meetup: Dance NYC"),
            ],
            d2: [self._ev("Queer Line & Partner Dancing", "The Bell House", "The Bell House")],
        }
        self.assertEqual(T._drop_misdated_aggregator_listings(buckets), 0)


class TestResaleAlsoOnDropped(unittest.TestCase):
    def test_resale_links_not_shown_in_also_on(self):
        when = (datetime.now(S.EASTERN) + timedelta(days=1)).replace(hour=20, minute=0, second=0, microsecond=0)
        iso = when.astimezone(timezone.utc).isoformat()
        payload = {
            "venues": [
                {
                    "venue": "Brooklyn Steel",
                    "url": "https://www.bowerypresents.com",
                    "events": [
                        {"name": "Japanese Breakfast", "venue": "Brooklyn Steel", "date": iso, "category": "music",
                         "url": "https://www.axs.com/events/12345"},
                    ],
                },
                {
                    "venue": "SeatGeek NYC",
                    "url": "https://seatgeek.com",
                    "events": [
                        {"name": "Japanese Breakfast", "venue": "Brooklyn Steel", "date": iso, "category": "music",
                         "url": "https://seatgeek.com/japanese-breakfast-tickets/1"},
                    ],
                },
                {
                    "venue": "Ticketmaster NYC",
                    "url": "https://www.ticketmaster.com",
                    "events": [
                        {"name": "Japanese Breakfast", "venue": "Brooklyn Steel", "date": iso, "category": "music",
                         "url": "https://www.ticketmaster.com/event/abc"},
                    ],
                },
            ]
        }
        html = T.render_page(payload)
        self.assertIn("https://www.axs.com/events/12345", html)
        self.assertIn("also on", html)
        self.assertIn("Ticketmaster", html)
        self.assertNotIn("seatgeek.com/japanese-breakfast-tickets/1", html)


if __name__ == "__main__":
    unittest.main()
