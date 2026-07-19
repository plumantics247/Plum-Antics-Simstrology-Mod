"""Carrier-specific persistence helpers for Cosmic Engine transit state."""

from __future__ import annotations

import base64
import json
from typing import Callable, Dict, Iterable, Optional


class TransitPersistenceCarriers:
    """Encapsulate carrier I/O separate from runtime bootstrap logic."""

    def __init__(
        self,
        *,
        module_file: str,
        get_persistence_service: Callable[[], object],
        iter_households: Callable[[], Iterable[object]],
        in_save_payload_prefix: str,
        in_save_payload_suffix: str,
        log_warn_once: Callable[..., None],
        log_exception: Callable[..., None],
    ) -> None:
        self._module_file = str(module_file or "")
        self._get_persistence_service = get_persistence_service
        self._iter_households = iter_households
        self._in_save_payload_prefix = str(in_save_payload_prefix or "")
        self._in_save_payload_suffix = str(in_save_payload_suffix or "")
        self._log_warn_once = log_warn_once
        self._log_exception = log_exception
        self._mod_data_key = "plumantics_cosmic_engine_transit"

    def read_sidecar_payload(self):
        # Legacy sidecar file persistence is retired. Keep the method as a
        # compatibility no-op so older callers cannot perform filesystem I/O.
        return {}

    def write_sidecar_payload(self, payload):
        # Legacy sidecar file persistence is retired in favor of
        # gameplay_data.mod_data. Always refuse filesystem writes here.
        self._log_warn_once(
            "legacy_sidecar_write_blocked",
            "Cosmic Engine blocked a retired legacy sidecar write and kept save data in gameplay_data.mod_data.",
        )
        return False

    def _get_household_description(self, household):
        if household is None:
            return ""
        try:
            return str(getattr(household, "description", "") or "")
        except Exception:
            return ""

    def _set_household_description(self, household, text):
        if household is None or not hasattr(household, "description"):
            return False
        try:
            household.description = str(text or "")
            return True
        except Exception:
            return False

    def _split_in_save_payload_text(self, raw_text):
        text = str(raw_text or "")
        start = text.find(self._in_save_payload_prefix)
        if start < 0:
            return text, None
        end = text.find(self._in_save_payload_suffix, start + len(self._in_save_payload_prefix))
        if end < 0:
            return text, None
        encoded = text[start + len(self._in_save_payload_prefix) : end]
        visible = (text[:start] + text[end + len(self._in_save_payload_suffix) :]).strip()
        return visible, encoded.strip() or None

    def _decode_in_save_payload(self, encoded):
        if not encoded:
            return {}
        try:
            raw = base64.urlsafe_b64decode(str(encoded).encode("ascii"))
            payload = json.loads(raw.decode("utf-8"))
        except Exception:
            return {}
        return payload if isinstance(payload, dict) else {}

    def _strip_in_save_payload_from_household(self, household):
        if household is None:
            return False
        raw_text = self._get_household_description(household)
        visible_text, encoded = self._split_in_save_payload_text(raw_text)
        if not encoded:
            return False
        if visible_text == raw_text:
            return False
        if not self._set_household_description(household, visible_text):
            self._log_warn_once(
                "in_save_payload_strip_failed",
                "Cosmic Engine could not remove an embedded payload from a household description.",
            )
            return False
        return True

    def cleanup_embedded_household_payloads(self):
        removed = 0
        for household in self._iter_households():
            try:
                if self._strip_in_save_payload_from_household(household):
                    removed += 1
            except Exception:
                continue
        return int(removed)

    def _is_ce_data_household(self, household):
        if household is None:
            return False
        _, encoded = self._split_in_save_payload_text(self._get_household_description(household))
        return bool(encoded)

    def _find_ce_data_household(self):
        for household in self._iter_households():
            try:
                if self._is_ce_data_household(household):
                    return household
            except Exception:
                continue
        return None

    def _get_mod_data_container(self):
        persistence_service = None
        try:
            persistence_service = self._get_persistence_service()
        except Exception:
            persistence_service = None
        if persistence_service is None:
            return None

        for getter_name in ("get_save_slot_proto_buff", "get_save_game_data_proto"):
            getter = getattr(persistence_service, getter_name, None)
            if not callable(getter):
                continue
            try:
                proto = getter()
            except Exception:
                proto = None
            if proto is None:
                continue
            gameplay_data = getattr(proto, "gameplay_data", None)
            if gameplay_data is None:
                continue
            mod_data = getattr(gameplay_data, "mod_data", None)
            if mod_data is not None:
                return mod_data
        return None

    def _read_mod_data_payload(self):
        mod_data = self._get_mod_data_container()
        if mod_data is None:
            return {}
        try:
            raw = mod_data.get(self._mod_data_key)
        except Exception:
            return {}
        if not raw:
            return {}
        try:
            payload = json.loads(raw) if isinstance(raw, str) else raw
        except Exception:
            self._log_exception("Failed decoding Cosmic Engine mod_data payload.")
            return {}
        return payload if isinstance(payload, dict) else {}

    def _write_mod_data_payload(self, payload):
        if not isinstance(payload, dict):
            return False
        mod_data = self._get_mod_data_container()
        if mod_data is None:
            self._log_warn_once(
                "mod_data_container_missing",
                "Cosmic Engine could not access gameplay_data.mod_data for save-wide persistence.",
            )
            return False
        try:
            mod_data[self._mod_data_key] = json.dumps(payload, sort_keys=True, separators=(",", ":"))
            return True
        except Exception:
            self._log_exception("Failed writing Cosmic Engine mod_data payload.")
            return False

    def read_in_save_payload(self):
        payload = self._read_mod_data_payload()
        if isinstance(payload, dict) and payload:
            removed = self.cleanup_embedded_household_payloads()
            if removed > 0:
                self._log_warn_once(
                    "household_description_payload_migrated",
                    "Cosmic Engine migrated legacy household-description transit data to save-wide mod_data persistence.",
                )
            return payload

        # Legacy migration path only: read any old embedded description payload,
        # then immediately strip it out and rewrite it to save-wide mod_data.
        household = self._find_ce_data_household()
        if household is None:
            return {}
        _, encoded = self._split_in_save_payload_text(self._get_household_description(household))
        payload = self._decode_in_save_payload(encoded)
        stripped_any = self._strip_in_save_payload_from_household(household)
        if payload:
            if self._write_mod_data_payload(payload):
                self._log_warn_once(
                    "household_description_payload_migrated",
                    "Cosmic Engine migrated legacy household-description transit data to save-wide mod_data persistence.",
                )
            elif stripped_any:
                self._log_warn_once(
                    "household_description_payload_removed",
                    "Cosmic Engine removed legacy household-description transit data but could not rewrite it to mod_data.",
                )
            return payload
        if stripped_any:
            self._log_warn_once(
                "household_description_payload_removed",
                "Cosmic Engine removed an unreadable embedded payload from a household description.",
            )
        self._log_warn_once(
            "in_save_payload_decode_failed",
            "Cosmic Engine found an in-save payload marker but could not decode it.",
        )
        return {}

    def write_in_save_payload(self, payload):
        removed = self.cleanup_embedded_household_payloads()
        if removed > 0:
            self._log_warn_once(
                "household_description_payload_cleanup",
                "Cosmic Engine removed embedded transit data from household descriptions and now stores save state in gameplay_data.mod_data instead.",
            )
        return self._write_mod_data_payload(payload)

    def debug_payload_status(self, *, slot_key: Optional[str] = None) -> Dict[str, object]:
        mod_data = self._get_mod_data_container()
        payload = self._read_mod_data_payload()
        slots = payload.get("slots") if isinstance(payload, dict) else None
        resolved_slot_key = str(slot_key or "").strip() or None
        slot_payload = None
        if isinstance(slots, dict):
            if resolved_slot_key:
                slot_payload = slots.get(resolved_slot_key)
            if not isinstance(slot_payload, dict):
                slot_payload = slots.get("default")

        legacy_payload_count = 0
        for household in self._iter_households():
            try:
                if self._is_ce_data_household(household):
                    legacy_payload_count += 1
            except Exception:
                continue

        return {
            "mod_data_container_available": bool(mod_data is not None),
            "mod_data_payload_present": bool(isinstance(payload, dict) and bool(payload)),
            "payload_version": payload.get("version") if isinstance(payload, dict) else None,
            "slot_count": len(slots) if isinstance(slots, dict) else 0,
            "resolved_slot_key": resolved_slot_key,
            "resolved_slot_present": bool(isinstance(slot_payload, dict)),
            "legacy_household_payload_count": int(legacy_payload_count),
        }
