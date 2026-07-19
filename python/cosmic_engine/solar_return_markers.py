"""Solar return marker sync for instanced sims.

First pass behavior:
- uses natal Sun sign hidden markers (`PlumAntics_CosmicEngineNatal_<Sign>SunHidden`)
- applies one hidden return marker when current Sun sign == natal Sun sign
- return marker trait is a hidden state marker only
- optional active-sim start/end notifications on marker changes
"""

from __future__ import annotations

from typing import Dict, Iterable, Optional

from .loot_actions import _trait_guid64, _trait_name
from .planet_house_markers import (
    _equipped_traits_with_ids,
    _get_active_sim_info,
    _get_trait_instance_manager,
    _iter_instanced_sim_infos,
    _iter_manager_trait_tunings,
    _show_notification,
    _sim_id,
    _trait_tracker_add_trait,
    _trait_tracker_remove_trait,
)
from .transit_core import SIGNS
from .transit_service import CosmicTransitService, get_global_transit_service


_NATAL_PREFIX = "PlumAntics_CosmicEngineNatal_"
_NATAL_SUN_SUFFIX = "SunHidden"
_RETURN_PREFIX = "PlumAntics_CosmicEngineReturns_"
_RETURN_SUN_SUFFIX = "SunReturnHidden"
_SIGN_TO_INDEX = {sign: idx for idx, sign in enumerate(SIGNS)}


_MARKER_CACHE = {
    "initialized": False,
    "return_trait_by_sign_index": {},  # type: Dict[int, object]
    "return_trait_id_by_sign_index": {},  # type: Dict[int, int]
    "return_candidate_ids": set(),  # type: set
}


def _parse_natal_sun_sign_name(trait_name: str) -> Optional[int]:
    if not trait_name:
        return None
    text = str(trait_name)
    if not text.startswith(_NATAL_PREFIX):
        return None
    if "House" in text or not text.endswith(_NATAL_SUN_SUFFIX):
        return None
    sign_name = text[len(_NATAL_PREFIX) : -len(_NATAL_SUN_SUFFIX)]
    sign_index = _SIGN_TO_INDEX.get(sign_name)
    return int(sign_index) if sign_index is not None else None


def _parse_return_sun_marker_name(trait_name: str) -> Optional[int]:
    if not trait_name:
        return None
    text = str(trait_name)
    if not text.startswith(_RETURN_PREFIX):
        return None
    if "House" in text or not text.endswith(_RETURN_SUN_SUFFIX):
        return None
    sign_name = text[len(_RETURN_PREFIX) : -len(_RETURN_SUN_SUFFIX)]
    sign_index = _SIGN_TO_INDEX.get(sign_name)
    return int(sign_index) if sign_index is not None else None


def _rebuild_marker_cache() -> Dict[str, object]:
    return_trait_by_sign_index: Dict[int, object] = {}
    return_trait_id_by_sign_index: Dict[int, int] = {}
    return_candidate_ids: set = set()

    for trait in _iter_manager_trait_tunings(_get_trait_instance_manager()):
        sign_index = _parse_return_sun_marker_name(_trait_name(trait))
        if sign_index is None:
            continue
        tid = _trait_guid64(trait)
        if tid is None:
            continue
        return_trait_by_sign_index.setdefault(int(sign_index), trait)
        return_trait_id_by_sign_index.setdefault(int(sign_index), int(tid))
        return_candidate_ids.add(int(tid))

    _MARKER_CACHE["initialized"] = True
    _MARKER_CACHE["return_trait_by_sign_index"] = return_trait_by_sign_index
    _MARKER_CACHE["return_trait_id_by_sign_index"] = return_trait_id_by_sign_index
    _MARKER_CACHE["return_candidate_ids"] = return_candidate_ids
    return _MARKER_CACHE


def _marker_cache() -> Dict[str, object]:
    if not _MARKER_CACHE.get("initialized"):
        return _rebuild_marker_cache()
    return _MARKER_CACHE


def reset_solar_return_marker_cache() -> None:
    _MARKER_CACHE["initialized"] = False
    _MARKER_CACHE["return_trait_by_sign_index"] = {}
    _MARKER_CACHE["return_trait_id_by_sign_index"] = {}
    _MARKER_CACHE["return_candidate_ids"] = set()


def _equipped_natal_sun_sign_index(equipped_traits_with_ids: Iterable[tuple]) -> Optional[int]:
    found = None
    for equipped_trait, _equipped_tid in equipped_traits_with_ids:
        sign_index = _parse_natal_sun_sign_name(_trait_name(equipped_trait))
        if sign_index is None:
            continue
        found = int(sign_index)
        break
    return found


def sync_zone_solar_return_markers(
    *,
    transit_service: Optional[CosmicTransitService] = None,
    refresh_marker_cache: bool = False,
    show_notifications: bool = True,
    sim_infos: Optional[Iterable[object]] = None,
) -> Dict[str, int]:
    if refresh_marker_cache:
        reset_solar_return_marker_cache()
    cache = _marker_cache()
    return_trait_by_sign_index = cache.get("return_trait_by_sign_index", {})
    return_trait_id_by_sign_index = cache.get("return_trait_id_by_sign_index", {})
    return_candidate_ids = cache.get("return_candidate_ids", set())

    summary = {
        "sims_seen": 0,
        "sims_with_natal_sun": 0,
        "sims_changed": 0,
        "traits_added": 0,
        "traits_removed": 0,
        "return_events": 0,
        "return_notifications_shown": 0,
        "available_marker_defs": len(return_trait_by_sign_index)
        if isinstance(return_trait_by_sign_index, dict)
        else 0,
    }
    if not isinstance(return_trait_by_sign_index, dict) or len(return_trait_by_sign_index) < 12:
        return summary

    service = transit_service or get_global_transit_service()
    current_sun_sign = int(service.state.sign_index_by_body.get("Sun", 0)) % 12
    active_sim_id = _sim_id(_get_active_sim_info()) if show_notifications else None

    target_sim_infos = tuple(_iter_instanced_sim_infos()) if sim_infos is None else tuple(sim_infos)

    for sim_info in target_sim_infos:
        summary["sims_seen"] += 1
        trait_tracker = getattr(sim_info, "trait_tracker", None)
        if trait_tracker is None:
            continue

        equipped = _equipped_traits_with_ids(sim_info)
        equipped_ids = {tid for _, tid in equipped}
        natal_sun_sign = _equipped_natal_sun_sign_index(equipped)
        if natal_sun_sign is None:
            continue
        summary["sims_with_natal_sun"] += 1

        desired_sign = int(current_sun_sign) if int(natal_sun_sign) == int(current_sun_sign) else None
        desired_tid = None
        desired_trait = None
        if desired_sign is not None:
            desired_tid = return_trait_id_by_sign_index.get(int(desired_sign))
            desired_trait = return_trait_by_sign_index.get(int(desired_sign))

        changed = False
        removed_any = False
        added_any = False

        for equipped_trait, equipped_tid in equipped:
            if equipped_tid not in return_candidate_ids:
                continue
            if desired_tid is not None and int(equipped_tid) == int(desired_tid):
                continue
            if _trait_tracker_remove_trait(sim_info, trait_tracker, equipped_trait):
                summary["traits_removed"] += 1
                changed = True
                removed_any = True
                equipped_ids.discard(int(equipped_tid))

        if desired_trait is not None and desired_tid is not None and int(desired_tid) not in equipped_ids:
            if _trait_tracker_add_trait(sim_info, trait_tracker, desired_trait):
                summary["traits_added"] += 1
                changed = True
                added_any = True
                equipped_ids.add(int(desired_tid))

        if changed:
            summary["sims_changed"] += 1
            sim_id = _sim_id(sim_info)
            if active_sim_id is not None and sim_id is not None and int(active_sim_id) == int(sim_id):
                if removed_any:
                    summary["return_events"] += 1
                    if _show_notification(
                        "Solar Return Ended",
                        "Your Solar Return window has closed.",
                        owner=sim_info,
                    ):
                        summary["return_notifications_shown"] += 1
                if added_any:
                    summary["return_events"] += 1
                    sign_name = SIGNS[int(current_sun_sign) % 12]
                    if _show_notification(
                        "Solar Return Started",
                        "Solar Return active: the Sun is in your natal Sun sign ({0}).".format(sign_name),
                        owner=sim_info,
                    ):
                        summary["return_notifications_shown"] += 1

    return summary
