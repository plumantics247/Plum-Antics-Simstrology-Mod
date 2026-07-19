from __future__ import annotations

from typing import Dict, Optional, Tuple

from .sign_compatibility_runtime_seed import (
    CLASHING_POOL_BY_ELEMENT,
    ELEMENT_BY_SIGN_INDEX,
    SAME_ELEMENT_POOL_BY_ELEMENT,
    normalize_sign_index,
)


LANE_NAMES = ("Sun", "Moon", "Rising")
STATE_NAMES = ("Compatible", "Neutral", "Incompatible")
COMPATIBLE = "Compatible"
NEUTRAL = "Neutral"
INCOMPATIBLE = "Incompatible"

RELBIT_ID_BY_LANE_STATE = {
    "Sun": {
        "Compatible": 830000000000043001,
        "Neutral": 830000000000043002,
        "Incompatible": 830000000000043003,
    },
    "Moon": {
        "Compatible": 830000000000043011,
        "Neutral": 830000000000043012,
        "Incompatible": 830000000000043013,
    },
    "Rising": {
        "Compatible": 830000000000043021,
        "Neutral": 830000000000043022,
        "Incompatible": 830000000000043023,
    },
}

VISIBLE_BUFF_ID_BY_LANE_STATE = {
    "Sun": {
        "Compatible": 830000000000042101,
        "Neutral": 830000000000042102,
        "Incompatible": 830000000000042103,
    },
    "Moon": {
        "Compatible": 830000000000042111,
        "Neutral": 830000000000042112,
        "Incompatible": 830000000000042113,
    },
    "Rising": {
        "Compatible": 830000000000042121,
        "Neutral": 830000000000042122,
        "Incompatible": 830000000000042123,
    },
}

SIGN_INDEX_KEY_BY_LANE = {
    "Sun": "sun_sign_index",
    "Moon": "moon_sign_index",
    "Rising": "rising_sign_index",
}


def resolve_lane_state(actor_sign_index, target_sign_index) -> Optional[str]:
    actor_index = normalize_sign_index(actor_sign_index)
    target_index = normalize_sign_index(target_sign_index)
    if actor_index is None or target_index is None:
        return None
    actor_element = ELEMENT_BY_SIGN_INDEX[int(actor_index)]
    if int(target_index) in SAME_ELEMENT_POOL_BY_ELEMENT[str(actor_element)]:
        return COMPATIBLE
    if int(target_index) in CLASHING_POOL_BY_ELEMENT[str(actor_element)]:
        return INCOMPATIBLE
    return NEUTRAL


def build_pair_relbit_seed_plan(*, actor_chart, target_chart) -> Dict[str, object]:
    lanes = {}
    for lane_name in LANE_NAMES:
        sign_key = SIGN_INDEX_KEY_BY_LANE[lane_name]
        state = resolve_lane_state(
            (actor_chart or {}).get(sign_key),
            (target_chart or {}).get(sign_key),
        )
        if state is None:
            continue
        lanes[lane_name] = {
            "state": state,
            "relbit_id": int(RELBIT_ID_BY_LANE_STATE[lane_name][state]),
            "visible_buff_id": int(VISIBLE_BUFF_ID_BY_LANE_STATE[lane_name][state]),
        }
    return {
        "ok": bool(lanes),
        "reason": "resolved" if lanes else "missing_big3",
        "lanes": lanes,
    }


def changed_lane_names(
    existing_indexes: Dict[str, int], expected_indexes: Dict[str, int]
) -> Tuple[str, ...]:
    changed = []
    for lane_name in LANE_NAMES:
        sign_key = SIGN_INDEX_KEY_BY_LANE[lane_name]
        existing_value = (existing_indexes or {}).get(
            sign_key, (existing_indexes or {}).get(lane_name)
        )
        expected_value = (expected_indexes or {}).get(
            sign_key, (expected_indexes or {}).get(lane_name)
        )
        if normalize_sign_index(existing_value) != normalize_sign_index(expected_value):
            changed.append(lane_name)
    return tuple(changed)
