"""AllEvents listings point at the seller's own page (Eventbrite etc.) when AllEvents says where they came from."""
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import scrapers  # noqa: E402

EB = "https://www.eventbrite.com/e/destin-conrad-bashment-tickets-2004496419751"


def _page(seller, origin="eventbrite", extra=""):
    wrapped = f"https://consumer.pxf.io/c/1/2/3?partnerpropertyid=9&u={quote(seller + '?aff=allevents&utm_source=x', safe='')}"
    return (f"<script>gtag('event','page_view',{{ 'event_origin': '{origin}', 'ticket_tagging': 'ticketed-external' }});</script>"
            f"<script>clevertap_obj['external_ticket_url'] = \"{wrapped.replace('/', chr(92) + '/')}\";</script>{extra}")


class TicketLinkTests(unittest.TestCase):
    def test_affiliate_wrapper_is_unwrapped_and_eventbrite_url_normalised(self):
        origin, url = scrapers._allevents_ticket_link(_page(EB + "/"))
        self.assertEqual((origin, url), ("eventbrite", EB))

    def test_other_sellers_keep_their_path_but_lose_tracking(self):
        _o, url = scrapers._allevents_ticket_link(_page("https://posh.vip/e/some-party", origin="46"))
        self.assertEqual(url, "https://posh.vip/e/some-party")

    def test_facebook_and_allevents_pages_do_not_count(self):
        for seller in ("https://www.facebook.com/events/123", "https://allevents.in/x/1"):
            self.assertEqual(scrapers._allevents_ticket_link(_page(seller))[1], None, seller)

    def test_resale_marketplaces_are_used_directly_without_tracking_when_nothing_better(self):
        _o, url = scrapers._allevents_ticket_link(_page("https://www.vividseats.com/charles-lloyd-quartet-tickets/production/1?utm_campaign=x", origin="46"))
        self.assertEqual(url, "https://www.vividseats.com/charles-lloyd-quartet-tickets/production/1")
        _o, url = scrapers._allevents_ticket_link(_page("https://www.ticketnetwork.com/tickets/8188984", origin="46"))
        self.assertEqual(url, "https://www.ticketnetwork.com/tickets/8188984")

    def test_any_primary_seller_outranks_resale_and_eventbrite_outranks_both(self):
        resale = quote("https://www.vividseats.com/x-tickets/production/1", safe="")
        primary = quote("https://posh.vip/e/party", safe="")
        extra = f'<a href="https://x.pxf.io/c?u={resale}">r</a><a href="https://y.pxf.io/c?u={primary}">p</a>'
        self.assertEqual(scrapers._allevents_ticket_link(_page("https://www.stubhub.com/e/9", extra=extra))[1], "https://posh.vip/e/party")
        self.assertEqual(scrapers._allevents_ticket_link(_page(EB, extra=extra))[1], EB)

    def test_eventbrite_is_preferred_over_another_candidate(self):
        other = quote("https://posh.vip/e/other", safe="")
        extra = f'<a href="https://x.pxf.io/c?u={other}">t</a>'
        self.assertEqual(scrapers._allevents_ticket_link(_page(EB, extra=extra))[1], EB)

    def test_page_without_a_ticket_link(self):
        self.assertEqual(scrapers._allevents_ticket_link("<script>{ 'event_origin': 'eventbrite' }</script>"), ("eventbrite", None))


def _ev(url, days=2, price=None):
    when = (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()
    return {"name": "Party", "date": when, "url": url, "venue": "Club", "price": price}


class ResolveTests(unittest.TestCase):
    def _run(self, results, pages, details=None, **kw):
        asked, checked = [], []

        def fetch(url):
            asked.append(url)
            return pages[url]

        def eb(event_id, ua):
            checked.append(event_id)
            return (details or {}).get(event_id, {"price": None, "sold_out": False, "status": "live"})
        with tempfile.TemporaryDirectory() as tmp:
            args = dict(links_path=os.path.join(tmp, "l.json"), details_path=os.path.join(tmp, "d.json"), fetch=fetch, details=eb)
            n = scrapers._resolve_allevents_links(results, **args, **kw)
            again = []
            scrapers._resolve_allevents_links(results, **{**args, "fetch": lambda u: again.append(u) or pages[u]}, **kw)
        return n, asked, checked, again

    def test_relinks_prices_and_flags_sold_out(self):
        a = _ev("https://allevents.in/brooklyn/party/1", price="$20")
        results = [{"venue": "AllEvents: Brooklyn (all)", "events": [a]}]
        details = {"2004496419751": {"price": "$28.52 - $71.21", "sold_out": True, "status": "live"}}
        n, asked, checked, again = self._run(results, {a["url"]: _page(EB)}, details)
        self.assertEqual(n, 1)
        self.assertEqual(a["url"], EB)
        self.assertEqual(a["_allevents_url"], "https://allevents.in/brooklyn/party/1")
        self.assertEqual((a["price"], a["sold_out"]), ("$28.52 - $71.21", True))
        self.assertEqual(checked, ["2004496419751"])
        self.assertEqual(again, [])  # the AllEvents page was cached, not read twice

    def test_unresolved_pages_and_other_sources_are_untouched(self):
        a = _ev("https://allevents.in/queens/x/2")
        b = _ev("https://allevents.in/queens/y/3")
        results = [{"venue": "AllEvents: Queens (all)", "events": [a]}, {"venue": "Elsewhere", "events": [b]}]
        n, asked, _checked, _again = self._run(results, {a["url"]: "<script>{ 'event_origin': 'eventbrite' }</script>"})
        self.assertEqual(n, 0)
        self.assertEqual(a["url"], "https://allevents.in/queens/x/2")
        self.assertEqual(asked, [a["url"]])  # the other source's listing was never fetched

    def test_non_eventbrite_sellers_relink_without_eventbrite_calls(self):
        a = _ev("https://allevents.in/new-york/p/4")
        n, _asked, checked, _again = self._run([{"venue": "AllEvents: New York (all)", "events": [a]}],
                                               {a["url"]: _page("https://posh.vip/e/party", origin="46")})
        self.assertEqual((n, a["url"], checked), (1, "https://posh.vip/e/party", []))

    def test_budgets_and_cancelled_events(self):
        events = [_ev(f"https://allevents.in/b/{i}", days=2 + i) for i in range(4)]
        pages = {e["url"]: _page(f"https://www.eventbrite.com/e/p-tickets-{2004496419751 + i}") for i, e in enumerate(events)}
        details = {str(2004496419751): {"price": "$5", "sold_out": False, "status": "canceled"}}
        originals = [e["url"] for e in events]  # relinking rewrites the listings in place
        n, asked, checked, again = self._run([{"venue": "AllEvents: Brooklyn (all)", "events": events}], pages, details, page_limit=3, detail_limit=2)
        self.assertEqual(asked, originals[:3])  # soonest first, 3 pages
        self.assertEqual(again, originals[3:])  # the rest next run
        self.assertEqual(len(checked), 3)  # two on the first run (budget), the third on the next
        self.assertIsNone(events[0].get("price"))  # cancelled: relinked, but its details aren't applied


if __name__ == "__main__":
    unittest.main()
