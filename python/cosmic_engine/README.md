# Cosmic Engine Python Scaffold

## Included modules
- `../cosmic_engine_loader.py`: top-level loader for script package import.
- `transit_core.py`: pure transit and house math.
- `transit_service.py`: global transit state + persistence record helpers.
- `houses_notification_bridge.py`: maps rising traits to current XML house notification loots and builds transit chart payloads.
- `runtime_hooks.py`: simple hook functions for load/save/tick integration.
- `loot_actions.py`: custom action class `SimstrologyHousesPythonReadoutLoot` for XML outcome routing.
- `save_adapter.py`: framework adapter (`load/save/tick`) around runtime hooks.
- `bootstrap.py`: optional debug command registration (`ce.transit.dump`, `ce.transit.advance`).

## Intended flow
1. On zone/save load:
   - call `runtime_hooks.on_zone_or_save_load(...)`
2. On time updates:
   - call `runtime_hooks.on_clock_snapshot(total_days_elapsed=..., total_segments_elapsed=...)`
3. On save:
   - call `runtime_hooks.on_pre_save()` and persist under key:
   - `CosmicTransitService.SAVE_RECORD_KEY`
4. During house-read interaction:
   - XML now calls `PlumAntics_SimstrologyHouses_PythonReadoutBridge_Loot`
   - Python caches `build_houses_readout_payload(...)` by `sim_id`
   - existing XML notification loots still run as before
   - you can inspect payload in-game via `ce.houses.last <sim_id>`

## Local sanity test
Set `PYTHONPATH=python` and run:

```powershell
python -c "from cosmic_engine import get_global_transit_service as g; s=g(); s.initialize(seed=42); print(s.advance(elapsed_days=2, elapsed_segments=1)); print(s.build_save_record())"
```

## Packaging note
- Your current `s4tk.config.json` builds only `src/*` package resources.
- These Python files must be compiled/packed separately as a `.ts4script` script mod.
- One-command helper (PowerShell):

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\build_ts4script.ps1
```

- Optional runtime `.pyc` archive (recommended with Python 3.7 path):

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\build_ts4script.ps1 -PycPython "C:\Path\To\Python37\python.exe"
```
