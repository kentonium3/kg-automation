# Implementation Plan: Inbox Processed-At Timestamp

**Branch**: `main` | **Date**: 2026-05-06 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `kitty-specs/inbox-processed-at-timestamp-01KQZ2Y5/spec.md`

## Summary

Add a `processed_at` frontmatter field (ISO 8601, agent's local timezone) written by the inbox processor alongside `status: processed`. Update prescan.py to prefer `processed_at` over filesystem mtime for staleness age calculation, with mtime fallback for legacy files.

## Technical Context

**Language/Version**: Python 3.10+ (office2), Markdown (agent instructions)
**Primary Dependencies**: PyYAML (existing), datetime stdlib
**Storage**: N/A (frontmatter in markdown files)
**Testing**: pytest (existing suite in `tests/scripts/inbox/`)
**Target Platform**: Linux server (office2)
**Project Type**: Single project
**Performance Goals**: N/A (batch script, not latency-sensitive)
**Constraints**: Backward compatible with files lacking `processed_at`
**Scale/Scope**: ~5-10 inbox files per day

## Charter Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Charter governance resolution reports unavailable tools (pytest, python) in the charter tool registry. This is a charter configuration issue, not a feature blocker. No governance conflicts with this feature — it operates within existing autonomy boundaries (Level 3, inbox processing path).

Post-design re-check: No new governance concerns. Feature is additive, backward-compatible, and within existing scope.

## Project Structure

### Documentation (this feature)

```
kitty-specs/inbox-processed-at-timestamp-01KQZ2Y5/
├── spec.md              # Feature specification
├── plan.md              # This file
├── research.md          # Phase 0 output (minimal — no unknowns)
├── meta.json            # Mission metadata
└── checklists/
    └── requirements.md  # Spec quality checklist
```

### Source Code (repository root)

```
scripts/
├── inbox/
│   └── prescan.py                    # Modify: classify_file() age calculation
└── openclaw/
    └── agents/
        └── felix-admin-capture/
            └── AGENTS.md             # Modify: Step 5 instructions

tests/
└── scripts/
    └── inbox/
        ├── test_prescan.py           # Modify: add processed_at test cases
        └── fixtures/
            ├── processed-recent.md   # Modify: add processed_at field
            └── processed-stale.md    # Modify: add processed_at field
```

## Implementation Strategy

### Change 1: prescan.py — prefer processed_at for age calculation

**File**: `scripts/inbox/prescan.py`
**Function**: `classify_file()` (lines 212-294)

After frontmatter is parsed (line 267), check for `processed_at` key. When present and the status is `processed`:
1. Parse `processed_at` using `datetime.fromisoformat()` (Python 3.7+, handles offset-aware timestamps)
2. Compute `age_days` from parsed timestamp instead of filesystem mtime
3. If parsing fails (malformed value), fall back to mtime silently with a warning

No changes to the `InboxFile` dataclass or classification logic — only the age source changes.

### Change 2: Agent instructions — write processed_at

**File**: `scripts/openclaw/agents/felix-admin-capture/AGENTS.md`
**Section**: Step 5 ("Mark as processed"), lines 146-154

Add instruction: when setting `status: processed`, also write `processed_at` with the current timestamp in ISO 8601 format using the agent's local timezone. Do NOT write `processed_at` when setting `needs-review`.

### Change 3: Test fixtures and test cases

**Fixtures**: Add `processed_at` field to `processed-recent.md` and `processed-stale.md`
**Tests**: Add cases in `test_prescan.py` for:
- `processed_at` present → age derived from it
- `processed_at` absent → age derived from mtime (backward compat)
- `processed_at` malformed → fallback to mtime

## Dependency Check

- `datetime.fromisoformat()` handles offset-aware ISO 8601 in Python 3.7+. No new pip dependencies.
- `yaml.safe_load()` already parses string fields — `processed_at` will be loaded as a string naturally.

## Work Package Outline

| WP | Description | Files | Dependencies |
|----|-------------|-------|--------------|
| WP01 | Update prescan.py to prefer processed_at | `scripts/inbox/prescan.py` | None |
| WP02 | Update test fixtures and add test cases | `tests/scripts/inbox/fixtures/*.md`, `tests/scripts/inbox/test_prescan.py` | WP01 |
| WP03 | Update agent instructions to write processed_at | `scripts/openclaw/agents/felix-admin-capture/AGENTS.md` | None |

WP01 and WP03 are independent (lane-parallelizable). WP02 depends on WP01.

## Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Agent writes malformed timestamp | Low | Low | Prescan falls back to mtime |
| fromisoformat unavailable | None | N/A | Python 3.10+ on office2 |
| Existing tests break | Low | Medium | Fixtures updated in same WP as test code |
