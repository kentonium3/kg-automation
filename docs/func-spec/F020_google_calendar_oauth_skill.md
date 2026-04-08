---
title: "F020: gog Google Workspace Skill — Calendar Foundation"
doc_type: func-spec
status: draft
feature: F020
---

# F020: gog Google Workspace Skill — Calendar Foundation

**Version**: 2.0
**Priority**: HIGH
**Type**: Infrastructure
**Recommended Mission Type**: `software-dev`
**Depends on**: F013

**Approach change (v2.0)**: Rather than building a custom `google-calendar` skill
from scratch, this feature adopts `gog` — the official Google Workspace CLI from
OpenClaw's own creator (steipete). `gog` covers Gmail, Calendar, Drive, Contacts,
Sheets, and Docs in a single tool, eliminating the need to build custom skills for
each Google service as Felix grows. **F020 activates Calendar only**; additional
services (Gmail, Drive, etc.) are enabled in future features as needed.

**Constitution approval**: Kent Gale has explicitly approved installation of
`gog` from `openclaw/openclaw` (steipete's repo) — 2026-04-06.

---

## Executive Summary

OAuth2 credentials for Google are established on office2. The remaining work is
installing `gog`, configuring it with existing credentials, writing a thin Felix
SKILL.md wrapper scoped to the personal calendar, and retiring the now-superseded
custom credential files in favour of gog's auth store.

Adopting `gog` instead of a custom skill delivers:
- Calendar access now (F020)
- Gmail, Drive, Contacts, Sheets, Docs available in future features without
  additional OAuth plumbing — just enabling APIs and extending gog's scope

Current gaps:
- ✅ OAuth2 client credentials established on office2 (pre-spec-kitty)
- ✅ OpenClaw confirmed read/write access to both personal and Intentional calendars
- ❌ `gog` not installed on office2
- ❌ `gog` not configured with Kent's Google account
- ❌ No Felix SKILL.md wrapper for agents to use
- ❌ Custom plaintext credential files superseded but not retired
- ❌ `credential-manifest.json` not updated to reflect gog auth store

---

## Problem Statement

**Current State:**
```
office2
├── /data/services/openclaw/secrets/google-calendar-client-id     ← superseded
├── /data/services/openclaw/secrets/google-calendar-client-secret ← superseded
├── /data/services/openclaw/secrets/google-calendar-refresh-token ← superseded
├── scripts/google/authorize-calendar.py  ← superseded (kept for reference)
└── [no gog binary]
    [no gog auth configured]
    [no google-calendar SKILL.md]
```

**Target State:**
```
office2
├── gog binary installed and on PATH
├── gog auth store configured for kentgale@gmail.com (calendar scope)
└── ~/.openclaw/skills/google-calendar/SKILL.md  ← Felix wrapper for gog

docs/
└── runbooks/google-calendar-ops.md  ← operations and setup guide

credential-manifest.json
└── personal-google  ← updated: gog auth store, calendar scope only
```

---

## CRITICAL: Study These Files FIRST

Before implementation, the planning phase MUST read:

1. **gog documentation and source**
   - `https://github.com/steipete/gogcli` — gog source repository; study the
     README for installation options on Linux (office2 is Ubuntu 24.04 LTS)
   - `https://gogcli.sh` — gog homepage
   - The gog SKILL.md from openclaw/openclaw:
     `https://github.com/openclaw/openclaw/blob/main/skills/gog/SKILL.md`
   - Understand the auth flow: `gog auth credentials`, `gog auth add`, `gog auth list`

2. **Existing credentials on office2**
   - `/data/services/openclaw/secrets/google-calendar-client-id`
   - `/data/services/openclaw/secrets/google-calendar-client-secret`
   - `/data/services/openclaw/secrets/google-calendar-refresh-token`
   - These were created for the prior approach. gog needs `client_secret.json`
     (standard Google OAuth2 JSON format). The planning phase must determine
     how to construct the client_secret.json from these stored values, OR
     whether to re-run gog's native auth flow from scratch.

3. **Existing auth script**
   - `scripts/google/authorize-calendar.py` — prior approach; keep for reference
     and to document what it set up. Do not delete.

4. **Vikunja API skill as structural pattern**
   - `scripts/openclaw/skills/vikunja-api/SKILL.md` — Felix SKILL.md wrappers
     in this project are thin instruction documents for agents. The google-calendar
     wrapper follows the same structural conventions.

5. **Credential manifest and ops runbook**
   - `docs/design/architecture/data/credential-manifest.json` — `personal-google`
     entry needs updating to reflect gog auth store
   - `docs/design/architecture/credentials-and-secrets.md` — storage mechanism
     narrative updated in maintenance-2026-04-06; verify gog auth store section
     remains accurate after this feature

---

## Kent's Manual Prerequisites

**Before Claude Code can proceed with FR-2 and beyond, Kent must:**

1. **Verify Google APIs enabled in the Cloud Console** (console.cloud.google.com)
   - For F020 (calendar only): Google Calendar API — confirm it is enabled
   - For future features (enable now to avoid repeat visits):
     - Gmail API → F025+ (email triage)
     - Google Drive API → future Drive integration
     - Google People API → Contacts
     - Google Sheets API → Sheets
     - Google Docs API → Docs
   - Location: APIs & Services → Library → search each by name → Enable

2. **Confirm OAuth consent screen scopes** include Calendar (and others if enabled)
   - APIs & Services → OAuth consent screen → Edit → Scopes
   - Add: `https://www.googleapis.com/auth/calendar`
   - Add future scopes now if enabling additional APIs above

These steps cannot be automated — they require access to the Google Cloud Console
under the Intentional organization account. The Cloud project was created during
initial OAuth setup.

---

## Functional Requirements

### FR-1: Install gog on office2

**What it must do:**
- Install the `gog` binary on office2 such that it is available on the PATH
  for the `claude` user
- office2 runs Ubuntu 24.04 LTS — determine the appropriate install method:
  - Homebrew on Linux (`brew install steipete/tap/gogcli`) if brew is available,
    or can be installed without sudo
  - Build from source (`git clone https://github.com/steipete/gogcli && make`)
    as an alternative if brew is not viable
- Verify: `gog --version` returns a version string

**Business rules:**
- Installation must not require sudo for ongoing use — only the install step
  itself may require elevated access if unavoidable
- The binary must be accessible to the `claude` user (the agent execution account)

**Success criteria:**
- [ ] `gog --version` succeeds as the claude user on office2
- [ ] Install method documented in `docs/runbooks/google-calendar-ops.md`

---

### FR-2: Configure gog with Google Account

**What it must do:**
- Configure gog with Kent's personal Google account (`kentgale@gmail.com`)
  scoped to Calendar service only for this feature
- Use the existing client credentials stored in the office2 secret store to
  construct the `client_secret.json` required by `gog auth credentials`
- Run `gog auth credentials /path/to/client_secret.json`
- Run `gog auth add kentgale@gmail.com --services calendar`
- This step requires an interactive OAuth consent flow — Kent must be present
  at the terminal or a URL must be printed for out-of-band authorization

**Business rules:**
- gog manages its own token store — after auth, the plaintext credential files
  in `/data/services/openclaw/secrets/google-calendar-*` are superseded but
  NOT deleted (kept as reference and fallback)
- Set `GOG_ACCOUNT=kentgale@gmail.com` as a persistent environment variable
  for the claude user to avoid requiring `--account` on every gog call
- Calendar scope only for F020 — additional services added in future features

**Success criteria:**
- [ ] `gog auth list` shows `kentgale@gmail.com` with calendar service
- [ ] `GOG_ACCOUNT` environment variable set for claude user
- [ ] Interactive auth step documented in runbook

---

### FR-3: Felix Google Calendar SKILL.md Wrapper

**What it must do:**
- Create `scripts/openclaw/skills/google-calendar/SKILL.md` — a Felix-specific
  wrapper that teaches agents how to use `gog` for calendar operations, scoped
  to `kentgale@gmail.com` personal calendar exclusively
- This is NOT a copy of gog's own SKILL.md — it is a thin Felix wrapper that:
  - States the personal-only scope constraint explicitly
  - Documents the specific `gog calendar` commands agents should use
  - Specifies `GOG_ACCOUNT=kentgale@gmail.com` / `primary` as the calendar target
  - Includes error handling guidance (token issues, API quota, calendar not found)
  - References the operations runbook for credential rotation

**Covered operations:**
- List upcoming events (date range, max results)
- Get a specific event by ID
- Create an event (title, start/end, description, location)
- Update an event
- Delete an event

**Business rules:**
- Skill operates on `kentgale@gmail.com` / `primary` calendar exclusively
- Skill must NOT use or reference `kent@intentional.biz` calendar
- Agents use `gog calendar` subcommands via `exec` — not raw Google API calls
- Output format: always use `--json` flag for machine-readable responses
- Confirm before creating or deleting events (constitutional Assisted-mode behavior)

**Success criteria:**
- [ ] SKILL.md at `scripts/openclaw/skills/google-calendar/SKILL.md`
- [ ] Skill deployed to `~/.openclaw/skills/google-calendar/SKILL.md` on office2
- [ ] Personal-only scope constraint stated explicitly in skill
- [ ] All five operations documented with working gog commands
- [ ] `--json` output format specified throughout

---

### FR-4: End-to-End Verification

**What it must do:**
- Confirm the full pipeline works by listing the next 5 events on the primary
  personal calendar via the SKILL.md-documented commands
- Confirm no Intentional calendar events appear in the output

**Success criteria:**
- [ ] `gog calendar events primary --max 5 --json` succeeds as claude user
- [ ] Response contains event titles and start times from kentgale@gmail.com
- [ ] No kent@intentional.biz events in output

---

### FR-5: Retire Superseded Files and Update Documentation

**What it must do:**
- Move the three plaintext credential files to an archived location or add a
  `SUPERSEDED-BY-GOG` prefix so their status is clear — do not delete them
- Update `credential-manifest.json`: `personal-google` entry reflects gog auth
  store as storage mechanism
- Update `docs/design/architecture/credentials-and-secrets.md` if the gog auth
  store section needs any correction after actual installation
- Create `docs/runbooks/google-calendar-ops.md` covering:
  - How gog is installed on office2
  - How to re-authorize if the token is revoked (`gog auth add` again)
  - How to add additional Google services in future features
  - How to verify the calendar connection is working
  - Troubleshooting: token expired, wrong account, API not enabled

**Success criteria:**
- [ ] Superseded plaintext files clearly marked or archived (not deleted)
- [ ] `credential-manifest.json` updated with gog storage mechanism
- [ ] `google-calendar-ops.md` runbook created and complete
- [ ] Architecture docs consistent with actual installation

---

## Architecture Documentation Updates

| File | Change |
|------|--------|
| `data/credential-manifest.json` | Update `personal-google` storage to reflect gog auth store; set `updated_by: "F020"` |
| `data/service-inventory.json` | Add `gog` as an installed tool under office2; set `updated_by: "F020"` |
| `credentials-and-secrets.md` | Verify gog auth store section accurate post-install |
| `service-inventory.md` | Add gog entry |

---

## Out of Scope

- ❌ Gmail integration — enabling Gmail API in Cloud Console is a prerequisite
  step Kent performs now; Gmail agent capability is F025+
- ❌ Drive, Contacts, Sheets, Docs — same; APIs enabled now, skills built later
- ❌ Task ↔ calendar event linking — F021
- ❌ Intentional LLC calendar (`kent@intentional.biz`) — separate future feature
- ❌ Deleting the prior `authorize-calendar.py` script — keep for reference
- ❌ Multi-account gog configuration — personal account only for now

---

## Success Criteria

**Complete when:**

### Installation
- [ ] `gog --version` succeeds as claude user on office2
- [ ] `gog auth list` shows `kentgale@gmail.com` with calendar service

### Skill
- [ ] SKILL.md deployed and agents can use `gog calendar` commands
- [ ] Personal-only scope constraint enforced in skill
- [ ] `--json` output throughout

### Verification
- [ ] 5-event listing from primary calendar succeeds
- [ ] No Intentional calendar contamination

### Documentation
- [ ] `google-calendar-ops.md` runbook complete
- [ ] `credential-manifest.json` updated
- [ ] Superseded credential files marked/archived

---

## Architecture Principles

### Adopt over Build

`gog` is maintained by the creator of OpenClaw and covers the full Google
Workspace surface. Building and maintaining a custom skill for each Google
service would be redundant work with worse coverage. The adoption pattern —
install once, extend scope feature by feature — is more durable than the
build-from-scratch pattern.

### Credential Model: gog auth store

gog manages its own token store. This is the correct home for credentials
that gog consumes. The plaintext file pattern (used for `vikunja-api`) remains
appropriate for skills that read tokens directly via `cat` — it is not the
right pattern for OAuth2 tokens that have their own managed refresh lifecycle.

### Thin Wrapper, Not Reimplementation

The Felix SKILL.md does not reimplement gog's functionality. It scopes gog to
Felix's use case: kentgale@gmail.com, calendar only, JSON output, confirm before
mutating. Agents read the wrapper; the wrapper tells them which gog commands to
run. Gog handles auth, token refresh, and API interaction.

---

## Constitutional Compliance

✅ **ClawHub approval**: Kent explicitly approved `gog` installation — 2026-04-06.

✅ **No credentials in code**: gog auth store manages tokens; no secrets
in SKILL.md or committed files.

✅ **Narrow scope**: Calendar only for F020; additional services in future specs.

✅ **Never fail silently**: SKILL.md error handling covers token expiry, quota
exceeded, and API-not-enabled errors.

---

## Risk Considerations

**Risk: gog install on Ubuntu 24.04 is non-trivial**
- gog's primary install is via Homebrew (`steipete/tap/gogcli`). Homebrew
  on Linux is functional but heavier than on Mac.
- Mitigation: Planning phase checks whether building from source
  (`git clone && make`) is simpler on Ubuntu. Either approach is acceptable.

**Risk: Existing refresh token incompatible with gog's auth store**
- gog runs its own OAuth consent flow and manages tokens independently.
  The refresh token in our plaintext files may not be importable.
- Mitigation: Re-running the OAuth consent flow via gog is acceptable and
  expected. The prior credentials are not lost — they remain as plaintext
  files. FR-2 explicitly allows for a fresh auth flow.

**Risk: Calendar API scope insufficient after re-authorization via gog**
- If the OAuth consent screen scopes don't include Calendar, gog auth will
  fail or return permission errors.
- Mitigation: Kent's manual prerequisite (FR-0) confirms scopes before
  FR-2 runs.

---

## Notes for Implementation

**Determine install method first (planning phase):**
Check if Homebrew is available on office2 as the claude user. If not, assess
whether `make install` from source is feasible without sudo for the install
step. Document the chosen approach in the runbook before proceeding.

**Constructing client_secret.json:**
gog's `auth credentials` command expects the standard Google OAuth2 JSON
format: `{"installed": {"client_id": "...", "client_secret": "...", ...}}`.
The planning phase must construct this from the stored credential files and
confirm the exact JSON structure expected by gog before running the command.
The constructed JSON should be written to a temporary file and not committed.

**GOG_ACCOUNT environment variable:**
Set in `/home/claude/.profile` or `/home/claude/.bashrc` so it persists across
sessions and cron invocations. Confirm it is visible to OpenClaw skill `exec`
calls in the agent execution environment.

---

## Revision History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-04-06 | Initial draft — custom curl-based google-calendar skill |
| 1.1 | 2026-04-06 | Pre-spec-kitty credential establishment noted; scope clarified to kentgale@gmail.com |
| 2.0 | 2026-04-06 | Complete rewrite: adopt gog instead of building custom skill; credential model updated to gog auth store |

---

**END OF SPECIFICATION**
