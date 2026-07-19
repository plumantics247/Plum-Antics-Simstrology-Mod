import pathlib
import sys
import unittest


sys.dont_write_bytecode = True

ROOT = pathlib.Path(__file__).resolve().parents[1]
PYTHON_DIR = ROOT / "python"
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))


from astrocore.domains.sky_effects import (
    build_retrograde_tick_handler,
    build_solar_boost_tick_handler,
    build_solar_return_tick_handler,
    build_visible_sign_tick_handler,
)


class AstroCoreSkyEffectsTests(unittest.TestCase):
    def test_visible_sign_tick_handler_runs_existing_manager(self):
        calls = []

        handler = build_visible_sign_tick_handler(
            sync_visible_signs_fn=lambda: calls.append("visible") or {"changed": 2}
        )

        result = handler(type("Context", (), {"metadata": {"movement_trigger": True}})())

        self.assertEqual(["visible"], calls)
        self.assertTrue(result["summary"]["handled"])
        self.assertEqual(2, result["summary"]["changed"])

    def test_solar_return_tick_handler_skips_when_shared_runtime_disabled(self):
        handler = build_solar_return_tick_handler(
            sync_solar_return_fn=lambda show_notifications: {"unexpected": show_notifications}
        )

        result = handler(
            type(
                "Context",
                (),
                {
                    "metadata": {
                        "movement_trigger": True,
                        "shared_runtime_enabled": False,
                    }
                },
            )()
        )

        self.assertFalse(result["summary"]["handled"])
        self.assertEqual("shared_runtime_disabled", result["summary"]["reason"])

    def test_solar_boost_tick_handler_runs_when_shared_runtime_enabled(self):
        calls = []

        handler = build_solar_boost_tick_handler(
            sync_solar_boosts_fn=lambda: calls.append("solar_boosts") or {"buffs_added": 4}
        )

        result = handler(
            type(
                "Context",
                (),
                {
                    "metadata": {
                        "movement_trigger": True,
                        "shared_runtime_enabled": True,
                    }
                },
            )()
        )

        self.assertEqual(["solar_boosts"], calls)
        self.assertTrue(result["summary"]["handled"])
        self.assertEqual(4, result["summary"]["buffs_added"])

    def test_retrograde_tick_handler_runs_marker_and_consequence_sync(self):
        calls = []

        handler = build_retrograde_tick_handler(
            sync_markers_fn=lambda: calls.append("markers") or {"markers_changed": 1},
            sync_consequences_fn=lambda reason: calls.append(("consequences", reason)) or {"buffs_changed": 3},
        )

        result = handler(
            type(
                "Context",
                (),
                {
                    "metadata": {
                        "movement_trigger": True,
                        "retrogrades_enabled": True,
                        "reason": "runtime.tick",
                    }
                },
            )()
        )

        self.assertEqual(["markers", ("consequences", "runtime.tick")], calls)
        self.assertTrue(result["summary"]["handled"])
        self.assertEqual(1, result["summary"]["marker_summary"]["markers_changed"])
        self.assertEqual(3, result["summary"]["consequence_summary"]["buffs_changed"])


if __name__ == "__main__":
    unittest.main()
