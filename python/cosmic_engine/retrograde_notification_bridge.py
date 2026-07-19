"""Retrograde notification routing bridge (event -> XML loot mapping).

This module intentionally separates:
- event detection (owned by transit_service)
- routing/mapping (this module)
- actual XML content (existing or future loot tunings)

By default the mapping is empty, so runtime processing is a safe no-op.
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from .astrology_skill_gate import simstrology_skill_meets, simstrology_skill_unlock_level, get_simstrology_skill_level
from .transit_service import CosmicTransitService, get_global_transit_service


# Key format: (planet_name, "start" | "end")
RETROGRADE_NOTIFICATION_LOOT_ID_BY_EVENT: Dict[Tuple[str, str], int] = {
    ("Mercury", "start"): 16999025911950867057,  # PlumAntics_CosmicEngineRetrogrades_Notify_MercuryRetrogradeStart
    ("Venus", "start"): 7342839272849963769,     # PlumAntics_CosmicEngineRetrogrades_Notify_VenusRetrogradeStart
    ("Mars", "start"): 5644155563595867911,      # PlumAntics_CosmicEngineRetrogrades_Notify_MarsRetrogradeStart
    ("Jupiter", "start"): 12034719427552703737,  # PlumAntics_CosmicEngineRetrogrades_Notify_JupiterRetrogradeStart
    ("Saturn", "start"): 4106986000893621385,    # PlumAntics_CosmicEngineRetrogrades_Notify_SaturnRetrogradeStart
    ("Mercury", "end"): 16999025911950867058,    # PlumAntics_CosmicEngineRetrogrades_Notify_MercuryRetrogradeEnd
    ("Venus", "end"): 7342839272849963770,       # PlumAntics_CosmicEngineRetrogrades_Notify_VenusRetrogradeEnd
    ("Mars", "end"): 5644155563595867912,        # PlumAntics_CosmicEngineRetrogrades_Notify_MarsRetrogradeEnd
    ("Jupiter", "end"): 12034719427552703738,    # PlumAntics_CosmicEngineRetrogrades_Notify_JupiterRetrogradeEnd
    ("Saturn", "end"): 4106986000893621386,      # PlumAntics_CosmicEngineRetrogrades_Notify_SaturnRetrogradeEnd
}

_LAST_NOTIFICATION_ROUTING_SUMMARY: Dict[str, object] = {}


def _normalized_key(body: object, event_name: object) -> Tuple[str, str]:
    return (str(body or ""), str(event_name or ""))


def _build_dispatch_plan(
    events: Sequence[Mapping[str, object]],
) -> Tuple[List[Dict[str, object]], Dict[str, int]]:
    plan: List[Dict[str, object]] = []
    stats = {
        "events_seen": 0,
        "events_mapped": 0,
        "events_unmapped": 0,
    }
    for event in events:
        stats["events_seen"] += 1
        key = _normalized_key(event.get("body"), event.get("event"))
        loot_id = RETROGRADE_NOTIFICATION_LOOT_ID_BY_EVENT.get(key)
        if loot_id is None:
            stats["events_unmapped"] += 1
            continue
        stats["events_mapped"] += 1
        plan.append(
            {
                "event_id": event.get("id"),
                "body": key[0],
                "event": key[1],
                "loot_id": int(loot_id),
                "source": event.get("source"),
                "count": int(event.get("count", 1) or 1),
            }
        )
    return plan, stats


def _get_services_module():
    try:
        import services  # type: ignore

        return services
    except Exception:
        return None


def _get_action_instance_manager():
    try:
        import sims4.resources  # type: ignore
    except Exception:
        return None
    services = _get_services_module()
    if services is None:
        return None
    get_instance_manager = getattr(services, "get_instance_manager", None)
    if not callable(get_instance_manager):
        return None
    for type_name in ("ACTION",):
        tuning_type = getattr(sims4.resources.Types, type_name, None)
        if tuning_type is None:
            continue
        try:
            return get_instance_manager(tuning_type)
        except Exception:
            continue
    return None


def _resolve_loot_tuning_by_id(loot_id: int):
    manager = _get_action_instance_manager()
    if manager is None:
        return None
    for attr_name in ("get",):
        fn = getattr(manager, attr_name, None)
        if callable(fn):
            try:
                loot = fn(int(loot_id))
            except Exception:
                loot = None
            if loot is not None:
                return loot
    for attr_name in ("types", "_tuned_classes"):
        value = getattr(manager, attr_name, None)
        if isinstance(value, dict):
            return value.get(int(loot_id))
    return None


def _get_active_sim_info():
    services = _get_services_module()
    if services is None:
        return None
    try:
        client_manager = services.client_manager()
    except Exception:
        client_manager = None
    if client_manager is None:
        return None
    get_first_client = getattr(client_manager, "get_first_client", None)
    client = None
    if callable(get_first_client):
        try:
            client = get_first_client()
        except Exception:
            client = None
    if client is None:
        return None
    for attr in ("active_sim_info",):
        sim_info = getattr(client, attr, None)
        if sim_info is not None:
            return sim_info
    active_sim = getattr(client, "active_sim", None)
    if active_sim is not None:
        return getattr(active_sim, "sim_info", None) or active_sim
    return None


def _make_single_sim_resolver(sim_info):
    try:
        from event_testing.resolver import SingleSimResolver  # type: ignore

        return SingleSimResolver(sim_info)
    except Exception:
        return None


def _apply_loot_to_active_sim(loot_id: int) -> bool:
    loot = _resolve_loot_tuning_by_id(int(loot_id))
    if loot is None:
        return False
    sim_info = _get_active_sim_info()
    if sim_info is None:
        return False
    resolver = _make_single_sim_resolver(sim_info)
    if resolver is None:
        return False

    apply_fn = getattr(loot, "apply_to_resolver", None)
    if callable(apply_fn):
        try:
            apply_fn(resolver)
            return True
        except Exception:
            return False

    try:
        loot_instance = loot()
    except Exception:
        loot_instance = None
    apply_fn = getattr(loot_instance, "apply_to_resolver", None)
    if callable(apply_fn):
        try:
            apply_fn(resolver)
            return True
        except Exception:
            return False

    return False


def process_pending_retrograde_notifications(
    *,
    transit_service: Optional[CosmicTransitService] = None,
    allowed_sources: Optional[Iterable[str]] = ("clock_snapshot",),
    consume_unmapped: bool = False,
    max_events: int = 20,
) -> Dict[str, object]:
    """Route pending retrograde events to mapped XML loots (if configured).

    Returns a debug summary. If no mapping exists, this is a safe no-op and
    leaves events in the queue unless consume_unmapped=True.
    """
    service = transit_service or get_global_transit_service()

    if not RETROGRADE_NOTIFICATION_LOOT_ID_BY_EVENT:
        summary = {
            "ok": True,
            "configured_mappings": 0,
            "events_considered": 0,
            "events_consumed": 0,
            "events_mapped": 0,
            "events_dispatched": 0,
            "events_failed_dispatch": 0,
            "events_unmapped": 0,
            "note": "no_mappings_configured",
        }
        _LAST_NOTIFICATION_ROUTING_SUMMARY.clear()
        _LAST_NOTIFICATION_ROUTING_SUMMARY.update(summary)
        return dict(summary)

    events = service.peek_pending_retrograde_events(limit=max_events)
    if allowed_sources is not None:
        allowed = {str(s) for s in allowed_sources}
        events = [e for e in events if str(e.get("source")) in allowed]

    plan, stats = _build_dispatch_plan(events)
    active_by_body = service.retrograde_active_by_body()
    valid_plan: List[Dict[str, object]] = []
    stale_event_ids: List[int] = []
    stale_event_count = 0
    for row in plan:
        body = str(row.get("body") or "")
        event_name = str(row.get("event") or "")
        if event_name == "start" and not bool(active_by_body.get(body)):
            try:
                stale_event_ids.append(int(row.get("event_id")))
            except Exception:
                pass
            stale_event_count += 1
            continue
        valid_plan.append(row)

    if stale_event_ids:
        service.consume_pending_retrograde_events_by_ids(stale_event_ids)

    active_sim_info = _get_active_sim_info()
    required_level = simstrology_skill_unlock_level("retrograde_awareness", 2)
    active_skill_level = int(get_simstrology_skill_level(active_sim_info))
    skill_gate_passed = simstrology_skill_meets(active_sim_info, required_level)
    dispatched = 0
    failed = 0
    events_skipped_skill_gate = 0
    if skill_gate_passed:
        for row in valid_plan:
            if _apply_loot_to_active_sim(int(row["loot_id"])):
                dispatched += 1
            else:
                failed += 1
    else:
        events_skipped_skill_gate = len(valid_plan)

    # Keep one-shot retrograde notices pending until they are actually
    # eligible to display. Otherwise a skill-gated block or a transient
    # dispatch failure permanently eats the event.
    should_consume = bool(consume_unmapped)
    if not should_consume and skill_gate_passed and dispatched > 0:
        should_consume = True
    consumed_count = 0
    if should_consume and events:
        consumed = service.consume_pending_retrograde_events_filtered(
            sources=allowed_sources,
            limit=len(events),
        )
        consumed_count = len(consumed)

    summary = {
        "ok": True,
        "configured_mappings": len(RETROGRADE_NOTIFICATION_LOOT_ID_BY_EVENT),
        "events_considered": int(stats["events_seen"]),
        "events_consumed": int(consumed_count),
        "events_mapped": int(stats["events_mapped"]),
        "events_stale_discarded": int(stale_event_count),
        "events_dispatched": int(dispatched),
        "events_failed_dispatch": int(failed),
        "events_unmapped": int(stats["events_unmapped"]),
        "events_skipped_skill_gate": int(events_skipped_skill_gate),
        "skill_gate_required_level": int(required_level),
        "active_sim_skill_level": int(active_skill_level),
        "skill_gate_blocked": 0 if skill_gate_passed else 1,
    }
    _LAST_NOTIFICATION_ROUTING_SUMMARY.clear()
    _LAST_NOTIFICATION_ROUTING_SUMMARY.update(summary)
    return dict(summary)


def get_last_notification_routing_summary() -> Dict[str, object]:
    return dict(_LAST_NOTIFICATION_ROUTING_SUMMARY)
