---
title: Alerting via the felix-alert Bus
doc_type: runbook
audience: agents_and_humans
status: approved
level: howto
created: 2026-07-10
last_validated: '2026-07-10'
last_updated: '2026-07-10'
updated_by: '#701 (unified-alert-bus-01KX5TYT)'
version: v1.0
owners: [kgale]
---

# Alerting via the felix-alert Bus

## Purpose

Every operator-facing Felix alert flows through **one shared alert bus** — the
`felix-alert` bus — and arrives on **one canonical ntfy thread**. This runbook
is the how-to for emitting an alert from Python, the CLI, or a bash script, and
the reference for the alert schema, the severity map, the topic-secret model,
and the fail-safe contract.

The bus is the observability substrate for Bedrock stabilization (RFC #327,
`felix-bedrock-stabilization.md`, `coherence/doctrine.md`) and was built by
mission `unified-alert-bus-01KX5TYT` (kentonium3/kg-automation#701).

**Canonical term:** an operator notification is an **alert**. Do not use
"notification", "ping", or "message" as drifting synonyms in code or docs.

## What the bus is

- A small Python package at **`scripts/common/alert_bus/`** plus a bash shim at
  **`scripts/common/alert_bus.sh`**.
- The **single path** that constructs and delivers alerts. No emitter keeps its
  own curl/ntfy code — a repository search finds ntfy alert delivery only in the
  bus (SC-006).
- `emit()` (via `delivery.py`) is the **only** module that performs ntfy I/O
  (FR-005).
- Stateless: the only configuration is the canonical topic (see
  [Topic-secret provisioning](<#topic-secret-provisioning>)).

Three subsystems emit through it today (the three real ntfy emitters, migrated
by #701):

| Emitter | Source path | Old per-component topic (retired) |
|---|---|---|
| felix-deployer subsystem (`notify.py` + `deploy/lib/health.py`, incl. `agent-prompt-sync`) | `scripts/deploy/felix-deployer/notify.py`, `scripts/deploy/lib/health.py` | `felix-deployer-ntfy-topic` |
| security-monitor | `scripts/office2/security-monitor/audit.sh` (via `alert_bus.sh`) | per-audit ntfy topic |
| felix-health-check | `scripts/office2/felix_health_check/run.py` | `felix-health-check` ntfy env topic |

The openclaw enforcement notifier additionally **co-emits** a `felix-alert` for
agent-drift events (FR-009) while keeping its existing WhatsApp + GitHub records.

## The `Alert` schema

Construct an `Alert` value object with these fields (canonical schema in
`kitty-specs/unified-alert-bus-01KX5TYT/data-model.md`):

| Field | Type | Required | Notes |
|---|---|---|---|
| `source` | str | yes | Component + specific phase, e.g. `"felix-deployer/apply"`. |
| `severity` | `Severity` | yes | One of `info`/`warn`/`error`/`critical`. Drives priority + tags. |
| `title` | str | yes | Short human-readable title, e.g. `"felix-deployer failed: felix-calendar-helper"`. |
| `description` | str | yes | Plain-language account of what happened (no bare phase codes). |
| `action` | str \| None | no | The operator's next step / recovery command, when known. |
| `details` | dict[str, str] | no | Structured extras: ids, paths, exit codes, and — for failures — the **actual error/stderr** (FR-003). |
| `timestamp` | datetime | auto | Set at construction if not supplied; rendered as UTC + local. |

**Invariants**

- `source`, `severity`, `title`, `description` are always present and
  non-empty. Constructing an `Alert` missing a required field raises
  `ValueError` **at the call site** (a programming error), not at delivery time.
- A missing optional field (`action`, empty `details`) still yields a
  deliverable, readable message (NFR-003) — the renderer omits absent sections
  rather than emitting placeholders.
- `details` values are redacted (secrets) **before** truncation during
  rendering (D8), using the shared `scripts.deploy.lib.verify.redact_secrets`.

## Severity → ntfy priority/tag map

The single source of truth is `SEVERITY_MAP` in
`scripts/common/alert_bus/model.py`. A monotonic priority gradient keeps
criticality visually distinct on the one thread (FR-004).

| Severity | ntfy Priority | ntfy Tags | Intended use |
|---|---|---|---|
| `info` | `low` | `information_source` | FYI / successful-but-notable events |
| `warn` | `default` | `warning` | Degraded but not failing; attention soon |
| `error` | `high` | `rotating_light` | A component operation failed (most migrated alerts) |
| `critical` | `max` | `rotating_light,sos` | Urgent — needs immediate operator action |

Choose the severity that fits at the call site: deployer failure → `error`;
unexpected-drift / critical-gate → `critical`; security summary → `warn` or
`error` by alert count; health-check failure → `error`.

## How to emit

The emit examples below match the public API and CLI contract exactly
(`kitty-specs/unified-alert-bus-01KX5TYT/contracts/alert-bus-api.md`). If the
API changes, update this runbook in the same change.

### From Python

```python
from scripts.common.alert_bus import emit, Alert, Severity

result = emit(Alert(
    source="felix-deployer/apply",
    severity=Severity.ERROR,
    title="felix-deployer failed: felix-calendar-helper",
    description="Dry-run failed before apply; the deploy script was not executable.",
    action="chmod +x the deploy script and re-queue the manifest.",
    details={
        "manifest": "felix-calendar-helper",
        "phase": "dry_run",
        "head": "0628e279",
        "exit_code": "126",
        "stderr": "<captured stderr — the actual error>",
    },
))
# result.ok -> bool ; emit() never raises
if not result.ok:
    # best-effort: log result.reason and continue; do NOT crash the caller.
    ...
```

`emit()` returns an `AlertResult(ok, reason, topic_configured)` and **never
raises**. `emit()` is the sole public entry point — do not import `deliver`,
`render_*`, or talk to ntfy directly.

### From the CLI

```
python3 -m scripts.common.alert_bus emit \
  --source "security-monitor/audit" \
  --severity warn \
  --title "Felix Security Alert — office2" \
  --description "3 audit finding(s) on 2026-07-10" \
  --action "Review the audit log and rebaseline if the drift is expected." \
  --detail findings=3 \
  --detail date=2026-07-10
```

- `--severity` accepts exactly `info|warn|error|critical`.
- `--detail key=value` may repeat; the value may itself contain `=`.
- `--detail-stdin` folds piped text into `details["stdin"]` — use it to pass
  captured stderr/output from a shell caller:
  ```
  some-command 2>&1 | python3 -m scripts.common.alert_bus emit \
    --source "x/y" --severity error --title "..." --description "..." --detail-stdin
  ```
- **Exit codes:** `emit` is best-effort by default → it **always exits 0** after
  attempting delivery (logging the `AlertResult`), so a cron/audit caller never
  fails because ntfy was down. Pass `--strict` to make `emit` reflect
  `AlertResult.ok` (non-zero on failure) for callers that want it.

### From bash

Use the shim; never re-implement curl/ntfy in a script:

```
scripts/common/alert_bus.sh emit \
  --source "security-monitor/audit" \
  --severity warn \
  --title "Felix Security Alert — office2" \
  --description "3 audit finding(s) on 2026-07-10"
```

The shim **sources the topic env-file** (`/home/claude/.config/felix/alert-bus/env`)
if present, then env-anchors to the checkout and invokes the CLI
(`cd /home/claude/kg-automation && python3 -m scripts.common.alert_bus "$@"` —
office2 has only `python3`, never bare `python`). Sourcing the env-file is what
lets a cron-launched `audit.sh` (which has no systemd `EnvironmentFile`) resolve
the topic. The shim is **best-effort**: it logs and **exits 0** even on delivery
failure, so it never fails the calling cron/audit regardless of `|| true`
discipline. (`self-test` / `--strict` still reflect failure inside the CLI.)

## Topic-secret provisioning

The canonical thread identity is the **single secret** `FELIX_ALERT_NTFY_TOPIC`
— a new, high-entropy, dedicated ntfy topic (do **not** reuse
`felix-deployer-ntfy-topic`). It is provisioned **out-of-band** and never
committed (the C-002 exception); only the placeholder template
`scripts/common/alert_bus.env.sample` is committed.

- **Storage:** env-file `/home/claude/.config/felix/alert-bus/env`, containing
  `FELIX_ALERT_NTFY_TOPIC=<topic-value>`.
- **Registry:** recorded in
  `docs/design/architecture/data/credential-manifest.json` (entry added by #701).
- **How each runtime gets it:**
  - felix-deployer.service, felix-health-check.service, and
    agent-prompt-sync.service load it via systemd `EnvironmentFile=-` (leading
    dash → the unit still starts cleanly if the file is missing).
  - The cron-launched security-monitor `audit.sh` inherits no systemd
    `EnvironmentFile`; `scripts/common/alert_bus.sh` sources the env-file
    directly.
- **Missing topic:** `emit()` returns `AlertResult(ok=False,
  reason="NTFY_MISSING_TOPIC", topic_configured=False)` and attempts no POST —
  it fails safe rather than crashing.
- **Publish-only secret:** knowing the topic lets a passive listener *read*
  alert bodies (which carry error text and paths) but cannot impersonate an
  emitter or mint deploys. No auth header is sent (public-subscribe topic;
  secrecy is the control). Subscribe the ntfy phone app to the same topic.
- **Rotation:** no automatic expiry. Rotate only on suspected leak — edit the
  env-file on office2 to a new random topic, restart the emitting timers (or
  wait for the next tick), and re-subscribe the phone app. See the
  credential-manifest entry for the full procedure.

## Fail-safe contract

The bus must never take down an emitting component (D7 / NFR-001 /
SC-005):

- **`emit()` never raises.** Every delivery failure surfaces as
  `AlertResult(ok=False, reason=…)`. Even an unexpected internal error is
  swallowed into `AlertResult(ok=False, reason="BUS_ERROR:…")`.
- **Non-blocking:** delivery uses `curl --max-time 10`; the subprocess is reaped
  at a 15 s ceiling. An unreachable endpoint never hangs or blocks the caller
  beyond that.
- **Best-effort at the boundaries:** the CLI `emit` and the bash shim both
  **exit 0** on delivery failure by default (logging the result). Callers on
  cron/audit paths never fail because ntfy was down.
- **Fail-loud only where it must:** `self-test` (and `emit --strict`) reflect
  delivery — exit non-zero on failure — because their whole job is to prove the
  path.

Reason codes you may see in an `AlertResult`: `NTFY_MISSING_TOPIC` (topic
unset/blank), `CURL_CONNECT` (couldn't resolve/connect), `CURL_HTTP` (HTTP
error via `--fail`), `CURL_TIMEOUT`, `CURL_ERROR:<rc>` / `CURL_EXEC_ERROR:<...>`,
`BUS_ERROR:<...>`.

## Durable ledger (#706)

Every `emit()` also appends a record to a durable, append-only local ledger on
office2 — so there is a **queryable fault history** that survives ntfy being
down and captures delivery failures too (a failed POST is still a recorded
fault). This is the write-side; a reader/scanner and any self-correction loop
are separate, later work (the latter gated on #683).

- **Location:** `/data/services/alert-bus/ledger/<YYYY-MM-DD>.jsonl` (override
  with `FELIX_ALERT_LEDGER_DIR`). Files older than 30 days are pruned on write.
- **Record shape (one JSON object per line):** `ts` (UTC ISO-8601), `source`,
  `severity`, `title`, `description`, `action`, `details`, and `delivery`
  (`ok`, `reason`, `topic_configured`). `description` and `details` values are
  redacted + truncated exactly as the sent alert is (no secrets the alert
  wouldn't carry); `title` and `action` are stored verbatim, matching what the
  renderer sends.
- **Best-effort:** a ledger write failure never changes the returned
  `AlertResult` and never breaks `emit()` (same discipline as the ntfy POST).
- **Query it:**
  ```bash
  # today's faults
  jq -c . /data/services/alert-bus/ledger/$(date -u +%F).jsonl
  # only failed deliveries this week
  cat /data/services/alert-bus/ledger/*.jsonl | jq -c 'select(.delivery.ok == false)'
  # recurring source
  cat /data/services/alert-bus/ledger/*.jsonl | jq -r .source | sort | uniq -c | sort -rn
  ```

## Per-runtime self-test

Each runtime that emits must be able to **prove** its topic wiring end-to-end.
Run the self-test from that runtime's context (it emits a known `info` alert and
exits non-zero iff delivery failed):

```
python3 -m scripts.common.alert_bus self-test
```

or via the shim (which sources the env-file first):

```
scripts/common/alert_bus.sh self-test
```

A green self-test confirms `FELIX_ALERT_NTFY_TOPIC` is wired and the alert
arrives on the canonical thread. The deploy preflight
(`scripts/deploy/deploy-unified-alert-bus.py --dry-run`) reports an absent
env-file before the mission is considered done (C-002).

## Verifying an alert on the thread

On the ntfy phone app subscribed to the canonical topic, a well-formed alert
shows the title, the mapped priority/tag (so critical vs informational is
visually distinct), and a body with: timestamp (UTC + local), `Source:`,
`Severity:`, the description, `Action:` (when set), and a `Details:` block of
`key=value` lines (with the real, redacted, truncated error text for failures).
Reading a single alert should tell you *what* failed, *when*, *how bad*, and
*what to do* (SC-003).

## Related

- Contracts: `kitty-specs/unified-alert-bus-01KX5TYT/contracts/alert-bus-api.md`
- Data model: `kitty-specs/unified-alert-bus-01KX5TYT/data-model.md`
- Service inventory entry: `docs/design/architecture/data/service-inventory.json`
  (`alert-bus` library + `felix-alert` unified topic).
- Credential registry: `docs/design/architecture/data/credential-manifest.json`
  (`FELIX_ALERT_NTFY_TOPIC`).
- Observability doctrine: `docs/design/coherence/doctrine.md`,
  `docs/design/felix-bedrock-stabilization.md` (which reference the `felix-alert`
  bus).
