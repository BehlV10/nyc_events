"""Prices: never show a ticketed event as Free, and prefer the venue's own price."""
import os
import sys
import unittest
from datetime import datetime, timedelta
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import scrapers  # noqa: E402
from scrapers import EASTERN, _partiful_price, admission_price, mentions_free  # noqa: E402
from template import _is_event_free, _merge_duplicates  # noqa: E402


class PriceTextTest(unittest.TestCase):
    def test_admission_price(self):
        cases = {
            "21+, $10 CASH ONLY cover": "$10",
            "🎟️: $10 CASH OR VENMO (RSVP NOW)": "$10",
            "Jackbox, Social Board Games & more? $5 Tickets.": "$5",
            "Tickets: $5 + fee": "$5",
            "Tickets $15 adv / $20 door": "$15–$20",
            "$40 & $30 + fee": "$30–$40",
            "Admission: $12.50": "$12.50",
            "$10 to enter": "$10",
        }
        for text, want in cases.items():
            self.assertEqual(admission_price(text), want, text)

    def test_amounts_that_are_not_admission(self):
        for text in ("Bring $3 for bag check", "Win $100 in prizes, free to play", "We raised $5,000",
                     "$1 Oysters", "$10 Pizza Night", "Free admission"):
            self.assertIsNone(admission_price(text), text)

    def test_mentions_free_needs_the_word(self):
        for text in ("FREE Early Movie Screening", "No Cover Karaoke", "Free Night of Comedy", "Free Thursday Nights"):
            self.assertTrue(mentions_free(text), text)
        for text in ("Alice Howe & Freebo", "Hot Slander & Dogs Run Free", "Verveine: Gluten Free Cafe",
                     "feel free to bring a friend"):
            self.assertFalse(mentions_free(text), text)


class PartifulTest(unittest.TestCase):
    def test_cover_in_description(self):
        self.assertEqual(_partiful_price({"title": "Uplifting Tinashe", "description": "21+, $10 CASH ONLY cover ★ RSVP"}), "$10")
        self.assertEqual(_partiful_price({"title": "3rd birthday", "description": "$15 cash cover, $10 for first 100 RSVPs"}), "$10–$15")

    def test_only_free_when_the_host_says_so(self):
        self.assertEqual(_partiful_price({"title": "Craft Meetup", "description": "Free, bring a project!"}), "Free")
        self.assertIsNone(_partiful_price({"title": "Craft Meetup", "isPublic": True, "description": "Bring a project!"}))
        self.assertIsNone(_partiful_price({"title": "Warehouse Party", "description": "Tickets at the link"}))


class TicketmasterZeroTest(unittest.TestCase):
    def test_a_zero_range_is_no_price(self):
        self.assertIsNone(scrapers._format_price_range(0 or None, 0 or None))
        self.assertEqual(scrapers._format_price_range(0 or None, 45.5), "$45.5")


class IsEventFreeTest(unittest.TestCase):
    def ev(self, name, **kw):
        e = {"name": name, "venue": kw.pop("venue", "Somewhere"), "_source_venue": kw.pop("source", "Somewhere"),
             "url": kw.pop("url", "https://example.com/event")}
        e.update(kw)
        return e

    def test_activity_words_still_suggest_free(self):
        self.assertTrue(_is_event_free(self.ev("Board Games @ Pete's Candy Store")))
        self.assertTrue(_is_event_free(self.ev("Poetry Open Mic", venue="Word Bookstore")))
        self.assertTrue(_is_event_free(self.ev("YA Book Club", source="Brooklyn Public Library")))

    def test_but_not_when_the_listing_says_otherwise(self):
        night = "Queer Board Game Night"
        self.assertFalse(_is_event_free(self.ev(night, description="Hosted by NYC Gaymers. $5 Tickets.")))
        self.assertFalse(_is_event_free(self.ev(night, _alt_sources=[{"venue": "DoNYC", "price": "$5 + fee"}])))
        self.assertFalse(_is_event_free(self.ev(night, price="$5")))
        self.assertFalse(_is_event_free(self.ev("Open Mic with Live Band", url="https://www.ticketweb.com/event/open-mic")))
        self.assertFalse(_is_event_free(self.ev("The Magic Lab: Open Mic Magic Show",
                                                url="https://www.eventbrite.com/e/the-magic-lab-tickets-1")))
        self.assertFalse(_is_event_free(self.ev("Wonder and Learn: Storytime!", venue="Brooklyn Children's Museum")))

    def test_free_in_a_name_is_not_always_admission(self):
        self.assertFalse(_is_event_free(self.ev("Iliza Shlesinger: Free Nights & Weekends",
                                                url="https://www.ticketmaster.com/iliza-shlesinger-free-nights")))
        self.assertFalse(_is_event_free(self.ev("Hot Slander & Dogs Run Free")))
        self.assertFalse(_is_event_free(self.ev("Verveine: Gluten Free Cafe & Bakery")))
        self.assertFalse(_is_event_free(self.ev("Alice Howe & Freebo")))
        self.assertTrue(_is_event_free(self.ev("Free Friday Nights", venue="Brooklyn Museum")))

    def test_explicit_free_price_still_wins(self):
        self.assertTrue(_is_event_free(self.ev("Drag Bingo", price="Free", url="https://www.ticketweb.com/x")))


class MergePriceTest(unittest.TestCase):
    def test_venue_price_beats_listing_site_free(self):
        t = (datetime.now(EASTERN) + timedelta(days=5)).replace(hour=19, minute=0, second=0, microsecond=0)
        events = [
            {"name": "Queer Board Game Night", "venue": "Rash Bar", "date": t.isoformat(),
             "url": "https://donyc.com/events/queer-board-game-night", "price": "Free",
             "category": "community", "_source_venue": "DoNYC Citywide", "_time": t},
            {"name": "Queer Board Game Night", "venue": "Rash Bar (Back Room)", "date": t.isoformat(),
             "url": "https://rashbar.example/events/queer-board-game-night", "price": "$5",
             "category": "community", "_source_venue": "Rash Bar", "_time": t},
        ]
        merged = _merge_duplicates(events)
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["_source_venue"], "Rash Bar")
        self.assertEqual(merged[0]["price"], "$5")
        self.assertFalse(_is_event_free(merged[0]))


if __name__ == "__main__":
    unittest.main()
