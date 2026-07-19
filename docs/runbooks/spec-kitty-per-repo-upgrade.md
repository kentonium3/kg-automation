---
title: Spec-Kitty — Per-Repo Version-Drift Sweep
doc_type: runbook
audience: humans
status: active
last_validated: 2026-07-19
---

# Spec-Kitty — Per-Repo Version-Drift Sweep

Operational checklist for keeping every spec-kitty-initialized repo on the same
template version as the installed CLI. This is the **fleet-sweep** layer; the
per-repo mechanical upgrade steps live in
[`spec-kitty-init-in-existing-repo.md` § 3 Upgrade](spec-kitty-init-in-existing-repo.md#3-upgrade)
and are not duplicated here.

## Why this exists (kentonium3/kg-automation#599)

The global `spec-kitty-cli` binary serves every repo, but each repo's project
state (`.kittify/metadata.yaml` + harness files) is versioned **independently**
and does **not** auto-bump when the CLI does. The CLI's own `--agent-check`
reports `up_to_date` even when a project has drifted. So repos silently fall
behind, and missions then run on stale templates against a newer CLI runtime —
the #597 friction class (protected-branch refusals, split-authority traps, merge
crashes). Before this sweep existed there was **no automatic surfacing** of the
gap; drift was caught only by ad-hoc operator vigilance.

## The drift-check helper (automatic surfacing)

`scripts/spec_kitty/check_version_drift.py` is the deterministic detector. It
discovers standalone kittified repos under a root, reads each recorded
`spec_kitty.version`, compares to the expected (installed-CLI) version, and
reports drift. **Detection only — it never runs `spec-kitty upgrade`.**

```bash
cd /Users/kentgale/repos/kg-automation && python3 -m scripts.spec_kitty.check_version_drift
```

- Default `--repos-root` is the parent of this checkout (`~/repos`); override with
  `--repos-root DIR`.
- Default expected version is parsed from `spec-kitty --version`; override with
  `--expected-version 3.2.6` (useful when pre-staging an upgrade).
- `--json` emits a machine-readable report (for a future trigger to consume).
- **Exit codes:** `0` = no drift, `1` = drift found, `2` = usage/IO error. The
  non-zero-on-drift contract is what lets a scheduler alert on it.

Discovery excludes hidden/scratch dirs (e.g. a `.autopilot-wt` worktree) and
linked git worktrees (`.git` is a file), so the count reflects independent repos.

## The sweep (run after any CLI bump, and periodically)

1. **Detect.** Run the helper. Exit `0` → done, nothing drifted.
2. **Check in-flight-mission safety** for each drifted repo before upgrading — a
   spec-kitty migration applied mid-mission can permanently break that mission's
   accept/merge gates (`feedback_no_mid_feature_upgrades.md`). The authoritative
   signal is an active git worktree:
   ```bash
   for repo in <drifted repos>; do
     d=/Users/kentgale/repos/$repo
     echo "=== $repo ==="; (cd "$d" && git worktree list 2>/dev/null | grep -v "^$d ")
   done
   ```
   Empty output = safe. Do **not** upgrade a repo with an open mission worktree.
3. **Upgrade** each safe, drifted repo per
   [`spec-kitty-init-in-existing-repo.md` § 3.3](spec-kitty-init-in-existing-repo.md#33-roll-the-bump-into-each-repo)
   (`spec-kitty upgrade --project --dry-run`, then `--project --yes`). Mind the
   § 3.4 soft-blockers (SNAPSHOT_DRIFT, dirty `kitty-specs/`).
4. **Re-run the helper** to confirm zero drift (exit `0`).

## Repo inventory (discover live; do not trust a static list)

The fleet grows. The helper discovers it on demand; a snapshot as of 2026-07-19
(expected `3.2.6`):

| Repo | Recorded | Note |
|---|---|---|
| bake-planner, bake-tracker, intentional, kg-automation, metalbox, vikunja-harness | 3.2.6 | current |
| spec-kitty | 3.2.6 | current — the **source** repo; it carries `.kittify/` because it dogfoods, but is **not** an upgrade *consumer*. Never run `upgrade --project` on it. |
| spec-kitty-analyzer | 3.2.3 | drifted; **maintainer carve-out** repo (dogfooded in place) |
| spec-kitty-saas | 3.2.0rc18 | drifted |
| spec-kitty-telescope | 3.2.0rc33 | drifted |
| teamspace-qa-scratch, teamspace-qa-scratch2 | 3.2.3 | drifted; **temporary QA scratch** tenants — may be excluded from the routine |

Membership nuance (which repos the routine should *act* on) is a standing
question — see "Open decision" below.

## Open decision — the always-on trigger (surfaced, not yet built)

#599's acceptance asks for a mechanical trigger that surfaces drift **without
operator action** (within 24h of a CLI bump). That is deliberately **not** shipped
here, because the shape is a genuine design fork with operator-environment
implications:

- The repos live on Kent's **Mac** under `~/repos`, not on office2 — so an office2
  cron cannot see them. Candidate shapes: a **session-start hook**, a **launchd**
  job, a **per-repo CI scheduled job** (would touch carve-out/source repos), or a
  Felix automation with Mac reach.
- Fleet **membership** needs a decision: are the source repo (`spec-kitty`), the
  maintainer carve-out repos (`spec-kitty-analyzer`), and the temporary
  `teamspace-qa-scratch*` tenants in the routine, or excluded?

Until decided, this sweep is **operator-run** (invoke the helper after a CLI bump).
The helper's `--json` + non-zero-on-drift exit is already trigger-ready — a
scheduler need only run it and alert on exit `1`.

## References

- [`spec-kitty-init-in-existing-repo.md`](spec-kitty-init-in-existing-repo.md) — install / init / **per-repo upgrade mechanics** (authoritative).
- `scripts/spec_kitty/check_version_drift.py` — the drift-check helper.
- Memory: `feedback_no_mid_feature_upgrades`, `reference_speckitty_version_history`.
- kentonium3/kg-automation#599 (this routine), #597 (friction exhibit).
