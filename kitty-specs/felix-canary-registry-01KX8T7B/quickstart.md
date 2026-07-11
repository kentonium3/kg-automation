# Quickstart: Felix component-health canary registry

## Run a pass locally (no side effects)

```
python3 -m scripts.canary.run --dry-run
```
Prints each component's computed `health` + evidence; emits nothing, mutates no state.

## Self-check (config + bus reachability)

```
python3 -m scripts.canary.run --self-check
```
Prints `status=ok` when `service-inventory.json` is readable and the alert-bus lib is importable.

## Add a canary (declare a health_check)

A component becomes a canary purely by declaring a `health_check` in
`docs/design/architecture/data/service-inventory.json` — there is no separate registry file.

- Liveness (process/http): `method: http|shell`, `endpoint`, `expected`, `timeout_seconds`.
- Freshness (scheduled job): `method: tick-signal-file`, `state_path` (the pointer), and
  **`max_age_seconds`** (the staleness bound). Set `status: active`/`running` to be alert-eligible;
  `suspended`/`deprecated`/`planned`/`retired` are evaluated but never alerted (ADR-0006).

## Verify the success criteria

| SC | How to verify |
|----|----------------|
| SC-001 | Break an active component's check (e.g. stop a timer / age its pointer past `max_age_seconds`); confirm an error alert reaches the phone within ~15 min. |
| SC-002 | Set a component `status: suspended`, age its pointer; confirm **zero** alerts. |
| SC-003 | Run `--dry-run`; confirm every active/running component with a `health_check` appears; confirm any active component lacking a usable `health_check` is listed as a coverage gap. |
| SC-004 | Leave a component broken across several ticks; confirm one alert per dedup window (default 6 h), not per tick. |
| SC-005 | Edit `last-backup.json` `snapshot_timestamp_utc` to 5 days ago; confirm a `stale` alert (the #511 dogfood). |
| SC-006 | Crash path: `systemctl --user kill felix-canary.service` mid-run → confirm the `OnFailure` out-of-band alert. (Total-silence/dead-timer detection is #269, deferred — see research R8.) |

## Deploy to office2

1. Land the mission to `main` (post-merge Codex first).
2. `deploys/queued/00NN-felix-canary-registry.yaml` is picked up by felix-deployer: installs
   `felix-canary.service`+`.timer` (15-min) + `OnFailure` shim, wires the alert-bus `EnvironmentFile`,
   `daemon-reload`, runs `--self-check` + `--dry-run` gate, enables the timer, and **rebaselines** the
   audited systemd surface.
3. Verify live: `systemctl --user list-timers felix-canary.timer`, one real `--once` run, then SC-001…006.

## Ops

Runbook: `docs/runbooks/canary-registry-ops.md` — where it runs, the state files
(`/data/services/felix-canary/state/`), how to read the tick-signal, how to silence a component
(suspend it), and how to add/adjust a canary.
