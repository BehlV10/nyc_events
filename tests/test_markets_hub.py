"""Markets & Festivals hub and Christmas & Holiday Markets subpage tests for NYC Events."""
import os
import sys
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import markets_hub  # noqa: E402
import scrapers  # noqa: E402
import seo  # noqa: E402
import template  # noqa: E402
import venues_geo  # noqa: E402
from scrapers import EASTERN  # noqa: E402


def _ev(name, days=2, venue="Union Square Park", category="markets"):
    t = (datetime.now(EASTERN) + timedelta(days=days)).replace(hour=11, minute=0, second=0, microsecond=0)
    return {
        "name": name,
        "venue": venue,
        "category": category,
        "_time": t,
        "date": t.isoformat(),
        "url": "https://example.com/" + name.replace(" ", "-"),
        "_source_venue": "Test",
    }


class WhatCountsAsAMarket(unittest.TestCase):
    def test_markets_of_every_kind(self):
        for name, kind in [
            ("Union Square Greenmarket", "farmers"),
            ("Brooklyn Borough Hall Farmers Market", "farmers"),
            ("Down to Earth Park Slope Farmers Market", "farmers"),
            ("Bank of America Winter Village at Bryant Park (Holiday Shops)", "holiday"),
            ("Union Square Holiday Market", "holiday"),
            ("Grand Central Holiday Fair", "holiday"),
            ("Church of Sweden Christmas Market (Julbutik)", "holiday"),
            ("Brooklyn Flea", "flea"),
            ("Chelsea Flea Vintage Market", "flea"),
            ("FAD Market at Empire Stores", "craft"),
            ("Renegade Craft Fair NYC", "craft"),
            ("Queens Night Market", "night"),
            ("Smorgasburg Williamsburg", "night"),
            ("Hester Street Open Market", "other"),
        ]:
            e = {"name": name}
            self.assertTrue(template.is_market(e), name)
            self.assertEqual(template.market_type(e), kind, name)

    def test_places_named_market_and_non_markets_are_not(self):
        for name in (
            "Chelsea Market Food Tour",
            "Comedy Night at Time Out Market",
            "Techno Party at Market Hotel",
            "Cooking Class at Essex Market",
            "Stock Market Basics",
            "Digital Marketing Meetup",
            "College Fair",
            "NYC Tech Job Fair",
            "Farmers' Market Visit",
            "Lagers and Leaves: A Fall Festival",
            "Blue Note Jazz Festival",
        ):
            self.assertFalse(template.is_market({"name": name}), name)

    def test_market_held_at_a_market_place_still_counts(self):
        self.assertTrue(template.is_market({"name": "Harlem Night Market Holiday Edition at La Marqueta"}))
        self.assertTrue(template.is_market({"name": "Holiday Pop-Up Market at Chelsea Market"}))

    def test_festivals_with_stalls_count_and_shows_do_not(self):
        for name, cat, kind in [
            ("Queens Autumn Harvest Fest", "community", "festival"),
            ("Astoria Greek Food Fest 2026", "food", "festival"),
            ("Chinatown Mid-Autumn Festival", "community", "festival"),
            ("Stone Street Oktoberfest", "markets", "festival"),
            ("Brooklyn Winter Festival", "community", "holiday"),
        ]:
            e = {"name": name, "category": cat}
            self.assertTrue(template.is_vendor_festival(e), name)
            self.assertEqual(template.market_type(e), kind, name)
        for name, cat in [
            ("Blue Note Jazz Festival", "music"),
            ("New York Film Festival Screening", "community"),
            ("Craft Beer & Cider Festival", "food"),
            ("Rockefeller Center Tree Lighting", "community"),
            ("NYC Tech Job Fair", "community"),
            ("Brooklyn Book Festival Author Panel", "community"),
            ("Block Party (ages 2 and up)", "community"),
            ("Slug Fest", "outdoors"),
        ]:
            self.assertFalse(template.is_vendor_festival({"name": name, "category": cat}), name)

    def test_nyc_holiday_markets_covered_and_geocoded(self):
        """Verify all 27 NYC Christmas & Holiday market scrapers emit valid holiday markets with coordinates."""
        scraper_fns = [
            scrapers.scrape_bryant_park_winter_village,
            scrapers.scrape_union_square_holiday_market,
            scrapers.scrape_columbus_circle_holiday_market,
            scrapers.scrape_grand_central_holiday_fair,
            scrapers.scrape_macys_holiday_square,
            scrapers.scrape_oculus_holiday_market,
            scrapers.scrape_fad_market_empire_stores,
            scrapers.scrape_fad_market_cobble_hill,
            scrapers.scrape_fad_market_invisible_dog,
            scrapers.scrape_wallabout_wonderland,
            scrapers.scrape_brooklyn_flea_holiday_dumbo,
            scrapers.scrape_chelsea_flea_holiday,
            scrapers.scrape_grand_bazaar_holiday,
            scrapers.scrape_renegade_craft_fair_nyc,
            scrapers.scrape_crafts_at_the_cathedral,
            scrapers.scrape_oddities_flea_holiday,
            scrapers.scrape_church_of_sweden_julbutik,
            scrapers.scrape_norwegian_seamens_julemarked,
            scrapers.scrape_harlem_night_market,
            scrapers.scrape_mcny_holiday_market,
            scrapers.scrape_williamsburg_winter_village,
            scrapers.scrape_city_point_holiday_market,
            scrapers.scrape_arts_gowanus_holiday_bazaar,
            scrapers.scrape_red_hook_holiday_market,
            scrapers.scrape_made_bush_terminal_holiday,
            scrapers.scrape_artists_and_fleas_holiday,
            scrapers.scrape_astoria_holiday_market,
            scrapers.scrape_queens_craft_brigade_holiday,
            scrapers.scrape_culture_lab_lic_holiday_market,
            scrapers.scrape_snug_harbor_holiday_hop,
            scrapers.scrape_bartow_pell_holiday_bazaar,
            scrapers.scrape_wave_hill_holiday_market,
        ]
        registered_scrapers = {v["scraper"] for v in scrapers.VENUES}
        with patch.object(scrapers, "fetch_soup", side_effect= RuntimeError("offline test")):
            for fn in scraper_fns:
                self.assertIn(fn, registered_scrapers, f"{fn.__name__} must be registered in scrapers.VENUES")
                evs = fn("https://example.com", scrapers.UA_CHROME)
                self.assertTrue(len(evs) >= 1, f"{fn.__name__} returned no events")
                first = evs[0]
                self.assertTrue(
                    markets_hub.is_market(first) or markets_hub.is_vendor_festival(first),
                    f"{first['name']} should count as a market",
                )
                self.assertEqual(markets_hub.market_type(first), "holiday", f"{first['name']} should be holiday type")
                self.assertTrue(first.get("end"), f"{first['name']} should include end time")
                geo = venues_geo.resolve_event_geo(first)
                self.assertIsNotNone(geo, f"{first['venue']} ({first['name']}) must resolve to coordinates")


class MarketsPage(unittest.TestCase):
    def setUp(self):
        events = [
            _ev("Union Square Greenmarket", 1, venue="Union Square Park"),
            _ev("Union Square Greenmarket", 8, venue="Union Square Park"),
            _ev("Kids Holiday Market", 3, venue="Brooklyn Children's Museum", category="family"),
            _ev("Brooklyn Flea", 4, venue="Brooklyn Flea"),
            _ev("Blue Note Jazz Festival", 2, venue="Blue Note", category="music"),
            _ev("Chelsea Market Food Tour", 2, venue="Chelsea Market", category="community"),
            _ev("Queens Autumn Harvest Fest", 5, venue="Bohemian Hall & Beer Garden", category="community"),
        ]
        self.html = template.render_hub_page("markets-festivals-nyc", events, site_url="https://example.com")

    def test_lists_markets_and_stall_festivals_and_nothing_else(self):
        self.assertIn("Kids Holiday Market", self.html)
        self.assertIn("Queens Autumn Harvest Fest", self.html)
        self.assertNotIn("Blue Note Jazz Festival", self.html)
        self.assertNotIn("Chelsea Market Food Tour", self.html)

    def test_weekly_market_shows_on_each_of_its_days(self):
        self.assertEqual(self.html.count(">Union Square Greenmarket<"), 2)
        self.assertNotIn('class="mk-daily"', self.html)

    def test_days_are_split_by_borough(self):
        self.assertIn('class="mk-city" data-city=', self.html)
        self.assertIn('class="mk-city-pill', self.html)
        self.assertIn("mk-hero-art", self.html)

    def test_kind_chips_only_for_kinds_present(self):
        self.assertIn('data-mtype="farmers"', self.html)
        self.assertIn('class="hub-city-chip hub-type-chip" data-mtype="holiday"', self.html)
        self.assertIn('class="hub-city-chip hub-type-chip" data-mtype="flea"', self.html)
        self.assertIn('class="hub-city-chip hub-type-chip" data-mtype="festival"', self.html)
        self.assertNotIn('class="hub-city-chip hub-type-chip" data-mtype="night"', self.html)
        self.assertIn("state.type", self.html)

    def test_hero_bar_has_full_calendar_button_on_right(self):
        self.assertIn('class="mk-hero-bar"', self.html)
        self.assertIn('>Full calendar →</a>', self.html)


class ChristmasMarketsPage(unittest.TestCase):
    def test_christmas_markets_subpage_filters_to_holiday_markets(self):
        events = [
            _ev("Union Square Holiday Market", 2, venue="Union Square Park"),
            _ev("Bank of America Winter Village at Bryant Park (Holiday Shops)", 2, venue="Bryant Park"),
            _ev("Union Square Greenmarket", 2, venue="Union Square Park"),
            _ev("Smorgasburg Williamsburg", 3, venue="Smorgasburg Williamsburg"),
        ]
        html = seo.render_hub_page("christmas-markets-nyc", events, site_url="https://example.com")
        self.assertIn("Christmas &amp; Holiday Markets in NYC", html)
        self.assertIn("Union Square Holiday Market", html)
        self.assertIn("Bank of America Winter Village at Bryant Park", html)
        self.assertNotIn("Union Square Greenmarket", html)
        self.assertNotIn("Smorgasburg Williamsburg", html)


class DailyAndHours(unittest.TestCase):
    def _day(self, d, h=11, end_h=20):
        t = (datetime.now(EASTERN) + timedelta(days=d)).replace(hour=h, minute=0, second=0, microsecond=0)
        e = _ev("Union Square Holiday Market", d, venue="Union Square Park", category="markets")
        e.update(_time=t, date=t.isoformat(), end=t.replace(hour=end_h).isoformat())
        return e

    def test_a_market_open_every_day_is_one_card_up_top(self):
        holiday = [self._day(d) for d in range(1, 15) if d != 6]  # closed one day
        weekly = [_ev("Union Square Greenmarket", d) for d in (2, 9)]
        events = sorted(holiday + weekly, key=lambda e: e["_time"])
        daily, dated = template._markets_split(events)
        self.assertEqual([e["name"] for e in daily], ["Union Square Holiday Market"])
        self.assertEqual([e["name"] for e in dated], ["Union Square Greenmarket"] * 2)
        html = template.render_hub_page("markets-festivals-nyc", events, site_url="https://example.com")
        self.assertEqual(html.count(">Union Square Holiday Market<"), 1)
        self.assertLess(html.index('class="mk-daily"'), html.index(">Union Square Greenmarket<"))
        closed = (datetime.now(EASTERN) + timedelta(days=6)).strftime("%b %-d")
        self.assertIn("Most days through", html)
        self.assertIn(f"closed {closed}", html)
        self.assertIn("11 am – 8 pm", html)

    def test_weekends_only_is_not_daily(self):
        events = [self._day(d) for d in range(1, 29) if d % 7 in (5, 6)]
        daily, dated = template._markets_split(events)
        self.assertEqual((len(daily), len(dated)), (0, len(events)))

    def test_hours(self):
        t = datetime(2026, 11, 14, 10, 0, tzinfo=EASTERN)
        h = lambda **kw: template._market_hours({"_time": t, "date": t.isoformat(), **kw})
        self.assertEqual(h(end=t.replace(hour=16).isoformat()), "10 am – 4 pm")
        self.assertEqual(h(end=t.replace(hour=11, minute=30).isoformat()), "10 – 11:30 am")
        self.assertEqual(h(), "10 am")
        self.assertEqual(h(end=(t - timedelta(hours=1)).isoformat()), "10 am")
        self.assertEqual(template._market_hours({"_time": t, "date": "2026-11-14"}), "Time TBA")


class NearMeAndGeocoding(unittest.TestCase):
    def test_near_me_origins_and_sorting_structure(self):
        t1 = datetime.now(EASTERN) + timedelta(days=2)
        t2 = datetime.now(EASTERN) + timedelta(days=3)
        ev1 = _ev("Union Square Holiday Market", 2, venue="Union Square Park", category="markets")
        ev1.update(_time=t1, date=t1.isoformat())
        ev2 = _ev("Brooklyn Flea Holiday Market", 3, venue="Brooklyn Flea", category="markets")
        ev2.update(_time=t2, date=t2.isoformat())
        html = template.render_hub_page("markets-festivals-nyc", [ev1, ev2], site_url="https://example.com")

        self.assertIn("Midtown / Bryant Park", html)
        self.assertIn("40.7536,-73.9832", html)
        self.assertIn('class="mk-day-section"', html)
        self.assertIn('class="mk-day-dist-grid mk-grid" hidden', html)
        self.assertIn("document.querySelectorAll('.mk-day-section').forEach", html)
        self.assertIn("sec.querySelector('.mk-day-dist-grid')", html)
        self.assertIn("c._origParent.insertBefore(c, c._origNext || null)", html)

    def test_known_and_unknown_venue_coordinates(self):
        t = datetime.now(EASTERN) + timedelta(days=1)
        known_ev = _ev("Bryant Park Winter Village", 1, venue="Bryant Park", category="markets")
        known_ev.update(_time=t, date=t.isoformat())
        card_html = template._render_market_card(known_ev, "2026-11-13")
        self.assertIn('data-lat="40.7536"', card_html)
        self.assertIn('data-lng="-73.9832"', card_html)

        unknown_ev = _ev("Mysterious Pop-Up Flea", 1, venue="Nowhere In Particular 123", category="markets")
        unknown_ev.update(_time=t, date=t.isoformat())
        card_unknown = template._render_market_card(unknown_ev, "2026-11-13")
        self.assertIn('data-lat=""', card_unknown)
        self.assertIn('data-lng=""', card_unknown)

    def test_tba_date_markets_stay_at_bottom(self):
        t = datetime.now(EASTERN) + timedelta(days=1)
        dated_ev = _ev("Tomorrow Greenmarket", 1, venue="Union Square Park", category="markets")
        dated_ev.update(_time=t, date=t.isoformat())
        tba_ev = _ev("Future Holiday Market TBA", 0, venue="Bryant Park", category="markets")
        tba_ev.update(_time=None, date=None)
        html = template.render_hub_page("markets-festivals-nyc", [dated_ev, tba_ev], site_url="https://example.com")
        self.assertIn('id="tba"', html)
        self.assertIn("Date TBA", html)
        self.assertLess(html.index(">Tomorrow Greenmarket<"), html.index(">Future Holiday Market TBA<"))


if __name__ == "__main__":
    unittest.main()
