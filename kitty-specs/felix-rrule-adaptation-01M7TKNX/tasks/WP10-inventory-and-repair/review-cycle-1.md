---
affected_files: []
cycle_number: 1
mission_slug: felix-rrule-adaptation-01M7TKNX
reproduction_command:
reviewed_at: '2026-11-20T00:03:20Z'
reviewer_agent: codex::reviewer-renata
wp_id: WP10
---

# WP10 review feedback — cycle 1

Reviewer: Codex CLI 0.170.0, model gpt-6.1-sol (OpenAI), read-only advisory, 2026-11-19. Verdict recorded by the orchestrator (Claude Opus 5.5). Implementer: Claude Opus 5.5 (python-pedro).

## Findings (verbatim)

1. MAJOR | Non-write logs authorize automatic repair | scripts/vikunja/rule_inventory.py:312 | Every nested task id counts as write attribution. A real sweeper record with dry_run=true and status=already_resolved classified a missing rule as lost. This exceeds the accepted timestamp-proximity risk and can undo intentional removals automatically. | Parse source-specific successful write records; exclude dry runs, evaluations, skips and failures. Add negative attribution tests.

2. MAJOR | Resume bypasses consent and drift protection through a replaced inventory | scripts/vikunja/rule_repair.py:766 | Runs retain only the inventory pathname. Resume reloads its current contents without validating selection or proposals. A probe repaired status=removed with accept_changed=false. Regenerating the inventory can also replace the fingerprint protecting intervening UI edits. | Persist immutable selected entries with the run, or verify the original inventory digest and refuse changes.

3. MAJOR | Torn journal tails swallow recovery outcomes | scripts/vikunja/rule_repair.py:195 | Reading ignores a partial final line, but appending does not repair its boundary. Resume’s outcome becomes concatenated with the damaged JSON and is subsequently ignored. The probe completed reconciliation yet left only the intent readable, losing the committed write’s outcome from reporting. | Recover the incomplete tail before appending, preserve complete records, fsync recovery, and test repeated resume after a torn outcome.

4. MAJOR | Apply reports success after collateral reminder loss | scripts/vikunja/rule_repair.py:490 | Apply verification checks only the rule and from-current flag. A probe through _apply_one removed reminders and the due date at readback and still journalled outcome=ok, readback_ok=true. The required preservation regression is missing. | Verify unchanged reminders, due date and completion state against the snapshot; compare relative reminders by relation and period. Test intact and stripped readbacks.

5. MINOR | Malformed seed values crash inventory | scripts/vikunja/rule_inventory.py:383 | Valid JSON rows with seeded_value="bad", [1], 7 or true raise uncaught AttributeError in normalise. These rows defeat the explicitly required malformed-ledger tolerance and prevent inventory output. | Validate seeded_value before normalization; count malformed rows as skipped and continue.

VERDICT: REJECT
## Required
- Fix all five, each with a test that fails on the current code.
- 1: source-specific parsers for each Felix log, counting only successful, non-dry-run writes that changed the task (sweeper auto_skipped_this_tick with dry_run=false for day-specific habits; habits/escalation done/rescheduled records with a Vikunja write; intake apply success). Anything unrecognised is NOT attribution.
- 2: persist the selected entries (or a digest of the inventory) with the run at apply time; resume refuses if the inventory changed.
- 3: repair a torn journal tail before appending (truncate to the last complete line, fsync), and test repeated resume after a torn outcome.
- 4: apply readback verifies reminders (relative by settings, absolute strict), due_date and done against the snapshot, not only the rule.
- 5: validate seeded_value before normalise; malformed -> skipped count.
