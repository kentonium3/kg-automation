# Quickstart: Adding a New Deploy

**Mission**: `pull-based-deploy-pipeline-01KTYQQS`
**Audience**: a coding agent (or operator) writing a plan for a new feature/infra issue that needs to deploy something to office2.

This walkthrough captures the canonical pattern *after* this mission merges. Before that, follow the interim guidance in the issue body — use a thin `scripts/deploy/deploy-{slug}.sh` wrapper as today.

---

## TL;DR

1. Write the deploy script: `scripts/deploy/deploy-<slug>.<sh|py>` — use the library at `scripts/deploy/lib/`.
2. Write the manifest: `deploys/queued/<slug>.yaml` — schema in `deploys/schema/manifest-v1.schema.json`.
3. PR both files together. CI validates the manifest schema and tier policy.
4. On merge, the felix-deployer applier on office2 picks up the manifest within 5 min and applies it.
5. Success → manifest moves to `deploys/applied/<NNNN>-<slug>.yaml`.
6. Failure → record at `deploys/failed/<slug>-<ts>.yaml`, WhatsApp DM to operator, manifest stays in queue.

---

## Step-by-step

### 1. Write the deploy entrypoint

Choose the appropriate language:
- **Bash** for simple file-copy or systemd unit installs (use `python3 -m scripts.deploy.lib.<module>` for any cron / verify / snapshot operation).
- **Python** for complex orchestration with multiple primitives (import `scripts.deploy.lib` directly).

Either way, the script MUST support two modes:
- `--dry-run` — print what would happen; no side effects on office2.
- `--apply` — execute.

Both modes use the deploy library for cron, snapshot, and verification primitives. Direct system crontab access is forbidden and CI-enforced.

Worked example (bash):

```bash
#!/usr/bin/env bash
set -euo pipefail
MODE="${1:-}"
case "$MODE" in
  --dry-run|--apply) ;;
  *) echo "usage: $0 --dry-run|--apply" >&2; exit 2 ;;
esac

# Pre-flight: confirm the source file exists locally
python3 -m scripts.deploy.lib.verify verify_file_present scripts/foo/bar.py
# Pre-flight: confirm openclaw cron is healthy
python3 -m scripts.deploy.lib.cron openclaw_cron_list >/dev/null

if [ "$MODE" = "--dry-run" ]; then
  echo "would: rsync scripts/foo/bar.py → office2:/home/claude/.../bar.py"
  echo "would: edit openclaw cron foo-job to point at new payload"
  exit 0
fi

# Apply: copy file
rsync ... office2-claude:...

# Apply: edit cron
python3 -m scripts.deploy.lib.cron openclaw_cron_edit foo-job --payload-file ...
```

### 2. Write the manifest

Filename: `deploys/queued/<slug>.yaml`. The slug should match (or be a clear extension of) your script's slug.

Minimal example:

```yaml
schema_version: v1
name: foo-config-bump-2026-06-15
mission_slug: foo-config-bump-mvp-01XXXXXX     # or: issue: kentonium3/kg-automation#NNN
tier: 3
entrypoint: scripts/deploy/deploy-foo-config-bump.sh
audited_surface: false
created_at: "2026-06-15T12:00:00Z"
created_by: claude-code-agent
notes: |
  Updates the foo service's threshold from 5 to 10 per #NNN.
```

For Tier 1 or Tier 2 changes, include a `verification` block:

```yaml
tier: 2
audited_surface: true
verification:
  pre:
    - python3 -m scripts.deploy.lib.snapshot verify_restic_recent --max-age-hours 24
  post:
    - python3 -m scripts.deploy.lib.verify verify_file_present /home/claude/.../bar.py --executable
    - ssh office2-claude 'systemctl --user status foo.service' >/dev/null
```

### 3. PR and merge

PR both files together (deploy script + manifest). CI runs:
- Schema validation against `deploys/schema/manifest-v1.schema.json`.
- Tier guard (Tier 0 rejected).
- Doctrinal cross-link check (catches incidental damage to discipline docs).
- Static check: `crontab` literal must not appear in `scripts/deploy/lib/`.

When CI passes and the PR merges:

### 4. The applier picks it up

Within 5 minutes of merge, the felix-deployer systemd timer fires:

1. `git pull` on office2.
2. Scan `deploys/queued/` — find your new manifest.
3. Run `lib.apply.dry_run_then_apply_gate(manifest, manifest_path)`:
   - Tier guard (re-check).
   - Restic recency (if tier==2).
   - `verification.pre` commands.
   - `<entrypoint> --dry-run`.
   - `<entrypoint> --apply`.
   - `verification.post` commands.
4. On success: write `deploys/applied/<NNNN>-<slug>.yaml` with `apply_mode: manifest`, `applied_at: <ts>`. Commit + push.
5. On failure: write `deploys/failed/<slug>-<ts>.yaml`, dispatch WhatsApp DM via openclaw, leave manifest in queue. No auto-retry.

### 5. What the operator (or you) does on failure

1. Read the WhatsApp DM — it names the manifest, tier, failure phase, and a redacted error summary.
2. Read the full failure record at `deploys/failed/<slug>-<ts>.yaml` in the repo (the applier pushes it).
3. Either:
   - Fix the deploy script in a follow-up PR — the next applier tick re-attempts automatically.
   - Delete the manifest from `deploys/queued/` to cancel.

---

## What this discipline replaces

This pattern replaces the per-mission one-shot wrappers in `scripts/deploy/deploy-{028,149,f013,f014,f026,...}.sh`. Those scripts remain in place and continue to work — they are grandfathered and not modified by this mission. Sibling issue #548 handles their cleanup.

For **any new deploy after this mission merges**, use the manifest discipline. The interim guidance to write a thin per-feature wrapper is retired.

---

## How an agent discovers this

A spec-kitty specify/plan agent working on a new feature reaches this discipline by:

- Reading `kg-automation/CLAUDE.md` at session start — the "Deploys to office2" section points here.
- Consulting `docs/design/architecture/data/signal-to-doc-map.json` when an issue's architecture-impact section names a deploy-related change class — the doc_targets point here.
- Reading the project charter Deployment Constraints rule (loaded via `spec-kitty charter context`) — the rule references this.
- Reading the feature/infra issue template's "Deploy required?" prompt — it links here.

If you are an agent reading this, the discipline is: **manifest in `deploys/queued/`, script in `scripts/deploy/`, library at `scripts/deploy/lib/`. No system crontab. Tier 0 is manual.**
