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
processed as **separate steps the agent sequences by hand**.

A captured note is not a single item: `classify_content` splits its body into
**multiple blocks**, and different blocks can route to different kinds (a calendar
event and a someday task in one note). But `status: processed` is **note-level**.
The correct fix is therefore not "one atomic helper per route" (that would mark the
whole note processed on the first block and silently drop the rest — a regression),
but a **note-level finalize transaction**: route every block, verify every artifact,
record a per-block routing-log entry, and only then mark the note processed — as one
indivisible, fail-loud, retry-safe operation. This mechanism becomes the **only**
path by which a note reaches `status: processed`; the agent's standalone
`mark_processed` is removed. A health rail flags any `processed` note lacking a
routing-log entry, and it is surfaced in the agent's IDLE gate so it actually
reaches Kent.

## User Scenarios & Testing

**Primary actor:** the `felix-admin-capture` agent, on Kent's behalf, during a
scheduled inbox tick.

**Trigger:** an inbox tick finds one or more unprocessed notes in `01-Inbox/`.

**Happy path:** for each note, the agent classifies its blocks (deterministically
where possible, using its own judgment for genuinely ambiguous blocks) and assembles
a per-block routing plan. It invokes a single note-level finalize with that plan. The
finalize routes each block, verifies each artifact (a Vikunja task id, a created
file, a GitHub issue number, a calendar event id), records a per-block routing-log
entry, and only then marks the note `processed`. The run reports what was routed.

**Primary exception (the bug this closes):** any block's route, or the verification
of its artifact, fails. The finalize leaves the **whole note unprocessed** (no
`status: processed`, no `processed_at`), surfaces which block failed, and the note is
retried next tick. On retry, blocks already routed+logged are skipped (no
double-create). A green run can never coexist with an unrouted-but-processed note.

**Multi-block note:** a note with a calendar block and a someday block is finalized
only after **both** artifacts exist and both are logged; the note is marked once. If
the someday block fails, the note stays unprocessed and the calendar event is not
re-created on retry (block-keyed idempotency).

**Delegated task creation:** a `vikunja_task` block is created by delegating to
`felix-admin-tasker`, which returns a task id. Finalize accepts that id, verifies the
task exists **and belongs to this note** (source provenance), records the entry, and
contributes it to the note-level mark.

**Genuinely empty note:** a note whose body is empty / templater-only is finalized
through an explicit no-route disposition that first **validates the body is genuinely
empty**, then records a routing-log entry (kind = empty) and marks the note
processed. There is no "processed with no log entry" outcome.

**Unclassifiable content:** a note whose content cannot be classified is left in a
`needs-review` state (no `processed_at`) — an explicitly non-processed terminal that
prescan treats as terminal (no reprocessing loop) and the health rail ignores.

## Requirements

### Functional Requirements

| ID | Requirement | Status |
|----|-------------|--------|
| FR-001 | Finalize shall be a **note-level, atomic, fail-loud transaction**: route every block of the note → verify every artifact → record a per-block routing-log entry → mark the note processed, as one indivisible unit. The note is marked `processed` **only** after every block is routed+verified+logged. | Draft |
| FR-002 | The transaction shall cover every route kind: `someday`, `journal`, `vikunja_task` (in-process and `felix-admin-tasker`-delegated), `github_issue`, and `calendar` (folded into the unified mechanism), plus the `empty` no-route disposition. | Draft |
| FR-003 | Before contributing a block to the note-level mark, finalize shall **verify the produced artifact exists** for that block (Vikunja task id resolves, created file exists, GitHub issue number returned/verifiable, calendar event id returned). Verification failure fails the transaction. | Draft |
| FR-004 | On **any** block failure (route, verify, or log), the transaction shall leave the **whole note unprocessed** — no `status: processed`, no `processed_at`, note preserved uncorrupted — and surface which block failed. Failure never yields a silent green run. | Draft |
| FR-005 | The capture agent shall **no longer have a standalone mark-processed or append-routing-log capability**. Only a successful finalize can stamp `processed`. Standalone `mark_processed` / `append_routing_entry` are removed from the agent's standing orders / toolkit. | Draft |
| FR-006 | For a `felix-admin-tasker`-delegated `vikunja_task` block, finalize shall accept the externally-created task id and verify it **exists and belongs to this note/block** (via source provenance recorded on the task, e.g. the `Source: <note-filename>` footer), not merely that some id exists. Retry shall never re-delegate a duplicate. | Draft |
| FR-007 | The `empty` no-route disposition shall first **validate the note body is genuinely empty / templater-only** before recording a routing-log entry (kind = `empty`) and marking the note processed. It shall refuse to bury a non-empty body. | Draft |
| FR-008 | An unclassifiable note shall remain `needs-review` with **no** `processed_at`; `prescan` shall classify inbox `needs-review` notes as **terminal** and exclude them from `unprocessed_paths` (no reprocessing loop). It is excluded from the health rail. | Draft |
| FR-009 | Every routed block shall record a routing-log entry keyed on **note filename + block index + block content hash**, so one routed block never masks another block in the same note and a reused basename never masks an unrelated note. | Draft |
| FR-010 | Finalize shall be **idempotent per block**: on re-run, a block already routed+logged (per its block key) is skipped and its side effect is never repeated. Each kind shall guard its side effect before performing it (calendar: source-path idempotency key; someday/vikunja_task: block-key precheck; journal: a per-block sentinel in the appended section; github_issue: block-key + issue verification). | Draft |
| FR-011 | The finalize **state machine** shall resolve log/mark ordering coherently: each block's routing-log entry is written durably **before** the note is marked; the note is marked only after **all** blocks are logged; a re-run reconciles from the routing log. This eliminates the "processed but unlogged" state. | Draft |
| FR-012 | `github_issue` routing (filed via the main agent's `felix-file-issue.py`) shall treat a **missing/null issue number as a finalize failure** and verify the issue exists before contributing it to the mark. The route's agent-hop nature shall be specified (who runs the filer; how the number returns to finalize). | Draft |
| FR-013 | A health check shall flag any note with `status: processed` that has **no corresponding routing-log entry** (extending the archive-anomaly scan), covering notes in both `01-Inbox/` and `02-Inbox-Processed/`. `needs-review` and unprocessed notes are not flagged. | Draft |
| FR-014 | The health-rail result shall be **surfaced to the agent**: the Step 1 IDLE gate shall block the `IDLE` reply and report `archive_anomalies` (including `processed-without-routing-log`), so the alarm reaches Kent rather than dying in a field no one reads. | Draft |
| FR-015 | Folding calendar into the unified mechanism shall **preserve #737's observable create behavior**: event creation, the `needs_clarification` (incomplete payload → note left unprocessed) path, and the `error` path behave identically. The prior leniency of reporting `finalized` with `routing_logged:false` is **intentionally removed** (a log failure now leaves the note unprocessed per FR-011). | Draft |
| FR-016 | The capture `AGENTS.md` standing orders shall be updated to the note-level single-finalize model: the agent classifies blocks, assembles a routing plan, and invokes one finalize; the hand-sequenced routing-log-append and mark-processed steps are removed for all kinds. | Draft |
| FR-017 | Documentation shall be synchronized: capture `AGENTS.md`(+`.tmpl`)/`TOOLS.md`(+`.tmpl`), the inbox/capture runbook(s), `docs/design/architecture/data/` service-inventory + health-check entries (and md views), `docs/INDEX.md`/roadmap as applicable. | Draft |

### Non-Functional Requirements

| ID | Requirement | Threshold | Status |
|----|-------------|-----------|--------|
| NFR-001 | No note may reach `status: processed` without a routing-log entry for every routed block. | 0 processed-but-unlogged notes across the test corpus; the health rail (FR-013/FR-014) detects any injected violation and blocks IDLE. | Draft |
| NFR-002 | A failed finalize surfaces within the same tick it occurs. | Failure reported in the tick summary in the same run; note left unprocessed for retry. | Draft |
| NFR-003 | Calendar-created events and the create/needs_clarification/error decision paths are unchanged when calendar is folded in. | Existing #737 create/clarification/error tests remain green (adjusted only for the FR-015 log-failure semantics change); created-event fields identical. | Draft |
| NFR-004 | Finalize logic is deterministic and unit-testable without live external services; retry safety is proven. | Vikunja/GitHub/calendar mockable; each kind has success + route-failure + verify-failure + **route-success-then-mark/log-failure retry** tests proving no double-create. | Draft |
| NFR-005 | Finalize adds bounded latency per note. | Every external call bounded by explicit subprocess/timeouts (per the #737 pattern); no unbounded hangs within the 600s cron turn. | Draft |

### Constraints

| ID | Constraint | Status |
|----|-----------|--------|
| C-001 | office2 is python3-only; helpers invoked as `python3 -m scripts.inbox.<helper>`; bare `python` prohibited. | Draft |
| C-002 | Risk tier 3 (Python helpers + agent prompt). Helpers deploy via office2 checkout self-pull; `AGENTS.md` via `agent-prompt-sync`; `deploys/queued/` manifest only if an office2 apply step beyond self-pull is needed. | Draft |
| C-003 | Inbox invariant: the original note is never deleted or moved; finalize performs frontmatter-only, in-place writes and preserves the body verbatim. | Draft |
| C-004 | Privacy: never read/write/route/reference/log any content under `04-Growth/_private/`; `mark_processed`'s exit-3 refusal is preserved (the reason finalize invokes it as a subprocess). | Draft |
| C-005 | The classification of ambiguous blocks remains **agent (LLM) judgment**; the deterministic helper owns route execution + verification + logging + marking. The agent passes a per-block routing plan to the helper (two-layer doctrine, Directive 6). | Draft |
| C-006 | Finding #10 (surfacing pending-calendar-clarification notes in prescan) is **out of scope**, deferred to the already-filed #740. | Draft |

## Success Criteria

- **SC-001:** Across a corpus spanning all kinds and multi-block notes, no note reaches `status: processed` without a routing-log entry for every routed block.
- **SC-002:** A note with a failing block is left unprocessed with its failure surfaced; on a later (non-failing) tick it finalizes, and no already-succeeded block's artifact is duplicated.
- **SC-003:** A multi-block note is marked processed exactly once, only after all its blocks' artifacts exist and are logged.
- **SC-004:** A tasker-delegated `vikunja_task` is contributed to the mark only after its id is verified to exist and belong to the note.
- **SC-005:** The health rail reports zero anomalies for a correctly-finalized corpus, flags an injected "processed-but-unlogged" note, and that anomaly blocks the agent's IDLE reply.
- **SC-006:** Calendar routing's create / needs_clarification / error behavior is unchanged; a calendar log failure now leaves the note unprocessed (no `finalized`+`routing_logged:false`).
- **SC-007:** The capture agent can no longer mark a note processed except through a successful finalize; the `empty` disposition refuses a non-empty body; `needs-review` notes do not reprocess.

## Key Entities

- **Captured note** — a markdown file in `01-Inbox/`; `status` (`unprocessed` → `processed` | `needs-review`), `processed_at` when processed, body preserved verbatim.
- **Block** — one semantic unit of a note (`classify_content.split_blocks`); has an index, content, and a routed kind. The unit of routing and of the routing-log key.
- **Route kind** — `someday`, `journal`, `vikunja_task`, `github_issue`, `calendar`, plus the `empty` no-route disposition.
- **Artifact** — the concrete thing a block produces (task id / file / issue number / event id) whose existence (and, for delegated tasks, provenance) is verified before the mark.
- **Routing-log entry** — the durable per-block record (note filename, block index, block hash, kind, destination, artifact id); the block-level idempotency substrate and the ground truth the health rail checks `processed` notes against.
- **Routing plan** — the agent-assembled list of `{block_index, kind, payload|artifact-id}` the finalize executes.

## Assumptions

- `felix-admin-tasker` records source provenance (`Source: <note-filename>`) on tasks it creates, enabling FR-006 provenance verification; if not, finalize adds/verifies it.
- Block content hashing over `split_blocks` output is stable enough to key idempotency across ticks for an unchanged note.
- Dependencies #745 (Someday + fallback=Inbox) and #744 (canonical Inbox) are merged, so destinations are stable.

## Dependencies

- **#737** — calendar atomic-finalize precedent; generalized and folded here.
- **#745 / #744** — CLOSED; destinations stable.
- **#740** — receives deferred finding #10 (pending-calendar-clarification surfacing).
- **#657 / #738 / #743** — silent-loss core and the confirming incident.

## Documentation Synchronization

Per DIR-014, the merge updates as applicable: `felix-admin-capture/AGENTS.md`(+`.tmpl`)
and `TOOLS.md`(+`.tmpl`), the inbox/capture runbook(s), `docs/design/architecture/data/`
service-inventory + health-check entries for the new rail (and md views),
`docs/INDEX.md`/`docs/DEVELOPER_PORTAL.md` if a doc surface is added, and the capability
roadmap status for the capture-reliability thread.
