# Feature Specification: Felix Calendar Helper

**Mission**: felix-calendar-helper-01KX4H3C
**Friendly name**: Felix Calendar Helper
**Status**: Draft
**Created**: 2026-07-09
**Source**: GitHub issue kentonium3/kg-automation#699 (converts accepted RFC #681)

## Overview

Felix reaches Google Calendar today through OpenClaw's `gog` skill — an
agent-to-agent path that is fragile and, for inbox-driven scheduling, silently
broken (#679). This feature gives Felix a **Felix-owned Calendar helper** that
talks to Google directly and deterministically, invoked by an agent with a
single command. A thin **judgment layer** (the reshaped `felix-admin-calendar`
agent) handles natural-language interpretation and hands a structured request to
the helper.

The helper is **multi-account-ready from day one** — it defaults to Kent's real
personal calendar (`kentgale@gmail.com`) and can add the `intentional.biz`
account later with no code change. This is the first concrete delivery of
accepted RFC #681; the authentication model and connectivity are already proven
(personal `@gmail` account + an "In production" OAuth app yields a durable
authorization; live connectivity probe was green on 2026-07-09).

## User Scenarios & Testing

### Scenario 1 — Inbox note becomes a calendar event (closes #679)

- **Actor**: Felix inbox-capture pipeline (triggered by a Kent voice/text note).
- **Trigger**: A note in the vault inbox expresses a calendar intent
  ("dentist Tuesday at 3pm").
- **Happy path**: The capture path recognizes the calendar intent and reaches the
  calendar through a **deterministic helper call** — no agent-to-agent
  delegation. An event is created on Kent's personal `primary` calendar and the
  note is marked processed.
- **Exception**: If the note's date/time is ambiguous, the judgment layer asks
  Kent exactly one clarifying question (via the normal conversational channel)
  before creating the event; it never guesses silently.

### Scenario 2 — Conversational scheduling

- **Actor**: Kent, conversing with Felix.
- **Trigger**: "Felix, put lunch with Sam on my calendar next Thursday noon."
- **Happy path**: The judgment layer parses the natural-language request into a
  structured event (title, start, end, timezone), calls the helper, and confirms
  the created event back to Kent.
- **Exception**: Missing end time → the layer applies a sensible default
  (e.g. 1 hour) and states the assumption in its confirmation.

### Scenario 3 — Read / update / cancel

- **Actor**: The judgment layer, on Kent's behalf.
- **Trigger**: "What's on my calendar tomorrow?" / "Move that to 4pm." / "Cancel it."
- **Happy path**: The helper lists events in the requested window; updates the
  target event's fields by its identifier; or deletes/cancels it. Each operation
  is a single deterministic helper invocation.

### Scenario 4 — Authorization failure is fail-safe

- **Actor**: The helper.
- **Trigger**: The stored authorization is expired/revoked (refresh fails).
- **Happy path**: The helper **fails safe** — it emits a clear, actionable error
  and a non-zero exit, and performs no calendar mutation. The agent surfaces the
  error rather than reporting a false success or taking a wrong action
  (no-silent-fallback doctrine, #675/#683).

### Scenario 5 — Second account, no code change

- **Actor**: Operator (future).
- **Trigger**: The `intentional.biz` account is later added.
- **Happy path**: Dropping that account's credentials into its own per-account
  location and passing its account name is sufficient; no helper code changes.

### Edge cases

- Empty result windows (no events) are reported as an explicit empty result,
  distinguishable from an error.
- An event identifier that no longer exists on update/delete surfaces a clear
  not-found error, not a silent success.
- **Attendees never silently email people.** Invitations are suppressed by
  default; the inbox path rejects attendees unless explicitly confirmed — a
  personal-calendar note must not send mail to external people as a side effect.
- **Retry safety**: if event creation succeeds but the follow-up (marking the
  note processed / logging) fails, a retry must not create a duplicate event.
  Keyed (inbox) creations carry a stable source key and return the existing event
  on retry.
- **Recurring events (v1 boundary)**: creating recurring events is supported;
  editing/canceling a *single occurrence* of a recurring series is out of scope
  for v1 and returns a clear error (whole-series operations act on the event id).
- Timezone: when a note omits a timezone, the default operating timezone
  (America/New_York) is applied and stated.

## Domain Language

| Canonical term | Meaning | Avoid |
|---|---|---|
| **account** | A named Google identity Felix can act as, with its own credential set. Default account name: `personal`. | "user", "profile" |
| **calendar helper** | The deterministic CLI that performs calendar I/O directly against Google. | "calendar script", "gog" |
| **judgment layer** | The reshaped `felix-admin-calendar` agent — natural-language interpretation and clarification only; no direct calendar I/O and no `gog`. | "calendar agent" (ambiguous) |
| **event** | A calendar entry: title, start, end, timezone, description, location, optional attendees, identifier. | "appointment", "meeting" |
| **primary calendar** | The account's default calendar; the default target. | "main calendar" |

## Requirements

### Functional Requirements

| ID | Requirement | Status |
|---|---|---|
| FR-001 | The calendar helper creates an event (title, start, end, timezone, and optional description, location, attendees) on the selected account's target calendar (default `primary`) via a single command, and returns the created event's identifier. | Draft |
| FR-002 | The calendar helper lists/finds events within a requested time window on the selected account and calendar, returning at minimum each event's identifier, title, start, and end. | Draft |
| FR-003 | The calendar helper updates an existing event's mutable fields, addressed by its identifier, on the selected account and calendar. | Draft |
| FR-004 | The calendar helper deletes/cancels an existing event, addressed by its identifier, on the selected account and calendar. | Draft |
| FR-005 | The calendar helper selects the target account by an explicit account selector (default `personal`), resolving credentials from a per-account credential store; adding a new account requires only new credentials in that store, with no code change. | Draft |
| FR-006 | The calendar helper loads and auto-refreshes the account's stored authorization; on any authorization failure it fails safe — emitting a clear, actionable error and a non-zero result, and performing no calendar mutation and no fallback action. | Draft |
| FR-007 | The calendar helper conforms to the project helper-script CLI contract: subcommand interface, documented exit codes, and a machine-parseable `SUMMARY:` result line on stdout. | Draft |
| FR-008 | The `felix-admin-calendar` agent is reshaped to a judgment-only layer: it interprets natural-language date/time/intent, performs at most one clarification round on ambiguity, emits a structured helper request, and makes no `gog` calls on the calendar surface. | Draft |
| FR-009 | Inbox capture reaches the calendar via a deterministic helper call (directly or through the reshaped judgment layer) with no agent-to-agent delegation; an inbox note with a calendar intent results in a created event end-to-end (closes #679). | Draft |
| FR-010 | The calendar helper is deployed to office2 through the manifest pipeline (including provisioning its dedicated dependency venv); per-account credentials are staged in their canonical location; and the `openclaw.json` change is rebaselined per the audited-surface protocol. | Draft |
| FR-011 | Architecture documentation is synchronized as part of this work: credential/identity records (new personal Google authorization), data-flow records (calendar now flows helper→Google directly, not through `gog`), service inventory (external Calendar API dependency), and navigation/roadmap entries (INDEX, capability roadmap, #681/#699/#679 status), as applicable per `signal-to-doc-map.json`. | Draft |

### Non-Functional Requirements

| ID | Requirement | Threshold | Status |
|---|---|---|---|
| NFR-001 | A single calendar operation returns promptly under normal connectivity, and surfaces a timeout error rather than hanging. | Single-event create/read/update/delete returns within 10 s under normal connectivity; on exceeding it, a clear timeout error is surfaced. | Draft |
| NFR-002 | The authorization model requires no routine interactive re-authentication. | Zero interactive re-auths required across a ≥7-day continuous operating window (the durability RFC #681 proved). | Draft |
| NFR-003 | The helper's behavior is verified without live network. | 100% of helper subcommands (create/list/update/delete) have ≥1 passing contract test with the Google API mocked; the authorization-failure path (FR-006) has an explicit failing-auth test; the suite runs in CI with no network. | Draft |
| NFR-004 | No credential material is committed or exposed. | Repo scan finds zero credential files/secrets; token and client-secret paths are gitignored; on-disk credentials are `0600` in a `0700` per-account directory. | Draft |
| NFR-005 | Every helper invocation is observable and unambiguous. | Each invocation emits a structured success/failure result with a reason; failures are distinguishable from empty results by the consuming agent. | Draft |

### Constraints

| ID | Constraint | Status |
|---|---|---|
| C-001 | The authentication substrate is fixed by RFC #681: personal `kentgale@gmail.com`, GCP project `felix-personal` (External + "In production"), Desktop OAuth client. This mission consumes that model; it does not change it. | Active |
| C-002 | Calendar scope only (a "sensitive", not "restricted", scope). No Gmail/Drive scopes — mail is F024, a later RFC #681 phase. | Active |
| C-003 | Deploy to office2 flows only through the manifest pipeline (`deploys/queued/<name>.yaml`), except the documented per-account credential staging and the required rebaseline. | Active |
| C-004 | `gog` is not retired by this mission; it retains its other surfaces until they migrate, and the #572 `gog` re-auth residual stays open. | Active |
| C-005 | Change is Tier 2 + Tier 3: confirm a recent Restic snapshot before deploy (Tier 2 state/credentials). The **only** rebaseline-triggering surface is the `openclaw.json` change (removing the `gog` skill); agent-prompt (AGENTS.md) edits are an *unmonitored* audited surface (no rebaseline), and the google dependencies live in a dedicated venv (not `requirements.txt`), so the pip-packages baseline is untouched. | Active |
| C-006 | Adding the second (`intentional.biz`) account is out of scope for implementation here; the design must not preclude it. | Active |
| C-007 | office2 is python3-only; the helper is invoked in module form (`python3 -m …`) to satisfy package imports and avoid the bare-`python` exit-127 class (#682). | Active |

## Success Criteria

- **SC-001**: Felix creates, reads, updates, and deletes an event on Kent's
  personal calendar through single commands, and each change is visible in
  Google Calendar.
- **SC-002**: An inbox note expressing a calendar intent results in a correctly
  scheduled event with no manual intervention (closes #679), verified by a live
  end-to-end run on office2.
- **SC-003**: The calendar judgment layer performs no `gog` calls on the calendar
  surface, verified by inspection of its prompt and post-deploy logs.
- **SC-004**: An injected authorization failure produces a clear surfaced error
  and no calendar mutation — no false success and no wrong action.
- **SC-005**: Configuring a second account name resolves to its own credential
  location and requires no helper code change (demonstrated with a dry
  configuration).
- **SC-006**: The system operates for at least 7 continuous days without any
  interactive re-authentication.

## Key Entities

- **Account** — a named Google identity Felix acts as; has its own credential
  set; default `personal`.
- **Credential store** — per-account authorization material (client secret +
  stored token) in a canonical per-account location.
- **Calendar** — a Google calendar belonging to an account; `primary` by default.
- **Event** — title, start, end, timezone, description, location, optional
  attendees, and an identifier.
- **Calendar helper** — the deterministic CLI performing calendar I/O.
- **Judgment layer** — the reshaped `felix-admin-calendar` agent.

## Assumptions

- Default operating timezone is **America/New_York** (Kent is ET) unless a note
  specifies otherwise.
- Default target calendar is the account's **primary** calendar.
- Attendees are an optional field; typical inbox/personal events have none.
  Sending invitations to external people is supported but not the default path.
- Personal credentials are already staged at
  `~/.config/felix/google/personal/` (from RFC #681); the intentional.biz
  credentials remain untouched.
- A default event duration (e.g. 1 hour) is applied when a note gives a start
  but no end; the assumption is stated back to Kent.

## Dependencies

- **RFC #681** (accepted) — authentication model and proven connectivity.
- **Google Calendar API** — free within Kent's usage quota.
- **`docs/design/helper-script-conventions.md`** — CLI helper contract.
- **`docs/design/engineering-principles.md`** — deterministic-vs-judgment split.
- **felix-deployer manifest pipeline** — deploy + rebaseline mechanics.
- **Closes #679** (inbox→calendar); reshapes **#680**; simplifies **#675**
  Foundation 0 Google-surface containment; **#572** residual stays open.

## Documentation Synchronization Requirement (DIR-014)

This mission MUST, as part of its merge, update the affected architecture and
navigation documents identified via
`docs/design/architecture/data/signal-to-doc-map.json` for the change classes
`credential-added-or-modified`, `data-flow-added-or-modified`, and the
agent-prompt change class — at minimum the credentials/identity JSON + markdown,
data-flows JSON + markdown, service inventory, a calendar-helper runbook,
`docs/INDEX.md`, and the capability-roadmap / issue status for #681/#699/#679.
