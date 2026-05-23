# Research: Tasker enrichment JSONL state migration

**Mission**: `tasker-jsonl-migration-01KSB5XV`

Phase 0 decisions, all locked from #310 spec-readiness probe + pre-spec probe of office2.

## D1 — Module structure: mirror scripts/escalation/

`scripts/escalation/` has 5102 lines across 6 files:
- `schema.py` (198) — EscalationCompletion dataclass + state enum
- `record_completion.py` (1000) — atomic three-write contract + CLI
- `reconcile_completions.py` (1535) — backfill from comments
- `backfill_jsonl_from_comments.py` (1116) — alternate backfill (we'll fold into reconcile for enrichment)
- `derive_state.py` (686) — compute current state from JSONL
- `hard_fail.py` (567) — failure-mode handling (use if needed)

For enrichment we'll create the same 4 core files (schema, record_completion, reconcile, derive_state). Adapt the state vocabulary; preserve API shape. Estimated ~3500 lines of new code (smaller than escalation since enrichment has 4 states vs escalation's 5+).

## D2 — Enrichment state vocabulary

Locked: `proposed`, `confirmed`, `skipped`, `declined`. Source of truth: deployed tasker AGENTS.md (verified at /data/services/openclaw/tasker-agent/AGENTS.md during #310 spec-readiness; the "Statuses" table enumerates these four explicitly).

No new states or migrations needed.

## D3 — AGENTS.md cut targets

Current: 19,391 chars. Target: ≤14,000 (NFR-002).

Cut targets (mirroring #371 D10 approach for habits):
1. §"Step 1 — Attribute Reasoning" prose (~2,500 chars) — defer to task-intelligence SKILL.md which is now deployed
2. §"Step 2 — Goal Check" detailed REST call examples (~800 chars) — keep high-level instruction, defer details to vikunja-api skill
3. §"Step 6 — Task Creation" verbose 8-step list (~1,800 chars) — compress to 3-4 line summary, defer to skill
4. §"Comment Write Procedure" (~600 chars) — REPLACE entirely with `record_completion.py` invocation pattern
5. Various verbose narratives in §"What Changed (F014)" historical commentary (~500 chars) — trim

Net target reduction: ~6,200 chars + ~500 chars added for new record_completion section. Final: ~13,700 chars (comfortable margin).

Implementer may adjust if their reading suggests different cuts — the goal is the size budget, not the specific cuts.

## D4 — Cutover script scope

`scripts/openclaw/helpers/cutover_tasker.py` — one-shot operator script:

1. Deploy task-intelligence SKILL.md: `cp scripts/openclaw/skills/task-intelligence/SKILL.md /home/claude/.openclaw/skills/task-intelligence/SKILL.md` (idempotent; checks if file exists and matches)
2. Deploy tasker AGENTS.md: `cp scripts/openclaw/agents/felix-admin-tasker/AGENTS.md /data/services/openclaw/tasker-agent/AGENTS.md`
3. Run reconcile_completions to backfill JSONL from existing comments
4. Write marker `~/.config/openclaw/cutover-310.done`

Pattern source: `scripts/doc_audit/helpers/cutover_362.py`. Mirror the `_StructuredArgumentParser` + `--dry-run` + `--force` + marker idempotency pattern.

Tasker session rotation: NOT included in this script. Tasker sessions are likely shorter-lived (delegation-driven) than main agent sessions. If session-rotation becomes a problem, can add `rotate_tasker_session.py` as a thin variant of `rotate_main_session.py` (from #374) in a follow-on.
