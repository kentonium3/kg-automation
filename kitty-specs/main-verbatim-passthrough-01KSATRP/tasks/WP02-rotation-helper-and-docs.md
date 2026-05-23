---
work_package_id: WP02
title: Session rotation helper + runbook + arch docs
dependencies:
- WP01
requirement_refs:
- C-003
- C-005
- C-006
- FR-005
- FR-006
- FR-007
- FR-008
- FR-009
- NFR-001
- NFR-002
- NFR-004
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
created_at: '2026-05-23T16:30:00+00:00'
subtasks:
- T005
- T006
- T007
- T008
history: []
authoritative_surface: scripts/openclaw/helpers/
execution_mode: code_change
mission_id: 01KSATRP0S0TDA5HV995Y558JK
mission_slug: main-verbatim-passthrough-01KSATRP
owned_files:
- scripts/openclaw/helpers/rotate_main_session.py
- tests/openclaw/helpers/test_rotate_main_session.py
- docs/runbooks/openclaw-agent-setup.md
- docs/design/architecture/data/service-inventory.json
- docs/design/architecture/data/data-flows.json
- docs/design/architecture/service-inventory.md
- docs/design/architecture/data-flows.md
tags: []
agent: "claude:opus:python-implementer:implementer"
shell_pid: "87974"
---

# WP02 — Session rotation helper + runbook + arch docs

## Objective

Create the `rotate_main_session.py` helper so the operator can force `main` agent's active sessions to reset (mirroring the existing `.jsonl.reset.<timestamp>` auto-rotation pattern). Update the openclaw-agent-setup runbook with the cutover sequence. Register the helper in architecture docs.

## Context

- **Spec**: FR-005..FR-009, NFR-001, NFR-002, NFR-004
- **Plan**: D1 (rename mechanism), D4 (main-only scope)
- **Contract**: [contracts/rotation-helper.md](../contracts/rotation-helper.md)
- **Pattern source**: `scripts/doc_audit/helpers/cutover_362.py` for `_StructuredArgumentParser`, marker file, idempotency, dry-run/force flags
- **Active sessions today**: 6 `.jsonl` files in `/home/claude/.openclaw/agents/main/sessions/` (verified pre-spec via ssh probe)

## Subtasks

### T005 — rotate_main_session.py

Steps:
1. Create `scripts/openclaw/helpers/rotate_main_session.py` with module docstring.
2. Module constants:
   ```python
   SESSIONS_DIR = Path("/home/claude/.openclaw/agents/main/sessions")
   MARKER_DIR = Path.home() / ".config" / "openclaw"
   ```
3. Functions:
   - `_list_active_sessions(sessions_dir) -> list[Path]` — return all `*.jsonl` files excluding `*.reset.*`
   - `_rotate_session(path, timestamp) -> Path` — rename to `<uuid>.jsonl.reset.<timestamp>`; return the new path
   - `_write_marker(rotated, timestamp) -> Path` — write marker file with list of rotated session names
   - `run(*, dry_run=False, force=False) -> RotationResult` — main orchestrator
   - `main(argv=None) -> int` — CLI with `--dry-run` and `--force`; uses `_StructuredArgumentParser` (mirror cutover_362)
4. Exit codes: 0 success, 1 filesystem error, 3 invalid args
5. Timestamp format: `2026-05-23T16-30-45.000Z` (hyphens not colons; cross-platform safe; matches existing pattern observed on office2)

Validation:
- [ ] `python3 scripts/openclaw/helpers/rotate_main_session.py --help` exits 0
- [ ] Module importable: `from scripts.openclaw.helpers.rotate_main_session import run, RotationResult`

### T006 — Tests

Steps:
1. Create `tests/openclaw/helpers/test_rotate_main_session.py`.
2. Use `tmp_path` to create a fake sessions dir with mock `.jsonl` and `.jsonl.reset.*` files.
3. Test cases:
   - Happy path: 3 active sessions → 3 renames + marker
   - Dry-run: no renames, no marker
   - Empty sessions dir: returns RotationResult with 0 sessions, exit 0
   - Skip-reset filter: `.jsonl.reset.*` files are NOT rotated
   - Filesystem rename failure: exit 1
   - Marker write failure: exit 1
   - CLI exit codes: 0/0/3
4. Coverage target ≥85%.

Validation:
- [ ] `PYTHONPATH=scripts python3 -m pytest tests/openclaw/helpers/test_rotate_main_session.py -v --cov=openclaw.helpers.rotate_main_session` ≥85%
- [ ] No filesystem leaks (use `tmp_path` fixtures only)

### T007 — Update openclaw-agent-setup runbook

Steps:
1. Read existing `docs/runbooks/openclaw-agent-setup.md`. Identify section structure.
2. Add new section §"Cutover sequence for main-agent AGENTS.md changes (post-#374)":
   ```markdown
   ## Cutover sequence for main-agent AGENTS.md changes (post-#374)

   When changing `/data/services/openclaw/data/AGENTS.md`, active sessions
   keep their cached system prompt. Use this sequence to force the new
   instructions to load:

   1. **Pull repo on office2**: `ssh office2-claude 'cd ~/kg-automation && git pull origin main'`
   2. **Deploy AGENTS.md**: `ssh office2-claude 'cp ~/kg-automation/scripts/openclaw/agents/main/AGENTS.md /data/services/openclaw/data/AGENTS.md'`
   3. **Verify size budget**: `ssh office2-claude 'wc -c /data/services/openclaw/data/AGENTS.md'` must show ≤14000
   4. **Rotate sessions**: `ssh office2-claude 'python3 ~/kg-automation/scripts/openclaw/helpers/rotate_main_session.py'`
   5. **Smoke test**: send a known WhatsApp message; verify verbatim text in the relevant sub-agent's session jsonl via:
      `ssh office2-claude 'ls -t /home/claude/.openclaw/agents/felix-admin-habits/sessions/*.jsonl | head -1 | xargs grep "<your verbatim phrase>"'`
   ```
3. Update frontmatter: `last_validated: 2026-05-23`, `updated_by: '#374'`, bump `version`.
4. Cross-reference the mission spec at `kitty-specs/main-verbatim-passthrough-01KSATRP/spec.md`.

Validation:
- [ ] Section present + grep-friendly
- [ ] Frontmatter updated_by includes '#374'
- [ ] All 5 cutover steps include actual command lines (operator can copy-paste)

### T008 — Architecture docs

Steps:
1. `docs/design/architecture/data/service-inventory.json`:
   - Find any existing entry for the `main` agent. Add a note that AGENTS.md is governed by the verbatim pass-through rule (post-#374); `updated_by: "#374"`.
   - Add new entry `rotate_main_session` (kind=one_shot_script, path=`scripts/openclaw/helpers/rotate_main_session.py`, invoked_by=`operator`, introduced_by=`"#374"`, writes_to=`/home/claude/.openclaw/agents/main/sessions/` (renames) + `~/.config/openclaw/main-rotation-*.done` (marker)).
2. `docs/design/architecture/data/data-flows.json`:
   - Add a new flow `main-session-rotation-rename` (from `scripts/openclaw/helpers/rotate_main_session.py`, to `/home/claude/.openclaw/agents/main/sessions/`). Trigger: operator manual run during cutover. introduced_by=`"#374"`.
3. Update markdown views to match (`service-inventory.md`, `data-flows.md`).
4. Validate JSON parses.

Validation:
- [ ] `python3 -c "import json; json.load(open('docs/design/architecture/data/service-inventory.json'))"` succeeds
- [ ] `python3 -c "import json; json.load(open('docs/design/architecture/data/data-flows.json'))"` succeeds
- [ ] Markdown views have corresponding entries for the new helper

## Definition of Done

- [ ] All 4 subtasks complete
- [ ] `pytest` passes ≥85% coverage on rotate_main_session.py
- [ ] Runbook section copy-pasteable end-to-end by operator
- [ ] JSONs parse; markdown views match

## Implementation Command

```bash
spec-kitty agent action implement WP02 --mission main-verbatim-passthrough-01KSATRP --agent claude:opus:python-implementer:implementer
```

## Activity Log

- 2026-05-23T18:04:17Z – claude:opus:python-implementer:implementer – shell_pid=87974 – Started implementation via action command
- 2026-05-23T19:30:55Z – claude:opus:python-implementer:implementer – shell_pid=87974 – Ready for review: rotate_main_session.py + tests + runbook + arch docs; 20 tests / 97% coverage
