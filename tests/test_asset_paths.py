"""The site is served from a sub-path (github.io/nyc_events/), so root-absolute asset URLs 404."""
import os
import re
import sys
import unittest
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import template as T  # noqa: E402


class AssetPathTests(unittest.TestCase):
    def test_no_root_absolute_css_urls(self):
        html = T.render_page({"generated_at": datetime.now(timezone.utc).isoformat(), "venues": []})
        bad = re.findall(r"url\(['\"]?/(?!/)[^)]*\)", html)
        self.assertEqual(bad, [], "root-absolute url() breaks on a project Pages site; use a relative path")

    def test_banner_is_relative(self):
        html = T.render_page({"generated_at": datetime.now(timezone.utc).isoformat(), "venues": []})
        self.assertIn("url('banner.jpg')", html)


if __name__ == "__main__":
    unittest.main()
