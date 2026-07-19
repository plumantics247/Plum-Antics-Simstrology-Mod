import pathlib
import unittest
import xml.etree.ElementTree as ET


ROOT = pathlib.Path(__file__).resolve().parents[1]
CORE_INTERACTION_DIR = ROOT / "src" / "core" / "Interaction"

COMPACT_SOCIALS = (
    "PlumAntics_Big3ModCore_Compatibility_SocialInteraction.xml",
    "PlumAntics_CosmicEngineCore_ComplainAboutRetrogrades_SocialInteraction.xml",
    "PlumAntics_CosmicEngineCore_DiscussChartRulers_SocialInteraction.xml",
    "PlumAntics_CosmicEngineCore_ReadNatalChart_SocialInteraction.xml",
    "PlumAntics_CosmicEngineCore_TalkAboutCurrentTransits_SocialInteraction.xml",
)

EXPECTED_CHILDREN = (
    ("T", "base_score"),
    ("L", "buff_preference"),
    ("V", "front_page_cooldown"),
)


class SimstrologySocialContentScoreTests(unittest.TestCase):
    def test_compact_socials_keep_only_the_approved_content_score_children(self):
        for name in COMPACT_SOCIALS:
            root = ET.parse(CORE_INTERACTION_DIR / name).getroot()
            enabled = root.find("V[@n='content_score'][@t='enabled']/U[@n='enabled']")
            self.assertIsNotNone(enabled, msg="Missing enabled content_score block in {0}".format(name))

            actual_children = tuple((child.tag, child.get("n")) for child in list(enabled))
            self.assertEqual(
                EXPECTED_CHILDREN,
                actual_children,
                msg="Expected compact content_score shell in {0}, got {1}".format(name, actual_children),
            )


if __name__ == "__main__":
    unittest.main()
