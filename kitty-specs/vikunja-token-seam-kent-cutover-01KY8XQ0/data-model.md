# Data Model — Vikunja token seam + kent cutover (phase 2 of #860)

This mission introduces **no new persistent data entities**. It changes one configuration resolution
point and one credential-manifest record. The "entities" below are configuration/identity artifacts.

## Token resolution point (new, in-code)

- **`get_vikunja_token_path() -> pathlib.Path`** (`scripts/common/vikunja_config.py`)
  - **Fields / inputs**: `VIKUNJA_TOKEN_PATH` env var (optional override); module default constant.
  - **Invariant**: exactly one place holds the default runtime token path. No runtime consumer defines
    its own token-path literal (SC-001).
  - **State transition (the only intentional data change in this mission)**:
    default `= /data/services/openclaw/secrets/vikunja-api` (felix-bot, IC-01)
    → `/data/services/openclaw/secrets/vikunja-api-kent` (kent, IC-04).
  - **Failure mode**: resolved file missing/unreadable → single typed error (NFR-002); no silent fallback.

## Credential manifest record (modified)

- **`vikunja-api` (felix-bot)** in `docs/design/architecture/data/credential-manifest.json`:
  - **Transition**: `runtime credential` → `retired / dormant (non-runtime)`. Not deleted (the dormant
    felix-bot Vikunja user still owns Inbox(14) + attribution history — C-002). File retained on office2.
  - **Consumers field**: drop the runtime consumers; keep only the dormant-user note + admin/one-shot refs.
- **`vikunja-api-kent` (kent)**:
  - **Transition**: `config/label-attach credential` → **sole runtime Vikunja credential**. Consumers list
    expands to every Felix→Vikunja runtime path.

## Vikunja server-side objects (reference only — unchanged)

Confirmed live (R1). Runtime targets remain **Inbox = project 1** and **Habits = project 13** (both visible
to kent). The flip *adds* runtime visibility of projects **16–20** (previously felix-bot-blind). Project
**14** (felix-bot's private Inbox) is not runtime-referenced and is intentionally left owned by the dormant
felix-bot user. No task/label/project data is created, moved, or deleted by this mission.

## Registry (`scripts/common/vikunja_refs.json`) — unchanged data, converged view

The declared project/label ids are unchanged. FR-005 only ensures the **validator** exercises the same
(kent) token the runtime uses, so declaration and access cannot silently diverge again — a validation-path
change, not a data change.
