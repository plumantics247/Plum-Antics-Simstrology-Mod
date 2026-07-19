"""Runtime transit service scaffold.

This module avoids hard dependencies on Sims 4 imports so it can be tested
locally. In-game, wire this service to zone load/save callbacks and clock ticks.
"""

from __future__ import annotations

import logging
import random
from typing import Dict, Mapping, Optional

from .outer_planets_activation import is_outer_planets_addon_active
from .transit_core import (
    FREE_INITIAL_MARS_PLUS_BODIES,
    SIGN_TO_INDEX,
    RULE_BY_BODY,
    TETHERED_INITIAL_BODIES,
    TransitState,
    advance_transits,
    body_chart_for_sim,
    build_house_sign_map_for_rising,
    fnv1_32,
    OPTIONAL_OUTER_BODY_NAMES,
    random_initial_state,
    reseed_mars_plus_state,
    resolve_active_body_names,
    state_from_payload,
    state_to_payload,
)


log = logging.getLogger("cosmic_engine.transit_service")

_SUN_ENVELOPE_OFFSETS = (-1, 0, 1)
_SUN_ENVELOPE_TRANSITIONS = {
    "Mercury": {
        -1: ((-1, 1), (0, 5)),
        0: ((-1, 1), (0, 5), (1, 1)),
        1: ((0, 5), (1, 1)),
    },
    "Venus": {
        -1: ((-1, 3), (0, 1)),
        0: ((-1, 2), (0, 1), (1, 2)),
        1: ((0, 1), (1, 3)),
    },
}
_MARS_WEIGHTED_DISTANCE_BY_ABS_OFFSET = (
    # Mars is semi-independent: it can drift far beyond the inner-planet
    # envelope, but it still samples a Sun-relative distance profile rather
    # than moving as a completely random sky body.
    (0, 20),
    (1, 25),
    (2, 20),
    (3, 13),
    (4, 12),
    (6, 10),
)
_MARS_OFFSET_DIRECTION_PERSISTENCE = ((1, 7), (-1, 3))
_DEFAULT_LUNAR_CYCLE_DAYS = 12.0
_DEFAULT_SIM_DAYS_PER_YEAR = 28.0
_RETROGRADE_BODIES = ("Mercury", "Venus", "Mars", "Jupiter", "Saturn")
_RETROGRADE_EVENT_QUEUE_MAX = 128
_CHART_RECORD_SOURCES_TO_PRESERVE_ON_TRANSIT_RESEED = frozenset(
    ("stored_natal_markers", "player_authored_big3")
)
_RETROGRADE_SEGMENT_SPECS = {
    "Jupiter": {"start_interval": 9.0, "duration": 4.0},
    "Saturn": {"start_interval": 15.0, "duration": 5.0},
}


class CosmicTransitService:
    """Owns global transit state and exposes persistence-friendly hooks."""

    LEGACY_SAVE_RECORD_VERSION = 1
    SAVE_RECORD_VERSION = 3
    SAVE_RECORD_KEY = "plumantics_cosmic_engine_transits_v1"
    CHART_RECORDS_KEY = "chart_record_payload_by_sim_id"
    MODE_LOCK_KEY = "mode_lock_payload"

    def __init__(self) -> None:
        self._state: Optional[TransitState] = None
        self._seed: Optional[int] = None
        self._venus_sun_offset: int = 1
        self._mercury_sun_offset: int = 0
        self._last_total_days_seen: Optional[int] = None
        self._last_total_day_progress_seen: Optional[float] = None
        self._last_total_segments_seen: Optional[int] = None
        self._moon_sign_progress_fraction: float = 0.0
        self._lunar_cycle_days_hint: float = _DEFAULT_LUNAR_CYCLE_DAYS
        self._sim_days_per_year_hint: float = _DEFAULT_SIM_DAYS_PER_YEAR
        self._retrograde_state_by_body: Dict[str, Dict[str, object]] = {}
        self._last_retrograde_changes: Dict[str, Dict[str, int]] = {}
        self._pending_retrograde_events: list[Dict[str, object]] = []
        self._retrograde_event_seq: int = 0
        self._last_houses_readout_by_sim_id: Dict[int, Dict[str, object]] = {}
        self._chart_record_payload_by_sim_id: Dict[int, Dict[str, object]] = {}
        self._mode_lock_payload: Dict[str, object] = {}
        self._anchor_state_payload: Optional[Dict[str, Dict[str, int]]] = None
        self._anchor_total_days_elapsed: Optional[int] = None
        self._anchor_total_day_progress_elapsed: Optional[float] = None
        self._anchor_total_segments_elapsed: Optional[int] = None
        self._anchor_venus_sun_offset: int = 1
        self._anchor_mercury_sun_offset: int = 0
        self._anchor_moon_sign_progress_fraction: float = 0.0
        self._anchor_retrograde_state_by_body: Dict[str, Dict[str, object]] = {}

    def has_initialized_state(self) -> bool:
        """Return True once the service has meaningful in-memory state.

        This is used to avoid reinitializing the save-wide sky on ordinary
        zone transitions when no persisted record is being loaded.
        """
        return (
            self._state is not None
            or self._last_total_days_seen is not None
            or self._last_total_day_progress_seen is not None
            or self._last_total_segments_seen is not None
            or bool(self._retrograde_state_by_body)
        )

    @property
    def state(self) -> TransitState:
        if self._state is None:
            self._state = random_initial_state(seed=self._seed)
            self._venus_sun_offset = self._pick_default_offset_direction(salt=11)
            self._mercury_sun_offset = self._pick_default_sun_envelope_offset(salt=29)
            self._sync_sun_relative_bodies()
        return self._state

    def outer_planets_active(self) -> bool:
        return bool(is_outer_planets_addon_active())

    def active_body_names(self):
        return resolve_active_body_names(include_outer=self.outer_planets_active())

    def _pick_default_sun_envelope_offset(self, *, salt: int) -> int:
        """Return a deterministic per-save envelope offset in {-1, 0, +1}."""
        seed = self._seed
        if seed is None:
            return 0
        index = (abs(int(seed)) + int(salt)) % len(_SUN_ENVELOPE_OFFSETS)
        return _SUN_ENVELOPE_OFFSETS[index]

    def _pick_default_offset_direction(self, *, salt: int) -> int:
        seed = self._seed
        if seed is None:
            return 1
        return -1 if ((abs(int(seed)) + int(salt)) % 2 == 0) else 1

    def _normalize_sun_envelope_offset(self, value: object, *, salt: int) -> int:
        try:
            offset = int(value)
        except Exception:
            return self._pick_default_sun_envelope_offset(salt=salt)
        if offset < -1:
            return -1
        if offset > 1:
            return 1
        return offset

    def _infer_or_default_sun_envelope_offset(self, body_name: str, *, salt: int) -> int:
        try:
            sun_index = int(self.state.sign_index_by_body.get("Sun", 0)) % 12
            body_index = int(self.state.sign_index_by_body.get(body_name, 0)) % 12
        except Exception:
            return self._pick_default_sun_envelope_offset(salt=salt)

        diff = (body_index - sun_index) % 12
        if diff == 0:
            return 0
        if diff == 1:
            return 1
        if diff == 11:
            return -1
        return self._pick_default_sun_envelope_offset(salt=salt)

    def _advance_sun_envelope_offset(self, current_offset: int, *, direction: int, steps: int) -> int:
        if steps <= 0:
            return self._normalize_sun_envelope_offset(current_offset, salt=0)
        try:
            current_index = _SUN_ENVELOPE_OFFSETS.index(int(current_offset))
        except Exception:
            current_index = 1
        step_dir = -1 if int(direction) < 0 else 1
        for _ in range(int(steps)):
            current_index = (current_index + step_dir) % len(_SUN_ENVELOPE_OFFSETS)
        return _SUN_ENVELOPE_OFFSETS[current_index]

    def _weighted_sun_envelope_offset(
        self,
        body_name: str,
        current_offset: int,
        *,
        step_key: int,
    ) -> int:
        transitions = _SUN_ENVELOPE_TRANSITIONS.get(str(body_name))
        if not transitions:
            return self._normalize_sun_envelope_offset(current_offset, salt=0)
        choices = transitions.get(int(current_offset), transitions.get(0, ((0, 1),)))
        total_weight = sum(max(0, int(weight)) for _, weight in choices)
        if total_weight <= 0:
            return self._normalize_sun_envelope_offset(current_offset, salt=0)
        hash_input = "{0}|{1}|{2}|{3}".format(
            int(self._seed or 0),
            str(body_name),
            int(current_offset),
            int(step_key),
        )
        draw = fnv1_32(hash_input) % total_weight
        cursor = 0
        for next_offset, weight in choices:
            cursor += max(0, int(weight))
            if draw < cursor:
                return self._normalize_sun_envelope_offset(next_offset, salt=0)
        return self._normalize_sun_envelope_offset(current_offset, salt=0)

    def _advance_weighted_sun_envelope_offset(
        self,
        body_name: str,
        current_offset: int,
        *,
        steps: int,
        base_step_key: int,
    ) -> int:
        offset = self._normalize_sun_envelope_offset(current_offset, salt=0)
        for step_index in range(max(0, int(steps))):
            offset = self._weighted_sun_envelope_offset(
                body_name,
                offset,
                step_key=int(base_step_key) + int(step_index),
            )
        return offset

    def _weighted_choice(self, choices, *, hash_input: str):
        resolved_choices = tuple(choices or ())
        total_weight = sum(max(0, int(weight)) for _, weight in resolved_choices)
        if total_weight <= 0:
            return None
        draw = fnv1_32(str(hash_input)) % total_weight
        cursor = 0
        for value, weight in resolved_choices:
            cursor += max(0, int(weight))
            if draw < cursor:
                return value
        return resolved_choices[-1][0]

    def _signed_solar_offset(self, body_name: str, *, sun_index: Optional[int] = None) -> int:
        state = self.state
        body_index = int(state.sign_index_by_body.get(body_name, 0)) % 12
        if sun_index is None:
            sun_index = int(state.sign_index_by_body.get("Sun", 0)) % 12
        offset = (int(body_index) - int(sun_index)) % 12
        if offset > 6:
            offset -= 12
        return int(offset)

    def _pick_mars_weighted_offset(self, current_offset: int, *, step_key: int) -> int:
        abs_offset = self._weighted_choice(
            _MARS_WEIGHTED_DISTANCE_BY_ABS_OFFSET,
            hash_input="{0}|Mars|distance|{1}".format(int(self._seed or 0), int(step_key)),
        )
        if abs_offset is None:
            return 0
        abs_offset = int(abs(abs_offset))
        if abs_offset == 0 or abs_offset == 6:
            return abs_offset

        if int(current_offset) < 0:
            current_direction = -1
        elif int(current_offset) > 0:
            current_direction = 1
        else:
            current_direction = 0

        if current_direction == 0:
            direction = self._weighted_choice(
                ((-1, 1), (1, 1)),
                hash_input="{0}|Mars|direction|{1}".format(int(self._seed or 0), int(step_key)),
            )
        else:
            direction = self._weighted_choice(
                tuple(
                    (int(current_direction) * int(sign), int(weight))
                    for sign, weight in _MARS_OFFSET_DIRECTION_PERSISTENCE
                ),
                hash_input="{0}|Mars|persist|{1}|{2}".format(
                    int(self._seed or 0),
                    int(current_offset),
                    int(step_key),
                ),
            )
        return int(abs_offset) * int(direction or 1)

    def _set_mars_from_weighted_sun_distance(self, *, step_key: int) -> None:
        # Mars is keyed from the Sun sign at the actual segment step so save-gap
        # rebuilds and normal runtime ticks both resolve to the same placement.
        sun_index = max(0, int(step_key)) % 12
        current_offset = self._signed_solar_offset("Mars", sun_index=sun_index)
        next_offset = self._pick_mars_weighted_offset(current_offset, step_key=step_key)
        self.state.sign_index_by_body["Mars"] = (int(sun_index) + int(next_offset)) % 12

    def _advance_mars_dynamic(self, elapsed_segments: int) -> int:
        if elapsed_segments <= 0:
            return 0

        interval = max(1, int(RULE_BY_BODY["Mars"].interval))
        accum = int(self.state.segment_progress_by_body.get("Mars", 0)) + int(elapsed_segments)
        steps, rem = divmod(accum, interval)
        self.state.segment_progress_by_body["Mars"] = rem
        if steps <= 0:
            return 0

        base_step_key = int(self._last_total_segments_seen or 0)
        first_step_key = max(0, int(base_step_key) - int(steps) + 1)
        for step_offset in range(int(steps)):
            self._set_mars_from_weighted_sun_distance(
                step_key=int(first_step_key) + int(step_offset)
            )
        return int(steps)

    def _sync_sun_relative_bodies(self) -> None:
        state = self.state
        sun_index = int(state.sign_index_by_body.get("Sun", 0)) % 12
        state.sign_index_by_body["Venus"] = (sun_index + self._venus_sun_offset) % 12
        state.sign_index_by_body["Mercury"] = (sun_index + self._mercury_sun_offset) % 12
        state.segment_progress_by_body["Venus"] = 0
        # Mercury cadence is still driven by its day remainder in transit_core.

    def _normalize_sim_days_per_year(self, value: object) -> float:
        try:
            days = float(value)
        except Exception:
            return float(_DEFAULT_SIM_DAYS_PER_YEAR)
        if not (days > 0):
            return float(_DEFAULT_SIM_DAYS_PER_YEAR)
        if days < 4.0:
            return 4.0
        return float(days)

    def set_sim_days_per_year_hint(self, value: object) -> float:
        self._sim_days_per_year_hint = self._normalize_sim_days_per_year(value)
        return float(self._sim_days_per_year_hint)

    def get_sim_days_per_year_hint(self) -> float:
        return float(self._sim_days_per_year_hint)

    def _normalize_lunar_cycle_days(self, value: object) -> float:
        try:
            days = float(value)
        except Exception:
            return float(_DEFAULT_LUNAR_CYCLE_DAYS)
        if not (days > 0):
            return float(_DEFAULT_LUNAR_CYCLE_DAYS)
        # Keep pathological values from producing extreme multi-sign jumps.
        if days < 1.0:
            return 1.0
        return float(days)

    def _advance_moon_dynamic(self, elapsed_days: int, *, lunar_cycle_days: Optional[float]) -> int:
        if elapsed_days <= 0:
            return 0
        cycle_days = self._normalize_lunar_cycle_days(
            self._lunar_cycle_days_hint if lunar_cycle_days is None else lunar_cycle_days
        )
        self._lunar_cycle_days_hint = cycle_days

        signs_per_day = 12.0 / cycle_days
        accum = float(self._moon_sign_progress_fraction) + (float(elapsed_days) * signs_per_day)
        steps = int(accum)
        self._moon_sign_progress_fraction = float(accum - float(steps))

        state = self.state
        # Moon no longer uses fixed day remainders; keep legacy field neutral.
        state.day_progress_by_body["Moon"] = 0
        if steps > 0:
            state.sign_index_by_body["Moon"] = (int(state.sign_index_by_body.get("Moon", 0)) + int(steps)) % 12
        return int(steps)

    def get_moon_progress_fraction(self) -> float:
        return float(self._moon_sign_progress_fraction)

    def get_lunar_cycle_days_hint(self) -> float:
        return float(self._lunar_cycle_days_hint)

    def _retrograde_day_spec(self, body: str) -> Dict[str, float]:
        year_days = float(self._sim_days_per_year_hint)
        if body == "Mercury":
            starts_per_year = 3.5
            return {
                "unit": "day",
                "start_interval": max(year_days / starts_per_year, 0.25),
                "duration": max(year_days * (21.0 / 365.0), 0.25),
            }
        if body == "Venus":
            return {
                "unit": "day",
                "start_interval": max(year_days * 1.5, 0.25),
                "duration": max(year_days * (40.0 / 365.0), 0.25),
            }
        if body == "Mars":
            return {
                "unit": "day",
                "start_interval": max(year_days * 2.0, 0.25),
                "duration": max(year_days * (60.0 / 365.0), 0.25),
            }
        raise KeyError(body)

    def _retrograde_spec(self, body: str) -> Dict[str, float]:
        if body in _RETROGRADE_SEGMENT_SPECS:
            spec = _RETROGRADE_SEGMENT_SPECS[body]
            return {
                "unit": "segment",
                "start_interval": float(spec["start_interval"]),
                "duration": float(spec["duration"]),
            }
        return self._retrograde_day_spec(body)

    def _ensure_retrograde_state_initialized(self) -> None:
        if self._retrograde_state_by_body:
            return
        seed = int(self._seed or 0)
        rng = random.Random(seed ^ 0xCEB00D)
        out: Dict[str, Dict[str, object]] = {}
        for body in _RETROGRADE_BODIES:
            spec = self._retrograde_spec(body)
            start_interval = max(float(spec["start_interval"]), 0.25)
            duration = max(min(float(spec["duration"]), start_interval), 0.1)
            phase = rng.random() * start_interval
            if phase < duration:
                active = True
                remaining = max(duration - phase, 0.01)
            else:
                active = False
                remaining = max(start_interval - phase, 0.01)
            out[body] = {
                "unit": str(spec["unit"]),
                "active": bool(active),
                "remaining": float(remaining),
            }
        self._retrograde_state_by_body = out

    def _load_retrograde_state_from_record(self, payload: object) -> bool:
        if not isinstance(payload, Mapping):
            return False

        loaded: Dict[str, Dict[str, object]] = {}
        for body in _RETROGRADE_BODIES:
            raw_state = payload.get(body)
            if not isinstance(raw_state, Mapping):
                continue

            spec = self._retrograde_spec(body)
            unit = str(spec.get("unit", "day"))
            start_interval = max(float(spec.get("start_interval", 1.0)), 0.25)
            duration = max(min(float(spec.get("duration", 0.5)), start_interval), 0.1)
            inactive_gap = max(start_interval - duration, 0.01)

            active = bool(raw_state.get("active", False))
            try:
                remaining = float(raw_state.get("remaining", 0.0))
            except Exception:
                remaining = 0.0
            max_remaining = duration if active else inactive_gap
            if not (remaining > 0.0):
                remaining = max_remaining
            if remaining > max_remaining:
                remaining = max_remaining

            loaded[body] = {
                "unit": unit,
                "active": bool(active),
                "remaining": float(remaining),
            }

        self._retrograde_state_by_body = loaded
        self._ensure_retrograde_state_initialized()
        return True

    def _advance_one_retrograde(self, body: str, delta_units: float) -> Dict[str, int]:
        self._ensure_retrograde_state_initialized()
        if delta_units <= 0:
            return {"starts": 0, "ends": 0}

        state = self._retrograde_state_by_body.get(body)
        if not isinstance(state, dict):
            return {"starts": 0, "ends": 0}
        spec = self._retrograde_spec(body)
        start_interval = max(float(spec["start_interval"]), 0.25)
        duration = max(min(float(spec["duration"]), start_interval), 0.1)
        inactive_gap = max(start_interval - duration, 0.01)

        remaining_delta = float(delta_units)
        starts = 0
        ends = 0
        guard = 0
        while remaining_delta > 1e-9 and guard < 256:
            guard += 1
            current_remaining = max(float(state.get("remaining", 0.0)), 0.01)
            if remaining_delta < current_remaining:
                state["remaining"] = float(current_remaining - remaining_delta)
                remaining_delta = 0.0
                break

            remaining_delta -= current_remaining
            if bool(state.get("active")):
                state["active"] = False
                state["remaining"] = float(inactive_gap)
                ends += 1
            else:
                state["active"] = True
                state["remaining"] = float(duration)
                starts += 1

        return {"starts": int(starts), "ends": int(ends)}

    def _advance_retrogrades(
        self,
        *,
        elapsed_day_progress: float,
        elapsed_segments: int,
    ) -> Dict[str, Dict[str, int]]:
        self._ensure_retrograde_state_initialized()
        changes: Dict[str, Dict[str, int]] = {}
        if elapsed_day_progress > 0:
            for body in ("Mercury", "Venus", "Mars"):
                result = self._advance_one_retrograde(body, float(elapsed_day_progress))
                if result["starts"] or result["ends"]:
                    changes[body] = result
        if elapsed_segments > 0:
            for body in ("Jupiter", "Saturn"):
                result = self._advance_one_retrograde(body, float(elapsed_segments))
                if result["starts"] or result["ends"]:
                    changes[body] = result
        return changes

    def _record_retrograde_changes(
        self,
        changes: Mapping[str, Mapping[str, int]],
        *,
        elapsed_days: int,
        elapsed_day_progress: float,
        elapsed_segments: int,
        source: str,
    ) -> None:
        normalized: Dict[str, Dict[str, int]] = {}
        for body, row in (changes or {}).items():
            try:
                starts = max(0, int(row.get("starts", 0)))
                ends = max(0, int(row.get("ends", 0)))
            except Exception:
                continue
            if starts <= 0 and ends <= 0:
                continue
            normalized[str(body)] = {"starts": starts, "ends": ends}

            state = self._retrograde_state_by_body.get(str(body), {})
            active_after = bool((state or {}).get("active", False))
            unit = str(((state or {}).get("unit")) or self._retrograde_spec(str(body)).get("unit", "day"))

            if starts > 0:
                self._retrograde_event_seq += 1
                self._pending_retrograde_events.append(
                    {
                        "id": int(self._retrograde_event_seq),
                        "body": str(body),
                        "event": "start",
                        "count": int(starts),
                        "unit": unit,
                        "active_after": bool(active_after),
                        "elapsed_days": int(elapsed_days),
                        "elapsed_day_progress": float(elapsed_day_progress),
                        "elapsed_segments": int(elapsed_segments),
                        "source": str(source),
                    }
                )
            if ends > 0:
                self._retrograde_event_seq += 1
                self._pending_retrograde_events.append(
                    {
                        "id": int(self._retrograde_event_seq),
                        "body": str(body),
                        "event": "end",
                        "count": int(ends),
                        "unit": unit,
                        "active_after": bool(active_after),
                        "elapsed_days": int(elapsed_days),
                        "elapsed_day_progress": float(elapsed_day_progress),
                        "elapsed_segments": int(elapsed_segments),
                        "source": str(source),
                    }
                )

            if len(self._pending_retrograde_events) > _RETROGRADE_EVENT_QUEUE_MAX:
                self._pending_retrograde_events = self._pending_retrograde_events[-_RETROGRADE_EVENT_QUEUE_MAX:]

        self._last_retrograde_changes = normalized

    def get_last_retrograde_changes(self) -> Dict[str, Dict[str, int]]:
        return {
            str(body): {"starts": int(row.get("starts", 0)), "ends": int(row.get("ends", 0))}
            for body, row in self._last_retrograde_changes.items()
        }

    def peek_pending_retrograde_events(self, *, limit: Optional[int] = None) -> list[Dict[str, object]]:
        events = list(self._pending_retrograde_events)
        if limit is not None:
            try:
                lim = max(0, int(limit))
            except Exception:
                lim = 0
            if lim > 0:
                events = events[:lim]
        return [dict(event) for event in events]

    def consume_pending_retrograde_events(self, *, limit: Optional[int] = None) -> list[Dict[str, object]]:
        if limit is None:
            events = self._pending_retrograde_events
            self._pending_retrograde_events = []
            return [dict(event) for event in events]
        try:
            lim = max(0, int(limit))
        except Exception:
            lim = 0
        if lim <= 0:
            return []
        events = self._pending_retrograde_events[:lim]
        self._pending_retrograde_events = self._pending_retrograde_events[lim:]
        return [dict(event) for event in events]

    def consume_pending_retrograde_events_filtered(
        self,
        *,
        sources: Optional[object] = None,
        limit: Optional[int] = None,
    ) -> list[Dict[str, object]]:
        allowed_sources = None
        if sources is not None:
            if isinstance(sources, str):
                allowed_sources = {str(sources)}
            else:
                try:
                    allowed_sources = {str(item) for item in sources}
                except Exception:
                    allowed_sources = {str(sources)}

        try:
            lim = None if limit is None else max(0, int(limit))
        except Exception:
            lim = None

        kept: list[Dict[str, object]] = []
        consumed: list[Dict[str, object]] = []
        for event in self._pending_retrograde_events:
            source = str((event or {}).get("source", ""))
            source_match = allowed_sources is None or source in allowed_sources
            if source_match and (lim is None or len(consumed) < lim):
                consumed.append(dict(event))
            else:
                kept.append(event)
        self._pending_retrograde_events = kept
        return consumed

    def consume_pending_retrograde_events_by_ids(
        self,
        event_ids: Iterable[object],
    ) -> list[Dict[str, object]]:
        wanted = set()
        for event_id in tuple(event_ids or ()):
            try:
                wanted.add(int(event_id))
            except Exception:
                continue
        if not wanted:
            return []

        kept: list[Dict[str, object]] = []
        consumed: list[Dict[str, object]] = []
        for event in self._pending_retrograde_events:
            try:
                event_id = int((event or {}).get("id"))
            except Exception:
                event_id = None
            if event_id is not None and event_id in wanted:
                consumed.append(dict(event))
            else:
                kept.append(event)
        self._pending_retrograde_events = kept
        return consumed

    def retrograde_debug_payload(self) -> Dict[str, object]:
        self._ensure_retrograde_state_initialized()
        bodies: Dict[str, Dict[str, object]] = {}
        for body in _RETROGRADE_BODIES:
            state = dict(self._retrograde_state_by_body.get(body, {}))
            spec = self._retrograde_spec(body)
            bodies[body] = {
                "unit": str(spec.get("unit")),
                "active": bool(state.get("active", False)),
                "remaining": round(float(state.get("remaining", 0.0)), 4),
                "start_interval": round(float(spec.get("start_interval", 0.0)), 4),
                "duration": round(float(spec.get("duration", 0.0)), 4),
            }
        return {
            "sim_days_per_year_hint": float(self._sim_days_per_year_hint),
            "last_total_days_seen": (
                int(self._last_total_days_seen)
                if self._last_total_days_seen is not None
                else None
            ),
            "last_total_day_progress_seen": (
                round(float(self._last_total_day_progress_seen), 6)
                if self._last_total_day_progress_seen is not None
                else None
            ),
            "last_total_segments_seen": (
                int(self._last_total_segments_seen)
                if self._last_total_segments_seen is not None
                else None
            ),
            "pending_event_count": len(self._pending_retrograde_events),
            "last_changes": self.get_last_retrograde_changes(),
            "bodies": bodies,
        }

    def retrograde_active_by_body(self) -> Dict[str, bool]:
        self._ensure_retrograde_state_initialized()
        return {
            body: bool((self._retrograde_state_by_body.get(body) or {}).get("active", False))
            for body in _RETROGRADE_BODIES
        }

    def _advance_sun_relative_offsets(self, moved: Mapping[str, int]) -> None:
        venus_steps = max(0, int(moved.get("Venus", 0)))
        mercury_steps = max(0, int(moved.get("Mercury", 0)))
        mercury_base_key = int(self._last_total_days_seen or 0)
        venus_base_key = int(self._last_total_segments_seen or 0)

        if venus_steps:
            self._venus_sun_offset = self._advance_weighted_sun_envelope_offset(
                "Venus",
                self._venus_sun_offset,
                steps=venus_steps,
                base_step_key=max(0, venus_base_key - venus_steps + 1),
            )
        if mercury_steps:
            self._mercury_sun_offset = self._advance_weighted_sun_envelope_offset(
                "Mercury",
                self._mercury_sun_offset,
                steps=mercury_steps,
                base_step_key=max(0, mercury_base_key - mercury_steps + 1),
            )

    def _sync_segment_anchored_bodies(self, total_segments_elapsed: int) -> None:
        """Anchor Sun to season segment and sync Sun-envelope bodies."""
        state = self.state
        sun_index = max(0, int(total_segments_elapsed)) % 12
        state.sign_index_by_body["Sun"] = sun_index
        state.segment_progress_by_body["Sun"] = 0
        self._sync_sun_relative_bodies()

    def initialize(self, *, seed: Optional[int] = None) -> TransitState:
        """Initialize fresh randomized state for a new save/session."""
        self._seed = seed
        self._state = random_initial_state(seed=seed)
        self._venus_sun_offset = self._pick_default_sun_envelope_offset(salt=11)
        self._mercury_sun_offset = self._pick_default_sun_envelope_offset(salt=29)
        self._sync_sun_relative_bodies()
        self._last_total_days_seen = None
        self._last_total_day_progress_seen = None
        self._last_total_segments_seen = None
        self._moon_sign_progress_fraction = 0.0
        self._lunar_cycle_days_hint = float(_DEFAULT_LUNAR_CYCLE_DAYS)
        self._sim_days_per_year_hint = float(_DEFAULT_SIM_DAYS_PER_YEAR)
        self._retrograde_state_by_body = {}
        self._last_retrograde_changes = {}
        self._pending_retrograde_events = []
        self._retrograde_event_seq = 0
        self._last_houses_readout_by_sim_id = {}
        self._chart_record_payload_by_sim_id = {}
        self._mode_lock_payload = {}
        self._anchor_state_payload = None
        self._anchor_total_days_elapsed = None
        self._anchor_total_day_progress_elapsed = None
        self._anchor_total_segments_elapsed = None
        self._anchor_venus_sun_offset = self._venus_sun_offset
        self._anchor_mercury_sun_offset = self._mercury_sun_offset
        self._anchor_moon_sign_progress_fraction = 0.0
        self._anchor_retrograde_state_by_body = {}
        self._ensure_retrograde_state_initialized()
        return self._state

    def _capture_current_state_as_anchor(
        self,
        *,
        total_days_elapsed: Optional[object],
        total_day_progress_elapsed: Optional[object] = None,
        total_segments_elapsed: Optional[object],
    ) -> None:
        self._ensure_retrograde_state_initialized()
        self._anchor_state_payload = state_to_payload(self.state)
        self._anchor_total_days_elapsed = (
            max(0, int(total_days_elapsed)) if total_days_elapsed is not None else 0
        )
        if total_day_progress_elapsed is None:
            total_day_progress_elapsed = self._anchor_total_days_elapsed
        try:
            total_day_progress = float(total_day_progress_elapsed)
        except Exception:
            total_day_progress = float(self._anchor_total_days_elapsed or 0)
        self._anchor_total_day_progress_elapsed = max(
            float(self._anchor_total_days_elapsed or 0),
            float(total_day_progress),
        )
        self._anchor_total_segments_elapsed = (
            max(0, int(total_segments_elapsed)) if total_segments_elapsed is not None else 0
        )
        self._anchor_venus_sun_offset = int(self._venus_sun_offset)
        self._anchor_mercury_sun_offset = int(self._mercury_sun_offset)
        self._anchor_moon_sign_progress_fraction = float(self._moon_sign_progress_fraction)
        self._anchor_retrograde_state_by_body = {
            body: dict(self._retrograde_state_by_body.get(body, {}))
            for body in _RETROGRADE_BODIES
        }

    def _restore_anchor_from_record(self, record: Mapping[str, object]) -> bool:
        anchor_payload = record.get("anchor_state_payload")
        if not isinstance(anchor_payload, Mapping):
            return False

        self._state = state_from_payload(anchor_payload)
        self._seed = int(record.get("seed", 0)) if record.get("seed") is not None else None
        self._venus_sun_offset = self._normalize_sun_envelope_offset(
            record.get("anchor_venus_sun_offset"),
            salt=11,
        )
        self._mercury_sun_offset = self._normalize_sun_envelope_offset(
            record.get("anchor_mercury_sun_offset"),
            salt=29,
        )
        try:
            self._moon_sign_progress_fraction = float(
                record.get("anchor_moon_sign_progress_fraction", 0.0)
            )
        except Exception:
            self._moon_sign_progress_fraction = 0.0
        if not (0.0 <= self._moon_sign_progress_fraction < 1.0):
            self._moon_sign_progress_fraction = self._moon_sign_progress_fraction % 1.0

        self._lunar_cycle_days_hint = self._normalize_lunar_cycle_days(
            record.get("lunar_cycle_days_hint", _DEFAULT_LUNAR_CYCLE_DAYS)
        )
        self._sim_days_per_year_hint = self._normalize_sim_days_per_year(
            record.get("sim_days_per_year_hint", _DEFAULT_SIM_DAYS_PER_YEAR)
        )
        self._retrograde_state_by_body = {}
        self._load_retrograde_state_from_record(record.get("anchor_retrograde_state_by_body"))
        self._last_retrograde_changes = {}
        self._pending_retrograde_events = []
        self._retrograde_event_seq = 0
        self._anchor_state_payload = state_to_payload(self.state)
        self._anchor_total_days_elapsed = (
            max(0, int(record.get("anchor_total_days_elapsed")))
            if record.get("anchor_total_days_elapsed") is not None
            else 0
        )
        raw_anchor_day_progress = record.get(
            "anchor_total_day_progress_elapsed",
            record.get("last_total_day_progress_seen", self._anchor_total_days_elapsed),
        )
        try:
            self._anchor_total_day_progress_elapsed = float(raw_anchor_day_progress)
        except Exception:
            self._anchor_total_day_progress_elapsed = float(self._anchor_total_days_elapsed or 0)
        self._anchor_total_day_progress_elapsed = max(
            float(self._anchor_total_days_elapsed or 0),
            float(self._anchor_total_day_progress_elapsed),
        )
        self._anchor_total_segments_elapsed = (
            max(0, int(record.get("anchor_total_segments_elapsed")))
            if record.get("anchor_total_segments_elapsed") is not None
            else 0
        )
        self._anchor_venus_sun_offset = int(self._venus_sun_offset)
        self._anchor_mercury_sun_offset = int(self._mercury_sun_offset)
        self._anchor_moon_sign_progress_fraction = float(self._moon_sign_progress_fraction)
        self._anchor_retrograde_state_by_body = {
            body: dict(self._retrograde_state_by_body.get(body, {}))
            for body in _RETROGRADE_BODIES
        }
        self._last_total_days_seen = self._anchor_total_days_elapsed
        self._last_total_day_progress_seen = self._anchor_total_day_progress_elapsed
        self._last_total_segments_seen = self._anchor_total_segments_elapsed
        return True

    def _load_shared_saved_payload(self, record: Mapping[str, object]) -> None:
        self._chart_record_payload_by_sim_id = {}
        chart_payloads = record.get(self.CHART_RECORDS_KEY)
        if isinstance(chart_payloads, Mapping):
            for sim_id, payload in chart_payloads.items():
                if not isinstance(payload, Mapping):
                    continue
                try:
                    resolved_sim_id = int(sim_id)
                except Exception:
                    continue
                self._chart_record_payload_by_sim_id[resolved_sim_id] = dict(payload)

        self._mode_lock_payload = {}
        raw_mode_lock = record.get(self.MODE_LOCK_KEY)
        if isinstance(raw_mode_lock, Mapping):
            self._mode_lock_payload = dict(raw_mode_lock)

    def _rebuild_state_from_anchor(
        self,
        *,
        seed: Optional[int],
        total_days_elapsed: Optional[object],
        total_day_progress_elapsed: Optional[object],
        total_segments_elapsed: Optional[object],
        lunar_cycle_days: Optional[object],
        sim_days_per_year: Optional[object],
    ) -> TransitState:
        self.initialize(seed=seed)
        self._lunar_cycle_days_hint = self._normalize_lunar_cycle_days(lunar_cycle_days)
        self._sim_days_per_year_hint = self._normalize_sim_days_per_year(sim_days_per_year)

        anchor_days = int(total_days_elapsed) if total_days_elapsed is not None else 0
        if total_day_progress_elapsed is None:
            total_day_progress_elapsed = anchor_days
        try:
            anchor_day_progress = float(total_day_progress_elapsed)
        except Exception:
            anchor_day_progress = float(anchor_days)
        anchor_segments = int(total_segments_elapsed) if total_segments_elapsed is not None else 0
        anchor_days = max(0, anchor_days)
        anchor_day_progress = max(float(anchor_days), float(anchor_day_progress))
        anchor_segments = max(0, anchor_segments)

        if anchor_days > 0 or anchor_segments > 0:
            self.advance(
                elapsed_days=anchor_days,
                elapsed_day_progress=anchor_day_progress,
                elapsed_segments=anchor_segments,
                lunar_cycle_days=self._lunar_cycle_days_hint,
                sim_days_per_year=self._sim_days_per_year_hint,
                event_source="save_record_rebuild",
            )

        self._last_total_days_seen = anchor_days
        self._last_total_day_progress_seen = anchor_day_progress
        self._last_total_segments_seen = anchor_segments
        self._last_retrograde_changes = {}
        self._pending_retrograde_events = []
        self._retrograde_event_seq = 0
        self._sync_segment_anchored_bodies(anchor_segments)
        # Moon uses dynamic fractional progress, so the old integer remainder field
        # is no longer meaningful.
        self.state.day_progress_by_body["Moon"] = 0
        return self._state

    def _load_v1_record(self, record: Mapping[str, object]) -> TransitState:
        payload = record.get("state_payload")
        if not isinstance(payload, Mapping):
            return self.initialize(seed=self._seed)

        self._state = state_from_payload(payload)
        self._seed = int(record.get("seed", 0)) if record.get("seed") is not None else None
        if record.get("venus_sun_offset") is not None:
            self._venus_sun_offset = self._normalize_sun_envelope_offset(
                record.get("venus_sun_offset"),
                salt=11,
            )
        else:
            self._venus_sun_offset = self._infer_or_default_sun_envelope_offset(
                "Venus",
                salt=11,
            )
        if record.get("mercury_sun_offset") is not None:
            self._mercury_sun_offset = self._normalize_sun_envelope_offset(
                record.get("mercury_sun_offset"),
                salt=29,
            )
        else:
            self._mercury_sun_offset = self._infer_or_default_sun_envelope_offset(
                "Mercury",
                salt=29,
            )
        self._last_total_days_seen = (
            int(record["last_total_days_seen"])
            if record.get("last_total_days_seen") is not None
            else None
        )
        raw_last_day_progress = record.get(
            "last_total_day_progress_seen",
            self._last_total_days_seen,
        )
        try:
            self._last_total_day_progress_seen = float(raw_last_day_progress)
        except Exception:
            self._last_total_day_progress_seen = (
                float(self._last_total_days_seen)
                if self._last_total_days_seen is not None
                else None
            )
        if self._last_total_days_seen is not None and self._last_total_day_progress_seen is not None:
            self._last_total_day_progress_seen = max(
                float(self._last_total_days_seen),
                float(self._last_total_day_progress_seen),
            )
        self._last_total_segments_seen = (
            int(record["last_total_segments_seen"])
            if record.get("last_total_segments_seen") is not None
            else None
        )
        try:
            self._moon_sign_progress_fraction = float(record.get("moon_sign_progress_fraction", 0.0))
        except Exception:
            self._moon_sign_progress_fraction = 0.0
        if not (0.0 <= self._moon_sign_progress_fraction < 1.0):
            self._moon_sign_progress_fraction = self._moon_sign_progress_fraction % 1.0
        self._lunar_cycle_days_hint = self._normalize_lunar_cycle_days(
            record.get("lunar_cycle_days_hint", _DEFAULT_LUNAR_CYCLE_DAYS)
        )
        self._sim_days_per_year_hint = self._normalize_sim_days_per_year(
            record.get("sim_days_per_year_hint", _DEFAULT_SIM_DAYS_PER_YEAR)
        )
        self._retrograde_state_by_body = {}
        self._last_retrograde_changes = {}
        self._pending_retrograde_events = []
        self._retrograde_event_seq = 0
        self._last_houses_readout_by_sim_id = {}
        self._load_shared_saved_payload(record)
        self._load_retrograde_state_from_record(record.get("retrograde_state_by_body"))
        if self._last_total_segments_seen is not None:
            self._sync_segment_anchored_bodies(self._last_total_segments_seen)
        else:
            self._sync_sun_relative_bodies()
        self._capture_current_state_as_anchor(
            total_days_elapsed=self._last_total_days_seen,
            total_day_progress_elapsed=self._last_total_day_progress_seen,
            total_segments_elapsed=self._last_total_segments_seen,
        )
        # Moon uses dynamic fractional progress, so the old integer remainder field
        # is no longer meaningful.
        self.state.day_progress_by_body["Moon"] = 0
        return self._state

    def _load_v2_record(self, record: Mapping[str, object]) -> TransitState:
        return self._load_v3_record(record)

    def _load_v3_record(self, record: Mapping[str, object]) -> TransitState:
        self._last_houses_readout_by_sim_id = {}
        self._load_shared_saved_payload(record)
        restored = self._restore_anchor_from_record(record)
        if restored:
            state = self.state
        else:
            seed = int(record.get("seed", 0)) if record.get("seed") is not None else None
            anchor_days = record.get("anchor_total_days_elapsed", record.get("last_total_days_seen"))
            anchor_segments = record.get(
                "anchor_total_segments_elapsed",
                record.get("last_total_segments_seen"),
            )
            state = self._rebuild_state_from_anchor(
                seed=seed,
                total_days_elapsed=anchor_days,
                total_day_progress_elapsed=record.get(
                    "anchor_total_day_progress_elapsed",
                    record.get("last_total_day_progress_seen", anchor_days),
                ),
                total_segments_elapsed=anchor_segments,
                lunar_cycle_days=record.get("lunar_cycle_days_hint", _DEFAULT_LUNAR_CYCLE_DAYS),
                sim_days_per_year=record.get("sim_days_per_year_hint", _DEFAULT_SIM_DAYS_PER_YEAR),
            )

        current_days_raw = record.get("last_total_days_seen", self._last_total_days_seen)
        current_day_progress_raw = record.get(
            "last_total_day_progress_seen",
            current_days_raw,
        )
        current_segments_raw = record.get("last_total_segments_seen", self._last_total_segments_seen)
        current_days = (
            max(0, int(current_days_raw))
            if current_days_raw is not None
            else int(self._last_total_days_seen or 0)
        )
        try:
            current_day_progress = max(float(current_days), float(current_day_progress_raw))
        except Exception:
            current_day_progress = float(current_days)
        current_segments = (
            max(0, int(current_segments_raw))
            if current_segments_raw is not None
            else int(self._last_total_segments_seen or 0)
        )
        delta_days = max(0, current_days - int(self._last_total_days_seen or 0))
        delta_day_progress = max(
            0.0,
            float(current_day_progress) - float(self._last_total_day_progress_seen or self._last_total_days_seen or 0),
        )
        delta_segments = max(0, current_segments - int(self._last_total_segments_seen or 0))
        if delta_days > 0 or delta_segments > 0:
            self.advance(
                elapsed_days=delta_days,
                elapsed_day_progress=delta_day_progress,
                elapsed_segments=delta_segments,
                lunar_cycle_days=self._lunar_cycle_days_hint,
                sim_days_per_year=self._sim_days_per_year_hint,
                event_source="save_record_rebuild",
            )
        self._last_total_days_seen = current_days
        self._last_total_day_progress_seen = current_day_progress
        self._last_total_segments_seen = current_segments
        self._last_retrograde_changes = {}
        self._pending_retrograde_events = []
        self._retrograde_event_seq = 0
        self._sync_segment_anchored_bodies(current_segments)

        expected_snapshot_key = str(record.get("last_snapshot_key") or "").strip()
        if expected_snapshot_key:
            actual_snapshot_key = self.current_snapshot_key()
            if actual_snapshot_key != expected_snapshot_key:
                log.warning(
                    "Transit save snapshot mismatch on load: expected=%s actual=%s",
                    expected_snapshot_key,
                    actual_snapshot_key,
                )

        expected_retrograde_flags = record.get("retrograde_active_by_body")
        if isinstance(expected_retrograde_flags, Mapping):
            actual_retrograde_flags = self.retrograde_active_by_body()
            mismatched = []
            for body in _RETROGRADE_BODIES:
                expected = bool(expected_retrograde_flags.get(body, False))
                actual = bool(actual_retrograde_flags.get(body, False))
                if expected != actual:
                    mismatched.append(body)
            if mismatched:
                log.warning(
                    "Transit retrograde reconciliation mismatch on load for bodies=%s",
                    ",".join(sorted(mismatched)),
                )
        return state

    def current_snapshot_key(self) -> str:
        self._ensure_retrograde_state_initialized()
        state = self.state
        parts = [
            "days={0}".format(
                int(self._last_total_days_seen) if self._last_total_days_seen is not None else -1
            ),
            "day_progress={0:.6f}".format(
                float(self._last_total_day_progress_seen)
                if self._last_total_day_progress_seen is not None
                else -1.0
            ),
            "segments={0}".format(
                int(self._last_total_segments_seen)
                if self._last_total_segments_seen is not None
                else -1
            ),
            "lunar={0:.5f}".format(float(self._lunar_cycle_days_hint)),
            "year={0:.5f}".format(float(self._sim_days_per_year_hint)),
            "moon_fraction={0:.6f}".format(float(self._moon_sign_progress_fraction)),
            "seed={0}".format(int(self._seed) if self._seed is not None else -1),
        ]
        for body in sorted(state.sign_index_by_body.keys()):
            parts.append(
                "{0}:{1}:{2}:{3}".format(
                    body,
                    int(state.sign_index_by_body.get(body, 0)),
                    int(state.day_progress_by_body.get(body, 0)),
                    int(state.segment_progress_by_body.get(body, 0)),
                )
            )
        for body in _RETROGRADE_BODIES:
            retro_state = self._retrograde_state_by_body.get(body, {})
            parts.append(
                "retro:{0}:{1}:{2:.4f}".format(
                    body,
                    1 if bool(retro_state.get("active", False)) else 0,
                    float(retro_state.get("remaining", 0.0)),
                )
            )
        return "{0:08x}".format(fnv1_32("|".join(parts)))

    def load_from_record(self, record: Mapping[str, object]) -> TransitState:
        """Load from persisted record. Falls back to initialize() if missing."""
        if not record:
            return self.initialize(seed=self._seed)

        version = int(record.get("version", 0))
        if version == self.LEGACY_SAVE_RECORD_VERSION:
            log.info("Loading legacy transit save record version %s", version)
            return self._load_v1_record(record)

        if version == 2:
            log.info("Loading transit save record version %s", version)
            return self._load_v2_record(record)

        if version != self.SAVE_RECORD_VERSION:
            log.warning(
                "Unsupported transit save record version %s (expected %s). Reinitializing.",
                version,
                self.SAVE_RECORD_VERSION,
            )
            return self.initialize(seed=self._seed)
        return self._load_v2_record(record)

    def build_save_record(self) -> Dict[str, object]:
        """Return persistence payload for save data."""
        self._ensure_retrograde_state_initialized()
        self._capture_current_state_as_anchor(
            total_days_elapsed=self._last_total_days_seen,
            total_day_progress_elapsed=self._last_total_day_progress_seen,
            total_segments_elapsed=self._last_total_segments_seen,
        )
        return {
            "version": self.SAVE_RECORD_VERSION,
            "seed": self._seed,
            "lunar_cycle_days_hint": self._lunar_cycle_days_hint,
            "sim_days_per_year_hint": self._sim_days_per_year_hint,
            "anchor_state_payload": dict(self._anchor_state_payload or {}),
            "anchor_total_days_elapsed": self._anchor_total_days_elapsed,
            "anchor_total_day_progress_elapsed": self._anchor_total_day_progress_elapsed,
            "anchor_total_segments_elapsed": self._anchor_total_segments_elapsed,
            "anchor_venus_sun_offset": self._anchor_venus_sun_offset,
            "anchor_mercury_sun_offset": self._anchor_mercury_sun_offset,
            "anchor_moon_sign_progress_fraction": self._anchor_moon_sign_progress_fraction,
            "anchor_retrograde_state_by_body": {
                body: dict(self._anchor_retrograde_state_by_body.get(body, {}))
                for body in _RETROGRADE_BODIES
            },
            "last_total_days_seen": self._last_total_days_seen,
            "last_total_day_progress_seen": self._last_total_day_progress_seen,
            "last_total_segments_seen": self._last_total_segments_seen,
            "last_snapshot_key": self.current_snapshot_key(),
            "retrograde_active_by_body": self.retrograde_active_by_body(),
            self.CHART_RECORDS_KEY: {
                str(sim_id): dict(payload)
                for sim_id, payload in self._chart_record_payload_by_sim_id.items()
                if isinstance(payload, Mapping)
            },
            self.MODE_LOCK_KEY: dict(self._mode_lock_payload),
        }

    def build_anchor_save_record(self, *, include_mode_lock: bool = True) -> Dict[str, object]:
        """Return the minimal save payload needed to restore the transit engine."""
        self._ensure_retrograde_state_initialized()
        self._capture_current_state_as_anchor(
            total_days_elapsed=self._last_total_days_seen,
            total_day_progress_elapsed=self._last_total_day_progress_seen,
            total_segments_elapsed=self._last_total_segments_seen,
        )
        record = {
            "version": self.SAVE_RECORD_VERSION,
            "seed": self._seed,
            "lunar_cycle_days_hint": self._lunar_cycle_days_hint,
            "sim_days_per_year_hint": self._sim_days_per_year_hint,
            "anchor_state_payload": dict(self._anchor_state_payload or {}),
            "anchor_total_days_elapsed": self._anchor_total_days_elapsed,
            "anchor_total_day_progress_elapsed": self._anchor_total_day_progress_elapsed,
            "anchor_total_segments_elapsed": self._anchor_total_segments_elapsed,
            "anchor_venus_sun_offset": self._anchor_venus_sun_offset,
            "anchor_mercury_sun_offset": self._anchor_mercury_sun_offset,
            "anchor_moon_sign_progress_fraction": self._anchor_moon_sign_progress_fraction,
            "anchor_retrograde_state_by_body": {
                body: dict(self._anchor_retrograde_state_by_body.get(body, {}))
                for body in _RETROGRADE_BODIES
            },
            "last_total_days_seen": self._last_total_days_seen,
            "last_total_day_progress_seen": self._last_total_day_progress_seen,
            "last_total_segments_seen": self._last_total_segments_seen,
            "last_snapshot_key": self.current_snapshot_key(),
            "retrograde_active_by_body": self.retrograde_active_by_body(),
        }
        if include_mode_lock:
            record[self.MODE_LOCK_KEY] = dict(self._mode_lock_payload)
        return record

    def reseed_mars_plus(self, *, seed: Optional[int] = None) -> Dict[str, object]:
        """Reseed Mars-plus sign placement without disturbing tethered bodies."""
        state = self.state
        tethered_before = {
            body: int(state.sign_index_by_body.get(body, 0))
            for body in TETHERED_INITIAL_BODIES
        }
        mars_plus_before = {
            body: int(state.sign_index_by_body.get(body, 0))
            for body in FREE_INITIAL_MARS_PLUS_BODIES
        }
        applied_seed = self._seed if seed is None else int(seed)
        self._state = reseed_mars_plus_state(state, seed=applied_seed)
        tethered_after = {
            body: int(self._state.sign_index_by_body.get(body, 0))
            for body in TETHERED_INITIAL_BODIES
        }
        mars_plus_after = {
            body: int(self._state.sign_index_by_body.get(body, 0))
            for body in FREE_INITIAL_MARS_PLUS_BODIES
        }
        self._capture_current_state_as_anchor(
            total_days_elapsed=self._last_total_days_seen,
            total_day_progress_elapsed=self._last_total_day_progress_seen,
            total_segments_elapsed=self._last_total_segments_seen,
        )
        return {
            "seed": applied_seed,
            "tethered_before": tethered_before,
            "tethered_after": tethered_after,
            "mars_plus_before": mars_plus_before,
            "mars_plus_after": mars_plus_after,
        }

    def clear_dynamic_chart_record_payloads(self) -> Dict[str, object]:
        """Drop non-historical chart caches so they can rebuild from current sky state."""
        removed_sim_ids = []
        kept_sim_ids = []
        next_payloads: Dict[int, Dict[str, object]] = {}

        for sim_id, payload in self._chart_record_payload_by_sim_id.items():
            if not isinstance(payload, Mapping):
                continue
            metadata = payload.get("metadata")
            chart_source = ""
            if isinstance(metadata, Mapping):
                chart_source = str(metadata.get("chart_source") or "").strip()
            if chart_source in _CHART_RECORD_SOURCES_TO_PRESERVE_ON_TRANSIT_RESEED:
                next_payloads[int(sim_id)] = dict(payload)
                kept_sim_ids.append(int(sim_id))
                continue
            removed_sim_ids.append(int(sim_id))

        self._chart_record_payload_by_sim_id = next_payloads
        return {
            "removed_count": int(len(removed_sim_ids)),
            "kept_count": int(len(kept_sim_ids)),
            "removed_sim_ids": tuple(removed_sim_ids),
            "kept_sim_ids": tuple(kept_sim_ids),
            "preserved_sources": tuple(
                sorted(_CHART_RECORD_SOURCES_TO_PRESERVE_ON_TRANSIT_RESEED)
            ),
        }

    def advance(
        self,
        *,
        elapsed_days: int = 0,
        elapsed_day_progress: Optional[float] = None,
        elapsed_segments: int = 0,
        lunar_cycle_days: Optional[float] = None,
        sim_days_per_year: Optional[float] = None,
        event_source: str = "advance",
    ) -> Dict[str, int]:
        """Explicit advancement API."""
        if sim_days_per_year is not None:
            self.set_sim_days_per_year_hint(sim_days_per_year)
        if lunar_cycle_days is not None:
            self._lunar_cycle_days_hint = self._normalize_lunar_cycle_days(lunar_cycle_days)
        if elapsed_day_progress is None:
            elapsed_day_progress = float(max(0, int(elapsed_days)))
        else:
            try:
                elapsed_day_progress = max(float(elapsed_day_progress), float(max(0, int(elapsed_days))))
            except Exception:
                elapsed_day_progress = float(max(0, int(elapsed_days)))
        moved = advance_transits(
            self.state,
            elapsed_days=max(0, int(elapsed_days)),
            elapsed_segments=max(0, int(elapsed_segments)),
            skip_bodies=("Moon", "Mars"),
            body_names=self.active_body_names(),
        )
        moved["Moon"] = self._advance_moon_dynamic(
            max(0, int(elapsed_days)),
            lunar_cycle_days=lunar_cycle_days,
        )
        moved["Mars"] = self._advance_mars_dynamic(max(0, int(elapsed_segments)))
        self._advance_sun_relative_offsets(moved)
        self._sync_sun_relative_bodies()
        retro_changes = self._advance_retrogrades(
            elapsed_day_progress=float(elapsed_day_progress),
            elapsed_segments=max(0, int(elapsed_segments)),
        )
        self._record_retrograde_changes(
            retro_changes,
            elapsed_days=max(0, int(elapsed_days)),
            elapsed_day_progress=float(elapsed_day_progress),
            elapsed_segments=max(0, int(elapsed_segments)),
            source=str(event_source or "advance"),
        )
        advanced_days = max(0, int(elapsed_days))
        advanced_segments = max(0, int(elapsed_segments))
        if (
            (advanced_days > 0 or advanced_segments > 0 or float(elapsed_day_progress) > 0.0)
            and str(event_source or "advance") not in ("clock_snapshot", "save_record_rebuild")
        ):
            if self._anchor_state_payload is None:
                anchor_days = self._last_total_days_seen
                anchor_segments = self._last_total_segments_seen
                if anchor_days is None and anchor_segments is None:
                    anchor_days = advanced_days
                    anchor_segments = advanced_segments
                self._capture_current_state_as_anchor(
                    total_days_elapsed=anchor_days,
                    total_segments_elapsed=anchor_segments,
                )
            current_days = int(self._last_total_days_seen or 0)
            current_day_progress = float(self._last_total_day_progress_seen or current_days)
            current_segments = int(self._last_total_segments_seen or 0)
            self._last_total_days_seen = current_days + advanced_days
            self._last_total_day_progress_seen = current_day_progress + float(elapsed_day_progress)
            self._last_total_segments_seen = current_segments + advanced_segments
            self._sync_segment_anchored_bodies(int(self._last_total_segments_seen or 0))
        return moved

    def advance_from_totals(
        self,
        *,
        total_days_elapsed: int,
        total_day_progress_elapsed: Optional[float] = None,
        total_segments_elapsed: int,
        lunar_cycle_days: Optional[float] = None,
        sim_days_per_year: Optional[float] = None,
    ) -> Dict[str, int]:
        """Advance by comparing absolute counters to last seen values.

        Caller should provide monotonically increasing totals.
        """
        total_days_elapsed = max(0, int(total_days_elapsed))
        if total_day_progress_elapsed is None:
            total_day_progress_elapsed = float(total_days_elapsed)
        else:
            try:
                total_day_progress_elapsed = float(total_day_progress_elapsed)
            except Exception:
                total_day_progress_elapsed = float(total_days_elapsed)
        total_day_progress_elapsed = max(float(total_days_elapsed), float(total_day_progress_elapsed))
        total_segments_elapsed = max(0, int(total_segments_elapsed))
        if sim_days_per_year is not None:
            self.set_sim_days_per_year_hint(sim_days_per_year)
        if lunar_cycle_days is not None:
            self._lunar_cycle_days_hint = self._normalize_lunar_cycle_days(lunar_cycle_days)

        if (
            self._last_total_days_seen is None
            or self._last_total_day_progress_seen is None
            or self._last_total_segments_seen is None
        ):
            self._last_total_days_seen = total_days_elapsed
            self._last_total_day_progress_seen = total_day_progress_elapsed
            self._last_total_segments_seen = total_segments_elapsed
            self._sync_segment_anchored_bodies(total_segments_elapsed)
            self._capture_current_state_as_anchor(
                total_days_elapsed=total_days_elapsed,
                total_day_progress_elapsed=total_day_progress_elapsed,
                total_segments_elapsed=total_segments_elapsed,
            )
            return {body: 0 for body in self.state.sign_index_by_body.keys()}

        elapsed_days = max(0, total_days_elapsed - self._last_total_days_seen)
        elapsed_day_progress = max(
            0.0,
            float(total_day_progress_elapsed) - float(self._last_total_day_progress_seen),
        )
        elapsed_segments = max(0, total_segments_elapsed - self._last_total_segments_seen)

        self._last_total_days_seen = total_days_elapsed
        self._last_total_day_progress_seen = total_day_progress_elapsed
        self._last_total_segments_seen = total_segments_elapsed

        moved = self.advance(
            elapsed_days=elapsed_days,
            elapsed_day_progress=elapsed_day_progress,
            elapsed_segments=elapsed_segments,
            lunar_cycle_days=lunar_cycle_days,
            sim_days_per_year=sim_days_per_year,
            event_source="clock_snapshot",
        )
        self._sync_segment_anchored_bodies(total_segments_elapsed)
        return moved

    def chart_for_rising(self, rising_sign_name: str) -> Dict[str, Dict[str, Optional[int]]]:
        rising_sign_index = SIGN_TO_INDEX[rising_sign_name]
        house_sign_map = build_house_sign_map_for_rising(rising_sign_index)
        return body_chart_for_sim(
            self.state,
            house_sign_map,
            body_names=self.active_body_names(),
        )

    def chart_for_house_sign_map(
        self, house_sign_map: Mapping[int, int]
    ) -> Dict[str, Dict[str, Optional[int]]]:
        return body_chart_for_sim(
            self.state,
            house_sign_map,
            body_names=self.active_body_names(),
        )

    def current_sim_day(self) -> int:
        return int(self._last_total_days_seen or 0)

    def set_last_houses_readout_payload(
        self, sim_id: int, payload: Mapping[str, object]
    ) -> None:
        self._last_houses_readout_by_sim_id[int(sim_id)] = dict(payload)

    def get_last_houses_readout_payload(self, sim_id: int) -> Optional[Dict[str, object]]:
        payload = self._last_houses_readout_by_sim_id.get(int(sim_id))
        if payload is None:
            return None
        return dict(payload)

    def set_chart_record_payload(
        self, sim_id: int, payload: Mapping[str, object]
    ) -> None:
        self._chart_record_payload_by_sim_id[int(sim_id)] = dict(payload)

    def get_chart_record_payload(self, sim_id: int) -> Optional[Dict[str, object]]:
        payload = self._chart_record_payload_by_sim_id.get(int(sim_id))
        if payload is None:
            return None
        return dict(payload)

    def set_mode_lock_payload(self, payload: Mapping[str, object]) -> None:
        self._mode_lock_payload = dict(payload) if isinstance(payload, Mapping) else {}

    def get_mode_lock_payload(self) -> Dict[str, object]:
        return dict(self._mode_lock_payload)


_GLOBAL_TRANSIT_SERVICE: Optional[CosmicTransitService] = None


def get_global_transit_service() -> CosmicTransitService:
    global _GLOBAL_TRANSIT_SERVICE
    if _GLOBAL_TRANSIT_SERVICE is None:
        _GLOBAL_TRANSIT_SERVICE = CosmicTransitService()
    return _GLOBAL_TRANSIT_SERVICE
