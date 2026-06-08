---
work_package_id: WP05
title: handle_clarification_state helper
dependencies: []
requirement_refs:
- FR-006
- FR-010
- FR-015
tracker_refs: []
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this mission were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks:
- T009
- T010
agent: claude
history: []
agent_profile: python-pedro
authoritative_surface: scripts/inbox/
execution_mode: code_change
mission_id: 01KTMS5QGXFJWQYVXB03SPYB48
mission_slug: capture-d6-helpers-extraction-01KTMS5Q
model: claude-sonnet-4-6
owned_files:
- scripts/inbox/handle_clarification_state.py
- tests/inbox/test_handle_clarification_state.py
role: implementer
tags: []
---

## ⚡ Do This First: Load Agent Profile

```
/ad-hoc-profile-load python-pedro
```

## Objective

Implement `scripts/inbox/handle_clarification_state.py` — three subcommands (`add` / `sweep` / `match`) managing a JSON array state file at `~/second-brain/agents/state/pending-calendar-clarifications.json`. Safe on missing state file. 24h aging in `sweep`.

CLI patterns:
```
python3 -m scripts.inbox.handle_clarification_state add --note-filename <name> --partial-payload <json>
python3 -m scripts.inbox.handle_clarification_state sweep
python3 -m scripts.inbox.handle_clarification_state match --reply-content <text>
```

## Context

| Document | Why |
|---|---|
| [../spec.md](../spec.md) § FR-006, FR-015, FR-010 | Functional contract + sweep-on-missing-file safety + atomic write |
| [../data-model.md](../data-model.md) § PendingClarificationState | State file shape |
| [../contracts/helper-cli.md](../contracts/helper-cli.md) § `handle_clarification_state` | CLI surface for each subcommand |

## Subtask Guidance

### T009 — Tests + Implementation

**Tests** (`tests/inbox/test_handle_clarification_state.py`):

- `test_add_creates_state_file_when_absent` — state file + parent dir don't exist → invocation creates both with one PendingClarification entry
- `test_add_appends_to_existing_state_file` — state file has 1 entry → invocation appends a second
- `test_add_atomic_write` — temp file cleaned up on success; original preserved on `os.replace` failure
- `test_sweep_safe_on_missing_state_file` — file absent → exit 0, no error, stdout `removed=0`
- `test_sweep_safe_on_empty_array` — file contains `[]` → exit 0, `removed=0`
- `test_sweep_removes_entries_older_than_24h` — file has 2 entries, one with `created_at` 25h ago, one with 1h ago → after sweep, only the 1h-old entry remains; stdout `removed=1`
- `test_sweep_24h_boundary_inclusive` — entry exactly 24h old → REMOVED (use `>= 24h` semantic; document this)
- `test_match_returns_null_when_no_match` — state file has 1 entry whose `title` doesn't appear in `--reply-content` → stdout `null`
- `test_match_returns_entry_when_substring_appears` — entry title is `"Meet with Rob"` and `--reply-content` is `"3pm works for the rob meeting"` → stdout JSON of the matched entry (case-insensitive substring)
- `test_match_returns_most_recent_when_multiple_match` — two entries both match → returns the entry with the most recent `created_at`
- `test_match_does_not_delete_entry` — after `match` returns an entry, the state file is unchanged
- `test_match_safe_on_missing_state_file` — file absent → stdout `null`, exit 0
- `test_add_invalid_partial_payload_json_exits_1` — `--partial-payload "not json"` → exit 1

**Implementation** (`scripts/inbox/handle_clarification_state.py`):

- Imports: `argparse`, `json`, `os`, `sys`, `datetime`, `pathlib`
- Module-level constant: `STATE_PATH_DEFAULT = Path.home() / "second-brain" / "agents" / "state" / "pending-calendar-clarifications.json"`
- Argparse with subcommands: `add` / `sweep` / `match`
- Function `load_state(path) -> list` — returns `[]` if absent
- Function `save_state(path, entries: list) -> None` — atomic write
- Function `subcommand_add(path, note_filename, partial_payload_json) -> int`
- Function `subcommand_sweep(path, now_utc) -> int`
- Function `subcommand_match(path, reply_content, now_utc) -> int`
- `main(argv=None) -> int` — dispatches to subcommand

### T010 — Coverage gate

```bash
pytest tests/inbox/test_handle_clarification_state.py \
  --cov=scripts.inbox.handle_clarification_state \
  --cov-branch --cov-fail-under=90
```

## Definition of Done

- [ ] `scripts/inbox/handle_clarification_state.py` exists with 3 subcommands
- [ ] `tests/inbox/test_handle_clarification_state.py` exists with all cases above
- [ ] `--help` exits 0 for each subcommand AND for the top-level command
- [ ] Coverage gate passes
- [ ] Lane committed; WP moved to `for_review`

## Risks

- 24h boundary semantics — pick `>= 24h ago = removed`; document inline. Tests should cover the exact boundary.
- Case-insensitive substring matching in `match` — confirm the canonical heuristic against Kent's actual reply patterns if any data exists.
- Multi-process race on state file — single-writer assumption per [[feedback_signal_driven_doc_audit]]; if multiple sweeps overlap, last-writer-wins is acceptable.
