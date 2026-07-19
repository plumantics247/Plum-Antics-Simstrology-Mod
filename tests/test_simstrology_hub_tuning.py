import pathlib
import sys
import unittest
import xml.etree.ElementTree as ET


ROOT = pathlib.Path(__file__).resolve().parents[1]
PYTHON_DIR = ROOT / "python"
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))


INTERACTION_DIR = ROOT / "src" / "core" / "Interaction"
INJECTOR_PATH = ROOT / "src" / "core" / "Snippet" / "PlumAntics_CosmicEngineCore_TuningInjector.xml"
BIG3_INJECTOR_PATH = ROOT / "src" / "core" / "Snippet" / "PlumAntics_Big3ModCore_TuningInjector_Mod.xml"
SHARED_INJECTOR_PATH = ROOT / "src" / "core" / "Snippet" / "PlumAntics_SimstrologicalMod_TuningInjector_Shared.xml"
HUB_IDS = {
    "PlumAntics_CosmicEngineCore_SimstrologyHubLauncher.xml": 830000000000009139,
    "PlumAntics_CosmicEngineCore_SimstrologyHubOnboarding.xml": 830000000000009140,
    "PlumAntics_CosmicEngineCore_SimstrologyHubChartSky.xml": 830000000000009141,
    "PlumAntics_CosmicEngineCore_SimstrologyHubCheats.xml": 830000000000009142,
    "PlumAntics_CosmicEngineCore_SimstrologyHubChangeSign.xml": 830000000000009143,
    "PlumAntics_CosmicEngineCore_SimstrologyHubChangeSun.xml": 830000000000009144,
    "PlumAntics_CosmicEngineCore_SimstrologyHubChangeMoon.xml": 830000000000009145,
    "PlumAntics_CosmicEngineCore_SimstrologyHubChangeRising.xml": 830000000000009146,
}


def _continuation_affordances(xml_path):
    root = ET.parse(xml_path).getroot()
    return [int(node.text) for node in root.findall(".//L[@n='continuation']/U/T[@n='affordance']")]


class SimstrologyHubTuningTests(unittest.TestCase):
    def test_hub_launchers_use_the_shared_python_picker_shell(self):
        for filename in HUB_IDS:
            root = ET.parse(INTERACTION_DIR / filename).getroot()
            self.assertEqual("SimstrologyHubPickerInteraction", root.attrib.get("c"))
            self.assertEqual("cosmic_engine.settings_picker", root.attrib.get("m"))
            self.assertEqual("OBJECT", root.findtext("E[@n='target_type']"))
            self.assertIsNotNone(root.find("L[@n='test_globals']"))
            self.assertIsNotNone(root.find("L[@n='choices']"))

    def test_hub_routes_to_existing_chart_settings_and_cheat_backends(self):
        self.assertEqual(
            [830000000000009140, 830000000000009141, 830000000000009132, 830000000000009142],
            _continuation_affordances(
                INTERACTION_DIR / "PlumAntics_CosmicEngineCore_SimstrologyHubLauncher.xml"
            ),
        )
        self.assertEqual(
            [263554064, 383662816, 2587898005, 3464372244, 2755943843567210630, 484998191268879100, 830000000000009139],
            _continuation_affordances(
                INTERACTION_DIR / "PlumAntics_CosmicEngineCore_SimstrologyHubOnboarding.xml"
            ),
        )
        self.assertEqual(
            [4460138363424262887, 9859702918831605378, 830000000000009139],
            _continuation_affordances(
                INTERACTION_DIR / "PlumAntics_CosmicEngineCore_SimstrologyHubChartSky.xml"
            ),
        )
        self.assertEqual(
            [830000000000009143, 830000000000009106, 830000000000009136, 830000000000009109, 12964943365501611110, 830000000000009139],
            _continuation_affordances(
                INTERACTION_DIR / "PlumAntics_CosmicEngineCore_SimstrologyHubCheats.xml"
            ),
        )

    def test_change_a_sign_routes_to_all_existing_sign_cheats(self):
        self.assertEqual(
            [830000000000009144, 830000000000009145, 830000000000009146, 830000000000009139],
            _continuation_affordances(
                INTERACTION_DIR / "PlumAntics_CosmicEngineCore_SimstrologyHubChangeSign.xml"
            ),
        )
        for filename in (
            "PlumAntics_CosmicEngineCore_SimstrologyHubChangeSun.xml",
            "PlumAntics_CosmicEngineCore_SimstrologyHubChangeMoon.xml",
            "PlumAntics_CosmicEngineCore_SimstrologyHubChangeRising.xml",
        ):
            affordances = _continuation_affordances(INTERACTION_DIR / filename)
            self.assertEqual(13, len(affordances))
            self.assertEqual(830000000000009139, affordances[-1])

    def test_every_hub_subcard_has_a_return_to_the_main_hub(self):
        for filename in HUB_IDS:
            if filename.endswith("SimstrologyHubLauncher.xml"):
                continue
            affordances = _continuation_affordances(INTERACTION_DIR / filename)
            self.assertEqual(830000000000009139, affordances[-1], filename)

    def test_hub_launcher_is_injected_onto_sims(self):
        root = ET.parse(INJECTOR_PATH).getroot()
        injected = [int(node.text) for node in root.findall(".//L[@n='affordances']/T")]
        self.assertIn(830000000000009139, injected)

    def test_hub_replaces_the_direct_pie_entries_it_routes(self):
        replaced_ids = {
            263554064,
            383662816,
            3464372244,
            2587898005,
            2755943843567210630,
            484998191268879100,
            830000000000009132,
            12964943365501611110,
            830000000000009106,
            830000000000009136,
            830000000000009109,
            4460138363424262887,
            9859702918831605378,
            2094721282,
        }
        replaced_ids.update(
            int(ET.parse(path).getroot().attrib["s"])
            for path in INTERACTION_DIR.glob("PlumAntics_Big3ModCore_CheatSelect*.xml")
        )
        for path in (INJECTOR_PATH, BIG3_INJECTOR_PATH, SHARED_INJECTOR_PATH):
            root = ET.parse(path).getroot()
            injected_ids = {
                int(node.text)
                for node in root.findall(".//L[@n='affordances']/T")
                if node.text is not None
            }
            self.assertFalse(replaced_ids & injected_ids, path.name)

    def test_hub_picker_subclass_is_importable_outside_game(self):
        from cosmic_engine.settings_picker import SimstrologyHubPickerInteraction

        self.assertTrue(issubclass(SimstrologyHubPickerInteraction, object))


if __name__ == "__main__":
    unittest.main()
