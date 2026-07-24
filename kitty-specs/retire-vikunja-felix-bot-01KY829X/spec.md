# Consolidate Felix→Vikunja onto the shared client (phase 1 of #860)

**Mission**: retire-vikunja-felix-bot-01KY829X *(legacy slug; this is the **Phase 1 consolidation** mission)*
**Source issue**: kentonium3/kg-automation#860 (Epic #531 — Shared Vikunja Client and Configuration Boundary)
**Mission type**: software-dev

## Purpose

**TL;DR** — Route **all** Felix→Vikunja runtime access through the shared `VikunjaClient`,
**behavior-preserving** (no identity change — still the felix-bot token). This establishes the
Epic #531 boundary / EA-architecture §11 task seam and is the foundation that makes the identity
flip (Phase 2) a safe one-liner.

Today ~6 runtime domains (sync, escalation, enrichment, habits, credential-health) bypass the
shared `VikunjaClient` and talk to Vikunja with hand-loaded tokens + **raw HTTP** — a design
inconsistency and a second, un-consolidated access path. This mission migrates every one of them
onto `VikunjaClient` (extending the client where it lacks an operation), with **no change to
identity, token, or observable Vikunja effects**. It is a pure, incrementally-mergeable refactor
that touches no live auth.

**Two-phase execution (why this is Phase 1):** flipping the token before every consumer is on the
client would leave a **split-brain** (some kent, some felix-bot) — worse than today. So Phase 1
consolidates everyone onto the client *consistently on felix-bot*; Phase 2 (a follow-on mission,
`#860`) then does the atomic single-line flip to the kent token + felix-bot Vikunja retirement +
the attended Tier-2 cutover.

**Architecture boundary (§11 discipline):** `VikunjaClient` *is* the seam. This mission establishes
it by consolidation; it explicitly does **not** build an abstract `TaskService` port / adapter
layer — that formal port is deferred until a second task backend (Todoist/Asana) justifies it.

## User Scenarios & Testing

**Primary actor**: the Felix runtime (every Vikunja consumer on office2).
**Secondary actors**: the operator (Kent).

### Primary scenario

1. Every runtime Vikunja operation flows through `VikunjaClient`; no runtime path hand-loads a
   token or issues raw HTTP to Vikunja.
2. Each migrated consumer produces the **same** Vikunja effects as before (same felix-bot token,
   same reads/writes) — verified per consumer.

### Exception / edge scenarios

- **Client gap**: a consumer needs an operation `VikunjaClient` lacks → add it to the client
  (following its contract + error model), never keep a raw path.
- **Behavior drift**: a migration subtly changes an effect (pagination, partial-update POST
  semantics) → caught by the per-consumer parity test.

## Requirements

### Functional Requirements

| ID | Requirement | Status |
|----|-------------|--------|
| FR-001 | **All Felix→Vikunja runtime access MUST go through the shared `VikunjaClient`.** Migrate the raw-HTTP / direct-token consumers onto it: **sync = `scripts/sync/{cycle,fetch,http}.py`** (sync's raw urllib is factored through `http.py` + `fetch.py`, driven by `cycle.py` — all three migrate), `scripts/escalation/{record_completion,reconcile_completions}.py`, `scripts/enrichment/{record_completion,reconcile_completions}.py`, `scripts/habits/{sweeper,set_due_dates,record_completion,exclude_completed,identify_workout_task,migrate_schedule,backfill_jsonl_from_comments}.py`, `scripts/security/credential_health_check/vikunja_writer.py`. No runtime path may hand-load the token or issue raw HTTP to Vikunja. Re-confirm the full set by grep at implementation. (`scripts/habits/reconcile_completions.py` reads via the sync **cache**, not raw HTTP → not migrated; but its dead `_read_token()` helper must be removed/classified — see SC-001.) | Required |
| FR-002 | `VikunjaClient` MUST be extended to cover every operation the migrated consumers require, following the existing client contract + error model, with unit tests per new method. This MUST include: (a) a `patch()` method + PATCH content-type handling in `_request` (escalation issues `PATCH /tasks/{id}` for done/reschedule — the client currently has only get/post/put/delete); (b) **separate** update methods for **raw POST-replace** vs **safe read-modify-write** (habits `record_completion` GET-before-POSTs to preserve `repeat_after`/`repeat_mode`, while `migrate_schedule` intentionally POSTs narrow bodies — a single generic "partial update" helper would reintroduce the v0.24.6 field-zeroing bug or alter existing effects); (c) an explicit decision per consumer on whether the migrated call preserves the raw `None`-on-empty / error-body-in-message semantics or adopts the client's `{}`-on-empty / redacted-exception model (adapter-translate where behavior must be preserved). | Required |
| FR-003 | The consolidation MUST be **behavior-preserving**: identity, token, base URL, and each consumer's observable Vikunja effects are unchanged. The `VikunjaClient` default token remains the felix-bot `vikunja-api` in this mission (the flip is Phase 2). Where the client's default enumeration differs from a raw consumer's (e.g. `list_all_tasks()` pages `GET /projects?page=…&per_page=50` whereas sync's `fetch.py` does one unpaged `GET /projects`), either preserve the raw algorithm behind a sync-specific client path or consciously accept + test the changed request profile. | Required |
| FR-004 | No abstract `TaskService` port / adapter layer is introduced (§11 — seam via `VikunjaClient`; formal port deferred). | Required |

### Non-Functional Requirements

| ID | Requirement | Threshold | Status |
|----|-------------|-----------|--------|
| NFR-001 | Behavior parity per consumer. | Each migrated consumer has a test proving its Vikunja effects are unchanged vs. the raw-HTTP path. Request-recording (method/path/body) is necessary but **not sufficient** — parity MUST also cover the domain/CLI boundary: exit codes, emitted records (JSONL/state), logs/error strings, cache writes, request **ordering**, idempotency short-circuits, and sync **failure-token classification** (`cycle_error` and the `/info` / cache-nonempty-abort guards). Highest care on `sync` (bidirectional). | Required |
| NFR-002 | Incremental mergeability / low risk. | The mission touches no live auth and no credential/service state; it deploys via checkout self-pull with no cutover. | Required |

### Constraints

| ID | Constraint | Status |
|----|-----------|--------|
| C-001 | **No identity or token change** in this mission — still felix-bot. The kent flip, felix-bot Vikunja retirement, inverse probe, ADR/doc reconciliation, and credential-manifest change are **Phase 2** (follow-on mission). | Required |
| C-002 | Single boundary: exactly one client (`VikunjaClient`) mediates Vikunja; no per-site token or raw HTTP remains in the runtime path. | Required |
| C-003 | No abstract task-service port/adapter layer (C-004 of the umbrella; §11 discipline). | Required |

## Success Criteria

| ID | Criterion |
|----|-----------|
| SC-001 | `grep -rnE "secrets/vikunja-api([^-]|$)" scripts/` and a grep for raw `urllib`/`requests` calls to Vikunja show **no runtime** consumer hand-loading a token or issuing raw HTTP; every runtime Vikunja op goes through `VikunjaClient` (only admin/one-shot + docs may remain). The sync helper modules `sync/http.py` + `sync/fetch.py` are included; the dead `_read_token()` in `habits/reconcile_completions.py` (which reads via cache, not HTTP) is removed or explicitly classified so the gate is clean. |
| SC-002 | Every migrated consumer has a green parity test; the full Vikunja/inbox/habits/escalation/enrichment/trust test surface passes. |
| SC-003 | Post-deploy, each migrated consumer runs correctly on office2 (still felix-bot) — spot-verified, no regression. |
| SC-004 | The `VikunjaClient` default token is unchanged (felix-bot) — confirming zero identity change this phase. |

## Key Entities

- **`VikunjaClient`** (`scripts/common/vikunja_client.py`) — the single Vikunja access boundary
  (#531 boundary / §11 task seam), extended here to cover all consumer operations.
- **Raw-HTTP consumers** — sync / escalation / enrichment / habits / credential-health modules
  migrated onto the client.
- **felix-bot token** (`vikunja-api`) — remains the client default this phase (untouched).

## Assumptions

- `VikunjaClient` is a sufficient/extensible boundary; where it lacks a method, this mission adds it.
- `intake/apply_reply.py` already uses `VikunjaClient` (verified) — no migration needed there.
- `scripts/habits/reconcile_completions.py` reads Vikunja state via the sync **cache**
  (`scripts/common/sync_cache.py`), not raw HTTP — it is **not** a migration target; only its
  dead `_read_token()` helper is cleaned up so SC-001's grep is unambiguous.
- Admin/one-shot scripts that deliberately target a specific token
  (`provision_felix_bot`, `validate_felix_bot`, `swap_vikunja_secrets`, `reconcile_projects`,
  `create_saved_filters`, `migrate_tasks`) are not runtime consumers and are out of scope here.

## Out of Scope (→ Phase 2, follow-on mission under #860)

- The identity flip to the kent token (`DEFAULT_TOKEN_PATH` change).
- Eliminating felix-bot's Vikunja view; the inverse probe + felix-bot data migration.
- Removing the felix-bot fail-soft branches (`route_someday` 403); #750 / #831 resolution.
- ADR-0004 + `identity-model.md` / `credentials-and-secrets.md` reconciliation; SKILL/TOOLS/unit
  token references; the credential-manifest retire.
- The attended Tier-2 credential cutover + projects-16–20 verification.
- Any abstract task-service port/adapter interface.
