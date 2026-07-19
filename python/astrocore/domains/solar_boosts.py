from __future__ import annotations

from typing import Dict, Iterable, Mapping, Optional, Sequence, Set

from cosmic_engine.chart_composition import get_sign_element
from cosmic_engine.loot_actions import _trait_name
from cosmic_engine.natal_snapshot_markers import (
    _get_buff_instance_manager,
    _iter_manager_trait_tunings,
    _sim_info_add_buff,
    _sim_info_has_buff,
    _sim_info_remove_buff,
)
from cosmic_engine.planet_house_markers import _equipped_traits_with_ids, _iter_instanced_sim_infos
from cosmic_engine.transit_core import SIGNS, house_index_for_sign_and_rising
from cosmic_engine.transit_service import get_global_transit_service


SIGN_INDEX_BY_NAME = {name: index for index, name in enumerate(SIGNS)}

SUN_SOLAR_BUFF_KEY_BY_SIGN_INDEX = {
    index: f"PlumAntics_Big3Mod_{sign_name}SunBuff"
    for index, sign_name in enumerate(SIGNS)
}
RISING_SOLAR_BUFF_KEY_BY_SIGN_INDEX = {
    index: f"PlumAntics_Big3Mod_{sign_name}RisingBuff"
    for index, sign_name in enumerate(SIGNS)
}
MOON_SOLAR_BUFF_KEY_BY_SIGN_INDEX = {
    index: f"PlumAntics_Big3Mod_{sign_name}MoonSolarBuff"
    for index, sign_name in enumerate(SIGNS)
}
ANGULAR_SOLAR_BUFF_KEY_BY_HOUSE_INDEX = {
    0: "PlumAntics_Big3Mod_SolarHouseFirstBuff",
    3: "PlumAntics_Big3Mod_SolarHouseFourthBuff",
    6: "PlumAntics_Big3Mod_SolarHouseSeventhBuff",
    9: "PlumAntics_Big3Mod_SolarHouseTenthBuff",
}
ELEMENT_SUPPORT_BUFF_KEY_BY_ELEMENT = {
    "fire": "PlumAntics_Big3Mod_ElementFireSolarSupportBuff",
    "earth": "PlumAntics_Big3Mod_ElementEarthSolarSupportBuff",
    "air": "PlumAntics_Big3Mod_ElementAirSolarSupportBuff",
    "water": "PlumAntics_Big3Mod_ElementWaterSolarSupportBuff",
}

OWNED_EXACT_VISIBLE_SOLAR_BUFF_KEYS = set(SUN_SOLAR_BUFF_KEY_BY_SIGN_INDEX.values()) | set(
    RISING_SOLAR_BUFF_KEY_BY_SIGN_INDEX.values()
) | set(MOON_SOLAR_BUFF_KEY_BY_SIGN_INDEX.values())
OWNED_ANGULAR_SOLAR_BUFF_KEYS = set(ANGULAR_SOLAR_BUFF_KEY_BY_HOUSE_INDEX.values())
OWNED_ELEMENT_SUPPORT_BUFF_KEYS = set(ELEMENT_SUPPORT_BUFF_KEY_BY_ELEMENT.values())
OWNED_VISIBLE_SOLAR_BUFF_KEYS = (
    OWNED_EXACT_VISIBLE_SOLAR_BUFF_KEYS
    | OWNED_ANGULAR_SOLAR_BUFF_KEYS
    | OWNED_ELEMENT_SUPPORT_BUFF_KEYS
)

_NATAL_TRAIT_PREFIX = "PlumAntics_CosmicEngineNatal_"
_BUFF_TUNING_BY_KEY_CACHE = None


def _normalize_sign_index(value: Optional[int]) -> Optional[int]:
    if value is None:
        return None
    return int(value) % 12


def _parse_natal_sign_index(trait_name: str, suffix: str) -> Optional[int]:
    text = str(trait_name or "")
    if not text.startswith(_NATAL_TRAIT_PREFIX) or not text.endswith(suffix):
        return None
    sign_name = text[len(_NATAL_TRAIT_PREFIX) : -len(suffix)]
    return SIGN_INDEX_BY_NAME.get(sign_name)


def resolve_natal_sign_index_by_layer(trait_names: Sequence[str]) -> Dict[str, Optional[int]]:
    rows = {"sun": None, "moon": None, "rising": None}
    for trait_name in tuple(trait_names or ()):
        if rows["sun"] is None:
            rows["sun"] = _parse_natal_sign_index(trait_name, "SunHidden")
        if rows["moon"] is None:
            rows["moon"] = _parse_natal_sign_index(trait_name, "MoonHidden")
        if rows["rising"] is None:
            rows["rising"] = _parse_natal_sign_index(trait_name, "RisingHidden")
    return rows


def build_desired_solar_boost_state(
    *,
    current_sun_sign_index: int,
    natal_sign_index_by_layer: Mapping[str, Optional[int]],
) -> Dict[str, object]:
    current_sun_sign_index = int(current_sun_sign_index) % 12
    natal_sun = _normalize_sign_index(natal_sign_index_by_layer.get("sun"))
    natal_moon = _normalize_sign_index(natal_sign_index_by_layer.get("moon"))
    natal_rising = _normalize_sign_index(natal_sign_index_by_layer.get("rising"))

    exact_buff_keys = []
    if natal_sun is not None and natal_sun == current_sun_sign_index:
        exact_buff_keys.append(SUN_SOLAR_BUFF_KEY_BY_SIGN_INDEX[natal_sun])
    if natal_rising is not None and natal_rising == current_sun_sign_index:
        exact_buff_keys.append(RISING_SOLAR_BUFF_KEY_BY_SIGN_INDEX[natal_rising])
    if natal_moon is not None and natal_moon == current_sun_sign_index:
        exact_buff_keys.append(MOON_SOLAR_BUFF_KEY_BY_SIGN_INDEX[natal_moon])

    angular_buff_key = None
    if natal_rising is not None:
        house_index = house_index_for_sign_and_rising(current_sun_sign_index, natal_rising)
        angular_buff_key = ANGULAR_SOLAR_BUFF_KEY_BY_HOUSE_INDEX.get(int(house_index))

    element_buff_key = None
    current_element = get_sign_element(SIGNS[current_sun_sign_index])
    if current_element is not None:
        matches = []
        for layer_name in ("sun", "moon", "rising"):
            sign_index = _normalize_sign_index(natal_sign_index_by_layer.get(layer_name))
            if sign_index is None:
                continue
            if get_sign_element(SIGNS[sign_index]) == current_element:
                matches.append(layer_name)
        if matches:
            element_buff_key = ELEMENT_SUPPORT_BUFF_KEY_BY_ELEMENT[str(current_element).lower()]

    return {
        "current_sun_sign_index": current_sun_sign_index,
        "exact_buff_keys": exact_buff_keys,
        "angular_buff_key": angular_buff_key,
        "element_buff_key": element_buff_key,
    }


def _desired_buff_key_set(state: Mapping[str, object]) -> Set[str]:
    keys = set(state.get("exact_buff_keys") or ())
    angular_buff_key = state.get("angular_buff_key")
    element_buff_key = state.get("element_buff_key")
    if angular_buff_key:
        keys.add(str(angular_buff_key))
    if element_buff_key:
        keys.add(str(element_buff_key))
    return keys


def _resolved_owned_buff_tunings_by_key():
    global _BUFF_TUNING_BY_KEY_CACHE
    if isinstance(_BUFF_TUNING_BY_KEY_CACHE, dict):
        return _BUFF_TUNING_BY_KEY_CACHE

    resolved = {}
    for buff in _iter_manager_trait_tunings(_get_buff_instance_manager()):
        buff_name = _trait_name(buff)
        if buff_name in OWNED_VISIBLE_SOLAR_BUFF_KEYS:
            resolved.setdefault(str(buff_name), buff)
    _BUFF_TUNING_BY_KEY_CACHE = resolved
    return resolved


def _default_trait_names_for_sim_info(sim_info):
    return [_trait_name(trait) for trait, _trait_id in _equipped_traits_with_ids(sim_info)]


def _default_current_buff_keys_for_sim_info(sim_info):
    resolved = _resolved_owned_buff_tunings_by_key()
    active_keys = set()
    for buff_key, buff in resolved.items():
        if _sim_info_has_buff(sim_info, buff):
            active_keys.add(str(buff_key))
    return active_keys


def _default_add_buff_by_key(sim_info, buff_key):
    buff = _resolved_owned_buff_tunings_by_key().get(str(buff_key))
    if buff is None:
        return False
    return _sim_info_add_buff(sim_info, buff)


def _default_remove_buff_by_key(sim_info, buff_key):
    buff = _resolved_owned_buff_tunings_by_key().get(str(buff_key))
    if buff is None:
        return False
    return _sim_info_remove_buff(sim_info, buff)


def sync_zone_solar_boosts(
    *,
    sim_infos: Optional[Iterable[object]] = None,
    current_sun_sign_index: Optional[int] = None,
    get_trait_names_fn=None,
    list_buff_keys_fn=None,
    add_buff_by_key_fn=None,
    remove_buff_by_key_fn=None,
) -> Dict[str, int]:
    summary = {
        "sims_seen": 0,
        "sims_changed": 0,
        "buffs_added": 0,
        "buffs_removed": 0,
    }

    if current_sun_sign_index is None:
        current_sun_sign_index = int(get_global_transit_service().state.sign_index_by_body.get("Sun", 0)) % 12

    get_trait_names_fn = get_trait_names_fn or _default_trait_names_for_sim_info
    list_buff_keys_fn = list_buff_keys_fn or _default_current_buff_keys_for_sim_info
    add_buff_by_key_fn = add_buff_by_key_fn or _default_add_buff_by_key
    remove_buff_by_key_fn = remove_buff_by_key_fn or _default_remove_buff_by_key

    target_sim_infos = tuple(_iter_instanced_sim_infos()) if sim_infos is None else tuple(sim_infos)
    for sim_info in target_sim_infos:
        summary["sims_seen"] += 1
        trait_names = list(get_trait_names_fn(sim_info) or ())
        natal_sign_index_by_layer = resolve_natal_sign_index_by_layer(trait_names)
        desired_state = build_desired_solar_boost_state(
            current_sun_sign_index=int(current_sun_sign_index),
            natal_sign_index_by_layer=natal_sign_index_by_layer,
        )
        desired_keys = _desired_buff_key_set(desired_state)
        current_keys = set(list_buff_keys_fn(sim_info) or ())
        owned_current_keys = current_keys & OWNED_VISIBLE_SOLAR_BUFF_KEYS

        changed = False
        for buff_key in sorted(owned_current_keys - desired_keys):
            if remove_buff_by_key_fn(sim_info, buff_key):
                summary["buffs_removed"] += 1
                changed = True

        for buff_key in sorted(desired_keys - owned_current_keys):
            if add_buff_by_key_fn(sim_info, buff_key):
                summary["buffs_added"] += 1
                changed = True

        if changed:
            summary["sims_changed"] += 1

    return summary


__all__ = [
    "ANGULAR_SOLAR_BUFF_KEY_BY_HOUSE_INDEX",
    "ELEMENT_SUPPORT_BUFF_KEY_BY_ELEMENT",
    "MOON_SOLAR_BUFF_KEY_BY_SIGN_INDEX",
    "OWNED_VISIBLE_SOLAR_BUFF_KEYS",
    "RISING_SOLAR_BUFF_KEY_BY_SIGN_INDEX",
    "SIGN_INDEX_BY_NAME",
    "SUN_SOLAR_BUFF_KEY_BY_SIGN_INDEX",
    "build_desired_solar_boost_state",
    "resolve_natal_sign_index_by_layer",
    "sync_zone_solar_boosts",
]
