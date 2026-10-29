# Mission Specification: Backup alerts name why the run failed

**Mission Branch**: `fix/backup-failure-cause-in-alert`
**Created**: 2026-10-15
**Status**: Draft
**Input**: kentonium3/kg-automation#1067. The intent summary was confirmed by Kent on 2026-10-15 (decision `01M502KQCV8SMFM13ZPZ5PZZTA`).

## Context

Since #1063, a failed nightly backup pages Kent within about 15 minutes. The canary evaluates the backup's state pointer against its declared key ledger every 15 minutes, and felix-health-check repeats that evaluation as a coverage check. The page names the **pointer key** that failed, not the **cause**. A run on 2026-09-27..10-14 found the backup drive unmounted. A page for a run like that reads as a key failure such as `restic_exit_code=127` (the script's "never attempted" sentinel), and the operator has to open the backup log to learn the drive is missing.

Two alternatives were rejected on 2026-10-15:
- Having the backup script call the alert bus directly. The script runs as root, and the alert bus is code the `claude` user can write. Root running it is equivalent to granting `claude` root (#899).
- A separate path watcher. It would page a second time for every failure the canary already pages for.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The page says the drive is missing (Priority: P1)

The 04:00 backup runs with the backup drive unmounted. Within the canary's next tick, Kent receives the usual `restic-backup health: failed` alert. Its text now also says, in plain words, that the backup drive is not mounted, so he knows to reseat the drive without reading a log.

**Why this priority**: this is the exact incident behind #1063 and #1067, and the most likely failure.

**Independent Test**: feed the canary evaluator a pointer from a not-mounted run and assert that the alert text contains the plain-words cause. Separately, run the backup script with a test mount point that is not mounted and assert that the pointer records the not-mounted cause.

**Acceptance Scenarios**:

1. **Given** a run that exits because the backup mount is missing, **When** the pointer is written, **Then** it records the not-mounted cause code.
2. **Given** that pointer, **When** the canary evaluates `restic-backup`, **Then** the outcome is still `failed`, and the alert evidence includes the cause's plain-words description.
3. **Given** that pointer, **When** felix-health-check runs its `restic-backup` coverage check, **Then** the coverage line also carries the cause.

---

### User Story 2 - Every fatal failure names its cause (Priority: P2)

A run can also end because the restic repository can't be opened, because `restic backup` itself fails, or because the script stops in a way it did not classify. Each of these pages with a cause that tells the cases apart.

**Why this priority**: the other fatal exits are rarer, but today they all page with keys that look alike.

**Independent Test**: drive the backup script down each fatal exit with test overrides and assert the recorded cause code.

**Acceptance Scenarios**:

1. **Given** a run whose repository check fails, **Then** the pointer records the repo-inaccessible cause.
2. **Given** a run whose `restic backup` returns a failing code, **Then** the pointer records the backup-failed cause.
3. **Given** a run that exits non-zero by a path the script does not classify, **Then** the pointer records an explicit "unclassified" cause, never `null`.
4. **Given** a run that completes, including one where only the prune or the weekly integrity check failed, **Then** the cause is `null`. Those conditions already page under their own self-describing keys.

---

### User Story 3 - Nothing else changes (Priority: P1)

Before Kent installs the new backup script, and for every other component the canary watches, alerts read and fire exactly as they do today.

**Why this priority**: this is a monitoring path; a regression could silence a page.

**Independent Test**: evaluate today's real pointer shape, which has no cause key, plus pointers with a `null`, wrong-type, oversized or unknown cause. Assert that outcome, evidence and alert cadence are identical to today, apart from the defined enrichment for a known cause.

**Acceptance Scenarios**:

1. **Given** a pointer with no cause key, **Then** canary and health-check verdicts and evidence are byte-identical to today's.
2. **Given** a cause value that is not a known code, **Then** health is unchanged, the evaluator does not raise, and the evidence either carries no cause or carries a safely bounded marker. It never carries arbitrary pointer text.
3. **Given** a healthy pointer with a non-null cause, **Then** health stays healthy. A cause never creates, suppresses or changes a verdict.

### Edge Cases

- **Pointer written by the old script.** There is no cause key, and behaviour is identical to today.
- **Cause present but the outcome is healthy.** Treated as inconsistent. The verdict is unchanged and no cause is shown.
- **Cause present and the outcome is `unknown`** (the pointer could not be evaluated). The verdict is unchanged; the cause may be shown.
- **A hostile or corrupt cause string**, for example very long or containing control characters or markup. It never reaches alert text verbatim; only declared codes map to text.
- **The reconciliation harness.** The new key must be declared in the ledger, or the existing harness fails.
- **The live script is still the old one.** `backup-script-drift` reports drift until Kent installs the new one, which is expected and recorded as outstanding.

## Requirements *(mandatory)*

### Functional Requirements

| ID | Title | User Story | Priority | Status | Delivery | No-op passable? |
|----|-------|------------|----------|--------|----------|-----------------|
| FR-001 | Script records the not-mounted cause | As Kent, I want a run that exits because the backup mount is missing to record a not-mounted cause code in its pointer, so that the alert can say so. | High | Open | [build] | no — today's script writes no cause key, so the assertion fails |
| FR-002 | Script records the other fatal causes | As Kent, I want the repo-inaccessible, backup-failed and unclassified fatal exits each to record their own cause code, so that failures are distinguishable. | High | Open | [build] | no — no cause key exists today |
| FR-003 | Clean runs record no cause | As Kent, I want a completed run, including prune-only or integrity-only failures, to record a `null` cause, so that the cause never implies a fatal failure that did not happen. | High | Open | [build] | no — paired with FR-001 on the same harness; the key must exist and be `null` |
| FR-004 | Ledger declares the cause key | As a maintainer, I want the `restic-backup` key ledger to declare the cause key as diagnostic-only, and to declare which key carries a cause and the plain-words text for each code, so that the reconciliation harness stays green and nothing is keyed on component names. | High | Open | [build] | no — the harness fails if the producer emits an undeclared key |
| FR-005 | Canary alert names the cause | As Kent, I want the canary's failed-outcome evidence for a pointer with a known cause code to include that code's declared plain-words text, so that the page tells me what to fix. | High | Open | [build] | no — today's evidence contains no cause text for the not-mounted fixture |
| FR-006 | Health-check coverage names the cause | As Kent, I want felix-health-check's `restic-backup` coverage finding to carry the same cause text, so that both watchers agree. | Medium | Open | [build] | no — asserted on the same not-mounted fixture as FR-005 |
| FR-007 | The cause never changes a verdict | As Kent, I want the outcome (`ok`/`failed`/`unknown`/stale) and alert cadence to be computed exactly as today, regardless of the cause key, so that diagnostics cannot silence or create a page. | High | Open | [ratchet] | yes — paired with FR-005: the same fixture with the cause removed must give the same outcome |
| FR-008 | Unknown or malformed causes fail safe | As Kent, I want an absent, `null`, wrong-type, unknown or oversized cause to leave today's evidence unchanged, or add only a bounded fixed marker, and never raise, so that a corrupt pointer cannot break or inject into alerts. | High | Open | [build] | no — includes an injection fixture whose raw text must not appear in the evidence |
| FR-009 | Runbook and inventory explain the cause | As an operator, I want `restic-backup-ops.md` to list the cause codes and what to do for each, and the inventory note to mention the key, so that the alert text and the docs agree. | Medium | Open | [build] | no — a doc check asserts that every declared code appears in the runbook |

### Non-Functional Requirements

| ID | Title | Requirement | Category | Priority | Status |
|----|-------|-------------|----------|----------|--------|
| NFR-001 | No added page volume | For every fixture in the test suite, the number and timing of alerts decided by dedup is identical with and without a cause key (0 extra emits). | Reliability | High | Open |
| NFR-002 | Bounded alert text | The cause text added to any evidence string is at most 120 characters and contains only text declared in the ledger, never pointer-supplied bytes. | Security | High | Open |
| NFR-003 | The script fails soft | Computing or writing the cause can never change the backup script's own exit status or prevent the pointer from being written. Verified on 100% of fatal-exit test paths. | Reliability | High | Open |
| NFR-004 | No regression | The full test suite passes, with 0 new failures against `main`. | Quality | High | Open |

### Constraints

| ID | Title | Constraint | Category | Priority | Status |
|----|-------|------------|----------|----------|--------|
| C-001 | No root-to-claude code edge | The backup script must not invoke, source or import any file the `claude` user can write. The cause is data in the pointer only. | Security | High | Open |
| C-002 | Manual install of the backup script | The live `backup.sh` is installed by hand by Kent (operator handoff in `restic-backup-ops.md`); the pipeline must not install it or make its directory claude-writable (#899). The mission records the install as outstanding until `backup-script-drift` reports converged. | Security | High | Open |
| C-003 | Declared, not keyed on names | The canary mechanism is driven by the ledger declaration. No canary or health-check code may branch on the `restic-backup` component name. | Technical | High | Open |
| C-004 | Diagnostic-only | The cause key is declared `diagnostic_only` and must not become adjudicated or affect freshness. | Technical | High | Open |
| C-005 | Scope | Out of scope: a run that never happens (staleness is already covered), a new alert source, any change to sudoers or the deployed script path, and any change to dedup. | Business | Medium | Open |

### Key Entities

- **Backup state pointer** (`last-backup.json`): the per-run JSON document written by the backup script on every exit. It gains one key, the failure cause.
- **Failure cause code**: a short, closed vocabulary (not mounted, repo inaccessible, backup failed, unclassified). It is `null` on a completed run.
- **Key ledger** (`restic-backup` `health_check.key_ledger` in `service-inventory.json`): the declaration of what each pointer key means. It gains the cause key (diagnostic-only), plus which key carries a cause and the plain-words text for each code.
- **Evidence**: the human-readable string carried by a canary or health-check verdict, which becomes the alert description.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For a not-mounted run, the alert Kent receives states that the backup drive is not mounted, with no log lookup needed. — [build] · no-op passable: no
- **SC-002**: Each of the 4 fatal-exit causes produces a distinct alert description. — [build] · no-op passable: no
- **SC-003**: 0 changes in verdict or alert count across all existing canary and health-check fixtures. — [ratchet] · no-op passable: yes — paired with SC-001's positive fixture
- **SC-004**: After deploy, the next canary tick on office2 evaluates `restic-backup` with the same outcome as before deploy (`tick_error` count 0). — [ratchet] · no-op passable: yes — paired with SC-001

## Assumptions

- The canary and felix-health-check run from the office2 checkout, so the evaluator change goes live when felix-deployer pulls the merge. The plan confirms whether a manifest is needed.
- Canary and inventory files are not audited surfaces. The plan confirms this against `audited-surfaces.json`.
- Dedup keys on outcome and the optional run-identity signal, not on evidence text (verified in `scripts/canary/dedup.py`), so enriching evidence does not change cadence.
