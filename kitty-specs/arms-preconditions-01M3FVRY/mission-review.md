# Mission Review Report: arms-preconditions-01M3FVRY

**Reviewer**: Codex (`codex-office4-d5c7b35d`), with an independent Reviewer Renata audit and a separate read-only `codex exec` review  
**Date**: 2026-09-28  
**Mission**: `arms-preconditions-01M3FVRY` — 849 Arms Run Pre-Run Preconditions  
**Baseline commit**: `1e5faad1637b180833caec1fe7e0d4146bde1035`  
**Squash merge commit**: `72eb7d8c5760874ff9371a04e1911805416b552a`  
**HEAD at report**: `366d32b577e1503f19a18ad8edef565b93081995`  
**WPs reviewed**: WP01..WP05

The implementation reached the feature branch, but the feature branch is not releasable to `main`. The required freeze-time checker record does not exist because the deterministic Arm G deadlock tracked by #1037 blocks the full two-seed suite. The acceptance matrix now records FR-015 and the aggregate verdict as `fail`.

---

## Gate Results

### Gate 1 — Contract tests

- Command: not run; the doctrine command targets `<spec-kitty-repo>/tests/contract/`, while this mission is in the `kg-automation` consumer repository and has no `tests/contract/` directory.
- Exit code: N/A
- Result: N/A — no repository subject
- Notes: This is a repository-scope determination, not an exception or waiver.

### Gate 2 — Architectural tests

- Command: `.venv/bin/python -m pytest -q tests/architectural`
- Exit code: `0`
- Result: PASS
- Notes: `9 passed in 0.04s`.

### Gate 3 — Cross-repo E2E

- Command attempted in the sibling repository: `SPEC_KITTY_ENABLE_SAAS_SYNC=1 uv run pytest scenarios/ -q -p no:cacheprovider`
- Exit code: `1`
- Result: N/A — no repository subject
- Notes: Gate 3 names the Spec Kitty end-to-end repository and Spec Kitty's FR-038..FR-041/C-010. `kg-automation` is a consumer repository, so no `mission-exception.md` was authored. Separately, the sibling environment is broken: its Spec Kitty CLI cannot import `spec_kitty_events.diary`; the run reported 1 failed, 1 passed and 3 skipped. That is not a finding against this mission and should not be re-diagnosed here.

### Gate 4 — Issue Matrix

- File: `kitty-specs/arms-preconditions-01M3FVRY/issue-matrix.json`
- Rows: `7`
- Empty / `unknown` verdicts: `0`
- `in-mission` verdicts after correction: `0`
- `deferred-with-followup` rows missing a follow-up handle: `0`
- Result: PASS at report HEAD
- Notes: Merge incorrectly completed while #1023 remained `in-mission`. Post-merge review caught the invalid terminal state. The authoritative `spec-kitty agent issue-verdict` seam recorded `deferred-with-followup` with #1037 and the required checker/main-landing work as evidence in commit `2b4d136c`. This independently reproduced the already-tracked validator defect #1032; generic evidence was added there.

---

## FR Coverage Matrix

| FR ID | Description (brief) | WP Owner | Test / evidence | Test adequacy | Finding |
|---|---|---|---|---|---|
| FR-001 | Register G, D and R with one shared embedder | WP04 | `test_live_runtime_registers_g_d_r_with_one_embedder` | ADEQUATE | — |
| FR-002 | Halt and record premise violations / unacknowledged G cancellation | WP02, WP04 | `test_a_premise_violation_records_both_events_and_halts_before_later_work`; cancellation integration test | ADEQUATE | — |
| FR-003 | Use one arm-refusal contract | WP02 | `test_the_arms_share_one_refusal_class` | ADEQUATE | — |
| FR-004 | An unregistered arm cannot silently produce a complete primary | WP04 | unregistered-arm integration test plus export refusal test | ADEQUATE | — |
| FR-005 | Start and bind the graph-store series and run-level boundaries | WP03, WP04 | real writer and ordered-boundary integration tests | ADEQUATE | — |
| FR-006 | Produce the graph-store run-level memory report | WP01, WP03 | real writer round-trip test | ADEQUATE | — |
| FR-007 | Fail closed on absent, stale, gapped or foreign series data | WP01, WP03 | unavailable-condition report tests | ADEQUATE | — |
| FR-008 | Stop and send zero bytes on a send-time ceiling breach | WP01, WP02, WP04 | send-time breach integration test | ADEQUATE | — |
| FR-009 | Resume through fresh timestamped gates with both negatives | WP05 | three live-style resume tests | ADEQUATE | — |
| FR-010 | Keep the isolation inventory bidirectionally complete | WP01 | package-to-registry and registry-to-package tests | ADEQUATE | — |
| FR-011 | Bind every attempt to its own session's gates | WP01 | `test_attempt_start_carries_the_session_id_of_its_own_session` | ADEQUATE | — |
| FR-012 | Accept canonical UTC timestamps only | WP03 | canonical-ISO-format test | ADEQUATE | — |
| FR-013 | Re-measure the registered token table at code freeze | WP04 | exact ordering, binding and token-measurement test | ADEQUATE for the tool contract | — |
| FR-014 | Report named research-environment skips | WP05 | named/countable skip-reason test | ADEQUATE | — |
| FR-015 | Produce a commit-bound two-seed, fresh-worktree and live-smoke PASS record | WP05 | checker unit tests exist; no final record exists | **MISSING at freeze time** | DRIFT-1 |
| FR-016 | Route every G operation per question and prove a live hybrid hit | WP02 | live hybrid search expected-hit test and routing tests | ADEQUATE | — |

FR-001..FR-014 and FR-016 have closed spec-to-test-to-production chains. Both independent post-merge reviews found no additional production-code correctness, security or cross-WP integration defect beyond #1037 and its effect on FR-015.

---

## Drift Findings

### DRIFT-1: Required freeze-time evidence is absent

**Type**: NFR-MISS  
**Severity**: HIGH  
**Spec reference**: FR-015, NFR-001, SC-007

**Evidence**:

- `tasks/WP05-envgate-resume-premerge/implementation-notes.md` records that the two-seed suite, detached-worktree simulation, live smoke and final commit-bound record were not run because of #1037.
- No `build/849-runs/premerge-<HEAD>.json` PASS record exists.
- The full checker invokes the required complete suites; the deterministic Arm G deadlock prevents it from finishing.
- Commit `366d32b5` corrected FR-015 to `fail` through the authoritative acceptance-verdict command, making `overall_verdict` fail.

**Analysis**: A unit test proving that the checker validates a record is not evidence that this commit passed the checker. The feature branch must not reach `main` until #1037 is repaired and the complete checker produces a commit-bound PASS record at the then-final HEAD.

### DRIFT-2: Acceptance could false-pass scaffold-only content

**Type**: LOCKED-DECISION / WORKFLOW-INTEGRITY  
**Severity**: MEDIUM  
**Evidence**:

- Before the post-merge correction, `acceptance-matrix.json` reported `overall_verdict: pass` while every criterion retained `notes: "TODO: replace with a real acceptance criterion"` and `negative_invariants` was empty.
- `acceptance-verdict` exposes no supported field for replacing criterion description or notes.
- Internal tooling issue #1050 records the reproduction, source diagnosis and a deduplicated upstream comment draft; no upstream post has been made.

**Analysis**: The aggregate proved that verdict fields had been populated. It did not prove that acceptance criteria or the negative-invariant decision had been authored. That allowed FR-015 to appear accepted using only a unit test of the checker.

### DRIFT-3: Accepted spec text retains draft/open markers

**Type**: ARTIFACT-STATE DRIFT  
**Severity**: LOW  
**Evidence**: `spec.md` still says `Status: Draft`, and its requirement checklist remains open after mission completion.

**Analysis**: The implementation and review evidence are durable elsewhere, but the human-readable specification does not reflect its terminal state. This does not change runtime behavior; it increases the chance that later readers misread mission maturity.

---

## Risk Findings

### RISK-1: Deterministic Arm G deadlock blocks every full verification run

**Type**: ERROR-PATH / CONCURRENCY  
**Severity**: HIGH  
**Location**: tracked in #1037; the caller waits in the Arm G bridge while its event loop remains idle  
**Trigger condition**: graphiti-enabled Arm G bridge tests or the full pre-merge checker

**Analysis**: The isolated reproduction times out under both required hash seeds. Focused WP suites missed it. Kent's earlier condition—repair WP02 only if it blocks later workflow—has fired because the defect now blocks the required freeze-time gate. The repair vehicle remains an operator decision; no direct patch or checker run was attempted during this review.

---

## Silent Failure Candidates

No new production-code silent-failure candidate was found. Two workflow-level false-positive paths were observed and recorded:

| Location | Condition | Silent result | Impact |
|---|---|---|---|
| acceptance aggregate | Every verdict is populated but criterion text remains scaffold-only | `overall_verdict: pass` | Unsupported acceptance can appear complete; tracked in #1050 |
| merge issue-matrix gate | A row remains `in-mission` when merge records WPs `done` | gate reports completeness PASS and merge exits 0 | Canonical issue state contradicts mission terminal state; tracked in #1032 |

---

## Security Notes

No blocking security finding was identified. The reviewers checked subprocess/path handling, cleanup, data integrity, cancellation and lock behavior. The material concurrency defect is the availability/deadlock issue in #1037, not a credential or authorization exposure.

---

## Integration and Merge Verification

- The final reviewed lane production/test tree at `9db5456a` is byte-identical to squash merge `72eb7d8c` and to the corresponding tree at report HEAD.
- The merge command's stale-assertion advisory identified no discrepancy in the production/test paths checked above. The real rubric changes between the lane and squash commits are separately reconciled by `contracts/ledger-deltas.md`.
- Architectural verification passed 9/9.
- An independent focused audit passed 28 selected tests and found no additional code defect.
- All post-merge workflow corrections preceding this report are pushed through `366d32b5`.

---

## Final Verdict

**FAIL**

### Verdict rationale

FR-001..FR-014 and FR-016 are implemented and adequately constrained. FR-015, NFR-001 and SC-007 are not satisfied because the required final, commit-bound checker record does not exist, and #1037 deterministically blocks the suite that must produce it. The authoritative acceptance matrix now reports this failure. Gate 4 was repaired through the supported workflow after merge; Gate 3 has no subject in this consumer repository. The feature branch must remain off `main` until #1037 is repaired, the full checker passes at final HEAD, and the resulting record is reviewed.

### Open items

| Item | Status / owner path |
|---|---|
| Choose and execute the code-change vehicle for #1037 | Kent decision pending; code-change ladder points to mission work |
| Run the complete pre-merge checker at final HEAD | Blocked by #1037; do not run until the repair path is authorized |
| Review the checker PASS record before feature-to-main landing | Required after the repair and final commit freeze |
| Acceptance false-pass workflow defect | Filed internally as #1050; upstream comment draft remains unapproved and unposted |
| Merge terminal-verdict validator defect | Existing #1032 updated with generic evidence; upstream #4943 is already closed |
| WP04+ runtime lifecycle chain | Intentionally absent under Kent's 2026-09-28 Option A; #1040 is the audit record |

## Retrospective Reminder

`retrospective.yaml` was authored automatically at the runtime terminus and records `findings_status: has_findings`. `spec-kitty retrospect summary` completed successfully, and `spec-kitty agent retrospect synthesize --mission arms-preconditions-01M3FVRY` ran in dry-run mode with no planned applications. Re-run those commands to review the captured record or staged proposals; use `--apply` only after reviewing a proposal.
