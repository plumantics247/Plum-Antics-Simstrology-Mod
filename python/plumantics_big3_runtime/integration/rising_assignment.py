from __future__ import annotations


RISING_SUN_TIME_BUCKETS = {
    6: 0,
    8: 1,
    10: 2,
    12: 3,
    14: 4,
    16: 5,
    18: 6,
    20: 7,
    22: 8,
    0: 9,
    2: 10,
    4: 11,
}


def resolve_rising_sign_index_for_sun_time(sun_sign_index, hour_24):
    hour = int(hour_24) % 24
    if hour not in RISING_SUN_TIME_BUCKETS:
        raise ValueError("unsupported_rising_hour:{0}".format(hour))
    return (int(sun_sign_index) + int(RISING_SUN_TIME_BUCKETS[hour])) % 12


def apply_sun_time_rising_assignment(
    sim_info,
    *,
    sun_sign_index,
    hour_24,
    trait_ids_by_sign_index,
    has_trait_fn,
    add_trait_fn,
):
    if sim_info is None:
        return {"applied": False, "reason": "sim_missing"}

    rising_trait_id = int(
        trait_ids_by_sign_index[resolve_rising_sign_index_for_sun_time(sun_sign_index, hour_24)]
    )
    if has_trait_fn(sim_info, rising_trait_id):
        return {"applied": False, "reason": "already_has_rising"}

    added = bool(add_trait_fn(sim_info, rising_trait_id))
    return {
        "applied": added,
        "reason": "applied" if added else "trait_add_failed",
        "rising_trait_id": rising_trait_id,
    }


def apply_random_rising_assignment(
    sim_info,
    *,
    available_sign_indexes,
    trait_ids_by_sign_index,
    has_any_rising_trait_fn,
    has_trait_fn,
    add_trait_fn,
    choose_sign_index_fn,
):
    if sim_info is None:
        return {"applied": False, "reason": "sim_missing"}

    if has_any_rising_trait_fn(sim_info):
        return {"applied": False, "reason": "already_has_rising"}

    available_sign_indexes = tuple(available_sign_indexes or ())
    if not available_sign_indexes:
        return {"applied": False, "reason": "rising_trait_pool_empty"}

    rising_sign_index = int(choose_sign_index_fn(available_sign_indexes))
    rising_trait_id = int(trait_ids_by_sign_index[rising_sign_index])
    if has_trait_fn(sim_info, rising_trait_id):
        return {"applied": False, "reason": "already_has_rising"}

    added = bool(add_trait_fn(sim_info, rising_trait_id))
    return {
        "applied": added,
        "reason": "applied" if added else "trait_add_failed",
        "rising_sign_index": rising_sign_index,
        "rising_trait_id": rising_trait_id,
    }
