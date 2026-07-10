# Implementation Plan: Felix Calendar Helper

**Branch**: `feat/felix-calendar-helper` | **Date**: 2026-07-09 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `kitty-specs/felix-calendar-helper-01KX4H3C/spec.md`

## Summary

Give Felix a **Felix-owned, deterministic Google Calendar helper** (a Python CLI
on `google-api-python-client`) that any agent invokes with one command, plus
reshape the `felix-admin-calendar` OpenClaw agent to judgment-only. The helper
replaces `gog calendar create` on the calendar surface, is multi-account-ready
(default `personal` = `kentgale@gmail.com`), and closes the broken inbox→calendar
path (#679) by letting inbox capture call the helper **directly** instead of
hopping to another agent. The existing deterministic NL→structured parsers are
reused verbatim; only the terminal "create" call changes. Deploys to office2 via
the manifest pipeline with a dedicated uv venv for the Google dependencies.

## Technical Context

**Language/Version**: Python 3.12 (office2 system `python3` is 3.12.3; repo targets 3.11+)
**Primary Dependencies**: `google-api-python-client`, `google-auth`, `google-auth-oauthlib` (pinned in a dedicated office2 venv — NOT in the repo's minimal `requirements.txt` runtime set); stdlib `argparse`/`json`/`datetime` for the CLI shell
**Storage**: Per-account OAuth credentials on disk at `~/.config/felix/google/<account>/{client_secret.json, token.json}` (0600 file, 0700 dir); no database. Existing clarification state (JSON array at `/data/services/openclaw/state/pending-calendar-clarifications.json`) unchanged.
**Testing**: `pytest` with the Google client + `Credentials` mocked; repo-global `tests/conftest.py` HTTP block; `--cov-branch` at repo threshold; one opt-in `live_smoke`-marked real-calendar round-trip (gated by `LIVE_SMOKE_ENABLED=1`, never CI)
**Target Platform**: office2 (Ubuntu 24.04 LTS), invoked on demand by OpenClaw agents via `exec`; authored on Mac
**Project Type**: single (helper scripts + agent-prompt reshape within the existing kg-automation tree)
**Performance Goals**: a single-event CRUD call returns within 10 s under normal connectivity (NFR-001); no long-running service
**Constraints**: office2 has no `pip` (only `uv` 0.11.2) and system `python3` lacks the google libs → dedicated venv (D3); python3-only (DIR-002, C-007); Tier 2 + Tier 3 change (C-005); secrets never committed (NFR-004); fail-safe on auth error (FR-006)
**Scale/Scope**: one user, two accounts eventually (one implemented now); ~4 CLI subcommands + auth module; low call volume (inbox notes + conversational requests)

## Charter Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

| Charter item | Status | Note |
|---|---|---|
| **DIR-001/002** production on office2, target Linux, python3-only | ✅ | Helper runs on office2; invoked via venv python3; no Windows/Dropbox. |
| **DIR-004** deploy via manifest discipline | ✅ | `deploys/queued/felix-calendar-helper.yaml`, Tier 3, entrypoint deploy script using `scripts/deploy/lib/` primitives. |
| **DIR-005/006** strict-order safe-deploy | ✅ | Deploy script: pre-flight (Restic age, creds presence) → provision venv → verify → self-check smoke. Artifacts before config. |
| **DIR-009 / C-005** Tier 2 Restic ≤24h before state change | ✅ | `snapshot.verify_restic_recent --max-age-hours 24` gate; operator-ack path available. |
| **Rebaseline (#557)** audited surface | ✅ | Only the `openclaw.json` `skills` edit is monitored (`openclaw-config`, rebaseline_required:true) → merge records `Rebaseline: completed at <ts>`. AGENTS.md edits are unmonitored (rebaseline_required:false — audit hashes only openclaw.json); google deps go in the venv, NOT requirements.txt, so the pip-packages baseline is untouched. (Corrected per post-plan Codex vs `audited-surfaces.json`.) |
| **DIRECTIVE_034** test-first | ✅ | Contract tests authored before/with helper code; auth-failure path explicitly tested. |
| **DIR-011** privacy/security boundaries | ✅ | Personal calendar only; no `_private`; creds 0600 outside repo, never committed. |
| **DIR-014** documentation-sync requirement | ✅ | Spec §Documentation Synchronization + IC-06; credentials/data-flows/service-inventory/INDEX/roadmap updated in-merge. |
| **DIRECTIVE_006 helper/library/skill split** | ✅ | Deterministic I/O → helper; judgment (NL/clarification) stays in agent prompt; skill promotion deferred until ≥2 agents call it. |
| **bare `python3 -m scripts.*` invocation convention** | ⚠️ justified deviation | Helper needs google libs absent from system `python3`; runs under a dedicated venv python (precedent: doc-auditor, heartbeat-gate). See Complexity Tracking. |

No blocking violations. Re-checked post-design (Phase 1): unchanged.

## Project Structure

### Documentation (this mission)

```
kitty-specs/felix-calendar-helper-01KX4H3C/
├── plan.md              # This file
├── research.md          # Phase 0 — decisions D1–D8
├── data-model.md        # Phase 1 — entities, payload + credential schemas
├── quickstart.md        # Phase 1 — deploy + verify runbook
├── contracts/
│   ├── calendar-helper-cli.md       # the helper CLI contract (subcommands, exit codes, SUMMARY)
│   └── felix-admin-calendar-reshape.md  # judgment-only agent contract (helper call replaces gog)
└── tasks.md             # Phase 2 (/spec-kitty.tasks — NOT created here)
```

### Source Code (repository root)

```
scripts/google/
├── workspace_auth_spike.py     # EXISTING (spike; retained, unchanged)
├── calendar_auth.py            # NEW — per-account load/refresh/persist (from spike pattern)
└── calendar_helper.py          # NEW — CLI: create/list/update/delete + --self-check

scripts/inbox/
└── route_calendar_event.py     # MODIFY — DEFAULT_ACCOUNT → personal; (envelope still built here)

scripts/calendar_routing/
└── validate_calendar_event.py  # MODIFY — DEFAULT_ACCOUNT → personal

scripts/openclaw/agents/felix-admin-calendar/
└── AGENTS.md                   # MODIFY — judgment-only; calls calendar_helper, not gog
scripts/openclaw/agents/felix-admin-capture/
└── AGENTS.md(.tmpl)            # MODIFY — inbox calendar step calls helper directly (no openclaw-agent hop)

deploys/queued/
└── felix-calendar-helper.yaml  # NEW — Tier 3 manifest (audited_surface: true)
scripts/deploy/
└── deploy-felix-calendar-helper.py  # NEW — Restic gate + uv venv provision + creds-presence + self-check

tests/google/
├── test_calendar_auth.py       # NEW
└── test_calendar_helper.py     # NEW

docs/design/architecture/data/   # MODIFY — credential-manifest, data-flows, service-inventory
docs/design/architecture/*.md    # MODIFY — narrative views
docs/INDEX.md, docs/design/felix-capability-roadmap.md  # MODIFY — nav + status
docs/runbooks/                   # NEW — calendar-helper ops runbook
```

**Structure Decision**: single-project layout inside the existing kg-automation
tree. The helper joins the existing `scripts/google/` package; the reshape edits
existing agent prompts and the two routing helpers; deploy + docs follow the
established manifest + architecture-data conventions.

## Complexity Tracking

| Deviation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| Dedicated uv venv instead of bare `python3 -m` | office2 system `python3` lacks the google libs and there is no `pip`; the deterministic-only convention can't carry a 3rd-party dependency | System install needs sudo (Tier 0, claude has none); `uv run --with` adds per-call latency + network inside a fail-safe path. Venv matches doc-auditor/heartbeat-gate precedent and is fully deterministic. |

## Implementation Concern Map

> Concerns are not work packages. `/spec-kitty.tasks` translates these into WPs.

### IC-01 — Calendar helper core (auth + CRUD + CLI contract)

- **Purpose**: The deterministic CLI that authenticates and performs event create/list/update/delete against Google Calendar, with a fail-safe auth path.
- **Relevant requirements**: FR-001, FR-002, FR-003, FR-004, FR-006, FR-007; NFR-001, NFR-005
- **Affected surfaces**: `scripts/google/calendar_helper.py`, `scripts/google/calendar_auth.py`
- **Sequencing/depends-on**: none (foundation)
- **Risks**: correct RFC3339/timezone handling; distinct exit codes; never mutating on auth failure.

### IC-02 — Multi-account credential resolution

- **Purpose**: Resolve credentials by `--account` from a per-account store so a second account is purely additive.
- **Relevant requirements**: FR-005; NFR-004; SC-005
- **Affected surfaces**: `scripts/google/calendar_auth.py` (path resolution), `FELIX_GOOGLE_DIR` override for tests
- **Sequencing/depends-on**: folds into IC-01 (shared auth module) but is a distinct testable concern
- **Risks**: path traversal / account-name validation; 0600/0700 enforcement.

### IC-03 — Inbox rewire + felix-admin-calendar reshape (closes #679)

- **Purpose**: Capture reaches the calendar via a **single deterministic command** (`route_calendar_event --create`, which validates → builds envelope → invokes the helper → emits status) — no agent hop; the calendar agent becomes judgment-only and calls the helper instead of gog; default account flips to `personal`.
- **Relevant requirements**: FR-008, FR-009; SC-002, SC-003
- **Affected surfaces**: `scripts/inbox/route_calendar_event.py` (add `--create` helper-call mode), capture `AGENTS.md`(.tmpl), `felix-admin-calendar/AGENTS.md`, `scripts/calendar_routing/validate_calendar_event.py`
- **Sequencing/depends-on**: IC-01 (helper must exist to be called)
- **Risks**: prompt fidelity (agents follow the deterministic call, not gog); preserving the existing clarification round-trip (JSON-array store at `pending-calendar-clarifications.json`); the `DEFAULT_ACCOUNT` default-change touch points + fixtures. Minimizing haiku's role to "one opaque command" is the core de-risk (post-plan Codex).

### IC-04 — Tests

- **Purpose**: Prove the contract without network — CRUD, fail-safe auth, payload-file mapping, multi-account resolution, exit codes.
- **Relevant requirements**: NFR-003; verifies FR-001..006, SC-004, SC-005
- **Affected surfaces**: `tests/google/test_calendar_helper.py`, `tests/google/test_calendar_auth.py`
- **Sequencing/depends-on**: co-developed with IC-01/IC-02 (test-first, DIRECTIVE_034)
- **Risks**: faithful Google-client mock; the one `live_smoke` test must stay CI-skipped.

### IC-05 — Deploy: venv provisioning, creds staging, manifest, rebaseline

- **Purpose**: Ship the helper to office2 safely — provision the uv venv, verify creds, self-check, rebaseline the audited surface.
- **Relevant requirements**: FR-010; C-003, C-005
- **Affected surfaces**: `deploys/queued/felix-calendar-helper.yaml`, `scripts/deploy/deploy-felix-calendar-helper.py`, `scripts/deploy/lib/` (reuse)
- **Sequencing/depends-on**: IC-01..IC-03 (code + prompts exist to deploy)
- **Risks**: Tier-2 Restic gate; venv idempotency (use `~/.local/bin/uv pip install --python <venv>/bin/python`, pinned — not `-m uv` inside the venv); creds are a manual step, minted Mac-side with `calendar.events` scope (manifest only verifies presence); rebaseline is openclaw.json-only (manual out-of-band); google deps NOT in requirements.txt.

### IC-06 — Architecture documentation sync

- **Purpose**: Keep the live architecture record faithful — new personal credential, changed calendar data-flow (helper→Google, not gog), service/dependency record, nav + roadmap status.
- **Relevant requirements**: FR-011; DIR-014
- **Affected surfaces**: `docs/design/architecture/data/{credential-manifest,data-flows,service-inventory}.json` + their `.md`/`.view.md` views, `docs/INDEX.md`, `docs/design/felix-capability-roadmap.md`, a new `docs/runbooks/` calendar-helper ops page; targets confirmed against `signal-to-doc-map.json`
- **Sequencing/depends-on**: none (can proceed in parallel; finalized at merge)
- **Risks**: `validate_architecture_data.py` is a blocking Docs-CI gate — JSON edits must pass schema.
