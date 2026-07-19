"""Helpers for Sun compatibility chemistry overlay routing."""

from __future__ import annotations

import hashlib
from typing import Dict, Iterable, Optional

from .chemistry_settings import normalize_chemistry_profile_id


SUN_CHEMISTRY_PROFILE_IDS = ("subtle", "balanced", "dramatic")
SUN_COMPATIBILITY_TIER_NAMES = (
    "VeryCompatible",
    "SomewhatCompatible",
    "Neutral",
    "SomewhatIncompatible",
    "VeryIncompatible",
)
_SUN_COMPATIBILITY_TIER_NAME_BY_KEY = {
    "verycompatible": "VeryCompatible",
    "somewhatcompatible": "SomewhatCompatible",
    "neutral": "Neutral",
    "somewhatincompatible": "SomewhatIncompatible",
    "veryincompatible": "VeryIncompatible",
}
SUN_TIER_BUFF_ID_BY_NAME = {
    "VeryCompatible": 15005668881878687258,
    "SomewhatCompatible": 14106856538116155360,
    "Neutral": 15288198472464110793,
    "SomewhatIncompatible": 10532275044759218237,
    "VeryIncompatible": 8576194995924309275,
}
SUN_RELBIT_ID_BY_TIER = {
    "VeryCompatible": 1172767005,
    "SomewhatCompatible": 2697969743,
    "Neutral": 3493519448,
    "SomewhatIncompatible": 2587459068,
    "VeryIncompatible": 3369622102,
}
BALANCED_SUN_RELATIONSHIP_MULTIPLIERS_BY_TIER = {
    "VeryCompatible": {"friendship": 1.35, "romance": 1.55},
    "SomewhatCompatible": {"friendship": 1.15, "romance": 1.25},
    "Neutral": {"friendship": 1.0, "romance": 1.0},
    "SomewhatIncompatible": {"friendship": 0.9, "romance": 0.75},
    "VeryIncompatible": {"friendship": 0.8, "romance": 0.55},
}
_PROFILE_DISTANCE_SCALE = {
    "subtle": 0.5,
    "balanced": 1.0,
    "dramatic": 1.5,
}


def normalize_sun_tier_name(tier_name) -> Optional[str]:
    text = "".join(ch for ch in str(tier_name or "") if ch.isalnum()).lower()
    return _SUN_COMPATIBILITY_TIER_NAME_BY_KEY.get(text)


def _stable_resource_instance_id(resource_name: str) -> int:
    digest = hashlib.sha256(str(resource_name or "").encode("utf-8")).hexdigest()[:16]
    return int(digest, 16)


def get_sun_profile_relationship_multipliers(tier_name, profile_id) -> Optional[Dict[str, float]]:
    normalized_tier_name = normalize_sun_tier_name(tier_name)
    normalized_profile_id = normalize_chemistry_profile_id(profile_id)
    if normalized_tier_name is None:
        return None
    base = BALANCED_SUN_RELATIONSHIP_MULTIPLIERS_BY_TIER.get(normalized_tier_name)
    scale = _PROFILE_DISTANCE_SCALE.get(normalized_profile_id)
    if base is None or scale is None:
        return None
    out = {}
    for track_name, base_value in base.items():
        delta = float(base_value) - 1.0
        out[str(track_name)] = round(1.0 + (delta * float(scale)), 6)
    return out


def get_sun_overlay_relationship_multipliers(tier_name, profile_id) -> Optional[Dict[str, float]]:
    normalized_tier_name = normalize_sun_tier_name(tier_name)
    normalized_profile_id = normalize_chemistry_profile_id(profile_id)
    if normalized_tier_name is None:
        return None
    if normalized_profile_id == "balanced":
        return {}
    base = BALANCED_SUN_RELATIONSHIP_MULTIPLIERS_BY_TIER.get(normalized_tier_name)
    target = get_sun_profile_relationship_multipliers(normalized_tier_name, normalized_profile_id)
    if base is None or target is None:
        return None
    out = {}
    for track_name, base_value in base.items():
        out[str(track_name)] = round(float(target[str(track_name)]) / float(base_value), 6)
    return out


def resolve_sun_overlay_name(tier_name, profile_id) -> Optional[str]:
    normalized_tier_name = normalize_sun_tier_name(tier_name)
    normalized_profile_id = normalize_chemistry_profile_id(profile_id)
    if normalized_tier_name is None or normalized_profile_id == "balanced":
        return None
    if normalized_profile_id not in SUN_CHEMISTRY_PROFILE_IDS:
        return None
    return "PlumAntics_CosmicEngineCore_SunChemistryOverlay_{0}_{1}".format(
        normalized_tier_name,
        normalized_profile_id.capitalize(),
    )


def resolve_sun_overlay_buff_id(tier_name, profile_id) -> Optional[int]:
    overlay_name = resolve_sun_overlay_name(tier_name, profile_id)
    if overlay_name is None:
        return None
    return _stable_resource_instance_id(overlay_name)


def iter_sun_overlay_buff_ids() -> Iterable[int]:
    for tier_name in SUN_COMPATIBILITY_TIER_NAMES:
        for profile_id in ("subtle", "dramatic"):
            overlay_buff_id = resolve_sun_overlay_buff_id(tier_name, profile_id)
            if overlay_buff_id is not None:
                yield int(overlay_buff_id)


def iter_sun_tier_buff_id_pairs() -> Iterable[tuple[str, int]]:
    for tier_name in SUN_COMPATIBILITY_TIER_NAMES:
        buff_id = SUN_TIER_BUFF_ID_BY_NAME.get(tier_name)
        if buff_id is not None:
            yield (tier_name, int(buff_id))


def iter_sun_relbit_id_pairs() -> Iterable[tuple[str, int]]:
    for tier_name in SUN_COMPATIBILITY_TIER_NAMES:
        relbit_id = SUN_RELBIT_ID_BY_TIER.get(tier_name)
        if relbit_id is not None:
            yield (tier_name, int(relbit_id))


def resolve_sun_tier_name_from_relbit_id(relbit_id) -> Optional[str]:
    try:
        target_relbit_id = int(relbit_id)
    except Exception:
        return None
    for tier_name, mapped_relbit_id in SUN_RELBIT_ID_BY_TIER.items():
        if int(mapped_relbit_id) == target_relbit_id:
            return str(tier_name)
    return None


def should_apply_first_contact_sun_pass(*, sun_known=False) -> bool:
    return not bool(sun_known)


def build_sun_overlay_buff_plan(tier_name, profile_id) -> Dict[str, object]:
    normalized_tier_name = normalize_sun_tier_name(tier_name)
    normalized_profile_id = normalize_chemistry_profile_id(profile_id)
    profile_multipliers = (
        get_sun_profile_relationship_multipliers(normalized_tier_name, normalized_profile_id)
        if normalized_tier_name is not None
        else None
    )
    overlay_multipliers = (
        get_sun_overlay_relationship_multipliers(normalized_tier_name, normalized_profile_id)
        if normalized_tier_name is not None
        else None
    )
    overlay_name = resolve_sun_overlay_name(normalized_tier_name, normalized_profile_id)
    overlay_buff_id = resolve_sun_overlay_buff_id(normalized_tier_name, normalized_profile_id)
    out = {
        "ok": False,
        "reason": None,
        "tier_name": normalized_tier_name,
        "profile_id": normalized_profile_id,
        "base_relationship_multipliers": (
            dict(BALANCED_SUN_RELATIONSHIP_MULTIPLIERS_BY_TIER.get(normalized_tier_name, {}))
            if normalized_tier_name is not None
            else {}
        ),
        "profile_relationship_multipliers": dict(profile_multipliers or {}),
        "overlay_relationship_multipliers": dict(overlay_multipliers or {}),
        "overlay_name": overlay_name,
        "overlay_buff_id": overlay_buff_id,
    }
    if normalized_tier_name is None:
        out["reason"] = "missing_tier"
        return out
    if normalized_profile_id == "balanced":
        out["ok"] = True
        out["reason"] = "base_only"
        return out
    if overlay_name is None or overlay_buff_id is None or overlay_multipliers is None:
        out["reason"] = "missing_overlay_mapping"
        return out
    out["ok"] = True
    out["reason"] = "resolved"
    return out
