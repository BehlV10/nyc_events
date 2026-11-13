import json, os, sys, tempfile, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import scrapers  # noqa: E402


class MeetupGroupTests(unittest.TestCase):
    def test_loader_skips_bad_slugs(self):
        with tempfile.TemporaryDirectory() as t:
            p = os.path.join(t, "g.json")
            json.dump({"groups": [{"slug": "good-group", "category": "music"}, {"slug": "bad/slug"}, {"slug": "x y"}, {"slug": "ok2"}]}, open(p, "w"))
            self.assertEqual(scrapers._load_meetup_groups(p), [("good-group", "music"), ("ok2", "community")])
        self.assertEqual(scrapers._load_meetup_groups("/nonexistent.json"), [])

    def test_groups_are_sources_on_the_meetup_lane(self):
        groups = [v for v in scrapers._ALL_VENUES if v["name"].startswith("Meetup group: ")]
        self.assertTrue(groups)
        self.assertTrue(all(v["url"].startswith("https://www.meetup.com/") and v["scraper"] is scrapers.scrape_meetup for v in groups))
        self.assertEqual(len({v["name"] for v in groups}), len(groups))


if __name__ == "__main__":
    unittest.main()
