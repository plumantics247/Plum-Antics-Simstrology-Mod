import json
import pathlib
import re
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SIGN_ROOT = ROOT / "src" / "SignCompatibility"
STRING_TABLE = ROOT / "src" / "String" / "SimstrologicalMod_English.stbl.json"
CONFIG_PATH = ROOT / "s4tk.config.json"
UINT32_MAX = 0xFFFFFFFF

CATEGORY_XML = tuple((SIGN_ROOT / "CASPreferenceCategory").glob("*.xml"))
CATEGORY_SIMDATA = tuple((SIGN_ROOT / "CASPreferenceCategory").glob("*.SimData.xml"))
PREFERENCE_XML = tuple((SIGN_ROOT / "PreferenceItem").glob("*/*.xml"))
PREFERENCE_SIMDATA = tuple((SIGN_ROOT / "PreferenceItem").glob("*/*.SimData.xml"))
PREFERENCE_TRAIT_XML = tuple((SIGN_ROOT / "Trait").glob("*.xml"))
PREFERENCE_TRAIT_SIMDATA = tuple((SIGN_ROOT / "Trait").glob("*.SimData.xml"))
BUFF_XML = tuple((SIGN_ROOT / "Buff").glob("*.xml"))
BUFF_SIMDATA = tuple((SIGN_ROOT / "Buff").glob("*.SimData.xml"))
STAT_XML = tuple((SIGN_ROOT / "Statistic").glob("*.xml"))
STAT_SIMDATA = tuple((SIGN_ROOT / "Statistic").glob("*.SimData.xml"))
GROUP_XML = tuple((SIGN_ROOT / "CASPreferenceGroup").glob("*.xml"))
GROUP_SIMDATA = tuple((SIGN_ROOT / "CASPreferenceGroup").glob("*.SimData.xml"))
SIGNS = (
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
ELEMENT_BY_SIGN = {
    "Aries": "Fire",
    "Leo": "Fire",
    "Sagittarius": "Fire",
    "Taurus": "Earth",
    "Virgo": "Earth",
    "Capricorn": "Earth",
    "Gemini": "Air",
    "Libra": "Air",
    "Aquarius": "Air",
    "Cancer": "Water",
    "Scorpio": "Water",
    "Pisces": "Water",
}
def _load_json(path):
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


class SignCompatibilityXmlTests(unittest.TestCase):
    def _expected_same_element_signs(self, target_sign):
        target_element = ELEMENT_BY_SIGN[target_sign]
        return [sign for sign in SIGNS if ELEMENT_BY_SIGN[sign] == target_element]

    def test_package_entry_exists_for_signcompatibility(self):
        payload = _load_json(CONFIG_PATH)
        package_names = [entry["filename"] for entry in payload["buildInstructions"]["packages"]]
        self.assertIn("PlumAntics_Simstrology_Addon_SignCompatibility_v2.51_optional", package_names)

        package_entry = next(
            entry
            for entry in payload["buildInstructions"]["packages"]
            if entry["filename"] == "PlumAntics_Simstrology_Addon_SignCompatibility_v2.51_optional"
        )
        self.assertEqual(["SignCompatibility/**/*"], package_entry["include"])

    def test_expected_file_counts_exist(self):
        self.assertEqual(3, len([path for path in CATEGORY_XML if not path.name.endswith(".SimData.xml")]))
        self.assertEqual(3, len(CATEGORY_SIMDATA))
        self.assertEqual(36, len([path for path in PREFERENCE_XML if not path.name.endswith(".SimData.xml")]))
        self.assertEqual(36, len(PREFERENCE_SIMDATA))
        self.assertEqual(72, len([path for path in PREFERENCE_TRAIT_XML if not path.name.endswith(".SimData.xml")]))
        self.assertEqual(72, len(PREFERENCE_TRAIT_SIMDATA))
        self.assertEqual(0, len([path for path in GROUP_XML if not path.name.endswith(".SimData.xml")]))
        self.assertEqual(0, len(GROUP_SIMDATA))

    def test_existing_preference_shell_baseline(self):
        self.assertEqual(36, len([path for path in PREFERENCE_XML if not path.name.endswith(".SimData.xml")]))
        self.assertEqual(72, len([path for path in PREFERENCE_TRAIT_XML if not path.name.endswith(".SimData.xml")]))
        self.assertGreaterEqual(len([path for path in BUFF_XML if not path.name.endswith(".SimData.xml")]), 6)
        self.assertGreaterEqual(len([path for path in STAT_XML if not path.name.endswith(".SimData.xml")]), 3)

    def test_category_icons_are_not_zeroed(self):
        sun_text = (
            SIGN_ROOT / "CASPreferenceCategory" / "PlumAntics_SunCompatibility_CasPreferenceCategory.SimData.xml"
        ).read_text(encoding="utf-8")
        moon_text = (
            SIGN_ROOT / "CASPreferenceCategory" / "PlumAntics_MoonCompatibility_CasPreferenceCategory.SimData.xml"
        ).read_text(encoding="utf-8")
        rising_text = (
            SIGN_ROOT / "CASPreferenceCategory" / "PlumAntics_RisingCompatibility_CasPreferenceCategory.SimData.xml"
        ).read_text(encoding="utf-8")

        self.assertNotIn("00000000-00000000-0000000000000000", sun_text)
        self.assertNotIn("00000000-00000000-0000000000000000", moon_text)
        self.assertNotIn("00000000-00000000-0000000000000000", rising_text)

    def test_strings_include_category_and_buff_labels(self):
        text = STRING_TABLE.read_text(encoding="utf-8")
        required_values = (
            "Sun Compatibility",
            "Moon Compatibility",
            "Rising Compatibility",
            "Sun Sign Like",
            "Sun Sign Dislike",
            "Moon Sign Like",
            "Moon Sign Dislike",
            "Rising Sign Like",
            "Rising Sign Dislike",
        )
        for value in required_values:
            self.assertIn(value, text)

    def test_generated_files_do_not_reference_python_modules(self):
        relevant_paths = (
            *CATEGORY_XML,
            *PREFERENCE_XML,
            *PREFERENCE_TRAIT_XML,
        )
        for path in relevant_paths:
            if path.name.endswith(".SimData.xml"):
                continue
            text = path.read_text(encoding="utf-8")
            self.assertNotRegex(text, re.compile(r"cosmic_engine|python"))

    def test_custom_preferences_use_32bit_instances(self):
        resource_paths = [
            *CATEGORY_XML,
            *PREFERENCE_XML,
            *PREFERENCE_TRAIT_XML,
        ]
        instance_pattern = re.compile(r'\bs="(\d+)"')

        for path in resource_paths:
            if path.name.endswith(".SimData.xml"):
                continue
            text = path.read_text(encoding="utf-8")
            match = instance_pattern.search(text)
            self.assertIsNotNone(match, path.as_posix())
            self.assertLessEqual(int(match.group(1)), UINT32_MAX, path.as_posix())

    def test_likes_dislikes_group_override_is_not_shipped(self):
        self.assertFalse(
            (SIGN_ROOT / "CASPreferenceGroup" / "casPreferenceGroup_likesdislikes.xml").exists()
        )
        self.assertFalse(
            (SIGN_ROOT / "CASPreferenceGroup" / "casPreferenceGroup_likesdislikes.SimData.xml").exists()
        )

    def test_preference_items_use_same_element_only_mapping(self):
        item_pattern = re.compile(
            r"PlumAntics_(Sun|Moon|Rising)Compatibility_(Aries|Taurus|Gemini|Cancer|Leo|Virgo|Libra|Scorpio|Sagittarius|Capricorn|Aquarius|Pisces)Preference"
        )
        trait_pattern = re.compile(
            r'<T n="key">\d+<!--PlumAntics_Big3Mod_(Aries|Taurus|Gemini|Cancer|Leo|Virgo|Libra|Scorpio|Sagittarius|Capricorn|Aquarius|Pisces)(Sun|Moon|Rising)--></T>\s*<T n="value">(5)</T>'
        )

        for path in PREFERENCE_XML:
            if path.name.endswith(".SimData.xml"):
                continue

            item_xml = path.read_text(encoding="utf-8")
            item_name_match = item_pattern.search(path.stem)
            self.assertIsNotNone(item_name_match, path.as_posix())
            channel, target_sign = item_name_match.groups()

            self.assertIn('c="CharacteristicPreferenceItem"', item_xml)
            self.assertEqual(3, item_xml.count('<T n="value">5</T>'), path.as_posix())
            self.assertEqual(0, item_xml.count('<T n="value">3</T>'), path.as_posix())

            actual = {sign for sign, mapped_channel, _ in trait_pattern.findall(item_xml)}
            expected = set(self._expected_same_element_signs(target_sign))
            self.assertEqual({channel}, {mapped_channel for _, mapped_channel, _ in trait_pattern.findall(item_xml)}, path.as_posix())
            self.assertEqual(expected, actual, path.as_posix())

        for path in PREFERENCE_SIMDATA:
            item_simdata = path.read_text(encoding="utf-8")
            self.assertIn('schema="CharacteristicPreferenceItem"', item_simdata, path.as_posix())
            self.assertIn('variant="0xC1A03855"', item_simdata, path.as_posix())

    def test_preference_traits_are_teen_plus_only(self):
        allowed_ages = {"TEEN", "YOUNGADULT", "ADULT", "ELDER"}
        blocked_ages = {"BABY", "TODDLER", "CHILD", "INFANT"}
        allowed_simdata_values = {"8", "16", "32", "64"}

        for path in PREFERENCE_TRAIT_XML:
            if path.name.endswith(".SimData.xml"):
                continue

            trait_xml = path.read_text(encoding="utf-8")
            ages_block = re.search(r'<L n="ages">(.*?)</L>', trait_xml, re.DOTALL)
            self.assertIsNotNone(ages_block, path.as_posix())
            present_ages = set(re.findall(r"<E>([A-Z]+)</E>", ages_block.group(1)))
            self.assertEqual(allowed_ages, present_ages, path.as_posix())
            self.assertTrue(blocked_ages.isdisjoint(present_ages), path.as_posix())

        for path in PREFERENCE_TRAIT_SIMDATA:
            trait_simdata = path.read_text(encoding="utf-8")
            ages_block = re.search(r'<L name="ages">(.*?)</L>', trait_simdata, re.DOTALL)
            self.assertIsNotNone(ages_block, path.as_posix())
            present_values = set(re.findall(r'<T type="Int64">(\d+)</T>', ages_block.group(1)))
            self.assertEqual(allowed_simdata_values, present_values, path.as_posix())

    def test_sign_categories_still_exist_without_local_group_override(self):
        for instance, stem in (
            ("4100000001", "PlumAntics_SunCompatibility_CasPreferenceCategory"),
            ("4100000002", "PlumAntics_MoonCompatibility_CasPreferenceCategory"),
            ("4100000003", "PlumAntics_RisingCompatibility_CasPreferenceCategory"),
        ):
            category_xml = (SIGN_ROOT / "CASPreferenceCategory" / f"{stem}.xml").read_text(
                encoding="utf-8"
            )
            self.assertIn(f's="{instance}"', category_xml)


if __name__ == "__main__":
    unittest.main()
