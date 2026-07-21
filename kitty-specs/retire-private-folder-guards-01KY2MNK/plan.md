# Implementation Plan: Retire _private folder guard apparatus

**Branch**: `feat/retire-private-folder-guards` | **Date**: 2026-07-21 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `kitty-specs/retire-private-folder-guards-01KY2MNK/spec.md`

## Summary

Remove the in-repo apparatus that guarded the now-physically-excluded `_private` folder (a
stale-path lint validator + its CI/pre-commit/Makefile/adapter wiring, the workspace-validator
privacy invariants, the enforceable red-line in every deployed agent prompt, and "absolute rule"
prose across governance/design/runbook docs). Keep and generalize the still-valuable general vault
hygiene (redact vault paths from alerts; refuse writes to arbitrary vault paths). Reframe the
graph-ingest privacy model to "verify not present". Behavior-preserving everywhere except the
deliberately removed folder guard. Technical approach: careful per-file classification (never a
blind sweep), pytest for the retained/generalized guards + validator self-tests, and deployment of
the cleaned agent prompts through the existing agent-prompt-sync path with a post-deploy smoke.

## Technical Context

**Language/Version**: Python 3.12 (scripts/, tests/, tooling/); Markdown + JSON (docs, agent
prompts, architecture data); YAML (CI workflow); bash (`.githooks/pre-commit`, `Makefile`).
**Primary Dependencies**: pytest (existing). No new dependencies. Touch points:
`scripts/openclaw/agents/validate_workspace.py`, `scripts/vault/resolver.py`,
`scripts/escalation/hard_fail.py`, `scripts/inbox/mark_processed.py`,
`tooling/scripts/validate_privacy_boundary.py`.
**Storage**: N/A. Artifacts are repo files plus the deployed agent prompts under
`/data/services/openclaw/data/` (main) and `/data/services/openclaw/*-agent/` on office2.
**Testing**: `pytest tests/` (unit); validator `--self-test`; office2 post-deploy agent smoke
(one message round-trip per affected agent). Retained-guard tests must stay green with ≥ the prior
number of leak/refusal assertions (NFR-003).
**Target Platform**: authored on macOS; runtime is office2 (Ubuntu 24.04, OpenClaw fleet).
**Project Type**: single project (Python + docs monorepo layout; no frontend/backend split).
**Performance Goals**: N/A — a removal/refactor; no runtime-performance surface.
**Constraints**: behavior-preserving except the removed folder guard (C-004); frozen/workflow-owned
surfaces off-limits (`docs/archive/`, `kitty-specs/`, `.kittify/` — C-001); agent-prompt changes
deploy via agent-prompt-sync, no new deploy manifest (C-003); rebaseline resolved per the
audited-surface protocol and confirmed against the live audit, not assumed (C-003).
**Scale/Scope**: ~30 live surfaces — 1 validator + 5 wiring points; 1 workspace validator (2
invariants + constants) + 2 tests; 7 agents × 1–4 prompt files each; ~20 docs (partial edits); 2
hygiene guards + their tests. Frozen archives / kitty-specs are explicitly excluded.

## Charter Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Activated directives (from `charter context --action plan`): DIRECTIVE_001 (architectural
integrity), DIRECTIVE_003 (decision documentation), DIRECTIVE_010 (spec fidelity), DIRECTIVE_024,
DIRECTIVE_031, DIRECTIVE_033, DIRECTIVE_034. Relevant charter section anchors: **Two Constitutions —
Don't Conflate**, **Change-Risk Taxonomy (Tier Protocol)**, **Rebaseline Obligation (Audited
Surfaces, #557)**.

- **Two Constitutions — Don't Conflate** — PASS with care. The Felix Constitution's *general*
  second-brain-repo boundary ("separate repo; don't write to it") is retained; only the
  folder-specific `_private` absolute rule is removed. The plan explicitly preserves the general
  boundary (C-002) and edits the constitution surgically (IC-04), not wholesale.
- **Change-Risk Taxonomy** — PASS. Highest tier touched is **Tier 3** (agent prompts = logic/
  workflow; deployed via the standard pull path). Docs are **Tier 4**. Removing a CI gate + local
  pre-commit hook is a governance/process change, not a Tier-0 host change — no UFW/sshd/sudoers/
  kernel/network-fabric surface is touched. No Tier-0/1/2 actions.
- **Rebaseline Obligation** — PASS with confirmation step. Agent prompts are a nominal audited
  surface, but `audit.sh` content-hashes `openclaw.json`, NOT prompt files (#621), so a rebaseline
  is expected **not-required** for these prompt edits. IC-08 confirms this against a live `audit.sh`
  run rather than assuming it; the merge records `Rebaseline: not required — <reason>` accordingly.
- **DIRECTIVE_003 (decision documentation)** — the physical-exclusion decision and the keep/remove/
  generalize split are recorded in the spec, this plan, and issue #848.

No charter violations to justify → Complexity Tracking is empty.

## Project Structure

### Documentation (this mission)

```
kitty-specs/retire-private-folder-guards-01KY2MNK/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output (surface inventory + keep/remove/generalize classification)
├── quickstart.md        # Phase 1 output (verification runbook)
└── tasks.md             # Phase 2 (/spec-kitty.tasks — NOT created here)
```

### Source Code (repository root)

```
tooling/scripts/validate_privacy_boundary.py        # REMOVE (IC-01)
.githooks/pre-commit                                 # EDIT: drop validator call (IC-01)
.github/workflows/docs-ci.yml                        # EDIT: drop "Validate privacy boundary lint" step (IC-01)
Makefile                                             # EDIT: drop validator target (IC-01)
.agents/autopilot/adapters/kg-automation.md          # EDIT: drop validator reference (IC-01)
docs/runbooks/local-test-gate.md                     # EDIT: drop validator mention (IC-01)

scripts/openclaw/agents/validate_workspace.py        # EDIT: remove Invariants A + D + constants (IC-02)
scripts/openclaw/agents/tests/test_validate_workspace.py  # EDIT: drop privacy-invariant tests (IC-02)
tests/openclaw/test_privacy_pointer.py               # REMOVE (IC-02)

scripts/openclaw/agents/{main,felix-admin-capture,felix-admin-escalation,felix-admin-habits,
  felix-admin-tasker,felix-admin-calendar,felix-doc-auditor}/{AGENTS,SOUL,TOOLS,USER}.md
                                                     # EDIT: remove enforceable red-line (IC-03) → deploy

CLAUDE.md, CODEX.md, ai-agents/{claude,claude-code,gemini}-instructions.md,
  docs/constitution/FELIX-CONSTITUTION.md            # EDIT: remove absolute rule, keep repo boundary (IC-04)

docs/design/architecture/{glossary,security-posture,service-inventory}.md + service-inventory.json,
  docs/design/{coherence/doctrine,openclaw-workspace-authoring-standard,felix-capability-roadmap}.md,
  docs/design/process-flows/{inbox-routing,journal}.md,
  docs/runbooks/{escalation-ops,habits-ops,inbox-ops,openclaw-agent-setup,tasker-ops}.md
                                                     # EDIT: reframe to physical exclusion (IC-05)

docs/design/second-brain-graph-layer.md, docs/design/executive-assistant-architecture.md
                                                     # EDIT: reframe #692/#696 gate to "verify not present" (IC-06)

scripts/escalation/hard_fail.py + tests/escalation/test_hard_fail.py,
  scripts/inbox/mark_processed.py + tests/inbox/test_mark_processed.py,
  scripts/inbox/{classify_content,prescan,route_and_finalize}.py + READMEs (per-file triage)
                                                     # KEEP+GENERALIZE (IC-07)
```

**Structure Decision**: single-project layout; no new modules. Changes are removals + surgical
edits to existing files, plus a deploy of already-existing prompt files.

## Complexity Tracking

*No charter violations — none.*

## Implementation Concern Map

> Concerns are architectural areas, not work packages. `/spec-kitty.tasks` maps them to WPs.

### IC-01 — Remove the stale-path lint validator + all wiring
- **Purpose**: The `validate_privacy_boundary.py` lint (a `02-Growth/_private` stale-path guard) is
  moot once the boundary is gone; remove it and every invocation so nothing calls a deleted script.
- **Relevant requirements**: FR-001, NFR-001, SC-002.
- **Affected surfaces**: `tooling/scripts/validate_privacy_boundary.py`, `.githooks/pre-commit`,
  `.github/workflows/docs-ci.yml`, `Makefile`, `.agents/autopilot/adapters/kg-automation.md`,
  `docs/runbooks/local-test-gate.md`.
- **Sequencing/depends-on**: none (but removing the CI step and the local hook together keeps gates
  self-consistent).
- **Risks**: leaving a dangling call to the deleted script red-fails pre-commit/CI. Remove the
  script and its callers in one change; verify a clean local commit + CI run.

### IC-02 — Retire the workspace-validator privacy invariants
- **Purpose**: `validate_workspace` should no longer force a `_private` red-line into every agent
  prompt; remove Invariant A (`check_privacy_boundary`), Invariant D (`check_privacy_path_canonical`),
  their constants/owner-set, and the registry-tie pointer test.
- **Relevant requirements**: FR-002.
- **Affected surfaces**: `scripts/openclaw/agents/validate_workspace.py`,
  `scripts/openclaw/agents/tests/test_validate_workspace.py`, `tests/openclaw/test_privacy_pointer.py`.
- **Sequencing/depends-on**: precede IC-03 (once the invariant is gone, prompts can drop the line
  without failing validation).
- **Risks**: must NOT weaken the validator's *other* invariants (output-discipline, staleness, byte
  budgets). Excise only the two privacy checks + their exclusive constants.

### IC-03 — Strip the red-line from deployed agent prompts + deploy
- **Purpose**: Remove the enforceable `_private` line from all 7 agents' prompt files and deploy the
  cleaned prompts to the running fleet.
- **Relevant requirements**: FR-003, NFR-004, SC-003.
- **Affected surfaces**: the 7 agent workspaces under `scripts/openclaw/agents/`; deploy via
  agent-prompt-sync; office2 `/data/services/openclaw/`. **Post-plan Codex LOW-1:** only the **6
  deployed** agents (main, capture, escalation, habits, tasker, calendar) get parity + smoke;
  **felix-doc-auditor is repo-only** (suspended #539; not in the agent-prompt-sync roster).
- **Sequencing/depends-on**: IC-02 (validation must accept a prompt without the line first).
- **Risks**: byte-budget floors on `main/AGENTS.md` (removing text only frees budget — safe);
  main's deploy dir is `/data/services/openclaw/data/` (slug≠dir); agent-prompt-sync copies IN
  (overwrites file content, so a stripped line IS removed on office2) but never deletes a whole file
  — a pure edit is fine. Post-deploy prompt parity + per-agent smoke + `drift_check.py report`
  (post-plan Codex LOW-2) required.

### IC-04 — Governance/instruction docs (partial edits)
- **Purpose**: Remove the `_private` "absolute rule" from CLAUDE.md/CODEX.md/ai-agents/constitution
  while KEEPING the general "second brain is a separate repo; don't write to it" boundary.
- **Relevant requirements**: FR-004, C-002.
- **Affected surfaces**: `CLAUDE.md`, `CODEX.md`, `ai-agents/{claude,claude-code,gemini}-instructions.md`,
  `docs/constitution/FELIX-CONSTITUTION.md`.
- **Sequencing/depends-on**: none.
- **Risks**: over-removal that deletes the still-valid repo boundary. Surgical, per-file edits.

### IC-05 — Design/architecture/runbook docs reframe
- **Purpose**: Reframe docs that state the folder rule as a *current enforced guard* to the
  physical-exclusion model.
- **Relevant requirements**: FR-005, SC-001.
- **Affected surfaces**: `docs/design/architecture/{glossary,security-posture,service-inventory}.md`
  + `service-inventory.json`, `docs/design/coherence/doctrine.md`,
  `docs/design/openclaw-workspace-authoring-standard.md`, `docs/design/felix-capability-roadmap.md`,
  `docs/design/process-flows/{inbox-routing,journal}.md`, `docs/runbooks/{escalation-ops,habits-ops,
  inbox-ops,openclaw-agent-setup,tasker-ops}.md`, plus `scripts/*/README.md` mentions.
- **Sequencing/depends-on**: none.
- **Risks**: `service-inventory.json` is validated by the arch-data validator — keep it well-formed.

### IC-06 — Graph-ingest model reframe (#692/#696)
- **Purpose**: Reframe the graph-ingest privacy model from "never ingest `_private`" enforcement to
  "verify the private content is not present" (physical exclusion). Design/model only; the runtime
  ingest check is out of scope (pipeline not built yet — #696).
- **Relevant requirements**: FR-006, SC-006.
- **Affected surfaces**: `docs/design/second-brain-graph-layer.md`,
  `docs/design/executive-assistant-architecture.md`.
- **Sequencing/depends-on**: none.
- **Risks**: keep the #696 gate description forward-consistent (a verification, not an in-repo rule).

### IC-07 — Keep + generalize general vault hygiene
- **Purpose**: Retain vault-path redaction and refuse-out-of-inbox-writes, decoupled from the defunct
  folder. **Post-plan Codex reclassification:** `classify_content` (exit-3 pre-read refusal) and
  `prescan` (skip `_private` path components) are LIVE general hygiene, not doc-triage → KEEP+GEN
  (never process private-marked content, folder-agnostic).
- **Relevant requirements**: FR-007, NFR-003, FR-008 (leave the unrelated Vikunja `is_private`).
- **Affected surfaces**: `hard_fail.py` (redaction — MED-1: keep the exact fragment set
  `~/second-brain`,`/second-brain`,`_private`), `mark_processed.py` (MED-1: refuse OUTSIDE the
  resolved inbox root — NOT "any vault path", or the legitimate `01-Inbox` would be rejected;
  inbox-root allow semantics preserved), `classify_content.py` + `prescan.py` (KEEP+GEN),
  `route_and_finalize.py` (doc triage) + their tests. Do NOT touch `tests/common/test_sync_cache.py`
  (`is_private` = Vikunja, unrelated).
- **Sequencing/depends-on**: none.
- **Risks**: (a) over-generalizing `mark_processed` into rejecting the inbox root (MED-1); (b)
  dropping a redaction fragment `hard_fail` currently catches (MED-1); (c) leaving literal
  `04-Growth` coupling behind. Keep ≥ prior coverage (NFR-003, INV-4).

### IC-08 — Verification, ordering-safety & rebaseline confirmation
- **Purpose**: Prove the safety invariant and green gates; confirm rebaseline disposition.
- **Relevant requirements**: NFR-001, NFR-002, C-003, SC-001..005.
- **Affected surfaces**: office2 (folder-absence re-check, agent smoke, `audit.sh` run), local +
  CI gates, the SC-001 residual-reference grep.
- **Sequencing/depends-on**: last.
- **Risks**: none new; this is the acceptance gate.
