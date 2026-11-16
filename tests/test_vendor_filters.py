"""Vendor organizers (tour operators, cruises, daily promos) are held for review instead of
published, and dance classes without social dancing are filed under Classes & Services."""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import scrapers  # noqa: E402


class VendorSignals(unittest.TestCase):
    def test_tour_operator_name(self):
        self.assertTrue(scrapers.vendor_signals("Awesome NYC Tours", ["Rock Music Tour"]))
        self.assertTrue(scrapers.vendor_signals("WalksNYC Tours & Cruises", []))

    def test_same_product_every_day(self):
        titles = ["Speakeasy Pub and Prohibition History Tour NYC"] * 20 + ["The Manhattan Social: Bar Night Out"] * 10
        self.assertTrue(scrapers.vendor_signals("NiteTables", titles))

    def test_varied_organizer_is_fine(self):
        titles = [f"Band {i} live" for i in range(30)]
        self.assertEqual(scrapers.vendor_signals("Some Music Hall", titles), [])

    def test_nightly_show_that_is_not_a_product_is_fine(self):
        self.assertEqual(scrapers.vendor_signals("Comedy Club", ["Late Night Standup Showcase"] * 40), [])

    def test_too_few_events_to_judge(self):
        self.assertEqual(scrapers.vendor_signals("Studio", ["Salsa Class"] * 5), [])


class OrganizerList(unittest.TestCase):
    def test_excluded_and_pending_are_not_scraped(self):
        with open(scrapers.EVENTBRITE_ORGANIZERS_FILE, encoding="utf-8") as f:
            data = json.load(f)
        listed = {i for _k, i, _n, _c in scrapers._load_eventbrite_organizers()}
        held = {str(x["id"]) for key in ("excluded", "pending") for x in data.get(key, [])}
        self.assertFalse(listed & held)
        self.assertIn("105361849101", held)  # Police GuidedTours

    def test_pending_entries_are_never_loaded(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump({"sources": [{"id": "1", "kind": "organizer", "name": "A"}],
                       "pending": [{"id": "2", "kind": "organizer", "name": "B"}]}, f)
        try:
            self.assertEqual([r[1] for r in scrapers._load_eventbrite_organizers(f.name)], ["1"])
        finally:
            os.unlink(f.name)


class DiscoveryHoldsVendors(unittest.TestCase):
    def _run(self, eb, scrape, found=None):
        results = []
        with tempfile.TemporaryDirectory() as t:
            dp, op = os.path.join(t, "d.json"), os.path.join(t, "o.json")
            json.dump(eb, open(dp, "w"))
            if found is not None:
                json.dump(found, open(op, "w"))
            n = scrapers._discover_eventbrite_organizers(results, details_path=dp, path=op, scrape=scrape,
                                                         tracked=set(), sleep=lambda s: None)
            return n, results, json.load(open(op))

    def test_new_tour_operator_is_held_not_published(self):
        eb = {"1": {"organizer_id": "500", "organizer_name": "Harbor Sunset Cruises"},
              "2": {"organizer_id": "600", "organizer_name": "Real Venue"}}

        def scrape(v):
            names = ["Sunset Cruise"] * 3 if "Cruises" in v["name"] else ["A show", "Another show"]
            return {"venue": v["name"], "events": [{"name": n} for n in names], "error": None}
        n, results, state = self._run(eb, scrape)
        self.assertEqual(n, 1)
        self.assertEqual(state["500"]["status"], "held")
        self.assertTrue(state["500"]["reasons"])
        self.assertEqual([r["venue"] for r in results], ["Real Venue"])

    def test_followed_organizer_that_turns_into_a_vendor_is_dropped(self):
        found = {"700": {"status": "ok", "name": "Night Out Co", "category": "party", "ts": 0}}
        events = [{"name": "Rooftop Bar Tour"}] * 16 + [{"name": "Pub Crawl"}] * 4
        _n, results, state = self._run({}, lambda v: {"venue": v["name"], "events": events, "error": None}, found)
        self.assertEqual(results, [])
        self.assertEqual(state["700"]["status"], "held")

    def test_followed_organizer_later_excluded_is_not_scraped(self):
        found = {"800": {"status": "ok", "name": "X", "category": "party", "ts": 0}}
        calls = []
        with tempfile.TemporaryDirectory() as t:
            dp, op = os.path.join(t, "d.json"), os.path.join(t, "o.json")
            json.dump({}, open(dp, "w"))
            json.dump(found, open(op, "w"))
            scrapers._discover_eventbrite_organizers([], details_path=dp, path=op, tracked={"800"},
                                                     scrape=lambda v: calls.append(v) or {"events": []},
                                                     sleep=lambda s: None)
        self.assertEqual(calls, [])


class DanceClasses(unittest.TestCase):
    def cls(self, name, src="Some Studio"):
        return scrapers.is_dropin_dance_class(name, "dance", src)

    def test_classes_and_dance_fitness_are_classes(self):
        for name in ["Salsa Classes for Beginners on Mondays", "Argentine Tango Group Class",
                     "West Coast Swing Lessons", "Dance Fitness", "Zumba", "MONDAY $10 Intro Cuban Salsa Class"]:
            self.assertTrue(self.cls(name), name)

    def test_socials_stay_in_dance(self):
        for name in ["LVG Salsa Social", "Paciencia Milonga Tuesdays", "Frim Fram Jam (Intro Swing Lesson & Social Dance)",
                     "Argentine Tango Classes & Practice", "Bachata at Solas", "Monday Night Live Jazz & Swing Dancing",
                     "World Class Salsa Night"]:
            self.assertFalse(self.cls(name), name)

    def test_class_directory_listings_are_classes_unless_social(self):
        src = "DanceUS: NYC Hip Hop"
        self.assertTrue(self.cls("Fierce Feminine Hip Hop with Emma Rosa", src))
        self.assertTrue(self.cls("Basic Belly Dance Wednesday's", src))
        self.assertFalse(self.cls("Tango Tuesdays", "DanceUS: NYC Argentine Tango"))
        self.assertFalse(self.cls("Practica La Resaca", "DanceUS: NYC Argentine Tango"))
        self.assertFalse(self.cls("Midtown Swings Social at a Studio", "DanceUS: NYC Swing"))

    def test_other_categories_untouched(self):
        self.assertFalse(scrapers.is_dropin_dance_class("Pottery Class", "art", "Clay Studio"))


if __name__ == "__main__":
    unittest.main()
