---
title: Deploy Discipline (canonical)
doc_type: runbook
audience: agents_and_humans
status: approved
last_updated: '2026-06-12'
---

# Deploy Discipline

## Purpose

Every deploy to office2 flows through this discipline. This runbook is the
canonical reference. Whether a feature ships a new OpenClaw cron job, a Python
helper, a systemd unit, or a config change, the path to office2 is the same:
write a manifest under `deploys/queued/`, write a deploy script that uses the
shared library under `scripts/deploy/lib/`, merge to `main`, and the
`felix-deployer` applier on office2 picks it up within 5 minutes and applies
it under a tier-aware safety gate. There is no other supported deploy path.
The grandfathered per-mission scripts at `scripts/deploy/deploy-{028,149,f013,
f014,f026,felix-admin-calendar,restore-whatsapp-dm-reply-delivery}.sh` remain
in place and continue to work — sibling issue #548 handles their cleanup —
but no new deploy is authored against the old pattern.

---

## The shape

A new deploy is two files committed together:

```
deploys/queued/<slug>.yaml          # manifest — picked up by felix-deployer
scripts/deploy/deploy-<slug>.{sh,py} # entrypoint — uses scripts/deploy/lib/
```

The manifest names the deploy, tier, and entrypoint:

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
    - systemctl --user status foo.service >/dev/null
```

> **⚠️ Verification commands run on office2, not on Mac.** Felix-deployer (the
> applier) runs as a systemd user timer on office2, and every `verification.pre`
> and `verification.post` command is executed in that context. Two consequences:
>
> 1. **Never wrap a verification command in `ssh office2-claude '…'`** — the
>    `office2-claude` host alias is defined in **Mac's** `~/.ssh/config`, not in
>    office2's. Loopback SSH from office2 to itself fails with
>    `Could not resolve hostname office2-claude`. Use the command locally.
> 2. **The bootstrap manifest at `deploys/applied/0002-bootstrap-felix-deployer-v2.yaml`
>    uses `ssh office2-claude '…'` in its verification block.** That was correct
>    for the one-off operator-run bootstrap (which executed from Mac), and that
>    file is **bootstrap-only** — its verification block is **not safe to copy**
>    for routine queued deploys. See `kentonium3/kg-automation#612`.
>
> When in doubt: copy the verification pattern from a recent
> `deploys/applied/<NNNN>-*.yaml` whose manifest has `apply_mode: manifest`
> (not `apply_mode: bootstrap`).

The full manifest schema lives at `deploys/schema/manifest-v1.schema.json` —
that file is authoritative. CI rejects any manifest that does not validate.

The entrypoint script MUST support two modes:

- `--dry-run` — print what would happen; no side effects on office2.
- `--apply` — execute.

Both modes use the deploy library for cron, snapshot, and verification
primitives. Direct system crontab access is forbidden and CI-enforced via a
static check on `scripts/deploy/lib/` itself.

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
  echo "would: edit openclaw cron foo-job to schedule '0 6 * * 1'"
  exit 0
fi

# Apply: copy file
rsync ... office2-claude:...

# Apply: edit cron (positional args: name, schedule, tz)
python3 -m scripts.deploy.lib.cron openclaw_cron_edit foo-job "0 6 * * 1" "America/New_York"
```

Choose Python for complex orchestration with multiple primitives (import
`scripts.deploy.lib` directly); choose bash for simple file-copy or systemd
unit installs (use `python3 -m scripts.deploy.lib.<module>` for cron, verify,
and snapshot primitives).

Worked example (Python entrypoint, subprocesses openclaw directly — pattern
used by `scripts/deploy/reschedule-felix-admin-habits-weekly-cron.py` and
`scripts/deploy/restore-tz-on-habits-weekly-report-cron.py`):

```python
#!/usr/bin/env python3
"""Deploy entrypoint — short description of what this changes."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

# Required only when importing from scripts.deploy.lib.*. felix-deployer
# invokes the entrypoint by path (not via `python3 -m`), so the repo root
# isn't on sys.path unless we put it there.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _dry_run() -> int:
    print("DRY-RUN: would …")
    return 0


def _apply() -> int:
    proc = subprocess.run(
        ["openclaw", "cron", "edit", "<uuid>", "--cron", "0 6 * * 1", "--tz", "America/New_York"],
        capture_output=True, text=True, check=False,
    )
    print(f"APPLY: rc={proc.returncode}")
    return 0 if proc.returncode == 0 else 1


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1 or args[0] not in ("--dry-run", "--apply"):
        sys.stderr.write("usage: <entrypoint> --dry-run|--apply\n")
        return 2
    return _dry_run() if args[0] == "--dry-run" else _apply()


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
```

### Python entrypoint authoring checklist

When the entrypoint is a Python file (`scripts/deploy/<slug>.py`):

1. **Shebang**: file starts with `#!/usr/bin/env python3`.
2. **Exec bit**: committed with mode `0755` (`chmod +x <file>` BEFORE
   `git add`). felix-deployer invokes the entrypoint as
   `subprocess.run([path, "--dry-run"], shell=False)` — a direct exec.
   Without the exec bit this errors out as `Permission denied` (exit
   126) at the `entrypoint_dry_run` phase.
3. **sys.path shim**: if you `from scripts.deploy.lib import ...`, add
   `sys.path.insert(0, str(Path(__file__).resolve().parents[2]))` near
   the top of the file. felix-deployer invokes entrypoints by path,
   NOT via `python3 -m`, so the `scripts` package isn't on `sys.path`
   without help.
4. **Argv dispatch**: `main()` parses `sys.argv[1:]` for `--dry-run`
   (no side effects on office2 — read-only lookups OK) and `--apply`
   (execute). Anything else returns exit 2 with a usage string on stderr.
5. **Dry-run as scout**: in the dry-run path, perform the read-only
   lookups your apply will need (e.g. resolve a cron UUID via
   `openclaw cron list --json`). Misconfiguration surfaces before the
   live apply tick rather than at `entrypoint_apply` time.

### Manifest verification-command pitfalls

`verification.pre` and `verification.post` are shell strings executed
by felix-deployer **on office2** under `shell=True`. Common foot-guns:

1. **Never wrap in `ssh office2-claude '…'`**. The `office2-claude`
   alias is defined in **Mac's** `~/.ssh/config`, not on office2. The
   bootstrap manifest at `deploys/applied/0002-bootstrap-felix-deployer-v2.yaml`
   uses the alias because it was operator-run from Mac; copying that
   pattern for routine queued deploys produces `Could not resolve
   hostname office2-claude`. See kg-automation#612.
2. **`openclaw cron list --json` returns `{"jobs": [...], "total": ...}`**,
   not a bare array. Index `["jobs"]` first.
3. **A cron's `schedule` field is an object**: `{"kind": "cron",
   "expr": "0 6 * * 1", "tz": "America/New_York"}`. Compare
   `m["schedule"]["expr"]` for the cron string and
   `m["schedule"].get("tz")` for the timezone — not `m["schedule"]`
   itself.
4. **No `\"` inside f-string `{}` expressions**. Python rejects the
   f-string at compile time with `SyntaxError: unexpected character
   after line continuation character`. Hoist the value to a local
   name first:
   ```python
   expr = m["schedule"]["expr"]
   assert expr == "0 6 * * 1", f"schedule still {expr!r}"
   ```
5. **If you edited an openclaw cron, verify BOTH `expr` and `tz`**.
   `openclaw cron edit <id> --cron <expr>` (without `--tz`) silently
   resets the cron's timezone to UTC. A schedule-only post-check
   passes and the cron then fires at the wrong wall clock. See
   kg-automation#614.
6. **Bug-class aware**: prefer subprocessing `openclaw` directly over
   `python3 -m scripts.deploy.lib.cron …` until kg-automation#613
   (cron.py CLI-shadow defect) is verified fixed in your checkout.

---

## The library

`scripts/deploy/lib/` is the shared primitive layer that all deploy scripts
build on. Full module-by-module API lives in
[`scripts/deploy/lib/README.md`](../../../scripts/deploy/lib/README.md).

One-line summary per module:

- `cron` — OpenClaw cron management (`openclaw_cron_list`,
  `openclaw_cron_edit`, `openclaw_cron_add`). Never touches the system
  crontab — that path is closed and CI-enforced.
- `snapshot` — Restic backup recency check
  (`verify_restic_recent --max-age-hours <N>`); the canonical Tier 2 gate.
- `verify` — file-presence, executability, and content checks for both
  pre-flight (source exists locally) and post-flight (artifact landed on
  office2) verification.
- `tier_guard` — tier classification and gating helpers used by
  `lib.apply.dry_run_then_apply_gate`; rejects Tier 0 deploys at runtime.
- `apply` — the orchestrator. `dry_run_then_apply_gate(manifest,
  manifest_path)` is the function the applier calls. It enforces the tier
  guard, runs `verification.pre`, calls the entrypoint with `--dry-run`,
  then `--apply`, then runs `verification.post`. Each phase halts on
  failure.

Use the library — do not reimplement these primitives in a deploy script.
That is what catches regressions and lets future deploys share safety
improvements.

---

## The applier

`scripts/deploy/felix-deployer/` is the office2-side applier. It is a
systemd user timer that fires every 5 minutes.

- **Service**: `felix-deployer.service` (oneshot, triggered by the timer).
- **Timer**: `felix-deployer.timer` (every 5 minutes, persistent).
- **Status**: `ssh office2-claude 'systemctl --user status felix-deployer.timer'`
  for the timer; `ssh office2-claude 'systemctl --user status felix-deployer.service'`
  for the most recent run.
- **Log location**: `/data/services/felix-deployer/logs/<YYYY-MM-DD>.jsonl`
  — one structured event per applier tick, with manifest discovery,
  tier-guard outcome, dry-run output, apply output, verification outcomes,
  and the final disposition (applied / failed / skipped).
- **Tick log on quiet days**: when there are no manifests in
  `deploys/queued/`, the tick still emits a single "scanned, nothing to do"
  event so the log is a continuous liveness signal.

The applier flow on each tick:

1. `git pull` on office2 against `main`.
2. Scan `deploys/queued/` — find any new manifests.
3. For each manifest, call `lib.apply.dry_run_then_apply_gate(manifest, manifest_path)`:
   - Tier guard (Tier 0 → reject, leave in queue, alert).
   - Restic recency check (if `tier: 2`).
   - `verification.pre` commands.
   - `<entrypoint> --dry-run`.
   - `<entrypoint> --apply`.
   - `verification.post` commands.
4. On success: write `deploys/applied/<NNNN>-<slug>.yaml` with
   `apply_mode: manifest`, `applied_at: <ts>`. Commit + push. Remove the
   manifest from `deploys/queued/`.
5. On failure: write `deploys/failed/<slug>-<ts>.yaml` with the failure
   phase and a redacted error summary. Commit + push. Leave the manifest
   in `deploys/queued/`. Dispatch a WhatsApp DM to the operator via
   openclaw. **No auto-retry on the next tick** — the failure record
   blocks the manifest until either the script is fixed (next tick
   re-attempts automatically) or the manifest is deleted from the queue.

The applier is itself deployed via the bootstrap script — see the
**Bootstrap** section below.

---

## Tier policy

The five-tier risk taxonomy at
`docs/design/architecture/data/change-risk-taxonomy.json` governs every
change to kg-automation. The manifest discipline mirrors it:

| Tier | Policy in the manifest discipline |
|---|---|
| **Tier 0 — Hard Lock** | **Never executed via the pipeline.** Tier 0 deploys remain manual via `ssh office2-kgale`. The applier rejects any manifest with `tier: 0` at the tier guard. |
| **Tier 1 — Verification Required** | Must include a `verification:` block with both `pre:` and `post:` commands proving connectivity / interface health. The applier runs both. |
| **Tier 2 — Snapshot Required** | Must include a `verification:` block. The applier additionally invokes `lib.snapshot.verify_restic_recent --max-age-hours 24` before the dry-run regardless of what the manifest declares. |
| **Tier 3 — Standard** | Manifest + entrypoint script only. No mandatory `verification:` block (though `pre:` / `post:` commands are still encouraged where they catch real failures cheaply). |
| **Tier 4 — Auto-Commit** | Manifest + entrypoint script only. Lightest path; suited to schema / metadata changes that touch deployed surfaces. |

When uncertain between two tiers, choose the higher one. The cost of an
extra verification step is small; the cost of skipping one is a silent
broken deploy.

---

## Failure handling

When a deploy fails, the applier:

1. Writes the failure record to `deploys/failed/<slug>-<ts>.yaml`. The
   record names the manifest, tier, failure phase
   (`tier_guard` / `verification_pre` / `dry_run` / `apply` /
   `verification_post`), and a redacted error summary (stack-trace tail,
   non-zero exit code, command that failed).
2. Commits and pushes the failure record to `main`.
3. Leaves the manifest in `deploys/queued/`.
4. Dispatches a WhatsApp DM to the operator via openclaw, naming the
   manifest, tier, failure phase, and a short summary.

**Operator (or agent) response options:**

- **Fix the deploy script in a follow-up PR.** Push the fix to `main`. The
  next applier tick automatically re-attempts the manifest. No state needs
  to be cleared.
- **Cancel the deploy.** Delete the manifest from `deploys/queued/` and
  push. The next tick will skip it because there's nothing to find.
- **Cancel the manifest but keep the script.** Useful if the script needs
  to wait for another precondition. Same path — delete the manifest, push,
  re-file the manifest later.

There is no manual "retry" button. The pipeline is pull-based and
deterministic: a manifest in the queue is a standing instruction to
attempt the deploy on every applier tick until it succeeds or is
explicitly cancelled.

---

## Bootstrap

The applier itself is deployed via the canonical bootstrap script at
`scripts/deploy/deploy-felix-deployer-bootstrap.sh`. That script installs
the felix-deployer systemd user units on office2 and starts the timer.

It exists as a reference example of a deploy script in the manifest
discipline shape — read it before authoring a new deploy script. It is
**not** for general use; it is invoked exactly once to bring the applier
online, and the applier handles every subsequent deploy on the system.

---

## Rebaseline obligation (FR-018)

Independent of the tier above, any deploy that touches an **audited
surface** triggers the rebaseline obligation described in the project
charter and in [`docs/runbooks/security-baseline-ops.md`](<../security-baseline-ops.md>).

Audited surfaces (per `docs/design/architecture/data/audited-surfaces.json`):

- OpenClaw agent prompts.
- OpenClaw config.
- Systemd user units and deploy scripts.
- Python dependency manifests.
- Docker stack files.
- Committed SSH key material.

When a manifest has `audited_surface: true`, the merge commit that brought
the manifest in (or the post-merge follow-up) MUST record one of:

- `Rebaseline: completed at <ISO-8601 UTC>` (with verification output if
  practical), OR
- `Rebaseline: not required — <one-line justification>` if the
  `audited_surface: true` flag turned out to be conservative.

The operator runs the reset command on office2 — neither the applier nor
CI runs it. Canonical command lives in
[`docs/runbooks/security-baseline-ops.md`](<../security-baseline-ops.md>).

If the manifest declared `audited_surface: false` but the deploy turned
out to touch an audited surface, fix the manifest in a follow-up PR
(`audited_surface: true`) and record the rebaseline in the follow-up
commit.

---

## Reference index

The discipline is anchored across these surfaces. If any one drifts,
the others should be checked.

| Surface | Role |
|---|---|
| **Project charter — Deployment Constraints rule** | The doctrinal anchor. Loaded via `spec-kitty charter context` on every mission action. Source: `.kittify/charter/charter.md`. |
| **`docs/runbooks/deploy/discipline.md`** | This runbook. The canonical operational reference. |
| **`docs/runbooks/deployment.md`** | Forwarding page that points here for any new question; preserves grandfathered-script structural info. |
| **`scripts/deploy/lib/README.md`** | Library API reference. Module-by-module surface area, function signatures, examples. |
| **`deploys/schema/manifest-v1.schema.json`** | Authoritative manifest schema. CI rejects any manifest that does not validate against this file. |
| **`docs/design/architecture/data/signal-to-doc-map.json`** | Deploy-related change classes (`systemd-unit-added-or-modified`, `service-added-or-modified`, etc.) point spec/plan agents at this runbook and the library README. |
| **`CLAUDE.md` "Deploys to office2" section** | Top-of-session doctrinal pointer for any Claude Code session. |
| **`.github/ISSUE_TEMPLATE/feature.md` — Deploy required?** | Issue-creation-time prompt for new feature work. |
| **`.github/ISSUE_TEMPLATE/infra.md` — Deploy required?** | Issue-creation-time prompt for new infra work. |
| **`scripts/deploy/felix-deployer/`** | The office2-side applier itself. |
| **`scripts/deploy/deploy-felix-deployer-bootstrap.sh`** | Reference example deploy script; also the path that brings the applier online. |
| **Mission contracts** | This mission's contracts under `kitty-specs/pull-based-deploy-pipeline-01KTYQQS/contracts/` formalize the manifest, applier, and library interfaces. |

For the user-facing walkthrough of writing a new deploy, see the mission's
quickstart at
`kitty-specs/pull-based-deploy-pipeline-01KTYQQS/quickstart.md`.
