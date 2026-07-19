import json
import pathlib
import sys
import unittest
import xml.etree.ElementTree as ET


ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT / "python") not in sys.path:
    sys.path.insert(0, str(ROOT / "python"))


from cosmic_engine.crystal_resonance import (
    ATTUNEMENT_BUFF_ID_BY_CRYSTAL_KEY,
    PASSIVE_BUFF_ID_BY_CRYSTAL_KEY,
)
from cosmic_engine.crystal_resonance_activation import (
    CRYSTAL_RESONANCE_ADDON_MARKER_ID,
    CRYSTAL_RESONANCE_ADDON_MARKER_NAME,
)


CONFIG_PATH = ROOT / "s4tk.config.json"
CRYSTAL_DIR = ROOT / "src" / "CrystalResonance"
MARKER_PATH = CRYSTAL_DIR / "Snippet" / "PlumAntics_CosmicEngine_CrystalResonanceActivationMarker.xml"
REGISTER_LOOT_PATH = (
    CRYSTAL_DIR
    / "Action"
    / "PlumAntics_CosmicEngineCrystalResonance_RegisterGiftedCrystalLoot.xml"
)
GIFT_SUCCESS_OVERRIDE_PATH = (
    CRYSTAL_DIR / "Action" / "S4_0C772E27_0000001A_000000000002C111_loot_GiveGift_Success.xml"
)
GIFT_SUCCESS_BUFFS_OVERRIDE_PATH = (
    CRYSTAL_DIR / "Action" / "S4_0C772E27_0000001A_000000000002DF39_loot_Inventory_GiveGift_Success_Buffs.xml"
)
REGISTER_GIFTED_LOOT_ID = "840000000000009200"


class CrystalResonancePackagingTests(unittest.TestCase):
    def _read_lines(self, path):
        return path.read_text(encoding="utf-8").splitlines()

    def test_s4tk_config_builds_crystal_resonance_as_separate_addon_package(self):
        config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        packages = config["buildInstructions"]["packages"]
        filenames = {package["filename"]: package for package in packages}

        package = filenames["PlumAntics_Simstrology_Addon_CrystalResonance_v2.21_optional"]
        self.assertEqual(["CrystalResonance/**/*"], package["include"])
        self.assertEqual([], package["exclude"])

    def test_release_zip_includes_crystal_resonance_package(self):
        config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        zip_entry = config["releaseSettings"]["zips"][0]

        self.assertIn(
            "PlumAntics_Simstrology_Addon_CrystalResonance_v2.21_optional",
            zip_entry["packages"],
        )

    def test_activation_marker_snippet_matches_core_constants(self):
        tree = ET.parse(MARKER_PATH)
        root = tree.getroot()

        self.assertEqual("TuningInjector", root.attrib["c"])
        self.assertEqual("snippet", root.attrib["i"])
        self.assertEqual("lot51_core.snippets.injector", root.attrib["m"])
        self.assertEqual(CRYSTAL_RESONANCE_ADDON_MARKER_NAME, root.attrib["n"])
        self.assertEqual(str(CRYSTAL_RESONANCE_ADDON_MARKER_ID), root.attrib["s"])

    def test_register_gifted_loot_action_targets_python_bridge(self):
        tree = ET.parse(REGISTER_LOOT_PATH)
        root = tree.getroot()

        self.assertEqual("CosmicEngineRegisterGiftedCrystalResonanceLoot", root.attrib["c"])
        self.assertEqual("action", root.attrib["i"])
        self.assertEqual("cosmic_engine.loot_actions", root.attrib["m"])
        self.assertEqual(REGISTER_GIFTED_LOOT_ID, root.attrib["s"])

    def test_ea_gift_success_overrides_append_crystal_resonance_loot(self):
        for path in (GIFT_SUCCESS_OVERRIDE_PATH, GIFT_SUCCESS_BUFFS_OVERRIDE_PATH):
            root = ET.parse(path).getroot()
            actions = [node.text for node in root.findall(".//T[@n='actions']")]
            self.assertIn(REGISTER_GIFTED_LOOT_ID, actions, msg=str(path))

    def test_generated_buff_pairs_cover_every_primary_crystal(self):
        buff_dir = CRYSTAL_DIR / "Buff"

        for crystal_key, buff_id in PASSIVE_BUFF_ID_BY_CRYSTAL_KEY.items():
            stem = crystal_key.replace(" ", "")
            path = buff_dir / f"PlumAntics_CosmicEngineCrystalResonance_{stem}_Passive.xml"
            root = ET.parse(path).getroot()
            self.assertEqual(str(buff_id), root.attrib["s"])

        for crystal_key, buff_id in ATTUNEMENT_BUFF_ID_BY_CRYSTAL_KEY.items():
            stem = crystal_key.replace(" ", "")
            path = buff_dir / f"PlumAntics_CosmicEngineCrystalResonance_{stem}_Attunement.xml"
            root = ET.parse(path).getroot()
            self.assertEqual(str(buff_id), root.attrib["s"])

        xml_files = sorted(buff_dir.glob("*.xml"))
        simdata_files = sorted(buff_dir.glob("*.SimData.xml"))
        self.assertEqual(24, len([path for path in xml_files if not path.name.endswith(".SimData.xml")]))
        self.assertEqual(24, len(simdata_files))

    def test_passive_simdata_uses_hidden_buff_schema_and_matching_instance_comment(self):
        path = CRYSTAL_DIR / "Buff" / "PlumAntics_CosmicEngineCrystalResonance_Amethyst_Passive.SimData.xml"
        lines = self._read_lines(path)

        self.assertEqual(
            "<!-- S4TK Type: 545AC67A, Group: 0017E8F6, Instance: 0BA8478CAB542333 -->",
            lines[1],
        )
        self.assertIn('<SimData version="0x00000101" u="0x00000000">', lines[2])
        self.assertIn('<Schema name="Buff" schema_hash="0xDCE584D3">', "\n".join(lines))

    def test_attunement_simdata_uses_visible_buff_schema_and_matching_instance_comment(self):
        path = CRYSTAL_DIR / "Buff" / "PlumAntics_CosmicEngineCrystalResonance_Amethyst_Attunement.SimData.xml"
        lines = self._read_lines(path)

        self.assertEqual(
            "<!-- S4TK Type: 545AC67A, Group: 0017E8F6, Instance: 0BA8478CAB542397 -->",
            lines[1],
        )
        self.assertIn('<SimData version="0x00000101" u="0x0000000A">', lines[2])
        self.assertIn('<Schema name="Buff" schema_hash="0x71722956">', "\n".join(lines))


if __name__ == "__main__":
    unittest.main()
