"""Shared natal chart record and builder helpers for Big 3 runtime.

This module is intentionally payload-compatible with AstroCore charting.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import random
from typing import Dict, Mapping, Optional

from .types import SIGNS

try:
    from cosmic_engine.outer_planets_activation import is_outer_planets_addon_active
except Exception:
    def is_outer_planets_addon_active(*, snippet_manager=None):
        return False

try:
    from cosmic_engine.transit_core import OPTIONAL_OUTER_BODY_NAMES
except Exception:
    OPTIONAL_OUTER_BODY_NAMES = ()

try:
    from cosmic_engine.chart_composition import (
        build_chart_composition_from_sign_indexes,
        get_legacy_single_element,
        get_legacy_single_mode,
    )
except Exception:
    build_chart_composition_from_sign_indexes = None
    get_legacy_single_element = None
    get_legacy_single_mode = None


HOUSES = (
    "First",
    "Second",
    "Third",
    "Fourth",
    "Fifth",
    "Sixth",
    "Seventh",
    "Eighth",
    "Ninth",
    "Tenth",
    "Eleventh",
    "Twelfth",
)

BODY_NAMES = (
    "Sun",
    "Moon",
    "Mercury",
    "Venus",
    "Mars",
    "Jupiter",
    "Saturn",
)

FULL_BODY_ORDER = BODY_NAMES + tuple(
    body_name for body_name in OPTIONAL_OUTER_BODY_NAMES if body_name not in BODY_NAMES
)

FIELD_SOURCE_PLAYER = "player"
FIELD_SOURCE_UNIVERSE = "universe"
FIELD_SOURCE_DERIVED = "derived"
FIELD_SOURCE_RANDOMIZED = "randomized"

MODE_BIG3 = "big3"
MODE_COSMIC = "cosmic"

CLUSTER_NONE = "none"
CLUSTER_MINOR = "minor"
CLUSTER_STRONG = "strong"
CLUSTER_MAJOR = "major"

SIGN_TO_INDEX = {name: index for index, name in enumerate(SIGNS)}
SIGN_TO_INDEX_LOWER = {name.lower(): index for index, name in enumerate(SIGNS)}

_RULER_BY_SIGN_INDEX = {
    0: "Mars",
    1: "Venus",
    2: "Mercury",
    3: "Moon",
    4: "Sun",
    5: "Mercury",
    6: "Venus",
    7: "Mars",
    8: "Jupiter",
    9: "Saturn",
    10: "Saturn",
    11: "Jupiter",
}

_CLUSTER_WEIGHT_BY_BODY = {
    "Sun": 3,
    "Moon": 3,
    "Mercury": 1,
    "Venus": 1,
    "Mars": 1,
    "Jupiter": 1,
    "Saturn": 1,
}


@dataclass(frozen=True)
class ChartCluster:
    sign_index: Optional[int] = None
    score: int = 0
    body_count: int = 0
    tier: str = CLUSTER_NONE


@dataclass(frozen=True)
class ChartRecord:
    sim_id: int
    chart_version: int
    mode_origin: str
    created_at_sim_day: int
    created_age: str
    locked: bool
    sun_sign_index: int
    moon_sign_index: int
    rising_sign_index: int
    house_sign_by_index: Dict[int, int] = field(default_factory=dict)
    house_by_body: Dict[str, int] = field(default_factory=dict)
    chart_ruler_body: str = ""
    source_by_field: Dict[str, str] = field(default_factory=dict)
    cluster: ChartCluster = field(default_factory=ChartCluster)
    metadata: Dict[str, object] = field(default_factory=dict)


def normalize_sign_index(sign_value) -> int:
    if isinstance(sign_value, int):
        return int(sign_value) % 12
    text = str(sign_value).strip().lower()
    if text not in SIGN_TO_INDEX_LOWER:
        raise ValueError("Unknown sign value: {0!r}".format(sign_value))
    return int(SIGN_TO_INDEX_LOWER[text])


def build_house_sign_map_for_rising(rising_sign_index: int) -> Dict[int, int]:
    rising_sign_index = normalize_sign_index(rising_sign_index)
    return {house_index: (rising_sign_index + house_index) % 12 for house_index in range(12)}


def house_for_sign(house_sign_map: Mapping[int, int], sign_index: int) -> Optional[int]:
    target_sign_index = normalize_sign_index(sign_index)
    for house_index, mapped_sign_index in house_sign_map.items():
        if int(mapped_sign_index) % 12 == target_sign_index:
            return int(house_index)
    return None


def chart_ruler_body_for_rising(rising_sign_index: int) -> str:
    return str(_RULER_BY_SIGN_INDEX[normalize_sign_index(rising_sign_index)])


def _resolve_chart_body_names(*, include_outer_planets: Optional[bool] = None):
    if include_outer_planets is None:
        include_outer_planets = is_outer_planets_addon_active()
    return FULL_BODY_ORDER if include_outer_planets else BODY_NAMES


def compute_cluster_signature(
    *,
    house_sign_by_index: Mapping[int, int],
    house_by_body: Mapping[str, int],
) -> ChartCluster:
    score_by_sign = {}  # type: Dict[int, int]
    body_count_by_sign = {}  # type: Dict[int, int]

    for body_name, body_weight in _CLUSTER_WEIGHT_BY_BODY.items():
        house_index = house_by_body.get(body_name)
        if house_index is None:
            continue
        if int(house_index) not in house_sign_by_index:
            continue
        sign_index = int(house_sign_by_index[int(house_index)]) % 12
        score_by_sign[sign_index] = int(score_by_sign.get(sign_index, 0)) + int(body_weight)
        body_count_by_sign[sign_index] = int(body_count_by_sign.get(sign_index, 0)) + 1

    if not score_by_sign:
        return ChartCluster()

    best_sign_index = None
    best_score = -1
    best_body_count = -1
    for sign_index, score in score_by_sign.items():
        body_count = int(body_count_by_sign.get(sign_index, 0))
        if score > best_score or (score == best_score and body_count > best_body_count):
            best_sign_index = int(sign_index)
            best_score = int(score)
            best_body_count = int(body_count)

    tier = CLUSTER_NONE
    if best_score >= 9:
        tier = CLUSTER_MAJOR
    elif best_score >= 7:
        tier = CLUSTER_STRONG
    elif best_score >= 5:
        tier = CLUSTER_MINOR

    return ChartCluster(
        sign_index=best_sign_index,
        score=int(best_score),
        body_count=int(best_body_count),
        tier=str(tier),
    )


def build_big3_chart(
    *,
    sim_id: int,
    created_at_sim_day: int,
    created_age: str,
    sun_sign_index: int,
    moon_sign_index: int,
    rising_sign_index: int,
    rng_seed: Optional[int] = None,
    lock_chart: bool = True,
    chart_version: int = 1,
    metadata: Optional[Mapping[str, object]] = None,
    include_outer_planets: Optional[bool] = None,
) -> ChartRecord:
    sun_sign_index = normalize_sign_index(sun_sign_index)
    moon_sign_index = normalize_sign_index(moon_sign_index)
    rising_sign_index = normalize_sign_index(rising_sign_index)
    rng = random.Random(rng_seed)

    house_sign_by_index = build_house_sign_map_for_rising(rising_sign_index)
    house_by_body = {
        "Sun": int(house_for_sign(house_sign_map=house_sign_by_index, sign_index=sun_sign_index)),
        "Moon": int(house_for_sign(house_sign_map=house_sign_by_index, sign_index=moon_sign_index)),
    }

    occupancy_by_house = {}  # type: Dict[int, int]
    for body_name in ("Sun", "Moon"):
        house_index = int(house_by_body[body_name])
        occupancy_by_house[house_index] = int(occupancy_by_house.get(house_index, 0)) + 1

    profile_roll = rng.random()
    if profile_roll < 0.72:
        profile = "spread"
    elif profile_roll < 0.95:
        profile = "mild_cluster"
    else:
        profile = "strong_cluster"

    occupied_houses = list(occupancy_by_house.keys())
    if occupied_houses:
        cluster_house = int(rng.choice(occupied_houses))
    else:
        cluster_house = int(rng.randrange(12))

    for body_name in _resolve_chart_body_names(include_outer_planets=include_outer_planets):
        if body_name in ("Sun", "Moon"):
            continue
        weighted_houses = []
        for house_index in range(12):
            occupancy = int(occupancy_by_house.get(house_index, 0))
            weight = 1.0

            if profile == "spread":
                if occupancy >= 2:
                    weight *= 0.1
                elif occupancy == 1:
                    weight *= 0.45
            elif profile == "mild_cluster":
                if house_index == cluster_house:
                    weight *= 1.4
                elif occupancy >= 2:
                    weight *= 0.2
                elif occupancy == 1:
                    weight *= 0.65
            else:
                if house_index == cluster_house:
                    weight *= 2.0
                elif occupancy >= 2:
                    weight *= 0.45
                elif occupancy == 1:
                    weight *= 0.85

            if body_name in ("Mercury", "Venus") and house_index == house_by_body["Sun"]:
                weight *= 1.2
            if body_name == "Mars" and house_index == house_by_body["Moon"]:
                weight *= 0.9

            weighted_houses.append((house_index, max(weight, 0.01)))

        total_weight = sum(weight for _, weight in weighted_houses)
        roll = rng.random() * total_weight
        selected_house_index = 0
        for house_index, weight in weighted_houses:
            roll -= weight
            if roll <= 0:
                selected_house_index = int(house_index)
                break

        house_by_body[body_name] = int(selected_house_index)
        occupancy_by_house[selected_house_index] = int(occupancy_by_house.get(selected_house_index, 0)) + 1

    classical_body_signs = {
        body_name: int(house_sign_by_index[int(house_index)]) % 12
        for body_name, house_index in house_by_body.items()
        if body_name in BODY_NAMES
        and house_index is not None and int(house_index) in house_sign_by_index
    }
    resolved_body_signs = {
        body_name: int(house_sign_by_index[int(house_index)]) % 12
        for body_name, house_index in house_by_body.items()
        if house_index is not None and int(house_index) in house_sign_by_index
    }
    resolved_metadata = dict(metadata or {})
    resolved_metadata.setdefault("body_sign_index_by_name", dict(resolved_body_signs))
    resolved_metadata.setdefault(
        "body_sign_name_by_name",
        {
            body_name: SIGNS[int(sign_index) % len(SIGNS)]
            for body_name, sign_index in resolved_body_signs.items()
        },
    )
    if callable(build_chart_composition_from_sign_indexes):
        chart_composition = build_chart_composition_from_sign_indexes(classical_body_signs)
        resolved_metadata.setdefault("chart_composition", chart_composition)
        # Deprecated compatibility shims for older Sun-only element/mode readers.
        if callable(get_legacy_single_element):
            resolved_metadata.setdefault(
                "legacy_primary_element",
                get_legacy_single_element(chart_composition),
            )
        if callable(get_legacy_single_mode):
            resolved_metadata.setdefault(
                "legacy_primary_mode",
                get_legacy_single_mode(chart_composition),
            )

    source_by_field = {
        "sun_sign_index": FIELD_SOURCE_PLAYER,
        "moon_sign_index": FIELD_SOURCE_PLAYER,
        "rising_sign_index": FIELD_SOURCE_PLAYER,
        "house_sign_by_index": FIELD_SOURCE_DERIVED,
        "house_by_body.Sun": FIELD_SOURCE_DERIVED,
        "house_by_body.Moon": FIELD_SOURCE_DERIVED,
        "house_by_body.Mercury": FIELD_SOURCE_RANDOMIZED,
        "house_by_body.Venus": FIELD_SOURCE_RANDOMIZED,
        "house_by_body.Mars": FIELD_SOURCE_RANDOMIZED,
        "house_by_body.Jupiter": FIELD_SOURCE_RANDOMIZED,
        "house_by_body.Saturn": FIELD_SOURCE_RANDOMIZED,
        "chart_ruler_body": FIELD_SOURCE_DERIVED,
    }
    for body_name in OPTIONAL_OUTER_BODY_NAMES:
        if body_name in house_by_body:
            source_by_field["house_by_body.{0}".format(body_name)] = FIELD_SOURCE_RANDOMIZED
    cluster = compute_cluster_signature(
        house_sign_by_index=house_sign_by_index,
        house_by_body=house_by_body,
    )
    return ChartRecord(
        sim_id=int(sim_id),
        chart_version=int(chart_version),
        mode_origin=MODE_BIG3,
        created_at_sim_day=int(created_at_sim_day),
        created_age=str(created_age or ""),
        locked=bool(lock_chart),
        sun_sign_index=int(sun_sign_index),
        moon_sign_index=int(moon_sign_index),
        rising_sign_index=int(rising_sign_index),
        house_sign_by_index=dict(house_sign_by_index),
        house_by_body=dict(house_by_body),
        chart_ruler_body=chart_ruler_body_for_rising(rising_sign_index),
        source_by_field=source_by_field,
        cluster=cluster,
        metadata=resolved_metadata,
    )


def chart_record_to_payload(record: ChartRecord) -> Dict[str, object]:
    return dict(asdict(record))


def chart_record_from_payload(payload: Mapping[str, object]) -> ChartRecord:
    cluster_payload = payload.get("cluster")
    if not isinstance(cluster_payload, Mapping):
        cluster_payload = {}
    cluster = ChartCluster(
        sign_index=(
            int(cluster_payload["sign_index"])
            if cluster_payload.get("sign_index") is not None
            else None
        ),
        score=int(cluster_payload.get("score", 0)),
        body_count=int(cluster_payload.get("body_count", 0)),
        tier=str(cluster_payload.get("tier", CLUSTER_NONE)),
    )
    return ChartRecord(
        sim_id=int(payload.get("sim_id", 0)),
        chart_version=int(payload.get("chart_version", 1)),
        mode_origin=str(payload.get("mode_origin", "")),
        created_at_sim_day=int(payload.get("created_at_sim_day", 0)),
        created_age=str(payload.get("created_age", "")),
        locked=bool(payload.get("locked", False)),
        sun_sign_index=int(payload.get("sun_sign_index", 0)),
        moon_sign_index=int(payload.get("moon_sign_index", 0)),
        rising_sign_index=int(payload.get("rising_sign_index", 0)),
        house_sign_by_index={
            int(key): int(value)
            for key, value in dict(payload.get("house_sign_by_index") or {}).items()
        },
        house_by_body={
            str(key): int(value)
            for key, value in dict(payload.get("house_by_body") or {}).items()
        },
        chart_ruler_body=str(payload.get("chart_ruler_body", "")),
        source_by_field={
            str(key): str(value)
            for key, value in dict(payload.get("source_by_field") or {}).items()
        },
        cluster=cluster,
        metadata=dict(payload.get("metadata") or {}),
    )
