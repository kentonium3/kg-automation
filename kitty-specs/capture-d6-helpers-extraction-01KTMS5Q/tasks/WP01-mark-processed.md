---
work_package_id: WP01
title: mark_processed helper
dependencies: []
requirement_refs:
- FR-001
- FR-002
- FR-008
- FR-009
- FR-010
tracker_refs: []
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this mission were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks:
- T001
- T002
agent: claude
history: []
agent_profile: python-pedro
authoritative_surface: scripts/inbox/
execution_mode: code_change
mission_id: 01KTMS5QGXFJWQYVXB03SPYB48
mission_slug: capture-d6-helpers-extraction-01KTMS5Q
model: claude-sonnet-4-6
owned_files:
- scripts/inbox/mark_processed.py
- tests/inbox/test_mark_processed.py
role: implementer
tags: []
---

## ⚡ Do This First: Load Agent Profile

```
/ad-hoc-profile-load python-pedro
```

Python implementer posture: stdlib-only, test-first, locality of change.

## Objective

Implement `scripts/inbox/mark_processed.py` — an atomic frontmatter-mutation helper that sets `status: processed` + `processed_at: <ISO 8601 UTC>` on a note while preserving the file's location, other frontmatter fields, and body verbatim. Idempotent on already-processed notes.

CLI: `python3 -m scripts.inbox.mark_processed --path <abs-path-to-note>`

## Context

| Document | Why |
|---|---|
| [../spec.md](../spec.md) § FR-001, FR-002, FR-010 | Functional contract + idempotency + atomic write |
| [../plan.md](../plan.md) § IC-01 | Concern map for this WP |
| [../contracts/helper-cli.md](../contracts/helper-cli.md) § `mark_processed` | CLI surface details |
| `scripts/inbox/inject_parse_error_marker.py` | Atomic-write pattern precedent (read before writing the helper) |
| `scripts/inbox/handle_marker_cleanup.py` | Frontmatter parsing pattern precedent (stdlib regex-based) |
| `tests/inbox/test_atomic_write_perms.py` | Atomic-write test precedent |

## Subtask Guidance

### T001 — Tests + Implementation

**Step 1: Tests first** (`tests/inbox/test_mark_processed.py`):

Add test fixtures via `tmp_path`:

- `test_mark_processed_sets_status_and_timestamp`: note with `status: unprocessed` → after invocation, frontmatter has `status: processed` and `processed_at: <ISO 8601 UTC>`, body preserved verbatim, file is at the same path.
- `test_mark_processed_idempotent`: note with `status: processed` → invocation is a no-op (file MD5 unchanged), exit 0.
- `test_mark_processed_preserves_other_frontmatter`: note with extra frontmatter fields (`id`, `created`, `tags`, etc.) → all preserved after invocation.
- `test_mark_processed_preserves_body`: note with multi-paragraph body including markdown features (headings, code blocks, callouts) → body byte-identical after invocation.
- `test_mark_processed_missing_file_exits_1`: `--path /tmp/does-not-exist.md` → exit 1, structured stderr.
- `test_mark_processed_no_frontmatter_exits_1`: note file without `---\n...\n---` block → exit 1.
- `test_mark_processed_atomic_no_temp_leftover_on_success`: invocation succeeds → no `.tmp.<pid>` file lingers in the note's dir.
- `test_mark_processed_atomic_no_destination_corruption_on_failure`: mock `os.replace` to raise → original file unchanged + no temp file lingers.
- `test_mark_processed_refuses_private_path`: `--path .../04-Growth/_private/secret.md` → exit 3 (C-001 refusal).
- `test_mark_processed_processed_at_iso_8601_utc`: invocation → `processed_at` ends with `Z` and parses via `datetime.fromisoformat`.

**Step 2: Implementation** (`scripts/inbox/mark_processed.py`):

- Module docstring referencing FR-001 + FR-002 + the invocation form
- Stdlib imports only: `argparse`, `os`, `re`, `sys`, `datetime`, `pathlib`
- Function `read_frontmatter(text: str) -> tuple[dict, str]` — regex-based parser; returns (frontmatter dict, body string); raises ValueError if no frontmatter
- Function `write_frontmatter(fm: dict, body: str) -> str` — preserves key order; ISO 8601 string values quoted
- Function `mark_processed(path: Path) -> int` — orchestrator; returns exit code per the contract
- `main(argv=None)` → CLI entry, returns int; module bottom `if __name__ == "__main__": sys.exit(main())`
- Atomic write per [`scripts/inbox/inject_parse_error_marker.py`](../../../scripts/inbox/inject_parse_error_marker.py) — write-temp + fsync + `os.replace`
- Refusal check: `Path("04-Growth/_private")` substring in the input path → exit 3 BEFORE any read

### T002 — Coverage gate

```bash
pytest tests/inbox/test_mark_processed.py \
  --cov=scripts.inbox.mark_processed \
  --cov-branch \
  --cov-report=term-missing \
  --cov-fail-under=90
```

Must show ≥90% line AND ≥85% branch. Use `# pragma: no branch` ONLY for genuinely-unreachable defensive branches; document each pragma with a comment.

## Definition of Done

- [ ] `scripts/inbox/mark_processed.py` exists, stdlib only
- [ ] `tests/inbox/test_mark_processed.py` exists with all test cases above
- [ ] `python3 -m scripts.inbox.mark_processed --help` exits 0 from repo root
- [ ] Coverage gate passes
- [ ] No third-party imports (verified by `grep -E "^import (requests|httpx|pydantic|yaml|frontmatter)" scripts/inbox/mark_processed.py | wc -l` returns 0)
- [ ] Lane committed; WP moved to `for_review`

## Risks

- Frontmatter parsing edge cases (escaped quotes, multi-line values). Mitigation: tests cover edge cases; if a real-world note breaks the parser, that's a separate follow-on issue (NOT in this mission).
- `os.replace` semantics on macOS vs Linux. Mitigation: same precedent as existing helpers; tests cover both via `tmp_path`.
