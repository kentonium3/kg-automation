# Implementation Plan: Vikunja token seam + kent cutover (phase 2 of #860)

**Branch**: `feat/vikunja-token-seam-kent-cutover` | **Date**: 2026-07-23 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `kitty-specs/vikunja-token-seam-kent-cutover-01KY8XQ0/spec.md`

## Summary

Finish the Vikunja token seam Phase 1 left half-done, then flip the runtime identity felix-bot → kent.
Concretely: introduce a single `get_vikunja_token_path()` resolution point in
`scripts/common/vikunja_config.py`, route every runtime consumer through it (behavior-preserving,
still felix-bot), prove the single-point property with a test, then flip that one point to the kent
token, retire the felix-bot runtime credential (dormant-not-deleted), converge the #748 validator,
reconcile the ADR/identity/credential docs + agent skill/tool references, and run the attended
Tier-2 cutover on office2. Sequenced so the behavior-preserving refactor and the intentional
identity change are separate, independently-reviewable steps.

## Technical Context

**Language/Version**: Python 3.12 (office2 is python3-only)
**Primary Dependencies**: stdlib only (`urllib`, `pathlib`, `os`) — no new deps; the shared
`scripts/common/vikunja_client.py` + `scripts/common/vikunja_config.py` are the seam.
**Storage**: plaintext token files on office2 (`/data/services/openclaw/secrets/{vikunja-api,vikunja-api-kent}`,
mode 600); no DB schema change. Vikunja server state untouched (identity of the *caller* changes, not data).
**Testing**: pytest; per-consumer parity tests (request + domain/CLI boundary) from Phase 1 stay green
pre-flip (NFR-001); a new single-point-flip test (SC-002); the `tests/architectural/` ratchets.
**Target Platform**: Linux (office2, Ubuntu 24.04); deployed via checkout self-pull (no manifest for the
code change; the credential-manifest doc edit is an audited-surface change → rebaseline obligation).
**Project Type**: single project (scripts/ + tests/).
**Performance Goals**: N/A (identity/config change; no hot path affected).
**Constraints**: behavior-preserving until the flip; single atomic flip (no split-brain); Tier-2 attended
cutover with before/after connectivity verification + Restic snapshot ≤24h.
**Scale/Scope**: ~13 runtime consumer modules + 1 config helper; ~6 docs/ADR; 1 credential-manifest entry.

## Charter Check

*GATE: Must pass before Phase 0. Re-checked after Phase 1.*

- **DIRECTIVE_001 (Architectural Integrity) — separation of concerns**: PASS — the mission's entire
  purpose is to make the token-resolution concern independently owned by one seam (`get_vikunja_token_path()`),
  replaceable without cascading edits. Directly advances this directive.
- **DIRECTIVE_024 (Locality of Change)**: PASS — after this mission a Vikunja identity change is one line at
  one point; today it is N points. Reduces future blast radius.
- **DIRECTIVE_031 (Context-Aware Design)**: PASS — the seam is the explicit translation layer between Felix
  reasoning and the Vikunja adapter; no new implicit cross-boundary coupling (and no abstract port — C-001).
- **DIRECTIVE_010 (Specification Fidelity)**: PASS — SC-001 is an explicit, enforceable gate (the corrective
  for Phase 1's relaxed acceptance); no criterion may be narrowed at accept without re-checking its property.
- **Change-Risk Taxonomy / Tier Protocol**: the code centralization is Tier 3 (logic); the credential-manifest
  edit + office2 token cutover is **Tier 2 (application/state) attended**, snapshot-gated (Restic ≤24h) with
  before/after connectivity verification.
- **Rebaseline Obligation (#557)**: the credential-manifest is an audited surface → rebaseline outcome recorded
  at merge (SC-005).

## Project Structure

### Documentation (this mission)

```
kitty-specs/vikunja-token-seam-kent-cutover-01KY8XQ0/
├── plan.md            # this file
├── research.md        # Phase 0
├── data-model.md      # Phase 1
├── quickstart.md      # Phase 1
├── contracts/         # Phase 1 (internal-refactor note — no new external API)
└── tasks.md           # Phase 2 (/spec-kitty.tasks — not created here)
```

### Source code (touched)

```
scripts/common/vikunja_config.py          # + get_vikunja_token_path() — the single resolution point (IC-01)
scripts/common/vikunja_client.py          # default-token load routes through IC-01 (IC-02)
scripts/habits/{sweeper,record_completion,exclude_completed,set_due_dates,
                identify_workout_task,migrate_schedule}.py   # drop own DEFAULT_TOKEN_PATH literal → IC-01 (IC-03)
scripts/sync/{cycle,fetch}.py             # token resolves via IC-01 (IC-03)
scripts/security/credential_health_check/vikunja_writer.py   # VIKUNJA_TOKEN_PATH → IC-01 (IC-03)
scripts/inbox/route_someday.py            # remove felix-bot 403 fail-soft branch (#750) (IC-05)
scripts/vikunja/validate_refs.py          # converge onto runtime token view (#748) (IC-05)
docs/design/architecture/adr/0007-*.md    # NEW ADR (IC-06)
docs/design/architecture/{identity-model,credentials-and-secrets,service-inventory,data-flows}.md
docs/design/architecture/data/{credential-manifest,service-inventory,data-flows}.json   # (IC-06)
scripts/openclaw/skills/vikunja-api/SKILL.md + escalation/SKILL.md
scripts/openclaw/agents/felix-admin-tasker/{TOOLS,AGENTS}.md   # token refs (#831) (IC-06)
tests/…                                    # single-point-flip proof (SC-002) + parity stays green (IC-01/04)
```

## Implementation Concern Map

| IC | Concern | Maps to | Notes |
|----|---------|---------|-------|
| IC-01 | **Single resolution point.** Add `get_vikunja_token_path()` (env `VIKUNJA_TOKEN_PATH` → canonical default `…/vikunja-api` for now); unit tests incl. env override + fail-loud. | FR-001, NFR-002, SC-002 | Foundation. Default stays felix-bot at this step. |
| IC-02 | Route `VikunjaClient` default-token loading through IC-01 (replace module `DEFAULT_TOKEN_PATH` literal). | FR-001 | Group-A consumers (bare `VikunjaClient()`) inherit IC-01 automatically. |
| IC-03 | Route the self-loading consumers through IC-01: 6 habits scripts, `sync/{cycle,fetch}`, `credential_health_check/vikunja_writer`. Remove their felix-bot `DEFAULT_TOKEN_PATH` literals; `--token-path` CLI defaults → `get_vikunja_token_path()`. | FR-001, FR-002, NFR-001 | Behavior-preserving; parity suite green, still felix-bot. |
| IC-04 | **The flip.** Change IC-01's default `vikunja-api` → `vikunja-api-kent`. Add the single-point-flip proof test. | FR-003, SC-002 | One line + one test. |
| IC-05 | Retire felix-bot runtime path: remove `route_someday` 403 fail-soft (#750); mark `vikunja-api` credential dormant/non-runtime in the manifest; converge `validate_refs.py` on the runtime token (#748, FR-005). | FR-004, FR-005 | |
| IC-06 | Docs/ADR: ADR-0007 (supersede ADR-0002 rationale); identity-model, credentials-and-secrets, service-inventory, data-flows; SKILL/TOOLS/AGENTS token refs + SKILL v2.4.0 + health-check fix (#831). | FR-006 | |
| IC-07 | **Attended Tier-2 cutover** (post-merge-to-feat, before feat→main): before/after connectivity per consumer; inverse probe (kent sees 16–20 + Inbox 1); rebaseline record. | FR-007, SC-004, SC-005 | Operator step — hard-stop for Kent; not a code WP. |

## Sequencing

1. **Centralize (behavior-preserving, still felix-bot)**: IC-01 → IC-02 ‖ IC-03. Gate: full affected suite +
   `tests/architectural/` green; resolved token unchanged (felix-bot). This is the "finish Phase 1" step and
   is independently deployable with no cutover.
2. **Flip (intentional identity change)**: IC-04. Gate: SC-002 single-point-flip test; suite green.
3. **Retire + docs**: IC-05, IC-06.
4. **Cutover**: IC-07 — attended, Tier-2, before/after connectivity, inverse probe, rebaseline. Hard-stop
   for Kent before anything reaches `main` (merge to main is the office2 deploy trigger).

## Architecture Impact (signal-to-doc-map)

Change classes: `credential-added-or-modified` (retire `vikunja-api` runtime credential),
`architecture-doc-added` (ADR-0007). To be finalized against `docs/design/architecture/data/signal-to-doc-map.json`
in research; doc targets enumerated in IC-06 + spec §Architecture Impact. `docs/INDEX.md` (and
`DEVELOPER_PORTAL.md` if the ADR is surfaced) updated for the new ADR.

## Complexity / risk notes

- **Highest-care module: `sync`** (bidirectional; a token change alters which user's tasks it reconciles) —
  its Phase-1 parity surface (cycle_error classification, cache guards, ordering) must stay green through IC-03
  and be spot-verified live at IC-07.
- **Split-brain avoidance**: IC-04 is a single change to one point; there is never a mixed-identity window.
- **Fail-safe**: IC-01 fails loud on a missing/unreadable token (NFR-002); no silent fallback to an old path.
