# Doc Audit Infrastructure

**Feature**: 020-doc-audit-infrastructure
**Mission**: software-dev
**Status**: draft
**Priority**: P1
**GitHub Issue**: #104
**Milestone**: Platform-Production-Ready

---

## Summary

Felix has a standing directive to keep documentation current, but no
machine-readable scope contract, no structured way to flag documentation
gaps, and no automated post-merge audit trigger. Documentation
maintenance is ad-hoc and easily skipped in long sessions.

This feature delivers the infrastructure that makes documentation
maintenance systematic, scoped, and automatable: a domain-to-docs
mapping, a docs-debt issue template, a commit tag convention, a
post-merge audit trigger GitHub Action, and a weekly safety-net audit
cron stub. This is the foundation the future `felix-doc-auditor` agent
(#105) will build on.

---

## Actors

- **Claude Code**: Creates and maintains the domain map, uses the commit
  tag convention, responds to audit issues
- **GitHub Actions**: Runs the post-merge and weekly audit triggers
- **Kent (system owner)**: Triages audit issues, reviews domain map scope
- **felix-doc-auditor (future)**: Will consume the domain map and audit
  issues — not an actor in this feature but the design must serve it

---

## User Scenarios and Testing

### Scenario 1: Post-merge audit issue created

**Precondition**: A PR with `area/task-intel` label is merged to main
**Flow**:
1. GitHub Action triggers on merge
2. Action reads the PR's area labels
3. Action looks up `area/task-intel` in doc-domain-map.json
4. Action creates a GitHub issue with a checklist of affected docs
5. Issue is labeled and visible in the queue

**Acceptance**: Audit issue created with correct scope, correct labels,
and a checklist matching the domain map entries for `area/task-intel`.

### Scenario 2: PR with no area labels merged

**Precondition**: A PR with only `P1-infra` label (no area label) is merged
**Flow**:
1. GitHub Action triggers on merge
2. Action finds no area labels on the PR
3. Action exits silently — no audit issue created

**Acceptance**: No issue created. Action succeeds without error.

### Scenario 3: Weekly audit stub fires

**Precondition**: Sunday midnight ET
**Flow**:
1. Scheduled workflow triggers
2. Checks for existing open weekly audit issue
3. If none exists, creates a new one with full-scope checklist
4. If one already exists, skips creation

**Acceptance**: One weekly audit issue exists (not duplicated).

### Scenario 4: Commit with [doc-audit] tag

**Precondition**: Developer commits a fix with `[doc-audit]` tag
**Flow**:
1. Commit lands on main: `fix: repair vikunja filter logic [doc-audit]`
2. The tag is visible in git log
3. Future felix-doc-auditor will scan for this tag

**Acceptance**: Tag convention documented in CLAUDE.md. No CI enforcement
(advisory only).

### Scenario 5: docs-debt issue created from template

**Precondition**: An audit identifies a missing runbook
**Flow**:
1. User creates issue via GitHub UI, selects docs-debt template
2. Template pre-fills structure: artifact name, gap description,
   cross-references, area label, draft outline
3. Issue is created with correct structure for Claude Code to act on

**Acceptance**: Template exists and produces well-structured issues.

---

## Requirements

### Functional Requirements

| ID | Requirement | Status |
|----|-------------|--------|
| FR-001 | Create `doc-domain-map.json` at `docs/design/architecture/data/` mapping each of the 8 area labels to the list of documents that must be verified when that domain changes | draft |
| FR-002 | Create `.github/ISSUE_TEMPLATE/docs-debt.md` as an issue template for documentation gaps, capturing: missing artifact name/path, gap description, cross-references, area label, and draft outline | draft |
| FR-003 | Add a `[doc-audit]` commit tag convention to CLAUDE.md's Git Workflow section, documenting its purpose (signals untracked maintenance changes for future audit scope) | draft |
| FR-004 | Create `.github/workflows/doc-audit-trigger.yml` that triggers on PR merge to main when the PR has area labels, reads the domain map, and creates a scoped audit issue with a checklist of affected docs | draft |
| FR-005 | Create `.github/workflows/doc-audit-weekly.yml` that triggers weekly (Sunday midnight ET) and creates a full-scope audit issue if no open weekly audit issue already exists | draft |
| FR-006 | Update `docs/INDEX.md` to reference the domain map; update `docs/design/architecture/README.md` to list the domain map in the Data Files table; set `updated_by` on doc-domain-map.json to this issue number | draft |

### Non-Functional Requirements

| ID | Requirement | Threshold | Status |
|----|-------------|-----------|--------|
| NFR-001 | The post-merge GitHub Action must not block PR merges — it runs as a non-required status check | Zero merge-blocking failures | draft |
| NFR-002 | The domain map must be editable by hand in under 30 seconds for a single new document entry | <= 30s for one-line edit | draft |
| NFR-003 | The post-merge action must not create duplicate audit issues for the same PR | Zero duplicates | draft |

### Constraints

| ID | Constraint | Status |
|----|------------|--------|
| C-001 | The domain map is the scope contract for the future felix-doc-auditor — changing its schema requires updating this spec | active |
| C-002 | The GitHub Actions use only `GITHUB_TOKEN` — no additional secrets required | active |
| C-003 | The `[doc-audit]` tag is advisory only — no CI enforcement | active |
| C-004 | The weekly stub creates a human-actionable issue, not an automated agent run — agent integration is #105's scope | active |
| C-005 | A document can appear under multiple domains in the map | active |

---

## Scope

### In scope

- doc-domain-map.json covering all 8 area labels and all active docs
- docs-debt issue template
- `[doc-audit]` commit tag convention in CLAUDE.md
- Post-merge audit trigger GitHub Action
- Weekly audit cron stub GitHub Action
- Architecture doc updates (INDEX.md, architecture README)

### Out of scope

- felix-doc-auditor agent (#105)
- Automated document editing
- CI enforcement of `[doc-audit]` tag
- Full system state auditor (#106)
- Auditing the second-brain vault or .kittify/ internal files

---

## Success Criteria

### Domain map
- doc-domain-map.json exists with entries for all 8 area labels
- All currently active runbooks and architecture docs are represented
- A new document can be added with a single-line JSON edit

### Issue template
- docs-debt template exists at `.github/ISSUE_TEMPLATE/docs-debt.md`
- Template includes all required fields (artifact, gap, cross-refs, area, outline)
- Template appears in the GitHub issue creation UI

### Commit convention
- CLAUDE.md documents the `[doc-audit]` tag with usage and purpose

### Post-merge action
- Workflow triggers on PR merge with area labels
- Creates audit issue with correct labels and domain-scoped checklist
- Does not create issues for PRs without area labels
- Does not create duplicates for the same PR
- Fails gracefully if domain map is missing

### Weekly stub
- Workflow triggers weekly on schedule
- Creates a full-scope audit issue if none exists
- Deduplication prevents stacking open weekly issues

### Architecture updates
- INDEX.md references the domain map and docs-debt template
- Architecture README lists domain map in Data Files table

---

## Key Entities

| Entity | Role | Changes |
|--------|------|---------|
| doc-domain-map.json | Machine-readable domain→docs scope contract | Created |
| docs-debt.md template | Structured issue template for documentation gaps | Created |
| doc-audit-trigger.yml | Post-merge audit issue creation workflow | Created |
| doc-audit-weekly.yml | Weekly safety-net audit issue workflow | Created |
| CLAUDE.md | Session initialization and conventions | `[doc-audit]` tag added |
| docs/INDEX.md | Documentation index | Domain map reference added |

---

## Assumptions

- The 8 area labels (infrastructure, security, felix-core, ea, task-intel,
  content, docs, biz-ops) are stable — the domain map schema supports
  adding new domains but the initial map covers only these 8
- GitHub Actions `issues: write` and `contents: read` permissions are
  sufficient for the workflows
- The `GITHUB_TOKEN` available in Actions context has the necessary
  scopes for issue creation
- PRs are the merge mechanism for features (spec-kitty merges create
  merge commits, not PRs — the post-merge action may need to trigger
  on push to main with area-label detection from commit messages or
  a different mechanism)

---

## Dependencies

- **Issue templates** (`.github/ISSUE_TEMPLATE/`): 4 templates already exist
- **Label taxonomy**: All 8 area labels already exist
- **Architecture data directory**: `docs/design/architecture/data/` already exists
- **GitHub Actions**: `.github/workflows/` directory already exists with Docs CI

---

**END OF SPECIFICATION**
