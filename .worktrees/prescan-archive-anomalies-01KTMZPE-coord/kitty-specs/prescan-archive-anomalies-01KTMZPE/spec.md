# Specification: Prescan Archive Anomalies Check

**Mission**: `prescan-archive-anomalies-01KTMZPE`
**Mission ID**: `01KTMZPE0QR0AZACXF1A0X9SV6`
**Target branch**: `main`
**Mission type**: `software-dev`
**Issue**: kentonium3/kg-automation#568 (closes); parent epic #563 (closes when this lands)
**Created**: 2026-06-08

## Purpose (Stakeholder Summary)

Epic #563 (silent inbox content loss) is structurally fixed: #566 shipped the AGENTS.md rewrite + 6 new helpers so capture's prompt is no longer truncated, and #567 shipped the 5-min auto-deploy pipeline. This mission adds the **defensive safety rail**: a read-only scan of `02-Inbox-Processed/` that flags any file with `status` other than `processed` (e.g., `unprocessed`, `needs-review`, missing status, parse failures). Result: any FUTURE regression of the bug class — whether from agent improvisation, a manual move, or new code — converts silent loss into a visible alarm via the existing daily-log + stderr surfaces. No file movement. No remediation. Just visibility.

The new behavior is an additive extension to the existing `scripts/inbox/prescan.py` (its `scan_archive_anomalies()` function), an additive field on the existing `PrescanResult` (`archive_anomalies`), and an additive section in the existing daily log when anomalies are present.

**Closes #568. Closes epic #563.**

## User Scenarios & Testing

### Primary scenario: capture cron tick with a clean archive

1. felix-admin-capture cron fires. The capture agent invokes `python3 -m scripts.inbox.prescan`.
2. prescan classifies the inbox AND scans `02-Inbox-Processed/`. All archive files have `status: processed` (the healthy case).
3. prescan's JSON output has `"archive_anomalies": []`. The agent ignores the empty field.
4. The daily log gets an entry; the `archive_anomalies` section is omitted (avoid log noise on the no-anomaly path).

### Scenario: a file with `status: unprocessed` is detected in archive

1. (Some prior regression — e.g., a future agent code path improvises) puts a note in `02-Inbox-Processed/` with `status: unprocessed`.
2. Next prescan tick scans the archive, finds the anomaly.
3. prescan's JSON output has `"archive_anomalies": [{"path": ".../Inbox 2026-06-08 1925.md", "status_raw": "unprocessed", "classification": "unprocessed", "warning": "status:unprocessed found in 02-Inbox-Processed/"}]`.
4. Daily log gains a new section `### archive_anomalies (count=1)` listing each path + warning.
5. stderr summary line includes `archive_anomalies=1`.
6. Capture agent's prompt logic decides what to do (out of scope here — the helper is read-only).

### Scenario: parse failure in archive

1. A file in `02-Inbox-Processed/` has malformed YAML frontmatter.
2. prescan's archive scan applies the existing `classify_file()` which detects the parse failure.
3. The anomaly is emitted with `classification: "parse-failure"`.

### Scenario: daily log files in archive are skipped

1. The archive contains `inbox-processing-2026-06-08.md` (a daily log written by the existing pipeline).
2. The archive scan filters by filename prefix `inbox-processing-`.
3. Daily logs do NOT appear in `archive_anomalies` regardless of their frontmatter shape.

### Scenario: large archive (>5,000 files)

1. The archive has accumulated >5,000 files over years.
2. The scan caps at 5,000 most-recent-mtime files.
3. A `cap_applied` warning is added to the existing `PrescanResult.warnings` list naming the cap value and how many files were skipped.
4. The cap threshold is a module-level constant for future tuning.

### Operator scenario: dry-run inspection on Mac

1. From the Mac repo root: `python3 -m scripts.inbox.prescan` (existing CLI).
2. The JSON output now includes the `archive_anomalies` field.
3. If the operator's local vault has archive files (unlikely on Mac — second-brain lives on office2 via Obsidian Sync), the field shows what's there. Empty otherwise.

## Domain Language

| Term | Definition |
|---|---|
| **Archive anomaly** | A file in `02-Inbox-Processed/` whose frontmatter `status` is NOT exactly `processed` (per the canonical processed state). Includes: `unprocessed`, `needs-review`, missing status, unknown values, parse failures. |
| **Daily log filename** | `inbox-processing-YYYY-MM-DD.md` — pre-existing surface the daily-log writer creates in `02-Inbox-Processed/`. NOT an anomaly even if its frontmatter doesn't match note conventions. |
| **Scan cap** | Module-level constant capping archive scan at the 5,000 most-recent (by mtime) `.md` files. Operator-tuneable. |
| **`classify_file()`** | The existing function in `scripts/inbox/prescan.py` that extracts `status_raw` + parse-failure detection from a single file. Reused as-is. |

## Functional Requirements

| ID | Description | Status |
|---|---|---|
| FR-001 | New function `scan_archive_anomalies(processed_dir: Path, now_utc: datetime) -> list[ArchiveAnomaly]` exists in `scripts/inbox/prescan.py`. Iterates `.md` files in `processed_dir` non-recursively (no subdirectories). | Specified |
| FR-002 | The new function filters out daily log files by filename prefix `inbox-processing-`. These are skipped silently (no anomaly, no warning). | Specified |
| FR-003 | For each non-skipped file, the new function applies the existing `classify_file()` to extract `status_raw` and parse-failure detection. | Specified |
| FR-004 | A file is classified as anomalous iff its `status_raw` is NOT exactly `"processed"`. This includes: `unprocessed`, `needs-review`, missing status, unknown values, and parse failures. | Specified |
| FR-005 | The new function returns one `ArchiveAnomaly` per anomalous file: `{path, status_raw, classification, warning}`. `classification` is one of `"unprocessed"`, `"needs-review"`, `"unknown-treated-as-unprocessed"`, `"parse-failure"`. `warning` is a short human-readable reason. | Specified |
| FR-006 | If the archive contains more than the SCAN_CAP constant (5,000 by default) `.md` files, the scan inspects only the most-recent 5,000 (by mtime descending) and adds a `cap_applied` warning to the existing `PrescanResult.warnings` list naming the cap value + skipped count. | Specified |
| FR-007 | `PrescanResult` gains a new field `archive_anomalies: list[ArchiveAnomaly] = field(default_factory=list)`. Additive; existing consumers reading other fields are unaffected. | Specified |
| FR-008 | `run_prescan()` invokes the new scan function and populates `PrescanResult.archive_anomalies`. The scan ordering is: existing inbox scan → archive-stale scan → NEW archive-anomalies scan. | Specified |
| FR-009 | When `archive_anomalies` is non-empty: the daily log gains a new section `### archive_anomalies (count=N)` with one bullet per anomaly (path + warning). When empty: the section is OMITTED (no log noise on healthy ticks). | Specified |
| FR-010 | The stderr summary line emitted by prescan includes `archive_anomalies=<int>` between the existing `archived` and `warnings` fields. | Specified |
| FR-011 | The helper is read-only against the archive directory. No file movement. No deletion. No frontmatter mutation. No remediation. | Specified |
| FR-012 | `scan_archive_anomalies()` is safe on a missing `processed_dir` — returns `[]` and adds a warning to `PrescanResult.warnings` rather than raising. | Specified |
| FR-013 | The scan cap value is exposed as a module-level constant `ARCHIVE_SCAN_CAP = 5000` so an operator can tune it without code surgery. | Specified |
| FR-014 | `classify_file()` is NOT modified by this mission. Reused as a public function (already used by the inbox scan path). | Specified |
| FR-015 | No mission-scope changes to other inbox helpers (existing or new from #566 half-1). Diff is bounded to `scripts/inbox/prescan.py` + `tests/scripts/inbox/test_prescan.py` (plus a small `service-inventory.json` `purpose` update). | Specified |

## Non-Functional Requirements

| ID | Description | Status |
|---|---|---|
| NFR-001 | The full prescan invocation (inbox scan + archive-stale + archive-anomalies) completes in <2 seconds for typical inputs (≤50 inbox files, ≤5000 archive files) on office2. | Specified |
| NFR-002 | Stdlib only — no new third-party packages. Reuses `pathlib`, `datetime`, `dataclasses`, `os.stat` for mtime. | Specified |
| NFR-003 | Per-function coverage gate: ≥90% line / ≥85% branch on the new code paths via `pytest --cov=scripts.inbox.prescan --cov-branch --cov-fail-under=90`. Existing prescan tests STAY passing (regression sanity). | Specified |
| NFR-004 | Tests use the existing `tmp_path` + `conftest.py` fixture pattern under `tests/scripts/inbox/test_prescan.py` (NOT a new test file). | Specified |
| NFR-005 | The new field is added to `PrescanResult` as an ADDITIVE list with a default factory, so existing JSON consumers that only read other fields are unaffected. | Specified |

## Constraints

| ID | Description | Status |
|---|---|---|
| C-001 | Per CLAUDE.md, `~/second-brain/notes/04-Growth/_private/` is never read, written, referenced, or logged. The archive scan operates on `02-Inbox-Processed/` only; this dir does not contain private paths but the C-001 invariant remains. | Specified |
| C-002 | The helper is read-only against the archive (FR-011). No remediation logic enters prescan; remediation is the agent's choice based on the visible anomalies. | Specified |
| C-003 | Risk tier 3 (Logic). No service-inventory schema change (component entry's `purpose` is updated; nothing structural). No credential surface. No new state files. | Specified |
| C-004 | This is the LAST sub-issue under epic #563. Mission close = epic close (#563 closes when #568 closes per [[project_epic_563_status]]). | Specified |
| C-005 | The scan cap (5000) is a module constant. Operator can tune via code edit in a future change; no env var or config file plumbing. Per scope discipline. | Specified |

## Success Criteria

1. `python3 -c "from scripts.inbox.prescan import scan_archive_anomalies, ARCHIVE_SCAN_CAP, PrescanResult; print(ARCHIVE_SCAN_CAP)"` returns `5000` and imports cleanly.
2. `pytest tests/scripts/inbox/test_prescan.py tests/inbox/test_prescan_parse_failure.py --cov=scripts.inbox.prescan --cov-branch --cov-fail-under=90 -v` passes with ≥90% line / ≥85% branch coverage.
3. A synthetic anomaly fixture (a note with `status: unprocessed` in the archive dir) is correctly flagged in the `archive_anomalies` field with `classification: "unprocessed"`.
4. A `inbox-processing-2026-06-08.md` fixture in the archive dir is correctly SKIPPED (no anomaly).
5. A fixture archive with 5001 `.md` files is capped at 5000; the `warnings` list contains a `cap_applied` entry.
6. JSON output validity: `python3 -m scripts.inbox.prescan` from a synthetic vault root produces parseable JSON with `archive_anomalies` field present (empty array on healthy).
7. No regression: existing 139 tests from #566 half-1 STAY passing.

## Key Entities

| Entity | Fields | Notes |
|---|---|---|
| **ArchiveAnomaly** | `path: str`, `status_raw: Optional[str]`, `classification: str` (enum), `warning: str` | New dataclass in prescan.py |
| **PrescanResult** (existing) | (existing fields) + `archive_anomalies: list[ArchiveAnomaly] = field(default_factory=list)` | Additive field |

## Assumptions

- `scripts/inbox/prescan.py`'s `classify_file()` API is stable. This mission consumes it without modification.
- The `paths.inbox_processed` path resolution from `scripts/vault/paths.json` works (already a precondition for the existing prescan).
- The archive contains routed inbox notes + daily logs (with `inbox-processing-` prefix). Other file types may exist (rare) and would be treated as anomalies if they have `.md` extension and non-`processed` status.
- Test fixtures in `tests/inbox/fixtures/` are stable. New fixtures can be added there without conflict.
- 5,000 is a generous cap for now (the archive has hundreds of files at most as of 2026-06-08). Future tuning is a code edit.

## Out of Scope

- Auto-remediation (file movement, frontmatter mutation, archive-to-inbox move) — explicitly excluded per FR-011.
- Other archive anomaly classes (duplicate files, permission issues, orphaned routing-log entries) — scope is status-mismatch only.
- Notification routing (WhatsApp, digest) — the daily log + stderr summary are sufficient; future enhancement could route via the existing digest-signals pipeline.
- Changes to capture's AGENTS.md (#566 closed the rewrite).
- Cross-mount vault verification — the helper trusts `paths.inbox_processed` from the registry.
- Performance benchmarking — NFR-001's <2s target is enforced by the cap + existing latency profile, not by a new benchmark surface.

## Architecture Documentation Updates (DIR-005)

| File | Update |
|---|---|
| `docs/design/architecture/data/service-inventory.json` | Update `services[openclaw-gateway].agents.felix-admin-capture.components[id=="inbox-prescan-helper"].purpose` to add a sentence about the archive-anomaly scan. Bump `updated_at` to today. Prepend this mission to `updated_by`. Top-level `last_updated` + `updated_by` bumped. |

This mission's scope is narrow; no new component entry (the archive-anomaly check lives inside the existing `inbox-prescan-helper` component).

## Reference Index

- Issue: kentonium3/kg-automation#568 (this mission closes)
- Parent epic: kentonium3/kg-automation#563 (closes when this lands)
- Sibling sub-issues: #566 (closed; AGENTS.md rewrite), #567 (closed; deploy pipeline)
- Related mission: `capture-d6-helpers-extraction-01KTMS5Q` (half-1 helpers) — this mission does NOT touch any of those 6 helpers
- Related mission: `capture-agents-md-rewrite-01KTMY86` (half-2 AGENTS.md) — this mission does NOT touch capture's prompt
- Memory references:
  - `[[feedback_signal_driven_doc_audit]]` — signal-driven approach (this mission applies the same pattern to inbox archive hygiene)
  - `[[feedback_helper_m_invocation_form]]` — `-m` form mandatory (already in prescan)
  - `[[feedback_scripts_vs_llm]]` — deterministic helper extension (no LLM surface)
  - `[[reference_speckitty_3_2_rc41_quirks]]` — workflow workarounds expected
  - `[[project_epic_563_status]]` — closes when this mission ships
- Existing helper: `scripts/inbox/prescan.py` (778 lines; this mission extends to ~830-870 lines)
- Existing test surface: `tests/scripts/inbox/test_prescan.py` + `tests/inbox/test_prescan_parse_failure.py`
- Existing fixtures: `tests/inbox/fixtures/`
