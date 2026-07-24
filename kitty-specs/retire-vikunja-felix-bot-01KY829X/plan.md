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
**Scale/Scope**: extend `VikunjaClient` + migrate ~15 runtime files (sync = `cycle`+`fetch`+`http`;
escalation ×2; enrichment ×2; habits = 7 scripts; credential-health writer). **Large refactor —
the bulk of #860's engineering.**

### Environment probe results (DIR-015 — verified live on office2, 2026-07-23; inventory re-confirmed post-Codex 2026-07-23)

- Consumer inventory (grep-confirmed): raw-HTTP direct-token consumers =
  **`sync/{cycle,fetch,http}.py`** (raw urllib is factored through `http.py` + `fetch.py`, driven
  by `cycle.py` — the earlier "cycle.py only" scoping was incomplete),
  `escalation/{record_completion,reconcile_completions}.py`, `enrichment/{record_completion,
  reconcile_completions}.py`, `habits/{sweeper,set_due_dates,record_completion,exclude_completed,
  identify_workout_task,migrate_schedule,backfill_jsonl_from_comments}.py`,
  `security/credential_health_check/vikunja_writer.py`. `intake/apply_reply.py` **already** uses
  `VikunjaClient`. `habits/reconcile_completions.py` reads via the sync **cache** (not raw HTTP) →
  not a migration target; its dead `_read_token()` is removed so the SC-001 grep is clean.
  Admin/one-shot scripts are not runtime consumers.
- HTTP profile: escalation/enrichment/habits/credential-health modules each issue ~7–10 raw
  urllib calls → each needs its ops mapped onto `VikunjaClient` methods. Escalation uses
  **`PATCH /tasks/{id}`** (client lacks `patch()` today). Sync's `fetch.py` does one unpaged
  `GET /projects` + paged `GET /projects/{id}/tasks` + best-effort `GET /info` with empty-response
  cache guards, dedup, and structured `cycle_error` tokens — all of which are parity surface.
- The felix-bot secret file is present + non-empty (unchanged this phase).

### Deploy & rebaseline

- Deploy = checkout self-pull; no restart (each new `VikunjaClient` instance loads the **unchanged**
  felix-bot default token at construction — no token changes this phase). No credential/service
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
scripts/common/vikunja_client.py     # MODIFIED — add patch() + PATCH content-type; raw-replace vs read-modify-write update methods; cover consumer ops (FR-002). NO default change.
scripts/sync/{cycle,fetch,http}.py   # MIGRATE — raw urllib (http.py/fetch.py) → VikunjaClient (bidirectional sync — highest stakes)
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
- **Affected surfaces**: `vikunja_client.py` — inventory the HTTP ops across the raw modules
  (comments CRUD, completion/done toggles, label attach/detach, bulk/filtered reads, partial-update
  POST); add missing methods on the existing contract + error model; unit-test each. Known gaps:
  (a) **`patch()` + PATCH content-type** in `_request` (escalation `PATCH /tasks/{id}`);
  (b) **two distinct update methods** — a raw POST-replace and a safe read-modify-write — never one
  generic "partial update" (habits `record_completion` GET-before-POSTs to keep `repeat_after`/
  `repeat_mode`; `migrate_schedule` deliberately POSTs narrow bodies);
  (c) preserve, or adapter-translate, the raw **`None`-on-empty / error-body-in-message** return
  semantics vs the client's `{}`-on-empty / redacted-exception model, decided per consumer.
- **Sequencing/depends-on**: only the truly shared primitives are foundational; consumer-specific
  methods are validated against their consumer's quirks, so add them **with** the domain WP (see
  IC-02 vertical decomposition) rather than all up front.
- **Risks**: preserve Vikunja quirks the raw code handled — pagination, the POST-partial-replace
  read-modify-write zeroing (v0.24.6), id-vs-identifier, server-side filter rejection; the client
  method must reproduce the exact effect.

### IC-02 — Migrate consumers onto the client (FR-001, FR-003, NFR-001)

- **Purpose**: replace hand-loaded-token + raw HTTP with `VikunjaClient` in every runtime consumer,
  behavior-preserving.
- **Relevant requirements**: FR-001, FR-003; NFR-001.
- **Affected surfaces**: sync = `cycle`+`fetch`+`http` (highest stakes — bidirectional; parity must
  cover call order, `/info` best-effort suppression, empty-response cache-abort guards, dedup, and
  emitted `cycle_error` classification), escalation ×2, enrichment ×2, habits ×7, credential-health
  writer. Each migration ships with a parity test (see IC-03 — request-level **plus** domain/CLI
  boundary).
- **Sequencing/depends-on**: **vertical decomposition** (Codex MED — avoid a big IC-01 foundation
  bottleneck that bakes in wrong abstractions). WP-A adds only the minimum *shared* client surface
  (`patch()`, the two update-method shapes, shared read helpers) + their unit tests; then one WP per
  domain — **sync** (cycle+fetch+http, most test care), **escalation+enrichment**, **habits**,
  **credential-health** — each adds any consumer-specific client method **with** its migration and
  parity test, so every added method is validated against a real consumer.
- **Risks**: this is the bulk; keep each consumer's effects identical; sync gets the most test care.

### IC-03 — Verification + behavior-preserving deploy (FR-003, SC-002/003/004)

- **Purpose**: prove no behavior changed and land the refactor.
- **Relevant requirements**: FR-003; SC-002, SC-003, SC-004; NFR-002.
- **Affected surfaces**: the grep gate (SC-001 — includes `sync/http.py`+`fetch.py` and the removed
  dead `_read_token()`), the full test surface (request-level parity **plus** golden domain/CLI-boundary
  tests: exit codes, emitted JSONL/state records, logs/error strings, cache writes, request ordering,
  sync failure-token classification — NFR-001), and a post-deploy spot-check that each migrated
  consumer runs correctly on office2 **still on the felix-bot token** (SC-004 confirms the default is
  unchanged).
- **Sequencing/depends-on**: IC-01, IC-02.
- **Risks**: none live — no auth/credential change; deploy is self-pull. The value is a clean,
  green foundation for the Phase-2 flip.

## Two-phase note

Phase 2 (follow-on, kitty-light under #860) — NOT in this mission: flip `DEFAULT_TOKEN_PATH` → kent;
remove `route_someday` 403 fail-soft; validator convergence; inverse probe + felix-bot data
migration; ADR-0004 + identity-model/credentials-and-secrets; SKILL/TOOLS/unit token refs;
credential-manifest retire; attended Tier-2 cutover + projects-16–20 verification; resolve #831/#750.
