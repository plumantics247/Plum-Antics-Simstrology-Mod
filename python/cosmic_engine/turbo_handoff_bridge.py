from __future__ import annotations

from typing import Dict

from .astrology_skill_gate import get_simstrology_skill_level
from .loot_actions import (
    _resolve_active_sun_chemistry_tier_name,
    _resolve_relationship_score_summary,
    _resolve_rising_sign_index_and_name,
    _resolve_sun_sign_index_and_name,
)
from .transit_core import SIGNS


FRIENDSHIP_TRACK_ID = 16650
SUN_FAMILIARITY_THRESHOLD = 20


def _coerce_int(value, default=0):
    try:
        return int(value)
    except Exception:
        return int(default)


def _iter_trait_text_candidates(trait):
    for attr_name in ("__name__", "trait_name", "name"):
        try:
            value = getattr(trait, attr_name, None)
        except Exception:
            value = None
        if isinstance(value, str) and value:
            yield value
    trait_type = type(trait)
    if trait_type is not None:
        trait_type_name = getattr(trait_type, "__name__", None)
        if isinstance(trait_type_name, str) and trait_type_name:
            yield trait_type_name
    try:
        rendered = str(trait)
    except Exception:
        rendered = None
    if isinstance(rendered, str) and rendered:
        yield rendered


def _iter_sim_traits(sim_info):
    if sim_info is None:
        return ()
    traits = []
    for attr_name in ("traits", "_traits", "all_traits", "_all_traits"):
        try:
            value = getattr(sim_info, attr_name, None)
        except Exception:
            value = None
        if isinstance(value, (list, tuple, set)):
            traits.extend(value)
    for method_name in ("get_traits", "get_all_traits"):
        fn = getattr(sim_info, method_name, None)
        if not callable(fn):
            continue
        try:
            value = fn()
        except Exception:
            continue
        if isinstance(value, (list, tuple, set)):
            traits.extend(value)
    return tuple(traits)


def _resolve_sign_from_trait_text(sim_info, suffix):
    token_suffix = str(suffix or "")
    if not token_suffix:
        return (None, None)
    for trait in _iter_sim_traits(sim_info):
        for text in _iter_trait_text_candidates(trait):
            for sign_index, sign_name in enumerate(SIGNS):
                if "{0}{1}".format(sign_name, token_suffix) in text:
                    return (sign_index, sign_name)
    return (None, None)


def _resolve_rising_sign(actor_or_target_sim_info):
    sign_index, sign_name = _resolve_rising_sign_index_and_name(actor_or_target_sim_info)
    if sign_name is not None:
        return (sign_index, sign_name)
    return _resolve_sign_from_trait_text(actor_or_target_sim_info, "Rising")


def _resolve_sun_sign(actor_or_target_sim_info):
    sign_index, sign_name = _resolve_sun_sign_index_and_name(actor_or_target_sim_info)
    if sign_name is not None:
        return (sign_index, sign_name)
    return _resolve_sign_from_trait_text(actor_or_target_sim_info, "Sun")


def build_turbo_pair_state(actor_sim_info, target_sim_info, *, awareness_skill_level: int = 3) -> Dict[str, object]:
    relationship_summary = _resolve_relationship_score_summary(actor_sim_info, target_sim_info)
    actor_rising_index, actor_rising_name = _resolve_rising_sign(actor_sim_info)
    target_rising_index, target_rising_name = _resolve_rising_sign(target_sim_info)
    actor_sun_index, actor_sun_name = _resolve_sun_sign(actor_sim_info)
    target_sun_index, target_sun_name = _resolve_sun_sign(target_sim_info)
    relationship_scores = relationship_summary.get("scores", {}) if isinstance(relationship_summary, dict) else {}
    friendship_score = relationship_scores.get("friendship")
    romance_score = relationship_scores.get("romance")
    actor_skill_level = _coerce_int(get_simstrology_skill_level(actor_sim_info), default=0) if actor_sim_info is not None else 0
    required_awareness_skill = _coerce_int(awareness_skill_level, default=3)
    return {
        "ok": True,
        "actor_rising_sign_index": actor_rising_index,
        "actor_rising_sign_name": actor_rising_name,
        "target_rising_sign_index": target_rising_index,
        "target_rising_sign_name": target_rising_name,
        "actor_sun_sign_index": actor_sun_index,
        "actor_sun_sign_name": actor_sun_name,
        "target_sun_sign_index": target_sun_index,
        "target_sun_sign_name": target_sun_name,
        "friendship_score": friendship_score,
        "romance_score": romance_score,
        "sun_tier_name": _resolve_active_sun_chemistry_tier_name(actor_sim_info, target_sim_info),
        "sun_unlocked": _coerce_int(friendship_score, default=0) > SUN_FAMILIARITY_THRESHOLD,
        "actor_skill_level": actor_skill_level,
        "actor_is_aware": actor_skill_level >= required_awareness_skill,
        "awareness_skill_level": required_awareness_skill,
        "friendship_track_id": FRIENDSHIP_TRACK_ID,
    }
