---
affected_files: []
cycle_number: 2
mission_slug: delivery-doctrine-followups-01M8FBH0
reproduction_command:
reviewed_at: '2026-11-27T21:51:00Z'
reviewer_agent: codex
wp_id: WP01
---

# WP01 review feedback, round 2

**Reviewer:** Codex gpt-6.1-sol (read-only), 2026-11-27. **Lead triage:** claude-opus-5-5, which rated by realistic likelihood (Kent's practicality rule) and narrowed scope because this is the third review round.
**Range:** 9826cb650..ba356a11a. **Codex verdict:** REQUEST CHANGES.

**Round-1 findings:** all four are closed (Codex probes).

## Fix (one item)

1. **MAJOR: a neighbouring instruction supplies a waiver** (`delivery_doctrine.py` ~L154).
   - **Problem:** `Notify Kent via WhatsApp\nInclude errors in your final reply.` returns `[]`, but round 1 flagged it. `Include`, `Put` and `Return` are missing from the instruction-boundary verbs. An indented verb is also missed: `Notify Kent via WhatsApp\n  Record errors in your final reply.` passes.
   - **Fix:** a line end followed by any capitalised word that starts a new sentence (optionally indented) ends the clause for waiver purposes. Don't keep a growing verb list; generalise the rule. Keep "Send the digest: it is your final reply." passing.
   - **Tests:** each red-first case, with controls on the same fixture.

## Accepted residuals (no change)

2. **MINOR: a `___` horizontal rule is not a boundary** (~L212). Rare in these prompts; `---` works. Recorded as a residual.
3. **MINOR: an exception word across a block boundary cancels a negation** (~L307). This only makes the guard stricter (a false positive, the safe direction). Recorded as a residual.
