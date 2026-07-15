# Data Model: Felix Vikunja reference-resolution seam

## Registry file (JSON — authoritative)

Conceptual shape (field names finalized during implementation):

```json
{
  "schema_version": 1,
  "source_of_truth": "docs/design/vikunja-configuration-design.md",
  "last_verified_utc": "2026-07-15T00:00:00Z",
  "projects": [
    { "name": "inbox", "vikunja_id": 1, "title": "Inbox", "owner": "kent" },
    { "name": "habits", "vikunja_id": 13, "title": "Habits", "owner": "kent" },
    { "name": "personal", "vikunja_id": null, "title": "Personal", "owner": "kent" }
    /* … Felix/kg-automation, Clients, PointerHealth, spec-kitty, Metal Casework, CT-90day … */
  ],
  "labels": [
    { "name": "q:schedule", "vikunja_id": null, "owner_token": "kent" },
    { "name": "t:habit", "vikunja_id": null, "owner_token": "kent" }
    /* … f:1..f:4, q:*, loe:* … */
  ]
}
```

### Entities

**ProjectRef**
- `name` — logical key Felix code uses (stable; snake/lower).
- `vikunja_id` — pinned integer id (the fast-path identity).
- `title` — the human title as it exists in Vikunja (used by the validator to detect drift).
- `owner` — owning user (kent); felix-bot's own Inbox is intentionally *not* declared (C-002).

**LabelRef**
- `name` — canonical label string (e.g. `q:schedule`).
- `vikunja_id` — pinned label id.
- `owner_token` — which token's namespace the id belongs to (#715).

**ValidationFinding**
- `kind` — `missing` | `id_drift` | `title_drift`.
- `ref_type` — `project` | `label`.
- `name` — the logical name affected.
- `detail` — human string (expected vs live).

## Accessor interface (behavioral)

- `project_id(name) -> int` — returns the pinned id; raises `VikunjaRefError` if `name` is undeclared.
- `label_id(name, owner_token) -> int` — returns the pinned id in that token's namespace; raises `VikunjaRefError` if undeclared for that token.
- `project_title(name) -> str` — the declared title (for validator/reporting).
- Loading is memoized; no network on any of these (NFR-001).

## Validator interface (behavioral)

- `validate(live_projects, live_labels_by_token) -> list[ValidationFinding]` — pure function over injected live data; returns all findings (empty == clean).
- CLI wrapper lists live Vikunja once (≤2 calls, NFR-002), prints findings, exits non-zero if any finding is present (fail-loud, FR-004).

## Invariants

- Every logical name a call site uses **must** exist in the registry (else `VikunjaRefError` at resolution — FR-003).
- `vikunja_id` for a declared name **must** match the live project/label whose title equals the declared `title`; a mismatch is `id_drift` (FR-004).
- The registry never declares felix-bot's own Inbox (C-002).
