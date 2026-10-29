---
id: spec-kitty-per-repo-upgrade
doc_type: runbook
title: Spec-Kitty Per-Repo Upgrade (DEPRECATED — pointer)
status: deprecated
level: reference
owners: [kent]
last_validated: 2026-09-28
version: 2.0.0
---

# Spec-Kitty Per-Repo Upgrade — DEPRECATED

⛔ **This copy is retired. Do not follow it. Do not restore it from history.**

**The entire procedure — build identification, install, per-repo project state, the fleet sweep,
abort conditions — lives in ONE canonical document:**

> `~/repos/spec-kitty-qa/docs/runbooks/spec-kitty-upgrade.md`

The fleet-sweep content that used to live here is now **§4a** of that document.

## Why this was retired (2026-09-28)

This file had **no `version:` field**, so its staleness was invisible, and it was last validated
**2026-08-21** while the canonical runbook advanced to v1.5.

⭐ **The reason for folding it in, rather than leaving two documents:** it **restated the
build-identity rule independently** — that `spec-kitty --version` identifies nothing and that a
repo's `.kittify/metadata.yaml` stamp is migration bookkeeping rather than build identity.
**Two statements of one rule in two repos is how a rule drifts**, and this is the rule that has
needed correcting mid-task most often.

**It also carried a claim that is now false:** that `< /dev/null` makes the mission-state repair
auto-decline. Measured on build `894f7cb9d` on 2026-09-28, `upgrade --project --yes < /dev/null`
**ran the repair** and rewrote a merged mission's event log. See §4 of the canonical runbook.

## The rule this file exists to stop anyone re-deriving

> **Identify a build by its SHA and provenance — line, SHA, how it got here. Never by a version
> string.** Two installs both reporting `3.2.6rc2` were 323 commits apart. On 2026-09-28 an
> upgrade moved `619bd1137 → 894f7cb9d`, **898 commits**, with the version string unchanged at
> `4.0.0rc5`.

**Keep one canonical source. Point at it. Never fork it.**
