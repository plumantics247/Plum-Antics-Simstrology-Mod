"""Runtime helpers for Big 3 crystal resonance."""

from __future__ import annotations

from collections.abc import Mapping as MappingABC
from typing import Dict, Iterable, Mapping, Optional, Sequence, Tuple

from .chart_records import SIGNS
from .crystal_resonance_activation import is_crystal_resonance_addon_active
from .transit_service import get_global_transit_service


PRIMARY_CRYSTAL_BY_SIGN = {
    "Aries": "Diamond",
    "Taurus": "Emerald",
    "Gemini": "Citrine",
    "Cancer": "Ruby",
    "Leo": "Fire Opal",
    "Virgo": "Sapphire",
    "Libra": "Rose",
    "Scorpio": "Turquoise",
    "Sagittarius": "Orange Topaz",
    "Capricorn": "Jet",
    "Aquarius": "Amethyst",
    "Pisces": "Quartz",
}

CRYSTAL_OBJECT_TOKENS = {
    "Diamond": ("diamond",),
    "Emerald": ("emerald",),
    "Citrine": ("citrine",),
    "Ruby": ("ruby",),
    "Fire Opal": ("fireopal", "fire_opal", "fire opal"),
    "Sapphire": ("sapphire",),
    "Rose": ("rosequartz", "rose_quartz", "rose"),
    "Turquoise": ("turquoise",),
    "Orange Topaz": ("orangetopaz", "orange_topaz", "orange topaz"),
    "Jet": ("jet",),
    "Amethyst": ("amethyst",),
    "Quartz": ("quartz",),
}

PASSIVE_BUFF_ID_BY_CRYSTAL_KEY = {
    "Diamond": 840000000000009001,
    "Emerald": 840000000000009002,
    "Citrine": 840000000000009003,
    "Ruby": 840000000000009004,
    "Fire Opal": 840000000000009005,
    "Sapphire": 840000000000009006,
    "Rose": 840000000000009007,
    "Turquoise": 840000000000009008,
    "Orange Topaz": 840000000000009009,
    "Jet": 840000000000009010,
    "Amethyst": 840000000000009011,
    "Quartz": 840000000000009012,
}

ATTUNEMENT_BUFF_ID_BY_CRYSTAL_KEY = {
    "Diamond": 840000000000009101,
    "Emerald": 840000000000009102,
    "Citrine": 840000000000009103,
    "Ruby": 840000000000009104,
    "Fire Opal": 840000000000009105,
    "Sapphire": 840000000000009106,
    "Rose": 840000000000009107,
    "Turquoise": 840000000000009108,
    "Orange Topaz": 840000000000009109,
    "Jet": 840000000000009110,
    "Amethyst": 840000000000009111,
    "Quartz": 840000000000009112,
}

_ATTUNEMENT_BY_SIM_ID: Dict[int, Dict[str, Dict[str, int]]] = {}


def _normalize_object_text(value) -> str:
    return str(value or "").strip().lower().replace("_", "").replace(" ", "")


def _unique_texts(values: Iterable[object]) -> Tuple[str, ...]:
    seen = set()
    resolved = []
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        resolved.append(text)
    return tuple(resolved)


def _extract_text_fragments(value, *, max_depth: int = 3, _depth: int = 0, _seen_ids=None) -> Tuple[str, ...]:
    if value is None or _depth > max_depth:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, (int, float, bool)):
        return ()

    if _seen_ids is None:
        _seen_ids = set()
    value_id = id(value)
    if value_id in _seen_ids:
        return ()
    _seen_ids.add(value_id)

    fragments = []
    if isinstance(value, MappingABC):
        for key, nested in value.items():
            fragments.extend(
                _extract_text_fragments(
                    key,
                    max_depth=max_depth,
                    _depth=_depth + 1,
                    _seen_ids=_seen_ids,
                )
            )
            fragments.extend(
                _extract_text_fragments(
                    nested,
                    max_depth=max_depth,
                    _depth=_depth + 1,
                    _seen_ids=_seen_ids,
                )
            )
        return _unique_texts(fragments)

    if isinstance(value, (tuple, list, set, frozenset)):
        for nested in value:
            fragments.extend(
                _extract_text_fragments(
                    nested,
                    max_depth=max_depth,
                    _depth=_depth + 1,
                    _seen_ids=_seen_ids,
                )
            )
        return _unique_texts(fragments)

    for attr_name in (
        "name",
        "debug_name",
        "state",
        "state_value",
        "value",
        "current_value",
        "active_value",
        "state_name",
        "value_name",
    ):
        nested = getattr(value, attr_name, None)
        if nested is None:
            continue
        fragments.extend(
            _extract_text_fragments(
                nested,
                max_depth=max_depth,
                _depth=_depth + 1,
                _seen_ids=_seen_ids,
            )
        )

    for method_name in ("values", "items", "keys"):
        method = getattr(value, method_name, None)
        if not callable(method):
            continue
        try:
            nested_values = method()
        except TypeError:
            continue
        except Exception:
            continue
        fragments.extend(
            _extract_text_fragments(
                nested_values,
                max_depth=max_depth,
                _depth=_depth + 1,
                _seen_ids=_seen_ids,
            )
        )

    try:
        nested_dict = vars(value)
    except Exception:
        nested_dict = None
    if nested_dict:
        fragments.extend(
            _extract_text_fragments(
                nested_dict,
                max_depth=max_depth,
                _depth=_depth + 1,
                _seen_ids=_seen_ids,
            )
        )

    class_name = getattr(getattr(value, "__class__", None), "__name__", None)
    if class_name:
        fragments.append(class_name)
    try:
        rendered = str(value)
    except Exception:
        rendered = None
    if rendered:
        fragments.append(rendered)
    return _unique_texts(fragments)


def _state_text_candidates(obj) -> Tuple[str, ...]:
    state_roots = []
    for attr_name in (
        "state_component",
        "states",
        "state_values",
        "current_states",
        "tooltip_component",
    ):
        value = getattr(obj, attr_name, None)
        if value is not None:
            state_roots.append(value)
    return _unique_texts(
        fragment
        for root in state_roots
        for fragment in _extract_text_fragments(root)
    )


def _object_text_candidates(obj) -> Tuple[str, ...]:
    definition = getattr(obj, "definition", None)
    return _unique_texts(
        (
            getattr(definition, "name", None),
            getattr(obj, "name", None),
            getattr(obj, "debug_name", None),
            getattr(getattr(obj, "__class__", None), "__name__", None),
            *_state_text_candidates(obj),
        )
    )


def _big3_sign_names(chart_payload: Mapping[str, object]) -> Tuple[str, str, str]:
    return (
        SIGNS[int(chart_payload["sun_sign_index"]) % 12],
        SIGNS[int(chart_payload["moon_sign_index"]) % 12],
        SIGNS[int(chart_payload["rising_sign_index"]) % 12],
    )


def allowed_crystal_keys_for_payload(chart_payload: Mapping[str, object]) -> Tuple[str, ...]:
    keys = {
        PRIMARY_CRYSTAL_BY_SIGN[sign_name]
        for sign_name in _big3_sign_names(chart_payload)
        if sign_name in PRIMARY_CRYSTAL_BY_SIGN
    }
    return tuple(sorted(keys))


def identify_crystal_key(obj) -> Optional[str]:
    normalized = tuple(_normalize_object_text(candidate) for candidate in _object_text_candidates(obj))
    for crystal_key, tokens in CRYSTAL_OBJECT_TOKENS.items():
        for token in tokens:
            normalized_token = _normalize_object_text(token)
            if any(normalized_token in candidate for candidate in normalized):
                return crystal_key
    return None


def _iter_personal_inventory_objects(sim_info) -> Iterable[object]:
    inventory_candidates = []
    inventory = getattr(sim_info, "inventory_component", None)
    if inventory is not None:
        inventory_candidates.append(inventory)

    live_sim = None
    for attr_name in ("get_sim_instance", "get_sim_instance_allow_hidden", "get_sim_instance_even_if_hidden"):
        method = getattr(sim_info, attr_name, None)
        if not callable(method):
            continue
        try:
            live_sim = method()
        except TypeError:
            try:
                live_sim = method(None)
            except Exception:
                live_sim = None
        except Exception:
            live_sim = None
        if live_sim is not None:
            break

    if live_sim is None:
        for attr_name in ("sim_instance", "_sim_instance", "sim"):
            live_sim = getattr(sim_info, attr_name, None)
            if live_sim is not None:
                break

    live_inventory = getattr(live_sim, "inventory_component", None) if live_sim is not None else None
    if live_inventory is not None and live_inventory not in inventory_candidates:
        inventory_candidates.append(live_inventory)

    for inventory in inventory_candidates:
        for method_name in ("inventory_items_gen", "player_try_get_all_inventory_items", "get_all_objects_gen"):
            method = getattr(inventory, method_name, None)
            if callable(method):
                try:
                    resolved = tuple(method())
                except TypeError:
                    try:
                        resolved = tuple(method(None))
                    except Exception:
                        resolved = ()
                except Exception:
                    resolved = ()
                if resolved:
                    return resolved
        try:
            resolved = tuple(inventory)
        except Exception:
            resolved = ()
        if resolved:
            return resolved
    return ()


def chart_payload_for_sim(sim_info) -> Optional[Dict[str, object]]:
    sim_id = getattr(sim_info, "sim_id", None)
    if sim_id is None:
        return None
    payload = get_global_transit_service().get_chart_record_payload(int(sim_id))
    return payload if isinstance(payload, dict) else None


def _sim_has_buff(sim_info, buff_id: int) -> bool:
    try:
        from .loot_actions import _sim_has_buff as _loot_actions_sim_has_buff
    except Exception:
        return False
    try:
        return bool(_loot_actions_sim_has_buff(sim_info, int(buff_id)))
    except Exception:
        return False


def _present_buff_keys_for_sim(sim_info, buff_id_by_crystal_key: Mapping[str, int]) -> Tuple[str, ...]:
    present = []
    for crystal_key, buff_id in buff_id_by_crystal_key.items():
        if _sim_has_buff(sim_info, int(buff_id)):
            present.append(str(crystal_key))
    return tuple(sorted(present))


def collect_matching_crystal_keys_for_sim(sim_info, *, chart_payload=None) -> Tuple[str, ...]:
    payload = chart_payload if isinstance(chart_payload, Mapping) else chart_payload_for_sim(sim_info)
    if not isinstance(payload, Mapping):
        return ()
    allowed = set(allowed_crystal_keys_for_payload(payload))
    matches = set()
    for obj in _iter_personal_inventory_objects(sim_info):
        crystal_key = identify_crystal_key(obj)
        if crystal_key in allowed:
            matches.add(crystal_key)
    return tuple(sorted(matches))


def debug_crystal_resonance_for_sim(sim_info, *, now_ticks: int = 0) -> Dict[str, object]:
    sim_id = _sim_id(sim_info)
    payload = chart_payload_for_sim(sim_info)
    allowed_keys = allowed_crystal_keys_for_payload(payload) if isinstance(payload, Mapping) else ()
    matching_keys = collect_matching_crystal_keys_for_sim(sim_info, chart_payload=payload)
    attuned_keys = active_attunement_keys_for_sim(sim_id, now_ticks=now_ticks) if sim_id is not None else ()
    present_passive_buff_keys = _present_buff_keys_for_sim(sim_info, PASSIVE_BUFF_ID_BY_CRYSTAL_KEY)
    present_attunement_buff_keys = _present_buff_keys_for_sim(sim_info, ATTUNEMENT_BUFF_ID_BY_CRYSTAL_KEY)
    inventory_debug = []
    for obj in _iter_personal_inventory_objects(sim_info):
        candidate_strings = _object_text_candidates(obj)
        inventory_debug.append(
            {
                "object_id": int(getattr(obj, "id", None) or getattr(obj, "guid64", None) or 0),
                "definition_name": str(getattr(getattr(obj, "definition", None), "name", "") or ""),
                "candidate_strings": candidate_strings,
                "resolved_crystal_key": identify_crystal_key(obj),
            }
        )
    return {
        "addon_active": bool(is_crystal_resonance_addon_active()),
        "sim_id": sim_id,
        "chart_record_present": isinstance(payload, Mapping),
        "allowed_keys": tuple(sorted(allowed_keys)),
        "matching_keys": tuple(sorted(matching_keys)),
        "attuned_keys": tuple(sorted(attuned_keys)),
        "present_passive_buff_keys": tuple(sorted(present_passive_buff_keys)),
        "present_attunement_buff_keys": tuple(sorted(present_attunement_buff_keys)),
        "inventory_objects": inventory_debug,
    }


def register_gifted_attunement(
    sim_id: int,
    crystal_key: str,
    *,
    object_id: int,
    now_ticks: int,
    duration_ticks: int,
) -> None:
    _ATTUNEMENT_BY_SIM_ID.setdefault(int(sim_id), {})[str(crystal_key)] = {
        "object_id": int(object_id),
        "expires_at_ticks": int(now_ticks + duration_ticks),
    }


def active_attunement_keys_for_sim(sim_id: int, *, now_ticks: int) -> Tuple[str, ...]:
    active = []
    for crystal_key, state in (_ATTUNEMENT_BY_SIM_ID.get(int(sim_id)) or {}).items():
        if int(state.get("expires_at_ticks", 0)) > int(now_ticks):
            active.append(str(crystal_key))
    return tuple(sorted(active))


def expire_attunements(*, now_ticks: int) -> None:
    for sim_id, crystal_states in tuple(_ATTUNEMENT_BY_SIM_ID.items()):
        for crystal_key, state in tuple(crystal_states.items()):
            if int(state.get("expires_at_ticks", 0)) <= int(now_ticks):
                crystal_states.pop(crystal_key, None)
        if not crystal_states:
            _ATTUNEMENT_BY_SIM_ID.pop(sim_id, None)


def _sim_id(sim_info) -> Optional[int]:
    for attr_name in ("sim_id", "id", "guid64"):
        value = getattr(sim_info, attr_name, None)
        if value is None:
            continue
        try:
            return int(value)
        except Exception:
            continue
    return None


def sync_crystal_resonance(sim_infos: Optional[Sequence[object]] = None, *, now_ticks: int = 0) -> Dict[str, int]:
    summary = {
        "sims_seen": 0,
        "passive_buffs_added": 0,
        "passive_buffs_removed": 0,
        "attunement_buffs_added": 0,
        "attunement_buffs_removed": 0,
        "attunement_expired": 0,
    }
    if not is_crystal_resonance_addon_active():
        return summary

    from .loot_actions import _add_buff_if_missing, _remove_buff_if_present

    for sim_info in tuple(sim_infos or ()):
        sim_id = _sim_id(sim_info)
        if sim_id is None:
            continue
        summary["sims_seen"] += 1
        matching_keys = set(collect_matching_crystal_keys_for_sim(sim_info))
        attuned_keys = set(active_attunement_keys_for_sim(sim_id, now_ticks=now_ticks))

        for crystal_key, buff_id in PASSIVE_BUFF_ID_BY_CRYSTAL_KEY.items():
            if crystal_key in matching_keys and crystal_key not in attuned_keys:
                if _add_buff_if_missing(sim_info, int(buff_id)):
                    summary["passive_buffs_added"] += 1
            else:
                if _remove_buff_if_present(sim_info, int(buff_id)):
                    summary["passive_buffs_removed"] += 1

        for crystal_key, buff_id in ATTUNEMENT_BUFF_ID_BY_CRYSTAL_KEY.items():
            if crystal_key in matching_keys and crystal_key in attuned_keys:
                if _add_buff_if_missing(sim_info, int(buff_id)):
                    summary["attunement_buffs_added"] += 1
            else:
                if _remove_buff_if_present(sim_info, int(buff_id)):
                    summary["attunement_buffs_removed"] += 1

    before = sum(len(states) for states in _ATTUNEMENT_BY_SIM_ID.values())
    expire_attunements(now_ticks=now_ticks)
    after = sum(len(states) for states in _ATTUNEMENT_BY_SIM_ID.values())
    summary["attunement_expired"] = max(0, before - after)
    return summary
