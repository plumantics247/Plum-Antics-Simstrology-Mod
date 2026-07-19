"""Planet-in-house marker sync for instanced sims in the active zone.

Design goals:
- Safe when marker trait XMLs do not exist yet (no-op)
- Reuses existing rising/house marker data to compute houses
- Incremental enough for runtime use (sync on init and only when transits move)
"""

from __future__ import annotations

import logging
from typing import Dict, Iterable, List, Mapping, Optional, Tuple

from .astrology_skill_gate import simstrology_skill_meets, simstrology_skill_unlock_level
from .houses_notification_bridge import resolve_rising_sign_index_from_trait_ids
from .loot_actions import (
    _add_buff_if_missing,
    _collect_trait_ids_and_markers,
    _iter_traits_for_sim_info,
    _remove_buff_if_present,
    _trait_guid64,
    _trait_name,
)
from .outer_planets_activation import is_outer_planets_addon_active
from .sim_eligibility import sim_info_is_human, sim_info_is_non_human, sim_info_species_name
from .transit_core import (
    ALL_BODY_NAMES,
    BODY_NAMES,
    HOUSES,
    OPTIONAL_OUTER_BODY_NAMES,
    RULE_BY_BODY,
    SEASON_SEGMENTS_PER_YEAR,
    SIGNS,
    build_house_sign_map_for_rising,
    resolve_house_sign_map_from_marker_ids,
)
from .transit_service import CosmicTransitService, get_global_transit_service


_DYNAMIC_PLANET_HOUSE_MARKER_PREFIX = "PlumAntics_CosmicEngineHouses_"
log = logging.getLogger("cosmic_engine.planet_house_markers")
_BODY_TO_INDEX = {body: idx for idx, body in enumerate(ALL_BODY_NAMES)}
_HOUSE_TO_INDEX = {house: idx for idx, house in enumerate(HOUSES)}
_WATCHED_TRANSIT_NOTICE_HOUSES = {
    0: "1st House",
    3: "4th House",
    9: "10th House",
}
# Planet transit notice icons use the packaged DST image resources in this project.
_DST_IMAGE_RESOURCE_TYPE = 0x00B2D882
# Temporary diagnostic: force a known EA UI icon through the same notification path.
# If this renders, the Python notification payload path is valid and the issue is with
# the custom planet icon resource reference/type.
_DEBUG_FORCE_EA_TRANSIT_NOTICE_ICON = False
_DEBUG_EA_NOTICE_ICON_RESOURCE_TYPE = 0x2F7D0004
_DEBUG_EA_NOTICE_ICON_INSTANCE = 0x9E70FC72781BF9B1
_PLANET_NOTICE_ICON_GROUP_BY_BODY = {
    "Sun": 0x00000000,
    "Moon": 0x00000000,
    "Mercury": 0x00000000,
    "Venus": 0x00000000,
    "Mars": 0x00000000,
    "Jupiter": 0x00000000,
    "Saturn": 0x00000000,
}
_PLANET_NOTICE_ICON_INSTANCE_BY_BODY = {
    "Sun": 0xDED106F4B50BC238,
    "Moon": 0xED7513E6668B03DF,
    "Mercury": 0xE92D9AEB74B1320C,
    "Venus": 0x8D91B3934B41E5CD,
    "Mars": 0xF78FEF9AF9F01A60,
    "Jupiter": 0xCEAF0651B4EF56F9,
    "Saturn": 0xCB4B88EEABC3F4C1,
    "Uranus": 0xA8F7344C2D7B91E1,
    "Neptune": 0xB61C9D4F7AE20358,
    "Pluto": 0xC4E8A91B5FD07236,
    "Chiron": 0xC4E8A91B5FD07236,
}
_DEFAULT_SIM_DAYS_PER_YEAR = 28.0


def _active_planet_house_body_names(transit_service: Optional[CosmicTransitService] = None) -> Tuple[str, ...]:
    resolver = getattr(transit_service, "active_body_names", None)
    if callable(resolver):
        try:
            return tuple(resolver())
        except Exception:
            pass
    return tuple(BODY_NAMES)


def _resolved_planet_house_body_names(
    transit_service: Optional[CosmicTransitService] = None,
    body_names: Optional[Iterable[str]] = None,
) -> Tuple[str, ...]:
    if body_names is None:
        return _active_planet_house_body_names(transit_service)
    out: List[str] = []
    seen = set()
    for body in tuple(body_names or ()):
        body_name = str(body)
        if body_name not in _BODY_TO_INDEX or body_name in seen:
            continue
        seen.add(body_name)
        out.append(body_name)
    return tuple(out)


def _get_services_module():
    try:
        import services  # type: ignore

        return services
    except Exception:
        return None


def _get_active_sim_info():
    services = _get_services_module()
    if services is None:
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


def _call_bool_attr(obj, attr_name: str) -> Optional[bool]:
    if obj is None:
        return None
    value = getattr(obj, attr_name, None)
    if callable(value):
        try:
            value = value()
        except Exception:
            return None
    if isinstance(value, bool):
        return value
    return None


def _sim_info_species_name(sim_info) -> Optional[str]:
    return sim_info_species_name(sim_info)


def _sim_info_is_human(sim_info) -> bool:
    return sim_info_is_human(sim_info)


def _sim_info_is_non_human(sim_info) -> bool:
    return sim_info_is_non_human(sim_info)


def _raw_text(value: str):
    try:
        from sims4.localization import LocalizationHelperTuning  # type: ignore

        return LocalizationHelperTuning.get_raw_text(str(value))
    except Exception:
        return str(value)


def _show_notification(title: str, text: str, *, owner=None) -> bool:
    try:
        from ui.ui_dialog_notification import UiDialogNotification  # type: ignore

        dialog_owner = owner if owner is not None else _get_active_sim_info()
        notification = UiDialogNotification.TunableFactory().default(
            dialog_owner,
            title=lambda *_, **__: _raw_text(title),
            text=lambda *_, **__: _raw_text(text),
        )
        notification.show_dialog()
        return True
    except Exception:
        return False


def _planet_notice_icon_info_for_body(body: Optional[str]):
    body_name = str(body or "")
    if _DEBUG_FORCE_EA_TRANSIT_NOTICE_ICON:
        icon_instance = _DEBUG_EA_NOTICE_ICON_INSTANCE
        icon_group = 0
        icon_type = _DEBUG_EA_NOTICE_ICON_RESOURCE_TYPE
    else:
        icon_instance = _PLANET_NOTICE_ICON_INSTANCE_BY_BODY.get(body_name)
        icon_group = _PLANET_NOTICE_ICON_GROUP_BY_BODY.get(body_name, 0)
        icon_type = _DST_IMAGE_RESOURCE_TYPE
    if icon_instance is None:
        return None
    try:
        if isinstance(icon_instance, str):
            icon_instance = int(icon_instance, 0)
        else:
            icon_instance = int(icon_instance)
    except Exception:
        return None

    try:
        from sims4 import resources  # type: ignore
        from distributor.shared_messages import IconInfoData  # type: ignore
    except Exception:
        return None

    try:
        resource_key = resources.get_resource_key(icon_instance, icon_type, group=int(icon_group))
    except Exception:
        try:
            resource_key = resources.get_resource_key(icon_instance, icon_type, int(icon_group))
        except Exception:
            resource_key = None
    if resource_key is None:
        return None

    try:
        return IconInfoData(icon_resource=resource_key)
    except Exception:
        try:
            return IconInfoData(resource_key=resource_key)
        except Exception:
            return None


def _show_notification_with_planet_icon(
    title: str,
    text: str,
    *,
    body: Optional[str],
    owner=None,
) -> bool:
    try:
        from ui.ui_dialog_notification import UiDialogNotification  # type: ignore

        dialog_owner = owner if owner is not None else _get_active_sim_info()
        base_kwargs = {
            "title": (lambda *_, **__: _raw_text(title)),
            "text": (lambda *_, **__: _raw_text(text)),
        }
        icon_info = _planet_notice_icon_info_for_body(body)
        default_factory = UiDialogNotification.TunableFactory().default

        if icon_info is not None:
            for kw_name in ("icon_override", "secondary_icon_override", "icon", "secondary_icon"):
                try:
                    log.info(
                        "Transit notice icon ctor attempt body=%s kw=%s icon_info_type=%s icon_info=%r",
                        body,
                        kw_name,
                        type(icon_info),
                        icon_info,
                    )
                    notification = default_factory(dialog_owner, **dict(base_kwargs, **{kw_name: icon_info}))
                    notification.show_dialog()
                    log.info("Transit notice icon ctor success body=%s kw=%s", body, kw_name)
                    return True
                except Exception as e:
                    log.exception(
                        "Transit notice icon ctor failed body=%s kw=%s icon_info=%r error=%r",
                        body,
                        kw_name,
                        icon_info,
                        e,
                    )
        notification = default_factory(dialog_owner, **base_kwargs)
        notification.show_dialog()
        return True
    except Exception:
        return False


def _format_transit_notice_title(body: str, event_name: str, house_label: str) -> str:
    if event_name == "exit":
        return "{0} Transit: Left {1}".format(body, house_label)
    return "{0} Transit: Entered {1}".format(body, house_label)


def _format_transit_notice_text(
    body: str,
    event_name: str,
    house_label: str,
    sign_name: Optional[str],
) -> str:
    if event_name == "exit":
        if sign_name:
            return "{0} has left your {1} ({2}).".format(body, house_label, sign_name)
        return "{0} has left your {1}.".format(body, house_label)
    if sign_name:
        return "{0} has entered your {1} ({2}).".format(body, house_label, sign_name)
    return "{0} has entered your {1}.".format(body, house_label)


def _get_trait_instance_manager():
    try:
        import sims4.resources  # type: ignore
    except Exception:
        return None

    services = _get_services_module()
    if services is None:
        return None

    get_instance_manager = getattr(services, "get_instance_manager", None)
    if not callable(get_instance_manager):
        return None

    try:
        return get_instance_manager(sims4.resources.Types.TRAIT)
    except Exception:
        return None


def _get_buff_instance_manager():
    try:
        import sims4.resources  # type: ignore
    except Exception:
        return None

    services = _get_services_module()
    if services is None:
        return None

    get_instance_manager = getattr(services, "get_instance_manager", None)
    if not callable(get_instance_manager):
        return None

    try:
        return get_instance_manager(sims4.resources.Types.BUFF)
    except Exception:
        return None


def _iter_manager_trait_tunings(instance_manager) -> Iterable[object]:
    if instance_manager is None:
        return ()

    # Common TS4 instance manager layouts.
    for attr_name in ("types", "_tuned_classes"):
        value = getattr(instance_manager, attr_name, None)
        if value is None:
            continue
        if isinstance(value, dict):
            return tuple(value.values())
        values_fn = getattr(value, "values", None)
        if callable(values_fn):
            try:
                values = values_fn()
            except Exception:
                continue
            try:
                return tuple(values)
            except Exception:
                continue

    for attr_name in ("get_all", "values"):
        fn = getattr(instance_manager, attr_name, None)
        if not callable(fn):
            continue
        try:
            items = fn()
        except Exception:
            continue
        try:
            return tuple(items)
        except Exception:
            continue

    return ()


def _parse_planet_house_marker_name(trait_name: str) -> Optional[Tuple[str, int]]:
    if not trait_name:
        return None
    text = str(trait_name)
    if not text.startswith(_DYNAMIC_PLANET_HOUSE_MARKER_PREFIX):
        return None
    if "House" not in text:
        return None
    if "Hidden" not in text:
        return None

    body = None
    for candidate in ALL_BODY_NAMES:
        if candidate in text:
            body = candidate
            break
    if body is None:
        return None

    house_index = None
    for house_name in HOUSES:
        token = "{0}House".format(house_name)
        if token in text:
            house_index = _HOUSE_TO_INDEX[house_name]
            break
    if house_index is None:
        return None

    return (body, int(house_index))


def _parse_planet_house_reward_marker_name(trait_name: str) -> Optional[Tuple[str, int]]:
    if not trait_name:
        return None
    text = str(trait_name)
    if not text.startswith(_DYNAMIC_PLANET_HOUSE_MARKER_PREFIX):
        return None
    if "House" not in text:
        return None
    if "TransitMarker" not in text:
        return None

    body = None
    for candidate in ALL_BODY_NAMES:
        if candidate in text:
            body = candidate
            break
    if body is None:
        return None

    house_index = None
    for house_name in HOUSES:
        token = "{0}House".format(house_name)
        if token in text:
            house_index = _HOUSE_TO_INDEX[house_name]
            break
    if house_index is None:
        return None

    return (body, int(house_index))


def _parse_planet_house_transit_buff_name(buff_name: str) -> Optional[Tuple[str, int]]:
    if not buff_name:
        return None
    text = str(buff_name)
    if not text.startswith(_DYNAMIC_PLANET_HOUSE_MARKER_PREFIX):
        return None
    if "House" not in text or "TransitBuff" not in text:
        return None

    body = None
    for candidate in ALL_BODY_NAMES:
        if candidate in text:
            body = candidate
            break
    if body is None:
        return None

    house_index = None
    for house_name in HOUSES:
        token = "{0}House".format(house_name)
        if token in text:
            house_index = _HOUSE_TO_INDEX[house_name]
            break
    if house_index is None:
        return None

    return (body, int(house_index))


_MARKER_CACHE = {
    "initialized": False,
    "available_by_body_house": {},  # type: Dict[Tuple[str, int], object]
    "candidate_ids_by_body": {},  # type: Dict[str, set]
    "body_house_by_trait_id": {},  # type: Dict[int, Tuple[str, int]]
    "visible_reward_by_body_house": {},  # type: Dict[Tuple[str, int], object]
    "visible_reward_ids_by_body": {},  # type: Dict[str, set]
    "visible_reward_body_house_by_trait_id": {},  # type: Dict[int, Tuple[str, int]]
    "buff_by_body_house": {},  # type: Dict[Tuple[str, int], object]
    "buff_id_by_body_house": {},  # type: Dict[Tuple[str, int], int]
}


def _rebuild_marker_cache() -> Dict[str, object]:
    available_by_body_house: Dict[Tuple[str, int], object] = {}
    candidate_ids_by_body: Dict[str, set] = {body: set() for body in ALL_BODY_NAMES}
    body_house_by_trait_id: Dict[int, Tuple[str, int]] = {}
    visible_reward_by_body_house: Dict[Tuple[str, int], object] = {}
    visible_reward_ids_by_body: Dict[str, set] = {body: set() for body in ALL_BODY_NAMES}
    visible_reward_body_house_by_trait_id: Dict[int, Tuple[str, int]] = {}
    buff_by_body_house: Dict[Tuple[str, int], object] = {}
    buff_id_by_body_house: Dict[Tuple[str, int], int] = {}

    for trait in _iter_manager_trait_tunings(_get_trait_instance_manager()):
        name = _trait_name(trait)
        trait_id = _trait_guid64(trait)
        if trait_id is None:
            continue
        parsed_hidden = _parse_planet_house_marker_name(name)
        if parsed_hidden is not None:
            body, house_index = parsed_hidden
            key = (body, house_index)
            # Prefer the first parsed trait found for a body/house pair.
            available_by_body_house.setdefault(key, trait)
            candidate_ids_by_body.setdefault(body, set()).add(int(trait_id))
            body_house_by_trait_id[int(trait_id)] = key

        parsed_reward = _parse_planet_house_reward_marker_name(name)
        if parsed_reward is not None:
            body, house_index = parsed_reward
            key = (body, house_index)
            visible_reward_by_body_house.setdefault(key, trait)
            visible_reward_ids_by_body.setdefault(body, set()).add(int(trait_id))
            visible_reward_body_house_by_trait_id[int(trait_id)] = key

    for buff in _iter_manager_trait_tunings(_get_buff_instance_manager()):
        name = _trait_name(buff)
        buff_id = _trait_guid64(buff)
        if buff_id is None:
            continue
        parsed_buff = _parse_planet_house_transit_buff_name(name)
        if parsed_buff is None:
            continue
        buff_by_body_house.setdefault(parsed_buff, buff)
        buff_id_by_body_house.setdefault(parsed_buff, int(buff_id))

    _MARKER_CACHE["initialized"] = True
    _MARKER_CACHE["available_by_body_house"] = available_by_body_house
    _MARKER_CACHE["candidate_ids_by_body"] = candidate_ids_by_body
    _MARKER_CACHE["body_house_by_trait_id"] = body_house_by_trait_id
    _MARKER_CACHE["visible_reward_by_body_house"] = visible_reward_by_body_house
    _MARKER_CACHE["visible_reward_ids_by_body"] = visible_reward_ids_by_body
    _MARKER_CACHE["visible_reward_body_house_by_trait_id"] = visible_reward_body_house_by_trait_id
    _MARKER_CACHE["buff_by_body_house"] = buff_by_body_house
    _MARKER_CACHE["buff_id_by_body_house"] = buff_id_by_body_house
    return _MARKER_CACHE


def _marker_cache() -> Dict[str, object]:
    if not _MARKER_CACHE.get("initialized"):
        return _rebuild_marker_cache()
    return _MARKER_CACHE


def reset_marker_cache() -> None:
    _MARKER_CACHE["initialized"] = False
    _MARKER_CACHE["available_by_body_house"] = {}
    _MARKER_CACHE["candidate_ids_by_body"] = {}
    _MARKER_CACHE["body_house_by_trait_id"] = {}
    _MARKER_CACHE["visible_reward_by_body_house"] = {}
    _MARKER_CACHE["visible_reward_ids_by_body"] = {}
    _MARKER_CACHE["visible_reward_body_house_by_trait_id"] = {}
    _MARKER_CACHE["buff_by_body_house"] = {}
    _MARKER_CACHE["buff_id_by_body_house"] = {}


def _iter_instanced_sim_infos() -> Iterable[object]:
    services = _get_services_module()
    if services is None:
        return ()

    sim_info_manager_fn = getattr(services, "sim_info_manager", None)
    sim_info_manager = None
    if callable(sim_info_manager_fn):
        try:
            sim_info_manager = sim_info_manager_fn()
        except Exception:
            sim_info_manager = None

    out: List[object] = []
    seen_sim_ids = set()

    def _append_sim(candidate, *, allow_unknown_instanced: bool = True) -> None:
        sim_info = getattr(candidate, "sim_info", None)
        if sim_info is None:
            sim_info = candidate
        if sim_info is None:
            return

        instanced_attr = getattr(sim_info, "is_instanced", None)
        instanced_value = None
        if callable(instanced_attr):
            try:
                instanced_value = bool(instanced_attr())
            except Exception:
                instanced_value = None
        elif isinstance(instanced_attr, bool):
            instanced_value = instanced_attr

        if instanced_value is False:
            return
        if instanced_value is None and not allow_unknown_instanced:
            return

        sim_id = _sim_id(sim_info)
        if sim_id is not None:
            if sim_id in seen_sim_ids:
                return
            seen_sim_ids.add(sim_id)
        out.append(sim_info)

    if sim_info_manager is not None:
        instanced_gen = getattr(sim_info_manager, "instanced_sims_gen", None)
        if callable(instanced_gen):
            try:
                sims = tuple(instanced_gen())
            except TypeError:
                try:
                    sims = tuple(instanced_gen(allow_hidden_flags=0))
                except Exception:
                    sims = ()
            except Exception:
                sims = ()
            if sims:
                for sim in sims:
                    _append_sim(sim)
                return tuple(out)

        get_all = getattr(sim_info_manager, "get_all", None)
        if callable(get_all):
            try:
                sim_infos = tuple(get_all())
            except Exception:
                sim_infos = ()
            if sim_infos:
                for sim_info in sim_infos:
                    _append_sim(sim_info)
                if out:
                    return tuple(out)

    _append_sim(_get_active_sim_info())
    if out:
        return tuple(out)

    household = _get_active_household()
    if household is None:
        return ()

    instanced_household_gen = getattr(household, "instanced_sims_gen", None)
    if callable(instanced_household_gen):
        try:
            for sim in instanced_household_gen():
                _append_sim(sim)
        except Exception:
            pass
    if out:
        return tuple(out)

    household_sim_info_gen = getattr(household, "sim_info_gen", None)
    if callable(household_sim_info_gen):
        try:
            for sim_info in household_sim_info_gen():
                _append_sim(sim_info, allow_unknown_instanced=False)
        except Exception:
            pass
    if out:
        return tuple(out)

    return ()


def _trait_tracker_add_trait(sim_info, trait_tracker, trait) -> bool:
    for owner in (trait_tracker, sim_info):
        if owner is None:
            continue
        method = getattr(owner, "add_trait", None)
        if callable(method):
            try:
                method(trait)
                return True
            except Exception:
                pass
    return False


def _trait_tracker_remove_trait(sim_info, trait_tracker, trait) -> bool:
    for owner in (trait_tracker, sim_info):
        if owner is None:
            continue
        method = getattr(owner, "remove_trait", None)
        if callable(method):
            try:
                method(trait)
                return True
            except Exception:
                pass
    return False


def _build_house_sign_map_for_sim(trait_ids: List[int], marker_trait_ids: List[int]) -> Optional[Dict[int, int]]:
    house_sign_map = resolve_house_sign_map_from_marker_ids(marker_trait_ids)
    if len(house_sign_map) == 12:
        return house_sign_map

    rising_sign_index = resolve_rising_sign_index_from_trait_ids(trait_ids)
    if rising_sign_index is None:
        return None
    return build_house_sign_map_for_rising(rising_sign_index)


def _desired_marker_traits_for_sim(
    transit_service: CosmicTransitService,
    house_sign_map: Mapping[int, int],
    available_by_body_house: Mapping[Tuple[str, int], object],
    *,
    body_names: Optional[Iterable[str]] = None,
) -> Dict[str, object]:
    body_chart = transit_service.chart_for_house_sign_map(house_sign_map)
    desired: Dict[str, object] = {}
    for body in _resolved_planet_house_body_names(transit_service, body_names):
        row = body_chart.get(body, {})
        house_index = row.get("house_index")
        if not isinstance(house_index, int):
            continue
        trait = available_by_body_house.get((body, int(house_index)))
        if trait is None:
            continue
        desired[body] = trait
    return desired


def _equipped_traits_with_ids(sim_info) -> List[Tuple[object, int]]:
    out: List[Tuple[object, int]] = []
    seen_ids: set = set()
    for trait in _iter_traits_for_sim_info(sim_info):
        tid = _trait_guid64(trait)
        if tid is None:
            continue
        tid = int(tid)
        if tid in seen_ids:
            continue
        seen_ids.add(tid)
        out.append((trait, tid))
    return out


def _slowest_body_first_sort_key(body_name: str) -> Tuple[float, str]:
    rule = RULE_BY_BODY.get(str(body_name))
    if rule is None:
        return (0.0, str(body_name))
    if str(rule.unit) == "day":
        cadence_days = float(rule.interval)
    else:
        cadence_days = float(rule.interval) * (
            float(_DEFAULT_SIM_DAYS_PER_YEAR) / float(SEASON_SEGMENTS_PER_YEAR)
        )
    return (float(cadence_days), str(body_name))


def _managed_watched_house_buff_ids(buff_id_by_body_house, active_body_names) -> set:
    watched_houses = set(_WATCHED_TRANSIT_NOTICE_HOUSES.keys())
    active = set(tuple(active_body_names or ()))
    managed = set()
    for key, buff_id in dict(buff_id_by_body_house or {}).items():
        if not isinstance(key, tuple) or len(key) != 2:
            continue
        body_name, house_index = key
        if str(body_name) not in active or int(house_index) not in watched_houses:
            continue
        try:
            managed.add(int(buff_id))
        except Exception:
            continue
    return managed


def _sync_house_transit_buffs_from_reward_markers(
    sim_info,
    *,
    visible_reward_body_house_by_trait_id,
    buff_id_by_body_house,
    active_body_names,
    skill_gate_enabled,
    summary: Optional[Dict[str, int]] = None,
) -> bool:
    watched_houses = set(_WATCHED_TRANSIT_NOTICE_HOUSES.keys())
    active = set(tuple(active_body_names or ()))
    equipped = _equipped_traits_with_ids(sim_info)
    candidates_by_house: Dict[int, List[str]] = {}

    for _trait, trait_id in equipped:
        body_house = dict(visible_reward_body_house_by_trait_id or {}).get(int(trait_id))
        if not isinstance(body_house, tuple) or len(body_house) != 2:
            continue
        body_name, house_index = body_house
        if int(house_index) not in watched_houses:
            continue
        if str(body_name) not in active:
            continue
        candidates_by_house.setdefault(int(house_index), []).append(str(body_name))

    desired_buff_ids = set()
    if skill_gate_enabled:
        for house_index, bodies in candidates_by_house.items():
            winning_body = sorted(
                tuple(bodies),
                key=_slowest_body_first_sort_key,
                reverse=True,
            )[0]
            buff_id = dict(buff_id_by_body_house or {}).get((winning_body, int(house_index)))
            if buff_id is None:
                continue
            try:
                desired_buff_ids.add(int(buff_id))
            except Exception:
                continue

    managed_buff_ids = _managed_watched_house_buff_ids(buff_id_by_body_house, active_body_names)
    changed = False
    buffs_removed = 0
    buffs_added = 0

    if not skill_gate_enabled:
        skipped = len(desired_buff_ids) if desired_buff_ids else len(managed_buff_ids)
        if summary is not None:
            summary["buffs_skipped_skill_gate"] = int(summary.get("buffs_skipped_skill_gate", 0) or 0) + int(skipped)

    for buff_id in sorted(managed_buff_ids - desired_buff_ids):
        if _remove_buff_if_present(sim_info, int(buff_id)):
            changed = True
            buffs_removed += 1

    for buff_id in sorted(desired_buff_ids):
        if _add_buff_if_missing(sim_info, int(buff_id)):
            changed = True
            buffs_added += 1

    if summary is not None:
        summary["buffs_added"] = int(summary.get("buffs_added", 0) or 0) + int(buffs_added)
        summary["buffs_removed"] = int(summary.get("buffs_removed", 0) or 0) + int(buffs_removed)
    return changed


def _clear_managed_house_traits_for_non_human(
    sim_info,
    trait_tracker,
    *,
    candidate_ids_by_body,
    visible_reward_ids_by_body,
    managed_buff_ids,
) -> Dict[str, int]:
    summary = {
        "traits_removed": 0,
        "reward_traits_removed": 0,
        "buffs_removed": 0,
    }
    if sim_info is None or trait_tracker is None:
        return summary

    marker_ids = set()
    if isinstance(candidate_ids_by_body, dict):
        for candidate_ids in candidate_ids_by_body.values():
            for candidate_id in tuple(candidate_ids or ()):
                try:
                    marker_ids.add(int(candidate_id))
                except Exception:
                    continue

    reward_ids = set()
    if isinstance(visible_reward_ids_by_body, dict):
        for candidate_ids in visible_reward_ids_by_body.values():
            for candidate_id in tuple(candidate_ids or ()):
                try:
                    reward_ids.add(int(candidate_id))
                except Exception:
                    continue

    for equipped_trait, equipped_tid in _equipped_traits_with_ids(sim_info):
        if equipped_tid not in marker_ids and equipped_tid not in reward_ids:
            continue
        if not _trait_tracker_remove_trait(sim_info, trait_tracker, equipped_trait):
            continue
        if equipped_tid in marker_ids:
            summary["traits_removed"] += 1
        if equipped_tid in reward_ids:
            summary["reward_traits_removed"] += 1
    for buff_id in sorted(set(managed_buff_ids or ())):
        if _remove_buff_if_present(sim_info, int(buff_id)):
            summary["buffs_removed"] += 1
    return summary


def sync_zone_planet_house_markers(
    *,
    transit_service: Optional[CosmicTransitService] = None,
    refresh_marker_cache: bool = False,
    sim_infos: Optional[Iterable[object]] = None,
    body_names: Optional[Iterable[str]] = None,
) -> Dict[str, int]:
    """Sync planet-in-house markers for instanced sims in the active zone.

    Returns a summary dict for debug commands/logging.
    """
    if refresh_marker_cache:
        reset_marker_cache()
    cache = _marker_cache()
    available_by_body_house = cache.get("available_by_body_house", {})
    candidate_ids_by_body = cache.get("candidate_ids_by_body", {})
    body_house_by_trait_id = cache.get("body_house_by_trait_id", {})
    visible_reward_by_body_house = cache.get("visible_reward_by_body_house", {})
    visible_reward_ids_by_body = cache.get("visible_reward_ids_by_body", {})
    visible_reward_body_house_by_trait_id = cache.get("visible_reward_body_house_by_trait_id", {})
    buff_id_by_body_house = cache.get("buff_id_by_body_house", {})

    summary = {
        "sims_seen": 0,
        "sims_with_house_map": 0,
        "sims_changed": 0,
        "traits_added": 0,
        "traits_removed": 0,
        "reward_traits_added": 0,
        "reward_traits_removed": 0,
        "reward_traits_skipped_skill_gate": 0,
        "buffs_added": 0,
        "buffs_removed": 0,
        "buffs_skipped_skill_gate": 0,
        "non_humans_skipped": 0,
        "non_human_traits_removed": 0,
        "non_human_reward_traits_removed": 0,
        "non_human_buffs_removed": 0,
        "notice_events": 0,
        "notices_shown": 0,
        "notice_skipped_initial_marker_seed": 0,
        "notice_skipped_skill_gate": 0,
        "transit_awareness_required_level": simstrology_skill_unlock_level("transit_awareness", 4),
        "available_marker_defs": len(available_by_body_house) if isinstance(available_by_body_house, dict) else 0,
        "available_reward_marker_defs": len(visible_reward_by_body_house) if isinstance(visible_reward_by_body_house, dict) else 0,
        "available_reward_buff_defs": len(buff_id_by_body_house) if isinstance(buff_id_by_body_house, dict) else 0,
    }

    if not isinstance(available_by_body_house, dict) or not available_by_body_house:
        # No marker trait definitions present yet; do not touch sims.
        return summary

    service = transit_service or get_global_transit_service()
    active_body_names = _resolved_planet_house_body_names(service, body_names)
    active_body_name_set = set(active_body_names)
    if active_body_name_set:
        available_by_body_house = {
            key: trait
            for key, trait in dict(available_by_body_house or {}).items()
            if isinstance(key, tuple) and len(key) == 2 and str(key[0]) in active_body_name_set
        }
        candidate_ids_by_body = {
            str(body): ids
            for body, ids in dict(candidate_ids_by_body or {}).items()
            if str(body) in active_body_name_set
        }
        visible_reward_by_body_house = {
            key: trait
            for key, trait in dict(visible_reward_by_body_house or {}).items()
            if isinstance(key, tuple) and len(key) == 2 and str(key[0]) in active_body_name_set
        }
        visible_reward_ids_by_body = {
            str(body): ids
            for body, ids in dict(visible_reward_ids_by_body or {}).items()
            if str(body) in active_body_name_set
        }
        visible_reward_body_house_by_trait_id = {
            int(trait_id): key
            for trait_id, key in dict(visible_reward_body_house_by_trait_id or {}).items()
            if isinstance(key, tuple) and len(key) == 2 and str(key[0]) in active_body_name_set
        }
        buff_id_by_body_house = {
            key: buff_id
            for key, buff_id in dict(buff_id_by_body_house or {}).items()
            if isinstance(key, tuple) and len(key) == 2 and str(key[0]) in active_body_name_set
        }
        summary["available_marker_defs"] = len(available_by_body_house)
        summary["available_reward_marker_defs"] = len(visible_reward_by_body_house)
        summary["available_reward_buff_defs"] = len(buff_id_by_body_house)
    active_sim_id = _sim_id(_get_active_sim_info())

    target_sim_infos = tuple(_iter_instanced_sim_infos()) if sim_infos is None else tuple(sim_infos)

    for sim_info in target_sim_infos:
        summary["sims_seen"] += 1

        trait_tracker = getattr(sim_info, "trait_tracker", None)
        if trait_tracker is None:
            continue

        if _sim_info_is_non_human(sim_info):
            summary["non_humans_skipped"] += 1
            cleanup = _clear_managed_house_traits_for_non_human(
                sim_info,
                trait_tracker,
                candidate_ids_by_body=candidate_ids_by_body,
                visible_reward_ids_by_body=visible_reward_ids_by_body,
                managed_buff_ids=_managed_watched_house_buff_ids(
                    buff_id_by_body_house,
                    active_body_names,
                ),
            )
            summary["traits_removed"] += int(cleanup.get("traits_removed", 0) or 0)
            summary["reward_traits_removed"] += int(cleanup.get("reward_traits_removed", 0) or 0)
            summary["buffs_removed"] += int(cleanup.get("buffs_removed", 0) or 0)
            summary["non_human_traits_removed"] += int(cleanup.get("traits_removed", 0) or 0)
            summary["non_human_reward_traits_removed"] += int(cleanup.get("reward_traits_removed", 0) or 0)
            summary["non_human_buffs_removed"] += int(cleanup.get("buffs_removed", 0) or 0)
            if (
                int(cleanup.get("traits_removed", 0) or 0)
                or int(cleanup.get("reward_traits_removed", 0) or 0)
                or int(cleanup.get("buffs_removed", 0) or 0)
            ):
                summary["sims_changed"] += 1
            continue

        trait_ids, marker_trait_ids = _collect_trait_ids_and_markers(sim_info)
        house_sign_map = _build_house_sign_map_for_sim(trait_ids, marker_trait_ids)
        if house_sign_map is None or len(house_sign_map) < 12:
            continue
        summary["sims_with_house_map"] += 1

        desired_by_body = _desired_marker_traits_for_sim(
            service,
            house_sign_map,
            available_by_body_house,
            body_names=active_body_names,
        )
        desired_id_by_body: Dict[str, int] = {}
        for body, trait in desired_by_body.items():
            tid = _trait_guid64(trait)
            if tid is not None:
                desired_id_by_body[body] = int(tid)
        desired_visible_reward_by_body = _desired_marker_traits_for_sim(
            service,
            house_sign_map,
            visible_reward_by_body_house if isinstance(visible_reward_by_body_house, dict) else {},
            body_names=active_body_names,
        )
        desired_visible_reward_id_by_body: Dict[str, int] = {}
        for body, trait in desired_visible_reward_by_body.items():
            tid = _trait_guid64(trait)
            if tid is not None:
                desired_visible_reward_id_by_body[body] = int(tid)
        required_transit_awareness_level = int(summary.get("transit_awareness_required_level", 4) or 4)
        if not simstrology_skill_meets(sim_info, required_transit_awareness_level):
            summary["reward_traits_skipped_skill_gate"] += len(desired_visible_reward_id_by_body)
            desired_visible_reward_by_body = {}
            desired_visible_reward_id_by_body = {}

        equipped = _equipped_traits_with_ids(sim_info)
        equipped_ids = {tid for _, tid in equipped}
        current_house_by_body: Dict[str, int] = {}
        for _equipped_trait, equipped_tid in equipped:
            parsed_key = None
            if isinstance(body_house_by_trait_id, dict):
                parsed_key = body_house_by_trait_id.get(int(equipped_tid))
            if not isinstance(parsed_key, tuple) or len(parsed_key) != 2:
                continue
            body_name, house_index = parsed_key
            if str(body_name) not in _BODY_TO_INDEX:
                continue
            if not isinstance(house_index, int):
                continue
            current_house_by_body[str(body_name)] = int(house_index)
        had_any_managed_marker = bool(current_house_by_body)

        pending_notice_events: List[Dict[str, object]] = []
        sim_id = _sim_id(sim_info)
        should_notify = (
            active_sim_id is not None
            and sim_id is not None
            and int(active_sim_id) == int(sim_id)
            and had_any_managed_marker
        )
        if should_notify:
            for body in active_body_names:
                previous_house = current_house_by_body.get(body)
                desired_tid = desired_id_by_body.get(body)
                desired_key = None
                if desired_tid is not None and isinstance(body_house_by_trait_id, dict):
                    desired_key = body_house_by_trait_id.get(int(desired_tid))
                desired_house = None
                if isinstance(desired_key, tuple) and len(desired_key) == 2 and isinstance(desired_key[1], int):
                    desired_house = int(desired_key[1])

                if previous_house is None and desired_house is None:
                    continue
                if previous_house is not None and desired_house is not None and int(previous_house) == int(desired_house):
                    continue

                if previous_house is not None and int(previous_house) in _WATCHED_TRANSIT_NOTICE_HOUSES:
                    sign_name = None
                    sign_index = house_sign_map.get(int(previous_house))
                    if isinstance(sign_index, int):
                        sign_name = SIGNS[int(sign_index) % 12]
                    pending_notice_events.append(
                        {
                            "body": str(body),
                            "event": "exit",
                            "house_index": int(previous_house),
                            "house_label": _WATCHED_TRANSIT_NOTICE_HOUSES[int(previous_house)],
                            "sign_name": sign_name,
                        }
                    )
                if desired_house is not None and int(desired_house) in _WATCHED_TRANSIT_NOTICE_HOUSES:
                    sign_name = None
                    sign_index = house_sign_map.get(int(desired_house))
                    if isinstance(sign_index, int):
                        sign_name = SIGNS[int(sign_index) % 12]
                    pending_notice_events.append(
                        {
                            "body": str(body),
                            "event": "enter",
                            "house_index": int(desired_house),
                            "house_label": _WATCHED_TRANSIT_NOTICE_HOUSES[int(desired_house)],
                            "sign_name": sign_name,
                        }
                    )
        changed = False

        # Remove outdated managed markers per body.
        for equipped_trait, equipped_tid in equipped:
            removed = False
            for body, candidate_ids in candidate_ids_by_body.items():
                if equipped_tid not in candidate_ids:
                    continue
                desired_tid = desired_id_by_body.get(body)
                if desired_tid is not None and desired_tid == equipped_tid:
                    removed = True  # Keep, but stop scanning other bodies
                    break
                if _trait_tracker_remove_trait(sim_info, trait_tracker, equipped_trait):
                    summary["traits_removed"] += 1
                    changed = True
                    equipped_ids.discard(equipped_tid)
                removed = True
                break
            if removed:
                continue

        # Add desired markers missing on the sim.
        for body, desired_trait in desired_by_body.items():
            desired_tid = desired_id_by_body.get(body)
            if desired_tid is None or desired_tid in equipped_ids:
                continue
            if _trait_tracker_add_trait(sim_info, trait_tracker, desired_trait):
                summary["traits_added"] += 1
                changed = True
                equipped_ids.add(desired_tid)

        # Remove outdated visible reward transit markers per body (if defs exist).
        if isinstance(visible_reward_ids_by_body, dict) and visible_reward_ids_by_body:
            for equipped_trait, equipped_tid in equipped:
                removed = False
                for body, candidate_ids in visible_reward_ids_by_body.items():
                    if equipped_tid not in candidate_ids:
                        continue
                    desired_tid = desired_visible_reward_id_by_body.get(body)
                    if desired_tid is not None and desired_tid == equipped_tid:
                        removed = True  # Keep, but stop scanning other bodies
                        break
                    if _trait_tracker_remove_trait(sim_info, trait_tracker, equipped_trait):
                        summary["reward_traits_removed"] += 1
                        changed = True
                        equipped_ids.discard(equipped_tid)
                    removed = True
                    break
                if removed:
                    continue

            # Add desired visible reward transit markers missing on the sim.
            for body, desired_trait in desired_visible_reward_by_body.items():
                desired_tid = desired_visible_reward_id_by_body.get(body)
                if desired_tid is None or desired_tid in equipped_ids:
                    continue
                if _trait_tracker_add_trait(sim_info, trait_tracker, desired_trait):
                    summary["reward_traits_added"] += 1
                    changed = True
                    equipped_ids.add(desired_tid)

        if _sync_house_transit_buffs_from_reward_markers(
            sim_info,
            visible_reward_body_house_by_trait_id=visible_reward_body_house_by_trait_id,
            buff_id_by_body_house=buff_id_by_body_house,
            active_body_names=active_body_names,
            skill_gate_enabled=simstrology_skill_meets(
                sim_info,
                required_transit_awareness_level,
            ),
            summary=summary,
        ):
            changed = True

        if changed:
            summary["sims_changed"] += 1
            if (
                active_sim_id is not None
                and sim_id is not None
                and int(active_sim_id) == int(sim_id)
                and not had_any_managed_marker
            ):
                summary["notice_skipped_initial_marker_seed"] += 1
            if pending_notice_events:
                summary["notice_events"] += len(pending_notice_events)
                required_level = simstrology_skill_unlock_level("transit_awareness", 4)
                if not simstrology_skill_meets(sim_info, required_level):
                    summary["notice_skipped_skill_gate"] += len(pending_notice_events)
                    continue
                for event in pending_notice_events:
                    title = _format_transit_notice_title(
                        str(event.get("body", "")),
                        str(event.get("event", "")),
                        str(event.get("house_label", "")),
                    )
                    text = _format_transit_notice_text(
                        str(event.get("body", "")),
                        str(event.get("event", "")),
                        str(event.get("house_label", "")),
                        str(event.get("sign_name")) if event.get("sign_name") is not None else None,
                    )
                    if _show_notification_with_planet_icon(
                        title,
                        text,
                        body=str(event.get("body", "")),
                        owner=sim_info,
                    ):
                        summary["notices_shown"] += 1

    return summary


def sync_active_household_outer_planets_only(
    *,
    transit_service: Optional[CosmicTransitService] = None,
    refresh_marker_cache: bool = False,
    sim_infos: Optional[Iterable[object]] = None,
) -> Dict[str, int]:
    summary = {
        "ok": False,
        "reason": None,
        "outer_planets_only": 1,
        "sims_seen": 0,
        "sims_refreshed": 0,
        "traits_added": 0,
        "traits_removed": 0,
        "reward_traits_added": 0,
        "reward_traits_removed": 0,
        "buffs_added": 0,
        "buffs_removed": 0,
    }

    if not is_outer_planets_addon_active():
        summary["reason"] = "addon_inactive"
        return summary

    target_sim_infos = tuple(sim_infos or ())
    if not target_sim_infos:
        summary["reason"] = "no_target_sims"
        return summary

    service = transit_service or get_global_transit_service()
    scoped_summary = sync_zone_planet_house_markers(
        transit_service=service,
        refresh_marker_cache=refresh_marker_cache,
        sim_infos=target_sim_infos,
        body_names=OPTIONAL_OUTER_BODY_NAMES,
    )
    summary.update(scoped_summary)
    summary["ok"] = True
    summary["reason"] = "refreshed"
    summary["outer_planets_only"] = 1
    summary["sims_refreshed"] = int(scoped_summary.get("sims_changed", 0) or 0)
    return summary
