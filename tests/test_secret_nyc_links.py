"""Secret NYC listings link straight to the ticket seller (Fever etc.), not to the Secret NYC article."""
import json
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
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


def _fever_page(name="Winter Lantern Festival (Snug Harbor)", city="new-york", days=3):
    """A trimmed Fever plan page: the embedded app state carries the plan, its sessions and prices."""
    start = datetime.now(timezone.utc).astimezone(scrapers.EASTERN).replace(hour=18, minute=30, second=0, microsecond=0) + timedelta(days=days)
    sess = {"label": "Adult", "starts_at_iso": start.isoformat(), "ends_at_iso": (start + timedelta(hours=3, minutes=30)).isoformat()}
    state = {
        "immersive-plan-detail:7:x": {
            "id": 7, "name": name, "citySlug": city, "description": "<p>Hundreds of lanterns.</p>",
            "firstActiveSessionDate": start.isoformat(), "lastActiveSessionDate": (start + timedelta(days=50)).isoformat(),
            "defaultPlace": {"name": "Snug Harbor", "address": "1000 Richmond Terrace, Staten Island, 10301",
                             "latitude": "40.64425", "longitude": "-74.101504"}},
        "PlanService.getPlanSessionsForPlaceAndDate.7.1.x..": {"level": {"items": [{"value": sess}]}},
        "PlanService.getPlanAvailabilityForPlace.7.1.x": {"dates": {"2026-11-19": {"minTicketPrice": 18.89}, "2026-11-20": {"minTicketPrice": 24.99}}},
    }
    return f'<html><script id="serverapp-state" type="application/json">{json.dumps(state)}</script></html>', start


class FeverPlanTests(unittest.TestCase):
    def test_plan_page_becomes_one_real_listing(self):
        page, start = _fever_page()
        e = scrapers._fever_plan_event(page, "https://feverup.com/en/new-york/m/7?utm_source=x")
        self.assertEqual(e["name"], "Winter Lantern Festival (Snug Harbor)")
        self.assertEqual(e["venue"], "Snug Harbor")
        self.assertEqual(e["address"], "1000 Richmond Terrace, Staten Island, 10301, NY")
        self.assertEqual(e["price"], "From $19")
        self.assertEqual(e["url"], "https://feverup.com/m/7")
        self.assertEqual(datetime.fromisoformat(e["date"]), start.astimezone(timezone.utc))
        self.assertEqual(datetime.fromisoformat(e["end"]) - datetime.fromisoformat(e["date"]), timedelta(hours=3, minutes=30))
        self.assertAlmostEqual(e["lat"], 40.64425)
        self.assertTrue(e["description"].startswith("Runs through"))

    def test_outside_the_city_and_pages_without_state_are_skipped(self):
        yorktown = _fever_page()[0].replace("40.64425", "41.29").replace("-74.101504", "-73.83")
        self.assertIsNone(scrapers._fever_plan_event(yorktown, "https://feverup.com/m/7"))
        self.assertIsNone(scrapers._fever_plan_event("<html>no state</html>", "https://feverup.com/m/7"))

    def test_brooklyn_market_plans_count_and_attractions_do_not(self):
        brooklyn = _fever_page(city="brooklyn-ny-us")[0]
        self.assertEqual(scrapers._fever_plan_event(brooklyn, "https://feverup.com/m/7")["venue"], "Snug Harbor")
        no_coords = _fever_page(city="boston")[0].replace('"latitude": "40.64425", "longitude": "-74.101504"', '"x": 1')
        self.assertIsNone(scrapers._fever_plan_event(no_coords, "https://feverup.com/m/7"))
        self.assertIsNone(scrapers._fever_plan_event(_fever_page(name="Empire State Building Observatory Ticket")[0], "https://feverup.com/m/7"))


class ScrapeSecretNycTests(unittest.TestCase):
    FEED = """<rss><channel>
      <item><title>Best things to do this weekend</title><content:encoded><![CDATA[
        <p>Go see <a href="https://feverup.com/m/7?utm_source=sn">lanterns</a>, follow
        <a href="https://www.instagram.com/secret_nyc/">us</a>, or read <a href="https://secretnyc.co/other/">more</a>.</p>]]></content:encoded></item>
      <item><title>A festival lights up Staten Island</title><content:encoded><![CDATA[<p>Pure headline, no links.</p>]]></content:encoded></item>
    </channel></rss>"""

    def _run(self, feed=FEED, jsonld=None):
        resp = SimpleNamespace(content=feed.encode(), raise_for_status=lambda: None)
        fever_page = _fever_page()[0]
        jsonld = jsonld if jsonld is not None else (lambda url, ua: [])
        with patch.object(scrapers._SESSION, "get", return_value=resp), \
             patch.object(scrapers, "fetch_soup", return_value=BeautifulSoup("<html></html>", "html.parser")), \
             patch.object(scrapers, "fetch_text", return_value=(200, fever_page)) as ft, \
             patch.object(scrapers, "scrape_jsonld", side_effect=jsonld):
            return scrapers.scrape_secret_nyc("https://secretnyc.co/", "ua"), ft

    def test_links_resolve_to_fever_pages_and_headlines_make_nothing(self):
        events, fetch = self._run()
        self.assertEqual([e["name"] for e in events], ["Winter Lantern Festival (Snug Harbor)"])
        self.assertEqual(events[0]["url"], "https://feverup.com/m/7")
        self.assertEqual(fetch.call_count, 1)  # instagram / secretnyc.co links are never fetched

    def test_headline_only_feed_produces_no_events(self):
        events, fetch = self._run(feed="<rss><channel><item><title>Lanterns!</title><content:encoded><![CDATA[<p>x</p>]]></content:encoded></item></channel></rss>")
        self.assertEqual(events, [])
        fetch.assert_not_called()

    def test_other_sites_count_only_through_their_event_data(self):
        feed = """<rss><channel><item><title>t</title><content:encoded><![CDATA[
            <a href="https://venue.example/show?utm_source=sn">a</a> <a href="https://empty.example/">b</a>]]></content:encoded></item></channel></rss>"""
        future = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()

        def jsonld(url, ua):
            return [{"name": "Real Show", "date": future, "venue": "Venue", "url": url}] if "venue.example" in url else []
        events, _ = self._run(feed=feed, jsonld=jsonld)
        self.assertEqual([e["name"] for e in events], ["Real Show"])


class BbgLightscapeTests(unittest.TestCase):
    def _page(self, start, end):
        fmt = lambda d: f"{d.strftime('%B')}\xa0{d.day},\xa0{d.year}"
        return BeautifulSoup(f"<main>Lightscape The Magic Returns! {fmt(start)}\u2013{fmt(end)} Get Tickets Adult $29 $39 $44 Child $15</main>", "html.parser")

    def test_before_opening_it_sits_on_opening_day_then_on_view(self):
        today = datetime.now(scrapers.EASTERN).date()
        with patch.object(scrapers, "fetch_soup", return_value=self._page(today + timedelta(days=7), today + timedelta(days=50))):
            (e,) = scrapers.scrape_bbg_lightscape("https://www.bbg.org/lightscape", "ua")
        self.assertEqual(e["price"], "From $29")
        self.assertNotIn("_exhibition", e)
        self.assertEqual(datetime.fromisoformat(e["date"]).astimezone(scrapers.EASTERN).date(), today + timedelta(days=7))
        with patch.object(scrapers, "fetch_soup", return_value=self._page(today - timedelta(days=3), today + timedelta(days=30))):
            (e,) = scrapers.scrape_bbg_lightscape("https://www.bbg.org/lightscape", "ua")
        self.assertTrue(e["_exhibition"])
        self.assertIsNone(e["date"])
        self.assertEqual(e["ends"], (today + timedelta(days=30)).isoformat())
        with patch.object(scrapers, "fetch_soup", return_value=self._page(today - timedelta(days=30), today - timedelta(days=1))):
            self.assertEqual(scrapers.scrape_bbg_lightscape("https://www.bbg.org/lightscape", "ua"), [])


if __name__ == "__main__":
    unittest.main()
