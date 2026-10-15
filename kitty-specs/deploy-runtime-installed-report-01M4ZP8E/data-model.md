# Data Model

- **InstalledReportLine**: `{"path": str}`, absolute resolved source path; written after landing; changed files only.
- **ApplyResult additions** (`LibResult.details` from `dry_run_then_apply_gate`): `installed_paths: list[str]` and `installed_report_warnings: list[str]`, present on success and on `--apply` failure.
- **ReportedMapping** (from `rebaseline.baselines_for_installed_paths`): `{"baselines": list[str], "matched": list[str] (repo-relative), "rejected": list[str], "unmatched": list[str], "warnings": list[str]}`.
- **Tick log event** `rebaseline_reported`: `{event, manifest_name, apply_ok, paths, baselines, rejected, unmatched, warnings}`.
- **Token**: unchanged schema. Reported baselines enter `expected_baselines` through the existing `fold_manifest_baselines`.

Invariant: `baselines` ⊆ ⋃ `affected_baselines` of surfaces matched by in-repo reported paths (C-002).
