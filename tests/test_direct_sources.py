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
        retired_slugs = (
            "saint-vitus", "public-records", "terra-blues", "nebula", "wonderville", "mood-ring",
            "the-red-pavilion", "3-dollar-bill", "brooklyn-bowl", "good-room", "music-hall-of-williamsburg",
            "brooklyn-steel", "kings-theatre", "the-sultan-room", "pioneer-works", "the-brooklyn-monarch",
            "the-meadows", "under-the-k-bridge-park", "lunatico", "starr-bar", "st-mazie",
            "brooklyn-comedy-collective-pig-pen", "brooklyn-art-haus", "alamo-drafthouse",
            "forest-hills-stadium", "noguchi-museum", "flushing-town-hall",
            "lehman-center-for-the-performing-arts", "webster-hall", "terminal-5", "racket-nyc",
            "blue-note-jazz-club", "caveat", "the-town-hall", "cafe-wha", "sid-gold-s-request-room",
            "groove", "new-york-comedy-club-east-village", "the-cooper-union", "somewhere-nowhere",
            "new-york-comedy-club-midtown", "the-broadway-comedy-club", "the-paley-center-for-media",
            "chamber-music-society-of-lincoln-center", "new-york-comedy-club-upper-west-side",
            "comic-strip-live-nyc", "shrine", "silvana-nyc", "ifc-center", "nublu-151",
            "eastville-comedy-club", "house-of-yes", "national-sawdust", "pianos", "berlin",
            "barclays-center", "baby-s-all-right", "basement-ny", "roulette", "liz-s-book_bar",
            "moma-ps1", "yankee-stadium", "st-george-theatre", "bowery-ballroom", "mercury-lounge",
            "david-rubenstein-atrium-at-lincoln-center", "the-new-school", "mannes-school-of-music",
            "apollo-theater", "madison-square-garden", "radio-city-music-hall", "beacon-theatre",
            "sony-hall", "palladium-times-square", "soho-playhouse-nyc", "city-winery",
            "donttellmama", "kaufman-music-center", "united-palace", "kgb-bar", "nitehawk-cinema",
            "drom", "tv-eye", "market-hotel", "avant-gardner", "the-brooklyn-mirage", "eris-deep-space",
            "old-man-hustle-bklyn-comedy-club", "crown-hill-theater", "brooklyn-storehouse",
            "le-poisson-rouge", "bowery-palace", "the-rooftop-at-pier-17", "marquee-new-york",
            "the-center", "duane-park", "new-york-city-ballet", "lincoln-center-theater",
            "film-at-lincoln-center", "joes-pub", "arlenes-grocery",
        )
        for slug in retired_slugs:
            self.assertFalse([u for u in urls if u.startswith(f"https://donyc.com/venues/{slug}")], slug)

    def test_baby_s_all_right_and_drom_sell_via_dice(self):
        paths = {path for _name, path in scrapers.DICE_VENUE_PAGES}
        self.assertIn("babys-all-right-g7qb", paths)
        self.assertIn("drom-megw", paths)
        self.assertIn("basement-e776", paths)
        self.assertIn("marquee-new-york-qqwy", paths)

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


class BoweryPresentsTests(unittest.TestCase):
    def test_parses_shows(self):
        sample = {
            "events": [
                {
                    "title": {"eventTitleText": "The National"},
                    "eventDateTimeISO": "2027-02-18T20:00:00-05:00",
                    "ticketing": {"eventUrl": "https://www.axs.com/events/123/tickets"},
                    "ticketPriceLow": "$45",
                    "venue": {
                        "title": "Brooklyn Steel",
                        "address_line": "319 Frost Street, Brooklyn, NY 11222",
                        "city": "Brooklyn",
                        "state": "NY",
                    },
                }
            ]
        }
        resp = mock.Mock(status_code=200, json=mock.Mock(return_value=sample))
        with mock.patch.object(scrapers._SESSION, "get", return_value=resp):
            events = scrapers.scrape_bowery_presents(None, "ua")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["name"], "The National")
        self.assertEqual(events[0]["venue"], "Brooklyn Steel")
        self.assertEqual(events[0]["price"], "$45")
        self.assertEqual(events[0]["url"], "https://www.axs.com/events/123/tickets")


class AlamoDrafthouseTests(unittest.TestCase):
    def test_parses_sessions(self):
        sample = {
            "data": {
                "presentations": [{"slug": "parasite-2019", "show": {"title": "Parasite"}}],
                "market": [{
                    "cinemas": [{
                        "id": "2101", "name": "Downtown Brooklyn",
                        "street1": "445 Albee Square West", "city": "Brooklyn", "state": "NY", "postalCode": "11201"
                    }]
                }],
                "sessions": [{
                    "presentationSlug": "parasite-2019",
                    "cinemaId": "2101",
                    "showTimeClt": "2027-02-18T19:30:00"
                }]
            }
        }
        resp = mock.Mock(status_code=200, json=mock.Mock(return_value=sample))
        with mock.patch.object(scrapers._SESSION, "get", return_value=resp):
            events = scrapers.scrape_alamo_drafthouse(None, "ua")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["name"], "Parasite")
        self.assertEqual(events[0]["venue"], "Alamo Drafthouse (Downtown Brooklyn)")
        self.assertIn("Albee Square", events[0]["address"])
        self.assertIn("drafthouse.com/nyc/show/parasite-2019", events[0]["url"])


class BlueNoteTests(unittest.TestCase):
    def test_parses_show_groups(self):
        html = """
        <li class="show-group">
            <h2>Vic Mensa Live</h2>
            <ul class="group-events">
                <li class="event">
                    <time>
                        <span class="day">Tue, Dec 15</span>
                        <span class="time">8:00 PM</span>
                    </time>
                    <a class="buy-tickets" href="https://ticketweb.com/event/123">Buy Tickets</a>
                </li>
            </ul>
        </li>
        """
        resp = mock.Mock(status_code=200, text=html)
        with mock.patch.object(scrapers._SESSION, "get", return_value=resp):
            events = scrapers.scrape_bluenote(None, "ua")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["name"], "Vic Mensa Live")
        self.assertEqual(events[0]["venue"], "Blue Note Jazz Club")
        self.assertEqual(events[0]["url"], "https://ticketweb.com/event/123")


class BrooklynBowlTests(unittest.TestCase):
    def test_parses_event_items(self):
        html = """
        <div class="eventItem entry clearfix">
            <h3>The Roots Live</h3>
            <div class="date">Dec 20</div>
            <div class="time">Show: 8:00 PM</div>
            <a class="tickets" href="https://ticketmaster.com/event/456">Tickets</a>
        </div>
        """
        resp = mock.Mock(status_code=200, text=html)
        with mock.patch.object(scrapers._SESSION, "get", return_value=resp):
            events = scrapers.scrape_brooklyn_bowl(None, "ua")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["name"], "The Roots Live")
        self.assertEqual(events[0]["venue"], "Brooklyn Bowl")
        self.assertEqual(events[0]["url"], "https://ticketmaster.com/event/456")


class NewSchoolTests(unittest.TestCase):
    def test_parses_algolia_hits(self):
        payload = {
            "hits": [
                {
                    "title": "Mannes Orchestra at Alice Tully Hall",
                    "first_date": "2026-12-05T19:30:00-05:00",
                    "location_name": "Ernst C. Stiefel Concert Hall",
                    "localist_url": "https://event.newschool.edu/mannesorchestra",
                    "free": True,
                    "address": "55 W 13th St, New York, NY 10011",
                }
            ]
        }
        resp = mock.Mock(status_code=200, json=mock.Mock(return_value=payload))
        resp.raise_for_status = mock.Mock()
        with mock.patch.object(scrapers._SESSION, "post", return_value=resp):
            events = scrapers.scrape_new_school(None, "ua")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["name"], "Mannes Orchestra at Alice Tully Hall")
        self.assertEqual(events[0]["price"], "Free")
        self.assertEqual(events[0]["category"], "music")
        self.assertIn("Stiefel Concert Hall", events[0]["venue"])
        self.assertEqual(events[0]["date"], "2026-12-06T00:30:00+00:00")


class NitehawkTests(unittest.TestCase):
    def test_parses_showtimes(self):
        index_html = """
        <html><body>
        <div class="show-container">
            <a href="/movies/paprika/">Paprika</a>
            <ul class="showtime-button-row">
                <li><a href="/purchase/111/">7:30 pm</a></li>
            </ul>
        </div>
        </body></html>
        """
        resp = mock.Mock(status_code=200, text=index_html)
        resp.raise_for_status = mock.Mock()
        with mock.patch.object(scrapers._SESSION, "get", return_value=resp):
            events = scrapers.scrape_nitehawk_cinema("https://nitehawkcinema.com/williamsburg/", "ua")
        self.assertEqual(len(events), 1)
        self.assertIn("Paprika (7:30 pm)", events[0]["name"])
        self.assertEqual(events[0]["venue"], "Nitehawk Cinema Williamsburg")
        self.assertEqual(events[0]["url"], "https://nitehawkcinema.com/purchase/111/")
        self.assertEqual(events[0]["category"], "film")


class ApolloTheaterTests(unittest.TestCase):
    def test_parses_webflow_items(self):
        html = """
        <div class="w-dyn-item">
            <div class="header-slider_title">Jane Handcock</div>
            <div>2026-11-13 | 10 PM</div>
            <a href="/event/apollo-music-cafe-jane-handcock">Find Out More</a>
        </div>
        """
        resp = mock.Mock(status_code=200, text=html)
        resp.raise_for_status = mock.Mock()
        with mock.patch.object(scrapers._SESSION, "get", return_value=resp):
            events = scrapers.scrape_apollo_theater("https://www.apollotheater.org/calendar/", "ua")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["name"], "Jane Handcock")
        self.assertEqual(events[0]["venue"], "Apollo Theater")
        self.assertEqual(events[0]["url"], "https://www.apollotheater.org/event/apollo-music-cafe-jane-handcock")
        self.assertEqual(events[0]["date"], "2026-11-14T03:00:00+00:00")


class TvEyeTests(unittest.TestCase):
    def test_parses_seetickets_events(self):
        html = """
        <div class="search-event">
            <div class="hover-name"><a href="https://www.seetickets.us/event/indie-rock-show/12345">Indie Rock Show</a></div>
            <div class="hover-date">Tuesday, November 17</div>
            <div class="hover-time">8:00 PM</div>
        </div>
        """
        resp = mock.Mock(status_code=200, text=html)
        resp.raise_for_status = mock.Mock()
        with mock.patch.object(scrapers._SESSION, "get", return_value=resp):
            events = scrapers.scrape_tv_eye("https://wl.seetickets.us/TVEye", "ua")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["name"], "Indie Rock Show")
        self.assertEqual(events[0]["venue"], "TV Eye")
        self.assertEqual(events[0]["url"], "https://www.seetickets.us/event/indie-rock-show/12345")
        self.assertEqual(events[0]["category"], "music")


class LePoissonRougeTests(unittest.TestCase):
    def test_parses_lpr_events(self):
        html = """
        <div class="event">
            <span class="black_visible">LPR Live Concert</span>
            <div class="date">Nov 20, 2026</div>
            <div class="time">7:00 pm</div>
            <a href="https://kyd.to/event/123">Tickets</a>
        </div>
        """
        resp = mock.Mock(status_code=200, text=html)
        resp.raise_for_status = mock.Mock()
        with mock.patch.object(scrapers._SESSION, "get", return_value=resp):
            events = scrapers.scrape_le_poisson_rouge("https://lpr.com/", "ua")
        self.assertTrue(len(events) >= 1)
        self.assertEqual(events[0]["name"], "LPR Live Concert")
        self.assertEqual(events[0]["venue"], "Le Poisson Rouge")
        self.assertEqual(events[0]["url"], "https://kyd.to/event/123")


class NycBalletTests(unittest.TestCase):
    def test_parses_ballet_events(self):
        data = [
            {
                "id": 999,
                "title": "The Nutcracker",
                "perf_date": "2026-12-15T19:00:00-05:00",
                "booking_link": "https://tickets.nycballet.com/booking/production/999",
                "short_description": "George Balanchine's The Nutcracker"
            }
        ]
        resp = mock.Mock(status_code=200)
        resp.raise_for_status = mock.Mock()
        resp.json = mock.Mock(return_value=data)
        with mock.patch.object(scrapers._SESSION, "get", return_value=resp):
            events = scrapers.scrape_nyc_ballet("https://www.nycballet.com/season-and-tickets/events/", "ua")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["name"], "The Nutcracker")
        self.assertEqual(events[0]["venue"], "David H. Koch Theater (Lincoln Center)")
        self.assertEqual(events[0]["category"], "dance")
        self.assertEqual(events[0]["url"], "https://tickets.nycballet.com/booking/production/999")
        self.assertEqual(events[0]["date"], "2026-12-16T00:00:00+00:00")


class ArlenesGroceryTests(unittest.TestCase):
    def test_parses_afton_events(self):
        data = {
            "status": "success",
            "data": [
                {
                    "event_id": "555",
                    "event_name": "Rock Showcase",
                    "start_time": "2026-11-25 20:00:00",
                    "min_price": 10,
                    "buy_ticket_url": "https://aftontickets.com/event/buyticket/555"
                }
            ]
        }
        resp = mock.Mock(status_code=200)
        resp.raise_for_status = mock.Mock()
        resp.json = mock.Mock(return_value=data)
        with mock.patch.object(scrapers._SESSION, "get", return_value=resp):
            events = scrapers.scrape_arlenes_grocery("https://aftontickets.com/api/get-events", "ua")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["name"], "Rock Showcase")
        self.assertEqual(events[0]["venue"], "Arlene's Grocery")
        self.assertEqual(events[0]["category"], "music")
        self.assertEqual(events[0]["price"], "$10")
        self.assertEqual(events[0]["url"], "https://aftontickets.com/event/buyticket/555")


if __name__ == "__main__":
    unittest.main()

