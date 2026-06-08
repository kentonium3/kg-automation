---
work_package_id: WP03
title: AGENTS.md edits + sibling-agent audit
dependencies:
- WP02
requirement_refs:
- FR-007
- FR-008
- FR-009
- FR-010
- FR-014
tracker_refs: []
planning_base_branch: kitty/mission-vikunja-client-and-habits-weekly-report-01KTKSFT
merge_target_branch: kitty/mission-vikunja-client-and-habits-weekly-report-01KTKSFT
branch_strategy: Planning artifacts for this mission were generated on kitty/mission-vikunja-client-and-habits-weekly-report-01KTKSFT. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into kitty/mission-vikunja-client-and-habits-weekly-report-01KTKSFT unless the human explicitly redirects the landing branch.
base_branch: kitty/mission-vikunja-client-and-habits-weekly-report-01KTKSFT
base_commit: 6b245f5165f53fcfa1bc0b3b436abd0455187853
created_at: '2026-06-08T17:10:19.507880+00:00'
subtasks:
- T014
- T015
- T016
- T017
shell_pid: "28071"
history: []
authoritative_surface: scripts/openclaw/agents/felix-admin-habits/
execution_mode: code_change
owned_files:
- scripts/openclaw/agents/felix-admin-habits/AGENTS.md
- scripts/openclaw/agents/felix-admin-habits/SOUL.md
- scripts/openclaw/agents/felix-admin-escalation/AGENTS.md
- scripts/openclaw/agents/felix-admin-tasker/AGENTS.md
tags: []
agent: "claude:sonnet:curator-carla:implementer"
---

# WP03: AGENTS.md edits + sibling-agent audit

## ⚡ Do This First: Load Agent Profile

Before reading anything else, load the agent profile assigned to this work package by running `/ad-hoc-profile-load` with the profile slug from this file's `agent_profile` frontmatter field. Apply the profile's identity, governance scope, boundaries, and initialization declaration to the rest of this session. If the field is absent, request a profile selection from the operator before proceeding.

## Objective

Wire the output-discipline Hard Rules into felix-admin-habits' weekly path and add the helper-invocation step so its WhatsApp output stops leaking internal monologue (FR-007, FR-008, Bug A). Audit felix-admin-escalation and felix-admin-tasker for the same drift class (FR-010). Confirm the cron entry exists and is documented (FR-014). Refresh felix-admin-habits' SOUL.md to reference the new behavior contract (FR-009).

This is the stochastic-surface side of the mission. WP02 produced the deterministic data; this WP makes the agent surface render it correctly and stop talking before the identity line.

## Context

- **Authority docs**: `spec.md` FR-007 to FR-010 + FR-014; `data-model.md` § HabitClassifier + WeeklyHabitReport; `contracts/weekly_report_payload.md` § Render contract.
- **Pattern reference**: `scripts/openclaw/agents/felix-admin-capture/AGENTS.md` — read the "Hard Rules" section. The output-discipline pattern (Hard Rule #1 / #2 / #3) is the template to mirror into felix-admin-habits' weekly path.
- **Recorded in memory**: `reference_felix_output_discipline_pattern.md` — 3 hard rules + 7 anti-patterns; the canonical template for this work.
- **Existing felix-admin-habits AGENTS.md**: read it end-to-end before editing. Note its structure (Identity → Lanes → Per-cron behavior → ...). The weekly-report lane is what's being modified.

## Branch Strategy

- Planning base: `main`
- Merge target: `main`
- Implementation command: `spec-kitty agent action implement WP03 --agent <name>` (depends on WP02)
- After merge, office2's sync picks up the new prompt; the next Sunday 22:00 cron tick exercises the change.

---

## Subtask T014: felix-admin-habits AGENTS.md edits

**Purpose**: Add Hard Rules + helper-invocation directive to the weekly path. Per FR-007 + FR-008.

**Steps**:
1. Read `scripts/openclaw/agents/felix-admin-habits/AGENTS.md` end-to-end. Note the current weekly-report lane's instructions.
2. Read `scripts/openclaw/agents/felix-admin-capture/AGENTS.md` Hard Rules section. Copy its **structure** (3 hard rules + 7 anti-patterns + identity-line discipline) into a new "Output Discipline" section in habits' AGENTS.md.
3. Insert the new section near the top, just after identity, BEFORE per-lane instructions. The Hard Rules apply to ALL of habits' surfaces (morning + weekly), not just one.
4. In the **weekly-report** lane specifically, add a directive that the agent MUST:
   - Invoke `python3 scripts/habits/query_active_habits_weekly.py` and consume its JSON stdout.
   - Render per `contracts/weekly_report_payload.md` § Render contract.
   - If the helper exits non-zero: emit the failure-render template (also in the contract).
   - NEVER hallucinate percentages. The JSON is authoritative.
5. Verify the morning-check-in lane's existing instructions are NOT modified (C-004 / NFR-006).

**Files**:
- `scripts/openclaw/agents/felix-admin-habits/AGENTS.md` (modified — ~40 added lines)

**Validation**:
- [ ] New "Output Discipline" section exists with 3 Hard Rules + anti-patterns
- [ ] Weekly-report lane references the helper script invocation explicitly
- [ ] Weekly-report lane references the contract document for rendering rules
- [ ] Morning-check-in lane is byte-identical to pre-mission (or only changed for shared Hard Rules placement)
- [ ] AGENTS.md `rawChars` after edits ≤ ~15K (per `reference_openclaw_gotchas.md` effective-budget memory)

---

## Subtask T015: felix-admin-habits SOUL.md refresh

**Purpose**: Surface the new behavior contract in SOUL.md so the agent's mission posture aligns. Per FR-009.

**Steps**:
1. Read `scripts/openclaw/agents/felix-admin-habits/SOUL.md`.
2. Add (or update) a section describing the weekly-report's deterministic-helper-backed nature.
3. Keep it brief — SOUL.md is mission-posture, not technical contract. Reference AGENTS.md for the operational details.
4. Make sure tone matches existing SOUL.md style.

**Files**:
- `scripts/openclaw/agents/felix-admin-habits/SOUL.md` (modified — ~5-10 added lines)

**Validation**:
- [ ] SOUL.md references the helper-backed weekly report
- [ ] References AGENTS.md for operational rules (no duplication)
- [ ] Tone consistent with existing SOUL.md content

---

## Subtask T016 [P]: felix-admin-escalation audit + edits

**Purpose**: Verify felix-admin-escalation's WhatsApp output also conforms to Hard Rules (FR-010). Patch if needed.

**Steps**:
1. Read `scripts/openclaw/agents/felix-admin-escalation/AGENTS.md` end-to-end.
2. Compare against felix-admin-capture's Hard Rules pattern.
3. Conclusion options:
   - **Already conforms** — document this in WP03's PR description ("escalation already has output discipline per X commit"). No edits needed.
   - **Missing Hard Rules** — add them, mirroring the structure from T014.
   - **Doesn't write to user-facing WhatsApp** — document this. No edits needed.
4. If `scripts/openclaw/agents/felix-admin-escalation/AGENTS.md` doesn't exist at this exact path: search via `find scripts/openclaw -name "AGENTS.md" -path "*escalation*"` and use the actual path. (Phase-0 R-005 flagged path uncertainty.)

**Files**:
- `scripts/openclaw/agents/felix-admin-escalation/AGENTS.md` (potentially modified)

**Validation**:
- [ ] Escalation's AGENTS.md was actually read (cite the path used)
- [ ] Audit conclusion is documented (in PR description AND as a brief comment in the WP completion handoff note)
- [ ] If edits made: same Hard Rules structure as habits, verified rawChars budget

---

## Subtask T017 [P]: felix-admin-tasker audit

**Purpose**: Same audit for tasker per FR-010. Patch if needed.

**Steps**:
1. Read `scripts/openclaw/agents/felix-admin-tasker/AGENTS.md` end-to-end.
2. Same analysis as T016.
3. Same path-discovery fallback if needed.
4. tasker is more likely than escalation to be in scope for output-discipline (it surfaces task summaries). Bias toward adding Hard Rules unless analysis clearly shows it doesn't render to a user-facing channel.

**Files**:
- `scripts/openclaw/agents/felix-admin-tasker/AGENTS.md` (potentially modified)

**Validation**:
- [ ] Tasker's AGENTS.md was actually read (cite the path used)
- [ ] Audit conclusion is documented
- [ ] If edits made: same Hard Rules structure, rawChars budget verified

---

## Definition of Done

- [ ] All 4 subtasks complete with their validation items checked.
- [ ] No changes to `scripts/openclaw/agents/felix-admin-capture/` or `scripts/openclaw/agents/felix-admin-habits/` morning-check-in content (capture is the pattern source; habits' morning path is C-004 invariant).
- [ ] All modified AGENTS.md files pass the `wc -c` sanity check (≤15K source per file, per `reference_openclaw_gotchas.md`).
- [ ] If escalation or tasker audits identified no required edits, that conclusion is captured in a brief 2-3 line note in the WP completion handoff.

## Risks

1. **Stale openclaw cache** — per `reference_openclaw_gotchas.md`, openclaw's systemPromptReport caches at session-init. The edits won't take effect until the next agent process start. Mitigation: document this in the PR description so smoke-test reviewer knows the first weekly tick might still show old behavior if openclaw didn't restart. (Operator-side: post-merge sync should restart the systemd unit.)
2. **rawChars inflation** — the openclaw gotchas memory recorded ~26% inflation. Stay well below the 20K nominal budget; target ≤15K source per AGENTS.md.
3. **Path drift between docs and reality** — phase-0 surfaced that not all expected `AGENTS.md` paths exist. T016/T017 must search-and-confirm before editing. Don't trust the paths in this WP file literally if `find` returns a different one.

## Reviewer guidance

- Reviewer verifies the new "Output Discipline" section was actually copied from felix-admin-capture (not paraphrased into something weaker).
- Reviewer verifies the morning-check-in lane is unchanged in any way that could affect behavior.
- Reviewer reads escalation + tasker audit conclusions and either accepts or pushes back.
- Reviewer runs `wc -c scripts/openclaw/agents/felix-admin-habits/AGENTS.md` and confirms <15000.
- Reviewer flags if any of the modified prompt files have lost their `Sent by <agent>:<model>` identity-line pattern.

## Activity Log

- 2026-06-08T17:10:22Z – claude:sonnet:curator-carla:implementer – shell_pid=28071 – Assigned agent via action command
