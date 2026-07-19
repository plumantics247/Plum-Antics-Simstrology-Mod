"""Default deterministic planner for shared SKY signals."""

from __future__ import annotations

from .types import AstroClock, SIGNS, SignalState, SimSnapshot, SkySnapshot


class DefaultPlanner(object):
    """Planner that emits sign-level sky signals only."""

    def _sun_sign(self, total_segments_elapsed):
        index = int(total_segments_elapsed) % 12
        return SIGNS[index]

    def _moon_sign(self, total_days_elapsed, lunar_cycle_days):
        cycle_days = float(lunar_cycle_days) if float(lunar_cycle_days) > 0 else 8.0
        signs_per_day = 12.0 / cycle_days
        index = int(float(total_days_elapsed) * signs_per_day) % 12
        return SIGNS[index]

    def build_sky_snapshot(self, clock):
        if not isinstance(clock, AstroClock):
            raise TypeError("clock must be AstroClock")
        return SkySnapshot(
            sim_day=int(clock.total_days_elapsed),
            sim_segment=int(clock.total_segments_elapsed),
            sun_sign=self._sun_sign(clock.total_segments_elapsed),
            moon_sign=self._moon_sign(clock.total_days_elapsed, clock.lunar_cycle_days),
            season_name=None,
            season_segment=None,
        )

    def desired_signals_for_sim(self, sim, sky):
        if not isinstance(sim, SimSnapshot):
            raise TypeError("sim must be SimSnapshot")
        if not isinstance(sky, SkySnapshot):
            raise TypeError("sky must be SkySnapshot")
        return [
            SignalState(key="SKY_SUN_SIGN_{0}".format(str(sky.sun_sign).upper())),
            SignalState(key="SKY_MOON_SIGN_{0}".format(str(sky.moon_sign).upper())),
        ]
