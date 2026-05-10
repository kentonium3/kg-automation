---
work_package_id: WP06
title: Canary + cron enablement + backlog drain
dependencies:
- WP05
requirement_refs:
- FR-010
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks:
- T022
- T023
- T024
- T025
- T026
agent: "claude:opus:orchestrator:orchestrator"
shell_pid: "48801"
history:
- at: '2026-05-09T23:54:00Z'
  actor: spec-kitty.tasks
  note: Initial scaffold from /spec-kitty.tasks
authoritative_surface: kitty-specs/felix-doc-auditor-agent-01KR7JK9/
execution_mode: planning_artifact
mission_id: 01KR7JK9QTHM5F4PD3YC43KDQW
mission_slug: felix-doc-auditor-agent-01KR7JK9
owned_files:
- kitty-specs/felix-doc-auditor-agent-01KR7JK9/canary-log.md
tags: []
---

# WP06 — Canary + cron enablement + backlog drain

## Objective

Validate the agent end-to-end against a real audit issue (#186 — the stuck weekly audit) at Level 1, then enable the cron and confirm the remaining 5 backlog issues drain within the NFR-006 window (≤6 hours).

This is the mission's correctness gate. If the canary fails, the agent does not go live and any deviations from spec must be filed and addressed before re-attempting.

## Context

- Mission: `felix-doc-auditor-agent-01KR7JK9`
- Spec: [../spec.md](../spec.md) — FR-009 (Level 1 approval), FR-010 (backlog), NFR-006 (drain SLA)
- Plan: [../plan.md](../plan.md)
- Research: [../research.md](../research.md) — R-014 (canary procedure)
- Quickstart: [../quickstart.md](../quickstart.md) — Steps 2-6 are the canary flow
- Contracts: [../contracts/whatsapp-summary.template.md](../contracts/whatsapp-summary.template.md), [../contracts/whatsapp-reply-vocabulary.md](../contracts/whatsapp-reply-vocabulary.md)

## Branch Strategy

- Planning/base branch: `main`
- Final merge target: `main`
- Execution: per-WP worktree from `lanes.json`. Branch from `main`. Merge back via spec-kitty review/merge.
- **Strict dependency**: WP05 must be complete (deploy + label + openclaw.json registration with cron disabled).

## Subtasks

### T022 — Manually invoke agent against issue #186

**Purpose**: Trigger the agent for a single, specific audit issue. Validates the full flow without depending on cron.

**Steps**:

1. Confirm pre-conditions (from WP05/T021):
   ```bash
   ssh office2-claude "openclaw agents | grep felix-doc-auditor"
   # Expected: agent listed
   ```

2. Confirm issue #186 is open and unprocessed:
   ```bash
   gh issue view 186 --repo kentonium3/kg-automation --json state,labels
   # Expected: state=OPEN, labels do NOT include status:in-progress
   ```

3. Invoke the agent:
   ```bash
   ssh office2-claude "openclaw delegate felix-doc-auditor 'Process audit issue #186 from kentonium3/kg-automation. Follow the doc-audit skill end-to-end.'"
   ```

4. Within ~10-30 seconds, observe:
   - Issue #186 should gain the `status:in-progress` label
   - Agent activity log entry should appear at `/home/kgale/second-brain/agents/logs/doc-auditor-YYYY-MM-DD.md`

**Validation**:
- [ ] Agent invocation returns success (no immediate error)
- [ ] `status:in-progress` label appears on #186
- [ ] Activity log shows the agent has started

**Failure modes**:
- Agent returns error → check WP05 deployment; check openclaw.json for correct workspace_path
- Label not applied → check gh CLI auth on office2 for the claude user
- No activity log entry → check that the log directory exists and is writable

---

### T023 — Receive WhatsApp summary; reply

**Purpose**: Exercise the Level 1 approval mechanism end-to-end.

**Steps**:

1. Wait for WhatsApp message from felix-doc-auditor. Expected within ~2-5 minutes of T022 (agent reads ~25 docs, builds proposals, composes message).

2. Inspect the summary message. Verify it:
   - Starts with `Sent by felix-doc-auditor:sonnet`
   - Lists the audit issue number (#186)
   - Lists docs reviewed count
   - Lists proposed high-confidence edits (numbered)
   - Lists planned debt issues / missing artifacts
   - Includes the reply vocabulary instructions

3. Inspect each proposed edit. For #186 (a weekly full-scope audit on docs that have likely seen many changes since 2026-04-19), the agent may propose several frontmatter date updates + cross-reference fixups.

4. Reply per the vocabulary in `contracts/whatsapp-reply-vocabulary.md`:
   - **If proposals look correct**: reply `approve`
   - **If some look right and others questionable**: reply `approve N,M` (only the safe ones)
   - **If all proposals look wrong or risky**: reply `reject` (agent will demote them all to debt issues)
   - **If the audit feels stale and you'd rather skip**: reply `skip`

5. For canary, recommended: if proposals are reasonable, reply `approve` to validate the commit path. Or `approve 1` to validate the partial-approve path.

**Validation**:
- [ ] WhatsApp message received within ~5 minutes
- [ ] Message format matches `whatsapp-summary.template.md` template
- [ ] Reply sent and acknowledged by agent (agent should send a brief confirmation)

---

### T024 — Verify canary outputs

**Purpose**: After the reply lands, the agent should commit + file debt issues + post summary + close + remove label, all in sequence. Validate each output.

**Steps**:

1. Verify any committed edits:
   ```bash
   git -C /Users/kentgale/repos/kg-automation log --oneline -5
   # Expected (if approved): a chore(doc-audit): ... (audit: #186) commit
   ```
   Pull the commit if it didn't auto-pull to local.

2. Verify the audit summary comment:
   ```bash
   gh issue view 186 --repo kentonium3/kg-automation --comments
   # Expected: a comment matching the template in contracts/audit-summary-comment.template.md
   ```

3. Verify the issue is closed:
   ```bash
   gh issue view 186 --repo kentonium3/kg-automation --json state
   # Expected: state=CLOSED
   ```

4. Verify the label is removed:
   ```bash
   gh issue view 186 --repo kentonium3/kg-automation --json labels
   # Expected: labels do NOT include status:in-progress
   ```

5. Verify any debt issues created:
   ```bash
   gh issue list --repo kentonium3/kg-automation --label P2-debt --state open --search "created:>=2026-05-09 type:Docs"
   # Expected: zero or more new "Docs:" issues
   ```
   Inspect each new docs-debt issue. Verify:
   - Title prefix `Docs:`
   - Six sections populated per `.github/ISSUE_TEMPLATE/docs-debt.md`
   - **Draft outline** is specific enough to act on (the FR-003 success criterion)

6. Verify the activity log:
   ```bash
   ssh office2-claude "tail -50 /home/kgale/second-brain/agents/logs/doc-auditor-$(date +%F).md"
   # Expected: an audit run entry with the canary stats
   ```

7. Append observations to `kitty-specs/felix-doc-auditor-agent-01KR7JK9/canary-log.md`:
   ```markdown
   # Canary log — felix-doc-auditor
   
   ## Run 1 — 2026-05-09 (issue #186)
   
   - Triggered by: manual delegate
   - Docs reviewed: <N>
   - WhatsApp message sent: <time>
   - Reply: `approve` / `reject` / `skip` / partial / timeout
   - Edits committed: <count> (commit: <sha>)
   - Debt issues created: <count> (#<N>, #<M>, ...)
   - Audit closed: yes/no
   - Label removed: yes/no
   - Notes / observations: <free text>
   ```

**Validation**:
- [ ] All 6 verification steps pass
- [ ] Canary log entry written
- [ ] Any debt issue created passes the "act-without-further-research" test (FR-003)

**If canary fails** (any output not as expected): STOP. Do not enable cron (T025). File issues for any deviations and re-do canary after fixing.

---

### T025 — Enable cron + restart OpenClaw

**Purpose**: Switch from canary mode to live operation. Only proceed if T024 passed cleanly.

**Steps**:

1. Edit `/home/claude/.openclaw/openclaw.json` to enable the cron entry (toggle `enabled: false` → `enabled: true`, or uncomment per convention).

2. Validate JSON:
   ```bash
   ssh office2-claude "jq . /home/claude/.openclaw/openclaw.json > /dev/null && echo OK"
   ```

3. Restart the OpenClaw cron service (per the actual service name discovered in WP05/T019 step 6):
   ```bash
   ssh office2-kgale "sudo systemctl restart openclaw-cron"
   # OR (if user-level): ssh office2-claude "systemctl --user restart openclaw-cron"
   ```

4. Confirm next scheduled run via `systemctl list-timers --all | grep openclaw` or equivalent.

5. Append to canary-log.md:
   ```markdown
   ## Cron enabled — <timestamp>
   - Cron schedule: 0 * * * *
   - Service restarted: <command used>
   - Next scheduled run: <timestamp>
   ```

**Validation**:
- [ ] JSON parses cleanly after edit
- [ ] OpenClaw cron service restarted without errors
- [ ] Next scheduled run shows up in systemctl timers

---

### T026 — Watch backlog drain (NFR-006 validation)

**Purpose**: Confirm the agent processes the remaining 5 backlog audit issues within ≤6 hours of cron-enable.

**Steps**:

1. Inventory the backlog before the next cron tick:
   ```bash
   gh issue list --repo kentonium3/kg-automation --label P2-debt --state open \
     --search "Doc audit OR Weekly doc audit" --json number,title,createdAt
   ```
   Expected: 5 open audit issues (#168, #169, #188, #192, #193 — minus #186 which canary processed).

2. Watch the next ~6 cron ticks (≥6 hours). At each tick, expect one issue to be picked up and processed. Verify:
   - The oldest unprocessed issue gets `status:in-progress`
   - Within ~5-10 minutes, it's processed (commits, debt issues, summary, close, label removed)
   - The next tick picks up the next-oldest

3. After ≤6 hours, re-run the inventory query. Expected: 0 open audit issues (all 5 processed). If any remain, investigate (stuck at status:in-progress? processing failure?) and document in the canary log.

4. Append observations to canary-log.md:
   ```markdown
   ## Backlog drain — 2026-05-09 onwards
   
   ### Pre-drain (after cron enabled at <time>)
   - Open audit issues: 5
     - #168 (2026-04-13)
     - #169 (2026-04-13)
     - #188 (2026-05-09)
     - #192 (2026-05-09)
     - #193 (2026-05-09)
   
   ### Per-tick observations
   - Tick 1 (<time>): picked up #168, processed in <duration>, closed: yes/no
   - Tick 2 (<time>): picked up #169, ...
   - Tick 3 (<time>): picked up #188, ...
   - Tick 4 (<time>): picked up #192, ...
   - Tick 5 (<time>): picked up #193, ...
   
   ### Post-drain (T+6h)
   - Open audit issues: <N>
   - NFR-006 met: yes/no
   - Notes: <observations on agent behavior, edge cases, etc.>
   ```

**Validation**:
- [ ] Inventory recorded pre-drain
- [ ] Per-tick observations recorded
- [ ] Final inventory shows 0 open audit issues OR remaining issues are documented with reasons
- [ ] NFR-006 (≤6 hours) met OR deviation explained

## Definition of Done (WP06)

- [ ] Issue #186 closed via canary with the audit summary comment + appropriate edits/debt issues
- [ ] No edits to constitution / CLAUDE.md / credentials per SC-005 (verify via `git log -p` since canary)
- [ ] Cron enabled
- [ ] All 5 remaining backlog issues processed (either via cron or, if cron failed, via manual fallback documented in canary log)
- [ ] `kitty-specs/felix-doc-auditor-agent-01KR7JK9/canary-log.md` is comprehensive
- [ ] Mission acceptance review (next phase) can verify all spec FRs/NFRs/SCs from the canary log + commits

## Risks

- **Canary surfaces a wrong proposal** — the safety net is the Level 1 approval gate. Reply `reject` and document. If repeated wrong proposals, the skill confidence rules need tightening before re-canary.
- **Backlog issues are stale** — many were created weeks ago. Their diffs reference commits that are now merged; the agent compares against current state, which is correct. But the prioritization signal (diff) is less informative.
- **NFR-006 missed** — if the drain takes >6 hours, this isn't a hard fail. Document and assess: is the polling interval too slow for the backlog density? Is the agent slow on each audit?
- **OpenClaw cron startup race** — when restarting OpenClaw cron, the next tick might fire immediately. Plan accordingly; T026 should account for this.
- **Concurrent label race** — extremely unlikely (cron ticks are 60 min apart) but if T022's canary completion overlaps with T025's cron-enable, two processes could try to claim the same issue. Mitigated by the `status:in-progress` label semantics (whoever applies it first wins).

## Reviewer guidance

A reviewer should check:
1. Canary log is comprehensive and honest about any deviations
2. SC-005 verified: `git log --since='2026-05-09' -- docs/constitution/FELIX-CONSTITUTION.md` returns no agent-authored commits
3. SC-006 verified: every commit by the agent references an audit issue; every debt issue links back; audit summaries are present
4. NFR-006 measurement: from cron enable timestamp → all backlog issues closed
5. Defensive check: the `status:in-progress` label is not currently applied to any issue (no leaks)

## Implementation command

```bash
spec-kitty agent action implement WP06 --agent <agent-name>
```

## Activity Log

- 2026-05-10T17:31:51Z – claude:opus:orchestrator:orchestrator – shell_pid=48801 – Started implementation via action command
