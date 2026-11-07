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


class RetiredDonycFeeds(unittest.TestCase):
    def test_venues_with_a_better_direct_feed_dont_use_donyc(self):
        urls = {v["url"] for v in scrapers.VENUES}
        for slug in ("saint-vitus", "public-records", "terra-blues", "nebula"):
            self.assertFalse([u for u in urls if u.startswith(f"https://donyc.com/venues/{slug}")], slug)

    def test_venues_that_sell_beyond_dice_keep_it(self):
        urls = " ".join(v["url"] for v in scrapers.VENUES)
        self.assertIn("donyc.com/venues/baby-s-all-right", urls)
        self.assertIn("donyc.com/venues/drom", urls)

    def test_citywide_feed_stays_as_a_safety_net(self):
        self.assertTrue([v for v in scrapers.VENUES if v["scraper"] is scrapers.scrape_donyc_calendar])


class ComicStrip(unittest.TestCase):
    def test_organizer_is_listed(self):
        ids = {i for _k, i, _n, _c in scrapers._load_eventbrite_organizers()}
        self.assertIn("8100188167", ids)


class DonycDetails(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.path = os.path.join(self.dir.name, "details.json")
        self.when = (datetime.now(timezone.utc) + timedelta(days=4)).isoformat()

    def _event(self, name, p="/events/2026/12/1/a", **kw):
        return dict({"name": name, "date": self.when, "url": "https://venue.example/", "price": None, "_donyc_path": p}, **kw)

    def _run(self, results, answers, **kw):
        self.calls = []

        def fake(path, ua):
            self.calls.append(path)
            answer = answers.get(path)
            if isinstance(answer, Exception):
                raise answer
            return answer

        with mock.patch.object(scrapers, "_donyc_detail", side_effect=fake), mock.patch("builtins.print"):
            scrapers._enrich_donyc_events(results, ua="ua", path=self.path, **kw)
        return results

    def _donyc(self, *events):
        return {"venue": "Some Venue", "url": "https://donyc.com/venues/x", "events": list(events)}

    def test_adds_the_real_link_and_price(self):
        e = self._event("Lera Lynn")
        self._run([self._donyc(e)], {"/events/2026/12/1/a": {"url": "https://ticketweb.com/e/1", "info": "$28, 21+", "free": False, "sold_out": False}})
        self.assertEqual((e["url"], e["ticket_url"], e["price"]), ("https://ticketweb.com/e/1", "https://ticketweb.com/e/1", "$28"))
        self.assertNotIn("_donyc_path", e)

    def test_an_age_limit_isnt_a_price(self):
        e = self._event("Show")
        self._run([self._donyc(e)], {"/events/2026/12/1/a": {"url": None, "info": "21+", "free": False, "sold_out": False}})
        self.assertIsNone(e["price"])

    def test_free_and_sold_out_flags(self):
        free, gone = self._event("A"), self._event("B", p="/b", price="$20")
        self._run([self._donyc(free, gone)], {"/events/2026/12/1/a": {"free": True}, "/b": {"sold_out": True}})
        self.assertEqual((free["price"], gone["price"]), ("Free", "$20 (sold out)"))

    def test_skips_events_another_source_lists(self):
        e = self._event("Big Show")
        self._run([self._donyc(e), {"venue": "Ticketmaster NYC", "url": "https://ticketmaster.com/", "events": [{"name": "big show", "date": self.when}]}], {})
        self.assertEqual(self.calls, [])

    def test_a_later_run_uses_what_it_learned_without_asking_again(self):
        answers = {"/events/2026/12/1/a": {"url": "https://axs.com/e", "info": None, "free": False, "sold_out": False}}
        self._run([self._donyc(self._event("Show"))], answers)
        again = self._event("Show")
        self._run([self._donyc(again)], {})
        self.assertEqual(self.calls, [])
        self.assertEqual(again["url"], "https://axs.com/e")

    def test_an_event_in_two_feeds_is_asked_once_and_both_improve(self):
        a, b = self._event("Show"), self._event("Show")
        self._run([self._donyc(a), self._donyc(b)], {"/events/2026/12/1/a": {"url": "https://axs.com/e"}})
        self.assertEqual(len(self.calls), 1)
        self.assertEqual((a["url"], b["url"]), ("https://axs.com/e", "https://axs.com/e"))

    def test_soonest_first_and_capped(self):
        soon = self._event("Soon", p="/soon", date=(datetime.now(timezone.utc) + timedelta(days=1)).isoformat())
        later = self._event("Later", p="/later")
        self._run([self._donyc(later, soon)], {"/soon": {}, "/later": {}}, limit=1)
        self.assertEqual(self.calls, ["/soon"])

    def test_stops_when_donyc_refuses(self):
        a, b = self._event("A", p="/a"), self._event("B", p="/b")
        self._run([self._donyc(a, b)], {"/a": scrapers.SiteRefused("403"), "/b": {}})
        self.assertEqual(len(self.calls), 1)

    def test_reads_sveltekit_data_file(self):
        payload = {"nodes": [None, {"type": "data", "data": [
            {"event": 1}, {"buy_tickets": 2, "ticket_info": 3, "free_event": 4, "tickets_sold_out": 4},
            "https://axs.com/e", "$28, 21+", False]}]}
        resp = mock.Mock(raise_for_status=mock.Mock(), json=mock.Mock(return_value=payload))
        with mock.patch.object(scrapers._SESSION, "get", return_value=resp):
            d = scrapers._donyc_detail("/events/x", "ua")
        self.assertEqual(d, {"url": "https://axs.com/e", "info": "$28, 21+", "free": False, "sold_out": False})

    def test_paths_are_captured_from_list_pages(self):
        page = ('{id:1,type:"event",title:"Show",permalink:"/events/2030/1/1/show-tickets",tz_adjusted_begin_time:"2030-01-01T20:00:00-05:00",'
                'category:"Music",genres:[],venue:{id:2,title:"Room",district_id:1,district_name:"X",area_id:1,area_name:"Y"}}')
        ev = scrapers._parse_donyc_svelte(page, datetime(2026, 1, 1, tzinfo=timezone.utc))
        self.assertEqual(ev[0]["_donyc_path"], "/events/2030/1/1/show-tickets")


if __name__ == "__main__":
    unittest.main()
