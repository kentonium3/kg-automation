# Mission Specification: 849 Arms Run Pre-Run Preconditions

**Mission Branch**: `feat/849-preconditions`
**Created**: 2026-09-26
**Status**: Draft
**Input**: kentonium3/kg-automation#1023 (spec: ready). Intent Summary confirmed by Kent in-session on 2026-09-26 (Decision Moment 01M3FVTDF8QAP577RE8E0D4DW0).

## Context

Mission `arms-run-01M3APTA` (#849) merged the three retrieval arms — **G** (typed graph), **D** (full dump) and **R** (vector retrieval) — together with the run ledger, the gate phases, the samplers, the harness and blinded grading. The merged tree is deliberately **not runnable**. The pre-registration (`docs/design/research/849-rubric.md` §10) lists preconditions that the first live cell may not precede, each "verified by a test, not by assertion". The post-merge review added one more, C13 (arm registration). This mission delivers them. The 72-cell decisive run and the blinded grading follow afterwards **as an operation**, not as part of this mission.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Every arm can actually run (Priority: P1)

The run operator — Kent, or an agent acting on his instruction on office4 — starts a live run, and each of the three arms answers its cells through the harness with its real dependencies. At present every cell would be recorded as "could not run".

**Why this priority**: Without it no result exists at all. Every other precondition protects a run that cannot yet happen.

**Independent Test**: With the research environment present, starting a session yields registered G, D and R arms sharing one embedder. A session with no arms registered cannot produce a ledger that counts as a complete primary.

**Acceptance Scenarios**:

1. **Given** the research environment on office4, **When** a live session starts, **Then** G, D and R are each registered with their own refusal class, and G and R share one embedder.
2. **Given** no arms are registered, **When** a full plan is executed, **Then** every cell records "could not run", and the resulting ledger is refused as a primary.
3. **Given** an arm refuses because of a configuration defect, **When** the attempt ends, **Then** the cell is terminal on the first attempt and is never retried.

---

### User Story 2 — The graph-store memory column is real and self-describing (Priority: P1)

For every G cell the operator gets a memory peak measured as the rubric registers it. The peak carries its supporting detail, so a reader can tell a well-supported peak from one that rests on a single held reading.

**Why this priority**: Memory is a registered measure (rubric §5). Until the series is wired, the harness correctly refuses every G cell.

**Independent Test**: Drive a synthetic series through the real measurement path. A G row carries the peak and its support. Absent, stale, gapped or wrong-container data refuses the cell.

**Acceptance Scenarios**:

1. **Given** a healthy series, **When** a G cell completes, **Then** its row holds the peak and its support: window bounds, in-window sample count, held timestamp, and whether the peak came from the held reading or from inside the window.
2. **Given** a series that is absent, stale, gapped or from the wrong container, **When** a G cell starts, **Then** the cell is refused as unmeasurable and is never recorded as zero or as a pass.
3. **Given** a G row without valid support, **When** it is written or replayed, **Then** the ledger refuses it.

---

### User Story 3 — A ceiling breach sends nothing (Priority: P1)

If memory is above the registered ceiling at the last moment before a request would be sent, nothing is sent and the session stops.

**Why this priority**: This protects office4 and the integrity of the run. The recorded peak remains authoritative (§5), but the guard must fire at the last point the protocol controls.

**Independent Test**: Force the ceiling reading above the threshold at send time and observe that no request leaves and the session stops.

**Acceptance Scenarios**:

1. **Given** the ceiling is breached at send time, **When** any arm sends, **Then** no request is sent, the breach reaches the harness unaltered, and the session stops with the breach recorded.
2. **Given** the ceiling is not breached, **When** an arm sends, **Then** the request proceeds unchanged.

---

### User Story 4 — A run survives interruption (Priority: P2)

A run interrupted mid-way can be resumed by a fresh session. The resumed session re-runs its own gates, and every earlier row survives unchanged.

**Why this priority**: 72 cells take hours. Resume is the recovery path, and it has only been tested with fakes whose timestamps never change, which is how the defect it now guards was hidden.

**Independent Test**: Run real gate phases in session 1, stop, then resume in a fresh session with fresh gate phases. Check the negatives as well.

**Acceptance Scenarios**:

1. **Given** a ledger interrupted mid-run, **When** a fresh session resumes, **Then** it records its own gate outcome and completes, with earlier rows byte-identical and nothing recorded twice.
2. **Given** a fresh session whose gates fail, **When** it resumes, **Then** it stops and records the failure without attempting a cell.
3. **Given** a session that skipped its gate phase, **When** it tries to record an attempt, **Then** the attempt is refused.

---

### User Story 5 — The evidence is complete and honest (Priority: P2)

The operator can trust what the harness and the ledger say about themselves:
- the isolation check covers every module of the run package;
- every attempt names the session whose gates authorised it;
- timestamps have a single canonical form;
- the registered token table can be re-measured at code freeze.

**Why this priority**: Each is a place where the record could otherwise read identically whether a property held or was never checked.

**Independent Test**: Each item has its own can-fail test.

**Acceptance Scenarios**:

1. **Given** a module is added to or removed from the run package, **When** the isolation check runs, **Then** the registered inventory and the package disagree, and the check fails.
2. **Given** an attempt whose session recorded no passing gates, **When** the ledger is replayed, **Then** it is refused, even if an earlier session's gates stand above it.
3. **Given** the code is frozen, **When** the token table is measured, **Then** all 8 questions report their request tokens, block tokens and prefix sharing, and the count of questions that exceed the model's context is still 6 of 8.

---

### User Story 6 — The research suite's coverage is visible (Priority: P3)

Anyone reading a test run can see which research tests ran and which were skipped for lack of the research environment. A merge to main records that the office4 suite ran.

**Why this priority**: CI does not exercise the arms (Kent, 2026-09-26). The office4 run is their only coverage, so it must be stated and recorded, not implied.

**Independent Test**: In an environment without the research stack, the research tests report named, counted skips and none errors. The pre-merge record names the commit and the result.

**Acceptance Scenarios**:

1. **Given** an environment without the research stack, **When** the full suite runs, **Then** the research tests report named skips and the suite passes.
2. **Given** a merge to main is about to happen, **When** the pre-merge check runs, **Then** a record exists of the office4 suite run and of a fresh-worktree simulation of CI, each with the commit and the result.

### Edge Cases

- The graph store's asynchronous client is bound to one event loop, while the harness runs each attempt on a fresh thread. Cancellation and timeouts must not leave an orphaned attempt.
- The memory series has not produced its first reading yet when the first G cell starts.
- The container is replaced mid-run under the same name.
- A timeout or cancellation arrives while a ceiling check or a graph build is in progress.
- Session 2 of a resume has a different process start time and different gate timestamps from session 1.
- Duplicate or boundary-tied timestamps in the memory series, already covered by rubric §5's window rule.

## Requirements *(mandatory)*

### Functional Requirements

| ID | Title | User Story | Priority | Status |
|----|-------|------------|----------|--------|
| FR-001 | Arms registered (C13) | As the run operator, I want G, D and R registered with their real dependencies and one shared embedder, so that a live run answers cells instead of recording "could not run". | High | Open |
| FR-002 | G refusals and limit check (C13) | As the run operator, I want arm G to have its own refusal class and the same configuration check of the context limit as D and R, so that a configuration defect is terminal on the first attempt for every arm. | High | Open |
| FR-003 | One refusal class, no fallbacks (C13) | As a maintainer, I want the arms' refusal classes unified and the transitional configuration fallbacks removed, so that terminality is decided in one place and the contract name is the only path. | Medium | Open |
| FR-004 | No-arms run is never a primary (C13, Condition A) | As the run operator, I want a test proving that a run with no registered arms cannot produce a primary-complete ledger, red before the fix, so that the fail-safe is demonstrated rather than argued. | High | Open |
| FR-005 | Memory series end to end (C9) | As the run operator, I want each G cell's memory peak read from the real measurement series as rubric §5 registers it, so that the graph-store column is measured rather than refused. | High | Open |
| FR-006 | Peak support recorded (C9) | As a reader of the results, I want each G row to carry its peak's support (window bounds, in-window count, held timestamp, peak source) and the ledger to validate it on write and replay, so that a weakly supported peak is distinguishable. | High | Open |
| FR-007 | Unmeasurable fails closed (C9) | As the run operator, I want absent, stale, gapped or wrong-container series data to refuse the cell through the real path, so that an unmeasurable peak is never recorded as zero or as a pass. | High | Open |
| FR-008 | Ceiling guard at send (C11) | As the run operator, I want the memory ceiling checked immediately before each request is sent, with nothing sent on a breach and the breach reaching the harness unaltered, so that the guard fires at the last point the protocol controls. | High | Open |
| FR-009 | Live-style resume (C8) | As the run operator, I want a resume across real, timestamp-bearing gate phases to complete with earlier rows intact, and both negatives (a failing fresh gate stops and records; a session that skipped its gates cannot write a row) demonstrated, so that recovery is proven before the run depends on it. | High | Open |
| FR-010 | Complete isolation inventory (C4) | As the run operator, I want the isolation check to name every module of the run package, with a two-way test, so that a truncated package cannot certify isolation. | Medium | Open |
| FR-011 | Attempts name their session | As a reader of the ledger, I want each attempt to carry the id of the session that wrote it and replay to check that session's gates, so that one session's gates can never authorise another's attempts. | Medium | Open |
| FR-012 | Canonical UTC timestamps (C12) | As a reader of the memory series, I want only canonical UTC timestamps accepted, so that every accepted timestamp is exactly what the writer emits. | Low | Open |
| FR-013 | Token table measurable at freeze (T039) | As the design lead, I want the §2 token table re-measurable at code freeze for all 8 questions, so that the registered numbers are confirmed on the final assembled requests. | Medium | Open |
| FR-014 | Research-environment gating | As a maintainer, I want the research suite's environment requirement stated once, with named, counted skips where it is absent, so that CI results distinguish "skipped for environment" from "passed". | Medium | Open |
| FR-015 | Office4 pre-merge record | As Kent, I want every merge to main from this work to carry a record of the office4 suite run and a fresh-worktree CI simulation, each with commit and result, so that the arms' only coverage is a gate rather than a habit. | Medium | Open |

### Non-Functional Requirements

| ID | Title | Requirement | Category | Priority | Status |
|----|-------|-------------|----------|----------|--------|
| NFR-001 | Suite green in both environments | 100% of tests pass on office4 with the research environment, under both PYTHONHASHSEED 0 and 3, and in a fresh-worktree CI simulation without it, with 0 collection errors. | Reliability | High | Open |
| NFR-002 | Can-fail evidence | Every functional requirement has at least one test that fails on the pre-change code; the evidence is recorded per work package. | Reliability | High | Open |
| NFR-003 | No orphaned attempts | Across 100 consecutive attempts with injected timeouts and cancellations against a fake graph store, 0 attempts remain running after their deadline. | Reliability | High | Open |
| NFR-004 | Measurement freshness | The memory series tolerances stay as registered: a gap or staleness of more than 5 sample intervals refuses the cell, and exactly 5 is allowed. | Accuracy | High | Open |
| NFR-005 | Fail closed | 0 paths record an unmeasurable, refused or unregistered cell as a score, a zero or a pass. | Integrity | High | Open |

### Constraints

| ID | Title | Constraint | Category | Priority | Status |
|----|-------|------------|----------|----------|--------|
| C-001 | Pre-registration fixed | No registered rubric value, frozen corpus, oracle or fingerprint changes. Any rubric text change is a dated design-lead amendment. | Research integrity | High | Open |
| C-002 | Preconditions proven by tests | Each rubric §10 precondition is satisfied by a test, never by the live run it protects (design-lead ruling 2026-09-26 20:02Z). | Research integrity | High | Open |
| C-003 | No CI coverage change | No change to `requirements.txt` or to CI workflow files; CI does not exercise the arms (Kent, 2026-09-26). | Business | High | Open |
| C-004 | office4 only | Runs on office4 (research sandbox, ADR-0008); no office2 deploy, no audited-surface change. | Technical | High | Open |
| C-005 | One sequential lane | Work packages execute in one sequential lane, so each sees the previous packages' code (#1018). | Process | High | Open |
| C-006 | Design rulings before plan | The measurement source for the memory column, the recording of a breach at send, and G's terminal errors are ruled by the design lead before planning (bus request 20260926T220152814799Zd8d8b2ef8c). | Process | High | Open |
| C-007 | Out of scope | The 72-cell run, blinded grading, and spec-kitty upstream issues are not part of this mission. | Business | High | Open |

### Key Entities

- **Arm registration**: an arm's answering function (or binding), its refusal class, and anything it needs (embedder, graph store connection).
- **Memory support**: the evidence behind one reported peak — window start and end, number of in-window samples, the held reading's timestamp if used, and the peak's source.
- **Session gates record**: a session's gate outcome (session id, passed, skipped), which authorises that session's attempts.
- **Pre-merge record**: commit, office4 suite result, and fresh-worktree CI simulation result.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A live session on office4 registers 3 of 3 arms. A run with 0 registered arms yields 0 ledgers accepted as primary.
- **SC-002**: 100% of G cells in an end-to-end test carry a memory peak with complete support. 4 of 4 unmeasurable conditions (absent, stale, gapped, wrong container) refuse the cell.
- **SC-003**: With the ceiling breached at send time, 0 requests are sent and the session stops.
- **SC-004**: A resumed run completes with 100% of earlier rows byte-identical and 0 double-recorded cells. Both negative cases behave as specified.
- **SC-005**: The isolation inventory matches the package in both directions (17 of 17 modules today).
- **SC-006**: The token table reports 8 of 8 questions, and the context-exceedance split remains 6 of 8.
- **SC-007**: The full suite passes both on office4 and in the fresh-worktree CI simulation, with 0 failures and 0 collection errors. Every merge to main carries the pre-merge record.

## Assumptions

- The research environment (graph-store client, embedder, rendered corpus, tokenizer cache) exists on office4 only.
- G's graph construction already exists. What is missing is registration and lifecycle plumbing.
- The sampler's series writer and reader already exist (the WP04 reopen). What is missing is running the writer during the run and binding the reader.
- The design-lead rulings named in C-006 arrive before planning. If a ruling changes a requirement's WHAT, the spec is amended before plan.

## Dependencies

- Rubric §5 (memory columns, window reconstruction, process-level rule) and §10 (preconditions).
- The contracts of mission arms-run-01M3APTA (arm-interface, ledger-schema, gates, data-model), which this mission amends with dated sentences where behaviour changes.
- kentonium3/kg-automation#1023 (this scope), #849 (parent), #1018 (lane topology), #1021 (merge-fault history).
