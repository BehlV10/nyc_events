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


class AllEventsWrongDates(unittest.TestCase):
    cards = staticmethod(AllEventsBroadwayPlaceholders._run)

    def test_one_off_show_filed_a_day_early_is_dropped(self):
        days = self.cards([
            ("Ticketmaster NYC", [("LPR Presents: JOHN SCOFIELD'S \"ELECTROSPECTIVE\"", "2030-01-08T20:00:00-05:00",
                                   "https://www.ticketmaster.com/scofield/1", "Town Hall (New York, NY)")]),
            ("AllEvents: Art", [("John Scofield", "2030-01-07T19:00:00-05:00", "https://allevents.in/x/scofield/1", "Town Hall Theatre - NY")])])
        self.assertNotIn("2030-01-07", days)
        self.assertIn("ticketmaster.com", days["2030-01-08"][0][1])

    def test_same_day_merge_ignores_allevents_time(self):
        days = self.cards([
            ("Ticketmaster NYC", [("New York Rangers vs. Carolina Hurricanes", "2030-01-08T19:00:00-05:00",
                                   "https://www.ticketmaster.com/rangers/1", "Madison Square Garden")]),
            ("AllEvents NYC (All)", [("Carolina Hurricanes at New York Rangers", "2030-01-08T12:30:00-05:00",
                                      "https://allevents.in/x/rangers/1", "Madison Square Garden")])])
        self.assertEqual(days["2030-01-08"], [("New York Rangers vs. Carolina Hurricanes", "https://www.ticketmaster.com/rangers/1")])

    def test_place_words_and_loose_overlaps_still_need_close_times(self):
        days = self.cards([
            ("Q.E.D. Astoria (own calendar)", [("Q.E.D. Astoria", "2030-01-08T18:00:00-05:00", "https://qedastoria.com/e/1", "Q.E.D. Astoria")]),
            ("Lincoln Center", [("Lincoln Center Tours", "2030-01-08T10:15:00-05:00", "https://lincolncenter.org/tours", "Lincoln Center")]),
            ("AllEvents: Queens (all)", [("Free Hookah Mondays at Egypt Astoria", "2030-01-08T23:00:00-05:00", "https://allevents.in/x/h/1", "Egypt Astoria"),
                                         ("FIRST MOVE Single Mingle & Dance @ Lincoln Center", "2030-01-08T18:30:00-05:00",
                                          "https://allevents.in/x/fm/1", "Lincoln Center for the Performing Arts")])])
        self.assertEqual(len(days["2030-01-08"]), 4)

    def test_generic_or_broader_titles_do_not_stand_for_other_events(self):
        days = self.cards([
            ("Ticketmaster NYC", [("New York Philharmonic", "2030-01-08T19:30:00-05:00", "https://www.ticketmaster.com/nyp/1", "David Geffen Hall"),
                                  ("Avengers: Doomsday", "2030-01-09T19:00:00-05:00", "https://www.ticketmaster.com/av/1", "Alamo Drafthouse Staten Island")]),
            ("AllEvents NYC (All)", [("New York Philharmonic: Rouvali Conducts Schubert", "2030-01-10T19:30:00-05:00",
                                      "https://allevents.in/x/nyp/1", "David Geffen Hall"),
                                     ("Avengers Doomsday Opening Day Movie hangout", "2030-01-11T18:00:00-05:00",
                                      "https://allevents.in/x/av/1", "Alamo Drafthouse Staten Island")])])
        self.assertIn("2030-01-10", days)
        self.assertIn("2030-01-11", days)

    def test_resale_links_rank_with_aggregators(self):
        self.assertEqual(T._url_priority("https://www.ticketnetwork.com/tickets/7881594?utm_source=ir"), 1)

    def test_events_abroad_and_airport_tours_are_dropped(self):
        days = self.cards([("AllEvents: Flushing (all)", [("ITMA Asia + CITME 2026", "2030-01-08T10:00:00-05:00", "https://allevents.in/x/itma/1", "Shanghai 上海, China"),
                                                        ("Costa Rica Eco-Beach Adventure", "2030-01-08T10:00:00-05:00", "https://allevents.in/x/cr/1", "John F. Kennedy International Airport"),
                                                        ("Curry Night", "2030-01-08T19:00:00-05:00", "https://allevents.in/x/c/1", "Taste of India")])])
        self.assertEqual([n for n, _u in days["2030-01-08"]], ["Curry Night"])


if __name__ == "__main__":
    unittest.main()
