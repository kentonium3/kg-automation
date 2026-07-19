# Specification: OpenClaw Skills Deploy/Sync

**Mission**: openclaw-skills-sync-01KXW1DQ
**Mission type**: software-dev
**Source issue**: kentonium3/kg-automation#775
**Status**: Draft

## Overview

OpenClaw agent **skills** authored in the repository (`scripts/openclaw/skills/<skill>/SKILL.md`)
have **no deploy/sync path** to the office2 host where OpenClaw runs. The sibling mechanism
`agent-prompt-sync` (#567) syncs agent *workspace prompt* files but does **not** cover skills.
As a result, a repo edit to a `SKILL.md` never reaches the deployed skill an agent reads at
runtime, and the divergence accrues silently — the deployed `vikunja-api/SKILL.md` on office2 is
~3 months stale (dated 2026-04-10). This is the same silent-drift class (#563/#166) that motivated
building `agent-prompt-sync` + its drift check, but for the **skills** surface, currently unguarded
on both deploy and drift.

This mission builds the auto-deploy sync (Kent's decision: there was never a manual-deploy intent)
plus a drift check, mirroring the proven `agent-prompt-sync` discipline, so deployed skills stay
faithful to the repo and any divergence is surfaced rather than silently accumulated.

**Scope is the deploy/sync mechanism only.** The stale *content* of `vikunja-api/SKILL.md` (its
pre-#714-reorg project-id table) is out of scope here — that refresh belongs to the #714
Vikunja-config epic.

## Domain Language

- **Skill** — a unit of reusable agent instruction, one directory `scripts/openclaw/skills/<skill>/`
  in the repo containing a single `SKILL.md`, deployed to `/home/claude/.openclaw/skills/<skill>/SKILL.md`
  on office2 where an OpenClaw agent reads it at runtime.
- **The six skills** (current, 1:1 repo↔office2): `doc-audit`, `escalation`, `skill-author`,
  `task-intelligence`, `vikunja-api`, `whisper`.
- **Source of truth** — the committed repo `SKILL.md`. The deployed copy converges to it.
- **Drift** — any divergence between a repo `SKILL.md` and its deployed counterpart on office2.
- **agent-prompt-sync** — the reference mechanism (#567): `deploy_agent_prompts.py` + its systemd
  user timer, syncing workspace prompts with MD5-diff + atomic copy + append-only JSONL audit log +
  health-watermark/one-ntfy-per-failure-streak + `--dry-run`. This mission mirrors that discipline
  for skills.

## User Scenarios & Testing

### Scenario 1 — a repo skill edit propagates (primary happy path)
- **Given** a developer or agent edits `scripts/openclaw/skills/vikunja-api/SKILL.md` and merges to `main`,
- **When** the skills-sync mechanism next runs on office2,
- **Then** `/home/claude/.openclaw/skills/vikunja-api/SKILL.md` is updated to byte-match the repo copy,
  the change is recorded in the sync audit log, and no alert fires.

### Scenario 2 — nothing to do (idempotent no-op)
- **Given** all deployed skills already match the repo,
- **When** the sync runs,
- **Then** no file is rewritten, the run is recorded as a healthy no-op, and no alert fires.

### Scenario 3 — sync failure is surfaced, not silent
- **Given** the sync cannot complete (e.g., source missing, copy fails, host unreachable),
- **When** the failure occurs,
- **Then** exactly one ntfy alert fires per failure streak (not once per run), the health watermark
  reflects the failure, and the deployed skill is left in its prior state (no partial/corrupt write).

### Scenario 4 — drift is detected (belt-and-suspenders guard)
- **Given** a deployed `SKILL.md` diverges from the repo (e.g., the sync silently stalled, or an
  out-of-band hand-edit was made directly on office2),
- **When** the drift check runs,
- **Then** the divergence is reported/alerted with the skill name and the differing files, and
  `*.backup*` sidecar files on office2 are ignored (not reported as drift).

### Scenario 5 — dry-run preview
- **Given** an operator wants to preview what the sync would change,
- **When** they run the sync in dry-run mode,
- **Then** it prints each drifted skill (`DRIFT <skill> SKILL.md src_md5=… dst_md5=…`) and writes nothing.

## Functional Requirements

| ID | Requirement | Status |
|----|-------------|--------|
| FR-001 | The system syncs each repo skill `SKILL.md` from `scripts/openclaw/skills/<skill>/SKILL.md` to `/home/claude/.openclaw/skills/<skill>/SKILL.md` on office2 for all in-scope skills. | Proposed |
| FR-002 | Sync uses content comparison (MD5): a deployed file is rewritten only when its content differs from the repo source. Unchanged files are left untouched. | Proposed |
| FR-003 | File writes are atomic and preserve the destination file mode (no partial/corrupt deployed file on failure mid-write). | Proposed |
| FR-004 | Sync is **copy-only (no pruning)**: it copies repo→office2 and does not delete unexpected office2-side files (e.g., `SKILL.md.backup.*`). | Proposed |
| FR-005 | Every sync run appends a structured (JSONL) audit record capturing at minimum: timestamp, per-skill action (synced / unchanged / failed), and source/destination MD5s for any file acted on. | Proposed |
| FR-006 | On sync failure, the system emits exactly one ntfy alert per failure streak (deduplicated across consecutive failing runs), and updates a health watermark. On recovery, the streak resets. | Proposed |
| FR-007 | The sync supports a `--dry-run` mode that reports drift (`DRIFT <skill> SKILL.md src_md5=… dst_md5=…`) and makes no changes. | Proposed |
| FR-008 | The sync runs automatically on office2 on a recurring schedule (systemd user timer), with cadence matching `agent-prompt-sync`. | Proposed |
| FR-009 | A drift check detects any divergence between repo and deployed skills and reports/alerts it (alert-only — it does not itself remediate; the sync is the remediation path). | Proposed |
| FR-010 | The drift check ignores office2-side sidecar/backup files matching `*.backup*` (does not classify them as drift). | Proposed |
| FR-011 | The scope of skills to sync is derived from the repo's `scripts/openclaw/skills/` directory (currently 6). Adding a new repo skill dir brings it into scope without code changes to the enumerator. | Proposed |
| FR-012 | Deployment of the new mechanism to office2 flows through a `deploys/queued/<name>.yaml` manifest consumed by felix-deployer (per DIR-004), not by ad-hoc scripts. | Proposed |
| FR-013 | The mission updates the architecture documentation surfaces enumerated in "Documentation Synchronization" below (DIR-014). | Proposed |

## Non-Functional Requirements

| ID | Requirement | Threshold | Status |
|----|-------------|-----------|--------|
| NFR-001 | Propagation latency: a merged repo `SKILL.md` edit reaches office2 within one timer interval. | ≤ the `agent-prompt-sync` timer interval (match its cadence) | Proposed |
| NFR-002 | Idempotency: repeated runs with no repo change perform zero writes and zero alerts. | 0 writes, 0 alerts on unchanged state | Proposed |
| NFR-003 | Failure observability: a persistent sync failure is visible without polling. | ≥1 ntfy alert per failure streak; health watermark reflects last outcome | Proposed |
| NFR-004 | Alert noise: consecutive failures do not produce an alert per run. | Exactly 1 alert per failure streak (dedup) | Proposed |
| NFR-005 | Safety of partial failure: a failed skill does not corrupt its deployed file nor block syncing the other skills. | Failed skill retains prior content; remaining skills still processed | Proposed |
| NFR-006 | Determinism: the sync/drift logic is fully deterministic (content hashing + copy); no agent/LLM judgment in the runtime path. | 0 stochastic steps | Proposed |

## Constraints

| ID | Constraint | Status |
|----|------------|--------|
| C-001 | Risk tier 3 (Standard) — Python + systemd user units + deploy logic. No Tier-0 host surfaces (UFW/iptables/sshd/sudoers). | Active |
| C-002 | The new systemd user unit(s) + deploy script are an **audited surface** (#557) → the mission's merge records a rebaseline outcome (`Rebaseline: completed at <ts>` or `not required — <reason>`) per `docs/runbooks/security-baseline-ops.md`. | Active |
| C-003 | Deployed target path must be read/confirmed from the real office2 layout (DIR-008), not inferred: verified `/home/claude/.openclaw/skills/<skill>/SKILL.md` (post-#653 relocation into claude-user space). | Active |
| C-004 | Skill **content** is out of scope; only the deploy/sync mechanism is built here. `vikunja-api/SKILL.md` content refresh stays in #714. | Active |
| C-005 | Reuse the shared `agent-prompt-sync` primitives/discipline rather than inventing a divergent mechanism (locality / consistency; DIRECTIVE_024). Extend-vs-parallel-module is a plan-phase decision. | Active |
| C-006 | No new package source is introduced (no brew tap / pip index / npm registry / MCP plugin); reuses existing repo Python + systemd. | Active |
| C-007 | Tailscale-only / office2-internal; no new public exposure (DIR-003). | Active |

## Key Entities

- **Skill sync unit of work** — one `(skill_name, repo_path, deployed_path)` triple; the enumerator
  produces one per repo skill dir.
- **Sync audit record** — one JSONL line per run (or per skill action): timestamp, skill, action,
  src_md5, dst_md5, outcome.
- **Health watermark** — persisted last-outcome state driving one-alert-per-failure-streak dedup.
- **Drift-check config** — the skills coverage added to/mirroring the enforcement drift-check config.
- **Deploy manifest** — `deploys/queued/<name>.yaml` describing the systemd unit + deploy-script install.

## Success Criteria

- **SC-001** — A repo `SKILL.md` edit reliably appears at `/home/claude/.openclaw/skills/<skill>/SKILL.md`
  on office2 within one timer interval, byte-for-byte, with an audit record and no alert. *(Measurable:
  edit → wait one interval → deployed MD5 == repo MD5.)*
- **SC-002** — With deployed skills already matching the repo, a sync run makes zero changes and zero
  alerts. *(Measurable: 0 writes, 0 alerts.)*
- **SC-003** — An induced sync failure produces exactly one ntfy alert per failure streak and a health
  watermark reflecting it; recovery resets the streak. *(Measurable: 1 alert / streak.)*
- **SC-004** — An intentionally-diverged deployed skill is flagged by the drift check; a `*.backup*`
  sidecar is not. *(Measurable: diverged skill reported, backup ignored.)*
- **SC-005** — `--dry-run` reports current drift and writes nothing. *(Measurable: 0 writes; drift lines printed.)*
- **SC-006** — The mechanism is deployed via a `deploys/queued/` manifest and the merge records a
  rebaseline outcome for the audited surface.
- **SC-007** — Architecture docs/data updated per the Documentation Synchronization list.

## Assumptions

- **A1** — Drift check is **alert-only** (mirrors the workspace guard); the sync is the remediation path. *(Confirmed with Kent.)*
- **A2** — Sync is **copy-only, no pruning**; unexpected office2-side files (e.g. `*.backup*`) are left in place and the drift check ignores `*.backup*`. *(Confirmed with Kent.)*
- **A3** — Timer **cadence matches `agent-prompt-sync`**. *(Confirmed with Kent.)*
- **A4** — Sync surface per skill is a single `SKILL.md` (verified: every skill dir contains exactly one file, both repo and office2). If a future skill dir gains supporting files, the enumerator should sync the whole dir; captured as a plan consideration, not required for the current 6.
- **A5** — office2 access for the deploy is the existing `claude`-user path; no new credential is introduced.

## Out of Scope

- Refreshing the **content** of any `SKILL.md` (esp. `vikunja-api` stale project table) — that is #714.
- Any change to the `agent-prompt-sync` path for workspace prompts.
- Two-way sync or editing skills on office2 as a source of truth (repo remains the sole source of truth).

## Documentation Synchronization (DIR-014)

Per the signal-to-doc-map for this mission's change classes (`service-added-or-modified`,
`systemd-unit-added-or-modified`, `data-flow-added-or-modified`, `runbook-modified`):

| Doc surface | Why |
|-------------|-----|
| `docs/design/architecture/data/service-inventory.json` + `service-inventory.md` | new skills-sync service + systemd unit registered |
| `docs/design/architecture/service-dependencies.view.md` | new sync service relationship |
| `docs/design/architecture/data/audited-surfaces.json` | confirm new systemd unit + deploy script are covered by existing globs (or extend) |
| `docs/design/architecture/data/data-flows.json` + `data-flows.md` + `data-flows.view.md` | new repo→office2 skill-sync data flow |
| `docs/runbooks/deployment.md` | document the skills-sync alongside agent-prompt-sync |
| `docs/INDEX.md` (+ `DEVELOPER_PORTAL.md` if a new runbook is added) | navigation for any added/modified runbook |
| `docs/design/felix-capability-roadmap.md` | capability/status note if applicable |

All JSON edits set `updated_by` to `775`; markdown views must match their JSON sources.
