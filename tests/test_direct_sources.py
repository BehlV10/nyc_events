"""Direct sources that replace DoNYC's capped venue pages."""
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import scrapers  # noqa: E402


def _dice_event(name="Torche, Spotlights", start="2026-11-14T19:00:00-05:00", amount=None, amount_from=2500, event_id="6a7b"):
    return {"id": event_id, "name": name, "dates": {"event_start_date": start},
            "price": {"amount": amount, "amount_from": amount_from},
            "venues": [{"name": "Saint Vitus", "address": "1120 Manhattan Ave, Brooklyn, New York 11222, United States",
                        "city": {"name": "Brooklyn"}}]}


class DiceVenuePages(unittest.TestCase):
    def _scrape(self, events):
        props = {"profile": {"sections": [{"events": events}]}}
        with mock.patch.object(scrapers, "_dice_page_props", return_value=props):
            return scrapers.scrape_dice_venue("https://dice.fm/venue/saint-vitus-rgrv", "ua")

    def test_reads_price_address_and_ticket_link(self):
        e = self._scrape([_dice_event()])[0]
        self.assertEqual(e["name"], "Torche, Spotlights")
        self.assertEqual(e["price"], "$25")
        self.assertEqual(e["url"], "https://dice.fm/event/6a7b")
        self.assertIn("1120 Manhattan Ave", e["address"])
        self.assertEqual(e["venue"], "Saint Vitus (Brooklyn)")
        self.assertEqual(e["date"], "2026-11-15T00:00:00+00:00")

    def test_free_and_unpriced(self):
        self.assertEqual(self._scrape([_dice_event(amount=0)])[0]["price"], "Free")
        self.assertIsNone(self._scrape([_dice_event(amount_from=None)])[0]["price"])

    def test_dates_ending_in_z_parse(self):
        self.assertEqual(self._scrape([_dice_event(start="2026-11-15T00:00:00Z")])[0]["date"], "2026-11-15T00:00:00+00:00")

    def test_a_listing_with_no_start_is_skipped(self):
        self.assertEqual(self._scrape([{"name": "No date", "dates": {}}]), [])

    def test_an_event_in_two_sections_appears_once(self):
        self.assertEqual(len(self._scrape([_dice_event(), _dice_event()])), 1)

    def test_venues_are_registered_with_unique_names(self):
        names = [v["name"] for v in scrapers._ALL_VENUES]
        dice = [v for v in scrapers.VENUES if v["scraper"] is scrapers.scrape_dice_venue]
        self.assertGreaterEqual(len(dice), 30)
        self.assertEqual(len(names), len(set(names)), "the cache is keyed by source name")

    def test_paced(self):
        self.assertEqual(scrapers._host_policy("dice.fm"), (2, 1.0))


class CitywideDiceStillWorks(unittest.TestCase):
    def test_shared_parser(self):
        with mock.patch.object(scrapers, "_dice_events_from_page", return_value=[_dice_event()]), \
                mock.patch.object(scrapers, "_dice_genre_suffixes", return_value=[]), mock.patch.object(scrapers.time, "sleep"):
            events = scrapers.scrape_dice_nyc("u", "ua")
        self.assertEqual({e["name"] for e in events}, {"Torche, Spotlights"})


if __name__ == "__main__":
    unittest.main()
