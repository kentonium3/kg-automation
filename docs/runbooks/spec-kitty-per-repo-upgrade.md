---
title: Spec-Kitty — Per-Repo Version-Drift Sweep
doc_type: runbook
audience: humans
status: active
last_validated: 2026-08-21
---

# Spec-Kitty — Per-Repo Migration-Bookkeeping Sweep

> **Retitled and rescoped 2026-09-02.** This was "Version-Drift Sweep", built around a helper that
> compared version strings. **That helper has been deleted** and the framing it encoded was wrong:
> a repo's `.kittify/metadata.yaml` stamp is **migration bookkeeping, not build identity**, and
> "same version as the installed CLI" is not a goal — we deliberately run ahead of the last release.
> Canonical build-identification and upgrade procedure now lives in
> `~/repos/spec-kitty-qa/docs/runbooks/spec-kitty-upgrade.md`; read its §0 rules before using this file.

Operational checklist for keeping each spec-kitty-initialized repo's **migration bookkeeping**
current. This is the **fleet-sweep** layer; the per-repo mechanical upgrade steps live in the
canonical runbook above and are not duplicated here.

## Why this exists (kentonium3/kg-automation#599)

The global `spec-kitty-cli` binary serves every repo, but each repo's project
state (`.kittify/metadata.yaml` + harness files) is versioned **independently**
and does **not** auto-bump when the CLI does. The CLI's own `--agent-check`
reports `up_to_date` even when a project has drifted. So repos silently fall
behind, and missions then run on stale templates against a newer CLI runtime —
the #597 friction class (protected-branch refusals, split-authority traps, merge
crashes). Before this sweep existed there was **no automatic surfacing** of the
gap; drift was caught only by ad-hoc operator vigilance.

## The drift-check helper — DELETED 2026-09-02

`scripts/spec_kitty/check_version_drift.py` and its test have been removed.

**Why.** Its entire contract was a semver comparison — recorded `spec_kitty.version` against
`spec-kitty --version` — which identifies nothing. It produced whole-fleet false positives on every
bump (**14/14 repos flagged** on 2026-08-21, expected `3.2.6rc3` vs recorded `3.2.6`, with no repo
having changed), and under two repository lines publishing overlapping numbers its false-positive
rate goes to 100%. A detector documented with a warning that its output is meaningless is worse than
no detector: it trains you to ignore an alert.

**What to do instead.** There are two independent questions and they must not be conflated:

1. **Is the installed CLI behind?** Compare commits, never versions — `spec-kitty-upgrade.md`
   §1 (which build is installed) then §2/§2a (which line, and how far behind its `main`).
2. **Is a repo's migration bookkeeping stuck?** Ask the repo, one at a time:
   ```bash
   spec-kitty upgrade --project --dry-run < /dev/null
   ```
   Cheap, non-mutating, and it answers directly. A repo can also be *stranded* — stamped above every
   migration target that exists, so no build can reach it. That is a bookkeeping state, **not** a
   claim about the CLI; see the canonical runbook's "A repo can be *stranded*" section.

⚠ Upstream **Priivacy-ai/spec-kitty#2617** (build/SHA-aware version reporting) and **#2771**
(Build Identity contract) are the real fixes. Until one lands, there is nothing to automate here.

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
3. **Upgrade** each safe repo whose dry-run reports pending migrations, per
   `~/repos/spec-kitty-qa/docs/runbooks/spec-kitty-upgrade.md` § 4
   (`spec-kitty upgrade --project --dry-run < /dev/null`, then `--project --yes < /dev/null`).
   Mind the soft-blockers there (SNAPSHOT_DRIFT, dirty `kitty-specs/`), and note that
   `< /dev/null` is load-bearing — it makes the mission-state repair auto-decline.
4. **Re-run the dry-run** on each repo to confirm it reports up to date. There is no fleet-wide
   exit code any more, and that is deliberate — see the deleted-helper section above.

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

- `~/repos/spec-kitty-qa/docs/runbooks/spec-kitty-upgrade.md` — **authoritative** for build
  identification (§0/§1/§2a) and per-repo project state (§4). Replaces the retired
  `spec-kitty-init-in-existing-repo.md` (deleted 2026-09-02; recoverable from git history).
- Memory: `feedback_no_mid_feature_upgrades`. (`reference_speckitty_version_history` is a historical
  upgrade log — **not** a build-identification reference.)
- kentonium3/kg-automation#599 (this routine), #597 (friction exhibit).
