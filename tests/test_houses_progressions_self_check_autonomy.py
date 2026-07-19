import pathlib
import unittest
import xml.etree.ElementTree as ET


ROOT = pathlib.Path(__file__).resolve().parents[1]
INTERACTION_ROOT = ROOT / "src" / "HousesandProgressions" / "Interaction"

SELF_CHECK_INTERACTIONS = (
    "PlumAntics_Big3ModHousesProgressions_SI_GetHouses.xml",
    "PlumAntics_Big3ModHousesProgressions_SI_GetProgressions.xml",
    "PlumAntics_Big3ModHousesProgressions_SI_GetHousesComputer.xml",
    "PlumAntics_Big3ModHousesProgressions_SI_GetProgressionsComputer.xml",
)

ADVANCED_READING_INTERACTIONS = (
    "PlumAntics_Big3ModHousesProgressions_SI_GetHouses.xml",
    "PlumAntics_Big3ModHousesProgressions_SI_GetProgressions.xml",
    "PlumAntics_Big3ModHousesProgressions_SI_GetHousesComputer.xml",
    "PlumAntics_Big3ModHousesProgressions_SI_GetProgressionsComputer.xml",
    "PlumAntics_Big3ModHousesProgressions_SI_ResearchHousesBooks.xml",
    "PlumAntics_Big3ModHousesProgressions_SI_ResearchProgressionsBooks.xml",
)


class SelfCheckAutonomyInteractionTests(unittest.TestCase):
    def test_self_check_interactions_disallow_autonomy_but_allow_user_direction(self):
        for name in SELF_CHECK_INTERACTIONS:
            root = ET.parse(INTERACTION_ROOT / name).getroot()
            self.assertEqual(
                "True",
                root.findtext("T[@n='allow_user_directed']"),
                msg="Expected allow_user_directed=True in {0}".format(name),
            )
            self.assertEqual(
                "False",
                root.findtext("T[@n='allow_autonomous']"),
                msg="Expected allow_autonomous=False in {0}".format(name),
            )

    def test_advanced_reading_interactions_unlock_at_level_4_without_a_ceiling(self):
        for name in ADVANCED_READING_INTERACTIONS:
            root = ET.parse(INTERACTION_ROOT / name).getroot()
            skill_test = root.find(".//V[@t='skill_test']/U[@n='skill_test']")
            self.assertIsNotNone(skill_test, msg="Missing skill_test in {0}".format(name))

            interval = skill_test.find("V[@n='skill_range'][@t='interval']/U[@n='interval']/U[@n='skill_interval']")
            self.assertIsNotNone(
                interval,
                msg="Expected interval-based skill gate in {0}".format(name),
            )
            self.assertEqual(
                "4",
                interval.findtext("T[@n='lower_bound']"),
                msg="Expected level 4 unlock in {0}".format(name),
            )
            self.assertIsNone(
                interval.find("T[@n='upper_bound']"),
                msg="Expected no upper skill ceiling in {0}".format(name),
            )


if __name__ == "__main__":
    unittest.main()
