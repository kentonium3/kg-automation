# Quickstart: Felix Doc Auditor Agent

**Mission**: `felix-doc-auditor-agent-01KR7JK9`
**Phase**: 1 (Design & Contracts)

This guide walks through the canary procedure (R-014) — the first end-to-end exercise of the agent against a real audit issue, before enabling the cron schedule.

---

## Prerequisites

All implementation tasks complete:

- [ ] Agent workspace exists in repo at `scripts/openclaw/agents/felix-doc-auditor/` (IDENTITY.md, SOUL.md, AGENTS.md, TOOLS.md)
- [ ] Skill exists in repo at `scripts/openclaw/skills/doc-audit/SKILL.md`
- [ ] Office2 has the latest commits pulled at `/home/claude/kg-automation/`
- [ ] Agent workspace deployed to office2 at `/data/services/openclaw/felix-doc-auditor/` (or symlink — per implementation decision)
- [ ] Skill deployed to office2 at `~/.openclaw/skills/doc-audit/` (per existing skill deploy pattern)
- [ ] OpenClaw config at `/home/claude/.openclaw/openclaw.json` registers `felix-doc-auditor` (cron entry **disabled** — manual canary first)
- [ ] AGENT-REGISTRY.md and agent-registry.json have the new entry per `contracts/agent-registry-entry.template.md`
- [ ] service-inventory.json has the new agent entry
- [ ] doc-domain-map.json includes the new ops runbook reference
- [ ] GitHub label `status:in-progress` exists (`gh label create status:in-progress --color fbca04 --description "Automated agent processing this issue. Manual cleanup if older than 30 min."`)
- [ ] FR-008 fix shipped: `.github/workflows/doc-audit-weekly.yml` updated per R-012 and pushed to main

---

## Canary procedure

### Step 1: Confirm initial state

```bash
# On office2 as claude:
cd /home/claude/kg-automation && git pull origin main
ls /data/services/openclaw/felix-doc-auditor/
ls ~/.openclaw/skills/doc-audit/

# Verify agent is registered to OpenClaw:
openclaw agents | grep felix-doc-auditor
# Expected: line showing felix-doc-auditor with its identity card

# Verify the GitHub label exists:
gh label list --repo kentonium3/kg-automation | grep status:in-progress

# Verify cron entry is disabled (commented out or schedule field empty):
cat /home/claude/.openclaw/openclaw.json | jq '.crons[] | select(.agent == "felix-doc-auditor")'
```

### Step 2: Manually invoke the agent against #186

```bash
# On office2 as claude:
openclaw delegate felix-doc-auditor "Process audit issue #186 from kentonium3/kg-automation. Follow the doc-audit skill end-to-end."
```

The agent should:

1. Apply the `status:in-progress` label to issue #186
2. Read issue #186's body (full-scope weekly audit checklist)
3. Read `doc-domain-map.json` and select all docs (no `area/*` labels → full scope)
4. For each doc, compare against current system state and build Edit Proposals
5. Send a WhatsApp message (template per `contracts/whatsapp-summary.template.md`)
6. Wait for Kent's reply (vocabulary per `contracts/whatsapp-reply-vocabulary.md`)

### Step 3: Reply via WhatsApp

Kent receives the WhatsApp summary. Inspect the proposed edits. Reply with one of the vocabulary keywords:

- `approve` to commit all
- `approve N` (e.g., `approve 1,3`) to commit selected
- `reject` to demote all to debt issues
- `skip` to close audit with a skip note

For the canary, recommended reply: `approve` (or `approve 1` if any proposed edit looks risky — use the partial-approve to validate that path too).

### Step 4: Verify the outputs

```bash
# Check git log for the audit commit:
git -C /home/claude/kg-automation log --oneline -5
# Expected: a chore(doc-audit): ... (audit: #186) commit if any edits were approved

# Check the audit issue is closed:
gh issue view 186 --repo kentonium3/kg-automation
# Expected: state=CLOSED, with the agent's audit summary comment

# Check that the label was removed:
gh issue view 186 --repo kentonium3/kg-automation --json labels
# Expected: status:in-progress NOT in the labels list

# Check for newly-created docs-debt issues:
gh issue list --repo kentonium3/kg-automation --label P2-debt --state open --search "created:>=2026-05-09"
# Expected: 0 or more new "Docs:" issues with structured outlines

# Check the agent activity log:
tail -50 /home/kgale/second-brain/agents/logs/doc-auditor-$(date +%F).md
# Expected: a section for the canary run with summary stats
```

### Step 5: If canary passes, enable cron

```bash
# Edit OpenClaw config to enable the cron entry:
# Open /home/claude/.openclaw/openclaw.json and uncomment / enable the cron line for felix-doc-auditor
# Then restart the OpenClaw cron service:
sudo systemctl restart openclaw-cron   # if Kent's sudo
# OR
systemctl --user restart openclaw-cron  # if user-level

# Confirm next scheduled run:
systemctl list-timers --all 2>&1 | grep openclaw
```

### Step 6: Watch the next cron tick

Within 60 minutes:

- Cron fires
- Agent picks the next-oldest open audit issue (#168 if not yet processed)
- Same flow as Step 2-4, but triggered automatically
- Backlog drains naturally over subsequent ticks (NFR-006: ≤6 hours for 6-issue backlog)

---

## Recovery procedures

### If the canary leaves issue #186 with `status:in-progress` and no commits

```bash
gh issue edit 186 --remove-label "status:in-progress" --repo kentonium3/kg-automation
# Investigate: openclaw logs / agent activity log
# Re-run Step 2 once the issue is identified
```

### If the agent commits something incorrect

```bash
# Revert the commit:
git -C /home/claude/kg-automation revert <sha>
git -C /home/claude/kg-automation push origin main

# Reopen the audit issue if relevant:
gh issue reopen <audit#> --repo kentonium3/kg-automation

# Investigate via the agent activity log + WhatsApp message history
# Adjust the skill (scripts/openclaw/skills/doc-audit/SKILL.md) confidence threshold rules
# Push the skill update; re-deploy
```

### If WhatsApp delivery fails

```bash
# Check WhatsApp service status (out of scope for this mission, but standard troubleshooting):
# Per docs/runbooks/whatsapp-ops.md

# At Level 1, no WhatsApp = no commits (the approval gate is mandatory).
# Issue stays open with status:in-progress until Kent manually intervenes.
# Document any recurring WhatsApp failures as separate issues.
```

### Emergency stop (kill switch)

```bash
# Disable the OpenClaw cron entry:
# Edit /home/claude/.openclaw/openclaw.json and disable the cron line for felix-doc-auditor
# Restart the OpenClaw cron service to pick up the change

# OR (heavier hammer — stops all OpenClaw scheduled agents):
sudo systemctl stop openclaw-cron
```

The ops runbook (FR-007) documents both the routine and emergency procedures.
