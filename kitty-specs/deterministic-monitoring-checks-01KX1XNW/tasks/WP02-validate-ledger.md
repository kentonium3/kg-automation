---
work_package_id: WP02
title: Ledger-replay + synthetic-fixture validation (INV-006)
dependencies:
- WP01
requirement_refs:
- C-006
- FR-011
- NFR-006
tracker_refs: []
planning_base_branch: feat/deterministic-monitoring-checks
merge_target_branch: feat/deterministic-monitoring-checks
branch_strategy: Planning artifacts for this mission were generated on feat/deterministic-monitoring-checks. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/deterministic-monitoring-checks unless the human explicitly redirects the landing branch.
subtasks:
- T007
- T008
- T009
- T010
agent: "claude:opus:reviewer-renata:reviewer"
history: []
agent_profile: python-pedro
authoritative_surface: scripts/openclaw/heartbeat_gate/validate_ledger.py
create_intent:
- scripts/openclaw/heartbeat_gate/validate_ledger.py
- scripts/openclaw/heartbeat_gate/tests/test_validate_ledger.py
- scripts/openclaw/heartbeat_gate/tests/fixtures/gate-ledger-sample.jsonl
execution_mode: code_change
owned_files:
- scripts/openclaw/heartbeat_gate/validate_ledger.py
- scripts/openclaw/heartbeat_gate/tests/test_validate_ledger.py
- scripts/openclaw/heartbeat_gate/tests/fixtures/**
role: implementer
tags: []
shell_pid: "70639"
---

## ⚡ Do This First: Load Agent Profile

`/ad-hoc-profile-load python-pedro` (role: implementer). Adopt its identity + TDD
discipline before reading further.

## Objective

Ship the INV-006 forcing function: a replay harness that re-runs the deterministic
escalation rule over a gate-ledger and asserts **0 missed escalations** (reporting the
over-escalation rate), plus synthetic-fixture tests that validate the
`LOG_AND_SKIP`↔`HEARTBEAT_OK` label split that the ledger replay cannot cover.

## Context (read these)

- Contract: `contracts/escalation-rule.contract.md` — see **"Historical-fidelity
  invariant"** and its **scope note** (the replay validates the escalate boolean ONLY;
  the ledger lacks `issues_filed`/per-signal counts).
- Depends on WP01's `decide_deterministic` (import it; do not reimplement the rule).
- Ledger shape: `scripts/openclaw/heartbeat_gate/ledger.py` (`GateTickRecord`) — the
  historical records carry `novelty_markers_seen`, `heartbeat_md_state`, `errors`,
  `outcome`.
- Live ledger (for the real run, not committed): `/data/services/openclaw/
  felix-heartbeat-gate/gate-ledger.jsonl` (1748 records; 42 escalate). The design-time
  replay already showed 0 missed / 0 over.

## Subtasks

### T007 — `validate_ledger.py`
- New module `scripts/openclaw/heartbeat_gate/validate_ledger.py`, runnable as
  `python3 -m scripts.openclaw.heartbeat_gate.validate_ledger --ledger PATH` (module
  form — office2 is python3-only; C-006).
- For each JSONL record, recompute the **escalation boolean** from
  `novelty_markers_seen` / `heartbeat_md_state` / `errors` (mirror WP01's escalate
  predicate — import a shared helper from `gate.py` rather than duplicating the
  boolean, so the two can never drift).
- Assert every record with `outcome == "ESCALATE_TO_SONNET"` recomputes to escalate
  (count **missed**); count **over**-escalations among non-escalate records; print a
  summary: total, actual escalate/non-escalate, missed, over (count + %).
- Exit non-zero if `missed > 0` (this is the gate); over-escalation is reported, and
  fails only if it exceeds the NFR-006 threshold (5%). Self-contained, stdlib-only.
- Keep it OUT of `.coveragerc` `source` (like `skills_snapshot.py`) so it doesn't move
  the coverage gate, OR fully cover it — confirm against the repo's coverage config.

### T008 — Fixture ledger `[P]`
- Commit a small `scripts/openclaw/heartbeat_gate/tests/fixtures/gate-ledger-sample.jsonl`
  with hand-authored records covering: an `ESCALATE_TO_SONNET` via novelty; one via
  `has_tasks`; one via `errors`; a `HEARTBEAT_OK`; a `LOG_AND_SKIP`. This is the
  committed regression substrate (do not depend on the live office2 ledger in tests).

### T009 — Synthetic `GateContext` label-split fixtures + tests
- In `tests/test_validate_ledger.py` (or a sibling), build synthetic `GateContext`
  objects and assert `decide_deterministic` labels:
  - `issues_filed` non-empty, empty `novelty_markers`, `heartbeat_md_state="empty"`,
    no errors → `LOG_AND_SKIP` (NOT escalate).
  - a `signals_evaluated` entry with non-zero cycle activity but `threshold_status
    == "below"` → `LOG_AND_SKIP`.
  - fully quiet → `HEARTBEAT_OK`.
  - each escalation trigger individually → `ESCALATE_TO_SONNET`.
- This is where the 3-label fidelity is proven (the ledger replay cannot, per contract).

### T010 — Replay test + suite wiring
- `test_validate_ledger.py`: run the harness against the T008 fixture; assert
  `missed == 0` and the reported over-escalation is within threshold; assert the CLI
  exit code contract (0 on clean, non-zero on injected missed — add a fixture with a
  deliberately-mislabeled record to prove the gate actually fails).
- Ensure `python3 -m pytest scripts/openclaw/heartbeat_gate/tests/` stays green.

## Branch Strategy

Base + merge target `feat/deterministic-monitoring-checks`; worktrees per `lanes.json`.
Depends on WP01 — your lane branches from WP01's output; `decide_deterministic` and the
shared escalate helper must already exist.

## Definition of Done

- [ ] `validate_ledger.py` implemented (module-runnable; missed>0 → non-zero exit).
- [ ] Fixture ledger committed with all 3 label kinds + all 3 escalation triggers.
- [ ] Synthetic label-split tests pass; a deliberately-mislabeled fixture proves the
      harness fails as designed.
- [ ] `python3 -m pytest scripts/openclaw/heartbeat_gate/tests/` green.
- [ ] Escalate predicate is SHARED with WP01 (imported), not duplicated.

## Risks / reviewer guidance

- Do NOT let the replay claim to validate the label split — it validates escalation
  only. Reviewer: confirm the label split is covered by synthetic fixtures, and that
  the escalate predicate is a single shared source of truth with WP01.
- The real 1748-tick run is an operational verification step (quickstart #13), not a
  unit test — don't commit the live ledger.

## Activity Log

- 2026-07-08T23:37:51Z – claude:sonnet:python-pedro:implementer – shell_pid=67708 – Assigned agent via action command
- 2026-07-08T23:43:11Z – claude:sonnet:python-pedro:implementer – shell_pid=67708 – Ready for review: INV-006 replay harness + synthetic label fixtures
- 2026-07-08T23:43:39Z – claude:opus:reviewer-renata:reviewer – shell_pid=70639 – Started review via action command
- 2026-07-08T23:45:50Z – user – shell_pid=70639 – Review passed: INV-006 replay harness imports gate.decide_deterministic (single source of truth, no duplicated escalate boolean); mislabeled fixture exits non-zero (gate has teeth); ledger replay validates escalate-boolean ONLY with docstrings not over-claiming label split; synthetic GateContext fixtures cover LOG_AND_SKIP<->HEARTBEAT_OK split; sample fixture covers all 3 escalate triggers + both non-escalate labels; validate_ledger.py correctly kept OUT of .coveragerc source (skills_snapshot precedent); scope clean (only owned files in WP02 commit 55c74f06); full suite 133 passed.
