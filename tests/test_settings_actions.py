import pathlib
import sys
import unittest
import xml.etree.ElementTree as ET


ROOT = pathlib.Path(__file__).resolve().parents[1]
PYTHON_DIR = ROOT / "python"
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))

CORE_INTERACTION_DIR = ROOT / "src" / "core" / "Interaction"
COMPAT_INTERACTION_DIR = ROOT / "src" / "SignCompatibility" / "Interaction"
CORE_ACTION_DIR = ROOT / "src" / "core" / "Action"
COMPAT_ACTION_DIR = ROOT / "src" / "SignCompatibility" / "Action"


def _continuation_affordances(xml_path):
    root = ET.parse(xml_path).getroot()
    return [int(node.text) for node in root.findall(".//L[@n='continuation']/U/T[@n='affordance']")]


def _outcome_loot_ids(xml_path):
    root = ET.parse(xml_path).getroot()
    return [int(node.text) for node in root.findall(".//U[@n='actions']/L[@n='loot_list']/T")]


def _profile_id(xml_path):
    root = ET.parse(xml_path).getroot()
    return root.findtext("T[@n='profile_id']")


class _MemoryPayloadStore(object):
    def __init__(self, payload):
        self.payload = dict(payload)

    def read(self):
        return dict(self.payload)

    def write(self, payload):
        self.payload = dict(payload)
        return True


class SettingsActionTests(unittest.TestCase):
    def test_root_and_section_launchers_route_to_expected_affordances(self):
        root_affordances = _continuation_affordances(
            CORE_INTERACTION_DIR / "PlumAntics_CosmicEngineCore_SettingsLauncher.xml"
        )
        compatibility_affordances = _continuation_affordances(
            COMPAT_INTERACTION_DIR / "PlumAntics_CosmicEngineCore_SettingsLauncher_Compatibility.xml"
        )
        retrograde_affordances = _continuation_affordances(
            CORE_INTERACTION_DIR / "PlumAntics_CosmicEngineCore_SettingsLauncher_Retrogrades.xml"
        )

        self.assertEqual(
            [830000000000009133, 830000000000009134, 830000000000009139],
            root_affordances,
        )
        self.assertEqual(
            [
                830000000000009139,
                830000000000009122,
                830000000000009121,
                830000000000009123,
            ],
            compatibility_affordances,
        )
        self.assertEqual(
            [
                830000000000009139,
                830000000000009126,
                830000000000009127,
            ],
            retrograde_affordances,
        )

    def test_setting_interactions_route_to_expected_loot_actions(self):
        self.assertEqual(
            [830000000000009118],
            _outcome_loot_ids(
                COMPAT_INTERACTION_DIR / "PlumAntics_CosmicEngineCore_SetChemistryIntensityBalanced.xml"
            ),
        )
        self.assertEqual(
            [830000000000009117],
            _outcome_loot_ids(
                COMPAT_INTERACTION_DIR / "PlumAntics_CosmicEngineCore_SetChemistryIntensitySubtle.xml"
            ),
        )
        self.assertEqual(
            [830000000000009119],
            _outcome_loot_ids(
                COMPAT_INTERACTION_DIR / "PlumAntics_CosmicEngineCore_SetChemistryIntensityDramatic.xml"
            ),
        )
        self.assertEqual(
            [830000000000009128],
            _outcome_loot_ids(
                CORE_INTERACTION_DIR / "PlumAntics_CosmicEngineCore_SetRetrogradeVisibilityRecommended.xml"
            ),
        )
        self.assertEqual(
            [830000000000009129],
            _outcome_loot_ids(
                CORE_INTERACTION_DIR / "PlumAntics_CosmicEngineCore_SetRetrogradeVisibilityUncapped.xml"
            ),
        )

    def test_action_tuning_profile_ids_match_expected_values(self):
        self.assertEqual(
            "balanced",
            _profile_id(COMPAT_ACTION_DIR / "PlumAntics_CosmicEngineCore_SetChemistryProfileBalanced.xml"),
        )
        self.assertEqual(
            "subtle",
            _profile_id(COMPAT_ACTION_DIR / "PlumAntics_CosmicEngineCore_SetChemistryProfileSubtle.xml"),
        )
        self.assertEqual(
            "dramatic",
            _profile_id(COMPAT_ACTION_DIR / "PlumAntics_CosmicEngineCore_SetChemistryProfileDramatic.xml"),
        )
        self.assertEqual(
            "recommended",
            _profile_id(
                CORE_ACTION_DIR / "PlumAntics_CosmicEngineCore_SetRetrogradeVisibilityProfileRecommended.xml"
            ),
        )
        self.assertEqual(
            "uncapped",
            _profile_id(
                CORE_ACTION_DIR / "PlumAntics_CosmicEngineCore_SetRetrogradeVisibilityProfileUncapped.xml"
            ),
        )

    def test_persistence_adapter_persists_profiles_without_dropping_transit_slots(self):
        from cosmic_engine.persistence_adapter import TransitPersistenceAdapter

        original_payload = {
            "version": 1,
            "slots": {
                "slot_alpha": {
                    "transit_record": {
                        "sign_index_by_body": {"Sun": 4, "Moon": 7},
                        "total_days_elapsed": 123,
                    }
                }
            },
        }
        store = _MemoryPayloadStore(original_payload)

        adapter = TransitPersistenceAdapter(
            read_in_save_payload=store.read,
            write_in_save_payload=store.write,
            resolve_save_slot_key=lambda: "slot_alpha",
            on_pre_save=lambda: {},
            log_warn_once=lambda *args, **kwargs: None,
            log_exception=lambda *args, **kwargs: None,
            log_debug=lambda *args, **kwargs: None,
        )

        self.assertTrue(adapter.persist_chemistry_profile("dramatic", reason="test"))
        chemistry_payload = store.read()
        self.assertEqual(
            {"profile_id": "dramatic"},
            chemistry_payload.get("chemistry_profile"),
        )
        self.assertEqual(original_payload["slots"], chemistry_payload.get("slots"))

        self.assertTrue(adapter.persist_retrograde_visibility_profile("uncapped", reason="test"))
        retro_payload = store.read()
        self.assertEqual(
            {"profile_id": "uncapped"},
            retro_payload.get("retrograde_visibility"),
        )
        self.assertEqual({"profile_id": "dramatic"}, retro_payload.get("chemistry_profile"))
        self.assertEqual(original_payload["slots"], retro_payload.get("slots"))


if __name__ == "__main__":
    unittest.main()
