# Data Model: Consolidate Felix→Vikunja onto the shared client (phase 1 of #860)

No application data model changes and **no credential/identity change** this phase. The Phase-1
"model" is the **consumer → access-path** topology: who talks to Vikunja, and through what.

## Entities

### `VikunjaClient` (the single access boundary)

- `scripts/common/vikunja_client.py` — the #531 boundary / §11 seam.
- Current surface: `get/post/put/delete`, `list_all_tasks`, `_request` (arbitrary method string,
  JSON content-type for POST/PUT only). `DEFAULT_TOKEN_PATH` = felix-bot `…/vikunja-api`
  (**unchanged** this phase). Token loaded at **construction**.
- Extended here (FR-002): `patch()` + PATCH content-type; two update shapes (raw POST-replace vs
  safe read-modify-write); any consumer-specific read/label/comment/completion ops.

### Runtime consumers → access path

| Consumer | Before (Phase 0) | After (Phase 1) |
|----------|------------------|-----------------|
| `intake/apply_reply.py` | `VikunjaClient` | `VikunjaClient` (unchanged) |
| `sync/{cycle,fetch,http}.py` | raw urllib + hand-loaded token | `VikunjaClient` |
| `escalation/{record_completion,reconcile_completions}.py` | raw urllib (incl. `PATCH`) | `VikunjaClient` |
| `enrichment/{record_completion,reconcile_completions}.py` | raw urllib | `VikunjaClient` |
| `habits/{sweeper,set_due_dates,record_completion,exclude_completed,identify_workout_task,migrate_schedule,backfill_jsonl_from_comments}.py` | raw urllib | `VikunjaClient` |
| `security/credential_health_check/vikunja_writer.py` | raw urllib | `VikunjaClient` |
| `habits/reconcile_completions.py` | reads via sync **cache** (not HTTP) | unchanged (dead `_read_token()` removed) |

**Identity/token**: every consumer stays on the **felix-bot** token — same reads/writes, same
observable Vikunja effects. This phase changes only *how* the request is issued, never *who* or
*what*.

## Invariants (Phase 1)

- **INV-1** (single boundary): after this phase exactly one type mediates runtime Vikunja access
  (`VikunjaClient`); no runtime path hand-loads a token or issues raw HTTP (C-002, SC-001).
- **INV-2** (behavior parity): each migrated consumer's requests **and** domain effects (exit codes,
  emitted records, logs, cache writes, ordering, sync error-token classification) are unchanged
  vs. the raw path (NFR-001, FR-003).
- **INV-3** (zero identity change): `VikunjaClient.DEFAULT_TOKEN_PATH` still resolves to the
  felix-bot `vikunja-api` file; no credential/service/manifest state changes (SC-004, C-001).
- **INV-4** (no premature abstraction): no `TaskService` port/adapter layer is introduced (C-003).

---

## Phase-2 target state (DEFERRED — follow-on mission under #860; NOT in scope here)

Retained for the follow-on kitty-light mission; **no** Phase-1 task touches these.

| Surface | Phase-1 end state | Phase-2 target |
|---------|-------------------|----------------|
| `VikunjaClient.DEFAULT_TOKEN_PATH` | `…/vikunja-api` (felix-bot) | `…/vikunja-api-kent` |
| no-token consumers | felix-bot view (partial) | kent view (full: projects 16–20 visible) |
| `route_someday` label-attach | fail-soft (felix-bot 403) | unconditional attach (kent can attach) |
| #748 validator token source | parallel kent constant | shared runtime default (R3) |
| felix-bot `vikunja-api` credential | in manifest, runtime default | retired from manifest; token valid, user dormant (R2) |
| ADR of record | ADR-0002 (attribution) | ADR-0004 (dropped attribution); 0002 superseded (R4) |
