import pathlib
import sys
import unittest


sys.dont_write_bytecode = True

ROOT = pathlib.Path(__file__).resolve().parents[1]
PYTHON_DIR = ROOT / "python"
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))


from cosmic_engine import retrograde_effects


class _FakeTransitService(object):
    def __init__(self, active_by_body):
        self._active_by_body = dict(active_by_body)

    def retrograde_active_by_body(self):
        return dict(self._active_by_body)


class _FakeStatistic(object):
    def __init__(self):
        self.amounts = []

    def add_value(self, amount):
        self.amounts.append(float(amount))


class _FakeTarget(object):
    def __init__(self, *, statistic=None, is_broken=False, tags=()):
        self._statistic = statistic
        self.is_broken = bool(is_broken)
        self.tags = tuple(tags)

    def get_stat_instance(self, statistic_id):
        if int(statistic_id) == retrograde_effects.STATISTIC_BREAKAGE_ID:
            return self._statistic
        return None


class _FakeInteraction(object):
    def __init__(self, target, affordance=None, sim=None):
        self.target = target
        self.affordance = affordance or type("UseObject", (), {})
        self.sim = sim


class _FakeRelationshipTracker(object):
    def __init__(self, scores=None):
        self.scores = dict(scores or {})
        self.adjustments = []

    def get_relationship_score(self, target_id, track_id):
        return self.scores.get((int(target_id), int(track_id)), 0.0)

    def add_relationship_score(self, target_id, amount, track_id):
        key = (int(target_id), int(track_id))
        self.adjustments.append((int(target_id), float(amount), int(track_id)))
        self.scores[key] = self.scores.get(key, 0.0) + float(amount)


class _FakeSimInfo(object):
    def __init__(self, sim_id, *, age="teen", energy_statistic=None, relationship_tracker=None):
        self.sim_id = int(sim_id)
        self.age = age
        self._energy_statistic = energy_statistic
        self.relationship_tracker = relationship_tracker or _FakeRelationshipTracker()

    def get_stat_instance(self, statistic_id):
        if int(statistic_id) == retrograde_effects.STATISTIC_ENERGY_ID:
            return self._energy_statistic
        return None


class _FakeSim(object):
    def __init__(self, sim_info):
        self.sim_info = sim_info


class _FakeSimTarget(object):
    def __init__(self, sim_info):
        self.sim_info = sim_info


class RetrogradeEffectTests(unittest.TestCase):
    def setUp(self):
        self._original_tuning_cache = retrograde_effects._BREAKAGE_STATISTIC_TUNING_CACHE
        self._original_addon_cache = retrograde_effects._RETROGRADES_ADDON_AVAILABLE_CACHE
        self._original_notice_times = dict(retrograde_effects._LAST_EFFECT_NOTICE_AT)
        retrograde_effects._BREAKAGE_STATISTIC_TUNING_CACHE = None
        retrograde_effects._RETROGRADES_ADDON_AVAILABLE_CACHE = False
        retrograde_effects._LAST_EFFECT_NOTICE_AT.clear()

    def tearDown(self):
        retrograde_effects._BREAKAGE_STATISTIC_TUNING_CACHE = self._original_tuning_cache
        retrograde_effects._RETROGRADES_ADDON_AVAILABLE_CACHE = self._original_addon_cache
        retrograde_effects._LAST_EFFECT_NOTICE_AT.clear()
        retrograde_effects._LAST_EFFECT_NOTICE_AT.update(self._original_notice_times)

    def test_mercury_wear_applies_to_repairable_target_after_successful_roll(self):
        statistic = _FakeStatistic()
        interaction = _FakeInteraction(_FakeTarget(statistic=statistic))

        result = retrograde_effects.on_completed_interaction(
            interaction,
            transit_service=_FakeTransitService({"Mercury": True}),
            random_roll_fn=lambda: 0.0,
            retrogrades_addon_available=True,
        )

        self.assertTrue(result["handled"])
        self.assertTrue(result["applied"])
        self.assertEqual("wear_applied", result["reason"])
        self.assertEqual([retrograde_effects.MERCURY_OBJECT_WEAR_AMOUNT], statistic.amounts)

    def test_mercury_wear_does_not_run_when_mercury_is_inactive(self):
        statistic = _FakeStatistic()
        interaction = _FakeInteraction(_FakeTarget(statistic=statistic))

        result = retrograde_effects.on_completed_interaction(
            interaction,
            transit_service=_FakeTransitService({"Mercury": False}),
            random_roll_fn=lambda: 0.0,
            retrogrades_addon_available=True,
        )

        self.assertFalse(result["handled"])
        self.assertEqual("no_relevant_retrogrades", result["reason"])
        self.assertEqual([], statistic.amounts)

    def test_mercury_wear_skips_unbreakable_and_already_broken_targets(self):
        cases = (
            _FakeTarget(statistic=_FakeStatistic(), tags=("Func_Unbreakable_Object",)),
            _FakeTarget(statistic=_FakeStatistic(), is_broken=True),
        )

        for target in cases:
            with self.subTest(target=target):
                result = retrograde_effects.on_completed_interaction(
                    _FakeInteraction(target),
                    transit_service=_FakeTransitService({"Mercury": True}),
                    random_roll_fn=lambda: 0.0,
                    retrogrades_addon_available=True,
                )
                self.assertFalse(result["applied"])
                self.assertIn(result["reason"], {"unbreakable_target", "already_broken"})
                self.assertEqual([], target._statistic.amounts)

    def test_mercury_wear_skips_repair_and_duplicate_completion_dispatch(self):
        statistic = _FakeStatistic()
        repair_affordance = type("RepairObject", (), {})
        repair_result = retrograde_effects.on_completed_interaction(
            _FakeInteraction(_FakeTarget(statistic=statistic), affordance=repair_affordance),
            transit_service=_FakeTransitService({"Mercury": True}),
            random_roll_fn=lambda: 0.0,
            retrogrades_addon_available=True,
        )
        self.assertEqual("maintenance_interaction", repair_result["reason"])
        self.assertEqual([], statistic.amounts)

        interaction = _FakeInteraction(_FakeTarget(statistic=statistic))
        first = retrograde_effects.on_completed_interaction(
            interaction,
            transit_service=_FakeTransitService({"Mercury": True}),
            random_roll_fn=lambda: 0.0,
            retrogrades_addon_available=True,
        )
        second = retrograde_effects.on_completed_interaction(
            interaction,
            transit_service=_FakeTransitService({"Mercury": True}),
            random_roll_fn=lambda: 0.0,
            retrogrades_addon_available=True,
        )
        self.assertTrue(first["applied"])
        self.assertEqual("already_processed", second["reason"])
        self.assertEqual([retrograde_effects.MERCURY_OBJECT_WEAR_AMOUNT], statistic.amounts)

    def test_mercury_wear_never_creates_breakage_for_nonrepairable_target(self):
        interaction = _FakeInteraction(_FakeTarget(statistic=None))

        result = retrograde_effects.on_completed_interaction(
            interaction,
            transit_service=_FakeTransitService({"Mercury": True}),
            random_roll_fn=lambda: 0.0,
            retrogrades_addon_available=True,
        )

        self.assertFalse(result["handled"])
        self.assertEqual("not_repairable", result["reason"])

    def test_mercury_wear_is_disabled_without_the_optional_retrogrades_package(self):
        statistic = _FakeStatistic()
        interaction = _FakeInteraction(_FakeTarget(statistic=statistic))

        result = retrograde_effects.on_completed_interaction(
            interaction,
            transit_service=_FakeTransitService({"Mercury": True}),
            random_roll_fn=lambda: 0.0,
            retrogrades_addon_available=False,
        )

        self.assertFalse(result["handled"])
        self.assertEqual("retrogrades_addon_unavailable", result["reason"])
        self.assertEqual([], statistic.amounts)

    def test_venus_applies_only_a_small_low_relationship_social_correction(self):
        relationship_tracker = _FakeRelationshipTracker(
            {(2, retrograde_effects.LTR_FRIENDSHIP_MAIN_TRACK_ID): 10.0}
        )
        actor = _FakeSimInfo(1, relationship_tracker=relationship_tracker)
        target = _FakeSimInfo(2)
        interaction = _FakeInteraction(
            _FakeSimTarget(target),
            affordance=type("SocialMixerFriendlyChat", (), {}),
            sim=_FakeSim(actor),
        )

        result = retrograde_effects.on_completed_interaction(
            interaction,
            transit_service=_FakeTransitService({"Venus": True}),
            random_roll_fn=lambda: 0.0,
            retrogrades_addon_available=True,
        )

        self.assertTrue(result["applied"])
        self.assertEqual("connection_drag_applied", result["reason"])
        self.assertEqual(
            [(2, retrograde_effects.VENUS_NEW_CONNECTION_AMOUNT, retrograde_effects.LTR_FRIENDSHIP_MAIN_TRACK_ID)],
            relationship_tracker.adjustments,
        )

    def test_venus_skips_established_relationships_and_children(self):
        adult_tracker = _FakeRelationshipTracker(
            {(2, retrograde_effects.LTR_FRIENDSHIP_MAIN_TRACK_ID): 60.0}
        )
        adult = _FakeSimInfo(1, relationship_tracker=adult_tracker)
        target = _FakeSimInfo(2)
        established = _FakeInteraction(
            _FakeSimTarget(target),
            affordance=type("SocialMixerFriendlyChat", (), {}),
            sim=_FakeSim(adult),
        )
        child = _FakeInteraction(
            _FakeSimTarget(target),
            affordance=type("SocialMixerFriendlyChat", (), {}),
            sim=_FakeSim(_FakeSimInfo(3, age="child")),
        )

        for interaction, expected_reason in ((established, "established_or_unknown_relationship"), (child, "not_eligible_social")):
            with self.subTest(reason=expected_reason):
                result = retrograde_effects.on_completed_interaction(
                    interaction,
                    transit_service=_FakeTransitService({"Venus": True}),
                    random_roll_fn=lambda: 0.0,
                    retrogrades_addon_available=True,
                )
                self.assertFalse(result["applied"])
                self.assertEqual(expected_reason, result["reason"])

    def test_mars_fatigue_can_apply_after_an_existing_strenuous_interaction(self):
        energy = _FakeStatistic()
        actor = _FakeSimInfo(1, energy_statistic=energy)
        interaction = _FakeInteraction(
            _FakeTarget(),
            affordance=type("FitnessWorkout", (), {}),
            sim=_FakeSim(actor),
        )

        result = retrograde_effects.on_completed_interaction(
            interaction,
            transit_service=_FakeTransitService({"Mars": True}),
            random_roll_fn=lambda: 0.0,
            retrogrades_addon_available=True,
        )

        self.assertTrue(result["applied"])
        self.assertEqual("fatigue_applied", result["reason"])
        self.assertEqual([retrograde_effects.MARS_STRENUOUS_ENERGY_AMOUNT], energy.amounts)

    def test_jupiter_and_saturn_reward_only_their_constructive_actions(self):
        jupiter_energy = _FakeStatistic()
        jupiter = _FakeInteraction(
            _FakeTarget(), affordance=type("MentoringSkillBook", (), {}), sim=_FakeSim(_FakeSimInfo(1, energy_statistic=jupiter_energy))
        )
        saturn_energy = _FakeStatistic()
        saturn = _FakeInteraction(
            _FakeTarget(), affordance=type("CompleteHomework", (), {}), sim=_FakeSim(_FakeSimInfo(2, age="child", energy_statistic=saturn_energy))
        )

        jupiter_result = retrograde_effects.on_completed_interaction(
            jupiter,
            transit_service=_FakeTransitService({"Jupiter": True}),
            retrogrades_addon_available=True,
        )
        saturn_result = retrograde_effects.on_completed_interaction(
            saturn,
            transit_service=_FakeTransitService({"Saturn": True}),
            retrogrades_addon_available=True,
        )

        self.assertEqual("relearning_reward_applied", jupiter_result["reason"])
        self.assertEqual([retrograde_effects.JUPITER_RELEARNING_ENERGY_AMOUNT], jupiter_energy.amounts)
        self.assertEqual("follow_through_reward_applied", saturn_result["reason"])
        self.assertEqual([retrograde_effects.SATURN_FOLLOW_THROUGH_ENERGY_AMOUNT], saturn_energy.amounts)

    def test_applied_effect_routes_the_exact_planet_notice_once(self):
        statistic = _FakeStatistic()
        actor = _FakeSimInfo(1)
        interaction = _FakeInteraction(_FakeTarget(statistic=statistic), sim=_FakeSim(actor))
        original_show_notice = retrograde_effects._show_effect_notice
        notice_calls = []
        try:
            retrograde_effects._show_effect_notice = lambda planet, completed_interaction: notice_calls.append((planet, completed_interaction)) or True
            result = retrograde_effects.on_completed_interaction(
                interaction,
                transit_service=_FakeTransitService({"Mercury": True}),
                random_roll_fn=lambda: 0.0,
                retrogrades_addon_available=True,
            )
        finally:
            retrograde_effects._show_effect_notice = original_show_notice

        self.assertTrue(result["notification_shown"])
        self.assertEqual([("mercury", interaction)], notice_calls)
        self.assertEqual(
            (
                "Mercury Retrograde: Technically Working",
                "The device survived another use. Whether it will survive the next one is between it and Mercury.",
            ),
            retrograde_effects.EFFECT_NOTICE_BY_PLANET["mercury"],
        )


if __name__ == "__main__":
    unittest.main()
