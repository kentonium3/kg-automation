---
work_package_id: WP01
title: Invert the env-assumption checker + tests + authoring runbook
dependencies: []
requirement_refs:
- FR-002
tracker_refs: []
planning_base_branch: feat/harden-inbox-capture
merge_target_branch: feat/harden-inbox-capture
branch_strategy: Planning artifacts for this mission were generated on feat/harden-inbox-capture. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/harden-inbox-capture unless the human explicitly redirects the landing branch.
subtasks:
- T001
- T002
- T003
- T004
- T005
- T006
agent: "claude"
shell_pid: "38435"
history:
- 2026-07-06 authored from plan IC-01 (+ post-plan Codex HIGH-2/MED-4/HIGH-3)
agent_profile: python-pedro
authoritative_surface: scripts/openclaw/agents/env_assumptions.py
create_intent: []
execution_mode: code_change
model: claude-sonnet-4-6
owned_files:
- scripts/openclaw/agents/env_assumptions.py
- scripts/openclaw/agents/tests/test_env_assumptions.py
- scripts/openclaw/agents/tests/test_env_assumptions_guard.py
- scripts/openclaw/agents/tests/test_validate_workspace.py
- docs/runbooks/openclaw-agent-setup.md
role: implementer
tags: []
---

## ⚡ Do This First: Load Agent Profile

Before reading anything else, run `/ad-hoc-profile-load python-pedro` (role: implementer).
Then read this WP top to bottom, plus `../contracts/env-assumptions-policy.md`,
`../research.md` (D1/D2/D3), and `../data-model.md` (EnvAssumptionPolicy transition table).

## Objective

Invert `scripts/openclaw/agents/env_assumptions.py` so the **corrected** canonical helper
invocation is compliant and the broken `${PYTHONPATH:?}` form is a violation. This checker is
imported by the Test-CI fleet guard (`test_env_assumptions_guard.py`) and by
`validate_workspace.check_runtime_env_assumptions`, so getting it right here is the gate for
WP02/WP03. This mission **corrects #658**, whose canonical `${PYTHONPATH:?}` form fails under
OpenClaw exec's PYTHONPATH sanitization (see research D1).

**Python 3.11-compatible, stdlib only. Deterministic**: no network, no subprocess, no env
reads, no clock (matches the current module's guarantees).

## Background (why)

OpenClaw's `exec` tool strips `PYTHONPATH`, so `cd "${PYTHONPATH:?PYTHONPATH unset}"` exits 127
on every cron run, and a bare `python3 -m scripts.…` (or relative `python3 scripts/x.py`) fails
with `ModuleNotFoundError` from the deployed workspace cwd. The only working form is the
self-contained, **exact** checkout-cd: `cd /home/claude/kg-automation && python3 -m scripts.…`.

## Subtasks

### T001 — Canonical form: exact checkout-cd

- Add a module constant `CANONICAL_CHECKOUT = "/home/claude/kg-automation"`.
- The compliant anchor is now: `cd /home/claude/kg-automation` (EXACT match of `CANONICAL_CHECKOUT`)
  immediately preceding a relative `python3 -m scripts.<pkg>.<mod>` or `python3 scripts/<path>.py`.
- Replace the old `_PYTHONPATH_ANCHOR_RE` notion of "compliant anchor" with a
  `_CHECKOUT_CD_RE` that matches `cd\s+["']?/home/claude/kg-automation(["']|\s|$)` — exact path,
  **not** "any path containing kg-automation" (Codex MED-4). A `cd /home/kgale/repos/kg-automation`
  or `/tmp/kg-automation` must NOT satisfy the anchor.

### T002 — Violation classes

Update `ViolationKind` and `_classify`:
- **`PYTHONPATH_ANCHOR`** (rename/replace the old `HARDCODED_CD`): flag any command containing
  `${PYTHONPATH:?…}` (reuse a `\$\{PYTHONPATH:\?` regex). It now fails under exec.
- **`RELATIVE_SCRIPT`** (NEW, Codex HIGH-2): flag a relative `python3?\s+scripts/<path>.py` OR a
  bare imperative `scripts/<path>.py` (e.g. prose "invoke `scripts/openclaw/agents/main/felix-file-issue.py`")
  that is NOT preceded by the exact checkout-cd anchor in the same logical line. Mirror the
  `BARE_M_SCRIPTS` "anchor must appear before the invocation" logic.
- **`BARE_M_SCRIPTS`** (keep): `python3 -m scripts.…` NOT preceded by the checkout-cd anchor.
  (The anchor is now the checkout-cd, not `${PYTHONPATH:?}`.)
- **`HARDCODED_ABS_PATH`** (keep): absolute `python3 /…/scripts/x.py` — still a violation.
- **`HOME_RELATIVE_WRITE`** (keep UNCHANGED, from #659): `>>`/`tee` to a `~`/`$HOME` dest.
- Remove the old `HARDCODED_CD` semantics entirely (the exact checkout-cd is now REQUIRED, not
  banned). A `kg-automation` path that is NOT the exact canonical stays a violation (fold into
  `PYTHONPATH_ANCHOR`/`RELATIVE_SCRIPT` remediation or a dedicated non-canonical-cd finding —
  implementer's discretion, but a wrong-path `cd` must NOT pass).
- Preserve: `_logical_lines` (backslash-join + HTML-comment strip), the waiver mechanism
  (`# env-guard: waive <kind>`), and the placeholder skip (`scripts.inbox.<helper>`).

### T003 — Remediation + docstring

- Update `_REMEDIATION` so every kind points at the checkout-cd form
  (`cd /home/claude/kg-automation && python3 -m scripts....` / `... && python3 scripts/....py`).
- Rewrite the module docstring's "Canonical (compliant) form" block to the checkout-cd form and
  cite this mission + #662 (correcting #658). Note the exec-sanitization rationale in one line.

### T004 — Rewrite `test_env_assumptions.py`

- Flip fixtures/assertions: the checkout-cd form is compliant (no findings); `${PYTHONPATH:?}`,
  bare `-m scripts`, relative `python3 scripts/x.py`, bare `scripts/x.py`, and wrong-path `cd`
  are violations with the expected kinds.
- Add cases for the new `RELATIVE_SCRIPT` class (pass: with checkout-cd; fail: without), including
  a backslash-continuation case and a bare-imperative `scripts/…py` case.
- Keep the waiver + HTML-comment + placeholder tests (adjusted to the new canonical).

### T005 — Update the two consumers' tests

- `test_env_assumptions_guard.py` (the Test-CI fleet guard): it scans the live fleet. It will
  only pass once WP02/WP03 land, so make the guard assert against the NEW policy (it should fail
  now on the still-old prompts — that's expected and is what gates WP02/WP03). Do NOT weaken it to
  pass prematurely. If it currently hard-asserts "fleet is clean," keep that assertion pointed at
  the new policy so CI stays red until the fleet is swapped.
- `test_validate_workspace.py`: update any env-assumption fixture/expectation to the new compliant
  form. `check_output_discipline` and `check_privacy_boundary` tests are untouched.

### T006 — Correct the authoring runbook (Codex HIGH-3)

- `docs/runbooks/openclaw-agent-setup.md` currently teaches the `${PYTHONPATH:?}` form and bans
  the checkout-cd (around lines 133/145/155). Rewrite those sections to teach the corrected
  canonical checkout-cd form, so future agent authoring does not reintroduce the broken form.
  Reference this mission / #662 (corrects #658).

## Definition of Done

- [ ] `env_assumptions.py` inverted per T001–T003; stdlib-only, deterministic.
- [ ] `pytest scripts/openclaw/agents/tests/test_env_assumptions.py scripts/openclaw/agents/tests/test_validate_workspace.py -q` green.
- [ ] `test_env_assumptions_guard.py` asserts the NEW policy (may be red against the unswapped
      fleet — that is the intended gate; it goes green after WP02+WP03).
- [ ] Branch coverage holds (`--cov-branch`); use `# pragma: no branch` only for genuinely
      unreachable defensive branches, per repo convention.
- [ ] Runbook teaches the checkout-cd form.

## Reviewer guidance

- Verify the anchor is EXACT-match `/home/claude/kg-automation` (reject `/home/kgale/...`, `/tmp/...`).
- Verify `RELATIVE_SCRIPT` catches both `python3 scripts/x.py` and bare `scripts/x.py`, and that a
  correctly-anchored one passes.
- Verify `${PYTHONPATH:?}` is now flagged and the checkout-cd is compliant (the exact inversion).
- Verify `HOME_RELATIVE_WRITE` and the waiver mechanism are unchanged.

## Branch Strategy

Planning base `feat/harden-inbox-capture`; final merge target `feat/harden-inbox-capture`.
Execution worktrees are allocated per computed lane from `lanes.json`. Command:
`spec-kitty agent action implement WP01 --agent claude`.

## Activity Log

- 2026-07-06T11:50:57Z – claude – shell_pid=28505 – Assigned agent via action command
- 2026-07-06T12:03:52Z – claude – shell_pid=28505 – Checker inverted; unit tests green; fleet guard red-by-design until WP02/03
- 2026-07-06T12:17:08Z – claude – shell_pid=38435 – Started review via action command
