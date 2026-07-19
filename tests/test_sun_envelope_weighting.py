import pathlib
import sys
import unittest
from collections import Counter


sys.dont_write_bytecode = True

ROOT = pathlib.Path(__file__).resolve().parents[1]
PYTHON_DIR = ROOT / "python"
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))


from cosmic_engine.transit_service import CosmicTransitService


def _signed_offset(body_index, sun_index):
    offset = (int(body_index) - int(sun_index)) % 12
    if offset > 6:
        offset -= 12
    return int(offset)


class SunEnvelopeWeightingTests(unittest.TestCase):
    def _sample_offsets(self, *, seed=123, total_days=84):
        service = CosmicTransitService()
        service.initialize(seed=seed)
        mercury_offsets = []
        venus_offsets = []
        for day in range(total_days):
            segment_total = day % 12
            service.advance_from_totals(
                total_days_elapsed=day,
                total_day_progress_elapsed=float(day),
                total_segments_elapsed=segment_total,
            )
            state = service.state
            sun = state.sign_index_by_body["Sun"]
            mercury = state.sign_index_by_body["Mercury"]
            venus = state.sign_index_by_body["Venus"]
            mercury_offsets.append(_signed_offset(mercury, sun))
            venus_offsets.append(_signed_offset(venus, sun))
        return mercury_offsets, venus_offsets

    def test_offsets_stay_within_sun_envelope(self):
        mercury_offsets, venus_offsets = self._sample_offsets()
        self.assertTrue(all(offset in (-1, 0, 1) for offset in mercury_offsets))
        self.assertTrue(all(offset in (-1, 0, 1) for offset in venus_offsets))

    def test_offsets_do_not_jump_directly_between_edges(self):
        mercury_offsets, venus_offsets = self._sample_offsets()
        for offsets in (mercury_offsets, venus_offsets):
            for previous, current in zip(offsets, offsets[1:]):
                self.assertFalse(previous == -1 and current == 1)
                self.assertFalse(previous == 1 and current == -1)

    def test_mercury_is_more_center_biased_than_venus(self):
        mercury_offsets, venus_offsets = self._sample_offsets(total_days=168)
        mercury_counts = Counter(mercury_offsets)
        venus_counts = Counter(venus_offsets)
        self.assertGreater(mercury_counts[0], venus_counts[0])
        self.assertGreater(mercury_counts[0], mercury_counts[-1])
        self.assertGreater(mercury_counts[0], mercury_counts[1])
        self.assertGreater(venus_counts[-1] + venus_counts[1], venus_counts[0])
        self.assertGreater(venus_counts[0], 0)


if __name__ == "__main__":
    unittest.main()
