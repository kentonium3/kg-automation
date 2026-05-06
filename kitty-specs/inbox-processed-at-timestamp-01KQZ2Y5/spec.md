# Inbox Processed-At Timestamp

**Mission**: inbox-processed-at-timestamp-01KQZ2Y5
**Source**: GitHub issue #187
**Status**: Draft
**Created**: 2026-05-06

## Overview

When the inbox processor marks a note as `status: processed`, it records no timestamp of when processing occurred. The only temporal signal is filesystem mtime, which resets on any subsequent edit and is not queryable from within Obsidian or by scripts reading frontmatter. This feature adds a `processed_at` frontmatter field written at processing time, and updates the prescan classifier to prefer it for staleness calculations.

## Actors

- **felix-admin-capture agent** (OpenClaw) — writes frontmatter during inbox processing
- **prescan.py script** — classifies inbox files by status and age for archival decisions
- **Kent** (Obsidian user) — reads processed_at in frontmatter for temporal context

## User Scenarios & Testing

### Scenario 1: New inbox file processed

1. An inbox note arrives with `status: unprocessed`
2. felix-admin-capture processes all content blocks successfully
3. Agent sets `status: processed` and `processed_at: 2026-05-06T12:30:00-04:00` (agent's local timezone, ISO 8601)
4. Kent opens the note in Obsidian and can see when it was processed

### Scenario 2: Prescan classifies a newly processed file

1. prescan.py reads a file with `status: processed` and `processed_at: 2026-05-06T12:30:00-04:00`
2. Prescan calculates age from `processed_at`, not filesystem mtime
3. File is classified as `processed-recent` (within 7-day threshold)

### Scenario 3: Prescan classifies a legacy file without processed_at

1. prescan.py reads a file with `status: processed` but no `processed_at` field
2. Prescan falls back to filesystem mtime for age calculation
3. Classification proceeds as before (backward compatible)

### Scenario 4: File marked needs-review

1. felix-admin-capture cannot classify all content blocks
2. Agent sets `status: needs-review` but does NOT write `processed_at`
3. `processed_at` is only written on successful full processing

## Functional Requirements

| ID | Requirement | Status |
|----|-------------|--------|
| FR-01 | When the inbox processor sets `status: processed`, it must also write a `processed_at` field with the current timestamp in ISO 8601 format using the agent's local timezone | Proposed |
| FR-02 | `processed_at` must NOT be written when status is set to `needs-review` | Proposed |
| FR-03 | `processed_at` is written once at processing time and not updated on subsequent file touches | Proposed |
| FR-04 | prescan.py `classify_file()` must prefer the `processed_at` frontmatter field for age calculation when the field is present | Proposed |
| FR-05 | prescan.py must fall back to filesystem mtime when `processed_at` is absent (legacy backward compatibility) | Proposed |

## Non-Functional Requirements

| ID | Requirement | Threshold | Status |
|----|-------------|-----------|--------|
| NFR-01 | Timestamp must be human-readable in Obsidian without conversion | ISO 8601 with local timezone offset (e.g. `2026-05-06T12:30:00-04:00`) | Proposed |

## Constraints

| ID | Constraint | Status |
|----|------------|--------|
| C-01 | No changes to the `status` field values or lifecycle | Active |
| C-02 | No backfilling of `processed_at` on already-processed legacy files | Active |
| C-03 | No timestamps for other status transitions (e.g. `needs-review`) | Active |

## Assumptions

- The felix-admin-capture agent can write ISO 8601 timestamps to YAML frontmatter (standard YAML capability)
- office2 system timezone is UTC; the agent's "local timezone" is whatever the system reports
- Existing processed files without `processed_at` will continue to work unchanged
- The 7-day staleness threshold in prescan.py remains unchanged

## Key Entities

| Entity | Field | Type | Description |
|--------|-------|------|-------------|
| Inbox note frontmatter | `processed_at` | string (ISO 8601) | Timestamp when the note was fully processed, in agent's local timezone |

## Success Criteria

- Newly processed inbox files contain a `processed_at` field that Kent can read in Obsidian to know when processing occurred
- Files marked `needs-review` do not contain `processed_at`
- Prescan staleness classification produces correct results using `processed_at` when present
- Legacy files without `processed_at` continue to classify correctly via mtime fallback

## Out of Scope

- Backfilling `processed_at` on already-processed legacy files
- Changing the `status` field values or lifecycle
- Adding timestamps for other status transitions
- Modifying the 7-day staleness threshold

## Risk Considerations

- **Risk tier**: Tier 3 (Logic/Workflow) — agent prompt change + Python script update
- **Impact**: Low — additive field, fully backward compatible
- **Mitigation**: Test fixtures validate both new-format and legacy (no `processed_at`) paths

## Architecture Impact

None. No changes to deployed services, credentials, ports, or data flows. This modifies agent instructions (prompt text) and a Python classification script.

## Constitutional Compliance

- **Autonomy level**: Autonomous (Level 3) — no human approval needed for timestamp writing
- **Scope**: Inbox processing frontmatter enrichment only
- **Failure behavior**: If timestamp write fails, processing should still complete; `processed_at` is additive, not blocking
- **Privacy boundary**: No second-brain private data affected — inbox files are in the system processing path
