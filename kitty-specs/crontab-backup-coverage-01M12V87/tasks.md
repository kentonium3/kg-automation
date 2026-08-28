# Tasks: Crontab Backup Coverage

**Mission**: `crontab-backup-coverage-01M12V87`
**Planning/base branch**: `feat/crontab-backup-coverage`
**Final merge target**: `feat/crontab-backup-coverage`
**Spec**: [spec.md](./spec.md) · **Plan**: [plan.md](./plan.md)

Five work packages, 24 subtasks. Ownership is disjoint by construction — no two
work packages name the same file — so WP02/WP03 and WP04 can run in parallel
once WP01 lands.

## Subtask Index

| ID | Description | WP | Parallel |
|----|-------------|----|----------|
| T001 | Warn above the manual rebaseline reset in `security-baseline-ops.md` | WP01 | |
| T002 | Warn above the rebaseline command in `post-change-verification.md` | WP01 | [P] |
| T003 | Warn above the rebaseline command in `CLAUDE.md` | WP01 | [P] |
| T004 | Correct the stale "14 baseline files" to 15 | WP01 | [P] |
| T005 | Record the runbook-modified signal in `docs/INDEX.md` | WP01 | [P] |
| T006 | Scaffold `crontab_capture.py` CLI, exit codes, SUMMARY line | WP02 | |
| T007 | Read the crontab and compose the artifact with a provenance header | WP02 | |
| T008 | Refuse empty or failed reads, preserving the prior artifact | WP02 | |
| T009 | Refuse suspicious truncation via a shrink guard, with `--force` | WP02 | |
| T010 | Write the freshness pointer atomically on every run | WP02 | |
| T011 | Unit tests covering capture, refusal, shrink, idempotency, atomicity | WP02 | |
| T012 | Author `crontab-capture.service` | WP03 | |
| T013 | Author `crontab-capture.timer` (hourly, `Persistent=true`) | WP03 | [P] |
| T014 | Author the deploy entrypoint with `--dry-run` / `--apply` | WP03 | |
| T015 | Author `deploys/queued/crontab-capture.yaml` | WP03 | |
| T016 | Validate the manifest locally against the schema | WP03 | |
| T017 | Emit a durable freshness pointer from `drift_check.py` | WP04 | |
| T018 | Map process exit codes to runner health, separating `has_drift` | WP04 | |
| T019 | Tests: drift-found is healthy, runner-error is not | WP04 | |
| T020 | Register `crontab-capture` in `service-inventory.json` | WP05 | |
| T021 | Register `agent-drift-check` in `service-inventory.json` | WP05 | |
| T022 | Add the capture data flow to `data-flows.{json,md,view.md}` | WP05 | [P] |
| T023 | Update `service-inventory.md` and `service-dependencies.view.md` | WP05 | [P] |
| T024 | Note the capability in `felix-capability-roadmap.md` | WP05 | [P] |

---

## Phase 0 — Guard the destructive step

### WP01 — Rebaseline destructive-step warning

**Goal**: Warn the operator, everywhere the destructive rebaseline is documented
as a human action, that the baselines directory may hold the only copy of host
state.
**Priority**: P3 story, but sequenced **first**.
**Independent test**: Read each prose copy and confirm the warning sits above the
destructive step, and that `audited-surfaces.json` is untouched.

Included subtasks: T001, T002, T003, T004, T005

**Implementation sketch**: add the warning block above the `rm` in the manual
reset procedure; repeat at the two other operator-facing copies; correct the
stale baseline count in the same section; record the runbook edits in the docs
index.

**Dependencies**: none.

**Risks**: `audited-surfaces.json` → `rebaseline_command` must stay byte-identical
(C-001). The occurrences under `docs/diagnostics/**` and `kitty-specs/**` are
frozen historical records and must not be edited.

Prompt: [WP01-rebaseline-warning.md](./tasks/WP01-rebaseline-warning.md)

---

## Phase 1 — Make the crontab recoverable

### WP02 — Crontab capture helper

**Goal**: A helper that captures the `claude` crontab into backed-up storage,
refuses to destroy a good copy, and reports its own health.
**Priority**: P1 — this is User Story 1.
**Independent test**: Run the helper against an injected `crontab -l`; confirm the
artifact is reinstallable, the pointer is written, and empty/truncated reads are
refused.

Included subtasks: T006, T007, T008, T009, T010, T011

**Implementation sketch**: argparse CLI → read crontab via an injectable callable
→ compose artifact with provenance header → apply refusal rules → atomic write
only on change → atomic pointer write always → `SUMMARY:` line.

**Dependencies**: WP01.

**Risks**: The refusal rules are the point of the WP, not a footnote — a capture
that overwrites a good artifact with an empty one during the destruction window
is worse than no capture. Atomicity must be real (tmp + `os.replace`).

Prompt: [WP02-capture-helper.md](./tasks/WP02-capture-helper.md)

### WP03 — Schedule and deploy the capture

**Goal**: Install the capture as a systemd user timer through the manifest
pipeline.
**Priority**: P1.
**Independent test**: `--dry-run` reports the intended actions and changes
nothing; the manifest validates against the schema locally.

Included subtasks: T012, T013, T014, T015, T016

**Implementation sketch**: unit + timer modelled on the `0018` precedent →
entrypoint copying units to `~/.config/systemd/user/`, `daemon-reload`,
`enable --now`, verify → manifest at Tier 3 with a `verification` block.

**Dependencies**: WP02.

**Risks**: `notes` must stay under 2000 characters — exceeding it lets the
entrypoint's side effects land and then blocks the applied record, re-applying
every five-minute tick with no alert (#891/#901). CI does **not** validate queued
manifests, so T016 is a mandatory manual gate, not a formality.

Prompt: [WP03-schedule-and-deploy.md](./tasks/WP03-schedule-and-deploy.md)

---

## Phase 2 — Make the drift check observable

### WP04 — Drift-check freshness pointer

**Goal**: Give `drift_check.py` a durable signal that says whether it *ran*,
without conflating that with whether it *found drift*.
**Priority**: P2 — User Story 2.
**Independent test**: A run that finds drift is judged healthy by the real canary
probe; a run that errors is not.

Included subtasks: T017, T018, T019

**Dependencies**: WP01. No technical dependency on WP02 or WP03 — may run in
parallel with them.

**Risks**: The exit-code mapping is the whole WP. `sys.exit(1 if has_drift else 0)`
means the process exit code is a *result*, not a health verdict; writing it into
the pointer would make every drift-finding run page as a failure.

Prompt: [WP04-drift-check-pointer.md](./tasks/WP04-drift-check-pointer.md)

---

## Phase 3 — Register and document

### WP05 — Architecture registration and doc surfaces

**Goal**: Register both components for health, and update every architecture
surface the signal-to-doc map names.
**Priority**: P2.
**Independent test**: `validate_architecture_data.py --strict` and the canary
inventory data-guard test both pass; both components appear in a canary dry run
with a definite verdict.

Included subtasks: T020, T021, T022, T023, T024

**Dependencies**: WP02, WP04 — the health checks point at state paths those WPs
define, so registering earlier would pin paths that do not yet exist.

**Risks**: Pointer methods require an absolute `state_path` and an integer
`max_age_seconds`, or the data-guard test fails. Neither component may probe a
path under `/tmp`.

Prompt: [WP05-architecture-registration.md](./tasks/WP05-architecture-registration.md)

---

## Dependency graph

```
WP01 ──┬── WP02 ── WP03
       │      │
       └── WP04
              │
       WP05 ──┴──(also needs WP02)
```

`WP01 -> {WP02, WP04}`; WP03 follows WP02; WP05 follows WP02 and WP04.

## MVP scope

**WP01 + WP02 + WP03** delivers User Story 1 end to end — the crontab becomes
recoverable from backup without a security-monitor baseline, which is the
failure that actually occurred on 2026-08-27. WP04 and WP05 add the observability
half.
