"""Interaction-driven gameplay effects for active retrogrades.

This module intentionally stays separate from ``retrograde_markers``. Marker
traits and visible retrograde moodlets remain teen+, while these effects can
use the global transit state for safe interaction-level behavior.
"""

from __future__ import annotations

import random
import time
from typing import Callable, Dict, Optional

from .transit_service import get_global_transit_service


MERCURY_BODY = "Mercury"
VENUS_BODY = "Venus"
MARS_BODY = "Mars"
JUPITER_BODY = "Jupiter"
SATURN_BODY = "Saturn"
MERCURY_RETROGRADE_MARKER_TRAIT_ID = 2821920925
STATISTIC_BREAKAGE_ID = 16633
STATISTIC_ENERGY_ID = 16654
LTR_FRIENDSHIP_MAIN_TRACK_ID = 16650
LTR_ROMANCE_MAIN_TRACK_ID = 16651
MERCURY_OBJECT_WEAR_CHANCE = 25.0
MERCURY_OBJECT_WEAR_AMOUNT = -2.0
VENUS_NEW_CONNECTION_CHANCE = 15.0
VENUS_NEW_CONNECTION_AMOUNT = -1.0
VENUS_AWKWARD_FLIRT_CHANCE = 20.0
VENUS_AWKWARD_FLIRT_AMOUNT = -2.0
VENUS_REPAIR_AMOUNT = 1.0
MARS_STRENUOUS_EFFORT_CHANCE = 20.0
MARS_STRENUOUS_ENERGY_AMOUNT = -5.0
JUPITER_RELEARNING_ENERGY_AMOUNT = 4.0
SATURN_FOLLOW_THROUGH_ENERGY_AMOUNT = 3.0
EFFECT_NOTICE_COOLDOWN_SECONDS = 20.0

EFFECT_NOTICE_BY_PLANET = {
    "mercury": (
        "Mercury Retrograde: Technically Working",
        "The device survived another use. Whether it will survive the next one is between it and Mercury.",
    ),
    "venus": (
        "Venus Retrograde: Mixed Signals",
        "That connection had chemistry. Unfortunately, it may have been the kind that causes a small explosion.",
    ),
    "mars": (
        "Mars Retrograde: Maximum Effort, Minimum Glory",
        "That took considerably more energy than the results would suggest.",
    ),
    "jupiter": (
        "Jupiter Retrograde: Second-Time Scholar",
        "Apparently, the material made more sense after the universe assigned it as homework again.",
    ),
    "saturn": (
        "Saturn Retrograde: Responsibility Handled",
        "The task is finally complete. Saturn has reviewed the work and will withhold further criticism—for now.",
    ),
}

_INTERACTION_PROCESSED_ATTR = "_plumantics_retrograde_effects_processed"
_BREAKAGE_STATISTIC_TUNING_CACHE = None
_STATISTIC_TUNING_CACHE = {}
_RETROGRADES_ADDON_AVAILABLE_CACHE = False
_LAST_EFFECT_NOTICE_AT = {}


def _safe_getattr(owner, name, default=None):
    try:
        return getattr(owner, name, default)
    except Exception:
        return default


def _call_or_value(owner, name, default=None):
    value = _safe_getattr(owner, name, default)
    if callable(value):
        try:
            return value()
        except Exception:
            return default
    return value


def _active_retrogrades(transit_service) -> Dict[str, bool]:
    try:
        active_by_body = transit_service.retrograde_active_by_body()
    except Exception:
        return {}
    if not isinstance(active_by_body, dict):
        return {}
    return {str(body): bool(active) for body, active in active_by_body.items()}


def _interaction_internal_tokens(interaction) -> str:
    """Return non-localized class/tuning identifiers for conservative filtering."""
    parts = []
    for owner in (interaction, _safe_getattr(interaction, "affordance", None)):
        if owner is None:
            continue
        cls = _safe_getattr(owner, "__class__", None)
        for value in (
            _safe_getattr(cls, "__name__", ""),
            _safe_getattr(cls, "__module__", ""),
            _safe_getattr(owner, "__name__", ""),
            _safe_getattr(owner, "tuning_name", ""),
            _safe_getattr(owner, "name", ""),
        ):
            if value:
                parts.append(str(value).lower())
    return " ".join(parts)


def _interaction_is_object_maintenance(interaction) -> bool:
    tokens = _interaction_internal_tokens(interaction)
    return any(
        marker in tokens
        for marker in ("repair", "upgrade", "replace", "broken", "mend", "fix")
    )


def _target_is_already_broken(target) -> bool:
    for name in ("is_broken", "broken", "isBroken"):
        value = _call_or_value(target, name, None)
        if value is not None:
            return bool(value)
    return False


def _target_is_unbreakable(target) -> bool:
    direct = _call_or_value(target, "is_unbreakable", None)
    if direct is not None:
        return bool(direct)

    tag_value = None
    try:
        import tag  # type: ignore

        tag_type = _safe_getattr(tag, "Tag", None)
        tag_value = _safe_getattr(tag_type, "Func_Unbreakable_Object", None)
    except Exception:
        tag_value = None

    has_tag = _safe_getattr(target, "has_tag", None)
    if callable(has_tag) and tag_value is not None:
        try:
            if has_tag(tag_value):
                return True
        except Exception:
            pass

    for owner in (target, _safe_getattr(target, "definition", None)):
        tags = _safe_getattr(owner, "tags", ())
        try:
            if any("unbreakable" in str(value).lower() for value in tags or ()):
                return True
        except Exception:
            continue
    return False


def _resolve_breakage_statistic_tuning():
    global _BREAKAGE_STATISTIC_TUNING_CACHE
    if _BREAKAGE_STATISTIC_TUNING_CACHE is not None:
        return _BREAKAGE_STATISTIC_TUNING_CACHE

    try:
        import services  # type: ignore
        import sims4.resources  # type: ignore

        resource_types = _safe_getattr(sims4.resources, "Types", None)
        statistic_type = _safe_getattr(resource_types, "STATISTIC", None)
        get_manager = _safe_getattr(services, "get_instance_manager", None)
        manager = get_manager(statistic_type) if callable(get_manager) and statistic_type is not None else None
        get_tuning = _safe_getattr(manager, "get", None)
        tuning = get_tuning(int(STATISTIC_BREAKAGE_ID)) if callable(get_tuning) else None
    except Exception:
        tuning = None

    if tuning is not None:
        _BREAKAGE_STATISTIC_TUNING_CACHE = tuning
    return tuning


def _resolve_statistic_tuning(statistic_id: int):
    """Resolve an EA statistic only when the live game exposes it."""
    normalized_id = int(statistic_id)
    if normalized_id == int(STATISTIC_BREAKAGE_ID):
        return _resolve_breakage_statistic_tuning()
    if normalized_id in _STATISTIC_TUNING_CACHE:
        return _STATISTIC_TUNING_CACHE[normalized_id]

    try:
        import services  # type: ignore
        import sims4.resources  # type: ignore

        resource_types = _safe_getattr(sims4.resources, "Types", None)
        statistic_type = _safe_getattr(resource_types, "STATISTIC", None)
        get_manager = _safe_getattr(services, "get_instance_manager", None)
        manager = get_manager(statistic_type) if callable(get_manager) and statistic_type is not None else None
        get_tuning = _safe_getattr(manager, "get", None)
        tuning = get_tuning(normalized_id) if callable(get_tuning) else None
    except Exception:
        tuning = None

    if tuning is not None:
        _STATISTIC_TUNING_CACHE[normalized_id] = tuning
    return tuning


def retrogrades_addon_is_available() -> bool:
    """Return whether the optional Retrogrades package is loaded right now.

    The runtime archive can be installed without the optional tuning package.
    Resolve the Mercury marker trait at use time so that configuration never
    produces object wear for players who did not install Retrogrades.
    """
    global _RETROGRADES_ADDON_AVAILABLE_CACHE
    if _RETROGRADES_ADDON_AVAILABLE_CACHE:
        return True

    try:
        import services  # type: ignore
        import sims4.resources  # type: ignore

        resource_types = _safe_getattr(sims4.resources, "Types", None)
        trait_type = _safe_getattr(resource_types, "TRAIT", None)
        get_manager = _safe_getattr(services, "get_instance_manager", None)
        manager = get_manager(trait_type) if callable(get_manager) and trait_type is not None else None
        get_tuning = _safe_getattr(manager, "get", None)
        marker_trait = (
            get_tuning(int(MERCURY_RETROGRADE_MARKER_TRAIT_ID))
            if callable(get_tuning)
            else None
        )
    except Exception:
        marker_trait = None

    _RETROGRADES_ADDON_AVAILABLE_CACHE = marker_trait is not None
    return bool(_RETROGRADES_ADDON_AVAILABLE_CACHE)


def _statistic_candidates(statistic_id: int):
    candidates = [int(statistic_id)]
    tuning = _resolve_statistic_tuning(int(statistic_id))
    if tuning is not None:
        candidates.insert(0, tuning)
    return tuple(candidates)


def _find_statistic(owner, statistic_id: int):
    if owner is None:
        return None

    for statistic_owner in (owner, _safe_getattr(owner, "statistic_tracker", None), _safe_getattr(owner, "commodity_tracker", None)):
        if statistic_owner is None:
            continue
        for method_name in ("get_stat_instance", "get_statistic", "get_stat", "get_value"):
            method = _safe_getattr(statistic_owner, method_name, None)
            if not callable(method):
                continue
            for candidate in _statistic_candidates(int(statistic_id)):
                for args in ((candidate,), (candidate, False)):
                    try:
                        statistic = method(*args)
                    except TypeError:
                        continue
                    except Exception:
                        continue
                    if statistic is not None:
                        return statistic
    return None


def _find_breakage_statistic(target):
    return _find_statistic(target, STATISTIC_BREAKAGE_ID)


def _apply_breakage_wear(target, statistic, amount: float) -> bool:
    for method_name in ("add_value", "add_stat_value", "add_amount"):
        method = _safe_getattr(statistic, method_name, None)
        if not callable(method):
            continue
        try:
            method(float(amount))
            return True
        except Exception:
            continue

    for tracker_name in ("statistic_tracker", "commodity_tracker"):
        tracker = _safe_getattr(target, tracker_name, None)
        method = _safe_getattr(tracker, "add_value", None)
        if not callable(method):
            continue
        for candidate in _statistic_candidates(STATISTIC_BREAKAGE_ID):
            try:
                method(candidate, float(amount))
                return True
            except Exception:
                continue
    return False


def _mark_interaction_processed(interaction) -> bool:
    if interaction is None:
        return False
    if bool(_safe_getattr(interaction, _INTERACTION_PROCESSED_ATTR, False)):
        return False
    try:
        setattr(interaction, _INTERACTION_PROCESSED_ATTR, True)
    except Exception:
        pass
    return True


def _roll_succeeds(chance: float, random_roll_fn: Callable[[], float]) -> bool:
    try:
        roll = float(random_roll_fn())
    except Exception:
        return False
    return roll < max(0.0, min(100.0, float(chance))) / 100.0


def _mercury_object_wear(
    interaction,
    *,
    random_roll_fn: Callable[[], float],
) -> Dict[str, object]:
    summary = {
        "handled": False,
        "applied": False,
        "reason": None,
        "amount": float(MERCURY_OBJECT_WEAR_AMOUNT),
    }
    target = _safe_getattr(interaction, "target", None)
    if target is None:
        summary["reason"] = "missing_target"
        return summary
    if _interaction_is_object_maintenance(interaction):
        summary["reason"] = "maintenance_interaction"
        return summary
    if _target_is_already_broken(target):
        summary["reason"] = "already_broken"
        return summary
    if _target_is_unbreakable(target):
        summary["reason"] = "unbreakable_target"
        return summary

    statistic = _find_breakage_statistic(target)
    if statistic is None:
        summary["reason"] = "not_repairable"
        return summary
    summary["handled"] = True

    if not _roll_succeeds(MERCURY_OBJECT_WEAR_CHANCE, random_roll_fn):
        summary["reason"] = "chance_failed"
        return summary
    if not _apply_breakage_wear(target, statistic, MERCURY_OBJECT_WEAR_AMOUNT):
        summary["reason"] = "wear_apply_failed"
        return summary

    summary["applied"] = True
    summary["reason"] = "wear_applied"
    return summary


def _interaction_actor_sim_info(interaction):
    actor = _safe_getattr(interaction, "sim", None)
    return _safe_getattr(actor, "sim_info", actor)


def _interaction_target_sim_info(interaction):
    target = _safe_getattr(interaction, "target", None)
    return _safe_getattr(target, "sim_info", target)


def _sim_id_value(sim_info):
    for name in ("sim_id", "id", "sim_instance_id"):
        value = _call_or_value(sim_info, name, None)
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return None


def _sim_is_teen_plus(sim_info) -> bool:
    """Return False rather than guessing when the age API is unavailable."""
    age = _safe_getattr(sim_info, "age", None)
    try:
        from sims.sim_info_types import Age  # type: ignore

        return bool(age >= Age.TEEN)
    except Exception:
        age_name = str(age or "").lower()
        return any(marker in age_name for marker in ("teen", "youngadult", "young_adult", "adult", "elder"))


def _interaction_is_social(interaction) -> bool:
    if _interaction_target_sim_info(interaction) is None:
        return False
    tokens = _interaction_internal_tokens(interaction)
    return "social" in tokens or "mixer" in tokens


def _interaction_matches(interaction, markers) -> bool:
    tokens = _interaction_internal_tokens(interaction)
    return any(marker in tokens for marker in markers)


def _read_relationship_score(actor_sim_info, target_sim_info, track_id: int):
    target_id = _sim_id_value(target_sim_info)
    if actor_sim_info is None or target_id is None:
        return None
    for owner in (_safe_getattr(actor_sim_info, "relationship_tracker", None), actor_sim_info):
        for method_name in ("get_relationship_score", "get_relationship_value", "get_track_score"):
            method = _safe_getattr(owner, method_name, None)
            if not callable(method):
                continue
            for args, kwargs in (
                ((target_id, int(track_id)), {}),
                ((target_id,), {"track_id": int(track_id)}),
                ((target_id,), {"track": int(track_id)}),
            ):
                try:
                    value = method(*args, **kwargs)
                except Exception:
                    continue
                for attr in ("value", "score", "current_value", "relationship_score"):
                    candidate = _safe_getattr(value, attr, None)
                    if candidate is not None:
                        value = candidate
                        break
                try:
                    return float(value)
                except (TypeError, ValueError):
                    continue
    return None


def _adjust_relationship_score(actor_sim_info, target_sim_info, track_id: int, amount: float) -> bool:
    """Use only explicit EA relationship-score APIs; never create relbits."""
    target_id = _sim_id_value(target_sim_info)
    if actor_sim_info is None or target_id is None:
        return False
    for owner in (_safe_getattr(actor_sim_info, "relationship_tracker", None), actor_sim_info):
        for method_name in ("add_relationship_score", "add_relationship_value", "add_track_score"):
            method = _safe_getattr(owner, method_name, None)
            if not callable(method):
                continue
            for args, kwargs in (
                ((target_id, float(amount), int(track_id)), {}),
                ((target_id, float(amount)), {"track_id": int(track_id)}),
                ((target_id, float(amount)), {"track": int(track_id)}),
            ):
                try:
                    method(*args, **kwargs)
                    return True
                except Exception:
                    continue
    return False


def _apply_statistic_delta(owner, statistic_id: int, amount: float) -> bool:
    statistic = _find_statistic(owner, int(statistic_id))
    if statistic is None:
        return False
    return _apply_breakage_wear(owner, statistic, float(amount))


def _summary(reason, *, handled=False, applied=False, amount=None):
    summary = {"handled": bool(handled), "applied": bool(applied), "reason": str(reason)}
    if amount is not None:
        summary["amount"] = float(amount)
    return summary


def _raw_text(value: str):
    try:
        from sims4.localization import LocalizationHelperTuning  # type: ignore

        return LocalizationHelperTuning.get_raw_text(str(value))
    except Exception:
        return str(value)


def _show_effect_notice(planet: str, interaction) -> bool:
    """Show one normal Sim-faced notice for an applied retrograde effect.

    Effects can happen repeatedly during an interaction-heavy play session. The
    cooldown is deliberately per Sim and planet so that different retrogrades
    remain legible while a repeated action does not fill the notification wall.
    """
    copy = EFFECT_NOTICE_BY_PLANET.get(str(planet or "").lower())
    actor = _interaction_actor_sim_info(interaction)
    sim_id = _sim_id_value(actor)
    if copy is None or actor is None or sim_id is None:
        return False

    key = (int(sim_id), str(planet).lower())
    now = time.monotonic()
    previous = _LAST_EFFECT_NOTICE_AT.get(key)
    if previous is not None and now - float(previous) < float(EFFECT_NOTICE_COOLDOWN_SECONDS):
        return False

    try:
        from ui.ui_dialog_notification import UiDialogNotification  # type: ignore

        title, text = copy
        notification = UiDialogNotification.TunableFactory().default(
            actor,
            title=lambda *_, **__: _raw_text(title),
            text=lambda *_, **__: _raw_text(text),
        )
        notification.show_dialog()
        _LAST_EFFECT_NOTICE_AT[key] = now
        return True
    except Exception:
        return False


def _venus_relationship_reflection(interaction, *, random_roll_fn):
    actor = _interaction_actor_sim_info(interaction)
    target = _interaction_target_sim_info(interaction)
    if not _sim_is_teen_plus(actor) or not _sim_is_teen_plus(target) or not _interaction_is_social(interaction):
        return _summary("not_eligible_social")

    romance = _interaction_matches(interaction, ("romance", "romantic", "flirt", "kiss", "woohoo"))
    repair = _interaction_matches(interaction, ("apolog", "compliment", "relationship", "reconcile"))
    if repair:
        track_id = LTR_ROMANCE_MAIN_TRACK_ID if romance else LTR_FRIENDSHIP_MAIN_TRACK_ID
        applied = _adjust_relationship_score(actor, target, track_id, VENUS_REPAIR_AMOUNT)
        return _summary("repair_applied" if applied else "relationship_api_unavailable", handled=True, applied=applied, amount=VENUS_REPAIR_AMOUNT)

    track_id = LTR_ROMANCE_MAIN_TRACK_ID if romance else LTR_FRIENDSHIP_MAIN_TRACK_ID
    score = _read_relationship_score(actor, target, track_id)
    if score is None or score >= 30.0:
        return _summary("established_or_unknown_relationship")
    chance = VENUS_AWKWARD_FLIRT_CHANCE if romance else VENUS_NEW_CONNECTION_CHANCE
    amount = VENUS_AWKWARD_FLIRT_AMOUNT if romance else VENUS_NEW_CONNECTION_AMOUNT
    if not _roll_succeeds(chance, random_roll_fn):
        return _summary("chance_failed", handled=True, amount=amount)
    applied = _adjust_relationship_score(actor, target, track_id, amount)
    return _summary("connection_drag_applied" if applied else "relationship_api_unavailable", handled=True, applied=applied, amount=amount)


def _mars_strenuous_effort(interaction, *, random_roll_fn):
    if not _interaction_matches(interaction, ("fitness", "workout", "exercise", "running", "jog", "boxing", "punching", "swim", "climb", "repair", "handiness")):
        return _summary("not_strenuous")
    actor = _interaction_actor_sim_info(interaction)
    if actor is None:
        return _summary("missing_actor")
    if not _roll_succeeds(MARS_STRENUOUS_EFFORT_CHANCE, random_roll_fn):
        return _summary("chance_failed", handled=True, amount=MARS_STRENUOUS_ENERGY_AMOUNT)
    applied = _apply_statistic_delta(actor, STATISTIC_ENERGY_ID, MARS_STRENUOUS_ENERGY_AMOUNT)
    return _summary("fatigue_applied" if applied else "energy_api_unavailable", handled=True, applied=applied, amount=MARS_STRENUOUS_ENERGY_AMOUNT)


def _jupiter_relearning(interaction):
    if not _interaction_matches(interaction, ("mentor", "mentoring", "tutor", "teach", "reread", "readbook", "read_book", "skillbook")):
        return _summary("not_relearning")
    actor = _interaction_actor_sim_info(interaction)
    if not _sim_is_teen_plus(actor):
        return _summary("underage_or_missing_actor")
    applied = _apply_statistic_delta(actor, STATISTIC_ENERGY_ID, JUPITER_RELEARNING_ENERGY_AMOUNT)
    return _summary("relearning_reward_applied" if applied else "energy_api_unavailable", handled=True, applied=applied, amount=JUPITER_RELEARNING_ENERGY_AMOUNT)


def _saturn_follow_through(interaction):
    if not _interaction_matches(interaction, ("homework", "clean", "repair", "paybill", "pay_bill", "paybills")):
        return _summary("not_follow_through")
    actor = _interaction_actor_sim_info(interaction)
    if actor is None:
        return _summary("missing_actor")
    applied = _apply_statistic_delta(actor, STATISTIC_ENERGY_ID, SATURN_FOLLOW_THROUGH_ENERGY_AMOUNT)
    return _summary("follow_through_reward_applied" if applied else "energy_api_unavailable", handled=True, applied=applied, amount=SATURN_FOLLOW_THROUGH_ENERGY_AMOUNT)


def on_completed_interaction(
    interaction,
    *,
    transit_service=None,
    random_roll_fn: Optional[Callable[[], float]] = None,
    retrogrades_addon_available: Optional[bool] = None,
) -> Dict[str, object]:
    """Apply safe, one-time retrograde effects after an interaction completes."""
    if not _mark_interaction_processed(interaction):
        return {"handled": False, "applied": False, "reason": "already_processed"}

    addon_available = (
        retrogrades_addon_is_available()
        if retrogrades_addon_available is None
        else bool(retrogrades_addon_available)
    )
    if not addon_available:
        return {"handled": False, "applied": False, "reason": "retrogrades_addon_unavailable"}

    service = transit_service or get_global_transit_service()
    active_by_body = _active_retrogrades(service)
    roll = random_roll_fn or random.random
    handlers = (
        (MERCURY_BODY, "mercury", lambda: _mercury_object_wear(interaction, random_roll_fn=roll)),
        (VENUS_BODY, "venus", lambda: _venus_relationship_reflection(interaction, random_roll_fn=roll)),
        (MARS_BODY, "mars", lambda: _mars_strenuous_effort(interaction, random_roll_fn=roll)),
        (JUPITER_BODY, "jupiter", lambda: _jupiter_relearning(interaction)),
        (SATURN_BODY, "saturn", lambda: _saturn_follow_through(interaction)),
    )
    active_handlers = [(label, handler) for body, label, handler in handlers if bool(active_by_body.get(body))]
    if not active_handlers:
        return {"handled": False, "applied": False, "reason": "no_relevant_retrogrades"}

    results = {label: handler() for label, handler in active_handlers}
    notices = {
        label: _show_effect_notice(label, interaction)
        for label, result in results.items()
        if bool(result.get("applied"))
    }
    if len(results) == 1:
        result = next(iter(results.values()))
        if notices:
            result = dict(result)
            result["notification_shown"] = bool(next(iter(notices.values())))
        return result
    return {
        "handled": any(bool(result.get("handled")) for result in results.values()),
        "applied": any(bool(result.get("applied")) for result in results.values()),
        "reason": "effects_dispatched",
        "effects": results,
        "notices": notices,
    }
