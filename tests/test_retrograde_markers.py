import importlib
import pathlib
import sys
import unittest
from unittest.mock import patch


sys.dont_write_bytecode = True

ROOT = pathlib.Path(__file__).resolve().parents[1]
PYTHON_DIR = ROOT / "python"
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))


retrograde_markers = importlib.import_module("cosmic_engine.retrograde_markers")


class _FakeSimInfo(object):
    def __init__(self, buffs=None, current_mood=None, external_mood_buff_types=None):
        self.buffs = set(buffs or ())
        self._current_mood = current_mood
        self.Buffs = _FakeBuffTracker(external_mood_buff_types or ())

    def get_mood(self):
        return self._current_mood


class _FakeBuffTracker(object):
    def __init__(self, buff_types):
        self._buffs = [_FakeBuffInstance(buff_type) for buff_type in buff_types]


class _FakeBuffInstance(object):
    def __init__(self, buff_type, visible=True):
        self.buff_type = buff_type
        self.visible = bool(visible)
        self.mood_type = getattr(buff_type, "mood_type", None)
        self.guid64 = getattr(buff_type, "guid64", None)


class _FakeMoodType(object):
    def __init__(self, guid64):
        self.guid64 = int(guid64)


class _FakeBuffType(object):
    def __init__(self, guid64, mood_type_id):
        self.guid64 = int(guid64)
        self.mood_type = _FakeMoodType(mood_type_id)


def _make_supporting_sim(*, current_mood_id=None, supporting_mood_ids=(), buffs=None):
    return _FakeSimInfo(
        buffs=set(buffs or ()),
        current_mood=_FakeMoodType(current_mood_id) if current_mood_id is not None else None,
        external_mood_buff_types=[
            _FakeBuffType(guid64=8000 + index, mood_type_id=mood_id)
            for index, mood_id in enumerate(supporting_mood_ids, start=1)
        ],
    )


class RetrogradeMarkerTests(unittest.TestCase):
    def test_desired_bodies_default_to_recommended_three_visible_cap(self):
        original_is_teen_plus = retrograde_markers._sim_info_is_teen_plus
        original_ruler = retrograde_markers._ruling_retrograde_body_for_sim
        try:
            retrograde_markers._sim_info_is_teen_plus = lambda sim_info: True
            retrograde_markers._ruling_retrograde_body_for_sim = (
                lambda sim_info, *, sun_trait_id_to_ruler_body: None
            )

            desired_base, desired_intense, intense_body = (
                retrograde_markers._desired_retrograde_bodies_for_sim(
                    object(),
                    {
                        "Mercury": True,
                        "Venus": True,
                        "Mars": False,
                        "Jupiter": True,
                        "Saturn": True,
                    },
                    sun_trait_id_to_ruler_body={},
                    retrograde_visibility_profile_id="recommended",
                )
            )

            self.assertEqual({"Mercury", "Venus", "Jupiter"}, desired_base)
            self.assertEqual(set(), desired_intense)
            self.assertIsNone(intense_body)
        finally:
            retrograde_markers._sim_info_is_teen_plus = original_is_teen_plus
            retrograde_markers._ruling_retrograde_body_for_sim = original_ruler

    def test_desired_bodies_cap_visible_retrogrades_at_three(self):
        original_is_teen_plus = retrograde_markers._sim_info_is_teen_plus
        original_ruler = retrograde_markers._ruling_retrograde_body_for_sim
        try:
            retrograde_markers._sim_info_is_teen_plus = lambda sim_info: True
            retrograde_markers._ruling_retrograde_body_for_sim = (
                lambda sim_info, *, sun_trait_id_to_ruler_body: None
            )

            desired_base, desired_intense, intense_body = (
                retrograde_markers._desired_retrograde_bodies_for_sim(
                    object(),
                    {
                        "Mercury": True,
                        "Venus": True,
                        "Mars": False,
                        "Jupiter": True,
                        "Saturn": True,
                    },
                    sun_trait_id_to_ruler_body={},
                    retrograde_visibility_profile_id="recommended",
                )
            )

            self.assertEqual({"Mercury", "Venus", "Jupiter"}, desired_base)
            self.assertEqual(set(), desired_intense)
            self.assertIsNone(intense_body)
        finally:
            retrograde_markers._sim_info_is_teen_plus = original_is_teen_plus
            retrograde_markers._ruling_retrograde_body_for_sim = original_ruler

    def test_desired_bodies_preserve_intense_retrograde_inside_three_body_cap(self):
        original_is_teen_plus = retrograde_markers._sim_info_is_teen_plus
        original_ruler = retrograde_markers._ruling_retrograde_body_for_sim
        try:
            retrograde_markers._sim_info_is_teen_plus = lambda sim_info: True
            retrograde_markers._ruling_retrograde_body_for_sim = (
                lambda sim_info, *, sun_trait_id_to_ruler_body: "Saturn"
            )

            desired_base, desired_intense, intense_body = (
                retrograde_markers._desired_retrograde_bodies_for_sim(
                    object(),
                    {
                        "Mercury": True,
                        "Venus": True,
                        "Mars": False,
                        "Jupiter": True,
                        "Saturn": True,
                    },
                    sun_trait_id_to_ruler_body={},
                    retrograde_visibility_profile_id="recommended",
                )
            )

            self.assertEqual({"Mercury", "Venus"}, desired_base)
            self.assertEqual({"Saturn"}, desired_intense)
            self.assertEqual("Saturn", intense_body)
        finally:
            retrograde_markers._sim_info_is_teen_plus = original_is_teen_plus
            retrograde_markers._ruling_retrograde_body_for_sim = original_ruler

    def test_desired_bodies_uncapped_profile_surfaces_all_active_retrogrades(self):
        original_is_teen_plus = retrograde_markers._sim_info_is_teen_plus
        original_ruler = retrograde_markers._ruling_retrograde_body_for_sim
        try:
            retrograde_markers._sim_info_is_teen_plus = lambda sim_info: True
            retrograde_markers._ruling_retrograde_body_for_sim = (
                lambda sim_info, *, sun_trait_id_to_ruler_body: "Saturn"
            )

            desired_base, desired_intense, intense_body = (
                retrograde_markers._desired_retrograde_bodies_for_sim(
                    object(),
                    {
                        "Mercury": True,
                        "Venus": True,
                        "Mars": False,
                        "Jupiter": True,
                        "Saturn": True,
                    },
                    sun_trait_id_to_ruler_body={},
                    retrograde_visibility_profile_id="uncapped",
                )
            )

            self.assertEqual({"Mercury", "Venus", "Jupiter"}, desired_base)
            self.assertEqual({"Saturn"}, desired_intense)
            self.assertEqual("Saturn", intense_body)
        finally:
            retrograde_markers._sim_info_is_teen_plus = original_is_teen_plus
            retrograde_markers._ruling_retrograde_body_for_sim = original_ruler

    def test_apply_retrograde_consequences_removes_capped_extra_buff(self):
        original_has_buff = retrograde_markers._sim_info_has_buff
        original_remove_buff = retrograde_markers._sim_info_remove_buff
        original_add_buff = retrograde_markers._sim_info_add_buff
        original_run_loot = retrograde_markers._run_loot_on_sim_info
        original_mood_gate = retrograde_markers._sim_has_visible_external_mood_support
        try:
            retrograde_markers._sim_info_has_buff = lambda sim_info, buff: buff in sim_info.buffs
            retrograde_markers._sim_info_remove_buff = (
                lambda sim_info, buff: sim_info.buffs.remove(buff) is None if buff in sim_info.buffs else False
            )
            retrograde_markers._sim_info_add_buff = (
                lambda sim_info, buff: (sim_info.buffs.add(buff) or True) if buff not in sim_info.buffs else False
            )
            retrograde_markers._run_loot_on_sim_info = lambda sim_info, loot_id: False
            retrograde_markers._sim_has_visible_external_mood_support = (
                lambda sim_info, mood_type_id, excluded_buffs=(): True
            )

            buff_mercury = _FakeBuffType(guid64=7001, mood_type_id=14645)
            buff_venus = _FakeBuffType(guid64=7002, mood_type_id=14646)
            buff_jupiter = _FakeBuffType(guid64=7003, mood_type_id=14644)
            buff_saturn = _FakeBuffType(guid64=7004, mood_type_id=14639)
            sim_info = _FakeSimInfo(
                buffs={buff_mercury, buff_venus, buff_jupiter, buff_saturn},
            )
            summary = {
                "buffs_added": 0,
                "buffs_removed": 0,
                "intense_buffs_added": 0,
                "intense_buffs_removed": 0,
                "dispatch_failures": 0,
            }

            changed = retrograde_markers._apply_retrograde_consequences_for_sim(
                sim_info,
                desired_base_bodies={"Mercury", "Venus", "Jupiter"},
                desired_intense_bodies=set(),
                base_buff_by_body={
                    "Mercury": buff_mercury,
                    "Venus": buff_venus,
                    "Jupiter": buff_jupiter,
                    "Saturn": buff_saturn,
                },
                intense_buff_by_body={},
                summary=summary,
            )

            self.assertTrue(changed)
            self.assertEqual({buff_mercury, buff_venus, buff_jupiter}, sim_info.buffs)
            self.assertEqual(1, summary["buffs_removed"])
            self.assertEqual(0, summary["dispatch_failures"])
        finally:
            retrograde_markers._sim_info_has_buff = original_has_buff
            retrograde_markers._sim_info_remove_buff = original_remove_buff
            retrograde_markers._sim_info_add_buff = original_add_buff
            retrograde_markers._run_loot_on_sim_info = original_run_loot
            retrograde_markers._sim_has_visible_external_mood_support = original_mood_gate

    def test_apply_retrograde_consequences_requires_current_matching_mood_for_base_buff(self):
        original_has_buff = retrograde_markers._sim_info_has_buff
        original_remove_buff = retrograde_markers._sim_info_remove_buff
        original_add_buff = retrograde_markers._sim_info_add_buff
        original_run_loot = retrograde_markers._run_loot_on_sim_info
        try:
            retrograde_markers._sim_info_has_buff = lambda sim_info, buff: buff in sim_info.buffs
            retrograde_markers._sim_info_remove_buff = (
                lambda sim_info, buff: sim_info.buffs.remove(buff) is None if buff in sim_info.buffs else False
            )
            retrograde_markers._sim_info_add_buff = (
                lambda sim_info, buff: (sim_info.buffs.add(buff) or True) if buff not in sim_info.buffs else False
            )
            retrograde_markers._run_loot_on_sim_info = lambda sim_info, loot_id: False

            sim_info = _FakeSimInfo(
                buffs=set(),
                current_mood=None,
            )
            saturn_base_buff = _FakeBuffType(guid64=9001, mood_type_id=14639)
            summary = {
                "buffs_added": 0,
                "buffs_removed": 0,
                "intense_buffs_added": 0,
                "intense_buffs_removed": 0,
                "dispatch_failures": 0,
            }

            changed = retrograde_markers._apply_retrograde_consequences_for_sim(
                sim_info,
                desired_base_bodies={"Saturn"},
                desired_intense_bodies=set(),
                base_buff_by_body={"Saturn": saturn_base_buff},
                intense_buff_by_body={},
                summary=summary,
            )

            self.assertFalse(changed)
            self.assertEqual(0, summary["buffs_added"])
            self.assertEqual(set(), sim_info.buffs)
        finally:
            retrograde_markers._sim_info_has_buff = original_has_buff
            retrograde_markers._sim_info_remove_buff = original_remove_buff
            retrograde_markers._sim_info_add_buff = original_add_buff
            retrograde_markers._run_loot_on_sim_info = original_run_loot

    def test_apply_retrograde_consequences_adds_base_buff_when_current_matching_mood_exists(self):
        original_has_buff = retrograde_markers._sim_info_has_buff
        original_remove_buff = retrograde_markers._sim_info_remove_buff
        original_add_buff = retrograde_markers._sim_info_add_buff
        original_run_loot = retrograde_markers._run_loot_on_sim_info
        try:
            retrograde_markers._sim_info_has_buff = lambda sim_info, buff: buff in sim_info.buffs
            retrograde_markers._sim_info_remove_buff = (
                lambda sim_info, buff: sim_info.buffs.remove(buff) is None if buff in sim_info.buffs else False
            )
            retrograde_markers._sim_info_add_buff = (
                lambda sim_info, buff: (sim_info.buffs.add(buff) or True) if buff not in sim_info.buffs else False
            )
            retrograde_markers._run_loot_on_sim_info = lambda sim_info, loot_id: False

            sim_info = _FakeSimInfo(
                buffs=set(),
                current_mood=_FakeMoodType(14639),
                external_mood_buff_types=[_FakeBuffType(guid64=8002, mood_type_id=14639)],
            )
            saturn_base_buff = _FakeBuffType(guid64=9002, mood_type_id=14639)
            summary = {
                "buffs_added": 0,
                "buffs_removed": 0,
                "intense_buffs_added": 0,
                "intense_buffs_removed": 0,
                "dispatch_failures": 0,
            }

            changed = retrograde_markers._apply_retrograde_consequences_for_sim(
                sim_info,
                desired_base_bodies={"Saturn"},
                desired_intense_bodies=set(),
                base_buff_by_body={"Saturn": saturn_base_buff},
                intense_buff_by_body={},
                summary=summary,
            )

            self.assertTrue(changed)
            self.assertEqual(1, summary["buffs_added"])
            self.assertEqual({saturn_base_buff}, sim_info.buffs)
        finally:
            retrograde_markers._sim_info_has_buff = original_has_buff
            retrograde_markers._sim_info_remove_buff = original_remove_buff
            retrograde_markers._sim_info_add_buff = original_add_buff
            retrograde_markers._run_loot_on_sim_info = original_run_loot

    def test_apply_retrograde_consequences_does_not_add_base_buff_from_background_matching_buff_alone(self):
        original_has_buff = retrograde_markers._sim_info_has_buff
        original_remove_buff = retrograde_markers._sim_info_remove_buff
        original_add_buff = retrograde_markers._sim_info_add_buff
        original_run_loot = retrograde_markers._run_loot_on_sim_info
        try:
            retrograde_markers._sim_info_has_buff = lambda sim_info, buff: buff in sim_info.buffs
            retrograde_markers._sim_info_remove_buff = (
                lambda sim_info, buff: sim_info.buffs.remove(buff) is None if buff in sim_info.buffs else False
            )
            retrograde_markers._sim_info_add_buff = (
                lambda sim_info, buff: (sim_info.buffs.add(buff) or True) if buff not in sim_info.buffs else False
            )
            retrograde_markers._run_loot_on_sim_info = lambda sim_info, loot_id: False

            sim_info = _FakeSimInfo(
                buffs=set(),
                current_mood=None,
                external_mood_buff_types=[_FakeBuffType(guid64=8001, mood_type_id=14639)],
            )
            saturn_base_buff = _FakeBuffType(guid64=9004, mood_type_id=14639)
            summary = {
                "buffs_added": 0,
                "buffs_removed": 0,
                "intense_buffs_added": 0,
                "intense_buffs_removed": 0,
                "dispatch_failures": 0,
            }

            changed = retrograde_markers._apply_retrograde_consequences_for_sim(
                sim_info,
                desired_base_bodies={"Saturn"},
                desired_intense_bodies=set(),
                base_buff_by_body={"Saturn": saturn_base_buff},
                intense_buff_by_body={},
                summary=summary,
            )

            self.assertFalse(changed)
            self.assertEqual(0, summary["buffs_added"])
            self.assertEqual(set(), sim_info.buffs)
        finally:
            retrograde_markers._sim_info_has_buff = original_has_buff
            retrograde_markers._sim_info_remove_buff = original_remove_buff
            retrograde_markers._sim_info_add_buff = original_add_buff
            retrograde_markers._run_loot_on_sim_info = original_run_loot

    def test_apply_retrograde_consequences_requires_exact_custom_mood_for_intense_buff(self):
        original_has_buff = retrograde_markers._sim_info_has_buff
        original_remove_buff = retrograde_markers._sim_info_remove_buff
        original_add_buff = retrograde_markers._sim_info_add_buff
        original_run_loot = retrograde_markers._run_loot_on_sim_info
        try:
            retrograde_markers._sim_info_has_buff = lambda sim_info, buff: buff in sim_info.buffs
            retrograde_markers._sim_info_remove_buff = (
                lambda sim_info, buff: sim_info.buffs.remove(buff) is None if buff in sim_info.buffs else False
            )
            retrograde_markers._sim_info_add_buff = (
                lambda sim_info, buff: (sim_info.buffs.add(buff) or True) if buff not in sim_info.buffs else False
            )
            retrograde_markers._run_loot_on_sim_info = lambda sim_info, loot_id: False

            sim_info = _FakeSimInfo(
                buffs=set(),
                current_mood=_FakeMoodType(14639),
            )
            jupiter_intense_buff = _FakeBuffType(guid64=9100, mood_type_id=3027807324045670738)
            summary = {
                "buffs_added": 0,
                "buffs_removed": 0,
                "intense_buffs_added": 0,
                "intense_buffs_removed": 0,
                "dispatch_failures": 0,
            }

            changed = retrograde_markers._apply_retrograde_consequences_for_sim(
                sim_info,
                desired_base_bodies=set(),
                desired_intense_bodies={"Jupiter"},
                base_buff_by_body={},
                intense_buff_by_body={"Jupiter": jupiter_intense_buff},
                summary=summary,
            )

            self.assertFalse(changed)
            self.assertEqual(0, summary["intense_buffs_added"])
            self.assertEqual(set(), sim_info.buffs)
        finally:
            retrograde_markers._sim_info_has_buff = original_has_buff
            retrograde_markers._sim_info_remove_buff = original_remove_buff
            retrograde_markers._sim_info_add_buff = original_add_buff
            retrograde_markers._run_loot_on_sim_info = original_run_loot

    def test_retrograde_buff_does_not_self_satisfy_mood_gate(self):
        original_has_buff = retrograde_markers._sim_info_has_buff
        original_remove_buff = retrograde_markers._sim_info_remove_buff
        original_add_buff = retrograde_markers._sim_info_add_buff
        original_run_loot = retrograde_markers._run_loot_on_sim_info
        try:
            retrograde_markers._sim_info_has_buff = lambda sim_info, buff: buff in sim_info.buffs
            retrograde_markers._sim_info_remove_buff = (
                lambda sim_info, buff: sim_info.buffs.remove(buff) is None if buff in sim_info.buffs else False
            )
            retrograde_markers._sim_info_add_buff = (
                lambda sim_info, buff: (sim_info.buffs.add(buff) or True) if buff not in sim_info.buffs else False
            )
            retrograde_markers._run_loot_on_sim_info = lambda sim_info, loot_id: False

            saturn_base_buff = _FakeBuffType(guid64=9003, mood_type_id=14639)
            sim_info = _FakeSimInfo(
                buffs={saturn_base_buff},
                current_mood=None,
            )
            summary = {
                "buffs_added": 0,
                "buffs_removed": 0,
                "intense_buffs_added": 0,
                "intense_buffs_removed": 0,
                "dispatch_failures": 0,
            }

            changed = retrograde_markers._apply_retrograde_consequences_for_sim(
                sim_info,
                desired_base_bodies={"Saturn"},
                desired_intense_bodies=set(),
                base_buff_by_body={"Saturn": saturn_base_buff},
                intense_buff_by_body={},
                summary=summary,
            )

            self.assertTrue(changed)
            self.assertEqual(1, summary["buffs_removed"])
            self.assertEqual(set(), sim_info.buffs)
        finally:
            retrograde_markers._sim_info_has_buff = original_has_buff
            retrograde_markers._sim_info_remove_buff = original_remove_buff
            retrograde_markers._sim_info_add_buff = original_add_buff
            retrograde_markers._run_loot_on_sim_info = original_run_loot

    def test_apply_retrograde_consequences_adds_saturn_buff_for_related_productive_mood(self):
        original_has_buff = retrograde_markers._sim_info_has_buff
        original_remove_buff = retrograde_markers._sim_info_remove_buff
        original_add_buff = retrograde_markers._sim_info_add_buff
        original_run_loot = retrograde_markers._run_loot_on_sim_info
        try:
            retrograde_markers._sim_info_has_buff = lambda sim_info, buff: buff in sim_info.buffs
            retrograde_markers._sim_info_remove_buff = (
                lambda sim_info, buff: sim_info.buffs.remove(buff) is None if buff in sim_info.buffs else False
            )
            retrograde_markers._sim_info_add_buff = (
                lambda sim_info, buff: (sim_info.buffs.add(buff) or True) if buff not in sim_info.buffs else False
            )
            retrograde_markers._run_loot_on_sim_info = lambda sim_info, loot_id: False

            sim_info = _make_supporting_sim(
                current_mood_id=13289050976871245414,
                supporting_mood_ids=(13289050976871245414,),
            )
            saturn_base_buff = _FakeBuffType(guid64=9201, mood_type_id=14639)
            summary = {
                "buffs_added": 0,
                "buffs_removed": 0,
                "intense_buffs_added": 0,
                "intense_buffs_removed": 0,
                "dispatch_failures": 0,
            }

            changed = retrograde_markers._apply_retrograde_consequences_for_sim(
                sim_info,
                desired_base_bodies={"Saturn"},
                desired_intense_bodies=set(),
                base_buff_by_body={"Saturn": saturn_base_buff},
                intense_buff_by_body={},
                summary=summary,
            )

            self.assertTrue(changed)
            self.assertEqual(1, summary["buffs_added"])
            self.assertEqual({saturn_base_buff}, sim_info.buffs)
        finally:
            retrograde_markers._sim_info_has_buff = original_has_buff
            retrograde_markers._sim_info_remove_buff = original_remove_buff
            retrograde_markers._sim_info_add_buff = original_add_buff
            retrograde_markers._run_loot_on_sim_info = original_run_loot

    def test_apply_retrograde_consequences_rejects_saturn_buff_for_unlisted_confident_mood(self):
        original_has_buff = retrograde_markers._sim_info_has_buff
        original_remove_buff = retrograde_markers._sim_info_remove_buff
        original_add_buff = retrograde_markers._sim_info_add_buff
        original_run_loot = retrograde_markers._run_loot_on_sim_info
        try:
            retrograde_markers._sim_info_has_buff = lambda sim_info, buff: buff in sim_info.buffs
            retrograde_markers._sim_info_remove_buff = (
                lambda sim_info, buff: sim_info.buffs.remove(buff) is None if buff in sim_info.buffs else False
            )
            retrograde_markers._sim_info_add_buff = (
                lambda sim_info, buff: (sim_info.buffs.add(buff) or True) if buff not in sim_info.buffs else False
            )
            retrograde_markers._run_loot_on_sim_info = lambda sim_info, loot_id: False

            sim_info = _make_supporting_sim(
                current_mood_id=9458162033570690727,
                supporting_mood_ids=(9458162033570690727,),
            )
            saturn_base_buff = _FakeBuffType(guid64=9202, mood_type_id=14639)
            summary = {
                "buffs_added": 0,
                "buffs_removed": 0,
                "intense_buffs_added": 0,
                "intense_buffs_removed": 0,
                "dispatch_failures": 0,
            }

            changed = retrograde_markers._apply_retrograde_consequences_for_sim(
                sim_info,
                desired_base_bodies={"Saturn"},
                desired_intense_bodies=set(),
                base_buff_by_body={"Saturn": saturn_base_buff},
                intense_buff_by_body={},
                summary=summary,
            )

            self.assertFalse(changed)
            self.assertEqual(0, summary["buffs_added"])
            self.assertEqual(set(), sim_info.buffs)
        finally:
            retrograde_markers._sim_info_has_buff = original_has_buff
            retrograde_markers._sim_info_remove_buff = original_remove_buff
            retrograde_markers._sim_info_add_buff = original_add_buff
            retrograde_markers._run_loot_on_sim_info = original_run_loot

    def test_retrograde_buff_does_not_self_sustain_when_current_mood_only_matches_itself(self):
        original_has_buff = retrograde_markers._sim_info_has_buff
        original_remove_buff = retrograde_markers._sim_info_remove_buff
        original_add_buff = retrograde_markers._sim_info_add_buff
        original_run_loot = retrograde_markers._run_loot_on_sim_info
        try:
            retrograde_markers._sim_info_has_buff = lambda sim_info, buff: buff in sim_info.buffs
            retrograde_markers._sim_info_remove_buff = (
                lambda sim_info, buff: sim_info.buffs.remove(buff) is None if buff in sim_info.buffs else False
            )
            retrograde_markers._sim_info_add_buff = (
                lambda sim_info, buff: (sim_info.buffs.add(buff) or True) if buff not in sim_info.buffs else False
            )
            retrograde_markers._run_loot_on_sim_info = lambda sim_info, loot_id: False

            saturn_base_buff = _FakeBuffType(guid64=9005, mood_type_id=14639)
            sim_info = _FakeSimInfo(
                buffs={saturn_base_buff},
                current_mood=_FakeMoodType(14639),
            )
            summary = {
                "buffs_added": 0,
                "buffs_removed": 0,
                "intense_buffs_added": 0,
                "intense_buffs_removed": 0,
                "dispatch_failures": 0,
            }

            changed = retrograde_markers._apply_retrograde_consequences_for_sim(
                sim_info,
                desired_base_bodies={"Saturn"},
                desired_intense_bodies=set(),
                base_buff_by_body={"Saturn": saturn_base_buff},
                intense_buff_by_body={},
                summary=summary,
            )

            self.assertTrue(changed)
            self.assertEqual(1, summary["buffs_removed"])
            self.assertEqual(set(), sim_info.buffs)
        finally:
            retrograde_markers._sim_info_has_buff = original_has_buff
            retrograde_markers._sim_info_remove_buff = original_remove_buff
            retrograde_markers._sim_info_add_buff = original_add_buff
            retrograde_markers._run_loot_on_sim_info = original_run_loot

    def test_apply_retrograde_consequences_adds_jupiter_intense_for_related_dazed_lane_mood(self):
        original_has_buff = retrograde_markers._sim_info_has_buff
        original_remove_buff = retrograde_markers._sim_info_remove_buff
        original_add_buff = retrograde_markers._sim_info_add_buff
        original_run_loot = retrograde_markers._run_loot_on_sim_info
        try:
            retrograde_markers._sim_info_has_buff = lambda sim_info, buff: buff in sim_info.buffs
            retrograde_markers._sim_info_remove_buff = (
                lambda sim_info, buff: sim_info.buffs.remove(buff) is None if buff in sim_info.buffs else False
            )
            retrograde_markers._sim_info_add_buff = (
                lambda sim_info, buff: (sim_info.buffs.add(buff) or True) if buff not in sim_info.buffs else False
            )
            retrograde_markers._run_loot_on_sim_info = lambda sim_info, loot_id: False

            sim_info = _make_supporting_sim(
                current_mood_id=12984624083398897387,
                supporting_mood_ids=(12984624083398897387,),
            )
            jupiter_intense_buff = _FakeBuffType(
                guid64=9203,
                mood_type_id=3027807324045670738,
            )
            summary = {
                "buffs_added": 0,
                "buffs_removed": 0,
                "intense_buffs_added": 0,
                "intense_buffs_removed": 0,
                "dispatch_failures": 0,
            }

            changed = retrograde_markers._apply_retrograde_consequences_for_sim(
                sim_info,
                desired_base_bodies=set(),
                desired_intense_bodies={"Jupiter"},
                base_buff_by_body={},
                intense_buff_by_body={"Jupiter": jupiter_intense_buff},
                summary=summary,
            )

            self.assertTrue(changed)
            self.assertEqual(1, summary["intense_buffs_added"])
            self.assertEqual({jupiter_intense_buff}, sim_info.buffs)
        finally:
            retrograde_markers._sim_info_has_buff = original_has_buff
            retrograde_markers._sim_info_remove_buff = original_remove_buff
            retrograde_markers._sim_info_add_buff = original_add_buff
            retrograde_markers._run_loot_on_sim_info = original_run_loot


if __name__ == "__main__":
    unittest.main()
