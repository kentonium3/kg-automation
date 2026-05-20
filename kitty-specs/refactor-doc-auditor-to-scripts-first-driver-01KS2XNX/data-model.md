# Data Model: Refactor doc-auditor to scripts-first driver

**Mission**: `refactor-doc-auditor-to-scripts-first-driver-01KS2XNX` (#343)
**Phase**: 1 (design — data-model)
**Date**: 2026-05-20

Entities below are described as Python dataclasses (the implementation language per `research.md` D1/D14) but the schemas are also realized in JSON shapes where artifacts cross process boundaries (`tick_signal.json`, prompt I/O, etc.). When a field's value carries a constraint, the constraint is stated explicitly.

---

## E-001: `Signal` — normalized input to the driver

The unifying abstraction across signal sources (D4). Each `SignalSource` adapter produces zero or more `Signal` instances per tick.

| Field | Type | Required | Description / constraints |
|---|---|---|---|
| `id` | str | yes | Stable identifier for dedup. For GH-issue signals: `gh-issue:<number>`. For drift events: `drift:<baseline_name>:<timestamp_utc>`. |
| `source` | str | yes | Adapter name. One of `gh_issue`, `drift_event`. Extensible. |
| `kind` | str | yes | Signal kind within source. For `gh_issue`: one of `doc_audit`, `weekly_doc_audit`, `pending_approval`. For `drift_event`: matches event_type from drift-events.jsonl. |
| `priority` | int | yes | Lower = earlier. `pending_approval` = 10, `doc_audit` = 20, `weekly_doc_audit` = 30, `drift_event` = 40. Driver processes lowest-first per tick. |
| `payload` | dict | yes | Source-specific data. GH-issue payload includes `issue_number`, `title`, `body`, `labels`, `area_labels`. Drift-event payload includes the raw event JSON. |
| `created_utc` | str | yes | ISO-8601 UTC timestamp. For GH issues, the issue created_at. For drift events, the timestamp field. |

**Invariants**:
- `id` is unique within a tick's processed-signal set; duplicate IDs are deduped (last-wins).
- `priority` defines the tick processing order.

---

## E-002: `AuditIssue` — parsed `Doc audit:` or `Weekly doc audit —` GH issue

Derived from a `Signal` of kind `doc_audit` / `weekly_doc_audit`. The driver constructs one `AuditIssue` per such signal as it begins processing.

| Field | Type | Required | Description / constraints |
|---|---|---|---|
| `issue_number` | int | yes | GitHub issue number. |
| `title` | str | yes | Verbatim issue title. |
| `is_weekly` | bool | yes | True if title starts with `Weekly doc audit —`. |
| `triggering_sha` | str | conditional | Required if `is_weekly=False`. Extracted from title (`Doc audit: <sha> (<domains>)`). |
| `area_labels` | list[str] | yes | All `area/*` labels. Empty list = full-scope (typical for weekly audits per SKILL.md §3 step 2). |
| `in_scope_docs` | list[str] | yes | Resolved via domain map intersection. Empty = full-scope, populated from union of all values. |
| `lock_acquired_at_utc` | str | nullable | Timestamp when `status:in-progress` was added this tick. Null if not yet acquired. |

**State transitions**:
- `lock_acquired` → audit is being processed in this tick
- `lock_released` → final state; audit is closed or returned to queue
- A stuck-lock audit (acquired in a prior tick that crashed) is recoverable per spec FR-014; recovery logic checks whether the audit has a referenced pending-approval issue (per SKILL.md §8.7 stale-lock detection).

---

## E-003: `PendingApproval` — pending-approval issue with operator decision

Filed in prior ticks when an audit produced Tier-B proposals. Resolved in current tick if a decision label is applied.

| Field | Type | Required | Description / constraints |
|---|---|---|---|
| `issue_number` | int | yes | GitHub issue number of the pending-approval issue. |
| `audit_issue_number` | int | yes | Cross-referenced originating audit issue. |
| `proposed_edits` | list[`ProposedEdit`] | yes | The before/after edits awaiting decision. Parsed from issue body. |
| `decision` | str | yes | One of `audit-approve`, `audit-reject`, `audit-skip`. Driver only constructs `PendingApproval` for issues with a decision label applied. |
| `actor_login` | str | yes | GitHub login of the user who applied the decision label (per SKILL.md §8.6 actor-verification check). |
| `is_self_apply` | bool | yes | True if `actor_login` matches the bot's own identity (`kg-felix-bot`). Triggers gate-violation handling per spec FR-008. |
| `area_labels` | list[str] | yes | Copied from the originating audit. |

**Invariants**:
- A `PendingApproval` with `is_self_apply=True` MUST NOT have its decision applied — gate violation.
- Decision processing happens BEFORE new-audit scanning in any tick (spec FR-004).

---

## E-004: `ProposedEdit` — single edit awaiting application

Embedded in `PendingApproval.proposed_edits` and (during fresh audit processing) in `AuditIssue`-derived state.

| Field | Type | Required | Description / constraints |
|---|---|---|---|
| `doc_path` | str | yes | Repo-relative path of the file to be edited. |
| `change_type` | str | yes | One of: `frontmatter_field_bump`, `frontmatter_updated_by`, `service_version`, `file_path_rename`, `dead_reference_removal`, `agent_registry_add`, `autonomy_level_update`. (Maps to SKILL.md §4.1 #1-7.) |
| `current_value` | str | yes | What's there today. |
| `proposed_value` | str | yes | What it should become. |
| `evidence_source` | str | yes | Pointer to the source-of-truth (e.g., `service-inventory.json:services[name=foo].version` or `git show <sha>`). |
| `tier` | str | yes | One of `tier_a` (frontmatter-only, auto-commit per §4.1.a), `tier_b` (gated per §4.1.b). Result of the `tier_classification` LLM call. |
| `confidence` | str | yes | One of `high`, `judgment`. Always `high` for a `ProposedEdit` (judgment edits become `DebtIssue` instead). |

---

## E-005: `EditTier` — enum for Tier A / B classification

```python
class EditTier(str, Enum):
    TIER_A = "tier_a"        # Frontmatter-only — autonomous per §4.1.a
    TIER_B = "tier_b"        # Content-touching — Level-1 gate per §4.1.b
    JUDGMENT = "judgment"    # Not high confidence — file as docs-debt per §4.2
```

The `tier_classification` LLM call returns one of these values. Driver dispatches per value: TIER_A → auto-commit; TIER_B → file pending-approval; JUDGMENT → file debt issue.

---

## E-006: `DebtIssue` — docs-debt issue to be filed

Constructed when a finding qualifies as `JUDGMENT` per §4.2 OR is a missing-artifact per §6.

| Field | Type | Required | Description / constraints |
|---|---|---|---|
| `title` | str | yes | Format: `Docs: <short title>`. For `area/biz-ops`: `Docs (biz-ops): <short title>` (per SKILL.md §8). |
| `artifact_path` | str | yes | Doc path (existing or proposed). |
| `gap_description` | str | yes | What's missing / outdated / incorrect. |
| `area_labels` | list[str] | yes | Copied from originating audit. |
| `cross_references` | list[str] | yes | Issue numbers + commits. Always includes the originating audit. |
| `draft_outline` | str | yes | The load-bearing field per SKILL.md §8 #5. Produced by `debt_body_generation` LLM call. |
| `success_criteria` | list[str] | yes | 2–4 verifiable bullets. |
| `is_missing_artifact` | bool | yes | True for §6 missing-artifact issues; influences body template. |

---

## E-007: `DriftEvent` — single entry from drift-events.jsonl

Direct mirror of the JSONL line shape emitted by `audit.sh`.

| Field | Type | Required | Description / constraints |
|---|---|---|---|
| `timestamp` | str | yes | ISO-8601 UTC timestamp. |
| `source` | str | yes | Always `audit.sh` for v1. |
| `event_type` | str | yes | Currently `baseline_drift`. Extensible. |
| `baseline_name` | str | yes | e.g., `openclaw-cron.txt`, `openclaw-config.txt`. Joined against `signal-to-doc-map.json` `match.baseline_name`. |
| `diff_b64` | str | yes | Base64-encoded diff text. The diff is what changed — fed to the cross-file-implication LLM call if a mapping is found. |

Consumed by `DriftEventSignalSource` via `handle_drift_events.py`. Mapped events are filed as `[doc-audit]` GH issues (cursor advanced); unmapped events accumulate in `unmapped-events.jsonl`.

---

## E-008: `TickResult` — internal driver outcome record

Aggregated as the driver processes the queue; serialized to `TickSignal` (E-009) at end.

| Field | Type | Required | Description / constraints |
|---|---|---|---|
| `started_utc` | str | yes | When the tick began. |
| `ended_utc` | str | yes | When the tick ended. |
| `status` | str | yes | One of `success`, `partial`, `failure`. |
| `signals_seen` | int | yes | Count of signals enumerated this tick across all adapters. |
| `signals_processed` | int | yes | Count of signals fully processed (closed audits, applied decisions, etc.). |
| `tier_a_commits` | list[str] | yes | SHAs of Tier-A commits made this tick. |
| `pending_approvals_filed` | list[int] | yes | Issue numbers of new pending-approval issues filed. |
| `pending_approvals_applied` | list[int] | yes | Issue numbers of pending-approvals resolved this tick. |
| `debt_filed` | list[int] | yes | Issue numbers of new debt issues filed. |
| `drift_events_consumed` | int | yes | Count of drift events processed (cursor delta). |
| `errors` | list[str] | yes | Error strings (rate-limit, gate-violation, etc.). |
| `judgment_calls` | dict | yes | Counts per moment: `{"tier_classification": N, "debt_body_generation": N, "cross_file_implication": N}`. |
| `token_usage` | dict | yes | `{"input_tokens": N, "cache_hit_input_tokens": N, "output_tokens": N}` summed across all LLM calls (NFR-001 measurement input). |

---

## E-009: `TickSignal` — JSON artifact at `last-tick.json`

The structured signal consumed by future #327 alerting. See `contracts/tick-signal.contract.md` for the full schema.

Derived from `TickResult` at end of tick. Atomically written to `/data/services/openclaw/felix-doc-auditor-driver/last-tick.json`.

---

## E-010: `ActivityLogEntry` — one line per tick in the activity log

Preserved format per spec C-005.

| Field | Type | Required | Description / constraints |
|---|---|---|---|
| `timestamp_utc` | str | yes | ISO-8601. |
| `tick_outcome` | str | yes | One-line summary (matches `TickResult.status` + counts). |
| `audits_processed` | list[int] | yes | Issue numbers touched this tick. |
| `errors` | list[str] | yes | If any. |
| `driver_version` | str | yes | For traceability. |

Written to `/home/kgale/second-brain/agents/logs/doc-auditor-YYYY-MM-DD.md` (preserved location per spec C-005, Assumption 4).

---

## State machine — audit issue lifecycle

```
[new audit filed by upstream] ──> open, no labels (steady state in queue)
        │
        v
[driver picks up in tick]  ──> open, status:in-progress (lock held)
        │
        ├─ empty audit  ──> summary comment posted ──> closed (lock released)
        │
        ├─ debt-only    ──> debt issues filed + summary posted ──> closed
        │
        ├─ Tier-A only  ──> Tier-A commit made + summary posted ──> closed
        │
        └─ Tier-B present ──> pending-approval issue filed ──> open, status:in-progress persists
                                          │
                                          v (next tick after operator labels)
                                  [decision label applied]
                                          │
                                          ├─ audit-approve ──> commit + close audit + close pending-approval
                                          ├─ audit-reject  ──> demote to debt + close both
                                          └─ audit-skip    ──> close both with skip note
```

Lock is released in EVERY closure path. Failed ticks release the lock in `finally`; if release itself fails, next tick recovers per spec FR-014.

---

## Cross-references

- **Spec**: `kitty-specs/refactor-doc-auditor-to-scripts-first-driver-01KS2XNX/spec.md`
- **Research**: `kitty-specs/refactor-doc-auditor-to-scripts-first-driver-01KS2XNX/research.md`
- **Signal map**: `docs/design/architecture/data/signal-to-doc-map.json`
- **Inherited classifications**: `scripts/openclaw/skills/doc-audit/SKILL.md` §4.1 (Tier A / B / judgment), §4.2 (judgment categories), §4.3 (constitutional guardrails), §6 (missing-artifact rules), §8 (debt-issue template), §8.6 (actor-verification)
