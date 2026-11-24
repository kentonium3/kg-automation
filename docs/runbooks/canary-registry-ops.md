---
title: Canary Registry Operations
doc_type: runbook
audience: agents_and_humans
status: approved
level: howto
created: 2026-07-11
last_validated: '2026-11-23'
last_updated: '2026-11-23'
updated_by: '#327 (felix-canary-registry-01KX8T7B) + #1063 (canary-deadman-backup-coverage-01M4XVY3) + #1133 (crash-loop-unit-alerting-01M858E8: crash-loop detection, pending deploy)'
version: v1.2
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
| `ledger/<YYYY-MM-DD>.jsonl` | Per-component **ledger** — one line per component per tick, recording **every** outcome (healthy / stale / failed / suppressed / gap / deduped), evidence, and timestamp (FR-008). Crash-loop scope, event and unverified lines are written here too ([Crash-loop detection](#crash-loop-detection)). | Appended, best-effort |
| `state/crash-loop.json` | Crash-loop state (#1133): per-unit generation, boot ID, restart-count history and open episode. | Atomically, after emit, every pass the stage runs |
| `state/crash-loop.lock` | Exclusive lock around the crash-loop stage's load, evaluate, emit and save. | Held during the stage |

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

## Crash-loop detection

> **Status: pending deploy.** This stage ships with mission
> `crash-loop-unit-alerting-01M858E8`
> ([#1133](https://github.com/kentonium3/kg-automation/issues/1133)). It goes
> live when `deploys/queued/crash-loop-unit-alerting.yaml` is applied, and
> that waits for Kent's approval of the merge to main. Until then the commands
> below find no `crash-loop` lines.

A unit under `Restart=always` that keeps crashing never reaches `failed`. It
spends most of its time `active` or `activating`, so the canary's "is it
active" probes read it as healthy. That is how the 2026-11-23 `obsidian-sync`
loop (39 restarts in 7 minutes) went unreported. The crash-loop stage runs once
in every canary pass, after the inventory components and coverage gaps. It reads
the **persistent restart counters**, which keep rising through the loop, so a
loop that starts and ends between two ticks still shows up. It is **detection
only**: it never restarts, stops or changes a unit. There is no LLM in the path.

### What it watches

Three scopes, read without sudo and without the journal:

| Scope | Watched | Counter | Read with |
|---|---|---|---|
| `system` | every loaded system service whose `Restart=` is not `no` | `NRestarts` | `systemctl list-units --type=service --all` + one `systemctl show -p Id,Restart,NRestarts,ActiveState,SubState,LoadState` |
| `user` | the same, in the `claude` user manager (the canary's own; no other user's manager is read) | `NRestarts` | the same two calls with `--user` |
| `container` | every docker container whose restart policy is not `no` | `RestartCount` | `docker ps -aq --no-trunc` + one `docker inspect --format` |

Units on the ignore list are left out. Units are keyed `system:<Id>`,
`user:<Id>` and `container:<name>` (the name without its leading `/`).

Each docker command runs with `DOCKER_CONFIG` set to a fresh empty temporary
directory, so the CLI loads no `config.json` and no registry credential, and
with `DOCKER_HOST=unix:///var/run/docker.sock`. The CLI still fetches each
container's full inspect object from the daemon; the canary process receives
only the five formatted fields (ID, name, restart count, restart policy,
status).

The three scopes share one read budget of 6 s (`read_budget_seconds`), and each
command gets at most 3 s of it. A normal read takes about 0.4 s.

### What pages

All crash-loop alerts go through the `#701` bus with `source` =
`felix-canary:crash-loop:<scope>:<name>` (the aggregate uses
`felix-canary:crash-loop:aggregate`).

| Event | Severity | When | Title |
|---|---|---|---|
| alert | ERROR | A proven crossing (below) opens an episode for the unit | `<name> crash-looping: <delta> restarts in <n> min` |
| re-remind | ERROR | The episode is still open, the last page is at least 6 h old, **and** a fresh crossing is proven on a baseline taken at or after that page | `still <name> crash-looping: …` |
| cleared | INFO | 2 consecutive quiet ticks (`quiet_ticks_to_clear`), about 30 minutes | `<name> crash loop cleared` |
| aggregate | ERROR, or INFO if it holds only cleared events | A tick has more than 3 events (`max_alerts_per_tick`): the first 3 go out on their own, the rest fold into one alert | `<n> more crash-loop events this tick` |

So a tick makes at most 4 crash-loop bus calls. Events are ordered alert, then
re-remind, then cleared, then by unit key. The aggregate's description names as
many units as fit in 900 characters. When not all fit, it ends with
`... and <k> more - see canary ledger <date>`. Every event, folded or not, gets its own ledger line.

A unit seen for the first time, a counter that went down (an operator
`systemctl restart`, `docker restart`), a container re-created under the same
name, and a reboot (a changed boot ID) all set a new baseline and never alert.
A reset in the middle of an episode counts as a quiet tick, so it can lead to
`cleared`. A reboot closes an open episode silently. When an episode clears,
its history is replaced by the current count, so a new episode needs new
restarts.

A failed delivery is **not retried** (the existing canary policy). It is
counted in `alerts_undelivered`, which makes the off-host dead-man ping `/fail`.

### The proven-crossing rule

The canary samples cumulative counters about every 15 minutes. Two samples
prove only that `delta` restarts happened somewhere in the time between them,
not when. So the stage splits that time into `m` parts, each no longer than the
window: `m = ceil(period / window_seconds)`. If
`delta ≥ m·(threshold − 1) + 1`, at least one part must hold `threshold`
restarts (pigeonhole), which proves "`threshold` restarts within one window".
Only a proven crossing pages. With the defaults (threshold 3, window 900 s) the
bound is `2m + 1`. The stage checks every stored baseline, not only the last
tick's, and reports the tightest proving interval.

Worked examples:

- **39 restarts over 16 minutes**: `m = ceil(960 / 900) = 2`, bound `2·2 + 1 =
  5`, and 39 ≥ 5. **Page.** This is the 2026-11-23 shape.
- **3 restarts over 16 minutes**: `m = 2`, bound 5, and 3 < 5. **No page.** The
  canary ledger gets one `crash-loop-unverified` line with the interval and the
  bound, and nothing is sent.

Ticks land 15 to 16 minutes apart, so `m` is normally 2 between consecutive
ticks, and a page on a single tick interval needs at least 5 restarts.

### Accepted limits

These follow from the 15-minute sampling cadence. They are deliberate and none
of them can cause a false page: every page is a proven crossing.

1. **A slow loop of 3 or 4 restarts per tick interval does not page on the tick
   where it first shows.** That tick writes `crash-loop-unverified`. If the
   loop keeps going, the longer interval proves itself: at 4 restarts per tick
   the page comes on about the 2nd tick (about 30 minutes), and at 3 per tick on
   about the 3rd (about 45 minutes), measured with ticks 15.5 to 16 minutes
   apart. A slow loop that stops before then never pages.
2. **A short burst split across a tick boundary can be missed.** For example, 4
   restarts in 2 minutes split 2 + 2 across two ticks proves nothing. A
   sustained loop is always caught.
3. **A failed delivery is not retried.** The dead-man reports it (`/fail`), and
   both ledgers record it (`delivered: false` on the canary line).
4. **During an alert storm the pass takes as long as the bus takes.** A pass
   with no events adds the read time (about 0.4 s, capped at 6 s). A pass that
   pages adds up to 4 bus calls, each normally under 1 s, with the bus's own
   ceiling at 15 s per call.

### Tuning

The config is `scripts/canary/crash_loop_config.json`, version-controlled in
this repo:

```json
{"threshold": 3, "window_seconds": 900, "quiet_ticks_to_clear": 2, "max_alerts_per_tick": 3, "read_budget_seconds": 6, "ignore": []}
```

| Field | Default | Valid | Meaning |
|---|---|---|---|
| `threshold` | 3 | integer 2–50 | Restarts that must be proven within one window |
| `window_seconds` | 900 | integer 60–3600 | The window |
| `quiet_ticks_to_clear` | 2 | integer ≥ 1 | Quiet ticks before `cleared` |
| `max_alerts_per_tick` | 3 | integer ≥ 1 | Individual alerts per tick before the rest fold into one aggregate |
| `read_budget_seconds` | 6 | integer 1–10 | The read budget for all three scopes |
| `ignore` | `[]` | list of `{"unit", "reason"}` | See below |

All six keys are required, and an unknown key is rejected. The file is read once
per pass, so a change takes effect on the next pass with no restart. An invalid
or unreadable file never falls back to defaults: every scope goes `unknown` with
evidence `could not check: config invalid: …`, and nothing is evaluated.

To change it, edit the file, check it locally, and commit through a normal pull
request. It reaches office2's checkout (`/home/claude/kg-automation`) through
the normal deploy pipeline. Never edit the office2 copy by hand.

```bash
python3 -c "from scripts.canary.crash_loop_model import load_config; print(load_config())"
```

### Ignore list

An entry is `{"unit": "<scope>:<name>", "reason": "<why>"}`:

```json
"ignore": [{"unit": "system:example.service", "reason": "restarts by design every 5 minutes; tracked in #NNNN"}]
```

- `reason` is required and must not be blank.
- Matching is **exact** on the unit key. There are no globs or prefixes. A
  container is keyed by its name without the leading `/`, and a systemd unit
  by its full `Id` including `.service`.
- A duplicate entry is rejected.
- An ignored unit is not stored and never alerts. Its count appears as
  `<i> ignored` in the scope's evidence.

### Reset

To start over, delete the state file. Do it between ticks, because a running
pass rewrites it after emitting:

```bash
ssh office2-claude 'systemctl --user is-active felix-canary.service; rm -f /data/services/felix-canary/state/crash-loop.json'
```

`is-active` should print `inactive` (no pass running). On the next pass every
unit is first-seen: it gets a baseline and **nothing alerts**, and any open
episode ends without a `cleared` message. Detection resumes from the pass after
that. A missing or corrupt file has the same effect, so a damaged file is never
a crash.

### Reading crash-loop ledger lines

```bash
# Every crash-loop line today (scopes, events, unverified rises):
ssh office2-claude 'jq -c "select(.component_id | startswith(\"crash-loop\")) | {evaluated_at, component_id, outcome, evidence}" /data/services/felix-canary/ledger/$(date -u +%Y-%m-%d).jsonl'

# Just the events and unverified rises, with their proof:
ssh office2-claude 'jq -c "select(.component_id | startswith(\"crash-loop\")) | select(.interval) | {evaluated_at, component_id, outcome, delivered, delta: .interval.delta, period_s: .interval.period_seconds, m: .interval.m, bound: .interval.bound}" /data/services/felix-canary/ledger/$(date -u +%Y-%m-%d).jsonl'

# Units currently in an open episode:
ssh office2-claude 'jq -c ".units | to_entries[] | select(.value.episode != null) | {unit: .key, episode: .value.episode}" /data/services/felix-canary/state/crash-loop.json'
```

Line types:

- **Scope lines**, `component_id` `crash-loop:system`, `crash-loop:user` or
  `crash-loop:container`: one each per pass. Outcome `healthy` with evidence
  `<n> watched, <i> ignored, <x> excluded, <ms> ms`, or `unknown` (see below).
  If a malformed entry was dropped from the state file, the system scope's
  evidence ends with `; state: …`.
- **Event lines**, `component_id` `crash-loop:<scope>:<name>`: `outcome` is
  `crash-loop`, `crash-loop-reremind` or `crash-loop-cleared`. They add
  `delivered` (bool) and `interval` = `{baseline_count, baseline_at,
  current_count, observed_at, delta, period_seconds, m, bound}`. Evidence is
  the alert title, with ` (in aggregate alert)` appended when the event was
  folded into the aggregate.
- **Unverified lines**: `outcome` `crash-loop-unverified`, `emitted: false`,
  `delivered: false`, plus `interval`. A rise of at least `threshold` that does
  not prove a crossing. No page.

A unit with no event writes no per-unit line; its history lives in
`crash-loop.json`. A dry run (`python3 -m scripts.canary.run --dry-run`) prints
the crash-loop lines it would write, but takes no lock, writes nothing and
sends nothing. `last-tick.json` is unchanged by this stage: its key set is the
same as before.

### Could-not-check

A scope that cannot be read completely is `unknown` and never reads as healthy.
It keeps every unit's stored state (a bad read never deletes coverage or an open
episode). It follows the canary's existing `unknown` rule: recorded at once,
paged as `crash-loop:<scope> health: unknown` (WARN) only once it persists past
the 6 h window, and `recovered` (INFO) when it reads again.

| Evidence after `could not check:` | Meaning | What to check |
|---|---|---|
| `config invalid: …` | The config failed validation; all three scopes are `unknown` and nothing is evaluated | The named field in `scripts/canary/crash_loop_config.json` |
| `boot id unreadable` | `/proc/sys/kernel/random/boot_id` could not be read; all three scopes are `unknown` | The host itself; this file is always world-readable |
| `read deadline exceeded` | The 6 s budget ran out before or while this scope was read | `systemctl show` or `docker inspect` timing; a hung docker daemon |
| `systemctl list-units: …` / `systemctl show: …` | The system-manager call failed, timed out (`timed out after 3.0s`), or returned output that does not match what was asked for | Run the same command by hand as `claude` |
| `systemctl --user …: …` | The same for the user manager. `exit 1: Failed to connect to bus` means `XDG_RUNTIME_DIR` or `DBUS_SESSION_BUS_ADDRESS` did not reach the canary | `loginctl show-user claude -p Linger`; the unit's environment |
| `docker ps: …` / `docker inspect: …` | The docker call failed or timed out | `docker info` as `claude`; group membership; the daemon |
| `missing requested containers` / `show output missing requested units` / `duplicate …` / `malformed …` | The output did not match what was asked for (often a unit or container that changed during the read) | Usually clears on the next tick; if it persists, the named unit |
| `<scope> reader crashed: …` | An unexpected fault in one scope's reader; the other scopes still ran | The exception text; file a bug |

A fault in the stage as a whole never aborts the pass. It is appended to
`errors[]` in `last-tick.json` (so `status` is `error` and the dead-man pings
`/fail`), and every other component is still evaluated:

- `crash_loop:locked`: another run held `crash-loop.lock`, so the stage was
  skipped for that pass. This is harmless once; if it repeats, look for a stuck
  manual run.
- `crash_loop:<Exception>:<message>`: an unexpected fault. File a bug.
- `crash_loop_state_save:…`: the state could not be saved after emitting. The
  next tick repeats the page. Check the disk and the directory's permissions.

### 7-day acceptance check

Run this 7 days after `deploys/queued/crash-loop-unit-alerting.yaml` is
applied (felix-deployer numbers it on apply; see the applied record under
`deploys/applied/`) (research R-14 of the mission; SC-003, NFR-004, NFR-005). Every command
is read-only. Run them from your own terminal.

**Step 1. Find the start date.** It is the UTC date of the first `crash-loop:system`
line:

```bash
ssh office2-claude 'grep -l "\"crash-loop:system\"" /data/services/felix-canary/ledger/*.jsonl | head -1'
```

Set `SINCE` to that file's date (`YYYY-MM-DD`) in the commands below.

**Step 2. Check 1: every page was a proven crossing (SC-003, NFR-004).** This reads
the canary ledger, the alert-bus ledger and the deployed config. Each
crash-loop alert, re-remind and cleared entry in the alert-bus ledger must
have its canary ledger line, and each aggregate's count must match its
folded lines. Each alert and re-remind line must satisfy
`delta ≥ m·(threshold−1)+1` with `m = ceil(period_seconds / window_seconds)`.
The pass condition is zero violations:

```bash
ssh office2-claude 'SINCE=YYYY-MM-DD python3 -I -' <<'EOF'
import json, math, os
from collections import Counter
from datetime import datetime
from pathlib import Path

since = os.environ["SINCE"]
canary_dir = Path(os.environ.get("CANARY_LEDGER", "/data/services/felix-canary/ledger"))
bus_dir = Path(os.environ.get("BUS_LEDGER", "/data/services/alert-bus/ledger"))
config_path = os.environ.get("CRASH_LOOP_CONFIG", "/home/claude/kg-automation/scripts/canary/crash_loop_config.json")
config = json.loads(Path(config_path).read_text())
n, window = config["threshold"], config["window_seconds"]


def records(directory):
    for path in sorted(directory.glob("*.jsonl")):
        if path.stem >= since:
            for line in path.read_text().splitlines():
                if line.strip():
                    yield json.loads(line)


def at(text):
    return round(datetime.fromisoformat(text).timestamp(), 3)


KIND = {"crash-loop": "alert", "crash-loop-reremind": "reremind", "crash-loop-cleared": "cleared"}
FOLDED = "(in aggregate alert)"
events = [r for r in records(canary_dir) if r.get("outcome") in KIND]
violations = []
for r in events:
    if r["outcome"] == "crash-loop-cleared":
        continue
    i = r["interval"]
    m = max(1, math.ceil(i["period_seconds"] / window))
    if i["m"] != m or i["bound"] != m * (n - 1) + 1 or i["delta"] < i["bound"]:
        violations.append(f"NOT PROVEN {r['component_id']} at {r['evaluated_at']}: {i}")
individual = {
    (r["component_id"], KIND[r["outcome"]], at(r["evaluated_at"]))
    for r in events
    if not r["evidence"].endswith(FOLDED)
}
folded = Counter(at(r["evaluated_at"]) for r in events if r["evidence"].endswith(FOLDED))
checked = 0
for b in records(bus_dir):
    if not b.get("source", "").startswith("felix-canary:crash-loop:"):
        continue
    details = b.get("details", {})
    kind = details.get("kind")
    if kind == "aggregate":
        checked += 1
        lines = folded.get(at(b["ts"]), 0)
        if lines != int(details["count"]):
            violations.append(f"AGGREGATE MISMATCH at {b['ts']}: count {details['count']}, canary lines {lines}")
    elif kind in ("alert", "reremind", "cleared"):
        checked += 1
        if (details.get("component_id"), kind, at(b["ts"])) not in individual:
            violations.append(f"NO CANARY LINE for bus {kind} {details.get('component_id')} at {b['ts']}")
print(f"config: threshold {n}, window {window} s")
print(f"canary event lines: {len(events)}; crash-loop bus entries checked: {checked}; violations: {len(violations)}")
for v in violations:
    print(" ", v)
print("PASS" if not violations else "FAIL")
EOF
```

The last line is `PASS` or `FAIL`. Every violation is printed above it.

**Step 3. Check 2a: the canary unit never failed (NFR-005).** The user journal of
`felix-canary.service` should show no non-zero exit:

```bash
ssh office2-claude 'journalctl --user -u felix-canary.service --since YYYY-MM-DD --no-pager | grep -E "Failed with result|status=[0-9]+/" || echo "no failed runs"'
```

Then count the passes that finished with `status=error`:

```bash
ssh office2-claude 'journalctl --user -u felix-canary.service --since YYYY-MM-DD --no-pager | grep -c "status=error"'
```

The journal records only the error **count** per pass (`errors=<n>`). The
error text is kept only for the latest pass, in `last-tick.json`. So a
non-zero count here cannot by itself show whether a `crash_loop:` error
occurred. Explain each one from check 2b (a pass where the stage faulted
before routing has no scope lines) and from the dead-man's `/fail` history
on healthchecks.io. Also check the latest pass:

```bash
ssh office2-claude 'jq -c ".errors" /data/services/felix-canary/state/last-tick.json'
```

**Step 4. Check 2b: every pass ran the stage (NFR-005).** Every daily file must have
scope lines at the 15-minute cadence (about 96 per scope per day, fewer on
the start day), with no gap over 1200 s, and every scope line `healthy`:

```bash
ssh office2-claude 'SINCE=YYYY-MM-DD python3 -I -' <<'EOF'
import json, os
from datetime import datetime
from pathlib import Path

since = os.environ["SINCE"]
ledger = Path(os.environ.get("CANARY_LEDGER", "/data/services/felix-canary/ledger"))
scopes = ("crash-loop:system", "crash-loop:user", "crash-loop:container")
seen = {scope: [] for scope in scopes}
not_healthy = []
for path in sorted(ledger.glob("*.jsonl")):
    if path.stem < since:
        continue
    per_day = dict.fromkeys(scopes, 0)
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        scope = r.get("component_id")
        if scope in seen:
            per_day[scope] += 1
            seen[scope].append(datetime.fromisoformat(r["evaluated_at"]))
            if r["outcome"] != "healthy":
                not_healthy.append(f"{r['evaluated_at']} {scope} {r['outcome']}: {r['evidence']}")
    print(path.stem, " ".join(f"{s.split(':')[1]}={c}" for s, c in per_day.items()))
gaps = []
for scope, times in seen.items():
    times.sort()
    for a, b in zip(times, times[1:]):
        if (b - a).total_seconds() > 1200:
            gaps.append(f"{scope}: {a.isoformat()} -> {b.isoformat()}")
print(f"gaps over 1200 s (a missed tick): {len(gaps)}")
for g in gaps:
    print(" ", g)
print(f"scope lines not healthy: {len(not_healthy)}")
for u in not_healthy:
    print(" ", u)
print("PASS" if not gaps and not not_healthy else "INVESTIGATE")
EOF
```

`PASS` means no gap and no non-healthy scope line. `INVESTIGATE` lists
each one. A gap can have an innocent cause (a reboot, a planned stop), so
explain each one rather than treating it as a failure.

**Step 5. Record the result** as a comment on
[kentonium3/kg-automation#1133](https://github.com/kentonium3/kg-automation/issues/1133).
Give the window (`SINCE` to the date you ran it), the check 1 summary line
and verdict, the check 2a counts, the check 2b gap and non-healthy counts,
an explanation of anything flagged, and the overall result: pass, or the
follow-up issue you opened.

### Scope boundary

Detecting drift between a deployed unit file and its repo copy is out of scope
here (mission constraint C-006). Follow-up:
[kentonium3/kg-automation#1138](https://github.com/kentonium3/kg-automation/issues/1138).

## Cross-references

- **Spec / plan / research**: `kitty-specs/felix-canary-registry-01KX8T7B/` (`spec.md`, `plan.md`, `research.md`, `quickstart.md`).
- **Alert bus**: [`alerting.md`](<./alerting.md>) — the `#701` `felix-alert` bus this runner emits through.
- **Sibling scanner**: [`trust-reporting-detector.md`](<./trust-reporting-detector.md>) — `felix-trust-scan`, the trust-drift sibling sharing the emit substrate.
- **Backup canary (first dogfood)**: [`restic-backup-ops.md`](<./restic-backup-ops.md>) — the `last-backup.json` freshness pointer this runner reads.
- **Status contract**: [ADR-0006](<../design/architecture/adr/0006-felix-component-lifecycle-status-contract.md>) — status-gates-health.
- **Service entry**: `docs/design/architecture/data/service-inventory.json` → `felix-canary` (WP05); narrative in [`service-inventory.md`](<../design/architecture/service-inventory.md>).
- **Deploy manifest**: `deploys/queued/0017-felix-canary-registry.yaml` (entrypoint `scripts/deploy/deploy-felix-canary.py`).
- **Issue**: [#327](https://github.com/kentonium3/kg-automation/issues/327).
- **Crash-loop detection**: mission `kitty-specs/crash-loop-unit-alerting-01M858E8/` (`spec.md`, `plan.md`, `research.md`, `contracts/crash-loop-alert.md`); config `scripts/canary/crash_loop_config.json`; deploy manifest `deploys/queued/crash-loop-unit-alerting.yaml` (pending); issue [#1133](https://github.com/kentonium3/kg-automation/issues/1133); unit-file drift follow-up [#1138](https://github.com/kentonium3/kg-automation/issues/1138).
