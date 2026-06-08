---
work_package_id: WP03
title: route_someday helper
dependencies: []
requirement_refs:
- FR-004
tracker_refs: []
planning_base_branch: main
merge_target_branch: main
branch_strategy: lane-from-coordination
subtasks:
- T005
- T006
agent: claude
history: []
agent_profile: python-pedro
authoritative_surface: scripts/inbox/
execution_mode: code_change
mission_id: 01KTMS5QGXFJWQYVXB03SPYB48
mission_slug: capture-d6-helpers-extraction-01KTMS5Q
model: claude-sonnet-4-6
owned_files:
- scripts/inbox/route_someday.py
- tests/inbox/test_route_someday.py
role: implementer
tags: []
---

## ⚡ Do This First: Load Agent Profile

```
/ad-hoc-profile-load python-pedro
```

## Objective

Implement `scripts/inbox/route_someday.py` — create a Vikunja task in the Someday project (resolved by name via the existing shared client). Use the CREATE endpoint per `[[feedback_vikunja_post_partial_replace]]`.

CLI: `python3 -m scripts.inbox.route_someday --title "<title>" --body "<body>" --note-filename <name>`

## Context

| Document | Why |
|---|---|
| [../spec.md](../spec.md) § FR-004, C-006 | Functional contract + partial-replace gotcha |
| [../contracts/helper-cli.md](../contracts/helper-cli.md) § `route_someday` | CLI surface |
| `scripts/common/vikunja_client.py` | The shared client (read its `list_projects` + `create_task` signatures before writing) |
| `tests/common/test_vikunja_client.py` | Mocking precedent for the client |

## Subtask Guidance

### T005 — Tests + Implementation

**Tests** (`tests/inbox/test_route_someday.py`):

- `test_resolves_someday_project_by_name` — mock `VikunjaClient.list_projects` to return projects including `{"id": 99, "title": "Someday"}`; verify helper resolves to id 99
- `test_creates_task_with_title_and_description_including_source` — mock `create_task`; verify it was called with the correct `project_id`, `title`, and `description` containing `Source: <note-filename>`
- `test_uses_create_endpoint_not_partial_update` — assert via mock that `create_task` (not `update_task`) was called; this is the load-bearing C-006 protection
- `test_emits_task_id_on_stdout` — successful create → `task_id=<int>` on stdout
- `test_vikunja_unreachable_exits_2` — mock client to raise `ConnectionError` → exit 2, structured stderr
- `test_someday_project_missing_exits_2` — mock `list_projects` to return no `Someday` → exit 2, stderr names the missing project
- `test_create_task_error_exits_2` — mock `create_task` to raise → exit 2
- `test_help_exits_0_with_usage_text`

**Implementation** (`scripts/inbox/route_someday.py`):

- Imports: `argparse`, `json`, `sys`, `scripts.common.vikunja_client`
- Function `find_someday_project(client) -> int` — returns project id or raises if missing
- Function `route_someday(title, body, note_filename) -> int` — orchestrator; calls list_projects, create_task, returns exit code
- `main(argv=None) -> int`

### T006 — Coverage gate

```bash
pytest tests/inbox/test_route_someday.py \
  --cov=scripts.inbox.route_someday \
  --cov-branch --cov-fail-under=90
```

## Definition of Done

- [ ] `scripts/inbox/route_someday.py` exists
- [ ] `tests/inbox/test_route_someday.py` exists with all cases above
- [ ] `--help` exits 0
- [ ] Coverage gate passes
- [ ] NO real Vikunja network call in tests (mock the client; verify with `grep -E "VikunjaClient\(\)" tests/inbox/test_route_someday.py` is mocked context)
- [ ] Lane committed; WP moved to `for_review`

## Risks

- `VikunjaClient` API drift — read its current signatures before writing tests. If the actual method is `get_projects()` not `list_projects()`, adjust both the helper AND the tests accordingly. Per `[[feedback_design_phase_research]]`.
- Vikunja project-name match is case-sensitive — verify against the actual `Someday` project's title in the live Vikunja, or document the case-sensitivity assumption.
