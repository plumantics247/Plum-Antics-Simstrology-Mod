from __future__ import annotations

from astrocore.domains.childhood_handoff import build_childhood_age_transition_handler
from astrocore.domains.compatibility_seed import (
    build_household_compatibility_handler,
    build_sim_age_transition_compatibility_handler,
)
from astrocore.domains.household_onboarding import build_household_onboarding_handler
from astrocore.domains.sky_effects import (
    build_retrograde_tick_handler,
    build_solar_boost_tick_handler,
    build_solar_return_tick_handler,
    build_visible_sign_tick_handler,
)
from astrocore.engine.addon_registry import AddonRegistry
from astrocore.engine.addon_registry import AddonDeclaration
from astrocore.engine.lifecycle_engine import LifecycleEngine
from astrocore.engine.lifecycle_types import (
    EVENT_HOUSEHOLD_ONBOARD_REQUESTED,
    EVENT_PERIODIC_REPAIR,
    EVENT_SAVE_LOADED,
    EVENT_SIM_AGE_TRANSITION,
    EVENT_ZONE_LOADED,
    LifecycleContext,
    LifecycleEvent,
)
from astrocore.engine.state_store import EngineStateStore


def _lookup_sim_info(sim_id):
    try:
        import services  # type: ignore
    except Exception:
        return None

    try:
        manager = services.sim_info_manager()
    except Exception:
        manager = None
    if manager is None:
        return None

    try:
        return manager.get(int(sim_id or 0))
    except Exception:
        return None


def _repair_childhood_teen_handoff(sim_info):
    try:
        from cosmic_engine.first_load_chooser import repair_childhood_teen_handoff_for_lifecycle
    except Exception:
        return {"ok": False, "reason": "repair_import_failed"}
    return repair_childhood_teen_handoff_for_lifecycle(sim_info)


def _onboard_active_household_natal_snapshots(
    active_household_id, refresh_marker_cache=False, teen_sign_seed_mode="current_sky"
):
    try:
        from cosmic_engine.natal_snapshot_markers import onboard_active_household_natal_snapshots_for_lifecycle
    except Exception:
        return {"ok": False, "reason": "onboard_import_failed"}
    return onboard_active_household_natal_snapshots_for_lifecycle(
        active_household_id=active_household_id,
        refresh_marker_cache=bool(refresh_marker_cache),
        teen_sign_seed_mode=str(teen_sign_seed_mode or "current_sky"),
    )


def _process_managed_visible_sign_buffs():
    try:
        from cosmic_engine.natal_snapshot_markers import process_managed_visible_sign_buffs
    except Exception:
        return {"ok": False, "reason": "visible_sign_import_failed"}
    return process_managed_visible_sign_buffs()


def _sync_zone_solar_return_markers(*, show_notifications=True):
    try:
        from cosmic_engine.solar_return_markers import sync_zone_solar_return_markers
    except Exception:
        return {"ok": False, "reason": "solar_return_import_failed"}
    return sync_zone_solar_return_markers(show_notifications=bool(show_notifications))


def _sync_zone_solar_boosts():
    try:
        from astrocore.domains.solar_boosts import sync_zone_solar_boosts
    except Exception:
        return {"ok": False, "reason": "solar_boost_import_failed"}
    return sync_zone_solar_boosts()


def _sync_zone_retrograde_markers():
    try:
        from cosmic_engine.retrograde_markers import sync_zone_retrograde_markers
    except Exception:
        return {"ok": False, "reason": "retrograde_import_failed"}
    return sync_zone_retrograde_markers(manage_consequences=False)


def _ensure_zone_retrograde_consequences(*, reason="runtime.periodic"):
    try:
        from cosmic_engine.retrograde_markers import ensure_zone_retrograde_consequences
    except Exception:
        return {"ok": False, "reason": "retrograde_import_failed"}
    return ensure_zone_retrograde_consequences(reason=str(reason or "runtime.periodic"))


class _NoopDispatcher(object):
    def apply(self, operation):
        return {"ok": True, "kind": operation.kind, "sim_id": operation.sim_id}


class AstroCoreRuntimeBridge(object):
    def __init__(self, engine=None):
        self._registry = AddonRegistry()
        self._state_store = EngineStateStore()
        self._last_addon_summaries = {}
        self._engine = engine or LifecycleEngine(
            registry=self._registry,
            state_store=self._state_store,
            dispatcher=_NoopDispatcher(),
        )
        self._registry.register(
            AddonDeclaration(
                name="childhood",
                lifecycle_events=(EVENT_SIM_AGE_TRANSITION,),
                handler=self._capture_handler_summary(
                    "childhood",
                    build_childhood_age_transition_handler(
                        repair_fn=_repair_childhood_teen_handoff,
                        lookup_sim_info=_lookup_sim_info,
                    ),
                ),
            )
        )
        self._registry.register(
            AddonDeclaration(
                name="core_onboarding",
                lifecycle_events=(EVENT_HOUSEHOLD_ONBOARD_REQUESTED,),
                handler=self._capture_handler_summary(
                    "core_onboarding",
                    build_household_onboarding_handler(
                        onboard_fn=_onboard_active_household_natal_snapshots,
                    ),
                ),
            )
        )
        self._registry.register(
            AddonDeclaration(
                name="compatibility_household",
                lifecycle_events=(EVENT_HOUSEHOLD_ONBOARD_REQUESTED, EVENT_PERIODIC_REPAIR),
                handler=self._capture_handler_summary(
                    "compatibility_household",
                    build_household_compatibility_handler(
                        seed_household_fn=_sync_active_household_sign_compatibility_preferences,
                    ),
                ),
            )
        )
        self._registry.register(
            AddonDeclaration(
                name="compatibility_age_transition",
                lifecycle_events=(EVENT_SIM_AGE_TRANSITION,),
                handler=self._capture_handler_summary(
                    "compatibility_age_transition",
                    build_sim_age_transition_compatibility_handler(
                        sync_sim_fn=_sync_sign_compatibility_preferences_for_lifecycle_sim,
                    ),
                ),
            )
        )
        self._registry.register(
            AddonDeclaration(
                name="sky_visible_sign_buffs",
                lifecycle_events=(EVENT_PERIODIC_REPAIR,),
                handler=self._capture_handler_summary(
                    "sky_visible_sign_buffs",
                    build_visible_sign_tick_handler(
                        sync_visible_signs_fn=_process_managed_visible_sign_buffs,
                    ),
                ),
            )
        )
        self._registry.register(
            AddonDeclaration(
                name="sky_solar_boosts",
                lifecycle_events=(EVENT_PERIODIC_REPAIR,),
                handler=self._capture_handler_summary(
                    "sky_solar_boosts",
                    build_solar_boost_tick_handler(
                        sync_solar_boosts_fn=_sync_zone_solar_boosts,
                    ),
                ),
            )
        )
        self._registry.register(
            AddonDeclaration(
                name="sky_solar_return",
                lifecycle_events=(EVENT_PERIODIC_REPAIR,),
                handler=self._capture_handler_summary(
                    "sky_solar_return",
                    build_solar_return_tick_handler(
                        sync_solar_return_fn=_sync_zone_solar_return_markers,
                    ),
                ),
            )
        )
        self._registry.register(
            AddonDeclaration(
                name="sky_retrograde",
                lifecycle_events=(EVENT_PERIODIC_REPAIR,),
                handler=self._capture_handler_summary(
                    "sky_retrograde",
                    build_retrograde_tick_handler(
                        sync_markers_fn=_sync_zone_retrograde_markers,
                        sync_consequences_fn=_ensure_zone_retrograde_consequences,
                    ),
                ),
            )
        )

    def _capture_handler_summary(self, addon_name, handler):
        def _wrapped(context):
            result = handler(context) or {}
            summary = result.get("summary")
            self._last_addon_summaries[str(addon_name)] = (
                dict(summary) if isinstance(summary, dict) else {}
            )
            return result

        return _wrapped

    def _dispatch_with_summary_capture(self, event, context):
        self._last_addon_summaries = {}
        report = self._engine.dispatch_event(event, context)
        out = dict(report or {})
        out["addon_summaries"] = dict(self._last_addon_summaries)
        return out

    def on_zone_or_save_load(self, *, saved_record=None, fallback_seed=None):
        return self._dispatch_with_summary_capture(
            LifecycleEvent(
                name=EVENT_SAVE_LOADED if saved_record else EVENT_ZONE_LOADED,
                reason="runtime.load",
            ),
            LifecycleContext(active_mode="cosmic", metadata={"fallback_seed": fallback_seed or 0}),
        )

    def on_clock_snapshot(self, *, total_days_elapsed, total_segments_elapsed, trigger_periodic_repair=False):
        if not bool(trigger_periodic_repair):
            return {"ok": True, "event_name": "clock_snapshot_skipped"}
        return self._dispatch_with_summary_capture(
            LifecycleEvent(
                name=EVENT_PERIODIC_REPAIR,
                reason="runtime.periodic",
            ),
            LifecycleContext(
                active_mode="cosmic",
                metadata={
                    "total_days_elapsed": int(total_days_elapsed),
                    "total_segments_elapsed": int(total_segments_elapsed),
                },
            ),
        )

    def dispatch_runtime_tick(
        self,
        *,
        total_days_elapsed,
        total_segments_elapsed,
        movement_trigger=False,
        count_trigger=False,
        periodic_trigger=False,
        active_mode="cosmic",
        shared_runtime_enabled=False,
        retrogrades_enabled=False,
    ):
        if not bool(movement_trigger or count_trigger or periodic_trigger):
            return {"ok": True, "event_name": "runtime_tick_skipped", "addon_summaries": {}}

        return self._dispatch_with_summary_capture(
            LifecycleEvent(
                name=EVENT_PERIODIC_REPAIR,
                reason="runtime.clock_tick",
            ),
            LifecycleContext(
                active_mode=str(active_mode or "cosmic"),
                metadata={
                    "total_days_elapsed": int(total_days_elapsed or 0),
                    "total_segments_elapsed": int(total_segments_elapsed or 0),
                    "movement_trigger": bool(movement_trigger),
                    "count_trigger": bool(count_trigger),
                    "periodic_trigger": bool(periodic_trigger),
                    "shared_runtime_enabled": bool(shared_runtime_enabled),
                    "retrogrades_enabled": bool(retrogrades_enabled),
                    "show_notifications": True,
                    "reason": "runtime.clock_tick",
                },
            ),
        )

    def dispatch_household_onboard(
        self,
        household_id,
        *,
        refresh_marker_cache=False,
        teen_sign_seed_mode="current_sky",
    ):
        return self._dispatch_with_summary_capture(
            LifecycleEvent(
                name=EVENT_HOUSEHOLD_ONBOARD_REQUESTED,
                household_id=int(household_id or 0),
                reason="runtime.household_onboard",
            ),
            LifecycleContext(
                active_mode="cosmic",
                metadata={
                    "household_id": int(household_id or 0),
                    "refresh_marker_cache": bool(refresh_marker_cache),
                    "teen_sign_seed_mode": str(teen_sign_seed_mode or "current_sky"),
                    "reason": "runtime.household_onboard",
                },
            ),
        )


def _sync_active_household_sign_compatibility_preferences(reason):
    try:
        from cosmic_engine.sign_compatibility_runtime_seed import (
            sync_active_household_sign_compatibility_preferences_for_lifecycle,
        )
    except Exception:
        return {"ok": False, "reason": "compatibility_import_failed"}
    return sync_active_household_sign_compatibility_preferences_for_lifecycle(
        reason=str(reason or "runtime.household_onboard"),
    )


def _sync_sign_compatibility_preferences_for_lifecycle_sim(sim_id, *, reason="runtime.age_transition"):
    try:
        from cosmic_engine.sign_compatibility_runtime_seed import (
            sync_sign_compatibility_preferences_for_lifecycle_sim,
        )
    except Exception:
        return {"ok": False, "reason": "compatibility_import_failed"}
    return sync_sign_compatibility_preferences_for_lifecycle_sim(
        int(sim_id or 0),
        reason=str(reason or "runtime.age_transition"),
    )
