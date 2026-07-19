"""Save-wide retrograde visibility profile payload helpers."""

from __future__ import annotations

from typing import Dict, Optional


RETROGRADE_VISIBILITY_PAYLOAD_KEY = "retrograde_visibility"
DEFAULT_RETROGRADE_VISIBILITY_PROFILE_ID = "recommended"
_RETROGRADE_VISIBILITY_PROFILE_ID_KEYS = ("profile_id", "profile", "selected_profile")
_RETROGRADE_VISIBILITY_PROFILE_LABELS = {
    "recommended": "Recommended (3 Visible)",
    "uncapped": "Uncapped",
}


def normalize_retrograde_visibility_profile_id(profile_id: Optional[object]) -> str:
    text = str(profile_id or "").strip().lower()
    if text in _RETROGRADE_VISIBILITY_PROFILE_LABELS:
        return text
    return DEFAULT_RETROGRADE_VISIBILITY_PROFILE_ID


def get_retrograde_visibility_profile_label(profile_id: Optional[object]) -> str:
    normalized = normalize_retrograde_visibility_profile_id(profile_id)
    return _RETROGRADE_VISIBILITY_PROFILE_LABELS.get(
        normalized,
        _RETROGRADE_VISIBILITY_PROFILE_LABELS[DEFAULT_RETROGRADE_VISIBILITY_PROFILE_ID],
    )


def _extract_profile_id(payload) -> Optional[str]:
    if not isinstance(payload, dict):
        return None

    nested = payload.get(RETROGRADE_VISIBILITY_PAYLOAD_KEY)
    if isinstance(nested, dict):
        for key in _RETROGRADE_VISIBILITY_PROFILE_ID_KEYS:
            value = nested.get(key)
            if isinstance(value, str) and value.strip():
                return value

    for key in _RETROGRADE_VISIBILITY_PROFILE_ID_KEYS:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return None


def build_retrograde_visibility_profile_payload(
    profile_id: Optional[object] = None,
    *,
    existing_payload=None
) -> Dict[str, object]:
    payload = dict(existing_payload) if isinstance(existing_payload, dict) else {}
    payload["profile_id"] = normalize_retrograde_visibility_profile_id(profile_id)
    return payload


def read_retrograde_visibility_profile_payload(payload) -> Dict[str, object]:
    nested = payload.get(RETROGRADE_VISIBILITY_PAYLOAD_KEY) if isinstance(payload, dict) else None
    return build_retrograde_visibility_profile_payload(
        _extract_profile_id(payload),
        existing_payload=nested,
    )


def read_retrograde_visibility_profile_id(payload) -> str:
    profile_payload = read_retrograde_visibility_profile_payload(payload)
    return str(
        profile_payload.get("profile_id") or DEFAULT_RETROGRADE_VISIBILITY_PROFILE_ID
    )


def merge_retrograde_visibility_profile_payload(
    payload,
    requested_profile_id: Optional[object] = None,
) -> Dict[str, object]:
    merged = dict(payload) if isinstance(payload, dict) else {}
    requested = requested_profile_id if requested_profile_id is not None else _extract_profile_id(merged)
    nested = merged.get(RETROGRADE_VISIBILITY_PAYLOAD_KEY)
    merged[RETROGRADE_VISIBILITY_PAYLOAD_KEY] = build_retrograde_visibility_profile_payload(
        requested,
        existing_payload=nested,
    )
    return merged


def resolve_retrograde_visibility_profile_payload(payload) -> Dict[str, object]:
    return merge_retrograde_visibility_profile_payload(payload)
