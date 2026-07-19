import importlib
import pathlib
import sys
import unittest


sys.dont_write_bytecode = True

ROOT = pathlib.Path(__file__).resolve().parents[1]
PYTHON_DIR = ROOT / "python"
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))


loot_actions = importlib.import_module("cosmic_engine.loot_actions")
runtime_hooks = importlib.import_module("cosmic_engine.runtime_hooks")
natal_snapshot_markers = importlib.import_module("cosmic_engine.natal_snapshot_markers")


class _FakeResolver(object):
    pass


class _FakeSimInfo(object):
    def __init__(self, household_id=67890):
        self.sim_id = 12345
        self.id = 12345
        self.household_id = int(household_id)
        self.household = type("Household", (), {"id": int(household_id)})()


class AstroCoreLootOnboardingBridgeCleanupTests(unittest.TestCase):
    def setUp(self):
        self._resolve_actor = loot_actions._resolve_actor_sim_info
        self._mark_dirty = loot_actions.mark_sim_dirty
        self._dispatch_household_onboard = runtime_hooks.dispatch_household_onboard
        self._apply_rising_buff = natal_snapshot_markers.apply_visible_rising_timed_buff_for_sim_info
        self._last_debug = loot_actions._LAST_NATAL_ONBOARD_DEBUG
        self._last_run = dict(loot_actions._NATAL_ONBOARD_LAST_RUN_BY_HOUSEHOLD_ID)
        self._in_progress = loot_actions._NATAL_ONBOARD_LOOT_IN_PROGRESS
        self._monotonic = loot_actions.time.monotonic

    def tearDown(self):
        loot_actions._resolve_actor_sim_info = self._resolve_actor
        loot_actions.mark_sim_dirty = self._mark_dirty
        runtime_hooks.dispatch_household_onboard = self._dispatch_household_onboard
        natal_snapshot_markers.apply_visible_rising_timed_buff_for_sim_info = self._apply_rising_buff
        loot_actions._LAST_NATAL_ONBOARD_DEBUG = self._last_debug
        loot_actions._NATAL_ONBOARD_LAST_RUN_BY_HOUSEHOLD_ID.clear()
        loot_actions._NATAL_ONBOARD_LAST_RUN_BY_HOUSEHOLD_ID.update(self._last_run)
        loot_actions._NATAL_ONBOARD_LOOT_IN_PROGRESS = self._in_progress
        loot_actions.time.monotonic = self._monotonic

    def test_current_sky_onboarding_loot_routes_through_astrocore_bridge(self):
        sim_info = _FakeSimInfo()
        dirty_calls = []
        bridge_calls = []
        monotonic_values = iter((10.0, 10.25, 10.5, 10.75))

        loot_actions._resolve_actor_sim_info = lambda resolver: sim_info
        loot_actions.mark_sim_dirty = lambda *args, **kwargs: dirty_calls.append((args, kwargs))
        runtime_hooks.dispatch_household_onboard = (
            lambda household_id, refresh_marker_cache=False, teen_sign_seed_mode="current_sky": bridge_calls.append(
                (household_id, refresh_marker_cache, teen_sign_seed_mode)
            )
            or {
                "ok": True,
                "addon_summaries": {
                    "core_onboarding": {"ok": True, "total_sims_seeded": 4}
                },
            }
        )
        natal_snapshot_markers.apply_visible_rising_timed_buff_for_sim_info = (
            lambda owner, refresh_marker_cache=False: {"buff_applied": True}
        )
        loot_actions.time.monotonic = lambda: next(monotonic_values)
        loot_actions._LAST_NATAL_ONBOARD_DEBUG = None
        loot_actions._NATAL_ONBOARD_LAST_RUN_BY_HOUSEHOLD_ID.clear()
        loot_actions._NATAL_ONBOARD_LOOT_IN_PROGRESS = False

        result = loot_actions.CosmicEngineNatalOnboardActiveHouseholdLoot().apply_to_resolver(_FakeResolver())

        self.assertTrue(result)
        self.assertEqual([(67890, False, "current_sky")], bridge_calls)
        self.assertEqual("current_sky", loot_actions._LAST_NATAL_ONBOARD_DEBUG["mode"])
        self.assertEqual(4, loot_actions._LAST_NATAL_ONBOARD_DEBUG["summary"]["total_sims_seeded"])
        self.assertEqual(1, len(dirty_calls))

    def test_random_sun_moon_onboarding_loot_routes_through_astrocore_bridge(self):
        sim_info = _FakeSimInfo()
        bridge_calls = []
        monotonic_values = iter((20.0, 20.5, 20.75, 21.0))

        loot_actions._resolve_actor_sim_info = lambda resolver: sim_info
        loot_actions.mark_sim_dirty = lambda *args, **kwargs: None
        runtime_hooks.dispatch_household_onboard = (
            lambda household_id, refresh_marker_cache=False, teen_sign_seed_mode="current_sky": bridge_calls.append(
                (household_id, refresh_marker_cache, teen_sign_seed_mode)
            )
            or {
                "ok": True,
                "addon_summaries": {
                    "core_onboarding": {"ok": True, "total_sims_seeded": 3}
                },
            }
        )
        natal_snapshot_markers.apply_visible_rising_timed_buff_for_sim_info = (
            lambda owner, refresh_marker_cache=False: {"buff_applied": True}
        )
        loot_actions.time.monotonic = lambda: next(monotonic_values)
        loot_actions._LAST_NATAL_ONBOARD_DEBUG = None
        loot_actions._NATAL_ONBOARD_LAST_RUN_BY_HOUSEHOLD_ID.clear()
        loot_actions._NATAL_ONBOARD_LOOT_IN_PROGRESS = False

        result = loot_actions.CosmicEngineNatalOnboardActiveHouseholdRandomSunMoonLoot().apply_to_resolver(
            _FakeResolver()
        )

        self.assertTrue(result)
        self.assertEqual([(67890, False, "random_sun_moon")], bridge_calls)
        self.assertEqual("random_sun_moon", loot_actions._LAST_NATAL_ONBOARD_DEBUG["mode"])
        self.assertEqual(3, loot_actions._LAST_NATAL_ONBOARD_DEBUG["summary"]["total_sims_seeded"])


if __name__ == "__main__":
    unittest.main()
