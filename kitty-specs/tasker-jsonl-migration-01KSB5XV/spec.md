# Spec: Tasker enrichment JSONL state migration (ADR-0002 Phase 7)

**Mission**: `tasker-jsonl-migration-01KSB5XV`
**Mission ID**: `01KSB5XVGW5WRDQFR17JSA52M5`
**Source**: GitHub issue [kentonium3/kg-automation#310](https://github.com/kentonium3/kg-automation/issues/310)
**Risk tier**: Tier 2 — Application / State (Restic snapshot required)
**Generated**: 2026-05-23

## Overview

Final phase of ADR-0002 (Felix JSONL-canonical state model). Port the felix-admin-tasker enrichment subsystem from Vikunja-comments-as-state to JSONL substrate. Mirrors the pattern proven by #308 (habits Phase 3), #309 (escalation), and #371 (habits scripts-first). Pre-existing skill deployment gap (`task-intelligence` skill referenced in tasker's AGENTS.md but not deployed) is in-scope to close.

**Architecture** (locked from #310 spec-readiness probe + this mission's research):
- New helper `scripts/enrichment/record_completion.py` adapted from `scripts/escalation/record_completion.py` — atomic three-write contract (Vikunja comment FIRST + JSONL append SECOND + ack log)
- New helper `scripts/enrichment/reconcile_completions.py` — backfill historic `[Felix] enrichment | state | timestamp` comments into `enrichment-history.jsonl` (window: post-#308 / 2026-04-11 onward)
- Deploy `scripts/openclaw/skills/task-intelligence/SKILL.md` to `/home/claude/.openclaw/skills/task-intelligence/SKILL.md` on office2 (closes a pre-existing gap; the deployed AGENTS.md references the skill but it's missing)
- Cut tasker AGENTS.md from 19,391 → ≤14,000 chars (mirror #371's D10 cut for habits)
- Q10 soft-fail policy: helper failures degrade gracefully (re-propose is annoying but harmless)
- Cutover + 3-day soak (harmonized with #309/#371; verification surface is passive observation + synthetic proposals since tasker is delegation-driven, not cron)

**Operating shape note** (unique to tasker vs habits/escalation):
- Tasker has NO cron — triggered by agent delegation (`felix-admin-capture` → `felix-admin-tasker` for enrich_task) and direct ask
- Soak verification needs synthetic proposal runs in addition to passive observation since natural traffic is sparse (~10 enrichment events/month based on Vikunja inspection)

## User Scenarios & Testing

### Primary user

Felix-admin-tasker (the agent) is the runtime user; Kent (the operator) sees JSONL-substrate analytics post-cutover. The pre-cutover Vikunja-comments-as-state model continues to work during soak (write-through pattern: helpers write both Vikunja comment AND JSONL).

### Acceptance scenarios

#### Scenario A — Enrichment proposal records to JSONL

- **Given**: `felix-admin-tasker` receives an `enrich_task` delegation and produces a `proposed` verdict
- **When**: the agent writes the enrichment state via `scripts/enrichment/record_completion.py --task-id <id> --state proposed --source agent`
- **Then**: a `[Felix] enrichment | proposed | <timestamp>` Vikunja comment is written (existing behavior, preserved)
- **And**: a row is appended to `/data/services/openclaw/state/enrichment/enrichment-history.jsonl` (new substrate)
- **And**: an entry is written to the activity log (existing pattern)

#### Scenario B — Single-offer policy verified via JSONL

- **Given**: a task had a `skipped` enrichment recorded yesterday
- **When**: a new enrichment cycle considers this task
- **Then**: `derive_state` (reading JSONL) returns `skipped` and the policy suppresses re-proposal
- **And**: behavior matches today's Vikunja-comment-based check exactly

#### Scenario C — Backfill historic comments

- **Given**: existing `[Felix] enrichment | state | timestamp` comments on Vikunja tasks from 2026-04-11 onward
- **When**: operator runs `reconcile_completions.py` once during cutover
- **Then**: each historic comment becomes a JSONL row in `enrichment-history.jsonl`
- **And**: disambiguation works: habit comments (`[Felix] YYYY-MM-DD | state`) are NOT parsed; only enrichment comments (`[Felix] enrichment | state | timestamp`) are
- **And**: no Vikunja side-effect runs (`--no-vikunja` flag for backfill)

#### Scenario D — Helper failure: soft-fail (Q10 policy)

- **Given**: a JSONL write fails (filesystem error, permission, etc.) during enrichment recording
- **When**: the helper detects the failure after Vikunja comment has already landed
- **Then**: the helper exits with a logged warning, NOT a hard failure
- **And**: the next enrichment cycle re-proposes (annoying but harmless; Vikunja state is consistent; JSONL is recoverable via reconcile)

#### Scenario E — Cutover + soak

- **Given**: code merged, AGENTS.md cut to ≤14K, SKILL.md deployed
- **When**: operator runs cutover (deploy + reconcile backfill) and observes for 3 days
- **Then**: synthetic enrichment runs (≥3 controlled scenarios) produce both Vikunja comments AND JSONL rows
- **And**: passive observation over the 3-day window shows zero corruption events; reconcile re-run is a no-op (idempotent)
- **And**: 1:1 correspondence between new enrichment comments and JSONL rows

#### Scenario F — Rollback

- **Given**: a defect surfaces post-deploy
- **When**: operator reverts the AGENTS.md edits + redeploys
- **Then**: tasker returns to direct Vikunja-comment writes; no data loss; existing comments remain canonical

### Edge cases

- `record_completion` called with `--idempotent` and a duplicate (task_id, state) hit → no-op, exit 0
- Reconcile encounters a malformed comment → log + skip; don't fail the whole run
- Reconcile encounters a task with both habit and enrichment comments → only enrichment parsed (disambiguation by second-field shape: literal "enrichment" vs `YYYY-MM-DD`)
- Helper called during a Vikunja outage → hard-fail (Vikunja first per atomic contract; no comment, no JSONL)
- AGENTS.md trim accidentally removes a load-bearing rule → reviewer (codex) catches per the lesson from #374 cycle 1
- Tasker agent's `task-intelligence` SKILL.md was missing pre-deploy → mission deploys it; no separate workaround needed

## Functional Requirements

| ID | Description | Status |
|---|---|---|
| FR-001 | `scripts/enrichment/record_completion.py` shall record an enrichment state transition via the atomic three-write contract: Vikunja comment FIRST → JSONL append SECOND → ack log | Planned |
| FR-002 | The helper shall support source values `agent`, `reconcile`, `backfill`, `operator_repair` (mirror escalation pattern) | Planned |
| FR-003 | The helper shall support enrichment states: `proposed`, `confirmed`, `skipped`, `declined` (per deployed AGENTS.md vocabulary) | Planned |
| FR-004 | The helper shall provide `--idempotent` flag — a duplicate (task_id, state) hit is a no-op exit 0 | Planned |
| FR-005 | The helper shall provide `--no-vikunja` flag for backfill/reconcile (write JSONL only, no Vikunja side-effect) | Planned |
| FR-006 | `scripts/enrichment/reconcile_completions.py` shall read existing `[Felix] enrichment` Vikunja comments and append synthetic JSONL rows | Planned |
| FR-007 | Reconcile shall disambiguate enrichment comments from habit comments via the second-field shape (literal `enrichment` vs `YYYY-MM-DD`) | Planned |
| FR-008 | Reconcile's backfill window shall be 2026-04-11 onward (post-#308 pattern formalization) | Planned |
| FR-009 | Reconcile shall be idempotent — re-running on the same comment set produces no duplicates | Planned |
| FR-010 | `scripts/openclaw/skills/task-intelligence/SKILL.md` shall be deployed to `/home/claude/.openclaw/skills/task-intelligence/SKILL.md` on office2 as part of cutover | Planned |
| FR-011 | `/data/services/openclaw/tasker-agent/AGENTS.md` source size shall be ≤14,000 chars after cut | Planned |
| FR-012 | The tasker AGENTS.md shall reference `scripts/enrichment/record_completion.py` as the canonical state-write helper | Planned |
| FR-013 | Q10 soft-fail policy: JSONL write failures after Vikunja side-effect lands shall log + exit 0 (NOT exit 1) | Planned |
| FR-014 | A `derive_state.py` (mirror escalation) shall compute current enrichment state from JSONL | Planned |
| FR-015 | Existing tasker behavior shall remain operational during soak (write-through pattern: helpers write Vikunja comment AND JSONL) | Planned |

## Non-Functional Requirements

| ID | Description | Threshold | Status |
|---|---|---|---|
| NFR-001 | Test coverage on each new helper (record_completion, reconcile_completions, derive_state) | ≥85% | Planned |
| NFR-002 | AGENTS.md size after cut | ≤14,000 chars | Planned |
| NFR-003 | Reconcile backfill completion time for the historic window | ≤60 seconds | Planned |
| NFR-004 | Soak observation: passive observation of zero corruption events + ≥3 synthetic proposal runs exercising all 4 states | 3 days, ≥3 synthetic runs | Planned |
| NFR-005 | Full doc_audit + escalation + habits test suite regression post-merge | 100% pass | Planned |
| NFR-006 | record_completion p95 latency per call (excluding Vikunja API latency) | ≤500 ms | Planned |

## Constraints

| ID | Description | Status |
|---|---|---|
| C-001 | The existing escalation + habits + doc_audit modules shall not be modified | Locked |
| C-002 | The `[Felix] enrichment` Vikunja comment vocabulary shall be preserved (write-through during soak; v2 follow-on can remove the comment-write path after soak completes — analogous to #376 follow-on for #362) | Locked |
| C-003 | Mirror the escalation module's API surface; adapt to enrichment states, do not invent new patterns | Locked |
| C-004 | No new third-party dependencies | Locked |
| C-005 | Tier 2 — Restic snapshot required within 24h pre-deploy | Locked |
| C-006 | Tasker is delegation-driven, NOT cron-driven; integration site is the tasker AGENTS.md instructing the LLM to invoke record_completion.py via the `exec` tool | Locked |
| C-007 | Cutover shall harmonize with #309/#371 — 3-day soak, write-through pattern during soak | Locked |
| C-008 | Architecture docs in-mission per Constitution Directive 5 | Locked |
| C-009 | Prerequisite gate: #374 must be merged (DONE — mission_number=49) | Cleared |

## Success Criteria

1. **Atomic three-write verified**: synthetic enrichment cycle produces exactly one Vikunja comment + one JSONL row + one ack log entry, in that order
2. **Reconcile clean run**: post-backfill, JSONL contains one row per historic enrichment comment (post-2026-04-11 window)
3. **AGENTS.md ≤14K**: deployed file size meets NFR-002
4. **SKILL.md deployed**: the pre-existing gap is closed
5. **3-day soak passes**: ≥3 synthetic runs covering all 4 states; zero corruption events; reconcile re-run is no-op
6. **No regression**: existing escalation + habits + doc_audit tests all pass

## Key Entities

### EnrichmentCompletion (JSONL row)

```python
@dataclass(frozen=True)
class EnrichmentCompletion:
    task_id: int
    state: str                   # "proposed" | "confirmed" | "skipped" | "declined"
    timestamp_utc: str           # ISO 8601 Z-suffixed
    source: str                  # "agent" | "reconcile" | "backfill" | "operator_repair"
    schema_version: int = 1
    note: Optional[str] = None
```

### Tasker AGENTS.md (post-cut)

Target ≤14,000 chars. Removes the deployed file's verbose `enrich_task` step-by-step prose (deferring to the deployed task-intelligence SKILL.md for attribute inference rules); replaces direct Vikunja-comment-write instructions with `record_completion.py` invocation pattern.

## Assumptions

1. The escalation module's `record_completion.py` (1000 lines) is the correct pattern to mirror
2. Vikunja API access via the existing `vikunja-api` skill works for tasker today
3. The deployed AGENTS.md vocabulary (`proposed/confirmed/skipped/declined`) is canonical
4. The 2026-04-11 backfill window captures all historically-meaningful enrichment activity
5. `task-intelligence` SKILL.md content in the repo is current (verified at 13,488 chars during #310 spec-readiness probe)

## Out of Scope

- Removing the Vikunja-comment write path (v2 follow-on after soak)
- New enrichment states or vocabulary changes
- Changes to `felix-admin-capture` delegation pattern
- Changes to escalation, habits, or doc_audit modules

## Dependencies

- #308 (Phase 5 — habits Phase 3 JSONL helpers): pattern source
- #309 (Phase 4/6 — escalation port): direct template
- #371 (habits scripts-first port): AGENTS.md cut shape
- #374 (main verbatim pass-through): **prerequisite — CLEARED**
- ADR-0002 (parent)

## Cross-References

- Issue: kentonium3/kg-automation#310
- Pattern source: `scripts/escalation/record_completion.py`, `scripts/escalation/reconcile_completions.py`, `scripts/escalation/derive_state.py`, `scripts/escalation/schema.py`
- AGENTS.md cut precedent: `scripts/openclaw/agents/felix-admin-habits/AGENTS.md` (post-#371, 13,557 chars)
- Memory: `feedback_design_phase_research.md`
