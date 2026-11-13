"""The Skint's "ongoing events" roundup becomes On-view-now listings with the organiser's own link."""
import os
import sys
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

from bs4 import BeautifulSoup

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import scrapers  # noqa: E402


def _md(days):
    d = datetime.now(scrapers.EASTERN).date() + timedelta(days=days)
    return f"{d.month}/{d.day}", d


class SkintOngoingTests(unittest.TestCase):
    def _run(self):
        m_end, m_date = _md(40)
        x_end, x_date = _md(20)
        past, _ = _md(-5)
        html = f"""<div class="entry-content">
          <p>holiday markets :</p>
          <p><a href="https://urbanspace.example/union-square">&#9658; thru {m_end}: union square holiday market : urbanspace's market returns, free. <a href="https://urbanspace.example/union-square">&gt;&gt;</a></a></p>
          <p>ice skating! lace up at these rinks:</p>
          <p>&#9658; domino park (thru {x_end}) <a href="https://domino.example/skate">&gt;&gt;</a> &#9658; wollman rink (thru {x_end}) <a href="https://wollman.example/">&gt;&gt;</a></p>
          <p>&#9658; thru {x_end} (fri-sun 12-6pm): the big show : a retrospective at the whitney museum of american art (meatpacking district), $30. <a href="https://whitney.example/show">&gt;&gt;</a></p>
          <p>&#9658; thru {past}: already over : gone. <a href="https://gone.example/">&gt;&gt;</a></p>
          <p>sponsored : thru {x_end}: buy this : ad. <a href="https://ad.example/">&gt;&gt;</a></p>
          <p>subscribe to the skint daily email</p></div>"""
        with patch.object(scrapers, "fetch_soup", return_value=BeautifulSoup(html, "html.parser")):
            return {e["name"]: e for e in scrapers.scrape_skint_ongoing("https://www.theskint.com/ongoing-events/", "ua")}, m_date, x_date

    def test_items_become_on_view_now_listings_with_their_own_links(self):
        got, m_date, x_date = self._run()
        self.assertEqual(set(got), {"Union Square Holiday Market", "Domino Park", "Wollman Rink", "The Big Show"})
        market = got["Union Square Holiday Market"]
        self.assertTrue(market["_exhibition"])
        self.assertIsNone(market["date"])
        self.assertEqual(market["ends"], m_date.isoformat())
        self.assertEqual((market["url"], market["price"], market["category"]), ("https://urbanspace.example/union-square", "Free", "markets"))

    def test_several_items_in_one_paragraph_each_get_their_own_link_and_section_category(self):
        got, _m, x_date = self._run()
        self.assertEqual(got["Domino Park"]["url"], "https://domino.example/skate")
        self.assertEqual(got["Wollman Rink"]["url"], "https://wollman.example/")
        self.assertEqual(got["Domino Park"]["category"], "outdoors")
        self.assertEqual(got["Domino Park"]["ends"], x_date.isoformat())

    def test_schedule_parenthetical_venue_price_and_museum_category(self):
        show = self._run()[0]["The Big Show"]
        self.assertEqual(show["name"], "The Big Show")
        self.assertEqual(show["venue"], "The Whitney Museum of American Art (Meatpacking District)")
        self.assertEqual((show["price"], show["category"]), ("$30", "art"))

    def test_ended_and_sponsored_items_are_dropped(self):
        got = self._run()[0]
        self.assertNotIn("Already Over", got)
        self.assertNotIn("Buy This", got)


class SkintTitleTests(unittest.TestCase):
    def test_capitals_small_words_and_area_codes(self):
        self.assertEqual(scrapers._skint_title("metrograph (les)"), "Metrograph (LES)")
        self.assertEqual(scrapers._skint_title("winter village at bryant park"), "Winter Village at Bryant Park")


if __name__ == "__main__":
    unittest.main()
