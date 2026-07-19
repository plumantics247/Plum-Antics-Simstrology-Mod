import importlib
import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
PYTHON_DIR = ROOT / "python"
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))


relbits = importlib.import_module("cosmic_engine.sign_compatibility_relbits")


class SignCompatibilityRelbitsTests(unittest.TestCase):
    def test_lane_state_resolution_uses_same_element_as_compatible(self):
        self.assertEqual("Compatible", relbits.resolve_lane_state(0, 4))
        self.assertEqual("Compatible", relbits.resolve_lane_state(3, 11))

    def test_lane_state_resolution_uses_opposing_element_as_incompatible(self):
        self.assertEqual("Incompatible", relbits.resolve_lane_state(0, 3))
        self.assertEqual("Incompatible", relbits.resolve_lane_state(10, 1))

    def test_lane_state_resolution_uses_remaining_pairs_as_neutral(self):
        self.assertEqual("Neutral", relbits.resolve_lane_state(0, 2))
        self.assertEqual("Neutral", relbits.resolve_lane_state(9, 11))

    def test_build_pair_plan_seeds_only_valid_lanes(self):
        plan = relbits.build_pair_relbit_seed_plan(
            actor_chart={"sun_sign_index": 0, "moon_sign_index": 4},
            target_chart={"sun_sign_index": 8, "moon_sign_index": 3, "rising_sign_index": 11},
        )
        self.assertTrue(plan["ok"])
        self.assertEqual(("Moon", "Sun"), tuple(sorted(plan["lanes"].keys())))
        self.assertEqual("Compatible", plan["lanes"]["Sun"]["state"])
        self.assertEqual("Incompatible", plan["lanes"]["Moon"]["state"])

    def test_changed_lane_names_detects_only_lane_specific_signature_changes(self):
        changed = relbits.changed_lane_names(
            {"Sun": 0, "Moon": 4, "Rising": 8},
            {"Sun": 0, "Moon": 11, "Rising": 8},
        )
        self.assertEqual(("Moon",), changed)


if __name__ == "__main__":
    unittest.main()
