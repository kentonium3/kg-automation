# Mission Specification: Backup Pointer Key Ledger

**Mission Branch**: `feat/934-pointer-key-ledger`
**Created**: 2026-08-30 · **Revised**: 2026-08-30 after the post-plan review point-cut
**Status**: Draft (v2 — supersedes the version committed at `61843458`)
**Input**: kentonium3/kg-automation#934 (body + the 2026-08-30 scope-decision comment). The office4
v0.2 design that shares this contract lives at `docs/design/office4-backup.md` **on branch
`feat/913-office4-restic-backup`, commit `fa6a669d`** — it is deliberately *not* on this branch, so
cite it by that commit, never by working-tree path.

> **Revision note.** v1 was reviewed by three independent lenses (Codex, reviewer-renata,
> paula-patterns) at the mandatory post-plan point-cut. All three returned "revise before tasks";
> ~39 findings, six found independently by more than one reviewer. v1 would have shipped a live
> regression of #902/FR-009, and overstated what its own mechanism guarantees. The material changes
> are recorded in *What the review changed* at the foot of this document.

## Problem

office2's nightly backup writes ten facts about each run into a state document that every health
surface reads. **Three of the ten decide health. Seven are inert** — written, then consulted by
nothing. One of the seven is the weekly `restic check` verdict, so a repository restic has *proven*
corrupt reports healthy everywhere, and the operator learns the truth at restore time, when the
backup is needed and can no longer be re-taken.

The narrow reading — "one field lacks a reader" — is the reading that produced the problem. A prior
mission on this component wrote a constraint forbidding unread fields (C-003), applied it to the
field it was adding, and never swept the field already sitting there. The constraint was enforced by
review, and review forgot.

### The generative rule

> **Every key emitted into the backup's state document is either (a) adjudicated, with an explicit
> definition of what "good" means for it, or (b) declared as kept for diagnosis only, with a stated
> reason. A test enumerates the keys the producer *actually emits* — by executing it — and fails if
> any key is in neither list.**

**What this does and does not buy.** It makes *silent* inertness impossible: a new key cannot be
ignored by default, because the suite goes red until someone places it. It does **not** remove the
reviewer from the loop — `diagnostic_only` remains an escape hatch, and a good-set spanning the whole
value domain adjudicates nothing. What changes is that an inert key stops being the default and
becomes a line in a diff, with a written reason attached. That is a real improvement and it is the
honest size of it. Claiming more is how C-003 came to be trusted.

## What this mission does not close

Stated up front because v1 buried it. The office4 v0.2 review's decisive verdict was that a backup
capturing an **empty snapshot**, onto a **98%-full disk**, into a **corrupting repository**, with a
**dead alerter**, reported healthy on all six of its rules.

| Leg | After this mission | Why |
|---|---|---|
| Corrupting repository | **Closed** | `integrity_check_passed` adjudicated (FR-001) |
| Integrity check silently stops running | **Closed** | `last_integrity_check_utc` added and adjudicated (FR-012) |
| Empty snapshot | **Closed** | `files_processed` + `source_roots_present` added and adjudicated (FR-013, FR-014) |
| Disk approaching full | **Closed** | `repo_fs_free_bytes` added and adjudicated (FR-015) |
| **Dead alerter** | **NOT closed** | See below |

**The alerter remains unwatched, and the reason is circular.** `felix-canary` is registered with a
`tick-signal-file` check reading its own tick pointer — and the only runtime process that probes that
pointer is the canary itself. A stopped timer does not run, therefore does not probe, therefore never
reports itself stale. office4's v0.2 solves this with an adjudicated `probe_last_tick_utc` *plus a
boot-time check*; office2 has neither. This mission does not fix it, and the assumption that
self-observation suffices is recorded as a **known false premise**, not an assumption (see
[Risks](#risks)).

Enforcement also covers the backup producers only. The other 16 pointer-emitting components remain
unledgered, tracked as kentonium3/kg-automation#937.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A repository proven corrupt stops reporting healthy (Priority: P1)

The backup verifies its repository weekly. When that verification fails, the operator is told,
through the surface that already reports every other component.

**Why this priority**: The reported defect, with unbounded cost — the repository is the only copy and
there is no off-site replica (#919), so corruption found late is permanent loss.

**Independent Test**: Present a state document carrying a failed verdict to the health evaluation and
confirm the component reads unhealthy with evidence naming the key.

**Acceptance Scenarios**:

1. **Given** a document whose integrity verdict is `false` and every other signal good, **When**
   health is evaluated, **Then** the component reads **unhealthy**, evidence naming the verdict.
2. **Given** a verdict of `null` because the check does not run today, **When** health is evaluated,
   **Then** the component reads **healthy**.
3. **Given** a verdict of `true`, **When** health is evaluated, **Then** healthy.
4. **Given** a verdict of the *string* `"false"` — a plausible shell-interpolation accident in a
   producer that builds JSON by interpolation — **When** health is evaluated, **Then** the component
   reads **unhealthy**, because a value outside the good-set is unhealthy regardless of type.

---

### User Story 2 - The verification cannot silently stop happening (Priority: P1)

A `null` verdict means "not checked today". Nothing today bounds how long that may persist.

**Why this priority**: Equal to US1, because it is US1's own defect one level up. Every backup
failure path in the producer returns *before* the weekly check runs, so a failed Sunday skips
verification entirely; the verdict stays `null` for a further seven days, all healthy. Repeated bad
Sundays leave the repository unverified for months while every surface reads green — and v1's success
criteria would have been *satisfied* throughout.

**Independent Test**: Present a document whose last-verification timestamp is older than the bound and
confirm unhealthy; present a recent one and confirm healthy.

**Acceptance Scenarios**:

1. **Given** a last-verification timestamp older than the bound, **When** health is evaluated,
   **Then** unhealthy, evidence naming the timestamp and its age.
2. **Given** a run in which the check does not execute, **When** the document is written, **Then** the
   last-verification timestamp carries forward from the previous run rather than resetting.
3. **Given** two consecutive missed Sundays, **When** the bound elapses, **Then** unhealthy — a single
   missed Sunday is tolerated, a persistent gap is not.

---

### User Story 3 - No emitted field can be silently inert (Priority: P1)

Each key is either load-bearing with a stated good-set, or explicitly marked recorded-for-diagnosis
with a reason. There is no third, accidental category.

**Why this priority**: The difference between fixing instances and closing the class.

**Independent Test**: Add a key to the producer without declaring it; the suite fails naming it.

**Acceptance Scenarios**:

1. **Given** the producer emits a key in neither list, **When** the suite runs, **Then** it fails
   naming the undeclared key.
2. **Given** every emitted key is declared exactly once, **When** the suite runs, **Then** it passes.
3. **Given** the ledger declares a key the producer no longer emits, **When** the suite runs, **Then**
   it fails naming the stale declaration.
4. **Given** the test, **When** it determines which keys exist, **Then** it derives them from a real
   execution of the producer, never from a list maintained by hand.
5. **Given** a component's ledger is deleted entirely, **When** the suite runs, **Then** it fails —
   removing the contract must not be a silent return to the prior behaviour.
6. **Given** the reconciliation selects which components to check, **When** that selection is empty,
   **Then** the suite fails rather than passing with zero assertions executed.

---

### User Story 4 - An empty or partial backup stops reporting healthy (Priority: P1)

A source-path typo, an over-broad exclude, or a vanished mount can yield exit 0, a real snapshot, a
fresh timestamp — and capture nothing, or capture only part of what was asked for.

**Why this priority**: One of the four catastrophic legs, and invisible today: nothing office2 emits
distinguishes a full backup from an empty one.

**Independent Test**: Present a document reporting zero files processed and confirm unhealthy; present
one reporting a missing source root and confirm unhealthy.

**Acceptance Scenarios**:

1. **Given** a document reporting zero files processed, **When** health is evaluated, **Then**
   unhealthy.
2. **Given** a document reporting that a configured source root is absent from the snapshot, **When**
   health is evaluated, **Then** unhealthy, evidence naming the missing root.
3. **Given** all configured roots present and a non-zero file count, **When** health is evaluated,
   **Then** the capture signals do not by themselves make it unhealthy.

---

### User Story 5 - The volume filling is visible before it is terminal (Priority: P2)

A backup onto a nearly-full filesystem fails loudly at the cliff; the approach to the cliff has no
signal at all.

**Why this priority**: Real but slower-moving than the P1s — the volume is at 1% today, so this buys
warning rather than fixing a live condition.

**Independent Test**: Present a document reporting free space below the floor and confirm unhealthy.

**Acceptance Scenarios**:

1. **Given** free space below the declared floor, **When** health is evaluated, **Then** unhealthy,
   evidence naming the free-space figure.
2. **Given** free space above the floor, **When** health is evaluated, **Then** it does not by itself
   make the component unhealthy.

---

### User Story 6 - A wiped repository stops reading healthy (Priority: P2)

A repository destroyed and re-created from empty produces one snapshot with a fresh timestamp and
successful results, while the entire history is gone.

**Why this priority**: A real silent total-loss condition, closable from a fact already recorded.

**Independent Test**: Present a document reporting a single snapshot and confirm unhealthy.

**Acceptance Scenarios**:

1. **Given** a document reporting exactly one snapshot, **When** health is evaluated, **Then**
   unhealthy.
2. **Given** two or more, **Then** the count does not by itself make it unhealthy.
3. **Given** a snapshot count that could not be measured — the producer's count query failed while the
   backup itself succeeded — **When** health is evaluated, **Then** the component reads **unknown**,
   not unhealthy and not healthy. "Could not count" is not "counted one", the same distinction US1
   rests on.

---

### User Story 7 - A skewed clock cannot pin the backup "fresh" forever (Priority: P2)

If the recorded time is in the future, computed age is negative, never exceeds any bound, and the
component reads fresh indefinitely.

**Why this priority**: A latent hole in the existing freshness rule, closed by porting a bound this
repository already chose elsewhere.

**Independent Test**: Present a document whose time is beyond the tolerance in the future and confirm
it does not read fresh.

**Acceptance Scenarios**:

1. **Given** a recorded time beyond the tolerance in the future, **When** freshness is evaluated,
   **Then** not fresh, evidence naming the future-dated time.
2. **Given** a time within tolerance in the future — benign skew — **Then** fresh.
3. **Given** a time in the normal recent past, **Then** fresh exactly as today.

---

### User Story 8 - The second machine inherits the rule rather than copying it (Priority: P3)

The second backup declares its own ledger and supplies its own execution harness, and gets the same
enforcement without reimplementing adjudication or reconciliation.

**Why this priority**: Deferred value, but it constrains the design from the start.

**Independent Test**: Declare a fictitious producer *script* with a different key set, run it through
the shared reconciliation and the shared evaluator, and confirm neither needed editing.

**Acceptance Scenarios**:

1. **Given** a second producer with different keys and good-sets, **When** it declares a ledger and a
   harness, **Then** the same enforcement applies with no change to shared logic.
2. **Given** a component declares a ledger but registers no harness, **When** the validation runs,
   **Then** it fails — a ledger nothing reconciles is a hand-maintained list.

### Edge Cases

- **The check did not run today.** Six days in seven the verdict is absent-by-design and must read
  healthy. A truthiness test cries wolf six days a week until muted, taking the real Sunday failure
  with it.
- **The check stopped running altogether.** Distinct from the above and previously invisible; closed
  by FR-012. The distinction between "not today" and "not for months" is the whole of US2.
- **A value of an unexpected type.** A verdict arriving as `"false"`, or an exit code arriving as
  `false`, must not slip through a type guard into healthy. Note both directions collide in the host
  language: a boolean equals a number and a number equals a boolean, so matching must be by type
  identity in both directions.
- **An adjudicated key absent entirely.** Distinct from present-and-`null`: `null` is a value the
  producer deliberately wrote; absence is the producer no longer speaking. Absence is always
  unhealthy, whatever the predicate.
- **A key declared but no longer emitted.** The ledger must not describe a producer that has moved on.
- **A ledger deleted wholesale.** Must fail, or the contract is removable in silence.
- **A brand-new repository.** Its first run reports one snapshot and, under US6, unhealthy. For
  office2 this is unreachable (14 snapshots). For a *new* backup it would alert for a full day on a
  correctly functioning first night — so a first-run suppression is required rather than optional.
- **Two producers with different key sets.** The contract must not assume the machines emit the same
  keys; they do not.
- **A producer that cannot be executed deterministically.** Several other components emit their
  pointer from an agent step. For those an enforcement test could only compare against a
  hand-maintained list — the defect, not the fix. Out of scope, tracked as #937.

## Requirements *(mandatory)*

### Functional Requirements

| ID | Title | User Story | Priority | Status |
|----|-------|------------|----------|--------|
| FR-001 | Integrity verdict decides health | As the operator, I want a failed repository-integrity verdict to make the backup unhealthy, so a proven-corrupt repository cannot report healthy. | High | Open |
| FR-002 | "Not checked today" stays healthy | As the operator, I want an absent verdict on days the check does not run to read healthy, so the signal is not muted by daily false alarms. | High | Open |
| FR-003 | Every emitted key is declared | As a maintainer, I want every emitted key declared adjudicated-with-a-good-set or diagnosis-only-with-a-reason, so no key is load-bearing by accident or inert by oversight. | High | Open |
| FR-004 | Enforcement derives keys from real emission | As a maintainer, I want the enforcing test to determine the key set by executing the producer, so the check cannot degrade into asserting a hand-maintained list. | High | Open |
| FR-005 | Undeclared key fails the suite | As a maintainer, I want an undeclared emitted key to fail the suite and be named, so the omission is caught before it ships. | High | Open |
| FR-006 | Stale declaration fails the suite | As a maintainer, I want a declared key the producer no longer emits to fail the suite, so the ledger cannot rot into fiction. | Medium | Open |
| FR-007 | Absent adjudicated key is unhealthy | As the operator, I want an adjudicated key missing from the document to read unhealthy regardless of its predicate, so a producer that stops emitting a health-bearing key cannot pass unnoticed. | High | Open |
| FR-008 | Future-dated time is not fresh | As the operator, I want a recorded time implausibly in the future to not read fresh, so clock skew cannot pin the component fresh indefinitely. | Medium | Open |
| FR-009 | Diagnosis-only keys carry a stated reason | As a maintainer, I want each diagnosis-only key to carry a written reason, so declining to adjudicate is a signed claim rather than a one-word escape. | Medium | Open |
| FR-010 | Contract is reusable by a second producer | As a maintainer, I want a second backup to obtain the same enforcement by supplying only its own ledger and execution harness, so no adjudication or reconciliation logic is duplicated. | Medium | Open |
| FR-011 | Adoption path for remaining components is tracked | As a maintainer, I want the other pointer-emitting components to have a written adoption path and a tracked follow-up (#937), so their exclusion is a scheduled decision. | Low | Open |
| FR-012 | Verification recency decides health | As the operator, I want the time of the last successful integrity verification recorded and bounded, so a verification that stops running is visible rather than indistinguishable from "not today". | High | Open |
| FR-013 | Empty capture is unhealthy | As the operator, I want a run that processed no files to read unhealthy, so a backup that captures nothing cannot report success. | High | Open |
| FR-014 | Missing source root is unhealthy | As the operator, I want a snapshot missing any configured source root to read unhealthy, so a partial capture is not mistaken for a complete one. | High | Open |
| FR-015 | Low free space is unhealthy | As the operator, I want free space on the repository volume below a declared floor to read unhealthy, so the approach to a full disk is visible before it is terminal. | Medium | Open |
| FR-016 | Unmeasurable count is unknown | As the operator, I want a snapshot count the producer could not measure to read unknown rather than unhealthy, so "could not count" is not reported as "counted one". | Medium | Open |
| FR-017 | Ledger binds to a reconciliation harness | As a maintainer, I want a declared ledger to require a registered execution harness, so a ledger nothing reconciles cannot merge. | High | Open |
| FR-018 | Declared freshness key is the anchor | As a maintainer, I want the key a ledger declares as its freshness anchor to be the key actually judged, so the declaration is binding rather than decorative. | High | Open |
| FR-019 | First-run suppression for a new repository | As the operator, I want a newly created backup repository to be exempt from the snapshot-count rule for its first runs, so a correctly functioning first night does not alert for a full day. | Medium | Open |

### Non-Functional Requirements

| ID | Title | Requirement | Category | Priority | Status |
|----|-------|-------------|----------|----------|--------|
| NFR-001 | Decision correctness | A document carrying a failed integrity verdict yields an unhealthy verdict with evidence naming the key, asserted offline with an injected clock. Detection *latency* is a derivation from the 15-minute evaluation interval plus the ≤5 s probe timeout, not an observed quantity. | Reliability | High | Open |
| NFR-002 | Deterministic and offline | Every test added passes with no network, no live-host access, and no dependence on the real date or day of week; repeated runs are identical. | Reliability | High | Open |
| NFR-003 | No regression, ledger-aware | The existing suite stays green with no reduction in passing tests — **and** the #902/FR-009 regression scenarios are re-asserted against the component's real declared ledger, not a hand-built configuration, so a ledger-only regression cannot hide behind ledger-free tests. | Reliability | High | Open |
| NFR-004 | Evidence names the cause | Every unhealthy or not-fresh verdict introduced here carries evidence naming the responsible key and value, so an operator can act without reading source. | Observability | High | Open |
| NFR-005 | No new false positives | The three integrity shapes a normal week produces — `run:false/passed:null`, `run:true/passed:true`, and the unmeasured-count shape — read healthy or unknown as specified, and only `run:true/passed:false` reads unhealthy. Asserted with an injected clock across explicit fixtures, never by real date. | Reliability | High | Open |
| NFR-006 | Evaluator totality | The adjudication logic raises no exception for any input shape the producer can emit, including malformed JSON values, wrong types, and absent keys — because a raised exception is caught upstream and mapped to `unknown`, and a first-seen `unknown` is recorded without alerting. An evaluator that throws converts a detected failure into silence. | Reliability | High | Open |

### Constraints

| ID | Title | Constraint | Category | Priority | Status |
|----|-------|------------|----------|----------|--------|
| C-001 | Producer is modified, deliberately | **Reversed from v1 after review.** The producer gains four emitted keys and one output guard. v1 forbade producer changes; that constraint is what forced the deepest defect (US2) to stay open, so it was lifted by explicit decision. | Technical | High | Open |
| C-002 | Live producer install is a manual operator step | The deployed producer is `root:root` in a `root:root` directory and the deploy agent has neither write access nor passwordless sudo. The repo change cannot install itself. The mission is not complete until the operator installs it and the drift comparator reports converged. | Technical | High | Open |
| C-003 | Existing good-sets preserved and kept separate | The backup-result and retention-result good-sets keep their deliberately different definitions and are not merged. Merging them is a named prior regression. | Technical | High | Open |
| C-004 | Absent is not failure is not "did not run" | Adjudication must distinguish "ran and failed", "did not run today", "has not run for a long time", and "could not be measured". A rule collapsing any of these is rejected however simple. | Technical | High | Open |
| C-005 | Enforcement scope limited to backup producers | Only the backup documents are enforced here; the other 16 components are tracked as #937. | Technical | High | Open |
| C-006 | Change-control tier | **Tier 2.** The producer is modified and reinstalled on the live host, so a Restic snapshot ≤24 h must be confirmed before install. | Regulatory | High | Open |
| C-007 | Second machine's ledger is not authored here | office4's ledger is authored by #913 against this mechanism. Its producer does not exist yet, so the enforcing test could not verify a declaration written now. | Technical | Medium | Open |
| C-008 | Schema version is bumped and pinned | Adding keys changes the document's shape, so the version is incremented and the ledger pins it. A future bump then forces a deliberate ledger review instead of passing silently. | Technical | Medium | Open |

### Key Entities

- **State document**: the record a backup run writes about itself. It is the interface between the
  backup and the canary's health verdict — **and not only that**: a second consumer, the Tier-2 deploy
  pre-flight gate, reads the same document with its own independent rules. `diagnostic_only` therefore
  means "does not decide *canary health*", never "unused by anything".
- **Ledger**: the per-producer declaration placing every emitted key in exactly one of two categories.
- **Adjudicated key**: a key with an explicit predicate. Values satisfying it leave health unchanged;
  values outside it make the component unhealthy.
- **Diagnosis-only key**: a key deliberately excluded from deciding canary health, with a written
  reason.
- **Reconciliation harness**: the executable that runs a producer under controlled effects and yields
  the keys it actually emitted. A ledger without one is a hand-maintained list.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A failed integrity verdict yields an unhealthy verdict naming the key, in 100% of
  evaluations. Currently: never.
- **SC-002**: Zero keys emitted by a covered backup are undeclared. Currently seven of ten are
  undeclared and inert.
- **SC-003**: Introducing an undeclared key, or deleting the ledger, causes a test failure naming the
  cause, in 100% of attempts. Currently both are accepted silently.
- **SC-004**: Across the three integrity shapes a normal week produces, the component reports healthy
  or unknown as specified and raises zero false alerts.
- **SC-005**: Each of the four previously-invisible total-loss conditions — corrupt repository,
  verification stopped, empty or partial capture, volume near full — is reported on the first
  evaluation after the condition is recorded. Currently all four report healthy.
- **SC-006**: A second backup obtains the full contract by supplying only its own ledger and its own
  execution harness, with zero lines of adjudication or reconciliation logic duplicated — asserted by
  a test that drives a fictitious producer through the same shared helpers.
- **SC-007**: The #902/FR-009 regression scenarios pass with the component's real ledger attached, not
  only in a ledger-free configuration.

## Assumptions

- **A1**: The snapshot-count floor is two, with an explicit first-run suppression (FR-019) rather than
  an inferred "established repository" qualifier. v0.2 expressed this as "after the first week"; that
  is the same intent stated as a bound rather than a judgement.
- **A2**: office4's ledger is authored by its own mission (C-007).
- **A3**: The backup-result and retention-result good-sets carry over exactly, including their
  deliberate difference (C-003).
- **A4**: The repo-side change reaches the canary by the existing checkout pull with no deploy
  manifest; the **producer** install is separate and manual (C-002).
- **A5**: The document's schema version is adjudicated with a pinned value rather than treated as
  diagnostic, because it is the one key whose purpose is to announce that the contract changed
  (C-008).

## Risks

- **R-001 — The alerter is unwatched, and self-observation does not fix it.** The canary's own
  liveness check is probed only by the canary, so a stopped runner cannot report itself. This is
  recorded as a known false premise rather than an assumption, and is **not** closed here. It is the
  fourth leg of the v0.2 catastrophe and it remains open.
- **R-002 — The reconciliation binds the repo copy, not the deployed producer.** The two are
  independent files reconciled only by a daily observe-only comparator. The contract's guarantee about
  live behaviour is void while that comparator reports drift, which must be stated in the runbook.
- **R-003 — Adjudication is enforced for one reader only.** The deploy pre-flight gate reads the same
  document with its own duplicated rules. Unifying them is out of scope here; the duplication is now
  documented rather than accidental.

## What the review changed

Recorded because the mission's subject is exactly this failure mode, and hiding its own review
findings would be self-refuting.

1. **A live regression was prevented.** v1's precedence rule was written per *key*; the code it
   suppresses is organised per *rule-block*, with the snapshot-timestamp guard nested inside the
   exit-code branch. v1 would have deleted that guard and reopened #902/FR-009 — and every existing
   regression test builds its configuration *without* a ledger, so all of them would have stayed green.
   Now NFR-003/SC-007.
2. **Counts were wrong.** v1 said six of ten keys were inert, inherited from #934's body without
   checking. The true figure is seven of ten, because the finish-witness timestamp cannot act as a
   fallback for this component.
3. **The framing was overstated.** "A rule that cannot be forgotten" became the accurate claim about
   silent versus deliberate inertness.
4. **The scope reduction was undisclosed.** v1 never named the three keys it declined to adopt. That
   is now the *What this mission does not close* table — which, after the decision to close all four
   legs, records only the one that genuinely remains.
5. **Type matching was half-specified.** v1 covered a number against a boolean good-set but not a
   boolean against a numeric one, which the host language treats as equal in both directions.
6. **Absence was self-contradictory.** v1 both restricted evaluation to present keys and adjudicated
   absent ones, and defined absence only for one of three predicate forms. Now FR-007, unconditional.
7. **The mechanism had no floor.** Nothing forced a ledger to have a harness, nothing failed when a
   ledger was deleted, and an empty component selection would have passed with zero assertions. Now
   FR-017 and US3 scenarios 5–6.
