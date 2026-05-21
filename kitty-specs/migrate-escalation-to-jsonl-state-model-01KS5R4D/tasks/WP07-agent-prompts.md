---
work_package_id: WP07
title: Agent prompts (SKILL.md + AGENTS.md)
dependencies:
- WP03
- WP05
requirement_refs:
- C-002
- C-005
- FR-007
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
created_at: '2026-05-21T17:45:30+00:00'
subtasks:
- T021
- T022
- T023
agent: "claude:opus:python-implementer:implementer"
shell_pid: "19210"
history:
- at: '2026-05-21T17:45:30+00:00'
  actor: spec-kitty.tasks
  event: created
authoritative_surface: scripts/openclaw/
execution_mode: code_change
mission_id: 01KS5R4D79WQQWY2MCHZVCT85G
mission_slug: migrate-escalation-to-jsonl-state-model-01KS5R4D
owned_files:
- scripts/openclaw/skills/escalation/SKILL.md
- scripts/openclaw/agents/felix-admin-escalation/AGENTS.md
tags: []
---

# WP07 — Agent prompts (SKILL.md + AGENTS.md)

## Objective

Update the deployed OpenClaw `felix-admin-escalation` agent's standing orders to invoke the new helpers via CLI and stop parsing `[Felix-Escalation]` comments in-prompt. The skill becomes a thin wrapper: derive state via `derive_state` CLI, build WhatsApp message from JSONL records, write events via `record_completion` CLI. Implements FR-007. Preserves C-002 (policy unchanged) and C-005 (autonomy unchanged).

## Context

- **Mission spec**: FR-007 (skill/AGENTS updates), C-002 (policy unchanged), C-005 (Observed autonomy Level 2)
- **Plan**: Complexity tracking § 2 ("dense `[Felix-Escalation]` parsing logic" — audit it out)
- **Dependencies**:
  - **WP03**: `record_completion.py` CLI must be live (skill invokes it).
  - **WP05**: `reconcile_completions.py` CLI must be live (skill invokes it at tick start).
- **Existing files**:
  - `scripts/openclaw/skills/escalation/SKILL.md` — v1 source of truth, 240 lines, heavy comment-parsing logic.
  - `scripts/openclaw/agents/felix-admin-escalation/AGENTS.md` — agent's standing orders.
- **Habits Phase 5 precedent**: the cutover mission updated the habits SKILL.md from comment-parsing to helper-invocation. Read `scripts/openclaw/skills/habits/SKILL.md` for the pattern.
- **Branching**: planning_base=`main`, merge_target=`main`. Execution worktree per `lanes.json`.

## Subtasks

### T021 — Update `scripts/openclaw/skills/escalation/SKILL.md`

**Purpose**: Replace the level-determination algorithm (§2) and comment-format/response-parsing sections (§3, §5) with helper-invocation instructions.

**Steps**:

1. Read the current SKILL.md end-to-end to understand the full vocabulary.
2. Preserve UNCHANGED:
   - §1 Escalation Criteria (qualification rules — policy lives there)
   - §4 WhatsApp Message Format (message rendering rules — purely cosmetic, unchanged)
   - §7 Daily Deduplication (max one alert per day rule)
3. REPLACE §2 "Level determination algorithm" with:
   ```markdown
   ## 2. Level Determination via JSONL State

   The skill no longer parses `[Felix-Escalation]` comments in-prompt. For each
   candidate task, invoke the `derive_state` CLI helper to get current state:

       python3 -m scripts.escalation.derive_state \
         --task-id <id> --project-id <pid>

   Parse stdout JSON. The `next_eligible_level` field tells you which level (if
   any) to send this tick.

   Policy rules (encoded in derive_state):

   - `current_state="new"` → send Level 1 if task qualifies per §1.
   - `current_state="level_1_sent"` with `next_eligible_level=null` → skip (not stale yet).
   - `current_state="level_1_sent"` with `next_eligible_level=2` → send Level 2.
   - `current_state="level_2_sent"` → send Level 2 again (daily dedup at §7 applies).
   - `current_state="snoozed"` → skip.
   - `current_state="snoozed_expired"` → re-enter at Level 1.
   - `current_state="rescheduled"` → re-evaluate via §1 against the new due_date.
   - `current_state="done"` or `"dismissed"` → skip (terminal).

   On `EscalationStateError` (exit code 3): the helper has filed a P2-bug
   automatically. Skip this task; continue with others.
   ```
4. REPLACE §3 "Escalation Comment Format" — DO NOT delete entirely. Rewrite as:
   ```markdown
   ## 3. Escalation State Format

   **Canonical state**: per-project JSONL at
   `/data/services/openclaw/state/escalation/project-<id>-escalation-history.jsonl`.

   See data-model.md in mission #309 for the record schema. Do NOT parse the
   `[Felix-Escalation]` Vikunja comments to derive state. The v1 comment writes
   (preserved during the 3-day soak post-cutover) are a compatibility mirror,
   not authoritative.

   **Writes**: invoke the `record_completion` CLI to record any event:

       python3 -m scripts.escalation.record_completion \
         --task-id <id> --project-id <pid> --title "<task title>" \
         --date <YYYY-MM-DD> --state <event_type> --source <agent|kent_reply> \
         [--level N | --snooze-days N | --reschedule-to YYYY-MM-DD] \
         [--reason "..."] [--idempotent]

   The helper handles the v1 comment write + JSONL append atomically per
   research D6 (Vikunja side-effect first, JSONL second).
   ```
5. REPLACE §5 "Response Parsing" — preserve the regex table (Kent's reply patterns DON'T change) but replace the "Write `X | acknowledged` comment" instructions with the equivalent `record_completion` CLI invocation. The skill still parses Kent's WhatsApp reply; it just routes the resulting event through the helper instead of writing a comment directly.
6. ADD a new section at the top (after the frontmatter):
   ```markdown
   ## 0. State Source

   The canonical state for escalation is per-project JSONL state-log files,
   NOT Vikunja `[Felix-Escalation]` comments. The agent reads state via
   `scripts/escalation/derive_state.py` and writes events via
   `scripts/escalation/record_completion.py`. During the 3-day post-cutover
   soak (until Phase 6 is declared complete), record_completion writes BOTH
   the v1 `[Felix-Escalation]` comment AND a JSONL record for compatibility.
   After soak, a follow-on mission removes the v1 comment write.

   Migration reference: mission #309 (ADR-0002 Phase 6).
   ```
7. UPDATE the frontmatter `version: 2.0.0` (was `1.0.0`).
8. Run a self-audit: `grep -n "parse\|comment-parsing\|scan for prefix" scripts/openclaw/skills/escalation/SKILL.md` should only return matches inside §0 (the explanatory section) and §5 (parsing Kent's WhatsApp replies — not Vikunja comments).

**Files**:
- `scripts/openclaw/skills/escalation/SKILL.md` (modified — significant rewrite of §2, §3, §5; new §0; preserve §1, §4, §6, §7)

**Validation**:
- [ ] `grep -c "Felix-Escalation" SKILL.md` returns a count consistent with explanatory context only — no remaining "scan for prefix" / "comments per task" / "split on" parsing instructions.
- [ ] The new §0 explains the v1 parity period (soak).
- [ ] All four helper CLI invocations (derive_state, record_completion, reconcile_completions, hard_fail) are mentioned with correct flags.

---

### T022 — Update `scripts/openclaw/agents/felix-admin-escalation/AGENTS.md`

**Purpose**: Update the agent's standing orders to invoke the helpers at tick start (reconcile sweep) and remove any duplicated parsing logic.

**Steps**:

1. Read the current AGENTS.md.
2. Identify the "tick workflow" section. REPLACE the existing tick workflow with:
   ```markdown
   ## Tick workflow

   1. **Reconcile sweep** (FIRST — detects UI-marking-done and due-date edits since
      last tick):

          python3 -m scripts.escalation.reconcile_completions --all

      Capture stdout. Each `DRIFT` line means a synthetic record was emitted. Each
      `HARDFAIL` line means a P2-bug was filed (or deduped). Do not retry — these
      are operator-triageable.

   2. **Candidate enumeration**: per SKILL.md §1, walk Vikunja tasks that qualify
      for escalation today.

   3. **State derivation**: for each candidate, invoke:

          python3 -m scripts.escalation.derive_state \
            --task-id <id> --project-id <pid>

      Use the `next_eligible_level` to decide whether to alert this tick.

   4. **Compose WhatsApp message**: per SKILL.md §4. Apply daily dedup per §7.

   5. **Send**: ship the message via the existing whatsapp skill.

   6. **Record events**: for each task that received an alert, invoke:

          python3 -m scripts.escalation.record_completion \
            --task-id <id> --project-id <pid> --title "<title>" \
            --date <today-local> --state level_sent --level <N> --source agent

   7. **Wait for Kent's reply**: per SKILL.md §5. When Kent replies, parse the
      response and route each task's event through `record_completion` with the
      appropriate `--state` and `--source=kent_reply`.
   ```
3. REMOVE any leftover instructions to "parse `[Felix-Escalation]` comments" or "scan task comments for level history".
4. PRESERVE: agent identity (felix-bot), Tailscale connectivity reminders, autonomy level (Observed L2), and the skills list at the bottom.
5. ADD a note at the bottom referencing mission #309 + the post-soak follow-on.

**Files**:
- `scripts/openclaw/agents/felix-admin-escalation/AGENTS.md` (modified — tick workflow rewritten, parsing removed)

**Validation**:
- [ ] The tick workflow starts with `reconcile_completions`.
- [ ] All references to parsing comments removed (except where SKILL.md §5 is referenced for parsing Kent's WhatsApp text).
- [ ] Agent identity remains `felix-bot` for Vikunja writes.
- [ ] Skills list at the bottom unchanged.

---

### T023 — Audit both files + add v1→v2 transition note

**Purpose**: Final pass to catch residual comment-parsing language. Add a clear "what changed" note for future readers.

**Steps**:

1. Audit grep:
   ```bash
   grep -nE "(parse|scan).*comment|[Felix-Escalation].*split|comments per task|most recent comment" \
     scripts/openclaw/skills/escalation/SKILL.md \
     scripts/openclaw/agents/felix-admin-escalation/AGENTS.md
   ```
   Every match must be in an explanatory / "do NOT" / historical context. If any imperative parsing instruction remains, fix.
2. Add transition note to SKILL.md (immediately after frontmatter):
   ```markdown
   > **v1 → v2 transition note**: SKILL.md v1.0.0 (pre-#309) derived state by
   > scanning `[Felix-Escalation]` Vikunja comments in-prompt. v2.0.0 (#309)
   > derives state from per-project JSONL files via `scripts/escalation/`
   > helpers. The v1 comment writes continue during the 3-day soak post-cutover
   > for rollback safety; after soak, a follow-on mission removes them.
   ```
3. Add transition note to AGENTS.md (in the same spot if there's an analogous header location):
   ```markdown
   > **Tick workflow updated by #309**: pre-#309 ticks read state from
   > `[Felix-Escalation]` comments. Post-#309 ticks read state from JSONL
   > via `derive_state` and write via `record_completion`. See
   > `kitty-specs/migrate-escalation-to-jsonl-state-model-01KS5R4D/`.
   ```

**Files**:
- `scripts/openclaw/skills/escalation/SKILL.md` (transition note added)
- `scripts/openclaw/agents/felix-admin-escalation/AGENTS.md` (transition note added)

**Validation**:
- [ ] Audit grep returns nothing actionable.
- [ ] Both files have transition notes.
- [ ] `grep -c "scripts.escalation" SKILL.md AGENTS.md` returns positive counts in both.

---

## Branch Strategy

- Planning/base branch: `main`
- Merge target: `main`
- Execution worktree allocated per `lanes.json` after `finalize_tasks`.

## Test Strategy

No unit tests for prose docs. Validation is via grep audits + a reviewer reading both files end-to-end. The "smoke test" for these files is the cutover: WP09's runbook exercises them on office2.

## Definition of Done

- [ ] T021-T023 subtasks complete with all validations green.
- [ ] No residual parsing imperatives in either file.
- [ ] Both files reference the new helpers' CLI surfaces with correct flags.
- [ ] Transition notes present in both files.
- [ ] SKILL.md version bumped to 2.0.0.

## Risks

- **Stale parsing language**: easy to leave a sentence like "scan the most recent comment for `level-N`" in place. T023 is the explicit catch.
- **WhatsApp message rendering**: §4 of SKILL.md is policy-pure (just message formatting). Make sure it doesn't accidentally reference comment state — it should reference `derive_state` output instead.
- **C-002 violation risk**: if the rewrite accidentally changes a policy detail (e.g., the §1 criteria), C-002 fails. Reviewer must diff §1 + §4 + §7 and confirm zero policy changes.

## Reviewer Guidance

1. Diff the existing SKILL.md against the new version. Confirm §1, §4, §7 are byte-identical (modulo line-wrap cosmetic changes).
2. Verify §0 + §2 + §3 + §5 cleanly invoke the new helpers with correct flags.
3. Audit grep: no parsing imperatives remain.
4. Read AGENTS.md tick workflow end-to-end as if you were the agent. Confirm it can be followed mechanically.

## Implementation Command

```bash
spec-kitty agent action implement WP07 --mission migrate-escalation-to-jsonl-state-model-01KS5R4D --agent claude:opus:python-implementer:implementer
```

## Activity Log

- 2026-05-21T21:59:07Z – claude:opus:python-implementer:implementer – shell_pid=19210 – Started implementation via action command
- 2026-05-21T22:03:07Z – claude:opus:python-implementer:implementer – shell_pid=19210 – Ready for review — SKILL.md v2 + AGENTS.md tick workflow rewritten + audit grep clean
