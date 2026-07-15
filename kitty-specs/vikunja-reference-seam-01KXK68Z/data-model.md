# Data Model: Felix Vikunja reference seam + capture routing alignment

## Registry file (JSON — authoritative)

Conceptual shape (field names finalized during implementation):

```json
{
  "schema_version": 1,
  "source_of_truth": "docs/design/vikunja-configuration-design.md",
  "last_verified_utc": "2026-07-15T00:00:00Z",
  "projects": [
    { "name": "inbox",   "selector": { "kind": "project_id", "value": 1 },  "title": "Inbox",    "owner": "kent" },
    { "name": "habits",  "selector": { "kind": "project_id", "value": 13 }, "title": "Habits",   "owner": "kent" },
    { "name": "personal","selector": { "kind": "project_id", "value": null }, "title": "Personal", "owner": "kent", "provisioned": false }
    /* … felix_kg_automation, clients, pointerhealth, spec_kitty, metal_casework, ct_90day … */
  ],
  "labels": [
    { "name": "felix:ignore", "selector": { "kind": "label", "value": 24 }, "title": "felix:ignore", "owner_token": "kent" }
    /* f:/q:/t:/loe: taxonomy labels DEFERRED to #749 — no runtime consumer yet (FR-006) */
  ],
  "private_projects": ["<logical names, or empty>"]
}
```

> The concrete ids above are illustrative; seed from a live post-reset read and
> let the validator confirm (Risks). `felix:ignore` id is live-probed at seed
> (finding #6), not assumed.

### Entities

**ProjectRef**
- `name` — logical key Felix runtime code uses (stable; snake/lower).
- `selector` — `{ "kind": "project_id" | "label", "value": <int | null | str> }`.
  Preserving the selector shape (not a bare int) lets an identity migrate
  representation without touching consumers — e.g. Habits moving from
  `project_id: 13` → `label: "t:habit"` under #717 (FR-008).
- `title` — the human title as it exists in Vikunja (used by the validator to detect drift).
- `owner` — owning user (kent); felix-bot's own Inbox (id 14) is intentionally *not* declared (C-002).
- `provisioned` (optional, default `true`) — `false` when the reference is
  declared but the identity does not yet exist live (`value: null`, e.g.
  `Personal`). Resolving an unprovisioned ref fails loud as "declared but
  unprovisioned" — distinct from `missing`/`id_drift` (FR-009).

**LabelRef**
- `name` — canonical label string (e.g. `felix:ignore`).
- `selector` — `{ "kind": "label", "value": <int | null> }`.
- `title` — the human label title in Vikunja (drift detection).
- `owner_token` — which token's namespace the id belongs to (#715).

**PrivateProjectSet** (finding #4)
- The sync `PRIVATE_PROJECT_IDS` set is a config-injected *set*, not a name→id.
  Model it as a `private_projects` list of logical names in the registry; the
  accessor derives the concrete id set via `project_id(name)`. **Plan decides**
  whether to encode it in the registry (preferred, one source) or explicitly
  scope the sync privacy set OUT of this mission — the data model supports the
  registry-encoded form.

**ValidationFinding**
- `kind` — `missing` | `id_drift` | `title_drift` | `unprovisioned` | `unreachable`.
- `ref_type` — `project` | `label`.
- `name` — the logical name affected (absent/global for `unreachable`).
- `detail` — human string (expected vs live).

## Accessor interface (behavioral)

- `project_id(name) -> int` — returns the pinned id from the `project_id`
  selector; raises `VikunjaRefError` if `name` is undeclared, if its selector is
  a `label` (wrong accessor), or if it is declared-but-unprovisioned (`value:
  null`).
- `label_id(name, owner_token) -> int` — returns the pinned id in that token's
  namespace; raises `VikunjaRefError` if undeclared/unprovisioned for that token.
- `selector(name) -> {kind, value}` — returns the raw selector (for the
  vikunja_scope selector layer and any consumer that dispatches on `kind`).
- `project_title(name) -> str` — the declared title (for validator/reporting).
- `private_project_ids() -> frozenset[int]` — resolves the `private_projects`
  logical names to ids (finding #4; empty if scoped out).
- Loading is memoized; no network on any of these (NFR-001).

## Validator interface (behavioral)

- `validate(live_projects, live_labels_by_token) -> list[ValidationFinding]` —
  pure function over injected live data; returns all findings (empty == clean).
- CLI wrapper lists live Vikunja once (≤2 calls, NFR-002), prints findings, exits
  non-zero if any finding is present (fail-loud, FR-004).
- **Unreachable path:** if the live list cannot be fetched (network/auth), the
  CLI emits a single `unreachable` finding and exits non-zero as "could not
  validate" — a state deliberately distinct from "registry clean" (FR-004).

## vikunja_scope ownership (finding #5)

`scripts/common/vikunja_scope.py` stays the **selector layer**, but its identity
values become **read-through to the registry** so there is one source:
- `HABIT_SELECTOR` is derived from `selector("habits")` (preserves the
  `{kind, value}` contract already in that module).
- `ESCALATION_EXCLUDED_PROJECT_IDS` **derives** from `project_id("habits")` — it
  no longer restates the literal `[13]`.
- The label-fetch-strategy dispatch remains #716/#717's work; this mission only
  moves the *identity source* into the registry, not the fetch strategy.

## Invariants

- Every logical name a runtime call site uses **must** exist in the registry
  (else `VikunjaRefError` at resolution — FR-003).
- A provisioned `project_id` selector value **must** match the live project whose
  title equals the declared `title`; a mismatch is `id_drift` (FR-004).
- A declared-but-unprovisioned ref (`value: null`) resolves as a loud
  `unprovisioned` error, never as `0`/`None` silently (FR-009).
- The registry never declares felix-bot's own Inbox (C-002) and never declares a
  "someday" project (C-004 — it is a `q:schedule`+no-due-date label state).
- The flat registry does not model sub-project parent/child hierarchy; consumers
  must not expect it.
