"""The PR card diff lists what a change adds, removes, recategorizes and relinks."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import card_diff  # noqa: E402


class CardDiff(unittest.TestCase):
    def test_report_lists_each_kind_of_change(self):
        base = {"d | Wicked | Gershwin": {"category": "theater", "url": "https://allevents.in/w"},
                "d | Hookah Night | Egypt": {"category": "clubbing", "url": "u1"},
                "d | Farmers Market | Fort Hamilton": {"category": "theater", "url": "u2"}}
        head = {"d | Wicked | Gershwin": {"category": "theater", "url": "https://www.ticketmaster.com/w"},
                "d | Farmers Market | Fort Hamilton": {"category": "markets", "url": "u2"},
                "d | New Show | Town Hall": {"category": "music", "url": "u3"}}
        md = card_diff.compare(base, head)
        self.assertIn("**1 gone, 1 new, 1 changed category, 1 changed link**", md)
        self.assertIn("- d | Hookah Night | Egypt  (clubbing)", md)
        self.assertIn("- d | Farmers Market | Fort Hamilton: theater → markets", md)
        self.assertIn("allevents.in/w → https://www.ticketmaster.com/w", md)

    def test_no_difference(self):
        same = {"d | A | B": {"category": "music", "url": "u"}}
        self.assertIn("No difference", card_diff.compare(same, dict(same)))


if __name__ == "__main__":
    unittest.main()
