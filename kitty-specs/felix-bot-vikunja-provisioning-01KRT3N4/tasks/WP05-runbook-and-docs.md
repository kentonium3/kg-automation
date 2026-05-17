---
work_package_id: WP05
title: Operator runbook + 4 architecture doc updates
dependencies:
- WP03
requirement_refs:
- FR-009
- FR-010
- FR-011
- FR-012
- FR-013
- NFR-006
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks:
- T020
- T021
- T022
- T023
- T024
agent: "codex:gpt-4o:python-reviewer:reviewer"
shell_pid: "80021"
history:
- action: drafted
  agent: claude
  timestamp: '2026-05-17T05:30:00Z'
authoritative_surface: docs/runbooks/felix-bot-vikunja-provisioning.md
execution_mode: code_change
mission_slug: felix-bot-vikunja-provisioning-01KRT3N4
owned_files:
- docs/runbooks/felix-bot-vikunja-provisioning.md
- docs/design/architecture/data/credential-manifest.json
- docs/design/architecture/credentials-and-secrets.md
- docs/design/architecture/identity-model.md
- docs/design/architecture/data/service-inventory.json
tags: []
---

# WP05 — Operator runbook + architecture doc updates

## Objective

Write the operator-facing runbook that sequences the four helpers from WP01-WP04, and update the four architecture documentation files to reflect felix-bot ownership. The runbook is the operator's primary reference during execution; the doc updates are the audit trail of the rotation.

## Context

- **Spec section**: FR-009 (cron verification documented in runbook), FR-010-FR-013 (doc updates), NFR-006 (soak monitoring documented).
- **Design rationale**: [research.md](../research.md) R-007 (doc updates committed after WP03 succeeds, before soak completes).
- **Quickstart**: [quickstart.md](../quickstart.md) is the one-page operator quick reference. The runbook is the full procedural document with GO/NO-GO criteria at each phase boundary.
- **Constraint**: All 4 doc files must be updated in a single commit per spec C-003 to prevent drift between authoritative JSON and narrative views.
- **Doc conventions** (per existing repo style):
  - `credential-manifest.json` is the authoritative JSON store for credentials; `credentials-and-secrets.md` is the narrative view
  - `identity-model.md` documents per-identity (human, agent, bot) scope and permissions
  - `service-inventory.json` is the machine-readable service catalog

## Branch strategy

Planning branch: `main`. Final merge target: `main`. Execution worktree allocated per computed lane in `lanes.json` after task finalization.

## Subtask guidance

### T020 — Write docs/runbooks/felix-bot-vikunja-provisioning.md (6-phase runbook with GO/NO-GO)

**Purpose**: The runbook is the operator's procedural reference. Detailed enough to follow without ambiguity; structured with explicit GO/NO-GO criteria at each phase boundary.

**Steps**:

1. Create `docs/runbooks/felix-bot-vikunja-provisioning.md` with the standard kg-automation runbook frontmatter:
   ```
   ---
   title: felix-bot Vikunja Provisioning
   doc_type: runbook
   status: approved
   audience: operator
   last_updated: 2026-05-17
   ---
   ```
2. Structure into six phases plus pre-flight:

   - **Pre-flight** — Required conditions before starting (Restic backup, Kent presence, dependent services baseline)
   - **Phase 1 — Provision** — Run `provision_felix_bot.py`. Document exact invocation, expected SUMMARY output, password handling, token capture flow. GO criteria: SUMMARY line confirms 12 projects shared.
   - **Phase 2 — Validate** — Run `validate_felix_bot.py`. Expected: all 12 projects accessible, attribution verified, throwaway task cleaned up, rollback smoke test passed. GO criteria: exit 0 + SUMMARY line. **NO-GO**: any validation failure halts here; production state is untouched.
   - **Phase 3 — Swap** — Run `swap_vikunja_secrets.py`. Expected: backup written, secrets rotated, gateway restarted, post-swap attribution verified. Automatic rollback on failure. GO criteria: SUMMARY line confirms attribution=felix-bot. **Rollback path**: documented inline.
   - **Phase 4 — Doc commit** — On the Mac, edit and commit the 4 architecture doc updates (which were written ahead of time during this WP's implementation). Push to main.
   - **Phase 5 — 7-day soak** — Daily monitoring. Documented checks per cron: habits-morning-checkin, escalation-daily, inbox-*. Documented log inspection commands. If any cron fails with auth errors during soak, **rollback** procedure (Phase 3 inverse) and investigate.
   - **Phase 6 — Cleanup** — Run `revoke_kent_tokens.py`. Remove `.bak` file. Close GitHub issue #304.

3. Each phase section must include:
   - Estimated duration
   - Exact command(s) to run, with placeholder values for operator inputs
   - Expected output (literal SUMMARY line format)
   - GO criteria (checkboxes the operator marks complete)
   - NO-GO / rollback trigger
   - Inline references to applicable spec FRs/NFRs

4. Include a final section "Success criteria checklist" that mirrors spec SC-001 through SC-007.

5. Length target: 300-400 lines of markdown. Concise but complete.

**Files**:
- `docs/runbooks/felix-bot-vikunja-provisioning.md` (new)

**Validation**:
- `markdownlint docs/runbooks/felix-bot-vikunja-provisioning.md` passes (or has only acceptable warnings)
- Manual review: an operator who has never seen this mission should be able to execute it end-to-end using only this runbook + the helper `--help` outputs

### T021 — Update credential-manifest.json vikunja-api entry

**Purpose**: Update the authoritative JSON manifest to reflect felix-bot ownership of the `vikunja-api` credential.

**Steps**:

1. Read the existing `vikunja-api` entry in `docs/design/architecture/data/credential-manifest.json`.
2. Update the following fields:
   - `last_reviewed`: change to the rotation date (use the execution date — for the spec this is a placeholder `<rotation-date>`; the actual date is set when the operator commits during Phase 4)
   - `updated_by`: prepend `#304-felix-bot-rotation` to the existing list (preserve historical chain)
   - `notes`: update text to mention felix-bot owns this token; reference issue #304 and ADR-0002 Phase 1
3. Top-level fields (`last_updated`, `updated_by` at file level) — bump similarly.
4. Validate the resulting file: `python3 -c "import json; json.load(open('docs/design/architecture/data/credential-manifest.json'))"` succeeds.

**Files**:
- `docs/design/architecture/data/credential-manifest.json` (modified)

**Validation**:
- JSON parses successfully
- `vikunja-api` entry references felix-bot in its `notes`
- `updated_by` chain preserves prior history
- Other entries in the manifest are unchanged

### T022 — Update credentials-and-secrets.md narrative

**Purpose**: Update the narrative view to mirror the JSON authoritative source. Per spec C-003 these must be in the same commit.

**Steps**:

1. Read the existing `docs/design/architecture/credentials-and-secrets.md`.
2. Bump frontmatter:
   - `last_updated`: rotation date (placeholder during implementation; actual date during operator commit)
   - `updated_by`: prepend `#304-felix-bot-rotation`
3. Update the Active Credentials table row for `vikunja-api`:
   - Reflect felix-bot ownership in the "Used By" or "Notes" column
   - If there's a column tracking the owning identity, update it
4. Section 3 "Scoped plaintext files (mode 600)" narrative — if it references `kent` as the owning identity of `vikunja-api`, update to `felix-bot`.
5. Run markdownlint; fix any new warnings introduced.

**Files**:
- `docs/design/architecture/credentials-and-secrets.md` (modified)

**Validation**:
- Markdown lints cleanly
- Active credentials table reflects felix-bot
- Narrative descriptions reference felix-bot
- Cross-references to credential-manifest.json remain valid

### T023 — Update identity-model.md Agent Service Accounts

**Purpose**: Add felix-bot (Vikunja) to the Agent Service Accounts section. Aligns with the existing kg-felix-bot (GitHub) entry.

**Steps**:

1. Read `docs/design/architecture/identity-model.md`.
2. Locate the "Agent Service Accounts" section (or equivalent — confirm the section name at implementation time).
3. Add a new row/entry for `felix-bot` (Vikunja):
   - Identity: `felix-bot`
   - Surface: Vikunja v0.24.6 on office2
   - Scope: All Felix sub-agent API writes; R/W on 12 projects
   - Created by: #304 / ADR-0002 Phase 1
   - Email: kentgale+felix-bot@gmail.com
   - Password storage: 1Password (no on-disk copy)
   - TOTP: not enabled (per ADR-0002 Q5c)
4. Cross-reference `kg-felix-bot` entry to clarify the two identities are distinct (one for GitHub, one for Vikunja).
5. Bump frontmatter `last_updated`.

**Files**:
- `docs/design/architecture/identity-model.md` (modified)

**Validation**:
- Markdown lints cleanly
- felix-bot row/entry is structurally consistent with the existing kg-felix-bot entry
- No accidental edit to the kg-felix-bot entry

### T024 — Verify + optionally update service-inventory.json

**Purpose**: If the `vikunja` service entry tracks per-user accounts in service-inventory.json, add felix-bot to that list. If not, this is a no-op.

**Steps**:

1. Read `docs/design/architecture/data/service-inventory.json`.
2. Locate the `vikunja` service entry.
3. Check if the entry has an `accounts`, `users`, `identities`, or similar field that tracks Vikunja users. If yes:
   - Add `felix-bot` to that list
   - Bump entry-level `last_updated` if present
4. If no such field exists in the schema today:
   - This subtask is a no-op
   - Document this in the commit message ("service-inventory.json verified; vikunja entry does not track user accounts today; no-op")
5. Top-level `last_updated` and `updated_by` bumped similarly to T021.
6. Validate JSON parses.

**Files**:
- `docs/design/architecture/data/service-inventory.json` (possibly modified; possibly verified-only)

**Validation**:
- JSON parses successfully
- If updated, felix-bot appears in the relevant vikunja account list
- If not updated, the commit message explicitly notes the no-op and why

## Test strategy

This WP produces documentation only — no code, no tests. Validation is via:

1. Markdownlint on the runbook and any narrative files
2. JSON validation on the manifest files
3. Manual review: the runbook should be readable end-to-end by an operator who has never seen this mission

## Definition of Done

- [ ] `docs/runbooks/felix-bot-vikunja-provisioning.md` exists, ~300-400 lines, 6 phases + pre-flight + success criteria checklist
- [ ] Each phase in the runbook has: exact commands, expected output format, GO/NO-GO criteria, rollback trigger
- [ ] Runbook references all 4 helpers from WP01-WP04 with their final invocation syntax
- [ ] `credential-manifest.json` `vikunja-api` entry updated (`last_reviewed`, `updated_by`, `notes`)
- [ ] `credentials-and-secrets.md` Active Credentials table + narrative reflect felix-bot ownership
- [ ] `identity-model.md` Agent Service Accounts includes felix-bot (Vikunja) entry
- [ ] `service-inventory.json` either updated (if vikunja entry tracks users) or explicitly verified as no-op
- [ ] All 4 doc updates parse/lint cleanly
- [ ] No accidental edits outside the targeted sections

## Risks

- **Doc schema drift**: If `credential-manifest.json` schema changed since the spec was written, follow the current schema. Confirm at implementation time.
- **Runbook quality affects operator success**: A poorly-structured runbook causes execution mistakes. Review by re-reading as if you were the operator. GO/NO-GO criteria should be objective and verifiable.
- **Placeholder dates**: The doc updates use a placeholder for the rotation date during WP implementation. The actual date is set when the operator commits during Phase 4 of the runbook. This is by design — do NOT hardcode today's date.

## Reviewer guidance (for Codex review)

- Verify the runbook has clear GO/NO-GO criteria at every phase boundary (not just success criteria).
- Verify the runbook's helper invocation syntax matches the actual argparse interfaces from WP01-WP04 (cross-check against those WPs' DoD).
- Verify JSON files parse and the schema is preserved (only fields stated in the subtask are modified; other fields untouched).
- Verify markdown files lint cleanly with no new warnings introduced.
- Verify the `updated_by` chains are preserved (no accidental overwrite of historical attribution).
- Verify the runbook does NOT reference any helper command that doesn't exist in WP01-WP04 (no aspirational commands).
- Verify the rollback procedure in the runbook is internally consistent with `swap_vikunja_secrets.py --rollback-from-bak` syntax.
- Confirm identity-model.md additions follow the existing entry structure (don't invent new fields).

## Implementation command

```bash
spec-kitty agent action implement WP05 --mission felix-bot-vikunja-provisioning-01KRT3N4 --agent <tool>:<model>:<profile>:<role>
```

## Review command

```bash
spec-kitty agent action review WP05 --mission felix-bot-vikunja-provisioning-01KRT3N4 --agent codex:gpt-4o:python-reviewer:reviewer
```

## Activity Log

- 2026-05-17T05:42:45Z – claude:opus-4-7:python-implementer:implementer – shell_pid=73776 – Started implementation via action command
- 2026-05-17T05:49:04Z – claude:opus-4-7:python-implementer:implementer – shell_pid=73776 – Ready for review — operator runbook + 4 architecture doc updates
- 2026-05-17T05:49:38Z – codex:gpt-4o:python-reviewer:reviewer – shell_pid=75323 – Started review via action command
- 2026-05-17T05:57:03Z – codex:gpt-4o:python-reviewer:reviewer – shell_pid=75323 – Moved to planned
- 2026-05-17T05:57:19Z – claude:opus-4-7:python-implementer:implementer – shell_pid=77115 – Started implementation via action command
- 2026-05-17T06:01:57Z – claude:opus-4-7:python-implementer:implementer – shell_pid=77115 – Cycle 2 — addressed all 4 Codex findings: Phase 2 invocation includes --token-file; Phase 2 + Phase 3 SUMMARY expectations match actual helper output; SC-002 wording corrected to single-target write probe.
- 2026-05-17T06:02:30Z – codex:gpt-4o:python-reviewer:reviewer – shell_pid=78397 – Started review via action command
- 2026-05-17T06:06:44Z – codex:gpt-4o:python-reviewer:reviewer – shell_pid=78397 – Moved to planned
- 2026-05-17T06:06:48Z – claude:opus-4-7:python-implementer:implementer – shell_pid=79373 – Started implementation via action command
- 2026-05-17T06:08:48Z – claude:opus-4-7:python-implementer:implementer – shell_pid=79373 – Cycle 3 — Phase 6 SUMMARY block added per ground-truth from grep -nE 'SUMMARY:' scripts/vikunja/revoke_kent_tokens.py; 4 variants documented (ui_fallback, dry-run, zero-tokens, revoked-N).
- 2026-05-17T06:09:06Z – codex:gpt-4o:python-reviewer:reviewer – shell_pid=80021 – Started review via action command
