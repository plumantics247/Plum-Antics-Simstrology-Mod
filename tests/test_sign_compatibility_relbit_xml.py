import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
REL_ROOT = ROOT / "src" / "SignCompatibility" / "RelationshipBit"


class SignCompatibilityRelbitXmlTests(unittest.TestCase):
    def test_all_nine_relbit_files_exist(self):
        expected = {
            "PlumAntics_CosmicEngineCore_Relbit_SunCompatibility_Compatible.xml",
            "PlumAntics_CosmicEngineCore_Relbit_SunCompatibility_Neutral.xml",
            "PlumAntics_CosmicEngineCore_Relbit_SunCompatibility_Incompatible.xml",
            "PlumAntics_CosmicEngineCore_Relbit_MoonCompatibility_Compatible.xml",
            "PlumAntics_CosmicEngineCore_Relbit_MoonCompatibility_Neutral.xml",
            "PlumAntics_CosmicEngineCore_Relbit_MoonCompatibility_Incompatible.xml",
            "PlumAntics_CosmicEngineCore_Relbit_RisingCompatibility_Compatible.xml",
            "PlumAntics_CosmicEngineCore_Relbit_RisingCompatibility_Neutral.xml",
            "PlumAntics_CosmicEngineCore_Relbit_RisingCompatibility_Incompatible.xml",
        }
        self.assertEqual(
            expected,
            {
                path.name
                for path in REL_ROOT.glob(
                    "PlumAntics_CosmicEngineCore_Relbit_*Compatibility_*.xml"
                )
                if not path.name.endswith(".SimData.xml")
            },
        )

    def test_relbits_are_persistent_bidirectional_and_hidden(self):
        for path in REL_ROOT.glob("PlumAntics_CosmicEngineCore_Relbit_*Compatibility_*.xml"):
            if path.name.endswith(".SimData.xml"):
                continue
            text = path.read_text(encoding="utf-8")
            self.assertIn("<E n=\"directionality\">BIDIRECTIONAL</E>", text)
            self.assertIn("<T n=\"persisted_tuning\">True</T>", text)
            self.assertIn("<T n=\"visible\">False</T>", text)


if __name__ == "__main__":
    unittest.main()
