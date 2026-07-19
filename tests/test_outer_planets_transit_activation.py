import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
PYTHON_DIR = ROOT / "python"
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))


from cosmic_engine import outer_planets_activation
from cosmic_engine.transit_core import (
    ALL_BODY_NAMES,
    OPTIONAL_OUTER_BODY_NAMES,
    RULE_BY_BODY,
    TransitState,
    resolve_active_body_names,
    state_from_payload,
    state_to_payload,
)
from cosmic_engine.transit_service import CosmicTransitService


class OuterPlanetsTransitActivationTests(unittest.TestCase):
    def tearDown(self):
        outer_planets_activation.clear_outer_planets_activation_override()

    def test_resolve_active_body_names_omits_outer_bodies_when_layer_is_inactive(self):
        outer_planets_activation.set_outer_planets_activation_override(False)

        active = resolve_active_body_names(
            include_outer=outer_planets_activation.is_outer_planets_addon_active()
        )

        self.assertEqual(("Moon", "Mercury", "Sun", "Venus", "Mars", "Jupiter", "Saturn"), active)
        for body in OPTIONAL_OUTER_BODY_NAMES:
            self.assertNotIn(body, active)

    def test_transit_state_roundtrip_preserves_outer_body_slots(self):
        payload = {
            "sign_index_by_body": {"Sun": 4, "Moon": 7, "Chiron": 2, "Pluto": 11},
            "day_progress_by_body": {"Moon": 1, "Mercury": 0},
            "segment_progress_by_body": {"Saturn": 9, "Chiron": 15, "Pluto": 44},
        }

        state = state_from_payload(payload)
        resolved = state_to_payload(state)

        self.assertEqual(2, resolved["sign_index_by_body"]["Chiron"])
        self.assertEqual(11, resolved["sign_index_by_body"]["Pluto"])
        self.assertIn("Uranus", resolved["sign_index_by_body"])
        self.assertIn("Neptune", resolved["sign_index_by_body"])

    def test_build_save_record_preserves_outer_state_even_when_runtime_roster_is_base_only(self):
        outer_planets_activation.set_outer_planets_activation_override(False)
        service = CosmicTransitService()
        service.initialize(seed=321)
        service.state.sign_index_by_body["Chiron"] = 8
        service.state.segment_progress_by_body["Chiron"] = 17

        record = service.build_save_record()

        anchor = record["anchor_state_payload"]["sign_index_by_body"]
        self.assertEqual(8, anchor["Chiron"])
        self.assertFalse(service.outer_planets_active())
        self.assertNotIn("Chiron", service.active_body_names())

    def test_outer_body_speed_order_stays_chiron_then_uranus_then_neptune_then_pluto(self):
        state = TransitState(
            sign_index_by_body={body: 0 for body in ALL_BODY_NAMES},
            day_progress_by_body={body: 0 for body in ALL_BODY_NAMES},
            segment_progress_by_body={body: 0 for body in ALL_BODY_NAMES},
        )

        chiron_interval = 0
        uranus_interval = 0
        neptune_interval = 0
        pluto_interval = 0
        for step in range(1, 200):
            from cosmic_engine.transit_core import advance_transits

            advance_transits(state, elapsed_segments=1, body_names=OPTIONAL_OUTER_BODY_NAMES)
            if chiron_interval == 0 and state.sign_index_by_body["Chiron"] != 0:
                chiron_interval = step
            if uranus_interval == 0 and state.sign_index_by_body["Uranus"] != 0:
                uranus_interval = step
            if neptune_interval == 0 and state.sign_index_by_body["Neptune"] != 0:
                neptune_interval = step
            if pluto_interval == 0 and state.sign_index_by_body["Pluto"] != 0:
                pluto_interval = step

        self.assertLess(chiron_interval, uranus_interval)
        self.assertLess(uranus_interval, neptune_interval)
        self.assertLess(neptune_interval, pluto_interval)

    def test_core_body_speed_rules_match_updated_timing_canon(self):
        self.assertEqual(1, RULE_BY_BODY["Moon"].interval)
        self.assertEqual(3, RULE_BY_BODY["Mars"].interval)
        self.assertEqual(18, RULE_BY_BODY["Jupiter"].interval)
        self.assertEqual(36, RULE_BY_BODY["Saturn"].interval)
        self.assertEqual(48, RULE_BY_BODY["Chiron"].interval)
        self.assertEqual(84, RULE_BY_BODY["Uranus"].interval)
        self.assertEqual(108, RULE_BY_BODY["Neptune"].interval)
        self.assertEqual(144, RULE_BY_BODY["Pluto"].interval)


if __name__ == "__main__":
    unittest.main()
