"""Installed-package detection for the optional crystal-resonance add-on."""

from __future__ import annotations

from typing import Optional


CRYSTAL_RESONANCE_ADDON_MARKER_NAME = "PlumAntics_CosmicEngine_CrystalResonanceActivationMarker"
CRYSTAL_RESONANCE_ADDON_MARKER_ID = 830000000000009231

_activation_override: Optional[bool] = None


def set_crystal_resonance_activation_override(value: Optional[bool]) -> None:
    global _activation_override
    _activation_override = None if value is None else bool(value)


def clear_crystal_resonance_activation_override() -> None:
    set_crystal_resonance_activation_override(None)


def is_crystal_resonance_addon_active(*, snippet_manager=None) -> bool:
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
        return manager.get(CRYSTAL_RESONANCE_ADDON_MARKER_ID) is not None
    except Exception:
        return False
