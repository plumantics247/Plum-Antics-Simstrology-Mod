import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
PYTHON_DIR = ROOT / "python"
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))


from astrocore.domains.solar_boosts import (
    ANGULAR_SOLAR_BUFF_KEY_BY_HOUSE_INDEX,
    ELEMENT_SUPPORT_BUFF_KEY_BY_ELEMENT,
    MOON_SOLAR_BUFF_KEY_BY_SIGN_INDEX,
    build_desired_solar_boost_state,
    sync_zone_solar_boosts,
)


class SolarBoostStatePlanningTests(unittest.TestCase):
    def test_aries_rising_in_aries_season_gets_exact_rising_first_house_and_fire_support(self):
        state = build_desired_solar_boost_state(
            current_sun_sign_index=0,
            natal_sign_index_by_layer={"sun": 5, "moon": 3, "rising": 0},
        )

        self.assertEqual({"PlumAntics_Big3Mod_AriesRisingBuff"}, set(state["exact_buff_keys"]))
        self.assertEqual(
            ANGULAR_SOLAR_BUFF_KEY_BY_HOUSE_INDEX[0],
            state["angular_buff_key"],
        )
        self.assertEqual(
            ELEMENT_SUPPORT_BUFF_KEY_BY_ELEMENT["fire"],
            state["element_buff_key"],
        )

    def test_exact_sun_and_rising_can_stack_but_element_support_caps_to_one_buff(self):
        state = build_desired_solar_boost_state(
            current_sun_sign_index=0,
            natal_sign_index_by_layer={"sun": 0, "moon": 4, "rising": 0},
        )

        self.assertEqual(
            {"PlumAntics_Big3Mod_AriesSunBuff", "PlumAntics_Big3Mod_AriesRisingBuff"},
            set(state["exact_buff_keys"]),
        )
        self.assertEqual(
            "PlumAntics_Big3Mod_ElementFireSolarSupportBuff",
            state["element_buff_key"],
        )

    def test_moon_solar_uses_the_new_moon_solar_family(self):
        state = build_desired_solar_boost_state(
            current_sun_sign_index=3,
            natal_sign_index_by_layer={"sun": 8, "moon": 3, "rising": 0},
        )

        self.assertIn(MOON_SOLAR_BUFF_KEY_BY_SIGN_INDEX[3], set(state["exact_buff_keys"]))
        self.assertNotIn("PlumAntics_Big3Mod_CancerMoonBuff", set(state["exact_buff_keys"]))

    def test_missing_big3_values_skip_missing_layers_without_throwing(self):
        state = build_desired_solar_boost_state(
            current_sun_sign_index=6,
            natal_sign_index_by_layer={"sun": None, "moon": None, "rising": 0},
        )

        self.assertEqual([], list(state["exact_buff_keys"]))
        self.assertEqual("PlumAntics_Big3Mod_SolarHouseSeventhBuff", state["angular_buff_key"])
        self.assertIsNone(state["element_buff_key"])


class _FakeSimInfo(object):
    def __init__(self, trait_names, buff_keys):
        self.trait_names = list(trait_names)
        self.buff_keys = set(buff_keys)


class SolarBoostSyncTests(unittest.TestCase):
    def test_sync_adds_exact_angular_and_element_layers_without_duplication(self):
        sim = _FakeSimInfo(
            trait_names=[
                "PlumAntics_CosmicEngineNatal_AriesSunHidden",
                "PlumAntics_CosmicEngineNatal_CancerMoonHidden",
                "PlumAntics_CosmicEngineNatal_AriesRisingHidden",
            ],
            buff_keys=set(),
        )

        summary = sync_zone_solar_boosts(
            sim_infos=[sim],
            current_sun_sign_index=0,
            get_trait_names_fn=lambda row: list(row.trait_names),
            list_buff_keys_fn=lambda row: set(row.buff_keys),
            add_buff_by_key_fn=lambda row, key: row.buff_keys.add(key) or True,
            remove_buff_by_key_fn=lambda row, key: row.buff_keys.remove(key) or True,
        )

        self.assertIn("PlumAntics_Big3Mod_AriesSunBuff", sim.buff_keys)
        self.assertIn("PlumAntics_Big3Mod_AriesRisingBuff", sim.buff_keys)
        self.assertIn("PlumAntics_Big3Mod_SolarHouseFirstBuff", sim.buff_keys)
        self.assertIn("PlumAntics_Big3Mod_ElementFireSolarSupportBuff", sim.buff_keys)
        self.assertEqual(4, summary["buffs_added"])

        summary = sync_zone_solar_boosts(
            sim_infos=[sim],
            current_sun_sign_index=0,
            get_trait_names_fn=lambda row: list(row.trait_names),
            list_buff_keys_fn=lambda row: set(row.buff_keys),
            add_buff_by_key_fn=lambda row, key: row.buff_keys.add(key) or True,
            remove_buff_by_key_fn=lambda row, key: row.buff_keys.remove(key) or True,
        )

        self.assertEqual(0, summary["buffs_added"])
        self.assertEqual(0, summary["buffs_removed"])

    def test_sync_removes_off_season_sunsolar_without_touching_lunar_cycle_moon_buffs(self):
        sim = _FakeSimInfo(
            trait_names=[
                "PlumAntics_CosmicEngineNatal_AriesSunHidden",
                "PlumAntics_CosmicEngineNatal_CancerMoonHidden",
                "PlumAntics_CosmicEngineNatal_AriesRisingHidden",
            ],
            buff_keys={
                "PlumAntics_Big3Mod_AriesSunBuff",
                "PlumAntics_Big3Mod_CancerMoonBuff",
                "PlumAntics_Big3Mod_SolarHouseFirstBuff",
                "PlumAntics_Big3Mod_ElementFireSolarSupportBuff",
            },
        )

        summary = sync_zone_solar_boosts(
            sim_infos=[sim],
            current_sun_sign_index=6,
            get_trait_names_fn=lambda row: list(row.trait_names),
            list_buff_keys_fn=lambda row: set(row.buff_keys),
            add_buff_by_key_fn=lambda row, key: row.buff_keys.add(key) or True,
            remove_buff_by_key_fn=lambda row, key: row.buff_keys.remove(key) or True,
        )

        self.assertNotIn("PlumAntics_Big3Mod_AriesSunBuff", sim.buff_keys)
        self.assertNotIn("PlumAntics_Big3Mod_SolarHouseFirstBuff", sim.buff_keys)
        self.assertNotIn("PlumAntics_Big3Mod_ElementFireSolarSupportBuff", sim.buff_keys)
        self.assertIn("PlumAntics_Big3Mod_CancerMoonBuff", sim.buff_keys)
        self.assertIn("PlumAntics_Big3Mod_SolarHouseSeventhBuff", sim.buff_keys)
        self.assertGreaterEqual(summary["buffs_removed"], 3)


if __name__ == "__main__":
    unittest.main()
