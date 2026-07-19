"""Shared sim eligibility helpers for Cosmic Engine runtime logic."""

from __future__ import annotations

from typing import Optional

_TEEN_PLUS_AGE_TOKENS = ("TEEN", "YOUNGADULT", "YOUNG_ADULT", "ADULT", "ELDER")
_TEEN_PLUS_AGE_BITS = (8, 16, 32, 64)
_PRETEEN_AGE_BITS = (2, 4, 128)
_TEEN_ONLY_AGE_BITS = (8,)
_ADULT_PLUS_AGE_BITS = (16, 32, 64)


def _coerce_int(value) -> Optional[int]:
    try:
        return int(value)
    except Exception:
        return None


def _call_bool_attr(obj, attr_name: str) -> Optional[bool]:
    if obj is None:
        return None
    value = getattr(obj, attr_name, None)
    if callable(value):
        try:
            value = value()
        except Exception:
            return None
    if isinstance(value, bool):
        return value
    return None


def _raw_enum_name(value) -> Optional[str]:
    if value is None:
        return None
    name = getattr(value, "name", None)
    if isinstance(name, str) and name:
        return name.upper()
    text = str(value or "").strip()
    if not text:
        return None
    if "." in text:
        text = text.split(".")[-1]
    return text.replace(">", "").strip().upper() or None


def sim_info_species_name(sim_info) -> Optional[str]:
    if sim_info is None:
        return None
    for attr_name in ("species", "extended_species", "species_extended"):
        try:
            value = getattr(sim_info, attr_name, None)
        except Exception:
            value = None
        enum_name = _raw_enum_name(value)
        if enum_name:
            return enum_name
    for method_name in ("get_species", "get_extended_species"):
        fn = getattr(sim_info, method_name, None)
        if not callable(fn):
            continue
        try:
            value = fn()
        except Exception:
            value = None
        enum_name = _raw_enum_name(value)
        if enum_name:
            return enum_name
    return None


def sim_info_is_human(sim_info) -> bool:
    if sim_info is None:
        return False
    is_human = _call_bool_attr(sim_info, "is_human")
    if is_human is True:
        return True
    is_pet = _call_bool_attr(sim_info, "is_pet")
    if is_pet is True:
        return False
    species_name = sim_info_species_name(sim_info)
    if species_name == "HUMAN":
        return True
    if species_name:
        return False
    return True


def sim_info_is_non_human(sim_info) -> bool:
    return bool(sim_info is not None and not sim_info_is_human(sim_info))


def sim_age_token(sim_info) -> str:
    if sim_info is None:
        return ""

    candidates = []
    age_value = getattr(sim_info, "age", None)
    if age_value is not None:
        for value in (getattr(age_value, "name", None), str(age_value)):
            if value:
                candidates.append(str(value))

    for attr_name in ("age_name", "_age_name"):
        value = getattr(sim_info, attr_name, None)
        if value:
            candidates.append(str(value))

    for candidate in candidates:
        token = str(candidate).strip().upper()
        if not token:
            continue
        if "." in token:
            token = token.rsplit(".", 1)[-1]
        token = token.replace(" ", "").replace("-", "").replace("_", "")
        if token:
            return token
    return ""


def sim_age_lane(sim_info) -> str:
    """Classify the sim into a shared gameplay age lane."""
    age_value = getattr(sim_info, "age", None)
    if age_value is None:
        return "unknown"

    token = sim_age_token(sim_info)
    if token:
        if any(fragment in token for fragment in ("INFANT", "TODDLER", "CHILD")):
            return "preteen"
        if token == "TEEN":
            return "teen"
        if any(fragment in token for fragment in ("YOUNGADULT", "ADULT", "ELDER")):
            return "adult_plus"
        if any(fragment in token for fragment in _TEEN_PLUS_AGE_TOKENS):
            return "adult_plus"

    age_int = _coerce_int(age_value)
    if age_int is None:
        return "unknown"
    if any((age_int & bit) == bit for bit in _PRETEEN_AGE_BITS):
        return "preteen"
    if any((age_int & bit) == bit for bit in _TEEN_ONLY_AGE_BITS):
        return "teen"
    if any((age_int & bit) == bit for bit in _ADULT_PLUS_AGE_BITS):
        return "adult_plus"
    if any((age_int & bit) == bit for bit in _TEEN_PLUS_AGE_BITS):
        return "adult_plus"
    return "unknown"


def sim_info_is_preteen(sim_info) -> bool:
    return sim_age_lane(sim_info) == "preteen"


def sim_info_is_teen(sim_info) -> bool:
    return sim_age_lane(sim_info) == "teen"


def sim_info_is_teen_plus(sim_info) -> bool:
    return sim_age_lane(sim_info) in ("teen", "adult_plus")


def sim_info_is_retrograde_eligible(sim_info) -> bool:
    return sim_info_is_human(sim_info) and sim_info_is_teen_plus(sim_info)
