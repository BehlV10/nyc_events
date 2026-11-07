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


class SquarespaceCalendars(unittest.TestCase):
    def _scrape(self, items, **kw):
        start = int((datetime.now(timezone.utc) + timedelta(days=3)).timestamp() * 1000)
        resp = mock.Mock(raise_for_status=mock.Mock(), json=mock.Mock(return_value={
            "upcoming": [dict({"startDate": start, "fullUrl": "/events/x"}, **i) for i in items]}))
        with mock.patch.object(scrapers._SESSION, "get", return_value=resp):
            return scrapers.scrape_squarespace_calendar("https://venue.example/events", "ua", **kw)

    def test_a_paid_show_isnt_called_free(self):
        """Every event on 25 Squarespace calendars was stamped "Free / No Cover"."""
        self.assertIsNone(self._scrape([{"title": "Jazz Quintet"}])[0]["price"])

    def test_reads_what_the_listing_says(self):
        self.assertEqual(self._scrape([{"title": "Blues Night", "excerpt": "<p>$20 cover</p>"}])[0]["price"], "$20")
        self.assertEqual(self._scrape([{"title": "Blues Night", "body": "<p>No cover!</p>"}])[0]["price"], "Free")

    def test_venue_and_address_can_be_set(self):
        e = self._scrape([{"title": "Show"}], venue="Terra Blues", address="149 Bleecker St")[0]
        self.assertEqual((e["venue"], e["address"]), ("Terra Blues", "149 Bleecker St"))

    def test_source_kwargs_are_accepted(self):
        import inspect
        for v in scrapers.DIRECT_CALENDARS:
            params = inspect.signature(v["scraper"]).parameters
            self.assertTrue(set(v["kwargs"]) <= set(params), v["name"])


class ComicStrip(unittest.TestCase):
    def test_organizer_is_listed(self):
        ids = {i for _k, i, _n, _c in scrapers._load_eventbrite_organizers()}
        self.assertIn("8100188167", ids)


if __name__ == "__main__":
    unittest.main()
