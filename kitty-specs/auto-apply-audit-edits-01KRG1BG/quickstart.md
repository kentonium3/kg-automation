# Quickstart: Auto-apply audit edits

**Mission**: `auto-apply-audit-edits-01KRG1BG`

End-to-end recipe for implementer and post-merge operator.

---

## 1. Local verification (Mac)

```bash
cd /Users/kentgale/repos/kg-automation
python3 -m pytest tests/openclaw/agents/felix-doc-auditor/ -v
```

**Expect**: 7+ new tests pass (cases listed in plan.md test plan), 0 failed. Full test suite remains green.

## 2. Deploy to office2

felix-doc-auditor's deploy mechanism per `reference_felix_doc_auditor_ops.md`: hourly systemd-user timer on office2 pulls the latest repo state. After merging to main, the next timer fire picks up:
- `scripts/openclaw/agents/felix-doc-auditor/handle_audit_routing.py` (new)
- `scripts/openclaw/agents/felix-doc-auditor/AGENTS.md` (updated)

No separate deploy command. The agent uses the source-in-repo path directly.

If immediate verification is desired:

```bash
ssh office2-claude 'systemctl --user status felix-doc-auditor.timer'
ssh office2-claude 'cat /home/claude/kg-automation/scripts/openclaw/agents/felix-doc-auditor/handle_audit_routing.py | head -20'
```

## 3. Smoke test — handler partitions correctly

On office2 as claude, with a synthetic audit-state JSON:

```bash
ssh office2-claude '
set -e
mkdir -p /tmp/sc003
cat > /tmp/sc003/audit-state.json <<EOF
{
  "audit_issue_number": 999,
  "commit_sha": "deadbeef",
  "areas": ["area/docs"],
  "proposals": [
    {
      "doc_path": "/tmp/sc003/smoke-doc.md",
      "change_type": "unknown_test_type",
      "current_value": "old",
      "proposed_value": "new",
      "evidence_source": "smoke test",
      "confidence": "high"
    }
  ],
  "debt_issues_filed": [],
  "missing_artifact_issues_filed": []
}
EOF
printf "---\nlast_updated: 2026-01-01\n---\nold\n" > /tmp/sc003/smoke-doc.md

# Set GH_TOKEN to a no-op or use --dry-run; this MUST be invoked carefully because the
# handler may attempt to file a real GH issue on issue #999 (a non-existent issue).
# For smoke testing, prefer running with a fake gh in PATH or a dry-run env var if the
# handler supports it. Otherwise skip this leg and rely on unit tests.
echo "Smoke test skeleton above — adapt with --dry-run flag if implemented."
rm -rf /tmp/sc003
'
```

**Note**: end-to-end office2 smoke testing of this helper is awkward without a `--dry-run` flag because the handler writes to docs and calls `gh issue create`. The implementer should consider adding `--dry-run` as part of T002 or T003. The unit-test suite is the load-bearing verification.

## 4. End-to-end verification (SC-001 + SC-003)

Post-merge operator step:

1. **Wait for the next felix-doc-auditor cron tick** (or trigger via `systemctl --user start felix-doc-auditor.service` on office2).
2. **Pre-condition**: there must be a recent commit on `main` that the auditor has not yet processed. If no fresh audit is pending, optionally make a trivial docs change to trigger one.
3. **Observe**: when the auditor's next audit cycle produces only known-change_type proposals, it should:
   - Apply the edits and commit them on `main` with a structured commit message (visible via `git log`).
   - Post a summary comment on the originating audit issue (e.g., the next `Doc audit: <SHA>` issue).
   - Close the originating audit issue.
   - NOT file a new `audit-pending-approval` issue.
4. **Drain the 3 existing pending-approvals** (the test cases): apply `audit-approve` label to #236, #249, and #250 in sequence. The auditor's § 3 decision-handling logic (unchanged by this mission) applies each edit and closes both issues.

## 5. Token-budget verification (NFR-003 + SC-004)

Compare cron-run `total_tokens` before and after the deploy:

```bash
ssh office2-claude 'openclaw cron runs --id <doc-auditor-cron-uuid> --limit 5 2>&1 | jq ".entries[] | {ts, status, total_tokens: .usage.total_tokens, summary: (.summary[:80])}"'
```

**Expect**: post-deploy ticks that produce only known-change_type audits show `total_tokens` reduced by ≥ 50% vs. pre-deploy comparable ticks. (The LLM is no longer doing routing-decision reasoning on every cycle.)

## 6. Rollback (if needed)

```bash
git revert <merge-commit-hash>
```

felix-doc-auditor's next tick picks up the reverted AGENTS.md from the source-in-repo path and reverts to the prose-driven routing. No additional deploy step.
