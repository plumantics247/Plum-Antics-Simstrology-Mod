import importlib
import pathlib
import sys
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[1]
PYTHON_DIR = ROOT / "python"
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))


natal_snapshot_markers = importlib.import_module("cosmic_engine.natal_snapshot_markers")
chart_records = importlib.import_module("cosmic_engine.chart_records")


class _FakeTransitService(object):
    def __init__(self):
        self.saved = []
        self.state = type("State", (), {"sign_index_by_body": {}})()

    def current_sim_day(self):
        return 12

    def set_chart_record_payload(self, sim_id, payload):
        self.saved.append((int(sim_id), dict(payload)))

    def get_chart_record_payload(self, sim_id):
        return None


class _FakeSimInfo(object):
    def __init__(self, sim_id, household_id=55):
        self.sim_id = int(sim_id)
        self.id = int(sim_id)
        self.household_id = int(household_id)
        self.trait_tracker = object()


class NatalSnapshotMarkerTests(unittest.TestCase):
    def test_store_chart_record_supports_existing_visible_signs_provenance(self):
        service = _FakeTransitService()
        sim_info = _FakeSimInfo(1234)

        payload = natal_snapshot_markers._store_chart_record_for_sim(
            sim_info=sim_info,
            transit_service=service,
            house_sign_map={0: 0, 1: 1, 2: 2},
            body_sign_index_by_name={
                "Sun": 0,
                "Moon": 4,
                "Mercury": 2,
                "Venus": 3,
                "Mars": 5,
                "Jupiter": 6,
                "Saturn": 7,
            },
            provenance="existing_visible_signs",
        )

        self.assertIsInstance(payload, dict)
        sources = payload.get("source_by_field", {})
        self.assertEqual(chart_records.FIELD_SOURCE_PLAYER, sources.get("sun_sign_index"))
        self.assertEqual(chart_records.FIELD_SOURCE_PLAYER, sources.get("moon_sign_index"))
        self.assertEqual(chart_records.FIELD_SOURCE_DERIVED, sources.get("house_by_body"))

    def test_seed_teen_snapshots_rebuilds_chart_record_for_already_captured_sim(self):
        service = _FakeTransitService()
        sim_info = _FakeSimInfo(4321)
        capture_flag_id = 9001
        sun_trait_id = 100
        moon_trait_id = 200

        cache = {
            "available_by_body_house": {(body, house): object() for body in chart_records.BODY_NAMES for house in range(12)},
            "candidate_ids_by_body": {},
            "planet_house_candidate_ids": set(),
            "sun_sign_trait_by_index": {index: object() for index in range(12)},
            "moon_sign_trait_by_index": {index: object() for index in range(12)},
            "sign_candidate_ids_by_body": {"Sun": {sun_trait_id}, "Moon": {moon_trait_id}},
            "visible_sun_reward_trait_by_index": {},
            "visible_moon_reward_trait_by_index": {},
            "visible_sign_reward_candidate_ids_by_body": {},
            "hidden_chart_ruler_body_by_trait_id": {},
            "visible_chart_ruler_reward_trait_by_body": {},
            "visible_chart_ruler_reward_body_by_trait_id": {},
            "personality_rising_trait_by_index": {},
            "rising_marker_trait_by_index": {},
            "rising_personality_sign_index_by_trait_id": {},
            "rising_marker_sign_index_by_trait_id": {},
            "capture_flag_trait": object(),
            "capture_flag_trait_id": capture_flag_id,
        }
        chart_body_signs = {
            "Sun": 0,
            "Moon": 1,
            "Mercury": 2,
            "Venus": 3,
            "Mars": 4,
            "Jupiter": 5,
            "Saturn": 6,
        }

        with mock.patch.object(natal_snapshot_markers, "_marker_cache", return_value=cache), mock.patch.object(
            natal_snapshot_markers,
            "_iter_household_sim_infos_by_id",
            return_value=(sim_info,),
        ), mock.patch.object(natal_snapshot_markers, "_is_teen_or_older", return_value=True), mock.patch.object(
            natal_snapshot_markers,
            "_collect_trait_ids_and_markers",
            return_value=([capture_flag_id, sun_trait_id, moon_trait_id], []),
        ), mock.patch.object(
            natal_snapshot_markers,
            "_equipped_traits_with_ids",
            return_value=[(object(), capture_flag_id), (object(), sun_trait_id), (object(), moon_trait_id)],
        ), mock.patch.object(
            natal_snapshot_markers,
            "_reconcile_rising_marker_guard",
            return_value={},
        ), mock.patch.object(
            natal_snapshot_markers,
            "_reconcile_visible_chart_ruler_rewards",
            return_value={},
        ), mock.patch.object(
            natal_snapshot_markers,
            "_build_house_sign_map_for_sim",
            return_value={index: index for index in range(12)},
        ), mock.patch.object(
            natal_snapshot_markers,
            "_complete_chart_body_sign_indexes_from_existing_traits",
            return_value=chart_body_signs,
        ):
            summary = natal_snapshot_markers.seed_active_household_teen_cosmic_natal_snapshots(
                active_household_id=55,
                transit_service=service,
            )

        self.assertEqual(1, summary.get("skipped_already_captured"))
        self.assertEqual(1, len(service.saved))
        self.assertEqual(4321, service.saved[0][0])
        self.assertEqual(0, service.saved[0][1].get("sun_sign_index"))


if __name__ == "__main__":
    unittest.main()
