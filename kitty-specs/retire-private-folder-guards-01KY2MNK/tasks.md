# Tasks: Retire _private folder guard apparatus

**Mission**: retire-private-folder-guards-01KY2MNK | **Branch**: `feat/retire-private-folder-guards`

Seven work packages map 1:1 to the plan's Implementation Concerns (IC-08 verification + the office2
deploy/smoke are **post-merge acceptance**, not worktree WPs — the deploy needs all WPs merged).
Every WP's authoritative detail is the shared [data-model.md](./data-model.md) surface table + the
[spec.md](./spec.md) requirements; WP prompts point to their rows rather than duplicating them.

## Subtask Index

| ID | Description | WP | Parallel |
|----|-------------|----|----------|
| T001 | Delete validate_privacy_boundary.py | WP01 | | [D] |
| T002 | Remove validator call from .githooks/pre-commit | WP01 | [D] |
| T003 | Remove "Validate privacy boundary lint" step from docs-ci.yml | WP01 | [D] |
| T004 | Remove validator target from Makefile | WP01 | [D] |
| T005 | Remove validator refs from autopilot adapter + local-test-gate runbook | WP01 | [D] |
| T006 | Remove Invariants A+D + constants from validate_workspace.py | WP02 | | [D] |
| T007 | Trim privacy tests in test_validate_workspace.py | WP02 | | [D] |
| T008 | Delete tests/openclaw/test_privacy_pointer.py | WP02 | [D] |
| T009 | Drop "prompts must carry privacy red-line" from openclaw-workspace-authoring-standard.md | WP02 | [D] |
| T010 | hard_fail: keep second-brain redaction, drop bare _private fragment | WP03 | | [D] |
| T011 | mark_processed: refuse-outside-inbox-root (drop _private literal) | WP03 | | [D] |
| T012 | classify_content + prescan: delete _private refusal/skip | WP03 | | [D] |
| T013 | route_and_finalize + gitignore-additions + inbox/vault READMEs: strip _private | WP03 | [D] |
| T014 | Update hygiene tests (hard_fail, mark_processed, classify_content, prescan) | WP03 | | [D] |
| T015 | Strip red-line from 6 deployed agents' prompts | WP04 | | [D] |
| T016 | Strip red-line from felix-doc-auditor prompts (repo-only) | WP04 | [D] |
| T017 | CLAUDE.md + CODEX.md: remove absolute rule, keep repo boundary | WP05 | | [D] |
| T018 | ai-agents/{claude,claude-code,gemini}-instructions.md: same | WP05 | [D] |
| T019 | FELIX-CONSTITUTION.md: reframe folder rule to physical exclusion | WP05 | [D] |
| T020 | architecture docs (glossary, security-posture, service-inventory.{md,json}): reframe | WP06 | | [D] |
| T021 | coherence/doctrine + roadmap + process-flows: reframe | WP06 | [D] |
| T022 | runbooks (escalation/habits/inbox/openclaw-agent-setup/tasker-ops): reframe | WP06 | [D] |
| T023 | second-brain-graph-layer.md: reframe #692/#696 gate to "verify not present" | WP07 | | [D] |
| T024 | executive-assistant-architecture.md: same model reframe | WP07 | [D] |

## Work Packages

### WP01 — Remove the stale-path lint validator + all wiring (IC-01)
- **Goal**: Delete `validate_privacy_boundary.py` and every caller so nothing invokes a removed script.
- **Priority**: P1 (gate self-consistency) · **Independent test**: local commit + CI green with no privacy-lint step.
- **Subtasks**: T001, T002, T003, T004, T005
- **Deps**: none · **Prompt**: [WP01](./tasks/WP01-remove-lint-validator.md) (~120 lines)

### WP02 — Retire the workspace-validator privacy invariants (IC-02)
- **Goal**: Remove Invariants A+D + constants from `validate_workspace`; drop the pointer test + the authoring-standard requirement.
- **Priority**: P1 (blocks WP04) · **Independent test**: `pytest test_validate_workspace.py` green without privacy checks.
- **Subtasks**: T006, T007, T008, T009
- **Deps**: none · **Prompt**: [WP02](./tasks/WP02-retire-workspace-invariants.md) (~130 lines)

### WP03 — Clean-sweep the hygiene guards + inbox scripts (IC-07)
- **Goal**: Keep vault-path redaction + refuse-outside-inbox; DELETE the `_private` literal from operational code.
- **Priority**: P1 · **Independent test**: hygiene tests green with ≥ prior leak/refusal coverage; legit inbox path still allowed.
- **Subtasks**: T010, T011, T012, T013, T014
- **Deps**: none · **Prompt**: [WP03](./tasks/WP03-cleansweep-hygiene.md) (~160 lines)

### WP04 — Strip the red-line from agent prompts (IC-03, code only)
- **Goal**: Remove the enforceable `_private` line from all 7 agents' prompts (6 deployed + doc-auditor repo-only). Deploy is post-merge.
- **Priority**: P1 · **Independent test**: `validate_workspace` passes on every workspace without the line.
- **Subtasks**: T015, T016
- **Deps**: WP02 (validator must accept a prompt without the line first) · **Prompt**: [WP04](./tasks/WP04-strip-agent-prompts.md) (~110 lines)

### WP05 — Governance/instruction/constitution docs (IC-04)
- **Goal**: Remove the `_private` absolute rule from CLAUDE.md/CODEX.md/ai-agents/constitution; KEEP the general repo boundary.
- **Priority**: P2 · **Independent test**: docs no longer state the folder rule; repo-boundary guidance intact.
- **Subtasks**: T017, T018, T019
- **Deps**: none · **Prompt**: [WP05](./tasks/WP05-governance-docs.md) (~110 lines)

### WP06 — Design/architecture/runbook docs reframe (IC-05)
- **Goal**: Reframe docs that state the folder rule as a current guard to the physical-exclusion model.
- **Priority**: P2 · **Independent test**: no stale "absolute rule / enforces _private" claims; service-inventory.json well-formed.
- **Subtasks**: T020, T021, T022
- **Deps**: none · **Prompt**: [WP06](./tasks/WP06-design-runbook-docs.md) (~140 lines)

### WP07 — Graph-ingest model reframe (IC-06)
- **Goal**: Reframe the #692/#696 graph-ingest privacy model to "verify not present" (design/model only; runtime check out of scope).
- **Priority**: P2 · **Independent test**: no "never ingest _private" enforcement language; "verify not present" present.
- **Subtasks**: T023, T024
- **Deps**: none · **Prompt**: [WP07](./tasks/WP07-graph-ingest-reframe.md) (~90 lines)

## MVP / sequencing

WP01–WP03 (code) + WP04 (prompts, after WP02) are the functional core; WP05–WP07 are docs. All WPs
are independently reviewable. Post-merge acceptance (not a WP): office2 folder-absence re-check →
agent-prompt-sync deploy → 6-agent smoke → `drift_check.py` + `audit.sh` → SC-001..006 verification.
