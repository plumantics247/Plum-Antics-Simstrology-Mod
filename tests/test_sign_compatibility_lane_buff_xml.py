import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SIGN_ROOT = ROOT / "src" / "SignCompatibility"
TIER_ROOT = SIGN_ROOT / "BuffTier"
OVERLAY_ROOT = SIGN_ROOT / "BuffOverlay"
VISIBLE_ROOT = SIGN_ROOT / "BuffVisible"


class SignCompatibilityLaneBuffXmlTests(unittest.TestCase):
    def test_expected_lane_buff_folders_exist(self):
        for path in (TIER_ROOT, OVERLAY_ROOT, VISIBLE_ROOT):
            self.assertTrue(path.exists(), path.as_posix())

    def test_expected_lane_buff_counts_exist(self):
        self.assertEqual(9, len([path for path in TIER_ROOT.glob("*.xml") if not path.name.endswith(".SimData.xml")]))
        self.assertEqual(9, len(tuple(TIER_ROOT.glob("*.SimData.xml"))))
        self.assertEqual(9, len([path for path in OVERLAY_ROOT.glob("*.xml") if not path.name.endswith(".SimData.xml")]))
        self.assertEqual(9, len(tuple(OVERLAY_ROOT.glob("*.SimData.xml"))))
        self.assertEqual(9, len([path for path in VISIBLE_ROOT.glob("*.xml") if not path.name.endswith(".SimData.xml")]))
        self.assertEqual(9, len(tuple(VISIBLE_ROOT.glob("*.SimData.xml"))))

    def test_sun_compatible_tier_uses_identity_buckets_only(self):
        sample = (TIER_ROOT / "PlumAntics_SunCompatibility_Tier_Compatible.xml").read_text(encoding="utf-8")
        self.assertIn("PlumAntics_Big3Mod_Interactions_SmallTalk", sample)
        self.assertIn("PlumAntics_Big3Mod_Interactions_Jokes", sample)
        self.assertIn("PlumAntics_Big3Mod_Interactions_Stories", sample)
        self.assertIn("PlumAntics_Big3Mod_Interactions_Hobbies", sample)
        self.assertIn("PlumAntics_Big3Mod_Interactions_Interests", sample)
        self.assertIn("PlumAntics_Big3Mod_Interactions_Gossip", sample)
        self.assertNotIn("PlumAntics_Big3Mod_Interactions_Flirtation", sample)
        self.assertNotIn("PlumAntics_Big3Mod_Interactions_Complaints", sample)

    def test_rising_incompatible_tier_uses_delivery_friction_only(self):
        sample = (TIER_ROOT / "PlumAntics_RisingCompatibility_Tier_Incompatible.xml").read_text(encoding="utf-8")
        self.assertIn("PlumAntics_Big3Mod_Interactions_Complaints", sample)
        self.assertIn("PlumAntics_Big3Mod_Interactions_Pranks", sample)
        self.assertNotIn("PlumAntics_Big3Mod_Interactions_Arguments", sample)
        self.assertNotIn("PlumAntics_Big3Mod_Interactions_Malicious", sample)

    def test_moon_compatible_tier_uses_intimacy_buckets_only(self):
        sample = (TIER_ROOT / "PlumAntics_MoonCompatibility_Tier_Compatible.xml").read_text(encoding="utf-8")
        self.assertIn("PlumAntics_Big3Mod_Interactions_Flirtation", sample)
        self.assertIn("PlumAntics_Big3Mod_Interactions_PhysicalIntimacy", sample)
        self.assertIn("PlumAntics_Big3Mod_Interactions_DeepThoughts", sample)
        self.assertNotIn("PlumAntics_Big3Mod_Interactions_Pranks", sample)
        self.assertNotIn("PlumAntics_Big3Mod_Interactions_Deception", sample)

    def test_visible_neutral_buff_keeps_plus_two_fine(self):
        sample = (VISIBLE_ROOT / "PlumAntics_SunCompatibility_NeutralReactionBuff.xml").read_text(encoding="utf-8")
        self.assertIn("14637<!--Mood_Fine-->", sample)
        self.assertIn('<T n="mood_weight">2</T>', sample)
        self.assertIn('<T n="show_timeout">True</T>', sample)

    def test_overlay_buff_is_hidden_and_timed(self):
        sample = (OVERLAY_ROOT / "PlumAntics_MoonCompatibility_Overlay_Incompatible.xml").read_text(encoding="utf-8")
        self.assertIn('<T n="visible">False</T>', sample)
        self.assertIn('<T n="show_timeout">False</T>', sample)
        self.assertIn('<V n="_temporary_commodity_info" t="enabled">', sample)


if __name__ == "__main__":
    unittest.main()
