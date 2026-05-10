# Research: Felix Doc Auditor Agent

**Mission**: `felix-doc-auditor-agent-01KR7JK9`
**Phase**: 0 (Outline & Research)

This document consolidates the research needed to ground Phase 1 design and remove every `[NEEDS CLARIFICATION]` from the Technical Context.

---

## R-001: OpenClaw skills directory layout

**Decision**: New skill at `scripts/openclaw/skills/doc-audit/SKILL.md`. Convention is one directory per skill containing `SKILL.md`. The deployed copy on office2 lives at `~/.openclaw/skills/doc-audit/SKILL.md` (per the consumption pattern shown in `felix-admin-habits/AGENTS.md` line: `cat ~/.openclaw/skills/vikunja-api/SKILL.md`).

**Rationale**: Confirmed by inspection — `scripts/openclaw/skills/` already contains five existing skills (`escalation`, `skill-author`, `task-intelligence`, `vikunja-api`, `whisper`). Pattern is established. The `skill-author` skill itself encodes how to write a conforming `SKILL.md`.

**Alternatives considered**:
- Inline skill content in agent's `AGENTS.md` — rejected; reusability and reviewability suffer.
- Co-located skill inside `agents/felix-doc-auditor/` — rejected; doesn't match established pattern.

**Source**: `scripts/openclaw/skills/`, `scripts/openclaw/skills/skill-author/SKILL.md`.

---

## R-002: Agent workspace required files and structure

**Decision**: `scripts/openclaw/agents/felix-doc-auditor/` will contain the standard four files:

| File | Required | Purpose |
|---|---|---|
| `AGENTS.md` | Yes | Standing orders — full operational instructions |
| `IDENTITY.md` | Yes | Identity card (name, emoji, creature, vibe) |
| `SOUL.md` | Yes | Voice, values, privacy boundaries |
| `TOOLS.md` | Yes | Tool boundary contract (resources, paths, APIs) |

`USER.md` is optional and is included in `felix-admin-habits/` because that agent communicates directly with Kent's daily flow. felix-doc-auditor only contacts Kent via approval messages, so USER.md is included for consistency.

**Rationale**: `docs/runbooks/openclaw-agent-setup.md` specifies the required + optional file list. All existing felix-admin-* agents follow this pattern.

**Source**: `docs/runbooks/openclaw-agent-setup.md`, `scripts/openclaw/agents/felix-admin-habits/`.

---

## R-003: Two-registration requirement

**Decision**: Agent registration is a **two-step** process per `docs/runbooks/openclaw-agent-setup.md`:

1. **Governance registry** (`docs/constitution/agent-registry.json` + `AGENT-REGISTRY.md`) — the kg-automation record of identity, autonomy level, team. Lives in this repo.
2. **OpenClaw config** (`/home/claude/.openclaw/openclaw.json` on office2) — how OpenClaw discovers and runs the agent. Without this, OpenClaw delegation fails with "Unknown agent id."

Both must be updated for the agent to actually function. The runbook is explicit: "Neither is sufficient alone."

**Rationale**: Documented standing requirement in `docs/runbooks/openclaw-agent-setup.md`. CLAUDE.md restates it as a standing requirement: "Any work that deploys, modifies, or registers an OpenClaw agent must read `docs/runbooks/openclaw-agent-setup.md` first."

**Source**: `docs/runbooks/openclaw-agent-setup.md`.

---

## R-004: AGENT-REGISTRY.md entry structure

**Decision**: New entry follows the existing per-agent section template:

```markdown
## felix-doc-auditor

**Team**: SuperAdmin (B)   [TBD — confirm team during implementation; likely SuperAdmin given the pattern]
**Scope**: Documentation audit — classifies, edits, and files debt issues against doc-domain-map scope
**Current Autonomy Level**: Assisted (Level 1)
**Model**: Sonnet (pinned — judgment-heavy work; promotion to Haiku requires validation per Model Assignment Policy)
**Deployed**: 2026-05-09 (#105 / mission 01KR7JK9)
**Registered**: 2026-05-09 (#105 / mission 01KR7JK9)

### Transition History

| Date | Level | Direction | Reason | Decided By |
|------|-------|-----------|--------|------------|
| 2026-05-09 | Assisted | Registration | Initial deployment per #105 / mission 01KR7JK9; planned promotion to Supervised after ~1 week of clean operation | Kent Gale |
```

The corresponding JSON entry in `agent-registry.json` follows the same shape. The model is **pinned** to Sonnet per the Model Assignment Policy — Haiku is the default for new agents but doc-auditor's judgment-heavy work (edit-vs-debt threshold, debt-issue outline drafting) warrants Sonnet, and the policy requires validation before any future move to a cheaper model.

**Rationale**: Inspection of existing `felix-admin-capture` and `felix-admin-habits` entries shows this exact section structure. Model Assignment Policy section in `AGENT-REGISTRY.md` documents the Pinned/Optimizable distinction.

**Source**: `docs/constitution/AGENT-REGISTRY.md`.

---

## R-005: doc-domain-map.json structure

**Decision**: Existing schema is used unchanged. The map keys are `area/*` label names; values are arrays of doc paths.

**Current state**: Schema version 1.0, `last_updated: 2026-04-08`, `updated_by: #104`. ~50 docs across 8 domains: `area/infrastructure` (16), `area/security` (7), `area/felix-core` (9), `area/ea` (2), `area/task-intel` (3), `area/content` (6), `area/docs` (12), `area/biz-ops` (3).

**Implementation impact**: As part of FR-007, this mission adds `docs/runbooks/doc-auditor-ops.md` to `area/felix-core` (since it documents an OpenClaw agent that operates on the documentation system). Updates `last_updated` and `updated_by`.

**Rationale**: Inspection.

**Source**: `docs/design/architecture/data/doc-domain-map.json`.

---

## R-006: docs-debt issue template structure

**Decision**: Template at `.github/ISSUE_TEMPLATE/docs-debt.md` is used **unchanged**. It already has the right shape.

Template sections:
1. **Artifact** — path to the doc (existing or proposed)
2. **Gap description** — what's missing/outdated/incorrect
3. **Area** — checklist of `area/*` labels
4. **Cross-references** — related docs/issues/PRs
5. **Draft outline** — suggested structure or content for the fix
6. **Success criteria** — how to verify the gap is resolved

Default labels: `P2-debt`. Default title prefix: `Docs:`. The agent must populate all six sections; the **Draft outline** field is the FR-003 critical success criterion (specific enough to act on without further research).

**Rationale**: Existing template matches the spec's FR-003 requirements precisely. No modifications needed.

**Source**: `.github/ISSUE_TEMPLATE/docs-debt.md`.

---

## R-007: WhatsApp pattern (copied from felix-admin-habits)

**Decision**: doc-auditor's WhatsApp interaction follows the `felix-admin-habits` pattern:

- **Identity header**: every outbound message starts with `Sent by felix-doc-auditor:sonnet` followed by a blank line.
- **Plain-text format**: numbered lists, no emoji spam, no motivational filler.
- **Send mechanism**: standard OpenClaw send-message tool (used by all felix-admin-* agents).
- **Reply parsing**: agent reads incoming WhatsApp messages addressed to it, parses structured intent (e.g., `approve`, `reject`, `skip`, `approve all`, `reject 2,3`). Implementation is embedded in `AGENTS.md` for this agent (per planning decision Q3 — copy not extract).

**Reply vocabulary** (initial, to be refined during implementation):

| Reply | Action |
|---|---|
| `approve` (or `yes`, `ok`, `go`) | Commit the proposed edits |
| `reject` (or `no`, `stop`) | Convert proposal into docs-debt issue; do not commit |
| `skip` | Skip this audit; close issue with summary noting the skip |
| `approve N` (e.g., `approve 1,3`) | Commit only listed proposals; defer rest as debt issues |
| (no reply within 2h) | Treat silence as deny per NFR-004 |

**Rationale**: Pattern is established in `felix-admin-habits/AGENTS.md`. Copying preserves consistency and avoids the runtime IPC complexity of cross-agent calls.

**Alternatives considered**:
- Extract into shared skill — deferred to a future feature (per planning Q3).
- Direct call to felix-admin-habits parser — rejected (brittle cross-agent coupling).

**Source**: `scripts/openclaw/agents/felix-admin-habits/AGENTS.md`.

---

## R-008: GitHub API rate limit headroom

**Decision**: Per-audit GitHub API call budget is comfortably under the rate limit. No mitigation needed beyond standard error handling.

**Estimate** (per typical post-merge audit, ~5 docs in scope):
- `gh issue view <audit#>`: 1 call
- `git log` / `git diff` for the merged commit: local, no API
- Read each in-scope doc: local file reads (no API)
- Apply `status:in-progress` label: 1 call
- Per high-confidence edit: 0 API (file edits are local; commit happens via local git)
- Per docs-debt issue created: 1 call (`gh issue create`)
- Per audit summary comment: 1 call (`gh issue comment`)
- Close audit issue: 1 call (`gh issue close`)
- Remove `status:in-progress` label: 1 call

Worst-case (full weekly audit, ~25 docs, ~10 debt issues): ~15 API calls per audit. With 24 audits/day theoretical max (one per cron tick), that's 360 API calls/day — vs the 5000/hour authenticated rate limit. Not a concern.

**Mitigation if hit**: standard exponential backoff on `gh` errors; agent leaves the audit in `status:in-progress` and the next cron tick retries.

**Source**: GitHub REST API documentation; spec NFR-006.

---

## R-009: Concurrency control via GitHub label

**Decision**: Agent applies the GitHub label `status:in-progress` to an audit issue when it begins processing it; removes the label when done.

- Cron query for unprocessed audits: `gh issue list --label "P2-debt" --state open --search "Doc audit OR Weekly doc audit" --json number,labels` — filter out any with `status:in-progress` already applied.
- Stale-lock recovery: any audit issue carrying `status:in-progress` for >30 min is presumed crashed. Manual cleanup: `gh issue edit <#> --remove-label "status:in-progress"`. The ops runbook (FR-007) documents this.
- The label `status:in-progress` is created as part of this mission's deployment (one-time `gh label create`).

**Rationale**: Per planning Q1 decision. Survives crashes, visible in UI, no on-disk state needed.

**Alternatives considered** (per planning):
- Lockfile on disk: rejected (stale-lock + on-disk state liability).
- Idempotent processing without locks: rejected (still want to avoid double WhatsApp messages and duplicate debt issues; idempotency is a defensive layer not a primary control).
- OpenClaw native overlap prevention: not researched; the GitHub label is the safety net regardless.

**Source**: planning Q1.

---

## R-010: Cron interval and OpenClaw scheduling

**Decision**: Register the agent in `~/.openclaw/openclaw.json` with a 60-minute cron schedule, matching the existing `openclaw-cron` pattern used by `felix-admin-tasker`. Specific cron expression: `0 * * * *` (every hour at the top of the hour).

The 60-minute interval is per NFR-001. Existing precedent in service-inventory.json shows `felix-admin-tasker` runs `0 */4 * * *` (every 4 hours), so finer cadences are supported.

**Rationale**: per planning Q1 / spec NFR-001. Consistency with existing OpenClaw cron agents.

**Source**: `docs/design/architecture/data/service-inventory.json` (felix-admin-tasker entry); planning interrogation.

---

## R-011: Agent deploy mechanism (repo → office2)

**Decision**: Source-of-truth for the agent's workspace files is this repo at `scripts/openclaw/agents/felix-doc-auditor/`. The deployed copy on office2 lives at `/data/services/openclaw/felix-doc-auditor/` per `docs/runbooks/openclaw-agent-setup.md`.

Deploy = `git pull` on office2 (the repo is already cloned at `/home/claude/kg-automation/`) + a copy/symlink step to `/data/services/openclaw/felix-doc-auditor/`. Implementation phase will choose between symlink (single source of truth) or copy (per existing felix-admin-* deployment); current felix-admin-* agents appear to use copies (visible at `/data/services/openclaw/<name>/` independent of the repo).

This is similar to the recently-fixed transcribe-api deploy gap (#190), but felix-admin-* agents have a longstanding pattern of being copied to `/data/services/openclaw/` rather than referenced from the repo clone. Implementation will follow whatever the existing felix-admin-* agents do for consistency. Plan flags this as a possible follow-up: bring all felix-admin-* under the same git-pull-based deploy model used by transcribe-api after #190.

**Rationale**: Stay consistent with existing felix-admin-* deployment pattern for now. Cleanup is out of scope here but should be tracked.

**Possible follow-up**: file an infra issue to migrate all felix-admin-* agents from copied workspaces to git-pull-based references (parallel to #190 for transcribe-api).

**Source**: `docs/runbooks/openclaw-agent-setup.md`.

---

## R-012: Weekly-audit suppression bug fix (FR-008)

**Decision**: Modify `.github/workflows/doc-audit-weekly.yml` step "Check for existing weekly audit" to scope the search to the current week's title.

**Current code** (line 22-30):
```yaml
COUNT=$(gh issue list --label "P2-debt" --state open \
  --search "Weekly doc audit" --json number --jq 'length')
```

**Proposed change**:
```yaml
DATE=$(date +%Y-%m-%d)
COUNT=$(gh issue list --label "P2-debt" --state open \
  --search "Weekly doc audit — ${DATE} in:title" --json number --jq 'length')
```

The `in:title` qualifier scopes the duplicate check to issues with today's date in the title. Stale weekly issues from prior weeks no longer block creation.

**Rationale**: Minimal, targeted fix that addresses the silent suppression bug without changing the overall workflow design. Verified by the regression scenario AS-009.

**Alternatives considered**:
- Auto-close older weekly audits when creating a new one: rejected — would close legitimate work-in-progress audits; not the intended behavior.
- Change label to `weekly-audit-current` and scope by label: rejected — adds label management complexity without benefit over title-scoped check.

**Source**: `.github/workflows/doc-audit-weekly.yml` current code; spec FR-008.

---

## R-013: Doc-audit skill scope and structure

**Decision**: `scripts/openclaw/skills/doc-audit/SKILL.md` will encode (per FR-006):

| Section | Content |
|---|---|
| Front matter | `name: doc-audit`, `description: How to read and act on doc-audit and weekly-doc-audit GitHub issues`, `version: 1.0.0` |
| What this skill is | One-paragraph purpose statement |
| Inputs | (a) audit issue number, (b) `doc-domain-map.json` path |
| Workflow | Step-by-step: read issue → read domain map → for each in-scope doc, read it and compare against current system state → classify each finding (high-confidence edit / judgment / missing artifact) → propose edits via WhatsApp (Level 1) → on approval, commit + create debt issues + comment + close |
| Confidence threshold rules | Enumerated list of high-confidence edit types (frontmatter dates, version numbers, paths, dead refs, registry entries) and explicit "not high confidence" categories |
| Comparison rules | What sources of system state to consult: service-inventory.json (services), agent-registry.json (agents), doc-domain-map.json (scope), git log (recent changes) |
| Commit message format | `chore(doc-audit): <doc>: <change> (audit: <issue#>)` template |
| Error handling | What to do when a doc is missing, locked, or unreadable |

**Rationale**: Per FR-006, the skill must be self-contained. Following the `skill-author/SKILL.md` conventions ensures it conforms to project standards.

**Source**: spec FR-006; `scripts/openclaw/skills/skill-author/SKILL.md`.

---

## R-014: Manual canary procedure (planning Q2)

**Decision**: Pre-cron canary procedure:

1. Deploy all artifacts (agent workspace, skill, openclaw.json registration, GitHub label `status:in-progress`).
2. Manually invoke the agent against issue #186 (the stuck weekly audit) at Level 1: `openclaw delegate felix-doc-auditor "Process audit issue #186"`.
3. Observe full flow: WhatsApp summary received → reply with `approve` (or `reject`/`skip` depending on what the agent proposes) → agent commits / files debt issues / posts summary / closes issue.
4. Verify all artifacts: commits in `git log`, debt issues in `gh issue list`, audit issue closed, label removed.
5. If clean, enable the cron schedule (uncomment the cron line in openclaw.json + restart openclaw service).
6. Watch the next cron tick process the next-oldest audit issue. Backlog drains naturally over subsequent ticks.

**Rationale**: Per planning Q2 — minimal ceremony, real-world test, no extra `--dry-run` flag scope. Level 1 approval gate IS the safety net.

**Source**: planning Q2.

---

## Open items deferred to implementation

- **Stale-lock cleanup automation**: currently manual (R-009). Could add a separate cron tick that auto-removes `status:in-progress` labels older than 30 min — but this is a "fix later if it actually causes trouble" item, not blocking.
- **OpenClaw cron native overlap semantics**: not researched. The GitHub label is the safety net regardless.
- **Kill switch mechanism**: documented in ops runbook as "edit `openclaw.json` to disable the cron entry, or `systemctl stop openclaw-cron`" — same as existing felix-admin-* pattern.
- **AGENT-REGISTRY team designation**: TBD during implementation — likely SuperAdmin (B) but worth confirming with the existing team taxonomy.
