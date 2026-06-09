# Tasks: Prescan Archive Anomalies Check

**Mission**: `prescan-archive-anomalies-01KTMZPE`
**Spec**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)

## Subtask Index

| ID | Description | WP |
|---|---|---|
| T001 | Add `ArchiveAnomaly` dataclass + `scan_archive_anomalies()` function (incl. cap + missing-dir safety) + extend `PrescanResult` with `archive_anomalies` field | WP01 |
| T002 | Wire `run_prescan()` to invoke the new scan; extend daily-log writer to emit `### archive_anomalies` section when non-empty; extend stderr summary with `archive_anomalies=N` | WP01 |
| T003 | Add ≥10 tests covering: anomaly detection per kind, daily-log filter, cap behavior, missing-dir safety, JSON output shape, log section omission on healthy ticks, regression on existing prescan tests | WP01 |
| T004 | Verify coverage gate ≥90% line / ≥85% branch on `scripts.inbox.prescan` | WP01 |
| T005 | Update `service-inventory.json` `inbox-prescan-helper` `purpose` + bump `updated_at`/`updated_by` (mission entry) | WP01 |

## Work Packages

### WP01 — Extend prescan.py with archive-anomaly scan + tests + docs

- **Goal**: Ship the additive archive scan + matching tests + arch-doc sync in one focused WP.
- **Priority**: P1
- **Independent test**:
  - `python3 -c "from scripts.inbox.prescan import scan_archive_anomalies, ARCHIVE_SCAN_CAP; print(ARCHIVE_SCAN_CAP)"` → `5000`
  - `pytest tests/scripts/inbox/test_prescan.py tests/inbox/test_prescan_parse_failure.py --cov=scripts.inbox.prescan --cov-branch --cov-fail-under=90 -v` passes
  - `python3 -c "import json; json.load(open('docs/design/architecture/data/service-inventory.json'))"` exits 0
- **Dependencies**: none
- **Prompt file**: [tasks/WP01-archive-anomalies.md](./tasks/WP01-archive-anomalies.md)

Subtasks:
- [x] T001 Dataclass + scan function + result field
- [x] T002 Wire into run_prescan + log + stderr
- [x] T003 Tests (≥10 cases)
- [x] T004 Coverage gate
- [x] T005 Arch-doc update

## Reviewer Guidance

- **Reviewer**: codex (per `[[reference_codex_speckitty_profile]]` + #330 verified). Self-review by claude is OK as fallback.
- Focus on:
  - Daily-log filename filter actually excludes `inbox-processing-*.md`
  - Cap-applied warning fires with correct format
  - Missing-dir safety doesn't crash
  - `archive_anomalies` section is OMITTED on healthy ticks (avoid log noise)
  - Coverage gate genuinely met (no `# pragma: no branch` abuse)
  - No regression in existing prescan tests
