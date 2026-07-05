# Feature Specification: Observation-Digest Log Repoint & Decommission

**Mission**: observation-digest-repoint-01KWS2E2
**Type**: software-dev
**Source issue**: kentonium3/kg-automation#659 (fast-follow to #656)
**Status**: Draft

## Overview

Felix's **observation-digest subsystem** (`felix-core-digest`, feature F014) runs on
office2 as a systemd **user** timer (user `claude`, every 15 minutes). On each tick it
writes raw per-agent activity logs (JSONL) and produces a human-readable digest.

The raw logs currently land in a **stray tree** — `/home/claude/second-brain/agents/logs/`
— on the `claude` service account, outside Kent's real account and outside the backed-up
vault. A prior fix (#656) relocated the *inbox* subsystem's state and logs off that stray
tree but deliberately **narrowed** its decommission, because this observation writer still
targets it. This mission finishes the job: repoint the remaining writer to the backed-up
vault-account path, migrate the historical logs, and fully **decommission** the stray tree.

### Grounding facts (verified against deployed code, 2026-07-05)

- The **only** runtime path still resolving onto the stray tree is the raw **input log
  dir**: `scripts/openclaw/observation/config.py:40` defaults `log_dir` to
  `Path.home()/second-brain/agents/logs`, which resolves to `/home/claude/…` because the
  deployed unit `felix-core-digest.service` sets `Environment=HOME=/home/claude` and passes
  no `--log-dir` override.
- The **digest output** dir (`config.py:41`) already resolves through the vault registry to
  `/home/kgale/second-brain/notes/00-System/agent-activity/Agent-Logs/` — **already synced.**
  The architecture docs recording the output at `/home/claude/second-brain/notes/Agent-Logs/`
  are **stale**, not a live defect.
- No systemd unit edit is required: making the `log_dir` default an absolute, registry-resolved
  path removes the `HOME` dependency.

## Domain Language

| Canonical term | Meaning | Avoid |
|---|---|---|
| **stray tree** | `/home/claude/second-brain` — directory on the `claude` service account, not backed up, to be decommissioned | bare "second-brain" |
| **vault** | `/home/kgale/second-brain` — Kent's account; the Obsidian **vault** proper is its `notes/` subtree | bare "second-brain" |
| **vault log dir** | `/home/kgale/second-brain/agents/logs` — sibling of `notes/`; backed-up account, intentionally **not** Obsidian-synced | — |
| **raw logs** | per-action JSONL at `agents/logs/{agent}/YYYY-MM-DD.jsonl` — forensic, high-volume | "logs" (ambiguous) |
| **digest** | human-readable Markdown summary under `…/00-System/agent-activity/Agent-Logs/` — already vault-synced | — |

## User Scenarios & Testing

The "user" here is the **operator** (Kent) and the automated **felix-deployer** pipeline;
there is no human-facing UI.

### Primary scenario — repointed writer

1. The mission merges; felix-deployer pulls `main` and applies the queued migration manifest.
2. On the next 15-minute `felix-core-digest.timer` tick, `log_action.py` writes the agent's
   activity log to `/home/kgale/second-brain/agents/logs/{agent}/YYYY-MM-DD.jsonl`.
3. Nothing is written under `/home/claude/second-brain`.
4. The digest continues to be produced at the unchanged, already-synced vault output path.

### Migration scenario — historical logs + decommission

1. The deploy manifest runs the one-time migrator under a Tier-2 Restic snapshot gate.
2. Historical raw logs are **union-merged** from the stray tree into the vault log dir
   (copy-before-cutover; no entry lost or duplicated).
3. After cutover is verified, the entire `/home/claude/second-brain` tree is removed.
4. Post-checks confirm absence of the stray tree and correct ownership/mode on the vault dir.

### Exception & edge cases

- **Live writer still targets stray tree at decommission time** → the migrator MUST abort
  before removal (fail-safe) and surface the condition; no destructive step runs.
- **Restic snapshot older than 24h** → the snapshot gate fails; a fresh snapshot is taken
  before proceeding.
- **Re-run after completion** → idempotent no-op (convergent).
- **Interrupted migration** → copy-before-cutover keeps the source intact until the copy is
  verified; safe to resume.

## Requirements

### Functional Requirements

| ID | Requirement | Status |
|---|---|---|
| FR-001 | The observation-digest raw `log_dir` default MUST resolve to an absolute, backed-up vault-account path (`/home/kgale/second-brain/agents/logs`) independent of `HOME`, so that under the deployed service account raw logs no longer land on the stray tree. | Draft |
| FR-002 | Existing historical raw logs under the stray tree MUST be migrated to the vault log dir with no entry lost or duplicated (union-merge of overlapping per-day JSONL files). | Draft |
| FR-003 | After migration and verified cutover, the entire stray tree (`/home/claude/second-brain`) MUST be removed (decommissioned). | Draft |
| FR-004 | Decommission MUST be preceded by a verification that no writer targets the stray tree; if any writer is detected, the destructive step MUST abort. | Draft |
| FR-005 | The migration + decommission MUST be idempotent and convergent (safe to re-run; completed state re-runs as a no-op). | Draft |
| FR-006 | Architecture docs MUST be corrected: `service-inventory.json` (`felix-core-digest`) and `data-flows.json` (`observation-digest`) repoint the log path, remove the `#659` `path_retention_note`s, correct the stale `output_path`, and correct the `exec_start` `repos/` discrepancy; markdown views regenerated to match. `updated_by` set to `659`. | Draft |
| FR-007 | Docstrings referencing `~/second-brain/agents/logs/` in `config.py`, `log_action.py`, and `summarize.py` MUST be updated to the canonical path. | Draft |
| FR-008 | Deployment MUST be expressed as a `deploys/queued/NNNN-*.yaml` manifest consumed by felix-deployer, reusing the shared deploy library and the #656 migrator machinery. | Draft |

### Non-Functional Requirements

| ID | Requirement | Threshold / Measure | Status |
|---|---|---|---|
| NFR-001 | Any destructive migration step MUST be gated on a recent Restic backup. | Snapshot age ≤ 24h at gate time (Tier-2). | Draft |
| NFR-002 | The digest subsystem MUST keep running on its existing schedule with no downtime introduced. | No missed 15-minute timer cycle; `felix-core-digest.timer` active post-deploy. | Draft |
| NFR-003 | Zero raw-log data loss during migration. | Post-migration union entry count ≥ union(source, target) pre-migration; verified by count/dedup check. | Draft |
| NFR-004 | The migrator deploy entrypoint MUST survive felix-deployer's shebang/dry-run invocation. | Regression test asserts `+x` bit, `sys.path` shim present, and `--dry-run` exits 0 with no side effects. | Draft |

### Constraints

| ID | Constraint | Status |
|---|---|---|
| C-001 | No change to `felix-core-digest.service` / `.timer` unit files or the 15-minute schedule. | Draft |
| C-002 | The digest **output** directory (already vault-synced at `…/00-System/agent-activity/Agent-Logs/`) MUST remain unchanged. | Draft |
| C-003 | The #490 `tick.py` signal-extraction path and its `/data/services/openclaw/felix-core-digest-signals/` state MUST remain unchanged. | Draft |
| C-004 | Inbox writers/state relocated in #656 MUST remain unchanged. | Draft |
| C-005 | Raw JSONL logs MUST NOT be placed inside the Obsidian-synced `notes/` tree; they stay at `agents/logs` (forensic, high-volume). | Draft |
| C-006 | All office2 changes MUST flow through the `deploys/queued` manifest pipeline; no out-of-band changes on office2. | Draft |
| C-007 | The #557 rebaseline obligation is triggered by the `deploy-pipeline` audited surface; the merge commit MUST record the rebaseline outcome per `security-baseline-ops.md`. | Draft |

## Success Criteria

| ID | Criterion (measurable, outcome-focused) |
|---|---|
| SC-001 | After one post-deploy timer cycle, new raw JSONL exists under `/home/kgale/second-brain/agents/logs/{agent}/` and **zero** new files appear under `/home/claude/second-brain`. |
| SC-002 | All historical raw logs are preserved (union-merge invariant holds; no entry lost). |
| SC-003 | `/home/claude/second-brain` does not exist on office2 and is not recreated within a full 15-minute cycle (`test ! -e`). |
| SC-004 | #656 SC-5's invariant — "no writer targets `/home/claude/second-brain`" — is fully satisfied across both the inbox and observation subsystems. |
| SC-005 | `service-inventory.json`, `data-flows.json`, and their markdown views reflect reality: vault log path, no `#659` retention notes, corrected `output_path` and `exec_start`. |
| SC-006 | Rebaseline recorded on merge; post-change verification passes; no felix-deployer failure ntfy alert. |

## Key Entities

- **felix-core-digest (F014)** — systemd user timer + oneshot service (user `claude`, office2); runs `summarize.py` then `tick.py` every 15 min.
- **Raw agent-activity logs** — per-agent JSONL at `agents/logs/{agent}/YYYY-MM-DD.jsonl`; written by `log_action.py`, read by `summarize.py`.
- **Stray tree** — `/home/claude/second-brain` (to be decommissioned).
- **Vault log dir** — `/home/kgale/second-brain/agents/logs` (backed-up account; sibling of `notes/`).
- **Vault path registry** — `scripts/vault/paths.json` + `scripts/vault/resolver.py`.
- **One-time migrator** — new deploy helper under `scripts/deploy/` (sibling of `migrate-inbox-state-and-logs.py`), reusing its union-merge / snapshot-gate / atomic-copy machinery.
- **Deploy manifest** — `deploys/queued/NNNN-*.yaml` consumed by felix-deployer.

## Assumptions

- The digest output already resolves to the synced vault (`config.py:41`); the arch-doc `output_path` is stale and is corrected here, not a live bug.
- felix-deployer's happy-path auto-rebaseline satisfies the #557 obligation for the `deploy-pipeline` surface; the merge commit records the outcome.
- No systemd unit edit is needed — making the `log_dir` default absolute/registry-resolved removes the `HOME=/home/claude` dependency (keeps the audited-surface footprint to the manifest only).
- The migrator's SOURCE root (`/home/claude/second-brain`) is intentionally hardcoded/parameterized as the stray tree; only the default is repointed in `config.py`.

## Out of Scope

- The inbox state/log relocation and inbox-writer fixes (delivered in #656).
- Making raw JSONL logs Obsidian-synced (intentionally not done — forensic, high-volume).
- The broader #658 fleet-wide runtime-environment-assumption audit (this mission is the concrete observation-digest instance of that class).

## Dependencies

- #656 merged to `main` (merge `c0ffcbb8`) — prerequisite (done).
- Shared deploy library `scripts/deploy/lib/` and the felix-deployer pipeline.
- Reusable #656 migrator `scripts/deploy/migrate-inbox-state-and-logs.py`.
