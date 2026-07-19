"""Optional AstroCore runtime bridge for Cosmic Engine."""

from __future__ import annotations

from typing import Dict, Optional

try:
    import services
    import sims4.resources
except Exception:
    services = None
    sims4 = None

try:
    from astro_core import AstroCoreEngine
    from astro_core.default_planner import DefaultPlanner
    from astro_core.types import ACTION_RUN_LOOT, AstroClock, DispatchResult, SimSnapshot
except Exception:
    AstroCoreEngine = None
    DefaultPlanner = None
    ACTION_RUN_LOOT = "RUN_LOOT"
    AstroClock = object
    DispatchResult = object
    SimSnapshot = object


_SUN_SIGNAL_ENTER_LOOT_BY_SIGN = {
    "ARIES": 192171841209815432,
    "TAURUS": 17707174217928792237,
    "GEMINI": 17958989398970670616,
    "CANCER": 10194902896960109518,
    "LEO": 16581042247478139592,
    "VIRGO": 11957172383048204265,
    "LIBRA": 12415973077234662066,
    "SCORPIO": 18024840256216673827,
    "SAGITTARIUS": 13024403037246095827,
    "CAPRICORN": 6196478298964914156,
    "AQUARIUS": 13371995975595704036,
    "PISCES": 14246891689587746371,
}
_MOON_SIGNAL_ENTER_LOOT_BY_SIGN = {
    "ARIES": 2885964974555236002,
    "TAURUS": 3003712286796803582,
    "GEMINI": 9480138564068541597,
    "CANCER": 7504080553217514111,
    "LEO": 8314964128606121309,
    "VIRGO": 5208898474953838056,
    "LIBRA": 10849585444383478994,
    "SCORPIO": 13774953817282568628,
    "SAGITTARIUS": 8702763336847771593,
    "CAPRICORN": 12798090775780639447,
    "AQUARIUS": 2838930508061107633,
    "PISCES": 15421847288342121070,
}

# Existing Cosmic hidden sign-trait ids (plus legacy umbrella traits).
_COSMIC_SUN_SIGN_TRAIT_IDS = {
    16288319043707067282,  # Aquarius
    3932245235,  # Aries
    12091197855899330377,  # Cancer
    15465208666713751968,  # Capricorn
    10107303776473103836,  # Gemini
    14093019412093895405,  # Leo
    11215395001044549951,  # Libra
    15277227368229634790,  # Pisces
    11824469484379778247,  # Sagittarius
    14045417915393411558,  # Scorpio
    12556226773632840593,  # Taurus
    18095672257494000204,  # Virgo
    9347662265918957273,  # generic Sun trait
}
_COSMIC_MOON_SIGN_TRAIT_IDS = {
    10695278403245366863,  # Aquarius
    11650509921942411200,  # Aries
    10210395513972085902,  # Cancer
    15419029532620477613,  # Capricorn
    15098505637711985297,  # Gemini
    14380993687067909978,  # Leo
    10904194554514963844,  # Libra
    11195456322365565579,  # Pisces
    13888295933713094476,  # Sagittarius
    14531262052241215371,  # Scorpio
    15981172008232333206,  # Taurus
    15759714517750486241,  # Virgo
    17239223782097826302,  # generic Moon trait
}

_ASTROCORE_EFFECT_DISPATCH_ENABLED = False


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


def _coerce_bool(value, default_value=False):
    if isinstance(value, bool):
        return value
    if value is None:
        return bool(default_value)
    token = str(value).strip().lower()
    if token in ("1", "true", "t", "yes", "y", "on"):
        return True
    if token in ("0", "false", "f", "no", "n", "off"):
        return False
    return bool(default_value)


class CosmicClockPort(object):
    def __init__(self):
        self._clock = AstroClock(total_days_elapsed=0, total_segments_elapsed=0)

    def update(
        self,
        *,
        total_days_elapsed,
        total_segments_elapsed,
        lunar_cycle_days,
        sim_days_per_year,
    ):
        self._clock = AstroClock(
            total_days_elapsed=max(0, _safe_int(total_days_elapsed, 0)),
            total_segments_elapsed=max(0, _safe_int(total_segments_elapsed, 0)),
            lunar_cycle_days=max(1.0, _safe_float(lunar_cycle_days, 12.0)),
            sim_days_per_year=max(4.0, _safe_float(sim_days_per_year, 28.0)),
        )

    def current_clock(self):
        return self._clock


class CosmicSimPort(object):
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

    def iter_sims(self):
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

        out = []
        for sim_info in gen():
            if sim_info is None:
                continue
            sim_id = getattr(sim_info, "sim_id", None)
            if sim_id is None:
                sim_id = getattr(sim_info, "id", None)
            if sim_id is None:
                continue

            household = getattr(sim_info, "household", None)
            household_id = getattr(household, "id", None) if household is not None else None
            out.append(
                SimSnapshot(
                    sim_id=_safe_int(sim_id, 0),
                    full_name=self._full_name(sim_info),
                    trait_ids=self._collect_trait_ids(sim_info),
                    household_id=None if household_id is None else _safe_int(household_id, 0),
                    sim_info=sim_info,
                    metadata={},
                )
            )
        return out


class CosmicMappingPort(object):
    """Signal-edge mapping with optional effect dispatch."""

    def __init__(self, *, effect_dispatch_enabled=False):
        self._effect_dispatch_enabled = bool(effect_dispatch_enabled)

    def set_effect_dispatch_enabled(self, enabled):
        self._effect_dispatch_enabled = bool(enabled)

    def _signal_sign(self, key, prefix):
        token = str(key)
        if not token.startswith(prefix):
            return None
        return token[len(prefix) :].strip().upper()

    def _sign_action(self, key, edge):
        if str(edge).strip().lower() != "enter":
            return []

        sun_sign = self._signal_sign(key, "SKY_SUN_SIGN_")
        if sun_sign is not None:
            tuning_id = _SUN_SIGNAL_ENTER_LOOT_BY_SIGN.get(sun_sign)
            if tuning_id is None:
                return []
            return [{"type": ACTION_RUN_LOOT, "tuning_id": int(tuning_id)}]

        moon_sign = self._signal_sign(key, "SKY_MOON_SIGN_")
        if moon_sign is not None:
            tuning_id = _MOON_SIGNAL_ENTER_LOOT_BY_SIGN.get(moon_sign)
            if tuning_id is None:
                return []
            return [{"type": ACTION_RUN_LOOT, "tuning_id": int(tuning_id)}]

        return []

    def actions_for_signal(self, signal_key, edge):
        if not self._effect_dispatch_enabled:
            return []
        return self._sign_action(signal_key, edge)


class CosmicDispatchPort(object):
    def __init__(
        self,
        *,
        effect_dispatch_enabled=False,
        sun_sign_trait_ids=None,
        moon_sign_trait_ids=None,
        skip_existing_sign_traits=True,
    ):
        self._effect_dispatch_enabled = bool(effect_dispatch_enabled)
        self._sun_sign_trait_ids = self._normalize_trait_id_set(
            _COSMIC_SUN_SIGN_TRAIT_IDS if sun_sign_trait_ids is None else sun_sign_trait_ids
        )
        self._moon_sign_trait_ids = self._normalize_trait_id_set(
            _COSMIC_MOON_SIGN_TRAIT_IDS if moon_sign_trait_ids is None else moon_sign_trait_ids
        )
        self._skip_existing_sign_traits = bool(skip_existing_sign_traits)

    def set_effect_dispatch_enabled(self, enabled):
        self._effect_dispatch_enabled = bool(enabled)

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

    def dispatch_requests(self, action_requests, sim_lookup):
        out = []
        for request in action_requests:
            sim_snapshot = sim_lookup.get(_safe_int(getattr(request, "target_sim_id", 0), 0))
            if sim_snapshot is None:
                out.append(
                    DispatchResult(request=request, applied=False, error="missing_sim_snapshot")
                )
                continue

            if self._should_skip_request_for_existing_sign_trait(request, sim_snapshot):
                out.append(DispatchResult(request=request, applied=True, error=None))
                continue

            action_type = str(getattr(request, "action_type", "")).strip().upper()
            if action_type != ACTION_RUN_LOOT:
                out.append(DispatchResult(request=request, applied=False, error="unsupported_action"))
                continue

            if not self._effect_dispatch_enabled:
                out.append(DispatchResult(request=request, applied=False, error="effect_dispatch_disabled"))
                continue

            applied = self._run_loot(getattr(request, "tuning_id", None), sim_snapshot)
            out.append(DispatchResult(request=request, applied=bool(applied), error=None if applied else "not_applied"))
        return out


class CosmicAstroCoreRuntime(object):
    def __init__(self, *, effect_dispatch_enabled=False):
        self._clock_port = CosmicClockPort()
        self._sim_port = CosmicSimPort()
        self._mapping_port = CosmicMappingPort(effect_dispatch_enabled=bool(effect_dispatch_enabled))
        self._dispatch_port = CosmicDispatchPort(effect_dispatch_enabled=bool(effect_dispatch_enabled))
        self._planner = DefaultPlanner()
        self._engine = AstroCoreEngine(
            clock_port=self._clock_port,
            sim_port=self._sim_port,
            planner_port=self._planner,
            mapping_port=self._mapping_port,
            dispatch_port=self._dispatch_port,
            logger=None,
        )
        self._last_tick_report = None

    def set_effect_dispatch_enabled(self, enabled):
        self._mapping_port.set_effect_dispatch_enabled(enabled)
        self._dispatch_port.set_effect_dispatch_enabled(enabled)

    def tick_from_totals(
        self,
        *,
        total_days_elapsed,
        total_segments_elapsed,
        lunar_cycle_days=None,
        sim_days_per_year=None,
        reason="cosmic.clock_snapshot",
    ):
        self._clock_port.update(
            total_days_elapsed=total_days_elapsed,
            total_segments_elapsed=total_segments_elapsed,
            lunar_cycle_days=12.0 if lunar_cycle_days is None else lunar_cycle_days,
            sim_days_per_year=28.0 if sim_days_per_year is None else sim_days_per_year,
        )
        self._last_tick_report = self._engine.tick(reason=reason)
        return self._last_tick_report

    def last_tick_report(self):
        return self._last_tick_report

    def tracking_state(self):
        report = self._last_tick_report
        if report is None:
            return {
                "dispatch_effects_enabled": bool(self._dispatch_port._effect_dispatch_enabled),
                "has_report": False,
                "active_signal_keys_by_sim": {},
            }
        active_by_sim = {}
        for sim_id, keys in getattr(self._engine, "_active_signal_keys_by_sim", {}).items():
            active_by_sim[str(sim_id)] = sorted([str(key) for key in keys])
        return {
            "dispatch_effects_enabled": bool(self._dispatch_port._effect_dispatch_enabled),
            "has_report": True,
            "reason": str(getattr(report, "reason", "")),
            "sim_count": _safe_int(getattr(report, "sim_count", 0), 0),
            "active_signal_count": _safe_int(getattr(report, "active_signal_count", 0), 0),
            "entered_signal_count": _safe_int(getattr(report, "entered_signal_count", 0), 0),
            "exited_signal_count": _safe_int(getattr(report, "exited_signal_count", 0), 0),
            "action_count": _safe_int(getattr(report, "action_count", 0), 0),
            "applied_action_count": _safe_int(getattr(report, "applied_action_count", 0), 0),
            "failed_action_count": _safe_int(getattr(report, "failed_action_count", 0), 0),
            "emitted_event_keys": list(getattr(report, "emitted_event_keys", []) or []),
            "active_signal_keys_by_sim": active_by_sim,
        }


_RUNTIME: Optional[CosmicAstroCoreRuntime] = None


def astrocore_available():
    return AstroCoreEngine is not None and DefaultPlanner is not None


def reset_astrocore_runtime():
    global _RUNTIME
    _RUNTIME = None


def astrocore_effect_dispatch_enabled():
    return bool(_ASTROCORE_EFFECT_DISPATCH_ENABLED)


def set_astrocore_effect_dispatch_enabled(enabled):
    global _ASTROCORE_EFFECT_DISPATCH_ENABLED
    _ASTROCORE_EFFECT_DISPATCH_ENABLED = _coerce_bool(enabled, False)

    global _RUNTIME
    if _RUNTIME is not None:
        _RUNTIME.set_effect_dispatch_enabled(_ASTROCORE_EFFECT_DISPATCH_ENABLED)


def get_astrocore_tracking_state():
    if _RUNTIME is None:
        return {
            "dispatch_effects_enabled": bool(_ASTROCORE_EFFECT_DISPATCH_ENABLED),
            "has_report": False,
            "active_signal_keys_by_sim": {},
        }
    return _RUNTIME.tracking_state()


def tick_astrocore_from_clock_snapshot(
    *,
    total_days_elapsed,
    total_segments_elapsed,
    lunar_cycle_days=None,
    sim_days_per_year=None,
    reason="cosmic.clock_snapshot",
):
    if not astrocore_available():
        return None

    global _RUNTIME
    if _RUNTIME is None:
        _RUNTIME = CosmicAstroCoreRuntime(
            effect_dispatch_enabled=_ASTROCORE_EFFECT_DISPATCH_ENABLED,
        )

    return _RUNTIME.tick_from_totals(
        total_days_elapsed=total_days_elapsed,
        total_segments_elapsed=total_segments_elapsed,
        lunar_cycle_days=lunar_cycle_days,
        sim_days_per_year=sim_days_per_year,
        reason=reason,
    )
