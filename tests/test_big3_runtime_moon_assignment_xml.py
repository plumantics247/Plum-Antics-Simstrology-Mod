import json
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "python" / "plumantics_big3_runtime" / "data" / "universe.config.json"
MOON_LUNAR_PHASE_ID = 13736671501533187751
MOON_RANDOM_ID = 13736671501533187752


class MoonRuntimeAssignmentXmlTests(unittest.TestCase):
    def test_moon_config_uses_python_loot_ids(self):
        payload = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        self.assertEqual(
            MOON_LUNAR_PHASE_ID,
            payload["v2"]["assignment"]["loot_ids"]["moon_lunar_phase"],
        )
        self.assertEqual(
            MOON_RANDOM_ID,
            payload["v2"]["assignment"]["loot_ids"]["moon_random"],
        )

    def test_on_instance_and_moon_by_sun_use_python_lunar_phase_loot(self):
        paths = (
            ROOT / "src" / "core" / "Action" / "PlumAntics_Big3ModCore_OnInstanceMoonLoot.xml",
            ROOT / "src" / "core" / "Interaction" / "PlumAntics_Big3ModCore_Moon_bySun.xml",
        )
        for path in paths:
            text = path.read_text(encoding="utf-8")
            self.assertIn(str(MOON_LUNAR_PHASE_ID), text, path.name)
            self.assertNotIn("12958710299405513646", text, path.name)

    def test_python_moon_loot_shells_exist(self):
        lunar_text = (
            ROOT
            / "src"
            / "core"
            / "Action"
            / "PlumAntics_Big3ModCore_AssignMoonLunarPhasePythonLoot.xml"
        ).read_text(encoding="utf-8")
        random_text = (
            ROOT
            / "src"
            / "core"
            / "Action"
            / "PlumAntics_Big3ModCore_AssignMoonRandomPythonLoot.xml"
        ).read_text(encoding="utf-8")
        self.assertIn("Big3AssignMoonLunarPhasePythonLoot", lunar_text)
        self.assertIn("Big3AssignMoonRandomPythonLoot", random_text)

    def test_signal_mapping_uses_python_lunar_phase_loot(self):
        text = (
            ROOT
            / "python"
            / "plumantics_big3_runtime"
            / "data"
            / "rules"
            / "v2"
            / "signals_to_loots.yaml"
        ).read_text(encoding="utf-8")
        self.assertIn(f"loot_id: {MOON_LUNAR_PHASE_ID}", text)
        self.assertNotIn("loot_id: 12958710299405513646", text)


if __name__ == "__main__":
    unittest.main()
