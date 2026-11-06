"""Drop a pin: tap the map, then events sort by distance from the pin like Near Me does from you.

The browser behavior (tap -> pin -> sorted list -> shareable #pin= link -> Reset clears it) was
checked in headless Chrome; these tests keep the pieces wired together in the rendered page.
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import template as T  # noqa: E402


def _render():
    when = (datetime.now(timezone.utc) + timedelta(hours=2)).replace(minute=0, second=0, microsecond=0).isoformat()
    return T.render_page({"generated_at": when, "venues": [
        {"venue": "Rockwood Music Hall", "url": "https://rockwood.example/", "error": None,
         "events": [{"name": "Folk Night", "date": when, "venue": "Rockwood Music Hall",
                     "url": "https://rockwood.example/e/1", "price": "$20", "category": "music"}]}]})


class DropPinTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = _render()

    def test_button_next_to_near_me_and_map_hint(self):
        near, pin, maps = (self.html.index('id="btn-near-me"'), self.html.index('id="btn-drop-pin"'),
                           self.html.index('id="btn-view-map"'))
        self.assertLess(near, pin)
        self.assertLess(pin, maps)
        self.assertIn("Tap the map to drop your pin.", self.html)

    def test_sorting_uses_the_pin_when_there_is_one(self):
        self.assertIn("if (pinCoords) return { lat: pinCoords.lat", self.html)
        self.assertIn("haversineMiles(origin.lat, origin.lng, lat, lng)", self.html)
        self.assertNotIn("haversineMiles(userCoords.lat", self.html)
        self.assertIn("Sorted by distance from ${fromPin ? 'your pin' : 'your location'}", self.html)

    def test_tap_places_pin_only_while_placing(self):
        self.assertIn("if (pinPlacing) placePin(ev.latlng.lat, ev.latlng.lng);", self.html)
        self.assertIn("draggable: true", self.html)

    def test_pin_is_shareable(self):
        self.assertIn("params.set('pin', `${pinCoords.lat},${pinCoords.lng}`)", self.html)
        self.assertIn("params.get('pin').split(',').map(Number)", self.html)

    def test_unchecked_sections_stay_off_the_map_and_near_list(self):
        """Unchecking a category collapses its section (.empty) without hiding each event, so both
        kept showing them."""
        self.assertIn("if (li.closest('.empty')) return;", self.html)
        self.assertIn("filter(ev => !ev.closest('.empty'))", self.html)

    @unittest.skipUnless(shutil.which("node"), "needs node")
    def test_page_script_parses(self):
        """The page's script lives in a Python f-string; a stray brace would break the whole site."""
        main = max(re.findall(r"<script>(.*?)</script>", self.html, re.S), key=len)
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as f:
            f.write(main)
        try:
            proc = subprocess.run(["node", "--check", f.name], capture_output=True, text=True)
        finally:
            os.unlink(f.name)
        self.assertEqual(proc.returncode, 0, proc.stderr)


if __name__ == "__main__":
    unittest.main()
