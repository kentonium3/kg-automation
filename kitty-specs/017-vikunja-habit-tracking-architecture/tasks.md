# Tasks: F017 Vikunja Habit Tracking Architecture

**Feature**: 017-vikunja-habit-tracking-architecture
**Mission**: research
**Date**: 2026-04-06
**Spec**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md)

---

## Subtask Index

| ID | Description | WP | Parallel |
|----|-------------|-----|----------|
| T001 | Verify Vikunja version on office2 from service-inventory.json | WP01 | — |
| T002 | Complete RQ-2: current F009 deployment state report | WP01 | [P] after T001 |
| T003 | Research RQ-1: Vikunja recurring task behavior | WP01 | [P] after T001 |
| T004 | Evaluate RQ-3: candidate approach comparison | WP01 | after T002, T003 |
| T005 | Confirm RQ-4: API capabilities for recommended approach | WP01 | after T004 |
| T006 | Write architecture recommendation with rationale and risks | WP01 | after T005 |

---

## Work Packages

### WP01: Full Investigation and Findings

**Prompt**: [WP01-full-investigation-and-findings.md](tasks/WP01-full-investigation-and-findings.md)
**Priority**: P0 (only WP)
**Dependencies**: none
**Subtasks**: T001, T002, T003, T004, T005, T006
**Estimated prompt size**: ~450 lines

**Goal**: Execute the complete research investigation across all four
research questions, producing a single `findings.md` document with
evidence-backed answers and an architecture recommendation.

**Included subtasks**:
- [x] T001 — Verify Vikunja version on office2
- [x] T002 — Complete RQ-2: current F009 deployment state
- [x] T003 — Research RQ-1: Vikunja recurring task behavior
- [ ] T004 — Evaluate RQ-3: three candidate approaches vs. five criteria
- [ ] T005 — Confirm RQ-4: API capabilities for recommended approach
- [ ] T006 — Write architecture recommendation

**Parallel opportunities**: T002 and T003 are independent after T001
completes (version verification). Both can proceed simultaneously.
T004 requires findings from both T002 and T003 before evaluation.

**Implementation sequence**:
1. T001: Version check (gates all external source validation)
2. T002 + T003: Parallel — current state audit + recurring task research
3. T004: Candidate comparison (requires T002 + T003 outputs)
4. T005: API capability confirmation (requires T004 recommendation)
5. T006: Final recommendation write-up (requires T005 confirmation)

**Success criteria**: findings.md addresses all four RQs with cited
sources; comparison table maps three options against five criteria;
single recommended approach stated with rationale; API endpoints
confirmed at field level; downstream F009 spec can be written without
further discovery.

**Risks**:
- Vikunja recurring task behavior may differ from documentation —
  mitigated by live API inspection
- No candidate approach may satisfy all five criteria — spec allows
  documenting best trade-off
- Community sources may reference wrong Vikunja version — mitigated
  by T001 version gate

---

**END OF TASKS**
