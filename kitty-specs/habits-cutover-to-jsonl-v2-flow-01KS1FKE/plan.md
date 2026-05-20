# Implementation Plan: Habits cutover to JSONL v2 flow

**Mission**: `habits-cutover-to-jsonl-v2-flow-01KS1FKE`
**Mission ID**: `01KS1FKE0QHYEHZW684YEJNEPW`
**Branch**: `main` (planning + merge target; matches current)
**Date**: 2026-05-19 (UTC 2026-05-20)
**Spec**: [spec.md](spec.md) · **Source issue**: [#308](https://github.com/kentonium3/issues/308) · **ADR**: [0002 Phase 5](../../docs/design/architecture/adr/0002-felix-vikunja-task-model.md)

## Summary

A Markdown edit to `scripts/openclaw/agents/felix-admin-habits/AGENTS.md` plus a runbook documentation update. Zero Python code changes (per spec C-005). The mission converts the deployed habits agent from v1 (comment-parsing + inline POST/PUT to Vikunja) to v2 (helper-mediated JSONL state log). Operator runs the documented `cat | ssh` deploy command post-merge; 2-3 day stabilization soak with fail-forward posture.

## Technical Context

**Language/Version**: Markdown (no programming language; AGENTS.md is the agent's prose contract)
**Primary Dependencies**: None new. All helpers referenced by the new AGENTS.md (`reconcile_completions.py`, `query_active_habits_v2.py`, `exclude_completed_v2.py`, `record_completion.py`) are already on main and deployed to office2 (Phase 3 #306 commit `188268d` + Phase 4 #307 commit `543aa3e` + #333 G6 fix `550fde6`).
**Storage**: N/A for the mission itself. Downstream: the cutover causes the habits agent to write to `/data/services/openclaw/state/habits-history.jsonl` (Phase 2 substrate; currently has 31 backfilled records).
**Testing**: No Python tests to update (spec C-005). Test approach is grep-based content assertions + manual smoke test of the post-deploy cron tick.
**Target Platform**: office2 (Ubuntu 24.04 LTS). The agent runs under the openclaw-gateway service.
**Project Type**: Single project — Markdown edit + Markdown documentation update.
**Performance Goals**: Post-cutover cron runtime ≤ 120s (NFR-001).
**Constraints**: No Python code changes (C-005); v1 sibling scripts preserved (C-001); cron config untouched (C-003); model unchanged (C-004); felix-bot identity only (C-006); fail-forward posture (C-007).
**Scale/Scope**: One Markdown file (~16KB → ~16-20KB), one runbook update (~50 lines added).

## Charter Check

Charter context: compact mode, no enforced directives or tactics. **No gate violations.**

## Project Structure

### Documentation (this feature)

```
kitty-specs/habits-cutover-to-jsonl-v2-flow-01KS1FKE/
├── plan.md              # This file
├── spec.md              # Mission specification
├── research.md          # Phase 0 — tactical decisions about content shape
├── data-model.md        # Phase 1 — AGENTS.md section map (BEFORE/AFTER)
├── quickstart.md        # Phase 1 — operator deploy walkthrough
├── contracts/
│   └── agents-md-sections.md  # Required content of changed AGENTS.md sections
└── tasks/               # Phase 2 — work packages (NOT created here)
```

### Source Code (repository root)

```
scripts/openclaw/agents/felix-admin-habits/
└── AGENTS.md                                # MODIFIED — primary deliverable

docs/runbooks/
└── habits-ops.md                            # MODIFIED — cutover date + new workflow noted

# No other files change. Helpers remain as-is (C-005).
```

**Structure Decision**: One Markdown edit + one Markdown doc update. No code changes. No new directories. The mission's footprint is minimal but its operational impact is the most-visible Felix interaction in Kent's daily routine.

## Complexity Tracking

No charter check violations. One design tension worth noting in the plan: **Step 3 (set_due_dates.py) becomes redundant** with v2's reliance on Vikunja's native `repeat_after`. Vikunja's auto-advance handles the due-date roll, so the agent no longer needs to manually set `due_date = today` on each habit. The Plan decision below resolves this.

---

## Plan

Both phases (research + design) execute in this single pass. Phase 5 has no code work, so design artifacts focus on **content** of the AGENTS.md edit.

### Phase 0 — Research artifacts

See [research.md](research.md). Six tactical content decisions documented:

1. **D1 — Step 3 (set_due_dates.py) disposition**: REMOVE from the morning workflow. Vikunja's native `repeat_after` from Phase 3 (#306) handles due_date roll automatically when a task is marked done=true. The `set_due_dates.py` helper itself stays in the repo for now (out of scope per C-001) but is no longer invoked.
2. **D2 — Weekly pattern report data source**: switch from Vikunja comment-parsing to JSONL state log via `state_log.read("habits", date_from=..., date_to=...)`. The weekly report is a downstream consumer of the same canonical history as the daily flow. Keeps consistency.
3. **D3 — Comment format specification section**: KEEP in AGENTS.md as historical context. The Phase 3 `record_completion.py` still writes `[Felix] <date> | <state>` comments as the Vikunja UI mirror; the format spec stays accurate. Add a short pointer note saying "JSONL log is canonical history; this comment format is the UI mirror written by record_completion.py."
4. **D4 — Testing the AGENTS.md change**: grep-based content assertions in the implementation prompt's validation steps (e.g., `grep "reconcile_completions" AGENTS.md`, `grep -v "query_active_habits.py" AGENTS.md`'s workflow section). No pytest changes. Final validation is the manual smoke test of the post-deploy cron tick.
5. **D5 — Operator deploy procedure**: re-use the existing `cat | ssh` sync command from `docs/runbooks/habits-ops.md`. No new deploy machinery introduced. The runbook gets one new section: "Phase 5 cutover (2026-05-XX)" documenting that the cutover happened on a specific date.
6. **D6 — Action Logging section update**: the existing "Action Logging" section (line 411 of current AGENTS.md) references logging completion actions. Update to clarify that action logs now reference the JSONL state_log entries rather than embedded comment writes — but the action-logging mechanism itself (write to agent-activity dir) is unchanged.

### Phase 1 — Design artifacts

- [data-model.md](data-model.md) — AGENTS.md section-by-section BEFORE/AFTER map (which sections change, which stay, which gain notes).
- [contracts/agents-md-sections.md](contracts/agents-md-sections.md) — required content of each changed section (the implementer reads this to know exactly what the new AGENTS.md must contain).
- [quickstart.md](quickstart.md) — operator walkthrough: pull, deploy via cat|ssh, sha256 verify, smoke-test the next morning tick.

### Charter re-check (post-design)

Same outcome — no constraints. Pass.

---

## Branch contract (restated)

- **Current branch at plan start**: `main`
- **Planning/base branch**: `main`
- **Final merge target**: `main`
- **branch_matches_target**: `true`

Completed changes from this mission merge into `main`. The operator then runs the documented deploy command to sync AGENTS.md to office2.

---

## Stop

Planning artifacts complete. Next: `/spec-kitty.tasks` to break the plan into work packages.
