"""Best-effort Sims 4 runtime hook installer for transit ticking and persistence.

This module is intentionally defensive:
- no hard dependency on specific TS4 internals at import time
- wrappers fail closed (log + continue gameplay)
- persistence writes through save-wide gameplay_data.mod_data, with only
  one-way cleanup remaining for legacy embedded household payloads
"""

import json
import os
import re
import importlib
import time
from typing import Optional

from .chemistry_settings import read_chemistry_profile_id
from .crystal_resonance import sync_crystal_resonance
from .retrograde_visibility_settings import read_retrograde_visibility_profile_id
from .dirty_sync_queue import (
    SCOPE_CRYSTAL_RESONANCE,
    SCOPE_HOUSE_INGRESS,
    SCOPE_MOON_RETURN,
    SCOPE_NATAL_SNAPSHOTS,
    SCOPE_PLANET_HOUSES,
    SCOPE_RETROGRADE_CONSEQUENCES,
    SCOPE_RETROGRADE_MARKERS,
    SCOPE_RISING_BUFFS,
    SCOPE_SOLAR_RETURN,
    SCOPE_VISIBLE_SIGN_BUFFS,
    flush_dirty_scopes,
    mark_scope_dirty,
)
from .persistence_carriers import TransitPersistenceCarriers
from .runtime_hooks import (
    _ASTROCORE_RUNTIME_BRIDGE as _RUNTIME_HOOKS_ASTROCORE_RUNTIME_BRIDGE,
    dispatch_household_onboard,
    on_clock_snapshot,
    on_pre_save,
    on_zone_or_save_load,
)
from .mode_lock import (
    get_mode_lock,
    has_household_outer_planets_refresh_run,
    has_household_legacy_v2_auto_migration_run,
    mark_household_outer_planets_refresh_run,
    mark_household_legacy_v2_auto_migration_run,
)
from .natal_snapshot_markers import (
    inspect_active_household_legacy_v2_candidates,
    process_managed_visible_sign_buffs,
    process_managed_rising_buffs,
    reset_managed_visible_sign_buff_state,
    reset_managed_rising_buff_state,
    sync_zone_natal_snapshots,
)
from .persistence_adapter import TransitPersistenceAdapter
from .moon_return_markers import sync_zone_moon_return_markers
from .outer_planets_activation import is_outer_planets_addon_active
from .planet_house_markers import (
    _iter_instanced_sim_infos,
    sync_active_household_outer_planets_only,
    sync_zone_planet_house_markers,
)
from .retrograde_markers import ensure_zone_retrograde_consequences, sync_zone_retrograde_markers
from .retrograde_notification_bridge import process_pending_retrograde_notifications
from .solar_return_markers import sync_zone_solar_return_markers
from .house_ingress_notifications import process_active_sim_house_ingress_notifications
from .transit_service import get_global_transit_service


_DATE_REPR_RE = re.compile(r"day:(\d+)\s+week:(\d+)", re.IGNORECASE)

_SEASON_NAME_TO_INDEX = {
    "SPRING": 0,
    "SUMMER": 1,
    "FALL": 2,
    "AUTUMN": 2,
    "WINTER": 3,
}

_SEGMENT_NAME_TO_INDEX = {
    "EARLY": 0,
    "PEAK": 1,
    "MID": 1,
    "MIDDLE": 1,
    "LATE": 2,
}

_MARKER_SYNC_TICK_INTERVAL = 120
_AUTO_TICK_ALARM_INTERVAL_SIM_MINUTES = 10
_AUTO_TICK_BOOTSTRAP_REAL_SECONDS = 15
_AUTO_TICK_FALLBACK_REAL_SECONDS = 15
_STARTUP_RETRO_REASSERT_REAL_SECONDS = 5
_STARTUP_RETRO_CATCHUP_MAX_ATTEMPTS = 8
_SERVICES_PROBE_RECONCILE_STALE_SECONDS = 5.0
_SERVICES_PROBE_MIN_CHECK_REAL_SECONDS = 5.0
_SERVICES_PROBE_HOOKS_ENABLED = True
_SOCIAL_COMPLETE_PATCH_TARGETS = (
    (
        "interactions.social.social_super_interaction",
        "SocialSuperInteraction",
        "_trigger_interaction_complete",
    ),
    (
        "interactions.social.social_mixer_interaction",
        "SocialMixerInteraction",
        "_trigger_interaction_complete",
    ),
    (
        "interactions.base.super_interaction",
        "SuperInteraction",
        "_trigger_interaction_complete",
    ),
)

_PERSISTENCE_BACKEND_IN_SAVE = "in_save_mod_data"
_PERSISTENCE_BACKEND = _PERSISTENCE_BACKEND_IN_SAVE
_IN_SAVE_PAYLOAD_PREFIX = "[[PLUMANTICS_CE_TRANSIT:"
_IN_SAVE_PAYLOAD_SUFFIX = ":PLUMANTICS_CE_TRANSIT]]"
_PERSISTENCE_CARRIERS = None
_PERSISTENCE_ADAPTER = None

_RUNTIME_STATE = {
    "installed": False,
    "initialized": False,
    "career_wrapper_patched": False,
    "persistence_hooks_patched": False,
    "social_complete_patched": False,
    "callbacks_registered": False,
    "sim_alarm_started": False,
    "realtime_alarm_started": False,
    "services_probe_patched": False,
    "last_install_result": {},
    "zone_id_initialized": None,
    "segment_total": None,
    "segment_pair": None,
    "warned_day_extract": False,
    "warned_segment_extract": False,
    "warned_runtime_errors": set(),
    "marker_sync_tick_counter": 0,
    "last_instanced_sim_count": None,
    "last_ready_sim_count": None,
    "last_active_household_id": None,
    "last_active_household_sim_count": None,
    "last_legacy_v2_auto_migration_summary": None,
    "last_outer_planets_household_refresh_summary": None,
    "last_sign_compatibility_household_seed_summary": None,
    "sim_days_per_year_hint": None,
    "planet_marker_sync_disabled": False,
    "retrograde_marker_sync_disabled": False,
    "natal_snapshot_sync_disabled": False,
    "moon_return_sync_disabled": False,
    "solar_return_sync_disabled": False,
    "house_ingress_notification_disabled": False,
    "runtime_alarm_tick_seen": False,
    "runtime_tick_inflight": False,
    "last_runtime_tick_real_seconds": None,
    "last_retrograde_runtime_summary": None,
    "last_astrocore_periodic_summary": None,
    "last_startup_retro_catchup_summary": None,
    "startup_retro_catchup_attempts": 0,
    "startup_retro_catchup_completed": False,
    "bootstrap_probe_inflight": False,
    "last_services_probe_check_real_seconds": None,
}

_ASTROCORE_RUNTIME_BRIDGE = _RUNTIME_HOOKS_ASTROCORE_RUNTIME_BRIDGE


def _dispatch_astrocore_load(saved_record=None, fallback_seed=None):
    return _ASTROCORE_RUNTIME_BRIDGE.on_zone_or_save_load(
        saved_record=saved_record,
        fallback_seed=fallback_seed,
    )


def _dispatch_astrocore_periodic(total_days_elapsed, total_segments_elapsed, periodic_trigger):
    return _ASTROCORE_RUNTIME_BRIDGE.on_clock_snapshot(
        total_days_elapsed=int(total_days_elapsed or 0),
        total_segments_elapsed=int(total_segments_elapsed or 0),
        trigger_periodic_repair=bool(periodic_trigger),
    )

_RUNTIME_ALARM_OWNER = None
_RUNTIME_ALARM_HANDLE = None
_RUNTIME_REALTIME_ALARM_HANDLE = None
_RUNTIME_BOOTSTRAP_ALARM_HANDLE = None
_RUNTIME_RETRO_REASSERT_HANDLE = None
_RUNTIME_INSTALL_RETRY_HANDLE = None
_RUNTIME_CALLBACKS_REGISTERED = False
_RUNTIME_ZONE_MANAGER_CALLBACK_REGISTERED = False
_RUNTIME_ZONE_CALLBACK_REGISTERED = False


class _RuntimeAlarmOwner(object):
    pass


def _logger():
    try:
        import sims4.log  # type: ignore

        return sims4.log.Logger("CosmicEngineRuntime", default_owner="PlumAntics")
    except Exception:
        return None


def _log_debug(msg, *args):
    log = _logger()
    if log is None:
        return
    try:
        log.debug(msg, *args)
    except Exception:
        pass


def _log_warn(msg, *args):
    log = _logger()
    if log is None:
        return
    try:
        log.warn(msg, *args)
    except Exception:
        try:
            log.error(msg, *args)
        except Exception:
            pass


def _log_exception(msg, *args):
    log = _logger()
    if log is None:
        return
    try:
        # Avoid Logger.exception because Better Exceptions/Mod Guard can treat
        # handled script issues as hard failures during travel/save transitions.
        log.error(msg, *args)
    except Exception:
        pass


def _log_warn_once(key, msg, *args):
    warned = _RUNTIME_STATE.get("warned_runtime_errors")
    if not isinstance(warned, set):
        warned = set()
        _RUNTIME_STATE["warned_runtime_errors"] = warned
    if key in warned:
        return
    warned.add(key)
    _log_warn(msg, *args)


def _coerce_int(value):
    if value is None:
        return None
    try:
        return int(value)
    except Exception:
        return None


def _call_or_value(obj, attr_name):
    if obj is None:
        return None
    value = getattr(obj, attr_name, None)
    if value is None:
        return None
    try:
        return value() if callable(value) else value
    except TypeError:
        return None
    except Exception:
        return None


def _get_time_service():
    services = _get_services_module()
    if services is None:
        return None
    fn = getattr(services, "time_service", None)
    if fn is None:
        return None
    try:
        return fn()
    except Exception:
        return None


def _get_lunar_cycle_service():
    services = _get_services_module()
    if services is None:
        return None

    for name in ("lunar_cycle_service", "get_lunar_cycle_service"):
        fn = getattr(services, name, None)
        if fn is None:
            continue
        try:
            return fn() if callable(fn) else fn
        except Exception:
            continue
    return None


def _get_sim_now():
    time_service = _get_time_service()
    if time_service is None:
        return None
    return getattr(time_service, "sim_now", None)


def _safe_call_method(owner, method_name, *args):
    if owner is None:
        return None
    fn = getattr(owner, method_name, None)
    if not callable(fn):
        return None
    try:
        return fn(*args)
    except Exception:
        return None


def _candidate_time_args():
    now = _get_sim_now()
    if now is None:
        return [tuple()]

    candidates = [tuple(), (now,)]
    ticks_value = _call_or_value(now, "absolute_ticks")
    if ticks_value is not None:
        candidates.append((ticks_value,))
    absolute_days = _call_or_value(now, "absolute_days")
    if absolute_days is not None:
        candidates.append((absolute_days,))
    return candidates


def _enum_name(value):
    if value is None:
        return None
    name = getattr(value, "name", None)
    if isinstance(name, str) and name:
        return name.upper()
    text = str(value)
    if "." in text:
        tail = text.split(".")[-1]
        if tail:
            return tail.replace(">", "").strip().upper()
    return None


_SEASON_LENGTH_NAME_TO_DAYS = {
    "SHORT": 7.0,
    "MEDIUM": 14.0,
    "LONG": 28.0,
    "VERY_LONG": 56.0,
}


def _season_length_days_from_enumish(value):
    if value is None:
        return None
    name = _enum_name(value)
    if not name:
        return None
    for token, days in _SEASON_LENGTH_NAME_TO_DAYS.items():
        if token in name:
            return float(days)
    return None


def _resolve_sim_days_per_year():
    """Best-effort sim year length in days from the Seasons setting."""
    services = _get_services_module()
    if services is None:
        return None

    season_fn = getattr(services, "season_service", None)
    if not callable(season_fn):
        return None
    try:
        season_service = season_fn()
    except Exception:
        return None
    if season_service is None:
        return None

    season_content = _get_season_content_candidate(season_service)

    numeric_names = (
        "season_length_days",
        "days_per_season",
        "season_duration_days",
        "season_length",
    )
    for owner in (season_service, season_content):
        if owner is None:
            continue
        for name in numeric_names:
            value = _call_or_value(owner, name)
            if value is None:
                continue
            try:
                days_per_season = float(value)
            except Exception:
                days_per_season = None
            if days_per_season is not None and days_per_season > 0:
                if days_per_season <= 4.0:
                    # Avoid interpreting enum ordinal values as day counts.
                    mapped = _season_length_days_from_enumish(value)
                    if mapped is not None:
                        return float(mapped * 4.0)
                return float(days_per_season * 4.0)
            mapped = _season_length_days_from_enumish(value)
            if mapped is not None:
                return float(mapped * 4.0)

    option_names = (
        "season_length_option",
        "length_option",
        "season_duration_option",
    )
    for owner in (season_service, season_content):
        if owner is None:
            continue
        for name in option_names:
            mapped = _season_length_days_from_enumish(_call_or_value(owner, name))
            if mapped is not None:
                return float(mapped * 4.0)

    method_names = (
        "get_season_length",
        "get_season_length_option",
        "get_days_per_season",
    )
    for owner in (season_service, season_content):
        if owner is None:
            continue
        for name in method_names:
            value = _safe_call_method(owner, name)
            if value is None:
                continue
            try:
                days_per_season = float(value)
            except Exception:
                days_per_season = None
            if days_per_season is not None and days_per_season > 0:
                if days_per_season <= 4.0:
                    mapped = _season_length_days_from_enumish(value)
                    if mapped is not None:
                        return float(mapped * 4.0)
                return float(days_per_season * 4.0)
            mapped = _season_length_days_from_enumish(value)
            if mapped is not None:
                return float(mapped * 4.0)

    return None


def _resolve_lunar_cycle_days():
    """Best-effort lunar cycle length in full-cycle days.

    Falls back to None when not discoverable, and caller can use a default.
    """
    svc = _get_lunar_cycle_service()
    if svc is None:
        return None

    direct_names = (
        "lunar_cycle_days",
        "cycle_length_days",
        "days_per_cycle",
        "full_cycle_length_days",
    )
    for name in direct_names:
        value = _call_or_value(svc, name)
        if value is None:
            continue
        try:
            days = float(value)
        except Exception:
            continue
        if days > 0:
            return float(days)

    # Some builds expose a phase length instead of full cycle length.
    phase_length_names = (
        "phase_length_days",
        "days_per_phase",
        "lunar_phase_length_days",
    )
    for name in phase_length_names:
        value = _call_or_value(svc, name)
        if value is None:
            continue
        try:
            phase_days = float(value)
        except Exception:
            continue
        if phase_days > 0:
            return float(phase_days * 8.0)

    # Option-style enum mapping fallback (best effort).
    option_names = (
        "cycle_length_option",
        "lunar_cycle_length_option",
        "cycle_length_setting",
        "lunar_cycle_setting",
    )
    for name in option_names:
        option = _call_or_value(svc, name)
        enum_name = _enum_name(option)
        if not enum_name:
            continue
        # Conservative mapping around the current transit default (12-day full cycle).
        if "SHORT" in enum_name:
            return 6.0
        if "LONG" in enum_name:
            return 24.0
        if "VERY_LONG" in enum_name or "EPIC" in enum_name:
            return 48.0
        if "MEDIUM" in enum_name or "NORMAL" in enum_name or "DEFAULT" in enum_name:
            return 12.0

    # Probe nested settings/tuning objects.
    for nested_name in ("settings", "lunar_cycle_tuning", "cycle_settings"):
        nested = getattr(svc, nested_name, None)
        if nested is None:
            continue
        for attr_name in direct_names:
            value = _call_or_value(nested, attr_name)
            if value is None:
                continue
            try:
                days = float(value)
            except Exception:
                continue
            if days > 0:
                return float(days)

    return None


def _get_services_module():
    try:
        import services  # type: ignore

        return services
    except Exception:
        return None


def _count_instanced_sims():
    services = _get_services_module()
    if services is None:
        return None

    sim_info_manager_fn = getattr(services, "sim_info_manager", None)
    if not callable(sim_info_manager_fn):
        return None
    try:
        sim_info_manager = sim_info_manager_fn()
    except Exception:
        return None
    if sim_info_manager is None:
        return None

    instanced_gen = getattr(sim_info_manager, "instanced_sims_gen", None)
    if callable(instanced_gen):
        try:
            count = 0
            for sim_info in instanced_gen():
                if sim_info is not None:
                    count += 1
            return int(count)
        except Exception:
            pass

    for attr_name in ("_instanced_sims", "instanced_sims"):
        value = getattr(sim_info_manager, attr_name, None)
        if value is None:
            continue
        try:
            return int(len(value))
        except Exception:
            pass

    get_all = getattr(sim_info_manager, "get_all", None)
    if callable(get_all):
        try:
            all_sims = tuple(get_all())
        except Exception:
            all_sims = ()
        count = 0
        for sim_info in all_sims:
            if sim_info is None:
                continue
            is_instanced = getattr(sim_info, "is_instanced", None)
            try:
                if is_instanced is True or (callable(is_instanced) and is_instanced()):
                    count += 1
            except Exception:
                continue
        return int(count)

    return None


def _count_ready_sims():
    if _get_services_module() is None:
        return None
    try:
        return int(sum(1 for _ in _iter_instanced_sim_infos()))
    except Exception:
        return None


def _update_ready_sim_count_state():
    count_trigger = False
    startup_ready_trigger = False

    current_ready_count = _count_ready_sims()
    previous_ready_count = _RUNTIME_STATE.get("last_ready_sim_count")
    current_active_household_id = _get_active_household_id()
    previous_active_household_id = _RUNTIME_STATE.get("last_active_household_id")
    current_active_household_sim_count = int(_count_active_household_sim_infos() or 0)
    previous_active_household_sim_count = _RUNTIME_STATE.get("last_active_household_sim_count")
    if current_ready_count is None:
        return count_trigger, startup_ready_trigger

    current_ready_count = int(current_ready_count)
    household_context_ready = (
        current_active_household_id is not None and current_active_household_sim_count > 0
    )
    if previous_ready_count is None:
        if (
            not _RUNTIME_STATE.get("startup_retro_catchup_completed")
            and current_ready_count > 0
            and household_context_ready
        ):
            startup_ready_trigger = True
        _RUNTIME_STATE["last_ready_sim_count"] = current_ready_count
        _RUNTIME_STATE["last_active_household_id"] = current_active_household_id
        _RUNTIME_STATE["last_active_household_sim_count"] = current_active_household_sim_count
        return count_trigger, startup_ready_trigger

    previous_ready_count = int(previous_ready_count)
    if previous_ready_count != current_ready_count:
        count_trigger = True
        if (
            not _RUNTIME_STATE.get("startup_retro_catchup_completed")
            and previous_ready_count <= 0
            and current_ready_count > 0
            and household_context_ready
        ):
            startup_ready_trigger = True
        _RUNTIME_STATE["last_ready_sim_count"] = current_ready_count

    if previous_active_household_id != current_active_household_id:
        count_trigger = True
        if (
            not _RUNTIME_STATE.get("startup_retro_catchup_completed")
            and current_ready_count > 0
            and household_context_ready
        ):
            startup_ready_trigger = True
        _RUNTIME_STATE["last_active_household_id"] = current_active_household_id

    if previous_active_household_sim_count is None:
        _RUNTIME_STATE["last_active_household_sim_count"] = current_active_household_sim_count
    else:
        previous_active_household_sim_count = int(previous_active_household_sim_count)
        if previous_active_household_sim_count != current_active_household_sim_count:
            count_trigger = True
            if (
                not _RUNTIME_STATE.get("startup_retro_catchup_completed")
                and previous_active_household_sim_count <= 0
                and current_ready_count > 0
                and household_context_ready
            ):
                startup_ready_trigger = True
            _RUNTIME_STATE["last_active_household_sim_count"] = current_active_household_sim_count

    return count_trigger, startup_ready_trigger


def _get_persistence_service():
    services = _get_services_module()
    if services is None:
        return None

    for name in ("get_persistence_service", "persistence_service"):
        fn = getattr(services, name, None)
        if fn is None:
            continue
        try:
            svc = fn()
        except TypeError:
            continue
        except Exception:
            continue
        if svc is not None:
            return svc
    return None


def _resolve_zone_id(zone_obj=None):
    if zone_obj is not None:
        for attr in ("id", "zone_id", "_zone_id"):
            value = _coerce_int(getattr(zone_obj, attr, None))
            if value is not None:
                return value

    services = _get_services_module()
    if services is None:
        return None

    current_zone = getattr(services, "current_zone", None)
    if current_zone is None:
        return None
    try:
        zone = current_zone()
    except Exception:
        return None
    if zone is None:
        return None

    for attr in ("id", "zone_id", "_zone_id"):
        value = _coerce_int(getattr(zone, attr, None))
        if value is not None:
            return value
    return None


def _get_current_zone():
    services = _get_services_module()
    if services is None:
        return None
    current_zone = getattr(services, "current_zone", None)
    if not callable(current_zone):
        return None
    try:
        return current_zone()
    except Exception:
        return None


def _zone_is_running(zone_obj) -> bool:
    if zone_obj is None:
        return False

    for attr_name in ("is_zone_running", "is_running"):
        value = getattr(zone_obj, attr_name, None)
        try:
            if value is True or (callable(value) and bool(value())):
                return True
        except Exception:
            pass

    try:
        import zone as zone_module  # type: ignore
    except Exception:
        zone_module = None
    running_state = getattr(getattr(zone_module, "ZoneState", None), "RUNNING", None)
    if running_state is None:
        return False

    for attr_name in ("zone_state", "_zone_state", "state", "current_state"):
        value = getattr(zone_obj, attr_name, None)
        if value is None:
            continue
        try:
            if value == running_state:
                return True
        except Exception:
            continue
    return False


def _is_current_zone_running():
    return _zone_is_running(_get_current_zone())


def _resolve_save_slot_key():
    psvc = _get_persistence_service()
    if psvc is None:
        return "default"

    candidate_methods = (
        ("get_save_slot_guid", "slot_guid"),
        ("get_save_slot_id", "slot_id"),
        ("get_save_slot_proto_guid", "slot_proto_guid"),
    )
    for name, prefix in candidate_methods:
        fn = getattr(psvc, name, None)
        if fn is None:
            continue
        try:
            value = fn()
        except TypeError:
            continue
        except Exception:
            continue
        slot_key = _normalize_slot_key_value(value, prefix=prefix)
        if slot_key:
            return slot_key

    proto_getter = getattr(psvc, "get_save_slot_proto_buff", None)
    if callable(proto_getter):
        try:
            proto = proto_getter()
        except Exception:
            proto = None
        if proto is not None:
            for attr in ("guid", "slot_id", "slot_name"):
                slot_key = _normalize_slot_key_value(
                    getattr(proto, attr, None), prefix="slot_{0}".format(attr)
                )
                if slot_key:
                    return slot_key

    candidate_attrs = (
        ("save_slot_guid", "slot_guid"),
        ("_save_slot_guid", "slot_guid"),
        ("save_slot_id", "slot_id"),
        ("_save_slot_id", "slot_id"),
        ("slot_id", "slot_id"),
        ("_slot_id", "slot_id"),
    )
    for name, prefix in candidate_attrs:
        slot_key = _normalize_slot_key_value(getattr(psvc, name, None), prefix=prefix)
        if slot_key:
            return slot_key

    return "default"


def _normalize_slot_key_value(value, prefix=None):
    if value is None:
        return None

    direct = _coerce_int(value)
    if direct is not None:
        return "{0}:{1}".format(prefix, direct) if prefix else str(direct)

    for attr in ("guid", "id", "slot_id"):
        nested = _coerce_int(getattr(value, attr, None))
        if nested is not None:
            return "{0}:{1}".format(prefix, nested) if prefix else str(nested)

    try:
        text = str(value)
    except Exception:
        return None
    text = text.strip()
    if not text:
        return None
    numeric_text = _coerce_int(text)
    if numeric_text is not None and numeric_text <= 0:
        return None
    return "{0}:{1}".format(prefix, text) if prefix else text


def _get_persistence_carriers():
    global _PERSISTENCE_CARRIERS
    if _PERSISTENCE_CARRIERS is None:
        _PERSISTENCE_CARRIERS = TransitPersistenceCarriers(
            module_file=__file__,
            get_persistence_service=_get_persistence_service,
            iter_households=_iter_households,
            in_save_payload_prefix=_IN_SAVE_PAYLOAD_PREFIX,
            in_save_payload_suffix=_IN_SAVE_PAYLOAD_SUFFIX,
            log_warn_once=_log_warn_once,
            log_exception=_log_exception,
        )
    return _PERSISTENCE_CARRIERS


def _iter_households():
    services = _get_services_module()
    if services is None:
        return ()
    try:
        household_manager = services.household_manager()
    except Exception:
        household_manager = None
    if household_manager is None:
        return ()
    get_all = getattr(household_manager, "get_all", None)
    if callable(get_all):
        try:
            return tuple(get_all())
        except Exception:
            return ()
    values = getattr(household_manager, "values", None)
    if callable(values):
        try:
            return tuple(values())
        except Exception:
            return ()
    return ()


def _get_active_household():
    services = _get_services_module()
    if services is None:
        return None

    for name in ("active_household", "owning_household_of_active_lot"):
        fn = getattr(services, name, None)
        if fn is None:
            continue
        try:
            household = fn() if callable(fn) else fn
        except Exception:
            household = None
        if household is not None:
            return household
    return None


def _get_household_id(household):
    if household is None:
        return None

    for attr in ("id", "household_id", "guid64"):
        value = getattr(household, attr, None)
        if value is None:
            continue
        try:
            return int(value)
        except Exception:
            continue
    return None


def _get_active_household_id():
    return _get_household_id(_get_active_household())


def _count_household_sim_infos(household):
    if household is None:
        return 0

    for attr in ("sim_info_gen", "instanced_sims_gen"):
        fn = getattr(household, attr, None)
        if callable(fn):
            try:
                return sum(1 for _ in fn())
            except Exception:
                continue

    for attr in ("sim_info_count", "size"):
        value = getattr(household, attr, None)
        if value is None:
            continue
        try:
            return max(0, int(value))
        except Exception:
            continue
    return 0


def _count_active_household_sim_infos():
    return _count_household_sim_infos(_get_active_household())


def _sim_info_household_id(sim_info):
    if sim_info is None:
        return None
    value = getattr(sim_info, "household_id", None)
    if value is not None:
        try:
            return int(value)
        except Exception:
            pass
    household = getattr(sim_info, "household", None)
    return _get_household_id(household)


def _sim_info_id(sim_info):
    if sim_info is None:
        return None
    for attr_name in ("sim_id", "id", "guid64"):
        value = getattr(sim_info, attr_name, None)
        if value is None:
            continue
        try:
            return int(value)
        except Exception:
            continue
    return None


def _iter_active_household_sim_infos():
    household = _get_active_household()
    target_household_id = _get_household_id(household)
    if household is None or target_household_id is None:
        return ()

    out = []
    seen = set()

    def _append(candidate):
        sim_info = getattr(candidate, "sim_info", None) or candidate
        if sim_info is None:
            return
        if _sim_info_household_id(sim_info) != int(target_household_id):
            return
        key = _sim_info_id(sim_info)
        if key is None:
            key = id(sim_info)
        if key in seen:
            return
        seen.add(key)
        out.append(sim_info)

    for attr_name in ("sim_info_gen", "instanced_sims_gen"):
        fn = getattr(household, attr_name, None)
        if not callable(fn):
            continue
        try:
            for candidate in fn():
                _append(candidate)
        except Exception:
            continue

    if out:
        return tuple(out)

    services = _get_services_module()
    if services is None:
        return ()
    try:
        manager = services.sim_info_manager()
    except Exception:
        manager = None
    if manager is None:
        return ()
    values = getattr(manager, "values", None)
    if not callable(values):
        return ()
    try:
        for candidate in values():
            _append(candidate)
    except Exception:
        return ()
    return tuple(out)


def _resolve_active_household_anchor_sim_info(preferred_sim_id=None):
    preferred_sim_id = _coerce_int(preferred_sim_id)
    first_sim_info = None
    for sim_info in _iter_active_household_sim_infos():
        if first_sim_info is None:
            first_sim_info = sim_info
        if preferred_sim_id is None:
            continue
        if _sim_info_id(sim_info) == int(preferred_sim_id):
            return sim_info
    return first_sim_info


def _maybe_run_legacy_v2_auto_migration(*, reason="runtime_init"):
    summary = {
        "ok": False,
        "reason": None,
        "active_household_id": _get_active_household_id(),
        "candidate_summary": None,
        "migration_summary": None,
        "already_migrated": 0,
    }
    household_id = _coerce_int(summary.get("active_household_id"))
    if household_id is None:
        summary["reason"] = "missing_household"
        return summary

    if has_household_legacy_v2_auto_migration_run(int(household_id)):
        summary["reason"] = "already_migrated"
        summary["already_migrated"] = 1
        return summary

    candidate_summary = inspect_active_household_legacy_v2_candidates(
        active_household_id=int(household_id),
        refresh_marker_cache=False,
        transit_service=get_global_transit_service(),
    )
    summary["candidate_summary"] = candidate_summary
    if not isinstance(candidate_summary, dict) or not candidate_summary.get("should_migrate"):
        summary["reason"] = "no_legacy_candidate"
        return summary

    anchor_sim_info = _resolve_active_household_anchor_sim_info(candidate_summary.get("anchor_sim_id"))
    if anchor_sim_info is None:
        summary["reason"] = "missing_anchor_sim"
        return summary

    try:
        from .loot_actions import migrate_legacy_v2_household_for_sim_info
    except Exception:
        _log_exception("Cosmic Engine legacy V2 auto-migration import failed.")
        summary["reason"] = "import_failed"
        return summary

    try:
        migration_summary = migrate_legacy_v2_household_for_sim_info(anchor_sim_info)
    except Exception:
        _log_exception("Cosmic Engine legacy V2 auto-migration failed for household %s.", household_id)
        summary["reason"] = "migration_failed"
        return summary

    summary["migration_summary"] = migration_summary
    if not isinstance(migration_summary, dict) or not migration_summary.get("ok"):
        summary["reason"] = "migration_failed"
        return summary

    mark_household_legacy_v2_auto_migration_run(
        int(household_id),
        source=str(reason or "runtime_init"),
        candidate_summary=candidate_summary,
        migration_summary=migration_summary,
    )
    _queue_runtime_scopes(
        (
            SCOPE_NATAL_SNAPSHOTS,
            SCOPE_PLANET_HOUSES,
            SCOPE_VISIBLE_SIGN_BUFFS,
            SCOPE_RISING_BUFFS,
        ),
        reason="legacy_v2_auto_migration",
    )
    summary["ok"] = True
    summary["reason"] = "migrated"
    return summary


def _maybe_run_outer_planets_household_refresh(*, reason="runtime_init"):
    summary = {
        "ok": False,
        "reason": None,
        "active_household_id": _get_active_household_id(),
        "already_refreshed": 0,
        "refresh_summary": None,
    }

    if not is_outer_planets_addon_active():
        summary["reason"] = "addon_inactive"
        return summary

    household_id = _coerce_int(summary.get("active_household_id"))
    if household_id is None:
        summary["reason"] = "missing_household"
        return summary

    if has_household_outer_planets_refresh_run(int(household_id)):
        summary["reason"] = "already_refreshed"
        summary["already_refreshed"] = 1
        return summary

    target_sim_infos = tuple(_iter_active_household_sim_infos())
    if not target_sim_infos:
        summary["reason"] = "no_household_sims"
        return summary

    try:
        refresh_summary = sync_active_household_outer_planets_only(
            transit_service=get_global_transit_service(),
            refresh_marker_cache=False,
            sim_infos=target_sim_infos,
        )
    except Exception:
        _log_exception("Outer planets one-time household refresh failed for household %s.", household_id)
        summary["reason"] = "refresh_failed"
        return summary

    summary["refresh_summary"] = refresh_summary
    if not isinstance(refresh_summary, dict) or not refresh_summary.get("ok"):
        summary["reason"] = "refresh_failed"
        return summary

    mark_household_outer_planets_refresh_run(
        int(household_id),
        source=str(reason or "runtime_init"),
        refresh_summary=refresh_summary,
    )
    summary["ok"] = True
    summary["reason"] = "refreshed"
    return summary


def _maybe_run_sign_compatibility_household_seed(*, reason="runtime_init"):
    summary = {
        "ok": False,
        "reason": None,
        "active_household_id": _get_active_household_id(),
        "refresh_summary": None,
    }

    household_id = _coerce_int(summary.get("active_household_id"))
    if household_id is None:
        summary["reason"] = "missing_household"
        return summary

    target_sim_infos = tuple(_iter_active_household_sim_infos())
    if not target_sim_infos:
        summary["reason"] = "no_household_sims"
        return summary

    try:
        bridge_report = dispatch_household_onboard(
            int(household_id),
            refresh_marker_cache=False,
        )
    except Exception:
        _log_exception(
            "Sign compatibility household seed failed for household %s.",
            household_id,
        )
        summary["reason"] = "seed_failed"
        return summary

    refresh_summary = (
        dict((bridge_report or {}).get("addon_summaries", {}).get("compatibility_household", {}))
        if isinstance(bridge_report, dict)
        else None
    )
    summary["refresh_summary"] = refresh_summary
    if not isinstance(refresh_summary, dict) or not refresh_summary:
        summary["reason"] = "seed_failed"
        return summary

    summary["ok"] = bool(refresh_summary.get("ok"))
    summary["reason"] = str(refresh_summary.get("reason") or "seed_failed")
    return summary


def _get_live_context_reconcile_reason():
    current_ready_count = _count_ready_sims()
    current_active_household_id = _get_active_household_id()
    current_active_household_sim_count = int(_count_active_household_sim_infos() or 0)

    last_ready_count = _RUNTIME_STATE.get("last_ready_sim_count")
    last_active_household_id = _RUNTIME_STATE.get("last_active_household_id")
    last_active_household_sim_count = _RUNTIME_STATE.get("last_active_household_sim_count")

    household_context_ready = (
        current_active_household_id is not None and current_active_household_sim_count > 0
    )
    if not household_context_ready:
        return None

    if (
        last_active_household_id is not None
        and last_active_household_id != current_active_household_id
    ):
        return "household_changed"
    if last_active_household_id is None:
        return "household_context_ready"

    if last_active_household_sim_count is None:
        return "household_count_ready"
    try:
        last_active_household_sim_count = int(last_active_household_sim_count)
    except Exception:
        last_active_household_sim_count = None
    if (
        last_active_household_sim_count is not None
        and last_active_household_sim_count != current_active_household_sim_count
    ):
        return "household_sim_count_changed"

    if current_ready_count is None:
        return None
    try:
        current_ready_count = int(current_ready_count)
    except Exception:
        return None

    if last_ready_count is None:
        if current_ready_count > 0:
            return "ready_sim_count_ready"
        return None
    try:
        last_ready_count = int(last_ready_count)
    except Exception:
        last_ready_count = None
    if last_ready_count is not None and last_ready_count != current_ready_count:
        return "ready_sim_count_changed"

    if not _RUNTIME_STATE.get("startup_retro_catchup_completed") and current_ready_count > 0:
        return "startup_context_ready"

    return None


def _read_in_save_payload():
    return _get_persistence_carriers().read_in_save_payload()


def _write_in_save_payload(payload):
    return _get_persistence_carriers().write_in_save_payload(payload)


def _get_persistence_adapter():
    global _PERSISTENCE_ADAPTER
    if _PERSISTENCE_ADAPTER is None:
        _PERSISTENCE_ADAPTER = TransitPersistenceAdapter(
            read_in_save_payload=_read_in_save_payload,
            write_in_save_payload=_write_in_save_payload,
            resolve_save_slot_key=_resolve_save_slot_key,
            on_pre_save=on_pre_save,
            log_warn_once=_log_warn_once,
            log_exception=_log_exception,
            log_debug=_log_debug,
        )
    return _PERSISTENCE_ADAPTER


def _read_persisted_payload():
    return _get_persistence_adapter().read_persisted_payload()

def _write_persisted_payload(payload):
    return _get_persistence_adapter().write_persisted_payload(payload)


def _load_persisted_transit_record():
    return _get_persistence_adapter().load_persisted_transit_record()


def _persist_transit_record(reason="unknown"):
    return _get_persistence_adapter().persist_transit_record(reason=reason)


def _load_persisted_chemistry_profile():
    return _get_persistence_adapter().load_persisted_chemistry_profile()


def _persist_chemistry_profile(profile_id, reason="unknown"):
    return _get_persistence_adapter().persist_chemistry_profile(
        str(profile_id or ""),
        reason=reason,
    )


def _load_persisted_retrograde_visibility_profile():
    return _get_persistence_adapter().load_persisted_retrograde_visibility_profile()


def _load_persisted_sign_compatibility_seed_profile():
    return _get_persistence_adapter().load_persisted_sign_compatibility_seed_profile()


def _persist_retrograde_visibility_profile(profile_id, reason="unknown"):
    return _get_persistence_adapter().persist_retrograde_visibility_profile(
        str(profile_id or ""),
        reason=reason,
    )


def load_chemistry_profile():
    return _load_persisted_chemistry_profile()


def persist_chemistry_profile(profile_id, reason="debug.manual"):
    """Best-effort manual write for chemistry profile changes."""
    try:
        return bool(_persist_chemistry_profile(profile_id, reason=reason))
    except Exception:
        _log_exception("Manual chemistry profile persist failed (%s).", reason)
        return False


def load_retrograde_visibility_profile():
    return _load_persisted_retrograde_visibility_profile()


def persist_retrograde_visibility_profile(profile_id, reason="debug.manual"):
    """Best-effort manual write for retrograde visibility profile changes."""
    try:
        return bool(_persist_retrograde_visibility_profile(profile_id, reason=reason))
    except Exception:
        _log_exception("Manual retrograde visibility profile persist failed (%s).", reason)
        return False


def _get_trait_manager():
    try:
        import services  # type: ignore
        import sims4.resources  # type: ignore

        return services.get_instance_manager(sims4.resources.Types.TRAIT)
    except Exception:
        return None


def _resolve_trait_tuning(trait_id):
    manager = _get_trait_manager()
    if manager is None:
        return None
    try:
        return manager.get(int(trait_id))
    except Exception:
        return None


def _trait_guid64(trait) -> Optional[int]:
    if trait is None:
        return None
    for attr_name in ("guid64", "guid", "trait_id"):
        value = getattr(trait, attr_name, None)
        if value is None:
            continue
        try:
            return int(value)
        except Exception:
            continue
    return None


def _iter_trait_tunings_for_sim_info(sim_info):
    if sim_info is None:
        return ()

    out = []
    seen = set()

    def _append(candidate):
        if candidate is None or isinstance(candidate, (str, bytes)):
            return
        if isinstance(candidate, dict):
            iterable = candidate.values()
        elif isinstance(candidate, (list, tuple, set, frozenset)):
            iterable = candidate
        else:
            iterable = None
        if iterable is not None:
            for item in iterable:
                _append(item)
            return
        key = _trait_guid64(candidate)
        if key is None:
            key = id(candidate)
        if key in seen:
            return
        seen.add(key)
        out.append(candidate)

    for owner in (getattr(sim_info, "trait_tracker", None), sim_info):
        if owner is None:
            continue
        for attr_name in (
            "equipped_traits",
            "_equipped_traits",
            "all_traits",
            "_all_traits",
            "traits",
            "_traits",
            "hidden_traits",
            "_hidden_traits",
        ):
            try:
                _append(getattr(owner, attr_name, None))
            except Exception:
                continue
        for method_name in (
            "get_traits",
            "get_all_traits",
            "all_traits_gen",
            "get_hidden_traits",
        ):
            fn = getattr(owner, method_name, None)
            if not callable(fn):
                continue
            try:
                _append(fn())
            except TypeError:
                continue
            except Exception:
                continue
    return tuple(out)


def _iter_trait_ids_for_sim_info(sim_info):
    return tuple(
        int(trait_id)
        for trait_id in (
            _trait_guid64(trait) for trait in _iter_trait_tunings_for_sim_info(sim_info)
        )
        if trait_id is not None
    )


def _add_trait_id_for_sim_info(sim_info, trait_id):
    if sim_info is None:
        return False
    desired_trait_id = _coerce_int(trait_id)
    if desired_trait_id is None:
        return False
    if int(desired_trait_id) in set(_iter_trait_ids_for_sim_info(sim_info)):
        return True

    trait = _resolve_trait_tuning(int(desired_trait_id))
    if trait is None:
        return False

    for owner in (getattr(sim_info, "trait_tracker", None), sim_info):
        add_fn = getattr(owner, "add_trait", None)
        if not callable(add_fn):
            continue
        try:
            add_fn(trait)
            return True
        except Exception:
            continue
    return False


def _remove_trait_id_for_sim_info(sim_info, trait_id):
    if sim_info is None:
        return False
    desired_trait_id = _coerce_int(trait_id)
    if desired_trait_id is None:
        return False

    removed = False
    for trait in _iter_trait_tunings_for_sim_info(sim_info):
        if _trait_guid64(trait) != int(desired_trait_id):
            continue
        for owner in (getattr(sim_info, "trait_tracker", None), sim_info):
            remove_fn = getattr(owner, "remove_trait", None)
            if not callable(remove_fn):
                continue
            try:
                remove_fn(trait)
                removed = True
                break
            except Exception:
                continue
    return removed


def _read_sign_compatibility_chart_payload(sim_info):
    try:
        from .loot_actions import _resolve_live_sign_compatibility_chart_payload
    except Exception:
        return None
    try:
        return _resolve_live_sign_compatibility_chart_payload(sim_info)
    except Exception:
        return None


def _clear_sign_compatibility_runtime_lane_state(sim_info, lane_name):
    try:
        from .loot_actions import _clear_sign_compatibility_runtime_lane_state_from_actor
    except Exception:
        return {"ok": False, "reason": "missing_runtime_helper"}
    try:
        return _clear_sign_compatibility_runtime_lane_state_from_actor(
            sim_info,
            str(lane_name or ""),
        )
    except Exception:
        return {"ok": False, "reason": "clear_failed"}


def get_persistence_debug_payload():
    slot_key = _resolve_save_slot_key()
    carrier_status = _get_persistence_carriers().debug_payload_status(slot_key=slot_key)
    payload = _read_persisted_payload()
    slots = payload.get("slots") if isinstance(payload, dict) else None
    slot_payload = slots.get(slot_key) if isinstance(slots, dict) else None
    if not isinstance(slot_payload, dict) and isinstance(slots, dict):
        slot_payload = slots.get("default")
    record = slot_payload.get("transit_record") if isinstance(slot_payload, dict) else None
    service = get_global_transit_service()

    def _active_bodies(mapping):
        if not isinstance(mapping, dict):
            return ()
        return tuple(sorted(str(body) for body, active in mapping.items() if bool(active)))

    out = {
        "backend": str(_PERSISTENCE_BACKEND),
        "slot_key": str(slot_key),
        "carrier_status": carrier_status,
        "payload_present": bool(isinstance(payload, dict) and bool(payload)),
        "payload_version": payload.get("version") if isinstance(payload, dict) else None,
        "record_present": bool(isinstance(record, dict)),
        "live_active_retrogrades": _active_bodies(service.retrograde_active_by_body()),
        "live_snapshot_key": service.current_snapshot_key(),
    }
    if isinstance(record, dict):
        out.update(
            {
                "record_version": record.get("version"),
                "record_last_snapshot_key": record.get("last_snapshot_key"),
                "record_anchor_days": record.get("anchor_total_days_elapsed"),
                "record_anchor_segments": record.get("anchor_total_segments_elapsed"),
                "record_active_retrogrades": _active_bodies(record.get("retrograde_active_by_body")),
                "record_has_mode_lock": bool(isinstance(record.get(service.MODE_LOCK_KEY), dict)),
                "record_mode_lock": (
                    dict(record.get(service.MODE_LOCK_KEY))
                    if isinstance(record.get(service.MODE_LOCK_KEY), dict)
                    else {}
                ),
            }
        )
    return out


def get_chemistry_profile_debug_payload():
    payload = _read_persisted_payload()
    chemistry_profile = _load_persisted_chemistry_profile()
    return {
        "backend": str(_PERSISTENCE_BACKEND),
        "payload_present": bool(isinstance(payload, dict) and bool(payload)),
        "payload_version": payload.get("version") if isinstance(payload, dict) else None,
        "selected_profile_id": read_chemistry_profile_id(chemistry_profile),
        "chemistry_profile": (
            dict(chemistry_profile) if isinstance(chemistry_profile, dict) else {}
        ),
    }


def get_retrograde_visibility_profile_debug_payload():
    payload = _read_persisted_payload()
    retrograde_visibility_profile = _load_persisted_retrograde_visibility_profile()
    return {
        "backend": str(_PERSISTENCE_BACKEND),
        "payload_present": bool(isinstance(payload, dict) and bool(payload)),
        "payload_version": payload.get("version") if isinstance(payload, dict) else None,
        "selected_profile_id": read_retrograde_visibility_profile_id(retrograde_visibility_profile),
        "retrograde_visibility_profile": (
            dict(retrograde_visibility_profile)
            if isinstance(retrograde_visibility_profile, dict)
            else {}
        ),
    }


def _prime_segment_total_from_service_record():
    record = get_global_transit_service().build_save_record()
    value = _coerce_int(record.get("last_total_segments_seen"))
    if value is None:
        value = 0
    _RUNTIME_STATE["segment_total"] = value
    _RUNTIME_STATE["segment_pair"] = None


def _is_shared_runtime_mode(active_mode=None):
    if active_mode is None:
        active_mode = get_mode_lock()
    return active_mode in (None, "big3", "cosmic")


def _queue_runtime_scopes(scopes, *, reason="runtime"):
    normalized = tuple(scope for scope in tuple(scopes or ()) if scope)
    if not normalized:
        return None
    return mark_scope_dirty(normalized, reason=reason)


def _resolve_dirty_sim_infos(sim_ids):
    normalized_ids = set()
    for sim_id in tuple(sim_ids or ()):
        try:
            normalized_ids.add(int(sim_id))
        except Exception:
            continue
    if not normalized_ids:
        return None

    out = []
    seen = set()
    for sim_info in _iter_instanced_sim_infos():
        resolved_id = None
        for attr_name in ("sim_id", "id"):
            value = getattr(sim_info, attr_name, None)
            if value is None:
                continue
            try:
                resolved_id = int(value)
                break
            except Exception:
                continue
        if resolved_id is None or resolved_id not in normalized_ids or resolved_id in seen:
            continue
        seen.add(resolved_id)
        out.append(sim_info)
    return tuple(out)


def _flush_dirty_sync_queue(*, reason="runtime", active_mode=None):
    if active_mode is None:
        active_mode = get_mode_lock()
    shared_runtime_enabled = _is_shared_runtime_mode(active_mode)
    retrogrades_enabled = _is_shared_runtime_mode(active_mode)
    cosmic_active = active_mode == "cosmic"
    lower_reason = str(reason or "runtime").lower()
    init_like = ("init" in lower_reason) or ("bootstrap" in lower_reason)
    tick_like = "tick" in lower_reason

    def _context_target_sim_infos(_context):
        target_sim_infos = _resolve_dirty_sim_infos((_context or {}).get("sim_ids", ()))
        if ((_context or {}).get("sim_ids") or ()) and not target_sim_infos:
            return ()
        return target_sim_infos

    def _planet_houses(_context):
        if not shared_runtime_enabled or _RUNTIME_STATE.get("planet_marker_sync_disabled"):
            return None
        target_sim_infos = _context_target_sim_infos(_context)
        if target_sim_infos == ():
            return None
        try:
            return sync_zone_planet_house_markers(sim_infos=target_sim_infos)
        except Exception:
            _log_warn_once(
                "planet_marker_sync_runtime_failed",
                "Cosmic Engine planet-house marker sync failed during runtime consolidation; markers disabled for this session.",
            )
            _RUNTIME_STATE["planet_marker_sync_disabled"] = True
            return None

    def _house_ingress(_context):
        if not shared_runtime_enabled or _RUNTIME_STATE.get("house_ingress_notification_disabled"):
            return None
        try:
            return process_active_sim_house_ingress_notifications(
                show_notifications=bool(tick_like and not init_like),
                refresh_baseline=bool(init_like),
                max_notices=0 if init_like else 5,
            )
        except Exception:
            _log_warn_once(
                "house_ingress_notice_runtime_failed",
                "Cosmic Engine house ingress notification processing failed during runtime consolidation; house ingress notices disabled for this session.",
            )
            _RUNTIME_STATE["house_ingress_notification_disabled"] = True
            return None

    def _natal_snapshots(_context):
        if not cosmic_active or _RUNTIME_STATE.get("natal_snapshot_sync_disabled"):
            return None
        target_sim_infos = _context_target_sim_infos(_context)
        if target_sim_infos == ():
            return None
        try:
            return sync_zone_natal_snapshots(sim_infos=target_sim_infos)
        except Exception:
            _log_warn_once(
                "natal_snapshot_sync_runtime_failed",
                "Cosmic Engine natal snapshot sync failed during runtime consolidation; natal snapshots disabled for this session.",
            )
            _RUNTIME_STATE["natal_snapshot_sync_disabled"] = True
            return None

    def _visible_sign_buffs(_context):
        if _RUNTIME_STATE.get("sign_buff_manager_disabled"):
            return None
        target_sim_infos = _context_target_sim_infos(_context)
        if target_sim_infos == ():
            return None
        try:
            return process_managed_visible_sign_buffs(sim_infos=target_sim_infos)
        except Exception:
            _log_warn_once(
                "sign_buff_manager_runtime_failed",
                "Cosmic Engine managed Sun/Moon buff processing failed during runtime consolidation; Sun/Moon flare buffs will not be auto-cleared this session.",
            )
            _RUNTIME_STATE["sign_buff_manager_disabled"] = True
            return None

    def _rising_buffs(_context):
        if _RUNTIME_STATE.get("rising_buff_manager_disabled"):
            return None
        target_sim_infos = _context_target_sim_infos(_context)
        if target_sim_infos == ():
            return None
        try:
            return process_managed_rising_buffs(sim_infos=target_sim_infos)
        except Exception:
            _log_warn_once(
                "rising_buff_manager_runtime_failed",
                "Cosmic Engine managed Rising buff processing failed during runtime consolidation; Rising timed buffs will not be auto-cleared this session.",
            )
            _RUNTIME_STATE["rising_buff_manager_disabled"] = True
            return None

    def _moon_return(_context):
        if not shared_runtime_enabled or _RUNTIME_STATE.get("moon_return_sync_disabled"):
            return None
        target_sim_infos = _context_target_sim_infos(_context)
        if target_sim_infos == ():
            return None
        try:
            return sync_zone_moon_return_markers(
                show_notifications=bool(tick_like and not init_like),
                sim_infos=target_sim_infos,
            )
        except Exception:
            _log_warn_once(
                "moon_return_sync_runtime_failed",
                "Cosmic Engine Moon Return sync failed during runtime consolidation; Moon Return markers disabled for this session.",
            )
            _RUNTIME_STATE["moon_return_sync_disabled"] = True
            return None

    def _solar_return(_context):
        if not shared_runtime_enabled or _RUNTIME_STATE.get("solar_return_sync_disabled"):
            return None
        target_sim_infos = _context_target_sim_infos(_context)
        if target_sim_infos == ():
            return None
        try:
            return sync_zone_solar_return_markers(
                show_notifications=bool(tick_like and not init_like),
                sim_infos=target_sim_infos,
            )
        except Exception:
            _log_warn_once(
                "solar_return_sync_runtime_failed",
                "Cosmic Engine Solar Return sync failed during runtime consolidation; Solar Return markers disabled for this session.",
            )
            _RUNTIME_STATE["solar_return_sync_disabled"] = True
            return None

    def _retrograde_markers(_context):
        if not retrogrades_enabled:
            return None
        target_sim_infos = _context_target_sim_infos(_context)
        if target_sim_infos == ():
            return None
        try:
            return sync_zone_retrograde_markers(
                manage_consequences=False,
                sim_infos=target_sim_infos,
            )
        except Exception:
            _log_warn_once(
                "retrograde_marker_sync_runtime_failed",
                "Cosmic Engine retrograde marker sync failed during runtime consolidation; will retry on a later tick.",
            )
            return None

    def _retrograde_consequences(_context):
        if not retrogrades_enabled:
            return None
        target_sim_infos = _context_target_sim_infos(_context)
        if target_sim_infos == ():
            return None
        try:
            return ensure_zone_retrograde_consequences(
                reason=str(reason or "runtime"),
                sim_infos=target_sim_infos,
            )
        except Exception:
            _log_warn_once(
                "retrograde_consequence_runtime_failed",
                "Cosmic Engine retrograde consequence sync failed during runtime consolidation; will retry on a later tick.",
            )
            return None

    def _crystal_resonance(_context):
        if _RUNTIME_STATE.get("crystal_resonance_disabled"):
            return None
        target_sim_infos = _context_target_sim_infos(_context)
        if target_sim_infos == ():
            return None
        if target_sim_infos is None:
            try:
                target_sim_infos = tuple(_iter_instanced_sim_infos())
            except Exception:
                target_sim_infos = ()
            if not target_sim_infos:
                return None
        try:
            sim_now = _get_sim_now()
            now_ticks = _call_or_value(sim_now, "absolute_ticks")
            return sync_crystal_resonance(sim_infos=target_sim_infos, now_ticks=int(now_ticks or 0))
        except Exception:
            _log_warn_once(
                "crystal_resonance_runtime_failed",
                "Cosmic Engine crystal resonance sync failed during runtime consolidation; crystal resonance disabled for this session.",
            )
            _RUNTIME_STATE["crystal_resonance_disabled"] = True
            return None

    executor_by_scope = {
        SCOPE_PLANET_HOUSES: _planet_houses,
        SCOPE_HOUSE_INGRESS: _house_ingress,
        SCOPE_NATAL_SNAPSHOTS: _natal_snapshots,
        SCOPE_VISIBLE_SIGN_BUFFS: _visible_sign_buffs,
        SCOPE_RISING_BUFFS: _rising_buffs,
        SCOPE_MOON_RETURN: _moon_return,
        SCOPE_SOLAR_RETURN: _solar_return,
        SCOPE_RETROGRADE_MARKERS: _retrograde_markers,
        SCOPE_RETROGRADE_CONSEQUENCES: _retrograde_consequences,
        SCOPE_CRYSTAL_RESONANCE: _crystal_resonance,
    }
    return flush_dirty_scopes(executor_by_scope, reason=str(reason or "runtime"))


def _apply_retrograde_runtime_consequences(reason="runtime", *, route_notifications=True):
    def _store_summary(
        *,
        skip_reason=None,
        last_changes=None,
        marker_summary=None,
        consequence_summary=None,
        dispatch_failed=False,
    ):
        summary = {
            "reason": str(reason),
            "skip_reason": str(skip_reason) if skip_reason else None,
            "last_changes": dict(last_changes) if isinstance(last_changes, dict) else {},
            "marker_summary": marker_summary if isinstance(marker_summary, dict) else {},
            "consequence_summary": (
                consequence_summary if isinstance(consequence_summary, dict) else {}
            ),
            "route_notifications": bool(route_notifications),
            "dispatch_failed": bool(dispatch_failed),
            "active_mode": str(get_mode_lock() or ""),
            "retrograde_marker_sync_disabled": bool(
                _RUNTIME_STATE.get("retrograde_marker_sync_disabled")
            ),
        }
        _RUNTIME_STATE["last_retrograde_runtime_summary"] = summary
        return summary

    if _RUNTIME_STATE.get("retrograde_marker_sync_disabled"):
        return _store_summary(skip_reason="retrograde_marker_sync_disabled")

    active_mode = get_mode_lock()
    if not _is_shared_runtime_mode(active_mode):
        return _store_summary(skip_reason="inactive_mode")

    service = get_global_transit_service()
    last_changes = {}
    try:
        last_changes = service.get_last_retrograde_changes()
    except Exception:
        last_changes = {}

    if last_changes:
        _log_debug("Retrograde edges (%s): %s", reason, last_changes)

    marker_summary = {}
    consequence_summary = {}
    try:
        marker_summary = sync_zone_retrograde_markers(manage_consequences=False)
        consequence_summary = ensure_zone_retrograde_consequences(reason=reason)
    except Exception:
        _log_warn_once(
            "retrograde_runtime_consequence_failed",
            "Cosmic Engine retrograde consequence pass failed (%s); will retry on a later tick.",
            reason,
        )
        return _store_summary(
            skip_reason="exception",
            last_changes=last_changes,
            marker_summary=marker_summary,
            consequence_summary=consequence_summary,
            dispatch_failed=True,
        )

    marker_changed = (
        int(marker_summary.get("traits_added", 0))
        or int(marker_summary.get("traits_removed", 0))
        or int(marker_summary.get("traits_rehydrated", 0))
        or int(marker_summary.get("traits_rehydrate_queued", 0))
    )
    consequence_changed = (
        int(consequence_summary.get("buffs_added", 0))
        or int(consequence_summary.get("buffs_removed", 0))
        or int(consequence_summary.get("intense_buffs_added", 0))
        or int(consequence_summary.get("intense_buffs_removed", 0))
    )
    dispatch_failures = int(consequence_summary.get("dispatch_failures", 0))

    if last_changes:
        _log_debug(
            "Retrograde edge apply (%s): edges=%s markers=%s consequences=%s",
            reason,
            last_changes,
            marker_summary,
            consequence_summary,
        )
    elif consequence_changed:
        _log_debug(
            "Retrograde reassert (%s): markers=%s consequences=%s",
            reason,
            marker_summary,
            consequence_summary,
        )
    elif marker_changed:
        _log_debug("Retrograde marker-only sync (%s): %s", reason, marker_summary)
    elif dispatch_failures:
        _log_warn_once(
            "retrograde_dispatch_failed_{0}".format(reason),
            "Cosmic Engine retrograde dispatch saw %s failures during %s.",
            dispatch_failures,
            reason,
        )

    if route_notifications:
        _route_retrograde_notifications(reason=reason)
    return _store_summary(
        last_changes=last_changes,
        marker_summary=marker_summary,
        consequence_summary=consequence_summary,
    )


def _run_startup_retro_catchup(reason="startup_catchup"):
    attempt = int(_RUNTIME_STATE.get("startup_retro_catchup_attempts") or 0) + 1
    _RUNTIME_STATE["startup_retro_catchup_attempts"] = attempt

    time_service = _get_time_service()
    total_days = _resolve_total_days_elapsed(time_service) if time_service is not None else None
    total_segments = _resolve_total_segments_elapsed()
    instanced_sim_count = _count_instanced_sims()
    ready_sim_count = _count_ready_sims()
    active_household_sim_count = _count_active_household_sim_infos()

    _log_debug(
        "Retrograde startup catch-up (%s): attempt=%s days=%s segments=%s instanced=%s ready=%s active_household=%s",
        reason,
        attempt,
        total_days,
        total_segments,
        instanced_sim_count,
        ready_sim_count,
        active_household_sim_count,
    )

    if int(ready_sim_count or 0) <= 0 or int(active_household_sim_count or 0) <= 0:
        summary = {
            "reason": str(reason),
            "phase": "startup_catchup",
            "attempt": int(attempt),
            "deferred_reason": "live_sim_context_not_ready",
            "total_days_elapsed": total_days,
            "total_segments_elapsed": total_segments,
            "instanced_sim_count": int(instanced_sim_count or 0),
            "ready_sim_count": int(ready_sim_count or 0),
            "active_household_sim_count": int(active_household_sim_count or 0),
            "did_direct_dispatch": False,
            "last_changes": {},
            "marker_summary": {},
            "consequence_summary": {},
            "route_notifications": False,
            "dispatch_failed": False,
            "active_mode": str(get_mode_lock() or ""),
            "retrograde_marker_sync_disabled": bool(
                _RUNTIME_STATE.get("retrograde_marker_sync_disabled")
            ),
            "skip_reason": None,
        }
        _RUNTIME_STATE["last_startup_retro_catchup_summary"] = summary
        return summary

    summary = _apply_retrograde_runtime_consequences(reason=reason, route_notifications=False) or {}
    consequence_summary = (
        summary.get("consequence_summary") if isinstance(summary.get("consequence_summary"), dict) else {}
    )
    dispatch_total = (
        int(consequence_summary.get("buffs_added", 0))
        + int(consequence_summary.get("buffs_removed", 0))
        + int(consequence_summary.get("intense_buffs_added", 0))
        + int(consequence_summary.get("intense_buffs_removed", 0))
    )
    summary["phase"] = "startup_catchup"
    summary["attempt"] = int(attempt)
    summary["deferred_reason"] = None
    summary["total_days_elapsed"] = total_days
    summary["total_segments_elapsed"] = total_segments
    summary["instanced_sim_count"] = int(instanced_sim_count or 0)
    summary["ready_sim_count"] = int(ready_sim_count or 0)
    summary["active_household_sim_count"] = int(active_household_sim_count or 0)
    summary["did_direct_dispatch"] = bool(dispatch_total > 0)
    _RUNTIME_STATE["last_startup_retro_catchup_summary"] = summary
    return summary


def _is_startup_retro_catchup_complete(summary):
    if not isinstance(summary, dict):
        return False
    if summary.get("deferred_reason") is not None:
        return False
    if summary.get("skip_reason") is not None:
        return False
    if bool(summary.get("dispatch_failed")):
        return False
    ready_sim_count = summary.get("ready_sim_count")
    if ready_sim_count is not None:
        if int(ready_sim_count or 0) <= 0:
            return False
    elif int(summary.get("instanced_sim_count") or 0) <= 0:
        return False
    return True


def _maybe_schedule_startup_retro_retry(summary):
    if not isinstance(summary, dict):
        return False
    if summary.get("deferred_reason") is None:
        return False
    if int(summary.get("attempt", 0)) >= _STARTUP_RETRO_CATCHUP_MAX_ATTEMPTS:
        return False
    return _schedule_runtime_retro_reassert()


def get_last_retrograde_runtime_summary():
    summary = _RUNTIME_STATE.get("last_retrograde_runtime_summary")
    if not isinstance(summary, dict):
        return None
    try:
        return json.loads(json.dumps(summary, sort_keys=True))
    except Exception:
        return dict(summary)


def get_last_startup_retro_catchup_summary():
    summary = _RUNTIME_STATE.get("last_startup_retro_catchup_summary")
    if not isinstance(summary, dict):
        return None
    try:
        return json.loads(json.dumps(summary, sort_keys=True))
    except Exception:
        return dict(summary)


def _route_retrograde_notifications(reason="runtime"):
    try:
        process_pending_retrograde_notifications(
            allowed_sources=("clock_snapshot",),
            consume_unmapped=False,
            max_events=20,
        )
    except Exception:
        _log_warn_once(
            "retrograde_runtime_notification_failed",
            "Cosmic Engine retrograde notification routing failed during %s.",
            reason,
        )


def _ensure_initialized(zone_obj=None):
    zone_id = _resolve_zone_id(zone_obj=zone_obj)
    if _RUNTIME_STATE.get("initialized"):
        if zone_id is None:
            return
        if _RUNTIME_STATE["zone_id_initialized"] == zone_id:
            return

    saved_record = _load_persisted_transit_record()
    fallback_seed = zone_id if zone_id is not None else None
    try:
        on_zone_or_save_load(saved_record=saved_record, fallback_seed=fallback_seed)
    except Exception:
        _log_exception("Cosmic Engine on_zone_or_save_load() failed.")
        return
    try:
        reset_managed_visible_sign_buff_state()
    except Exception:
        _log_warn_once(
            "sign_buff_manager_reset_failed",
            "Cosmic Engine managed Sun/Moon buff state reset failed on zone init.",
        )
    try:
        reset_managed_rising_buff_state()
    except Exception:
        _log_warn_once(
            "rising_buff_manager_reset_failed",
            "Cosmic Engine managed Rising buff state reset failed on zone init.",
        )

    _prime_segment_total_from_service_record()
    _cancel_runtime_retro_reassert_alarm()
    _RUNTIME_STATE["zone_id_initialized"] = zone_id
    _RUNTIME_STATE["marker_sync_tick_counter"] = 0
    _RUNTIME_STATE["last_startup_retro_catchup_summary"] = None
    _RUNTIME_STATE["startup_retro_catchup_attempts"] = 0
    _RUNTIME_STATE["startup_retro_catchup_completed"] = False
    _RUNTIME_STATE["last_instanced_sim_count"] = _count_instanced_sims()
    _RUNTIME_STATE["last_ready_sim_count"] = _count_ready_sims()
    _RUNTIME_STATE["last_active_household_id"] = _get_active_household_id()
    _RUNTIME_STATE["last_active_household_sim_count"] = _count_active_household_sim_infos()
    sim_days_per_year_hint = _resolve_sim_days_per_year()
    if sim_days_per_year_hint is not None:
        _RUNTIME_STATE["sim_days_per_year_hint"] = float(sim_days_per_year_hint)
    try:
        _RUNTIME_STATE["last_legacy_v2_auto_migration_summary"] = _maybe_run_legacy_v2_auto_migration(
            reason="zone_init"
        )
    except Exception:
        _RUNTIME_STATE["last_legacy_v2_auto_migration_summary"] = {
            "ok": False,
            "reason": "exception",
        }
        _log_exception("Cosmic Engine legacy V2 auto-migration probe failed.")
    try:
        _RUNTIME_STATE["last_outer_planets_household_refresh_summary"] = (
            _maybe_run_outer_planets_household_refresh(reason="zone_init")
        )
    except Exception:
        _RUNTIME_STATE["last_outer_planets_household_refresh_summary"] = {
            "ok": False,
            "reason": "exception",
        }
        _log_exception("Outer planets one-time household refresh probe failed.")
    try:
        _RUNTIME_STATE["last_sign_compatibility_household_seed_summary"] = (
            _maybe_run_sign_compatibility_household_seed(reason="zone_init")
        )
    except Exception:
        _RUNTIME_STATE["last_sign_compatibility_household_seed_summary"] = {
            "ok": False,
            "reason": "exception",
        }
        _log_exception("Sign compatibility household seed probe failed.")
    active_mode = get_mode_lock()
    retrogrades_enabled = _is_shared_runtime_mode(active_mode)
    shared_runtime_enabled = _is_shared_runtime_mode(active_mode)
    cosmic_active = active_mode == "cosmic"
    init_scopes = [SCOPE_VISIBLE_SIGN_BUFFS, SCOPE_RISING_BUFFS]
    if shared_runtime_enabled:
        init_scopes.extend((SCOPE_PLANET_HOUSES, SCOPE_HOUSE_INGRESS, SCOPE_MOON_RETURN, SCOPE_SOLAR_RETURN, SCOPE_CRYSTAL_RESONANCE))
    if cosmic_active:
        init_scopes.append(SCOPE_NATAL_SNAPSHOTS)
    _queue_runtime_scopes(init_scopes, reason="zone_init")
    _flush_dirty_sync_queue(reason="zone_init", active_mode=active_mode)
    _log_debug(
        "Initialized transit runtime (zone=%s, has_record=%s).",
        zone_id,
        bool(saved_record),
    )
    _RUNTIME_STATE["initialized"] = True


def _resolve_total_days_elapsed(time_service_obj):
    sim_now = getattr(time_service_obj, "sim_now", None)
    if sim_now is None:
        return None

    for name in ("absolute_days", "absolute_day"):
        value = _call_or_value(sim_now, name)
        if value is None:
            continue
        try:
            return int(value)
        except Exception:
            try:
                return int(float(value))
            except Exception:
                pass

    ticks = _call_or_value(sim_now, "absolute_ticks")
    if ticks is not None:
        ticks_int = _coerce_int(ticks)
        if ticks_int is not None:
            ticks_per_day = _resolve_sim_ticks_per_day()
            if ticks_per_day:
                try:
                    return int(ticks_int // ticks_per_day)
                except Exception:
                    pass

    try:
        text = str(sim_now)
    except Exception:
        text = ""
    match = _DATE_REPR_RE.search(text)
    if match:
        day = int(match.group(1))
        week = int(match.group(2))
        return (week * 7) + day

    return None


def _resolve_total_day_progress_elapsed(time_service_obj):
    sim_now = getattr(time_service_obj, "sim_now", None)
    if sim_now is None:
        return None

    ticks = _call_or_value(sim_now, "absolute_ticks")
    if ticks is not None:
        try:
            ticks_value = float(ticks)
        except Exception:
            ticks_value = None
        if ticks_value is not None:
            ticks_per_day = _resolve_sim_ticks_per_day()
            if ticks_per_day:
                try:
                    return float(ticks_value) / float(ticks_per_day)
                except Exception:
                    pass

    total_days = _resolve_total_days_elapsed(time_service_obj)
    if total_days is None:
        return None
    try:
        return float(total_days)
    except Exception:
        return None


def _resolve_sim_ticks_per_day():
    try:
        import date_and_time  # type: ignore

        fn = getattr(date_and_time, "sim_ticks_per_day", None)
        if callable(fn):
            value = fn()
            return _coerce_int(value)
    except Exception:
        return None
    return None


def _enumish_to_index(value, name_map):
    if value is None:
        return None

    # Prefer enum names over raw int values. TS4 enums can be int-like and some
    # use flag-style numeric values (e.g., FALL=4), which would normalize wrong.
    nested_name = getattr(value, "name", None)
    if nested_name:
        idx = _enumish_text_to_index(str(nested_name), name_map)
        if idx is not None:
            return idx

    idx = _enumish_text_to_index(str(value), name_map)
    if idx is not None:
        return idx

    direct = _coerce_int(value)
    if direct is not None:
        return direct

    nested = getattr(value, "value", None)
    nested_int = _coerce_int(nested)
    if nested_int is not None:
        return nested_int
    return None


def _enumish_text_to_index(text, name_map):
    upper = text.upper()
    for key, idx in name_map.items():
        if key in upper:
            return idx
    return None


def _season_pair_via_game_enums(season_value, segment_value):
    """Try explicit TS4 enum coercion (handles raw int enum values)."""
    try:
        from seasons.seasons import SeasonSegment, SeasonType  # type: ignore
    except Exception:
        return None

    try:
        season_name = SeasonType(season_value).name
        segment_name = SeasonSegment(segment_value).name
    except Exception:
        return None

    season_idx = _enumish_text_to_index(str(season_name), _SEASON_NAME_TO_INDEX)
    segment_idx = _enumish_text_to_index(str(segment_name), _SEGMENT_NAME_TO_INDEX)
    if season_idx is None or segment_idx is None:
        return None
    return (int(season_idx) % 4, int(segment_idx) % 3)


def _coerce_pair_from_values(season_value, segment_value):
    pair = _season_pair_via_game_enums(season_value, segment_value)
    if pair is not None:
        return pair
    season_idx = _enumish_to_index(season_value, _SEASON_NAME_TO_INDEX)
    segment_idx = _enumish_to_index(segment_value, _SEGMENT_NAME_TO_INDEX)
    if season_idx is None or segment_idx is None:
        return None
    return (int(season_idx) % 4, int(segment_idx) % 3)


def _extract_pair_from_containerish(value):
    """Parse season/segment pair from tuple/list/dict/object returns."""
    if value is None:
        return None

    # Common case: tuple/list with season + segment values.
    if isinstance(value, (tuple, list)):
        if len(value) >= 2:
            pair = _coerce_pair_from_values(value[0], value[1])
            if pair is not None:
                return pair
        # Search nested/other positions.
        season_candidate = None
        segment_candidate = None
        for item in value:
            if season_candidate is None:
                season_candidate = item
            if segment_candidate is None and _enumish_to_index(item, _SEGMENT_NAME_TO_INDEX) is not None:
                segment_candidate = item
            nested_pair = _extract_pair_from_containerish(item)
            if nested_pair is not None:
                return nested_pair
        if season_candidate is not None and segment_candidate is not None:
            pair = _coerce_pair_from_values(season_candidate, segment_candidate)
            if pair is not None:
                return pair
        return None

    if isinstance(value, dict):
        season_value = None
        segment_value = None
        for key, item in value.items():
            key_text = str(key).lower()
            if season_value is None and "season" in key_text and "segment" not in key_text:
                season_value = item
            if segment_value is None and "segment" in key_text:
                segment_value = item
        pair = _coerce_pair_from_values(season_value, segment_value)
        if pair is not None:
            return pair
        for item in value.values():
            nested_pair = _extract_pair_from_containerish(item)
            if nested_pair is not None:
                return nested_pair
        return None

    # Generic object with season/segment attrs.
    season_value = None
    segment_value = None
    for name in ("season", "current_season", "get_season"):
        season_value = _call_or_value(value, name)
        if season_value is not None:
            break
    for name in ("season_segment", "segment", "current_segment", "get_season_segment", "get_segment"):
        segment_value = _call_or_value(value, name)
        if segment_value is not None:
            break
    pair = _coerce_pair_from_values(season_value, segment_value)
    if pair is not None:
        return pair
    return None


def _extract_pair_from_season_service_combined(season_service):
    for args in _candidate_time_args():
        pair_value = _safe_call_method(season_service, "get_season_and_segments", *args)
        pair = _extract_pair_from_containerish(pair_value)
        if pair is not None:
            return pair
    return None


def _find_enumish_index_on_owner(
    owner,
    name_map,
    *,
    preferred_names=(),
    required_tokens=(),
    excluded_tokens=(),
):
    if owner is None:
        return None

    for name in preferred_names:
        idx = _enumish_to_index(_call_or_value(owner, name), name_map)
        if idx is not None:
            return idx

    try:
        names = sorted(dir(owner))
    except Exception:
        names = []

    for name in names:
        if name.startswith("__"):
            continue
        lowered = name.lower()
        if required_tokens and not all(token in lowered for token in required_tokens):
            continue
        if excluded_tokens and any(token in lowered for token in excluded_tokens):
            continue
        idx = _enumish_to_index(_call_or_value(owner, name), name_map)
        if idx is not None:
            return idx
    return None


def _get_season_content_candidate(season_service):
    for name in (
        "season_content",
        "_season_content",
        "current_season_content",
        "get_season_content",
        "get_current_season_content",
    ):
        value = _call_or_value(season_service, name)
        if value is not None:
            return value
    return None


def _extract_season_segment_pair():
    services = _get_services_module()
    if services is None:
        return None

    season_fn = getattr(services, "season_service", None)
    if season_fn is None:
        return None
    try:
        season_service = season_fn()
    except Exception:
        return None
    if season_service is None:
        return None

    # Prefer the public SeasonsService API first.
    season_value = None
    segment_value = None

    for attr in ("season",):
        season_value = _call_or_value(season_service, attr)
        if season_value is not None:
            break
    if season_value is None:
        for method_name in ("get_season",):
            fn = getattr(season_service, method_name, None)
            if callable(fn):
                try:
                    season_value = fn()
                except Exception:
                    season_value = None
                if season_value is not None:
                    break

    for attr in ("season_segment",):
        segment_value = _call_or_value(season_service, attr)
        if segment_value is not None:
            break
    if segment_value is None:
        for method_name in ("get_season_segment",):
            fn = getattr(season_service, method_name, None)
            if callable(fn):
                try:
                    segment_value = fn()
                except Exception:
                    segment_value = None
                if segment_value is not None:
                    break

    # TS4 builds may expose a combined method instead of season_segment.
    pair = _extract_pair_from_season_service_combined(season_service)
    if pair is not None:
        return pair

    pair = _season_pair_via_game_enums(season_value, segment_value)
    if pair is not None:
        return pair

    season_idx = _enumish_to_index(season_value, _SEASON_NAME_TO_INDEX)
    segment_idx = _enumish_to_index(segment_value, _SEGMENT_NAME_TO_INDEX)
    if season_idx is not None and segment_idx is not None:
        return (int(season_idx) % 4, int(segment_idx) % 3)

    season_content = _get_season_content_candidate(season_service)

    season_idx = None
    for owner in (season_service, season_content):
        if owner is None:
            continue
        for attr in ("season", "current_season", "_season"):
            season_idx = _enumish_to_index(_call_or_value(owner, attr), _SEASON_NAME_TO_INDEX)
            if season_idx is not None:
                break
        if season_idx is None:
            for method_name in ("get_season", "get_current_season"):
                season_idx = _enumish_to_index(
                    _call_or_value(owner, method_name),
                    _SEASON_NAME_TO_INDEX,
                )
                if season_idx is not None:
                    break
        if season_idx is not None:
            break
        season_idx = _find_enumish_index_on_owner(
            owner,
            _SEASON_NAME_TO_INDEX,
            required_tokens=("season",),
            excluded_tokens=("segment", "length", "day", "days", "time", "weather"),
        )
        if season_idx is not None:
            break

    segment_idx = None
    for owner in (season_service, season_content):
        if owner is None:
            continue
        for attr in (
            "season_segment",
            "current_season_segment",
            "_season_segment",
            "segment",
            "current_segment",
            "_segment",
        ):
            segment_idx = _enumish_to_index(
                _call_or_value(owner, attr),
                _SEGMENT_NAME_TO_INDEX,
            )
            if segment_idx is not None:
                break
        if segment_idx is None:
            for method_name in (
                "get_season_segment",
                "get_current_season_segment",
                "get_segment",
                "get_current_segment",
            ):
                for args in _candidate_time_args():
                    segment_idx = _enumish_to_index(
                        _safe_call_method(owner, method_name, *args),
                        _SEGMENT_NAME_TO_INDEX,
                    )
                    if segment_idx is not None:
                        break
                if segment_idx is not None:
                    break
        if segment_idx is not None:
            break
        segment_idx = _find_enumish_index_on_owner(
            owner,
            _SEGMENT_NAME_TO_INDEX,
            required_tokens=("segment",),
            excluded_tokens=("length", "remaining", "duration", "count", "num", "total"),
        )
        if segment_idx is not None:
            break

    if season_idx is None or segment_idx is None:
        return None

    season_idx = int(season_idx) % 4
    segment_idx = int(segment_idx) % 3
    return (season_idx, segment_idx)


def get_season_debug_payload():
    """Debug helper for in-game commands; returns serializable values."""
    services = _get_services_module()
    payload = {
        "ok": False,
        "season_value_repr": None,
        "season_type": None,
        "segment_value_repr": None,
        "segment_type": None,
        "service_season_and_segments_repr": None,
        "pair": None,
        "pair_index": None,
    }
    if services is None:
        payload["error"] = "services_import_failed"
        return payload

    season_fn = getattr(services, "season_service", None)
    if season_fn is None:
        payload["error"] = "season_service_missing"
        return payload

    try:
        season_service = season_fn()
    except Exception as exc:
        payload["error"] = "season_service_call_failed"
        payload["exception"] = repr(exc)
        return payload
    if season_service is None:
        payload["error"] = "season_service_none"
        return payload

    season_value = _call_or_value(season_service, "season")
    if season_value is None:
        get_season = getattr(season_service, "get_season", None)
        if callable(get_season):
            try:
                season_value = get_season()
            except Exception:
                season_value = None

    segment_value = _call_or_value(season_service, "season_segment")
    if segment_value is None:
        get_segment = getattr(season_service, "get_season_segment", None)
        if callable(get_segment):
            try:
                segment_value = get_segment()
            except Exception:
                segment_value = None

    payload["season_value_repr"] = repr(season_value)
    payload["season_type"] = type(season_value).__name__ if season_value is not None else None
    payload["segment_value_repr"] = repr(segment_value)
    payload["segment_type"] = type(segment_value).__name__ if segment_value is not None else None
    payload["service_season_and_segments_repr"] = repr(
        _safe_call_method(season_service, "get_season_and_segments")
    )
    payload["service_season_and_segments_with_now_repr"] = repr(
        _safe_call_method(season_service, "get_season_and_segments", _get_sim_now())
    )

    season_content = _get_season_content_candidate(season_service)
    payload["season_content_repr"] = repr(season_content)
    payload["season_content_type"] = (
        type(season_content).__name__ if season_content is not None else None
    )
    payload["content_get_segment_repr"] = repr(
        _safe_call_method(season_content, "get_segment")
    )
    payload["content_get_segment_with_now_repr"] = repr(
        _safe_call_method(season_content, "get_segment", _get_sim_now())
    )

    pair = _extract_pair_from_season_service_combined(season_service)
    if pair is None:
        pair = _season_pair_via_game_enums(season_value, segment_value)
    if pair is None:
        s_idx = _enumish_to_index(season_value, _SEASON_NAME_TO_INDEX)
        g_idx = _enumish_to_index(segment_value, _SEGMENT_NAME_TO_INDEX)
        if s_idx is not None and g_idx is not None:
            pair = (int(s_idx) % 4, int(g_idx) % 3)
    if pair is None:
        fallback_s_idx = None
        fallback_g_idx = None
        for owner in (season_service, season_content):
            if owner is None:
                continue
            if fallback_s_idx is None:
                fallback_s_idx = _find_enumish_index_on_owner(
                    owner,
                    _SEASON_NAME_TO_INDEX,
                    required_tokens=("season",),
                    excluded_tokens=("segment", "length", "day", "days", "time", "weather"),
                )
            if fallback_g_idx is None:
                fallback_g_idx = _find_enumish_index_on_owner(
                    owner,
                    _SEGMENT_NAME_TO_INDEX,
                    required_tokens=("segment",),
                    excluded_tokens=("length", "remaining", "duration", "count", "num", "total"),
                )
        payload["fallback_season_idx"] = fallback_s_idx
        payload["fallback_segment_idx"] = fallback_g_idx
        if fallback_s_idx is not None and fallback_g_idx is not None:
            pair = (int(fallback_s_idx) % 4, int(fallback_g_idx) % 3)

    def _names_with_token(obj, token):
        if obj is None:
            return []
        try:
            names = [n for n in dir(obj) if token in n.lower()]
        except Exception:
            return []
        names.sort()
        return names[:20]

    payload["service_segment_names"] = _names_with_token(season_service, "segment")
    payload["content_segment_names"] = _names_with_token(season_content, "segment")

    payload["pair"] = pair
    if pair is not None:
        payload["pair_index"] = (int(pair[0]) * 3) + int(pair[1])
        payload["ok"] = True
    return payload


def get_runtime_status_payload():
    time_service = _get_time_service()
    sim_now = getattr(time_service, "sim_now", None) if time_service is not None else None
    try:
        sim_now_repr = repr(sim_now)
    except Exception:
        sim_now_repr = "<unprintable>"

    return {
        "installed": bool(_RUNTIME_STATE.get("installed")),
        "initialized": bool(_RUNTIME_STATE.get("initialized")),
        "persistence_backend": str(_PERSISTENCE_BACKEND),
        "career_wrapper_patched": bool(_RUNTIME_STATE.get("career_wrapper_patched")),
        "persistence_hooks_patched": bool(_RUNTIME_STATE.get("persistence_hooks_patched")),
        "social_complete_patched": bool(_RUNTIME_STATE.get("social_complete_patched")),
        "callbacks_registered_state": bool(_RUNTIME_STATE.get("callbacks_registered")),
        "sim_alarm_started_state": bool(_RUNTIME_STATE.get("sim_alarm_started")),
        "realtime_alarm_started_state": bool(_RUNTIME_STATE.get("realtime_alarm_started")),
        "services_probe_patched": bool(_RUNTIME_STATE.get("services_probe_patched")),
        "last_install_result": dict(_RUNTIME_STATE.get("last_install_result") or {}),
        "zone_id_initialized": _RUNTIME_STATE.get("zone_id_initialized"),
        "runtime_alarm_tick_seen": bool(_RUNTIME_STATE.get("runtime_alarm_tick_seen")),
        "has_time_service": bool(time_service is not None),
        "sim_now_repr": sim_now_repr,
        "resolved_total_days_elapsed": (
            _resolve_total_days_elapsed(time_service) if time_service is not None else None
        ),
        "resolved_total_day_progress_elapsed": (
            _resolve_total_day_progress_elapsed(time_service) if time_service is not None else None
        ),
        "resolved_total_segments_elapsed": _resolve_total_segments_elapsed(),
        "sim_days_per_year_hint": _RUNTIME_STATE.get("sim_days_per_year_hint"),
        "last_instanced_sim_count": _RUNTIME_STATE.get("last_instanced_sim_count"),
        "last_ready_sim_count": _RUNTIME_STATE.get("last_ready_sim_count"),
        "warned_day_extract": bool(_RUNTIME_STATE.get("warned_day_extract")),
        "warned_segment_extract": bool(_RUNTIME_STATE.get("warned_segment_extract")),
        "planet_marker_sync_disabled": bool(_RUNTIME_STATE.get("planet_marker_sync_disabled")),
        "retrograde_marker_sync_disabled": bool(_RUNTIME_STATE.get("retrograde_marker_sync_disabled")),
        "natal_snapshot_sync_disabled": bool(_RUNTIME_STATE.get("natal_snapshot_sync_disabled")),
        "moon_return_sync_disabled": bool(_RUNTIME_STATE.get("moon_return_sync_disabled")),
        "solar_return_sync_disabled": bool(_RUNTIME_STATE.get("solar_return_sync_disabled")),
        "house_ingress_notification_disabled": bool(_RUNTIME_STATE.get("house_ingress_notification_disabled")),
        "has_sim_alarm": bool(_RUNTIME_ALARM_HANDLE is not None),
        "has_realtime_alarm": bool(_RUNTIME_REALTIME_ALARM_HANDLE is not None),
        "has_bootstrap_alarm": bool(_RUNTIME_BOOTSTRAP_ALARM_HANDLE is not None),
        "has_install_retry_alarm": bool(_RUNTIME_INSTALL_RETRY_HANDLE is not None),
        "callbacks_registered": bool(_RUNTIME_CALLBACKS_REGISTERED),
        "zone_running": bool(_is_current_zone_running()),
    }


def _resolve_total_segments_elapsed():
    pair = _extract_season_segment_pair()
    if pair is None:
        return _coerce_int(_RUNTIME_STATE.get("segment_total")) or 0

    segment_total = _RUNTIME_STATE.get("segment_total")
    if segment_total is None:
        segment_total = 0
    segment_total = int(segment_total)
    current_pair_index = (int(pair[0]) * 3) + int(pair[1])

    previous_pair = _RUNTIME_STATE.get("segment_pair")
    if previous_pair is None:
        # Align the modulo-12 position with the current season segment so:
        # Early Spring=Aries(0) ... Early Fall=Libra(6), while preserving
        # any previously accumulated year-count cycles in segment_total.
        segment_total = (segment_total - (segment_total % 12)) + current_pair_index
        _RUNTIME_STATE["segment_pair"] = pair
        _RUNTIME_STATE["segment_total"] = int(segment_total)
        return int(segment_total)

    if pair != previous_pair:
        prev_index = (int(previous_pair[0]) * 3) + int(previous_pair[1])
        curr_index = current_pair_index
        delta = (curr_index - prev_index) % 12
        if delta <= 0:
            delta = 1
        segment_total = int(segment_total) + int(delta)
        _RUNTIME_STATE["segment_total"] = segment_total
        _RUNTIME_STATE["segment_pair"] = pair

    return int(_RUNTIME_STATE.get("segment_total") or 0)


def _tick_from_time_service(time_service_obj):
    _ensure_initialized()

    ready_count_trigger = False
    startup_ready_trigger = False
    try:
        ready_count_trigger, startup_ready_trigger = _update_ready_sim_count_state()
    except Exception:
        ready_count_trigger = False
        startup_ready_trigger = False

    total_days = _resolve_total_days_elapsed(time_service_obj)
    if total_days is None:
        if not _RUNTIME_STATE["warned_day_extract"]:
            _RUNTIME_STATE["warned_day_extract"] = True
            _log_warn("Could not resolve total sim days from time_service; auto transit tick disabled.")
        return
    total_day_progress = _resolve_total_day_progress_elapsed(time_service_obj)
    if total_day_progress is None:
        total_day_progress = float(total_days)

    total_segments = _resolve_total_segments_elapsed()
    if _extract_season_segment_pair() is None and not _RUNTIME_STATE["warned_segment_extract"]:
        _RUNTIME_STATE["warned_segment_extract"] = True
        _log_warn(
            "Could not resolve season segment pair; segment-based planets will not auto-progress."
        )

    try:
        lunar_cycle_days = _resolve_lunar_cycle_days()
        sim_days_per_year = _RUNTIME_STATE.get("sim_days_per_year_hint")
        if sim_days_per_year is None:
            sim_days_per_year = _resolve_sim_days_per_year()
            if sim_days_per_year is not None:
                _RUNTIME_STATE["sim_days_per_year_hint"] = float(sim_days_per_year)
        _log_debug(
            "Runtime clock snapshot: days=%s segments=%s sim_days_per_year=%s lunar_cycle_days=%s",
            total_days,
            total_segments,
            sim_days_per_year,
            lunar_cycle_days,
        )
        moved = on_clock_snapshot(
            total_days_elapsed=int(total_days),
            total_day_progress_elapsed=float(total_day_progress),
            total_segments_elapsed=int(total_segments),
            lunar_cycle_days=lunar_cycle_days,
            sim_days_per_year=sim_days_per_year,
        )
    except Exception as exc:
        _log_warn_once(
            "on_clock_snapshot_failed",
            "Cosmic Engine on_clock_snapshot() failed during auto tick; will retry on a later tick (%s).",
            exc,
        )
        _RUNTIME_STATE["warned_day_extract"] = True
        _RUNTIME_STATE["warned_segment_extract"] = True
        return

    movement_trigger = False
    count_trigger = bool(ready_count_trigger)
    periodic_trigger = False
    try:
        if isinstance(moved, dict):
            try:
                movement_trigger = any(int(value) > 0 for value in moved.values())
            except Exception:
                movement_trigger = False

        current_instanced_count = _count_instanced_sims()
        previous_instanced_count = _RUNTIME_STATE.get("last_instanced_sim_count")
        if current_instanced_count is not None:
            if previous_instanced_count is None:
                _RUNTIME_STATE["last_instanced_sim_count"] = int(current_instanced_count)
            elif int(previous_instanced_count) != int(current_instanced_count):
                count_trigger = True
                if (
                    not _RUNTIME_STATE.get("startup_retro_catchup_completed")
                    and int(previous_instanced_count) <= 0
                    and int(current_instanced_count) > 0
                ):
                    startup_ready_trigger = True
                _RUNTIME_STATE["last_instanced_sim_count"] = int(current_instanced_count)

        tick_counter = int(_RUNTIME_STATE.get("marker_sync_tick_counter") or 0) + 1
        if tick_counter >= _MARKER_SYNC_TICK_INTERVAL:
            periodic_trigger = True
            tick_counter = 0
        _RUNTIME_STATE["marker_sync_tick_counter"] = tick_counter

    except Exception:
        _log_warn_once(
            "marker_sync_trigger_calc_failed",
            "Cosmic Engine marker sync trigger calculation failed during tick.",
        )
        movement_trigger = False
        count_trigger = False
        periodic_trigger = False
        startup_ready_trigger = False

    _log_debug(
        "Runtime tick triggers: moved=%s movement=%s count=%s periodic=%s startup_ready=%s instanced=%s ready=%s",
        moved,
        movement_trigger,
        count_trigger,
        periodic_trigger,
        startup_ready_trigger,
        _RUNTIME_STATE.get("last_instanced_sim_count"),
        _RUNTIME_STATE.get("last_ready_sim_count"),
    )

    active_mode = get_mode_lock()
    shared_runtime_enabled = _is_shared_runtime_mode(active_mode)
    retrogrades_enabled = _is_shared_runtime_mode(active_mode)
    cosmic_active = active_mode == "cosmic"
    astrocore_tick_owned = False

    if retrogrades_enabled and startup_ready_trigger:
        try:
            summary = _run_startup_retro_catchup(reason="instanced_sim_ready_catchup")
            if _is_startup_retro_catchup_complete(summary):
                _RUNTIME_STATE["startup_retro_catchup_completed"] = True
        except Exception:
            _log_warn_once(
                "retrograde_instanced_sim_ready_catchup_failed",
                "Cosmic Engine retrograde catch-up failed when instanced sims became ready; will retry later.",
            )

    if movement_trigger or count_trigger or periodic_trigger:
        try:
            astrocore_tick_summary = _ASTROCORE_RUNTIME_BRIDGE.dispatch_runtime_tick(
                total_days_elapsed=int(total_days or 0),
                total_segments_elapsed=int(total_segments or 0),
                movement_trigger=bool(movement_trigger),
                count_trigger=bool(count_trigger),
                periodic_trigger=bool(periodic_trigger),
                active_mode=active_mode,
                shared_runtime_enabled=bool(shared_runtime_enabled),
                retrogrades_enabled=bool(retrogrades_enabled),
            )
            _RUNTIME_STATE["last_astrocore_periodic_summary"] = astrocore_tick_summary
            astrocore_tick_owned = bool((astrocore_tick_summary or {}).get("ok"))
            retrograde_summary = dict(
                ((astrocore_tick_summary or {}).get("addon_summaries") or {}).get("sky_retrograde") or {}
            )
            if retrograde_summary:
                _RUNTIME_STATE["last_retrograde_runtime_summary"] = retrograde_summary
        except Exception:
            _RUNTIME_STATE["last_astrocore_periodic_summary"] = {
                "ok": False,
                "reason": "exception",
            }
            astrocore_tick_owned = False
            _log_warn_once(
                "astrocore_runtime_tick_failed",
                "AstroCore runtime tick failed during clock_tick; legacy shell scopes will run instead.",
            )

        tick_scopes = [SCOPE_RISING_BUFFS]
        if not astrocore_tick_owned:
            tick_scopes.insert(0, SCOPE_VISIBLE_SIGN_BUFFS)
        if shared_runtime_enabled:
            shared_scopes = [
                SCOPE_PLANET_HOUSES,
                SCOPE_HOUSE_INGRESS,
                SCOPE_MOON_RETURN,
                SCOPE_CRYSTAL_RESONANCE,
            ]
            if not astrocore_tick_owned:
                shared_scopes.append(SCOPE_SOLAR_RETURN)
            tick_scopes.extend(tuple(shared_scopes))
        if retrogrades_enabled and not astrocore_tick_owned:
            tick_scopes.extend((SCOPE_RETROGRADE_MARKERS, SCOPE_RETROGRADE_CONSEQUENCES))
        if cosmic_active:
            tick_scopes.append(SCOPE_NATAL_SNAPSHOTS)
        _queue_runtime_scopes(tick_scopes, reason="clock_tick")
        _flush_dirty_sync_queue(reason="clock_tick", active_mode=active_mode)

    if retrogrades_enabled and (movement_trigger or count_trigger or periodic_trigger):
        _route_retrograde_notifications(reason="clock_tick_notifications")


def _patch_method(owner, method_name, wrapper_factory):
    original = getattr(owner, method_name, None)
    if original is None:
        return False
    if getattr(original, "_cosmic_engine_patched", False):
        return False

    wrapped = wrapper_factory(original)
    try:
        wrapped._cosmic_engine_patched = True
    except Exception:
        pass
    setattr(owner, method_name, wrapped)
    return True


def _services_probe_due_now():
    min_interval = float(_SERVICES_PROBE_MIN_CHECK_REAL_SECONDS)
    if min_interval <= 0:
        return True

    try:
        now = float(time.monotonic())
    except Exception:
        return True

    last_check = _RUNTIME_STATE.get("last_services_probe_check_real_seconds")
    try:
        last_check = float(last_check) if last_check is not None else None
    except Exception:
        last_check = None

    if last_check is not None and (now - last_check) < min_interval:
        return False

    _RUNTIME_STATE["last_services_probe_check_real_seconds"] = now
    return True


def _maybe_bootstrap_from_live_services(zone_obj=None, *, reason="services_probe"):
    if _RUNTIME_STATE.get("bootstrap_probe_inflight"):
        return False
    if not _services_probe_due_now():
        return False

    if zone_obj is None:
        zone_obj = _get_current_zone()
    if not _zone_is_running(zone_obj):
        return False

    _RUNTIME_STATE["bootstrap_probe_inflight"] = True
    try:
        if _RUNTIME_STATE.get("initialized"):
            last_tick_real_seconds = _RUNTIME_STATE.get("last_runtime_tick_real_seconds")
            try:
                last_tick_real_seconds = (
                    float(last_tick_real_seconds) if last_tick_real_seconds is not None else None
                )
            except Exception:
                last_tick_real_seconds = None

            try:
                now = float(time.monotonic())
            except Exception:
                now = None

            runtime_stale = bool(
                now is None
                or last_tick_real_seconds is None
                or (now - last_tick_real_seconds) >= float(_SERVICES_PROBE_RECONCILE_STALE_SECONDS)
            )
            startup_incomplete = not bool(_RUNTIME_STATE.get("startup_retro_catchup_completed"))
            if not runtime_stale and not startup_incomplete:
                return True

            live_context_reason = None
            if runtime_stale or startup_incomplete:
                live_context_reason = _get_live_context_reconcile_reason()
            if not runtime_stale and live_context_reason is None:
                return True

            reconcile_suffix = live_context_reason or "stale_runtime"
            _log_debug(
                "Cosmic Engine live-services reconcile probe fired (%s -> %s).",
                reason,
                reconcile_suffix,
            )
            _ensure_runtime_retry_surfaces()
            _perform_runtime_tick(
                zone_obj=zone_obj,
                reason="{0}_{1}".format(reason, reconcile_suffix),
            )
            return True

        _log_debug("Cosmic Engine live-services bootstrap probe fired (%s).", reason)
        _start_runtime_alarm()
        _start_runtime_realtime_alarm()
        _perform_runtime_tick(zone_obj=zone_obj, reason=reason)
        if not _RUNTIME_STATE.get("startup_retro_catchup_completed"):
            _schedule_runtime_retro_reassert()
        _ensure_runtime_bootstrap_alarm()
        _cancel_runtime_install_retry_alarm()
        return bool(_RUNTIME_STATE.get("initialized"))
    except Exception:
        _log_warn_once(
            "live_services_bootstrap_probe_failed_{0}".format(reason),
            "Cosmic Engine live-services bootstrap probe failed during %s.",
            reason,
        )
        return False
    finally:
        _RUNTIME_STATE["bootstrap_probe_inflight"] = False


def _register_services_probe_hooks():
    if not _SERVICES_PROBE_HOOKS_ENABLED:
        _RUNTIME_STATE["services_probe_patched"] = False
        return False

    services = _get_services_module()
    if services is None:
        return False

    patched_any = False

    if hasattr(services, "time_service"):
        def _wrap_time_service(original):
            def _wrapped(*args, **kwargs):
                value = original(*args, **kwargs)
                try:
                    if value is not None:
                        _maybe_bootstrap_from_live_services(reason="services.time_service")
                except Exception:
                    pass
                return value

            return _wrapped

        try:
            patched_any = _patch_method(services, "time_service", _wrap_time_service) or patched_any
        except Exception:
            patched_any = patched_any

    _RUNTIME_STATE["services_probe_patched"] = bool(
        _RUNTIME_STATE.get("services_probe_patched") or patched_any
    )
    return patched_any


def _nudge_services_probe():
    services = _get_services_module()
    if services is None:
        return False

    touched_any = False

    current_zone = getattr(services, "current_zone", None)
    if callable(current_zone):
        try:
            current_zone()
            touched_any = True
        except Exception:
            pass

    time_service = getattr(services, "time_service", None)
    if callable(time_service):
        try:
            time_service()
            touched_any = True
        except Exception:
            pass

    return touched_any


def _safe_object_debug_name(value):
    if value is None:
        return None
    for attr in ("__name__", "name"):
        try:
            named = getattr(value, attr, None)
        except Exception:
            named = None
        if named:
            return str(named)
    try:
        return value.__class__.__name__
    except Exception:
        return None


def _career_debug_payload(career_obj):
    payload = {}
    if career_obj is None:
        return payload
    for attr in (
        "guid64",
        "guid",
        "career_uid",
        "career_id",
        "_career_uid",
        "_career_id",
    ):
        try:
            value = getattr(career_obj, attr, None)
        except Exception:
            value = None
        if value is not None:
            payload[attr] = value
    for attr in (
        "display_name",
        "career_name",
        "name",
    ):
        try:
            value = getattr(career_obj, attr, None)
        except Exception:
            value = None
        if value is not None:
            payload[attr] = str(value)

    try:
        track = getattr(career_obj, "current_track_tuning", None)
    except Exception:
        track = None
    payload["track_tuning"] = _safe_object_debug_name(track)

    try:
        level = getattr(career_obj, "current_level_tuning", None)
    except Exception:
        level = None
    payload["level_tuning"] = _safe_object_debug_name(level)

    return payload


def _career_populate_set_career_op_wrapper(original):
    def _wrapped(self, *args, **kwargs):
        try:
            return original(self, *args, **kwargs)
        except AttributeError as exc:
            text = str(exc)
            if "NoneType" in text and ("guid64" in text or "display_name" in text):
                _log_warn(
                    "Cosmic Engine guarded broken career op: %s payload=%s",
                    text,
                    _career_debug_payload(self),
                )
                return None
            raise

    return _wrapped


def _social_interaction_sim_info(value):
    if value is None:
        return None
    try:
        sim_info = getattr(value, "sim_info", None)
    except Exception:
        sim_info = None
    return sim_info if sim_info is not None else value


def _interaction_instance_is_social_like(interaction) -> bool:
    if interaction is None:
        return False
    class_name = ""
    module_name = ""
    try:
        class_name = str(interaction.__class__.__name__ or "").lower()
    except Exception:
        class_name = ""
    try:
        module_name = str(interaction.__class__.__module__ or "").lower()
    except Exception:
        module_name = ""
    if "social" in class_name or "social" in module_name:
        return True
    try:
        interaction_name = str(getattr(interaction, "interaction_name", "") or "").lower()
    except Exception:
        interaction_name = ""
    if "social" in interaction_name:
        return True
    try:
        affordance_name = str(getattr(interaction, "affordance", "") or "").lower()
    except Exception:
        affordance_name = ""
    if "social" in affordance_name:
        return True
    return False


def _social_complete_wrapper(original):
    def _wrapped(self, *args, **kwargs):
        result = original(self, *args, **kwargs)
        try:
            from .retrograde_effects import on_completed_interaction

            on_completed_interaction(self)
        except Exception:
            _log_exception("Failed during retrograde interaction-effect dispatch.")
        try:
            from .loot_actions import refresh_chemistry_after_completed_social

            if not _interaction_instance_is_social_like(self):
                return result
            actor_sim_info = _social_interaction_sim_info(getattr(self, "sim", None))
            target_sim_info = _social_interaction_sim_info(getattr(self, "target", None))
            refresh_chemistry_after_completed_social(
                actor_sim_info,
                target_sim_info,
                source="runtime.social_complete",
            )
        except Exception:
            _log_exception("Failed during social-complete chemistry refresh wrapper.")
        return result

    return _wrapped


def _register_social_complete_hooks():
    patched_any = False

    for module_name, class_name, method_name in _SOCIAL_COMPLETE_PATCH_TARGETS:
        try:
            owner_module = importlib.import_module(module_name)
        except Exception:
            continue

        owner = getattr(owner_module, class_name, None)
        if owner is None:
            continue

        try:
            did_patch = _patch_method(owner, method_name, _social_complete_wrapper)
        except Exception:
            did_patch = False
        patched_any = did_patch or patched_any

    _RUNTIME_STATE["social_complete_patched"] = bool(
        _RUNTIME_STATE.get("social_complete_patched") or patched_any
    )
    return patched_any


def _ensure_runtime_alarm_owner():
    global _RUNTIME_ALARM_OWNER

    if _RUNTIME_ALARM_OWNER is None:
        _RUNTIME_ALARM_OWNER = _RuntimeAlarmOwner()
    return _RUNTIME_ALARM_OWNER


def _cancel_runtime_alarm():
    global _RUNTIME_ALARM_HANDLE

    if _RUNTIME_ALARM_HANDLE is None:
        return False
    try:
        import alarms  # type: ignore

        alarms.cancel_alarm(_RUNTIME_ALARM_HANDLE)
    except Exception:
        pass
    _RUNTIME_ALARM_HANDLE = None
    return True


def _cancel_runtime_realtime_alarm():
    global _RUNTIME_REALTIME_ALARM_HANDLE

    if _RUNTIME_REALTIME_ALARM_HANDLE is None:
        return False
    try:
        import alarms  # type: ignore

        alarms.cancel_alarm(_RUNTIME_REALTIME_ALARM_HANDLE)
    except Exception:
        pass
    _RUNTIME_REALTIME_ALARM_HANDLE = None
    return True


def _cancel_runtime_bootstrap_alarm():
    global _RUNTIME_BOOTSTRAP_ALARM_HANDLE

    if _RUNTIME_BOOTSTRAP_ALARM_HANDLE is None:
        return False
    try:
        import alarms  # type: ignore

        alarms.cancel_alarm(_RUNTIME_BOOTSTRAP_ALARM_HANDLE)
    except Exception:
        pass
    _RUNTIME_BOOTSTRAP_ALARM_HANDLE = None
    return True


def _cancel_runtime_retro_reassert_alarm():
    global _RUNTIME_RETRO_REASSERT_HANDLE

    if _RUNTIME_RETRO_REASSERT_HANDLE is None:
        return False
    try:
        import alarms  # type: ignore

        alarms.cancel_alarm(_RUNTIME_RETRO_REASSERT_HANDLE)
    except Exception:
        pass
    _RUNTIME_RETRO_REASSERT_HANDLE = None
    return True


def _cancel_runtime_install_retry_alarm():
    global _RUNTIME_INSTALL_RETRY_HANDLE

    if _RUNTIME_INSTALL_RETRY_HANDLE is None:
        return False
    try:
        import alarms  # type: ignore

        alarms.cancel_alarm(_RUNTIME_INSTALL_RETRY_HANDLE)
    except Exception:
        pass
    _RUNTIME_INSTALL_RETRY_HANDLE = None
    return True

def _real_interval_from_seconds(seconds):
    seconds = max(1, int(seconds))
    try:
        import clock  # type: ignore
    except Exception:
        return None

    interval_in_real_seconds = getattr(clock, "interval_in_real_seconds", None)
    if callable(interval_in_real_seconds):
        try:
            return interval_in_real_seconds(seconds)
        except Exception:
            pass

    interval_in_real_minutes = getattr(clock, "interval_in_real_minutes", None)
    if callable(interval_in_real_minutes):
        try:
            minutes = max(1, int((seconds + 59) // 60))
            return interval_in_real_minutes(minutes)
        except Exception:
            pass

    interval_in_sim_minutes = getattr(clock, "interval_in_sim_minutes", None)
    if callable(interval_in_sim_minutes):
        try:
            minutes = max(1, int((seconds + 59) // 60))
            return interval_in_sim_minutes(minutes)
        except Exception:
            pass

    return None


def _ensure_runtime_retry_surfaces():
    started_any = False
    try:
        if _RUNTIME_ALARM_HANDLE is None:
            started_any = _start_runtime_alarm() or started_any
    except Exception:
        pass
    try:
        if _RUNTIME_REALTIME_ALARM_HANDLE is None:
            started_any = _start_runtime_realtime_alarm() or started_any
    except Exception:
        pass
    try:
        if not _RUNTIME_STATE.get("runtime_alarm_tick_seen"):
            _ensure_runtime_bootstrap_alarm()
    except Exception:
        pass
    return started_any

def _runtime_install_retry_callback(_alarm_handle):
    global _RUNTIME_INSTALL_RETRY_HANDLE
    del _alarm_handle
    _RUNTIME_INSTALL_RETRY_HANDLE = None

    callbacks_registered = bool(_RUNTIME_STATE.get("callbacks_registered"))
    if not callbacks_registered:
        try:
            callbacks_registered = _register_runtime_callbacks() or callbacks_registered
        except Exception:
            callbacks_registered = callbacks_registered
        try:
            callbacks_registered = _register_zone_manager_bootstrap_callback() or callbacks_registered
        except Exception:
            callbacks_registered = callbacks_registered
        try:
            callbacks_registered = _register_zone_bootstrap_callback() or callbacks_registered
        except Exception:
            callbacks_registered = callbacks_registered
        _RUNTIME_STATE["callbacks_registered"] = bool(callbacks_registered)

    _RUNTIME_STATE["installed"] = bool(
        _RUNTIME_STATE.get("career_wrapper_patched")
        or _RUNTIME_STATE.get("persistence_hooks_patched")
        or _RUNTIME_STATE.get("social_complete_patched")
        or callbacks_registered
    )

    if _is_current_zone_running():
        try:
            _runtime_zone_bootstrap_callback()
            return
        except Exception:
            _log_warn_once(
                "runtime_install_retry_bootstrap_failed",
                "Cosmic Engine deferred runtime bootstrap failed after zone entered running state.",
            )

    _schedule_runtime_install_retry()


def _schedule_runtime_install_retry(interval_real_seconds=_STARTUP_RETRO_REASSERT_REAL_SECONDS):
    global _RUNTIME_INSTALL_RETRY_HANDLE

    if _RUNTIME_INSTALL_RETRY_HANDLE is not None:
        return True

    try:
        import alarms  # type: ignore
    except Exception:
        return False

    add_real_time = getattr(alarms, "add_alarm_real_time", None)
    if callable(add_real_time):
        interval = _real_interval_from_seconds(interval_real_seconds)
        if interval is not None:
            try:
                _RUNTIME_INSTALL_RETRY_HANDLE = add_real_time(
                    _ensure_runtime_alarm_owner(),
                    interval,
                    _runtime_install_retry_callback,
                    repeating=False,
                )
            except Exception:
                _RUNTIME_INSTALL_RETRY_HANDLE = None
    if _RUNTIME_INSTALL_RETRY_HANDLE is None:
        try:
            import clock  # type: ignore

            _RUNTIME_INSTALL_RETRY_HANDLE = alarms.add_alarm(
                _ensure_runtime_alarm_owner(),
                clock.interval_in_sim_minutes(max(1, int((interval_real_seconds + 59) // 60))),
                _runtime_install_retry_callback,
                repeating=False,
            )
        except Exception:
            _RUNTIME_INSTALL_RETRY_HANDLE = None
            return False
    return True


def _perform_runtime_tick(zone_obj=None, reason="runtime_alarm"):
    if _RUNTIME_STATE.get("runtime_tick_inflight"):
        return False

    _RUNTIME_STATE["runtime_tick_inflight"] = True
    try:
        try:
            _ensure_initialized(zone_obj=zone_obj)
        except Exception:
            _log_exception("Failed during runtime bootstrap (%s).", reason)
            return False

        active_mode = get_mode_lock()
        retrogrades_enabled = _is_shared_runtime_mode(active_mode)
        time_service = _get_time_service()
        tick_ran = False

        if retrogrades_enabled and not _RUNTIME_STATE.get("startup_retro_catchup_completed"):
            _ensure_runtime_retry_surfaces()
            try:
                _, startup_ready_trigger = _update_ready_sim_count_state()
                if startup_ready_trigger:
                    summary = _run_startup_retro_catchup(reason="live_sim_ready_catchup")
                    if _is_startup_retro_catchup_complete(summary):
                        _RUNTIME_STATE["startup_retro_catchup_completed"] = True
                    else:
                        _maybe_schedule_startup_retro_retry(summary)
            except Exception:
                _log_warn_once(
                    "retrograde_live_sim_ready_catchup_failed",
                    "Cosmic Engine retrograde catch-up failed when live sim context became ready; will retry later.",
                )

        if time_service is not None:
            try:
                _tick_from_time_service(time_service)
                tick_ran = True
            except Exception:
                _log_warn_once(
                    "runtime_alarm_tick_failed",
                    "Cosmic Engine alarm-driven runtime tick failed; will retry on a later tick.",
                )

        if retrogrades_enabled and not _RUNTIME_STATE.get("startup_retro_catchup_completed"):
            try:
                summary = _run_startup_retro_catchup(reason="{0}_catchup".format(reason))
                if _is_startup_retro_catchup_complete(summary):
                    _RUNTIME_STATE["startup_retro_catchup_completed"] = True
                else:
                    _maybe_schedule_startup_retro_retry(summary)
            except Exception:
                _log_warn_once(
                    "retrograde_runtime_tick_catchup_failed",
                    "Cosmic Engine retrograde runtime catch-up failed during %s; will retry later.",
                    reason,
                )

        if tick_ran:
            _RUNTIME_STATE["runtime_alarm_tick_seen"] = True

        if (
            retrogrades_enabled
            and _RUNTIME_STATE.get("startup_retro_catchup_completed")
            and not tick_ran
        ):
            _queue_runtime_scopes(
                (SCOPE_RETROGRADE_MARKERS, SCOPE_RETROGRADE_CONSEQUENCES),
                reason="{0}_post".format(reason),
            )
            _flush_dirty_sync_queue(reason="{0}_post".format(reason), active_mode=active_mode)

        try:
            _RUNTIME_STATE["last_runtime_tick_real_seconds"] = float(time.monotonic())
        except Exception:
            pass

        return tick_ran or retrogrades_enabled
    finally:
        _RUNTIME_STATE["runtime_tick_inflight"] = False


def _runtime_alarm_callback(_alarm_handle):
    del _alarm_handle
    _perform_runtime_tick(reason="runtime_alarm")
    if _RUNTIME_STATE.get("runtime_alarm_tick_seen"):
        _cancel_runtime_bootstrap_alarm()


def _runtime_realtime_alarm_callback(_alarm_handle):
    del _alarm_handle
    _perform_runtime_tick(reason="runtime_realtime_alarm")
    if _RUNTIME_STATE.get("runtime_alarm_tick_seen"):
        _cancel_runtime_bootstrap_alarm()


def _runtime_bootstrap_alarm_callback(_alarm_handle):
    del _alarm_handle

    if _RUNTIME_STATE.get("runtime_alarm_tick_seen"):
        _cancel_runtime_bootstrap_alarm()
        return

    try:
        _start_runtime_alarm()
    except Exception:
        pass

    _perform_runtime_tick(reason="bootstrap_retry")

    if _RUNTIME_STATE.get("runtime_alarm_tick_seen"):
        _cancel_runtime_bootstrap_alarm()


def _runtime_retro_reassert_callback(_alarm_handle):
    global _RUNTIME_RETRO_REASSERT_HANDLE
    del _alarm_handle
    _RUNTIME_RETRO_REASSERT_HANDLE = None
    try:
        summary = _run_startup_retro_catchup(reason="zone_bootstrap_retry")
        if _is_startup_retro_catchup_complete(summary):
            _RUNTIME_STATE["startup_retro_catchup_completed"] = True
        elif (
            isinstance(summary, dict)
            and summary.get("deferred_reason") is not None
            and int(summary.get("attempt", 0)) < _STARTUP_RETRO_CATCHUP_MAX_ATTEMPTS
        ):
            _schedule_runtime_retro_reassert()
    except Exception:
        _log_warn_once(
            "retrograde_zone_bootstrap_retry_failed",
            "Cosmic Engine retrograde bootstrap retry failed; will rely on later runtime ticks.",
        )


def _schedule_runtime_retro_reassert(interval_real_seconds=_STARTUP_RETRO_REASSERT_REAL_SECONDS):
    global _RUNTIME_RETRO_REASSERT_HANDLE

    _cancel_runtime_retro_reassert_alarm()
    try:
        import alarms  # type: ignore
    except Exception:
        return False

    owner = _ensure_runtime_alarm_owner()
    handle = None
    add_real_time = getattr(alarms, "add_alarm_real_time", None)
    if callable(add_real_time):
        interval = _real_interval_from_seconds(interval_real_seconds)
        if interval is not None:
            try:
                handle = add_real_time(
                    owner,
                    interval,
                    _runtime_retro_reassert_callback,
                    repeating=False,
                )
            except Exception:
                handle = None
    if handle is None:
        try:
            import clock  # type: ignore

            handle = alarms.add_alarm(
                owner,
                clock.interval_in_sim_minutes(1),
                _runtime_retro_reassert_callback,
                repeating=False,
            )
        except Exception:
            handle = None

    _RUNTIME_RETRO_REASSERT_HANDLE = handle
    return _RUNTIME_RETRO_REASSERT_HANDLE is not None


def _start_runtime_alarm(interval_sim_minutes=_AUTO_TICK_ALARM_INTERVAL_SIM_MINUTES):
    global _RUNTIME_ALARM_HANDLE

    if _RUNTIME_ALARM_HANDLE is not None:
        return True

    try:
        import alarms  # type: ignore
        import clock  # type: ignore
    except Exception:
        return False

    owner = _ensure_runtime_alarm_owner()
    try:
        _RUNTIME_ALARM_HANDLE = alarms.add_alarm(
            owner,
            clock.interval_in_sim_minutes(max(1, int(interval_sim_minutes))),
            _runtime_alarm_callback,
            repeating=True,
        )
    except Exception:
        _RUNTIME_ALARM_HANDLE = None
        return False
    return _RUNTIME_ALARM_HANDLE is not None


def _start_runtime_realtime_alarm(interval_real_seconds=_AUTO_TICK_FALLBACK_REAL_SECONDS):
    global _RUNTIME_REALTIME_ALARM_HANDLE

    if _RUNTIME_REALTIME_ALARM_HANDLE is not None:
        return True

    try:
        import alarms  # type: ignore
    except Exception:
        return False

    add_real_time = getattr(alarms, "add_alarm_real_time", None)
    if not callable(add_real_time):
        return False

    owner = _ensure_runtime_alarm_owner()
    interval = _real_interval_from_seconds(interval_real_seconds)
    if interval is None:
        return False

    try:
        _RUNTIME_REALTIME_ALARM_HANDLE = add_real_time(
            owner,
            interval,
            _runtime_realtime_alarm_callback,
            repeating=True,
        )
    except Exception:
        _RUNTIME_REALTIME_ALARM_HANDLE = None
        return False
    return _RUNTIME_REALTIME_ALARM_HANDLE is not None


def _ensure_runtime_bootstrap_alarm(interval_real_seconds=_AUTO_TICK_BOOTSTRAP_REAL_SECONDS):
    global _RUNTIME_BOOTSTRAP_ALARM_HANDLE

    if _RUNTIME_STATE.get("runtime_alarm_tick_seen"):
        _cancel_runtime_bootstrap_alarm()
        return True
    if _RUNTIME_BOOTSTRAP_ALARM_HANDLE is not None:
        return True

    try:
        import alarms  # type: ignore
    except Exception:
        return False

    owner = _ensure_runtime_alarm_owner()
    handle = None

    add_real_time = getattr(alarms, "add_alarm_real_time", None)
    if callable(add_real_time):
        interval = _real_interval_from_seconds(interval_real_seconds)
        if interval is not None:
            try:
                handle = add_real_time(
                    owner,
                    interval,
                    _runtime_bootstrap_alarm_callback,
                    repeating=True,
                )
            except Exception:
                handle = None

    if handle is None:
        try:
            import clock  # type: ignore

            handle = alarms.add_alarm(
                owner,
                clock.interval_in_sim_minutes(max(1, int((interval_real_seconds + 59) // 60))),
                _runtime_bootstrap_alarm_callback,
                repeating=True,
            )
        except Exception:
            handle = None

    _RUNTIME_BOOTSTRAP_ALARM_HANDLE = handle
    return _RUNTIME_BOOTSTRAP_ALARM_HANDLE is not None


def _runtime_zone_bootstrap_callback(*_args, **_kwargs):
    del _args
    del _kwargs

    zone_obj = None
    services = _get_services_module()
    if services is not None:
        current_zone = getattr(services, "current_zone", None)
        if callable(current_zone):
            try:
                zone_obj = current_zone()
            except Exception:
                zone_obj = None

    _start_runtime_alarm()
    _start_runtime_realtime_alarm()
    _perform_runtime_tick(zone_obj=zone_obj, reason="zone_bootstrap")
    if not _RUNTIME_STATE.get("startup_retro_catchup_completed"):
        _schedule_runtime_retro_reassert()
    _ensure_runtime_bootstrap_alarm()
    _cancel_runtime_install_retry_alarm()


def _register_zone_manager_bootstrap_callback():
    global _RUNTIME_ZONE_MANAGER_CALLBACK_REGISTERED

    if _RUNTIME_ZONE_MANAGER_CALLBACK_REGISTERED:
        return True

    services = _get_services_module()
    if services is None:
        return False

    manager_getter = getattr(services, "get_zone_manager", None)
    if not callable(manager_getter):
        return False

    try:
        zone_manager = manager_getter()
    except Exception:
        zone_manager = None
    if zone_manager is None:
        return False

    register_callback = getattr(zone_manager, "register_zone_change_callback", None)
    if not callable(register_callback):
        return False

    try:
        register_callback(_runtime_zone_bootstrap_callback)
        _RUNTIME_ZONE_MANAGER_CALLBACK_REGISTERED = True
        return True
    except TypeError:
        try:
            register_callback(None, _runtime_zone_bootstrap_callback)
            _RUNTIME_ZONE_MANAGER_CALLBACK_REGISTERED = True
            return True
        except Exception:
            return False
    except Exception:
        return False


def _register_zone_bootstrap_callback():
    global _RUNTIME_ZONE_CALLBACK_REGISTERED

    if _RUNTIME_ZONE_CALLBACK_REGISTERED:
        return True

    services = _get_services_module()
    if services is None:
        return False

    try:
        current_zone = services.current_zone()
    except Exception:
        current_zone = None
    if current_zone is None:
        return False

    register_callback = getattr(current_zone, "register_callback", None)
    if not callable(register_callback):
        return False

    try:
        import zone as zone_module  # type: ignore
    except Exception:
        return False

    zone_state = getattr(zone_module, "ZoneState", None)
    running_state = getattr(zone_state, "RUNNING", None) if zone_state is not None else None
    if running_state is None:
        return False

    try:
        register_callback(running_state, _runtime_zone_bootstrap_callback)
        _RUNTIME_ZONE_CALLBACK_REGISTERED = True
        return True
    except TypeError:
        try:
            register_callback(_runtime_zone_bootstrap_callback, running_state)
            _RUNTIME_ZONE_CALLBACK_REGISTERED = True
            return True
        except Exception:
            return False
    except Exception:
        return False


def _register_runtime_callbacks():
    global _RUNTIME_CALLBACKS_REGISTERED

    if _RUNTIME_CALLBACKS_REGISTERED:
        return True

    try:
        import sims4.callback_utils as callback_utils  # type: ignore
    except Exception:
        return False

    callback_event = getattr(callback_utils, "CallbackEvent", None)
    add_callbacks = getattr(callback_utils, "add_callbacks", None)
    if callback_event is None or not callable(add_callbacks):
        return False

    registered_any = False
    for name in ("POST_ZONE_LOAD", "ZONE_RUNNING"):
        event_value = getattr(callback_event, name, None)
        if event_value is None:
            continue
        try:
            add_callbacks(event_value, _runtime_zone_bootstrap_callback)
            registered_any = True
        except Exception:
            continue

    _RUNTIME_CALLBACKS_REGISTERED = registered_any
    return registered_any


def _save_wrapper(original, reason):
    def _wrapped(self, *args, **kwargs):
        try:
            reason_text = str(reason or "")
            # Keep persistence writes scoped to explicit PersistenceService save
            # hooks, but honor every save path we patch. Save-and-quit and
            # scratch-slot flows do not always route through save_game_gen.
            if reason_text.startswith("persistence."):
                _persist_transit_record(reason=reason_text)
        except Exception:
            _log_exception("Failed during save wrapper (%s).", reason)
        return original(self, *args, **kwargs)

    return _wrapped


def get_persistence_backend():
    return str(_PERSISTENCE_BACKEND)


def persist_now(reason="debug.manual"):
    """Best-effort manual write for debug commands using the active save carrier."""
    try:
        return bool(_persist_transit_record(reason=reason))
    except Exception:
        _log_exception("Manual transit persist failed (%s).", reason)
        return False


def _runtime_install_surfaces_ready():
    if bool(_RUNTIME_STATE.get("initialized")):
        return True
    if bool(_RUNTIME_STATE.get("callbacks_registered")):
        return True
    if bool(_RUNTIME_STATE.get("social_complete_patched")):
        return True
    if bool(_RUNTIME_CALLBACKS_REGISTERED or _RUNTIME_ZONE_MANAGER_CALLBACK_REGISTERED or _RUNTIME_ZONE_CALLBACK_REGISTERED):
        return True
    if any(
        handle is not None
        for handle in (
            _RUNTIME_ALARM_HANDLE,
            _RUNTIME_REALTIME_ALARM_HANDLE,
            _RUNTIME_BOOTSTRAP_ALARM_HANDLE,
            _RUNTIME_INSTALL_RETRY_HANDLE,
        )
    ):
        return True
    return False


def install_runtime_hooks():
    """Install TS4 runtime wrappers (idempotent)."""
    if _RUNTIME_STATE["installed"] and _runtime_install_surfaces_ready():
        return True

    install_result = {
        "career_import_ok": False,
        "career_wrapper_patched": False,
        "persistence_hooks_patched": False,
        "social_complete_patched": False,
        "callbacks_registered": False,
        "sim_alarm_started": False,
        "realtime_alarm_started": False,
        "bootstrap_callback_ran": False,
    }

    patched_any = False

    try:
        import careers.career_base as career_base  # type: ignore
        install_result["career_import_ok"] = True

        patched_any = (
            _patch_method(
                career_base.CareerBase,
                "populate_set_career_op",
                _career_populate_set_career_op_wrapper,
            )
            or patched_any
        )
        _RUNTIME_STATE["career_wrapper_patched"] = bool(patched_any)
        install_result["career_wrapper_patched"] = bool(patched_any)
    except Exception:
        _log_exception("Failed installing career safety wrapper.")

    persistence_patched = False
    try:
        persistence_mod = None
        for mod_name in ("persistence_service", "services.persistence_service"):
            try:
                persistence_mod = importlib.import_module(mod_name)
                break
            except Exception:
                continue

        persistence_cls = getattr(persistence_mod, "PersistenceService", None) if persistence_mod else None
        if persistence_cls is not None:
            for method_name in ("save_game_gen", "save_using", "save_to_scratch_slot_gen"):
                if hasattr(persistence_cls, method_name):
                    did_patch = _patch_method(
                        persistence_cls,
                        method_name,
                        lambda original, _name=method_name: _save_wrapper(
                            original, "persistence.{0}".format(_name)
                        ),
                    )
                    persistence_patched = did_patch or persistence_patched
                    patched_any = did_patch or patched_any
        if not persistence_patched:
            _log_warn_once(
                "persistence_hooks_not_patched",
                "Cosmic Engine could not patch PersistenceService save hooks; save-wide transit persistence may be unavailable.",
            )
        _RUNTIME_STATE["persistence_hooks_patched"] = bool(persistence_patched)
        install_result["persistence_hooks_patched"] = bool(persistence_patched)
    except Exception:
        # Persistence hooks are optional for now.
        _log_warn_once(
            "persistence_hook_install_failed",
            "Cosmic Engine failed installing PersistenceService hooks; save-wide transit persistence may be unavailable.",
        )

    try:
        social_complete_patched = _register_social_complete_hooks()
    except Exception:
        social_complete_patched = False
    install_result["social_complete_patched"] = bool(
        social_complete_patched or _RUNTIME_STATE.get("social_complete_patched")
    )

    callbacks_registered = False
    try:
        callbacks_registered = _register_runtime_callbacks()
    except Exception:
        _log_warn_once(
            "runtime_callback_install_failed",
            "Cosmic Engine failed installing zone bootstrap callbacks; runtime will rely on alarm bootstrap only.",
        )
    try:
        callbacks_registered = _register_zone_manager_bootstrap_callback() or callbacks_registered
    except Exception:
        pass
    try:
        callbacks_registered = _register_zone_bootstrap_callback() or callbacks_registered
    except Exception:
        pass
    _RUNTIME_STATE["callbacks_registered"] = bool(callbacks_registered)
    install_result["callbacks_registered"] = bool(callbacks_registered)

    try:
        services_probe_patched = _register_services_probe_hooks()
    except Exception:
        services_probe_patched = False
    install_result["services_probe_patched"] = bool(services_probe_patched or _RUNTIME_STATE.get("services_probe_patched"))
    if services_probe_patched or _RUNTIME_STATE.get("services_probe_patched"):
        try:
            _nudge_services_probe()
        except Exception:
            pass

    alarm_started = False
    _RUNTIME_STATE["sim_alarm_started"] = bool(alarm_started)
    install_result["sim_alarm_started"] = bool(alarm_started)

    realtime_alarm_started = False
    _RUNTIME_STATE["realtime_alarm_started"] = bool(realtime_alarm_started)
    install_result["realtime_alarm_started"] = bool(realtime_alarm_started)

    if _is_current_zone_running():
        try:
            _runtime_zone_bootstrap_callback()
            install_result["bootstrap_callback_ran"] = True
            alarm_started = bool(_RUNTIME_ALARM_HANDLE is not None)
            realtime_alarm_started = bool(_RUNTIME_REALTIME_ALARM_HANDLE is not None)
            _RUNTIME_STATE["sim_alarm_started"] = alarm_started
            _RUNTIME_STATE["realtime_alarm_started"] = realtime_alarm_started
            install_result["sim_alarm_started"] = alarm_started
            install_result["realtime_alarm_started"] = realtime_alarm_started
        except Exception:
            _log_warn_once(
                "runtime_running_zone_bootstrap_failed",
                "Cosmic Engine runtime bootstrap failed while the current zone was already running.",
            )

    installed_any = bool(
        callbacks_registered
        or alarm_started
        or realtime_alarm_started
        or _RUNTIME_STATE.get("career_wrapper_patched")
        or _RUNTIME_STATE.get("persistence_hooks_patched")
        or _RUNTIME_STATE.get("social_complete_patched")
    )
    _RUNTIME_STATE["installed"] = installed_any
    install_result["installed"] = bool(installed_any)
    _RUNTIME_STATE["last_install_result"] = install_result
    if not _RUNTIME_STATE.get("initialized"):
        try:
            _schedule_runtime_install_retry()
        except Exception:
            pass
    if installed_any:
        _log_debug("Cosmic Engine runtime hooks installed.")
    return installed_any


def force_runtime_install_now():
    _RUNTIME_STATE["installed"] = False
    return bool(install_runtime_hooks())
