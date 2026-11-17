"""Songkick is a directory, so the seller's link goes on the card; and events whose only link is
a Google-search fallback are never merged with each other just for sharing that link."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import scrapers  # noqa: E402
import template as T  # noqa: E402

DAY = "2030-01-08T18:00:00-05:00"


def _cards(results):
    dated, _tba, _ong = T.group_by_date(results)
    return [e for _d, evs in dated for e in evs]


class SearchFallbackLinks(unittest.TestCase):
    def test_search_links_do_not_identify_an_event(self):
        self.assertEqual(T._clean_event_url("https://www.google.com/search?q=Hohyun+Mercury+Lounge+NYC"), "")

    def test_unrelated_donyc_events_stay_separate(self):
        g = lambda q: f"https://www.google.com/search?q={q}"
        results = [
            {"venue": "Songkick NYC Concerts", "url": "https://www.songkick.com/metro-areas/7644", "events": [
                {"name": "HOHYUN", "date": DAY, "url": "https://www.songkick.com/concerts/1-hohyun", "venue": "Mercury Lounge", "category": "music"}]},
            {"venue": "Ticketmaster NYC", "url": "https://tm", "events": [
                {"name": "HOHYUN", "date": DAY, "url": "https://www.ticketmaster.com/hohyun/event/1", "venue": "Mercury Lounge (New York, NY)", "category": "music"}]},
            {"venue": "DoNYC Citywide", "url": "https://donyc.com/events", "events": [
                {"name": "Hohyun", "date": DAY, "url": g("Hohyun+Mercury+Lounge"), "venue": "Mercury Lounge", "category": "music"},
                {"name": "Spike Wilner Trio", "date": "2030-01-08T18:30:00-05:00", "url": g("Spike+Wilner+Trio"), "venue": "Smalls Jazz Club", "category": "music"},
                {"name": "Open Mic (FREE)", "date": "2030-01-08T19:00:00-05:00", "url": g("Open+Mic"), "venue": "QED", "price": "Free", "category": "comedy"}]}]
        cards = {c["name"]: c for c in _cards(results)}
        self.assertEqual(len(cards), 3, sorted(cards))
        show = next(c for n, c in cards.items() if n.lower() == "hohyun")
        self.assertIn("ticketmaster.com", show["url"])  # the seller, not the directory
        self.assertFalse(show.get("price"))             # not "Free" from someone else's open mic
        self.assertEqual(show.get("_other_times") or [], [])


class SongkickRank(unittest.TestCase):
    def test_songkick_ranks_with_aggregators(self):
        self.assertEqual(T._url_priority("https://www.songkick.com/concerts/43371315-hohyun-at-mercury-lounge"), 1)

    def test_mercury_east_venues_are_scraped_directly(self):
        urls = {v["url"] for v in scrapers.VENUES}
        self.assertIn("https://mercuryeastpresents.com/mercurylounge/", urls)
        self.assertIn("https://mercuryeastpresents.com/boweryballroom/", urls)

    def test_allevents_topics_are_one_source(self):
        names = [v["name"] for v in scrapers.VENUES if v["name"].startswith("AllEvents")]
        self.assertIn("AllEvents NYC (by topic)", names)
        self.assertTrue(all(n in ("AllEvents NYC", "AllEvents NYC (All)", "AllEvents NYC (by topic)") or n.endswith("(all)")
                            for n in names), names)

    def test_topic_feed_dedupes_and_title_beats_topic(self):
        from unittest import mock
        ev = lambda name, u: {"name": name, "date": DAY, "url": u, "venue": "Somewhere"}
        pages = {"https://allevents.in/a": [ev("Dungeons & Dragons Night", "u1"), ev("Evening at the Loft", "u2")],
                 "https://allevents.in/b": [ev("Evening at the Loft", "u2"), ev("Quiet Hour", "u3")]}
        calls = []

        def fake(url, ua, pages=4, param="page"):
            calls.append(url)
            if url.endswith("/c"):
                raise RuntimeError("timeout")
            return [dict(e) for e in globals_pages[url]]
        globals_pages = pages
        with mock.patch.object(scrapers, "scrape_jsonld_paged", fake):
            out = scrapers.scrape_allevents_categories("https://allevents.in", None,
                                                       category_pages=(("a", "theater"), ("c", "music"), ("b", "music")))
        self.assertEqual(len(calls), 3)  # the failed page is skipped, not fatal
        cats = {e["name"]: e["category"] for e in out}
        self.assertEqual(cats, {"Dungeons & Dragons Night": "gaming", "Evening at the Loft": "theater", "Quiet Hour": "music"})


class ArtistVersusTourTitle(unittest.TestCase):
    def test_directory_artist_title_merges_into_the_venue_tour_title(self):
        t = "2030-01-08T19:00:00-05:00"
        results = [
            {"venue": "Brooklyn Paramount (Official Calendar)", "url": "https://bp", "events": [
                {"name": "Syd: Beard Tour", "date": t, "url": "https://www.brooklynparamount.com/syd", "venue": "Brooklyn Paramount", "category": "music"}]},
            {"venue": "SeatGeek NYC", "url": "https://sg", "events": [
                {"name": "Syd", "date": t, "url": "https://seatgeek.com/syd", "venue": "Brooklyn Paramount", "category": "music"}]},
            {"venue": "Songkick NYC Concerts", "url": "https://sk", "events": [
                {"name": "Syd", "date": t, "url": "https://www.songkick.com/concerts/2-syd", "venue": "Brooklyn Paramount", "category": "music"}]}]
        cards = _cards(results)
        self.assertEqual([c["name"] for c in cards], ["Syd: Beard Tour"])
        self.assertIn("brooklynparamount.com", cards[0]["url"])

    def test_two_venue_listings_are_not_merged_by_this_rule(self):
        t = "2030-01-08T19:00:00-05:00"
        results = [{"venue": "Some Club (own calendar)", "url": "https://c", "events": [
            {"name": "Trivia", "date": t, "url": "https://c/1", "venue": "Some Club", "category": "gaming"},
            {"name": "Trivia Night: Movies Edition Upstairs", "date": t, "url": "https://c/2", "venue": "Some Club", "category": "gaming"}]}]
        self.assertEqual(len(_cards(results)), 2)


class WarsawTimes(unittest.TestCase):
    def test_naive_times_are_new_york_time(self):
        from unittest import mock
        page = ('<script type="application/ld+json">[{"@type":"MusicEvent","name":"Eloise","startDate":"2099-12-09T19:00:00",'
                '"url":"https://www.warsawconcerts.com/e/1"}]</script>')
        resp = mock.Mock(status_code=200, text=page)
        with mock.patch.object(scrapers._SESSION, "get", return_value=resp):
            ev = scrapers.scrape_warsaw(None, None)
        self.assertEqual(ev[0]["date"], "2099-12-10T00:00:00+00:00")  # 7pm Eastern


class TomorrowAuditFixes(unittest.TestCase):
    def test_search_fallback_uses_scraped_venue_calendar(self):
        t = "2030-01-08T19:00:00-05:00"
        results = [{"venue": "DoNYC Citywide", "url": "https://donyc.com/events", "events": [
            {"name": "DJ Awesome", "date": t, "url": "https://www.google.com/search?q=DJ+Awesome+Shrine+NYC",
             "venue": "Shrine", "category": "clubbing"},
            {"name": "Afrobeat Late Set", "date": "2030-01-08T22:00:00-05:00",
             "url": "https://www.google.com/search?q=Afrobeat+Shrine+NYC", "venue": "Shrine", "category": "clubbing"},
        ]}]
        cards = _cards(results)
        self.assertEqual(len(cards), 2)
        self.assertEqual(cards[0]["url"], "https://www.shrinenyc.com/calendar_main.php")

    def test_compare_links_only_when_major_seller_lists_event(self):
        donyc_only = {
            "name": "Indie Band Night", "venue": "Bowery Ballroom", "_source_venue": "DoNYC Citywide",
            "url": "https://www.boweryballroom.com/e/1", "price": "$25", "category": "music",
        }
        self.assertEqual(T._build_compare_links(donyc_only, donyc_only["name"]), "")
        tm_ev = {
            "name": "Indie Band Night", "venue": "Bowery Ballroom", "_source_venue": "Ticketmaster NYC",
            "url": "https://www.ticketmaster.com/event/123", "price": "$25", "category": "music",
        }
        self.assertIn("StubHub", T._build_compare_links(tm_ev, tm_ev["name"]))

    def test_daily_tours_sink_below_timed_events(self):
        results = [{"venue": "DoNYC Citywide", "url": "https://donyc.com/events", "events": [
            {"name": "Lincoln Center Tours", "date": "2030-01-08T10:15:00-05:00",
             "url": "https://lincolncenter.org/tours", "venue": "Lincoln Center", "category": "music"},
            {"name": "Evening Jazz Concert", "date": "2030-01-08T20:00:00-05:00",
             "url": "https://lincolncenter.org/jazz", "venue": "Lincoln Center", "category": "music"},
        ]}]
        cards = _cards(results)
        self.assertEqual([c["name"] for c in cards], ["Evening Jazz Concert", "Lincoln Center Tours"])

    def test_shop_and_support_cashmere_sale_filtered(self):
        self.assertTrue(scrapers.is_service_ad("Shop + Support: JCC Party at The Cashmere Sale", "JCC Manhattan"))

    def test_flozier_54_below_start_time_extracted(self):
        from datetime import date
        html = '<h4 class="dt-duration">November 17, 2026</h4><a href="https://54below.org/t">Tue, Nov 17 :9:30 pm / 9:00 pm</a>'
        self.assertEqual(scrapers.start_time_from_page(html, date(2026, 11, 17)), (21, 30))

    def test_cinema_regular_runs_dropped_and_film_society_categorized_as_film(self):
        results = [{"venue": "DoNYC Citywide", "url": "https://donyc.com/events", "events": [
            {"name": "Fatherland", "date": "2030-01-08T17:30:00-05:00", "url": "https://filmlinc.org/f",
             "venue": "Film Society of Lincoln Center", "category": "music"},
            {"name": "Fatherland", "date": "2030-01-09T17:30:00-05:00", "url": "https://filmlinc.org/f",
             "venue": "Film Society of Lincoln Center", "category": "music"},
            {"name": "Fatherland", "date": "2030-01-10T17:30:00-05:00", "url": "https://filmlinc.org/f",
             "venue": "Film Society of Lincoln Center", "category": "music"},
            {"name": "Rare 35mm Restoration", "date": "2030-01-08T19:00:00-05:00", "url": "https://filmlinc.org/r",
             "venue": "Film Society of Lincoln Center", "category": "music"},
        ]}]
        days, _, _ = T.group_by_date(results)
        all_cards = [e for _, evs in days for e in evs]
        self.assertEqual([c["name"] for c in all_cards], ["Rare 35mm Restoration"])
        self.assertEqual(all_cards[0]["category"], "film")

    def test_dance_nyc_extracts_venue_and_address_and_drops_zoom(self):
        from unittest import mock
        listing_html = """
        <div class="event">
          <div class="event_time">6:30pm</div>
          <div class="event_details">
            <a href="/for-audiences/community-calendar/view/Modern-Showcase/2099-11-18/"><h3>Modern Showcase</h3></a>
            <p>Taylor Center for Dance Education<br/>An evening of movement.</p>
          </div>
        </div>
        <div class="event">
          <div class="event_time">10:00am</div>
          <div class="event_details">
            <a href="/for-audiences/community-calendar/view/Zoom-Class/2099-11-18/"><h3>Morning Movement</h3></a>
            <p>Online Dance Co<br/>Join from home.</p>
          </div>
        </div>
        """
        detail_pages = {
            "https://www.dance.nyc/for-audiences/community-calendar/view/Modern-Showcase/2099-11-18/": """
                <div class="event_details">
                  <p><b>Company:</b> Taylor Center for Dance Education<br/><b>Venue:</b> Taylor Dance East<br/><b>Location:</b> New York City, NY</p>
                  <p>Taylor Center for Dance Education<br/>551 Grand Street<br/>New York City, NY, 10002</p>
                </div>
            """,
            "https://www.dance.nyc/for-audiences/community-calendar/view/Zoom-Class/2099-11-18/": """
                <div class="event_details">
                  <p><b>Company:</b> Online Dance Co<br/><b>Venue:</b> Zoom<br/><b>Location:</b> New York, NY</p>
                </div>
            """,
        }
        with mock.patch.object(scrapers, "fetch_soup", return_value=scrapers.BeautifulSoup(listing_html, "html.parser")):
            evs = scrapers.scrape_dance_nyc("https://www.dance.nyc/for-audiences/community-calendar/", "ua",
                                            fetch_detail=lambda u: detail_pages[u])
        self.assertEqual(len(evs), 1)
        self.assertEqual(evs[0]["venue"], "Taylor Dance East")
        self.assertEqual(evs[0]["address"], "551 Grand Street, New York City, NY, 10002")


    def test_noon_placeholder_feed_is_time_unknown_and_filled_from_page(self):
        evs = [{"name": f"Cabaret Night {i}", "date": f"2099-11-{17 + i}T17:00:00+00:00",
                "url": f"https://54below.org/events/show-{i}/", "venue": "Feinstein's/54 Below", "category": "music"}
               for i in range(4)]
        self.assertTrue(scrapers.is_noon_placeholder_feed(evs))
        results = [{"venue": "Feinstein's/54 Below", "url": "https://54below.org/", "events": [dict(e) for e in evs]}]
        days, _, _ = T.group_by_date(results)
        self.assertTrue(all(e.get("_time_unknown") for _, day in days for e in day))
        import os, tempfile
        with tempfile.TemporaryDirectory() as d:
            filled = scrapers._fill_missing_times(
                results, path=os.path.join(d, "times.json"),
                fetch=lambda u: '{"startDate":"2099-11-17T21:30:00-05:00"}' if "show-0" in u else "<p>none</p>")
        self.assertEqual(filled, 1)
        self.assertEqual(results[0]["events"][0]["date"], "2099-11-18T02:30:00+00:00")

    def test_noon_feed_needs_most_events_at_noon(self):
        evs = [{"date": "2099-11-17T17:00:00+00:00"}, {"date": "2099-11-18T00:00:00+00:00"},
               {"date": "2099-11-19T00:30:00+00:00"}, {"date": "2099-11-20T17:00:00+00:00"}]
        self.assertFalse(scrapers.is_noon_placeholder_feed(evs))
        market = [{"date": f"2099-12-0{i}T17:00:00+00:00", "end": f"2099-12-0{i}T23:00:00+00:00"} for i in range(1, 5)]
        self.assertFalse(scrapers.is_noon_placeholder_feed(market))
        flagged = [{"date": "2099-11-17T17:00:00+00:00", "time_unknown": True}] + [{"date": "2099-11-18T17:00:00+00:00"}] * 3
        self.assertFalse(scrapers.is_noon_placeholder_feed(flagged))  # scraper already marks its placeholders

    def test_venue_calendar_skips_feed_and_aggregator_urls(self):
        for name in ("Arlene's Grocery", "City Winery", "The Skint", "Skinny Dennis"):
            url = scrapers.known_venue_calendar(name)
            self.assertFalse(url and scrapers._FEED_URL_RE.search(url), (name, url))
        self.assertIsNone(scrapers.known_venue_calendar("Skint"))


if __name__ == "__main__":
    unittest.main()
