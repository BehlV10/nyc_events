"""Deals & Specials holds menu specials and pure ads, not events that mention a deal."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scrapers import is_deal_event, special_note  # noqa: E402
import template as T  # noqa: E402


class DealOrEvent(unittest.TestCase):
    def test_specials_and_ads_are_deals(self):
        for name in ("Happy Hour Deals!", "MARTES CHINGONES (TACO TUESDAYS)", "Gift Certificates",
                     "Follow us and receive a complimentary $10 discount on your first visit",
                     "20% off all apps this week", "Discounted drinks all night"):
            self.assertTrue(is_deal_event(name, "https://allevents.in/new-york/x"), name)

    def test_events_that_mention_a_deal_are_not(self):
        for name in ("PIT ENSEMBLES: Psychopomp & Half Priced Drinks", "Discount Philosophy",
                     "World Team Tennis - 2-Day Ticket - 20% Discount", "Coffee Walk & Impact Kitchen DISCOUNT",
                     "TACO TUESDAY & KARAOKE / THE CELTIC KNOT", "MEETUP SPECIAL 25% OFF ABSOLUTE BEGINNER TANGO CLASSES",
                     "Mineola Tuesday Book Swap for Gift Cards"):
            self.assertFalse(is_deal_event(name), name)

    def test_specials_posted_on_rsvp_platforms_are_events(self):
        self.assertFalse(is_deal_event("Taco Tuesday hoboken", "https://www.meetup.com/find/?keywords=social"))
        self.assertFalse(is_deal_event("TACO TUESDAY AT SOUTH BEACH ASTORIA",
                                       "https://www.eventbrite.com/api/v3/organizers/1/events/"))
        self.assertTrue(is_deal_event("Gift Certificates", "https://www.eventbrite.com/e/1"), "ads go to deals anywhere")

    def test_a_feed_filing_karaoke_under_deals_is_overruled(self):
        out = T.group_by_date([{"venue": "Myrtle Avenue Bar Events", "url": "https://myrtleavenue.org/wp-json/tribe",
                                "events": [{"name": "Karaoke Night", "date": "2099-11-12T01:00:00+00:00",
                                            "venue": "Somethin' on Myrtle", "category": "deals",
                                            "description": "Sing a little and enjoy $8 shots, $8 margaritas"}]}])
        flat = repr(out)
        self.assertIn("Karaoke Night", flat)
        self.assertNotIn("'category': 'deals'", flat)

    def test_special_note(self):
        self.assertEqual(special_note("Karaoke ... enjoy great specials- $8 shots, $8 margaritas"), "$8 shots")
        self.assertIsNone(special_note("Folk Night with the Hollow Pines"))


if __name__ == "__main__":
    unittest.main()
