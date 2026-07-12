# Research: Deterministic escalation + weekly-report crons

Phase 0. Load-bearing facts were probed **live on office2** (OpenClaw 2026.6.11) and against the repo, per the design-phase research discipline. Each finding is a decision the plan/tasks depend on.

## R1 — `openclaw message send` interface (weekly delivery)

**Decision**: The weekly driver delivers with
`openclaw message send --channel whatsapp --target +16179300916 --message "<body>" --json`.
**Evidence** (`openclaw message send --help`, office2): flags `--channel whatsapp`, `-t/--target <E.164>`, `-m/--message <text>` (required unless `--media`), `--dry-run` (print payload, skip send), `--json` (structured result). WhatsApp target is E.164.
**Rationale**: A deterministic CLI send removes the LLM agent from the path entirely. `--json` gives a machine-checkable delivery result for FR-006 truthful confirmation; `--dry-run` supports the deploy self-test.
**RESOLVED (post-plan review C1)**: a real send returns exit 0 with a non-empty `payload.result.messageId` (+ `runId`) and `dryRun:false`. **Confirmation predicate**: exit 0 AND non-empty `messageId` AND `dryRun==false`; any other shape ⇒ not delivered. A `--dry-run --json` send omits `result` (has only `dryRun:true`). See `contracts/post-plan-review-resolutions.md` C1.
**Alternatives rejected**: keeping it an openclaw agent cron (the current failing design); ntfy/alert-bus (that is for alerts, not a scheduled user-facing report).

## R2 — `VikunjaClient` + the all-tasks endpoint (escalation enumeration)

**Decision**: `enumerate_candidates.py` uses `scripts.common.vikunja_client.VikunjaClient` and paginates `client.get("/tasks/all", params={"page": n, "per_page": 50})` until an empty batch, then filters client-side.
**Evidence**: `VikunjaClient` (scripts/common/vikunja_client.py:132) is a stateless stdlib HTTP wrapper — `get(path, *, params, timeout)`, **no** pagination/caching helper (callers paginate). Paths need a **leading slash**; base_url already ends `/api/v1`. `/tasks/all` is the cross-project all-tasks endpoint (the agent's improvised `/projects/-4/tasks` was a wrong guess). Vikunja caps `per_page` at 50 (paginate until empty; do **not** stop on `len < 100`).
**Rationale**: Deterministic fetch + client-side filter matches the repo's Vikunja pattern (server-side `?filter=` is rejected — G6/G7 gotchas) and the habits helpers' use of the same client.
**Alternatives rejected**: server-side `?filter=` (rejected by Vikunja); per-project fetch loop (needs a project list; `/tasks/all` is simpler).

## R3 — Escalation §1 qualification criteria (the filter to mechanize)

**Decision**: The client-side filter reproduces SKILL.md §1 exactly: `done == false`; `priority >= 2`; `project_id` NOT in the scope-excluded set; (`due_date < today` **OR** (`due_date == today` AND `priority >= 3`)); drop the null-due sentinel `0001-01-01T00:00:00Z`. Snooze/dismiss lifecycle stays with `derive_state` downstream (unchanged).
**Evidence**: `scripts/openclaw/skills/escalation/SKILL.md` §1. Excluded projects today: 11 (Goals), 13 (Habits) — sourced from IC-01 scope config, not hardcoded.
**Rationale**: C-002 — criteria unchanged, only mechanized. The helper returns candidates; the agent still calls `derive_state` per candidate for level decisions.

## R4 — Habit project id is hardcoded (config externalization)

**Decision**: Move `HABITS_PROJECT_ID = 13` out of `query_active_habits_weekly.py` (line 71) into `scripts/common/vikunja_scope.py`; the helper reads it via an accessor.
**Evidence**: `query_active_habits_weekly.py:71` `HABITS_PROJECT_ID = 13`, used at `/projects/{HABITS_PROJECT_ID}/tasks` (lines 290, 389, 912).
**Rationale**: FR-008 — the single point the #714 reorg updates. Shape the accessor so a future label form is a config change (`{kind: "label", value: "t:habit"}`) not a code change (NFR-004).

## R5 — Deterministic-driver pattern (systemd timer + freshness pointer)

**Decision**: Mirror the felix-canary deploy (`deploys/applied/0017-felix-canary-registry.yaml`): install `felix-habits-weekly.{service,timer}` + an OnFailure ntfy shim into `~/.config/systemd/user/`, `daemon-reload`, then a **verify-before-enable** gate (assert ExecStart, run the real unit once, assert a fresh `last-tick.json`), then `enable --now`. The driver writes `last-tick.json` (`completed_at_utc`, `exit_code`) so the #722 canary monitors it as a `tick-signal-file` freshness service.
**Evidence**: 0017 manifest notes (verify-before-enable gate, #711/#703 "don't trust dry-run" lesson); the canary `tick-signal-file` freshness probe (`scripts/canary/probes.py`, #720/#722).
**Rationale**: FR-009 observability + safe deploy. Weekly cadence ⇒ `max_age_seconds ≈ 8 days` (7-day period + 1-day slack).

## R6 — Rebaseline mechanics (audited surfaces)

**Decision**: The deploy manifest declares `expected_baselines` for the **openclaw-cron-removal** drift only. Systemd-unit + AGENTS.md changes have repo-file signals and auto-rebaseline.
**Evidence**: 0017 manifest — "systemd units under scripts/office2/ are a hashed audited surface, so felix-deployer auto-rebaselines … no expected_baselines needed"; `docs/design/architecture/data/audited-surfaces.json`; CLAUDE.md rebaseline "no repo-file signal ⇒ declare via expected_baselines". `openclaw cron rm habits-weekly-report` drifts the openclaw-config baseline with no tracked-file change.
**Rationale**: C-003/C-004.

## R7 — Escalation stays an agent; morning check-in untouched

**Decision**: `escalation-daily` remains an openclaw-cron agent (still #722-monitored via `openclaw-cron-state`); only Step 2 becomes a helper call. `habits-morning-checkin` is unchanged. No service-inventory change for escalation.
**Rationale**: C-001. The escalation run needs LLM judgment (level, compose); enumeration is the only deterministic slice. Keeps blast radius minimal (DIRECTIVE_024).
