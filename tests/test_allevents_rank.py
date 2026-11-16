"""AllEvents is an aggregator: when it lists the same show as Ticketmaster or a venue, the card
links to that source and AllEvents never becomes the main link."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import template as T  # noqa: E402

DAY = "2030-01-08T19:00:00-05:00"


def _cards(*sources):
    dated, _tba, _ong = T.group_by_date([
        {"venue": src, "url": "https://src.example", "events": [
            {"name": name, "date": DAY, "url": url, "venue": "Richard Rodgers Theatre", "category": "theater"}]}
        for src, name, url in sources])
    return [e for _d, evs in dated for e in evs]


class AllEventsIsNeverPrimary(unittest.TestCase):
    def test_url_rank_matches_other_aggregators(self):
        self.assertEqual(T._url_priority("https://allevents.in/new%20york/hamilton/123"), 1)
        self.assertLess(T._url_priority("https://allevents.in/x/1"), T._url_priority("https://www.ticketmaster.com/event/Z1"))

    def test_ticketmaster_copy_wins_over_allevents(self):
        for order in (1, -1):
            sources = [("AllEvents: Art", "Hamilton at Richard Rodgers Theatre New York", "https://allevents.in/new%20york/hamilton/1"),
                       ("Ticketmaster NYC", "Hamilton", "https://www.ticketmaster.com/hamilton-new-york/event/Z1")][::order]
            cards = _cards(*sources)
            self.assertEqual(len(cards), 1, cards)
            self.assertIn("ticketmaster.com", cards[0]["url"])

    def test_allevents_only_listing_still_shown(self):
        cards = _cards(("AllEvents NYC (All)", "Two Strangers", "https://allevents.in/new%20york/two-strangers/2"))
        self.assertEqual([c["url"] for c in cards], ["https://allevents.in/new%20york/two-strangers/2"])


if __name__ == "__main__":
    unittest.main()
