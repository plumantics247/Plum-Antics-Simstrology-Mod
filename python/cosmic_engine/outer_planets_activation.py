"""Installed-package detection for the optional outer-planets transit add-on."""

from __future__ import annotations

from typing import Optional


OUTER_PLANETS_ADDON_MARKER_NAME = "PlumAntics_CosmicEngine_OuterPlanetsActivationMarker"
OUTER_PLANETS_ADDON_MARKER_ID = 830000000000009201

_activation_override: Optional[bool] = None


def set_outer_planets_activation_override(value: Optional[bool]) -> None:
    global _activation_override
    _activation_override = None if value is None else bool(value)


def clear_outer_planets_activation_override() -> None:
    set_outer_planets_activation_override(None)


def is_outer_planets_addon_active(*, snippet_manager=None) -> bool:
    if _activation_override is not None:
        return bool(_activation_override)

    manager = snippet_manager
    if manager is None:
        try:
            import services  # type: ignore
            import sims4.resources  # type: ignore

            manager = services.get_instance_manager(sims4.resources.Types.SNIPPET)
        except Exception:
            manager = None

    if manager is None:
        return False

    try:
        return manager.get(OUTER_PLANETS_ADDON_MARKER_ID) is not None
    except Exception:
        return False
