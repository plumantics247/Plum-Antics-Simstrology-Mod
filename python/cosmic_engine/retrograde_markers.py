"""Retrograde active marker sync for instanced sims in the active zone.

Design goals:
- Safe when retrograde marker trait XMLs do not exist yet (no-op)
- Applies/removes hidden traits based on the Python retrograde scheduler
- Keeps Python responsible for timing; hidden markers are state only
"""

from __future__ import annotations

import time
from typing import Dict, Iterable, Optional

from .dirty_sync_queue import (
    SCOPE_RETROGRADE_CONSEQUENCES,
    SCOPE_RETROGRADE_MARKERS,
    mark_scope_dirty,
)
from .loot_actions import _trait_guid64, _trait_name
from .natal_snapshot_markers import _sim_info_add_buff, _sim_info_has_buff, _sim_info_remove_buff
from .planet_house_markers import (
    _equipped_traits_with_ids,
    _get_trait_instance_manager,
    _iter_instanced_sim_infos,
    _iter_manager_trait_tunings,
    _trait_tracker_add_trait,
    _trait_tracker_remove_trait,
)
from .sim_eligibility import sim_info_is_human, sim_info_is_retrograde_eligible, sim_info_is_teen_plus
from .transit_service import CosmicTransitService, get_global_transit_service

try:
    from plumantics_big3_runtime.config_io import load_json_from_package
except Exception:  # pragma: no cover - TS4 runtime fallback
    load_json_from_package = None


_RETROGRADE_BODIES = ("Mercury", "Venus", "Mars", "Jupiter", "Saturn")
_MAX_VISIBLE_RETROGRADE_BODIES = 3
_DEFAULT_RETROGRADE_VISIBILITY_PROFILE_ID = "recommended"
_MARKER_PREFIX_HINTS = ("PlumAntics_CosmicEngine",)

_MARKER_CACHE = {
    "initialized": False,
    "available_by_body": {},  # type: Dict[str, object]
    "candidate_ids_by_body": {},  # type: Dict[str, set]
}

_EXPRESSION_CACHE = {
    "initialized": False,
    "base_by_body": {},  # type: Dict[str, object]
    "intense_by_body": {},  # type: Dict[str, object]
    "sun_trait_id_to_ruler_body": {},  # type: Dict[int, str]
}

_RETROGRADE_BODY_NAME_MAP = {
    "MERCURY": "Mercury",
    "VENUS": "Venus",
    "MARS": "Mars",
    "JUPITER": "Jupiter",
    "SATURN": "Saturn",
}

_RELATED_MOOD_IDS_BY_RETROGRADE_BODY = {
    "Mercury": {
        14645,  # Stressed
        12007408306322509544,  # Anxious / Panicked
        9307149080924141964,  # Concerned / Worried
        13462015975732492314,  # Confused
        12804992432920066260,  # Indecisive
        15435392828079855046,  # Neurotic
        12277182702334031605,  # Scared
        15247843764430021480,  # Shocked
    },
    "Venus": {
        14646,  # Uncomfortable
        14270534356023240913,  # Disgusted
        11986540994083714246,  # In Pain
    },
    "Mars": {
        10729101171116214446,  # Annoyed
        14632,  # Angry
        10615865970650664919,  # Bitter
        17702429368596500571,  # Frustrated
        13731302549822629728,  # Jealous
        9615123671955616519,  # Resentful
        14743011960414179192,  # Vengeful
        18005805515317705470,  # Suspicious
        13311754828264219826,  # Reproachful
    },
    "Jupiter": {
        14644,  # Dazed
        3027807324045670738,  # Distracted
        18318069077024219952,  # Conflicted
        12984624083398897387,  # Nostalgic
        17998589746303365631,  # Tired
        16016989147475615211,  # Lazy
    },
    "Saturn": {
        14639,  # Focused
        15799275429558895056,  # Determined
        13289050976871245414,  # Productive
        9986929074150603838,  # Fascinated
    },
}

_TRADITIONAL_SUN_RULER_BY_SIGN = {
    "ARIES": "Mars",
    "TAURUS": "Venus",
    "GEMINI": "Mercury",
    "CANCER": None,
    "LEO": None,
    "VIRGO": "Mercury",
    "LIBRA": "Venus",
    "SCORPIO": "Mars",
    "SAGITTARIUS": "Jupiter",
    "CAPRICORN": "Saturn",
    "AQUARIUS": "Saturn",
    "PISCES": "Jupiter",
}

_RETROGRADE_ADD_LOOT_ID_BY_BODY = {
    "Mercury": 11800000000000000002,
    "Venus": 11800000000000000003,
    "Mars": 11800000000000000004,
    "Jupiter": 11800000000000000005,
    "Saturn": 11800000000000000006,
}
_RETROGRADE_REMOVE_LOOT_ID_BY_BODY = {
    "Mercury": 11800000000000000012,
    "Venus": 11800000000000000013,
    "Mars": 11800000000000000014,
    "Jupiter": 11800000000000000015,
    "Saturn": 11800000000000000016,
}
_RETROGRADE_ADD_INTENSE_LOOT_ID_BY_BODY = {
    "Mercury": 11800000000000000007,
    "Venus": 11800000000000000008,
    "Mars": 11800000000000000009,
    "Jupiter": 11800000000000000010,
    "Saturn": 11800000000000000011,
}
_TRAIT_REHYDRATE_DEBOUNCE_SECONDS = 2.0
_LAST_TRAIT_REHYDRATE_BY_SIM_BODY = {}  # type: Dict[tuple[int, str], float]
_PENDING_MARKER_READD_BY_SIM_BODY = {}  # type: Dict[tuple[int, str], float]
_PENDING_REHYDRATE_ALARM_HANDLE = None
_PENDING_REHYDRATE_ALARM_OWNER = None


class _RetrogradeAlarmOwner(object):
    pass


def _normalize_retrograde_body_name(value) -> Optional[str]:
    text = str(value or "").strip()
    if not text:
        return None
    upper = text.upper()
    if upper in _RETROGRADE_BODY_NAME_MAP:
        return _RETROGRADE_BODY_NAME_MAP[upper]
    return text if text in _RETROGRADE_BODIES else None


def _get_buff_instance_manager():
    try:
        import sims4.resources  # type: ignore
        import services  # type: ignore
    except Exception:
        return None

    get_instance_manager = getattr(services, "get_instance_manager", None)
    if not callable(get_instance_manager):
        return None
    try:
        return get_instance_manager(sims4.resources.Types.BUFF)
    except Exception:
        return None


def _sim_info_is_teen_plus(sim_info) -> bool:
    return sim_info_is_teen_plus(sim_info)


def _sim_info_is_retrograde_eligible(sim_info) -> bool:
    return sim_info_is_retrograde_eligible(sim_info)


def _get_action_instance_manager():
    try:
        import sims4.resources  # type: ignore
        import services  # type: ignore
    except Exception:
        return None

    get_instance_manager = getattr(services, "get_instance_manager", None)
    if not callable(get_instance_manager):
        return None
    try:
        return get_instance_manager(sims4.resources.Types.ACTION)
    except Exception:
        return None


def _resolve_action_loot_tuning(loot_id: int):
    manager = _get_action_instance_manager()
    if manager is None:
        return None
    try:
        return manager.get(int(loot_id))
    except Exception:
        return None


def _make_single_sim_resolver(sim_info):
    try:
        from event_testing.resolver import SingleSimResolver  # type: ignore

        return SingleSimResolver(sim_info)
    except Exception:
        return None


def _run_loot_on_sim_info(sim_info, loot_id: int) -> bool:
    if sim_info is None or loot_id is None:
        return False
    tuning = _resolve_action_loot_tuning(int(loot_id))
    if tuning is None:
        return False
    resolver = _make_single_sim_resolver(sim_info)
    if resolver is None:
        return False
    for method_name in (
        "apply_to_resolver",
        "apply_to_resolver_and_get_result",
        "apply_to_single_resolver",
    ):
        method = getattr(tuning, method_name, None)
        if not callable(method):
            continue
        try:
            method(resolver)
            return True
        except Exception:
            continue
    return False


def _load_retrograde_buff_id_registry() -> Dict[str, Dict[str, int]]:
    if load_json_from_package is None:
        return {}
    try:
        payload = load_json_from_package("plumantics_big3_runtime", "data/ids.registry.json")
    except Exception:
        return {}
    if not isinstance(payload, dict):
        return {}
    return payload


def _rebuild_expression_cache() -> Dict[str, object]:
    manager = _get_buff_instance_manager()
    registry = _load_retrograde_buff_id_registry()
    base_by_body: Dict[str, object] = {}
    intense_by_body: Dict[str, object] = {}
    sun_trait_id_to_ruler_body: Dict[int, str] = {}

    if manager is not None:
        base_ids = registry.get("retrograde_buffs", {})
        if isinstance(base_ids, dict):
            for body, buff_id in base_ids.items():
                body_name = _normalize_retrograde_body_name(body)
                if body_name is None:
                    continue
                try:
                    buff = manager.get(int(buff_id))
                except Exception:
                    buff = None
                if buff is not None:
                    base_by_body[body_name] = buff

        intense_ids = registry.get("retrograde_buffs_intense", {})
        if isinstance(intense_ids, dict):
            for body, buff_id in intense_ids.items():
                body_name = _normalize_retrograde_body_name(body)
                if body_name is None:
                    continue
                try:
                    buff = manager.get(int(buff_id))
                except Exception:
                    buff = None
                if buff is not None:
                    intense_by_body[body_name] = buff

        sun_trait_ids = registry.get("sun_traits", {})
        if isinstance(sun_trait_ids, dict):
            for sign_name, trait_id in sun_trait_ids.items():
                ruler_body = _TRADITIONAL_SUN_RULER_BY_SIGN.get(str(sign_name or "").strip().upper())
                if not ruler_body:
                    continue
                try:
                    sun_trait_id_to_ruler_body[int(trait_id)] = str(ruler_body)
                except Exception:
                    continue

    _EXPRESSION_CACHE["initialized"] = True
    _EXPRESSION_CACHE["base_by_body"] = base_by_body
    _EXPRESSION_CACHE["intense_by_body"] = intense_by_body
    _EXPRESSION_CACHE["sun_trait_id_to_ruler_body"] = sun_trait_id_to_ruler_body
    return _EXPRESSION_CACHE


def _expression_cache() -> Dict[str, object]:
    if not _EXPRESSION_CACHE.get("initialized"):
        return _rebuild_expression_cache()
    return _EXPRESSION_CACHE


def reset_retrograde_expression_cache() -> None:
    _EXPRESSION_CACHE["initialized"] = False
    _EXPRESSION_CACHE["base_by_body"] = {}
    _EXPRESSION_CACHE["intense_by_body"] = {}
    _EXPRESSION_CACHE["sun_trait_id_to_ruler_body"] = {}


def _ruling_retrograde_body_for_sim(sim_info, *, sun_trait_id_to_ruler_body: Dict[int, str]) -> Optional[str]:
    if sim_info is None or not isinstance(sun_trait_id_to_ruler_body, dict) or not sun_trait_id_to_ruler_body:
        return None
    for _, trait_id in _equipped_traits_with_ids(sim_info):
        try:
            body = sun_trait_id_to_ruler_body.get(int(trait_id))
        except Exception:
            body = None
        if body:
            return str(body)
    return None


def _parse_retrograde_marker_name(trait_name: str) -> Optional[str]:
    if not trait_name:
        return None
    text = str(trait_name)
    if not any(prefix in text for prefix in _MARKER_PREFIX_HINTS):
        return None
    if "Retrograde" not in text or "Active" not in text or "Hidden" not in text:
        return None

    for body in _RETROGRADE_BODIES:
        token = "{0}Retrograde".format(body)
        if token in text:
            return body
    return None


def _rebuild_marker_cache() -> Dict[str, object]:
    available_by_body: Dict[str, object] = {}
    candidate_ids_by_body: Dict[str, set] = {body: set() for body in _RETROGRADE_BODIES}

    for trait in _iter_manager_trait_tunings(_get_trait_instance_manager()):
        body = _parse_retrograde_marker_name(_trait_name(trait))
        if body is None:
            continue
        trait_id = _trait_guid64(trait)
        if trait_id is None:
            continue
        available_by_body.setdefault(body, trait)
        candidate_ids_by_body.setdefault(body, set()).add(int(trait_id))

    _MARKER_CACHE["initialized"] = True
    _MARKER_CACHE["available_by_body"] = available_by_body
    _MARKER_CACHE["candidate_ids_by_body"] = candidate_ids_by_body
    return _MARKER_CACHE


def _marker_cache() -> Dict[str, object]:
    if not _MARKER_CACHE.get("initialized"):
        return _rebuild_marker_cache()
    return _MARKER_CACHE


def reset_retrograde_marker_cache() -> None:
    _MARKER_CACHE["initialized"] = False
    _MARKER_CACHE["available_by_body"] = {}
    _MARKER_CACHE["candidate_ids_by_body"] = {}
    reset_retrograde_expression_cache()


def _sim_id(sim_info) -> Optional[int]:
    if sim_info is None:
        return None
    for attr in ("sim_id", "id", "guid64", "sim_guid"):
        value = getattr(sim_info, attr, None)
        if value is None:
            continue
        try:
            return int(value)
        except Exception:
            continue
    return None


def _should_rehydrate_marker(sim_info, body: str) -> bool:
    sim_id = _sim_id(sim_info)
    if sim_id is None:
        return False
    key = (int(sim_id), str(body))
    now = time.time()
    last = _LAST_TRAIT_REHYDRATE_BY_SIM_BODY.get(key)
    if last is not None and (now - float(last)) < _TRAIT_REHYDRATE_DEBOUNCE_SECONDS:
        return False
    _LAST_TRAIT_REHYDRATE_BY_SIM_BODY[key] = now
    return True


def _refresh_retrograde_marker_trait(
    sim_info,
    trait_tracker,
    body: str,
    available_by_body,
    candidate_ids_by_body,
) -> bool:
    if (
        sim_info is None
        or trait_tracker is None
        or not isinstance(available_by_body, dict)
        or not isinstance(candidate_ids_by_body, dict)
    ):
        return False
    trait = available_by_body.get(body)
    if trait is None:
        return False
    removed = False
    candidate_ids = candidate_ids_by_body.get(body) or set()
    for equipped_trait, equipped_tid in _equipped_traits_with_ids(sim_info):
        if equipped_tid not in candidate_ids:
            continue
        removed = _trait_tracker_remove_trait(sim_info, trait_tracker, equipped_trait)
        if removed:
            break
    added = _trait_tracker_add_trait(sim_info, trait_tracker, trait)
    return bool(removed and added)


def _queue_marker_readd(sim_info, body: str, delay_seconds: float = 0.25) -> bool:
    sim_id = _sim_id(sim_info)
    if sim_id is None:
        return False
    _PENDING_MARKER_READD_BY_SIM_BODY[(int(sim_id), str(body))] = time.time() + float(delay_seconds)
    _schedule_pending_rehydrate_sync(delay_seconds=max(0.25, float(delay_seconds)))
    return True


def _has_pending_marker_readd(sim_info, body: str) -> bool:
    sim_id = _sim_id(sim_info)
    if sim_id is None:
        return False
    return (int(sim_id), str(body)) in _PENDING_MARKER_READD_BY_SIM_BODY


def _clear_pending_marker_readds_for_sim(sim_info) -> int:
    sim_id = _sim_id(sim_info)
    if sim_id is None:
        return 0
    removed = 0
    for body in _RETROGRADE_BODIES:
        key = (int(sim_id), str(body))
        if key in _PENDING_MARKER_READD_BY_SIM_BODY:
            _PENDING_MARKER_READD_BY_SIM_BODY.pop(key, None)
            removed += 1
    return removed


def _apply_pending_marker_readds(
    sim_info,
    trait_tracker,
    desired_by_body,
    desired_id_by_body,
    equipped_ids,
) -> int:
    sim_id = _sim_id(sim_info)
    if sim_id is None or sim_info is None or trait_tracker is None:
        return 0

    now = time.time()
    applied = 0
    for body in _RETROGRADE_BODIES:
        key = (int(sim_id), str(body))
        ready_at = _PENDING_MARKER_READD_BY_SIM_BODY.get(key)
        if ready_at is None or now < float(ready_at):
            continue
        desired_trait = desired_by_body.get(body) if isinstance(desired_by_body, dict) else None
        desired_tid = desired_id_by_body.get(body) if isinstance(desired_id_by_body, dict) else None
        if desired_trait is None or desired_tid is None:
            _PENDING_MARKER_READD_BY_SIM_BODY.pop(key, None)
            continue
        if desired_tid in equipped_ids:
            _PENDING_MARKER_READD_BY_SIM_BODY.pop(key, None)
            continue
        if _trait_tracker_add_trait(sim_info, trait_tracker, desired_trait):
            equipped_ids.add(desired_tid)
            applied += 1
            _PENDING_MARKER_READD_BY_SIM_BODY.pop(key, None)
    return applied


def _remove_equipped_marker_trait(sim_info, trait_tracker, body: str, candidate_ids_by_body) -> bool:
    if sim_info is None or trait_tracker is None or not isinstance(candidate_ids_by_body, dict):
        return False
    candidate_ids = candidate_ids_by_body.get(body) or set()
    for equipped_trait, equipped_tid in _equipped_traits_with_ids(sim_info):
        if equipped_tid not in candidate_ids:
            continue
        return _trait_tracker_remove_trait(sim_info, trait_tracker, equipped_trait)
    return False


def _ensure_retrograde_alarm_owner():
    global _PENDING_REHYDRATE_ALARM_OWNER
    if _PENDING_REHYDRATE_ALARM_OWNER is None:
        _PENDING_REHYDRATE_ALARM_OWNER = _RetrogradeAlarmOwner()
    return _PENDING_REHYDRATE_ALARM_OWNER


def _real_interval_from_seconds(seconds: float):
    try:
        import clock  # type: ignore
    except Exception:
        return None

    interval_in_real_seconds = getattr(clock, "interval_in_real_seconds", None)
    if callable(interval_in_real_seconds):
        try:
            return interval_in_real_seconds(seconds)
        except Exception:
            return None
    return None


def _pending_rehydrate_alarm_callback(_alarm_handle):
    global _PENDING_REHYDRATE_ALARM_HANDLE
    _PENDING_REHYDRATE_ALARM_HANDLE = None
    try:
        mark_scope_dirty(
            (SCOPE_RETROGRADE_MARKERS, SCOPE_RETROGRADE_CONSEQUENCES),
            reason="retrograde_rehydrate_alarm",
        )
    except Exception:
        pass


def _schedule_pending_rehydrate_sync(delay_seconds: float = 0.25) -> bool:
    global _PENDING_REHYDRATE_ALARM_HANDLE
    if _PENDING_REHYDRATE_ALARM_HANDLE is not None:
        return True

    try:
        import alarms  # type: ignore
    except Exception:
        return False

    add_real_time = getattr(alarms, "add_alarm_real_time", None)
    if not callable(add_real_time):
        return False

    interval = _real_interval_from_seconds(delay_seconds)
    if interval is None:
        return False

    try:
        _PENDING_REHYDRATE_ALARM_HANDLE = add_real_time(
            _ensure_retrograde_alarm_owner(),
            interval,
            _pending_rehydrate_alarm_callback,
            repeating=False,
        )
    except Exception:
        _PENDING_REHYDRATE_ALARM_HANDLE = None
        return False
    return True


def _desired_retrograde_bodies_for_sim(
    sim_info,
    active_by_body,
    *,
    sun_trait_id_to_ruler_body,
    retrograde_visibility_profile_id=_DEFAULT_RETROGRADE_VISIBILITY_PROFILE_ID,
):
    if not _sim_info_is_teen_plus(sim_info):
        return set(), set(), None
    active_bodies_in_priority_order = [
        body for body in _RETROGRADE_BODIES if bool((active_by_body or {}).get(body))
    ]
    active_bodies = set(active_bodies_in_priority_order)
    intense_body = _ruling_retrograde_body_for_sim(
        sim_info,
        sun_trait_id_to_ruler_body=sun_trait_id_to_ruler_body if isinstance(sun_trait_id_to_ruler_body, dict) else {},
    )
    normalized_profile_id = str(
        retrograde_visibility_profile_id or _DEFAULT_RETROGRADE_VISIBILITY_PROFILE_ID
    ).strip().lower()
    if normalized_profile_id == "uncapped":
        desired_intense_bodies = {intense_body} if intense_body in active_bodies else set()
        desired_base_bodies = set(active_bodies) - set(desired_intense_bodies)
        return desired_base_bodies, desired_intense_bodies, intense_body
    selected_bodies = []
    if intense_body in active_bodies:
        selected_bodies.append(intense_body)
    for body in active_bodies_in_priority_order:
        if body in selected_bodies:
            continue
        if len(selected_bodies) >= _MAX_VISIBLE_RETROGRADE_BODIES:
            break
        selected_bodies.append(body)
    selected_bodies = selected_bodies[:_MAX_VISIBLE_RETROGRADE_BODIES]
    selected_body_set = set(selected_bodies)
    desired_intense_bodies = {intense_body} if intense_body in selected_body_set else set()
    desired_base_bodies = set(selected_body_set) - set(desired_intense_bodies)
    return desired_base_bodies, desired_intense_bodies, intense_body


def _load_retrograde_visibility_profile_id() -> str:
    try:
        from .ts4_runtime_install import load_retrograde_visibility_profile
    except Exception:
        load_retrograde_visibility_profile = None

    if callable(load_retrograde_visibility_profile):
        try:
            payload = load_retrograde_visibility_profile()
            profile_id = str((payload or {}).get("profile_id") or "").strip().lower()
            if profile_id in ("recommended", "uncapped"):
                return profile_id
        except Exception:
            pass
    return _DEFAULT_RETROGRADE_VISIBILITY_PROFILE_ID


def _buff_mood_type_id(buff) -> Optional[int]:
    if buff is None:
        return None
    value = getattr(buff, "mood_type", None)
    if value is None:
        return None
    guid = getattr(value, "guid64", None)
    if guid is not None:
        try:
            return int(guid)
        except Exception:
            return None
    try:
        return int(value)
    except Exception:
        return None


def _mood_type_id(value) -> Optional[int]:
    if value is None:
        return None
    guid = getattr(value, "guid64", None)
    if guid is not None:
        try:
            return int(guid)
        except Exception:
            return None
    try:
        return int(value)
    except Exception:
        return None


def _current_mood_type_id(sim_info) -> Optional[int]:
    if sim_info is None:
        return None

    get_mood = getattr(sim_info, "get_mood", None)
    if callable(get_mood):
        try:
            mood = get_mood()
        except Exception:
            mood = None
        if mood is not None:
            return _mood_type_id(mood)

    for tracker_attr_name in ("Buffs", "buff_tracker", "_buff_tracker"):
        tracker = getattr(sim_info, tracker_attr_name, None)
        if tracker is None:
            continue
        tracker_get_mood = getattr(tracker, "get_mood", None)
        if not callable(tracker_get_mood):
            continue
        try:
            mood = tracker_get_mood()
        except Exception:
            mood = None
        if mood is not None:
            return _mood_type_id(mood)
    return None


def _allowed_mood_ids_for_retrograde_body(body: str) -> set[int]:
    body_name = str(body or "")
    allowed = _RELATED_MOOD_IDS_BY_RETROGRADE_BODY.get(body_name)
    if not allowed:
        return set()
    return {int(mood_id) for mood_id in allowed}


def _iter_active_buffs(sim_info):
    tracker_candidates = (
        getattr(sim_info, "Buffs", None),
        getattr(sim_info, "buff_tracker", None),
        getattr(sim_info, "_buff_tracker", None),
    )
    for tracker in tracker_candidates:
        if tracker is None:
            continue
        for attr_name in ("buffs", "_buffs", "active_buffs", "_active_buffs"):
            buff_collection = getattr(tracker, attr_name, None)
            if buff_collection is None:
                continue
            if isinstance(buff_collection, dict):
                iterable = tuple(buff_collection.values())
            else:
                try:
                    iterable = tuple(buff_collection)
                except TypeError:
                    continue
            for buff in iterable:
                if buff is not None:
                    yield buff
            return


def _sim_current_mood_in_allowed_set(sim_info, allowed_mood_ids) -> bool:
    current_mood_id = _current_mood_type_id(sim_info)
    if current_mood_id is None:
        return False
    normalized_allowed = {int(mood_id) for mood_id in allowed_mood_ids or ()}
    return int(current_mood_id) in normalized_allowed


def _sim_has_visible_external_mood_support(sim_info, allowed_mood_ids, excluded_buffs=()) -> bool:
    normalized_allowed = {int(mood_id) for mood_id in allowed_mood_ids or ()}
    if not normalized_allowed:
        return False
    if not _sim_current_mood_in_allowed_set(sim_info, normalized_allowed):
        return False

    excluded_ids = set()
    for buff in excluded_buffs or ():
        buff_id = getattr(buff, "guid64", None)
        if buff_id is not None:
            try:
                excluded_ids.add(int(buff_id))
            except Exception:
                pass

    for buff in _iter_active_buffs(sim_info):
        buff_type = getattr(buff, "buff_type", None) or getattr(buff, "type", None) or buff
        buff_id = getattr(buff_type, "guid64", None)
        try:
            if buff_id is not None and int(buff_id) in excluded_ids:
                continue
        except Exception:
            pass
        visible = getattr(buff, "visible", getattr(buff_type, "visible", True))
        if not visible:
            continue
        if _buff_mood_type_id(buff_type) in normalized_allowed:
            return True
    return False


def _apply_retrograde_consequences_for_sim(
    sim_info,
    *,
    desired_base_bodies,
    desired_intense_bodies,
    base_buff_by_body,
    intense_buff_by_body,
    summary,
):
    current_base_bodies = set()
    if isinstance(base_buff_by_body, dict):
        for body, buff in base_buff_by_body.items():
            if _sim_info_has_buff(sim_info, buff):
                current_base_bodies.add(str(body))

    current_intense_bodies = set()
    if isinstance(intense_buff_by_body, dict):
        for body, buff in intense_buff_by_body.items():
            if _sim_info_has_buff(sim_info, buff):
                current_intense_bodies.add(str(body))

    changed = False
    for body in _RETROGRADE_BODIES:
        base_buff = base_buff_by_body.get(body) if isinstance(base_buff_by_body, dict) else None
        intense_buff = intense_buff_by_body.get(body) if isinstance(intense_buff_by_body, dict) else None
        allowed_mood_ids = _allowed_mood_ids_for_retrograde_body(body)
        has_base = body in current_base_bodies
        has_intense = body in current_intense_bodies
        base_gate = False
        intense_gate = False
        if body in desired_base_bodies and base_buff is not None:
            base_gate = _sim_has_visible_external_mood_support(
                sim_info,
                allowed_mood_ids,
                excluded_buffs=(base_buff, intense_buff),
            )
        if body in desired_intense_bodies and intense_buff is not None:
            intense_gate = _sim_has_visible_external_mood_support(
                sim_info,
                allowed_mood_ids,
                excluded_buffs=(base_buff, intense_buff),
            )
        wants_base = body in desired_base_bodies and bool(base_gate)
        wants_intense = body in desired_intense_bodies and bool(intense_gate)
        if isinstance(summary, dict):
            summary.setdefault("mood_gated_bodies", {})[body] = {
                "allowed_mood_ids": sorted(int(mood_id) for mood_id in allowed_mood_ids),
                "base_gate": bool(base_gate),
                "intense_gate": bool(intense_gate),
            }

        if not wants_base and not wants_intense:
            if has_base or has_intense:
                loot_id = _RETROGRADE_REMOVE_LOOT_ID_BY_BODY.get(body)
                removed = False
                if loot_id is not None and _run_loot_on_sim_info(sim_info, int(loot_id)):
                    removed = True
                else:
                    if has_base and base_buff is not None:
                        removed = _sim_info_remove_buff(sim_info, base_buff) or removed
                    if has_intense and intense_buff is not None:
                        removed = _sim_info_remove_buff(sim_info, intense_buff) or removed
                if removed:
                    if has_base:
                        summary["buffs_removed"] += 1
                    if has_intense:
                        summary["intense_buffs_removed"] += 1
                    changed = True
                elif has_base or has_intense:
                    summary["dispatch_failures"] += 1
            continue

        if wants_intense:
            if has_intense and not has_base:
                continue
            remove_loot_id = _RETROGRADE_REMOVE_LOOT_ID_BY_BODY.get(body)
            if remove_loot_id is not None and (has_base or has_intense):
                removed = False
                if _run_loot_on_sim_info(sim_info, int(remove_loot_id)):
                    removed = True
                else:
                    if has_base and base_buff is not None:
                        removed = _sim_info_remove_buff(sim_info, base_buff) or removed
                    if has_intense and intense_buff is not None:
                        removed = _sim_info_remove_buff(sim_info, intense_buff) or removed
                if removed:
                    if has_base:
                        summary["buffs_removed"] += 1
                    if has_intense:
                        summary["intense_buffs_removed"] += 1
                    changed = True
            add_loot_id = _RETROGRADE_ADD_INTENSE_LOOT_ID_BY_BODY.get(body)
            added = False
            if add_loot_id is not None and _run_loot_on_sim_info(sim_info, int(add_loot_id)):
                added = True
            else:
                if intense_buff is not None and not _sim_info_has_buff(sim_info, intense_buff):
                    added = _sim_info_add_buff(sim_info, intense_buff)
            if added:
                summary["intense_buffs_added"] += 1
                changed = True
            else:
                summary["dispatch_failures"] += 1
            continue

        if wants_base:
            if has_base and not has_intense:
                continue
            remove_loot_id = _RETROGRADE_REMOVE_LOOT_ID_BY_BODY.get(body)
            if remove_loot_id is not None and has_intense:
                removed = False
                if _run_loot_on_sim_info(sim_info, int(remove_loot_id)):
                    removed = True
                else:
                    if intense_buff is not None:
                        removed = _sim_info_remove_buff(sim_info, intense_buff)
                if removed:
                    summary["intense_buffs_removed"] += 1
                    changed = True
            if not has_base or has_intense:
                add_loot_id = _RETROGRADE_ADD_LOOT_ID_BY_BODY.get(body)
                added = False
                if add_loot_id is not None and _run_loot_on_sim_info(sim_info, int(add_loot_id)):
                    added = True
                else:
                    if base_buff is not None and not _sim_info_has_buff(sim_info, base_buff):
                        added = _sim_info_add_buff(sim_info, base_buff)
                if added:
                    summary["buffs_added"] += 1
                    changed = True
                else:
                    summary["dispatch_failures"] += 1
    return changed


def _clear_retrograde_state_for_ineligible_sim(
    sim_info,
    *,
    trait_tracker,
    candidate_ids_by_body,
    base_buff_by_body,
    intense_buff_by_body,
    summary,
) -> bool:
    changed = False
    _clear_pending_marker_readds_for_sim(sim_info)
    if trait_tracker is not None and isinstance(candidate_ids_by_body, dict):
        for body in _RETROGRADE_BODIES:
            if _remove_equipped_marker_trait(sim_info, trait_tracker, body, candidate_ids_by_body):
                summary["traits_removed"] += 1
                changed = True
    if _apply_retrograde_consequences_for_sim(
        sim_info,
        desired_base_bodies=set(),
        desired_intense_bodies=set(),
        base_buff_by_body=base_buff_by_body,
        intense_buff_by_body=intense_buff_by_body,
        summary=summary,
    ):
        changed = True
    return changed


def sync_zone_retrograde_markers(
    *,
    transit_service: Optional[CosmicTransitService] = None,
    refresh_marker_cache: bool = False,
    manage_consequences: bool = True,
    sim_infos: Optional[Iterable[object]] = None,
) -> Dict[str, int]:
    """Sync retrograde active marker traits for instanced sims in the active zone."""
    if refresh_marker_cache:
        reset_retrograde_marker_cache()

    cache = _marker_cache()
    available_by_body = cache.get("available_by_body", {})
    candidate_ids_by_body = cache.get("candidate_ids_by_body", {})
    expression_cache = _expression_cache()
    base_buff_by_body = expression_cache.get("base_by_body", {})
    intense_buff_by_body = expression_cache.get("intense_by_body", {})
    sun_trait_id_to_ruler_body = expression_cache.get("sun_trait_id_to_ruler_body", {})

    # TS4 instance managers can come online after our first zone bootstrap.
    # If caches were initialized too early, allow sync to self-heal by
    # rebuilding them once managers/tunings are actually available.
    if not isinstance(available_by_body, dict) or not available_by_body:
        reset_retrograde_marker_cache()
        cache = _marker_cache()
        available_by_body = cache.get("available_by_body", {})
        candidate_ids_by_body = cache.get("candidate_ids_by_body", {})
        expression_cache = _expression_cache()
        base_buff_by_body = expression_cache.get("base_by_body", {})
        intense_buff_by_body = expression_cache.get("intense_by_body", {})
        sun_trait_id_to_ruler_body = expression_cache.get("sun_trait_id_to_ruler_body", {})

    if isinstance(available_by_body, dict) and available_by_body:
        missing_base_buffs = not isinstance(base_buff_by_body, dict) or not base_buff_by_body
        missing_intense_buffs = not isinstance(intense_buff_by_body, dict) or not intense_buff_by_body
        if missing_base_buffs or missing_intense_buffs:
            reset_retrograde_expression_cache()
            expression_cache = _expression_cache()
            base_buff_by_body = expression_cache.get("base_by_body", {})
            intense_buff_by_body = expression_cache.get("intense_by_body", {})
            sun_trait_id_to_ruler_body = expression_cache.get("sun_trait_id_to_ruler_body", {})

    summary = {
        "sims_seen": 0,
        "sims_changed": 0,
        "traits_added": 0,
        "traits_removed": 0,
        "traits_rehydrated": 0,
        "traits_rehydrate_queued": 0,
        "buffs_added": 0,
        "buffs_removed": 0,
        "intense_buffs_added": 0,
        "intense_buffs_removed": 0,
        "non_humans_skipped": 0,
        "underage_skipped": 0,
        "available_marker_defs": len(available_by_body) if isinstance(available_by_body, dict) else 0,
        "available_retrograde_buffs": len(base_buff_by_body) if isinstance(base_buff_by_body, dict) else 0,
        "dispatch_failures": 0,
        "mood_gated_bodies": {},
    }

    if not isinstance(available_by_body, dict) or not available_by_body:
        return summary

    service = transit_service or get_global_transit_service()
    active_by_body = service.retrograde_active_by_body()
    retrograde_visibility_profile_id = _load_retrograde_visibility_profile_id()
    summary["visibility_profile_id"] = str(retrograde_visibility_profile_id)
    desired_by_body = {
        body: available_by_body[body]
        for body in _RETROGRADE_BODIES
        if bool(active_by_body.get(body)) and body in available_by_body
    }
    desired_id_by_body: Dict[str, int] = {}
    for body, trait in desired_by_body.items():
        tid = _trait_guid64(trait)
        if tid is not None:
            desired_id_by_body[body] = int(tid)

    target_sim_infos = tuple(_iter_instanced_sim_infos()) if sim_infos is None else tuple(sim_infos)

    for sim_info in target_sim_infos:
        summary["sims_seen"] += 1
        trait_tracker = getattr(sim_info, "trait_tracker", None)
        if trait_tracker is None:
            continue
        if not sim_info_is_human(sim_info):
            summary["non_humans_skipped"] += 1
            if _clear_retrograde_state_for_ineligible_sim(
                sim_info,
                trait_tracker=trait_tracker,
                candidate_ids_by_body=candidate_ids_by_body,
                base_buff_by_body=base_buff_by_body,
                intense_buff_by_body=intense_buff_by_body,
                summary=summary,
            ):
                summary["sims_changed"] += 1
            continue
        if not _sim_info_is_teen_plus(sim_info):
            summary["underage_skipped"] += 1
            if _clear_retrograde_state_for_ineligible_sim(
                sim_info,
                trait_tracker=trait_tracker,
                candidate_ids_by_body=candidate_ids_by_body,
                base_buff_by_body=base_buff_by_body,
                intense_buff_by_body=intense_buff_by_body,
                summary=summary,
            ):
                summary["sims_changed"] += 1
            continue

        equipped = _equipped_traits_with_ids(sim_info)
        equipped_ids = {tid for _, tid in equipped}
        changed = False

        for equipped_trait, equipped_tid in equipped:
            handled = False
            for body, candidate_ids in candidate_ids_by_body.items():
                if equipped_tid not in candidate_ids:
                    continue
                desired_tid = desired_id_by_body.get(body)
                if desired_tid is not None and desired_tid == equipped_tid:
                    handled = True
                    break
                if _trait_tracker_remove_trait(sim_info, trait_tracker, equipped_trait):
                    summary["traits_removed"] += 1
                    changed = True
                    equipped_ids.discard(equipped_tid)
                handled = True
                break
            if handled:
                continue

        for body, desired_trait in desired_by_body.items():
            desired_tid = desired_id_by_body.get(body)
            if desired_tid is None or desired_tid in equipped_ids:
                continue
            if _trait_tracker_add_trait(sim_info, trait_tracker, desired_trait):
                summary["traits_added"] += 1
                changed = True
                equipped_ids.add(desired_tid)

        applied_readds = _apply_pending_marker_readds(
            sim_info,
            trait_tracker,
            desired_by_body,
            desired_id_by_body,
            equipped_ids,
        )
        if applied_readds:
            summary["traits_rehydrated"] += int(applied_readds)
            changed = True

        equipped_marker_bodies = set()
        for body, candidate_ids in candidate_ids_by_body.items():
            if any(candidate_id in equipped_ids for candidate_id in candidate_ids):
                equipped_marker_bodies.add(str(body))

        # The authoritative runtime path splits marker bookkeeping from the
        # direct consequence pass, so marker rehydrate must still be able to
        # detect missing retrograde moodlets even when manage_consequences is
        # disabled. Otherwise load/travel/CAS can preserve the hidden marker
        # state but drop the visible buff layer without triggering the refresh.
        desired_base_bodies, desired_intense_bodies, intense_body = _desired_retrograde_bodies_for_sim(
            sim_info,
            active_by_body,
            sun_trait_id_to_ruler_body=sun_trait_id_to_ruler_body,
            retrograde_visibility_profile_id=retrograde_visibility_profile_id,
        )

        # Rehydrate trait-driven retrograde presentation after load/CAS by
        # briefly refreshing the hidden active marker when the marker exists
        # but its expected moodlet layer is missing. This needs to run even
        # when direct consequence dispatch is handled in a separate pass.
        for body in tuple(equipped_marker_bodies):
            wants_intense = body in desired_intense_bodies
            wants_base = body in desired_base_bodies
            if not wants_base and not wants_intense:
                continue
            base_buff = base_buff_by_body.get(body) if isinstance(base_buff_by_body, dict) else None
            intense_buff = intense_buff_by_body.get(body) if isinstance(intense_buff_by_body, dict) else None
            has_base_now = base_buff is not None and _sim_info_has_buff(sim_info, base_buff)
            has_intense_now = intense_buff is not None and _sim_info_has_buff(sim_info, intense_buff)
            needs_rehydrate = (wants_base and not has_base_now) or (wants_intense and not has_intense_now)
            if not needs_rehydrate:
                continue
            if not _should_rehydrate_marker(sim_info, body):
                continue
            if _remove_equipped_marker_trait(sim_info, trait_tracker, body, candidate_ids_by_body):
                equipped_ids = {
                    tid for _, tid in _equipped_traits_with_ids(sim_info)
                }
                if _queue_marker_readd(sim_info, body):
                    summary["traits_rehydrate_queued"] += 1
                else:
                    _refresh_retrograde_marker_trait(
                        sim_info,
                        trait_tracker,
                        body,
                        available_by_body,
                        candidate_ids_by_body,
                    )
                changed = True

        if manage_consequences:
            if _apply_retrograde_consequences_for_sim(
                sim_info,
                desired_base_bodies=desired_base_bodies,
                desired_intense_bodies=desired_intense_bodies,
                base_buff_by_body=base_buff_by_body,
                intense_buff_by_body=intense_buff_by_body,
                summary=summary,
            ):
                changed = True

        if changed:
            summary["sims_changed"] += 1

    return summary


def ensure_zone_retrograde_consequences(
    *,
    transit_service: Optional[CosmicTransitService] = None,
    reason: str = "runtime",
    sim_infos: Optional[Iterable[object]] = None,
) -> Dict[str, int]:
    service = transit_service or get_global_transit_service()
    active_by_body = service.retrograde_active_by_body()
    expression_cache = _expression_cache()
    base_buff_by_body = expression_cache.get("base_by_body", {})
    intense_buff_by_body = expression_cache.get("intense_by_body", {})
    sun_trait_id_to_ruler_body = expression_cache.get("sun_trait_id_to_ruler_body", {})

    # Startup catch-up can reach live sims before every buff tuning has been
    # hydrated into the expression cache. Rebuild once here so direct runtime
    # consequence dispatch does not silently no-op until a later debug/manual sync.
    active_retrogrades_present = any(bool((active_by_body or {}).get(body)) for body in _RETROGRADE_BODIES)
    missing_base_buffs = not isinstance(base_buff_by_body, dict) or not base_buff_by_body
    missing_intense_buffs = not isinstance(intense_buff_by_body, dict) or not intense_buff_by_body
    missing_ruler_map = (
        not isinstance(sun_trait_id_to_ruler_body, dict) or not sun_trait_id_to_ruler_body
    )
    if active_retrogrades_present and (missing_base_buffs or missing_intense_buffs or missing_ruler_map):
        reset_retrograde_expression_cache()
        expression_cache = _expression_cache()
        base_buff_by_body = expression_cache.get("base_by_body", {})
        intense_buff_by_body = expression_cache.get("intense_by_body", {})
        sun_trait_id_to_ruler_body = expression_cache.get("sun_trait_id_to_ruler_body", {})

    summary = {
        "reason": str(reason),
        "sims_seen": 0,
        "sims_changed": 0,
        "buffs_added": 0,
        "buffs_removed": 0,
        "intense_buffs_added": 0,
        "intense_buffs_removed": 0,
        "non_humans_skipped": 0,
        "underage_skipped": 0,
        "dispatch_failures": 0,
        "available_retrograde_buffs": len(base_buff_by_body) if isinstance(base_buff_by_body, dict) else 0,
        "mood_gated_bodies": {},
    }
    retrograde_visibility_profile_id = _load_retrograde_visibility_profile_id()
    summary["visibility_profile_id"] = str(retrograde_visibility_profile_id)

    target_sim_infos = tuple(_iter_instanced_sim_infos()) if sim_infos is None else tuple(sim_infos)

    for sim_info in target_sim_infos:
        summary["sims_seen"] += 1
        if not sim_info_is_human(sim_info):
            summary["non_humans_skipped"] += 1
            if _apply_retrograde_consequences_for_sim(
                sim_info,
                desired_base_bodies=set(),
                desired_intense_bodies=set(),
                base_buff_by_body=base_buff_by_body,
                intense_buff_by_body=intense_buff_by_body,
                summary=summary,
            ):
                summary["sims_changed"] += 1
            continue
        if not _sim_info_is_teen_plus(sim_info):
            summary["underage_skipped"] += 1
            if _apply_retrograde_consequences_for_sim(
                sim_info,
                desired_base_bodies=set(),
                desired_intense_bodies=set(),
                base_buff_by_body=base_buff_by_body,
                intense_buff_by_body=intense_buff_by_body,
                summary=summary,
            ):
                summary["sims_changed"] += 1
            continue
        desired_base_bodies, desired_intense_bodies, _ = _desired_retrograde_bodies_for_sim(
            sim_info,
            active_by_body,
            sun_trait_id_to_ruler_body=sun_trait_id_to_ruler_body,
            retrograde_visibility_profile_id=retrograde_visibility_profile_id,
        )
        if _apply_retrograde_consequences_for_sim(
            sim_info,
            desired_base_bodies=desired_base_bodies,
            desired_intense_bodies=desired_intense_bodies,
            base_buff_by_body=base_buff_by_body,
            intense_buff_by_body=intense_buff_by_body,
            summary=summary,
        ):
            summary["sims_changed"] += 1
    return summary


def debug_retrograde_payload_for_sim(sim_info) -> Dict[str, object]:
    payload: Dict[str, object] = {
        "ok": False,
        "sim_id": _sim_id(sim_info),
        "retrograde_eligible": _sim_info_is_retrograde_eligible(sim_info),
        "teen_plus": _sim_info_is_teen_plus(sim_info),
    }
    if sim_info is None:
        payload["reason"] = "no_sim_info"
        return payload

    trait_tracker = getattr(sim_info, "trait_tracker", None)
    payload["has_trait_tracker"] = bool(trait_tracker is not None)

    cache = _marker_cache()
    available_by_body = cache.get("available_by_body", {})
    candidate_ids_by_body = cache.get("candidate_ids_by_body", {})
    expression_cache = _expression_cache()
    base_buff_by_body = expression_cache.get("base_by_body", {})
    intense_buff_by_body = expression_cache.get("intense_by_body", {})
    sun_trait_id_to_ruler_body = expression_cache.get("sun_trait_id_to_ruler_body", {})

    service = get_global_transit_service()
    active_by_body = service.retrograde_active_by_body()
    payload["active_by_body"] = dict(active_by_body)
    payload["retrograde_visibility_profile_id"] = _load_retrograde_visibility_profile_id()

    equipped = _equipped_traits_with_ids(sim_info)
    equipped_ids = {tid for _, tid in equipped}
    equipped_marker_bodies = []
    for body, candidate_ids in candidate_ids_by_body.items():
        if any(candidate_id in equipped_ids for candidate_id in candidate_ids):
            equipped_marker_bodies.append(str(body))
    payload["equipped_marker_bodies"] = sorted(equipped_marker_bodies)

    intense_body = None
    if payload["teen_plus"]:
        intense_body = _ruling_retrograde_body_for_sim(
            sim_info,
            sun_trait_id_to_ruler_body=sun_trait_id_to_ruler_body if isinstance(sun_trait_id_to_ruler_body, dict) else {},
        )
    payload["intense_body"] = intense_body

    desired_base_bodies = []
    desired_intense_bodies = []
    if payload["teen_plus"]:
        desired_base_set, desired_intense_set, _ = _desired_retrograde_bodies_for_sim(
            sim_info,
            active_by_body,
            sun_trait_id_to_ruler_body=sun_trait_id_to_ruler_body,
            retrograde_visibility_profile_id=payload["retrograde_visibility_profile_id"],
        )
        desired_base_bodies = sorted(desired_base_set)
        desired_intense_bodies = sorted(desired_intense_set)
    payload["desired_base_bodies"] = desired_base_bodies
    payload["desired_intense_bodies"] = desired_intense_bodies

    current_base_bodies = []
    if isinstance(base_buff_by_body, dict):
        for body, buff in base_buff_by_body.items():
            if _sim_info_has_buff(sim_info, buff):
                current_base_bodies.append(str(body))
    payload["current_base_bodies"] = sorted(current_base_bodies)

    current_intense_bodies = []
    if isinstance(intense_buff_by_body, dict):
        for body, buff in intense_buff_by_body.items():
            if _sim_info_has_buff(sim_info, buff):
                current_intense_bodies.append(str(body))
    payload["current_intense_bodies"] = sorted(current_intense_bodies)

    try:
        age = getattr(sim_info, "age", None)
        age_name = getattr(age, "name", None) or str(age or "")
    except Exception:
        age_name = None
    payload["age"] = age_name
    payload["available_marker_defs"] = len(available_by_body) if isinstance(available_by_body, dict) else 0
    payload["available_retrograde_buffs"] = len(base_buff_by_body) if isinstance(base_buff_by_body, dict) else 0
    payload["ok"] = True
    return payload
