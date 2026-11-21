# Post-plan review (independent, cross-vendor)

- **Date:** 2026-11-19
- **Reviewer:** Codex CLI 0.170.0, model `gpt-6.1-sol` (OpenAI). Read-only sandbox, no profile.
- **Plan author / implementer orchestrator:** Claude Opus 5.5 (Anthropic). The reviewer is a different vendor from the implementer, as the standing rule requires.
- **Inputs:** spec.md, plan.md, research.md, data-model.md, contracts/*, quickstart.md, plus repo source and vikunja-harness `d7e202228`.
- **Verdict:** `not-ready`, with 10 findings (7 HIGH, 3 MEDIUM). All 10 were verified by the lead and accepted. The plan artifacts were revised in the same commit as this record.

## Raw findings (verbatim)

1. HIGH | The preservation invariant contradicts valid COUNT completion
   Evidence: kitty-specs/felix-rrule-adaptation-01M7TKNX/data-model.md:107; contracts/vikunja-client-v2.md:71–75; d7e202228:pkg/models/tasks.go:2342–2368.
   Why it matters: Successful completions decrement COUNT, and the final completion clears the rule. Requiring the same rule after every completion either rejects correct behavior or encourages fixtures that conceal it.
   Suggested change to the plan: Define operation-specific invariants and test COUNT=2 → COUNT=1 → Done/no rule. Test server-driven reminder movement separately from accidental reminder removal.

2. MEDIUM | Done does not prove that a series exhausted normally
   Evidence: kitty-specs/felix-rrule-adaptation-01M7TKNX/data-model.md:47–50; d7e202228:pkg/models/tasks.go:2335–2351; d7e202228:pkg/models/task_next_occurrence.go:100–130.
   Why it matters: Invalid rules, horizon limits and policy refusals also leave tasks Done. The proposed classifier labels these failures “series_ended” and suppresses its unexpected-outcome alert.
   Suggested change to the plan: Distinguish expected COUNT/UNTIL exhaustion from evaluation refusal, using occurrence reasons where available. Require alerting when exhaustion cannot be established.

3. HIGH | Restore cannot reliably reproduce the snapshot
   Evidence: kitty-specs/felix-rrule-adaptation-01M7TKNX/contracts/repair-and-inventory-cli.md:35; contracts/vikunja-client-v2.md:15; research.md:41; d7e202228:pkg/models/task_repeat_update.go:97–110; d7e202228:pkg/models/task_rule_text.go:239–263.
   Why it matters: Restoring a higher COUNT can be ignored as a stale echo. Restoring a structured repeat merges with existing rule parts, while a snapshot’s reminders=null is rejected by patch_task’s contract; restoring done=true against an open repeating task can also trigger completion.
   Suggested change to the plan: Specify an ordered restore algorithm using canonical rule text, deliberate clearing where necessary, explicit nullable-field handling and controlled done transitions. Test restoration across different rules, decremented COUNT, null reminders and changed completion state.

4. HIGH | Inventory differences are not necessarily damage, and repair ignores intervening edits
   Evidence: kitty-specs/felix-rrule-adaptation-01M7TKNX/contracts/repair-and-inventory-cli.md:27–31; quickstart.md:44–45; d7e202228:pkg/models/tasks.go:2357–2368.
   Why it matters: COUNT naturally changes through completion, and Kent may intentionally edit or remove rules. Apply snapshots the current task but never requires it to match the inventoried current value, so it can overwrite a subsequent UI edit with an older restore proposal.
   Suggested change to the plan: Separate expected progression and intentional changes from confirmed damage. Before applying, compare the fresh read with the inventory’s expected state and stop on drift; define how UI writes are excluded during repair.

5. HIGH | Two-PATCH series termination has no recovery contract
   Evidence: kitty-specs/felix-rrule-adaptation-01M7TKNX/contracts/vikunja-client-v2.md:21–25; data-model.md:37; d7e202228:pkg/models/tasks.go:1729–1761.
   Why it matters: If clearing succeeds and marking Done fails, an open task is left without recurrence. A timeout leaves the committed state uncertain, and the contract only checks Done rather than also confirming that recurrence remains absent.
   Suggested change to the plan: Define resumable termination with readbacks, explicit partial-success reporting and verification of both final conditions. Test failures and timeouts at each PATCH, 304 responses and a rule reintroduced between steps.

6. HIGH | Failed repair verification can omit a committed write from the journal
   Evidence: kitty-specs/felix-rrule-adaptation-01M7TKNX/contracts/repair-and-inventory-cli.md:28–31; spec.md:177; spec.md:189.
   Why it matters: The journal append occurs only after successful readback. A committed PATCH followed by a timeout or mismatch stops before recording the change, defeating the requirement that every live change be recorded.
   Suggested change to the plan: Persist an operation-intent record before PATCH and journal success, mismatch and unknown outcomes. Generate restore instructions before writing and make interrupted runs recoverable from that journal.

7. HIGH | A single merge does not synchronize helpers and agent instructions
   Evidence: kitty-specs/felix-rrule-adaptation-01M7TKNX/plan.md:121; plan.md:152–153; docs/runbooks/deploy/office2-deploy-paths.md:74–87; scripts/openclaw/agents/felix-admin-escalation/AGENTS.md:202–208.
   Why it matters: Helpers become active when the shared checkout advances, while prompt and skill copies update independently. During that window, old escalation instructions still execute the destructive v1 POST before calling the newly working helper.
   Suggested change to the plan: Pause affected agent writes during rollout, verify helper and copied-document revisions, then resume. Include active sessions holding old instructions in the deployment gate.

8. MEDIUM | The required pre-merge credential probe calls an undeployed method
   Evidence: kitty-specs/felix-rrule-adaptation-01M7TKNX/quickstart.md:19–27; plan.md:71; docs/runbooks/deploy/office2-deploy-paths.md:74–79; scripts/common/vikunja_client.py:415–475.
   Why it matters: Before merge, office2’s normal checkout lacks the new occurrences method, so the prescribed probe fails independently of token permissions. It also checks only occurrences, leaving preview permission unverified.
   Suggested change to the plan: Use existing read-only HTTP tooling to verify both endpoint permissions before revoking the old token. Keep helper-level probes after deployment and make their output match the stated status-only contract.

9. MEDIUM | Silent first-cycle seeding can permanently hide a real rule loss
   Evidence: kitty-specs/felix-rrule-adaptation-01M7TKNX/plan.md:145; research.md:92–94; quickstart.md:32–45.
   Why it matters: A rule lost before its first observation is silently adopted as absent. The proposed test removes a rule only after seeding, and the rollout does not coordinate seeding with the damage inventory.
   Suggested change to the plan: Establish and persist a verified rule baseline before reopening writes, coordinated with inventory. Add a deployment-to-first-cycle loss test that must produce an unresolved discrepancy rather than a silent seed.

10. MEDIUM | The retained fallback is neither preserved mechanically nor guarded as specified
    Evidence: kitty-specs/felix-rrule-adaptation-01M7TKNX/spec.md:157; contracts/vikunja-client-v2.md:53–54; scripts/common/vikunja_client.py:458–463.
    Why it matters: update_task_fields currently calls replace_task_fields, which the plan removes. Its planned change is described as a docstring update, and no guard prevents changes from explicitly dropping an existing rule or reminders.
    Suggested change to the plan: Explicitly replace the removed internal call and define the FR-002 preservation guard. Add fallback tests covering successful full echo and refusal of destructive changes.

VERDICT: not-ready
## Dispositions

| # | Sev | Finding | Disposition | Where fixed |
|---|---|---|---|---|
| 1 | HIGH | The rule-preservation invariant contradicts the COUNT decrement and the clear on exhaustion | Accepted. Invariants are now per operation; completion tests cover COUNT 2→1, COUNT 1→Done, UNTIL, and unexpected outcomes | data-model.md Invariants; contracts/vikunja-client-v2.md test obligations |
| 2 | MED | `done=true` does not prove a normal series end | Accepted. `series_ended` requires exhaustion to be expected before the write (COUNT==1, or UNTIL checked by preview). Otherwise the outcome is `unexpected` and raises an alert | data-model.md Completion outcome; research.md R-010 note; plan.md IC-01 |
| 3 | HIGH | Restore cannot reliably reproduce the snapshot | Accepted. Ordered restore algorithm: canonical text with clear-first, `[]` for null reminders, controlled done transitions, full readback | data-model.md Repair restore algorithm; repair contract |
| 4 | HIGH | Inventory differences are not necessarily damage; repair ignores later edits | Accepted. New statuses `progressed`, `ended`, `lost`, `changed`, `unresolved`; only `lost` is auto-repaired; fingerprint drift check before each write | data-model.md inventory entry; repair contract |
| 5 | HIGH | The two-PATCH series end has no recovery contract | Accepted. Resumable, idempotent `end_series` with `SeriesEndIncomplete` states, a re-read on timeout, and failure and timeout tests at each step | data-model.md End-series recovery contract; client contract |
| 6 | HIGH | A failed verification can leave a committed write out of the journal | Accepted. Intent journal before the write, an outcome journal entry for every attempt (`ok`, `mismatch`, `unknown`), and `--resume` | repair contract |
| 7 | HIGH | A single merge does not switch helpers and agent docs together | Accepted. Rollout-window procedure: pause `N done` (or, with Kent's go, disable the cron), check synced-copy MD5s and a fresh session, then lift the pause | quickstart.md Rollout window; plan.md IC-03 and gates |
| 8 | MED | The pre-merge probe calls an undeployed method, and only checks occurrences | Accepted. Inline probe that uses only deployed code and checks both endpoints; verify before revoking the old token | research.md R-004; quickstart.md |
| 9 | MED | Silent first-cycle seeding can hide a real loss | Accepted. Seeds are recorded in `seed-ledger.jsonl`; the inventory runs after the first sync cycle and cross-checks the ledger | data-model.md sync entry; inventory contract; quickstart.md; plan.md IC-06 |
| 10 | MED | The retained fallback is neither kept working nor guarded | Accepted. `update_task_fields` calls `post` directly, carries the FR-002 guard and an explicit override, and has tests | data-model.md client table; client contract |

## Re-review 1 (2026-11-19, same reviewer: Codex 0.170.0 / gpt-6.1-sol), on commit 4022abc6

Verdict `not-ready`. Findings 1, 6, 7 and 10 were resolved. 2, 3, 4, 5, 8 and 9 were partial. The revision introduced two new HIGH problems and one new MEDIUM. Verbatim:

Read-only review of `4022abc6`; no files changed, network used, or skills loaded. Plan paths below are relative to `kitty-specs/felix-rrule-adaptation-01M7TKNX/`; server references are pinned to `d7e202228`.

1. **RESOLVED** — Operation-specific invariants now allow COUNT decrement and final rule removal, with explicit tests. `data-model.md:121–126`; `contracts/vikunja-client-v2.md:88`.
2. **PARTIAL** — Expected exhaustion is required, but “returned no occurrence” still accepts refusal/horizon failures as exhaustion. `data-model.md:52`; server `pkg/models/task_occurrences.go:249–256`, `pkg/models/task_next_occurrence.go:108–114`.
3. **PARTIAL** — Clear-first works: echoed unchanged text defers to `repeat=null`, and the subsequent text write succeeds against empty storage. However, restoring a no-rule snapshot omits its `repeats_from_current_date`; restoring an unset due date also conflicts with the client’s null prohibition. `data-model.md:151–155`; `contracts/vikunja-client-v2.md:15`; server `pkg/models/task_rule_text.go:235–261`.
4. **PARTIAL** — Fingerprinting and progress statuses address drift and COUNT changes, but intentional rule removal remains classified `lost` and automatically repaired. `data-model.md:85–86`; `contracts/repair-and-inventory-cli.md:29–32`.
5. **PARTIAL** — Recovery, timeouts and partial outcomes are specified, but the new Done-with-rule no-op contradicts the required final “Done AND no rule” invariant. `data-model.md:127`, `data-model.md:140`; `contracts/vikunja-client-v2.md:26`.
6. **RESOLVED** — Durable intent precedes writes; mismatch/unknown outcomes and interrupted-run reconciliation are specified. `contracts/repair-and-inventory-cli.md:33–37`.
7. **RESOLVED** — Rollout pauses affected replies and checks copied instructions plus cached session prompts before resuming. `quickstart.md:32–40`.
8. **PARTIAL** — The replacement probe uses existing client attributes and checks both endpoints, but the numbered procedure still deletes the old token before verification. `research.md:58–74`; `quickstart.md:23–24`; `scripts/common/vikunja_client.py:219–220`.
9. **PARTIAL** — Seeding is recorded and cross-checked, but the unconditional baseline-rule/seeded-no-rule override also flags legitimate completed COUNT series as damage. `data-model.md:73–75`; `contracts/repair-and-inventory-cli.md:17`; server `pkg/models/tasks.go:2342–2347`.
10. **RESOLVED** — Direct `self.post`, the preservation guard, override and fallback tests are explicit. `contracts/vikunja-client-v2.md:63–65`.

New problems introduced by the revision:

- **HIGH — Exhaustion classifier still suppresses real failures.** The new empty-occurrences shortcut accepts `anchor_beyond_horizon`, for example. Due date alone also cannot reproduce completion context: preview omits start/end/reminders, defaults from-current-date to false, and forecasts future from-current completions at the due date. Require explicit exhaustion reasons and matching context; otherwise classify unknown/unexpected. `data-model.md:52`; server `pkg/models/task_occurrences.go:150–176`, `:196–201`; `pkg/models/tasks.go:2375–2385`.
- **HIGH — Seed-ledger override can resurrect a legitimately ended series.** COUNT exhaustion produces Done/no rule; first-cycle seeding then satisfies the new unconditional `lost` override, making it eligible for automatic repair. Apply normal-end classification before that override. `contracts/repair-and-inventory-cli.md:17`, `:29`; server `pkg/models/tasks.go:2342–2347`.
- **MEDIUM — `end_series` now accepts Done-with-rule without establishing UNTIL exhaustion.** Done-with-rule can also represent evaluation refusal, so the new no-op branch cannot assume normal termination. `data-model.md:140`; server `pkg/models/tasks.go:2349–2351`.

The requested `done=false` check: it **does not advance recurrence or decrement COUNT**; it clears `done_at`. The revised transition is safe from completion stepping, though not side-effect-free. Server `pkg/models/tasks.go:2551–2566`.

VERDICT: not-ready
### Dispositions (all accepted and verified against source)

| Item | Fix |
|---|---|
| 2 + new-HIGH 1 (exhaustion classifier) | `series_ended` requires an explicit reason: COUNT==1 locally, or preview `until_passed`/`count_exhausted` with the from-current flag false. An empty list with any other reason, or the from-current flag set, gives `unknown`, which means unexpected and an alert. |
| 3 (restore) | A no-rule snapshot restores `repeats_from_current_date` together with the rule clear. A null due date is restored through a sanctioned internal `_allow_null` path. |
| 4 (intentional removal) | `lost` now requires Felix-write attribution (a Felix log entry, with the task's `updated` within 120 s of it). Otherwise the status is `removed` and the task goes to Kent. |
| 5 + new-MEDIUM (end_series) | A done task that still has a rule is not taken as a normal end: `repeat:null` is PATCHed and read back. The final "done and no rule" check now holds in every branch. |
| 8 (token order) | Quickstart reordered: verify the new token, then delete the old one; restore the old one on failure. |
| 9 + new-HIGH 2 (seed override) | The normal-end check runs first. A seeded no-rule task whose baseline had COUNT or UNTIL goes to Kent and is never auto-repaired. |

## Re-review 2 (2026-11-19, Codex 0.170.0 / gpt-6.1-sol), on commit b290150d

Verdict `not-ready`. Resolved: 2, 3, 8, 9, new-HIGH 1 and new-HIGH 2. Open: 4, 5 and new-MEDIUM. Verbatim:

Paths relative to `kitty-specs/felix-rrule-adaptation-01M7TKNX/`; reviewed HEAD against server `d7e202228`.

- **2 — RESOLVED:** Explicit exhaustion reasons replace empty-result inference; refusal and uncertainty raise alerts. `data-model.md:50`
- **3 — RESOLVED:** Restore includes the snapshot’s from-current flag and permits internal null due-date clearing. `data-model.md:124`, `data-model.md:157`
- **4 — NOT RESOLVED:** A Felix write followed by intentional UI rule removal within 120 seconds still qualifies as `lost`; timestamp proximity cannot establish which write removed the rule. `data-model.md:90`
- **5 — NOT RESOLVED:** Recovery table requires clearing Done-with-rule, but the client contract still explicitly returns UNTIL-ended tasks as-is. `data-model.md:145`; `contracts/vikunja-client-v2.md:26`
- **8 — RESOLVED:** Both endpoint probes now precede old-token revocation. `quickstart.md:23`, `quickstart.md:27`
- **9 — RESOLVED:** Normal-end classification precedes seed handling; finite seeded series cannot become auto-repair candidates. `contracts/repair-and-inventory-cli.md:18`
- **New HIGH 1 — RESOLVED:** Explicit preview reasons and exclusion of from-current rules close the failure-suppression shortcut. `data-model.md:52`
- **New HIGH 2 — RESOLVED:** Seeded COUNT/UNTIL series are classified `ended` or `removed`, never `lost`. `contracts/repair-and-inventory-cli.md:18`
- **New MEDIUM — NOT RESOLVED:** The revised recovery table fixes the branch, but the contradictory as-is exception remains in the client contract. `contracts/vikunja-client-v2.md:26`

No additional verified NEW HIGH problems found.

VERDICT: not-ready
### Dispositions

- **5 and new-MEDIUM: fixed.** The `end_series` docstring in the client contract had a stale "returned as-is" exception. It now matches the recovery table: done with no rule in every branch.
- **4: accepted residual risk, documented (lead decision; Kent can overrule).** Timestamp proximity cannot prove which write removed a rule. The remaining misclassification needs a Felix write followed, within 120 s, by Kent removing the rule in the UI. The impact is a rule re-added to one task, and it is fully reversible: every repair has a snapshot and a `--restore`. Mitigations:
  - Felix attribution is required for `lost`.
  - The `lost` dry-run list is posted on #1111 before `--apply`.
  - Each task gets a drift check immediately before its write.
  - The expected inventory is empty (#1111 core-worker audit).

  No further review round. The open item is a recorded disposition, not an unresolved defect.
