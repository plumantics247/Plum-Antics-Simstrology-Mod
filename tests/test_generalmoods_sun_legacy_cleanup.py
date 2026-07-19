import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"

LEGACY_SUN_FILES = (
    SRC_DIR / "GeneralMoods" / "Statistic" / "PlumAntics_Big3ModGeneralMoods_AstrologySunController.xml",
    SRC_DIR / "GeneralMoods" / "Action" / "PlumAntics_Big3ModGeneralMoods_SunControllerMigration.xml",
    SRC_DIR / "GeneralMoods" / "Action" / "PlumAntics_Big3ModGeneralMoods_Reset_SunController.xml",
)

LEGACY_SUN_MARKERS = (
    "PlumAntics_Big3ModGeneralMoods_AstrologySunController",
    "PlumAntics_Big3Mod_SunControllerMigration",
    "PlumAntics_Big3Mod_Reset_SunController",
    "1506550166",
    "11497615811027826550",
)


class GeneralMoodsSunLegacyCleanupTests(unittest.TestCase):
    def test_legacy_generalmoods_sun_files_are_gone(self):
        existing = [str(path.relative_to(ROOT)) for path in LEGACY_SUN_FILES if path.exists()]
        self.assertEqual(
            [],
            existing,
            msg="Legacy GeneralMoods sun-controller files should be removed once the core per-sign sun path owns refresh behavior.",
        )

    def test_no_source_xml_keeps_legacy_generalmoods_sun_markers(self):
        hits = []
        for path in SRC_DIR.rglob("*.xml"):
            text = path.read_text(encoding="utf-8")
            for marker in LEGACY_SUN_MARKERS:
                if marker in text:
                    hits.append((str(path.relative_to(ROOT)), marker))

        self.assertEqual(
            [],
            hits,
            msg="Legacy GeneralMoods sun-controller markers should not remain anywhere in src after cleanup.",
        )


if __name__ == "__main__":
    unittest.main()
