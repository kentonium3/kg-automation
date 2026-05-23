---
work_package_id: WP03
title: tasker AGENTS.md cut + cutover_tasker + arch docs + runbook
dependencies:
- WP02
requirement_refs:
- C-008
- FR-010
- FR-011
- FR-012
- NFR-002
- NFR-004
- NFR-005
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this mission were generated on main.
created_at: '2026-05-23T19:50:00+00:00'
subtasks:
- T007
- T008
- T009
- T010
history: []
authoritative_surface: scripts/openclaw/agents/felix-admin-tasker/
execution_mode: code_change
mission_id: 01KSB5XVGW5WRDQFR17JSA52M5
mission_slug: tasker-jsonl-migration-01KSB5XV
owned_files:
- scripts/openclaw/agents/felix-admin-tasker/AGENTS.md
- scripts/openclaw/helpers/cutover_tasker.py
- tests/openclaw/helpers/test_cutover_tasker.py
- docs/design/architecture/data/service-inventory.json
- docs/design/architecture/data/data-flows.json
- docs/design/architecture/service-inventory.md
- docs/design/architecture/data-flows.md
- docs/runbooks/tasker-ops.md
tags: []
---

# WP03 — tasker AGENTS.md cut + cutover script + arch docs + runbook

## Objective

Cut tasker AGENTS.md to ≤14K chars + wire it to invoke record_completion.py. Create the one-shot cutover script. Update arch docs + create operator runbook.

## Context

- **Pattern source**: AGENTS.md cut — `scripts/openclaw/agents/felix-admin-habits/AGENTS.md` (post-#371 cut, 13,557 chars). Cutover script — `scripts/doc_audit/helpers/cutover_362.py`.
- **Plan**: D3 (cut targets), D4 (cutover script scope)
- **Spec**: FR-010, FR-011, FR-012, NFR-002, NFR-004, NFR-005, C-008
- **Tasker AGENTS.md location (repo)**: `scripts/openclaw/agents/felix-admin-tasker/AGENTS.md`
- **Tasker AGENTS.md location (deployed)**: `/data/services/openclaw/tasker-agent/AGENTS.md`

## Subtasks

### T007 — tasker AGENTS.md cut

Steps:
1. Read current `scripts/openclaw/agents/felix-admin-tasker/AGENTS.md` end-to-end (currently 19,391 chars per #310 spec-readiness probe).
2. Apply cut targets per research D3:
   - Remove the entire §"Step 1 — Attribute Reasoning" prose (~2,500 chars) — replace with a 1-line reference to `task-intelligence` SKILL.md
   - Compress §"Step 2 — Goal Check" REST examples (~800 chars) — keep high-level guidance only
   - Compress §"Step 6 — Task Creation" 8-step list (~1,800 chars) — defer details to skills; keep 3-4 line summary
   - REPLACE §"Comment Write Procedure" (~600 chars) with:
     ```
     ### Recording Enrichment State

     Use the canonical helper for all state transitions:

       python3 -m scripts.enrichment.record_completion \
         --task-id <id> --state {proposed,confirmed,skipped,declined} \
         --source agent [--note "<optional context>"]

     The helper writes the [Felix] enrichment comment AND appends to
     enrichment-history.jsonl atomically. Do NOT write enrichment comments
     directly via Vikunja API.
     ```
   - Trim historical §"What Changed (F014)" verbosity (~500 chars)
3. Verify final size: `wc -c scripts/openclaw/agents/felix-admin-tasker/AGENTS.md` ≤14,000.
4. Preserve all standing-orders rules (privacy, message identity, action flows, error handling, etc.). Only remove redundant prose + replace the comment-write procedure.

Validation:
- [ ] `wc -c` ≤14,000
- [ ] grep `record_completion` returns ≥1 match (new section)
- [ ] grep `enrich_task` still returns matches (action flow preserved)
- [ ] grep `proposed`, `confirmed`, `skipped`, `declined` all return matches (state vocab preserved)

### T008 — cutover_tasker.py

Steps:
1. Create `scripts/openclaw/helpers/cutover_tasker.py` based on `scripts/doc_audit/helpers/cutover_362.py` structure.
2. Module constants:
   - `MARKER_PATH = Path.home() / ".config" / "openclaw" / "cutover-310.done"`
   - `MISSION_SLUG = "tasker-jsonl-migration-01KSB5XV"`
   - `MISSION_ID = "01KSB5XVGW5WRDQFR17JSA52M5"`
   - `SKILL_SOURCE = Path(__file__).resolve().parents[2] / "openclaw" / "skills" / "task-intelligence" / "SKILL.md"`
   - `SKILL_TARGET = Path("/home/claude/.openclaw/skills/task-intelligence/SKILL.md")`
   - `AGENTS_SOURCE = Path(__file__).resolve().parents[2] / "openclaw" / "agents" / "felix-admin-tasker" / "AGENTS.md"`
   - `AGENTS_TARGET = Path("/data/services/openclaw/tasker-agent/AGENTS.md")`
3. Steps in `run(*, dry_run=False, force=False)`:
   - Check marker (skip unless --force)
   - Deploy SKILL.md (mkdir -p parent + cp). Verify source exists first.
   - Deploy AGENTS.md (cp)
   - Run `python3 -m scripts.enrichment.reconcile_completions` to backfill
   - Write marker
4. `_StructuredArgumentParser` for exit code 3. Exit 0 success/no-op / 1 filesystem / 2 reconcile failed / 3 invalid args.

Validation:
- [ ] CLI `--help` exits 0
- [ ] Module importable

### T009 — Tests for cutover_tasker

Steps:
1. Create `tests/openclaw/helpers/test_cutover_tasker.py` mirroring `tests/doc_audit/helpers/test_cutover_362.py`.
2. Mock subprocess (for reconcile invocation) + filesystem ops (cp, mkdir). Use tmp_path for marker.
3. Test cases:
   - Happy path: SKILL.md + AGENTS.md deployed + reconcile invoked + marker written
   - Dry-run: no mutations
   - Idempotent no-op: marker pre-exists → CutoverResult(already_done=True)
   - `--force` overrides marker
   - SKILL.md source missing → exit 1
   - Reconcile subprocess failure → exit 2
   - Marker write failure → exit 1
4. Coverage target ≥85%.

Validation:
- [ ] `pytest tests/openclaw/helpers/test_cutover_tasker.py -v --cov=openclaw.helpers.cutover_tasker` ≥85%

### T010 — Arch docs + runbook

Steps:
1. `docs/design/architecture/data/service-inventory.json`:
   - Update `felix-admin-tasker` entry: note that enrichment state migration completed; `updated_by: "#310"`
   - Add new entries: `scripts/enrichment/record_completion.py`, `scripts/enrichment/reconcile_completions.py`, `scripts/enrichment/derive_state.py`, `scripts/openclaw/helpers/cutover_tasker.py` — all with `introduced_by: "#310"`
   - **Fix existing drift discovered during #310 spec-readiness**: the entry currently lists a `task-detection` cron every 4h UTC that does NOT exist in `openclaw cron list`. Remove or annotate (decide based on whether tasker should have a cron — likely remove since tasker is delegation-driven).
2. `docs/design/architecture/data/data-flows.json`:
   - Add: enrichment-record-completion-jsonl flow (record_completion → enrichment-history.jsonl)
   - Add: enrichment-record-completion-vikunja flow (record_completion → Vikunja comments API)
   - Add: enrichment-reconcile-backfill flow (reconcile → Vikunja read + JSONL write)
   - All with `introduced_by: "#310"`
3. Update markdown views (service-inventory.md, data-flows.md) to match JSON.
4. Create `docs/runbooks/tasker-ops.md` (or update if exists) with:
   - Mission overview + cutover sequence (deploy SKILL + deploy AGENTS + run cutover_tasker + 3-day soak)
   - Soak verification procedure: synthetic enrichment runs (3 controlled scenarios covering all 4 states) + passive observation
   - Rollback procedure
   - Cross-references to #310, #309, #371
5. Validate JSON parses.

Validation:
- [ ] `python3 -c "import json; json.load(open('docs/design/architecture/data/service-inventory.json'))"` succeeds
- [ ] `python3 -c "import json; json.load(open('docs/design/architecture/data/data-flows.json'))"` succeeds
- [ ] `docs/runbooks/tasker-ops.md` exists + walks operator end-to-end through cutover + soak + rollback

## Definition of Done

- [ ] All 4 subtasks complete
- [ ] `wc -c` AGENTS.md ≤14,000; coverage ≥85% cutover_tasker
- [ ] JSON files parse; markdown views match
- [ ] Runbook readable + complete

## Implementation Command

```bash
spec-kitty agent action implement WP03 --mission tasker-jsonl-migration-01KSB5XV --agent claude:opus:python-implementer:implementer
```
