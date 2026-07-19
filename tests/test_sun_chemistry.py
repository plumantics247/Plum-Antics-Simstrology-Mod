import importlib
import pathlib
import sys
import unittest


sys.dont_write_bytecode = True

ROOT = pathlib.Path(__file__).resolve().parents[1]
PYTHON_DIR = ROOT / "python"
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))


def _import_sun_chemistry_module():
    try:
        return importlib.import_module("cosmic_engine.sun_chemistry")
    except ModuleNotFoundError as exc:
        if exc.name != "cosmic_engine.sun_chemistry":
            raise
    return None


def _import_loot_actions_module():
    try:
        return importlib.import_module("cosmic_engine.loot_actions")
    except ModuleNotFoundError as exc:
        if exc.name != "cosmic_engine.loot_actions":
            raise
    return None


def _resolve_overlay_name(tier_name, profile_id):
    module = _import_sun_chemistry_module()
    if module is None:
        raise AssertionError("Expected cosmic_engine.sun_chemistry module to exist.")
    resolver = getattr(module, "resolve_sun_overlay_name", None)
    if not callable(resolver):
        raise AssertionError(
            "Expected resolve_sun_overlay_name(tier_name, profile_id) helper in cosmic_engine.sun_chemistry."
        )
    return resolver(tier_name, profile_id)


def _resolve_overlay_id(tier_name, profile_id):
    module = _import_sun_chemistry_module()
    if module is None:
        raise AssertionError("Expected cosmic_engine.sun_chemistry module to exist.")
    resolver = getattr(module, "resolve_sun_overlay_buff_id", None)
    if not callable(resolver):
        raise AssertionError(
            "Expected resolve_sun_overlay_buff_id(tier_name, profile_id) helper in cosmic_engine.sun_chemistry."
        )
    return resolver(tier_name, profile_id)


def _resolve_active_sun_tier_name(actor_sim_info, target_sim_info):
    loot_actions = _import_loot_actions_module()
    if loot_actions is None:
        raise AssertionError("Expected cosmic_engine.loot_actions module to exist.")
    resolver = getattr(loot_actions, "_resolve_active_sun_chemistry_tier_name", None)
    if not callable(resolver):
        raise AssertionError(
            "Expected _resolve_active_sun_chemistry_tier_name(actor_sim_info, target_sim_info) helper in cosmic_engine.loot_actions."
        )
    return resolver(actor_sim_info, target_sim_info)


class SunChemistryTests(unittest.TestCase):
    def test_overlay_name_routes_dramatic_profile_to_exact_resource_name(self):
        self.assertEqual(
            "PlumAntics_CosmicEngineCore_SunChemistryOverlay_VeryCompatible_Dramatic",
            _resolve_overlay_name("VeryCompatible", "dramatic"),
        )

    def test_overlay_name_routes_subtle_profile_to_exact_resource_name(self):
        self.assertEqual(
            "PlumAntics_CosmicEngineCore_SunChemistryOverlay_SomewhatIncompatible_Subtle",
            _resolve_overlay_name("SomewhatIncompatible", "subtle"),
        )

    def test_balanced_profile_uses_base_tier_without_overlay(self):
        self.assertIsNone(_resolve_overlay_name("Neutral", "balanced"))
        self.assertIsNone(_resolve_overlay_id("Neutral", "balanced"))

    def test_pair_aware_sun_tier_resolution_reads_relationship_state_against_target(self):
        loot_actions = _import_loot_actions_module()
        if loot_actions is None:
            raise AssertionError("Expected cosmic_engine.loot_actions module to exist.")

        original_sim_has_buff = loot_actions._sim_has_buff

        class _FakeRelationshipTracker(object):
            def __init__(self):
                self.calls = []

            def has_relationship_bit(self, target_sim_id, bit_id):
                self.calls.append((int(target_sim_id), int(bit_id)))
                return int(target_sim_id) == 222 and int(bit_id) == 2587459068

        class _FakeSimInfo(object):
            def __init__(self, sim_id, tracker):
                self.sim_id = int(sim_id)
                self.relationship_tracker = tracker

        tracker = _FakeRelationshipTracker()
        actor = _FakeSimInfo(111, tracker)
        target = _FakeSimInfo(222, _FakeRelationshipTracker())

        try:
            loot_actions._sim_has_buff = lambda _sim, buff_id: int(buff_id) == 15005668881878687258

            tier_name = _resolve_active_sun_tier_name(actor, target)

            self.assertEqual("SomewhatIncompatible", tier_name)
            self.assertIn((222, 2587459068), tracker.calls)
        finally:
            loot_actions._sim_has_buff = original_sim_has_buff

    def test_sync_actor_sun_overlay_buffs_clears_existing_state_when_replacement_resource_is_missing(self):
        loot_actions = _import_loot_actions_module()
        sun_chemistry = _import_sun_chemistry_module()
        if loot_actions is None or sun_chemistry is None:
            raise AssertionError("Expected cosmic_engine loot modules to exist.")

        original_iter = sun_chemistry.iter_sun_overlay_buff_ids
        original_resolve_buff = loot_actions._resolve_buff
        original_sim_has_buff = loot_actions._sim_has_buff
        original_remove_buff_if_present = loot_actions._remove_buff_if_present
        original_add_buff_if_missing = loot_actions._add_buff_if_missing

        existing_buff_ids = {111}
        removed_buff_ids = []
        added_buff_ids = []

        try:
            sun_chemistry.iter_sun_overlay_buff_ids = lambda: (111, 333)
            loot_actions._resolve_buff = lambda buff_id: None if int(buff_id) == 333 else object()
            loot_actions._sim_has_buff = lambda _sim, buff_id: int(buff_id) in existing_buff_ids

            def _fake_remove(_sim, buff_id):
                removed_buff_ids.append(int(buff_id))
                existing_buff_ids.discard(int(buff_id))
                return True

            def _fake_add(_sim, buff_id):
                added_buff_ids.append(int(buff_id))
                existing_buff_ids.add(int(buff_id))
                return True

            loot_actions._remove_buff_if_present = _fake_remove
            loot_actions._add_buff_if_missing = _fake_add

            summary = loot_actions._sync_actor_sun_chemistry_overlay_buffs(
                object(),
                {"ok": True, "overlay_buff_id": 333},
            )

            self.assertFalse(summary.get("ok"))
            self.assertEqual("missing_buff_resource", summary.get("reason"))
            self.assertEqual(333, summary.get("applied_buff_id"))
            self.assertEqual([111], summary.get("removed_buff_ids"))
            self.assertEqual(1, summary.get("removed_count"))
            self.assertEqual([111], removed_buff_ids)
            self.assertEqual([], added_buff_ids)
            self.assertEqual(set(), existing_buff_ids)
        finally:
            sun_chemistry.iter_sun_overlay_buff_ids = original_iter
            loot_actions._resolve_buff = original_resolve_buff
            loot_actions._sim_has_buff = original_sim_has_buff
            loot_actions._remove_buff_if_present = original_remove_buff_if_present
            loot_actions._add_buff_if_missing = original_add_buff_if_missing

    def test_sync_actor_sun_overlay_buffs_clears_existing_state_when_tier_is_missing(self):
        loot_actions = _import_loot_actions_module()
        sun_chemistry = _import_sun_chemistry_module()
        if loot_actions is None or sun_chemistry is None:
            raise AssertionError("Expected cosmic_engine loot modules to exist.")

        original_iter = sun_chemistry.iter_sun_overlay_buff_ids
        original_sim_has_buff = loot_actions._sim_has_buff
        original_remove_buff_if_present = loot_actions._remove_buff_if_present
        original_add_buff_if_missing = loot_actions._add_buff_if_missing

        existing_buff_ids = {111}
        removed_buff_ids = []
        added_buff_ids = []

        try:
            sun_chemistry.iter_sun_overlay_buff_ids = lambda: (111, 333)
            loot_actions._sim_has_buff = lambda _sim, buff_id: int(buff_id) in existing_buff_ids

            def _fake_remove(_sim, buff_id):
                removed_buff_ids.append(int(buff_id))
                existing_buff_ids.discard(int(buff_id))
                return True

            def _fake_add(_sim, buff_id):
                added_buff_ids.append(int(buff_id))
                existing_buff_ids.add(int(buff_id))
                return True

            loot_actions._remove_buff_if_present = _fake_remove
            loot_actions._add_buff_if_missing = _fake_add

            summary = loot_actions._sync_actor_sun_chemistry_overlay_buffs(
                object(),
                {"ok": False, "reason": "missing_tier"},
            )

            self.assertFalse(summary.get("ok"))
            self.assertEqual("missing_tier", summary.get("reason"))
            self.assertIsNone(summary.get("applied_buff_id"))
            self.assertEqual([111], summary.get("removed_buff_ids"))
            self.assertEqual(1, summary.get("removed_count"))
            self.assertEqual([111], removed_buff_ids)
            self.assertEqual([], added_buff_ids)
            self.assertEqual(set(), existing_buff_ids)
        finally:
            sun_chemistry.iter_sun_overlay_buff_ids = original_iter
            loot_actions._sim_has_buff = original_sim_has_buff
            loot_actions._remove_buff_if_present = original_remove_buff_if_present
            loot_actions._add_buff_if_missing = original_add_buff_if_missing

    def test_sync_actor_sun_overlay_buffs_handles_none_plan_and_clears_existing_state(self):
        loot_actions = _import_loot_actions_module()
        sun_chemistry = _import_sun_chemistry_module()
        if loot_actions is None or sun_chemistry is None:
            raise AssertionError("Expected cosmic_engine loot modules to exist.")

        original_iter = sun_chemistry.iter_sun_overlay_buff_ids
        original_sim_has_buff = loot_actions._sim_has_buff
        original_remove_buff_if_present = loot_actions._remove_buff_if_present
        original_add_buff_if_missing = loot_actions._add_buff_if_missing

        existing_buff_ids = {111}
        removed_buff_ids = []
        added_buff_ids = []

        try:
            sun_chemistry.iter_sun_overlay_buff_ids = lambda: (111, 333)
            loot_actions._sim_has_buff = lambda _sim, buff_id: int(buff_id) in existing_buff_ids

            def _fake_remove(_sim, buff_id):
                removed_buff_ids.append(int(buff_id))
                existing_buff_ids.discard(int(buff_id))
                return True

            def _fake_add(_sim, buff_id):
                added_buff_ids.append(int(buff_id))
                existing_buff_ids.add(int(buff_id))
                return True

            loot_actions._remove_buff_if_present = _fake_remove
            loot_actions._add_buff_if_missing = _fake_add

            summary = loot_actions._sync_actor_sun_chemistry_overlay_buffs(
                object(),
                None,
            )

            self.assertFalse(summary.get("ok"))
            self.assertEqual("missing_buff_plan", summary.get("reason"))
            self.assertIsNone(summary.get("applied_buff_id"))
            self.assertEqual([111], summary.get("removed_buff_ids"))
            self.assertEqual(1, summary.get("removed_count"))
            self.assertEqual([111], removed_buff_ids)
            self.assertEqual([], added_buff_ids)
            self.assertEqual(set(), existing_buff_ids)
        finally:
            sun_chemistry.iter_sun_overlay_buff_ids = original_iter
            loot_actions._sim_has_buff = original_sim_has_buff
            loot_actions._remove_buff_if_present = original_remove_buff_if_present
            loot_actions._add_buff_if_missing = original_add_buff_if_missing

    def test_first_contact_sun_pass_is_skipped_when_pair_is_already_known(self):
        module = _import_sun_chemistry_module()
        if module is None:
            raise AssertionError("Expected cosmic_engine.sun_chemistry module to exist.")
        helper = getattr(module, "should_apply_first_contact_sun_pass", None)
        if not callable(helper):
            raise AssertionError(
                "Expected should_apply_first_contact_sun_pass(sun_known=False) helper in cosmic_engine.sun_chemistry."
            )
        self.assertTrue(helper(sun_known=False))
        self.assertFalse(helper(sun_known=True))


if __name__ == "__main__":
    unittest.main()
