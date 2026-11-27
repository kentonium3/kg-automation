---
affected_files: []
cycle_number: 1
mission_slug: delivery-doctrine-followups-01M8FBH0
reproduction_command:
reviewed_at: '2026-11-27T21:23:54Z'
reviewer_agent: claude
wp_id: WP01
---

# WP01 review feedback, round 1

**Reviewer:** Codex gpt-6.1-sol (read-only), 2026-11-27, independent of the implementer (w1, claude-sonnet-5-5). **Lead triage:** claude-opus-5-5.
**Range:** f3f99d167..9826cb650. **Verdict:** REQUEST CHANGES.

**Likelihood check by the lead:** the repo prompts are hard-wrapped. Escalation `AGENTS.md` has 129 of its 247 non-empty lines at 60–100 chars, and the skills wrap too. So bypasses that depend on a soft wrap are normal-use risks, and items 1–3 stay MAJOR.

Fix all four. Add a regression test for each that fails before the fix, and a same-fixture control.

1. **MAJOR: negation exceptions are lost across boundaries** (`delivery_doctrine.py` ~L149, L213–217).
   - `Do not record no_change\nunless the run is idle.` returns `[]`, but the base implementation flagged it.
   - `Do not record no_change, but do so when idle.` passes, because splitting removes `but` before the `_EXCEPTION` check sees it.
   - **Fix:** evaluate the unless/except/but/without exception context across soft wraps and coordinating clauses before granting the negation exemption.
2. **MAJOR: an ordinary soft wrap still bypasses FR-001** (~L86).
   - `Process the inbox, then notify Kent\nvia WhatsApp.` returns `[]`, because `_DESTINATION` excludes newlines in its window.
   - **Fix:** join soft-wrapped lines within the same paragraph before scanning, keeping list-item, table-cell and blank-line paragraph boundaries. Line citations must still point at the original line where the match starts.
3. **MAJOR: the schema exemption weakens an existing catch** (~L219–226).
   - `If idle, emit {"record_result":\n"no_change"}.` returns `[]`, though the single-line form and the base implementation flag it.
   - **Fix:** check the complete structured value, across wraps, before granting the quoted-key exemption.
4. **MINOR: the colon split creates a new false positive** (~L149, L212).
   - `Send the digest: it is your final reply.` is now flagged.
   - **Fix:** keep the colon boundary that makes `Do not skip this: record no_change` stay flagged, but recognise explicit final-reply routing across that colon, so the routing clause can exempt its own lead-in.

**Decisions:** Codex judged decisions 2–3 reasonable. Decision 4 is reasonable apart from the lost exception context (item 1). Decision 5 needs a structured, multi-line scope (item 3). Decision 1 needs the item 1 and item 4 revisions.

**Already verified, keep as-is:**
- all three prompts and six skills return `[]`;
- the byte-exact block appears once in each prompt, and the caps hold;
- both C-003 probes are flagged;
- about 54 ms (NFR-003);
- no catastrophic-backtracking pattern and no vacuous assertion.
