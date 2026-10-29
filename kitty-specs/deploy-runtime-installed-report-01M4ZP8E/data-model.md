# Data Model

*(Revised 2026-10-15 after the post-plan review; supersedes the first draft.)*

- **InstalledReportLine**: `{"source": abs resolved repo path, "dest": abs resolved host path}`. Written after landing; changed files only.
- **ReadResult** (`installed_report.read_report`): `{"entries": list[{source, dest}], "rejected": bool, "missing": bool, "warnings": list[str]}`. Validation is wholesale.
- **ApplyResult additions** (`LibResult.details` from `dry_run_then_apply_gate`, on every return after `--apply`): `installed_report: ReadResult` and `installed_report_write_failed: bool`.
- **ReportedMapping** (`rebaseline.baselines_for_installed_report`): `{"baselines": list[str], "rejected": bool, "matched": list[str] (repo-relative sources), "warnings": list[str]}`.
- **Registry addition**: `audited_surfaces[].host_paths: list[str]` (optional; `~`-prefixed allowed). Set for `systemd-user-units` = `["~/.config/systemd/user/"]`.
- **Token additions**: `last_fold_utc` (set on a fold merge; preserved by `observe()`; used for grace only), and a persisted `manifest_names` union (contributors, including reported-only failed applies).
- **Tick log event** `rebaseline_reported`: `{manifest_name, apply_ok, entries, baselines, rejected, missing, warnings, write_failed, absorbed}`.

Invariant (C-002): `baselines` ⊆ ⋃ `affected_baselines` of surfaces S where **every** report entry has a source matching S's patterns inside the resolved repo root **and** a destination inside S's resolved `host_paths`. Any entry failing either check gives ∅.
