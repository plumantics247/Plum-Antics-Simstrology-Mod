import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
PYTHON_DIR = ROOT / "python"
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))


from cosmic_engine import outer_planets_activation
from cosmic_engine.houses_notification_bridge import build_houses_readout_payload
from cosmic_engine.transit_service import CosmicTransitService


class OuterPlanetsReadoutTests(unittest.TestCase):
    def tearDown(self):
        outer_planets_activation.clear_outer_planets_activation_override()

    def _service(self, active):
        outer_planets_activation.set_outer_planets_activation_override(active)
        service = CosmicTransitService()
        service.initialize(seed=222)
        service.state.sign_index_by_body["Chiron"] = 1
        service.state.sign_index_by_body["Uranus"] = 2
        service.state.sign_index_by_body["Neptune"] = 3
        service.state.sign_index_by_body["Pluto"] = 10
        return service

    def test_houses_readout_omits_outer_weather_lines_when_addon_is_inactive(self):
        payload = build_houses_readout_payload(
            self._service(False),
            actor_trait_ids=[10264073582958847151],
            actor_marker_trait_ids=None,
        )

        self.assertTrue(payload["ok"])
        self.assertFalse(payload["outer_planets_active"])
        self.assertEqual([], payload["outer_weather_lines"])
        self.assertTrue(all("Pluto" not in line for line in payload["body_lines"]))

    def test_houses_readout_includes_outer_weather_lines_when_addon_is_active(self):
        payload = build_houses_readout_payload(
            self._service(True),
            actor_trait_ids=[10264073582958847151],
            actor_marker_trait_ids=None,
        )

        self.assertTrue(payload["outer_planets_active"])
        self.assertEqual(
            [
                "Chiron is in Taurus.",
                "Uranus is in Gemini.",
                "Neptune is in Cancer.",
                "Pluto is in Aquarius.",
            ],
            payload["outer_weather_lines"],
        )

    def test_active_transit_weather_body_names_expand_only_when_addon_is_active(self):
        import cosmic_engine.loot_actions as loot_actions

        outer_planets_activation.set_outer_planets_activation_override(False)
        inactive_names = loot_actions._active_transit_weather_body_names(self._service(False))
        self.assertEqual(("Moon", "Mercury", "Sun", "Venus", "Mars", "Jupiter", "Saturn"), inactive_names)

        outer_planets_activation.set_outer_planets_activation_override(True)
        active_names = loot_actions._active_transit_weather_body_names(self._service(True))
        self.assertIn("Pluto", active_names)
        self.assertIn("Chiron", active_names)

    def test_transit_pretty_payload_omits_outer_bodies_when_addon_is_inactive(self):
        import cosmic_engine.loot_actions as loot_actions

        payload = loot_actions.build_transit_pretty_payload(service=self._service(False))

        self.assertTrue(payload["ok"])
        self.assertTrue(any(line.startswith("Saturn:") for line in payload["lines"]))
        self.assertFalse(any(line.startswith("Uranus:") for line in payload["lines"]))
        self.assertTrue(payload["lines"][-2].startswith("DayProgress:"))
        self.assertTrue(payload["lines"][-1].startswith("SegmentRemainders:"))

    def test_transit_pretty_payload_appends_outer_bodies_when_addon_is_active(self):
        import cosmic_engine.loot_actions as loot_actions

        payload = loot_actions.build_transit_pretty_payload(service=self._service(True))
        joined = "\n".join(payload["lines"])

        self.assertLess(joined.index("Saturn:"), joined.index("Uranus:"))
        self.assertLess(joined.index("Uranus:"), joined.index("Neptune:"))
        self.assertLess(joined.index("Neptune:"), joined.index("Pluto:"))
        self.assertLess(joined.index("Pluto:"), joined.index("Chiron:"))
        self.assertTrue(payload["lines"][-2].startswith("DayProgress:"))
        self.assertTrue(payload["lines"][-1].startswith("SegmentRemainders:"))

    def test_transit_pretty_payload_skips_missing_outer_body_cleanly(self):
        import cosmic_engine.loot_actions as loot_actions

        service = self._service(True)
        del service.state.sign_index_by_body["Chiron"]

        payload = loot_actions.build_transit_pretty_payload(service=service)

        self.assertTrue(payload["ok"])
        self.assertTrue(any(line.startswith("Pluto:") for line in payload["lines"]))
        self.assertFalse(any(line.startswith("Chiron:") for line in payload["lines"]))


if __name__ == "__main__":
    unittest.main()
