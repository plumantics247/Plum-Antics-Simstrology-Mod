"""Runtime seeding helpers for sign compatibility preference traits."""

from __future__ import annotations

from typing import Dict, Iterable, Optional

from .sim_eligibility import sim_info_is_teen_plus


SIGN_NAMES = (
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
ELEMENT_BY_SIGN_INDEX = {
    0: "Fire",
    1: "Earth",
    2: "Air",
    3: "Water",
    4: "Fire",
    5: "Earth",
    6: "Air",
    7: "Water",
    8: "Fire",
    9: "Earth",
    10: "Air",
    11: "Water",
}
SAME_ELEMENT_POOL_BY_ELEMENT = {
    "Fire": (0, 4, 8),
    "Earth": (1, 5, 9),
    "Air": (2, 6, 10),
    "Water": (3, 7, 11),
}
CLASHING_POOL_BY_ELEMENT = {
    "Fire": (3, 7, 11),
    "Water": (0, 4, 8),
    "Air": (1, 5, 9),
    "Earth": (2, 6, 10),
}
LANE_TRAIT_BASES = {
    "Sun": {"like": 4100020000, "dislike": 4100030000},
    "Moon": {"like": 4100120000, "dislike": 4100130000},
    "Rising": {"like": 4100220000, "dislike": 4100230000},
}
MOON_EA_ATTRACTION_TRAIT_IDS = {
    0: {"turn_on": 363941, "turn_off": 363942},
    1: {"turn_on": 363943, "turn_off": 363940},
    2: {"turn_on": 363937, "turn_off": 363952},
    3: {"turn_on": 363935, "turn_off": 363924},
    4: {"turn_on": 363957, "turn_off": 363952},
    5: {"turn_on": 363929, "turn_off": 363946},
    6: {"turn_on": 363951, "turn_off": 363924},
    7: {"turn_on": 363933, "turn_off": 363930},
    8: {"turn_on": 363941, "turn_off": 363952},
    9: {"turn_on": 363939, "turn_off": 363398},
    10: {"turn_on": 363927, "turn_off": 363930},
    11: {"turn_on": 363945, "turn_off": 363924},
}
SEED_VERSION = 5
LANE_EA_TRAIT_IDS = {
    "Sun": {
        0: {"like": 305964, "dislike": 306407},
        1: {"like": 305965, "dislike": 306414},
        2: {"like": 305970, "dislike": 306420},
        3: {"like": 305971, "dislike": 306408},
        4: {"like": 305966, "dislike": 306420},
        5: {"like": 305972, "dislike": 306410},
        6: {"like": 305971, "dislike": 306408},
        7: {"like": 305970, "dislike": 306410},
        8: {"like": 305964, "dislike": 306417},
        9: {"like": 305972, "dislike": 306407},
        10: {"like": 305970, "dislike": 306410},
        11: {"like": 305947, "dislike": 306408},
    },
    "Moon": {
        0: {"like": 306473, "dislike": 306483},
        1: {"like": 306474, "dislike": 306482},
        2: {"like": 306469, "dislike": 306486},
        3: {"like": 306474, "dislike": 306492},
        4: {"like": 306464, "dislike": 306483},
        5: {"like": 306477, "dislike": 306496},
        6: {"like": 306474, "dislike": 306482},
        7: {"like": 306465, "dislike": 306497},
        8: {"like": 306466, "dislike": 306483},
        9: {"like": 306477, "dislike": 306494},
        10: {"like": 306465, "dislike": 306481},
        11: {"like": 306466, "dislike": 306492},
    },
    "Rising": {
        0: {"like": 306473, "dislike": 306497},
        1: {"like": 306464, "dislike": 306482},
        2: {"like": 306478, "dislike": 306486},
        3: {"like": 306464, "dislike": 306492},
        4: {"like": 306464, "dislike": 306483},
        5: {"like": 306477, "dislike": 306496},
        6: {"like": 306464, "dislike": 306482},
        7: {"like": 306471, "dislike": 306497},
        8: {"like": 306466, "dislike": 306483},
        9: {"like": 306477, "dislike": 306494},
        10: {"like": 306469, "dislike": 306484},
        11: {"like": 306466, "dislike": 306482},
    },
}
MANAGED_SIGN_COMPATIBILITY_TRAIT_IDS = frozenset(
    int(base) + sign_ordinal
    for lane_map in LANE_TRAIT_BASES.values()
    for base in lane_map.values()
    for sign_ordinal in range(1, len(SIGN_NAMES) + 1)
)
MANAGED_EA_PREFERENCE_TRAIT_IDS = frozenset(
    int(slot_trait_id)
    for lane_map in LANE_EA_TRAIT_IDS.values()
    for sign_map in lane_map.values()
    for slot_trait_id in sign_map.values()
)
MANAGED_EA_ATTRACTION_TRAIT_IDS = frozenset(
    int(slot_trait_id)
    for sign_map in MOON_EA_ATTRACTION_TRAIT_IDS.values()
    for slot_trait_id in sign_map.values()
)


def _coerce_int(value) -> Optional[int]:
    try:
        return int(value)
    except Exception:
        return None


def _sim_id_value(sim_info) -> Optional[int]:
    if sim_info is None:
        return None
    for attr_name in ("sim_id", "id", "guid64"):
        value = _coerce_int(getattr(sim_info, attr_name, None))
        if value is not None:
            return int(value)
    return None


def normalize_sign_index(value) -> Optional[int]:
    coerced = _coerce_int(value)
    if coerced is None:
        return None
    return int(coerced) % len(SIGN_NAMES)


def build_chart_signature(
    sun_sign_index,
    moon_sign_index,
    rising_sign_index,
) -> Optional[str]:
    indexes = (
        normalize_sign_index(sun_sign_index),
        normalize_sign_index(moon_sign_index),
        normalize_sign_index(rising_sign_index),
    )
    if any(value is None for value in indexes):
        return None
    return "{0}:{1}:{2}".format(*indexes)


def preference_trait_id(lane_name: str, polarity: str, sign_index) -> Optional[int]:
    normalized_index = normalize_sign_index(sign_index)
    lane_bases = LANE_TRAIT_BASES.get(str(lane_name))
    if normalized_index is None or not isinstance(lane_bases, dict):
        return None
    return int(lane_bases[str(polarity)]) + normalized_index + 1


def ea_preference_trait_id(lane_name: str, polarity: str, sign_index) -> Optional[int]:
    normalized_index = normalize_sign_index(sign_index)
    lane_map = LANE_EA_TRAIT_IDS.get(str(lane_name))
    if normalized_index is None or not isinstance(lane_map, dict):
        return None
    sign_map = lane_map.get(int(normalized_index))
    if not isinstance(sign_map, dict):
        return None
    trait_id = _coerce_int(sign_map.get(str(polarity)))
    return None if trait_id is None else int(trait_id)


def moon_ea_attraction_trait_id(polarity: str, sign_index) -> Optional[int]:
    normalized_index = normalize_sign_index(sign_index)
    if normalized_index is None:
        return None
    sign_map = MOON_EA_ATTRACTION_TRAIT_IDS.get(int(normalized_index))
    if not isinstance(sign_map, dict):
        return None
    trait_id = _coerce_int(sign_map.get(str(polarity)))
    return None if trait_id is None else int(trait_id)


def resolve_dislike_pool_sign_indexes(seed_sign_index) -> tuple:
    normalized_index = normalize_sign_index(seed_sign_index)
    if normalized_index is None:
        return ()
    return tuple(CLASHING_POOL_BY_ELEMENT[ELEMENT_BY_SIGN_INDEX[normalized_index]])


def resolve_like_pool_sign_indexes(seed_sign_index) -> tuple:
    normalized_index = normalize_sign_index(seed_sign_index)
    if normalized_index is None:
        return ()
    return tuple(SAME_ELEMENT_POOL_BY_ELEMENT[ELEMENT_BY_SIGN_INDEX[normalized_index]])


def resolve_trait_ids_for_sign_indexes(lane_name: str, polarity: str, sign_indexes) -> tuple:
    resolved = []
    for sign_index in tuple(sign_indexes or ()):
        trait_id = preference_trait_id(lane_name, polarity, sign_index)
        if trait_id is not None:
            resolved.append(int(trait_id))
    return tuple(resolved)


def build_lane_seed_payload(lane_name: str, seed_sign_index) -> Optional[Dict[str, object]]:
    normalized_index = normalize_sign_index(seed_sign_index)
    if normalized_index is None:
        return None
    like_sign_indexes = resolve_like_pool_sign_indexes(normalized_index)
    dislike_pool = resolve_dislike_pool_sign_indexes(normalized_index)
    like_trait_ids = resolve_trait_ids_for_sign_indexes(
        lane_name, "like", like_sign_indexes
    )
    dislike_trait_ids = resolve_trait_ids_for_sign_indexes(
        lane_name, "dislike", dislike_pool
    )
    return {
        "seed_sign_index": normalized_index,
        "seed_sign_name": SIGN_NAMES[normalized_index],
        "auto_like_sign_indexes": like_sign_indexes,
        "auto_dislike_sign_indexes": dislike_pool,
        "auto_like_trait_ids": like_trait_ids,
        "auto_dislike_trait_ids": dislike_trait_ids,
        "ea_like_trait_id": ea_preference_trait_id(lane_name, "like", normalized_index),
        "ea_dislike_trait_id": ea_preference_trait_id(
            lane_name, "dislike", normalized_index
        ),
        "ea_attraction_turn_on_trait_id": (
            moon_ea_attraction_trait_id("turn_on", normalized_index)
            if str(lane_name) == "Moon"
            else None
        ),
        "ea_attraction_turn_off_trait_id": (
            moon_ea_attraction_trait_id("turn_off", normalized_index)
            if str(lane_name) == "Moon"
            else None
        ),
    }


def build_expected_sign_compatibility_seed_record(
    *,
    sun_sign_index,
    moon_sign_index,
    rising_sign_index,
) -> Optional[Dict[str, object]]:
    signature = build_chart_signature(sun_sign_index, moon_sign_index, rising_sign_index)
    if signature is None:
        return None

    lanes = {
        "Sun": build_lane_seed_payload("Sun", sun_sign_index),
        "Moon": build_lane_seed_payload("Moon", moon_sign_index),
        "Rising": build_lane_seed_payload("Rising", rising_sign_index),
    }
    if any(not isinstance(lane_payload, dict) for lane_payload in lanes.values()):
        return None

    trait_ids_flat = sorted(
        {
            int(normalized_trait_id)
            for lane_payload in lanes.values()
            for normalized_trait_id in (
                _coerce_int(trait_id)
                for trait_id in (
                    *tuple(lane_payload.get("auto_like_trait_ids") or ()),
                    *tuple(lane_payload.get("auto_dislike_trait_ids") or ()),
                    lane_payload["ea_like_trait_id"],
                    lane_payload["ea_dislike_trait_id"],
                    lane_payload.get("ea_attraction_turn_on_trait_id"),
                    lane_payload.get("ea_attraction_turn_off_trait_id"),
                )
            )
            if normalized_trait_id is not None
        }
    )

    return {
        "seed_version": SEED_VERSION,
        "chart_signature": signature,
        "sun_sign_index": normalize_sign_index(sun_sign_index),
        "moon_sign_index": normalize_sign_index(moon_sign_index),
        "rising_sign_index": normalize_sign_index(rising_sign_index),
        "lanes": lanes,
        "trait_ids_flat": tuple(trait_ids_flat),
    }


def _normalized_chart_indexes(chart_payload) -> Optional[Dict[str, int]]:
    if not isinstance(chart_payload, dict):
        return None
    sun_sign_index = normalize_sign_index(chart_payload.get("sun_sign_index"))
    moon_sign_index = normalize_sign_index(chart_payload.get("moon_sign_index"))
    rising_sign_index = normalize_sign_index(chart_payload.get("rising_sign_index"))
    if None in (sun_sign_index, moon_sign_index, rising_sign_index):
        return None
    return {
        "sun_sign_index": sun_sign_index,
        "moon_sign_index": moon_sign_index,
        "rising_sign_index": rising_sign_index,
    }


def _runtime_owned_trait_ids_from_record(
    seed_record,
    lane_name: Optional[str] = None,
) -> frozenset:
    if not isinstance(seed_record, dict):
        return frozenset()
    lanes = seed_record.get("lanes")
    if not isinstance(lanes, dict):
        return frozenset()
    lane_names = (lane_name,) if isinstance(lane_name, str) else tuple(lanes.keys())
    owned = set()
    for current_lane_name in lane_names:
        lane_payload = lanes.get(current_lane_name)
        if not isinstance(lane_payload, dict):
            continue
        for trait_id in (
            *tuple(lane_payload.get("auto_like_trait_ids") or ()),
            *tuple(lane_payload.get("auto_dislike_trait_ids") or ()),
            lane_payload.get("ea_like_trait_id"),
            lane_payload.get("ea_dislike_trait_id"),
            lane_payload.get("ea_attraction_turn_on_trait_id"),
            lane_payload.get("ea_attraction_turn_off_trait_id"),
        ):
            trait_id = _coerce_int(trait_id)
            if trait_id is not None:
                owned.add(int(trait_id))
    return frozenset(owned)


def _seed_record_is_current(seed_record) -> bool:
    return bool(
        isinstance(seed_record, dict)
        and int(seed_record.get("seed_version", 0)) == SEED_VERSION
        and isinstance(seed_record.get("lanes"), dict)
        and isinstance(seed_record.get("chart_signature"), str)
    )


def _changed_lane_names(existing_seed_record, expected_seed_record) -> tuple:
    changed = []
    existing_lanes = existing_seed_record.get("lanes") if isinstance(existing_seed_record, dict) else None
    expected_lanes = expected_seed_record.get("lanes") if isinstance(expected_seed_record, dict) else None
    for lane_name in ("Sun", "Moon", "Rising"):
        existing_lane = existing_lanes.get(lane_name) if isinstance(existing_lanes, dict) else None
        expected_lane = expected_lanes.get(lane_name) if isinstance(expected_lanes, dict) else None
        if not isinstance(existing_lane, dict) or not isinstance(expected_lane, dict):
            changed.append(lane_name)
            continue
        if (
            existing_lane.get("seed_sign_index") != expected_lane.get("seed_sign_index")
            or tuple(existing_lane.get("auto_like_trait_ids") or ())
            != tuple(expected_lane.get("auto_like_trait_ids") or ())
            or tuple(existing_lane.get("auto_dislike_trait_ids") or ())
            != tuple(expected_lane.get("auto_dislike_trait_ids") or ())
            or existing_lane.get("ea_like_trait_id") != expected_lane.get("ea_like_trait_id")
            or existing_lane.get("ea_dislike_trait_id") != expected_lane.get("ea_dislike_trait_id")
            or existing_lane.get("ea_attraction_turn_on_trait_id")
            != expected_lane.get("ea_attraction_turn_on_trait_id")
            or existing_lane.get("ea_attraction_turn_off_trait_id")
            != expected_lane.get("ea_attraction_turn_off_trait_id")
        ):
            changed.append(lane_name)
    return tuple(changed)


def _changed_runtime_lane_names(existing_seed_record, expected_seed_record) -> tuple:
    changed = []
    existing_lanes = existing_seed_record.get("lanes") if isinstance(existing_seed_record, dict) else None
    expected_lanes = expected_seed_record.get("lanes") if isinstance(expected_seed_record, dict) else None
    for lane_name in ("Sun", "Moon", "Rising"):
        existing_lane = existing_lanes.get(lane_name) if isinstance(existing_lanes, dict) else None
        expected_lane = expected_lanes.get(lane_name) if isinstance(expected_lanes, dict) else None
        existing_value = (
            existing_lane.get("seed_sign_index")
            if isinstance(existing_lane, dict)
            else existing_seed_record.get("{0}_sign_index".format(str(lane_name).lower()))
            if isinstance(existing_seed_record, dict)
            else None
        )
        expected_value = (
            expected_lane.get("seed_sign_index")
            if isinstance(expected_lane, dict)
            else expected_seed_record.get("{0}_sign_index".format(str(lane_name).lower()))
            if isinstance(expected_seed_record, dict)
            else None
        )
        if normalize_sign_index(existing_value) != normalize_sign_index(expected_value):
            changed.append(lane_name)
    return tuple(changed)


def _all_runtime_lane_names() -> tuple:
    return ("Sun", "Moon", "Rising")


def _all_managed_trait_ids() -> frozenset:
    return (
        MANAGED_SIGN_COMPATIBILITY_TRAIT_IDS
        | MANAGED_EA_PREFERENCE_TRAIT_IDS
        | MANAGED_EA_ATTRACTION_TRAIT_IDS
    )


def sync_sign_compatibility_preferences_for_sim_info(
    sim_info,
    *,
    existing_seed_record,
    read_chart_payload,
    iter_trait_ids,
    add_trait_id,
    remove_trait_id,
    clear_runtime_lane_state,
):
    summary = {
        "ok": False,
        "reason": None,
        "sim_id": _sim_id_value(sim_info),
        "seed_record": None,
        "traits_removed": 0,
        "traits_added": 0,
        "runtime_lanes_cleared": [],
    }

    if sim_info is None:
        summary["reason"] = "missing_sim_info"
        return summary
    current_trait_ids = set()
    if callable(iter_trait_ids):
        for trait_id in iter_trait_ids(sim_info):
            normalized_trait_id = _coerce_int(trait_id)
            if normalized_trait_id is not None:
                current_trait_ids.add(int(normalized_trait_id))

    def _clear_stale_managed_state(clear_reason: str):
        managed_trait_ids = set(current_trait_ids & _all_managed_trait_ids())
        if _seed_record_is_current(existing_seed_record):
            managed_trait_ids |= set(_runtime_owned_trait_ids_from_record(existing_seed_record))

        has_persisted_seed = isinstance(existing_seed_record, dict)
        if not managed_trait_ids and not has_persisted_seed:
            summary["reason"] = str(clear_reason)
            return summary

        if callable(clear_runtime_lane_state):
            for lane_name in _all_runtime_lane_names():
                try:
                    clear_runtime_lane_state(sim_info, str(lane_name))
                    summary["runtime_lanes_cleared"].append(str(lane_name))
                except Exception:
                    continue

        for trait_id in sorted(managed_trait_ids):
            remove_trait_id(sim_info, int(trait_id))
        summary["traits_removed"] = len(managed_trait_ids)
        summary["traits_added"] = 0
        summary["seed_record"] = None
        summary["ok"] = True
        summary["reason"] = "cleared_{0}".format(str(clear_reason))
        return summary

    if not sim_info_is_teen_plus(sim_info):
        return _clear_stale_managed_state("ineligible_age")

    chart_payload = read_chart_payload(sim_info) if callable(read_chart_payload) else None
    indexes = _normalized_chart_indexes(chart_payload)
    if not isinstance(indexes, dict):
        return _clear_stale_managed_state("missing_big3")

    expected = build_expected_sign_compatibility_seed_record(**indexes)
    if not isinstance(expected, dict):
        return _clear_stale_managed_state("missing_big3")

    summary["seed_record"] = dict(expected)

    remove_ids = set()
    add_ids = set()
    runtime_changed_lanes = ()
    if _seed_record_is_current(existing_seed_record):
        changed_lanes = _changed_lane_names(existing_seed_record, expected)
        runtime_changed_lanes = _changed_runtime_lane_names(existing_seed_record, expected)
        if (
            not changed_lanes
            and existing_seed_record.get("chart_signature") == expected["chart_signature"]
        ):
            summary["ok"] = True
            summary["reason"] = "chart_unchanged"
            summary["seed_record"] = dict(existing_seed_record)
            return summary
        for lane_name in changed_lanes:
            remove_ids.update(
                _runtime_owned_trait_ids_from_record(existing_seed_record, lane_name)
            )
            add_ids.update(_runtime_owned_trait_ids_from_record(expected, lane_name))
        remove_ids &= current_trait_ids
        add_ids -= current_trait_ids
        summary["reason"] = "chart_changed"
    else:
        remove_ids = (
            set(
                current_trait_ids
                & (
                    MANAGED_SIGN_COMPATIBILITY_TRAIT_IDS
                    | MANAGED_EA_PREFERENCE_TRAIT_IDS
                    | MANAGED_EA_ATTRACTION_TRAIT_IDS
                )
            )
            if isinstance(existing_seed_record, dict)
            else set()
        )
        add_ids = set(_runtime_owned_trait_ids_from_record(expected))
        add_ids -= current_trait_ids
        summary["reason"] = (
            "seed_model_changed" if isinstance(existing_seed_record, dict) else "initial_seed"
        )
        runtime_changed_lanes = (
            _changed_runtime_lane_names(existing_seed_record, expected)
            if isinstance(existing_seed_record, dict)
            else ()
        )

    if callable(clear_runtime_lane_state):
        for lane_name in runtime_changed_lanes:
            try:
                clear_runtime_lane_state(sim_info, str(lane_name))
                summary["runtime_lanes_cleared"].append(str(lane_name))
            except Exception:
                continue

    for trait_id in sorted(remove_ids):
        remove_trait_id(sim_info, int(trait_id))
    summary["traits_removed"] = len(remove_ids)

    for trait_id in sorted(add_ids):
        add_trait_id(sim_info, int(trait_id))
    summary["traits_added"] = len(add_ids)

    summary["ok"] = True
    return summary


def sync_active_household_sign_compatibility_preferences(
    *,
    sim_infos,
    load_seed_record_for_sim,
    persist_seed_record_for_sim,
    remove_seed_record_for_sim=None,
    read_chart_payload,
    iter_trait_ids,
    add_trait_id,
    remove_trait_id,
    clear_runtime_lane_state,
):
    summary = {
        "ok": True,
        "reason": "processed",
        "sims_seen": 0,
        "sims_seeded": 0,
        "sims_refreshed": 0,
        "sims_unchanged": 0,
        "sims_skipped": 0,
        "sims_failed": 0,
    }

    for sim_info in tuple(sim_infos or ()):
        summary["sims_seen"] += 1
        sim_id = _sim_id_value(sim_info)
        existing_seed_record = None
        if sim_id is not None and callable(load_seed_record_for_sim):
            existing_seed_record = load_seed_record_for_sim(int(sim_id))

        sim_summary = sync_sign_compatibility_preferences_for_sim_info(
            sim_info,
            existing_seed_record=existing_seed_record,
            read_chart_payload=read_chart_payload,
            iter_trait_ids=iter_trait_ids,
            add_trait_id=add_trait_id,
            remove_trait_id=remove_trait_id,
            clear_runtime_lane_state=clear_runtime_lane_state,
        )
        reason = sim_summary.get("reason")

        if reason == "initial_seed":
            summary["sims_seeded"] += 1
        elif reason == "chart_changed":
            summary["sims_refreshed"] += 1
        elif reason == "seed_model_changed":
            summary["sims_refreshed"] += 1
        elif reason == "cleared_missing_big3":
            summary["sims_refreshed"] += 1
        elif reason == "cleared_ineligible_age":
            summary["sims_refreshed"] += 1
        elif reason == "chart_unchanged":
            summary["sims_unchanged"] += 1
        elif sim_summary.get("ok"):
            summary["sims_unchanged"] += 1
        else:
            summary["sims_skipped"] += 1

        seed_record = sim_summary.get("seed_record")
        if sim_summary.get("ok") and reason in (
            "initial_seed",
            "seed_model_changed",
            "chart_changed",
        ):
            if sim_id is None or not callable(persist_seed_record_for_sim):
                summary["ok"] = False
                summary["reason"] = "persist_failed"
                summary["sims_failed"] += 1
                continue
            persisted_ok = bool(
                persist_seed_record_for_sim(int(sim_id), dict(seed_record or {}))
            )
            if not persisted_ok:
                summary["ok"] = False
                summary["reason"] = "persist_failed"
                summary["sims_failed"] += 1
        elif sim_summary.get("ok") and reason in (
            "cleared_missing_big3",
            "cleared_ineligible_age",
        ):
            if sim_id is None or not callable(remove_seed_record_for_sim):
                continue
            removed_ok = bool(remove_seed_record_for_sim(int(sim_id)))
            if not removed_ok:
                summary["ok"] = False
                summary["reason"] = "persist_failed"
                summary["sims_failed"] += 1

    return summary


def sync_active_household_sign_compatibility_preferences_for_lifecycle(
    *, reason="runtime.household_onboard"
):
    try:
        from . import ts4_runtime_install as runtime_install
    except Exception:
        return {"ok": False, "reason": "runtime_import_failed"}

    target_sim_infos = tuple(runtime_install._iter_active_household_sim_infos())
    if not target_sim_infos:
        return {"ok": False, "reason": "no_household_sims"}

    adapter = runtime_install._get_persistence_adapter()
    try:
        return sync_active_household_sign_compatibility_preferences(
            sim_infos=target_sim_infos,
            load_seed_record_for_sim=lambda sim_id: (
                adapter.load_persisted_sign_compatibility_seed_profile()
                .get("sim_profiles", {})
                .get(str(int(sim_id)))
            ),
            persist_seed_record_for_sim=lambda sim_id, record: (
                adapter.persist_sign_compatibility_seed_profile(
                    int(sim_id),
                    dict(record or {}),
                    reason=reason,
                )
            ),
            remove_seed_record_for_sim=lambda sim_id: (
                adapter.remove_sign_compatibility_seed_profile(
                    int(sim_id),
                    reason=reason,
                )
            ),
            read_chart_payload=runtime_install._read_sign_compatibility_chart_payload,
            iter_trait_ids=runtime_install._iter_trait_ids_for_sim_info,
            add_trait_id=runtime_install._add_trait_id_for_sim_info,
            remove_trait_id=runtime_install._remove_trait_id_for_sim_info,
            clear_runtime_lane_state=runtime_install._clear_sign_compatibility_runtime_lane_state,
        )
    except Exception:
        return {"ok": False, "reason": "seed_failed"}


def sync_sign_compatibility_preferences_for_lifecycle_sim(
    sim_id, *, reason="runtime.age_transition"
):
    normalized_sim_id = _coerce_int(sim_id)
    if normalized_sim_id is None or normalized_sim_id <= 0:
        return {"ok": False, "reason": "missing_sim", "sim_id": None}

    try:
        from . import ts4_runtime_install as runtime_install
    except Exception:
        return {"ok": False, "reason": "runtime_import_failed", "sim_id": int(normalized_sim_id)}

    services = runtime_install._get_services_module()
    if services is None:
        return {"ok": False, "reason": "missing_sim", "sim_id": int(normalized_sim_id)}
    try:
        manager = services.sim_info_manager()
    except Exception:
        manager = None
    if manager is None:
        return {"ok": False, "reason": "missing_sim", "sim_id": int(normalized_sim_id)}
    try:
        sim_info = manager.get(int(normalized_sim_id))
    except Exception:
        sim_info = None
    if sim_info is None:
        return {"ok": False, "reason": "missing_sim", "sim_id": int(normalized_sim_id)}

    adapter = runtime_install._get_persistence_adapter()
    existing_seed_record = (
        adapter.load_persisted_sign_compatibility_seed_profile()
        .get("sim_profiles", {})
        .get(str(int(normalized_sim_id)))
    )
    summary = sync_sign_compatibility_preferences_for_sim_info(
        sim_info,
        existing_seed_record=existing_seed_record,
        read_chart_payload=runtime_install._read_sign_compatibility_chart_payload,
        iter_trait_ids=runtime_install._iter_trait_ids_for_sim_info,
        add_trait_id=runtime_install._add_trait_id_for_sim_info,
        remove_trait_id=runtime_install._remove_trait_id_for_sim_info,
        clear_runtime_lane_state=runtime_install._clear_sign_compatibility_runtime_lane_state,
    )
    summary["sim_id"] = int(normalized_sim_id)

    if summary.get("ok") and summary.get("reason") in ("initial_seed", "seed_model_changed", "chart_changed"):
        persisted_ok = bool(
            adapter.persist_sign_compatibility_seed_profile(
                int(normalized_sim_id),
                dict(summary.get("seed_record") or {}),
                reason=reason,
            )
        )
        if not persisted_ok:
            summary["ok"] = False
            summary["reason"] = "persist_failed"
    elif summary.get("ok") and summary.get("reason") in ("cleared_missing_big3", "cleared_ineligible_age"):
        removed_ok = bool(
            adapter.remove_sign_compatibility_seed_profile(
                int(normalized_sim_id),
                reason=reason,
            )
        )
        if not removed_ok:
            summary["ok"] = False
            summary["reason"] = "persist_failed"
    return summary
