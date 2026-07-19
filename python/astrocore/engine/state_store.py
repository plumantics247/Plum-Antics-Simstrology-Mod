from __future__ import annotations

from typing import Dict, List


class EngineStateStore(object):
    def __init__(self):
        self._completed = set()
        self._deferred: List[Dict[str, object]] = []

    def mark_completed(self, addon_name, event_name, sim_id):
        self._completed.add((str(addon_name), str(event_name), int(sim_id or 0)))

    def was_completed(self, addon_name, event_name, sim_id):
        return (str(addon_name), str(event_name), int(sim_id or 0)) in self._completed

    def defer(self, *, addon_name, event_name, sim_id=0, reason="", payload=None):
        self._deferred.append(
            {
                "addon_name": str(addon_name),
                "event_name": str(event_name),
                "sim_id": int(sim_id or 0),
                "reason": str(reason),
                "payload": dict(payload or {}),
            }
        )

    def pop_due(self, event_name):
        due = [row for row in self._deferred if row["event_name"] == str(event_name)]
        self._deferred = [row for row in self._deferred if row["event_name"] != str(event_name)]
        return due
