"""Lead sources (DoNYC, The Skint, ...) are enriched from the primary page their link points at."""
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import scrapers  # noqa: E402
from scrapers import EASTERN  # noqa: E402


def _local(days, hour=19, minute=0):
    return (datetime.now(EASTERN) + timedelta(days=days)).replace(hour=hour, minute=minute, second=0, microsecond=0)


def _iso(dt):
    return dt.astimezone(timezone.utc).isoformat()


def _lead(source, events):
    return {"venue": source, "url": "https://lead.example/", "error": None, "events": events}


def _run(results, pages, limit=None):
    """Run the pass against canned pages; returns (applied, urls fetched)."""
    asked = []

    def fetch(url, ua):
        asked.append(url)
        return pages.get(url, [])

    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "cache.json")
        applied = scrapers._enrich_from_primary_pages(results, path=path, fetch=fetch, limit=limit)
        again = []

        def fetch2(url, ua):
            again.append(url)
            return pages.get(url, [])
        scrapers._enrich_from_primary_pages(results, path=path, fetch=fetch2, limit=limit)
    return applied, asked, again


class PrimaryPageTests(unittest.TestCase):
    def test_time_price_address_come_from_the_page_names_and_links_stay(self):
        day = _local(3, 0, 0)
        e = {"name": "Winter Market", "date": _iso(day), "url": "https://venue.example/market", "venue": "Venue", "price": "Check link"}
        page = {"https://venue.example/market": [
            {"name": "Winter Market (page)", "date": _iso(_local(3, 11)), "end": _iso(_local(3, 17)), "price": "$12",
             "address": "1 Main St, Brooklyn, NY 11201", "lat": 40.7, "lng": -73.9, "description": "Stalls."}]}
        applied, _asked, _again = _run([_lead("The Skint NYC", [e])], page)
        self.assertEqual(applied, 1)
        self.assertEqual(datetime.fromisoformat(e["date"]).astimezone(EASTERN).hour, 11)
        self.assertEqual((e["name"], e["url"], e["venue"]), ("Winter Market", "https://venue.example/market", "Venue"))
        self.assertEqual((e["price"], e["address"], e["lat"], e["description"]), ("$12", "1 Main St, Brooklyn, NY 11201", 40.7, "Stalls."))
        self.assertIn("end", e)

    def test_guessed_skint_time_is_replaced_but_a_stated_time_is_kept(self):
        guessed = {"name": "A", "date": _iso(_local(2, 19)), "url": "https://a.example/e", "venue": "V", "price": "$5", "_time_guess": True}
        stated = {"name": "B", "date": _iso(_local(2, 19)), "url": "https://b.example/e", "venue": "V", "price": "Free / Various"}
        page_time = _iso(_local(2, 14, 30))
        pages = {"https://a.example/e": [{"name": "A", "date": page_time, "price": "$9"}],
                 "https://b.example/e": [{"name": "B", "date": page_time, "price": "$9"}]}
        _run([_lead("The Skint NYC", [guessed, stated])], pages)
        self.assertEqual(datetime.fromisoformat(guessed["date"]).astimezone(EASTERN).hour, 14)
        self.assertNotIn("_time_guess", guessed)
        self.assertEqual(guessed["price"], "$5")  # a real price is never overwritten
        self.assertEqual(datetime.fromisoformat(stated["date"]).astimezone(EASTERN).hour, 19)
        self.assertEqual(stated["price"], "$9")  # a vague one is

    def test_only_the_listing_day_counts_and_the_closest_showtime_wins(self):
        e = {"name": "Show", "date": _iso(_local(4, 20)), "url": "https://v.example/show", "venue": "V"}
        pages = {"https://v.example/show": [
            {"name": "Show", "date": _iso(_local(5, 20)), "price": "$99"},      # another day
            {"name": "Show", "date": _iso(_local(4, 16)), "price": "$20"},      # matinee
            {"name": "Show", "date": _iso(_local(4, 20, 30)), "price": "$30"}]}  # closest to 20:00
        _run([_lead("DoNYC Citywide", [e])], pages)
        self.assertEqual(e["price"], "$30")
        e2 = {"name": "Show", "date": _iso(_local(9, 20)), "url": "https://w.example/show", "venue": "V"}
        applied, *_ = _run([_lead("DoNYC Citywide", [e2])], {"https://w.example/show": [{"name": "Show", "date": _iso(_local(8, 20)), "price": "$1"}]})
        self.assertEqual(applied, 0)
        self.assertNotIn("price", e2)

    def test_skipped_hosts_and_other_sources_are_never_fetched(self):
        mk = lambda u: {"name": "x", "date": _iso(_local(2)), "url": u, "venue": "V"}
        lead = _lead("The Skint NYC", [mk("https://www.instagram.com/p/abc"), mk("https://www.eventbrite.com/e/1"),
                                      mk("https://kyd.to/xyz"), mk("https://ok.example/e")])
        other = _lead("Elsewhere Brooklyn", [mk("https://other.example/e")])
        _applied, asked, _again = _run([lead, other], {})
        self.assertEqual(asked, ["https://ok.example/e"])

    def test_pages_are_cached_and_the_budget_is_respected(self):
        events = [{"name": f"e{i}", "date": _iso(_local(2 + i)), "url": f"https://v.example/{i}", "venue": "V"} for i in range(5)]
        _applied, asked, again = _run([_lead("The Skint NYC", events)], {}, limit=3)
        self.assertEqual(asked, [f"https://v.example/{i}" for i in range(3)])  # soonest first
        self.assertEqual(again, ["https://v.example/3", "https://v.example/4"])  # the first three came from the cache

    def test_a_site_that_refuses_us_is_not_asked_again(self):
        e = {"name": "x", "date": _iso(_local(2)), "url": "https://blocked.example/e", "venue": "V"}
        calls = []

        def fetch(url, ua):
            calls.append(url)
            raise scrapers.SiteRefused(url)
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "c.json")
            for _ in range(2):
                scrapers._enrich_from_primary_pages([_lead("The Skint NYC", [e])], path=path, fetch=fetch)
        self.assertEqual(len(calls), 1)

    def test_fever_links_use_the_plan_parser_and_other_pages_use_json_ld(self):
        fever = {"name": "Lanterns", "date": "2026-11-19T23:30:00+00:00", "price": "From $19"}
        with patch.object(scrapers, "fetch_text", return_value=(200, "<html/>")), \
             patch.object(scrapers, "_fever_plan_event", return_value=fever) as plan:
            self.assertEqual(scrapers._primary_page_entries("https://feverup.com/m/782364", "ua"), [fever])
            plan.assert_called_once()
        ld = {"@context": "https://schema.org", "@type": "MusicEvent", "name": "Gig", "startDate": "2026-12-01T20:00:00-05:00",
              "endDate": "2026-12-01T23:00:00-05:00", "offers": {"price": "15", "priceCurrency": "USD"},
              "location": {"@type": "Place", "name": "Hall", "address": "5 Elm St, Queens, NY 11101"}}
        page = f'<html><script type="application/ld+json">{json.dumps(ld)}</script></html>'
        with patch.object(scrapers, "fetch_text", return_value=(200, page)):
            (entry,) = scrapers._primary_page_entries("https://hall.example/gig", "ua")
        self.assertEqual((entry["name"], entry["price"], entry["venue"]), ("Gig", "$15", "Hall"))
        self.assertIn("end", entry)


if __name__ == "__main__":
    unittest.main()
