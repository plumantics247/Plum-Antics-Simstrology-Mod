import pathlib
import sys
import unittest
from types import SimpleNamespace
import types


ROOT = pathlib.Path(__file__).resolve().parents[1]
PYTHON_DIR = ROOT / "python"
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))

from plumantics_big3_runtime.integration import moon_assignment


MOON_BUCKET_SIGN_INDEX = {
    "NEW_MOON": {
        "ARIES": 0,
        "TAURUS": 1,
        "GEMINI": 2,
        "CANCER": 3,
        "LEO": 4,
        "VIRGO": 5,
        "LIBRA": 6,
        "SCORPIO": 7,
        "SAGITTARIUS": 8,
        "CAPRICORN": 9,
        "AQUARIUS": 10,
        "PISCES": 11,
    },
    "WAXING_CRESCENT_DAY": {
        "ARIES": 1,
        "TAURUS": 2,
        "GEMINI": 3,
        "CANCER": 4,
        "LEO": 5,
        "VIRGO": 6,
        "LIBRA": 7,
        "SCORPIO": 8,
        "SAGITTARIUS": 9,
        "CAPRICORN": 10,
        "AQUARIUS": 11,
        "PISCES": 0,
    },
    "WAXING_CRESCENT_NIGHT": {
        "ARIES": 2,
        "TAURUS": 3,
        "GEMINI": 4,
        "CANCER": 5,
        "LEO": 6,
        "VIRGO": 7,
        "LIBRA": 8,
        "SCORPIO": 9,
        "SAGITTARIUS": 10,
        "CAPRICORN": 11,
        "AQUARIUS": 0,
        "PISCES": 1,
    },
    "FIRST_QUARTER": {
        "ARIES": 3,
        "TAURUS": 4,
        "GEMINI": 5,
        "CANCER": 6,
        "LEO": 7,
        "VIRGO": 8,
        "LIBRA": 9,
        "SCORPIO": 10,
        "SAGITTARIUS": 11,
        "CAPRICORN": 0,
        "AQUARIUS": 1,
        "PISCES": 2,
    },
    "WAXING_GIBBOUS_DAY": {
        "ARIES": 4,
        "TAURUS": 5,
        "GEMINI": 6,
        "CANCER": 7,
        "LEO": 8,
        "VIRGO": 9,
        "LIBRA": 10,
        "SCORPIO": 11,
        "SAGITTARIUS": 0,
        "CAPRICORN": 1,
        "AQUARIUS": 2,
        "PISCES": 3,
    },
    "WAXING_GIBBOUS_NIGHT": {
        "ARIES": 5,
        "TAURUS": 6,
        "GEMINI": 7,
        "CANCER": 8,
        "LEO": 9,
        "VIRGO": 10,
        "LIBRA": 11,
        "SCORPIO": 0,
        "SAGITTARIUS": 1,
        "CAPRICORN": 2,
        "AQUARIUS": 3,
        "PISCES": 4,
    },
    "FULL_MOON": {
        "ARIES": 6,
        "TAURUS": 7,
        "GEMINI": 8,
        "CANCER": 9,
        "LEO": 10,
        "VIRGO": 11,
        "LIBRA": 0,
        "SCORPIO": 1,
        "SAGITTARIUS": 2,
        "CAPRICORN": 3,
        "AQUARIUS": 4,
        "PISCES": 5,
    },
    "WANING_GIBBOUS_DAY": {
        "ARIES": 7,
        "TAURUS": 8,
        "GEMINI": 9,
        "CANCER": 10,
        "LEO": 11,
        "VIRGO": 0,
        "LIBRA": 1,
        "SCORPIO": 2,
        "SAGITTARIUS": 3,
        "CAPRICORN": 4,
        "AQUARIUS": 5,
        "PISCES": 6,
    },
    "WANING_GIBBOUS_NIGHT": {
        "ARIES": 8,
        "TAURUS": 9,
        "GEMINI": 10,
        "CANCER": 11,
        "LEO": 0,
        "VIRGO": 1,
        "LIBRA": 2,
        "SCORPIO": 3,
        "SAGITTARIUS": 4,
        "CAPRICORN": 5,
        "AQUARIUS": 6,
        "PISCES": 7,
    },
    "THIRD_QUARTER": {
        "ARIES": 9,
        "TAURUS": 10,
        "GEMINI": 11,
        "CANCER": 0,
        "LEO": 1,
        "VIRGO": 2,
        "LIBRA": 3,
        "SCORPIO": 4,
        "SAGITTARIUS": 5,
        "CAPRICORN": 6,
        "AQUARIUS": 7,
        "PISCES": 8,
    },
    "WANING_CRESCENT_DAY": {
        "ARIES": 10,
        "TAURUS": 11,
        "GEMINI": 0,
        "CANCER": 1,
        "LEO": 2,
        "VIRGO": 3,
        "LIBRA": 4,
        "SCORPIO": 5,
        "SAGITTARIUS": 6,
        "CAPRICORN": 7,
        "AQUARIUS": 8,
        "PISCES": 9,
    },
    "WANING_CRESCENT_NIGHT": {
        "ARIES": 11,
        "TAURUS": 0,
        "GEMINI": 1,
        "CANCER": 2,
        "LEO": 3,
        "VIRGO": 4,
        "LIBRA": 5,
        "SCORPIO": 6,
        "SAGITTARIUS": 7,
        "CAPRICORN": 8,
        "AQUARIUS": 9,
        "PISCES": 10,
    },
}


class MoonRuntimeAssignmentTests(unittest.TestCase):
    def test_bucket_map_matches_approved_table(self):
        self.assertEqual(
            MOON_BUCKET_SIGN_INDEX,
            moon_assignment.build_bucket_sign_index_map(),
        )

    def test_resolve_lunar_bucket_key_uses_phase_and_hour(self):
        self.assertEqual(
            "WAXING_CRESCENT_DAY",
            moon_assignment.resolve_lunar_bucket_key("WAXING_CRESCENT", 12),
        )
        self.assertEqual(
            "WAXING_CRESCENT_NIGHT",
            moon_assignment.resolve_lunar_bucket_key("WAXING_CRESCENT", 22),
        )
        self.assertEqual(
            "FULL_MOON",
            moon_assignment.resolve_lunar_bucket_key("FULL_MOON", 8),
        )

    def test_exact_mapping_examples_match_approved_table(self):
        self.assertEqual(
            4,
            moon_assignment.resolve_moon_sign_index_for_bucket(4, "NEW_MOON"),
        )
        self.assertEqual(
            10,
            moon_assignment.resolve_moon_sign_index_for_bucket(4, "FULL_MOON"),
        )
        self.assertEqual(
            7,
            moon_assignment.resolve_moon_sign_index_for_bucket(4, "FIRST_QUARTER"),
        )
        self.assertEqual(
            3,
            moon_assignment.resolve_moon_sign_index_for_bucket(11, "WAXING_GIBBOUS_DAY"),
        )

    def test_lunar_phase_assignment_skips_when_moon_trait_already_exists(self):
        class FakeSimInfo(object):
            def __init__(self):
                self.sim_id = 101
                self._traits = {4080273607}

        result = moon_assignment.apply_lunar_phase_moon_assignment(
            FakeSimInfo(),
            sun_sign_index=0,
            lunar_bucket_key="NEW_MOON",
            trait_ids_by_sign_index={0: 4080273607},
            has_any_moon_trait_fn=lambda sim_info: True,
            has_trait_fn=lambda sim_info, trait_id: trait_id in sim_info._traits,
            add_trait_fn=lambda sim_info, trait_id: (_ for _ in ()).throw(AssertionError("unexpected add")),
        )

        self.assertEqual({"applied": False, "reason": "already_has_moon"}, result)

    def test_random_assignment_uses_selected_sign_index(self):
        class FakeSimInfo(object):
            def __init__(self):
                self.sim_id = 202
                self._traits = set()

        fake_sim = FakeSimInfo()
        result = moon_assignment.apply_random_moon_assignment(
            fake_sim,
            available_sign_indexes=(0, 5, 8),
            trait_ids_by_sign_index={0: 4080273607, 5: 3315030320, 8: 3557938955},
            has_any_moon_trait_fn=lambda sim_info: False,
            has_trait_fn=lambda sim_info, trait_id: trait_id in sim_info._traits,
            add_trait_fn=lambda sim_info, trait_id: sim_info._traits.add(trait_id) is None,
            choose_sign_index_fn=lambda indexes: 5,
        )

        self.assertTrue(result["applied"])
        self.assertEqual(5, result["moon_sign_index"])
        self.assertEqual(3315030320, result["moon_trait_id"])


class MoonRuntimeBridgeTests(unittest.TestCase):
    def test_python_loot_bridge_calls_runtime_lunar_phase_assignment(self):
        from plumantics_big3_runtime import loot_actions

        calls = []

        class FakeRuntime(object):
            def assign_moon_lunar_phase_for_sim_info(self, sim_info, reason="unknown"):
                calls.append((sim_info, reason))
                return {"applied": True}

        class FakeLoot(loot_actions.Big3AssignMoonLunarPhasePythonLoot):
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

        self.assertEqual([(fake_sim, "loot_bridge:moon_lunar_phase")], calls)

    def test_python_loot_bridge_calls_runtime_random_assignment(self):
        from plumantics_big3_runtime import loot_actions

        calls = []

        class FakeRuntime(object):
            def assign_moon_random_for_sim_info(self, sim_info, reason="unknown"):
                calls.append((sim_info, reason))
                return {"applied": True}

        class FakeLoot(loot_actions.Big3AssignMoonRandomPythonLoot):
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

        self.assertEqual([(fake_sim, "loot_bridge:moon_random")], calls)

    def test_runtime_service_routes_lunar_phase_and_random_modes_without_xml_loot(self):
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
            service.assign_moon_lunar_phase_for_sim_info = (
                lambda sim_info, reason="unknown", **kwargs: {"applied": True}
            )
            service.assign_moon_random_for_sim_info = (
                lambda sim_info, reason="unknown", **kwargs: {"applied": True}
            )
            service._run_loot_for_sim_info = lambda loot_id, sim_info: (_ for _ in ()).throw(
                AssertionError("moon should not route through xml loot")
            )

            lunar_result = service.assign_big3_for_sim(
                sim_id=77,
                request=AssignmentRequest(
                    sun_mode="skip",
                    moon_mode="lunar_phase",
                    rising_mode="skip",
                    overwrite_existing=False,
                ),
            )
            random_result = service.assign_big3_for_sim(
                sim_id=77,
                request=AssignmentRequest(
                    sun_mode="skip",
                    moon_mode="random",
                    rising_mode="skip",
                    overwrite_existing=False,
                ),
            )
        finally:
            bridge._resolve_sim_info = original_resolve_sim_info

        self.assertTrue(lunar_result["moon_applied"])
        self.assertTrue(random_result["moon_applied"])

    def test_runtime_service_moon_assignment_refreshes_chart_cache_and_syncs_preferences(self):
        from plumantics_big3_runtime.integration import bridge

        service = object.__new__(bridge.Big3RuntimeService)
        service._model = SimpleNamespace(
            ids={
                "moon_traits": {"ARIES": 4080273607},
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
        service._trait_ids_for_sim_info = lambda sim_info: [3164395998]
        service._resolve_sign_index_from_traits = (
            lambda trait_ids, groups: 0 if tuple(groups) == ("sun_traits", "sun_traits_child") else None
        )

        fake_sim = SimpleNamespace(sim_id=404, age="ADULT", _traits=set())
        refresh_calls = []
        sync_calls = []

        original_has_trait = bridge._sim_has_trait
        original_add_trait = bridge._add_trait_if_missing
        original_phase = bridge._current_lunar_phase_name
        original_hour = bridge._current_sim_hour
        original_sync = getattr(bridge, "_sync_sign_compatibility_after_big3_assignment", None)
        try:
            bridge._sim_has_trait = lambda sim_info, trait_id: trait_id in sim_info._traits
            bridge._add_trait_if_missing = lambda sim_info, trait_id: sim_info._traits.add(trait_id) is None
            bridge._current_lunar_phase_name = lambda: "NEW_MOON"
            bridge._current_sim_hour = lambda: 10
            bridge._sync_sign_compatibility_after_big3_assignment = (
                lambda sim_info, reason="unknown": sync_calls.append((sim_info, reason)) or {"ok": True}
            )
            service._refresh_chart_record_caches_for_sim_info = (
                lambda sim_info, reason="unknown": refresh_calls.append((sim_info, reason)) or {"ok": True}
            )

            result = service.assign_moon_lunar_phase_for_sim_info(fake_sim, reason="test")
        finally:
            bridge._sim_has_trait = original_has_trait
            bridge._add_trait_if_missing = original_add_trait
            bridge._current_lunar_phase_name = original_phase
            bridge._current_sim_hour = original_hour
            if original_sync is None:
                delattr(bridge, "_sync_sign_compatibility_after_big3_assignment")
            else:
                bridge._sync_sign_compatibility_after_big3_assignment = original_sync

        self.assertTrue(result["applied"])
        self.assertEqual([(fake_sim, "test")], refresh_calls)
        self.assertEqual([(fake_sim, "test")], sync_calls)

    def test_assign_big3_for_sim_refreshes_chart_cache_and_syncs_after_sun_change(self):
        from plumantics_big3_runtime.integration import bridge
        from plumantics_big3_runtime.integration.assignments import AssignmentRequest

        service = object.__new__(bridge.Big3RuntimeService)
        service._chart_record_payload_by_sim_id = {}
        service._resolve_requested_modes = lambda age_name, request: request
        service._run_refresh_router_after_assignment = lambda: False
        service._run_loot_for_sim_info = lambda loot_id, sim_info: True
        service._assignment_loot_id = lambda key: 123
        service._refresh_chart_record_caches_for_sim_info = lambda sim_info, reason="unknown": {
            "ok": True
        }

        fake_sim = SimpleNamespace(sim_id=77, age="ADULT")
        refresh_calls = []
        sync_calls = []

        original_resolve_sim_info = bridge._resolve_sim_info
        original_sync = getattr(bridge, "_sync_sign_compatibility_after_big3_assignment", None)
        try:
            bridge._resolve_sim_info = lambda sim_id: fake_sim
            service._refresh_chart_record_caches_for_sim_info = (
                lambda sim_info, reason="unknown": refresh_calls.append((sim_info, reason)) or {"ok": True}
            )
            bridge._sync_sign_compatibility_after_big3_assignment = (
                lambda sim_info, reason="unknown": sync_calls.append((sim_info, reason)) or {"ok": True}
            )

            result = service.assign_big3_for_sim(
                sim_id=77,
                request=AssignmentRequest(
                    sun_mode="personality",
                    moon_mode="skip",
                    rising_mode="skip",
                    overwrite_existing=False,
                ),
            )
        finally:
            bridge._resolve_sim_info = original_resolve_sim_info
            if original_sync is None:
                delattr(bridge, "_sync_sign_compatibility_after_big3_assignment")
            else:
                bridge._sync_sign_compatibility_after_big3_assignment = original_sync

        self.assertTrue(result["sun_applied"])
        self.assertEqual([(fake_sim, "big3_auto_assignment")], refresh_calls)
        self.assertEqual([(fake_sim, "assign_big3_for_sim")], sync_calls)

    def test_random_moon_interaction_requests_random_mode(self):
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
            generator = interactions.Big3UniverseAssignMoonImmediate._run_interaction_gen(
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
                    "moon_mode": "random",
                    "rising_mode": "skip",
                    "overwrite_existing": False,
                }
            ],
            calls,
        )


if __name__ == "__main__":
    unittest.main()
