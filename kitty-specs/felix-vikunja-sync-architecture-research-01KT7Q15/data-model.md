# Data Model (Discovery Draft) — Felix-Vikunja Sync Architecture Research

**Scope note**: This is a *research mission*. The entities below are the conceptual model the research will populate. Concrete implementation models (schemas, tables, columns) are produced by the follow-on implementation missions filed under FR-008 / FR-012. This document describes what the research must capture; it does not pre-decide implementation.

## Entities

### Entity: Sync Layer

- **Description**: One of `status`, `task`, `project`. The three-layer model the architecture proposes for partitioning Vikunja-Felix state synchronization.
- **Attributes**:
  - `layer_name` (string) — one of `status` / `task` / `project`.
  - `vikunja_resources` (list[string]) — Vikunja API resources mapped to this layer (e.g., `/tasks`, `/projects`, `/labels`).
  - `felix_state_surface` (string) — where Felix stores its computed/cached view of this layer (existing substrate name or "TBD by recommendation").
  - `reconciliation_cadence` (duration) — how often this layer is reconciled. Must fit under the 5-min overall ceiling.
  - `read_touchpoints_count` (int) — populated from RQ-2 inventory.
  - `write_touchpoints_count` (int) — populated from RQ-2 inventory.
  - `conflict_surfaces` (list[string]) — where conflicts on this layer arise (e.g., due-date conflicts on task layer).
- **Identifiers**: `layer_name` is the primary identifier.
- **Lifecycle Notes**: Layers are static — the three-layer model is a deliberate architectural choice. Adding a fourth layer would require an ADR-0003 amendment.

### Entity: Touchpoint

- **Description**: A Felix code callsite that reads from or writes to Vikunja. One row per callsite, not per file.
- **Attributes**:
  - `file_path` (string) — repo-relative.
  - `function_or_callsite` (string) — function name or `(module-level)`.
  - `layer` (string) — one of `status` / `task` / `project`.
  - `http_verb` (string) — `GET` / `POST` / `PUT` / `PATCH` / `DELETE`.
  - `vikunja_endpoint` (string) — endpoint pattern.
  - `read_set` (list[string]) — Vikunja fields read.
  - `write_set` (list[string]) — Vikunja fields written.
  - `freshness_assumption` (string) — `<5 min` / `same-cron-tick` / `no constraint` / etc.
  - `owner_component` (string) — which Felix component owns this callsite.
  - `runtime_trigger` (string) — `cron` / `systemd-timer` / `openclaw-agent` / `manual`.
- **Identifiers**: composite (`file_path`, `function_or_callsite`, `vikunja_endpoint`).
- **Lifecycle Notes**: Populated during RQ-2. Each row cites the source-register entry for the file. The reproducible grep commands used to find the touchpoints are themselves cited (NFR-equivalent NFR-006 documentation).

### Entity: Conflict Event

- **Description**: A structured record emitted when Felix's computed state diverges from Vikunja's actual state. Emitted to a log; consumed by zero-or-more routers (initially: log + WhatsApp for unsafe class only).
- **Attributes** (these are the dimensions the research must capture; the implementation schema is a research output):
  - `event_id` (string) — idempotency anchor. Required for at-least-once router delivery.
  - `ts_emitted_utc` (ISO-8601) — sender-side timestamp.
  - `ts_observed_utc` (ISO-8601) — when Felix observed the conflict.
  - `layer` (string) — `status` / `task` / `project`.
  - `vikunja_entity_id` (string) — Vikunja-side primary identifier (per RQ-1 stable-identifier choice).
  - `vikunja_entity_kind` (string) — `task` / `project` / etc.
  - `felix_state_snapshot` (json) — Felix's view at conflict time. Compact.
  - `vikunja_state_snapshot` (json) — Vikunja's view at conflict time. Compact.
  - `diff_summary` (string) — one-line human-readable summary (used by WhatsApp router).
  - `conflict_class` (string) — initially `auto_resolved` or `unsafe_to_auto_resolve`; extensible.
  - `resolution_decision` (string) — `accepted_vikunja` / `escalated` / etc.
  - `router_route_set` (list[string]) — e.g., `["log"]` for auto_resolved; `["log", "whatsapp"]` for unsafe_to_auto_resolve.
  - `correlation_id` (string, optional) — links the event to a Felix mission, operator action, or upstream event.
  - `schema_version` (int) — forward-compat anchor.
- **Identifiers**: `event_id`.
- **Lifecycle Notes**: Append-only log. `event_id` derivation must be deterministic so that replays of the same conflict produce the same ID (idempotency).

### Entity: Unsafe-to-Auto-Resolve Class

- **Description**: The criteria set that defines which conflicts route to the WhatsApp ping in addition to the log. Each criterion is testable from conflict-event fields alone (no out-of-band lookup).
- **Attributes** (criterion dimensions; the criterion list is a research output):
  - `criterion_name` (string) — e.g., `kent_edit_after_felix_write`.
  - `description` (string).
  - `test_predicate` (string) — describes how the criterion is evaluated from conflict-event fields.
  - `worked_example_ref` (string) — points to a row in evidence-log.csv that demonstrates this criterion firing on a real-or-realistic conflict.
- **Identifiers**: `criterion_name`.
- **Lifecycle Notes**: Initially defined by RQ-3. Future implementation missions may extend the criterion set; the schema must allow that.

### Entity: Reconciliation Cycle

- **Description**: One polling pass that reconciles Felix's view with Vikunja's actual state.
- **Phases**:
  - `fetch` — query Vikunja for changed-since state (if API supports) or current full state.
  - `diff` — compare Vikunja state to Felix's cached view per layer.
  - `classify` — for each diff, classify as `noop` / `auto_resolved` / `unsafe_to_auto_resolve`.
  - `emit` — write conflict events to log. Route unsafe-class events through WhatsApp router.
  - `update` — update Felix's cached state to match Vikunja (per C-002: Vikunja wins).
  - `complete` — write a freshness pointer (cycle completion ts; per `reference_felix_doc_auditor_ops` pattern).
- **Identifiers**: implicit by timestamp + layer.
- **Lifecycle Notes**: Cadence is decided in the recommendation. The 5-min overall ceiling (NFR-002) constrains cadence × per-layer latency budget.

### Entity: Stable Identifier (candidate field)

- **Description**: A Vikunja field evaluated as a candidate for cross-cycle entity re-identification.
- **Attributes** (evaluation dimensions; the verdict matrix is a research output):
  - `candidate` (string) — field name (e.g., `id`, `identifier`, `uuid`, `created_at`).
  - `stability_under_edit` (bool) — does the value change when the entity is edited?
  - `stability_under_delete_recreate` (bool) — does a deleted-and-recreated entity get the same value?
  - `cross_project_uniqueness` (bool) — is the value unique across all projects, or only within one?
  - `surfaced_in_ui` (bool) — is the value visible to operators (relevant for WhatsApp ping content)?
  - `verdict` (string) — `Suitable` / `Conditional` / `Not suitable`.
- **Identifiers**: `candidate`.
- **Lifecycle Notes**: Populated during RQ-1. Memory cross-reference: `reference_vikunja_id_vs_identifier` (UI shows `identifier`, API uses `id`).

## Relationships

| Source | Relation | Target | Cardinality | Notes |
|--------|----------|--------|-------------|-------|
| Sync Layer | groups | Touchpoint | 1:N | One layer can have many touchpoints; one touchpoint belongs to exactly one layer (or sometimes two for cross-layer reads). |
| Sync Layer | is monitored by | Reconciliation Cycle | 1:N | Each reconciliation cycle reconciles one layer (or all layers — design decision in recommendation). |
| Reconciliation Cycle | emits | Conflict Event | 1:N | One cycle may emit zero or many conflict events. |
| Conflict Event | classified by | Unsafe-to-Auto-Resolve Class | N:1 | A conflict event maps to zero or one unsafe-class criterion. |
| Touchpoint | participates in | Reconciliation Cycle (phase: `update`) | N:M | Multiple touchpoints update during the `update` phase based on the diff. |
| Stable Identifier (candidate) | references | Vikunja Entity (task/project) | N:1 | One Vikunja entity has multiple candidate identifiers; the architecture picks one as primary. |

## Validation & Governance

- **Data quality requirements**:
  - Touchpoint inventory MUST be exhaustive (every callsite), not representative (FR-004).
  - Every load-bearing claim MUST cite an evidence-log row (NFR-001).
  - Every API claim MUST be tagged observed-vs-documented (NFR-006).
- **Compliance considerations**: not applicable — research operates on operator-owned infrastructure; no PII flow, no external data sharing.
- **Source of truth**:
  - For Vikunja state: the live Vikunja instance via `https://office2.tail0f5f56.ts.net/api/v1` (per C-002 Vikunja wins).
  - For Felix touchpoint inventory: the current `main` branch of `/Users/kentgale/repos/kg-automation/`.
  - For locked policy decisions: spec.md C-### entries.
  - For architectural decisions: the draft `adr-0003.md` produced by WP03.

> Treat this as a working model. As research surfaces new dimensions, update the entity attribute lists immediately so downstream sub-questions and the synthesis inherit up-to-date context.
