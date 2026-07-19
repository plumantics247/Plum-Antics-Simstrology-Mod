from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional


EVENT_SAVE_LOADED = "save_loaded"
EVENT_ZONE_LOADED = "zone_loaded"
EVENT_HOUSEHOLD_ONBOARD_REQUESTED = "household_onboard_requested"
EVENT_SIM_CREATED = "sim_created"
EVENT_SIM_AGE_TRANSITION = "sim_age_transition"
EVENT_PERIODIC_REPAIR = "periodic_repair"


@dataclass(frozen=True)
class LifecycleEvent(object):
    name: str
    sim_id: Optional[int] = None
    household_id: Optional[int] = None
    age_from: str = ""
    age_to: str = ""
    reason: str = ""


@dataclass
class LifecycleContext(object):
    active_mode: str = ""
    metadata: Dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class OperationRequest(object):
    kind: str
    sim_id: int
    payload: Dict[str, object]
    source: str
