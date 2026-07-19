"""Save/load adapter for plugging Cosmic transit state into a framework."""

from __future__ import annotations

from typing import Callable, Dict, MutableMapping, Optional

from .runtime_hooks import on_clock_snapshot, on_pre_save, on_zone_or_save_load
from .transit_service import CosmicTransitService


class CosmicTransitSaveAdapter:
    """Thin adapter over runtime hooks.

    Wire this into whichever persistence layer you use for script-mod data.
    """

    def __init__(
        self,
        *,
        read_record_fn: Callable[[str], Optional[Dict[str, object]]],
        write_record_fn: Callable[[str, Dict[str, object]], None],
        fallback_seed: Optional[int] = None,
    ) -> None:
        self._read_record_fn = read_record_fn
        self._write_record_fn = write_record_fn
        self._fallback_seed = fallback_seed

    @classmethod
    def from_dict_container(
        cls,
        container: MutableMapping[str, object],
        *,
        fallback_seed: Optional[int] = None,
    ) -> "CosmicTransitSaveAdapter":
        def _read(key: str) -> Optional[Dict[str, object]]:
            value = container.get(key)
            return value if isinstance(value, dict) else None

        def _write(key: str, record: Dict[str, object]) -> None:
            container[key] = dict(record)

        return cls(
            read_record_fn=_read,
            write_record_fn=_write,
            fallback_seed=fallback_seed,
        )

    @property
    def record_key(self) -> str:
        return CosmicTransitService.SAVE_RECORD_KEY

    def load(self) -> CosmicTransitService:
        record = self._read_record_fn(self.record_key)
        return on_zone_or_save_load(
            saved_record=record,
            fallback_seed=self._fallback_seed,
        )

    def save(self) -> Dict[str, object]:
        record = on_pre_save()
        self._write_record_fn(self.record_key, record)
        return record

    def tick(
        self,
        *,
        total_days_elapsed: int,
        total_segments_elapsed: int,
    ) -> Dict[str, int]:
        return on_clock_snapshot(
            total_days_elapsed=total_days_elapsed,
            total_segments_elapsed=total_segments_elapsed,
        )
