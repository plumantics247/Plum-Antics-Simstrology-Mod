"""Adapter ports for AstroCore runtime integration."""

from __future__ import annotations

from typing import Iterable, Mapping, Optional, Sequence

try:
    from typing import Protocol
except Exception:
    # Sims 4 embeds a Python runtime where typing.Protocol may be unavailable.
    class Protocol(object):
        pass

from .types import ActionRequest, AstroClock, DispatchResult, SignalState, SimSnapshot, SkySnapshot


class ClockPort(Protocol):
    def current_clock(self) -> AstroClock:
        """Return current simulation clock snapshot."""


class SimPort(Protocol):
    def iter_sims(self) -> Iterable[SimSnapshot]:
        """Yield current sim snapshots for evaluation."""


class PlannerPort(Protocol):
    def build_sky_snapshot(self, clock: AstroClock) -> SkySnapshot:
        """Build deterministic sky snapshot for the current clock."""

    def desired_signals_for_sim(self, sim: SimSnapshot, sky: SkySnapshot) -> Sequence[SignalState]:
        """Return desired active signals for a sim at this sky snapshot."""


class MappingPort(Protocol):
    def actions_for_signal(self, signal_key: str, edge: str) -> Sequence[Mapping[str, object]]:
        """Map a signal key + edge to action definitions."""


class DispatchPort(Protocol):
    def dispatch_requests(
        self,
        action_requests: Sequence[ActionRequest],
        sim_lookup: Mapping[int, SimSnapshot],
    ) -> Sequence[DispatchResult]:
        """Execute action requests in game context."""


class SavePort(Protocol):
    def load_state(self) -> Optional[Mapping[str, object]]:
        """Load persisted AstroCore runtime state payload."""

    def save_state(self, payload: Mapping[str, object]) -> None:
        """Persist AstroCore runtime state payload."""
