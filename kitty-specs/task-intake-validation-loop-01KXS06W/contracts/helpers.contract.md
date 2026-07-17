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

**Writes (unless `--dry-run`):** `intake-digest-<ET-date>.json` (overwrite per ET
date), `intake-tick-<ET-date>.json`.

**Stdout JSON:** `{status, scanned, incomplete, entries:[{n,task_id,title,missing_fields,tier2_prompted}], digest_text}`.
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
| `--unresolved <json>` | optional map of LLM-resolved tokens the agent supplies for genuine ambiguity only (R6) |
| `--dry-run` | resolve + plan, no writes |
| `--json` | machine output |

**Stdout JSON:** `{results:[ApplyResult...], applied, echoed_back, overload_flagged, noop}`.

**Invariants:**
- A line whose token is unresolved (and not in `--unresolved`) → `echoed_back`
  with `understood`/`failed`; other well-formed lines still apply (FR-012).
- `f:4` → `overload_flagged`, task **not** given a working-project schedule (FR-009).
- Applying labels/project never removes pre-existing labels or zeros unstated
  fields; verified by readback diff (NFR-003). Re-applying the same reply, or a
  task already Tier-1-complete / done, is a `noop` (FR-013).
- Tier-2 `due:` written as ET end-of-day (R4). Missing Tier-2 never blocks Tier-1
  apply (FR-010).
