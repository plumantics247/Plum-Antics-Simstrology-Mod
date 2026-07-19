import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
PYTHON_DIR = ROOT / "python"
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))


from cosmic_engine import planet_house_markers


class _FakeTrait(object):
    def __init__(self, name, guid64):
        self.name = str(name)
        self.guid64 = int(guid64)


class _FakeSimInfo(object):
    def __init__(self):
        self.traits = ()
        self.buffs = set()


class HouseTransitBuffTests(unittest.TestCase):
    def test_core_marker_derives_matching_buff(self):
        marker = _FakeTrait(
            "PlumAntics_CosmicEngineHouses_FirstHouse_MercuryTransitMarker",
            1001,
        )
        sim_info = _FakeSimInfo()
        added = []

        original_equipped = planet_house_markers._equipped_traits_with_ids
        original_add_buff = getattr(planet_house_markers, "_add_buff_if_missing", None)
        original_remove_buff = getattr(planet_house_markers, "_remove_buff_if_present", None)
        try:
            planet_house_markers._equipped_traits_with_ids = lambda _sim: ((marker, 1001),)
            planet_house_markers._add_buff_if_missing = (
                lambda _sim, buff_id: added.append(int(buff_id)) or True
            )
            planet_house_markers._remove_buff_if_present = lambda _sim, buff_id: False

            changed = planet_house_markers._sync_house_transit_buffs_from_reward_markers(
                sim_info,
                visible_reward_body_house_by_trait_id={1001: ("Mercury", 0)},
                buff_id_by_body_house={("Mercury", 0): 2001},
                active_body_names=("Moon", "Mercury", "Sun"),
                skill_gate_enabled=True,
            )

            self.assertTrue(changed)
            self.assertEqual([2001], added)
        finally:
            planet_house_markers._equipped_traits_with_ids = original_equipped
            if original_add_buff is not None:
                planet_house_markers._add_buff_if_missing = original_add_buff
            else:
                delattr(planet_house_markers, "_add_buff_if_missing")
            if original_remove_buff is not None:
                planet_house_markers._remove_buff_if_present = original_remove_buff
            else:
                delattr(planet_house_markers, "_remove_buff_if_present")

    def test_outer_marker_derives_matching_buff(self):
        marker = _FakeTrait(
            "PlumAntics_CosmicEngineHouses_TenthHouse_PlutoTransitMarker",
            1101,
        )
        sim_info = _FakeSimInfo()
        added = []

        original_equipped = planet_house_markers._equipped_traits_with_ids
        original_add_buff = getattr(planet_house_markers, "_add_buff_if_missing", None)
        original_remove_buff = getattr(planet_house_markers, "_remove_buff_if_present", None)
        try:
            planet_house_markers._equipped_traits_with_ids = lambda _sim: ((marker, 1101),)
            planet_house_markers._add_buff_if_missing = (
                lambda _sim, buff_id: added.append(int(buff_id)) or True
            )
            planet_house_markers._remove_buff_if_present = lambda _sim, buff_id: False

            changed = planet_house_markers._sync_house_transit_buffs_from_reward_markers(
                sim_info,
                visible_reward_body_house_by_trait_id={1101: ("Pluto", 9)},
                buff_id_by_body_house={("Pluto", 9): 2101},
                active_body_names=("Moon", "Mercury", "Sun", "Pluto"),
                skill_gate_enabled=True,
            )

            self.assertTrue(changed)
            self.assertEqual([2101], added)
        finally:
            planet_house_markers._equipped_traits_with_ids = original_equipped
            if original_add_buff is not None:
                planet_house_markers._add_buff_if_missing = original_add_buff
            else:
                delattr(planet_house_markers, "_add_buff_if_missing")
            if original_remove_buff is not None:
                planet_house_markers._remove_buff_if_present = original_remove_buff
            else:
                delattr(planet_house_markers, "_remove_buff_if_present")

    def test_slowest_planet_wins_inside_same_house(self):
        jupiter = _FakeTrait(
            "PlumAntics_CosmicEngineHouses_FourthHouse_JupiterTransitMarker",
            1201,
        )
        saturn = _FakeTrait(
            "PlumAntics_CosmicEngineHouses_FourthHouse_SaturnTransitMarker",
            1202,
        )
        sim_info = _FakeSimInfo()
        added = []
        removed = []
        equipped_buffs = set()

        original_equipped = planet_house_markers._equipped_traits_with_ids
        original_add_buff = getattr(planet_house_markers, "_add_buff_if_missing", None)
        original_remove_buff = getattr(planet_house_markers, "_remove_buff_if_present", None)
        try:
            planet_house_markers._equipped_traits_with_ids = (
                lambda _sim: ((jupiter, 1201), (saturn, 1202))
            )
            planet_house_markers._add_buff_if_missing = (
                lambda _sim, buff_id: (
                    added.append(int(buff_id)) or equipped_buffs.add(int(buff_id)) or True
                )
            )
            planet_house_markers._remove_buff_if_present = (
                lambda _sim, buff_id: (
                    removed.append(int(buff_id)) or equipped_buffs.remove(int(buff_id)) is None
                ) if int(buff_id) in equipped_buffs else False
            )

            changed = planet_house_markers._sync_house_transit_buffs_from_reward_markers(
                sim_info,
                visible_reward_body_house_by_trait_id={
                    1201: ("Jupiter", 3),
                    1202: ("Saturn", 3),
                },
                buff_id_by_body_house={
                    ("Jupiter", 3): 2201,
                    ("Saturn", 3): 2202,
                },
                active_body_names=("Moon", "Mercury", "Sun", "Jupiter", "Saturn"),
                skill_gate_enabled=True,
            )

            self.assertTrue(changed)
            self.assertEqual([2202], added)
            self.assertEqual([], removed)
        finally:
            planet_house_markers._equipped_traits_with_ids = original_equipped
            if original_add_buff is not None:
                planet_house_markers._add_buff_if_missing = original_add_buff
            else:
                delattr(planet_house_markers, "_add_buff_if_missing")
            if original_remove_buff is not None:
                planet_house_markers._remove_buff_if_present = original_remove_buff
            else:
                delattr(planet_house_markers, "_remove_buff_if_present")

    def test_skill_gate_removes_existing_house_transit_buffs(self):
        marker = _FakeTrait(
            "PlumAntics_CosmicEngineHouses_FirstHouse_MercuryTransitMarker",
            1301,
        )
        sim_info = _FakeSimInfo()
        removed = []

        original_equipped = planet_house_markers._equipped_traits_with_ids
        original_add_buff = getattr(planet_house_markers, "_add_buff_if_missing", None)
        original_remove_buff = getattr(planet_house_markers, "_remove_buff_if_present", None)
        try:
            planet_house_markers._equipped_traits_with_ids = lambda _sim: ((marker, 1301),)
            planet_house_markers._add_buff_if_missing = lambda _sim, buff_id: False
            planet_house_markers._remove_buff_if_present = (
                lambda _sim, buff_id: removed.append(int(buff_id)) or True
            )

            changed = planet_house_markers._sync_house_transit_buffs_from_reward_markers(
                sim_info,
                visible_reward_body_house_by_trait_id={1301: ("Mercury", 0)},
                buff_id_by_body_house={("Mercury", 0): 2301},
                active_body_names=("Moon", "Mercury", "Sun"),
                skill_gate_enabled=False,
            )

            self.assertTrue(changed)
            self.assertEqual([2301], removed)
        finally:
            planet_house_markers._equipped_traits_with_ids = original_equipped
            if original_add_buff is not None:
                planet_house_markers._add_buff_if_missing = original_add_buff
            else:
                delattr(planet_house_markers, "_add_buff_if_missing")
            if original_remove_buff is not None:
                planet_house_markers._remove_buff_if_present = original_remove_buff
            else:
                delattr(planet_house_markers, "_remove_buff_if_present")


if __name__ == "__main__":
    unittest.main()
