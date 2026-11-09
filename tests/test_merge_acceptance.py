"""Merge acceptance tests: the same event twice is one card; different events stay two.

Ported from boston_events' acceptance tests, plus the NYC cases found comparing a full rebuild.
Each uses titles, venues and sources as they appear on the site.
"""
import os
import sys
import unittest
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import template as T  # noqa: E402
from template import EASTERN  # noqa: E402

_counter = [0]


def _day_at(days, hour, minute=0):
    base = datetime.now(EASTERN).replace(hour=hour, minute=minute, second=0, microsecond=0)
    return base + timedelta(days=days)


def _ev(name, source, venue, when, url=None, category="music", **extra):
    _counter[0] += 1
    return {"name": name, "_source_venue": source, "venue": venue, "_time": when, "date": when.isoformat(),
            "url": url or f"https://x.example/{_counter[0]}", "category": category, **extra}


def _merge(events):
    return T._merge_duplicates(events, T.title_word_freq(events))


class SameEventMerges(unittest.TestCase):
    def test_the_label_shows_the_time_the_card_is_sorted_by(self):
        """Le Poisson Rouge says 7:30; SeatGeek and Songkick say 6:30 (doors). The card sorted at
        7:30 used to read "6:30 PM" because only _time, not date, took the venue's time."""
        out = _merge([
            _ev("Daniel Lanois", "SeatGeek NYC", "Le Poisson Rouge", _day_at(3, 18, 30),
                url="https://seatgeek.com/daniel-lanois-tickets/1"),
            _ev("Daniel Lanois", "Songkick NYC Concerts", "Le Poisson Rouge", _day_at(3, 18, 30),
                url="https://www.songkick.com/concerts/1-daniel-lanois"),
            _ev("Daniel Lanois Trio In The Round", "Le Poisson Rouge", "Le Poisson Rouge", _day_at(3, 19, 30),
                url="https://kyd.to/KjMophJk"),
        ])
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["_time"].strftime("%H:%M"), "19:30")
        self.assertEqual(T.format_when(out[0]), "7:30 PM")

    def test_venue_and_bookstore_listings_merge_and_the_venues_title_leads(self):
        t = _day_at(8, 19, 30)
        out = _merge([
            _ev("SOLD OUT! Ada Limon: The Hurting Kind", "Greenlight Bookstore", "Kaufmann Concert Hall", t, category="books"),
            _ev("A Conversation with Ada Limon", "Kaufmann Concert Hall", "Kaufmann Concert Hall", t, category="books"),
        ])
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["name"], "A Conversation with Ada Limon")

    def test_ticketmaster_double_listing_merges(self):
        t = _day_at(2, 22)
        out = _merge([
            _ev("CamelPhat", "Ticketmaster NYC", "Brooklyn Mirage", t, url="https://www.ticketmaster.com/event/A1"),
            _ev("CamelPhat (21 and Over)", "Ticketmaster NYC", "Brooklyn Mirage", t, url="https://www.ticketmaster.com/event/B2"),
            _ev("CamelPhat  (21+)", "Brooklyn Mirage", "Brooklyn Mirage", t, url="https://link.dice.fm/X9a354cd3dfe"),
        ])
        self.assertEqual(len(out), 1)

    def test_reseller_time_doesnt_split_a_feeds_double_listing(self):
        out = _merge([
            _ev("Phoebe Robinson - Feral & Fired Up! Tour", "DoNYC Citywide", "Beacon Theatre", _day_at(9, 18, 30),
                url="https://eventschaser.com/tickets/Phoebe-Robinson/7826233/"),
            _ev("Phoebe Robinson: Feral & Fired Up!", "DoNYC Citywide", "Beacon Theatre", _day_at(9, 19, 30),
                url="https://beacontheatre.com/event/phoebe-robinson/"),
        ])
        self.assertEqual(len(out), 1)

    def test_door_ages_are_not_different_shows(self):
        t = _day_at(9, 20)
        self.assertEqual(len(_merge([
            _ev("Hunxho - Ages 18+", "Ticketmaster NYC", "Webster Hall", t),
            _ev("Hunxho (16+)", "SeatGeek NYC", "Webster Hall", t),
        ])), 1)

    def test_a_date_in_the_title_is_not_a_show_number(self):
        t = _day_at(9, 23)
        self.assertEqual(len(_merge([
            _ev("LOVE 2 LOVE - A DONNA SUMMER DISCO PARTY", "GBH Parties", "TV Eye", t, category="clubbing"),
            _ev("Love to Love: A Donna Summer Disco Party Friday, December 11th", "Partiful NYC", "TV Eye", t, category="clubbing"),
        ])), 1)

    def test_a_citywide_feed_posting_one_show_twice_merges(self):
        t = _day_at(5, 19)
        self.assertEqual(len(_merge([
            _ev("Wicked", "AllEvents: Performances", "Gershwin Theatre", t, category="theater",
                url="https://allevents.in/new-york/wicked/21000281"),
            _ev("Wicked New York Tickets", "AllEvents: Performances", "Gershwin Theatre", t, category="theater",
                url="https://allevents.in/new-york/wicked-new-york"),
        ])), 1)

    def test_numbers_in_a_name_dont_block_merging(self):
        t = _day_at(7, 20)
        self.assertEqual(len(_merge([
            _ev("Brutalismus 3000", "Knockdown Center", "Knockdown Center", t, url="https://knockdown.center/e/1"),
            _ev("Brutalismus 3000 (18+)", "SeatGeek NYC", "Knockdown Center", t, url="https://seatgeek.com/b3k"),
        ])), 1)


class DifferentEventsStaySeparate(unittest.TestCase):
    def test_same_title_at_two_bars_stays_separate(self):
        t = _day_at(4, 19, 30)
        out = _merge([
            _ev("NYC Trivia Night", "NYC Trivia League", "Conor's Goat", t, category="gaming", lat=40.7450, lng=-73.9900),
            _ev("NYC Trivia Night", "NYC Trivia League", "Clara's Gramercy", t, category="gaming", lat=40.7350, lng=-73.9800,
                url="https://x.example/gramercy"),
        ])
        self.assertEqual(len(out), 2)

    def test_same_title_at_one_place_still_merges(self):
        t = _day_at(4, 19, 30)
        out = _merge([
            _ev("NYC Trivia Night", "NYC Trivia League", "Conor's Goat", t, category="gaming", lat=40.7450, lng=-73.9900),
            _ev("NYC Trivia Night", "AllEvents NYC", "Conors Goat", t, category="gaming", lat=40.7451, lng=-73.9901),
        ])
        self.assertEqual(len(out), 1)

    def test_one_venues_separate_programs_stay_separate(self):
        t = _day_at(4, 10)
        out = _merge([
            _ev("Family Art Day: Prints", "Museum of Arts and Design", "Museum of Arts and Design", t, category="family",
                url="https://madmuseum.org/events/family-art-day-prints"),
            _ev("Family Art Day: Collage", "Museum of Arts and Design", "Museum of Arts and Design", t, category="family",
                url="https://madmuseum.org/events/family-art-day-collage"),
        ])
        self.assertEqual(len(out), 2)

    def test_classes_on_a_schedule_stay_separate(self):
        t = _day_at(4, 18, 30)
        out = _merge([
            _ev("Pop Fusion Classes for Beginners on Mondays", "Dance Classes NYC", "Pearl Studios NYC", t, category="dance",
                url="https://www.eventbrite.com/e/pop-fusion-classes-1"),
            _ev("Samba Classes for Beginners on Mondays", "Dance Classes NYC", "Pearl Studios NYC", t, category="dance",
                url="https://www.eventbrite.com/e/samba-classes-2"),
        ])
        self.assertEqual(len(out), 2)

    def test_numbered_rounds_and_age_groups_stay_separate(self):
        t = _day_at(8, 19)
        self.assertEqual(len(_merge([
            _ev("COMEDY CONTEST PRELIMINARY ROUND 3", "DoNYC Citywide", "City Winery", t, category="comedy"),
            _ev("NY Comedy Contest Preliminary Round 5", "City Winery NYC", "The Loft at City Winery", t, category="comedy"),
        ])), 2)
        for ages in (("Ages 27-37", "Ages 36-48"), ("(Ages 27-37)", "(Ages 36-48)")):
            self.assertEqual(len(_merge([
                _ev(f"Speed Dating {ages[0]}", "Meetup: Speed Dating", "Tavern 29", t, category="community"),
                _ev(f"Speed Dating {ages[1]}", "Meetup: Speed Dating", "Tavern 29", t, category="community"),
            ])), 2, ages)

    def test_programs_at_different_libraries_stay_separate(self):
        t = _day_at(8, 15)
        out = _merge([
            _ev("Crafternoon: Tornado in a Jar", "Brooklyn Public Library", "Brooklyn Public Library (Flatbush)", t, category="family"),
            _ev("Tween Crafternoon", "Queens Public Library", "Queens Public Library (Central Branch)", t, category="family"),
        ])
        self.assertEqual(len(out), 2)

    def test_brunches_at_different_bars_stay_separate(self):
        t = _day_at(4, 11, 30)
        out = _merge([
            _ev("Sunday Drag Brunch", "Rudy's Bar", "Rudy's", t, category="community"),
            _ev("Sunday Jazz Brunch", "DoNYC Citywide", "Lou's", t, category="community"),
        ])
        self.assertEqual(len(out), 2)

    def test_shows_on_one_ticket_page_with_event_ids_stay_separate(self):
        t = _day_at(10, 19)
        out = _merge([
            _ev("Truancy", "Venue A", "The Back Room", t, url="https://tickets.example.com/perf.asp?evt=1601"),
            _ev("Chick Singer Night", "Venue B", "Another Room", t, url="https://tickets.example.com/perf.asp?evt=1557"),
        ])
        self.assertEqual(len(out), 2)


class TitleHelpers(unittest.TestCase):
    def test_title_numbers(self):
        self.assertEqual(T._title_numbers("Round 3"), {"3"})
        self.assertEqual(T._title_numbers("Ages 27-37"), {"27", "37"})
        self.assertEqual(T._title_numbers("Show 2026"), frozenset())
        for t in ("Hunxho (16+)", "CamelPhat 21 and over", "11/06 Rooftop", "Friday, December 11th", "Doors 7:30", "Show at 8pm"):
            self.assertFalse(T._title_numbers(t), t)

    def test_titles_unrelated(self):
        self.assertTrue(T._titles_unrelated("Yoga in the Park", "Salsa Social"))
        self.assertFalse(T._titles_unrelated("Yoga in the Park", "Sunset Yoga"))
        self.assertFalse(T._titles_unrelated("half•alive", "halfalive"))
        self.assertFalse(T._titles_unrelated("Anything", None))

    def test_clean_url_keeps_event_ids_only(self):
        self.assertEqual(T._clean_event_url("https://x.com/p.asp?evt=12&utm_source=a"), "https://x.com/p.asp?evt=12")
        self.assertEqual(T._clean_event_url("https://x.com/shows/?utm_source=a"), "https://x.com/shows")


class AlsoListedOnCards(unittest.TestCase):
    def test_card_shows_an_absorbed_listings_title_when_unrelated(self):
        # Direct: the alt carries its title and the renderer labels it.
        t = _day_at(3, 20)
        out = _merge([
            _ev("A Conversation with Ada Limon", "Kaufmann Concert Hall", "Kaufmann Concert Hall", t, category="books",
                url="https://92ny.example/ada"),
            _ev("Ada Limon: The Hurting Kind", "Greenlight Bookstore", "Kaufmann Concert Hall", t, category="books",
                url="https://greenlight.example/ada"),
        ])
        self.assertEqual(out[0]["_alt_sources"][0].get("name"), "Ada Limon: The Hurting Kind")


if __name__ == "__main__":
    unittest.main()


class OneTimePerCard(unittest.TestCase):
    """A card's label, sort time, epoch, calendar date and "also" note never disagree."""

    def setUp(self):
        self.out = _merge([
            _ev("Daniel Lanois", "SeatGeek NYC", "Le Poisson Rouge", _day_at(3, 18, 30),
                url="https://seatgeek.com/daniel-lanois-tickets/1"),
            _ev("Daniel Lanois Trio In The Round", "Le Poisson Rouge", "Le Poisson Rouge", _day_at(3, 19, 30),
                url="https://kyd.to/KjMophJk"),
        ])

    def test_date_follows_the_winning_time(self):
        e = self.out[0]
        self.assertEqual(datetime.fromisoformat(e["date"]), e["_time"])
        self.assertEqual(T.format_when(e), "7:30 PM")

    def test_other_calendars_time_is_shown_not_hidden(self):
        e = self.out[0]
        self.assertEqual([t.strftime("%H:%M") for t in e["_other_times"]], ["18:30"])
        self.assertIn("also 6:30 PM", T._other_times_html(e))

    def test_label_is_the_sort_time_even_if_date_is_stale(self):
        e = dict(self.out[0], date=_day_at(3, 18, 30).isoformat())
        self.assertEqual(T.format_when(e), "7:30 PM")

    def test_rendered_cards_match_their_sort_time(self):
        import re
        html = T.render_page({"generated_at": datetime.now(EASTERN).isoformat(), "venues": [
            {"venue": "SeatGeek NYC", "url": "https://seatgeek.com/", "events": [
                {"name": "Daniel Lanois", "date": _day_at(1, 18, 30).isoformat(), "venue": "Le Poisson Rouge",
                 "url": "https://seatgeek.com/daniel-lanois-tickets/1", "category": "music"}]},
            {"venue": "Le Poisson Rouge", "url": "https://lpr.com/", "events": [
                {"name": "Daniel Lanois Trio In The Round", "date": _day_at(1, 19, 30).isoformat(),
                 "venue": "Le Poisson Rouge", "url": "https://kyd.to/KjMophJk", "category": "music"}]},
        ]})
        cards = re.findall(r'data-time-mins="(\d+)"[^>]*><div class="when">(\d+):(\d\d) ([AP]M)', html)
        self.assertTrue(cards)
        for mins, h, m, ap in cards:
            self.assertEqual(int(mins), (int(h) % 12 + (12 if ap == "PM" else 0)) * 60 + int(m))
