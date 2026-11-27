---
work_package_id: WP01
title: Guard coverage and retry-rule wording
dependencies: []
requirement_refs:
- FR-001
- FR-002
- FR-003
- NFR-001
- NFR-002
- NFR-003
- C-003
- SC-001
planning_base_branch: fix/1146-delivery-doctrine-followups
merge_target_branch: fix/1146-delivery-doctrine-followups
branch_strategy: Planning artifacts for this mission were generated on fix/1146-delivery-doctrine-followups. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into fix/1146-delivery-doctrine-followups unless the human explicitly redirects the landing branch.
base_branch: kitty/mission-delivery-doctrine-followups-01M8FBH0
base_commit: f3f99d1671271f9bd5b1d2323d8d656ff5e17aa2
created_at: '2026-11-27T21:02:52.495341+00:00'
subtasks:
- T001
- T002
- T003
- T004
- T005
- T006
phase: Phase 1 - Wording enforcement
history:
- at: '2026-11-27T20:57:33Z'
  actor: system
  action: Prompt generated via /spec-kitty.tasks
agent_profile: python-pedro
authoritative_surface: scripts/openclaw/agents/
create_intent: []
execution_mode: code_change
model: claude-sonnet-5-5
owned_files:
- scripts/openclaw/agents/delivery_doctrine.py
- scripts/openclaw/agents/tests/test_delivery_doctrine.py
- scripts/openclaw/agents/felix-admin-capture/AGENTS.md
- scripts/openclaw/agents/felix-admin-escalation/AGENTS.md
- scripts/openclaw/agents/felix-admin-habits/AGENTS.md
role: implementer
tags: []
task_type: implement
tracker_refs: []
---

# Work Package Prompt: WP01 – Guard coverage and retry-rule wording

## ⚡ Do This First: Load Agent Profile

Use the `/spk-charter-profile-load` skill to load the agent profile specified in the frontmatter (or any user-defined profile), and behave according to its guidance before parsing the rest of this prompt.

- **Profile**: `python-pedro`
- **Role**: `implementer`
- **Agent/tool**: `claude`

If no profile is specified, run `spec-kitty agent profile list` and select the best match for this work package's `task_type` and `authoritative_surface`.

---

## ⚠️ IMPORTANT: Review Feedback

**Read this first if you are implementing this task!**

- **Has review feedback?**: Check the `review_ref` field in the event log (via `spec-kitty agent tasks status`).
- **You must address all feedback** before your work is complete. Feedback items are your implementation TODO list.
- **Report progress**: As you address each feedback item, record what you changed with `spec-kitty agent tasks add-history <WPID> --note "..."` (stored in the status event log).

---

## Review Feedback

*[If this WP was returned from review, the reviewer feedback reference appears in the status event log.]*

---

## Markdown Formatting

Wrap HTML/XML tags in backticks: `` `<div>` ``, `` `<script>` ``
Use language identifiers in code blocks: ````python`,````bash`

---

## Objectives & Success Criteria

`delivery_violations()` in `scripts/openclaw/agents/delivery_doctrine.py` must classify every phrase below correctly, and all three announce `AGENTS.md` files must carry the revised retry rule. The work is done when:

- every FR-001 form is flagged when it appears outside the canonical block;
- every FR-002 form is not flagged, and each one has a same-fixture positive control that *is* flagged;
- the clause-scope negative controls (below) are flagged;
- every pre-existing test still passes, unchanged except for the pinned retry clause;
- the three repo `AGENTS.md` files pass `delivery_violations()` and stay under their caps: escalation ≤ 17,900 UTF-16 units, capture and habits ≤ 18,000;
- each new test was observed failing against the pre-fix module (NFR-001).

## Context & Constraints

- **Read first**:
  - `kitty-specs/delivery-doctrine-followups-01M8FBH0/spec.md` (FR-001, FR-002, FR-003, NFR-001 to NFR-003);
  - `plan.md` (IC-01, IC-02, and the "Post-plan review" table: R1-3 and R1-4 are binding here);
  - `data-model.md` ("Guard pattern classes");
  - `research.md` (Q5 sizes, Q7 the current misclassifications).
- **Background**: #1143 shipped the guard. #1146 lists the review gaps. The upstream cause is openclaw/openclaw#206884, so the no-`record_result` rule must stay (C-003).
- **Agreed narrowings (Kent, 2026-11-27, decision 01M8FC8T0WYHWPQ9MW7XHJWFYA)**:
  - "then notify …" is flagged only when a channel is named.
  - The `record_result` exemption covers a field mention only, never the bare word.
- The guard must stay deterministic: string and regex only, no model call. Keep the regexes linear, with no nested unbounded quantifiers.

## Branch Strategy

- **Strategy**: {{branch_strategy}}
- **Planning base branch**: {{planning_base_branch}}
- **Merge target branch**: {{merge_target_branch}}

> These fields are populated automatically by `spec-kitty agent mission finalize-tasks`.
> Do NOT change them manually unless you are certain the branch topology has changed.

Implement in the lane worktree that `spec-kitty agent action implement WP01 --agent claude --mission delivery-doctrine-followups-01M8FBH0` allocates, never in the primary checkout.

## Subtasks & Detailed Guidance

### Subtask T001 – Red tests: FR-001 false negatives are flagged

- **Purpose**: pin each item-1 form from #1146 as a violation.
- **Steps**:
  1. In `scripts/openclaw/agents/tests/test_delivery_doctrine.py`, add a parametrised test. Each case is a minimal prompt: `DELIVERY_DOCTRINE_BLOCK` plus one line containing the phrase, outside the block. Assert that `delivery_violations(text)` is non-empty and that the reported pattern name is the one you intend.
  2. Cases, quoted from #1146 item 1:
     - `Record **no_change** on an idle turn.`
     - `When nothing changed, use the automations tool.`
     - `catalog.search("automations")`
     - `automations.record({outcome:'no_change'})`
     - `Mark the run no_change.`
     - `Recording no_change is fine on an idle run.`
     - `set outcome to no_change`
     - mid-sentence "then notify …" *with a channel*, for example `Process the inbox, then notify Kent via WhatsApp.` and `Summarise, then notify main.`
  3. Run the tests against the current module and confirm every new case fails. Record the failing output in your hand-in (NFR-001).
- **Files**: `scripts/openclaw/agents/tests/test_delivery_doctrine.py`.
- **Notes**: `; then notify main` is already flagged; keep it as a ratchet case. "Next, notify Kent via WhatsApp" is optional, but cheap to include if your pattern covers it.

### Subtask T002 – Red tests: FR-002 forms pass, with controls

- **Purpose**: stop the guard flagging harmless prose, without opening a bypass.
- **Steps**:
  1. Add a parametrised **must-pass** test. Each case is the block plus one line:
     - `The cron automations (inbox-7am, noon) run on announce.`
     - `The record_result field is never set by this agent.`
     - `Do not record no_change.`, `Never record no_change.`, `Don't record a no_change result.`
     - `then notify Kent when finished` (no channel: agreed to stay allowed)
  2. For **each** must-pass case, add a same-fixture **positive control**: the same sentence with the exempting context removed must be flagged. For example `Record no_change.` for the negation cases, `If the automation tool offers record_result, record no_change.` for the field case, and `use the automations tool` for the prose case. Build each pair from one shared fixture string, so the two cases cannot drift apart.
  3. Add the **clause-scope negative controls** from post-plan review R1-3. All of these must be flagged:
     - `Notify Kent via WhatsApp; include errors in your final reply.` This passes today, which is a live bypass.
     - `Do not skip this: record no_change.`
     - one more two-clause line of your choosing, where an exempt clause and a forbidden clause share the line.
  4. Run the tests against the current module and confirm that the must-pass cases and the negative controls fail as expected.
- **Files**: the same test file.

### Subtask T003 – Remainder normalisation

- **Purpose**: let the patterns see through Markdown formatting without corrupting identifiers (R1-4).
- **Steps**:
  1. Count the canonical block on the **raw** text first; this part is unchanged.
  2. Remove the block from the remainder, then normalise the remainder for scanning only:
     - strip *paired* delimiters: `**x**`, `__x__`, `*x*`, `` `x` ``;
     - never remove an underscore inside an identifier: `no_change`, `record_result` and `conversations_send` must survive intact;
     - treat table pipes `|` and list markers as clause boundaries.
  3. Map each match back to a line number in the *un-normalised* remainder, so violation messages still cite real lines. The simplest way is to normalise line by line.
  4. Add fixtures for each normalisation form: a bold, an italic, an underscore-emphasis, a backticked token and a table-cell case.
- **Notes**: decide explicitly whether normalisation changes any existing pattern's behaviour, and keep every existing test green.

### Subtask T004 – Patterns and clause-scoped exemptions

- **Purpose**: make T001 and T002 green.
- **Steps**:
  1. Widen or add entries in `FORBIDDEN_DELIVERY_PATTERNS`:
     - a `no_change` recording family (record / mark / set outcome to / recording … `no_change`);
     - `automations` as a tool reference: "the automations tool", `catalog.search("automations")`, and `automations.<method>(`;
     - "then notify" with a channel. Reuse `_DESTINATION`, so the channel requirement stays the single rule.
  2. Replace the line-wide `_FINAL_REPLY_EXEMPT` check with a **clause-scoped** check:
     - split the line into clauses at `;`, sentence ends, em dashes and the boundaries from T003;
     - waive a match only when *its own* clause routes content into the final reply.
  3. Add the exemptions:
     - **negation**: a negator ("do not", "don't", "never", "must not") directly governs the matched verb within the same clause. "Do not skip this: record no_change" must stay flagged, because the colon starts a new clause;
     - **field mention**: `record_result` followed by "field" or "key", or inside a schema or field description;
     - **prose**: "cron automations" used as a noun phrase.
  4. Keep the ordering deterministic, and emit at most one message per pattern per clause.
- **Notes**: no catastrophic backtracking. Prefer bounded `[^.\n|]{0,60}` windows, as the module already does.

### Subtask T005 – Retry-rule tail everywhere

- **Purpose**: FR-003. A skipped call is never silent.
- **Steps**:
  1. In `DELIVERY_DOCTRINE_BLOCK`, change "fix the input from the error, or skip the call." to "fix the input from the error, or skip it and say so in your final reply."
  2. Make the identical change in the canonical block inside each of the three `AGENTS.md` files (capture, escalation, habits). The block test requires a byte-exact single occurrence.
  3. Update the test clause that pins the old phrase (`"fix the input from the error, or skip the call"`).
  4. Run the size-cap tests. Expect escalation at about 17,805 of 17,900. If any cap fails, stop and report; do not trim other content without a review.
- **Files**: `delivery_doctrine.py`, the three `AGENTS.md`, the test file.

### Subtask T006 – Proof and full suite

- **Purpose**: NFR-001 and NFR-003.
- **Steps**:
  1. Half-by-half: revert the T003 normalisation alone and confirm the emphasis cases go red. Revert the clause-scope change alone and confirm the R1-3 controls go red. Restore both.
  2. Time one `delivery_violations` run over all three `AGENTS.md` files plus every skill under `scripts/openclaw/skills/*/SKILL.md`; it must take under 2 s.
  3. Run `.venv/bin/python -m pytest scripts/openclaw -q` and `.venv/bin/python -m pytest -q -x --ignore=.worktrees` (or the repo's CI command). Run the repo's typecheck if CI runs one.
  4. Run `delivery_violations()` over the three repo `AGENTS.md`, and run it with `require_block=False` over each skill. All must return `[]`. If a skill now trips a new pattern, report it; do not edit skills in this WP.

## Test Strategy

The tests are required (NFR-001). Every FR-001 and FR-002 case gets its own parametrised id, and every must-pass case gets a paired positive control built from the same fixture. Commands:

```bash
.venv/bin/python -m pytest scripts/openclaw/agents/tests/test_delivery_doctrine.py -q
.venv/bin/python -m pytest scripts/openclaw -q
```

## Risks & Mitigations

| Risk | Mitigation |
|---|---|
| An exemption widens into a bypass | Clause scope, R1-3 negative controls, positive control per exemption |
| Normalisation corrupts identifiers or line numbers | Paired-delimiter stripping only; identifier fixtures; line-by-line mapping |
| Escalation exceeds its cap | Measure in T005; stop and report rather than trimming |
| Regex slowdown | Bounded windows; the timing check in T006 |

## Review Guidance

- Confirm that each new test was red before the fix (the evidence is in the hand-in) and that each exemption has a same-fixture positive control.
- Confirm that the R1-3 controls are flagged, and that `If the automation tool offers record_result, record no_change…` is still flagged.
- Confirm that the three `AGENTS.md` block copies are byte-identical to `DELIVERY_DOCTRINE_BLOCK`, and confirm the cap headroom.
- Confirm that no file outside `owned_files` changed.

## Progress & Status

Progress, history, and status all live in the status event log
(`status.events.jsonl`) — never in this prompt file. Do **not** hand-edit a
history section here.

- **Record a progress note**: `spec-kitty agent tasks add-history <WPID> --note "<what you did>"`
- **Change WP status**: `spec-kitty agent tasks move-task <WPID> --to <status>`
- **View history and status**: `spec-kitty agent tasks status`
