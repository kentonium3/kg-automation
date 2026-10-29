---
title: Canary Registry Operations
doc_type: runbook
audience: agents_and_humans
status: approved
level: howto
created: 2026-07-11
last_validated: '2026-10-14'
last_updated: '2026-10-14'
updated_by: '#327 (felix-canary-registry-01KX8T7B) + #1063 (canary-deadman-backup-coverage-01M4XVY3)'
version: v1.1
owners: [kgale]
---

# Canary Registry Operations

The **component-health canary** for office2. A deterministic, scheduled runner
that reads every service's declared `health_check` from `service-inventory.json`,
computes each component's health per ADR-0006, and alerts — via the `#701`
`felix-alert` bus — when a *live* component is stale, failed, or un-evaluable.
It is the missing middle piece between "components already declare how to check
their health" and "the alert bus already exists": the thing that actually
evaluates those checks on a schedule so Felix stops failing silently.

There is **no separate canary registry file** — a component becomes a canary
purely by declaring a `health_check` in the inventory (constraint C-001). The
runner has **no LLM in its path** (0 tokens/tick, NFR-003).

## Overview

| | |
|---|---|
| Governing spec | `kitty-specs/felix-canary-registry-01KX8T7B/spec.md` (issue [#327](https://github.com/kentonium3/kg-automation/issues/327), Foundation 1 / Epic #516) |
| Governing contract | [ADR-0006](<../design/architecture/adr/0006-felix-component-lifecycle-status-contract.md>) — component lifecycle status (status-gates-health) |
| Alert substrate | The `#701` unified alert bus ([alerting.md](<./alerting.md>)); INV-003 — one canonical alert stream |
| Coherence | Sibling scanner to `felix-trust-scan` (health vs trust are different domains); [decisions.jsonl](<../design/coherence/decisions.jsonl>) `DEC-007` |
| First concrete canary | The restic backup (`last-backup.json` freshness — the #511 dogfood) |

Two health *modes*, both derived from the declared `health_check`:

- **Liveness** — is the thing up / responding *now*? (`http`, `shell`,
  `systemd-status`, `self-check-command`/`self-test`). A non-zero exit or a
  wrong HTTP status is `failed`.
- **Freshness** — did the scheduled thing run *recently enough*? (`state-file`
  / `tick-signal-file` / `signal-file`, plus `log-tail`/`journal`). The probe
  reads the pointer's authoritative timestamp and compares its age to
  `max_age_seconds`. Past the bound is `stale`.

## Where it runs

office2, as a `systemd --user` timer under the `claude` user — the same
structural template and cadence as `felix-trust-scan`.

| Unit | Role |
|---|---|
| `felix-canary.timer` | 15-minute cadence (`OnUnitActiveSec=15min`, `OnBootSec=5min`) |
| `felix-canary.service` | `Type=oneshot`; runs `/usr/bin/python3 -m scripts.canary.run --once` from `/home/claude/kg-automation` |
| `felix-canary-onfailure.service` | The `OnFailure=` shim — fires an out-of-band ERROR via `scripts/common/alert_bus.sh` **only** when `felix-canary.service` exits non-zero (SC-006 crash detection, independent of the runner's own emit logic) |

Canonical unit sources live at `scripts/office2/felix-canary.{service,timer}` and
`scripts/office2/felix-canary-onfailure.service`; they are installed into
`~/.config/systemd/user/` by the deploy entrypoint
`scripts/deploy/deploy-felix-canary.py` (manifest `deploys/queued/0017-felix-canary-registry.yaml`).
The `.service` loads `EnvironmentFile=-/home/claude/.config/felix/alert-bus/env`
for the ntfy topic (leading `-` keeps startup non-fatal if the topic file is
absent — the bus returns `NTFY_MISSING_TOPIC` rather than failing the run).

```bash
# Is the timer scheduled?
ssh office2-claude 'systemctl --user list-timers felix-canary.timer'
# Run one pass right now (writes state + emits like a real tick):
ssh office2-claude 'systemctl --user start felix-canary.service'
# Was the last run clean? (a runner-level fault shows as a failed service)
ssh office2-claude 'systemctl --user status felix-canary.service'
```

## State & ledger files

All under `/data/services/felix-canary/`. Every write is **atomic** (temp file
in the same directory + `os.replace`) so a crash mid-write never leaves a
partial/corrupt file.

| Path | What | Written |
|---|---|---|
| `state/last-tick.json` | Aggregate **tick-signal** — the runner's own health pointer (FR-010). One object, overwritten each tick. | Atomically, every tick |
| `state/dedup.json` | Dedup state: `component_id -> {last_outcome, last_emitted_utc}`. Drives once-per-window paging. | Atomically, every tick |
| `ledger/<YYYY-MM-DD>.jsonl` | Per-component **ledger** — one line per component per tick, recording **every** outcome (healthy / stale / failed / suppressed / gap / deduped), evidence, and timestamp (FR-008). | Appended, best-effort |

### `last-tick.json` schema

```json
{
  "status": "success",
  "completed_at_utc": "2026-07-11T15:30:00+00:00",
  "components_evaluated": 24,
  "emitted": 1,
  "suppressed_dedup": 2,
  "coverage_gaps": 3,
  "suppressed_status": 5,
  "errors": [],
  "duration_ms": 812
}
```

- `status` — `success` when `errors` is empty, else `error`. A `status: error`
  here is a *within-pass* degradation (e.g. a ledger write hiccup), **not** a
  crashed run — the process still exited 0.
- `completed_at_utc` — the freshness anchor WP05 registered as the runner's own
  `health_check` (`state-file`, `max_age_seconds` covering ~2 missed ticks).
- `suppressed_status` — components gated off by declared status (never probed).
- `coverage_gaps` — live components with no usable `health_check`.
- `errors[]` — per-component fault strings (`evaluate:<id>:...`, `ledger:<id>:...`);
  never a whole-pass abort (NFR-004).

### Ledger line schema

```json
{"component_id":"restic-backup","outcome":"healthy","evidence":"ts snapshot_timestamp_utc=… age 3600s vs max_age 100800s → fresh","emitted":false,"suppressed_dedup":false,"evaluated_at":"2026-07-11T15:30:00+00:00"}
```

`outcome` is one of `healthy` / `stale` / `failed` / `degraded` / `unknown` /
`suppressed` / `gap`. `emitted` records whether this outcome actually paged this
tick; `suppressed_dedup` records that it was held (inside the window, or a
first-seen unknown/gap pending persistence).

## Reading a tick

```bash
# Aggregate: did the last pass complete, and what did it emit?
ssh office2-claude 'cat /data/services/felix-canary/state/last-tick.json | jq .'

# Per-component: what did each component say this tick?
ssh office2-claude 'cat /data/services/felix-canary/ledger/$(date -u +%Y-%m-%d).jsonl | jq -c "{component_id, outcome, emitted}"'

# Just the ones that paged today:
ssh office2-claude 'jq -c "select(.emitted==true)" /data/services/felix-canary/ledger/$(date -u +%Y-%m-%d).jsonl'
```

An **offline preview** (evaluates with the real probes but writes nothing and
emits nothing) is the fastest "what would the canary say?" check:

```bash
ssh office2-claude 'cd /home/claude/kg-automation && python3 -m scripts.canary.run --dry-run'
```

## Adding or adjusting a canary

A component is monitored the instant it declares an evaluable `health_check` in
`docs/design/architecture/data/service-inventory.json` — there is nothing else
to register.

- **Freshness (a scheduled job):** `method: state-file` (or `tick-signal-file` /
  `signal-file`), `state_path` pointing at the pointer JSON, and
  **`max_age_seconds`** (the staleness bound). Without `max_age_seconds` the
  probe falls back to *liveness only* (pointer readable ⇒ ok) and cannot detect
  staleness — the WP01 validator warns on the omission.
- **Liveness (a service/endpoint):** `method: http` (+ `endpoint`, `expected`,
  `timeout_seconds`) or `method: shell` / `systemd-status` (+ `endpoint` command).

The freshness probe resolves the pointer's timestamp by trying an ordered list
of candidate keys (`completed_at_utc`, `snapshot_timestamp_utc`, `timestamp`, …
in `scripts/canary/probes.py:TIMESTAMP_KEYS`) — **do not** special-case a
component name; if a pointer uses a new timestamp key, add it to that list. A
pointer shape the probe cannot interpret (a bare fingerprint map, a JSONL log)
reads as an honest `unknown`, never a false `healthy`.

> **Note on ownership:** `service-inventory.json` is edited under the
> architecture-docs change-control protocol (JSON is authoritative; update the
> [`service-inventory.md`](<../design/architecture/service-inventory.md>)
> narrative in the same change). Editing the inventory is a Tier 2/3 change, not
> a canary code change.

## Silencing a component (suppress, don't patch)

A noisy or expected-down component is silenced by **changing its declared
status**, never by editing canary code. Per ADR-0006, only `active`/`running`
components are alert-eligible; setting a component's `status` to `suspended`
(or `deprecated`/`planned`/`retired`) makes the runner **gate it before probing**
— it is recorded as `suppressed` in the ledger and never emits. A suspended
backup that hasn't run is *expected*, not an incident (SC-002).

```jsonc
// in service-inventory.json — the ONLY correct way to silence a canary
{ "id": "some-service", "status": "suspended", "health_check": { … } }
```

This is the single suppression rule (FR-003, gate-before-probe). Do not comment
out probes, add allowlists, or special-case IDs in `scripts/canary/` — that
would drift the code from the inventory's single source of truth.

## Alert types & severities

Alerts emit through the `#701` bus (`scripts/common/alert_bus/`) with `source`
= `felix-canary:<component_id>`. Severity maps by outcome:

| Outcome | Severity | Meaning |
|---|---|---|
| `failed` | ERROR | An evaluable check said *not ok* (non-zero exit, wrong HTTP status, explicit error in a pointer). |
| `stale` | ERROR | Freshness bound exceeded — the pointer's timestamp is older than `max_age_seconds`. |
| `degraded` | WARN | A self-reported partial-health signal. (No probe emits this today; the mapping is retained for future probes.) |
| `unknown` (persistent) | WARN | A probe could not run conclusively. See the timing rule below. |
| `gap` (coverage gap, persistent) | WARN | A live component declares no usable `health_check` (`method: none`, missing/empty, or an unhandled method) — "we thought we were watching it but weren't." |
| recovery | INFO | A component transitioned back to `healthy` from a prior bad outcome. |

### Timing rules

- **`failed` / `stale` / `degraded` page immediately** on first sight, then
  re-page **once per dedup window** (default 6 h) while unchanged. A continuing
  failure does not re-page every tick (FR-005 / SC-004).
- **`unknown` and `gap` are recorded but NOT paged on first sight** (F5). They
  page only once they have *persisted past the dedup window* — a live component
  we can't even evaluate is itself a signal, but a single-tick blip shouldn't
  page. After that, once per window like any other bad outcome.
- **Any transition emits** (dedup is keyed on `component_id` + `last_outcome`),
  so `failed → healthy → failed` produces all three alerts — a re-failure after
  a recovery is never swallowed by a stale suppression window (INV-F).

## Troubleshooting

**"A component is stuck `unknown` / persistently paging WARN."**
The probe cannot interpret its pointer or run its check conclusively. Check the
ledger `evidence` for that `component_id` — it names *why* (e.g. "no
interpretable timestamp key", "freshness pointer is not a JSON object"). This is
correct, honest behavior for a pointer shape the probe doesn't yet handle; the
fix is either to declare a usable `health_check` or to extend the probe
(`TIMESTAMP_KEYS` / a new handler), not to silence it.

**"A live component isn't being watched (`coverage_gaps` > 0)."**
Some `active`/`running` service declares `method: none`, an empty
`health_check`, or a method the runner doesn't handle. Find it in the ledger
(`outcome: "gap"`, evidence names the reason) and give it a real `health_check`.

**"The whole pass shows `status: error`."**
`errors[]` in `last-tick.json` lists the per-component faults. A single probe
fault never aborts the pass (NFR-004) — the component records `unknown` and
evaluation continues. Investigate the named component; the pass itself is fine.

**"The service unit went `failed` (systemctl)."**
That is a **runner-level** fault (inventory unreadable, state dir unwritable) —
the process exited non-zero, which fired the `OnFailure` shim and paged an
out-of-band ERROR. Read `journalctl --user -u felix-canary.service` for the
cause; a healthy-but-unhealthy-components pass exits 0 and never does this.

## Self-observability boundary (honest scope)

The canary watches other components; watching *the canary itself* is only
partially in scope here — stated plainly so no one over-trusts it:

- **A crashing run is covered.** `felix-canary.service` declares
  `OnFailure=felix-canary-onfailure.service`, so a non-zero exit fires an
  out-of-band ERROR independent of the runner's own emit logic (SC-006).
  `felix-trust-scan` lacked this; the canary adds it.
- **A dead timer is covered by felix-health-check (#1063).** A dead process
  cannot report itself: from 2026-09-27 to 2026-10-14 this timer was dormant
  (#1062) and nothing noticed. `felix-health-check`, an independent calendar
  timer, now evaluates this runner's `last-tick.json` declaration twice a day
  through the canary's own evaluator. The declaration carries a `key_ledger`
  (#1063): `status` must be `success`, `completed_at_utc` is the anchor with no
  fallback timestamp, and `components_evaluated` must be ≥ 1, so a runner that
  ticks without doing anything does not read as alive. The canary in turn
  watches the health check's `last-run.json` (#891), so each watches the other.
- **Whole-host silence is covered off-host (#1077).** If office2 is down, or
  the shared ntfy topic is lost, both watchers go quiet together. Each now
  pings a hosted healthchecks.io check, which emails Kent when the pings stop;
  see [Off-host dead-man pings](#off-host-dead-man-pings-1077). The separate
  Felix/OpenClaw outage watchdog is [#269](https://github.com/kentonium3/kg-automation/issues/269).

## Off-host dead-man pings (#1077)

The canary and felix-health-check each ping their own
[healthchecks.io](https://healthchecks.io) check after every run, via
`scripts/common/deadman.py`. When a check misses its window, or a `/fail`
arrives, healthchecks.io **emails** Kent, never through ntfy. Decided in RFC
[#1069](https://github.com/kentonium3/kg-automation/issues/1069).

| Check | Env variable | Schedule on healthchecks.io |
|---|---|---|
| `felix-canary` | `FELIX_DEADMAN_CANARY_URL` | Simple: period 15 min, grace 45 min |
| `felix-health-check` | `FELIX_DEADMAN_HEALTHCHECK_URL` | Cron `0 11,23 * * *`, timezone UTC, grace 1 h. This matches `felix-health-check.timer`'s `OnCalendar`, which uses host-local time; office2 is `Etc/UTC`. If the host timezone ever changes, change the check's timezone too. |

**What a ping means.** A run pings `success` only when the watcher did its own
work and the felix-alert channel could deliver. It does **not** mean
everything it watches is healthy. It pings `/fail` when any of these holds:
- the run hit an execution fault: the canary pass errored or raised, or the
  health-check script was missing or timed out, or coverage could not run;
- `FELIX_ALERT_NTFY_TOPIC` is missing;
- the read-only `ntfy /v1/health` probe failed;
- an alert this run tried to send was not delivered.

Dry runs and `--self-check` never ping.

**Secret handling.** Each URL is a capability: anyone holding it can mark the
check up or down. The URLs live only in `/home/claude/.config/felix/deadman/env`
(claude:claude, 0600). They are never put in an environment variable, never
passed on a command line (curl reads the URL on stdin), and never logged.
Without that file every ping is a silent no-op (`unconfigured`). Template:
`scripts/common/deadman.env.sample`.

### Provision or rotate

From your own terminal (the values are never echoed):

```bash
ssh -t office2-claude 'umask 077; mkdir -p ~/.config/felix/deadman; read -rsp "canary ping URL: " C; echo; read -rsp "health-check ping URL: " H; echo; printf "FELIX_DEADMAN_CANARY_URL=%s\nFELIX_DEADMAN_HEALTHCHECK_URL=%s\n" "$C" "$H" > ~/.config/felix/deadman/env'
```

To rotate, regenerate the ping URL in healthchecks.io and run the same
one-liner again. The remote command relies on bash's `read -rsp`; `claude`'s
login shell on office2 is `/bin/bash`, verified 2026-10-15.

### Verify

```bash
ssh office2-claude 'journalctl --user -u felix-canary.service --since -20min | grep deadman'
```

The output should show `deadman canary success: ok`, and the check should
read "up" on the healthchecks.io dashboard. To test the failure email
deliberately:

```bash
ssh office2-claude 'cd ~/kg-automation && python3 -m scripts.common.deadman --label canary --outcome fail'
```

You should get an email. The next real tick returns the check to "up".

### Reading a `fail` email

Check the journal of the watcher whose check failed:

```bash
ssh office2-claude 'journalctl --user -u felix-canary.service --since -1h | grep deadman'
```

```bash
ssh office2-claude 'journalctl --user -u felix-health-check.service --since -13h | grep deadman'
```

In the canary journal the reason follows `deadman channel:`. In the health-check
journal it follows `deadman fail reason:`.

Reasons:
- `topic_missing`: fix `~/.config/felix/alert-bus/env`.
- `ntfy_unhealthy` or `probe_error`: ntfy, or the network path to it, is down.
- `undelivered`: an alert failed; see the felix-alert ledger under
  `/data/services/alert-bus/ledger/`.
- An execution fault (the canary status line shows `status=error`, or the
  health check logs `deadman fail reason: ...`).

A *missed-ping* email (no `/fail`) means the watcher did not run at all: host
down, user manager down, timer dormant, or a broken checkout.

### Planned downtime

Pause both checks in healthchecks.io before planned office2 maintenance, and
resume them afterwards.

### Accepted residuals

- A revoked or mistyped topic on a healthy ntfy server is caught only when
  the next real alert fails to deliver.
- Losing both attempts of one ping produces one false email; the next run
  clears it.

## Cross-references

- **Spec / plan / research**: `kitty-specs/felix-canary-registry-01KX8T7B/` (`spec.md`, `plan.md`, `research.md`, `quickstart.md`).
- **Alert bus**: [`alerting.md`](<./alerting.md>) — the `#701` `felix-alert` bus this runner emits through.
- **Sibling scanner**: [`trust-reporting-detector.md`](<./trust-reporting-detector.md>) — `felix-trust-scan`, the trust-drift sibling sharing the emit substrate.
- **Backup canary (first dogfood)**: [`restic-backup-ops.md`](<./restic-backup-ops.md>) — the `last-backup.json` freshness pointer this runner reads.
- **Status contract**: [ADR-0006](<../design/architecture/adr/0006-felix-component-lifecycle-status-contract.md>) — status-gates-health.
- **Service entry**: `docs/design/architecture/data/service-inventory.json` → `felix-canary` (WP05); narrative in [`service-inventory.md`](<../design/architecture/service-inventory.md>).
- **Deploy manifest**: `deploys/queued/0017-felix-canary-registry.yaml` (entrypoint `scripts/deploy/deploy-felix-canary.py`).
- **Issue**: [#327](https://github.com/kentonium3/kg-automation/issues/327).
