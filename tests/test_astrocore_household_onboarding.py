import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
PYTHON_DIR = ROOT / "python"
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))


from astrocore.domains.household_onboarding import build_household_onboarding_handler


class AstroCoreHouseholdOnboardingTests(unittest.TestCase):
    def test_household_onboard_calls_existing_natal_snapshot_onboarder_once(self):
        calls = []

        def _onboard(active_household_id, refresh_marker_cache=False, teen_sign_seed_mode="current_sky"):
            calls.append((active_household_id, refresh_marker_cache, teen_sign_seed_mode))
            return {"total_sims_seeded": 4, "total_traits_added": 12}

        handler = build_household_onboarding_handler(onboard_fn=_onboard)
        result = handler(type("Context", (), {"metadata": {"household_id": 777, "refresh_marker_cache": False}})())

        self.assertEqual([(777, False, "current_sky")], calls)
        self.assertEqual(4, result["summary"]["total_sims_seeded"])

    def test_missing_household_id_returns_skip_summary(self):
        handler = build_household_onboarding_handler(onboard_fn=lambda **_kwargs: {"unexpected": True})
        result = handler(type("Context", (), {"metadata": {}})())
        self.assertFalse(result["summary"]["handled"])
        self.assertEqual("missing_household_id", result["summary"]["reason"])

    def test_handler_passes_through_seed_mode_when_present(self):
        calls = []

        def _onboard(active_household_id, refresh_marker_cache=False, teen_sign_seed_mode="current_sky"):
            calls.append((active_household_id, refresh_marker_cache, teen_sign_seed_mode))
            return {"total_sims_seeded": 2}

        handler = build_household_onboarding_handler(onboard_fn=_onboard)
        result = handler(
            type(
                "Context",
                (),
                {
                    "metadata": {
                        "household_id": 777,
                        "refresh_marker_cache": False,
                        "teen_sign_seed_mode": "random_sun_moon",
                    }
                },
            )()
        )

        self.assertEqual([(777, False, "random_sun_moon")], calls)
        self.assertEqual(2, result["summary"]["total_sims_seeded"])


if __name__ == "__main__":
    unittest.main()
