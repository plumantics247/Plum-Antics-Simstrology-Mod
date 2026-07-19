import importlib
import pathlib
import sys
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[1]
PYTHON_DIR = ROOT / "python"
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))


seed = importlib.import_module("cosmic_engine.sign_compatibility_runtime_seed")
runtime_install = importlib.import_module("cosmic_engine.ts4_runtime_install")


class FakeSimInfo:
    def __init__(self, sim_id, age=8, chart_payload=None, traits=None):
        self.id = sim_id
        self.sim_id = sim_id
        self.guid64 = sim_id
        self.age = age
        self.chart_payload = chart_payload or {}
        self._trait_ids = set(traits or ())


def _sync_for_fake(sim_info, existing_seed_record=None):
    return seed.sync_sign_compatibility_preferences_for_sim_info(
        sim_info,
        existing_seed_record=existing_seed_record,
        read_chart_payload=lambda sim: dict(sim.chart_payload),
        iter_trait_ids=lambda sim: tuple(sim._trait_ids),
        add_trait_id=lambda sim, trait_id: sim._trait_ids.add(int(trait_id)),
        remove_trait_id=lambda sim, trait_id: sim._trait_ids.discard(int(trait_id)),
        clear_runtime_lane_state=None,
    )


class SignCompatibilityHouseholdSeedTests(unittest.TestCase):
    def test_initial_seed_adds_hidden_and_ea_owned_traits(self):
        sim_info = FakeSimInfo(
            12345,
            chart_payload={
                "sun_sign_index": 0,
                "moon_sign_index": 4,
                "rising_sign_index": 8,
            },
        )
        summary = _sync_for_fake(sim_info, existing_seed_record=None)
        self.assertEqual("initial_seed", summary["reason"])
        self.assertEqual("0:4:8", summary["seed_record"]["chart_signature"])
        owned_slot_ids = [
            trait_id
            for lane_name in ("Sun", "Moon", "Rising")
            for slot_name in ("auto_like_trait_ids", "auto_dislike_trait_ids")
            for trait_id in summary["seed_record"]["lanes"][lane_name][slot_name]
        ] + [
            summary["seed_record"]["lanes"][lane_name]["ea_like_trait_id"]
            for lane_name in ("Sun", "Moon", "Rising")
        ] + [
            summary["seed_record"]["lanes"][lane_name]["ea_dislike_trait_id"]
            for lane_name in ("Sun", "Moon", "Rising")
        ] + [
            summary["seed_record"]["lanes"][lane_name]["ea_attraction_turn_on_trait_id"]
            for lane_name in ("Sun", "Moon", "Rising")
            if summary["seed_record"]["lanes"][lane_name].get("ea_attraction_turn_on_trait_id") is not None
        ] + [
            summary["seed_record"]["lanes"][lane_name]["ea_attraction_turn_off_trait_id"]
            for lane_name in ("Sun", "Moon", "Rising")
            if summary["seed_record"]["lanes"][lane_name].get("ea_attraction_turn_off_trait_id") is not None
        ]
        self.assertEqual(26, len(owned_slot_ids))
        self.assertEqual(set(summary["seed_record"]["trait_ids_flat"]), sim_info._trait_ids)

    def test_moon_change_replaces_only_moon_owned_defaults_and_attraction_traits(self):
        existing = seed.build_expected_sign_compatibility_seed_record(
            sun_sign_index=0,
            moon_sign_index=0,
            rising_sign_index=8,
        )
        sim_info = FakeSimInfo(
            12345,
            chart_payload={
                "sun_sign_index": 0,
                "moon_sign_index": 11,
                "rising_sign_index": 8,
            },
            traits=set(existing["trait_ids_flat"]) | {4100020001, 9999999999},
        )
        summary = _sync_for_fake(sim_info, existing_seed_record=existing)
        self.assertEqual("chart_changed", summary["reason"])
        self.assertIn(363945, sim_info._trait_ids)
        self.assertIn(363924, sim_info._trait_ids)
        self.assertNotIn(363941, sim_info._trait_ids)
        self.assertNotIn(363942, sim_info._trait_ids)
        self.assertIn(4100020001, sim_info._trait_ids)
        self.assertIn(9999999999, sim_info._trait_ids)

    def test_unchanged_v4_chart_leaves_manual_custom_and_ea_edits_alone(self):
        existing = seed.build_expected_sign_compatibility_seed_record(
            sun_sign_index=0,
            moon_sign_index=4,
            rising_sign_index=8,
        )
        sim_info = FakeSimInfo(
            12345,
            chart_payload={
                "sun_sign_index": 0,
                "moon_sign_index": 4,
                "rising_sign_index": 8,
            },
            traits=set(existing["trait_ids_flat"]) | {4100020011, 4100030002, 9999999999, 306488},
        )
        summary = _sync_for_fake(sim_info, existing_seed_record=existing)
        self.assertEqual("chart_unchanged", summary["reason"])
        self.assertIn(4100020011, sim_info._trait_ids)
        self.assertIn(4100030002, sim_info._trait_ids)
        self.assertIn(9999999999, sim_info._trait_ids)
        self.assertIn(306488, sim_info._trait_ids)

    def test_initial_seed_preserves_preexisting_unowned_ea_preferences(self):
        sim_info = FakeSimInfo(
            12345,
            chart_payload={
                "sun_sign_index": 0,
                "moon_sign_index": 4,
                "rising_sign_index": 8,
            },
            traits={305965, 306488},
        )
        summary = _sync_for_fake(sim_info, existing_seed_record=None)
        self.assertEqual("initial_seed", summary["reason"])
        self.assertIn(305965, sim_info._trait_ids)
        self.assertIn(306488, sim_info._trait_ids)
        self.assertEqual(len(set(summary["seed_record"]["trait_ids_flat"])) + 2, len(sim_info._trait_ids))

    def test_sun_change_replaces_only_sun_owned_defaults(self):
        existing = seed.build_expected_sign_compatibility_seed_record(
            sun_sign_index=0,
            moon_sign_index=4,
            rising_sign_index=8,
        )
        sim_info = FakeSimInfo(
            12345,
            chart_payload={
                "sun_sign_index": 1,
                "moon_sign_index": 4,
                "rising_sign_index": 8,
            },
            traits=set(existing["trait_ids_flat"]) | {4100120005, 4100130004, 8888888888},
        )
        summary = _sync_for_fake(sim_info, existing_seed_record=existing)
        self.assertEqual("chart_changed", summary["reason"])
        self.assertIn(4100020002, sim_info._trait_ids)
        self.assertIn(4100020006, sim_info._trait_ids)
        self.assertIn(4100020010, sim_info._trait_ids)
        self.assertIn(4100030003, sim_info._trait_ids)
        self.assertIn(4100030007, sim_info._trait_ids)
        self.assertIn(4100030011, sim_info._trait_ids)
        self.assertIn(4100120005, sim_info._trait_ids)
        self.assertIn(4100130004, sim_info._trait_ids)
        self.assertIn(8888888888, sim_info._trait_ids)
        self.assertNotIn(4100020001, sim_info._trait_ids)
        self.assertNotIn(4100030012, sim_info._trait_ids)

    def test_sign_change_clears_only_changed_runtime_lane(self):
        existing = seed.build_expected_sign_compatibility_seed_record(
            sun_sign_index=0,
            moon_sign_index=4,
            rising_sign_index=8,
        )
        sim_info = FakeSimInfo(
            12345,
            chart_payload={
                "sun_sign_index": 0,
                "moon_sign_index": 11,
                "rising_sign_index": 8,
            },
            traits=set(existing["trait_ids_flat"]),
        )
        cleared = []
        summary = seed.sync_sign_compatibility_preferences_for_sim_info(
            sim_info,
            existing_seed_record=existing,
            read_chart_payload=lambda sim: dict(sim.chart_payload),
            iter_trait_ids=lambda sim: tuple(sim._trait_ids),
            add_trait_id=lambda sim, trait_id: sim._trait_ids.add(int(trait_id)),
            remove_trait_id=lambda sim, trait_id: sim._trait_ids.discard(int(trait_id)),
            clear_runtime_lane_state=lambda sim, lane_name: cleared.append(
                (int(sim.sim_id), str(lane_name))
            ) or {"ok": True, "reason": "cleared"},
        )
        self.assertEqual("chart_changed", summary["reason"])
        self.assertEqual([(12345, "Moon")], cleared)

    def test_unchanged_chart_does_not_clear_runtime_lanes(self):
        existing = seed.build_expected_sign_compatibility_seed_record(
            sun_sign_index=0,
            moon_sign_index=4,
            rising_sign_index=8,
        )
        sim_info = FakeSimInfo(
            12345,
            chart_payload={
                "sun_sign_index": 0,
                "moon_sign_index": 4,
                "rising_sign_index": 8,
            },
            traits=set(existing["trait_ids_flat"]),
        )
        cleared = []
        summary = seed.sync_sign_compatibility_preferences_for_sim_info(
            sim_info,
            existing_seed_record=existing,
            read_chart_payload=lambda sim: dict(sim.chart_payload),
            iter_trait_ids=lambda sim: tuple(sim._trait_ids),
            add_trait_id=lambda sim, trait_id: sim._trait_ids.add(int(trait_id)),
            remove_trait_id=lambda sim, trait_id: sim._trait_ids.discard(int(trait_id)),
            clear_runtime_lane_state=lambda sim, lane_name: cleared.append(
                (int(sim.sim_id), str(lane_name))
            ) or {"ok": True, "reason": "cleared"},
        )
        self.assertEqual("chart_unchanged", summary["reason"])
        self.assertEqual([], cleared)

    def test_missing_big3_clears_managed_traits_and_runtime_lanes_when_seed_exists(self):
        existing = seed.build_expected_sign_compatibility_seed_record(
            sun_sign_index=0,
            moon_sign_index=4,
            rising_sign_index=8,
        )
        sim_info = FakeSimInfo(
            12345,
            chart_payload={
                "sun_sign_index": 0,
                "moon_sign_index": 4,
            },
            traits=set(existing["trait_ids_flat"]) | {9999999999},
        )
        cleared = []
        summary = seed.sync_sign_compatibility_preferences_for_sim_info(
            sim_info,
            existing_seed_record=existing,
            read_chart_payload=lambda sim: dict(sim.chart_payload),
            iter_trait_ids=lambda sim: tuple(sim._trait_ids),
            add_trait_id=lambda sim, trait_id: sim._trait_ids.add(int(trait_id)),
            remove_trait_id=lambda sim, trait_id: sim._trait_ids.discard(int(trait_id)),
            clear_runtime_lane_state=lambda sim, lane_name: cleared.append(
                (int(sim.sim_id), str(lane_name))
            ) or {"ok": True, "reason": "cleared"},
        )
        self.assertTrue(summary["ok"])
        self.assertEqual("cleared_missing_big3", summary["reason"])
        self.assertEqual({9999999999}, sim_info._trait_ids)
        self.assertEqual(
            [
                (12345, "Sun"),
                (12345, "Moon"),
                (12345, "Rising"),
            ],
            cleared,
        )

    def test_missing_big3_or_underage_sim_is_skipped(self):
        child = FakeSimInfo(
            1,
            age=4,
            chart_payload={
                "sun_sign_index": 0,
                "moon_sign_index": 4,
                "rising_sign_index": 8,
            },
        )
        missing = FakeSimInfo(
            2,
            age=8,
            chart_payload={"sun_sign_index": 0, "moon_sign_index": 4},
        )
        child_summary = _sync_for_fake(child, existing_seed_record=None)
        missing_summary = _sync_for_fake(missing, existing_seed_record=None)
        self.assertEqual("ineligible_age", child_summary["reason"])
        self.assertEqual("missing_big3", missing_summary["reason"])

    def test_household_sync_aggregates_seed_refresh_unchanged_and_skip_counts(self):
        seed_sim = FakeSimInfo(
            1,
            chart_payload={"sun_sign_index": 0, "moon_sign_index": 4, "rising_sign_index": 8},
        )
        refresh_existing = seed.build_expected_sign_compatibility_seed_record(
            sun_sign_index=0,
            moon_sign_index=4,
            rising_sign_index=8,
        )
        refresh_sim = FakeSimInfo(
            2,
            chart_payload={"sun_sign_index": 1, "moon_sign_index": 4, "rising_sign_index": 8},
            traits=set(refresh_existing["trait_ids_flat"]),
        )
        unchanged_existing = seed.build_expected_sign_compatibility_seed_record(
            sun_sign_index=2,
            moon_sign_index=6,
            rising_sign_index=10,
        )
        unchanged_sim = FakeSimInfo(
            3,
            chart_payload={"sun_sign_index": 2, "moon_sign_index": 6, "rising_sign_index": 10},
            traits=set(unchanged_existing["trait_ids_flat"]) | {9999999999},
        )
        skipped_child = FakeSimInfo(
            4,
            age=4,
            chart_payload={"sun_sign_index": 0, "moon_sign_index": 4, "rising_sign_index": 8},
        )
        records = {
            "2": refresh_existing,
            "3": unchanged_existing,
        }
        persisted = {}

        summary = seed.sync_active_household_sign_compatibility_preferences(
            sim_infos=(seed_sim, refresh_sim, unchanged_sim, skipped_child),
            load_seed_record_for_sim=lambda sim_id: records.get(str(int(sim_id))),
            persist_seed_record_for_sim=lambda sim_id, record: persisted.__setitem__(str(int(sim_id)), dict(record)) or True,
            read_chart_payload=lambda sim: dict(sim.chart_payload),
            iter_trait_ids=lambda sim: tuple(sim._trait_ids),
            add_trait_id=lambda sim, trait_id: sim._trait_ids.add(int(trait_id)),
            remove_trait_id=lambda sim, trait_id: sim._trait_ids.discard(int(trait_id)),
            clear_runtime_lane_state=None,
        )

        self.assertTrue(summary["ok"])
        self.assertEqual(4, summary["sims_seen"])
        self.assertEqual(1, summary["sims_seeded"])
        self.assertEqual(1, summary["sims_refreshed"])
        self.assertEqual(1, summary["sims_unchanged"])
        self.assertEqual(1, summary["sims_skipped"])
        self.assertIn("1", persisted)
        self.assertIn("2", persisted)

    def test_household_sync_removes_persisted_seed_when_big3_missing(self):
        existing = seed.build_expected_sign_compatibility_seed_record(
            sun_sign_index=0,
            moon_sign_index=4,
            rising_sign_index=8,
        )
        sim_info = FakeSimInfo(
            77,
            chart_payload={
                "sun_sign_index": 0,
                "moon_sign_index": 4,
            },
            traits=set(existing["trait_ids_flat"]),
        )
        removed = []

        summary = seed.sync_active_household_sign_compatibility_preferences(
            sim_infos=(sim_info,),
            load_seed_record_for_sim=lambda sim_id: existing,
            persist_seed_record_for_sim=lambda sim_id, record: (_ for _ in ()).throw(
                AssertionError("should not persist replacement record when chart is incomplete")
            ),
            remove_seed_record_for_sim=lambda sim_id: removed.append(int(sim_id)) or True,
            read_chart_payload=lambda sim: dict(sim.chart_payload),
            iter_trait_ids=lambda sim: tuple(sim._trait_ids),
            add_trait_id=lambda sim, trait_id: sim._trait_ids.add(int(trait_id)),
            remove_trait_id=lambda sim, trait_id: sim._trait_ids.discard(int(trait_id)),
            clear_runtime_lane_state=None,
        )

        self.assertTrue(summary["ok"])
        self.assertEqual(1, summary["sims_refreshed"])
        self.assertEqual([77], removed)
        self.assertEqual(set(), sim_info._trait_ids)


class SignCompatibilityRuntimeHookTests(unittest.TestCase):
    def test_runtime_chart_payload_prefers_live_traits_over_stale_cached_chart(self):
        loot_actions = importlib.import_module("cosmic_engine.loot_actions")

        class FakeTrait:
            def __init__(self, name):
                self.name = name

        fake_sim = FakeSimInfo(
            12345,
            chart_payload={},
        )
        fake_sim.trait_tracker = None

        original_payload = loot_actions._chart_payload_for_sim
        original_iter_traits = loot_actions._iter_traits_for_sim_info
        original_rising = loot_actions._resolve_rising_sign_index_and_name
        try:
            loot_actions._chart_payload_for_sim = lambda sim_id, sim_info=None: {
                "sun_sign_index": 0,
                "moon_sign_index": 0,
                "rising_sign_index": 0,
            }
            loot_actions._iter_traits_for_sim_info = lambda sim_info: (
                FakeTrait("PlumAntics_CosmicEngineCore_AquariusSunHidden"),
                FakeTrait("PlumAntics_CosmicEngineCore_LibraMoonHidden"),
            )
            loot_actions._resolve_rising_sign_index_and_name = lambda sim_info: (11, "Pisces")

            payload = runtime_install._read_sign_compatibility_chart_payload(fake_sim)
        finally:
            loot_actions._chart_payload_for_sim = original_payload
            loot_actions._iter_traits_for_sim_info = original_iter_traits
            loot_actions._resolve_rising_sign_index_and_name = original_rising

        self.assertEqual(
            {
                "sun_sign_index": 10,
                "moon_sign_index": 6,
                "rising_sign_index": 11,
            },
            payload,
        )

    def test_runtime_hook_skips_without_active_household(self):
        with mock.patch(
            "cosmic_engine.ts4_runtime_install._get_active_household_id",
            return_value=None,
        ):
            summary = runtime_install._maybe_run_sign_compatibility_household_seed(
                reason="zone_init"
            )
        self.assertEqual("missing_household", summary["reason"])

    def test_runtime_hook_routes_household_seed_through_astrocore_bridge(self):
        with mock.patch(
            "cosmic_engine.ts4_runtime_install._get_active_household_id",
            return_value=12345,
        ), mock.patch(
            "cosmic_engine.ts4_runtime_install._iter_active_household_sim_infos",
            return_value=(object(), object()),
        ), mock.patch(
            "cosmic_engine.ts4_runtime_install.dispatch_household_onboard",
            return_value={
                "ok": True,
                "addon_summaries": {
                    "compatibility_household": {
                        "ok": True,
                        "reason": "processed",
                        "sims_seeded": 2,
                    }
                },
            },
        ) as dispatch_mock:
            summary = runtime_install._maybe_run_sign_compatibility_household_seed(
                reason="zone_init"
            )
        self.assertTrue(summary["ok"])
        dispatch_mock.assert_called_once_with(12345, refresh_marker_cache=False)
        self.assertEqual(2, summary["refresh_summary"]["sims_seeded"])

    def test_runtime_hook_fail_closed_on_bridge_exception(self):
        with mock.patch(
            "cosmic_engine.ts4_runtime_install._get_active_household_id",
            return_value=12345,
        ), mock.patch(
            "cosmic_engine.ts4_runtime_install._iter_active_household_sim_infos",
            return_value=(object(),),
        ), mock.patch(
            "cosmic_engine.ts4_runtime_install.dispatch_household_onboard",
            side_effect=RuntimeError("boom"),
        ):
            summary = runtime_install._maybe_run_sign_compatibility_household_seed(
                reason="zone_init"
            )
        self.assertEqual("seed_failed", summary["reason"])


if __name__ == "__main__":
    unittest.main()
