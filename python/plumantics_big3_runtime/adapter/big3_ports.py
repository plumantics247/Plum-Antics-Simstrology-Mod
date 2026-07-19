"""Big 3 adapter ports for the vendored private runtime."""

from __future__ import annotations

from typing import Mapping, Optional

try:
    import services
    import sims4.resources
except Exception:
    services = None
    sims4 = None

from ..core.types import (
    ACTION_RUN_LOOT,
    ACTION_RUN_WEIGHTED_LOOT_TABLE,
    ACTION_SET_COMMODITY,
    AstroClock,
    DispatchResult,
    SimSnapshot,
)


_SEASON_INDEX = {
    "SPRING": 0,
    "SUMMER": 1,
    "FALL": 2,
    "AUTUMN": 2,
    "WINTER": 3,
}
_SEGMENT_INDEX = {
    "EARLY": 0,
    "MID": 1,
    "MIDDLE": 1,
    "PEAK": 1,
    "LATE": 2,
}

# Existing Big3 sign assignment loots.
_SUN_SIGNAL_ENTER_LOOT_BY_SIGN = {
    "ARIES": 429587337,
    "TAURUS": 506944317,
    "GEMINI": 1512857696,
    "CANCER": 2393511253,
    "LEO": 2407078947,
    "VIRGO": 437426406,
    "LIBRA": 122628565,
    "SCORPIO": 1564554120,
    "SAGITTARIUS": 1453199743,
    "CAPRICORN": 2192525866,
    "AQUARIUS": 1271968254,
    "PISCES": 3877182070,
}
_MOON_SIGNAL_ENTER_LOOT_BY_SIGN = {
    "ARIES": 2804873217,
    "TAURUS": 3585805589,
    "GEMINI": 4009011192,
    "CANCER": 2943509661,
    "LEO": 2484586187,
    "VIRGO": 3812642094,
    "LIBRA": 4271410941,
    "SCORPIO": 3707951424,
    "SAGITTARIUS": 2716646429,
    "CAPRICORN": 3859344386,
    "AQUARIUS": 3834984550,
    "PISCES": 3321581438,
}


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


class Big3ClockPort(object):
    """Clock provider using Big 3 time + season/segment providers."""

    def __init__(
        self,
        *,
        sim_minute_provider=None,
        season_provider=None,
        sim_days_per_year=28.0,
        lunar_cycle_days=8.0,
    ):
        self._sim_minute_provider = sim_minute_provider
        self._season_provider = season_provider
        self._sim_days_per_year = float(sim_days_per_year)
        self._lunar_cycle_days = float(lunar_cycle_days)

    def _segment_total_from_season(self):
        provider = self._season_provider
        if not callable(provider):
            return None
        season_name = None
        segment_name = None
        try:
            season_name, segment_name = provider()
        except Exception:
            return None
        season_idx = _SEASON_INDEX.get(str(season_name).strip().upper())
        segment_idx = _SEGMENT_INDEX.get(str(segment_name).strip().upper())
        if season_idx is None or segment_idx is None:
            return None
        return int((season_idx * 3) + segment_idx)

    def _sim_minute(self):
        provider = self._sim_minute_provider
        if callable(provider):
            try:
                return max(0, _safe_int(provider(), 0))
            except Exception:
                return 0
        return 0

    def current_clock(self):
        sim_minute = self._sim_minute()
        total_days = max(0, int(sim_minute) // 1440)
        segment_total = self._segment_total_from_season()
        if segment_total is None:
            segment_total = total_days % 12

        return AstroClock(
            total_days_elapsed=int(total_days),
            total_segments_elapsed=int(segment_total),
            lunar_cycle_days=max(1.0, _safe_float(self._lunar_cycle_days, 8.0)),
            sim_days_per_year=max(4.0, _safe_float(self._sim_days_per_year, 28.0)),
        )


class Big3SimPort(object):
    """Converts Big 3 sim rows into runtime SimSnapshot values."""

    def __init__(self, *, sim_snapshot_provider=None):
        self._sim_snapshot_provider = sim_snapshot_provider

    def _collect_trait_ids(self, sim_info):
        tracker = getattr(sim_info, "trait_tracker", None)
        if tracker is None:
            return []
        equipped = getattr(tracker, "equipped_traits", None)
        if equipped is None:
            return []

        out = []
        for trait in equipped:
            guid = getattr(trait, "guid64", None)
            if guid is None:
                guid = getattr(trait, "guid", None)
            if guid is None:
                continue
            try:
                out.append(int(guid))
            except Exception:
                continue
        return out

    def _full_name(self, sim_info):
        first = getattr(sim_info, "first_name", "Sim")
        last = getattr(sim_info, "last_name", "")
        return ("{0} {1}".format(first, last)).strip()

    def _rows_from_provider(self):
        provider = self._sim_snapshot_provider
        if not callable(provider):
            return []
        try:
            return list(provider())
        except Exception:
            return []

    def _rows_from_services(self):
        if services is None:
            return []
        try:
            manager = services.sim_info_manager()
        except Exception:
            manager = None
        if manager is None:
            return []
        gen = getattr(manager, "instanced_sims_gen", None)
        if not callable(gen):
            return []
        return list(gen())

    def iter_sims(self):
        rows = self._rows_from_provider()
        if not rows:
            rows = self._rows_from_services()

        out = []
        for row in rows:
            if isinstance(row, SimSnapshot):
                sim_id = _safe_int(getattr(row, "sim_id", None), 0)
                if sim_id > 0:
                    out.append(row)
                continue

            sim_info = getattr(row, "sim_info", None)
            sim_id = _safe_int(getattr(row, "sim_id", None), 0)
            if sim_id <= 0:
                sim_id = _safe_int(getattr(row, "id", None), 0)
            if sim_id <= 0 and sim_info is not None:
                sim_id = _safe_int(getattr(sim_info, "sim_id", None), 0)
                if sim_id <= 0:
                    sim_id = _safe_int(getattr(sim_info, "id", None), 0)
            if sim_id <= 0:
                continue

            if sim_info is None and getattr(row, "trait_tracker", None) is not None:
                sim_info = row

            full_name = str(getattr(row, "full_name", "") or "").strip()
            if not full_name and sim_info is not None:
                full_name = self._full_name(sim_info)
            if not full_name:
                full_name = "Sim {0}".format(int(sim_id))

            trait_ids = list(getattr(row, "trait_ids", []) or [])
            if not trait_ids and sim_info is not None:
                trait_ids = self._collect_trait_ids(sim_info)

            household_id = getattr(row, "household_id", None)
            if household_id is None and sim_info is not None:
                household = getattr(sim_info, "household", None)
                household_id = getattr(household, "id", None) if household is not None else None

            out.append(
                SimSnapshot(
                    sim_id=int(sim_id),
                    full_name=str(full_name),
                    trait_ids=[_safe_int(tid, 0) for tid in trait_ids if _safe_int(tid, 0) > 0],
                    household_id=None if household_id is None else _safe_int(household_id, 0),
                    sim_info=sim_info,
                    metadata={},
                )
            )
        return out


class Big3MappingPort(object):
    """Map runtime signal edges to Big 3 tuning IDs."""

    def __init__(
        self,
        mapping=None,
        *,
        enable_default_sign_mapping=True,
        fallback_mapping_repo=None,
    ):
        self._mapping = mapping or {}
        self._enable_default_sign_mapping = bool(enable_default_sign_mapping)
        self._fallback_mapping_repo = fallback_mapping_repo

    def _signal_sign(self, key, prefix):
        token = str(key)
        if not token.startswith(prefix):
            return None
        return token[len(prefix) :].strip().upper()

    def _sign_action(self, signal_key, edge):
        if str(edge).strip().lower() != "enter":
            return []

        sun_sign = self._signal_sign(signal_key, "SKY_SUN_SIGN_")
        if sun_sign is not None:
            tuning_id = _SUN_SIGNAL_ENTER_LOOT_BY_SIGN.get(sun_sign)
            if tuning_id is None:
                return []
            return [{"type": ACTION_RUN_LOOT, "tuning_id": int(tuning_id)}]

        moon_sign = self._signal_sign(signal_key, "SKY_MOON_SIGN_")
        if moon_sign is not None:
            tuning_id = _MOON_SIGNAL_ENTER_LOOT_BY_SIGN.get(moon_sign)
            if tuning_id is None:
                return []
            return [{"type": ACTION_RUN_LOOT, "tuning_id": int(tuning_id)}]

        return []

    def actions_for_signal(self, signal_key, edge):
        if self._enable_default_sign_mapping:
            mapped = self._sign_action(signal_key, edge)
            if mapped:
                return mapped

        key = "{0}:{1}".format(str(signal_key), str(edge))
        row = self._mapping.get(key, [])
        if isinstance(row, (list, tuple)):
            return list(row)

        repo = self._fallback_mapping_repo
        if repo is None:
            return []
        getter = getattr(repo, "action_defs_for_signal", None)
        if not callable(getter):
            return []
        try:
            rows = getter(signal_key, edge)
        except Exception:
            return []
        if not isinstance(rows, list):
            return []
        return rows


class Big3DispatchPort(object):
    """Bridge runtime action requests to TS4 loot/stat systems."""

    def __init__(
        self,
        *,
        sun_sign_trait_ids=None,
        moon_sign_trait_ids=None,
        skip_existing_sign_traits=True,
    ):
        self._sun_sign_trait_ids = self._normalize_trait_id_set(sun_sign_trait_ids)
        self._moon_sign_trait_ids = self._normalize_trait_id_set(moon_sign_trait_ids)
        self._skip_existing_sign_traits = bool(skip_existing_sign_traits)

    def _normalize_trait_id_set(self, values):
        out = set()
        if values is None:
            return out
        for value in values:
            trait_id = _safe_int(value, 0)
            if trait_id > 0:
                out.add(int(trait_id))
        return out

    def _sim_trait_id_set(self, sim_snapshot):
        trait_ids = list(getattr(sim_snapshot, "trait_ids", []) or [])
        return {int(_safe_int(value, 0)) for value in trait_ids if _safe_int(value, 0) > 0}

    def _should_skip_request_for_existing_sign_trait(self, request, sim_snapshot):
        if not self._skip_existing_sign_traits:
            return False
        edge = str(getattr(request, "edge", "")).strip().lower()
        if edge != "enter":
            return False
        signal_key = str(getattr(request, "signal_key", "")).strip().upper()
        if not signal_key:
            return False

        sim_trait_ids = self._sim_trait_id_set(sim_snapshot)
        if not sim_trait_ids:
            return False

        if signal_key.startswith("SKY_SUN_SIGN_") and self._sun_sign_trait_ids:
            return bool(sim_trait_ids & self._sun_sign_trait_ids)
        if signal_key.startswith("SKY_MOON_SIGN_") and self._moon_sign_trait_ids:
            return bool(sim_trait_ids & self._moon_sign_trait_ids)
        return False

    def _loot_manager(self):
        if services is None or sims4 is None:
            return None
        try:
            return services.get_instance_manager(sims4.resources.Types.ACTION)
        except Exception:
            return None

    def _stat_manager(self):
        if services is None or sims4 is None:
            return None
        try:
            return services.get_instance_manager(sims4.resources.Types.STATISTIC)
        except Exception:
            return None

    def _resolver(self, sim_info):
        getter = getattr(sim_info, "get_resolver", None)
        if callable(getter):
            try:
                return getter()
            except Exception:
                return None
        return None

    def _run_loot(self, loot_id, sim_snapshot):
        if loot_id is None:
            return False
        sim_info = getattr(sim_snapshot, "sim_info", None)
        if sim_info is None:
            return False
        manager = self._loot_manager()
        if manager is None:
            return False
        tuning = manager.get(int(loot_id))
        if tuning is None:
            return False

        resolver = self._resolver(sim_info)
        if resolver is None:
            return False

        for method_name in (
            "apply_to_resolver",
            "apply_to_resolver_and_get_result",
            "apply_to_single_resolver",
        ):
            method = getattr(tuning, method_name, None)
            if not callable(method):
                continue
            try:
                method(resolver)
                return True
            except Exception:
                continue
        return False

    def _run_weighted_loot_table(self, table_id, weights, sim_snapshot):
        del weights
        return self._run_loot(table_id, sim_snapshot)

    def _set_commodity(self, commodity_id, value, sim_snapshot):
        if commodity_id is None:
            return False
        sim_info = getattr(sim_snapshot, "sim_info", None)
        if sim_info is None:
            return False
        stat_manager = self._stat_manager()
        if stat_manager is None:
            return False
        stat_tuning = stat_manager.get(int(commodity_id))
        if stat_tuning is None:
            return False

        trackers = []
        for attr in ("commodity_tracker", "static_commodity_tracker", "statistic_tracker"):
            tracker = getattr(sim_info, attr, None)
            if tracker is not None:
                trackers.append(tracker)
        if not trackers:
            return False

        applied = False
        for tracker in trackers:
            adder = getattr(tracker, "add_statistic", None)
            statistic = None
            if callable(adder):
                try:
                    statistic = adder(stat_tuning)
                except Exception:
                    statistic = None

            for setter_name in ("set_value", "set_stat_value"):
                setter = getattr(tracker, setter_name, None)
                if callable(setter):
                    try:
                        setter(stat_tuning, float(value))
                        applied = True
                        continue
                    except Exception:
                        pass
                if statistic is not None:
                    stat_setter = getattr(statistic, setter_name, None)
                    if callable(stat_setter):
                        try:
                            stat_setter(float(value))
                            applied = True
                            continue
                        except Exception:
                            pass
        return bool(applied)

    def dispatch_requests(self, action_requests, sim_lookup):
        out = []
        for request in action_requests:
            sim_snapshot = sim_lookup.get(int(getattr(request, "target_sim_id", 0)))
            if sim_snapshot is None:
                out.append(
                    DispatchResult(
                        request=request,
                        applied=False,
                        error="missing_sim_snapshot",
                    )
                )
                continue

            if self._should_skip_request_for_existing_sign_trait(request, sim_snapshot):
                out.append(
                    DispatchResult(
                        request=request,
                        applied=True,
                        error=None,
                    )
                )
                continue

            action_type = str(getattr(request, "action_type", "")).strip().upper()
            try:
                if action_type == ACTION_RUN_LOOT:
                    applied = self._run_loot(getattr(request, "tuning_id", None), sim_snapshot)
                elif action_type == ACTION_RUN_WEIGHTED_LOOT_TABLE:
                    applied = self._run_weighted_loot_table(
                        getattr(request, "tuning_id", None),
                        getattr(request, "weights", {}),
                        sim_snapshot,
                    )
                elif action_type == ACTION_SET_COMMODITY:
                    applied = self._set_commodity(
                        getattr(request, "tuning_id", None),
                        getattr(request, "commodity_value", None),
                        sim_snapshot,
                    )
                else:
                    applied = False

                out.append(
                    DispatchResult(
                        request=request,
                        applied=bool(applied),
                        error=None if applied else "not_applied",
                    )
                )
            except Exception as exc:
                out.append(
                    DispatchResult(
                        request=request,
                        applied=False,
                        error=str(exc),
                    )
                )
        return out


class Big3SavePort(object):
    """In-memory save stub; replace with TS4 save extension bridge."""

    def __init__(self, *, load_fn=None, save_fn=None):
        self._payload = None
        self._load_fn = load_fn
        self._save_fn = save_fn

    def load_state(self):
        if callable(self._load_fn):
            try:
                payload = self._load_fn()
                if isinstance(payload, Mapping):
                    return payload
            except Exception:
                return None
        return self._payload

    def save_state(self, payload):
        if callable(self._save_fn):
            try:
                self._save_fn(payload)
            except Exception:
                pass
        self._payload = dict(payload) if isinstance(payload, Mapping) else None
