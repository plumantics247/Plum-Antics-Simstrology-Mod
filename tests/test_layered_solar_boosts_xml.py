import json
import pathlib
import unittest
import xml.etree.ElementTree as ET


ROOT = pathlib.Path(__file__).resolve().parents[1]
CORE_BUFF_DIR = ROOT / "src" / "core" / "Buff"
STRING_FILE = ROOT / "src" / "String" / "SimstrologicalMod_English.stbl.json"

MOON_SOLAR_FILE_NAMES = [
    "PlumAntics_Big3ModCore_AriesMoonSolarBuff.xml",
    "PlumAntics_Big3ModCore_TaurusMoonSolarBuff.xml",
    "PlumAntics_Big3ModCore_GeminiMoonSolarBuff.xml",
    "PlumAntics_Big3ModCore_CancerMoonSolarBuff.xml",
    "PlumAntics_Big3ModCore_LeoMoonSolarBuff.xml",
    "PlumAntics_Big3ModCore_VirgoMoonSolarBuff.xml",
    "PlumAntics_Big3ModCore_LibraMoonSolarBuff.xml",
    "PlumAntics_Big3ModCore_ScorpioMoonSolarBuff.xml",
    "PlumAntics_Big3ModCore_SagittariusMoonSolarBuff.xml",
    "PlumAntics_Big3ModCore_CapricornMoonSolarBuff.xml",
    "PlumAntics_Big3ModCore_AquariusMoonSolarBuff.xml",
    "PlumAntics_Big3ModCore_PiscesMoonSolarBuff.xml",
]
ANGULAR_FILE_NAMES = [
    "PlumAntics_Big3ModCore_SolarHouseFirstBuff.xml",
    "PlumAntics_Big3ModCore_SolarHouseFourthBuff.xml",
    "PlumAntics_Big3ModCore_SolarHouseSeventhBuff.xml",
    "PlumAntics_Big3ModCore_SolarHouseTenthBuff.xml",
]
ELEMENT_SUPPORT_FILE_NAMES = [
    "PlumAntics_Big3ModCore_ElementFireSolarSupportBuff.xml",
    "PlumAntics_Big3ModCore_ElementEarthSolarSupportBuff.xml",
    "PlumAntics_Big3ModCore_ElementAirSolarSupportBuff.xml",
    "PlumAntics_Big3ModCore_ElementWaterSolarSupportBuff.xml",
]


class LayeredSolarBoostXmlTests(unittest.TestCase):
    def test_new_moonsolar_angular_and_element_support_files_exist(self):
        for file_name in MOON_SOLAR_FILE_NAMES + ANGULAR_FILE_NAMES + ELEMENT_SUPPORT_FILE_NAMES:
            self.assertTrue((CORE_BUFF_DIR / file_name).exists(), file_name)
            self.assertTrue((CORE_BUFF_DIR / file_name.replace(".xml", ".SimData.xml")).exists(), file_name)

    def test_new_player_facing_buffs_do_not_use_missing_image_icons(self):
        for file_name in MOON_SOLAR_FILE_NAMES + ANGULAR_FILE_NAMES + ELEMENT_SUPPORT_FILE_NAMES:
            xml_text = (CORE_BUFF_DIR / file_name).read_text(encoding="utf-8")
            self.assertNotIn("missing_image.png", xml_text, file_name)

    def test_new_player_facing_buffs_keep_mood_weight_at_or_below_two(self):
        for file_name in MOON_SOLAR_FILE_NAMES + ANGULAR_FILE_NAMES + ELEMENT_SUPPORT_FILE_NAMES:
            tree = ET.parse(CORE_BUFF_DIR / file_name)
            mood_weight = tree.find(".//T[@n='mood_weight']")
            self.assertIsNotNone(mood_weight, file_name)
            self.assertLessEqual(int(mood_weight.text), 2, file_name)

    def test_strings_contain_required_layered_solar_values(self):
        payload = json.loads(STRING_FILE.read_text(encoding="utf-8"))
        values = {entry["value"] for entry in payload["entries"]}
        self.assertIn("Solar Tide: Aries Moon", values)
        self.assertIn("Solar House Activation: First House", values)
        self.assertIn("Elemental Backing: Fire", values)


if __name__ == "__main__":
    unittest.main()
