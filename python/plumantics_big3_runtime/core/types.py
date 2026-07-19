"""Shared datatypes for AstroCore runtime."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


SIGNS = (
    "Aries",
    "Taurus",
    "Gemini",
    "Cancer",
    "Leo",
    "Virgo",
    "Libra",
    "Scorpio",
    "Sagittarius",
    "Capricorn",
    "Aquarius",
    "Pisces",
)

ACTION_RUN_LOOT = "RUN_LOOT"
ACTION_RUN_WEIGHTED_LOOT_TABLE = "RUN_WEIGHTED_LOOT_TABLE"
ACTION_SET_COMMODITY = "SET_COMMODITY"

EDGE_ENTER = "enter"
EDGE_EXIT = "exit"


@dataclass
class AstroClock:
    total_days_elapsed: int
    total_segments_elapsed: int
    lunar_cycle_days: float = 8.0
    sim_days_per_year: float = 28.0


@dataclass
class SkySnapshot:
    sim_day: int
    sim_segment: int
    sun_sign: str
    moon_sign: str
    season_name: Optional[str] = None
    season_segment: Optional[str] = None


@dataclass
class SimSnapshot:
    sim_id: int
    full_name: str = ""
    trait_ids: List[int] = field(default_factory=list)
    household_id: Optional[int] = None
    sim_info: Any = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SignalState:
    key: str
    intensity: float = 1.0
    scope: str = "sim"
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ActionRequest:
    action_type: str
    target_sim_id: int
    signal_key: str
    edge: str
    tuning_id: Optional[int] = None
    commodity_value: Optional[float] = None
    weights: Dict[str, float] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DispatchResult:
    request: ActionRequest
    applied: bool
    error: Optional[str] = None


@dataclass
class TickReport:
    sim_day: int
    sim_segment: int
    reason: str
    sky: SkySnapshot
    sim_count: int = 0
    active_signal_count: int = 0
    entered_signal_count: int = 0
    exited_signal_count: int = 0
    action_count: int = 0
    applied_action_count: int = 0
    failed_action_count: int = 0
    emitted_event_keys: List[str] = field(default_factory=list)
