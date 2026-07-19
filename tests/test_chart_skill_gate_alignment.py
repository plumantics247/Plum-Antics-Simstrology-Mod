import pathlib
import re
import unittest
import xml.etree.ElementTree as ET


ROOT = pathlib.Path(__file__).resolve().parents[1]
CORE_INTERACTION_DIR = ROOT / "src" / "core" / "Interaction"
COSMIC_LOOT_ACTIONS = ROOT / "python" / "cosmic_engine" / "loot_actions.py"
ASTROLOGY_SKILL_GATE = ROOT / "python" / "cosmic_engine" / "astrology_skill_gate.py"

ADVANCED_CHART_READING_SOCIALS = (
    "PlumAntics_CosmicEngineCore_ReadNatalChart_SocialInteraction.xml",
    "PlumAntics_CosmicEngineCore_TalkAboutCurrentTransits_SocialInteraction.xml",
)

PYTHON_FALLBACK_PATTERN = re.compile(
    r'simstrology_skill_unlock_level\("advanced_chart_reading", default=(\d+)\)'
)


class ChartSkillGateAlignmentTests(unittest.TestCase):
    def test_advanced_chart_reading_socials_unlock_at_level_4(self):
        for name in ADVANCED_CHART_READING_SOCIALS:
            root = ET.parse(CORE_INTERACTION_DIR / name).getroot()
            threshold = root.findtext(
                "./L[@n='test_globals']/V[@t='skill_test']/U[@n='skill_test']"
                "/V[@n='skill_range']/U[@n='threshold']/U[@n='skill_threshold']/T[@n='value']"
            )
            self.assertEqual("4", threshold, msg="Expected level-4 skill gate in {0}".format(name))

    def test_advanced_chart_reading_unlock_map_stays_at_level_4(self):
        text = ASTROLOGY_SKILL_GATE.read_text(encoding="utf-8")
        self.assertIn('"advanced_chart_reading": 4', text)

    def test_python_fallbacks_match_the_level_4_advanced_chart_reading_gate(self):
        text = COSMIC_LOOT_ACTIONS.read_text(encoding="utf-8")
        defaults = tuple(int(match.group(1)) for match in PYTHON_FALLBACK_PATTERN.finditer(text))
        self.assertEqual(
            (4, 4),
            defaults,
            msg=(
                "CosmicEngine loot_actions.py should keep the read-chart and transit-weather "
                "advanced_chart_reading fallbacks aligned to level 4."
            ),
        )


if __name__ == "__main__":
    unittest.main()
