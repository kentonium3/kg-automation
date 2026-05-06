---
work_package_id: WP01
title: Update prescan classifier to prefer processed_at
dependencies: []
requirement_refs:
- FR-04
- FR-05
planning_base_branch: main
merge_target_branch: main
branch_strategy: Worktree allocated per computed lane from lanes.json. Merges into main.
subtasks:
- T001
- T002
- T003
history:
- date: '2026-05-06'
  event: created
  agent: claude-opus
authoritative_surface: scripts/inbox/
execution_mode: code_change
owned_files:
- scripts/inbox/prescan.py
tags: []
---

# WP01: Update prescan classifier to prefer processed_at

## Objective

Modify the `classify_file()` function in `scripts/inbox/prescan.py` to derive
staleness age from a `processed_at` frontmatter field when present, falling back
to filesystem mtime for backward compatibility.

## Context

- **File**: `scripts/inbox/prescan.py`
- **Function**: `classify_file()` at line 212
- **Current behavior**: Age is always computed from filesystem mtime (line 214-216)
- **Target behavior**: When `status == "processed"` and `processed_at` exists in
  frontmatter, parse it as ISO 8601 and use it for age. Fall back to mtime otherwise.

The `InboxFile` dataclass and classification categories (`processed-recent`,
`processed-stale`) remain unchanged. Only the age source changes.

## Implementation Guide

### T001: Add processed_at parsing to classify_file()

**Purpose**: When frontmatter contains `processed_at` and status is `processed`,
compute `age_days` from the parsed timestamp instead of mtime.

**Steps**:

1. After frontmatter is parsed and `status_raw` is extracted (around line 268),
   check for `processed_at` in the frontmatter dict.

2. In the `elif status_raw == "processed":` branch (line 277), before computing
   staleness, attempt to parse `processed_at`:

   ```python
   processed_at_raw = frontmatter.get("processed_at")
   if processed_at_raw is not None:
       effective_age = _parse_processed_at_age(processed_at_raw, now_utc)
       if effective_age is not None:
           age_days = effective_age
   ```

3. The `age_days` variable is already initialized from mtime at the top of the
   function (line 216). This approach only overrides it when `processed_at` is
   present and valid — mtime remains the default.

**Files**: `scripts/inbox/prescan.py`

### T002: Handle processed_at as both str and datetime from YAML

**Purpose**: `yaml.safe_load()` may auto-parse ISO timestamps into `datetime`
objects depending on the exact format. Handle both types defensively.

**Steps**:

1. Create a helper function `_parse_processed_at_age()` near the other helper
   functions (after `_extract_frontmatter_block`, around line 210):

   ```python
   def _parse_processed_at_age(
       raw: object, now_utc: datetime
   ) -> Optional[float]:
       """Parse processed_at value and return age in days, or None on failure."""
       if isinstance(raw, datetime):
           ts = raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
       elif isinstance(raw, str):
           try:
               ts = datetime.fromisoformat(raw)
           except (ValueError, TypeError):
               return None
           if ts.tzinfo is None:
               ts = ts.replace(tzinfo=timezone.utc)
       else:
           return None
       return (now_utc - ts).total_seconds() / 86400.0
   ```

2. This handles:
   - String values (normal case from agent-written frontmatter)
   - datetime objects (if YAML auto-parses)
   - Naive timestamps (assumed UTC)
   - Returns None on any parse failure (triggers mtime fallback)

**Files**: `scripts/inbox/prescan.py`

### T003: Graceful fallback when processed_at is malformed

**Purpose**: If `processed_at` contains garbage, the classifier must silently
fall back to mtime without crashing or changing classification behavior.

**Steps**:

1. The `_parse_processed_at_age()` function already returns `None` on parse
   failure. Ensure the calling code in `classify_file()` treats `None` as
   "use mtime" — which it does by only overriding `age_days` when the helper
   returns a non-None value.

2. No warning is emitted for malformed `processed_at` — this is intentional.
   The field is additive and its absence or malformation should not pollute
   the warning output that operators monitor.

**Files**: `scripts/inbox/prescan.py`

## Definition of Done

- [ ] `classify_file()` uses `processed_at` for age when present and valid
- [ ] `classify_file()` falls back to mtime when `processed_at` is absent
- [ ] `classify_file()` falls back to mtime when `processed_at` is malformed
- [ ] No new dependencies added (stdlib only)
- [ ] Existing tests still pass (run `pytest tests/scripts/inbox/ -v`)

## Risks

- **YAML auto-parsing**: Mitigated by handling both `str` and `datetime` types
- **Timezone-naive timestamps**: Mitigated by assuming UTC for naive values

## Reviewer Guidance

- Verify the mtime fallback path is still exercised for files without `processed_at`
- Verify no new imports beyond stdlib
- Check that the helper function is pure (no side effects, no file I/O)
