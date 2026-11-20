"""Tests for frontend & mobile UX features ported from boston_events (#144, #145, #150, #151, #153)."""
import os
import re
import sys
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import scrapers as S  # noqa: E402
import template as T  # noqa: E402


class TestFrontendUxPorts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        when = (datetime.now(S.EASTERN) + timedelta(days=1)).replace(hour=20, minute=0, second=0, microsecond=0)
        iso = when.astimezone(timezone.utc).isoformat()
        payload = {
            "venues": [
                {
                    "venue": "Zebra Club",
                    "url": "https://zebra.example",
                    "events": [
                        {"name": "Indie Night", "venue": "Zebra Club", "date": iso, "category": "music",
                         "url": "https://zebra.example/e/1", "description": "Great show"},
                    ],
                },
                {
                    "venue": "Alpha Hall",
                    "url": "https://alpha.example",
                    "events": [
                        {"name": "Comedy Hour", "venue": "Alpha Hall", "date": iso, "category": "comedy",
                         "url": "https://alpha.example/e/2"},
                    ],
                },
                {
                    "venue": "Ticketmaster NYC",
                    "url": "https://www.ticketmaster.com",
                    "events": [
                        {"name": "Indie Night", "venue": "Zebra Club", "date": iso, "category": "music",
                         "url": "https://www.ticketmaster.com/event/123"},
                    ],
                },
            ]
        }
        cls.html = T.render_page(payload)

    def test_mobile_cards_hide_desc_presenter_and_also_on(self):
        self.assertIn(".event .desc, .event .presenter-tag, .event .also-on { display: none; }", self.html)
        self.assertIn('<span class="also-on">', self.html)

    def test_banner_title_links_home_and_clears_saved_filters(self):
        self.assertIn('<h1 class="banner-title"><a href="/" class="banner-home" title="Back to all events">NYC Events</a></h1>', self.html)
        self.assertIn("localStorage.removeItem('nyc_saved_venues')", self.html)

    def test_simple_view_button_css_and_js(self):
        self.assertIn('id="btn-simple-view"', self.html)
        self.assertIn("body.simple-view li.event", self.html)
        self.assertIn("nyc_events_simple_view", self.html)
        self.assertIn('[data-theme="light"] .simple-view-btn', self.html)

    def test_timeframe_popover_full_width_and_single_row_mobile(self):
        self.assertIn('id="timeframe-toggle-btn"', self.html)
        self.assertIn('id="btn-clear-time-window"', self.html)
        self.assertIn(".timeframe-popover {", self.html)
        popover_css = self.html[self.html.index(".timeframe-popover {"):self.html.index(".timeframe-popover {") + 260]
        self.assertIn("width: 100%;", popover_css)
        self.assertIn("box-sizing: border-box;", popover_css)
        self.assertIn("padding: 4px 7px;", self.html)

    def test_boroughs_and_categories_collapsible_on_click(self):
        self.assertIn(".city-section.collapsed > .buckets { display: none; }", self.html)
        self.assertIn(".bucket.collapsed > ul { display: none; }", self.html)
        self.assertIn("e.target.closest('.city-head')", self.html)
        self.assertIn("e.target.closest('.bucket-head')", self.html)

    def test_venues_sorted_alphabetically_in_sidebar(self):
        venues = re.findall(r'class="venue-chk" value="([^"]+)"', self.html)
        self.assertEqual(venues, sorted(venues, key=lambda v: v.lower()))


if __name__ == "__main__":
    unittest.main()
