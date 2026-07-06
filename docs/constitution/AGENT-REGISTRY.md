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
**Model**: Haiku (evaluating) — held on haiku as the static baseline. #662's reliability fix was ENVIRONMENTAL (exec strips PYTHONPATH; fixed by self-contained `cd /home/claude/kg-automation && python3 -m scripts.…` invocations, corrects #658), NOT a model deficit — haiku's "missing infrastructure" output was a downstream misread of ModuleNotFoundError. Briefly moved to sonnet 2026-07-06 then reverted same day; haiku sufficiency under ~1-week evaluation (#671).
**Deployed**: F008 (2026-03-31)
**Registered**: F012 (2026-04-01)

### Transition History

| Date | Level | Direction | Reason | Decided By |
|------|-------|-----------|--------|------------|
| 2026-04-01 | Assisted | Registration | Initial registration under Felix governance framework (F012) | Kent Gale |
| 2026-07-06 | Assisted | Model hold | harden-inbox-capture-01KWVGZM (#662): briefly moved to Sonnet then reverted to Haiku same day — the reliability fix was environmental (self-contained invocations, corrects #658), not a model deficit; held on haiku, model choice deferred to evaluation (#671) | Kent Gale |

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

## felix-admin-calendar

**Team**: SuperAdmin (B)
**Scope**: Calendar substrate — event creation via `gog`/Google Calendar, clarification reply handler for incomplete inbox-captured events; future home for calendar credential health, recurrence, attendee tracking
**Does NOT handle**: Inbox classification (felix-admin-capture), habits, task enrichment (felix-admin-tasker), escalation, briefings
**Current Autonomy Level**: Assisted (Level 1)
**Model**: Haiku 4.5 (optimizable) — Routine deterministic-validator-driven workflow, matches capture / habits / tasker shape. Re-evaluate if accuracy is poor in production.
**Deployed**: [#579](https://github.com/kentonium3/kg-automation/issues/579) / mission `felix-calendar-subagent-extraction-01KTTA33` (2026-06-11)
**Registered**: [#579](https://github.com/kentonium3/kg-automation/issues/579) / mission `felix-calendar-subagent-extraction-01KTTA33` (2026-06-11)

### Transition History

| Date | Level | Direction | Reason | Decided By |
|------|-------|-----------|--------|------------|
| 2026-06-11 | Assisted | Registration | Extracted from `main/AGENTS.md` per [#579](https://github.com/kentonium3/kg-automation/issues/579) to restore WhatsApp reply relay; broader calendar-substrate charter per mission spec discovery Q2 = A+C (mission `felix-calendar-subagent-extraction-01KTTA33`) | Kent Gale |

---

## felix-doc-auditor

**Team**: SuperAdmin (B)
**Scope**: Documentation audit — processes Doc Audit and Weekly Doc Audit issues; classifies each in-scope doc as high-confidence edit (commits directly) or judgment gap (files docs-debt issue); detects missing artifacts
**Current Autonomy Level**: Assisted (Level 1)
**Model**: Haiku 4.5 (pinned — downshifted from Sonnet by #343 because judgment calls are now narrow and prompt-scoped post-scripts-first refactor; promotion back to Sonnet would require validation per Model Assignment Policy)
**Operating Identity**: `kg-felix-bot` (see Service Accounts section below)
**Deployed**: 2026-05-10 (#105 / mission `felix-doc-auditor-agent-01KR7JK9`)
**Registered**: 2026-05-10 (#105 / mission `felix-doc-auditor-agent-01KR7JK9`)
**Operational Status**: ⏸ **Suspended indefinitely 2026-05-26** (timer disabled + interpretation flags `enabled=false` + GH Actions `disabled_manually`; reactivation gated on [#137](https://github.com/kentonium3/kg-automation/issues/137) cost-control epic)

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
