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


if __name__ == "__main__":
    unittest.main()
