"""Hidden pair-memory helpers for chemistry first-contact writes."""

from __future__ import annotations

from typing import Dict, Iterable


RISING_KNOWN_RELBIT_NAME = "RisingKnown"
SUN_KNOWN_RELBIT_NAME = "SunKnown"
RISING_KNOWN_RELBIT_ID = 830000000000009601
SUN_KNOWN_RELBIT_ID = 830000000000009602
PAIR_MEMORY_RELBIT_IDS = {
    RISING_KNOWN_RELBIT_NAME: int(RISING_KNOWN_RELBIT_ID),
    SUN_KNOWN_RELBIT_NAME: int(SUN_KNOWN_RELBIT_ID),
}


def _has_text(value) -> bool:
    return bool(str(value or "").strip())


def _has_complete_sign_data(refresh_summary, sign_keys: Iterable[str]) -> bool:
    if not isinstance(refresh_summary, dict):
        return False
    return all(_has_text(refresh_summary.get(sign_key)) for sign_key in sign_keys)


def should_write_pair_memory(refresh_summary) -> bool:
    if not isinstance(refresh_summary, dict) or not refresh_summary.get("ok"):
        return False
    return _has_complete_sign_data(
        refresh_summary,
        (
            "actor_rising_sign_name",
            "target_rising_sign_name",
            "actor_sun_sign_name",
            "target_sun_sign_name",
        ),
    )


def build_pair_memory_write_summary(
    refresh_summary,
    *,
    rising_known=False,
    sun_known=False,
) -> Dict[str, object]:
    if bool(rising_known) and bool(sun_known):
        return {"ok": True, "reason": "already_known", "relbits_to_write": []}
    if not should_write_pair_memory(refresh_summary):
        return {"ok": False, "reason": "missing_sign_data", "relbits_to_write": []}
    relbits_to_write = [RISING_KNOWN_RELBIT_NAME, SUN_KNOWN_RELBIT_NAME]
    return {
        "ok": True,
        "reason": "write_both",
        "relbits_to_write": relbits_to_write,
        "relbit_ids": [PAIR_MEMORY_RELBIT_IDS[name] for name in relbits_to_write],
    }


def iter_relbit_ids_for_layer(layer_name) -> Iterable[int]:
    text = str(layer_name or "").strip().lower()
    if text == "rising":
        yield int(RISING_KNOWN_RELBIT_ID)
    elif text == "sun":
        yield int(SUN_KNOWN_RELBIT_ID)
    elif text == "both":
        yield int(RISING_KNOWN_RELBIT_ID)
        yield int(SUN_KNOWN_RELBIT_ID)
