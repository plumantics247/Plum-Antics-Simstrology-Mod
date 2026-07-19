"""Save-wide sign compatibility seed payload helpers."""

from __future__ import annotations

from typing import Dict, Optional


SIGN_COMPATIBILITY_SEED_PAYLOAD_KEY = "sign_compatibility_seed_profile"
_SIM_PROFILES_KEY = "sim_profiles"


def _normalize_sim_id(sim_id) -> Optional[str]:
    try:
        return str(int(sim_id))
    except Exception:
        return None


def build_sign_compatibility_seed_payload(
    *,
    sim_profiles=None,
    existing_payload=None
) -> Dict[str, object]:
    payload = dict(existing_payload) if isinstance(existing_payload, dict) else {}
    profiles = sim_profiles if isinstance(sim_profiles, dict) else payload.get(_SIM_PROFILES_KEY)
    payload[_SIM_PROFILES_KEY] = dict(profiles) if isinstance(profiles, dict) else {}
    return payload


def read_sign_compatibility_seed_payload(payload) -> Dict[str, object]:
    nested = payload.get(SIGN_COMPATIBILITY_SEED_PAYLOAD_KEY) if isinstance(payload, dict) else None
    return build_sign_compatibility_seed_payload(existing_payload=nested)


def read_sign_compatibility_seed_record(payload, sim_id) -> Optional[Dict[str, object]]:
    normalized_sim_id = _normalize_sim_id(sim_id)
    if normalized_sim_id is None:
        return None
    nested = read_sign_compatibility_seed_payload(payload)
    profiles = nested.get(_SIM_PROFILES_KEY)
    if not isinstance(profiles, dict):
        return None
    record = profiles.get(normalized_sim_id)
    return dict(record) if isinstance(record, dict) else None


def merge_sign_compatibility_seed_payload(payload, *, sim_id, seed_record) -> Dict[str, object]:
    merged = dict(payload) if isinstance(payload, dict) else {}
    nested = read_sign_compatibility_seed_payload(merged)
    normalized_sim_id = _normalize_sim_id(sim_id)
    if normalized_sim_id is not None and isinstance(seed_record, dict):
        profiles = dict(nested.get(_SIM_PROFILES_KEY) or {})
        profiles[normalized_sim_id] = dict(seed_record)
        nested[_SIM_PROFILES_KEY] = profiles
    merged[SIGN_COMPATIBILITY_SEED_PAYLOAD_KEY] = nested
    return merged


def remove_sign_compatibility_seed_payload_for_sim(payload, sim_id) -> Dict[str, object]:
    merged = dict(payload) if isinstance(payload, dict) else {}
    nested = read_sign_compatibility_seed_payload(merged)
    normalized_sim_id = _normalize_sim_id(sim_id)
    if normalized_sim_id is not None:
        profiles = dict(nested.get(_SIM_PROFILES_KEY) or {})
        profiles.pop(normalized_sim_id, None)
        nested[_SIM_PROFILES_KEY] = profiles
    merged[SIGN_COMPATIBILITY_SEED_PAYLOAD_KEY] = nested
    return merged


def resolve_sign_compatibility_seed_payload(payload) -> Dict[str, object]:
    return read_sign_compatibility_seed_payload(payload)
