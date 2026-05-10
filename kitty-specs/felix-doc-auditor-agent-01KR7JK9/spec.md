---
title: Felix Doc Auditor Agent
mission_id: 01KR7JK9QTHM5F4PD3YC43KDQW
mission_slug: felix-doc-auditor-agent-01KR7JK9
status: draft
target_branch: main
mission_type: software-dev
created: 2026-05-09
source_issue: kentonium3/kg-automation#105
---

# Specification: Felix Doc Auditor Agent

## Executive Summary

Build **`felix-doc-auditor`** — a specialist OpenClaw agent that autonomously processes the documentation audit issues created by the existing `doc-audit-trigger.yml` (per-merge) and `doc-audit-weekly.yml` (weekly cron) GitHub Actions workflows. Replaces the current pattern (manual Claude Code sessions resolving each audit issue) with structured per-doc evaluation: high-confidence edits committed directly, judgment-required gaps converted into structured `docs-debt` issues with actionable outlines, missing artifacts flagged proactively.

The agent's purpose is to make documentation accuracy a system-level capability rather than a human discipline that competes with feature work. As agent autonomy expands across the kg-automation system, downstream agents will rely on accurate architecture docs to make safe operational decisions — drift in those docs becomes a load-bearing risk this agent exists to mitigate.

## Problem Statement

**Current state:**

1. The doc-audit infrastructure (per-commit and weekly) creates scoped audit issues automatically. Each issue lists the documents that should be reviewed for accuracy after some change.
2. These issues sit in the queue with no automated processing. They require manual Claude Code sessions to resolve.
3. Six audit issues are currently open. The oldest (#168, #169) have been open since 2026-04-13. The 2026-04-19 weekly audit (#186) is also open.
4. A separate latent failure: `doc-audit-weekly.yml` skips creating a new weekly issue if any "Weekly doc audit" issue is open. Because #186 has remained open, the weekly cadence has been silently broken since 2026-04-19 — three Sundays of weekly audits not created (`2026-04-26`, `2026-05-03`, `2026-05-10`).
5. Manual processing is variable in thoroughness: high-confidence trivial edits (frontmatter dates, version numbers) get the same human attention as architectural rewrites; missing artifacts are identified only when a human notices.

**Target state:**

1. Audit issue created by existing trigger workflows.
2. `felix-doc-auditor` polls for unprocessed audit issues every 60 minutes.
3. For each in-scope doc, the agent classifies the change required:
   - **High confidence** → edits the file directly, commits atomically
   - **Judgment required** → creates a structured `docs-debt` issue with a draft outline specific enough to act on without further research
4. Agent also detects missing artifacts (deployed agents/services/skills without docs) by comparing inventory data against `doc-domain-map.json` + `docs/INDEX.md`.
5. Agent posts a summary comment on the originating audit issue listing what was edited, what debt issues were created, what missing artifacts were flagged, and any items that could not be classified.
6. Agent closes the audit issue.
7. Weekly cadence restored: weekly audits create new issues every Sunday regardless of whether older weekly issues remain open (scoped to "this week's" issue).

## User Scenarios & Testing

**Primary actors:**

- **Kent** (system owner): receives WhatsApp notifications and (during Level 1 bedding-in) approval requests; consumes the structured `docs-debt` issues the agent creates.
- **Downstream Claude Code sessions**: act on `docs-debt` issues using the agent's draft outline as a starting spec.
- **Other autonomous agents** (future): rely on the architecture docs the auditor keeps accurate.

**Acceptance scenarios:**

1. **AS-001: Per-merge audit, all-trivial edits** — A commit lands on `main` that updates a service version. `doc-audit-trigger.yml` opens audit issue. Within 60 minutes, the agent reads the issue, identifies the affected service-inventory entry, updates the version field and the entry's `last_updated` field, commits, posts a summary comment, closes the audit issue.

2. **AS-002: Per-merge audit, mixed trivial + judgment** — A commit adds a new service. Audit issue opens with several affected docs. The agent updates `service-inventory.json` `last_updated` (trivial), creates a `docs-debt` issue for the missing service entry in `service-inventory.md` narrative section (judgment-required outline), and a separate `docs-debt` issue for the missing service runbook (missing artifact).

3. **AS-003: Weekly full-scope audit** — Sunday morning, the weekly workflow creates an audit issue with the full doc checklist. The agent processes each doc, makes any high-confidence frontmatter updates, creates debt issues for any drift detected, summarizes, closes.

4. **AS-004: Backlog drain on first deploy** — On first cron tick after deploy, the agent finds 6 open audit issues. It processes them oldest-first. A subsequent cron tick (60 min later) confirms zero unprocessed issues remain.

5. **AS-005: Doc unreadable** — The agent attempts to read a doc listed in the domain map; the file is missing or has read errors. The agent logs the failure, skips the doc, includes it in the audit summary as "could not read", and continues with the rest of the scope. The audit issue is closed but with a flagged item for human follow-up.

6. **AS-006: Level 1 approval, accepted** — Agent at Assisted level produces a proposed edit. Sends a WhatsApp summary. Kent replies "approve". Agent commits the edit and proceeds.

7. **AS-007: Level 1 approval, rejected** — Same as AS-006 but Kent replies "reject" or "skip". Agent does not commit; instead converts the proposed edit into a `docs-debt` issue for human handling and proceeds with next doc.

8. **AS-008: Level 1 approval, no response** — Agent sends WhatsApp summary; no reply within 2 hours. Agent treats silence as deny: converts the proposed edit into a `docs-debt` issue and moves on. Records the timeout in the audit summary.

9. **AS-009: Weekly cadence regression test** — A weekly audit issue from a previous week remains open. Sunday's cron fires; the workflow creates a new weekly audit issue (scoped to the current week).

## Functional Requirements

| ID | Requirement | Status |
|---|---|---|
| FR-001 | Agent must poll for unprocessed audit issues every 60 minutes via cron, identify in-scope docs from each issue's body and `area/` labels, and read the merged commit diff (when present) to *prioritize* — but not limit — scope. | Required |
| FR-002 | For each in-scope doc, agent must identify changes that meet the high-confidence threshold (frontmatter `last_updated`/`last_validated`/`revision`, service version numbers when diff confirms an upgrade, file paths after a rename in the diff, `updated_by` references for new entries, agent registry autonomy levels when an explicit governance decision is in the diff, dead-reference removal after file deletion, new agent registry entries when a new agent is in the diff) and commit them atomically with a message referencing the audit issue number. | Required |
| FR-003 | For each gap requiring judgment (architectural prose, new sections/runbooks, ambiguous source-of-truth conflicts), agent must create a `docs-debt` issue using `.github/ISSUE_TEMPLATE/docs-debt.md` populated with: what needs to change, why, cross-referenced docs, and a draft outline specific enough to act on without further research. One debt issue per gap; correct `area/*` labels and `type/debt` applied. | Required |
| FR-004 | Agent must detect missing artifacts by comparing what is deployed (service-inventory, agent-registry) against what is documented (`doc-domain-map.json`, `docs/INDEX.md`). A doc is considered missing only if absent — thin or stale docs are FR-003 gaps, not FR-004 missing artifacts. Missing-artifact detection runs on every audit regardless of scope. | Required |
| FR-005 | After processing, agent must post a structured summary comment on the originating audit issue (docs reviewed count, edits made with commit hash, debt issues created with numbers and links, missing artifacts flagged, items that could not be classified) and close the audit issue. At Assisted level, the close requires confirmation. | Required |
| FR-006 | A `doc-audit` skill must exist at `scripts/openclaw/skills/doc-audit/SKILL.md` encoding: domain map interpretation, the high-confidence vs judgment threshold, debt issue template field requirements, how to compare a doc against system state (which sources to consult), commit message format for audit commits, and error handling for unreadable/locked docs. The skill must be self-contained — the agent can run a full audit using only this skill plus the domain map. | Required |
| FR-007 | An ops runbook must exist at `docs/runbooks/doc-auditor-ops.md` covering: how the agent operates and when it runs, how to manually trigger an audit against a specific issue number, how to add a document to the domain map, how to adjust the confidence threshold, troubleshooting (missed docs, false positives, GitHub API failures). The agent must be registered in `docs/constitution/AGENT-REGISTRY.md` at Assisted (Level 1). The agent must appear in `docs/design/architecture/data/service-inventory.json`. | Required |
| FR-008 | The `doc-audit-weekly.yml` GitHub Actions workflow must be modified so that the "skip if open weekly audit exists" check is scoped to *this week's* issue (e.g., title match for the current ISO date), not any open weekly audit. After this fix, a stale older weekly issue must not block creation of new weekly audit issues. | Required |
| FR-009 | At Assisted (Level 1), agent must propose all edits via WhatsApp summary message and parse a reply (approve/reject/skip) before committing. Reply parsing must follow the same pattern used by the existing daily habit check-in reply parser. Time-based default-deny (2-hour timeout): silence converts the edit into a `docs-debt` issue. | Required |
| FR-010 | The agent must process the existing 6 open audit issues retroactively on first cron tick after deployment (no special "first run" mode — the cron's normal scan picks them up because they are open and unprocessed). Stale audit issues are processed by comparing current docs against current system state; the (possibly old) commit diff serves only as a prioritization hint, not as a scope filter. | Required |

## Non-Functional Requirements

| ID | Requirement | Threshold | Status |
|---|---|---|---|
| NFR-001 | Polling interval | Every 60 minutes (±5 min jitter acceptable) | Required |
| NFR-002 | Per-audit-issue processing time | ≤ 10 minutes wall-clock for a typical post-merge audit (≤ 5 docs in scope); ≤ 30 minutes for a weekly full-scope audit | Required |
| NFR-003 | Per-doc failure isolation | A doc that fails to read must not abort the audit. Failure is logged, doc is skipped, summary records the failure. | Required |
| NFR-004 | Level-1 approval timeout | 2 hours from WhatsApp message to default-deny conversion | Required |
| NFR-005 | LLM model | Sonnet (cost/judgment trade-off appropriate for an agent committing to architecture docs) | Required |
| NFR-006 | Backlog drain | All 6 currently-open audit issues processed within the first 6 cron ticks (≤ 6 hours) post-deploy | Required |
| NFR-007 | Audit trail | Every commit must reference the originating audit issue number; every debt issue must link to the originating audit issue; every audit summary comment must list all artifacts created | Required |
| NFR-008 | Operational logging | Agent activity logged via standard OpenClaw agent logging to `/home/kgale/second-brain/agents/logs/` (consistent with existing felix-admin-* agents) | Required |

## Constraints

| ID | Constraint | Status |
|---|---|---|
| C-001 | Constitutional autonomy: deploys at Assisted (Level 1). Promotion to Supervised (Level 2) is a separate governance decision expected ~1 week post-deploy. The agent itself never self-promotes. | Required |
| C-002 | Scope limit: agent never edits the Felix Constitution (`docs/constitution/FELIX-CONSTITUTION.md`), CLAUDE.md (any), credential files (`.env`, `credentials.json`), or `kitty-specs/` / `.kittify/` directories. | Required |
| C-003 | Privacy boundary: agent never reads, writes, references, or logs anything under `~/second-brain/notes/04-Growth/_private/` regardless of trigger source. | Required |
| C-004 | Reversibility: all operations reversible. File edits go through git (revertible). Issue mutations (creates, comments, closes) are reversible via gh CLI. No destructive operations on disk or external services. | Required |
| C-005 | Scope authority: in-scope docs are determined by `docs/design/architecture/data/doc-domain-map.json` + the audit issue's `area/*` labels. Agent does not expand scope beyond what the map defines without explicit instruction. | Required |
| C-006 | Issue creation policy: when filing `docs-debt` issues for `area/biz-ops` gaps, agent must include a flag for human confirmation before filing — business-ops docs may be intentionally private or informal. | Required |
| C-007 | Tooling: agent uses `gh` CLI for all GitHub interactions (per repo convention; MCP GitHub auth is unreliable). | Required |

## Success Criteria

| ID | Criterion |
|---|---|
| SC-001 | Within one week of deploy, all audit issues created in that week are closed by the agent (not by humans) — measured by checking which user closed each `Doc audit:` and `Weekly doc audit` issue. |
| SC-002 | The 6 currently-open audit issues are processed within 6 hours of deploy (per NFR-006). |
| SC-003 | At least one `docs-debt` issue created by the agent is acted on by a downstream Claude Code session using only the agent's draft outline (no extra research session needed) — proves outline quality (FR-003 success criterion). |
| SC-004 | The first weekly audit after the FR-008 fix lands creates a new weekly audit issue even though older weekly audit issues remain open. |
| SC-005 | Agent makes zero edits to Felix Constitution, CLAUDE.md, or credential files (validated by inspecting commit diffs in the first 30 days post-deploy). |
| SC-006 | Promotion review at end of week 1 has a complete audit trail: every proposed edit shows a WhatsApp message + reply or timeout; every commit references an audit issue; every debt issue links back. |

## Key Entities

| Entity | Description |
|---|---|
| **Audit issue** | GitHub issue created by `doc-audit-trigger.yml` (per-merge, titled `Doc audit: <sha>`) or `doc-audit-weekly.yml` (titled `Weekly doc audit — YYYY-MM-DD`). Body contains a checklist of in-scope docs grouped by domain. Labeled `P2-debt` plus zero or more `area/*` labels. The agent's input. |
| **Domain map** | `docs/design/architecture/data/doc-domain-map.json` — maps area labels to lists of doc paths. The scope contract for any audit. |
| **High-confidence edit** | A direct edit to a doc where the correct value is unambiguous and deterministic (frontmatter date, version number after a confirmed upgrade, path rename after a confirmed file move). Committed atomically with audit-issue reference. |
| **Docs-debt issue** | GitHub issue created by the agent using `.github/ISSUE_TEMPLATE/docs-debt.md` for a gap that requires judgment. Contains a draft outline specific enough to act on. |
| **Missing artifact** | A doc that *should* exist (deployed agent without runbook, new service without architecture entry, new skill without SKILL.md reference) but does not. Surfaced as a `docs-debt` issue. |
| **Audit summary comment** | The agent's structured comment on the originating audit issue listing all outputs (edits, debt issues, missing artifacts, unclassifiable items) before closing. |
| **`doc-audit` skill** | The skill at `scripts/openclaw/skills/doc-audit/SKILL.md` that encodes the audit logic. Self-contained — the agent runs a full audit using only this skill plus the domain map. |

## Edge Cases

- **Stale audit issue**: target diff (the commit that triggered the audit) was merged weeks ago. Agent compares current docs against current system state; the diff is just a prioritization hint, not a scope filter. Stale audits are still meaningful audits.
- **Multiple cron ticks during one audit**: an audit is mid-processing when the next cron fires. Agent must use a lock or "in-progress" marker to avoid double-processing.
- **GitHub API rate limiting**: hitting rate limits should not corrupt state. Agent backs off and retries on the next tick.
- **Domain map out of date**: a doc exists in the repo but is not listed in the domain map. FR-004 missing-artifact detection catches this for deployed agents/services; for orphan docs, the agent does nothing (the map is the scope contract per C-005).
- **WhatsApp delivery failure at Level 1**: agent cannot send the approval message. Agent does not commit (Assisted level requires confirmation). Issue stays open; failure logged. Recovery: human runs the agent with `--bypass-whatsapp` flag (out of scope for v1; flagged in plan).
- **Conflicting edits between agent and human**: agent prepares an edit; human pushes a conflicting change before the agent commits. Agent must detect the conflict (e.g., via `git pull --rebase` before commit), abort the proposed edit, and convert it to a `docs-debt` issue.
- **Audit issue with no `area/*` labels**: weekly audits intentionally have no `area/*` labels (full scope). Agent treats absence as full-scope per FR-001.
- **Promotion to Level 2 mid-audit**: governance decision changes autonomy level while an audit is in progress. Agent completes the in-flight audit at the autonomy level it started with; subsequent audits use the new level.

## Assumptions

| ID | Assumption |
|---|---|
| A-001 | The existing daily-habit-checkin WhatsApp reply parser (`felix-admin-habits`) is reusable as a model for the doc-auditor's approval reply parsing. The parser's pattern (regex match on configured keywords, timeout fallback) is suitable for approve/reject/skip responses. |
| A-002 | `gh` CLI is installed and authenticated on office2 with `issues: write` scope. (Confirmed: claude user's existing crons already use `gh`.) |
| A-003 | The `doc-domain-map.json` is the single source of truth for audit scope. If new docs need to be audited, they are added to the map (FR-006 troubleshooting documents this). |
| A-004 | The `.github/ISSUE_TEMPLATE/docs-debt.md` template exists and is the standard format for debt issues. (Plan phase verifies this; if missing, plan adds it.) |
| A-005 | OpenClaw cron scheduling supports a 60-minute interval and per-agent invocation contracts (pattern: `felix-admin-tasker` runs every 4 hours, so finer cadences are supported). |
| A-006 | The agent runs as the `claude` user on office2, with the same SSH/git credentials and gh auth used by other admin agents. |
| A-007 | "Felix Constitution" and "CLAUDE.md" file paths are stable enough to hardcode in the agent's exclusion list. (Both are top-of-tree well-known paths.) |
| A-008 | The Restic backup at `/mnt/backups/restic-repo` covers `/data/services/openclaw/` and `/home/claude/`, providing recovery for the agent's logs and any state files. (Confirmed during issue #80 backup investigation.) |

## Out of Scope

- ❌ **Full System State Auditor** (RFC #106 Approach C) — separate future feature. This agent audits *documentation*, not full system state.
- ❌ **Automated doc *writing* beyond the draft outline** — the agent identifies gaps and outlines them; Claude Code (or future agents) writes the actual prose.
- ❌ **Auditing the second-brain vault** (`~/second-brain/`) — strictly out of scope per privacy boundary (C-003).
- ❌ **Auditing `kitty-specs/` or `.kittify/` directories** — managed exclusively by spec-kitty.
- ❌ **Edits to the Felix Constitution or CLAUDE.md guardrails** — never autonomously edited (C-002).
- ❌ **Self-promotion across autonomy levels** — promotion from Assisted → Supervised is a governance decision Kent makes (C-001), not a self-service operation.
- ❌ **Direct WhatsApp interaction with Kent for non-approval purposes** — agent only sends approval messages and audit summaries, not free-form conversation.
- ❌ **Building or modifying the `felix-admin-habits` reply parser** — the doc-auditor reuses the *pattern* (Assumption A-001) but does not modify the existing parser.

## Architecture Impact

| File | Change |
|---|---|
| `docs/design/architecture/data/service-inventory.json` | Add `felix-doc-auditor` agent entry; bump `last_updated`/`updated_by` |
| `docs/design/architecture/data/doc-domain-map.json` | Add `doc-auditor-ops.md` runbook reference (and confirm SKILL.md exists if mapped) |
| `docs/constitution/AGENT-REGISTRY.md` | Add `felix-doc-auditor` at Assisted (Level 1) with autonomy transition_history seeded |
| `docs/runbooks/doc-auditor-ops.md` | New file — ops runbook (FR-007) |
| `scripts/openclaw/skills/doc-audit/SKILL.md` | New file — agent skill (FR-006) |
| `scripts/openclaw/agents/felix-doc-auditor/` | New directory — agent workspace (IDENTITY.md, SOUL.md, AGENTS.md, TOOLS.md per `docs/runbooks/openclaw-agent-setup.md`) |
| `.github/workflows/doc-audit-weekly.yml` | Modify the "skip if exists" check to scope to current-week issue (FR-008) |
| OpenClaw `openclaw.json` registration on office2 | Register the new agent (per `docs/runbooks/openclaw-agent-setup.md`) |

JSON files updated with `updated_by` set to this issue/mission identifier; markdown views match JSON sources.

## Constitutional Compliance

- **Autonomy level (initial)**: Assisted (Level 1) — all edits proposed via WhatsApp before committing; all debt issues shown before filing; audit issue close requires confirmation.
- **Autonomy lifecycle**: Expected promotion to Supervised (Level 2) ~1 week post-deploy after evidence review (per Felix Constitution autonomy-promotion process). Promotion is a separate governance decision; this mission delivers Level 1 only.
- **Scope of action**: Documentation files only — no agent configs (other than self-registration), no deployed services, no credential files, no second-brain.
- **Failure behavior**: If any doc read fails, agent logs the failure, skips that doc, notes it in the audit summary, never fails silently.
- **Privacy**: `~/second-brain/notes/04-Growth/_private/` never read or referenced.
- **Tool use**: `gh` CLI only for GitHub; standard file I/O for repo edits; standard git for commits.

## Risk Considerations

| Risk | Impact | Mitigation |
|---|---|---|
| Agent makes a high-confidence edit that turns out to be wrong | Incorrect doc — detected on next review or audit | Assisted (Level 1) means all edits confirmed first; all edits git-committed and reversible; confidence threshold errs toward creating a debt issue rather than autonomous edit |
| Debt issue volume too high — queue becomes noise | Debt issues ignored, defeating purpose | Missing-artifact detection bounded by what's actually deployed; draft-outline requirement makes each issue immediately actionable; one-issue-per-gap rule prevents duplicates |
| Domain map becomes single point of failure for audit scope | Docs not in map escape auditing permanently | FR-004 missing-artifact detection catches deployed agents/services without docs even if the map doesn't list them yet |
| WhatsApp reply parser produces false positive (interprets unrelated message as approval) | Wrong edit committed | Reply must arrive on the correct conversation thread within the timeout window; parser uses configured keywords (approve/reject/skip), not freeform NLU; Level 1 is short-lived (~1 week) |
| Cron tick races with itself (long-running audit) | Double-processing same issue | Use lock file or in-progress marker (plan phase decides mechanism) |
| Promotion to Level 2 happens without sufficient evidence | Premature autonomy increase | Promotion gated by 30-day minimum evidence rule per Felix Constitution; this mission only delivers Level 1 — promotion is out of scope |

## Notes for Planning

The following materials should be studied during the plan phase before writing tasks:

1. **`scripts/openclaw/agents/felix-admin-habits/AGENTS.md`** — pattern for cron-triggered agent that reads structured inputs and produces structured outputs with constitutional compliance.
2. **`scripts/openclaw/agents/felix-admin-habits/`** WhatsApp reply parser implementation — the exact mechanism Assumption A-001 relies on.
3. **`scripts/openclaw/agents/felix-core-digest/AGENTS.md`** — pattern for an agent that reads system state and produces summarized output without taking user-facing actions.
4. **`docs/runbooks/openclaw-agent-setup.md`** — required workspace files (IDENTITY.md, SOUL.md, AGENTS.md, TOOLS.md), `openclaw.json` registration steps, verification checklist. **Standing requirement** per CLAUDE.md.
5. **`docs/design/architecture/data/doc-domain-map.json`** — agent's scope contract. Plan must understand its structure to specify the audit logic.
6. **`.github/ISSUE_TEMPLATE/docs-debt.md`** — debt issue template format (verify it exists; if not, plan creates it).
7. **All current in-scope documentation** — every file listed in the domain map. Plan must understand what "current state" looks like for each doc type before specifying how to compare against it.
8. **`docs/constitution/agent-registry.json`** — `transition_history` structure the agent must read to detect autonomy level changes.
9. **F012 skill-authoring conventions** — the `doc-audit` skill must follow the project's skill-authoring pattern.
10. **`.github/workflows/doc-audit-weekly.yml`** — current implementation; the FR-008 fix needs to scope the duplicate check to the current week's issue title.
