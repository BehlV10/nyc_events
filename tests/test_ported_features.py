"""Tests for features ported from Boston events and the new high-yield NYC feeds.

Run via:
  python -m unittest discover tests
"""

import json
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import scrapers  # noqa: E402
from scrapers import (  # noqa: E402
    EASTERN,
    UA_CHROME,
    _clean_scraped_events,
    fix_doubled_url,
    guess_category,
    is_kid_family_event,
    is_placeholder_or_closed_event,
    is_standing_exhibit,
    is_utility_event,
    sanitize_event_url,
)
from template import _merge_duplicates, group_by_date, render_page  # noqa: E402


def _future_local(days, hour, minute=0):
    d = (datetime.now(EASTERN) + timedelta(days=days)).date()
    return datetime(d.year, d.month, d.day, hour, minute, tzinfo=EASTERN)


def _resp(text=None, payload=None, status=200):
    r = MagicMock()
    r.status_code = status
    r.text = text if text is not None else json.dumps(payload)
    r.content = r.text.encode()
    r.json = MagicMock(return_value=payload)
    r.raise_for_status = MagicMock()
    return r


def _local(iso):
    return datetime.fromisoformat(iso).astimezone(EASTERN)


class TestFiltersAndCleanup(unittest.TestCase):
    def test_moved_to_and_everyday_placeholders(self):
        self.assertTrue(is_placeholder_or_closed_event("[moved to Brooklyn Steel!] Some Band"))
        self.assertTrue(is_placeholder_or_closed_event("Volunteer Opportunities Everyday"))
        self.assertFalse(is_placeholder_or_closed_event("Moved by the Spirit: Gospel Night"))

    def test_fix_doubled_and_sanitize_urls(self):
        self.assertEqual(fix_doubled_url("https://venue.comhttps://venue.com/e/1"), "https://venue.com/e/1")
        share = "https://x.com/share?u=https://venue.com/e/1"
        self.assertEqual(fix_doubled_url(share), share)
        self.assertEqual(sanitize_event_url("/events/1", fallback="https://v.com"), "https://v.com")
        self.assertEqual(sanitize_event_url("https://v.com/cdn-cgi/l/email-protection#x", fallback="F"), "F")
        self.assertEqual(sanitize_event_url("https://v.com/e/1"), "https://v.com/e/1")

    def test_standing_exhibit_from_donyc_start_date(self):
        occ = _future_local(2, 10)
        start = occ - timedelta(days=60)
        url = f"https://donyc.com/events/{start.year}/{start.month}/{start.day}/photo-show"
        e = {"name": "Photo Show", "url": url, "venue": "Museum of the City of New York",
             "date": occ.astimezone(timezone.utc).isoformat()}
        self.assertTrue(is_standing_exhibit(e))
        e["venue"] = "Brooklyn Bowl"  # not a museum-type venue
        self.assertFalse(is_standing_exhibit(e))
        self.assertTrue(is_standing_exhibit({"name": "Winter Coat Drive!"}))

    def test_utility_and_family_categories(self):
        self.assertTrue(is_utility_event("ESOL Conversation Group"))
        self.assertFalse(is_utility_event("Sunday Sessions with DJ Spinna"))
        self.assertTrue(is_kid_family_event("Toddler Storytime"))
        self.assertFalse(is_kid_family_event("Childish Gambino Tribute Night"))
        self.assertEqual(guess_category("Resume Help Workshop", "community"), "services")
        self.assertEqual(guess_category("Baby Rave at the Library", "music"), "family")
        self.assertEqual(guess_category("Techno Night", "community"), "clubbing")

    def test_clean_scraped_events(self):
        when = _future_local(3, 20).astimezone(timezone.utc).isoformat()
        out = _clean_scraped_events([
            {"name": "Rock &amp; Roll Night", "date": when, "url": "https://a.comhttps://a.com/e/1"},
            {"name": "Rock & Roll Night", "date": when, "url": "https://a.com/e/1"},  # exact repeat
            {"name": "Virtual: Book Talk", "date": when},
            {"name": "Coding Hangout", "date": when, "venue": "Online"},
            {"name": "CANCELLED - Jazz Brunch", "date": when},
        ])
        self.assertEqual([e["name"] for e in out], ["Rock & Roll Night"])
        self.assertEqual(out[0]["url"], "https://a.com/e/1")

    def test_online_titles_dropped_but_hybrid_and_lookalikes_kept(self):
        when = _future_local(3, 20).astimezone(timezone.utc).isoformat()
        names = ["NYC Online Speed Dating (56+)", "Book Club on Zoom", "ONLINE LIVE- Word Game Party",
                 "Writing Workshop (In-Person & Online)", "Zoom Out: Photography Walk", "Virtual Reality Arcade Night"]
        out = _clean_scraped_events([{"name": n, "date": when} for n in names])
        self.assertEqual([e["name"] for e in out],
                         ["Writing Workshop (In-Person & Online)", "Zoom Out: Photography Walk", "Virtual Reality Arcade Night"])


class TestFeedScrapers(unittest.TestCase):
    def test_resident_advisor_local_time_and_pagination(self):
        start = _future_local(2, 22).strftime("%Y-%m-%dT%H:%M:%S.000")
        page1 = {"data": {"eventListings": {"totalResults": 101, "data": [
            {"event": {"title": "Techno Tuesday", "startTime": start, "cost": "15",
                       "contentUrl": "/events/1", "venue": {"name": "Nowadays", "address": "56-06 Cooper Ave; Ridgewood"}}}]}}}
        page2 = {"data": {"eventListings": {"totalResults": 101, "data": [
            {"event": {"title": "House Wednesday", "startTime": start, "cost": "",
                       "contentUrl": "/events/2", "venue": {"name": "Elsewhere", "address": ""}}}]}}}
        with patch("scrapers._SESSION.post", side_effect=[_resp(payload=page1), _resp(payload=page2)]) as post:
            events = scrapers.scrape_resident_advisor("https://ra.co/events/us/newyorkcity", UA_CHROME)
        self.assertEqual(post.call_count, 2)
        body = post.call_args_list[1][1]["json"]
        self.assertIn("$page: Int", body["query"])
        self.assertEqual(body["variables"]["page"], 2)
        self.assertEqual(len(events), 2)
        self.assertEqual(_local(events[0]["date"]).hour, 22)  # was shifted to 5pm when treated as UTC
        self.assertEqual(events[0]["price"], "$15")
        self.assertIn("Ridgewood", events[0]["address"])

    def test_eventbrite_exact_time_from_server_data(self):
        day = _future_local(5, 0).date()
        page = f"""<html><script>window.__SERVER_DATA__ = {{"search_data": {{"events": {{"results": [
            {{"eventbrite_event_id": "1234567890", "name": "Sunrise Run", "start_date": "{day}",
              "start_time": "07:30", "timezone": "America/New_York"}}]}}}}}};
            window.other = 1;</script>
          <script type="application/ld+json">{{"@type": "ItemList", "itemListElement": [
            {{"item": {{"@type": "Event", "name": "Sunrise Run", "startDate": "{day}",
              "url": "https://www.eventbrite.com/e/sunrise-run-tickets-1234567890"}}}},
            {{"item": {{"@type": "Event", "name": "Night Market", "startDate": "{day}",
              "url": "https://www.eventbrite.com/e/night-market-tickets-9999999999"}}}}]}}</script></html>"""
        with patch("scrapers._SESSION.get", return_value=_resp(text=page)):
            events = scrapers.scrape_eventbrite_jsonld("https://www.eventbrite.com/d/ny--new-york/running/", UA_CHROME)
        by_name = {e["name"]: _local(e["date"]) for e in events}
        self.assertEqual((by_name["Sunrise Run"].date(), by_name["Sunrise Run"].hour, by_name["Sunrise Run"].minute), (day, 7, 30))
        # No server time: date-only must stay on its own date (not the previous evening)
        self.assertEqual((by_name["Night Market"].date(), by_name["Night Market"].hour), (day, 19))

    def test_dice_event_url_price_and_address(self):
        start = _future_local(4, 21).isoformat()
        nd = {"props": {"pageProps": {"events": [{
            "id": "abc123", "name": "DJ Night", "dates": {"event_start_date": start},
            "venues": [{"name": "Public Records", "address": "233 Butler St, Brooklyn, NY 11217", "city": {"name": "Brooklyn"}}],
            "price": {"amount": 2266}}]}}}
        page = f'<script id="__NEXT_DATA__" type="application/json">{json.dumps(nd)}</script>'
        with patch("scrapers._SESSION.get", return_value=_resp(text=page)), patch("scrapers.time.sleep"):
            events = scrapers.scrape_dice_nyc("", UA_CHROME)
        self.assertEqual(len(events), 1)  # same event on every filter page is collapsed
        e = events[0]
        self.assertEqual(e["url"], "https://dice.fm/event/abc123")
        self.assertEqual(e["price"], "$22.66")
        self.assertIn("11217", e["address"])

    def test_songkick_strips_venue_and_stops_at_horizon(self):
        soon = _future_local(3, 20).strftime("%Y-%m-%dT%H:%M:%S")
        late = _future_local(scrapers.HORIZON_DAYS + 5, 20).strftime("%Y-%m-%dT%H:%M:%S")
        ld = [{"@type": "MusicEvent", "name": "YEBBA @ Brooklyn Paramount", "startDate": soon,
               "url": "https://www.songkick.com/concerts/1-yebba?utm_source=x",
               "location": {"@type": "Place", "name": "Brooklyn Paramount",
                            "address": {"streetAddress": "385 Flatbush Ave Ext", "addressLocality": "Brooklyn", "addressRegion": "NY", "postalCode": "11201"},
                            "geo": {"latitude": 40.69, "longitude": -73.98}}},
              {"@type": "MusicEvent", "name": "Far Future @ MSG", "startDate": late, "location": {"name": "MSG"}}]
        page = f'<script type="application/ld+json">{json.dumps(ld)}</script>'
        with patch("scrapers._SESSION.get", return_value=_resp(text=page)) as get, patch("scrapers.time.sleep"):
            events = scrapers.scrape_songkick_metro("https://www.songkick.com/metro-areas/7644-us-new-york-nyc", UA_CHROME)
        self.assertEqual(get.call_count, 1)  # past the horizon on page 1 -> no page 2
        self.assertEqual(len(events), 1)
        e = events[0]
        self.assertEqual(e["name"], "YEBBA")
        self.assertEqual(_local(e["date"]).hour, 20)
        self.assertEqual(e["url"], "https://www.songkick.com/concerts/1-yebba")
        self.assertIn("11201", e["address"])

    def test_nyc_parks_category_microdata(self):
        start = _future_local(2, 11).isoformat()
        page = f"""<div itemscope itemtype="http://schema.org/Event" class="row event">
          <h3 itemprop="name"><a href="/events/2026/11/05/greenbelt-hike">Greenbelt Adult Hike</a></h3>
          <h4 class="location" itemprop="location" itemscope itemtype="http://schema.org/Place">at <span itemprop="name">High Rock Gate</span> (in High Rock Park)
            <span itemprop="address" itemscope><meta itemprop="streetAddress" content="Nevada Ave" />, <span itemprop="addressLocality">Staten Island</span></span></h4>
          <meta itemprop="startDate" content="{start}"><p><span itemprop="description">Crisp fall hike.</span><strong>Free!</strong></p></div>"""
        empty = "<html></html>"

        def fake_get(url, **_kw):
            return _resp(text=page if url.endswith("/hiking") else empty)

        with patch("scrapers._SESSION.get", side_effect=fake_get), patch("scrapers.time.sleep"):
            events = scrapers.scrape_nyc_parks_categories("", UA_CHROME)
        self.assertEqual(len(events), 1)
        e = events[0]
        self.assertEqual(e["venue"], "High Rock Gate (High Rock Park)")
        self.assertEqual(e["price"], "Free")
        self.assertEqual(e["category"], "outdoors")
        self.assertEqual(e["neighborhood"], "Staten Island")
        self.assertTrue(e["url"].startswith("https://www.nycgovparks.org/events/"))

    def test_partiful_public_is_not_free(self):
        start = _future_local(3, 19).astimezone(timezone.utc).isoformat()
        nd = {"props": {"pageProps": {"items": [{"item": {"event": {
            "id": "abc", "title": "Rooftop Mixer", "startDate": start, "isPublic": True,
            "locationInfo": {"displayName": "Le Bain", "mapsInfo": {"addressLines": ["848 Washington St", "New York, NY 10014"]}}}}}]}}}
        page = f'<script id="__NEXT_DATA__" type="application/json">{json.dumps(nd)}</script>'
        with patch("scrapers._SESSION.get", return_value=_resp(text=page)), \
                patch("scrapers._get_partiful_targets", return_value=["https://partiful.com/explore/l/nyc/events"]):
            events = scrapers.scrape_partiful("https://partiful.com/explore/l/nyc/events", UA_CHROME)
        self.assertEqual(len(events), 1)
        self.assertIsNone(events[0]["price"])
        self.assertEqual(events[0]["url"], "https://partiful.com/e/abc")
        self.assertIn("10014", events[0]["address"])

    def test_ical_rrule_with_exdate(self):
        first = _future_local(1, 19)
        skip = first + timedelta(days=7)
        ics = "\r\n".join([
            "BEGIN:VCALENDAR", "BEGIN:VEVENT", "UID:run-1", "SUMMARY:Free Social Run",
            f"DTSTART;TZID=America/New_York:{first.strftime('%Y%m%dT%H%M%S')}",
            "RRULE:FREQ=WEEKLY;COUNT=3",
            f"EXDATE;TZID=America/New_York:{skip.strftime('%Y%m%dT%H%M%S')}",
            "LOCATION:Pier 45\\, Hudson River Park", "END:VEVENT", "END:VCALENDAR"])
        with patch("scrapers._SESSION.get", return_value=_resp(text=ics)):
            events = scrapers.scrape_ical("https://example.com/cal.ics", UA_CHROME)
        days = [_local(e["date"]).date() for e in events]
        self.assertEqual(days, [first.date(), (first + timedelta(days=14)).date()])
        self.assertEqual(events[0]["price"], "Free")
        self.assertEqual(events[0]["address"], "Pier 45, Hudson River Park")


class TestDedup(unittest.TestCase):
    def _ev(self, name, venue, local_dt, source, url=None, category="music"):
        return {"name": name, "venue": venue, "_source_venue": source, "category": category,
                "date": local_dt.astimezone(timezone.utc).isoformat(), "_time": local_dt,
                "url": url or f"https://example.com/{abs(hash((name, source, local_dt)))}"}

    def test_possessive_title_merges(self):
        t = _future_local(4, 19, 30)
        out = _merge_duplicates([
            self._ev("Harper Lee's To Kill a Mockingbird", "Shubert Theatre", t, "Ticketmaster NYC", category="theater"),
            self._ev("To Kill a Mockingbird", "Shubert Theatre", t, "SeatGeek NYC", category="theater"),
        ])
        self.assertEqual(len(out), 1)

    def test_noon_placeholder_merges_and_upgrades_time(self):
        noon, evening = _future_local(6, 12), _future_local(6, 20)
        out = _merge_duplicates([
            self._ev("Japanese Breakfast", "Brooklyn Steel", noon, "SeatGeek NYC"),
            self._ev("Japanese Breakfast", "Brooklyn Steel", evening, "Brooklyn Steel"),
        ])
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["_time"].hour, 20)

    def test_distinct_run_clubs_from_generic_feeds_stay_separate(self):
        t = _future_local(2, 19)
        out = _merge_duplicates([
            self._ev("Brooklyn Run Club Social 5K", "McCarren Park", t, "Meetup: Run Clubs", category="sports"),
            self._ev("Brooklyn Run Club Tempo Night", "Prospect Park", t, "Eventbrite: Run Clubs", category="sports"),
        ])
        self.assertEqual(len(out), 2)

    def test_concurrent_comedy_rooms_stay_separate(self):
        t = _future_local(3, 21, 30)
        out = _merge_duplicates([
            self._ev("Comedy Cellar MacDougal Street Show", "Comedy Cellar", t, "Comedy Cellar", category="comedy"),
            self._ev("Comedy Cellar Village Underground Show", "Comedy Cellar", t, "Comedy Cellar", category="comedy"),
        ])
        self.assertEqual(len(out), 2)

    def test_formatting_variants_merge_at_same_venue(self):
        t = _future_local(5, 20)
        out = _merge_duplicates([
            self._ev("half•alive", "Terminal 5", t, "Ticketmaster NYC"),
            self._ev("halfalive", "Terminal 5 (Hell's Kitchen)", t + timedelta(minutes=30), "Songkick NYC Concerts"),
        ])
        self.assertEqual(len(out), 1)

    def test_hourly_tours_consolidate(self):
        evs = [self._ev("Brooklyn Brewery Tour", "Brooklyn Brewery", _future_local(3, h), "Brooklyn Brewery",
                        category="food") for h in (13, 14, 15, 16)]
        out = _merge_duplicates(evs)
        self.assertEqual(len(out), 1)
        self.assertEqual(len(out[0]["_tour_times"]), 4)
        self.assertIn("1:00 PM", out[0]["description"])

    def test_group_by_date_categorizes_and_filters(self):
        t = _future_local(2, 10).astimezone(timezone.utc).isoformat()
        results = [{"venue": "NYPL", "url": "https://www.nypl.org/events", "events": [
            {"name": "ESL Conversation Group", "date": t, "category": "theater"},
            {"name": "Toddler Storytime", "date": t},
            {"name": "Winter Coat Drive", "date": t},
            {"name": "Author Talk", "date": t, "url": "/relative/path"},
        ]}]
        dated, _tba, _ongoing = group_by_date(results)
        events = {e["name"]: e for _d, es in dated for e in es}
        self.assertEqual(events["ESL Conversation Group"]["category"], "services")
        self.assertEqual(events["Toddler Storytime"]["category"], "family")
        self.assertNotIn("Winter Coat Drive", events)
        self.assertEqual(events["Author Talk"]["url"], "https://www.nypl.org/events")


class TestRenderSplit(unittest.TestCase):
    def test_split_deferred_and_default_unchecked_buckets(self):
        events = [{"name": f"Show {i}", "venue": "Brooklyn Bowl", "category": "music",
                   "date": _future_local(i, 20).astimezone(timezone.utc).isoformat(), "url": f"https://x.com/{i}"}
                  for i in range(0, 6)]
        events.append({"name": "Toddler Storytime", "venue": "Brooklyn Public Library",
                       "date": _future_local(1, 10).astimezone(timezone.utc).isoformat(), "url": "https://x.com/s"})
        payload = {"venues": [{"venue": "Brooklyn Bowl", "url": "https://x.com", "events": events}]}
        page, deferred = render_page(payload, split_deferred=True)
        self.assertIn('data-src="deferred_days.html?v=', page)
        self.assertIn("Show 0", page)
        self.assertNotIn("Show 5", page)
        self.assertIn("Show 5", deferred)
        self.assertRegex(page, r'class="cat-chk" value="Kids &amp; Family">')
        self.assertRegex(page, r'class="cat-chk" value="Music &amp; nightlife" checked>')
        inline = render_page(payload)
        self.assertIsInstance(inline, str)
        self.assertIn("Show 5", inline)


class TestRenderDetails(unittest.TestCase):
    def test_topic_feeds_are_not_presenters_and_alts_collapse(self):
        when = _future_local(2, 19).astimezone(timezone.utc).isoformat()
        url = "https://www.eventbrite.com/e/pizza-crawl-tickets-2001116388988"
        results = [
            {"venue": f"Eventbrite: {topic}", "url": f"https://www.eventbrite.com/d/ny--new-york/{slug}/",
             "events": [{"name": "Haunted Pizza Crawl", "date": when, "venue": "Washington Square Park",
                         "url": f"{url}?aff={slug}", "category": "food"}]}
            for topic, slug in (("Run Clubs", "run-club"), ("Hikes", "hike"), ("Outdoor Adventures", "outdoor-adventure"))
        ]
        page = render_page({"venues": results})
        self.assertNotIn("presented by Eventbrite:", page)
        self.assertEqual(page.count("Haunted Pizza Crawl</a>"), 1)
        self.assertNotIn("also on", page.split("Haunted Pizza Crawl</a>")[1].split("</li>")[0])


class TestTopicSources(unittest.TestCase):
    def test_topic_sources_registered_without_duplicates(self):
        names = [v["name"] for v in scrapers.VENUES]
        urls = [v["url"] for v in scrapers.VENUES]
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(len(urls), len(set(urls)))
        self.assertIn("Meetup: Run Clubs", names)
        self.assertIn("Eventbrite: DJ Sets", names)
        for v in scrapers.VENUES:
            if v["name"].startswith(("Meetup: ", "Eventbrite: ")) and v["scraper"] in (scrapers.scrape_meetup, scrapers.scrape_eventbrite_pages):
                self.assertTrue(v["url"].startswith("https://www."), v["name"])


if __name__ == "__main__":
    unittest.main()
