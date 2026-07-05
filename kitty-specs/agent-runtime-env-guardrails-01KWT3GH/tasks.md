# Tasks: Agent runtime-env guardrails (#658)

**Mission**: agent-runtime-env-guardrails-01KWT3GH · **Branch**: `feat/agent-runtime-env-guardrails`
**Artifacts**: [spec.md](./spec.md) · [plan.md](./plan.md) · [research.md](./research.md) · [data-model.md](./data-model.md) · [contracts/checker-contract.md](./contracts/checker-contract.md)

Canonical anchor form (post-Codex): `cd "${PYTHONPATH:?<msg>}" && python3 -m scripts.X.Y`
and `cd "${PYTHONPATH:?<msg>}" && python3 scripts/<path>.py` (covers `python` and `python3`).
No hardcoded checkout; deterministic cwd; fail-loud outside gateway; helper args absolute.

## Subtask Index

| ID | Description | WP | Parallel |
|----|-------------|----|----------|
| T001 | Finding dataclass + ViolationKind enum (4 kinds; python+python3 abs-path) | WP01 | | [D] |
| T002 | Logical-command recognizer (join continuations/fenced; inline-imperative; exclude placeholder/comment) | WP01 | | [D] |
| T003 | Classification: cd-form compliance predicate + 4 violation detectors | WP01 | | [D] |
| T004 | Waiver parsing (`# env-guard: waive <kind> — reason`) | WP01 | | [D] |
| T005 | Public API scan_text/scan_file/scan_agents_root (exclude retired doc-auditor) | WP01 | | [D] |
| T006 | Unit tests: each ViolationKind TP, canonical TN, must-not-flag, multiline, python-abspath, waiver | WP01 | | [D] |
| T007 | capture AGENTS.md: convert 14 bare `-m scripts.` → cd form | WP02 | [D] |
| T008 | capture AGENTS.md.tmpl: convert abs-path `python3 /home/claude/...` invocations | WP02 | [D] |
| T009 | capture `.tmpl`↔AGENTS.md lockstep; convert the `.tmpl` `-m scripts.` | WP02 | [D] |
| T010 | capture self-scan with checker → 0 findings; args absolute | WP02 | [D] |
| T011 | habits: de-hardcode 5 `cd /home/claude/kg-automation` → cd "${PYTHONPATH:?}" | WP03 | [D] |
| T012 | habits: convert 3 abs-path felix-file-issue.py invocations | WP03 | [D] |
| T013 | escalation: convert 7 bare `-m scripts.` + 1 abs-path | WP03 | [D] |
| T014 | habits+escalation self-scan → 0 findings | WP03 | [D] |
| T015 | tasker: convert 2 `-m scripts.` + abs-path + `.tmpl` lockstep | WP04 | [D] |
| T016 | calendar: convert abs-path log_action.py (×3) + validate_calendar_event.py | WP04 | [D] |
| T017 | main: audit; convert any abs-path or confirm clean | WP04 | [D] |
| T018 | tasker+calendar+main self-scan → 0 findings | WP04 | [D] |
| T019 | Fleet-scan guard test (scan_agents_root → 0 non-waived; actionable msg) | WP05 | |
| T020 | check_runtime_env_assumptions() in validate_workspace.py (CheckResult `ok`) + append to checks | WP05 | |
| T021 | doc-auditor retired disposition recorded | WP05 | |
| T022 | Extend test_validate_workspace.py; full guard green | WP05 | |
| T023 | Update #167 workspace-authoring standard doc to reference the guardrail | WP06 | |
| T024 | Reconcile architecture docs per signal-to-doc-map | WP06 | |
| T025 | Author deploys/queued/0010-agent-runtime-env-guardrails.yaml (deploy_agent_prompts.py; health incl calendar; auto-rebaseline) | WP06 | |
| T026 | Post-deploy verification (capture prescan self-check; cron green; calendar; cwd smoke) | WP06 | |

## Work Packages

### WP01 — Shared env-assumption checker + unit tests
- **Goal**: deliver `scripts/openclaw/agents/env_assumptions.py` — the one deterministic
  detector both consumers (Test-CI guard, workspace validator) share — plus its unit tests.
- **Priority**: P0 (foundational). **Independent test**: `pytest test_env_assumptions.py` green.
- **Subtasks**: T001, T002, T003, T004, T005, T006
- **Dependencies**: none. **Est. prompt**: ~320 lines.
- **Requirements**: FR-001, FR-002, FR-007, NFR-001..004.

### WP02 — Convert felix-admin-capture
- **Goal**: convert all capture invocations (AGENTS.md + AGENTS.md.tmpl) to the canonical form.
- **Subtasks**: T007, T008, T009, T010. **Dependencies**: WP01. **Est.**: ~200 lines.
- **Requirements**: FR-005.

### WP03 — Convert felix-admin-habits + felix-admin-escalation
- **Goal**: de-hardcode habits' `cd` + abs-path; convert escalation's bare invocations.
- **Subtasks**: T011, T012, T013, T014. **Dependencies**: WP01. **Est.**: ~220 lines.
- **Requirements**: FR-005, FR-006.

### WP04 — Convert felix-admin-tasker + felix-admin-calendar + audit main
- **Goal**: convert tasker (+.tmpl) + calendar abs-path; audit main.
- **Subtasks**: T015, T016, T017, T018. **Dependencies**: WP01. **Est.**: ~230 lines.
- **Requirements**: FR-005, FR-008.

### WP05 — Fleet-scan guard + validator fold + doc-auditor disposition
- **Goal**: the Test-CI guard (green only after WP02-04) + validate_workspace.py fold.
- **Subtasks**: T019, T020, T021, T022. **Dependencies**: WP02, WP03, WP04. **Est.**: ~240 lines.
- **Requirements**: FR-003, FR-004, FR-008.

### WP06 — Docs + deploy + verify
- **Goal**: #167 standard doc + architecture reconcile + deploy manifest 0010 + verification.
- **Subtasks**: T023, T024, T025, T026. **Dependencies**: WP05. **Est.**: ~230 lines.
- **Requirements**: FR-009, Architecture Impact.

## Sequencing
`WP01` → (`WP02` ∥ `WP03` ∥ `WP04`) → `WP05` → `WP06`. MVP = WP01 (the checker) — it is the
prevention mechanism; conversions clear the existing fleet; deploy ships it.
