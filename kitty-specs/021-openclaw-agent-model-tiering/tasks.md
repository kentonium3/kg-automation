# Tasks: OpenClaw Agent Model Tiering

**Feature**: 021-openclaw-agent-model-tiering
**Branch**: main → main
**Date**: 2026-04-09

## Subtask Index

| ID | Description | WP | Parallel |
|---|---|---|---|
| T001 | Verify Restic backup recency on office2 | WP01 | |
| T002 | Snapshot current openclaw.json to backup location | WP01 | |
| T003 | Document current model assignments as baseline | WP01 | |
| T004 | Collect recent production inputs for inbox agent | WP02 | |
| T005 | Run inbox agent on Haiku, compare to Sonnet baseline | WP02 | |
| T006 | Collect recent production inputs for habits agent (daily) | WP03 | |
| T007 | Run habits daily check-in on Haiku, compare to Sonnet | WP03 | |
| T008 | Collect recent production inputs for habits agent (weekly) | WP03 | |
| T009 | Run habits weekly review on Haiku, compare to Sonnet | WP03 | |
| T010 | Collect escalation agent inputs including known triggers | WP03 | |
| T011 | Run escalation agent on Haiku, compare to Sonnet | WP03 | |
| T012 | Document validation results per agent (pass/fail) | WP03 | |
| T013 | Set global default model to Haiku in openclaw.json | WP04 | |
| T014 | Update per-agent model fields based on validation | WP04 | |
| T015 | Restart OpenClaw and verify model assignments | WP04 | |
| T016 | Monitor first scheduled execution post-change | WP04 | |
| T017 | Add model fields to agent-registry.json | WP05 | [P] |
| T018 | Update AGENT-REGISTRY.md to match JSON | WP05 | |
| T019 | Update service-inventory.md OpenClaw entry | WP05 | [P] |
| T020 | Update agent-setup runbook with model tier requirement | WP05 | [P] |
| T021 | Calculate and document monthly cost target | WP05 | |

---

## Work Packages

### WP01: Pre-flight and Baseline

**Goal**: Ensure Tier 2 change control compliance and document the starting state before any changes.

**Priority**: High — must complete before any validation or config changes.

**Dependencies**: None

**Prompt file**: [WP01-preflight-baseline.md](tasks/WP01-preflight-baseline.md)

**Subtasks**:
- [ ] T001: Verify Restic backup recency on office2
- [ ] T002: Snapshot current openclaw.json to backup location
- [ ] T003: Document current model assignments as baseline

**Estimated prompt size**: ~250 lines

---

### WP02: Validate Inbox Agent on Haiku

**Goal**: Test whether the inbox classification agent produces acceptable results on Haiku. This is the simplest agent, highest-volume (8×/day), and biggest cost savings target.

**Priority**: High — lowest-risk validation, should run first.

**Dependencies**: WP01

**Prompt file**: [WP02-validate-inbox.md](tasks/WP02-validate-inbox.md)

**Subtasks**:
- [ ] T004: Collect recent production inputs for inbox agent
- [ ] T005: Run inbox agent on Haiku, compare to Sonnet baseline

**Estimated prompt size**: ~300 lines

---

### WP03: Validate Habits and Escalation on Haiku

**Goal**: Test whether habits (daily + weekly) and escalation agents produce acceptable results on Haiku. Habits weekly review does trend reasoning — this is the key quality decision. Escalation has the highest consequence if wrong.

**Priority**: High — must complete before deploying config changes.

**Dependencies**: WP01

**Prompt file**: [WP03-validate-habits-escalation.md](tasks/WP03-validate-habits-escalation.md)

**Subtasks**:
- [ ] T006: Collect recent production inputs for habits agent (daily check-in)
- [ ] T007: Run habits daily check-in on Haiku, compare to Sonnet
- [ ] T008: Collect recent production inputs for habits agent (weekly review)
- [ ] T009: Run habits weekly review on Haiku, compare to Sonnet
- [ ] T010: Collect escalation agent inputs including known triggers
- [ ] T011: Run escalation agent on Haiku, compare to Sonnet
- [ ] T012: Document validation results per agent (pass/fail with observations)

**Parallel with WP02**: Yes — WP02 and WP03 both depend on WP01 but are independent of each other.

**Estimated prompt size**: ~450 lines

---

### WP04: Deploy Tiered Configuration

**Goal**: Apply validated model tier assignments to production openclaw.json and verify all agents function correctly.

**Priority**: High — this is the cost-saving deployment.

**Dependencies**: WP02, WP03 (must know which agents passed validation)

**Prompt file**: [WP04-deploy-config.md](tasks/WP04-deploy-config.md)

**Subtasks**:
- [ ] T013: Set global default model to Haiku in openclaw.json
- [ ] T014: Update per-agent model fields based on validation results
- [ ] T015: Restart OpenClaw and verify model assignments
- [ ] T016: Monitor first scheduled execution post-change

**Estimated prompt size**: ~350 lines

---

### WP05: Registry and Documentation Update

**Goal**: Update agent registry, architecture docs, and runbook to reflect tiered model assignments. Calculate cost target.

**Priority**: Medium — can run after or in parallel with WP04 for the doc portions.

**Dependencies**: WP04 (needs final model assignments; doc updates can start from validation results)

**Prompt file**: [WP05-registry-docs.md](tasks/WP05-registry-docs.md)

**Subtasks**:
- [ ] T017: Add model, model_policy, model_rationale fields to agent-registry.json
- [ ] T018: Update AGENT-REGISTRY.md to match JSON
- [ ] T019: Update service-inventory.md OpenClaw entry
- [ ] T020: Update agent-setup runbook with model tier requirement
- [ ] T021: Calculate and document monthly cost target

**Estimated prompt size**: ~400 lines

---

## Dependency Graph

```
WP01 (pre-flight)
├─→ WP02 (validate inbox)     ──┐
└─→ WP03 (validate habits/esc) ─┤
                                 └─→ WP04 (deploy) → WP05 (registry/docs)
```

WP02 and WP03 can run in parallel after WP01.

## Size Validation

| WP | Subtasks | Est. Lines | Status |
|---|---|---|---|
| WP01 | 3 | ~250 | ✓ Ideal range |
| WP02 | 2 | ~300 | ✓ Ideal range |
| WP03 | 7 | ~450 | ✓ Ideal range (upper) |
| WP04 | 4 | ~350 | ✓ Ideal range |
| WP05 | 5 | ~400 | ✓ Ideal range |

All WPs within ideal sizing. No splits needed.
