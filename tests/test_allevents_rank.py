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


class AllEventsBroadwayPlaceholders(unittest.TestCase):
    @staticmethod
    def _run(listings):
        dated, _tba, _ong = T.group_by_date([
            {"venue": src, "url": "https://src.example", "events": [
                {"name": name, "date": date, "url": url, "venue": venue, "category": "theater"}
                for name, date, url, venue in evs]} for src, evs in listings])
        return {d.isoformat(): [(e["name"], e["url"]) for e in evs] for d, evs in dated}

    def test_single_word_title_merges_with_allevents_copy(self):
        days = self._run([
            ("Ticketmaster NYC", [("MJ", "2030-01-08T19:00:00-05:00", "https://www.ticketmaster.com/mj/1", "Neil Simon Theatre")]),
            ("AllEvents NYC", [("MJ The Musical Tickets", "2030-01-08T19:00:00-05:00", "https://allevents.in/x/mj/9", "Neil Simon Theater")])])
        self.assertEqual(days["2030-01-08"], [("MJ", "https://www.ticketmaster.com/mj/1")])

    def test_allevents_date_on_a_dark_night_is_dropped(self):
        runs = [("Wicked (NY)", f"2030-01-{d:02d}T19:00:00-05:00", f"https://www.ticketmaster.com/wicked/{d}", "Gershwin Theatre")
                for d in (8, 9, 10, 11)]
        days = self._run([
            ("Ticketmaster NYC", runs),
            ("AllEvents: Theatre", [("Wicked", "2030-01-07T00:00:00-05:00", "https://allevents.in/x/wicked/1", "Gershwin Theatre"),
                                    ("Two Strangers", "2030-01-07T19:00:00-05:00", "https://allevents.in/x/two/2", "Longacre Theatre")])])
        self.assertEqual(days.get("2030-01-07"), [("Two Strangers", "https://allevents.in/x/two/2")])  # no direct run: kept
        self.assertEqual(len(days["2030-01-08"]), 1)


if __name__ == "__main__":
    unittest.main()
