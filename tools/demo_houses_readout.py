#!/usr/bin/env python3
"""Quick demo for houses notification bridge payload."""

from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
PYTHON_DIR = ROOT / "python"
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))

from cosmic_engine.houses_notification_bridge import build_houses_readout_payload  # noqa: E402
from cosmic_engine.transit_service import get_global_transit_service  # noqa: E402


def main() -> int:
    service = get_global_transit_service()
    service.initialize(seed=42)

    # Example: Aries rising trait id.
    payload = build_houses_readout_payload(
        service,
        actor_trait_ids=[10264073582958847151],
        actor_marker_trait_ids=[],
    )
    print("existing_notification_loot_id:", payload["existing_notification_loot_id"])
    print("rising_sign_name:", payload.get("rising_sign_name"))
    print("body_lines:")
    for line in payload.get("body_lines", []):
        print(" -", line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
