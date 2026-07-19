import pathlib
import re
import sys
import unittest
from collections import Counter


sys.dont_write_bytecode = True

ROOT = pathlib.Path(__file__).resolve().parents[1]
SNIPPET_DIR = ROOT / "src" / "SignCompatibility" / "Snippet"
LEGACY_SUN_TIER_DIR = ROOT / "archive" / "SunCompatibility" / "Buff"
CORE_BUFF_DIR = ROOT / "src" / "SignCompatibility" / "Buff"
LEGACY_SUN_BUFF_DIR = ROOT / "archive" / "SunCompatibility" / "Buff"
RISING_SIGNS = (
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


def _negative_bucket_duplicates(xml_path):
    text = xml_path.read_text(encoding="utf-8")
    duplicates = {}
    modifier_pattern = re.compile(
        r"<V t=\"affordance_modifier\">\s*<U n=\"affordance_modifier\">(.*?)</U>\s*</V>",
        re.DOTALL,
    )
    bonus_pattern = re.compile(r"<T n=\"content_score_bonus\">(-?\d+)</T>")
    affordance_pattern = re.compile(r"<T>(\d+)(?:<!--(.*?)-->)?</T>")
    for modifier_match in modifier_pattern.finditer(text):
        modifier_text = modifier_match.group(1)
        bonus_match = bonus_pattern.search(modifier_text)
        if bonus_match is None or int(bonus_match.group(1)) <= 0:
            continue
        bonus_value = int(bonus_match.group(1))
        affordance_labels = {}
        affordance_ids = []
        for affordance_id, comment in affordance_pattern.findall(modifier_text):
            affordance_id = affordance_id.strip()
            label = comment.strip() or affordance_id
            affordance_labels.setdefault(affordance_id, label)
            affordance_ids.append(affordance_id)
        counts = Counter(affordance_ids)
        repeated = sorted(
            "{0} ({1})".format(affordance_id, affordance_labels[affordance_id])
            for affordance_id, count in counts.items()
            if count > 1
        )
        if repeated:
            duplicates[bonus_value] = repeated
    return duplicates


class ChemistryTuningTests(unittest.TestCase):
    def test_every_rising_sign_has_matching_residual_affordance_list(self):
        missing = []
        for sign in RISING_SIGNS:
            base_path = SNIPPET_DIR / (
                "PlumAntics_Big3ModCore_affordanceList_{0}Rising.xml".format(sign)
            )
            residual_path = SNIPPET_DIR / (
                "PlumAntics_Big3ModCore_affordanceList_{0}RisingResidual.xml".format(sign)
            )
            self.assertTrue(base_path.exists(), str(base_path))
            if not residual_path.exists():
                missing.append(residual_path.name)

        self.assertEqual([], missing, "Missing Rising residual affordance lists: {0}".format(missing))

    def test_incompatible_sun_tier_files_do_not_repeat_negative_bucket_references(self):
        duplicate_map = {}
        for xml_path in sorted(LEGACY_SUN_TIER_DIR.glob("PlumAntics_Big3ModSunCompatibility_Tier_*.xml")):
            if xml_path.name.endswith(".SimData.xml"):
                continue
            duplicates = _negative_bucket_duplicates(xml_path)
            if duplicates:
                duplicate_map[xml_path.name] = duplicates

        self.assertEqual(
            {},
            duplicate_map,
            "Duplicate negative interaction bucket references found: {0}".format(duplicate_map),
        )

    def test_generated_chemistry_buff_simdata_uses_resource_key_icon_format(self):
        invalid_icons = {}
        chemistry_paths = sorted(CORE_BUFF_DIR.glob("PlumAntics_CosmicEngineCore_*Rising*.SimData.xml"))
        chemistry_paths.extend(
            sorted(
                LEGACY_SUN_BUFF_DIR.glob("PlumAntics_CosmicEngineCore_SunChemistryOverlay_*.SimData.xml")
            )
        )
        for simdata_path in chemistry_paths:
            text = simdata_path.read_text(encoding="utf-8")
            icon_match = re.search(r"<T name=\"icon\">(.*?)</T>", text)
            if icon_match is None:
                invalid_icons[simdata_path.name] = "missing icon"
                continue
            icon_value = icon_match.group(1).strip()
            if not re.fullmatch(r"[0-9A-F]{8}-[0-9A-F]{8}-[0-9A-F]{16}", icon_value):
                invalid_icons[simdata_path.name] = icon_value

        self.assertEqual(
            {},
            invalid_icons,
            "Generated chemistry SimData files have invalid icon resource keys: {0}".format(
                invalid_icons
            ),
        )


if __name__ == "__main__":
    unittest.main()
