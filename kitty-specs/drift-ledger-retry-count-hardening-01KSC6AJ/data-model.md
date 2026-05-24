# Data Model: `AuditLedgerEntry` (drift-ledger variant) — post-fix

**Mission**: `drift-ledger-retry-count-hardening-01KSC6AJ`
**File**: `scripts/doc_audit/output/drift_ledger.py`

This document describes the dataclass as it will exist **after** this mission. Only the `retry_count` invariant changes. Field layout, serialization, and on-disk format are unchanged (NFR-001).

> **Note**: There are two unrelated classes both named `AuditLedgerEntry` — one in `output/drift_ledger.py` (this one, with `retry_count`) and one in `output/audit_ledger.py` (no `retry_count`). Only the drift-ledger variant is affected by this mission.

---

## Fields

Field order is load-bearing per `FIELD_ORDER` in the module. Unchanged from today.

| Field | Type | Required | Validation | Notes |
|---|---|---|---|---|
| `schema_version` | `int` | yes | `== SCHEMA_VERSION` (`1`) | Unchanged. Additive bound widening does not bump version. |
| `event_id` | `str` | yes | non-empty | Composite `<cursor_line>:<timestamp>` |
| `timestamp_utc` | `str` | yes | non-empty | ISO 8601 UTC; verdict-finalize time |
| `baseline` | `str` | yes | non-empty | Baseline file name (e.g., `openclaw-cron`) |
| `mapping_id` | `str` | yes | non-empty | Mapping id (e.g., `openclaw-cron-drift`) |
| `verdict` | `str` | yes | ∈ `VALID_VERDICTS` | `PROPOSED_EDIT` \| `JUDGMENT_REQUIRED` \| `NO_CHANGE_NEEDED` \| `RETRY_EXHAUSTED` |
| `confidence` | `float \| None` | yes | `None` iff verdict is `RETRY_EXHAUSTED`; else `∈ [0.0, 1.0]` | Unchanged |
| `outcome` | `str` | yes | ∈ `VALID_OUTCOMES` | `auto_committed` \| `pr_filed` \| `issue_filed` \| `auto_closed` \| `retry_exhausted` |
| `doc_paths` | `list[str]` | yes | list of strings | From mapping's `doc_targets` |
| **`retry_count`** | **`int`** | **yes** | **`∈ [0, retry_max]`** where `retry_max = 1 + len(RETRY_DELAYS_SECONDS)` (currently `4`) | **CHANGED** — bound widened from `[0, 3]`. Records the actual attempt count of the retry helper, including the final failing attempt. |
| `latency_ms` | `int` | yes | `>= 0` | End-to-end including retries |
| `tier_classification_outcome` | `str \| None` | yes | ∈ `{tier_a, tier_b, judgment, None}` | `None` when Moment 1 not invoked |
| `github_issue_number` | `int \| None` | yes | int or None | Set when outcome includes a filed issue/PR |

## Invariants

Validated by `_validate_entry()` before write. After this mission:

```python
if entry.retry_count < 0 or entry.retry_count > retry_max:
    raise ValueError(
        f"retry_count must be in [0, {retry_max}]; got {entry.retry_count!r}"
    )
```

Where `retry_max` is derived from `RETRY_DELAYS_SECONDS` at module load time (imported from `doc_audit.judgment.drift_interpretation`).

All other invariants in `_validate_entry()` are unchanged.

## Backward Compatibility

- **Existing rows** (`retry_count ∈ [0, 3]`): continue to validate without modification. `[0, 3]` is a strict subset of `[0, retry_max]` (where `retry_max ≥ 3`).
- **schema_version**: NOT bumped. Per the contract doc: "Adding new optional fields without bumping schema_version is allowed (consumers MUST ignore unknown fields)." Widening an existing field's accepted range is similarly forward-compatible — no consumer that handled the old range can fail on a value within it.
- **Readers**: `_dict_to_entry()` and `_parse_json_line()` are unaffected. The validator is the only enforcement point.

## State Transitions

None. The entry is an append-only record; no in-place mutation.

## Cross-File Dependencies

The new validator must read `retry_max` from one of:
- `from doc_audit.judgment.drift_interpretation import RETRY_DELAYS_SECONDS` (selected — keeps the source-of-truth in the retry module where the policy actually lives)

Other options considered and rejected in [research.md](research.md) Decision 1.
