"""Cosmic Engine runtime scaffolding.

This package is safe to import outside Sims 4 for local math testing.
"""

from astrocore.integrations.ts4.runtime_bridge import AstroCoreRuntimeBridge

from .houses_notification_bridge import (
    build_houses_readout_payload,
    resolve_existing_houses_notification_loot_id,
    resolve_rising_sign_index_from_trait_ids,
)
from .bootstrap import register_debug_commands
from .chart_composition import (
    CLASSICAL_PLANETS,
    DEFAULT_DOMINANT_TIE_BEHAVIOR,
    SIGN_TO_ELEMENT,
    SIGN_TO_MODE,
    build_chart_composition,
    build_chart_composition_from_chart_payload,
    build_chart_composition_from_sign_indexes,
    build_chart_composition_for_sim,
    build_chart_composition_placeholders,
    calculate_element_totals,
    calculate_mode_totals,
    get_dominant_element,
    get_dominant_mode,
    get_legacy_single_element,
    get_legacy_single_mode,
    get_sign_element,
    get_sign_mode,
    rank_totals,
)
from .mode_lock import sync_mode_lock_traits
from .transit_core import (
    BODY_NAMES,
    HOUSES,
    SIGNS,
    TransitState,
)
from .loot_actions import CosmicEngineHousesPythonReadoutLoot
from .turbo_handoff_bridge import build_turbo_pair_state
from .save_adapter import CosmicTransitSaveAdapter
from .ts4_runtime_install import force_runtime_install_now, get_runtime_status_payload, install_runtime_hooks
from .transit_service import (
    CosmicTransitService,
    get_global_transit_service,
)
from .loot_actions import apply_chart_marker_traits

__all__ = [
    "BODY_NAMES",
    "CLASSICAL_PLANETS",
    "CosmicEngineHousesPythonReadoutLoot",
    "CosmicTransitService",
    "CosmicTransitSaveAdapter",
    "DEFAULT_DOMINANT_TIE_BEHAVIOR",
    "HOUSES",
    "SIGN_TO_ELEMENT",
    "SIGN_TO_MODE",
    "SIGNS",
    "TransitState",
    "AstroCoreRuntimeBridge",
    "apply_chart_marker_traits",
    "build_chart_composition",
    "build_chart_composition_from_chart_payload",
    "build_chart_composition_from_sign_indexes",
    "build_chart_composition_for_sim",
    "build_chart_composition_placeholders",
    "build_turbo_pair_state",
    "calculate_element_totals",
    "calculate_mode_totals",
    "build_houses_readout_payload",
    "force_runtime_install_now",
    "get_dominant_element",
    "get_dominant_mode",
    "get_global_transit_service",
    "get_legacy_single_element",
    "get_legacy_single_mode",
    "get_sign_element",
    "get_sign_mode",
    "get_runtime_status_payload",
    "install_runtime_hooks",
    "rank_totals",
    "register_debug_commands",
    "resolve_existing_houses_notification_loot_id",
    "resolve_rising_sign_index_from_trait_ids",
]

try:
    sync_mode_lock_traits()
except Exception:
    pass

try:
    register_debug_commands()
except Exception:
    pass

try:
    install_runtime_hooks()
except Exception:
    pass
