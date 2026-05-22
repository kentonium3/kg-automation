# Research: Habits check-in + reply scripts-first port

**Mission**: `habits-checkin-reply-scripts-first-01KS86ZQ`
**Date**: 2026-05-22

Engineering decisions locked before implementation. Format: **Decision → Rationale → Alternatives considered**.

---

## D1. State artifact location + naming

**Decision**: `/data/services/openclaw/state/habits/morning-checkin-<YYYY-MM-DD>.json`. Date is in `America/New_York` (Kent's local TZ).

**Rationale**: One artifact per Kent-day. Local TZ matches Kent's experience ("today's check-in" is HIS today, not UTC's). Directory parallels mission #309's `/data/services/openclaw/state/escalation/`. No JSONL append semantics needed; this is a per-date snapshot, not a state-log.

**Alternatives considered**:
- UTC dates in filename (rejected — UTC midnight isn't a meaningful day boundary for Kent).
- Single rolling file with embedded date keys (rejected — atomic writes are cleaner per-file; old files self-archive by date naming).
- Path under `/data/services/openclaw/habits-agent/state/` (rejected — co-locates with agent workspace, fragile if agent dir moves; parallel to escalation pattern is better).

---

## D2. Atomic write of the artifact

**Decision**: Write to `<path>.tmp`, fsync, then `os.replace(<path>.tmp, <path>)`. No state_log library involvement.

**Rationale**: The artifact is a per-date SNAPSHOT (single JSON object), not an append-only event log. The Phase 2 state_log library is for JSONL with append semantics — wrong shape. The atomic tmp+fsync+rename pattern matches habits Phase 4 snapshot precedent.

**Alternatives considered**:
- Use state_log.append (rejected — semantics mismatch; would force one-record-per-line shape).
- Direct write without tmp+rename (rejected — power-loss / crash during write would leave a corrupt file the next morning).

---

## D3. Parser deterministic-match rules

**Decision**: Three-tier match order, evaluated in sequence:

1. **Number references**: digit tokens (1-N), comma-separated lists (`"1, 3, 5"`), no ranges. Position-based, deterministic.
2. **Exact title match**: case-insensitive whole-string match against `title` field in the morning list.
3. **Simple substring match**: case-insensitive substring; ONLY emits a match if the substring uniquely identifies exactly one habit. Multi-match → `judgment_required`.

The special-token family (`"all done"`, etc.) is checked FIRST as a separate pass before the per-token matching.

**Rationale**: Each tier is deterministic and trivially testable. Substring match captures most reasonable Kent shorthand (`"meditation"` → "Meditate 45 min") without false positives. Ambiguity is surfaced explicitly, not silently resolved.

**Alternatives considered**:
- Token-similarity scoring (rejected — non-deterministic in edge cases; harder to test).
- Levenshtein distance threshold (rejected — same).
- Send everything to the LLM (rejected — over-uses judgment surface; expensive; per scripts-vs-LLM split).

---

## D4. Disambiguator prompt structure

**Decision**: Single-turn LLM call. System prompt explains the task verbatim. User prompt provides:
- The original reply text (full string)
- The ambiguous token (e.g., `"PT"`)
- The candidate titles + task_ids
- A short instruction: "Return the chosen task_id as JSON. If you cannot confidently determine which one Kent meant, return `'clarify'`."

Response format: strict JSON with one of `{chosen_task_id: int}` or `{result: "clarify", reason: str}`.

**Rationale**: Single-turn is sufficient for this narrow choice. Cache-friendly (system prompt + candidate-format scaffold is cacheable; only the specific reply + candidates vary per call).

**Alternatives considered**:
- Multi-turn with retry on bad JSON (rejected — extra latency for a narrow surface; if Haiku can't produce JSON for this, the prompt is wrong, not the model).
- Free-text response with parsing (rejected — defeats the purpose of structured output).

---

## D5. Disambiguator model

**Decision**: `claude-haiku-4-5` (matches `scripts/doc_audit/judgment/client.py`'s model selection from mission #343).

**Rationale**: Narrow disambiguation is exactly Haiku's strength — fast, cheap, sufficient capability. The same model already runs in production for the doc-auditor judgment surface; no new API surface to validate.

**Alternatives considered**:
- Sonnet 4.6 (rejected — overkill for binary/few-way disambiguation; ~10x cost).
- Opus (rejected — even more overkill).

---

## D6. Disambiguator API key + auth

**Decision**: Read API key from `/data/services/openclaw/secrets/anthropic` (mode 0600), same path used by `scripts/doc_audit/judgment/client.py`.

**Rationale**: Single source of truth for Anthropic credentials on office2. No new credential to provision or rotate.

**Alternatives considered**:
- Use the project-specific key in `~/.zshrc` (rejected — that's Kent's interactive shell env, not deployable as cron-readable).
- Use a separate habits-specific key (rejected — pointless credential proliferation).

---

## D7. Reply special-token taxonomy

**Decision**: The parser detects (case-insensitive) these patterns BEFORE per-token matching, mapping them to "complete every position in the morning list":

- `"all done"`, `"done with everything"`, `"everything done"`, `"all complete"`
- `"all of them"` (only when not preceded by a different verb)
- `"done with all"` / `"all"` (only when alone or with `"done"`)

Skip patterns (mapping to "skip every position"):
- `"skipping everything"`, `"skipped all"`, `"none done"`, `"nothing done"`

Mixed patterns (e.g., `"all done except 3"`) require a more flexible parse — these initially route to `judgment_required` so the LLM disambiguator can interpret. This is acceptable LLM use because parsing English clauses with exceptions IS judgment work.

**Rationale**: The common patterns are deterministic and frequent — fast-path them in the parser. The rarer "all X except Y" patterns are correctly LLM-judgment.

**Alternatives considered**:
- Enumerate all "except" patterns deterministically (rejected — long tail of English variation; brittle).
- Send everything to LLM (rejected — common cases shouldn't pay LLM cost).

---

## D8. Number range syntax (`"1-4 done"`)

**Decision**: Out of scope (C-006). The parser treats `"-"` as a separator character and tokenizes `"1-4"` as two tokens `"1"`, `"4"` (or rejects with a structured error if neither parses). Kent uses comma-separated single positions only.

**Rationale**: Range syntax adds parsing complexity for a use case Kent doesn't actually use today. Easy to add later as a follow-on if needed.

**Alternatives considered**:
- Support ranges (deferred — file a follow-on if Kent's usage patterns shift).
- Send ranges to LLM (rejected — deterministic work).

---

## D9. Idempotency

**Decision**: The parser does NOT implement dedup. Idempotency comes entirely from `record_completion.py`'s existing `idempotent_record_event` contract (Phase 3). The agent invokes `record_completion --idempotent` for each tuple from the parser.

**Rationale**: Dedup at the parser would require coupling to the JSONL state log — a layering violation. The existing record_completion API already handles "this habit + this date + this state already recorded" cleanly.

**Alternatives considered**:
- Parser checks state log before emitting (rejected — couples concerns; parser becomes stateful).
- Multiple replies same day produce conflicting tuples (rejected — record_completion already deals with this).

---

## D10. AGENTS.md cut targets

**Decision**: Remove from the deployed AGENTS.md:

- §"Step 2: Query habits scheduled for today (helper)" — collapse to one-line "Invoke `morning_checkin_list.py` and pass through stdout to Kent"
- §"Step 4: Exclude habits already addressed today" — same; the helper handles it internally
- §"Step 5: Format the check-in message" — DELETE entirely; helper emits the formatted message
- §"Completion marking → Recognize natural language" — DELETE the enumerated examples and prose; replaced with one-line invocation of `parse_morning_reply.py`
- §"Match against habit titles using fuzzy matching" — DELETE; helper does it
- §"If Kent references numbers... match against the numbered list from the most recent check-in message in this session" — DELETE (THE BUG LINE)

Keep:
- Governance + identity + autonomy declaration
- Output discipline (Hard Rules #1 and #2 — what the agent's final reply must look like)
- Scope statement
- Tick workflow SKELETON (5-7 step-numbered structure, ≤10 lines per step)
- Helper-invocation block: `python3 -m scripts.habits.morning_checkin_list ...` and `python3 -m scripts.habits.parse_morning_reply ...`
- Ambiguity-clarification protocol: when parser emits `judgment_required` and disambiguator emits `"clarify"`, agent asks Kent ONE clarifying question per cluster; no silent guessing
- Fallback on helper failure: file P2-bug via `felix-file-issue.py`; reply with `IDLE` token
- Tailscale connectivity reminder
- Reference link to this mission's spec

Target: source content ≤14,000 chars. Headroom for the openclaw ~26% inflation per memory `reference_openclaw_gotchas.md`.

**Rationale**: The deleted sections are responsibilities that move to scripts. The retained sections are pure orchestration + governance + protocol — irreducible.

**Alternatives considered**:
- Keep everything but reorganize (rejected — keeps AGENTS.md over budget; truncation problem persists).
- Delete more aggressively (rejected — risks losing tick-workflow continuity).

---

## D11. Cutover sequence

**Decision**: Manual cutover per quickstart.md, in this order:

1. Pre-flight: confirm Restic backup within 24h (Tier 2); verify cron is disabled.
2. SSH office2 → `cd /home/claude/kg-automation && git pull origin main` (after merge).
3. CLI smoke-test: `python3 -m scripts.habits.morning_checkin_list --dry-run` (writes nothing but emits formatted message).
4. CLI smoke-test: synthetic morning-list JSON + a test reply through `python3 -m scripts.habits.parse_morning_reply`.
5. Diff current vs new deployed AGENTS.md; confirm structural cuts match D10; confirm char count ≤14K.
6. Copy new AGENTS.md to deploy path (writable as `claude:felix` group).
7. Manual cron tick trigger (`openclaw cron run 3082343c-bc7f-47ee-916b-ee070b1e50dc` while cron is still disabled — single one-off invocation).
8. Verify journalctl shows: NO truncation warning, helper invocation appears in agent output, persisted JSON file created at expected path.
9. Send a synthetic test reply to the agent via OpenClaw's reply path; verify parser output + record_completion calls hit the right habits.
10. Re-enable cron: `openclaw cron enable 3082343c-bc7f-47ee-916b-ee070b1e50dc`.
11. Tomorrow morning 7:05 AM ET: Kent observes the cron tick + sends a real reply. Verify journal + JSONL.

If step 9 fails or step 8 shows truncation warning: abort, restore AGENTS.md from the pre-cutover snapshot, leave cron disabled, file follow-on issue.

**Rationale**: Manual cutover with explicit verify-each-step gates. Single biggest risk is AGENTS.md truncation — step 5 (pre-deploy char-count check) catches it before the bad version lands.

**Alternatives considered**:
- Automate the cutover (rejected — too risky; manual sanity checks at each step are cheap).
- Skip manual tick trigger (rejected — first real tick should NOT be tomorrow morning's cron; verify in a controlled window).

---

## Summary

11 engineering decisions locked. No outstanding clarifications. Proceed to Phase 1 design artifacts (data-model.md, contracts/, quickstart.md).
