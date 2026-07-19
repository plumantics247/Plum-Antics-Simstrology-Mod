import importlib
import pathlib
import sys
import unittest


sys.dont_write_bytecode = True

ROOT = pathlib.Path(__file__).resolve().parents[1]
PYTHON_DIR = ROOT / "python"
if ROOT.parent.name == ".worktrees":
    WORKSPACE_ROOT = ROOT.parents[2]
else:
    WORKSPACE_ROOT = ROOT.parent
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))


first_load_chooser = importlib.import_module("cosmic_engine.first_load_chooser")
CHILDHOOD_TUNING_INJECTOR = (
    WORKSPACE_ROOT
    / "PlumAntics Simstrology Childhood"
    / "src"
    / "Snippet"
    / "PlumAntics_Big3ModChildhood_TuningInjector.xml"
)


class _FakeTrait(object):
    def __init__(self, trait_id):
        self.guid64 = int(trait_id)


class _FakeTraitTracker(object):
    def __init__(self, trait_ids):
        self.equipped_traits = [_FakeTrait(trait_id) for trait_id in trait_ids]


class _FakeSimInfo(object):
    def __init__(self, *, trait_ids, age="TEEN", sim_id=12345):
        self.sim_id = sim_id
        self.id = sim_id
        self.age = age
        self.trait_tracker = _FakeTraitTracker(trait_ids)


class ChildhoodTeenHandoffBridgeTests(unittest.TestCase):
    def setUp(self):
        self._state = dict(first_load_chooser._STATE)
        self._get_mode_lock = first_load_chooser.get_mode_lock
        self._restore_mode = first_load_chooser.restore_mode_lock_from_traits
        self._apply_lane = first_load_chooser._apply_lane_handoff_state
        self._mark_dirty = first_load_chooser.mark_sim_dirty
        self._run_loot = first_load_chooser._run_loot_on_sim_info

    def tearDown(self):
        first_load_chooser._STATE.clear()
        first_load_chooser._STATE.update(self._state)
        first_load_chooser.get_mode_lock = self._get_mode_lock
        first_load_chooser.restore_mode_lock_from_traits = self._restore_mode
        first_load_chooser._apply_lane_handoff_state = self._apply_lane
        first_load_chooser.mark_sim_dirty = self._mark_dirty
        first_load_chooser._run_loot_on_sim_info = self._run_loot

    def test_repair_childhood_teen_handoff_runs_only_matching_transition_and_refresh(self):
        sim_info = _FakeSimInfo(trait_ids=(3140110952,))
        calls = []

        first_load_chooser.get_mode_lock = lambda: "none"
        first_load_chooser.restore_mode_lock_from_traits = lambda: "none"
        first_load_chooser._apply_lane_handoff_state = lambda *_args, **_kwargs: False
        first_load_chooser.mark_sim_dirty = lambda *_args, **_kwargs: None
        first_load_chooser._run_loot_on_sim_info = lambda _owner, loot_id: calls.append(int(loot_id)) or True

        summary = first_load_chooser.repair_childhood_teen_handoff(sim_info)

        self.assertTrue(summary["ok"])
        self.assertEqual(
            [
                15345425176956107593,
                13880462707991368211,
            ],
            calls,
        )

    def test_childhood_tuning_injector_uses_single_core_teen_handoff_bridge(self):
        text = CHILDHOOD_TUNING_INJECTOR.read_text(encoding="utf-8")

        self.assertIn("830000000000009138", text)
        self.assertIn("PlumAntics_CosmicEngineCore_ChildhoodTeenHandoffPythonLoot", text)
        self.assertNotIn("PlumAntics_Big3Mod_AquariusMoonChildtoAdult", text)
        self.assertNotIn("PlumAntics_Big3ModCore_SimstrologyRefreshContext_LifecycleRouter", text)

    def test_lifecycle_bridge_wrapper_delegates_to_existing_repair(self):
        calls = []
        original_repair = first_load_chooser.repair_childhood_teen_handoff
        sim_info = _FakeSimInfo(trait_ids=())

        try:
            first_load_chooser.repair_childhood_teen_handoff = lambda owner: calls.append(owner.sim_id) or {"ok": True}
            summary = first_load_chooser.repair_childhood_teen_handoff_for_lifecycle(sim_info)
        finally:
            first_load_chooser.repair_childhood_teen_handoff = original_repair

        self.assertEqual([sim_info.sim_id], calls)
        self.assertTrue(summary["ok"])


if __name__ == "__main__":
    unittest.main()
