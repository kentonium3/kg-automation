# Post-Plan Codex Review — clarification-allday-fallback

**When**: 2026-07-18. **Reviewer**: Codex (`codex exec -p spec-kitty-review`, gpt-5.5,
danger-full-access), primary post-plan checkpoint. Clean exit 0, ~118k tokens,
full-stdout capture (no `-o`). Reviewer verified claims against the real source.

**Verdict**: plan directionally right (week-drift, `route_and_finalize` reuse,
all-day helper, rebaseline/deploy). Blockers were eligibility precision + an
overclaimed atomicity story. All findings folded into the artifacts (review-AND-fix).

| # | Sev | Finding | Resolution |
|---|-----|---------|------------|
| 1 | HIGH | Eligibility `== ["start_time"]` fails the canonical "Meet Rob Thursday" (no duration → `["start_time","end_or_duration"]`). | FR-005 rewritten to a **timing-only-gap** rule (start_time missing, end/duration optional, resolved date + title required). Updated in spec/plan/research/data-model. |
| 2 | HIGH | Validator would emit `start_date` only on the exact-match branch, excluding the real case. | IC-01: emit resolved `start_date` on **every** start-time-missing result. |
| 3 | HIGH | Atomicity overclaimed — record removal is post-transaction; after mark-succeeds/remove-fails the note IS processed. | Added **FR-009 reconciliation** + INV-6; FR-008 scoped to before-mark. |
| 4 | HIGH | Exactly-once is find-before-insert (TOCTOU) under concurrency. | NFR-004 **narrowed to sequential** (single serialized felix-admin-capture tick); documented, no lock added. |
| 5 | MED | Distinct routing-log signal underspecified (normal row is just `kind="calendar"`). | FR-007 + contract C3: concrete marker `calendar_all_day_fallback` (or explicit field). |
| 6 | MED | Idempotency key identity — record stores basename; helper keys on source_path. | INV-7 + contract: one **canonical absolute inbox path** for note arg AND `--idempotency-key`; test basename/path-form. |
| 7 | LOW | Keep timed regression tests when adding all-day seam. | IC-05/quickstart already cover; reaffirmed. |
| 8 | LOW | Rebaseline/deploy claim sound (agent AGENTS.md `affected_baselines: []`). | Confirmed; no change. |

Raw synthesis: `scratchpad/codex-postplan-780.synthesis.txt` (session-local).
