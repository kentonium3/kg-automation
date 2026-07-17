# Data Model: Task-Intake Validation Loop

Phase 1 output. Entities, schemas, and validation/state rules derived from the
spec requirements and the R1–R7 research decisions.

## Entities

### Inbox task (Vikunja)
The intake subject — a Vikunja task read from the Inbox project.

| Field | Source | Notes |
|-------|--------|-------|
| `id` | Vikunja | int; the write key |
| `title` | Vikunja | shown in the digest |
| `project_id` | Vikunja | Inbox id (via seam) ⇒ Tier-1-incomplete |
| `labels` | Vikunja | list; scanned for `f:` and `q:` presence |
| `done` | Vikunja | only `done == false` tasks are candidates |
| `due_date` | Vikunja | Tier-2; ET-EOD convention on write |

**Validation / classification rule (FR-002):** Tier-1-complete iff
`project_id != Inbox` **and** ≥1 label in {`f:1-flow`,`f:2-growth`,`f:3-edge`}
(NOT `f:4-overload`) **and** exactly one label in
{`q:do`,`q:schedule`,`q:delegate`,`q:eliminate`}. Otherwise Tier-1-incomplete,
with `missing_fields ⊆ {project, friction, quadrant}`.

### Intake digest / correlation record
The state artifact the scan writes so a later reply can be applied
deterministically. One per inbox tick that finds ≥1 incomplete task. Lives at
`/data/services/openclaw/state/intake/intake-digest-<ET-date>.json` (dir mirrors
the habits state dir). Correlated by the apply step within a bounded window
(default 48h, matching the habits contract).

```json
{
  "digest_id": "intake-2026-07-17T2200Z",
  "created_utc": "2026-07-17T22:00:11Z",
  "created_et_date": "2026-07-17",
  "source_cron": "inbox-5pm",
  "entries": [
    {
      "n": 1,
      "task_id": 412,
      "title": "Draft PointerHealth onboarding deck",
      "missing_fields": ["project", "friction", "quadrant"],
      "tier2_prompted": ["due_date"]
    }
  ]
}
```

**State rules:** append-only per tick (overwrite the same ET-date file on a later
same-day tick with the *current* incomplete set — re-prompt-until-resolved, no
suppression). A task resolved out of Inbox simply does not appear in the next
tick's digest (FR-008/FR-011). The apply step correlates a reply to the
most-recent digest whose `n`→`task_id` mapping the reply's line numbers hit
(habits `correlate_reply_to_checkin` semantics).

### Compact-shorthand reply
Kent's WhatsApp message. Parsed line-by-line; each line independent (FR-005/FR-012).

**Line grammar (deterministic):**
```
<n> <project-token> f<1-4> <quadrant-token> [due:<date>] [habit] [loe:<s|m|l>]
```
- `<n>` — digest number (maps to `task_id` via the correlation record).
- `<project-token>` — a canonical project name or documented short-name/alias
  (case-insensitive), resolved via `vikunja_refs.project_id`.
- `f<1-4>` — friction; `f1`→`f:1-flow`, `f2`→`f:2-growth`, `f3`→`f:3-edge`,
  `f4`→`f:4-overload` (decomposition trigger, FR-009).
- `<quadrant-token>` — `do`|`schedule`|`delegate`|`eliminate` → `q:*`.
- Optional Tier-2: `due:<date>` (ET-EOD write), `habit`→`t:habit`,
  `loe:<s|m|l>`.

**Alias table** (seed; finalized in the contract): friction `f1/f2/f3/f4`;
quadrant `do/sched/schedule/deleg/delegate/elim/eliminate`; project short-names
per the declared projects (e.g. `personal`, `felix`, `clients`, `pointerhealth`,
`spec-kitty`, `intentional`, `habits`). A token not in the alias table and not a
seam-declared name → LLM fallback (R6); still unresolved → echo back (FR-012).

### Apply result
Per-line outcome returned by the apply helper (drives the confirmation message).

```json
{
  "line": 1, "task_id": 412, "status": "applied",
  "applied": {"project": "pointerhealth", "labels": ["f:3-edge","q:schedule"], "due_date": "2026-07-22T23:59:59-04:00"},
  "notes": []
}
```
`status ∈ {applied, echoed_back, noop, overload_flagged}`. `echoed_back` carries
`understood` + `failed` so Kent sees what didn't parse (FR-012). `overload_flagged`
= `f:4` path (FR-009): task flagged for decomposition, not scheduled.

### Per-tick observability artifact
`/data/services/openclaw/state/intake/intake-tick-<ET-date>.json` — mirrors the
habits sweeper tick. Fields: `started_at_utc`, `exit_status`, counts
`{scanned, incomplete, prompted}`, `errors[]` (FR-014). The apply side appends an
`intake-apply-<ET-date>.jsonl` ledger of apply results.

## Seam registry additions (`scripts/common/vikunja_refs.json`)
Declare label ids (owner `kent`) for: `f:1-flow`, `f:2-growth`, `f:3-edge`,
`f:4-overload`, `q:do`, `q:schedule` (present), `q:delegate`, `q:eliminate`,
`t:habit`, `loe:s`, `loe:m`, `loe:l` — each with the live id (reconciled against
the #715 label set, ids ~18–29) and governed by `vikunja_refs_validate.py`.
