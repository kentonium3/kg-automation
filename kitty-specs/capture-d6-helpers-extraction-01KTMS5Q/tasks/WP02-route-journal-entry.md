---
work_package_id: WP02
title: route_journal_entry helper
dependencies: []
requirement_refs:
- FR-003
- FR-010
- FR-011
tracker_refs: []
planning_base_branch: kitty/mission-capture-d6-helpers-extraction-01KTMS5Q
merge_target_branch: kitty/mission-capture-d6-helpers-extraction-01KTMS5Q
branch_strategy: Planning artifacts for this mission were generated on kitty/mission-capture-d6-helpers-extraction-01KTMS5Q. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into kitty/mission-capture-d6-helpers-extraction-01KTMS5Q unless the human explicitly redirects the landing branch.
subtasks:
- T003
- T004
agent: claude
history: []
agent_profile: python-pedro
authoritative_surface: scripts/inbox/
execution_mode: code_change
mission_id: 01KTMS5QGXFJWQYVXB03SPYB48
mission_slug: capture-d6-helpers-extraction-01KTMS5Q
model: claude-sonnet-4-6
owned_files:
- scripts/inbox/route_journal_entry.py
- tests/inbox/test_route_journal_entry.py
role: implementer
tags: []
---

## ⚡ Do This First: Load Agent Profile

```
/ad-hoc-profile-load python-pedro
```

## Objective

Implement `scripts/inbox/route_journal_entry.py` — append content to a dated `08-Journal/Journal YYYY-MM-DD HHmm.md` (create file with correct frontmatter if absent), under a level-2 timestamp heading. Path resolution via `scripts.vault.paths`.

CLI: `python3 -m scripts.inbox.route_journal_entry --content-file <abs-path> --datetime <ISO 8601>`

## Context

| Document | Why |
|---|---|
| [../spec.md](../spec.md) § FR-003, FR-010, FR-011 | Functional contract + atomic write + path resolution |
| [../contracts/helper-cli.md](../contracts/helper-cli.md) § `route_journal_entry` | CLI surface |
| `scripts/vault/paths.json` | Source for `paths.journal` (= `/home/kgale/second-brain/notes/08-Journal`) |
| `scripts/inbox/inject_parse_error_marker.py` | Atomic-write precedent |

## Subtask Guidance

### T003 — Tests + Implementation

**Tests** (`tests/inbox/test_route_journal_entry.py`):

- `test_creates_journal_file_when_absent` — first call creates `Journal YYYY-MM-DD HHmm.md` with correct frontmatter (`id`, `doc_type: journal`, `created`, `last_validated`)
- `test_appends_section_under_h2_timestamp_heading` — content appears under `## HH:mm — <first 60 chars trimmed>`
- `test_appends_to_existing_journal_file` — second call to the same minute appends another section without rewriting the file's frontmatter or earlier sections
- `test_datetime_drives_filename` — `--datetime "2026-06-08T07:32:00-04:00"` → file `Journal 2026-06-08 0732.md`
- `test_atomic_write_no_temp_leftover_on_success`
- `test_atomic_write_no_corruption_on_failure` (mock `os.replace` to raise)
- `test_invalid_datetime_exits_1`
- `test_missing_content_file_exits_1`
- `test_short_content_uses_only_timestamp_heading` — content <8 chars → heading is `## HH:mm` only
- `test_journal_path_via_vault_paths_module` — patches `scripts.vault.paths` to point at `tmp_path`; verifies the helper uses that path (not a hard-coded fallback)

**Implementation** (`scripts/inbox/route_journal_entry.py`):

- Imports: `argparse`, `json`, `os`, `sys`, `datetime`, `pathlib`, `scripts.vault.paths` (helper TBD interface; otherwise read `scripts/vault/paths.json` directly)
- Function `resolve_journal_dir() -> Path` — reads `paths.json`, returns `paths.journal` as `Path`
- Function `target_filename(dt: datetime) -> str` — formats `Journal YYYY-MM-DD HHmm.md`
- Function `make_heading(dt: datetime, content: str) -> str` — `## HH:mm` or `## HH:mm — <trimmed>`
- Function `ensure_journal_file(path: Path, dt: datetime) -> None` — creates with frontmatter if absent
- Function `append_section(path: Path, heading: str, content: str) -> None` — atomic append (read whole file, append, atomic-write)
- `main(argv=None) -> int` — orchestrator, exit code contract

### T004 — Coverage gate

```bash
pytest tests/inbox/test_route_journal_entry.py \
  --cov=scripts.inbox.route_journal_entry \
  --cov-branch --cov-fail-under=90
```

## Definition of Done

- [ ] `scripts/inbox/route_journal_entry.py` exists, stdlib + internal imports only
- [ ] `tests/inbox/test_route_journal_entry.py` exists with all cases above
- [ ] `--help` exits 0
- [ ] Coverage gate passes
- [ ] Lane committed; WP moved to `for_review`

## Risks

- `scripts.vault.paths` might be a module OR a raw `paths.json` read pattern. Inspect existing helpers (`scripts/inbox/prescan.py`) to use the same approach.
- Journal frontmatter shape — check an existing `08-Journal/Journal YYYY-MM-DD HHmm.md` for the canonical shape if a sample exists in the vault. Otherwise use the same shape as `~/second-brain/notes/08-Journal/`'s typical files.
