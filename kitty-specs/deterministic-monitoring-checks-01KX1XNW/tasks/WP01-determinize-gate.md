---
work_package_id: WP01
title: Determinize the heartbeat-gate decision
dependencies: []
requirement_refs:
- C-004
- C-006
- FR-001
- FR-002
- FR-003
- FR-004
- FR-005
- FR-006
- FR-007
- FR-008
- NFR-001
- NFR-004
- NFR-005
tracker_refs: []
planning_base_branch: feat/deterministic-monitoring-checks
merge_target_branch: feat/deterministic-monitoring-checks
branch_strategy: Planning artifacts for this mission were generated on feat/deterministic-monitoring-checks. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/deterministic-monitoring-checks unless the human explicitly redirects the landing branch.
subtasks:
- T001
- T002
- T003
- T004
- T005
- T006
agent: "claude:opus:reviewer-renata:reviewer"
history: []
agent_profile: python-pedro
authoritative_surface: scripts/openclaw/heartbeat_gate/gate.py
create_intent: []
execution_mode: code_change
owned_files:
- scripts/openclaw/heartbeat_gate/gate.py
- scripts/openclaw/heartbeat_gate/run.py
- scripts/openclaw/heartbeat_gate/prompts/routing.prompt.md
- scripts/openclaw/heartbeat_gate/baselines/measure-tokens.py
- scripts/openclaw/heartbeat_gate/tests/test_gate_routing.py
- scripts/openclaw/heartbeat_gate/tests/test_run.py
- scripts/openclaw/heartbeat_gate/tests/test_measure_tokens.py
role: implementer
tags: []
shell_pid: "64339"
---

## ⚡ Do This First: Load Agent Profile

Before reading anything else, load your assigned profile:
`/ad-hoc-profile-load python-pedro` (role: implementer). Adopt its identity, boundaries,
and TDD discipline for this WP.

## Objective

Replace the heartbeat-gate's per-tick **Haiku call** (`gate.decide`) with a pure,
standard-library-only function `decide_deterministic(context) -> GateDecision` that
reproduces the routing prompt's exact boolean escalation contract, emits a
deterministically-built reason, and records **zero** token counts. Preserve the
orchestrator's steps 1/3/4 and the fail-safe exactly. No LLM in the tick hot path.

## Context (read these)

- Contract: `contracts/escalation-rule.contract.md` — the truth table, totality
  invariant, reason parity, and historical-fidelity scope. **This is authoritative.**
- Current code: `scripts/openclaw/heartbeat_gate/gate.py` (the Haiku wrapper to
  replace), `run.py` (orchestrator; step 2 call site at ~line 204; fail-safe), and
  `context.py` (the deterministic `GateContext` — DO NOT change; it is WP-out-of-scope
  and produces the rule's input).
- Routing semantics being reproduced: `prompts/routing.prompt.md` — the three outcomes
  are defined there as boolean conditions.
- **Design-time proof**: the rule was replayed over 1748 historical ticks → 0 missed /
  0 over escalations. The rule is not speculative; it is exact.

## Subtasks

### T001 — Implement `decide_deterministic(context) -> GateDecision`
Add to `gate.py` (stdlib-only; no `anthropic` import anywhere in the call path).
- `escalate := len(context.novelty_markers) > 0 or context.heartbeat_md_state ==
  "has_tasks" or len(context.errors) > 0`.
- If `escalate`: `outcome="ESCALATE_TO_SONNET"`, `reason=build_reason(context)`.
- Else sub-label (both are no-Sonnet): `LOG_AND_SKIP` when
  `len(context.issues_filed) > 0` OR any entry in `context.signals_evaluated` has
  non-zero cycle activity while `threshold_status == "below"`; otherwise `HEARTBEAT_OK`.
- Return `GateDecision(outcome, reason, input_tokens=0, cache_hit_tokens=0, output_tokens=0)`.
- **Totality (FR-007, Codex #2)**: the function MUST NOT raise on any `GateContext`
  that `context.load_context` can produce — guard every field access (treat missing/
  non-list fields as empty). Do not assume well-formed `signals_evaluated` entries.

### T002 — Deterministic `build_reason(context)`
- One paragraph, ≤500 chars, citing only the firing triggers: novelty marker IDs
  (from `novelty_markers`), `"heartbeat contract has tasks"` when `has_tasks`, and
  error types (from `errors[].error_type`).
- **No action/recommendation framing** (no "so Sonnet can…", "should") — report
  triggers only (Codex #8). Truncate to 500 chars defensively.

### T003 — Rewire `run.py` step 2 + belt-and-suspenders fail-safe
- Replace the `_gate.decide(context_obj, api_key_path=…, prompt_path=…)` call with
  `_gate.decide_deterministic(context_obj)`.
- **Broaden the step-2 `except`** (currently only `GateRoutingError` + `FileNotFoundError`)
  to also catch `Exception` → the existing fallback path (`fallback_invoked=True`,
  escalate, tokens 0, exit 0). This is defense-in-depth behind T001's totality so an
  impl bug never hits the exit-1 emergency path (FR-007).
- Keep steps 1 (`load_context`), 3 (`escalator.escalate`), 4 (`ledger.write_tick_record`)
  and `_emergency_fallback_write` behaviorally unchanged.

### T004 — Remove the LLM surface from the tick path (no vestiges)
- Delete the `--api-key` and `--prompt` argparse flags from `run.py`'s parser and the
  corresponding `run_tick` parameters (`api_key_path`, `prompt_path`) where they only
  fed the decide path. **No vestigial no-op flags** (migration hygiene / DIR-024).
- Remove the Anthropic call machinery from `gate.py` (the `decide` function, `read_api_key`,
  `_build_client`, `_split_prompt`/`_render_user_section` if only the Haiku path used
  them, retry/parse helpers, `anthropic` imports). Keep `GateDecision` and
  `GateRoutingError` only if still referenced; otherwise remove `GateRoutingError` too
  and update `run.py`'s except accordingly. The tick path MUST import no third-party
  package (NFR-005).
- Grep for stray importers before deleting: `grep -rn "heartbeat_gate.gate import\|gate.decide\|read_api_key" scripts/ tests/`.

### T005 — Update tests (`test_gate_routing.py`, `test_run.py`)
- `test_gate_routing.py`: replace Haiku-stub tests with deterministic-outcome tests —
  escalate on each trigger (novelty / has_tasks / errors); `HEARTBEAT_OK` on fully
  quiet; `LOG_AND_SKIP` on issues_filed-non-empty and on below-but-nonzero activity;
  reason cites triggers and contains no recommendation words; tokens all 0.
- `test_run.py`: remove `client_factory`/Anthropic expectations; add a
  **malformed-but-loaded** tick payload test proving step 2 routes to the fail-safe
  (`fallback_invoked=True`, exit 0) — NOT the exit-1 emergency path.
- Follow existing test style/fixtures in `tests/conftest.py`. Use `python3 -m pytest`.

### T006 — Retire the now-dead LLM baseline artifacts
- `prompts/routing.prompt.md`: it no longer drives a runtime call. Either delete it (if
  nothing imports it) or keep it with a top-of-file `DEPRECATED (#676): retained for
  history; no longer executed` note. Pick based on the T004 grep.
- `baselines/measure-tokens.py` + `tests/test_measure_tokens.py`: this measured the
  Haiku token cost. If it now measures nothing meaningful, neutralize/remove it and
  its test so the suite stays green. Record what you did and why in the WP history.

## Branch Strategy

Planning/base branch: `feat/deterministic-monitoring-checks`. Final merge target:
`feat/deterministic-monitoring-checks`. Execution worktrees are allocated per computed
lane from `lanes.json` — do not hand-create branches.

## Definition of Done

- [ ] `decide_deterministic` implemented, stdlib-only, total; `build_reason` compliant.
- [ ] `run.py` calls it; step-2 `except` broadened; steps 1/3/4 + fail-safe unchanged.
- [ ] `--api-key`/`--prompt` + `anthropic` fully removed from the tick path (no vestiges);
      grep shows no stray importers.
- [ ] Tests updated + green: `python3 -m pytest scripts/openclaw/heartbeat_gate/tests/`.
- [ ] `--dry-run` tick prints `tokens=in:0(cache:0)/out:0`.
- [ ] Malformed-context test proves fail-safe (`fallback_invoked=true`, exit 0).
- [ ] No third-party import remains in the tick path.

## Risks / reviewer guidance

- The subtle risk is FR-007: an uncaught exception in the new decide would silently
  degrade to exit-1 minimal fallback. Reviewer: confirm BOTH T001 totality AND T003's
  broadened except, and that the malformed-context test actually exercises the
  `fallback_invoked=true` path (not the emergency path).
- Confirm the escalation truth table matches the contract EXACTLY (esp. that
  `issues_filed` is NOT an escalation trigger — it only distinguishes LOG_AND_SKIP).
- Confirm zero behavioral change to escalator/ledger.

## Activity Log

- 2026-07-08T23:19:46Z – claude:sonnet:python-pedro:implementer – shell_pid=60249 – Assigned agent via action command
- 2026-07-08T23:27:31Z – claude:sonnet:python-pedro:implementer – shell_pid=60249 – Implementation complete, all tests green, commit 149c7f2c. move-task to for_review is BLOCKED by spec-kitty's own pre-check: an untracked kitty-specs/.../analysis-report.md file (a pre-existing /spec-kitty.analyze artifact from mission init, not created by this WP) that the coordination worktree considers WP01-owned. Reporting per workflow rules rather than committing/force-moving unilaterally.
- 2026-07-08T23:29:02Z – claude:sonnet:python-pedro:implementer – shell_pid=60249 – Ready for review: deterministic gate, no LLM in tick path, fail-safe preserved
- 2026-07-08T23:29:25Z – claude:opus:reviewer-renata:reviewer – shell_pid=64339 – Started review via action command
- 2026-07-08T23:35:46Z – user – shell_pid=64339 – Review passed (reviewer-renata/opus): deterministic gate, truth table exact, totality+fail-safe verified, no LLM in tick path, 114 tests green
