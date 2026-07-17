# Research: Atomic Capture Finalize Across Route Kinds

All decisions below are grounded in a read of the live inbox toolkit
(`scripts/inbox/*.py`, `scripts/openclaw/agents/felix-admin-capture/AGENTS.md`)
on 2026-07-17 (DIR-015: probe the real environment during design).

## D1 — Finalize skeleton: generalize `route_calendar_event._run_finalize`

- **Decision**: Build one generic finalize skeleton in a new
  `scripts/inbox/route_and_finalize.py`, structurally identical to the proven
  `route_calendar_event._run_finalize` (#737): route → verify artifact →
  `mark_processed` (subprocess) → routing-log append (LAST) → derive exit code
  from the OUTCOME, not from the route step.
- **Rationale**: #737 already solved the hard atomicity/ordering problems for
  calendar. The same skeleton generalizes cleanly if the per-kind bits (route
  call + verify predicate + routing-log kind/destination) are parameterized.
  Rule-of-three: calendar is the first instance; someday/journal/vikunja_task/
  github_issue are instances 2–5 → extract the shared skeleton.
- **Load-bearing details carried over verbatim**:
  - `mark_processed` MUST be a **subprocess**, never an in-process function call:
    the `_private/` refusal (exit 3), inbox-root validation, and the symlink
    `.resolve()` guard live in `mark_processed.main()`. A direct call would let a
    symlinked vault note mark the symlink while the real target stays
    unprocessed — re-opening the silent-loss class (route_calendar_event.py:374-402).
  - routing-log append is **last and idempotent** (`RoutingLogReader.has()`):
    `prescan` dedups on the routing-log filename, so a log-before-mark write can
    strand a note (skipped forever, never processed). See
    `_append_calendar_routing_log` (route_calendar_event.py:405-430).
  - Exit code derives from outcome: `_run_create`/route helpers return 0 for
    created/error alike, so the skeleton inspects status + artifact presence and
    forces a non-zero exit on failure (route_calendar_event.py:433-496).
- **Alternatives considered**: (a) per-kind `--finalize` flag on each existing
  route helper — rejected: duplicates the atomic skeleton 5×, and the agent
  would still juggle 5 command shapes. (b) leave calendar separate — rejected by
  Kent (2026-07-17): fold calendar in for one mechanism, no vestige.

## D2 — Fold calendar into the generic mechanism (Kent decision 2026-07-17)

- **Decision**: The generic dispatcher handles `--kind calendar` by invoking the
  existing calendar create/verify path (`route_calendar_event._run_create` +
  event_id check). The calendar-specific create internals (envelope build, google
  venv subprocess, `needs_clarification`/`error` result shapes) are **preserved**;
  only the finalize *wrapper* is unified.
- **Rationale**: One mechanism, no divergent finalize implementations
  (no-vestiges). Keeping calendar's route internals intact bounds regression risk
  to the one route that already works.
- **Guardrail (NFR-003)**: existing #737 calendar tests must stay green; the
  `needs_clarification` (payload incomplete → note left unprocessed) and `error`
  (create failed → note left unprocessed) paths behave identically. Add a
  regression assertion that a folded calendar route yields the same result JSON
  as today.

## D3 — vikunja_task, both paths (Kent decision 2026-07-17: cover both)

- **Decision**: `--kind vikunja_task` finalize supports two provenances:
  1. **In-process** — finalize calls `route_someday.route_someday(...)` (or the
     future enriched task creator), gets `task_id=<int>`, verifies the id
     resolves via `VikunjaClient`, then logs (kind=`vikunja_task`,
     destination=task_id) + marks.
  2. **Tasker-delegated** — the capture agent delegates to `felix-admin-tasker`,
     which returns `task_created (id=<n>)`. Capture passes that id to finalize
     (e.g. `route_and_finalize --kind vikunja_task --task-id <n> --source-path
     <p>`); finalize **verifies** the id exists (does not create), then logs +
     marks atomically.
- **Rationale**: The silent-loss gap exists on the delegated path too (tasker
  creates the task, capture marks processed separately). Accepting an
  externally-created artifact id and verifying it closes the agent-hop-then-mark
  gap uniformly.
- **Verification**: a lightweight `GET /tasks/<id>` (or the client's task-fetch)
  under the felix-bot token; a 404/absent task is a finalize failure (note left
  unprocessed). felix-bot can READ kent-shared tasks (the #715 boundary only
  blocks label *attach*), so read-verify is available.
- **Note (out of scope, tracked)**: `route_someday`'s q:schedule label attach is
  already fail-soft (felix-bot 403, #750); finalize does not change that — task
  creation is the durable landing, label attach remains best-effort.

## D4 — No-route / empty disposition (closes the health-rail false-positive gap)

- **Decision**: Add an explicit `--kind empty` (no-route) finalize disposition
  that records a routing-log entry (kind=`empty`, destination="") and marks the
  note processed. Genuinely empty notes (frontmatter, no routable content — today
  marked by a bare `mark_processed`, AGENTS.md §"Empty inbox files") go through
  this path.
- **Rationale**: Makes the invariant **`processed ⇒ routing-log entry` total**,
  so the FR-010 health rail has zero legitimate false positives. Without it,
  empty notes would be `processed` with no log entry and trip the rail.
- **`needs-review` stays separate**: unclassifiable notes remain
  `status: needs-review` with no `processed_at` via the existing direct
  frontmatter edit (AGENTS.md §"Exception — unclassifiable blocks"). It is NOT
  `processed`, so it is out of the rail's scope. This is the one sanctioned
  non-finalize frontmatter write and is preserved.

## D5 — Remove standalone mark_processed from the agent toolkit (FR-005)

- **Decision**: `mark_processed.py` remains in the repo (finalize calls it as a
  subprocess) but is **removed from the capture agent's standing orders / TOOLS**
  as an independently-invokable step. AGENTS.md Steps 5b (append_routing_entry)
  and 5c (mark_processed) collapse into "run `route_and_finalize` for the kind."
- **Rationale**: Only a successful finalize can stamp `processed`. Removing the
  agent's ability to call `mark_processed` (or `append_routing_entry`) directly
  eliminates the hand-sequencing that let a note be marked without a verified
  route.
- **Preserved exceptions**: the `needs-review` direct edit (D4) and — folded into
  `--kind empty` — the empty-note case. No other path may write `status: processed`.

## D6 — Health rail: processed-without-routing-log (FR-010)

- **Decision**: Extend the `prescan.py` archive-anomaly rail (`scan_archive_anomalies`,
  #568) with a new classification `processed-without-routing-log`: for notes whose
  status IS `processed`, cross-reference `RoutingLogReader.has(filename)`; a miss is
  an anomaly. Scan both `01-Inbox/` (processed notes await the 7-day archive there)
  and `02-Inbox-Processed/`.
- **Rationale**: The existing rail scans for the *inverse* (non-processed files in
  the archive). The new check is the direct detector for #746's signature. Read-only,
  no remediation — surfaces the alarm; the tick summary carries it.
- **Bounds**: reuse `ARCHIVE_SCAN_CAP` and the `inbox-processing-` daily-log filename
  exclusion. `empty`-kind and `needs-review` notes never trip it (D4).

## D7 — Deploy (C-002)

- **Decision**: Helper changes (`scripts/inbox/*`, `prescan.py`) deploy via the
  office2 checkout self-pull (felix-deployer auto-pulls origin/main). The capture
  `AGENTS.md`/`TOOLS.md` deploy via `agent-prompt-sync` to
  `/data/services/openclaw/inbox-agent/` (slug `felix-admin-capture` ≠ deploy dir —
  [[reference_office2_agent_deploy_paths]]). A `deploys/queued/<name>.yaml` manifest
  is added only if an office2-side apply step beyond the self-pull is required
  (none anticipated — pure code + prompt).
- **Rebaseline**: expected **not required** — AGENTS.md is not a hashed audited
  surface (#621); `scripts/inbox/` is not in `audited-surfaces.json`. Confirm at
  merge and stamp the reason.
- **Verification**: office2 `--dry-run` (credential-free wiring) per kind where a
  dry-run exists; live smoke on the next inbox tick.

---

## Post-plan Codex review fold (2026-07-17)

The mandatory post-plan Codex review (spec-kitty-review profile; 3 lenses) returned
12 findings (6 HIGH / 6 MEDIUM), verdict "fold findings first." Kent's scope call
(2026-07-17): fold findings 1–9, 11, 12; defer finding 10 (pending-calendar-clarification
surfacing) to the already-filed #740. The decisions below resolve them; they reshape the
design from "per-route finalize" to a **note-level finalize transaction**.

### D8 — Note-level finalize transaction (finding 1)

- **Decision**: Finalize operates on the **whole note**, not a single route. The agent
  classifies the note's blocks (deterministic via `classify_content` + LLM judgment for
  ambiguous ones), assembles a per-block routing plan `{block_index, kind, payload|task_id}`,
  and invokes ONE note-level finalize. The helper routes each block, verifies each artifact,
  writes a per-block routing-log entry, and marks the note processed **once, only after all
  blocks are done**.
- **Rationale**: `classify_content.split_blocks` genuinely emits multiple blocks per note
  (verified 2026-07-17), and `mark_processed` is note-level. A per-route finalize would mark
  the whole note processed on the first block's success and silently drop later blocks — a
  regression versus today's route-all-then-mark-once behavior. Note-level is the correct unit.
- **Two-layer split (C-005, Directive 6)**: classification stays LLM (its job); the helper
  owns deterministic route-execute + verify + log + mark. The agent's role shrinks to
  classify → build plan → call one command. This *removes* the hand-sequencing that caused
  the bug.

### D9 — Finalize state machine + log/mark ordering (findings 3, 11, 12)

- **Decision**: Resolve the spec-vs-precedent ordering contradiction with an explicit state
  machine. Per block: route → verify → **write the block's routing-log entry (durable,
  block-keyed)**. After **all** blocks are logged: mark the note processed (once). A re-run
  reconciles from the routing log (skip already-logged blocks). This makes log-before-mark at
  the note level, and there is no "processed but unlogged" state.
- **prescan dedup shift**: prescan's note-level dedup moves from "filename present in routing
  log" to note **status** (`processed`/`needs-review` are terminal). Block-level idempotency
  now lives inside finalize (block keys), so the note-level log dedup is no longer needed and
  the ordering contradiction dissolves.
- **Calendar leniency removed (finding 12 / NFR-003 / FR-015)**: #737 currently returns
  `finalized` with `routing_logged:false` when the log write fails. Under D9 a log failure
  leaves the note unprocessed (not finalized). This is an intended tightening — that leniency
  was itself a silent-loss vector. NFR-003 is re-scoped to preserve **created-event fields +
  the create/needs_clarification/error decision paths**, and the #737 tests that bless
  `routing_logged:false + finalized` are updated to the new semantics.

### D10 — Per-block routing-log keys + per-kind idempotency (findings 2, 4, 5)

- **Decision**: The routing-log entry key becomes **note filename + block index + block
  content hash** (not filename alone), so one routed block never masks another and a reused
  basename never masks an unrelated note. Each kind guards its side effect *before*
  performing it: calendar keeps its source-path idempotency key; someday/vikunja_task do a
  block-key precheck (skip create if the block key is already logged); journal writes a
  **per-block sentinel** into the appended section and verifies it before appending (no
  duplicate section on reprocess); github_issue does a block-key precheck + issue verify.
- **Rationale**: fail-loud-then-retry is only safe if a route that succeeded before a later
  mark/log failure is not repeated on the next tick. `RoutingLogReader.has(filename)` (the
  #737 dedup) is too coarse for multi-block notes.
- **Test posture (NFR-004)**: every kind gets a "route-success then mark/log-failure → retry
  → no double-create" test.

### D11 — Agent-hop route provenance: tasker + github (findings 6, 7)

- **Decision (tasker, finding 6)**: verifying a `vikunja_task` id must prove it **belongs to
  this note/block**, not merely that some task exists. Finalize checks source provenance (the
  `Source: <note-filename>` footer `route_someday` already writes, or the tasker envelope) on
  the fetched task; a mismatched/absent-provenance id is a finalize failure. Retry keyed on
  the block never re-delegates.
- **Decision (github, finding 7)**: `felix-file-issue.py` is invoked by the **main** agent
  and can exit 0 with `issue_number: null` (URL-parse miss). Finalize treats a missing/null
  issue number as a failure and verifies the issue exists (e.g. `gh issue view`) before
  contributing it to the mark. The plan specifies the hop explicitly: capture assembles the
  issue payload, the filer runs (main-agent helper), the returned number flows back into the
  note-level finalize plan; a null number blocks the note's mark.

### D12 — Empty disposition body validation (finding 8)

- **Decision**: `--kind empty` (no-route) first validates the note body is **genuinely
  empty / templater-only** (mirrors `prescan.classify_file`'s empty detection) before marking
  processed with a kind=`empty` routing-log entry. It refuses a non-empty body loudly.
- **Rationale**: without this guard the `empty` disposition is a silent-loss escape hatch —
  the exact failure this mission closes. Empty is a verified terminal, not a bypass.

### D13 — needs-review terminal in prescan + health rail surfaced (findings 9, 11→14)

- **Decision (finding 9)**: `prescan` classifies inbox `needs-review` notes as **terminal**
  (excluded from `unprocessed_paths`) so they don't reprocess every tick; they are also
  excluded from the new health rail (not `processed`).
- **Decision (finding 11 → FR-014)**: the new `processed-without-routing-log` anomaly is
  surfaced in the agent's **Step 1 IDLE gate** — the gate must block the `IDLE` reply and
  report `archive_anomalies` when any exist. Otherwise the rail writes to a field the agent
  never reads and the alarm never reaches Kent.
