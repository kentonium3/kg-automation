# Tasks — Harden Inbox Capture on Sonnet

**Mission**: harden-inbox-capture-01KWVGZM · **Branch**: `feat/harden-inbox-capture`
**Spec**: [spec.md](./spec.md) · **Plan**: [plan.md](./plan.md)

Phase 1 of #662, corrects #658. Four implementable work packages (repo changes);
**deploy + verify + rebaseline is a post-merge operator step** documented in
[quickstart.md](./quickstart.md) (executed after `feat → main`, not an implement-WP —
it edits office2's `openclaw.json` out-of-band and runs the manual rebaseline).

## Subtask Index

| ID | Description | WP | Parallel |
|----|-------------|----|----------|
| T001 | Invert checker canonical form: exact `CANONICAL_CHECKOUT` const, checkout-cd compliant | WP01 | |
| T002 | Add `RELATIVE_SCRIPT` class; rename `HARDCODED_CD`→`PYTHONPATH_ANCHOR` (flag `${PYTHONPATH:?}`); keep `BARE_M_SCRIPTS` + `HOME_RELATIVE_WRITE` | WP01 | |
| T003 | Update remediation strings + module docstring (cite #662, corrects #658) | WP01 | |
| T004 | Rewrite `test_env_assumptions.py` fixtures/assertions to new policy | WP01 | |
| T005 | Update `test_validate_workspace.py` + `test_env_assumptions_guard.py` (fleet guard) | WP01 | |
| T006 | Correct `docs/runbooks/openclaw-agent-setup.md` (teach checkout-cd, not `${PYTHONPATH:?}`) | WP01 | |
| T010 | Swap all invocation forms in capture `AGENTS.md` to `cd /home/claude/kg-automation && …` (incl. bare `scripts/…felix-file-issue.py`) | WP02 | |
| T011 | Reword `AGENTS.md:74` so no model can negate helper existence | WP02 | |
| T012 | `:haiku`→`:sonnet` identity line (all occurrences) | WP02 | |
| T013 | Apply the same invocation swaps to capture `AGENTS.md.tmpl` | WP02 | |
| T014 | Verify capture passes the inverted checker + `pytest` green | WP02 | |
| T020 | Swap invocation forms in `felix-admin-escalation/AGENTS.md` | WP03 | [P] |
| T021 | Swap invocation forms in `felix-admin-habits/AGENTS.md` | WP03 | [P] |
| T022 | Swap invocation forms in `felix-admin-calendar/AGENTS.md` | WP03 | [P] |
| T023 | Swap invocation forms in `felix-admin-tasker/AGENTS.md` (+ `.tmpl`) | WP03 | [P] |
| T024 | Swap invocation forms in `main/AGENTS.md` | WP03 | [P] |
| T025 | Verify fleet passes the inverted checker (`env_assumptions` = ok) | WP03 | |
| T030 | `service-inventory.json` (+ `service-inventory.md`) capture model haiku→sonnet + correct the PYTHONPATH-drop-in claim | WP04 | [P] |
| T031 | `AGENT-REGISTRY.md` + authoritative `agent-registry.json` capture model haiku→sonnet | WP04 | [P] |

## WP01 — Invert the env-assumption checker + tests + runbook

**Goal**: Make the corrected canonical invocation form (`cd /home/claude/kg-automation && …`)
the compliant one and the `${PYTHONPATH:?}` form a violation, so CI enforces the fix instead
of the bug. This is the gate for WP02/WP03.
**Priority**: P1 (foundational — do first). **Depends on**: none.
**Independent test**: `pytest scripts/openclaw/agents/tests/` green; `python3 -m
scripts.openclaw.agents.env_assumptions` runs (will still report findings until WP02/03 land).
**Requirements**: FR-002. **Prompt**: [tasks/WP01-invert-env-checker.md](./tasks/WP01-invert-env-checker.md) (~350 lines).

- [x] T001 Invert checker canonical form: exact `CANONICAL_CHECKOUT` const (WP01)
- [x] T002 Add `RELATIVE_SCRIPT`; rename `HARDCODED_CD`→`PYTHONPATH_ANCHOR`; keep bare-m + home-write (WP01)
- [x] T003 Update remediation strings + docstring (WP01)
- [x] T004 Rewrite `test_env_assumptions.py` (WP01)
- [x] T005 Update `test_validate_workspace.py` + `test_env_assumptions_guard.py` (WP01)
- [x] T006 Correct `openclaw-agent-setup.md` runbook (WP01)

## WP02 — Capture prompt hardening (invocation swap + reword + sonnet identity)

**Goal**: Make `felix-admin-capture` reliable: self-contained invocations, no negatable
"helpers live at `<path>`" prose, sonnet identity. Owns the whole capture prompt so the
swap + reword + identity land atomically (no ownership split).
**Priority**: P1. **Depends on**: WP01 (checker must accept the new form).
**Independent test**: capture `AGENTS.md`/`.tmpl` pass the inverted checker; `pytest` green;
grep shows zero `${PYTHONPATH:?}` and zero bare `scripts/…py` invocations in capture.
**Requirements**: FR-001, FR-003, FR-004, FR-005. **Prompt**: [tasks/WP02-capture-prompt-hardening.md](./tasks/WP02-capture-prompt-hardening.md) (~300 lines).

- [x] T010 Swap all capture `AGENTS.md` invocations to checkout-cd form (incl. bare felix-file-issue.py) (WP02)
- [x] T011 Reword `AGENTS.md:74` (WP02)
- [x] T012 `:haiku`→`:sonnet` identity (WP02)
- [x] T013 Apply swaps to capture `AGENTS.md.tmpl` (WP02)
- [x] T014 Verify capture passes checker + pytest (WP02)

## WP03 — Fleet invocation-form swap (escalation, habits, calendar, tasker, main)

**Goal**: Apply the self-contained invocation form to the other five active agents so the
whole fleet stops failing under exec sanitization.
**Priority**: P1. **Depends on**: WP01. **Parallel with**: WP02, WP04.
**Independent test**: `python3 -m scripts.openclaw.agents.env_assumptions` reports **ok**
fleet-wide (with WP02 also landed); `pytest` green.
**Requirements**: FR-001. **Prompt**: [tasks/WP03-fleet-invocation-swap.md](./tasks/WP03-fleet-invocation-swap.md) (~280 lines).

- [ ] T020 Swap `felix-admin-escalation/AGENTS.md` (WP03)
- [ ] T021 Swap `felix-admin-habits/AGENTS.md` (WP03)
- [ ] T022 Swap `felix-admin-calendar/AGENTS.md` (WP03)
- [ ] T023 Swap `felix-admin-tasker/AGENTS.md` (+ `.tmpl`) (WP03)
- [ ] T024 Swap `main/AGENTS.md` (WP03)
- [ ] T025 Verify fleet checker = ok (WP03)

## WP04 — Model doc updates (arch data + agent registry)

**Goal**: Keep the docs consistent with the sonnet move so nothing split-brains after merge.
**Priority**: P2. **Depends on**: none (independent doc edits). **Parallel with**: WP02, WP03.
**Independent test**: `service-inventory.json`, `agent-registry.json` show capture on
`anthropic/claude-sonnet-4-6`; architecture-data validator green.
**Requirements**: FR-004. **Prompt**: [tasks/WP04-model-doc-updates.md](./tasks/WP04-model-doc-updates.md) (~200 lines).

- [ ] T030 `service-inventory.json` + `service-inventory.md`: capture model + PYTHONPATH-drop-in claim (WP04)
- [ ] T031 `AGENT-REGISTRY.md` + `agent-registry.json`: capture model (WP04)

## Post-merge operator step (not a WP)

After all WPs merge and `feat/harden-inbox-capture → main` (following the post-merge Codex
review), execute [quickstart.md](./quickstart.md) steps 4–13 on office2: confirm the six
prompts auto-synced, flip `openclaw.json` capture model to `anthropic/claude-sonnet-4-6`,
restart the gateway, confirm model-in-effect, then manual rebaseline, then run behavioral
verification (SC-001..008). Record `Rebaseline: completed at <ts>` on the merge.

## Dependencies

- WP01 → WP02, WP03 (checker defines "compliant" before the fleet is validated against it).
- WP04 independent (may run anytime).
- WP02, WP03, WP04 may run in parallel after WP01.

## MVP

WP01 + WP02 (checker + capture) deliver the core reliability fix for the headline symptom
(inbox capture). WP03 extends it fleet-wide; WP04 keeps docs honest.
