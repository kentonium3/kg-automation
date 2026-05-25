---
work_package_id: WP02
title: 'Deploy WP01 to office2, capture payload, document findings, close #404'
dependencies:
- WP01
requirement_refs:
- FR-007
- FR-008
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks:
- T007
- T008
- T009
- T010
- T011
- T012
- T013
history:
- event: planned
  timestamp: '2026-05-25T02:42:46Z'
  note: Created by /spec-kitty.tasks under mission drift-interpretation-debug-capture-01KSEFT8
authoritative_surface: docs/
execution_mode: code_change
mission_slug: drift-interpretation-debug-capture-01KSEFT8
owned_files:
- docs/diagnostics/drift-interpretation-payload-shape.md
- docs/runbooks/doc-auditor-driver-ops.md
tags: []
---

# WP02 — Deploy WP01 to office2, capture payload, document findings, close #404

## Objective

Operationalize the WP01 code change. Pull `main` (including the WP01 merge) onto office2, enable the debug env var for one tick, capture a real drift-event payload from `journalctl`, author the diagnostic doc with root-cause analysis, update the doc-auditor runbook, disable the env var, and close GitHub issue #404 with a summary comment + link to the diagnostic doc. File a follow-up fix issue if the analysis reveals one is needed.

This is the WP that delivers the mission's user-visible value: a recorded payload + root-cause hypothesis that informs the next step.

## Context

- WP01 ships the code path. WP02 makes it produce diagnostic output and records the findings.
- The mission charter restricts long-term timer enablement: the timer was disabled at ~05:00 UTC 2026-05-24 during #403 triage and must stay disabled until both #404 (this mission) and #402 land. WP02 enables for **one tick only**.
- The full operator runbook for this WP is at [`../quickstart.md`](../quickstart.md). Read it as the canonical sequence — this WP prompt restates it in WP-execution language.
- The diagnostic doc template uses the operational-analysis convention (no `xx_` prefix, slug-only filename) per [research.md R7](../research.md).
- The follow-up fix issue, if needed, is filed with `P1-bug` + `area/felix-core` + `spec: brief` (matching how #404 was originally captured).

## Branch Strategy

- **Planning base branch**: `main`
- **Merge target branch**: `main`
- **Execution lane**: depends on WP01. After WP01 merges, this WP's lane (likely the same lane or a follow-on) is allocated by `finalize-tasks`. The lane worktree path comes from `spec-kitty agent context resolve --mission <slug> --wp WP02 --json` after WP01 is in `approved`/`done`.
- Do NOT begin WP02 work until WP01 is approved and merged. Spec-kitty's dependency enforcement should already block this, but confirm via `spec-kitty agent tasks status --mission drift-interpretation-debug-capture-01KSEFT8` before starting.

## Detailed guidance per subtask

### T007 — Pull `main` to office2; verify new helper symbol present

**Purpose**: Get the WP01 code change onto office2's working tree at `/home/claude/kg-automation` so the next debug-enabled tick actually exercises the new capture path.

**Steps**:
1. SSH to office2 as the `claude` user and pull `main`:
   ```bash
   ssh office2-claude 'cd /home/claude/kg-automation && git pull origin main'
   ```
   Expect a fast-forward to include the WP01 merge commit.

2. Verify the helper symbol is present:
   ```bash
   ssh office2-claude 'grep -n "_log_raw_response_if_debug\|DOC_AUDIT_DEBUG_DRIFT_PAYLOADS" /home/claude/kg-automation/scripts/doc_audit/judgment/drift_interpretation.py'
   ```
   Expect at least 2 hits (function definition + env var constant).

3. Verify the deployed venv resolves the import correctly (paranoid double-check that the venv isn't using a stale .pyc):
   ```bash
   ssh office2-claude '/data/services/openclaw/felix-doc-auditor-driver/venv/bin/python -c "from doc_audit.judgment import drift_interpretation; print(drift_interpretation._log_raw_response_if_debug)"'
   ```
   Expect a function-object repr in the output.

**Files**: none (verification only).

**Validation**:
- [ ] `main` pulled to `/home/claude/kg-automation` on office2
- [ ] Helper symbol present per grep
- [ ] Helper symbol importable from venv per python `-c` test

### T008 — Add `DOC_AUDIT_DEBUG_DRIFT_PAYLOADS=1` env var via systemctl --user edit

**Purpose**: Set the env var on the `felix-doc-auditor.service` unit so the next tick reads it.

**Steps**:
1. Edit the unit drop-in:
   ```bash
   ssh office2-claude 'systemctl --user edit felix-doc-auditor.service'
   ```
   This opens an editor over the drop-in file at `~/.config/systemd/user/felix-doc-auditor.service.d/override.conf` (or similar). Add:
   ```ini
   [Service]
   Environment="DOC_AUDIT_DEBUG_DRIFT_PAYLOADS=1"
   ```
   Save and exit.

2. Reload the systemd user manager:
   ```bash
   ssh office2-claude 'systemctl --user daemon-reload'
   ```

3. Verify the env var is in the unit's effective configuration:
   ```bash
   ssh office2-claude 'systemctl --user show felix-doc-auditor.service | grep DOC_AUDIT_DEBUG'
   ```
   Expect: `Environment=DOC_AUDIT_DEBUG_DRIFT_PAYLOADS=1`.

**Files**: none (systemd drop-in on office2, not committed to repo).

**Validation**:
- [ ] `systemctl --user show ...` reports the env var

### T009 — Trigger one tick; extract captured payload from journalctl

**Purpose**: Run the doc-auditor once with the env var enabled to capture a real failure.

**Steps**:
1. Trigger the service (one-shot):
   ```bash
   ssh office2-claude 'systemctl --user start felix-doc-auditor.service'
   ```
   The service runs synchronously to completion (it's a `Type=oneshot` unit driven by the timer normally).

2. Wait ~30s for the service to finish (it has retry delays of (30, 60, 120) seconds, so a failing call may take ~3.5 min total).

3. Tail the journal for the captured payload:
   ```bash
   ssh office2-claude 'journalctl --user -u felix-doc-auditor.service --since "10 minutes ago" --no-pager | grep -A 2 drift_interpretation.schema_fail'
   ```
   Expect at least one line of the form:
   ```
   ... WARNING ... drift_interpretation.schema_fail | <error_message> | <raw_response_body>...
   ```

4. If no capture line appears:
   - Check the env var is actually in the unit (re-run the `systemctl show` from T008).
   - Check whether the tick encountered a drift event at all:
     ```bash
     ssh office2-claude 'journalctl --user -u felix-doc-auditor.service --since "10 minutes ago" --no-pager | grep "drift_event\|RETRY_EXHAUSTED"'
     ```
   - If no drift event, file an investigation note in the diagnostic doc explaining the tick had no drift-eligible signal, then trigger again after a drift-eligible commit lands.

5. Save the captured output locally for analysis:
   ```bash
   ssh office2-claude 'journalctl --user -u felix-doc-auditor.service --since "10 minutes ago" --no-pager > /tmp/drift_capture_raw.txt'
   scp office2-claude:/tmp/drift_capture_raw.txt /tmp/drift_capture_raw.txt
   ```

**Files**: none in repo (`/tmp/drift_capture_raw.txt` on Mac is transient).

**Validation**:
- [ ] At least one `drift_interpretation.schema_fail` line in the journal
- [ ] Captured payload pulled to local Mac for analysis

### T010 — Author `docs/diagnostics/drift-interpretation-payload-shape.md`

**Purpose**: Record the findings so future engineers (or the same engineer in a future session) can pick up the follow-up fix without re-running the capture.

**Steps**:
1. Inspect the captured payload from T009. Identify:
   - Which `_RetrySchemaError` raise site fired (look at the `<error_message>` segment of the log line)
   - The raw response body shape (is it valid JSON? markdown-wrapped? completely off-schema?)
   - The candidate root cause: prompt regression / schema regression / model behavior change

2. Sanitize the payload if it contains repo-specific content (commit messages, file paths, or doc text):
   - Replace specific paths with placeholders (`<repo-root>`, `<file-path>`)
   - Hash or redact any commit SHAs
   - Keep the JSON/structural shape intact (that's the diagnostic value)

3. Create `docs/diagnostics/drift-interpretation-payload-shape.md` with the following structure:

   ```markdown
   ---
   title: "Diagnostic: drift_interpretation payload shape (issue #404 root cause)"
   doc_type: diagnostic
   status: active
   ---
   # Diagnostic: drift_interpretation payload shape (issue #404 root cause)

   **Date captured**: 2026-MM-DD
   **Mission**: drift-interpretation-debug-capture-01KSEFT8
   **Captured by**: <implementer agent / human operator>
   **Status**: ANALYSIS COMPLETE — follow-up fix tracked in #<issue-number>

   ## Captured payload (sanitized)

   ```json
   <pasted-payload-here>
   ```

   ## Raise-site identification

   The `_RetrySchemaError` that fired carried message: `<exact-message-from-log>`.
   This corresponds to the raise site at `scripts/doc_audit/judgment/drift_interpretation.py:<line-number>`,
   which validates `<what-the-check-validates>`.

   ## Schema vs. payload diff

   Expected shape (from `_parse_verdict`):
   ```
   <describe-expected>
   ```

   Actual shape (from capture):
   ```
   <describe-actual>
   ```

   Diff: <one-sentence summary of where they differ>.

   ## Root cause hypothesis

   <Pick one and justify:>
   - [ ] Prompt regression — recent edit to the prompt shifted the LLM's response shape
   - [ ] Schema regression — recent edit to `_parse_verdict` tightened validation
   - [ ] Model behavior change — upstream Anthropic API change

   Justification: <2-3 sentences explaining the evidence>.

   ## Recommended follow-up fix shape

   <One paragraph describing what the next mission should do, e.g.:>
   - If prompt regression: revert the offending prompt commit, OR add a normalization step that handles the new shape
   - If schema regression: tighten the prompt to match the schema, OR loosen the schema where reasonable
   - If model behavior change: switch model, OR add a parsing/normalization layer

   ## Next steps

   1. File follow-up issue (or update an existing one) with this diagnostic as the input
   2. Re-enable the timer once the follow-up fix lands AND #402 lands
   3. Archive this diagnostic doc after the fix verifies (move to `docs/archive/diagnostics/`)

   ## Discovered

   2026-MM-DD by <agent/operator> during mission `drift-interpretation-debug-capture-01KSEFT8` (issue #404).
   ```

4. Fill in every placeholder with concrete content from the actual capture.

**Files**:
- `docs/diagnostics/drift-interpretation-payload-shape.md` (new)

**Validation**:
- [ ] Document exists at the expected path with all sections filled
- [ ] Sanitized payload preserved enough structure for diagnosis
- [ ] Root cause hypothesis is one of the three categories, with justification
- [ ] Follow-up recommendation is concrete enough for someone to file an issue from

### T011 — Add one-line note about env var to `docs/runbooks/doc-auditor-driver-ops.md`

**Purpose**: The new env var is an operational knob; future operators need to know it exists.

**Steps**:
1. Open `docs/runbooks/doc-auditor-driver-ops.md`.
2. Find the section that describes service env vars or operational toggles. If no such section exists, add a small subsection near the troubleshooting or "advanced operations" area.
3. Add (or extend) a short note:
   ```markdown
   ### Debug capture for drift_interpretation

   `DOC_AUDIT_DEBUG_DRIFT_PAYLOADS=1` (exact match) enables raw-response logging
   at each `_RetrySchemaError` raise site in `scripts/doc_audit/judgment/drift_interpretation.py`.
   Off by default — enable only for diagnostic capture, never in steady-state production.
   See [`../diagnostics/drift-interpretation-payload-shape.md`](../diagnostics/drift-interpretation-payload-shape.md)
   for the captured-payload analysis (mission #404).
   ```

**Files**:
- `docs/runbooks/doc-auditor-driver-ops.md` (modified — small addition)

**Validation**:
- [ ] Runbook has a short, accurate note about the env var
- [ ] Note links to the diagnostic doc from T010

### T012 — Disable env var on office2; verify clean state; confirm timer still disabled

**Purpose**: Return office2 to the pre-mission steady state.

**Steps**:
1. Remove the env var drop-in:
   ```bash
   ssh office2-claude 'systemctl --user edit felix-doc-auditor.service'
   ```
   Remove the `Environment="DOC_AUDIT_DEBUG_DRIFT_PAYLOADS=1"` line. Save and exit.

2. Reload:
   ```bash
   ssh office2-claude 'systemctl --user daemon-reload'
   ```

3. Confirm clean:
   ```bash
   ssh office2-claude 'systemctl --user show felix-doc-auditor.service | grep DOC_AUDIT'
   ```
   Expect no matching lines.

4. Confirm timer is still disabled:
   ```bash
   ssh office2-claude 'systemctl --user is-enabled felix-doc-auditor.timer'
   ```
   Expect: `disabled`.

5. Trigger one more tick (defensive — confirm the now-clean code path doesn't produce capture lines):
   ```bash
   ssh office2-claude 'systemctl --user start felix-doc-auditor.service'
   ssh office2-claude 'journalctl --user -u felix-doc-auditor.service --since "2 minutes ago" --no-pager | grep drift_interpretation.schema_fail'
   ```
   Expect: no matching lines.

**Files**: none (operational verification only).

**Validation**:
- [ ] Env var no longer in unit configuration
- [ ] Timer is disabled
- [ ] A post-disable tick produces zero `drift_interpretation.schema_fail` lines

### T013 — Close #404 with summary comment + diagnostic doc link; file follow-up fix issue if needed

**Purpose**: Tie the mission deliverable back to the GitHub issue queue and signal the next action.

**Steps**:
1. File the follow-up fix issue (if the diagnostic indicates a fix is needed — almost certainly yes):
   ```bash
   gh issue create --repo kentonium3/kg-automation \
     --title "Fix drift_interpretation schema validation root cause (from #404 diagnostic)" \
     --label "P1-bug,area/felix-core,spec: brief" \
     --body "$(cat <<'EOF'
   ## Why this exists

   Follow-up to #404. Mission `drift-interpretation-debug-capture-01KSEFT8` captured a real
   payload and identified the root cause: <prompt-regression | schema-regression | model-behavior-change>.

   See [`docs/diagnostics/drift-interpretation-payload-shape.md`](https://github.com/kentonium3/kg-automation/blob/main/docs/diagnostics/drift-interpretation-payload-shape.md)
   for the captured payload, raise-site, schema vs. payload diff, and recommended fix shape.

   ## Goal

   Apply the recommended fix from the diagnostic. <One-paragraph statement of the fix shape.>

   ## Acceptance

   - Drift events return real verdicts on the vast majority of calls (< 5% schema fails)
   - `felix-doc-auditor.timer` can be re-enabled for steady-state operation once #402 also lands

   ## Related

   - #404 — the investigation that surfaced this
   - #402 — sibling driver bug (audit_interpretation oversized diff); also blocking timer re-enable
   - #403 — the crash fix that made this investigation possible
   EOF
   )"
   ```
   Capture the issue number returned (e.g., `405`).

2. Close #404 with a summary comment:
   ```bash
   gh issue close 404 --repo kentonium3/kg-automation --comment "Diagnostic captured 2026-MM-DD on office2 under mission drift-interpretation-debug-capture-01KSEFT8. Findings recorded in docs/diagnostics/drift-interpretation-payload-shape.md. Follow-up fix tracked in #<follow-up-issue-number>."
   ```

3. If the diagnostic surprisingly reveals NO fix is needed (extremely unlikely but possible — e.g., the prompt was already adjusted in an unmerged branch), close #404 with that conclusion and skip the follow-up issue.

**Files**: none in repo (GitHub state only).

**Validation**:
- [ ] Follow-up fix issue filed (or explicit decision to skip recorded in the closure comment)
- [ ] Issue #404 closed
- [ ] Closure comment links to the diagnostic doc
- [ ] Cross-references between #404, the new issue, and the diagnostic doc are bidirectional

## Test Strategy

No automated tests for this WP — it's operational + documentation work. The "test" is the diagnostic doc existing with a complete root-cause analysis and the issue being closed with the right cross-references.

## Definition of Done

- [ ] All 7 subtasks complete (T007–T013)
- [ ] `docs/diagnostics/drift-interpretation-payload-shape.md` exists on `main` with all sections filled
- [ ] `docs/runbooks/doc-auditor-driver-ops.md` has a one-line note about the env var
- [ ] Office2 env var is disabled; timer is disabled; post-disable tick produces no capture lines
- [ ] GitHub issue #404 is closed with a summary comment linking to the diagnostic doc
- [ ] Follow-up fix issue is filed (with #404 cross-reference) OR explicit rationale recorded in #404 closure
- [ ] WP02 lane transitioned to `for_review`

## Risks

- **Tailscale outage during ssh sessions** — multiple ssh round-trips. If Tailscale drops, retry; if persistent, the WP stalls until connectivity returns. Document the stall in the WP's status notes.
- **No drift event during the trigger tick** — if the doc-auditor queue is empty of drift-eligible signals, the capture produces nothing. Workaround: land any small commit touching `docs/` or `scripts/` on `main` before triggering, to ensure a drift signal exists.
- **Payload truncation discards key signal** — if the captured response exceeds 4096 bytes and the diagnostic JSON shape isn't visible in the first 4KB, bump the truncation limit (in WP01's code) and re-deploy. This would technically be a WP01 follow-up; flag in the WP02 status notes and consider whether to re-open WP01 or hot-patch.
- **Diagnostic ambiguity** — the capture may not be unambiguous about which of the three root-cause categories applies. If so, the diagnostic doc records the ambiguity, the follow-up issue inherits the uncertainty, and the next mission's first move is further investigation.

## Reviewer Guidance

Focus on:
1. **Diagnostic doc completeness** — every section filled, sanitization sensible, root cause hypothesis with justification, recommended fix shape concrete enough to act on.
2. **Office2 clean state** — verify T012's checks passed (env var removed, timer disabled, no capture lines on post-disable tick).
3. **GitHub state hygiene** — #404 closed with the right comment; follow-up issue filed with the right labels and cross-references.
4. **Runbook note** — short, accurate, links to the diagnostic.

Do NOT focus on:
- The choice of root cause (the implementer made a judgment call from the evidence; reviewer can disagree and discuss in the follow-up issue, not block this WP)
- The exact wording of the follow-up issue body (any reasonable shape is fine)

## Branch / Implement / Review Commands

```bash
# Implement (after WP01 is in `approved`/`done`)
spec-kitty agent action implement WP02 --agent claude --mission drift-interpretation-debug-capture-01KSEFT8

# After committing in the worktree (docs only), transition to for_review
spec-kitty agent tasks move-task WP02 --to for_review --note "Diagnostic captured + docs landed; ready for review"

# Review (claimed by codex with the spec-kitty-review profile)
spec-kitty agent action review WP02 --agent codex:gpt-5:spec-kitty-review:reviewer --mission drift-interpretation-debug-capture-01KSEFT8
```
