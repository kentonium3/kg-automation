---
affected_files: []
cycle_number: 2
mission_slug: office4-architecture-registration-01M15RW2
reproduction_command:
reviewed_at: '2026-08-29T04:38:34Z'
reviewer_agent: user
wp_id: WP02
---

# WP02 Review Feedback — cycle 2

**Verdict**: REQUEST-CHANGES
**Reviewer**: reviewer-renata (independent)
**Date**: 2026-08-29

Cycle 1's structural error is fixed — the example now resolves the right way (office2).
F2, F4, F5 confirmed fixed; no regressions; both gates green. Three remaining items, all
independently re-verified.

## F1-R — MAJOR: the "silently / discovered only at restore time" claim is false

ADR line 87-89 says the missed backup costs a restore point "permanently, **silently**, and
the loss is **discovered only when someone needs to restore**."

The factual scaffolding is right (`restic-backup` is `type: cron`, `0 4 * * *`, a *user*
crontab so anacron does not cover it), but the silence claim is the opposite of the truth:

- `restic-backup` declares a `health_check` with `max_age_seconds: 100800` (28 h),
  `state_path: /data/services/backup/state/last-backup.json`, explicitly documented as
  "Freshness-probe semantics (canary registry, FR-007)".
- `scripts/canary/registry.py` includes `cron` in `SERVICE_TYPES`, so restic **is** a canary
  target; `felix-canary` is an active systemd timer running every 15 minutes and maps
  `stale → Severity.ERROR` through the #701 alert bus.
- `docs/runbooks/canary-registry-ops.md` names it as the *first concrete canary*.

Scenario: 04:00 run missed; at ~08:00 the pointer crosses 28 h and the canary raises ERROR.
Detected in about four hours, not at restore time.

**Why this matters beyond a wrong adjective**: as written it redefines the placement test as
being about *undetectability*. The criterion the ADR actually needs is **unrecoverability** —
which is the stronger argument, because it survives the canary.

**Required fix**: keep the example, correct the mechanism. Acknowledge that the canary *will*
notice, and make the point that detection is not recovery — no later run recreates a snapshot
that was never taken, and a human present at 04:10 could not have brought it back either.

## F1-R2 — MEDIUM: `felix-vikunja-sync-driver` is not a valid `Persistent=true` example

`scripts/sync/systemd/felix-vikunja-sync.timer` is `OnUnitInactiveSec=300s`, `OnBootSec=120s`,
`Persistent=true` — with **no `OnCalendar=`**. Per `systemd.timer(5)`, `Persistent=` "only has
an effect on timers configured with `OnCalendar=`". On a purely monotonic timer it is inert.

The unit's own comment block ("If office2 was off when a tick was supposed to fire, run ONE
catch-up tick on resume") is therefore wrong, and `service-inventory.json`'s
`schedule_note: "catch-up on resume"` inherits the same error. The ADR would propagate a
pre-existing repo mistake into an immutable record, where it will be cited.

**Required fix**: drop `felix-vikunja-sync-driver` from the contrast. Use
`credential-health-check` (`OnCalendar=*-*-* 13:00:00`, `Persistent=true`) — verified, and a
daily calendar job is the closest structural analogue to restic. `backup-script-drift`
(`OnCalendar=daily, Persistent=true`) is already correct and stays.

**Separately**: file the underlying repo defect — the timer comment and the
`service-inventory.json` `schedule_note` both promise catch-up behaviour that systemd does
not provide.

## F6 — the cycle-1 dated-count fix was never applied

Line 55 still reads "47 entries in `service-inventory.json` name `host: office2`". The
cycle-1 required fix was the dated phrasing. The replacement silently no-opped — the edit
was applied without an assertion guarding it, unlike the two beside it.

**Required fix**: apply it, and verify the edit landed rather than assuming it did.

## Advisory (accepted, acted on)

The five-subsystem argument now appears three times — the numbered list, the first
Alternatives entry, and "Revisiting this". In a frozen document that is three surfaces that
must agree forever. Trim the Alternatives entry to name the count and point at the list.

## Confirmed fixed in this cycle

- **F2** `## Alternatives Considered` present at 153, before `## Consequences` (176), matching
  0004 and 0006. Three rejected options with genuinely distinct reasoning.
- **F4** `deploylock.py:37` = `ENV_LOCK_PATH = "DEPLOY_CHECKOUT_LOCK"`, documented as taking
  precedence; grep shows it is set **only** in `tests/` (7 `monkeypatch.setenv` sites) —
  nothing in the pipeline sets it. Phrasing now matches citation 3's rigor.
- **F5** #910 present and its gloss is faithful to the real issue title.
- **F3** unchanged by design; WP06 T028 carries it.
- No regressions: both validators green, heading hierarchy clean, links resolve, frontmatter
  still matches siblings, Alternatives does not contradict "Revisiting this".
