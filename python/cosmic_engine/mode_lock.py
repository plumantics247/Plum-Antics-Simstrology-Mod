"""Shared AstroSuite save-global mode lock stored in the transit save record."""

from __future__ import annotations

from typing import Dict, Optional

try:
    import services  # type: ignore
    import sims4.resources  # type: ignore
except Exception:  # pragma: no cover - local fallback
    services = None
    sims4 = None

from .transit_service import get_global_transit_service

_MODE_BIG3 = "big3"
_MODE_COSMIC = "cosmic"
_VALID_MODES = frozenset((_MODE_BIG3, _MODE_COSMIC))
_BIG3_MODE_TRAIT_ID = 810000000000009001
_COSMIC_MODE_TRAIT_ID = 810000000000009002
_LEGACY_V2_AUTO_MIGRATION_KEY = "legacy_v2_auto_migrated_households"
_OUTER_PLANETS_HOUSEHOLD_REFRESH_KEY = "outer_planets_refreshed_households"


def normalize_mode(mode) -> Optional[str]:
    text = str(mode or "").strip().lower()
    if not text or text in ("unset", "clear", "none"):
        return None
    if text in _VALID_MODES:
        return text
    return None


def _normalize_household_id(household_id) -> Optional[int]:
    try:
        value = int(household_id)
    except Exception:
        return None
    return value if value > 0 else None


def _read_payload() -> Dict[str, object]:
    return get_global_transit_service().get_mode_lock_payload()


def _write_payload(payload: Dict[str, object]) -> bool:
    try:
        get_global_transit_service().set_mode_lock_payload(payload)
        return True
    except Exception:
        return False


def get_mode_lock() -> Optional[str]:
    return normalize_mode(_read_payload().get("active_mode"))


def set_mode_lock(mode, *, source: str = "manual") -> bool:
    normalized = normalize_mode(mode)
    raw_text = str(mode or "").strip().lower()
    if normalized is None and raw_text not in ("", "unset", "clear", "none"):
        return False
    payload = _read_payload()
    payload["version"] = 1
    payload["active_mode"] = normalized
    payload["updated_by"] = str(source or "manual")
    return _write_payload(payload)


def clear_mode_lock(*, source: str = "manual") -> bool:
    payload = _read_payload()
    payload["version"] = 1
    payload["active_mode"] = None
    payload["updated_by"] = str(source or "manual")
    payload.pop("onboarding_choice", None)
    return _write_payload(payload)


def get_onboarding_choice() -> Optional[str]:
    payload = _read_payload()
    value = payload.get("onboarding_choice")
    text = str(value or "").strip()
    return text or None


def set_onboarding_choice(choice, *, source: str = "manual") -> bool:
    payload = _read_payload()
    payload["version"] = 1
    payload["onboarding_choice"] = str(choice or "").strip() or None
    payload["updated_by"] = str(source or "manual")
    return _write_payload(payload)


def has_startup_intro_been_seen() -> bool:
    payload = _read_payload()
    return bool(payload.get("startup_intro_seen"))


def mark_startup_intro_seen(*, source: str = "manual") -> bool:
    payload = _read_payload()
    payload["version"] = 1
    payload["startup_intro_seen"] = True
    payload["updated_by"] = str(source or "manual")
    return _write_payload(payload)


def get_outer_planets_refreshed_households() -> Dict[str, object]:
    payload = _read_payload()
    value = payload.get(_OUTER_PLANETS_HOUSEHOLD_REFRESH_KEY)
    return dict(value) if isinstance(value, dict) else {}


def has_household_outer_planets_refresh_run(household_id) -> bool:
    normalized_household_id = _normalize_household_id(household_id)
    if normalized_household_id is None:
        return False
    return str(int(normalized_household_id)) in get_outer_planets_refreshed_households()


def mark_household_outer_planets_refresh_run(
    household_id,
    *,
    source: str = "auto",
    refresh_summary: Optional[Dict[str, object]] = None,
) -> bool:
    normalized_household_id = _normalize_household_id(household_id)
    if normalized_household_id is None:
        return False

    payload = _read_payload()
    payload["version"] = 1
    payload["updated_by"] = str(source or "auto")
    entries = payload.get(_OUTER_PLANETS_HOUSEHOLD_REFRESH_KEY)
    if not isinstance(entries, dict):
        entries = {}

    entry = {
        "status": "completed",
        "updated_by": str(source or "auto"),
    }
    if isinstance(refresh_summary, dict):
        entry["sims_refreshed"] = int(refresh_summary.get("sims_refreshed", 0) or 0)
        entry["traits_added"] = int(refresh_summary.get("traits_added", 0) or 0)
        entry["reward_traits_added"] = int(refresh_summary.get("reward_traits_added", 0) or 0)
        entry["buffs_added"] = int(refresh_summary.get("buffs_added", 0) or 0)

    entries[str(int(normalized_household_id))] = entry
    payload[_OUTER_PLANETS_HOUSEHOLD_REFRESH_KEY] = entries
    return _write_payload(payload)


def get_legacy_v2_auto_migrated_households() -> Dict[str, object]:
    payload = _read_payload()
    value = payload.get(_LEGACY_V2_AUTO_MIGRATION_KEY)
    return dict(value) if isinstance(value, dict) else {}


def has_household_legacy_v2_auto_migration_run(household_id) -> bool:
    normalized_household_id = _normalize_household_id(household_id)
    if normalized_household_id is None:
        return False
    return str(int(normalized_household_id)) in get_legacy_v2_auto_migrated_households()


def mark_household_legacy_v2_auto_migration_run(
    household_id,
    *,
    source: str = "auto",
    candidate_summary: Optional[Dict[str, object]] = None,
    migration_summary: Optional[Dict[str, object]] = None,
) -> bool:
    normalized_household_id = _normalize_household_id(household_id)
    if normalized_household_id is None:
        return False

    payload = _read_payload()
    payload["version"] = 1
    payload["updated_by"] = str(source or "auto")
    entries = payload.get(_LEGACY_V2_AUTO_MIGRATION_KEY)
    if not isinstance(entries, dict):
        entries = {}

    entry = {
        "status": "completed",
        "updated_by": str(source or "auto"),
    }
    if isinstance(candidate_summary, dict):
        entry["visible_big3_without_capture"] = int(
            candidate_summary.get("candidate_visible_big3_without_capture", 0) or 0
        )
        entry["captured_without_legacy_incomplete"] = int(
            candidate_summary.get("candidate_captured_without_legacy_incomplete", 0) or 0
        )
    if isinstance(migration_summary, dict):
        raw_migration_summary = migration_summary.get("migration_summary")
        if isinstance(raw_migration_summary, dict):
            entry["legacy_sims_marked"] = int(raw_migration_summary.get("legacy_sims_marked", 0) or 0)
            entry["onboard_total_sims_seeded"] = int(
                raw_migration_summary.get("onboard_total_sims_seeded", 0) or 0
            )

    entries[str(int(normalized_household_id))] = entry
    payload[_LEGACY_V2_AUTO_MIGRATION_KEY] = entries
    return _write_payload(payload)


def is_big3_mode_active() -> bool:
    mode = get_mode_lock()
    return mode in (None, _MODE_BIG3)


def is_cosmic_mode_active() -> bool:
    mode = get_mode_lock()
    return mode in (None, _MODE_COSMIC)


def mode_status_payload(branch: str) -> Dict[str, object]:
    normalized_branch = normalize_mode(branch)
    active_mode = get_mode_lock()
    payload = _read_payload()
    return {
        "version": 1,
        "requested_branch": normalized_branch,
        "active_mode": active_mode,
        "is_active": active_mode in (None, normalized_branch),
        "payload_present": bool(payload),
    }


def _trait_manager():
    if services is None or sims4 is None:
        return None
    try:
        return services.get_instance_manager(sims4.resources.Types.TRAIT)
    except Exception:
        return None


def _resolve_trait(trait_id: int):
    manager = _trait_manager()
    if manager is None:
        return None
    try:
        return manager.get(int(trait_id))
    except Exception:
        return None


def _iter_sim_infos():
    if services is None:
        return ()
    try:
        manager = services.sim_info_manager()
    except Exception:
        manager = None
    if manager is None:
        return ()
    values = getattr(manager, "values", None)
    if callable(values):
        try:
            return tuple(values())
        except Exception:
            return ()
    get_all = getattr(manager, "get_all", None)
    if callable(get_all):
        try:
            return tuple(get_all())
        except Exception:
            return ()
    return ()


def _add_trait(sim_info, trait_id: int) -> bool:
    if sim_info is None:
        return False
    trait_tracker = getattr(sim_info, "trait_tracker", None)
    if trait_tracker is None:
        return False
    try:
        if hasattr(trait_tracker, "has_trait") and trait_tracker.has_trait(trait_id):
            return False
    except Exception:
        pass
    trait = _resolve_trait(trait_id)
    if trait is None:
        return False
    for owner in (trait_tracker, sim_info):
        add_fn = getattr(owner, "add_trait", None)
        if callable(add_fn):
            try:
                add_fn(trait)
                return True
            except Exception:
                continue
    return False


def _sim_has_trait(sim_info, trait_id: int) -> bool:
    if sim_info is None:
        return False
    trait_tracker = getattr(sim_info, "trait_tracker", None)
    if trait_tracker is None:
        return False
    has_trait = getattr(trait_tracker, "has_trait", None)
    if callable(has_trait):
        try:
            return bool(has_trait(int(trait_id)))
        except Exception:
            pass
    equipped = getattr(trait_tracker, "equipped_traits", None) or ()
    for candidate in equipped:
        guid = getattr(candidate, "guid64", None)
        if guid is None:
            guid = getattr(candidate, "guid", None)
        try:
            if int(guid) == int(trait_id):
                return True
        except Exception:
            continue
    return False


def _remove_trait(sim_info, trait_id: int) -> bool:
    if sim_info is None:
        return False
    trait_tracker = getattr(sim_info, "trait_tracker", None)
    if trait_tracker is None:
        return False
    trait = _resolve_trait(trait_id)
    equipped = None
    if trait is None:
        equipped = getattr(trait_tracker, "equipped_traits", None) or ()
        for candidate in equipped:
            guid = getattr(candidate, "guid64", None)
            if guid is None:
                guid = getattr(candidate, "guid", None)
            try:
                if int(guid) == int(trait_id):
                    trait = candidate
                    break
            except Exception:
                continue
    if trait is None:
        return False
    for owner in (trait_tracker, sim_info):
        remove_fn = getattr(owner, "remove_trait", None)
        if callable(remove_fn):
            try:
                remove_fn(trait)
                return True
            except Exception:
                continue
    return False


def infer_mode_lock_from_traits() -> Optional[str]:
    big3_count = 0
    cosmic_count = 0
    for sim_info in _iter_sim_infos():
        if sim_info is None:
            continue
        if _sim_has_trait(sim_info, _BIG3_MODE_TRAIT_ID):
            big3_count += 1
        if _sim_has_trait(sim_info, _COSMIC_MODE_TRAIT_ID):
            cosmic_count += 1
    if big3_count and not cosmic_count:
        return _MODE_BIG3
    if cosmic_count and not big3_count:
        return _MODE_COSMIC
    return None


def restore_mode_lock_from_traits(*, source: str = "trait_inference") -> Optional[str]:
    active_mode = get_mode_lock()
    if active_mode in (_MODE_BIG3, _MODE_COSMIC):
        return active_mode
    inferred = infer_mode_lock_from_traits()
    if inferred is None:
        return None
    payload = _read_payload()
    payload["version"] = 1
    payload["active_mode"] = inferred
    payload["updated_by"] = str(source or "trait_inference")
    if _write_payload(payload):
        return inferred
    return None


def sync_mode_lock_traits() -> Dict[str, int]:
    active_mode = get_mode_lock()
    add_trait_id = None
    remove_trait_ids = ()
    if active_mode == _MODE_BIG3:
        add_trait_id = _BIG3_MODE_TRAIT_ID
        remove_trait_ids = (_COSMIC_MODE_TRAIT_ID,)
    elif active_mode == _MODE_COSMIC:
        add_trait_id = _COSMIC_MODE_TRAIT_ID
        remove_trait_ids = (_BIG3_MODE_TRAIT_ID,)
    else:
        remove_trait_ids = (_BIG3_MODE_TRAIT_ID, _COSMIC_MODE_TRAIT_ID)

    added = 0
    removed = 0
    for sim_info in _iter_sim_infos():
        if sim_info is None:
            continue
        if add_trait_id is not None and _add_trait(sim_info, add_trait_id):
            added += 1
        for trait_id in remove_trait_ids:
            if _remove_trait(sim_info, trait_id):
                removed += 1
    return {
        "active_mode": active_mode or "",
        "added": int(added),
        "removed": int(removed),
    }
