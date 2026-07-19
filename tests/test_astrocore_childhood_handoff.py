import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
PYTHON_DIR = ROOT / "python"
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))


from astrocore.domains.childhood_handoff import build_childhood_age_transition_handler
from astrocore.engine.lifecycle_types import EVENT_SIM_AGE_TRANSITION, LifecycleContext, LifecycleEvent


class AstroCoreChildhoodHandoffTests(unittest.TestCase):
    def test_child_to_teen_event_runs_existing_handoff_repair(self):
        calls = []

        def _repair(sim_info):
            calls.append(getattr(sim_info, "sim_id", 0))
            return {"ok": True, "repair_path": "existing_bridge"}

        handler = build_childhood_age_transition_handler(
            repair_fn=_repair,
            lookup_sim_info=lambda sim_id: type("Sim", (), {"sim_id": sim_id})(),
        )

        result = handler(
            LifecycleContext(
                active_mode="cosmic",
                metadata={
                    "event": LifecycleEvent(
                        name=EVENT_SIM_AGE_TRANSITION,
                        sim_id=222,
                        age_from="child",
                        age_to="teen",
                    )
                },
            )
        )

        self.assertEqual([222], calls)
        self.assertTrue(result["summary"]["handled"])
        self.assertEqual("childhood_handoff", result["summary"]["reason"])
        self.assertEqual("existing_bridge", result["summary"]["repair_summary"]["repair_path"])

    def test_handler_skips_when_event_is_not_child_to_teen(self):
        handler = build_childhood_age_transition_handler(
            repair_fn=lambda _sim_info: {"unexpected": True},
            lookup_sim_info=lambda sim_id: type("Sim", (), {"sim_id": sim_id})(),
        )

        result = handler(
            LifecycleContext(
                active_mode="cosmic",
                metadata={
                    "event": LifecycleEvent(
                        name=EVENT_SIM_AGE_TRANSITION,
                        sim_id=222,
                        age_from="teen",
                        age_to="youngadult",
                    )
                },
            )
        )

        self.assertFalse(result["summary"]["handled"])
        self.assertEqual("age_not_child_to_teen", result["summary"]["reason"])


if __name__ == "__main__":
    unittest.main()
