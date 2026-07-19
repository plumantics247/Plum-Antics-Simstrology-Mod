"""Thin TS4 bridge for the Big 3 private runtime."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Dict, Optional
import zlib

from ..adapter.big3_ports import (
    Big3ClockPort,
    Big3DispatchPort,
    Big3MappingPort,
    Big3SavePort,
    Big3SimPort,
)
from ..config_io import load_json_from_package
from ..core.charting import build_big3_chart, chart_record_to_payload
from ..core.default_planner import DefaultPlanner
from ..core.engine import AstroCoreEngine
from ..core.types import SimSnapshot
from .assignments import (
    AssignmentRequest,
    MOON_MODE_AUTO,
    MOON_MODE_LUNAR_PHASE,
    MOON_MODE_NATAL,
    MOON_MODE_RANDOM,
    MOON_MODE_SKIP,
    RISING_MODE_AUTO,
    RISING_MODE_RANDOM,
    RISING_MODE_SKIP,
    RISING_MODE_SUN_TIME,
    SUN_MODE_AUTO,
    SUN_MODE_PERSONALITY,
    SUN_MODE_SEASON,
    SUN_MODE_SKIP,
    is_childhood_age,
    normalize_age_name,
    normalize_assignment_request,
)
from .mapping_loader import MappingRepository
from .mode_lock import (
    clear_mode_lock,
    get_mode_lock,
    is_big3_mode_active,
    mode_status_payload,
    set_mode_lock,
    sync_mode_lock_traits,
)

try:
    import sims4.commands as s4_commands
except Exception:
    s4_commands = None

try:
    import services
except Exception:
    services = None


_RUNTIME = None
_PACKAGE_NAME = "plumantics_big3_runtime"


def _safe_int(value, default_value=0):
    try:
        return int(value)
    except Exception:
        return int(default_value)


def _safe_float(value, default_value=0.0):
    try:
        return float(value)
    except Exception:
        return float(default_value)


def _current_sim_minute():
    if services is None:
        return 0
    try:
        time_service = services.time_service()
    except Exception:
        time_service = None
    if time_service is None:
        return 0
    sim_now = getattr(time_service, "sim_now", None)
    if sim_now is None:
        return 0
    for attr in ("in_minutes", "absolute_minutes"):
        value = getattr(sim_now, attr, None)
        if callable(value):
            try:
                return max(0, _safe_int(value(), 0))
            except Exception:
                continue
        if value is not None:
            return max(0, _safe_int(value, 0))
    for attr in ("in_ticks", "absolute_ticks", "ticks"):
        value = getattr(sim_now, attr, None)
        if callable(value):
            try:
                return max(0, _safe_int(value(), 0) // 60)
            except Exception:
                continue
        if value is not None:
            return max(0, _safe_int(value, 0) // 60)
    return 0


def _current_sim_hour():
    return int(_current_sim_minute() // 60) % 24


def _enum_name(value):
    if value is None:
        return None
    name = getattr(value, "name", None)
    if isinstance(name, str) and name:
        return name
    text = str(value).strip()
    if "." in text:
        text = text.split(".")[-1]
    return text or None


def _season_pair():
    if services is None:
        return (None, None)
    try:
        season_service = services.season_service()
    except Exception:
        season_service = None
    if season_service is None:
        return (None, None)

    season_value = getattr(season_service, "season", None)
    if callable(season_value):
        try:
            season_value = season_value()
        except Exception:
            season_value = None

    segment_value = getattr(season_service, "season_segment", None)
    if callable(segment_value):
        try:
            segment_value = segment_value()
        except Exception:
            segment_value = None

    return (_enum_name(season_value), _enum_name(segment_value))


def _current_lunar_phase_name():
    if services is None:
        return None
    try:
        lunar_service = services.lunar_cycle_service()
    except Exception:
        lunar_service = None
    if lunar_service is None:
        return None

    for attr in ("current_phase", "current_lunar_phase", "phase"):
        value = getattr(lunar_service, attr, None)
        if callable(value):
            try:
                value = value()
            except Exception:
                value = None
        if value is not None:
            return _enum_name(value)
    return None


def _active_sim_info():
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


def _resolve_sim_info(sim_id):
    if sim_id in (None, -1):
        return _active_sim_info()
    if services is None:
        return None
    try:
        manager = services.sim_info_manager()
    except Exception:
        manager = None
    if manager is None:
        return None
    try:
        return manager.get(_safe_int(sim_id, 0))
    except Exception:
        return None


def _trait_manager():
    if services is None:
        return None
    try:
        import sims4.resources  # type: ignore

        return services.get_instance_manager(sims4.resources.Types.TRAIT)
    except Exception:
        return None


def _resolve_trait(trait_id):
    manager = _trait_manager()
    if manager is None:
        return None
    try:
        return manager.get(int(trait_id))
    except Exception:
        return None


def _equipped_traits(sim_info):
    trait_tracker = getattr(sim_info, "trait_tracker", None)
    if trait_tracker is None:
        return ()
    return tuple(getattr(trait_tracker, "equipped_traits", None) or ())


def _sim_has_trait(sim_info, trait_id):
    for trait in _equipped_traits(sim_info):
        guid = getattr(trait, "guid64", None)
        if guid is None:
            guid = getattr(trait, "guid", None)
        try:
            if int(guid) == int(trait_id):
                return True
        except Exception:
            continue
    return False


def _add_trait_if_missing(sim_info, trait_id):
    if _sim_has_trait(sim_info, trait_id):
        return False
    trait = _resolve_trait(trait_id)
    if trait is None:
        return False
    for owner in (getattr(sim_info, "trait_tracker", None), sim_info):
        add_fn = getattr(owner, "add_trait", None)
        if callable(add_fn):
            try:
                add_fn(trait)
                return True
            except Exception:
                continue
    return False


def _sync_sign_compatibility_after_big3_assignment(sim_info, reason="unknown"):
    sim_id = _safe_int(getattr(sim_info, "sim_id", None), 0) if sim_info is not None else 0
    if sim_id <= 0 and sim_info is not None:
        sim_id = _safe_int(getattr(sim_info, "id", None), 0)
    if sim_id <= 0:
        return {"ok": False, "reason": "sim_missing"}
    try:
        from cosmic_engine.sign_compatibility_runtime_seed import (
            sync_sign_compatibility_preferences_for_lifecycle_sim,
        )
    except Exception:
        return {"ok": False, "reason": "compatibility_import_failed", "sim_id": int(sim_id)}
    try:
        return sync_sign_compatibility_preferences_for_lifecycle_sim(
            int(sim_id),
            reason=str(reason or "runtime.big3_assignment"),
        )
    except Exception:
        return {"ok": False, "reason": "compatibility_sync_failed", "sim_id": int(sim_id)}


@dataclass
class _RuntimeModel:
    config: Dict[str, object]
    ids: Dict[str, object]
    testbed_root: Optional[str] = None

    def zodiac_order(self):
        order = self.config.get("zodiac_order", []) if isinstance(self.config, dict) else []
        return [str(sign).strip().upper() for sign in order]


class Big3RuntimeService(object):
    """Standalone Big 3 runtime built from vendored shared core pieces."""

    def __init__(self):
        config = load_json_from_package(_PACKAGE_NAME, "data/universe.config.json")
        ids = load_json_from_package(_PACKAGE_NAME, "data/ids.registry.json")
        self._model = _RuntimeModel(config=config, ids=ids)
        self._mapping_repo = MappingRepository(self._model)
        self._save_port = Big3SavePort()
        self._dispatch_port = Big3DispatchPort(
            sun_sign_trait_ids=self._trait_ids_from_group("sun_traits")
            | self._trait_ids_from_group("sun_traits_child"),
            moon_sign_trait_ids=self._trait_ids_from_group("moon_traits")
            | self._trait_ids_from_group("moon_traits_child"),
            skip_existing_sign_traits=True,
        )
        timebase = self._model.config.get("timebase", {}) if isinstance(self._model.config, dict) else {}
        self._clock_port = Big3ClockPort(
            sim_minute_provider=_current_sim_minute,
            season_provider=_season_pair,
            sim_days_per_year=_safe_float(timebase.get("sim_year_days", 28.0), 28.0),
            lunar_cycle_days=_safe_float(timebase.get("lunar_cycle_days", 8.0), 8.0),
        )
        self._sim_port = Big3SimPort()
        self._mapping_port = Big3MappingPort(
            fallback_mapping_repo=self._mapping_repo,
        )
        self._engine = AstroCoreEngine(
            clock_port=self._clock_port,
            sim_port=self._sim_port,
            planner_port=DefaultPlanner(),
            mapping_port=self._mapping_port,
            dispatch_port=self._dispatch_port,
            save_port=self._save_port,
            logger=None,
        )
        self._chart_record_payload_by_sim_id = {}

    def _trait_ids_from_group(self, group_name):
        group = self._model.ids.get(str(group_name), {}) if isinstance(self._model.ids, dict) else {}
        if not isinstance(group, dict):
            return set()
        out = set()
        for value in group.values():
            trait_id = _safe_int(value, 0)
            if trait_id > 0:
                out.add(int(trait_id))
        return out

    def _assignment_config(self):
        v2 = self._model.config.get("v2", {}) if isinstance(self._model.config, dict) else {}
        assignment = v2.get("assignment", {}) if isinstance(v2, dict) else {}
        return assignment if isinstance(assignment, dict) else {}

    def _assignment_loot_id(self, key):
        assignment = self._assignment_config()
        loot_ids = assignment.get("loot_ids", {}) if isinstance(assignment, dict) else {}
        if not isinstance(loot_ids, dict):
            return None
        tuning_id = _safe_int(loot_ids.get(str(key)), 0)
        return tuning_id if tuning_id > 0 else None

    def _childhood_loot_id(self, key):
        childhood = {
            "sun_add_child": 16959539105888300859,
            "moon_add_child_all": 250873907,
            "rising_add_child_all": 13680423494074038312,
            "refresh_lifecycle_router": 13880462707991368211,
        }
        tuning_id = _safe_int(childhood.get(str(key)), 0)
        return tuning_id if tuning_id > 0 else None

    def _refresh_router_loot_id(self):
        assignment = self._assignment_config()
        tuning_id = _safe_int(assignment.get("refresh_router_loot_id"), 0)
        return tuning_id if tuning_id > 0 else None

    def _run_refresh_router_after_assignment(self):
        assignment = self._assignment_config()
        return bool(assignment.get("run_refresh_router_after_assignment", False))

    def _snapshot_for_sim_info(self, sim_info):
        sim_id = _safe_int(getattr(sim_info, "sim_id", None), 0)
        if sim_id <= 0:
            sim_id = _safe_int(getattr(sim_info, "id", None), 0)
        household = getattr(sim_info, "household", None)
        household_id = getattr(household, "id", None) if household is not None else None
        return SimSnapshot(
            sim_id=sim_id,
            full_name="{0} {1}".format(
                getattr(sim_info, "first_name", "Sim"),
                getattr(sim_info, "last_name", ""),
            ).strip(),
            trait_ids=[],
            household_id=None if household_id is None else _safe_int(household_id, 0),
            sim_info=sim_info,
            metadata={},
        )

    def _current_sim_day(self):
        sim_minutes_per_day = self._model.config.get("timebase", {}).get("sim_minutes_per_day", 1440)
        sim_minutes_per_day = max(1, _safe_int(sim_minutes_per_day, 1440))
        return max(0, _current_sim_minute() // sim_minutes_per_day)

    def _trait_ids_for_sim_info(self, sim_info):
        try:
            return list(self._sim_port._collect_trait_ids(sim_info))
        except Exception:
            return []

    def _sign_index_by_trait_id(self, group_name):
        group = self._model.ids.get(str(group_name), {}) if isinstance(self._model.ids, dict) else {}
        if not isinstance(group, dict):
            return {}
        out = {}
        for sign_name, trait_id in group.items():
            resolved_trait_id = _safe_int(trait_id, 0)
            if resolved_trait_id <= 0:
                continue
            zodiac_order = self._model.zodiac_order()
            sign_text = str(sign_name).strip().upper()
            if sign_text not in zodiac_order:
                continue
            out[int(resolved_trait_id)] = zodiac_order.index(sign_text)
        return out

    def _resolve_sign_index_from_traits(self, trait_ids, group_names):
        trait_ids = {int(_safe_int(value, 0)) for value in list(trait_ids or []) if _safe_int(value, 0) > 0}
        if not trait_ids:
            return None
        for group_name in group_names:
            sign_index_by_trait_id = self._sign_index_by_trait_id(group_name)
            for trait_id in trait_ids:
                if trait_id in sign_index_by_trait_id:
                    return int(sign_index_by_trait_id[trait_id])
        return None

    def _chart_seed_for_sim(self, sim_id, sun_sign_index, moon_sign_index, rising_sign_index):
        token = "{0}:{1}:{2}:{3}:{4}".format(
            _safe_int(sim_id, 0),
            _safe_int(sun_sign_index, 0),
            _safe_int(moon_sign_index, 0),
            _safe_int(rising_sign_index, 0),
            self._current_sim_day(),
        )
        return int(zlib.crc32(token.encode("utf-8")) & 0xFFFFFFFF)

    def _store_chart_record_for_sim_info(self, sim_info, metadata=None, overwrite_existing=False):
        if sim_info is None:
            return None
        sim_id = _safe_int(getattr(sim_info, "sim_id", None), 0)
        if sim_id <= 0:
            sim_id = _safe_int(getattr(sim_info, "id", None), 0)
        if sim_id <= 0:
            return None
        if (not bool(overwrite_existing)) and int(sim_id) in self._chart_record_payload_by_sim_id:
            payload = self._chart_record_payload_by_sim_id.get(int(sim_id))
            return dict(payload) if isinstance(payload, dict) else None

        trait_ids = self._trait_ids_for_sim_info(sim_info)
        sun_sign_index = self._resolve_sign_index_from_traits(
            trait_ids,
            ("sun_traits", "sun_traits_child"),
        )
        moon_sign_index = self._resolve_sign_index_from_traits(
            trait_ids,
            ("moon_traits", "moon_traits_child"),
        )
        rising_sign_index = self._resolve_sign_index_from_traits(
            trait_ids,
            ("rising_traits", "rising_traits_child"),
        )
        if sun_sign_index is None or moon_sign_index is None or rising_sign_index is None:
            return None

        household = getattr(sim_info, "household", None)
        household_id = _safe_int(getattr(household, "id", None), 0) if household is not None else 0
        resolved_metadata = dict(metadata or {})
        if household_id > 0:
            resolved_metadata.setdefault("household_id", household_id)
        resolved_metadata.setdefault("chart_source", "player_authored_big3")
        resolved_metadata.setdefault("sim_name", "{0} {1}".format(
            getattr(sim_info, "first_name", "Sim"),
            getattr(sim_info, "last_name", ""),
        ).strip())

        record = build_big3_chart(
            sim_id=sim_id,
            created_at_sim_day=self._current_sim_day(),
            created_age=normalize_age_name(getattr(sim_info, "age", None)) or "",
            sun_sign_index=sun_sign_index,
            moon_sign_index=moon_sign_index,
            rising_sign_index=rising_sign_index,
            rng_seed=self._chart_seed_for_sim(
                sim_id=sim_id,
                sun_sign_index=sun_sign_index,
                moon_sign_index=moon_sign_index,
                rising_sign_index=rising_sign_index,
            ),
            metadata=resolved_metadata,
        )
        payload = chart_record_to_payload(record)
        self._chart_record_payload_by_sim_id[int(sim_id)] = payload
        return payload

    def _refresh_chart_record_caches_for_sim_info(self, sim_info, reason="unknown"):
        payload = self._store_chart_record_for_sim_info(
            sim_info,
            metadata={
                "assignment_reason": str(reason or "unknown"),
                "assignment_flow": "refresh_chart_record_cache",
            },
            overwrite_existing=True,
        )
        if not isinstance(payload, dict):
            return {"ok": False, "reason": "missing_big3_traits"}

        sim_id = _safe_int(getattr(sim_info, "sim_id", None), 0) if sim_info is not None else 0
        if sim_id <= 0 and sim_info is not None:
            sim_id = _safe_int(getattr(sim_info, "id", None), 0)

        mirrored = False
        if sim_id > 0:
            try:
                from cosmic_engine.transit_service import get_global_transit_service

                get_global_transit_service().set_chart_record_payload(int(sim_id), dict(payload))
                mirrored = True
            except Exception:
                mirrored = False

        return {
            "ok": True,
            "reason": str(reason or "unknown"),
            "sim_id": int(sim_id) if sim_id > 0 else 0,
            "chart_payload": dict(payload),
            "mirrored_to_transit_service": bool(mirrored),
        }

    def get_chart_record_payload(self, sim_id):
        sim_id = _safe_int(sim_id, 0)
        if sim_id <= 0:
            return None
        payload = self._chart_record_payload_by_sim_id.get(int(sim_id))
        return dict(payload) if isinstance(payload, dict) else None

    def _run_loot_for_sim_info(self, loot_id, sim_info):
        if loot_id is None or sim_info is None:
            return False
        snapshot = self._snapshot_for_sim_info(sim_info)
        return bool(self._dispatch_port._run_loot(loot_id, snapshot))

    def assign_rising_sun_time_for_sim_info(
        self,
        sim_info,
        reason="unknown",
        *,
        sync_compatibility=True,
        refresh_chart_cache=True,
    ):
        from . import rising_assignment

        if sim_info is None:
            return {"applied": False, "reason": "sim_missing"}

        trait_ids = self._trait_ids_for_sim_info(sim_info)
        sun_sign_index = self._resolve_sign_index_from_traits(
            trait_ids,
            ("sun_traits", "sun_traits_child"),
        )
        if sun_sign_index is None:
            return {"applied": False, "reason": "sun_missing"}

        age_name = normalize_age_name(getattr(sim_info, "age", None))
        rising_group_name = "rising_traits_child" if is_childhood_age(age_name) else "rising_traits"
        rising_trait_group = self._model.ids.get(rising_group_name, {})
        zodiac_order = tuple(self._model.zodiac_order())
        trait_ids_by_sign_index = {
            zodiac_order.index(str(sign_name).strip().upper()): int(trait_id)
            for sign_name, trait_id in dict(rising_trait_group).items()
            if str(sign_name).strip().upper() in zodiac_order and _safe_int(trait_id, 0) > 0
        }

        current_hour = int(self._clock_port.sim_minute_provider() // 60) % 24
        result = rising_assignment.apply_sun_time_rising_assignment(
            sim_info,
            sun_sign_index=sun_sign_index,
            hour_24=current_hour,
            trait_ids_by_sign_index=trait_ids_by_sign_index,
            has_trait_fn=_sim_has_trait,
            add_trait_fn=_add_trait_if_missing,
        )
        result.setdefault("reason", str(reason))
        if bool(result.get("applied")):
            if bool(refresh_chart_cache):
                result["chart_refresh_summary"] = self._refresh_chart_record_caches_for_sim_info(
                    sim_info,
                    reason=str(reason or "unknown"),
                )
            if bool(sync_compatibility):
                result["sign_compatibility_sync_summary"] = (
                    _sync_sign_compatibility_after_big3_assignment(
                        sim_info,
                        reason=str(reason or "unknown"),
                    )
                )
        return result

    def assign_rising_random_for_sim_info(
        self,
        sim_info,
        reason="unknown",
        *,
        sync_compatibility=True,
        refresh_chart_cache=True,
    ):
        from . import rising_assignment
        import random

        if sim_info is None:
            return {"applied": False, "reason": "sim_missing"}

        age_name = normalize_age_name(getattr(sim_info, "age", None))
        rising_group_name = "rising_traits_child" if is_childhood_age(age_name) else "rising_traits"
        rising_trait_group = self._model.ids.get(rising_group_name, {})
        zodiac_order = tuple(self._model.zodiac_order())
        trait_ids_by_sign_index = {
            zodiac_order.index(str(sign_name).strip().upper()): int(trait_id)
            for sign_name, trait_id in dict(rising_trait_group).items()
            if str(sign_name).strip().upper() in zodiac_order and _safe_int(trait_id, 0) > 0
        }
        available_sign_indexes = tuple(sorted(trait_ids_by_sign_index.keys()))
        chooser = random.Random(_safe_int(getattr(sim_info, "sim_id", 0), 0)).choice

        result = rising_assignment.apply_random_rising_assignment(
            sim_info,
            available_sign_indexes=available_sign_indexes,
            trait_ids_by_sign_index=trait_ids_by_sign_index,
            has_any_rising_trait_fn=lambda candidate: self._resolve_sign_index_from_traits(
                self._trait_ids_for_sim_info(candidate),
                ("rising_traits", "rising_traits_child"),
            ) is not None,
            has_trait_fn=_sim_has_trait,
            add_trait_fn=_add_trait_if_missing,
            choose_sign_index_fn=chooser,
        )
        result.setdefault("reason", str(reason))
        if bool(result.get("applied")):
            if bool(refresh_chart_cache):
                result["chart_refresh_summary"] = self._refresh_chart_record_caches_for_sim_info(
                    sim_info,
                    reason=str(reason or "unknown"),
                )
            if bool(sync_compatibility):
                result["sign_compatibility_sync_summary"] = (
                    _sync_sign_compatibility_after_big3_assignment(
                        sim_info,
                        reason=str(reason or "unknown"),
                    )
                )
        return result

    def assign_moon_lunar_phase_for_sim_info(
        self,
        sim_info,
        reason="unknown",
        *,
        sync_compatibility=True,
        refresh_chart_cache=True,
    ):
        from . import moon_assignment

        if sim_info is None:
            return {"applied": False, "reason": "sim_missing"}

        trait_ids = self._trait_ids_for_sim_info(sim_info)
        sun_sign_index = self._resolve_sign_index_from_traits(
            trait_ids,
            ("sun_traits", "sun_traits_child"),
        )
        if sun_sign_index is None:
            return {"applied": False, "reason": "sun_missing"}

        age_name = normalize_age_name(getattr(sim_info, "age", None))
        moon_group_name = "moon_traits_child" if is_childhood_age(age_name) else "moon_traits"
        moon_trait_group = self._model.ids.get(moon_group_name, {})
        zodiac_order = tuple(self._model.zodiac_order())
        trait_ids_by_sign_index = {
            zodiac_order.index(str(sign_name).strip().upper()): int(trait_id)
            for sign_name, trait_id in dict(moon_trait_group).items()
            if str(sign_name).strip().upper() in zodiac_order and _safe_int(trait_id, 0) > 0
        }

        result = moon_assignment.apply_lunar_phase_moon_assignment(
            sim_info,
            sun_sign_index=sun_sign_index,
            lunar_bucket_key=moon_assignment.resolve_lunar_bucket_key(
                phase_name=_current_lunar_phase_name(),
                hour_24=_current_sim_hour(),
            ),
            trait_ids_by_sign_index=trait_ids_by_sign_index,
            has_any_moon_trait_fn=lambda candidate: self._resolve_sign_index_from_traits(
                self._trait_ids_for_sim_info(candidate),
                ("moon_traits", "moon_traits_child"),
            ) is not None,
            has_trait_fn=_sim_has_trait,
            add_trait_fn=_add_trait_if_missing,
        )
        result.setdefault("reason", str(reason))
        if bool(result.get("applied")):
            if bool(refresh_chart_cache):
                result["chart_refresh_summary"] = self._refresh_chart_record_caches_for_sim_info(
                    sim_info,
                    reason=str(reason or "unknown"),
                )
            if bool(sync_compatibility):
                result["sign_compatibility_sync_summary"] = (
                    _sync_sign_compatibility_after_big3_assignment(
                        sim_info,
                        reason=str(reason or "unknown"),
                    )
                )
        return result

    def assign_moon_random_for_sim_info(
        self,
        sim_info,
        reason="unknown",
        *,
        sync_compatibility=True,
        refresh_chart_cache=True,
    ):
        from . import moon_assignment
        import random

        if sim_info is None:
            return {"applied": False, "reason": "sim_missing"}

        age_name = normalize_age_name(getattr(sim_info, "age", None))
        moon_group_name = "moon_traits_child" if is_childhood_age(age_name) else "moon_traits"
        moon_trait_group = self._model.ids.get(moon_group_name, {})
        zodiac_order = tuple(self._model.zodiac_order())
        trait_ids_by_sign_index = {
            zodiac_order.index(str(sign_name).strip().upper()): int(trait_id)
            for sign_name, trait_id in dict(moon_trait_group).items()
            if str(sign_name).strip().upper() in zodiac_order and _safe_int(trait_id, 0) > 0
        }
        available_sign_indexes = tuple(sorted(trait_ids_by_sign_index.keys()))
        chooser = random.Random(_safe_int(getattr(sim_info, "sim_id", 0), 0)).choice

        result = moon_assignment.apply_random_moon_assignment(
            sim_info,
            available_sign_indexes=available_sign_indexes,
            trait_ids_by_sign_index=trait_ids_by_sign_index,
            has_any_moon_trait_fn=lambda candidate: self._resolve_sign_index_from_traits(
                self._trait_ids_for_sim_info(candidate),
                ("moon_traits", "moon_traits_child"),
            ) is not None,
            has_trait_fn=_sim_has_trait,
            add_trait_fn=_add_trait_if_missing,
            choose_sign_index_fn=chooser,
        )
        result.setdefault("reason", str(reason))
        if bool(result.get("applied")):
            if bool(refresh_chart_cache):
                result["chart_refresh_summary"] = self._refresh_chart_record_caches_for_sim_info(
                    sim_info,
                    reason=str(reason or "unknown"),
                )
            if bool(sync_compatibility):
                result["sign_compatibility_sync_summary"] = (
                    _sync_sign_compatibility_after_big3_assignment(
                        sim_info,
                        reason=str(reason or "unknown"),
                    )
                )
        return result

    def tick(self, reason="manual"):
        if not is_big3_mode_active():
            return None
        return self._engine.tick(reason=reason)

    def status(self):
        payload = self._engine.build_save_payload()
        payload["package_name"] = _PACKAGE_NAME
        payload["known_signal_loot_rules"] = len(
            getattr(self._mapping_repo, "_signal_loot_rules", {}) or {}
        )
        payload["chart_record_count"] = len(self._chart_record_payload_by_sim_id)
        payload["mode_lock"] = get_mode_lock()
        payload["mode_active"] = is_big3_mode_active()
        return payload

    def _effective_auto_modes_for_age(self, age_name):
        if is_childhood_age(age_name):
            return (SUN_MODE_SEASON, MOON_MODE_LUNAR_PHASE, RISING_MODE_SUN_TIME)
        return (SUN_MODE_PERSONALITY, MOON_MODE_LUNAR_PHASE, RISING_MODE_SUN_TIME)

    def _resolve_requested_modes(self, age_name, request):
        normalized = normalize_assignment_request(request)
        sun_mode = normalized.sun_mode
        moon_mode = normalized.moon_mode
        rising_mode = normalized.rising_mode
        auto_sun, auto_moon, auto_rising = self._effective_auto_modes_for_age(age_name)
        if sun_mode == SUN_MODE_AUTO:
            sun_mode = auto_sun
        if moon_mode == MOON_MODE_AUTO:
            moon_mode = auto_moon
        if rising_mode == RISING_MODE_AUTO:
            rising_mode = auto_rising
        if moon_mode == MOON_MODE_NATAL:
            # Big 3 runtime has no natal-specific moon loot yet; keep auto assignment usable.
            moon_mode = MOON_MODE_LUNAR_PHASE
        return AssignmentRequest(
            sun_mode=sun_mode,
            moon_mode=moon_mode,
            rising_mode=rising_mode,
            overwrite_existing=bool(normalized.overwrite_existing),
        )

    def assign_big3_for_sim(self, sim_id=-1, request=None):
        if not is_big3_mode_active():
            return {"ok": False, "error": "mode_locked:cosmic"}
        sim_info = _resolve_sim_info(sim_id)
        if sim_info is None:
            return {"ok": False, "error": "sim_not_found"}

        age_name = normalize_age_name(getattr(sim_info, "age", None))
        resolved = self._resolve_requested_modes(age_name, request or AssignmentRequest())
        result = {
            "ok": True,
            "sim_id": _safe_int(getattr(sim_info, "sim_id", None), 0),
            "age": age_name,
            "sun_mode": resolved.sun_mode,
            "moon_mode": resolved.moon_mode,
            "rising_mode": resolved.rising_mode,
            "sun_applied": False,
            "moon_applied": False,
            "rising_applied": False,
        }

        if resolved.sun_mode == SUN_MODE_SEASON:
            result["sun_applied"] = self._run_loot_for_sim_info(
                self._assignment_loot_id("sun_season"), sim_info
            )
        elif resolved.sun_mode == SUN_MODE_PERSONALITY:
            result["sun_applied"] = self._run_loot_for_sim_info(
                self._assignment_loot_id("sun_personality"), sim_info
            )
        elif resolved.sun_mode != SUN_MODE_SKIP:
            result["ok"] = False
            result["error"] = "unsupported_sun_mode:{0}".format(resolved.sun_mode)
            return result

        if resolved.moon_mode == MOON_MODE_LUNAR_PHASE:
            result["moon_applied"] = bool(
                self.assign_moon_lunar_phase_for_sim_info(
                    sim_info,
                    reason="assign_big3_for_sim:lunar_phase",
                    sync_compatibility=False,
                    refresh_chart_cache=False,
                ).get("applied")
            )
        elif resolved.moon_mode == MOON_MODE_RANDOM:
            result["moon_applied"] = bool(
                self.assign_moon_random_for_sim_info(
                    sim_info,
                    reason="assign_big3_for_sim:random",
                    sync_compatibility=False,
                    refresh_chart_cache=False,
                ).get("applied")
            )
        elif resolved.moon_mode != MOON_MODE_SKIP:
            result["ok"] = False
            result["error"] = "unsupported_moon_mode:{0}".format(resolved.moon_mode)
            return result

        if resolved.rising_mode == RISING_MODE_SUN_TIME:
            result["rising_applied"] = bool(
                self.assign_rising_sun_time_for_sim_info(
                    sim_info,
                    reason="assign_big3_for_sim:sun_time",
                    sync_compatibility=False,
                    refresh_chart_cache=False,
                ).get("applied")
            )
        elif resolved.rising_mode == RISING_MODE_RANDOM:
            result["rising_applied"] = bool(
                self.assign_rising_random_for_sim_info(
                    sim_info,
                    reason="assign_big3_for_sim:random",
                    sync_compatibility=False,
                    refresh_chart_cache=False,
                ).get("applied")
            )
        elif resolved.rising_mode != RISING_MODE_SKIP:
            result["ok"] = False
            result["error"] = "unsupported_rising_mode:{0}".format(resolved.rising_mode)
            return result

        if self._run_refresh_router_after_assignment():
            self._run_loot_for_sim_info(self._refresh_router_loot_id(), sim_info)
        if bool(result["sun_applied"] or result["moon_applied"] or result["rising_applied"]):
            result["chart_refresh_summary"] = self._refresh_chart_record_caches_for_sim_info(
                sim_info,
                reason="big3_auto_assignment",
            )
            result["chart_record_built"] = bool(
                isinstance(result.get("chart_refresh_summary"), dict)
                and result["chart_refresh_summary"].get("ok")
            )
            result["sign_compatibility_sync_summary"] = (
                _sync_sign_compatibility_after_big3_assignment(
                    sim_info,
                    reason="assign_big3_for_sim",
                )
            )
        else:
            chart_payload = self._store_chart_record_for_sim_info(
                sim_info,
                metadata={
                    "assignment_reason": "big3_auto_assignment",
                    "sun_mode": resolved.sun_mode,
                    "moon_mode": resolved.moon_mode,
                    "rising_mode": resolved.rising_mode,
                },
                overwrite_existing=False,
            )
            result["chart_record_built"] = bool(chart_payload)
        return result

    def auto_assign_child_for_sim_info(self, sim_info, reason="born_in_world"):
        if not is_big3_mode_active():
            return {"ok": False, "error": "mode_locked:cosmic"}
        if sim_info is None:
            return {"ok": False, "error": "sim_not_found"}

        age_name = normalize_age_name(getattr(sim_info, "age", None))
        if not is_childhood_age(age_name):
            return {
                "ok": False,
                "error": "age_not_childhood",
                "age": age_name,
            }

        result = {
            "ok": True,
            "age": age_name,
            "reason": str(reason),
            "sim_id": _safe_int(getattr(sim_info, "sim_id", None), 0),
            "sun_applied": self._run_loot_for_sim_info(
                self._childhood_loot_id("sun_add_child"),
                sim_info,
            ),
            "moon_applied": self._run_loot_for_sim_info(
                self._childhood_loot_id("moon_add_child_all"),
                sim_info,
            ),
            "rising_applied": self._run_loot_for_sim_info(
                self._childhood_loot_id("rising_add_child_all"),
                sim_info,
            ),
        }
        self._run_loot_for_sim_info(
            self._childhood_loot_id("refresh_lifecycle_router"),
            sim_info,
        )
        chart_payload = self._store_chart_record_for_sim_info(
            sim_info,
            metadata={
                "assignment_reason": str(reason),
                "assignment_flow": "childhood_auto_assign",
            },
            overwrite_existing=False,
        )
        result["chart_record_built"] = bool(chart_payload)
        return result

    def capture_chart_for_sim(self, sim_id=-1, reason="manual_capture"):
        if not is_big3_mode_active():
            return {"ok": False, "error": "mode_locked:cosmic"}
        sim_info = _resolve_sim_info(sim_id)
        if sim_info is None:
            return {"ok": False, "error": "sim_not_found"}
        payload = self._store_chart_record_for_sim_info(
            sim_info,
            metadata={
                "assignment_reason": str(reason),
                "assignment_flow": "capture_from_existing_traits",
            },
            overwrite_existing=False,
        )
        if payload is None:
            return {
                "ok": False,
                "error": "missing_big3_traits",
                "sim_id": _safe_int(getattr(sim_info, "sim_id", None), 0),
            }
        return {
            "ok": True,
            "sim_id": _safe_int(getattr(sim_info, "sim_id", None), 0),
            "chart_record_built": True,
        }


def get_runtime():
    global _RUNTIME
    sync_mode_lock_traits()
    if _RUNTIME is None:
        _RUNTIME = Big3RuntimeService()
    return _RUNTIME


def big3_universe2_tick(_connection=None):
    report = get_runtime().tick(reason="manual")
    if s4_commands is not None and _connection is not None:
        if report is None:
            s4_commands.output(
                "Big 3 runtime inactive in this save (mode lock: {0}).".format(get_mode_lock()),
                _connection,
            )
            return False
        s4_commands.output(
            "Big3 runtime tick day={0} segment={1} actions={2}".format(
                report.sim_day,
                report.sim_segment,
                report.action_count,
            ),
            _connection,
        )
    return True


def big3_universe2_dispatcher_tick(_connection=None):
    return bool(big3_universe2_tick(_connection=_connection))


def big3_universe2_status(_connection=None):
    payload = get_runtime().status()
    if s4_commands is not None and _connection is not None:
        for key in (
            "package_name",
            "version",
            "key",
            "known_signal_loot_rules",
            "chart_record_count",
            "mode_lock",
            "mode_active",
        ):
            s4_commands.output("{0}: {1}".format(key, payload.get(key)), _connection)
    return payload


def big3_mode_status(_connection=None):
    payload = mode_status_payload("big3")
    if s4_commands is not None and _connection is not None:
        s4_commands.output(json.dumps(payload, sort_keys=True), _connection)
    return payload


def big3_mode_set(mode: str = "big3", _connection=None):
    ok = set_mode_lock(mode, source="big3.command")
    sync_summary = sync_mode_lock_traits()
    payload = mode_status_payload("big3")
    payload["sync"] = sync_summary
    if s4_commands is not None and _connection is not None:
        if not ok:
            s4_commands.output("Invalid Big 3 mode value: {0}".format(mode), _connection)
        s4_commands.output(json.dumps(payload, sort_keys=True), _connection)
    return bool(ok)


def big3_mode_clear(_connection=None):
    ok = clear_mode_lock(source="big3.command")
    sync_summary = sync_mode_lock_traits()
    payload = mode_status_payload("big3")
    payload["sync"] = sync_summary
    if s4_commands is not None and _connection is not None:
        s4_commands.output(json.dumps(payload, sort_keys=True), _connection)
    return bool(ok)


def big3_universe2_assign_big3_for_sim(
    sim_id: int = -1,
    sun_mode: str = SUN_MODE_AUTO,
    moon_mode: str = MOON_MODE_AUTO,
    rising_mode: str = RISING_MODE_AUTO,
    overwrite_existing: int = 0,
    _connection=None,
):
    result = get_runtime().assign_big3_for_sim(
        sim_id=sim_id,
        request=AssignmentRequest(
            sun_mode=sun_mode,
            moon_mode=moon_mode,
            rising_mode=rising_mode,
            overwrite_existing=bool(int(overwrite_existing)),
        ),
    )
    if s4_commands is not None and _connection is not None:
        s4_commands.output(str(result), _connection)
    return bool(result.get("ok"))


def big3_universe2_capture_chart_for_sim(
    sim_id: int = -1,
    reason: str = "manual_capture",
    _connection=None,
):
    result = get_runtime().capture_chart_for_sim(sim_id=sim_id, reason=reason)
    if s4_commands is not None and _connection is not None:
        s4_commands.output(str(result), _connection)
    return bool(result.get("ok"))


def big3_universe2_chart_record(sim_id: int = -1, _connection=None):
    sim_info = _resolve_sim_info(sim_id)
    if sim_info is None:
        payload = None
    else:
        payload = get_runtime().get_chart_record_payload(getattr(sim_info, "sim_id", sim_id))
    if s4_commands is not None and _connection is not None:
        if payload is None:
            s4_commands.output("No Big 3 chart record payload found.", _connection)
        else:
            s4_commands.output(json.dumps(payload, sort_keys=True, indent=2), _connection)
    return payload


def register_debug_commands():
    if s4_commands is None:
        return None

    @s4_commands.Command("big3.universe2.tick", command_type=s4_commands.CommandType.Live)
    def _cmd_tick(_connection=None):
        return bool(big3_universe2_tick(_connection=_connection))

    @s4_commands.Command(
        "big3.universe2.dispatcher_tick",
        command_type=s4_commands.CommandType.Live,
    )
    def _cmd_dispatcher_tick(_connection=None):
        return bool(big3_universe2_dispatcher_tick(_connection=_connection))

    @s4_commands.Command("big3.universe2.status", command_type=s4_commands.CommandType.Live)
    def _cmd_status(_connection=None):
        big3_universe2_status(_connection=_connection)
        return True

    @s4_commands.Command("big3.mode.status", command_type=s4_commands.CommandType.Live)
    def _cmd_mode_status(_connection=None):
        big3_mode_status(_connection=_connection)
        return True

    @s4_commands.Command("big3.mode.set", command_type=s4_commands.CommandType.Live)
    def _cmd_mode_set(mode: str = "big3", _connection=None):
        return bool(big3_mode_set(mode=mode, _connection=_connection))

    @s4_commands.Command("big3.mode.clear", command_type=s4_commands.CommandType.Live)
    def _cmd_mode_clear(_connection=None):
        return bool(big3_mode_clear(_connection=_connection))

    @s4_commands.Command(
        "big3.universe2.assign_big3_for_sim",
        command_type=s4_commands.CommandType.Live,
    )
    def _cmd_assign_big3_for_sim(
        sim_id: int = -1,
        sun_mode: str = SUN_MODE_AUTO,
        moon_mode: str = MOON_MODE_AUTO,
        rising_mode: str = RISING_MODE_AUTO,
        overwrite_existing: int = 0,
        _connection=None,
    ):
        return bool(
            big3_universe2_assign_big3_for_sim(
                sim_id=sim_id,
                sun_mode=sun_mode,
                moon_mode=moon_mode,
                rising_mode=rising_mode,
                overwrite_existing=overwrite_existing,
                _connection=_connection,
            )
        )

    @s4_commands.Command(
        "big3.universe2.capture_chart_for_sim",
        command_type=s4_commands.CommandType.Live,
    )
    def _cmd_capture_chart_for_sim(
        sim_id: int = -1,
        reason: str = "manual_capture",
        _connection=None,
    ):
        return bool(
            big3_universe2_capture_chart_for_sim(
                sim_id=sim_id,
                reason=reason,
                _connection=_connection,
            )
        )

    @s4_commands.Command(
        "big3.universe2.chart_record",
        command_type=s4_commands.CommandType.Live,
    )
    def _cmd_chart_record(sim_id: int = -1, _connection=None):
        big3_universe2_chart_record(sim_id=sim_id, _connection=_connection)
        return True

    return True
