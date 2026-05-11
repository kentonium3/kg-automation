---
title: Felix Agent Registry
doc_type: reference
status: approved
---

# Felix Agent Registry

The authoritative record for agent registration and autonomy levels is
`agent-registry.json` in this directory. This file is the human-readable view.

---

## Model Assignment Policy

New agents default to Haiku (`anthropic/claude-haiku-4-5`) unless the task
requires complex reasoning, trend analysis, or orchestration. Model assignment
is based on task complexity, not autonomy level.

- **Pinned**: Agent must stay on its assigned model. Change requires validation
  with representative production inputs and documented justification.
- **Optimizable**: Agent may move to a cheaper model in the future if one
  becomes available and passes quality validation.

To change an agent's model tier: validate on representative inputs, document
results, update this registry and `agent-registry.json`.

---

## felix-admin-capture

**Team**: SuperAdmin (B)
**Scope**: Obsidian inbox processing — classifies notes, routes to vault, creates Vikunja tasks
**Current Autonomy Level**: Assisted (Level 1)
**Model**: Haiku (optimizable) — validated 2026-04-09, equivalent routing accuracy
**Deployed**: F008 (2026-03-31)
**Registered**: F012 (2026-04-01)

### Transition History

| Date | Level | Direction | Reason | Decided By |
|------|-------|-----------|--------|------------|
| 2026-04-01 | Assisted | Registration | Initial registration under Felix governance framework (F012) | Kent Gale |

---

## felix-admin-habits

**Team**: SuperAdmin (B)
**Scope**: Daily habit check-ins, completion recording, and pattern reporting
**Current Autonomy Level**: Assisted (Level 1)
**Model**: Sonnet (pinned) — Haiku failed workflow execution (2026-04-09). Pending #141 agent split.
**Deployed**: F009 (2026-03-31)
**Registered**: F012 (2026-04-01)

### Transition History

| Date | Level | Direction | Reason | Decided By |
|------|-------|-----------|--------|------------|
| 2026-04-01 | Assisted | Registration | Initial registration under Felix governance framework (F012) | Kent Gale |

---

## felix-admin-tasker

**Team**: SuperAdmin (B)
**Scope**: Task structuring and enrichment — transforms raw task descriptions into fully structured Vikunja tasks
**Does NOT handle**: Inbox processing, habit tracking, briefings, calendar, email
**Current Autonomy Level**: Assisted (Level 1)
**Model**: Sonnet (pinned) — complex multi-step reasoning, pre-classified
**Deployed**: F013 (2026-04-02)
**Registered**: F013 (2026-04-02)

### Transition History

| Date | Level | Direction | Reason | Decided By |
|------|-------|-----------|--------|------------|
| 2026-04-02 | Assisted | Registration | Initial registration under Felix governance framework (F013) | Kent Gale |

---

## felix-admin-escalation

**Team**: SuperAdmin (B)
**Scope**: Overdue and at-risk task escalation — detects tasks past due date, delivers level-appropriate WhatsApp alerts, tracks escalation state via Vikunja comments, handles responses
**Does NOT handle**: Habits, inbox processing, task structuring, briefings, calendar, goal-level commitment assessment
**Current Autonomy Level**: Assisted (Level 1)
**Model**: Sonnet (pinned) — Haiku produced false positive on priority threshold (2026-04-09). High consequence agent.
**Deployed**: F019 (2026-04-06)
**Registered**: F019 (2026-04-06)

### Transition History

| Date | Level | Direction | Reason | Decided By |
|------|-------|-----------|--------|------------|
| 2026-04-06 | Assisted | Registration | Initial registration under Felix governance framework (F019) | Kent Gale |

---

## felix-doc-auditor

**Team**: SuperAdmin (B)
**Scope**: Documentation audit — processes Doc Audit and Weekly Doc Audit issues; classifies each in-scope doc as high-confidence edit (commits directly) or judgment gap (files docs-debt issue); detects missing artifacts
**Current Autonomy Level**: Assisted (Level 1)
**Model**: Sonnet (pinned — judgment-heavy work; promotion to Haiku requires validation per Model Assignment Policy)
**Operating Identity**: `kg-felix-bot` (see Service Accounts section below)
**Deployed**: 2026-05-10 (#105 / mission `felix-doc-auditor-agent-01KR7JK9`)
**Registered**: 2026-05-10 (#105 / mission `felix-doc-auditor-agent-01KR7JK9`)

### Transition History

| Date | Level | Direction | Reason | Decided By |
|------|-------|-----------|--------|------------|
| 2026-05-10 | Assisted | Registration | Initial deployment per #105 / mission `felix-doc-auditor-agent-01KR7JK9`. Planned promotion to Supervised after ~1 week of clean operation per Felix Constitution autonomy promotion process. | Kent Gale |

---

## Service Accounts

Service accounts are GitHub identities Felix agents use for git push and `gh` CLI actions. They provide a separate audit-trail identity from Kent's personal `kentonium3` account, so commits and issue actions performed by agents are unambiguously attributable.

### kg-felix-bot

- **Type**: GitHub bot identity (collaborator on `kentonium3/kg-automation`)
- **GitHub username**: `kg-felix-bot`
- **Email alias**: `kentgale+felix-bot@gmail.com` (routes to `kentgale@gmail.com`)
- **2FA**: enabled
- **Authentication**: classic personal access token with `repo`, `read:org`, `workflow` scopes; configured on office2 under the `claude` user's `gh` auth (`/home/claude/.config/gh/hosts.yml`)
- **Credential record**: see `kg-felix-bot-pat` in [`credential-manifest.json`](<../design/architecture/data/credential-manifest.json>)
- **Currently used by**: `felix-doc-auditor`
- **Established**: 2026-05-11 (#215, after the canary surfaced a gate-violation pattern when bot and human shared an identity)
- **Required PAT type**: classic (not fine-grained — fine-grained PATs restrict access to resources owned by the token's account, and `kg-felix-bot` is a collaborator on the repo, not an owner)
- **Rotation**: annual review, or sooner on suspected compromise. Procedure documented in `kg-felix-bot-pat.expiry_notes` in the credential manifest.
