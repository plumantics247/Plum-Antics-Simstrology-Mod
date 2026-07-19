#!/usr/bin/env python3
"""Cosmic Engine transit math prototype.

Runtime-agnostic helpers for:
- global transit progression math (Moon/Mercury/Sun/Venus/Mars/Jupiter/Saturn)
- house/sign resolution from either rising-sign math or marker traits
- simple CLI simulation for fast design iteration
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
import random
import re
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


SIGNS: Tuple[str, ...] = (
    "Aries",
    "Taurus",
    "Gemini",
    "Cancer",
    "Leo",
    "Virgo",
    "Libra",
    "Scorpio",
    "Sagittarius",
    "Capricorn",
    "Aquarius",
    "Pisces",
)

HOUSES: Tuple[str, ...] = (
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

SIGN_TO_INDEX: Dict[str, int] = {name: i for i, name in enumerate(SIGNS)}
SIGN_TO_INDEX_BY_LOWER: Dict[str, int] = {name.lower(): i for i, name in enumerate(SIGNS)}
HOUSE_TO_INDEX: Dict[str, int] = {name: i for i, name in enumerate(HOUSES)}

# Your model currently assumes 12 season-segments in a full sim year:
# Early/Mid/Late for each of 4 seasons.
SEASON_SEGMENTS_PER_YEAR = 12


class TimeUnit:
    DAY = "day"
    SEGMENT = "segment"


@dataclass(frozen=True)
class BodyRule:
    body: str
    unit: str
    interval: int


BODY_RULES: Tuple[BodyRule, ...] = (
    BodyRule("Moon", TimeUnit.DAY, 2),
    BodyRule("Mercury", TimeUnit.DAY, 2),
    BodyRule("Sun", TimeUnit.SEGMENT, 1),
    BodyRule("Venus", TimeUnit.SEGMENT, 1),
    BodyRule("Mars", TimeUnit.SEGMENT, 2),
    BodyRule("Jupiter", TimeUnit.SEGMENT, 12),  # one full year per house
    BodyRule("Saturn", TimeUnit.SEGMENT, 24),   # two full years per house
)

BODY_NAMES: Tuple[str, ...] = tuple(rule.body for rule in BODY_RULES)
RULE_BY_BODY: Dict[str, BodyRule] = {rule.body: rule for rule in BODY_RULES}

MARKER_NAME_RE = re.compile(
    r"^PlumAntics_SimstrologyHouses_"
    r"(First|Second|Third|Fourth|Fifth|Sixth|Seventh|Eighth|Ninth|Tenth|Eleventh|Twelfth)"
    r"House_"
    r"(Aries|Taurus|Gemini|Cancer|Leo|Virgo|Libra|Scorpio|Sagittarius|Capricorn|Aquarius|Pisces)"
    r"Hidden$"
)


def normalize_sign_name(sign_name: str) -> str:
    key = sign_name.strip().lower()
    if key not in SIGN_TO_INDEX_BY_LOWER:
        raise ValueError(f"Unknown sign '{sign_name}'.")
    return SIGNS[SIGN_TO_INDEX_BY_LOWER[key]]


def fnv1_32(text: str) -> int:
    """FNV-1 32-bit (matches your existing XML 32-bit style)."""
    h = 0x811C9DC5
    for b in text.encode("utf-8"):
        h = (h * 0x01000193) & 0xFFFFFFFF
        h ^= b
    return h


def marker_trait_name(house_index: int, sign_index: int) -> str:
    return (
        f"PlumAntics_SimstrologyHouses_{HOUSES[house_index]}House_{SIGNS[sign_index]}Hidden"
    )


def marker_trait_id(house_index: int, sign_index: int) -> int:
    return fnv1_32(marker_trait_name(house_index, sign_index).lower())


def build_marker_lookup() -> Dict[int, Tuple[int, int]]:
    """Return marker trait-id -> (house_index, sign_index)."""
    lookup: Dict[int, Tuple[int, int]] = {}
    for h in range(12):
        for s in range(12):
            lookup[marker_trait_id(h, s)] = (h, s)
    return lookup


def marker_traits_for_rising(rising_sign_index: int) -> List[int]:
    """Return the 12 marker trait IDs assigned for a rising sign.

    House 1 takes the rising sign itself, then rotates forward zodiacally.
    """
    ids: List[int] = []
    for house_index in range(12):
        sign_index = (rising_sign_index + house_index) % 12
        ids.append(marker_trait_id(house_index, sign_index))
    return ids


def build_house_sign_map_for_rising(rising_sign_index: int) -> Dict[int, int]:
    """Return house_index -> sign_index for a rising sign."""
    return {
        house_index: (rising_sign_index + house_index) % 12
        for house_index in range(12)
    }


def house_index_for_sign_and_rising(sign_index: int, rising_sign_index: int) -> int:
    """Resolve which house a sign lands in for a given rising sign."""
    return (sign_index - rising_sign_index) % 12


@dataclass
class TransitState:
    """Mutable transit state for all bodies."""

    sign_index_by_body: Dict[str, int] = field(default_factory=dict)
    day_progress_by_body: Dict[str, int] = field(default_factory=dict)
    segment_progress_by_body: Dict[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for body in BODY_NAMES:
            self.sign_index_by_body.setdefault(body, 0)
            self.day_progress_by_body.setdefault(body, 0)
            self.segment_progress_by_body.setdefault(body, 0)

    def sign_name(self, body: str) -> str:
        return SIGNS[self.sign_index_by_body[body] % 12]


def state_to_payload(state: TransitState) -> Dict[str, Dict[str, int]]:
    """Serialize state for persistence in a custom save payload."""
    return {
        "sign_index_by_body": dict(state.sign_index_by_body),
        "day_progress_by_body": dict(state.day_progress_by_body),
        "segment_progress_by_body": dict(state.segment_progress_by_body),
    }


def state_from_payload(payload: Mapping[str, Mapping[str, int]]) -> TransitState:
    """Deserialize state from persisted payload data."""
    return TransitState(
        sign_index_by_body=dict(payload.get("sign_index_by_body", {})),
        day_progress_by_body=dict(payload.get("day_progress_by_body", {})),
        segment_progress_by_body=dict(payload.get("segment_progress_by_body", {})),
    )


def random_initial_state(seed: Optional[int] = None) -> TransitState:
    """Create a state where each body starts in a random sign (0..11)."""
    rng = random.Random(seed)
    sign_index_by_body = {body: rng.randrange(12) for body in BODY_NAMES}
    return TransitState(sign_index_by_body=sign_index_by_body)


def _advance_body_by_unit(state: TransitState, body: str, unit_delta: int) -> int:
    """Advance a single body by elapsed units; return number of sign steps taken."""
    if unit_delta <= 0:
        return 0

    rule = RULE_BY_BODY[body]
    if rule.unit == TimeUnit.DAY:
        accum = state.day_progress_by_body[body] + unit_delta
        steps, rem = divmod(accum, rule.interval)
        state.day_progress_by_body[body] = rem
    else:
        accum = state.segment_progress_by_body[body] + unit_delta
        steps, rem = divmod(accum, rule.interval)
        state.segment_progress_by_body[body] = rem

    if steps:
        state.sign_index_by_body[body] = (state.sign_index_by_body[body] + steps) % 12
    return steps


def advance_transits(
    state: TransitState,
    *,
    elapsed_days: int = 0,
    elapsed_segments: int = 0,
) -> Dict[str, int]:
    """Advance all bodies and return per-body sign-step counts."""
    moved: Dict[str, int] = {}
    for body in BODY_NAMES:
        rule = RULE_BY_BODY[body]
        if rule.unit == TimeUnit.DAY:
            moved[body] = _advance_body_by_unit(state, body, elapsed_days)
        else:
            moved[body] = _advance_body_by_unit(state, body, elapsed_segments)
    return moved


def resolve_house_sign_map_from_marker_ids(
    marker_trait_ids: Iterable[int],
    marker_lookup: Optional[Mapping[int, Tuple[int, int]]] = None,
) -> Dict[int, int]:
    """Resolve house->sign using a sim's marker trait IDs."""
    lookup = dict(marker_lookup or build_marker_lookup())
    mapping: Dict[int, int] = {}
    for tid in marker_trait_ids:
        if tid not in lookup:
            continue
        house_index, sign_index = lookup[tid]
        mapping[house_index] = sign_index
    return mapping


def resolve_house_sign_map_from_marker_names(
    marker_trait_names: Iterable[str],
) -> Dict[int, int]:
    """Resolve house->sign from marker trait names."""
    mapping: Dict[int, int] = {}
    for name in marker_trait_names:
        m = MARKER_NAME_RE.match(name)
        if not m:
            continue
        house_name = m.group(1)
        sign_name = m.group(2)
        mapping[HOUSE_TO_INDEX[house_name]] = SIGN_TO_INDEX[sign_name]
    return mapping


def house_for_sign(
    house_sign_map: Mapping[int, int],
    sign_index: int,
) -> Optional[int]:
    """Return house_index where sign_index is currently placed, or None."""
    for house_index, mapped_sign in house_sign_map.items():
        if mapped_sign == sign_index:
            return house_index
    return None


def body_chart_for_sim(
    state: TransitState,
    house_sign_map: Mapping[int, int],
) -> Dict[str, Dict[str, Optional[int]]]:
    """Resolve per-body sign + house for a sim."""
    out: Dict[str, Dict[str, Optional[int]]] = {}
    for body in BODY_NAMES:
        s_idx = state.sign_index_by_body[body] % 12
        h_idx = house_for_sign(house_sign_map, s_idx)
        out[body] = {
            "sign_index": s_idx,
            "sign_name": SIGNS[s_idx],
            "house_index": h_idx,
            "house_number": (h_idx + 1) if h_idx is not None else None,
            "house_name": HOUSES[h_idx] if h_idx is not None else None,
        }
    return out


def body_chart_for_rising(
    state: TransitState,
    rising_sign_index: int,
) -> Dict[str, Dict[str, int]]:
    """Resolve per-body sign + house using direct rising math.

    This is equivalent to the marker-trait mapping when marker traits are assigned correctly.
    """
    out: Dict[str, Dict[str, int]] = {}
    for body in BODY_NAMES:
        sign_index = state.sign_index_by_body[body] % 12
        house_index = house_index_for_sign_and_rising(sign_index, rising_sign_index)
        out[body] = {
            "sign_index": sign_index,
            "house_index": house_index,
        }
    return out


def _format_body_chart_table(chart: Mapping[str, Mapping[str, Optional[int]]]) -> str:
    lines = ["Body | Sign | House", "---- | ---- | -----"]
    for body in BODY_NAMES:
        row = chart.get(body, {})
        sign_name = str(row.get("sign_name", "?"))
        house_number = row.get("house_number")
        house_display = f"{house_number}" if house_number is not None else "?"
        lines.append(f"{body} | {sign_name} | {house_display}")
    return "\n".join(lines)


def _build_cli() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Cosmic Engine transit math helper")
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Seed for deterministic random initial body signs.",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=0,
        help="Elapsed sim days to advance.",
    )
    parser.add_argument(
        "--segments",
        type=int,
        default=0,
        help="Elapsed season segments to advance.",
    )
    parser.add_argument(
        "--rising",
        type=str,
        default="Aries",
        help="Rising sign used for house mapping in output chart.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON output.",
    )
    return parser


def _run_cli(seed: int, days: int, segments: int, rising: str, as_json: bool) -> int:
    rising_name = normalize_sign_name(rising)
    rising_sign_index = SIGN_TO_INDEX[rising_name]

    state = random_initial_state(seed=seed)
    moved = advance_transits(state, elapsed_days=days, elapsed_segments=segments)
    house_map = build_house_sign_map_for_rising(rising_sign_index)
    chart = body_chart_for_sim(state, house_map)

    # Sanity check: marker-driven map should match direct rising map.
    marker_map = resolve_house_sign_map_from_marker_ids(
        marker_traits_for_rising(rising_sign_index)
    )
    marker_matches = marker_map == house_map

    payload = {
        "config": {
            "seed": seed,
            "elapsed_days": days,
            "elapsed_segments": segments,
            "rising": rising_name,
            "segments_per_year": SEASON_SEGMENTS_PER_YEAR,
        },
        "moved_steps": moved,
        "current_sign_by_body": {b: state.sign_name(b) for b in BODY_NAMES},
        "chart": chart,
        "marker_map_matches_rising_math": marker_matches,
        "state_payload": state_to_payload(state),
    }

    if as_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    print("Transit config:", payload["config"])
    print("Steps moved:", moved)
    print("Current signs:", payload["current_sign_by_body"])
    print("Marker map matches rising math:", marker_matches)
    print()
    print(_format_body_chart_table(chart))
    return 0


if __name__ == "__main__":
    args = _build_cli().parse_args()
    raise SystemExit(
        _run_cli(
            seed=args.seed,
            days=args.days,
            segments=args.segments,
            rising=args.rising,
            as_json=args.json,
        )
    )
