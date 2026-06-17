# Data Model: Auto-Rebaseline Security Baselines on Deploy

## Entity: Rebaseline-Pending Token

Single JSON file at `/data/services/felix-deployer/state/rebaseline-pending.json`.
Written atomically (`.tmp` + `os.replace`). Absent file = nothing pending.

| Field | Type | Notes |
|-------|------|-------|
| `schema_version` | int | `1`. |
| `pending_since_utc` | ISO-8601 str | When the audited-surface change was first observed in a pulled range. |
| `observed_head_sha` | str | post-pull HEAD that introduced the change. |
| `surface_ids` | list[str] | Audited-surface ids matched in the pulled range. |
| `expected_baselines` | list[str] | Union of `affected_baselines` for `surface_ids` — the only baselines an *expected* drift may touch. |
| `matched_files` | list[str] | Changed paths that matched (for the observability record). |
| `last_check_utc` | ISO-8601 str / null | Last reconcile-tick audit time. |
| `alerts_emitted` | list[str] | Event keys already alerted (dedupe: `unexpected_drift`, `stale`, `rebaseline_failed`). |

**Lifecycle**: created/merged on pull-intersection → reconciled each tick →
deleted on `rebaselined` or `cleared_clean`.

## Entity: Rebaseline Outcome (observability record)

Appended to the tick log (`/data/services/felix-deployer/logs/<date>.jsonl`)
and surfaced on the deploy record. One of:

| `outcome` | Meaning | FR |
|-----------|---------|-----|
| `not_required` | Pulled range touched no audited surface. | FR-004 |
| `pending_set` | Audited-surface change observed; token written. | FR-001/FR-008 |
| `completed` | Expected drift confirmed → baselines reset + verified healthy. Carries `rebaselined_at_utc`, `baseline_count`. | FR-002/FR-005 |
| `cleared_clean` | Pending reconciled but audit clean → no reset needed. | FR-004 |
| `unexpected_drift` | Drift beyond expected baselines → no auto-reset; human alerted. | FR-009 |
| `failed` | Rebaseline ran but verification failed (count != expected or audit not clear). Carries `error_summary`; applied code left in place. | FR-006 |
| `stale` | Token exceeded max age without confirmation → human alerted. | FR-006 |

## Entity: Audited-Surface Registry (read-only)

`docs/design/architecture/data/audited-surfaces.json` (existing). Consumed
fields: `audited_surfaces[].patterns`, `[].affected_baselines`, `[].id`,
`expected_baseline_count`, `rebaseline_command`, `rebaseline_runbook`.

## Drift classification (the decision core)

Let `D` = set of baselines reported drifted by the read-only audit;
`E` = `expected_baselines` from the token.

- `D == ∅` → **cleared_clean**.
- `D ⊆ E` and `D ≠ ∅` → **rebaseline** → verify → **completed** | **failed**.
- `D ⊄ E` (any drift outside E) → **unexpected_drift** (alert, no reset; FR-009).
