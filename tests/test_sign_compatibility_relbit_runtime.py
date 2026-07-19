import importlib
import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
PYTHON_DIR = ROOT / "python"
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))


def _import_loot_actions_module():
    try:
        return importlib.import_module("cosmic_engine.loot_actions")
    except ModuleNotFoundError as exc:
        if exc.name != "cosmic_engine.loot_actions":
            raise
    return None


def _import_relbits_module():
    try:
        return importlib.import_module("cosmic_engine.sign_compatibility_relbits")
    except ModuleNotFoundError as exc:
        if exc.name != "cosmic_engine.sign_compatibility_relbits":
            raise
    return None


class _FakeSimInfo(object):
    def __init__(self, sim_id):
        self.sim_id = int(sim_id)
        self.id = int(sim_id)
        self.guid64 = int(sim_id)
        self.relationship_tracker = object()


class SignCompatibilityRelbitRuntimeTests(unittest.TestCase):
    def test_seed_pair_sign_compatibility_relbits_writes_all_missing_valid_lanes(self):
        loot_actions = _import_loot_actions_module()
        relbits = _import_relbits_module()
        if loot_actions is None or relbits is None:
            raise AssertionError("Expected cosmic_engine relbit runtime modules to exist.")

        actor = _FakeSimInfo(111)
        target = _FakeSimInfo(222)
        written = []

        original_chart_payload_for_sim = loot_actions._chart_payload_for_sim
        original_resolve_rising = loot_actions._resolve_rising_sign_index_and_name
        original_resolve_state = getattr(loot_actions, "_resolve_pair_sign_compatibility_state", None)
        original_write_pair_relbit = loot_actions._write_pair_relbit

        try:
            loot_actions._chart_payload_for_sim = lambda sim_id, sim_info=None: (
                {"sun_sign_index": 0, "moon_sign_index": 4}
                if int(sim_id) == 111
                else {"sun_sign_index": 8, "moon_sign_index": 3}
            )
            loot_actions._resolve_rising_sign_index_and_name = lambda sim_info: (
                (8, "Sagittarius") if int(sim_info.sim_id) == 111 else (11, "Pisces")
            )
            loot_actions._resolve_pair_sign_compatibility_state = (
                lambda actor_sim_info, target_sim_info, lane_name: None
            )
            loot_actions._write_pair_relbit = (
                lambda actor_sim_info, target_sim_info, relbit_id: written.append(int(relbit_id)) or True
            )

            summary = loot_actions._seed_pair_sign_compatibility_relbits(actor, target)

            self.assertTrue(summary.get("ok"))
            self.assertEqual(
                [
                    relbits.RELBIT_ID_BY_LANE_STATE["Sun"]["Compatible"],
                    relbits.RELBIT_ID_BY_LANE_STATE["Moon"]["Incompatible"],
                    relbits.RELBIT_ID_BY_LANE_STATE["Rising"]["Incompatible"],
                ],
                written,
            )
        finally:
            loot_actions._chart_payload_for_sim = original_chart_payload_for_sim
            loot_actions._resolve_rising_sign_index_and_name = original_resolve_rising
            if original_resolve_state is not None:
                loot_actions._resolve_pair_sign_compatibility_state = original_resolve_state
            loot_actions._write_pair_relbit = original_write_pair_relbit

    def test_seed_pair_sign_compatibility_relbits_skips_lanes_that_are_already_known(self):
        loot_actions = _import_loot_actions_module()
        relbits = _import_relbits_module()
        if loot_actions is None or relbits is None:
            raise AssertionError("Expected cosmic_engine relbit runtime modules to exist.")

        actor = _FakeSimInfo(111)
        target = _FakeSimInfo(222)
        written = []

        original_chart_payload_for_sim = loot_actions._chart_payload_for_sim
        original_resolve_rising = loot_actions._resolve_rising_sign_index_and_name
        original_resolve_state = getattr(loot_actions, "_resolve_pair_sign_compatibility_state", None)
        original_write_pair_relbit = loot_actions._write_pair_relbit

        try:
            loot_actions._chart_payload_for_sim = lambda sim_id, sim_info=None: (
                {"sun_sign_index": 0, "moon_sign_index": 4}
                if int(sim_id) == 111
                else {"sun_sign_index": 8, "moon_sign_index": 3}
            )
            loot_actions._resolve_rising_sign_index_and_name = lambda sim_info: (
                (8, "Sagittarius") if int(sim_info.sim_id) == 111 else (11, "Pisces")
            )
            loot_actions._resolve_pair_sign_compatibility_state = (
                lambda actor_sim_info, target_sim_info, lane_name: (
                    "Compatible" if str(lane_name) == "Rising" else None
                )
            )
            loot_actions._write_pair_relbit = (
                lambda actor_sim_info, target_sim_info, relbit_id: written.append(int(relbit_id)) or True
            )

            summary = loot_actions._seed_pair_sign_compatibility_relbits(actor, target)

            self.assertTrue(summary.get("ok"))
            self.assertEqual(
                [
                    relbits.RELBIT_ID_BY_LANE_STATE["Sun"]["Compatible"],
                    relbits.RELBIT_ID_BY_LANE_STATE["Moon"]["Incompatible"],
                ],
                written,
            )
            self.assertEqual(("Rising",), tuple(summary.get("already_known_lanes", ())))
        finally:
            loot_actions._chart_payload_for_sim = original_chart_payload_for_sim
            loot_actions._resolve_rising_sign_index_and_name = original_resolve_rising
            if original_resolve_state is not None:
                loot_actions._resolve_pair_sign_compatibility_state = original_resolve_state
            loot_actions._write_pair_relbit = original_write_pair_relbit

    def test_sync_actor_sign_compatibility_visible_buffs_reads_relbits_only(self):
        loot_actions = _import_loot_actions_module()
        relbits = _import_relbits_module()
        if loot_actions is None or relbits is None:
            raise AssertionError("Expected cosmic_engine relbit runtime modules to exist.")

        actor = _FakeSimInfo(111)
        target = _FakeSimInfo(222)
        existing_buffs = {
            relbits.VISIBLE_BUFF_ID_BY_LANE_STATE["Sun"]["Neutral"],
            relbits.VISIBLE_BUFF_ID_BY_LANE_STATE["Moon"]["Neutral"],
            relbits.VISIBLE_BUFF_ID_BY_LANE_STATE["Rising"]["Compatible"],
        }
        removed = []
        added = []

        original_resolve_state = getattr(loot_actions, "_resolve_pair_sign_compatibility_state", None)
        original_sim_has_buff = loot_actions._sim_has_buff
        original_remove_buff_if_present = loot_actions._remove_buff_if_present
        original_add_buff_if_missing = loot_actions._add_buff_if_missing
        original_resolve_buff = loot_actions._resolve_buff

        try:
            state_by_lane = {
                "Sun": "Compatible",
                "Moon": None,
                "Rising": "Incompatible",
            }
            loot_actions._resolve_pair_sign_compatibility_state = (
                lambda actor_sim_info, target_sim_info, lane_name: state_by_lane[str(lane_name)]
            )
            loot_actions._sim_has_buff = lambda sim_info, buff_id: int(buff_id) in existing_buffs
            loot_actions._resolve_buff = lambda buff_id: object()

            def _fake_remove(sim_info, buff_id):
                removed.append(int(buff_id))
                existing_buffs.discard(int(buff_id))
                return True

            def _fake_add(sim_info, buff_id):
                added.append(int(buff_id))
                existing_buffs.add(int(buff_id))
                return True

            loot_actions._remove_buff_if_present = _fake_remove
            loot_actions._add_buff_if_missing = _fake_add

            summary = loot_actions._sync_actor_sign_compatibility_visible_buffs(actor, target)

            self.assertTrue(summary.get("ok"))
            self.assertIn(relbits.VISIBLE_BUFF_ID_BY_LANE_STATE["Sun"]["Neutral"], removed)
            self.assertIn(relbits.VISIBLE_BUFF_ID_BY_LANE_STATE["Moon"]["Neutral"], removed)
            self.assertIn(relbits.VISIBLE_BUFF_ID_BY_LANE_STATE["Rising"]["Compatible"], removed)
            self.assertEqual(
                [
                    relbits.VISIBLE_BUFF_ID_BY_LANE_STATE["Sun"]["Compatible"],
                    relbits.VISIBLE_BUFF_ID_BY_LANE_STATE["Rising"]["Incompatible"],
                ],
                added,
            )
        finally:
            if original_resolve_state is not None:
                loot_actions._resolve_pair_sign_compatibility_state = original_resolve_state
            loot_actions._sim_has_buff = original_sim_has_buff
            loot_actions._remove_buff_if_present = original_remove_buff_if_present
            loot_actions._add_buff_if_missing = original_add_buff_if_missing
            loot_actions._resolve_buff = original_resolve_buff

    def test_clear_sign_compatibility_runtime_lane_state_removes_relbits_and_visible_buffs(self):
        loot_actions = _import_loot_actions_module()
        relbits = _import_relbits_module()
        if loot_actions is None or relbits is None:
            raise AssertionError("Expected cosmic_engine relbit runtime modules to exist.")

        actor = _FakeSimInfo(111)
        removed_relbit_ids = []
        existing_buffs = set(relbits.VISIBLE_BUFF_ID_BY_LANE_STATE["Moon"].values())
        removed_buffs = []

        original_clear_actor_pair_relbit = loot_actions._clear_actor_pair_relbit
        original_sim_has_buff = loot_actions._sim_has_buff
        original_remove_buff_if_present = loot_actions._remove_buff_if_present

        try:
            loot_actions._clear_actor_pair_relbit = (
                lambda sim_info, relbit_id: removed_relbit_ids.append(int(relbit_id)) or 2
            )
            loot_actions._sim_has_buff = lambda sim_info, buff_id: int(buff_id) in existing_buffs

            def _fake_remove(sim_info, buff_id):
                removed_buffs.append(int(buff_id))
                existing_buffs.discard(int(buff_id))
                return True

            loot_actions._remove_buff_if_present = _fake_remove

            summary = loot_actions._clear_sign_compatibility_runtime_lane_state_from_actor(
                actor,
                "Moon",
            )

            self.assertTrue(summary.get("ok"))
            self.assertEqual(
                list(relbits.RELBIT_ID_BY_LANE_STATE["Moon"].values()),
                removed_relbit_ids,
            )
            self.assertEqual(
                list(relbits.VISIBLE_BUFF_ID_BY_LANE_STATE["Moon"].values()),
                removed_buffs,
            )
        finally:
            loot_actions._clear_actor_pair_relbit = original_clear_actor_pair_relbit
            loot_actions._sim_has_buff = original_sim_has_buff
            loot_actions._remove_buff_if_present = original_remove_buff_if_present


if __name__ == "__main__":
    unittest.main()
