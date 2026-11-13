"""Secret NYC listings link straight to the ticket seller (Fever etc.), not to the Secret NYC article."""
import os
import sys
import unittest
from unittest.mock import patch

from bs4 import BeautifulSoup

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import scrapers  # noqa: E402


class DirectLinkTests(unittest.TestCase):
    def test_prefers_ticket_platform_and_drops_noise(self):
        links = ["https://secretnyc.co/other-article/", "https://www.instagram.com/x", "https://feverup.com/legal/terms_en.html",
                 "https://venue.example/show?utm_source=sn&id=2", "https://feverup.com/m/42?utm_medium=email"]
        self.assertEqual(scrapers._secret_direct_link(links), "https://feverup.com/m/42")

    def test_falls_back_to_other_site_then_none(self):
        self.assertEqual(scrapers._secret_direct_link(["https://venue.example/show?utm_source=sn&id=2"]), "https://venue.example/show?id=2")
        self.assertIsNone(scrapers._secret_direct_link(["https://secretnyc.co/x", "mailto:a@b.c", "/relative"]))
        self.assertIsNone(scrapers._secret_direct_link([]))

    def test_section_links_stop_at_next_heading_row(self):
        html = ('<div class="module-heading-row"><h2>One</h2></div><p>x <a href="https://feverup.com/m/1">t</a></p>'
                '<div class="btn"><a href="https://feverup.com/m/2">Buy</a></div>'
                '<div class="module-heading-row"><h2>Two</h2></div><p><a href="https://feverup.com/m/3">t</a></p>')
        rows = BeautifulSoup(html, "html.parser").find_all("div", class_="module-heading-row")
        self.assertEqual(scrapers._secret_section_links(rows[0]), ["https://feverup.com/m/1", "https://feverup.com/m/2"])
        self.assertEqual(scrapers._secret_section_links(None), [])


class ScrapeSecretNycTests(unittest.TestCase):
    def test_no_listing_points_at_the_guide_when_a_direct_link_exists(self):
        guide = BeautifulSoup(
            '<div class="module-heading-row"><h2>Sip a holiday cocktail carol</h2></div>'
            '<p>An immersive christmas show.</p><div><a href="https://feverup.com/m/784122?utm_source=sn">Buy tickets</a></div>',
            "html.parser")
        with patch.object(scrapers, "fetch_soup", return_value=guide), \
             patch.object(scrapers._SESSION, "get", side_effect=RuntimeError("no feed")), \
             patch.object(scrapers, "_is_within_horizon", return_value=True):
            events = scrapers.scrape_secret_nyc("https://secretnyc.co/", "ua")
        urls = {e["name"]: e["url"] for e in events}
        self.assertEqual(urls["Sip a holiday cocktail carol"], "https://feverup.com/m/784122")
        for name, u in urls.items():
            if "Cocktail Carol" in name or "Luminiscence" in name:
                self.assertTrue(u.startswith("https://feverup.com/m/"), (name, u))
        highlights = [u for n, u in urls.items() if n != "Sip a holiday cocktail carol"]
        self.assertEqual(len(highlights), 6)
        self.assertFalse([u for u in highlights if "secretnyc.co" in u], highlights)


if __name__ == "__main__":
    unittest.main()
