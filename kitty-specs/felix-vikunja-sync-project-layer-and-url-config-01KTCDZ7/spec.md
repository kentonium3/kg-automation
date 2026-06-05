# Felix-Vikunja Sync — Project Layer and URL Config

**Status**: Specification (post-discovery, ready for `/spec-kitty.plan`)
**Mission ID**: `01KTCDZ78163ZG65BGKF7F7HMD`
**Mission slug**: `felix-vikunja-sync-project-layer-and-url-config-01KTCDZ7`
**Mission type**: software-dev
**Target branch**: main
**Source**: [#520](https://github.com/kentonium3/kg-automation/issues/520) — sub-issue of Epic [#507](https://github.com/kentonium3/kg-automation/issues/507)
**Predecessors**: [#518](https://github.com/kentonium3/kg-automation/issues/518) (sync driver foundation), [#519](https://github.com/kentonium3/kg-automation/issues/519) (touchpoint migration)
**Source research**: [#508](https://github.com/kentonium3/kg-automation/issues/508), in particular `docs/research/felix-vikunja-sync-architecture/findings/rq-4-use-case-mapping.md`

---

## Story / Context

Epic #507 set out to deliver a complete Felix↔Vikunja sync architecture. Missions #518 (driver foundation, status + task layers) and #519 (touchpoint migration to sync cache) shipped the first two layers and the cache-read path. This mission delivers the remaining three structural pieces:

1. **Project-layer reconciliation** — Vikunja's `updated_since` is task-scoped; project changes (rename, archive, new project add) are not detected by the existing driver. Add a project layer to the driver cycle.
2. **Task-deletion convergence** — research mission RQ-4 § 4 documented a 15-minute worst-case latency gap for task deletion under the original incremental-polling design (the only NFR-002 miss across all 7 RQ-4 use cases).
3. **URL base normalization** — two Vikunja URL bases (`https://office2.tail0f5f56.ts.net/api/v1` and `http://100.92.197.90:3456/api/v1`) are in concurrent use across scripts, creating silent inconsistency risk and a recurring "which is canonical?" tax on every new touchpoint.

**Architectural shift adopted during this mission's discovery**: at the operating scale (~50 tasks, ≤100 worst case), the `updated_since` incremental-polling optimization that #518 built is paying for itself with complexity that exceeds the few-KB-per-cycle of HTTP saved. This mission **replaces** #518's incremental polling with full-poll + 3-way set diff for both the task and project layers. Per RQ-4 § 4, full polling was explicitly considered during research and described as "acceptable at Felix's scale." The simpler model:

- Eliminates the 15-min deletion gap entirely (deletion converges in N=1 cycle = 5 min)
- Removes the documented incremental-polling edge cases (RQ-4 § 7 Deferred items 1 + 2 become moot)
- Unifies task-layer and project-layer detection under a single set-diff mechanism
- Removes the need for an N-cycle confirmation algorithm

The rework is contained within the driver (`scripts/sync/`); the cache-read contract from #519 (`scripts/common/sync_cache.py`) is unchanged. Touchpoints continue to read TaskCacheView objects exactly as they do today.

---

## User Scenarios & Testing

**Primary persona**: Kent (operator) — modifies Vikunja state through the web UI and expects Felix's view to converge to the same state within one driver cycle (5 min).

**Secondary persona**: future Felix agents and engineers reading the URL config — expect a single canonical source for the Vikunja base URL.

The 7 use cases from RQ-4 (a–g) are the test contract for this mission. Each must hit ≤ 5 min worst-case latency.

### Acceptance Scenarios

- **AS-001 (use case a, status change)**: Operator marks task #N done in Vikunja UI. Within 5 min, sync cache shows `done: true` for task #N; next Felix touchpoint reads the updated state.
- **AS-002 (use case b, deletion)**: Operator deletes task #N (a habit) in Vikunja UI. Within 5 min: task absent from sync cache; entry pruned from `scripts/habits/migrations/phase3-schedule.yaml`; `task_deleted` event appended to `scripts/habits/state/habits-history.jsonl`; next morning check-in does not include the deleted task.
- **AS-003 (use case c, task moved)**: Operator moves task #N from project A to project B. Within 5 min, sync cache shows `project_id: B` for task #N.
- **AS-004 (use case d, new project)**: Operator creates project Z in Vikunja UI. Within 5 min: project Z appears in `project-cache.json`; driver tick log records a `project_added` event.
- **AS-005 (use case e, bulk move)**: Operator moves 5 tasks from project A to project B. Within 5 min, all 5 tasks show `project_id: B` in cache.
- **AS-006 (use case f, rename)**: Operator renames project A to "Project A (Renamed)". Within 5 min, `project-cache.json` reflects the new title; driver tick log records a `project_renamed` event.
- **AS-007 (use case g, due date set)**: Operator sets a new `due_date` on task #N. Within 5 min, sync cache shows the new `due_date` for task #N.
- **AS-008 (URL config change)**: Operator edits `/data/services/openclaw/config/vikunja-base-url.txt` to a different valid base URL. On the next script invocation, every consumer reads the new URL with no code changes.
- **AS-009 (Vikunja transient failure)**: Vikunja returns HTTP 5xx on a cycle's full-poll. Cycle aborts cleanly: no cache mutation, no spurious deletions, error logged. Next cycle (5 min later) succeeds and converges normally.

### Edge Cases

- **EC-001**: Task moved to a project felix-bot can't see (no share grant). The task is absent from `GET /tasks/all` because of API filtering, not because the task was deleted. With full-poll + N=1 deletion, this would erroneously classify the task as deleted. **Mitigation**: this is a known operational pattern only triggered by deliberate operator action; if the operator removes a task from felix-bot's visible projects, treating it as deleted is the desired behavior (Felix correctly stops tracking it). If the task is moved back to a visible project later, it will reappear in the next full poll and be re-added to the cache.
- **EC-002**: Vikunja API returns an empty `[]` for `GET /tasks/all` when the cache has non-zero tasks. Most likely cause: auth failure (401/403). Cycle aborts cleanly per FR-012 (no spurious deletions).
- **EC-003**: Project layer's full poll succeeds but the task layer's full poll fails mid-cycle. The cycle's atomic-update guarantee (per `last-tick.json`) means the partial poll is discarded — both layers must succeed for the cycle to commit a cache update.
- **EC-004**: Two operators (Kent + a Felix agent) simultaneously modify the same task within one 5-min window. C-002 (Vikunja wins) from #518 still holds; the full-poll observes whichever write landed last.

---

## Functional Requirements

### FR-001: Full-poll replaces incremental polling for task layer

**Status**: Approved

The reconciliation driver replaces `GET /tasks/all?updated_since=<ts>` with `GET /tasks/all` (no `updated_since` query parameter) at the task layer. Cache update logic switches from delta-apply to set diff against the prior cache snapshot.

**Rationale**: at ≤100 tasks, the incremental optimization saves ~50KB of HTTP per cycle while introducing significant complexity (the `updated_since` anchor pointer, the deletion-detection N-cycle algorithm, the documented edge cases). Removing it simplifies the driver substantially.

### FR-002: 3-way set diff is the single change-detection mechanism

**Status**: Approved

Each cycle, the driver computes three disjoint sets from the full-poll response and the prior cache:
- `in_vikunja_only` → new tasks to add to cache
- `in_cache_only` → tasks deleted in Vikunja, to remove from cache (per FR-003 cleanup)
- `in_both` → tasks where each tracked field is compared; differences become content-change events

No other change-detection path (no `updated_since` hybrid, no per-task GET probe, no transient counters).

### FR-003: N=1 deletion detection with three-action cleanup

**Status**: Approved

A task in `in_cache_only` on a successful cycle is classified as deleted. The driver performs exactly three actions per confirmed deletion:

1. Prune the entry for that `task_id` from `scripts/habits/migrations/phase3-schedule.yaml` (if present)
2. Append a `task_deleted` event to `scripts/habits/state/habits-history.jsonl` with the task_id, title, and the timestamp of detection
3. Remove the task record from the sync cache (`task-cache.json`)

No other downstream orchestration. Consumers of the cache that encounter a missing task_id rely on the existing "task not in cache" branch in `read_cached_task_by_id` (raises `MissingTaskError`).

### FR-004: Project layer added to driver cycle

**Status**: Approved

The reconciliation driver adds a `project` layer that performs `GET /projects` per cycle, diffs against `project-cache.json` using the same 3-way set diff mechanism as FR-002, and updates the cache. Project diff events recorded:

- `project_added` (new project_id appears in poll, not in cache)
- `project_removed` (project_id in cache, absent from poll)
- `project_renamed` (title differs between poll and cache for same project_id)
- `project_archived` (`is_archived` field changes from `false` to `true`)
- `project_unarchived` (`is_archived` field changes from `true` to `false`)

### FR-005: Project layer is audit/discovery only — no downstream consumer changes

**Status**: Approved

No touchpoint reads `project-cache.json` for business logic in this mission. The layer exists to keep the cache fresh and emit log events for audit/discovery. Future missions that need project state in consumers can build on top of the cache; this mission does not create such consumers.

### FR-006: URL config — canonical file at fixed path

**Status**: Approved

A canonical Vikunja base URL is stored at `/data/services/openclaw/config/vikunja-base-url.txt`. The file contains exactly one line: the base URL (e.g., `https://office2.tail0f5f56.ts.net/api/v1`). File mode `0644`, owner `claude:claude`. The file is the single source of truth.

### FR-007: URL config — env var wrapper for interactive sessions and systemd

**Status**: Approved

A `VIKUNJA_BASE_URL` environment variable is exported in:
- `~/.bashrc` for the `claude` user (interactive shell sessions)
- `/data/services/openclaw/secrets/openclaw-gateway.env` (systemd `EnvironmentFile=` for `openclaw-gateway.service` and its child agent sessions)

Both exports read the value from the canonical file. The env var is a convenience wrapper; the file is authoritative.

### FR-008: 6 migrated touchpoints + #518 driver + 2 write touchpoints read URL from config

**Status**: Approved

The following scripts read the Vikunja base URL from a shared helper that reads `/data/services/openclaw/config/vikunja-base-url.txt` (or `$VIKUNJA_BASE_URL` if set):

- The 6 touchpoints migrated by #519 (TP-02, TP-03, TP-04, TP-07, TP-10, TP-12)
- The #518 reconciliation driver (`scripts/sync/*`)
- The 2 retained write paths: `set_due_dates.py`'s `_http_put` (TP-04 PUT phase) and `enrichment/reconcile_completions.py`'s `_http_get` + `_fetch_comments` (TP-12)

No hardcoded URL strings remain in any of these files.

### FR-009: Driver tick log includes both layers' phases

**Status**: Approved

Each cycle's `last-tick.json` includes per-layer status under a new `layer_summary` field:

```json
{
  "task_layer": {"polled_at_utc": "...", "added": 0, "removed": 0, "updated": 0, "errors": []},
  "project_layer": {"polled_at_utc": "...", "added": 0, "removed": 0, "renamed": 0, "errors": []}
}
```

A partial-failure cycle (one layer succeeded, the other failed) records both per-layer entries and aborts the cache commit (no half-applied state).

### FR-010: One-off setup/utility scripts excluded from FR-008 scope

**Status**: Approved

The following scripts continue to use their existing URL handling and are NOT migrated in this mission:

- `scripts/vikunja/provision_felix_bot.py`, `validate_felix_bot.py`, `swap_vikunja_secrets.py`, `revoke_kent_tokens.py` (one-shot felix-bot provisioning helpers from #304)
- `scripts/vikunja/setup_goals.py` (one-shot goals project setup)
- `scripts/habits/migrate_schedule.py` (one-shot habit migration from #408)
- `scripts/habits/query_active_habits.py` (legacy v1, superseded by v2)
- `scripts/security/credential_health_check/vikunja_writer.py` (uses its own `VIKUNJA_API_BASE` constant)

A follow-up issue tracks migration of these to the shared config when they're next touched.

### FR-011: Migrate `query_active_habits.py` (v1) is excluded explicitly

**Status**: Approved

`scripts/habits/query_active_habits.py` is the legacy v1 of the habits query script. v2 (in the runtime path) was migrated by #519. v1 is no longer invoked at runtime and is retained only as a reference. It is excluded from FR-008 scope and may be archived in a future cleanup.

### FR-012: Cycle aborts on partial/erroring poll response

**Status**: Approved

If the `GET /tasks/all` or `GET /projects` response shows signs of being incomplete or malformed (HTTP 5xx, empty `[]` when cache has non-zero entries, response truncation, JSON parse failure), the driver aborts the cycle BEFORE the set-diff phase. The cache is not mutated. The error is logged in `last-tick.json` under `layer_summary.<layer>.errors`. Next cycle re-attempts.

This guard prevents spurious deletions from a Vikunja blip without paying the N>1 latency cost.

---

## Non-Functional Requirements

### NFR-001: Cycle time stays ≤ 60s after project layer + full-poll

**Status**: Approved
**Threshold**: 60s end-to-end per cycle, measured from `started_at_utc` to `completed_at_utc` in `last-tick.json`.
**Measurement**: `duration_ms` field in `last-tick.json` (already populated by #518).

### NFR-002: All 7 RQ-4 use cases hit ≤ 5min worst-case latency

**Status**: Approved
**Threshold**: 5 minutes (300s) end-to-end from operator action to convergence in Felix's cache. Eliminates the 15-min deletion gap from RQ-4 § 4.
**Measurement**: integration test simulates each use case, observes cache state on next cycle.

### NFR-003: Full-poll completes in < 5s

**Status**: Approved
**Threshold**: < 5s for `GET /tasks/all` + `GET /projects` combined, at ≤100 tasks + ≤20 projects.
**Measurement**: per-layer `polled_at_utc` deltas in `layer_summary`.

### NFR-004: Cache-read contract from #519 is unchanged

**Status**: Approved
**Threshold**: byte-for-byte identical output from `read_cached_tasks` / `read_cached_task_by_id` / `read_completion_timestamps` / `read_freshness_pointer` / `is_cache_healthy` before vs after this mission's driver rework, given equivalent cache contents.
**Measurement**: regression test suite from #519 passes unchanged.

### NFR-005: URL config file permissions

**Status**: Approved
**Threshold**: `/data/services/openclaw/config/vikunja-base-url.txt` has mode `0644`, owner `claude:claude`. The directory `/data/services/openclaw/config/` is created with mode `0755`, owner `claude:claude`.
**Measurement**: deploy script verifies via `stat -c "%a %U:%G %n"`.

### NFR-006: Zero hardcoded URL strings in runtime-path scripts

**Status**: Approved
**Threshold**: `grep -rn "office2.tail0f5f56.ts.net\|100.92.197.90:3456" scripts/` returns hits ONLY in (a) the canonical config file path/value itself, (b) scripts explicitly listed out-of-scope in FR-010, and (c) test fixtures.
**Measurement**: grep command in success-criteria script.

---

## Constraints

### C-001: Polling only (no webhooks)

**Status**: Approved (inherited from #508 research C-001)

The webhook channel option is locked closed for this mission and the Epic. Vikunja v0.24.6 has `webhooks_enabled=true` but unconfigured per RQ-1 § 7. Pursuing webhooks is explicitly out of scope.

### C-002: No silent fallback on cache or sync failure

**Status**: Approved (inherits from #518 + #519)

A failed cache read or partial sync cycle surfaces as a structured stderr error and non-zero exit code. The driver does not write a partial cache state on a partial poll. Consumers do not fall back to direct Vikunja reads when the cache is missing or stale.

### C-003: Full-poll model replaces incremental — no hybrid

**Status**: Approved

The `updated_since` code path is removed from the driver. The `layer_pointers.before/after` fields in `last-tick.json` are deprecated (replaced by `layer_summary.<layer>.polled_at_utc`). No hybrid model is permitted; the spec rejects "incremental for routine cycles + occasional full poll for deletion" as a design.

### C-004: 3-way set diff is the only change-detection mechanism

**Status**: Approved

The driver has exactly one detection path: full poll → 3-way set diff → cache update + log events. Per-task GET probes, transient counters, or absence-confirmation algorithms are explicitly out.

### C-005: Project layer is audit/discovery only — no consumer reads in this mission

**Status**: Approved

No touchpoint added in this mission reads `project-cache.json` for business logic. Future missions that need project state in consumers are free to build on top of the cache; this mission does not create such consumers.

### C-006: Deletion cleanup is exactly three actions

**Status**: Approved

On confirmed deletion, the driver performs the three FR-003 actions and nothing else. No event emission to OpenClaw, no WhatsApp ping, no Vikunja API write-back, no cascading deletes across other state files.

### C-007: URL config scope is narrow — runtime path only

**Status**: Approved

FR-008 covers the 9 runtime-path scripts (6 touchpoints + driver + 2 write paths). One-off setup/utility scripts (per FR-010) are explicitly out of scope. The follow-up issue for the one-off scripts is NOT a blocker for this mission's merge.

### C-008: `change_mode: regular` (not `bulk_edit`)

**Status**: Approved

While FR-008 changes a fixed URL string across multiple files, the changes are mixed refactor (add `read_config()` import, replace hardcoded constant with `BASE_URL = read_vikunja_base_url()`) rather than pure find-replace. The `meta.json` `change_mode` field is set to `regular`. Per-WP review catches any misses.

---

## Success Criteria

### SC-001: All 7 RQ-4 use cases converge in ≤ 5min

Integration test simulates each use case (a–g per RQ-4) via the Vikunja API; observes the cache reflects the change on the next driver cycle.

### SC-002: Grep success criterion holds

`grep -rn "office2.tail0f5f56.ts.net\|100.92.197.90:3456" scripts/` returns hits only in the canonical config file path/value and the explicit FR-010 exclusions.

### SC-003: Project rename event recorded in tick log

After renaming a project in Vikunja, the next `last-tick.json` shows `project_renamed` event under `layer_summary.project_layer`.

### SC-004: Task deletion three-action cleanup observed

After deleting a habit task in Vikunja: schedule.yaml entry removed, `task_deleted` line appended to habits-history.jsonl, task absent from sync cache — all within one cycle.

### SC-005: Per-layer phases in tick log

`cat last-tick.json | jq .layer_summary` shows both `task_layer` and `project_layer` keys with `polled_at_utc` populated.

### SC-006: Morning habit check-in regression-free post-deploy

The day after deploy, the 07:05 ET morning check-in produces the same task list it would have produced under #519's incremental-poll driver. Verified by comparing the WhatsApp output to the prior day's output (minus any operator-driven changes).

### SC-007: Full-poll completes in < 5s

`layer_summary.task_layer.polled_at_utc` to `layer_summary.project_layer.polled_at_utc` delta is < 5s (sequential poll); or combined-poll duration is < 5s if implemented in parallel.

### SC-008: URL config change takes effect on next invocation

Edit `/data/services/openclaw/config/vikunja-base-url.txt` to a test value; invoke `python3 -m scripts.habits.morning_checkin_list`; verify the script reads the new value (e.g., via a debug log or by observing the HTTP request URL in a test environment).

---

## Key Entities

- **TaskCacheView** — unchanged from #519. Touchpoints continue to consume this contract.
- **ProjectCacheRecord** — NEW. A dict per project: `{id, title, is_archived, owner_id, last_polled_utc}`. Stored in `project-cache.json`.
- **LayerSummary** — NEW. Replaces the deprecated `layer_pointers.before/after`. Per-layer record of `polled_at_utc`, counts of `added`/`removed`/`updated`/`renamed`, and `errors` array.
- **TaskDeletedEvent** — NEW. JSONL line in `habits-history.jsonl`: `{type: "task_deleted", task_id, title, detected_at_utc}`.
- **ProjectDiffEvent** — NEW. JSONL line in a new `project-events.jsonl` (or appended to the existing `last-tick.json` events log — implementation choice): `{type: project_added|project_removed|project_renamed|project_archived|project_unarchived, project_id, title, detected_at_utc, ...}`.
- **VikunjaBaseUrlConfig** — NEW. Singleton file at `/data/services/openclaw/config/vikunja-base-url.txt`. One line: the URL.

---

## Out of Scope

- **Webhook integration** (locked closed per C-001).
- **Bulk-API optimization** (Vikunja v0.24.6 does not expose batch endpoints per RQ-1).
- **The broader #516 emission framework** (conflict log shape remains forward-compatible only).
- **Migration of one-off setup/utility scripts to the URL config** (deferred to a separate follow-up issue tracked from this mission).
- **Downstream consumer changes that USE project-layer state** (deferred until a use case emerges; per C-005).
- **Soft-delete / tombstone handling on the Vikunja side** (not supported by v0.24.6).
- **Schedule.yaml deletion-cleanup for non-habit tasks** (only habit tasks have schedule.yaml entries; deletion cleanup is no-op for non-habits).

---

## Assumptions

- **#518 is deployed** (verified 2026-06-05 16:07 UTC — `felix-vikunja-sync.timer` active, last fire 1 min before check)
- **#519 is deployed** (verified 2026-06-05 — `sync_cache.py` present, 6 touchpoints carry `TOUCHPOINT_SLA`, end-to-end `morning_checkin_list` run succeeded against the deployed cache)
- **Task count stays ≤ 100** — the design point that makes per-cycle full-poll trivially cheap. If task count grows substantially (e.g., > 500), revisit cadence trade-offs.
- **Project count stays ≤ 20** — current instance has 14 projects (RQ-1). Same caveat as task count.
- **The two URL bases are network-functionally equivalent** — verified during research (RQ-2). Config file initial value is the Tailscale HTTPS variant (`https://office2.tail0f5f56.ts.net/api/v1`).
- **felix-bot project membership is stable across cycles** — a task moved to a project felix-bot can't see is treated as deleted (EC-001). This is the desired behavior.

---

## Architecture Impact

Per the signal-to-doc-map `mission-architecture-impact` lookup, the change classes triggered are:

- **`service-added-or-modified`** (driver evolves: incremental → full-poll, adds project layer):
  - `docs/design/architecture/data/service-inventory.json`
  - `docs/design/architecture/service-inventory.md`
  - `docs/design/architecture/service-dependencies.view.md`
  - `docs/design/felix-capability-roadmap.md`

- **`data-flow-added-or-modified`** (new project-cache flow, new URL config flow):
  - `docs/design/architecture/data/data-flows.json`
  - `docs/design/architecture/data-flows.md`
  - `docs/design/architecture/data-flows.view.md`

- **`runbook-modified`** (sync-driver-ops.md updated with full-poll + project layer + deletion algorithm + URL config):
  - `docs/INDEX.md`
  - (and the runbook itself: `docs/runbooks/sync-driver-ops.md`)

The driver runbook (`docs/runbooks/sync-driver-ops.md`) gets the canonical operator-facing description of the new full-poll model, the project layer's audit semantics, the URL config form, and the three-action deletion cleanup.

---

## Notes for Implementation

- **The cache-read contract is the contract**. Touchpoints from #519 must continue to work unchanged. NFR-004 enforces this. If a WP is tempted to change `sync_cache.py`, that's a red flag — the helper is stable.
- **Removing the `updated_since` code path is destructive but bounded**. The driver is small (`scripts/sync/state.py` is the main file, ~500 lines). The set-diff path is simpler than the delta-apply path; the line count goes down, not up.
- **Project layer can land in a separate WP from the task-layer rework** — they share the same 3-way set diff helper but otherwise touch different code paths. Reviewers should validate each layer independently.
- **The URL config rollout (FR-006, FR-007, FR-008) is a separate WP**. The helper that reads the config + env-var fallback can be shared across all consumers via a single helper (`scripts/common/config.py` or similar). Touchpoints get a one-line refactor each.
- **No mid-feature spec-kitty upgrade** (per memory `feedback_no_mid_feature_upgrades`).
- **Deploy gate after merge**: per memory `feedback_speckitty_split_code_and_deploy_missions`, this mission's WPs do not need cross-WP intermediate deploys (they all land on `main` together at merge). Deploy is a single step after the mission's merge commit.

---

## Constitutional Compliance

- **Directive 6 (deterministic vs stochastic split)**: the driver work is fully deterministic — full-poll, set diff, cache update. No LLM judgment is required. All WPs route through Python helpers; the agent's role is mechanical.
- **Directive 8 (operational symptom required)**: every functional requirement maps to an operator-observable symptom (per the issue body's "Observable Symptom" section, retained here): stale habit reminders for 15+ min after deletion, recurring "which URL base is canonical?" tax, missing detection of new projects.
- **Standing directive (Architecture Documentation)**: this mission modifies a deployed service (`felix-vikunja-sync.service`), modifies the data flow (cache schema additions), and modifies a runbook (sync-driver-ops.md). All listed `doc_targets` from the signal-to-doc-map MUST update in the same merge.

---

## Risk Considerations

- **Risk: full-poll regression on cycle time** — mitigated by NFR-001 (60s ceiling) and NFR-003 (< 5s poll). If polling at full-poll scale exceeds these, the cycle aborts cleanly per FR-012.
- **Risk: spurious deletions during Vikunja transient errors** — mitigated by FR-012 (cycle aborts on partial response).
- **Risk: project layer adds cycle cost** — mitigated by NFR-001 ceiling check. At 14 projects, `GET /projects` is one HTTP call returning < 5KB.
- **Risk: URL config file becomes a single point of failure** — mitigated by the env var wrapper (FR-007), which holds the same value and is available to scripts even if the file becomes unreadable transiently. The deploy script also creates the file before any consumer reads it.
- **Risk: deletion cleanup misses a consumer that doesn't handle `MissingTaskError`** — mitigated by the explicit post-merge sweep planned for downstream-leftovers verification (per operator request 2026-06-05).
- **Risk: rework of #518's incremental code introduces a regression** — mitigated by NFR-004 (cache-read contract unchanged), the unchanged #519 touchpoint surface, and the existing #519 test suite as a regression guard.

---

## Spec-Ready Criteria

- [x] Discovery answers locked (5 design points confirmed by operator 2026-06-05)
- [x] Source research (RQ-4 § 4) reviewed and design rationale recorded
- [x] All FRs, NFRs, Constraints have `Status: Approved` (locked, not Proposed)
- [x] Success criteria are testable
- [x] Architecture Impact lists doc_targets from signal-to-doc-map
- [x] Out of Scope is bounded
- [x] Assumptions are verified
- [x] Constitutional compliance recorded
