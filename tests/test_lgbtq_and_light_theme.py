"""The "LGBTQ+ events only" filter and the light theme."""
import os
import re
import sys
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import template as T  # noqa: E402
from lgbtq import is_lgbtq_event  # noqa: E402
from light_theme import LIGHT_THEME_CSS  # noqa: E402


def ev(name, venue="Somewhere", source="Somewhere", description=""):
    return {"name": name, "venue": venue, "_source_venue": source, "description": description}


def _render(events=None):
    when = (datetime.now(timezone.utc) + timedelta(hours=2)).replace(minute=0, second=0, microsecond=0).isoformat()
    events = events or [{"name": "Folk Night", "date": when, "venue": "Rockwood Music Hall",
                         "url": "https://rockwood.example/e/1", "price": "$20", "category": "music"}]
    for e in events:
        e.setdefault("date", when)
    return T.render_page({"generated_at": datetime.now(timezone.utc).isoformat(), "venues": [
        {"venue": "Rockwood Music Hall", "url": "https://rockwood.example/", "error": None, "events": events}]})


class LgbtqTag(unittest.TestCase):
    def test_queer_titles(self):
        for name in ("Queer Board Game Night", "Queeraoke", "Sapphic Speed Dating | NYC LGBTQ+ Singles | 25-45",
                     "Allyship with Trans People", "Holiday Drag Night", "Desi Pride Social",
                     "RuPaul's Drag Race Werq The World 2027 Tour", "Curator Talk | Queer Spaces, Queer Contexts"):
            self.assertTrue(is_lgbtq_event(ev(name)), name)

    def test_queer_venues_and_sources(self):
        self.assertTrue(is_lgbtq_event(ev("Karaoke", venue="The Stonewall Inn", source="DoNYC Citywide")))
        self.assertTrue(is_lgbtq_event(ev("Open Mic", venue="Pieces Bar", source="AllEvents NYC")))
        self.assertTrue(is_lgbtq_event(ev("Board Games", venue="Gay French language practice", source="Meetup: French")))
        self.assertTrue(is_lgbtq_event(ev("Climb Night", source="CRUX LGBTQIA+ Climbing")))
        self.assertTrue(is_lgbtq_event(ev("Monday Meetup", venue="The Center (208 W. 13th Street, New York, NY)")))

    def test_description_terms(self):
        self.assertTrue(is_lgbtq_event(ev("Kingdom Showcase", description="A drag king showcase")))
        self.assertFalse(is_lgbtq_event(ev("Open Mic", description="We take pride in our open mic. Drag a friend!")))

    def test_not_queer(self):
        for name in ("Pride and Prejudice", "Pride & Prejudice: A Musical", "Trans-Siberian Orchestra", "Marvin Gaye Tribute",
                     "Drag Racing Night at the Speedway", "Transit Planning Workshop", "Irish Pride Pub Crawl"):
            self.assertFalse(is_lgbtq_event(ev(name)), name)

    def test_keyword_feeds_and_lookalike_venues_dont_count(self):
        self.assertFalse(is_lgbtq_event(ev("Salsa Classes", source="AllEvents: Lgbt")))
        self.assertFalse(is_lgbtq_event(ev("Speed Dating Rockville Centre", source="Meetup: Gay Speed Dating")))
        self.assertFalse(is_lgbtq_event(ev("Guitar Clinic", venue="Main Drag Music")))
        self.assertFalse(is_lgbtq_event(ev("Book Talk", venue="The Center for Fiction")))


class LgbtqFilter(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = _render([{"name": "Queer Trivia", "venue": "Pieces Bar", "url": "https://x.example/1", "category": "gaming"},
                            {"name": "Folk Night", "venue": "Rockwood Music Hall", "url": "https://x.example/2", "category": "music"}])

    def test_only_tagged_cards_carry_the_flag(self):
        self.assertEqual(self.html.count('data-lgbtq="true"'), 1)

    def test_checkbox_follows_free_events_only(self):
        self.assertLess(self.html.index('id="free-only-chk"'), self.html.index('id="lgbtq-only-chk"'))

    def test_filter_is_wired_everywhere_guestlist_is(self):
        self.assertIn("params.set('lgbtq', '1')", self.html)
        self.assertIn("params.get('lgbtq') === '1'", self.html)
        self.assertEqual(self.html.count("guestlistOk && lgbtqOk"), 2, "both filter passes")
        self.assertIn("if (lgbtqOnlyChk) lgbtqOnlyChk.checked = false;", self.html)


class LightTheme(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = _render()

    def test_picker_has_light_next_to_dark(self):
        self.assertIn('data-theme="light" role="radio"', self.html)
        self.assertIn("'classic', 'light', 'indie'", self.html)

    def test_first_visit_follows_the_device_and_a_pick_sticks(self):
        self.assertIn("matches) ? 'light' : 'classic'", self.html)
        self.assertIn("(stored && BASE_THEMES.indexOf(stored) !== -1) ? stored : systemTheme()", self.html)
        self.assertIn("schemeQuery.addEventListener('change', followDevice)", self.html)

    def test_palette_defined(self):
        block = re.search(r'\[data-theme="light"\] \{(.*?)\}', self.html, re.S).group(1)
        for token in ("--bg", "--card", "--fg", "--muted", "--accent", "--border", "--green"):
            self.assertIn(token + ":", block)
        self.assertIn("color-scheme: light", block)

    def test_overrides_only_touch_the_light_theme(self):
        css = re.sub(r"/\*.*?\*/", "", LIGHT_THEME_CSS, flags=re.S)
        selectors = [s.strip() for sel in re.findall(r"([^{}]+)\{[^{}]*\}", css) for s in sel.split(",")]
        self.assertGreater(len(selectors), 50)
        self.assertEqual([s for s in selectors if not s.startswith('[data-theme="light"]')], [])
        self.assertIn(LIGHT_THEME_CSS.strip()[:40], self.html)

    def test_light_map_shows_tiles_uninverted(self):
        self.assertRegex(LIGHT_THEME_CSS, r'\.osm-dark-tiles \.leaflet-tile-pane \{ filter: saturate')


if __name__ == "__main__":
    unittest.main()


class FreeTiersOnThePage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = _render([
            {"name": "Swing Night", "venue": "The Back Room", "url": "https://x.example/a", "price": "No Cover", "category": "dance"},
            {"name": "Friday Party", "venue": "The DL", "url": "https://x.example/b", "price": "Free - $28.52", "category": "nightlife"},
            {"name": "Park Concert", "venue": "Bryant Park", "url": "https://x.example/c", "price": "Free", "category": "music"},
        ])

    def test_each_tier_is_flagged_and_labelled(self):
        self.assertEqual(self.html.count('data-free="true"'), 2, "free + no cover")
        self.assertEqual(self.html.count('data-free-catch="true"'), 1)
        self.assertIn('class="price free-catch"', self.html)
        self.assertIn("No cover: no charge at the door", self.html)

    def test_catch_checkbox_is_wired(self):
        self.assertIn('id="free-catch-chk"', self.html)
        self.assertIn("params.set('free', (freeCatchChk && freeCatchChk.checked) ? '2' : '1')", self.html)
        self.assertEqual(self.html.count("(freeCatch && "), 2, "both filter passes")

    def test_deals_sidebar_has_only_vetted_clubs(self):
        deals = self.html.split("<h3>Deals &amp; lotteries</h3>", 1)[1].split("</div>\n        </div>", 1)[0]
        for gone in ("slatenyc.com", "nebulanewyork.com", "si-bk.com", "ferry.nyc", "Dueling Pianos"):
            self.assertNotIn(gone, deals)
        self.assertIn("Bossa Nova Civic Club", deals)
        self.assertNotIn("ferry.nyc", self.html)


class MapPinNamesDefault(unittest.TestCase):
    def test_map_starts_with_numbers_only(self):
        html = _render()
        self.assertIn('<div id="leaflet-map" class="leaflet-map hide-pin-names">', html)
        self.assertIn(">🔢 Numbers Only</button>", html)
