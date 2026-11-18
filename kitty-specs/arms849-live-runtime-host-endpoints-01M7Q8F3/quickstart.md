# Quickstart: live verification for #1083

This is the procedure for SC-001–SC-003, the charter's pre-merge live exercise (form a). Run it on office4 after the mission merges into `feat/849-preconditions`.

## Preconditions

- The primary checkout is on `feat/849-preconditions` at the commit under test and is clean. Keep the untracked `.kittify/mission-state-audit/` moved aside (it is parked at `~/.local/share/kg-849-evidence/parked/`), because `checkout-clean-at-start` fails on it.
- `build/849-runs/setup.json` is present (`substrate setup` from 2026-10-23), and the frozen corpus is at `build/849-corpus`.
- No stale container pins the llama.cpp image (`docker ps -a --filter ancestor=<llama image>` is empty).
- `ARMS849_CACHE` is **unset**. A relative value broke host-gates once.

## Run

```bash
.venv/bin/python3 scripts/research/check_849_premerge.py --output ~/.local/share/kg-849-evidence/premerge-<sha>.json
```

## Read the result

- Every step passes. In particular `live-required-nodes` records 2 of 2 nodes passed (SC-001), and `live-smoke` and `live-down` pass (SC-002).
- The `live-required-nodes` `environment` shows `ARMS849_LIVE=1` and the four overrides at `127.0.0.1:16379` and `127.0.0.1:18080`.

## Verify (SC-003)

```bash
.venv/bin/python3 scripts/research/check_849_premerge.py --verify ~/.local/share/kg-849-evidence/premerge-<sha>.json
```

Accepted. Two mutated copies, one without `ARMS849_LIVE` and one without the overrides, are rejected. The unit test T-g covers this. Repeat it by hand only if T-g is in doubt.

## Then (out of this mission's scope)

Record `arms-preconditions-01M3FVRY#FR-015` with `spec-kitty agent acceptance-verdict`, then follow the `feat/849-preconditions` → main path in #1023.
