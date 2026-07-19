import importlib
import pathlib
import sys
import unittest


sys.dont_write_bytecode = True

ROOT = pathlib.Path(__file__).resolve().parents[1]
PYTHON_DIR = ROOT / "python"
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))


def _import_pair_memory_module():
    try:
        return importlib.import_module("cosmic_engine.chemistry_pair_memory")
    except ModuleNotFoundError as exc:
        if exc.name != "cosmic_engine.chemistry_pair_memory":
            raise
    return None


def _import_loot_actions_module():
    try:
        return importlib.import_module("cosmic_engine.loot_actions")
    except ModuleNotFoundError as exc:
        if exc.name != "cosmic_engine.loot_actions":
            raise
    return None


def _pair_write_decision(refresh_summary, *, rising_known=False, sun_known=False):
    module = _import_pair_memory_module()
    if module is None:
        raise AssertionError("Expected cosmic_engine.chemistry_pair_memory module to exist.")
    resolver = getattr(module, "build_pair_memory_write_summary", None)
    if not callable(resolver):
        raise AssertionError(
            "Expected build_pair_memory_write_summary(...) helper in cosmic_engine.chemistry_pair_memory."
        )
    summary = resolver(
        refresh_summary,
        rising_known=rising_known,
        sun_known=sun_known,
    )
    if not isinstance(summary, dict):
        raise AssertionError("build_pair_memory_write_summary(...) must return a dict.")
    return summary


class _FakeRelationshipTracker(object):
    def __init__(self, present_relbits_by_target=None, fail_add_relbits_by_target=None):
        present_relbits_by_target = present_relbits_by_target or {}
        fail_add_relbits_by_target = fail_add_relbits_by_target or {}
        self.present_relbits_by_target = {
            int(target_sim_id): {int(relbit_id) for relbit_id in tuple(relbit_ids)}
            for target_sim_id, relbit_ids in present_relbits_by_target.items()
        }
        self.fail_add_relbits_by_target = {
            int(target_sim_id): {int(relbit_id) for relbit_id in tuple(relbit_ids)}
            for target_sim_id, relbit_ids in fail_add_relbits_by_target.items()
        }
        self.added = []
        self.removed = []

    def has_relationship_bit(self, target_sim_id, bit_id):
        return int(bit_id) in self.present_relbits_by_target.get(int(target_sim_id), set())

    def add_relationship_bit(self, target_sim_id, bit_id):
        target_sim_id = int(target_sim_id)
        bit_id = int(bit_id)
        if bit_id in self.fail_add_relbits_by_target.get(target_sim_id, set()):
            return False
        self.added.append(bit_id)
        self.present_relbits_by_target.setdefault(target_sim_id, set()).add(bit_id)
        return True

    def remove_relationship_bit(self, target_sim_id, bit_id):
        target_sim_id = int(target_sim_id)
        bit_id = int(bit_id)
        relbits = self.present_relbits_by_target.get(target_sim_id, set())
        if bit_id not in relbits:
            return False
        self.removed.append(bit_id)
        relbits.discard(bit_id)
        return True


class _FakeSimInfo(object):
    def __init__(self, sim_id, present_relbits_by_target=None, fail_add_relbits_by_target=None):
        self.sim_id = int(sim_id)
        self.relationship_tracker = _FakeRelationshipTracker(
            present_relbits_by_target=present_relbits_by_target,
            fail_add_relbits_by_target=fail_add_relbits_by_target,
        )


class _FakeResolver(object):
    def __init__(self, actor_sim_info):
        self.actor = actor_sim_info


class ChemistryPairMemoryTests(unittest.TestCase):
    def test_valid_sign_data_writes_both_relbits_together(self):
        summary = _pair_write_decision(
            {
                "ok": True,
                "actor_rising_sign_name": "Aquarius",
                "target_rising_sign_name": "Leo",
                "actor_sun_sign_name": "Aries",
                "target_sun_sign_name": "Cancer",
            }
        )

        self.assertTrue(summary.get("ok"))
        self.assertEqual("write_both", summary.get("reason"))
        self.assertEqual(["RisingKnown", "SunKnown"], summary.get("relbits_to_write"))
        self.assertEqual(
            [830000000000009601, 830000000000009602],
            summary.get("relbit_ids"),
        )

    def test_missing_any_chart_data_writes_neither_relbit(self):
        summary = _pair_write_decision(
            {
                "ok": True,
                "actor_rising_sign_name": "Aquarius",
                "target_rising_sign_name": None,
                "actor_sun_sign_name": "Aries",
                "target_sun_sign_name": "Cancer",
            }
        )

        self.assertFalse(summary.get("ok"))
        self.assertEqual("missing_sign_data", summary.get("reason"))
        self.assertEqual([], summary.get("relbits_to_write"))

    def test_invalid_refresh_state_with_populated_signs_writes_neither_relbit(self):
        summary = _pair_write_decision(
            {
                "ok": False,
                "actor_rising_sign_name": "Aquarius",
                "target_rising_sign_name": "Leo",
                "actor_sun_sign_name": "Aries",
                "target_sun_sign_name": "Cancer",
            }
        )

        self.assertFalse(summary.get("ok"))
        self.assertEqual("missing_sign_data", summary.get("reason"))
        self.assertEqual([], summary.get("relbits_to_write"))

    def test_existing_known_state_skips_duplicate_write(self):
        summary = _pair_write_decision(
            {
                "ok": True,
                "actor_rising_sign_name": "Aquarius",
                "target_rising_sign_name": "Leo",
                "actor_sun_sign_name": "Aries",
                "target_sun_sign_name": "Cancer",
            },
            rising_known=True,
            sun_known=True,
        )

        self.assertTrue(summary.get("ok"))
        self.assertEqual("already_known", summary.get("reason"))
        self.assertEqual([], summary.get("relbits_to_write"))

    def test_half_known_pair_still_writes_both_relbits_to_restore_symmetric_state(self):
        summary = _pair_write_decision(
            {
                "ok": True,
                "actor_rising_sign_name": "Aquarius",
                "target_rising_sign_name": "Leo",
                "actor_sun_sign_name": "Aries",
                "target_sun_sign_name": "Cancer",
            },
            rising_known=True,
            sun_known=False,
        )

        self.assertTrue(summary.get("ok"))
        self.assertEqual("write_both", summary.get("reason"))
        self.assertEqual(["RisingKnown", "SunKnown"], summary.get("relbits_to_write"))
        self.assertEqual(
            [830000000000009601, 830000000000009602],
            summary.get("relbit_ids"),
        )

    def test_loot_actions_pair_known_state_reads_hidden_relbits_by_layer(self):
        loot_actions = _import_loot_actions_module()
        if loot_actions is None:
            raise AssertionError("Expected cosmic_engine.loot_actions module to exist.")
        helper = getattr(loot_actions, "_pair_has_relbit", None)
        if not callable(helper):
            raise AssertionError(
                "Expected _pair_has_relbit(actor_sim_info, target_sim_info, relbit_id) helper in cosmic_engine.loot_actions."
            )

        actor = _FakeSimInfo(111, present_relbits_by_target={222: (830000000000009601,)})
        target = _FakeSimInfo(222, present_relbits_by_target={111: (830000000000009601,)})

        self.assertTrue(helper(actor, target, 830000000000009601))
        self.assertFalse(helper(actor, target, 830000000000009602))

    def test_loot_actions_pair_known_state_requires_same_relbit_on_both_directions(self):
        loot_actions = _import_loot_actions_module()
        if loot_actions is None:
            raise AssertionError("Expected cosmic_engine.loot_actions module to exist.")
        helper = getattr(loot_actions, "_pair_has_relbit", None)
        if not callable(helper):
            raise AssertionError(
                "Expected _pair_has_relbit(actor_sim_info, target_sim_info, relbit_id) helper in cosmic_engine.loot_actions."
            )

        actor = _FakeSimInfo(111, present_relbits_by_target={222: (830000000000009601,)})
        target = _FakeSimInfo(222, present_relbits_by_target={111: (830000000000009602,)})

        self.assertFalse(helper(actor, target, 830000000000009601))
        self.assertFalse(helper(actor, target, 830000000000009602))

    def test_loot_actions_pair_write_helper_only_writes_when_contract_says_write_both(self):
        loot_actions = _import_loot_actions_module()
        if loot_actions is None:
            raise AssertionError("Expected cosmic_engine.loot_actions module to exist.")
        helper = getattr(loot_actions, "_write_pair_relbit", None)
        if not callable(helper):
            raise AssertionError(
                "Expected _write_pair_relbit(actor_sim_info, target_sim_info, relbit_id) helper in cosmic_engine.loot_actions."
            )

        actor = _FakeSimInfo(111)
        target = _FakeSimInfo(222)

        self.assertTrue(helper(actor, target, 830000000000009601))
        self.assertTrue(helper(actor, target, 830000000000009602))
        self.assertEqual(
            [830000000000009601, 830000000000009602],
            actor.relationship_tracker.added,
        )
        self.assertEqual(
            [830000000000009601, 830000000000009602],
            target.relationship_tracker.added,
        )

    def test_loot_actions_pair_write_helper_fails_when_one_direction_cannot_be_aligned(self):
        loot_actions = _import_loot_actions_module()
        if loot_actions is None:
            raise AssertionError("Expected cosmic_engine.loot_actions module to exist.")
        helper = getattr(loot_actions, "_write_pair_relbit", None)
        if not callable(helper):
            raise AssertionError(
                "Expected _write_pair_relbit(actor_sim_info, target_sim_info, relbit_id) helper in cosmic_engine.loot_actions."
            )

        actor = _FakeSimInfo(111)
        target = _FakeSimInfo(222, fail_add_relbits_by_target={111: (830000000000009601,)})

        self.assertFalse(helper(actor, target, 830000000000009601))
        self.assertFalse(actor.relationship_tracker.has_relationship_bit(222, 830000000000009601))
        self.assertFalse(target.relationship_tracker.has_relationship_bit(111, 830000000000009601))

    def test_loot_actions_pair_write_helper_preserves_preexisting_half_state_on_failed_repair(self):
        loot_actions = _import_loot_actions_module()
        if loot_actions is None:
            raise AssertionError("Expected cosmic_engine.loot_actions module to exist.")
        helper = getattr(loot_actions, "_write_pair_relbit", None)
        if not callable(helper):
            raise AssertionError(
                "Expected _write_pair_relbit(actor_sim_info, target_sim_info, relbit_id) helper in cosmic_engine.loot_actions."
            )

        actor = _FakeSimInfo(111, present_relbits_by_target={222: (830000000000009601,)})
        target = _FakeSimInfo(222, fail_add_relbits_by_target={111: (830000000000009601,)})

        self.assertFalse(helper(actor, target, 830000000000009601))
        self.assertTrue(actor.relationship_tracker.has_relationship_bit(222, 830000000000009601))
        self.assertFalse(target.relationship_tracker.has_relationship_bit(111, 830000000000009601))

    def test_clear_known_chemistry_helper_only_removes_requested_layer(self):
        loot_actions = _import_loot_actions_module()
        if loot_actions is None:
            raise AssertionError("Expected cosmic_engine.loot_actions module to exist.")
        helper = getattr(loot_actions, "_clear_actor_pair_relbit", None)
        if not callable(helper):
            raise AssertionError(
                "Expected _clear_actor_pair_relbit(actor_sim_info, relbit_id) helper in cosmic_engine.loot_actions."
            )

        actor = _FakeSimInfo(
            111,
            present_relbits_by_target={
                222: (830000000000009601, 830000000000009602),
                333: (830000000000009601,),
            },
        )
        target_a = _FakeSimInfo(
            222,
            present_relbits_by_target={111: (830000000000009601,)},
        )
        target_b = _FakeSimInfo(
            333,
            present_relbits_by_target={111: (830000000000009601, 830000000000009602)},
        )

        original_iter_all = getattr(loot_actions, "_iter_all_sim_infos", None)
        loot_actions._iter_all_sim_infos = lambda: (actor, target_a, target_b)

        try:
            removed_count = helper(actor, 830000000000009601)
        finally:
            loot_actions._iter_all_sim_infos = original_iter_all

        self.assertEqual(4, removed_count)
        self.assertFalse(actor.relationship_tracker.has_relationship_bit(222, 830000000000009601))
        self.assertTrue(actor.relationship_tracker.has_relationship_bit(222, 830000000000009602))
        self.assertFalse(actor.relationship_tracker.has_relationship_bit(333, 830000000000009601))
        self.assertFalse(target_a.relationship_tracker.has_relationship_bit(111, 830000000000009601))
        self.assertFalse(target_b.relationship_tracker.has_relationship_bit(111, 830000000000009601))
        self.assertTrue(target_b.relationship_tracker.has_relationship_bit(111, 830000000000009602))

    def test_clear_known_chemistry_loot_resolves_actor_and_clears_only_sun_layer(self):
        loot_actions = _import_loot_actions_module()
        if loot_actions is None:
            raise AssertionError("Expected cosmic_engine.loot_actions module to exist.")
        loot_cls = getattr(loot_actions, "CosmicEngineClearKnownChemistryLoot", None)
        if loot_cls is None:
            raise AssertionError(
                "Expected CosmicEngineClearKnownChemistryLoot in cosmic_engine.loot_actions."
            )

        actor = _FakeSimInfo(
            111,
            present_relbits_by_target={
                222: (830000000000009601, 830000000000009602),
                333: (830000000000009602,),
            },
        )
        resolver = _FakeResolver(actor)
        loot = loot_cls()
        loot.layer_name = "sun"

        loot.apply_to_resolver(resolver)

        self.assertTrue(actor.relationship_tracker.has_relationship_bit(222, 830000000000009601))
        self.assertFalse(actor.relationship_tracker.has_relationship_bit(222, 830000000000009602))
        self.assertFalse(actor.relationship_tracker.has_relationship_bit(333, 830000000000009602))


if __name__ == "__main__":
    unittest.main()
