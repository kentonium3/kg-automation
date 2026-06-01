---
title: Data Flows
doc_type: reference
status: approved
---

# Data Flows

Authoritative data: [`data/data-flows.json`](<./data/data-flows.json>)

## Active Flows

### Vikunja Web UI (F001)

```
Kent (Mac/iPhone) → HTTPS via Tailscale Serve → Vikunja :3456 → SQLite
```

Direct task management through the browser. Accessible from any Tailscale-connected device at `https://office2.tail0f5f56.ts.net`.

### Obsidian Vault Sync (updated F011)

**Live sync** (Obsidian Sync — bidirectional):
```
Mac (Obsidian) ↔ Obsidian Sync cloud ↔ office2 (ob sync --continuous) ↔ Obsidian Sync cloud ↔ iPhone (Obsidian)
```

Three-device sync loop: Mac, office2, and iPhone all stay in sync via Obsidian Sync cloud. The `ob` CLI on office2 runs as a continuous daemon (`obsidian-sync.service`, kgale user unit), syncing to `/home/kgale/second-brain/notes`. Changes on any device propagate to the others in near real-time. Obsidian Sync is the live sync mechanism — not git.

**Consumer**: `felix-admin-capture` reads from `/home/kgale/second-brain/notes/01-Inbox/` (3x daily via OpenClaw cron). Processed items are moved to `/home/kgale/second-brain/notes/02-Inbox-Processed/` once the inbox pre-scan helper (#149) ships.

### Second Brain Git Sync (F011)

**Non-vault content** (git — bidirectional, every 15 min):
```
office2 (/home/kgale/second-brain) ↔ git pull --rebase + push ↔ GitHub
```

Bidirectional git sync every 15 minutes via `second-brain-sync.timer` (kgale user unit). Syncs non-vault content (agents/, logs/, config). Vault content (`notes/`) is excluded via `.gitignore` — Obsidian Sync handles that. Replaces the old outbound-only vault-snapshot.

### Nightly Backup

```
office2 (/data/services, /data/transcripts, /home/*) → Restic → /mnt/backups/restic-repo
```

Runs at 4AM daily via claude's crontab. GFS retention policy. Excludes transcribe models, temp files, and caches.

### Security Audit

```
audit.sh → compare running state against baselines → log alerts
```

Runs at 3AM daily. Checks: Docker images, enabled services, listening ports, SSH keys, crontabs, pip packages, hosts file, pth files.

### OpenClaw → Vikunja API (F007)

```
OpenClaw agent → HTTPS via Tailscale Serve → Vikunja REST API :3456 → SQLite
```

OpenClaw agents use the vikunja_api skill to create, read, update, and query tasks
via the Vikunja REST API. Authentication is via Bearer token read from the
credential store at runtime. Used by all downstream features that touch tasks.

### Observation Digest (F014)

```
Felix agent → log_action.py → JSONL → summarize.py (15-min timer) → Markdown → Obsidian Sync → Kent's devices
```

Agent activity logging and digest generation pipeline:
1. Felix agents call `log_action.py` via OpenClaw's exec tool with structured arguments
2. `log_action.py` validates, enforces schema, and appends a JSONL entry to `~/second-brain/agents/logs/{agent}/YYYY-MM-DD.jsonl`
3. `summarize.py` runs every 15 minutes via systemd timer, reads JSONL, generates per-agent Markdown digests at `~/second-brain/notes/Agent-Logs/`
4. Digests reach Kent's Mac and iPhone via the existing Obsidian Sync flow

Raw JSONL logs are gitignored in the second-brain repo. Digest Markdown flows through Obsidian Sync (not git).

### Habits Scripts-First Morning + Reply (#371)

Mirror of the #309 escalation port — same architecture (canonical per-Kent-day state file + deterministic parser + narrow LLM judgment helper) replicated for the habits morning + reply flow. The original bug (#371): the morning cron tick and the reply tick are two separate openclaw sessions; the reply session had no access to the morning session's numbered list and regenerated it independently — orderings diverged, replies got applied to the wrong habits. The fix moves the ordered list and the reply mapping into helper scripts; the agent becomes a thin orchestrator.

**Morning tick (write path)**:

```
felix-admin-habits agent (cron habits-morning-checkin, 7:05 AM ET)
  → scripts/habits/morning_checkin_list.py
       ├─ scripts/habits/query_active_habits_v2.py  (Vikunja GET /projects/13/tasks, filter due_date<=now/d AND done=false)
       └─ scripts/habits/exclude_completed_v2.py    (reads /data/services/openclaw/state/habits-history.jsonl)
  → /data/services/openclaw/state/habits/morning-checkin-<YYYY-MM-DD>.json   (atomic write — canonical ordering)
  → stdout (formatted WhatsApp message, relayed verbatim by the agent)
```

The artifact ordering is byte-identical to the formatted WhatsApp message (FR-002). The agent relays the helper's stdout verbatim with NO commentary or re-ordering (FR-007). One file per Kent-day; ~1 KB at N=8-12 habits (NFR-005); no rotation (~365 files/year).

**Reply tick (read path)**:

```
felix-admin-habits agent (reply tick)
  → scripts/habits/parse_morning_reply.py
       └─ /data/services/openclaw/state/habits/morning-checkin-<YYYY-MM-DD>.json   (read-only)
  → stdout: {tuples, judgment_required, errors} JSON (data-model Entity 2)

For each tuple in deterministic tuples:
  → scripts/habits/record_completion.py --task-id <id> --state <state> --date <date> --source kent_reply --idempotent
       (Phase 3 helper unchanged per C-001/FR-010; three-write to Vikunja + JSONL state log)
```

The parser NEVER re-queries Vikunja (FR-008) — the morning-list artifact is the authoritative source of position->task_id mapping for the date. If the artifact is missing (exit code 4), the agent files a P2-bug via `felix-file-issue.py` rather than falling back to live Vikunja state (FR-009).

**Narrow LLM judgment surface** (only when parser emits `judgment_required`):

```
scripts/habits/parse_morning_reply.py emitted judgment_required (e.g., "PT done" matches multiple PT habits)
  → scripts/habits/judgment/disambiguate_reply.py
       ├─ /data/services/openclaw/secrets/anthropic   (file read 0600)
       └─ api.anthropic.com   (HTTPS via anthropic-python SDK, claude-haiku-4-5)
  → stdout: {result: chosen, chosen_task_id} OR {result: clarify, suggested_question}
```

The LLM is NEVER in the path for the bulk of replies — only for ambiguous reply tokens (FR-006). Mirrors the #343 doc-audit judgment pattern. Validates `chosen_task_id` is within the input's candidate set; out-of-set responses are a hard-fail (exit code 5). On `clarify`, the agent asks Kent ONE clarifying question per ambiguity cluster — never silently guesses.

### Doc-Auditor Direct Anthropic API (#343, v2 since #362)

> ⏸ **Operational status**: this flow is **suspended indefinitely** since
> 2026-05-26 (timer `disabled` + interpretation flags `false` + GH Actions
> `disabled_manually`). The architecture below describes the intended runtime
> behavior; the system does not currently execute it. See the
> [doc-auditor driver runbook](<../../runbooks/doc-auditor-driver-ops.md>)
> for the full suspension context and reactivation gate ([#137](https://github.com/kentonium3/kg-automation/issues/137)).

```
felix-doc-auditor.timer → felix-doc-auditor.service → scripts/doc_audit/run.py
  → Anthropic API (HTTPS, anthropic-python SDK)
  → gh CLI (subprocess; kg-felix-bot PAT)
  → /home/kgale/second-brain/agents/logs/doc-auditor-YYYY-MM-DD.md (file append)
```

Post-#343 doc-audit tick flow. The systemd user timer (`felix-doc-auditor.timer`, `OnCalendar=hourly`, `Persistent=true`) launches the oneshot service which execs the Python driver. The driver:

1. Loads the Anthropic API key from `/data/services/openclaw/secrets/anthropic` (0600 file read) — see **Doc-Auditor Credential Read** below.
2. Calls Anthropic directly at judgment moments. **Post-#400 the surface is five moments**: Moment 0 has TWO surfaces, one per signal class — **drift_interpretation** (per mapped drift event, introduced by #362, cron-path corrected by #391) and **audit_interpretation** (per in-scope doc within a commit-derived audit, introduced by #400). Both classify PROPOSED_EDIT / JUDGMENT_REQUIRED / NO_CHANGE_NEEDED with explicit confidence using a structural-twin module pattern. Moment 1 — **tier_classification** (consumes PROPOSED_EDIT verdicts from either Moment 0 surface). Moments 2 and 3 — **debt_body_generation** and **cross_file_implication** (unchanged from #343). The drift Moment 0 cron-path invocation flows through `signals/drift_event.py::DriftEventSignalSource.commit()` → `routing/drift_moment0.py::route_drift_event()` (post-#391); the audit Moment 0 invocation flows through `helpers/handle_audit_routing.py`'s no-proposals branch (post-#400, gated by `[audit_interpretation].enabled`). PROPOSED_EDIT verdicts at confidence ≥0.80 from EITHER Moment 0 surface are routed through `tier_classification` (preserving SKILL.md §4.3 guardrails). Prompt caching is enabled via the SDK to amortize the cached boilerplate across calls within a tick.
3. Mutates GitHub state exclusively via `gh` subprocess (issue list/edit/create/close, label add/remove, comment create) under the `kg-felix-bot` PAT.
4. Appends a per-tick prose entry to the operator-readable activity log under `/home/kgale/second-brain/agents/logs/`.

This replaces the pre-#343 path that routed through openclaw-gateway and an LLM-interpreted `SKILL.md` procedure. **No openclaw-gateway proxy is in the path** — the driver talks to Anthropic, GitHub, and the filesystem directly. The two Moment 0 LLM call legs are registered as their own flows (`doc-audit-drift-interpretation-llm` and `doc-audit-audit-interpretation-llm`) below for graph clarity. Both Moment 0 surfaces additionally write to their respective ledgers (`doc-audit-drift-ledger-write` and `doc-audit-audit-ledger-write`).

**Signal sources consumed (read-only)**:
- `/data/services/security-monitor/logs/drift-events.jsonl` — drift adapter signal source
- `/home/claude/kg-automation/docs/design/architecture/data/doc-domain-map.json` — changed-file → owning-doc scope contract
- `/home/claude/kg-automation/docs/design/architecture/data/signal-to-doc-map.json` — signal-class → candidate-doc map

### Doc-Auditor Tick Signal Write (#343)

```
scripts/doc_audit/run.py → /data/services/openclaw/felix-doc-auditor-driver/last-tick.json (file write, atomic rename)
```

At the end of each tick, the driver writes a structured JSON tick signal capturing `status`, `exit_code`, `timestamp_utc`, `signals_processed`, judgment-call counts, token usage, and any errors. This is the canonical health-check and tick-observation surface (replaces the pre-#343 reliance on parsing the prose activity log). The file is overwritten each tick — latest-wins. See `contracts/tick-signal.contract.md` for the full schema.

### Doc-Auditor Credential Read (#343)

```
scripts/doc_audit/run.py → /data/services/openclaw/secrets/anthropic (file read, mode 0600)
```

Sensitive credential read path. The scripts-first driver loads the Anthropic API key directly from disk at tick start. Replaces pre-#343 indirect access through openclaw-gateway's auth-profiles indirection. The credential itself is unchanged (same key, same storage); the driver process is now the second consumer of the same secret. Sibling consumer is `openclaw-gateway` (unchanged), which holds it via its native `auth-profiles.json` mechanism.

**Sensitivity discipline**: the key is loaded once per tick into process memory only. It is never logged, never emitted in the tick signal, and never echoed to the activity log.

### Escalation Event Writes (#309 — JSONL state migration, Phase 6 of ADR-0002)

Three-write ordering per research D6 (Vikunja side-effect FIRST, JSONL append LAST — failing the unreliable remote ops first surfaces network issues before any state_log line is written):

```
felix-admin-escalation agent → scripts/escalation/record_completion.py
  → Vikunja /tasks/<id>/comments + /tasks/<id>   (PUT [Felix-Escalation] comment, PATCH done/due_date)
  → scripts/common/state_log.py → /data/services/openclaw/state/escalation/<project-slug>-escalation-history.jsonl
```

Side-effects per event_type:
- `level_sent` — WhatsApp send + `[Felix-Escalation]` comment write (during the C-001 soak)
- `snoozed` / `dismissed` — `[Felix-Escalation]` comment write
- `done` — `PATCH done=true` + `[Felix-Escalation]` comment write
- `rescheduled` (kent_reply source) — `PATCH due_date` + `[Felix-Escalation]` comment write

JSONL state log files are per-project (NFR-003, research D2): filename-based partition keyed on project slug. Schema (data-model Entity 1): `domain=escalation`, `state ∈ {level_sent, snoozed, dismissed, done, rescheduled}`, `source ∈ {agent, reconcile, backfill, kent_reply, operator_repair}`.

### Escalation State Read (#309)

```
felix-admin-escalation agent → scripts/escalation/derive_state.py
  → scripts/common/state_log.py → <project-slug>-escalation-history.jsonl   (read-only)
```

`derive_state(records)` is a pure function. Input: list of JSONL records for one task (newest-first). Output: `EscalationState` dataclass with `current_state`, `snooze_active_until`, `next_eligible_level`, `last_event_recorded_at`. All escalation policy lives here; the agent no longer parses `[Felix-Escalation]` comments post-#309 cutover.

### Escalation Reconcile Sweep (#309)

```
felix-admin-escalation agent → scripts/escalation/reconcile_completions.py
  → Vikunja /projects/<id>/tasks + /tasks/<id>   (GET only)
  → scripts/escalation/record_completion.py --no-vikunja   (synthetic record emit, source=reconcile)
  → scripts/common/state_log.py → <project-slug>-escalation-history.jsonl
```

Runs at tick start (FR-005). Enumerates escalation-subscribed tasks (those with at least one prior `level_sent` JSONL record AND no terminal record since); GETs current Vikunja state per task; emits synthetic records when:
- `vikunja.done=true` but JSONL has no `done` → synthetic `{state: "done", source: "reconcile"}`
- `vikunja.due_date != last_rescheduled_to` (and no terminal record) → synthetic `{state: "rescheduled", source: "reconcile", reschedule_to: <new>}`

### Escalation Historical Backfill (#309)

```
Operator (Kent) → scripts/escalation/backfill_jsonl_from_comments.py
  → Vikunja /projects, /projects/<id>/tasks, /tasks/<id>/comments   (GET only)
  → /data/services/openclaw/state/escalation/pre-phase6-snapshot.json   (snapshot — written BEFORE any JSONL writes)
  → scripts/common/state_log.py → <project-slug>-escalation-history.jsonl   (source=backfill)
```

One-shot operator-driven replay of existing `[Felix-Escalation]` comments to JSONL records (FR-006). Read-only on Vikunja (GET only). The pre-backfill snapshot at `pre-phase6-snapshot.json` is the rollback substrate (data-model Entity 4) — written exactly once per backfill invocation. Idempotent on re-run via the Phase 2 (task_id, date, state) dedup; malformed comments are NOT replayed (they surface in the backfill report).

### Enrichment Record Writes (#310 — JSONL state migration, Phase 7 of ADR-0002 / final)

Three-write ordering per the ADR-0002 contract (Vikunja side-effect FIRST, JSONL append SECOND, ack log THIRD — failing the unreliable remote ops first surfaces network issues before any state_log line is written):

```
felix-admin-tasker agent → scripts/enrichment/record_completion.py
  → Vikunja /tasks/<id>/comments                                  (PUT [Felix] enrichment | <state> | <ISO timestamp>)
  → /data/services/openclaw/state/enrichment/enrichment-history.jsonl   (fcntl-locked append)
  → ~/second-brain/agents/logs/<date>.md                          (ack log, best-effort — never blocks)
```

Triggers: `enrich_task` delegation from felix-admin-capture, `retroactive_enrichment` batch, `detect_incomplete` single-task proposal. Per FR-013 (Q10 soft-fail): if the JSONL step fails AFTER the Vikunja comment lands, `record_completion.py` logs a warning and exits 0 — the Vikunja state is consistent and the next enrichment cycle re-proposes (annoying but harmless; reconcile recovers the JSONL row). Pre-Vikunja failures (idempotency-check I/O error) surface as exit 2 cleanly because no side-effect has landed.

JSONL state log is a **single file** (NOT per-project — enrichment is system-wide; ~10 events/month natural traffic). Schema (data-model E1): `EnrichmentCompletion(task_id, state, timestamp_utc, source[, note], schema_version=1)`. `VALID_STATES = {proposed, confirmed, skipped, declined}`. `VALID_SOURCES = {agent, reconcile, backfill, operator_repair}`.

### Enrichment Reconcile / Backfill (#310)

```
Operator (Kent) via cutover_tasker.py → scripts/enrichment/reconcile_completions.py
  → Vikunja /projects, /projects/<id>/tasks, /tasks/<id>/comments   (GET only)
  → scripts/enrichment/record_completion.py --no-vikunja --source backfill
  → /data/services/openclaw/state/enrichment/enrichment-history.jsonl
```

One-shot operator-driven backfill at cutover time (FR-006..FR-009). Read-only on Vikunja (`--no-vikunja` on the replay path skips the comment-write step). Window: 2026-04-11 onward (post-#308 pattern formalization, per FR-008). Disambiguates habit comments (`[Felix] YYYY-MM-DD | <state>`) from enrichment comments (`[Felix] enrichment | <state> | <timestamp>`) by inspecting the second pipe-separated field — only the literal `enrichment` second-field shape is replayed. Idempotent — re-running on the same comment set produces no duplicates (FR-009).

### Enrichment State Read (#310)

```
felix-admin-tasker agent → scripts/enrichment/derive_state.py
  → /data/services/openclaw/state/enrichment/enrichment-history.jsonl   (read-only scan)
```

`derive_state(records)` is a pure function. Input: list of JSONL records for one task (newest-first). Output: `EnrichmentState` with `current_state`, `last_event_recorded_at`. Single-offer policy (skipped/declined are terminal) lives here. Consumed by the tasker agent at every check-before-propose, by `record_completion.py` for idempotency, and by `reconcile_completions.py` for dedup. The agent NO LONGER parses `[Felix] enrichment` Vikunja comments post-cutover.

### Tasker Cutover (#310)

```
Operator (Kent) → scripts/openclaw/helpers/cutover_tasker.py
  → cp scripts/openclaw/skills/task-intelligence/SKILL.md → /home/claude/.openclaw/skills/task-intelligence/SKILL.md
  → cp scripts/openclaw/agents/felix-admin-tasker/AGENTS.md → /data/services/openclaw/tasker-agent/AGENTS.md
  → python3 -m scripts.enrichment.reconcile_completions       (JSONL backfill)
  → ~/.config/openclaw/cutover-310.done                       (idempotency marker)
```

One-shot operator cutover (FR-010, FR-011). Closes the pre-existing skill deployment gap (`task-intelligence` SKILL.md referenced in the deployed AGENTS.md but never deployed — surfaced during #310 spec-readiness probe), deploys the cut AGENTS.md (≤14K chars per NFR-002), runs the JSONL backfill, and writes the marker. Idempotent — re-runs are no-ops unless `--force` is supplied. Pattern source: `scripts/doc_audit/helpers/cutover_362.py`. Exit codes: 0 success/no-op / 1 filesystem / 2 reconcile failed / 3 invalid args.

### Escalation Q10 Hard-Fail (#309)

```
scripts/escalation/reconcile_completions.py (or record_completion.py during validate)
  → scripts/escalation/hard_fail.py
       ├─ dedup_existing_open(): gh issue list --state open --search '...' (research D9)
       └─ file_hard_fail_bug(): scripts/openclaw/agents/main/felix-file-issue.py (subprocess)
            → gh CLI → GitHub API (gh issue create)
```

Hard-fail trigger conditions (FR-008, research D8):
1. `malformed_jsonl_record` — schema validation (via `schema.py`'s `validate_event_params`) fails on a JSONL line.
2. `phantom_subscription` — Vikunja shows `[Felix-Escalation]` comments but JSONL has no anchor records.
3. `derive_state_inconsistency` — `derive_state()` raises `EscalationStateError`.

**Surface separation**: `scripts/escalation/schema.py` is the event-parameter validator only (exposes `EVENT_TYPE_PARAMETERS`, `validate_event_params`, `EscalationSchemaError`). It does NOT file bug reports. The Q10 hard-fail bug-filing + dedup helper lives at `scripts/escalation/hard_fail.py`, owned by WP04 in this same mission (forward-referenced from WP08 per C-004).

Filing path: `hard_fail.py` runs the dedup pre-check (`gh issue list --state open --search 'in:title "(task #<id>)" "Escalation hard-fail"'` per research D9). If an open issue exists, it returns `{filed: False, deduped: True}` and does NOT call `felix-file-issue.py`. Otherwise it invokes `scripts/openclaw/agents/main/felix-file-issue.py` as a subprocess; that helper calls `gh issue create`. Identity: `kg-felix-bot` (classic PAT). Labels: `P2-bug, area/escalation`. Body template per data-model Entity 5.

### Doc-Audit Drift Interpretation LLM (#362, cron-path corrected by #391)

```
scripts/doc_audit/signals/drift_event.py::DriftEventSignalSource.commit() (cron entry point)
  ├─ delegates to →
scripts/doc_audit/helpers/handle_drift_events.py::process_events()  (operator-replay entry point only — NOT used by cron post-#391)
  └─ delegates to →
scripts/doc_audit/routing/drift_moment0.py::route_drift_event()   (shared Moment 0 routing helper, #391)
  → scripts/doc_audit/judgment/drift_interpretation.py
       ├─ /data/services/openclaw/secrets/anthropic   (file read 0600, via shared JudgmentClient)
       └─ api.anthropic.com   (HTTPS via anthropic-python SDK, model claude-haiku-4-5-20251001)
  → DriftVerdict (PROPOSED_EDIT / JUDGMENT_REQUIRED / NO_CHANGE_NEEDED, confidence ∈ [0.0, 1.0])
```

Moment 0 of the doc-audit judgment surface, introduced by #362. **Cron-path invocation site corrected by #391**: the cron entry point is `signals/drift_event.py::DriftEventSignalSource.commit()`, which delegates to the shared helper `routing/drift_moment0.py::route_drift_event()`. The library/CLI surface `helpers/handle_drift_events.py::process_events()` delegates to the *same* routing helper but is invoked only by operator replay (`python3 -m doc_audit.helpers.handle_drift_events`) — not by the cron service.

Per mapped drift event, the routing helper assembles a `DriftInterpretationContext` (event metadata + diff + mapping rationale + current contents of each `doc_target`) and calls `drift_interpretation.interpret(client, context)`. The helper builds a cache-aware prompt (system portion ≥80% of tokens, marked `cache_control: ephemeral` per the existing `tier_classification.py` pattern — C-005), calls Anthropic via the shared `JudgmentClient` (no new SDK creation — C-004), and parses + validates the response against the E1 invariants (`verdict ∈ {PROPOSED_EDIT, JUDGMENT_REQUIRED, NO_CHANGE_NEEDED}`, `confidence ∈ [0.0, 1.0]`, `proposed_edit` present iff verdict is PROPOSED_EDIT, etc.).

Verdict routing (inside `routing/drift_moment0.py::route_drift_event()`):

- **PROPOSED_EDIT at confidence ≥0.80** → translate via `drift_to_proposed_edit.build()` to a `ProposedEdit` (`change_type='drift_derived'`, `tier='tier_b'` placeholder) and route through the existing `tier_classification` surface (Moment 1). Tier A → auto-commit; Tier B → PR; judgment → docs-debt issue. Defense-in-depth: drift-derived edits the classifier can't confidently tier go to judgment.
- **PROPOSED_EDIT or NO_CHANGE_NEEDED at confidence <0.80** → demoted to JUDGMENT_REQUIRED at the helper boundary; rationale + proposed-edit context folded into the issue body.
- **JUDGMENT_REQUIRED** → file a `[doc-audit]` issue with the LLM's specific question (not "review the diff"), per FR-006.
- **NO_CHANGE_NEEDED at confidence ≥0.80** → auto-close the drift event with a one-line summary; no GitHub issue is filed (FR-007).

Retry policy: 30s / 60s / 120s exponential backoff (FR-008). On retry exhaustion, `interpret()` raises `DriftInterpretationError`; the caller (the cron entry point `signals/drift_event.py` or the replay entry point `helpers/handle_drift_events.py`) catches it, writes a `RETRY_EXHAUSTED` ledger row, and escalates via the pre-#362 `[doc-audit]` issue path with the diagnostic block embedded in the body (FR-009). The routing helper itself never catches this exception — letting it propagate keeps fallback semantics in one place at each caller. Schema violations (malformed JSON, out-of-set `verdict`, out-of-bound `confidence`, out-of-set proposed `doc_path`) demote to JUDGMENT_REQUIRED rather than triggering retry exhaustion (C-006).

Gated by `[drift_interpretation].enabled` in `scripts/doc_audit/config.toml`. Flipping to `false` reverts to deterministic-only behavior in ≤60s (NFR-007 / FR-013) — the next tick reads the updated config and skips Moment 0 entirely.

### Doc-Audit Drift Ledger Write (#362, cron-path corrected by #391)

```
scripts/doc_audit/signals/drift_event.py (cron entry point)   →   scripts/doc_audit/routing/drift_moment0.py::route_drift_event()
scripts/doc_audit/helpers/handle_drift_events.py (replay)     →   scripts/doc_audit/routing/drift_moment0.py::route_drift_event()
  → scripts/doc_audit/output/drift_ledger.py
  → /data/services/security-monitor/logs/drift-events-ledger.jsonl   (append-only JSONL, atomic tempfile + rename)
```

Terminal write for every processed drift event. After the verdict is routed (PROPOSED_EDIT through `tier_classification`, JUDGMENT_REQUIRED via `[doc-audit]` issue, NO_CHANGE_NEEDED auto-closed, or RETRY_EXHAUSTED escalated), `routing/drift_moment0.py::route_drift_event()` calls `drift_ledger.append()` with one `AuditLedgerEntry` (data-model E3). Both the cron entry point (`signals/drift_event.py`) and the replay entry point (`helpers/handle_drift_events.py`) reach this write via the same routing helper, guaranteeing identical behavior across the two surfaces:

```
{
  "event_id": "47:2026-05-22T03:00:07Z",
  "timestamp_utc": "2026-05-22T03:00:07Z",
  "baseline": "openclaw-cron",
  "mapping_id": "openclaw-cron-drift",
  "verdict": "PROPOSED_EDIT",
  "confidence": 0.90,
  "outcome": "auto_committed",
  "doc_paths": ["docs/design/architecture/data/service-inventory.json"],
  "retry_count": 0,
  "latency_ms": 7320,
  "tier_classification_outcome": "tier_a",
  "github_issue_number": null,
  "schema_version": 1
}
```

`outcome ∈ {auto_committed, pr_filed, issue_filed, auto_closed, retry_exhausted}`. Append is atomic (tempfile + rename). The ledger is read-only consumed by the `drift_ledger` CLI subcommands (`summary`, `tail`, `triage-rate`) which back the NFR-001 operator-triage-rate metric over a configurable trailing window (default 7 days). No rotation in v1 (~3-10 entries/day at current drift volume; ~1.1k entries/year).

### Doc-Audit Audit Interpretation LLM (#400)

```
scripts/doc_audit/helpers/handle_audit_routing.py (no-proposals branch)
  → scripts/doc_audit/judgment/audit_interpretation.py
       ├─ /data/services/openclaw/secrets/anthropic   (file read 0600, via shared JudgmentClient)
       └─ api.anthropic.com   (HTTPS via anthropic-python SDK, model claude-haiku-4-5-20251001)
  → list[AuditVerdict]   (one per in-scope doc; PROPOSED_EDIT / JUDGMENT_REQUIRED / NO_CHANGE_NEEDED, confidence ∈ [0.0, 1.0])
```

Moment 0 (commit-audit surface), introduced by #400. Structural twin of `doc-audit-drift-interpretation-llm` adapted for commit-derived `Doc audit:` issues. The invocation site is `handle_audit_routing.py`'s no-proposals branch — i.e., when the deterministic pattern-matching path finds zero auto-applyable proposals AND `[audit_interpretation].enabled = true` in `scripts/doc_audit/config.toml`. The routing helper assembles an `AuditInterpretationContext` (audit issue metadata + commit SHA + commit diff + in-scope doc paths from the audit body + per-doc current contents from disk) and invokes `interpret_audit(client, context)`, which calls Anthropic ONCE PER in-scope doc via the shared `JudgmentClient` (cache-aware prompt: system portion ≥80% of tokens marked `cache_control: ephemeral` per the existing `tier_classification.py` / `drift_interpretation.py` pattern).

Per-doc verdict routing (inside `handle_audit_routing.py`):

- **PROPOSED_EDIT at confidence ≥0.80** → translate to a `ProposedEdit` and route through the existing `tier_classification` surface (Moment 1). Tier A → auto-commit; Tier B → pending-approval issue; judgment → docs-debt issue.
- **PROPOSED_EDIT or NO_CHANGE_NEEDED at confidence <0.80** → demoted to JUDGMENT_REQUIRED at the helper boundary; rationale + proposed-edit context folded into the consolidated comment.
- **PROPOSED_EDIT proposing an edit to a path NOT in the audit's in-scope list** → semantic violation → demoted to JUDGMENT_REQUIRED.
- **JUDGMENT_REQUIRED** → accumulated into a SINGLE consolidated comment posted to the audit issue (per research D3 — avoids comment noise; operator reads one comment to see all questions).
- **NO_CHANGE_NEEDED at confidence ≥0.80 across ALL in-scope docs** → auto-close the audit issue with a summary comment listing the docs as "clean per LLM check" (FR-008).
- **NO_CHANGE_NEEDED at confidence ≥0.80 for SOME docs but ANY doc is JUDGMENT_REQUIRED** → audit stays open with the consolidated comment (FR-009).

Per-doc isolation: retry exhaustion on doc N does NOT prevent docs N±1 from being evaluated. The helper emits a synthetic JUDGMENT_REQUIRED verdict (`confidence=0.0`, `rationale="LLM retry exhausted"`) for the failed doc and continues. Catastrophic per-audit failures fall back to the pre-#400 no-proposals path (lock release + "no automatable edits" comment from the today-merged `handle_audit_routing` fix).

Gated by `[audit_interpretation].enabled` in `scripts/doc_audit/config.toml`. Flipping to `false` reverts to the pre-#400 no-proposals path in ≤60s (FR-013) — the next tick reads the updated config and skips Moment 0 entirely. The deterministic pattern-matching path (when proposals IS non-empty) is unaffected per spec C-002.

Weekly audits (no triggering SHA, empty diff) skip Moment 0 entirely (C-006) — existing weekly behavior preserved.

### Doc-Audit Audit Ledger Write (#400)

```
scripts/doc_audit/helpers/handle_audit_routing.py
  → scripts/doc_audit/output/audit_ledger.py
  → /data/services/openclaw/state/doc_audit/audit-events-ledger.jsonl   (append-only JSONL, atomic tempfile + rename)
```

Terminal write for every in-scope doc evaluated by `audit_interpretation`. One row per (audit_issue, doc_path) pair — i.e., a single audit with 5 in-scope docs produces 5 ledger rows. After the verdict is routed (PROPOSED_EDIT through `tier_classification`, JUDGMENT_REQUIRED accumulated into the consolidated comment, NO_CHANGE_NEEDED auto-closed when all docs clean, or RETRY_EXHAUSTED escalated), `handle_audit_routing.py` calls `audit_ledger.append(entry)`:

```
{
  "audit_issue": 412,
  "doc_path": "docs/design/architecture/data/service-inventory.json",
  "verdict": "PROPOSED_EDIT",
  "confidence": 0.90,
  "outcome": "auto_committed",
  "retry_count": 0,
  "latency_ms": 5840,
  "tier_classification_outcome": "tier_a",
  "timestamp_utc": "2026-05-23T17:42:00Z",
  "schema_version": 1
}
```

`outcome ∈ {auto_committed, pr_filed, judgment_required_posted, auto_closed, retry_exhausted}`. Note `judgment_required_posted` replaces drift's `issue_filed` because audit appends a comment to the EXISTING audit issue rather than creating a new one (per spec D1). The ledger is consumed by the `audit_ledger` CLI subcommands (`summary`, `tail`, `triage-rate`) which back the NFR-001 operator-triage-rate metric (target ≤30%). No rotation in v1.

### Doc-Audit Cutover #362 Issue Close (#362)

```
Operator (Kent) → scripts/doc_audit/helpers/cutover_362.py
  → gh issue list --search 'is:issue is:open label:P3-candidate "[doc-audit]" in:title'
  → per match: gh issue comment + gh issue close
  → /data/services/security-monitor/.drift-events.cursor   (reset to 0)
  → ~/.config/doc-audit/cutover-362.done   (sentinel marker)
```

One-shot operator-driven backlog cutover that bridges from the pre-#362 deterministic-only pipeline into the new Moment 0 pipeline. Invoked manually post-deploy (Quickstart §3 of the mission's `quickstart.md`). Behavior:

1. Check marker `~/.config/doc-audit/cutover-362.done` — if present and `--force` not set, exit 0 (idempotent no-op).
2. Query GitHub for the 13 known pre-#362 `[doc-audit]` P3 issues (#351-#360, #368-#370). For each: post a comment noting the new pipeline will reprocess the underlying drift event, then close.
3. Reset the drift-events cursor at `/data/services/security-monitor/.drift-events.cursor` to `0` (calls `handle_drift_events --reset-cursor` or writes `0` directly) so existing piled-up drift events get reprocessed via Moment 0 on the next tick.
4. Write the sentinel marker file with `mission`, `mission_id`, `run_at_utc`, `closed_issues`, `cursor_reset_to`.

Identity for the GitHub mutations: `kg-felix-bot` (classic PAT, via `gh` CLI subprocess). `--dry-run` prints intent without mutations. The marker file is permanent — leave it in place as historical record per Quickstart §8.

### Doc-Audit Cleanup #391 Issue Close (#391)

```
Operator (Kent) → scripts/doc_audit/helpers/cleanup_391.py
  → per static issue (#378-#390): gh issue comment + gh issue close → api.github.com
  → ~/.config/doc-audit/cleanup-391.done   (sentinel marker)
```

One-shot operator-driven cleanup that closes the 13 broken-pipeline `[doc-audit]` artifact issues (#378-#390) filed by the broken pre-#391 pipeline replay on 2026-05-22T22:28 UTC. Structurally identical to the #362 cutover script with two deliberate omissions:

1. **Static issue list** — no `gh issue list` query; the 13 issue numbers are baked into the module at code-write time.
2. **No cursor reset** — the fixed pipeline at `signals/drift_event.py` processes subsequent drift events via Moment 0 naturally; we do not re-replay.

Behavior:

1. Check marker `~/.config/doc-audit/cleanup-391.done` — if present and `--force` not set, exit 0 (idempotent no-op).
2. For each of the 13 known artifact issues (#378-#390): post a closing comment noting the fix site (`signals/drift_event.py` via `routing/drift_moment0.py`), then close. Per-issue failures are tolerated; the script continues with the remaining issues.
3. Write the sentinel marker file with `mission`, `mission_id`, `run_at_utc`, `closed_issues`.

Identity for the GitHub mutations: `kg-felix-bot` (classic PAT, via `gh` CLI subprocess). `--dry-run` prints intent without mutations. The marker file is permanent — leave it in place as historical record.

### Main-Session Rotation #374 (post-AGENTS.md deploy)

```
Operator (Kent) → ssh office2-claude
  → python3 ~/kg-automation/scripts/openclaw/helpers/rotate_main_session.py
  → /home/claude/.openclaw/agents/main/sessions/   (rename *.jsonl → *.jsonl.reset.<timestamp>)
  → ~/.config/openclaw/main-rotation-<timestamp>.done   (marker)
```

One-shot operator-driven session rotation that forces the OpenClaw **main** agent to re-load `/data/services/openclaw/data/AGENTS.md`. The cached system prompt in any already-running session would otherwise mask the new content; only the next-started session sees changes. This helper renames every active `<uuid>.jsonl` under the main agent's sessions directory to `<uuid>.jsonl.reset.<timestamp>` (the existing OpenClaw rotation convention), guaranteeing the next `openclaw agent --agent main` invocation starts fresh.

Wraps as step 4 of the 5-step cutover in [`openclaw-agent-setup.md`](<../../runbooks/openclaw-agent-setup.md>) §"Cutover sequence for main-agent AGENTS.md changes (post-#374)" (pull → deploy → verify size → rotate → smoke-test). Behavior:

1. List active `*.jsonl` files in `/home/claude/.openclaw/agents/main/sessions/` (skip already-rotated `.reset.*` artifacts).
2. For each active session: rename to `<uuid>.jsonl.reset.<timestamp>` where the timestamp is `YYYY-MM-DDTHH-MM-SS.mmmZ` (hyphens, not colons; matches the existing auto-rotation pattern on office2; millisecond precision).
3. Write the marker at `~/.config/openclaw/main-rotation-<timestamp>.done` recording `mission`, `run_at_utc`, and the list of rotated session basenames.

Naturally idempotent — each call produces a uniquely-timestamped marker and reset suffix, so re-runs simply rotate whatever sessions have started since the last run (typically zero if no traffic). `--dry-run` prints intent without mutations. `--force` is reserved for future use.

### Signal Extraction → GitHub (#490, signal-driven-monitoring-haiku-gate)

```
felix-core-digest.timer (15-min)
  → felix-core-digest.service (oneshot, two chained ExecStart)
      → summarize.py        (existing — agent-log digest)
      → tick.py             (NEW — deterministic signal extraction)
           → /tmp/openclaw/openclaw-*.log                                (read)
           → /data/services/openclaw/felix-core-digest-signals/state/    (per-signal counters, atomic write)
           → scripts/openclaw/agents/main/felix-file-issue.py            (subprocess on threshold cross)
                → gh issue create (kg-felix-bot PAT)
           → /data/services/openclaw/felix-core-digest-signals/last-tick.json   (atomic write)
           → /data/services/openclaw/felix-core-digest-signals/signals-ledger.jsonl   (append)
```

Deterministic OpenClaw-log signal extraction with threshold-driven GitHub issue filing. **No LLM is in this path** (NFR-003). Replaces the prior heartbeat-driven LLM-judged filing path for the named signal classes defined in `scripts/openclaw/observation/signals/config.toml` (initial set: `whatsapp_creds_restore`, `web_watchdog_reconnect`, `agent_unhandled_error` — FR-006). Novel patterns continue to route through the heartbeat gate (next section).

Behavior per tick:
1. `summarize.py` runs first (existing agent-log digest pass). If it exits non-zero, `tick.py` does **not** run (systemd `Type=oneshot` semantics).
2. `tick.py` reads `/tmp/openclaw/openclaw-*.log` covering the rolling window per signal source.
3. Per signal: increment counters, compare against `cycle_threshold` / `rolling_threshold`.
4. On threshold cross AND no matching open issue in the dedup window (FR-002): invoke `felix-file-issue.py` to file a new issue with template-compliant body (FR-003) under the `kg-felix-bot` identity. Log excerpts are credential-redacted per C-005.
5. Persist per-signal counters atomically (FR-004); cold-start logic re-reads recent log windows before trusting state.
6. Write `last-tick.json` (structured health signal — primary input to the heartbeat gate) and append one row per filing to `signals-ledger.jsonl` (audit trail backing NFR-004).

Signal definitions are edit-without-code-changes (FR-005) — operator edits `signals/config.toml`, commits, deploys; next cycle picks them up.

### Heartbeat Gate → Main Agent (#490, signal-driven-monitoring-haiku-gate)

```
felix-heartbeat-gate.timer (30-min, +5-min boot offset)
  → felix-heartbeat-gate.service (oneshot)
      → scripts/openclaw/heartbeat_gate/run.py
           → /data/services/openclaw/felix-core-digest-signals/last-tick.json   (read — primary input)
           → /data/services/openclaw/data/HEARTBEAT.md                          (read — contract file, FR-010)
           → /data/services/openclaw/secrets/anthropic                          (read 0600 — never logged)
           → api.anthropic.com (HTTPS, anthropic-python SDK, claude-haiku-4-5)
           → openclaw system event --mode now   (subprocess, ON ESCALATE_TO_SONNET or fallback only)
           → /data/services/openclaw/felix-heartbeat-gate/last-gate-decision.json   (atomic write)
           → /data/services/openclaw/felix-heartbeat-gate/gate-ledger.jsonl    (append)
```

Haiku-tier routing gate that fronts OpenClaw's heartbeat. The gate decides whether each 30-minute tick needs to wake the expensive Sonnet main-agent path; on the steady state it does not.

Per tick, the gate returns one of:
- **HEARTBEAT_OK** — nothing to do (silent tick, no escalation, no contract task).
- **LOG_AND_SKIP** — observable but doesn't require action this tick.
- **ESCALATE_TO_SONNET** — novel/ambiguous signal OR contract task requires judgment. Gate invokes `openclaw system event --mode now` exactly once (FR-008), wakes the existing Sonnet 4.6 main-agent path with the gate's structured reason as context.

**Failure handling (FR-011)**: API error, timeout, or malformed-response triggers the fallback path — same `openclaw system event --mode now` invocation, with `fallback_invoked: true` recorded in `last-gate-decision.json`. Observation is **never silently dropped**.

**Contract semantics (FR-010)**: the gate honors the existing `HEARTBEAT.md` "empty = skip" rule. Scheduled tasks in the contract file are executed (cheap-tier where feasible, escalated when judgment is required) — behavior indistinguishable from the pre-#490 path from the contract author's perspective.

**Cutover dependency (Tier 2)**: when this gate goes live, OpenClaw's internal heartbeat must be disabled (`openclaw system heartbeat disable`) to avoid double-fire. Rollback re-enables it. See [`docs/runbooks/signal-driven-monitoring-ops.md`](<../../runbooks/signal-driven-monitoring-ops.md>) for the full cutover procedure including the Restic-backup precondition.

The 5-minute `OnBootSec` offset (vs felix-core-digest's `OnBootSec=3min`) avoids lockstep contention on boot.

## Planned Flows (Not Yet Implemented)

| Flow | Features | Description |
|------|----------|-------------|
| WhatsApp Command Channel | F003–F006 | WhatsApp voice/text → OpenClaw → Whisper → Intent Parser → Vikunja |
| Obsidian Inbox Processing | F007–F010 | 01-Inbox → hourly processor → vault routing + Vikunja API |
| Daily Briefing | F014 | Heartbeat → task summary → WhatsApp to Kent |
| Escalation Heartbeat | F015 | Vikunja label state → escalation logic → WhatsApp alert |

## Storage Locations

| Data | Path | Backed Up |
|------|------|-----------|
| Vikunja tasks (SQLite) | `/data/services/vikunja/data/vikunja.db` | Yes |
| Obsidian vault | `/home/kgale/second-brain/notes` | Yes |
| Transcribe data | `/data/services/transcribe` | Yes (excl. models) |
| Backup repo | `/mnt/backups/restic-repo` | N/A (is the backup) |
| Security baselines | `/data/services/security-monitor/baselines` | Yes |
| Security/audit logs | `/data/services/security-monitor/logs` | Yes |
| Backup logs | `/data/services/backup/logs` | Yes |
| Agent JSONL logs | `/home/claude/second-brain/agents/logs/` | No (gitignored, ephemeral) |
| Agent digest files | `/home/claude/second-brain/notes/Agent-Logs/` | Via Obsidian Sync |
| Doc-auditor tick signal | `/data/services/openclaw/felix-doc-auditor-driver/last-tick.json` | No (overwritten each tick) |
| Doc-auditor activity log | `/home/kgale/second-brain/agents/logs/doc-auditor-YYYY-MM-DD.md` | Via Obsidian Sync |
| Anthropic API key (sensitive) | `/data/services/openclaw/secrets/anthropic` | Yes (mode 0600) |
| Escalation JSONL state log (#309) | `/data/services/openclaw/state/escalation/<project-slug>-escalation-history.jsonl` | Yes |
| Escalation pre-backfill snapshot (#309) | `/data/services/openclaw/state/escalation/pre-phase6-snapshot.json` | Yes |
| Enrichment JSONL state log (#310) | `/data/services/openclaw/state/enrichment/enrichment-history.jsonl` | Yes |
| Cutover-310 marker (#310) | `~/.config/openclaw/cutover-310.done` | No (sentinel; ~/.config not in Restic scope) |
| Habits morning-list artifact (#371) | `/data/services/openclaw/state/habits/morning-checkin-<YYYY-MM-DD>.json` | Yes |
| Drift-events ledger (#362) | `/data/services/security-monitor/logs/drift-events-ledger.jsonl` | Yes |
| Audit-events ledger (#400) | `/data/services/openclaw/state/doc_audit/audit-events-ledger.jsonl` | Yes |
| Cutover-362 marker (#362) | `~/.config/doc-audit/cutover-362.done` | No (sentinel; ~/.config not in Restic scope) |
| Cleanup-391 marker (#391) | `~/.config/doc-audit/cleanup-391.done` | No (sentinel; ~/.config not in Restic scope) |
| Main-session rotation marker (#374) | `~/.config/openclaw/main-rotation-<timestamp>.done` | No (audit trail; ~/.config not in Restic scope) |
| Signal-extraction tick signal (#490) | `/data/services/openclaw/felix-core-digest-signals/last-tick.json` | No (overwritten each cycle) |
| Signal-extraction per-signal state (#490) | `/data/services/openclaw/felix-core-digest-signals/state/` | Yes |
| Signal-extraction ledger (#490) | `/data/services/openclaw/felix-core-digest-signals/signals-ledger.jsonl` | Yes |
| Heartbeat-gate decision (#490) | `/data/services/openclaw/felix-heartbeat-gate/last-gate-decision.json` | No (overwritten each tick) |
| Heartbeat-gate ledger (#490) | `/data/services/openclaw/felix-heartbeat-gate/gate-ledger.jsonl` | Yes |
