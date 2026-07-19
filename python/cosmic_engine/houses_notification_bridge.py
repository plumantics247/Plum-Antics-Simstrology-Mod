"""Bridge helpers for existing Houses notification flow.

Purpose:
- keep current XML notification loots intact
- provide Python payloads with transit body sign+house mapping
- map rising trait ids to the existing per-rising notification loot ids
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Mapping, Optional, Sequence

from .transit_core import (
    BODY_NAMES,
    HOUSES,
    OPTIONAL_OUTER_BODY_NAMES,
    SIGNS,
    build_house_sign_map_for_rising,
    resolve_house_sign_map_from_marker_ids,
)
from .transit_service import CosmicTransitService


RISING_SIGN_TRAIT_ID_TO_SIGN_INDEX: Dict[int, int] = {
    2297406366: 0,             # Aries (Big 3 visible)
    10264073582958847151: 0,   # Aries
    16761871892616728776: 0,   # Aries Marker
    2588878312: 1,             # Taurus (Big 3 visible)
    9813396616419578473: 1,    # Taurus
    11175056517398517295: 1,   # Taurus Marker
    4242808797: 2,             # Gemini (Big 3 visible)
    11246474050470629778: 2,   # Gemini
    9692131357347781131: 2,    # Gemini Marker
    2154635568: 3,             # Cancer (Big 3 visible)
    15034935288076959985: 3,   # Cancer
    1381248803109246197: 3,    # Cancer Marker
    3739357428: 4,             # Leo (Big 3 visible)
    17746946338361058941: 4,   # Leo
    3793302558151472525: 4,    # Leo Marker
    2665561705: 5,             # Virgo (Big 3 visible)
    12634547309226959906: 5,   # Virgo
    5430967048860416012: 5,    # Virgo Marker
    3123976786: 6,             # Libra (Big 3 visible)
    18147682633923242291: 6,   # Libra
    2833538433433103528: 6,    # Libra Marker
    3923158167: 7,             # Scorpio (Big 3 visible)
    14856533790243246112: 7,   # Scorpio
    15335252023511564677: 7,   # Scorpio Marker
    2405249506: 8,             # Sagittarius (Big 3 visible)
    15868666942167378891: 8,   # Sagittarius
    17200683087698565611: 8,   # Sagittarius Marker
    3178572581: 9,             # Capricorn (Big 3 visible)
    16969997717301751310: 9,   # Capricorn
    9263783293184932856: 9,    # Capricorn Marker
    2243949835: 10,            # Aquarius (Big 3 visible)
    12362127493914262916: 10,  # Aquarius
    2536309387367529460: 10,   # Aquarius Marker
    3588503643: 11,            # Pisces (Big 3 visible)
    13957571496592220960: 11,  # Pisces
    5851936451986304843: 11,   # Pisces Marker
}

SIGN_INDEX_TO_EXISTING_NOTIFICATION_LOOT_ID: Dict[int, int] = {
    0: 97932201534315430,            # Aries
    1: 15905974288357010002,         # Taurus
    2: 11499159365287496408,         # Gemini
    3: 1039661398921854596,          # Cancer
    4: 4431438872431254724,          # Leo
    5: 11485692368206791108,         # Virgo
    6: 18055358178431099330,         # Libra
    7: 7982241382578648746,          # Scorpio
    8: 6399055199630821525,          # Sagittarius
    9: 1117396741393882353,          # Capricorn
    10: 11496171549410926301,        # Aquarius
    11: 10355534268030172892,        # Pisces
}


def resolve_rising_sign_index_from_trait_ids(trait_ids: Iterable[int]) -> Optional[int]:
    for trait_id in trait_ids:
        idx = RISING_SIGN_TRAIT_ID_TO_SIGN_INDEX.get(int(trait_id))
        if idx is not None:
            return idx
    return None


def resolve_existing_houses_notification_loot_id(trait_ids: Iterable[int]) -> Optional[int]:
    rising_sign_index = resolve_rising_sign_index_from_trait_ids(trait_ids)
    if rising_sign_index is None:
        return None
    return SIGN_INDEX_TO_EXISTING_NOTIFICATION_LOOT_ID.get(rising_sign_index)


def _build_house_sign_map(
    *,
    rising_sign_index: int,
    marker_trait_ids: Optional[Sequence[int]] = None,
) -> Dict[int, int]:
    if marker_trait_ids:
        resolved = resolve_house_sign_map_from_marker_ids(marker_trait_ids)
        # If markers are incomplete, fall back to deterministic rising map.
        if len(resolved) == 12:
            return resolved
    return build_house_sign_map_for_rising(rising_sign_index)


def build_transit_chart_lines(
    body_chart: Mapping[str, Mapping[str, object]],
    *,
    body_names: Optional[Sequence[str]] = None,
) -> List[str]:
    lines: List[str] = []
    names = BODY_NAMES if body_names is None else tuple(body_names)
    for body in names:
        row = body_chart.get(body, {})
        sign_name = str(row.get("sign_name", "?"))
        house_index = row.get("house_index")
        if isinstance(house_index, int):
            house_name = HOUSES[house_index]
            lines.append(f"{body}: {sign_name} ({house_name} House)")
        else:
            lines.append(f"{body}: {sign_name}")
    return lines


def build_outer_collective_weather_lines(
    body_chart: Mapping[str, Mapping[str, object]],
    *,
    body_names: Optional[Sequence[str]] = None,
) -> List[str]:
    lines: List[str] = []
    names = OPTIONAL_OUTER_BODY_NAMES if body_names is None else tuple(body_names)
    for body in names:
        row = body_chart.get(body, {})
        sign_name = str(row.get("sign_name", "?"))
        lines.append(f"{body} is in {sign_name}.")
    return lines


def build_houses_readout_payload(
    transit_service: CosmicTransitService,
    *,
    actor_trait_ids: Sequence[int],
    actor_marker_trait_ids: Optional[Sequence[int]] = None,
) -> Dict[str, object]:
    """Build a payload for chart read interactions.

    This preserves your existing rising notification flow by returning the
    matching XML loot id, while also adding computed transit output.
    """
    rising_sign_index = resolve_rising_sign_index_from_trait_ids(actor_trait_ids)
    if rising_sign_index is None:
        return {
            "ok": False,
            "error": "missing_rising_trait",
            "existing_notification_loot_id": None,
            "body_chart": {},
            "body_lines": [],
            "outer_planets_active": False,
            "outer_weather_lines": [],
        }

    house_sign_map = _build_house_sign_map(
        rising_sign_index=rising_sign_index,
        marker_trait_ids=actor_marker_trait_ids,
    )
    active_body_names = tuple(transit_service.active_body_names())
    body_chart = transit_service.chart_for_house_sign_map(house_sign_map)
    base_body_names = tuple(body for body in active_body_names if body in BODY_NAMES)
    outer_body_names = tuple(
        body for body in active_body_names if body in OPTIONAL_OUTER_BODY_NAMES
    )
    body_lines = build_transit_chart_lines(body_chart, body_names=base_body_names)
    outer_weather_lines = build_outer_collective_weather_lines(
        body_chart,
        body_names=outer_body_names,
    )

    return {
        "ok": True,
        "rising_sign_index": rising_sign_index,
        "rising_sign_name": SIGNS[rising_sign_index],
        "existing_notification_loot_id": SIGN_INDEX_TO_EXISTING_NOTIFICATION_LOOT_ID[
            rising_sign_index
        ],
        "body_chart": body_chart,
        "body_lines": body_lines,
        "outer_planets_active": bool(outer_body_names),
        "outer_weather_lines": outer_weather_lines,
    }
