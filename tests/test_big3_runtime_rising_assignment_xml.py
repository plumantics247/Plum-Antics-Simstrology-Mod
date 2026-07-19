import json
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "python" / "plumantics_big3_runtime" / "data" / "universe.config.json"


class RisingRuntimeAssignmentXmlTests(unittest.TestCase):
    def test_rising_sun_time_config_uses_python_loot_id(self):
        payload = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        self.assertEqual(
            13736671501533187750,
            payload["v2"]["assignment"]["loot_ids"]["rising_sun_time"],
        )

    def test_on_instance_and_risingbyseason_use_python_loot(self):
        paths = (
            ROOT / "src" / "core" / "Action" / "PlumAntics_Big3ModCore_OnInstanceRisingLoot.xml",
            ROOT / "src" / "core" / "Interaction" / "PlumAntics_Big3ModCore_RisingbySeason.xml",
            ROOT / "src" / "core" / "Interaction" / "PlumAntics_CosmicEngineCore_RisingbySeason.xml",
            ROOT / "src" / "core" / "Interaction" / "PlumAntics_CosmicEngineCore_RisingbySeasonComputer.xml",
        )
        for path in paths:
            text = path.read_text(encoding="utf-8")
            self.assertIn("13736671501533187750", text, path.name)
            self.assertNotIn("1497322224<!--PlumAntics_Big3Mod_RisingPhaseTestAll-->", text, path.name)
            self.assertNotIn("7190085866707849644<!--PlumAntics_CosmicEngineCore_RisingPhaseTestAll-->", text, path.name)

    def test_rising_random_config_uses_python_loot_id(self):
        payload = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        self.assertEqual(
            13736671501533187753,
            payload["v2"]["assignment"]["loot_ids"]["rising_random"],
        )

    def test_cosmic_rising_random_callers_use_python_loot(self):
        paths = (
            ROOT / "src" / "core" / "Interaction" / "PlumAntics_CosmicEngineCore_Rising_Random.xml",
            ROOT / "src" / "core" / "Interaction" / "PlumAntics_CosmicEngineCore_Rising_RandomComputer.xml",
        )
        for path in paths:
            text = path.read_text(encoding="utf-8")
            self.assertIn("13736671501533187753", text, path.name)
            self.assertNotIn("8338455827166060778", text, path.name)

    def test_rising_random_python_loot_shell_exists(self):
        path = ROOT / "src" / "core" / "Action" / "PlumAntics_Big3ModCore_AssignRisingRandomPythonLoot.xml"
        text = path.read_text(encoding="utf-8")
        self.assertIn('c="Big3AssignRisingRandomPythonLoot"', text)
        self.assertIn('m="plumantics_big3_runtime.loot_actions"', text)
        self.assertIn('s="13736671501533187753"', text)

    def test_first_load_chooser_uses_python_random_rising_loot(self):
        text = (
            ROOT
            / "python"
            / "cosmic_engine"
            / "first_load_chooser.py"
        ).read_text(encoding="utf-8")
        self.assertIn("_COSMIC_RANDOM_RISING_LOOT_ID = 13736671501533187753", text)
        self.assertNotIn("_COSMIC_RANDOM_RISING_LOOT_ID = 8338455827166060778", text)


if __name__ == "__main__":
    unittest.main()
