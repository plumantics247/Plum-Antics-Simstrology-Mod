import pathlib
import re
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
CORE_ROOT = ROOT / "src" / "core"
SIGN_ROOT = ROOT / "src" / "SignCompatibility"


class SignCompatibilityAffordanceScoringXmlTests(unittest.TestCase):
    def test_core_affection_snippet_exists(self):
        path = CORE_ROOT / "Snippet" / "PlumAntics_Big3ModCore_Interactions_Affection.xml"
        self.assertTrue(path.exists(), path.as_posix())

    def test_core_affection_snippet_contains_supportive_socials(self):
        sample = (CORE_ROOT / "Snippet" / "PlumAntics_Big3ModCore_Interactions_Affection.xml").read_text(encoding="utf-8")
        for token in (
            "sim_BeAffectionate",
            "mixer_social_AskForReassurance_targeted_romance_emotionSpecific",
            "mixer_social_CheerUp_targeted_friendly_emotionSpecific",
            "mixer_social_ConsoleAboutDeath_Targeted_Friendly_EmotionSpecific",
        ):
            self.assertIn(token, sample)

    def test_sun_tier_compatible_uses_identity_buckets(self):
        sample = (SIGN_ROOT / "BuffTier" / "PlumAntics_SunCompatibility_Tier_Compatible.xml").read_text(encoding="utf-8")
        for token in (
            "PlumAntics_Big3Mod_Interactions_Interests",
            "PlumAntics_Big3Mod_Interactions_Stories",
            "PlumAntics_Big3Mod_Interactions_DeepThoughts",
            "PlumAntics_Big3Mod_Interactions_Compliments",
        ):
            self.assertIn(token, sample)
        self.assertNotIn("PlumAntics_Big3Mod_Interactions_PhysicalIntimacy", sample)
        self.assertNotIn("PlumAntics_Big3Mod_Interactions_Pranks", sample)

    def test_rising_tier_compatible_uses_delivery_buckets(self):
        sample = (SIGN_ROOT / "BuffTier" / "PlumAntics_RisingCompatibility_Tier_Compatible.xml").read_text(encoding="utf-8")
        for token in (
            "PlumAntics_Big3Mod_Interactions_Compliments",
            "PlumAntics_Big3Mod_Interactions_Gossip",
            "PlumAntics_Big3Mod_Interactions_Jokes",
            "PlumAntics_Big3Mod_Interactions_SmallTalk",
        ):
            self.assertIn(token, sample)
        self.assertNotIn("PlumAntics_Big3Mod_Interactions_PhysicalIntimacy", sample)
        self.assertNotIn("PlumAntics_Big3Mod_Interactions_Malicious", sample)

    def test_moon_tier_compatible_uses_emotional_buckets(self):
        sample = (SIGN_ROOT / "BuffTier" / "PlumAntics_MoonCompatibility_Tier_Compatible.xml").read_text(encoding="utf-8")
        for token in (
            "PlumAntics_Big3Mod_Interactions_Affection",
            "PlumAntics_Big3Mod_Interactions_DeepThoughts",
            "PlumAntics_Big3Mod_Interactions_Stories",
        ):
            self.assertIn(token, sample)
        self.assertNotIn("PlumAntics_Big3Mod_Interactions_Pranks", sample)
        self.assertNotIn("PlumAntics_Big3Mod_Interactions_Deception", sample)

    def test_passive_core_sign_buffs_are_subtle(self):
        samples = (
            CORE_ROOT / "Buff" / "PlumAntics_Big3ModCore_AriesSunBuffHidden.xml",
            CORE_ROOT / "Buff" / "PlumAntics_Big3ModCore_AriesRisingBuffHidden.xml",
            CORE_ROOT / "Buff" / "PlumAntics_Big3ModCore_AriesMoonBuff.xml",
        )
        for path in samples:
            text = path.read_text(encoding="utf-8")
            scores = [int(value) for value in re.findall(r'<T n="content_score_bonus">(-?\d+)</T>', text)]
            self.assertTrue(scores, path.as_posix())
            self.assertTrue(all(-4 <= value <= 4 for value in scores), path.as_posix())

    def test_compatibility_tier_buffs_are_stronger_than_passive(self):
        samples = (
            SIGN_ROOT / "BuffTier" / "PlumAntics_SunCompatibility_Tier_Compatible.xml",
            SIGN_ROOT / "BuffTier" / "PlumAntics_RisingCompatibility_Tier_Incompatible.xml",
            SIGN_ROOT / "BuffTier" / "PlumAntics_MoonCompatibility_Tier_Compatible.xml",
        )
        for path in samples:
            text = path.read_text(encoding="utf-8")
            scores = [int(value) for value in re.findall(r'<T n="content_score_bonus">(-?\d+)</T>', text)]
            self.assertTrue(any(abs(value) >= 8 for value in scores), path.as_posix())

    def test_visible_reaction_buffs_are_timed_and_visible(self):
        sample = (SIGN_ROOT / "BuffVisible" / "PlumAntics_MoonCompatibility_CompatibleReactionBuff.xml").read_text(encoding="utf-8")
        self.assertIn('<T n="visible">True</T>', sample)
        self.assertIn('<T n="max_duration">90</T>', sample)

    def test_overlay_buffs_are_hidden_and_timed(self):
        sample = (SIGN_ROOT / "BuffOverlay" / "PlumAntics_RisingCompatibility_Overlay_Compatible.xml").read_text(encoding="utf-8")
        self.assertIn('<T n="visible">False</T>', sample)
        self.assertIn('<T n="max_duration">90</T>', sample)


if __name__ == "__main__":
    unittest.main()
