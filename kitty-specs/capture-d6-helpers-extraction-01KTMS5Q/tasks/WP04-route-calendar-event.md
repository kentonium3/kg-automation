---
work_package_id: WP04
title: route_calendar_event helper
dependencies: []
requirement_refs:
- FR-005
tracker_refs: []
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this mission were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks:
- T007
- T008
agent: claude
history: []
agent_profile: python-pedro
authoritative_surface: scripts/inbox/
execution_mode: code_change
mission_id: 01KTMS5QGXFJWQYVXB03SPYB48
mission_slug: capture-d6-helpers-extraction-01KTMS5Q
model: claude-sonnet-4-6
owned_files:
- scripts/inbox/route_calendar_event.py
- tests/inbox/test_route_calendar_event.py
role: implementer
tags: []
---

## ⚡ Do This First: Load Agent Profile

```
/ad-hoc-profile-load python-pedro
```

## Objective

Implement `scripts/inbox/route_calendar_event.py` — validate a calendar payload JSON via the existing `scripts.calendar_routing.validate_calendar_event`; on valid, emit a normalized payload JSON on stdout (with default `end` if absent); on invalid, exit non-zero with structured stderr.

CLI: `python3 -m scripts.inbox.route_calendar_event --payload-file <abs-path>`

## Context

| Document | Why |
|---|---|
| [../spec.md](../spec.md) § FR-005, FR-009 | Functional contract |
| [../contracts/helper-cli.md](../contracts/helper-cli.md) § `route_calendar_event` | CLI surface |
| `scripts/calendar_routing/validate_calendar_event.py` | The validator — READ its actual signature before writing |

## Subtask Guidance

### T007 — Tests + Implementation

**FIRST: probe the actual `validate_calendar_event` signature**:

```bash
grep -E "^def " scripts/calendar_routing/validate_calendar_event.py
```

Note the return shape. Spec assumes `(is_valid: bool, missing: list[str])` — verify against actual; adjust this WP if different. Per `[[feedback_design_phase_research]]`.

**Tests** (`tests/inbox/test_route_calendar_event.py`):

- `test_valid_payload_emits_normalized_json` — payload has title + start (no end) → stdout JSON has `end` filled in (start + 1 hour); exit 0
- `test_valid_payload_with_end_passes_through` — payload has explicit `end` → stdout JSON preserves it
- `test_invalid_payload_emits_structured_error` — payload missing required field → stderr is `{"error": "invalid_payload", "missing": [...]}` JSON; exit 1
- `test_payload_file_missing_exits_1`
- `test_payload_file_malformed_json_exits_1`
- `test_help_exits_0`

**Implementation** (`scripts/inbox/route_calendar_event.py`):

- Imports: `argparse`, `json`, `sys`, `datetime`, `scripts.calendar_routing.validate_calendar_event`
- Function `normalize_payload(payload: dict) -> dict` — fills in `end` if absent
- `main(argv=None) -> int` — orchestrator

### T008 — Coverage gate

```bash
pytest tests/inbox/test_route_calendar_event.py \
  --cov=scripts.inbox.route_calendar_event \
  --cov-branch --cov-fail-under=90
```

## Definition of Done

- [ ] `scripts/inbox/route_calendar_event.py` exists
- [ ] `tests/inbox/test_route_calendar_event.py` exists with all cases above
- [ ] `--help` exits 0
- [ ] Coverage gate passes
- [ ] Lane committed; WP moved to `for_review`

## Risks

- Validator signature drift — probed at design time but verify before writing tests.
- Default-end logic — start + 1 hour is the assumption; if the existing system uses 30 min or other, match the existing default.
