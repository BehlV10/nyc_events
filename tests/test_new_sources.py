"""AllEvents listings relinked to Eventbrite by id, member-organization events dropped, and the
IFPA pinball and Hot House jazz sources."""
import os
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import scrapers  # noqa: E402


def _ev(url, days=3):
    when = datetime.now(timezone.utc) + timedelta(days=days)
    return {"name": "Event", "date": when.isoformat(), "url": url, "venue": "Somewhere"}


def _no_fetch(url):
    raise AssertionError(f"page read: {url}")


class AlleventsEventbriteIds(unittest.TestCase):
    def test_eventbrite_ids_map_without_reading_the_page(self):
        self.assertEqual(scrapers.allevents_eventbrite_url("https://allevents.in/new-york/gratitude-through-music/100002000600156924"),
                         "https://www.eventbrite.com/e/2000600156924")
        self.assertIsNone(scrapers.allevents_eventbrite_url("https://allevents.in/new-york/lfc-vs-man-utd/200031027179415"))
        self.assertIsNone(scrapers.allevents_eventbrite_url("https://www.eventbrite.com/e/100002000600156924"))

    def _run(self, results, fetch=_no_fetch, details=None, **kw):
        with tempfile.TemporaryDirectory() as tmp:
            return scrapers._resolve_allevents_links(
                results, links_path=os.path.join(tmp, "l.json"), details_path=os.path.join(tmp, "d.json"),
                fetch=fetch, details=details or (lambda i, ua: {"status": "live"}), **kw)

    def test_relinked_from_id_even_with_no_page_budget(self):
        a = _ev("https://allevents.in/new-york/gratitude-through-music/100002000600156924")
        results = [{"venue": "AllEvents NYC", "events": [a]}]
        self.assertEqual(self._run(results, page_limit=0), 1)
        self.assertEqual(a["url"], "https://www.eventbrite.com/e/2000600156924")

    def test_member_organization_events_are_dropped(self):
        sorority = _ev("https://allevents.in/staten-island/ugly-sweater-holiday-bowling-party/200031022169723")
        club = _ev("https://allevents.in/brooklyn/chapter-gala/100002004124541453")
        ok = _ev("https://allevents.in/brooklyn/queer-friendsgiving/100002004124541999")
        results = [{"venue": "AllEvents: Staten Island (all)", "events": [sorority, club, ok]}]
        page = ('<script type="application/ld+json">{"@type":"Event","organizer":[{"@type":"Organization",'
                '"name":"Staten Island Alumnae Chapter of Delta Sigma Theta Sorority Inc.","url":"x"}]}</script>')
        details = {"2004124541453": {"status": "live", "organizer_name": "Omega Psi Phi Fraternity, Inc. - Nu Chapter"},
                   "2004124541999": {"status": "live", "organizer_name": "Mister Cheeks"}}
        self._run(results, fetch=lambda u: page, details=lambda i, ua: details[i])
        self.assertEqual([e["url"] for e in results[0]["events"]], ["https://www.eventbrite.com/e/2004124541999"])

    def test_host_read_from_json_ld(self):
        page = '{"organizer":[{"@type":"Organization","name":"Caf\\u00e9 Club \\"NYC\\"","url":"x"}]}'
        self.assertEqual(scrapers._allevents_host(page), 'Café Club "NYC"')
        self.assertIsNone(scrapers._allevents_host("<html></html>"))

    def test_overlap_report_counts_direct_eventbrite_listings(self):
        results = [
            {"venue": "AllEvents NYC", "events": [{"url": "https://www.eventbrite.com/e/111111111"},
                                                  {"url": "https://www.eventbrite.com/e/222222222"},
                                                  {"url": "https://allevents.in/x/200031022169723"}]},
            {"venue": "Eventbrite organizer", "events": [{"url": "https://www.eventbrite.com/e/party-tickets-111111111"}]},
        ]
        self.assertEqual(scrapers._report_allevents_overlap(results), (1, 2, 3))


IFPA_LIST = """
<div id="search_result_1" class="list-group-item"><h5 class="mb-1"><a href="/tournaments/view.php?t=121871">FiDi Winter Pinball Open</a></h5>
<p class="mb-1"><small><span class="us sprite"></span> New York, NY, United States | Main Tournament | Dec 12, 2099 to Dec 13, 2099</small></p></div>
<div id="search_result_2" class="list-group-item"><h5 class="mb-1"><a href="/tournaments/view.php?t=122273">The Feast! (@ Red Hook)</a></h5>
<p class="mb-1"><small><span class="us sprite"></span> Brooklyn, NY, United States | Main Tournament | Nov 20, 2099</small></p></div>
<div id="search_result_3" class="list-group-item"><h5 class="mb-1"><a href="/tournaments/view.php?t=1">Jersey Flips</a></h5>
<p class="mb-1"><small><span class="us sprite"></span> Hoboken, NJ, United States | Main Tournament | Nov 21, 2099</small></p></div>
"""


def _ifpa_detail(address, start):
    return (f'<div class="col"><span class="ps-1 fw-bold">Address</span><br/><h6><a href="x">{address}</a></h6></div>'
            f'<div class="col"><b>Start Time</b><br/><h6>{start}</h6></div>'
            '<div><a href="https://www.facebook.com/x" TARGET="_blank">Website</a></div>')


class IfpaPinball(unittest.TestCase):
    def test_nyc_tournaments_with_address_and_start_time(self):
        details = {
            "https://www.ifpapinball.com/tournaments/view.php?t=121871": _ifpa_detail("10 Cortlandt St\nNew York NY 10007", "1:00 PM"),
            "https://www.ifpapinball.com/tournaments/view.php?t=122273": _ifpa_detail("Brooklyn, NY 11231, United States", "12:00 am"),
        }
        with mock.patch.object(scrapers, "fetch_soup", return_value=scrapers.BeautifulSoup(IFPA_LIST, "html.parser")):
            evs = scrapers.scrape_ifpa_nearby("u", "ua", fetch_detail=lambda u: details[u])
        by_name = {e["name"]: e for e in evs}
        self.assertEqual(set(by_name), {"FiDi Winter Pinball Open", "The Feast! (@ Red Hook) (pinball tournament)"})  # not Hoboken
        fidi = by_name["FiDi Winter Pinball Open"]
        self.assertEqual(fidi["venue"], "10 Cortlandt St")
        self.assertEqual(fidi["date"], "2099-12-12T18:00:00+00:00")
        self.assertNotIn("time_unknown", fidi)
        feast = by_name["The Feast! (@ Red Hook) (pinball tournament)"]
        self.assertEqual(feast["venue"], "Red Hook")  # no street address; "12:00 am" is the form's blank
        self.assertTrue(feast["time_unknown"])


HOTHOUSE_DAY = """
<div class="col-md-4"><div class="hhj-sbox"><div class="hhj-sinfo"><h3>Harlem Jazz Series - Rod Williams</h3>
<p><img/> Harlem</p><p><img/> <a class="loca-map" href="m">Mount Morris Ascension Presbyterian Church</a></p>
<p><a class="loca-map web-link" href="https://harlemjazzboxx.com">harlemjazzboxx.com</a></p></div>
<div class="hhj-box-bottom"><div class="event-cost"><p class="paid">$30</p></div>
<div class="hhj-sdate"><h6>20 NOV FRI</h6><h6>07:00 PM</h6></div></div></div>
<div class="hhj-buttons"><a href="https://www.hothousejazz.com/event_detail/181946" class="online-btn">View event</a></div></div>
<div class="col-md-4"><div class="hhj-sbox"><div class="hhj-sinfo"><h3>Latin Jazz Fridays</h3>
<p><img/> Greenwich Village</p><p><img/> <a class="loca-map" href="m">Django (The)</a></p></div>
<div class="hhj-box-bottom"><div class="event-cost"><p class="paid">Free adm</p></div>
<div class="hhj-sdate"><h6>20 NOV FRI</h6><h6>10:15 PM</h6></div></div></div>
<div class="hhj-buttons"><a href="https://www.hothousejazz.com/event_detail/2" class="online-btn">View event</a></div></div>
<div class="col-md-4"><div class="hhj-sbox"><div class="hhj-sinfo"><h3>West Coast Trio</h3>
<p><img/> California</p><p><img/> <a class="loca-map" href="m">SFJAZZ</a></p></div>
<div class="hhj-box-bottom"><div class="hhj-sdate"><h6>20 NOV FRI</h6><h6>08:00 PM</h6></div></div></div>
<div class="hhj-buttons"><a href="https://www.hothousejazz.com/event_detail/3" class="online-btn">View event</a></div></div>
"""


class HotHouseJazz(unittest.TestCase):
    def test_nyc_listings_with_venue_time_and_price(self):
        evs = scrapers._parse_hothouse_day(HOTHOUSE_DAY, date(2099, 11, 20))
        self.assertEqual([e["name"] for e in evs], ["Harlem Jazz Series - Rod Williams", "Latin Jazz Fridays"])  # not California
        rod, latin = evs
        self.assertEqual(rod["date"], "2099-11-21T00:00:00+00:00")  # 7 PM Eastern
        self.assertEqual((rod["venue"], rod["price"], rod["url"]),
                         ("Mount Morris Ascension Presbyterian Church", "$30", "https://www.hothousejazz.com/event_detail/181946"))
        self.assertEqual((latin["venue"], latin["price"]), ("The Django", "Free"))

    def test_scraper_reads_each_day(self):
        asked = []
        evs = scrapers.scrape_hothouse_jazz("u", "ua", days=3, post=lambda d: asked.append(d) or {"data": ""})
        self.assertEqual((len(asked), evs), (3, []))


class PoshNyc(unittest.TestCase):
    def _ev(self, slug, title, venue, days=2, hour=22, group="Night Crew", price=20, tz="America/New_York"):
        start = (datetime.now(timezone.utc) + timedelta(days=days)).replace(hour=hour, minute=0, second=0, microsecond=0)
        return {"url": slug, "title": title, "venueName": venue, "startDate": start.isoformat().replace("+00:00", "Z"),
                "timezone": tz, "groupName": group, "minTicketPrice": price}

    def test_filters_and_pagination(self):
        pages = [
            {"events": [self._ev("a", "Salsa Night", "San Antonios", price=0),
                        self._ev("b", "Secret Rave", "Location given day of"),
                        self._ev("c", "Online Mixer", "Virtual"),
                        self._ev("d", "Jersey Jam", "Maddhatter Hoboken"),
                        self._ev("e", "Old Party", "Bar 13", days=-3)], "nextCursor": 20},
            {"events": [self._ev("f", "Harbor Cruise", "Pier 40", group="iBoat Cruises NYC"),
                        self._ev("g", "Late One", "Bar 13", hour=23, group="Bar 13"),
                        self._ev("h", "Later One", "Bar 13", hour=23, group="Bar 13"),
                        self._ev("i", "Latest One", "Bar 13", hour=23, group="Bar 13"), self._ev("a", "Salsa Night", "San Antonios")],
             "nextCursor": None},
        ]
        asked = []
        evs = scrapers.scrape_posh_nyc("u", "ua", get=lambda p: asked.append(p.get("cursor")) or pages[len(asked) - 1])
        self.assertEqual(asked, [None, 20])
        names = sorted(e["name"] for e in evs)
        self.assertEqual(len([n for n in names if n.endswith("One")]), 2)  # at most two a day per organizer
        self.assertIn("Salsa Night", names)
        for gone in ("Secret Rave", "Online Mixer", "Jersey Jam", "Old Party", "Harbor Cruise"):
            self.assertNotIn(gone, names)
        salsa = next(e for e in evs if e["name"] == "Salsa Night")
        self.assertEqual((salsa["url"], salsa["price"], salsa["venue"]), ("https://posh.vip/e/a", "Free", "San Antonios"))

    def test_nyc_places_with_out_of_town_words_are_kept(self):
        pages = [{"events": [self._ev("a", "LIC Rooftop", "Cavalli Long Island City"),
                             self._ev("b", "Nolita Night", "Bar on Elizabeth St", group="Other"),
                             self._ev("c", "Out East", "Patchogue, Long Island", group="Third")], "nextCursor": None}]
        names = {e["name"] for e in scrapers.scrape_posh_nyc("u", "ua", get=lambda p: pages[0])}
        self.assertEqual(names, {"LIC Rooftop", "Nolita Night"})

    def test_failure_partway_keeps_fetched_pages(self):
        url = "https://posh.vip/api/bff/v1/explore/events"
        first = {"events": [self._ev("a", "Salsa Night", "San Antonios", price="n/a")], "nextCursor": 20}

        def get(params):
            if params.get("cursor") is None:
                return first
            raise ValueError("Expecting value: line 1 column 1 (char 0)")  # an HTML error page

        scrapers.HOST_GATE.reset()
        try:
            evs = scrapers.scrape_posh_nyc(url, "ua", get=get)
            self.assertEqual([(e["name"], e["price"]) for e in evs], [("Salsa Night", None)])
            # Flagged so _scrape_one tops this short list up with last run's listings.
            self.assertIn(scrapers._host_of(url), scrapers.HOST_GATE.refused)
        finally:
            scrapers.HOST_GATE.reset()
        with self.assertRaises(ValueError):  # nothing fetched at all: the last run's list is served
            scrapers.scrape_posh_nyc(url, "ua", get=lambda p: get({"cursor": 1}))
        scrapers.HOST_GATE.reset()


class PoshIsCrawledGently(unittest.TestCase):
    def test_posh_pacing_and_daily_refresh(self):
        self.assertEqual(scrapers._host_policy("posh.vip"), (1, 4.0))
        src = next(v for v in scrapers.VENUES if v["name"] == "Posh NYC")
        self.assertEqual(scrapers._get_venue_ttl(src["name"], v=src), scrapers.POSH_TTL)
        self.assertGreaterEqual(scrapers.POSH_TTL, 12 * 3600)


class TwelveHourJsonLdTimes(unittest.TestCase):
    def test_parses_clock_after_t(self):
        self.assertEqual(scrapers._local_iso_to_utc("2026-11-20T7:00 PM").isoformat(), "2026-11-21T00:00:00+00:00")
        self.assertEqual(scrapers._local_iso_to_utc("2026-11-21T12:30 pm").isoformat(), "2026-11-21T17:30:00+00:00")
        self.assertEqual(scrapers._local_iso_to_utc("2026-11-21T12:15 AM").isoformat(), "2026-11-21T05:15:00+00:00")
        self.assertIsNone(scrapers._local_iso_to_utc("next Tuesday"))

    def test_muse_paintbar_source_names_the_place(self):
        src = next(v for v in scrapers.VENUES if v["name"] == "Muse Paintbar Tribeca")
        self.assertEqual(src["kwargs"]["venue"], "Muse Paintbar Tribeca")
        self.assertIn("329 Greenwich", src["kwargs"]["address"])


if __name__ == "__main__":
    unittest.main()
