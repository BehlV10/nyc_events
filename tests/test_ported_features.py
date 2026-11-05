"""Tests for features ported from Boston events and the new high-yield NYC feeds.

Run via:
  python -m unittest discover tests
"""

import json
import os
import re
import sys
import time
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
        # Visible markup only: JSON-LD for search engines intentionally lists the coming week.
        visible = re.sub(r'<script type="application/ld\+json">.*?</script>', "", page, flags=re.S)
        self.assertIn("Show 0", visible)
        self.assertNotIn("Show 5", visible)
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


class TestComedyClubScrapers(unittest.TestCase):
    def test_venuepilot_reads_account_id_and_local_time(self):
        day = _future_local(3, 0).date().isoformat()
        home = "<script>window.venuepilotSettings = { general: { accountIds: [2535], server: 'x' } }</script>"
        payload = {"data": {"paginatedEvents": {"collection": [
            {"id": 1, "name": "Saturday House Show", "date": day, "startTime": "21:30:00", "status": "Tickets",
             "ticketsUrl": "https://square.link/u/abc", "description": "<p>Lineup: <b>Wali Collins</b></p>",
             "venue": {"name": "Stand Up NY at Bond 45", "street1": "221 W 46th St", "city": "New York", "state": "NY", "postal": 10036}},
            {"id": 2, "name": "Cancelled Show", "date": day, "startTime": "19:00:00", "status": "Cancelled", "venue": {}},
        ]}}}
        with patch("scrapers._SESSION.get", return_value=_resp(text=home)), \
                patch("scrapers._SESSION.post", return_value=_resp(payload=payload)) as post:
            events = scrapers.scrape_venuepilot("https://standupny.com/", UA_CHROME)
        self.assertEqual(post.call_args[1]["json"]["variables"]["ids"], [2535])
        self.assertEqual(len(events), 1)
        e = events[0]
        self.assertEqual((_local(e["date"]).hour, _local(e["date"]).minute), (21, 30))
        self.assertEqual(e["url"], "https://square.link/u/abc")
        self.assertIn("221 W 46th St", e["address"])
        self.assertIn("Wali Collins", e["description"])

    def test_st_marks_calendar_cards(self):
        d = _future_local(2, 20, 30)
        card = (
            '<div class="event-item w-dyn-item"><a href="https://www.tixr.com/groups/stmarkscomedyclub/events/x-1">'
            '<div class="text-block-35">Joe Levy Headlines</div><div class="event-card grid"><div class="date-info grid">'
            f'<div class="month grid date">{d:%a}</div><div class="month grid">{d:%b}</div>'
            f'<div class="month grid custom-filter">{d:%B}</div><div class="month day grid">{d.day}</div>'
            '<div class="month day time">8:30 pm</div></div></div></a></div>'
        )
        with patch("scrapers._SESSION.get", return_value=_resp(text=card * 2)):
            events = scrapers.scrape_st_marks_comedy("https://www.stmarkscomedyclub.com/calendar", UA_CHROME)
        self.assertEqual(len(events), 1)
        self.assertEqual(_local(events[0]["date"]), d)
        self.assertEqual(events[0]["venue"], "St. Marks Comedy Club")
        self.assertTrue(events[0]["url"].startswith("https://www.tixr.com/"))

    def test_jsonld_crawl_follows_show_links(self):
        start = _future_local(4, 19, 30).isoformat()
        listing = '<a href="/shows/clean-up-your-act-1">A</a><a href="/shows/clean-up-your-act-1">dup</a><a href="/about">x</a>'
        show = ('<script type="application/ld+json">' + json.dumps({
            "@type": "ComedyEvent", "name": "Clean Up Your Act", "startDate": start,
            "location": {"@type": "ComedyClub", "name": "West Side Comedy Club"}}) + "</script>")
        def fake_get(url, **kw):
            return _resp(text=show if "/shows/" in url else listing)
        with patch("scrapers._SESSION.get", side_effect=fake_get) as get:
            events = scrapers.scrape_jsonld_crawl("https://westsidecomedyclub.com/shows", UA_CHROME)
        self.assertEqual(get.call_count, 2)
        self.assertEqual([e["name"] for e in events], ["Clean Up Your Act"])
        self.assertEqual(events[0]["venue"], "West Side Comedy Club")


class TestComedyRoundFour(unittest.TestCase):
    def test_stand_skips_west_cards_and_walks_days(self):
        d = _future_local(1, 21)
        slug = d.strftime("%Y-%m-%d-%H%M00")
        page = (
            f'<div class="row show_row"><h2 class="showtitle"><a href="https://thestandnyc.com//shows/show/1/{slug}-a">Union Sq Show</a></h2></div>'
            f'<div class="row show_row"><h6>This event will be held at The Stand West</h6>'
            f'<h2 class="showtitle"><a href="https://thestandnyc.com//shows/show/2/{slug}-b">West Show</a></h2></div>'
        )
        with patch("scrapers._SESSION.get", return_value=_resp(text=page)) as get:
            events = scrapers.scrape_the_stand_nyc("https://thestandnyc.com/shows", UA_CHROME, days=3)
        self.assertEqual(get.call_count, 3)
        self.assertEqual([e["name"] for e in events], ["Union Sq Show"])
        self.assertEqual(_local(events[0]["date"]), d)
        self.assertNotIn("//shows", events[0]["url"].replace("https://", ""))

    def test_magnet_month_grid(self):
        d = _future_local(2, 19, 30)
        page = (f'<table><tr><td><strong class="date">{d.day}</strong>'
                '<div class="an-event tab1"><abr class="time dtstart">7:30pm - $10</abr>'
                '<a href="https://magnettheater.com/show/1"><p class="summary"><strong>Megawatt</strong></p></a></div></td></tr></table>')
        empty = "<table></table>"
        def fake_get(url, **kw):
            return _resp(text=page if f"date={d.year}-{d.month:02d}-01" in url else empty)
        with patch("scrapers._SESSION.get", side_effect=fake_get):
            events = scrapers.scrape_magnet_theater("https://magnettheater.com/calendar/month/", UA_CHROME, months=3)
        self.assertEqual(len(events), 1)
        self.assertEqual(_local(events[0]["date"]), d)
        self.assertEqual(events[0]["price"], "$10")

    def test_pit_day_timestamps_and_rooms(self):
        d = _future_local(2, 0)
        page = (f"<div id='day-{int(d.timestamp())}' class='date day'><ul class='events'><li class='event'>"
                '<a href="https://thepit-nyc.com/events/x/"><p class="event__title">Improv Jam</p></a><ul class="performances">'
                '<li class="performance"><section class="action__time">7:00pm</section><div class="venue"><p class="venue__title">The PIT LAB</p></div></li>'
                '<li class="performance"><section class="action__time">9:30pm</section><div class="venue"><p class="venue__title">The Fishbowl</p></div></li>'
                '</ul></li></ul></div>')
        with patch("scrapers._SESSION.get", return_value=_resp(text=page)):
            events = scrapers.scrape_pit_calendar("https://thepit-nyc.com/calendar/", UA_CHROME, months=1)
        self.assertEqual([(_local(e["date"]).hour, e["venue"]) for e in events], [(19, "The PIT LAB"), (21, "The PIT (The Fishbowl)")])

    def test_improv_calendar_cards(self):
        d = _future_local(3, 19)
        card = (f'<a class="item" href="/brooklyn/event/x/"><div class="maindate"><dl><dt>{d:%b}</dt><dd>{d.day}<i> {d:%a}</i></dd></dl></div>'
                '<div class="info"><h3>Usual Suspects</h3><div class="times"><span>7:00pm</span><span>9:30pm</span></div>'
                '<div class="city"> @ The Lab</div></div></a>')
        with patch("scrapers._SESSION.get", return_value=_resp(text=card)):
            events = scrapers.scrape_improv_calendar("https://improv.com/brooklyn/calendar/", UA_CHROME, months=1)
        self.assertEqual([_local(e["date"]).hour for e in events], [19, 21])
        self.assertEqual(events[0]["venue"], "Brooklyn Improv (The Lab)")
        self.assertTrue(events[0]["url"].startswith("https://improv.com/brooklyn/event/"))

    def test_punchup_flight_data(self):
        dt = _future_local(2, 20).strftime("%Y-%m-%dT%H:%M:%S")
        obj = json.dumps({"id": "f17603a6-3c3f-49e7-a928-d2f57b80b8f0", "venue": "Greenpoint Comedy Club & Bar",
                          "ticket_link": "https://event.tixologi.com/event/1/tickets", "datetime": dt, "title": "Friday Showcase"})
        chunk = json.dumps('x:{"state":{"data":[' + obj + ']}}')[1:-1]
        page = f'<script>self.__next_f.push([1,"{chunk}"])</script>'
        with patch("scrapers._SESSION.get", return_value=_resp(text=page)):
            events = scrapers.scrape_punchup_venue("https://punchup.live/venue/greenpointcomedyclub", UA_CHROME)
        self.assertEqual(len(events), 1)
        self.assertEqual(_local(events[0]["date"]).hour, 20)
        self.assertEqual(events[0]["url"], "https://event.tixologi.com/event/1/tickets")

    def test_wix_events_warmup(self):
        start = (_future_local(2, 20).astimezone(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        data = {"events": {"events": [{"title": "Thursday Showcase", "slug": "thu-1",
                "scheduling": {"config": {"startDate": start, "scheduleTbd": False}},
                "location": {"name": "Bushwick Comedy Club", "address": "259 Melrose St, Brooklyn, NY 11206, USA",
                             "coordinates": {"lat": 40.702, "lng": -73.93}}}], "hasMore": False}}
        page = "<script>var w=" + json.dumps(data) + ";</script>"
        with patch("scrapers._SESSION.get", return_value=_resp(text=page)):
            events = scrapers.scrape_wix_events("https://www.bushwickcomedy.com/shows", UA_CHROME)
        self.assertEqual(events[0]["url"], "https://www.bushwickcomedy.com/event-details/thu-1")
        self.assertEqual(_local(events[0]["date"]).hour, 20)
        self.assertEqual(events[0]["address"], "259 Melrose St, Brooklyn, NY 11206")

    def test_tribe_follows_next_rest_url(self):
        d = _future_local(2, 19).strftime("%Y-%m-%d %H:%M:%S")
        p1 = {"events": [{"title": "Show A", "start_date": d, "url": "https://comedyvillage.com/a"}], "next_rest_url": "https://comedyvillage.com/p2"}
        p2 = {"events": [{"title": "Show B", "start_date": d, "url": "https://comedyvillage.com/b"}]}
        with patch("scrapers._SESSION.get", side_effect=[_resp(payload=p1), _resp(payload=p2)]):
            events = scrapers.scrape_tribe_events_api("https://comedyvillage.com/wp-json/tribe/events/v1/events?per_page=50", UA_CHROME)
        self.assertEqual([e["name"] for e in events], ["Show A", "Show B"])
        self.assertEqual(events[0]["venue"], "Comedy Village")

    def test_nycc_zero_price_tier_is_not_free(self):
        start = _future_local(2, 19, 30).isoformat()
        page = ('<script type="application/ld+json">' + json.dumps({"@type": "Event", "name": "Headliners", "startDate": start,
                "location": {"name": "New York Comedy Club"}, "offers": {"@type": "Offer", "price": "0.00"}}) + "</script>")
        with patch("scrapers._SESSION.get", return_value=_resp(text=page)):
            events = scrapers.scrape_jsonld_months("https://newyorkcomedyclub.com/calendar", UA_CHROME, months=2)
        self.assertEqual(len(events), 1)
        self.assertIsNone(events[0]["price"])


class TestCacheFingerprint(unittest.TestCase):
    def test_changed_source_does_not_reuse_old_cache(self):
        name = "Test Fingerprint Venue"
        path = scrapers._venue_cache_path(name)
        future = _future_local(3, 20).astimezone(timezone.utc).isoformat()
        old_ev = [{"name": "Old Eventbrite Result", "date": future, "url": "https://www.eventbrite.com/e/1"}]
        new_ev = [{"name": "Venue Calendar Show", "date": future, "url": "https://example.com/show"}]
        old_v = {"name": name, "url": "https://www.eventbrite.com/d/x/", "scraper": scrapers.scrape_eventbrite_jsonld}
        new_v = {"name": name, "url": "https://example.com/calendar", "scraper": lambda u, ua: [], "default_category": "comedy"}
        try:
            scrapers._save_venue_cache(name, old_ev, src=scrapers._source_fingerprint(old_v))
            self.assertIsNotNone(scrapers._load_venue_cache(name, src=scrapers._source_fingerprint(old_v)))
            self.assertIsNone(scrapers._load_venue_cache(name, src=scrapers._source_fingerprint(new_v)))
            # New scraper returns nothing: must not fall back to the old source's events.
            with patch("scrapers._run_scraper", return_value=[]):
                res = scrapers._scrape_one(new_v, force=True)
            self.assertEqual(res["events"], [])
            # Legacy entries (no fingerprint) are still accepted, so a deploy doesn't flush every cache.
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"ts": scrapers.time.time(), "venue": name, "events": new_ev}, f)
            self.assertIsNotNone(scrapers._load_venue_cache(name, src=scrapers._source_fingerprint(new_v)))
        finally:
            if os.path.exists(path):
                os.remove(path)
            scrapers._last_known_good.pop(name, None)


class TestGenericVenueParsers(unittest.TestCase):
    def test_html_cards_dates_times_and_skips(self):
        d = _future_local(3, 18, 30)
        page = ("<ul>"
                f'<li><h3>Gallery Late Night</h3><p>{d:%A, %B} {d.day}, {d.year} 6:30 pm</p><a href="/events/late-night">Learn more</a></li>'
                f'<li><h3>Museum Closed for Holiday</h3><p>{d:%B} {d.day}</p><a href="/events/closed">x</a></li>'
                f'<li><a href="/events/family-day">Family Day</a><span>{d:%b} {d.day}</span></li>'
                f'<li><a href="/about">About</a><span>{d:%b} {d.day}</span></li>'
                "</ul>")
        with patch("scrapers._SESSION.get", return_value=_resp(text=page)):
            events = scrapers.scrape_html_cards("https://example.org/calendar", UA_CHROME, link_re=r"^/events/", venue="Example Museum")
        names = {e["name"]: e for e in events}
        self.assertEqual(set(names), {"Gallery Late Night", "Family Day"})
        self.assertEqual(_local(names["Gallery Late Night"]["date"]), d)
        self.assertEqual(_local(names["Family Day"]["date"]).hour, 12)  # untimed -> noon placeholder
        self.assertEqual(names["Family Day"]["url"], "https://example.org/events/family-day")
        self.assertEqual(names["Family Day"]["venue"], "Example Museum")

    def test_tribe_unknown_domain_uses_event_venue(self):
        d = _future_local(2, 19).strftime("%Y-%m-%d %H:%M:%S")
        payload = {"events": [{"title": "Story Time", "start_date": d, "url": "https://kids.example.org/e/1",
                   "venue": {"venue": "Main Branch", "address": "1 Main St", "city": "Brooklyn", "zip": "11201",
                             "geo_lat": "40.69", "geo_lng": "-73.99"}}]}
        with patch("scrapers._SESSION.get", return_value=_resp(payload=payload)):
            events = scrapers.scrape_tribe_events_api("https://kids.example.org/wp-json/tribe/events/v1/events", UA_CHROME)
        self.assertEqual(events[0]["venue"], "Main Branch")
        self.assertEqual(events[0]["address"], "1 Main St, Brooklyn, NY 11201")
        self.assertNotIn("Queens", json.dumps(events[0]))
        self.assertAlmostEqual(events[0]["lat"], 40.69)

    def test_source_kwargs_are_passed(self):
        seen = {}
        def fake(url, ua, **kw):
            seen.update(kw)
            return []
        scrapers._run_scraper({"url": "https://x.example.org/", "ua": "UA", "scraper": fake, "kwargs": {"link_re": "^/e/"}})
        self.assertEqual(seen, {"link_re": "^/e/"})


class TestFever(unittest.TestCase):
    def test_fever_cards_local_time_and_filters(self):
        when = _future_local(3, 18, 30).strftime("%Y-%m-%dT%H:%M:%S") + "+00:00"
        page = (f'<a data-plan-id="1" data-plan-name="Candlelight: Vivaldi" data-plan-date="{when}" data-plan-price="35.5" href="/m/1">x</a>'
                f'<a data-plan-id="1" data-plan-name="Candlelight: Vivaldi" data-plan-date="{when}" href="/m/1">dup</a>'
                f'<a data-plan-id="2" data-plan-name="SUMMIT One Vanderbilt: Entry Ticket" data-plan-date="{when}" href="/m/2">x</a>'
                f'<a data-plan-id="3" data-plan-name="Westchester Winter Wonderland" data-plan-date="{when}" href="/m/3">x</a>')
        with patch("scrapers._SESSION.get", return_value=_resp(text=page)):
            events = scrapers.scrape_fever("https://feverup.com/en/new-york", UA_CHROME)
        self.assertEqual([e["name"] for e in events], ["Candlelight: Vivaldi"])
        self.assertEqual((_local(events[0]["date"]).hour, _local(events[0]["date"]).minute), (18, 30))
        self.assertEqual(events[0]["url"], "https://feverup.com/m/1")
        self.assertEqual(events[0]["price"], "From $36")


class TestTicketmasterWindows(unittest.TestCase):
    def test_per_day_windows_keep_api_key_and_filter(self):
        start = _future_local(1, 20).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        def ev(name, venue, state="NY"):
            return {"name": name, "url": "https://tm/e", "dates": {"start": {"dateTime": start}, "status": {"code": "onsale"}},
                    "_embedded": {"venues": [{"name": venue, "city": {"name": "New York"}, "state": {"stateCode": state}}]}}
        payload = {"_embedded": {"events": [ev("Hamilton", "Richard Rodgers Theatre"), ev("Parking Pass", "MSG"),
                                            ev("Jersey Show", "Prudential Center", "NJ"), ev("Banksy Museum - Flexiticket", "Banksy Museum")]}}
        calls = []
        def fake_get(url, params=None, **kw):
            calls.append(dict(params or {}))
            return _resp(payload=payload)
        with patch("scrapers._SESSION.get", side_effect=fake_get), patch("scrapers.time.sleep"):
            events = scrapers.scrape_ticketmaster_nyc("", "")
        self.assertEqual(len(calls), scrapers.HORIZON_DAYS)
        self.assertEqual(len({c["apikey"] for c in calls}), 1)  # the dedupe key used to clobber the API key
        self.assertTrue(all(c.get("endDateTime") for c in calls))
        self.assertEqual([e["name"] for e in events], ["Hamilton"])


class TestFamilyClassifier(unittest.TestCase):
    def test_family_phrases_and_adult_exclusions(self):
        for t in ("Weekend Family Workshop", "Stroller Walk in Prospect Park", "Parents' Night Out", "Ages 3-6 Music Class", "Bluey Live", "Puppet Show"):
            self.assertTrue(is_kid_family_event(t), t)
        for t in ("Family Guy Trivia", "Teenage Fanclub", "Puppet Slam 21+", "Family-style dinner club", "Crime Family Comedy",
                  "Speed Dating NYC: Men ages 48-65", "NYC Ages 21-40s Board Game Event", "Teen Jesus and The Jean Teasers"):
            self.assertFalse(is_kid_family_event(t), t)


class TestVillageVanguard(unittest.TestCase):
    def test_residencies_expand_to_nightly_listings(self):
        d = _future_local(10, 20).date()
        e = d + timedelta(days=5)
        page = (f"<h2>Tyshawn Sorey</h2><p>{d:%B} {d.day} - {e:%B} {e.day}</p><p>with Aaron Diehl</p>"
                f"<h2>COMING SOON!</h2><p>{d:%B} {d.day}-{e.day}</p><h3>Vanguard Jazz Orchestra</h3><p>Every Monday Night</p>")
        with patch("scrapers._SESSION.get", return_value=_resp(text=page)):
            events = scrapers.scrape_village_vanguard("https://villagevanguard.com/", UA_CHROME)
        sorey = [x for x in events if x["name"] == "Tyshawn Sorey"]
        self.assertEqual(len(sorey), 6)
        self.assertEqual(_local(sorey[0]["date"]).hour, 20)
        self.assertFalse(any("COMING" in x["name"] for x in events))
        self.assertTrue(any(x["name"] == "Vanguard Jazz Orchestra" for x in events))


class TestTurntable(unittest.TestCase):
    def test_turntable_performances(self):
        when = _future_local(2, 20).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        payload = {"count": 2, "results": [
            {"datetime": when, "show_id": 7, "show": {"id": 7, "name": "Charles McPherson Quintet"}, "sold": False, "availability_state": "selling_fast"},
            {"datetime": when, "show_id": 8, "show": {"id": 8, "name": "Gone Show"}, "sold": False, "availability_state": "cancelled"}]}
        with patch("scrapers._SESSION.get", return_value=_resp(payload=payload)) as get:
            events = scrapers.scrape_turntable("https://tickets.smokejazz.com/", UA_CHROME, venue="Smoke Jazz Club")
        self.assertEqual(get.call_args[1]["params"]["page_size"], 200)
        self.assertEqual([e["name"] for e in events], ["Charles McPherson Quintet"])
        self.assertEqual(_local(events[0]["date"]).hour, 20)
        self.assertNotIn("sold_out", events[0])
        self.assertTrue(events[0]["url"].startswith("https://tickets.smokejazz.com/shows/7/"))


class TestParksOpenData(unittest.TestCase):
    def test_parks_opendata_rows(self):
        start = _future_local(2, 10).strftime("%Y-%m-%dT%H:%M:%S.000")
        rows = [{"title": "Line Dance Fitness", "starttime": start, "parknames": "St. John's Park", "parkids": "B245",
                 "location": "Dance Room (in St. John's Park)", "categories": "Dance | Fitness | Shape Up NYC",
                 "coordinates": "40.6735, -73.9347", "link": {"url": "http://www.nycgovparks.org/events/x"}}]
        with patch("scrapers._SESSION.get", return_value=_resp(payload=rows)):
            events = scrapers.scrape_nyc_parks_opendata("https://data.cityofnewyork.us/resource/w3wp-dpdi.json", UA_CHROME)
        e = events[0]
        self.assertEqual(e["category"], "dance")
        self.assertEqual(e["address"], "St. John's Park, Brooklyn, NY")
        self.assertEqual(_local(e["date"]).hour, 10)
        self.assertTrue(e["url"].startswith("https://"))
        self.assertAlmostEqual(e["lat"], 40.6735)


class TestHostRotation(unittest.TestCase):
    def test_meetup_rotation_limits_live_refreshes(self):
        import tempfile
        old = scrapers.CACHE_DIR
        scrapers.CACHE_DIR = tempfile.mkdtemp()
        try:
            venues = [{"name": f"Meetup: T{i}", "url": f"https://www.meetup.com/find/?keywords=t{i}"} for i in range(10)]
            venues.append({"name": "Other", "url": "https://example.org/"})
            scrapers._save_venue_cache("Meetup: T0", [{"name": "x", "date": "2030-01-01T00:00:00+00:00"}])  # fresh
            picked = scrapers._pick_rotation_refreshes(venues, "meetup.com", limit=4, ttl=3600, now=time.time())
            self.assertEqual(len(picked), 4)
            self.assertNotIn("Meetup: T0", picked)  # fresh cache is not due
            self.assertNotIn("Other", picked)
            again = scrapers._pick_rotation_refreshes(venues, "meetup.com", limit=4, ttl=3600, now=time.time() + 1)
            self.assertFalse(picked & again)  # attempted sources go to the back of the line
        finally:
            scrapers.CACHE_DIR = old


class TestSidearmHomeGames(unittest.TestCase):
    def test_home_games_only(self):
        rows = [{"name": "[W] Fordham University Men's Soccer vs  Saint Louis", "date": _future_local(2, 19).isoformat(), "url": "https://x/a?b=1&amp;c=2", "address": "Bronx, N.Y., Moglia Stadium"},
                {"name": "Fordham University Volleyball at Rhode Island", "date": _future_local(3, 19).isoformat(), "url": "u", "address": "Kingston, R.I."},
                {"name": "Fordham University Squash vs Field", "date": _future_local(4, 19).isoformat(), "url": "u", "address": "Bala Cynwyd, Pa."}]
        with patch("scrapers.scrape_ical", return_value=rows):
            out = scrapers.scrape_sidearm_home_games("https://fordhamsports.com/calendar.ashx/calendar.ics", UA_CHROME,
                                                     home_re="Bronx", school="Fordham University", borough="Bronx")
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["name"], "Fordham University Men's Soccer vs Saint Louis")
        self.assertEqual(out[0]["venue"], "Fordham University (Moglia Stadium)")
        self.assertEqual(out[0]["address"], "Moglia Stadium, Bronx, NY")
        self.assertEqual(out[0]["url"], "https://x/a?b=1&c=2")


class TestDatedShowLinks(unittest.TestCase):
    def test_date_and_time_from_slug(self):
        d = _future_local(3, 21).date()
        href = f"/shows/{d:%Y-%m-%d}-mac-ohara-and-friends-900-pm/"
        page = (f'<a href="{href}">Mac O\u2019hara And Friends {d:%B} {d.day}th 9PM</a><a href="{href}">Buy Tickets</a>'
                f'<a href="/shows/{d:%Y-%m-%d}-late-show-1130-pm/"></a>')
        with patch("scrapers._SESSION.get", return_value=_resp(text=page)):
            events = scrapers.scrape_dated_show_links("https://www.greenwichvillagecomedyclub.com/", UA_CHROME, venue="GVCC")
        by = {e["name"]: e for e in events}
        self.assertIn("Mac O\u2019hara And Friends", by)
        self.assertEqual(_local(by["Mac O\u2019hara And Friends"]["date"]).hour, 21)
        self.assertEqual((_local(by["Late Show"]["date"]).hour, _local(by["Late Show"]["date"]).minute), (23, 30))


class TestEncodingDefault(unittest.TestCase):
    def test_missing_charset_decodes_as_utf8(self):
        import requests as _rq
        r = _rq.models.Response()
        r.headers["content-type"] = "text/html"
        r._content = "Dvo\u0159\u00e1k \u00ae".encode("utf-8")
        r.encoding = "ISO-8859-1"
        scrapers._default_utf8(r)
        self.assertEqual(r.text, "Dvo\u0159\u00e1k \u00ae")
        r2 = _rq.models.Response()
        r2.headers["content-type"] = "text/html; charset=windows-1252"
        r2.encoding = "windows-1252"
        scrapers._default_utf8(r2)
        self.assertEqual(r2.encoding, "windows-1252")  # declared charsets are respected


if __name__ == "__main__":
    unittest.main()
