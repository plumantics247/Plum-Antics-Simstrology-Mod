import json
import pathlib
import re
import unittest
import xml.etree.ElementTree as ET


ROOT = pathlib.Path(__file__).resolve().parents[1]
TRAIT_DIR = ROOT / "src" / "OuterPlanets" / "Trait"
BUFF_DIR = ROOT / "src" / "OuterPlanets" / "Buff"
DST_IMAGE_DIR = ROOT / "src" / "OuterPlanets" / "DstImage"
STRING_TABLE_PATH = ROOT / "src" / "String" / "SimstrologicalMod_English.stbl.json"

ALL_HOUSES = (
    "First",
    "Second",
    "Third",
    "Fourth",
    "Fifth",
    "Sixth",
    "Seventh",
    "Eighth",
    "Ninth",
    "Tenth",
    "Eleventh",
    "Twelfth",
)
VISIBLE_HOUSES = ("First", "Fourth", "Tenth")
OUTER_BODIES = ("Uranus", "Neptune", "Pluto", "Chiron")
EXPECTED_MOODS = {
    "Uranus": ("15799275429558895056", "1"),
    "Neptune": ("9986929074150603838", "1"),
    "Pluto": ("15435392828079855046", "2"),
    "Chiron": ("16174400495578286549", "1"),
}
EXPECTED_VISIBLE_NAMES = {
    "PlumAntics_CosmicEngineHouses_FirstHouse_UranusTransitBuff": "Uranus Transiting The 1st House: Wild Card Aura",
    "PlumAntics_CosmicEngineHouses_FourthHouse_UranusTransitBuff": "Uranus Transiting The 4th House: Restless Nest",
    "PlumAntics_CosmicEngineHouses_TenthHouse_UranusTransitBuff": "Uranus Transiting The 10th House: Career Plot Twist",
    "PlumAntics_CosmicEngineHouses_FirstHouse_NeptuneTransitBuff": "Neptune Transiting The 1st House: Soft Focus Persona",
    "PlumAntics_CosmicEngineHouses_FourthHouse_NeptuneTransitBuff": "Neptune Transiting The 4th House: Private Fog Bank",
    "PlumAntics_CosmicEngineHouses_TenthHouse_NeptuneTransitBuff": "Neptune Transiting The 10th House: Mythmaking Season",
    "PlumAntics_CosmicEngineHouses_FirstHouse_PlutoTransitBuff": "Pluto Transiting The 1st House: Rebuild the Self",
    "PlumAntics_CosmicEngineHouses_FourthHouse_PlutoTransitBuff": "Pluto Transiting The 4th House: Basement Excavation",
    "PlumAntics_CosmicEngineHouses_TenthHouse_PlutoTransitBuff": "Pluto Transiting The 10th House: Power Climb",
    "PlumAntics_CosmicEngineHouses_FirstHouse_ChironTransitBuff": "Chiron Transiting The 1st House: Tender Edges",
    "PlumAntics_CosmicEngineHouses_FourthHouse_ChironTransitBuff": "Chiron Transiting The 4th House: Ancestral Ache",
    "PlumAntics_CosmicEngineHouses_TenthHouse_ChironTransitBuff": "Chiron Transiting The 10th House: Public Bruise, Public Lesson",
}
VISIBLE_ICON_SIMDATA_BY_BODY = {
    "Uranus": "2F7D0004-00000000-A8F7344C2D7B91E1",
    "Neptune": "2F7D0004-00000000-B61C9D4F7AE20358",
    "Pluto": "2F7D0004-00000000-C4E8A91B5FD07236",
    "Chiron": "2F7D0004-00000000-C4E8A91B5FD07236",
}
VISIBLE_ICON_XML_BY_BODY = {
    "Uranus": "2f7d0004:00000000:a8f7344c2d7b91e1",
    "Neptune": "2f7d0004:00000000:b61c9d4f7ae20358",
    "Pluto": "2f7d0004:00000000:c4e8a91b5fd07236",
    "Chiron": "2f7d0004:00000000:c4e8a91b5fd07236",
}
EXPECTED_DDS_FILES = {
    "00B2D882_00000000_A8F7344C2D7B91E1.dds",
    "00B2D882_00000000_B61C9D4F7AE20358.dds",
    "00B2D882_00000000_C4E8A91B5FD07236.dds",
}
SUN_FALLBACK_ICON_SIMDATA = "2F7D0004-00000000-DED106F4B50BC238"


def _string_values():
    payload = json.loads(STRING_TABLE_PATH.read_text(encoding="utf-8"))
    return {entry["value"] for entry in payload["entries"]}


def _match_body(path):
    match = re.search(r"_(Uranus|Neptune|Pluto|Chiron)(?:TransitBuff|TransitMarker)(?:\.SimData)?$", path.stem)
    return None if match is None else match.group(1)


def _icon_text(root):
    return root.findtext(".//T[@name='icon']") or root.findtext(".//T[@n='icon']")


class OuterPlanetsHouseAssetTests(unittest.TestCase):
    def test_hidden_marker_inventory_covers_all_outer_bodies_and_houses(self):
        xml_paths = sorted(TRAIT_DIR.glob("*Hidden.xml"))
        xml_paths = [path for path in xml_paths if not path.name.endswith(".SimData.xml")]
        names = {path.stem for path in xml_paths}

        expected = {
            "PlumAntics_CosmicEngineHouses_{0}House_{1}Hidden".format(house, body)
            for house in ALL_HOUSES
            for body in OUTER_BODIES
        }
        self.assertEqual(expected, names)

    def test_visible_transit_marker_inventory_is_limited_to_first_fourth_tenth(self):
        xml_paths = sorted(TRAIT_DIR.glob("*TransitMarker.xml"))
        xml_paths = [path for path in xml_paths if not path.name.endswith(".SimData.xml")]
        names = {path.stem for path in xml_paths}

        expected = {
            "PlumAntics_CosmicEngineHouses_{0}House_{1}TransitMarker".format(house, body)
            for house in VISIBLE_HOUSES
            for body in OUTER_BODIES
        }
        self.assertEqual(expected, names)

    def test_visible_transit_buff_inventory_is_limited_to_first_fourth_tenth(self):
        xml_paths = sorted(BUFF_DIR.glob("*TransitBuff.xml"))
        xml_paths = [path for path in xml_paths if not path.name.endswith(".SimData.xml")]
        names = {path.stem for path in xml_paths}

        expected = {
            "PlumAntics_CosmicEngineHouses_{0}House_{1}TransitBuff".format(house, body)
            for house in VISIBLE_HOUSES
            for body in OUTER_BODIES
        }
        self.assertEqual(expected, names)

    def test_every_generated_trait_and_buff_has_matching_simdata(self):
        roots = (TRAIT_DIR, BUFF_DIR)
        missing = []
        for root in roots:
            for xml_path in sorted(root.glob("*.xml")):
                if xml_path.name.endswith(".SimData.xml"):
                    continue
                simdata_path = xml_path.with_name(xml_path.stem + ".SimData.xml")
                if not simdata_path.exists():
                    missing.append(simdata_path.name)
        self.assertEqual([], missing)

    def test_visible_outer_planet_buffs_use_approved_moods_and_weights(self):
        mismatches = {}
        for xml_path in sorted(BUFF_DIR.glob("*TransitBuff.xml")):
            if xml_path.name.endswith(".SimData.xml"):
                continue
            root = ET.parse(xml_path).getroot()
            match = re.search(r"_(Uranus|Neptune|Pluto|Chiron)TransitBuff$", xml_path.stem)
            self.assertIsNotNone(match, xml_path.name)
            body = match.group(1)
            mood_type = root.findtext("T[@n='mood_type']")
            mood_weight = root.findtext("T[@n='mood_weight']")
            if (str(mood_type), str(mood_weight)) != EXPECTED_MOODS[body]:
                mismatches[xml_path.name] = (mood_type, mood_weight)
        self.assertEqual({}, mismatches)

    def test_visible_outer_planet_copy_exists_in_string_table(self):
        values = _string_values()
        missing = [value for value in EXPECTED_VISIBLE_NAMES.values() if value not in values]
        self.assertEqual([], missing)

    def test_normalized_outer_planet_dds_resources_exist_with_expected_names(self):
        names = {path.name for path in DST_IMAGE_DIR.glob("*.dds")}
        self.assertEqual(EXPECTED_DDS_FILES, names)

        invalid_headers = {}
        for path in sorted(DST_IMAGE_DIR.glob("*.dds")):
            header = path.read_bytes()[:4]
            if header != b"DDS ":
                invalid_headers[path.name] = header.hex()
        self.assertEqual({}, invalid_headers)

    def test_visible_outer_planet_marker_and_buff_icons_use_expected_keys(self):
        wrong_icons = {}

        visible_trait_xml_paths = [
            path for path in sorted(TRAIT_DIR.glob("*TransitMarker.xml"))
            if not path.name.endswith(".SimData.xml")
        ]
        visible_trait_simdata_paths = sorted(TRAIT_DIR.glob("*TransitMarker.SimData.xml"))
        visible_buff_xml_paths = [
            path for path in sorted(BUFF_DIR.glob("*TransitBuff.xml"))
            if not path.name.endswith(".SimData.xml")
        ]
        visible_buff_simdata_paths = sorted(BUFF_DIR.glob("*TransitBuff.SimData.xml"))

        for xml_path in visible_trait_xml_paths + visible_buff_xml_paths:
            body = _match_body(xml_path)
            self.assertIsNotNone(body, xml_path.name)
            root = ET.parse(xml_path).getroot()
            icon_value = _icon_text(root)
            if icon_value != VISIBLE_ICON_XML_BY_BODY[body]:
                wrong_icons[xml_path.name] = icon_value

        for simdata_path in visible_trait_simdata_paths + visible_buff_simdata_paths:
            body = _match_body(simdata_path)
            self.assertIsNotNone(body, simdata_path.name)
            root = ET.parse(simdata_path).getroot()
            icon_value = _icon_text(root)
            if icon_value != VISIBLE_ICON_SIMDATA_BY_BODY[body]:
                wrong_icons[simdata_path.name] = icon_value

        self.assertEqual({}, wrong_icons)
        self.assertEqual(
            VISIBLE_ICON_SIMDATA_BY_BODY["Pluto"],
            VISIBLE_ICON_SIMDATA_BY_BODY["Chiron"],
        )
        self.assertNotEqual(
            VISIBLE_ICON_SIMDATA_BY_BODY["Uranus"],
            VISIBLE_ICON_SIMDATA_BY_BODY["Neptune"],
        )
        self.assertNotIn(SUN_FALLBACK_ICON_SIMDATA, wrong_icons.values())


if __name__ == "__main__":
    unittest.main()
