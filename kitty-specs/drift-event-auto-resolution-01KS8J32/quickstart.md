# Quickstart: Drift event auto-resolution cutover

**Mission**: `drift-event-auto-resolution-01KS8J32`
**Risk tier**: Tier 3 — Logic / Workflow

Operator-facing cutover guide. Follow in order on deploy day. Each section is independently verifiable; do not skip the verification steps.

---

## 0. Pre-flight (10 min)

Run on the Mac (project root):

```bash
cd /Users/kentgale/repos/kg-automation
git status                                  # should be clean on main
gh issue view 362 --repo kentonium3/kg-automation --json state,labels  # verify open + spec: ready
```

Run on office2:

```bash
ssh office2-claude 'ls -la /data/services/security-monitor/logs/drift-events.jsonl /data/services/openclaw/secrets/anthropic'
ssh office2-claude 'systemctl --user status felix-doc-auditor-driver.timer'   # should be active
```

Confirm:

- [ ] `~/.config/doc-audit/cutover-362.done` does NOT exist on office2 (fresh cutover)
- [ ] `/data/services/security-monitor/logs/drift-events-ledger.jsonl` does NOT exist (fresh ledger)
- [ ] Anthropic API key file is present (mode 0600 — owner readable only)
- [ ] Driver timer is active

---

## 1. Deploy the code (15 min)

The mission lands on `main` via spec-kitty merge. After merge:

```bash
# On Mac: confirm latest main has the mission's commits
git log --oneline main -10 | head

# On office2: pull latest, run installer-style commands
ssh office2-claude 'cd ~/kg-automation && git pull origin main'
```

Required files present after pull:

```bash
ssh office2-claude 'ls -la ~/kg-automation/scripts/doc_audit/judgment/drift_interpretation.py \
                          ~/kg-automation/scripts/doc_audit/prompts/drift_interpretation.prompt.md \
                          ~/kg-automation/scripts/doc_audit/helpers/cutover_362.py \
                          ~/kg-automation/scripts/doc_audit/output/drift_ledger.py \
                          ~/kg-automation/scripts/doc_audit/routing/drift_to_proposed_edit.py'
```

Confirm `config.toml` has the new section:

```bash
ssh office2-claude 'grep -A6 "\[drift_interpretation\]" ~/kg-automation/scripts/doc_audit/config.toml'
```

Expected output includes `enabled = true` and the other fields per `contracts/cli.md`.

---

## 2. Dry-run smoke test (10 min)

Run the cutover script in dry-run mode:

```bash
ssh office2-claude 'cd ~/kg-automation && python3 scripts/doc_audit/helpers/cutover_362.py --dry-run'
```

Expected output:

- Lists the 13 known pre-#362 P3 issues that would be closed
- Reports the cursor position that would be reset to 0
- States that no actions are being taken

Manually verify a couple of drift events through `drift_interpretation` directly:

```bash
ssh office2-claude 'cd ~/kg-automation && \
  python3 -m scripts.doc_audit.judgment.drift_interpretation \
    --input-file tests/doc_audit/fixtures/drift_event_openclaw_cron.json'
```

Expected: a valid `DriftVerdict` JSON on stdout, likely with `verdict: NO_CHANGE_NEEDED` for the openclaw-cron `deliveryMode` fixture.

---

## 3. Run the cutover (5 min)

Once dry-run looks correct:

```bash
ssh office2-claude 'cd ~/kg-automation && python3 scripts/doc_audit/helpers/cutover_362.py'
```

Verify:

```bash
ssh office2-claude 'cat ~/.config/doc-audit/cutover-362.done'
ssh office2-claude 'cat /data/services/security-monitor/.drift-events.cursor'   # should be 0
gh issue list --repo kentonium3/kg-automation --state closed --search 'label:P3-candidate "[doc-audit]"' --limit 15 | head
```

Confirm:

- [ ] Marker file written with run timestamp + list of closed issues
- [ ] Cursor reset to `0`
- [ ] All 13 pre-#362 issues now closed with cutover comment

---

## 4. Wait for the next cron tick (≤1 hour)

The driver timer fires at the top of each hour by default. Either wait or trigger manually:

```bash
ssh office2-claude 'systemctl --user start felix-doc-auditor-driver.service'
ssh office2-claude 'journalctl --user -u felix-doc-auditor-driver.service --since "5 minutes ago" | tail -50'
```

Expected log entries:

- "Processing N drift events from cursor 0"
- "Drift interpretation moment 0 invoked for event-id <...>"
- Per-event verdict line with confidence
- "Ledger entry written"

---

## 5. Post-deploy smoke tests (15 min)

### 5a. Verify ledger file exists and is well-formed

```bash
ssh office2-claude 'wc -l /data/services/security-monitor/logs/drift-events-ledger.jsonl'
ssh office2-claude 'tail -3 /data/services/security-monitor/logs/drift-events-ledger.jsonl | jq .'
```

### 5b. Verify each verdict type appears at least once

```bash
ssh office2-claude 'cd ~/kg-automation && python3 -m scripts.doc_audit.output.drift_ledger summary --days 1'
```

Expected: counts for `PROPOSED_EDIT`, `JUDGMENT_REQUIRED`, `NO_CHANGE_NEEDED` (and ideally zero `RETRY_EXHAUSTED`).

### 5c. Check the triage rate

```bash
ssh office2-claude 'cd ~/kg-automation && python3 -m scripts.doc_audit.output.drift_ledger triage-rate --days 1'
```

Expected: a percentage (likely a small number on day 1; the 7-day metric is the success criterion).

### 5d. Verify existing path still works

```bash
gh issue list --repo kentonium3/kg-automation --state open --search '"Doc audit:" in:title' --limit 5
```

Expected: existing commit-derived `Doc audit:` issues continue to flow unchanged (no regression in `handle_audit_routing.py`).

### 5e. Verify no spurious Tier A auto-commits

```bash
git log --since "1 hour ago" --grep "^chore.*doc-audit" main | head
```

Manually inspect any commits that landed; confirm they look correct.

---

## 6. Seven-day observation (passive)

The success criterion is measured over a 7-day post-deploy window. Daily check-in:

```bash
# Daily morning check (e.g., 9am ET)
ssh office2-claude 'cd ~/kg-automation && python3 -m scripts.doc_audit.output.drift_ledger triage-rate --days 7'
ssh office2-claude 'cd ~/kg-automation && python3 -m scripts.doc_audit.output.drift_ledger summary --days 7'
```

Expected after day 7:

- [ ] Triage rate ≤30% (NFR-001 / Success Criterion 1)
- [ ] Reliability ≥98% (NFR-005 / Success Criterion 2)
- [ ] No regression in `Doc audit:` path (manual sample-check)

If metrics are out of bounds:

- File a follow-on issue describing the failure mode
- Consider flipping `drift_interpretation.enabled = false` and rolling back (see §7)

---

## 7. Rollback procedure (≤60s — NFR-007)

If something goes wrong post-deploy:

```bash
# Disable Moment 0 immediately
ssh office2-claude 'sed -i "s/^enabled = true$/enabled = false/" ~/kg-automation/scripts/doc_audit/config.toml'
ssh office2-claude 'grep "enabled" ~/kg-automation/scripts/doc_audit/config.toml | grep drift_interpretation -A1'
```

Verify on next cron tick:

```bash
ssh office2-claude 'systemctl --user start felix-doc-auditor-driver.service'
ssh office2-claude 'journalctl --user -u felix-doc-auditor-driver.service --since "1 minute ago" | grep -i "drift_interpretation"'
```

Expected: log entries showing the pipeline skipped Moment 0 and used the pre-#362 path.

The ledger file is preserved. Issues already auto-resolved (Tier A commits, Tier B PRs, auto-closed events) remain in their final state. Re-enabling later is just flipping the flag back to `true`.

### Rollback to a prior commit

If a code-level revert is needed (rare; the config flag is the primary lever):

```bash
ssh office2-claude 'cd ~/kg-automation && git revert <merge-commit-sha>'
ssh office2-claude 'cd ~/kg-automation && git push origin main'
# Then pull again on office2 (no additional restart needed)
```

---

## 8. Cleanup

Once the 7-day observation is complete and metrics are within bounds:

- [ ] Close GitHub issue #362 with merge commit reference
- [ ] Update `docs/design/architecture/data/service-inventory.json` (in-mission, per Constitution Directive 5)
- [ ] Update `docs/runbooks/doc-auditor-driver-ops.md` to document the Moment 0 layer

The marker file `~/.config/doc-audit/cutover-362.done` is permanent — leave it in place as historical record.

---

## Cross-references

- Mission spec: [spec.md](spec.md)
- Implementation plan: [plan.md](plan.md)
- CLI contract: [contracts/cli.md](contracts/cli.md)
- API contract: [contracts/api.md](contracts/api.md)
- LLM JSON contract: [contracts/llm-json.md](contracts/llm-json.md)
- Ledger schema: [contracts/ledger-schema.md](contracts/ledger-schema.md)
- Origin issue: kentonium3/kg-automation#362
