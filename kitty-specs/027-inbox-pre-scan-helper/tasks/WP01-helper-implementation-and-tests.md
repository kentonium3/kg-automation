---
work_package_id: WP01
title: Helper Implementation + Unit Tests
dependencies: []
requirement_refs:
- C-001
- C-002
- C-003
- C-004
- FR-001
- FR-002
- FR-003
- FR-004
- FR-005
- FR-006
- FR-007
- FR-008
- FR-013
- NFR-001
- NFR-002
- NFR-004
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
base_branch: kitty/mission-027-inbox-pre-scan-helper
base_commit: 5a37041139b391e371347fb2fbb373422072569e
created_at: '2026-04-11T18:25:51.214647+00:00'
subtasks:
- T001
- T002
- T003
- T004
- T005
- T006
- T007
shell_pid: "49934"
agent: "claude:opus-4-6:python-implementer:implementer"
history:
- date: '2026-04-11'
  event: created
authoritative_surface: scripts/inbox/
execution_mode: code_change
mission_slug: 027-inbox-pre-scan-helper
owned_files:
- scripts/inbox/**
- tests/scripts/inbox/**
tags: []
---

# WP01: Helper Implementation + Unit Tests

## Objective

Implement the pre-scan helper (`scripts/inbox/prescan.py`) and its pytest unit test suite. The helper is pure Python logic with no office2 contact — it resolves paths from the vault registry, classifies files by frontmatter + mtime, moves stale processed files, and emits a JSON result. Tests cover every classification rule and every edge case.

This WP is the foundation of the mission. Everything downstream (WP02 agent contract, WP03 deploy wrapper, WP05 live deploy) references the helper that this WP produces.

## Context

Read these first:
- `kitty-specs/027-inbox-pre-scan-helper/spec.md` — full spec (FR-001 through FR-008, NFR-001 through NFR-004, C-001 through C-004)
- `kitty-specs/027-inbox-pre-scan-helper/plan.md` — Technical Context + Helper CLI contract sections
- `kitty-specs/027-inbox-pre-scan-helper/data-model.md` — InboxFile, PrescanResult, LogEntry definitions and classification rules
- `scripts/vault/paths.json` — the vault path registry delivered by mission 026 (the source of truth for `inbox` and `inbox_processed`)
- `scripts/vault/` — check for an existing Python resolver module; if present, prefer importing it over duplicating the read-paths.json logic

Registry contract (what the helper consumes):
```json
{
  "version": 1,
  "paths": {
    "inbox": "/home/kgale/second-brain/notes/01-Inbox",
    "inbox_processed": "/home/kgale/second-brain/notes/02-Inbox-Processed",
    ...
  }
}
```

The helper needs exactly two entries: `inbox` and `inbox_processed`. No other paths.

## Branch Strategy

- **Planning base**: main
- **Final merge target**: main
- **Execution worktree**: assigned by `spec-kitty agent action implement WP01 --agent <name>` at implementation time. Each lane gets its own worktree from `lanes.json` after `finalize-tasks` runs.

Use `spec-kitty next --agent <your-name> --mission 027-inbox-pre-scan-helper` to get the exact implementation command and lane assignment. Do not hand-pick a branch.

## Subtasks

### T001 — Create `scripts/inbox/prescan.py` skeleton

**Purpose**: Establish the file, CLI entry point, argparse, module docstring, and imports. No business logic yet.

**Steps**:
1. Create `scripts/inbox/prescan.py` with:
   - Shebang: `#!/usr/bin/env python3`
   - Module docstring explaining the contract (one paragraph): what the script does, what it reads, what it writes, its exit codes, its `--self-check` mode
   - Imports: `argparse`, `json`, `os`, `sys`, `shutil`, `datetime` (timezone-aware), `pathlib.Path`, `yaml` (PyYAML)
   - `main()` function with argparse setup for `--self-check` flag
   - `if __name__ == "__main__":` guard calling `sys.exit(main())`
2. Create `scripts/inbox/README.md` briefly documenting: purpose, invocation, exit codes, contract, troubleshooting tips

**Files**:
- `scripts/inbox/prescan.py` (new, ~50 lines at this stage)
- `scripts/inbox/README.md` (new, ~40 lines)

**Validation**:
- [ ] `python3 scripts/inbox/prescan.py --help` prints a sensible help message
- [ ] `python3 scripts/inbox/prescan.py --self-check` does not crash (may fail with "not implemented" — that's fine at this stage)

### T002 — Implement vault path registry resolver

**Purpose**: Read `scripts/vault/paths.json` and return absolute paths for `inbox` and `inbox_processed`. Fail loud on any error.

**Steps**:
1. Define a `resolve_registry()` function that:
   - Looks for `paths.json` at a default location. **Critical**: the helper must work both (a) in the repo during testing, and (b) on office2 at `/home/claude/kg-automation/scripts/vault/paths.json`. Strategy: compute the default as `Path(__file__).parent.parent / "vault" / "paths.json"`, so it resolves relative to the helper's own location. This works in both environments because the deploy wrapper preserves the repo layout under `/home/claude/kg-automation/`.
   - Allows override via `PRESCAN_REGISTRY_PATH` environment variable (for test isolation)
   - Reads the JSON, extracts `paths.inbox` and `paths.inbox_processed`
   - Returns a `(inbox_path, inbox_processed_path)` tuple as `Path` objects
2. Error modes (all → raise a domain exception with a clear message):
   - Registry file missing
   - Registry unreadable (permissions)
   - JSON malformed
   - `paths.inbox` key missing
   - `paths.inbox_processed` key missing
   - Either resolved path does not exist on the filesystem
   - Either resolved path is not a directory
3. Define a dedicated exception class (e.g., `PrescanError`) so the main function can catch it and emit a clean stderr message + exit 1.

**Files**:
- `scripts/inbox/prescan.py` (extend, ~40 more lines)

**Validation**:
- [ ] Unit test (part of T007) asserts each error mode raises `PrescanError` with a useful message
- [ ] Unit test asserts happy path returns the expected Path objects

### T003 — Implement InboxFile classification

**Purpose**: Given a directory, return a list of classified files per `data-model.md` rules.

**Steps**:
1. Define `classify_file(path: Path, now_utc: datetime) -> InboxFile` function:
   - Read the file's mtime via `os.path.getmtime(path)`, convert to UTC-aware datetime
   - Open the file, extract the frontmatter block (between the first two `---` lines)
   - Parse the frontmatter with `yaml.safe_load` inside a try/except that catches `yaml.YAMLError` and returns "malformed" marker
   - Extract the `status` field (may be missing)
   - Compute the classification per the rules in `data-model.md`:
     - No frontmatter / no status field / malformed YAML → `unknown-treated-as-unprocessed`
     - `status == "unprocessed"` → `unprocessed`
     - `status == "processed"` AND `age_days > 7` → `processed-stale`
     - `status == "processed"` AND `age_days <= 7` → `processed-recent`
     - Any other `status` value → `unknown-treated-as-unprocessed` (safety default)
   - The 7-day boundary is exclusive: a file exactly 7.0 days old is `processed-recent`, not `processed-stale`
2. Define `InboxFile` as a `@dataclass` with fields: `path: Path`, `mtime_utc: datetime`, `status_raw: str | None`, `classification: str`, `warning: str | None`
3. Define `scan_directory(inbox_dir: Path, now_utc: datetime) -> list[InboxFile]` that:
   - Lists `.md` files in `inbox_dir` (non-recursive by default; see defense-in-depth note below)
   - **Defense-in-depth for C-001**: if any `.md` file's path contains `/_private/` or resolves to a symlink target under `_private/`, skip it with a warning. The inbox directory should never contain such files, but this check is belt-and-suspenders.
   - Returns the list of `InboxFile`s, sorted deterministically by filename

**Files**:
- `scripts/inbox/prescan.py` (extend, ~80 more lines)

**Validation**:
- [ ] Unit tests (T007) cover every classification rule against fixture files
- [ ] Unit test asserts sorting is deterministic
- [ ] Unit test with a synthetic `_private/` subdirectory confirms the helper skips it

### T004 — Implement stale-processed archive move

**Purpose**: Move `processed-stale` files from `{{VAULT_INBOX}}` to `{{VAULT_INBOX_PROCESSED}}`.

**Steps**:
1. Define `archive_stale(stale_files: list[InboxFile], inbox_processed_dir: Path) -> list[ArchiveResult]` function:
   - For each stale file, compute `dst = inbox_processed_dir / file.path.name`
   - If `dst` already exists, log a warning, DO NOT overwrite, skip the move, return a warning entry in the ArchiveResult list
   - Use `shutil.move(str(file.path), str(dst))` to perform the move (preserves mtime on same-filesystem moves, which is the common case here)
   - If the move raises `PermissionError` or `OSError`, catch it, log a warning, skip, continue to the next file
   - Return a list of `ArchiveResult` dataclasses (fields: `src`, `dst`, `age_days`, `success: bool`, `warning: str | None`)
2. Idempotence: re-running on an inbox where the stale files have already been moved is a no-op (the files no longer exist in the source list because the classification pass runs first each invocation)

**Files**:
- `scripts/inbox/prescan.py` (extend, ~60 more lines)

**Validation**:
- [ ] Unit test moves a fixture stale file and confirms it lands in the destination
- [ ] Unit test with a pre-existing destination file confirms skip + warning
- [ ] Unit test with a read-only destination directory confirms skip + warning + non-fatal behavior
- [ ] Unit test confirms unprocessed files are NEVER moved regardless of age

### T005 — Implement output layer

**Purpose**: Emit the JSON `PrescanResult` to stdout, human-readable logs to stderr, append-only daily log to the agent logs directory. Also implement `--self-check` mode.

**Steps**:
1. Define `PrescanResult` dataclass matching the schema in `data-model.md` (run_id, started_at_utc, finished_at_utc, inbox_path, inbox_processed_path, unprocessed_count, unprocessed_paths, archived_count, archived, warnings)
2. Implement `run_id` generation: ISO timestamp + 6 random hex chars, e.g., `2026-04-11T12:00:00Z-a1b2c3`
3. Implement stdout JSON emission: `json.dumps(result, indent=None)` followed by a newline. Single-line JSON is preferred for clean agent parsing.
4. Implement stderr logging: one `print(..., file=sys.stderr)` per significant step ("scanning inbox", "classified N files", "archiving M stale files", "writing daily log", "done"). Timestamps optional but recommended.
5. Implement daily log append: file at `/home/claude/second-brain/agents/logs/inbox-prescan-YYYY-MM-DD.md` (use UTC date). **Fallback**: if that directory doesn't exist (e.g., running in unit tests or local dev), log to `$TMPDIR/inbox-prescan-YYYY-MM-DD.md` instead and mention the fallback in a stderr warning. Never fail the run because the log directory is missing. Use a `PRESCAN_LOG_DIR` env var for test isolation.
6. Log format: append a markdown section per `data-model.md` LogEntry example (run header, counts, duration, archived list, unprocessed list)
7. Implement `--self-check` mode:
   - Call `resolve_registry()` to verify both paths
   - Confirm both directories exist
   - Print `{"self_check": "ok", "inbox": "...", "inbox_processed": "..."}` to stdout
   - Exit 0
   - Any error → exit 1 with clear stderr
8. Wire the main flow end-to-end: parse args → if `--self-check`, run self-check and exit → else resolve registry → scan inbox → archive stale → build result → emit outputs → exit 0

**Files**:
- `scripts/inbox/prescan.py` (extend, ~120 more lines; final total ~350 lines)

**Validation**:
- [ ] Unit test for `--self-check` happy path and failure paths
- [ ] Unit test asserts stdout is valid JSON matching the schema
- [ ] Unit test asserts daily log file is appended (uses `PRESCAN_LOG_DIR` override to point at tmpdir)
- [ ] Unit test asserts a second invocation on the same state produces identical JSON output (idempotence)

### T006 — Create test fixtures

**Purpose**: Seven markdown fixture files covering all classification cases.

**Steps**:
1. Create `tests/scripts/inbox/fixtures/` directory
2. Create the following fixture files (each ~15–30 lines of content, realistic frontmatter + body):
   - `processed-recent.md`: `status: processed`, fresh mtime (test will touch it)
   - `processed-stale.md`: `status: processed`, stale mtime (test will touch it)
   - `unprocessed.md`: `status: unprocessed`, any mtime
   - `no-frontmatter.md`: no `---` block at all
   - `no-status.md`: frontmatter present but no `status` field
   - `malformed-yaml.md`: frontmatter block with intentionally broken YAML (e.g., `date: [unclosed` or invalid tab indentation)
   - `unknown-status.md`: frontmatter with `status: pending` (not one of the known values)
3. Tests will copy these to a tmpdir and set mtimes explicitly for each test case. Fixtures themselves don't need specific mtimes.

**Files**:
- `tests/scripts/inbox/fixtures/processed-recent.md` (new)
- `tests/scripts/inbox/fixtures/processed-stale.md` (new)
- `tests/scripts/inbox/fixtures/unprocessed.md` (new)
- `tests/scripts/inbox/fixtures/no-frontmatter.md` (new)
- `tests/scripts/inbox/fixtures/no-status.md` (new)
- `tests/scripts/inbox/fixtures/malformed-yaml.md` (new)
- `tests/scripts/inbox/fixtures/unknown-status.md` (new)

**Validation**:
- [ ] All 7 files exist
- [ ] `malformed-yaml.md` causes `yaml.safe_load` to raise (manually verified once)

### T007 — Write pytest unit tests

**Purpose**: Comprehensive unit test coverage for the helper.

**Steps**:
1. Create `tests/scripts/inbox/test_prescan.py`
2. Use pytest `tmp_path` fixture to create a synthetic inbox + inbox_processed pair, and a synthetic `paths.json` for each test. Set `PRESCAN_REGISTRY_PATH` and `PRESCAN_LOG_DIR` via `monkeypatch`.
3. Test cases (at minimum):
   - **Registry resolution**:
     - `test_registry_missing_raises_prescan_error`
     - `test_registry_malformed_json_raises_prescan_error`
     - `test_registry_missing_inbox_key_raises_prescan_error`
     - `test_registry_missing_inbox_processed_key_raises_prescan_error`
     - `test_registry_happy_path_returns_paths`
   - **Classification**:
     - `test_classify_unprocessed` (status: unprocessed)
     - `test_classify_processed_recent` (status: processed, mtime 3 days ago)
     - `test_classify_processed_stale` (status: processed, mtime 8 days ago)
     - `test_classify_processed_at_boundary_exactly_7_days` (must be processed-recent, not processed-stale)
     - `test_classify_processed_at_boundary_just_over_7_days` (must be processed-stale)
     - `test_classify_no_frontmatter_treated_as_unprocessed`
     - `test_classify_no_status_treated_as_unprocessed`
     - `test_classify_malformed_yaml_treated_as_unprocessed`
     - `test_classify_unknown_status_treated_as_unprocessed`
   - **Archive**:
     - `test_archive_moves_stale_file_to_processed_dir`
     - `test_archive_skips_when_destination_exists` (with warning)
     - `test_archive_never_moves_unprocessed_file_regardless_of_age`
     - `test_archive_never_moves_processed_recent_file`
   - **Output**:
     - `test_stdout_json_schema_matches_expected_shape`
     - `test_daily_log_is_appended_not_overwritten`
     - `test_idempotence_two_runs_produce_identical_stdout` (given no state change between runs)
   - **Self-check**:
     - `test_self_check_happy_path_exits_zero_with_json`
     - `test_self_check_missing_directory_exits_one`
   - **Privacy boundary defense-in-depth**:
     - `test_private_subdirectory_is_never_walked` (construct inbox with a `_private/` subdir containing a file; assert the helper does not read or classify it)
   - **Empty inbox**:
     - `test_empty_inbox_returns_zero_counts_and_exits_zero`
4. Total test count: ~25–30 focused tests

**Files**:
- `tests/scripts/inbox/test_prescan.py` (new, ~400 lines)
- `tests/scripts/inbox/__init__.py` (new, empty)

**Validation**:
- [ ] `pytest tests/scripts/inbox/ -v` passes all tests
- [ ] Running pytest with `-x` (fail fast) catches any issue on the first failing test
- [ ] No network access, no office2 contact, no external dependencies beyond PyYAML

## Definition of Done

- [ ] `scripts/inbox/prescan.py` exists and is executable (`chmod +x` if needed)
- [ ] `scripts/inbox/README.md` exists
- [ ] All 7 fixture files exist under `tests/scripts/inbox/fixtures/`
- [ ] `tests/scripts/inbox/test_prescan.py` exists and all tests pass
- [ ] `python3 scripts/inbox/prescan.py --self-check` runs cleanly against a valid synthetic registry
- [ ] `python3 scripts/inbox/prescan.py` (without flags) runs cleanly against a valid synthetic registry with a synthetic inbox
- [ ] All FRs listed in `requirement_refs` have corresponding test cases
- [ ] No hardcoded vault paths anywhere in the code — all paths flow through the registry
- [ ] Code is self-contained — it does not import from `scripts/vault/` other than reading `paths.json` directly
- [ ] PyYAML is the only non-stdlib dependency
- [ ] Commit message follows conventional commits: `feat(WP01): inbox pre-scan helper + unit tests`

## Risks

- **Timezone drift**: mtime is typically returned as a local-timezone-naive float. Always convert to UTC-aware datetime before computing age. Use `datetime.fromtimestamp(mtime, tz=timezone.utc)`.
- **PyYAML version**: office2 has 6.0.1. Use `yaml.safe_load` exclusively, never `yaml.load` without a Loader.
- **Obsidian template placeholders**: files may contain `<% tp.file.cursor() %>` or similar in the body. This is fine — the helper only parses frontmatter, not body.
- **File locks during agent writes**: if the agent is mid-write on a file when the helper reads it, the frontmatter may be partial. The helper's malformed-yaml fallback (treat as unprocessed) handles this safely. No additional locking needed.
- **Log file path on dev machines**: the daily log defaults to `/home/claude/second-brain/agents/logs/...` which won't exist on Mac. The `PRESCAN_LOG_DIR` override + fallback-to-tmpdir logic prevents this from breaking local development and tests.

## Reviewer Guidance

- Verify test coverage: does every FR (FR-001 through FR-008) have at least one test case?
- Verify classification rules: does the 7-day boundary test use `age == 7.0` and assert `processed-recent`? (Common bug: off-by-one on boundary.)
- Verify `_private/` defense-in-depth test: is there a fixture subdirectory named `_private/` in the synthetic inbox and an assertion that its content is NOT in the result?
- Verify registry resolution via `PRESCAN_REGISTRY_PATH` env var: does the test use `monkeypatch.setenv` and not modify the real `scripts/vault/paths.json`?
- Verify the helper does not import anything from `openclaw` or `anthropic` — it should have zero LLM dependencies (NFR-002).
- Verify the helper's total runtime on a fixture inbox of 50 files is under 1 second (NFR-001). If tests are slow (>5s total), the helper may have a performance bug.
- Verify `--self-check` exits cleanly with a stable JSON shape.

## Implementation command

```bash
spec-kitty agent action implement WP01 --mission 027-inbox-pre-scan-helper --agent <tool>:<model>:<profile>:<role>
```

## Activity Log

- 2026-04-11T18:25:51Z – claude:opus-4-6:python-implementer:implementer – shell_pid=49934 – Assigned agent via action command
