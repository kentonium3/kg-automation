---
work_package_id: WP04
title: Inbox-quality issue writer
dependencies:
- WP01
requirement_refs:
- C-003
- FR-006
- FR-007
- NFR-004
planning_base_branch: main
merge_target_branch: main
branch_strategy: Lane-allocated worktree from main; merges into main
subtasks:
- T012
- T013
history:
- event: created
  at: '2026-05-12T20:55:30Z'
  by: 'spec-kitty.tasks (auto-drive via #185)'
authoritative_surface: scripts/inbox/file_inbox_quality_issue.py
execution_mode: code_change
owned_files:
- scripts/inbox/file_inbox_quality_issue.py
- tests/inbox/test_inbox_quality_issue_writer.py
tags: []
---

# WP04 — Inbox-quality issue writer

## Objective

`scripts/inbox/file_inbox_quality_issue.py` — title-prefix-deduped GitHub issue writer invoked by the agent at end-of-cron-turn when one or more notes have parse failures. Mirrors the credential-health-check `github_writer.py` pattern.

## Context

- **Spec** anchors: FR-006 (batched issue), FR-007 (title-prefix dedup).
- **Contracts** anchor: `contracts/inbox-quality-issue-writer.md`.
- **Plan** anchor: identity = `kg-felix-bot` via existing `gh` CLI auth on office2.
- **Prior art**: credential-health-check's `github_writer.py` (`scripts/security/credential_health_check/github_writer.py`) — same pattern. Borrow the dedup-via-fuzzy-search + post-filter design.

## Branch Strategy

- Planning/base branch: `main`
- Merge target branch: `main`

## Subtasks

### T012 — Implement `file_inbox_quality_issue.py`

**Purpose**: Title-prefix-deduped issue filing.

**Steps**:

1. Create `scripts/inbox/file_inbox_quality_issue.py`. CLI:
   - `--parse-failures` — JSON string OR `@<file>` to read from a file. Schema: `[{"path": ..., "reason": ...}, ...]`.
   - `--date` (optional, default UTC today as `YYYY-MM-DD`) — for deterministic test invocations.

2. Behavior:
   - Parse the input.
   - If list is empty: exit 0 without filing anything.
   - **Dedup check** via `gh issue list`:
     ```python
     subprocess.run(
         ["gh", "issue", "list",
          "--repo", "kentonium3/kg-automation",
          "--search", 'in:title "Inbox quality"',
          "--state", "open",
          "--json", "number,title",
          "--limit", "50"],
         capture_output=True, text=True, check=True, timeout=15,
     )
     ```
   - Parse JSON output. Post-filter for titles starting with `"Inbox quality:"` (gh's `in:title` is fuzzy).
   - If any match: print the existing issue number to stdout, exit 0. Do NOT update the existing issue's body.
   - If no match: construct title and body, file new issue, print new number to stdout, exit 0.

3. **Title format** (stable contract):
   ```
   Inbox quality: <N> notes with parse errors — <YYYY-MM-DD>
   ```

4. **Body template**:
   ```markdown
   The `felix-admin-capture` agent encountered <N> notes whose frontmatter could not be parsed on <YYYY-MM-DD>. Routing for these notes is halted until the frontmatter is fixed; each note has been tagged with a `> [!error] felix-capture:` callout marker referencing this issue.

   | Filename | Reason |
   |---|---|
   | `<basename>` | <reason> |
   | ... | ... |

   Per-run activity log: `/home/kgale/second-brain/agents/logs/inbox-processing-<YYYY-MM-DD>.md`

   ### What to do

   Open each note in Obsidian. The agent has injected a `> [!error] felix-capture:` callout at the top indicating the malformation. Common fixes:

   - **Leading whitespace before `---`**: delete blank lines / spaces / BOM before the opening `---`.
   - **UTF-8 BOM**: re-save the file in UTF-8 without BOM.
   - **Missing closing `---`**: add the closing fence.
   - **Invalid YAML inside frontmatter**: fix the YAML syntax.

   After fixing, the next cron tick will re-classify, auto-strip the marker, and route normally.

   *Filed by `felix-admin-capture` on office2 via `kg-felix-bot`.*
   ```

5. Issue filing:
   - Default labels: `area/content`
   - Default assignees: `kentonium3`
   - Filed against `kentonium3/kg-automation`

6. Make executable: `chmod +x`.

**Files**: `scripts/inbox/file_inbox_quality_issue.py` (create, ~180 lines, executable).

**Validation**: covered in T013.

---

### T013 — Tests for the writer

**Purpose**: Lock title/body templating and dedup behavior. All external surfaces stubbed.

**Steps**:

1. Create `tests/inbox/test_inbox_quality_issue_writer.py`.
2. Expose the core logic as Python functions (consider `dedup_check(parse_failures)` and `file_new_issue(parse_failures, date)`) so tests can call them directly, with subprocess as a thin shim. Alternative: test by mocking `subprocess.run` and invoking `main()`.
3. Cases:
   - `test_empty_parse_failures_exits_zero_without_filing` — empty list, no gh calls.
   - `test_dedup_finds_existing_issue` — stub `gh issue list` returning `[{"number": 999, "title": "Inbox quality: 3 notes with parse errors — 2026-05-12"}]` → helper prints `999`, does NOT call `gh issue create`.
   - `test_dedup_post_filters_fuzzy_match` — stub returning a fuzzy match like `{"number": 500, "title": "Some inbox quality concerns about ..."}` (not exact prefix) → helper treats as no-match, proceeds to file new issue.
   - `test_new_issue_filed_when_no_existing` — stub list empty, stub create returning URL → helper prints new issue number.
   - `test_title_format` — verify title is exactly `Inbox quality: 3 notes with parse errors — 2026-05-12` for 3 failures on 2026-05-12.
   - `test_body_includes_each_parse_failure_row` — body contains a row for each filename + reason.
   - `test_body_includes_activity_log_path`.
   - `test_gh_failure_returns_exit_1`.
   - `test_command_line_shape` — verify the constructed `gh issue create` argv has expected flags (`--label area/content`, `--assignee kentonium3`, `--title <expected>`, `--body <expected>`, `--repo kentonium3/kg-automation`).

**Files**: `tests/inbox/test_inbox_quality_issue_writer.py` (create, ~180 lines).

**Validation**: `pytest tests/inbox/test_inbox_quality_issue_writer.py -v` — green.

---

## Definition of Done

- All two subtasks complete.
- `pytest tests/inbox/ -v` total green.
- Script is `chmod +x` (mode `100755`).
- Commit prefix: `feat(WP04):` referencing #185.

## Risks

- **Title prefix is a stable contract**: any drift breaks dedup forever. Lock it via a module-level constant and test against that constant.
- **gh's fuzzy `in:title`**: post-filter is mandatory; tests must include a fuzzy-non-match case to lock the behavior.
- **Body length**: at 1000+ parse failures, body could exceed GitHub's 65K limit. Defer until v2 — current inbox scale is ~5 notes.

## Reviewer guidance

- Verify: title prefix constant is exposed at module top (e.g., `INBOX_QUALITY_TITLE_PREFIX = "Inbox quality:"`) and used in both filing and dedup.
- Verify: dedup uses `startswith()` post-filter against `gh`'s search results.
- Verify: empty parse_failures input produces zero gh calls (don't accidentally file an empty issue).
- Verify: `--date` argument is honored so tests can pin the date.

## Suggested implement command

```bash
spec-kitty agent action implement WP04 --agent <name>
```
