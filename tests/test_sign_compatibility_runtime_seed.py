import importlib
import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
PYTHON_DIR = ROOT / "python"
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))


seed = importlib.import_module("cosmic_engine.sign_compatibility_runtime_seed")


class SignCompatibilityRuntimeSeedLogicTests(unittest.TestCase):
    def test_same_sign_like_uses_same_element_hidden_preference_trait_ids(self):
        record = seed.build_expected_sign_compatibility_seed_record(
            sun_sign_index=0,
            moon_sign_index=0,
            rising_sign_index=0,
        )
        self.assertEqual(
            (4100020001, 4100020005, 4100020009),
            tuple(record["lanes"]["Sun"]["auto_like_trait_ids"]),
        )
        self.assertEqual(
            (4100120001, 4100120005, 4100120009),
            tuple(record["lanes"]["Moon"]["auto_like_trait_ids"]),
        )
        self.assertEqual(
            (4100220001, 4100220005, 4100220009),
            tuple(record["lanes"]["Rising"]["auto_like_trait_ids"]),
        )

    def test_same_sign_dislike_uses_full_opposing_element_hidden_preference_trait_ids(self):
        record = seed.build_expected_sign_compatibility_seed_record(
            sun_sign_index=0,
            moon_sign_index=0,
            rising_sign_index=0,
        )
        self.assertEqual(
            (4100030004, 4100030008, 4100030012),
            tuple(record["lanes"]["Sun"]["auto_dislike_trait_ids"]),
        )
        self.assertEqual(
            (4100130004, 4100130008, 4100130012),
            tuple(record["lanes"]["Moon"]["auto_dislike_trait_ids"]),
        )
        self.assertEqual(
            (4100230004, 4100230008, 4100230012),
            tuple(record["lanes"]["Rising"]["auto_dislike_trait_ids"]),
        )

    def test_sun_lane_maps_to_characteristic_like_and_dislike_trait_ids(self):
        record = seed.build_expected_sign_compatibility_seed_record(
            sun_sign_index=0,
            moon_sign_index=4,
            rising_sign_index=8,
        )
        lane = record["lanes"]["Sun"]
        self.assertEqual(305964, lane["ea_like_trait_id"])
        self.assertEqual(306407, lane["ea_dislike_trait_id"])

    def test_moon_lane_maps_to_conversation_topic_like_and_dislike_trait_ids(self):
        record = seed.build_expected_sign_compatibility_seed_record(
            sun_sign_index=0,
            moon_sign_index=10,
            rising_sign_index=8,
        )
        lane = record["lanes"]["Moon"]
        self.assertEqual(306465, lane["ea_like_trait_id"])
        self.assertEqual(306481, lane["ea_dislike_trait_id"])

    def test_moon_lane_maps_to_attraction_turn_on_and_turn_off_trait_ids(self):
        record = seed.build_expected_sign_compatibility_seed_record(
            sun_sign_index=0,
            moon_sign_index=0,
            rising_sign_index=8,
        )
        lane = record["lanes"]["Moon"]
        self.assertEqual(363941, lane["ea_attraction_turn_on_trait_id"])
        self.assertEqual(363942, lane["ea_attraction_turn_off_trait_id"])

    def test_rising_lane_maps_to_revised_conversation_topic_like_and_dislike_trait_ids(self):
        record = seed.build_expected_sign_compatibility_seed_record(
            sun_sign_index=0,
            moon_sign_index=4,
            rising_sign_index=10,
        )
        lane = record["lanes"]["Rising"]
        self.assertEqual(306469, lane["ea_like_trait_id"])
        self.assertEqual(306484, lane["ea_dislike_trait_id"])

    def test_runtime_seed_record_contains_twenty_six_owned_defaults(self):
        record = seed.build_expected_sign_compatibility_seed_record(
            sun_sign_index=0,
            moon_sign_index=4,
            rising_sign_index=8,
        )
        sun_lane = record["lanes"]["Sun"]
        moon_lane = record["lanes"]["Moon"]
        rising_lane = record["lanes"]["Rising"]

        self.assertEqual(
            (0, 4, 8),
            tuple(
                record[key]
                for key in ("sun_sign_index", "moon_sign_index", "rising_sign_index")
            ),
        )
        self.assertEqual(
            (0, 4, 8),
            tuple(lane["seed_sign_index"] for lane in (sun_lane, moon_lane, rising_lane)),
        )

        self.assertEqual((0, 4, 8), tuple(sun_lane["auto_like_sign_indexes"]))
        self.assertEqual((3, 7, 11), tuple(sun_lane["auto_dislike_sign_indexes"]))
        self.assertEqual(
            (4100020001, 4100020005, 4100020009),
            tuple(sun_lane["auto_like_trait_ids"]),
        )
        self.assertEqual(
            (4100030004, 4100030008, 4100030012),
            tuple(sun_lane["auto_dislike_trait_ids"]),
        )

        owned_slot_ids = [
            trait_id
            for lane_name in ("Sun", "Moon", "Rising")
            for slot_name in ("auto_like_trait_ids", "auto_dislike_trait_ids")
            for trait_id in record["lanes"][lane_name][slot_name]
        ] + [
            record["lanes"][lane_name]["ea_like_trait_id"]
            for lane_name in ("Sun", "Moon", "Rising")
        ] + [
            record["lanes"][lane_name]["ea_dislike_trait_id"]
            for lane_name in ("Sun", "Moon", "Rising")
        ] + [
            record["lanes"][lane_name]["ea_attraction_turn_on_trait_id"]
            for lane_name in ("Sun", "Moon", "Rising")
            if record["lanes"][lane_name].get("ea_attraction_turn_on_trait_id") is not None
        ] + [
            record["lanes"][lane_name]["ea_attraction_turn_off_trait_id"]
            for lane_name in ("Sun", "Moon", "Rising")
            if record["lanes"][lane_name].get("ea_attraction_turn_off_trait_id") is not None
        ]
        self.assertEqual(26, len(owned_slot_ids))
        self.assertTrue(
            {
                4100020001,
                4100020005,
                4100020009,
                4100030004,
                4100030008,
                4100030012,
                4100120005,
                4100120009,
                4100130004,
                4100130008,
                4100130012,
                4100220009,
                4100220001,
                4100220005,
                4100230004,
                4100230008,
                4100230012,
                305964,
                306407,
                306464,
                306483,
                306466,
                363957,
                363952,
            }.issubset(set(owned_slot_ids))
        )
        self.assertEqual(set(owned_slot_ids), set(record["trait_ids_flat"]))

    def test_chart_signature_changes_when_any_lane_changes(self):
        self.assertNotEqual(
            seed.build_chart_signature(0, 4, 8),
            seed.build_chart_signature(0, 4, 9),
        )


if __name__ == "__main__":
    unittest.main()
