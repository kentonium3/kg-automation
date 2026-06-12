# Implementation Plan: Pull-Based Deploy Pipeline with Tier Guard and Doctrinal Anchor

**Branch**: `main` | **Date**: 2026-06-12 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `kitty-specs/pull-based-deploy-pipeline-01KTYQQS/spec.md`
**Mission**: `pull-based-deploy-pipeline-01KTYQQS` (mid8 `01KTYQQS`)
**Source issue**: kentonium3/kg-automation#136 (Epic #533; supersedes #154; captures #549)

## Summary

Establish a pull-based deploy pipeline where office2 pulls deploy manifests from GitHub on a schedule, applies them using a shared Python library of vetted primitives, enforces tier-aware controls at PR-time and execute-time, and anchors the discipline in agent-facing surfaces (charter rule, CLAUDE.md, signal-to-doc-map, issue templates, new canonical runbook) so future specify/plan runs automatically incorporate it.

Implementation choices locked during planning:
- **Language**: Python 3.10+ (matches existing `scripts/` codebase; office2 has it)
- **Manifest format**: YAML files validated by JSON Schema (PyYAML + jsonschema)
- **Applier scheduling**: systemd user timer + `Type=oneshot` service (natural serialization — no extra locking needed)
- **DM dispatch**: applier invokes existing openclaw cron with a synthesized payload (no new outbound surface, no new credential consumer)
- **Notification policy**: WhatsApp DM only on apply failure; no success-path traffic
- **Bootstrap**: deploy-felix-deployer-bootstrap.sh follows canonical `deploy-149.sh` shape and writes `deploys/applied/0001-bootstrap-felix-deployer.yaml` as the historical first entry / canonical example

## Technical Context

**Language/Version**: Python 3.10+
**Primary Dependencies**: PyYAML (manifest parsing), jsonschema (manifest validation against canonical schema), standard library `subprocess` for `git pull` and `openclaw cron` invocation; no new heavyweight deps
**Storage**: Filesystem — `deploys/queued/`, `deploys/applied/`, `deploys/failed/` in the repo; structured JSONL tick log at `/data/services/felix-deployer/logs/`
**Testing**: pytest with `subprocess.run` mocks for unit + integration; one CI integration test runs the full applier loop against a synthetic mock-git tree; a doctrinal cross-link integrity test exercises the discipline-surface graph (CLAUDE.md ↔ runbook ↔ charter ↔ signal-to-doc-map ↔ issue templates) and runs in <30s; smoke test via `--dry-run` on a no-op manifest at acceptance time
**Target Platform**: Linux (Ubuntu 24.04 LTS on office2); Mac authoring
**Project Type**: single (Python package + bash bootstrap wrapper + systemd user units + CI workflow + doctrine docs)
**Performance Goals**: applier tick ≤30s for typical no-op poll; ≤5 min for a typical small deploy; CI doctrinal-link check ≤30s wall-clock; WhatsApp DM dispatch ≤60s from failure detection
**Constraints**: pull-only architecture (office2 pulls from GitHub; Mac never pushes directly); Tailscale-internal only; no system crontab mutation (OpenClaw cron interface is the canonical surface); Tier 0 hard-locked at CI and at execute time; office2 is the only deploy target
**Scale/Scope**: ~10 deploys/month sustainably; one applier instance on office2; one DM recipient (operator)

## Charter Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

The Felix project charter (`.kittify/charter/charter.md`) declares relevant deployment governance under **Deployment Constraints**:

1. **"Production services run on office2"** — ✅ aligned. The applier runs on office2; nothing runs on Mac except authoring.
2. **"Target Linux by default"** — ✅ aligned.
3. **"Tailscale-only service exposure"** — ✅ aligned. The applier never opens a port; it pulls from GitHub over the public internet (allowed; GitHub is not a managed service) and reaches OpenClaw locally.
4. **"Every feature that deploys ... must include a deploy script at `scripts/deploy/deploy-f{NNN}.sh`"** — ⚠️ this is the rule the mission **rewrites**. The mission ships a charter amendment in the same merge: the rule is replaced with the manifest discipline. Charter and code stay in sync from the merge commit forward.
5. **"Deploy scripts follow the strict-order-of-operations safe-deploy pattern"** — ✅ inherited; the bootstrap wrapper continues this pattern; the library primitives codify it.
6. **"System crontab is never used"** — ✅ inherited as a binding constraint on the library; CI enforces it.
7. **"Tier 2 pre-flight requires Restic ≤24h"** — ✅ encoded in `lib/snapshot.py` (`verify_restic_recent`); manifest schema requires a verification block on Tier 1/2.

**Change-Risk Taxonomy** (`docs/design/architecture/data/change-risk-taxonomy.json`):
- This mission itself is **Tier 3** (logic/workflow; new Python library, deploy scripts, agent prompts).
- The bootstrap deploy of `felix-deployer` is a **Tier 1** deploy (new systemd user unit + new service) — must pass the verification block requirement encoded in the schema.
- Tier 0 deploys are explicitly out of scope and rejected at both CI and execute time.

**Rebaseline Obligation (#557)**: ✅ **Required.** This mission touches audited surfaces — `scripts/deploy/lib/`, `scripts/deploy/felix-deployer/` (new systemd user units), and the bootstrap script. Merge commit must record `Rebaseline: completed at <ts>` per `docs/runbooks/security-baseline-ops.md`.

**Gate**: PASS with one declared inversion — the charter rule (item 4) is itself the target of this mission's rewrite. Acceptable because the rewrite lands in the same merge commit; there is no window where the new code and old rule coexist on main.

## Project Structure

### Documentation (this mission)

```
kitty-specs/pull-based-deploy-pipeline-01KTYQQS/
├── spec.md              # ✓ committed
├── plan.md              # this file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   ├── manifest-v1.schema.json     # canonical manifest schema
│   ├── dm-payload-v1.md            # openclaw cron payload contract for DM
│   └── deploy-library-api.md       # Python library API contract
├── checklists/
│   └── requirements.md  # ✓ committed
├── meta.json            # ✓ committed
└── tasks/               # (populated by /spec-kitty.tasks, not by /spec-kitty.plan)
```

### Source Code (repository root)

```
scripts/deploy/lib/                 # IC-02 — Python deploy primitives library
├── __init__.py
├── cron.py                         # openclaw_cron_disable/enable/edit (subprocess wrappers)
├── snapshot.py                     # verify_restic_recent
├── verify.py                       # verify_file_present, verify_no_stale_literal
├── tier.py                         # tier_guard(mode='ci'|'runtime')
├── apply.py                        # dry_run_then_apply_gate orchestrator
└── README.md                       # library API summary; links to contracts/deploy-library-api.md

scripts/deploy/felix-deployer/      # IC-03 + IC-04 — the applier
├── deployer.py                     # entrypoint: pull, scan queue, apply, record outcome
├── notify.py                       # WhatsApp DM via openclaw cron payload synthesis
├── felix-deployer.service          # systemd user unit (Type=oneshot)
└── felix-deployer.timer            # systemd user timer (5-min cadence)

scripts/deploy/                     # IC-05 + grandfathered
├── deploy-felix-deployer-bootstrap.sh  # one-shot bootstrap (canonical example)
├── deploy-028.sh                   # grandfathered — NOT modified
├── deploy-149.sh                   # grandfathered — NOT modified (still the reference shape)
├── deploy-f013.sh                  # grandfathered — NOT modified
├── deploy-f014.sh                  # grandfathered — NOT modified
├── deploy-f026.sh                  # grandfathered — NOT modified
├── deploy-felix-admin-calendar.sh  # grandfathered — NOT modified
└── deploy-restore-whatsapp-dm-reply-delivery.sh   # grandfathered — NOT modified

deploys/                            # IC-01 — manifest queue + history
├── queued/
│   └── .gitkeep
├── applied/
│   ├── .gitkeep
│   └── 0001-bootstrap-felix-deployer.yaml   # retroactive canonical example (written by bootstrap)
├── failed/
│   └── .gitkeep
└── schema/
    └── manifest-v1.schema.json     # canonical schema (also in contracts/)

docs/runbooks/deploy/               # IC-08 — doctrinal runbook
└── discipline.md                   # operational how-to + library summary

docs/runbooks/deployment.md         # IC-08 — rewritten to point at deploy/discipline.md

docs/design/architecture/data/      # IC-10 — architecture data updates
├── service-inventory.json          # + felix-deployer entry
├── data-flows.json                 # + github-to-office2-deploy-pull flow
├── audited-surfaces.json           # + deploys/ + scripts/deploy/lib/ paths
├── signal-to-doc-map.json          # + 3 deploy change-classes (mapping entries)
└── mutation-surfaces.json          # + deployer mutation surface

.github/workflows/                  # IC-06 — CI tier guard + cross-link check
└── deploy-manifest-validate.yml    # validates schema + rejects tier 0

.github/ISSUE_TEMPLATE/              # IC-09 — issue template hooks
├── feature.md                      # + "Deploy required?" prompt
└── infra.md                        # + "Deploy required?" prompt

CLAUDE.md  (kg-automation root)     # IC-09 — agentic visibility surface
                                    # + "Deploys to office2" section pointing at discipline.md

tests/
├── unit/
│   ├── test_cron.py                # IC-02
│   ├── test_tier.py                # IC-02
│   ├── test_verify.py              # IC-02
│   └── test_apply.py               # IC-02
├── integration/
│   ├── test_deployer.py            # IC-03 — full applier loop with subprocess mocks
│   ├── test_cross_link.py          # IC-06 — discipline cross-link integrity
│   └── test_bootstrap_record.py    # IC-05 — bootstrap writes applied/0001-... correctly
└── contract/
    └── test_manifest_schema.py     # IC-01 — schema validates canonical fixtures
```

## Implementation Concern Map

A multi-developer/agent mission. Decomposing the architecture into Implementation Concerns (`IC-##`) so `/spec-kitty.tasks` can lay them out into work packages.

| IC | Concern | Primary surfaces | Depends on |
|----|---------|------------------|------------|
| **IC-01** | Manifest schema authoring & validation | `deploys/schema/manifest-v1.schema.json` + `contracts/manifest-v1.schema.json` + `tests/contract/test_manifest_schema.py` | — |
| **IC-02** | Python deploy library | `scripts/deploy/lib/{cron,snapshot,verify,tier,apply}.py` + `lib/README.md` + `tests/unit/test_*.py` | IC-01 (for tier signatures) |
| **IC-03** | felix-deployer applier core | `scripts/deploy/felix-deployer/deployer.py` + `.service` + `.timer` + `tests/integration/test_deployer.py` | IC-01, IC-02 |
| **IC-04** | WhatsApp DM dispatch (openclaw cron payload) | `scripts/deploy/felix-deployer/notify.py` + integration test stubs | IC-03 |
| **IC-05** | Bootstrap wrapper + retroactive applied entry | `scripts/deploy/deploy-felix-deployer-bootstrap.sh` + `deploys/applied/0001-bootstrap-felix-deployer.yaml` + `tests/integration/test_bootstrap_record.py` | IC-01, IC-02, IC-03, IC-04 |
| **IC-06** | CI tier guard + doctrinal cross-link verification | `.github/workflows/deploy-manifest-validate.yml` + `tests/integration/test_cross_link.py` | IC-01, IC-07, IC-08, IC-09, IC-10 |
| **IC-07** | Charter Deployment Constraints rewrite | `.kittify/charter/charter.md` + `spec-kitty charter sync` | — |
| **IC-08** | Doctrinal runbook | `docs/runbooks/deploy/discipline.md` (new) + `docs/runbooks/deployment.md` (rewrite) | IC-01, IC-02 (for accuracy) |
| **IC-09** | CLAUDE.md + issue template hooks | `kg-automation/CLAUDE.md` + `.github/ISSUE_TEMPLATE/{feature,infra}.md` | IC-08 |
| **IC-10** | Architecture data updates | 5 JSON files under `docs/design/architecture/data/` | IC-03 (for service inventory accuracy) |
| **IC-11** | Mission acceptance + rebaseline | merge commit `Rebaseline:` line + post-merge baseline reset on office2 | all |

## Doctrinal cross-link graph (the IC-06 invariant)

This is the graph the CI cross-link test walks. Every edge must be present in the merge commit.

```
CLAUDE.md (kg-automation root, "Deploys to office2" section)
  └→ docs/runbooks/deploy/discipline.md

.kittify/charter/charter.md (Deployment Constraints rule, rewritten)
  └→ docs/runbooks/deploy/discipline.md
  └→ scripts/deploy/lib/README.md

docs/runbooks/deployment.md (rewritten)
  └→ docs/runbooks/deploy/discipline.md

docs/design/architecture/data/signal-to-doc-map.json
  ├→ docs/runbooks/deploy/discipline.md   (via doc_targets on deploy-* mappings)
  └→ scripts/deploy/lib/README.md         (via doc_targets on deploy-* mappings)

.github/ISSUE_TEMPLATE/feature.md
  └→ docs/runbooks/deploy/discipline.md

.github/ISSUE_TEMPLATE/infra.md
  └→ docs/runbooks/deploy/discipline.md
```

The CI test fails the build if any link in this graph is missing or broken.

## Branch contract

Re-stated per runbook requirement.

- **Current branch at plan start**: `main`
- **Planning/base branch for this feature**: `main`
- **Final merge target for completed changes**: `main`
- `branch_matches_target`: `true`

Plan commits land on the coordination branch `kitty/mission-pull-based-deploy-pipeline-01KTYQQS` (per the rc42 safe-commit refusal workaround), then FF main at the plan→tasks lifecycle handoff.
