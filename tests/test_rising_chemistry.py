import importlib
import pathlib
import sys
import unittest


sys.dont_write_bytecode = True

ROOT = pathlib.Path(__file__).resolve().parents[1]
PYTHON_DIR = ROOT / "python"
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))


def _import_rising_chemistry_module():
    try:
        return importlib.import_module("cosmic_engine.rising_chemistry")
    except ModuleNotFoundError as exc:
        if exc.name != "cosmic_engine.rising_chemistry":
            raise
    return None


def _import_loot_actions_module():
    try:
        return importlib.import_module("cosmic_engine.loot_actions")
    except ModuleNotFoundError as exc:
        if exc.name != "cosmic_engine.loot_actions":
            raise
    return None


def _resolve_band(score):
    module = _import_rising_chemistry_module()
    if module is None:
        raise AssertionError("Expected cosmic_engine.rising_chemistry module to exist.")
    resolver = getattr(module, "resolve_relationship_band", None)
    if not callable(resolver):
        raise AssertionError(
            "Expected resolve_relationship_band(score) helper in cosmic_engine.rising_chemistry."
        )
    return resolver(score)


def _build_profile_band_key(profile_id, band):
    module = _import_rising_chemistry_module()
    if module is None:
        raise AssertionError("Expected cosmic_engine.rising_chemistry module to exist.")
    builder = getattr(module, "build_profile_band_key", None)
    if not callable(builder):
        raise AssertionError(
            "Expected build_profile_band_key(profile_id, band) helper in cosmic_engine.rising_chemistry."
        )
    return builder(profile_id, band)


def _build_refresh_summary(
    profile_id,
    relationship_score=None,
    actor_sim_id=1,
    target_sim_id=2,
    friendship_score=None,
    romance_score=None,
):
    module = _import_rising_chemistry_module()
    if module is None:
        raise AssertionError("Expected cosmic_engine.rising_chemistry module to exist.")
    builder = getattr(module, "build_refresh_summary", None)
    if not callable(builder):
        raise AssertionError(
            "Expected build_refresh_summary(...) helper in cosmic_engine.rising_chemistry."
        )
    summary = builder(
        actor_sim_id=actor_sim_id,
        target_sim_id=target_sim_id,
        profile_id=profile_id,
        relationship_score=relationship_score,
        friendship_score=friendship_score,
        romance_score=romance_score,
    )
    if not isinstance(summary, dict):
        raise AssertionError("build_refresh_summary(...) must return a dict.")
    return summary


def _build_actor_buff_plan(sign_name, profile_id, friendship_score=None, romance_score=None):
    module = _import_rising_chemistry_module()
    if module is None:
        raise AssertionError("Expected cosmic_engine.rising_chemistry module to exist.")
    builder = getattr(module, "build_actor_rising_chemistry_buff_plan", None)
    if not callable(builder):
        raise AssertionError(
            "Expected build_actor_rising_chemistry_buff_plan(...) helper in cosmic_engine.rising_chemistry."
        )
    plan = builder(
        sign_name=sign_name,
        profile_id=profile_id,
        friendship_score=friendship_score,
        romance_score=romance_score,
    )
    if not isinstance(plan, dict):
        raise AssertionError("build_actor_rising_chemistry_buff_plan(...) must return a dict.")
    return plan


class RisingChemistryTests(unittest.TestCase):
    def test_relationship_band_zero_to_thirty_is_initial(self):
        for score in (0, 15, 30):
            with self.subTest(score=score):
                self.assertEqual("initial", _resolve_band(score))

    def test_relationship_band_thirty_one_to_sixty_is_mixed(self):
        for score in (31, 45, 60):
            with self.subTest(score=score):
                self.assertEqual("mixed", _resolve_band(score))

    def test_relationship_band_sixty_one_and_above_is_residual(self):
        for score in (61, 80, 100):
            with self.subTest(score=score):
                self.assertEqual("residual", _resolve_band(score))

    def test_relationship_band_uses_absolute_magnitude_for_negative_scores(self):
        expected_by_score = {
            -5: "initial",
            -31: "mixed",
            -75: "residual",
        }
        for score, expected in expected_by_score.items():
            with self.subTest(score=score):
                self.assertEqual(expected, _resolve_band(score))

    def test_profile_band_key_normalizes_profile_and_band(self):
        self.assertEqual("dramatic_residual", _build_profile_band_key(" Dramatic ", "residual"))

    def test_refresh_summary_exposes_profile_band_shape_for_followup_xml(self):
        summary = _build_refresh_summary("subtle", relationship_score=31)

        self.assertTrue(summary.get("ok"))
        self.assertEqual("resolved", summary.get("reason"))
        self.assertEqual(1, summary.get("actor_sim_id"))
        self.assertEqual(2, summary.get("target_sim_id"))
        self.assertEqual("subtle", summary.get("profile_id"))
        self.assertEqual(31, summary.get("relationship_score"))
        self.assertEqual("mixed", summary.get("relationship_band"))
        self.assertEqual("subtle_mixed", summary.get("profile_band_key"))
        self.assertEqual([], summary.get("pending_buff_keys"))

    def test_refresh_summary_preserves_friendship_and_romance_tracks_separately(self):
        summary = _build_refresh_summary(
            "balanced",
            friendship_score=-72,
            romance_score=18,
        )

        self.assertEqual({"friendship": -72, "romance": 18}, summary.get("relationship_scores"))
        self.assertEqual(
            {"friendship": "residual", "romance": "initial"},
            summary.get("relationship_bands"),
        )
        self.assertIsNone(summary.get("relationship_score"))
        self.assertIsNone(summary.get("relationship_band"))
        self.assertEqual([], summary.get("pending_buff_keys"))

    def test_actor_rising_buff_plan_uses_dominant_track_magnitude(self):
        plan = _build_actor_buff_plan(
            "Scorpio",
            "dramatic",
            friendship_score=-72,
            romance_score=18,
        )

        self.assertEqual("friendship", plan.get("applied_track"))
        self.assertEqual("residual", plan.get("relationship_band"))
        self.assertEqual("residual", plan.get("affordance_stage"))
        self.assertEqual("scorpio_residual_dramatic", plan.get("managed_buff_key"))

    def test_sync_actor_rising_buffs_keeps_existing_state_when_replacement_resource_is_missing(self):
        loot_actions = _import_loot_actions_module()
        rising_chemistry = _import_rising_chemistry_module()
        if loot_actions is None or rising_chemistry is None:
            raise AssertionError("Expected cosmic_engine loot modules to exist.")

        original_iter = rising_chemistry.iter_actor_rising_chemistry_managed_buff_ids
        original_resolve_buff = loot_actions._resolve_buff
        original_sim_has_buff = loot_actions._sim_has_buff
        original_remove_buff_if_present = loot_actions._remove_buff_if_present
        original_add_buff_if_missing = loot_actions._add_buff_if_missing

        existing_buff_ids = {111}
        removed_buff_ids = []
        added_buff_ids = []

        try:
            rising_chemistry.iter_actor_rising_chemistry_managed_buff_ids = lambda: (111, 333)
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

            summary = loot_actions._sync_actor_rising_chemistry_buffs(
                object(),
                {"ok": True, "managed_buff_id": 333},
            )

            self.assertFalse(summary.get("ok"))
            self.assertEqual("missing_buff_resource", summary.get("reason"))
            self.assertEqual(333, summary.get("applied_buff_id"))
            self.assertEqual([], summary.get("removed_buff_ids"))
            self.assertEqual(0, summary.get("removed_count"))
            self.assertEqual([], removed_buff_ids)
            self.assertEqual([], added_buff_ids)
            self.assertEqual({111}, existing_buff_ids)
        finally:
            rising_chemistry.iter_actor_rising_chemistry_managed_buff_ids = original_iter
            loot_actions._resolve_buff = original_resolve_buff
            loot_actions._sim_has_buff = original_sim_has_buff
            loot_actions._remove_buff_if_present = original_remove_buff_if_present
            loot_actions._add_buff_if_missing = original_add_buff_if_missing

    def test_first_contact_rising_pass_is_skipped_when_pair_is_already_known(self):
        module = _import_rising_chemistry_module()
        if module is None:
            raise AssertionError("Expected cosmic_engine.rising_chemistry module to exist.")
        helper = getattr(module, "should_apply_first_contact_rising_pass", None)
        if not callable(helper):
            raise AssertionError(
                "Expected should_apply_first_contact_rising_pass(rising_known=False) helper in cosmic_engine.rising_chemistry."
        )
        self.assertTrue(helper(rising_known=False))
        self.assertFalse(helper(rising_known=True))

    def test_runtime_completed_social_refresh_entrypoint_reuses_refresh_flow(self):
        loot_actions = _import_loot_actions_module()
        rising_chemistry = _import_rising_chemistry_module()
        sun_chemistry = importlib.import_module("cosmic_engine.sun_chemistry")
        ts4_runtime_install = importlib.import_module("cosmic_engine.ts4_runtime_install")
        houses_notification_bridge = importlib.import_module("cosmic_engine.houses_notification_bridge")
        if loot_actions is None or rising_chemistry is None:
            raise AssertionError("Expected cosmic_engine loot modules to exist.")

        class _FakeRelationshipTracker(object):
            def __init__(self):
                self.present_relbits_by_target = {}

            def has_relationship_bit(self, target_sim_id, bit_id):
                return int(bit_id) in self.present_relbits_by_target.get(int(target_sim_id), set())

            def add_relationship_bit(self, target_sim_id, bit_id):
                target_sim_id = int(target_sim_id)
                bit_id = int(bit_id)
                self.present_relbits_by_target.setdefault(target_sim_id, set()).add(bit_id)
                return True

        class _FakeSimInfo(object):
            def __init__(self, sim_id, full_name):
                self.sim_id = int(sim_id)
                self.full_name = full_name
                self.relationship_tracker = _FakeRelationshipTracker()

        actor = _FakeSimInfo(111, "Actor Sim")
        target = _FakeSimInfo(222, "Target Sim")

        original_relationship_summary = loot_actions._resolve_relationship_score_summary
        original_collect_traits = loot_actions._collect_trait_ids_and_markers
        original_sync_rising = loot_actions._sync_actor_rising_chemistry_buffs
        original_sync_sun = loot_actions._sync_actor_sun_chemistry_overlay_buffs
        original_resolve_active_sun_tier = loot_actions._resolve_active_sun_chemistry_tier_name
        original_chart_payload_for_sim = loot_actions._chart_payload_for_sim
        original_build_refresh_summary = rising_chemistry.build_refresh_summary
        original_build_actor_plan = rising_chemistry.build_actor_rising_chemistry_buff_plan
        original_should_apply_rising = rising_chemistry.should_apply_first_contact_rising_pass
        original_build_sun_plan = sun_chemistry.build_sun_overlay_buff_plan
        original_should_apply_sun = sun_chemistry.should_apply_first_contact_sun_pass
        original_load_profile = ts4_runtime_install.load_chemistry_profile
        original_resolve_rising = houses_notification_bridge.resolve_rising_sign_index_from_trait_ids

        try:
            loot_actions._resolve_relationship_score_summary = lambda _actor, _target: {
                "scores": {"friendship": 12, "romance": 48},
                "source_owners": {"friendship": "actor", "romance": "target"},
                "track_ids": {"friendship": 16650, "romance": 16651},
            }
            loot_actions._collect_trait_ids_and_markers = (
                lambda sim_info: ((101,) if sim_info is actor else (202,), set())
            )
            loot_actions._sync_actor_rising_chemistry_buffs = lambda _sim, _plan: {
                "ok": True,
                "reason": "added",
            }
            loot_actions._sync_actor_sun_chemistry_overlay_buffs = lambda _sim, _plan: {
                "ok": True,
                "reason": "added",
            }
            loot_actions._resolve_active_sun_chemistry_tier_name = lambda _actor, _target: "VeryCompatible"
            loot_actions._chart_payload_for_sim = lambda sim_id, sim_info=None: {
                "sun_sign_index": 0 if int(sim_id) == 111 else 3,
            }
            rising_chemistry.build_refresh_summary = lambda **kwargs: {
                "ok": True,
                "reason": "resolved",
                "actor_sim_id": kwargs.get("actor_sim_id"),
                "target_sim_id": kwargs.get("target_sim_id"),
                "profile_id": kwargs.get("profile_id"),
                "relationship_scores": {
                    "friendship": kwargs.get("friendship_score"),
                    "romance": kwargs.get("romance_score"),
                },
                "relationship_bands": {"friendship": "initial", "romance": "mixed"},
                "pending_buff_keys": [],
                "pending_buff_count": 0,
            }
            rising_chemistry.build_actor_rising_chemistry_buff_plan = lambda **kwargs: {
                "ok": True,
                "reason": "resolved",
                "managed_buff_key": "aquarius_initial_dramatic",
                "affordance_stage": "initial",
            }
            rising_chemistry.should_apply_first_contact_rising_pass = lambda **kwargs: not bool(
                kwargs.get("rising_known")
            )
            sun_chemistry.build_sun_overlay_buff_plan = lambda tier_name, profile_id: {
                "ok": True,
                "reason": "resolved",
                "tier_name": tier_name,
                "profile_id": profile_id,
                "overlay_name": "Overlay_Debug",
            }
            sun_chemistry.should_apply_first_contact_sun_pass = lambda **kwargs: not bool(
                kwargs.get("sun_known")
            )
            ts4_runtime_install.load_chemistry_profile = lambda: {"chemistry_profile_id": "dramatic"}
            houses_notification_bridge.resolve_rising_sign_index_from_trait_ids = (
                lambda trait_ids: 10 if tuple(trait_ids) == (101,) else 4
            )

            summary_bundle = loot_actions.refresh_chemistry_after_completed_social(
                actor,
                target,
                source="runtime.social_complete",
            )
            summary = loot_actions.get_last_rising_chemistry_refresh_summary()
            sun_summary = loot_actions.get_last_sun_chemistry_refresh_summary()

            self.assertTrue(summary_bundle.get("ok"))
            self.assertEqual("dispatched", summary_bundle.get("reason"))
            self.assertEqual("runtime.social_complete", summary_bundle.get("source"))
            self.assertEqual("runtime.social_complete", summary.get("trigger_reason"))
            self.assertEqual("runtime.social_complete", sun_summary.get("trigger_reason"))
            self.assertEqual("write_both", summary.get("pair_memory_write", {}).get("reason"))
        finally:
            loot_actions._resolve_relationship_score_summary = original_relationship_summary
            loot_actions._collect_trait_ids_and_markers = original_collect_traits
            loot_actions._sync_actor_rising_chemistry_buffs = original_sync_rising
            loot_actions._sync_actor_sun_chemistry_overlay_buffs = original_sync_sun
            loot_actions._resolve_active_sun_chemistry_tier_name = original_resolve_active_sun_tier
            loot_actions._chart_payload_for_sim = original_chart_payload_for_sim
            rising_chemistry.build_refresh_summary = original_build_refresh_summary
            rising_chemistry.build_actor_rising_chemistry_buff_plan = original_build_actor_plan
            rising_chemistry.should_apply_first_contact_rising_pass = original_should_apply_rising
            sun_chemistry.build_sun_overlay_buff_plan = original_build_sun_plan
            sun_chemistry.should_apply_first_contact_sun_pass = original_should_apply_sun
            ts4_runtime_install.load_chemistry_profile = original_load_profile
            houses_notification_bridge.resolve_rising_sign_index_from_trait_ids = original_resolve_rising

    def test_refresh_loot_exposes_pair_memory_flags_and_gates_first_contact_writes(self):
        loot_actions = _import_loot_actions_module()
        rising_chemistry = _import_rising_chemistry_module()
        sun_chemistry = importlib.import_module("cosmic_engine.sun_chemistry")
        ts4_runtime_install = importlib.import_module("cosmic_engine.ts4_runtime_install")
        houses_notification_bridge = importlib.import_module("cosmic_engine.houses_notification_bridge")
        if loot_actions is None or rising_chemistry is None:
            raise AssertionError("Expected cosmic_engine loot modules to exist.")

        class _FakeRelationshipTracker(object):
            def __init__(self):
                self.present_relbits_by_target = {}
                self.added_relbits = []

            def has_relationship_bit(self, target_sim_id, bit_id):
                return int(bit_id) in self.present_relbits_by_target.get(int(target_sim_id), set())

            def add_relationship_bit(self, target_sim_id, bit_id):
                target_sim_id = int(target_sim_id)
                bit_id = int(bit_id)
                self.added_relbits.append(bit_id)
                self.present_relbits_by_target.setdefault(target_sim_id, set()).add(bit_id)
                return True

        class _FakeSimInfo(object):
            def __init__(self, sim_id, full_name):
                self.sim_id = int(sim_id)
                self.full_name = full_name
                self.relationship_tracker = _FakeRelationshipTracker()

        actor = _FakeSimInfo(111, "Actor Sim")
        target = _FakeSimInfo(222, "Target Sim")

        original_resolve_actor = loot_actions._resolve_actor_sim_info
        original_resolve_participant = loot_actions._resolve_participant_sim_info
        original_relationship_summary = loot_actions._resolve_relationship_score_summary
        original_collect_traits = loot_actions._collect_trait_ids_and_markers
        original_sync_rising = loot_actions._sync_actor_rising_chemistry_buffs
        original_sync_sun = loot_actions._sync_actor_sun_chemistry_overlay_buffs
        original_resolve_active_sun_tier = loot_actions._resolve_active_sun_chemistry_tier_name
        original_chart_payload_for_sim = loot_actions._chart_payload_for_sim
        original_build_refresh_summary = rising_chemistry.build_refresh_summary
        original_build_actor_plan = rising_chemistry.build_actor_rising_chemistry_buff_plan
        original_should_apply_rising = rising_chemistry.should_apply_first_contact_rising_pass
        original_build_sun_plan = sun_chemistry.build_sun_overlay_buff_plan
        original_should_apply_sun = sun_chemistry.should_apply_first_contact_sun_pass
        original_load_profile = ts4_runtime_install.load_chemistry_profile
        original_resolve_rising = houses_notification_bridge.resolve_rising_sign_index_from_trait_ids

        try:
            loot_actions._resolve_actor_sim_info = lambda _resolver: actor
            loot_actions._resolve_participant_sim_info = lambda _resolver, _participants: target
            loot_actions._resolve_relationship_score_summary = lambda _actor, _target: {
                "scores": {"friendship": 12, "romance": 48},
                "source_owners": {"friendship": "actor", "romance": "target"},
                "track_ids": {"friendship": 16650, "romance": 16651},
            }
            loot_actions._collect_trait_ids_and_markers = (
                lambda sim_info: ((101,) if sim_info is actor else (202,), set())
            )
            loot_actions._sync_actor_rising_chemistry_buffs = lambda _sim, _plan: {
                "ok": True,
                "reason": "added",
            }
            loot_actions._sync_actor_sun_chemistry_overlay_buffs = lambda _sim, _plan: {
                "ok": True,
                "reason": "added",
            }
            loot_actions._resolve_active_sun_chemistry_tier_name = lambda _actor, _target: "VeryCompatible"
            loot_actions._chart_payload_for_sim = lambda sim_id, sim_info=None: {
                "sun_sign_index": 0 if int(sim_id) == 111 else 3,
            }
            rising_chemistry.build_refresh_summary = lambda **kwargs: {
                "ok": True,
                "reason": "resolved",
                "actor_sim_id": kwargs.get("actor_sim_id"),
                "target_sim_id": kwargs.get("target_sim_id"),
                "profile_id": kwargs.get("profile_id"),
                "relationship_scores": {
                    "friendship": kwargs.get("friendship_score"),
                    "romance": kwargs.get("romance_score"),
                },
                "relationship_bands": {"friendship": "initial", "romance": "mixed"},
                "pending_buff_keys": [],
                "pending_buff_count": 0,
            }
            rising_chemistry.build_actor_rising_chemistry_buff_plan = lambda **kwargs: {
                "ok": True,
                "reason": "resolved",
                "managed_buff_key": "aquarius_initial_dramatic",
                "affordance_stage": "initial",
            }
            rising_chemistry.should_apply_first_contact_rising_pass = lambda **kwargs: not bool(
                kwargs.get("rising_known")
            )
            sun_chemistry.build_sun_overlay_buff_plan = lambda tier_name, profile_id: {
                "ok": True,
                "reason": "resolved",
                "tier_name": tier_name,
                "profile_id": profile_id,
                "overlay_name": "Overlay_Debug",
            }
            sun_chemistry.should_apply_first_contact_sun_pass = lambda **kwargs: not bool(
                kwargs.get("sun_known")
            )
            ts4_runtime_install.load_chemistry_profile = lambda: {"chemistry_profile_id": "dramatic"}
            houses_notification_bridge.resolve_rising_sign_index_from_trait_ids = (
                lambda trait_ids: 10 if tuple(trait_ids) == (101,) else 4
            )

            loot = loot_actions.CosmicEngineRefreshRisingChemistryLoot()
            loot.apply_to_resolver(object())

            summary = loot_actions.get_last_rising_chemistry_refresh_summary()
            sun_summary = loot_actions.get_last_sun_chemistry_refresh_summary()

            self.assertEqual("Aquarius", summary.get("actor_rising_sign_name"))
            self.assertEqual("Leo", summary.get("target_rising_sign_name"))
            self.assertEqual("Aries", summary.get("actor_sun_sign_name"))
            self.assertEqual("Cancer", summary.get("target_sun_sign_name"))
            self.assertFalse(summary.get("rising_known"))
            self.assertFalse(summary.get("sun_known"))
            self.assertTrue(summary.get("apply_first_contact_rising"))
            self.assertEqual("write_both", summary.get("pair_memory_write", {}).get("reason"))
            self.assertEqual(
                [830000000000009601, 830000000000009602],
                summary.get("written_pair_memory_relbit_ids"),
            )
            self.assertEqual(
                [
                    830000000000009601,
                    830000000000009602,
                    830000000000043003,
                    830000000000043022,
                ],
                actor.relationship_tracker.added_relbits,
            )
            self.assertEqual(
                [
                    830000000000009601,
                    830000000000009602,
                    830000000000043003,
                    830000000000043022,
                ],
                target.relationship_tracker.added_relbits,
            )
            self.assertEqual(
                ("Sun", "Rising"),
                tuple(summary.get("sign_compatibility_seed_summary", {}).get("written_lanes", ())),
            )
            self.assertFalse(sun_summary.get("sun_known"))
            self.assertTrue(sun_summary.get("apply_first_contact_sun"))
        finally:
            loot_actions._resolve_actor_sim_info = original_resolve_actor
            loot_actions._resolve_participant_sim_info = original_resolve_participant
            loot_actions._resolve_relationship_score_summary = original_relationship_summary
            loot_actions._collect_trait_ids_and_markers = original_collect_traits
            loot_actions._sync_actor_rising_chemistry_buffs = original_sync_rising
            loot_actions._sync_actor_sun_chemistry_overlay_buffs = original_sync_sun
            loot_actions._resolve_active_sun_chemistry_tier_name = original_resolve_active_sun_tier
            loot_actions._chart_payload_for_sim = original_chart_payload_for_sim
            rising_chemistry.build_refresh_summary = original_build_refresh_summary
            rising_chemistry.build_actor_rising_chemistry_buff_plan = original_build_actor_plan
            rising_chemistry.should_apply_first_contact_rising_pass = original_should_apply_rising
            sun_chemistry.build_sun_overlay_buff_plan = original_build_sun_plan
            sun_chemistry.should_apply_first_contact_sun_pass = original_should_apply_sun
            ts4_runtime_install.load_chemistry_profile = original_load_profile
            houses_notification_bridge.resolve_rising_sign_index_from_trait_ids = original_resolve_rising

    def test_refresh_loot_does_not_report_pair_memory_write_success_when_only_subset_aligns(self):
        loot_actions = _import_loot_actions_module()
        rising_chemistry = _import_rising_chemistry_module()
        sun_chemistry = importlib.import_module("cosmic_engine.sun_chemistry")
        ts4_runtime_install = importlib.import_module("cosmic_engine.ts4_runtime_install")
        houses_notification_bridge = importlib.import_module("cosmic_engine.houses_notification_bridge")
        if loot_actions is None or rising_chemistry is None:
            raise AssertionError("Expected cosmic_engine loot modules to exist.")

        class _FakeRelationshipTracker(object):
            def __init__(self, blocked_relbit_ids=()):
                self.present_relbits_by_target = {}
                self.blocked_relbit_ids = {int(relbit_id) for relbit_id in tuple(blocked_relbit_ids)}
                self.added_relbits = []

            def has_relationship_bit(self, target_sim_id, bit_id):
                return int(bit_id) in self.present_relbits_by_target.get(int(target_sim_id), set())

            def add_relationship_bit(self, target_sim_id, bit_id):
                target_sim_id = int(target_sim_id)
                bit_id = int(bit_id)
                if bit_id in self.blocked_relbit_ids:
                    return False
                self.added_relbits.append(bit_id)
                self.present_relbits_by_target.setdefault(target_sim_id, set()).add(bit_id)
                return True

        class _FakeSimInfo(object):
            def __init__(self, sim_id, full_name, blocked_relbit_ids=()):
                self.sim_id = int(sim_id)
                self.full_name = full_name
                self.relationship_tracker = _FakeRelationshipTracker(blocked_relbit_ids=blocked_relbit_ids)

        actor = _FakeSimInfo(111, "Actor Sim")
        target = _FakeSimInfo(222, "Target Sim", blocked_relbit_ids=(830000000000009602,))

        original_resolve_actor = loot_actions._resolve_actor_sim_info
        original_resolve_participant = loot_actions._resolve_participant_sim_info
        original_relationship_summary = loot_actions._resolve_relationship_score_summary
        original_collect_traits = loot_actions._collect_trait_ids_and_markers
        original_sync_rising = loot_actions._sync_actor_rising_chemistry_buffs
        original_sync_sun = loot_actions._sync_actor_sun_chemistry_overlay_buffs
        original_resolve_active_sun_tier = loot_actions._resolve_active_sun_chemistry_tier_name
        original_chart_payload_for_sim = loot_actions._chart_payload_for_sim
        original_build_refresh_summary = rising_chemistry.build_refresh_summary
        original_build_actor_plan = rising_chemistry.build_actor_rising_chemistry_buff_plan
        original_should_apply_rising = rising_chemistry.should_apply_first_contact_rising_pass
        original_build_sun_plan = sun_chemistry.build_sun_overlay_buff_plan
        original_should_apply_sun = sun_chemistry.should_apply_first_contact_sun_pass
        original_load_profile = ts4_runtime_install.load_chemistry_profile
        original_resolve_rising = houses_notification_bridge.resolve_rising_sign_index_from_trait_ids

        try:
            loot_actions._resolve_actor_sim_info = lambda _resolver: actor
            loot_actions._resolve_participant_sim_info = lambda _resolver, _participants: target
            loot_actions._resolve_relationship_score_summary = lambda _actor, _target: {
                "scores": {"friendship": 12, "romance": 48},
                "source_owners": {"friendship": "actor", "romance": "target"},
                "track_ids": {"friendship": 16650, "romance": 16651},
            }
            loot_actions._collect_trait_ids_and_markers = (
                lambda sim_info: ((101,) if sim_info is actor else (202,), set())
            )
            loot_actions._sync_actor_rising_chemistry_buffs = lambda _sim, _plan: {
                "ok": True,
                "reason": "added",
            }
            loot_actions._sync_actor_sun_chemistry_overlay_buffs = lambda _sim, _plan: {
                "ok": True,
                "reason": "added",
            }
            loot_actions._resolve_active_sun_chemistry_tier_name = lambda _actor, _target: "VeryCompatible"
            loot_actions._chart_payload_for_sim = lambda sim_id, sim_info=None: {
                "sun_sign_index": 0 if int(sim_id) == 111 else 3,
            }
            rising_chemistry.build_refresh_summary = lambda **kwargs: {
                "ok": True,
                "reason": "resolved",
                "actor_sim_id": kwargs.get("actor_sim_id"),
                "target_sim_id": kwargs.get("target_sim_id"),
                "profile_id": kwargs.get("profile_id"),
                "relationship_scores": {
                    "friendship": kwargs.get("friendship_score"),
                    "romance": kwargs.get("romance_score"),
                },
                "relationship_bands": {"friendship": "initial", "romance": "mixed"},
                "pending_buff_keys": [],
                "pending_buff_count": 0,
            }
            rising_chemistry.build_actor_rising_chemistry_buff_plan = lambda **kwargs: {
                "ok": True,
                "reason": "resolved",
                "managed_buff_key": "aquarius_initial_dramatic",
                "affordance_stage": "initial",
            }
            rising_chemistry.should_apply_first_contact_rising_pass = lambda **kwargs: not bool(
                kwargs.get("rising_known")
            )
            sun_chemistry.build_sun_overlay_buff_plan = lambda tier_name, profile_id: {
                "ok": True,
                "reason": "resolved",
                "tier_name": tier_name,
                "profile_id": profile_id,
                "overlay_name": "Overlay_Debug",
            }
            sun_chemistry.should_apply_first_contact_sun_pass = lambda **kwargs: not bool(
                kwargs.get("sun_known")
            )
            ts4_runtime_install.load_chemistry_profile = lambda: {"chemistry_profile_id": "dramatic"}
            houses_notification_bridge.resolve_rising_sign_index_from_trait_ids = (
                lambda trait_ids: 10 if tuple(trait_ids) == (101,) else 4
            )

            loot = loot_actions.CosmicEngineRefreshRisingChemistryLoot()
            loot.apply_to_resolver(object())

            summary = loot_actions.get_last_rising_chemistry_refresh_summary()

            self.assertEqual("write_both", summary.get("pair_memory_write", {}).get("reason"))
            self.assertEqual([830000000000009601], summary.get("written_pair_memory_relbit_ids"))
            self.assertFalse(summary.get("pair_memory_write_summary", {}).get("ok"))
            self.assertNotEqual(
                len(summary.get("pair_memory_write_summary", {}).get("requested_relbit_ids", [])),
                len(summary.get("pair_memory_write_summary", {}).get("written_relbit_ids", [])),
            )
        finally:
            loot_actions._resolve_actor_sim_info = original_resolve_actor
            loot_actions._resolve_participant_sim_info = original_resolve_participant
            loot_actions._resolve_relationship_score_summary = original_relationship_summary
            loot_actions._collect_trait_ids_and_markers = original_collect_traits
            loot_actions._sync_actor_rising_chemistry_buffs = original_sync_rising
            loot_actions._sync_actor_sun_chemistry_overlay_buffs = original_sync_sun
            loot_actions._resolve_active_sun_chemistry_tier_name = original_resolve_active_sun_tier
            loot_actions._chart_payload_for_sim = original_chart_payload_for_sim
            rising_chemistry.build_refresh_summary = original_build_refresh_summary
            rising_chemistry.build_actor_rising_chemistry_buff_plan = original_build_actor_plan
            rising_chemistry.should_apply_first_contact_rising_pass = original_should_apply_rising
            sun_chemistry.build_sun_overlay_buff_plan = original_build_sun_plan
            sun_chemistry.should_apply_first_contact_sun_pass = original_should_apply_sun
            ts4_runtime_install.load_chemistry_profile = original_load_profile
            houses_notification_bridge.resolve_rising_sign_index_from_trait_ids = original_resolve_rising


if __name__ == "__main__":
    unittest.main()
