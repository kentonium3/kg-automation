---
work_package_id: WP01
title: 'Foundation: routing-log module + fixture corpus'
dependencies: []
requirement_refs:
- FR-001
- FR-002
planning_base_branch: main
merge_target_branch: main
branch_strategy: Lane-allocated worktree from main; merges into main
subtasks:
- T001
- T002
- T003
history:
- event: created
  at: '2026-05-12T20:55:30Z'
  by: 'spec-kitty.tasks (auto-drive via #185)'
authoritative_surface: scripts/inbox/routing_log.py
execution_mode: code_change
owned_files:
- scripts/inbox/routing_log.py
- tests/inbox/conftest.py
- tests/inbox/test_routing_log.py
- tests/inbox/fixtures/**
tags: []
---

# WP01 — Foundation: routing-log module + fixture corpus

## Objective

Build `scripts/inbox/routing_log.py` (the load-bearing dedup substrate per #185) and lay down the test fixture corpus that downstream WPs reuse. No application-level integration in this WP — pure module + tests.

## Context

- **Spec** anchors: FR-001 (routing log location + format), FR-002 (entry schema).
- **Contracts** anchor: `contracts/routing-log.md` is the authoritative spec.
- **Data-model** anchor: §RoutingLogEntry.
- **Plan** anchor: project structure §`scripts/inbox/` neighborhood + §`tests/inbox/`.

## Branch Strategy

- Planning/base branch: `main`
- Merge target branch: `main`
- Lane-allocated worktree from main; merges into main.

## Subtasks

### T001 — Create test fixture corpus + conftest

**Purpose**: A standard set of inbox-note fixtures the rest of the mission tests against. Single source-of-truth keeps tests focused and consistent.

**Steps**:

1. Create `tests/inbox/conftest.py` with `sys.path` bootstrap so test files can `from routing_log import ...` directly:
   ```python
   from __future__ import annotations
   import sys
   from pathlib import Path

   REPO_ROOT = Path(__file__).resolve().parent.parent.parent
   SCRIPTS_INBOX = REPO_ROOT / "scripts" / "inbox"
   if str(SCRIPTS_INBOX) not in sys.path:
       sys.path.insert(0, str(SCRIPTS_INBOX))

   FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
   ```
2. Create `tests/inbox/fixtures/` directory.
3. Inside `tests/inbox/fixtures/`, add the following inbox-note fixture files (each a tiny `.md` file):

   - `inbox-well-formed.md` — happy path: opens with `---`, valid YAML with `status: unprocessed`, body text.
   - `inbox-leading-blank-lines.md` — mission-027 case: ONE blank line then `---` then valid YAML then `status: unprocessed`. (Used for regression — must NOT be classified parse_failure.)
   - `inbox-leading-newline-before-fence.md` — bug-trigger case: a literal `\n` THEN `---` with no intermediate content. Distinguished from above by being multi-character whitespace before `---`. (Actually, the existing leading-blank-line strip handles this too — this fixture's purpose is to confirm the regression and reinforce that this case is intentionally classified `unprocessed`, not `parse_failure`. The new `parse_failure` classification is for the cases below.)
   - `inbox-utf8-bom.md` — file starts with the BOM bytes `\xEF\xBB\xBF` then `---` then valid YAML.
   - `inbox-missing-close-fence.md` — opens with `---`, has valid YAML on next lines, but NO closing `---`. Body follows.
   - `inbox-invalid-yaml.md` — opens with `---`, has malformed YAML (e.g., unmatched quote in a value), closes with `---`.
   - `inbox-already-processed.md` — opens with `---`, valid YAML with `status: processed`, body.
   - `inbox-no-frontmatter.md` — no `---` at all; just plain text. (Existing classification: `unprocessed` — pre-mission behavior preserved.)

4. The fixture files are committed to the repo (in `tests/inbox/fixtures/`).

**Files**:

- `tests/inbox/conftest.py` (create)
- `tests/inbox/fixtures/inbox-well-formed.md` (create)
- `tests/inbox/fixtures/inbox-leading-blank-lines.md` (create)
- `tests/inbox/fixtures/inbox-leading-newline-before-fence.md` (create)
- `tests/inbox/fixtures/inbox-utf8-bom.md` (create — use `printf '\xEF\xBB\xBF---\n...'` or Python `bytes` write to get the BOM exact)
- `tests/inbox/fixtures/inbox-missing-close-fence.md` (create)
- `tests/inbox/fixtures/inbox-invalid-yaml.md` (create)
- `tests/inbox/fixtures/inbox-already-processed.md` (create)
- `tests/inbox/fixtures/inbox-no-frontmatter.md` (create)

**Validation**:

- `ls tests/inbox/fixtures/ | wc -l` returns 8 (the 8 .md fixtures).
- `python3 -c "import sys; sys.path.insert(0, 'tests/inbox'); from conftest import FIXTURES_DIR; print(FIXTURES_DIR.exists())"` returns True.
- `xxd tests/inbox/fixtures/inbox-utf8-bom.md | head -1` shows `efbbbf` in the first 3 bytes.

---

### T002 — Implement `scripts/inbox/routing_log.py`

**Purpose**: The Python module exposed to the rest of the codebase + helper scripts. Authoritative spec: `contracts/routing-log.md`.

**Steps**:

1. Create `scripts/inbox/routing_log.py` with these classes:

   ```python
   """Routing log helper module for felix-admin-capture inbox dedup.

   See kitty-specs/inbox-capture-dedup-and-parser-hardening-01KREZJ8/contracts/routing-log.md
   for the authoritative contract.
   """
   from __future__ import annotations

   import json
   import sys
   from dataclasses import dataclass, asdict
   from datetime import datetime, timezone
   from pathlib import Path
   from typing import Iterable, Optional


   DEFAULT_ROUTING_LOG_PATH = Path.home() / "second-brain" / "agents" / "state" / "inbox-routing.jsonl"


   @dataclass(frozen=True)
   class RoutingEntry:
       filename: str
       issue_number: int
       vikunja_task_id: Optional[int]
       routed_at: str  # ISO-8601 UTC
       note_excerpt: str = ""

       def to_dict(self) -> dict:
           return asdict(self)


   class RoutingLogReader:
       def __init__(self, path: Path = DEFAULT_ROUTING_LOG_PATH):
           self._path = path
           self._cache: Optional[set[str]] = None

       def routed_filenames(self) -> set[str]:
           if self._cache is not None:
               return self._cache
           names: set[str] = set()
           if not self._path.exists():
               self._cache = names
               return names
           try:
               with self._path.open("r", encoding="utf-8") as fh:
                   for lineno, raw in enumerate(fh, start=1):
                       raw = raw.strip()
                       if not raw:
                           continue
                       try:
                           entry = json.loads(raw)
                       except json.JSONDecodeError as exc:
                           print(f"[routing_log] line {lineno}: malformed JSON, skipping: {exc}", file=sys.stderr)
                           continue
                       name = entry.get("filename")
                       if not isinstance(name, str):
                           print(f"[routing_log] line {lineno}: missing/invalid filename, skipping", file=sys.stderr)
                           continue
                       names.add(name)
           except OSError as exc:
               print(f"[routing_log] could not read {self._path}: {exc}", file=sys.stderr)
           self._cache = names
           return names

       def has(self, filename: str) -> bool:
           return filename in self.routed_filenames()


   class RoutingLogWriter:
       def __init__(self, path: Path = DEFAULT_ROUTING_LOG_PATH):
           self._path = path

       def append(
           self,
           filename: str,
           issue_number: int,
           vikunja_task_id: Optional[int] = None,
           note_excerpt: str = "",
       ) -> RoutingEntry:
           entry = RoutingEntry(
               filename=filename,
               issue_number=issue_number,
               vikunja_task_id=vikunja_task_id,
               routed_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
               note_excerpt=(note_excerpt or "")[:120],
           )
           self._path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
           with self._path.open("a", encoding="utf-8") as fh:
               fh.write(json.dumps(entry.to_dict()) + "\n")
           return entry
   ```

2. Ensure stdlib only (no external deps).
3. Module is invocable both as a library and indirectly via the CLI helpers landed in WP03.

**Files**:

- `scripts/inbox/routing_log.py` (create, ~100 lines)

**Validation**: see T003 below.

---

### T003 — Tests for `routing_log.py`

**Purpose**: Lock the public API behavior of `RoutingLogReader` + `RoutingLogWriter`. Pytest-style, no external deps.

**Steps**:

1. Create `tests/inbox/test_routing_log.py` with cases:
   - `test_reader_returns_empty_set_when_file_missing` — pass a nonexistent path via `tmp_path`; expect empty set.
   - `test_reader_returns_filenames_when_present` — write 3 JSONL lines to `tmp_path/log.jsonl`, init reader, assert `routed_filenames()` returns exactly those 3 filenames.
   - `test_reader_skips_malformed_lines_with_warning` — write 2 valid lines + 1 garbage line; verify the 2 valid show up, the garbage doesn't (captured via `capsys`).
   - `test_reader_caches_after_first_read` — call `routed_filenames()` twice, verify file is read once (via `monkeypatch` of `Path.open` or by mutating the file between calls — should NOT see the new content).
   - `test_has_returns_true_for_present_filename` and `test_has_returns_false_for_absent_filename`.
   - `test_writer_appends_single_line` — call `append(...)` once, verify file has exactly one valid JSONL line containing the expected fields.
   - `test_writer_appends_does_not_truncate` — call `append` twice with different filenames, verify file has both lines.
   - `test_writer_creates_parent_directory` — pass a path whose parent doesn't exist; verify `append` creates it.
   - `test_writer_truncates_note_excerpt_at_120_chars` — pass a 200-char excerpt; verify written excerpt is 120 chars.
   - `test_writer_sets_routed_at_iso_utc` — call `append`, verify `routed_at` parses via `datetime.fromisoformat`.

2. All tests use `tmp_path` fixtures; NO test should write to `~/second-brain/agents/state/`.

**Files**: `tests/inbox/test_routing_log.py` (create, ~150 lines)

**Validation**:

- `pytest tests/inbox/test_routing_log.py -v` — all green.
- After test run, `~/second-brain/agents/state/inbox-routing.jsonl` is NOT modified (the tests should be hermetic).

---

## Definition of Done

- All three subtasks complete.
- `pytest tests/inbox/test_routing_log.py -v` is green.
- `tests/inbox/fixtures/` contains 8 .md files; the BOM fixture has correct bytes verified via `xxd`.
- Commit prefix: `feat(WP01):` referencing #185.

## Risks

- **Hermetic tests**: never let tests write to the real `~/second-brain/agents/state/`. Always pass explicit paths from `tmp_path`. If a test ever fails because of stale data in the real path, it's an indication of a bad test, not a code bug.
- **Encoding**: BOM-prefixed fixture file must be written as raw bytes; `Write` tool's text-mode write may not preserve BOM. Use `python3 -c "open('.../inbox-utf8-bom.md', 'wb').write(...)"` or equivalent.

## Reviewer guidance

- Verify: `RoutingEntry` is `frozen=True` (immutable).
- Verify: `append` uses `mkdir(parents=True, exist_ok=True, mode=0o700)`.
- Verify: `routed_at` is rendered with the `Z` suffix (UTC) per the contract, not `+00:00`.
- Verify: `note_excerpt` truncates at 120 chars (FR-002).
- Verify: tests use `tmp_path`, NOT the production path.

## Suggested implement command

```bash
spec-kitty agent action implement WP01 --agent <name>
```
