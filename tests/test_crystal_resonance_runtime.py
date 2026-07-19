import copy
import importlib
import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
PYTHON_DIR = ROOT / "python"
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))


dirty_sync_queue = importlib.import_module("cosmic_engine.dirty_sync_queue")
runtime = importlib.import_module("cosmic_engine.ts4_runtime_install")


class CrystalResonanceRuntimeTests(unittest.TestCase):
    def setUp(self):
        self._runtime_state = copy.deepcopy(runtime._RUNTIME_STATE)
        self._queue_state = copy.deepcopy(dirty_sync_queue._STATE)

    def tearDown(self):
        runtime._RUNTIME_STATE.clear()
        runtime._RUNTIME_STATE.update(self._runtime_state)
        dirty_sync_queue._STATE.clear()
        dirty_sync_queue._STATE.update(self._queue_state)

    def test_dirty_scope_registry_accepts_crystal_resonance(self):
        summary = dirty_sync_queue.mark_scope_dirty(
            (dirty_sync_queue.SCOPE_CRYSTAL_RESONANCE,),
            sim_id=101,
            reason="test",
        )

        self.assertIn(dirty_sync_queue.SCOPE_CRYSTAL_RESONANCE, summary["marked_scopes"])
        self.assertIn(dirty_sync_queue.SCOPE_CRYSTAL_RESONANCE, dirty_sync_queue.pending_scopes())

    def test_runtime_flush_dispatches_crystal_resonance_scope(self):
        class FakeNow(object):
            absolute_ticks = 321

        class FakeSimInfo(object):
            def __init__(self, sim_id):
                self.sim_id = int(sim_id)
                self.id = int(sim_id)

        calls = []
        original_sync = getattr(runtime, "sync_crystal_resonance", None)
        original_resolve = runtime._resolve_dirty_sim_infos
        original_get_now = runtime._get_sim_now
        try:
            runtime.sync_crystal_resonance = (
                lambda sim_infos=None, now_ticks=0: calls.append((tuple(sim_infos or ()), int(now_ticks))) or {"ok": True}
            )
            runtime._resolve_dirty_sim_infos = lambda sim_ids: tuple(FakeSimInfo(sim_id) for sim_id in sim_ids)
            runtime._get_sim_now = lambda: FakeNow()

            dirty_sync_queue.mark_scope_dirty(
                (dirty_sync_queue.SCOPE_CRYSTAL_RESONANCE,),
                sim_id=111,
                reason="unit_test",
            )

            summary = runtime._flush_dirty_sync_queue(reason="runtime", active_mode="cosmic")

            self.assertEqual(1, len(calls))
            self.assertEqual((111,), tuple(sim.sim_id for sim in calls[0][0]))
            self.assertEqual(321, calls[0][1])
            self.assertIn(dirty_sync_queue.SCOPE_CRYSTAL_RESONANCE, summary["executed_scopes"])
        finally:
            if original_sync is not None:
                runtime.sync_crystal_resonance = original_sync
            else:
                delattr(runtime, "sync_crystal_resonance")
            runtime._resolve_dirty_sim_infos = original_resolve
            runtime._get_sim_now = original_get_now

    def test_runtime_flush_uses_instanced_sims_when_crystal_scope_has_no_target_ids(self):
        class FakeNow(object):
            absolute_ticks = 654

        class FakeSimInfo(object):
            def __init__(self, sim_id):
                self.sim_id = int(sim_id)
                self.id = int(sim_id)

        calls = []
        original_sync = getattr(runtime, "sync_crystal_resonance", None)
        original_iter_instanced = runtime._iter_instanced_sim_infos
        original_get_now = runtime._get_sim_now
        try:
            runtime.sync_crystal_resonance = (
                lambda sim_infos=None, now_ticks=0: calls.append((tuple(sim_infos or ()), int(now_ticks))) or {"ok": True}
            )
            runtime._iter_instanced_sim_infos = lambda: (
                FakeSimInfo(201),
                FakeSimInfo(202),
            )
            runtime._get_sim_now = lambda: FakeNow()

            dirty_sync_queue.mark_scope_dirty(
                (dirty_sync_queue.SCOPE_CRYSTAL_RESONANCE,),
                reason="unit_test_global",
            )

            summary = runtime._flush_dirty_sync_queue(reason="runtime", active_mode="big3")

            self.assertEqual(1, len(calls))
            self.assertEqual((201, 202), tuple(sim.sim_id for sim in calls[0][0]))
            self.assertEqual(654, calls[0][1])
            self.assertIn(dirty_sync_queue.SCOPE_CRYSTAL_RESONANCE, summary["executed_scopes"])
        finally:
            if original_sync is not None:
                runtime.sync_crystal_resonance = original_sync
            else:
                delattr(runtime, "sync_crystal_resonance")
            runtime._iter_instanced_sim_infos = original_iter_instanced
            runtime._get_sim_now = original_get_now

    def test_zone_init_queues_crystal_resonance_scope(self):
        queued = []
        original_resolve_zone_id = runtime._resolve_zone_id
        original_load_record = runtime._load_persisted_transit_record
        original_on_load = runtime.on_zone_or_save_load
        original_reset_visible = runtime.reset_managed_visible_sign_buff_state
        original_reset_rising = runtime.reset_managed_rising_buff_state
        original_prime = runtime._prime_segment_total_from_service_record
        original_cancel = runtime._cancel_runtime_retro_reassert_alarm
        original_count_instanced = runtime._count_instanced_sims
        original_count_ready = runtime._count_ready_sims
        original_active_household_id = runtime._get_active_household_id
        original_active_household_count = runtime._count_active_household_sim_infos
        original_sim_days = runtime._resolve_sim_days_per_year
        original_legacy = runtime._maybe_run_legacy_v2_auto_migration
        original_outer = runtime._maybe_run_outer_planets_household_refresh
        original_sign = runtime._maybe_run_sign_compatibility_household_seed
        original_mode_lock = runtime.get_mode_lock
        original_queue = runtime._queue_runtime_scopes
        original_flush = runtime._flush_dirty_sync_queue
        try:
            runtime._resolve_zone_id = lambda zone_obj=None: 9001
            runtime._load_persisted_transit_record = lambda: {}
            runtime.on_zone_or_save_load = lambda **kwargs: None
            runtime.reset_managed_visible_sign_buff_state = lambda: None
            runtime.reset_managed_rising_buff_state = lambda: None
            runtime._prime_segment_total_from_service_record = lambda: None
            runtime._cancel_runtime_retro_reassert_alarm = lambda: None
            runtime._count_instanced_sims = lambda: 1
            runtime._count_ready_sims = lambda: 1
            runtime._get_active_household_id = lambda: 77
            runtime._count_active_household_sim_infos = lambda: 1
            runtime._resolve_sim_days_per_year = lambda: 28.0
            runtime._maybe_run_legacy_v2_auto_migration = lambda **kwargs: {}
            runtime._maybe_run_outer_planets_household_refresh = lambda **kwargs: {}
            runtime._maybe_run_sign_compatibility_household_seed = lambda **kwargs: {}
            runtime.get_mode_lock = lambda: "big3"
            runtime._queue_runtime_scopes = lambda scopes, **kwargs: queued.append(tuple(scopes)) or {}
            runtime._flush_dirty_sync_queue = lambda **kwargs: {"ok": True}

            runtime._ensure_initialized()

            self.assertEqual(1, len(queued))
            self.assertIn(dirty_sync_queue.SCOPE_CRYSTAL_RESONANCE, queued[0])
        finally:
            runtime._resolve_zone_id = original_resolve_zone_id
            runtime._load_persisted_transit_record = original_load_record
            runtime.on_zone_or_save_load = original_on_load
            runtime.reset_managed_visible_sign_buff_state = original_reset_visible
            runtime.reset_managed_rising_buff_state = original_reset_rising
            runtime._prime_segment_total_from_service_record = original_prime
            runtime._cancel_runtime_retro_reassert_alarm = original_cancel
            runtime._count_instanced_sims = original_count_instanced
            runtime._count_ready_sims = original_count_ready
            runtime._get_active_household_id = original_active_household_id
            runtime._count_active_household_sim_infos = original_active_household_count
            runtime._resolve_sim_days_per_year = original_sim_days
            runtime._maybe_run_legacy_v2_auto_migration = original_legacy
            runtime._maybe_run_outer_planets_household_refresh = original_outer
            runtime._maybe_run_sign_compatibility_household_seed = original_sign
            runtime.get_mode_lock = original_mode_lock
            runtime._queue_runtime_scopes = original_queue
            runtime._flush_dirty_sync_queue = original_flush

    def test_clock_tick_queues_crystal_resonance_scope(self):
        class FakeNow(object):
            absolute_days = 42

        class FakeTimeService(object):
            sim_now = FakeNow()

        queued = []
        replacements = {
            "_ensure_initialized": lambda *args, **kwargs: None,
            "_update_ready_sim_count_state": lambda: (False, False),
            "_resolve_total_days_elapsed": lambda _svc: 42,
            "_resolve_total_day_progress_elapsed": lambda _svc: 42.0,
            "_resolve_total_segments_elapsed": lambda: 7,
            "_extract_season_segment_pair": lambda: (2, 1),
            "_resolve_lunar_cycle_days": lambda: 8.0,
            "_resolve_sim_days_per_year": lambda: 28.0,
            "on_clock_snapshot": lambda **kwargs: {"Moon": 1},
            "_count_instanced_sims": lambda: 3,
            "get_mode_lock": lambda: "big3",
            "_route_retrograde_notifications": lambda **kwargs: None,
        }
        originals = {name: getattr(runtime, name) for name in replacements}
        original_queue = runtime._queue_runtime_scopes
        original_flush = runtime._flush_dirty_sync_queue
        try:
            for name, value in replacements.items():
                setattr(runtime, name, value)
            runtime._queue_runtime_scopes = lambda scopes, **kwargs: queued.append(tuple(scopes)) or {}
            runtime._flush_dirty_sync_queue = lambda **kwargs: {"ok": True}
            runtime._RUNTIME_STATE["startup_retro_catchup_completed"] = True
            runtime._RUNTIME_STATE["last_instanced_sim_count"] = 3
            runtime._RUNTIME_STATE["marker_sync_tick_counter"] = 0

            runtime._tick_from_time_service(FakeTimeService())

            self.assertEqual(1, len(queued))
            self.assertIn(dirty_sync_queue.SCOPE_CRYSTAL_RESONANCE, queued[0])
        finally:
            for name, value in originals.items():
                setattr(runtime, name, value)
            runtime._queue_runtime_scopes = original_queue
            runtime._flush_dirty_sync_queue = original_flush


if __name__ == "__main__":
    unittest.main()
