"""Core runtime for shared AstroCore signal evaluation."""

from __future__ import annotations

from typing import Dict, List, Mapping, Optional, Sequence, Set

from .ports import ClockPort, DispatchPort, MappingPort, PlannerPort, SavePort, SimPort
from .types import (
    ACTION_RUN_LOOT,
    ACTION_RUN_WEIGHTED_LOOT_TABLE,
    ACTION_SET_COMMODITY,
    EDGE_ENTER,
    EDGE_EXIT,
    ActionRequest,
    DispatchResult,
    TickReport,
)


class AstroCoreEngine(object):
    """Shared signal -> action runtime with adapter ports."""

    SAVE_RECORD_VERSION = 1
    SAVE_RECORD_KEY = "plumantics_astrocore_v1"

    def __init__(
        self,
        *,
        clock_port: ClockPort,
        sim_port: SimPort,
        planner_port: PlannerPort,
        mapping_port: MappingPort,
        dispatch_port: DispatchPort,
        save_port: Optional[SavePort] = None,
        logger=None,
    ):
        self._clock_port = clock_port
        self._sim_port = sim_port
        self._planner_port = planner_port
        self._mapping_port = mapping_port
        self._dispatch_port = dispatch_port
        self._save_port = save_port
        self._logger = logger
        self._active_signal_keys_by_sim: Dict[int, Set[str]] = {}
        self._last_clock_payload: Dict[str, int] = {}

    def _log_debug(self, message, *args):
        if self._logger is None:
            return
        try:
            self._logger.debug(message, *args)
        except Exception:
            pass

    def _safe_int(self, value, default=0):
        try:
            return int(value)
        except Exception:
            return int(default)

    def _build_action_request(self, action_def, sim_id, signal_key, edge):
        action_type = str(action_def.get("type", "")).strip().upper()
        if action_type not in (
            ACTION_RUN_LOOT,
            ACTION_RUN_WEIGHTED_LOOT_TABLE,
            ACTION_SET_COMMODITY,
        ):
            return None

        tuning_id = action_def.get("tuning_id")
        if tuning_id is not None:
            try:
                tuning_id = int(tuning_id)
            except Exception:
                return None

        weights = action_def.get("weights", {})
        if not isinstance(weights, dict):
            weights = {}

        commodity_value = action_def.get("value")
        if commodity_value is not None:
            try:
                commodity_value = float(commodity_value)
            except Exception:
                commodity_value = 0.0

        return ActionRequest(
            action_type=action_type,
            target_sim_id=int(sim_id),
            signal_key=str(signal_key),
            edge=str(edge),
            tuning_id=tuning_id,
            commodity_value=commodity_value,
            weights=dict(weights),
            metadata={},
        )

    def load(self):
        if self._save_port is None:
            return
        payload = self._save_port.load_state()
        self.load_from_payload(payload)

    def load_from_payload(self, payload):
        if not isinstance(payload, Mapping):
            return
        if self._safe_int(payload.get("version"), 0) != self.SAVE_RECORD_VERSION:
            return

        active = payload.get("active_signal_keys_by_sim")
        if isinstance(active, Mapping):
            restored: Dict[int, Set[str]] = {}
            for sim_id_key, signal_keys in active.items():
                sim_id = self._safe_int(sim_id_key, 0)
                if sim_id <= 0:
                    continue
                if not isinstance(signal_keys, Sequence):
                    continue
                restored[sim_id] = {str(k) for k in signal_keys if str(k)}
            self._active_signal_keys_by_sim = restored

        last_clock = payload.get("last_clock_payload")
        if isinstance(last_clock, Mapping):
            self._last_clock_payload = {
                "total_days_elapsed": self._safe_int(last_clock.get("total_days_elapsed"), 0),
                "total_segments_elapsed": self._safe_int(last_clock.get("total_segments_elapsed"), 0),
            }

    def build_save_payload(self):
        return {
            "version": self.SAVE_RECORD_VERSION,
            "key": self.SAVE_RECORD_KEY,
            "active_signal_keys_by_sim": {
                str(sim_id): sorted(list(keys))
                for sim_id, keys in self._active_signal_keys_by_sim.items()
            },
            "last_clock_payload": dict(self._last_clock_payload),
        }

    def save(self):
        if self._save_port is None:
            return
        self._save_port.save_state(self.build_save_payload())

    def tick(self, reason="manual"):
        clock = self._clock_port.current_clock()
        sky = self._planner_port.build_sky_snapshot(clock)
        sim_snapshots = list(self._sim_port.iter_sims())
        sim_lookup = {int(sim.sim_id): sim for sim in sim_snapshots}

        action_requests: List[ActionRequest] = []
        emitted_event_keys: List[str] = []
        entered_total = 0
        exited_total = 0
        active_total = 0

        for sim in sim_snapshots:
            sim_id = int(sim.sim_id)
            desired_signals = list(self._planner_port.desired_signals_for_sim(sim, sky))
            desired_keys = {str(signal.key) for signal in desired_signals if str(signal.key)}
            prev_keys = self._active_signal_keys_by_sim.get(sim_id, set())

            entered_keys = sorted(list(desired_keys - prev_keys))
            exited_keys = sorted(list(prev_keys - desired_keys))
            persisted_count = len(prev_keys & desired_keys)

            self._active_signal_keys_by_sim[sim_id] = desired_keys

            active_total += len(entered_keys) + persisted_count
            entered_total += len(entered_keys)
            exited_total += len(exited_keys)

            for edge, keys in ((EDGE_ENTER, entered_keys), (EDGE_EXIT, exited_keys)):
                for signal_key in keys:
                    action_defs = self._mapping_port.actions_for_signal(signal_key, edge)
                    for action_def in action_defs:
                        request = self._build_action_request(
                            action_def,
                            sim_id=sim_id,
                            signal_key=signal_key,
                            edge=edge,
                        )
                        if request is None:
                            continue
                        action_requests.append(request)

                    emitted_event_keys.append("{0}:{1}:{2}".format(sim_id, signal_key, edge))

        dispatch_results = list(self._dispatch_port.dispatch_requests(action_requests, sim_lookup))
        applied_count = 0
        failed_count = 0
        for result in dispatch_results:
            if isinstance(result, DispatchResult) and bool(result.applied):
                applied_count += 1
            else:
                failed_count += 1

        self._last_clock_payload = {
            "total_days_elapsed": int(clock.total_days_elapsed),
            "total_segments_elapsed": int(clock.total_segments_elapsed),
        }

        report = TickReport(
            sim_day=int(clock.total_days_elapsed),
            sim_segment=int(clock.total_segments_elapsed),
            reason=str(reason),
            sky=sky,
            sim_count=len(sim_snapshots),
            active_signal_count=active_total,
            entered_signal_count=entered_total,
            exited_signal_count=exited_total,
            action_count=len(action_requests),
            applied_action_count=applied_count,
            failed_action_count=failed_count,
            emitted_event_keys=emitted_event_keys,
        )
        self._log_debug(
            "AstroCore tick reason=%s day=%s segment=%s sims=%s actions=%s",
            report.reason,
            report.sim_day,
            report.sim_segment,
            report.sim_count,
            report.action_count,
        )
        return report
