"""One-time natal snapshot capture for teen+ sims.

Current scope:
- captures permanent natal planet-in-house markers (7 bodies x 12 possible defs)
- captures permanent natal Sun + Moon sign markers
- adds a one-time hidden capture flag so the snapshot is not overwritten
- uses the sim's existing rising/house blueprint to derive house placement
"""

from __future__ import annotations

import random
import re
import time
import zlib
from typing import Dict, Iterable, List, Mapping, Optional, Tuple

from .chart_records import (
    FIELD_SOURCE_DERIVED,
    FIELD_SOURCE_PLAYER,
    FIELD_SOURCE_RANDOMIZED,
    FIELD_SOURCE_UNIVERSE,
    build_cosmic_chart,
    chart_record_to_payload,
)
from .loot_actions import _collect_trait_ids_and_markers, _iter_traits_for_sim_info, _trait_guid64, _trait_name
from .planet_house_markers import (
    _build_house_sign_map_for_sim,
    _equipped_traits_with_ids,
    _get_trait_instance_manager,
    _iter_instanced_sim_infos,
    _iter_manager_trait_tunings,
    _trait_tracker_add_trait,
    _trait_tracker_remove_trait,
)
from .sim_eligibility import sim_age_lane, sim_info_is_teen_plus
from .transit_core import BODY_NAMES, HOUSES, SIGNS, build_house_sign_map_for_rising
from .transit_service import CosmicTransitService, get_global_transit_service


_NATAL_PLANET_HOUSE_PREFIX = "PlumAntics_CosmicEngineNatal_"
_NATAL_CAPTURE_FLAG_NAME = "PlumAntics_CosmicEngineNatal_ChartCapturedHidden"
_NATAL_LEGACY_FLAG_NAME = "PlumAntics_CosmicEngineNatal_ChartLegacyGeneratedHidden"
_BODY_TO_INDEX = {body: idx for idx, body in enumerate(BODY_NAMES)}
_HOUSE_TO_INDEX = {house: idx for idx, house in enumerate(HOUSES)}
_SIGN_TO_INDEX = {sign: idx for idx, sign in enumerate(SIGNS)}
_HEX_ID_RE = re.compile(r"0x([0-9A-Fa-f]{6,16})")
_VISIBLE_SIGN_REWARD_PREFIXES = (
    "PlumAntics_Big3Mod_",
    "PlumAntics_CosmicEngineCore_",
)
_VISIBLE_SIGN_TIMED_BUFF_PREFIX = "PlumAntics_CosmicEngineCore_"
_RETURN_MARKER_PREFIX = "PlumAntics_CosmicEngineReturns_"
_CHART_RULER_TRAIT_PREFIX = "PlumAntics_CosmicEngineCore_"
_RISING_TRAIT_PREFIXES = (
    "PlumAntics_Big3Mod_",
    "PlumAntics_CosmicEngineCore_",
)
_RISING_TIMED_BUFF_APPLY_DEBOUNCE_SECONDS = 0.75
_RISING_TIMED_BUFF_LAST_APPLY_BY_SIM_SIGN = {}  # type: Dict[Tuple[int, int], float]
_VISIBLE_SIGN_PY_MANAGED_BUFF_DURATION_MINUTES = 240
_VISIBLE_SIGN_MANAGED_BUFF_EXPIRY_BY_SIM_BODY = {}  # type: Dict[Tuple[int, str], Dict[str, int]]
_RISING_PY_MANAGED_BUFF_DURATION_MINUTES = 120
_RISING_MANAGED_BUFF_EXPIRY_BY_SIM_ID = {}  # type: Dict[int, Dict[str, int]]


_MARKER_CACHE = {
    "initialized": False,
    "available_by_body_house": {},  # type: Dict[Tuple[str, int], object]
    "candidate_ids_by_body": {},  # type: Dict[str, set]
    "planet_house_candidate_ids": set(),  # type: set
    "sun_sign_trait_by_index": {},  # type: Dict[int, object]
    "moon_sign_trait_by_index": {},  # type: Dict[int, object]
    "sign_candidate_ids_by_body": {},  # type: Dict[str, set]
    "visible_sun_reward_trait_by_index": {},  # type: Dict[int, object]
    "visible_moon_reward_trait_by_index": {},  # type: Dict[int, object]
    "visible_sign_reward_candidate_ids_by_body": {},  # type: Dict[str, set]
    "visible_sun_timed_buff_by_index": {},  # type: Dict[int, object]
    "visible_moon_timed_buff_by_index": {},  # type: Dict[int, object]
    "return_marker_candidate_ids_by_body": {},  # type: Dict[str, set]
    "hidden_chart_ruler_body_by_trait_id": {},  # type: Dict[int, str]
    "visible_chart_ruler_reward_trait_by_body": {},  # type: Dict[str, object]
    "visible_chart_ruler_reward_candidate_ids": set(),  # type: set
    "visible_chart_ruler_reward_body_by_trait_id": {},  # type: Dict[int, str]
    "visible_rising_timed_buff_by_index": {},  # type: Dict[int, object]
    "personality_rising_trait_by_index": {},  # type: Dict[int, object]
    "rising_marker_trait_by_index": {},  # type: Dict[int, object]
    "rising_personality_candidate_ids": set(),  # type: set
    "rising_marker_candidate_ids": set(),  # type: set
    "rising_personality_sign_index_by_trait_id": {},  # type: Dict[int, int]
    "rising_marker_sign_index_by_trait_id": {},  # type: Dict[int, int]
    "capture_flag_trait": None,  # type: Optional[object]
    "capture_flag_trait_id": None,  # type: Optional[int]
    "legacy_flag_trait": None,  # type: Optional[object]
    "legacy_flag_trait_id": None,  # type: Optional[int]
}


def _parse_natal_planet_house_marker_name(trait_name: str) -> Optional[Tuple[str, int]]:
    if not trait_name:
        return None
    text = str(trait_name)
    if not text.startswith(_NATAL_PLANET_HOUSE_PREFIX):
        return None
    if text in (_NATAL_CAPTURE_FLAG_NAME, _NATAL_LEGACY_FLAG_NAME):
        return None
    if "House" not in text or "Hidden" not in text:
        return None

    body = None
    for candidate in BODY_NAMES:
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


def _parse_natal_sign_marker_name(trait_name: str) -> Optional[Tuple[str, int]]:
    if not trait_name:
        return None
    text = str(trait_name)
    if not text.startswith(_NATAL_PLANET_HOUSE_PREFIX):
        return None
    if text in (_NATAL_CAPTURE_FLAG_NAME, _NATAL_LEGACY_FLAG_NAME):
        return None
    if "House" in text or "Hidden" not in text:
        return None

    for body in ("Sun", "Moon"):
        suffix = "{0}Hidden".format(body)
        if not text.endswith(suffix):
            continue
        core = text[len(_NATAL_PLANET_HOUSE_PREFIX) : -len(suffix)]
        if not core:
            return None
        sign_index = _SIGN_TO_INDEX.get(core)
        if sign_index is None:
            return None
        return (body, int(sign_index))
    return None


def _parse_visible_sign_reward_trait_name(trait_name: str) -> Optional[Tuple[str, int]]:
    if not trait_name:
        return None
    text = str(trait_name)
    if any(token in text for token in ("Buff", "Return", "Natal", "House")):
        return None

    prefix = None
    for candidate in _VISIBLE_SIGN_REWARD_PREFIXES:
        if text.startswith(candidate):
            prefix = candidate
            break
    if prefix is None:
        return None

    core = text[len(prefix) :]
    # Accept legacy `_Hidden` suffixes here so older Cosmic saves and any
    # still-unmigrated tuning names continue to parse cleanly.
    if core.endswith("_Hidden"):
        core = core[: -len("_Hidden")]

    for body in ("Sun", "Moon"):
        if not core.endswith(body):
            continue
        sign_core = core[: -len(body)]
        if not sign_core:
            return None
        sign_index = _SIGN_TO_INDEX.get(sign_core)
        if sign_index is None:
            return None
        return (body, int(sign_index))
    return None


def _parse_visible_sign_timed_buff_name(buff_name: str) -> Optional[Tuple[str, int]]:
    if not buff_name:
        return None
    text = str(buff_name)
    if not text.startswith(_VISIBLE_SIGN_TIMED_BUFF_PREFIX):
        return None
    if any(token in text for token in ("Hidden", "Return", "Natal", "House")):
        return None

    core = text[len(_VISIBLE_SIGN_TIMED_BUFF_PREFIX) :]
    for body in ("Sun", "Moon"):
        suffix = "{0}Buff".format(body)
        if not core.endswith(suffix):
            continue
        sign_core = core[: -len(suffix)]
        if not sign_core:
            return None
        sign_index = _SIGN_TO_INDEX.get(sign_core)
        if sign_index is None:
            return None
        return (body, int(sign_index))
    return None


def _parse_return_sign_marker_name(trait_name: str) -> Optional[Tuple[str, int]]:
    if not trait_name:
        return None
    text = str(trait_name)
    if not text.startswith(_RETURN_MARKER_PREFIX):
        return None
    if not text.endswith("ReturnHidden"):
        return None

    core = text[len(_RETURN_MARKER_PREFIX) :]
    for body in ("Sun", "Moon"):
        suffix = "{0}ReturnHidden".format(body)
        if not core.endswith(suffix):
            continue
        sign_core = core[: -len(suffix)]
        if not sign_core:
            return None
        sign_index = _SIGN_TO_INDEX.get(sign_core)
        if sign_index is None:
            return None
        return (body, int(sign_index))
    return None


def _parse_hidden_chart_ruler_marker_name(trait_name: str) -> Optional[str]:
    if not trait_name:
        return None
    text = str(trait_name)
    if not text.startswith(_CHART_RULER_TRAIT_PREFIX):
        return None
    if any(token in text for token in ("Buff", "Return", "Natal", "House", "Rising", "ChartRuler")):
        return None
    if not text.endswith("_Hidden"):
        return None
    core = text[len(_CHART_RULER_TRAIT_PREFIX) : -len("_Hidden")]
    return str(core) if core in BODY_NAMES else None


def _parse_visible_chart_ruler_reward_trait_name(trait_name: str) -> Optional[str]:
    if not trait_name:
        return None
    text = str(trait_name)
    if not text.startswith(_CHART_RULER_TRAIT_PREFIX):
        return None
    if any(token in text for token in ("Buff", "Return", "Natal", "House", "Rising")):
        return None
    if not text.endswith("ChartRuler"):
        return None
    core = text[len(_CHART_RULER_TRAIT_PREFIX) : -len("ChartRuler")]
    return str(core) if core in BODY_NAMES else None


def _parse_visible_rising_timed_buff_name(buff_name: str) -> Optional[int]:
    if not buff_name:
        return None
    text = str(buff_name)
    if not text.startswith(_VISIBLE_SIGN_TIMED_BUFF_PREFIX):
        return None
    if any(token in text for token in ("Hidden", "Return", "Natal", "House", "Controller")):
        return None

    core = text[len(_VISIBLE_SIGN_TIMED_BUFF_PREFIX) :]
    if not core.endswith("RisingBuff"):
        return None
    sign_core = core[: -len("RisingBuff")]
    if not sign_core:
        return None
    sign_index = _SIGN_TO_INDEX.get(sign_core)
    return int(sign_index) if sign_index is not None else None


def _parse_rising_sign_trait_name(trait_name: str) -> Optional[Tuple[int, bool]]:
    if not trait_name:
        return None
    text = str(trait_name)
    if any(token in text for token in ("Buff", "Return", "Natal", "House", "Controller")):
        return None

    prefix = None
    for candidate in _RISING_TRAIT_PREFIXES:
        if text.startswith(candidate):
            prefix = candidate
            break
    if prefix is None:
        return None

    core = text[len(prefix) :]
    marker_hint = False
    for suffix in ("_Hidden", "Hidden", "_Reward", "Reward", "_Marker", "Marker"):
        if core.endswith(suffix):
            core = core[: -len(suffix)]
            marker_hint = True
            break

    if not core.endswith("Rising"):
        return None
    sign_core = core[: -len("Rising")]
    if not sign_core:
        return None
    sign_index = _SIGN_TO_INDEX.get(sign_core)
    if sign_index is None:
        return None
    return (int(sign_index), bool(marker_hint))


def _trait_type_texts(trait) -> List[str]:
    out: List[str] = []
    for attr_name in ("trait_type", "_trait_type"):
        try:
            value = getattr(trait, attr_name, None)
        except Exception:
            value = None
        if value is None:
            continue
        for candidate in (getattr(value, "name", None), str(value), repr(value)):
            if not candidate:
                continue
            text = str(candidate)
            if text not in out:
                out.append(text)
        try:
            ivalue = int(value)
        except Exception:
            ivalue = None
        if ivalue is not None:
            text = str(int(ivalue))
            if text not in out:
                out.append(text)
    return out


def _classify_rising_trait_bucket(trait, *, marker_hint: bool) -> str:
    if marker_hint:
        return "marker"

    texts = [str(text).upper() for text in _trait_type_texts(trait)]
    for text in texts:
        if "PERSONALITY" in text:
            return "personality"
    for text in texts:
        if "GAMEPLAY" in text or "REWARD" in text:
            return "marker"

    # Existing CE rising traits are personality unless explicitly duplicated as markers.
    return "personality"


def _prefer_visible_gameplay_rising_marker(existing_trait, candidate_trait, *, candidate_marker_hint: bool) -> bool:
    """Prefer the gameplay-visible Rising trait over the legacy hidden marker def."""
    if existing_trait is None:
        return True
    if candidate_marker_hint:
        return False

    existing_name = _trait_name(existing_trait) or ""
    candidate_name = _trait_name(candidate_trait) or ""
    existing_marker_named = "_Marker" in str(existing_name)
    candidate_marker_named = "_Marker" in str(candidate_name)
    if existing_marker_named and not candidate_marker_named:
        return True
    return False


def _is_teen_or_older(sim_info) -> bool:
    return sim_info_is_teen_plus(sim_info)


def _rising_age_lane_for_sim_info(sim_info) -> str:
    return sim_age_lane(sim_info)


def _coerce_int(value) -> Optional[int]:
    try:
        return int(value)
    except Exception:
        return None


def _call_if_callable(value):
    if callable(value):
        try:
            return value()
        except Exception:
            return None
    return value


def _stable_text_fallback_seed(sim_info) -> int:
    parts: List[str] = []
    for attr_name in ("first_name", "last_name", "full_name"):
        try:
            value = getattr(sim_info, attr_name, None)
        except Exception:
            value = None
        if value:
            parts.append(str(value))

    household_id = _coerce_int(getattr(sim_info, "household_id", None))
    if household_id is None:
        household = getattr(sim_info, "household", None)
        household_id = _coerce_int(getattr(household, "id", None)) if household is not None else None
    if household_id is not None:
        parts.append(str(int(household_id)))

    try:
        repr_text = repr(sim_info)
    except Exception:
        repr_text = str(type(sim_info))
    if repr_text:
        parts.append(repr_text)

    text = "|".join(parts) if parts else str(type(sim_info))
    return int(zlib.crc32(text.encode("utf-8")) & 0xFFFFFFFF)


def _trait_text_candidates(trait) -> List[str]:
    out: List[str] = []
    for value in (
        _trait_name(trait),
        getattr(trait, "name", None),
        getattr(trait, "_name", None),
        getattr(type(trait), "__name__", None),
    ):
        if value:
            text = str(value)
            if text not in out:
                out.append(text)
    for fn in (str, repr):
        try:
            text = fn(trait)
        except Exception:
            continue
        if text and text not in out:
            out.append(text)
    return out


def _trait_contains_text(trait, needle: str) -> bool:
    if not needle:
        return False
    for text in _trait_text_candidates(trait):
        if needle in text:
            return True
    return False


def _sim_info_id(sim_info) -> int:
    # Try common TS4 identifiers first (attributes and zero-arg getters).
    # Intentionally do not fall back to household ids here: random seeding and
    # dirty-sync targeting must stay per-sim, not per-household.
    for attr_name in ("sim_id", "id", "sim_info_id", "guid64"):
        value = _call_if_callable(getattr(sim_info, attr_name, None))
        coerced = _coerce_int(value)
        if coerced is not None:
            return int(coerced)
    for method_name in ("get_sim_id", "get_id", "get_guid64"):
        value = _call_if_callable(getattr(sim_info, method_name, None))
        coerced = _coerce_int(value)
        if coerced is not None:
            return int(coerced)

    # Some builds expose the unique sim id only in repr strings.
    try:
        repr_text = repr(sim_info)
    except Exception:
        repr_text = ""
    match = _HEX_ID_RE.search(repr_text or "")
    if match:
        try:
            return int(match.group(1), 16)
        except Exception:
            pass

    # Final deterministic fallback so legacy seeding still diverges per sim.
    return _stable_text_fallback_seed(sim_info)


def _target_instanced_sim_infos(sim_infos: Optional[Iterable[object]] = None) -> Tuple[object, ...]:
    candidates = tuple(_iter_instanced_sim_infos()) if sim_infos is None else tuple(sim_infos)
    out = []
    seen = set()
    for sim_info in candidates:
        if sim_info is None:
            continue
        sim_id = _coerce_int(_sim_info_id(sim_info))
        key = int(sim_id) if sim_id is not None else id(sim_info)
        if key in seen:
            continue
        seen.add(key)
        out.append(sim_info)
    return tuple(out)


def _sim_info_household_id(sim_info) -> Optional[int]:
    household_id = _coerce_int(getattr(sim_info, "household_id", None))
    if household_id is None:
        household = getattr(sim_info, "household", None)
        household_id = _coerce_int(getattr(household, "id", None)) if household is not None else None
    return int(household_id) if household_id is not None else None


def _chart_created_age_for_sim_info(sim_info) -> str:
    age_value = getattr(sim_info, "age", None)
    if age_value is None:
        return "UNKNOWN"
    age_name = getattr(age_value, "name", None)
    if isinstance(age_name, str) and age_name:
        return str(age_name).upper()
    try:
        return str(age_value).upper()
    except Exception:
        return "UNKNOWN"


def _store_chart_record_for_sim(
    *,
    sim_info,
    transit_service: CosmicTransitService,
    house_sign_map: Mapping[int, int],
    body_sign_index_by_name: Mapping[str, int],
    provenance: str,
) -> Optional[Dict[str, object]]:
    if sim_info is None:
        return None
    sim_id = _sim_info_id(sim_info)
    if sim_id <= 0:
        return None

    rising_sign_index = house_sign_map.get(0)
    if not isinstance(rising_sign_index, int):
        return None

    source_by_field = {
        "rising_sign_index": FIELD_SOURCE_PLAYER,
    }
    if str(provenance) == "legacy_random":
        source_by_field.update(
            {
                "sun_sign_index": FIELD_SOURCE_RANDOMIZED,
                "moon_sign_index": FIELD_SOURCE_RANDOMIZED,
                "house_by_body": FIELD_SOURCE_RANDOMIZED,
            }
        )
    elif str(provenance) in ("existing_visible_signs", "existing_big3_traits"):
        source_by_field.update(
            {
                "sun_sign_index": FIELD_SOURCE_PLAYER,
                "moon_sign_index": FIELD_SOURCE_PLAYER,
                "house_by_body": FIELD_SOURCE_DERIVED,
            }
        )
    elif str(provenance) in ("stored_natal_markers",):
        source_by_field.update(
            {
                "sun_sign_index": FIELD_SOURCE_DERIVED,
                "moon_sign_index": FIELD_SOURCE_DERIVED,
                "house_by_body": FIELD_SOURCE_DERIVED,
            }
        )
    else:
        source_by_field.update(
            {
                "sun_sign_index": FIELD_SOURCE_UNIVERSE,
                "moon_sign_index": FIELD_SOURCE_UNIVERSE,
                "house_by_body": FIELD_SOURCE_UNIVERSE,
            }
        )

    record = build_cosmic_chart(
        sim_id=int(sim_id),
        created_at_sim_day=int(transit_service.current_sim_day()),
        created_age=_chart_created_age_for_sim_info(sim_info),
        rising_sign_index=int(rising_sign_index),
        body_sign_index_by_name=body_sign_index_by_name,
        source_by_field=source_by_field,
        metadata={
            "chart_source": str(provenance),
            "household_id": _sim_info_household_id(sim_info),
        },
    )
    payload = chart_record_to_payload(record)
    transit_service.set_chart_record_payload(int(sim_id), payload)
    return payload


def _get_active_household_id() -> Optional[int]:
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

    household_id = _coerce_int(getattr(client, "active_household_id", None))
    if household_id is not None:
        return int(household_id)
    active_sim_info = getattr(client, "active_sim_info", None)
    if active_sim_info is not None:
        return _sim_info_household_id(active_sim_info)
    active_sim = getattr(client, "active_sim", None)
    if active_sim is not None:
        return _sim_info_household_id(getattr(active_sim, "sim_info", None) or active_sim)
    return None


def _iter_household_sim_infos_by_id(household_id: Optional[int]) -> Iterable[object]:
    target_household_id = _coerce_int(household_id)
    if target_household_id is None:
        return tuple(_iter_instanced_sim_infos())

    services = _get_services_module()
    out: List[object] = []
    seen_sim_ids: set = set()

    def _append(candidate) -> None:
        sim_info = getattr(candidate, "sim_info", None) or candidate
        if sim_info is None:
            return
        sim_household_id = _sim_info_household_id(sim_info)
        if sim_household_id is None or int(sim_household_id) != int(target_household_id):
            return
        sim_id = _coerce_int(_sim_info_id(sim_info))
        marker = int(sim_id) if sim_id is not None else id(sim_info)
        if marker in seen_sim_ids:
            return
        seen_sim_ids.add(marker)
        out.append(sim_info)

    household_manager = None
    if services is not None:
        household_manager_fn = getattr(services, "household_manager", None)
        if callable(household_manager_fn):
            try:
                household_manager = household_manager_fn()
            except Exception:
                household_manager = None

    household = None
    if household_manager is not None:
        get_fn = getattr(household_manager, "get", None)
        if callable(get_fn):
            try:
                household = get_fn(int(target_household_id))
            except Exception:
                household = None

    if household is not None:
        for method_name in ("sim_info_gen", "instanced_sims_gen"):
            method = getattr(household, method_name, None)
            if not callable(method):
                continue
            try:
                members = tuple(method())
            except Exception:
                members = ()
            for member in members:
                _append(member)

    if services is not None:
        sim_info_manager_fn = getattr(services, "sim_info_manager", None)
        if callable(sim_info_manager_fn):
            try:
                sim_info_manager = sim_info_manager_fn()
            except Exception:
                sim_info_manager = None
            else:
                sim_info_manager = sim_info_manager
            if sim_info_manager is not None:
                get_all = getattr(sim_info_manager, "get_all", None)
                if callable(get_all):
                    try:
                        sim_infos = tuple(get_all())
                    except Exception:
                        sim_infos = ()
                    for sim_info in sim_infos:
                        _append(sim_info)

    if not out:
        for sim_info in _iter_instanced_sim_infos():
            _append(sim_info)

    return tuple(out)


def _get_buff_instance_manager():
    try:
        import sims4.resources  # type: ignore
        import services  # type: ignore
    except Exception:
        return None


def _get_services_module():
    try:
        import services  # type: ignore

        return services
    except Exception:
        return None


def _call_or_value_attr(obj, attr_name: str):
    if obj is None:
        return None
    value = getattr(obj, attr_name, None)
    if callable(value):
        try:
            return value()
        except Exception:
            return None
    return value


def _resolve_sim_ticks_per_day_local() -> Optional[int]:
    try:
        import date_and_time  # type: ignore

        fn = getattr(date_and_time, "sim_ticks_per_day", None)
        if callable(fn):
            return _coerce_int(fn())
    except Exception:
        return None
    return None


def _current_sim_absolute_ticks() -> Optional[int]:
    services = _get_services_module()
    if services is None:
        return None
    time_service_fn = getattr(services, "time_service", None)
    if not callable(time_service_fn):
        return None
    try:
        time_service = time_service_fn()
    except Exception:
        return None
    if time_service is None:
        return None
    sim_now = getattr(time_service, "sim_now", None)
    if sim_now is None:
        return None
    ticks = _call_or_value_attr(sim_now, "absolute_ticks")
    return _coerce_int(ticks)


def _sim_minutes_to_ticks(minutes: int) -> Optional[int]:
    ticks_per_day = _resolve_sim_ticks_per_day_local()
    if ticks_per_day is None or int(ticks_per_day) <= 0:
        return None
    try:
        ticks = int(round((int(ticks_per_day) * int(minutes)) / 1440.0))
    except Exception:
        return None
    return max(1, int(ticks))

    get_instance_manager = getattr(services, "get_instance_manager", None)
    if not callable(get_instance_manager):
        return None
    try:
        return get_instance_manager(sims4.resources.Types.BUFF)
    except Exception:
        return None


def _sim_info_add_buff(sim_info, buff) -> bool:
    if sim_info is None or buff is None:
        return False

    buff_id = _trait_guid64(buff)
    if buff_id is not None:
        try:
            buff_id = int(buff_id)
        except Exception:
            buff_id = None

    owners = (
        getattr(sim_info, "Buffs", None),
        getattr(sim_info, "buff_tracker", None),
        getattr(sim_info, "_buff_tracker", None),
        sim_info,
    )
    for owner in owners:
        if owner is None:
            continue
        for method_name in ("add_buff_by_type", "add_buff", "add_buff_from_op"):
            method = getattr(owner, method_name, None)
            if not callable(method):
                continue
            args_to_try = ()
            if method_name == "add_buff_by_type":
                args_to_try = ((int(buff_id),),) if buff_id is not None else ()
            else:
                args_to_try = ((buff,),)
                if buff_id is not None:
                    args_to_try = args_to_try + ((int(buff_id),),)
            for args in args_to_try:
                try:
                    method(*args)
                    return True
                except TypeError:
                    try:
                        method(*args, None)
                        return True
                    except Exception:
                        continue
                except Exception:
                    continue
    return False


def _sim_info_remove_buff(sim_info, buff) -> bool:
    if sim_info is None or buff is None:
        return False

    buff_id = _trait_guid64(buff)
    if buff_id is not None:
        try:
            buff_id = int(buff_id)
        except Exception:
            buff_id = None

    owners = (
        getattr(sim_info, "Buffs", None),
        getattr(sim_info, "buff_tracker", None),
        getattr(sim_info, "_buff_tracker", None),
        sim_info,
    )
    for owner in owners:
        if owner is None:
            continue
        for method_name in ("remove_buff_by_type", "remove_buff"):
            method = getattr(owner, method_name, None)
            if not callable(method):
                continue
            for arg in (buff, int(buff_id) if buff_id is not None else None):
                if arg is None:
                    continue
                try:
                    method(arg)
                    return True
                except TypeError:
                    try:
                        method(arg, None)
                        return True
                    except Exception:
                        continue
                except Exception:
                    continue
    return False


def _sim_info_has_buff(sim_info, buff) -> bool:
    if sim_info is None or buff is None:
        return False

    buff_id = _trait_guid64(buff)
    if buff_id is not None:
        try:
            buff_id = int(buff_id)
        except Exception:
            buff_id = None

    owners = (
        getattr(sim_info, "Buffs", None),
        getattr(sim_info, "buff_tracker", None),
        getattr(sim_info, "_buff_tracker", None),
        sim_info,
    )
    for owner in owners:
        if owner is None:
            continue

        for method_name in ("has_buff", "has_buff_by_type"):
            method = getattr(owner, method_name, None)
            if not callable(method):
                continue
            try:
                if bool(method(buff)):
                    return True
            except TypeError:
                pass
            except Exception:
                continue
            if buff_id is not None:
                try:
                    if bool(method(int(buff_id))):
                        return True
                except Exception:
                    pass

        for method_name in ("get_buff_by_type", "get_buff"):
            method = getattr(owner, method_name, None)
            if not callable(method):
                continue
            try:
                found = method(buff)
                if found is not None:
                    return True
            except TypeError:
                pass
            except Exception:
                continue
            if buff_id is not None:
                try:
                    found = method(int(buff_id))
                    if found is not None:
                        return True
                except Exception:
                    pass

        for attr_name in ("buffs", "_buffs", "active_buffs", "_active_buffs"):
            value = getattr(owner, attr_name, None)
            if value is None:
                continue
            candidates = ()
            if isinstance(value, dict):
                candidates = tuple(value.keys()) + tuple(value.values())
            else:
                values_fn = getattr(value, "values", None)
                if callable(values_fn):
                    try:
                        values = values_fn()
                    except Exception:
                        values = ()
                    try:
                        candidates = tuple(values)
                    except Exception:
                        candidates = ()
                if not candidates:
                    try:
                        candidates = tuple(value)
                    except Exception:
                        candidates = ()
            for item in candidates:
                if item is buff:
                    return True
                item_id = _trait_guid64(item)
                if item_id is None:
                    item_type = getattr(item, "buff_type", None)
                    item_id = _trait_guid64(item_type) if item_type is not None else None
                if buff_id is not None and item_id is not None:
                    try:
                        if int(item_id) == int(buff_id):
                            return True
                    except Exception:
                        continue
    return False


def _register_managed_rising_buff_expiry(sim_info, buff, sign_index: int) -> bool:
    sim_id = _coerce_int(_sim_info_id(sim_info))
    buff_id = _coerce_int(_trait_guid64(buff))
    now_ticks = _current_sim_absolute_ticks()
    duration_ticks = _sim_minutes_to_ticks(_RISING_PY_MANAGED_BUFF_DURATION_MINUTES)
    if sim_id is None or buff_id is None or now_ticks is None or duration_ticks is None:
        return False
    _RISING_MANAGED_BUFF_EXPIRY_BY_SIM_ID[int(sim_id)] = {
        "buff_id": int(buff_id),
        "sign_index": int(sign_index) % 12,
        "expires_at_ticks": int(now_ticks + duration_ticks),
        "applied_at_ticks": int(now_ticks),
    }
    return True


def _register_managed_visible_sign_buff_expiry(sim_info, buff, body: str, sign_index: int) -> bool:
    sim_id = _coerce_int(_sim_info_id(sim_info))
    buff_id = _coerce_int(_trait_guid64(buff))
    now_ticks = _current_sim_absolute_ticks()
    duration_ticks = _sim_minutes_to_ticks(_VISIBLE_SIGN_PY_MANAGED_BUFF_DURATION_MINUTES)
    if sim_id is None or buff_id is None or now_ticks is None or duration_ticks is None:
        return False
    body_text = str(body or "")
    if body_text not in ("Sun", "Moon"):
        return False
    _VISIBLE_SIGN_MANAGED_BUFF_EXPIRY_BY_SIM_BODY[(int(sim_id), body_text)] = {
        "buff_id": int(buff_id),
        "body": body_text,
        "sign_index": int(sign_index) % 12,
        "expires_at_ticks": int(now_ticks + duration_ticks),
        "applied_at_ticks": int(now_ticks),
    }
    return True


def reset_managed_rising_buff_state() -> None:
    _RISING_MANAGED_BUFF_EXPIRY_BY_SIM_ID.clear()
    _RISING_TIMED_BUFF_LAST_APPLY_BY_SIM_SIGN.clear()


def reset_managed_visible_sign_buff_state() -> None:
    _VISIBLE_SIGN_MANAGED_BUFF_EXPIRY_BY_SIM_BODY.clear()


def process_managed_rising_buffs(
    *,
    refresh_marker_cache: bool = False,
    sim_infos: Optional[Iterable[object]] = None,
) -> Dict[str, int]:
    summary = {
        "ok": 1,
        "sim_now_ticks_known": 0,
        "tracked_sims": len(_RISING_MANAGED_BUFF_EXPIRY_BY_SIM_ID),
        "expiry_entries_seeded_from_existing": 0,
        "buffs_removed": 0,
        "stale_entries_cleared": 0,
        "errors": 0,
    }
    if refresh_marker_cache:
        reset_natal_marker_cache()
    cache = _marker_cache()
    rising_buff_map = cache.get("visible_rising_timed_buff_by_index", {})
    if not isinstance(rising_buff_map, dict) or not rising_buff_map:
        return summary

    now_ticks = _current_sim_absolute_ticks()
    if now_ticks is None:
        summary["ok"] = 0
        return summary
    summary["sim_now_ticks_known"] = 1

    duration_ticks = _sim_minutes_to_ticks(_RISING_PY_MANAGED_BUFF_DURATION_MINUTES)
    if duration_ticks is None:
        summary["ok"] = 0
        return summary

    target_sim_infos = _target_instanced_sim_infos(sim_infos)
    target_sim_ids = {
        int(sim_id)
        for sim_id in (_coerce_int(_sim_info_id(sim_info)) for sim_info in target_sim_infos)
        if sim_id is not None
    }

    # Baseline any existing rising buff we find after load/travel when the in-memory
    # expiry table is empty or incomplete.
    for sim_info in target_sim_infos:
        sim_id = _coerce_int(_sim_info_id(sim_info))
        if sim_id is None:
            continue
        if int(sim_id) in _RISING_MANAGED_BUFF_EXPIRY_BY_SIM_ID:
            continue
        found = False
        for sign_index, buff in rising_buff_map.items():
            try:
                sign_index_int = int(sign_index) % 12
            except Exception:
                continue
            if buff is None or not _sim_info_has_buff(sim_info, buff):
                continue
            buff_id = _coerce_int(_trait_guid64(buff))
            if buff_id is None:
                continue
            _RISING_MANAGED_BUFF_EXPIRY_BY_SIM_ID[int(sim_id)] = {
                "buff_id": int(buff_id),
                "sign_index": int(sign_index_int),
                "expires_at_ticks": int(now_ticks + duration_ticks),
                "applied_at_ticks": int(now_ticks),
            }
            summary["expiry_entries_seeded_from_existing"] += 1
            found = True
            break
        if found:
            continue

    by_sim_id = {
        int(_sim_info_id(sim)): sim
        for sim in target_sim_infos
        if _coerce_int(_sim_info_id(sim)) is not None
    }

    for sim_id, row in tuple(_RISING_MANAGED_BUFF_EXPIRY_BY_SIM_ID.items()):
        if target_sim_ids and int(sim_id) not in target_sim_ids:
            continue
        if not isinstance(row, dict):
            _RISING_MANAGED_BUFF_EXPIRY_BY_SIM_ID.pop(int(sim_id), None)
            summary["stale_entries_cleared"] += 1
            continue
        expires_at = _coerce_int(row.get("expires_at_ticks"))
        sign_index = _coerce_int(row.get("sign_index"))
        buff_id = _coerce_int(row.get("buff_id"))
        if expires_at is None or sign_index is None or buff_id is None:
            _RISING_MANAGED_BUFF_EXPIRY_BY_SIM_ID.pop(int(sim_id), None)
            summary["stale_entries_cleared"] += 1
            continue
        if int(now_ticks) < int(expires_at):
            continue
        sim_info = by_sim_id.get(int(sim_id))
        if sim_info is None:
            _RISING_MANAGED_BUFF_EXPIRY_BY_SIM_ID.pop(int(sim_id), None)
            summary["stale_entries_cleared"] += 1
            continue
        buff = rising_buff_map.get(int(sign_index) % 12)
        if buff is None:
            _RISING_MANAGED_BUFF_EXPIRY_BY_SIM_ID.pop(int(sim_id), None)
            summary["stale_entries_cleared"] += 1
            continue
        try:
            if not _sim_info_has_buff(sim_info, buff):
                _RISING_MANAGED_BUFF_EXPIRY_BY_SIM_ID.pop(int(sim_id), None)
                summary["stale_entries_cleared"] += 1
                continue
            if _sim_info_remove_buff(sim_info, buff):
                summary["buffs_removed"] += 1
            _RISING_MANAGED_BUFF_EXPIRY_BY_SIM_ID.pop(int(sim_id), None)
        except Exception:
            summary["errors"] += 1

    summary["tracked_sims"] = len(_RISING_MANAGED_BUFF_EXPIRY_BY_SIM_ID)
    return summary


def process_managed_visible_sign_buffs(
    *,
    refresh_marker_cache: bool = False,
    sim_infos: Optional[Iterable[object]] = None,
) -> Dict[str, int]:
    summary = {
        "ok": 1,
        "sim_now_ticks_known": 0,
        "tracked_entries": len(_VISIBLE_SIGN_MANAGED_BUFF_EXPIRY_BY_SIM_BODY),
        "expiry_entries_seeded_from_existing": 0,
        "buffs_removed": 0,
        "stale_entries_cleared": 0,
        "skipped_return_owned_body": 0,
        "errors": 0,
    }
    if refresh_marker_cache:
        reset_natal_marker_cache()
    cache = _marker_cache()
    sun_buff_map = cache.get("visible_sun_timed_buff_by_index", {})
    moon_buff_map = cache.get("visible_moon_timed_buff_by_index", {})
    return_marker_ids_by_body = cache.get("return_marker_candidate_ids_by_body", {})
    if not isinstance(sun_buff_map, dict) or not isinstance(moon_buff_map, dict):
        summary["ok"] = 0
        return summary
    if not sun_buff_map and not moon_buff_map:
        return summary

    now_ticks = _current_sim_absolute_ticks()
    if now_ticks is None:
        summary["ok"] = 0
        return summary
    summary["sim_now_ticks_known"] = 1

    duration_ticks = _sim_minutes_to_ticks(_VISIBLE_SIGN_PY_MANAGED_BUFF_DURATION_MINUTES)
    if duration_ticks is None:
        summary["ok"] = 0
        return summary

    target_sim_infos = _target_instanced_sim_infos(sim_infos)
    target_sim_ids = {
        int(sim_id)
        for sim_id in (_coerce_int(_sim_info_id(sim_info)) for sim_info in target_sim_infos)
        if sim_id is not None
    }
    by_sim_id: Dict[int, object] = {}
    return_owned_bodies_by_sim_id: Dict[int, set] = {}
    for sim_info in target_sim_infos:
        sim_id = _coerce_int(_sim_info_id(sim_info))
        if sim_id is None:
            continue
        sim_id = int(sim_id)
        by_sim_id[sim_id] = sim_info

        owned_bodies = set()
        try:
            trait_ids, _ = _collect_trait_ids_and_markers(sim_info)
        except Exception:
            trait_ids = []
        for body in ("Sun", "Moon"):
            candidate_ids = (
                return_marker_ids_by_body.get(body, set())
                if isinstance(return_marker_ids_by_body, dict)
                else set()
            )
            if any(int(tid) in candidate_ids for tid in trait_ids):
                owned_bodies.add(body)
        return_owned_bodies_by_sim_id[sim_id] = owned_bodies

        for body, buff_map in (("Sun", sun_buff_map), ("Moon", moon_buff_map)):
            key = (sim_id, body)
            if key in _VISIBLE_SIGN_MANAGED_BUFF_EXPIRY_BY_SIM_BODY:
                continue
            if body in owned_bodies:
                continue
            for sign_index, buff in tuple(buff_map.items()):
                try:
                    sign_index = int(sign_index) % 12
                except Exception:
                    continue
                if buff is None or not _sim_info_has_buff(sim_info, buff):
                    continue
                buff_id = _coerce_int(_trait_guid64(buff))
                if buff_id is None:
                    continue
                _VISIBLE_SIGN_MANAGED_BUFF_EXPIRY_BY_SIM_BODY[key] = {
                    "buff_id": int(buff_id),
                    "body": body,
                    "sign_index": int(sign_index),
                    "expires_at_ticks": int(now_ticks + duration_ticks),
                    "applied_at_ticks": int(now_ticks),
                }
                summary["expiry_entries_seeded_from_existing"] += 1
                break

    for key, row in tuple(_VISIBLE_SIGN_MANAGED_BUFF_EXPIRY_BY_SIM_BODY.items()):
        if not isinstance(key, tuple) or len(key) != 2:
            _VISIBLE_SIGN_MANAGED_BUFF_EXPIRY_BY_SIM_BODY.pop(key, None)
            summary["stale_entries_cleared"] += 1
            continue
        sim_id, body = key
        sim_id = _coerce_int(sim_id)
        body = str(body or "")
        if sim_id is not None and target_sim_ids and int(sim_id) not in target_sim_ids:
            continue
        if sim_id is None or body not in ("Sun", "Moon"):
            _VISIBLE_SIGN_MANAGED_BUFF_EXPIRY_BY_SIM_BODY.pop(key, None)
            summary["stale_entries_cleared"] += 1
            continue
        sim_info = by_sim_id.get(int(sim_id))
        if sim_info is None:
            _VISIBLE_SIGN_MANAGED_BUFF_EXPIRY_BY_SIM_BODY.pop(key, None)
            summary["stale_entries_cleared"] += 1
            continue
        if body in return_owned_bodies_by_sim_id.get(int(sim_id), set()):
            _VISIBLE_SIGN_MANAGED_BUFF_EXPIRY_BY_SIM_BODY.pop(key, None)
            summary["skipped_return_owned_body"] += 1
            continue

        if not isinstance(row, dict):
            _VISIBLE_SIGN_MANAGED_BUFF_EXPIRY_BY_SIM_BODY.pop(key, None)
            summary["stale_entries_cleared"] += 1
            continue
        expires_at = _coerce_int(row.get("expires_at_ticks"))
        sign_index = _coerce_int(row.get("sign_index"))
        if expires_at is None or sign_index is None:
            _VISIBLE_SIGN_MANAGED_BUFF_EXPIRY_BY_SIM_BODY.pop(key, None)
            summary["stale_entries_cleared"] += 1
            continue
        if int(now_ticks) < int(expires_at):
            continue

        buff_map = sun_buff_map if body == "Sun" else moon_buff_map
        buff = buff_map.get(int(sign_index) % 12)
        if buff is None:
            _VISIBLE_SIGN_MANAGED_BUFF_EXPIRY_BY_SIM_BODY.pop(key, None)
            summary["stale_entries_cleared"] += 1
            continue
        try:
            if not _sim_info_has_buff(sim_info, buff):
                _VISIBLE_SIGN_MANAGED_BUFF_EXPIRY_BY_SIM_BODY.pop(key, None)
                summary["stale_entries_cleared"] += 1
                continue
            if _sim_info_remove_buff(sim_info, buff):
                summary["buffs_removed"] += 1
            _VISIBLE_SIGN_MANAGED_BUFF_EXPIRY_BY_SIM_BODY.pop(key, None)
        except Exception:
            summary["errors"] += 1

    summary["tracked_entries"] = len(_VISIBLE_SIGN_MANAGED_BUFF_EXPIRY_BY_SIM_BODY)
    return summary


def _apply_visible_sign_timed_buff_for_trait_add(
    sim_info,
    visible_sign_trait,
    *,
    cache: Mapping[str, object],
) -> bool:
    parsed = _parse_visible_sign_reward_trait_name(_trait_name(visible_sign_trait))
    if parsed is None:
        return False
    body, sign_index = parsed

    buff_map = (
        cache.get("visible_sun_timed_buff_by_index", {})
        if body == "Sun"
        else cache.get("visible_moon_timed_buff_by_index", {})
    )
    if not isinstance(buff_map, dict):
        return False
    buff = buff_map.get(int(sign_index))
    if buff is None:
        return False
    if _sim_info_has_buff(sim_info, buff):
        _register_managed_visible_sign_buff_expiry(sim_info, buff, body, int(sign_index))
        return False

    # Keep one visible sign flare buff per body.
    for other_index, other_buff in tuple(buff_map.items()):
        try:
            other_index = int(other_index) % 12
        except Exception:
            continue
        if other_index == int(sign_index):
            continue
        if other_buff is None:
            continue
        if _sim_info_has_buff(sim_info, other_buff):
            _sim_info_remove_buff(sim_info, other_buff)
    added = _sim_info_add_buff(sim_info, buff)
    if added:
        _register_managed_visible_sign_buff_expiry(sim_info, buff, body, int(sign_index))
    return added


def _apply_visible_rising_timed_buff_for_sign_index(
    sim_info,
    sign_index: Optional[int],
    *,
    cache: Mapping[str, object],
) -> bool:
    if sign_index is None:
        return False
    try:
        sign_index = int(sign_index) % 12
    except Exception:
        return False

    buff_map = cache.get("visible_rising_timed_buff_by_index", {})
    if not isinstance(buff_map, dict):
        return False
    buff = buff_map.get(int(sign_index))
    if buff is None:
        return False
    if _sim_info_has_buff(sim_info, buff):
        _register_managed_rising_buff_expiry(sim_info, buff, int(sign_index))
        return False

    # Rising should only surface one visible timed moodlet at a time.
    for other_index, other_buff in tuple(buff_map.items()):
        try:
            other_index = int(other_index) % 12
        except Exception:
            continue
        if other_index == int(sign_index):
            continue
        if other_buff is None:
            continue
        if _sim_info_has_buff(sim_info, other_buff):
            _sim_info_remove_buff(sim_info, other_buff)

    sim_key = None
    try:
        sim_key = int(_sim_info_id(sim_info))
    except Exception:
        sim_key = None

    if sim_key is not None:
        cache_key = (int(sim_key), int(sign_index))
        now = time.monotonic()
        last = _RISING_TIMED_BUFF_LAST_APPLY_BY_SIM_SIGN.get(cache_key)
        if last is not None and (now - float(last)) < _RISING_TIMED_BUFF_APPLY_DEBOUNCE_SECONDS:
            return False
        if _sim_info_add_buff(sim_info, buff):
            _RISING_TIMED_BUFF_LAST_APPLY_BY_SIM_SIGN[cache_key] = time.monotonic()
            _register_managed_rising_buff_expiry(sim_info, buff, int(sign_index))
            return True
        return False

    added = _sim_info_add_buff(sim_info, buff)
    if added:
        _register_managed_rising_buff_expiry(sim_info, buff, int(sign_index))
    return added


def apply_visible_rising_timed_buff_for_sim_info(
    sim_info,
    *,
    refresh_marker_cache: bool = False,
) -> Dict[str, int]:
    summary = {
        "ok": 0,
        "has_rising_sign": 0,
        "has_visible_rising_buff_def": 0,
        "buff_applied": 0,
    }
    if sim_info is None:
        return summary
    if refresh_marker_cache:
        reset_natal_marker_cache()
    cache = _marker_cache()

    rising_buff_map = cache.get("visible_rising_timed_buff_by_index", {})
    if not isinstance(rising_buff_map, dict) or not rising_buff_map:
        return summary

    personality_map = cache.get("rising_personality_sign_index_by_trait_id", {})
    marker_map = cache.get("rising_marker_sign_index_by_trait_id", {})
    if not isinstance(personality_map, dict):
        personality_map = {}
    if not isinstance(marker_map, dict):
        marker_map = {}

    trait_ids, _ = _collect_trait_ids_and_markers(sim_info)
    sign_index = None
    for tid in trait_ids:
        idx = personality_map.get(int(tid))
        if idx is None:
            idx = marker_map.get(int(tid))
        if isinstance(idx, int):
            sign_index = int(idx) % 12
            break

    summary["ok"] = 1
    if sign_index is None:
        return summary

    summary["has_rising_sign"] = 1
    if int(sign_index) in rising_buff_map:
        summary["has_visible_rising_buff_def"] = 1
    if _apply_visible_rising_timed_buff_for_sign_index(sim_info, sign_index, cache=cache):
        summary["buff_applied"] = 1
    return summary


def _rebuild_marker_cache() -> Dict[str, object]:
    available_by_body_house: Dict[Tuple[str, int], object] = {}
    candidate_ids_by_body: Dict[str, set] = {body: set() for body in BODY_NAMES}
    planet_house_candidate_ids: set = set()
    sun_sign_trait_by_index: Dict[int, object] = {}
    moon_sign_trait_by_index: Dict[int, object] = {}
    sign_candidate_ids_by_body: Dict[str, set] = {"Sun": set(), "Moon": set()}
    visible_sun_reward_trait_by_index: Dict[int, object] = {}
    visible_moon_reward_trait_by_index: Dict[int, object] = {}
    visible_sign_reward_candidate_ids_by_body: Dict[str, set] = {"Sun": set(), "Moon": set()}
    visible_sun_timed_buff_by_index: Dict[int, object] = {}
    visible_moon_timed_buff_by_index: Dict[int, object] = {}
    return_marker_candidate_ids_by_body: Dict[str, set] = {"Sun": set(), "Moon": set()}
    hidden_chart_ruler_body_by_trait_id: Dict[int, str] = {}
    visible_chart_ruler_reward_trait_by_body: Dict[str, object] = {}
    visible_chart_ruler_reward_candidate_ids: set = set()
    visible_chart_ruler_reward_body_by_trait_id: Dict[int, str] = {}
    visible_rising_timed_buff_by_index: Dict[int, object] = {}
    personality_rising_trait_by_index: Dict[int, object] = {}
    rising_marker_trait_by_index: Dict[int, object] = {}
    rising_personality_candidate_ids: set = set()
    rising_marker_candidate_ids: set = set()
    rising_personality_sign_index_by_trait_id: Dict[int, int] = {}
    rising_marker_sign_index_by_trait_id: Dict[int, int] = {}
    capture_flag_trait = None
    capture_flag_trait_id = None
    legacy_flag_trait = None
    legacy_flag_trait_id = None

    for trait in _iter_manager_trait_tunings(_get_trait_instance_manager()):
        name = _trait_name(trait)
        if name == _NATAL_CAPTURE_FLAG_NAME:
            capture_flag_trait = trait
            tid = _trait_guid64(trait)
            if tid is not None:
                capture_flag_trait_id = int(tid)
            continue
        if name == _NATAL_LEGACY_FLAG_NAME:
            legacy_flag_trait = trait
            tid = _trait_guid64(trait)
            if tid is not None:
                legacy_flag_trait_id = int(tid)
            continue

        sign_parsed = _parse_natal_sign_marker_name(name)
        if sign_parsed is not None:
            tid = _trait_guid64(trait)
            if tid is None:
                continue
            body, sign_index = sign_parsed
            if body == "Sun":
                sun_sign_trait_by_index.setdefault(int(sign_index), trait)
            elif body == "Moon":
                moon_sign_trait_by_index.setdefault(int(sign_index), trait)
            sign_candidate_ids_by_body.setdefault(body, set()).add(int(tid))
            continue

        visible_sign_parsed = _parse_visible_sign_reward_trait_name(name)
        if visible_sign_parsed is not None:
            tid = _trait_guid64(trait)
            if tid is None:
                continue
            body, sign_index = visible_sign_parsed
            if body == "Sun":
                visible_sun_reward_trait_by_index.setdefault(int(sign_index), trait)
            elif body == "Moon":
                visible_moon_reward_trait_by_index.setdefault(int(sign_index), trait)
            visible_sign_reward_candidate_ids_by_body.setdefault(body, set()).add(int(tid))
            continue

        return_sign_parsed = _parse_return_sign_marker_name(name)
        if return_sign_parsed is not None:
            tid = _trait_guid64(trait)
            if tid is None:
                continue
            body, _sign_index = return_sign_parsed
            return_marker_candidate_ids_by_body.setdefault(body, set()).add(int(tid))
            continue

        hidden_chart_ruler_body = _parse_hidden_chart_ruler_marker_name(name)
        if hidden_chart_ruler_body is not None:
            tid = _trait_guid64(trait)
            if tid is None:
                continue
            hidden_chart_ruler_body_by_trait_id[int(tid)] = str(hidden_chart_ruler_body)
            continue

        visible_chart_ruler_body = _parse_visible_chart_ruler_reward_trait_name(name)
        if visible_chart_ruler_body is not None:
            tid = _trait_guid64(trait)
            if tid is None:
                continue
            visible_chart_ruler_reward_trait_by_body.setdefault(str(visible_chart_ruler_body), trait)
            visible_chart_ruler_reward_candidate_ids.add(int(tid))
            visible_chart_ruler_reward_body_by_trait_id[int(tid)] = str(visible_chart_ruler_body)
            continue

        rising_parsed = _parse_rising_sign_trait_name(name)
        if rising_parsed is not None:
            tid = _trait_guid64(trait)
            if tid is None:
                continue
            sign_index, marker_hint = rising_parsed
            bucket = _classify_rising_trait_bucket(trait, marker_hint=marker_hint)
            if bucket == "marker":
                if _prefer_visible_gameplay_rising_marker(
                    rising_marker_trait_by_index.get(int(sign_index)),
                    trait,
                    candidate_marker_hint=marker_hint,
                ):
                    rising_marker_trait_by_index[int(sign_index)] = trait
                rising_marker_candidate_ids.add(int(tid))
                rising_marker_sign_index_by_trait_id[int(tid)] = int(sign_index)
            else:
                personality_rising_trait_by_index.setdefault(int(sign_index), trait)
                rising_personality_candidate_ids.add(int(tid))
                rising_personality_sign_index_by_trait_id[int(tid)] = int(sign_index)
            continue

        parsed = _parse_natal_planet_house_marker_name(name)
        if parsed is None:
            continue
        tid = _trait_guid64(trait)
        if tid is None:
            continue
        body, house_index = parsed
        available_by_body_house.setdefault((body, house_index), trait)
        candidate_ids_by_body.setdefault(body, set()).add(int(tid))
        planet_house_candidate_ids.add(int(tid))

    for buff in _iter_manager_trait_tunings(_get_buff_instance_manager()):
        buff_name = _trait_name(buff)
        parsed = _parse_visible_sign_timed_buff_name(buff_name)
        if parsed is not None:
            body, sign_index = parsed
            if body == "Sun":
                visible_sun_timed_buff_by_index.setdefault(int(sign_index), buff)
            elif body == "Moon":
                visible_moon_timed_buff_by_index.setdefault(int(sign_index), buff)
            continue
        rising_sign_index = _parse_visible_rising_timed_buff_name(buff_name)
        if rising_sign_index is not None:
            visible_rising_timed_buff_by_index.setdefault(int(rising_sign_index), buff)

    _MARKER_CACHE["initialized"] = True
    _MARKER_CACHE["available_by_body_house"] = available_by_body_house
    _MARKER_CACHE["candidate_ids_by_body"] = candidate_ids_by_body
    _MARKER_CACHE["planet_house_candidate_ids"] = planet_house_candidate_ids
    _MARKER_CACHE["sun_sign_trait_by_index"] = sun_sign_trait_by_index
    _MARKER_CACHE["moon_sign_trait_by_index"] = moon_sign_trait_by_index
    _MARKER_CACHE["sign_candidate_ids_by_body"] = sign_candidate_ids_by_body
    _MARKER_CACHE["visible_sun_reward_trait_by_index"] = visible_sun_reward_trait_by_index
    _MARKER_CACHE["visible_moon_reward_trait_by_index"] = visible_moon_reward_trait_by_index
    _MARKER_CACHE["visible_sign_reward_candidate_ids_by_body"] = visible_sign_reward_candidate_ids_by_body
    _MARKER_CACHE["visible_sun_timed_buff_by_index"] = visible_sun_timed_buff_by_index
    _MARKER_CACHE["visible_moon_timed_buff_by_index"] = visible_moon_timed_buff_by_index
    _MARKER_CACHE["return_marker_candidate_ids_by_body"] = return_marker_candidate_ids_by_body
    _MARKER_CACHE["hidden_chart_ruler_body_by_trait_id"] = hidden_chart_ruler_body_by_trait_id
    _MARKER_CACHE["visible_chart_ruler_reward_trait_by_body"] = visible_chart_ruler_reward_trait_by_body
    _MARKER_CACHE["visible_chart_ruler_reward_candidate_ids"] = visible_chart_ruler_reward_candidate_ids
    _MARKER_CACHE["visible_chart_ruler_reward_body_by_trait_id"] = visible_chart_ruler_reward_body_by_trait_id
    _MARKER_CACHE["visible_rising_timed_buff_by_index"] = visible_rising_timed_buff_by_index
    _MARKER_CACHE["personality_rising_trait_by_index"] = personality_rising_trait_by_index
    _MARKER_CACHE["rising_marker_trait_by_index"] = rising_marker_trait_by_index
    _MARKER_CACHE["rising_personality_candidate_ids"] = rising_personality_candidate_ids
    _MARKER_CACHE["rising_marker_candidate_ids"] = rising_marker_candidate_ids
    _MARKER_CACHE["rising_personality_sign_index_by_trait_id"] = rising_personality_sign_index_by_trait_id
    _MARKER_CACHE["rising_marker_sign_index_by_trait_id"] = rising_marker_sign_index_by_trait_id
    _MARKER_CACHE["capture_flag_trait"] = capture_flag_trait
    _MARKER_CACHE["capture_flag_trait_id"] = capture_flag_trait_id
    _MARKER_CACHE["legacy_flag_trait"] = legacy_flag_trait
    _MARKER_CACHE["legacy_flag_trait_id"] = legacy_flag_trait_id
    return _MARKER_CACHE


def _marker_cache() -> Dict[str, object]:
    if not _MARKER_CACHE.get("initialized"):
        return _rebuild_marker_cache()
    return _MARKER_CACHE


def reset_natal_marker_cache() -> None:
    _MARKER_CACHE["initialized"] = False
    _MARKER_CACHE["available_by_body_house"] = {}
    _MARKER_CACHE["candidate_ids_by_body"] = {}
    _MARKER_CACHE["planet_house_candidate_ids"] = set()
    _MARKER_CACHE["sun_sign_trait_by_index"] = {}
    _MARKER_CACHE["moon_sign_trait_by_index"] = {}
    _MARKER_CACHE["sign_candidate_ids_by_body"] = {}
    _MARKER_CACHE["visible_sun_reward_trait_by_index"] = {}
    _MARKER_CACHE["visible_moon_reward_trait_by_index"] = {}
    _MARKER_CACHE["visible_sign_reward_candidate_ids_by_body"] = {}
    _MARKER_CACHE["visible_sun_timed_buff_by_index"] = {}
    _MARKER_CACHE["visible_moon_timed_buff_by_index"] = {}
    _MARKER_CACHE["return_marker_candidate_ids_by_body"] = {}
    _MARKER_CACHE["hidden_chart_ruler_body_by_trait_id"] = {}
    _MARKER_CACHE["visible_chart_ruler_reward_trait_by_body"] = {}
    _MARKER_CACHE["visible_chart_ruler_reward_candidate_ids"] = set()
    _MARKER_CACHE["visible_chart_ruler_reward_body_by_trait_id"] = {}
    _MARKER_CACHE["visible_rising_timed_buff_by_index"] = {}
    _MARKER_CACHE["personality_rising_trait_by_index"] = {}
    _MARKER_CACHE["rising_marker_trait_by_index"] = {}
    _MARKER_CACHE["rising_personality_candidate_ids"] = set()
    _MARKER_CACHE["rising_marker_candidate_ids"] = set()
    _MARKER_CACHE["rising_personality_sign_index_by_trait_id"] = {}
    _MARKER_CACHE["rising_marker_sign_index_by_trait_id"] = {}
    _MARKER_CACHE["capture_flag_trait"] = None
    _MARKER_CACHE["capture_flag_trait_id"] = None
    _MARKER_CACHE["legacy_flag_trait"] = None
    _MARKER_CACHE["legacy_flag_trait_id"] = None


def _desired_natal_traits_for_sim(
    transit_service: CosmicTransitService,
    house_sign_map: Mapping[int, int],
    available_by_body_house: Mapping[Tuple[str, int], object],
) -> Dict[str, object]:
    body_chart = transit_service.chart_for_house_sign_map(house_sign_map)
    desired: Dict[str, object] = {}
    for body in BODY_NAMES:
        row = body_chart.get(body, {})
        house_index = row.get("house_index")
        if not isinstance(house_index, int):
            continue
        trait = available_by_body_house.get((body, int(house_index)))
        if trait is None:
            continue
        desired[body] = trait
    return desired


def _desired_natal_traits_for_body_sign_indexes(
    *,
    house_sign_map: Mapping[int, int],
    available_by_body_house: Mapping[Tuple[str, int], object],
    body_sign_index_by_name: Mapping[str, int],
) -> Dict[str, object]:
    sign_to_house_index = {
        int(sign_index) % 12: int(house_index)
        for house_index, sign_index in house_sign_map.items()
        if isinstance(house_index, int) and isinstance(sign_index, int)
    }
    desired: Dict[str, object] = {}
    for body in BODY_NAMES:
        sign_index = body_sign_index_by_name.get(body)
        if not isinstance(sign_index, int):
            continue
        house_index = sign_to_house_index.get(int(sign_index) % 12)
        if not isinstance(house_index, int):
            continue
        trait = available_by_body_house.get((body, int(house_index)))
        if trait is not None:
            desired[body] = trait
    return desired


def _desired_natal_sign_traits_from_current_sky(
    transit_service: CosmicTransitService,
    sun_sign_trait_by_index: Mapping[int, object],
    moon_sign_trait_by_index: Mapping[int, object],
) -> Dict[str, object]:
    state = transit_service.state
    desired: Dict[str, object] = {}
    sun_index = state.sign_index_by_body.get("Sun")
    moon_index = state.sign_index_by_body.get("Moon")
    if isinstance(sun_index, int):
        trait = sun_sign_trait_by_index.get(int(sun_index) % 12)
        if trait is not None:
            desired["Sun"] = trait
    if isinstance(moon_index, int):
        trait = moon_sign_trait_by_index.get(int(moon_index) % 12)
        if trait is not None:
            desired["Moon"] = trait
    return desired


def _desired_natal_sign_traits_from_sign_indexes(
    *,
    sign_index_by_body: Mapping[str, int],
    sun_sign_trait_by_index: Mapping[int, object],
    moon_sign_trait_by_index: Mapping[int, object],
) -> Dict[str, object]:
    desired: Dict[str, object] = {}
    sun_index = sign_index_by_body.get("Sun")
    moon_index = sign_index_by_body.get("Moon")
    if isinstance(sun_index, int):
        trait = sun_sign_trait_by_index.get(int(sun_index) % 12)
        if trait is not None:
            desired["Sun"] = trait
    if isinstance(moon_index, int):
        trait = moon_sign_trait_by_index.get(int(moon_index) % 12)
        if trait is not None:
            desired["Moon"] = trait
    return desired


def _stable_legacy_rng_for_sim(
    sim_info,
    transit_service: CosmicTransitService,
) -> random.Random:
    seed_value = None
    try:
        record = transit_service.build_save_record()
        if isinstance(record, dict):
            seed_value = record.get("seed")
    except Exception:
        seed_value = None
    base_seed = _coerce_int(seed_value)
    if base_seed is None:
        base_seed = 0
    sim_seed = _sim_info_id(sim_info)
    mixed = ((int(base_seed) & 0xFFFFFFFFFFFFFFFF) ^ (int(sim_seed) * 0x9E3779B185EBCA87)) & 0xFFFFFFFFFFFFFFFF
    return random.Random(mixed)


def _legacy_sign_indexes_by_body(
    *,
    sim_info,
    transit_service: CosmicTransitService,
) -> Dict[str, int]:
    rng = _stable_legacy_rng_for_sim(sim_info, transit_service)
    sun_index = int(rng.randrange(12))
    moon_index = int(rng.randrange(12))
    mercury_index = (sun_index + int(rng.choice((-1, 0, 1)))) % 12
    venus_index = (sun_index + int(rng.choice((-1, 0, 1)))) % 12
    mars_index = int(rng.randrange(12))
    jupiter_index = int(rng.randrange(12))
    saturn_index = int(rng.randrange(12))
    return {
        "Sun": sun_index,
        "Moon": moon_index,
        "Mercury": mercury_index,
        "Venus": venus_index,
        "Mars": mars_index,
        "Jupiter": jupiter_index,
        "Saturn": saturn_index,
    }


def _desired_legacy_natal_traits_for_sim(
    *,
    sim_info,
    transit_service: CosmicTransitService,
    house_sign_map: Mapping[int, int],
    available_by_body_house: Mapping[Tuple[str, int], object],
    sun_sign_trait_by_index: Mapping[int, object],
    moon_sign_trait_by_index: Mapping[int, object],
) -> Tuple[Dict[str, object], Dict[str, object]]:
    sign_index_by_body = _legacy_sign_indexes_by_body(
        sim_info=sim_info,
        transit_service=transit_service,
    )
    sign_to_house_index = {int(sign_index): int(house_index) for house_index, sign_index in house_sign_map.items()}

    desired_planet_house: Dict[str, object] = {}
    for body in BODY_NAMES:
        sign_index = sign_index_by_body.get(body)
        if not isinstance(sign_index, int):
            continue
        house_index = sign_to_house_index.get(int(sign_index) % 12)
        if not isinstance(house_index, int):
            continue
        trait = available_by_body_house.get((body, int(house_index)))
        if trait is not None:
            desired_planet_house[body] = trait

    desired_sign_traits: Dict[str, object] = {}
    sun_trait = sun_sign_trait_by_index.get(int(sign_index_by_body.get("Sun", 0)) % 12)
    moon_trait = moon_sign_trait_by_index.get(int(sign_index_by_body.get("Moon", 0)) % 12)
    if sun_trait is not None:
        desired_sign_traits["Sun"] = sun_trait
    if moon_trait is not None:
        desired_sign_traits["Moon"] = moon_trait
    return desired_planet_house, desired_sign_traits


def _extract_equipped_natal_house_indexes_for_bodies(
    equipped_traits_with_ids: Iterable[Tuple[object, int]],
    bodies: Iterable[str],
) -> Dict[str, int]:
    bodies_set = set(str(body) for body in bodies)
    found: Dict[str, int] = {}
    for equipped_trait, _equipped_tid in equipped_traits_with_ids:
        parsed = _parse_natal_planet_house_marker_name(_trait_name(equipped_trait))
        if parsed is None:
            continue
        body, house_index = parsed
        if body not in bodies_set:
            continue
        found.setdefault(body, int(house_index))
    return found


def _body_sign_indexes_from_existing_natal_markers(
    *,
    equipped_traits_with_ids: Iterable[Tuple[object, int]],
    house_sign_map: Mapping[int, int],
) -> Dict[str, int]:
    desired: Dict[str, int] = {}
    body_to_house_index = _extract_equipped_natal_house_indexes_for_bodies(
        equipped_traits_with_ids,
        BODY_NAMES,
    )
    for body, house_index in body_to_house_index.items():
        sign_index = house_sign_map.get(int(house_index))
        if not isinstance(sign_index, int):
            continue
        desired[str(body)] = int(sign_index) % 12
    return desired


def _visible_sign_indexes_from_equipped_traits(
    equipped_traits_with_ids: Iterable[Tuple[object, int]],
) -> Dict[str, int]:
    desired: Dict[str, int] = {}
    for equipped_trait, _equipped_tid in equipped_traits_with_ids:
        parsed = _parse_visible_sign_reward_trait_name(_trait_name(equipped_trait))
        if parsed is None:
            continue
        body, sign_index = parsed
        desired.setdefault(str(body), int(sign_index) % 12)
    return desired


def _has_complete_equipped_sun_moon_sign_state(
    *,
    equipped_ids: Iterable[int],
    sign_candidate_ids_by_body: Mapping[str, Iterable[int]],
    visible_sign_reward_candidate_ids_by_body: Mapping[str, Iterable[int]],
    require_visible_rewards: bool,
) -> bool:
    equipped_id_set = {int(tid) for tid in equipped_ids}
    for body in ("Sun", "Moon"):
        candidate_ids = sign_candidate_ids_by_body.get(body, ())
        if not any(int(tid) in equipped_id_set for tid in candidate_ids):
            return False

    if not require_visible_rewards:
        return True

    for body in ("Sun", "Moon"):
        candidate_ids = visible_sign_reward_candidate_ids_by_body.get(body, ())
        if not any(int(tid) in equipped_id_set for tid in candidate_ids):
            return False
    return True


def _sim_info_id(sim_info) -> Optional[int]:
    if sim_info is None:
        return None
    for attr_name in ("sim_id", "id", "guid64"):
        value = getattr(sim_info, attr_name, None)
        if value is None:
            continue
        try:
            return int(value)
        except Exception:
            continue
    return None


def _chart_payload_is_complete(payload: Optional[Mapping[str, object]]) -> bool:
    if not isinstance(payload, Mapping):
        return False
    house_sign_by_index = payload.get("house_sign_by_index")
    house_by_body = payload.get("house_by_body")
    return bool(
        payload.get("sun_sign_index") is not None
        and payload.get("moon_sign_index") is not None
        and payload.get("rising_sign_index") is not None
        and isinstance(house_sign_by_index, Mapping)
        and isinstance(house_by_body, Mapping)
        and len(dict(house_sign_by_index)) >= 12
        and len(dict(house_by_body)) >= len(BODY_NAMES)
    )


def _complete_chart_body_sign_indexes_from_existing_traits(
    *,
    equipped_traits_with_ids: Iterable[Tuple[object, int]],
    house_sign_map: Mapping[int, int],
    sun_sign_trait_by_index: Mapping[int, object],
    moon_sign_trait_by_index: Mapping[int, object],
) -> Optional[Dict[str, int]]:
    existing_body_sign_indexes = _body_sign_indexes_from_existing_natal_markers(
        equipped_traits_with_ids=equipped_traits_with_ids,
        house_sign_map=house_sign_map,
    )
    if len(existing_body_sign_indexes) < len(BODY_NAMES):
        return None

    desired_sign_traits = _desired_natal_sign_traits_from_existing_natal_markers(
        equipped_traits_with_ids=equipped_traits_with_ids,
        house_sign_map=house_sign_map,
        sun_sign_trait_by_index=sun_sign_trait_by_index,
        moon_sign_trait_by_index=moon_sign_trait_by_index,
    )
    if len(desired_sign_traits) < 2:
        return None

    return dict(existing_body_sign_indexes)


def _desired_natal_sign_traits_from_existing_natal_markers(
    *,
    equipped_traits_with_ids: Iterable[Tuple[object, int]],
    house_sign_map: Mapping[int, int],
    sun_sign_trait_by_index: Mapping[int, object],
    moon_sign_trait_by_index: Mapping[int, object],
) -> Dict[str, object]:
    desired: Dict[str, object] = {}
    body_to_house_index = _extract_equipped_natal_house_indexes_for_bodies(
        equipped_traits_with_ids,
        ("Sun", "Moon"),
    )
    for body, house_index in body_to_house_index.items():
        sign_index = house_sign_map.get(int(house_index))
        if not isinstance(sign_index, int):
            continue
        sign_index = int(sign_index) % 12
        if body == "Sun":
            trait = sun_sign_trait_by_index.get(sign_index)
        else:
            trait = moon_sign_trait_by_index.get(sign_index)
        if trait is not None:
            desired[body] = trait
    return desired


def _desired_visible_sign_reward_traits_from_natal_sign_traits(
    desired_natal_sign_traits: Mapping[str, object],
    visible_sun_reward_trait_by_index: Mapping[int, object],
    visible_moon_reward_trait_by_index: Mapping[int, object],
) -> Dict[str, object]:
    desired: Dict[str, object] = {}
    for body in ("Sun", "Moon"):
        natal_trait = desired_natal_sign_traits.get(body)
        if natal_trait is None:
            continue
        parsed = _parse_natal_sign_marker_name(_trait_name(natal_trait))
        if parsed is None:
            continue
        parsed_body, sign_index = parsed
        if parsed_body != body:
            continue
        if body == "Sun":
            visible_trait = visible_sun_reward_trait_by_index.get(int(sign_index) % 12)
        else:
            visible_trait = visible_moon_reward_trait_by_index.get(int(sign_index) % 12)
        if visible_trait is not None:
            desired[body] = visible_trait
    return desired


def _reconcile_visible_chart_ruler_rewards(
    *,
    sim_info,
    trait_tracker,
    equipped_traits_with_ids: Iterable[Tuple[object, int]],
    equipped_ids: set,
    hidden_chart_ruler_body_by_trait_id: Mapping[int, str],
    visible_chart_ruler_reward_trait_by_body: Mapping[str, object],
    visible_chart_ruler_reward_body_by_trait_id: Mapping[int, str],
) -> Dict[str, int]:
    summary = {
        "changed": 0,
        "traits_added": 0,
        "traits_removed": 0,
        "chart_ruler_visible_traits_added": 0,
        "chart_ruler_visible_traits_removed": 0,
    }

    desired_body = None  # type: Optional[str]
    for _trait, tid in equipped_traits_with_ids:
        body = hidden_chart_ruler_body_by_trait_id.get(int(tid))
        if isinstance(body, str) and body in BODY_NAMES:
            desired_body = str(body)
            break

    visible_present_by_body: Dict[str, Tuple[object, int]] = {}
    for equipped_trait, equipped_tid in equipped_traits_with_ids:
        visible_body = visible_chart_ruler_reward_body_by_trait_id.get(int(equipped_tid))
        if isinstance(visible_body, str) and visible_body in BODY_NAMES:
            visible_present_by_body.setdefault(str(visible_body), (equipped_trait, int(equipped_tid)))

    desired_visible_trait = (
        visible_chart_ruler_reward_trait_by_body.get(str(desired_body))
        if isinstance(desired_body, str)
        else None
    )
    desired_visible_tid = _trait_guid64(desired_visible_trait) if desired_visible_trait is not None else None
    if desired_visible_tid is not None:
        desired_visible_tid = int(desired_visible_tid)

    for visible_body, (equipped_trait, equipped_tid) in tuple(visible_present_by_body.items()):
        if (
            desired_body is not None
            and str(visible_body) == str(desired_body)
            and desired_visible_tid is not None
            and int(equipped_tid) == int(desired_visible_tid)
        ):
            continue
        if _trait_tracker_remove_trait(sim_info, trait_tracker, equipped_trait):
            summary["changed"] += 1
            summary["traits_removed"] += 1
            summary["chart_ruler_visible_traits_removed"] += 1
            equipped_ids.discard(int(equipped_tid))

    if (
        desired_visible_trait is not None
        and desired_visible_tid is not None
        and int(desired_visible_tid) not in equipped_ids
    ):
        if _trait_tracker_add_trait(sim_info, trait_tracker, desired_visible_trait):
            summary["changed"] += 1
            summary["traits_added"] += 1
            summary["chart_ruler_visible_traits_added"] += 1
            equipped_ids.add(int(desired_visible_tid))

    return summary


def _reconcile_rising_marker_guard(
    *,
    sim_info,
    trait_tracker,
    is_teen_plus: bool,
    rising_age_lane: Optional[str] = None,
    equipped_traits_with_ids: Iterable[Tuple[object, int]],
    equipped_ids: set,
    personality_rising_trait_by_index: Mapping[int, object],
    rising_marker_trait_by_index: Mapping[int, object],
    rising_personality_sign_index_by_trait_id: Mapping[int, int],
    rising_marker_sign_index_by_trait_id: Mapping[int, int],
) -> Dict[str, int]:
    summary = {
        "changed": 0,
        "traits_added": 0,
        "traits_removed": 0,
        "rising_marker_added_preteen": 0,
        "rising_marker_removed_preteen": 0,
        "rising_promoted_to_personality": 0,
        "rising_promotion_skipped_teen_lane": 0,
        "rising_promotion_deferred_teen": 0,
        "rising_promotion_deferred_adult": 0,
        "rising_marker_removed_teen": 0,
        "rising_marker_removed_adult": 0,
        "rising_lane_preteen_seen": 0,
        "rising_lane_teen_seen": 0,
        "rising_lane_adult_seen": 0,
        "rising_lane_unknown_seen": 0,
    }
    lane = str(rising_age_lane or "").strip().lower()
    if lane not in ("preteen", "teen", "adult_plus", "unknown"):
        lane = "adult_plus" if is_teen_plus else "preteen"
    if lane == "preteen":
        summary["rising_lane_preteen_seen"] += 1
    elif lane == "teen":
        summary["rising_lane_teen_seen"] += 1
    elif lane == "adult_plus":
        summary["rising_lane_adult_seen"] += 1
    else:
        summary["rising_lane_unknown_seen"] += 1

    personality_present_by_sign: Dict[int, Tuple[object, int]] = {}
    marker_present_by_sign: Dict[int, Tuple[object, int]] = {}
    for equipped_trait, equipped_tid in equipped_traits_with_ids:
        personality_sign_index = rising_personality_sign_index_by_trait_id.get(int(equipped_tid))
        if isinstance(personality_sign_index, int):
            personality_present_by_sign.setdefault(
                int(personality_sign_index),
                (equipped_trait, int(equipped_tid)),
            )
            continue
        marker_sign_index = rising_marker_sign_index_by_trait_id.get(int(equipped_tid))
        if isinstance(marker_sign_index, int):
            marker_present_by_sign.setdefault(
                int(marker_sign_index),
                (equipped_trait, int(equipped_tid)),
            )

    personality_sign_index = next(iter(personality_present_by_sign.keys()), None)
    marker_sign_index = next(iter(marker_present_by_sign.keys()), None)
    # Canonical Rising state lives in the hidden marker layer. Visible personality
    # traits are an optional mirror for lanes that can safely support them.
    desired_sign_index = marker_sign_index if marker_sign_index is not None else personality_sign_index
    if desired_sign_index is None:
        return summary

    desired_marker_trait = rising_marker_trait_by_index.get(int(desired_sign_index))
    desired_marker_tid = _trait_guid64(desired_marker_trait) if desired_marker_trait is not None else None
    if desired_marker_tid is not None:
        desired_marker_tid = int(desired_marker_tid)

    if lane == "teen" and personality_sign_index is not None:
        # Teen gameplay already exposes Rising through the personality-style
        # trait lane. Do not mirror a second Rising marker onto teens that
        # already have a determined Rising, or they can end up with duplicate
        # visible Rising signs after onboarding/catchup passes.
        desired_marker_trait = None
        desired_marker_tid = None

    for _sign_index, (equipped_trait, equipped_tid) in tuple(marker_present_by_sign.items()):
        if desired_marker_tid is not None and int(equipped_tid) == int(desired_marker_tid):
            continue
        if _trait_tracker_remove_trait(sim_info, trait_tracker, equipped_trait):
            summary["changed"] += 1
            summary["traits_removed"] += 1
            if lane == "teen":
                summary["rising_marker_removed_teen"] += 1
            elif lane == "adult_plus":
                summary["rising_marker_removed_adult"] += 1
            else:
                summary["rising_marker_removed_preteen"] += 1
            equipped_ids.discard(int(equipped_tid))

    if (
        desired_marker_trait is not None
        and desired_marker_tid is not None
        and int(desired_marker_tid) not in equipped_ids
    ):
        if _trait_tracker_add_trait(sim_info, trait_tracker, desired_marker_trait):
            summary["changed"] += 1
            summary["traits_added"] += 1
            if lane == "teen":
                summary["rising_promotion_skipped_teen_lane"] += 1
            elif lane != "adult_plus":
                summary["rising_marker_added_preteen"] += 1
            equipped_ids.add(int(desired_marker_tid))
            marker_sign_index = int(desired_sign_index)
            marker_present_by_sign[int(desired_sign_index)] = (
                desired_marker_trait,
                int(desired_marker_tid),
            )
            _apply_visible_rising_timed_buff_for_sign_index(
                sim_info,
                int(desired_sign_index),
                cache=_marker_cache(),
            )

    if lane in ("preteen", "teen") or (lane == "unknown" and not is_teen_plus):
        if lane == "teen" and marker_sign_index is not None and personality_sign_index is None:
            # Teen lane now prefers the gameplay-visible Rising trait; personality
            # promotion is still optional for legacy saves and slot-limited cases.
            summary["rising_promotion_skipped_teen_lane"] += 1
        return summary

    is_teen_lane = lane == "teen"
    for _sign_index, (equipped_trait, equipped_tid) in tuple(personality_present_by_sign.items()):
        if int(_sign_index) == int(desired_sign_index):
            continue
        if _trait_tracker_remove_trait(sim_info, trait_tracker, equipped_trait):
            summary["changed"] += 1
            summary["traits_removed"] += 1
            equipped_ids.discard(int(equipped_tid))
        if personality_sign_index == _sign_index:
            personality_sign_index = None

    if personality_sign_index is None and marker_sign_index is not None:
        desired_personality_trait = personality_rising_trait_by_index.get(int(marker_sign_index))
        desired_personality_tid = (
            _trait_guid64(desired_personality_trait) if desired_personality_trait is not None else None
        )
        if desired_personality_tid is not None:
            desired_personality_tid = int(desired_personality_tid)
        if (
            desired_personality_trait is not None
            and desired_personality_tid is not None
            and int(desired_personality_tid) not in equipped_ids
        ):
            promoted = _trait_tracker_add_trait(sim_info, trait_tracker, desired_personality_trait)
            if not promoted:
                # Fallback for slot-friction cases: legacy hidden-marker teens can
                # age into YA with the gameplay-visible lane still carrying Rising.
                # Some runtimes reject adding the personality variant until the
                # older hidden marker is removed first.
                marker_pair = marker_present_by_sign.get(int(marker_sign_index))
                marker_trait = marker_pair[0] if marker_pair is not None else None
                marker_tid = marker_pair[1] if marker_pair is not None else None
                marker_removed_for_swap = False

                if marker_trait is not None and marker_tid is not None:
                    if _trait_tracker_remove_trait(sim_info, trait_tracker, marker_trait):
                        summary["changed"] += 1
                        summary["traits_removed"] += 1
                        if is_teen_lane:
                            summary["rising_marker_removed_teen"] += 1
                        else:
                            summary["rising_marker_removed_adult"] += 1
                        equipped_ids.discard(int(marker_tid))
                        marker_removed_for_swap = True

                promoted = _trait_tracker_add_trait(sim_info, trait_tracker, desired_personality_trait)
                if (not promoted) and marker_removed_for_swap and marker_trait is not None and marker_tid is not None:
                    # Roll back marker removal if promotion still cannot happen.
                    if _trait_tracker_add_trait(sim_info, trait_tracker, marker_trait):
                        summary["changed"] += 1
                        summary["traits_added"] += 1
                        equipped_ids.add(int(marker_tid))

            if promoted:
                summary["changed"] += 1
                summary["traits_added"] += 1
                summary["rising_promoted_to_personality"] += 1
                equipped_ids.add(int(desired_personality_tid))
                personality_sign_index = int(marker_sign_index)
                _apply_visible_rising_timed_buff_for_sign_index(
                    sim_info,
                    int(marker_sign_index),
                    cache=_marker_cache(),
                )
            else:
                # Most often this means the sim has no free PERSONALITY slot.
                if is_teen_lane:
                    summary["rising_promotion_deferred_teen"] += 1
                else:
                    summary["rising_promotion_deferred_adult"] += 1

    return summary


def sync_zone_natal_snapshots(
    *,
    transit_service: Optional[CosmicTransitService] = None,
    refresh_marker_cache: bool = False,
    legacy_seed_uncaptured: bool = False,
    seed_uncaptured_teen_plus: bool = False,
    sim_infos: Optional[Iterable[object]] = None,
) -> Dict[str, int]:
    """Capture one-time natal snapshots for teen+ instanced sims."""
    if refresh_marker_cache:
        reset_natal_marker_cache()
    cache = _marker_cache()
    available_by_body_house = cache.get("available_by_body_house", {})
    candidate_ids_by_body = cache.get("candidate_ids_by_body", {})
    planet_house_candidate_ids = cache.get("planet_house_candidate_ids", set())
    sun_sign_trait_by_index = cache.get("sun_sign_trait_by_index", {})
    moon_sign_trait_by_index = cache.get("moon_sign_trait_by_index", {})
    sign_candidate_ids_by_body = cache.get("sign_candidate_ids_by_body", {})
    visible_sun_reward_trait_by_index = cache.get("visible_sun_reward_trait_by_index", {})
    visible_moon_reward_trait_by_index = cache.get("visible_moon_reward_trait_by_index", {})
    visible_sign_reward_candidate_ids_by_body = cache.get("visible_sign_reward_candidate_ids_by_body", {})
    hidden_chart_ruler_body_by_trait_id = cache.get("hidden_chart_ruler_body_by_trait_id", {})
    visible_chart_ruler_reward_trait_by_body = cache.get("visible_chart_ruler_reward_trait_by_body", {})
    visible_chart_ruler_reward_body_by_trait_id = cache.get("visible_chart_ruler_reward_body_by_trait_id", {})
    personality_rising_trait_by_index = cache.get("personality_rising_trait_by_index", {})
    rising_marker_trait_by_index = cache.get("rising_marker_trait_by_index", {})
    rising_personality_sign_index_by_trait_id = cache.get("rising_personality_sign_index_by_trait_id", {})
    rising_marker_sign_index_by_trait_id = cache.get("rising_marker_sign_index_by_trait_id", {})
    capture_flag_trait = cache.get("capture_flag_trait")
    capture_flag_trait_id = cache.get("capture_flag_trait_id")
    legacy_flag_trait = cache.get("legacy_flag_trait")
    legacy_flag_trait_id = cache.get("legacy_flag_trait_id")

    summary = {
        "sims_seen": 0,
        "teen_plus_seen": 0,
        "eligible_without_capture": 0,
        "sims_captured": 0,
        "sims_signs_backfilled": 0,
        "sims_legacy_seeded": 0,
        "traits_added": 0,
        "traits_removed": 0,
        "available_marker_defs": len(available_by_body_house) if isinstance(available_by_body_house, dict) else 0,
        "available_sun_sign_defs": len(sun_sign_trait_by_index) if isinstance(sun_sign_trait_by_index, dict) else 0,
        "available_moon_sign_defs": len(moon_sign_trait_by_index) if isinstance(moon_sign_trait_by_index, dict) else 0,
        "available_visible_sun_reward_defs": len(visible_sun_reward_trait_by_index) if isinstance(visible_sun_reward_trait_by_index, dict) else 0,
        "available_visible_moon_reward_defs": len(visible_moon_reward_trait_by_index) if isinstance(visible_moon_reward_trait_by_index, dict) else 0,
        "available_visible_chart_ruler_reward_defs": len(visible_chart_ruler_reward_trait_by_body) if isinstance(visible_chart_ruler_reward_trait_by_body, dict) else 0,
        "available_personality_rising_defs": len(personality_rising_trait_by_index) if isinstance(personality_rising_trait_by_index, dict) else 0,
        "available_rising_marker_defs": len(rising_marker_trait_by_index) if isinstance(rising_marker_trait_by_index, dict) else 0,
        "chart_ruler_visible_traits_added": 0,
        "chart_ruler_visible_traits_removed": 0,
        "rising_marker_added_preteen": 0,
        "rising_marker_removed_preteen": 0,
        "rising_promoted_to_personality": 0,
        "rising_promotion_skipped_teen_lane": 0,
        "rising_promotion_deferred_teen": 0,
        "rising_promotion_deferred_adult": 0,
        "rising_marker_removed_teen": 0,
        "rising_marker_removed_adult": 0,
        "rising_lane_preteen_seen": 0,
        "rising_lane_teen_seen": 0,
        "rising_lane_adult_seen": 0,
        "rising_lane_unknown_seen": 0,
        "has_capture_flag_def": 1 if capture_flag_trait is not None and capture_flag_trait_id is not None else 0,
        "has_legacy_flag_def": 1 if legacy_flag_trait is not None and legacy_flag_trait_id is not None else 0,
        "legacy_seed_mode": 1 if bool(legacy_seed_uncaptured) else 0,
        "seed_uncaptured_teen_plus": 1 if bool(seed_uncaptured_teen_plus) else 0,
        "active_household_id": None,
        "active_household_uncaptured_teen_plus_with_house_map": 0,
        "auto_legacy_seed_active_household_multi_uncaptured": 0,
        "auto_legacy_seeded_uncaptured": 0,
    }

    if not isinstance(available_by_body_house, dict) or len(available_by_body_house) < len(BODY_NAMES):
        return summary
    if not isinstance(sun_sign_trait_by_index, dict) or len(sun_sign_trait_by_index) < 12:
        return summary
    if not isinstance(moon_sign_trait_by_index, dict) or len(moon_sign_trait_by_index) < 12:
        return summary
    if capture_flag_trait is None or capture_flag_trait_id is None:
        return summary

    manage_visible_sign_rewards = (
        isinstance(visible_sun_reward_trait_by_index, dict)
        and isinstance(visible_moon_reward_trait_by_index, dict)
        and len(visible_sun_reward_trait_by_index) >= 12
        and len(visible_moon_reward_trait_by_index) >= 12
    )

    service = transit_service or get_global_transit_service()
    instanced_sims = _target_instanced_sim_infos(sim_infos)
    probe_sims = tuple(_iter_instanced_sim_infos())
    active_household_id = _get_active_household_id()
    if active_household_id is not None:
        summary["active_household_id"] = int(active_household_id)

    auto_legacy_seed_active_household_multi_uncaptured = False
    if not legacy_seed_uncaptured and active_household_id is not None:
        active_uncaptured_teen_plus_with_house_map = 0
        target_household_id = int(active_household_id)
        for probe_sim_info in probe_sims:
            if _sim_info_household_id(probe_sim_info) != target_household_id:
                continue
            if _rising_age_lane_for_sim_info(probe_sim_info) not in ("teen", "adult_plus"):
                continue
            if getattr(probe_sim_info, "trait_tracker", None) is None:
                continue
            probe_trait_ids, probe_marker_ids = _collect_trait_ids_and_markers(probe_sim_info)
            if int(capture_flag_trait_id) in {int(tid) for tid in probe_trait_ids}:
                continue
            probe_house_sign_map = _build_house_sign_map_for_sim(probe_trait_ids, probe_marker_ids)
            if probe_house_sign_map is None or len(probe_house_sign_map) < 12:
                continue
            active_uncaptured_teen_plus_with_house_map += 1

        summary["active_household_uncaptured_teen_plus_with_house_map"] = int(
            active_uncaptured_teen_plus_with_house_map
        )
        if active_uncaptured_teen_plus_with_house_map >= 2:
            auto_legacy_seed_active_household_multi_uncaptured = True
            summary["auto_legacy_seed_active_household_multi_uncaptured"] = 1

    for sim_info in instanced_sims:
        summary["sims_seen"] += 1

        trait_tracker = getattr(sim_info, "trait_tracker", None)
        if trait_tracker is None:
            continue

        trait_ids, marker_trait_ids = _collect_trait_ids_and_markers(sim_info)
        equipped = _equipped_traits_with_ids(sim_info)
        equipped_ids = {tid for _, tid in equipped}
        rising_age_lane = _rising_age_lane_for_sim_info(sim_info)
        is_teen_plus = rising_age_lane in ("teen", "adult_plus")

        rising_guard_summary = _reconcile_rising_marker_guard(
            sim_info=sim_info,
            trait_tracker=trait_tracker,
            is_teen_plus=is_teen_plus,
            rising_age_lane=rising_age_lane,
            equipped_traits_with_ids=equipped,
            equipped_ids=equipped_ids,
            personality_rising_trait_by_index=(
                personality_rising_trait_by_index if isinstance(personality_rising_trait_by_index, dict) else {}
            ),
            rising_marker_trait_by_index=(
                rising_marker_trait_by_index if isinstance(rising_marker_trait_by_index, dict) else {}
            ),
            rising_personality_sign_index_by_trait_id=(
                rising_personality_sign_index_by_trait_id
                if isinstance(rising_personality_sign_index_by_trait_id, dict)
                else {}
            ),
            rising_marker_sign_index_by_trait_id=(
                rising_marker_sign_index_by_trait_id
                if isinstance(rising_marker_sign_index_by_trait_id, dict)
                else {}
            ),
        )
        for key in (
            "rising_marker_added_preteen",
            "rising_marker_removed_preteen",
            "rising_promoted_to_personality",
            "rising_promotion_skipped_teen_lane",
            "rising_promotion_deferred_teen",
            "rising_promotion_deferred_adult",
            "rising_marker_removed_teen",
            "rising_marker_removed_adult",
            "rising_lane_preteen_seen",
            "rising_lane_teen_seen",
            "rising_lane_adult_seen",
            "rising_lane_unknown_seen",
        ):
            summary[key] += int(rising_guard_summary.get(key, 0) or 0)
        summary["traits_added"] += int(rising_guard_summary.get("traits_added", 0) or 0)
        summary["traits_removed"] += int(rising_guard_summary.get("traits_removed", 0) or 0)
        if int(rising_guard_summary.get("changed", 0) or 0):
            trait_ids, marker_trait_ids = _collect_trait_ids_and_markers(sim_info)
            equipped = _equipped_traits_with_ids(sim_info)
            equipped_ids = {tid for _, tid in equipped}

        chart_ruler_summary = _reconcile_visible_chart_ruler_rewards(
            sim_info=sim_info,
            trait_tracker=trait_tracker,
            equipped_traits_with_ids=equipped,
            equipped_ids=equipped_ids,
            hidden_chart_ruler_body_by_trait_id=(
                hidden_chart_ruler_body_by_trait_id if isinstance(hidden_chart_ruler_body_by_trait_id, dict) else {}
            ),
            visible_chart_ruler_reward_trait_by_body=(
                visible_chart_ruler_reward_trait_by_body
                if isinstance(visible_chart_ruler_reward_trait_by_body, dict)
                else {}
            ),
            visible_chart_ruler_reward_body_by_trait_id=(
                visible_chart_ruler_reward_body_by_trait_id
                if isinstance(visible_chart_ruler_reward_body_by_trait_id, dict)
                else {}
            ),
        )
        summary["traits_added"] += int(chart_ruler_summary.get("traits_added", 0) or 0)
        summary["traits_removed"] += int(chart_ruler_summary.get("traits_removed", 0) or 0)
        summary["chart_ruler_visible_traits_added"] += int(
            chart_ruler_summary.get("chart_ruler_visible_traits_added", 0) or 0
        )
        summary["chart_ruler_visible_traits_removed"] += int(
            chart_ruler_summary.get("chart_ruler_visible_traits_removed", 0) or 0
        )

        if not is_teen_plus:
            continue
        summary["teen_plus_seen"] += 1

        trait_id_set = {int(tid) for tid in trait_ids}
        already_captured = int(capture_flag_trait_id) in trait_id_set
        already_legacy = (
            legacy_flag_trait_id is not None and int(legacy_flag_trait_id) in trait_id_set
        )

        sign_ids_sun = sign_candidate_ids_by_body.get("Sun", set())
        sign_ids_moon = sign_candidate_ids_by_body.get("Moon", set())
        has_natal_sun_sign = any(eid in sign_ids_sun for eid in equipped_ids)
        has_natal_moon_sign = any(eid in sign_ids_moon for eid in equipped_ids)
        visible_reward_ids_sun = visible_sign_reward_candidate_ids_by_body.get("Sun", set())
        visible_reward_ids_moon = visible_sign_reward_candidate_ids_by_body.get("Moon", set())
        has_visible_sun_reward = any(eid in visible_reward_ids_sun for eid in equipped_ids)
        has_visible_moon_reward = any(eid in visible_reward_ids_moon for eid in equipped_ids)
        have_visible_rewards_if_managed = (
            (not manage_visible_sign_rewards)
            or (has_visible_sun_reward and has_visible_moon_reward)
        )
        house_sign_map = _build_house_sign_map_for_sim(trait_ids, marker_trait_ids)
        if house_sign_map is None or len(house_sign_map) < 12:
            continue
        existing_visible_sign_indexes = _visible_sign_indexes_from_equipped_traits(equipped)
        existing_natal_body_sign_indexes = _body_sign_indexes_from_existing_natal_markers(
            equipped_traits_with_ids=equipped,
            house_sign_map=house_sign_map,
        )
        if already_captured and has_natal_sun_sign and has_natal_moon_sign and have_visible_rewards_if_managed:
            _store_chart_record_for_sim(
                sim_info=sim_info,
                transit_service=service,
                house_sign_map=house_sign_map,
                body_sign_index_by_name=(
                    existing_natal_body_sign_indexes
                    if len(existing_natal_body_sign_indexes) >= len(BODY_NAMES)
                    else (
                        _legacy_sign_indexes_by_body(sim_info=sim_info, transit_service=service)
                        if already_legacy
                        else dict(service.state.sign_index_by_body)
                    )
                ),
                provenance=(
                    "stored_natal_markers"
                    if len(existing_natal_body_sign_indexes) >= len(BODY_NAMES)
                    else ("legacy_random" if already_legacy else "clock_snapshot")
                ),
            )
            summary["sims_captured"] += 1
            if already_legacy:
                summary["sims_legacy_seeded"] += 1
            continue

        changed = False
        desired_by_body: Dict[str, object] = {}
        desired_id_by_body: Dict[str, int] = {}
        use_legacy_seed_for_uncaptured = bool(legacy_seed_uncaptured)
        chart_body_sign_index_by_name: Dict[str, int] = dict(service.state.sign_index_by_body)
        chart_provenance = "clock_snapshot"

        if not already_captured:
            summary["eligible_without_capture"] += 1
            if not seed_uncaptured_teen_plus:
                continue
            sim_household_id = _sim_info_household_id(sim_info)
            if (
                not use_legacy_seed_for_uncaptured
                and auto_legacy_seed_active_household_multi_uncaptured
                and active_household_id is not None
                and sim_household_id is not None
                and int(sim_household_id) == int(active_household_id)
            ):
                use_legacy_seed_for_uncaptured = True

            if len(existing_visible_sign_indexes) >= 2:
                chart_body_sign_index_by_name.update(existing_visible_sign_indexes)
                desired_by_body = _desired_natal_traits_for_body_sign_indexes(
                    house_sign_map=house_sign_map,
                    available_by_body_house=available_by_body_house,
                    body_sign_index_by_name=chart_body_sign_index_by_name,
                )
                desired_sign_traits = _desired_natal_sign_traits_from_sign_indexes(
                    sign_index_by_body=existing_visible_sign_indexes,
                    sun_sign_trait_by_index=sun_sign_trait_by_index,
                    moon_sign_trait_by_index=moon_sign_trait_by_index,
                )
                chart_provenance = "existing_visible_signs"
            elif use_legacy_seed_for_uncaptured:
                chart_body_sign_index_by_name = _legacy_sign_indexes_by_body(
                    sim_info=sim_info,
                    transit_service=service,
                )
                desired_by_body, desired_sign_traits = _desired_legacy_natal_traits_for_sim(
                    sim_info=sim_info,
                    transit_service=service,
                    house_sign_map=house_sign_map,
                    available_by_body_house=available_by_body_house,
                    sun_sign_trait_by_index=sun_sign_trait_by_index,
                    moon_sign_trait_by_index=moon_sign_trait_by_index,
                )
                chart_provenance = "legacy_random"
            else:
                desired_by_body = _desired_natal_traits_for_sim(service, house_sign_map, available_by_body_house)
                desired_sign_traits = _desired_natal_sign_traits_from_current_sky(
                    service,
                    sun_sign_trait_by_index=sun_sign_trait_by_index,
                    moon_sign_trait_by_index=moon_sign_trait_by_index,
                )
                chart_provenance = "clock_snapshot"
            if use_legacy_seed_for_uncaptured and not legacy_seed_uncaptured and chart_provenance == "legacy_random":
                summary["auto_legacy_seeded_uncaptured"] += 1
            if len(desired_by_body) < len(BODY_NAMES):
                continue
            for body, trait in desired_by_body.items():
                tid = _trait_guid64(trait)
                if tid is not None:
                    desired_id_by_body[body] = int(tid)
            if len(desired_id_by_body) < len(BODY_NAMES):
                continue

            # Clean any partial natal planet-house markers if present before capture.
            for equipped_trait, equipped_tid in equipped:
                if equipped_tid not in planet_house_candidate_ids:
                    continue
                desired_match = False
                for body, candidate_ids in candidate_ids_by_body.items():
                    if equipped_tid not in candidate_ids:
                        continue
                    if desired_id_by_body.get(body) == equipped_tid:
                        desired_match = True
                    break
                if desired_match:
                    continue
                if _trait_tracker_remove_trait(sim_info, trait_tracker, equipped_trait):
                    summary["traits_removed"] += 1
                    changed = True
                    equipped_ids.discard(equipped_tid)

            # Add natal planet-house markers.
            for body, desired_trait in desired_by_body.items():
                desired_tid = desired_id_by_body.get(body)
                if desired_tid is None or desired_tid in equipped_ids:
                    continue
                if _trait_tracker_add_trait(sim_info, trait_tracker, desired_trait):
                    summary["traits_added"] += 1
                    changed = True
                    equipped_ids.add(desired_tid)

        # Natal Sun/Moon sign markers:
        # - new capture: use current sky (current Sun/Moon signs)
        # - already captured but missing signs: backfill from existing natal planet-house markers
        if already_captured:
            desired_sign_traits = _desired_natal_sign_traits_from_existing_natal_markers(
                equipped_traits_with_ids=equipped,
                house_sign_map=house_sign_map,
                sun_sign_trait_by_index=sun_sign_trait_by_index,
                moon_sign_trait_by_index=moon_sign_trait_by_index,
            )
        if len(desired_sign_traits) < 2:
            continue

        desired_sign_ids: Dict[str, int] = {}
        for body, trait in desired_sign_traits.items():
            tid = _trait_guid64(trait)
            if tid is not None:
                desired_sign_ids[body] = int(tid)
        if len(desired_sign_ids) < 2:
            continue

        # Clean partial/incorrect natal Sun/Moon sign markers.
        for equipped_trait, equipped_tid in equipped:
            sign_body = None
            if equipped_tid in sign_ids_sun:
                sign_body = "Sun"
            elif equipped_tid in sign_ids_moon:
                sign_body = "Moon"
            if sign_body is None:
                continue
            if desired_sign_ids.get(sign_body) == equipped_tid:
                continue
            if _trait_tracker_remove_trait(sim_info, trait_tracker, equipped_trait):
                summary["traits_removed"] += 1
                changed = True
                equipped_ids.discard(equipped_tid)

        # Add natal Sun/Moon sign markers.
        for body in ("Sun", "Moon"):
            desired_trait = desired_sign_traits.get(body)
            desired_tid = desired_sign_ids.get(body)
            if desired_trait is None or desired_tid is None or desired_tid in equipped_ids:
                continue
            if _trait_tracker_add_trait(sim_info, trait_tracker, desired_trait):
                summary["traits_added"] += 1
                changed = True
                equipped_ids.add(desired_tid)

        if manage_visible_sign_rewards:
            desired_visible_sign_traits = _desired_visible_sign_reward_traits_from_natal_sign_traits(
                desired_sign_traits,
                visible_sun_reward_trait_by_index=visible_sun_reward_trait_by_index,
                visible_moon_reward_trait_by_index=visible_moon_reward_trait_by_index,
            )
            desired_visible_sign_ids: Dict[str, int] = {}
            for body, trait in desired_visible_sign_traits.items():
                tid = _trait_guid64(trait)
                if tid is not None:
                    desired_visible_sign_ids[body] = int(tid)

            if len(desired_visible_sign_ids) >= 2:
                for equipped_trait, equipped_tid in equipped:
                    visible_body = None
                    if equipped_tid in visible_reward_ids_sun:
                        visible_body = "Sun"
                    elif equipped_tid in visible_reward_ids_moon:
                        visible_body = "Moon"
                    if visible_body is None:
                        continue
                    if desired_visible_sign_ids.get(visible_body) == equipped_tid:
                        continue
                    if _trait_tracker_remove_trait(sim_info, trait_tracker, equipped_trait):
                        summary["traits_removed"] += 1
                        changed = True
                        equipped_ids.discard(equipped_tid)

                for body in ("Sun", "Moon"):
                    desired_trait = desired_visible_sign_traits.get(body)
                    desired_tid = desired_visible_sign_ids.get(body)
                    if desired_trait is None or desired_tid is None or desired_tid in equipped_ids:
                        continue
                    if _trait_tracker_add_trait(sim_info, trait_tracker, desired_trait):
                        summary["traits_added"] += 1
                        changed = True
                        equipped_ids.add(desired_tid)
                        _apply_visible_sign_timed_buff_for_trait_add(
                            sim_info,
                            desired_trait,
                            cache=cache,
                        )

        if already_captured and changed:
            summary["sims_signs_backfilled"] += 1

        # Add capture flag only after all natal markers/signs are in place.
        have_all_house_natal = all(desired_tid in equipped_ids for desired_tid in desired_id_by_body.values()) if desired_id_by_body else True
        have_sign_natal = all(desired_tid in equipped_ids for desired_tid in desired_sign_ids.values())
        if (
            not already_captured
            and have_all_house_natal
            and have_sign_natal
            and int(capture_flag_trait_id) not in equipped_ids
        ):
            if _trait_tracker_add_trait(sim_info, trait_tracker, capture_flag_trait):
                summary["traits_added"] += 1
                changed = True
                equipped_ids.add(int(capture_flag_trait_id))
                already_captured = True

        if (
            legacy_seed_uncaptured
            and not already_legacy
            and legacy_flag_trait is not None
            and legacy_flag_trait_id is not None
            and int(capture_flag_trait_id) in equipped_ids
            and int(legacy_flag_trait_id) not in equipped_ids
        ):
            if _trait_tracker_add_trait(sim_info, trait_tracker, legacy_flag_trait):
                summary["traits_added"] += 1
                changed = True
                equipped_ids.add(int(legacy_flag_trait_id))
                already_legacy = True

        if int(capture_flag_trait_id) in equipped_ids:
            summary["sims_captured"] += 1
            _store_chart_record_for_sim(
                sim_info=sim_info,
                transit_service=service,
                house_sign_map=house_sign_map,
                body_sign_index_by_name=(
                    existing_natal_body_sign_indexes
                    if len(existing_natal_body_sign_indexes) >= len(BODY_NAMES)
                    else chart_body_sign_index_by_name
                ),
                provenance=(
                    "stored_natal_markers"
                    if len(existing_natal_body_sign_indexes) >= len(BODY_NAMES)
                    else chart_provenance
                ),
            )
        if legacy_flag_trait_id is not None and int(legacy_flag_trait_id) in equipped_ids:
            summary["sims_legacy_seeded"] += 1

    return summary


def seed_active_household_preteen_natal_snapshots(
    *,
    active_household_id: Optional[int],
    refresh_marker_cache: bool = False,
    sign_seed_mode: str = "current_sky",
    transit_service: Optional[CosmicTransitService] = None,
) -> Dict[str, object]:
    """Seed natal markers/signs for uncaptured pre-teen sims in the active household.

    Intended as a migration helper to mimic a "birth-time" capture for existing
    infant/toddler/child sims in a currently played household.
    """
    if refresh_marker_cache:
        reset_natal_marker_cache()
    cache = _marker_cache()

    available_by_body_house = cache.get("available_by_body_house", {})
    candidate_ids_by_body = cache.get("candidate_ids_by_body", {})
    planet_house_candidate_ids = cache.get("planet_house_candidate_ids", set())
    sun_sign_trait_by_index = cache.get("sun_sign_trait_by_index", {})
    moon_sign_trait_by_index = cache.get("moon_sign_trait_by_index", {})
    sign_candidate_ids_by_body = cache.get("sign_candidate_ids_by_body", {})
    visible_sun_reward_trait_by_index = cache.get("visible_sun_reward_trait_by_index", {})
    visible_moon_reward_trait_by_index = cache.get("visible_moon_reward_trait_by_index", {})
    visible_sign_reward_candidate_ids_by_body = cache.get("visible_sign_reward_candidate_ids_by_body", {})
    hidden_chart_ruler_body_by_trait_id = cache.get("hidden_chart_ruler_body_by_trait_id", {})
    visible_chart_ruler_reward_trait_by_body = cache.get("visible_chart_ruler_reward_trait_by_body", {})
    visible_chart_ruler_reward_body_by_trait_id = cache.get("visible_chart_ruler_reward_body_by_trait_id", {})
    personality_rising_trait_by_index = cache.get("personality_rising_trait_by_index", {})
    rising_marker_trait_by_index = cache.get("rising_marker_trait_by_index", {})
    rising_personality_sign_index_by_trait_id = cache.get("rising_personality_sign_index_by_trait_id", {})
    rising_marker_sign_index_by_trait_id = cache.get("rising_marker_sign_index_by_trait_id", {})
    capture_flag_trait = cache.get("capture_flag_trait")
    capture_flag_trait_id = cache.get("capture_flag_trait_id")

    summary: Dict[str, object] = {
        "active_household_id": int(active_household_id) if active_household_id is not None else None,
        "has_active_household_id": 1 if active_household_id is not None else 0,
        "sign_seed_mode": str(sign_seed_mode or "current_sky"),
        "sims_seen": 0,
        "household_sims_seen": 0,
        "preteen_seen": 0,
        "eligible_without_capture": 0,
        "sims_seeded": 0,
        "sims_changed": 0,
        "skipped_no_trait_tracker": 0,
        "skipped_already_captured": 0,
        "skipped_existing_chart_state": 0,
        "skipped_missing_house_map": 0,
        "traits_added": 0,
        "traits_removed": 0,
        "available_marker_defs": len(available_by_body_house) if isinstance(available_by_body_house, dict) else 0,
        "available_sun_sign_defs": len(sun_sign_trait_by_index) if isinstance(sun_sign_trait_by_index, dict) else 0,
        "available_moon_sign_defs": len(moon_sign_trait_by_index) if isinstance(moon_sign_trait_by_index, dict) else 0,
        "available_visible_sun_reward_defs": len(visible_sun_reward_trait_by_index) if isinstance(visible_sun_reward_trait_by_index, dict) else 0,
        "available_visible_moon_reward_defs": len(visible_moon_reward_trait_by_index) if isinstance(visible_moon_reward_trait_by_index, dict) else 0,
        "available_visible_chart_ruler_reward_defs": len(visible_chart_ruler_reward_trait_by_body) if isinstance(visible_chart_ruler_reward_trait_by_body, dict) else 0,
        "available_personality_rising_defs": len(personality_rising_trait_by_index) if isinstance(personality_rising_trait_by_index, dict) else 0,
        "available_rising_marker_defs": len(rising_marker_trait_by_index) if isinstance(rising_marker_trait_by_index, dict) else 0,
        "chart_ruler_visible_traits_added": 0,
        "chart_ruler_visible_traits_removed": 0,
        "rising_lane_preteen_seen": 0,
        "rising_lane_teen_seen": 0,
        "rising_lane_adult_seen": 0,
        "rising_lane_unknown_seen": 0,
        "has_capture_flag_def": 1 if capture_flag_trait is not None and capture_flag_trait_id is not None else 0,
    }

    if active_household_id is None:
        return summary
    if not isinstance(available_by_body_house, dict) or len(available_by_body_house) < len(BODY_NAMES):
        return summary
    if not isinstance(sun_sign_trait_by_index, dict) or len(sun_sign_trait_by_index) < 12:
        return summary
    if not isinstance(moon_sign_trait_by_index, dict) or len(moon_sign_trait_by_index) < 12:
        return summary
    if capture_flag_trait is None or capture_flag_trait_id is None:
        return summary

    manage_visible_sign_rewards = (
        isinstance(visible_sun_reward_trait_by_index, dict)
        and isinstance(visible_moon_reward_trait_by_index, dict)
        and len(visible_sun_reward_trait_by_index) >= 12
        and len(visible_moon_reward_trait_by_index) >= 12
    )

    service = transit_service or get_global_transit_service()
    target_household_id = int(active_household_id)

    for sim_info in _iter_household_sim_infos_by_id(active_household_id):
        summary["sims_seen"] += 1

        summary["household_sims_seen"] += 1

        if _is_teen_or_older(sim_info):
            continue
        summary["preteen_seen"] += 1

        trait_tracker = getattr(sim_info, "trait_tracker", None)
        if trait_tracker is None:
            summary["skipped_no_trait_tracker"] += 1
            continue

        trait_ids, marker_trait_ids = _collect_trait_ids_and_markers(sim_info)
        equipped = _equipped_traits_with_ids(sim_info)
        equipped_ids = {tid for _, tid in equipped}

        rising_age_lane = _rising_age_lane_for_sim_info(sim_info)
        rising_guard_summary = _reconcile_rising_marker_guard(
            sim_info=sim_info,
            trait_tracker=trait_tracker,
            is_teen_plus=False,
            rising_age_lane=rising_age_lane,
            equipped_traits_with_ids=equipped,
            equipped_ids=equipped_ids,
            personality_rising_trait_by_index=(
                personality_rising_trait_by_index if isinstance(personality_rising_trait_by_index, dict) else {}
            ),
            rising_marker_trait_by_index=(
                rising_marker_trait_by_index if isinstance(rising_marker_trait_by_index, dict) else {}
            ),
            rising_personality_sign_index_by_trait_id=(
                rising_personality_sign_index_by_trait_id
                if isinstance(rising_personality_sign_index_by_trait_id, dict)
                else {}
            ),
            rising_marker_sign_index_by_trait_id=(
                rising_marker_sign_index_by_trait_id
                if isinstance(rising_marker_sign_index_by_trait_id, dict)
                else {}
            ),
        )
        for key in (
            "rising_lane_preteen_seen",
            "rising_lane_teen_seen",
            "rising_lane_adult_seen",
            "rising_lane_unknown_seen",
        ):
            summary[key] = int(summary.get(key, 0) or 0) + int(rising_guard_summary.get(key, 0) or 0)
        summary["traits_added"] += int(rising_guard_summary.get("traits_added", 0) or 0)
        summary["traits_removed"] += int(rising_guard_summary.get("traits_removed", 0) or 0)
        if int(rising_guard_summary.get("changed", 0) or 0):
            trait_ids, marker_trait_ids = _collect_trait_ids_and_markers(sim_info)
            equipped = _equipped_traits_with_ids(sim_info)
            equipped_ids = {tid for _, tid in equipped}

        chart_ruler_summary = _reconcile_visible_chart_ruler_rewards(
            sim_info=sim_info,
            trait_tracker=trait_tracker,
            equipped_traits_with_ids=equipped,
            equipped_ids=equipped_ids,
            hidden_chart_ruler_body_by_trait_id=(
                hidden_chart_ruler_body_by_trait_id if isinstance(hidden_chart_ruler_body_by_trait_id, dict) else {}
            ),
            visible_chart_ruler_reward_trait_by_body=(
                visible_chart_ruler_reward_trait_by_body
                if isinstance(visible_chart_ruler_reward_trait_by_body, dict)
                else {}
            ),
            visible_chart_ruler_reward_body_by_trait_id=(
                visible_chart_ruler_reward_body_by_trait_id
                if isinstance(visible_chart_ruler_reward_body_by_trait_id, dict)
                else {}
            ),
        )
        summary["traits_added"] += int(chart_ruler_summary.get("traits_added", 0) or 0)
        summary["traits_removed"] += int(chart_ruler_summary.get("traits_removed", 0) or 0)
        summary["chart_ruler_visible_traits_added"] += int(
            chart_ruler_summary.get("chart_ruler_visible_traits_added", 0) or 0
        )
        summary["chart_ruler_visible_traits_removed"] += int(
            chart_ruler_summary.get("chart_ruler_visible_traits_removed", 0) or 0
        )

        trait_id_set = {int(tid) for tid in trait_ids}
        existing_sun_moon_sign_state_complete = _has_complete_equipped_sun_moon_sign_state(
            equipped_ids=equipped_ids,
            sign_candidate_ids_by_body=(
                sign_candidate_ids_by_body if isinstance(sign_candidate_ids_by_body, dict) else {}
            ),
            visible_sign_reward_candidate_ids_by_body=(
                visible_sign_reward_candidate_ids_by_body
                if isinstance(visible_sign_reward_candidate_ids_by_body, dict)
                else {}
            ),
            require_visible_rewards=bool(manage_visible_sign_rewards),
        )
        already_captured = int(capture_flag_trait_id) in trait_id_set and existing_sun_moon_sign_state_complete
        if int(capture_flag_trait_id) not in trait_id_set:
            summary["eligible_without_capture"] += 1

        house_sign_map = _build_house_sign_map_for_sim(trait_ids, marker_trait_ids)
        if house_sign_map is None or len(house_sign_map) < 12:
            rising_sign_index = None
            for tid in trait_id_set:
                idx = None
                if isinstance(rising_personality_sign_index_by_trait_id, dict):
                    idx = rising_personality_sign_index_by_trait_id.get(int(tid))
                if idx is None and isinstance(rising_marker_sign_index_by_trait_id, dict):
                    idx = rising_marker_sign_index_by_trait_id.get(int(tid))
                if isinstance(idx, int):
                    rising_sign_index = int(idx) % 12
                    break
            if rising_sign_index is not None:
                house_sign_map = build_house_sign_map_for_rising(int(rising_sign_index))
        if house_sign_map is None or len(house_sign_map) < 12:
            summary["skipped_missing_house_map"] += 1
            continue

        changed = False
        resolved_sign_seed_mode = str(sign_seed_mode or "current_sky").strip().lower()
        if resolved_sign_seed_mode == "random_sun_moon":
            chart_body_sign_index_by_name = dict(service.state.sign_index_by_body)
            randomized_sign_indexes = _legacy_sign_indexes_by_body(
                sim_info=sim_info,
                transit_service=service,
            )
            for body in ("Sun", "Moon"):
                randomized_index = randomized_sign_indexes.get(body)
                if isinstance(randomized_index, int):
                    chart_body_sign_index_by_name[body] = int(randomized_index) % 12
            desired_by_body = _desired_natal_traits_for_body_sign_indexes(
                house_sign_map=house_sign_map,
                available_by_body_house=available_by_body_house,
                body_sign_index_by_name=chart_body_sign_index_by_name,
            )
            desired_sign_traits = _desired_natal_sign_traits_from_sign_indexes(
                sign_index_by_body=chart_body_sign_index_by_name,
                sun_sign_trait_by_index=sun_sign_trait_by_index,
                moon_sign_trait_by_index=moon_sign_trait_by_index,
            )
        else:
            desired_by_body = _desired_natal_traits_for_sim(service, house_sign_map, available_by_body_house)
            desired_sign_traits = _desired_natal_sign_traits_from_current_sky(
                service,
                sun_sign_trait_by_index=sun_sign_trait_by_index,
                moon_sign_trait_by_index=moon_sign_trait_by_index,
            )
        if len(desired_by_body) < len(BODY_NAMES) or len(desired_sign_traits) < 2:
            continue

        desired_id_by_body: Dict[str, int] = {}
        for body, trait in desired_by_body.items():
            tid = _trait_guid64(trait)
            if tid is not None:
                desired_id_by_body[body] = int(tid)
        if len(desired_id_by_body) < len(BODY_NAMES):
            continue

        desired_sign_ids: Dict[str, int] = {}
        for body, trait in desired_sign_traits.items():
            tid = _trait_guid64(trait)
            if tid is not None:
                desired_sign_ids[body] = int(tid)
        if len(desired_sign_ids) < 2:
            continue

        # Clean partial natal planet-house markers if present before capture.
        for equipped_trait, equipped_tid in equipped:
            if equipped_tid not in planet_house_candidate_ids:
                continue
            desired_match = False
            for body, candidate_ids in candidate_ids_by_body.items():
                if equipped_tid not in candidate_ids:
                    continue
                if desired_id_by_body.get(body) == equipped_tid:
                    desired_match = True
                break
            if desired_match:
                continue
            if _trait_tracker_remove_trait(sim_info, trait_tracker, equipped_trait):
                summary["traits_removed"] += 1
                changed = True
                equipped_ids.discard(equipped_tid)

        # Add natal planet-house markers.
        for body, desired_trait in desired_by_body.items():
            desired_tid = desired_id_by_body.get(body)
            if desired_tid is None or desired_tid in equipped_ids:
                continue
            if _trait_tracker_add_trait(sim_info, trait_tracker, desired_trait):
                summary["traits_added"] += 1
                changed = True
                equipped_ids.add(desired_tid)

        sign_ids_sun = sign_candidate_ids_by_body.get("Sun", set())
        sign_ids_moon = sign_candidate_ids_by_body.get("Moon", set())

        # Clean partial/incorrect natal Sun/Moon sign markers.
        for equipped_trait, equipped_tid in equipped:
            sign_body = None
            if equipped_tid in sign_ids_sun:
                sign_body = "Sun"
            elif equipped_tid in sign_ids_moon:
                sign_body = "Moon"
            if sign_body is None:
                continue
            if desired_sign_ids.get(sign_body) == equipped_tid:
                continue
            if _trait_tracker_remove_trait(sim_info, trait_tracker, equipped_trait):
                summary["traits_removed"] += 1
                changed = True
                equipped_ids.discard(equipped_tid)

        # Add natal Sun/Moon sign markers.
        for body in ("Sun", "Moon"):
            desired_trait = desired_sign_traits.get(body)
            desired_tid = desired_sign_ids.get(body)
            if desired_trait is None or desired_tid is None or desired_tid in equipped_ids:
                continue
            if _trait_tracker_add_trait(sim_info, trait_tracker, desired_trait):
                summary["traits_added"] += 1
                changed = True
                equipped_ids.add(desired_tid)

        if manage_visible_sign_rewards:
            visible_reward_ids_sun = visible_sign_reward_candidate_ids_by_body.get("Sun", set())
            visible_reward_ids_moon = visible_sign_reward_candidate_ids_by_body.get("Moon", set())
            desired_visible_sign_traits = _desired_visible_sign_reward_traits_from_natal_sign_traits(
                desired_sign_traits,
                visible_sun_reward_trait_by_index=visible_sun_reward_trait_by_index,
                visible_moon_reward_trait_by_index=visible_moon_reward_trait_by_index,
            )
            desired_visible_sign_ids: Dict[str, int] = {}
            for body, trait in desired_visible_sign_traits.items():
                tid = _trait_guid64(trait)
                if tid is not None:
                    desired_visible_sign_ids[body] = int(tid)

            if len(desired_visible_sign_ids) >= 2:
                for equipped_trait, equipped_tid in equipped:
                    visible_body = None
                    if equipped_tid in visible_reward_ids_sun:
                        visible_body = "Sun"
                    elif equipped_tid in visible_reward_ids_moon:
                        visible_body = "Moon"
                    if visible_body is None:
                        continue
                    if desired_visible_sign_ids.get(visible_body) == equipped_tid:
                        continue
                    if _trait_tracker_remove_trait(sim_info, trait_tracker, equipped_trait):
                        summary["traits_removed"] += 1
                        changed = True
                        equipped_ids.discard(equipped_tid)

                for body in ("Sun", "Moon"):
                    desired_trait = desired_visible_sign_traits.get(body)
                    desired_tid = desired_visible_sign_ids.get(body)
                    if desired_trait is None or desired_tid is None or desired_tid in equipped_ids:
                        continue
                    if _trait_tracker_add_trait(sim_info, trait_tracker, desired_trait):
                        summary["traits_added"] += 1
                        changed = True
                        equipped_ids.add(desired_tid)
                        _apply_visible_sign_timed_buff_for_trait_add(
                            sim_info,
                            desired_trait,
                            cache=cache,
                        )

        have_all_house_natal = all(desired_tid in equipped_ids for desired_tid in desired_id_by_body.values())
        have_sign_natal = all(desired_tid in equipped_ids for desired_tid in desired_sign_ids.values())
        if (
            have_all_house_natal
            and have_sign_natal
            and int(capture_flag_trait_id) not in equipped_ids
        ):
            if _trait_tracker_add_trait(sim_info, trait_tracker, capture_flag_trait):
                summary["traits_added"] += 1
                changed = True
                equipped_ids.add(int(capture_flag_trait_id))
                summary["sims_seeded"] += 1

        if int(capture_flag_trait_id) in equipped_ids:
            _store_chart_record_for_sim(
                sim_info=sim_info,
                transit_service=service,
                house_sign_map=house_sign_map,
                body_sign_index_by_name=dict(service.state.sign_index_by_body),
                provenance="clock_snapshot",
            )

        if changed:
            summary["sims_changed"] += 1

    return summary


def seed_active_household_teen_legacy_natal_snapshots(
    *,
    active_household_id: Optional[int],
    refresh_marker_cache: bool = False,
    transit_service: Optional[CosmicTransitService] = None,
) -> Dict[str, object]:
    """Seed uncaptured teen+ sims in the active household using legacy-style randomness."""
    if refresh_marker_cache:
        reset_natal_marker_cache()
    cache = _marker_cache()

    available_by_body_house = cache.get("available_by_body_house", {})
    candidate_ids_by_body = cache.get("candidate_ids_by_body", {})
    planet_house_candidate_ids = cache.get("planet_house_candidate_ids", set())
    sun_sign_trait_by_index = cache.get("sun_sign_trait_by_index", {})
    moon_sign_trait_by_index = cache.get("moon_sign_trait_by_index", {})
    sign_candidate_ids_by_body = cache.get("sign_candidate_ids_by_body", {})
    visible_sun_reward_trait_by_index = cache.get("visible_sun_reward_trait_by_index", {})
    visible_moon_reward_trait_by_index = cache.get("visible_moon_reward_trait_by_index", {})
    visible_sign_reward_candidate_ids_by_body = cache.get("visible_sign_reward_candidate_ids_by_body", {})
    hidden_chart_ruler_body_by_trait_id = cache.get("hidden_chart_ruler_body_by_trait_id", {})
    visible_chart_ruler_reward_trait_by_body = cache.get("visible_chart_ruler_reward_trait_by_body", {})
    visible_chart_ruler_reward_body_by_trait_id = cache.get("visible_chart_ruler_reward_body_by_trait_id", {})
    personality_rising_trait_by_index = cache.get("personality_rising_trait_by_index", {})
    rising_marker_trait_by_index = cache.get("rising_marker_trait_by_index", {})
    rising_personality_sign_index_by_trait_id = cache.get("rising_personality_sign_index_by_trait_id", {})
    rising_marker_sign_index_by_trait_id = cache.get("rising_marker_sign_index_by_trait_id", {})
    capture_flag_trait = cache.get("capture_flag_trait")
    capture_flag_trait_id = cache.get("capture_flag_trait_id")
    legacy_flag_trait = cache.get("legacy_flag_trait")
    legacy_flag_trait_id = cache.get("legacy_flag_trait_id")

    summary: Dict[str, object] = {
        "active_household_id": int(active_household_id) if active_household_id is not None else None,
        "has_active_household_id": 1 if active_household_id is not None else 0,
        "sims_seen": 0,
        "household_sims_seen": 0,
        "teen_plus_seen": 0,
        "eligible_without_capture": 0,
        "sims_seeded": 0,
        "sims_changed": 0,
        "skipped_no_trait_tracker": 0,
        "skipped_already_captured": 0,
        "skipped_missing_house_map": 0,
        "traits_added": 0,
        "traits_removed": 0,
        "available_marker_defs": len(available_by_body_house) if isinstance(available_by_body_house, dict) else 0,
        "available_sun_sign_defs": len(sun_sign_trait_by_index) if isinstance(sun_sign_trait_by_index, dict) else 0,
        "available_moon_sign_defs": len(moon_sign_trait_by_index) if isinstance(moon_sign_trait_by_index, dict) else 0,
        "available_visible_sun_reward_defs": len(visible_sun_reward_trait_by_index) if isinstance(visible_sun_reward_trait_by_index, dict) else 0,
        "available_visible_moon_reward_defs": len(visible_moon_reward_trait_by_index) if isinstance(visible_moon_reward_trait_by_index, dict) else 0,
        "available_visible_chart_ruler_reward_defs": len(visible_chart_ruler_reward_trait_by_body) if isinstance(visible_chart_ruler_reward_trait_by_body, dict) else 0,
        "available_personality_rising_defs": len(personality_rising_trait_by_index) if isinstance(personality_rising_trait_by_index, dict) else 0,
        "available_rising_marker_defs": len(rising_marker_trait_by_index) if isinstance(rising_marker_trait_by_index, dict) else 0,
        "chart_ruler_visible_traits_added": 0,
        "chart_ruler_visible_traits_removed": 0,
        "rising_promotion_deferred_teen": 0,
        "rising_promotion_deferred_adult": 0,
        "rising_marker_removed_teen": 0,
        "rising_marker_removed_adult": 0,
        "rising_lane_preteen_seen": 0,
        "rising_lane_teen_seen": 0,
        "rising_lane_adult_seen": 0,
        "rising_lane_unknown_seen": 0,
        "has_capture_flag_def": 1 if capture_flag_trait is not None and capture_flag_trait_id is not None else 0,
        "has_legacy_flag_def": 1 if legacy_flag_trait is not None and legacy_flag_trait_id is not None else 0,
        "legacy_seed_mode": 1,
    }

    if active_household_id is None:
        return summary
    if not isinstance(available_by_body_house, dict) or len(available_by_body_house) < len(BODY_NAMES):
        return summary
    if not isinstance(sun_sign_trait_by_index, dict) or len(sun_sign_trait_by_index) < 12:
        return summary
    if not isinstance(moon_sign_trait_by_index, dict) or len(moon_sign_trait_by_index) < 12:
        return summary
    if capture_flag_trait is None or capture_flag_trait_id is None:
        return summary
    if legacy_flag_trait is None or legacy_flag_trait_id is None:
        return summary

    manage_visible_sign_rewards = (
        isinstance(visible_sun_reward_trait_by_index, dict)
        and isinstance(visible_moon_reward_trait_by_index, dict)
        and len(visible_sun_reward_trait_by_index) >= 12
        and len(visible_moon_reward_trait_by_index) >= 12
    )

    service = transit_service or get_global_transit_service()
    target_household_id = int(active_household_id)

    for sim_info in _iter_household_sim_infos_by_id(active_household_id):
        summary["sims_seen"] += 1

        summary["household_sims_seen"] += 1

        if not _is_teen_or_older(sim_info):
            continue
        summary["teen_plus_seen"] += 1

        trait_tracker = getattr(sim_info, "trait_tracker", None)
        if trait_tracker is None:
            summary["skipped_no_trait_tracker"] += 1
            continue

        trait_ids, marker_trait_ids = _collect_trait_ids_and_markers(sim_info)
        equipped = _equipped_traits_with_ids(sim_info)
        equipped_ids = {tid for _, tid in equipped}

        rising_age_lane = _rising_age_lane_for_sim_info(sim_info)
        rising_guard_summary = _reconcile_rising_marker_guard(
            sim_info=sim_info,
            trait_tracker=trait_tracker,
            is_teen_plus=True,
            rising_age_lane=rising_age_lane,
            equipped_traits_with_ids=equipped,
            equipped_ids=equipped_ids,
            personality_rising_trait_by_index=(
                personality_rising_trait_by_index if isinstance(personality_rising_trait_by_index, dict) else {}
            ),
            rising_marker_trait_by_index=(
                rising_marker_trait_by_index if isinstance(rising_marker_trait_by_index, dict) else {}
            ),
            rising_personality_sign_index_by_trait_id=(
                rising_personality_sign_index_by_trait_id
                if isinstance(rising_personality_sign_index_by_trait_id, dict)
                else {}
            ),
            rising_marker_sign_index_by_trait_id=(
                rising_marker_sign_index_by_trait_id
                if isinstance(rising_marker_sign_index_by_trait_id, dict)
                else {}
            ),
        )
        for key in (
            "rising_promotion_deferred_teen",
            "rising_promotion_deferred_adult",
            "rising_marker_removed_teen",
            "rising_marker_removed_adult",
            "rising_lane_preteen_seen",
            "rising_lane_teen_seen",
            "rising_lane_adult_seen",
            "rising_lane_unknown_seen",
        ):
            summary[key] = int(summary.get(key, 0) or 0) + int(rising_guard_summary.get(key, 0) or 0)
        summary["traits_added"] += int(rising_guard_summary.get("traits_added", 0) or 0)
        summary["traits_removed"] += int(rising_guard_summary.get("traits_removed", 0) or 0)
        if int(rising_guard_summary.get("changed", 0) or 0):
            trait_ids, marker_trait_ids = _collect_trait_ids_and_markers(sim_info)
            equipped = _equipped_traits_with_ids(sim_info)
            equipped_ids = {tid for _, tid in equipped}

        chart_ruler_summary = _reconcile_visible_chart_ruler_rewards(
            sim_info=sim_info,
            trait_tracker=trait_tracker,
            equipped_traits_with_ids=equipped,
            equipped_ids=equipped_ids,
            hidden_chart_ruler_body_by_trait_id=(
                hidden_chart_ruler_body_by_trait_id if isinstance(hidden_chart_ruler_body_by_trait_id, dict) else {}
            ),
            visible_chart_ruler_reward_trait_by_body=(
                visible_chart_ruler_reward_trait_by_body
                if isinstance(visible_chart_ruler_reward_trait_by_body, dict)
                else {}
            ),
            visible_chart_ruler_reward_body_by_trait_id=(
                visible_chart_ruler_reward_body_by_trait_id
                if isinstance(visible_chart_ruler_reward_body_by_trait_id, dict)
                else {}
            ),
        )
        summary["traits_added"] += int(chart_ruler_summary.get("traits_added", 0) or 0)
        summary["traits_removed"] += int(chart_ruler_summary.get("traits_removed", 0) or 0)
        summary["chart_ruler_visible_traits_added"] += int(
            chart_ruler_summary.get("chart_ruler_visible_traits_added", 0) or 0
        )
        summary["chart_ruler_visible_traits_removed"] += int(
            chart_ruler_summary.get("chart_ruler_visible_traits_removed", 0) or 0
        )

        trait_id_set = {int(tid) for tid in trait_ids}
        existing_sun_moon_sign_state_complete = _has_complete_equipped_sun_moon_sign_state(
            equipped_ids=equipped_ids,
            sign_candidate_ids_by_body=(
                sign_candidate_ids_by_body if isinstance(sign_candidate_ids_by_body, dict) else {}
            ),
            visible_sign_reward_candidate_ids_by_body=(
                visible_sign_reward_candidate_ids_by_body
                if isinstance(visible_sign_reward_candidate_ids_by_body, dict)
                else {}
            ),
            require_visible_rewards=bool(manage_visible_sign_rewards),
        )
        already_captured = int(capture_flag_trait_id) in trait_id_set and existing_sun_moon_sign_state_complete
        if int(capture_flag_trait_id) not in trait_id_set:
            summary["eligible_without_capture"] += 1

        house_sign_map = _build_house_sign_map_for_sim(trait_ids, marker_trait_ids)
        if house_sign_map is None or len(house_sign_map) < 12:
            summary["skipped_missing_house_map"] += 1
            continue

        existing_chart_body_sign_indexes = _complete_chart_body_sign_indexes_from_existing_traits(
            equipped_traits_with_ids=equipped,
            house_sign_map=house_sign_map,
            sun_sign_trait_by_index=(
                sun_sign_trait_by_index if isinstance(sun_sign_trait_by_index, dict) else {}
            ),
            moon_sign_trait_by_index=(
                moon_sign_trait_by_index if isinstance(moon_sign_trait_by_index, dict) else {}
            ),
        )
        if already_captured:
            if isinstance(existing_chart_body_sign_indexes, dict):
                summary["skipped_already_captured"] += 1
                _store_chart_record_for_sim(
                    sim_info=sim_info,
                    transit_service=service,
                    house_sign_map=house_sign_map,
                    body_sign_index_by_name=existing_chart_body_sign_indexes,
                    provenance="stored_natal_markers",
                )
                continue
            sim_id = _sim_info_id(sim_info)
            if sim_id is not None and _chart_payload_is_complete(service.get_chart_record_payload(int(sim_id))):
                summary["skipped_already_captured"] += 1
                continue
        if isinstance(existing_chart_body_sign_indexes, dict) and existing_sun_moon_sign_state_complete:
            summary["skipped_existing_chart_state"] += 1
            _store_chart_record_for_sim(
                sim_info=sim_info,
                transit_service=service,
                house_sign_map=house_sign_map,
                body_sign_index_by_name=existing_chart_body_sign_indexes,
                provenance="stored_natal_markers",
            )
            continue

        sim_id = _sim_info_id(sim_info)
        if (
            sim_id is not None
            and existing_sun_moon_sign_state_complete
            and _chart_payload_is_complete(service.get_chart_record_payload(int(sim_id)))
        ):
            summary["skipped_existing_chart_state"] += 1
            continue

        changed = False
        existing_visible_sign_indexes = _visible_sign_indexes_from_equipped_traits(equipped)
        chart_body_sign_index_by_name: Dict[str, int]
        chart_provenance: str
        if len(existing_visible_sign_indexes) >= 2:
            chart_body_sign_index_by_name = dict(service.state.sign_index_by_body)
            chart_body_sign_index_by_name.update(existing_visible_sign_indexes)
            desired_by_body = _desired_natal_traits_for_body_sign_indexes(
                house_sign_map=house_sign_map,
                available_by_body_house=available_by_body_house,
                body_sign_index_by_name=chart_body_sign_index_by_name,
            )
            desired_sign_traits = _desired_natal_sign_traits_from_sign_indexes(
                sign_index_by_body=existing_visible_sign_indexes,
                sun_sign_trait_by_index=sun_sign_trait_by_index,
                moon_sign_trait_by_index=moon_sign_trait_by_index,
            )
            chart_provenance = "existing_visible_signs"
        else:
            chart_body_sign_index_by_name = _legacy_sign_indexes_by_body(
                sim_info=sim_info,
                transit_service=service,
            )
            desired_by_body, desired_sign_traits = _desired_legacy_natal_traits_for_sim(
                sim_info=sim_info,
                transit_service=service,
                house_sign_map=house_sign_map,
                available_by_body_house=available_by_body_house,
                sun_sign_trait_by_index=sun_sign_trait_by_index,
                moon_sign_trait_by_index=moon_sign_trait_by_index,
            )
            chart_provenance = "legacy_random"
        if len(desired_by_body) < len(BODY_NAMES) or len(desired_sign_traits) < 2:
            continue

        desired_id_by_body: Dict[str, int] = {}
        for body, trait in desired_by_body.items():
            tid = _trait_guid64(trait)
            if tid is not None:
                desired_id_by_body[body] = int(tid)
        if len(desired_id_by_body) < len(BODY_NAMES):
            continue

        desired_sign_ids: Dict[str, int] = {}
        for body, trait in desired_sign_traits.items():
            tid = _trait_guid64(trait)
            if tid is not None:
                desired_sign_ids[body] = int(tid)
        if len(desired_sign_ids) < 2:
            continue

        for equipped_trait, equipped_tid in equipped:
            if equipped_tid not in planet_house_candidate_ids:
                continue
            desired_match = False
            for body, candidate_ids in candidate_ids_by_body.items():
                if equipped_tid not in candidate_ids:
                    continue
                if desired_id_by_body.get(body) == equipped_tid:
                    desired_match = True
                break
            if desired_match:
                continue
            if _trait_tracker_remove_trait(sim_info, trait_tracker, equipped_trait):
                summary["traits_removed"] += 1
                changed = True
                equipped_ids.discard(equipped_tid)

        for body, desired_trait in desired_by_body.items():
            desired_tid = desired_id_by_body.get(body)
            if desired_tid is None or desired_tid in equipped_ids:
                continue
            if _trait_tracker_add_trait(sim_info, trait_tracker, desired_trait):
                summary["traits_added"] += 1
                changed = True
                equipped_ids.add(desired_tid)

        sign_ids_sun = sign_candidate_ids_by_body.get("Sun", set())
        sign_ids_moon = sign_candidate_ids_by_body.get("Moon", set())
        for equipped_trait, equipped_tid in equipped:
            sign_body = None
            if equipped_tid in sign_ids_sun:
                sign_body = "Sun"
            elif equipped_tid in sign_ids_moon:
                sign_body = "Moon"
            if sign_body is None:
                continue
            if desired_sign_ids.get(sign_body) == equipped_tid:
                continue
            if _trait_tracker_remove_trait(sim_info, trait_tracker, equipped_trait):
                summary["traits_removed"] += 1
                changed = True
                equipped_ids.discard(equipped_tid)

        for body in ("Sun", "Moon"):
            desired_trait = desired_sign_traits.get(body)
            desired_tid = desired_sign_ids.get(body)
            if desired_trait is None or desired_tid is None or desired_tid in equipped_ids:
                continue
            if _trait_tracker_add_trait(sim_info, trait_tracker, desired_trait):
                summary["traits_added"] += 1
                changed = True
                equipped_ids.add(desired_tid)

        if manage_visible_sign_rewards:
            visible_reward_ids_sun = visible_sign_reward_candidate_ids_by_body.get("Sun", set())
            visible_reward_ids_moon = visible_sign_reward_candidate_ids_by_body.get("Moon", set())
            desired_visible_sign_traits = _desired_visible_sign_reward_traits_from_natal_sign_traits(
                desired_sign_traits,
                visible_sun_reward_trait_by_index=visible_sun_reward_trait_by_index,
                visible_moon_reward_trait_by_index=visible_moon_reward_trait_by_index,
            )
            desired_visible_sign_ids: Dict[str, int] = {}
            for body, trait in desired_visible_sign_traits.items():
                tid = _trait_guid64(trait)
                if tid is not None:
                    desired_visible_sign_ids[body] = int(tid)
            if len(desired_visible_sign_ids) >= 2:
                for equipped_trait, equipped_tid in equipped:
                    visible_body = None
                    if equipped_tid in visible_reward_ids_sun:
                        visible_body = "Sun"
                    elif equipped_tid in visible_reward_ids_moon:
                        visible_body = "Moon"
                    if visible_body is None:
                        continue
                    if desired_visible_sign_ids.get(visible_body) == equipped_tid:
                        continue
                    if _trait_tracker_remove_trait(sim_info, trait_tracker, equipped_trait):
                        summary["traits_removed"] += 1
                        changed = True
                        equipped_ids.discard(equipped_tid)

                for body in ("Sun", "Moon"):
                    desired_trait = desired_visible_sign_traits.get(body)
                    desired_tid = desired_visible_sign_ids.get(body)
                    if desired_trait is None or desired_tid is None or desired_tid in equipped_ids:
                        continue
                    if _trait_tracker_add_trait(sim_info, trait_tracker, desired_trait):
                        summary["traits_added"] += 1
                        changed = True
                        equipped_ids.add(desired_tid)
                        _apply_visible_sign_timed_buff_for_trait_add(
                            sim_info,
                            desired_trait,
                            cache=cache,
                        )

        have_all_house_natal = all(desired_tid in equipped_ids for desired_tid in desired_id_by_body.values())
        have_sign_natal = all(desired_tid in equipped_ids for desired_tid in desired_sign_ids.values())
        if (
            have_all_house_natal
            and have_sign_natal
            and int(capture_flag_trait_id) not in equipped_ids
        ):
            if _trait_tracker_add_trait(sim_info, trait_tracker, capture_flag_trait):
                summary["traits_added"] += 1
                changed = True
                equipped_ids.add(int(capture_flag_trait_id))

        if int(capture_flag_trait_id) in equipped_ids and int(legacy_flag_trait_id) not in equipped_ids:
            if _trait_tracker_add_trait(sim_info, trait_tracker, legacy_flag_trait):
                summary["traits_added"] += 1
                changed = True
                equipped_ids.add(int(legacy_flag_trait_id))

        if int(capture_flag_trait_id) in equipped_ids:
            _store_chart_record_for_sim(
                sim_info=sim_info,
                transit_service=service,
                house_sign_map=house_sign_map,
                body_sign_index_by_name=chart_body_sign_index_by_name,
                provenance=chart_provenance,
            )

        if changed:
            summary["sims_changed"] += 1
        if int(capture_flag_trait_id) in equipped_ids and int(legacy_flag_trait_id) in equipped_ids:
            summary["sims_seeded"] += 1

    return summary


def seed_active_household_teen_cosmic_natal_snapshots(
    *,
    active_household_id: Optional[int],
    refresh_marker_cache: bool = False,
    sign_seed_mode: str = "current_sky",
    transit_service: Optional[CosmicTransitService] = None,
) -> Dict[str, object]:
    """Seed uncaptured teen+ sims in the active household from the configured Cosmic sign source."""
    if refresh_marker_cache:
        reset_natal_marker_cache()
    cache = _marker_cache()

    available_by_body_house = cache.get("available_by_body_house", {})
    candidate_ids_by_body = cache.get("candidate_ids_by_body", {})
    planet_house_candidate_ids = cache.get("planet_house_candidate_ids", set())
    sun_sign_trait_by_index = cache.get("sun_sign_trait_by_index", {})
    moon_sign_trait_by_index = cache.get("moon_sign_trait_by_index", {})
    sign_candidate_ids_by_body = cache.get("sign_candidate_ids_by_body", {})
    visible_sun_reward_trait_by_index = cache.get("visible_sun_reward_trait_by_index", {})
    visible_moon_reward_trait_by_index = cache.get("visible_moon_reward_trait_by_index", {})
    visible_sign_reward_candidate_ids_by_body = cache.get("visible_sign_reward_candidate_ids_by_body", {})
    hidden_chart_ruler_body_by_trait_id = cache.get("hidden_chart_ruler_body_by_trait_id", {})
    visible_chart_ruler_reward_trait_by_body = cache.get("visible_chart_ruler_reward_trait_by_body", {})
    visible_chart_ruler_reward_body_by_trait_id = cache.get("visible_chart_ruler_reward_body_by_trait_id", {})
    personality_rising_trait_by_index = cache.get("personality_rising_trait_by_index", {})
    rising_marker_trait_by_index = cache.get("rising_marker_trait_by_index", {})
    rising_personality_sign_index_by_trait_id = cache.get("rising_personality_sign_index_by_trait_id", {})
    rising_marker_sign_index_by_trait_id = cache.get("rising_marker_sign_index_by_trait_id", {})
    capture_flag_trait = cache.get("capture_flag_trait")
    capture_flag_trait_id = cache.get("capture_flag_trait_id")

    summary: Dict[str, object] = {
        "active_household_id": int(active_household_id) if active_household_id is not None else None,
        "has_active_household_id": 1 if active_household_id is not None else 0,
        "sims_seen": 0,
        "household_sims_seen": 0,
        "teen_plus_seen": 0,
        "eligible_without_capture": 0,
        "sims_seeded": 0,
        "sims_changed": 0,
        "skipped_no_trait_tracker": 0,
        "skipped_already_captured": 0,
        "skipped_existing_chart_state": 0,
        "skipped_missing_house_map": 0,
        "traits_added": 0,
        "traits_removed": 0,
        "available_marker_defs": len(available_by_body_house) if isinstance(available_by_body_house, dict) else 0,
        "available_sun_sign_defs": len(sun_sign_trait_by_index) if isinstance(sun_sign_trait_by_index, dict) else 0,
        "available_moon_sign_defs": len(moon_sign_trait_by_index) if isinstance(moon_sign_trait_by_index, dict) else 0,
        "available_visible_sun_reward_defs": len(visible_sun_reward_trait_by_index) if isinstance(visible_sun_reward_trait_by_index, dict) else 0,
        "available_visible_moon_reward_defs": len(visible_moon_reward_trait_by_index) if isinstance(visible_moon_reward_trait_by_index, dict) else 0,
        "available_visible_chart_ruler_reward_defs": len(visible_chart_ruler_reward_trait_by_body) if isinstance(visible_chart_ruler_reward_trait_by_body, dict) else 0,
        "available_personality_rising_defs": len(personality_rising_trait_by_index) if isinstance(personality_rising_trait_by_index, dict) else 0,
        "available_rising_marker_defs": len(rising_marker_trait_by_index) if isinstance(rising_marker_trait_by_index, dict) else 0,
        "chart_ruler_visible_traits_added": 0,
        "chart_ruler_visible_traits_removed": 0,
        "rising_promotion_deferred_teen": 0,
        "rising_promotion_deferred_adult": 0,
        "rising_marker_removed_teen": 0,
        "rising_marker_removed_adult": 0,
        "rising_lane_preteen_seen": 0,
        "rising_lane_teen_seen": 0,
        "rising_lane_adult_seen": 0,
        "rising_lane_unknown_seen": 0,
        "has_capture_flag_def": 1 if capture_flag_trait is not None and capture_flag_trait_id is not None else 0,
        "cosmic_seed_mode": 1,
        "sign_seed_mode": str(sign_seed_mode or "current_sky"),
    }

    if active_household_id is None:
        return summary
    if not isinstance(available_by_body_house, dict) or len(available_by_body_house) < len(BODY_NAMES):
        return summary
    if not isinstance(sun_sign_trait_by_index, dict) or len(sun_sign_trait_by_index) < 12:
        return summary
    if not isinstance(moon_sign_trait_by_index, dict) or len(moon_sign_trait_by_index) < 12:
        return summary
    if capture_flag_trait is None or capture_flag_trait_id is None:
        return summary

    manage_visible_sign_rewards = (
        isinstance(visible_sun_reward_trait_by_index, dict)
        and isinstance(visible_moon_reward_trait_by_index, dict)
        and len(visible_sun_reward_trait_by_index) >= 12
        and len(visible_moon_reward_trait_by_index) >= 12
    )

    service = transit_service or get_global_transit_service()
    target_household_id = int(active_household_id)

    for sim_info in _iter_household_sim_infos_by_id(active_household_id):
        summary["sims_seen"] += 1

        summary["household_sims_seen"] += 1

        if not _is_teen_or_older(sim_info):
            continue
        summary["teen_plus_seen"] += 1

        trait_tracker = getattr(sim_info, "trait_tracker", None)
        if trait_tracker is None:
            summary["skipped_no_trait_tracker"] += 1
            continue

        trait_ids, marker_trait_ids = _collect_trait_ids_and_markers(sim_info)
        equipped = _equipped_traits_with_ids(sim_info)
        equipped_ids = {tid for _, tid in equipped}

        rising_age_lane = _rising_age_lane_for_sim_info(sim_info)
        rising_guard_summary = _reconcile_rising_marker_guard(
            sim_info=sim_info,
            trait_tracker=trait_tracker,
            is_teen_plus=True,
            rising_age_lane=rising_age_lane,
            equipped_traits_with_ids=equipped,
            equipped_ids=equipped_ids,
            personality_rising_trait_by_index=(
                personality_rising_trait_by_index if isinstance(personality_rising_trait_by_index, dict) else {}
            ),
            rising_marker_trait_by_index=(
                rising_marker_trait_by_index if isinstance(rising_marker_trait_by_index, dict) else {}
            ),
            rising_personality_sign_index_by_trait_id=(
                rising_personality_sign_index_by_trait_id
                if isinstance(rising_personality_sign_index_by_trait_id, dict)
                else {}
            ),
            rising_marker_sign_index_by_trait_id=(
                rising_marker_sign_index_by_trait_id
                if isinstance(rising_marker_sign_index_by_trait_id, dict)
                else {}
            ),
        )
        for key in (
            "rising_promotion_deferred_teen",
            "rising_promotion_deferred_adult",
            "rising_marker_removed_teen",
            "rising_marker_removed_adult",
            "rising_lane_preteen_seen",
            "rising_lane_teen_seen",
            "rising_lane_adult_seen",
            "rising_lane_unknown_seen",
        ):
            summary[key] = int(summary.get(key, 0) or 0) + int(rising_guard_summary.get(key, 0) or 0)
        summary["traits_added"] += int(rising_guard_summary.get("traits_added", 0) or 0)
        summary["traits_removed"] += int(rising_guard_summary.get("traits_removed", 0) or 0)
        if int(rising_guard_summary.get("changed", 0) or 0):
            trait_ids, marker_trait_ids = _collect_trait_ids_and_markers(sim_info)
            equipped = _equipped_traits_with_ids(sim_info)
            equipped_ids = {tid for _, tid in equipped}

        chart_ruler_summary = _reconcile_visible_chart_ruler_rewards(
            sim_info=sim_info,
            trait_tracker=trait_tracker,
            equipped_traits_with_ids=equipped,
            equipped_ids=equipped_ids,
            hidden_chart_ruler_body_by_trait_id=(
                hidden_chart_ruler_body_by_trait_id if isinstance(hidden_chart_ruler_body_by_trait_id, dict) else {}
            ),
            visible_chart_ruler_reward_trait_by_body=(
                visible_chart_ruler_reward_trait_by_body
                if isinstance(visible_chart_ruler_reward_trait_by_body, dict)
                else {}
            ),
            visible_chart_ruler_reward_body_by_trait_id=(
                visible_chart_ruler_reward_body_by_trait_id
                if isinstance(visible_chart_ruler_reward_body_by_trait_id, dict)
                else {}
            ),
        )
        summary["traits_added"] += int(chart_ruler_summary.get("traits_added", 0) or 0)
        summary["traits_removed"] += int(chart_ruler_summary.get("traits_removed", 0) or 0)
        summary["chart_ruler_visible_traits_added"] += int(
            chart_ruler_summary.get("chart_ruler_visible_traits_added", 0) or 0
        )
        summary["chart_ruler_visible_traits_removed"] += int(
            chart_ruler_summary.get("chart_ruler_visible_traits_removed", 0) or 0
        )

        trait_id_set = {int(tid) for tid in trait_ids}
        existing_sun_moon_sign_state_complete = _has_complete_equipped_sun_moon_sign_state(
            equipped_ids=equipped_ids,
            sign_candidate_ids_by_body=(
                sign_candidate_ids_by_body if isinstance(sign_candidate_ids_by_body, dict) else {}
            ),
            visible_sign_reward_candidate_ids_by_body=(
                visible_sign_reward_candidate_ids_by_body
                if isinstance(visible_sign_reward_candidate_ids_by_body, dict)
                else {}
            ),
            require_visible_rewards=bool(manage_visible_sign_rewards),
        )
        already_captured = int(capture_flag_trait_id) in trait_id_set and existing_sun_moon_sign_state_complete
        if int(capture_flag_trait_id) not in trait_id_set:
            summary["eligible_without_capture"] += 1

        house_sign_map = _build_house_sign_map_for_sim(trait_ids, marker_trait_ids)
        if house_sign_map is None or len(house_sign_map) < 12:
            summary["skipped_missing_house_map"] += 1
            continue

        existing_chart_body_sign_indexes = _complete_chart_body_sign_indexes_from_existing_traits(
            equipped_traits_with_ids=equipped,
            house_sign_map=house_sign_map,
            sun_sign_trait_by_index=(
                sun_sign_trait_by_index if isinstance(sun_sign_trait_by_index, dict) else {}
            ),
            moon_sign_trait_by_index=(
                moon_sign_trait_by_index if isinstance(moon_sign_trait_by_index, dict) else {}
            ),
        )
        if already_captured:
            if isinstance(existing_chart_body_sign_indexes, dict):
                summary["skipped_already_captured"] += 1
                _store_chart_record_for_sim(
                    sim_info=sim_info,
                    transit_service=service,
                    house_sign_map=house_sign_map,
                    body_sign_index_by_name=existing_chart_body_sign_indexes,
                    provenance="stored_natal_markers",
                )
                continue
            sim_id = _sim_info_id(sim_info)
            if sim_id is not None and _chart_payload_is_complete(service.get_chart_record_payload(int(sim_id))):
                summary["skipped_already_captured"] += 1
                continue
        if isinstance(existing_chart_body_sign_indexes, dict) and existing_sun_moon_sign_state_complete:
            summary["skipped_existing_chart_state"] += 1
            _store_chart_record_for_sim(
                sim_info=sim_info,
                transit_service=service,
                house_sign_map=house_sign_map,
                body_sign_index_by_name=existing_chart_body_sign_indexes,
                provenance="stored_natal_markers",
            )
            continue

        sim_id = _sim_info_id(sim_info)
        if (
            sim_id is not None
            and existing_sun_moon_sign_state_complete
            and _chart_payload_is_complete(service.get_chart_record_payload(int(sim_id)))
        ):
            summary["skipped_existing_chart_state"] += 1
            continue

        changed = False
        existing_visible_sign_indexes = _visible_sign_indexes_from_equipped_traits(equipped)
        if isinstance(existing_chart_body_sign_indexes, dict):
            chart_body_sign_index_by_name = dict(service.state.sign_index_by_body)
            chart_body_sign_index_by_name.update(existing_chart_body_sign_indexes)
            desired_by_body = _desired_natal_traits_for_body_sign_indexes(
                house_sign_map=house_sign_map,
                available_by_body_house=available_by_body_house,
                body_sign_index_by_name=chart_body_sign_index_by_name,
            )
            desired_sign_traits = _desired_natal_sign_traits_from_existing_natal_markers(
                equipped_traits_with_ids=equipped,
                house_sign_map=house_sign_map,
                sun_sign_trait_by_index=sun_sign_trait_by_index,
                moon_sign_trait_by_index=moon_sign_trait_by_index,
            )
            chart_provenance = "stored_natal_markers"
        elif len(existing_visible_sign_indexes) >= 2:
            chart_body_sign_index_by_name = dict(service.state.sign_index_by_body)
            chart_body_sign_index_by_name.update(existing_visible_sign_indexes)
            desired_by_body = _desired_natal_traits_for_body_sign_indexes(
                house_sign_map=house_sign_map,
                available_by_body_house=available_by_body_house,
                body_sign_index_by_name=chart_body_sign_index_by_name,
            )
            desired_sign_traits = _desired_natal_sign_traits_from_sign_indexes(
                sign_index_by_body=existing_visible_sign_indexes,
                sun_sign_trait_by_index=sun_sign_trait_by_index,
                moon_sign_trait_by_index=moon_sign_trait_by_index,
            )
            chart_provenance = "existing_visible_signs"
        else:
            resolved_sign_seed_mode = str(sign_seed_mode or "current_sky").strip().lower()
            chart_body_sign_index_by_name = dict(service.state.sign_index_by_body)
            if resolved_sign_seed_mode == "random_sun_moon":
                randomized_sign_indexes = _legacy_sign_indexes_by_body(
                    sim_info=sim_info,
                    transit_service=service,
                )
                for body in ("Sun", "Moon"):
                    randomized_index = randomized_sign_indexes.get(body)
                    if isinstance(randomized_index, int):
                        chart_body_sign_index_by_name[body] = int(randomized_index) % 12
                desired_by_body = _desired_natal_traits_for_body_sign_indexes(
                    house_sign_map=house_sign_map,
                    available_by_body_house=available_by_body_house,
                    body_sign_index_by_name=chart_body_sign_index_by_name,
                )
                desired_sign_traits = _desired_natal_sign_traits_from_sign_indexes(
                    sign_index_by_body=chart_body_sign_index_by_name,
                    sun_sign_trait_by_index=sun_sign_trait_by_index,
                    moon_sign_trait_by_index=moon_sign_trait_by_index,
                )
                chart_provenance = "randomized_sun_moon"
            else:
                desired_by_body = _desired_natal_traits_for_sim(service, house_sign_map, available_by_body_house)
                desired_sign_traits = _desired_natal_sign_traits_from_current_sky(
                    service,
                    sun_sign_trait_by_index=sun_sign_trait_by_index,
                    moon_sign_trait_by_index=moon_sign_trait_by_index,
                )
                chart_provenance = "clock_snapshot"
        if len(desired_by_body) < len(BODY_NAMES) or len(desired_sign_traits) < 2:
            continue

        desired_id_by_body: Dict[str, int] = {}
        for body, trait in desired_by_body.items():
            tid = _trait_guid64(trait)
            if tid is not None:
                desired_id_by_body[body] = int(tid)
        if len(desired_id_by_body) < len(BODY_NAMES):
            continue

        desired_sign_ids: Dict[str, int] = {}
        for body, trait in desired_sign_traits.items():
            tid = _trait_guid64(trait)
            if tid is not None:
                desired_sign_ids[body] = int(tid)
        if len(desired_sign_ids) < 2:
            continue

        for equipped_trait, equipped_tid in equipped:
            if equipped_tid not in planet_house_candidate_ids:
                continue
            desired_match = False
            for body, candidate_ids in candidate_ids_by_body.items():
                if equipped_tid not in candidate_ids:
                    continue
                if desired_id_by_body.get(body) == equipped_tid:
                    desired_match = True
                break
            if desired_match:
                continue
            if _trait_tracker_remove_trait(sim_info, trait_tracker, equipped_trait):
                summary["traits_removed"] += 1
                changed = True
                equipped_ids.discard(equipped_tid)

        for body, desired_trait in desired_by_body.items():
            desired_tid = desired_id_by_body.get(body)
            if desired_tid is None or desired_tid in equipped_ids:
                continue
            if _trait_tracker_add_trait(sim_info, trait_tracker, desired_trait):
                summary["traits_added"] += 1
                changed = True
                equipped_ids.add(desired_tid)

        sign_ids_sun = sign_candidate_ids_by_body.get("Sun", set())
        sign_ids_moon = sign_candidate_ids_by_body.get("Moon", set())
        for equipped_trait, equipped_tid in equipped:
            sign_body = None
            if equipped_tid in sign_ids_sun:
                sign_body = "Sun"
            elif equipped_tid in sign_ids_moon:
                sign_body = "Moon"
            if sign_body is None:
                continue
            if desired_sign_ids.get(sign_body) == equipped_tid:
                continue
            if _trait_tracker_remove_trait(sim_info, trait_tracker, equipped_trait):
                summary["traits_removed"] += 1
                changed = True
                equipped_ids.discard(equipped_tid)

        for body in ("Sun", "Moon"):
            desired_trait = desired_sign_traits.get(body)
            desired_tid = desired_sign_ids.get(body)
            if desired_trait is None or desired_tid is None or desired_tid in equipped_ids:
                continue
            if _trait_tracker_add_trait(sim_info, trait_tracker, desired_trait):
                summary["traits_added"] += 1
                changed = True
                equipped_ids.add(desired_tid)

        if manage_visible_sign_rewards:
            visible_reward_ids_sun = visible_sign_reward_candidate_ids_by_body.get("Sun", set())
            visible_reward_ids_moon = visible_sign_reward_candidate_ids_by_body.get("Moon", set())
            desired_visible_sign_traits = _desired_visible_sign_reward_traits_from_natal_sign_traits(
                desired_sign_traits,
                visible_sun_reward_trait_by_index=visible_sun_reward_trait_by_index,
                visible_moon_reward_trait_by_index=visible_moon_reward_trait_by_index,
            )
            desired_visible_sign_ids: Dict[str, int] = {}
            for body, trait in desired_visible_sign_traits.items():
                tid = _trait_guid64(trait)
                if tid is not None:
                    desired_visible_sign_ids[body] = int(tid)
            if len(desired_visible_sign_ids) >= 2:
                for equipped_trait, equipped_tid in equipped:
                    visible_body = None
                    if equipped_tid in visible_reward_ids_sun:
                        visible_body = "Sun"
                    elif equipped_tid in visible_reward_ids_moon:
                        visible_body = "Moon"
                    if visible_body is None:
                        continue
                    if desired_visible_sign_ids.get(visible_body) == equipped_tid:
                        continue
                    if _trait_tracker_remove_trait(sim_info, trait_tracker, equipped_trait):
                        summary["traits_removed"] += 1
                        changed = True
                        equipped_ids.discard(equipped_tid)

                for body in ("Sun", "Moon"):
                    desired_trait = desired_visible_sign_traits.get(body)
                    desired_tid = desired_visible_sign_ids.get(body)
                    if desired_trait is None or desired_tid is None or desired_tid in equipped_ids:
                        continue
                    if _trait_tracker_add_trait(sim_info, trait_tracker, desired_trait):
                        summary["traits_added"] += 1
                        changed = True
                        equipped_ids.add(desired_tid)
                        _apply_visible_sign_timed_buff_for_trait_add(
                            sim_info,
                            desired_trait,
                            cache=cache,
                        )

        have_all_house_natal = all(desired_tid in equipped_ids for desired_tid in desired_id_by_body.values())
        have_sign_natal = all(desired_tid in equipped_ids for desired_tid in desired_sign_ids.values())
        if (
            have_all_house_natal
            and have_sign_natal
            and int(capture_flag_trait_id) not in equipped_ids
        ):
            if _trait_tracker_add_trait(sim_info, trait_tracker, capture_flag_trait):
                summary["traits_added"] += 1
                changed = True
                equipped_ids.add(int(capture_flag_trait_id))
                summary["sims_seeded"] += 1

        if int(capture_flag_trait_id) in equipped_ids:
            _store_chart_record_for_sim(
                sim_info=sim_info,
                transit_service=service,
                house_sign_map=house_sign_map,
                body_sign_index_by_name=chart_body_sign_index_by_name,
                provenance=chart_provenance,
            )

        if changed:
            summary["sims_changed"] += 1

    return summary


def onboard_active_household_natal_snapshots(
    *,
    active_household_id: Optional[int],
    refresh_marker_cache: bool = False,
    teen_sign_seed_mode: str = "current_sky",
    transit_service: Optional[CosmicTransitService] = None,
) -> Dict[str, object]:
    """One-shot onboarding for a newly played household.

    Pre-teens and teen+ sims are seeded for Cosmic onboarding using the
    configured sign-seed mode.
    """
    service = transit_service or get_global_transit_service()
    preteen_summary = seed_active_household_preteen_natal_snapshots(
        active_household_id=active_household_id,
        refresh_marker_cache=bool(refresh_marker_cache),
        sign_seed_mode=teen_sign_seed_mode,
        transit_service=service,
    )
    teen_summary = seed_active_household_teen_cosmic_natal_snapshots(
        active_household_id=active_household_id,
        refresh_marker_cache=False,
        sign_seed_mode=teen_sign_seed_mode,
        transit_service=service,
    )

    return {
        "active_household_id": int(active_household_id) if active_household_id is not None else None,
        "has_active_household_id": 1 if active_household_id is not None else 0,
        "teen_sign_seed_mode": str(teen_sign_seed_mode or "current_sky"),
        "preteen_summary": preteen_summary,
        "teen_summary": teen_summary,
        "teen_cosmic_summary": teen_summary,
        "preteen_sims_seeded": int(preteen_summary.get("sims_seeded", 0) or 0),
        "teen_sims_seeded": int(teen_summary.get("sims_seeded", 0) or 0),
        "teen_cosmic_sims_seeded": int(teen_summary.get("sims_seeded", 0) or 0),
        "total_sims_seeded": int(preteen_summary.get("sims_seeded", 0) or 0)
        + int(teen_summary.get("sims_seeded", 0) or 0),
        "total_traits_added": int(preteen_summary.get("traits_added", 0) or 0)
        + int(teen_summary.get("traits_added", 0) or 0),
        "total_traits_removed": int(preteen_summary.get("traits_removed", 0) or 0)
        + int(teen_summary.get("traits_removed", 0) or 0),
    }


def onboard_active_household_natal_snapshots_for_lifecycle(
    *,
    active_household_id: Optional[int],
    refresh_marker_cache: bool = False,
    teen_sign_seed_mode: str = "current_sky",
) -> Dict[str, object]:
    return onboard_active_household_natal_snapshots(
        active_household_id=active_household_id,
        refresh_marker_cache=bool(refresh_marker_cache),
        teen_sign_seed_mode=str(teen_sign_seed_mode or "current_sky"),
    )


def inspect_active_household_legacy_v2_candidates(
    *,
    active_household_id: Optional[int],
    refresh_marker_cache: bool = False,
    transit_service: Optional[CosmicTransitService] = None,
) -> Dict[str, object]:
    """Inspect whether an active household still looks like a pre-V2 Big3 save.

    We only auto-migrate households that still show a clear legacy shape:
    visible Big3 signs already exist, but the household never received natal
    capture data, or it carries an incomplete captured state from an older pass.
    """
    if refresh_marker_cache:
        reset_natal_marker_cache()
    cache = _marker_cache()
    capture_flag_trait_id = cache.get("capture_flag_trait_id")
    legacy_flag_trait_id = cache.get("legacy_flag_trait_id")
    sun_sign_trait_by_index = cache.get("sun_sign_trait_by_index", {})
    moon_sign_trait_by_index = cache.get("moon_sign_trait_by_index", {})

    summary: Dict[str, object] = {
        "active_household_id": int(active_household_id) if active_household_id is not None else None,
        "has_active_household_id": 1 if active_household_id is not None else 0,
        "sims_seen": 0,
        "teen_plus_seen": 0,
        "sims_with_visible_big3": 0,
        "sims_with_capture_flag": 0,
        "sims_with_legacy_flag": 0,
        "candidate_visible_big3_without_capture": 0,
        "candidate_captured_without_legacy_incomplete": 0,
        "candidate_sim_ids": [],
        "candidate_reasons_by_sim_id": {},
        "anchor_sim_id": None,
        "should_migrate": 0,
    }
    if active_household_id is None:
        return summary

    service = transit_service or get_global_transit_service()
    candidate_sim_ids = []
    candidate_reasons_by_sim_id: Dict[str, str] = {}

    for sim_info in _iter_household_sim_infos_by_id(active_household_id):
        summary["sims_seen"] += 1
        if not _is_teen_or_older(sim_info):
            continue
        summary["teen_plus_seen"] += 1

        trait_tracker = getattr(sim_info, "trait_tracker", None)
        if trait_tracker is None:
            continue

        trait_ids, marker_trait_ids = _collect_trait_ids_and_markers(sim_info)
        trait_id_set = {int(tid) for tid in trait_ids}
        equipped = _equipped_traits_with_ids(sim_info)
        sim_id = _sim_info_id(sim_info)

        has_capture_flag = (
            capture_flag_trait_id is not None and int(capture_flag_trait_id) in trait_id_set
        )
        has_legacy_flag = (
            legacy_flag_trait_id is not None and int(legacy_flag_trait_id) in trait_id_set
        )
        if has_capture_flag:
            summary["sims_with_capture_flag"] += 1
        if has_legacy_flag:
            summary["sims_with_legacy_flag"] += 1

        visible_sign_indexes = _visible_sign_indexes_from_equipped_traits(equipped)
        has_visible_rising = False
        for equipped_trait, _equipped_tid in equipped:
            if _parse_rising_sign_trait_name(_trait_name(equipped_trait)) is not None:
                has_visible_rising = True
                break
        has_visible_big3 = has_visible_rising and len(visible_sign_indexes) >= 2
        if has_visible_big3:
            summary["sims_with_visible_big3"] += 1

        candidate_reason = None
        if has_visible_big3 and not has_capture_flag:
            candidate_reason = "visible_big3_without_capture"
        elif has_capture_flag and not has_legacy_flag and has_visible_big3:
            house_sign_map = _build_house_sign_map_for_sim(trait_ids, marker_trait_ids)
            complete_chart_state = None
            if isinstance(house_sign_map, Mapping) and len(dict(house_sign_map)) >= 12:
                complete_chart_state = _complete_chart_body_sign_indexes_from_existing_traits(
                    equipped_traits_with_ids=equipped,
                    house_sign_map=house_sign_map,
                    sun_sign_trait_by_index=(
                        sun_sign_trait_by_index if isinstance(sun_sign_trait_by_index, dict) else {}
                    ),
                    moon_sign_trait_by_index=(
                        moon_sign_trait_by_index if isinstance(moon_sign_trait_by_index, dict) else {}
                    ),
                )
            chart_payload = service.get_chart_record_payload(int(sim_id)) if sim_id is not None else None
            if not _chart_payload_is_complete(chart_payload) and not isinstance(complete_chart_state, dict):
                candidate_reason = "captured_without_legacy_incomplete"

        if candidate_reason is None or sim_id is None:
            continue

        candidate_sim_ids.append(int(sim_id))
        candidate_reasons_by_sim_id[str(int(sim_id))] = str(candidate_reason)
        if summary["anchor_sim_id"] is None:
            summary["anchor_sim_id"] = int(sim_id)
        if candidate_reason == "visible_big3_without_capture":
            summary["candidate_visible_big3_without_capture"] += 1
        else:
            summary["candidate_captured_without_legacy_incomplete"] += 1

    summary["candidate_sim_ids"] = tuple(candidate_sim_ids)
    summary["candidate_reasons_by_sim_id"] = candidate_reasons_by_sim_id
    summary["should_migrate"] = 1 if candidate_sim_ids else 0
    return summary


def migrate_active_household_legacy_natal_to_v2(
    *,
    active_household_id: Optional[int],
    refresh_marker_cache: bool = False,
    transit_service: Optional[CosmicTransitService] = None,
) -> Dict[str, object]:
    """Upgrade the active household's legacy natal state into V2-compatible data."""
    service = transit_service or get_global_transit_service()
    summary: Dict[str, object] = {
        "active_household_id": int(active_household_id) if active_household_id is not None else None,
        "has_active_household_id": 1 if active_household_id is not None else 0,
        "legacy_mark_summary": None,
        "legacy_reseed_summary": None,
        "onboard_summary": None,
        "legacy_sims_marked": 0,
        "legacy_sims_seen": 0,
        "legacy_traits_added": 0,
        "legacy_traits_removed": 0,
        "onboard_total_sims_seeded": 0,
        "onboard_total_traits_added": 0,
        "onboard_total_traits_removed": 0,
    }
    if active_household_id is None:
        return summary

    legacy_mark_summary = mark_zone_captured_unflagged_as_legacy(
        active_household_id=active_household_id,
        refresh_marker_cache=bool(refresh_marker_cache),
        reseed_now=True,
        transit_service=service,
    )
    onboard_summary = onboard_active_household_natal_snapshots(
        active_household_id=active_household_id,
        refresh_marker_cache=False,
        transit_service=service,
    )

    summary["legacy_mark_summary"] = legacy_mark_summary
    summary["legacy_reseed_summary"] = (
        legacy_mark_summary.get("reseed_summary") if isinstance(legacy_mark_summary, dict) else None
    )
    summary["onboard_summary"] = onboard_summary
    summary["legacy_sims_marked"] = int(legacy_mark_summary.get("sims_marked_legacy", 0) or 0)
    summary["legacy_sims_seen"] = int(legacy_mark_summary.get("sims_with_capture_flag", 0) or 0)
    summary["legacy_traits_added"] = int(legacy_mark_summary.get("traits_added", 0) or 0)

    reseed_summary = summary["legacy_reseed_summary"]
    if isinstance(reseed_summary, dict):
        summary["legacy_traits_removed"] = int(reseed_summary.get("traits_removed", 0) or 0)

    if isinstance(onboard_summary, dict):
        summary["onboard_total_sims_seeded"] = int(onboard_summary.get("total_sims_seeded", 0) or 0)
        summary["onboard_total_traits_added"] = int(onboard_summary.get("total_traits_added", 0) or 0)
        summary["onboard_total_traits_removed"] = int(onboard_summary.get("total_traits_removed", 0) or 0)

    return summary


def reset_natal_snapshot_for_sim_info(
    sim_info,
    *,
    refresh_marker_cache: bool = False,
) -> Dict[str, object]:
    """Reset natal snapshot traits for one sim, regardless of legacy flag."""
    if refresh_marker_cache:
        reset_natal_marker_cache()
    cache = _marker_cache()

    planet_house_candidate_ids = set(cache.get("planet_house_candidate_ids", set()) or set())
    sign_candidate_ids_by_body = cache.get("sign_candidate_ids_by_body", {}) or {}
    visible_sign_reward_candidate_ids_by_body = cache.get("visible_sign_reward_candidate_ids_by_body", {}) or {}
    capture_flag_trait_id = cache.get("capture_flag_trait_id")
    legacy_flag_trait_id = cache.get("legacy_flag_trait_id")

    sign_candidate_ids = set()
    if isinstance(sign_candidate_ids_by_body, dict):
        for _body, ids in sign_candidate_ids_by_body.items():
            try:
                sign_candidate_ids.update(int(v) for v in ids)
            except Exception:
                continue
    visible_sign_reward_candidate_ids = set()
    if isinstance(visible_sign_reward_candidate_ids_by_body, dict):
        for _body, ids in visible_sign_reward_candidate_ids_by_body.items():
            try:
                visible_sign_reward_candidate_ids.update(int(v) for v in ids)
            except Exception:
                continue

    all_resettable_ids = set(int(v) for v in planet_house_candidate_ids)
    all_resettable_ids.update(int(v) for v in sign_candidate_ids)
    all_resettable_ids.update(int(v) for v in visible_sign_reward_candidate_ids)
    if capture_flag_trait_id is not None:
        all_resettable_ids.add(int(capture_flag_trait_id))
    if legacy_flag_trait_id is not None:
        all_resettable_ids.add(int(legacy_flag_trait_id))

    summary: Dict[str, object] = {
        "ok": False,
        "sim_name": None,
        "sim_id": None,
        "traits_removed": 0,
        "had_capture_flag": 0,
        "had_legacy_flag": 0,
        "had_any_natal_traits": 0,
        "resettable_trait_defs_known": len(all_resettable_ids),
    }

    if sim_info is None:
        summary["error"] = "missing_sim_info"
        return summary

    try:
        full_name = getattr(sim_info, "full_name", None)
    except Exception:
        full_name = None
    if not full_name:
        try:
            first_name = getattr(sim_info, "first_name", None) or ""
            last_name = getattr(sim_info, "last_name", None) or ""
            full_name = ("{0} {1}".format(first_name, last_name)).strip() or None
        except Exception:
            full_name = None
    summary["sim_name"] = str(full_name) if full_name else None
    summary["sim_id"] = _sim_info_id(sim_info)

    trait_tracker = getattr(sim_info, "trait_tracker", None)
    if trait_tracker is None:
        summary["error"] = "missing_trait_tracker"
        return summary

    trait_ids, _marker_trait_ids = _collect_trait_ids_and_markers(sim_info)
    trait_id_set = {int(tid) for tid in trait_ids}
    raw_traits = tuple(_iter_traits_for_sim_info(sim_info))
    equipped = _equipped_traits_with_ids(sim_info)

    if capture_flag_trait_id is not None and int(capture_flag_trait_id) in trait_id_set:
        summary["had_capture_flag"] = 1
    if legacy_flag_trait_id is not None and int(legacy_flag_trait_id) in trait_id_set:
        summary["had_legacy_flag"] = 1

    raw_seen_obj_ids: set = set()
    removable_candidates: List[Tuple[object, Optional[int]]] = []
    for trait, tid in equipped:
        raw_seen_obj_ids.add(id(trait))
        removable_candidates.append((trait, int(tid)))
    for trait in raw_traits:
        marker = id(trait)
        if marker in raw_seen_obj_ids:
            continue
        raw_seen_obj_ids.add(marker)
        tid = _trait_guid64(trait)
        removable_candidates.append((trait, int(tid) if tid is not None else None))

    removed_any = False
    had_any_natal = False
    for candidate_trait, candidate_tid in removable_candidates:
        trait_name = _trait_name(candidate_trait)
        removable_by_name = (
            _trait_contains_text(candidate_trait, _NATAL_CAPTURE_FLAG_NAME)
            or _trait_contains_text(candidate_trait, _NATAL_LEGACY_FLAG_NAME)
            or _trait_contains_text(candidate_trait, _NATAL_PLANET_HOUSE_PREFIX)
            or _parse_natal_planet_house_marker_name(trait_name) is not None
            or _parse_natal_sign_marker_name(trait_name) is not None
            or _parse_visible_sign_reward_trait_name(trait_name) is not None
        )
        removable_by_id = (
            candidate_tid is not None and int(candidate_tid) in all_resettable_ids
        )
        if not removable_by_name and not removable_by_id:
            continue
        had_any_natal = True
        if _trait_tracker_remove_trait(sim_info, trait_tracker, candidate_trait):
            summary["traits_removed"] += 1
            removed_any = True

    summary["had_any_natal_traits"] = 1 if had_any_natal else 0
    summary["ok"] = True
    summary["changed"] = 1 if removed_any else 0
    return summary


def reset_zone_legacy_natal_snapshots(
    *,
    refresh_marker_cache: bool = False,
    reseed_now: bool = False,
    active_household_id: Optional[int] = None,
    transit_service: Optional[CosmicTransitService] = None,
) -> Dict[str, object]:
    """Remove natal markers/flags for legacy-generated charts, optionally reseed immediately.

    This only resets sims carrying `PlumAntics_CosmicEngineNatal_ChartLegacyGeneratedHidden`.
    """
    if refresh_marker_cache:
        reset_natal_marker_cache()
    cache = _marker_cache()

    planet_house_candidate_ids = set(cache.get("planet_house_candidate_ids", set()) or set())
    sign_candidate_ids_by_body = cache.get("sign_candidate_ids_by_body", {}) or {}
    visible_sign_reward_candidate_ids_by_body = cache.get("visible_sign_reward_candidate_ids_by_body", {}) or {}
    capture_flag_trait_id = cache.get("capture_flag_trait_id")
    legacy_flag_trait_id = cache.get("legacy_flag_trait_id")

    sign_candidate_ids = set()
    if isinstance(sign_candidate_ids_by_body, dict):
        for _body, ids in sign_candidate_ids_by_body.items():
            try:
                sign_candidate_ids.update(int(v) for v in ids)
            except Exception:
                continue
    visible_sign_reward_candidate_ids = set()
    if isinstance(visible_sign_reward_candidate_ids_by_body, dict):
        for _body, ids in visible_sign_reward_candidate_ids_by_body.items():
            try:
                visible_sign_reward_candidate_ids.update(int(v) for v in ids)
            except Exception:
                continue

    all_resettable_ids = set(int(v) for v in planet_house_candidate_ids)
    all_resettable_ids.update(int(v) for v in sign_candidate_ids)
    all_resettable_ids.update(int(v) for v in visible_sign_reward_candidate_ids)
    if capture_flag_trait_id is not None:
        all_resettable_ids.add(int(capture_flag_trait_id))
    if legacy_flag_trait_id is not None:
        all_resettable_ids.add(int(legacy_flag_trait_id))

    summary: Dict[str, object] = {
        "active_household_id": int(active_household_id) if active_household_id is not None else None,
        "has_active_household_id": 1 if active_household_id is not None else 0,
        "sims_seen": 0,
        "legacy_sims_seen": 0,
        "sims_changed": 0,
        "traits_removed": 0,
        "resettable_trait_defs_known": len(all_resettable_ids),
        "has_legacy_flag_def": 1 if legacy_flag_trait_id is not None else 0,
        "reseed_now": 1 if bool(reseed_now) else 0,
        "reseed_summary": None,
    }

    # Allow name-based fallback even if the legacy flag tuning id was not
    # discovered from the trait manager on this runtime build.
    if not all_resettable_ids and legacy_flag_trait_id is None:
        return summary

    service = transit_service or get_global_transit_service()
    target_household_id = int(active_household_id) if active_household_id is not None else None

    for sim_info in _iter_household_sim_infos_by_id(active_household_id):
        summary["sims_seen"] += 1

        trait_tracker = getattr(sim_info, "trait_tracker", None)
        if trait_tracker is None:
            continue

        trait_ids, _marker_trait_ids = _collect_trait_ids_and_markers(sim_info)
        trait_id_set = {int(tid) for tid in trait_ids}
        raw_traits = tuple(_iter_traits_for_sim_info(sim_info))
        equipped = _equipped_traits_with_ids(sim_info)
        raw_seen_obj_ids: set = set()
        removable_candidates: List[Tuple[object, Optional[int]]] = []
        for trait, tid in equipped:
            raw_seen_obj_ids.add(id(trait))
            removable_candidates.append((trait, int(tid)))
        for trait in raw_traits:
            marker = id(trait)
            if marker in raw_seen_obj_ids:
                continue
            raw_seen_obj_ids.add(marker)
            tid = _trait_guid64(trait)
            removable_candidates.append((trait, int(tid) if tid is not None else None))

        has_legacy_flag = False
        if legacy_flag_trait_id is not None:
            has_legacy_flag = int(legacy_flag_trait_id) in trait_id_set
        if not has_legacy_flag:
            for equipped_trait, equipped_tid in equipped:
                if legacy_flag_trait_id is not None and int(equipped_tid) == int(legacy_flag_trait_id):
                    has_legacy_flag = True
                    break
                if _trait_contains_text(equipped_trait, _NATAL_LEGACY_FLAG_NAME):
                    has_legacy_flag = True
                    break
        if not has_legacy_flag:
            for raw_trait in raw_traits:
                if _trait_contains_text(raw_trait, _NATAL_LEGACY_FLAG_NAME):
                    has_legacy_flag = True
                    break
        if not has_legacy_flag:
            continue
        summary["legacy_sims_seen"] += 1

        changed = False
        for candidate_trait, candidate_tid in removable_candidates:
            trait_name = _trait_name(candidate_trait)
            removable_by_name = (
                _trait_contains_text(candidate_trait, _NATAL_CAPTURE_FLAG_NAME)
                or _trait_contains_text(candidate_trait, _NATAL_LEGACY_FLAG_NAME)
                or _trait_contains_text(candidate_trait, _NATAL_PLANET_HOUSE_PREFIX)
                or _parse_natal_planet_house_marker_name(trait_name) is not None
                or _parse_natal_sign_marker_name(trait_name) is not None
                or _parse_visible_sign_reward_trait_name(trait_name) is not None
            )
            removable_by_id = (
                candidate_tid is not None and int(candidate_tid) in all_resettable_ids
            )
            if not removable_by_name and not removable_by_id:
                continue
            if _trait_tracker_remove_trait(sim_info, trait_tracker, candidate_trait):
                summary["traits_removed"] += 1
                changed = True

        if changed:
            summary["sims_changed"] += 1

    if reseed_now:
        if active_household_id is not None:
            preteen_summary = seed_active_household_preteen_natal_snapshots(
                active_household_id=active_household_id,
                refresh_marker_cache=False,
                transit_service=service,
            )
            teen_summary = seed_active_household_teen_legacy_natal_snapshots(
                active_household_id=active_household_id,
                refresh_marker_cache=False,
                transit_service=service,
            )
            summary["reseed_summary"] = {
                "active_household_id": int(active_household_id),
                "has_active_household_id": 1,
                "preteen_summary": preteen_summary,
                "teen_legacy_summary": teen_summary,
                "preteen_sims_seeded": int(preteen_summary.get("sims_seeded", 0) or 0),
                "teen_legacy_sims_seeded": int(teen_summary.get("sims_seeded", 0) or 0),
                "total_sims_seeded": int(preteen_summary.get("sims_seeded", 0) or 0)
                + int(teen_summary.get("sims_seeded", 0) or 0),
                "traits_added": int(preteen_summary.get("traits_added", 0) or 0)
                + int(teen_summary.get("traits_added", 0) or 0),
                "traits_removed": int(preteen_summary.get("traits_removed", 0) or 0)
                + int(teen_summary.get("traits_removed", 0) or 0),
            }
        else:
            summary["reseed_summary"] = sync_zone_natal_snapshots(
                transit_service=service,
                refresh_marker_cache=False,
                legacy_seed_uncaptured=True,
            )

    return summary


def mark_zone_captured_unflagged_as_legacy(
    *,
    refresh_marker_cache: bool = False,
    reseed_now: bool = False,
    active_household_id: Optional[int] = None,
    transit_service: Optional[CosmicTransitService] = None,
) -> Dict[str, object]:
    """Mark captured natal charts as legacy when provenance flag is missing.

    Intended as a migration helper for test saves / older builds where natal
    charts were captured before the legacy provenance trait was added.
    """
    if refresh_marker_cache:
        reset_natal_marker_cache()
    cache = _marker_cache()

    capture_flag_trait = cache.get("capture_flag_trait")
    capture_flag_trait_id = cache.get("capture_flag_trait_id")
    legacy_flag_trait = cache.get("legacy_flag_trait")
    legacy_flag_trait_id = cache.get("legacy_flag_trait_id")
    planet_house_candidate_ids = set(cache.get("planet_house_candidate_ids", set()) or set())
    sign_candidate_ids_by_body = cache.get("sign_candidate_ids_by_body", {}) or {}

    sign_candidate_ids = set()
    if isinstance(sign_candidate_ids_by_body, dict):
        for _body, ids in sign_candidate_ids_by_body.items():
            try:
                sign_candidate_ids.update(int(v) for v in ids)
            except Exception:
                continue

    natal_candidate_ids = set(int(v) for v in planet_house_candidate_ids)
    natal_candidate_ids.update(int(v) for v in sign_candidate_ids)

    summary: Dict[str, object] = {
        "active_household_id": int(active_household_id) if active_household_id is not None else None,
        "has_active_household_id": 1 if active_household_id is not None else 0,
        "sims_seen": 0,
        "sims_with_capture_flag": 0,
        "sims_already_legacy": 0,
        "sims_marked_legacy": 0,
        "traits_added": 0,
        "has_capture_flag_def": 1 if capture_flag_trait is not None and capture_flag_trait_id is not None else 0,
        "has_legacy_flag_def": 1 if legacy_flag_trait is not None and legacy_flag_trait_id is not None else 0,
        "reseed_now": 1 if bool(reseed_now) else 0,
        "reseed_summary": None,
    }

    if capture_flag_trait_id is None or legacy_flag_trait is None or legacy_flag_trait_id is None:
        return summary

    service = transit_service or get_global_transit_service()
    target_household_id = int(active_household_id) if active_household_id is not None else None

    for sim_info in _iter_household_sim_infos_by_id(active_household_id):
        summary["sims_seen"] += 1

        trait_tracker = getattr(sim_info, "trait_tracker", None)
        if trait_tracker is None:
            continue

        trait_ids, _marker_trait_ids = _collect_trait_ids_and_markers(sim_info)
        trait_id_set = {int(tid) for tid in trait_ids}

        if int(capture_flag_trait_id) not in trait_id_set:
            continue
        summary["sims_with_capture_flag"] += 1

        if int(legacy_flag_trait_id) in trait_id_set:
            summary["sims_already_legacy"] += 1
            continue

        # Only retro-flag sims that actually carry natal marker/sign traits.
        has_any_natal_marker = any(int(tid) in natal_candidate_ids for tid in trait_id_set)
        if not has_any_natal_marker:
            equipped = _equipped_traits_with_ids(sim_info)
            for equipped_trait, _equipped_tid in equipped:
                trait_name = _trait_name(equipped_trait)
                if (
                    _trait_contains_text(equipped_trait, _NATAL_PLANET_HOUSE_PREFIX)
                    or _parse_natal_planet_house_marker_name(trait_name) is not None
                    or _parse_natal_sign_marker_name(trait_name) is not None
                ):
                    has_any_natal_marker = True
                    break
        if not has_any_natal_marker:
            continue

        if _trait_tracker_add_trait(sim_info, trait_tracker, legacy_flag_trait):
            summary["traits_added"] += 1
            summary["sims_marked_legacy"] += 1

    if reseed_now:
        summary["reseed_summary"] = reset_zone_legacy_natal_snapshots(
            refresh_marker_cache=False,
            reseed_now=True,
            active_household_id=active_household_id,
            transit_service=service,
        )

    return summary
