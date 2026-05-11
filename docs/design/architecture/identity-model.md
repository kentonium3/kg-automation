---
title: Identity Model
doc_type: reference
status: approved
last_updated: '2026-05-11'
updated_by: '#227'
---

# Identity Model

## Dual Google Identity

Kent operates with two Google identities:

| Identity | Scope | Vikunja Label | Calendar | Status |
|----------|-------|---------------|----------|--------|
| Personal | Personal life, health, growth | `personal` (blue, #2196f3) | Personal Google Calendar | Label exists (F001); calendar integration planned (F012) |
| Intentional LLC | Business, consultancy | `intentional` (green, #4caf50) | Intentional Workspace | Label exists (F001); routing deferred to Phase 3 |

## How Identity Routing Works

1. Tasks in Vikunja are tagged with `personal` or `intentional` labels
2. When calendar integration arrives (F012), the label determines which Google identity receives the calendar event
3. When WhatsApp integration arrives (F003-F006), the intent parser will infer identity from context and apply the label

## Current State (Post-F001)

- Both labels exist in Vikunja and are selectable on any task
- No automated routing yet — labels are applied manually
- Full routing is a Phase 3 capability

## Vikunja Project Structure

```
Everyday
├── Inbox           (default landing zone)
└── Someday         (deferred tasks)

Personal Growth & Transformation    (Area)
Business Acquisition                (Area)
└── CT-90day                        (subproject)
Health & Conditioning               (Area)
Intentional LLC                     (Area)
Metal Casework                      (Area)
```

Areas are organizational parent projects — convention is to place tasks in subprojects, not directly in Area projects.

## Agent Service Accounts

Felix agents act in GitHub under a dedicated service-account identity (`kg-felix-bot`), distinct from Kent's personal `kentonium3` account. Splitting human and agent identities keeps the GitHub event timeline unambiguously attributable: any commit, issue comment, label change, or PR action performed by an agent is visible as `kg-felix-bot` and cannot be confused with a Kent-driven action. This separation is also load-bearing for the `felix-doc-auditor` Level-1 gate (see [AGENTS.md §8.6](<../../../scripts/openclaw/agents/felix-doc-auditor/AGENTS.md>)), where the agent must verify that an approval label was applied by a human and not by itself.

| Field | Value |
|---|---|
| GitHub username | `kg-felix-bot` |
| Repo role | Collaborator on `kentonium3/kg-automation` |
| Currently used by | `felix-doc-auditor` |
| Credential | `kg-felix-bot-pat` — see [`credential-manifest.json`](<./data/credential-manifest.json>) |

Canonical registry: [`AGENT-REGISTRY.md` §Service Accounts](<../../constitution/AGENT-REGISTRY.md#service-accounts>).

Future Felix agents may share `kg-felix-bot` or get their own dedicated service accounts, depending on whether per-agent audit-trail separation becomes useful.
