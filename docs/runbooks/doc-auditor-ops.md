---
title: Doc Auditor Operations Runbook
doc_type: runbook
audience: agents_and_humans
status: draft
last_updated: '2026-05-11'
updated_by: '#226'
---

# Doc Auditor Operations Runbook

This runbook covers day-to-day operations for the `felix-doc-auditor` agent —
the autonomous OpenClaw agent that processes documentation audit issues
created by `doc-audit-trigger.yml` (per-merge) and `doc-audit-weekly.yml`
(weekly cron).

## Service Overview

`felix-doc-auditor` is a specialist OpenClaw agent. It polls GitHub for
unprocessed `Doc audit:` and `Weekly doc audit` issues, classifies each
finding (high-confidence edit / judgment-required / missing artifact),
proposes edits via WhatsApp at Level 1, and on approval commits the edits,
files structured `docs-debt` issues, and closes the originating audit issue.

**Agent name**: `felix-doc-auditor`
**Current autonomy level**: Assisted (Level 1)
**Model**: Sonnet (pinned per Model Assignment Policy)
**Schedule**: cron `0 * * * *` (every 60 minutes)
**Host**: office2 (Ubuntu 24.04 LTS)
**Run-as user**: `claude`
**Workspace (repo)**: [`scripts/openclaw/agents/felix-doc-auditor/`](../../scripts/openclaw/agents/felix-doc-auditor/) — IDENTITY.md, SOUL.md, AGENTS.md, TOOLS.md
**Workspace (deployed)**: `/data/services/openclaw/felix-doc-auditor/` on office2
**Skill (repo)**: [`scripts/openclaw/skills/doc-audit/SKILL.md`](../../scripts/openclaw/skills/doc-audit/SKILL.md)
**Skill (deployed)**: `~/.openclaw/skills/doc-audit/SKILL.md` on office2
**Activity log**: `/home/kgale/second-brain/agents/logs/doc-auditor-YYYY-MM-DD.md`
**OpenClaw registration**: `/home/claude/.openclaw/openclaw.json` (cron entry)

**Source-of-truth in this repo**:

- Agent workspace: [`scripts/openclaw/agents/felix-doc-auditor/`](../../scripts/openclaw/agents/felix-doc-auditor/)
- Skill: [`scripts/openclaw/skills/doc-audit/`](../../scripts/openclaw/skills/doc-audit/)
- Governance entry: [`docs/constitution/AGENT-REGISTRY.md`](<../constitution/AGENT-REGISTRY.md>), [`docs/constitution/agent-registry.json`](<../constitution/agent-registry.json>)
- Service-inventory entry: [`docs/design/architecture/data/service-inventory.json`](<../design/architecture/data/service-inventory.json>), [`docs/design/architecture/service-inventory.md`](<../design/architecture/service-inventory.md>)
- Domain map (scope contract): [`docs/design/architecture/data/doc-domain-map.json`](<../design/architecture/data/doc-domain-map.json>)

### GitHub Operating Identity

The agent acts on GitHub as `kg-felix-bot` — a dedicated service-account collaborator, distinct from Kent's personal `kentonium3` account. This separation is load-bearing: the §8.6 actor-verification check in [AGENTS.md](<../../scripts/openclaw/agents/felix-doc-auditor/AGENTS.md>) confirms that an `audit-approve` / `audit-reject` / `audit-skip` label was applied by a human, not by the agent itself.

| Surface | Appears as |
|---|---|
| Git commit author | `kg-felix-bot <283481604+kg-felix-bot@users.noreply.github.com>` |
| `gh` CLI actions (labels, comments, issue creation) | `kg-felix-bot` in GitHub timeline events |
| Credential | classic PAT at `/home/claude/.config/gh/hosts.yml` on office2 — see [`kg-felix-bot-pat`](<../design/architecture/data/credential-manifest.json>) in credential-manifest.json |

Canonical identity record: [`AGENT-REGISTRY.md` §Service Accounts](<../constitution/AGENT-REGISTRY.md#service-accounts>). PAT rotation procedure: see `kg-felix-bot-pat.expiry_notes` in credential-manifest.json.

## How It Operates

The agent is a cron-triggered processor — no long-running daemon, no inbound
listener. Each cron tick is a complete audit attempt against one issue.

### Per-tick lifecycle

1. **Cron fires** (every 60 minutes, top of the hour).
2. **Query for unprocessed audits**:
   ```
   gh issue list --label "P2-debt" --state open \
     --search "Doc audit OR Weekly doc audit" --json number,labels,title
   ```
   Filter out any issue carrying the `status:in-progress` label (active or
   stale lock — see [Stale-Lock Recovery](<#stale-lock-recovery>)).
3. **Pick oldest unprocessed issue** (FIFO by creation date).
4. **Claim it** by applying `status:in-progress` label. This is the
   concurrency control — survives crashes, visible in the GitHub UI, no
   on-disk state.
5. **Load the doc-audit skill** (`~/.openclaw/skills/doc-audit/SKILL.md`).
   The skill is self-contained: domain map interpretation, confidence
   threshold rules, debt-issue template requirements, comparison rules,
   commit message format, and error handling all live there.
6. **Read the audit issue body** to determine scope:
   - If the issue has `area/*` labels → scoped audit; in-scope docs are the
     intersection of `doc-domain-map.json` entries for those labels.
   - If no `area/*` labels (weekly audits) → full scope per the domain map.
7. **For each in-scope doc**: read it; compare against current system state
   (consulting `service-inventory.json`, `agent-registry.json`,
   `doc-domain-map.json`, `git log`); classify each finding as:
   - **High-confidence edit** (frontmatter dates, version numbers, paths,
     dead refs, registry entries with explicit governance evidence)
   - **Judgment-required** (architectural prose, ambiguous source-of-truth
     conflicts, new sections needing design)
   - **Missing artifact** (deployed agent without runbook, new service
     without architecture entry)
8. **Build edit proposals + debt-issue drafts**.
9. **Level 1 approval gate**: Send a WhatsApp summary message (identity
   header `Sent by felix-doc-auditor:sonnet`) listing the proposed edits,
   debt issues, and missing artifacts.
10. **Wait for reply** (timeout 2 hours per NFR-004). Reply vocabulary:
    `approve`, `reject`, `skip`, `approve N` (e.g., `approve 1,3`).
11. **Apply outcome**:
    - `approve` → commit edits atomically (commit message format
      `chore(doc-audit): <doc>: <change> (audit: <issue#>)`); create
      debt issues; post audit summary comment; close audit issue.
    - `reject` → do not commit; convert all proposed edits into debt
      issues; post summary; close.
    - `skip` → no commits, no debt issues; post a skip-note summary; close.
    - `approve N` → commit only listed proposals; defer the rest as debt
      issues.
    - Timeout (default-deny) → convert proposed edits to debt issues; record
      the timeout in the summary; close.
12. **Release the lock** by removing the `status:in-progress` label.

For the per-doc state machine and full data model, see
[`kitty-specs/felix-doc-auditor-agent-01KR7JK9/data-model.md`](../../kitty-specs/felix-doc-auditor-agent-01KR7JK9/data-model.md).

### What runs where

- **Cron schedule**: lives in `/home/claude/.openclaw/openclaw.json` on
  office2 (managed by OpenClaw).
- **Audit logic**: `~/.openclaw/skills/doc-audit/SKILL.md` (the skill).
- **Standing orders**: `/data/services/openclaw/felix-doc-auditor/AGENTS.md`
  (the agent workspace).
- **Outbound WhatsApp**: standard OpenClaw `send-message` tool, same as
  every `felix-admin-*` agent.

## Manual Trigger

Use case: an ad-hoc audit against a specific issue, the [canary
procedure](../../kitty-specs/felix-doc-auditor-agent-01KR7JK9/quickstart.md)
for first deploy, or re-running an audit after fixing a stale-lock.

```
ssh office2-claude
openclaw delegate felix-doc-auditor "Process audit issue #<N> from kentonium3/kg-automation. Follow the doc-audit skill end-to-end."
```

The agent runs the same code path as a cron tick — there is no
"manual mode" branch in the skill or workspace. The Level 1 approval gate
still applies; the agent will send a WhatsApp summary and wait for a reply.

For the first end-to-end exercise (canary), follow the procedure in
[`quickstart.md`](../../kitty-specs/felix-doc-auditor-agent-01KR7JK9/quickstart.md)
rather than duplicating the steps here.

## Adding a Document to the Audit Scope

Audit scope is determined by the domain map at
[`docs/design/architecture/data/doc-domain-map.json`](<../design/architecture/data/doc-domain-map.json>).
The map keys are `area/*` label names; the values are arrays of doc paths
(repo-relative). To bring a new document under audit:

1. **Edit the domain map**:
   - Open `docs/design/architecture/data/doc-domain-map.json`.
   - Find the appropriate `area/*` key (e.g., `area/felix-core` for
     governance/agent/runbook docs; `area/infrastructure` for office2
     hardware/network/services; `area/security` for credentials/UFW/Tailscale;
     etc.).
   - Append the doc path to that array (alphabetical order preferred).
   - Bump `last_updated` to today's ISO date.
   - Set `updated_by` to the issue or commit reference making the change.
2. **Commit + push** to `main` — the next per-merge audit will already
   pick up the new entry.
3. **No agent restart required.** The agent reads the domain map fresh on
   every cron tick.

A doc may belong to multiple areas — list it in each. The agent reads the
union for full-scope audits.

If a doc is in the repo but **not** in the domain map, the agent does
nothing with it (per constraint C-005, the map is the scope contract).
The exception: missing-artifact detection (FR-004) catches deployed
agents/services without docs even if the map doesn't list them yet.

## Adjusting the Confidence Threshold

The high-confidence vs judgment threshold lives in the skill:
[`scripts/openclaw/skills/doc-audit/SKILL.md`](../../scripts/openclaw/skills/doc-audit/SKILL.md)
(deployed to `~/.openclaw/skills/doc-audit/SKILL.md` on office2). The skill
enumerates the high-confidence categories and the explicit "not high
confidence" categories.

To **make the agent more conservative** (fewer direct edits, more debt
issues): add the questionable category to the "not high confidence" list
in `SKILL.md`. Example: if the agent is over-eagerly bumping version
numbers, demote that category until the comparison rules can be tightened.

To **make it more aggressive** (rare; only with strong evidence): add the
new category to the high-confidence list, including the evidence pattern
the agent must observe in the diff/system-state to qualify.

After editing the skill:

1. Commit + push to `main`.
2. On office2, re-deploy the skill copy:
   ```
   ssh office2-claude "cd /home/claude/kg-automation && git pull origin main"
   ```
   Plus the skill-copy step that the felix-doc-auditor deploy script (from
   WP05) handles. Until that script lands, copy by hand:
   ```
   ssh office2-claude "cp -r /home/claude/kg-automation/scripts/openclaw/skills/doc-audit ~/.openclaw/skills/"
   ```
3. **No service restart needed.** The agent loads the skill at the start
   of every audit run.

The threshold change takes effect on the next cron tick.

## Stale-Lock Recovery

**Symptom**: a `Doc audit:` or `Weekly doc audit` issue carries the
`status:in-progress` label for more than 30 minutes without progressing
(no commits, no debt issues, no summary comment).

**Root causes**:

- Agent crashed or hit an unhandled error mid-run.
- WhatsApp delivery failed — at Level 1 the agent cannot commit without
  approval, so the run halts but the label was already applied.
- Network blip during cron tick (office2 lost Tailscale, GitHub API
  unreachable).

**Recovery** (any user — no sudo required):

```
gh issue edit <#> --remove-label "status:in-progress" --repo kentonium3/kg-automation
```

The next cron tick (within 60 minutes) will re-pick the issue and start a
fresh audit. The previously prepared in-memory edit proposals are gone, so
the agent will re-read the doc and re-propose — that's intentional and
safe.

If the same issue stale-locks repeatedly, inspect the activity log at
`/home/kgale/second-brain/agents/logs/doc-auditor-YYYY-MM-DD.md` for the
recurring failure pattern (e.g., a specific doc that consistently fails to
read; a WhatsApp service outage). Address the root cause before
re-attempting.

## Kill Switch

Two levels of disable, in order of preference.

### Soft kill — disable the agent's cron entry only

Other OpenClaw agents continue to run.

1. SSH to office2 as claude:
   ```
   ssh office2-claude
   ```
2. Edit `/home/claude/.openclaw/openclaw.json`. Find the `felix-doc-auditor`
   cron entry and either:
   - Set `enabled: false` on the cron entry, or
   - Comment out the cron line (per existing convention used by other
     `felix-admin-*` agents when paused).
3. Restart the OpenClaw cron service to pick up the change. The exact
   command depends on whether OpenClaw runs as a system service or a user
   service — check the [OpenClaw Operations runbook](<./openclaw-ops.md>):
   ```
   # System service (requires sudo via kgale):
   sudo systemctl restart openclaw-cron
   # OR user service:
   systemctl --user restart openclaw-cron
   ```
4. Verify: `systemctl list-timers --all 2>&1 | grep openclaw` should no
   longer show a `felix-doc-auditor` next-run.

To re-enable: reverse the edit and restart again.

### Heavy kill — stop all OpenClaw cron agents

Use this only when there is a system-wide concern (e.g., GitHub API
outage, runaway agent in another component).

```
sudo systemctl stop openclaw-cron
```

This halts every cron-triggered OpenClaw agent. Re-start with
`sudo systemctl start openclaw-cron` once the underlying issue is
resolved.

Any audit issue currently carrying `status:in-progress` when the kill
switch is hit will become a stale lock — clear it per
[Stale-Lock Recovery](<#stale-lock-recovery>) before re-enabling.

## Promotion to Supervised (Level 2)

Promotion from Assisted (Level 1) to Supervised (Level 2) is a **separate
governance decision** Kent makes — the agent never self-promotes
(constraint C-001). Promotion is expected ~1 week post-deploy after
evidence review per the
[Felix Constitution](<../constitution/FELIX-CONSTITUTION.md>) autonomy
process.

### Evidence required

Before promotion, confirm:

- **No false-positive commits**: every audit commit in the first week is
  correct (validated by inspecting `git log` for `chore(doc-audit):` commits
  and reviewing each).
- **WhatsApp approval cycle worked smoothly**: the agent's proposals were
  generally appropriate, with no recurring `reject` or `skip` for what
  should have been clear high-confidence edits.
- **No edits to forbidden paths**: zero commits touching the Felix
  Constitution, any CLAUDE.md, credential files (`.env`,
  `credentials.json`), or `kitty-specs/` / `.kittify/` directories
  (constraint C-002, validated by `git log --all --diff-filter=M -- <path>`
  for each forbidden path).
- **Audit trail intact**: every commit references an audit issue number;
  every debt issue links to the originating audit; every audit summary
  comment is present (NFR-007).

### Operational change

Promotion is a metadata flip:

1. Update [`docs/constitution/AGENT-REGISTRY.md`](<../constitution/AGENT-REGISTRY.md>):
   - Bump the agent's `Current Autonomy Level` to `Supervised (Level 2)`.
   - Append a new row to its `Transition History` table with date,
     direction (`Promotion`), reason, and decided-by.
2. Update [`docs/constitution/agent-registry.json`](<../constitution/agent-registry.json>):
   - Set `autonomy_level` to `2`.
   - Append a `transition_history` entry with the same fields.
3. Commit + push.

The agent reads `agent-registry.json` at the start of every audit. On the
next tick after the promotion lands, the agent will skip the WhatsApp
approval step for high-confidence edits — instead committing directly and
sending a post-hoc summary message. Judgment-required gaps still become
debt issues; the constitution and CLAUDE.md guardrails still apply
(constraint C-002 is autonomy-independent).

Demotion follows the same flip in reverse.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Agent never processes audit issues | Cron entry disabled or OpenClaw cron service stopped | Check `cat /home/claude/.openclaw/openclaw.json | jq '.crons[] | select(.agent == "felix-doc-auditor")'`; restart `openclaw-cron` |
| Issue stuck at `status:in-progress` for >30 min | Agent crashed mid-run, WhatsApp delivery failed at Level 1, or network blip | [Stale-Lock Recovery](<#stale-lock-recovery>) — remove the label; next tick will retry |
| Agent files debt issues for what should be high-confidence types | Skill threshold misconfigured | Review confidence rules in `scripts/openclaw/skills/doc-audit/SKILL.md`; demote/promote categories per [Adjusting the Confidence Threshold](<#adjusting-the-confidence-threshold>) |
| Agent commits an incorrect doc edit | Comparison rules wrong, or system-state source out of date | Revert the commit (`git revert <sha>`); reopen the audit issue (`gh issue reopen <#>`); inspect skill comparison rules; consider lowering autonomy until the rule is fixed |
| WhatsApp delivery fails | Existing WhatsApp service issue | Per [`docs/runbooks/whatsapp-ops.md`](<./whatsapp-ops.md>). At Level 1 the agent halts (no commits without approval); the audit issue stays open with `status:in-progress` until the lock is manually cleared. |
| GitHub API rate-limit hit (5000/hr authenticated) | Many audits stacked + many commits/issues per audit | Lower polling cadence in `openclaw.json` (e.g., to every 2 hours); investigate why backlog accumulated |
| Agent reads a file outside the domain map's scope | Skill or AGENTS.md mistake | Inspect activity log at `/home/kgale/second-brain/agents/logs/doc-auditor-*.md`; tighten `TOOLS.md` disallowed-paths list; redeploy workspace |
| Doc unreadable mid-audit | File missing, permissions issue, encoding error | Per spec NFR-003 the agent logs the failure, skips the doc, includes it in the audit summary as "could not read", and continues. Manual follow-up via the summary's flagged item. |
| Weekly audit not created on Sunday | Stale weekly issue blocks creation (pre-FR-008 fix) | Confirm the FR-008 fix is in `.github/workflows/doc-audit-weekly.yml` (search query must include `in:title` and current `${DATE}`). Manually trigger: `gh workflow run doc-audit-weekly.yml`. |
| Agent makes zero edits over an entire week | Confidence threshold too conservative, or no audit issues with high-confidence findings | Review weekly debt-issue volume — if all gaps are judgment, that's expected. If high-confidence findings are being demoted, see threshold adjustment above. |
| Commits or issue actions attributed to `kentonium3` instead of `kg-felix-bot` | `gh` auth on office2 fell back to the wrong account, or git committer config drifted | On office2 as the claude user, run `gh api user --jq .login` — it must return `kg-felix-bot`. If not: `gh auth logout --hostname github.com` then `gh auth login --hostname github.com --git-protocol https` with the `kg-felix-bot-pat`. Also verify `git config --get user.email` returns the bot's `noreply` address (see [GitHub Operating Identity](<#github-operating-identity>)). |

## Security Baseline Reset

After deploying or upgrading `felix-doc-auditor`, the security monitoring
baselines on office2 should be updated to reflect the new expected state
(same pattern as the [transcribe-ops Security Baseline Reset](<./transcribe-ops.md#security-baseline-reset>)).

### What changes

After a felix-doc-auditor deploy or upgrade, the following are new expected
state:

- New entry in `service-inventory.json` (deployed agent on office2).
- New directory `/data/services/openclaw/felix-doc-auditor/` (the deployed
  workspace copy).
- New skill at `~/.openclaw/skills/doc-audit/` on the claude user's home.
- New cron entry in `/home/claude/.openclaw/openclaw.json`.
- Agent activity-log directory pattern at
  `/home/kgale/second-brain/agents/logs/doc-auditor-*.md`.

### Reset procedure

This step may require sudo. Run as kgale if needed:

```
# Check current baseline status:
ls -la /data/services/security-monitor/baselines/

# Regenerate baselines:
cd /data/services/security-monitor
./scripts/generate-baselines.sh
```

### When to reset

- After initial felix-doc-auditor deployment (this mission, #105).
- After any change to the agent workspace (IDENTITY.md, SOUL.md, AGENTS.md,
  TOOLS.md) that alters file paths or tool allowlists.
- After any change to the cron schedule in `openclaw.json`.
- After autonomy-level promotion (Level 1 → 2 changes the expected
  WhatsApp message volume; security monitor heuristics may flag a sudden
  drop).
