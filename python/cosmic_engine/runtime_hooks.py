"""Optional runtime hooks for Sims 4 integration.

These are intentionally lightweight wrappers around CosmicTransitService.
Connect them to your script-mod bootstrap and save extension points.
"""

from __future__ import annotations

import json
from typing import Dict, Optional

from astrocore.integrations.ts4.runtime_bridge import AstroCoreRuntimeBridge

from .astrocore_bridge import (
    get_astrocore_tracking_state,
    reset_astrocore_runtime,
    set_astrocore_effect_dispatch_enabled,
    tick_astrocore_from_clock_snapshot,
)
from .first_load_chooser import (
    maybe_repair_active_household_progressed_sun_state,
    maybe_show_first_load_reminder,
    reset_first_load_chooser_state,
)
from .mode_lock import get_mode_lock, sync_mode_lock_traits
from .transit_service import CosmicTransitService, get_global_transit_service

_ASTROCORE_RUNTIME_BRIDGE = AstroCoreRuntimeBridge()


def on_zone_or_save_load(
    *,
    saved_record: Optional[Dict[str, object]] = None,
    fallback_seed: Optional[int] = None,
) -> CosmicTransitService:
    """Initialize or load transit state at zone/save load time."""
    # Ensure AstroCore edge-state does not leak across zone/load transitions.
    _ASTROCORE_RUNTIME_BRIDGE.on_zone_or_save_load(
        saved_record=saved_record,
        fallback_seed=fallback_seed,
    )
    reset_astrocore_runtime()
    reset_first_load_chooser_state(zone_token=fallback_seed)
    service = get_global_transit_service()
    if saved_record:
        service.load_from_record(saved_record)
    elif not service.has_initialized_state():
        service.initialize(seed=fallback_seed)
    else:
        # Ordinary zone travel should preserve the existing save-wide sky state
        # when no explicit persisted record is being loaded.
        pass
    sync_mode_lock_traits()
    return service


def on_pre_save() -> Dict[str, object]:
    """Collect record payload before save write."""
    return get_global_transit_service().build_anchor_save_record(include_mode_lock=True)


def dispatch_household_onboard(
    household_id: int,
    *,
    refresh_marker_cache: bool = False,
    teen_sign_seed_mode: str = "current_sky",
) -> Dict[str, object]:
    return _ASTROCORE_RUNTIME_BRIDGE.dispatch_household_onboard(
        household_id,
        refresh_marker_cache=bool(refresh_marker_cache),
        teen_sign_seed_mode=str(teen_sign_seed_mode or "current_sky"),
    )


def on_clock_snapshot(
    *,
    total_days_elapsed: int,
    total_day_progress_elapsed: Optional[float] = None,
    total_segments_elapsed: int,
    lunar_cycle_days: Optional[float] = None,
    sim_days_per_year: Optional[float] = None,
) -> Dict[str, int]:
    """Advance transits from absolute time counters."""
    _ASTROCORE_RUNTIME_BRIDGE.on_clock_snapshot(
        total_days_elapsed=total_days_elapsed,
        total_segments_elapsed=total_segments_elapsed,
        trigger_periodic_repair=bool(int(total_segments_elapsed or 0) % 8 == 0),
    )
    sync_mode_lock_traits()
    try:
        maybe_repair_active_household_progressed_sun_state()
    except Exception:
        pass
    try:
        # The generic startup welcome popup is retired from automatic runtime
        # flow because it has been confusing for some players. Keep only the
        # save-level first-load reminder here when a save still needs intake.
        maybe_show_first_load_reminder()
    except Exception:
        pass
    active_mode = get_mode_lock()
    moved = get_global_transit_service().advance_from_totals(
        total_days_elapsed=total_days_elapsed,
        total_day_progress_elapsed=total_day_progress_elapsed,
        total_segments_elapsed=total_segments_elapsed,
        lunar_cycle_days=lunar_cycle_days,
        sim_days_per_year=sim_days_per_year,
    )
    # AstroCore tick is additive; keep return payload shape unchanged.
    if active_mode == "cosmic":
        try:
            tick_astrocore_from_clock_snapshot(
                total_days_elapsed=total_days_elapsed,
                total_segments_elapsed=total_segments_elapsed,
                lunar_cycle_days=lunar_cycle_days,
                sim_days_per_year=sim_days_per_year,
                reason="cosmic.clock_snapshot",
            )
        except Exception:
            pass
    return moved


def debug_dump_state_json() -> str:
    service = get_global_transit_service()
    payload = service.build_save_record()
    return json.dumps(payload, sort_keys=True)


def set_astrocore_dispatch_effects(enabled: bool) -> None:
    """Toggle AstroCore effect dispatch (tracking remains active either way)."""
    set_astrocore_effect_dispatch_enabled(bool(enabled))


def astrocore_tracking_state() -> Dict[str, object]:
    """Return latest AstroCore tracking snapshot for debugging."""
    return get_astrocore_tracking_state()
