"""Sold-out listings: a real sell-out, a full free RSVP, a waitlist, and a weekly party whose free
guestlist tier ran out (the door's still open, so it gets no label)."""
import os
import re
import sys
import unittest
from datetime import datetime, timedelta, timezone

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in (BASE_DIR, os.path.join(BASE_DIR, "scripts")):
    if p not in sys.path:
        sys.path.insert(0, p)

import scrapers  # noqa: E402
import seo  # noqa: E402
import template as T  # noqa: E402
from export_feeds import build_rss  # noqa: E402
from scrapers import EASTERN  # noqa: E402


def _eb(price=None, sold_out=False, waitlist=False, series=False, is_free=False, lo=None, hi=None):
    ta = {"is_sold_out": sold_out, "waitlist_available": waitlist}
    if lo is not None:
        ta["minimum_ticket_price"] = {"major_value": lo}
    if hi is not None:
        ta["maximum_ticket_price"] = {"major_value": hi}
    return {"is_free": is_free, "is_series": series, "ticket_availability": ta}


class EventbriteData(unittest.TestCase):
    def test_a_sold_out_event_keeps_its_price(self):
        ev = _eb(sold_out=True, lo="55.80", hi="55.80")
        self.assertEqual(scrapers._eb_price(ev), "$55.80")
        self.assertEqual(scrapers._eb_availability(ev), {"sold_out": True, "waitlist": False, "series": False})

    def test_waitlist_and_series_flags(self):
        ev = _eb(sold_out=True, waitlist=True, series=True, lo="0.00", hi="108.55")
        self.assertEqual(scrapers._eb_price(ev), "Free - $108.55")
        self.assertEqual(scrapers._eb_availability(ev), {"sold_out": True, "waitlist": True, "series": True})

    def test_waitlist_only_counts_when_sold_out(self):
        self.assertFalse(scrapers._eb_availability(_eb(waitlist=True))["waitlist"])

    def test_only_true_flags_are_stored(self):
        e = {}
        self.assertFalse(scrapers._apply_sold_out(e, {"sold_out": False, "waitlist": False, "series": True}))
        self.assertEqual(e, {})
        self.assertTrue(scrapers._apply_sold_out(e, {"sold_out": True, "waitlist": False, "series": True}))
        self.assertEqual(e, {"sold_out": True, "series": True})


class PriceText(unittest.TestCase):
    def test_sold_out_moves_out_of_the_price(self):
        for price, rest in (("Sold Out", None), ("Sold out", None), ("$85-$135 (sold out)", "$85-$135"),
                            ("$25 [SOLD OUT]", "$25"), ("$20", "$20"), (None, None)):
            e = T._normalize_sold_out_price({"price": price})
            self.assertEqual(e["price"], rest, price)
            self.assertEqual(bool(e.get("sold_out")), bool(price and "sold" in price.lower()), price)


class States(unittest.TestCase):
    def test_paid_free_waitlist_and_weekly(self):
        self.assertIsNone(T.sold_out_state({"price": "$20"}))
        self.assertEqual(T.sold_out_state({"price": "$20", "sold_out": True}), "sold_out")
        self.assertEqual(T.sold_out_state({"price": "$20", "sold_out": True, "waitlist": True}), "waitlist")
        self.assertEqual(T.sold_out_state({"price": "Free", "sold_out": True}), "rsvp_full")
        # A weekly party's free RSVP tier ran out: pay at the door, nothing to flag.
        party = {"price": "Free - $108.55", "sold_out": True, "series": True, "category": "clubbing"}
        self.assertIsNone(T.sold_out_state(party))
        self.assertIsNone(T.sold_out_state({"price": "Free", "sold_out": True, "category": "music"}, recurring=True))
        # A weekly storytime or workshop that's full is worth saying so.
        self.assertEqual(T.sold_out_state({"price": "Free", "sold_out": True, "category": "community"}, recurring=True),
                         "rsvp_full")
        # A paid weekly show that sold out is still sold out.
        self.assertEqual(T.sold_out_state({"price": "$55.80", "sold_out": True, "series": True}), "sold_out")

    def test_weekly_means_a_few_weekdays_not_a_nightly_run(self):
        start = datetime(2026, 11, 23, 20, tzinfo=EASTERN)  # a Monday

        def ev(name, offsets):
            return [{"name": name, "_source_venue": "V", "venue": "Club", "_time": start + timedelta(days=d)}
                    for d in offsets]

        events = (ev("Mon Night Jazz", [0, 7, 14])                                   # weekly
                  + ev("Residency", [0, 1, 7, 8, 14, 15])                             # Mon + Tue, weekly
                  + ev("Six", [d for d in range(15) if d % 7 != 0])                   # six nights a week
                  + ev("One Off", [3]))
        keys = T.compute_recurring([(None, events)])
        names = {k[0] for k in keys}
        self.assertEqual(names, {"mon night jazz", "residency"})
        self.assertEqual(T.recurring_key(events[0]), ("mon night jazz", "V", "club"))
        # A ticket seller's handful of a run's dates isn't a weekly event.
        sampled = [dict(e, _source_venue="SeatGeek NYC") for e in ev("& Juliet", [6, 13, 20])]
        self.assertEqual(T.compute_recurring([(None, sampled)]), set())

    def test_price_text_for_feeds(self):
        self.assertEqual(T.price_with_availability({"price": "$20", "sold_out": True}), "$20 (sold out)")
        self.assertEqual(T.price_with_availability({"price": "Free", "sold_out": True}), "Free (rsvp full)")
        self.assertEqual(T.price_with_availability({"sold_out": True}), "Sold out")
        self.assertEqual(T.price_with_availability({"price": "$20"}), "$20")


def _render(events):
    """Events two days out at one source, through render_page; returns (html, dated)."""
    day = (datetime.now(EASTERN) + timedelta(days=2)).replace(second=0, microsecond=0)
    rows = []
    for i, (name, kw) in enumerate(events):
        t = day.replace(hour=18 + i % 5, minute=0)
        rows.append(dict({"name": name, "date": t.astimezone(timezone.utc).isoformat(), "venue": "Elsewhere Brooklyn",
                          "url": f"https://www.eventbrite.com/e/x-tickets-{1000 + i}", "category": "music"}, **kw))
    ctx = {}
    html = T.render_page({"generated_at": datetime.now(timezone.utc).isoformat(), "venues": [
        {"venue": "Some Promoter", "url": "https://x.example/", "error": None, "events": rows}]}, context_out=ctx)
    return html, ctx["dated"]


class Page(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html, cls.dated = _render([
            ("Gone Show", {"price": "$30", "sold_out": True}),
            ("Open Show", {"price": "$15"}),
            ("Opening Reception", {"price": "Free", "sold_out": True}),
            ("Waitlist Show", {"price": "$40", "sold_out": True, "waitlist": True}),
            ("Weekly Club Night", {"price": "Free - $108.55", "sold_out": True, "series": True, "category": "clubbing"}),
            ("Legacy Listing", {"price": "Sold Out"}),
        ])

    def _li(self, name):
        m = re.search(r'<li class="([^"]+)"[^>]*>(?:(?!</li>).)*?' + re.escape(name) + r'(?:(?!</li>).)*</li>', self.html, re.S)
        self.assertIsNotNone(m, name)
        return m.group(1), m.group(0)

    def test_labels(self):
        cls, li = self._li("Gone Show")
        self.assertEqual(cls, "event soldout")
        self.assertIn('class="price">$30</span>', li)
        self.assertIn(">Sold out</span>", li)
        self.assertIn(">RSVP full</span>", self._li("Opening Reception")[1])
        self.assertIn(">Waitlist</span>", self._li("Waitlist Show")[1])
        self.assertIn(">Sold out</span>", self._li("Legacy Listing")[1])
        self.assertNotIn("Sold Out", self._li("Legacy Listing")[1].replace(">Sold out<", ""))

    def test_weekly_party_and_open_show_have_no_label(self):
        for name in ("Weekly Club Night", "Open Show"):
            cls, li = self._li(name)
            self.assertEqual(cls, "event", name)
            self.assertNotIn('class="avail', li)

    def test_sold_out_listings_go_last(self):
        order = [self.html.index(f'rel="noopener">{n}</a>') for n in ("Open Show", "Weekly Club Night", "Gone Show", "Opening Reception",
                                              "Waitlist Show", "Legacy Listing")]
        self.assertEqual(order[:2], sorted(order[:2]))
        self.assertLess(max(order[:2]), min(order[2:]))
        self.assertEqual(len(re.findall(r'<li class="event soldout"[^>]* data-soldout="true"', self.html)), 4)

    def test_skip_sold_out_checkbox_is_on_by_default(self):
        self.assertIn('<input type="checkbox" id="skip-soldout-chk" checked>', self.html)
        self.assertIn("Skip sold-out events", self.html)
        # Search and My Schedule still show them; unticking is remembered in the link (#soldout=1).
        self.assertIn("const skipSoldout = !!(skipSoldoutChk && skipSoldoutChk.checked) && !searchText && !starredOnly;", self.html)
        self.assertIn("const soldoutOk = !skipSoldout || !m.soldout;", self.html)
        self.assertIn("params.set('soldout', '1')", self.html)
        self.assertIn("if (skipSoldoutChk) skipSoldoutChk.checked = true;", self.html)  # Reset turns skipping back on

    def test_schema_and_guide_pages(self):
        events = {e["name"]: e for _d, evs in self.dated for e in evs}
        self.assertEqual(seo.event_schema(events["Gone Show"])["offers"]["availability"], "https://schema.org/SoldOut")
        self.assertEqual(seo.event_schema(events["Open Show"])["offers"]["availability"], "https://schema.org/InStock")
        hub = {"slug": "x", "time": None}
        names = {e["name"] for e in seo.hub_events(hub, self.dated)}
        self.assertEqual(names, {"Open Show", "Weekly Club Night"})

    def test_feeds_note_the_sell_out(self):
        events = {e["name"]: e for _d, evs in self.dated for e in evs}
        rss = build_rss([events["Gone Show"]])
        self.assertIn("Price: $30 (sold out).", rss)


class Highlights(unittest.TestCase):
    def test_sold_out_events_arent_picked(self):
        from curate_highlights import score_event
        t = (datetime.now(EASTERN) + timedelta(days=2)).replace(hour=20, minute=0, second=0, microsecond=0)
        base = {"name": "Big Show", "venue": "Brooklyn Steel", "_source_venue": "Brooklyn Steel", "category": "music",
                "_time": t, "date": t.isoformat(), "price": "$40"}
        self.assertIsNotNone(score_event(dict(base), set())[0])
        self.assertIsNone(score_event(dict(base, sold_out=True), set())[0])


class WeeklyEvents(unittest.TestCase):
    def test_a_weekly_event_is_marked_weekly(self):
        day = (datetime.now(EASTERN) + timedelta(days=2)).replace(hour=21, minute=0, second=0, microsecond=0)
        rows = [{"name": "Friday Party", "date": (day + timedelta(days=7 * i)).astimezone(timezone.utc).isoformat(),
                 "venue": "Kimoto Rooftop", "url": f"https://www.eventbrite.com/e/p-tickets-{i}", "category": "clubbing",
                 "price": "Free", "sold_out": True} for i in range(2)]
        html = T.render_page({"generated_at": datetime.now(timezone.utc).isoformat(), "venues": [
            {"venue": "Promoter", "url": "https://x.example/", "error": None, "events": rows}]})
        self.assertIn('data-recur="weekly"', html)
        self.assertIn("↻ weekly", html)
        self.assertNotIn("RSVP full</span>", html)  # weekly + free tier gone: no label


if __name__ == "__main__":
    unittest.main()
