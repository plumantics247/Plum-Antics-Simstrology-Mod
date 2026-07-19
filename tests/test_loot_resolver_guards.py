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


class _FakeResolver(object):
    def __init__(self, **attrs):
        for key, value in attrs.items():
            setattr(self, key, value)


class _FakeSimInfo(object):
    def __init__(self):
        self.sim_id = 12345
        self.household_id = 67890
        self.age = "TEEN"


class _FakeObject(object):
    def __init__(self):
        self.id = 999


class _FakeSim(object):
    def __init__(self, sim_info):
        self.sim_info = sim_info


class LootResolverGuardTests(unittest.TestCase):
    def test_resolve_actor_sim_info_accepts_embedded_sim_info(self):
        sim_info = _FakeSimInfo()
        resolver = _FakeResolver(actor=_FakeSim(sim_info))

        resolved = loot_actions._resolve_actor_sim_info(resolver)

        self.assertIs(sim_info, resolved)

    def test_resolve_actor_sim_info_rejects_non_sim_objects(self):
        resolver = _FakeResolver(actor=_FakeObject())

        resolved = loot_actions._resolve_actor_sim_info(resolver)

        self.assertIsNone(resolved)

    def test_resolve_participant_sim_info_accepts_sim_info_like_targets(self):
        sim_info = _FakeSimInfo()
        resolver = _FakeResolver(target=sim_info)

        resolved = loot_actions._resolve_participant_sim_info(resolver, ("TargetSim",))

        self.assertIs(sim_info, resolved)

    def test_resolve_participant_sim_info_rejects_object_targets_without_sim_info(self):
        resolver = _FakeResolver(target=_FakeObject())

        resolved = loot_actions._resolve_participant_sim_info(resolver, ("TargetSim",))

        self.assertIsNone(resolved)


if __name__ == "__main__":
    unittest.main()
