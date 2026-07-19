"""Shared Simstrology skill gate helpers for Cosmic Engine feature unlocks.

This module is intentionally non-invasive:
- no runtime hooks
- no behavior changes unless imported/called by a system

It provides one place to define the Simstrology skill tuning id and the planned
knowledge unlock thresholds for notifications/readouts/socials.
"""

from __future__ import annotations

from typing import Dict, Optional


SIMSTROLOGY_SKILL_STATISTIC_ID = 17669575907783292335

# Planned knowledge gating thresholds (see GAMEPLAY_NOTES.md).
SIMSTROLOGY_KNOWLEDGE_UNLOCK_LEVELS = {
    "rising_awareness": 1,
    "retrograde_awareness": 2,
    "chart_marker_awareness": 4,
    "chart_ruler_awareness": 4,
    "transit_awareness": 4,
    "advanced_chart_reading": 4,
    "simstrologer_career": 5,
}  # type: Dict[str, int]

_SIMSTROLOGY_SKILL_TUNING_CACHE = None


def _safe_int(value) -> Optional[int]:
    try:
        return int(value)
    except Exception:
        return None


def _coerce_skill_level_candidate(value) -> Optional[int]:
    """Return a plausible user-facing skill level (filters raw point totals)."""
    level = _safe_int(value)
    if level is None:
        return None
    # Simstrology skill is a minor skill (5 levels). Allow a little headroom for
    # runtime variance, but reject obvious raw-point totals like 100 or 7300.
    if level < 0 or level > 10:
        return None
    return int(level)


def _read_statistic_user_level(statistic) -> Optional[int]:
    """Best-effort level extraction across TS4 statistic/skill object variants."""
    if statistic is None:
        return None

    # Some tracker APIs return a raw numeric value directly.
    raw_level = _coerce_skill_level_candidate(statistic)
    if raw_level is not None:
        return raw_level

    for attr in ("level", "current_level", "_level"):
        try:
            value = getattr(statistic, attr, None)
        except Exception:
            value = None
        level = _coerce_skill_level_candidate(value)
        if level is not None:
            return level

    for fn_name in ("get_level", "get_user_value", "get_skill_level"):
        try:
            fn = getattr(statistic, fn_name, None)
        except Exception:
            fn = None
        if fn is None:
            continue
        try:
            value = fn()
        except TypeError:
            continue
        except Exception:
            continue
        level = _coerce_skill_level_candidate(value)
        if level is not None:
            return level

    return None


def _resolve_simstrology_skill_tuning():
    global _SIMSTROLOGY_SKILL_TUNING_CACHE
    if _SIMSTROLOGY_SKILL_TUNING_CACHE is not None:
        return _SIMSTROLOGY_SKILL_TUNING_CACHE

    try:
        import services  # type: ignore
        import sims4.resources  # type: ignore
    except Exception:
        return None

    try:
        manager = services.get_instance_manager(sims4.resources.Types.STATISTIC)
    except Exception:
        manager = None
    if manager is None:
        return None

    tuning = None
    for fn_name in ("get",):
        fn = getattr(manager, fn_name, None)
        if not callable(fn):
            continue
        try:
            tuning = fn(int(SIMSTROLOGY_SKILL_STATISTIC_ID))
        except Exception:
            tuning = None
        if tuning is not None:
            break

    if tuning is not None:
        _SIMSTROLOGY_SKILL_TUNING_CACHE = tuning
    return tuning


def _lookup_statistic_on_tracker(tracker, stat_id: int):
    if tracker is None:
        return None

    fallback_value = None
    stat_tuning = _resolve_simstrology_skill_tuning()
    key_candidates = [int(stat_id)]
    if stat_tuning is not None:
        key_candidates.insert(0, stat_tuning)

    for fn_name in ("get_statistic", "get_value", "get_stat"):
        try:
            fn = getattr(tracker, fn_name, None)
        except Exception:
            fn = None
        if fn is None:
            continue
        for key in key_candidates:
            for args in ((key,), (key, False)):
                try:
                    value = fn(*args)
                except TypeError:
                    continue
                except Exception:
                    continue
                if value is None:
                    continue
                # Prefer full statistic objects if available, but keep a numeric
                # fallback if that's all the runtime exposes on this tracker.
                if _coerce_skill_level_candidate(value) is not None:
                    if fallback_value is None:
                        fallback_value = value
                    continue
                return value

    return fallback_value


def get_simstrology_skill_level(sim_info) -> int:
    """Return the Simstrology skill level for a sim, defaulting to 0."""
    if sim_info is None:
        return 0

    stat_tuning = _resolve_simstrology_skill_tuning()

    # Some runtimes expose direct stat value helpers on sim_info.
    for fn_name in (
        "get_stat_value",
        "get_statistic_level",
        "get_skill_level",
        "get_user_value",
    ):
        try:
            fn = getattr(sim_info, fn_name, None)
        except Exception:
            fn = None
        if fn is None:
            continue
        key_candidates = []  # type: list
        if stat_tuning is not None:
            key_candidates.append(stat_tuning)
        key_candidates.append(int(SIMSTROLOGY_SKILL_STATISTIC_ID))

        for key in key_candidates:
            for args in ((key,), (key, False)):
                try:
                    value = fn(*args)
                except TypeError:
                    continue
                except Exception:
                    continue
                level = _coerce_skill_level_candidate(value)
                if level is not None:
                    return max(0, level)

    for tracker_attr in ("statistic_tracker", "commodity_tracker", "_statistic_tracker", "_commodity_tracker"):
        try:
            tracker = getattr(sim_info, tracker_attr, None)
        except Exception:
            tracker = None
        statistic = _lookup_statistic_on_tracker(tracker, int(SIMSTROLOGY_SKILL_STATISTIC_ID))
        level = _read_statistic_user_level(statistic)
        if level is not None:
            return max(0, int(level))

    return 0


def simstrology_skill_meets(sim_info, required_level: int) -> bool:
    try:
        target = int(required_level)
    except Exception:
        return False
    return int(get_simstrology_skill_level(sim_info)) >= max(0, target)


def simstrology_skill_unlock_level(feature_key: str, default: int = 0) -> int:
    try:
        value = SIMSTROLOGY_KNOWLEDGE_UNLOCK_LEVELS.get(str(feature_key), default)
    except Exception:
        value = default
    level = _safe_int(value)
    return max(0, int(level)) if level is not None else max(0, int(default))


def simstrology_skill_unlocks() -> Dict[str, int]:
    return {str(k): int(v) for k, v in SIMSTROLOGY_KNOWLEDGE_UNLOCK_LEVELS.items()}


def simstrology_skill_debug_payload(sim_info) -> Dict[str, object]:
    payload = {
        "ok": sim_info is not None,
        "sim_id": None,
        "sim_name": None,
        "skill_stat_id": int(SIMSTROLOGY_SKILL_STATISTIC_ID),
        "resolved_level": int(get_simstrology_skill_level(sim_info)) if sim_info is not None else 0,
        "tuning_resolved": _resolve_simstrology_skill_tuning() is not None,
        "tracker_results": [],
    }  # type: Dict[str, object]
    if sim_info is None:
        return payload

    try:
        payload["sim_id"] = int(getattr(sim_info, "sim_id", getattr(sim_info, "id", 0)) or 0)
    except Exception:
        payload["sim_id"] = str(getattr(sim_info, "sim_id", None) or getattr(sim_info, "id", None))
    try:
        payload["sim_name"] = "{0} {1}".format(getattr(sim_info, "first_name", "") or "", getattr(sim_info, "last_name", "") or "").strip()
    except Exception:
        payload["sim_name"] = None

    stat_tuning = _resolve_simstrology_skill_tuning()
    key_candidates = [("id", int(SIMSTROLOGY_SKILL_STATISTIC_ID))]
    if stat_tuning is not None:
        key_candidates.insert(0, ("tuning", stat_tuning))

    rows = []
    for tracker_attr in ("statistic_tracker", "commodity_tracker", "_statistic_tracker", "_commodity_tracker"):
        try:
            tracker = getattr(sim_info, tracker_attr, None)
        except Exception as exc:
            rows.append({"tracker": tracker_attr, "error": repr(exc)})
            continue
        if tracker is None:
            rows.append({"tracker": tracker_attr, "missing": True})
            continue
        tracker_row = {"tracker": tracker_attr, "type": type(tracker).__name__, "calls": []}
        for fn_name in ("get_statistic", "get_value", "get_stat"):
            fn = getattr(tracker, fn_name, None)
            if not callable(fn):
                tracker_row["calls"].append({"fn": fn_name, "missing": True})
                continue
            for key_kind, key in key_candidates:
                for arg_variant in ((key,), (key, False)):
                    try:
                        value = fn(*arg_variant)
                        tracker_row["calls"].append(
                            {
                                "fn": fn_name,
                                "key": key_kind,
                                "argc": len(arg_variant),
                                "value_type": type(value).__name__ if value is not None else None,
                                "value_int": _safe_int(value),
                                "level_guess": _read_statistic_user_level(value),
                            }
                        )
                    except TypeError:
                        continue
                    except Exception as exc:
                        tracker_row["calls"].append(
                            {"fn": fn_name, "key": key_kind, "argc": len(arg_variant), "error": repr(exc)}
                        )
        rows.append(tracker_row)
    payload["tracker_results"] = rows
    return payload
