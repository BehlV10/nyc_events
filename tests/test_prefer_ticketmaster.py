"""A show listed through a guide or resale site links its Ticketmaster page; venue sites and AXS stay."""
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import scrapers as S  # noqa: E402
import template as T  # noqa: E402


def _card(url, venue="Birdland", name="Maria Schneider Orchestra", alts=()):
    return {"name": name, "venue": venue, "url": url, "_source_venue": "Birdland", "price": "$40", "_alt_sources": list(alts)}


def _tm(url="https://www.ticketweb.com/event/maria-schneider-orchestra-birdland-jazz-club-tickets/1",
        venue="Birdland Jazz Club", name="Maria Schneider Orchestra", price="$45"):
    return {"venue": "TicketWeb", "source": "Ticketmaster NYC", "url": url, "name": name, "event_venue": venue, "price": price}


class PreferTicketmaster(unittest.TestCase):
    def test_guide_link_gives_way_to_ticketmaster(self):
        e = _card("https://www.hothousejazz.com/event_detail/181429", alts=[_tm()])
        self.assertTrue(T._prefer_ticketmaster(e))
        self.assertIn("ticketweb.com", e["url"])
        self.assertEqual(e["_alt_sources"][0]["url"], "https://www.hothousejazz.com/event_detail/181429")
        self.assertEqual(e["price"], "$40")  # the card keeps its own price

    def test_takes_ticketmaster_price_when_card_has_none(self):
        e = _card("https://events.amny.com/event/tosca/", venue="The Metropolitan Opera", name="Puccini's Tosca",
                  alts=[_tm("https://www.ticketmaster.com/event/Z7r9", "Metropolitan Opera House", "Tosca", "$35+")])
        e["price"] = None
        self.assertTrue(T._prefer_ticketmaster(e))
        self.assertEqual((e["url"], e["price"]), ("https://www.ticketmaster.com/event/Z7r9", "$35+"))

    def test_sister_venue_or_other_event_is_not_swapped(self):
        smalls = _card("https://www.hothousejazz.com/event_detail/1", venue="Smalls Jazz Club",
                       name="Thomas Linger Trio", alts=[_tm("https://www.ticketweb.com/event/thomas-linger-trio-mezzrow-tickets/2",
                                                            "Mezzrow", "Thomas Linger Trio")])
        self.assertFalse(T._prefer_ticketmaster(smalls))
        book_club = _card("https://allevents.in/new-york/horror-classics/1", venue="The Twisted Spine",
                          name="Horror Classics Book Club: A Christmas Carol",
                          alts=[_tm("https://www.ticketmaster.com/event/Z7", "Merchant's House Museum", "A Christmas Carol")])
        self.assertFalse(T._prefer_ticketmaster(book_club))
        unrelated = _card("https://www.hothousejazz.com/event_detail/2", alts=[_tm(name="Birdland Big Band")])
        self.assertFalse(T._prefer_ticketmaster(unrelated))

    def test_venue_sites_and_original_sellers_stay(self):
        for url in ("https://www.birdlandjazz.com/tm-event/maria-schneider-orchestra-5/", "https://www.metopera.org/season/tosca",
                    "https://www.axs.com/events/1/guster", "https://dice.fm/event/abc", "https://www.eventbrite.com/e/1",
                    "https://www.ticketmaster.com/event/Z1"):
            e = _card(url, alts=[_tm()])
            self.assertFalse(T._prefer_ticketmaster(e), url)
            self.assertEqual(e["url"], url)

    def test_card_links_ticketmaster_end_to_end(self):
        when = (datetime.now(S.EASTERN) + timedelta(days=1)).replace(hour=20, minute=0, second=0, microsecond=0)
        iso = when.astimezone(timezone.utc).isoformat()
        payload = {"venues": [
            {"venue": "Hot House Jazz Guide", "url": "https://www.hothousejazz.com/calendar", "events": [
                {"name": "Maria Schneider Orchestra", "venue": "Birdland", "date": iso, "category": "music",
                 "url": "https://www.hothousejazz.com/event_detail/181429"}]},
            {"venue": "Ticketmaster NYC", "url": "https://www.ticketmaster.com", "events": [
                {"name": "Maria Schneider Orchestra", "venue": "Birdland Jazz Club", "date": iso, "category": "music",
                 "url": "https://www.ticketweb.com/event/maria-schneider-orchestra-birdland-jazz-club-tickets/1"}]},
        ]}
        buckets = dict(T.group_by_date(payload["venues"])[0])
        cards = [e for evs in buckets.values() for e in evs]
        self.assertEqual(len(cards), 1)
        self.assertIn("ticketweb.com", cards[0]["url"])
        self.assertTrue(any("hothousejazz.com" in a["url"] for a in cards[0]["_alt_sources"]))


if __name__ == "__main__":
    unittest.main()
