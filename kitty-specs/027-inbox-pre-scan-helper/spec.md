---
id: spec-027-inbox-pre-scan-helper
title: Inbox Pre-Scan Helper
doc_type: spec
status: draft
last_updated: '2026-04-11'
owners:
  - '@kentonium3'
mission_slug: 027-inbox-pre-scan-helper
source_issue: kentonium3/kg-automation#149
---

# Inbox Pre-Scan Helper

## Problem Statement

The `felix-admin-capture` inbox agent runs four times per day via `openclaw cron`. On every run, the Haiku-backed agent reads every file currently in `{{VAULT_INBOX}}`, parses each file's frontmatter to check `status`, and discards the ~27 already-processed files to operate on the 0–1 that are genuinely unprocessed. Token cost scales with inbox history, not with actual work. Empty runs still cost a full agent invocation. Processed files accumulate in `{{VAULT_INBOX}}` indefinitely, making the cost-vs-value curve worse over time.

Kent's intent is that the agent does real cognitive work — routing, classifying, summarising — not inventory scanning. A cheap deterministic pre-scan can hand the agent exactly the files it needs, and skip the agent invocation entirely when the inbox has no unprocessed items.

## User Scenarios & Testing

### Primary Scenarios

**Scenario 1 — Empty run (most common case).**
The 12:00 inbox cron fires. `{{VAULT_INBOX}}` contains 30 files, all with `status: processed`. The pre-scan helper runs, finds zero unprocessed files, and signals "empty" to cron. `felix-admin-capture` is not invoked. Zero agent tokens are consumed. A log line records "0 unprocessed" for the run.

**Scenario 2 — Single-item run (typical work case).**
The 17:00 inbox cron fires. `{{VAULT_INBOX}}` contains 30 files, one of which has `status: unprocessed`. The helper identifies the one file, and cron invokes `felix-admin-capture` with that file's path. The agent reads only that file, routes it, and writes the outcome. Processed-file cleanup (Scenario 4) runs as part of the same helper invocation regardless of the unprocessed count.

**Scenario 3 — Multi-item run (catch-up case).**
A cron run fires after Kent has captured several notes rapidly. Three files have `status: unprocessed`. The helper returns three paths, cron invokes `felix-admin-capture` once with all three paths, and the agent processes them in the same turn.

**Scenario 4 — Stale processed file archiving.**
As part of every helper invocation (regardless of how many unprocessed files are present), the helper identifies processed files older than seven days and moves them to `{{VAULT_INBOX_PROCESSED}}`. The move is logged with source path, destination path, timestamp, and reason. Recent processed files (<7 days) stay in `{{VAULT_INBOX}}` so the agent retains short-term context.

**Scenario 5 — Helper failure.**
The helper encounters an unrecoverable error (e.g., `{{VAULT_INBOX_PROCESSED}}` does not exist, frontmatter parse error on a file, registry resolver returns an error). The failure is logged with a clear message, the helper exits non-zero, and `felix-admin-capture` is NOT invoked. The next cron run retries.

### Edge Cases

- **File with no frontmatter** → treated as unprocessed (safe default; a human or agent should triage it).
- **File with missing `status` field** → treated as unprocessed (safe default).
- **File with `status` value other than the known processed/unprocessed values** → treated as unprocessed (safe default; never accidentally archived).
- **File locked or temporarily unreadable** → logged as a warning, file treated as unprocessed for this run, next run retries.
- **Concurrent helper invocations** → safe; helper is idempotent and reads-before-writes so two overlapping runs cannot double-move a file (or at worst produce one harmless "destination already exists" error that gets logged).
- **`{{VAULT_INBOX_PROCESSED}}` missing** → helper logs error and exits non-zero. It does NOT create the directory itself (that is a registry/deploy concern).
- **Helper finds a file whose target path in `{{VAULT_INBOX_PROCESSED}}` already exists** → log and skip (do not overwrite). Manual cleanup path.

## Functional Requirements

| ID | Requirement | Status |
|---|---|---|
| FR-001 | A pre-scan helper MUST resolve `{{VAULT_INBOX}}` and `{{VAULT_INBOX_PROCESSED}}` via the vault path registry introduced in missions 024 and 026. The helper MUST NOT hardcode any vault directory path. | Draft |
| FR-002 | The helper MUST identify files in `{{VAULT_INBOX}}` whose frontmatter `status` field equals "unprocessed" and emit their absolute paths in a deterministic machine-readable form on stdout. | Draft |
| FR-003 | The helper MUST treat files with missing frontmatter, missing `status` field, or any `status` value other than an explicit processed value as unprocessed. The "unknown → unprocessed" default is a safety rule to prevent accidental archiving. | Draft |
| FR-004 | The helper MUST identify files in `{{VAULT_INBOX}}` whose `status` is explicitly processed AND whose age exceeds 7 days, and move them to `{{VAULT_INBOX_PROCESSED}}` preserving the original filename. | Draft |
| FR-005 | The helper MUST log every archive move with timestamp, source path, destination path, and reason, to a log file path determined during planning. Log entries MUST be appended, never overwritten. | Draft |
| FR-006 | The helper MUST be idempotent. Re-running on an unchanged inbox MUST produce the same unprocessed list and no additional archive moves. | Draft |
| FR-007 | The helper MUST exit non-zero and log a clear error message when `{{VAULT_INBOX_PROCESSED}}` does not exist, when registry resolution fails, or when any unrecoverable parse/filesystem error occurs. The helper MUST NOT attempt to create vault directories. | Draft |
| FR-008 | The helper MUST NOT read, write, reference, or log any path under `~/second-brain/notes/04-Growth/_private/`, consistent with the Felix constitutional privacy boundary. | Draft |
| FR-009 | The `felix-admin-capture` cron invocation MUST be replaced with a sequence that runs the helper first and invokes the agent only when the helper reports at least one unprocessed file. On empty runs the agent MUST NOT be invoked and no agent tokens MUST be consumed. | Draft |
| FR-010 | When the agent is invoked, the helper's unprocessed list MUST be passed to it as input (env var, argument, or file — selected during planning) so that the agent's Step 1 input contract is "read these files" rather than "scan the inbox". | Draft |
| FR-011 | If the helper exits non-zero, the cron sequence MUST log the failure and MUST NOT invoke the agent. The next cron run retries from scratch. | Draft |
| FR-012 | The `felix-admin-capture` agent workspace (IDENTITY.md / SOUL.md / AGENTS.md, whichever defines Step 1) MUST be updated to describe the new input contract so future edits do not revert it. | Draft |
| FR-013 | The helper's canonical source MUST live in the kg-automation repository under `scripts/inbox/` (exact subdirectory confirmed during planning) and MUST be deployed to office2 via a one-shot deploy wrapper patterned on mission 026's `deploy-f026.sh`. | Draft |
| FR-014 | The deploy wrapper MUST follow the change-control protocol established by missions 024 and 026: snapshot the prior state of any file it replaces, apply atomically where possible, verify post-apply, and pause `felix-admin-capture` cron during the risky window using the correct `openclaw cron disable <uuid>` path (NOT the system crontab fallback that #162 identified as broken). | Draft |
| FR-015 | Architecture documentation (`docs/design/architecture/data/service-inventory.json` and its markdown counterpart, at minimum) MUST be updated to reflect the pre-scan helper as a component of the `felix-admin-capture` service path. | Draft |

## Non-Functional Requirements

| ID | Requirement | Threshold | Status |
|---|---|---|---|
| NFR-001 | Helper runtime on the current inbox size | ≤ 1 second wall-clock on office2 for up to 50 files | Draft |
| NFR-002 | Helper must not consume LLM tokens or make network calls | 0 tokens, 0 network calls per invocation | Draft |
| NFR-003 | Empty-run token cost (no unprocessed files) | 0 agent tokens consumed end-to-end | Draft |
| NFR-004 | Frontmatter parsing must be robust to YAML edge cases | Zero false positives on a corpus of 50 real inbox files including multi-line values, quoted strings, and files with missing/empty frontmatter | Draft |
| NFR-005 | Deploy wrapper risky-window duration | ≤ 15 minutes between cron pause and cron resume | Draft |
| NFR-006 | Helper logging verbosity | One log line per run at minimum (counts + status); one line per archive move | Draft |

## Constraints

| ID | Constraint | Status |
|---|---|---|
| C-001 | The helper MUST operate only inside `{{VAULT_INBOX}}` and `{{VAULT_INBOX_PROCESSED}}`. No other vault paths are permitted. `~/second-brain/notes/04-Growth/_private/` is the constitutional hard limit and MUST NOT be touched under any circumstances. | Binding |
| C-002 | The helper MUST NOT modify file contents. It may only list files and move whole files between the two registered directories. Frontmatter stays as-is; status transitions remain the agent's responsibility. | Binding |
| C-003 | The helper MUST NOT create the `{{VAULT_INBOX_PROCESSED}}` directory. Directory creation is the responsibility of the vault path registry and deploy pattern (missions 024 and 026). | Binding |
| C-004 | The helper MUST NOT introduce new vault path registry markers. This mission consumes `{{VAULT_INBOX}}` and `{{VAULT_INBOX_PROCESSED}}` as already defined; extending the registry is out of scope. | Binding |
| C-005 | The mission MUST be implementable without waiting on issue #136 (Mac → office2 deploy model). A one-shot deploy wrapper is acceptable; migration to #136's primitives is a future concern. | Binding |
| C-006 | The mission MUST NOT break existing `felix-admin-capture` behavior on non-empty runs. Routing, summarisation, and downstream task/journal creation remain unchanged. | Binding |
| C-007 | Backwards movement of files (from `{{VAULT_INBOX_PROCESSED}}` back to `{{VAULT_INBOX}}`) is out of scope. Recovery is manual. | Binding |

## Success Criteria

| ID | Criterion | Measurement |
|---|---|---|
| SC-001 | Empty inbox run costs zero agent tokens | Observe a cron run where `{{VAULT_INBOX}}` has zero unprocessed files; confirm via logs that `felix-admin-capture` was not invoked and no Anthropic tokens were billed for that run. |
| SC-002 | Non-empty run routes correctly | Place a known unprocessed test file in `{{VAULT_INBOX}}`, trigger the cron, confirm the agent processed only that file (not the other ~28), and confirm the expected downstream effect (Vikunja task, vault write, or whatever the file's content dictates). |
| SC-003 | Stale processed files archive on schedule | Place a processed file with an 8-day-old mtime in `{{VAULT_INBOX}}`, trigger the helper, confirm the file is now in `{{VAULT_INBOX_PROCESSED}}` and the move is recorded in the helper log. |
| SC-004 | Recent processed files stay put | Place a processed file with a 6-day-old mtime, trigger the helper, confirm the file remains in `{{VAULT_INBOX}}` and no move is logged for it. |
| SC-005 | Unprocessed files are never archived | Place an unprocessed file with a 30-day-old mtime, trigger the helper, confirm the file remains in `{{VAULT_INBOX}}` and no move is logged for it. |
| SC-006 | Helper fails loud on missing destination | Temporarily rename `{{VAULT_INBOX_PROCESSED}}`, trigger the helper, confirm non-zero exit, confirm `felix-admin-capture` is not invoked, confirm the cron run's failure is visible in logs. Restore directory. |
| SC-007 | Agent workspace reflects the new contract | Read `ai-agents/felix-admin-capture/` files and confirm Step 1 describes the helper-provided input list, not "scan the inbox". |
| SC-008 | Deploy wrapper pauses cron correctly | Observe a full deploy run: confirm `openclaw cron list` shows `inbox-*` crons disabled during the risky window and re-enabled after verification. The #162 failure mode (system crontab fallback) MUST NOT appear. |
| SC-009 | Architecture docs updated | `docs/design/architecture/data/service-inventory.json` references the pre-scan helper; markdown counterpart matches; JSON `updated_by` field notes this mission's slug. |
| SC-010 | Issue #149 closeable | All issue #149 acceptance criteria (as listed in the issue body) are satisfied; closure comment can be posted after `/spec-kitty.merge`. |

## Assumptions

- **A-001**: The vault path registry (from missions 024 and 026) provides a resolver (Python and/or shell) that returns real filesystem paths for `{{VAULT_INBOX}}` and `{{VAULT_INBOX_PROCESSED}}`. Plan phase verifies the exact API.
- **A-002**: `{{VAULT_INBOX_PROCESSED}}` was created as part of mission 026 and exists on office2 with correct group ownership (secondbrain + setgid, per the #161 fix). Plan phase confirms with a single `ls -ld`.
- **A-003**: The `claude` user on office2 has read+write access to both `{{VAULT_INBOX}}` and `{{VAULT_INBOX_PROCESSED}}`. Plan phase confirms.
- **A-004**: Inbox frontmatter uses a stable `status` field with at least two known values: "unprocessed" and some explicit "processed" value (likely "processed", to be confirmed by sampling). Plan phase samples real files and records the exact values in the plan.
- **A-005**: File mtime is a reasonable proxy for "how long since this file was processed" for the 7-day archive rule. If sampling shows a stable frontmatter date field (`processed_at` or similar), plan phase may prefer it; otherwise mtime stands.
- **A-006**: Python 3 is available on office2 with PyYAML installed (or easily installable). Plan phase confirms.
- **A-007**: The existing `openclaw cron` jobs for `inbox-*` are invoked by UUID, and the deploy wrapper can disable/enable them via `openclaw cron disable <uuid>` (the working path identified in #162's analysis).
- **A-008**: Issue #136 (Mac → office2 deploy model) will NOT ship before this mission. This mission builds a one-shot wrapper and accepts that it will be retroactively migrated when #136 delivers primitives.
- **A-009**: Mission 025's self-observation work is not affected. The helper is separate from the agent's cognitive layer.

## Key Entities

- **Inbox file** — a markdown file in `{{VAULT_INBOX}}`, typically with YAML frontmatter containing `status` and optional timestamps. Represents a single capture (Wispr Flow transcription, manual note, etc.).
- **Pre-scan helper** — a Python script that lists unprocessed inbox files and archives stale processed ones. Pure deterministic logic, no LLM, no network.
- **Deploy wrapper** — a shell script in `scripts/deploy/` that pushes the helper, agent workspace patch, and cron wiring from the kg-automation repo to office2, following the mission 026 pattern.
- **`felix-admin-capture` agent** — the existing OpenClaw agent that processes inbox captures. Its cron entry and Step 1 input contract change; its core logic does not.
- **Vault path registry** — the JSON registry + Python/shell resolvers + deploy mechanism delivered by missions 024 and 026. This mission is a consumer.
- **Archive log** — an append-only log file recording every stale-processed-file move. Path determined during planning.

## Dependencies

- **Inbound**: Mission 026 (#152) must be merged — ✅ merged, commit c2aa4a1. `{{VAULT_INBOX_PROCESSED}}` exists and is reachable via the registry.
- **Adjacent**: #161 group-ownership fix must be in place — ✅ setgid applied, confirmed.
- **Not blocking this mission**: #158 (Obsidian Sync silent failure — risk-accepted, close follow-on). #136 (deploy model — this mission builds a one-shot; migration is a future concern).

## Out of Scope

- Rewriting `felix-admin-capture`'s processing logic beyond Step 1 input contract
- Changing frontmatter schema or introducing new status values
- Creating or managing `{{VAULT_INBOX_PROCESSED}}`
- Extending the vault path registry with new markers
- Reverse migration (from `{{VAULT_INBOX_PROCESSED}}` back to `{{VAULT_INBOX}}`)
- Making the helper an OpenClaw skill or agent
- Token-savings observability/alerting (tracked separately under #137 / #138)
- Generalizing the deploy wrapper into reusable primitives (that's #136)
- Fixing Obsidian Sync silent-failure risk (that's #158, risk-accepted for this mission)
