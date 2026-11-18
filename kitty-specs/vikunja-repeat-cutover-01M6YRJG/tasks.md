# Work Packages: Vikunja repeat cutover

Tracking: see #1095. Historical route: see #1087.
Planning base and merge target: fix/vikunja-repeat-cutover. Timestamp: 2026-11-09T05:00:00Z.

## Subtask Index

| Subtask | Description | WP | Parallel |
|---|---|---|---|
| T001 | Accept rrule versions and refuse malformed suffixes | WP01 | No; sequential dependency chain |
| T002 | Parse gzip after pinning the original archive bytes | WP01 | No; sequential dependency chain |
| T003 | Verify tagged Docker imports and preflight collisions | WP01 | No; sequential dependency chain |
| T004 | Validate an optional baseline binding shape | WP01 | No; sequential dependency chain |
| T005 | Make shared CLI failures emit stable codes only | WP01 | No; sequential dependency chain |
| T006 | Freeze the first-cutover record and isolate historical tests | WP01 | No; sequential dependency chain |
| T007 | Replace the obsolete rollback schema criterion | WP02 | No; sequential dependency chain |
| T008 | Require exact pre_version before tag or start | WP02 | No; sequential dependency chain |
| T009 | Recover unfinished pre-snapshot markers under both locks | WP02 | No; sequential dependency chain |
| T010 | Count repeats edits and label backfill privately | WP02 | No; sequential dependency chain |
| T011 | Remove private DB safety reporting | WP02 | No; sequential dependency chain |
| T012 | Adopt the frozen fixture and reverse obsolete expectations | WP02 | No; sequential dependency chain |
| T013 | Load and authenticate the bound baseline | WP03 | No; sequential dependency chain |
| T014 | Implement versioned schema identity | WP03 | No; sequential dependency chain |
| T015 | Share comparison, aggregates and data-free build logic | WP03 | No; sequential dependency chain |
| T016 | Write a durable private baseline receipt | WP03 | No; sequential dependency chain |
| T017 | Gate ACTIVATE between snapshot persistence and retag | WP03 | No; sequential dependency chain |
| T018 | Scrub every ACTIVATE private detail producer | WP03 | No; sequential dependency chain |
| T019 | Prove failure ordering, replay and snapshot rollback recovery | WP03 | No; sequential dependency chain |
| T020 | Implement stable-copy preflight | WP04 | No; sequential dependency chain |
| T021 | Implement acceptance against the durable gate receipt | WP04 | No; sequential dependency chain |
| T022 | Build only the committed data-free baseline | WP04 | No; sequential dependency chain |
| T023 | Test data-loss, copy races and privacy failures | WP04 | No; sequential dependency chain |
| T024 | Confirm real callers and Python 3.12 CLI behaviour | WP04 | No; sequential dependency chain |
| T025 | Make route tests explicitly phase-aware | WP05 | No; sequential dependency chain |
| T026 | Derive current rollback-version expectations | WP05 | No; sequential dependency chain |
| T027 | Document repeat-cutover operation and recovery | WP05 | No; sequential dependency chain |
| T028 | Package every repeat-cutover dependency in the candidate | WP05 | No; sequential dependency chain |
| T029 | Validate docs and the complete phase test matrix | WP05 | No; sequential dependency chain |
| T030 | Generate the qualified data-free baseline with Claude | WP06 | No; sequential dependency chain |
| T031 | Bind the published release and exact rollback identities | WP06 | No; sequential dependency chain |
| T032 | Create the queued STAGE manifest | WP06 | No; sequential dependency chain |
| T033 | Validate the STAGE phase and PR1 boundary | WP06 | No; sequential dependency chain |
| T034 | Create the queued ACTIVATE manifest | WP07 | No; sequential dependency chain |
| T035 | Promote machine inventory and narrative together | WP07 | No; sequential dependency chain |
| T036 | Validate ACTIVATE and prove the exact PR2 diff | WP07 | No; sequential dependency chain |

## WP01 — Release and archive compatibility

**Summary**: Both gzip and historical tar records pass only with pinned bytes and verified identities.
**Priority**: P1
**Owner**: implementer-ivan; implementer; codex / gpt-6.1-sol.
**Reviewer**: Claude Sonnet 5.5.
**References**: FR-001, FR-002, FR-003.
**Independent test**: `python3 -m pytest -q tests/deploy/test_vikunja_release_core.py tests/deploy/test_vikunja_release_readiness.py tests/deploy/test_deploy_vikunja_release_stage.py tests/deploy/test_vikunja_stage_release_archive.py`.

### Subtasks

T001 Accept rrule versions and refuse malformed suffixes (WP01)
T002 Parse gzip after pinning the original archive bytes (WP01)
T003 Verify tagged Docker imports and preflight collisions (WP01)
T004 Validate an optional baseline binding shape (WP01)
T005 Make shared CLI failures emit stable codes only (WP01)
T006 Freeze the first-cutover record and isolate historical tests (WP01)

### Implementation sketch

- Freeze the existing release metadata before WP06 changes it.
- Extend version/archive/binding validation in the shared core, then tagged-load handling in STAGE.
- Prove the privacy failure path and historical isolation with injected runners.

Dependencies: none

### Risks

- An imported tag collision can destroy a prior binding; preflight all validated RepoTags.
- Compressed-byte pinning can regress through a reopen; retain the same-handle race tests.
- Core schema changes affect all callers; preserve strict validation and absent-baseline compatibility.

Prompt: `tasks/WP01-release-and-archive-compatibility.md`


## WP02 — Rollback correctness

**Summary**: A correct RRULE snapshot restore succeeds and wrong hash or exact version fails before image mutation.
**Priority**: P1
**Owner**: implementer-ivan; implementer; codex / gpt-6.1-sol.
**Reviewer**: Claude Sonnet 5.5.
**References**: FR-004, FR-005, FR-006, FR-007.
**Independent test**: `python3 -m pytest -q tests/deploy/test_vikunja_release_db.py tests/deploy/test_vikunja_rollback.py`.

### Subtasks

T007 Replace the obsolete rollback schema criterion (WP02)
T008 Require exact pre_version before tag or start (WP02)
T009 Recover unfinished pre-snapshot markers under both locks (WP02)
T010 Count repeats edits and label backfill privately (WP02)
T011 Remove private DB safety reporting (WP02)
T012 Adopt the frozen fixture and reverse obsolete expectations (WP02)

### Implementation sketch

- Change the low-level guard and propagate the exact reviewed rollback version.
- Extend marker recovery without admitting any post-snapshot phase.
- Repair write counting and privacy producers, then migrate historical fixture consumers.

Dependencies: WP01

### Risks

- Starting an image before version validation risks irreversible incompatibility; assert call order.
- An unfinished marker is admissible only in started/stopped, with exact identity checks and both locks.
- Gate failure after snapshot must continue to require snapshot restore, handled in WP03 integration tests.

Prompt: `tasks/WP02-rollback-correctness.md`


## WP03 — Baseline module and ACTIVATE gate

**Summary**: Every mismatch fails before release image selection and persists the designed marker error.
**Priority**: P1
**Owner**: implementer-ivan; implementer; codex / gpt-6.1-sol.
**Reviewer**: Claude Sonnet 5.5.
**References**: FR-008, NFR-001, NFR-002, NFR-003, C-005.
**Independent test**: `python3 -m pytest -q tests/deploy/test_vikunja_release_baseline.py tests/deploy/test_deploy_vikunja_release_activate.py`.

### Subtasks

T013 Load and authenticate the bound baseline (WP03)
T014 Implement versioned schema identity (WP03)
T015 Share comparison, aggregates and data-free build logic (WP03)
T016 Write a durable private baseline receipt (WP03)
T017 Gate ACTIVATE between snapshot persistence and retag (WP03)
T018 Scrub every ACTIVATE private detail producer (WP03)
T019 Prove failure ordering, replay and snapshot rollback recovery (WP03)

### Implementation sketch

- Implement trusted data-free baseline loading and deterministic comparison in a new shared module.
- Add a separately validated durable receipt, then integrate at the existing snapshot-to-tag boundary.
- Test full failure/replay/recovery ordering with injected clocks and Docker.

Dependencies: WP01 WP02

### Risks

- Synchronous SQLite work can overrun deadlines; include bounded query execution and elapsed-time checks.
- SQLite schema text can change during consolidation; test the actual route on both CI runtimes.
- Cleanup failure is a distinct state; never claim successful absence if cleanup failed.

Prompt: `tasks/WP03-baseline-module-and-activate-gate.md`


## WP04 — Preflight, acceptance verifier, baseline builder

**Summary**: Preflight removes temporary copies on every exit and labels instability inconclusive.
**Priority**: P1
**Owner**: implementer-ivan; implementer; codex / gpt-6.1-sol.
**Reviewer**: Claude Sonnet 5.5.
**References**: FR-009, FR-013, SC-004.
**Independent test**: `python3 -m pytest -q tests/deploy/test_vikunja_release_preflight.py tests/deploy/test_vikunja_release_acceptance.py`.

### Subtasks

T020 Implement stable-copy preflight (WP04)
T021 Implement acceptance against the durable gate receipt (WP04)
T022 Build only the committed data-free baseline (WP04)
T023 Test data-loss, copy races and privacy failures (WP04)
T024 Confirm real callers and Python 3.12 CLI behaviour (WP04)

### Implementation sketch

- Wrap shared baseline functions in three small stdlib operator CLIs.
- Reuse the existing consolidation design on private filesystem copies, with deterministic copy-race tests.
- Validate live call wiring through local CLI tests and hand exact usage to WP05.

Dependencies: WP03

### Risks

- Copying a live WAL set can produce false confidence; require agreement and bounded retries.
- Receipt/baseline identity confusion can admit another release; validate all binding fields.
- Builder metadata creep can disclose private facts; use an exact output whitelist.

Prompt: `tasks/WP04-preflight-verifier-and-builder.md`


## WP05 — Phase-aware change-set tests and repeat-cutover runbook

**Summary**: Focused tests pass on the current tree and synthetic STAGE/ACTIVATE trees.
**Priority**: P2
**Owner**: implementer-ivan; implementer; codex / gpt-6.1-sol.
**Reviewer**: Claude Sonnet 5.5.
**References**: FR-012, NFR-004, C-001, C-003, C-004.
**Independent test**: `python3 -m pytest -q tests/deploy/test_vikunja_cutover_change_set.py tests/deploy/test_vikunja_release_consistency.py`.

### Subtasks

T025 Make route tests explicitly phase-aware (WP05)
T026 Derive current rollback-version expectations (WP05)
T027 Document repeat-cutover operation and recovery (WP05)
T028 Package every repeat-cutover dependency in the candidate (WP05)
T029 Validate docs and the complete phase test matrix (WP05)

### Implementation sketch

- Parameterize phase evaluation while explicitly freezing historical checks.
- Derive current identity assertions from current release metadata and previous deployed identity.
- Rewrite current runbook sections and validate all local documentation and tests.

Dependencies: WP04

### Risks

- Latest-applied fallback can silently validate history; current queued invalidity is an unconditional failure.
- Premature inventory promotion misstates running production; gate it on ACTIVATE phase.
- Historical conversion commands can be mistaken for current steps; label and separate them clearly.

Prompt: `tasks/WP05-phase-tests-and-repeat-cutover-runbook.md`


## WP06 — STAGE change set

**Summary**: Committed baseline is data-free and bound by its exact bytes to the new release record.
**Priority**: P1
**Owner**: implementer-ivan; implementer; claude / claude-opus-5-5.
**Reviewer**: Claude Sonnet 5.5.
**References**: FR-010, SC-001, C-002.
**Independent test**: `python3 -m pytest -q tests/deploy/test_vikunja_cutover_change_set.py tests/deploy/test_vikunja_release_core.py tests/deploy/test_deploy_vikunja_release_stage.py tests/deploy/test_vikunja_release_baseline.py tests/deploy/test_vikunja_release_acceptance.py`.

### Subtasks

T030 Generate the qualified data-free baseline with Claude (WP06)
T031 Bind the published release and exact rollback identities (WP06)
T032 Create the queued STAGE manifest (WP06)
T033 Validate the STAGE phase and PR1 boundary (WP06)

### Implementation sketch

- Claude generates qualification through the reviewed builder using privately held inputs.
- Populate the release trust root from the held packet and bind the baseline.
- Create only STAGE metadata, then run the full phase-aware suite before review.

Dependencies: WP05

### Risks

- The baseline cannot be supplied by Codex; keep execution assigned to Claude Opus 5.5.
- Packet identities are provenance inputs, not evidence that a fresh download was verified.
- An accidentally included ACTIVATE manifest would cut over on merge; inspect exact PR1 paths.

Prompt: `tasks/WP06-stage-change-set.md`


## WP07 — ACTIVATE change set

**Summary**: ACTIVATE and inventory share exact current identities; Compose retains active/never.
**Priority**: P1
**Owner**: implementer-ivan; implementer; codex / gpt-6.1-sol.
**Reviewer**: Claude Sonnet 5.5.
**References**: FR-011, SC-002, SC-003, SC-005, C-001, C-002, C-006, C-007.
**Independent test**: `python3 -m pytest -q tests/deploy/test_vikunja_cutover_change_set.py tests/deploy/test_vikunja_release_consistency.py`.

### Subtasks

T034 Create the queued ACTIVATE manifest (WP07)
T035 Promote machine inventory and narrative together (WP07)
T036 Validate ACTIVATE and prove the exact PR2 diff (WP07)

### Implementation sketch

- Build a release-exact ACTIVATE manifest from established phase-aware postchecks.
- Promote Vikunja JSON and narrative inventory in the same PR.
- Validate the ACTIVATE phase and actual PR2 path equality before merge by Kent, the program lead or the core worker under Kent's delegation.

Dependencies: WP06

### Risks

- Premature PR2 creation can trigger a cutover before qualification; require applied STAGE and preflight evidence.
- Inventory drift can conceal wrong image identity; compare both views with release.json.
- A constant path set is not diff evidence; inspect the actual PR2 range during assembly.

Prompt: `tasks/WP07-activate-change-set.md`

## Sequencing

Execute WP01 → WP02 → WP03 → WP04 → WP05 → WP06 → WP07. Ownership is disjoint; no code WP owns a kitty-specs path.
All WPs consolidate onto fix/vikunja-repeat-cutover, which is never merged to main whole. PR1 is a branch from main with the mission tree minus WP07’s paths (plan D5). WP06 is implemented by Claude Opus 5.5 using privately held qualification inputs.
PR2 contains exactly the ACTIVATE manifest and the two inventory paths owned by WP07. Open it only after STAGE applies and preflight passes.
Validate the actual PR path sets during assembly; phase-test constants and file existence are not diff proof.
Kent or the program lead merges. Kent retains privileged restore, browser acceptance and ACCEPT or ROLLBACK.
Required final checks: `python3 -m pytest -q --ignore=docs/archive` and `python3 tooling/scripts/validate_docs.py`.
