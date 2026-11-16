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

    def test_allevents_is_read_by_place_only(self):
        names = [v["name"] for v in scrapers.VENUES if v["name"].startswith("AllEvents")]
        self.assertTrue(names)
        self.assertTrue(all(n in ("AllEvents NYC", "AllEvents NYC (All)") or n.endswith("(all)") for n in names), names)


if __name__ == "__main__":
    unittest.main()
