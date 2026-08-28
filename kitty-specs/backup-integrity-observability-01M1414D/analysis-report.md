---
schema_version: 1
artifact_type: spec-kitty.analysis-report
command: /spec-kitty.analyze
mission_slug: backup-integrity-observability-01M1414D
mission_id: 01M1414DJR4NR3CQ8875X06Y9W
generated_at: '2026-08-28T11:43:42.072496+00:00'
analyzer_agent: unknown
input_artifacts:
  spec.md:
    path: /Users/kentgale/repos/kg-automation/kitty-specs/backup-integrity-observability-01M1414D/spec.md
    sha256: af294fd804d96e3adf3daac17c0d8ac25bee985fc1323bc8aeccd693442fe633
  plan.md:
    path: /Users/kentgale/repos/kg-automation/kitty-specs/backup-integrity-observability-01M1414D/plan.md
    sha256: ba46843ccd37d950d14140d160020fb9c2ceb277eee0bb6fe056424f2b649190
  tasks.md:
    path: /Users/kentgale/repos/kg-automation/kitty-specs/backup-integrity-observability-01M1414D/tasks.md
    sha256: 7132f5e1d6ae8e230d545fbf91f666503c328fc212bfe1f6df77ee3261a6c4cf
  charter:
    path: /Users/kentgale/repos/kg-automation/.kittify/charter/charter.md
    sha256: 4891223a0c3fc0dc96917475523586e8f3147a3ccaa113ecb7ff19da646e82e2
verdict: ready
issue_counts:
  high: 0
  critical: 0
  medium: 3
  low: 1
  info: 0
findings:
- id: C1
  severity: medium
  category: coverage
  summary: WP01 carries no test subtask; the 127 sentinel across early-exit paths is verified by reading the script, not by executing it.
- id: C2
  severity: medium
  category: coverage
  summary: SC-008 requires the operator's privileged install and cannot be closed by any work package.
- id: I1
  severity: medium
  category: inconsistency
  summary: 'The mission introduces the same unenforced-coupling class it exists to remove: inventory expected prose and probe code must agree, bound only by review.'
- id: C3
  severity: low
  category: coverage
  summary: NFR-004 (comparator under 5 seconds, reads only two files) has no measuring task.
---

## Specification Analysis Report

**Mission**: `backup-integrity-observability-01M1414D` · **Analyzed**: 2026-08-28
**Artifacts**: spec.md, plan.md, tasks.md, 5 WP prompts, research.md, data-model.md, quickstart.md

| ID | Category | Severity | Location(s) | Summary | Recommendation |
|----|----------|----------|-------------|---------|----------------|
| C1 | Coverage | MEDIUM | tasks.md WP01; WP01 T003 | WP01 changes `restic-backup.sh` and has **no test subtask**. Its riskiest logic — that `PRUNE_RC=127` survives every early-exit path — is verified by T003 "reading the script", which is exactly the kind of by-inspection assurance that failed for #906. A shell-variable mistake on an early-exit branch would not be caught. | Add a subtask that executes the script's `write_state_pointer` path with stubbed `restic`/`du`/`jq` and asserts the emitted JSON for at least the mount-fail and backup-fail branches. If a bash harness is judged disproportionate, say so explicitly and accept that WP02's tests cover only the *consumer* side of the contract, never the producer. |
| C2 | Coverage | MEDIUM | spec.md SC-008; quickstart.md | SC-008 (the install verifies its source and confirms what landed) requires `sudo install` and a root-readable comparison. Every WP runs unprivileged. No WP can close it. | Correctly disclosed, and no WP claims it — recorded so the mission is not reported complete on WP verdicts alone. This is the second mission running with a criterion only the operator can close; that is inherent to an unprivileged agent on a privileged boundary, not a planning defect. |
| I1 | Inconsistency | MEDIUM | WP05 T017 vs WP02 T005/T006 | WP05 corrects the `restic-backup` `expected` prose to describe the prune good-set and the snapshot-timestamp rule; WP02 implements them. Nothing binds the two — they agree only if a reviewer notices. That is **the same unenforced-coupling class this mission exists to remove** (#906 was prose that drifted from code). The mission would ship having fixed two instances and created a third. | Either add a test asserting the inventory `expected` text mentions the prune rule, or accept it explicitly with a rationale. The cheap version — assert the substring `prune_exit_code` appears in that entry's `expected` — is weak but would have caught the #906 shape. Worth raising to the implementer of WP05 rather than leaving silent. |
| C3 | Coverage | LOW | spec.md NFR-004; WP03 | "Completes in under 5 seconds and reads no more than the two files it compares" has measurable thresholds but no task asserts either. | Add a cheap assertion to WP03 T013 (elapsed time; and that no path outside the two inputs is opened), or downgrade NFR-004 to a design note. A threshold nobody measures is decoration. |

**Coverage Summary Table:**

| Requirement Key | Has Task? | Task IDs | Notes |
|-----------------|-----------|----------|-------|
| FR-001 record-prune-outcome | Yes | T001, T002 | WP01 |
| FR-002 distinguish-not-attempted | Yes | T001, T003 | WP01; see C1 — verified by reading only |
| FR-003 health-acts-on-it | Yes | T005, T007 | WP02, via the real probe |
| FR-004 detect-divergence | Yes | T008, T013 | WP03 |
| FR-005 comparator-observable | Yes | T009, T013 | WP03 |
| FR-006 recover-without-strip | Yes | T014, T015, T016 | WP04 |
| FR-007 procedure-in-runbook | Yes | T019 | WP05 |
| FR-008 deploy-story-written | Yes | T020 | WP05 |
| FR-009 no-snapshot-not-healthy | Yes | T006, T007 | WP02 |
| FR-010 trusted-install-source | Yes | T020 | WP05; verification step documented, execution is the operator's |
| NFR-001 health-can-fail | Yes | T007, T013 | Both driven through the real `run_probe` |
| NFR-002 no-consumer-regression | Yes | T007 | The legacy-pointer row |
| NFR-003 round-trip-enforced | Yes | T016 | The format-drift guard |
| NFR-004 comparator-cost | **No** | — | See C3 |

All 10 functional requirements map to at least one task; 3 of 4 non-functional
requirements have an owning task.

**Charter Alignment Issues:** none. The Tier protocol, rebaseline obligation,
deterministic-work discipline, boy-scout rule, and test-first directive are each
addressed with evidence in plan.md. The #899 boundary is treated as a hard
constraint (C-001, C-002) and the plan explicitly rejects the design that would
violate it.

**Duplication / Ambiguity:** no duplicate requirements. FR-003 and C-006 look
adjacent but are outcome versus boundary, which the checklist notes explain. No
unresolved placeholders; `decision verify` reports clean, 0 deferred, 0 markers.
The one previously-ambiguous phrase — "mirrors the existing `restic_exit_code`
handling exactly" — was caught in post-plan review and removed; C-006 now pins
the prune good-set to `{0}` and WP02 carries an explicit `prune_exit_code: 3 →
unhealthy` test row.

**Task ordering:** consistent. `WP01 → WP02`, `{WP01..WP04} → WP05`, WP03 and
WP04 independent; the tasks.md graph matches the `dependencies` frontmatter in
all five files. No integration-before-foundation inversion.

**Terminology:** stable. "prune outcome", "verdict", "drift", "inconclusive", and
"recognised header" each carry one meaning. Note "drift" is used in two senses
across the repo — baseline drift (security-monitor) and script drift (this
mission) — but they are never used in the same sentence and the component names
disambiguate.

**Verdict**: `ready` — no HIGH or CRITICAL findings. C1 and I1 are the ones worth
acting on during implementation rather than at merge: both are places where this
mission risks reproducing, in miniature, the defect class it was created to fix.
