from __future__ import annotations


ZODIAC_ORDER = (
    "ARIES",
    "TAURUS",
    "GEMINI",
    "CANCER",
    "LEO",
    "VIRGO",
    "LIBRA",
    "SCORPIO",
    "SAGITTARIUS",
    "CAPRICORN",
    "AQUARIUS",
    "PISCES",
)

DAY_PHASE_BUCKETS = {
    "WAXING_CRESCENT": "WAXING_CRESCENT_DAY",
    "WAXING_GIBBOUS": "WAXING_GIBBOUS_DAY",
    "WANING_GIBBOUS": "WANING_GIBBOUS_DAY",
    "WANING_CRESCENT": "WANING_CRESCENT_DAY",
}

NIGHT_PHASE_BUCKETS = {
    "WAXING_CRESCENT": "WAXING_CRESCENT_NIGHT",
    "WAXING_GIBBOUS": "WAXING_GIBBOUS_NIGHT",
    "WANING_GIBBOUS": "WANING_GIBBOUS_NIGHT",
    "WANING_CRESCENT": "WANING_CRESCENT_NIGHT",
}

BUCKET_SIGN_INDEX = {
    "NEW_MOON": {
        "ARIES": 0,
        "TAURUS": 1,
        "GEMINI": 2,
        "CANCER": 3,
        "LEO": 4,
        "VIRGO": 5,
        "LIBRA": 6,
        "SCORPIO": 7,
        "SAGITTARIUS": 8,
        "CAPRICORN": 9,
        "AQUARIUS": 10,
        "PISCES": 11,
    },
    "WAXING_CRESCENT_DAY": {
        "ARIES": 1,
        "TAURUS": 2,
        "GEMINI": 3,
        "CANCER": 4,
        "LEO": 5,
        "VIRGO": 6,
        "LIBRA": 7,
        "SCORPIO": 8,
        "SAGITTARIUS": 9,
        "CAPRICORN": 10,
        "AQUARIUS": 11,
        "PISCES": 0,
    },
    "WAXING_CRESCENT_NIGHT": {
        "ARIES": 2,
        "TAURUS": 3,
        "GEMINI": 4,
        "CANCER": 5,
        "LEO": 6,
        "VIRGO": 7,
        "LIBRA": 8,
        "SCORPIO": 9,
        "SAGITTARIUS": 10,
        "CAPRICORN": 11,
        "AQUARIUS": 0,
        "PISCES": 1,
    },
    "FIRST_QUARTER": {
        "ARIES": 3,
        "TAURUS": 4,
        "GEMINI": 5,
        "CANCER": 6,
        "LEO": 7,
        "VIRGO": 8,
        "LIBRA": 9,
        "SCORPIO": 10,
        "SAGITTARIUS": 11,
        "CAPRICORN": 0,
        "AQUARIUS": 1,
        "PISCES": 2,
    },
    "WAXING_GIBBOUS_DAY": {
        "ARIES": 4,
        "TAURUS": 5,
        "GEMINI": 6,
        "CANCER": 7,
        "LEO": 8,
        "VIRGO": 9,
        "LIBRA": 10,
        "SCORPIO": 11,
        "SAGITTARIUS": 0,
        "CAPRICORN": 1,
        "AQUARIUS": 2,
        "PISCES": 3,
    },
    "WAXING_GIBBOUS_NIGHT": {
        "ARIES": 5,
        "TAURUS": 6,
        "GEMINI": 7,
        "CANCER": 8,
        "LEO": 9,
        "VIRGO": 10,
        "LIBRA": 11,
        "SCORPIO": 0,
        "SAGITTARIUS": 1,
        "CAPRICORN": 2,
        "AQUARIUS": 3,
        "PISCES": 4,
    },
    "FULL_MOON": {
        "ARIES": 6,
        "TAURUS": 7,
        "GEMINI": 8,
        "CANCER": 9,
        "LEO": 10,
        "VIRGO": 11,
        "LIBRA": 0,
        "SCORPIO": 1,
        "SAGITTARIUS": 2,
        "CAPRICORN": 3,
        "AQUARIUS": 4,
        "PISCES": 5,
    },
    "WANING_GIBBOUS_DAY": {
        "ARIES": 7,
        "TAURUS": 8,
        "GEMINI": 9,
        "CANCER": 10,
        "LEO": 11,
        "VIRGO": 0,
        "LIBRA": 1,
        "SCORPIO": 2,
        "SAGITTARIUS": 3,
        "CAPRICORN": 4,
        "AQUARIUS": 5,
        "PISCES": 6,
    },
    "WANING_GIBBOUS_NIGHT": {
        "ARIES": 8,
        "TAURUS": 9,
        "GEMINI": 10,
        "CANCER": 11,
        "LEO": 0,
        "VIRGO": 1,
        "LIBRA": 2,
        "SCORPIO": 3,
        "SAGITTARIUS": 4,
        "CAPRICORN": 5,
        "AQUARIUS": 6,
        "PISCES": 7,
    },
    "THIRD_QUARTER": {
        "ARIES": 9,
        "TAURUS": 10,
        "GEMINI": 11,
        "CANCER": 0,
        "LEO": 1,
        "VIRGO": 2,
        "LIBRA": 3,
        "SCORPIO": 4,
        "SAGITTARIUS": 5,
        "CAPRICORN": 6,
        "AQUARIUS": 7,
        "PISCES": 8,
    },
    "WANING_CRESCENT_DAY": {
        "ARIES": 10,
        "TAURUS": 11,
        "GEMINI": 0,
        "CANCER": 1,
        "LEO": 2,
        "VIRGO": 3,
        "LIBRA": 4,
        "SCORPIO": 5,
        "SAGITTARIUS": 6,
        "CAPRICORN": 7,
        "AQUARIUS": 8,
        "PISCES": 9,
    },
    "WANING_CRESCENT_NIGHT": {
        "ARIES": 11,
        "TAURUS": 0,
        "GEMINI": 1,
        "CANCER": 2,
        "LEO": 3,
        "VIRGO": 4,
        "LIBRA": 5,
        "SCORPIO": 6,
        "SAGITTARIUS": 7,
        "CAPRICORN": 8,
        "AQUARIUS": 9,
        "PISCES": 10,
    },
}


def build_bucket_sign_index_map():
    return {bucket: dict(value) for bucket, value in BUCKET_SIGN_INDEX.items()}


def resolve_lunar_bucket_key(phase_name, hour_24):
    phase_key = str(phase_name or "").strip().upper()
    hour = int(hour_24) % 24
    if phase_key in ("NEW_MOON", "FULL_MOON", "FIRST_QUARTER", "THIRD_QUARTER"):
        return phase_key
    if phase_key in DAY_PHASE_BUCKETS:
        return DAY_PHASE_BUCKETS[phase_key] if 7 <= hour < 19 else NIGHT_PHASE_BUCKETS[phase_key]
    raise ValueError("unsupported_lunar_phase:{0}".format(phase_name))


def resolve_moon_sign_index_for_bucket(sun_sign_index, lunar_bucket_key):
    sign_name = ZODIAC_ORDER[int(sun_sign_index) % len(ZODIAC_ORDER)]
    return int(BUCKET_SIGN_INDEX[str(lunar_bucket_key)][sign_name])


def apply_lunar_phase_moon_assignment(
    sim_info,
    *,
    sun_sign_index,
    lunar_bucket_key,
    trait_ids_by_sign_index,
    has_any_moon_trait_fn,
    has_trait_fn,
    add_trait_fn,
):
    if sim_info is None:
        return {"applied": False, "reason": "sim_missing"}
    if has_any_moon_trait_fn(sim_info):
        return {"applied": False, "reason": "already_has_moon"}

    moon_sign_index = resolve_moon_sign_index_for_bucket(sun_sign_index, lunar_bucket_key)
    moon_trait_id = int(trait_ids_by_sign_index[moon_sign_index])
    if has_trait_fn(sim_info, moon_trait_id):
        return {"applied": False, "reason": "already_has_moon"}

    added = bool(add_trait_fn(sim_info, moon_trait_id))
    return {
        "applied": added,
        "reason": "applied" if added else "trait_add_failed",
        "moon_sign_index": moon_sign_index,
        "moon_trait_id": moon_trait_id,
    }


def apply_random_moon_assignment(
    sim_info,
    *,
    available_sign_indexes,
    trait_ids_by_sign_index,
    has_any_moon_trait_fn,
    has_trait_fn,
    add_trait_fn,
    choose_sign_index_fn,
):
    if sim_info is None:
        return {"applied": False, "reason": "sim_missing"}
    if has_any_moon_trait_fn(sim_info):
        return {"applied": False, "reason": "already_has_moon"}

    moon_sign_index = int(choose_sign_index_fn(tuple(available_sign_indexes)))
    moon_trait_id = int(trait_ids_by_sign_index[moon_sign_index])
    if has_trait_fn(sim_info, moon_trait_id):
        return {"applied": False, "reason": "already_has_moon"}

    added = bool(add_trait_fn(sim_info, moon_trait_id))
    return {
        "applied": added,
        "reason": "applied" if added else "trait_add_failed",
        "moon_sign_index": moon_sign_index,
        "moon_trait_id": moon_trait_id,
    }
