# Implementation Plan: Consolidate Felix→Vikunja onto the shared client (phase 1 of #860)

**Branch**: `fix/860-retire-vikunja-felix-bot` | **Date**: 2026-07-23 | **Spec**: [spec.md](./spec.md)
**Input**: `kitty-specs/retire-vikunja-felix-bot-01KY829X/spec.md` | **Source issue**: kentonium3/kg-automation#860 (Epic #531)

## Summary

**Phase 1 of a two-phase execution.** Migrate every runtime Felix→Vikunja consumer that currently
uses hand-loaded tokens + raw HTTP onto the shared `VikunjaClient`, **behavior-preserving** (still
the felix-bot token — no identity change). Extend `VikunjaClient` where it lacks an operation a
consumer needs. This establishes the Epic #531 boundary / EA-§11 task seam and touches no live
auth. **Phase 2** (a follow-on **kitty-light** change under #860) does the atomic token flip to
kent + felix-bot Vikunja retirement + the attended Tier-2 cutover — safe to reduce to a one-liner
*because* Phase 1 already put everyone on the client.

## Technical Context

**Language/Version**: Python 3 (office2 python3-only).
**Primary Dependencies**: `scripts/common/vikunja_client.py` (the boundary — extended here).
**Storage**: unchanged (still reads `/data/services/openclaw/secrets/vikunja-api`, the felix-bot token).
**Testing**: per-consumer **parity** tests (mock/record the HTTP each consumer issues; prove the
migrated path produces the same requests/effects); new `VikunjaClient` method unit tests; the full
Vikunja/inbox/habits/escalation/enrichment/trust suite stays green.
**Target Platform**: office2. Checkout-resident (self-pull). Behavior-preserving → **no cutover, no
Tier-2 hold** in this phase (that's Phase 2).
**Project Type**: single.
**Constraints**: no identity/token change (C-001); single boundary (C-002); no abstract port (C-003).
**Scale/Scope**: extend `VikunjaClient` + migrate ~13 runtime files (6 raw-HTTP modules;
habits = 7 scripts). **Large refactor — the bulk of #860's engineering.**

### Environment probe results (DIR-015 — verified live on office2, 2026-07-23)

- Consumer inventory (grep-confirmed): raw-HTTP direct-token consumers = `sync/cycle.py`,
  `escalation/{record_completion,reconcile_completions}.py`, `enrichment/{record_completion,
  reconcile_completions}.py`, `habits/{sweeper,set_due_dates,record_completion,exclude_completed,
  identify_workout_task,migrate_schedule,backfill_jsonl_from_comments}.py`,
  `security/credential_health_check/vikunja_writer.py`. `intake/apply_reply.py` **already** uses
  `VikunjaClient`. Admin/one-shot scripts are not runtime consumers.
- HTTP profile: escalation/enrichment/habits/credential-health modules each issue ~7–10 raw
  urllib calls → each needs its ops mapped onto `VikunjaClient` methods.
- The felix-bot secret file is present + non-empty (unchanged this phase).

### Deploy & rebaseline

- Deploy = checkout self-pull; no restart (clients read the token per-call). No credential/service
  change. `scripts/**` matches no audited-surface pattern → **Rebaseline: not required**. No deploy
  manifest (nothing imperative to do).

## Charter Check

*GATE: passed (compact charter).*
- **DIR-006 (deterministic)**: mechanical, behavior-preserving migration. ✅
- **DIR-015 (probe)**: office2 probe + full consumer inventory done. ✅
- **Single source of truth / boundary (C-002)** + **§11 seam-not-port (C-003)**. ✅
- **Test discipline**: per-consumer parity tests are the core acceptance gate. ✅
- *(DIR-014 doc-sync, Tier-1/2, ADR — all deferred to Phase 2; this phase changes no docs/credentials.)*

## Project Structure

```
scripts/common/vikunja_client.py     # MODIFIED — add methods to cover consumer ops (FR-002). NO default change.
scripts/sync/cycle.py                # MIGRATE — raw HTTP → VikunjaClient (bidirectional sync — highest stakes)
scripts/escalation/{record_completion,reconcile_completions}.py   # MIGRATE
scripts/enrichment/{record_completion,reconcile_completions}.py   # MIGRATE
scripts/habits/{sweeper,set_due_dates,record_completion,exclude_completed,identify_workout_task,migrate_schedule,backfill_jsonl_from_comments}.py  # MIGRATE
scripts/security/credential_health_check/vikunja_writer.py        # MIGRATE
tests/**                             # NEW/MODIFIED — VikunjaClient method tests + per-consumer parity tests
```

## Implementation Concern Map

### IC-01 — `VikunjaClient` boundary completeness (FR-002)

- **Purpose**: make the client cover every operation the raw-HTTP consumers need, so migration loses
  no capability.
- **Relevant requirements**: FR-002; C-002.
- **Affected surfaces**: `vikunja_client.py` — inventory the HTTP ops across the 6 raw modules
  (comments CRUD, completion/done toggles, label attach/detach, bulk/filtered reads, partial-update
  POST); add missing methods on the existing contract + error model; unit-test each.
- **Sequencing/depends-on**: none (foundation).
- **Risks**: preserve Vikunja quirks the raw code handled — pagination, and the known
  POST-partial-replace read-modify-write semantics; the client method must reproduce the exact effect.

### IC-02 — Migrate consumers onto the client (FR-001, FR-003, NFR-001)

- **Purpose**: replace hand-loaded-token + raw HTTP with `VikunjaClient` in every runtime consumer,
  behavior-preserving.
- **Relevant requirements**: FR-001, FR-003; NFR-001.
- **Affected surfaces**: sync/cycle (highest stakes — bidirectional), escalation ×2, enrichment ×2,
  habits ×7, credential-health writer. Each migration ships with a parity test (the requests issued
  before == after).
- **Sequencing/depends-on**: IC-01. Likely decomposed into several WPs by domain (sync; escalation+
  enrichment; habits; credential-health) to keep WPs reviewable.
- **Risks**: this is the bulk; keep each consumer's effects identical; `sync/cycle.py` gets the most
  test care.

### IC-03 — Verification + behavior-preserving deploy (FR-003, SC-002/003/004)

- **Purpose**: prove no behavior changed and land the refactor.
- **Relevant requirements**: FR-003; SC-002, SC-003, SC-004; NFR-002.
- **Affected surfaces**: the grep gate (SC-001), the full test surface, and a post-deploy spot-check
  that each migrated consumer runs correctly on office2 **still on the felix-bot token** (SC-004
  confirms the default is unchanged).
- **Sequencing/depends-on**: IC-01, IC-02.
- **Risks**: none live — no auth/credential change; deploy is self-pull. The value is a clean,
  green foundation for the Phase-2 flip.

## Two-phase note

Phase 2 (follow-on, kitty-light under #860) — NOT in this mission: flip `DEFAULT_TOKEN_PATH` → kent;
remove `route_someday` 403 fail-soft; validator convergence; inverse probe + felix-bot data
migration; ADR-0004 + identity-model/credentials-and-secrets; SKILL/TOOLS/unit token refs;
credential-manifest retire; attended Tier-2 cutover + projects-16–20 verification; resolve #831/#750.
