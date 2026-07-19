import pathlib
import unittest
import xml.etree.ElementTree as ET


ROOT = pathlib.Path(__file__).resolve().parents[1]
TRAIT_DIR = ROOT / "src" / "Retrogrades" / "Trait"


class RetrogradeTraitTuningTests(unittest.TestCase):
    def test_hidden_retrograde_traits_do_not_directly_add_visible_moodlets(self):
        trait_paths = sorted(TRAIT_DIR.glob("*RetrogradeActiveHidden.xml"))
        self.assertTrue(trait_paths, "Expected hidden retrograde trait XML files to exist")

        for trait_path in trait_paths:
            tree = ET.parse(trait_path)
            root = tree.getroot()
            loot_on_trait_add = root.find("./V[@n='loot_on_trait_add']")
            self.assertIsNone(
                loot_on_trait_add,
                f"{trait_path.name} should not apply visible retrograde moodlets from trait add",
            )


if __name__ == "__main__":
    unittest.main()
