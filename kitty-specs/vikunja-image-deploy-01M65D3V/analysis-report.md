---
schema_version: 1
artifact_type: spec-kitty.analysis-report
command: /spec-kitty.analyze
mission_slug: vikunja-image-deploy-01M65D3V
mission_id: 01M65D3V047EQFZ0RNYG5E48H7
generated_at: '2026-10-30T03:45:25.032376+00:00'
analyzer_agent: unknown
input_artifacts:
  spec.md:
    path: kitty-specs/vikunja-image-deploy-01M65D3V/spec.md
    sha256: ab4253a663f5371df6d84001ce8d6759dd47dc526c950b9e1fde9a3e99495dd1
  plan.md:
    path: kitty-specs/vikunja-image-deploy-01M65D3V/plan.md
    sha256: bfade65cac399a6bae85be6f7dde4ecb2f815b5b0835471d8de597faa53bdeb7
  tasks.md:
    path: kitty-specs/vikunja-image-deploy-01M65D3V/tasks.md
    sha256: 1ba0233cfe95b5cdcabff1d392c1ba7873abaf408cf27f9014e600451f8db7c8
  charter:
    path: .kittify/charter/charter.yaml
    sha256: 212313e7295e83d9a2fc22d6b35aa7460974a9c3d3af46ecee9b1673d3624a0a
verdict: ready
issue_counts:
  critical: 0
  high: 0
  medium: 3
  low: 3
  info: 0
findings:
- id: I1
  severity: medium
  category: inconsistency
  summary: plan.md Project Structure and contracts/entrypoints.md name the operator helpers as .sh; WP06/WP07 implement them as Python (rollback_release.py, stage_release_archive.py).
- id: U1
  severity: medium
  category: underspecification
  summary: WP06 needs the pre-cutover 2.4.0 version string for its readiness check, but WP04 T019 does not record /api/v1/info's version in snapshot.json before the stop.
- id: C1
  severity: medium
  category: coverage
  summary: New docs (evidence doc, cutover runbook) have no task updating docs/INDEX.md / DEVELOPER_PORTAL.md per signal-to-doc-map (runbook-added).
- id: I2
  severity: low
  category: inconsistency
  summary: spec.md User Story 2 scenario 1 says 'the Compose file names it' (the staged image); under the indirection design Compose names office2.local/vikunja:active.
- id: A1
  severity: low
  category: charter
  summary: Charter Deployment Constraints suggest Tier 2 wrappers accept --backup-confirmed; the discipline mode contract allows only --dry-run/--apply and apply.py enforces the backup gate itself.
- id: U2
  severity: low
  category: underspecification
  summary: NFR-003 text still says FR-001..FR-014; plan fold-in extends coverage to FR-017..FR-020 but spec NFR-003 wording was not amended.
---

## Specification Analysis Report

Mission vikunja-image-deploy-01M65D3V, branch `feat/vikunja-image-deploy`. Analyst: Claude Opus 5.5 (the mission's planner), 2026-10-30. Inputs: spec.md, plan.md, research.md R-1 to R-24 (R-9 to R-24 take precedence), data-model.md, contracts/entrypoints.md, quickstart.md, tasks.md, and WP01 to WP09.

| ID | Category | Severity | Location(s) | Summary | Recommendation |
|----|----------|----------|-------------|---------|----------------|
| I1 | Inconsistency | MEDIUM | plan.md Project Structure; contracts/entrypoints.md helper sections; WP06, WP07 | Helpers are named `.sh` in the plan and contract, but Python in the WPs | WP09 T039 records the contract amendment, and WP06/WP07 follow the WP names. Implementers use the WP names. |
| U1 | Underspecification | MEDIUM | WP04 T019; WP06 T026 | The rollback readiness check needs the pre-cutover 2.4.0 version; nothing records it | WP04 T019 reads `/api/v1/info` before `compose down` and stores `pre_version` in snapshot.json. WP06 uses it, falling back to the 2.4 major.minor. |
| C1 | Coverage | MEDIUM | WP05, WP09; CLAUDE.md signal-to-doc-map rule | New docs are not added to docs/INDEX.md or DEVELOPER_PORTAL.md | WP09 T040 adds index entries per `signal-to-doc-map.json` (runbook-added, architecture-doc-added) before doc validation. |
| I2 | Inconsistency | LOW | spec.md US2 scenario 1 | "Compose file names it" predates the indirection | Read it as "Compose selects the indirection tag" (FR-007 as amended). No code impact. |
| A1 | Charter | LOW | charter Deployment Constraints (`--backup-confirmed`); discipline.md mode contract | The charter's suggested flag conflicts with the two-flag contract | Follow discipline.md and apply.py: the pipeline's tier-2 gate enforces backup recency. No flag. |
| U2 | Underspecification | LOW | spec.md NFR-003 | The coverage threshold text lists FR-001 to FR-014 only | Treat NFR-003 as covering FR-001 to FR-020, per plan.md's fold-in Testing line. |

**Coverage Summary Table:**

| Requirement Key | Has Task? | Task IDs | Notes |
|-----------------|-----------|----------|-------|
| FR-001 to FR-005 | Yes | WP03 (T012–T016), WP01 | STAGE |
| FR-006 | Yes | WP01, WP07 | ingress |
| FR-007 | Yes | WP08 T033 | two-line Compose diff |
| FR-008 to FR-012 | Yes | WP04, WP02 | ACTIVATE |
| FR-013, FR-014 | Yes | WP06, WP02 T008–T009 | rollback and guard |
| FR-015 | Yes | WP06, WP09 | operator steps |
| FR-016 | Yes | WP08 T035, WP09 T037–T038 | records and runbooks |
| FR-017 | Yes | WP02, WP04, WP05, WP06 | invariants; engine evidence |
| FR-018, FR-019 | Yes | WP01 T002–T003, WP02, WP04 T022 | deadlines, allowlist |
| FR-020 | Yes | WP04 T018 | replay and cancel |
| NFR-001 to NFR-004 | Yes | WP04 T022, WP03 T012, all test WPs, WP06/WP09 | |
| C-001 to C-007 | Yes | WP09, WP07, WP05, WP08, WP01 | |
| SC-001 to SC-004 | Yes | WP03, WP04, WP06, WP09 | |

**Charter Alignment Issues:** A1 only (low). The Tier-2 backup gate, manifest discipline, pytest coverage, no-dead-code and the defined live verification (WP05 pre-merge, then the go packet's post-merge canary) are all present.

**Unmapped Tasks:** none. All of T001 to T040 sit under a WP with requirement refs.

**Metrics:**

- Total Requirements: 20 FR, 4 NFR, 7 C and 4 SC (35)
- Total Tasks: 40 subtasks in 9 WPs
- Coverage: 100% (every requirement has at least one task)
- Ambiguity Count: 0
- Duplication Count: 0
- Critical Issues Count: 0
