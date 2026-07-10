---
work_package_id: WP04
title: Deploy — manifest + deploy script (venv provision, gates, self-check)
dependencies:
- WP02
- WP03
requirement_refs:
- FR-010
tracker_refs: []
planning_base_branch: feat/felix-calendar-helper
merge_target_branch: feat/felix-calendar-helper
branch_strategy: Planning artifacts for this mission were generated on feat/felix-calendar-helper. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/felix-calendar-helper unless the human explicitly redirects the landing branch.
subtasks:
- T014
- T015
- T016
agent: "claude:opus:reviewer-renata:reviewer"
history: []
agent_profile: implementer-ivan
authoritative_surface: scripts/deploy/deploy-felix-calendar-helper.py
create_intent:
- deploys/queued/felix-calendar-helper.yaml
- scripts/deploy/deploy-felix-calendar-helper.py
- tests/deploy/test_deploy_felix_calendar_helper.py
execution_mode: code_change
mission_id: 01KX4H3C4CZ2W0DRSHZHSNAY53
mission_slug: felix-calendar-helper-01KX4H3C
owned_files:
- deploys/queued/felix-calendar-helper.yaml
- scripts/deploy/deploy-felix-calendar-helper.py
- tests/deploy/test_deploy_felix_calendar_helper.py
role: implementer
tags: []
shell_pid: "64625"
---

# WP04 — Deploy: manifest + deploy script

## ⚡ Do This First: Load Agent Profile

Load `/ad-hoc-profile-load implementer-ivan` (role: implementer) first.

## Branch Strategy
- **Planning/base**: `feat/felix-calendar-helper` · **Merge target**: `feat/felix-calendar-helper`.

## Objective

Ship the helper to office2 through the manifest pipeline. Authoritative:
`../quickstart.md` and `../research.md` D3/D6. **Read first**:
`docs/runbooks/deploy/discipline.md`, `scripts/deploy/lib/README.md`,
`deploys/schema/manifest-v1.schema.json`, and a recent applied manifest
(`deploys/applied/0005-felix-deployer-auto-rebaseline.yaml`) for shape.

Key grounded facts: office2 has **no pip**, only `uv 0.11.2`
(`~/.local/bin/uv`); the helper needs its own venv at
`/data/services/openclaw/felix-calendar/venv` (precedent: doc-auditor,
heartbeat-gate). Creds are **manually** staged (secrets — the script only
verifies presence). Only the `openclaw.json` edit rebaselines (not prompts, not
requirements — deps live in the venv).

## Subtasks

### T014 — `deploys/queued/felix-calendar-helper.yaml`
- `schema_version: v1`, `name: felix-calendar-helper`, `mission_slug: felix-calendar-helper-01KX4H3C`,
  `tier: 3`, `entrypoint: scripts/deploy/deploy-felix-calendar-helper.py`, `audited_surface: true`.
- `verification.pre`: Restic ≤24h (via the entrypoint), helper module present in checkout.
- `verification.post`: run the helper `--self-check --account personal` and assert exit 0.
- Do **not** pre-number the manifest (felix-deployer assigns the applied `NNNN-`). Validate against the schema.

### T015 — `scripts/deploy/deploy-felix-calendar-helper.py`
- Use `scripts/deploy/lib/` primitives. Strict order, halt-on-error:
  1. `snapshot.verify_restic_recent(max_age_hours=24)` (Tier-2 gate; accept an operator `--backup-confirmed` ack path).
  2. Provision venv idempotently: `~/.local/bin/uv venv /data/services/openclaw/felix-calendar/venv --python 3.12`
     then `~/.local/bin/uv pip install --python <venv>/bin/python "google-api-python-client==<pin>" "google-auth==<pin>" "google-auth-oauthlib==<pin>"`
     (pins resolved + recorded in the script; **not** added to requirements.txt).
  3. `verify.verify_file_present` for `~/.config/felix/google/personal/{client_secret,token}.json` (fail with a clear "stage creds first" message).
  4. Post-flight: run the helper `--self-check` via the venv python (cwd=checkout); non-zero → fail the deploy.
- Follow the helper `-m` invocation form; office2 is python3-only. Print recovery instructions on failure (no auto-rollback).

### T016 — Tests (`tests/deploy/test_deploy_felix_calendar_helper.py`)
- Mock subprocess/uv/ssh and the lib primitives. Assert: gate ordering (Restic before venv before creds before self-check);
  halt-on-error at each step; venv provisioning is idempotent (re-run is a no-op / safe); creds-absent → clear failure;
  self-check failure fails the deploy. Manifest validates against the schema (`lib.manifest.validate_manifest_file`).

## Definition of Done
- [ ] Manifest validates against `deploys/schema/manifest-v1.schema.json`; Tier 3, audited_surface true.
- [ ] Deploy script runs the four ordered gates; halts on error; google deps go to the venv (not requirements.txt).
- [ ] `pytest tests/deploy/test_deploy_felix_calendar_helper.py` passes with subprocess/uv mocked.
- [ ] Rebaseline scope documented: only the openclaw.json `skills` edit; prompts unmonitored.

## Risks / reviewer guidance
- Confirm the uv install form (`uv pip install --python <venv>/bin/python`, not `-m uv` inside the venv).
- Confirm the script does NOT copy secrets (manual staging) — it only verifies presence.
- Confirm no google deps leak into `requirements.txt`/`pyproject.toml` (would drift the pip-packages baseline).

## Activity Log

- 2026-07-10T00:08:26Z – claude:opus:implementer-ivan:implementer – shell_pid=62241 – Assigned agent via action command
- 2026-07-10T00:13:46Z – claude:opus:implementer-ivan:implementer – shell_pid=62241 – Ready for review — Tier-3 manifest (schema-valid) + deploy script (Restic->venv->creds->self-check ordered, idempotent, no secret copy, deps venv-only) + tests green.
- 2026-07-10T00:14:40Z – claude:opus:reviewer-renata:reviewer – shell_pid=64625 – Started review via action command
