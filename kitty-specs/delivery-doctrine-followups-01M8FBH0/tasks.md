# Tasks: Delivery-doctrine follow-ups (#1146)

**Mission**: delivery-doctrine-followups-01M8FBH0 · **Spec**: [spec.md](spec.md) · **Plan**: [plan.md](plan.md)
**Branches**: planning on `kitty/mission-delivery-doctrine-followups-01M8FBH0`, landing on `fix/1146-delivery-doctrine-followups`. Execution worktrees are allocated per computed lane (`lanes.json`).

## Subtask Index

| ID | Description | WP | Parallel |
|----|-------------|----|----------|
| T001 | Red tests: each FR-001 false-negative form is flagged | WP01 | |
| T002 | Red tests: each FR-002 false-positive form passes, with same-fixture positive controls and clause-scope negative controls | WP01 | |
| T003 | Remainder normalisation (paired delimiters, clause boundaries) | WP01 | |
| T004 | New and widened patterns; clause-scoped exemptions (final-reply narrowed, negation, field mention, prose) | WP01 | |
| T005 | Retry-rule tail in the canonical block, the 3 announce AGENTS.md copies and the pinning test; size caps | WP01 | |
| T006 | Determinism and speed check (NFR-003); half-by-half proof; full suite | WP01 | |
| T007 | Rewrite escalation SKILL.md §7 to the real JSONL dedup | WP02 | [P] |
| T008 | Committed announce-agent → skills mirror | WP02 | |
| T009 | Skill-coverage test: guard in skill mode over every mirrored skill, with a positive control | WP02 | |
| T010 | Confirm the sync path and the guard-clean state of edited skills | WP02 | |
| T011 | Find a read-only way to list an agent's effective tool catalog on office2 | WP03 | [P] |
| T012 | Deploy entrypoint `deploy-announce-agent-tool-deny.py` (dry-run/apply, refusals, recovery receipt, patch, validate, read-back, reload and PID checks) | WP03 | |
| T013 | Entrypoint tests; migrate `openclaw-sample.json` to `agents.entries` and update `test_openclaw_config_schema.py` | WP03 | |
| T014 | Queued manifest `announce-agent-tool-deny.yaml` (Tier 2, verification, expected_baselines, recovery notes); schema-validated | WP03 | |
| T015 | `scripts/deploy/lib/README.md`: config-patch pattern note | WP03 | |
| T016 | Service inventory (json and md): announce agents' tool deny | WP04 | [P] |
| T017 | `openclaw-agent-setup.md`: announce-agent tool policy | WP04 | [P] |
| T018 | `deploy/discipline.md`: manifest-driven `openclaw.json` edit pattern and scoped rollback | WP04 | |
| T019 | `security-posture.md`; review the remaining doc-map targets; run validators | WP04 | |

## Work Packages

### WP01 — Guard coverage and retry-rule wording ([WP01-guard-coverage-and-retry-wording.md](tasks/WP01-guard-coverage-and-retry-wording.md))

**Goal**: the wording guard classifies every reviewed phrase correctly, and every announce prompt carries the revised retry rule. **Priority**: P1. **Requirements**: FR-001, FR-002, FR-003, NFR-001, NFR-002, NFR-003.
**Independent test**: `pytest scripts/openclaw/agents/tests/test_delivery_doctrine.py`. Every new case fails against the pre-fix module and passes after.

T001 Red tests: each FR-001 false-negative form is flagged (WP01)
T002 Red tests: FR-002 false positives pass, with positive and negative controls (WP01)
T003 Remainder normalisation (WP01)
T004 Patterns and clause-scoped exemptions (WP01)
T005 Retry-rule tail across the block, 3 AGENTS.md copies and the pinning test (WP01)
T006 NFR-003 check, half-by-half proof, full suite (WP01)

**Sketch**: tests first (T001, T002) → normalise (T003) → patterns and exemptions (T004) → wording (T005) → proof (T006).
**Dependencies**: none. **Risks**: the block's byte-exact count; exemption over-reach; escalation headroom (120 → 95).

### WP02 — Skill wording and skill coverage ([WP02-skill-wording-and-coverage.md](tasks/WP02-skill-wording-and-coverage.md))

**Goal**: the escalation skill's dedup text is true, and no skill an announce agent reads can reintroduce a send path. **Priority**: P2. **Requirements**: FR-004, FR-005, SC-003.
**Independent test**: `pytest scripts/openclaw/agents/tests/test_announce_skill_coverage.py`.

T007 Escalation SKILL.md §7 dedup rewrite (WP02)
T008 Announce agent → skills mirror (WP02)
T009 Skill-coverage test with a positive control (WP02)
T010 Sync path and guard-clean confirmation (WP02)

**Dependencies**: WP01, because the coverage test must use the improved guard. **Risks**: the mirror drifting from live config (re-checked in the canary).

### WP03 — Announce-agent tool deny deploy ([WP03-announce-agent-tool-deny-deploy.md](tasks/WP03-announce-agent-tool-deny-deploy.md))

**Goal**: a reversible, recorded, Tier 2 deploy that denies `conversations_*`, `sessions_*`, `message` and `automations` to the three announce agents in office2's live config, changing nothing else. **Priority**: P2. **Requirements**: FR-006, FR-007, C-001, C-002, SC-002, SC-004.
**Independent test**: `pytest tests/deploy/test_announce_agent_tool_deny.py scripts/openclaw/agents/tests/test_openclaw_config_schema.py`, plus manifest schema validation and an entrypoint `--dry-run` against the fixture.

T011 Read-only effective-catalog listing method (WP03)
T012 Deploy entrypoint (WP03)
T013 Entrypoint tests; fixture migration (WP03)
T014 Queued manifest (WP03)
T015 Deploy library README note (WP03)

**Dependencies**: none. **Risks**: Gateway write semantics (arrays replace); hot reload; the CLI PATH under felix-deployer; rollback re-application.

### WP04 — Architecture and runbook docs ([WP04-architecture-and-runbook-docs.md](tasks/WP04-architecture-and-runbook-docs.md))

**Goal**: the docs the signal-to-doc map names for agent-prompt-changed and deploy-manifest-added describe the new state. **Priority**: P3. **Requirements**: FR-007.
**Independent test**: `validate_docs.py`, `validate_architecture_data.py --strict` and `generate_doc_standards.py --check` all pass.

T016 Service inventory (WP04)
T017 openclaw-agent-setup.md (WP04)
T018 deploy/discipline.md (WP04)
T019 security-posture.md; review the other targets; validators (WP04)

**Dependencies**: WP03, because the docs describe its entrypoint and manifest names. **Risks**: none significant.

## Parallelisation

WP01 and WP03 can run in parallel. WP02 follows WP01, and WP04 follows WP03. MVP: WP01 (it closes the live guard bypass Codex found).

## Post-merge (not a WP)

The operator canary in `quickstart.md` (SC-002, SC-004), recorded on #1146 after the PR merges to `main`.
