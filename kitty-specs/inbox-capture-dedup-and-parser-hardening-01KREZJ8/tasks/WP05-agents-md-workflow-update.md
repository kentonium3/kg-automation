---
work_package_id: WP05
title: AGENTS.md workflow update
dependencies:
- WP01
- WP02
- WP03
- WP04
requirement_refs:
- C-001
- C-007
- FR-001
- FR-003
- FR-004
- FR-006
- FR-008
- FR-010
- FR-011
- FR-012
- NFR-003
- NFR-004
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks:
- T014
- T015
- T016
- T017
agent: "claude"
shell_pid: "45413"
history:
- event: created
  at: '2026-05-12T20:55:30Z'
  by: 'spec-kitty.tasks (auto-drive via #185)'
authoritative_surface: scripts/openclaw/agents/felix-admin-capture/AGENTS.md
execution_mode: code_change
owned_files:
- scripts/openclaw/agents/felix-admin-capture/AGENTS.md
tags: []
---

# WP05 — AGENTS.md workflow update

## Objective

Update `scripts/openclaw/agents/felix-admin-capture/AGENTS.md` (the LLM agent's runtime prompt) to integrate all the new helpers and produce the correct routing/dedup/parse-failure behavior. This is the final integration WP — without it, the helpers from WP01-WP04 exist but the agent doesn't use them.

## Context

- **Spec** anchors: all 12 FRs land here in the agent's turn-by-turn behavior.
- **Plan** anchor: §"Project Structure" `scripts/openclaw/agents/felix-admin-capture/AGENTS.md`.
- **Helpers consumed**: `routing_log.py` (read indirectly via prescan), `append_routing_entry.py`, `inject_parse_error_marker.py`, `strip_parse_error_marker.py`, `file_inbox_quality_issue.py`.

## Branch Strategy

- Planning/base branch: `main`
- Merge target branch: `main`

## Subtasks

### T014 — Update §Step 1 to consume new prescan output fields

**Purpose**: Teach the agent to read `parse_failures`, `dedup_skipped`, and `marker_cleanup_needed` from prescan's JSON output.

**Steps**:

1. Open `scripts/openclaw/agents/felix-admin-capture/AGENTS.md`.
2. Find §"Step 1: Run the pre-scan helper" (around line 32).
3. Update the documented JSON shape to include the new fields:
   ```json
   {
     "unprocessed_count": <int>,
     "unprocessed_paths": [<absolute path>, ...],
     "archived_count": <int>,
     "archived": [{...}],
     "warnings": [...],
     "parse_failures": [{"path": <abs>, "reason": <str>}, ...],
     "dedup_skipped": [{"path": <abs>, "filename": <str>, "existing_issue": <int or null>}, ...],
     "marker_cleanup_needed": [<abs_path>, ...]
   }
   ```
4. Update the "Branch on the result" guidance:
   - **`unprocessed_count == 0` AND `parse_failures` is empty AND `marker_cleanup_needed` is empty**: reply `IDLE` (unchanged behavior — the existing IDLE path).
   - **`unprocessed_count == 0` AND `parse_failures` is non-empty**: skip routing but still go to Step 6 to file the batched "Inbox quality" issue + marker injection. Do NOT reply IDLE.
   - **`unprocessed_count == 0` AND `marker_cleanup_needed` is non-empty**: invoke `strip_parse_error_marker.py` for each affected path before replying IDLE. Activity-log the cleanup events.
   - **`unprocessed_count > 0`**: process each file in `unprocessed_paths` per Steps 2-5 (existing flow + new sub-steps from T015/T017).

**Files**: `scripts/openclaw/agents/felix-admin-capture/AGENTS.md` (modify).

---

### T015 — Update §Step 5 to invoke `append_routing_entry.py` + `inject_parse_error_marker.py`

**Purpose**: After routing each note, write to the routing log. At end-of-turn, inject markers for any halted notes.

**Steps**:

1. In AGENTS.md §"Step 5" (the post-route frontmatter-write step), insert a new sub-step BEFORE the `status: processed` write:

   ```markdown
   ### Step 5a: Record route in the routing log

   Immediately after the GitHub issue is created (and any Vikunja task is filed), invoke:

   ```bash
   python3 /home/claude/kg-automation/scripts/inbox/append_routing_entry.py \
     "<basename of note>" <issue_number> <task_id_or_dash> "<short excerpt of first ~120 chars of body>"
   ```

   If the helper exits non-zero, log the failure but continue to Step 5b. The routing log is the load-bearing dedup; if it fails, future runs may produce one duplicate (acceptable; alerted via the activity log).
   ```

2. After Step 5 (atomic frontmatter write), add a new Step 6 / final-turn-action block:

   ```markdown
   ### Step 6: End-of-turn parse-failure handling

   If prescan's `parse_failures` list was non-empty for this turn:

   1. File (or dedupe against) the batched "Inbox quality" issue:

      ```bash
      python3 /home/claude/kg-automation/scripts/inbox/file_inbox_quality_issue.py \
        --parse-failures "<JSON of parse_failures list>"
      ```

      Capture the printed issue number (existing or new) from stdout.

   2. For each entry in `parse_failures`:

      ```bash
      python3 /home/claude/kg-automation/scripts/inbox/inject_parse_error_marker.py \
        "<absolute path>" <issue_number>
      ```

      The marker write is idempotent — if a marker already exists, it's refreshed in place; no duplicates.

   3. Log each marker injection to the activity log.
   ```

**Files**: `scripts/openclaw/agents/felix-admin-capture/AGENTS.md` (modify).

---

### T016 — Add end-of-turn invocation when parse_failures non-empty

**Purpose**: Already covered in T015's Step 6 block. This subtask is the explicit verification + activity-log entry instruction.

**Steps**:

1. Confirm the Step 6 block from T015 includes the activity-log entries. Each parse failure should produce:
   - `parse-halt cycle=<cycle_id> filename=<...> reason=<...>` log line
   - `marker-inject cycle=<cycle_id> filename=<...> issue_number=<N>` log line
   - `inbox-quality-filed cycle=<cycle_id> issue_number=<N> count=<N>` log line (once per turn if filed)
2. Also add a regression note: "Even if `unprocessed_paths` is empty, this Step 6 may still run if `parse_failures` is non-empty (a note was previously well-formed and was just edited badly)."

**Files**: same as T015.

---

### T017 — Handle `marker_cleanup_needed`

**Purpose**: When prescan flags notes for marker cleanup (because they now parse cleanly but still have an old marker), the agent strips the marker as part of its Step 5 frontmatter write OR explicitly invokes strip.

**Steps**:

1. Per R-006 deferred decision D-001: prescan flags `marker_cleanup_needed`; the agent invokes the strip helper. Add to AGENTS.md §Step 5:

   ```markdown
   ### Step 5b: Strip stale parse-error markers (if any)

   If the file appears in prescan's `marker_cleanup_needed` list (i.e., it parses cleanly now but still has an old `> [!error] felix-capture:` marker from a previous turn), invoke:

   ```bash
   python3 /home/claude/kg-automation/scripts/inbox/strip_parse_error_marker.py "<absolute path>"
   ```

   Then proceed with the normal Step 5 frontmatter write (status: processed). The strip and the write are separate operations; if strip fails, log it and continue with the write — the worst case is a stale marker sitting at the top of a routed note, which is cosmetic, not correctness-breaking.
   ```

2. Log `marker-cleanup cycle=<cycle_id> filename=<...>` to the activity log.

**Files**: same.

---

## Definition of Done

- All four subtasks complete.
- AGENTS.md describes the full new workflow end-to-end: prescan output schema → branch on outcome → route + routing-log + atomic mark → end-of-turn parse-failure handling.
- The diff is reviewable: every helper script from WP01-WP04 has a documented invocation in AGENTS.md.
- A redeploy of the agent workspace (`bash scripts/office2/deploy/felix-admin-capture.sh`) leaves the deployed `/data/services/openclaw/inbox-agent/AGENTS.md` matching the in-repo source.
- Commit prefix: `feat(WP05):` referencing #185.

## Risks

- **Prompt clarity**: AGENTS.md is read by an LLM at runtime. Ambiguous instructions get interpreted differently each turn. Each step should be concrete with explicit bash commands and clear branching language ("if X, do Y; if not X, do Z").
- **Step ordering**: the agent must invoke routing-log append BEFORE the atomic `status: processed` write — if the order is reversed and the script crashes between them, the next tick would treat the note as unprocessed (frontmatter check fails because mark didn't land) but the routing log already has the entry, so it skips. Net effect: no duplicate. Order is safe; document it.
- **Helper-script paths**: all helpers reference `/home/claude/kg-automation/scripts/inbox/...` absolutely. Verify those paths are correct after deploy.

## Reviewer guidance

- Verify: every new bash invocation in AGENTS.md uses an absolute path (`/home/claude/kg-automation/scripts/inbox/...`).
- Verify: the agent is told to capture stdout from `file_inbox_quality_issue.py` (the issue number) and pass it to `inject_parse_error_marker.py` calls.
- Verify: the IDLE-but-with-marker-cleanup path is documented (a turn where there's nothing to route but a previously-malformed note now needs its marker stripped).
- Verify: activity-log entry formats are concrete.

## Suggested implement command

```bash
spec-kitty agent action implement WP05 --agent <name>
```

## Activity Log

- 2026-05-13T02:12:36Z – claude – shell_pid=45413 – Started implementation via action command
- 2026-05-13T02:16:53Z – claude – shell_pid=45413 – Ready for review: AGENTS.md + AGENTS.md.tmpl updated for new prescan fields, 5-way Step 1 branch, Step 5a/5b/5c restructure, new Step 6 parse-failure handling, 7 new action-log types.
