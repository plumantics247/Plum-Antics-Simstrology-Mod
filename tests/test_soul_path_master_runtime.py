import importlib
import pathlib
import sys
import unittest


sys.dont_write_bytecode = True

ROOT = pathlib.Path(__file__).resolve().parents[1]
PYTHON_DIR = ROOT / "python"
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))


loot_actions = importlib.import_module("cosmic_engine.loot_actions")


class _FakeSimInfo(object):
    def __init__(self, sim_id):
        self.sim_id = int(sim_id)


class SoulPathMasterRuntimeTests(unittest.TestCase):
    def setUp(self):
        self._original_has_trait = loot_actions._sim_has_trait
        self._original_add_buff = loot_actions._add_buff_if_missing

    def tearDown(self):
        loot_actions._sim_has_trait = self._original_has_trait
        loot_actions._add_buff_if_missing = self._original_add_buff

    def test_reward_helper_noops_without_soul_path_master_trait(self):
        helper = getattr(loot_actions, "apply_soul_path_master_social_resolution", None)
        self.assertTrue(callable(helper))

        buff_calls = []
        loot_actions._sim_has_trait = lambda sim_info, trait_id: False
        loot_actions._add_buff_if_missing = lambda sim_info, buff_id: buff_calls.append((sim_info, buff_id)) or True

        result = helper(_FakeSimInfo(111), source="runtime.social_complete")

        self.assertEqual(
            {
                "ok": False,
                "reason": "trait_missing",
                "source": "runtime.social_complete",
            },
            result,
        )
        self.assertEqual([], buff_calls)

    def test_reward_helper_applies_confident_pulse_for_reward_trait_holder(self):
        helper = getattr(loot_actions, "apply_soul_path_master_social_resolution", None)
        self.assertTrue(callable(helper))

        sim_info = _FakeSimInfo(222)
        buff_calls = []
        loot_actions._sim_has_trait = lambda actor_sim_info, trait_id: actor_sim_info is sim_info
        loot_actions._add_buff_if_missing = lambda actor_sim_info, buff_id: buff_calls.append((actor_sim_info, buff_id)) or True

        result = helper(sim_info, source="runtime.social_complete")

        self.assertEqual(
            {
                "ok": True,
                "reason": "pulse_applied",
                "source": "runtime.social_complete",
            },
            result,
        )
        self.assertEqual(1, len(buff_calls))
        self.assertIs(sim_info, buff_calls[0][0])

    def test_reward_helper_keeps_runtime_path_trait_scoped(self):
        helper = getattr(loot_actions, "apply_soul_path_master_social_resolution", None)
        self.assertTrue(callable(helper))

        trait_holder = _FakeSimInfo(333)
        other_sim = _FakeSimInfo(444)
        buff_calls = []
        loot_actions._sim_has_trait = lambda actor_sim_info, trait_id: actor_sim_info is trait_holder
        loot_actions._add_buff_if_missing = lambda actor_sim_info, buff_id: buff_calls.append((actor_sim_info, buff_id)) or True

        helper(other_sim, source="runtime.social_complete")
        helper(trait_holder, source="runtime.social_complete")

        self.assertEqual([(trait_holder, buff_calls[0][1])], buff_calls)


if __name__ == "__main__":
    unittest.main()
