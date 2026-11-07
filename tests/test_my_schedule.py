"""My Schedule: stars, the schedule view and shared links.

The shared page reads everything from a link anyone can write, so these guard how it handles that
text. The full flow (star across weeks, reload, share, open the link, tampered link) was checked
in headless Chrome.
"""
import os
import re
import sys
import unittest
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import template as T  # noqa: E402


def read(*path):
    with open(os.path.join(ROOT, *path), encoding="utf-8") as f:
        return f.read()


class SchedulePage(unittest.TestCase):
    def setUp(self):
        self.page = read("schedule", "index.html")

    def test_link_contents_never_become_html(self):
        script = self.page[self.page.rindex("<script>"):]
        for sink in ("innerHTML", "insertAdjacentHTML", "document.write"):
            self.assertNotIn(sink, script)

    def test_only_web_links_are_kept(self):
        self.assertIn("url.protocol === 'https:' || url.protocol === 'http:'", self.page)

    def test_shared_schedules_stay_out_of_search(self):
        self.assertIn('<meta name="robots" content="noindex">', self.page)

    def test_links_work_under_the_project_path(self):
        """The site lives at /nyc_events/, so a root-relative link would leave it."""
        self.assertNotRegex(self.page, r'href="/')
        self.assertIn('href="../"', self.page)

    def test_events_drop_off_a_day_after_they_start(self):
        self.assertIn("var KEEP_SECONDS = 86400;", self.page)

    def test_untimed_events_are_all_day_on_the_calendar(self):
        self.assertIn("'DTSTART;VALUE=DATE:'", self.page)

    def test_only_one_weekend_is_called_a_weekend(self):
        """Two Fridays three weeks apart read as "Sam's weekend"."""
        self.assertIn("span < 3 * 86400", self.page)

    def test_is_tracked_by_git(self):
        """A bare "index.html" ignore rule hid this page, so it would never have deployed."""
        self.assertIn("!/schedule/index.html", read(".gitignore"))


class ScheduleOnHomePage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        when = (datetime.now(timezone.utc) + timedelta(hours=3)).replace(minute=0, second=0, microsecond=0).isoformat()
        cls.html = T.render_page({"generated_at": when, "venues": [
            {"venue": "Rockwood Music Hall", "url": "https://rockwood.example/", "error": None,
             "events": [{"name": "Folk Night", "date": when, "venue": "Rockwood Music Hall",
                         "url": "https://rockwood.example/e/1", "price": "$20", "category": "music"}]}]})

    def test_every_card_has_a_star(self):
        cards = len(re.findall(r'<li class="event', self.html))
        self.assertGreater(cards, 0)
        self.assertEqual(self.html.count('<button type="button" class="star-btn"'), cards)

    def test_bar_elements_are_declared_before_first_use(self):
        self.assertLess(self.html.index("const scheduleBar = "), self.html.index("function updateQuickChipsUI"))

    def test_untimed_events_are_flagged_rather_than_given_an_hour(self):
        self.assertIn("li.dataset.epoch ? 0 : 1", self.html)

    def test_share_link_is_relative_to_the_page(self):
        self.assertIn("new URL('schedule/', location.href)", self.html)
        self.assertNotIn("location.origin}/schedule/", self.html)

    def test_view_shows_saved_events_whatever_the_filters_and_clock_say(self):
        self.assertIn("const boxOn = b => starredOnly || b.checked;", self.html)
        self.assertIn("if (isPast && !showPastToday && !starredOnly)", self.html)
        self.assertIn("inTime = starDates.has(date);", self.html)

    def test_stars_are_restored_on_weeks_loaded_later(self):
        self.assertIn("days.forEach(markStars);", self.html)

    def test_events_leave_a_day_after_they_start(self):
        self.assertIn("details[k][1] < cutoff", self.html)

    def test_rebuilding_a_heading_drops_its_cached_count(self):
        self.assertIn("day._countEl = null;", self.html)

    def test_day_headings_dont_repeat_the_weekday(self):
        self.assertIn("${prefix ? prefix + ' · ' : ''}${dayName}, ${shortStr}", self.html)


if __name__ == "__main__":
    unittest.main()
