"""Full-chart element and mode composition helpers.

This layer sits on top of existing planetary sign assignments. It does not
assign signs, move planets, read houses, or touch Sims 4 APIs directly.
"""

from __future__ import annotations

from typing import Callable, Dict, List, Mapping, Optional

from .transit_core import SIGNS


CLASSICAL_PLANETS = (
    "Sun",
    "Moon",
    "Mercury",
    "Venus",
    "Mars",
    "Jupiter",
    "Saturn",
)

ELEMENT_ORDER = ("fire", "earth", "air", "water")
MODE_ORDER = ("cardinal", "fixed", "mutable")
DEFAULT_DOMINANT_TIE_BEHAVIOR = "none"

SIGN_TO_ELEMENT = {
    "Aries": "fire",
    "Taurus": "earth",
    "Gemini": "air",
    "Cancer": "water",
    "Leo": "fire",
    "Virgo": "earth",
    "Libra": "air",
    "Scorpio": "water",
    "Sagittarius": "fire",
    "Capricorn": "earth",
    "Aquarius": "air",
    "Pisces": "water",
}

SIGN_TO_MODE = {
    "Aries": "cardinal",
    "Cancer": "cardinal",
    "Libra": "cardinal",
    "Capricorn": "cardinal",
    "Taurus": "fixed",
    "Leo": "fixed",
    "Scorpio": "fixed",
    "Aquarius": "fixed",
    "Gemini": "mutable",
    "Virgo": "mutable",
    "Sagittarius": "mutable",
    "Pisces": "mutable",
}

_SIGN_NAME_BY_LOWER = {name.lower(): name for name in SIGN_TO_ELEMENT}
_PLANET_NAME_BY_LOWER = {name.lower(): name for name in CLASSICAL_PLANETS}


def _normalize_sign_name(sign_name) -> Optional[str]:
    if sign_name is None:
        return None
    text = str(sign_name).strip()
    if not text:
        return None
    return _SIGN_NAME_BY_LOWER.get(text.lower())


def _normalize_planet_name(planet_name) -> Optional[str]:
    if planet_name is None:
        return None
    text = str(planet_name).strip()
    if not text:
        return None
    return _PLANET_NAME_BY_LOWER.get(text.lower())


def _zero_totals(keys) -> Dict[str, int]:
    return {str(key): 0 for key in keys}


def _safe_int(value, default_value=0) -> int:
    try:
        return int(value)
    except Exception:
        return int(default_value)


def _ranking_order_for_key(key: str) -> int:
    if key in ELEMENT_ORDER:
        return int(ELEMENT_ORDER.index(key))
    if key in MODE_ORDER:
        return int(MODE_ORDER.index(key))
    return len(ELEMENT_ORDER) + len(MODE_ORDER)


def _leaders_from_totals(totals: Mapping[str, int]) -> List[str]:
    ranking = rank_totals(totals)
    if not ranking:
        return []
    top_value = _safe_int(totals.get(ranking[0], 0), 0)
    return [key for key in ranking if _safe_int(totals.get(key, 0), 0) == top_value and top_value > 0]


def _spread_from_totals(totals: Mapping[str, int]) -> int:
    counts = [_safe_int(value, 0) for value in totals.values()]
    if not counts:
        return 0
    return max(counts) - min(counts)


def _is_balanced_totals(totals: Mapping[str, int]) -> bool:
    if not totals:
        return True
    return _spread_from_totals(totals) <= 1


def _composition_from_input(value: Mapping[str, object]) -> Dict[str, object]:
    if not isinstance(value, Mapping):
        return build_chart_composition({})
    if "planets" in value and "element_totals" in value and "mode_totals" in value:
        return dict(value)
    return build_chart_composition(value)


def _copy_totals_with_defaults(source: Mapping[str, object], order) -> Dict[str, int]:
    totals = _zero_totals(order)
    if not isinstance(source, Mapping):
        return totals
    for key in order:
        totals[str(key)] = _safe_int(source.get(key, 0), 0)
    return totals


def _normalize_tie_behavior(tie_behavior) -> str:
    text = str(tie_behavior or DEFAULT_DOMINANT_TIE_BEHAVIOR).strip().lower()
    if text in ("balanced", "leaders", "none", "top"):
        return text
    return DEFAULT_DOMINANT_TIE_BEHAVIOR


def _resolve_dominant_from_totals(
    totals: Mapping[str, int],
    *,
    tie_behavior=DEFAULT_DOMINANT_TIE_BEHAVIOR,
):
    leaders = _leaders_from_totals(totals)
    if len(leaders) == 1:
        return str(leaders[0])

    normalized_tie_behavior = _normalize_tie_behavior(tie_behavior)
    if normalized_tie_behavior == "top":
        ranking = rank_totals(totals)
        if ranking:
            return str(ranking[0])
        return None
    if normalized_tie_behavior == "balanced":
        return "balanced"
    if normalized_tie_behavior == "leaders":
        return leaders
    return None


def get_sign_element(sign_name) -> Optional[str]:
    normalized_sign = _normalize_sign_name(sign_name)
    if normalized_sign is None:
        return None
    return SIGN_TO_ELEMENT.get(normalized_sign)


def get_sign_mode(sign_name) -> Optional[str]:
    normalized_sign = _normalize_sign_name(sign_name)
    if normalized_sign is None:
        return None
    return SIGN_TO_MODE.get(normalized_sign)


def calculate_element_totals(planet_signs_or_composition: Mapping[str, object]) -> Dict[str, int]:
    composition = _composition_from_input(planet_signs_or_composition)
    return _copy_totals_with_defaults(composition.get("element_totals") or {}, ELEMENT_ORDER)


def calculate_mode_totals(planet_signs_or_composition: Mapping[str, object]) -> Dict[str, int]:
    composition = _composition_from_input(planet_signs_or_composition)
    return _copy_totals_with_defaults(composition.get("mode_totals") or {}, MODE_ORDER)


def rank_totals(totals_dict: Mapping[str, int]) -> List[str]:
    if not isinstance(totals_dict, Mapping):
        return []

    sortable = []
    for key, value in totals_dict.items():
        normalized_key = str(key)
        sortable.append(
            (
                normalized_key,
                _safe_int(value, 0),
                _ranking_order_for_key(normalized_key),
            )
        )

    sortable.sort(key=lambda item: (-item[1], item[2], item[0]))
    return [item[0] for item in sortable]


def get_dominant_element(
    chart_composition: Mapping[str, object],
    *,
    tie_behavior=DEFAULT_DOMINANT_TIE_BEHAVIOR,
):
    totals = calculate_element_totals(chart_composition)
    return _resolve_dominant_from_totals(totals, tie_behavior=tie_behavior)


def get_dominant_mode(
    chart_composition: Mapping[str, object],
    *,
    tie_behavior=DEFAULT_DOMINANT_TIE_BEHAVIOR,
):
    totals = calculate_mode_totals(chart_composition)
    return _resolve_dominant_from_totals(totals, tie_behavior=tie_behavior)


def build_chart_composition(planet_signs: Mapping[str, object]) -> Dict[str, object]:
    normalized_signs_by_planet = {}
    unexpected_planets = {}

    if isinstance(planet_signs, Mapping):
        for raw_planet_name, raw_sign_name in planet_signs.items():
            normalized_planet = _normalize_planet_name(raw_planet_name)
            if normalized_planet is None:
                unexpected_planets[str(raw_planet_name)] = raw_sign_name
                continue
            normalized_signs_by_planet[normalized_planet] = raw_sign_name
    else:
        planet_signs = {}

    planets = {}
    missing_planets = []
    invalid_signs = {}
    element_totals = _zero_totals(ELEMENT_ORDER)
    mode_totals = _zero_totals(MODE_ORDER)

    for planet_name in CLASSICAL_PLANETS:
        raw_sign_name = normalized_signs_by_planet.get(planet_name)
        normalized_sign_name = _normalize_sign_name(raw_sign_name)
        element_name = get_sign_element(normalized_sign_name)
        mode_name = get_sign_mode(normalized_sign_name)

        planets[planet_name] = {
            "sign": normalized_sign_name,
            "element": element_name,
            "mode": mode_name,
        }

        if normalized_sign_name is None:
            if raw_sign_name in (None, ""):
                missing_planets.append(planet_name)
            else:
                invalid_signs[planet_name] = raw_sign_name
            continue

        if element_name is not None:
            element_totals[element_name] += 1
        if mode_name is not None:
            mode_totals[mode_name] += 1

    expected_planet_count = len(CLASSICAL_PLANETS)
    recognized_planet_count = sum(1 for data in planets.values() if data["sign"] is not None)
    element_ranking = rank_totals(element_totals)
    mode_ranking = rank_totals(mode_totals)
    element_leaders = _leaders_from_totals(element_totals)
    mode_leaders = _leaders_from_totals(mode_totals)

    return {
        "planets": planets,
        "element_totals": element_totals,
        "mode_totals": mode_totals,
        "element_ranking": element_ranking,
        "mode_ranking": mode_ranking,
        "element_leaders": element_leaders,
        "mode_leaders": mode_leaders,
        "element_tie": len(element_leaders) > 1,
        "mode_tie": len(mode_leaders) > 1,
        "element_spread": _spread_from_totals(element_totals),
        "mode_spread": _spread_from_totals(mode_totals),
        "element_is_balanced": _is_balanced_totals(element_totals),
        "mode_is_balanced": _is_balanced_totals(mode_totals),
        "recognized_planet_count": int(recognized_planet_count),
        "expected_planet_count": int(expected_planet_count),
        "is_complete_chart": recognized_planet_count == expected_planet_count and not invalid_signs,
        "missing_planets": missing_planets,
        "invalid_signs": invalid_signs,
        "unexpected_planets": unexpected_planets,
    }


def build_chart_composition_for_sim(
    sim_info,
    planet_sign_getter: Optional[Callable[[object], Mapping[str, object]]] = None,
) -> Dict[str, object]:
    getter = planet_sign_getter
    if getter is None:
        getter = globals().get("get_planet_signs_for_sim")
    if not callable(getter):
        raise ValueError(
            "build_chart_composition_for_sim requires your existing "
            "get_planet_signs_for_sim(sim_info) callable."
        )

    planet_signs = getter(sim_info)
    if not isinstance(planet_signs, Mapping):
        raise ValueError("planet_sign_getter must return a mapping of planet names to sign names.")
    return build_chart_composition(planet_signs)


def build_chart_composition_from_sign_indexes(
    sign_indexes_by_planet: Mapping[str, object],
) -> Dict[str, object]:
    planet_signs = {}
    if isinstance(sign_indexes_by_planet, Mapping):
        for raw_planet_name, raw_sign_index in sign_indexes_by_planet.items():
            normalized_planet = _normalize_planet_name(raw_planet_name)
            if normalized_planet is None:
                planet_signs[str(raw_planet_name)] = raw_sign_index
                continue
            try:
                sign_name = SIGNS[int(raw_sign_index) % len(SIGNS)]
            except Exception:
                sign_name = raw_sign_index
            planet_signs[normalized_planet] = sign_name
    return build_chart_composition(planet_signs)


def build_chart_composition_from_chart_payload(
    payload: Mapping[str, object],
) -> Dict[str, object]:
    if not isinstance(payload, Mapping):
        return build_chart_composition({})

    metadata = payload.get("metadata")
    if isinstance(metadata, Mapping):
        existing = metadata.get("chart_composition")
        if isinstance(existing, Mapping):
            return dict(existing)

        body_sign_names = metadata.get("body_sign_name_by_name")
        if isinstance(body_sign_names, Mapping):
            return build_chart_composition(body_sign_names)

        body_sign_indexes = metadata.get("body_sign_index_by_name")
        if isinstance(body_sign_indexes, Mapping):
            return build_chart_composition_from_sign_indexes(body_sign_indexes)

    house_by_body = payload.get("house_by_body")
    house_sign_by_index = payload.get("house_sign_by_index")
    if isinstance(house_by_body, Mapping) and isinstance(house_sign_by_index, Mapping):
        sign_indexes_by_planet = {}
        for body_name, house_index in house_by_body.items():
            try:
                sign_index = house_sign_by_index.get(int(house_index))
            except Exception:
                sign_index = None
            if sign_index is None:
                continue
            sign_indexes_by_planet[str(body_name)] = sign_index
        if sign_indexes_by_planet:
            return build_chart_composition_from_sign_indexes(sign_indexes_by_planet)

    sign_indexes_by_planet = {}
    for planet_name, payload_key in (
        ("Sun", "sun_sign_index"),
        ("Moon", "moon_sign_index"),
    ):
        if payload_key in payload:
            sign_indexes_by_planet[planet_name] = payload.get(payload_key)
    return build_chart_composition_from_sign_indexes(sign_indexes_by_planet)


def get_legacy_single_element(chart_composition: Mapping[str, object]) -> Optional[str]:
    # Deprecated compatibility shim: older Sun-only logic expected a single
    # element value. We only surface one when the chart has a unique leader.
    dominant = get_dominant_element(chart_composition, tie_behavior="none")
    return dominant if isinstance(dominant, str) else None


def get_legacy_single_mode(chart_composition: Mapping[str, object]) -> Optional[str]:
    # Deprecated compatibility shim: older Sun-only logic expected a single
    # mode value. We only surface one when the chart has a unique leader.
    dominant = get_dominant_mode(chart_composition, tie_behavior="none")
    return dominant if isinstance(dominant, str) else None


def build_chart_composition_placeholders(chart_composition: Mapping[str, object]) -> Dict[str, object]:
    element_leaders = list(chart_composition.get("element_leaders") or [])
    mode_leaders = list(chart_composition.get("mode_leaders") or [])
    element_totals = dict(chart_composition.get("element_totals") or {})
    mode_totals = dict(chart_composition.get("mode_totals") or {})

    notification_lines = [
        "Element emphasis: {0}".format(", ".join(element_leaders) if element_leaders else "none"),
        "Mode emphasis: {0}".format(", ".join(mode_leaders) if mode_leaders else "none"),
    ]

    buff_tokens = []
    hidden_trait_tokens = []
    if element_leaders:
        buff_tokens.extend("chart_element_{0}_emphasis".format(element) for element in element_leaders)
    if mode_leaders:
        buff_tokens.extend("chart_mode_{0}_emphasis".format(mode) for mode in mode_leaders)
    if bool(chart_composition.get("element_is_balanced")):
        hidden_trait_tokens.append("chart_element_balance")
    if bool(chart_composition.get("mode_is_balanced")):
        hidden_trait_tokens.append("chart_mode_balance")

    return {
        "notification_text": "\n".join(notification_lines),
        "buff_tokens": buff_tokens,
        "hidden_trait_tokens": hidden_trait_tokens,
        "interpretation_context": {
            "element_ranking": list(chart_composition.get("element_ranking") or []),
            "mode_ranking": list(chart_composition.get("mode_ranking") or []),
            "element_totals": element_totals,
            "mode_totals": mode_totals,
            "planets": dict(chart_composition.get("planets") or {}),
        },
    }


__all__ = [
    "CLASSICAL_PLANETS",
    "DEFAULT_DOMINANT_TIE_BEHAVIOR",
    "ELEMENT_ORDER",
    "MODE_ORDER",
    "SIGN_TO_ELEMENT",
    "SIGN_TO_MODE",
    "build_chart_composition",
    "build_chart_composition_for_sim",
    "build_chart_composition_from_chart_payload",
    "build_chart_composition_from_sign_indexes",
    "build_chart_composition_placeholders",
    "calculate_element_totals",
    "calculate_mode_totals",
    "get_dominant_element",
    "get_dominant_mode",
    "get_legacy_single_element",
    "get_legacy_single_mode",
    "get_sign_element",
    "get_sign_mode",
    "rank_totals",
]
