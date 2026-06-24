# Specification: Atomic inbox-file finalize helper

## Purpose

The `felix-admin-capture` agent finishes processing each inbox file by running a
deterministic cleanup sequence: mark the file's frontmatter `status: processed`,
move it from `01-Inbox/` to `02-Inbox-Processed/`, and append a line to the daily
processing log. Today the agent performs these as separate LLM-issued tool calls
(`Edit` + `Bash mv` + log append) with **no atomicity, no error surface, and no
idempotent recovery**. This has twice produced silent partial-finalize states
(2026-05-13 and 2026-05-18) that went undetected for days.

This mission delivers a single helper the agent invokes once per file. The cleanup
runs as a deterministic, idempotent, atomic-per-step operation that surfaces clear
errors, so finalize either fully completes or fails loudly — never silently
half-done.

## User Scenarios & Testing

**Primary actor:** the `felix-admin-capture` agent (autonomous, running on office2).

**Trigger:** the agent has finished routing one inbox file's content to its
destination(s) and must finalize that file.

**Happy path:** the agent calls the helper with the file path (and its own agent
id). The helper sets the frontmatter status, moves the file to the processed
directory, appends a dated log line, prints a single-line JSON result, and exits
0. The agent records the finalize as complete.

**Main exception:** a step cannot complete (e.g., permission denied writing the
processed directory). The helper exits non-zero with the specific OS error on
stderr; the agent, per its standing orders, surfaces the failure and does **not**
mark the file complete.

**Recovery scenario:** a prior finalize left the file already moved and status
already `processed`, but the daily-log line is missing. Re-invoking the helper
detects the completed steps, appends only the missing log line, and exits 0 — no
duplication, no error.

### Acceptance scenarios

1. **Happy path** — unprocessed file in `01-Inbox/` → status becomes `processed`,
   file is in `02-Inbox-Processed/`, exactly one matching daily-log line exists,
   stdout is the JSON result, exit 0.
2. **Already finalized (idempotent)** — fully-finalized file → no changes, no
   duplicate log line, exit 0.
3. **Partial-state recovery** — file moved + status set but no log line →
   only the log line is appended, exit 0.
4. **Permission denied (file write)** — frontmatter write blocked → exit 2,
   OSError on stderr, no partial file left behind.
5. **Permission denied (directory write)** — move/log-append blocked → exit 2,
   OSError on stderr.
6. **Missing frontmatter** → exit 1.
7. **Malformed YAML frontmatter** → exit 1.
8. **Cross-filesystem rename rejected** → exit 2 (no silent copy fallback).

## Requirements

### Functional Requirements

| ID | Requirement | Status |
|----|-------------|--------|
| FR-001 | The helper accepts an inbox file path argument and an optional caller identifier (the routing agent id). | Approved |
| FR-002 | The helper validates input before mutating anything: the path exists, resolves under the inbox root, and has parseable YAML frontmatter; otherwise it fails as a validation error. | Approved |
| FR-003 | The helper sets the file's frontmatter `status` to `processed`, and treats an already-`processed` file as a no-op for this step. | Approved |
| FR-004 | The helper moves the file into the processed directory, and treats a file already present in the processed directory (matched by basename) as a no-op for this step. | Approved |
| FR-005 | The helper appends one line for the file to the current UTC-dated daily processing log, creating that log file with standard frontmatter if absent; the line records filename, routed-by, and finalized-at UTC timestamp. | Approved |
| FR-006 | A line already present for this filename in today's log is a no-op (no duplicate). | Approved |
| FR-007 | Each state-mutating step is preceded by an idempotence check, so re-invocation on a partially-finalized file completes only the remaining steps without duplication. | Approved |
| FR-008 | On success (full or partial-becomes-full) the helper emits a single-line JSON object to stdout reporting that the file was finalized, which steps executed, and the file's final path. | Approved |
| FR-009 | The helper communicates outcome via exit code: success/already-finalized, validation failure, and filesystem failure are each distinct codes; filesystem failures carry the specific OS error message on stderr. | Approved |
| FR-010 | The `felix-admin-capture` standing orders are updated to invoke the helper as the single final per-file step (replacing the inline frontmatter edit + move), and define how the agent handles each non-success exit code. | Approved |

### Non-Functional Requirements

| ID | Requirement | Status |
|----|-------------|--------|
| NFR-001 | Each state mutation is atomic at the filesystem level (content writes via temp-file-plus-rename; the move via an atomic rename) such that no partially-written or partially-moved file is ever observable by a concurrent reader. | Approved |
| NFR-002 | The operation is idempotent: running it any number of times on the same file converges to the same end state and exactly one daily-log line for that file (zero duplicates). | Approved |
| NFR-003 | Every failure exits non-zero with a specific human-readable message on stderr, and every success emits machine-parseable JSON on stdout following the existing `prescan.py` convention, so the orchestrating agent can determine the outcome deterministically (zero silent failures). | Approved |
| NFR-004 | Automated tests cover all eight enumerated scenarios (happy, idempotent, permission-denied on file write, permission-denied on directory write, missing frontmatter, malformed YAML, cross-filesystem rename rejected, partial-state recovery). | Approved |

### Constraints

| ID | Constraint | Status |
|----|------------|--------|
| C-001 | The inbox root and processed directory are resolved from the `scripts/vault/paths.json` registry (same pattern as `prescan.py`); no hardcoded vault paths. | Approved |
| C-002 | Change is Tier 3 (Logic/Workflow), additive: no production state changes at deploy; the cutover is the standing-orders edit; rollback is reverting that edit and deleting the helper. | Approved |
| C-003 | The daily-log date is the UTC calendar date (`YYYY-MM-DD`). | Approved |
| C-004 | The move uses an atomic same-filesystem rename; a cross-filesystem move is rejected as a filesystem error rather than silently copied. | Approved |
| C-005 | The stdout JSON result shape matches the `prescan.py` contract for agent consumption. | Approved |

## Success Criteria

- **SC-001:** After a normal agent finalize, the file is in the processed
  directory with `status: processed` AND a matching daily-log line exists — 100%
  of finalizes, with no silent partial states.
- **SC-002:** Re-running finalize on any partially- or fully-finalized file never
  creates a duplicate log line and never errors.
- **SC-003:** Any finalize failure is detectable by the orchestrator from a
  non-zero exit plus a stderr message — zero silent failures.
- **SC-004:** All eight enumerated test scenarios pass in CI.

## Key Entities

- **Inbox file** — a Markdown note with YAML frontmatter including a `status`
  field; lives in `01-Inbox/` before finalize and `02-Inbox-Processed/` after.
- **Daily processing log** — one Markdown file per UTC date in the processed
  directory, with standard frontmatter and one line per finalized file.
- **Vault path registry** — `scripts/vault/paths.json`, the source of the inbox
  root and processed directory locations.

## Assumptions

- The vault path registry (`scripts/vault/paths.json`) exists and exposes the
  inbox root and processed directory, consistent with how `prescan.py` consumes
  it today.
- The 2026-05-12 pre-existing stuck file may have already aged out via prescan's
  7-day archive sweep. If it is still present when this lands, the new helper
  itself finalizes it on invocation — no separate one-off cleanup script is
  required.

## Out of Scope

- Universal error/alerting escalation primitives that scripts and LLM agents can
  call to escalate silent failures (warrants its own RFC).
- The umask/permissions root cause, already resolved in #323; this mission closes
  the underlying architectural gap (non-atomic, unrecoverable finalize), not the
  permission symptom.
