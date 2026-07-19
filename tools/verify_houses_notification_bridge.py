#!/usr/bin/env python3
"""Verify bridge constants against Houses notification XML files."""

from __future__ import annotations

import glob
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
PYTHON_DIR = ROOT / "python"
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))

from cosmic_engine.houses_notification_bridge import (  # noqa: E402
    RISING_SIGN_TRAIT_ID_TO_SIGN_INDEX,
    SIGN_INDEX_TO_EXISTING_NOTIFICATION_LOOT_ID,
)
from cosmic_engine.transit_core import SIGN_TO_INDEX  # noqa: E402


NOTIFICATION_RE = re.compile(r"n=\"PlumAntics_Big3Mod_(\w+)Notification_Loot\"")
INSTANCE_RE = re.compile(r"\bs=\"(\d+)\"")
TRAIT_RE = re.compile(r"<L n=\"whitelist_traits\">\s*<T>(\d+)", re.S)


def main() -> int:
    folder = ROOT / "src" / "HousesandProgressions" / "Action"
    paths = sorted(glob.glob(str(folder / "*Notification_Loot.xml")))
    if not paths:
        print("No notification files found.")
        return 1

    failures = []
    for path in paths:
        text = Path(path).read_text(encoding="utf-8")
        notif_match = NOTIFICATION_RE.search(text)
        inst_match = INSTANCE_RE.search(text)
        trait_match = TRAIT_RE.search(text)
        if not notif_match or not inst_match or not trait_match:
            failures.append(f"{Path(path).name}: could not parse notification data")
            continue

        sign_name = notif_match.group(1)
        sign_index = SIGN_TO_INDEX[sign_name]
        loot_id = int(inst_match.group(1))
        trait_id = int(trait_match.group(1))

        expected_loot = SIGN_INDEX_TO_EXISTING_NOTIFICATION_LOOT_ID.get(sign_index)
        expected_sign = RISING_SIGN_TRAIT_ID_TO_SIGN_INDEX.get(trait_id)
        if expected_loot != loot_id:
            failures.append(
                f"{Path(path).name}: loot mismatch expected={expected_loot} actual={loot_id}"
            )
        if expected_sign != sign_index:
            failures.append(
                f"{Path(path).name}: trait-sign mismatch expected={sign_index} actual={expected_sign}"
            )

    if failures:
        print("Bridge verification FAILED:")
        for failure in failures:
            print(f" - {failure}")
        return 1

    print(f"Bridge verification passed ({len(paths)} notification files).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
