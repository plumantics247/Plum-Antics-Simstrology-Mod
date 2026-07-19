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


DEFAULT_PROFILE_ID = "balanced"


def _import_settings_module():
    candidates = (
        "plumantics_big3_runtime.chemistry_settings",
        "cosmic_engine.chemistry_settings",
    )
    for module_name in candidates:
        try:
            return importlib.import_module(module_name)
        except ModuleNotFoundError as exc:
            if exc.name != module_name:
                raise
            continue
    return None


def _merge_payload(payload):
    module = _import_settings_module()
    if module is None:
        raise AssertionError(
            "Expected a chemistry settings module with save-wide profile payload helpers."
        )
    resolver = getattr(module, "merge_chemistry_profile_payload", None)
    if resolver is None:
        resolver = getattr(module, "resolve_chemistry_profile_payload", None)
    if not callable(resolver):
        raise AssertionError(
            "Expected chemistry settings helper "
            "'merge_chemistry_profile_payload(payload)' or "
            "'resolve_chemistry_profile_payload(payload)'."
        )
    resolved = resolver(payload)
    if not isinstance(resolved, dict):
        raise AssertionError("Chemistry profile resolver must return a dict payload.")
    return resolved


def _resolved_profile_id(payload):
    nested = payload.get("chemistry_profile")
    if isinstance(nested, dict):
        for key in ("profile_id", "profile", "selected_profile"):
            value = nested.get(key)
            if isinstance(value, str) and value:
                return value
    for key in ("profile_id", "profile", "selected_profile"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    raise AssertionError("Resolved chemistry payload must expose the selected profile id.")


class ChemistrySettingsTests(unittest.TestCase):
    def test_merging_profile_preserves_existing_transit_payload_data(self):
        transit_slots = {
            "slot_alpha": {
                "transit_record": {
                    "sign_index_by_body": {"Sun": 4, "Moon": 7},
                    "total_days_elapsed": 123,
                }
            }
        }
        original_payload = {
            "version": 1,
            "slots": copy.deepcopy(transit_slots),
            "chemistry_profile": {"profile_id": "dramatic"},
        }

        resolved = _merge_payload(copy.deepcopy(original_payload))

        self.assertEqual("dramatic", _resolved_profile_id(resolved))
        self.assertEqual(transit_slots, resolved.get("slots"))
        self.assertEqual(1, resolved.get("version"))

    def test_invalid_profile_falls_back_to_default_without_dropping_save_payload(self):
        original_payload = {
            "version": 1,
            "slots": {
                "slot_beta": {
                    "transit_record": {
                        "sign_index_by_body": {"Venus": 2},
                    }
                }
            },
            "chemistry_profile": {"profile_id": "chaotic"},
        }

        resolved = _merge_payload(copy.deepcopy(original_payload))

        self.assertEqual(DEFAULT_PROFILE_ID, _resolved_profile_id(resolved))
        self.assertEqual(original_payload["slots"], resolved.get("slots"))

    def test_valid_requested_profile_survives_merge(self):
        original_payload = {
            "version": 1,
            "slots": {
                "slot_gamma": {
                    "transit_record": {
                        "sign_index_by_body": {"Mars": 10},
                    }
                }
            },
            "chemistry_profile": {"profile_id": "subtle"},
        }

        resolved = _merge_payload(copy.deepcopy(original_payload))

        self.assertEqual("subtle", _resolved_profile_id(resolved))
        self.assertEqual(original_payload["slots"], resolved.get("slots"))


if __name__ == "__main__":
    unittest.main()
