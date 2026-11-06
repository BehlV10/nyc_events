"""Sold-out titles and band names at music venues."""
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import scrapers  # noqa: E402
from scrapers import keep_music_venue_category  # noqa: E402


def clean(name, **extra):
    when = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    return scrapers._clean_scraped_events([dict({"name": name, "date": when, "url": "https://x.example/1"}, **extra)])[0]


class SoldOutTitles(unittest.TestCase):
    def test_note_moves_from_the_title_to_the_price(self):
        for title, name in (("[SOLD OUT] Fahim Anwar", "Fahim Anwar"), ("SOLD OUT - Jacqueline Novak", "Jacqueline Novak"),
                            ("SOLD OUT: DANNA- THE BEDROOM SESSIONS US TOUR", "DANNA- THE BEDROOM SESSIONS US TOUR"),
                            ("Fabrizio - SOLD OUT", "Fabrizio"), ("Jackie Evans SOLD OUT", "Jackie Evans"),
                            ("Teksupport: Volkoder (all night long) SOLD OUT", "Teksupport: Volkoder (all night long)"),
                            ("Late Show (Sold Out)", "Late Show")):
            e = clean(title)
            self.assertEqual(e["name"], name)
            self.assertEqual(e["price"], "Sold out")

    def test_a_listed_price_is_kept(self):
        self.assertEqual(clean("SOLD OUT: Show", price="$25")["price"], "$25 (sold out)")
        self.assertEqual(clean("SOLD OUT: Show", price="Sold Out")["price"], "Sold Out")

    def test_is_stable_when_cached_events_are_cleaned_again(self):
        e = clean("SOLD OUT: Show", price="$25")
        self.assertEqual(scrapers._clean_scraped_events([e])[0]["price"], "$25 (sold out)")

    def test_a_title_about_something_else_stays(self):
        self.assertEqual(clean("Speed dating for NYC Singles (30s/40s) Women Sold Out")["name"],
                         "Speed dating for NYC Singles (30s/40s) Women Sold Out")


class MusicVenueBands(unittest.TestCase):
    def test_band_with_a_keyword_in_its_name_stays_music(self):
        self.assertEqual(keep_music_venue_category("books", "music", "Indie band from Queens with a new album"), "music")

    def test_without_evidence_the_guess_stands(self):
        self.assertEqual(keep_music_venue_category("books", "music", "Monthly reading group"), "books")

    def test_only_at_music_sources(self):
        self.assertEqual(keep_music_venue_category("books", "community", "Indie band"), "books")

    def test_what_music_venues_really_host_is_left_alone(self):
        for cat in ("comedy", "gaming", "clubbing"):
            self.assertEqual(keep_music_venue_category(cat, "music", "Live band"), cat)


if __name__ == "__main__":
    unittest.main()
