import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"

LEGACY_RISING_FILES = (
    SRC_DIR / "GeneralMoods" / "Action" / "PlumAntics_Big3ModGeneralMoods_RisingControllerMigration.xml",
    SRC_DIR / "GeneralMoods" / "Action" / "PlumAntics_Big3ModGeneralMoods_Reset_RisingController.xml",
)

LEGACY_RISING_MARKERS = (
    "PlumAntics_Big3Mod_RisingControllerMigration",
    "PlumAntics_Big3Mod_Reset_RisingController",
    "2143187574",
    "1778355158",
)


class GeneralMoodsRisingLegacyCleanupTests(unittest.TestCase):
    def test_legacy_generalmoods_rising_files_are_gone(self):
        existing = [str(path.relative_to(ROOT)) for path in LEGACY_RISING_FILES if path.exists()]
        self.assertEqual(
            [],
            existing,
            msg="Legacy GeneralMoods rising migration/reset files should be removed once overlays own the rising controller path.",
        )

    def test_no_source_xml_keeps_legacy_generalmoods_rising_markers(self):
        hits = []
        for path in SRC_DIR.rglob("*.xml"):
            text = path.read_text(encoding="utf-8")
            for marker in LEGACY_RISING_MARKERS:
                if marker in text:
                    hits.append((str(path.relative_to(ROOT)), marker))

        self.assertEqual(
            [],
            hits,
            msg="Legacy GeneralMoods rising migration/reset markers should not remain anywhere in src after cleanup.",
        )


if __name__ == "__main__":
    unittest.main()
