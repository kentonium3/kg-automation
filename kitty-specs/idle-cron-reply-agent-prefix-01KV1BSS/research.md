# Research: Prefix IDLE Cron Replies With Agent Slug

**Mission**: `idle-cron-reply-agent-prefix-01KV1BSS`
**Date**: 2026-06-13
**Researcher**: Claude Code (probing live office2 + repo)

Plan-phase Probe Findings — three substantive corrections to the spec
landed before plan.md was authored. Recording each as a research note in
the Decision / Rationale / Alternatives format.

---

## R-01: Agent set is 4 (not 5); calendar excluded

**Decision**: Limit the mission to 4 Felix sub-agents:
`felix-admin-capture`, `felix-admin-habits`, `felix-admin-tasker`,
`felix-admin-escalation`. Exclude `felix-admin-calendar`.

**Rationale**: Issue #592 listed 5 affected agents including calendar, but
plan-phase probing showed:

1. `scripts/openclaw/agents/felix-admin-calendar/AGENTS.md` contains no
   "Hard rule #1", no IDLE concept, and no no-op reply path.
   `grep -nE 'IDLE|Hard rule|four characters' .../felix-admin-calendar/AGENTS.md`
   returns zero matches; `grep -nE '^##|^# '` shows the section headers are
   all about delegated calendar-event creation and clarification-reply
   handling.
2. Live `openclaw cron list --json` on office2 returns 9 cron jobs across
   `felix-admin-capture` (4: inbox-7am, inbox-noon, inbox-5pm, inbox-10pm),
   `felix-admin-habits` (2: habits-morning-checkin, habits-weekly-report),
   `felix-admin-escalation` (1: escalation-daily), and `main` (2:
   health-check-morning, health-check-evening). No calendar cron exists.
   `felix-admin-tasker` and `felix-admin-calendar` have zero cron entries.
3. The canonical agent slugs from `docs/constitution/AGENT-REGISTRY.md` are
   `felix-admin-*`, not the `<area>-agent` shorthand used in #592's
   "Affected files (likely)" section. The issue itself flagged
   uncertainty with the word "likely".

Spec updated to scope-4. `felix-admin-tasker` is kept in scope (it has the
Hard rule #1 even though it has no cron) because it can emit IDLE when
delegated to from `felix-admin-capture` — the attribution rule still
applies to its replies.

**Alternatives considered**:
- *Add the new rule to `felix-admin-calendar` too as future-proofing*:
  rejected per operator decision (2026-06-13). Adds prompt budget for
  behavior the agent doesn't currently exhibit. If calendar later gets a
  cron, the rule shape extends naturally and can be added then.
- *Drop `felix-admin-tasker`*: rejected. Tasker has the Hard rule #1
  today; the attribution gap applies to any path that emits IDLE, not
  just cron paths.

**Affected spec sections**: Overview, FR-002, FR-003, NFR-001, NFR-003,
C-006, SC-001, SC-002, SC-006 (added), EC-1 (rewritten), Domain Language,
Doc Sync.

**Decision record**: `01KV1CBKWHJPVSC6JMDH28FCYD` (resolved).

---

## R-02: Deploy mechanism is automatic; no `deploys/queued/` manifest

**Decision**: Rely on the existing `scripts/openclaw/deploy/deploy_agent_prompts.py`
+ `scripts/office2/agent-prompt-sync.service|timer` pair. Do not author a
`deploys/queued/<name>.yaml` manifest.

**Rationale**: `docs/design/architecture/data/audited-surfaces.json` entry
`openclaw-agent-prompts` documents the deploy path as:

> `scripts/openclaw/deploy/deploy_agent_prompts.py + agent-prompt-sync.service (auto)`

The systemd timer runs every 5 minutes on office2 and syncs any change to
`scripts/openclaw/agents/*/AGENTS.md` (and its `*.tmpl`/`SOUL.md`/`IDENTITY.md`
siblings) into `/data/services/openclaw/<workspace>/`. This pipeline was
shipped under #567 explicitly so that AGENTS.md edits do NOT require a
queued-manifest entry per change. Authoring a manifest here would either
be a no-op (the timer fires regardless) or worse, racy.

The deploy script does the workspace-name mapping that
[[reference_office2_agent_deploy_paths]] documents (agent-slug
`felix-admin-capture` → workspace `inbox-agent`); reviewers don't have to
know the mapping at change-authoring time.

**Alternatives considered**:
- *Author a deploys/queued manifest as "belt and suspenders"*: rejected.
  Adds a tracked artifact for a deploy that happens automatically anyway;
  also duplicates the deploy_agent_prompts.py invocation across two
  surfaces and risks them drifting.
- *Bypass the timer and push directly via the deploy script*: rejected.
  The timer is the canonical path; manual invocations should be reserved
  for recovery, not steady-state changes.

**Affected spec sections**: FR-003, FR-008 (rewritten), C-002 (refined),
Doc Sync (manifest line removed), Dependencies (deploy_agent_prompts.py
added).

---

## R-03: NFR-002 must be relative growth, not absolute size

**Decision**: NFR-002 threshold is **≤ +500 bytes per file post-mission vs
pre-mission baseline**, not the original "≤ 15,000 source bytes" absolute
ceiling.

**Rationale**: Pre-mission byte sizes via `wc -c`:

| File | Pre-mission bytes |
|------|-------------------|
| `felix-admin-capture/AGENTS.md` | 15,288 |
| `felix-admin-habits/AGENTS.md` | 15,043 |
| `felix-admin-tasker/AGENTS.md` | 14,994 |
| `felix-admin-escalation/AGENTS.md` | 12,366 |
| `felix-admin-calendar/AGENTS.md` (not in scope) | 11,893 |

Two of the four in-scope files (capture, habits) are already above the
14–15K source budget cited in [[reference_openclaw_gotchas]]. The
observation memo says the *effective* budget is ~14–15K source (~20K post
~26% inflation), but production currently runs without surfaced budget
failures — meaning the observed ceiling is empirical, not absolute.

Setting an absolute 15K cap would require compressing existing prose in
`felix-admin-capture/AGENTS.md` and `felix-admin-habits/AGENTS.md` as a
precondition for this mission. That's a meaningful scope expansion and a
distraction from the operator's stated small-mission goal. Keeping a
relative threshold (≤+500 bytes per file) honors the non-regression intent
without retroactive prose-trimming.

Expected actual growth at IC-01 contract drafting: ~+150–250 bytes per
file based on the proposed Hard rule #1 block size (one rewritten rule
line + one example line + one operator-rationale line + preserved
prohibited-pattern enumeration). Reviewer-WP enforces the ≤+500
threshold.

**Alternatives considered**:
- *Keep absolute ≤15K*: rejected per operator decision (2026-06-13).
  Forces unrelated compression work.
- *Drop NFR-002 entirely*: rejected. The non-regression bound is cheap
  insurance against an accidental rule-block bloat.

**Affected spec sections**: NFR-002 (rewritten).

---

## R-04: Existing Hard rule #1 prose varies across the 4 files

**Decision**: The canonical Hard rule #1 block (IC-01) replaces each file's
current rule-block, but keeps incident-anchor prose **as-is** where it
exists (capture has the longest variant with extensive 2026-05-20 +
2026-06-09 narrative). The canonical block contains:

1. The new byte-format directive (`[<agent-slug>]: IDLE`)
2. The example line (e.g., `Example: [felix-admin-capture]: IDLE`)
3. The enumerated still-prohibited patterns
4. The one-line operator rationale ("observed-mode attribution is a
   load-bearing observability surface; the structured prefix is required
   for that.")

Each file's existing prior-incident narrative around the rule (capture
lines 35–44, habits lines 34–35, tasker line 39, escalation lines 49–58)
is **preserved verbatim** with two surgical updates: any literal
`the four characters IDLE` is replaced with the new byte-format directive,
and any example like `your final reply is the four characters IDLE` keeps
the surrounding pedagogy but updates the literal.

**Rationale**: NFR-001 mandates rule-block shape parity but not
prose-content parity (capture's incident-anchor narrative is intentional
and load-bearing). NFR-003 mandates the change ships without modifying
non-IDLE reply paths or code. The cleanest application is: replace the
old rule line with the new rule line at the same position, update any
in-text references to "the four characters IDLE", and leave the rest of
the surrounding section alone.

**Alternatives considered**:
- *Rewrite the entire rule block uniformly across all 4 files (drop
  capture's extra incident-anchor narrative)*: rejected. Capture's
  narrative was earned through two production incidents and serves a
  pedagogical function for the model; removing it risks regressing the
  anti-narrative invariants C-005 protects.
- *Add the new rule as Hard rule #1a, leave the old text*: rejected.
  Duplicate rules invite drift; the old text would still mandate the
  bare four-character format, contradicting the new spec.

**Affected spec sections**: NFR-001 (clarified), IC-01 risk note in plan.

---

## R-05: `felix-admin-capture` inbox-5pm currently failing with auth error

**Decision**: Surface to operator; do not block mission. SC-001 verification
for `felix-admin-capture` proceeds via `inbox-7am` or another healthy
cron-id if `inbox-5pm` is still failing at IC-03 time.

**Rationale**: Plan-phase probe at 2026-06-13T20:54Z showed `inbox-5pm`
with `lastRunStatus: "error"`, `lastError: "FailoverError: LLM error
authentication_error: invalid x-api-key"`, and `lastErrorReason: "auth"`.
This is a live operational issue unrelated to issue #592 — it predates
this mission and would block SC-001 for capture if still firing at
verification time.

The other 3 cron-firing entries (`inbox-7am`, `inbox-10pm`, `inbox-noon`
for capture; `habits-morning-checkin` for habits; `escalation-daily` for
escalation) can carry SC-001 verification. The mission does not depend on
`inbox-5pm` specifically.

If the auth-store issue resurfaces and blocks all of capture's crons, the
implement-phase agent escalates to the operator. Recording the snapshot
here so future readers can verify whether this overlapped with mission
execution.

**Alternatives considered**:
- *Block mission until inbox-5pm is healthy*: rejected. The other capture
  crons (inbox-7am, inbox-noon, inbox-10pm) suffice for SC-001 capture
  verification. Blocking creates a circular dependency with whichever
  separate workstream resolves the auth issue.

**Affected spec sections**: Assumptions (added note about auth-store state).

---

## Open Research / Deferred

None. All plan-phase questions resolved. No outstanding `[NEEDS
CLARIFICATION]` markers in spec or plan.
