"""Active-sim watched house ingress notifications (1st / 4th / 10th).

This is a Python-notification path on purpose so the notice body can include
the current house sign without exploding XML variants.

Design notes:
- active sim only (first pass, avoids NPC/household notification spam)
- ingress only (fires when a planet changes into a watched house)
- first observation is baseline only (no retroactive popup on load/travel)
"""

from __future__ import annotations

from typing import Dict, Mapping, Optional

from .astrology_skill_gate import simstrology_skill_meets, simstrology_skill_unlock_level, get_simstrology_skill_level
from .loot_actions import _collect_trait_ids_and_markers
from .planet_house_markers import _build_house_sign_map_for_sim, _show_notification_with_planet_icon
from .transit_core import BODY_NAMES, SIGNS
from .transit_service import CosmicTransitService, get_global_transit_service


_WATCHED_HOUSES: Dict[int, Dict[str, str]] = {
    0: {"label": "1st House", "theme": "identity"},
    3: {"label": "4th House", "theme": "home"},
    9: {"label": "10th House", "theme": "work and career"},
}

_LAST_ACTIVE_SIM_HOUSES_BY_SIM_ID: Dict[int, Dict[str, Optional[int]]] = {}
_LAST_INGRESS_SUMMARY: Dict[str, object] = {}


def _ingress_body_names(transit_service: Optional[CosmicTransitService] = None):
    resolver = getattr(transit_service, "active_body_names", None)
    if callable(resolver):
        try:
            return tuple(resolver())
        except Exception:
            pass
    return tuple(BODY_NAMES)


def _get_services_module():
    try:
        import services  # type: ignore

        return services
    except Exception:
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

    sim_info = getattr(client, "active_sim_info", None)
    if sim_info is not None:
        return sim_info
    active_sim = getattr(client, "active_sim", None)
    if active_sim is not None:
        return getattr(active_sim, "sim_info", None) or active_sim
    return None


def _sim_id(sim_info) -> Optional[int]:
    for attr in ("sim_id", "id", "guid64", "sim_guid"):
        value = getattr(sim_info, attr, None)
        if value is None:
            continue
        try:
            return int(value)
        except Exception:
            continue
    return None


def _sim_display_name(sim_info) -> str:
    first = getattr(sim_info, "first_name", None)
    last = getattr(sim_info, "last_name", None)
    if first or last:
        return "{0} {1}".format(first or "", last or "").strip()
    full_name = getattr(sim_info, "full_name", None)
    if full_name:
        try:
            return str(full_name)
        except Exception:
            pass
    return "Your Sim"


def _raw_text(value: str):
    try:
        from sims4.localization import LocalizationHelperTuning  # type: ignore

        return LocalizationHelperTuning.get_raw_text(str(value))
    except Exception:
        return str(value)


def _show_notification(title: str, text: str, *, body: Optional[str] = None) -> bool:
    # Reuse the transit notice icon path (planet icon by body), with graceful fallback.
    return _show_notification_with_planet_icon(title, text, body=body, owner=_get_active_sim_info())


def _show_notification_legacy(title: str, text: str) -> bool:
    try:
        from ui.ui_dialog_notification import UiDialogNotification  # type: ignore

        notification = UiDialogNotification.TunableFactory().default(
            None,
            title=lambda *_, **__: _raw_text(title),
            text=lambda *_, **__: _raw_text(text),
        )
        notification.show_dialog()
        return True
    except Exception:
        return False


def _current_body_house_map_for_active_sim(
    transit_service: CosmicTransitService,
) -> Optional[Dict[str, Dict[str, object]]]:
    sim_info = _get_active_sim_info()
    if sim_info is None:
        return None

    trait_ids, marker_trait_ids = _collect_trait_ids_and_markers(sim_info)
    house_sign_map = _build_house_sign_map_for_sim(trait_ids, marker_trait_ids)
    if house_sign_map is None or len(house_sign_map) < 12:
        return None

    chart = transit_service.chart_for_house_sign_map(house_sign_map)
    sid = _sim_id(sim_info)
    if sid is None:
        return None
    return {
        "sim_id": int(sid),
        "sim_info": sim_info,
        "house_sign_map": dict(house_sign_map),
        "chart": chart,
    }


def _format_ingress_title(body: str, house_label: str) -> str:
    return "{0} Transit: {1}".format(str(body), str(house_label))


def _format_ingress_text(body: str, house_label: str, theme: str, sign_name: Optional[str]) -> str:
    if sign_name:
        return (
            "{0} has entered your {1} ({2}). "
            "That house is currently in {3}."
        ).format(body, house_label, theme, sign_name)
    return "{0} has entered your {1} ({2}).".format(body, house_label, theme)


def process_active_sim_house_ingress_notifications(
    *,
    transit_service: Optional[CosmicTransitService] = None,
    max_notices: int = 5,
    refresh_baseline: bool = False,
    show_notifications: bool = True,
) -> Dict[str, object]:
    """Detect and optionally notify for active-sim ingress into watched houses.

    Returns a debug summary. First observation is baseline-only.
    """
    service = transit_service or get_global_transit_service()
    summary: Dict[str, object] = {
        "ok": True,
        "active_sim_found": False,
        "sim_has_house_map": False,
        "baseline_initialized": False,
        "events_detected": 0,
        "events_notified": 0,
        "events_skipped_first_observation": 0,
        "events_skipped_skill_gate": 0,
        "events": [],
    }

    if refresh_baseline:
        _LAST_ACTIVE_SIM_HOUSES_BY_SIM_ID.clear()

    payload = _current_body_house_map_for_active_sim(service)
    if not isinstance(payload, dict):
        _LAST_INGRESS_SUMMARY.clear()
        _LAST_INGRESS_SUMMARY.update(summary)
        return dict(summary)

    sim_info = payload.get("sim_info")
    sim_id = int(payload.get("sim_id", 0) or 0)
    chart = payload.get("chart")
    house_sign_map = payload.get("house_sign_map")

    summary["active_sim_found"] = True
    if not isinstance(chart, Mapping) or not isinstance(house_sign_map, Mapping):
        _LAST_INGRESS_SUMMARY.clear()
        _LAST_INGRESS_SUMMARY.update(summary)
        return dict(summary)

    summary["sim_has_house_map"] = True
    summary["sim_id"] = sim_id
    summary["sim_name"] = _sim_display_name(sim_info)

    current_by_body: Dict[str, Optional[int]] = {}
    active_body_names = _ingress_body_names(service)
    for body in active_body_names:
        row = chart.get(body, {})
        house_index = None
        if isinstance(row, Mapping):
            value = row.get("house_index")
            if isinstance(value, int):
                house_index = int(value)
        current_by_body[body] = house_index

    previous_by_body = _LAST_ACTIVE_SIM_HOUSES_BY_SIM_ID.get(sim_id)
    _LAST_ACTIVE_SIM_HOUSES_BY_SIM_ID[sim_id] = dict(current_by_body)

    if not isinstance(previous_by_body, dict):
        summary["baseline_initialized"] = True
        summary["events_skipped_first_observation"] = 1
        _LAST_INGRESS_SUMMARY.clear()
        _LAST_INGRESS_SUMMARY.update(summary)
        return dict(summary)

    events = []
    for body in active_body_names:
        previous_house = previous_by_body.get(body)
        current_house = current_by_body.get(body)
        if current_house is None:
            continue
        if previous_house is None:
            continue
        if int(previous_house) == int(current_house):
            continue
        if int(current_house) not in _WATCHED_HOUSES:
            continue

        meta = _WATCHED_HOUSES[int(current_house)]
        sign_name = None
        sign_index = house_sign_map.get(int(current_house))
        if isinstance(sign_index, int):
            sign_name = SIGNS[int(sign_index) % 12]

        event = {
            "sim_id": int(sim_id),
            "sim_name": summary.get("sim_name"),
            "body": str(body),
            "from_house_index": int(previous_house),
            "to_house_index": int(current_house),
            "house_label": meta["label"],
            "house_theme": meta["theme"],
            "house_sign_name": sign_name,
        }
        events.append(event)

    summary["events_detected"] = len(events)
    summary["events"] = list(events)

    if show_notifications and events:
        required_level = simstrology_skill_unlock_level("transit_awareness", 4)
        summary["skill_gate_required_level"] = int(required_level)
        summary["active_sim_skill_level"] = int(get_simstrology_skill_level(sim_info))
        if not simstrology_skill_meets(sim_info, required_level):
            summary["events_skipped_skill_gate"] = min(len(events), max(0, int(max_notices)))
            _LAST_INGRESS_SUMMARY.clear()
            _LAST_INGRESS_SUMMARY.update(summary)
            return dict(summary)
        notified = 0
        for event in events[: max(0, int(max_notices))]:
            title = _format_ingress_title(str(event["body"]), str(event["house_label"]))
            text = _format_ingress_text(
                str(event["body"]),
                str(event["house_label"]),
                str(event["house_theme"]),
                event.get("house_sign_name"),
            )
            if _show_notification(title, text, body=str(event["body"])):
                notified += 1
        summary["events_notified"] = int(notified)

    _LAST_INGRESS_SUMMARY.clear()
    _LAST_INGRESS_SUMMARY.update(summary)
    return dict(summary)


def get_last_house_ingress_summary() -> Dict[str, object]:
    return dict(_LAST_INGRESS_SUMMARY)
