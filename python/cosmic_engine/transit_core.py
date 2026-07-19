"""Transit math core for Cosmic Engine.

Pure logic only: no Sims 4 APIs in this module.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import random
import re
from typing import Dict, Iterable, List, Mapping, Optional, Tuple


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
SIGN_TO_INDEX_LOWER: Dict[str, int] = {name.lower(): i for i, name in enumerate(SIGNS)}
HOUSE_TO_INDEX: Dict[str, int] = {name: i for i, name in enumerate(HOUSES)}

# 4 seasons * (Early/Mid/Late)
SEASON_SEGMENTS_PER_YEAR = 12


class TimeUnit:
    DAY = "day"
    SEGMENT = "segment"


@dataclass(frozen=True)
class BodyRule:
    body: str
    unit: str
    interval: int


# Sun, Mercury, and Venus keep their existing runtime policy in transit_service.
# Mars is the first semi-independent sign cycle, and everything beyond Mars
# should feel progressively slower and more persistent.
BODY_RULES: Tuple[BodyRule, ...] = (
    BodyRule("Moon", TimeUnit.DAY, 1),
    BodyRule("Mercury", TimeUnit.DAY, 2),
    BodyRule("Sun", TimeUnit.SEGMENT, 1),
    BodyRule("Venus", TimeUnit.SEGMENT, 1),
    BodyRule("Mars", TimeUnit.SEGMENT, 3),
    BodyRule("Jupiter", TimeUnit.SEGMENT, 18),
    BodyRule("Saturn", TimeUnit.SEGMENT, 36),
)

OPTIONAL_OUTER_BODY_RULES: Tuple[BodyRule, ...] = (
    BodyRule("Chiron", TimeUnit.SEGMENT, 48),
    BodyRule("Uranus", TimeUnit.SEGMENT, 84),
    BodyRule("Neptune", TimeUnit.SEGMENT, 108),
    BodyRule("Pluto", TimeUnit.SEGMENT, 144),
)

BODY_NAMES: Tuple[str, ...] = tuple(rule.body for rule in BODY_RULES)
OPTIONAL_OUTER_BODY_NAMES: Tuple[str, ...] = tuple(
    rule.body for rule in OPTIONAL_OUTER_BODY_RULES
)
ALL_BODY_RULES: Tuple[BodyRule, ...] = BODY_RULES + OPTIONAL_OUTER_BODY_RULES
ALL_BODY_NAMES: Tuple[str, ...] = BODY_NAMES + OPTIONAL_OUTER_BODY_NAMES
RULE_BY_BODY: Dict[str, BodyRule] = {rule.body: rule for rule in ALL_BODY_RULES}
TETHERED_INITIAL_BODIES: Tuple[str, ...] = ("Sun", "Moon", "Mercury", "Venus")
FREE_INITIAL_MARS_PLUS_BODIES: Tuple[str, ...] = (
    "Mars",
    "Jupiter",
    "Saturn",
    "Chiron",
    "Uranus",
    "Neptune",
    "Pluto",
)

MARKER_NAME_RE = re.compile(
    r"^PlumAntics_CosmicEngineHouses_"
    r"(First|Second|Third|Fourth|Fifth|Sixth|Seventh|Eighth|Ninth|Tenth|Eleventh|Twelfth)"
    r"House_"
    r"(Aries|Taurus|Gemini|Cancer|Leo|Virgo|Libra|Scorpio|Sagittarius|Capricorn|Aquarius|Pisces)"
    r"Hidden$"
)


def resolve_active_body_names(*, include_outer: bool = False) -> Tuple[str, ...]:
    return ALL_BODY_NAMES if include_outer else BODY_NAMES


def normalize_sign_name(sign_name: str) -> str:
    lowered = sign_name.strip().lower()
    if lowered not in SIGN_TO_INDEX_LOWER:
        raise ValueError(f"Unknown sign name: {sign_name!r}")
    return SIGNS[SIGN_TO_INDEX_LOWER[lowered]]


def fnv1_32(text: str) -> int:
    h = 0x811C9DC5
    for b in text.encode("utf-8"):
        h = (h * 0x01000193) & 0xFFFFFFFF
        h ^= b
    return h


def marker_trait_name(house_index: int, sign_index: int) -> str:
    return (
        f"PlumAntics_CosmicEngineHouses_{HOUSES[house_index]}House_{SIGNS[sign_index]}Hidden"
    )


def marker_trait_id(house_index: int, sign_index: int) -> int:
    return fnv1_32(marker_trait_name(house_index, sign_index).lower())


def marker_traits_for_rising(rising_sign_index: int) -> List[int]:
    ids: List[int] = []
    for house_index in range(12):
        sign_index = (rising_sign_index + house_index) % 12
        ids.append(marker_trait_id(house_index, sign_index))
    return ids


def build_marker_lookup() -> Dict[int, Tuple[int, int]]:
    lookup: Dict[int, Tuple[int, int]] = {}
    for house_index in range(12):
        for sign_index in range(12):
            lookup[marker_trait_id(house_index, sign_index)] = (house_index, sign_index)
    return lookup


def build_house_sign_map_for_rising(rising_sign_index: int) -> Dict[int, int]:
    return {
        house_index: (rising_sign_index + house_index) % 12
        for house_index in range(12)
    }


def house_index_for_sign_and_rising(sign_index: int, rising_sign_index: int) -> int:
    return (sign_index - rising_sign_index) % 12


@dataclass
class TransitState:
    sign_index_by_body: Dict[str, int] = field(default_factory=dict)
    day_progress_by_body: Dict[str, int] = field(default_factory=dict)
    segment_progress_by_body: Dict[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for body in ALL_BODY_NAMES:
            self.sign_index_by_body.setdefault(body, 0)
            self.day_progress_by_body.setdefault(body, 0)
            self.segment_progress_by_body.setdefault(body, 0)

    def sign_name(self, body: str) -> str:
        return SIGNS[self.sign_index_by_body[body] % 12]


def state_to_payload(state: TransitState) -> Dict[str, Dict[str, int]]:
    return {
        "sign_index_by_body": dict(state.sign_index_by_body),
        "day_progress_by_body": dict(state.day_progress_by_body),
        "segment_progress_by_body": dict(state.segment_progress_by_body),
    }


def state_from_payload(payload: Mapping[str, Mapping[str, int]]) -> TransitState:
    return TransitState(
        sign_index_by_body=dict(payload.get("sign_index_by_body", {})),
        day_progress_by_body=dict(payload.get("day_progress_by_body", {})),
        segment_progress_by_body=dict(payload.get("segment_progress_by_body", {})),
    )


def reseed_mars_plus_state(state: TransitState, seed: Optional[int] = None) -> TransitState:
    rng = random.Random(seed)
    next_state = TransitState(
        sign_index_by_body=dict(state.sign_index_by_body),
        day_progress_by_body=dict(state.day_progress_by_body),
        segment_progress_by_body=dict(state.segment_progress_by_body),
    )
    for body in FREE_INITIAL_MARS_PLUS_BODIES:
        next_state.sign_index_by_body[body] = rng.randrange(12)
    return next_state


def random_initial_state(
    seed: Optional[int] = None,
    *,
    body_names: Optional[Iterable[str]] = None,
    tethered_sign_index_by_body: Optional[Mapping[str, int]] = None,
) -> TransitState:
    rng = random.Random(seed)
    names = tuple(body_names or ALL_BODY_NAMES)
    sign_index_by_body = {}
    tethered = dict(tethered_sign_index_by_body or {})
    for body in names:
        if body in TETHERED_INITIAL_BODIES and body in tethered:
            sign_index_by_body[body] = int(tethered[body]) % 12
        else:
            sign_index_by_body[body] = rng.randrange(12)
    return TransitState(sign_index_by_body=sign_index_by_body)


def _advance_body_by_unit(state: TransitState, body: str, unit_delta: int) -> int:
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
    skip_bodies: Optional[Iterable[str]] = None,
    body_names: Optional[Iterable[str]] = None,
) -> Dict[str, int]:
    moved: Dict[str, int] = {}
    skipped = {str(body) for body in (skip_bodies or ())}
    names = tuple(body_names or BODY_NAMES)
    for body in names:
        if body in skipped:
            moved[body] = 0
            continue
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
    lookup = dict(marker_lookup or build_marker_lookup())
    mapping: Dict[int, int] = {}
    for trait_id in marker_trait_ids:
        if trait_id not in lookup:
            continue
        house_index, sign_index = lookup[trait_id]
        mapping[house_index] = sign_index
    return mapping


def resolve_house_sign_map_from_marker_names(
    marker_trait_names: Iterable[str],
) -> Dict[int, int]:
    mapping: Dict[int, int] = {}
    for marker_name in marker_trait_names:
        match = MARKER_NAME_RE.match(marker_name)
        if not match:
            continue
        house_name = match.group(1)
        sign_name = match.group(2)
        mapping[HOUSE_TO_INDEX[house_name]] = SIGN_TO_INDEX[sign_name]
    return mapping


def house_for_sign(house_sign_map: Mapping[int, int], sign_index: int) -> Optional[int]:
    for house_index, mapped_sign in house_sign_map.items():
        if mapped_sign == sign_index:
            return house_index
    return None


def body_chart_for_sim(
    state: TransitState,
    house_sign_map: Mapping[int, int],
    *,
    body_names: Optional[Iterable[str]] = None,
) -> Dict[str, Dict[str, Optional[int]]]:
    out: Dict[str, Dict[str, Optional[int]]] = {}
    for body in tuple(body_names or BODY_NAMES):
        sign_index = state.sign_index_by_body[body] % 12
        house_index = house_for_sign(house_sign_map, sign_index)
        out[body] = {
            "sign_index": sign_index,
            "sign_name": SIGNS[sign_index],
            "house_index": house_index,
            "house_number": (house_index + 1) if house_index is not None else None,
            "house_name": HOUSES[house_index] if house_index is not None else None,
        }
    return out
