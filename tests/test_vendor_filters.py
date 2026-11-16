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


class DanceClassCategory(unittest.TestCase):
    def test_kids_dance_classes_are_family(self):
        for name in ["Hip Hop 8-10 yrs @ Midtown Movement And Dance", "Hip Hop 3-5 yrs @ Midtown Movement And Dance",
                     "Acro/Hip Hop (Ages 8 & under) @ The Brooklyn Dance Centers", "Acro/Hip Hop (Ages 9 & Up) @ Studio",
                     "KindiBreaking (Tuesday)", "Young Dancers Program – Hip Hop & Multi-Discipline"]:
            self.assertTrue(scrapers.is_kid_family_event(name), name)

    def test_adult_age_ranges_are_not_family(self):
        for name in ["Singles Mixer Ages 25-40", "Salsa Night 21 & up", "Ages 18 & Up Dance Party", "Speed Dating 30-45 yrs"]:
            self.assertFalse(scrapers.is_kid_family_event(name), name)

    def test_dance_classes_have_their_own_hidden_bucket(self):
        import template
        self.assertEqual(scrapers.category_bucket("dance class"), "Dance Classes")
        self.assertIn("Dance Classes", template.DEFAULT_UNCHECKED_BUCKETS)
        self.assertIn("dance class", scrapers.CATEGORY_STYLES)

    def test_grouping_files_classes_and_kids_classes(self):
        import template
        day = "2030-01-07T19:00:00-05:00"
        results = [{"venue": "DanceUS: NYC Hip Hop", "url": "https://x", "events": [
            {"name": "Fierce Feminine Hip Hop with Emma Rosa", "date": day},
            {"name": "Hip Hop 8-10 yrs @ Midtown Movement And Dance", "date": day}]},
            {"venue": "SalsaVida NYC Socials", "url": "https://y", "default_category": "dance", "events": [
                {"name": "LVG Salsa Social", "date": day, "category": "dance"}]}]
        dated, _tba, _ong = template.group_by_date(results)
        cats = {e["name"]: e["category"] for _d, evs in dated for e in evs}
        self.assertEqual(cats["Fierce Feminine Hip Hop with Emma Rosa"], "dance class")
        self.assertEqual(cats["Hip Hop 8-10 yrs @ Midtown Movement And Dance"], "family")
        self.assertEqual(cats["LVG Salsa Social"], "dance")


class CategoryCleanup(unittest.TestCase):
    def test_theater_lookalikes_and_keyword_feeds(self):
        import template
        day = "2030-01-08T19:00:00-05:00"
        ev = lambda name, venue: {"name": name, "date": day, "category": "theater", "venue": venue}
        results = [
            {"venue": "Meetup: Jazz", "url": "https://www.meetup.com/find/?keywords=jazz",
             "events": [ev("Beginners Hip Hop at Broadway Dance Center | NOT FREE", "Broadway Dance Center")]},
            {"venue": "AllEvents: Brooklyn Kids", "url": "https://allevents.in/brooklyn/kids",
             "events": [ev("Farmers Market at Fort Hamilton", "123 John Warren Ave")]},
            {"venue": "Meetup: Drag Shows", "url": "https://www.meetup.com/find/?keywords=drag",
             "events": [ev("Beginners Dungeons & Dragons", "Last Place On Earth"), ev("Queens of the Night", "Club X")]},
            {"venue": "St Mazie", "url": "https://x", "events": [ev("Gypsy Jazz with Antoine Thouvenin", "St Mazie Bar")]},
            {"venue": "Ticketmaster NYC", "url": "https://tm",
             "events": [ev("Hamilton", "Richard Rodgers Theatre"), ev("Gypsy", "Majestic Theatre")]}]
        dated, _t, _o = template.group_by_date(results)
        cats = {e["name"]: e["category"] for _d, evs in dated for e in evs}
        self.assertNotEqual(cats["Beginners Hip Hop at Broadway Dance Center | NOT FREE"], "theater")
        self.assertEqual(cats["Farmers Market at Fort Hamilton"], "markets")
        self.assertEqual(cats["Beginners Dungeons & Dragons"], "gaming")
        self.assertEqual(cats["Gypsy Jazz with Antoine Thouvenin"], "music")
        for show in ("Hamilton", "Gypsy", "Queens of the Night"):
            self.assertEqual(cats[show], "theater", show)

    def test_community_catch_all_is_sorted_where_the_title_is_clear(self):
        g = lambda t: scrapers.guess_category(t)
        self.assertEqual(g("Lectures on Tap: Why Outrage Goes Viral"), "talks")
        self.assertEqual(g("Macedonian Izvoren music with Niva"), "music")
        self.assertEqual(g("Yu & Me Community Book Club"), "books")
        self.assertEqual(g("Street Tree Care in Ditmas Park"), "outdoors")
        self.assertEqual(g("Gotham Go Group - Tuesdays at the Hungarian"), "gaming")
        self.assertEqual(g("AI Founders Panel & Networking"), "community")  # tech talks stay put
        self.assertEqual(g("2nd Annual Cousins Gathering"), "community")
        self.assertEqual(scrapers.category_bucket("talks"), "Arts & culture")
        self.assertIn("talks", scrapers.CATEGORY_STYLES)
