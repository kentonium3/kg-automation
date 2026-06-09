# Implementation Plan: Capture Directive-6 Helpers Extraction

**Branch**: `kitty/mission-capture-d6-helpers-extraction-01KTMS5Q`
**Date**: 2026-06-08
**Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `kitty-specs/capture-d6-helpers-extraction-01KTMS5Q/spec.md`

## Summary

Ship six new stdlib Python helpers under `scripts/inbox/` that the follow-on AGENTS.md rewrite (separate mission) will invoke. Each helper is a focused, single-purpose script: `mark_processed` (atomic frontmatter mutation), `route_journal_entry` (append to dated journal), `route_someday` (Vikunja Someday task), `route_calendar_event` (validate + emit normalized payload), `handle_clarification_state` (24h pending-clarification state file), `classify_content` (deterministic per-block classification with LLM-judgment flagging for ambiguous tokens). Each invokable via `python3 -m scripts.inbox.<module>`. No modification to existing helpers in `scripts/inbox/`. No modification to capture's AGENTS.md.

## Technical Context

**Language/Version**: Python 3.10+ (matches office2 system python at `/usr/bin/python3`; matches existing scripts/inbox/ helpers)
**Primary Dependencies**: Standard library only — `pathlib`, `argparse`, `json`, `re`, `os`, `datetime`, `sys`, `subprocess` (sweep timing). PLUS existing internal modules: `scripts.common.vikunja_client.VikunjaClient` (for `route_someday`), `scripts.calendar_routing.validate_calendar_event` (for `route_calendar_event`), `scripts.vault.paths` (for journal path lookup). NO new third-party packages.
**Storage**: File system only.
  - Read: `~/second-brain/notes/01-Inbox/<note>.md` (handled by `mark_processed`, `classify_content`); existing notes' frontmatter and body
  - Write: `~/second-brain/notes/08-Journal/Journal YYYY-MM-DD HHmm.md` (handled by `route_journal_entry`); `~/second-brain/agents/state/pending-calendar-clarifications.json` (handled by `handle_clarification_state`)
  - Read-only: `scripts/vault/paths.json` (path lookup table)
  - Network: Vikunja API via shared client (`route_someday` only)
**Testing**: pytest with pytest-cov. Tests under `tests/inbox/test_<helper>.py`. Coverage gate per helper: ≥90% line, ≥85% branch via `pytest --cov=scripts.inbox.<helper> --cov-branch --cov-fail-under=90`. Same `tmp_path` + `conftest.py` fixtures as existing inbox tests. No Vikunja network in tests (mock the client per existing precedent).
**Target Platform**: office2 (Ubuntu 24.04 LTS) as production; macOS for development. Both run the same `python3 -m scripts.inbox.<helper>` invocation form.
**Project Type**: Single project (kg-automation; scripts under `scripts/`, tests under `tests/`).
**Performance Goals**: Per NFR-001 — each helper completes in <500 ms for typical inputs. Steady-state agent ticks invoke 1-2 route helpers + mark_processed + classify_content per note; <2s total per note.
**Constraints**: No third-party deps (NFR-002), no private-growth path (C-001), Vikunja create endpoint only (C-006), no AGENTS.md mutation (FR-013), no existing-helper modification (FR-012).
**Scale/Scope**: 6 new helper files + 6 new test files + 6 component entries in `service-inventory.json`. ~150-300 LOC per helper; ~200-400 LOC per test file. Total mission: ~2500-3500 LOC across 13 files.

## Charter Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Directive | Applicability | Status |
|---|---|---|
| **DIRECTIVE_001** Architectural Integrity | Each helper is a focused single-purpose module with a clear CLI surface and exit-code contract. No cross-helper coupling beyond shared imports. | PASS |
| **DIRECTIVE_010** Specification Fidelity | Plan maps each FR directly to a helper module + its test file. No drift between intent and implementation surface. | PASS |
| **DIRECTIVE_024** Locality of Change | All new code lives under `scripts/inbox/` + `tests/inbox/` + one service-inventory entry. No cross-domain reach. | PASS |
| **DIRECTIVE_033** Targeted Staging Policy | Each WP commits only its own helper + tests + any per-WP arch-doc updates. Enforced at WP boundaries. | PASS |
| **DIRECTIVE_034** Test-First Development | Each WP writes its test scaffolding first, then the production helper to pass the tests. Coverage gate ≥90% line / ≥85% branch is the verification surface. | PASS |
| **DIR-005** Mission spec docs-sync requirement | Spec § Architecture Documentation Updates lists the service-inventory.json + signal-to-doc-map.json + runbook surfaces. | PASS |
| **DIR-006** Probe real environment during design | Probed `scripts/inbox/`, `scripts/common/`, `scripts/calendar_routing/`, `scripts/vault/paths.json`, `tests/inbox/`, and the `~/second-brain/` path layout before authoring this plan. | PASS |

No gate violations. Complexity Tracking section intentionally empty.

## Project Structure

### Documentation (this mission)

```
kitty-specs/capture-d6-helpers-extraction-01KTMS5Q/
├── spec.md                # Committed
├── plan.md                # This file
├── meta.json              # Identity
├── research.md            # Phase 0 output (concise; mission scope is narrow)
├── data-model.md          # Phase 1 output (Block + ClassificationOutput + PendingClarification shapes)
├── quickstart.md          # Phase 1 output (operator invocation examples)
├── contracts/
│   └── helper-cli.md      # Per-helper CLI contracts (consolidated)
├── checklists/
│   └── requirements.md    # Committed
└── tasks/                 # Populated by /spec-kitty.tasks
```

### Source Code (repository root)

```
scripts/inbox/                                # EXISTS; new files added
├── __init__.py                               # EXISTS (no change)
├── mark_processed.py                         # NEW (WP01)
├── route_journal_entry.py                    # NEW (WP02)
├── route_someday.py                          # NEW (WP03)
├── route_calendar_event.py                   # NEW (WP04)
├── handle_clarification_state.py             # NEW (WP05)
├── classify_content.py                       # NEW (WP06)
└── (existing 8 helpers untouched)

tests/inbox/                                  # EXISTS; new test files added
├── conftest.py                               # EXISTS (no change)
├── fixtures/                                 # EXISTS; new fixtures added per helper
├── test_mark_processed.py                    # NEW (WP01)
├── test_route_journal_entry.py               # NEW (WP02)
├── test_route_someday.py                     # NEW (WP03)
├── test_route_calendar_event.py              # NEW (WP04)
├── test_handle_clarification_state.py        # NEW (WP05)
├── test_classify_content.py                  # NEW (WP06)
└── (existing test files untouched)

docs/design/architecture/data/                # MODIFY
└── service-inventory.json                    # Extend felix-admin-capture.components with 6 new entries (WP07 doc-sync)
```

**Structure Decision**: Each helper gets its own WP. Six helpers × (test scaffold + impl + coverage gate) = 6 implementation WPs. A seventh WP (WP07) handles the architecture-doc sync. Each helper's `owned_files` is its own file + its own test file — zero overlap, enabling **parallel implementation** (the natural Workflow opportunity). WP07 has no dependencies on WPs 1-6 but should land last so the arch doc accurately reflects what was actually built.

## Complexity Tracking

*Empty — no Charter Check violations.*

## Implementation Concern Map

### IC-01 — `mark_processed.py`

- **Purpose**: Atomic frontmatter write of `status: processed` + `processed_at`. Idempotent on already-processed notes. Preserves file location.
- **Relevant requirements**: FR-001, FR-002, FR-010
- **Affected surfaces**: `scripts/inbox/mark_processed.py`, `tests/inbox/test_mark_processed.py`
- **Sequencing/depends-on**: none (foundational)
- **Risks**: YAML frontmatter parsing without `python-frontmatter` dep — must hand-roll a minimal parser (per NFR-002 stdlib-only). Mitigation: use the same regex-based parser as existing `scripts/inbox/handle_marker_cleanup.py` (verified in `tests/inbox/test_handle_marker_cleanup.py`).

### IC-02 — `route_journal_entry.py`

- **Purpose**: Append content to `08-Journal/Journal YYYY-MM-DD HHmm.md`. Create file if absent with correct frontmatter.
- **Relevant requirements**: FR-003, FR-010, FR-011
- **Affected surfaces**: `scripts/inbox/route_journal_entry.py`, `tests/inbox/test_route_journal_entry.py`
- **Sequencing/depends-on**: none
- **Risks**: Journal filename includes a timestamp; race condition if two ticks try to create the same minute's file. Mitigation: `os.makedirs(exist_ok=True)` + create-if-absent pattern; the append step is atomic.

### IC-03 — `route_someday.py`

- **Purpose**: Create Vikunja task in the Someday project via the shared client.
- **Relevant requirements**: FR-004, C-003, C-006
- **Affected surfaces**: `scripts/inbox/route_someday.py`, `tests/inbox/test_route_someday.py`
- **Sequencing/depends-on**: none (consumes existing `scripts.common.vikunja_client.VikunjaClient`)
- **Risks**: Project-name resolution to project ID — must use the existing Vikunja client's resolve-by-name pattern, NOT a hard-coded ID. Mitigation: existing tests cover this in `tests/common/test_vikunja_client.py` (precedent).

### IC-04 — `route_calendar_event.py`

- **Purpose**: Validate calendar payload via existing `scripts.calendar_routing.validate_calendar_event`; emit normalized JSON on stdout; exit non-zero on invalid.
- **Relevant requirements**: FR-005, FR-009
- **Affected surfaces**: `scripts/inbox/route_calendar_event.py`, `tests/inbox/test_route_calendar_event.py`
- **Sequencing/depends-on**: none (consumes existing validator)
- **Risks**: validator API might be slightly different from what spec.md assumes. Mitigation: probe the actual `validate_calendar_event` signature during WP04 implementation (per `[[feedback_design_phase_research]]` lesson from #567).

### IC-05 — `handle_clarification_state.py`

- **Purpose**: Three subcommands (add / sweep / match) operating on `~/second-brain/agents/state/pending-calendar-clarifications.json`. Safe on missing state file.
- **Relevant requirements**: FR-006, FR-015, FR-010
- **Affected surfaces**: `scripts/inbox/handle_clarification_state.py`, `tests/inbox/test_handle_clarification_state.py`
- **Sequencing/depends-on**: none
- **Risks**: 24h aging logic needs reliable time source (UTC ISO 8601). Mitigation: `datetime.now(timezone.utc)` and explicit timezone in fixtures.

### IC-06 — `classify_content.py`

- **Purpose**: Block-based deterministic classification with LLM-flag for ambiguous tokens.
- **Relevant requirements**: FR-007, FR-014
- **Affected surfaces**: `scripts/inbox/classify_content.py`, `tests/inbox/test_classify_content.py`
- **Sequencing/depends-on**: none
- **Risks**: This is the most judgment-adjacent helper. Classification heuristics need to cover real Kent-content shapes (voice-captured notes with mixed topics). Mitigation: build fixture suite from real inbox shapes (anonymized); document heuristics inline per FR-014.

### IC-07 — Architecture documentation sync

- **Purpose**: Extend `services[openclaw-gateway].agents.felix-admin-capture.components` with 6 new entries. Bump `updated_by`.
- **Relevant requirements**: spec § Architecture Documentation Updates, DIR-005
- **Affected surfaces**: `docs/design/architecture/data/service-inventory.json` (and `docs/runbooks/inbox-ops.md` if a brief mention fits — but defer full operator content to the follow-on AGENTS.md mission)
- **Sequencing/depends-on**: WPs 1-6 (docs accurately reflect what was actually built)
- **Risks**: JSON schema is rich; malformed addition fails CI. Mitigation: copy structure verbatim from the existing `components` array entries (e.g., `inbox-prescan-helper`).

## Parallel Opportunities

**WPs 1-6 have zero `owned_files` overlap** — each WP owns its helper file + its test file. They can implement in PARALLEL. This is the Workflow fan-out opportunity: spawn 6 implementing agents simultaneously, each working in a different lane worktree on independent files.

WP07 depends on 1-6 and runs sequentially after.

## Reference Index

- Spec: [spec.md](./spec.md)
- Issue: kentonium3/kg-automation#566 (helpers half)
- Memory references: `[[feedback_helper_m_invocation_form]]`, `[[feedback_scripts_vs_llm]]`, `[[feedback_speckitty_split_code_and_deploy_missions]]`, `[[feedback_vikunja_post_partial_replace]]`, `[[feedback_design_phase_research]]`
- Existing precedents:
  - Atomic write: `scripts/inbox/inject_parse_error_marker.py` + `tests/inbox/test_atomic_write_perms.py`
  - Frontmatter parsing: `scripts/inbox/handle_marker_cleanup.py`
  - CLI shape: `scripts/inbox/append_routing_entry.py`
  - Vikunja client usage: `scripts/common/vikunja_client.py` (consumers: many)
  - Calendar validation: `scripts/calendar_routing/validate_calendar_event.py`
  - Test patterns: `tests/inbox/test_classifier_regression.py`, `tests/inbox/test_handle_parse_failures.py`
- Architecture: `docs/design/architecture/data/service-inventory.json` § `services[openclaw-gateway].agents.felix-admin-capture.components` array
