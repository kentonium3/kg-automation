# Research: Task-Intake Validation Loop

Phase 0 output. Resolves the unknowns in the spec's Technical Context and the
plan-phase decisions before design.

## R1 — Reply correlation mechanism (the load-bearing decision)

**Decision:** Content-based correlation, mirroring the habits `parse_morning_reply.correlate_reply_to_checkin` pattern. The scan writes a dated intake-digest correlation record; the main agent matches Kent's numbered reply lines to the most-recent digest.

**Investigation (why not WhatsApp quote-reply, Kent's first choice):** Kent initially chose WhatsApp native quote-reply. Live probe of office2 + the habits precedent falsified its feasibility:
- The baileys protocol library under `@openclaw/whatsapp` *does* carry `quotedMessage` / `contextInfo` (node_modules), but the **openclaw plugin's agent-facing payload does not forward it** to the agent.
- `docs/runbooks/habits-ops.md` (mission #408) documents this exact wall: *"WhatsApp quote-reply metadata … is NOT currently plumbed to the parser — the channel layer does not forward it."* The `quote_reply_id` kwarg in `scripts/habits/parse_morning_reply.py:723` is a `# pragma: no cover -- reserved hook` awaiting a future channel-layer extension.
- Decisive additional point: even *with* quote-reply, the design still needs a correlation record to map digest numbers → task ids; quote-reply would only identify *which digest*, which content-based correlation already solves (most-recent). Marginal value, large cost (editing a fragile, non-auto-upgraded external plugin — #588 re-trigger class).

**Rationale:** Content-based correlation is habits-proven, needs zero channel-layer work, and reuses an existing, tested pattern. Kent confirmed this path after the finding was surfaced.

**Alternatives considered:** (a) WhatsApp quote-reply — infeasible without a channel-layer extension (rejected). (b) Light trigger keyword (`intake` prefix) — viable and slightly more deterministic, but adds typing friction and still needs the correlation record; kept as a documented fallback if content-detection proves ambiguous in practice.

## R2 — Deterministic Vikunja resolution (seam) and the two-token model

**Decision:** All project/label resolution goes through the #748 `scripts/common/vikunja_refs.py` accessor. The accessor already exposes `project_id(name)`, `label_id(name, owner_token)`, `declared_labels()`, and `set_registry_for_test()` — the two-token model is already a first-class parameter (`owner_token`). Extend `vikunja_refs.json` to declare the friction (`f:1-flow`/`f:2-growth`/`f:3-edge`/`f:4-overload`), Eisenhower (`q:do`/`q:schedule`/`q:delegate`/`q:eliminate`), `t:habit`, and `loe:` label ids under the existing `vikunja_refs_validate.py` drift/AST gate (`q:schedule` id 23 is already declared).

**Rationale:** Fail-loud, no hardcoded ids, drift-gated — matches C-004 and the shipped seam discipline. The accessor's `owner_token` param directly supports FR-007.

**Alternatives considered:** A standalone label-resolution helper (rejected — duplicates the seam and bypasses the drift gate).

## R3 — Reading Inbox and applying replies (token split + read-modify-write)

**Decision:** Reuse the `scripts/vikunja/migrate_tasks.py` patterns:
- **Read** (scan): felix-bot token via `VikunjaClient` default; paginated done-inclusive enumeration (`GET /tasks/all`); filter to Inbox project id (via seam) and `done == false`.
- **Write** (apply): kent token from `/data/services/openclaw/secrets/vikunja-api-kent` (never the felix-bot default); **read-modify-write with a readback diff** (Vikunja `POST /tasks/<id>` zeros unstated fields; labels attached per per-user ownership). This is the same primitive migrate_tasks already ships (`DEFAULT_KENT_TOKEN_FILE`, `list_labels`, RMW+readback).

**Rationale:** Proven code paths; satisfies C-003/C-005/FR-013 without new low-level Vikunja plumbing.

**Alternatives considered:** felix-bot for writes (rejected — 403 on kent-owned label attach, the #750 defect).

## R4 — Tier-2 due-date writes (ET end-of-day)

**Decision:** Write Tier-2 due dates using the established ET end-of-day convention (23:59:59 with DST-aware `-04:00`/`-05:00` offset) as implemented in `scripts/habits/record_completion.py` (`_reschedule_due_date_et`, mission #733) and matching habits #112. There is **no** `scripts/common/et_datetime.py` yet — memory/roadmap has that extraction planned in the calendar mission (#739), which is not built. This mission reuses the record_completion ET-EOD approach inline.

**Rationale:** Avoids the `T00:00:00Z` off-by-one read/write class (#733/#736); consistent with how habits/escalation already write due dates.

**Alternatives considered:** Waiting on the #739 `et_datetime.py` extraction (rejected — #739 is design-stage, not built; would block this mission). **Cross-mission note:** if #739 extracts the shared helper before this merges, consume it instead of inlining; flagged as a rule-of-three candidate (this + habits + escalation = 3 sites → the extraction is justified, but owned by #739).

## R5 — Where the scan runs and where the digest state lives

**Decision:** The `inbox-processing` cron (agent `felix-admin-capture`, isolated session, 4×/day, 600s) runs `scan_inbox.py` after `route_and_finalize` and includes the numbered digest in its WhatsApp output (the capture cron already reaches Kent — the source of today's IDLE pings). The correlation record + a per-tick observability artifact live under `/data/services/openclaw/state/intake/` — mirroring the habits state dir `/data/services/openclaw/state/habits/` (`morning-checkin-<date>.json`, `sweeper-tick-<date>.json`).

**Rationale:** Rides the existing cron (Kent's cadence choice); reuses the habits state-dir + tick-artifact conventions for observability (FR-014) and correlation windowing (R1).

**Alternatives considered:** A separate dedicated intake cron/timer (rejected — Kent chose "ride the inbox crons"); emitting the digest from a new agent (rejected — capture agent already messages Kent).

## R6 — Deterministic/LLM split (Directive 6) and the LLM fallback boundary

**Decision:** Scan, shorthand parse, token resolution, and apply are 100% deterministic helpers. The **only** LLM touch points are: (a) the capture/main agent framing the WhatsApp exchange, and (b) a narrow, explicit fallback the main agent invokes **only** for a shorthand token the deterministic parser cannot resolve against the seam/alias table. An unresolved-and-unclassifiable line is echoed back to Kent, never guessed silently.

**Rationale:** Directive 6 two-layer doctrine; keeps the failure-prone agent-orchestration seam (the #737/#746 thesis) as thin as possible.

## R7 — Deploy, rebaseline, risk tier

**Decision:** Risk tier 3. Helpers deploy via office2 checkout self-pull; capture + main agent prompt updates (`AGENTS.md`/`TOOLS.md`) via `agent-prompt-sync`; a `deploys/queued/<name>.yaml` manifest creates the `/data/services/openclaw/state/intake/` dir and asserts the kent-token secret is present. **Rebaseline not required** — `audit.sh` hashes `openclaw.json`, never agent `AGENTS.md` (memory: rebaseline-directives-gap #621); no other audited surface changes.

**Rationale:** Matches the established Felix deploy discipline and the #621 rebaseline determination used by the prior #167/#746 agent-prompt missions.
