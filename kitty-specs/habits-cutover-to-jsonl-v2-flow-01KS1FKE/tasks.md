# Tasks: Habits cutover to JSONL v2 flow

**Mission**: `habits-cutover-to-jsonl-v2-flow-01KS1FKE`
**Mission ID**: `01KS1FKE0QHYEHZW684YEJNEPW`
**Branch**: main (planning + merge target)
**Date**: 2026-05-19 (UTC 2026-05-20)
**Spec**: [spec.md](spec.md) · **Plan**: [plan.md](plan.md)

---

## Summary

Phase 5 of ADR-0002. Markdown content cutover — switch the deployed habits agent's standing orders from v1 (inline comment parsing + inline POST/PUT writes) to v2 (helper-mediated JSONL state log).

**Footprint**: One Markdown file edit (`scripts/openclaw/agents/felix-admin-habits/AGENTS.md`) + one runbook update (`docs/runbooks/habits-ops.md`). Zero Python code changes per C-005.

**Sizing**: 1 work package, 6 subtasks. Cohesive scope, tightly coupled — splitting into multiple WPs would produce undersized fragments that share the same authoritative surface.

---

## Subtask Index

| ID | Description | WP | Parallel |
|----|-------------|----|----------|
| T001 | AGENTS.md — restructure Morning check-in section (add Step 0; v2 helper names; drop Step 3) | WP01 | |
| T002 | AGENTS.md — restructure Completion marking section (helper invocation; state mapping table) | WP01 | |
| T003 | AGENTS.md — switch Weekly pattern report data source from comments to JSONL state_log | WP01 | |
| T004 | AGENTS.md — light annotations on 3 sections (Comment format pointer + Track record query + Action Logging) | WP01 | |
| T005 | docs/runbooks/habits-ops.md — document cutover date + new workflow shape | WP01 | |
| T006 | Validation — run grep contract + size-budget check; commit | WP01 | |

---

## WP01 — Cutover AGENTS.md to v2 workflow + update runbook

- **Prompt**: [WP01-cutover-agents-md-to-v2-workflow.md](tasks/WP01-cutover-agents-md-to-v2-workflow.md)
- **Goal**: Switch the deployed habits agent's standing orders (`AGENTS.md`) from the v1 comment-parsing flow to the v2 JSONL-based flow. Update the operator runbook to document the cutover.
- **Priority**: P1 (the only WP; mission-blocking)
- **Estimated prompt size**: ~450 lines
- **Independent test**: After merge, operator runs the documented deploy command. Next morning cron tick produces a WhatsApp check-in. Tuesday cron tick omits any workout task.
- **Includes**:
  - [ ] T001 AGENTS.md — restructure Morning check-in section (WP01)
  - [ ] T002 AGENTS.md — restructure Completion marking section (WP01)
  - [ ] T003 AGENTS.md — Weekly pattern report data source switch (WP01)
  - [ ] T004 AGENTS.md — light annotations (Comment format + Track record query + Action Logging) (WP01)
  - [ ] T005 docs/runbooks/habits-ops.md — cutover documentation update (WP01)
  - [ ] T006 Validation — grep contract + size budget + commit (WP01)
- **Dependencies**: None (foundation work from Phases 1-4 already on main)
- **Owned files**:
  - `scripts/openclaw/agents/felix-admin-habits/AGENTS.md`
  - `docs/runbooks/habits-ops.md`
- **Risks**:
  - Implementer could over-rewrite sections that should remain byte-identical (Governance, Authority, Privacy, etc.). Mitigation: contract file enumerates which sections change.
  - Grep contract assertion could miss semantic issues that only the post-deploy smoke test surfaces. Mitigation: quickstart.md drives operator smoke test.

---

## Parallelization

No parallelization possible — single WP. The WP is sequential by nature (one file edited section-by-section).

---

## MVP Scope Recommendation

WP01 IS the MVP. There is no smaller scope that delivers the cutover. The post-soak decommission mission (delete v1 scripts, rename `_v2.py`) is explicitly out of scope per C-001 / C-002.

---

## Requirement Coverage

WP01 covers all functional requirements:

- **FR-001, FR-002, FR-003** (Step 0 added; v1 helpers renamed to v2) → T001
- **FR-004** (record_completion.py invocation; no inline POST/PUT) → T002
- **FR-005** (comment-parsing instructions removed; JSONL pointer notes) → T002, T003, T004
- **FR-006** (preserve identity / format / weekly-report semantics) → T001, T002, T003
- **FR-007** (deploy command unchanged) → T005 (runbook re-references existing command)
- **FR-008** (post-deploy sha256 match) → T006 (validation includes byte-equality contract)
- **FR-009** (v1 scripts NOT deleted) → C-001 enforced implicitly (no delete operations in WP01)
- **FR-010** (runbook documents cutover) → T005

Non-functional:

- **NFR-002** (AGENTS.md size budget) → T006
- **NFR-005** (no new secrets) → enforced by content discipline; verified visually during review

---

## Next Steps

After tasks finalize, the next command is `/spec-kitty.implement` (or auto-drive via the `spec-kitty-implement-review` skill).
