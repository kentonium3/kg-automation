# WP02 Review Feedback — cycle 1

**Verdict**: REQUEST-CHANGES
**Reviewer**: reviewer-renata (independent)
**Date**: 2026-08-29

The citation work is sound — all five resolve at the claimed paths and lines, the
"defaults to" discipline is honoured, and the managed-status paragraph is correct. Two
major findings, both independently re-verified by the orchestrator before acceptance.

## F1 — MAJOR: worked case A resolves the WRONG way under the ADR's own test

The ADR uses the inbox processor as its office2 exemplar, reasoning that ten unwatched
minutes down means "captures arriving with nowhere to land". **That is false**, and it is
falsifiable against the repo's own docs:

- `service-inventory.json` → `inbox-processing` is an `openclaw-cron`, `risk_tier: 3`,
  running 4x daily. Ten minutes is an order of magnitude shorter than the ~6h inter-tick
  gap, so the outage is indistinguishable from steady state.
- `docs/runbooks/inbox-ops.md:18-24` — mission #746 replaced the lossy path with a
  note-level finalize transaction that is "atomic, fail-loud, and **retry-safe**",
  explicitly closing "the silent-loss class".

Captures land in the vault via Obsidian Sync regardless; processing defers to the next
tick. By the ADR's own test the inbox processor scores **annoyance → office4** — the
opposite of the conclusion drawn. The one example meant to *demonstrate* the load-bearing
idea instead teaches a reader to misapply it, in a document that is immutable once approved.

**Required fix**: replace case A entirely — not patched wording, since the failure is
structural. Use a workload whose ten unwatched minutes destroy something unrecreatable,
and name the mechanism.

**Recommended replacement, verified**: `restic-backup` is `type: cron`, `schedule:
"0 4 * * *"`, `risk_tier: 2`. Plain cron has **no catch-up** — unlike the repo's systemd
timers, which carry `Persistent=true` precisely so they do catch up after downtime
(`felix-vikunja-sync-driver`, `backup-script-drift`). A host down at 04:00 — unwatched by
definition, at 4am — simply skips that night's run. The restore point for that day is gone,
the failure is silent, and it is discovered only when someone needs to restore. That is
data loss, and the contrast with `Persistent=true` makes the mechanism explicit.

## F2 — MAJOR: no `## Alternatives Considered` section

All seven prior ADRs have one (0001 L76, 0002 L222, 0003 L202, 0004 L103, 0005 L136,
0006 L170, 0007 L63), and `docs/design/architecture/adr/README.md:37` names it in the
template: *"Alternatives considered — other options evaluated and why they were not
chosen."* T006 said "match their shape exactly". ADR-0008 goes Consequences → Review-only
affirmations → References.

This matters most here precisely because the ADR's central decision *is* a rejection — a
future author deciding whether to supersede goes looking for exactly this section.

**Required fix**: add `## Alternatives Considered` before `## Consequences`, covering
(a) make office4 a second managed host; (b) run a subset of services on office4 short of
full managed status; (c) leave office4 undocumented.

## F3 — MEDIUM: present-tense claim is not yet true on this lane

The ADR says office4 "is registered in `network-topology.json` and in
`hardware-inventory.json`". True after WP01 merges; false on lane-b today. Expected in a
lane-based mission, but the ADR's correctness now depends on another lane landing.

**Disposition**: no ADR change. WP06 T028 already asserts office4 is present in both files
before the feature branch reaches main, which is the check that protects this sentence.

## F4 — LOW: asymmetric rigor on citation 2

The ADR is scrupulous about `_tick.py` ("defaults to… an override exists at line 404") but
writes citation 2 as the lock "is named" `office2-checkout.lock`. The same structure
exists: `scripts/deploy/lib/deploylock.py:37` defines `ENV_LOCK_PATH =
"DEPLOY_CHECKOUT_LOCK"`, documented as taking "precedence over `DEFAULT_LOCK_PATH`".
Conclusion unchanged, but a document that makes a virtue of not overstating should be
uniform.

**Required fix**: phrase citation 2 as a default that is overridable via
`DEPLOY_CHECKOUT_LOCK`, which nothing in the pipeline sets.

## F5 — LOW: tag `910` has no thread in the document

`tags: [909, 908, 910, 917]` but #910 appears nowhere in the body or References.

**Fix**: add a References entry for #910 (office4 Phase 1 — host baseline and Python
strategy), which is genuine sibling context.

## F6 — NIT: the count `47` will decay

"all 47 entries" is exactly true today and correctly hedged with "today", but an immutable
file ages better with "every entry (47 as of 2026-08-29)".

**Fix**: adopt the dated phrasing.
