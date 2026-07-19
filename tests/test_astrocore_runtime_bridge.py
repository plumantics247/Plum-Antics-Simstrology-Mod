import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
PYTHON_DIR = ROOT / "python"
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))


from astrocore.integrations.ts4.runtime_bridge import AstroCoreRuntimeBridge


class _FakeEngine(object):
    def __init__(self):
        self.events = []

    def dispatch_event(self, event, context):
        self.events.append(
            {
                "name": event.name,
                "sim_id": event.sim_id,
                "reason": event.reason,
                "active_mode": context.active_mode,
                "metadata": dict(getattr(context, "metadata", {}) or {}),
            }
        )
        return {"ok": True, "event_name": event.name}


class AstroCoreRuntimeBridgeTests(unittest.TestCase):
    def test_zone_or_save_load_dispatches_save_loaded_event(self):
        bridge = AstroCoreRuntimeBridge(engine=_FakeEngine())
        report = bridge.on_zone_or_save_load(saved_record={"seed": 1}, fallback_seed=9)
        self.assertTrue(report["ok"])
        self.assertEqual("save_loaded", bridge._engine.events[0]["name"])

    def test_periodic_tick_dispatches_periodic_repair_when_requested(self):
        bridge = AstroCoreRuntimeBridge(engine=_FakeEngine())
        report = bridge.on_clock_snapshot(
            total_days_elapsed=12,
            total_segments_elapsed=48,
            trigger_periodic_repair=True,
        )
        self.assertTrue(report["ok"])
        self.assertEqual("periodic_repair", bridge._engine.events[-1]["name"])

    def test_dispatch_household_onboard_emits_household_onboard_requested_event(self):
        bridge = AstroCoreRuntimeBridge(engine=_FakeEngine())
        report = bridge.dispatch_household_onboard(777, refresh_marker_cache=True)
        self.assertTrue(report["ok"])
        self.assertEqual("household_onboard_requested", bridge._engine.events[-1]["name"])

    def test_dispatch_runtime_tick_emits_periodic_repair_with_tick_metadata(self):
        bridge = AstroCoreRuntimeBridge(engine=_FakeEngine())
        report = bridge.dispatch_runtime_tick(
            total_days_elapsed=12,
            total_segments_elapsed=48,
            movement_trigger=True,
            count_trigger=False,
            periodic_trigger=False,
            active_mode="cosmic",
            shared_runtime_enabled=True,
            retrogrades_enabled=True,
        )

        self.assertTrue(report["ok"])
        self.assertEqual("periodic_repair", bridge._engine.events[-1]["name"])
        self.assertTrue(bridge._engine.events[-1]["metadata"]["movement_trigger"])
        self.assertTrue(bridge._engine.events[-1]["metadata"]["shared_runtime_enabled"])
        self.assertTrue(bridge._engine.events[-1]["metadata"]["retrogrades_enabled"])

    def test_runtime_bridge_registers_solar_boost_periodic_handler(self):
        bridge = AstroCoreRuntimeBridge(engine=_FakeEngine())
        names = [row.name for row in bridge._registry.handlers_for_event("periodic_repair")]
        self.assertIn("sky_solar_boosts", names)


if __name__ == "__main__":
    unittest.main()
