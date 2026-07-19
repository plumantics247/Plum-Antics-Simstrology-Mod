import pathlib
import sys
import unittest
from types import SimpleNamespace


ROOT = pathlib.Path(__file__).resolve().parents[1]
PYTHON_DIR = ROOT / "python"
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))


from cosmic_engine import crystal_resonance_activation
from cosmic_engine.chart_records import SIGNS


class _FakeInventoryObject(object):
    def __init__(self, definition_name, object_id, *, state_component=None):
        self.id = int(object_id)
        self.guid64 = int(object_id)
        self.definition = SimpleNamespace(name=str(definition_name))
        self.state_component = state_component


class _FakeInventoryComponent(object):
    def __init__(self, objects):
        self._objects = tuple(objects)

    def inventory_items_gen(self):
        for obj in self._objects:
            yield obj


class _FakeSimInfo(object):
    def __init__(self, sim_id, inventory_objects=(), live_inventory_objects=None):
        self.sim_id = int(sim_id)
        self.id = int(sim_id)
        self.inventory_component = _FakeInventoryComponent(inventory_objects)
        self._live_sim = None
        if live_inventory_objects is not None:
            self._live_sim = SimpleNamespace(
                inventory_component=_FakeInventoryComponent(live_inventory_objects),
            )

    def get_sim_instance(self):
        return self._live_sim


class CrystalResonanceTests(unittest.TestCase):
    def tearDown(self):
        crystal_resonance_activation.clear_crystal_resonance_activation_override()

    def _payload(self, sun, moon, rising):
        return {
            "sun_sign_index": SIGNS.index(sun),
            "moon_sign_index": SIGNS.index(moon),
            "rising_sign_index": SIGNS.index(rising),
        }

    def test_primary_crystal_table_matches_approved_sign_map(self):
        from cosmic_engine.crystal_resonance import PRIMARY_CRYSTAL_BY_SIGN

        self.assertEqual("Diamond", PRIMARY_CRYSTAL_BY_SIGN["Aries"])
        self.assertEqual("Emerald", PRIMARY_CRYSTAL_BY_SIGN["Taurus"])
        self.assertEqual("Citrine", PRIMARY_CRYSTAL_BY_SIGN["Gemini"])
        self.assertEqual("Ruby", PRIMARY_CRYSTAL_BY_SIGN["Cancer"])
        self.assertEqual("Fire Opal", PRIMARY_CRYSTAL_BY_SIGN["Leo"])
        self.assertEqual("Sapphire", PRIMARY_CRYSTAL_BY_SIGN["Virgo"])
        self.assertEqual("Rose", PRIMARY_CRYSTAL_BY_SIGN["Libra"])
        self.assertEqual("Turquoise", PRIMARY_CRYSTAL_BY_SIGN["Scorpio"])
        self.assertEqual("Orange Topaz", PRIMARY_CRYSTAL_BY_SIGN["Sagittarius"])
        self.assertEqual("Jet", PRIMARY_CRYSTAL_BY_SIGN["Capricorn"])
        self.assertEqual("Amethyst", PRIMARY_CRYSTAL_BY_SIGN["Aquarius"])
        self.assertEqual("Quartz", PRIMARY_CRYSTAL_BY_SIGN["Pisces"])

    def test_unique_matching_keys_stack_across_big3_but_duplicate_objects_do_not(self):
        from cosmic_engine.crystal_resonance import collect_matching_crystal_keys_for_sim

        sim_info = _FakeSimInfo(
            101,
            inventory_objects=(
                _FakeInventoryObject("collectible_Crystal_Diamond", 1),
                _FakeInventoryObject("collectible_Crystal_Diamond", 2),
                _FakeInventoryObject("collectible_Crystal_Ruby", 3),
                _FakeInventoryObject("collectible_Crystal_FireOpal", 4),
            ),
        )

        keys = collect_matching_crystal_keys_for_sim(
            sim_info,
            chart_payload=self._payload("Aries", "Cancer", "Leo"),
        )

        self.assertEqual(("Diamond", "Fire Opal", "Ruby"), keys)

    def test_non_matching_inventory_items_are_ignored(self):
        from cosmic_engine.crystal_resonance import collect_matching_crystal_keys_for_sim

        sim_info = _FakeSimInfo(
            102,
            inventory_objects=(
                _FakeInventoryObject("collectible_Crystal_Emerald", 10),
                _FakeInventoryObject("collectible_Crystal_Turquoise", 11),
            ),
        )

        keys = collect_matching_crystal_keys_for_sim(
            sim_info,
            chart_payload=self._payload("Aries", "Cancer", "Leo"),
        )

        self.assertEqual((), keys)

    def test_live_sim_inventory_is_used_when_sim_info_inventory_is_empty(self):
        from cosmic_engine.crystal_resonance import collect_matching_crystal_keys_for_sim

        sim_info = _FakeSimInfo(
            103,
            inventory_objects=(),
            live_inventory_objects=(_FakeInventoryObject("collectible_Crystal_Diamond", 21),),
        )

        keys = collect_matching_crystal_keys_for_sim(
            sim_info,
            chart_payload=self._payload("Aries", "Cancer", "Leo"),
        )

        self.assertEqual(("Diamond",), keys)

    def test_state_driven_gemology_object_matches_when_definition_name_is_generic(self):
        from cosmic_engine.crystal_resonance import collect_matching_crystal_keys_for_sim

        sim_info = _FakeSimInfo(
            104,
            inventory_objects=(
                _FakeInventoryObject(
                    "object_gemologyTable_CraftingObject_CutGemstone",
                    31,
                    state_component={
                        "crystal_state": SimpleNamespace(name="crystalType_Diamond"),
                        "metal_state": SimpleNamespace(name="metalType_Gold"),
                    },
                ),
            ),
        )

        keys = collect_matching_crystal_keys_for_sim(
            sim_info,
            chart_payload=self._payload("Aries", "Cancer", "Leo"),
        )

        self.assertEqual(("Diamond",), keys)

    def test_attunement_registry_expires_and_falls_back_to_passive_resonance(self):
        from cosmic_engine.crystal_resonance import (
            active_attunement_keys_for_sim,
            expire_attunements,
            register_gifted_attunement,
        )

        register_gifted_attunement(5001, "Diamond", object_id=9001, now_ticks=100, duration_ticks=20)
        self.assertEqual(("Diamond",), active_attunement_keys_for_sim(5001, now_ticks=110))

        expire_attunements(now_ticks=121)
        self.assertEqual((), active_attunement_keys_for_sim(5001, now_ticks=121))

    def test_activation_helper_defaults_false_without_marker(self):
        from cosmic_engine.crystal_resonance_activation import is_crystal_resonance_addon_active

        crystal_resonance_activation.set_crystal_resonance_activation_override(False)
        self.assertFalse(is_crystal_resonance_addon_active())

    def test_sync_crystal_resonance_adds_passive_buff_for_matching_key(self):
        from cosmic_engine import crystal_resonance
        from cosmic_engine import loot_actions

        crystal_resonance_activation.set_crystal_resonance_activation_override(True)
        sim_info = _FakeSimInfo(
            777,
            inventory_objects=(_FakeInventoryObject("collectible_Crystal_Diamond", 1),),
        )
        added = []
        removed = []

        original_add = loot_actions._add_buff_if_missing
        original_remove = loot_actions._remove_buff_if_present
        original_payload = crystal_resonance.chart_payload_for_sim
        try:
            loot_actions._add_buff_if_missing = lambda _sim, buff_id: added.append(int(buff_id)) or True
            loot_actions._remove_buff_if_present = lambda _sim, buff_id: removed.append(int(buff_id)) or False
            crystal_resonance.chart_payload_for_sim = lambda _sim: self._payload("Aries", "Cancer", "Leo")

            summary = crystal_resonance.sync_crystal_resonance((sim_info,), now_ticks=10)

            self.assertEqual(1, summary["sims_seen"])
            self.assertIn(crystal_resonance.PASSIVE_BUFF_ID_BY_CRYSTAL_KEY["Diamond"], added)
        finally:
            loot_actions._add_buff_if_missing = original_add
            loot_actions._remove_buff_if_present = original_remove
            crystal_resonance.chart_payload_for_sim = original_payload

    def test_gifted_attunement_overrides_passive_lane_for_same_key(self):
        from cosmic_engine import crystal_resonance
        from cosmic_engine import loot_actions

        crystal_resonance_activation.set_crystal_resonance_activation_override(True)
        sim_info = _FakeSimInfo(
            778,
            inventory_objects=(_FakeInventoryObject("collectible_Crystal_Diamond", 99),),
        )
        added = []

        original_add = loot_actions._add_buff_if_missing
        original_remove = loot_actions._remove_buff_if_present
        original_payload = crystal_resonance.chart_payload_for_sim
        try:
            loot_actions._add_buff_if_missing = lambda _sim, buff_id: added.append(int(buff_id)) or True
            loot_actions._remove_buff_if_present = lambda _sim, buff_id: False
            crystal_resonance.chart_payload_for_sim = lambda _sim: self._payload("Aries", "Cancer", "Leo")
            crystal_resonance.register_gifted_attunement(778, "Diamond", object_id=99, now_ticks=100, duration_ticks=50)

            crystal_resonance.sync_crystal_resonance((sim_info,), now_ticks=110)

            self.assertIn(crystal_resonance.ATTUNEMENT_BUFF_ID_BY_CRYSTAL_KEY["Diamond"], added)
            self.assertNotIn(crystal_resonance.PASSIVE_BUFF_ID_BY_CRYSTAL_KEY["Diamond"], added)
        finally:
            loot_actions._add_buff_if_missing = original_add
            loot_actions._remove_buff_if_present = original_remove
            crystal_resonance.chart_payload_for_sim = original_payload

    def test_debug_payload_reports_allowed_matching_and_attuned_keys(self):
        from cosmic_engine import crystal_resonance

        crystal_resonance_activation.set_crystal_resonance_activation_override(True)
        sim_info = _FakeSimInfo(
            880,
            inventory_objects=(_FakeInventoryObject("collectible_Crystal_Diamond", 91),),
        )

        original_payload = crystal_resonance.chart_payload_for_sim
        try:
            crystal_resonance.chart_payload_for_sim = lambda _sim: self._payload("Aries", "Cancer", "Leo")
            crystal_resonance.register_gifted_attunement(880, "Diamond", object_id=91, now_ticks=100, duration_ticks=50)

            payload = crystal_resonance.debug_crystal_resonance_for_sim(sim_info, now_ticks=120)

            self.assertTrue(payload.get("addon_active"))
            self.assertEqual(("Diamond", "Fire Opal", "Ruby"), tuple(payload.get("allowed_keys") or ()))
            self.assertEqual(("Diamond",), tuple(payload.get("matching_keys") or ()))
            self.assertEqual(("Diamond",), tuple(payload.get("attuned_keys") or ()))
        finally:
            crystal_resonance.chart_payload_for_sim = original_payload

    def test_debug_payload_reports_present_passive_and_attunement_buff_keys(self):
        from cosmic_engine import crystal_resonance

        crystal_resonance_activation.set_crystal_resonance_activation_override(True)
        sim_info = _FakeSimInfo(
            881,
            inventory_objects=(_FakeInventoryObject("collectible_Crystal_Diamond", 92),),
        )

        original_payload = crystal_resonance.chart_payload_for_sim
        original_has_buff = getattr(crystal_resonance, "_sim_has_buff", None)
        try:
            crystal_resonance.chart_payload_for_sim = lambda _sim: self._payload("Aries", "Cancer", "Leo")
            crystal_resonance.register_gifted_attunement(881, "Diamond", object_id=92, now_ticks=100, duration_ticks=50)
            crystal_resonance._sim_has_buff = lambda _sim, buff_id: int(buff_id) in {
                crystal_resonance.PASSIVE_BUFF_ID_BY_CRYSTAL_KEY["Diamond"],
                crystal_resonance.ATTUNEMENT_BUFF_ID_BY_CRYSTAL_KEY["Diamond"],
            }

            payload = crystal_resonance.debug_crystal_resonance_for_sim(sim_info, now_ticks=120)

            self.assertEqual(("Diamond",), tuple(payload.get("present_passive_buff_keys") or ()))
            self.assertEqual(("Diamond",), tuple(payload.get("present_attunement_buff_keys") or ()))
        finally:
            crystal_resonance.chart_payload_for_sim = original_payload
            if original_has_buff is not None:
                crystal_resonance._sim_has_buff = original_has_buff


if __name__ == "__main__":
    unittest.main()
