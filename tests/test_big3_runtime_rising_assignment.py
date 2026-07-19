import pathlib
import sys
import types
import unittest
from types import SimpleNamespace


ROOT = pathlib.Path(__file__).resolve().parents[1]
PYTHON_DIR = ROOT / "python"
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))

from plumantics_big3_runtime.integration import rising_assignment


class RisingRuntimeAssignmentTests(unittest.TestCase):
    def test_sun_time_bucket_offsets_match_legacy_xml(self):
        self.assertEqual(
            {
                6: 0,
                8: 1,
                10: 2,
                12: 3,
                14: 4,
                16: 5,
                18: 6,
                20: 7,
                22: 8,
                0: 9,
                2: 10,
                4: 11,
            },
            rising_assignment.RISING_SUN_TIME_BUCKETS,
        )

    def test_aries_sun_resolves_expected_rising_signs_across_day(self):
        self.assertEqual(0, rising_assignment.resolve_rising_sign_index_for_sun_time(0, 6))
        self.assertEqual(1, rising_assignment.resolve_rising_sign_index_for_sun_time(0, 8))
        self.assertEqual(2, rising_assignment.resolve_rising_sign_index_for_sun_time(0, 10))
        self.assertEqual(3, rising_assignment.resolve_rising_sign_index_for_sun_time(0, 12))
        self.assertEqual(8, rising_assignment.resolve_rising_sign_index_for_sun_time(0, 22))
        self.assertEqual(9, rising_assignment.resolve_rising_sign_index_for_sun_time(0, 0))
        self.assertEqual(10, rising_assignment.resolve_rising_sign_index_for_sun_time(0, 2))
        self.assertEqual(11, rising_assignment.resolve_rising_sign_index_for_sun_time(0, 4))

    def test_resolution_wraps_for_late_signs(self):
        self.assertEqual(0, rising_assignment.resolve_rising_sign_index_for_sun_time(11, 8))
        self.assertEqual(2, rising_assignment.resolve_rising_sign_index_for_sun_time(11, 12))
        self.assertEqual(8, rising_assignment.resolve_rising_sign_index_for_sun_time(11, 0))

    def test_assignment_is_skipped_when_sim_already_has_rising_trait(self):
        class FakeSimInfo(object):
            def __init__(self):
                self.sim_id = 123
                self._traits = {2297406366}

        result = rising_assignment.apply_sun_time_rising_assignment(
            FakeSimInfo(),
            sun_sign_index=0,
            hour_24=6,
            trait_ids_by_sign_index={0: 2297406366},
            has_trait_fn=lambda sim_info, trait_id: trait_id in sim_info._traits,
            add_trait_fn=lambda sim_info, trait_id: (_ for _ in ()).throw(AssertionError("unexpected add")),
        )

        self.assertEqual({"applied": False, "reason": "already_has_rising"}, result)

    def test_invalid_hour_raises_instead_of_guessing(self):
        with self.assertRaises(ValueError):
            rising_assignment.resolve_rising_sign_index_for_sun_time(0, 7)

    def test_python_loot_bridge_calls_runtime_rising_assignment(self):
        from plumantics_big3_runtime import loot_actions

        calls = []

        class FakeRuntime(object):
            def assign_rising_sun_time_for_sim_info(self, sim_info, reason="unknown"):
                calls.append((sim_info, reason))
                return {"applied": True}

        class FakeLoot(loot_actions.Big3AssignRisingSunTimePythonLoot):
            pass

        original_get_runtime = loot_actions.get_runtime
        original_resolve_actor = loot_actions._resolve_actor_sim_info
        try:
            fake_sim = object()
            loot_actions.get_runtime = lambda: FakeRuntime()
            loot_actions._resolve_actor_sim_info = lambda resolver: fake_sim
            FakeLoot().apply_to_resolver(object(), skip_test=True)
        finally:
            loot_actions.get_runtime = original_get_runtime
            loot_actions._resolve_actor_sim_info = original_resolve_actor

        self.assertEqual([(fake_sim, "loot_bridge:rising_sun_time")], calls)

    def test_runtime_service_assign_rising_sun_time_uses_normalized_helper(self):
        from plumantics_big3_runtime.integration import bridge

        service = object.__new__(bridge.Big3RuntimeService)
        service._model = SimpleNamespace(
            ids={
                "rising_traits": {"ARIES": 2297406366},
            },
            zodiac_order=lambda: [
                "ARIES",
                "TAURUS",
                "GEMINI",
                "CANCER",
                "LEO",
                "VIRGO",
                "LIBRA",
                "SCORPIO",
                "SAGITTARIUS",
                "CAPRICORN",
                "AQUARIUS",
                "PISCES",
            ],
        )
        service._clock_port = SimpleNamespace(sim_minute_provider=lambda: 360)
        service._trait_ids_for_sim_info = lambda sim_info: [3164395998]
        service._resolve_sign_index_from_traits = lambda trait_ids, groups: 0

        class FakeSimInfo(object):
            def __init__(self):
                self.sim_id = 42
                self._traits = set()

        fake_sim = FakeSimInfo()
        original_has_trait = bridge._sim_has_trait
        original_add_trait = bridge._add_trait_if_missing
        original_sync = getattr(bridge, "_sync_sign_compatibility_after_big3_assignment", None)
        try:
            bridge._sim_has_trait = lambda sim_info, trait_id: trait_id in sim_info._traits
            bridge._add_trait_if_missing = lambda sim_info, trait_id: sim_info._traits.add(trait_id) is None
            bridge._sync_sign_compatibility_after_big3_assignment = (
                lambda sim_info, reason="unknown": {"ok": True}
            )
            service._refresh_chart_record_caches_for_sim_info = (
                lambda sim_info, reason="unknown": {"ok": True}
            )
            result = service.assign_rising_sun_time_for_sim_info(fake_sim, reason="test")
        finally:
            bridge._sim_has_trait = original_has_trait
            bridge._add_trait_if_missing = original_add_trait
            if original_sync is None:
                delattr(bridge, "_sync_sign_compatibility_after_big3_assignment")
            else:
                bridge._sync_sign_compatibility_after_big3_assignment = original_sync

        self.assertTrue(result["applied"])
        self.assertEqual(2297406366, result["rising_trait_id"])

    def test_random_rising_assignment_uses_selected_sign_index(self):
        class FakeSimInfo(object):
            def __init__(self):
                self.sim_id = 200
                self._traits = set()

        fake_sim = FakeSimInfo()
        result = rising_assignment.apply_random_rising_assignment(
            fake_sim,
            available_sign_indexes=(0, 4, 9),
            trait_ids_by_sign_index={0: 2297406366, 4: 3739357428, 9: 3178572581},
            has_any_rising_trait_fn=lambda sim_info: False,
            has_trait_fn=lambda sim_info, trait_id: trait_id in sim_info._traits,
            add_trait_fn=lambda sim_info, trait_id: sim_info._traits.add(trait_id) is None,
            choose_sign_index_fn=lambda indexes: 4,
        )

        self.assertTrue(result["applied"])
        self.assertEqual(4, result["rising_sign_index"])
        self.assertEqual(3739357428, result["rising_trait_id"])

    def test_random_rising_assignment_skips_when_rising_exists(self):
        class FakeSimInfo(object):
            def __init__(self):
                self.sim_id = 201
                self._traits = {2297406366}

        result = rising_assignment.apply_random_rising_assignment(
            FakeSimInfo(),
            available_sign_indexes=(0,),
            trait_ids_by_sign_index={0: 2297406366},
            has_any_rising_trait_fn=lambda sim_info: True,
            has_trait_fn=lambda sim_info, trait_id: trait_id in sim_info._traits,
            add_trait_fn=lambda sim_info, trait_id: (_ for _ in ()).throw(AssertionError("unexpected add")),
            choose_sign_index_fn=lambda indexes: 0,
        )

        self.assertEqual({"applied": False, "reason": "already_has_rising"}, result)

    def test_python_loot_bridge_calls_runtime_random_rising_assignment(self):
        from plumantics_big3_runtime import loot_actions

        calls = []

        class FakeRuntime(object):
            def assign_rising_random_for_sim_info(self, sim_info, reason="unknown"):
                calls.append((sim_info, reason))
                return {"applied": True}

        class FakeLoot(loot_actions.Big3AssignRisingRandomPythonLoot):
            pass

        original_get_runtime = loot_actions.get_runtime
        original_resolve_actor = loot_actions._resolve_actor_sim_info
        try:
            fake_sim = object()
            loot_actions.get_runtime = lambda: FakeRuntime()
            loot_actions._resolve_actor_sim_info = lambda resolver: fake_sim
            FakeLoot().apply_to_resolver(object(), skip_test=True)
        finally:
            loot_actions.get_runtime = original_get_runtime
            loot_actions._resolve_actor_sim_info = original_resolve_actor

        self.assertEqual([(fake_sim, "loot_bridge:rising_random")], calls)

    def test_runtime_service_routes_random_rising_without_xml_loot(self):
        from plumantics_big3_runtime.integration import bridge
        from plumantics_big3_runtime.integration.assignments import AssignmentRequest

        service = object.__new__(bridge.Big3RuntimeService)
        service._run_refresh_router_after_assignment = lambda: False
        service._store_chart_record_for_sim_info = lambda sim_info, metadata=None, overwrite_existing=False: None
        service._resolve_requested_modes = lambda age_name, request: request

        fake_sim = SimpleNamespace(sim_id=77, age="ADULT")
        original_resolve_sim_info = bridge._resolve_sim_info
        try:
            bridge._resolve_sim_info = lambda sim_id: fake_sim
            service.assign_rising_random_for_sim_info = (
                lambda sim_info, reason="unknown", **kwargs: {"applied": True}
            )
            service._run_loot_for_sim_info = lambda loot_id, sim_info: (_ for _ in ()).throw(
                AssertionError("rising random should not route through xml loot")
            )

            result = service.assign_big3_for_sim(
                sim_id=77,
                request=AssignmentRequest(
                    sun_mode="skip",
                    moon_mode="skip",
                    rising_mode="random",
                    overwrite_existing=False,
                ),
            )
        finally:
            bridge._resolve_sim_info = original_resolve_sim_info

        self.assertTrue(result["rising_applied"])

    def test_runtime_service_rising_assignment_refreshes_chart_cache_and_syncs_preferences(self):
        from plumantics_big3_runtime.integration import bridge

        service = object.__new__(bridge.Big3RuntimeService)
        service._model = SimpleNamespace(
            ids={
                "rising_traits": {"ARIES": 2297406366},
            },
            zodiac_order=lambda: [
                "ARIES",
                "TAURUS",
                "GEMINI",
                "CANCER",
                "LEO",
                "VIRGO",
                "LIBRA",
                "SCORPIO",
                "SAGITTARIUS",
                "CAPRICORN",
                "AQUARIUS",
                "PISCES",
            ],
        )
        service._clock_port = SimpleNamespace(sim_minute_provider=lambda: 360)
        service._trait_ids_for_sim_info = lambda sim_info: [3164395998]
        service._resolve_sign_index_from_traits = (
            lambda trait_ids, groups: 0 if tuple(groups) == ("sun_traits", "sun_traits_child") else None
        )

        fake_sim = SimpleNamespace(sim_id=505, age="ADULT", _traits=set())
        refresh_calls = []
        sync_calls = []

        original_has_trait = bridge._sim_has_trait
        original_add_trait = bridge._add_trait_if_missing
        original_sync = getattr(bridge, "_sync_sign_compatibility_after_big3_assignment", None)
        try:
            bridge._sim_has_trait = lambda sim_info, trait_id: trait_id in sim_info._traits
            bridge._add_trait_if_missing = lambda sim_info, trait_id: sim_info._traits.add(trait_id) is None
            bridge._sync_sign_compatibility_after_big3_assignment = (
                lambda sim_info, reason="unknown": sync_calls.append((sim_info, reason)) or {"ok": True}
            )
            service._refresh_chart_record_caches_for_sim_info = (
                lambda sim_info, reason="unknown": refresh_calls.append((sim_info, reason)) or {"ok": True}
            )

            result = service.assign_rising_sun_time_for_sim_info(fake_sim, reason="test")
        finally:
            bridge._sim_has_trait = original_has_trait
            bridge._add_trait_if_missing = original_add_trait
            if original_sync is None:
                delattr(bridge, "_sync_sign_compatibility_after_big3_assignment")
            else:
                bridge._sync_sign_compatibility_after_big3_assignment = original_sync

        self.assertTrue(result["applied"])
        self.assertEqual([(fake_sim, "test")], refresh_calls)
        self.assertEqual([(fake_sim, "test")], sync_calls)

    def test_random_rising_interaction_requests_random_mode(self):
        original_modules = {}
        for name in (
            "sims4",
            "sims4.log",
            "interactions",
            "interactions.base",
            "interactions.base.immediate_interaction",
            "plumantics_big3_runtime.integration.interactions",
        ):
            original_modules[name] = sys.modules.get(name)

        sims4_module = types.ModuleType("sims4")
        sims4_log_module = types.ModuleType("sims4.log")
        sims4_log_module.Logger = lambda *args, **kwargs: SimpleNamespace(
            exception=lambda *a, **k: None,
            error=lambda *a, **k: None,
        )
        sims4_module.log = sims4_log_module
        sys.modules["sims4"] = sims4_module
        sys.modules["sims4.log"] = sims4_log_module

        interactions_module = types.ModuleType("interactions")
        interactions_base_module = types.ModuleType("interactions.base")
        immediate_module = types.ModuleType("interactions.base.immediate_interaction")
        immediate_module.ImmediateSuperInteraction = type(
            "ImmediateSuperInteraction",
            (object,),
            {},
        )
        sys.modules["interactions"] = interactions_module
        sys.modules["interactions.base"] = interactions_base_module
        sys.modules["interactions.base.immediate_interaction"] = immediate_module

        sys.modules.pop("plumantics_big3_runtime.integration.interactions", None)
        from plumantics_big3_runtime.integration import interactions

        calls = []
        original_invoke = interactions._invoke_assign_big3_assignment
        try:
            interactions._invoke_assign_big3_assignment = lambda **kwargs: calls.append(kwargs) or True
            generator = interactions.Big3UniverseAssignRisingImmediate._run_interaction_gen(
                SimpleNamespace(),
                timeline=None,
            )
            try:
                next(generator)
            except StopIteration as exc:
                result = exc.value
            else:
                result = None
        finally:
            interactions._invoke_assign_big3_assignment = original_invoke
            for name, module in original_modules.items():
                if module is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = module

        self.assertTrue(result)
        self.assertEqual(
            [
                {
                    "sun_mode": "skip",
                    "moon_mode": "skip",
                    "rising_mode": "random",
                    "overwrite_existing": False,
                }
            ],
            calls,
        )


if __name__ == "__main__":
    unittest.main()
