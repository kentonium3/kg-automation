---
affected_files: []
cycle_number: 4
mission_slug: office4-architecture-registration-01M15RW2
reproduction_command:
reviewed_at: '2026-08-29T05:17:25Z'
reviewer_agent: user
wp_id: WP02
---

# WP02 Review Feedback — cycle 3 (raised by the WP06 closeout review)

**Verdict**: REQUEST-CHANGES
**Origin**: WP06's reviewer, executing quickstart step 6 properly for the first time.
**Date**: 2026-08-29

## MODERATE — Q4 of the ADR's own five questions is not answerable from the document

Contract C-5 requires a reader to answer, without leaving the ADR: *"What must office4 never
hold, and why?"*

The constraint heading is *"office4 must hold no `kg-automation` checkout at a
**felix-deployer-recognisable path**"* — and that qualifier, which carries the entire
operational meaning, is **never defined**. The only in-document referent is citation 3's
`DEFAULT_REPO_ROOT = /home/claude/kg-automation`, and the *next* constraint states office4 has
no `claude` user — so the one path a reader could infer is impossible on office4 by the ADR's
own account.

Concretely: office4 holds a checkout at `/home/kgale/repos/kg-automation` right now — it is
the tree this mission was executed in. A reader cannot determine from ADR-0008 whether that
breaches the constraint. For a documentation-only constraint with **no mechanical
enforcement**, being unactionable is the whole failure: the ADR is the only thing standing
between the constraint and a breach, and it does not say what a breach looks like.

**Required fix**: define what "recognisable" means, in the document. The two constraints are
in fact mutually reinforcing and the ADR should say so:

- felix-deployer resolves its checkout from `DEFAULT_REPO_ROOT`
  (`scripts/deploy/felix-deployer/_tick.py:59`) = `/home/claude/kg-automation`.
- That path lives under a `claude` home directory. office4 has no `claude` user — which is
  the *second* constraint — so the recognised path cannot exist there.
- Therefore `/home/kgale/repos/kg-automation` is **not** recognisable and is not a breach.
- The constraint bites if someone creates a `claude` user on office4, or relocates the
  deployer's repo root, or otherwise makes office4 present a checkout at the path the
  deployer resolves.

State the safe case explicitly. A constraint a reader can only satisfy by accident is not a
constraint.

## Process note

This gap survived four review cycles because quickstart step 6 was recorded in WP06's report
as PASS on the evidence *"verified across four independent review cycles"* — a citation of
other people's work rather than an execution of the step. Those cycles reviewed FR-001–FR-005
compliance; only one mentions the placement test, in passing, and none ran the five-question
test. WP06's report is being corrected in step with this.
