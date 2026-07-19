import importlib
import pathlib
import sys
import unittest
import xml.etree.ElementTree as ET


sys.dont_write_bytecode = True

ROOT = pathlib.Path(__file__).resolve().parents[1]
PYTHON_DIR = ROOT / "python"
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))


first_load_chooser = importlib.import_module("cosmic_engine.first_load_chooser")


class _FakeTrait(object):
    def __init__(self, trait_id):
        self.guid64 = int(trait_id)


class _FakeTraitTracker(object):
    def __init__(self, trait_ids):
        self.equipped_traits = [_FakeTrait(trait_id) for trait_id in trait_ids]

    def add_trait(self, trait):
        trait_id = int(getattr(trait, "guid64", getattr(trait, "guid", 0)))
        if trait_id not in [item.guid64 for item in self.equipped_traits]:
            self.equipped_traits.append(_FakeTrait(trait_id))

    def remove_trait(self, trait):
        trait_id = int(getattr(trait, "guid64", getattr(trait, "guid", 0)))
        self.equipped_traits = [item for item in self.equipped_traits if int(item.guid64) != trait_id]


class _FakeHousehold(object):
    def __init__(self, sim_infos):
        self._sim_infos = tuple(sim_infos)

    def sim_info_gen(self):
        for sim_info in self._sim_infos:
            yield sim_info


class _FakeSimInfo(object):
    def __init__(self, *, trait_ids, age="ADULT", sim_id=12345, household=None):
        self.sim_id = sim_id
        self.id = sim_id
        self.age = age
        self.trait_tracker = _FakeTraitTracker(trait_ids)
        self.household = household

    def add_trait(self, trait):
        self.trait_tracker.add_trait(trait)

    def remove_trait(self, trait):
        self.trait_tracker.remove_trait(trait)


class ProgressedSunRepairTests(unittest.TestCase):
    def setUp(self):
        self._resolve_trait_tuning = first_load_chooser._resolve_trait_tuning
        self._run_loot_on_sim_info = first_load_chooser._run_loot_on_sim_info
        self._active_sim_info = first_load_chooser._active_sim_info
        self._state = dict(first_load_chooser._STATE)

    def tearDown(self):
        first_load_chooser._resolve_trait_tuning = self._resolve_trait_tuning
        first_load_chooser._run_loot_on_sim_info = self._run_loot_on_sim_info
        first_load_chooser._active_sim_info = self._active_sim_info
        first_load_chooser._STATE.clear()
        first_load_chooser._STATE.update(self._state)

    def _install_fake_trait_resolution(self):
        first_load_chooser._resolve_trait_tuning = lambda trait_id: _FakeTrait(trait_id)

    def test_repair_progressed_sun_state_rebuilds_stacked_traits(self):
        self._install_fake_trait_resolution()
        natal_aries_sun = 3164395998
        hidden_aries = 8960710436078173163
        visible_aries = 13216465842102949165
        visible_taurus = 380949979615310389
        hidden_taurus = 1637815211027082137

        sim_info = _FakeSimInfo(
            trait_ids=(natal_aries_sun, hidden_aries, visible_aries, visible_taurus),
            age="ADULT",
        )

        def _fake_router(owner, loot_id):
            self.assertEqual(first_load_chooser._PROGRESSED_SUN_REPAIR_LOOT_ID, int(loot_id))
            owner.add_trait(_FakeTrait(hidden_taurus))
            owner.add_trait(_FakeTrait(visible_taurus))
            return True

        first_load_chooser._run_loot_on_sim_info = _fake_router

        summary = first_load_chooser.repair_progressed_sun_state(sim_info)

        hidden_after = summary["hidden_after"]
        visible_after = summary["visible_after"]
        equipped_after = {int(item.guid64) for item in sim_info.trait_tracker.equipped_traits}

        self.assertTrue(summary["changed"])
        self.assertTrue(summary["consistent_after"])
        self.assertEqual((hidden_taurus,), hidden_after)
        self.assertEqual((visible_taurus,), visible_after)
        self.assertNotIn(hidden_aries, equipped_after)
        self.assertNotIn(visible_aries, equipped_after)
        self.assertEqual(2, len(summary["visible_before"]))

    def test_repair_progressed_sun_state_skips_sims_without_progressed_traits(self):
        self._install_fake_trait_resolution()
        natal_aries_sun = 3164395998
        sim_info = _FakeSimInfo(trait_ids=(natal_aries_sun,), age="ADULT")
        calls = []

        first_load_chooser._run_loot_on_sim_info = lambda *_args, **_kwargs: calls.append(True)

        summary = first_load_chooser.repair_progressed_sun_state(sim_info)

        equipped_after = {int(item.guid64) for item in sim_info.trait_tracker.equipped_traits}
        self.assertFalse(summary["changed"])
        self.assertEqual("no_progressed_state", summary["reason"])
        self.assertEqual({natal_aries_sun}, equipped_after)
        self.assertEqual([], calls)

    def test_active_household_progressed_sun_repair_runs_once_per_zone(self):
        self._install_fake_trait_resolution()
        natal_aries_sun = 3164395998
        hidden_aries = 8960710436078173163
        visible_aries = 13216465842102949165
        hidden_taurus = 1637815211027082137
        visible_taurus = 380949979615310389

        sim_a = _FakeSimInfo(
            trait_ids=(natal_aries_sun, hidden_aries, visible_aries, visible_taurus),
            age="ADULT",
            sim_id=1,
        )
        sim_b = _FakeSimInfo(trait_ids=(natal_aries_sun,), age="ADULT", sim_id=2)
        household = _FakeHousehold((sim_a, sim_b))
        sim_a.household = household
        sim_b.household = household
        first_load_chooser._active_sim_info = lambda: sim_a

        call_count = {"value": 0}

        def _fake_router(owner, loot_id):
            call_count["value"] += 1
            self.assertEqual(first_load_chooser._PROGRESSED_SUN_REPAIR_LOOT_ID, int(loot_id))
            owner.add_trait(_FakeTrait(hidden_taurus))
            owner.add_trait(_FakeTrait(visible_taurus))
            return True

        first_load_chooser._run_loot_on_sim_info = _fake_router

        changed_first = first_load_chooser.maybe_repair_active_household_progressed_sun_state()
        changed_second = first_load_chooser.maybe_repair_active_household_progressed_sun_state()

        self.assertTrue(changed_first)
        self.assertFalse(changed_second)
        self.assertEqual(1, call_count["value"])


class ProgressedSunTraitConflictTests(unittest.TestCase):
    def test_all_progressed_sun_traits_conflict_with_their_own_layer(self):
        trait_root = ROOT / "src" / "HousesandProgressions" / "Trait"

        for path in sorted(trait_root.glob("*ProgressedSun*.xml")):
            if path.name.endswith(".SimData.xml"):
                continue

            tree = ET.parse(path)
            root = tree.getroot()
            trait_id = int(root.attrib["s"])
            trait_type = tree.findtext("E[@n='trait_type']")
            conflict_ids = {
                int(node.text)
                for node in tree.findall("L[@n='conflicting_traits']/T")
                if (node.text or "").strip()
            }

            if trait_type == "HIDDEN":
                expected_ids = set(first_load_chooser._PROGRESSED_SUN_HIDDEN_TRAIT_IDS)
            elif trait_type == "GAMEPLAY":
                expected_ids = set(first_load_chooser._PROGRESSED_SUN_VISIBLE_TRAIT_IDS)
            else:
                self.fail("Unexpected trait_type for {0}: {1}".format(path.name, trait_type))

            expected_ids.discard(trait_id)
            self.assertEqual(
                expected_ids,
                conflict_ids,
                msg="Unexpected progressed-Sun conflicts in {0}".format(path.name),
            )

    def test_all_progressed_sun_simdata_conflicts_match_their_layer(self):
        trait_root = ROOT / "src" / "HousesandProgressions" / "Trait"

        for path in sorted(trait_root.glob("*ProgressedSun*.SimData.xml")):
            tree = ET.parse(path)
            instance = tree.find(".//Instances/I")
            if instance is None:
                self.fail("Missing SimData instance in {0}".format(path.name))

            trait_name = instance.attrib.get("name", "")
            conflict_ids = {
                int(node.text)
                for node in tree.findall(".//I/L[@name='conflicting_traits']/T")
                if (node.text or "").strip()
            }
            xml_name = path.name.replace(".SimData.xml", ".xml")
            xml_root = ET.parse(trait_root / xml_name).getroot()
            trait_id = int(xml_root.attrib["s"])
            trait_type = xml_root.findtext("E[@n='trait_type']")

            if trait_type == "HIDDEN":
                expected_ids = set(first_load_chooser._PROGRESSED_SUN_HIDDEN_TRAIT_IDS)
            elif trait_type == "GAMEPLAY":
                expected_ids = set(first_load_chooser._PROGRESSED_SUN_VISIBLE_TRAIT_IDS)
            else:
                self.fail(
                    "Unexpected progressed-Sun SimData trait type in {0}: {1} ({2})".format(
                        path.name,
                        trait_type,
                        trait_name,
                    )
                )

            expected_ids.discard(trait_id)
            self.assertEqual(
                expected_ids,
                conflict_ids,
                msg="Unexpected progressed-Sun SimData conflicts in {0}".format(path.name),
            )


if __name__ == "__main__":
    unittest.main()
