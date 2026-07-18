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

### Intake digest / correlation record (FR-016)
The state artifact the scan writes so a later reply can be applied
deterministically. **One immutable file per `digest_id`** (never an overwritten
same-day file — 4 ticks/day would otherwise let a delayed reply map number `1` to
a different task):
`/data/services/openclaw/state/intake/digests/intake-<digest_id>.json`, plus a
`latest.json` pointer. Files older than the retention window (48h, habits parity)
are expired.

```json
{
  "digest_id": "2026-07-17T2200Z-inbox-5pm",
  "created_utc": "2026-07-17T22:00:11Z",
  "created_et_date": "2026-07-17",
  "source_cron": "inbox-5pm",
  "entries": [
    {
      "n": 1,
      "task_id": 412,
      "title": "Draft PointerHealth onboarding deck",
      "missing_fields": ["project", "friction", "quadrant"]
    }
  ]
}
```
(No `tier2_prompted` at scan time — Tier-2 applicability depends on the reply's
quadrant and is evaluated at apply time, FR-010.)

**Correlation (habits `correlate_reply_to_checkin` semantics, FR-016):** the apply
step selects the digest whose entries best match the reply — by the reply's
**line-number set AND task-title/content evidence**, within the 48h window —
never by position in the newest file alone. If a reply line's number maps to no
unambiguous task across live digests, that line is `echoed_back` (FR-012). A task
resolved out of Inbox simply does not appear in later digests (FR-008/FR-011);
re-prompt-until-resolved is achieved by each tick writing a fresh digest of the
*current* incomplete set, not by mutating an old one.

### Compact-shorthand reply
Kent's WhatsApp message. Parsed line-by-line; each line independent (FR-005/FR-012).

**Line grammar (deterministic, sparse — FR-005):** every token after `<n>` is
**optional**; a line supplies only the fields the digest reported missing.
```
<n> [project-token] [f<1-4>] [quadrant-token] [due:<date>] [habit] [loe:<s|m|l>]
```
- `<n>` — digest number (correlated to `task_id` per FR-016).
- `project-token` — a canonical project name or documented short-name/alias
  (case-insensitive), resolved via `vikunja_refs.project_id`.
- `f<1-4>` — friction; `f1/f2/f3`→schedulable, `f4`→`f:4-overload`
  (decomposition-pending, FR-009). Applying a new `f:` replaces any existing
  `f:`-family label (FR-013 family-replace).
- `quadrant-token` — `do`|`sched`|`schedule`|`deleg`|`delegate`|`elim`|`eliminate`
  → `q:*`. Applying a new `q:` replaces any existing `q:`-family label.
  `eliminate` → mark the task done (FR-008).
- Optional Tier-2: `due:<date>` (ET-EOD write), `habit`→`t:habit`,
  `loe:<s|m|l>` — governed by the Tier-2 compatibility matrix below.
- A line that supplies a field the task already has valid → treated as an
  explicit correction (family-replace), not an error.

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
`status ∈ {applied, echoed_back, noop, overload_flagged, not_found, already_done,
moved_conflict, access_denied}` (FR-012). `echoed_back` carries `understood` +
`failed`. `overload_flagged` = `f:4` decomposition-pending (FR-009). `noop` **only**
when live project/labels/due already match the intended values, or the task is
done/deleted (FR-013) — a partially-resolved task still gets its still-missing
fields. `moved_conflict` = task left Inbox by another process between digest and
reply; `not_found`/`already_done`/`access_denied` per FR-012. Each line's status is
independent (one failing line never blocks the rest).

### Tier-2 compatibility matrix (FR-017)
| Tier-2 token | with `q:do`/`q:schedule` | with `q:delegate` | with `q:eliminate` / `f:4` | malformed |
|---|---|---|---|---|
| `due:<date>` | apply (ET-EOD); if absent → non-blocking follow-up | apply if given | **ignore-with-note** | echo-back |
| `habit` | apply `t:habit`; if task already recurring → note, no double-recurrence | apply | ignore-with-note | — |
| `loe:<s\|m\|l>` | apply | apply | apply | echo-back |

### Label family-replace rule (FR-013)
`q:*` are mutually exclusive; `f:1/f:2/f:3/f:4` are mutually exclusive. Applying a
new member of a family **removes the prior member of that family** and attaches the
new one via read-modify-write; all **non-family** labels (e.g. `t:habit`, `loe:*`,
domain labels) are preserved untouched. A task must never end with two `q:` or two
`f:` labels.

### Per-tick observability artifact (FR-014)
`/data/services/openclaw/state/intake/intake-tick-<ET-date>.json` — mirrors the
habits sweeper tick. Scan fields: `started_at_utc`, `exit_status`,
`{scanned, incomplete, prompted}`, `errors[]`. **Apply aggregates** (same file or a
rolled-up daily summary): `{applied, echoed_back, overload_flagged, noop,
not_found, already_done, moved_conflict, access_denied, failed}`, satisfying
FR-014's per-tick observability. The apply side also appends an
`intake-apply-<ET-date>.jsonl` ledger of individual `ApplyResult`s.

## Seam registry additions (`scripts/common/vikunja_refs.json`)
Declare label ids (owner `kent`) for: `f:1-flow`, `f:2-growth`, `f:3-edge`,
`f:4-overload`, `q:do`, `q:schedule` (present), `q:delegate`, `q:eliminate`,
`t:habit`, `loe:s`, `loe:m`, `loe:l` — each with the live id (reconciled against
the #715 label set, ids ~18–29) and governed by `vikunja_refs_validate.py`.
