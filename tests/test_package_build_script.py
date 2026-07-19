import json
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
PACKAGE_JSON_PATH = ROOT / "package.json"
BUILD_SCRIPT_PATH = ROOT / "tools" / "build_s4tk_packages.js"
S4TK_CONFIG_PATH = ROOT / "s4tk.config.json"


class PackageBuildScriptTests(unittest.TestCase):
    def test_package_json_exposes_repo_local_package_build_scripts(self):
        package_json = json.loads(PACKAGE_JSON_PATH.read_text(encoding="utf-8"))
        scripts = package_json["scripts"]

        self.assertEqual(
            "node .\\tools\\build_s4tk_packages.js --mode build",
            scripts["build:package"],
        )
        self.assertEqual(
            "node .\\tools\\build_s4tk_packages.js --mode release",
            scripts["build:package:release"],
        )

    def test_repo_local_package_build_script_exists(self):
        self.assertTrue(BUILD_SCRIPT_PATH.is_file())

    def test_release_zip_package_names_match_declared_build_package_filenames(self):
        config = json.loads(S4TK_CONFIG_PATH.read_text(encoding="utf-8"))
        build_package_names = {
            package["filename"]
            for package in config["buildInstructions"]["packages"]
        }
        zip_package_names = set(config["releaseSettings"]["zips"][0]["packages"])

        self.assertEqual(build_package_names, zip_package_names)


if __name__ == "__main__":
    unittest.main()
