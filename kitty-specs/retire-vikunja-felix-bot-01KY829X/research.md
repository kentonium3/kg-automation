# Research: Consolidate Felix→Vikunja onto the shared client (phase 1 of #860)

Phase 0 decisions. Decision → Rationale → Alternatives.
**Scope note:** this mission is **Phase 1** — the behavior-preserving consolidation. R1/R1b and
the Phase-1 decisions below govern it. The Phase-2 decisions (token flip, ADR, credential retire,
attended cutover) are retained at the bottom **for the follow-on mission only** — they are NOT in
scope here and must not drive Phase-1 task decomposition.

## R1 — Consolidate onto the client first, THEN a one-line identity flip (revised, Codex HIGH)

- **Decision**: the mission is a **consolidation**, not a one-line pivot. ~6 runtime domains
  (sync, escalation, enrichment, habits, credential-health) talk to Vikunja with raw HTTP +
  hand-loaded tokens; Phase 1 migrates them all onto the shared `VikunjaClient` (extending it where
  it lacks an op). Phase 2 then flips the single `DEFAULT_TOKEN_PATH` to the kent token.
- **Rationale**: repointing the client default alone would leave the raw-HTTP consumers on
  felix-bot → a **split-brain** (some kent, some felix-bot) worse than today's consistent-but-partial
  view. Consolidation is also the Epic #531 boundary / EA-§11 task seam and fixes the design
  inconsistency directly.
- **Alternatives**: flip only the `VikunjaClient` consumers now, migrate the rest later — rejected
  (split-brain, prohibited by NFR-001). A one-line pivot — rejected (undercounts the real surface).

## R1b — Establish the seam, not a formal port (EA-§11 discipline)

- **Decision**: `VikunjaClient` is the seam; do **not** build an abstract `TaskService` port /
  adapter registry now.
- **Rationale**: §11 — "seam now, formal port when a second implementation justifies it." No second
  task backend exists; Todoist/Asana is explicitly deferred.
- **Alternatives**: introduce a `TaskService` interface + Vikunja adapter now — rejected as
  premature generalization (C-004).

## R1c — Sync's raw HTTP is in `http.py`+`fetch.py`, not just `cycle.py` (Codex HIGH)

- **Decision**: scope the sync migration as **`sync/{cycle,fetch,http}.py`**. `http.py` is the
  urllib wrapper; `fetch.py` is the read algorithm (one unpaged `GET /projects`, paged
  `GET /projects/{id}/tasks`, best-effort `GET /info`, empty-response cache-abort guards, dedup,
  `cycle_error` tokens); `cycle.py` is the driver.
- **Rationale**: an inventory that names only `cycle.py` would leave `http.py`/`fetch.py` raw and
  fail the consolidation (SC-001) in practice.
- **Alternatives**: migrate `cycle.py` only — rejected (leaves the real raw path in place).

## R1d — Client method gaps: PATCH + two update shapes (Codex HIGH)

- **Decision**: extend `VikunjaClient` with (a) `patch()` + PATCH content-type handling in
  `_request` (escalation issues `PATCH /tasks/{id}`; the client today has only get/post/put/delete);
  (b) **two separate** update methods — a raw POST-replace and a safe read-modify-write — never one
  generic "partial update"; (c) a per-consumer decision on preserving the raw `None`-on-empty /
  error-body-in-message semantics vs the client's `{}`-on-empty / redacted-exception model.
- **Rationale**: habits `record_completion` GET-before-POSTs to preserve `repeat_after`/`repeat_mode`
  (v0.24.6 POST-zeroing), while `migrate_schedule` intentionally POSTs narrow bodies — a single
  helper would either reintroduce the zeroing bug or change existing effects. Escalation's PATCH and
  the raw return/error semantics are behavior that parity must preserve.
- **Alternatives**: one generic partial-update helper — rejected (Codex HIGH: unsafe).

## R1e — Parity = request-recording PLUS domain/CLI boundary (Codex MED)

- **Decision**: per-consumer parity proves method/path/body **and** exit codes, emitted JSONL/state
  records, logs/error strings, cache writes, request **ordering**, idempotency short-circuits, and
  sync **failure-token classification** (`cycle_error`, `/info` best-effort suppression,
  empty-response cache-abort). Golden tests at the CLI/domain boundary, not only HTTP mocks.
- **Rationale**: a request-level mock alone misses ordering-sensitive and side-effect behavior —
  highest risk in bidirectional sync.
- **Alternatives**: request-recording only — rejected (insufficient for behavior preservation).

## R1f — Vertical WP decomposition (Codex MED)

- **Decision**: WP-A adds only the minimum *shared* client surface + unit tests; then one WP per
  domain (sync; escalation+enrichment; habits; credential-health), each adding any consumer-specific
  client method **with** its migration + parity test.
- **Rationale**: a large "add all client methods first" WP is hard to review and risks baking in
  wrong abstractions; consumer-specific methods are best validated against their consumer's quirks.
- **Alternatives**: one big foundation WP then migrations — rejected (bottleneck + abstraction risk).

## R5 — Deploy mechanism (Phase 1)

- **Decision**: the refactor lands by **felix-deployer self-pull** (runtime scripts are
  checkout-resident). No manifest, no restart: each new `VikunjaClient` instance loads the
  **unchanged** felix-bot default token at construction. Behavior-preserving → no cutover, no Tier-2
  hold this phase.
- **Rationale**: no token/credential/service change; `scripts/**` matches no audited surface →
  **Rebaseline: not required**.
- **Alternatives**: add a deploy manifest — rejected (nothing imperative to do; pulls in a
  deploy-pipeline rebaseline for no gain).

---

## Phase-2 decisions (DEFERRED — follow-on mission under #860; NOT in scope here)

Retained for the follow-on kitty-light mission; do not act on these in Phase 1.

- **R2 — Rollback-safe token retirement**: retire the felix-bot `vikunja-api` credential from the
  manifest + runtime, but leave the token **valid** and the felix-bot **user** dormant (reverting
  the runtime commit restores prior behavior; attribution history preserved).
- **R3 — Validator draws its token from the runtime default**: `validate_refs.py` / `vikunja_refs.py`
  obtain their token from the shared `VikunjaClient` default rather than a parallel
  `DEFAULT_KENT_TOKEN_FILE` constant, so validator ≠ runtime divergence becomes structurally
  impossible.
- **R4 — New record is ADR-0004, not ADR-0003**: `adr/0003-felix-vikunja-sync-architecture.md`
  already exists; the issue body's "ADR-0003" is stale. Write **ADR-0004** (dropped-attribution /
  single-token), superseding ADR-0002.
- **R7 — Attended Tier-2 boundary**: HOLD for the operator before any live change — confirm a Restic
  snapshot within 24h, capture the *before* connectivity baseline of all consumers, operator present
  for the cutover, verify projects 16–20 + all consumers post-cutover.
