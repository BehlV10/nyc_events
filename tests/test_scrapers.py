"""NYC Events — Automated Unit Test Suite.

Run via:
  python -m unittest discover tests
"""

import os
import sys
import unittest
from datetime import datetime, timezone, timedelta

# Ensure project root is in sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from scrapers import _ALL_VENUES, UA_CHROME, is_placeholder_or_closed_event
from venues_geo import VENUE_COORDINATES, MIN_LAT, MAX_LAT, MIN_LNG, MAX_LNG, resolve_event_geo
from template import (
    render_page,
    SUBAREAS_BY_CITY,
    resolve_subarea,
    _event_city,
    _event_stable_id,
    _merge_duplicates,
    _clean_event_url,
    _normalize_title_head,
    group_by_date,
    EASTERN,
)
from scripts.add_community_event import validate_and_normalize as validate_event
from scripts.add_suggested_venue import validate_and_normalize as validate_venue


class TestNYCEvents(unittest.TestCase):

    def test_all_venues_defined(self):
        """Every venue must have a name, non-empty URL, and a callable scraper."""
        self.assertGreater(len(_ALL_VENUES), 200, "Expected at least 200 configured venues")
        for v in _ALL_VENUES:
            self.assertTrue(v.get("name"), f"Missing name in venue config: {v}")
            self.assertTrue(v.get("url"), f"Missing URL in venue config: {v['name']}")
            self.assertTrue(callable(v.get("scraper")), f"Scraper is not callable for venue: {v['name']}")

    def test_geo_bounding_box(self):
        """All curated venue coordinates must fall within NYC bounding box."""
        self.assertGreater(len(VENUE_COORDINATES), 300)
        for vname, (lat, lng, neigh, addr, cname) in VENUE_COORDINATES.items():
            self.assertTrue(
                MIN_LAT <= lat <= MAX_LAT,
                f"Latitude {lat} for '{cname}' outside [{MIN_LAT}, {MAX_LAT}]"
            )
            self.assertTrue(
                MIN_LNG <= lng <= MAX_LNG,
                f"Longitude {lng} for '{cname}' outside [{MIN_LNG}, {MAX_LNG}]"
            )
            self.assertTrue(len(addr) > 0, f"Missing address for '{cname}'")

    def test_geo_resolver(self):
        """resolve_event_geo should accurately match known venues across all 5 boroughs."""
        res_bowery = resolve_event_geo({"venue": "Bowery Ballroom"})
        self.assertIsNotNone(res_bowery)
        self.assertIn("Lower East Side", res_bowery["neighborhood"])
        self.assertEqual(res_bowery["venue"], "Bowery Ballroom")

        res_bluenote = resolve_event_geo({"venue": "Blue Note Jazz Club"})
        self.assertIsNotNone(res_bluenote)
        self.assertIn("Greenwich Village", res_bluenote["neighborhood"])

        res_babys = resolve_event_geo({"venue": "Baby's All Right"})
        self.assertIsNotNone(res_babys)
        self.assertIn("Williamsburg", res_babys["neighborhood"])

        res_flophouse = resolve_event_geo({"venue": "Flop House Comedy Club"})
        self.assertIsNotNone(res_flophouse)
        self.assertIn("Williamsburg", res_flophouse["neighborhood"])

        res_sobs = resolve_event_geo({"venue": "S.O.B.'s"})
        self.assertIsNotNone(res_sobs)
        self.assertIn("SoHo", res_sobs["neighborhood"])

        res_lincoln = resolve_event_geo({"venue": "Lincoln Center"})
        self.assertIsNotNone(res_lincoln)
        self.assertIn("Upper West Side", res_lincoln["neighborhood"])

        res_virtual = resolve_event_geo({"venue": "Online / Zoom"})
        self.assertIsNone(res_virtual)

    def test_community_event_validation_success(self):
        """Valid community event should normalize properly."""
        tomorrow = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%d")
        payload = {
            "name": "Live Acoustic Night",
            "venue": "Bowery Ballroom",
            "date": tomorrow,
            "url": "https://boweryballroom.com/tickets",
            "borough": "manhattan",
            "price": "$15",
        }
        res = validate_event(payload)
        self.assertEqual(res["name"], "Live Acoustic Night")
        self.assertEqual(res["venue"], "Bowery Ballroom")
        self.assertEqual(res["city"], "manhattan")
        self.assertEqual(res["price"], "$15")
        self.assertTrue(res["_is_community"])

    def test_community_event_validation_failures(self):
        """Invalid community events must raise ValueError."""
        # Missing name
        with self.assertRaises(ValueError):
            validate_event({"name": "", "venue": "Club", "date": "2026-10-20"})

        # Missing venue
        with self.assertRaises(ValueError):
            validate_event({"name": "Show", "venue": "", "date": "2026-10-20"})

        # Past date (>2 days ago)
        with self.assertRaises(ValueError):
            validate_event({"name": "Show", "venue": "Club", "date": "2020-01-01"})

        # Invalid URL scheme
        tomorrow = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%d")
        with self.assertRaises(ValueError):
            validate_event({"name": "Show", "venue": "Club", "date": tomorrow, "url": "javascript:alert(1)"})

    def test_suggested_venue_validation(self):
        """Valid suggested venue should normalize properly."""
        payload = {
            "name": "Flop House Comedy Club",
            "url": "https://flophousecomedy.com",
            "borough": "brooklyn",
            "category": "comedy",
            "address": "362 Grand St, Brooklyn, NY",
            "notes": "Intimate indie comedy club in Brooklyn",
        }
        res = validate_venue(payload)
        self.assertEqual(res["name"], "Flop House Comedy Club")
        self.assertEqual(res["url"], "https://flophousecomedy.com")
        self.assertEqual(res["city"], "brooklyn")
        self.assertEqual(res["category"], "comedy")
        self.assertEqual(res["status"], "pending_review")

        # Invalid URL should raise ValueError
        with self.assertRaises(ValueError):
            validate_venue({"name": "Place", "url": "not-a-valid-url"})

    def test_template_rendering(self):
        """render_page() must render complete HTML without template exceptions."""
        mock_data = [
            {
                "venue": "Bowery Ballroom",
                "url": "https://boweryballroom.com",
                "error": None,
                "events": [
                    {
                        "name": "Indie Rock Night",
                        "date": datetime.now(timezone.utc).isoformat(),
                        "url": "https://boweryballroom.com/event/1",
                        "venue": "Bowery Ballroom",
                        "category": "music",
                        "price": "$25",
                    }
                ],
            }
        ]
        html = render_page(mock_data)
        self.assertIn("<!doctype html>", html.lower())
        self.assertIn("Bowery Ballroom", html)
        self.assertIn("Indie Rock Night", html)
        self.assertIn("id=\"btn-open-submit-modal\"", html)
        self.assertIn("id=\"submit-event-modal\"", html)
        self.assertIn("Suggest a Venue", html)
        self.assertIn("Add an Event", html)
        self.assertIn("id=\"subarea-chips-bar\"", html)
        self.assertIn("id=\"map-label-toggle-btn\"", html)
        self.assertIn("data-subarea=\"les_ev\"", html)

    def test_subarea_mapping_and_coverage(self):
        """All defined subareas must be valid and all scraped events must map cleanly."""
        for b in ["manhattan", "brooklyn", "queens", "bronx", "staten_island", "other"]:
            self.assertIn(b, SUBAREAS_BY_CITY)

        # Test canonical venues across NYC boroughs
        self.assertEqual(resolve_subarea("manhattan", {"venue": "Bowery Ballroom"})[1], "les_ev")
        self.assertEqual(resolve_subarea("manhattan", {"venue": "Comedy Cellar"})[1], "village_soho")
        self.assertEqual(resolve_subarea("manhattan", {"venue": "Lincoln Center"})[1], "uws_lincoln")
        self.assertEqual(resolve_subarea("manhattan", {"venue": "Apollo Theater"})[1], "harlem_uptown")
        self.assertEqual(resolve_subarea("manhattan", {"venue": "Terminal 5"})[1], "midtown_chelsea")

        self.assertEqual(resolve_subarea("brooklyn", {"venue": "Baby's All Right"})[1], "williamsburg_gp")
        self.assertEqual(resolve_subarea("brooklyn", {"venue": "Brooklyn Bowl"})[1], "williamsburg_gp")
        self.assertEqual(resolve_subarea("brooklyn", {"venue": "Elsewhere"})[1], "bushwick_ew")
        self.assertEqual(resolve_subarea("brooklyn", {"venue": "Flop House Comedy Club"})[1], "williamsburg_gp")
        self.assertEqual(resolve_subarea("brooklyn", {"venue": "Bell House"})[1], "park_slope_gowanus")

        # Test full dataset coverage if events.json is present
        events_json = os.path.join(BASE_DIR, "events.json")
        if os.path.exists(events_json):
            import json
            with open(events_json, "r") as f:
                data = json.load(f)
            total_events = 0
            for v in data.get("venues", []):
                vname = v.get("venue", "")
                for e in v.get("events", []):
                    total_events += 1
                    city = _event_city(e.get("venue"), vname, e)
                    geo = resolve_event_geo(e)
                    sname, sslug = resolve_subarea(city, e, geo)
                    valid_slugs = {s[0] for s in SUBAREAS_BY_CITY[city]}
                    self.assertIn(
                        sslug,
                        valid_slugs,
                        f"Event '{e.get('name')}' at '{e.get('venue')}' produced unmapped slug '{sslug}' in '{city}'"
                    )
            self.assertGreater(total_events, 500, "Expected at least 500 events in events.json")

    def test_event_stable_id(self):
        """_event_stable_id must produce deterministic IDs starting with 'ev_'."""
        e1 = {"name": "Jazz Brunch", "venue": "Blue Note", "date": "2026-10-25T11:00:00"}
        e2 = {"name": "jazz brunch", "venue": "blue note", "date": "2026-10-25T19:00:00"}
        e3 = {"name": "Rock Show", "venue": "Bowery Ballroom", "date": "2026-10-25T20:00:00"}

        id1 = _event_stable_id(e1)
        id2 = _event_stable_id(e2)
        id3 = _event_stable_id(e3)

        self.assertTrue(id1.startswith("ev_"))
        self.assertEqual(id1, id2, "Identical normalized title, venue, and date must generate identical ID")
        self.assertNotEqual(id1, id3, "Different events must have different IDs")

    def test_is_placeholder_or_closed_event(self):
        """Ensure dummy calendar placeholders, closures, and cancellations are caught while preserving real shows."""
        placeholders = [
            "No Event Tonight-Check Our Calendar For Upcoming Events",
            "No Live Music",
            "club closed",
            "Closed for the Thanksgiving Holiday",
            "Closed for the Christmas Holiday",
            "Closed for New Year's Day",
            "** Private Event **",
            "*PRIVATE EVENT*",
            "CANCELED Andy Gross",
            "POSTPONED Recital: Max Ignas",
            "CANCELLED: Free Drop-in Tutoring for Teens",
            "Tbd",
            "TBA",
        ]
        for title in placeholders:
            self.assertTrue(is_placeholder_or_closed_event(title), f"Failed to detect placeholder: {title}")

        real_events = [
            "Vince Staples, Private School",
            "Straight No Chaser",
            "No Cover Drag Bingo with Wilhelmina",
            "No Relation Hidden Sushi Bar",
        ]
        for title in real_events:
            self.assertFalse(is_placeholder_or_closed_event(title), f"False positive on real event: {title}")

    def test_deduplication_and_timezones(self):
        """Verify URL matching, cross-source venue deduplication, and timezone handling."""
        # 1. Clean event url test
        self.assertEqual(_clean_event_url("https://boweryballroom.com/event/indie-rock/"), "https://boweryballroom.com/event/indie-rock")
        self.assertEqual(_clean_event_url("https://boweryballroom.com/event/indie-rock/#buy-tix?ref=1"), "https://boweryballroom.com/event/indie-rock")
        self.assertEqual(_clean_event_url("https://boweryballroom.com/events"), "")

        # 2. Cross-source duplicate merge
        dt_8pm = datetime(2026, 10, 20, 20, 0, tzinfo=EASTERN).astimezone(timezone.utc).isoformat()
        sample_events = [
            {
                "name": "The Strokes Live",
                "date": dt_8pm,
                "venue": "Bowery Ballroom",
                "price": "$40",
                "url": "https://boweryballroom.com/event/the-strokes",
                "source": "bowery ballroom",
            },
            {
                "name": "The Strokes",
                "date": dt_8pm,
                "venue": "Bowery Ballroom",
                "price": None,
                "url": "https://donyc.com/events/the-strokes",
                "source": "donyc",
            },
        ]
        merged = _merge_duplicates(sample_events)
        self.assertEqual(len(merged), 1, "Duplicate events from different sources must merge into 1")
        self.assertEqual(merged[0]["price"], "$40")
        self.assertEqual(len(merged[0].get("_alt_sources", [])), 1)
        self.assertEqual(merged[0]["_alt_sources"][0]["source"], "donyc")

        # 3. Eastern timezone check in group_by_date
        # 20:00 EDT = 00:00 UTC (next day). When grouped by date, it must resolve to 20:00 EDT on 2026-10-20.
        venue_res = [{
            "venue": "Bowery Ballroom",
            "url": "https://boweryballroom.com",
            "events": [{"name": "The Strokes", "date": dt_8pm, "venue": "Bowery Ballroom"}]
        }]
        dated, _, _ = group_by_date(venue_res)
        target_date = datetime(2026, 10, 20).date()
        date_map = dict(dated)
        self.assertIn(target_date, date_map)
        item = date_map[target_date][0]
        self.assertEqual(item["_time"].hour, 20)
        self.assertEqual(item["_time"].minute, 0)

    def test_venue_ttl_and_disk_cache(self):
        """Test per-venue TTL categorization, cache saving, and loading."""
        from scrapers import (
            _get_venue_ttl, FAST_VENUE_TTL, SLOW_VENUE_TTL, DEFAULT_VENUE_TTL,
            _venue_cache_path, _save_venue_cache, _load_venue_cache, _scrape_one
        )

        # 1. TTL checks
        self.assertEqual(_get_venue_ttl("Ticketmaster NYC"), FAST_VENUE_TTL)
        self.assertEqual(_get_venue_ttl("DoNYC"), FAST_VENUE_TTL)
        self.assertEqual(_get_venue_ttl("NYC Parks & Recreation"), SLOW_VENUE_TTL)
        self.assertEqual(_get_venue_ttl("Bowery Ballroom"), DEFAULT_VENUE_TTL)

        # 2. Cache save and load
        test_vname = "Test NYC Venue TTL"
        test_events = [{"name": "Test Band NYC", "date": "2026-10-25T20:00:00Z"}]
        cpath = _venue_cache_path(test_vname)

        try:
            _save_venue_cache(test_vname, test_events, duration=0.5)
            self.assertTrue(os.path.exists(cpath))

            # Fresh load
            loaded = _load_venue_cache(test_vname, max_age=3600)
            self.assertIsNotNone(loaded)
            self.assertEqual(len(loaded["events"]), 1)
            self.assertEqual(loaded["events"][0]["name"], "Test Band NYC")

            # Expired load
            expired = _load_venue_cache(test_vname, max_age=-1)
            self.assertIsNone(expired)

            # Test _scrape_one using cache
            mock_venue = {
                "name": test_vname,
                "url": "https://example.com",
                "ua": "TestUA",
                "scraper": lambda u, a: self.fail("Scraper should not be invoked when cache is valid!"),
                "default_category": "music"
            }
            res = _scrape_one(mock_venue, force=False)
            self.assertTrue(res.get("cached"))
            self.assertEqual(len(res["events"]), 1)
        finally:
            if os.path.exists(cpath):
                os.remove(cpath)

    def test_sobs_scraper_and_geo(self):
        """Test S.O.B.'s scraper parsing and geo resolution."""
        from unittest.mock import patch, MagicMock
        from scrapers import scrape_sobs

        sample_html = """
        <div class="ecard" data-link="https://sobs.com/events/brazilian-carnaval/">
            <div class="ecard_titu">Brazilian Carnaval Bash</div>
            <div class="ecard_date">Oct 28, 2026</div>
            <div class="ecard_time">Doors: 7:00 PM | Show: 8:00 PM</div>
            <a class="btn-line" href="https://sobs.com/events/brazilian-carnaval/">Tickets</a>
        </div>
        """
        with patch("scrapers._SESSION.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.text = sample_html
            mock_get.return_value = mock_resp

            events = scrape_sobs("https://sobs.com/calendar/", "TestUA")

        self.assertEqual(len(events), 1)
        ev = events[0]
        self.assertEqual(ev["name"], "Brazilian Carnaval Bash")
        self.assertEqual(ev["venue"], "S.O.B.'s")
        self.assertEqual(ev["category"], "music")
        self.assertEqual(ev["url"], "https://sobs.com/events/brazilian-carnaval/")

        geo = resolve_event_geo(ev)
        self.assertIsNotNone(geo)
        self.assertEqual(geo["venue"], "S.O.B.'s")
        self.assertEqual(geo["neighborhood"], "SoHo / Hudson Sq")


if __name__ == "__main__":
    unittest.main()
