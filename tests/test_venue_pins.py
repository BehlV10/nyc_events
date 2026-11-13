import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import venues_geo  # noqa: E402
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import geocode_venues as gv  # noqa: E402


class PinnedVenueTests(unittest.TestCase):
    def test_pinned_name_resolves_before_other_rules(self):
        venues_geo.VENUE_PINS["pinned test hall"] = (40.7, -73.95, "Williamsburg", "1 Main St", "Pinned Test Hall")
        try:
            g = venues_geo.resolve_event_geo({"venue": "Pinned Test Hall"})
        finally:
            del venues_geo.VENUE_PINS["pinned test hall"]
        self.assertEqual((g["lat"], g["lng"], g["venue"]), (40.7, -73.95, "Pinned Test Hall"))

    def test_name_match_is_strict(self):
        self.assertTrue(gv.name_matches("Hack Manhattan (, New York, NY)", "Hack Manhattan"))
        self.assertFalse(gv.name_matches("Lower East Side", "LOWER EAST SIDE 1 HOUSES"))
        self.assertFalse(gv.name_matches("Open Air Club", "SI ZOO OPEN AIR PAVILION"))
        self.assertFalse(gv.name_matches("Chinatown", "Chinatown"))  # a bare neighbourhood is not a venue

    def test_candidates_skip_neighbourhoods_and_outside_towns(self):
        self.assertTrue(gv._not_a_venue("Chinatown (, New York, NY)"))
        self.assertTrue(gv._not_a_venue("St Lukes Episcopal Church (253 Glen Ave, Sea Cliff, NY)"))
        self.assertFalse(gv._not_a_venue("Soapbox Gallery"))
        self.assertFalse(gv._not_a_venue("Ballet Academy East (BAE)"))


if __name__ == "__main__":
    unittest.main()
