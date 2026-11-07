"""Museum exhibitions: read from each museum's page, shown under "On view now" rather than on a day."""
import os
import sys
import unittest
from datetime import date, datetime, timedelta, timezone
from unittest import mock

from bs4 import BeautifulSoup

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import scrapers  # noqa: E402
import template as T  # noqa: E402
from scrapers import _exhibit_dates  # noqa: E402

TODAY = date(2026, 11, 6)


class ExhibitDates(unittest.TestCase):
    def test_through(self):
        self.assertEqual(_exhibit_dates("Roy Lichtenstein: Like New Through May 10, 2027", TODAY), (None, date(2027, 5, 10)))
        self.assertEqual(_exhibit_dates("On View Through February 15, 2027", TODAY), (None, date(2027, 2, 15)))

    def test_through_with_no_year_is_the_next_one(self):
        self.assertEqual(_exhibit_dates("Through January 18", TODAY), (None, date(2027, 1, 18)))
        self.assertEqual(_exhibit_dates("Through November 29", TODAY), (None, date(2026, 11, 29)))

    def test_ranges(self):
        self.assertEqual(_exhibit_dates("Oct. 15, 2026 – Jan. 11, 2027", TODAY), (date(2026, 10, 15), date(2027, 1, 11)))
        self.assertEqual(_exhibit_dates("nephomancer OCTOBER 29–DECEMBER 6, 2026", TODAY), (date(2026, 10, 29), date(2026, 12, 6)))
        self.assertEqual(_exhibit_dates("Sep.\xa018,\xa02026 – Feb.\xa07,\xa02027", TODAY), (date(2026, 9, 18), date(2027, 2, 7)))

    def test_upcoming_or_open_ended_have_no_end(self):
        for text in ("Opens November 20, 2026", "Ongoing Raise Your Voice", "Permanent collection"):
            self.assertEqual(_exhibit_dates(text, TODAY), (None, None), text)


class ReadingAPage(unittest.TestCase):
    PAGE = """<html><body><nav><a href="/exhibitions/nav-link">Nope Through Jan 1, 2027</a></nav>
    <div class="grid">
      <div class="card"><a href="/exhibitions/one"><h3>Tone Tone</h3></a><p>Through January 3, 2027</p></div>
      <div class="card"><a href="/exhibitions/two"><img></a><a href="/exhibitions/two">On View Second Show</a><span>Oct. 1, 2026 – Dec. 1, 2026</span></div>
      <div class="card"><a href="/exhibitions/three"><h3>Next Year's Show</h3></a><p>Feb. 1, 2027 – May 1, 2027</p></div>
      <div class="card"><a href="/exhibitions/four"><h3>Opening Soon</h3></a><p>Opens March 12, 2027</p></div>
      <div class="card"><a href="/exhibitions/five"><h3>Closed Show</h3></a><p>Through March 12, 2026</p></div>
      <div class="card"><a href="/exhibitions/six"><h3>No Dates Here</h3></a></div>
    </div></body></html>"""

    def _scrape(self):
        soup = BeautifulSoup(self.PAGE, "html.parser")
        pages = (("Test Museum", "1 Main St, New York, NY", "https://museum.example/exhibitions", r"/exhibitions/[a-z]+"),)
        now = datetime(2026, 11, 6, 12, tzinfo=scrapers.EASTERN)

        class Frozen(datetime):
            @classmethod
            def now(cls, tz=None):
                return now

        with mock.patch.object(scrapers, "fetch_soup", return_value=soup), mock.patch.object(scrapers, "_EXHIBITION_PAGES", pages), \
                mock.patch.object(scrapers, "datetime", Frozen):
            return scrapers.scrape_museum_exhibitions("u", "ua")

    def test_only_what_is_on_view_now(self):
        self.assertEqual({e["name"] for e in self._scrape()}, {"Tone", "Second Show"})

    def test_undated_with_a_closing_date(self):
        e = next(x for x in self._scrape() if x["name"] == "Tone")
        self.assertIsNone(e["date"])
        self.assertEqual(e["ends"], "2027-01-03")
        self.assertTrue(e["_exhibition"])
        self.assertEqual(e["url"], "https://museum.example/exhibitions/one")

    def test_a_shared_box_doesnt_lend_its_dates(self):
        soup = BeautifulSoup("""<ul><li><a href="/exhibitions/a">A</a></li><li><a href="/exhibitions/b">B</a></li>
            <li>Through May 1, 2027</li></ul>""", "html.parser")
        self.assertEqual(list(scrapers._exhibit_cards(soup, "https://m.example/exhibitions", r"/exhibitions/[a-z]+")), [])

    def test_one_museum_failing_keeps_the_others(self):
        pages = (("A", "x", "https://a.example/", r"/e/"), ("B", "x", "https://b.example/", r"/e/"))
        soup = BeautifulSoup("<p></p>", "html.parser")
        with mock.patch.object(scrapers, "fetch_soup", side_effect=[RuntimeError("403"), soup]), mock.patch.object(scrapers, "_EXHIBITION_PAGES", pages):
            self.assertEqual(scrapers.scrape_museum_exhibitions("u", "ua"), [])
        with mock.patch.object(scrapers, "fetch_soup", side_effect=RuntimeError("403")), mock.patch.object(scrapers, "_EXHIBITION_PAGES", pages), \
                self.assertRaises(RuntimeError):
            scrapers.scrape_museum_exhibitions("u", "ua")


class OnViewSection(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        when = (datetime.now(timezone.utc) + timedelta(hours=3)).isoformat()
        cls.html = T.render_page({"generated_at": when, "venues": [
            {"venue": "Museum Exhibitions", "url": "https://m.example/", "error": None, "events": [
                {"name": "Later Show", "date": None, "ends": "2027-05-01", "url": "https://m.example/1", "venue": "Whitney Museum of American Art",
                 "category": "art", "_exhibition": True},
                {"name": "Closing Soon", "date": None, "ends": "2027-01-03", "url": "https://m.example/2", "venue": "Whitney Museum of American Art",
                 "category": "art", "_exhibition": True},
            ]},
            {"venue": "Rockwood", "url": "https://r.example/", "error": None,
             "events": [{"name": "Folk Night", "date": when, "venue": "Rockwood", "url": "https://r.example/1", "category": "music"}]},
        ]})

    def test_appears_in_its_own_section_not_date_tba(self):
        self.assertIn("On view now", self.html)
        section = self.html[self.html.index('<section class="ongoing">'):]
        self.assertIn("Closing Soon", section[:section.index("</section>")])
        self.assertNotIn("Date TBA", self.html[:self.html.index('<section class="ongoing">')].split("<body")[1].split("<main")[0])

    def test_closing_soonest_first_with_the_date_on_the_card(self):
        section = self.html[self.html.index('<section class="ongoing">'):]
        self.assertLess(section.index("Closing Soon"), section.index("Later Show"))
        self.assertIn("thru 1/3", section)

    def test_shows_on_the_opening_view(self):
        self.assertIn("timeFilter === 'today'", self.html[self.html.index("const showOngoing"):][:160])


if __name__ == "__main__":
    unittest.main()
