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

Each docker command runs with `DOCKER_CONFIG` set to a directory that cannot
exist, `/proc/nonexistent-felix-canary-docker-config`, so the CLI loads no `config.json` and no
registry credential, and with `DOCKER_HOST=unix:///var/run/docker.sock`.
Nothing is created there, so a read (a dry run included) writes nothing. If the
CLI ever tried to create the directory, the command would fail and the
container scope would report could-not-check. The CLI still fetches each
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

`period` is never shorter than the true time between the two samples. The stage
reads the wall clock just before and just after it reads the counters. It
stores each sample at the earlier reading (`baseline_at`) and measures the
period to the later reading (`observed_at`). A slow probe earlier in the pass,
or a slow read, can therefore only lengthen `period` and raise the bound. It can
never make a page out of restarts that were spread too thinly to prove one. If
either reading is not later than a unit's newest stored sample (the clock
stepped back, or two reads overlapped), the unit's history is replaced by this
sample alone and nothing is sent for it that tick. An open episode stays open.
No sample from before the clock step is kept, so no later proof can span it.
Neither time is the pass's start time (`evaluated_at`).

Worked examples:

- **39 restarts over 16 minutes**: `m = ceil(960 / 900) = 2`, bound `2·2 + 1 =
  5`, and 39 ≥ 5. **Page.** This is the 2026-11-23 shape.
- **3 restarts over 16 minutes**: `m = 2`, bound 5, and 3 < 5. **No page.** The
  canary ledger gets one `crash-loop-unverified` line with the interval and the
  bound, and nothing is sent.

Ticks land 15 to 16 minutes apart, so `m` is normally 2 between consecutive
ticks, and a page on a single tick interval needs at least 5 restarts.

### Detection envelope and accepted limits

Every page is a proven crossing, so none of these limits can cause a false
page. They can cause a **miss**. They follow from two of Kent's decisions:
15-minute sampling, and the rule of 3 restarts within 15 minutes. Whether to
accept them is Kent's call. They are listed under "Surfaced judgment calls" in
the mission's `plan.md`, and loosening them is a change to the proof
predicate in `evaluate_tick`.

**What is caught.** A unit pages when, for some stored baseline, the rise
since that baseline is at least `m·(threshold−1)+1`, where `m` is the number
of windows the interval spans. With the defaults, and ticks 15.5 to 16
minutes apart, that means:

- **A burst** of 5 or more restarts between two ticks pages on that tick.
- **A steady loop of 4 restarts per tick** pages on about the 2nd tick (about
  30 minutes). **A steady 3 per tick** pages on about the 3rd (about 45
  minutes). A slow loop that stops before then never pages.

**What is not caught.** These are the accepted limits:

1. **A steady loop averaging 2 or fewer restarts per tick interval never
   pages, however long it runs**, unless one tick interval holds a burst of 5 or
   more. Over `k` ticks the bound is about `2k + 3`, so
   it grows as fast as the rise. Simulated with the shipped `evaluate_tick`, a
   steady +2 every 930 s gave zero events across 120 ticks (30 hours). Such a
   loop can still meet the real rule ("3 within 15 minutes") when its restarts
   cluster, but the samples can never prove it. It is not silent: once the
   rise since a baseline reaches 3, every tick writes a `crash-loop-unverified`
   line. **Nothing pages on those lines**, so a slow loop shows only if someone
   reads the ledger (see [Reading crash-loop ledger
   lines](#reading-crash-loop-ledger-lines)).
2. **A short burst split across a tick boundary can be missed.** For example, 4
   restarts in 2 minutes split 2 + 2 across two ticks proves nothing.
3. **Long multi-window proofs can be lost to history pruning.** Every
   observation inside the last window is kept, so single-window proofs are
   always found. Older observations are kept only for 24 h, and at most 64 of
   them. A proof that needs a baseline more than 24 h back, or more than 64
   older distinct-count observations back, is not found. In practice this hits
   only loops averaging just over 2 per tick, which would need more than about
   16 hours of history to prove.
4. **A failed delivery is not retried.** The dead-man reports it (`/fail`), and
   both ledgers record it (`delivered: false` on the canary line).
5. **During an alert storm the pass takes as long as the bus takes.** A pass
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

To start over, delete the state file **under the stage's own lock**. The
canary holds an exclusive non-blocking `flock` on `crash-loop.lock` from
loading the state to saving it, so a delete taken under the same lock can
never be undone by a pass that is running. The reset is refused if the lock
is busy:

```bash
ssh office2-claude 'flock -n -E 75 /data/services/felix-canary/state/crash-loop.lock rm -f /data/services/felix-canary/state/crash-loop.json; rc=$?; if [ $rc -eq 0 ]; then echo "reset done"; elif [ $rc -eq 75 ]; then echo "busy: a pass holds the lock; nothing deleted, retry in a minute"; else echo "rm failed: exit $rc"; fi'
```

`flock(1)` and the canary's `fcntl.flock` (`StateLock` in
`scripts/canary/crash_loop_state.py`) take the same kind of lock, so they
exclude each other. While the reset holds the lock, a pass that starts skips
the stage and records `crash_loop:locked` (harmless once). On the next pass
every unit is first-seen: it gets a baseline and **nothing alerts**, and any
open episode ends without a `cleared` message. Detection resumes from the pass
after that. A missing or corrupt file has the same effect, so a damaged file is
never a crash.

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

Run this once 7 full days have passed since
`deploys/queued/crash-loop-unit-alerting.yaml` was applied (felix-deployer
numbers the manifest when it applies it; see the applied record under
`deploys/applied/`). It is research R-14 of the mission, covering SC-003,
NFR-004 and NFR-005. Every command is read-only, and you run them from your own
terminal.

Every check prints one verdict on its last line:

- `PASS` means the check had the evidence it needs and found nothing wrong.
- `FAIL` means it found a problem. Each problem is printed above the verdict.
- `INCONCLUSIVE` means evidence is missing: the window is not over, a ledger
  is missing, the stage left no lines, or the config changed during the
  window. Missing evidence is never a `PASS`.

**Step 1. Fix the window.** The window starts at the first `crash-loop:system`
line, which is the stage's first pass after deploy, and ends exactly 7 days
later:

```bash
ssh office2-claude 'cat /data/services/felix-canary/ledger/*.jsonl | jq -r "select(.component_id==\"crash-loop:system\") | .evaluated_at" | head -1'
```

Use that timestamp as `START`. Compute `END` as `START` plus 7 days:

```bash
date -u -d "START + 7 days" +%Y-%m-%dT%H:%M:%S+00:00
```

Replace `START` and `END` in the commands below with those two timestamps,
for example `2026-12-01T14:03:11+00:00`. Both checks refuse a window shorter
than 7 days, or one that has not ended yet.

**Step 2. Check 1: every page was a proven crossing (SC-003, NFR-004).** It
reads the canary ledger, the alert-bus ledger and the office2 checkout's
config.

- **Config.** The check requires the config to be **unchanged for the whole
  window**, and verifies it from the checkout's git history. There must be no
  local edit to `scripts/canary/crash_loop_config.json`, and its newest commit
  on the first-parent history must be older than `START`. If the config
  changed inside the window, the check is `INCONCLUSIVE`. Start a new 7-day
  window after the change; do not check historical pages against a config
  that was not in force when they were sent.
- **Proofs, recomputed.** The check does not trust the numbers the canary
  wrote. For every emitted event line it derives `delta = current_count −
  baseline_count` and `period = observed_at − baseline_at` from the recorded
  samples. It requires `period > 0`, and both values must equal the line's
  `delta` and `period_seconds`. For alert and re-remind lines it then
  recomputes `m = ceil(period / window_seconds)` and
  `bound = m·(threshold−1)+1`, and requires `delta ≥ bound` and the recorded
  `m` and `bound` to match. Any mismatch is a `FAIL`.
- **Two-way reconciliation.** Every emitted canary event line in the window
  needs its alert-bus entry: an individual entry with the same component,
  kind and time, or an aggregate entry whose `count` equals the number of
  lines folded into it at that time. The time is the line's
  `interval.observed_at`, which is the alert's timestamp, not `evaluated_at`.
  Every bus entry from a `felix-canary:crash-loop:` source needs its canary
  line or lines. A bus entry with no canary line, or an aggregate count that
  does not match, is a `FAIL`. A canary page with no bus entry, or no bus ledger files for the
  window at all, is `INCONCLUSIVE`, because the bus ledger is best-effort and
  the evidence is missing rather than contradicted.

```bash
ssh office2-claude 'START=START END=END python3 -I -' <<'EOF'
import json, math, os, subprocess
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

T = datetime.fromisoformat
start, end = T(os.environ["START"]), T(os.environ["END"])
now = T(os.environ["NOW"]) if "NOW" in os.environ else datetime.now(timezone.utc)
canary_dir = Path(os.environ.get("CANARY_LEDGER", "/data/services/felix-canary/ledger"))
bus_dir = Path(os.environ.get("BUS_LEDGER", "/data/services/alert-bus/ledger"))
repo = os.environ.get("REPO", "/home/claude/kg-automation")
config_rel = "scripts/canary/crash_loop_config.json"
missing, violations = [], []


def records(directory, when):
    # From the day before START: a canary file is named for the pass's start,
    # which can be just before midnight when the counter read is just after it.
    first = (start - timedelta(days=1)).date().isoformat()
    days = [p for p in sorted(directory.glob("*.jsonl")) if first <= p.stem <= end.date().isoformat()]
    if not days:
        missing.append(f"no ledger files for the window in {directory}")
    for path in days:
        for line in path.read_text().splitlines():
            if line.strip() and start <= T(when(json.loads(line))) < end:
                yield json.loads(line)


# An event line is placed by its interval's observed_at, the alert's timestamp,
# so it falls inside or outside the window together with its bus entry.
canary_time = lambda r: r["interval"]["observed_at"] if "interval" in r else r["evaluated_at"]


if end - start < timedelta(days=7):
    missing.append(f"window is {end - start}, shorter than 7 days")
if end > now:
    missing.append(f"window ends {end.isoformat()}, after now {now.isoformat()}")

# The config must be the one in force for the whole window.
git = lambda *a: subprocess.run(["git", "-C", repo, *a], capture_output=True, text=True)
edits, log = git("status", "--porcelain", "--", config_rel), git("log", "--first-parent", "--format=%cI %h", "--", config_rel)
if edits.returncode or log.returncode or not log.stdout.strip():
    missing.append(f"cannot read the config history in {repo}")
elif edits.stdout.strip():
    missing.append(f"{config_rel} has local edits")
elif T(log.stdout.split()[0]) >= start:
    missing.append(f"config changed at {log.stdout.split()[0]} ({log.stdout.split()[1]}); start a new window after it")
config = json.loads((Path(repo) / config_rel).read_text())
n, window = config["threshold"], config["window_seconds"]

KIND = {"crash-loop": "alert", "crash-loop-reremind": "reremind", "crash-loop-cleared": "cleared"}
FOLDED = "(in aggregate alert)"
canary = list(records(canary_dir, canary_time)) if canary_dir.is_dir() else missing.append(f"missing: {canary_dir}") or []
bus = list(records(bus_dir, lambda b: b["ts"])) if bus_dir.is_dir() else missing.append(f"missing: {bus_dir}") or []
if not any(r["component_id"] == "crash-loop:system" for r in canary):
    missing.append("no crash-loop:system lines in the window: no evidence the stage ran")

# Recompute every proof from the recorded samples; trust no producer number.
events = [r for r in canary if r.get("outcome") in KIND and r.get("emitted")]
for r in events:
    i, where = r["interval"], f"{r['component_id']} at {r['evaluated_at']}"
    period = (T(i["observed_at"]) - T(i["baseline_at"])).total_seconds()
    delta = i["current_count"] - i["baseline_count"]
    if period <= 0 or delta != i["delta"] or abs(period - i["period_seconds"]) > 0.001:
        violations.append(f"INCONSISTENT {where}: delta {delta} vs {i['delta']}, period {period} vs {i['period_seconds']}")
    elif r["outcome"] != "crash-loop-cleared":
        m = max(1, math.ceil(period / window))
        if delta < m * (n - 1) + 1 or (i["m"], i["bound"]) != (m, m * (n - 1) + 1):
            violations.append(f"NOT PROVEN {where}: delta {delta}, m {m}, bound {m * (n - 1) + 1}, recorded {i['m']}/{i['bound']}")

# Two-way reconciliation between the canary ledger and the alert-bus ledger.
at = lambda text: round(T(text).timestamp(), 3)
canary_single = {(r["component_id"], KIND[r["outcome"]], at(r["interval"]["observed_at"])) for r in events if not r["evidence"].endswith(FOLDED)}
canary_folded = Counter(at(r["interval"]["observed_at"]) for r in events if r["evidence"].endswith(FOLDED))
bus = [b for b in bus if b.get("source", "").startswith("felix-canary:crash-loop:") and b.get("details", {}).get("kind")]
bus_single = {(b["details"].get("component_id"), b["details"]["kind"], at(b["ts"])) for b in bus if b["details"]["kind"] != "aggregate"}
bus_folded = Counter({at(b["ts"]): int(b["details"]["count"]) for b in bus if b["details"]["kind"] == "aggregate"})
for key in sorted(canary_single - bus_single):
    missing.append(f"canary page with no bus entry: {key}")
for key in sorted(bus_single - canary_single):
    violations.append(f"bus entry with no canary line: {key}")
for ts in sorted(set(canary_folded) | set(bus_folded)):
    if ts not in bus_folded:
        missing.append(f"{canary_folded[ts]} folded canary lines at {ts} with no bus aggregate")
    elif bus_folded[ts] != canary_folded[ts]:
        violations.append(f"aggregate at {ts}: bus count {bus_folded[ts]}, canary folded lines {canary_folded[ts]}")

print(f"window {start.isoformat()} to {end.isoformat()}; threshold {n}, window {window} s")
print(f"canary event lines {len(events)}; bus crash-loop entries {len(bus)}")
for item in missing:
    print("  MISSING EVIDENCE:", item)
for item in violations:
    print("  VIOLATION:", item)
print("FAIL" if violations else "INCONCLUSIVE" if missing else "PASS")
EOF
```

Check 1 needs scope lines in the window as evidence that the stage ran, but it
does not test their cadence. Step 4 does that.

**Step 3. Check 2a: the canary unit never failed (NFR-005).** The user journal
of `felix-canary.service` should show no non-zero exit in the window:

```bash
ssh office2-claude 'journalctl --user -u felix-canary.service --since START --until END --no-pager | grep -E "Failed with result|status=[0-9]+/" || echo "no failed runs"'
```

Then count the passes that finished with `status=error`, and the passes that
finished at all:

```bash
ssh office2-claude 'j=$(journalctl --user -u felix-canary.service --since START --until END --no-pager); echo "passes: $(grep -c "^.*status=\(success\|error\) " <<<"$j")  with errors: $(grep -c "status=error " <<<"$j")"'
```

If `passes` is 0, the journal holds no evidence for the window (for example it
was rotated). Record check 2a as `INCONCLUSIVE`, not as passed. The journal
records only the error **count** per pass (`errors=<n>`). The error text is kept
only for the latest pass, in `last-tick.json`. So a non-zero count cannot by
itself show whether a `crash_loop:` error happened. Explain each one from
check 2b (a pass where the stage faulted before routing has no scope lines)
and from the dead-man's `/fail` history on healthchecks.io. Also look at the
latest pass:

```bash
ssh office2-claude 'jq -c ".errors" /data/services/felix-canary/state/last-tick.json'
```

**Step 4. Check 2b: every pass ran the stage (NFR-005).** All three scopes
(`crash-loop:system`, `crash-loop:user`, `crash-loop:container`) must have
lines across the whole window. Coverage must reach both boundaries: the first
line no more than 1200 s after `START`, the last no more than 1200 s before
`END`, and no gap over 1200 s in between (one missed tick). Every scope line
must be `healthy`.

```bash
ssh office2-claude 'START=START END=END python3 -I -' <<'EOF'
import json, os
from datetime import datetime, timedelta, timezone
from pathlib import Path

start = datetime.fromisoformat(os.environ["START"])
end = datetime.fromisoformat(os.environ["END"])
now = datetime.fromisoformat(os.environ["NOW"]) if "NOW" in os.environ else datetime.now(timezone.utc)
ledger = Path(os.environ.get("CANARY_LEDGER", "/data/services/felix-canary/ledger"))
max_gap = timedelta(seconds=1200)
scopes = ("crash-loop:system", "crash-loop:user", "crash-loop:container")
seen = {scope: [] for scope in scopes}
missing, problems = [], []

if end - start < timedelta(days=7):
    missing.append(f"window is {end - start}, shorter than 7 days")
if end > now:
    missing.append(f"window ends {end.isoformat()}, after now {now.isoformat()}")
if not ledger.is_dir():
    missing.append(f"ledger directory missing: {ledger}")
else:
    first, last = start.date().isoformat(), end.date().isoformat()
    files = [p for p in sorted(ledger.glob("*.jsonl")) if first <= p.stem <= last]
    if not files:
        missing.append(f"no ledger files dated {first} to {last}")
    for path in files:
        for line in path.read_text().splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            scope = r.get("component_id")
            if scope not in seen:
                continue
            when = datetime.fromisoformat(r["evaluated_at"])
            if not start <= when < end:
                continue
            seen[scope].append(when)
            if r["outcome"] != "healthy":
                problems.append(f"{r['evaluated_at']} {scope} {r['outcome']}: {r['evidence']}")

for scope, times in seen.items():
    times.sort()
    if not times:
        problems.append(f"{scope}: no lines at all in the window")
        continue
    edges = [start, *times, end]
    for a, b in zip(edges, edges[1:]):
        if b - a > max_gap:
            problems.append(f"{scope}: gap {a.isoformat()} -> {b.isoformat()} ({b - a})")
    print(f"{scope}: {len(times)} lines, first {times[0].isoformat()}, last {times[-1].isoformat()}")

print(f"window: {start.isoformat()} to {end.isoformat()}")
for item in missing:
    print("  MISSING EVIDENCE:", item)
for item in problems:
    print("  PROBLEM:", item)
print("INCONCLUSIVE" if missing else "FAIL" if problems else "PASS")
EOF
```

A scope with no lines, an edge or inner gap, and a non-healthy line are each a
`FAIL`, listed as `PROBLEM`. A gap can have an innocent cause, such as a reboot
or a planned stop. Explain each one in the record; do not drop it.

The environment variables `CANARY_LEDGER`, `BUS_LEDGER`, `REPO` and `NOW` in
the two scripts exist only so the scripts can be tested off-host. On office2,
leave them unset.

**Step 5. Record the result** as a comment on
[kentonium3/kg-automation#1133](https://github.com/kentonium3/kg-automation/issues/1133).
Give:

- the window (`START` to `END`);
- check 1's three summary lines and its verdict;
- check 2a's failed-run output and its pass and error counts;
- check 2b's per-scope lines and its verdict;
- an explanation of everything flagged;
- the overall result. It is a pass only if every check passed. Otherwise give
  the follow-up issue you opened, or the date you will re-run the check.

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
