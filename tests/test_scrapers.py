"""NYC Events — Automated Unit Test Suite.

Run via:
  python -m unittest discover tests
"""

import json
import os
import sys
import unittest
from datetime import datetime, timezone, timedelta

# Ensure project root is in sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from scrapers import (
    _ALL_VENUES,
    UA_CHROME,
    is_placeholder_or_closed_event,
    scrape_luma,
    scrape_skip_the_small_talk,
    BROADWAY_THEATRES,
    guess_category,
)
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
    _url_priority,
    _ticket_source_name,
    _build_compare_links,
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
        future_day = (datetime.now(EASTERN) + timedelta(days=5)).date()
        dt_8pm = datetime(future_day.year, future_day.month, future_day.day, 20, 0, tzinfo=EASTERN).astimezone(timezone.utc).isoformat()
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
        # 20:00 EDT = 00:00 UTC (next day). When grouped by date, it must resolve to 20:00 EDT on future_day.
        venue_res = [{
            "venue": "Bowery Ballroom",
            "url": "https://boweryballroom.com",
            "events": [{"name": "The Strokes", "date": dt_8pm, "venue": "Bowery Ballroom"}]
        }]
        dated, _, _ = group_by_date(venue_res)
        target_date = future_day
        date_map = dict(dated)
        self.assertIn(target_date, date_map)
        item = date_map[target_date][0]
        self.assertEqual(item["_time"].hour, 20)
        self.assertEqual(item["_time"].minute, 0)

    def test_venue_ttl_and_disk_cache(self):
        """Test per-venue TTL categorization, cache saving, and loading."""
        from scrapers import (
            _get_venue_ttl, FAST_VENUE_TTL, SLOW_VENUE_TTL, DEFAULT_VENUE_TTL, EVENTBRITE_TTL,
            _venue_cache_path, _save_venue_cache, _load_venue_cache, _scrape_one
        )

        # 1. TTL checks
        self.assertEqual(_get_venue_ttl("Ticketmaster NYC"), FAST_VENUE_TTL)
        self.assertEqual(_get_venue_ttl("DoNYC"), FAST_VENUE_TTL)
        self.assertEqual(_get_venue_ttl("NYC Parks & Recreation"), SLOW_VENUE_TTL)
        self.assertEqual(_get_venue_ttl("Bowery Ballroom"), DEFAULT_VENUE_TTL)
        self.assertEqual(_get_venue_ttl("NYC Salsa (Eventbrite)"), EVENTBRITE_TTL)
        self.assertEqual(_get_venue_ttl("Brooklyn Made", {"url": "https://www.eventbrite.com/d/ny--brooklyn/brooklyn-made/"}), EVENTBRITE_TTL)

        # 2. Cache save and load
        fut_date = (datetime.now(EASTERN) + timedelta(days=5)).strftime("%Y-%m-%dT20:00:00Z")
        test_vname = "Test NYC Venue TTL"
        test_events = [{"name": "Test Band NYC", "date": fut_date}]
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

    def test_diwali_times_square_scraper(self):
        """Test Diwali at Times Square scraper and geo resolution."""
        from unittest.mock import patch, MagicMock
        from scrapers import scrape_diwali_times_square

        future_date_str = (datetime.now(timezone.utc) + timedelta(days=5)).strftime("%B %d, %Y")
        sample_html = f"""
        <html><body>
            <div>Event Location 46th-48th Street & Broadway, Times Square, New York City, NY</div>
            <div>Event Date {future_date_str}</div>
            <meta property="og:image" content="https://diwalitimessquare.com/og-photo-dats-2026.webp" />
        </body></html>
        """
        with patch("scrapers._SESSION.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.text = sample_html
            mock_get.return_value = mock_resp

            events = scrape_diwali_times_square("https://diwalitimessquare.com/", "TestUA")

        self.assertEqual(len(events), 1)
        ev = events[0]
        self.assertIn("Diwali at Times Square", ev["name"])
        self.assertEqual(ev["price"], "Free")
        self.assertEqual(ev["category"], "community")
        self.assertEqual(ev["venue"], "Times Square (46th-48th St)")

        geo = resolve_event_geo(ev)
        self.assertIsNotNone(geo)
        self.assertEqual(geo["neighborhood"], "Times Square")

    def test_clearview_festivals_scraper(self):
        """Test Clearview street fairs scraper parsing and location resolution."""
        from unittest.mock import patch, MagicMock
        from scrapers import scrape_clearview_festivals

        fut_str = (datetime.now(EASTERN) + timedelta(days=5)).strftime("%m/%d/%Y")
        sample_html = f"""
        <table>
            <tr>
                <td><span class="sponsor">{fut_str} Upper Broadway Harvest Fair</span></td>
            </tr>
            <tr>
                <td class="uctest">Broadway (W)</td>
            </tr>
            <tr>
                <td class="uctest">96th St - 106th St</td>
            </tr>
        </table>
        """
        with patch("scrapers._SESSION.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.text = sample_html
            mock_get.return_value = mock_resp

            events = scrape_clearview_festivals("https://vendors.clearviewfestival.com", "TestUA")

        self.assertEqual(len(events), 1)
        ev = events[0]
        self.assertIn("Upper Broadway Harvest Fair", ev["name"])
        self.assertEqual(ev["price"], "Free")
        self.assertEqual(ev["category"], "community")
        self.assertEqual(ev["neighborhood"], "Upper West Side")
        self.assertEqual(ev["city"], "manhattan")

    def test_donyc_direct_link_resolution(self):
        """scrape_donyc should extract direct ticket URLs and venue websites rather than donyc.com links."""
        from unittest.mock import patch
        from scrapers import scrape_donyc
        from bs4 import BeautifulSoup

        d1 = (datetime.now(EASTERN) + timedelta(days=2)).strftime("%Y-%m-%dT20:00:00-0400")
        d2 = (datetime.now(EASTERN) + timedelta(days=3)).strftime("%Y-%m-%dT20:00:00-0400")
        sample_html = f"""
        <html>
        <head>
            <span class="ds-detail-website ds-meta-item">
                <a href="http://www.brooklynbowl.com">Official Website</a>
            </span>
        </head>
        <body>
            <div itemscope itemtype="http://schema.org/Event" itemprop="event" data-permalink="/events/2026/10/25/great-concert-tickets">
                <span itemprop="name">Great Concert</span>
                <meta itemprop="startDate" content="{d1}" />
                <div itemprop="location" itemscope itemtype="http://schema.org/Place">
                    <span itemprop="name">Brooklyn Bowl</span>
                </div>
                <span itemprop="offers" itemscope itemtype="http://schema.org/Offer">
                    <meta itemprop="url" content="https://ticketmaster.evyy.net/c/253185/264167/4272?SharedId=DoStuff&u=https%3A%2F%2Fwww.ticketmaster.com%2Fgreat-concert%2Fevent%2F123" />
                    <a class="ds-buy-tix" href="https://ticketmaster.evyy.net/c/253185/264167/4272?SharedId=DoStuff&u=https%3A%2F%2Fwww.ticketmaster.com%2Fgreat-concert%2Fevent%2F123">Buy</a>
                </span>
            </div>
            <div itemscope itemtype="http://schema.org/Event" itemprop="event" data-permalink="/events/2026/10/26/free-jam-tickets">
                <span itemprop="name">Free Jam Night</span>
                <meta itemprop="startDate" content="{d2}" />
                <div itemprop="location" itemscope itemtype="http://schema.org/Place">
                    <span itemprop="name">Brooklyn Bowl</span>
                </div>
            </div>
        </body>
        </html>
        """
        with patch("scrapers.fetch_soup") as mock_soup:
            mock_soup.return_value = BeautifulSoup(sample_html, "html.parser")
            events = scrape_donyc("https://donyc.com/venues/brooklyn-bowl", "TestUA")

        self.assertEqual(len(events), 2)
        # Event 1: has direct ticket link unpacked from affiliate
        self.assertEqual(events[0]["url"], "https://www.ticketmaster.com/great-concert/event/123")
        self.assertEqual(events[0]["ticket_url"], "https://www.ticketmaster.com/great-concert/event/123")
        self.assertNotIn("donyc.com", events[0]["url"])

        # Event 2: has no ticket link, should use official venue website
        self.assertEqual(events[1]["url"], "http://www.brooklynbowl.com")
        self.assertNotIn("donyc.com", events[1]["url"])

    def test_dedupe_prefers_direct_url_over_donyc(self):
        """_merge_duplicates should replace a doNYC URL with a direct ticketing or venue URL."""
        fut = (datetime.now(EASTERN) + timedelta(days=2)).replace(hour=20, minute=0, second=0, microsecond=0)
        e_donyc = {
            "name": "Live Concert at Brooklyn Bowl",
            "date": fut.isoformat(),
            "_time": fut,
            "venue": "Brooklyn Bowl",
            "_source_venue": "DoNYC Citywide",
            "url": "https://donyc.com/events/2026/10/24/live-concert-tickets",
        }
        e_direct = {
            "name": "Live Concert at Brooklyn Bowl",
            "date": fut.isoformat(),
            "_time": fut,
            "venue": "Brooklyn Bowl",
            "_source_venue": "Brooklyn Bowl",
            "url": "https://www.ticketmaster.com/event/999",
            "price": "$25",
        }
        merged = _merge_duplicates([e_donyc, e_direct])
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["url"], "https://www.ticketmaster.com/event/999")
        self.assertNotIn("donyc.com", merged[0]["url"])

    def test_dedicated_scrapers(self):
        """Test The Stone, Grand Bazaar, and Queens Night Market scrapers."""
        from scrapers import scrape_queens_night_market
        from unittest.mock import patch, MagicMock

        # Queens Night Market
        fut_qnm = (datetime.now(EASTERN) + timedelta(days=6)).strftime("%b %d").upper()
        qnm_html = f"<html><body>NEXT NIGHT MARKET: {fut_qnm} NEW YORK HALL OF SCIENCE FLUSHING MEADOWS CORONA PARK FROM 4 PM UNTIL 12 AM</body></html>"
        with patch("scrapers._SESSION.get") as mock_get:
            m = MagicMock()
            m.status_code = 200
            m.text = qnm_html
            mock_get.return_value = m
            q_evs = scrape_queens_night_market("https://queensnightmarket.com/", "TestUA")
        self.assertGreaterEqual(len(q_evs), 1)
        self.assertIn("Queens Night Market", q_evs[0]["name"])
        self.assertEqual(q_evs[0]["price"], "Free")
        self.assertEqual(q_evs[0]["category"], "food")

        # Miller Theatre
        from scrapers import scrape_miller_theatre
        import html as html_lib
        fut_unix = int((datetime.now(timezone.utc) + timedelta(days=20)).timestamp())
        mock_events_data = [{
            "title": "Hub New Music",
            "subtitle": "Contemporary Chamber Works",
            "date": {"formatted": "Tuesday, Nov 15, 6PM", "unix": str(fut_unix)},
            "price": "Free",
            "category": {"title": "Pop-Up Concerts", "slug": "pop-up-concerts"},
            "url": "https://www.millertheatre.com/events/hub-new-music"
        }]
        mock_attr = html_lib.escape(json.dumps(mock_events_data))
        miller_html = f'<html><body><events :events="{mock_attr}"></events></body></html>'
        with patch("scrapers._SESSION.get") as mock_get:
            m = MagicMock()
            m.status_code = 200
            m.text = miller_html
            mock_get.return_value = m
            m_evs = scrape_miller_theatre("https://www.millertheatre.com/events", "TestUA")
        self.assertEqual(len(m_evs), 1)
        self.assertIn("Hub New Music", m_evs[0]["name"])
        self.assertEqual(m_evs[0]["price"], "Free")
        self.assertEqual(m_evs[0]["category"], "music")

    def test_scrape_one_cache_preservation_on_empty(self):
        """_scrape_one must not clobber existing cached events when a live scrape returns empty."""
        from scrapers import _scrape_one, _save_venue_cache, _load_venue_cache

        venue_name = "Mock Stale Resilience Venue"
        test_url = "https://example.com/events"
        fut_dt = (datetime.now(timezone.utc) + timedelta(days=10)).isoformat()
        initial_events = [{
            "name": "Resilient Community Gathering",
            "date": fut_dt,
            "url": test_url,
            "venue": venue_name,
            "price": "Free",
            "category": "community"
        }]
        _save_venue_cache(venue_name, initial_events, duration=1.0)

        mock_venue_spec = {
            "name": venue_name,
            "url": test_url,
            "ua": "TestUA",
            "scraper": lambda u, ua: [],
            "default_category": "community"
        }

        # Force live scrape with empty result — should preserve existing events
        res = _scrape_one(mock_venue_spec, force=True)
        self.assertEqual(len(res["events"]), 1)
        self.assertEqual(res["events"][0]["name"], "Resilient Community Gathering")

        # Verify cache file still has the preserved event
        cached = _load_venue_cache(venue_name, max_age=None)
        self.assertIsNotNone(cached)
        self.assertEqual(len(cached["events"]), 1)

    def test_ticketmaster_and_direct_preferred_over_seatgeek(self):
        """Ticketmaster and direct venue links must take priority over SeatGeek."""
        fut = (datetime.now(EASTERN) + timedelta(days=3)).replace(hour=19, minute=30, second=0, microsecond=0)
        e_sg = {
            "name": "New York Knicks vs Boston Celtics",
            "date": fut.isoformat(),
            "_time": fut,
            "venue": "Madison Square Garden",
            "_source_venue": "SeatGeek NYC",
            "url": "https://seatgeek.com/knicks-vs-celtics-tickets/111",
            "price": "$120",
        }
        e_tm = {
            "name": "New York Knicks vs Boston Celtics",
            "date": fut.isoformat(),
            "_time": fut,
            "venue": "Madison Square Garden",
            "_source_venue": "Ticketmaster NYC",
            "url": "https://www.ticketmaster.com/event/222",
            "price": "$95",
        }
        e_direct = {
            "name": "New York Knicks vs Boston Celtics",
            "date": fut.isoformat(),
            "_time": fut,
            "venue": "Madison Square Garden",
            "_source_venue": "Madison Square Garden",
            "url": "https://www.msg.com/events/knicks-celtics",
            "price": "$95",
        }

        # Case 1: SeatGeek first, Ticketmaster second -> Ticketmaster becomes primary
        m1 = _merge_duplicates([e_sg.copy(), e_tm.copy()])
        self.assertEqual(len(m1), 1)
        self.assertEqual(m1[0]["url"], "https://www.ticketmaster.com/event/222")
        self.assertTrue(any(a["url"] == "https://seatgeek.com/knicks-vs-celtics-tickets/111" for a in m1[0]["_alt_sources"]))

        # Case 2: Ticketmaster first, SeatGeek second -> Ticketmaster remains primary
        m2 = _merge_duplicates([e_tm.copy(), e_sg.copy()])
        self.assertEqual(len(m2), 1)
        self.assertEqual(m2[0]["url"], "https://www.ticketmaster.com/event/222")
        self.assertTrue(any(a["url"] == "https://seatgeek.com/knicks-vs-celtics-tickets/111" for a in m2[0]["_alt_sources"]))

        # Case 3: SeatGeek first, Direct venue second -> Direct becomes primary
        m3 = _merge_duplicates([e_sg.copy(), e_direct.copy()])
        self.assertEqual(len(m3), 1)
        self.assertEqual(m3[0]["url"], "https://www.msg.com/events/knicks-celtics")
        self.assertTrue(any(a["url"] == "https://seatgeek.com/knicks-vs-celtics-tickets/111" for a in m3[0]["_alt_sources"]))

        # Case 4: Ticketmaster first, Direct venue second -> Direct becomes primary
        m4 = _merge_duplicates([e_tm.copy(), e_direct.copy()])
        self.assertEqual(len(m4), 1)
        self.assertEqual(m4[0]["url"], "https://www.msg.com/events/knicks-celtics")
        self.assertTrue(any(a["url"] == "https://www.ticketmaster.com/event/222" for a in m4[0]["_alt_sources"]))

    def test_compare_links_use_tickpick_and_stubhub(self):
        """Compare links must use fast, reliable TickPick and StubHub, dropping Gametime."""
        fut = (datetime.now(EASTERN) + timedelta(days=2)).replace(hour=20, minute=0, second=0, microsecond=0)
        e = {
            "name": "Radiohead Tribute Concert",
            "date": fut.isoformat(),
            "_time": fut,
            "venue": "Brooklyn Steel",
            "_source_venue": "The Bowery Presents",
            "url": "https://www.ticketmaster.com/event/777",
            "price": "$30",
            "category": "music",
        }
        links_html = _build_compare_links(e, e["name"])
        self.assertIn("TickPick", links_html)
        self.assertIn("https://www.tickpick.com/search/?q=Radiohead+Tribute+Concert", links_html)
        self.assertIn("StubHub", links_html)
        self.assertIn("https://www.stubhub.com/search?q=Radiohead+Tribute+Concert", links_html)
        self.assertIn("SeatGeek", links_html)
        self.assertNotIn("Gametime", links_html)
        self.assertNotIn("gametime.co", links_html)

    def test_meetup_and_eventbrite_scrapers(self):
        """Verify that Meetup and Eventbrite scrapers accurately parse physical in-person events."""
        from scrapers import scrape_meetup, scrape_eventbrite_jsonld
        from unittest.mock import patch, MagicMock

        # 1. Meetup test with physical and virtual events
        meetup_jsonld = json.dumps([
            {
                "@type": "Event",
                "name": "Central Park Board Game Picnic",
                "startDate": (datetime.now(timezone.utc) + timedelta(days=2)).isoformat(),
                "eventAttendanceMode": "https://schema.org/OfflineEventAttendanceMode",
                "location": {
                    "@type": "Place",
                    "name": "Sheep Meadow, Central Park",
                    "address": {"streetAddress": "Central Park", "addressLocality": "New York", "addressRegion": "NY"}
                },
                "url": "https://www.meetup.com/nyc-boardgames/events/12345"
            },
            {
                "@type": "Event",
                "name": "Zoom Virtual Trivia Night",
                "startDate": (datetime.now(timezone.utc) + timedelta(days=2)).isoformat(),
                "eventAttendanceMode": "https://schema.org/OnlineEventAttendanceMode",
                "location": {"@type": "VirtualLocation", "url": "https://zoom.us/j/123"},
                "url": "https://www.meetup.com/trivia/events/99999"
            }
        ])
        meetup_html = f'<html><head><script type="application/ld+json">{meetup_jsonld}</script></head><body></body></html>'

        with patch("scrapers._SESSION.get") as mock_get:
            m = MagicMock()
            m.status_code = 200
            m.text = meetup_html
            mock_get.return_value = m
            m_events = scrape_meetup("https://www.meetup.com/find/?keywords=board%20games", "TestUA")

        self.assertEqual(len(m_events), 1)
        self.assertEqual(m_events[0]["name"], "Central Park Board Game Picnic")
        self.assertEqual(m_events[0]["venue"], "Sheep Meadow, Central Park")
        self.assertIn("meetup.com", m_events[0]["url"])

        # 2. Eventbrite ItemList test
        eb_jsonld = json.dumps({
            "@type": "ItemList",
            "itemListElement": [
                {
                    "@type": "ListItem",
                    "item": {
                        "@type": "Event",
                        "name": "Williamsburg Salsa Social",
                        "startDate": (datetime.now(timezone.utc) + timedelta(days=3)).isoformat(),
                        "url": "https://www.eventbrite.com/e/williamsburg-salsa-tickets-1111",
                        "location": {
                            "@type": "Place",
                            "name": "Brooklyn Bowl",
                            "address": {"streetAddress": "61 Wythe Ave", "addressLocality": "Brooklyn", "addressRegion": "NY"}
                        },
                        "offers": {"price": "0.00"}
                    }
                }
            ]
        })
        eb_html = f'<html><head><script type="application/ld+json">{eb_jsonld}</script></head><body></body></html>'

        with patch("scrapers._SESSION.get") as mock_get:
            m = MagicMock()
            m.status_code = 200
            m.text = eb_html
            mock_get.return_value = m
            eb_events = scrape_eventbrite_jsonld("https://www.eventbrite.com/d/ny--brooklyn/salsa/", "TestUA")

        self.assertEqual(len(eb_events), 1)
        self.assertEqual(eb_events[0]["name"], "Williamsburg Salsa Social")
        self.assertEqual(eb_events[0]["venue"], "Brooklyn Bowl")
        self.assertEqual(eb_events[0]["price"], "Free")
        self.assertIn("eventbrite.com", eb_events[0]["url"])

    def test_luma_scraper_and_geo(self):
        """Luma NYC scraper should extract structured tech & community events with coordinates."""
        mock_payload = {
            "entries": [
                {
                    "api_id": "evt-mock1",
                    "event": {
                        "name": "NYC AI & Tech Summit",
                        "start_at": (datetime.now(timezone.utc) + timedelta(days=2)).isoformat(),
                        "url": "nyc-ai-summit-2026",
                        "geo_address_info": {
                            "mode": "shown",
                            "address": "100 Broadway",
                            "city": "New York",
                            "full_address": "100 Broadway, New York, NY 10005",
                            "sublocality": "Financial District",
                        },
                        "coordinate": {"latitude": 40.7081, "longitude": -74.0112},
                    },
                    "calendar": {
                        "name": "NY Tech Hub",
                        "description_short": "Premier community for builders and AI founders in Manhattan.",
                    },
                    "hosts": [{"name": "NY Tech Collective"}],
                    "ticket_info": {"is_free": False, "price": {"cents": 1500}},
                },
                {
                    "api_id": "evt-mock2",
                    "event": {
                        "name": "Brooklyn Tech Founder Mixer",
                        "start_at": (datetime.now(timezone.utc) + timedelta(days=3)).isoformat(),
                        "url": "bk-tech-mixer-oct",
                        "geo_address_info": {
                            "mode": "obfuscated",
                            "city": "Brooklyn",
                            "sublocality": "DUMBO",
                        },
                        "coordinate": {"latitude": 40.7033, "longitude": -73.9893},
                    },
                    "calendar": {"name": "Personal"},
                    "hosts": [{"name": "Dumbo Founders"}],
                    "ticket_info": {"is_free": True},
                }
            ],
            "has_more": False,
            "next_cursor": None,
        }

        from unittest.mock import patch, MagicMock
        mock_resp = MagicMock()
        mock_resp.json.return_value = mock_payload
        mock_resp.raise_for_status = MagicMock()

        with patch("scrapers._SESSION.get", return_value=mock_resp):
            events = scrape_luma("https://lu.ma/nyc", UA_CHROME)

        self.assertEqual(len(events), 2)
        ev1, ev2 = events[0], events[1]

        # Check event 1 (shown address, paid ticket, custom calendar)
        self.assertEqual(ev1["name"], "NYC AI & Tech Summit")
        self.assertEqual(ev1["venue"], "100 Broadway, New York")
        self.assertEqual(ev1["price"], "$15")
        self.assertEqual(ev1["url"], "https://lu.ma/nyc-ai-summit-2026")
        self.assertEqual(ev1["category"], "community")
        self.assertEqual(ev1["lat"], 40.7081)
        self.assertEqual(ev1["lng"], -74.0112)
        self.assertIn("Hosted by NY Tech Collective", ev1["description"])
        self.assertIn("Premier community", ev1["description"])

        # Check event 2 (obfuscated RSVP address, free ticket)
        self.assertEqual(ev2["name"], "Brooklyn Tech Founder Mixer")
        self.assertEqual(ev2["venue"], "DUMBO (RSVP for address)")
        self.assertEqual(ev2["price"], "Free")
        self.assertEqual(ev2["category"], "community")

        # Check geo resolution
        geo1 = resolve_event_geo(ev1)
        self.assertIsNotNone(geo1)
        self.assertEqual(geo1["lat"], 40.7081)
        self.assertEqual(geo1["lng"], -74.0112)
        self.assertEqual(geo1["neighborhood"], "Financial District")

        # Check URL priority and source naming
        self.assertEqual(_url_priority("https://lu.ma/nyc-ai-summit-2026"), 7)
        self.assertEqual(_ticket_source_name("https://lu.ma/nyc-ai-summit-2026"), "Luma")

    def test_broadway_theatre_category_and_merge(self):
        """Events at James Earl Jones Theatre and other Broadway houses must classify as theater."""
        # 1. Verification of BROADWAY_THEATRES membership
        self.assertIn("james earl jones", BROADWAY_THEATRES)
        self.assertIn("cort theatre", BROADWAY_THEATRES)
        self.assertIn("lena horne", BROADWAY_THEATRES)

        # 2. Category guessing for ambiguous titles at Broadway theatres
        cat = guess_category("Wanted", default="music", venue="James Earl Jones Theatre (New York, NY)")
        self.assertEqual(cat, "theater", "Wanted at James Earl Jones Theatre should be theater")

        # 3. Geo resolution for James Earl Jones Theatre
        geo = resolve_event_geo({"venue": "James Earl Jones Theatre (New York, NY)"})
        self.assertIsNotNone(geo)
        self.assertEqual(geo["venue"], "James Earl Jones Theatre")
        self.assertEqual(geo["neighborhood"], "Times Square")
        self.assertAlmostEqual(geo["lat"], 40.7593, places=3)
        self.assertAlmostEqual(geo["lng"], -73.9830, places=3)

        # 4. Subarea mapping
        subarea_label, subarea_key = resolve_subarea("manhattan", {"venue": "James Earl Jones Theatre (New York, NY)"})
        self.assertEqual(subarea_label, "Midtown & Chelsea")
        self.assertEqual(subarea_key, "midtown_chelsea")

        # 5. Merging duplicate cross-source event stubs (Ticketmaster + SeatGeek)
        tm_event = {
            "name": "Wanted",
            "date": "2026-10-25T17:00:00Z",
            "url": "https://www.ticketmaster.com/event/Z7r9jZ1A7P-qP",
            "venue": "James Earl Jones Theatre (New York, NY)",
            "lat": 40.7593,
            "lng": -73.990196,
            "category": "theater",
            "_source_venue": "Ticketmaster NYC",
        }
        sg_event = {
            "name": "Wanted - New York",
            "date": "2026-10-25T17:00:00Z",
            "url": "https://seatgeek.com/wanted-1-tickets/broadway/2026-10-25-1-pm/18470441",
            "venue": "James Earl Jones Theatre (New York, NY)",
            "lat": 40.7592,
            "lng": -73.983,
            "category": "theater",
            "_source_venue": "SeatGeek NYC",
        }
        merged = _merge_duplicates([tm_event, sg_event])
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["name"], "Wanted")
        self.assertEqual(merged[0]["url"], "https://www.ticketmaster.com/event/Z7r9jZ1A7P-qP")
        self.assertEqual(merged[0]["category"], "theater")
        self.assertTrue(any(a["url"] == "https://seatgeek.com/wanted-1-tickets/broadway/2026-10-25-1-pm/18470441" for a in merged[0]["_alt_sources"]))

    def test_skip_the_small_talk_direct_scraper(self):
        """Skip the Small Talk scraper parses official store items with venue, date, time, and pricing."""
        mock_payload = {
            "items": [
                {
                    "title": "Skip the Small Talk Night at McCarren Parkhouse: Tuesday, October 27, 2026",
                    "fullUrl": "/store/skip-the-small-talk-night-at-mccarren-parkhouse-tuesday-october-27-2026",
                    "categories": ["New York City"],
                    "excerpt": "<p><strong>EVENT START-END TIME</strong> | 7:00 pm - 9:00 pm ET <br /><strong>WHERE</strong> | McCarren Parkhouse, 855 Lorimer St, Brooklyn, NY 11222 (<a href=\"#\">map</a>)</p>",
                    "variants": [{"salePrice": 1500, "price": 2400}],
                },
                {
                    "title": "Friendship Comedy Night at Flop House Comedy Club (East Village): Thursday, October 29, 2026",
                    "fullUrl": "/store/friendship-comedy-night-at-flop-house-comedy-club-east-village-thursday-october-29-2026",
                    "categories": ["New York City"],
                    "excerpt": "<p><strong>EVENT START-END TIME</strong> | 7:00 pm - 9:00 pm ET <br /><strong>WHERE</strong> | Flop House Comedy Club, 312 E 14th St, New York, NY</p>",
                    "variants": [{"salePrice": 1500, "price": 2000}],
                },
                {
                    "title": "Skip the Small Talk Online: Wednesday, November 4, 2026",
                    "fullUrl": "/store/online-stst",
                    "categories": ["New York City", "Online"],
                    "excerpt": "",
                }
            ]
        }

        from unittest.mock import patch, MagicMock
        mock_resp = MagicMock()
        mock_resp.json.return_value = mock_payload
        mock_resp.raise_for_status = MagicMock()

        with patch("scrapers._SESSION.get", return_value=mock_resp):
            events = scrape_skip_the_small_talk("https://www.skipthesmalltalk.com/store?format=json", UA_CHROME)

        # Online event must be excluded
        self.assertEqual(len(events), 2)

        # Tuesday event
        self.assertEqual(events[0]["name"], "Skip the Small Talk Night at McCarren Parkhouse")
        self.assertEqual(events[0]["venue"], "McCarren Parkhouse")
        self.assertIn("855 Lorimer St", events[0]["address"])
        self.assertEqual(events[0]["price"], "$15")
        self.assertIn("2026-10-27T23:00:00", events[0]["date"])

        # Thursday event
        self.assertEqual(events[1]["name"], "Friendship Comedy Night at Flop House Comedy Club (East Village)")
        self.assertEqual(events[1]["venue"], "Flop House Comedy Club")
        self.assertIn("312 E 14th St", events[1]["address"])
        self.assertEqual(events[1]["price"], "$15")
        self.assertIn("2026-10-29T23:00:00", events[1]["date"])

    def test_warm_cache_and_scrape_fallbacks(self):
        """Test warm cache fallback when scraper raises exception or returns empty."""
        from unittest.mock import MagicMock
        from scrapers import _scrape_one, _last_known_good, _save_venue_cache, _venue_cache_path

        test_venue_name = "Resilient Warm Cache Venue"
        fut_date = (datetime.now(EASTERN) + timedelta(days=6)).strftime("%Y-%m-%dT20:00:00Z")
        saved_evs = [{"name": "Existing Concert", "date": fut_date, "venue": test_venue_name}]
        _save_venue_cache(test_venue_name, saved_evs)
        _last_known_good[test_venue_name] = saved_evs
        cpath = _venue_cache_path(test_venue_name)

        try:
            # Case 1: Scraper throws HTTPError/Exception (e.g. Cloudflare 403)
            failing_venue = {
                "name": test_venue_name,
                "url": "https://www.eventbrite.com/d/ny--new-york/test/",
                "ua": "TestUA",
                "scraper": MagicMock(side_effect=Exception("403 Client Error: Forbidden")),
                "default_category": "music"
            }
            res_fail = _scrape_one(failing_venue, force=True)
            self.assertTrue(res_fail.get("cached"))
            self.assertEqual(len(res_fail["events"]), 1)
            self.assertEqual(res_fail["events"][0]["name"], "Existing Concert")
            self.assertIn("403 Client Error", res_fail.get("error", ""))

            # Case 2: Scraper returns empty [] - must NOT wipe out cache
            empty_venue = {
                "name": test_venue_name,
                "url": "https://www.eventbrite.com/d/ny--new-york/test/",
                "ua": "TestUA",
                "scraper": MagicMock(return_value=[]),
                "default_category": "music"
            }
            res_empty = _scrape_one(empty_venue, force=True)
            self.assertEqual(len(res_empty["events"]), 1)
            self.assertEqual(res_empty["events"][0]["name"], "Existing Concert")
        finally:
            if os.path.exists(cpath):
                os.remove(cpath)
            _last_known_good.pop(test_venue_name, None)

    def test_eventbrite_jsonld_headers_and_parsing(self):
        """Test scrape_eventbrite_jsonld sends full browser headers and parses ItemList."""
        from scrapers import scrape_eventbrite_jsonld, UA_CHROME
        from unittest.mock import patch, MagicMock

        fut_date = (datetime.now(EASTERN) + timedelta(days=7)).strftime("%Y-%m-%dT19:00:00-04:00")
        sample_html = f"""
        <html>
        <head>
            <script type="application/ld+json">
            {{
                "@context": "https://schema.org",
                "@type": "ItemList",
                "itemListElement": [
                    {{
                        "@type": "ListItem",
                        "position": 1,
                        "item": {{
                            "@type": "Event",
                            "name": "Brooklyn Salsa Social",
                            "startDate": "{fut_date}",
                            "url": "https://www.eventbrite.com/e/brooklyn-salsa-social-12345",
                            "location": {{
                                "@type": "Place",
                                "name": "Williamsburg Dance Studio",
                                "address": {{
                                    "streetAddress": "100 Grand St",
                                    "addressLocality": "Brooklyn",
                                    "addressRegion": "NY"
                                }}
                            }},
                            "offers": {{
                                "price": "10.00"
                            }}
                        }}
                    }}
                ]
            }}
            </script>
        </head>
        </html>
        """
        mock_resp = MagicMock()
        mock_resp.text = sample_html
        mock_resp.raise_for_status = MagicMock()

        with patch("scrapers._SESSION.get", return_value=mock_resp) as mock_get:
            events = scrape_eventbrite_jsonld("https://www.eventbrite.com/d/ny--brooklyn/salsa/", UA_CHROME)
            mock_get.assert_called_once()
            call_headers = mock_get.call_args[1].get("headers", {})
            self.assertIn("Sec-Ch-Ua", call_headers)
            self.assertIn("Upgrade-Insecure-Requests", call_headers)
            self.assertEqual(call_headers["User-Agent"], UA_CHROME)

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["name"], "Brooklyn Salsa Social")
        self.assertEqual(events[0]["venue"], "Williamsburg Dance Studio")
        self.assertEqual(events[0]["price"], "$10.00")
        self.assertIn("100 Grand St", events[0]["address"])

    def test_queens_borough_classification_and_scrapers(self):
        """Verify Long Island City, Wyckoff Ave Ridgewood, and Queens venues classify as Queens and test direct Queens scrapers."""
        from template import _event_city, resolve_subarea
        from venues_geo import resolve_event_geo
        from scrapers import scrape_tribe_events_api, scrape_queens_theatre, scrape_qed_astoria
        from unittest.mock import patch, MagicMock

        # 1. Long Island City must NEVER be misclassified as Tri-State ("other")
        lic_ev = {"venue": "Culture Lab LIC (Long Island City)", "address": "5-25 46th Ave, Long Island City, NY"}
        lic_geo = resolve_event_geo(lic_ev)
        self.assertEqual(_event_city(lic_ev["venue"], "The Skint NYC", geo=lic_geo, event=lic_ev), "queens")
        self.assertEqual(resolve_subarea("queens", lic_ev, geo=lic_geo)[1], "astoria_lic")

        # 2. Wyckoff Ave in Ridgewood, Queens must classify as Queens, not Wyckoff, NJ
        h0l0_ev = {"venue": "H0L0", "address": "1090 Wyckoff Ave, Ridgewood, NY 11385"}
        h0l0_geo = resolve_event_geo(h0l0_ev)
        self.assertEqual(_event_city(h0l0_ev["venue"], "Resident Advisor NYC", geo=h0l0_geo, event=h0l0_ev), "queens")
        self.assertEqual(resolve_subarea("queens", h0l0_ev, geo=h0l0_geo)[1], "flushing_ridgewood")

        # 3. Queens Botanical Garden must resolve to Flushing, Queens (not NYBG in Bronx)
        qbg_ev = {"venue": "Queens Botanical Garden"}
        qbg_geo = resolve_event_geo(qbg_ev)
        self.assertIsNotNone(qbg_geo)
        self.assertEqual(qbg_geo["neighborhood"], "Flushing")
        self.assertEqual(_event_city(qbg_ev["venue"], "Queens Botanical Garden", geo=qbg_geo, event=qbg_ev), "queens")

        # 4. Event with Queens address but unmapped venue name
        jh_ev = {"venue": "P.S. 149 Christa McAuliffe", "address": "93-11 34th Avenue, Jackson Heights, Queens, NY"}
        self.assertEqual(_event_city(jh_ev["venue"], "Eventbrite", geo=None, event=jh_ev), "queens")
        self.assertEqual(resolve_subarea("queens", jh_ev, geo=None)[1], "jh_sunnyside")

        # 5. Tribe Events API scraper (e.g. Museum of the Moving Image)
        fut_str = (datetime.now(EASTERN) + timedelta(days=3)).strftime("%Y-%m-%d 18:30:00")
        mock_tribe_resp = MagicMock()
        mock_tribe_resp.json.return_value = {
            "events": [{
                "title": "Jim Henson&#8217;s Labyrinth 35mm Screening",
                "start_date": fut_str,
                "url": "https://movingimage.org/event/labyrinth/",
                "cost": "$15",
                "excerpt": "<p>Special screening in Astoria.</p>",
                "venue": {"venue": "Redstone Theater"}
            }]
        }
        mock_tribe_resp.raise_for_status = MagicMock()
        with patch("scrapers._SESSION.get", return_value=mock_tribe_resp):
            momi_evs = scrape_tribe_events_api("https://movingimage.org/wp-json/tribe/events/v1/events?per_page=50", "TestUA")
        self.assertEqual(len(momi_evs), 1)
        self.assertEqual(momi_evs[0]["name"], "Jim Henson’s Labyrinth 35mm Screening")
        self.assertEqual(momi_evs[0]["neighborhood"], "Astoria")
        self.assertEqual(momi_evs[0]["price"], "$15")

    def test_meetup_apollo_and_brooklyn_brainery(self):
        """Verify Meetup __NEXT_DATA__ Apollo state scraping, Brooklyn Brainery scraper, and Brooklyn/Queens meetup classification."""
        from template import _event_city
        from scrapers import scrape_meetup, scrape_brooklyn_brainery
        from unittest.mock import patch, MagicMock
        import json

        fut_iso = (datetime.now(EASTERN) + timedelta(days=4)).isoformat()
        apollo_payload = {
            "props": {
                "pageProps": {
                    "__APOLLO_STATE__": {
                        "Venue:101": {
                            "__typename": "Venue",
                            "id": "101",
                            "name": "Cobblestones Pub",
                            "address": "117-18 Queens Blvd",
                            "city": "Forest Hills",
                            "state": "NY",
                        },
                        "Group:202": {
                            "__typename": "Group",
                            "id": "202",
                            "name": "Queens Board Gamers Group",
                        },
                        "Event:303": {
                            "__typename": "Event",
                            "id": "303",
                            "title": "Tuesday Night Weekly Game Night - Forest Hills Edition",
                            "dateTime": fut_iso,
                            "eventType": "PHYSICAL",
                            "eventUrl": "https://www.meetup.com/queens-board-gamers-group/events/303/",
                            "description": "Board games in Forest Hills!",
                            "venue": {"__ref": "Venue:101"},
                            "group": {"__ref": "Group:202"},
                            "feeSettings": None,
                        },
                    }
                }
            }
        }
        mock_meetup_resp = MagicMock()
        mock_meetup_resp.text = f'<html><body><script id="__NEXT_DATA__" type="application/json">{json.dumps(apollo_payload)}</script></body></html>'
        mock_meetup_resp.raise_for_status = MagicMock()
        with patch("scrapers._SESSION.get", return_value=mock_meetup_resp):
            m_evs = scrape_meetup("https://www.meetup.com/queens-board-gamers-group/events/", "TestUA")
        self.assertEqual(len(m_evs), 1)
        self.assertIn("Forest Hills", m_evs[0]["venue"])
        self.assertEqual(_event_city(m_evs[0]["venue"], "Meetup: Queens Board Gamers Group", event=m_evs[0]), "queens")

        # Kings County and title fallback when venue is hidden
        kc_ev = {"name": "Sketch Prospect Park's Fall Leaves!", "venue": "Lincoln Road & Ocean Avenue (Kings County, NY)"}
        self.assertEqual(_event_city(kc_ev["venue"], "Meetup", event=kc_ev), "brooklyn")
        hidden_ev = {"name": "Non Alcoholic Happy Hour in Brooklyn", "venue": "NYC Community Location"}
        self.assertEqual(_event_city(hidden_ev["venue"], "Meetup", event=hidden_ev), "brooklyn")

        # Brooklyn Brainery scraper (filters out online courses)
        fut_dt = datetime.now(EASTERN) + timedelta(days=5)
        mon_name = fut_dt.strftime("%B")
        day_num = fut_dt.day
        bb_html = f"""
        <html><body>
          <div class="course-info">
            <h3><a href="/courses/watercolor-food-illustration">Watercolor Food Illustration</a></h3>
            <p><a href="/courses/watercolor-food-illustration">Tue. {mon_name} {day_num}, 6pm</a></p>
          </div>
          <div class="course-info">
            <h3><a href="/courses/history-talk-online">History Talk (Online)</a></h3>
            <p><a href="/courses/history-talk-online">Tue. {mon_name} {day_num}, 8pm</a></p>
          </div>
        </body></html>
        """
        mock_bb_resp = MagicMock()
        mock_bb_resp.text = bb_html
        mock_bb_resp.raise_for_status = MagicMock()
        with patch("scrapers._SESSION.get", return_value=mock_bb_resp):
            bb_evs = scrape_brooklyn_brainery("https://brooklynbrainery.com/courses", "TestUA")
        self.assertEqual(len(bb_evs), 1)
        self.assertEqual(bb_evs[0]["name"], "Watercolor Food Illustration")
        self.assertEqual(bb_evs[0]["venue"], "Brooklyn Brainery")


if __name__ == "__main__":
    unittest.main()

