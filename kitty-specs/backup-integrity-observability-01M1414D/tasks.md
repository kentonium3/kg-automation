# Tasks: Backup Integrity Observability

**Mission**: `backup-integrity-observability-01M1414D`
**Planning/base branch**: `feat/backup-integrity-observability`
**Spec**: [spec.md](./spec.md) · **Plan**: [plan.md](./plan.md)

Five work packages, 22 subtasks, disjoint file ownership.

## Subtask Index

| ID | Description | WP | Parallel |
|----|-------------|----|----------|
| T001 | Initialise `PRUNE_RC` to the `127` not-run sentinel | WP01 | |
| T002 | Record `prune_exit_code` in the state pointer | WP01 | |
| T003 | Confirm every pre-prune exit path reports `127` | WP01 | |
| T004 | Update the script's own header comment to describe the new field | WP01 | [P] |
| T005 | Check `prune_exit_code` with a `{0}` good-set | WP02 | |
| T006 | Fail closed when a restic pointer has no snapshot timestamp | WP02 | |
| T007 | Prove both through the real probe, including legacy pointers | WP02 | |
| T008 | Comparator module with match / drift / inconclusive | WP03 | |
| T009 | Freshness pointer with affirmative health | WP03 | |
| T010 | systemd user unit + daily timer | WP03 | [P] |
| T011 | Deploy entrypoint with `--dry-run` / `--apply` | WP03 | |
| T012 | Manifest with `verification.post`, validated locally | WP03 | |
| T013 | Tests: every verdict reachable, never fails open | WP03 | |
| T014 | Refactor to one header parser reporting recognition | WP04 | |
| T015 | `--emit-body`, failing closed on unrecognised input | WP04 | |
| T016 | Round-trip test that fails if the header format drifts | WP04 | |
| T017 | Register the comparator; correct the restic `expected` prose | WP05 | |
| T018 | Narrative + view docs + capability roadmap | WP05 | [P] |
| T019 | New `crontab-recovery.md` runbook | WP05 | [P] |
| T020 | `restic-backup-ops.md`: prune signal + manual-install decision | WP05 | |
| T021 | Deploy-discipline doc surfaces | WP05 | [P] |
| T022 | `docs/INDEX.md` + `DEVELOPER_PORTAL.md` | WP05 | [P] |

---

## Phase 0 — Make the prune outcome exist

### WP01 — Record the prune outcome

**Goal**: `restic-backup.sh` records whether retention was applied.
**Independent test**: Read the pointer after a run and find `prune_exit_code`;
confirm a run that never reaches the prune reports `127`, not absent and not `0`.

Included subtasks: T001, T002, T003, T004

**Dependencies**: none.

**Risks**: This file is `root:root` on the host and hand-installed. The repo
change lands here; the host does not have it until the operator installs it, and
that is expected. Do not attempt to install it.

Prompt: [WP01-record-prune-outcome.md](./tasks/WP01-record-prune-outcome.md)

---

## Phase 1 — Make it consequential

### WP02 — Canary acts on the prune outcome

**Goal**: A recorded prune failure makes the component unhealthy, and a backup
with no snapshot stops reading fresh.
**Independent test**: Drive the real `run_probe` with `prune_exit_code` of 0, 1,
3, and 127, and with a null snapshot timestamp; required verdicts in the prompt.

Included subtasks: T005, T006, T007

**Dependencies**: WP01 (field contract).

**Risks**: `probes.py` is shared by every registered component — the change must
be inert when the key is absent. The prune good-set is `{0}`, **not**
`_RESTIC_OK_EXIT_CODES` `{0, 3}`; reusing the backup's set would accept a prune
that did not apply retention, which is the failure being fixed.

Prompt: [WP02-canary-acts-on-prune.md](./tasks/WP02-canary-acts-on-prune.md)

---

## Phase 2 — Detect divergence, fix recovery

### WP03 — Backup script drift comparator

**Goal**: Report divergence between the repo and deployed backup script.
**Independent test**: Point it at an altered copy, a missing copy, and an
identical copy; require `drift`, `inconclusive`, `match`.

Included subtasks: T008, T009, T010, T011, T012, T013

**Dependencies**: none.

**Risks**: Must never write under `/data/services/backup/scripts/` — that
directory must stay non-claude-writable (C-001). Must fail **closed**: an
unreadable deployed copy is `inconclusive`, never `match`.

Prompt: [WP03-drift-comparator.md](./tasks/WP03-drift-comparator.md)

### WP04 — Crontab recovery without a hand-written strip

**Goal**: The capture helper emits its own reinstallable body.
**Independent test**: `--emit-body` output is byte-identical to the `crontab -l`
input that produced the artifact, with no hand-written pattern anywhere.

Included subtasks: T014, T015, T016

**Dependencies**: none.

**Risks**: Today's `strip_header()` returns input unchanged both when no header
matches and when the sentinel is missing — it cannot tell a caller whether a
header was recognised. Reusing it as-is would emit a headerless file as though
verified. One parser, refactored; do not add a second recogniser.

Prompt: [WP04-emit-body.md](./tasks/WP04-emit-body.md)

---

## Phase 3 — Register and document

### WP05 — Registration, runbooks, and the trusted install

**Goal**: Both new signals registered; the recovery and install procedures live
where an operator looks.
**Independent test**: Both blocking validators pass; the comparator appears in a
canary dry run with a definite verdict.

Included subtasks: T017, T018, T019, T020, T021, T022

**Dependencies**: WP01, WP02, WP03, WP04.

**Risks**: `success_status_values: ["success"]` is required on the comparator's
check — without an allow-list `probes.py` treats `status` as a deny-list and an
unrecognised verdict word passes as healthy. The install procedure must verify
its source, not just its destination.

Prompt: [WP05-registration-and-runbooks.md](./tasks/WP05-registration-and-runbooks.md)

---

## Dependency graph

```
WP01 ── WP02 ──┐
WP03 ──────────┼── WP05
WP04 ──────────┘
```

## MVP scope

**WP01 + WP02** closes #902 — the defect that a prune failure was invisible.
WP03 closes #903, WP04 closes #906, WP05 makes all three legible.
