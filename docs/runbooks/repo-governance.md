---
title: Repository Governance
doc_type: runbook
status: approved
owners: [kent@intentional.biz]
last_validated: 2026-04-07
last_updated: '2026-04-07'
revision: v2.0
audience: agents_and_humans
---

# Repository governance

This page defines how changes land in kg-automation, how issues are
tracked, and how the repository is organized for both humans and AI
agents.

## Git workflow

- **Default branch**: `main`
- **Push model**: Push directly to `main` for routine changes. Feature
  branches are used for complex multi-step work via spec-kitty (worktrees
  and lane branches are managed automatically).
- **Conventional commits**: `feat:`, `fix:`, `docs:`, `chore:`, `ci:`,
  `refactor:`
- **CI**: Docs CI validates on every push to main (frontmatter, secrets
  scan). A pre-commit hook runs `validate_docs.py` locally before each
  commit.

## Feature development

All features are implemented through spec-kitty:

```text
specify -> plan -> tasks -> implement -> review -> merge
```

Spec-kitty manages worktrees, branches, and lane-based merges. Do not
create feature branches manually — the workflow handles this.

See `docs/func-spec/claude-pre-implementation-prompt.md` for the
standing orchestration directive.

## Issue management

Issues are tracked on GitHub using a structured label taxonomy,
milestones, and a project board.

### Label taxonomy

Issues receive exactly one P-label (priority + type) and one or more
area/ labels (domain).

**P-labels (triage gate)**

| Label | Meaning |
|-------|---------|
| P0-bug | Critical / blocking active work |
| P1-bug | Confirmed bug, fix in current cycle |
| P2-bug | Known bug, backlog |
| P0-infra | Critical infra, blocking active work |
| P1-infra | Infra work, current cycle |
| P2-infra | Infra work, backlog |
| P1-feature | Approved, next cycle |
| P2-feature | Approved, future backlog |
| P3-candidate | Proposed, not yet approved |
| P1-rfc | RFC under active review |
| P2-rfc | RFC parked for future consideration |
| P1-debt | Tech debt, current cycle |
| P2-debt | Tech debt, backlog |

**Area labels (domain)**

| Label | Scope |
|-------|-------|
| area/infrastructure | office2, Docker, Tailscale, networking, hardware, credentials, monitoring |
| area/security | Hardening, audit, access control, fail2ban, UFW |
| area/felix-core | Constitution, agent registry, operating modes, ClawHub |
| area/ea | Executive Assistant capability |
| area/task-intel | Vikunja, task enrichment, escalation engine |
| area/content | Copy, graphics, video, transcription shared services |
| area/docs | Documentation architecture, MkDocs, Obsidian sync |
| area/biz-ops | Intentional LLC, CT acquisition, metalbox |

### Milestones

Milestones represent capability clusters on the Felix roadmap:

- **Platform-Production-Ready** — office2 stable, security hardened,
  GPU inference operational
- **Felix-Intelligence-Layer** — task enrichment, escalation engine
- **EA-Calendaring** — calendar management
- **EA-Voice** — conversational voice interaction
- **EA-InboxManagement** — email triage and priority alerts
- **EA-OutcomePlanning** — weekly planning against goals
- **EA-Coaching** — behavioral intervention
- **Felix-DeepResearch** — autonomous research
- **Intentional-LLC-Operational** — client pipeline and tooling
- **Acquisition-Research-Active** — CT acquisition workflow

### Project board

The **Felix Roadmap** project
(https://github.com/users/kentonium3/projects/1) provides three views:

- **Board** — columns by Phase (matches milestones)
- **Table** — sorted by priority
- **Roadmap** — timeline by milestone

Custom fields: **Domain** (matches area/ labels), **Phase** (matches
milestones).

### Creating issues

```bash
gh issue create --repo kentonium3/kg-automation \
  --title "<Type>: <Short description>" \
  --label "<P-label>,<area-label>" \
  --milestone "<Milestone>"
```

After creation, add to the project:

```bash
GITHUB_TOKEN= gh project item-add 1 --owner kentonium3 \
  --url <issue-url>
```

Note: `GITHUB_TOKEN` env var must be unset for `gh project` commands
to use the CLI's stored auth which has the `project` scope.

## Continuous Integration

The Docs CI workflow validates on every push to main:

1. YAML frontmatter on all docs (required: `title`, `doc_type`, `status`)
2. Enum validation (`doc_type`, `status`, `level`, `audience` against
   `docs/design/standards/allowed-values.json`)
3. Secret pattern scan (AWS keys, GitHub tokens, private keys)

A pre-commit hook runs the same validation locally before each commit.

See `docs/runbooks/ci-handbook.md` for details.

## Secrets and sensitive data

- Never commit credentials. Use references or the office2 credential
  store (`/data/services/openclaw/secrets/`).
- CI runs a pattern scan; violations block the commit.
- See `docs/design/architecture/data/credential-manifest.json` for the
  full credential inventory.

## AI agent rules

- Agents push directly to `main` for routine changes (same as humans).
- Feature work uses spec-kitty workflows (worktrees, lane branches).
- Never edit `.env` files, commit secrets, force push, or `rm -rf`.
- Never modify `.github/workflows/` without explicit instruction.
- On spec-kitty workflow failure: stop and report, do not work around.

## Governance framework

Felix agents operate under a formal governance framework:

| Document | Path |
|----------|------|
| Felix Constitution | `docs/constitution/FELIX-CONSTITUTION.md` |
| Agent Registry | `docs/constitution/AGENT-REGISTRY.md` |
| Governance Runbook | `docs/runbooks/felix-governance.md` |
| Change Control | `docs/design/architecture/change-control.md` |
| Risk Register | `docs/design/risk-register.md` |

All agents start at Assisted (Level 1) and require explicit promotion.
