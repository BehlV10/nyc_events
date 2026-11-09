"""Dated holiday themes recolor the skyline, and the site has real icon files."""
import json
import os
import re
import sys
import unittest
from datetime import date, datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import holiday_themes as H  # noqa: E402
import seo  # noqa: E402
import template as T  # noqa: E402


class HolidayCalendar(unittest.TestCase):
    def test_nyc_dates(self):
        cases = {date(2026, 11, 1): "marathon", date(2027, 11, 7): "marathon", date(2027, 6, 27): "pride",
                 date(2027, 6, 13): "prparade", date(2026, 11, 8): "diwali", date(2026, 11, 26): "thanksgiving",
                 date(2026, 12, 31): "newyearseve", date(2027, 3, 17): "stpatricks", date(2027, 7, 4): "july4"}
        for d, key in cases.items():
            self.assertEqual(H.holiday_on(d)["key"], key, d)
        self.assertIsNone(H.holiday_on(date(2026, 11, 4)))

    def test_no_boston_holidays_left(self):
        text = json.dumps([{k: v for k, v in h.items() if k in ("key", "label", "greeting")} for h in H.HOLIDAYS])
        for word in ("Boston", "Fenway", "Bunker", "Charles", "Patriots"):
            self.assertNotIn(word, text)

    def test_calendar_lists_each_holiday_day(self):
        cal = H.holiday_calendar(date(2026, 11, 4), 30)
        self.assertEqual(cal["2026-11-11"], "veterans")
        self.assertNotIn("2026-11-04", cal)


class HolidayCss(unittest.TestCase):
    def test_every_holiday_has_a_greeting_rule(self):
        css = H.holiday_theme_css()
        for h in H.HOLIDAYS:
            self.assertIn(f'.holiday-greeting[data-for="{h["key"]}"]', css)

    def test_palette_holidays_recolor_the_skyline(self):
        css = H.holiday_theme_css()
        self.assertRegex(css, r'\[data-theme="diwali"\] \.banner-svg-wrap \{ --sky1: #0b0420;')

    def test_css_braces_balance(self):
        css = H.holiday_theme_css()
        self.assertEqual(css.count("{"), css.count("}"))

    def test_holiday_banners_exist_and_linked(self):
        next_8 = ["veterans", "thanksgiving", "blackfriday", "cybermonday", "hanukkah", "christmas", "newyearseve", "newyear"]
        css = H.holiday_theme_css()
        for key in next_8:
            svg_path = os.path.join(ROOT, "static", "holidays", f"{key}.svg")
            self.assertTrue(os.path.exists(svg_path), f"Missing banner SVG: {svg_path}")
            self.assertGreater(os.path.getsize(svg_path), 5000, f"SVG banner too small: {svg_path}")
            self.assertIn(f"static/holidays/{key}.svg", css)


class HolidayPage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        when = (datetime.now(timezone.utc) + timedelta(hours=3)).isoformat()
        cls.html = T.render_page({"generated_at": when, "venues": [
            {"venue": "Rockwood", "url": "https://r.example/", "error": None,
             "events": [{"name": "Folk Night", "date": when, "venue": "Rockwood", "url": "https://r.example/1", "category": "music"}]}]})

    def test_skyline_colors_are_variables_with_the_usual_defaults(self):
        self.assertIn("stop-color: var(--sky1, #0c0926)", self.html)
        self.assertIn("stop-color: var(--water1, #142852)", self.html)

    def test_calendar_and_theme_choice_reach_the_page(self):
        self.assertIn("var HOLIDAY_CALENDAR = ", self.html)
        self.assertIn("var HOLIDAY_META = ", self.html)
        self.assertIn("id=\"theme-pill-holiday\"", self.html)
        self.assertIn("if (holiday) return (pickedOn === today && stored) ? stored : holiday;", self.html)
        self.assertIn("const VALID_THEMES = BASE_THEMES.concat(HOLIDAY_KEYS);", self.html)

    def test_a_pick_lasts_the_day_so_the_next_holiday_still_shows(self):
        self.assertIn("localStorage.setItem(THEME_MANUAL_KEY, localISODate(new Date()))", self.html)

    def test_greetings_rendered(self):
        self.assertEqual(self.html.count('class="holiday-greeting"'), len(H.HOLIDAYS))


class Icons(unittest.TestCase):
    def test_files_exist(self):
        for name in ("favicon.ico", "favicon.svg", "apple-touch-icon.png", "logo-192.png", "logo-512.png", "site.webmanifest"):
            self.assertTrue(os.path.getsize(os.path.join(ROOT, name)) > 100, name)

    def test_every_page_links_real_icons(self):
        head = seo.build_seo_meta_tags(site_url="https://behlv10.github.io/nyc_events")
        self.assertIn('href="https://behlv10.github.io/nyc_events/favicon.ico"', head)
        self.assertIn('rel="apple-touch-icon"', head)
        self.assertIn('rel="manifest"', head)
        self.assertNotIn("data:image/svg", open(os.path.join(ROOT, "template.py"), encoding="utf-8").read())

    def test_manifest_paths_stay_under_the_project_path(self):
        m = json.load(open(os.path.join(ROOT, "site.webmanifest"), encoding="utf-8"))
        self.assertEqual(m["start_url"], "./")
        self.assertFalse([i for i in m["icons"] if i["src"].startswith("/")])


if __name__ == "__main__":
    unittest.main()
