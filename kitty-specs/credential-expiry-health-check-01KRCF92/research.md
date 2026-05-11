# Research — Credential Expiry Health Check

**Mission**: `credential-expiry-health-check-01KRCF92`
**Spec**: [spec.md](./spec.md)
**Date**: 2026-05-11

This document records plan-phase decisions and the evidence behind them. Each decision is captured in the format: **Decision** / **Rationale** / **Alternatives considered**.

---

## R-001 — Resolution of spec assumption A-004: `monitor-activity` activity-staleness checks

**Decision**: **In scope for v1.** Both `monitor-activity` credentials (`tailscale-auth`, `whatsapp-session`) have programmatic activity signals that are trivially queryable from the `claude` user without sudo.

**Rationale (probed live on office2 during plan phase)**:

- `tailscale-auth`: `tailscale status --json` returns a structured payload including `BackendState` (string, e.g. `"Running"`) and full peer state. Detecting drift to `BackendState != "Running"` is sufficient signal.
- `whatsapp-session`: `openclaw channels status` returns a one-line summary per channel including `in:<duration> ago, out:<duration> ago` and a `connected` / `running` / `linked` triplet. Detecting `not connected`, `not running`, or `in:` / `out:` > 14 days (the documented session-expiry threshold per `whatsapp-session.expiry_notes`) is sufficient signal.

**Alternatives considered**:

- *Defer to a follow-up issue.* Rejected: signals are trivially available right now; deferring would leave a known gap in v1.
- *Include `tailscale-auth` but defer `whatsapp-session`.* Rejected: same parse-shell-output pattern works for both; no marginal complexity from including both.

---

## R-002 — Audit-trail log destination

**Decision**: **Use the systemd journal**, accessible to the `claude` user without sudo via `journalctl --user -u credential-health-check.service`. No separate log file is written.

**Rationale**:

- Matches the precedent set by `felix-doc-auditor.service` (#223), which also writes to the journal and is the model for this auditor's scheduling. Operational consistency.
- The systemd journal supports time-range queries (`--since`, `--until`) which makes per-cycle inspection cleaner than a flat append-only file.
- No filesystem-quota or rotation concerns; the journal handles retention.

**Alternatives considered**:

- *Plain log file at `/tmp/credential-health-check.log`.* Rejected: matches `sync-heartbeat.py` (#158) but `/tmp` is volatile and the journal is the more durable choice. Operationally, the journal is what oncall would reach for first.
- *Log file under `/home/claude/.local/state/`.* Rejected: yet another path to memorize; the journal is canonical.

---

## R-003 — Manifest path resolution

**Decision**: The check accepts an optional `--manifest <path>` CLI argument. Default value: `/home/claude/kg-automation/docs/design/architecture/data/credential-manifest.json` (the deployed repo path under the `claude` user). The systemd service unit passes the default explicitly so the path is visible in the unit file.

**Rationale**:

- Makes the unit file self-documenting (no implicit defaults).
- Enables straightforward testing against a synthetic manifest fixture (`--manifest tests/fixtures/manifest-near-expiry.json`).
- The repo is already cloned at `/home/claude/kg-automation/` per the felix-doc-auditor deploy precedent — single source of truth for both deployments.

**Alternatives considered**:

- *Hard-code the path.* Rejected: kills testability and makes the unit file opaque.
- *Read from an environment variable.* Rejected: indirection without payoff; the unit file already controls execution context.

---

## R-004 — Module structure: single script vs. package

**Decision**: **Single Python script** (`scripts/security/credential-health-check.py`) with internal helper functions. No package, no separate modules.

**Rationale**:

- Total LOC is small (estimated 300–500 lines including tests).
- Mirrors `scripts/obsidian/sync-heartbeat.py` (#158) and `scripts/openclaw/observation/summarize.py` — single-file Python scripts are the established kg-automation pattern for systemd-timer-triggered automation.
- Testing remains straightforward: helper functions are importable; the orchestrating `main()` is the only entry point.

**Alternatives considered**:

- *Package layout (`scripts/security/credential_health_check/{__init__,manifest,alerts,activity}.py`).* Rejected: over-structured for the scope; would create a precedent that none of the other Felix runners follow.

---

## R-005 — Alert dedup mechanism

**Decision**: **Title-prefix-based GitHub issue search**. The check queries `gh issue list --search 'in:title "Credential review: <name>"' --state open --json number,title` before filing; if any open issue matches, the cycle skips that credential's alert (and does not create a duplicate Vikunja task).

The stable title format is:

```
Credential review: <name> due <YYYY-MM-DD>
```

Where `<name>` is the credential's `name` field from the manifest and `<YYYY-MM-DD>` is the computed cadence boundary.

**Rationale**:

- Single source of truth (the GitHub issue state) drives all dedup decisions for both alerts.
- No need to track Vikunja task IDs separately or maintain a routing log on disk.
- If Kent rotates and updates `last_reviewed` mid-cycle, the next cycle's boundary computation moves the date out of the warning window and no new alert is filed even if the old issue stays open (which is expected — Kent closes it after rotation).
- GitHub search-by-title is reliable enough; the title prefix is unique to this auditor.

**Alternatives considered**:

- *Issue label `credential-pending-review` instead of title prefix.* Rejected: adds a label-management step (create on repo, manage retention) without buying anything title prefix doesn't already give us.
- *Local routing log mapping credential name → issue number.* Rejected: introduces on-disk state that must survive crashes and redeploys; complicates testing.

---

## R-006 — Test strategy

**Decision**: Three layers:

1. **Unit tests** for the deterministic data-processing functions (date arithmetic, boundary computation, dedup-key generation, manifest parsing). Pure Python, no external surfaces. Mocking is unnecessary — these functions take dict / datetime inputs.
2. **Contract tests** for the activity-signal extractors (`tailscale-status-parser`, `whatsapp-channels-parser`) using captured fixture output from real `tailscale status --json` and `openclaw channels status` invocations on office2.
3. **Integration smoke test** for the alert path: a runnable canary that points at a synthetic manifest fixture and a side-channel GitHub label (`canary-do-not-rotate`) so Kent can validate the GitHub + Vikunja write paths without disturbing the live alert queue.

**Rationale**:

- The deterministic layer is the high-value target — the dedup math and cadence math is where false-positives/missed-alerts come from. Unit tests give us SC-003 and SC-004 evidence cheaply.
- Contract tests with captured fixtures isolate the parsers from upstream tool output changes; if `tailscale` or `openclaw` ever change their output format, the parser tests are the failure surface.
- The integration smoke test is the same shape as the felix-doc-auditor canary established in #105 / #215.

**Alternatives considered**:

- *No tests — just deploy and watch.* Rejected: SC-003 and SC-004 require demonstrable correctness; we're not running 14 days of validation by visual inspection.
- *Full end-to-end test against the live GitHub + Vikunja.* Rejected: pollutes the real issue queue; the canary procedure covers this with side-channel hygiene.

---

## R-007 — Manifest-quality reporting (FR-012)

**Decision**: If any credential entry has a missing or malformed `last_reviewed` or `review_cadence`, file **one** GitHub issue per cycle (not per credential) with the title `Credential manifest quality: <N> entries with issues — <YYYY-MM-DD>` and a body listing the affected entries. The check still processes all well-formed entries.

**Rationale**:

- Matches FR-012's "at most one ... per cycle" wording.
- A single batched issue is less noisy than per-credential manifest-quality issues; the manifest is a small file so all issues can be inspected together.
- The body's structured list makes it easy to fix everything in one Kent session.

**Alternatives considered**:

- *Halt the entire cycle if any entry is malformed.* Rejected: would defeat the purpose for the well-formed majority; an early-warning regression in field hygiene shouldn't break the auditor.

---

## R-008 — Self-referential PAT alerts (edge case from spec §2)

**Decision**: When the credential being alerted on is `kg-felix-bot-pat` itself, the check still files the issue using the existing PAT (assumed valid through its own warning window per spec assumption A-001's analog). When the credential is `vikunja-api`, the check still creates the task using the existing token.

The check does **not** attempt to detect "my own PAT is broken" — that's an outer-layer concern (the systemd unit's exit status surfaces in `journalctl`, which Kent inspects during the post-deploy 14-day verification window).

**Rationale**:

- Pragmatic: the 30-day warning window combined with annual review cadence means the auditor has 30+ days to alert before the PAT expires, which is more than enough buffer to rotate the PAT before the PAT-fail mode kicks in.
- Detecting "my own auth is bad" requires a chicken-and-egg meta-channel; deferring to journalctl + systemd-status visibility is the simplest robust answer.

**Alternatives considered**:

- *Fail-fast self-test of GitHub + Vikunja auth at the start of each cycle.* Considered but rejected for v1: adds API calls (rate-limit concerns) and complexity for a failure mode that the operational visibility layer already handles.

---

## R-009 — Scheduling time-of-day

**Decision**: `OnCalendar=*-*-* 13:00:00 UTC` (13:00 UTC daily). Selected because:

- It is **after** the Restic backup (04:00 UTC) and security audit (03:00 UTC) — the auditor runs against a fully-quiesced post-backup system.
- It is **after** Kent's typical morning (which falls around 11–13 UTC during EDT). Alerts that fire from this run land in his email and Vikunja before lunchtime ET.
- It is **before** the inbox-5pm processing tick (17:00 ET = 21:00 UTC during EDT), so the daily Felix cadence remains predictable.

**Rationale**:

- The exact time matters only modestly; the daily granularity is what's load-bearing. Choosing 13:00 UTC removes ambiguity and gives the system a natural anchor.
- Avoids 00:00 UTC (overlaps with inbox-10pm ET) and avoids 06:00–10:00 UTC (Kent asleep / unavailable for follow-up if alerts arrive).

**Alternatives considered**:

- *`OnCalendar=daily` (= 00:00 UTC).* Rejected: collides with inbox-10pm ET (also UTC midnight-adjacent under EDT) and lands alerts during Kent's evening when he's least responsive.
- *`OnCalendar=hourly`.* Rejected: violates FR-009 (once per UTC day) — though hourly would still dedup, it's wasted runs.

---

## R-010 — Naming conventions

**Decision**: All artefacts follow `credential-health-check` as the slug:

| Artefact | Path |
|---|---|
| Script | `scripts/security/credential-health-check.py` |
| Timer unit | `scripts/office2/credential-health-check.timer` (source); `~/.config/systemd/user/credential-health-check.timer` (deployed) |
| Service unit | `scripts/office2/credential-health-check.service` (source); `~/.config/systemd/user/credential-health-check.service` (deployed) |
| Deploy script | `scripts/office2/deploy/credential-health-check.sh` |
| Service-inventory entry name | `credential-health-check` |
| GitHub issue title prefix | `Credential review:` (for cadence alerts) / `Credential manifest quality:` (for FR-012) |

**Rationale**:

- Mirrors `felix-doc-auditor` naming and deploy-script convention exactly.
- The friendly mission name `Credential Expiry Health Check` becomes `credential-health-check` in code — short enough for unit-file names, descriptive enough to be unambiguous.

---

## Open items deferred to implement phase

| ID | Item | Disposition |
|---|---|---|
| **D-001** | Exact field shape for the Vikunja task (project, priority, labels) | Implement-phase decision; default = Inbox project, no labels, priority unset. Resolvable by reading the existing Vikunja project structure. |
| **D-002** | Whether to set `assignees: ['kentonium3']` on the GitHub issue | Implement-phase decision; default = yes (matches manual assignment Kent would do anyway). |

These are not architecture questions and don't require Kent's input. They're "preferences with sensible defaults" that the implementer can pick.
