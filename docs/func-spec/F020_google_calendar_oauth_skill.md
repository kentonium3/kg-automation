---
title: "F020: Google Calendar OAuth Skill"
doc_type: func-spec
status: draft
feature: F020
---

# F020: Google Calendar OAuth Skill

**Version**: 1.1
**Priority**: HIGH
**Type**: Infrastructure
**Recommended Mission Type**: `software-dev`
**Depends on**: F013 (structured tasks exist to link to calendar events)

**Implementation note (pre-spec-kitty)**: OAuth2 credentials are already established
outside the spec-kitty workflow. See Credential State below.

---

## Executive Summary

OAuth2 credentials are established and OpenClaw can already read and write to
Google Calendar. The remaining work is the skill layer: a `google-calendar` skill
that teaches OpenClaw agents to use the API consistently, and the supporting
architecture documentation updates.

**Calendar scope — personal only**: This feature and all downstream calendar
features (F021–F023) concern **kentgale@gmail.com exclusively**. The Google Cloud
project lives under the Intentional Google organization (`kent@intentional.biz`),
and OpenClaw has visibility into both the personal and Intentional calendars.
However, agents must only read and write the personal calendar (`kentgale@gmail.com`)
unless explicitly directed otherwise in a future feature spec. The Intentional
calendar (`kent@intentional.biz`) is visible but out of scope.

Current gaps:
- ✅ OAuth2 credentials established on office2 (completed pre-spec-kitty)
- ✅ OpenClaw confirmed reading and writing both personal and Intentional calendars
- ❌ No `google-calendar` skill exists for OpenClaw agents
- ❌ Agents have no consistent, documented API interaction pattern
- ❌ `credential-manifest.json` entry for `personal-google` remains as `planned`

This spec delivers: a one-time OAuth2 authorization flow for Kent's personal Google
Calendar, a persistent refresh token stored on office2, and a `google-calendar` skill
that teaches OpenClaw agents to list events, query availability, and create, update,
and delete events via the Google Calendar API v3.

---

## Problem Statement

**Current State:**
```
office2 credential store (/data/services/openclaw/secrets/)
├── vikunja-api          ✅
├── anthropic            ✅
└── google-calendar-*    ❌ DOESN'T EXIST

OpenClaw skills (~/.openclaw/skills/)
├── vikunja-api/         ✅
├── task-intelligence/   ✅
├── escalation/          ✅ (F019)
└── google-calendar/     ❌ DOESN'T EXIST

Downstream features blocked:
├── F023 — Task ↔ calendar event linking    ❌ blocked on this
├── F024 — Daily briefing heartbeat         ❌ blocked on this
└── F025 — Level 1-2 escalation heartbeat   ❌ blocked on this
```

**Target State:**
```
office2 credential store
├── google-calendar-client-id        ✅ already present
├── google-calendar-client-secret    ✅ already present
└── google-calendar-refresh-token    ✅ already present

OpenClaw skills
└── google-calendar/SKILL.md         ✅ Teaches agents to use Calendar API v3
                                        PERSONAL CALENDAR ONLY (kentgale@gmail.com)

credential-manifest.json
└── personal-google entry            ✅ Updated from planned → active with storage paths

Downstream features
├── F021 — Task ↔ calendar event linking    ✅ unblocked
├── F022 — Daily briefing heartbeat         ✅ unblocked
└── F023 — Level 1-2 escalation heartbeat   ✅ unblocked
```

---

## Credential State (Pre-Spec-Kitty Establishment)

The following credentials were established manually before this spec ran:

| File | Status |
|------|--------|
| `/data/services/openclaw/secrets/google-calendar-client-id` | ✅ Present, mode 600 |
| `/data/services/openclaw/secrets/google-calendar-client-secret` | ✅ Present, mode 600 |
| `/data/services/openclaw/secrets/google-calendar-refresh-token` | ✅ Present, mode 600 |

The Google Cloud project is hosted under the Intentional Google organization
(`kent@intentional.biz`). OpenClaw has confirmed read/write access to both
`kentgale@gmail.com` (personal) and `kent@intentional.biz` (Intentional) calendars.
**This feature and all downstream features target `kentgale@gmail.com` only.**

FR-1 (Google Cloud project setup) and FR-2 (credential storage) from the original
spec are complete. FR-3 (authorization script) is also complete — `scripts/google/authorize-calendar.py`
was run and produced the stored refresh token.

---

## CRITICAL: Study These Files FIRST

Before implementation, the planning phase MUST read:

1. **Existing credential patterns**
   - `docs/design/architecture/data/credential-manifest.json` — the `personal-google`
     planned credential entry is the target; see the `vikunja-api` entry as the
     pattern for how stored credentials are documented
   - `/data/services/openclaw/secrets/` on office2 — credentials are already present

2. **Vikunja API skill as the pattern reference**
   - `scripts/openclaw/skills/vikunja-api/SKILL.md` — this is the exact structural
     pattern the google-calendar skill must follow: health check, authentication,
     operations, error handling, usage examples
   - Study the auth pattern specifically — the vikunja-api skill reads a token from
     a file at runtime; the google-calendar skill does the same with a refresh-token
     exchange step added

3. **Google Calendar API v3 documentation**
   - `https://developers.google.com/calendar/api/v3/reference` — authoritative
     reference for all endpoints used in this feature
   - `https://developers.google.com/identity/protocols/oauth2` — OAuth2 flow
   - Key resource: `Events: list`, `Events: insert`, `Events: update`, `Events: delete`
   - Key resource: `Calendars: get`, `CalendarList: list`

4. **OpenClaw skill deployment pattern**
   - `docs/runbooks/openclaw-ops.md` — how skills are deployed to office2
   - `docs/runbooks/vikunja-ops.md` "Update Skill on office2" section — the
     `cat >` deployment pattern applies identically here

5. **Architecture change-control protocol**
   - `docs/design/architecture/change-control.md` — this feature adds a credential
     and a service integration; architecture docs must be updated per the protocol

---

## OAuth2 Setup Model

Google Calendar requires OAuth2 with a refresh token for server-side automation.
The setup is a one-time manual flow followed by fully automated token refresh.

### One-time setup (human-in-the-loop required)

1. Kent creates a Google Cloud project with Calendar API enabled and generates
   OAuth2 client credentials (client ID and client secret) in the Google Console
2. Client ID and client secret stored on office2 in the credential store
3. An authorization script generates the OAuth2 consent URL
4. Kent opens the URL in a browser, selects the personal Google account, and
   approves Calendar access
5. The script exchanges the authorization code for an access token + refresh token
6. Refresh token stored on office2 in the credential store
7. Access token is ephemeral — never stored, always obtained by refreshing

### Automated token refresh (no human required)

The google-calendar skill includes a token refresh procedure:
1. Read client ID, client secret, and refresh token from the credential store
2. POST to `https://oauth2.googleapis.com/token` with `grant_type=refresh_token`
3. Receive a fresh access token (valid 3600 seconds)
4. Use the access token for all Calendar API calls in that session

The refresh token is long-lived and persists until explicitly revoked. The skill
handles the refresh transparently — agents call the skill and receive calendar data;
the token exchange happens inside the skill's auth procedure.

### OAuth2 scope

Request only the minimum scope needed:
- `https://www.googleapis.com/auth/calendar` — full read/write access to all
  calendars on the account

A read-only scope (`calendar.readonly`) would be insufficient because agents
must be able to create events (task↔event linking, time-blocking). Full calendar
scope is appropriate given the use cases.

---

## Functional Requirements

### FR-1: Google Cloud Project and OAuth2 Credentials ✅ COMPLETE

Completed pre-spec-kitty. Google Cloud project under Intentional organization,
Calendar API enabled, Desktop app OAuth2 credentials generated. Client ID,
client secret, and refresh token stored on office2.

---

### FR-2: Credential Storage on office2 ✅ COMPLETE

All three credential files present at `/data/services/openclaw/secrets/` with
mode 600. See Credential State section above.

---

### FR-3: OAuth2 Authorization Script ✅ COMPLETE

`scripts/google/authorize-calendar.py` exists and was successfully run.
Refresh token is stored and verified working.

---

### FR-4: Google Calendar Skill

**What it must do:**
- Create `scripts/openclaw/skills/google-calendar/SKILL.md` following the exact
  structural pattern of the vikunja-api skill
- Teach agents to perform the following operations using the Google Calendar API v3:
  - **Token refresh** — exchange refresh token for access token (prerequisite to all calls)
  - **List calendars** — enumerate calendars on the account to resolve the primary
    calendar ID and any named calendars
  - **List events** — retrieve events in a date range from a specified calendar
  - **Get event** — retrieve a single event by ID
  - **Create event** — create a new calendar event with title, time, description,
    and optional attendees
  - **Update event** — modify an existing event
  - **Delete event** — remove an event

**Business rules:**
- All API calls use `curl` via the `exec` tool, consistent with vikunja-api pattern
- Token refresh must be performed at the start of every agent session that uses
  this skill — access tokens expire after 3600 seconds
- Never log or print the access token, client secret, or refresh token values
- The skill must include the full token refresh procedure, not just the API calls
- Error handling must follow the vikunja-api pattern: pre-flight validation,
  HTTP error responses, halt-on-ambiguity

**Calendar scope — PERSONAL ONLY:**
- This skill operates on `kentgale@gmail.com` exclusively
- The canonical calendar ID is `primary` — this resolves to the primary calendar
  of whichever account authorized the OAuth token (kentgale@gmail.com)
- The skill must NOT read from or write to `kent@intentional.biz` calendar
- If an agent session somehow surfaces the Intentional calendar, the skill must
  ignore it and operate on `primary` only
- Future access to the Intentional calendar requires a separate feature spec and
  a separate credential (`intentional-google`)

**Success criteria:**
- [ ] Skill written at `scripts/openclaw/skills/google-calendar/SKILL.md`
- [ ] Skill covers all seven operations: token refresh, list calendars, list events,
  get event, create event, update event, delete event
- [ ] Skill includes complete token refresh procedure with credential file paths
- [ ] Error handling covers auth failures, 403, 404, network errors
- [ ] Skill deployed to office2 at `~/.openclaw/skills/google-calendar/SKILL.md`
- [ ] Skill follows vikunja-api structural pattern exactly

---

### FR-5: End-to-End Verification ✅ PARTIALLY COMPLETE

OpenClaw has already confirmed read/write access to both calendars. The
verification step for this spec is confirming the **skill itself** (once written)
can list events via the documented curl pattern — not just that the API works.

### FR-5: Skill Verification

**What it must do:**
- Verify the complete credential + skill pipeline works end-to-end by running
  a read-only test: list the next 5 events on the primary calendar
- The test must be run via Claude Code using `ssh office2-claude` to confirm the
  skill works in the actual agent execution environment
- Any errors in the token refresh, API call, or response parsing must be resolved
  before the feature is accepted

**Success criteria:**
- [ ] `google-calendar` skill lists next 5 events from primary calendar successfully
- [ ] Token refresh completes without errors
- [ ] Response includes event titles and start times
- [ ] No credentials appear in output

---

### FR-6: Operations Runbook

**What it must do:**
- Create `docs/runbooks/google-calendar-ops.md` covering:
  - One-time setup steps (Google Cloud Console steps Kent must perform)
  - How to run the authorization script
  - How to verify the credential is working
  - How to rotate the refresh token (re-run authorization script)
  - Troubleshooting: token expired, API quota exceeded, wrong calendar ID

**Success criteria:**
- [ ] Runbook exists and covers all topics
- [ ] Google Cloud Console steps documented with enough detail for Kent to follow
  without further guidance

---

## Architecture Documentation Updates

F022 adds OAuth credentials and a new external API integration.

### JSON Updates Required

| File | Change |
|------|--------|
| `data/credential-manifest.json` | Update `personal-google` from `planned_credentials` to `credentials`; add storage paths, used_by, deployed_by |
| `data/service-inventory.json` | Add `google-calendar-api` integration entry under openclaw-gateway; set `updated_by: "F022"` |
| `data/data-flows.json` | Add Google Calendar API as an external data source; data flow: office2 → Google Calendar API (read/write events) |

### Markdown Updates Required

| File | Change |
|------|--------|
| `service-inventory.md` | Add Google Calendar API integration under OpenClaw external integrations |
| `credentials-and-secrets.md` | Add personal-google OAuth credential section |
| `data-flows.md` | Add Google Calendar data flow |

**Success criteria:**
- [ ] All JSON files updated with `updated_by: "F022"`
- [ ] `personal-google` moved from `planned_credentials` to `credentials` in manifest
- [ ] Markdown views match JSON sources

---

## Out of Scope

- ❌ Task ↔ calendar event linking — F023; that feature builds on this one
- ❌ Daily briefing with calendar context — F024
- ❌ Calendar-aware escalation heartbeat — F025
- ❌ Intentional LLC Google Workspace calendar — separate credential (`intentional-google`)
  planned but not in this feature; personal calendar only
- ❌ Google Meet / video conferencing integration — not needed at basic level
- ❌ Calendar event reminders or notifications — out of scope for the skill layer
- ❌ Recurring event creation — skill documents the API capability but agents
  are not required to use it in this feature; complex recurrence rules are future scope
- ❌ Two-way sync with Vikunja tasks — F023

---

## Success Criteria

**Complete when:**

### OAuth Setup
- [ ] Client ID and client secret stored on office2 (mode 600)
- [ ] Authorization script runs and produces authorization URL
- [ ] Kent completes authorization flow
- [ ] Refresh token stored on office2 (mode 600)

### Skill
- [ ] `google-calendar` skill written and deployed to office2
- [ ] All seven operations documented with working curl examples
- [ ] Token refresh procedure included and tested
- [ ] Error handling complete

### Verification
- [ ] Skill lists next 5 events from primary calendar (kentgale@gmail.com) via documented curl pattern
- [ ] Token refresh procedure in skill executes correctly
- [ ] Intentional calendar events do not appear in output

### Documentation
- [ ] `docs/runbooks/google-calendar-ops.md` complete
- [ ] `credential-manifest.json` updated (planned → active)
- [ ] `service-inventory.json` updated
- [ ] `data-flows.json` updated
- [ ] Markdown views updated

---

## Architecture Principles

### Refresh Token as the Stored Credential

Google OAuth2 access tokens expire after one hour. Storing them persistently is
pointless and a mild security liability. The refresh token is the persistent
credential — long-lived, revocable, and scopable. The access token is ephemeral:
obtained at session start, used, and discarded. This is the correct pattern for
automated server-side Google API use.

### Minimum Scope

The `calendar` scope (full read/write) is the minimum that supports the
downstream use cases (creating events for task↔calendar linking, reading events
for briefings). A narrower `calendar.readonly` scope would require re-authorization
when write capability is needed. Request the right scope once.

### Same Credential Store Pattern

Google Calendar credentials follow the same layout as `vikunja-api`: plain text
files in `/data/services/openclaw/secrets/`, owned by claude, mode 600. No new
patterns, no new tooling. Consistency with the existing credential architecture
is worth more than any marginal optimization.

### Skill as the API Abstraction Layer

Agents never interact with the Google Calendar API directly from their AGENTS.md
standing orders — they use the skill. The skill abstracts the token refresh,
URL construction, response parsing, and error handling. This means changes to
the authentication model or API version are made in one place (the skill) rather
than in every agent that uses calendar access.

---

## Constitutional Compliance

✅ **No credentials in code**: All credential values read at runtime from
`/data/services/openclaw/secrets/` — never hardcoded or logged.

✅ **Narrow scope**: This feature delivers credential setup and the skill.
It does not build any calendar-using agent behaviors — those are F023–F025.

✅ **Never fail silently**: Token refresh failures, API errors, and network
issues are all surfaced explicitly in the skill's error handling section.

✅ **Privacy is absolute**: `02-Growth/_private/` content is not involved.
Calendar events are Kent's personal data; the skill reads and writes only what
agents are explicitly directed to access.

---

## Risk Considerations

**Risk: Google OAuth consent screen requires app verification for external apps**
- If the Cloud project is set up with "External" user type, Google may limit
  access to test users until the app is verified.
- Mitigation: Set the OAuth consent screen to "Internal" if using Google Workspace,
  or add Kent's personal account as a test user for an external project. The
  authorization script does not need to be a published app.

**Risk: Refresh token revoked without warning**
- Google revokes refresh tokens if the account password changes, security
  review triggers, or the token is unused for 6+ months.
- Mitigation: The runbook (FR-6) documents the re-authorization procedure.
  The skill's error handling surfaces token revocation (HTTP 401 with
  `invalid_grant` error) clearly.

**Risk: API quota exceeded**
- Google Calendar API has per-user quotas. Normal Felix agent use is well
  within limits, but runaway agents could hit them.
- Mitigation: Skill documents the quota error response (HTTP 429). No
  automated retry — halt and report.

**Risk: Authorization script fails on office2 (no browser available)**
- The interactive OAuth2 flow requires a browser to open the consent URL.
  office2 has no GUI.
- Mitigation: The script prints the authorization URL for Kent to open on
  any device. The authorization code can be pasted back into the script
  (manual redirect approach). This is a one-time setup step.

---

## Notes for Implementation

**Pattern Discovery (Planning Phase):**
- Study `scripts/openclaw/skills/vikunja-api/SKILL.md` section by section before
  writing the google-calendar skill — match the structure exactly
- Study `/data/services/openclaw/secrets/vikunja-api` permissions for the
  credential store file layout
- Review Google Calendar API v3 reference for Events and CalendarList resources
  before writing skill curl examples — verify endpoint signatures at planning time

**Authorization script approach:**
- The simplest approach for office2: print the auth URL, wait for Kent to paste
  the authorization code back into the terminal. No localhost server needed.
- Python's `google-auth-oauthlib` library handles the OAuth2 flow cleanly, but
  a pure stdlib approach using `urllib` is also viable — planning phase decides

**Skill token refresh pattern:**
- The refresh call is a `curl -X POST` to `https://oauth2.googleapis.com/token`
  with `client_id`, `client_secret`, `refresh_token`, and `grant_type=refresh_token`
- The response contains `access_token` — capture it as a shell variable for the
  remainder of the session, never write it to disk

---

**END OF SPECIFICATION**
