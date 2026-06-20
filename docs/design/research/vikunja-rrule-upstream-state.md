---
id: research-vikunja-rrule-upstream-state
doc_type: research
title: Vikunja RRULE upstream state
status: draft
level: research
owners: [kent]
last_validated: 2026-05-16
version: 1.0
---

# Vikunja RRULE upstream state

Research-only assessment of whether RRULE support is a live, stalled, or
closed conversation in the Vikunja project, and what advocacy leverage (if
any) is available to a non-developer user. Facts and quotes are cited
inline; no strategy is proposed.

## Executive summary

- RRULE is unambiguously a **live conversation**, not a closed one. The
  upstream maintainer (kolaente) personally asked a contributor to switch
  approaches mid-PR specifically so the project could land RFC 5545 RRULE
  support, and pointed him at the same library Kent identified
  (`teambition/rrule-go`).
- A concrete, near-complete PR exists: **PR #2032** ("feat(repeat):
  migrate from legacy repeat fields to RFC 5545 RRULE") by
  IAMSamuelRodda, opened 2025-12-29, last activity 2026-05-15. It
  currently sits in `CHANGES_REQUESTED` / `mergeStateStatus: BLOCKED`
  state but is being actively iterated — the contributor responded to
  review comments on 2026-04-28, and another community user pinged
  kolaente for a re-review on 2026-05-15.
- The 1.0 release timing was the primary reason kolaente paused review.
  Quote (2026-01-08): *"This is quite a large feature, I'd like to get it
  right and right now we're pretty close to the 1.0 release."*
- The Vikunja repo even maintains a **dedicated label** —
  `area/recurring-tasks` with the description *"Repeat rules, recurring
  task behavior, RRULE"* — applied across 16 issues/PRs in this domain.
  That signals the project considers RRULE a tracked area of work, not a
  fringe request.
- The teambition/rrule-go library is **MIT-licensed** (compatible with
  Vikunja's AGPL-3.0), implements the full python-dateutil port of
  RFC 2445/5545 RRULE, but its upstream is **largely dormant** — last
  commit 2024-08-15, 371 stars, 7 open issues including known timezone
  and DST bugs.

In short: this is the *opposite* of a closed conversation. There is a
mergeable RRULE PR with maintainer engagement, and the bottleneck is
review/iteration bandwidth, not philosophical opposition.

## Issue and PR survey

| # | Type | Title | State | Created | Last update | Comments | +1 / reactions |
|---|---|---|---|---|---|---|---|
| [#2032](https://github.com/go-vikunja/vikunja/pull/2032) | PR | feat(repeat): migrate from legacy repeat fields to RFC 5545 RRULE | Open, BLOCKED | 2025-12-29 | 2026-05-15 | 7 + 19 reviews | 4 thumbs-up on a single re-ping comment |
| [#2029](https://github.com/go-vikunja/vikunja/pull/2029) | PR | feat(repeat): add more precise recurrence settings | Closed (superseded by 2032) | 2025-12-28 | 2025-12-29 | 3 | 1 |
| [#1369](https://github.com/go-vikunja/vikunja/issues/1369) | Issue | More precise settings for the recurrence of a task | Open (parent of #2032) | 2025-09-01 | 2026-04-11 | 4 | 8 thumbs-up |
| [#2234](https://github.com/go-vikunja/vikunja/issues/2234) | Issue | Enhancements to recurring events | Open | 2026-02-14 | 2026-04-11 | 1 | 0 |
| [#1872](https://github.com/go-vikunja/vikunja/issues/1872) | Issue | Configurable behaviour for repeat tasks | Open | 2025-11-25 | 2026-04-11 | 1 | 5 thumbs-up |
| [#2203](https://github.com/go-vikunja/vikunja/issues/2203) | Issue | Adding cron parsing for repeating intervals (alt approach) | Open | 2026-02-08 | 2026-04-11 | 2 | 0 |
| [#543](https://github.com/go-vikunja/vikunja/issues/543) | Issue | CalDAV — sync repeat tasks (legacy, originally 2023) | Open | 2025-04-01 (migrated) | 2026-04-23 | 2 | 4 thumbs-up on user complaint |
| [#898](https://github.com/go-vikunja/vikunja/issues/898) | Issue | Repeat tasks not resetting progress | Open | 2025-06-08 | 2026-04-11 | 2 | 4 thumbs-up |
| [#748](https://github.com/go-vikunja/vikunja/pull/748) | PR | Enable iOS CalDAV support for recurring tasks (partial RRULE write fix) | Closed, cherry-picked | 2025-05-09 | 2025-12-13 | 7 | — |

**Synthesis.** The "recurring-tasks" cluster currently has roughly 11
open issues and 1 active open PR. Activity has been **accelerating**
through 2025-2026, with the dedicated label rolled out and a maintainer
explicitly directing contributor work toward the RRULE path. The pattern
is not "we get one request a year"; it is "the maintainer has a clear
target architecture (RRULE) but a single active contributor has stalled
twice."

The pattern of failed attempts is informative. PR #2029 was opened by
IAMSamuelRodda with a narrower "more precise recurrence" approach;
kolaente *redirected him within hours* to RRULE specifically. The
contributor reworked the PR overnight, reopened it as #2032, received a
substantive light review on 2026-01-08, then a `CHANGES_REQUESTED` review
on 2026-02-17, and went silent for ~10 weeks before responding to the
review comments on 2026-04-28. Kolaente's most recent action on the PR
was the February changes-requested review; there is no May response yet.

There is also a much older, pre-GitHub attempt referenced by kolaente in
PR #2029: a gist at `gist.github.com/kolaente/c6dc60bb1e1952d02edbaed6d81f645c`
showing a previous diff that was attempted "before we moved to github."
That historical attempt is documented but did not land.

## Maintainer sentiment

Kolaente's sentiment toward RRULE is **explicitly supportive**. Direct
quotes:

On PR #2029, redirecting the contributor's approach (2025-12-28):

> "To make this more flexible once and for all, please change the
> approach here to implement RRULE (the format that caldav uses).
> There's a Go library that does the parsing:
> https://github.com/teambition/rrule-go [...] The advantage of this
> approach is that it will allow for all kinds of recurring schedule
> (like once on the first tuesday of the month but only on every other
> month) that we would need to build separately if we continue the
> current route."

On PR #2032 first review (2026-01-08):

> "Hey thanks for the PR! I've only done a light review now, will take
> another look at this after the 1.0 release (early February). This is
> quite a large feature, I'd like to get it right and right now we're
> pretty close to the 1.0 release."

On the alternative cron proposal (#2203, 2026-02-08):

> "Really unsure about this because cron is not very accessible to
> non-it people. And there is
> https://github.com/go-vikunja/vikunja/pull/2032 which will likely
> clash."

On issue #1369 when asked about sponsorship (2025-09-05):

> "Happy to take donations for it. I estimate this to be ~5h of work, at
> my current hourly rate that would be 600 € to sponsor the whole thing.
> It will probably happen anyway at some point, just not a priority
> right now."

On issue #2234 (2026-02-14), succinctly:

> "This will be fixed by https://github.com/go-vikunja/vikunja/pull/2032"

There are no maintainer comments anywhere expressing reluctance, scope
concerns, or "this is the wrong abstraction" pushback toward RRULE. The
consistent message is: RRULE is the target; the blockers are
review-bandwidth and the contributor finishing the iteration loop.

## The teambition/rrule-go package

- **Repository:** https://github.com/teambition/rrule-go
- **License:** MIT — fully compatible with Vikunja's AGPL-3.0.
- **Stars / activity:** 371 stars, 66 forks; **last commit
  2024-08-15** (about 21 months stale at time of writing). 7 open
  issues, 0 of which the maintainer has triaged recently.
- **Spec coverage:** README claims *"a complete implementation of the
  recurrence rules documented in the iCalendar RFC"* (RFC 2445,
  superseded by RFC 5545). It is a port of python-dateutil's `rrule`
  module, which is the de-facto reference RRULE implementation.
  Supports `RRule`, `RRuleSet`, `RDATE`, `EXDATE`, all `BY*` clauses,
  `BYSETPOS`, `BYDAY`, `BYMONTHDAY`, `BYWEEKNO`, `COUNT`, `UNTIL`,
  `INTERVAL`. README example shows the "every four years, first Tuesday
  after a Monday in November" pattern (US presidential election day),
  which is among the more pathological RRULE cases.
- **Known caveats** (from open issues):
  - #67, #68: `UNTIL` is always interpreted as UTC; timezone handling
    around `UNTIL` + `DTSTART` is broken.
  - #66, #63: DST transitions cause invalid timestamps for `HOURLY`
    intervals.
  - #69: `BYHOUR` / `BYMINUTE` order interaction with `BYSETPOS`.
  - The library has stalled bug reports going back to 2023 with no
    maintainer response.
- **Cross-reference with PR #2032:** the PR body explicitly cites
  `teambition/rrule-go` as the chosen library, and the contributor
  reports adding RRULE validation via the library on save. So library
  fitness is no longer a hypothetical — it is committed code awaiting
  re-review.

**Net read:** the library is functionally sufficient for Vikunja's
current scope (daily / weekly / monthly / yearly with BYDAY / BYMONTHDAY
patterns) but carries inherited DST / timezone debt. Vikunja's
maintainer has already accepted this trade-off implicitly by directing
the contributor to use it.

## Advocacy entry points (ordered by leverage)

A non-developer advocating for RRULE has these concrete moves available,
roughly highest leverage first:

1. **PR #2032 — comment requesting re-review.** This is the single
   highest-leverage spot. A community user already did this on 2026-05-15
   ("`kolaente can you take a new look at this PR? Thanks!`") with no
   maintainer response yet. A second voice pinging in support — ideally
   referencing concrete CalDAV / weekly-recurrence use cases — would
   reinforce the signal that this PR has user demand behind it.
2. **PR #2032 — thumbs-up reactions on the contributor's commitment
   comments.** The "I'll get this sorted tonight" comment from
   IAMSamuelRodda on 2026-04-28 already has 3 hearts. Stronger reaction
   density signals the PR is socially watched.
3. **Issue #1369 — already at 8 thumbs-up.** This is the parent issue
   that PR #2032 closes. Adding a reaction here is cheap. Kolaente's
   sponsorship offer ("600 € to sponsor the whole thing") on this issue
   is the most explicit monetary lever available — if Kent valued the
   feature at that price, the maintainer has stated he would prioritize
   it.
4. **Issue #543 — CalDAV sync.** Already drawing one strong frustration
   comment (EpsilonAlpha, 2026-04-23) and 4 thumbs-up reactions on the
   "What's the status?" comment. This issue ties the missing yearly
   repetition mode to real CalDAV interop failures, which is harder for
   the project to dismiss than pure UX requests.
5. **Issue #1872 (configurable behaviour) and #2234 (more frequencies)
   — already labeled as "fixed by #2032" or "duplicate of #1369".** No
   additional advocacy leverage here; these have been folded into the
   main PR.
6. **Community forum (community.vikunja.io).** Kolaente has linked five
   distinct forum threads on recurrence over the past 2-3 years:
   `/t/repeat-intervals-set-weekdays/1570`,
   `/t/vikunja-and-tasks-org-not-working-with-recurring-tasks/2151`,
   `/t/self-replicating-repeating-tasks/2122`,
   `/t/specific-weekdays-repeat-mode/639`,
   `/t/yearly-repeat-mode/1165`. The forum is where the longer-form
   user pain has historically been captured; a substantive thread tying
   PR #2032 to specific user workflows would feed into the same
   maintainer attention loop.

There is no public roadmap or project board for Vikunja prioritization
beyond the issue tracker itself. There is no maintainer "pinned" comment
specifying acceptance criteria for the PR — the criteria are inside the
inline review comments on #2032, which are visible only via the GitHub
PR diff view.

## Counterfactuals

If, despite the favorable maintainer stance, PR #2032 stalls indefinitely:

- **Fork-and-vendor.** The Vikunja codebase is AGPL-3.0 Go; Kent could
  in principle run a forked instance with PR #2032's branch applied.
  This trades upstream-tracking work for early access to the feature.
  Cost: ongoing rebase against upstream, container build pipeline
  changes.
- **Self-built RRULE-aware layer in Felix.** Kent's current direction
  (description-parser that emits Vikunja's interval-only `repeat_after`)
  is the canonical workaround. The parser can be extended to handle
  "every Monday" by computing the next occurrence client-side and
  setting Vikunja's due-date directly, treating Vikunja's native repeat
  as best-effort. This is the path that does not depend on upstream.
- **Switch tooling.** Self-hosted task managers with native RRULE
  include Nextcloud Tasks (CalDAV-native, AGPL), Tasks.org (Android
  client), and Sourcehut's `todo`. None of these are drop-in
  replacements for Vikunja's project/label/filter model. Kent has
  already invested in Vikunja as the task store; switching cost is
  high.
- **Sponsorship.** Kolaente's own quoted estimate is "5h of work,
  600 €." If PR #2032 dies due to contributor unavailability rather
  than maintainer objection, this offer is a paid path to bypass the
  contributor bottleneck entirely.

## Open questions

- **What does kolaente's `CHANGES_REQUESTED` review on PR #2032
  actually require?** The 17 inline review comments are visible only
  through the GitHub diff UI and were not enumerated in this pass. The
  outstanding question of "is this PR weeks from merge or months?"
  hinges on whether the requested changes are cosmetic or
  architectural.
- **Is the 1.0 release out?** Kolaente said "early February" for 1.0 in
  January 2026, which is more than three months ago. The release tag
  status and whether 1.0 release pressure is still consuming maintainer
  bandwidth was not verified here.
- **Has the contributor (IAMSamuelRodda) actually responded to the
  review on 2026-04-28, or only marked his presence?** The 19 review
  events from him on 2026-04-28 are mostly `COMMENTED` with empty
  bodies, which usually indicates inline diff comments. Whether those
  comments are substantive responses or just "ack" was not verified.
- **Are there parallel forks of teambition/rrule-go that have addressed
  the DST and timezone bugs?** Given the library is stale upstream, a
  more-maintained fork might exist; this was not investigated.
- **Is the Vikunja 1.0 milestone explicit about RRULE inclusion?** No
  milestone metadata was queried in this pass.
