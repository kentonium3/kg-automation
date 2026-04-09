# Implementation Plan: Inbox GitHub Issue Routing

**Branch**: `main` | **Date**: 2026-04-09 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `kitty-specs/022-inbox-github-issue-routing/spec.md`
**Source Issue**: #146

## Summary

Add a GitHub issue routing path to the inbox agent (felix-admin-capture) by updating its standing orders and tools reference. The agent uses OpenClaw's bundled `github` skill (which wraps `gh` CLI) to create issues — no new services, agents, or code required. The implementation is entirely agent configuration: AGENTS.md routing table, workflow instructions, and TOOLS.md tool reference.

## Technical Context

**Platform**: office2 (Ubuntu 24.04 LTS) via `ssh office2-claude`
**Agent**: felix-admin-capture
**Agent workspace**: `/data/services/openclaw/inbox-agent/`
**Repo-side copies**: `scripts/openclaw/agents/felix-admin-capture/`
**GitHub skill**: OpenClaw bundled `github` skill at `/usr/lib/node_modules/openclaw/skills/github/SKILL.md`
**gh CLI**: `/usr/bin/gh`, authenticated as kentonium3 (confirmed 2026-04-09)
**Change control**: Tier 3 (agent prompts/logic) — no backup required
**Model**: `anthropic/claude-haiku-4-5` (set during mission 021)

## Research Findings

All unknowns resolved through live discovery:

| Question | Answer | Source |
|---|---|---|
| How does the agent create issues? | OpenClaw bundled `github` skill wraps `gh` CLI | `openclaw skills list` |
| Is `gh` authenticated? | Yes, as kentonium3 | `gh auth status` on office2 |
| What tools does the agent have? | Vikunja API skill, vault access, privacy boundaries | TOOLS.md on office2 |
| How are new routes added? | New row in AGENTS.md Step 3 routing table + workflow section | AGENTS.md structure |
| How is action logging done? | Action type table in AGENTS.md + `log_action.py` | AGENTS.md logging section |
| What labels exist? | P0-P3 + type suffix, 8 area/ labels, spec lifecycle labels | `gh label list` |

**No research.md needed** — all clarifications resolved through live discovery.

## Implementation Approach

This feature modifies two files on office2 and their repo-side copies. No new files created.

### AGENTS.md Changes

1. **Routing table (Step 3)** — add new row:

   | Content type | Destination | Action |
   |---|---|---|
   | GitHub issue request | GitHub (kentonium3/kg-automation) | Create issue via github skill, confirm via WhatsApp |

2. **New section: "GitHub issue creation"** — after the tasker delegation section, add:
   - Trigger phrase detection rules (explicit "github issue" required)
   - Title inference instructions (distill from voice content, apply prefix convention)
   - Label inference instructions with the full label list embedded
   - `gh issue create` command template
   - Processing summary format showing created issue
   - Confirmation response handling (accept/modify/reject)
   - Error handling (gh CLI failure → log + needs-review)
   - Out-of-scope handling (multi-repo requests → inform Kent)

3. **Action logging table** — add new action type:

   | Action type | Description | Category |
   |---|---|---|
   | `github_issue_created` | GitHub issue created from inbox content | routine |
   | `github_issue_failed` | GitHub issue creation failed | error |
   | `github_issue_updated` | Issue labels updated per Kent's request | routine |
   | `github_issue_rejected` | Issue closed per Kent's rejection | routine |

### TOOLS.md Changes

Add a GitHub section:
- Skill: `github` (OpenClaw bundled)
- Target repo: `kentonium3/kg-automation`
- Available P-labels: P1-feature, P2-feature, P3-candidate, P1-infra, P2-infra, P1-bug, P2-bug, P1-rfc, P2-debt
- Available area labels: area/infrastructure, area/security, area/felix-core, area/ea, area/task-intel, area/content, area/docs, area/biz-ops
- Always apply: `spec: brief`
- Note: multi-repo not yet supported

### Documentation Updates (repo)

- `docs/design/architecture/service-inventory.md` — update inbox agent description to note GitHub issue routing capability
- `scripts/openclaw/agents/felix-admin-capture/` — update repo-side copies of AGENTS.md and TOOLS.md

## Haiku Capability Concern

The inbox agent now runs on Haiku (mission 021). The GitHub issue routing adds complexity to the agent's decision tree:
- Trigger phrase detection (pattern matching — Haiku should handle this)
- Title inference (summarization — Haiku should handle this)
- Label inference (classification — Haiku should handle this)
- `gh` CLI execution (tool use — Haiku struggled with multi-step tool workflows in mission 021)

The `gh issue create` is a single CLI call, not a multi-step tool chain like Vikunja querying. This should be within Haiku's capability. However, if the agent fails to execute the GitHub skill reliably on Haiku, we may need to evaluate whether this specific routing path requires Sonnet — or whether the standing orders need to be written in a way that minimizes tool-call complexity for Haiku.

**Mitigation**: Write the AGENTS.md instructions as a single clear command template rather than multi-step reasoning. Test on Haiku before considering model changes.

## Project Structure

### Files Modified on office2

```
/data/services/openclaw/inbox-agent/
├── AGENTS.md    ← routing table + GitHub issue workflow section
└── TOOLS.md     ← GitHub section with skill reference and label list
```

### Files Modified in kg-automation repo

```
scripts/openclaw/agents/felix-admin-capture/
├── AGENTS.md    ← repo-side copy (kept in sync)
└── TOOLS.md     ← repo-side copy (kept in sync)

docs/design/architecture/
└── service-inventory.md  ← update inbox agent description
```

## Risk Mitigation

| Risk | Mitigation | Phase |
|---|---|---|
| Haiku can't execute github skill reliably | Write instructions as single-command template; test before deploying | Implementation |
| gh auth expires | Agent detects failure, reports in summary, marks content needs-review | Standing orders |
| Label inference is wrong | Confirmation flow lets Kent correct; default to P2-feature when uncertain | Standing orders |
| Generic "issue" triggers false positive | Require explicit "github issue" pairing; document in standing orders | Standing orders |

## Branch Contract

- Current branch: `main`
- Planning/base branch: `main`
- Merge target: `main`
- Branch matches target: **true**

---

**PLAN COMPLETE** — Ready for `/spec-kitty.tasks --mission 022-inbox-github-issue-routing`
