import json
import pathlib
import sys
import unittest
import xml.etree.ElementTree as ET


ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT / "python") not in sys.path:
    sys.path.insert(0, str(ROOT / "python"))


from cosmic_engine.outer_planets_activation import (
    OUTER_PLANETS_ADDON_MARKER_ID,
    OUTER_PLANETS_ADDON_MARKER_NAME,
)


CONFIG_PATH = ROOT / "s4tk.config.json"
MARKER_PATH = (
    ROOT
    / "src"
    / "OuterPlanets"
    / "Snippet"
    / "PlumAntics_CosmicEngine_OuterPlanetsActivationMarker.xml"
)


class OuterPlanetsPackagingTests(unittest.TestCase):
    def test_s4tk_config_builds_outer_planets_as_separate_addon_package(self):
        config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        packages = config["buildInstructions"]["packages"]
        filenames = {package["filename"]: package for package in packages}

        package = filenames["PlumAntics_Simstrology_Addon_OuterPlanets_v2.21_optional"]
        self.assertEqual(["OuterPlanets/**/*"], package["include"])
        self.assertEqual(["OuterPlanets/DstSource/**/*"], package["exclude"])

    def test_release_zip_includes_outer_planets_package(self):
        config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        zip_entry = config["releaseSettings"]["zips"][0]

        self.assertIn(
            "PlumAntics_Simstrology_Addon_OuterPlanets_v2.21_optional",
            zip_entry["packages"],
        )

    def test_outer_planets_activation_marker_snippet_matches_core_constants(self):
        tree = ET.parse(MARKER_PATH)
        root = tree.getroot()

        self.assertEqual("TuningInjector", root.attrib["c"])
        self.assertEqual("snippet", root.attrib["i"])
        self.assertEqual("lot51_core.snippets.injector", root.attrib["m"])
        self.assertEqual(OUTER_PLANETS_ADDON_MARKER_NAME, root.attrib["n"])
        self.assertEqual(str(OUTER_PLANETS_ADDON_MARKER_ID), root.attrib["s"])


if __name__ == "__main__":
    unittest.main()
