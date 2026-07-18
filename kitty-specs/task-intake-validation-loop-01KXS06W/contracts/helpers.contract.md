# Contract: Intake helper CLIs

Both helpers are deterministic (no LLM), invoked as `python3 -m scripts.intake.<helper>`
(C-001), import `scripts.common.vikunja_refs`, emit JSON on stdout, and bound
every external call with a timeout (NFR-005).

## `scripts.intake.scan_inbox`

**Purpose:** deterministically enumerate not-done Inbox tasks, classify Tier-1
completeness, write the correlation record + tick artifact, and return the
numbered digest text.

**Reads:** felix-bot token (default `VikunjaClient`); Inbox id via
`vikunja_refs.project_id("inbox")`; `GET /tasks/all` paginated, done-inclusive,
filtered to `project_id == inbox && done == false`.

| Flag | Meaning |
|------|---------|
| `--state-dir <path>` | default `/data/services/openclaw/state/intake` |
| `--now-utc <iso>` | injectable clock (testing; no `Date.now()`-style nondeterminism) |
| `--dry-run` | classify + render digest, **do not** write the correlation record |
| `--json` | machine output |

**Writes (unless `--dry-run`):** an **immutable** `digests/intake-<digest_id>.json`
+ `latest.json` pointer (never an overwritten same-day file — FR-016), and
`intake-tick-<ET-date>.json`. Digests older than `--window-hours` are expired.

**Stdout JSON:** `{status, digest_id, scanned, incomplete, entries:[{n,task_id,title,missing_fields}], digest_text}`.
`incomplete == 0` ⇒ `digest_text` empty, no message sent (SC-009). Exit non-zero
only on infrastructure failure (never on "0 incomplete").

## `scripts.intake.apply_reply`

**Purpose:** parse Kent's compact-shorthand reply, resolve tokens via the seam,
and apply project + labels + Tier-2 via the kent token (read-modify-write).

**Reads:** the correlation record (most-recent within the window, R1);
`vikunja_refs.project_id` / `label_id(name, "kent")`.
**Writes:** kent token from `/data/services/openclaw/secrets/vikunja-api-kent`
(never felix-bot); `GET /tasks/<id>` → merge → `POST /tasks/<id>` with readback
diff (C-005/FR-013).

| Flag | Meaning |
|------|---------|
| `--reply-file <path>` / `--reply -` | the reply text (stdin) |
| `--state-dir <path>` | correlation-record location |
| `--window-hours <n>` | default 48 (habits parity) |
| `--unresolved <json>` | **constrained** LLM-fallback input (FR-006): a list of `{line, token, position, canonical_name}` only. The helper **re-resolves** each `canonical_name` through `vikunja_refs`; raw ids or free-form label/project values are rejected. Never a channel for arbitrary values. |
| `--dry-run` | resolve + plan, no writes |
| `--json` | machine output |

**Correlation:** selects the digest by the reply's line-number set + task-title
evidence within `--window-hours` (FR-016), not by newest-file position.

**Stdout JSON:** `{digest_id, results:[ApplyResult...], aggregates:{applied, echoed_back, overload_flagged, noop, not_found, already_done, moved_conflict, access_denied, failed}}`.

**Invariants:**
- Sparse lines apply only the supplied fields; already-valid fields are left intact (FR-005).
- Every line yields an independent status in `{applied, echoed_back, overload_flagged, noop, not_found, already_done, moved_conflict, access_denied}` (FR-012); one failing line never blocks the rest.
- A line whose token is unresolved (and not covered by `--unresolved`) → `echoed_back` with `understood`/`failed`.
- `f:4` → `overload_flagged`, decomposition-pending, **not** scheduled; it stops re-prompting (FR-009).
- **Family-replace:** a new `q:`/`f:` replaces the same-family label; non-family labels preserved; never two quadrants (FR-013). Verified by readback diff (NFR-003).
- `noop` **only** when live project/labels/due already match the intended values, or the task is done/deleted — a partially-resolved task still gets its missing fields (FR-013).
- Tier-2 governed by the compatibility matrix (FR-017): `due:` ET-EOD on `q:do`/`q:schedule`, ignored-with-note on `q:eliminate`/`f:4`; malformed `loe:`/`due:` → `echoed_back`; missing Tier-2 never blocks Tier-1 (FR-010). A `q:do`/`q:schedule` apply with no `due:` emits a non-blocking follow-up.
- `q:eliminate` marks the task done rather than requiring a working project (FR-008).
