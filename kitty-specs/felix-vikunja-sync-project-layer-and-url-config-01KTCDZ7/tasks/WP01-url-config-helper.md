---
work_package_id: WP01
title: URL Config Helper
dependencies: []
requirement_refs:
- FR-006
- FR-007
- NFR-006
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
base_branch: kitty/mission-felix-vikunja-sync-project-layer-and-url-config-01KTCDZ7
base_commit: 166c9c647fd5ae2d6a58a51555c9b78e05999df6
created_at: '2026-06-05T19:12:38.050953+00:00'
subtasks:
- T001
- T002
- T003
shell_pid: "78214"
history: []
authoritative_surface: scripts/common/vikunja_config.py
execution_mode: code_change
owned_files:
- scripts/common/vikunja_config.py
- tests/test_vikunja_config.py
tags: []
agent: "claude:sonnet:implementer:implementer"
---

# WP01 — URL Config Helper

## Objective

Add a shared helper `scripts/common/vikunja_config.py` exposing a single function `get_vikunja_base_url()` and a custom error class `VikunjaConfigError`. This helper is the canonical lookup for the Vikunja API base URL across the codebase — replacing the multiple hardcoded URL strings that currently exist across `scripts/`.

This is the foundation for WP05 (touchpoint URL migration). It is a small, self-contained module with a clear public API.

## Context

Per spec FR-006 / FR-007 / FR-008 and `contracts/url-config.md`, the helper resolves the URL in this precedence order:

1. `VIKUNJA_BASE_URL` environment variable, if set and non-empty
2. Contents of `/data/services/openclaw/config/vikunja-base-url.txt`, whitespace-stripped

If neither is available, raise `VikunjaConfigError` with a message naming both expected sources.

The trailing slash is normalized: the function always returns the URL with a trailing slash, regardless of whether the env var / file has one. Consumers can then concatenate paths as `f"{base_url}tasks/all"` without conditional logic.

Path traversal is not a concern — the helper accepts no input from callers.

## Implementation guidance

### Subtask T001: Create `scripts/common/vikunja_config.py`

**Purpose**: provide the public API.

**Steps**:

1. Create the module at `scripts/common/vikunja_config.py`. Follow the structural conventions used in `scripts/common/sync_cache.py` (the WP01-FOUNDATION sibling from #519): top-level docstring with mission reference, `from __future__ import annotations`, stdlib-only imports, dataclass-style organization where helpful.

2. Define the public API:

   ```python
   import os
   import re
   from pathlib import Path

   _CANONICAL_FILE_PATH = Path("/data/services/openclaw/config/vikunja-base-url.txt")
   _URL_REGEX = re.compile(r"^https?://[^/]+/api/v1/?$")


   class VikunjaConfigError(RuntimeError):
       """Raised when neither VIKUNJA_BASE_URL env var nor canonical config file is available."""


   def get_vikunja_base_url() -> str:
       """Return the canonical Vikunja API base URL.

       Resolution order:
         1. VIKUNJA_BASE_URL environment variable, if set and non-empty
         2. Contents of {_CANONICAL_FILE_PATH}, stripped of whitespace

       Returns:
           URL with trailing slash, e.g., "https://office2.tail0f5f56.ts.net/api/v1/"

       Raises:
           VikunjaConfigError: if neither source is available, or if the value
               does not match a valid Vikunja API base URL pattern.
       """
       value = os.environ.get("VIKUNJA_BASE_URL", "").strip()
       if not value:
           if not _CANONICAL_FILE_PATH.exists():
               raise VikunjaConfigError(
                   f"Vikunja base URL not available. Set VIKUNJA_BASE_URL env var, "
                   f"or create {_CANONICAL_FILE_PATH} with a single line containing the URL."
               )
           try:
               value = _CANONICAL_FILE_PATH.read_text(encoding="utf-8").strip()
           except OSError as e:
               raise VikunjaConfigError(
                   f"Vikunja base URL file at {_CANONICAL_FILE_PATH} could not be read: {e}"
               ) from e
       if not value:
           raise VikunjaConfigError(
               f"Vikunja base URL is empty (env var and {_CANONICAL_FILE_PATH} both empty)."
           )
       if not _URL_REGEX.match(value):
           raise VikunjaConfigError(
               f"Vikunja base URL value {value!r} does not match expected pattern "
               f"(https?://<host>/api/v1[/])."
           )
       # Normalize trailing slash
       if not value.endswith("/"):
           value = value + "/"
       return value
   ```

3. Use stdlib only (`os`, `re`, `pathlib`). No third-party dependencies.

**Files**: `scripts/common/vikunja_config.py` (new, ~60 lines)

**Validation**:
- [ ] Module imports cleanly: `python3 -c "from scripts.common.vikunja_config import get_vikunja_base_url, VikunjaConfigError"`
- [ ] `_CANONICAL_FILE_PATH` is the documented path
- [ ] URL regex matches the documented pattern

### Subtask T002: Tests in `tests/test_vikunja_config.py`

**Purpose**: cover all 7 contract scenarios from `contracts/url-config.md` § Test contract.

**Steps**:

Create `tests/test_vikunja_config.py` with pytest. Use `monkeypatch` for env var manipulation and a `tmp_path` fixture (with `monkeypatch.setattr` on `_CANONICAL_FILE_PATH`) for the file fallback.

The 7 scenarios:

1. **Env var precedence**: set `VIKUNJA_BASE_URL=https://test.example/api/v1/`; create a file with a different URL; expect `get_vikunja_base_url()` returns the env var value (file not consulted).

2. **File fallback**: unset env var; create file with a URL; expect `get_vikunja_base_url()` returns the file's URL.

3. **Trailing-slash normalization**: env var has no trailing slash; expect returned URL has trailing slash.

4. **Whitespace stripping**: file has trailing newline + leading whitespace; expect returned URL is whitespace-stripped (still trailing slash normalized).

5. **Empty env var falls through**: env var set to empty string; file has a URL; expect file's URL returned.

6. **Both missing**: env var unset; file does not exist; expect `VikunjaConfigError` with message naming both expected locations.

7. **URL validation**: env var set to `not-a-url`; expect `VikunjaConfigError` with regex-mismatch message.

Plus one bonus test:

8. **Empty file**: env var unset; file exists but contains only whitespace; expect `VikunjaConfigError` (empty value).

**Files**: `tests/test_vikunja_config.py` (new, ~120 lines)

**Validation**:
- [ ] `pytest tests/test_vikunja_config.py -v` passes all 8 tests
- [ ] No live HTTP, no live filesystem outside `tmp_path`
- [ ] Tests use `monkeypatch.setattr("scripts.common.vikunja_config._CANONICAL_FILE_PATH", tmp_path / "url.txt")` to redirect the file path; tests do NOT write to `/data/services/openclaw/config/`.

### Subtask T003: Verify NFR-006 grep contract in this WP's owned files

**Purpose**: confirm that the file `scripts/common/vikunja_config.py` contains the expected URL pattern references (and no extra ones).

**Steps**:

1. Run `grep -n "office2.tail0f5f56.ts.net\|100.92.197.90:3456" scripts/common/vikunja_config.py`.

2. Expected output: zero hits, OR hits only in test fixtures / docstring examples (which is acceptable). The helper does NOT need to hardcode either URL value — it just resolves whatever the env var / file provides.

3. Run `grep -n "office2.tail0f5f56.ts.net\|100.92.197.90:3456" tests/test_vikunja_config.py`.

4. Expected output: test fixture values may use either URL (it's a test fixture, not a hardcoded reference).

5. Document the result of both greps in the WP's PR description (or include as comment when filing for review).

**Files**: no file changes — verification step only.

**Validation**:
- [ ] grep on `scripts/common/vikunja_config.py` returns zero or only-docstring matches
- [ ] grep on `tests/test_vikunja_config.py` is acceptable (test fixture values)

## Branch Strategy

- **Planning base branch**: `main`
- **Final merge target**: `main`
- **Execution worktree**: allocated per computed lane from `lanes.json` after `finalize-tasks` runs. The lane will be deduced from this WP's `owned_files` plus the dependency graph (none for WP01).

## Test Strategy

Unit tests only — this is a pure-helper module with no I/O dependencies beyond a single file read.

- All scenarios from `contracts/url-config.md` § Test contract are covered (8 tests including the empty-file edge case).
- No integration tests required (the helper is exercised by WP05's touchpoint migrations, which have their own existing test coverage).

## Definition of Done

- [ ] `scripts/common/vikunja_config.py` exists and exposes `get_vikunja_base_url()` + `VikunjaConfigError`
- [ ] `tests/test_vikunja_config.py` exists with 8 tests covering all contract scenarios
- [ ] `pytest tests/test_vikunja_config.py -v` passes (exit code 0)
- [ ] Module uses stdlib only
- [ ] NFR-006 grep verification (T003) documented
- [ ] No changes to files outside `owned_files`

## Risks

- **Trailing slash edge cases**: file has trailing slash + extra trailing whitespace; or file has no trailing slash. Both must produce the same normalized output. Tests T002 case 3 + case 4 cover this.
- **Empty env var precedence**: per memory `feedback_speckitty_input_not_output`, the spec is explicit that empty env var should fall through to the file. Make sure the test asserts this clearly (case 5).
- **Path injection**: not applicable — the helper accepts no input parameters.

## Reviewer Guidance

The reviewer should validate:

1. **API matches contract**: `get_vikunja_base_url()` signature + `VikunjaConfigError` class are exactly as specified in `contracts/url-config.md`.
2. **Precedence order is correct**: env var first, file fallback second; empty env var falls through to file.
3. **Trailing slash normalization**: returned URL always has trailing slash.
4. **URL validation**: invalid URL values raise `VikunjaConfigError` (not a silent default).
5. **Tests use monkeypatch correctly**: file path is monkeypatched to `tmp_path`; tests never write to the canonical production path.
6. **No live HTTP, no third-party imports**: stdlib only.
7. **Module docstring includes mission reference**: standard for new modules in this codebase (`scripts/common/sync_cache.py` is the precedent).

## Implementation command

```bash
spec-kitty agent action implement WP01 --mission felix-vikunja-sync-project-layer-and-url-config-01KTCDZ7 --agent <tool>:<model>:<profile>:<role>
```

## Next steps after WP01 approval

- WP05 can begin (it depends only on WP01).
- WP02, WP03 are independent of WP01 — they can run in parallel.

## Activity Log

- 2026-06-05T19:12:40Z – claude:sonnet:implementer:implementer – shell_pid=78214 – Assigned agent via action command
