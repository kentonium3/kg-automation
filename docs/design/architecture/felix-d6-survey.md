---
title: "Felix-wide Directive 6 Survey — Phase 1 of #281"
doc_type: note
status: draft
audience: agents_and_humans
owners: [kgale]
last_validated: 2026-05-21
tags: [281, 112, 278, 276, 1, 2, 3, 4, 343]
---

# Felix-wide Directive 6 Survey

Phase 1 deliverable for [#281](https://github.com/kentonium3/kg-automation/issues/281). Inventories every Felix agent's standing orders and every background pipeline against Constitution Directive 6 (deterministic detection, AI interpretation). Identifies refactoring candidates with operational rationale per the criteria specified in #281.

## Methodology

For each agent (`scripts/openclaw/agents/*/AGENTS.md`):
- Line count + section structure
- Model assignment (from `~/.openclaw/openclaw.json` on office2)
- Run frequency (from cron + OpenClaw cron + systemd timers)
- Current helper count: agent-co-located (`scripts/openclaw/agents/<agent>/*.py`) and domain-co-located (`scripts/<domain>/`)
- Per-operational-block classification: deterministic / stochastic / mixed
- Per-block criticality assessment (consequence-of-getting-it-wrong)
- Per-block hallucination risk (likelihood the LLM gets it wrong without script support)
- Extraction recommendation against #281 thresholds (3-step OR clear-contract+criticality+hallucination)

For background pipelines (`scripts/*/`): already script-driven by definition; assessed only for any agent-side wrappers worth reviewing.

## Aggregate baseline

| Surface | Lines | Sections | Helpers (agent-dir) | Helpers (domain) | Model | Run freq |
|---|---|---|---|---|---|---|
| `main` | 258 | 12 | 0 | n/a | sonnet-4.6 | per-tick + WhatsApp |
| `felix-admin-capture` | 918 | 13 | 0 | **8** in `scripts/inbox/` | haiku-4.5 | 4×/day |
| `felix-admin-habits` | 478 | 14 | 0 | **0** | sonnet-4.6 | 2×/week (daily + weekly) |
| `felix-admin-escalation` | 256 | 9 | 0 | **0** | sonnet-4.6 | 1×/day |
| `felix-admin-tasker` | 497 | 14 | 0 | **0** | sonnet-4.6 | every 4h |
| `felix-doc-auditor` | 485 | 15 | **2** in agent-dir | 0 | sonnet-4.6 | 1×/h |

**Aggregate observations:**

- **Total agent prompt lines: 2,892** across six agents.
- **Helper distribution is bimodal**: `felix-admin-capture` and `felix-doc-auditor` have substantial helper integration; the other three sub-agents have ZERO helpers. This is the visible D6 gap.
- **Model distribution is locked at Sonnet** for every agent except `felix-admin-capture`. The capture agent's Haiku assignment is enabled by its helper density — direct validation of the D6 cost-lever hypothesis.
- **None of the sub-agents currently on Sonnet have any helper scripts** — every multi-step Vikunja API workflow, every state-tracking comment write, every parsing operation lives in-prompt.
- **AGENTS.md size correlates inversely with helper presence**: capture (918L) has 8 domain helpers; doc-auditor (485L) has 2 agent helpers; habits/tasker (478L/497L) have zero. The 250-line ceiling from #281 is achievable but the path is helper extraction, not prompt trimming.

## Per-agent assessment

### main (Felix orchestrator) — 258L, Sonnet

**Section profile:**
- ~225L of upstream OpenClaw conventions (memory, heartbeat, group chat, reactions, tool intro)
- ~35L of project-specific delegation (inbox + habits delegation; ~17L each)

**Operational block analysis:**

| Block | Lines | Type | Steps | Criticality | Hallucination risk | Extract? |
|---|---|---|---|---|---|---|
| Inbox processing delegation | ~18 | Mixed | 4 | Medium | Low | No |
| Habit tracking delegation | ~16 | Mixed | 2 | Medium | Low | No |
| Memory maintenance (heartbeat) | ~30 | Stochastic | n/a | Low | n/a | Keep |
| Group chat behavior | ~50 | Stochastic | n/a | Low | n/a | Keep (upstream) |

**Verdict: LOW PRIORITY for refactor.** The agent is appropriately balanced. Most of the file is upstream OpenClaw conventions we shouldn't touch. Project-specific delegation logic is already pattern-match + invoke + relay — minimal and unobjectionable.

**One possible improvement** (not strictly D6-driven): the delegation logic for inbox + habits is currently ad-hoc. As more sub-agents come online (calendar, escalation responses, etc.), a `scripts/openclaw/agents/main/delegate.py` could template the "detect pattern → invoke sub-agent → relay result" surface. But only if the delegation count grows past ~4 distinct sub-agents AND each delegation acquires payload-shaping logic.

---

### felix-admin-habits — 478L, Sonnet — **TOP PRIORITY CANDIDATE**

**Section profile:**
- Standard prefix (governance, authority, message identity, output discipline, scope): ~67L
- Morning check-in (Steps 1-6): ~120L
- Completion marking (recognize, ambiguity, record, confirm): ~70L
- Comment format spec, idempotency, no-response tracking: ~30L
- Weekly pattern report: ~50L
- Track record query: ~30L
- Habit management (add, pause, remove): ~50L
- Action logging, error handling, privacy: ~60L

**Operational block analysis — Morning check-in (the daily-run path):**

| Step | Lines | Type | Sub-steps | Criticality | Halluc. risk | Extract? |
|---|---|---|---|---|---|---|
| 1. Determine today's day (with TZ) | 13 | Deterministic | 2 | **HIGH** (wrong day = wrong habits delivered) | Low (cmd) / Medium (TZ rule) | **YES** (D6 §4 criticality) |
| 2. Query active habits (Vikunja + filter) | 17 | Deterministic | 4 | **HIGH** (wrong filter = wrong list) | **HIGH** (table parsing) | **YES** (full threshold) |
| 3. Set due_date for Today filter | 42 | Deterministic | 3 + per-habit loop | **HIGH** (off-by-one via TZ bug; see #112) | **HIGH** (TZ offset detection fiddly) | **YES** (full threshold) |
| 4. Exclude already-completed | 12 | Deterministic | 2 | **HIGH** (duplicate check-ins) | Medium | **YES** (criticality) |
| 5. Format check-in message | 21 | Mixed | 1 | Medium | Medium | Marginal |
| 6. Output discipline (no stage directions) | 10 | Stochastic | n/a | n/a | n/a | Keep |

**Operational block analysis — Completion marking:**

| Block | Lines | Type | Sub-steps | Criticality | Halluc. risk | Extract? |
|---|---|---|---|---|---|---|
| Recognize natural language | 14 | Stochastic | n/a | n/a | n/a | Keep |
| Handle ambiguity | 9 | Stochastic | n/a | n/a | n/a | Keep |
| Record completion in Vikunja | 22 | Deterministic | 5 | **HIGH** (wrong state = wrong history; comment format exact) | **HIGH** (format `[Felix] YYYY-MM-DD \| state \| note`) | **YES** (full threshold) |
| Confirm to Kent | 10 | Deterministic | 1 | Low | Low | No |

**Operational block analysis — Weekly report + Track record + Habit management:**

| Block | Lines | Type | Sub-steps | Criticality | Halluc. risk | Extract? |
|---|---|---|---|---|---|---|
| Weekly report: query completion history | ~30 | Deterministic | 3 | Medium | Medium | **YES** (3-step + halluc.) |
| Weekly report: calculate rates | ~10 | Deterministic | 1 | Medium | Medium | Marginal |
| Weekly report: format | ~10 | Mixed | 1 | Low | Low | No |
| Track record query | ~30 | Deterministic | 3 | Medium | Medium | **YES** (3-step) |
| Habit management (add/pause/remove) | ~50 | Deterministic | 3+ each | **HIGH** (mutates habit definitions) | High | **YES** (criticality) |

**Verdict: HIGHEST PRIORITY CANDIDATE.** Estimated extractable surface: ~250L (>50% of operational logic). Multiple HIGH-criticality blocks currently in-prompt subject to LLM hallucination (TZ offset rules, comment format, state-machine transitions). Post-refactor target: ~150-200L total AGENTS.md, Haiku-viable, with `scripts/habits/` containing 4-6 helpers.

**Proposed helper set** (working hypothesis — to be refined in Phase 4 child issue):

- `scripts/habits/compute_today.py` — TZ-aware day + date resolution + Eastern offset
- `scripts/habits/query_active_habits.py` — Vikunja query + frequency-table filter + PAUSED/done exclusion → returns scheduled habits for today
- `scripts/habits/set_due_dates.py` — sets due_date end-of-day-ET on a list of habits, error-resilient per-habit
- `scripts/habits/exclude_completed.py` — fetches comments, filters out today-completed habits
- `scripts/habits/record_completion.py` — atomic completion-state comment write with exact format
- `scripts/habits/weekly_metrics.py` — completion-history calculation

The agent's standing orders shrink to: invoke helpers, get structured results, format the user-facing message, handle NLP-shape parsing of Kent's responses. Genuine LLM work; everything else lives in scripts.

---

### felix-admin-escalation — 256L, Sonnet — **HIGH PRIORITY CANDIDATE**

**Section profile:**
- Standard prefix: ~55L
- Daily escalation run (Steps 1-7): ~85L
- Response handling (Steps 1-4): ~60L
- Action logging, log paths: ~55L

**Operational block analysis — Daily escalation run:**

| Step | Lines | Type | Sub-steps | Criticality | Halluc. risk | Extract? |
|---|---|---|---|---|---|---|
| 1. Load escalation skill | 8 | Deterministic | 1 | n/a | n/a | No |
| 2. Query overdue + at-risk | 22 | Deterministic | 5 conditions × 2 sets | **HIGH** (wrong filter = wrong escalations) | **HIGH** (5 conditions, project ID exclusion) | **YES** (full threshold) |
| 3. Determine escalation level | 10 | Mixed | algorithm from skill | High | Medium | Partially (skill abstracts) |
| 4. Re-check task status | 5 | Deterministic | 1 | Medium | Low | Marginal |
| 5. Format WhatsApp message | 13 | Mixed | per-task loop | Medium | Medium | Marginal |
| 6. Deliver message | 2 | Deterministic | 1 | Low | Low | No |
| 7. Record escalation state | 12 | Deterministic | 2 + per-task loop | **HIGH** (state tracking; if missed, escalation logic breaks) | **HIGH** (comment format `[Felix-Escalation] YYYY-MM-DD \| level-N \| sent`) | **YES** (full threshold) |

**Operational block analysis — Response handling:**

| Block | Lines | Type | Sub-steps | Criticality | Halluc. risk | Extract? |
|---|---|---|---|---|---|---|
| Parse response (NLP) | 1 | Stochastic | n/a | n/a | n/a | Keep |
| Execute action — Done | 4 | Deterministic | 3 | **HIGH** | High | **YES** (criticality) |
| Execute action — Snooze | 3 | Deterministic | 2 | **HIGH** | High | **YES** (criticality) |
| Execute action — Dismiss | 3 | Deterministic | 2 | **HIGH** | High | **YES** (criticality) |
| Execute action — Reschedule | 6 | Deterministic | 5 | **HIGH** | **HIGH** (date parsing + format) | **YES** (full threshold) |
| Execute action — Acknowledge | 3 | Deterministic | 0 (no mutation) | Low | Low | No |
| Execute action — All snooze | 2 | Deterministic | per-task | **HIGH** | High | **YES** (criticality) |

**Verdict: HIGH PRIORITY CANDIDATE.** The five `Execute action` blocks are individually small (each <5L, <3 steps) but collectively constitute the entire state-mutation surface of the agent. Each has HIGH criticality (wrong state on a real task) and HIGH hallucination risk (each has its own comment format). This is the classic case for the Directive 6 §4 criticality clause — small in size, but failure has direct consequences.

**Proposed helper set:**

- `scripts/escalation/detect_escalation_candidates.py` — Step 2's filter logic, returns candidate task list
- `scripts/escalation/record_escalation_state.py` — Step 7's per-task state-comment write
- `scripts/escalation/execute_action.py` — dispatcher for done/snooze/dismiss/reschedule/all-snooze; takes action_type + task_id + params; writes the canonical comment + Vikunja mutation as a single atomic operation

The agent retains: NLP parsing of Kent's response, level-determination judgment, message formatting, error-state handling.

---

### felix-admin-tasker — 497L, Sonnet — **HIGH PRIORITY CANDIDATE**

**Section profile:**
- Standard prefix: ~75L
- Enrichment state tracking (comment format, check-before-propose, single-offer): ~50L
- Action: enrich_task (Steps 1-7): ~135L
- Action: retroactive_enrichment (Steps 1-N): ~150L+
- Action logging, error handling: remainder

**Operational block analysis — enrich_task:**

| Step | Lines | Type | Sub-steps | Criticality | Halluc. risk | Extract? |
|---|---|---|---|---|---|---|
| 1. Attribute reasoning | 30 | Stochastic | n/a | High | High (judgment) | Keep — genuine LLM work |
| 2. Goal check | 10 | Deterministic | 4 | Medium | Medium | Marginal (4 steps; medium crit) |
| 3. Clarification | 10 | Stochastic | n/a | Medium | n/a | Keep |
| 4. Proposal format | 15 | Mixed | 1 | Medium | Low | Marginal |
| 5. Confirmation handling | 10 | Stochastic | n/a | High (state-mutation depends) | High | Keep — but tied to Step 6 |
| 6. Task creation | 15 | Deterministic | **9** | **HIGH** (this is the actual task write) | **HIGH** (9 API calls with specific shapes) | **YES** (canonical case for D6) |
| 7. Error handling | 10 | Mixed | n/a | High | Medium | Partially extractable |

**Operational block analysis — retroactive_enrichment** (preview from line counts; full read not yet performed):
- Step 1: Identify Flat Tasks — deterministic Vikunja query
- Subsequent steps: re-use enrich_task flow with batched input

**Verdict: HIGH PRIORITY CANDIDATE — Step 6 alone is the cleanest extraction case in all of Felix.** Nine sequential Vikunja API calls in fixed order is exactly what helper scripts exist for. Every step is mechanically verifiable; format errors at any step compound. The standing orders should describe WHAT (create a task with these enriched attributes), the helper does HOW (resolve IDs, check duplicates, create task, label, relate, comment).

**Proposed helper set:**

- `scripts/tasker/create_enriched_task.py` — Step 6's 9-step creation flow, atomic, returns task ID + status
- `scripts/tasker/check_enrichment_state.py` — the Check-Before-Propose procedure (parse comments, apply rules)
- `scripts/tasker/write_enrichment_comment.py` — single comment write with format guarantee
- `scripts/tasker/find_flat_tasks.py` — Inbox query for retroactive enrichment batch
- `scripts/tasker/goal_match.py` — Step 2's goal comparison (this is partly stochastic; ?? — may need to leave or split into "fetch goals" deterministic + "match" stochastic)

---

### felix-admin-capture — 918L, **Haiku** — MEDIUM PRIORITY (already substantially refactored)

**Section profile:**
- Standard prefix: ~58L
- Processing workflow (Steps 1-7): ~290L — but multiple steps already helper-driven
- Goal declaration handling: ~65L
- File operation standards: ~65L
- Privacy, edge cases, action logging: ~110L
- Task delegation to felix-admin-tasker: ~85L
- Task bridge fallback: ~50L
- GitHub issue creation: remainder

**Helper integration density:**
- Step 1: `prescan.py` (full)
- Step 5: `handle_marker_cleanup.py` + `append_routing_entry.py`
- Step 6: `handle_parse_failures.py`
- Step 7: minimal
- Steps 2-4: mostly in-prompt (parse → classify → route → execute)

**Operational block analysis — remaining extraction candidates:**

| Block | Lines | Type | Sub-steps | Criticality | Halluc. risk | Extract? |
|---|---|---|---|---|---|---|
| Step 2: Parse each file | 18 | Mixed | 5 (frontmatter parse, validation) | Medium | Medium | Marginal — partly already handled by prescan |
| Step 3: Classify and route | 28 | Stochastic | n/a | Medium | n/a | Keep — genuine LLM classification |
| Step 4: Execute file operations | 31 | Deterministic | 5+ | **HIGH** (file ops on vault) | High | **YES** (full threshold) |
| Task delegation block | ~85 | Deterministic | build payload + invoke + handle response | High | Medium | **YES** (multiple steps, repeat pattern) |
| Task bridge fallback (Vikunja create) | ~50 | Deterministic | 3+ per task | **HIGH** (creates real tasks) | High | **YES** — overlap with tasker's create flow |
| GitHub issue creation | varies | Deterministic | multi-step | Medium | Medium | Marginal |

**Verdict: MEDIUM PRIORITY** — already on Haiku (good), already has 8 helpers in `scripts/inbox/` (good). Remaining opportunities are Step 4 (file ops) and the task-delegation / task-bridge surfaces (which overlap with tasker's extraction work — could share helpers).

**Key observation: capture and tasker have OVERLAPPING task-creation logic.** Capture's "task bridge fallback" creates Vikunja tasks directly when delegation fails; tasker's Step 6 creates them via the enrichment flow. A shared `scripts/vikunja/create_task.py` would consolidate both. This is the **consolidation lever** named in #281's threshold criteria.

---

### felix-doc-auditor — 485L, Sonnet — LOW PRIORITY (most evolved already)

**Section profile:**
- Standard prefix: ~64L
- Trigger / queue management: ~5L
- §2 (drift event processing, added today): ~80L — invokes `handle_drift_events.py`
- §3 (decision processing): ~30L — gh-CLI driven
- §4 (audit selection): ~25L — gh-CLI driven
- §5-7.5 (lock, skill load, audit workflow, per-doc eval): ~120L
- §7.6-7.11 (missing artifact, debt issues, routing helper): ~80L
- §7.12+ (commit, post, release): remainder

**Operational block analysis:**

| Block | Lines | Type | Sub-steps | Criticality | Halluc. risk | Extract? |
|---|---|---|---|---|---|---|
| §2 Drift event processing | 80 | Mixed | helper invocation + AI review of unmapped | High | n/a (helper-handled) | Already extracted (handle_drift_events.py) |
| §3 Decision processing | 30 | Deterministic | gh query + label parsing | Medium | Medium | Marginal — could extract |
| §4 New-audit selection | 25 | Deterministic | gh query + filter + select-oldest | Medium | Medium | Marginal — could extract |
| §5 Lock acquisition | 10 | Deterministic | 1 (gh label add) | High | Low | No (single command) |
| §6 Skill loading | 10 | Deterministic | 1 | n/a | n/a | No |
| §7.5 Per-doc evaluation | 25 | Stochastic | n/a | High (false-positive edits) | High | Keep — genuine LLM judgment |
| §7.6 Missing-artifact detection | 10 | Deterministic | filesystem scan + registry comparison | Medium | Medium | **YES** (3-step + repeats per artifact class) |
| §7.8 File docs-debt issues | 18 | Deterministic | gh issue create with template | Medium | Medium | Marginal — already structured |
| §7.9 Branch on outcome | 12 | Deterministic | branch + invoke routing helper | High | n/a (helper-handled) | Already extracted (handle_audit_routing.py) |
| §7.12+ Commit / post / release | varies | Deterministic | git + gh ops | Medium | Low | Marginal |

**Verdict: LOW PRIORITY.** The agent has already done the right work — `handle_audit_routing.py` (#259) and `handle_drift_events.py` (#278) handle the highest-stakes deterministic surfaces. Remaining candidates are §3 (decision queue) and §7.6 (missing-artifact filesystem scan); both medium-criticality, both currently working, neither urgent.

---

## Background pipeline assessment (already script-driven)

| Pipeline | Lines | Run freq | Notes |
|---|---|---|---|
| `audit.sh` | 269 | daily 03:00 UTC | Recently extended (#277, #278); helper integration via `emit_drift_event`. Healthy. |
| `summarize.py` (observation) | 554 | daily 23:00 UTC | Self-contained Python. No agent-side wrapper. |
| `sync-heartbeat.py` (obsidian) | 252 | every 30 min | Self-contained. |
| `drift_check.py` (enforcement) | 284 | daily 06:00 UTC | Self-contained. |

**Verdict:** All background pipelines are already correctly script-shaped. No agent prompts are wrapping them. No D6 work needed here. (Possible future improvement: standardize the SUMMARY-line stdout convention from `handle_drift_events.py` across these too, but that's Phase 3 best-practices work, not Phase 4 refactoring.)

## OpenClaw native ops + skills surface

Kent's flagged concern: standards adopted "all the way through the system" including OpenClaw native operations and skills.

**Current state inventory:**

| Surface | Location | D6 status |
|---|---|---|
| Skills (community via ClawHub) | `~/.openclaw/skills/<skill>/SKILL.md` | Not in our control — upstream maintained |
| Skills (project-specific) | None currently | **GAP** — we have helpers but no project-specific skills |
| OpenClaw CLI helpers | None | n/a |

**Implication:** The skills system is an **underused capability**. Helpers that get reused across ≥2 agents (e.g., a shared Vikunja task-creation helper between `felix-admin-capture` and `felix-admin-tasker`) would be better expressed as project-specific skills — auto-discoverable, conventionally documented, single source of truth.

**Recommendation for Phase 3:** the helper-script-conventions.md doc should include a "helper vs skill" decision rule:

- **Helper**: used by exactly one agent; agent-co-located OR domain-co-located
- **Skill**: used by ≥2 agents OR has cross-agent reuse potential; goes in a project-specific `~/.openclaw/skills/<name>/` shape

This is the right home for the `scripts/vikunja/create_task.py` consolidation noted under felix-admin-capture above — it's used by both capture (fallback) and tasker (primary), so it should be a skill, not a helper.

## Aggregate findings + hypothesis validation

**Hypothesis validation (from #281 a-priori ranking):**

| Hypothesis | Confidence (a-priori) | Validated by survey? |
|---|---|---|
| felix-admin-habits is highest-contrast (478L, zero helpers, Sonnet, daily) | High | **CONFIRMED** — top priority |
| main's delegation logic is already minimal | Medium | **CONFIRMED** — low priority |
| felix-admin-escalation has extractable detection logic | Medium | **CONFIRMED** — strong candidate (Step 2 query, Step 7 state record, all five action mutations) |
| felix-admin-tasker — unknown current state | Low | **CONFIRMED** — Step 6 is among the cleanest extraction cases in all of Felix |
| felix-core-digest already sufficiently scripted | Low | **CONFIRMED** — no agent prompts to refactor |
| felix-admin-capture has remaining opportunities | Low | **CONFIRMED** — Step 4 + task delegation + task bridge fallback |

All six a-priori predictions held. No surprises in the survey reversed expectations.

**New findings the survey surfaced:**

1. **Capture + Tasker have overlapping task-creation logic.** Consolidation lever per #281 threshold; recommend a shared skill rather than two helpers.
2. **Doc-auditor is the right model for how to do this.** Worth studying its handle_audit_routing.py + handle_drift_events.py pattern as the reference architecture.
3. **Three sub-agents (habits, escalation, tasker) have zero helpers and run on Sonnet.** All three plausibly migrate to Haiku post-refactor — that's three cost-lever wins, not just one.
4. **The criticality clause expands scope as expected.** Many small (1-3 step) blocks qualify because they mutate state with format-sensitive comments (Vikunja state tracking). Without the criticality clause, these would be below threshold; with it, they're inclusion candidates.
5. **AGENTS.md size aligns with spec-kitty's WP sweet spot (200-500).** Five of six agents are within or close to this range; only capture (918) is outside, and that's offset by 8 domain helpers.

## Preliminary Phase 2 prioritization

Hypothesis ranking (Kent finalizes in Phase 2 once #276 cost data lands):

| Rank | Surface | Why first | Effort estimate | Expected impact |
|---|---|---|---|---|
| 1 | `felix-admin-habits` Steps 1-4 (morning check-in) | Daily run, multiple HIGH-criticality blocks, single-agent scope (no consolidation risk), Haiku migration path | ~1 mission (4-6 helpers, AGENTS.md trim, deploy) | Sonnet → Haiku for habits daily run; ~250L of prompt → ~150L; eliminate TZ-offset and comment-format hallucination paths |
| 2 | `felix-admin-tasker` Step 6 (task creation) | Single biggest deterministic block (9 sequential API calls); highest hallucination risk in any agent | ~1 mission (1-2 helpers + AGENTS.md) | Reliability win even before cost win; potential reuse by capture |
| 3 | `felix-admin-escalation` action dispatch | State-mutation surface; HIGH criticality across five action types; format-sensitive | ~1 mission | Reliability win; Haiku migration potential |
| 4 | Vikunja task-creation skill (consolidation) | Cross-agent reuse case; piloting the project-specific skills pattern | ~1 small mission | Shared helper; first project-specific skill; pattern for future consolidation |
| 5 | `felix-admin-capture` Step 4 (file ops) + remaining | Already Haiku; gains are reliability not cost | ~1 mission | Reliability win on vault ops |
| 6 | `felix-admin-habits` Completion marking + Weekly + Track record | Continuation of #1; same agent, same patterns | Continuation mission | Completes habits refactor |
| 7 | `felix-doc-auditor` §3 + §7.6 | Lowest priority; agent is already well-shaped | ~0.5 mission | Marginal reliability gain |

**Recommended sequencing:**

1. Ship Phase 3 (best-practices doc) **before** any Phase 4 children. The first refactor benefits enormously from being able to point to "this is the convention" rather than re-deriving conventions per mission.
2. Pilot Phase 4 with **felix-admin-habits** as the canonical example. It's the highest-impact AND the most clearly-bounded (no cross-agent coupling). The mission produces the first project-specific skill (or doesn't, and we learn).
3. After #1 ships and stabilizes (~1 week of daily runs), proceed to #2 and #3 in parallel if capacity allows.
4. Defer #4 (Vikunja consolidation skill) until at least #2 ships — we'll have empirical signal on what the create_task helper actually needs.

## Phase 1 → Phase 2 handoff

This survey is the input to Phase 2 prioritization. Phase 2 decisions Kent needs to make:

1. **Confirm or reorder** the preliminary ranking above.
2. **Decide on Phase 3 timing** — ship best-practices doc first (recommended) vs. parallel with first Phase 4 mission.
3. **Confirm the helper-vs-skill rule** for cases like the Vikunja task-creation consolidation.
4. **Confirm threshold application** on marginal cases — several "Marginal" verdicts above could go either way; Kent's judgment determines whether to include them in scope.

## What this survey did NOT cover

Deferred to Phase 2 / Phase 3 work:

- **Token cost attribution per agent.** Requires #276 LLM spend inventory data. Once available, the ranking can be re-weighted by actual spend rather than estimated.
- **Behavior-equivalence test plans** per agent. Each Phase 4 mission specifies its own golden-path scenarios; survey doesn't pre-build them.
- **Specific helper interface contracts.** Phase 3 best-practices doc establishes the conventions; each Phase 4 mission designs against them.
- **Migration order for deployment.** Operational concern, decided per Phase 4 mission.

## Cross-references

- [#281](https://github.com/kentonium3/kg-automation/issues/281) — Parent epic
- [Constitution Directive 6](<../../constitution/FELIX-CONSTITUTION.md>) — Principle being applied
- [#253](https://github.com/kentonium3/kg-automation/issues/253), [#259](https://github.com/kentonium3/kg-automation/issues/259), [#277](https://github.com/kentonium3/kg-automation/issues/277), [#278](https://github.com/kentonium3/kg-automation/issues/278) — Validating missions
- [#276](https://github.com/kentonium3/kg-automation/issues/276) — LLM spend inventory (Phase 2 dependency)
- [#141](https://github.com/kentonium3/kg-automation/issues/141) — Closed; explicit residue captured the "extract helper first" pattern for habits

---

*Survey prepared overnight 2026-05-14 → 2026-05-15. Pure analysis; no system changes were made. Awaiting Kent's review and Phase 2 prioritization.*

---

## Update — 2026-05-21 — issue #343

The "LOW PRIORITY" verdict for `felix-doc-auditor` above assessed
further **helper-extraction** opportunities (extracting more of the prose
procedure into Python helpers like `handle_audit_routing.py` and
`handle_drift_events.py`). That verdict remains correct for that
question — the high-value extractions have already happened.

**#343 changed a different dimension**: the orchestration layer
**above** the helpers. The agent's role of interpreting a 38 KB
SKILL.md procedure as runtime LLM prose was its own cost-and-reliability
problem, separate from helper extraction. Mission #343 replaces the
agent-as-orchestrator with a Python driver that calls the existing
helpers + makes narrow LLM judgment calls at three checked-in prompts
(`tier_classification`, `debt_body_generation`, `cross_file_implication`).

Net effect: this survey's "low priority" verdict no longer applies as
an overall judgment of felix-doc-auditor's optimization opportunity.
The helper-extraction surface IS low priority; the orchestrator surface
was high priority and was addressed by #343.

See: `kitty-specs/refactor-doc-auditor-to-scripts-first-driver-01KS2XNX/`
(mission spec, plan, contracts, baselines) and
`docs/runbooks/doc-auditor-driver-ops.md` (post-#343 operator runbook).
