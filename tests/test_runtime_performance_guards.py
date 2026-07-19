import copy
import importlib
import pathlib
import sys
import unittest


sys.dont_write_bytecode = True

ROOT = pathlib.Path(__file__).resolve().parents[1]
PYTHON_DIR = ROOT / "python"
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))


runtime = importlib.import_module("cosmic_engine.ts4_runtime_install")
transit_service = importlib.import_module("cosmic_engine.transit_service")


class RuntimePerformanceGuardTests(unittest.TestCase):
    def setUp(self):
        self._state = copy.deepcopy(runtime._RUNTIME_STATE)

    def tearDown(self):
        runtime._RUNTIME_STATE.clear()
        runtime._RUNTIME_STATE.update(self._state)

    def test_services_probe_hooks_patch_only_time_service_and_throttle_recovery(self):
        class FakeZone(object):
            def is_zone_running(self):
                return True

        class FakeServices(object):
            def __init__(self):
                self._zone = FakeZone()

            def current_zone(self):
                return self._zone

            def time_service(self):
                return object()

        fake_services = FakeServices()
        original_current_zone = FakeServices.current_zone
        original_time_service = FakeServices.time_service
        original_get_services = runtime._get_services_module
        original_hooks_enabled = runtime._SERVICES_PROBE_HOOKS_ENABLED
        original_interval = getattr(runtime, "_SERVICES_PROBE_MIN_CHECK_REAL_SECONDS", 5.0)
        original_monotonic = runtime.time.monotonic
        original_tick = runtime._perform_runtime_tick
        original_retry = runtime._ensure_runtime_retry_surfaces
        call_reasons = []
        monotonic_values = iter((10.0, 10.1, 10.2, 16.2, 16.3, 16.4))
        try:
            runtime._get_services_module = lambda: fake_services
            runtime._SERVICES_PROBE_HOOKS_ENABLED = True
            runtime._SERVICES_PROBE_MIN_CHECK_REAL_SECONDS = 5.0
            runtime._RUNTIME_STATE["services_probe_patched"] = False
            runtime._RUNTIME_STATE["initialized"] = True
            runtime._RUNTIME_STATE["startup_retro_catchup_completed"] = True
            runtime._RUNTIME_STATE["last_runtime_tick_real_seconds"] = 0.0
            runtime._RUNTIME_STATE["last_services_probe_check_real_seconds"] = None
            runtime.time.monotonic = lambda: next(monotonic_values)
            runtime._ensure_runtime_retry_surfaces = lambda: None
            runtime._perform_runtime_tick = lambda *args, **kwargs: call_reasons.append(kwargs.get("reason"))

            patched = runtime._register_services_probe_hooks()
            fake_services.time_service()
            fake_services.time_service()
            fake_services.time_service()

            self.assertTrue(patched)
            self.assertTrue(runtime._RUNTIME_STATE["services_probe_patched"])
            self.assertIs(FakeServices.current_zone, original_current_zone)
            self.assertIs(FakeServices.time_service, original_time_service)
            self.assertFalse(getattr(fake_services.current_zone, "_cosmic_engine_patched", False))
            self.assertTrue(getattr(fake_services.time_service, "_cosmic_engine_patched", False))
            self.assertEqual(
                ["services.time_service_stale_runtime", "services.time_service_stale_runtime"],
                call_reasons,
            )
        finally:
            runtime._get_services_module = original_get_services
            runtime._SERVICES_PROBE_HOOKS_ENABLED = original_hooks_enabled
            runtime._SERVICES_PROBE_MIN_CHECK_REAL_SECONDS = original_interval
            runtime.time.monotonic = original_monotonic
            runtime._perform_runtime_tick = original_tick
            runtime._ensure_runtime_retry_surfaces = original_retry

    def test_runtime_tick_skips_when_already_inflight(self):
        tick_calls = []
        original_ensure = runtime._ensure_initialized
        original_get_mode_lock = runtime.get_mode_lock
        original_get_time_service = runtime._get_time_service
        original_tick_from_time_service = runtime._tick_from_time_service
        original_run_startup = runtime._run_startup_retro_catchup
        try:
            runtime._ensure_initialized = lambda *args, **kwargs: None
            runtime.get_mode_lock = lambda: "cosmic"
            runtime._get_time_service = lambda: object()
            runtime._tick_from_time_service = lambda svc: tick_calls.append(svc)
            runtime._run_startup_retro_catchup = lambda **kwargs: {"ok": True}
            runtime._RUNTIME_STATE["startup_retro_catchup_completed"] = True
            runtime._RUNTIME_STATE["runtime_tick_inflight"] = True

            result = runtime._perform_runtime_tick(reason="runtime_realtime_alarm")

            self.assertFalse(result)
            self.assertEqual([], tick_calls)
        finally:
            runtime._ensure_initialized = original_ensure
            runtime.get_mode_lock = original_get_mode_lock
            runtime._get_time_service = original_get_time_service
            runtime._tick_from_time_service = original_tick_from_time_service
            runtime._run_startup_retro_catchup = original_run_startup

    def test_no_change_clock_tick_does_not_flush_fallback_full_zone_scopes(self):
        class FakeNow(object):
            absolute_days = 42

        class FakeTimeService(object):
            sim_now = FakeNow()

        replacements = {
            "_ensure_initialized": lambda *args, **kwargs: None,
            "_update_ready_sim_count_state": lambda: (False, False),
            "_resolve_total_segments_elapsed": lambda: 7,
            "_extract_season_segment_pair": lambda: (2, 1),
            "_resolve_lunar_cycle_days": lambda: 8.0,
            "_resolve_sim_days_per_year": lambda: 28.0,
            "on_clock_snapshot": lambda **kwargs: {},
            "_count_instanced_sims": lambda: 3,
            "get_mode_lock": lambda: "big3",
            "_route_retrograde_notifications": lambda **kwargs: None,
        }
        originals = {name: getattr(runtime, name) for name in replacements}
        flush_calls = []

        def record_flush(*args, **kwargs):
            flush_calls.append((args, kwargs))
            return {"ok": True, "executed_scopes": ()}

        original_flush = runtime._flush_dirty_sync_queue
        original_queue = runtime._queue_runtime_scopes
        try:
            for name, value in replacements.items():
                setattr(runtime, name, value)
            runtime._flush_dirty_sync_queue = record_flush
            runtime._queue_runtime_scopes = lambda *args, **kwargs: None
            runtime._RUNTIME_STATE["startup_retro_catchup_completed"] = True
            runtime._RUNTIME_STATE["last_instanced_sim_count"] = 3
            runtime._RUNTIME_STATE["marker_sync_tick_counter"] = 1

            runtime._tick_from_time_service(FakeTimeService())

            self.assertEqual([], flush_calls)
        finally:
            for name, value in originals.items():
                setattr(runtime, name, value)
            runtime._flush_dirty_sync_queue = original_flush
            runtime._queue_runtime_scopes = original_queue

    def test_same_day_progress_advances_day_based_retrogrades(self):
        service = transit_service.CosmicTransitService()
        service.initialize(seed=123)
        service._retrograde_state_by_body = {
            "Mercury": {"unit": "day", "active": False, "remaining": 5.0},
        }
        service._last_total_days_seen = 10
        service._last_total_day_progress_seen = 10.0
        service._last_total_segments_seen = 2

        service.advance_from_totals(
            total_days_elapsed=10,
            total_day_progress_elapsed=10.25,
            total_segments_elapsed=2,
        )

        payload = service.retrograde_debug_payload()
        mercury = payload.get("bodies", {}).get("Mercury", {})
        self.assertAlmostEqual(4.75, mercury.get("remaining"))

    def test_one_sim_day_advances_moon_by_one_sign_in_runtime_service(self):
        service = transit_service.CosmicTransitService()
        service.initialize(seed=123)
        start_sign = int(service.state.sign_index_by_body["Moon"])
        service.advance_from_totals(
            total_days_elapsed=0,
            total_day_progress_elapsed=0.0,
            total_segments_elapsed=0,
        )

        moved = service.advance_from_totals(
            total_days_elapsed=1,
            total_day_progress_elapsed=1.0,
            total_segments_elapsed=0,
        )

        self.assertEqual(1, moved.get("Moon"))
        self.assertEqual((start_sign + 1) % 12, service.state.sign_index_by_body["Moon"])
        self.assertAlmostEqual(0.0, service.get_moon_progress_fraction())

    def test_retrograde_debug_payload_reports_updated_saturn_segment_spec(self):
        service = transit_service.CosmicTransitService()
        service.initialize(seed=123)

        payload = service.retrograde_debug_payload()
        saturn = payload.get("bodies", {}).get("Saturn", {})

        self.assertEqual("segment", saturn.get("unit"))
        self.assertAlmostEqual(15.0, saturn.get("start_interval"))
        self.assertAlmostEqual(5.0, saturn.get("duration"))

    def test_social_complete_hooks_patch_trigger_interaction_complete_and_refresh_pair_chemistry(self):
        class FakeSocialSuperInteraction(object):
            def __init__(self, sim=None, target=None):
                self.sim = sim
                self.target = target

            def _trigger_interaction_complete(self, *args, **kwargs):
                return {
                    "args": args,
                    "kwargs": kwargs,
                }

        class FakeSimInfo(object):
            def __init__(self, sim_id):
                self.sim_id = int(sim_id)

        class FakeSim(object):
            def __init__(self, sim_info):
                self.sim_info = sim_info

        fake_module = type("FakeSocialModule", (), {})()
        fake_module.SocialSuperInteraction = FakeSocialSuperInteraction

        original_import_module = runtime.importlib.import_module
        loot_actions = importlib.import_module("cosmic_engine.loot_actions")
        original_refresh = loot_actions.refresh_chemistry_after_completed_social
        retrograde_effects = importlib.import_module("cosmic_engine.retrograde_effects")
        original_dispatch = retrograde_effects.on_completed_interaction
        calls = []
        retrograde_effect_calls = []
        actor = FakeSim(FakeSimInfo(111))
        target = FakeSim(FakeSimInfo(222))

        try:
            runtime._RUNTIME_STATE["social_complete_patched"] = False
            runtime.importlib.import_module = (
                lambda name: fake_module
                if name == "interactions.social.social_super_interaction"
                else original_import_module(name)
            )
            loot_actions.refresh_chemistry_after_completed_social = (
                lambda actor_sim_info, target_sim_info, source="runtime.social_complete": calls.append(
                    (
                        actor_sim_info,
                        target_sim_info,
                        source,
                    )
                ) or {"ok": True}
            )
            retrograde_effects.on_completed_interaction = (
                lambda completed_interaction: retrograde_effect_calls.append(completed_interaction)
                or {"handled": False, "reason": "test"}
            )

            patched = runtime._register_social_complete_hooks()
            interaction = FakeSocialSuperInteraction(sim=actor, target=target)
            result = interaction._trigger_interaction_complete(1, key="value")

            self.assertTrue(patched)
            self.assertTrue(runtime._RUNTIME_STATE["social_complete_patched"])
            self.assertTrue(
                getattr(
                    FakeSocialSuperInteraction._trigger_interaction_complete,
                    "_cosmic_engine_patched",
                    False,
                )
            )
            self.assertEqual({"args": (1,), "kwargs": {"key": "value"}}, result)
            self.assertEqual(
                [(actor.sim_info, target.sim_info, "runtime.social_complete")],
                calls,
            )
            self.assertEqual([interaction], retrograde_effect_calls)
        finally:
            runtime.importlib.import_module = original_import_module
            loot_actions.refresh_chemistry_after_completed_social = original_refresh
            retrograde_effects.on_completed_interaction = original_dispatch

    def test_install_runtime_hooks_reports_social_complete_patch_result(self):
        class FakeSocialSuperInteraction(object):
            def _trigger_interaction_complete(self, *args, **kwargs):
                return {"args": args, "kwargs": kwargs}

        fake_module = type("FakeSocialModule", (), {})()
        fake_module.SocialSuperInteraction = FakeSocialSuperInteraction

        original_import_module = runtime.importlib.import_module
        original_register_callbacks = runtime._register_runtime_callbacks
        original_register_zone_manager = runtime._register_zone_manager_bootstrap_callback
        original_register_zone = runtime._register_zone_bootstrap_callback
        original_register_services_probe = runtime._register_services_probe_hooks
        original_is_zone_running = runtime._is_current_zone_running
        original_schedule_retry = runtime._schedule_runtime_install_retry

        try:
            runtime._RUNTIME_STATE["installed"] = False
            runtime._RUNTIME_STATE["social_complete_patched"] = False
            runtime.importlib.import_module = (
                lambda name: fake_module
                if name == "interactions.social.social_super_interaction"
                else (_ for _ in ()).throw(ModuleNotFoundError(name))
            )
            runtime._register_runtime_callbacks = lambda: False
            runtime._register_zone_manager_bootstrap_callback = lambda: False
            runtime._register_zone_bootstrap_callback = lambda: False
            runtime._register_services_probe_hooks = lambda: False
            runtime._is_current_zone_running = lambda: False
            runtime._schedule_runtime_install_retry = lambda *args, **kwargs: False

            installed = runtime.install_runtime_hooks()
            install_result = runtime._RUNTIME_STATE.get("last_install_result", {})

            self.assertTrue(installed)
            self.assertTrue(runtime._RUNTIME_STATE["social_complete_patched"])
            self.assertTrue(install_result.get("social_complete_patched"))
        finally:
            runtime.importlib.import_module = original_import_module
            runtime._register_runtime_callbacks = original_register_callbacks
            runtime._register_zone_manager_bootstrap_callback = original_register_zone_manager
            runtime._register_zone_bootstrap_callback = original_register_zone
            runtime._register_services_probe_hooks = original_register_services_probe
            runtime._is_current_zone_running = original_is_zone_running
            runtime._schedule_runtime_install_retry = original_schedule_retry

    def test_social_complete_hooks_search_fallback_candidates_for_trigger_interaction_complete(self):
        class FakeSocialMixerInteraction(object):
            def _trigger_interaction_complete(self, *args, **kwargs):
                return {"args": args, "kwargs": kwargs}

        class FakeSuperInteraction(object):
            def _trigger_interaction_complete(self, *args, **kwargs):
                return {"args": args, "kwargs": kwargs}

        mixer_module = type("FakeMixerModule", (), {})()
        mixer_module.SocialMixerInteraction = FakeSocialMixerInteraction
        base_module = type("FakeBaseModule", (), {})()
        base_module.SuperInteraction = FakeSuperInteraction

        original_import_module = runtime.importlib.import_module
        loot_actions = importlib.import_module("cosmic_engine.loot_actions")
        original_refresh = loot_actions.refresh_chemistry_after_completed_social
        calls = []
        try:
            runtime._RUNTIME_STATE["social_complete_patched"] = False

            def _fake_import(name):
                if name == "interactions.social.social_super_interaction":
                    raise ModuleNotFoundError(name)
                if name == "interactions.social.social_mixer_interaction":
                    return mixer_module
                if name == "interactions.base.super_interaction":
                    return base_module
                raise ModuleNotFoundError(name)

            runtime.importlib.import_module = _fake_import
            loot_actions.refresh_chemistry_after_completed_social = (
                lambda actor_sim_info, target_sim_info, source="runtime.social_complete": calls.append(source) or {"ok": True}
            )

            patched = runtime._register_social_complete_hooks()
            result = FakeSocialMixerInteraction()._trigger_interaction_complete()

            self.assertTrue(patched)
            self.assertTrue(runtime._RUNTIME_STATE["social_complete_patched"])
            self.assertTrue(
                getattr(
                    FakeSocialMixerInteraction._trigger_interaction_complete,
                    "_cosmic_engine_patched",
                    False,
                )
            )
            self.assertEqual({"args": (), "kwargs": {}}, result)
            self.assertEqual(["runtime.social_complete"], calls)
        finally:
            runtime.importlib.import_module = original_import_module
            loot_actions.refresh_chemistry_after_completed_social = original_refresh

    def test_social_complete_patch_targets_match_literal_plan_order(self):
        self.assertEqual(
            (
                (
                    "interactions.social.social_super_interaction",
                    "SocialSuperInteraction",
                    "_trigger_interaction_complete",
                ),
                (
                    "interactions.social.social_mixer_interaction",
                    "SocialMixerInteraction",
                    "_trigger_interaction_complete",
                ),
                (
                    "interactions.base.super_interaction",
                    "SuperInteraction",
                    "_trigger_interaction_complete",
                ),
            ),
            runtime._SOCIAL_COMPLETE_PATCH_TARGETS,
        )

    def test_social_complete_super_interaction_fallback_skips_clearly_non_social_instances(self):
        class FakeTargetSim(object):
            def __init__(self):
                self.sim_info = object()

        class FakeSuperInteraction(object):
            __module__ = "interactions.base.super_interaction"

            def __init__(self):
                self.sim = object()
                self.target = FakeTargetSim()

            def _trigger_interaction_complete(self, *args, **kwargs):
                return {"args": args, "kwargs": kwargs}

        base_module = type("FakeBaseModule", (), {})()
        base_module.SuperInteraction = FakeSuperInteraction

        original_import_module = runtime.importlib.import_module
        loot_actions = importlib.import_module("cosmic_engine.loot_actions")
        original_refresh = loot_actions.refresh_chemistry_after_completed_social
        calls = []
        try:
            runtime._RUNTIME_STATE["social_complete_patched"] = False

            def _fake_import(name):
                if name == "interactions.social.social_super_interaction":
                    raise ModuleNotFoundError(name)
                if name == "interactions.social.social_mixer_interaction":
                    raise ModuleNotFoundError(name)
                if name == "interactions.base.super_interaction":
                    return base_module
                raise ModuleNotFoundError(name)

            runtime.importlib.import_module = _fake_import
            loot_actions.refresh_chemistry_after_completed_social = (
                lambda actor_sim_info, target_sim_info, source="runtime.social_complete": calls.append(source) or {"ok": True}
            )

            patched = runtime._register_social_complete_hooks()
            result = FakeSuperInteraction()._trigger_interaction_complete()

            self.assertTrue(patched)
            self.assertEqual({"args": (), "kwargs": {}}, result)
            self.assertEqual([], calls)
        finally:
            runtime.importlib.import_module = original_import_module
            loot_actions.refresh_chemistry_after_completed_social = original_refresh

    def test_runtime_install_surfaces_ready_accepts_social_complete_patch_surface(self):
        runtime._RUNTIME_STATE["initialized"] = False
        runtime._RUNTIME_STATE["callbacks_registered"] = False
        runtime._RUNTIME_STATE["social_complete_patched"] = True
        self.assertTrue(runtime._runtime_install_surfaces_ready())

    def test_runtime_install_exposes_astrocore_bridge_dispatch_helpers(self):
        original_bridge = getattr(runtime, "_ASTROCORE_RUNTIME_BRIDGE", None)
        calls = []

        try:
            runtime._ASTROCORE_RUNTIME_BRIDGE = type(
                "Bridge",
                (),
                {
                    "on_zone_or_save_load": staticmethod(
                        lambda **kwargs: calls.append(("load", dict(kwargs))) or {"ok": True}
                    ),
                    "on_clock_snapshot": staticmethod(
                        lambda **kwargs: calls.append(("periodic", dict(kwargs))) or {"ok": True}
                    ),
                },
            )()

            load_summary = runtime._dispatch_astrocore_load(saved_record={"seed": 1}, fallback_seed=9)
            periodic_summary = runtime._dispatch_astrocore_periodic(12, 48, True)

            self.assertTrue(load_summary["ok"])
            self.assertTrue(periodic_summary["ok"])
            self.assertEqual("load", calls[0][0])
            self.assertEqual("periodic", calls[1][0])
        finally:
            runtime._ASTROCORE_RUNTIME_BRIDGE = original_bridge

    def test_clock_tick_routes_runtime_sky_effects_through_astrocore_bridge(self):
        class FakeNow(object):
            absolute_days = 42

        class FakeTimeService(object):
            sim_now = FakeNow()

        bridge_calls = []
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
            "get_mode_lock": lambda: "cosmic",
            "_route_retrograde_notifications": lambda **kwargs: None,
        }
        originals = {name: getattr(runtime, name) for name in replacements}
        original_queue = runtime._queue_runtime_scopes
        original_flush = runtime._flush_dirty_sync_queue
        original_bridge = runtime._ASTROCORE_RUNTIME_BRIDGE
        try:
            for name, value in replacements.items():
                setattr(runtime, name, value)
            runtime._ASTROCORE_RUNTIME_BRIDGE = type(
                "Bridge",
                (),
                {
                    "dispatch_runtime_tick": staticmethod(
                        lambda **kwargs: bridge_calls.append(dict(kwargs)) or {"ok": True}
                    )
                },
            )()
            runtime._queue_runtime_scopes = lambda scopes, **kwargs: queued.append(tuple(scopes)) or {}
            runtime._flush_dirty_sync_queue = lambda **kwargs: {"ok": True}
            runtime._RUNTIME_STATE["startup_retro_catchup_completed"] = True
            runtime._RUNTIME_STATE["last_instanced_sim_count"] = 3
            runtime._RUNTIME_STATE["marker_sync_tick_counter"] = 0

            runtime._tick_from_time_service(FakeTimeService())

            self.assertEqual(1, len(bridge_calls))
            self.assertEqual(1, len(queued))
            self.assertIn(runtime.SCOPE_RISING_BUFFS, queued[0])
            self.assertNotIn(runtime.SCOPE_VISIBLE_SIGN_BUFFS, queued[0])
            self.assertNotIn(runtime.SCOPE_SOLAR_RETURN, queued[0])
            self.assertNotIn(runtime.SCOPE_RETROGRADE_MARKERS, queued[0])
            self.assertNotIn(runtime.SCOPE_RETROGRADE_CONSEQUENCES, queued[0])
        finally:
            for name, value in originals.items():
                setattr(runtime, name, value)
            runtime._queue_runtime_scopes = original_queue
            runtime._flush_dirty_sync_queue = original_flush
            runtime._ASTROCORE_RUNTIME_BRIDGE = original_bridge


if __name__ == "__main__":
    unittest.main()
