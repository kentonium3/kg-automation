# Implementation Plan: Felix Vikunja reference-resolution seam

**Mission**: vikunja-reference-seam-01KXK68Z
**Branch**: feat/vikunja-reference-seam (merge target: feat/vikunja-reference-seam → main)
**Spec**: [spec.md](./spec.md)
**Issue**: kentonium3/kg-automation#748 (epic #747)

## Technical Context

**Language/Version**: Python 3.12 (office2 is python3-only; helpers run via `python3 -m scripts.…`)
**Primary Dependencies**: Standard library + existing `scripts/common/vikunja_client.py`, `scripts/common/vikunja_config.py`. No new third-party dependencies.
**Storage**: Committed machine-readable registry file under `scripts/common/` (JSON is authoritative per repo convention); no runtime database.
**Testing**: pytest (unit; all Vikunja effects injected/mocked, no live network in tests).
**Target Platform**: office2 helper/library code consumed by felix-admin-* agents and the sync/security drivers.
**Project Type**: single (Python library + call-site refactor; no service, no API surface).
**Performance Goals**: zero per-resolution network calls on the hot path (NFR-001); validation ≤2 Vikunja list calls (NFR-002).
**Constraints**: no new dependencies; Felix-side code only (no Vikunja config change, C-001); no dependence on is-null date filtering (#725, C-003).
**Scale/Scope**: 4 call sites migrated; ~1 new accessor module + 1 registry data file + 1 validator CLI; deploys via office2 `git pull` of main (no manifest/cron/systemd change; not an audited surface).

## Charter / Constitution Check

Relevant engineering directives (from `docs/design/engineering-principles.md`) and how this plan satisfies them:

- **Single source of truth / integration boundary** — one declared registry replaces scattered by-title and hardcoded-id resolution (FR-001/FR-002). ✅
- **Fail-loud / single-point-of-failure recovery** — unresolved references raise typed errors; drift is surfaced loudly by the validator, never silently mis-routed (FR-003/FR-004). ✅ (Directly targets the #743 silent-loss class.)
- **Deterministic work (Directive 6)** — resolution and validation are fully deterministic; no LLM in the path. Both are helper/library code, unit-tested independently. ✅
- **JSON validation** — the registry is machine-readable and validated against a schema + against live Vikunja. ✅
- **Migrations leave no vestiges** — the mission's Definition of Done removes the old by-title / hardcoded-id lookups; no parity path is left behind. ✅
- **Active-surface hygiene** — call sites converge on the seam; dead resolution code is deleted. ✅

No charter conflicts. Charter mode: compact.

## Architecture Overview

Three cooperating pieces, all new/changed on the Felix side only (no Vikunja config change — C-001):

1. **Registry data file** — a committed JSON document declaring, for each logical project and label name Felix uses, its Vikunja identity (id + optional selector) and owning token. Source of truth; matches the "JSON authoritative, code is a view" convention (Q1).
2. **Typed accessor** (`scripts/common/vikunja_refs.py`, name finalized in tasks) — loads the registry once, exposes fail-loud lookups (`project_id(name)`, `label_id(name, token)`), raising a typed `VikunjaRefError` on an undeclared name. Committed ids give a network-free hot path (Q2 / NFR-001).
3. **Validator** — a routine (helper CLI + importable function) that lists live Vikunja projects+labels once and reports any declared reference that is missing or whose id no longer matches the recorded name (drift). Fail-loud, on-demand, ≤2 list calls (FR-004 / NFR-002).

**Call-site migration:** the four known resolution sites move onto the accessor and their old lookups are deleted (FR-005):
- `scripts/inbox/route_someday.py` — `find_someday_project` by-title lookup
- `scripts/security/credential_health_check/vikunja_writer.py` — `lookup_inbox_project_id` by-title
- `scripts/common/vikunja_scope.py` — hardcoded habits `project_id: 13`
- `scripts/sync/` — `PRIVATE_PROJECT_IDS` constant

**Label ownership (FR-006):** labels are per-token (#715). The registry records the owning token per label; the accessor resolves within that namespace or fails loud.

## Project Structure (files)

```
scripts/common/
  vikunja_refs.json      (new) — the declared registry (projects + labels, per-token)
  vikunja_refs.py        (new) — typed fail-loud accessor + validator function
scripts/vikunja/
  validate_refs.py       (new, or fold into an existing check) — CLI wrapper for the validator
tests/common/
  test_vikunja_refs.py   (new) — accessor + validator unit tests (all effects injected)
# refactored call sites (old lookups removed):
scripts/inbox/route_someday.py
scripts/security/credential_health_check/vikunja_writer.py
scripts/common/vikunja_scope.py
scripts/sync/…            (PRIVATE_PROJECT_IDS source)
```

## Phase 0 — Research

See [research.md](./research.md). Resolves: registry representation (Q1), id strategy (Q2), label-ownership handling, fail-loud contract, and the drift-validation approach. No open `[NEEDS CLARIFICATION]` markers remain.

## Phase 1 — Design & Contracts

See [data-model.md](./data-model.md) for the registry schema, the accessor interface, and the validation-report shape. `contracts/vikunja-refs.contract.md` captures the accessor + validator behavioral contract (this is a library, not an HTTP API — the "contract" is the function/CLI interface + error semantics). [quickstart.md](./quickstart.md) shows a consumer call and a validation run.

## Implementation Concern Map (Directive 6 split)

| Concern | Deterministic? | Likely WP |
|---------|----------------|-----------|
| Registry schema + seed data (post-reset names/ids) | Yes | WP: registry data + schema |
| Typed accessor with fail-loud lookups | Yes | WP: accessor |
| Drift/missing validator (+ CLI) | Yes | WP: validator |
| Migrate 4 call sites; delete old lookups | Yes | WP: call-site migration |
| Unit tests (injected effects) | Yes | across WPs |

All work is deterministic — no stochastic/LLM step. Each piece is independently unit-testable.

## Testing Strategy

- Accessor: resolve declared name → id; undeclared name → typed raise; per-token label resolution; no network on the hot path (injected loader).
- Validator: missing reference → reported; id drift → reported; all-good → clean; ≤2 injected list calls.
- Call sites: each refactored site resolves via the seam; regression test that a deleted/renamed reference fails loud rather than returning empty (the #743 guard, SC-002).

## Risks / Complexity

- **Seeding correct ids:** the registry must be seeded from the *live* post-reset ids (Inbox=1, Habits=13, etc.). Mitigation: seed via a one-time live read + the validator confirms on every run.
- **Label per-token subtlety (#715):** must resolve labels in the correct token's namespace. Mitigation: record owning token in the registry; validator checks per-token.
- **Duplicate "Inbox" (id 1 vs felix-bot id 14):** registry pins id 1, owner-scoped; felix-bot Inbox excluded (C-002).

## Migration & Deployment

- Old lookups removed in the same change (no vestiges).
- Deploys via office2 `git pull` of main after `feat/vikunja-reference-seam` merges — pure library, no manifest/cron/systemd change, so no deploy manifest and no rebaseline required (not an audited surface).

## Branch Contract

Current branch: `feat/vikunja-reference-seam`. Planning/base branch: `feat/vikunja-reference-seam`. Mission merges into `feat/vikunja-reference-seam`; the feature branch then merges to `main` separately.
