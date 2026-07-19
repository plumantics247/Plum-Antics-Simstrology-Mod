# Cosmic Engine Transit Runtime Blueprint

## Goal
Use XML for declarative content (traits, loots, notifications, interactions) and Python for dynamic time math (planet movement + random starts + periodic updates).

## What XML Should Own
- Rising traits and their house-sign marker assignment routers.
- House/sign marker traits (`PlumAntics_SimstrologyHouses_<House>_<Sign>Hidden`).
- Player-facing interactions (computer/bookcase "read chart" flows).
- Notification loot actions and localized strings.

## What Python Should Own
- Global transit state for bodies:
  - Moon: +1 sign every 1 sim day
  - Mercury: +1 sign every 2 sim days
  - Sun: +1 sign every 1 season segment
  - Venus: +1 sign every 1 season segment
  - Mars: +1 sign every 2 season segments
  - Jupiter: +1 sign every 12 season segments (1 sim year)
  - Saturn: +1 sign every 30 season segments (2.5 sim years)
- Random initial sign per body when a save first initializes transit state.
- Time progression checks and sign-step updates.
- Resolver API used by chart-reading interactions (body sign + house per target sim).

## Core Math
- House map from rising sign:
  - `house_sign[house_index] = (rising_sign_index + house_index) % 12`
- House for any sign under a rising:
  - `house_index = (sign_index - rising_sign_index) % 12`
- This is equivalent to your marker trait assignment and can be cross-checked.

## Persistence Strategy
- Persist a compact payload:
  - `sign_index_by_body`
  - `day_progress_by_body`
  - `segment_progress_by_body`
- Keep this in Python-managed save data.
- Do not duplicate this state into many XML traits/buffs unless needed for UI display.

## Why This Split
- XML-only approach for moving transits requires many routers and timing chains and grows quickly.
- Python keeps moving parts small while still allowing XML notifications and interactions.
- Marker traits remain useful for chart reading and future "read another Sim" interactions.

## Minimal Rollout (Recommended)
1. Keep current XML marker system for rising -> house-sign map.
2. Add Python transit service that updates body sign state by elapsed time.
3. Expose one helper that returns, for a target sim:
   - each body's sign
   - each body's house (resolved from target rising markers)
4. Reuse existing notification loots to present results.
5. Add optional buffs/effects later once timing logic is stable.

## Current Tooling
- `tools/transit_math.py` already includes:
  - transit rules
  - deterministic random initialization
  - advancement math
  - marker trait id/name helpers
  - house/sign resolution from markers or rising math
  - CLI simulation output for quick tuning tests
- Runtime scaffold package:
  - `python/cosmic_engine/transit_service.py`
  - `python/cosmic_engine/runtime_hooks.py`
  - `python/cosmic_engine/houses_notification_bridge.py`
  - `python/cosmic_engine/loot_actions.py`
  - `python/cosmic_engine/save_adapter.py`
  - preserves existing Houses notification loot flow via
    `existing_notification_loot_id` mapping
  - XML router hook added:
    `src/HousesandProgressions/Action/PlumAntics_SimstrologyHouses_PythonReadoutBridge_Loot.xml`
