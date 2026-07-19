import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"
PYTHON_DIR = ROOT / "python"

LEGACY_FILES = (
    SRC_DIR / "core" / "Interaction" / "PlumAntics_Big3ModCore_ReadNatalChart_SocialInteraction.xml",
    SRC_DIR / "core" / "Action" / "PlumAntics_Big3ModCore_ReadNatalChartBridge_Loot.xml",
)

LEGACY_XML_MARKERS = (
    "PlumAntics_Big3ModCore_ReadNatalChart_SocialInteraction",
    "13736671501533187742",
    "PlumAntics_Big3ModCore_ReadNatalChartBridge_Loot",
    "13736671501533187740",
)

LEGACY_PYTHON_MARKER = "class Big3ReadNatalChartSocialLoot"


class LegacyReadNatalChartCleanupTests(unittest.TestCase):
    def test_legacy_big3_read_chart_files_are_gone(self):
        existing = [str(path.relative_to(ROOT)) for path in LEGACY_FILES if path.exists()]
        self.assertEqual(
            [],
            existing,
            msg="Legacy Big3 read-chart interaction and bridge loot should be removed once CosmicEngine owns the surfaced social.",
        )

    def test_no_source_xml_keeps_legacy_big3_read_chart_markers(self):
        hits = []
        for path in SRC_DIR.rglob("*.xml"):
            text = path.read_text(encoding="utf-8")
            for marker in LEGACY_XML_MARKERS:
                if marker in text:
                    hits.append((str(path.relative_to(ROOT)), marker))

        self.assertEqual(
            [],
            hits,
            msg="Legacy Big3 read-chart XML markers should not remain anywhere in src after cleanup.",
        )

    def test_legacy_big3_read_chart_runtime_class_is_gone(self):
        runtime_path = PYTHON_DIR / "plumantics_big3_runtime" / "loot_actions.py"
        text = runtime_path.read_text(encoding="utf-8")
        self.assertNotIn(
            LEGACY_PYTHON_MARKER,
            text,
            msg="Legacy Big3 read-chart runtime bridge class should be removed once the CosmicEngine bridge owns the flow.",
        )


if __name__ == "__main__":
    unittest.main()
