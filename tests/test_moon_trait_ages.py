import pathlib
import unittest
import xml.etree.ElementTree as ET


ROOT = pathlib.Path(__file__).resolve().parents[1]
TRAIT_DIR = ROOT / "src" / "core" / "Trait"
EXPECTED_AGES = ("TEEN", "YOUNGADULT", "ADULT", "ELDER")
VISIBLE_MOON_TRAIT_NAMES = (
    "Aries",
    "Taurus",
    "Gemini",
    "Cancer",
    "Leo",
    "Virgo",
    "Libra",
    "Scorpio",
    "Sagittarius",
    "Capricorn",
    "Aquarius",
    "Pisces",
)


def _trait_ages(xml_path):
    root = ET.parse(xml_path).getroot()
    return tuple(age.text for age in root.findall("./L[@n='ages']/E"))


class MoonTraitAgesTests(unittest.TestCase):
    def test_visible_moon_traits_cover_all_teen_plus_ages(self):
        failures = []
        for sign in VISIBLE_MOON_TRAIT_NAMES:
            xml_path = TRAIT_DIR / "PlumAntics_Big3ModCore_{0}Moon.xml".format(sign)
            ages = _trait_ages(xml_path)
            if ages != EXPECTED_AGES:
                failures.append("{0}: expected {1}, got {2}".format(xml_path.name, EXPECTED_AGES, ages))
        self.assertFalse(
            failures,
            "Visible Moon sign traits must stay available for every teen-plus life stage. "
            + "; ".join(failures),
        )


if __name__ == "__main__":
    unittest.main()
