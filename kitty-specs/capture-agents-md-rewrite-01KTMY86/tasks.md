# Tasks: Capture AGENTS.md Rewrite (Directive-6 half-2)

**Mission**: `capture-agents-md-rewrite-01KTMY86`
**Branch**: `kitty/mission-capture-agents-md-rewrite-01KTMY86`
**Spec**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)
**Date**: 2026-06-08

## Subtask Index

| ID | Description | WP | Parallel |
|---|---|---|---|
| T001 | Rewrite `scripts/openclaw/agents/felix-admin-capture/AGENTS.md` per spec.md § Structural map | WP01 | |
| T002 | Verify hard-ceiling: `wc -c AGENTS.md` ≤ 14,000; ideal mid-range 4,500-8,500 | WP01 | |
| T003 | Verify Step 5 invariant lands in first 8,000 chars; verify `-m` form everywhere; verify no existing-helper invocation regression | WP01 | |
| T004 | Update `docs/design/architecture/data/service-inventory.json` capture entry: bump `last_updated`, prepend mission to `updated_by`, update `notes` | WP01 | |

## Work Packages

### WP01 — AGENTS.md rewrite + arch-doc update

- **Goal**: Rewrite the prompt per spec's structural map; reduce 1,215 lines → ~250-400 lines (4,500-8,500 chars); keep judgment surfaces verbatim; replace deterministic recipes with `-m` invocations.
- **Priority**: P1
- **Independent test**:
  - `wc -c scripts/openclaw/agents/felix-admin-capture/AGENTS.md` ≤ 14,000 (NFR-001)
  - `head -c 8000 scripts/openclaw/agents/felix-admin-capture/AGENTS.md | grep -i "do NOT delete\|preserve"` matches (FR-004)
  - `grep -c "python3 scripts/inbox/" scripts/openclaw/agents/felix-admin-capture/AGENTS.md` returns 0 (NFR-002 — no script-path form)
  - `grep -c "python3 -m scripts.inbox" scripts/openclaw/agents/felix-admin-capture/AGENTS.md` returns ≥ 6 (FR-005, all new helpers referenced)
  - `python3 -c "import json; json.load(open('docs/design/architecture/data/service-inventory.json'))"` exits 0
- **Dependencies**: none
- **Prompt file**: [tasks/WP01-rewrite.md](./tasks/WP01-rewrite.md)

Subtasks:
- [x] T001 Rewrite AGENTS.md per structural map (WP01)
- [x] T002 Verify size hard ceiling + mid-target (WP01)
- [x] T003 Verify Step 5 invariant placement + `-m` form + no existing-helper regression (WP01)
- [x] T004 Update service-inventory.json capture entry (WP01)

## MVP Scope

WP01 IS the mission. No deferred work; everything ships in one WP.

## Test Strategy

No new automated tests. Verification is:
- Static checks (size, grep patterns) — listed in WP01's Independent test
- Existing helper test suite still passes (`pytest tests/inbox/` returns 139 passing)
- Post-merge operator verification (FR-015) — `grep "bootstrap file AGENTS.md.*truncating" /tmp/openclaw/openclaw-<date>.log` returns no matches for felix-admin-capture ticks in the 24h after deploy

## Reviewer Guidance

- Independent: ideally codex (already verified working in half-1 per #330). Falling back to claude is acceptable since #330 is already closed.
- Focus on (a) hard ceiling actually met, (b) Step 5 invariant location, (c) every `-m scripts.inbox` reference uses the EXACT module path, (d) no judgment surface (Output Discipline Hard Rules, Goal declaration validation rules, Privacy absolute rule, Edge cases) was inadvertently trimmed.
- Reviewer should also do a "voice spot check": read 3-4 random judgment surfaces and confirm Kent's first-person framing survived.
