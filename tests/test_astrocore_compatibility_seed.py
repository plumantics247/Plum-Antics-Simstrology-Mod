import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
PYTHON_DIR = ROOT / "python"
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))


from astrocore.domains.compatibility_seed import (
    build_household_compatibility_handler,
    build_sim_age_transition_compatibility_handler,
)
from astrocore.engine.lifecycle_types import EVENT_SIM_AGE_TRANSITION, LifecycleEvent


class AstroCoreCompatibilitySeedTests(unittest.TestCase):
    def test_household_handler_runs_existing_household_seed_once(self):
        calls = []

        def _seed_household(reason):
            calls.append(reason)
            return {"written_lanes": ("Sun", "Moon")}

        handler = build_household_compatibility_handler(seed_household_fn=_seed_household)
        result = handler(type("Context", (), {"metadata": {"reason": "runtime.household_onboard"}})())

        self.assertEqual(["runtime.household_onboard"], calls)
        self.assertEqual(("Sun", "Moon"), tuple(result["summary"]["written_lanes"]))

    def test_age_transition_handler_skips_non_eligible_ages(self):
        handler = build_sim_age_transition_compatibility_handler(
            sync_sim_fn=lambda sim_id, reason: {"unexpected": True}
        )
        result = handler(
            type(
                "Context",
                (),
                {
                    "metadata": {
                        "event": LifecycleEvent(
                            name=EVENT_SIM_AGE_TRANSITION,
                            sim_id=55,
                            age_from="child",
                            age_to="child",
                        )
                    }
                },
            )()
        )
        self.assertFalse(result["summary"]["handled"])
        self.assertEqual("age_not_newly_eligible", result["summary"]["reason"])


if __name__ == "__main__":
    unittest.main()
