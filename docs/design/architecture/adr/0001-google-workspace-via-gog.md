---
title: ADR-0001 — Google Workspace integration via `gog` CLI
doc_type: reference
status: approved
owners: ["@kentonium3"]
last_updated: '2026-05-13'
version: v1.0
audience: agents_and_humans
tags: [120, 100, 164, 165]
---

# ADR-0001 — Google Workspace integration via `gog` CLI

**Status**: Approved
**Date**: 2026-05-13
**Deciders**: Kent Gale
**Closes**: Phase 1 (Research) of [#100](https://github.com/kentonium3/kg-automation/issues/100); materially unblocks [#120](https://github.com/kentonium3/kg-automation/issues/120), [#164](https://github.com/kentonium3/kg-automation/issues/164), [#165](https://github.com/kentonium3/kg-automation/issues/165)

## Context

Felix's Executive Assistant capability area requires programmatic access to Kent's Google Workspace — Calendar, Gmail, Drive, Contacts, Sheets, Docs. This is the foundation for multiple downstream user stories:

- Morning calendar briefings (#164 US-01)
- Look-ahead alerts for upcoming events needing preparation (#164 US-02)
- Email→calendar automation (#164 US-03)
- Travel time allocation (#164 US-06)
- Email triage, drafting, label management (#165, #120)
- Task ↔ calendar event linking (#117)
- Daily briefing heartbeat (#118)

Issue #100 left the integration substrate explicitly open and required research before picking an approach. The research-phase options were:

| Option | Description |
|---|---|
| A: `gog` CLI | steipete's Google Workspace CLI; bundled as an OpenClaw skill ("needs setup"); covers all six target services |
| B: `gcalcli` | Established Python CLI; calendar-only; ClawHub skill `brainz-calendar` wraps it |
| C: Direct Google Calendar API | Python `google-api-python-client`; maximum flexibility; no CLI dependency |
| D: MCP Google Calendar | Claude Code MCP tools; unclear availability in OpenClaw agent context |
| E: ClawHub community skills | `afrexai-email-to-calendar`, `gws-calendar-agenda`, others; service-specific |

Prior to this ADR, the existing state on office2 was:

- OAuth Client ID + Secret + Calendar-scoped refresh token at `/data/services/openclaw/secrets/google-calendar-*` (created 2026-04-06 to 2026-04-13)
- Calendar-scoped `scripts/google/authorize-calendar.py` (April 13)
- `gog` SKILL.md bundled with OpenClaw at `/usr/lib/node_modules/openclaw/skills/gog/SKILL.md`, status "needs setup" (binary not installed)
- No actual API calls being made; credentials unused since creation

## Decision

**Adopt option A: `gog` CLI as the Google Workspace integration substrate.** Install the binary via Linuxbrew (`brew install steipete/tap/gogcli`). Use gog's native auth flow (`gog auth credentials <client_secret.json>` + `gog auth add <email> --services ... --remote`) to mint a single refresh token covering all six target services. The existing Calendar-only credentials become legacy; gog manages its own keyring.

## Consequences

### Positive

- **Single skill covers all six services.** One install, one OAuth client, one refresh token. The video referenced below confirms the install path and OAuth flow; the gog CLI's `--services <list>` flag explicitly enables scope-aware refresh-token mint.
- **Designed for agent use.** gog ships an `agent` subcommand tree, agent-safety flags (`--gmail-no-send`, `--no-input`, `--dry-run`, `--force`), JSON output (`-j`), stable plain output (`-p`), and a machine-readable command schema (`gog schema`). The maintainer (steipete) is explicit about AI-agent use cases.
- **Headless OAuth path.** `gog auth add ... --remote` prints the consent URL for the operator to open in a browser and accepts the callback URL pasted back at the terminal — exactly the flow office2 needs as a headless server with no display.
- **OpenClaw integration is free.** `gog` is already a bundled OpenClaw skill (SKILL.md present, just "needs setup"). Once the binary is installed, `openclaw skills info gog` flips to ✓ Ready and the skill is automatically discoverable by Felix agents via OpenClaw's standard skill mechanism. No wrapper or custom helper to write.
- **Community maintenance.** Tens of thousands of OpenClaw users exercise gog daily. Bug fixes, breaking-change adaptation, and Google API churn are absorbed upstream rather than landing on Kent's plate.
- **CLI ergonomics.** Felix agents invoke a documented command surface (per SKILL.md) rather than constructing API request bodies. Easier to write agent prompts; easier to debug operationally; matches the existing skill pattern (whisper, vikunja-api, etc.).
- **Extensibility beyond Workspace.** gog covers 20+ Google services including Chat, Drive, Sheets, Docs, Slides, Meet, Apps Script, Analytics, Search Console, YouTube. Future Felix capabilities that need any of these inherit the same auth + invocation pattern.

### Negative

- **Linuxbrew dependency on office2.** ~8–10 GB disk footprint (portable Ruby + bottled GCC toolchain + glibc + dependencies — the cost of cross-distro binary portability). Adds a parallel package manager that the operator must remember exists. Mitigated by office2's 2.7 TB `/data` partition (footprint is noise) and Kent's expressed desire for brew-style ergonomics on Linux.
- **Third-party tap dependency.** `gog` lives in `steipete/tap`, not `homebrew-core`. If the maintainer abandons the project, the tap could go stale. Mitigated by gog's active community use and the fact that the source is available — could be re-tapped or forked.
- **Existing Calendar-only credentials become orphaned.** The April-2026 work (client_id, client_secret, refresh_token files, `authorize-calendar.py`) is superseded. Marked deprecated in the credential manifest; cleaned up in a future pass.
- **Operator runs Google Cloud Console manually.** No automation of project creation, API enablement, OAuth consent screen, or Client ID download. This is intrinsic to Google's OAuth model (no headless project bootstrap) — same constraint any option would face.

### Neutral

- **Refresh-token shape**: single shared refresh token covering all six scopes, stored in gog's keyring. Personal account only at this phase; the future Intentional business account will use a separate Google Cloud project and OAuth Client with its own gog `--client` alias, sharing the gog install.
- **No Felix-side authorize script.** The earlier proposal to generalize `authorize-calendar.py` → `authorize-google-workspace.py` was made obsolete by gog's native `gog auth` flow. The existing `authorize-calendar.py` is being deprecated, not extended.

## Alternatives Considered

### B: `gcalcli`

Calendar-only. Would force a second tool for Gmail (`himalaya`?), a third for Drive, etc. — multiplying both the install surface and the agent's mental model. Rejected.

### C: Direct Google Calendar API (Python `google-api-python-client`)

Maximum flexibility but maximum maintenance burden. Felix would own auth flow, API call construction, response parsing, error handling, retry logic, scope management, and breakage adaptation across all six services. Kent's explicit preference is to leverage community-maintained prior art rather than write and maintain a Python wrapper. Rejected.

### D: MCP Google Calendar

Available in Claude Code sessions, but Felix agents run in OpenClaw, not Claude Code. The MCP surface isn't part of OpenClaw's agent runtime. Even if it were, MCP is Calendar-only — same multiplier problem as option B. Rejected.

### E: ClawHub community skills (`afrexai-email-to-calendar`, `gws-calendar-agenda`, etc.)

Service-specific or use-case-specific. Would require integrating multiple community skills (some of which are themselves `gog`-based) rather than the single underlying tool. Rejected as a strictly-narrower version of option A.

## References

- **Video reference** (research-phase evidence): https://youtu.be/acuhctFqaOc — install walkthrough of `gog` as an OpenClaw skill. Transcribed via the in-house Whisper API on 2026-05-13; transcript at `/data/transcripts/20260513-142129-b6e63c64.json`. The video predates Kent's office2 install by weeks; the install flow is materially the same with two adaptations: (1) Linuxbrew instead of Mac brew, (2) `gog auth add ... --remote` instead of the Telegram bot's chat-paste flow.
- **`gog` homepage**: https://gogcli.sh
- **`gog` SKILL.md** (canonical setup procedure on office2): `/usr/lib/node_modules/openclaw/skills/gog/SKILL.md`
- **OpenClaw skill readiness check**: `openclaw skills info gog` (validates binary presence; runtime auth state is gog's own concern)
- **Issue #100**: original research-phase issue; this ADR closes its Phase 1.
- **Issue #120**: Gmail integration skill (F024); closes alongside #100 since the same gog install + same refresh token covers Gmail.
- **Issues #164 / #165**: Calendar / Email management epics. Stay open as user-story trackers; downstream missions for individual stories build on this foundation.
