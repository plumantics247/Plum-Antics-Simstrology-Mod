"""XML interaction shim for the Big 3 private runtime."""

import sims4.log

from interactions.base.immediate_interaction import ImmediateSuperInteraction


LOGGER = sims4.log.Logger("Big3RuntimeInteractions", default_owner="PlumAntics")


def _invoke_assign_big3_assignment(
    *,
    sun_mode="skip",
    moon_mode="skip",
    rising_mode="skip",
    overwrite_existing=False,
):
    try:
        from . import bridge
        from .mode_lock import set_mode_lock, sync_mode_lock_traits
    except Exception:
        LOGGER.exception("Failed importing plumantics_big3_runtime.integration.bridge for assignment interaction.")
        return False

    assign_fn = getattr(bridge, "big3_universe2_assign_big3_for_sim", None)
    if not callable(assign_fn):
        LOGGER.error("big3_universe2_assign_big3_for_sim is unavailable.")
        return False

    try:
        set_mode_lock("big3", source="big3.auto_interaction")
        sync_mode_lock_traits()
        return bool(
            assign_fn(
                sim_id=-1,
                sun_mode=sun_mode,
                moon_mode=moon_mode,
                rising_mode=rising_mode,
                overwrite_existing=1 if bool(overwrite_existing) else 0,
                _connection=None,
            )
        )
    except Exception:
        LOGGER.exception("Big 3 private runtime assignment command failed.")
        return False


class Big3UniverseAssignSunImmediate(ImmediateSuperInteraction):
    """Auto-assign only the Sun step through the Python runtime."""

    def _run_interaction_gen(self, timeline):
        del timeline
        ok = _invoke_assign_big3_assignment(
            sun_mode="auto",
            moon_mode="skip",
            rising_mode="skip",
            overwrite_existing=False,
        )
        if False:
            yield None
        return bool(ok)


class Big3UniverseAssignMoonImmediate(ImmediateSuperInteraction):
    """Auto-assign only the Moon step through the Python runtime."""

    def _run_interaction_gen(self, timeline):
        del timeline
        ok = _invoke_assign_big3_assignment(
            sun_mode="skip",
            moon_mode="random",
            rising_mode="skip",
            overwrite_existing=False,
        )
        if False:
            yield None
        return bool(ok)


class Big3UniverseAssignRisingImmediate(ImmediateSuperInteraction):
    """Auto-assign only the Rising step through the Python runtime."""

    def _run_interaction_gen(self, timeline):
        del timeline
        ok = _invoke_assign_big3_assignment(
            sun_mode="skip",
            moon_mode="skip",
            rising_mode="random",
            overwrite_existing=False,
        )
        if False:
            yield None
        return bool(ok)
