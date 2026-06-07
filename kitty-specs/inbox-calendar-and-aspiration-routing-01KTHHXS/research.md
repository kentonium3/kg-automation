# Phase 0 Research: Inbox calendar and aspiration routing

**Mission**: `inbox-calendar-and-aspiration-routing-01KTHHXS`
**Spec**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)

This document records the load-bearing environmental research conducted during `/spec-kitty.plan` per Felix Constitution Directive 6 (probe the real environment during design phase). Each item follows the format Decision / Rationale / Alternatives considered.

---

## R-001 — Google Calendar write mechanism: `gog calendar create` via existing skill

**Decision**: Reuse the existing `gog` openclaw skill installed system-wide on office2. Capture agent delegates to Felix main via `openclaw agent --agent main`; Felix main shells out to `/home/linuxbrew/.linuxbrew/bin/gog calendar create <calendarId> --summary "…" --from <iso> --to <iso> [--rrule <rrule>] [--location <loc>] [--description <desc>] [--start-timezone <tz>] -j`.

**Rationale**:
- gog v0.19.0 is already installed, authenticated, and operational on office2.
- The `--rrule` flag accepts RFC 5545 strings — confirmed for the trivia-night use case from #324.
- gog OAuth is wired via `gog-keyring-password` + `openclaw-gateway-env` systemd EnvironmentFile, so child agent sessions inherit credentials transparently (no per-mission credential work).
- The architecture inventory at `docs/design/architecture/data/service-inventory.json` documents gog as "consumption by any Felix agent" — first-class integration.
- Felix main already runs gog interactively when Kent asks via WhatsApp; this mission extends that pattern to inbox-driven delegation.

**Alternatives considered**:
- *Capture invokes gog directly*: would require giving the capture agent the `gog` skill and `GOG_KEYRING_PASSWORD` access. Expanded the autonomy surface unnecessarily; Felix main already has gog and is the natural cross-system action agent.
- *Use Google Calendar Python API (`google-api-python-client`) directly*: bypasses the gog skill, requires reimplementing OAuth credential plumbing, adds a new dependency. Gog already wraps these concerns.
- *Defer calendar write to a follow-up mission*: rejected by operator — calendar write is the primary mission value (see spec FR-005).

**Verification**:
- `ssh office2-claude '/home/linuxbrew/.linuxbrew/bin/gog --version'` → `v0.19.0 (b25a3c0 2026-05-22T15:53:00Z)`
- `gog calendar create --help` returns the full flag surface including `--rrule=RRULE`.

---

## R-002 — Felix main is the WhatsApp inbound receiving agent

**Decision**: FR-007's "receiving agent" is Felix `main`. Kent's WhatsApp reply to a clarification prompt is routed to Felix main by the openclaw whatsapp channel; Felix main reads the pending-calendar-clarifications JSONL state file, matches the reply to the most recent open entry, and completes the event creation.

**Rationale**:
- `openclaw doctor` explicitly states: "Agent 'main' is routed from channel 'whatsapp', but the message tool is unavailable for that agent…" — confirming agent `main` is the inbound endpoint.
- Felix main already has gog access (per R-001), so the reply→event-create chain is single-agent.
- No new agent introduced — matches C-001 in the spec.

**Alternatives considered**:
- *Capture agent receives the reply*: would require capture to also have gog access. Cross-agent coupling. Rejected.
- *A new dedicated calendar-reply agent*: violates C-001 (no new agents). Rejected.

**Open caveat**: `openclaw doctor` warns that channel-action calls like `sendAttachment`, `thread-reply`, `reply` can fail because the `message` tool is missing from main's allowlist. For this mission's flow, Felix main reads a file and shells out to gog — it does NOT need the channel-action `reply` tool to complete the work. It may need to send a confirmation via WhatsApp turn-summary at end of turn, which is the standard openclaw outbound (not a special action). If that breaks, it's a pre-existing openclaw config issue separate from this mission.

**Verification**:
- `ssh office2-claude 'openclaw doctor 2>&1'` → confirms main + whatsapp routing + tool gap.

---

## R-003 — Pending-calendar-clarifications state file location and shape

**Decision**: Append-and-rewrite JSONL file at `~/second-brain/agents/state/pending-calendar-clarifications.jsonl`. One line per open clarification with shape `{clarification_id, source_inbox_path, source_block_index, fields_so_far, missing_fields, sent_at}`. Resolved entries are removed (read-all → filter → write-back). 24h timeout entries stay until manually purged (audit trail).

**Rationale**:
- `~/second-brain/agents/state/` already hosts `inbox-routing.jsonl` — the natural neighbour for sibling state.
- JSONL is the same substrate as the routing log → operator already knows the read shape.
- Single-file state for ≤dozens of open clarifications at any time keeps the design trivially simple.
- File is local to office2; no cross-host coordination needed.

**Alternatives considered**:
- *Vikunja task records*: would re-create the very anti-pattern this mission is fixing (calendar items as Vikunja todos).
- *In-memory only on Felix main*: lost on agent restart; no audit trail.
- *A new SQLite or DB*: massive overkill for ≤dozens of records.

---

## R-004 — Vikunja Someday project resolution

**Decision**: Route Someday-classified blocks to Vikunja project `id=4, title="Someday"`. Capture resolves the project by name (not by hard-coding the id) using the existing vikunja-api skill resolution pattern, so a future rename of the project doesn't break the mission.

**Rationale**:
- Probe confirmed project exists: `4: Someday (identifier=)`.
- Vikunja's existing project-by-name resolution in the vikunja-api skill is the established pattern.
- Hard-coding the id couples the mission to a UI choice that could change.

**Alternatives considered**:
- *Hard-code project_id=4*: brittle. Rejected.
- *Create a new "Calendar-Pending" or "Inbox-Calendar" project*: adds Vikunja noise; existing Someday project semantically fits "concrete-but-parked actionable items".

**Verification**:
- `ssh office2-claude` + `curl /api/v1/projects` → returns Someday at id=4.

---

## R-005 — vikunja_config helper public API and trailing-slash quirk

**Decision**: Use `scripts/common/vikunja_config.get_vikunja_base_url()` for the base URL. Token loaded directly from `/data/services/openclaw/secrets/vikunja-api` (no helper for token). Normalize the URL by stripping any trailing slash before making API calls.

**Rationale**:
- `vikunja_config.py` exports only `get_vikunja_base_url()` (verified via `grep '^def ' scripts/common/vikunja_config.py`). My initial spec assumption (`from vikunja_api.config import get_token, get_base_url`) was wrong on both module name and exported symbols (per memory `feedback_wp_prompts_grep_codebase.md`).
- The canonical config file `/data/services/openclaw/config/vikunja-base-url.txt` has a trailing slash; the Vikunja API rejects requests where the path begins with `//`. Strip the trailing slash before composing the request URL.
- Token storage path matches the existing `vikunja-api` openclaw skill convention.

**Alternatives considered**:
- *Use the vikunja-api skill's wrapper functions directly*: the openclaw skills surface is invoked from agent prompts, not from helper scripts. Capture's classifier is the agent; the helper script is pure Python and doesn't go through openclaw.

---

## R-006 — Calendar account and calendar ID defaults

**Decision**: Default to `--account kent@intentional.biz --calendar primary` for all inbox-routed calendar events in this mission. No calendar-picker logic.

**Rationale**:
- The credential manifest lists `kent@intentional.biz` (owner) and `kentgale@gmail.com` (writer/shared). Routing to the shared account adds an account-decision dimension that isn't required by the spec.
- Kent's primary calendar is where personal + business events flow today; this mission preserves that.

**Alternatives considered**:
- *Account inference by block content* (business → intentional, personal → kentgale): would require additional classifier signals and a domain rule. Out of scope; can be a follow-up.

---

## R-007 — RRULE coverage in the validator

**Decision**: Per spec FR-004, the helper accepts these natural-language patterns and converts to RFC 5545:
- Weekly on a named weekday: "every Tuesday" / "weekly on Tuesday" → `RRULE:FREQ=WEEKLY;BYDAY=TU`
- Biweekly: "every other week" / "biweekly" → `RRULE:FREQ=WEEKLY;INTERVAL=2`
- Monthly on a numeric day: "monthly on the 15th" → `RRULE:FREQ=MONTHLY;BYMONTHDAY=15`
- By-weekday-of-month: "first Monday of the month" → `RRULE:FREQ=MONTHLY;BYDAY=1MO`; "last Friday" → `RRULE:FREQ=MONTHLY;BYDAY=-1FR`

Patterns outside this set return `"missing recurrence"`. The helper does NOT attempt to parse arbitrary recurrence phrases; the LLM's job is to extract the recurrence_phrase, the helper's job is deterministic conversion.

**Rationale**:
- These four patterns cover the trivia-night case (#324) plus the most common natural-language shapes Kent submits.
- Standard library `re` + a small lookup table handle these without any external dependency.
- "Common" was the spec-phase answer (vs. "Conservative" or "Broad" library-based parsing).

**Alternatives considered**:
- *Use `python-dateutil.rrule.rrulestr` for full RFC 5545 parsing*: only useful if the LLM produces RRULE strings directly; it produces natural language. Library doesn't help with the NL→RRULE step.
- *Use `dateparser`*: handles dates, not recurrence patterns.

---

## R-008 — Vikunja recurrence boundary (called out by operator on 2026-06-07)

**Decision**: This mission uses RFC 5545 RRULE strings exclusively for Google Calendar (via `gog --rrule`). It does NOT write recurrence to Vikunja in any form. The plan's "Someday item" routing creates one-off Vikunja tasks with no recurrence — consistent with FR-009.

**Rationale**:
- Vikunja's recurrence model today is `repeat_after` (integer seconds) + `repeat_mode` (enum), not RFC 5545. Native RRULE support is in flight upstream at [go-vikunja/vikunja#2032](https://github.com/go-vikunja/vikunja/pull/2032) but not shipped.
- This mission's calendar events go exclusively to Google Calendar — never to Vikunja. So the substrates do not collide.
- Captured as memory `reference_vikunja_recurrence_model.md` to prevent future confusion.

**Verification**:
- Per the operator-flagged distinction during 2026-06-07 plan-phase clarification.
- go-vikunja/vikunja#2032 confirmed open / not yet merged at the time of writing.

---

## R-009 — Architecture-docs-first lesson (operational, not artifact-shape)

**Decision**: Memory note `feedback_architecture_docs_first.md` recorded. Future plan-phase research consults `docs/design/architecture/data/*.json` FIRST before SSH probing. The architecture JSONs are canonical for "does X exist, where, how is it wired."

**Rationale**: During this plan phase, I missed the gog skill location and OAuth wiring by probing `/home/claude/` only and concluding "gog skill missing." The architecture inventory had the full picture (`/home/linuxbrew/.linuxbrew/bin/gog`, `/usr/lib/node_modules/openclaw/skills/gog/SKILL.md`, `gog-keyring-password` / `openclaw-gateway-env` wiring). Operator flagged the gap explicitly.

---

## Clarifications still parked

None. All spec-phase deferrals and plan-phase open items resolved above.
