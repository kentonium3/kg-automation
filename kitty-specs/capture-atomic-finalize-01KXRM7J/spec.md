# Feature Specification: Atomic Capture Finalize Across Route Kinds

**Mission**: capture-atomic-finalize-01KXRM7J
**Issue**: kentonium3/kg-automation#746 (P1-bug, area/felix-core)
**Mission type**: software-dev

## Overview

The inbox capture agent (`felix-admin-capture`) can mark a captured note
`status: processed` **without having routed its content**, and still report the
run as successful. This is silent loss of Kent's captured intentions — the core
guarantee of the inbox system. Issue #737 closed this hole for the **calendar**
route only, via a single atomic `route_calendar_event --finalize` command. Every
other route kind still routes, records the routing-log entry, and marks the note
processed as **separate steps the agent sequences by hand** — so a note can be
stamped `processed` even though its route never happened or was never verified.

This mission generalizes the atomic finalize to **every** route kind, removes the
agent's ability to stamp `processed` on its own, and adds a health rail for the
exact signature that hid the loss: a note marked `processed` with no
corresponding routing-log entry.

## User Scenarios & Testing

**Primary actor:** the `felix-admin-capture` agent, acting on Kent's behalf during
a scheduled inbox tick.

**Trigger:** an inbox tick finds one or more unprocessed notes in `01-Inbox/`.

**Happy path:** for each note, the agent classifies the content and invokes a
single finalize operation for its kind. That operation routes the content, verifies
the produced artifact (a Vikunja task id, a created file, a GitHub issue number, a
calendar event id), records a routing-log entry, and only then marks the note
`processed`. The run reports what was routed.

**Primary exception (the bug this closes):** the route, or the verification of its
artifact, fails. The finalize operation leaves the note **unprocessed** (no
`status: processed`, no `processed_at`), surfaces the failure loudly in the tick
summary, and the note is retried on the next tick. A green run can never coexist
with an unrouted-but-processed note.

**Secondary scenario — delegated task creation:** a `vikunja_task` note is created
by delegating to the `felix-admin-tasker` agent, which returns a task id. Capture
must still finalize the note; the finalize operation accepts that externally-created
id, verifies the task exists, records the routing-log entry, and marks processed —
closing the agent-hop-then-mark gap.

**Secondary scenario — genuinely empty note:** a note with frontmatter but no
routable content is finalized through an explicit no-route disposition that records
a routing-log entry (kind = empty) and marks the note processed. There is no
"processed with no log entry" outcome.

**Secondary scenario — unclassifiable content:** a note whose content cannot be
classified is left in a `needs-review` state (no `processed_at`) — an explicitly
non-processed terminal, excluded from the health rail.

## Requirements

### Functional Requirements

| ID | Requirement | Status |
|----|-------------|--------|
| FR-001 | A single **atomic, fail-loud** finalize operation shall perform route → verify artifact → write routing-log entry → mark note processed as one indivisible unit for each supported route kind. A note is marked `processed` **only** as the final step of a successful finalize. | Draft |
| FR-002 | The finalize operation shall cover every route kind: `someday`, `journal`, `vikunja_task` (both the in-process fallback and the `felix-admin-tasker`-delegated path), `github_issue`, and `calendar` (folded into the unified mechanism). | Draft |
| FR-003 | Before marking a note processed, the finalize operation shall **verify the produced artifact exists** for that kind (e.g. a Vikunja task id resolves, a created file exists, a GitHub issue number was returned, a calendar event id/link was returned). Verification failure is a finalize failure. | Draft |
| FR-004 | On any failure (route failure, artifact-verification failure, routing-log failure), the finalize operation shall leave the note **unprocessed** — no `status: processed`, no `processed_at`, note preserved uncorrupted at its original path — and surface an actionable error. Failure never results in a silent green run. | Draft |
| FR-005 | The capture agent shall **no longer have a standalone "mark processed" capability**. Only a successful finalize can stamp `processed`. The standalone `mark_processed` step is removed from the agent's toolkit / standing orders. | Draft |
| FR-006 | For the `felix-admin-tasker`-delegated `vikunja_task` path, the finalize operation shall accept the externally-created task id, verify it, then record the routing-log entry and mark the note processed — so the delegated route closes the same silent-loss gap as in-process routes. | Draft |
| FR-007 | A genuinely empty / no-routable-content note shall be finalized through an explicit **no-route disposition** that still records a routing-log entry (kind = `empty`) and marks the note processed, so that `processed` always implies a routing-log entry. | Draft |
| FR-008 | An unclassifiable note shall remain in a `needs-review` state with **no** `processed_at` — an explicitly non-processed terminal that is excluded from the health rail (FR-010). | Draft |
| FR-009 | Every finalize shall record a routing-log entry capturing at least: note filename, route kind, destination, and the produced artifact identifier (task id / issue number / event id / file path, as applicable). | Draft |
| FR-010 | A health check shall flag any note with `status: processed` that has **no corresponding routing-log entry**, extending the existing archive-anomaly scan. `needs-review` and unprocessed notes are not flagged. | Draft |
| FR-011 | Finalize shall be **idempotent**: re-running it for a note already routed+processed (detected via the routing-log dedup substrate) is a no-op and never double-creates an artifact. | Draft |
| FR-012 | Folding calendar into the unified mechanism shall **preserve #737 behavior**: the `needs_clarification` (incomplete payload → note left unprocessed) and `error` paths, event creation, and routing-log `kind: calendar` entry are unchanged in observable behavior. | Draft |
| FR-013 | The `felix-admin-capture` `AGENTS.md` standing orders shall be updated to the single-finalize-command-per-route model, removing the hand-sequenced separate routing-log-append and mark-processed steps for all kinds. | Draft |
| FR-014 | Documentation shall be synchronized: affected architecture JSON + markdown views, the inbox/capture runbook(s), service-inventory health-check entries (for the new rail), `docs/INDEX.md`, and roadmap status, as applicable. | Draft |

### Non-Functional Requirements

| ID | Requirement | Threshold | Status |
|----|-------------|-----------|--------|
| NFR-001 | No note may reach `status: processed` without a routing-log entry. | 0 unrouted-but-processed notes across the mission's test corpus; health rail (FR-010) detects any injected violation. | Draft |
| NFR-002 | A failed finalize surfaces within the same tick it occurs. | Failure is reported in the tick summary in the same run; note is `unprocessed` for retry on the next tick. | Draft |
| NFR-003 | Zero observable behavior change to calendar-created events when calendar is folded in. | Existing #737 calendar tests remain green; created-event fields identical. | Draft |
| NFR-004 | Finalize logic is deterministic and unit-testable without live external services. | Vikunja/GitHub/calendar interactions mockable; each route kind's finalize has success + failure + idempotent unit tests. | Draft |
| NFR-005 | Finalize adds bounded latency per note. | External calls are bounded by explicit timeouts (following the #737 calendar precedent's subprocess/timeout pattern); no unbounded hangs. | Draft |

### Constraints

| ID | Constraint | Status |
|----|-----------|--------|
| C-001 | Production runs on office2 (python3-only). Helpers are invoked as `python3 -m scripts.inbox.<helper>`; bare `python` is prohibited (exit-127 + false cron-fail alert). | Draft |
| C-002 | Risk tier 3 (Python helpers + agent prompt). Helper deploy flows via office2 checkout self-pull; the `AGENTS.md` change deploys via `agent-prompt-sync`. Any office2-affecting change is queued through the `deploys/queued/` manifest discipline where applicable. | Draft |
| C-003 | Inbox invariant: the original note is **never** deleted or moved; finalize performs frontmatter-only, in-place writes and preserves the body verbatim. | Draft |
| C-004 | Privacy hard boundary: never read, write, route to, reference, or log any content in `04-Growth/_private/`. | Draft |
| C-005 | The routing log remains the dedup substrate; finalize must write it as part of the atomic unit (log-then-mark ordering must not create a state where a note is processed but the log write was skipped). | Draft |

## Success Criteria

- **SC-001:** Across a representative corpus of notes for all route kinds, no note reaches `status: processed` without a verified route and a routing-log entry.
- **SC-002:** A note whose route is made to fail is left unprocessed and its failure is surfaced in the tick summary; it is picked up and routed on a subsequent (non-failing) tick.
- **SC-003:** A `vikunja_task` created via the `felix-admin-tasker` delegation is finalized (logged + marked) only after its task id is verified.
- **SC-004:** The health rail reports zero anomalies for a correctly-finalized corpus and flags an injected "processed but unlogged" note.
- **SC-005:** Calendar routing continues to work exactly as before the fold (create, `needs_clarification`, and `error` paths all behave as in #737).
- **SC-006:** The capture agent can no longer mark a note processed except through a successful finalize (no standalone mark-processed surface remains in its standing orders/toolkit).

## Key Entities

- **Captured note** — a markdown file in `01-Inbox/` with frontmatter; the unit of capture. Has a `status` (`unprocessed` → `processed` | `needs-review`) and, when processed, a `processed_at`.
- **Route kind** — the classification that determines destination: `someday`, `journal`, `vikunja_task`, `github_issue`, `calendar`, plus the `empty` no-route disposition.
- **Artifact** — the concrete thing a route produces (Vikunja task id, created file, GitHub issue number, calendar event id/link) whose existence must be verified before finalize.
- **Routing-log entry** — the durable record of a finalize (filename, kind, destination, artifact id); the dedup substrate and the ground truth the health rail checks `processed` notes against.

## Assumptions

- The `felix-admin-tasker` delegation returns a task id that capture can pass to finalize for verification (per the existing `task_created (id=<n>)` contract).
- The empty / no-route disposition is the correct home for notes that legitimately carry no routable content (today handled by a bare `mark_processed`); folding it into finalize keeps the `processed ⇒ routing-log entry` invariant total.
- `needs-review` remains a deliberately non-`processed` state and is out of scope for the health rail.
- Dependencies #745 (restore Someday + fallback=Inbox) and #744 (canonical Inbox) are already merged, so finalize routes to stable, correct destinations.

## Dependencies

- **#737** — calendar atomic-finalize precedent (`route_calendar_event --finalize`); this mission generalizes it and folds calendar in.
- **#745 / #744** — CLOSED; the destinations finalize routes to are stable.
- **#657 / #738 / #743** — silent-loss core and the incident that confirmed this hole.

## Documentation Synchronization

Per DIR-014, the mission merge shall update, as applicable: `felix-admin-capture/AGENTS.md`
(and its `.tmpl`), the inbox/capture runbook(s), `docs/design/architecture/data/`
service-inventory + health-check entries for the new rail (and their markdown views),
`docs/INDEX.md` / `docs/DEVELOPER_PORTAL.md` if a new doc surface is added, and the
capability roadmap status for the capture-reliability thread.
