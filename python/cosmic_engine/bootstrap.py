"""Optional bootstrap entry for script-mod runtime registration."""

import json
from typing import Callable

from .astrology_skill_gate import simstrology_skill_debug_payload
from .crystal_resonance import debug_crystal_resonance_for_sim, sync_crystal_resonance
from .first_load_chooser import (
    maybe_show_first_load_chooser,
    repair_childhood_teen_handoff,
    reset_first_load_chooser_state,
)
from .runtime_hooks import debug_dump_state_json, dispatch_household_onboard
from .natal_snapshot_markers import (
    mark_zone_captured_unflagged_as_legacy,
    reset_natal_snapshot_for_sim_info,
    reset_zone_legacy_natal_snapshots,
    seed_active_household_preteen_natal_snapshots,
    sync_zone_natal_snapshots,
)
from .loot_actions import (
    _current_sim_absolute_ticks,
    build_transit_pretty_payload,
    clear_simstrology_state_from_non_humans,
    debug_trait_scan_for_sim_info,
    get_last_natal_onboard_summary,
)
from .moon_return_markers import sync_zone_moon_return_markers
from .mode_lock import (
    clear_mode_lock,
    get_mode_lock,
    is_cosmic_mode_active,
    mode_status_payload,
    set_mode_lock,
    sync_mode_lock_traits,
)
from .planet_house_markers import sync_zone_planet_house_markers
from .retrograde_markers import (
    debug_retrograde_payload_for_sim,
    ensure_zone_retrograde_consequences,
    sync_zone_retrograde_markers,
)
from .retrograde_notification_bridge import (
    get_last_notification_routing_summary,
    process_pending_retrograde_notifications,
)
from .transit_service import get_global_transit_service
from .ts4_runtime_install import (
    force_runtime_install_now,
    get_last_retrograde_runtime_summary,
    get_last_startup_retro_catchup_summary,
    get_persistence_backend,
    get_persistence_debug_payload,
    get_runtime_status_payload,
    get_season_debug_payload,
    install_runtime_hooks,
    persist_now,
)
from .solar_return_markers import sync_zone_solar_return_markers
from .house_ingress_notifications import (
    get_last_house_ingress_summary,
    process_active_sim_house_ingress_notifications,
)


def _noop(*_args, **_kwargs) -> None:
    return None


def _ensure_runtime_ready_for_debug() -> bool:
    try:
        payload = get_runtime_status_payload()
    except Exception:
        payload = {}
    if bool((payload or {}).get("installed")):
        return True
    try:
        return bool(install_runtime_hooks())
    except Exception:
        return False


def register_debug_commands() -> Callable[..., None]:
    """Register lightweight debug commands when Sims 4 command API is available."""
    try:
        import sims4.commands  # type: ignore
    except Exception:
        return _noop

    def _get_active_sim_info_for_debug():
        try:
            import services  # type: ignore
        except Exception:
            return None
        try:
            client_manager = services.client_manager()
        except Exception:
            client_manager = None
        if client_manager is None:
            return None
        get_first_client = getattr(client_manager, "get_first_client", None)
        client = None
        if callable(get_first_client):
            try:
                client = get_first_client()
            except Exception:
                client = None
        if client is None:
            return None
        sim_info = getattr(client, "active_sim_info", None)
        if sim_info is not None:
            return sim_info
        active_sim = getattr(client, "active_sim", None)
        if active_sim is not None:
            return getattr(active_sim, "sim_info", None) or active_sim
        return None

    def _get_sim_info_by_id(sim_id):
        if not sim_id:
            return None
        try:
            import services  # type: ignore
        except Exception:
            return None
        try:
            manager = services.sim_info_manager()
        except Exception:
            manager = None
        if manager is None:
            return None
        try:
            return manager.get(int(sim_id))
        except Exception:
            return None

    def _get_household_id_for_sim_info(sim_info):
        if sim_info is None:
            return None
        try:
            value = getattr(sim_info, "household_id", None)
            if value is not None:
                return int(value)
        except Exception:
            pass
        try:
            household = getattr(sim_info, "household", None)
        except Exception:
            household = None
        try:
            hid = getattr(household, "id", None) if household is not None else None
            return int(hid) if hid is not None else None
        except Exception:
            return None

    @sims4.commands.Command("ce.transit.dump", command_type=sims4.commands.CommandType.Live)
    def _cmd_dump(_connection=None):
        sims4.commands.output(debug_dump_state_json(), _connection)
        return True

    @sims4.commands.Command("ce.transit.advance", command_type=sims4.commands.CommandType.Live)
    def _cmd_advance(days: int = 0, segments: int = 0, _connection=None):
        moved = get_global_transit_service().advance(
            elapsed_days=int(days),
            elapsed_segments=int(segments),
        )
        try:
            marker_summary = sync_zone_planet_house_markers()
        except Exception:
            marker_summary = None
        try:
            retro_marker_summary = sync_zone_retrograde_markers()
        except Exception:
            retro_marker_summary = None
        try:
            natal_summary = sync_zone_natal_snapshots()
        except Exception:
            natal_summary = None
        try:
            moon_return_summary = sync_zone_moon_return_markers()
        except Exception:
            moon_return_summary = None
        try:
            solar_return_summary = sync_zone_solar_return_markers()
        except Exception:
            solar_return_summary = None
        sims4.commands.output(str(moved), _connection)
        if marker_summary is not None:
            sims4.commands.output(
                "marker_sync={0}".format(marker_summary),
                _connection,
            )
        if retro_marker_summary is not None:
            sims4.commands.output(
                "retro_marker_sync={0}".format(retro_marker_summary),
                _connection,
            )
        if natal_summary is not None:
            sims4.commands.output(
                "natal_snapshot_sync={0}".format(natal_summary),
                _connection,
            )
        if moon_return_summary is not None:
            sims4.commands.output(
                "moon_return_sync={0}".format(moon_return_summary),
                _connection,
            )
        if solar_return_summary is not None:
            sims4.commands.output(
                "solar_return_sync={0}".format(solar_return_summary),
                _connection,
            )
        return True

    @sims4.commands.Command("ce.transit.pretty", command_type=sims4.commands.CommandType.Live)
    def _cmd_pretty(_connection=None):
        payload = build_transit_pretty_payload()
        sims4.commands.output(str(payload.get("title") or "Cosmic Engine Transits"), _connection)
        for line in payload.get("lines", ()):
            sims4.commands.output(str(line), _connection)
        return bool(payload.get("ok"))

    @sims4.commands.Command(
        "ce.transit.reseed_mars_plus",
        command_type=sims4.commands.CommandType.Live,
    )
    def _cmd_reseed_mars_plus(seed: int = 0, _connection=None):
        service = get_global_transit_service()
        applied_seed = int(seed) if int(seed or 0) != 0 else None
        summary = service.reseed_mars_plus(seed=applied_seed)
        chart_refresh = service.clear_dynamic_chart_record_payloads()
        natal_summary = sync_zone_natal_snapshots()
        persisted = persist_now(reason="debug.ce_transit_reseed_mars_plus")
        sims4.commands.output("Cosmic Engine Transit Mars-Plus Reseed", _connection)
        sims4.commands.output(
            json.dumps(
                {
                    "persisted": bool(persisted),
                    "summary": summary,
                    "chart_refresh": chart_refresh,
                    "natal_snapshot_sync": natal_summary,
                },
                sort_keys=True,
            ),
            _connection,
        )
        return bool(persisted)

    @sims4.commands.Command("ce.season.debug", command_type=sims4.commands.CommandType.Live)
    def _cmd_season_debug(_connection=None):
        payload = get_season_debug_payload()
        sims4.commands.output("Cosmic Engine Season Debug", _connection)
        for key in (
            "ok",
            "season_value_repr",
            "season_type",
            "segment_value_repr",
            "segment_type",
            "service_season_and_segments_repr",
            "service_season_and_segments_with_now_repr",
            "season_content_repr",
            "season_content_type",
            "content_get_segment_repr",
            "content_get_segment_with_now_repr",
            "pair",
            "pair_index",
            "fallback_season_idx",
            "fallback_segment_idx",
            "service_segment_names",
            "content_segment_names",
            "error",
            "exception",
        ):
            if key in payload:
                sims4.commands.output(
                    "{0}: {1}".format(key, payload.get(key)),
                    _connection,
                )
        return bool(payload.get("ok"))

    @sims4.commands.Command("ce.skill.debug", command_type=sims4.commands.CommandType.Live)
    def _cmd_skill_debug(_connection=None):
        payload = simstrology_skill_debug_payload(_get_active_sim_info_for_debug())
        sims4.commands.output("Cosmic Engine Simstrology Skill Debug", _connection)
        for key in ("ok", "sim_name", "sim_id", "skill_stat_id", "resolved_level", "tuning_resolved"):
            sims4.commands.output("{0}: {1}".format(key, payload.get(key)), _connection)
        tracker_rows = payload.get("tracker_results", [])
        if isinstance(tracker_rows, list):
            for row in tracker_rows:
                sims4.commands.output("tracker: {0}".format(row), _connection)
        return bool(payload.get("ok"))

    @sims4.commands.Command("ce.markers.sync", command_type=sims4.commands.CommandType.Live)
    def _cmd_markers_sync(refresh: int = 0, _connection=None):
        summary = sync_zone_planet_house_markers(refresh_marker_cache=bool(int(refresh)))
        sims4.commands.output("Cosmic Engine Marker Sync", _connection)
        for key in (
            "sims_seen",
            "sims_with_house_map",
            "sims_changed",
            "traits_added",
            "traits_removed",
            "reward_traits_added",
            "reward_traits_removed",
            "reward_traits_skipped_skill_gate",
            "buffs_added",
            "buffs_removed",
            "buffs_skipped_skill_gate",
            "notice_events",
            "notices_shown",
            "notice_skipped_initial_marker_seed",
            "notice_skipped_skill_gate",
            "transit_awareness_required_level",
            "available_marker_defs",
            "available_reward_marker_defs",
            "available_reward_buff_defs",
        ):
            sims4.commands.output(
                "{0}: {1}".format(key, summary.get(key)),
                _connection,
            )
        return True

    @sims4.commands.Command("ce.natal.sync", command_type=sims4.commands.CommandType.Live)
    def _cmd_natal_sync(
        refresh: int = 0,
        legacy_seed_uncaptured: int = 0,
        seed_uncaptured_teen_plus: int = 0,
        _connection=None,
    ):
        summary = sync_zone_natal_snapshots(
            refresh_marker_cache=bool(int(refresh)),
            legacy_seed_uncaptured=bool(int(legacy_seed_uncaptured)),
            seed_uncaptured_teen_plus=bool(int(seed_uncaptured_teen_plus)),
        )
        sims4.commands.output("Cosmic Engine Natal Snapshot Sync", _connection)
        for key in (
            "sims_seen",
            "teen_plus_seen",
            "eligible_without_capture",
            "sims_captured",
            "sims_signs_backfilled",
            "sims_legacy_seeded",
            "traits_added",
            "traits_removed",
            "available_marker_defs",
            "available_sun_sign_defs",
            "available_moon_sign_defs",
            "available_visible_sun_reward_defs",
            "available_visible_moon_reward_defs",
            "available_visible_chart_ruler_reward_defs",
            "available_personality_rising_defs",
            "available_rising_marker_defs",
            "chart_ruler_visible_traits_added",
            "chart_ruler_visible_traits_removed",
            "rising_marker_added_preteen",
            "rising_marker_removed_preteen",
            "rising_promoted_to_personality",
            "rising_promotion_skipped_teen_lane",
            "rising_promotion_deferred_teen",
            "rising_promotion_deferred_adult",
            "rising_marker_removed_teen",
            "rising_marker_removed_adult",
            "rising_lane_preteen_seen",
            "rising_lane_teen_seen",
            "rising_lane_adult_seen",
            "rising_lane_unknown_seen",
            "has_capture_flag_def",
            "has_legacy_flag_def",
            "legacy_seed_mode",
            "seed_uncaptured_teen_plus",
        ):
            sims4.commands.output(
                "{0}: {1}".format(key, summary.get(key)),
                _connection,
            )
        skipped_teen_lane = int(summary.get("rising_promotion_skipped_teen_lane", 0) or 0)
        if skipped_teen_lane > 0:
            sims4.commands.output(
                "note: teen rising now uses the gameplay-visible lane; legacy personality promotion may still be skipped",
                _connection,
            )
        deferred = int(summary.get("rising_promotion_deferred_teen", 0) or 0)
        if deferred > 0:
            sims4.commands.output(
                "note: a legacy hidden rising marker was kept on teen because personality promotion failed",
                _connection,
            )
        return True

    @sims4.commands.Command("ce.natal.seed_preteen_household", command_type=sims4.commands.CommandType.Live)
    def _cmd_natal_seed_preteen_household(refresh: int = 0, _connection=None):
        active_sim_info = _get_active_sim_info_for_debug()
        household_id = _get_household_id_for_sim_info(active_sim_info)
        summary = seed_active_household_preteen_natal_snapshots(
            active_household_id=household_id,
            refresh_marker_cache=bool(int(refresh)),
        )
        sims4.commands.output("Cosmic Engine Natal Pre-Teen Household Seed", _connection)
        for key in (
            "active_household_id",
            "has_active_household_id",
            "sims_seen",
            "household_sims_seen",
            "preteen_seen",
            "eligible_without_capture",
            "sims_seeded",
            "sims_changed",
            "skipped_no_trait_tracker",
            "skipped_already_captured",
            "skipped_missing_house_map",
            "traits_added",
            "traits_removed",
            "available_personality_rising_defs",
            "available_rising_marker_defs",
            "available_visible_sun_reward_defs",
            "available_visible_moon_reward_defs",
            "available_visible_chart_ruler_reward_defs",
            "chart_ruler_visible_traits_added",
            "chart_ruler_visible_traits_removed",
            "has_capture_flag_def",
        ):
            sims4.commands.output(
                "{0}: {1}".format(key, summary.get(key)),
                _connection,
            )
        return True

    @sims4.commands.Command("ce.natal.onboard_played_household", command_type=sims4.commands.CommandType.Live)
    def _cmd_natal_onboard_played_household(refresh: int = 0, _connection=None):
        active_sim_info = _get_active_sim_info_for_debug()
        household_id = _get_household_id_for_sim_info(active_sim_info)
        summary = dispatch_household_onboard(
            household_id,
            refresh_marker_cache=bool(int(refresh)),
        )
        sims4.commands.output("Cosmic Engine Natal Household Onboarding", _connection)
        for key in (
            "active_household_id",
            "has_active_household_id",
            "preteen_sims_seeded",
            "teen_sims_seeded",
            "total_sims_seeded",
            "total_traits_added",
            "total_traits_removed",
        ):
            sims4.commands.output(
                "{0}: {1}".format(key, summary.get(key)),
                _connection,
            )
        preteen_summary = summary.get("preteen_summary")
        if isinstance(preteen_summary, dict):
            sims4.commands.output("preteen_summary={0}".format(preteen_summary), _connection)
        teen_summary = summary.get("teen_summary")
        if isinstance(teen_summary, dict):
            sims4.commands.output("teen_summary={0}".format(teen_summary), _connection)
        return True

    @sims4.commands.Command("ce.natal.reset_active", command_type=sims4.commands.CommandType.Live)
    def _cmd_natal_reset_active(refresh: int = 0, _connection=None):
        sim_info = _get_active_sim_info_for_debug()
        summary = reset_natal_snapshot_for_sim_info(
            sim_info,
            refresh_marker_cache=bool(int(refresh)),
        )
        sims4.commands.output("Cosmic Engine Natal Reset Active", _connection)
        for key in (
            "ok",
            "sim_name",
            "sim_id",
            "changed",
            "traits_removed",
            "had_capture_flag",
            "had_legacy_flag",
            "had_any_natal_traits",
            "resettable_trait_defs_known",
        ):
            sims4.commands.output(
                "{0}: {1}".format(key, summary.get(key)),
                _connection,
            )
        if summary.get("error") is not None:
            sims4.commands.output("error: {0}".format(summary.get("error")), _connection)
        return bool(summary.get("ok"))

    @sims4.commands.Command("ce.natal.reset_legacy", command_type=sims4.commands.CommandType.Live)
    def _cmd_natal_reset_legacy(
        reseed_now: int = 0,
        refresh: int = 0,
        _connection=None,
    ):
        summary = reset_zone_legacy_natal_snapshots(
            refresh_marker_cache=bool(int(refresh)),
            reseed_now=bool(int(reseed_now)),
        )
        sims4.commands.output("Cosmic Engine Natal Legacy Reset", _connection)
        for key in (
            "sims_seen",
            "legacy_sims_seen",
            "sims_changed",
            "traits_removed",
            "resettable_trait_defs_known",
            "has_legacy_flag_def",
            "reseed_now",
        ):
            sims4.commands.output(
                "{0}: {1}".format(key, summary.get(key)),
                _connection,
            )
        if summary.get("reseed_summary") is not None:
            sims4.commands.output(
                "reseed_summary={0}".format(summary.get("reseed_summary")),
                _connection,
            )
        return True

    @sims4.commands.Command("ce.natal.mark_captured_legacy", command_type=sims4.commands.CommandType.Live)
    def _cmd_natal_mark_captured_legacy(
        reseed_now: int = 0,
        refresh: int = 0,
        _connection=None,
    ):
        summary = mark_zone_captured_unflagged_as_legacy(
            refresh_marker_cache=bool(int(refresh)),
            reseed_now=bool(int(reseed_now)),
        )
        sims4.commands.output("Cosmic Engine Natal Legacy Backfill", _connection)
        for key in (
            "sims_seen",
            "sims_with_capture_flag",
            "sims_already_legacy",
            "sims_marked_legacy",
            "traits_added",
            "has_capture_flag_def",
            "has_legacy_flag_def",
            "reseed_now",
        ):
            sims4.commands.output(
                "{0}: {1}".format(key, summary.get(key)),
                _connection,
            )
        if summary.get("reseed_summary") is not None:
            sims4.commands.output(
                "reseed_summary={0}".format(summary.get("reseed_summary")),
                _connection,
            )
        return True

    @sims4.commands.Command("ce.natal.debug_traits", command_type=sims4.commands.CommandType.Live)
    def _cmd_natal_debug_traits(
        max_matches: int = 40,
        filter_text: str = "PlumAntics_CosmicEngineNatal_",
        _connection=None,
    ):
        sim_info = _get_active_sim_info_for_debug()
        payload = debug_trait_scan_for_sim_info(
            sim_info,
            contains=str(filter_text or "PlumAntics_CosmicEngineNatal_"),
            max_matches=max(1, min(int(max_matches), 200)),
        )
        sims4.commands.output("Cosmic Engine Natal Trait Debug", _connection)
        for key in (
            "ok",
            "sim_name",
            "sim_id",
            "trait_tracker_type",
            "merged_trait_count",
            "merged_trait_ids_count",
            "natal_marker_trait_ids_count",
        ):
            sims4.commands.output(
                "{0}: {1}".format(key, payload.get(key)),
                _connection,
            )

        source_counts = payload.get("source_counts", [])
        if isinstance(source_counts, list):
            sims4.commands.output("source_counts:", _connection)
            for row in source_counts:
                sims4.commands.output("  {0}".format(row), _connection)

        contains_matches = payload.get("contains_matches", [])
        legacy_matches = payload.get("legacy_flag_matches", [])
        sims4.commands.output(
            "contains_matches_count: {0}".format(
                len(contains_matches) if isinstance(contains_matches, list) else 0
            ),
            _connection,
        )
        if isinstance(contains_matches, list):
            for row in contains_matches:
                sims4.commands.output("  match: {0}".format(row), _connection)

        sims4.commands.output(
            "legacy_flag_matches_count: {0}".format(
                len(legacy_matches) if isinstance(legacy_matches, list) else 0
            ),
            _connection,
        )
        if isinstance(legacy_matches, list):
            for row in legacy_matches:
                sims4.commands.output("  legacy: {0}".format(row), _connection)
        return bool(payload.get("ok"))

    @sims4.commands.Command("ce.natal.chart_record", command_type=sims4.commands.CommandType.Live)
    def _cmd_natal_chart_record(_connection=None):
        sim_info = _get_active_sim_info_for_debug()
        if sim_info is None:
            sims4.commands.output("No active Sim available.", _connection)
            return False

        sim_id = getattr(sim_info, "sim_id", None)
        if sim_id is None:
            sims4.commands.output("Active Sim has no sim_id.", _connection)
            return False

        service = get_global_transit_service()
        payload = service.get_chart_record_payload(int(sim_id))
        if payload is None:
            sims4.commands.output(
                "No chart record payload found for sim_id={0}.".format(sim_id),
                _connection,
            )
            return False

        sims4.commands.output(
            json.dumps(payload, sort_keys=True, indent=2),
            _connection,
        )
        return True

    @sims4.commands.Command("ce.crystal.debug", command_type=sims4.commands.CommandType.Live)
    def _cmd_crystal_debug(_connection=None):
        sim_info = _get_active_sim_info_for_debug()
        if sim_info is None:
            sims4.commands.output("No active Sim available.", _connection)
            return False

        now_ticks = _current_sim_absolute_ticks()
        payload = debug_crystal_resonance_for_sim(
            sim_info,
            now_ticks=int(now_ticks or 0),
        )
        sims4.commands.output(
            json.dumps(payload, sort_keys=True, indent=2),
            _connection,
        )
        return True

    @sims4.commands.Command("ce.crystal.sync_active", command_type=sims4.commands.CommandType.Live)
    def _cmd_crystal_sync_active(_connection=None):
        sim_info = _get_active_sim_info_for_debug()
        if sim_info is None:
            sims4.commands.output("No active Sim available.", _connection)
            return False

        now_ticks = _current_sim_absolute_ticks()
        summary = sync_crystal_resonance(
            (sim_info,),
            now_ticks=int(now_ticks or 0),
        )
        sims4.commands.output(
            json.dumps(summary, sort_keys=True, indent=2),
            _connection,
        )
        return True

    @sims4.commands.Command("ce.moonreturn.sync", command_type=sims4.commands.CommandType.Live)
    def _cmd_moonreturn_sync(refresh: int = 0, _connection=None):
        summary = sync_zone_moon_return_markers(refresh_marker_cache=bool(int(refresh)))
        sims4.commands.output("Cosmic Engine Moon Return Sync", _connection)
        for key in (
            "sims_seen",
            "sims_with_natal_moon",
            "sims_changed",
            "traits_added",
            "traits_removed",
            "available_marker_defs",
        ):
            sims4.commands.output(
                "{0}: {1}".format(key, summary.get(key)),
                _connection,
            )
        return True

    @sims4.commands.Command("ce.solarreturn.sync", command_type=sims4.commands.CommandType.Live)
    def _cmd_solarreturn_sync(refresh: int = 0, _connection=None):
        summary = sync_zone_solar_return_markers(refresh_marker_cache=bool(int(refresh)))
        sims4.commands.output("Cosmic Engine Solar Return Sync", _connection)
        for key in (
            "sims_seen",
            "sims_with_natal_sun",
            "sims_changed",
            "traits_added",
            "traits_removed",
            "available_marker_defs",
        ):
            sims4.commands.output(
                "{0}: {1}".format(key, summary.get(key)),
                _connection,
            )
        return True

    @sims4.commands.Command("ce.househits.sync", command_type=sims4.commands.CommandType.Live)
    def _cmd_househits_sync(
        show_notifications: int = 1,
        refresh_baseline: int = 0,
        max_notices: int = 5,
        _connection=None,
    ):
        summary = process_active_sim_house_ingress_notifications(
            show_notifications=bool(int(show_notifications)),
            refresh_baseline=bool(int(refresh_baseline)),
            max_notices=int(max_notices),
        )
        sims4.commands.output("Cosmic Engine House Ingress Notices", _connection)
        sims4.commands.output(str(summary), _connection)
        return True

    @sims4.commands.Command("ce.househits.status", command_type=sims4.commands.CommandType.Live)
    def _cmd_househits_status(_connection=None):
        sims4.commands.output(str(get_last_house_ingress_summary()), _connection)
        return True

    @sims4.commands.Command("ce.retro.dump", command_type=sims4.commands.CommandType.Live)
    def _cmd_retro_dump(_connection=None):
        _ensure_runtime_ready_for_debug()
        payload = get_global_transit_service().retrograde_debug_payload()
        season_payload = get_season_debug_payload()
        pair = season_payload.get("pair") if isinstance(season_payload, dict) else None
        pair_index = season_payload.get("pair_index") if isinstance(season_payload, dict) else None
        sims4.commands.output("Cosmic Engine Retrogrades", _connection)
        sims4.commands.output(
            "sim_days_per_year_hint: {0}".format(payload.get("sim_days_per_year_hint")),
            _connection,
        )
        sims4.commands.output(
            "last_total_days_seen: {0}".format(payload.get("last_total_days_seen")),
            _connection,
        )
        sims4.commands.output(
            "last_total_day_progress_seen: {0}".format(payload.get("last_total_day_progress_seen")),
            _connection,
        )
        sims4.commands.output(
            "last_total_segments_seen: {0}".format(payload.get("last_total_segments_seen")),
            _connection,
        )
        sims4.commands.output(
            "season_pair: {0} pair_index={1}".format(pair, pair_index),
            _connection,
        )
        sims4.commands.output(
            "pending_event_count: {0}".format(payload.get("pending_event_count")),
            _connection,
        )
        sims4.commands.output(
            "last_changes: {0}".format(payload.get("last_changes")),
            _connection,
        )
        bodies = payload.get("bodies", {})
        if isinstance(bodies, dict):
            for body in ("Mercury", "Venus", "Mars", "Jupiter", "Saturn"):
                info = bodies.get(body, {})
                if not isinstance(info, dict):
                    continue
                sims4.commands.output(
                    "{0}: active={1} unit={2} remaining={3} interval={4} duration={5}".format(
                        body,
                        info.get("active"),
                        info.get("unit"),
                        info.get("remaining"),
                        info.get("start_interval"),
                        info.get("duration"),
                    ),
                    _connection,
                )
        return True

    @sims4.commands.Command("ce.retro.active_sim", command_type=sims4.commands.CommandType.Live)
    def _cmd_retro_active_sim(_connection=None):
        sim_info = _get_active_sim_info_for_debug()
        if sim_info is None:
            sims4.commands.output("No active Sim available.", _connection)
            return False
        sims4.commands.output(
            json.dumps(debug_retrograde_payload_for_sim(sim_info), sort_keys=True, indent=2),
            _connection,
        )
        return True

    @sims4.commands.Command("ce.runtime.status", command_type=sims4.commands.CommandType.Live)
    def _cmd_runtime_status(_connection=None):
        _ensure_runtime_ready_for_debug()
        sims4.commands.output(
            json.dumps(get_runtime_status_payload(), sort_keys=True, indent=2),
            _connection,
        )
        return True

    @sims4.commands.Command("ce.runtime.install", command_type=sims4.commands.CommandType.Live)
    def _cmd_runtime_install(_connection=None):
        result = force_runtime_install_now()
        sims4.commands.output(
            "ce.runtime.install -> {0}".format(result),
            _connection,
        )
        sims4.commands.output(
            json.dumps(get_runtime_status_payload(), sort_keys=True, indent=2),
            _connection,
        )
        return True

    @sims4.commands.Command("ce.retro.events", command_type=sims4.commands.CommandType.Live)
    def _cmd_retro_events(limit: int = 20, consume: int = 0, _connection=None):
        service = get_global_transit_service()
        if int(consume):
            events = service.consume_pending_retrograde_events(limit=int(limit))
        else:
            events = service.peek_pending_retrograde_events(limit=int(limit))
        sims4.commands.output(
            "Cosmic Engine Retrograde Events ({0})".format(
                "consume" if int(consume) else "peek"
            ),
            _connection,
        )
        sims4.commands.output(str(events), _connection)
        return True

    @sims4.commands.Command("ce.retro.sync", command_type=sims4.commands.CommandType.Live)
    def _cmd_retro_sync(refresh: int = 0, _connection=None):
        marker_summary = sync_zone_retrograde_markers(
            refresh_marker_cache=bool(int(refresh)),
            manage_consequences=False,
        )
        consequence_summary = ensure_zone_retrograde_consequences(reason="debug.ce_retro_sync")
        sims4.commands.output("Cosmic Engine Retrograde Marker Sync", _connection)
        for key in (
            "sims_seen",
            "sims_changed",
            "traits_added",
            "traits_removed",
            "traits_rehydrated",
            "traits_rehydrate_queued",
            "available_marker_defs",
        ):
            sims4.commands.output(
                "marker.{0}: {1}".format(key, marker_summary.get(key)),
                _connection,
            )
        for key in (
            "sims_seen",
            "sims_changed",
            "buffs_added",
            "buffs_removed",
            "intense_buffs_added",
            "intense_buffs_removed",
            "dispatch_failures",
            "available_retrograde_buffs",
        ):
            sims4.commands.output(
                "consequence.{0}: {1}".format(key, consequence_summary.get(key)),
                _connection,
            )
        return True

    @sims4.commands.Command("ce.retro.notify.route", command_type=sims4.commands.CommandType.Live)
    def _cmd_retro_notify_route(
        max_events: int = 20,
        consume_unmapped: int = 0,
        all_sources: int = 0,
        _connection=None,
    ):
        allowed_sources = None if int(all_sources) else ("clock_snapshot",)
        summary = process_pending_retrograde_notifications(
            allowed_sources=allowed_sources,
            consume_unmapped=bool(int(consume_unmapped)),
            max_events=int(max_events),
        )
        sims4.commands.output("Cosmic Engine Retrograde Notification Routing", _connection)
        sims4.commands.output(str(summary), _connection)
        return True

    @sims4.commands.Command("ce.retro.notify.status", command_type=sims4.commands.CommandType.Live)
    def _cmd_retro_notify_status(_connection=None):
        sims4.commands.output(
            str(get_last_notification_routing_summary()),
            _connection,
        )
        return True

    @sims4.commands.Command("ce.retro.runtime.status", command_type=sims4.commands.CommandType.Live)
    def _cmd_retro_runtime_status(_connection=None):
        summary = get_last_retrograde_runtime_summary()
        startup_summary = get_last_startup_retro_catchup_summary()
        sims4.commands.output("Cosmic Engine Retrograde Runtime Summary", _connection)
        if not isinstance(summary, dict):
            sims4.commands.output("No runtime retrograde summary recorded yet.", _connection)
        else:
            sims4.commands.output(
                "reason: {0}".format(summary.get("reason")),
                _connection,
            )
            sims4.commands.output(
                "skip_reason: {0}".format(summary.get("skip_reason")),
                _connection,
            )
            sims4.commands.output(
                "active_mode: {0}".format(summary.get("active_mode")),
                _connection,
            )
            sims4.commands.output(
                "dispatch_failed: {0}".format(bool(summary.get("dispatch_failed"))),
                _connection,
            )
            sims4.commands.output(
                "phase: {0}".format(summary.get("phase")),
                _connection,
            )
            sims4.commands.output(
                "attempt: {0}".format(summary.get("attempt")),
                _connection,
            )
            sims4.commands.output(
                "deferred_reason: {0}".format(summary.get("deferred_reason")),
                _connection,
            )
            sims4.commands.output(
                "total_days_elapsed: {0}".format(summary.get("total_days_elapsed")),
                _connection,
            )
            sims4.commands.output(
                "total_segments_elapsed: {0}".format(summary.get("total_segments_elapsed")),
                _connection,
            )
            sims4.commands.output(
                "instanced_sim_count: {0}".format(summary.get("instanced_sim_count")),
                _connection,
            )
            sims4.commands.output(
                "ready_sim_count: {0}".format(summary.get("ready_sim_count")),
                _connection,
            )
            sims4.commands.output(
                "active_household_sim_count: {0}".format(summary.get("active_household_sim_count")),
                _connection,
            )
            sims4.commands.output(
                "did_direct_dispatch: {0}".format(summary.get("did_direct_dispatch")),
                _connection,
            )
            sims4.commands.output(
                "last_changes: {0}".format(summary.get("last_changes")),
                _connection,
            )
            marker_summary = summary.get("marker_summary") if isinstance(summary.get("marker_summary"), dict) else {}
            consequence_summary = (
                summary.get("consequence_summary")
                if isinstance(summary.get("consequence_summary"), dict)
                else {}
            )
            for key in (
                "sims_seen",
                "sims_changed",
                "traits_added",
                "traits_removed",
                "traits_rehydrated",
                "traits_rehydrate_queued",
                "available_marker_defs",
            ):
                sims4.commands.output(
                    "marker.{0}: {1}".format(key, marker_summary.get(key)),
                    _connection,
                )
            for key in (
                "sims_seen",
                "sims_changed",
                "buffs_added",
                "buffs_removed",
                "intense_buffs_added",
                "intense_buffs_removed",
                "dispatch_failures",
                "available_retrograde_buffs",
            ):
                sims4.commands.output(
                    "consequence.{0}: {1}".format(key, consequence_summary.get(key)),
                    _connection,
                )
            sims4.commands.output(
                "route_notifications: {0}".format(bool(summary.get("route_notifications"))),
                _connection,
            )

        sims4.commands.output("Cosmic Engine Startup Retrograde Catch-Up", _connection)
        if not isinstance(startup_summary, dict):
            sims4.commands.output("No startup catch-up summary recorded yet.", _connection)
            return bool(isinstance(summary, dict))
        for key in (
            "reason",
            "phase",
            "attempt",
            "deferred_reason",
            "total_days_elapsed",
            "total_segments_elapsed",
            "instanced_sim_count",
            "ready_sim_count",
            "active_household_sim_count",
            "did_direct_dispatch",
            "last_changes",
        ):
            sims4.commands.output(
                "startup.{0}: {1}".format(key, startup_summary.get(key)),
                _connection,
            )
        return True

    @sims4.commands.Command("ce.persist.path", command_type=sims4.commands.CommandType.Live)
    def _cmd_persist_path(_connection=None):
        sims4.commands.output(
            "Cosmic Engine backend: {0}".format(get_persistence_backend()),
            _connection,
        )
        sims4.commands.output(
            "Cosmic Engine save carrier: gameplay_data.mod_data",
            _connection,
        )
        sims4.commands.output(
            "Legacy household-description payloads are scrubbed automatically if found.",
            _connection,
        )
        return True

    @sims4.commands.Command("ce.persist.now", command_type=sims4.commands.CommandType.Live)
    def _cmd_persist_now(_connection=None):
        ok = persist_now(reason="debug.ce_persist_now")
        sims4.commands.output(
            "Cosmic Engine manual persist via {0}: {1}".format(
                get_persistence_backend(),
                bool(ok),
            ),
            _connection,
        )
        return bool(ok)

    @sims4.commands.Command("ce.persist.inspect", command_type=sims4.commands.CommandType.Live)
    def _cmd_persist_inspect(_connection=None):
        sims4.commands.output(
            json.dumps(get_persistence_debug_payload(), sort_keys=True, indent=2),
            _connection,
        )
        return True

    @sims4.commands.Command("ce.persist.backend", command_type=sims4.commands.CommandType.Live)
    def _cmd_persist_backend(mode: str = "", _connection=None):
        sims4.commands.output(
            "Cosmic Engine backend is fixed to: {0}".format(get_persistence_backend()),
            _connection,
        )
        sims4.commands.output(
            "Runtime backend switching has been retired; legacy payload cleanup still runs automatically.",
            _connection,
        )
        return True

    @sims4.commands.Command("ce.natal.onboard.status", command_type=sims4.commands.CommandType.Live)
    def _cmd_natal_onboard_status(_connection=None):
        sims4.commands.output(
            json.dumps(get_last_natal_onboard_summary(), sort_keys=True, indent=2),
            _connection,
        )
        return True

    @sims4.commands.Command("ce.mode.status", command_type=sims4.commands.CommandType.Live)
    def _cmd_mode_status(_connection=None):
        sims4.commands.output(
            json.dumps(mode_status_payload("cosmic"), sort_keys=True),
            _connection,
        )
        return True

    @sims4.commands.Command("ce.mode.set", command_type=sims4.commands.CommandType.Live)
    def _cmd_mode_set(mode: str = "cosmic", _connection=None):
        ok = set_mode_lock(mode, source="cosmic.command")
        sync_summary = sync_mode_lock_traits()
        if not ok:
            sims4.commands.output("Invalid Cosmic mode value: {0}".format(mode), _connection)
        payload = mode_status_payload("cosmic")
        payload["sync"] = sync_summary
        sims4.commands.output(
            json.dumps(payload, sort_keys=True),
            _connection,
        )
        return bool(ok)

    @sims4.commands.Command("ce.mode.clear", command_type=sims4.commands.CommandType.Live)
    def _cmd_mode_clear(_connection=None):
        ok = clear_mode_lock(source="cosmic.command")
        payload = mode_status_payload("cosmic")
        payload["sync"] = sync_mode_lock_traits()
        sims4.commands.output(
            json.dumps(payload, sort_keys=True),
            _connection,
        )
        return bool(ok)

    @sims4.commands.Command("ce.childhood.repair", command_type=sims4.commands.CommandType.Live)
    def _cmd_childhood_repair(sim_id: int = 0, _connection=None):
        sim_info = _get_sim_info_by_id(sim_id) if int(sim_id or 0) else _get_active_sim_info_for_debug()
        if sim_info is None:
            sims4.commands.output(
                json.dumps({"ok": False, "reason": "missing_sim"}, sort_keys=True),
                _connection,
            )
            return False
        summary = repair_childhood_teen_handoff(sim_info)
        sims4.commands.output(json.dumps(summary, sort_keys=True), _connection)
        return bool(summary.get("ok"))

    @sims4.commands.Command("ce.nonhuman.cleanup", command_type=sims4.commands.CommandType.Live)
    def _cmd_nonhuman_cleanup(_connection=None):
        summary = clear_simstrology_state_from_non_humans()
        sims4.commands.output(json.dumps(summary, sort_keys=True), _connection)
        return bool(summary.get("non_humans_seen") or summary.get("base_remove_loot_runs"))

    @sims4.commands.Command("ce.chooser.show", command_type=sims4.commands.CommandType.Live)
    def _cmd_chooser_show(reset: int = 1, _connection=None):
        if bool(int(reset)):
            reset_first_load_chooser_state()
        shown = maybe_show_first_load_chooser(force=True)
        sims4.commands.output(
            "Cosmic chooser shown: {0}".format(bool(shown)),
            _connection,
        )
        return bool(shown)

    @sims4.commands.Command("ce.mode.active", command_type=sims4.commands.CommandType.Live)
    def _cmd_mode_active(_connection=None):
        sims4.commands.output(
            "Cosmic mode active: {0} (lock={1})".format(
                bool(is_cosmic_mode_active()),
                get_mode_lock(),
            ),
            _connection,
        )
        return True

    @sims4.commands.Command(
        "ce.houses.last", command_type=sims4.commands.CommandType.Live
    )
    def _cmd_houses_last(sim_id: int = 0, _connection=None):
        payload = get_global_transit_service().get_last_houses_readout_payload(int(sim_id))
        if payload is None:
            sims4.commands.output("No cached houses payload for sim.", _connection)
            return False
        sims4.commands.output(json.dumps(payload, sort_keys=True), _connection)
        return True

    return _cmd_dump
