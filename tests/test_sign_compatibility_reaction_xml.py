import pathlib
import re
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SIGN_ROOT = ROOT / "src" / "SignCompatibility"

ACTION_ROOT = SIGN_ROOT / "Action"
VISIBLE_BUFF_ROOT = SIGN_ROOT / "BuffVisible"
HIDDEN_BUFF_ROOT = SIGN_ROOT / "BuffHidden"
INTERACTION_ROOT = SIGN_ROOT / "Interaction"
INJECTOR_ROOT = SIGN_ROOT / "Injector"


class SignCompatibilityReactionXmlTests(unittest.TestCase):
    def test_expected_reaction_folders_exist(self):
        for path in (ACTION_ROOT, VISIBLE_BUFF_ROOT, HIDDEN_BUFF_ROOT, INTERACTION_ROOT, INJECTOR_ROOT):
            self.assertTrue(path.exists(), path.as_posix())

    def test_expected_reaction_file_counts_exist(self):
        self.assertEqual(108, len(tuple(ACTION_ROOT.glob("*.xml"))))
        self.assertEqual(9, len([path for path in VISIBLE_BUFF_ROOT.glob("*.xml") if not path.name.endswith(".SimData.xml")]))
        self.assertEqual(9, len(tuple(VISIBLE_BUFF_ROOT.glob("*.SimData.xml"))))
        self.assertEqual(3, len([path for path in HIDDEN_BUFF_ROOT.glob("*.xml") if not path.name.endswith(".SimData.xml")]))
        self.assertEqual(3, len(tuple(HIDDEN_BUFF_ROOT.glob("*.SimData.xml"))))
        self.assertEqual(3, len(tuple(INTERACTION_ROOT.glob("*.xml"))))
        self.assertEqual(1, len(tuple(INJECTOR_ROOT.glob("*.xml"))))

    def test_sample_loot_references_preference_target_and_cooldown(self):
        sample = (ACTION_ROOT / "PlumAntics_MoonCompatibility_AquariusIncompatibleReactionLoot.xml").read_text(encoding="utf-8")
        self.assertIn("PlumAntics_MoonCompatibility_AquariusDislikePreferenceTrait", sample)
        self.assertIn("PlumAntics_Big3Mod_AquariusMoon", sample)
        self.assertIn("PlumAntics_MoonCompatibility_ReactionCooldownBuff", sample)
        self.assertIn("PlumAntics_MoonCompatibility_IncompatibleReactionBuff", sample)

    def test_neutral_loot_uses_blacklist_preference_gate(self):
        sample = (ACTION_ROOT / "PlumAntics_SunCompatibility_AquariusNeutralReactionLoot.xml").read_text(encoding="utf-8")
        self.assertIn('<L n="blacklist_traits">', sample)
        self.assertIn("PlumAntics_SunCompatibility_AquariusLikePreferenceTrait", sample)
        self.assertIn("PlumAntics_SunCompatibility_AquariusDislikePreferenceTrait", sample)
        self.assertIn("PlumAntics_SunCompatibility_NeutralReactionBuff", sample)

    def test_mixer_shape_is_hidden_autonomous_carrier(self):
        sample = (INTERACTION_ROOT / "PlumAntics_SunCompatibility_ReactionMixer.xml").read_text(encoding="utf-8")
        self.assertIn('c="SocialMixerInteraction"', sample)
        self.assertIn('<T n="allow_autonomous">True</T>', sample)
        self.assertIn('<T n="allow_user_directed">False</T>', sample)
        self.assertIn('<T n="visible">False</T>', sample)
        self.assertIn('<L n="basic_extras">', sample)

    def test_injector_is_retired_so_runtime_relbits_drive_visible_buffs(self):
        sample = (INJECTOR_ROOT / "PlumAntics_SignCompatibility_TuningInjector.xml").read_text(encoding="utf-8")
        self.assertIn('<L n="inject_to_mixer_list"/>', sample)
        self.assertNotIn("social_Mixers_Friendly_NonTouching", sample)
        self.assertNotIn("social_Mixers_Friendly_Touching", sample)

    def test_reaction_layer_stays_xml_only(self):
        forbidden = re.compile(r"cosmic_engine\.|plumantics\.|python|loot_actions\.py", re.IGNORECASE)
        for path in SIGN_ROOT.glob("**/*.xml"):
            if any(part in {"Action", "BuffVisible", "BuffHidden", "Interaction", "Injector"} for part in path.parts):
                self.assertNotRegex(path.read_text(encoding="utf-8"), forbidden, path.as_posix())


if __name__ == "__main__":
    unittest.main()
