# Research: Tactical content decisions

**Mission**: `habits-cutover-to-jsonl-v2-flow-01KS1FKE`
**Phase**: 0 (research — content decisions for the AGENTS.md edit)

Phase 5 has no code work — the architectural decisions are settled by ADR-0002 and Phases 1-4. This research phase resolves the *content* of the AGENTS.md edit: which sections change, what new instructions look like, what existing instructions are preserved/removed/annotated.

---

## D1 — Step 3 (set_due_dates.py) disposition

**Decision**: REMOVE the Step 3 invocation from the morning check-in workflow in AGENTS.md. Leave `scripts/habits/set_due_dates.py` in the repo (out of scope per C-001) but no longer invoke it during the daily flow.

**Rationale**:
- The original Step 3 existed because v1 habit tasks had `repeat_after=0` (per the Vikunja research doc baseline). The agent manually PATCHed `due_date = end-of-day-ET` to make habits appear in Vikunja's Today filter.
- Phase 3 (#306) set `repeat_after` to a positive value for all 7 daily habits (86400) plus the 3 new MWF tasks (604800). Vikunja's native auto-advance now handles `due_date` rolling automatically when a task is marked `done=true`.
- The set_due_dates.py invocation is now a no-op at best, harmful at worst (could set due_date to a different value than Vikunja's native logic expects).

**Rejected alternatives**:
- **Keep Step 3 as a defensive belt-and-suspenders measure**: confuses the workflow; the new path is "Vikunja handles dates."
- **Delete `set_due_dates.py` outright**: violates C-001 (v1 scripts preserved during the soak). Defer to the post-soak decommission mission.

---

## D2 — Weekly pattern report data source

**Decision**: Update the "Weekly pattern report" section's data source from Vikunja comment-parsing to JSONL state_log queries (`state_log.read("habits", date_from=..., date_to=..., state="complete")`).

**Rationale**:
- The weekly report (Sunday 22:00 UTC) currently queries Vikunja's `[Felix]` comments to compute completion rates and patterns.
- Phase 4's backfill populated the JSONL log with the same historical data those comments contain. The JSONL is now the canonical source.
- Keeping the weekly report on comments while the daily flow is on JSONL would mean two different historical-data sources — inconsistency invites drift bugs (e.g., a record manually edited in one place but not the other).
- After cutover, the daily `record_completion.py` writes BOTH to JSONL AND to comments (the comment is the UI mirror per ADR Q3-D). So comments don't disappear; they just stop being the canonical history queryable surface.

**Implementation note**: the weekly report's Steps need updating to invoke a JSONL-reading helper (could be `state_log.read` directly via a small `scripts/habits/weekly_report_helper.py`, OR inline via `python3 -m scripts.common.state_log read --domain habits ...`). The implementer picks; both are acceptable. No new code in `scripts/habits/` is required — the Phase 2 state_log already exposes the CLI surface.

**Rejected alternatives**:
- **Keep weekly report on comments**: drift risk; inconsistent source-of-truth across the agent's flows.
- **Defer weekly report to a separate mission**: artificially fragments the cutover; the report runs Sundays, so the same Sunday post-cutover would surface the inconsistency. Better to handle in this mission.

---

## D3 — Comment format specification section disposition

**Decision**: KEEP the "Comment format specification" section in AGENTS.md. Add a short pointer note clarifying that JSONL is canonical and the comment format is the UI mirror written by `record_completion.py`.

**Rationale**:
- Phase 3's `record_completion.py` still writes `[Felix] <date> | <state> | <note>` comments (the UI mirror per ADR Q3-D). The format spec stays accurate.
- An operator inspecting the agent's behavior (or reading the standing orders) benefits from knowing what the comment shape is — even though the agent no longer parses comments to make decisions.
- Removing the section would force a reader to dig into `record_completion.py`'s source to understand the comment format. Keeping it in AGENTS.md is operator-friendly.

**Rejected alternatives**:
- **Remove the section entirely**: makes the comment format an undocumented helper-side concern; harder for operators to audit.
- **Move to a separate `docs/design/architecture/data/felix-comment-format.md`**: scope creep. The section is short; AGENTS.md is the right home for now.

---

## D4 — Testing the AGENTS.md change

**Decision**: Three test layers, all light-touch:

1. **Grep-based content assertions** in the implementer's validation steps:
   - `grep -F "reconcile_completions" scripts/openclaw/agents/felix-admin-habits/AGENTS.md` returns ≥1 line.
   - `grep -F "query_active_habits_v2" scripts/openclaw/agents/felix-admin-habits/AGENTS.md` returns ≥1 line.
   - `grep -F "exclude_completed_v2" scripts/openclaw/agents/felix-admin-habits/AGENTS.md` returns ≥1 line.
   - `grep -F "record_completion" scripts/openclaw/agents/felix-admin-habits/AGENTS.md` returns ≥1 line.
   - The active workflow sections (Step 0 through Step 6) do NOT reference `query_active_habits.py` or `exclude_completed.py` (the v1 names without `_v2` suffix). Historical-context sections MAY mention v1 names with explicit historical framing.
   - `set_due_dates.py` is NOT invoked in the active workflow (D1).

2. **Markdownlint pass** (if the repo uses markdownlint; otherwise just visual inspection during review).

3. **Post-deploy smoke test** (operator-driven, in `quickstart.md`): verify the next cron tick produces a check-in message and the openclaw session log shows the v2 helpers being invoked. This is the real integration test — mocks aren't useful for an agent's prose contract.

**Rationale**: AGENTS.md is prose for an LLM to consume. The "test" is whether the LLM follows the new instructions correctly at cron time. Grep assertions catch obvious omissions (e.g., implementer forgot to add Step 0). Live cron output catches semantic issues (e.g., implementer wrote the new Step 4 in a confusing way).

**Rejected alternatives**:
- **Mocked LLM invocations**: not feasible without standing up a full openclaw test harness. Mocks would test the harness, not the prose.
- **Skip content assertions, rely entirely on the cron**: leaves room for the implementer to omit something subtle. Grep gates are cheap.

---

## D5 — Operator deploy procedure

**Decision**: Re-use the existing `cat | ssh` sync command from `docs/runbooks/habits-ops.md` § Update workspace files. No new deploy machinery.

**Rationale**:
- The deploy command is documented and battle-tested. It's been used for prior AGENTS.md updates.
- Introducing a deploy script (`scripts/openclaw/agents/deploy_habits_workspace.sh` or similar) would be scope creep. Defer until there's a real need.
- The operator runs the command interactively post-merge. The 60-second deploy doesn't merit automation today.

**Implementation note**: the deploy command syncs ALL workspace files (SOUL, USER, IDENTITY, TOOLS, AGENTS) at once, not just AGENTS.md. This is correct — if any sibling file has drifted, the sync brings it back to the repo state. Defensive.

**Rejected alternatives**:
- **Write a deploy script**: scope creep; out of spec.
- **Automate via a git post-merge hook**: changes the operator-driven model; out of scope for Phase 5.

---

## D6 — Action Logging section disposition

**Decision**: KEEP the existing "Action Logging" section in AGENTS.md but update its language to clarify that completion actions are now recorded via `record_completion.py` (which itself writes to the JSONL log + Vikunja comment + sets done=true). The agent's high-level action-log entry should reference the JSONL entry as the canonical record, not the comment.

**Rationale**:
- Action logging is the agent's internal observability — separate from the data layer.
- The cutover changes the data layer but not the observability layer. The action log still names what the agent did (e.g., "marked habit 14 complete based on Kent's WhatsApp reply").
- Updating the language is a 1-2 line edit, not a section rewrite.

**Rejected alternatives**:
- **Skip the Action Logging update**: leaves stale references to inline comment writes; minor doc inconsistency.
- **Rewrite the section to deeply describe JSONL**: scope creep; the JSONL schema is documented in `agent-state-log-schema.md`.

---

## Summary

Six tactical decisions for the AGENTS.md content. The bulk of the implementer's work is mechanical (insert new steps, rename helper invocations, add pointer notes), bounded by the grep assertions in D4. The operator-driven deploy + smoke test (D5 + quickstart.md) is the real integration test.

No `[NEEDS CLARIFICATION]` markers remain. Ready for Phase 1 design artifacts.
