"""Helpers for relationship-band Rising chemistry routing."""

from __future__ import annotations

import hashlib
from typing import Dict, Iterable, Optional

from .chemistry_settings import normalize_chemistry_profile_id
from .transit_core import SIGNS


RELATIONSHIP_BAND_INITIAL = "initial"
RELATIONSHIP_BAND_MIXED = "mixed"
RELATIONSHIP_BAND_RESIDUAL = "residual"
RISING_CHEMISTRY_STAGE_INITIAL = "initial"
RISING_CHEMISTRY_STAGE_RESIDUAL = "residual"
_VALID_RELATIONSHIP_BANDS = frozenset(
    (
        RELATIONSHIP_BAND_INITIAL,
        RELATIONSHIP_BAND_MIXED,
        RELATIONSHIP_BAND_RESIDUAL,
    )
)
_VALID_RISING_CHEMISTRY_STAGES = frozenset(
    (
        RISING_CHEMISTRY_STAGE_INITIAL,
        RISING_CHEMISTRY_STAGE_RESIDUAL,
    )
)
RISING_CHEMISTRY_PROFILE_IDS = ("subtle", "balanced", "dramatic")
_MIXED_BAND_STAGE_THRESHOLD = 45
_RISING_CHEMISTRY_MAGNITUDE_BY_STAGE_PROFILE = {
    RISING_CHEMISTRY_STAGE_INITIAL: {
        "subtle": 4,
        "balanced": 8,
        "dramatic": 12,
    },
    RISING_CHEMISTRY_STAGE_RESIDUAL: {
        "subtle": 2,
        "balanced": 4,
        "dramatic": 6,
    },
}
_TRACK_PRIORITY = {
    "romance": 2,
    "friendship": 1,
    "summary": 0,
}


def _coerce_int(value) -> Optional[int]:
    try:
        return int(value)
    except Exception:
        return None


def normalize_relationship_band(band) -> Optional[str]:
    text = str(band or "").strip().lower()
    if text in _VALID_RELATIONSHIP_BANDS:
        return text
    return None


def normalize_rising_chemistry_stage(stage) -> Optional[str]:
    text = str(stage or "").strip().lower()
    if text in _VALID_RISING_CHEMISTRY_STAGES:
        return text
    return None


def normalize_sign_name(sign_name) -> Optional[str]:
    text = str(sign_name or "").strip().lower()
    for sign in SIGNS:
        if str(sign).lower() == text:
            return str(sign)
    return None


def resolve_relationship_band(relationship_score) -> Optional[str]:
    score = _coerce_int(relationship_score)
    if score is None:
        return None
    score = abs(int(score))
    if score <= 30:
        return RELATIONSHIP_BAND_INITIAL
    if score <= 60:
        return RELATIONSHIP_BAND_MIXED
    return RELATIONSHIP_BAND_RESIDUAL


def should_apply_first_contact_rising_pass(*, rising_known=False) -> bool:
    return not bool(rising_known)


def build_profile_band_key(profile_id, relationship_band) -> str:
    normalized_profile_id = normalize_chemistry_profile_id(profile_id)
    normalized_band = normalize_relationship_band(relationship_band) or RELATIONSHIP_BAND_INITIAL
    return "{0}_{1}".format(normalized_profile_id, normalized_band)


def resolve_rising_chemistry_stage(relationship_band, relationship_score=None) -> Optional[str]:
    normalized_band = normalize_relationship_band(relationship_band)
    score = abs(int(_coerce_int(relationship_score) or 0))
    if normalized_band == RELATIONSHIP_BAND_INITIAL:
        return RISING_CHEMISTRY_STAGE_INITIAL
    if normalized_band == RELATIONSHIP_BAND_RESIDUAL:
        return RISING_CHEMISTRY_STAGE_RESIDUAL
    if normalized_band != RELATIONSHIP_BAND_MIXED:
        return None
    if score <= _MIXED_BAND_STAGE_THRESHOLD:
        return RISING_CHEMISTRY_STAGE_INITIAL
    return RISING_CHEMISTRY_STAGE_RESIDUAL


def _stable_resource_instance_id(resource_name: str) -> int:
    digest = hashlib.sha256(str(resource_name or "").encode("utf-8")).hexdigest()[:16]
    return int(digest, 16)


def build_actor_rising_chemistry_managed_buff_key(sign_name, stage, profile_id) -> Optional[str]:
    normalized_sign_name = normalize_sign_name(sign_name)
    normalized_stage = normalize_rising_chemistry_stage(stage)
    normalized_profile_id = normalize_chemistry_profile_id(profile_id)
    if normalized_sign_name is None or normalized_stage is None:
        return None
    return "{0}_{1}_{2}".format(
        normalized_sign_name.lower(),
        normalized_stage,
        normalized_profile_id,
    )


def build_actor_rising_chemistry_managed_buff_resource_name(sign_name, stage, profile_id) -> Optional[str]:
    normalized_sign_name = normalize_sign_name(sign_name)
    normalized_stage = normalize_rising_chemistry_stage(stage)
    normalized_profile_id = normalize_chemistry_profile_id(profile_id)
    if normalized_sign_name is None or normalized_stage is None:
        return None
    return "PlumAntics_CosmicEngineCore_{0}Rising{1}_{2}".format(
        normalized_sign_name,
        normalized_stage.capitalize(),
        normalized_profile_id.capitalize(),
    )


def resolve_actor_rising_chemistry_managed_buff_id(sign_name, stage, profile_id) -> Optional[int]:
    resource_name = build_actor_rising_chemistry_managed_buff_resource_name(
        sign_name,
        stage,
        profile_id,
    )
    if resource_name is None:
        return None
    return _stable_resource_instance_id(resource_name)


def iter_actor_rising_chemistry_managed_buff_ids() -> Iterable[int]:
    for sign_name in SIGNS:
        for stage in _VALID_RISING_CHEMISTRY_STAGES:
            for profile_id in RISING_CHEMISTRY_PROFILE_IDS:
                buff_id = resolve_actor_rising_chemistry_managed_buff_id(
                    sign_name,
                    stage,
                    profile_id,
                )
                if buff_id is not None:
                    yield int(buff_id)


def resolve_dominant_relationship_track(
    *,
    friendship_score=None,
    romance_score=None,
    relationship_score=None,
) -> Dict[str, object]:
    candidates = []
    for track_name, track_score in (
        ("romance", romance_score),
        ("friendship", friendship_score),
    ):
        normalized_score = _coerce_int(track_score)
        if normalized_score is None:
            continue
        candidates.append(
            {
                "track": track_name,
                "relationship_score": int(normalized_score),
                "relationship_band": resolve_relationship_band(normalized_score),
            }
        )

    if not candidates:
        normalized_score = _coerce_int(relationship_score)
        if normalized_score is None:
            return {
                "track": None,
                "relationship_score": None,
                "relationship_band": None,
            }
        return {
            "track": "summary",
            "relationship_score": int(normalized_score),
            "relationship_band": resolve_relationship_band(normalized_score),
        }

    return max(
        candidates,
        key=lambda payload: (
            abs(int(payload.get("relationship_score", 0))),
            int(_TRACK_PRIORITY.get(str(payload.get("track") or ""), 0)),
        ),
    )


def build_actor_rising_chemistry_buff_plan(
    *,
    sign_name=None,
    profile_id=None,
    friendship_score=None,
    romance_score=None,
    relationship_score=None,
) -> Dict[str, object]:
    normalized_sign_name = normalize_sign_name(sign_name)
    normalized_profile_id = normalize_chemistry_profile_id(profile_id)
    selected_track = resolve_dominant_relationship_track(
        friendship_score=friendship_score,
        romance_score=romance_score,
        relationship_score=relationship_score,
    )
    relationship_band = selected_track.get("relationship_band")
    selected_score = selected_track.get("relationship_score")
    affordance_stage = resolve_rising_chemistry_stage(
        relationship_band,
        relationship_score=selected_score,
    )
    managed_buff_key = build_actor_rising_chemistry_managed_buff_key(
        normalized_sign_name,
        affordance_stage,
        normalized_profile_id,
    )
    managed_buff_resource_name = build_actor_rising_chemistry_managed_buff_resource_name(
        normalized_sign_name,
        affordance_stage,
        normalized_profile_id,
    )
    managed_buff_id = resolve_actor_rising_chemistry_managed_buff_id(
        normalized_sign_name,
        affordance_stage,
        normalized_profile_id,
    )
    out = {
        "ok": False,
        "reason": None,
        "sign_name": normalized_sign_name,
        "sign_index": SIGNS.index(normalized_sign_name) if normalized_sign_name in SIGNS else None,
        "profile_id": normalized_profile_id,
        "applied_track": selected_track.get("track"),
        "relationship_score": selected_score,
        "relationship_band": relationship_band,
        "affordance_stage": affordance_stage,
        "managed_buff_key": managed_buff_key,
        "managed_buff_resource_name": managed_buff_resource_name,
        "managed_buff_id": managed_buff_id,
        "content_score_bonus": None,
    }
    if normalized_sign_name is None:
        out["reason"] = "missing_rising_sign"
        return out
    if relationship_band is None or selected_score is None:
        out["reason"] = "missing_relationship_score"
        return out
    if affordance_stage is None or managed_buff_key is None or managed_buff_id is None:
        out["reason"] = "missing_buff_mapping"
        return out
    out["content_score_bonus"] = int(
        _RISING_CHEMISTRY_MAGNITUDE_BY_STAGE_PROFILE[affordance_stage][normalized_profile_id]
    )
    out["ok"] = True
    out["reason"] = "resolved"
    return out


def build_refresh_summary(
    *,
    actor_sim_id=None,
    target_sim_id=None,
    profile_id=None,
    relationship_score=None,
    friendship_score=None,
    romance_score=None,
) -> Dict[str, object]:
    normalized_profile_id = normalize_chemistry_profile_id(profile_id)
    normalized_score = _coerce_int(relationship_score)
    relationship_band = resolve_relationship_band(normalized_score)
    normalized_friendship_score = _coerce_int(friendship_score)
    normalized_romance_score = _coerce_int(romance_score)
    relationship_scores = {}
    relationship_bands = {}
    track_profile_band_keys = {}
    for track_name, track_score in (
        ("friendship", normalized_friendship_score),
        ("romance", normalized_romance_score),
    ):
        if track_score is None:
            continue
        relationship_scores[track_name] = int(track_score)
        band = resolve_relationship_band(track_score)
        relationship_bands[track_name] = band
        track_profile_band_keys[track_name] = (
            build_profile_band_key(normalized_profile_id, band) if band is not None else None
        )

    use_track_specific_scores = bool(relationship_scores)
    profile_band_key = (
        build_profile_band_key(normalized_profile_id, relationship_band)
        if relationship_band is not None and not use_track_specific_scores
        else None
    )
    summary = {
        "ok": False,
        "reason": None,
        "actor_sim_id": _coerce_int(actor_sim_id),
        "target_sim_id": _coerce_int(target_sim_id),
        "profile_id": normalized_profile_id,
        "relationship_score": None if use_track_specific_scores else normalized_score,
        "relationship_band": None if use_track_specific_scores else relationship_band,
        "relationship_scores": relationship_scores,
        "relationship_bands": relationship_bands,
        "profile_band_key": profile_band_key,
        "track_profile_band_keys": track_profile_band_keys,
        "pending_buff_keys": [],
        "pending_buff_count": 0,
    }

    if summary["actor_sim_id"] is None or summary["target_sim_id"] is None:
        summary["reason"] = "missing_sim_id"
        return summary

    if not relationship_scores and (normalized_score is None or relationship_band is None):
        summary["reason"] = "missing_relationship_score"
        return summary

    summary["ok"] = True
    summary["reason"] = "resolved"
    return summary
