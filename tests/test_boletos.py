"""Boletos Express city pages: NYC cards become events, other cities and past dates are dropped."""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import scrapers  # noqa: E402


def _card(href, title, when, where, label="Concert"):
    return f'''<div class="card"><div class="card-wall"><a href="{href}"></a><div class="musicLabel">{label}</div></div>
      <div class="card-body"><h5 class="card-title"><a href="{href}">{title}</a></h5>
      <div class="card-text pb-3"><p>{when}<br>Doors: 7:00pm, Show: 9:30pm<br></p><p>{where}</p></div></div></div>'''


def _page(*cards):
    return f'<div class="eventsListing"><div class="row eventsCards row-flex">{"".join(cards)}</div></div>'


class BoletosExpress(unittest.TestCase):
    def test_reads_nyc_cards_from_every_borough_page(self):
        pages = {
            "new york": _page(_card("./elvis/91176/", "Elvis Martinez", "Monday, December 7, 2099", "Opus Lounge, New York, NY"),
                              _card("./x/1/", "Jersey Show", "Monday, December 7, 2099", "Prudential Center, Newark, NJ"),
                              _card("./y/2/", "Old Show", "Monday, December 7, 2020", "United Palace, New York, NY")),
            "queens": _page(_card("./event.php?event_id=5", "Salsa on Steinway", "Friday, December 11, 2099",
                                  "Ritmos 60, Queens, NY", label="Party"),
                            _card("./elvis/91176/", "Elvis Martinez", "Monday, December 7, 2099", "Opus Lounge, New York, NY")),
        }
        asked = []

        def fake_fetch(url, headers=None):
            city = url.split("city=")[1].replace("+", " ")
            asked.append(city)
            return 200, pages.get(city, _page())
        with mock.patch.object(scrapers, "fetch_text", fake_fetch), mock.patch.object(scrapers.time, "sleep", lambda s: None):
            events = scrapers.scrape_boletosexpress("https://www.boletosexpress.com/", None)
        self.assertEqual(asked, list(scrapers._BOLETOS_CITIES))
        by_name = {e["name"]: e for e in events}
        self.assertEqual(sorted(by_name), ["Elvis Martinez", "Salsa on Steinway"])  # NJ, past and repeat dropped
        self.assertEqual(by_name["Elvis Martinez"]["date"], "2099-12-07T21:30:00-05:00")
        self.assertEqual(by_name["Elvis Martinez"]["url"], "https://www.boletosexpress.com/elvis/91176/")
        self.assertEqual(by_name["Elvis Martinez"]["venue"], "Opus Lounge")
        self.assertEqual(by_name["Salsa on Steinway"]["category"], "clubbing")

    def test_listed_as_a_source(self):
        self.assertTrue([v for v in scrapers.VENUES if v["scraper"] is scrapers.scrape_boletosexpress])


if __name__ == "__main__":
    unittest.main()
