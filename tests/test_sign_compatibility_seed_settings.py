import copy
import importlib
import pathlib
import sys
import unittest


sys.dont_write_bytecode = True

ROOT = pathlib.Path(__file__).resolve().parents[1]
PYTHON_DIR = ROOT / "python"
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))


def _import_module():
    candidates = (
        "plumantics_big3_runtime.sign_compatibility_seed_settings",
        "cosmic_engine.sign_compatibility_seed_settings",
    )
    for module_name in candidates:
        try:
            return importlib.import_module(module_name)
        except ModuleNotFoundError as exc:
            if exc.name != module_name:
                raise
            continue
    raise AssertionError("Expected sign_compatibility_seed_settings module.")


class SignCompatibilitySeedSettingsTests(unittest.TestCase):
    def test_merge_preserves_existing_slots_and_other_profiles(self):
        module = _import_module()
        payload = {
            "version": 1,
            "slots": {"slot_alpha": {"transit_record": {"sun_sign_index": 4}}},
            "chemistry_profile": {"profile_id": "dramatic"},
        }

        merged = module.merge_sign_compatibility_seed_payload(
            copy.deepcopy(payload),
            sim_id=12345,
            seed_record={
                "sun_sign_index": 0,
                "moon_sign_index": 4,
                "rising_sign_index": 8,
            },
        )

        nested = merged["sign_compatibility_seed_profile"]["sim_profiles"]
        self.assertEqual(payload["slots"], merged["slots"])
        self.assertEqual(payload["chemistry_profile"], merged["chemistry_profile"])
        self.assertEqual(0, nested["12345"]["sun_sign_index"])

    def test_read_returns_empty_profile_when_missing(self):
        module = _import_module()
        resolved = module.read_sign_compatibility_seed_payload({})
        self.assertEqual({}, resolved.get("sim_profiles"))

    def test_remove_sim_seed_drops_only_requested_sim_entry(self):
        module = _import_module()
        payload = {
            "sign_compatibility_seed_profile": {
                "sim_profiles": {
                    "12345": {"chart_signature": "0:4:8"},
                    "67890": {"chart_signature": "1:5:9"},
                }
            }
        }
        merged = module.remove_sign_compatibility_seed_payload_for_sim(
            payload, 12345
        )
        profiles = merged["sign_compatibility_seed_profile"]["sim_profiles"]
        self.assertNotIn("12345", profiles)
        self.assertIn("67890", profiles)

    def test_merge_preserves_list_based_lane_default_sets(self):
        module = _import_module()
        seed_record = {
            "seed_version": 4,
            "chart_signature": "0:4:8",
            "lanes": {
                "Sun": {
                    "seed_sign_index": 0,
                    "auto_like_sign_indexes": (0, 4, 8),
                    "auto_dislike_sign_indexes": (3, 7, 11),
                    "auto_like_trait_ids": (4100020001, 4100020005, 4100020009),
                    "auto_dislike_trait_ids": (4100030004, 4100030008, 4100030012),
                    "ea_like_trait_id": 305964,
                    "ea_dislike_trait_id": 306407,
                }
            },
        }

        merged = module.merge_sign_compatibility_seed_payload({}, sim_id=12345, seed_record=seed_record)

        stored = merged["sign_compatibility_seed_profile"]["sim_profiles"]["12345"]
        self.assertEqual(4, stored["seed_version"])
        self.assertEqual((0, 4, 8), tuple(stored["lanes"]["Sun"]["auto_like_sign_indexes"]))
        self.assertEqual((3, 7, 11), tuple(stored["lanes"]["Sun"]["auto_dislike_sign_indexes"]))
        self.assertEqual(
            (4100020001, 4100020005, 4100020009),
            tuple(stored["lanes"]["Sun"]["auto_like_trait_ids"]),
        )
        self.assertEqual(
            (4100030004, 4100030008, 4100030012),
            tuple(stored["lanes"]["Sun"]["auto_dislike_trait_ids"]),
        )
        self.assertEqual(305964, stored["lanes"]["Sun"]["ea_like_trait_id"])


if __name__ == "__main__":
    unittest.main()
