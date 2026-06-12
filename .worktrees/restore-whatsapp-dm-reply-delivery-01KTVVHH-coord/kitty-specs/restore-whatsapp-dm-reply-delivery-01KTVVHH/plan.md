# Implementation Plan: Restore WhatsApp DM Reply Delivery

**Mission**: `restore-whatsapp-dm-reply-delivery-01KTVVHH`
**Mission ID**: `01KTVVHHBJKKG3JPMGRVHSB81P` (mid8 `01KTVVHH`)
**Spec**: [`spec.md`](spec.md)
**Source**: GitHub issue [#588](https://github.com/kentonium3/kg-automation/issues/588)
**Mission type**: software-dev (bug fix)
**Date**: 2026-06-11
**Branch contract**: planning + merge target = `kitty/mission-restore-whatsapp-dm-reply-delivery-01KTVVHH`; mission rolls up to `main` at mission-end via spec-kitty merge gate

## Summary

Bug-fix mission targeting the openclaw-gateway's WhatsApp DM-reply dispatch wiring on office2. Diagnosis is documented in [`research.md`](research.md); the observed runtime state machine is documented in [`data-model.md`](data-model.md); the lifecycle and journal contracts that frame acceptance are in [`contracts/`](contracts/); and the operator-driven smoke is in [`quickstart.md`](quickstart.md). The implementation lane is bounded by FR-009/C-001: if root cause turns out to be in the vendored `openclaw` runtime, the mission concludes with an internal tracking issue and documented workaround.

## Technical Context

**Language/Version**: Bash (deploy script), Python 3.10+ (any helper or test scaffolding). No new TypeScript/JS — vendored openclaw runtime is read-only per C-001.
**Primary Dependencies**: openclaw 2026.5.28 (vendored npm-global), `@openclaw/whatsapp` plugin, systemd user units, paired WhatsApp Web session.
**Storage**: None new. Mission does not introduce persistent storage.
**Testing**: `pytest` for any Python helper added by the deploy script; operator-driven smoke via `journalctl --user -u openclaw-gateway` + WhatsApp client per [`contracts/journal-event-assertions.md`](contracts/journal-event-assertions.md). Operator-in-the-loop by design (Decision D5 in research).
**Target Platform**: Linux (office2 Ubuntu 24.04 LTS, claude user, Tailscale-internal). DIR-001, DIR-002.
**Project Type**: bug-fix at the openclaw agent-config / openclaw.json layer. No new service surface; possibly new config keys; possibly an AGENTS.md edit.
**Performance Goals**: DM reply latency < 30s (NFR-001); 0 `sessions.resolve current` errors per smoke (NFR-002); cron-announce latency stays < 1s (NFR-004).
**Constraints**: Tier 2 (Restic ≤24h, rebaseline trailer per #557, audited surfaces touched per `audited-surfaces.json`); SSH as `office2-claude` only; no sudo; no system crontab.
**Scale/Scope**: Single bug. Reconciles 2 architecture JSONs + 2 architecture markdown views + 1 runbook + 2 memories per FR-012 (DR-1 through DR-9 in `data-model.md`). Expected ~3–5 work packages.

## Charter Check

*GATE: passes Phase 0 and Phase 1.*

Per `spec-kitty charter context --action plan --json` (mode: compact; software-dev-default template set; c4-incremental-detail-modeling paradigm).

### Built-in directives (DIRECTIVE_001 … DIRECTIVE_034)

| Directive | Compliance |
|---|---|
| DIRECTIVE_001 (Architectural Integrity) | Mission only repairs existing runtime wiring; no new component boundaries. ✓ |
| DIRECTIVE_003 (Decision Documentation) | All decisions recorded in `research.md` §5 (D1–D6). ✓ |
| DIRECTIVE_010 (Specification Fidelity) | Implementation lane gates against the FR/NFR/SC tables in `spec.md`; no scope creep. ✓ |
| DIRECTIVE_024 (Locality of Change) | Mission touches only openclaw config + (possibly) one agent prompt; deploy script + doc-sync are mission-local. ✓ |
| DIRECTIVE_031 (Context-Aware Design) | Bounded context = "openclaw gateway runtime wiring"; doc-sync edits respect JSON-first/markdown-second hierarchy. ✓ |
| DIRECTIVE_033 (Targeted Staging) | Per-WP commits stage only that WP's expected deliverables. ✓ |
| DIRECTIVE_034 (Test-First) | Smoke contract authored before implementation (`contracts/journal-event-assertions.md`). ✓ |

### Project directives (DIR-001 … DIR-015)

| Directive | Compliance |
|---|---|
| DIR-001 (Production on office2) | All deploys land on office2 via `ssh office2-claude`. ✓ |
| DIR-002 (Linux-only) | All scripts target Linux; no Windows references. ✓ |
| DIR-003 (Tailscale-only exposure) | No new ports opened; openclaw-gateway already binds loopback. ✓ |
| DIR-004 (Deploy script required) | `scripts/deploy/deploy-restore-whatsapp-dm-reply-delivery.sh` is in the WP scope. ✓ |
| DIR-005 (Strict-order safe-deploy) | Deploy script follows pre-flight → copy artifacts → verify artifacts → edit config → post-flight smoke. ✓ |
| DIR-006 (No cron pause/resume) | Mission does not touch the cron path; cron `announce` continues unchanged. ✓ |
| DIR-007 (No system crontab) | Mission does not touch any cron config. ✓ |
| DIR-008 (Real service paths) | All deploys reference canonical paths from `/home/claude/.openclaw/openclaw.json` and `audited-surfaces.json`. ✓ |
| DIR-009 (Tier 2 Restic ≤24h) | Deploy wrapper accepts `--backup-confirmed`; quickstart §4.1 documents the attestation path. ✓ |
| DIR-010 (c4-incremental-detail-modeling) | Plan → Research → Data-model → Contracts → Quickstart, each layer adds concrete detail. ✓ |
| DIR-011 (Privacy boundaries) | No `04-Growth/_private/` access; no second-brain writes from this mission. ✓ |
| DIR-012 (Doc sync) | FR-012 + DR-1..DR-9 in `data-model.md` E4 explicitly enumerate the reconciliation. ✓ |
| DIR-013 (Doc standards) | JSON-first, markdown-second; Mermaid `.view.md` updates are part of DR-5. ✓ |
| DIR-014 (Doc-sync requirement) | Spec has FR-011 + FR-012 explicit; data-model E4 enumerates targets. ✓ |
| DIR-015 (Probe real env during design) | `research.md` §3 documents the live diagnostic probe of office2; full root-cause depth chosen per Decision `01KTVXK5AT0X8BC5EAEDHBGYV8`. ✓ |

### Rebaseline obligation (#557)

The mission touches `openclaw-config` (and possibly `openclaw-agent-prompts`), both listed in `docs/design/architecture/data/audited-surfaces.json`. Per quickstart §4.7:

```bash
ssh office2-claude 'rm /data/services/security-monitor/baselines/* && sg docker -c /data/services/security-monitor/scripts/audit.sh'
```

The mission's merge commit MUST carry `Rebaseline: completed at <ISO8601-UTC>`.

## Project Structure

### Documentation (this mission)

```
kitty-specs/restore-whatsapp-dm-reply-delivery-01KTVVHH/
├── plan.md                                 # This file
├── research.md                             # Phase 0 — diagnostic findings + decisions D1–D6
├── data-model.md                           # Phase 1 — E1 Session, E2 EmbeddedRun, E3 ChannelEvent, E4 DocReconciliation, E5 RebaselineAttestation
├── quickstart.md                           # Phase 1 — operator runbook (reproduce / ramp / deploy / smoke / rollback)
├── contracts/
│   ├── embedded-run-lifecycle.md           # Phase 1 — gateway-internal lifecycle contract
│   └── journal-event-assertions.md         # Phase 1 — POSIX-ERE patterns + operator smoke command
├── checklists/
│   └── requirements.md                     # Spec-quality checklist (from specify phase)
├── meta.json                               # Mission identity + vcs + source_description
└── tasks/                                  # /spec-kitty.tasks will populate (NOT created here)
```

### Source Code (repository root)

```
scripts/
├── openclaw/
│   └── agents/
│       └── main/
│           └── AGENTS.md                   # Potentially touched (H3 in research §4)
├── deploy/
│   └── deploy-restore-whatsapp-dm-reply-delivery.sh  # NEW — required by DIR-004/005
└── (no new Python helpers anticipated, but if needed: scripts/openclaw/diagnose/*.py)

docs/
├── design/architecture/
│   ├── data/
│   │   ├── service-inventory.json          # DR-1 (FR-012)
│   │   ├── data-flows.json                 # DR-2 (FR-012)
│   │   └── audited-surfaces.json           # DR-3 (FR-012, verify-only likely)
│   ├── service-inventory.md                # DR-4
│   ├── data-flows.md                       # DR-5
│   └── data-flows.view.md                  # DR-5 (Mermaid)
├── runbooks/
│   └── openclaw-agent-setup.md             # DR-6 (FR-012)
└── INDEX.md                                # DR-7 (conditional)
```

**Structure Decision**: kg-automation does not follow a "single project src/ + tests/" layout — it's a polyrepo-style infrastructure-as-code tree. The directories above reflect the existing kg-automation organization (`scripts/openclaw/agents/<slug>/` per-agent prompts, `scripts/deploy/<mission-slug>.sh` per-mission deploys, `docs/design/architecture/data/*.json` machine-readable canon + parallel `.md` narratives). No structural reorganization is needed for this mission.

## Complexity Tracking

Charter Check has no unresolved violations. This section is empty.

## Implementation Concern Map

> Implementation concerns are NOT work packages. `/spec-kitty.tasks` will translate these into executable WPs. Concerns may be decomposed or merged at that stage.

### IC-01 — Diagnostic ramp

- **Purpose**: Validate the H2–H5 hypotheses from research §4 in cost order (H5 plugin → H4 config swap → H2 missing field → H3 AGENTS.md rollback probe), or escalate to H1 (vendored runtime) and conclude per FR-009 if all in-scope hypotheses fail.
- **Relevant requirements**: FR-007 (recent-changes audit), FR-009 (vendored escalation), FR-011 (arch-docs baseline), C-001 (no vendored mods), C-002 (investigation prior).
- **Affected surfaces**: read-only — `journalctl`, `/home/claude/.openclaw/openclaw.json`, `~/.openclaw/agents/*/agent/`, `/usr/lib/node_modules/openclaw/dist/`. May briefly mutate one config file or `/data/services/openclaw/data/AGENTS.md` as part of a fast-rollback probe.
- **Sequencing/depends-on**: none.
- **Risks**: H1 escalation closes the mission without a fix. Captured in spec FR-009/C-001 and risk table below.

### IC-02 — Apply fix (conditional on IC-01 outcome)

- **Purpose**: Ship the smallest change that satisfies SC-001 through SC-007. Shape depends on which hypothesis validated in IC-01: a config edit (H2/H4), an AGENTS.md edit (H3), or a plugin reinstall (H5).
- **Relevant requirements**: FR-001 (dispatch routing), FR-002 (Sending fires), FR-003 (typing indicator), FR-004 (proximate cause), FR-006 (preserve #579), FR-008 (deploy script), FR-010 (E2E smoke).
- **Affected surfaces**: depending on hypothesis — `scripts/openclaw/openclaw.json` (or equivalent deploy-time config), `scripts/openclaw/agents/main/AGENTS.md`, `scripts/deploy/deploy-restore-whatsapp-dm-reply-delivery.sh`.
- **Sequencing/depends-on**: IC-01 must produce a named root cause.
- **Risks**: deploy could regress cron-announce path; mitigated by post-flight smoke in deploy script + SC-005 next-day check.

### IC-03 — Architecture doc reconciliation

- **Purpose**: Land DR-1 through DR-7 (per `data-model.md` E4): bump `service-inventory.json` to v2026.5.28 + correct `dm_policy` + add `session.dmScope`; add `whatsapp-dm-reply` flow to `data-flows.json` + parallel narrative + Mermaid; verify `audited-surfaces.json`; mirror narrative updates; add runbook troubleshooting section.
- **Relevant requirements**: FR-011 (read-baseline-first), FR-012 (reconcile-at-fix), DIR-014 (doc-sync requirement), DIR-008 (real service paths).
- **Affected surfaces**: `docs/design/architecture/data/*.json`, `docs/design/architecture/*.md`, `docs/design/architecture/*.view.md`, `docs/runbooks/openclaw-agent-setup.md`, `docs/INDEX.md` (conditional).
- **Sequencing/depends-on**: independent of IC-02. Can run in parallel once IC-01 produces a root cause (so the doc updates reflect the actual fix shape).
- **Risks**: missing a doc surface; mitigated by `signal-to-doc-map.json` change-class lookup per FR-012.

### IC-04 — Memory + audit-trail updates

- **Purpose**: Land DR-8 (correct `project_whatsapp_dmpolicy` from `disabled` → `allowlist`) and DR-9 (new `reference_openclaw_dm_reply_lifecycle` capturing the lifecycle markers + stuck-session signature).
- **Relevant requirements**: FR-012 (broad doc reconciliation), aligns with `observability per feature` engineering principle.
- **Affected surfaces**: `~/.claude/projects/-Users-kentgale-repos-kg-automation/memory/*.md` (plus `MEMORY.md` index update).
- **Sequencing/depends-on**: independent. Can land alongside IC-03.
- **Risks**: forgotten if not explicitly enumerated — IC-04 makes it explicit.

### IC-05 — Deploy + acceptance smoke

- **Purpose**: Execute the deploy script on office2, run the 5-DM smoke (SC-001 through SC-007), perform the #557 rebaseline, attest with the merge trailer.
- **Relevant requirements**: FR-008 (deploy), FR-010 (E2E smoke), C-003 (Tier 2 + #557), SC-001..SC-007.
- **Affected surfaces**: office2 only (no repo writes); commit message trailer on the final mission commit.
- **Sequencing/depends-on**: IC-02 (deploy artifact). May run in parallel with IC-03/IC-04 doc reconciliation, but the rebaseline trailer must be present in the merge commit.
- **Risks**: smoke fails (rollback via quickstart §4.6); cron regression next day (SC-005 next-day check); rebaseline forgotten (mitigated by explicit attestation gate).

### IC-Alt — Mission-conclusion escalation (only if IC-01 reaches H1)

- **Purpose**: If H1 (vendored runtime) is the standing candidate after IC-01 exhausts H2–H5, file an internal tracking issue with all gathered evidence and conclude.
- **Relevant requirements**: FR-009 (concludes with internal issue + workaround), C-001 (no vendored mods).
- **Affected surfaces**: new GitHub issue via `gh issue create`; possibly a brief workaround doc.
- **Sequencing/depends-on**: branches off IC-01 if all in-scope hypotheses fail.
- **Risks**: operator UX during the bug — until the upstream / runtime fix lands, DM-reply remains broken. Captured in spec Impact section.

## Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| H1 (vendored runtime regression) is the actual root cause; H2–H5 fail | Medium (~50%) | Mission concludes without delivering the fix | FR-009 + C-001 explicitly cover this path; quickstart §3.5 documents escalation |
| Diagnostic probe destabilizes the gateway | Low | Operator-visible downtime | All probes are read-only or have fast rollback; Tier 2 pre-flight + DIR-009 backup attestation |
| AGENTS.md rollback probe (H3) leaves wrong file deployed | Low | Persistent regression | Quickstart §3.4 saves current copy first, rolls back regardless of outcome |
| Deploy script breaks cron `announce` path | Low | Morning checkin / IDLE pings stop | DIR-005 strict-order + post-flight smoke catches; SC-005 next-day regression check confirms |
| Rebaseline forgotten | Medium | Daily security-monitor noise | Quickstart §4.7 makes explicit; merge trailer is required per #557 |
| spec-kitty rc40/41 workflow gotchas | High | Workflow may stall at task-finalize or merge boundary | Apply documented workarounds: `.worktrees/` in `.gitignore` (preventive); fast-forward main at lifecycle handoffs (#1784 workaround); `spec-kitty agent tasks status` instead of dashboard during active mission (#1824 workaround). Upgrade to rc42 after mission. |

## Out of Scope

Repeated from `spec.md` for plan-completeness:

- Modifying vendored `/usr/lib/node_modules/openclaw/dist/*` (C-001)
- Upgrading or downgrading the openclaw runtime
- Re-pairing WhatsApp on office2
- Cron-mode behavioral changes; multi-number routing; `dmPolicy` semantic changes (the working `allowlist` policy stays)
- Migration of `felix-admin-*` agent set membership
- Generic "WhatsApp UX improvements"

## Bulk-edit check

Not a bulk edit. Runtime/wiring bug fix; no identifier/path/key/term is being renamed across many files. The doc reconciliation touches multiple files but each edit is distinct (not the same string repeated). `meta.json#change_mode` remains default; no `occurrence_map.yaml`.

## Branch contract (restated #2 of 2)

- **Current branch**: `kitty/mission-restore-whatsapp-dm-reply-delivery-01KTVVHH` (coordination)
- **Planning + base branch during mission**: same
- **Final merge target at mission-end**: `main` (via spec-kitty merge gate)
- **Match with user's intended landing branch**: ✓ (kg-automation convention is direct-to-main; spec-kitty 3.2 routes through coord first)

## Next step

User runs `/spec-kitty.tasks` to translate IC-01 through IC-05 (or IC-Alt) into concrete work packages. Plan-phase is complete; this command stops here per the MANDATORY STOP POINT.
