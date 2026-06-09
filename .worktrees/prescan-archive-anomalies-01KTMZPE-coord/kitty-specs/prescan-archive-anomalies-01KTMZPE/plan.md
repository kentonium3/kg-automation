# Implementation Plan: Prescan Archive Anomalies Check

**Branch**: `kitty/mission-prescan-archive-anomalies-01KTMZPE`
**Date**: 2026-06-08
**Spec**: [spec.md](./spec.md)

## Summary

Extend `scripts/inbox/prescan.py` with a `scan_archive_anomalies(processed_dir, now_utc)` function that returns one `ArchiveAnomaly` per file in `02-Inbox-Processed/` whose frontmatter `status` is anything other than `processed`. Add the result as a new `archive_anomalies` field on `PrescanResult`. Bounded scan (cap 5,000 files by mtime) protects latency. Daily logs (`inbox-processing-*.md`) are filtered. Daily log surface gains a `### archive_anomalies (count=N)` section when non-empty; stderr summary gains `archive_anomalies=N`. Read-only — no remediation. Closes #568. Closes epic #563.

## Technical Context

**Language/Version**: Python 3.10+ (matches existing prescan.py).
**Primary Dependencies**: Standard library only — `pathlib`, `dataclasses`, `datetime`, `os.stat` for mtime. Reuses existing internals from prescan.py: `classify_file()`, `_extract_frontmatter_block()`, `InboxFile`. NO third-party additions.
**Storage**: File system read-only against `02-Inbox-Processed/`. The existing prescan writes daily logs under `~/second-brain/agents/logs/inbox-prescan-*.md`; this mission extends that surface additively.
**Testing**: pytest + pytest-cov. Tests added to existing `tests/scripts/inbox/test_prescan.py`. Fixtures under `tests/inbox/fixtures/` (new fixtures per anomaly scenario). Coverage gate: ≥90% line / ≥85% branch on `scripts.inbox.prescan` via `pytest --cov=scripts.inbox.prescan --cov-branch --cov-fail-under=90`.
**Target Platform**: office2 (Ubuntu 24.04 LTS); the helper runs on each felix-admin-capture cron tick.
**Project Type**: Single project (kg-automation).
**Performance Goals**: NFR-001 — full prescan completes in <2s for typical inputs (≤5,000 archive files). Bounded scan caps growth.
**Constraints**: Risk tier 3. Stdlib-only (NFR-002). Read-only against archive (C-002, FR-011).
**Scale/Scope**: Single file extension (~50-80 new LOC) + new dataclass + ~10-15 new test cases.

## Charter Check

| Directive | Applicability | Status |
|---|---|---|
| **DIRECTIVE_001** Architectural Integrity | Additive extension to existing helper; no API breakage. | PASS |
| **DIRECTIVE_010** Specification Fidelity | Plan maps to 15 FRs in spec.md. | PASS |
| **DIRECTIVE_024** Locality of Change | `scripts/inbox/prescan.py` + matching test file + one JSON `purpose` update. | PASS |
| **DIRECTIVE_033** Targeted Staging Policy | Single-file extension + single test file + one JSON edit. | PASS |
| **DIRECTIVE_034** Test-First Development | Test scaffolding written first; production code implements to pass. Coverage gate enforced. | PASS |
| **DIR-005** Mission spec docs-sync | `service-inventory.json` `purpose` field updated for the `inbox-prescan-helper` component. | PASS |
| **DIR-006** Probe real environment | Probed: existing prescan.py structure (778 lines, 30+ functions), classify_file() signature, PrescanResult dataclass, ArchiveResult dataclass, test_prescan.py location (tests/scripts/inbox/), fixtures dir. | PASS |

## Project Structure

### Documentation (this mission)

```
kitty-specs/prescan-archive-anomalies-01KTMZPE/
├── spec.md            # committed
├── plan.md            # this file
├── meta.json
├── checklists/requirements.md   # committed
└── tasks/             # populated by /spec-kitty.tasks
```

No data-model.md (the dataclass is documented in spec.md). No contracts/ (no new CLI surface). No quickstart.md (the helper is invoked the same way as today).

### Source Code (repository root)

```
scripts/inbox/prescan.py                # EXTEND (~50-80 LOC added)
tests/scripts/inbox/test_prescan.py     # EXTEND (~10-15 new tests)
tests/inbox/fixtures/                   # ADD a few new fixture files
docs/design/architecture/data/service-inventory.json  # one-line `purpose` update
```

## Implementation Concern Map

### IC-01 — Archive scan + ArchiveAnomaly emission

- **Purpose**: New `scan_archive_anomalies()` function + new `ArchiveAnomaly` dataclass. Iterates `.md` files in `processed_dir`; filters `inbox-processing-*.md` daily logs; applies existing `classify_file()`; emits one anomaly per non-`processed` status.
- **Relevant requirements**: FR-001..005, FR-014
- **Affected surfaces**: `scripts/inbox/prescan.py`
- **Dependencies**: none (reuses existing `classify_file()`)
- **Risks**: classify_file's signature might not expose `status_raw` directly. Probe before implementing — InboxFile dataclass may need a `status_raw` getter or the function may return it inline.

### IC-02 — Bounded scan (cap) + missing-dir safety

- **Purpose**: When archive has >5,000 files: sort by mtime descending, take top 5,000, add cap warning. When archive dir is missing: return [] + add warning.
- **Relevant requirements**: FR-006, FR-012, FR-013
- **Affected surfaces**: `scripts/inbox/prescan.py` (inside `scan_archive_anomalies()`)
- **Dependencies**: IC-01
- **Risks**: mtime sort on 5,000 files adds latency. Mitigation: NFR-001's <2s threshold is enforced; benchmark in T002.

### IC-03 — PrescanResult integration + log/stderr surfaces

- **Purpose**: Add `archive_anomalies` field to `PrescanResult` dataclass. Wire `run_prescan()` to call the new scan + populate the field. Daily log gets `### archive_anomalies (count=N)` section when non-empty. Stderr summary gains `archive_anomalies=N`.
- **Relevant requirements**: FR-007..010
- **Affected surfaces**: `scripts/inbox/prescan.py` (PrescanResult, _append_daily_log, _emit_stderr / run_prescan stderr)
- **Dependencies**: IC-01
- **Risks**: Existing log format consumers (humans reading) need the section to be ABSENT on healthy ticks (avoid noise). Confirmed in FR-009.

### IC-04 — Architecture doc-sync

- **Purpose**: Update `service-inventory.json` `inbox-prescan-helper` `purpose` to add a sentence about archive-anomaly detection. Bump `updated_at` + prepend mission to `updated_by`. Top-level `last_updated` + `updated_by` bumped.
- **Relevant requirements**: spec § Architecture Documentation Updates, DIR-005
- **Affected surfaces**: `docs/design/architecture/data/service-inventory.json`
- **Dependencies**: IC-01..03 (docs reflect what was built)
- **Risks**: JSON validation. Mitigation: `python3 -c "import json; json.load(open(...))"`.

## Parallel Opportunities

None — single-file extension. One WP, sequential.

## Reference Index

- Spec: [spec.md](./spec.md)
- Issue: kentonium3/kg-automation#568 (this mission closes)
- Parent epic: kentonium3/kg-automation#563 (closes when this lands)
- Sibling missions: `capture-d6-helpers-extraction-01KTMS5Q` + `capture-agents-md-rewrite-01KTMY86` (both closed)
- Memory references: `[[feedback_signal_driven_doc_audit]]`, `[[feedback_helper_m_invocation_form]]`, `[[reference_speckitty_3_2_rc41_quirks]]`, `[[project_epic_563_status]]`
- Existing surfaces:
  - `scripts/inbox/prescan.py` (778 lines; this mission adds ~80)
  - `tests/scripts/inbox/test_prescan.py` (this mission adds ~10-15 tests)
  - `tests/inbox/fixtures/` (this mission adds ~5 new fixtures)
- Mission #185 introduced parse-failure handling + dedup substrate; this mission's archive scan reuses `classify_file()` from that surface.
