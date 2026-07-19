import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
PYTHON_DIR = ROOT / "python"
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))


from cosmic_engine.transit_core import TransitState
from cosmic_engine import transit_core
from cosmic_engine.transit_service import CosmicTransitService


MARS_PLUS = ("Mars", "Jupiter", "Saturn", "Chiron", "Uranus", "Neptune", "Pluto")
TETHERED = ("Sun", "Moon", "Mercury", "Venus")


class InitialMarsPlusRandomizationTests(unittest.TestCase):
    def test_new_save_initializer_keeps_tethered_bodies_and_randomizes_mars_plus(self):
        state = transit_core.random_initial_state(seed=12345)
        self.assertIsInstance(state, TransitState)
        for body in TETHERED:
            self.assertIn(body, state.sign_index_by_body)
        for body in MARS_PLUS:
            self.assertIn(body, state.sign_index_by_body)

    def test_new_save_initializer_is_deterministic_for_same_seed(self):
        a = transit_core.random_initial_state(seed=98765)
        b = transit_core.random_initial_state(seed=98765)
        self.assertEqual(a.sign_index_by_body, b.sign_index_by_body)

    def test_new_save_initializer_can_change_mars_plus_without_requiring_full_state_drift(self):
        a = transit_core.random_initial_state(seed=101)
        b = transit_core.random_initial_state(seed=202)
        self.assertTrue(
            any(a.sign_index_by_body[body] != b.sign_index_by_body[body] for body in MARS_PLUS)
        )

    def test_reseed_helper_changes_only_mars_plus(self):
        state = TransitState(
            sign_index_by_body={
                "Sun": 1,
                "Moon": 2,
                "Mercury": 1,
                "Venus": 2,
                "Mars": 3,
                "Jupiter": 4,
                "Saturn": 5,
                "Chiron": 6,
                "Uranus": 7,
                "Neptune": 8,
                "Pluto": 9,
            }
        )
        reseeded = transit_core.reseed_mars_plus_state(state, seed=444)
        for body in TETHERED:
            self.assertEqual(state.sign_index_by_body[body], reseeded.sign_index_by_body[body])
        self.assertTrue(
            any(state.sign_index_by_body[body] != reseeded.sign_index_by_body[body] for body in MARS_PLUS)
        )

    def test_first_init_path_uses_supplied_tethered_bodies_without_mutating_them(self):
        tethered = {"Sun": 8, "Moon": 3, "Mercury": 9, "Venus": 7}
        state = transit_core.random_initial_state(seed=222, tethered_sign_index_by_body=tethered)
        self.assertEqual(8, state.sign_index_by_body["Sun"])
        self.assertEqual(3, state.sign_index_by_body["Moon"])
        self.assertEqual(9, state.sign_index_by_body["Mercury"])
        self.assertEqual(7, state.sign_index_by_body["Venus"])

    def test_first_clock_snapshot_does_not_reseed_mars_plus_from_the_tethered_sky(self):
        service = CosmicTransitService()
        service.initialize(seed=123)
        initial = {
            body: int(service.state.sign_index_by_body[body])
            for body in MARS_PLUS
        }

        service.advance_from_totals(
            total_days_elapsed=0,
            total_day_progress_elapsed=0.0,
            total_segments_elapsed=8,
        )

        after = {
            body: int(service.state.sign_index_by_body[body])
            for body in MARS_PLUS
        }
        self.assertEqual(initial, after)

    def test_service_reseed_mars_plus_updates_anchor_without_touching_tethered_bodies(self):
        service = CosmicTransitService()
        service.initialize(seed=123)
        service.advance_from_totals(
            total_days_elapsed=5,
            total_day_progress_elapsed=5.0,
            total_segments_elapsed=20,
        )
        tethered_before = {
            body: int(service.state.sign_index_by_body[body])
            for body in TETHERED
        }
        mars_plus_before = {
            body: int(service.state.sign_index_by_body[body])
            for body in MARS_PLUS
        }

        summary = service.reseed_mars_plus(seed=999)

        self.assertEqual(999, summary["seed"])
        self.assertEqual(tethered_before, summary["tethered_after"])
        self.assertEqual(mars_plus_before, summary["mars_plus_before"])
        self.assertTrue(
            any(
                mars_plus_before[body] != summary["mars_plus_after"][body]
                for body in MARS_PLUS
            )
        )
        record = service.build_save_record()
        anchor = record["anchor_state_payload"]["sign_index_by_body"]
        for body in TETHERED:
            self.assertEqual(tethered_before[body], anchor[body])
        for body in MARS_PLUS:
            self.assertEqual(summary["mars_plus_after"][body], anchor[body])

    def test_bootstrap_declares_explicit_mars_plus_reseed_command(self):
        source = (ROOT / "python" / "cosmic_engine" / "bootstrap.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("ce.transit.reseed_mars_plus", source)
        self.assertIn("debug.ce_transit_reseed_mars_plus", source)

    def test_reseed_dynamic_chart_cache_clear_preserves_historical_sources(self):
        service = CosmicTransitService()
        service.set_chart_record_payload(
            101,
            {
                "metadata": {"chart_source": "clock_snapshot"},
                "sim_id": 101,
            },
        )
        service.set_chart_record_payload(
            202,
            {
                "metadata": {"chart_source": "stored_natal_markers"},
                "sim_id": 202,
            },
        )
        service.set_chart_record_payload(
            303,
            {
                "metadata": {"chart_source": "player_authored_big3"},
                "sim_id": 303,
            },
        )
        service.set_chart_record_payload(
            404,
            {
                "metadata": {"chart_source": "existing_visible_signs"},
                "sim_id": 404,
            },
        )

        summary = service.clear_dynamic_chart_record_payloads()

        self.assertEqual(2, summary["removed_count"])
        self.assertEqual(2, summary["kept_count"])
        self.assertIsNone(service.get_chart_record_payload(101))
        self.assertIsNone(service.get_chart_record_payload(404))
        self.assertIsNotNone(service.get_chart_record_payload(202))
        self.assertIsNotNone(service.get_chart_record_payload(303))


if __name__ == "__main__":
    unittest.main()
