# Implementation Plan: Capture AGENTS.md Rewrite (Directive-6 half-2)

**Branch**: `kitty/mission-capture-agents-md-rewrite-01KTMY86`
**Date**: 2026-06-08
**Spec**: [spec.md](./spec.md)

## Summary

Rewrite `scripts/openclaw/agents/felix-admin-capture/AGENTS.md` from 1,215 lines (52,942 chars) down to 250-400 lines (4,500-8,500 chars) by replacing deterministic Step 1-7 recipes with `python3 -m scripts.inbox.<helper>` invocations and trimming redundant prose. The 14 inbox helpers (8 existing + 6 from half-1) self-document via `--help` and module docstrings; the rewritten prompt only describes WHEN to invoke and HOW to interpret the output. LLM judgment surfaces (Output Discipline Hard Rules, ambiguous-block disambiguation, calendar clarification message authoring, goal declaration validation, edge cases, task delegation framing) STAY. The Step 5 invariant ("do NOT delete the original file") moves to the first 8,000 chars of the file so it survives openclaw's 12K bootstrap truncation cliff — though once the rewrite is in budget, truncation no longer fires.

## Technical Context

**Language/Version**: Markdown (the deliverable is a prompt file, not code). YAML frontmatter unchanged. Helper invocations in the prompt reference Python 3.10+ stdlib helpers shipped in half-1; no new code is written by this mission.
**Primary Dependencies**: The 14 helpers under `scripts/inbox/` (8 existing + 6 from half-1). No new third-party packages.
**Storage**: File system. Single file: `scripts/openclaw/agents/felix-admin-capture/AGENTS.md`. Optional one-line updates to `docs/design/architecture/data/service-inventory.json` for the doc-sync per DIR-005.
**Testing**: No new automated tests (this is a prompt rewrite, not a code change). Verification surfaces: (1) `wc -c` < 14,000 hard ceiling, (2) post-deploy `grep "bootstrap file AGENTS.md.*truncating"` returns no matches, (3) post-deploy MD5 parity. All 139 tests from half-1 STAY passing (regression sanity).
**Target Platform**: office2 (Ubuntu 24.04 LTS); the prompt is consumed by openclaw at session-init for each felix-admin-capture cron tick (7am / noon / 5pm / 10pm ET).
**Project Type**: Single project (kg-automation; agent prompts under `scripts/openclaw/agents/<slug>/`).
**Performance Goals**: openclaw bootstrap reads + injects the prompt in ≤500 ms (existing envelope). Structural win: NO truncation → Step 5 invariant becomes visible.
**Constraints**: Risk tier 3. No service/credential/data-flow changes. Existing helpers and sibling agent prompts STAY untouched (C-001, C-002).
**Scale/Scope**: One file rewrite + one JSON field update. Diff: net negative (~800 lines removed; ~250-350 lines remain).

## Charter Check

| Directive | Applicability | Status |
|---|---|---|
| **DIRECTIVE_001** Architectural Integrity | Rewrite cleanly separates judgment (prompt) from determinism (helpers). | PASS |
| **DIRECTIVE_010** Specification Fidelity | Plan maps to spec FRs with section-by-section structural map. | PASS |
| **DIRECTIVE_024** Locality of Change | One file in the agent dir; no cross-domain edits. | PASS |
| **DIRECTIVE_033** Targeted Staging Policy | Single-file commit + one-line JSON edit. | PASS |
| **DIRECTIVE_034** Test-First Development | No new code; existing helper tests (139) are the test surface. | PASS (n/a) |
| **DIR-005** Mission spec docs-sync | service-inventory.json `last_updated` + `updated_by`; no schema change. | PASS |
| **DIR-006** Probe real environment | Probed: current AGENTS.md section map (50+ sections); helper CLI signatures via `--help`. | PASS |

## Project Structure

### Documentation (this mission)

```
kitty-specs/capture-agents-md-rewrite-01KTMY86/
├── spec.md                # committed
├── plan.md                # this file
├── meta.json
├── research.md            # Phase 0 output (tight; narrow scope)
├── quickstart.md          # Phase 1 output (post-merge verification commands)
├── checklists/requirements.md  # committed
└── tasks/                 # populated by /spec-kitty.tasks
```

No data-model.md (no data structures introduced). No contracts/ (no new CLI surfaces). The structural map in spec.md IS the design contract.

### Source Code (repository root)

```
scripts/openclaw/agents/felix-admin-capture/AGENTS.md     # REWRITTEN (single file)
docs/design/architecture/data/service-inventory.json      # ONE-LINE UPDATE (last_updated + updated_by + notes)
```

The mission has the smallest source-code diff surface of any in this epic.

## Implementation Concern Map

### IC-01 — AGENTS.md rewrite

- **Purpose**: Rewrite the prompt per the structural map in spec.md. Drop deterministic recipes; keep judgment surfaces; ensure Step 5 invariant lands in the first 8,000 chars; reference helpers via `-m` form.
- **Relevant requirements**: FR-001..014, NFR-001..005, C-001..006
- **Affected surfaces**: `scripts/openclaw/agents/felix-admin-capture/AGENTS.md`
- **Dependencies**: none (half-1 helpers already live on office2)
- **Risks**:
  - **Voice drift**: rewritten prompt loses Kent's voice in compressed sections. Mitigation: preserve voice in judgment surfaces; drop voice in deterministic-recipe replacement spots.
  - **Invariant location**: Step 5 "do NOT delete" MUST land early (FR-004). Mitigation: reviewer verifies via `head -c 8000 AGENTS.md | grep -i "do NOT delete\|preserve"`.
  - **Helper invocation form**: per `[[feedback_helper_m_invocation_form]]` (TWO production incidents), every reference uses `-m scripts.inbox.<helper>` form. Mitigation: reviewer greps for any `python3 scripts/inbox/` (script-path form) — MUST return zero.
  - **Truncation regression**: rewriter accidentally adds new prose pushing over 14K. Mitigation: NFR-001 enforces hard ceiling; reviewer verifies `wc -c` ≤14,000.
  - **Existing helper invocation regression**: rewriter accidentally drops a reference to an EXISTING helper that current AGENTS.md does invoke. Mitigation: reviewer cross-checks all 14 helpers are still referenced where they were before (only ADD new helper references; don't remove existing ones unless the section itself is removed).

### IC-02 — Architecture documentation update

- **Purpose**: Update `service-inventory.json` `services[openclaw-gateway].agents.felix-admin-capture` entry: `last_updated` to today, `updated_by` prepends this mission, `notes` field reflects Step 5 invariant visibility + the helper-extraction structural pattern.
- **Relevant requirements**: FR-015 (operator verification), DIR-005
- **Affected surfaces**: `docs/design/architecture/data/service-inventory.json`
- **Dependencies**: IC-01 (docs reflect what was rewritten)
- **Risks**: JSON validation. Mitigation: `python3 -c "import json; json.load(open(...))"` post-edit.

## Parallel Opportunities

None — single-file mission. One WP, sequential implementation. IC-02 is a small JSON edit folded into the same WP.

## Reference Index

- Spec: [spec.md](./spec.md)
- Issue: kentonium3/kg-automation#566 (this mission closes)
- Predecessor mission: `capture-d6-helpers-extraction-01KTMS5Q` (helpers live on office2; verified)
- Memory references:
  - `[[feedback_helper_m_invocation_form]]` — `-m` form mandatory
  - `[[feedback_scripts_vs_llm]]` — Directive 6 split (this mission IS the canonical example)
  - `[[reference_openclaw_gotchas]]` — 12K bootstrap budget + ~26% inflation
  - `[[reference_office2_agent_deploy_paths]]` — felix-admin-capture → inbox-agent
  - `[[reference_felix_output_discipline_pattern]]` — Output Discipline Hard Rules (keep verbatim)
- Helper inventory: 8 existing + 6 from half-1; full list in spec.md § Domain Language
- Half-1 contracts (for invocation reference): `kitty-specs/capture-d6-helpers-extraction-01KTMS5Q/contracts/helper-cli.md`
