# Implementation Plan: Felix Vikunja reference seam + capture routing alignment

**Mission**: vikunja-reference-seam-01KXK68Z
**Branch**: feat/vikunja-reference-seam (merge target: feat/vikunja-reference-seam → main)
**Spec**: [spec.md](./spec.md)
**Issues**: kentonium3/kg-automation#748 + #745 (epic #747)

## Technical Context

**Language/Version**: Python 3.12 (office2 is python3-only; helpers run via `python3 -m scripts.…`)
**Primary Dependencies**: Standard library + existing `scripts/common/vikunja_client.py`, `scripts/common/vikunja_config.py`. No new third-party dependencies.
**Storage**: Committed machine-readable registry file under `scripts/common/` (JSON is authoritative per repo convention); no runtime database.
**Testing**: pytest (unit; all Vikunja effects injected/mocked, no live network in tests).
**Target Platform**: office2 helper/library code consumed by felix-admin-* agents and the sync/security drivers.
**Project Type**: single (Python library + call-site refactor + capture routing change; no service, no API surface).
**Performance Goals**: zero per-resolution network calls on the hot path (NFR-001); validation ≤2 Vikunja list calls (NFR-002).
**Constraints**: no new dependencies; Felix-side code only (no Vikunja config change, C-001); no dependence on is-null date filtering (#725, C-003); provisioning tools exempt (C-005).
**Scale/Scope**: **9 runtime call sites** migrated (inventory in spec.md, not 4 as first drafted) + the #745 capture routing change; ~1 new accessor module + 1 registry data file + 1 validator CLI; capture AGENTS.md prompt edit. Deploys via office2 `git pull` of main for the library/helpers; capture AGENTS.md via `agent-prompt-sync`. Not an audited surface for the library; check rebaseline for the AGENTS.md change (#621, #745 risk note).

## Charter / Constitution Check

Relevant engineering directives (from `docs/design/engineering-principles.md`) and how this plan satisfies them:

- **Single source of truth / integration boundary** — one declared registry replaces scattered by-title and hardcoded-id runtime resolution (FR-001/FR-002); `vikunja_scope.py` reads through it rather than restating ids (finding #5). ✅
- **Fail-loud / single-point-of-failure recovery** — unresolved / unprovisioned / drifted references raise typed errors; drift and unreachability are surfaced loudly by the validator, never silently mis-routed (FR-003/FR-004/FR-009). ✅ (Directly targets the #743 silent-loss class.)
- **Deterministic work (Directive 6)** — resolution, validation, and routing-target selection are fully deterministic; no LLM in the path. Helper/library code, unit-tested independently. ✅
- **JSON validation** — the registry is machine-readable and validated against a schema + against live Vikunja. ✅
- **Migrations leave no vestiges** — the Definition of Done removes the old by-title / hardcoded-id lookups and retires `route_someday`'s Someday-project lookup; no parity path is left behind. ✅
- **Active-surface hygiene** — call sites converge on the seam; dead resolution code is deleted. ✅

No charter conflicts. Charter mode: compact.

## Architecture Overview

Four cooperating pieces, all new/changed on the Felix side only (no Vikunja config change — C-001):

1. **Registry data file** — a committed JSON document declaring, for each logical
   project and label name Felix uses at runtime, its Vikunja identity
   (`{kind, value}` selector), title, owner/owner_token, provisioned flag, and the
   private-project set. Source of truth; matches the "JSON authoritative, code is
   a view" convention.
2. **Typed accessor** (`scripts/common/vikunja_refs.py`, name finalized in tasks) —
   loads the registry once, exposes fail-loud lookups (`project_id`, `label_id`,
   `selector`, `private_project_ids`), raising a typed `VikunjaRefError` on an
   undeclared/unprovisioned name. Committed ids give a network-free hot path
   (NFR-001).
3. **Validator** — a routine (helper CLI + importable function) that lists live
   Vikunja projects+labels once and reports any declared reference that is
   missing, drifted, unprovisioned, or (if the list fails) `unreachable`.
   Fail-loud, on-demand, ≤2 list calls (FR-004 / NFR-002).
4. **Capture routing alignment (#745)** — `route_someday` and the capture
   AGENTS.md are reworked to the post-reset model (below).

### Runtime call-site migration (FR-005 — full inventory in spec.md)

The 9 runtime sites move onto the accessor and their old lookups are deleted:
`route_someday.py`, `vikunja_writer.py`, `vikunja_scope.py`,
`sync/diff.py` (private set), `query_active_habits_v2.py`,
`reconcile_completions.py`, `backfill_jsonl_from_comments.py`,
`query_active_habits_weekly.py` (collapse the mirror), `sync/classify.py`
(`felix:ignore`). The `scripts/vikunja/` provisioning tools + `create_task.py`
are exempt (C-005) and untouched.

### vikunja_scope ownership (finding #5)

`vikunja_scope.py` stays the **selector layer** but sources its identity values
from the registry: `HABIT_SELECTOR` ← `selector("habits")`;
`ESCALATION_EXCLUDED_PROJECT_IDS` **derives** from `project_id("habits")` instead
of restating `[13]`. This keeps one source (registry) while preserving the
`{kind, value}` contract #723 established for the #717 label migration. The
label-fetch-strategy dispatch stays #716/#717's work — this mission moves only
the identity *source*, not the fetch strategy.

### Private-project set (finding #4)

`sync/diff.py`'s `PRIVATE_PROJECT_IDS` (empty `frozenset()` default, threaded
through diff/cycle/emit) is a config-injected set, not a name→id. **Decision:**
encode it in the registry as a `private_projects` list of logical names and have
the accessor resolve it to an id set (`private_project_ids()`), so the privacy
set has one declared home. If seeding reveals no private projects exist yet, the
list is empty and the sync default is unchanged — but the *mechanism* moves onto
the seam rather than staying a bare module constant.

### Capture routing alignment (#745)

- **Fall-through → Inbox (FR-010):** unclassifiable / no-project captures resolve
  `project_id("inbox")` and land in Inbox (id 1). Correct the capture AGENTS.md
  wording that calls "Someday" the safe-fallback bucket.
- **"Someday" → `q:schedule` + no due date (FR-011):** retire
  `find_someday_project`; create the task in Inbox (or the resolved topic
  project) and attach the `q:schedule` label with **no committed due date**.
  `route_someday.py` is reworked (or renamed) accordingly — it no longer looks up
  a "Someday" project.
- **Tier-1 labels (FR-012):** apply project / `f:` / `q:` labels where
  determinable; otherwise leave in Inbox for #749.
- **Preserve routing-log / dedup (FR-013).**

> **Label-application reality (finding #6, #715):** attaching a kent-owned label
> from the felix-bot token returned 403 in #715. Before implementing FR-011/FR-012
> label attachment, live-probe which token attaches `q:schedule` and whether the
> capture path uses it. If felix-bot cannot attach, the routing change must either
> use the kent token for label attach or record the limitation loudly — resolve at
> WP time, do not assume.

## Project Structure (files)

```
scripts/common/
  vikunja_refs.json      (new) — the declared registry (projects + labels + private set, per-token)
  vikunja_refs.py        (new) — typed fail-loud accessor + validator function
  vikunja_scope.py       (edit) — read identity through the registry (finding #5)
scripts/vikunja/
  validate_refs.py       (new, or fold into an existing check) — CLI wrapper for the validator
scripts/inbox/
  route_someday.py       (rework) — retarget to q:schedule+no-due-date; retire Someday-project lookup (#745)
scripts/openclaw/agents/felix-admin-capture/
  AGENTS.md              (edit) — fall-through=Inbox wording; deploy via agent-prompt-sync (#745)
tests/common/
  test_vikunja_refs.py   (new) — accessor + validator unit tests (all effects injected)
# refactored runtime call sites (old lookups removed) — see FR-005 inventory:
scripts/security/credential_health_check/vikunja_writer.py
scripts/sync/diff.py            (private set → registry)
scripts/sync/classify.py        (felix:ignore → registry)
scripts/habits/query_active_habits_v2.py
scripts/habits/reconcile_completions.py
scripts/habits/backfill_jsonl_from_comments.py
scripts/habits/query_active_habits_weekly.py
```

## Phase 0 — Research

See [research.md](./research.md). Resolves: registry representation, id strategy,
label-ownership handling, fail-loud contract, and the drift-validation approach.
No open `[NEEDS CLARIFICATION]` markers remain. **Live-probe items carried to WP
time:** confirm live Habits id = 13 at seed; confirm `felix:ignore` token
resolution + felix-bot visibility; confirm the label-attach token for #745.

## Phase 1 — Design & Contracts

See [data-model.md](./data-model.md) for the registry schema (selector shape,
`private` set, provisioned state), the accessor interface, and the validation
findings (incl. `unprovisioned` / `unreachable`). `contracts/vikunja-refs.contract.md`
captures the accessor + validator behavioral contract (this is a library, not an
HTTP API). [quickstart.md](./quickstart.md) shows a consumer call, a validation
run (incl. the unreachable path), and a #745 routing example.

## Implementation Concern Map (Directive 6 split)

| Concern | Deterministic? | Likely WP |
|---------|----------------|-----------|
| Registry schema + seed data (post-reset names/ids, live-probed) | Yes | WP: registry data + schema |
| Typed accessor with fail-loud lookups (incl. unprovisioned) | Yes | WP: accessor |
| Drift/missing/unprovisioned/unreachable validator (+ CLI) | Yes | WP: validator |
| Migrate 9 runtime call sites; delete old lookups | Yes | WP: call-site migration |
| vikunja_scope read-through + derive escalation exclusion | Yes | WP: call-site migration |
| #745 capture routing (Inbox fallback, q:schedule someday, Tier-1 labels) + AGENTS.md | Yes | WP: capture routing |
| Unit tests (injected effects) + SC-001 acceptance grep | Yes | across WPs |

All work is deterministic — no stochastic/LLM step. Each piece is independently unit-testable.

## Testing Strategy

- Accessor: resolve declared name → id; undeclared → typed raise; unprovisioned
  (`null`) → typed raise; per-token label resolution; `selector()` returns the raw
  shape; no network on the hot path (injected loader).
- Validator: missing → reported; id drift → reported; unprovisioned → reported;
  unreachable → single finding + non-zero; all-good → clean; ≤2 injected list calls.
- Call sites: each refactored site resolves via the seam; regression test that a
  deleted/renamed reference fails loud rather than returning empty (the #743
  guard, SC-002).
- #745 routing: someday block → `q:schedule`+no-due-date task (SC-005);
  unclassifiable → Inbox; routing-log/dedup preserved (FR-013).
- **SC-001 acceptance grep** wired as a test/gate over the migrated surface,
  excluding the C-005 exempt list.

## Risks / Complexity

- **Seeding correct ids:** seed the registry from the *live* post-reset ids
  (Inbox=1, Habits=13, etc.) via a one-time live read; the validator confirms on
  every run. Live-probe Habits=13 before locking.
- **Label per-token subtlety (#715):** resolve/attach labels in the correct
  token's namespace; felix-bot may 403 on kent-owned label attach — resolve the
  attach-token question at WP time (finding #6).
- **Duplicate "Inbox" (id 1 vs felix-bot id 14):** registry pins id 1,
  owner-scoped; felix-bot Inbox excluded (C-002).
- **route_someday is a behavior change, not a swap:** it changes the routing
  target model (#745), so it carries the SC-005 routing tests, not just a resolver
  substitution.

## Migration & Deployment

- Old runtime lookups removed in the same change (no vestiges); `route_someday`
  Someday-project lookup retired.
- Library/helpers deploy via office2 `git pull` of main after
  `feat/vikunja-reference-seam` merges — pure library, no manifest/cron/systemd
  change, so no deploy manifest and no rebaseline required (not an audited
  surface).
- The capture **AGENTS.md** change deploys via `agent-prompt-sync`; agent prompts
  are not hashed (#621) so rebaseline is not required — confirm at merge and
  record `Rebaseline: not required — #621` per the #745 risk note.

## Branch Contract

Current branch: `feat/vikunja-reference-seam`. Planning/base branch:
`feat/vikunja-reference-seam`. Mission merges into `feat/vikunja-reference-seam`;
the feature branch then merges to `main` separately.
