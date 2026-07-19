import json
import pathlib
import unittest
import xml.etree.ElementTree as ET


ROOT = pathlib.Path(__file__).resolve().parents[1]
CORE_INTERACTION_DIR = ROOT / "src" / "core" / "Interaction"
HOROSCOPE_INTERACTION_DIR = ROOT / "src" / "Horoscopes" / "Interaction"
STRING_TABLE_PATH = ROOT / "src" / "String" / "SimstrologicalMod_English.stbl.json"

SELF_ASSIGNMENT_TOOLTIP_KEYS = {
    "PlumAntics_Big3ModCore_Sun_Random.xml": "0xA53F1E60",
    "PlumAntics_Big3ModCore_Sun_BySeason_SI.xml": "0xA53F1E61",
    "PlumAntics_Big3ModCore_Sun_ByPersonality_SI.xml": "0xA53F1E62",
    "PlumAntics_Big3ModCore_Moon_Random.xml": "0xA53F1E63",
    "PlumAntics_Big3ModCore_Moon_bySun.xml": "0xA53F1E64",
    "PlumAntics_CosmicEngineCore_Rising_Random.xml": "0xA53F1E65",
    "PlumAntics_CosmicEngineCore_RisingbySeason.xml": "0xA53F1E66",
}

SOCIAL_TOOLTIP_KEYS = {
    "PlumAntics_Big3ModCore_Compatibility_SocialInteraction.xml": "0xA53F1E80",
    "PlumAntics_CosmicEngineCore_ReadNatalChart_SocialInteraction.xml": "0xA53F1E81",
    "PlumAntics_CosmicEngineCore_DiscussChartRulers_SocialInteraction.xml": "0xA53F1E82",
    "PlumAntics_CosmicEngineCore_TalkAboutCurrentTransits_SocialInteraction.xml": "0xA53F1E83",
    "PlumAntics_CosmicEngineCore_ComplainAboutRetrogrades_SocialInteraction.xml": "0xA53F1E84",
}

HOROSCOPE_TOOLTIP_KEY = "0xA53F1E70"
HOROSCOPE_INTERACTIONS = (
    "PlumAntics_Big3ModHoroscopes_SI_GetHoroscope_Aquarius.xml",
    "PlumAntics_Big3ModHoroscopes_SI_GetHoroscope_AquariusComputer.xml",
    "PlumAntics_Big3ModHoroscopes_SI_GetHoroscope_Aries.xml",
    "PlumAntics_Big3ModHoroscopes_SI_GetHoroscope_AriesComputer.xml",
    "PlumAntics_Big3ModHoroscopes_SI_GetHoroscope_Cancer.xml",
    "PlumAntics_Big3ModHoroscopes_SI_GetHoroscope_CancerComputer.xml",
    "PlumAntics_Big3ModHoroscopes_SI_GetHoroscope_Capricorn.xml",
    "PlumAntics_Big3ModHoroscopes_SI_GetHoroscope_CapricornComputer.xml",
    "PlumAntics_Big3ModHoroscopes_SI_GetHoroscope_Gemini.xml",
    "PlumAntics_Big3ModHoroscopes_SI_GetHoroscope_GeminiComputer.xml",
    "PlumAntics_Big3ModHoroscopes_SI_GetHoroscope_Leo.xml",
    "PlumAntics_Big3ModHoroscopes_SI_GetHoroscope_LeoComputer.xml",
    "PlumAntics_Big3ModHoroscopes_SI_GetHoroscope_Libra.xml",
    "PlumAntics_Big3ModHoroscopes_SI_GetHoroscope_LibraComputer.xml",
    "PlumAntics_Big3ModHoroscopes_SI_GetHoroscope_Pisces.xml",
    "PlumAntics_Big3ModHoroscopes_SI_GetHoroscope_PiscesComputer.xml",
    "PlumAntics_Big3ModHoroscopes_SI_GetHoroscope_Sagittarius.xml",
    "PlumAntics_Big3ModHoroscopes_SI_GetHoroscope_SagittariusComputer.xml",
    "PlumAntics_Big3ModHoroscopes_SI_GetHoroscope_Scorpio.xml",
    "PlumAntics_Big3ModHoroscopes_SI_GetHoroscope_ScorpioComputer.xml",
    "PlumAntics_Big3ModHoroscopes_SI_GetHoroscope_Taurus.xml",
    "PlumAntics_Big3ModHoroscopes_SI_GetHoroscope_TaurusComputer.xml",
    "PlumAntics_Big3ModHoroscopes_SI_GetHoroscope_Virgo.xml",
    "PlumAntics_Big3ModHoroscopes_SI_GetHoroscope_VirgoComputer.xml",
)


def _tooltip_key(xml_path):
    root = ET.parse(xml_path).getroot()
    tooltip = root.find("V[@n='display_tooltip']")
    if tooltip is None:
        return None
    return tooltip.findtext("T[@n='enabled']")


def _string_table_keys():
    with STRING_TABLE_PATH.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    return {entry["key"].upper() for entry in payload["entries"]}


class EverydayGameplayTooltipTests(unittest.TestCase):
    def test_self_assignment_interactions_use_expected_tooltip_keys(self):
        failures = []
        for name, expected_key in SELF_ASSIGNMENT_TOOLTIP_KEYS.items():
            actual_key = _tooltip_key(CORE_INTERACTION_DIR / name)
            if actual_key != expected_key:
                failures.append("{0}: expected {1}, got {2}".format(name, expected_key, actual_key))
        self.assertFalse(
            failures,
            "Self-assignment interactions must use distinct tooltip keys that match their actual assignment rule. "
            + "; ".join(failures),
        )

    def test_self_assignment_tooltip_strings_exist(self):
        string_keys = _string_table_keys()
        missing = [
            key for key in sorted(set(SELF_ASSIGNMENT_TOOLTIP_KEYS.values()))
            if key.upper() not in string_keys
        ]
        self.assertFalse(
            missing,
            "Missing self-assignment tooltip keys in SimstrologicalMod_English.stbl.json: "
            + ", ".join(missing),
        )

    def test_social_interactions_use_expected_tooltip_keys(self):
        failures = []
        for name, expected_key in SOCIAL_TOOLTIP_KEYS.items():
            actual_key = _tooltip_key(CORE_INTERACTION_DIR / name)
            if actual_key != expected_key:
                failures.append("{0}: expected {1}, got {2}".format(name, expected_key, actual_key))
        self.assertFalse(
            failures,
            "Everyday social interactions must expose the expected tooltip key. " + "; ".join(failures),
        )

    def test_horoscope_interactions_share_one_tooltip_key(self):
        failures = []
        for name in HOROSCOPE_INTERACTIONS:
            actual_key = _tooltip_key(HOROSCOPE_INTERACTION_DIR / name)
            if actual_key != HOROSCOPE_TOOLTIP_KEY:
                failures.append("{0}: expected {1}, got {2}".format(name, HOROSCOPE_TOOLTIP_KEY, actual_key))
        self.assertFalse(
            failures,
            "Horoscope interactions must expose the shared horoscope tooltip key. " + "; ".join(failures),
        )

    def test_social_and_horoscope_tooltip_strings_exist(self):
        string_keys = _string_table_keys()
        expected_keys = set(SOCIAL_TOOLTIP_KEYS.values())
        expected_keys.add(HOROSCOPE_TOOLTIP_KEY)
        missing = [key for key in sorted(expected_keys) if key.upper() not in string_keys]
        self.assertFalse(
            missing,
            "Missing social or horoscope tooltip keys in SimstrologicalMod_English.stbl.json: "
            + ", ".join(missing),
        )


if __name__ == "__main__":
    unittest.main()
