import importlib
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
PYTHON_DIR = ROOT / "python"
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))


def _import_bridge():
    return importlib.import_module("cosmic_engine.turbo_handoff_bridge")


class TurboHandoffBridgeTests(unittest.TestCase):
    def test_pair_state_payload_exposes_signs_and_awareness(self):
        bridge = _import_bridge()

        class _Tracker:
            def __init__(self, friendship_score):
                self.friendship_score = friendship_score

            def get_relationship_score(self, target_sim_id, track_id):
                return self.friendship_score if int(track_id) == 16650 else 0

            def has_relationship_bit(self, target_sim_id, bit_id):
                return int(bit_id) == 1172767005

        class _Trait:
            def __init__(self, guid64, name):
                self.guid64 = guid64
                self.__name__ = name

        class _SimInfo:
            def __init__(self, sim_id, friendship_score, traits):
                self.sim_id = sim_id
                self.relationship_tracker = _Tracker(friendship_score)
                self.trait_tracker = object()
                self._traits = traits

            def get_traits(self):
                return list(self._traits)

        actor = _SimInfo(
            101,
            24,
            [_Trait(2297406366, "PlumAntics_Big3Mod_AriesRising"), _Trait(3164395998, "PlumAntics_Big3Mod_AriesSun")],
        )
        target = _SimInfo(
            202,
            24,
            [_Trait(2588878312, "PlumAntics_Big3Mod_TaurusRising"), _Trait(4281780916, "PlumAntics_Big3Mod_TaurusSun")],
        )

        payload = bridge.build_turbo_pair_state(actor, target, awareness_skill_level=3)

        self.assertEqual("Aries", payload["actor_rising_sign_name"])
        self.assertEqual("Taurus", payload["target_sun_sign_name"])
        self.assertEqual(24, payload["friendship_score"])
        self.assertTrue(payload["sun_unlocked"])
        self.assertIn("actor_is_aware", payload)


if __name__ == "__main__":
    unittest.main()
