# Data Model — Reconcile Target

This mission adds no new entities. It corrects fields on an existing record shape.

## Entity: Agent inventory entry (`service-inventory.json`)

Each Felix OpenClaw agent is a keyed object under the OpenClaw-agents grouping in
`docs/design/architecture/data/service-inventory.json`. Fields relevant to this reconcile:

| Field | Meaning | Reconcile rule |
|---|---|---|
| `model` | The agent's configured model. | MUST equal live `openclaw.json` value. **habits, tasker → `anthropic/claude-haiku-4-5`** (were `sonnet-4-6`). Others already correct. |
| `skills` | The agent's per-agent skills list (REPLACE semantics in OpenClaw). | MUST equal the live Step-2-deployed array. **calendar → `[]`** (was fictional `["calendar","gog"]`; #699 removed gog). |
| exec posture (narrative/notes) | The agent's `tools.exec` security. | Record as `security: full` fleet-wide (no per-agent restriction deployed); note the exec-allowlist finding rather than claiming allowlist containment. |
| `updated_by` | Provenance string (mission-slug + issue refs). | Append this mission's provenance; preserve the existing convention/format. |

### Invariants

- **INV-1 — JSON authoritative:** the narrative markdown view MUST agree with the JSON; on conflict, JSON wins.
- **INV-2 — Live-config truth:** where the inventory disagrees with live `openclaw.json`, the *live* value is correct (this is a "docs were wrong," not "config is wrong," reconcile — no config change).
- **INV-3 — Validator-clean:** the edited JSON MUST pass `tooling/scripts/validate_architecture_data.py`.
- **INV-4 — gog ownership:** exactly one recorded gog user post-#699: **`main`** (email + drive). No worker (including calendar) uses gog.

### Ground-truth reference

The authoritative live snapshot to reconcile against is captured in
[research.md](./research.md) → "Decision 2 — Reconcile target."

## No API contracts

This is a documentation/governance mission — no endpoints, events, or wire contracts.
`contracts/` is intentionally empty.
