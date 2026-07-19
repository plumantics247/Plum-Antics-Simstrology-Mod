import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
PYTHON_DIR = ROOT / "python"
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))


from cosmic_engine.chart_read_dialogs import _screen_three_text
from cosmic_engine.chart_records import build_cosmic_chart, should_refresh_outer_planets_chart_payload
from cosmic_engine import outer_planets_activation
from plumantics_big3_runtime.core.charting import build_big3_chart
from plumantics_big3_runtime.loot_actions import _resolve_chart_payload_for_read as resolve_big3_chart_payload_for_read


BODY_SIGNS = {
    "Sun": 0,
    "Moon": 1,
    "Mercury": 2,
    "Venus": 3,
    "Mars": 4,
    "Jupiter": 5,
    "Saturn": 6,
    "Uranus": 7,
    "Neptune": 8,
    "Pluto": 9,
    "Chiron": 10,
}


class OuterPlanetsNatalChartPayloadTests(unittest.TestCase):
    def tearDown(self):
        outer_planets_activation.clear_outer_planets_activation_override()

    def test_build_cosmic_chart_omits_outer_bodies_when_addon_is_inactive(self):
        record = build_cosmic_chart(
            sim_id=101,
            created_at_sim_day=12,
            created_age="YOUNGADULT",
            rising_sign_index=0,
            body_sign_index_by_name=BODY_SIGNS,
            include_outer_planets=False,
        )

        self.assertEqual(
            {"Sun", "Moon", "Mercury", "Venus", "Mars", "Jupiter", "Saturn"},
            set(record.house_by_body.keys()),
        )
        self.assertNotIn("Uranus", record.metadata["body_sign_index_by_name"])

    def test_build_cosmic_chart_includes_outer_bodies_when_addon_is_active(self):
        record = build_cosmic_chart(
            sim_id=202,
            created_at_sim_day=34,
            created_age="ADULT",
            rising_sign_index=0,
            body_sign_index_by_name=BODY_SIGNS,
            include_outer_planets=True,
        )

        self.assertEqual(
            {
                "Sun",
                "Moon",
                "Mercury",
                "Venus",
                "Mars",
                "Jupiter",
                "Saturn",
                "Uranus",
                "Neptune",
                "Pluto",
                "Chiron",
            },
            set(record.house_by_body.keys()),
        )
        self.assertEqual(7, record.metadata["body_sign_index_by_name"]["Uranus"])

    def test_build_big3_chart_includes_outer_bodies_when_addon_is_active(self):
        outer_planets_activation.set_outer_planets_activation_override(True)
        record = build_big3_chart(
            sim_id=303,
            created_at_sim_day=40,
            created_age="ADULT",
            sun_sign_index=0,
            moon_sign_index=1,
            rising_sign_index=2,
            rng_seed=123,
        )

        self.assertEqual(
            {
                "Sun",
                "Moon",
                "Mercury",
                "Venus",
                "Mars",
                "Jupiter",
                "Saturn",
                "Uranus",
                "Neptune",
                "Pluto",
                "Chiron",
            },
            set(record.house_by_body.keys()),
        )
        self.assertIn("Uranus", record.metadata["body_sign_index_by_name"])


class OuterPlanetsNatalChartDialogTests(unittest.TestCase):
    def test_screen_three_text_appends_outer_bodies_in_expected_order(self):
        payload = {
            "house_by_body": {
                "Sun": 0,
                "Moon": 1,
                "Mercury": 2,
                "Venus": 3,
                "Mars": 4,
                "Jupiter": 5,
                "Saturn": 6,
                "Uranus": 7,
                "Neptune": 8,
                "Pluto": 9,
                "Chiron": 10,
            },
            "house_sign_by_index": {index: index for index in range(12)},
        }

        text = _screen_three_text(payload)

        self.assertLess(text.index("Saturn rests"), text.index("Uranus rests"))
        self.assertLess(text.index("Uranus rests"), text.index("Neptune rests"))
        self.assertLess(text.index("Neptune rests"), text.index("Pluto rests"))
        self.assertLess(text.index("Pluto rests"), text.index("Chiron rests"))

    def test_screen_three_text_skips_missing_outer_body_without_breaking(self):
        payload = {
            "house_by_body": {
                "Sun": 0,
                "Moon": 1,
                "Mercury": 2,
                "Venus": 3,
                "Mars": 4,
                "Jupiter": 5,
                "Saturn": 6,
                "Uranus": 7,
                "Neptune": 8,
                "Pluto": 9,
            },
            "house_sign_by_index": {index: index for index in range(12)},
        }

        text = _screen_three_text(payload)

        self.assertIn("Pluto rests in the 10th House, in Capricorn.", text)
        self.assertNotIn("Chiron rests", text)


class OuterPlanetsNatalChartRefreshTests(unittest.TestCase):
    def tearDown(self):
        outer_planets_activation.clear_outer_planets_activation_override()

    def test_stale_classical_payload_is_flagged_for_outer_planets_refresh(self):
        payload = {
            "house_by_body": {
                "Sun": 0,
                "Moon": 1,
                "Mercury": 2,
                "Venus": 3,
                "Mars": 4,
                "Jupiter": 5,
                "Saturn": 6,
            }
        }

        self.assertTrue(
            should_refresh_outer_planets_chart_payload(
                payload,
                include_outer_planets=True,
            )
        )

    def test_payload_with_outer_bodies_is_not_flagged_for_refresh(self):
        payload = {
            "house_by_body": {
                "Sun": 0,
                "Moon": 1,
                "Mercury": 2,
                "Venus": 3,
                "Mars": 4,
                "Jupiter": 5,
                "Saturn": 6,
                "Uranus": 7,
                "Neptune": 8,
                "Pluto": 9,
                "Chiron": 10,
            }
        }

        self.assertFalse(
            should_refresh_outer_planets_chart_payload(
                payload,
                include_outer_planets=True,
            )
        )

    def test_big3_read_refresh_overwrites_stale_payload_for_outer_planets(self):
        outer_planets_activation.set_outer_planets_activation_override(True)

        stale_payload = {
            "house_by_body": {
                "Sun": 0,
                "Moon": 1,
                "Mercury": 2,
                "Venus": 3,
                "Mars": 4,
                "Jupiter": 5,
                "Saturn": 6,
            }
        }
        fresh_payload = {
            "house_by_body": {
                **stale_payload["house_by_body"],
                "Uranus": 7,
                "Neptune": 8,
                "Pluto": 9,
                "Chiron": 10,
            }
        }

        class FakeRuntime:
            def __init__(self):
                self.capture_calls = []
                self.store_calls = []
                self.payload = dict(stale_payload)

            def get_chart_record_payload(self, sim_id):
                return dict(self.payload)

            def capture_chart_for_sim(self, sim_id=-1, reason="manual_capture"):
                self.capture_calls.append((sim_id, reason))
                return {"ok": True}

            def _store_chart_record_for_sim_info(self, sim_info, metadata=None, overwrite_existing=False):
                self.store_calls.append((sim_info, dict(metadata or {}), overwrite_existing))
                self.payload = dict(fresh_payload)
                return dict(self.payload)

        runtime = FakeRuntime()
        sim_info = object()

        payload = resolve_big3_chart_payload_for_read(runtime, 999, sim_info)

        self.assertEqual(fresh_payload, payload)
        self.assertEqual([], runtime.capture_calls)
        self.assertEqual(1, len(runtime.store_calls))
        self.assertTrue(runtime.store_calls[0][2])


if __name__ == "__main__":
    unittest.main()
