import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
PYTHON_DIR = ROOT / "python"
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))


from astrocore.engine.addon_registry import AddonDeclaration, AddonRegistry
from astrocore.engine.lifecycle_engine import LifecycleEngine
from astrocore.engine.lifecycle_types import (
    EVENT_SIM_AGE_TRANSITION,
    EVENT_ZONE_LOADED,
    LifecycleContext,
    LifecycleEvent,
    OperationRequest,
)
from astrocore.engine.state_store import EngineStateStore


class _RecordingDispatcher(object):
    def __init__(self):
        self.applied = []

    def apply(self, operation):
        self.applied.append((operation.kind, operation.sim_id, dict(operation.payload)))
        return {"ok": True, "kind": operation.kind}


class AstroCoreLifecycleEngineTests(unittest.TestCase):
    def test_dispatch_event_runs_registered_handlers_and_marks_completion(self):
        registry = AddonRegistry()
        state = EngineStateStore()
        dispatcher = _RecordingDispatcher()

        def _handler(context):
            del context
            return {
                "operations": (
                    OperationRequest(
                        kind="run_loot",
                        sim_id=123,
                        payload={"loot_id": 830000000000009138},
                        source="childhood",
                    ),
                ),
                "summary": {"handler": "childhood"},
            }

        registry.register(
            AddonDeclaration(
                name="childhood",
                lifecycle_events=(EVENT_SIM_AGE_TRANSITION,),
                handler=_handler,
            )
        )
        engine = LifecycleEngine(registry=registry, state_store=state, dispatcher=dispatcher)

        report = engine.dispatch_event(
            LifecycleEvent(
                name=EVENT_SIM_AGE_TRANSITION,
                sim_id=123,
                age_from="child",
                age_to="teen",
                reason="test",
            ),
            LifecycleContext(active_mode="cosmic"),
        )

        self.assertTrue(report["ok"])
        self.assertEqual(1, len(dispatcher.applied))
        self.assertEqual("run_loot", dispatcher.applied[0][0])
        self.assertTrue(state.was_completed("childhood", EVENT_SIM_AGE_TRANSITION, 123))

    def test_dispatch_event_replays_due_deferred_work_on_zone_load(self):
        registry = AddonRegistry()
        state = EngineStateStore()
        dispatcher = _RecordingDispatcher()
        engine = LifecycleEngine(registry=registry, state_store=state, dispatcher=dispatcher)
        state.defer(
            addon_name="compatibility",
            event_name=EVENT_ZONE_LOADED,
            sim_id=456,
            reason="missing_chart",
            payload={"lane": "Sun"},
        )

        report = engine.dispatch_event(
            LifecycleEvent(name=EVENT_ZONE_LOADED, reason="test"),
            LifecycleContext(active_mode="cosmic"),
        )

        self.assertTrue(report["ok"])
        self.assertEqual(1, report["deferred_replayed"])
        self.assertEqual("compatibility", report["replayed"][0]["addon_name"])


if __name__ == "__main__":
    unittest.main()
