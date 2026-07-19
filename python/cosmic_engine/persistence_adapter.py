"""Persistence policy adapter for Cosmic Engine transit save state."""

from __future__ import annotations

from typing import Callable, Dict, Optional

from .chemistry_settings import (
    merge_chemistry_profile_payload,
    read_chemistry_profile_id,
    read_chemistry_profile_payload,
)
from .retrograde_visibility_settings import (
    merge_retrograde_visibility_profile_payload,
    read_retrograde_visibility_profile_id,
    read_retrograde_visibility_profile_payload,
)
from .sign_compatibility_seed_settings import (
    merge_sign_compatibility_seed_payload,
    remove_sign_compatibility_seed_payload_for_sim,
    read_sign_compatibility_seed_payload,
)


class TransitPersistenceAdapter:
    """Encapsulate transit persistence policy separate from runtime install hooks."""

    def __init__(
        self,
        *,
        read_in_save_payload: Callable[[], Dict[str, object]],
        write_in_save_payload: Callable[[Dict[str, object]], bool],
        resolve_save_slot_key: Callable[[], str],
        on_pre_save: Callable[[], Dict[str, object]],
        log_warn_once: Callable[..., None],
        log_exception: Callable[..., None],
        log_debug: Callable[..., None],
    ) -> None:
        self._read_in_save_payload = read_in_save_payload
        self._write_in_save_payload = write_in_save_payload
        self._resolve_save_slot_key = resolve_save_slot_key
        self._on_pre_save = on_pre_save
        self._log_warn_once = log_warn_once
        self._log_exception = log_exception
        self._log_debug = log_debug

    def read_persisted_payload(self):
        payload = self._read_in_save_payload()
        return payload if isinstance(payload, dict) else {}

    def write_persisted_payload(self, payload):
        if not isinstance(payload, dict):
            return False
        if self._write_in_save_payload(payload):
            return True
        self._log_warn_once(
            "mod_data_write_unavailable",
            "Cosmic Engine could not write transit state to gameplay_data.mod_data.",
        )
        return False

    def load_persisted_transit_record(self) -> Optional[Dict[str, object]]:
        payload = self.read_persisted_payload()
        slots = payload.get("slots")
        if not isinstance(slots, dict):
            return None

        slot_key = self._resolve_save_slot_key()
        slot_payload = slots.get(slot_key)
        if not isinstance(slot_payload, dict):
            slot_payload = slots.get("default")
        if not isinstance(slot_payload, dict):
            return None

        record = slot_payload.get("transit_record")
        return record if isinstance(record, dict) else None

    def load_persisted_chemistry_profile(self) -> Dict[str, object]:
        payload = self.read_persisted_payload()
        return read_chemistry_profile_payload(payload)

    def load_persisted_retrograde_visibility_profile(self) -> Dict[str, object]:
        payload = self.read_persisted_payload()
        return read_retrograde_visibility_profile_payload(payload)

    def load_persisted_sign_compatibility_seed_profile(self) -> Dict[str, object]:
        payload = self.read_persisted_payload()
        return read_sign_compatibility_seed_payload(payload)

    def persist_transit_record(self, reason: str = "unknown") -> bool:
        try:
            record = self._on_pre_save()
        except Exception:
            self._log_exception("Cosmic Engine on_pre_save() failed during %s", reason)
            return False

        if not isinstance(record, dict):
            return False

        payload = self.read_persisted_payload()
        slots = payload.get("slots")
        if not isinstance(slots, dict):
            slots = {}
            payload["slots"] = slots

        slot_key = self._resolve_save_slot_key()
        slots[slot_key] = {
            "transit_record": dict(record),
        }
        payload["version"] = 1
        if not self.write_persisted_payload(payload):
            return False
        self._log_debug(
            "Persisted transit record for slot %s (%s) via %s.",
            slot_key,
            reason,
            "in_save_mod_data",
        )
        return True

    def persist_chemistry_profile(self, profile_id: str, reason: str = "unknown") -> bool:
        payload = merge_chemistry_profile_payload(
            self.read_persisted_payload(),
            requested_profile_id=profile_id,
        )
        if payload.get("version") is None:
            payload["version"] = 1
        if not self.write_persisted_payload(payload):
            return False
        self._log_debug(
            "Persisted chemistry profile %s (%s) via %s.",
            read_chemistry_profile_id(payload),
            reason,
            "in_save_mod_data",
        )
        return True

    def persist_retrograde_visibility_profile(self, profile_id: str, reason: str = "unknown") -> bool:
        payload = merge_retrograde_visibility_profile_payload(
            self.read_persisted_payload(),
            requested_profile_id=profile_id,
        )
        if payload.get("version") is None:
            payload["version"] = 1
        if not self.write_persisted_payload(payload):
            return False
        self._log_debug(
            "Persisted retrograde visibility profile %s (%s) via %s.",
            read_retrograde_visibility_profile_id(payload),
            reason,
            "in_save_mod_data",
        )
        return True

    def persist_sign_compatibility_seed_profile(
        self,
        sim_id,
        seed_record,
        reason: str = "unknown",
    ) -> bool:
        payload = merge_sign_compatibility_seed_payload(
            self.read_persisted_payload(),
            sim_id=sim_id,
            seed_record=seed_record,
        )
        if payload.get("version") is None:
            payload["version"] = 1
        if not self.write_persisted_payload(payload):
            return False
        self._log_debug(
            "Persisted sign compatibility seed profile for sim %s (%s) via %s.",
            sim_id,
            reason,
            "in_save_mod_data",
        )
        return True

    def remove_sign_compatibility_seed_profile(self, sim_id, reason: str = "unknown") -> bool:
        payload = remove_sign_compatibility_seed_payload_for_sim(
            self.read_persisted_payload(),
            sim_id=sim_id,
        )
        if payload.get("version") is None:
            payload["version"] = 1
        if not self.write_persisted_payload(payload):
            return False
        self._log_debug(
            "Removed sign compatibility seed profile for sim %s (%s) via %s.",
            sim_id,
            reason,
            "in_save_mod_data",
        )
        return True
