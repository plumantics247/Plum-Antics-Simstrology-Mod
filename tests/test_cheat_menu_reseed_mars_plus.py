import pathlib
import unittest
import xml.etree.ElementTree as ET


ROOT = pathlib.Path(__file__).resolve().parents[1]
INTERACTION_PATH = (
    ROOT
    / "src"
    / "core"
    / "Interaction"
    / "PlumAntics_CosmicEngineCore_CheatReseedMarsPlus.xml"
)
ACTION_PATH = (
    ROOT
    / "src"
    / "core"
    / "Action"
    / "PlumAntics_CosmicEngineCore_ReseedMarsPlusPythonLoot.xml"
)
INJECTOR_PATH = ROOT / "src" / "core" / "Snippet" / "PlumAntics_CosmicEngineCore_TuningInjector.xml"

RESEED_INTERACTION_ID = "830000000000009136"
RESEED_LOOT_ID = "830000000000009137"
ROOT_CHEAT_CATEGORY_ID = "17585182514099890486"


class CheatMenuReseedMarsPlusTests(unittest.TestCase):
    def test_reseed_interaction_uses_root_cheat_menu_shell(self):
        root = ET.parse(INTERACTION_PATH).getroot()

        self.assertEqual(RESEED_INTERACTION_ID, root.attrib["s"])
        self.assertEqual("SuperInteraction", root.attrib["c"])
        self.assertEqual("interactions.base.super_interaction", root.attrib["m"])
        self.assertEqual(ROOT_CHEAT_CATEGORY_ID, root.findtext("T[@n='category']"))
        self.assertEqual("True", root.findtext("T[@n='cheat']"))
        self.assertEqual(RESEED_LOOT_ID, root.find("L[@n='basic_extras']//T").text)

    def test_reseed_loot_uses_cosmic_python_bridge(self):
        root = ET.parse(ACTION_PATH).getroot()

        self.assertEqual(RESEED_LOOT_ID, root.attrib["s"])
        self.assertEqual("CosmicEngineReseedMarsPlusLoot", root.attrib["c"])
        self.assertEqual("cosmic_engine.loot_actions", root.attrib["m"])

    def test_reseed_interaction_is_available_only_through_the_hub(self):
        root = ET.parse(INJECTOR_PATH).getroot()
        affordance_ids = [
            tuning.text
            for tuning in root.findall(".//L[@n='affordances']/T")
            if tuning.text is not None
        ]
        self.assertNotIn(RESEED_INTERACTION_ID, affordance_ids)
        self.assertIn("830000000000009139", affordance_ids)


if __name__ == "__main__":
    unittest.main()
