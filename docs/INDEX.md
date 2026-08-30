---
title: kg-automation Documentation Index
doc_type: reference
status: approved
owners: [kgale]
version: "2.0"
last_validated: 2026-05-26
tags: [152, 126, 119, 103, 114, 115, 116, 490, 518/, 507, 572]
---

# kg-automation Documentation Index

Master map for all active documentation under `docs/`. Referenced from
`CLAUDE.md` as the starting point for agents discovering documentation.

**Scope**: `docs/**` excluding `docs/archive/`
(both exempt from restructuring).

---

## Onboarding & Navigation

- [Developer Portal](<./DEVELOPER_PORTAL.md>) — guided onboarding sitemap (start here for new agents and contributors)
- [Doc Maintenance](<./runbooks/doc-maintenance.md>) — link conventions, runbook frontmatter, portal filter, and validator behavior

---

## Constitution & Governance

### docs/constitution/ — Governance authority

- [Felix Constitution](<./constitution/FELIX-CONSTITUTION.md>) — top-level governance, autonomy levels, principles
- [Agent Registry (narrative)](<./constitution/AGENT-REGISTRY.md>) — current agent state, deployment status, autonomy transitions
- [Agent Registry (JSON)](<./constitution/agent-registry.json>) — machine-readable authoritative registry

### docs/runbooks/governance/ — Change control governance

- [Pre-Flight Change Checklist](<./runbooks/governance/pre-flight-checklist.md>) — mandatory assessment for Tier 0/1/2 changes
- [Post-Change Verification Protocol](<./runbooks/governance/post-change-verification.md>) — health-check verification after changes
- [Incident Postmortem Template](<./runbooks/governance/incident-postmortem-template.md>) — reusable template for incident analysis

---

## System Architecture

### docs/design/architecture/ — Current-state system reference

- [README](<./design/architecture/README.md>) — architecture suite index
- [Service Inventory](<./design/architecture/service-inventory.md>) — running services, ports, systemd units
- [Data Flows](<./design/architecture/data-flows.md>) + [Mermaid view](<./design/architecture/data-flows.view.md>)
- [Observability & Alerting — the Deterministic-Scanner Pattern](<./design/architecture/observability-and-alerting.md>) — *Explanation* — the reusable pattern for self-observing scanners (inventory-declared health check → deterministic systemd-timer scanner → #701 alert bus → durable ledger); the shape a new alert producer follows. Exemplars: `felix-canary` (#327) + `felix-trust-scan` (#683).
- [Physical Topology](<./design/architecture/physical-topology.md>) + [Mermaid view](<./design/architecture/physical-topology.view.md>)
- [Credentials & Secrets](<./design/architecture/credentials-and-secrets.md>)
- [Identity Model](<./design/architecture/identity-model.md>)
- [Security Posture](<./design/architecture/security-posture.md>)
- [Backup & Recovery](<./design/architecture/backup-and-recovery.md>)
- [Change Control Protocol](<./design/architecture/change-control.md>)
- [Service Dependencies Diagram](<./design/architecture/service-dependencies.view.md>)
- [Glossary](<./design/architecture/glossary.md>)
- [LLM Spend Baseline](<./design/architecture/llm-spend-baseline.md>) — monthly cost snapshot per service, trend commentary (narrative companion to `data/llm-spend-baseline.json`) *(pre-2026-05-26 doc-audit suspension; expect substantial June 2026 drop)*
- [LLM Cost Source Ledger](<./design/architecture/llm-cost.md>) — Kent's raw invoice/dashboard sweep (Anthropic, Gemini, etc.); source data feeding the spend baseline

### docs/design/architecture/adr/ — Architecture Decision Records

Immutable, dated records of *why* particular options were chosen over alternatives. See the README for when to write one.

- [ADR Index](<./design/architecture/adr/README.md>)
- [ADR-0001 — Google Workspace integration via `gog`](<./design/architecture/adr/0001-google-workspace-via-gog.md>) (approved 2026-05-13)
- [ADR-0002 — Felix ↔ Vikunja task model](<./design/architecture/adr/0002-felix-vikunja-task-model.md>) (approved 2026-05-17; Q6 superseded by ADR-0007)
- [ADR-0003 — Felix ↔ Vikunja sync architecture](<./design/architecture/adr/0003-felix-vikunja-sync-architecture.md>) (approved 2026-06-09)
- [ADR-0004 — Enable Tailscale SSH on office2 with `accept` ACL](<./design/architecture/adr/0004-tailscale-ssh-with-accept-acl.md>) (approved 2026-06-09)
- [ADR-0005 — Vikunja client standardization (base URL, token, timeout, error policy)](<./design/architecture/adr/0005-vikunja-client-standards.md>) (approved 2026-06-10)
- [ADR-0006 — Felix component lifecycle status contract (declared status vs observed health)](<./design/architecture/adr/0006-felix-component-lifecycle-status-contract.md>) (approved 2026-07-11)
- [ADR-0007 — Retire Vikunja felix-bot; single kent-token runtime identity](<./design/architecture/adr/0007-retire-vikunja-felix-bot.md>) (approved 2026-07-23)
- [ADR-0008 — Three-machine model; office2 managed, MacBook Pro and office4 unmanaged peers](<./design/architecture/adr/0008-three-machine-model.md>) (approved 2026-08-29)

### docs/design/architecture/data/ — Machine-readable state (JSON)

Authoritative operational state. **Exempt from moves (F015 constraint C-001)**.

- [Agent State Log Schema](<./design/architecture/data/agent-state-log-schema.md>) (reference) — canonical JSONL schema for the shared agent state log
- [Service Inventory](<./design/architecture/data/service-inventory.json>)
- [Hardware Inventory](<./design/architecture/data/hardware-inventory.json>)
- [Network Topology](<./design/architecture/data/network-topology.json>)
- [Credential Manifest](<./design/architecture/data/credential-manifest.json>)
- [Data Flows](<./design/architecture/data/data-flows.json>)
- [Capabilities Schema](<./design/architecture/data/capabilities-schema.json>)
- [Catalog Schema](<./design/architecture/data/catalog-schema.json>)
- [Mutation Surfaces](<./design/architecture/data/mutation-surfaces.json>) — Layer 1.5 governance: enumeration of all mutation surfaces (file edits, GitHub API, git push, shell exec, etc.) available to Felix agents, with per-surface risk tier and approval requirements
- [Change Risk Taxonomy](<./design/architecture/data/change-risk-taxonomy.json>)
- [Doc Domain Map](<./design/architecture/data/doc-domain-map.json>)
- [LLM Spend Baseline](<./design/architecture/data/llm-spend-baseline.json>) — monthly LLM cost across all services (authoritative; see narrative companion in parent dir)
- [Audited Surfaces](<./design/architecture/data/audited-surfaces.json>) — repo paths whose changes affect office2 security-monitor baselines; consumed by `.github/workflows/audited-surface-reminder.yml` and the spec-kitty charter rebaseline obligation (#557)

### docs/design/architecture/baselines/ — Pre/post-change measurement baselines

Numerators/denominators captured before and after material architectural changes; referenced by spec-level NFR acceptance gates.

- [Baselines Index & Methodology](<./design/architecture/baselines/README.md>) — how baselines are captured, retained, and compared (includes the felix-doc-auditor pre-rework snapshot)

---

## Operational Runbooks (docs/runbooks/)

### Configuration Integrity Sweeps (topical view)

Three periodic sweeps verify that office2's configuration and Felix's own
reported behavior are in the state we expect; together they cover
system-level drift, credential-level drift, and unrequested-infrastructure /
ungrounded-completion drift, and any new sweep should be added to this group.
All three runbooks are also listed under *Agent-executable* below.

- [Crontab Recovery](<./runbooks/crontab-recovery.md>) — restore the `claude` crontab after it is lost, using `crontab_capture.py --emit-body` (which strips the provenance header with the same parser that wrote it). ⚠️ Do **not** use the hand-written `grep -v "^# captured-…"` form from the #895 quickstart — it predates the sentinel-delimited header, reports a false verification failure, and installs a crontab that grows stray lines on every recovery cycle (#906). Scope is the `claude` crontab only; `kgale` and `root` are unreadable unprivileged.
- [Security Baseline Operations](<./runbooks/security-baseline-ops.md>) — daily 3 AM audit comparing the live system (pip / brew packages, Docker images, listening ports, systemd units, SSH keys, crontabs, OpenClaw cron + config) against `/data/services/security-monitor/baselines/`. Drift fires the alert log + `drift-events.jsonl`. Audited surface list at [`audited-surfaces.json`](<./design/architecture/data/audited-surfaces.json>) drives the rebaseline obligation (#557).
- [Credential Liveness Probe Operations](<./runbooks/credential-liveness-probe-ops.md>) — 6-hourly OAuth liveness probe (00, 06, 12, 18 UTC). Live API call per credential, classified as `dead` (invalid/revoked token — investigate before re-authing) or `probe-error`. Auto-files a GitHub issue with the recovery command in the body (#572, #731).
- [Trust Reporting Detector Operations](<./runbooks/trust-reporting-detector.md>) — 15-min `felix-trust-scan` timer: cron-drift detection (live OpenClaw crons vs the approved-cron baseline — the load-bearing, agent-independent guard) + completion-assertion verification (asserted artifacts checked against their owning system). Alerts via the `#701` felix-alert bus. Detection half of the Felix Truthful Reporting Guardrails (#683).

### Agent-executable runbooks

- [Doc Auditor Driver Operations](<./runbooks/doc-auditor-driver-ops.md>) — felix-doc-auditor **scripts-first driver** operations (post-#343): hourly systemd tick, `last-tick.json` health signal, prompt artifacts, backlog/lock recovery, pending-approval workflow, troubleshooting, baselines *(⏸ currently suspended; see runbook banner)*
- [Signal-Driven Monitoring Operations](<./runbooks/signal-driven-monitoring-ops.md>) — `felix-core-digest` signal extraction + `felix-heartbeat-gate` (Haiku-tier routing) operations: pre-cutover checklist (Restic Tier 2 precondition + identity/credential checks), 12-step cutover procedure, post-cutover verification, troubleshooting, rollback, post-rollout tuning. Mission #490.
- [Felix-Vikunja Sync Driver Operations](<./runbooks/sync-driver-ops.md>) — install, bootstrap, observe, and recover the Felix-Vikunja reconciliation driver per ADR-0003: 5-min systemd timer, 7-phase full-poll pipeline, project-layer audit (`layer_summary`), deletion cleanup (Phase 5b), URL config prerequisite (`vikunja-base-url.txt`), `conflict-events.jsonl` audit trail, three delivery guards (G-1/G-2/G-3), known soft edge for Vikunja server-side auto-advance, full SC-001..SC-009 verification commands. Missions #518/#519/#520 (Epic #507 complete).
- [Doc Auditor Operations (pre-#343 — historical)](<./runbooks/doc-auditor-ops.md>) — original openclaw-agent runbook; retained for reference until the pre-#343 implementation is fully retired
- [Security Baseline Operations](<./runbooks/security-baseline-ops.md>) — canonical baseline-reset procedure for the daily 3 AM audit; linked from service runbooks for the "how". ⚠️ The reset deletes every baseline, and some are the only surviving copy of the host state they fingerprint — archive before resetting (#895)
- [Credential Liveness Probe Operations](<./runbooks/credential-liveness-probe-ops.md>) — 6-hourly OAuth liveness probe (sister sweep to the daily security audit); cadence, classification logic, manifest config, operator response when an issue is filed (#572, #616)
- [Trust Reporting Detector Operations](<./runbooks/trust-reporting-detector.md>) — 15-min `felix-trust-scan` timer (third sweep in the configuration-integrity cluster); how to read alerts, baseline maintenance + ordering rule, run modes + exit-code discipline, disable/rollback, fail-safe guarantee, SC-001..005 regression checklist (#683)
- [Canary Registry Operations](<./runbooks/canary-registry-ops.md>) *(runbook / how-to)* — 15-min `felix-canary` timer: deterministic component-health watcher that reads each service's declared `health_check` from `service-inventory.json`, computes health per ADR-0006, and alerts stale/failed/coverage-gap/persistent-unknown via the `#701` felix-alert bus. State + per-component ledger under `/data/services/felix-canary/`; silence a component by suspending it (not a code change); crash covered via `OnFailure`, dead-timer deferred to #269. Sibling scanner to `felix-trust-scan` (#327).
- [Vikunja Operations](<./runbooks/vikunja-ops.md>)
- [OpenClaw Operations](<./runbooks/openclaw-ops.md>)
- [OpenClaw Ecosystem Upgrade](<./runbooks/openclaw-ecosystem-upgrade.md>) *(runbook / how-to)* — weekly `felix-openclaw-updates` timer detects available OpenClaw **core + channel-plugin** updates (`npm outdated` + `~/.openclaw/npm/projects/` vs registry), silent unless found, WARN digest via the `#701` bus. Plus the **operator-attended lockstep upgrade procedure** (core + all plugins together, gateway restart, mandatory DM-reply smoke) that prevents the #588/#617 silent WhatsApp break. Detection-only automation; apply is manual (#628).
- [office2 OS Maintenance](<./runbooks/office2-os-maintenance.md>) *(runbook / how-to)* — Ubuntu 24.04 host patching: unprivileged `apt list --upgradable` detection (agent-safe) driven by a monthly Vikunja reminder; **apply is a Tier-0 change Kent runs via `ssh office2-kgale`** (agent never runs `sudo apt upgrade`). Blast-radius awareness for containerd/docker/kernel/sshd; reboot + stack-health verification (#628).
- [office4 Work-Hat Environment](<./runbooks/office4-work-hat-environment.md>) *(runbook / how-to)* — environment handoff for a **work-account** (`kent@spec-kitty.ai`) agent starting on office4: direnv `CLAUDE_CONFIG_DIR`/`CODEX_HOME` hat routing (and why user memory still resolves to `~/.claude/CLAUDE.md` regardless), the Tailscale-SSH `accept` termination semantics that make `authorized_keys` inert on the tailnet path, per-repo venv build recipes (incl. `spec-kitty-qa`'s non-uv PEP 735 path and its refusal of narrowed pytest runs), and what is still unconfigured (MCP servers, `core.hooksPath`, no vault, no work-hat memory tree).
- [Obsidian Sync Operations](<./runbooks/obsidian-sync-ops.md>)
- [Transcribe Operations](<./runbooks/transcribe-ops.md>)
- [Ollama Operations](<./runbooks/ollama-ops.md>) — local LLM inference runtime (GPU-accelerated)
- [Inbox Processing](<./runbooks/inbox-ops.md>)
- [Task-Intake Validation Loop Operations](<./runbooks/intake-ops.md>) — the Tier-1 task-intake loop that rides each inbox tick (#749): `scan_inbox.py` flags Inbox tasks missing a working project / `f:` / `q:`, sends one batched WhatsApp digest, and `apply_reply.py` applies Kent's compact-shorthand reply through the **kent** Vikunja token (closes #750). State-dir layout, shorthand grammar, per-line statuses, 30-second health check.
- [Goals Operations](<./runbooks/goals-ops.md>)
- [Habits Operations](<./runbooks/habits-ops.md>)
- [Task Intelligence Operations](<./runbooks/task-intelligence-ops.md>)
- [Escalation Engine Operations](<./runbooks/escalation-ops.md>)
- [OpenClaw Agent Setup](<./runbooks/openclaw-agent-setup.md>) — agent deployment + verification; now includes DM-reply lifecycle troubleshooting (#588)
- [Google Workspace Operations](<./runbooks/google-workspace-ops.md>) — `gog` CLI setup, OAuth flow, pitfalls, common commands, second-account expansion, credential liveness probe auto-detection (#100, ADR-0001, #572). *(Calendar surface migrated off gog to the Felix calendar helper by #699 — see below.)*
- [Calendar Helper Operations](<./runbooks/calendar-helper-ops.md>) — Felix-owned Google Calendar helper (RFC #681 calendar phase, #699): how to invoke (`python -m scripts.google.calendar_helper`), per-account OAuth creds at `~/.config/felix/google/<account>/`, `--self-check`, re-mint on scope/auth failure, dedicated venv location, exit-code (0/1/2/3) troubleshooting. Replaces `gog calendar create`; closes #679.
- [Phone Termius Setup & Recovery](<./runbooks/phone-termius-setup.md>) — iPhone Termius SSH setup (kgale + claude hosts), new-phone enrollment, post-key-rotation recovery, Tailscale SSH ACL gotchas (#575, ADR-0004)
- [Local Test Gate (pre-push hook)](<./runbooks/local-test-gate.md>) — `.githooks/pre-push` runs `make test` before `git push`; one-time `git config core.hooksPath .githooks` setup; bypass policy (#571)
- [Smoke checklist — felix-admin-calendar extraction (#579)](<./runbooks/felix-calendar-subagent-extraction-01KTTA33-smoke.md>) — operator-driven post-deploy verification for the felix-calendar-subagent-extraction mission: DM round-trips per subagent, doc-auditor `last-tick.json` freshness, 24h observation window for scheduled outbound flows, decision criteria

### Human and mixed-audience runbooks

- [Agent Workspace Reconciliation](<./runbooks/agent-workspace-reconciliation.md>) — drift enforcement, factory-default lifecycle, last-author-wins strategy
- [office2 Deploy Paths — Surface Partition](<./runbooks/deploy/office2-deploy-paths.md>) — *Reference* — which of office2's deploy mechanisms delivers which change: the felix-deployer manifest pipeline (crons/units/config/lib), agent-prompt-sync + agent-skill-sync (prompt/skill content), and self-pull (helper scripts). Surface-partition table, slug→deploy-dir map, the drift-check-is-not-a-deploy-path clarification (#766), and the open audit-parity recommendation. Reconciles the two paths (#636)
- [Deploy Discipline (canonical)](<./runbooks/deploy/discipline.md>) — manifest-driven deploys to office2 via the felix-deployer applier; entrypoint shape, tier policy, verification commands, failure handling, rebaseline obligation
- [Deployment Runbook](<./runbooks/deployment.md>) — historical stub; redirects to the discipline runbook above. Preserved as a stable URL for older docs / ADRs / issues that link here
- [Agent Skill Sync Operations](<./runbooks/agent-skill-sync-ops.md>) — the `agent-skill-sync` pull-based OpenClaw `SKILL.md` deploy pipeline (#775, sibling to agent-prompt-sync #567): systemd units, manifest-pipeline deploy + hard verify-before-enable gate, manual enable/validation, the independent drift check (canary-probed), audit log + freshness pointer + health watermarks, and rollback. Closes the SKILL.md silent-drift gap (#563 class)
- [Felix Governance](<./runbooks/felix-governance.md>) — agent registration, promotion, demotion, violation handling
- [felix-bot Vikunja Provisioning](<./runbooks/felix-bot-vikunja-provisioning.md>) — operator runbook for provisioning, rotating, and revoking the kg-felix-bot Vikunja API credential
- [Credential Rotation Operations](<./runbooks/credential-rotation-ops.md>) — operator runbook for manually rotating each credential in the manifest with a manual rotation path (8 procedures + pre-flight + manifest-update obligations)
- [Vault Path Registry Migration](<./runbooks/vault-path-registry-migration.md>) — reusable playbook for migrating vault folder names through the registry (how-to guide; first executed by mission 026 / #152)
- [Repository Governance](<./runbooks/repo-governance.md>) — git workflow, labels, milestones, issue management
- [GitHub Issues Workflow](<./runbooks/github-issues-workflow.md>) — issue lifecycle, templates, triage, project board
- [Observation Intelligence Ops](<./runbooks/observation-ops.md>)
- [Obsidian Setup Guide](<./runbooks/obsidian-setup.md>)
- [Obsidian Vault](<./runbooks/obsidian.md>)
- [WhatsApp Channel Operations](<./runbooks/whatsapp-ops.md>)

### Deprecated runbooks (retained in place)

- [Spec-Kitty Mission Review Cycle](<./runbooks/spec-kitty-review-cycle.md>) — full mission arc with the two mandatory independent Codex review checkpoints (post-plan + post-merge); how they complement `analyze` and `mission-review`
- [Spec-Kitty Bug Reporting](<./runbooks/spec-kitty-bug-reporting.md>) — dual-track workflow for filing tooling bugs: internal kg-automation issue tracks status, slim external paste doc goes upstream
- [Spec-Kitty Install Guide](<./runbooks/spec-kitty-init-in-existing-repo.md>) — historical, setup already complete

### Non-runbook content in runbooks/

- [Templater Commands (Canon v2)](<./runbooks/templater-commands.md>) — command reference

---

## Design & Standards

### docs/design/ — Vision and rationale

- [Felix System Overview](<./design/README.md>) — **start here for new contributors.** Day-1 orientation: what Felix is, what it does for Kent, how he interacts with it, key flows, components, and architectural principles. 5 high-level mermaid diagrams.
- [Felix Capability Roadmap](<./design/felix-capability-roadmap.md>) — living capability status, feature sequence, and design principles
- [Executive Assistant Architecture — Design Brief](<./design/executive-assistant-architecture.md>) — the CEO-EA organizing frame; intake→router→executor layering; the keystone reconciliation that the world-model **is** the #692 graph layer; settled decisions (write-back, federated, coaching deferred); the router as the net-new forward design *(draft)*
- [OpenClaw Workspace Authoring Standard](<./design/openclaw-workspace-authoring-standard.md>) — file-ownership contract (SOUL/USER/TOOLS/IDENTITY/AGENTS) + shared-invariant rules every agent workspace is authored against; validated by `scripts/openclaw/agents/validate_workspace.py` (#587)
- [Vision & Architecture](<./archive/vision-framework.md>) *(archived — superseded by capability roadmap)*
- [Personal AI System Spec v1.0](<./archive/personal-ai-system-spec-v1.0.md>) *(archived — design intent consolidated into roadmap; work items in GitHub issues)*
- [Strategic Acceleration Charter](<./archive/strategic-acceleration-charter.md>) *(archived — pre-Felix era, superseded by capability roadmap)*
- [Adversarial Analysis](<./archive/adversarial-analysis.md>) *(archived — items extracted to #126, #119)*
- [office2 Backup & Security](<./design/office2-backup-and-security.md>)
- [Vikunja Integration Notes](<./archive/Vikunja.md>) *(archived — items covered by #103)*
- [Risk Register](<./archive/risk-register.md>) *(archived — items transcribed to GitHub issues #114, #115, #116)*
- [Decision Log](<./archive/decision-log.md>) *(archived — decisions tracked as GitHub issues with RFC labels)*

### docs/design/process-flows/ — Current-state process flows

- [Process-Flow Docs — Convention & Index](<./design/process-flows/README.md>) — *Explanation* — the discoverable home and shape for user process-flow docs: the canonical section order, the frontmatter convention, the ID-citation discipline, how flows are wired into machine discovery (`signal-to-doc-map.json` change classes + INDEX + portal), and a checklist for adding a new flow. Start here (#794).
- [Inbox Routing Process Flow](<./design/process-flows/inbox-routing.md>) — *Explanation/Reference* — the umbrella capture lifecycle: tick → prescan → classify → route → atomic `route_and_finalize` → mark processed, and the note states around it (unprocessed / withheld / processed / needs-review / errored / archived). Consolidates #185 + #746 + #740 + #683 and flags the superseded founding requirements. Parent of the calendar/someday/journal routes.
- [Calendar Clarification Process Flow](<./design/process-flows/calendar-clarification.md>) — *Explanation/Reference* — current-state behavior when a captured note resolves to an appointment with a date but no time: actors + trigger, the full flow & states (ask-first → 8h window → answered-timed / eligible→all-day fallback / ineligible→delete-and-release), the operating rules & invariants (with FR/INV IDs), the implementing seams, and a Mermaid state diagram. Consolidates #739 + FR-007 (routing mission) + #746 + #786 + #780. The exemplar shape #794 generalized to the sibling flows.
- [Someday Routing Process Flow](<./design/process-flows/someday.md>) — *Explanation/Reference* — captures classified "someday" → a `q:schedule` + no-due-date Vikunja task landed in Inbox, with fail-soft label attach (felix-bot #715 403 boundary) and the anti-silent-loss guarantee that retired the old "Someday project" (#743). Consolidates #745 + #743 + #715 + #524.
- [Journal Process Flow](<./design/process-flows/journal.md>) — *Explanation/Reference* — captures classified "journal" → a single-shot, dated, atomic append into the `08-Journal/` vault tree (no ask/pending/sweep). Sentinel + verify-before-append idempotency. Consolidates the D6 helper-extraction and atomic-finalize missions.
- [Habits Process Flow](<./design/process-flows/habits.md>) — *Explanation/Reference* — the habit completion lifecycle: morning check-in → `record_completion` (done=true POST echoing repeat_after #524; JSONL history) → 48h auto-skip sweeper → reconcile, plus the EOD-ET write (#112) and the #409 weekly-report ownership relocation. Consolidates the native-repeat/JSONL-state, day-specific-scheduling, and trustworthy-weekly-report missions.

### docs/design/coherence/ — Coherence doctrine (Foundation 3)

- [Coherence Practice](<./design/coherence/README.md>) — the anti-myopia practice: how the point-cut coherence review, the action-scoped injection map, and the 3-boolean significance gate work (Bedrock Foundation 3, #677; machinery deferred to #643)
- [Felix Doctrine — Scoped Invariants](<./design/coherence/doctrine.md>) — canonical `INV-###` cross-cutting invariants (no-fabrication, no-silent-fallback, alerting seam, self-contained workspaces)
- [Decision Corpus](<./design/coherence/decisions.jsonl>) — append-only `DEC-###` decision markers that establish and cite the invariants

### docs/design/standards/ — Cross-cutting standards

- [Divio Classification Standard](<./design/standards/divio-classification.md>)
- [Documentation Standards](<./design/standards/doc-standards.md>)
- [Visual Documentation Style](<./design/standards/visual-docs-style.md>)
- [Obsidian Linter Alignment](<./design/standards/obsidian-linter-alignment.md>)
- [Allowed Values (JSON)](<./design/standards/allowed-values.json>)
- [Validator Policy (JSON)](<./design/standards/validator-policy.json>)

---

## Feature Specifications (docs/archive/func-spec/)

Historical archive. Features F001-F020 are documented here as the
historical record. New features are tracked as GitHub Issues — see
[GitHub Issues Workflow](<./runbooks/github-issues-workflow.md>).

Templates:

- [Feature Specification Template](<./archive/func-spec/_TEMPLATE_spec_kitty_input.md>)
- [Research Mission Template](<./archive/func-spec/_TEMPLATE_spec_kitty_research_input.md>)
- [Docs Debt Issue Template](<../.github/ISSUE_TEMPLATE/docs-debt.md>)
- [Research Issue Template](<../.github/ISSUE_TEMPLATE/research.md>)

---

## Diagnostics (docs/diagnostics/)

Active troubleshooting and upstream bug reporting.

- [Spec-Kitty Workflow Journal](<./diagnostics/spec-kitty-workflow-journal.md>) — running observations log; promote stabilized entries to internal kg-automation issues per the bug-reporting runbook
- [Spec-Kitty External Bug Report Template](<./diagnostics/spec-kitty-bug-report-external-template.md>) — slim template for upstream submission; source for transient paste docs at `{slug}-external.md`
- [Spec-Kitty Upstream Issue Comment Template](<./diagnostics/spec-kitty-upstream-comment-template.md>) — peer template for commenting on an *existing* upstream issue (recurrence/persistence, supplying a missing build SHA, evidence, or responding to a maintainer); mandates the 9-char build ID and the pre-posting approval gate
- [Spec-Kitty Bug Report Template (deprecated)](<./diagnostics/spec-kitty-bug-report-template.md>) — original combined internal+external template; superseded 2026-05-28 by the dual-track workflow (internal issue template at `.github/ISSUE_TEMPLATE/spec-kitty-bug.md` + external template above); retained as reference during the migration window

---

## Archive (docs/archive/)

Frozen historical artifacts. Not maintained. Excluded from this index.

---

## Adding a New Document

1. Identify the Divio type per [Divio Classification Standard](<./design/standards/divio-classification.md>).
2. Place the file in the canonical home for that type.
3. Add frontmatter (`title`, `doc_type`, `status` minimum; `audience` required for runbooks).
4. **Update this INDEX.md** in the same change.
