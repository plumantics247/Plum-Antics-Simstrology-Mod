"""Custom action tuning bridge for Houses readout."""

from __future__ import annotations

import logging
import random
import time
from typing import Dict, Iterable, List, Optional, Tuple

from .astrology_skill_gate import simstrology_skill_meets, simstrology_skill_unlock_level, get_simstrology_skill_level
from .chart_composition import (
    build_chart_composition_from_chart_payload,
    get_dominant_element,
    get_dominant_mode,
)
from .chart_records import should_refresh_outer_planets_chart_payload
from .chart_read_dialogs import chart_readout_available, show_chart_readout_dialog_sequence
from .chemistry_settings import get_chemistry_profile_label, read_chemistry_profile_id
from .crystal_resonance import (
    allowed_crystal_keys_for_payload,
    chart_payload_for_sim,
    identify_crystal_key,
    register_gifted_attunement,
)
from .crystal_resonance_activation import is_crystal_resonance_addon_active
from .retrograde_visibility_settings import (
    get_retrograde_visibility_profile_label,
    read_retrograde_visibility_profile_id,
)
from .dirty_sync_queue import (
    SCOPE_CRYSTAL_RESONANCE,
    SCOPE_MOON_RETURN,
    SCOPE_NATAL_SNAPSHOTS,
    SCOPE_PLANET_HOUSES,
    SCOPE_RETROGRADE_CONSEQUENCES,
    SCOPE_RETROGRADE_MARKERS,
    SCOPE_RISING_BUFFS,
    SCOPE_SOLAR_RETURN,
    SCOPE_VISIBLE_SIGN_BUFFS,
    mark_sim_dirty,
)
from .houses_notification_bridge import build_houses_readout_payload
from .mode_lock import clear_mode_lock, set_mode_lock, sync_mode_lock_traits
from .sim_eligibility import sim_info_is_human, sim_info_is_teen_plus
from .transit_core import ALL_BODY_NAMES, BODY_NAMES, SIGNS
from .transit_service import get_global_transit_service


log = logging.getLogger("cosmic_engine.loot_actions")

_NATAL_ONBOARD_LOOT_IN_PROGRESS = False
_NATAL_ONBOARD_LAST_RUN_BY_HOUSEHOLD_ID = {}  # type: Dict[int, float]
_NATAL_ONBOARD_DEBOUNCE_SECONDS = 1.5
_LAST_NATAL_ONBOARD_DEBUG = None
_LAST_RISING_CHEMISTRY_REFRESH_DEBUG = None
_LAST_SUN_CHEMISTRY_REFRESH_DEBUG = None
_LTR_FRIENDSHIP_MAIN_TRACK_ID = 16650
_LTR_ROMANCE_MAIN_TRACK_ID = 16651
_CRYSTAL_RESONANCE_GIFT_ATTUNEMENT_MINUTES = 480
_ZODIAC_SIGNS = (
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
_POST_ONBOARD_DIRTY_SCOPES = (
    SCOPE_PLANET_HOUSES,
    SCOPE_NATAL_SNAPSHOTS,
    SCOPE_VISIBLE_SIGN_BUFFS,
    SCOPE_RISING_BUFFS,
    SCOPE_MOON_RETURN,
    SCOPE_SOLAR_RETURN,
    SCOPE_RETROGRADE_MARKERS,
    SCOPE_RETROGRADE_CONSEQUENCES,
)
_CHART_PLANETS = ("Sun", "Moon", "Mercury", "Venus", "Mars", "Jupiter", "Saturn")
_TRANSIT_MARKER_BODIES = tuple(ALL_BODY_NAMES)
_TRANSIT_HOUSE_TOKEN_TO_LABEL = (
    ("FirstHouse", "1st House"),
    ("FourthHouse", "4th House"),
    ("TenthHouse", "10th House"),
)
_TRANSIT_HOUSE_LABEL_ORDER = {"1st House": 0, "4th House": 1, "10th House": 2}
_PLANET_ORDER = {planet: idx for idx, planet in enumerate(_CHART_PLANETS)}
_TRANSIT_MARKER_PLANET_ORDER = {planet: idx for idx, planet in enumerate(_TRANSIT_MARKER_BODIES)}
_LEGACY_ELEMENT_TRAIT_IDS = {
    "fire": 2913211980,
    "earth": 2344594988,
    "air": 3056304860,
    "water": 3974436693,
}
_LEGACY_MODE_TRAIT_IDS = {
    "cardinal": 3493848740,
    "fixed": 3268539798,
    "mutable": 2904895862,
}
_LEGACY_BIG3_PLANET_TRAIT_IDS = frozenset((
    4208090340,  # PlumAntics_Big3Mod_Mercury
    3858955547,  # PlumAntics_Big3Mod_Mars
))
_CHART_MARKER_SKILL_FEATURE = "chart_marker_awareness"
_CHART_RULER_SKILL_FEATURE = "chart_ruler_awareness"
_CHART_MARKER_TIE_BEHAVIOR = "top"
_LEGACY_ELEMENT_CHANNEL_BUFF_IDS = {
    "fire": 16127254205400264106,
    "earth": 17985278563382514346,
    "air": 17851971977042887498,
    "water": 16516863652583972695,
}
_CHART_RULER_HIDDEN_TRAIT_IDS = {
    "Sun": 9347662265918957273,
    "Moon": 17239223782097826302,
    "Mercury": 16904598435992729626,
    "Venus": 15345056623721389106,
    "Mars": 14595238808715947030,
    "Jupiter": 9922924821041816598,
    "Saturn": 14935865373790362108,
}
_CHART_RULER_VISIBLE_TRAIT_IDS = {
    "Sun": 16719930145011223341,
    "Moon": 16719930145011223342,
    "Mercury": 16719930145011223343,
    "Venus": 16719930145011223344,
    "Mars": 16719930145011223345,
    "Jupiter": 16719930145011223346,
    "Saturn": 16719930145011223347,
}
_SOUL_PATH_MASTER_TRAIT_ID = 8185333920870945121
_SOUL_PATH_MASTER_CONFIDENT_PULSE_BUFF_ID = 8185333920870945122

try:
    from .natal_snapshot_markers import _current_sim_absolute_ticks, _sim_minutes_to_ticks
except Exception:  # pragma: no cover - local fallback

    def _current_sim_absolute_ticks():
        return None

    def _sim_minutes_to_ticks(_minutes):
        return None


def _active_transit_weather_body_names(service) -> Tuple[str, ...]:
    resolver = getattr(service, "active_body_names", None)
    if callable(resolver):
        return tuple(resolver())
    return tuple(_CHART_PLANETS)


_PRETTY_TRANSIT_BODY_ORDER = (
    "Sun",
    "Moon",
    "Mercury",
    "Venus",
    "Mars",
    "Jupiter",
    "Saturn",
    "Uranus",
    "Neptune",
    "Pluto",
    "Chiron",
)


def _active_pretty_transit_body_names(service) -> Tuple[str, ...]:
    active_body_names = set(_active_transit_weather_body_names(service))
    return tuple(
        body_name
        for body_name in _PRETTY_TRANSIT_BODY_ORDER
        if body_name in active_body_names
    )


def get_last_natal_onboard_summary() -> Dict[str, object]:
    payload = _LAST_NATAL_ONBOARD_DEBUG
    return dict(payload) if isinstance(payload, dict) else {}


def get_last_rising_chemistry_refresh_summary() -> Dict[str, object]:
    payload = _LAST_RISING_CHEMISTRY_REFRESH_DEBUG
    return dict(payload) if isinstance(payload, dict) else {}


def get_last_sun_chemistry_refresh_summary() -> Dict[str, object]:
    payload = _LAST_SUN_CHEMISTRY_REFRESH_DEBUG
    return dict(payload) if isinstance(payload, dict) else {}


_RISING_TRAIT_ID_TO_CHART_RULER = {
    2297406366: "Mars",       # Aries Rising
    3923158167: "Mars",       # Scorpio Rising
    2588878312: "Venus",      # Taurus Rising
    3123976786: "Venus",      # Libra Rising
    4242808797: "Mercury",    # Gemini Rising
    2665561705: "Mercury",    # Virgo Rising
    2154635568: "Moon",       # Cancer Rising
    3739357428: "Sun",        # Leo Rising
    2405249506: "Jupiter",    # Sagittarius Rising
    3588503643: "Jupiter",    # Pisces Rising
    3178572581: "Saturn",     # Capricorn Rising
    2243949835: "Saturn",     # Aquarius Rising
}
_VISIBLE_RISING_SIGN_INDEX_TO_TRAIT_ID = {
    0: 2297406366,   # Aries Rising
    1: 2588878312,   # Taurus Rising
    2: 4242808797,   # Gemini Rising
    3: 2154635568,   # Cancer Rising
    4: 3739357428,   # Leo Rising
    5: 2665561705,   # Virgo Rising
    6: 3123976786,   # Libra Rising
    7: 3923158167,   # Scorpio Rising
    8: 2405249506,   # Sagittarius Rising
    9: 3178572581,   # Capricorn Rising
    10: 2243949835,  # Aquarius Rising
    11: 3588503643,  # Pisces Rising
}
_HOUSES_ASSIGN_ROUTER_LOOT_ID = 11593030835386645003
_REMOVE_ALL_SIMSTROLOGY_STATE_LOOT_ID = 830000000000009100
_FIRST_HOUSE_RISING_MARKER_TRAIT_IDS = frozenset((
    3343364179,  # PlumAntics_CosmicEngineHouses_FirstHouse_AriesHidden
    4000742779,  # PlumAntics_CosmicEngineHouses_FirstHouse_TaurusHidden
    3030542498,  # PlumAntics_CosmicEngineHouses_FirstHouse_GeminiHidden
    1721376067,  # PlumAntics_CosmicEngineHouses_FirstHouse_CancerHidden
    277283509,   # PlumAntics_CosmicEngineHouses_FirstHouse_LeoHidden
    88897080,    # PlumAntics_CosmicEngineHouses_FirstHouse_VirgoHidden
    698795255,   # PlumAntics_CosmicEngineHouses_FirstHouse_LibraHidden
    2925616490,  # PlumAntics_CosmicEngineHouses_FirstHouse_ScorpioHidden
    1952046335,  # PlumAntics_CosmicEngineHouses_FirstHouse_SagittariusHidden
    2986595748,  # PlumAntics_CosmicEngineHouses_FirstHouse_CapricornHidden
    4207452764,  # PlumAntics_CosmicEngineHouses_FirstHouse_AquariusHidden
    3220165512,  # PlumAntics_CosmicEngineHouses_FirstHouse_PiscesHidden
))


def _coerce_trait_candidates(value) -> Iterable[object]:
    if value is None:
        return ()
    if isinstance(value, dict):
        value = value.values()
    if isinstance(value, (str, bytes)):
        return ()
    try:
        return tuple(value)
    except Exception:
        return (value,)


def _append_unique_traits(out: List[object], seen_obj_ids: set, value) -> None:
    for trait in _coerce_trait_candidates(value):
        if trait is None:
            continue
        marker = id(trait)
        if marker in seen_obj_ids:
            continue
        seen_obj_ids.add(marker)
        out.append(trait)


def _iter_traits_from_tracker(trait_tracker) -> Iterable[object]:
    if trait_tracker is None:
        return ()

    out: List[object] = []
    seen_obj_ids: set = set()

    # Common containers across different runtime builds. Some builds expose
    # hidden traits here while others only expose visible/equipped traits.
    for attr_name in (
        "equipped_traits",
        "_equipped_traits",
        "all_traits",
        "_all_traits",
        "traits",
        "_traits",
        "hidden_traits",
        "_hidden_traits",
    ):
        try:
            value = getattr(trait_tracker, attr_name, None)
        except Exception:
            value = None
        _append_unique_traits(out, seen_obj_ids, value)

    for method_name in (
        "get_traits",
        "get_all_traits",
        "all_traits_gen",
        "get_hidden_traits",
    ):
        fn = getattr(trait_tracker, method_name, None)
        if not callable(fn):
            continue
        try:
            value = fn()
        except TypeError:
            continue
        except Exception:
            continue
        _append_unique_traits(out, seen_obj_ids, value)

    # Final fallback for tracker types that expose iteration only.
    try:
        _append_unique_traits(out, seen_obj_ids, tuple(trait_tracker))
    except Exception:
        pass

    return tuple(out)


def _enum_name(value):
    if value is None:
        return None
    name = getattr(value, "name", None)
    if isinstance(name, str) and name:
        return name.upper()
    text = str(value)
    if "." in text:
        tail = text.split(".")[-1]
        if tail:
            return tail.replace(">", "").strip().upper()
    text = str(text or "").strip()
    return text.upper() if text else None


_LUNAR_PHASE_NAME_LABELS = {
    "NEW_MOON": "new",
    "WAXING_CRESCENT": "waxing crescent",
    "FIRST_QUARTER": "first quarter",
    "WAXING_GIBBOUS": "waxing gibbous",
    "FULL_MOON": "full",
    "WANING_GIBBOUS": "waning gibbous",
    "THIRD_QUARTER": "third quarter",
    "WANING_CRESCENT": "waning crescent",
}


def _get_lunar_cycle_service():
    try:
        import services  # type: ignore
    except Exception:
        return None

    for name in ("lunar_cycle_service", "get_lunar_cycle_service"):
        fn = getattr(services, name, None)
        if fn is None:
            continue
        try:
            return fn() if callable(fn) else fn
        except Exception:
            continue
    return None


def _current_lunar_phase_name():
    svc = _get_lunar_cycle_service()
    if svc is None:
        return None

    phase_candidates = []
    for attr_name in (
        "current_phase",
        "current_lunar_phase",
        "current_moon_phase",
        "lunar_phase",
        "moon_phase",
        "phase",
    ):
        try:
            value = getattr(svc, attr_name, None)
        except Exception:
            value = None
        if value is not None:
            phase_candidates.append(value)

    for method_name in (
        "get_current_phase",
        "get_current_lunar_phase",
        "get_phase",
        "current_phase",
    ):
        fn = getattr(svc, method_name, None)
        if not callable(fn):
            continue
        try:
            value = fn()
        except TypeError:
            continue
        except Exception:
            continue
        if value is not None:
            phase_candidates.append(value)

    for value in phase_candidates:
        enum_name = _enum_name(value)
        if enum_name in _LUNAR_PHASE_NAME_LABELS:
            return enum_name
    return None


def _iter_traits_for_sim_info(sim_info) -> Iterable[object]:
    out: List[object] = []
    seen_obj_ids: set = set()

    trait_tracker = getattr(sim_info, "trait_tracker", None)
    _append_unique_traits(out, seen_obj_ids, _iter_traits_from_tracker(trait_tracker))

    # Some builds expose complete trait collections on sim_info instead of the
    # tracker's equipped trait list.
    for attr_name in ("traits", "_traits", "all_traits", "_all_traits"):
        try:
            value = getattr(sim_info, attr_name, None)
        except Exception:
            value = None
        _append_unique_traits(out, seen_obj_ids, value)

    for method_name in ("get_traits", "get_all_traits", "all_traits_gen"):
        fn = getattr(sim_info, method_name, None)
        if not callable(fn):
            continue
        try:
            value = fn()
        except TypeError:
            continue
        except Exception:
            continue
        _append_unique_traits(out, seen_obj_ids, value)

    return tuple(out)


def _trait_manager():
    try:
        import services  # type: ignore
        import sims4.resources  # type: ignore

        return services.get_instance_manager(sims4.resources.Types.TRAIT)
    except Exception:
        return None


def _buff_manager():
    try:
        import services  # type: ignore
        import sims4.resources  # type: ignore

        return services.get_instance_manager(sims4.resources.Types.BUFF)
    except Exception:
        return None


def _resolve_trait(trait_id):
    manager = _trait_manager()
    if manager is None:
        return None
    try:
        return manager.get(int(trait_id))
    except Exception:
        return None


def _resolve_buff(buff_id):
    manager = _buff_manager()
    if manager is None:
        return None
    try:
        return manager.get(int(buff_id))
    except Exception:
        return None


def _trait_guid64(trait) -> Optional[int]:
    for attr in ("guid64", "guid", "instance"):
        value = getattr(trait, attr, None)
        if value is None:
            continue
        try:
            return int(value)
        except Exception:
            continue
    return None


def _trait_name(trait) -> str:
    for attr in ("__name__", "name", "_name"):
        value = getattr(trait, attr, None)
        if value:
            return str(value)
    return str(trait)


def _sim_has_trait(sim_info, trait_id: int) -> bool:
    for trait in _iter_traits_for_sim_info(sim_info):
        guid = _trait_guid64(trait)
        try:
            if int(guid) == int(trait_id):
                return True
        except Exception:
            continue
    return False


def _add_trait_if_missing(sim_info, trait_id: int) -> bool:
    if sim_info is None or _sim_has_trait(sim_info, trait_id):
        return False
    trait = _resolve_trait(trait_id)
    if trait is None:
        return False
    for owner in (getattr(sim_info, "trait_tracker", None), sim_info):
        add_fn = getattr(owner, "add_trait", None)
        if not callable(add_fn):
            continue
        try:
            add_fn(trait)
            return True
        except Exception:
            continue
    return False


def _remove_trait_if_present(sim_info, trait_id: int) -> bool:
    if sim_info is None:
        return False
    removed = False
    for trait in _iter_traits_for_sim_info(sim_info):
        guid = _trait_guid64(trait)
        try:
            if int(guid) != int(trait_id):
                continue
        except Exception:
            continue
        for owner in (getattr(sim_info, "trait_tracker", None), sim_info):
            remove_fn = getattr(owner, "remove_trait", None)
            if not callable(remove_fn):
                continue
            try:
                remove_fn(trait)
                removed = True
                break
            except Exception:
                continue
    return removed


def _sim_has_buff(sim_info, buff_id: int) -> bool:
    buff = _resolve_buff(buff_id)
    if sim_info is None or buff is None:
        return False
    for owner in (
        getattr(sim_info, "Buffs", None),
        getattr(sim_info, "buff_tracker", None),
        getattr(sim_info, "_buff_tracker", None),
        sim_info,
    ):
        if owner is None:
            continue
        for method_name in ("has_buff", "has_buff_by_type"):
            method = getattr(owner, method_name, None)
            if not callable(method):
                continue
            for arg in (buff, int(buff_id)):
                try:
                    if bool(method(arg)):
                        return True
                except Exception:
                    continue
    return False


def _add_buff_if_missing(sim_info, buff_id: int) -> bool:
    if sim_info is None or _sim_has_buff(sim_info, buff_id):
        return False
    buff = _resolve_buff(buff_id)
    if buff is None:
        return False
    for owner in (
        getattr(sim_info, "Buffs", None),
        getattr(sim_info, "buff_tracker", None),
        getattr(sim_info, "_buff_tracker", None),
        sim_info,
    ):
        if owner is None:
            continue
        for method_name in ("add_buff_by_type", "add_buff", "add_buff_from_op"):
            method = getattr(owner, method_name, None)
            if not callable(method):
                continue
            if method_name == "add_buff_by_type":
                arg_sets = ((int(buff_id),),)
            else:
                arg_sets = ((buff,), (int(buff_id),))
            for args in arg_sets:
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


def _remove_buff_if_present(sim_info, buff_id: int) -> bool:
    buff = _resolve_buff(buff_id)
    if sim_info is None or buff is None:
        return False
    removed = False
    for owner in (
        getattr(sim_info, "Buffs", None),
        getattr(sim_info, "buff_tracker", None),
        getattr(sim_info, "_buff_tracker", None),
        sim_info,
    ):
        if owner is None:
            continue
        for method_name in ("remove_buff_by_type", "remove_buff"):
            method = getattr(owner, method_name, None)
            if not callable(method):
                continue
            for arg in (buff, int(buff_id)):
                try:
                    method(arg)
                    removed = True
                except TypeError:
                    try:
                        method(arg, None)
                        removed = True
                    except Exception:
                        continue
                except Exception:
                    continue
    return removed


def _chart_payload_for_sim(sim_id: int, sim_info=None):
    payload = get_global_transit_service().get_chart_record_payload(int(sim_id))
    if isinstance(payload, dict) and not should_refresh_outer_planets_chart_payload(payload):
        return payload
    try:
        from plumantics_big3_runtime.integration.bridge import get_runtime  # type: ignore
    except Exception:
        return payload if isinstance(payload, dict) else None
    try:
        runtime = get_runtime()
        payload = runtime.get_chart_record_payload(int(sim_id))
        if isinstance(payload, dict) and should_refresh_outer_planets_chart_payload(payload):
            payload = None
        if not isinstance(payload, dict) and sim_info is not None:
            capture_fn = getattr(runtime, "_store_chart_record_for_sim_info", None)
            if callable(capture_fn):
                payload = capture_fn(
                    sim_info,
                    metadata={
                        "assignment_reason": "chart_marker_sync",
                        "assignment_flow": "recover_from_existing_traits",
                    },
                    overwrite_existing=True,
                )
    except Exception:
        payload = payload if isinstance(payload, dict) else None
    return payload if isinstance(payload, dict) else None


def apply_chart_marker_traits(sim_info, composition, *, tie_behavior=_CHART_MARKER_TIE_BEHAVIOR) -> Dict[str, object]:
    """Apply chart-wide element/mode marker traits from composition totals.

    Deprecated Sun-only logic used to assign these traits from the natal Sun
    sign alone. We now clear those legacy traits first and then apply chart
    markers only when totals produce a configured dominant result.
    """

    summary = {
        "dominant_element": None,
        "dominant_mode": None,
        "applied_element_trait_id": None,
        "applied_mode_trait_id": None,
        "removed_element_trait_ids": [],
        "removed_mode_trait_ids": [],
        "removed_element_buff_ids": [],
        "tie_behavior": str(tie_behavior or _CHART_MARKER_TIE_BEHAVIOR),
        "required_skill_level": int(
            simstrology_skill_unlock_level(_CHART_MARKER_SKILL_FEATURE, default=4)
        ),
        "actor_skill_level": int(get_simstrology_skill_level(sim_info)) if sim_info is not None else 0,
        "skill_gate_blocked": False,
    }

    if sim_info is None:
        return summary

    dominant_element = get_dominant_element(composition, tie_behavior=tie_behavior)
    dominant_mode = get_dominant_mode(composition, tie_behavior=tie_behavior)
    if isinstance(dominant_element, str):
        summary["dominant_element"] = dominant_element
    if isinstance(dominant_mode, str):
        summary["dominant_mode"] = dominant_mode

    for trait_id in _LEGACY_ELEMENT_TRAIT_IDS.values():
        if _remove_trait_if_present(sim_info, int(trait_id)):
            summary["removed_element_trait_ids"].append(int(trait_id))
    for trait_id in _LEGACY_MODE_TRAIT_IDS.values():
        if _remove_trait_if_present(sim_info, int(trait_id)):
            summary["removed_mode_trait_ids"].append(int(trait_id))

    # Deprecated cleanup for the old Sun-sign channel buffs. We remove any
    # stale buffs here, but chart marker assignment now applies traits only.
    for buff_id in _LEGACY_ELEMENT_CHANNEL_BUFF_IDS.values():
        if _remove_buff_if_present(sim_info, int(buff_id)):
            summary["removed_element_buff_ids"].append(int(buff_id))

    if not simstrology_skill_meets(sim_info, int(summary["required_skill_level"])):
        summary["skill_gate_blocked"] = True
        return summary

    trait_id = _LEGACY_ELEMENT_TRAIT_IDS.get(summary["dominant_element"])
    if trait_id is not None and _add_trait_if_missing(sim_info, int(trait_id)):
        summary["applied_element_trait_id"] = int(trait_id)

    trait_id = _LEGACY_MODE_TRAIT_IDS.get(summary["dominant_mode"])
    if trait_id is not None and _add_trait_if_missing(sim_info, int(trait_id)):
        summary["applied_mode_trait_id"] = int(trait_id)

    return summary


def _resolve_chart_ruler_planet(sim_info) -> Optional[str]:
    if sim_info is None:
        return None

    for rising_trait_id, planet in _RISING_TRAIT_ID_TO_CHART_RULER.items():
        if _sim_has_trait(sim_info, int(rising_trait_id)):
            return str(planet)

    sim_id = getattr(sim_info, "sim_id", None)
    if sim_id is None:
        sim_id = getattr(sim_info, "id", None)
    if sim_id is None:
        return None

    payload = _chart_payload_for_sim(int(sim_id), sim_info=sim_info)
    if not isinstance(payload, dict):
        return None

    chart_ruler_body = payload.get("chart_ruler_body")
    if chart_ruler_body in _CHART_RULER_VISIBLE_TRAIT_IDS:
        return str(chart_ruler_body)

    metadata = payload.get("metadata")
    if isinstance(metadata, dict):
        chart_ruler_body = metadata.get("chart_ruler_body")
        if chart_ruler_body in _CHART_RULER_VISIBLE_TRAIT_IDS:
            return str(chart_ruler_body)

    return None


def sync_chart_ruler_traits(sim_info) -> Dict[str, object]:
    """Sync internal and visible chart ruler traits from Rising/chart data."""

    summary = {
        "chart_ruler_body": None,
        "applied_hidden_trait_id": None,
        "applied_visible_trait_id": None,
        "removed_legacy_big3_trait_ids": [],
        "removed_hidden_trait_ids": [],
        "removed_visible_trait_ids": [],
        "required_skill_level": int(
            simstrology_skill_unlock_level(_CHART_RULER_SKILL_FEATURE, default=4)
        ),
        "actor_skill_level": int(get_simstrology_skill_level(sim_info)) if sim_info is not None else 0,
        "skill_gate_blocked": False,
        "source_missing": False,
    }

    if sim_info is None:
        summary["source_missing"] = True
        return summary

    # Retire the old Sun-sign Mercury/Mars markers so only chart-ruler markers remain live.
    for trait_id in _LEGACY_BIG3_PLANET_TRAIT_IDS:
        if _remove_trait_if_present(sim_info, int(trait_id)):
            summary["removed_legacy_big3_trait_ids"].append(int(trait_id))

    chart_ruler_body = _resolve_chart_ruler_planet(sim_info)
    if chart_ruler_body not in _CHART_RULER_VISIBLE_TRAIT_IDS:
        summary["source_missing"] = True
        return summary
    summary["chart_ruler_body"] = str(chart_ruler_body)

    for trait_id in _CHART_RULER_HIDDEN_TRAIT_IDS.values():
        if _remove_trait_if_present(sim_info, int(trait_id)):
            summary["removed_hidden_trait_ids"].append(int(trait_id))
    for trait_id in _CHART_RULER_VISIBLE_TRAIT_IDS.values():
        if _remove_trait_if_present(sim_info, int(trait_id)):
            summary["removed_visible_trait_ids"].append(int(trait_id))

    hidden_trait_id = _CHART_RULER_HIDDEN_TRAIT_IDS.get(chart_ruler_body)
    if hidden_trait_id is not None and _add_trait_if_missing(sim_info, int(hidden_trait_id)):
        summary["applied_hidden_trait_id"] = int(hidden_trait_id)

    if not simstrology_skill_meets(sim_info, int(summary["required_skill_level"])):
        summary["skill_gate_blocked"] = True
        return summary

    visible_trait_id = _CHART_RULER_VISIBLE_TRAIT_IDS.get(chart_ruler_body)
    if visible_trait_id is not None and _add_trait_if_missing(sim_info, int(visible_trait_id)):
        summary["applied_visible_trait_id"] = int(visible_trait_id)

    return summary


def _trait_text_candidates(trait) -> List[str]:
    out: List[str] = []
    for value in (
        _trait_name(trait),
        getattr(trait, "name", None),
        getattr(trait, "_name", None),
        getattr(type(trait), "__name__", None),
    ):
        if not value:
            continue
        text = str(value)
        if text not in out:
            out.append(text)
    for fn in (repr, str):
        try:
            text = fn(trait)
        except Exception:
            continue
        if text and text not in out:
            out.append(text)
    return out


def _source_debug_entries(owner, owner_label: str, attr_names: Iterable[str], method_names: Iterable[str]) -> List[Dict[str, object]]:
    rows: List[Dict[str, object]] = []

    for attr_name in attr_names:
        try:
            value = getattr(owner, attr_name, None)
        except Exception as exc:
            rows.append({"source": f"{owner_label}.{attr_name}", "error": repr(exc)})
            continue
        items = tuple(_coerce_trait_candidates(value))
        rows.append({"source": f"{owner_label}.{attr_name}", "count": len(items)})

    for method_name in method_names:
        fn = getattr(owner, method_name, None)
        if not callable(fn):
            rows.append({"source": f"{owner_label}.{method_name}()", "missing": True})
            continue
        try:
            value = fn()
        except TypeError as exc:
            rows.append({"source": f"{owner_label}.{method_name}()", "error": "TypeError", "detail": repr(exc)})
            continue
        except Exception as exc:
            rows.append({"source": f"{owner_label}.{method_name}()", "error": repr(exc)})
            continue
        items = tuple(_coerce_trait_candidates(value))
        rows.append({"source": f"{owner_label}.{method_name}()", "count": len(items)})

    return rows


def debug_trait_scan_for_sim_info(
    sim_info,
    *,
    contains: str = "PlumAntics_CosmicEngineNatal_",
    max_matches: int = 80,
) -> Dict[str, object]:
    payload: Dict[str, object] = {
        "ok": False,
        "sim_id": None,
        "sim_name": None,
        "contains": contains,
        "trait_tracker_type": None,
        "source_counts": [],
        "merged_trait_count": 0,
        "merged_trait_ids_count": 0,
        "natal_marker_trait_ids_count": 0,
        "contains_matches": [],
        "legacy_flag_matches": [],
    }

    if sim_info is None:
        payload["error"] = "missing_sim_info"
        return payload

    sim_id = getattr(sim_info, "sim_id", None)
    if sim_id is None:
        sim_id = getattr(sim_info, "id", None)
    try:
        payload["sim_id"] = int(sim_id) if sim_id is not None else None
    except Exception:
        payload["sim_id"] = str(sim_id)

    first_name = getattr(sim_info, "first_name", None)
    last_name = getattr(sim_info, "last_name", None)
    if first_name or last_name:
        payload["sim_name"] = "{0} {1}".format(first_name or "", last_name or "").strip()
    else:
        payload["sim_name"] = str(getattr(sim_info, "full_name", None) or "")

    trait_tracker = getattr(sim_info, "trait_tracker", None)
    payload["trait_tracker_type"] = type(trait_tracker).__name__ if trait_tracker is not None else None

    source_counts: List[Dict[str, object]] = []
    if trait_tracker is not None:
        source_counts.extend(
            _source_debug_entries(
                trait_tracker,
                "trait_tracker",
                (
                    "equipped_traits",
                    "_equipped_traits",
                    "all_traits",
                    "_all_traits",
                    "traits",
                    "_traits",
                    "hidden_traits",
                    "_hidden_traits",
                ),
                ("get_traits", "get_all_traits", "all_traits_gen", "get_hidden_traits"),
            )
        )
    source_counts.extend(
        _source_debug_entries(
            sim_info,
            "sim_info",
            ("traits", "_traits", "all_traits", "_all_traits"),
            ("get_traits", "get_all_traits", "all_traits_gen"),
        )
    )
    payload["source_counts"] = source_counts

    merged = tuple(_iter_traits_for_sim_info(sim_info))
    payload["merged_trait_count"] = len(merged)

    trait_ids, marker_trait_ids = _collect_trait_ids_and_markers(sim_info)
    payload["merged_trait_ids_count"] = len(trait_ids)
    payload["natal_marker_trait_ids_count"] = len(marker_trait_ids)

    contains_matches: List[Dict[str, object]] = []
    legacy_matches: List[Dict[str, object]] = []
    contains_text = str(contains or "")
    for idx, trait in enumerate(merged):
        texts = _trait_text_candidates(trait)
        guid = _trait_guid64(trait)
        row = {
            "index": int(idx),
            "guid64": int(guid) if guid is not None else None,
            "name": _trait_name(trait),
            "texts": texts[:4],
        }
        if contains_text and any(contains_text in text for text in texts):
            if len(contains_matches) < int(max_matches):
                contains_matches.append(row)
        if any("PlumAntics_CosmicEngineNatal_ChartLegacyGeneratedHidden" in text for text in texts):
            if len(legacy_matches) < int(max_matches):
                legacy_matches.append(row)

    payload["contains_matches"] = contains_matches
    payload["legacy_flag_matches"] = legacy_matches
    payload["ok"] = True
    return payload


def _resolve_actor_sim_info(resolver):
    actor = None

    # Try resolver participant API first.
    try:
        from interactions import ParticipantType  # type: ignore

        if hasattr(resolver, "get_participant"):
            for participant_name in ("Actor", "Subject", "ActorSim"):
                participant_type = getattr(ParticipantType, participant_name, None)
                if participant_type is None:
                    continue
                try:
                    actor = resolver.get_participant(participant_type)
                except Exception:
                    continue
                if actor is not None:
                    break
    except Exception:
        pass

    # Fallbacks for common resolver fields.
    if actor is None:
        for attr in ("_actor", "actor", "sim", "_sim", "subject"):
            actor = getattr(resolver, attr, None)
            if actor is not None:
                break

    return _coerce_sim_info_candidate(actor)


def _resolve_participant_sim_info(resolver, participant_names: Iterable[str]):
    participant = None

    try:
        from interactions import ParticipantType  # type: ignore

        if hasattr(resolver, "get_participant"):
            for participant_name in participant_names:
                participant_type = getattr(ParticipantType, str(participant_name), None)
                if participant_type is None:
                    continue
                try:
                    participant = resolver.get_participant(participant_type)
                except Exception:
                    continue
                if participant is not None:
                    break
    except Exception:
        pass

    if participant is None:
        for attr in ("_target", "target", "target_sim", "_target_sim", "picked_sim", "_picked_sim", "obj", "_obj"):
            participant = getattr(resolver, attr, None)
            if participant is not None:
                break

    return _coerce_sim_info_candidate(participant)


def _resolve_participant_object(resolver, participant_names: Iterable[str]):
    participant = None

    try:
        from interactions import ParticipantType  # type: ignore

        if hasattr(resolver, "get_participant"):
            for participant_name in participant_names:
                participant_type = getattr(ParticipantType, str(participant_name), None)
                if participant_type is None:
                    continue
                try:
                    participant = resolver.get_participant(participant_type)
                except Exception:
                    continue
                if participant is not None:
                    break
    except Exception:
        pass

    if participant is None:
        for attr in ("picked_object", "_picked_object", "obj", "_obj", "object", "_object"):
            participant = getattr(resolver, attr, None)
            if participant is not None:
                break

    return _coerce_object_candidate(participant)


def _coerce_sim_info_candidate(candidate):
    if candidate is None:
        return None

    sim_info = getattr(candidate, "sim_info", None)
    if sim_info is not None:
        candidate = sim_info

    if _looks_like_sim_info(candidate):
        return candidate
    return None


def _coerce_object_candidate(candidate):
    if candidate is None:
        return None
    if _coerce_sim_info_candidate(candidate) is not None:
        return None
    return candidate


def _looks_like_sim_info(candidate):
    if candidate is None:
        return False

    candidate_type = type(candidate)
    type_name = str(getattr(candidate_type, "__name__", "") or "").lower()
    module_name = str(getattr(candidate_type, "__module__", "") or "").lower()
    if type_name in ("siminfo", "sim_info") or type_name.endswith("siminfo") or "sim_info" in module_name:
        return True

    if getattr(candidate, "sim_id", None) is not None:
        return True

    sim_info_signals = 0
    for attr_name in ("household_id", "age", "trait_tracker", "is_human", "is_teen_or_older"):
        if hasattr(candidate, attr_name):
            sim_info_signals += 1
    return sim_info_signals >= 2 and getattr(candidate, "id", None) is not None


def _sim_display_name(sim_info) -> str:
    first_name = getattr(sim_info, "first_name", None)
    last_name = getattr(sim_info, "last_name", None)
    if first_name or last_name:
        return "{0} {1}".format(first_name or "", last_name or "").strip()
    return str(getattr(sim_info, "full_name", None) or "Sim")


def _sim_id_value(sim_info) -> Optional[int]:
    if sim_info is None:
        return None
    for attr_name in ("sim_id", "id", "guid64", "sim_guid"):
        value = getattr(sim_info, attr_name, None)
        if value is None:
            continue
        try:
            return int(value)
        except Exception:
            continue
    return None


def _coerce_relationship_score_candidate(value) -> Optional[int]:
    if value is None:
        return None
    for attr_name in ("score", "value", "current_value", "relationship_score"):
        attr_value = getattr(value, attr_name, None)
        if attr_value is None:
            continue
        try:
            return int(attr_value)
        except Exception:
            continue
    try:
        return int(value)
    except Exception:
        return None


def _try_read_relationship_track_score(owner, target_sim_id: int, track_id: int) -> Optional[int]:
    if owner is None:
        return None

    for method_name in ("get_relationship_score", "get_relationship_value", "get_track_score"):
        method = getattr(owner, method_name, None)
        if not callable(method):
            continue

        call_specs = (
            (((int(target_sim_id), int(track_id))), {}),
            (((int(target_sim_id),)), {"track_id": int(track_id)}),
            (((int(target_sim_id),)), {"track": int(track_id)}),
        )
        for args, kwargs in call_specs:
            try:
                value = method(*args, **kwargs)
            except TypeError:
                continue
            except Exception:
                continue

            score = _coerce_relationship_score_candidate(value)
            if score is not None:
                return score
    return None


def _resolve_relationship_score_summary(actor_sim_info, target_sim_info) -> Dict[str, object]:
    summary = {
        "scores": {},
        "track_ids": {},
        "source_owners": {},
    }
    actor_sim_id = _sim_id_value(actor_sim_info)
    target_sim_id = _sim_id_value(target_sim_info)
    if (
        actor_sim_info is None
        or target_sim_info is None
        or actor_sim_id is None
        or target_sim_id is None
    ):
        return summary

    for source_track, track_id in (
        ("friendship", _LTR_FRIENDSHIP_MAIN_TRACK_ID),
        ("romance", _LTR_ROMANCE_MAIN_TRACK_ID),
    ):
        resolved_score = None
        resolved_source_owner = None
        for source_owner, sim_info, other_sim_id in (
            ("actor", actor_sim_info, target_sim_id),
            ("target", target_sim_info, actor_sim_id),
        ):
            for owner in (getattr(sim_info, "relationship_tracker", None), sim_info):
                score = _try_read_relationship_track_score(owner, other_sim_id, track_id)
                if score is None:
                    continue
                resolved_score = int(score)
                resolved_source_owner = str(source_owner)
                break
            if resolved_score is not None:
                break

        if resolved_score is None:
            continue
        summary["scores"][str(source_track)] = resolved_score
        summary["track_ids"][str(source_track)] = int(track_id)
        summary["source_owners"][str(source_track)] = resolved_source_owner
    return summary


def _sync_actor_rising_chemistry_buffs(sim_info, buff_plan) -> Dict[str, object]:
    summary = {
        "ok": False,
        "reason": None,
        "removed_buff_ids": [],
        "removed_count": 0,
        "applied_buff_id": None,
        "buff_added": 0,
        "buff_already_present": 0,
    }
    if sim_info is None:
        summary["reason"] = "missing_actor"
        return summary

    if isinstance(buff_plan, dict):
        try:
            target_buff_id = int(buff_plan.get("managed_buff_id"))
        except Exception:
            target_buff_id = None
    else:
        target_buff_id = None

    if not isinstance(buff_plan, dict) or not bool(buff_plan.get("ok")):
        summary["reason"] = (
            str(buff_plan.get("reason"))
            if isinstance(buff_plan, dict) and buff_plan.get("reason")
            else "missing_buff_plan"
        )
        return summary

    if target_buff_id is None:
        summary["reason"] = "missing_buff_id"
        return summary
    summary["applied_buff_id"] = int(target_buff_id)
    if _resolve_buff(int(target_buff_id)) is None:
        summary["reason"] = "missing_buff_resource"
        return summary

    try:
        from .rising_chemistry import iter_actor_rising_chemistry_managed_buff_ids
    except Exception:
        iter_actor_rising_chemistry_managed_buff_ids = None

    managed_buff_ids = (
        tuple(int(buff_id) for buff_id in iter_actor_rising_chemistry_managed_buff_ids())
        if callable(iter_actor_rising_chemistry_managed_buff_ids)
        else ()
    )

    for buff_id in managed_buff_ids:
        if int(buff_id) == int(target_buff_id):
            continue
        if not _sim_has_buff(sim_info, int(buff_id)):
            continue
        if _remove_buff_if_present(sim_info, int(buff_id)):
            summary["removed_buff_ids"].append(int(buff_id))

    summary["removed_count"] = len(summary["removed_buff_ids"])
    if _sim_has_buff(sim_info, int(target_buff_id)):
        summary["buff_already_present"] = 1
        summary["reason"] = "kept_existing"
        summary["ok"] = True
        return summary
    if _add_buff_if_missing(sim_info, int(target_buff_id)):
        summary["buff_added"] = 1
        summary["reason"] = "added"
        summary["ok"] = True
        return summary
    summary["reason"] = "add_failed"
    return summary


def _try_has_relationship_bit(owner, target_sim_id: int, bit_id: int) -> Optional[bool]:
    if owner is None:
        return None

    for method_name in (
        "has_relationship_bit",
        "has_bit",
        "relationship_has_bit",
        "has_relbit",
        "get_relationship_bit",
        "get_bit",
    ):
        method = getattr(owner, method_name, None)
        if not callable(method):
            continue

        call_specs = (
            (((int(target_sim_id), int(bit_id))), {}),
            (((int(target_sim_id),)), {"bit_id": int(bit_id)}),
            (((int(target_sim_id),)), {"bit": int(bit_id)}),
        )
        for args, kwargs in call_specs:
            try:
                value = method(*args, **kwargs)
            except TypeError:
                continue
            except Exception:
                continue

            if value is None:
                continue
            if isinstance(value, bool):
                return bool(value)
            try:
                return bool(int(value))
            except Exception:
                return True
    return None


def _try_add_relationship_bit(owner, target_sim_id: int, bit_id: int) -> Optional[bool]:
    if owner is None:
        return None

    for method_name in (
        "add_relationship_bit",
        "add_bit",
        "relationship_add_bit",
        "add_relbit",
    ):
        method = getattr(owner, method_name, None)
        if not callable(method):
            continue

        call_specs = (
            (((int(target_sim_id), int(bit_id))), {}),
            (((int(target_sim_id),)), {"bit_id": int(bit_id)}),
            (((int(target_sim_id),)), {"bit": int(bit_id)}),
        )
        for args, kwargs in call_specs:
            try:
                value = method(*args, **kwargs)
            except TypeError:
                continue
            except Exception:
                continue

            if value is None:
                return True
            if isinstance(value, bool):
                return bool(value)
            try:
                return bool(int(value))
            except Exception:
                return True
    return None


def _try_remove_relationship_bit(owner, target_sim_id: int, bit_id: int) -> Optional[bool]:
    if owner is None:
        return None

    for method_name in (
        "remove_relationship_bit",
        "remove_bit",
        "relationship_remove_bit",
        "remove_relbit",
    ):
        method = getattr(owner, method_name, None)
        if not callable(method):
            continue

        call_specs = (
            (((int(target_sim_id), int(bit_id))), {}),
            (((int(target_sim_id),)), {"bit_id": int(bit_id)}),
            (((int(target_sim_id),)), {"bit": int(bit_id)}),
        )
        for args, kwargs in call_specs:
            try:
                value = method(*args, **kwargs)
            except TypeError:
                continue
            except Exception:
                continue

            if value is None:
                return True
            if isinstance(value, bool):
                return bool(value)
            try:
                return bool(int(value))
            except Exception:
                return True
    return None


def _iter_relationship_target_ids(sim_info) -> Iterable[int]:
    tracker = getattr(sim_info, "relationship_tracker", None)
    if tracker is None:
        return ()

    target_ids = []
    seen = set()

    def _append_target_id(value) -> None:
        try:
            target_id = int(value)
        except Exception:
            return
        if target_id in seen:
            return
        seen.add(target_id)
        target_ids.append(target_id)

    for attr_name in (
        "present_relbits_by_target",
        "_relationships",
        "relationships",
        "_relationship_data",
        "relationship_data",
    ):
        value = getattr(tracker, attr_name, None)
        if isinstance(value, dict):
            for target_id in value.keys():
                _append_target_id(target_id)

    for method_name in ("keys", "get_target_sim_ids", "get_all_target_sim_ids"):
        method = getattr(tracker, method_name, None)
        if not callable(method):
            continue
        try:
            values = method()
        except TypeError:
            continue
        except Exception:
            continue
        try:
            for target_id in values:
                _append_target_id(target_id)
        except Exception:
            continue

    return tuple(target_ids)


def _single_direction_has_relationship_bit(source_sim_info, target_sim_info, bit_id: int) -> bool:
    source_sim_id = _sim_id_value(source_sim_info)
    target_sim_id = _sim_id_value(target_sim_info)
    if source_sim_info is None or source_sim_id is None or target_sim_id is None:
        return False

    for owner in (getattr(source_sim_info, "relationship_tracker", None), source_sim_info):
        has_bit = _try_has_relationship_bit(owner, int(target_sim_id), int(bit_id))
        if has_bit is not None:
            return bool(has_bit)
    return False


def _pair_has_relbit(actor_sim_info, target_sim_info, relbit_id: int) -> bool:
    return bool(
        _single_direction_has_relationship_bit(actor_sim_info, target_sim_info, int(relbit_id))
        and _single_direction_has_relationship_bit(target_sim_info, actor_sim_info, int(relbit_id))
    )


def _write_relationship_bit_if_missing(source_sim_info, target_sim_info, bit_id: int) -> bool:
    source_sim_id = _sim_id_value(source_sim_info)
    target_sim_id = _sim_id_value(target_sim_info)
    if source_sim_info is None or source_sim_id is None or target_sim_id is None:
        return False
    if _single_direction_has_relationship_bit(source_sim_info, target_sim_info, int(bit_id)):
        return False

    for owner in (getattr(source_sim_info, "relationship_tracker", None), source_sim_info):
        added = _try_add_relationship_bit(owner, int(target_sim_id), int(bit_id))
        if added is not None:
            return bool(added)
    return False


def _write_pair_relbit(actor_sim_info, target_sim_info, relbit_id: int) -> bool:
    relbit_id = int(relbit_id)
    actor_had_bit = _single_direction_has_relationship_bit(actor_sim_info, target_sim_info, relbit_id)
    target_had_bit = _single_direction_has_relationship_bit(target_sim_info, actor_sim_info, relbit_id)
    _write_relationship_bit_if_missing(actor_sim_info, target_sim_info, relbit_id)
    _write_relationship_bit_if_missing(target_sim_info, actor_sim_info, relbit_id)
    if _pair_has_relbit(actor_sim_info, target_sim_info, int(relbit_id)):
        return True
    actor_target_sim_id = _sim_id_value(target_sim_info)
    target_actor_sim_id = _sim_id_value(actor_sim_info)
    if actor_target_sim_id is not None and not actor_had_bit:
        _remove_relationship_bit_if_present(actor_sim_info, int(actor_target_sim_id), relbit_id)
    if target_actor_sim_id is not None and not target_had_bit:
        _remove_relationship_bit_if_present(target_sim_info, int(target_actor_sim_id), relbit_id)
    return False


def _remove_relationship_bit_if_present(source_sim_info, target_sim_id: int, bit_id: int) -> bool:
    source_sim_id = _sim_id_value(source_sim_info)
    if source_sim_info is None or source_sim_id is None:
        return False
    has_bit = None
    for owner in (getattr(source_sim_info, "relationship_tracker", None), source_sim_info):
        has_bit = _try_has_relationship_bit(owner, int(target_sim_id), int(bit_id))
        if has_bit is not None:
            break
    if not bool(has_bit):
        return False

    for owner in (getattr(source_sim_info, "relationship_tracker", None), source_sim_info):
        removed = _try_remove_relationship_bit(owner, int(target_sim_id), int(bit_id))
        if removed is not None:
            return bool(removed)
    return False


def _clear_actor_pair_relbit(actor_sim_info, relbit_id) -> int:
    removed_count = 0
    if actor_sim_info is None:
        return 0

    def _resolve_target_sim_info(target_sim_id: int):
        try:
            sim_infos = tuple(_iter_all_sim_infos())
        except Exception:
            sim_infos = ()
        for sim_info in sim_infos:
            if _sim_id_value(sim_info) == int(target_sim_id):
                return sim_info
        return None

    for target_sim_id in _iter_relationship_target_ids(actor_sim_info):
        if _remove_relationship_bit_if_present(actor_sim_info, int(target_sim_id), int(relbit_id)):
            removed_count += 1
        target_sim_info = _resolve_target_sim_info(int(target_sim_id))
        actor_sim_id = _sim_id_value(actor_sim_info)
        if target_sim_info is not None and actor_sim_id is not None:
            if _remove_relationship_bit_if_present(target_sim_info, int(actor_sim_id), int(relbit_id)):
                removed_count += 1
    return int(removed_count)


def _clear_known_chemistry_pair_memory_from_actor(actor_sim_info, layer_name) -> Dict[str, object]:
    summary = {
        "ok": False,
        "reason": None,
        "actor_sim_id": _sim_id_value(actor_sim_info),
        "layer_name": str(layer_name or "").strip().lower(),
        "requested_relbit_ids": [],
        "relationship_target_ids": [],
        "removed_relbit_ids": [],
        "removed_count": 0,
    }
    if actor_sim_info is None:
        summary["reason"] = "missing_actor"
        return summary

    try:
        from .chemistry_pair_memory import iter_relbit_ids_for_layer
    except Exception:
        summary["reason"] = "missing_pair_memory_helper"
        return summary

    requested_relbit_ids = [int(relbit_id) for relbit_id in iter_relbit_ids_for_layer(layer_name)]
    summary["requested_relbit_ids"] = list(requested_relbit_ids)
    if not requested_relbit_ids:
        summary["reason"] = "missing_layer"
        return summary

    target_ids = list(_iter_relationship_target_ids(actor_sim_info))
    summary["relationship_target_ids"] = list(target_ids)

    for relbit_id in requested_relbit_ids:
        removed_count = _clear_actor_pair_relbit(actor_sim_info, int(relbit_id))
        if removed_count <= 0:
            continue
        summary["removed_relbit_ids"].extend([int(relbit_id)] * int(removed_count))

    summary["removed_count"] = len(summary["removed_relbit_ids"])
    summary["ok"] = True
    summary["reason"] = "cleared"
    return summary


def _normalize_sign_compatibility_lane_name(lane_name) -> Optional[str]:
    text = str(lane_name or "").strip().lower()
    if text == "sun":
        return "Sun"
    if text == "moon":
        return "Moon"
    if text == "rising":
        return "Rising"
    return None


def _iter_sign_compatibility_relbit_ids_for_lane(lane_name) -> Iterable[int]:
    try:
        from .sign_compatibility_relbits import RELBIT_ID_BY_LANE_STATE, STATE_NAMES
    except Exception:
        return ()
    normalized_lane_name = _normalize_sign_compatibility_lane_name(lane_name)
    if normalized_lane_name is None:
        return ()
    lane_mapping = RELBIT_ID_BY_LANE_STATE.get(normalized_lane_name, {})
    return tuple(int(lane_mapping[state_name]) for state_name in STATE_NAMES if state_name in lane_mapping)


def _iter_sign_compatibility_visible_buff_ids_for_lane(lane_name) -> Iterable[int]:
    try:
        from .sign_compatibility_relbits import STATE_NAMES, VISIBLE_BUFF_ID_BY_LANE_STATE
    except Exception:
        return ()
    normalized_lane_name = _normalize_sign_compatibility_lane_name(lane_name)
    if normalized_lane_name is None:
        return ()
    lane_mapping = VISIBLE_BUFF_ID_BY_LANE_STATE.get(normalized_lane_name, {})
    return tuple(int(lane_mapping[state_name]) for state_name in STATE_NAMES if state_name in lane_mapping)


def _clear_sign_compatibility_visible_buffs_for_lane(sim_info, lane_name) -> Dict[str, object]:
    summary = {
        "ok": False,
        "reason": None,
        "lane_name": _normalize_sign_compatibility_lane_name(lane_name),
        "removed_buff_ids": [],
        "removed_count": 0,
    }
    normalized_lane_name = summary["lane_name"]
    if sim_info is None:
        summary["reason"] = "missing_actor"
        return summary
    if normalized_lane_name is None:
        summary["reason"] = "missing_lane"
        return summary

    for buff_id in _iter_sign_compatibility_visible_buff_ids_for_lane(normalized_lane_name):
        if not _sim_has_buff(sim_info, int(buff_id)):
            continue
        if _remove_buff_if_present(sim_info, int(buff_id)):
            summary["removed_buff_ids"].append(int(buff_id))

    summary["removed_count"] = len(summary["removed_buff_ids"])
    summary["ok"] = True
    summary["reason"] = "cleared"
    return summary


def _clear_sign_compatibility_runtime_lane_state_from_actor(actor_sim_info, lane_name) -> Dict[str, object]:
    summary = {
        "ok": False,
        "reason": None,
        "actor_sim_id": _sim_id_value(actor_sim_info),
        "lane_name": _normalize_sign_compatibility_lane_name(lane_name),
        "requested_relbit_ids": [],
        "removed_relbit_ids": [],
        "removed_relbit_count": 0,
        "visible_buff_clear_summary": {},
    }
    normalized_lane_name = summary["lane_name"]
    if actor_sim_info is None:
        summary["reason"] = "missing_actor"
        return summary
    if normalized_lane_name is None:
        summary["reason"] = "missing_lane"
        return summary

    requested_relbit_ids = list(_iter_sign_compatibility_relbit_ids_for_lane(normalized_lane_name))
    summary["requested_relbit_ids"] = list(requested_relbit_ids)
    for relbit_id in requested_relbit_ids:
        removed_count = _clear_actor_pair_relbit(actor_sim_info, int(relbit_id))
        if removed_count <= 0:
            continue
        summary["removed_relbit_ids"].append(int(relbit_id))

    summary["removed_relbit_count"] = len(summary["removed_relbit_ids"])
    visible_buff_clear_summary = _clear_sign_compatibility_visible_buffs_for_lane(
        actor_sim_info,
        normalized_lane_name,
    )
    summary["visible_buff_clear_summary"] = dict(visible_buff_clear_summary)
    summary["ok"] = True
    summary["reason"] = "cleared"
    return summary


def _resolve_pair_sign_compatibility_state(actor_sim_info, target_sim_info, lane_name) -> Optional[str]:
    try:
        from .sign_compatibility_relbits import RELBIT_ID_BY_LANE_STATE, STATE_NAMES
    except Exception:
        return None
    normalized_lane_name = _normalize_sign_compatibility_lane_name(lane_name)
    if normalized_lane_name is None:
        return None
    lane_mapping = RELBIT_ID_BY_LANE_STATE.get(normalized_lane_name, {})
    for state_name in STATE_NAMES:
        relbit_id = lane_mapping.get(state_name)
        if relbit_id is None:
            continue
        if _pair_has_relbit(actor_sim_info, target_sim_info, int(relbit_id)):
            return str(state_name)
    return None


def _build_sign_compatibility_chart_for_sim(sim_info) -> Optional[Dict[str, int]]:
    payload = _resolve_live_sign_compatibility_chart_payload(sim_info)
    return dict(payload) if isinstance(payload, dict) else None


def _resolve_live_sign_compatibility_chart_payload(sim_info) -> Optional[Dict[str, int]]:
    sim_id = _sim_id_value(sim_info)
    payload = _chart_payload_for_sim(int(sim_id), sim_info=sim_info) if sim_id is not None else None
    chart = {}
    if isinstance(payload, dict):
        for sign_key in ("sun_sign_index", "moon_sign_index", "rising_sign_index"):
            sign_index = payload.get(sign_key)
            if isinstance(sign_index, int):
                chart[str(sign_key)] = int(sign_index) % len(_ZODIAC_SIGNS)

    traits = _iter_traits_for_sim_info(sim_info)
    sun_sign_name = _extract_sign_from_traits(traits, "Sun")
    if sun_sign_name in _ZODIAC_SIGNS:
        chart["sun_sign_index"] = _ZODIAC_SIGNS.index(str(sun_sign_name))

    moon_sign_name = _extract_sign_from_traits(traits, "Moon")
    if moon_sign_name in _ZODIAC_SIGNS:
        chart["moon_sign_index"] = _ZODIAC_SIGNS.index(str(moon_sign_name))

    rising_sign_index, _rising_sign_name = _resolve_rising_sign_index_and_name(sim_info)
    if rising_sign_index is not None:
        chart["rising_sign_index"] = int(rising_sign_index) % len(_ZODIAC_SIGNS)
    return chart if chart else None


def _seed_pair_sign_compatibility_relbits(actor_sim_info, target_sim_info) -> Dict[str, object]:
    summary = {
        "ok": False,
        "reason": None,
        "actor_sim_id": _sim_id_value(actor_sim_info),
        "target_sim_id": _sim_id_value(target_sim_info),
        "actor_chart": {},
        "target_chart": {},
        "lanes": {},
        "written_relbit_ids": [],
        "written_lanes": [],
        "already_known_lanes": [],
    }
    if actor_sim_info is None or target_sim_info is None:
        summary["reason"] = "missing_pair"
        return summary
    try:
        from .sign_compatibility_relbits import build_pair_relbit_seed_plan
    except Exception:
        summary["reason"] = "missing_relbit_helper"
        return summary

    actor_chart = _build_sign_compatibility_chart_for_sim(actor_sim_info) or {}
    target_chart = _build_sign_compatibility_chart_for_sim(target_sim_info) or {}
    summary["actor_chart"] = dict(actor_chart)
    summary["target_chart"] = dict(target_chart)

    plan = build_pair_relbit_seed_plan(actor_chart=actor_chart, target_chart=target_chart)
    summary["plan"] = dict(plan) if isinstance(plan, dict) else {}
    if not isinstance(plan, dict) or not plan.get("ok"):
        summary["reason"] = "missing_big3"
        return summary

    for lane_name, lane_payload in (plan.get("lanes") or {}).items():
        existing_state = _resolve_pair_sign_compatibility_state(
            actor_sim_info,
            target_sim_info,
            lane_name,
        )
        lane_summary = dict(lane_payload)
        lane_summary["existing_state"] = existing_state
        if existing_state is not None:
            lane_summary["write_ok"] = False
            lane_summary["reason"] = "already_known"
            summary["already_known_lanes"].append(str(lane_name))
            summary["lanes"][str(lane_name)] = lane_summary
            continue
        write_ok = _write_pair_relbit(
            actor_sim_info,
            target_sim_info,
            int(lane_payload.get("relbit_id")),
        )
        lane_summary["write_ok"] = bool(write_ok)
        lane_summary["reason"] = "written" if write_ok else "write_failed"
        summary["lanes"][str(lane_name)] = lane_summary
        if write_ok:
            summary["written_lanes"].append(str(lane_name))
            summary["written_relbit_ids"].append(int(lane_payload.get("relbit_id")))

    summary["ok"] = True
    summary["reason"] = "resolved"
    return summary


def _sync_actor_sign_compatibility_visible_buffs(actor_sim_info, target_sim_info) -> Dict[str, object]:
    summary = {
        "ok": False,
        "reason": None,
        "actor_sim_id": _sim_id_value(actor_sim_info),
        "target_sim_id": _sim_id_value(target_sim_info),
        "lanes": {},
    }
    if actor_sim_info is None:
        summary["reason"] = "missing_actor"
        return summary
    try:
        from .sign_compatibility_relbits import STATE_NAMES, VISIBLE_BUFF_ID_BY_LANE_STATE
    except Exception:
        summary["reason"] = "missing_relbit_helper"
        return summary

    overall_ok = True
    for lane_name in ("Sun", "Moon", "Rising"):
        state_name = _resolve_pair_sign_compatibility_state(
            actor_sim_info,
            target_sim_info,
            lane_name,
        )
        lane_summary = {
            "lane_name": lane_name,
            "state": state_name,
            "removed_buff_ids": [],
            "removed_count": 0,
            "applied_buff_id": None,
            "buff_added": 0,
            "buff_already_present": 0,
            "ok": True,
            "reason": None,
        }
        lane_mapping = VISIBLE_BUFF_ID_BY_LANE_STATE.get(lane_name, {})
        target_buff_id = lane_mapping.get(state_name) if state_name is not None else None
        for visible_state_name in STATE_NAMES:
            buff_id = lane_mapping.get(visible_state_name)
            if buff_id is None or int(buff_id) == int(target_buff_id or 0):
                continue
            if not _sim_has_buff(actor_sim_info, int(buff_id)):
                continue
            if _remove_buff_if_present(actor_sim_info, int(buff_id)):
                lane_summary["removed_buff_ids"].append(int(buff_id))
        lane_summary["removed_count"] = len(lane_summary["removed_buff_ids"])

        if target_buff_id is None:
            lane_summary["reason"] = "missing_relbit"
            summary["lanes"][lane_name] = lane_summary
            continue

        lane_summary["applied_buff_id"] = int(target_buff_id)
        if _resolve_buff(int(target_buff_id)) is None:
            lane_summary["ok"] = False
            lane_summary["reason"] = "missing_buff_resource"
            overall_ok = False
            summary["lanes"][lane_name] = lane_summary
            continue
        if _sim_has_buff(actor_sim_info, int(target_buff_id)):
            lane_summary["buff_already_present"] = 1
            lane_summary["reason"] = "kept_existing"
            summary["lanes"][lane_name] = lane_summary
            continue
        if _add_buff_if_missing(actor_sim_info, int(target_buff_id)):
            lane_summary["buff_added"] = 1
            lane_summary["reason"] = "added"
            summary["lanes"][lane_name] = lane_summary
            continue
        lane_summary["ok"] = False
        lane_summary["reason"] = "add_failed"
        overall_ok = False
        summary["lanes"][lane_name] = lane_summary

    summary["ok"] = overall_ok
    summary["reason"] = "resolved" if overall_ok else "partial_failure"
    return summary


def _build_pair_memory_known_state_summary(actor_sim_info, target_sim_info) -> Dict[str, object]:
    try:
        from .chemistry_pair_memory import RISING_KNOWN_RELBIT_ID, SUN_KNOWN_RELBIT_ID
    except Exception:
        return {
            "ok": False,
            "reason": "missing_pair_memory_helper",
            "rising_known": False,
            "sun_known": False,
            "rising_known_relbit_id": None,
            "sun_known_relbit_id": None,
        }

    rising_relbit_id = int(RISING_KNOWN_RELBIT_ID)
    sun_relbit_id = int(SUN_KNOWN_RELBIT_ID)
    return {
        "ok": True,
        "reason": "resolved",
        "rising_known": _pair_has_relbit(actor_sim_info, target_sim_info, rising_relbit_id),
        "sun_known": _pair_has_relbit(actor_sim_info, target_sim_info, sun_relbit_id),
        "rising_known_relbit_id": rising_relbit_id,
        "sun_known_relbit_id": sun_relbit_id,
    }


def _resolve_rising_sign_index_and_name(sim_info) -> Tuple[Optional[int], Optional[str]]:
    try:
        from .houses_notification_bridge import resolve_rising_sign_index_from_trait_ids
    except Exception:
        return (None, None)

    trait_ids, _marker_trait_ids = _collect_trait_ids_and_markers(sim_info)
    rising_sign_index = resolve_rising_sign_index_from_trait_ids(trait_ids)
    if rising_sign_index is None:
        return (None, None)
    rising_sign_index = int(rising_sign_index) % len(SIGNS)
    return (rising_sign_index, SIGNS[rising_sign_index])


def _resolve_sun_sign_index_and_name(sim_info) -> Tuple[Optional[int], Optional[str]]:
    sim_id = _sim_id_value(sim_info)
    payload = _chart_payload_for_sim(int(sim_id), sim_info=sim_info) if sim_id is not None else None
    sun_sign_index = payload.get("sun_sign_index") if isinstance(payload, dict) else None
    if isinstance(sun_sign_index, int):
        normalized_index = int(sun_sign_index) % len(_ZODIAC_SIGNS)
        return (normalized_index, _ZODIAC_SIGNS[normalized_index])

    sign_name = _extract_sign_from_traits(_iter_traits_for_sim_info(sim_info), "Sun")
    if sign_name not in _ZODIAC_SIGNS:
        return (None, None)
    normalized_index = _ZODIAC_SIGNS.index(sign_name)
    return (normalized_index, sign_name)


def _resolve_active_sun_chemistry_tier_name(actor_sim_info, target_sim_info) -> Optional[str]:
    try:
        from .sun_chemistry import iter_sun_relbit_id_pairs
    except Exception:
        iter_sun_relbit_id_pairs = None
    actor_sim_id = _sim_id_value(actor_sim_info)
    target_sim_id = _sim_id_value(target_sim_info)
    if (
        actor_sim_info is None
        or target_sim_info is None
        or actor_sim_id is None
        or target_sim_id is None
        or not callable(iter_sun_relbit_id_pairs)
    ):
        return None
    for tier_name, relbit_id in iter_sun_relbit_id_pairs():
        for sim_info, other_sim_id in (
            (actor_sim_info, target_sim_id),
            (target_sim_info, actor_sim_id),
        ):
            for owner in (getattr(sim_info, "relationship_tracker", None), sim_info):
                has_bit = _try_has_relationship_bit(owner, other_sim_id, int(relbit_id))
                if has_bit:
                    return str(tier_name)
    return None


def _sync_actor_sun_chemistry_overlay_buffs(sim_info, buff_plan) -> Dict[str, object]:
    summary = {
        "ok": False,
        "reason": None,
        "removed_buff_ids": [],
        "removed_count": 0,
        "applied_buff_id": None,
        "buff_added": 0,
        "buff_already_present": 0,
    }
    if sim_info is None:
        summary["reason"] = "missing_actor"
        return summary

    try:
        from .sun_chemistry import iter_sun_overlay_buff_ids
    except Exception:
        iter_sun_overlay_buff_ids = None

    managed_buff_ids = (
        tuple(int(buff_id) for buff_id in iter_sun_overlay_buff_ids())
        if callable(iter_sun_overlay_buff_ids)
        else ()
    )

    buff_plan_dict = buff_plan if isinstance(buff_plan, dict) else None

    target_buff_id = buff_plan_dict.get("overlay_buff_id") if buff_plan_dict is not None else None
    try:
        target_buff_id = int(target_buff_id) if target_buff_id is not None else None
    except Exception:
        target_buff_id = None

    plan_ok = bool(buff_plan_dict.get("ok")) if buff_plan_dict is not None else False
    if not plan_ok:
        target_buff_id = None

    if target_buff_id is not None:
        summary["applied_buff_id"] = int(target_buff_id)

    for buff_id in managed_buff_ids:
        if target_buff_id is not None and int(buff_id) == int(target_buff_id):
            continue
        if not _sim_has_buff(sim_info, int(buff_id)):
            continue
        if _remove_buff_if_present(sim_info, int(buff_id)):
            summary["removed_buff_ids"].append(int(buff_id))

    summary["removed_count"] = len(summary["removed_buff_ids"])
    if target_buff_id is not None and _resolve_buff(int(target_buff_id)) is None:
        summary["reason"] = "missing_buff_resource"
        return summary
    if not plan_ok:
        summary["reason"] = (
            str(buff_plan_dict.get("reason"))
            if buff_plan_dict is not None and buff_plan_dict.get("reason")
            else "missing_buff_plan"
        )
        return summary
    if target_buff_id is None:
        summary["ok"] = True
        summary["reason"] = "base_only"
        return summary
    if _sim_has_buff(sim_info, int(target_buff_id)):
        summary["buff_already_present"] = 1
        summary["reason"] = "kept_existing"
        summary["ok"] = True
        return summary
    if _add_buff_if_missing(sim_info, int(target_buff_id)):
        summary["buff_added"] = 1
        summary["reason"] = "added"
        summary["ok"] = True
        return summary
    summary["reason"] = "add_failed"
    return summary


def _sim_household_id(sim_info) -> Optional[int]:
    if sim_info is None:
        return None
    household_id = getattr(sim_info, "household_id", None)
    if household_id is None:
        household = getattr(sim_info, "household", None)
        household_id = getattr(household, "id", None) if household is not None else None
    if household_id is None:
        return None
    try:
        return int(household_id)
    except Exception:
        return None


def _is_teen_plus_sim_info(sim_info) -> bool:
    return sim_info_is_teen_plus(sim_info)


def _collect_visible_big3_status(sim_info) -> Dict[str, object]:
    status = {
        "eligible": 0,
        "has_visible_rising": 0,
        "has_visible_sun": 0,
        "has_visible_moon": 0,
        "complete": 0,
    }
    if sim_info is None:
        return status

    status["eligible"] = 1 if _is_teen_plus_sim_info(sim_info) else 0

    parse_visible_sign_reward_trait_name = None
    try:
        from .natal_snapshot_markers import _parse_visible_sign_reward_trait_name

        parse_visible_sign_reward_trait_name = _parse_visible_sign_reward_trait_name
    except Exception:
        parse_visible_sign_reward_trait_name = None

    visible_rising_ids = frozenset(int(v) for v in _VISIBLE_RISING_SIGN_INDEX_TO_TRAIT_ID.values())
    for trait in _iter_traits_for_sim_info(sim_info):
        trait_id = _trait_guid64(trait)
        if trait_id is not None:
            try:
                if int(trait_id) in visible_rising_ids:
                    status["has_visible_rising"] = 1
            except Exception:
                pass

        parsed = None
        if callable(parse_visible_sign_reward_trait_name):
            try:
                parsed = parse_visible_sign_reward_trait_name(_trait_name(trait))
            except Exception:
                parsed = None
        if parsed is None:
            continue

        body_name = str(parsed[0])
        if body_name == "Sun":
            status["has_visible_sun"] = 1
        elif body_name == "Moon":
            status["has_visible_moon"] = 1

    status["complete"] = 1 if (
        status["eligible"]
        and status["has_visible_rising"]
        and status["has_visible_sun"]
        and status["has_visible_moon"]
    ) else 0
    return status


def _iter_household_sim_infos(anchor_sim_info) -> Iterable[object]:
    if anchor_sim_info is None:
        return ()

    out: List[object] = []
    seen_keys: set = set()
    target_household_id = _sim_household_id(anchor_sim_info)

    def _append(candidate) -> None:
        sim_info = getattr(candidate, "sim_info", None) or candidate
        if sim_info is None:
            return
        if target_household_id is not None and _sim_household_id(sim_info) != int(target_household_id):
            return
        key = _sim_id_value(sim_info)
        if key is None:
            key = id(sim_info)
        if key in seen_keys:
            return
        seen_keys.add(key)
        out.append(sim_info)

    household = getattr(anchor_sim_info, "household", None)
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

    try:
        import services  # type: ignore
    except Exception:
        services = None
    if services is not None:
        sim_info_manager_fn = getattr(services, "sim_info_manager", None)
        if callable(sim_info_manager_fn):
            try:
                sim_info_manager = sim_info_manager_fn()
            except Exception:
                sim_info_manager = None
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
        _append(anchor_sim_info)
    return tuple(out)


def _iter_all_sim_infos() -> Iterable[object]:
    out: List[object] = []
    seen_keys: set = set()

    def _append(candidate) -> None:
        sim_info = getattr(candidate, "sim_info", None) or candidate
        if sim_info is None:
            return
        key = _sim_id_value(sim_info)
        if key is None:
            key = id(sim_info)
        if key in seen_keys:
            return
        seen_keys.add(key)
        out.append(sim_info)

    try:
        import services  # type: ignore
    except Exception:
        services = None
    if services is not None:
        sim_info_manager_fn = getattr(services, "sim_info_manager", None)
        if callable(sim_info_manager_fn):
            try:
                sim_info_manager = sim_info_manager_fn()
            except Exception:
                sim_info_manager = None
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


def _sim_info_is_human_runtime(sim_info) -> bool:
    return sim_info_is_human(sim_info)


def clear_simstrology_state_from_non_humans() -> Dict[str, object]:
    summary = {
        "sims_seen": 0,
        "non_humans_seen": 0,
        "base_remove_loot_runs": 0,
        "house_traits_removed": 0,
        "house_reward_traits_removed": 0,
        "house_buffs_removed": 0,
        "retrograde_traits_removed": 0,
        "retrograde_buffs_removed": 0,
        "retrograde_intense_buffs_removed": 0,
        "sim_ids_cleared": [],
    }

    try:
        from .planet_house_markers import (
            _clear_managed_house_traits_for_non_human,
            _marker_cache as _planet_marker_cache,
        )
    except Exception:
        _clear_managed_house_traits_for_non_human = None
        _planet_marker_cache = None

    try:
        from .retrograde_markers import (
            _clear_retrograde_state_for_non_human,
            _expression_cache as _retrograde_expression_cache,
            _marker_cache as _retrograde_marker_cache,
            _run_loot_on_sim_info,
        )
    except Exception:
        _clear_retrograde_state_for_non_human = None
        _retrograde_expression_cache = None
        _retrograde_marker_cache = None
        _run_loot_on_sim_info = None

    planet_cache = _planet_marker_cache() if callable(_planet_marker_cache) else {}
    retrograde_marker_cache = _retrograde_marker_cache() if callable(_retrograde_marker_cache) else {}
    retrograde_expression_cache = (
        _retrograde_expression_cache() if callable(_retrograde_expression_cache) else {}
    )

    for sim_info in _iter_all_sim_infos():
        summary["sims_seen"] += 1
        if _sim_info_is_human_runtime(sim_info):
            continue

        summary["non_humans_seen"] += 1
        sim_id = _sim_id_value(sim_info)

        if callable(_run_loot_on_sim_info) and _run_loot_on_sim_info(
            sim_info,
            int(_REMOVE_ALL_SIMSTROLOGY_STATE_LOOT_ID),
        ):
            summary["base_remove_loot_runs"] += 1

        trait_tracker = getattr(sim_info, "trait_tracker", None)
        if callable(_clear_managed_house_traits_for_non_human) and trait_tracker is not None:
            house_cleanup = _clear_managed_house_traits_for_non_human(
                sim_info,
                trait_tracker,
                candidate_ids_by_body=planet_cache.get("candidate_ids_by_body", {}),
                visible_reward_ids_by_body=planet_cache.get("visible_reward_ids_by_body", {}),
                managed_buff_ids={
                    int(buff_id)
                    for buff_id in dict(planet_cache.get("buff_id_by_body_house", {})).values()
                },
            )
            summary["house_traits_removed"] += int(house_cleanup.get("traits_removed", 0) or 0)
            summary["house_reward_traits_removed"] += int(
                house_cleanup.get("reward_traits_removed", 0) or 0
            )
            summary["house_buffs_removed"] += int(house_cleanup.get("buffs_removed", 0) or 0)

        if callable(_clear_retrograde_state_for_non_human):
            retrograde_summary = {
                "traits_removed": 0,
                "buffs_removed": 0,
                "intense_buffs_removed": 0,
                "dispatch_failures": 0,
            }
            _clear_retrograde_state_for_non_human(
                sim_info,
                trait_tracker=trait_tracker,
                candidate_ids_by_body=retrograde_marker_cache.get("candidate_ids_by_body", {}),
                base_buff_by_body=retrograde_expression_cache.get("base_by_body", {}),
                intense_buff_by_body=retrograde_expression_cache.get("intense_by_body", {}),
                summary=retrograde_summary,
            )
            summary["retrograde_traits_removed"] += int(retrograde_summary.get("traits_removed", 0) or 0)
            summary["retrograde_buffs_removed"] += int(retrograde_summary.get("buffs_removed", 0) or 0)
            summary["retrograde_intense_buffs_removed"] += int(
                retrograde_summary.get("intense_buffs_removed", 0) or 0
            )

        if sim_id is not None:
            summary["sim_ids_cleared"].append(int(sim_id))

    return summary


def _refresh_visible_rising_trait(sim_info) -> Dict[str, object]:
    summary = {
        "ok": False,
        "reason": None,
        "sim_name": _sim_display_name(sim_info) if sim_info is not None else "Sim",
        "sim_id": _sim_id_value(sim_info),
        "household_id": _sim_household_id(sim_info),
        "rising_sign_index": None,
        "target_trait_id": None,
        "had_target_trait": 0,
        "removed_target_trait": 0,
        "added_target_trait": 0,
        "has_target_trait_after": 0,
    }
    if sim_info is None:
        summary["reason"] = "missing_sim"
        return summary

    trait_ids, _marker_trait_ids = _collect_trait_ids_and_markers(sim_info)
    try:
        from .houses_notification_bridge import resolve_rising_sign_index_from_trait_ids
    except Exception:
        summary["reason"] = "import_failed"
        return summary

    rising_sign_index = resolve_rising_sign_index_from_trait_ids(trait_ids)
    if rising_sign_index is None:
        summary["reason"] = "missing_rising_sign"
        return summary
    summary["rising_sign_index"] = int(rising_sign_index)

    target_trait_id = _VISIBLE_RISING_SIGN_INDEX_TO_TRAIT_ID.get(int(rising_sign_index))
    if target_trait_id is None:
        summary["reason"] = "missing_target_trait_mapping"
        return summary
    summary["target_trait_id"] = int(target_trait_id)

    if _resolve_trait(int(target_trait_id)) is None:
        summary["reason"] = "missing_target_trait_def"
        return summary

    had_target_trait = _sim_has_trait(sim_info, int(target_trait_id))
    summary["had_target_trait"] = 1 if had_target_trait else 0
    if had_target_trait:
        has_target_trait_after = _sim_has_trait(sim_info, int(target_trait_id))
        summary["has_target_trait_after"] = 1 if has_target_trait_after else 0
        summary["ok"] = bool(has_target_trait_after)
        summary["reason"] = "already_present" if has_target_trait_after else "refresh_failed"
        return summary

    added = _add_trait_if_missing(sim_info, int(target_trait_id))
    summary["added_target_trait"] = 1 if added else 0

    has_target_trait_after = _sim_has_trait(sim_info, int(target_trait_id))
    summary["has_target_trait_after"] = 1 if has_target_trait_after else 0
    summary["ok"] = bool(has_target_trait_after)
    if summary["added_target_trait"]:
        summary["reason"] = "added_missing"
    elif has_target_trait_after:
        summary["reason"] = "already_present"
    else:
        summary["reason"] = "refresh_failed"
    return summary


def _refresh_visible_sun_moon_traits(sim_info) -> Dict[str, object]:
    summary = {
        "ok": False,
        "reason": None,
        "sim_name": _sim_display_name(sim_info) if sim_info is not None else "Sim",
        "sim_id": _sim_id_value(sim_info),
        "household_id": _sim_household_id(sim_info),
        "sun_sign_index": None,
        "moon_sign_index": None,
        "removed_trait_ids": [],
        "added_trait_ids": [],
        "has_visible_sun_after": 0,
        "has_visible_moon_after": 0,
    }
    if sim_info is None:
        summary["reason"] = "missing_sim"
        return summary

    try:
        from .natal_snapshot_markers import (
            _apply_visible_sign_timed_buff_for_trait_add,
            _desired_natal_sign_traits_from_sign_indexes,
            _desired_visible_sign_reward_traits_from_natal_sign_traits,
            _marker_cache,
        )
    except Exception:
        summary["reason"] = "import_failed"
        return summary

    cache = _marker_cache()
    sun_sign_trait_by_index = cache.get("sun_sign_trait_by_index", {})
    moon_sign_trait_by_index = cache.get("moon_sign_trait_by_index", {})
    visible_sun_reward_trait_by_index = cache.get("visible_sun_reward_trait_by_index", {})
    visible_moon_reward_trait_by_index = cache.get("visible_moon_reward_trait_by_index", {})
    visible_sign_reward_candidate_ids_by_body = cache.get("visible_sign_reward_candidate_ids_by_body", {})
    if not (
        isinstance(sun_sign_trait_by_index, dict)
        and isinstance(moon_sign_trait_by_index, dict)
        and isinstance(visible_sun_reward_trait_by_index, dict)
        and isinstance(visible_moon_reward_trait_by_index, dict)
        and isinstance(visible_sign_reward_candidate_ids_by_body, dict)
    ):
        summary["reason"] = "missing_trait_maps"
        return summary

    sign_index_by_body: Dict[str, int] = {}
    sim_id = _sim_id_value(sim_info)
    payload = _chart_payload_for_sim(int(sim_id), sim_info=sim_info) if sim_id is not None else None
    if isinstance(payload, dict):
        sun_sign_index = payload.get("sun_sign_index")
        moon_sign_index = payload.get("moon_sign_index")
        if isinstance(sun_sign_index, int):
            sign_index_by_body["Sun"] = int(sun_sign_index) % 12
        if isinstance(moon_sign_index, int):
            sign_index_by_body["Moon"] = int(moon_sign_index) % 12

    traits = tuple(_iter_traits_for_sim_info(sim_info))
    for body in ("Sun", "Moon"):
        if body in sign_index_by_body:
            continue
        sign_name = _extract_sign_from_traits(traits, body)
        if sign_name in _ZODIAC_SIGNS:
            sign_index_by_body[body] = _ZODIAC_SIGNS.index(sign_name)

    if "Sun" in sign_index_by_body:
        summary["sun_sign_index"] = int(sign_index_by_body["Sun"])
    if "Moon" in sign_index_by_body:
        summary["moon_sign_index"] = int(sign_index_by_body["Moon"])
    if len(sign_index_by_body) < 2:
        summary["reason"] = "missing_sign_indexes"
        return summary

    desired_sign_traits = _desired_natal_sign_traits_from_sign_indexes(
        sign_index_by_body=sign_index_by_body,
        sun_sign_trait_by_index=sun_sign_trait_by_index,
        moon_sign_trait_by_index=moon_sign_trait_by_index,
    )
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

    if len(desired_visible_sign_ids) < 2:
        summary["reason"] = "missing_visible_trait_defs"
        return summary

    desired_visible_sun_id = _coerce_int(desired_visible_sign_ids.get("Sun"))
    desired_visible_moon_id = _coerce_int(desired_visible_sign_ids.get("Moon"))
    has_desired_visible_sun = (
        desired_visible_sun_id is not None and _sim_has_trait(sim_info, int(desired_visible_sun_id))
    )
    has_desired_visible_moon = (
        desired_visible_moon_id is not None and _sim_has_trait(sim_info, int(desired_visible_moon_id))
    )
    if has_desired_visible_sun and has_desired_visible_moon:
        summary["has_visible_sun_after"] = 1
        summary["has_visible_moon_after"] = 1
        summary["ok"] = True
        summary["reason"] = "already_present"
        return summary

    visible_reward_ids_sun = set(visible_sign_reward_candidate_ids_by_body.get("Sun", set()) or set())
    visible_reward_ids_moon = set(visible_sign_reward_candidate_ids_by_body.get("Moon", set()) or set())

    for trait in traits:
        equipped_tid = _trait_guid64(trait)
        if equipped_tid is None:
            continue
        visible_body = None
        if int(equipped_tid) in visible_reward_ids_sun:
            visible_body = "Sun"
        elif int(equipped_tid) in visible_reward_ids_moon:
            visible_body = "Moon"
        if visible_body is None:
            continue
        if desired_visible_sign_ids.get(visible_body) == int(equipped_tid):
            continue
        if _remove_trait_if_present(sim_info, int(equipped_tid)):
            summary["removed_trait_ids"].append(int(equipped_tid))

    for body in ("Sun", "Moon"):
        desired_trait = desired_visible_sign_traits.get(body)
        desired_tid = desired_visible_sign_ids.get(body)
        if desired_trait is None or desired_tid is None:
            continue
        added = _add_trait_if_missing(sim_info, int(desired_tid))
        if added:
            summary["added_trait_ids"].append(int(desired_tid))
            try:
                _apply_visible_sign_timed_buff_for_trait_add(
                    sim_info,
                    desired_trait,
                    cache=cache,
                )
            except Exception:
                pass

    has_visible_sun_after = _sim_has_trait(sim_info, int(desired_visible_sign_ids.get("Sun", 0)))
    has_visible_moon_after = _sim_has_trait(sim_info, int(desired_visible_sign_ids.get("Moon", 0)))
    summary["has_visible_sun_after"] = 1 if has_visible_sun_after else 0
    summary["has_visible_moon_after"] = 1 if has_visible_moon_after else 0
    summary["ok"] = bool(has_visible_sun_after and has_visible_moon_after)
    if summary["added_trait_ids"] or summary["removed_trait_ids"]:
        summary["reason"] = "refreshed_existing"
    elif summary["ok"]:
        summary["reason"] = "already_present"
    else:
        summary["reason"] = "refresh_failed"
    return summary


def _refresh_household_v2_upgrade_state(
    anchor_sim_info,
    *,
    run_house_router: bool,
) -> Dict[str, object]:
    summary = {
        "sims_seen": 0,
        "sims_ok": 0,
        "sims_refreshed": 0,
        "sims_added_missing": 0,
        "sims_missing_rising": 0,
        "sun_moon_refresh_ok": 0,
        "sun_moon_traits_added": 0,
        "sun_moon_traits_removed": 0,
        "house_router_runs": 0,
        "eligible_visible_big3_sims": 0,
        "visible_big3_complete_sims": 0,
        "pending_visible_big3_sims": 0,
        "results": [],
    }

    for household_sim_info in _iter_household_sim_infos(anchor_sim_info):
        rising_refresh = _refresh_visible_rising_trait(household_sim_info)
        sun_moon_refresh = _refresh_visible_sun_moon_traits(household_sim_info)
        ran_house_router = False

        if run_house_router:
            ran_house_router = _run_action_loot_on_sim_info(
                household_sim_info,
                _HOUSES_ASSIGN_ROUTER_LOOT_ID,
            )

        visible_big3_status = _collect_visible_big3_status(household_sim_info)
        sim_refresh = {
            "rising_refresh": rising_refresh,
            "sun_moon_refresh": sun_moon_refresh,
            "house_router_ran": 1 if ran_house_router else 0,
            "visible_big3_status": visible_big3_status,
        }

        summary["sims_seen"] += 1
        if bool(rising_refresh.get("ok")):
            summary["sims_ok"] += 1
        if rising_refresh.get("reason") == "refreshed_existing":
            summary["sims_refreshed"] += 1
        elif rising_refresh.get("reason") == "added_missing":
            summary["sims_added_missing"] += 1
        elif rising_refresh.get("reason") == "missing_rising_sign":
            summary["sims_missing_rising"] += 1
        if bool(sun_moon_refresh.get("ok")):
            summary["sun_moon_refresh_ok"] += 1
        summary["sun_moon_traits_added"] += len(tuple(sun_moon_refresh.get("added_trait_ids") or ()))
        summary["sun_moon_traits_removed"] += len(tuple(sun_moon_refresh.get("removed_trait_ids") or ()))
        if ran_house_router:
            summary["house_router_runs"] += 1
        if visible_big3_status.get("eligible"):
            summary["eligible_visible_big3_sims"] += 1
            if visible_big3_status.get("complete"):
                summary["visible_big3_complete_sims"] += 1
            else:
                summary["pending_visible_big3_sims"] += 1

        summary["results"].append(sim_refresh)

    return summary


def migrate_legacy_v2_household_for_sim_info(sim_info) -> Dict[str, object]:
    summary = {
        "ok": False,
        "reason": None,
        "sim_name": _sim_display_name(sim_info) if sim_info is not None else "Sim",
        "sim_id": _sim_id_value(sim_info),
        "household_id": _sim_household_id(sim_info),
        "migration_summary": None,
        "repair_summary": None,
        "rising_refresh_summary": None,
        "marker_sync_summary": None,
        "rising_buff_summary": None,
        "pass_count": 0,
        "passes": [],
    }
    if sim_info is None:
        summary["reason"] = "missing_sim"
        return summary

    household_id = _sim_household_id(sim_info)
    if household_id is None:
        summary["reason"] = "missing_household"
        return summary
    summary["household_id"] = int(household_id)

    from .natal_snapshot_markers import (
        apply_visible_rising_timed_buff_for_sim_info,
        migrate_active_household_legacy_natal_to_v2,
    )

    try:
        from .first_load_chooser import repair_childhood_teen_handoff
    except Exception:
        repair_childhood_teen_handoff = None

    try:
        from .planet_house_markers import sync_zone_planet_house_markers
    except Exception:
        sync_zone_planet_house_markers = None

    if callable(repair_childhood_teen_handoff):
        try:
            summary["repair_summary"] = repair_childhood_teen_handoff(sim_info)
        except Exception:
            log.exception("Legacy V2 migration childhood repair failed for %s.", _sim_display_name(sim_info))

    final_migration_summary = None
    final_rising_refresh_summary = None
    final_marker_sync_summary = None
    max_passes = 3

    for pass_index in range(1, max_passes + 1):
        pre_refresh_summary = _refresh_household_v2_upgrade_state(
            sim_info,
            run_house_router=False,
        )
        migration_summary = migrate_active_household_legacy_natal_to_v2(
            active_household_id=int(household_id),
            refresh_marker_cache=False,
        )
        post_refresh_summary = _refresh_household_v2_upgrade_state(
            sim_info,
            run_house_router=True,
        )

        marker_sync_summary = None
        if callable(sync_zone_planet_house_markers):
            try:
                marker_sync_summary = sync_zone_planet_house_markers(
                    refresh_marker_cache=False,
                )
            except Exception:
                log.exception("Legacy V2 migration house marker sync failed for household %s.", household_id)

        pass_summary = {
            "pass_index": int(pass_index),
            "pre_refresh_summary": pre_refresh_summary,
            "migration_summary": migration_summary,
            "post_refresh_summary": post_refresh_summary,
            "marker_sync_summary": marker_sync_summary,
        }
        summary["passes"].append(pass_summary)
        summary["pass_count"] = int(pass_index)

        final_migration_summary = migration_summary
        final_rising_refresh_summary = post_refresh_summary
        final_marker_sync_summary = marker_sync_summary

        pass_changes = (
            int(pre_refresh_summary.get("sims_refreshed", 0) or 0)
            + int(pre_refresh_summary.get("sims_added_missing", 0) or 0)
            + int(pre_refresh_summary.get("sun_moon_traits_added", 0) or 0)
            + int(pre_refresh_summary.get("sun_moon_traits_removed", 0) or 0)
            + int((migration_summary or {}).get("legacy_sims_marked", 0) or 0)
            + int((migration_summary or {}).get("onboard_total_sims_seeded", 0) or 0)
            + int((post_refresh_summary or {}).get("sims_refreshed", 0) or 0)
            + int((post_refresh_summary or {}).get("sims_added_missing", 0) or 0)
            + int((post_refresh_summary or {}).get("sun_moon_traits_added", 0) or 0)
            + int((post_refresh_summary or {}).get("sun_moon_traits_removed", 0) or 0)
            + max(
                0,
                int(pre_refresh_summary.get("pending_visible_big3_sims", 0) or 0)
                - int(post_refresh_summary.get("pending_visible_big3_sims", 0) or 0),
            )
        )
        pending_visible_big3_sims = int(post_refresh_summary.get("pending_visible_big3_sims", 0) or 0)
        if pending_visible_big3_sims <= 0:
            break
        if pass_changes <= 0:
            break

    summary["migration_summary"] = final_migration_summary
    summary["rising_refresh_summary"] = final_rising_refresh_summary
    summary["marker_sync_summary"] = final_marker_sync_summary

    try:
        summary["rising_buff_summary"] = apply_visible_rising_timed_buff_for_sim_info(
            sim_info,
            refresh_marker_cache=False,
        )
    except Exception:
        log.exception("Legacy V2 migration rising buff sync failed for %s.", _sim_display_name(sim_info))

    summary["ok"] = bool(
        isinstance(migration_summary, dict)
        and migration_summary.get("has_active_household_id")
    )
    summary["reason"] = "migrated" if summary["ok"] else "migration_failed"
    return summary


def _extract_sign_from_traits(traits: Iterable[object], body_suffix: str) -> Optional[str]:
    best = None  # type: Optional[tuple[int, str]]
    for trait in traits:
        for text in _trait_text_candidates(trait):
            if "PlumAntics_CosmicEngineCore_" not in text:
                continue
            if "Return" in text:
                continue
            for sign in _ZODIAC_SIGNS:
                token = "{0}{1}".format(sign, body_suffix)
                if token not in text:
                    continue
                score = 0
                if "Hidden" in text:
                    score += 10
                if "_Marker" in text:
                    score += 5
                if "ChartRuler" in text:
                    score += 20
                candidate = (score, sign)
                if best is None or candidate[0] < best[0]:
                    best = candidate
    return best[1] if best is not None else None


def _extract_chart_ruler_from_traits(traits: Iterable[object]) -> Optional[str]:
    best = None  # type: Optional[tuple[int, str]]
    for trait in traits:
        for text in _trait_text_candidates(trait):
            if "PlumAntics_CosmicEngineCore_" not in text:
                continue
            planet = None
            for candidate_planet in _CHART_PLANETS:
                if "{0}ChartRuler".format(candidate_planet) in text:
                    planet = candidate_planet
                    score = 0
                    break
                if "{0}_Hidden".format(candidate_planet) in text:
                    planet = candidate_planet
                    score = 10
                    break
            if planet is None:
                continue
            candidate = (score, planet)
            if best is None or candidate[0] < best[0]:
                best = candidate
    return best[1] if best is not None else None


def _extract_transit_marker_rows(traits: Iterable[object]) -> List[str]:
    rows = []  # type: List[tuple[int, int, str]]
    seen = set()
    for trait in traits:
        for text in _trait_text_candidates(trait):
            if "PlumAntics_CosmicEngineHouses_" not in text or "TransitMarker" not in text:
                continue
            house_label = None
            house_order = None
            for token, label in _TRANSIT_HOUSE_TOKEN_TO_LABEL:
                if token in text:
                    house_label = label
                    house_order = _TRANSIT_HOUSE_LABEL_ORDER.get(label, 99)
                    break
            if house_label is None:
                continue

            body = None
            for candidate_planet in _TRANSIT_MARKER_BODIES:
                if "{0}TransitMarker".format(candidate_planet) in text:
                    body = candidate_planet
                    break
            if body is None:
                continue

            key = (house_label, body)
            if key in seen:
                continue
            seen.add(key)
            rows.append(
                (
                    int(house_order),
                    int(_TRANSIT_MARKER_PLANET_ORDER.get(body, 99)),
                    "{0} ({1})".format(body, house_label),
                )
            )

    rows.sort(key=lambda row: (row[0], row[1], row[2]))
    return [row[2] for row in rows]


def _show_simple_notification(owner, title: str, text: str) -> bool:
    try:
        from sims4.localization import LocalizationHelperTuning  # type: ignore
        from ui.ui_dialog_notification import UiDialogNotification  # type: ignore

        notification = UiDialogNotification.TunableFactory().default(
            owner,
            title=lambda *_, **__: LocalizationHelperTuning.get_raw_text(str(title)),
            text=lambda *_, **__: LocalizationHelperTuning.get_raw_text(str(text)),
        )
        notification.show_dialog()
        return True
    except Exception:
        return False


def _show_chart_skill_gate_notification(
    owner,
    *,
    required_level: int,
    actor_skill_level: int,
) -> bool:
    title = "Chart Reading Not Ready"
    text = (
        "Read Natal Chart unlocks at Simstrology level {0}. "
        "Current level: {1}."
    ).format(int(required_level), int(actor_skill_level))
    return _show_simple_notification(owner, title, text)


def _signed_sun_offset(body_index: int, sun_index: int) -> int:
    offset = (int(body_index) - int(sun_index)) % 12
    if offset > 6:
        offset -= 12
    return int(offset)


def build_transit_pretty_payload(service=None) -> Dict[str, object]:
    payload = {
        "ok": False,
        "command_name": "ce.transit.pretty",
        "title": "Cosmic Engine Transits",
        "lines": [],
    }

    try:
        service = service or get_global_transit_service()
        state = getattr(service, "state", None)
        if state is None:
            payload["lines"] = ["Transit service unavailable."]
            return payload

        sun_index = int(state.sign_index_by_body.get("Sun", 0)) % 12
        lines = []
        for body in _active_pretty_transit_body_names(service):
            if body not in state.sign_index_by_body:
                continue
            sign_index = int(state.sign_index_by_body.get(body, 0)) % 12
            sign_name = SIGNS[sign_index]
            offset = _signed_sun_offset(sign_index, sun_index)
            if offset == 0:
                offset_text = "Sun+0"
            elif offset > 0:
                offset_text = "Sun+{0}".format(offset)
            else:
                offset_text = "Sun{0}".format(offset)
            lines.append(
                "{0}: {1} ({2}) [{3}]".format(body, sign_name, sign_index, offset_text)
            )

        lines.append(
            "DayProgress: MoonFrac={0:.3f} (cycle={1:g}d), Mercury={2}".format(
                float(service.get_moon_progress_fraction()),
                float(service.get_lunar_cycle_days_hint()),
                int(state.day_progress_by_body.get("Mercury", 0)),
            )
        )
        lines.append(
            "SegmentRemainders: Sun={0}, Venus={1}, Mars={2}, Jupiter={3}, Saturn={4}".format(
                int(state.segment_progress_by_body.get("Sun", 0)),
                int(state.segment_progress_by_body.get("Venus", 0)),
                int(state.segment_progress_by_body.get("Mars", 0)),
                int(state.segment_progress_by_body.get("Jupiter", 0)),
                int(state.segment_progress_by_body.get("Saturn", 0)),
            )
        )
        payload["ok"] = True
        payload["lines"] = lines
        return payload
    except Exception:
        log.exception("Failed building ce.transit.pretty payload.")
        payload["lines"] = ["Transit pretty payload failed."]
        return payload


_PRETTY_COMMAND_PAYLOAD_BUILDERS = {
    "ce.transit.pretty": build_transit_pretty_payload,
}


def show_pretty_command_notification(owner, command_name: str) -> bool:
    normalized = str(command_name or "").strip().lower()
    builder = _PRETTY_COMMAND_PAYLOAD_BUILDERS.get(normalized)
    if not callable(builder):
        return False

    payload = builder() or {}
    title = str(payload.get("title") or normalized or "Simstrology Pretty Output")
    lines = payload.get("lines")
    if isinstance(lines, (list, tuple)):
        text = "\n".join(str(line) for line in lines if str(line or "").strip())
    else:
        text = str(payload.get("text") or "")
    if not text:
        return False
    return _show_simple_notification(owner, title, text)


def _collect_trait_ids_and_markers(sim_info) -> tuple[List[int], List[int]]:
    trait_ids: List[int] = []
    marker_trait_ids: List[int] = []
    seen_trait_ids: set = set()

    for trait in _iter_traits_for_sim_info(sim_info):
        trait_id = _trait_guid64(trait)
        if trait_id is None:
            continue
        trait_id = int(trait_id)
        if trait_id in seen_trait_ids:
            continue
        seen_trait_ids.add(trait_id)

        trait_ids.append(trait_id)
        trait_name = _trait_name(trait)
        if (
            "PlumAntics_CosmicEngineHouses_" in trait_name
            and "House_" in trait_name
            and trait_name.endswith("Hidden")
        ):
            marker_trait_ids.append(trait_id)

    return trait_ids, marker_trait_ids


def _run_action_loot_on_sim_info(sim_info, loot_id: Optional[int]) -> bool:
    try:
        import services  # type: ignore
        import sims4.resources  # type: ignore
    except Exception:
        return False

    if sim_info is None or loot_id is None:
        return False

    try:
        manager = services.get_instance_manager(sims4.resources.Types.ACTION)
    except Exception:
        manager = None
    if manager is None:
        return False

    try:
        tuning = manager.get(int(loot_id))
    except Exception:
        tuning = None
    if tuning is None:
        return False

    resolver_getter = getattr(sim_info, "get_resolver", None)
    if not callable(resolver_getter):
        return False
    try:
        resolver = resolver_getter()
    except Exception:
        resolver = None
    if resolver is None:
        return False

    for method_name in (
        "apply_to_resolver",
        "apply_to_resolver_and_get_result",
        "apply_to_single_resolver",
    ):
        method = getattr(tuning, method_name, None)
        if not callable(method):
            continue
        try:
            method(resolver)
            return True
        except Exception:
            continue
    return False


try:
    from interactions.utils.loot import LootActions  # type: ignore
except Exception:  # pragma: no cover - local fallback

    class LootActions(object):
        """Fallback shim for local syntax checks outside game runtime."""

        def apply_to_resolver(self, resolver, skip_test=False):
            return True


try:
    from sims4.tuning.tunable import Tunable  # type: ignore
except Exception:  # pragma: no cover - local fallback

    class Tunable(object):
        def __init__(self, *args, **kwargs):
            pass


class CosmicEngineHousesPythonReadoutLoot(LootActions):
    """Action tuning class called directly from SI_GetHouses loot list.

    It computes the Python chart payload and stores it on the transit service
    cache for future custom notifications/dialog rendering.
    """

    def apply_to_resolver(self, resolver, skip_test=False):
        result = super().apply_to_resolver(resolver, skip_test=skip_test)

        try:
            sim_info = _resolve_actor_sim_info(resolver)
            if sim_info is None:
                log.warning("Python readout loot could not resolve actor sim_info.")
                return result

            sim_id = getattr(sim_info, "sim_id", None)
            if sim_id is None:
                sim_id = getattr(sim_info, "id", None)
            if sim_id is None:
                log.warning("Python readout loot missing sim id.")
                return result

            required_level = int(
                simstrology_skill_unlock_level("chart_ruler_awareness", default=3)
            )
            actor_skill_level = int(get_simstrology_skill_level(sim_info))
            if not simstrology_skill_meets(sim_info, required_level):
                get_global_transit_service().set_last_houses_readout_payload(
                    int(sim_id),
                    {
                        "ok": False,
                        "skill_gate_blocked": True,
                        "feature": "chart_ruler_awareness",
                        "required_level": required_level,
                        "actor_skill_level": actor_skill_level,
                    },
                )
                log.debug(
                    "Python houses readout blocked by Simstrology skill gate (sim=%s level=%s required=%s).",
                    int(sim_id),
                    actor_skill_level,
                    required_level,
                )
                return result

            trait_ids, marker_trait_ids = _collect_trait_ids_and_markers(sim_info)
            payload = build_houses_readout_payload(
                get_global_transit_service(),
                actor_trait_ids=trait_ids,
                actor_marker_trait_ids=marker_trait_ids,
            )
            get_global_transit_service().set_last_houses_readout_payload(
                int(sim_id), payload
            )
        except Exception:
            log.exception("Python readout loot bridge failed.")

        return result


class SimstrologyHousesDispatchExistingNotificationLoot(LootActions):
    """Apply the existing per-rising Houses notice selected by Python."""

    def apply_to_resolver(self, resolver, skip_test=False):
        result = super().apply_to_resolver(resolver, skip_test=skip_test)

        try:
            sim_info = _resolve_actor_sim_info(resolver)
            if sim_info is None:
                log.warning("Houses notification dispatch could not resolve actor sim_info.")
                return result

            sim_id = getattr(sim_info, "sim_id", None)
            if sim_id is None:
                sim_id = getattr(sim_info, "id", None)
            if sim_id is None:
                log.warning("Houses notification dispatch missing sim id.")
                return result

            sim_id = int(sim_id)
            transit_service = get_global_transit_service()
            payload = transit_service.get_last_houses_readout_payload(sim_id)
            if not isinstance(payload, dict) or not payload.get("ok"):
                trait_ids, marker_trait_ids = _collect_trait_ids_and_markers(sim_info)
                payload = build_houses_readout_payload(
                    transit_service,
                    actor_trait_ids=trait_ids,
                    actor_marker_trait_ids=marker_trait_ids,
                )
                transit_service.set_last_houses_readout_payload(sim_id, payload)

            loot_id = payload.get("existing_notification_loot_id")
            if loot_id is None:
                log.debug(
                    "Houses notification dispatch found no existing notification loot (sim=%s payload=%s).",
                    sim_id,
                    payload,
                )
                return result

            try:
                import services  # type: ignore
                import sims4.resources  # type: ignore
            except Exception:
                log.exception("Houses notification dispatch could not import game services.")
                return result

            manager = services.get_instance_manager(sims4.resources.Types.ACTION)
            if manager is None:
                log.warning("Houses notification dispatch missing ACTION instance manager.")
                return result

            tuning = manager.get(int(loot_id))
            if tuning is None:
                log.warning(
                    "Houses notification dispatch missing tuned loot id %s for sim %s.",
                    int(loot_id),
                    sim_id,
                )
                return result

            dispatched = False
            for method_name in (
                "apply_to_resolver",
                "apply_to_resolver_and_get_result",
                "apply_to_single_resolver",
            ):
                method = getattr(tuning, method_name, None)
                if not callable(method):
                    continue
                try:
                    method(resolver)
                    dispatched = True
                    break
                except Exception:
                    continue

            if not dispatched:
                log.warning(
                    "Houses notification dispatch could not execute loot id %s for sim %s.",
                    int(loot_id),
                    sim_id,
                )
        except Exception:
            log.exception("Houses notification dispatch failed.")

        return result


class CosmicEngineSetChemistryProfileLoot(LootActions):
    """Persist the selected save-wide chemistry profile from the self hub."""

    INSTANCE_TUNABLES = {
        "profile_id": Tunable(
            description="Save-wide astrology chemistry profile to persist.",
            tunable_type=str,
            default="balanced",
        ),
    }

    def apply_to_resolver(self, resolver, skip_test=False):
        result = super().apply_to_resolver(resolver, skip_test=skip_test)
        requested_profile_id = str(
            getattr(self, "profile_id", "balanced") or "balanced"
        ).strip().lower()

        try:
            from .ts4_runtime_install import load_chemistry_profile, persist_chemistry_profile
        except Exception:
            load_chemistry_profile = None
            persist_chemistry_profile = None

        try:
            owner = _resolve_actor_sim_info(resolver)
            if owner is None:
                owner = _resolve_participant_sim_info(
                    resolver,
                    ("TargetSim", "Object", "Target", "PickedSim"),
                )

            if not callable(persist_chemistry_profile) or not persist_chemistry_profile(
                requested_profile_id,
                reason="loot.chemistry_profile",
            ):
                log.warning(
                    "Chemistry profile loot could not persist requested profile '%s'.",
                    requested_profile_id,
                )
                return result

            saved_payload = load_chemistry_profile() if callable(load_chemistry_profile) else {}
            saved_profile_id = read_chemistry_profile_id(saved_payload)
            title = "Chemistry Intensity Updated"
            text = "Astrology chemistry intensity set to {0} for this save.".format(
                get_chemistry_profile_label(saved_profile_id)
            )
            if owner is not None and not _show_simple_notification(owner, title, text):
                log.warning(
                    "Chemistry profile loot could not show confirmation notification for '%s'.",
                    saved_profile_id,
                )
        except Exception:
            log.exception(
                "Chemistry profile loot bridge failed for requested profile '%s'.",
                requested_profile_id,
            )

        return result


class CosmicEngineSetRetrogradeVisibilityProfileLoot(LootActions):
    """Persist the selected save-wide retrograde visibility profile from the self hub."""

    INSTANCE_TUNABLES = {
        "profile_id": Tunable(
            description="Save-wide retrograde visibility profile to persist.",
            tunable_type=str,
            default="recommended",
        ),
    }

    def apply_to_resolver(self, resolver, skip_test=False):
        result = super().apply_to_resolver(resolver, skip_test=skip_test)
        requested_profile_id = str(
            getattr(self, "profile_id", "recommended") or "recommended"
        ).strip().lower()

        try:
            from .ts4_runtime_install import (
                load_retrograde_visibility_profile,
                persist_retrograde_visibility_profile,
            )
        except Exception:
            load_retrograde_visibility_profile = None
            persist_retrograde_visibility_profile = None

        try:
            owner = _resolve_actor_sim_info(resolver)
            if owner is None:
                owner = _resolve_participant_sim_info(
                    resolver,
                    ("TargetSim", "Object", "Target", "PickedSim"),
                )

            if not callable(persist_retrograde_visibility_profile) or not persist_retrograde_visibility_profile(
                requested_profile_id,
                reason="loot.retrograde_visibility_profile",
            ):
                log.warning(
                    "Retrograde visibility profile loot could not persist requested profile '%s'.",
                    requested_profile_id,
                )
                return result

            saved_payload = (
                load_retrograde_visibility_profile()
                if callable(load_retrograde_visibility_profile)
                else {}
            )
            saved_profile_id = read_retrograde_visibility_profile_id(saved_payload)
            title = "Retrograde Visibility Updated"
            text = "Retrograde visibility set to {0} for this save.".format(
                get_retrograde_visibility_profile_label(saved_profile_id)
            )
            if owner is not None and not _show_simple_notification(owner, title, text):
                log.warning(
                    "Retrograde visibility profile loot could not show confirmation notification for '%s'.",
                    saved_profile_id,
                )
        except Exception:
            log.exception(
                "Retrograde visibility profile loot bridge failed for requested profile '%s'.",
                requested_profile_id,
            )

        return result


class CosmicEngineClearKnownChemistryLoot(LootActions):
    """Clear known chemistry pair-memory relbits from the actor for one chart layer."""

    INSTANCE_TUNABLES = {
        "layer_name": Tunable(
            description="Pair-memory layer name to clear from the actor's relationships.",
            tunable_type=str,
            default="rising",
        ),
    }

    def apply_to_resolver(self, resolver, skip_test=False):
        result = super().apply_to_resolver(resolver, skip_test=skip_test)
        actor_sim_info = _resolve_actor_sim_info(resolver)
        try:
            _clear_known_chemistry_pair_memory_from_actor(
                actor_sim_info,
                getattr(self, "layer_name", "rising"),
            )
        except Exception:
            log.exception("Known chemistry pair-memory clear loot bridge failed.")
        return result


def _refresh_chemistry_for_pair(
    actor_sim_info,
    target_sim_info,
    *,
    trigger_reason="resolver_loot",
):
    global _LAST_RISING_CHEMISTRY_REFRESH_DEBUG
    global _LAST_SUN_CHEMISTRY_REFRESH_DEBUG

    try:
        from .rising_chemistry import (
            build_actor_rising_chemistry_buff_plan,
            build_refresh_summary,
            should_apply_first_contact_rising_pass,
        )
    except Exception:
        build_actor_rising_chemistry_buff_plan = None
        build_refresh_summary = None
        should_apply_first_contact_rising_pass = None
    try:
        from .sun_chemistry import (
            build_sun_overlay_buff_plan,
            should_apply_first_contact_sun_pass,
        )
    except Exception:
        build_sun_overlay_buff_plan = None
        should_apply_first_contact_sun_pass = None
    try:
        from .chemistry_pair_memory import build_pair_memory_write_summary
    except Exception:
        build_pair_memory_write_summary = None
    try:
        from .ts4_runtime_install import load_chemistry_profile
    except Exception:
        load_chemistry_profile = None

    try:
        relationship_summary = _resolve_relationship_score_summary(
            actor_sim_info,
            target_sim_info,
        )
        actor_rising_sign_index, actor_rising_sign_name = _resolve_rising_sign_index_and_name(actor_sim_info)
        target_rising_sign_index, target_rising_sign_name = _resolve_rising_sign_index_and_name(target_sim_info)
        actor_sun_sign_index, actor_sun_sign_name = _resolve_sun_sign_index_and_name(actor_sim_info)
        target_sun_sign_index, target_sun_sign_name = _resolve_sun_sign_index_and_name(target_sim_info)
        chemistry_payload = load_chemistry_profile() if callable(load_chemistry_profile) else {}
        profile_id = read_chemistry_profile_id(chemistry_payload)
        actor_sun_tier_name = _resolve_active_sun_chemistry_tier_name(
            actor_sim_info,
            target_sim_info,
        )
        known_state_summary = _build_pair_memory_known_state_summary(actor_sim_info, target_sim_info)

        if not callable(build_refresh_summary):
            _LAST_RISING_CHEMISTRY_REFRESH_DEBUG = {
                "ok": False,
                "reason": "missing_refresh_helper",
                "trigger_reason": trigger_reason,
                "actor_sim_id": _sim_id_value(actor_sim_info),
                "target_sim_id": _sim_id_value(target_sim_info),
                "profile_id": profile_id,
                "actor_rising_sign_index": actor_rising_sign_index,
                "actor_rising_sign_name": actor_rising_sign_name,
                "target_rising_sign_index": target_rising_sign_index,
                "target_rising_sign_name": target_rising_sign_name,
                "actor_sun_sign_index": actor_sun_sign_index,
                "actor_sun_sign_name": actor_sun_sign_name,
                "target_sun_sign_index": target_sun_sign_index,
                "target_sun_sign_name": target_sun_sign_name,
                "rising_known": known_state_summary.get("rising_known"),
                "sun_known": known_state_summary.get("sun_known"),
            }
            _LAST_SUN_CHEMISTRY_REFRESH_DEBUG = {
                "ok": False,
                "reason": "missing_refresh_helper",
                "trigger_reason": trigger_reason,
                "actor_sim_id": _sim_id_value(actor_sim_info),
                "target_sim_id": _sim_id_value(target_sim_info),
                "profile_id": profile_id,
                "sun_tier_name": actor_sun_tier_name,
                "actor_sun_sign_index": actor_sun_sign_index,
                "actor_sun_sign_name": actor_sun_sign_name,
                "target_sun_sign_index": target_sun_sign_index,
                "target_sun_sign_name": target_sun_sign_name,
                "rising_known": known_state_summary.get("rising_known"),
                "sun_known": known_state_summary.get("sun_known"),
            }
            return {
                "ok": False,
                "reason": "missing_refresh_helper",
                "trigger_reason": trigger_reason,
                "rising_summary": dict(_LAST_RISING_CHEMISTRY_REFRESH_DEBUG),
                "sun_summary": dict(_LAST_SUN_CHEMISTRY_REFRESH_DEBUG),
            }

        summary = build_refresh_summary(
            actor_sim_id=_sim_id_value(actor_sim_info),
            target_sim_id=_sim_id_value(target_sim_info),
            profile_id=profile_id,
            friendship_score=relationship_summary.get("scores", {}).get("friendship"),
            romance_score=relationship_summary.get("scores", {}).get("romance"),
        )
        summary["trigger_reason"] = trigger_reason
        summary["score_source_owners"] = dict(relationship_summary.get("source_owners", {}))
        summary["score_track_ids"] = dict(relationship_summary.get("track_ids", {}))
        summary["actor_rising_sign_index"] = actor_rising_sign_index
        summary["actor_rising_sign_name"] = actor_rising_sign_name
        summary["target_rising_sign_index"] = target_rising_sign_index
        summary["target_rising_sign_name"] = target_rising_sign_name
        summary["actor_sun_sign_index"] = actor_sun_sign_index
        summary["actor_sun_sign_name"] = actor_sun_sign_name
        summary["target_sun_sign_index"] = target_sun_sign_index
        summary["target_sun_sign_name"] = target_sun_sign_name
        summary["actor_name"] = _sim_display_name(actor_sim_info) if actor_sim_info is not None else None
        summary["target_name"] = _sim_display_name(target_sim_info) if target_sim_info is not None else None
        summary["rising_known"] = bool(known_state_summary.get("rising_known"))
        summary["sun_known"] = bool(known_state_summary.get("sun_known"))
        summary["known_state_summary"] = dict(known_state_summary)
        summary["apply_first_contact_rising"] = (
            bool(should_apply_first_contact_rising_pass(rising_known=summary["rising_known"]))
            if callable(should_apply_first_contact_rising_pass)
            else None
        )
        pair_memory_write = (
            build_pair_memory_write_summary(
                summary,
                rising_known=summary["rising_known"],
                sun_known=summary["sun_known"],
            )
            if callable(build_pair_memory_write_summary)
            else {"ok": False, "reason": "missing_pair_memory_helper", "relbit_ids": []}
        )
        summary["pair_memory_write"] = (
            dict(pair_memory_write) if isinstance(pair_memory_write, dict) else {}
        )
        summary["pair_memory_summary"] = dict(summary["pair_memory_write"])
        pair_memory_write = summary.get("pair_memory_write", {})
        if pair_memory_write.get("reason") == "write_both":
            written_ids = []
            for relbit_id in pair_memory_write.get("relbit_ids", []):
                if _write_pair_relbit(actor_sim_info, target_sim_info, int(relbit_id)):
                    written_ids.append(int(relbit_id))
            summary["written_pair_memory_relbit_ids"] = written_ids
        else:
            summary["written_pair_memory_relbit_ids"] = []
        requested_relbit_ids = [
            int(relbit_id)
            for relbit_id in pair_memory_write.get("relbit_ids", [])
            if relbit_id is not None
        ]
        pair_memory_write_ok = (
            pair_memory_write.get("reason") == "write_both"
            and len(summary["written_pair_memory_relbit_ids"]) == len(requested_relbit_ids)
        )
        pair_memory_write_reason = str(pair_memory_write.get("reason") or "skipped")
        if pair_memory_write.get("reason") == "write_both" and not pair_memory_write_ok:
            pair_memory_write_reason = "partial_write_failed"
        summary["pair_memory_write_summary"] = {
            "ok": bool(pair_memory_write_ok),
            "reason": pair_memory_write_reason,
            "requested_relbit_ids": requested_relbit_ids,
            "written_relbit_ids": list(summary["written_pair_memory_relbit_ids"]),
            "write_count": len(summary["written_pair_memory_relbit_ids"]),
        }
        sign_compatibility_seed_summary = _seed_pair_sign_compatibility_relbits(
            actor_sim_info,
            target_sim_info,
        )
        sign_compatibility_visible_buff_summary = _sync_actor_sign_compatibility_visible_buffs(
            actor_sim_info,
            target_sim_info,
        )
        summary["sign_compatibility_seed_summary"] = (
            dict(sign_compatibility_seed_summary)
            if isinstance(sign_compatibility_seed_summary, dict)
            else {}
        )
        summary["sign_compatibility_visible_buff_summary"] = (
            dict(sign_compatibility_visible_buff_summary)
            if isinstance(sign_compatibility_visible_buff_summary, dict)
            else {}
        )

        if callable(build_actor_rising_chemistry_buff_plan):
            buff_plan = build_actor_rising_chemistry_buff_plan(
                sign_name=actor_rising_sign_name,
                profile_id=profile_id,
                friendship_score=relationship_summary.get("scores", {}).get("friendship"),
                romance_score=relationship_summary.get("scores", {}).get("romance"),
                relationship_score=summary.get("relationship_score"),
            )
        else:
            buff_plan = {"ok": False, "reason": "missing_buff_plan_helper"}
        summary["managed_buff_plan"] = dict(buff_plan) if isinstance(buff_plan, dict) else {}
        summary["pending_buff_keys"] = []
        if isinstance(buff_plan, dict) and buff_plan.get("managed_buff_key"):
            summary["pending_buff_keys"] = [str(buff_plan.get("managed_buff_key"))]
        summary["pending_buff_count"] = len(summary["pending_buff_keys"])
        summary["managed_buff_sync"] = _sync_actor_rising_chemistry_buffs(actor_sim_info, buff_plan)
        _LAST_RISING_CHEMISTRY_REFRESH_DEBUG = summary

        sun_summary = {
            "ok": False,
            "reason": None,
            "trigger_reason": trigger_reason,
            "actor_sim_id": _sim_id_value(actor_sim_info),
            "target_sim_id": _sim_id_value(target_sim_info),
            "actor_name": _sim_display_name(actor_sim_info) if actor_sim_info is not None else None,
            "target_name": _sim_display_name(target_sim_info) if target_sim_info is not None else None,
            "profile_id": profile_id,
            "sun_tier_name": actor_sun_tier_name,
            "actor_sun_sign_index": actor_sun_sign_index,
            "actor_sun_sign_name": actor_sun_sign_name,
            "target_sun_sign_index": target_sun_sign_index,
            "target_sun_sign_name": target_sun_sign_name,
            "actor_rising_sign_index": actor_rising_sign_index,
            "actor_rising_sign_name": actor_rising_sign_name,
            "target_rising_sign_index": target_rising_sign_index,
            "target_rising_sign_name": target_rising_sign_name,
            "rising_known": bool(known_state_summary.get("rising_known")),
            "sun_known": bool(known_state_summary.get("sun_known")),
            "overlay_buff_plan": {},
            "pending_overlay_keys": [],
            "pending_overlay_count": 0,
            "overlay_sync": {},
        }
        sun_summary["known_state_summary"] = dict(known_state_summary)
        sun_summary["pair_memory_write"] = dict(summary.get("pair_memory_write", {}))
        sun_summary["pair_memory_summary"] = dict(summary.get("pair_memory_summary", {}))
        sun_summary["pair_memory_write_summary"] = dict(summary.get("pair_memory_write_summary", {}))
        sun_summary["apply_first_contact_sun"] = (
            bool(should_apply_first_contact_sun_pass(sun_known=sun_summary["sun_known"]))
            if callable(should_apply_first_contact_sun_pass)
            else None
        )
        if callable(build_sun_overlay_buff_plan):
            sun_buff_plan = build_sun_overlay_buff_plan(
                actor_sun_tier_name,
                profile_id,
            )
        else:
            sun_buff_plan = {"ok": False, "reason": "missing_buff_plan_helper"}
        sun_summary["overlay_buff_plan"] = (
            dict(sun_buff_plan) if isinstance(sun_buff_plan, dict) else {}
        )
        if isinstance(sun_buff_plan, dict):
            overlay_name = sun_buff_plan.get("overlay_name")
            if overlay_name:
                sun_summary["pending_overlay_keys"] = [str(overlay_name)]
        sun_summary["pending_overlay_count"] = len(sun_summary["pending_overlay_keys"])
        sun_summary["overlay_sync"] = _sync_actor_sun_chemistry_overlay_buffs(
            actor_sim_info,
            sun_buff_plan,
        )
        sync_summary = sun_summary.get("overlay_sync", {})
        sun_summary["ok"] = bool(sync_summary.get("ok"))
        sun_summary["reason"] = (
            str(sync_summary.get("reason"))
            if isinstance(sync_summary, dict) and sync_summary.get("reason")
            else (
                str(sun_buff_plan.get("reason"))
                if isinstance(sun_buff_plan, dict) and sun_buff_plan.get("reason")
                else None
            )
        )
        _LAST_SUN_CHEMISTRY_REFRESH_DEBUG = sun_summary

        log.debug(
            "Chemistry refresh prepared for actor=%s target=%s profile=%s rising=%s friendship_band=%s romance_band=%s applied_stage=%s rising_buff_key=%s sun_tier=%s sun_overlay=%s sign_lanes_written=%s.",
            summary.get("actor_name"),
            summary.get("target_name"),
            summary.get("profile_id"),
            summary.get("actor_rising_sign_name"),
            summary.get("relationship_bands", {}).get("friendship"),
            summary.get("relationship_bands", {}).get("romance"),
            summary.get("managed_buff_plan", {}).get("affordance_stage"),
            summary.get("managed_buff_plan", {}).get("managed_buff_key"),
            sun_summary.get("sun_tier_name"),
            sun_summary.get("overlay_buff_plan", {}).get("overlay_name"),
            summary.get("sign_compatibility_seed_summary", {}).get("written_lanes"),
        )
        return {
            "ok": (
                bool(summary.get("ok"))
                and bool(sun_summary.get("ok"))
                and bool(summary.get("sign_compatibility_visible_buff_summary", {}).get("ok"))
            ),
            "reason": str(summary.get("reason") or sun_summary.get("reason") or "resolved"),
            "trigger_reason": trigger_reason,
            "rising_summary": dict(summary),
            "sun_summary": dict(sun_summary),
            "sign_compatibility_summary": {
                "seed_summary": dict(summary.get("sign_compatibility_seed_summary", {})),
                "visible_buff_summary": dict(
                    summary.get("sign_compatibility_visible_buff_summary", {})
                ),
            },
        }
    except Exception:
        log.exception("Chemistry refresh bridge failed.")
        return {
            "ok": False,
            "reason": "exception",
            "trigger_reason": trigger_reason,
            "actor_sim_id": _sim_id_value(actor_sim_info),
            "target_sim_id": _sim_id_value(target_sim_info),
        }


class _CompletedSocialPairResolver(object):
    def __init__(self, actor_sim_info, target_sim_info, source=None):
        self.actor = actor_sim_info
        self.target = target_sim_info
        self.refresh_source = source


def _build_social_pair_resolver(actor_sim_info, target_sim_info, source=None):
    if actor_sim_info is None or target_sim_info is None:
        return None
    return _CompletedSocialPairResolver(actor_sim_info, target_sim_info, source=source)


def apply_soul_path_master_social_resolution(
    actor_sim_info,
    *,
    source="runtime.social_complete",
):
    source = str(source or "runtime.social_complete")
    if actor_sim_info is None:
        return {
            "ok": False,
            "reason": "missing_actor",
            "source": source,
        }
    if not _sim_has_trait(actor_sim_info, int(_SOUL_PATH_MASTER_TRAIT_ID)):
        return {
            "ok": False,
            "reason": "trait_missing",
            "source": source,
        }
    buff_added = _add_buff_if_missing(
        actor_sim_info,
        int(_SOUL_PATH_MASTER_CONFIDENT_PULSE_BUFF_ID),
    )
    return {
        "ok": True,
        "reason": "pulse_applied" if buff_added else "pulse_already_active",
        "source": source,
    }


def refresh_chemistry_after_completed_social(
    actor_sim_info,
    target_sim_info,
    *,
    source="runtime.social_complete",
):
    """Plan-facing runtime entrypoint for post-social chemistry refresh."""
    source = str(source or "runtime.social_complete")
    actor_sim_id = _sim_id_value(actor_sim_info)
    target_sim_id = _sim_id_value(target_sim_info)
    if actor_sim_info is None or target_sim_info is None:
        return {
            "ok": False,
            "reason": "missing_pair",
            "source": source,
        }
    if actor_sim_id is not None and target_sim_id is not None and int(actor_sim_id) == int(target_sim_id):
        return {
            "ok": False,
            "reason": "missing_pair",
            "source": source,
        }
    resolver = _build_social_pair_resolver(actor_sim_info, target_sim_info, source=source)
    if resolver is None:
        return {
            "ok": False,
            "reason": "missing_resolver",
            "source": source,
    }
    loot = CosmicEngineRefreshRisingChemistryLoot()
    loot.apply_to_resolver(resolver, skip_test=True)
    pulse_summary = apply_soul_path_master_social_resolution(
        actor_sim_info,
        source=source,
    )
    return {
        "ok": True,
        "reason": "dispatched",
        "source": source,
        "soul_path_master": pulse_summary,
    }


def refresh_chemistry_after_social_pair(actor_sim_info, target_sim_info, *, reason="social_complete"):
    """Backward-compatible wrapper for the Task 5 runtime entrypoint."""
    return refresh_chemistry_after_completed_social(
        actor_sim_info,
        target_sim_info,
        source=str(reason or "social_complete"),
    )


class CosmicEngineRefreshRisingChemistryLoot(LootActions):
    """Run the chemistry refresh resolver after existing social loot effects."""

    def apply_to_resolver(self, resolver, skip_test=False):
        result = super().apply_to_resolver(resolver, skip_test=skip_test)
        actor_sim_info = _resolve_actor_sim_info(resolver)
        target_sim_info = _resolve_participant_sim_info(
            resolver,
            ("TargetSim", "Object", "Target", "PickedSim"),
        )
        trigger_reason = str(getattr(resolver, "refresh_source", None) or "resolver_loot")
        _refresh_chemistry_for_pair(
            actor_sim_info,
            target_sim_info,
            trigger_reason=trigger_reason,
        )
        return result


class CosmicEngineRegisterGiftedCrystalResonanceLoot(LootActions):
    """Register temporary attunement when a matching crystal gift resolves successfully."""

    def apply_to_resolver(self, resolver, skip_test=False):
        result = super().apply_to_resolver(resolver, skip_test=skip_test)

        try:
            if not is_crystal_resonance_addon_active():
                return result

            target_sim_info = _resolve_participant_sim_info(
                resolver,
                ("TargetSim", "Target", "PickedSim"),
            )
            if target_sim_info is None:
                log.warning("Gifted crystal resonance loot could not resolve target sim_info.")
                return result

            gifted_object = _resolve_participant_object(
                resolver,
                ("PickedObject", "Object"),
            )
            if gifted_object is None:
                log.warning("Gifted crystal resonance loot could not resolve gifted object.")
                return result

            crystal_key = identify_crystal_key(gifted_object)
            if not crystal_key:
                return result

            allowed_keys = set(allowed_crystal_keys_for_payload(chart_payload_for_sim(target_sim_info)))
            if crystal_key not in allowed_keys:
                return result

            sim_id = _sim_id_value(target_sim_info)
            if sim_id is None:
                log.warning("Gifted crystal resonance loot could not resolve target sim id.")
                return result

            now_ticks = _current_sim_absolute_ticks()
            duration_ticks = _sim_minutes_to_ticks(_CRYSTAL_RESONANCE_GIFT_ATTUNEMENT_MINUTES)
            if now_ticks is None or duration_ticks is None:
                log.warning("Gifted crystal resonance loot could not resolve attunement timing.")
                return result

            object_id = getattr(gifted_object, "id", None) or getattr(gifted_object, "guid64", None) or 0
            register_gifted_attunement(
                sim_id,
                crystal_key,
                object_id=int(object_id),
                now_ticks=int(now_ticks),
                duration_ticks=int(duration_ticks),
            )
            mark_sim_dirty(
                target_sim_info,
                (SCOPE_CRYSTAL_RESONANCE,),
                reason="gifted_crystal_resonance",
            )
        except Exception:
            log.exception("Gifted crystal resonance loot bridge failed.")

        return result


class CosmicEngineSetModeLockLoot(LootActions):
    """Persist the save-global lane choice when Cosmic onboarding starts."""

    def apply_to_resolver(self, resolver, skip_test=False):
        result = super().apply_to_resolver(resolver, skip_test=skip_test)
        try:
            set_mode_lock("cosmic", source="cosmic.onboarding")
            sync_mode_lock_traits()
        except Exception:
            log.exception("Cosmic mode-lock loot bridge failed.")
        return result


class SimstrologyClearModeLockLoot(LootActions):
    """Clear the save-global onboarding choice for a full clean-slate reset."""

    def apply_to_resolver(self, resolver, skip_test=False):
        result = super().apply_to_resolver(resolver, skip_test=skip_test)
        try:
            clear_mode_lock(source="simstrology.remove_all")
            sync_mode_lock_traits()
        except Exception:
            log.exception("Simstrology clear-mode-lock loot bridge failed.")
        return result


class SimstrologyClearChildhoodTraitsLoot(LootActions):
    """Remove stranded Childhood sign traits without requiring the add-on package."""

    def apply_to_resolver(self, resolver, skip_test=False):
        result = super().apply_to_resolver(resolver, skip_test=skip_test)

        try:
            from .first_load_chooser import _CHILD_SIGN_TRAIT_IDS
        except Exception:
            _CHILD_SIGN_TRAIT_IDS = ()

        try:
            sim_info = _resolve_actor_sim_info(resolver)
            if sim_info is None:
                sim_info = _resolve_participant_sim_info(
                    resolver,
                    ("TargetSim", "Object", "Target", "PickedSim"),
                )
            if sim_info is None:
                log.warning("Simstrology childhood-trait clear loot could not resolve sim.")
                return result

            removed = 0
            for trait_id in tuple(_CHILD_SIGN_TRAIT_IDS):
                if _remove_trait_if_present(sim_info, int(trait_id)):
                    removed += 1

            if removed:
                log.info(
                    "Removed %s stranded Childhood sign trait(s) from sim %s during reset.",
                    int(removed),
                    getattr(sim_info, "sim_id", None) or getattr(sim_info, "id", None),
                )
        except Exception:
            log.exception("Simstrology childhood-trait clear loot bridge failed.")

        return result


class SimstrologyRepairTeenHandoffLoot(LootActions):
    """Force a selected Sim through the Childhood -> teen+ repair pass."""

    def apply_to_resolver(self, resolver, skip_test=False):
        result = super().apply_to_resolver(resolver, skip_test=skip_test)

        try:
            from .first_load_chooser import repair_childhood_teen_handoff
        except Exception:
            repair_childhood_teen_handoff = None

        try:
            sim_info = _resolve_actor_sim_info(resolver)
            if sim_info is None:
                sim_info = _resolve_participant_sim_info(
                    resolver,
                    ("TargetSim", "Object", "Target", "PickedSim"),
                )
            if sim_info is None:
                log.warning("Simstrology teen-handoff repair loot could not resolve sim.")
                return result

            if callable(repair_childhood_teen_handoff):
                summary = repair_childhood_teen_handoff(sim_info)
                log.info("Teen-handoff repair summary: %s", summary)
        except Exception:
            log.exception("Simstrology teen-handoff repair loot bridge failed.")

        return result


class CosmicEngineRefreshV2SelfLoot(LootActions):
    """Run the existing V2 refresh/migration repair path from the self hub."""

    def apply_to_resolver(self, resolver, skip_test=False):
        result = super().apply_to_resolver(resolver, skip_test=skip_test)

        try:
            sim_info = _resolve_actor_sim_info(resolver)
            if sim_info is None:
                sim_info = _resolve_participant_sim_info(
                    resolver,
                    ("TargetSim", "Object", "Target", "PickedSim"),
                )
            if sim_info is None:
                log.warning("Simstrology V2 refresh loot could not resolve sim.")
                return result

            summary = migrate_legacy_v2_household_for_sim_info(sim_info)
            title = "Simstrology Refreshed"
            if summary.get("ok"):
                pass_count = int(summary.get("pass_count", 0) or 0)
                text = (
                    "Checked this household's V2 Simstrology state and refreshed "
                    "visible signs, markers, and legacy handoff data."
                )
                if pass_count > 0:
                    text += " Repair passes run: {0}.".format(pass_count)
            else:
                reason = str(summary.get("reason") or "unknown_state").replace("_", " ")
                text = "Simstrology refresh could not run ({0}).".format(reason)

            _show_simple_notification(sim_info, title, text)
        except Exception:
            log.exception("Simstrology V2 refresh loot bridge failed.")

        return result


class SimstrologyClearNonHumanTraitsLoot(LootActions):
    """Sweep non-human sims and remove any Simstrology state that slipped onto them."""

    def apply_to_resolver(self, resolver, skip_test=False):
        result = super().apply_to_resolver(resolver, skip_test=skip_test)

        try:
            summary = clear_simstrology_state_from_non_humans()
            log.info("Non-human Simstrology cleanup summary: %s", summary)
        except Exception:
            log.exception("Simstrology non-human cleanup loot bridge failed.")

        return result


class CosmicEnginePrettyCommandLoot(LootActions):
    """Render a registered pretty command payload through an in-game notification."""

    INSTANCE_TUNABLES = {
        "command_name": Tunable(
            description="Registered pretty command name to display.",
            tunable_type=str,
            default="ce.transit.pretty",
        ),
    }

    def apply_to_resolver(self, resolver, skip_test=False):
        result = super().apply_to_resolver(resolver, skip_test=skip_test)
        command_name = str(
            getattr(self, "command_name", "ce.transit.pretty") or "ce.transit.pretty"
        ).strip().lower()

        try:
            owner = _resolve_actor_sim_info(resolver)
            if owner is None:
                owner = _resolve_participant_sim_info(
                    resolver,
                    ("TargetSim", "Object", "Target", "PickedSim"),
                )
            if not show_pretty_command_notification(owner, command_name):
                log.warning(
                    "Pretty command loot could not render command '%s'.",
                    command_name,
                )
        except Exception:
            log.exception(
                "Pretty command loot bridge failed for command '%s'.",
                command_name,
            )

        return result


class CosmicEngineReseedMarsPlusLoot(LootActions):
    """Reseed the save-wide Mars-plus transit sky and confirm the result in UI."""

    def apply_to_resolver(self, resolver, skip_test=False):
        result = super().apply_to_resolver(resolver, skip_test=skip_test)

        try:
            from .natal_snapshot_markers import sync_zone_natal_snapshots
            from .ts4_runtime_install import persist_now

            owner = _resolve_actor_sim_info(resolver)
            if owner is None:
                owner = _resolve_participant_sim_info(
                    resolver,
                    ("TargetSim", "Object", "Target", "PickedSim"),
                )

            summary = get_global_transit_service().reseed_mars_plus()
            chart_refresh = get_global_transit_service().clear_dynamic_chart_record_payloads()
            natal_summary = sync_zone_natal_snapshots()
            persisted = persist_now(reason="debug.ce_transit_reseed_mars_plus")

            before = summary.get("mars_plus_before") or {}
            after = summary.get("mars_plus_after") or {}
            changed = [
                "{0}: {1} -> {2}".format(body, before.get(body), after.get(body))
                for body in ("Mars", "Jupiter", "Saturn", "Chiron", "Uranus", "Neptune", "Pluto")
                if before.get(body) != after.get(body)
            ]
            if not changed:
                changed = ["No Mars-plus signs changed on this roll."]
            text = (
                "Mars-plus transit placements were reseeded for this save.\n"
                "{0}\n"
                "Chart caches refreshed: {1}\n"
                "Natal sync updates: {2}\n"
                "Persisted: {3}"
            ).format(
                "\n".join(changed),
                int(chart_refresh.get("removed_count", 0) or 0),
                int(natal_summary.get("sims_changed", 0) or 0),
                "Yes" if bool(persisted) else "No",
            )
            if owner is not None and not _show_simple_notification(
                owner,
                "Mars-Plus Sky Reseeded",
                text,
            ):
                log.warning("Mars-plus reseed loot could not show confirmation notification.")
        except Exception:
            log.exception("Mars-plus reseed loot bridge failed.")

        return result


class CosmicEngineSyncLegacyChartCompositionLoot(LootActions):
    """Sync deprecated single-value element/mode outputs from chart composition."""

    def apply_to_resolver(self, resolver, skip_test=False):
        result = super().apply_to_resolver(resolver, skip_test=skip_test)

        try:
            sim_info = _resolve_actor_sim_info(resolver)
            if sim_info is None:
                log.warning("Chart composition sync could not resolve actor sim_info.")
                return result

            sim_id = getattr(sim_info, "sim_id", None)
            if sim_id is None:
                sim_id = getattr(sim_info, "id", None)
            if sim_id is None:
                log.warning("Chart composition sync missing sim id.")
                return result

            payload = _chart_payload_for_sim(int(sim_id), sim_info=sim_info)
            if not isinstance(payload, dict):
                log.debug("Chart composition sync skipped; no chart payload for sim %s.", int(sim_id))
                return result

            chart_composition = build_chart_composition_from_chart_payload(payload)
            dominant_element = get_dominant_element(
                chart_composition,
                tie_behavior=_CHART_MARKER_TIE_BEHAVIOR,
            )
            dominant_mode = get_dominant_mode(
                chart_composition,
                tie_behavior=_CHART_MARKER_TIE_BEHAVIOR,
            )

            metadata = payload.get("metadata")
            if not isinstance(metadata, dict):
                metadata = {}
                payload["metadata"] = metadata
            metadata["chart_composition"] = dict(chart_composition)
            metadata["dominant_element"] = dominant_element
            metadata["dominant_mode"] = dominant_mode
            metadata["chart_marker_tie_behavior"] = _CHART_MARKER_TIE_BEHAVIOR
            # Deprecated compatibility shims: older Sun-only systems consumed a
            # single element/mode. We now expose one only when chart totals
            # produce a unique leader; tie handling is centrally configurable.
            metadata["legacy_primary_element"] = (
                dominant_element if dominant_element in _LEGACY_ELEMENT_TRAIT_IDS else None
            )
            metadata["legacy_primary_mode"] = (
                dominant_mode if dominant_mode in _LEGACY_MODE_TRAIT_IDS else None
            )
            metadata["chart_marker_trait_sync"] = apply_chart_marker_traits(
                sim_info,
                chart_composition,
                tie_behavior=_CHART_MARKER_TIE_BEHAVIOR,
            )
            metadata["chart_ruler_trait_sync"] = sync_chart_ruler_traits(sim_info)

            get_global_transit_service().set_chart_record_payload(int(sim_id), payload)
        except Exception:
            log.exception("Chart composition sync bridge failed.")

        return result


class CosmicEngineReadNatalChartSocialLoot(LootActions):
    """Show a step-by-step natal chart readout for the social interaction."""

    def apply_to_resolver(self, resolver, skip_test=False):
        result = super().apply_to_resolver(resolver, skip_test=skip_test)

        try:
            actor_sim_info = _resolve_actor_sim_info(resolver)
            if actor_sim_info is None:
                log.warning("Read chart loot could not resolve actor sim_info.")
                return result

            target_sim_info = _resolve_participant_sim_info(
                resolver,
                ("TargetSim", "Object", "Target", "PickedSim"),
            )
            if target_sim_info is None:
                log.warning("Read chart loot could not resolve target sim_info.")
                return result

            required_level = int(
                simstrology_skill_unlock_level("advanced_chart_reading", default=4)
            )
            actor_skill_level = int(get_simstrology_skill_level(actor_sim_info))
            if not simstrology_skill_meets(actor_sim_info, required_level):
                log.debug(
                    "Read chart loot blocked by Simstrology skill gate (actor=%s level=%s required=%s).",
                    _sim_display_name(actor_sim_info),
                    actor_skill_level,
                    required_level,
                )
                if not _show_chart_skill_gate_notification(
                    actor_sim_info,
                    required_level=required_level,
                    actor_skill_level=actor_skill_level,
                ):
                    log.warning(
                        "Read chart loot could not show skill-gate notification for %s.",
                        _sim_display_name(actor_sim_info),
                    )
                return result

            target_sim_id = getattr(target_sim_info, "sim_id", None)
            if target_sim_id is None:
                target_sim_id = getattr(target_sim_info, "id", None)

            payload = None
            if target_sim_id is not None:
                try:
                    payload = _chart_payload_for_sim(int(target_sim_id), sim_info=target_sim_info)
                except Exception:
                    payload = None

            title = "Chart Reading: {0}".format(_sim_display_name(target_sim_info))
            if not chart_readout_available(payload):
                text = "Natal chart data is not available for this Sim yet."
                if not _show_simple_notification(actor_sim_info, title, text):
                    log.warning(
                        "Read chart loot could not show unavailable notification for %s.",
                        _sim_display_name(target_sim_info),
                    )
                return result

            if not show_chart_readout_dialog_sequence(
                actor_sim_info,
                subject_name=_sim_display_name(target_sim_info),
                payload=payload,
            ):
                log.warning(
                    "Read chart loot could not show chart dialog sequence for %s.",
                    _sim_display_name(target_sim_info),
                )
        except Exception:
            log.exception("Read chart loot bridge failed.")

        return result


class CosmicEngineTransitWeatherSocialLoot(LootActions):
    """Show a lightweight random planet/sign sky readout for social chat."""

    def apply_to_resolver(self, resolver, skip_test=False):
        result = super().apply_to_resolver(resolver, skip_test=skip_test)

        try:
            actor_sim_info = _resolve_actor_sim_info(resolver)
            if actor_sim_info is None:
                log.warning("Transit weather loot could not resolve actor sim_info.")
                return result

            required_level = int(
                simstrology_skill_unlock_level("advanced_chart_reading", default=4)
            )
            actor_skill_level = int(get_simstrology_skill_level(actor_sim_info))
            if not simstrology_skill_meets(actor_sim_info, required_level):
                log.debug(
                    "Transit weather loot blocked by Simstrology skill gate (actor=%s level=%s required=%s).",
                    _sim_display_name(actor_sim_info),
                    actor_skill_level,
                    required_level,
                )
                return result

            service = get_global_transit_service()
            state = getattr(service, "state", None)
            sign_index_by_body = getattr(state, "sign_index_by_body", None)
            if not isinstance(sign_index_by_body, dict):
                log.warning("Transit weather loot missing transit sign map.")
                return result

            available_bodies = [
                body
                for body in _active_transit_weather_body_names(service)
                if body in sign_index_by_body
            ]
            if not available_bodies:
                log.warning("Transit weather loot found no tracked planets.")
                return result

            body = random.choice(available_bodies)
            body_sign_index = int(sign_index_by_body.get(body, 0)) % len(_ZODIAC_SIGNS)
            body_sign_name = _ZODIAC_SIGNS[body_sign_index]

            if body == "Moon":
                lunar_phase_name = _current_lunar_phase_name()
                phase_label = _LUNAR_PHASE_NAME_LABELS.get(str(lunar_phase_name or "").upper())
                if phase_label:
                    text = "The Moon is {0} and it's in {1} right now.".format(
                        phase_label,
                        body_sign_name,
                    )
                else:
                    text = "The Moon is in {0} right now.".format(body_sign_name)
            else:
                text = "{0} is in {1} right now.".format(body, body_sign_name)

            if not _show_simple_notification(actor_sim_info, "Astrological Weather", text):
                log.warning(
                    "Transit weather loot could not show notification for %s.",
                    _sim_display_name(actor_sim_info),
                )
        except Exception:
            log.exception("Transit weather loot bridge failed.")

        return result


class CosmicEngineCareerWeatherSocialLoot(LootActions):
    """Show a richer two-line cosmic weather readout for career socials."""

    def apply_to_resolver(self, resolver, skip_test=False):
        result = super().apply_to_resolver(resolver, skip_test=skip_test)

        try:
            actor_sim_info = _resolve_actor_sim_info(resolver)
            if actor_sim_info is None:
                log.warning("Career weather loot could not resolve actor sim_info.")
                return result

            service = get_global_transit_service()
            state = getattr(service, "state", None)
            sign_index_by_body = getattr(state, "sign_index_by_body", None)
            if not isinstance(sign_index_by_body, dict):
                log.warning("Career weather loot missing transit sign map.")
                return result

            available_bodies = [
                body
                for body in _active_transit_weather_body_names(service)
                if body in sign_index_by_body
            ]
            if not available_bodies:
                log.warning("Career weather loot found no tracked planets.")
                return result

            lines = []

            if "Moon" in sign_index_by_body:
                moon_sign_index = int(sign_index_by_body.get("Moon", 0)) % len(_ZODIAC_SIGNS)
                moon_sign_name = _ZODIAC_SIGNS[moon_sign_index]
                lunar_phase_name = _current_lunar_phase_name()
                phase_label = _LUNAR_PHASE_NAME_LABELS.get(str(lunar_phase_name or "").upper())
                if phase_label:
                    lines.append(
                        "Moon watch: The Moon is {0} in {1}.".format(
                            phase_label,
                            moon_sign_name,
                        )
                    )
                else:
                    lines.append(
                        "Moon watch: The Moon is in {0}.".format(moon_sign_name)
                    )

            retrograde_line = None
            try:
                active_by_body = service.retrograde_active_by_body()
            except Exception:
                active_by_body = {}

            if isinstance(active_by_body, dict):
                active_bodies = [
                    body
                    for body in ("Mercury", "Venus", "Mars", "Jupiter", "Saturn")
                    if bool(active_by_body.get(body))
                ]
                if active_bodies:
                    retro_body = random.choice(active_bodies)
                    retro_sign_index = int(sign_index_by_body.get(retro_body, 0)) % len(_ZODIAC_SIGNS)
                    retro_sign_name = _ZODIAC_SIGNS[retro_sign_index]
                    retrograde_line = "{0} is retrograde in {1}.".format(
                        retro_body,
                        retro_sign_name,
                    )
                else:
                    retrograde_line = "No major retrogrades are active right now."

            if retrograde_line:
                lines.append("Retrograde watch: {0}".format(retrograde_line))

            if len(lines) < 2:
                remaining_bodies = [body for body in available_bodies if body != "Moon"]
                if remaining_bodies:
                    body = random.choice(remaining_bodies)
                    body_sign_index = int(sign_index_by_body.get(body, 0)) % len(_ZODIAC_SIGNS)
                    body_sign_name = _ZODIAC_SIGNS[body_sign_index]
                    lines.append(
                        "Transit spotlight: {0} is in {1}.".format(body, body_sign_name)
                    )

            if not lines:
                body = random.choice(available_bodies)
                body_sign_index = int(sign_index_by_body.get(body, 0)) % len(_ZODIAC_SIGNS)
                body_sign_name = _ZODIAC_SIGNS[body_sign_index]
                lines.append(
                    "Transit spotlight: {0} is in {1}.".format(body, body_sign_name)
                )

            text = "\n".join(lines[:2])
            if not _show_simple_notification(actor_sim_info, "Simstrological Weather", text):
                log.warning(
                    "Career weather loot could not show notification for %s.",
                    _sim_display_name(actor_sim_info),
                )
        except Exception:
            log.exception("Career weather loot bridge failed.")

        return result


class CosmicEngineSyncChartRulerTraitsLoot(LootActions):
    """Sync chart ruler marker traits from Rising with a Level 4 visible gate."""

    def apply_to_resolver(self, resolver, skip_test=False):
        result = super().apply_to_resolver(resolver, skip_test=skip_test)

        try:
            sim_info = _resolve_actor_sim_info(resolver)
            if sim_info is None:
                log.warning("Chart ruler sync could not resolve actor sim_info.")
                return result

            sync_chart_ruler_traits(sim_info)
        except Exception:
            log.exception("Chart ruler sync bridge failed.")

        return result


class CosmicEngineNatalOnboardActiveHouseholdLoot(LootActions):
    """Run active-household natal onboarding after Rising assignment interactions."""

    def apply_to_resolver(self, resolver, skip_test=False):
        result = super().apply_to_resolver(resolver, skip_test=skip_test)

        global _LAST_NATAL_ONBOARD_DEBUG
        global _NATAL_ONBOARD_LOOT_IN_PROGRESS
        acquired_lock = False
        try:
            sim_info = _resolve_actor_sim_info(resolver)
            if sim_info is None:
                log.warning("Natal onboarding loot could not resolve actor sim_info.")
                return result

            household_id = getattr(sim_info, "household_id", None)
            if household_id is None:
                household = getattr(sim_info, "household", None)
                household_id = getattr(household, "id", None)
            if household_id is None:
                log.warning("Natal onboarding loot missing household id.")
                return result
            household_id = int(household_id)

            now = time.monotonic()
            last_run = _NATAL_ONBOARD_LAST_RUN_BY_HOUSEHOLD_ID.get(household_id)
            if last_run is not None and (now - float(last_run)) < _NATAL_ONBOARD_DEBOUNCE_SECONDS:
                log.debug(
                    "Natal onboarding loot skipped (debounced) for household %s (dt=%.3fs).",
                    household_id,
                    now - float(last_run),
                )
                return result

            if _NATAL_ONBOARD_LOOT_IN_PROGRESS:
                log.debug(
                    "Natal onboarding loot skipped (re-entrant) for household %s.",
                    household_id,
                )
                return result

            # Lazy imports avoid module cycles at runtime.
            from .natal_snapshot_markers import (
                apply_visible_rising_timed_buff_for_sim_info,
            )
            from .runtime_hooks import dispatch_household_onboard

            _NATAL_ONBOARD_LOOT_IN_PROGRESS = True
            acquired_lock = True
            started = time.monotonic()
            bridge_report = dispatch_household_onboard(
                household_id,
                refresh_marker_cache=False,
                teen_sign_seed_mode="current_sky",
            )
            summary = dict((bridge_report or {}).get("addon_summaries", {}).get("core_onboarding", {}))
            rising_buff_summary = apply_visible_rising_timed_buff_for_sim_info(
                sim_info,
                refresh_marker_cache=False,
            )
            elapsed = max(0.0, time.monotonic() - started)
            _NATAL_ONBOARD_LAST_RUN_BY_HOUSEHOLD_ID[household_id] = time.monotonic()
            _LAST_NATAL_ONBOARD_DEBUG = {
                "kind": "household_onboard",
                "mode": "current_sky",
                "household_id": int(household_id),
                "elapsed_seconds": float(elapsed),
                "summary": dict(summary) if isinstance(summary, dict) else {},
                "rising_buff_summary": (
                    dict(rising_buff_summary) if isinstance(rising_buff_summary, dict) else {}
                ),
            }
            log.debug(
                "Natal onboarding loot synced household %s in %.3fs (seeded_total=%s, preteen=%s, teen=%s, rising_buff_applied=%s).",
                household_id,
                elapsed,
                summary.get("total_sims_seeded"),
                summary.get("preteen_sims_seeded"),
                summary.get("teen_sims_seeded"),
                rising_buff_summary.get("buff_applied"),
            )
            mark_sim_dirty(
                sim_info,
                _POST_ONBOARD_DIRTY_SCOPES,
                reason="loot.natal_onboard_household",
            )
        except Exception:
            log.exception("Natal onboarding loot bridge failed.")
        finally:
            if acquired_lock:
                _NATAL_ONBOARD_LOOT_IN_PROGRESS = False

        return result


class CosmicEngineNatalOnboardActiveHouseholdRandomSunMoonLoot(LootActions):
    """Run active-household natal onboarding with per-sim Sun/Moon randomization after random Rising."""

    def apply_to_resolver(self, resolver, skip_test=False):
        result = super().apply_to_resolver(resolver, skip_test=skip_test)

        global _LAST_NATAL_ONBOARD_DEBUG
        global _NATAL_ONBOARD_LOOT_IN_PROGRESS
        acquired_lock = False
        try:
            sim_info = _resolve_actor_sim_info(resolver)
            if sim_info is None:
                log.warning("Natal onboarding random Sun/Moon loot could not resolve actor sim_info.")
                return result

            household_id = getattr(sim_info, "household_id", None)
            if household_id is None:
                household = getattr(sim_info, "household", None)
                household_id = getattr(household, "id", None)
            if household_id is None:
                log.warning("Natal onboarding random Sun/Moon loot missing household id.")
                return result
            household_id = int(household_id)

            if _NATAL_ONBOARD_LOOT_IN_PROGRESS:
                log.debug(
                    "Natal onboarding random Sun/Moon loot skipped (re-entrant) for household %s.",
                    household_id,
                )
                return result

            # Lazy imports avoid module cycles at runtime.
            from .natal_snapshot_markers import (
                apply_visible_rising_timed_buff_for_sim_info,
            )
            from .runtime_hooks import dispatch_household_onboard

            _NATAL_ONBOARD_LOOT_IN_PROGRESS = True
            acquired_lock = True
            started = time.monotonic()
            bridge_report = dispatch_household_onboard(
                household_id,
                refresh_marker_cache=False,
                teen_sign_seed_mode="random_sun_moon",
            )
            summary = dict((bridge_report or {}).get("addon_summaries", {}).get("core_onboarding", {}))
            rising_buff_summary = apply_visible_rising_timed_buff_for_sim_info(
                sim_info,
                refresh_marker_cache=False,
            )
            elapsed = max(0.0, time.monotonic() - started)
            _NATAL_ONBOARD_LAST_RUN_BY_HOUSEHOLD_ID[household_id] = time.monotonic()
            _LAST_NATAL_ONBOARD_DEBUG = {
                "kind": "household_onboard",
                "mode": "random_sun_moon",
                "household_id": int(household_id),
                "elapsed_seconds": float(elapsed),
                "summary": dict(summary) if isinstance(summary, dict) else {},
                "rising_buff_summary": (
                    dict(rising_buff_summary) if isinstance(rising_buff_summary, dict) else {}
                ),
            }
            log.debug(
                "Natal onboarding random Sun/Moon loot synced household %s in %.3fs (seeded_total=%s, preteen=%s, teen=%s, rising_buff_applied=%s).",
                household_id,
                elapsed,
                summary.get("total_sims_seeded"),
                summary.get("preteen_sims_seeded"),
                summary.get("teen_sims_seeded"),
                rising_buff_summary.get("buff_applied"),
            )
            mark_sim_dirty(
                sim_info,
                _POST_ONBOARD_DIRTY_SCOPES,
                reason="loot.natal_onboard_random_sun_moon",
            )
        except Exception:
            log.exception("Natal onboarding random Sun/Moon loot bridge failed.")
        finally:
            if acquired_lock:
                _NATAL_ONBOARD_LOOT_IN_PROGRESS = False

        return result
