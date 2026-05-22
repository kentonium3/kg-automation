# Specification: Habits check-in + reply scripts-first port

**Mission ID**: 01KS86ZQE8GSZ77ZSGSSQMN08K
**Mission slug**: habits-checkin-reply-scripts-first-01KS86ZQ
**Mission type**: software-dev
**Source**: GitHub issue [#371](https://github.com/kentonium3/kg-automation/issues/371) (P1-bug)
**Target branch**: main

---

## Overview

Port the `felix-admin-habits` morning check-in + reply-parsing flow to a scripts-first pattern, mirroring mission #309's escalation port. The bug: the morning cron tick (sends a numbered list) and the reply-handling tick (interprets Kent's number-referencing reply) are two separate openclaw sessions; the reply session has no access to the morning session's list and regenerates it independently — the orderings diverge, and Kent's reply gets applied to the wrong habits. Aggravated by AGENTS.md exceeding the openclaw effective source budget (24K chars vs. ~14K usable), silently truncating standing orders.

This mission introduces two helper scripts that persist + read the canonical ordered list, narrows the LLM judgment surface to ambiguous reply cases only, and cuts AGENTS.md prose so the agent prompt stays within the openclaw budget.

---

## User Scenarios & Testing

### Primary scenario — Morning check-in arrives, Kent replies by number

7:05 AM ET cron fires. `morning_checkin_list.py` is invoked. It:
1. Reads today's active habit tasks from Vikunja (via existing `query_active_habits_v2.py` or equivalent).
2. Excludes habits already addressed today (via existing `exclude_completed_v2.py`).
3. Produces a deterministic ordered list (positions 1..N) of remaining habits.
4. Persists the list to `/data/services/openclaw/state/habits/morning-checkin-<YYYY-MM-DD>.json` with the schema `{position, vikunja_task_id, title}` per record.
5. Renders the formatted WhatsApp check-in message.

The agent receives the formatted message from the helper and relays it verbatim to WhatsApp. No LLM rendering of the list.

Later, Kent replies `"Skipped 3,7,8 done"`. The reply-handling cron tick fires. The agent:
1. Reads Kent's reply text.
2. Invokes `parse_morning_reply.py <reply-text> --date <YYYY-MM-DD>`.
3. The parser reads the persisted morning list and produces canonical `[(task_id, state)]` tuples deterministically: positions 3, 7, 8 → `skipped`; positions 1, 2, 4, 5, 6 → `complete`.
4. The agent iterates the tuples and calls existing `record_completion.py` once per habit.

Expected: every record_completion call lines up with the habit Kent actually saw at that position.

### Secondary scenario — Kent replies by habit name (deterministic match)

Kent replies `"meditation done, skipped morning shoulder PT"`. `parse_morning_reply.py`:
1. Loads the morning list.
2. Tokenizes the reply.
3. For each token group: exact title match against the morning list's titles first; then case-insensitive simple-substring match (e.g., `"meditation"` matches `"Meditate"` if it's a unique prefix/substring of exactly one title).
4. On a unique match: emits `(task_id, state)`.
5. On ambiguity (substring matches multiple titles): emits a `judgment_required` record with the ambiguous token + candidate task_ids.

The agent reads the parser output. For deterministic tuples it routes directly to `record_completion.py`. For `judgment_required` items, it invokes a narrow LLM judgment helper (analogous to `scripts/doc_audit/judgment/*` in #343) that takes the ambiguous token + candidate titles + (optionally) the full reply text for context, and returns either a chosen candidate or `"clarify"`. The agent asks Kent ONE clarifying question per cluster of ambiguities — never guesses silently.

### Tertiary scenario — Reply received without a persisted morning list

If the reply parser is invoked but no morning-list artifact exists for the relevant date (cron didn't fire today, or the file was deleted), the parser exits with a structured error. The agent files a P2-bug via `felix-file-issue.py` (per the existing hard-fail pattern from #309 WP04) and replies to Kent with a clarification message asking him to re-state his habit progress in natural language.

### Edge cases

- **Reply uses both numbers and names**: `"1 done, skipped meditation"` — parser handles each token independently against the same persisted list.
- **Reply uses ranges**: `"1-4 done, skipped 5"` — parser expands ranges into positions before mapping. Out of scope optionally; see C-006.
- **Reply uses "all done"**: parser detects the special token and emits a `(task_id, complete)` tuple for every habit in the morning list.
- **Multiple replies same day**: the parser is idempotent in routing — if a habit is already recorded via `record_completion` for today, the existing `idempotent_record_event` semantics dedup.
- **Vikunja state changes between morning send and reply**: the parser uses the persisted list, NOT live Vikunja state. The morning list is the authoritative ordering. Habits added/removed in Vikunja between 7 AM and the reply do NOT affect parsing.
- **Empty reply or unparseable text**: parser exits with a structured error; agent asks Kent to clarify.

---

## Functional Requirements

| ID | Status | Requirement |
|---|---|---|
| FR-001 | required | `scripts/habits/morning_checkin_list.py` MUST emit today's ordered habit list as both (a) the formatted WhatsApp check-in message text on stdout AND (b) a persisted JSON file at `/data/services/openclaw/state/habits/morning-checkin-<YYYY-MM-DD>.json`. The JSON schema MUST be `{schema_version: int, date: str, generated_at: str (ISO-8601 UTC), habits: [{position: int, vikunja_task_id: int, title: str}]}`. |
| FR-002 | required | The ordering used in the JSON file's `position` field and in the formatted message MUST be identical (same habit at position N in both). |
| FR-003 | required | `scripts/habits/parse_morning_reply.py` MUST accept a reply text + a date, load the persisted morning list for that date, and emit canonical tuples on stdout as JSON: `{tuples: [{task_id, state}], judgment_required: [{token, candidate_task_ids, candidate_titles}], errors: [{type, detail}]}`. State values are constrained to `{complete, incomplete, skipped}` per Phase 2 enum. |
| FR-004 | required | The reply parser MUST handle: (a) number references (single digits, comma-separated lists), (b) exact title matches (case-insensitive), (c) simple substring matches that uniquely identify one habit. Ambiguous substring matches (matches multiple titles) MUST emit a `judgment_required` record, NOT silently pick one. |
| FR-005 | required | The reply parser MUST support the special tokens `"all done"`, `"done with everything"`, `"everything done"`, and equivalent close paraphrases — emitting `complete` tuples for every position in the morning list. |
| FR-006 | required | When the parser emits `judgment_required` records, the agent MUST invoke a narrow LLM judgment helper (`scripts/habits/judgment/disambiguate_reply.py` or equivalent) ONLY for those cases. The judgment helper returns either a chosen candidate task_id or `"clarify"`. If `"clarify"`, the agent MUST ask Kent ONE clarifying question per ambiguity cluster — never guess silently. |
| FR-007 | required | `morning_checkin_list.py` MUST be the SOLE source of the ordered list. The agent's standing orders (AGENTS.md) MUST NOT contain any prose that instructs the agent to derive, generate, or re-order the habit list. |
| FR-008 | required | The reply-handling path MUST NOT re-query Vikunja for the habit list. It MUST read positions exclusively from the persisted morning-list JSON for the relevant date. |
| FR-009 | required | If the reply-handler is invoked and no persisted morning-list exists for the date, the parser MUST exit with a structured error (exit code 4 or equivalent) AND the agent MUST file a P2-bug via `felix-file-issue.py` describing the missing artifact. The agent MUST NOT silently fall back to live Vikunja state. |
| FR-010 | required | `record_completion.py` (from Phase 3) MUST NOT be modified. The new helpers MUST consume its existing CLI/API surface as-is. |
| FR-011 | required | The deployed `/data/services/openclaw/habits-agent/AGENTS.md` MUST be reduced to ≤14,000 source characters (the openclaw effective budget per memory `reference_openclaw_gotchas.md`). Specifically: remove the level-determination algorithm, the fuzzy-match-by-title prose, the ambiguity-resolution rules, and the "match against the numbered list from the most recent check-in message in this session" instruction. Those responsibilities move to the helper scripts. |

---

## Non-Functional Requirements

| ID | Status | Requirement |
|---|---|---|
| NFR-001 | required | The reply-parsing path MUST be byte-deterministic given a fixed reply text + a fixed persisted morning-list JSON. Running the parser twice on the same inputs MUST produce identical output. |
| NFR-002 | required | Code coverage on the new helpers (`morning_checkin_list.py`, `parse_morning_reply.py`, `disambiguate_reply.py` or equivalent) MUST be ≥85% line + branch. |
| NFR-003 | required | The morning-list emission helper MUST complete in ≤10 seconds (well under the cron's tick envelope). The reply parser MUST complete in ≤5 seconds per typical reply (< 20 tokens). |
| NFR-004 | required | The deployed `AGENTS.md` post-fix MUST NOT emit an openclaw truncation warning on cron tick. Verify by running one manual tick post-deploy and checking journalctl for the `"truncating in injected context"` message — it MUST be absent. |
| NFR-005 | required | The persisted morning-list JSON files MUST be bounded: one file per date, max ~1 KB per file at typical N=8-12 habits. No rotation needed (file count grows ~365/year; ops doc explains the cleanup convention). |

---

## Constraints

| ID | Status | Constraint |
|---|---|---|
| C-001 | required | This mission MUST NOT modify `scripts/habits/record_completion.py` or any other Phase 3 / Phase 5 habits helper that's currently in production. The contract for `record_completion` is fixed. |
| C-002 | required | This mission MUST NOT modify any escalation code (`scripts/escalation/*`) — those landed in mission #309 and are in soak. |
| C-003 | required | This mission MUST NOT modify the Phase 2 `scripts/common/state_log*` library (consistent with mission #309 C-003). |
| C-004 | required | The habits cron (`habits-morning-checkin`, UUID `3082343c-bc7f-47ee-916b-ee070b1e50dc`) is currently DISABLED on office2 as a safety measure. Re-enabling is a post-merge cutover step, NOT part of mission code changes. |
| C-005 | required | The OpenClaw `felix-admin-habits` agent stays as a thin orchestrator (mirror mission #309's pattern). This mission does NOT retire the agent. Full agent retirement is the post-#309 follow-on epic. |
| C-006 | required | Reply-text grammar (range syntax like `"1-4 done"`, complex conditionals) is OUT of scope. Initial parser supports comma-separated numbers, exact titles, simple substrings, and the `"all done"` family. Range expansion can be added in a follow-on if needed. |
| C-007 | required | Architecture documentation updates (service-inventory.json, data-flows.json, habits-ops.md) are part of THIS mission, not a separate follow-on. `updated_by: #371` on touched entries; markdown views must match JSON sources. |
| C-008 | required | Constitutional autonomy level: Observed (Level 2). The agent writes habit records autonomously per existing policy; clarification questions go to Kent. No new autonomy elevation. |
| C-009 | required | Privacy boundary: the helpers MUST NOT read second-brain notes or any path under `~/second-brain/notes/04-Growth/_private/`. |

---

## Success Criteria

| ID | Outcome |
|---|---|
| SC-001 | Tomorrow morning's 7:05 AM ET (2026-05-23) cron — re-enabled post-merge — produces a check-in message whose ordering is byte-identical to the persisted morning-list JSON for that date. |
| SC-002 | A reply test scenario `"Skipped 3,7,8 done"` against the 8-habit list from 2026-05-22 (preserved as test fixture) produces canonical tuples that map exactly to positions 3, 7, 8 as `skipped` and positions 1, 2, 4, 5, 6 as `complete` — the same intent Kent expressed. |
| SC-003 | A reply test scenario with an ambiguous token (e.g., `"PT done"` with both `"Morning shoulder PT"` and `"Evening shoulder PT"` in the list) emits a `judgment_required` record; the disambiguation helper returns either a chosen task_id or `"clarify"`; the agent asks Kent ONE clarifying question. |
| SC-004 | The deployed `AGENTS.md` is ≤14,000 source characters. One manual tick post-deploy produces NO openclaw truncation warning in journalctl. |
| SC-005 | A reply received without a persisted morning-list (synthetic test scenario) results in: exit code 4 from the parser; a P2-bug filed via `felix-file-issue.py`; no silent fallback to live Vikunja state; no habit records corrupted. |
| SC-006 | All three end-to-end test scenarios pass: (a) reply by name (`"meditation done, skipped morning shoulder PT"`); (b) reply by number (`"skipped 3,7,8 done"`); (c) mixed (`"1 done, skipped 2 and 3, meditation done"`). |
| SC-007 | Coverage ≥85% on new helpers; no regression in existing `tests/habits/` (Phase 3 + Phase 5 tests still pass). |
| SC-008 | Cron re-enabled post-cutover; one full morning cycle verified manually (Kent triggers tick, checks the message, sends a controlled reply, verifies the recorded JSONL matches intent). |

---

## Key Entities

- **Persisted morning-list artifact** — `/data/services/openclaw/state/habits/morning-checkin-<YYYY-MM-DD>.json`. Schema per FR-001. One file per day.
- **Reply parser output** — JSON `{tuples, judgment_required, errors}`. Tuples are deterministic; judgment_required is the narrow LLM judgment surface; errors trigger hard-fail.
- **Ambiguity cluster** — a group of related judgment_required records for which the agent asks a single clarifying question (e.g., all `"PT"` references batched into one disambiguation request).
- **AGENTS.md (post-fix)** — thin orchestrator: receive tick → invoke `morning_checkin_list.py` → relay output → wait for reply → invoke `parse_morning_reply.py` → for each tuple call `record_completion.py` → for judgment_required, invoke disambiguator → ask clarifying questions if needed.

---

## Assumptions

The plan phase MUST validate these before implementation begins:

1. The existing `scripts/habits/query_active_habits_v2.py` and `exclude_completed_v2.py` produce a usable habit list that `morning_checkin_list.py` can consume. Plan confirms via direct read of those scripts' output schemas.
2. The Phase 2 `scripts/common/state_log/` library's `append()` API works for the morning-list artifact (which is NOT a habit-history record — it's a separate per-date state file). If state_log's API doesn't fit (e.g., it's hardcoded to per-domain history JSONL), the helper writes the artifact directly using `pathlib` + atomic write (tmp + fsync + rename), per habits Phase 4 snapshot precedent.
3. The `felix-file-issue.py` helper at `scripts/openclaw/agents/main/felix-file-issue.py` accepts the body-via-stdin or body-via-tempfile pattern that mission #309's `hard_fail.py` (WP04) discovered. Plan confirms by reading the current felix-file-issue.py.
4. The deployed AGENTS.md path on office2 is `/data/services/openclaw/habits-agent/AGENTS.md` (verified via `find` per memory `reference_office2_agent_deploy_paths.md`).
5. The cron `habits-morning-checkin` (UUID `3082343c-bc7f-47ee-916b-ee070b1e50dc`) is currently disabled (verified by orchestrator during this mission setup).
6. The openclaw cron's tick mechanism passes the agent the cron metadata (date, UUID) such that the agent can construct the right date string for the persisted-list filename. Plan confirms by inspecting how Step 1 ("Compute today's context") gets the date today.

---

## Out of Scope

The following are explicitly NOT part of this mission:

1. Retiring the OpenClaw `felix-admin-habits` agent. Agent stays as a thin orchestrator; full retirement is the post-#309 follow-on epic.
2. Repairing today's (2026-05-22) miscoded habit records. Kent edits JSONL manually if needed.
3. Range-syntax reply parsing (`"1-4 done"`). Comma-separated lists are sufficient for typical replies.
4. Modifying any Phase 3/5 habits helpers (`record_completion.py`, `reconcile_completions.py`, `backfill_jsonl_from_comments.py`, query/exclude variants).
5. Modifying any escalation code (mission #309 territory).
6. Modifying Phase 2's `scripts/common/state_log/` library.
7. New telemetry beyond the existing JSONL append + journalctl signal.
8. Habits weekly report (different cron, different code path; unaffected by this bug).

---

## Cross-References

- **GitHub issue**: [#371](https://github.com/kentonium3/kg-automation/issues/371)
- **Pattern source**: [#309](https://github.com/kentonium3/kg-automation/issues/309) — escalation port to scripts-first; same architecture replicated here
- **Pattern source**: [#343](https://github.com/kentonium3/kg-automation/issues/343) — felix-doc-auditor rework; the narrow LLM judgment pattern this mission uses for ambiguity
- **Foundation**: [#306](https://github.com/kentonium3/kg-automation/issues/306) (habits Phase 3) and [#308](https://github.com/kentonium3/kg-automation/issues/308) (habits Phase 5) — JSONL state model already in place
- **ADR**: `docs/design/architecture/adr/0002-felix-vikunja-task-model.md`
- **Memory**: `reference_openclaw_gotchas.md` — AGENTS.md effective char budget
- **Memory**: `feedback_scripts_vs_llm.md` — the architectural principle
- **Memory**: `reference_office2_agent_deploy_paths.md` — felix-admin-habits → habits-agent deploy mapping
- **Memory**: `reference_codex_speckitty_profile.md` — codex `-p spec-kitty-review` profile for review dispatch

---

## Discovery Record

The following decisions were resolved during specify-phase discovery on 2026-05-22:

| # | Question | Decision | Encoded in |
|---|---|---|---|
| Q1 | Where does fuzzy-match-by-name live for replies? | **Helper script with strict matching; narrow LLM judgment only for ambiguous cases** (mirror #343 pattern). | FR-003, FR-004, FR-006, SC-003 |
| Q2 | What's the agent's role post-fix? | **Thin orchestrator** (mirror #309 pattern). AGENTS.md shrinks; helpers do the work. | FR-007, FR-011, C-005, SC-004 |
| Q3 | Today's miscoded records — fix as part of this mission? | **Out of scope.** Kent edits JSONL manually if needed. | Out of Scope §2 |
