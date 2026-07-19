import pathlib
import sys
import unittest
from collections import Counter


ROOT = pathlib.Path(__file__).resolve().parents[1]
PYTHON_DIR = ROOT / "python"
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))


from cosmic_engine.transit_core import RULE_BY_BODY
from cosmic_engine.transit_service import CosmicTransitService


def _signed_offset(body_index, sun_index):
    offset = (int(body_index) - int(sun_index)) % 12
    if offset > 6:
        offset -= 12
    return int(offset)


class MarsOuterTimingTests(unittest.TestCase):
    def test_mars_uses_weighted_sun_distance_bands_instead_of_staying_in_inner_envelope(self):
        service = CosmicTransitService()
        service.initialize(seed=123)
        # Prime the absolute-counter path so Sun anchoring is live.
        service.advance_from_totals(
            total_days_elapsed=0,
            total_day_progress_elapsed=0.0,
            total_segments_elapsed=0,
        )

        signed_offsets = []
        mars_interval = int(RULE_BY_BODY["Mars"].interval)
        for segment_total in range(1, 361):
            service.advance_from_totals(
                total_days_elapsed=0,
                total_day_progress_elapsed=0.0,
                total_segments_elapsed=segment_total,
            )
            if segment_total % mars_interval == 0:
                state = service.state
                signed_offsets.append(
                    _signed_offset(
                        state.sign_index_by_body["Mars"],
                        state.sign_index_by_body["Sun"],
                    )
                )

        allowed_offsets = {0, -1, 1, -2, 2, -3, 3, -4, 4, 6}
        self.assertTrue(all(offset in allowed_offsets for offset in signed_offsets))
        self.assertTrue(any(abs(offset) > 1 for offset in signed_offsets))
        self.assertFalse(any(abs(offset) == 5 for offset in signed_offsets))

        bands = Counter(abs(offset) for offset in signed_offsets)
        self.assertGreater(bands[1], bands[6])
        self.assertGreater(bands[3] + bands[4], bands[6])
        self.assertGreater(bands[0], 0)
        self.assertGreater(bands[2], 0)

    def test_mars_and_outer_body_intervals_match_the_refined_timing_model(self):
        self.assertEqual(3, RULE_BY_BODY["Mars"].interval)
        self.assertEqual(18, RULE_BY_BODY["Jupiter"].interval)
        self.assertEqual(36, RULE_BY_BODY["Saturn"].interval)
        self.assertEqual(84, RULE_BY_BODY["Uranus"].interval)
        self.assertEqual(108, RULE_BY_BODY["Neptune"].interval)
        self.assertEqual(144, RULE_BY_BODY["Pluto"].interval)


if __name__ == "__main__":
    unittest.main()
