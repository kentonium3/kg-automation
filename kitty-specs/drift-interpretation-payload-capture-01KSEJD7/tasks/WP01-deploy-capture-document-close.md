---
work_package_id: WP01
title: 'Deploy + capture + document + close #404 (operational follow-up to mission #53)'
dependencies: []
requirement_refs:
- FR-001
- FR-002
- FR-003
- FR-004
- FR-005
- FR-006
- FR-007
- FR-008
- FR-009
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
base_branch: kitty/mission-drift-interpretation-payload-capture-01KSEJD7
base_commit: ba11f54390afcdee72671104ee2c42d1060bdc38
created_at: '2026-05-25T03:27:44.324070+00:00'
subtasks:
- T001
- T002
- T003
- T004
- T005
- T006
- T007
shell_pid: "69347"
agent: "claude:opus:python-implementer:implementer"
history:
- event: planned
  timestamp: '2026-05-25T03:25:00Z'
  note: Created by /spec-kitty.tasks under mission drift-interpretation-payload-capture-01KSEJD7
authoritative_surface: docs/
execution_mode: code_change
mission_slug: drift-interpretation-payload-capture-01KSEJD7
owned_files:
- docs/diagnostics/drift-interpretation-payload-shape.md
- docs/runbooks/doc-auditor-driver-ops.md
tags: []
---

# WP01 — Deploy + capture + document + close #404

## Objective

Complete the operational arc that mission #53's canceled WP02 was scoped to do. Deploy main (which now includes `_log_raw_response_if_debug` via `fbfe2a0f`) to office2, enable the debug env var for one tick, capture a real drift-event payload from `journalctl`, sanitize and analyze it, author `docs/diagnostics/drift-interpretation-payload-shape.md`, update the doc-auditor runbook with a short env-var note, restore office2 to clean state, and close GitHub issue #404 with findings + a follow-up fix issue (if needed).

## Context

- Mission #53 (`drift-interpretation-debug-capture`) merged at `fbfe2a0f`. The new helper `_log_raw_response_if_debug` and 11 raise-site captures are live in main.
- Mission #53's WP02 was canceled because it required the WP01 code merged-to-main; spec-kitty merges at end-of-mission only, creating a chicken-and-egg.
- All operational decisions (D1–D4) from this mission's `plan.md` apply.
- The mission spec is at [`../spec.md`](../spec.md). Plan is at [`../plan.md`](../plan.md).

## Branch Strategy

- **Planning base branch**: `main`
- **Merge target branch**: `main`
- **Execution lane**: allocated by `finalize-tasks` from `lanes.json`.
- Worktree path: from `spec-kitty agent context resolve --mission <slug> --wp WP01 --json` (`workspace_path` field).

## Detailed guidance per subtask

### T001 — Pull main to office2; verify helper present

```bash
ssh office2-claude 'cd /home/claude/kg-automation && git pull origin main'
ssh office2-claude 'grep -n "_log_raw_response_if_debug\|DOC_AUDIT_DEBUG_DRIFT_PAYLOADS" /home/claude/kg-automation/scripts/doc_audit/judgment/drift_interpretation.py | head -5'
ssh office2-claude '/data/services/openclaw/felix-doc-auditor-driver/venv/bin/python -c "from doc_audit.judgment import drift_interpretation; print(drift_interpretation._log_raw_response_if_debug)"'
```

Expected: 5+ grep hits; python `-c` prints a function repr. If not, STOP and report — main may not have the WP01 code yet.

### T002 — Add env var via systemd drop-in (non-interactive)

```bash
ssh office2-claude 'mkdir -p ~/.config/systemd/user/felix-doc-auditor.service.d/'
ssh office2-claude "cat > ~/.config/systemd/user/felix-doc-auditor.service.d/debug-capture.conf << 'EOF'
[Service]
Environment=\"DOC_AUDIT_DEBUG_DRIFT_PAYLOADS=1\"
EOF"
ssh office2-claude 'systemctl --user daemon-reload'
ssh office2-claude 'systemctl --user show felix-doc-auditor.service | grep DOC_AUDIT_DEBUG'
```

Expected: `Environment=DOC_AUDIT_DEBUG_DRIFT_PAYLOADS=1` in show output.

### T003 — Trigger one tick; extract payload

```bash
ssh office2-claude 'systemctl --user start felix-doc-auditor.service'
# Wait for retries to complete (4 attempts × ~50s delay)
sleep 270
ssh office2-claude 'journalctl --user -u felix-doc-auditor.service --since "8 minutes ago" --no-pager > /tmp/drift_tick_full.txt && grep -A 2 drift_interpretation.schema_fail /tmp/drift_tick_full.txt | head -50'
scp office2-claude:/tmp/drift_tick_full.txt /tmp/drift_tick_full.txt
```

Expected: at least one `drift_interpretation.schema_fail` line. If absent:
- Check env var is set on the service: re-run T002 verification
- Check for drift events: `ssh office2-claude 'grep -E "drift_event|RETRY_EXHAUSTED" /tmp/drift_tick_full.txt | head -10'`
- If no drift events fired, wait 5 min and retrigger (auditor's drift queue is driven by recent commits; today's session committed plenty)

### T004 — Author diagnostic doc

Inspect the capture from T003. Identify:
- Which `_RetrySchemaError` raise site fired (look at the `<error_message>` segment)
- Raw response body shape (valid JSON? markdown-wrapped? completely off-schema?)
- Root cause category: prompt regression / schema regression / model behavior change

Sanitize: redact repo paths, commit SHAs, doc-content fragments. Preserve JSON/structural shape.

Create `docs/diagnostics/drift-interpretation-payload-shape.md` IN THE WORKTREE. Mandatory sections:

```markdown
---
title: "Diagnostic: drift_interpretation payload shape (issue #404 root cause)"
doc_type: diagnostic
status: active
---
# Diagnostic: drift_interpretation payload shape (issue #404 root cause)

**Date captured**: 2026-05-24 (replace with actual capture date)
**Mission**: drift-interpretation-payload-capture-01KSEJD7
**Status**: ANALYSIS COMPLETE — follow-up fix tracked in #<issue-number>

## Captured payload (sanitized)
```json
<paste-sanitized-payload>
```

## Raise-site identification
The `_RetrySchemaError` that fired carried message: `<exact-message>`.
Raise site: `scripts/doc_audit/judgment/drift_interpretation.py:<line>` (validates `<what>`).

## Schema vs payload diff
Expected (from `_parse_verdict`):
```
<describe-expected>
```
Actual (from capture):
```
<describe-actual>
```
Diff: <one-sentence summary>.

## Root cause hypothesis
- [ ] Prompt regression
- [ ] Schema regression
- [ ] Model behavior change

Justification: <2-3 sentences>.

## Recommended follow-up fix shape
<one-paragraph>

## Next steps
1. File follow-up issue with this diagnostic as input
2. Re-enable timer once follow-up fix AND #402 land
3. Archive this doc after the fix verifies (move to docs/archive/diagnostics/)

## Discovered
2026-05-24 by claude (mission drift-interpretation-payload-capture-01KSEJD7, issue #404).
```

### T005 — Update runbook

Add to `docs/runbooks/doc-auditor-driver-ops.md` (find an env-vars or troubleshooting section; add a subsection):

```markdown
### Debug capture for drift_interpretation

`DOC_AUDIT_DEBUG_DRIFT_PAYLOADS=1` (exact match) enables raw-response logging
at each `_RetrySchemaError` raise site in `scripts/doc_audit/judgment/drift_interpretation.py`.
Off by default — enable only for diagnostic capture, never in steady-state production.
See [`../diagnostics/drift-interpretation-payload-shape.md`](../diagnostics/drift-interpretation-payload-shape.md)
for the captured-payload analysis (mission #404 follow-up).
```

### T006 — Disable env var; verify clean state

```bash
ssh office2-claude 'rm ~/.config/systemd/user/felix-doc-auditor.service.d/debug-capture.conf'
ssh office2-claude 'rmdir ~/.config/systemd/user/felix-doc-auditor.service.d/ 2>/dev/null || true'
ssh office2-claude 'systemctl --user daemon-reload'
ssh office2-claude 'systemctl --user show felix-doc-auditor.service | grep DOC_AUDIT'
# Expected: no output
ssh office2-claude 'systemctl --user is-enabled felix-doc-auditor.timer'
# Expected: disabled

# Defensive: run one more tick and confirm no capture lines
ssh office2-claude 'systemctl --user start felix-doc-auditor.service'
sleep 270
ssh office2-claude 'journalctl --user -u felix-doc-auditor.service --since "5 minutes ago" --no-pager | grep drift_interpretation.schema_fail || echo "POST_DISABLE_CLEAN"'
# Expected: POST_DISABLE_CLEAN
```

### T007 — Close #404; file follow-up fix issue

File follow-up fix issue:
```bash
gh issue create --repo kentonium3/kg-automation \
  --title "Fix drift_interpretation schema validation root cause (from #404 diagnostic)" \
  --label "P1-bug,area/felix-core,spec: brief" \
  --body "$(cat <<'EOF'
## Why this exists

Follow-up to #404. Mission `drift-interpretation-payload-capture-01KSEJD7` captured a real
payload and identified the root cause: <prompt-regression | schema-regression | model-behavior-change>.

See [`docs/diagnostics/drift-interpretation-payload-shape.md`](https://github.com/kentonium3/kg-automation/blob/main/docs/diagnostics/drift-interpretation-payload-shape.md)
for the captured payload, raise-site, schema vs. payload diff, and recommended fix shape.

## Goal

Apply the recommended fix from the diagnostic. <One-paragraph statement of the fix shape.>

## Acceptance

- Drift events return real verdicts on the vast majority of calls (< 5% schema fails)
- felix-doc-auditor.timer can be re-enabled for steady-state operation once #402 also lands

## Related

- #404 — the investigation that surfaced this
- #402 — sibling driver bug (audit_interpretation oversized diff); also blocking timer re-enable
- #403 — the crash fix that made this investigation possible
- mission #53 — shipped the debug capture code path
EOF
)"
```
Capture the new issue number (e.g., `405`).

Close #404:
```bash
gh issue close 404 --repo kentonium3/kg-automation --comment "Diagnostic captured 2026-MM-DD on office2 under mission drift-interpretation-payload-capture-01KSEJD7. Findings recorded in docs/diagnostics/drift-interpretation-payload-shape.md. Follow-up fix tracked in #<follow-up-number>."
```

## Completion sequence

```bash
cd <worktree-path>
git status
git add docs/diagnostics/drift-interpretation-payload-shape.md docs/runbooks/doc-auditor-driver-ops.md
git diff --cached
git commit -m "feat(WP01): operationalize debug capture + record findings + close #404

Captured raw drift_interpretation payload from office2 with DOC_AUDIT_DEBUG_DRIFT_PAYLOADS=1.
Diagnostic recorded at docs/diagnostics/drift-interpretation-payload-shape.md.
Runbook updated with env-var note. Office2 returned to clean state (timer still disabled).
Follow-up fix tracked in #<new-issue-number>."

spec-kitty agent tasks mark-status T001 T002 T003 T004 T005 T006 T007 --status done --mission drift-interpretation-payload-capture-01KSEJD7

spec-kitty agent tasks move-task WP01 --to for_review --mission drift-interpretation-payload-capture-01KSEJD7 --note "Diagnostic captured + docs landed + #404 closed; ready for review"
```

## Hard rules

- Stay within `owned_files`: only `docs/diagnostics/drift-interpretation-payload-shape.md` (new) and `docs/runbooks/doc-auditor-driver-ops.md` (modified). No code edits under `scripts/`.
- Always ssh as `office2-claude`; the claude user has no sudo.
- Do not commit raw LLM payloads unsanitized.
- Do not leave the timer enabled.
- If office2 is unreachable, retry once then STOP and report — don't fabricate.

## Definition of Done

- [ ] T001 — main pulled to office2; helper present
- [ ] T002 — env var set via drop-in
- [ ] T003 — payload captured from journalctl
- [ ] T004 — diagnostic doc authored with all required sections
- [ ] T005 — runbook updated
- [ ] T006 — office2 clean (no env var, timer disabled)
- [ ] T007 — #404 closed; follow-up issue filed
- [ ] WP01 transitioned to for_review

## Branch / Implement / Review Commands

```bash
spec-kitty agent action implement WP01 --agent claude:opus:python-implementer:implementer --mission drift-interpretation-payload-capture-01KSEJD7
spec-kitty agent tasks move-task WP01 --to for_review --mission drift-interpretation-payload-capture-01KSEJD7 --note "Ready for review"
spec-kitty agent action review WP01 --agent codex:gpt-5:spec-kitty-review:reviewer --mission drift-interpretation-payload-capture-01KSEJD7
```

## Activity Log

- 2026-05-25T03:27:46Z – claude:opus:python-implementer:implementer – shell_pid=69347 – Assigned agent via action command
