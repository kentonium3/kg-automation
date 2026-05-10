# Data Model: Felix Doc Auditor Agent

**Mission**: `felix-doc-auditor-agent-01KR7JK9`
**Phase**: 1 (Design & Contracts)

This document defines the entities the agent reads, produces, or coordinates around. There is no database — all entities live in GitHub (issues, labels, comments) or as commits in this repo. State persistence between cron ticks is via the `status:in-progress` label on an audit issue (R-009).

---

## E-001: Audit Issue (input)

The agent's primary input. Created by the existing GitHub Actions workflows.

| Field | Source | Description |
|---|---|---|
| `number` | GitHub | Issue number (e.g., #188) |
| `title` | GitHub | Either `Doc audit: <sha> (<domains>)` (per-merge trigger) or `Weekly doc audit — YYYY-MM-DD` (weekly trigger) |
| `body` | GitHub | Markdown checklist of in-scope docs grouped by `area/*` domain |
| `labels` | GitHub | Always includes `P2-debt`. Per-merge audits also include the affected `area/*` labels. May include `status:in-progress` after the agent claims it. |
| `state` | GitHub | `open` while unprocessed; `closed` after agent finishes |
| `triggering_sha` | parsed from title | The commit SHA that triggered the audit (per-merge only). Used to read the diff for prioritization. |
| `triggering_domains` | derived from `area/*` labels | Domains in scope; if absent, treat as full-scope (weekly pattern) |

**Lifecycle**: created by workflow → claimed by agent (label applied) → processed → closed by agent (with summary comment) → label removed.

---

## E-002: Domain Map (scope contract)

The authoritative scope reference. Read-only from the agent's perspective.

| Field | Source | Description |
|---|---|---|
| Path | repo | `docs/design/architecture/data/doc-domain-map.json` |
| `schema_version` | file | Currently "1.0" |
| `domains` | file | Object mapping `area/*` label name → array of doc paths |
| `last_updated` | file | ISO date — informational |
| `updated_by` | file | Issue or feature ID — informational |

**Used by agent for**: determining the in-scope docs for any audit. The audit issue's `area/*` labels select which domains apply. If no `area/*` label, agent uses all domains (full-scope).

---

## E-003: System State Sources

The "current state" the agent compares docs against. None are mutated by the agent (read-only).

| Source | Path | Used to verify |
|---|---|---|
| Service inventory | `docs/design/architecture/data/service-inventory.json` | Service entries, versions, dependencies, status |
| Agent registry | `docs/constitution/agent-registry.json` | Agent autonomy levels, transition history |
| Hardware inventory | `docs/design/architecture/data/hardware-inventory.json` | Host hardware, OS, GPU, kernel |
| Network topology | `docs/design/architecture/data/network-topology.json` | Network bindings, ports |
| Credential manifest | `docs/design/architecture/data/credential-manifest.json` | Credentials inventory |
| Data flows | `docs/design/architecture/data/data-flows.json` | Data flow definitions |
| `docs/INDEX.md` | repo | Doc index (used for missing-artifact detection) |
| `git log` | local | Recent commits — used for prioritization and to identify dead-reference candidates after file deletions |

---

## E-004: Edit Proposal (intermediate)

Internal data structure the agent builds during processing. Not persisted between cron ticks.

| Field | Description |
|---|---|
| `audit_issue_number` | The originating audit issue # |
| `doc_path` | Repo-relative path to the doc being modified |
| `change_type` | One of: `frontmatter_date`, `version_bump`, `path_rename`, `dead_ref_removal`, `registry_entry_add`, `registry_autonomy_update` |
| `current_value` | What's in the doc now |
| `proposed_value` | What the agent proposes to change it to |
| `evidence_source` | Which system-state source justified this (e.g., "service-inventory.json transcribe-api version field") |
| `confidence` | `high` (auto-edit candidate) or `judgment` (debt-issue candidate) |

At Level 1, all `high` proposals must be approved via WhatsApp before becoming a commit. At Level 2, `high` proposals are committed without approval.

---

## E-005: Audit Commit (output)

A single git commit produced when the agent has one or more approved high-confidence edits to apply.

| Field | Description |
|---|---|
| `subject` | Format: `chore(doc-audit): <one-line summary> (audit: #<N>)` |
| `body` | Bullet list of edits, one per line: `- <doc>: <change>` |
| `footer` | `Refs #<audit-issue-number>` and standard `Co-Authored-By:` |
| `branch` | `main` (no worktree per OpenClaw cron convention) |
| `author` | `claude` (the os user) with the existing git identity used by other felix-admin-* commits |

Multiple proposed edits from a single audit are bundled into one commit (atomicity per FR-002).

---

## E-006: Docs-Debt Issue (output)

Created using the existing `.github/ISSUE_TEMPLATE/docs-debt.md` template. One per gap.

| Section | Source | Notes |
|---|---|---|
| Title | agent | `Docs: <one-line description>` |
| Artifact | agent | Repo-relative path to the doc |
| Gap description | agent | What's missing/outdated/incorrect (specific) |
| Area | agent | Checked items match the audit issue's `area/*` labels |
| Cross-references | agent | Links to: originating audit issue, related docs, related commits |
| **Draft outline** | agent | **The critical field** — specific enough that a downstream Claude Code session can act without further research (FR-003 success criterion). |
| Success criteria | agent | 2-4 verifiable bullet points |
| Labels | agent | `P2-debt`, plus the matching `area/*` label(s), plus `type/debt` |

---

## E-007: Audit Summary Comment (output)

Posted on the originating audit issue before closing it.

```
## Audit summary — <YYYY-MM-DD HH:MM UTC>

**Docs reviewed**: <N>

**Edits committed**:
- `<doc>`: <change> (commit: <sha>)
- `<doc>`: <change> (commit: <sha>)

**Debt issues created**:
- #<N> — <title>
- #<N> — <title>

**Missing artifacts flagged**:
- #<N> — <title>

**Items requiring human review** (could not classify):
- `<doc>`: <reason>

**Approval log** (Level 1 only):
- WhatsApp message: <timestamp>
- Reply: `approve` / `reject` / `skip` / (timeout)
```

---

## E-008: GitHub Label `status:in-progress` (state)

Lock substrate per R-009.

| Field | Description |
|---|---|
| Name | `status:in-progress` |
| Color | (TBD — e.g., yellow `#fbca04`) |
| Description | "An automated agent is currently processing this issue. Manual cleanup if older than 30 min." |
| Created | One-time during deployment via `gh label create` |

The agent applies it when claiming an audit issue and removes it on completion (success, failure, or skip). Cron query filters out issues already carrying it.

---

## E-009: WhatsApp Message Pair (Level 1 only)

For every high-confidence edit proposal at Level 1, the agent produces an outbound message and listens for an inbound reply. Message format defined in [contracts/whatsapp-summary.template.md](./contracts/whatsapp-summary.template.md).

Reply parsing follows the rules in [contracts/whatsapp-reply-vocabulary.md](./contracts/whatsapp-reply-vocabulary.md). Default-deny on 2-hour timeout per NFR-004.

After Level 1 → Level 2 promotion, this entity is no longer produced; the agent commits without approval.

---

## E-010: Activity Log Entry (output)

Per NFR-008, agent activity is logged via the standard OpenClaw agent logging pattern.

| Field | Description |
|---|---|
| Path | `/home/kgale/second-brain/agents/logs/doc-auditor-YYYY-MM-DD.md` |
| Format | One markdown section per audit run (timestamp, audit issue #, summary stats, errors) |
| Frequency | Append per cron tick when an audit is processed |

This log is consumed by `felix-core-digest` (the existing observation digest agent) for cross-agent activity summaries.

---

## Lifecycle (end-to-end)

```
cron fires (60-min tick)
    │
    └─> agent queries open audit issues lacking status:in-progress
        │
        └─> agent picks oldest unprocessed
            │
            ├─> applies status:in-progress label (E-008)
            │
            ├─> reads issue body, labels, triggering_sha (E-001)
            ├─> reads doc-domain-map.json (E-002) → in-scope docs
            ├─> reads system-state sources (E-003)
            │
            ├─> for each in-scope doc:
            │       ├─> compare doc vs system state
            │       └─> build Edit Proposal (E-004): high or judgment
            │
            ├─> [Level 1] WhatsApp summary (E-009 outbound) → wait for reply
            │       ├─> approve → continue
            │       ├─> reject → demote all proposals to debt issues
            │       ├─> skip → close audit with skip note
            │       └─> timeout → demote all proposals to debt issues
            │
            ├─> commit Audit Commit (E-005) for approved high-confidence edits
            ├─> file Docs-Debt Issues (E-006) for judgment items + missing artifacts
            ├─> post Audit Summary Comment (E-007)
            ├─> close audit issue
            ├─> writes Activity Log Entry (E-010)
            │
            └─> removes status:in-progress label
                │
                └─> next cron tick processes the next-oldest unprocessed
```
