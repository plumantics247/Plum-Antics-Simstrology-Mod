"""Shared dirty-sim scope queue for consolidated runtime sync passes."""

from __future__ import annotations

from typing import Dict, Iterable, Optional, Tuple

SCOPE_PLANET_HOUSES = "planet_houses"
SCOPE_HOUSE_INGRESS = "house_ingress"
SCOPE_NATAL_SNAPSHOTS = "natal_snapshots"
SCOPE_VISIBLE_SIGN_BUFFS = "visible_sign_buffs"
SCOPE_RISING_BUFFS = "rising_buffs"
SCOPE_MOON_RETURN = "moon_return"
SCOPE_SOLAR_RETURN = "solar_return"
SCOPE_RETROGRADE_MARKERS = "retrograde_markers"
SCOPE_RETROGRADE_CONSEQUENCES = "retrograde_consequences"
SCOPE_CRYSTAL_RESONANCE = "crystal_resonance"

_KNOWN_SCOPES = frozenset(
    (
        SCOPE_PLANET_HOUSES,
        SCOPE_HOUSE_INGRESS,
        SCOPE_NATAL_SNAPSHOTS,
        SCOPE_VISIBLE_SIGN_BUFFS,
        SCOPE_RISING_BUFFS,
        SCOPE_MOON_RETURN,
        SCOPE_SOLAR_RETURN,
        SCOPE_RETROGRADE_MARKERS,
        SCOPE_RETROGRADE_CONSEQUENCES,
        SCOPE_CRYSTAL_RESONANCE,
    )
)

_STATE = {
    "pending_scopes": set(),
    "pending_sim_ids_by_scope": {},
    "last_reason_by_scope": {},
    "flush_inflight": False,
}


def _normalize_scopes(scopes) -> Tuple[str, ...]:
    if scopes is None:
        return ()
    if isinstance(scopes, str):
        candidates = (scopes,)
    else:
        candidates = tuple(scopes)
    out = []
    seen = set()
    for candidate in candidates:
        scope = str(candidate or "").strip()
        if not scope or scope not in _KNOWN_SCOPES or scope in seen:
            continue
        seen.add(scope)
        out.append(scope)
    return tuple(out)


def _resolve_sim_id(sim_info) -> Optional[int]:
    if sim_info is None:
        return None
    for attr_name in ("sim_id", "id"):
        value = getattr(sim_info, attr_name, None)
        if value is None:
            continue
        try:
            return int(value)
        except Exception:
            continue
    return None


def pending_scopes() -> Tuple[str, ...]:
    return tuple(sorted(_STATE.get("pending_scopes", set())))


def pending_summary() -> Dict[str, object]:
    sim_ids_by_scope = _STATE.get("pending_sim_ids_by_scope", {})
    return {
        "pending_scopes": pending_scopes(),
        "pending_scope_count": len(_STATE.get("pending_scopes", set())),
        "pending_sim_counts_by_scope": {
            scope: len(sim_ids) for scope, sim_ids in sim_ids_by_scope.items() if sim_ids
        },
        "flush_inflight": bool(_STATE.get("flush_inflight")),
    }


def mark_scope_dirty(scopes, *, sim_id: Optional[int] = None, reason: str = "unspecified") -> Dict[str, object]:
    normalized_scopes = _normalize_scopes(scopes)
    pending = _STATE.setdefault("pending_scopes", set())
    sim_ids_by_scope = _STATE.setdefault("pending_sim_ids_by_scope", {})
    reasons = _STATE.setdefault("last_reason_by_scope", {})
    for scope in normalized_scopes:
        pending.add(scope)
        reasons[scope] = str(reason or "unspecified")
        if sim_id is not None:
            sim_ids_by_scope.setdefault(scope, set()).add(int(sim_id))
    summary = pending_summary()
    summary["marked_scopes"] = normalized_scopes
    if sim_id is not None:
        summary["sim_id"] = int(sim_id)
    return summary


def mark_sim_dirty(sim_info, scopes, *, reason: str = "unspecified") -> Dict[str, object]:
    return mark_scope_dirty(scopes, sim_id=_resolve_sim_id(sim_info), reason=reason)


def flush_dirty_scopes(executor_by_scope: Dict[str, object], *, reason: str = "runtime") -> Dict[str, object]:
    if _STATE.get("flush_inflight"):
        return {
            "ok": False,
            "reason": "flush_inflight",
            "executed_scopes": (),
            "failed_scopes": (),
        }

    scopes = pending_scopes()
    if not scopes:
        return {
            "ok": True,
            "reason": str(reason or "runtime"),
            "executed_scopes": (),
            "failed_scopes": (),
            "skipped_scopes": (),
        }

    pending = _STATE.setdefault("pending_scopes", set())
    sim_ids_by_scope = _STATE.setdefault("pending_sim_ids_by_scope", {})
    reasons = _STATE.setdefault("last_reason_by_scope", {})
    claimed_sim_ids = {
        scope: tuple(sorted(sim_ids_by_scope.pop(scope, set())))
        for scope in scopes
    }
    claimed_reasons = {scope: reasons.pop(scope, str(reason or "runtime")) for scope in scopes}
    for scope in scopes:
        pending.discard(scope)

    executed = []
    failed = []
    skipped = []
    _STATE["flush_inflight"] = True
    try:
        for scope in scopes:
            callback = executor_by_scope.get(scope)
            if not callable(callback):
                skipped.append(scope)
                continue
            context = {
                "scope": scope,
                "reason": str(reason or "runtime"),
                "mark_reason": claimed_reasons.get(scope, str(reason or "runtime")),
                "sim_ids": claimed_sim_ids.get(scope, ()),
            }
            try:
                callback(context)
                executed.append(scope)
            except Exception:
                failed.append(scope)
                mark_scope_dirty(
                    (scope,),
                    reason=claimed_reasons.get(scope, str(reason or "runtime")),
                )
                for sim_id in claimed_sim_ids.get(scope, ()):
                    mark_scope_dirty((scope,), sim_id=int(sim_id), reason=claimed_reasons.get(scope, str(reason or "runtime")))
    finally:
        _STATE["flush_inflight"] = False

    return {
        "ok": not failed,
        "reason": str(reason or "runtime"),
        "executed_scopes": tuple(executed),
        "failed_scopes": tuple(failed),
        "skipped_scopes": tuple(skipped),
        "pending_after": pending_summary(),
    }
