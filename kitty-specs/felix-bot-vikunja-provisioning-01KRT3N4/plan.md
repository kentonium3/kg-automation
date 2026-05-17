# Implementation Plan: Provision felix-bot Vikunja identity

**Mission**: `felix-bot-vikunja-provisioning-01KRT3N4`
**Branch**: `main` (target = planning_base = merge_target)
**Date**: 2026-05-17
**Spec**: [spec.md](./spec.md)
**Source**: Issue [#304](https://github.com/kentonium3/kg-automation/issues/304) — Phase 1 of [ADR-0002](../../docs/design/architecture/adr/0002-felix-vikunja-task-model.md)

---

## Summary

Provision a dedicated `felix-bot` Vikunja user on the office2 instance via four phased Python helpers + an operator-driven runbook. The helpers handle deterministic API operations (registration, project sharing, token generation, side-channel validation, atomic secrets-file rotation, post-swap verification, token revocation). The operator drives sequencing and decision points between phases. After the swap, all Felix sub-agent API writes attribute to `felix-bot` at the Vikunja API layer instead of `kent`, eliminating the `[Felix]` text-prefix as the sole audit signal and enabling the structured `created_by` reconciliation patterns that ADR-0002's later phases depend on.

The architecture is operator-driven (not auto-orchestrated) — preserving the ability to pause, inspect SUMMARY output, and decide whether to proceed at each phase boundary. This matches Felix Constitution Directive 6 (deterministic detection in scripts; judgment / interpretation by the human operator).

---

## Technical Context

**Language/Version**: Python 3.10+ (matches kg-automation standard per `CLAUDE.md`)

**Primary Dependencies**: standard library only (`argparse`, `json`, `subprocess`, `urllib.request` or `requests` if already a project dep). No new third-party packages.

**Storage**:
- Vikunja v0.24.6 instance on `office2` — target of the user registration, project shares, token operations
- `/data/services/openclaw/secrets/vikunja-api` (mode 600, claude:claude) — the canonical secrets file
- `/data/services/openclaw/secrets/vikunja-api.kent-pre-felix-bot.bak` (mode 600, claude:claude) — transient backup file used for rollback only
- Architecture documentation files in `docs/design/architecture/` — updated to reflect new identity

**Testing**: Pytest unit tests in `tests/vikunja/` (new directory) using subprocess + mocked HTTP responses, following the pattern from `tests/openclaw/agents/main/test_felix_file_issue.py`. No live Vikunja calls in pytest. Live integration is the operator-driven `validate_felix_bot.py` execution during pre-swap validation (FR-004).

**Target Platform**: Helpers run on `office2` (Ubuntu 24.04 LTS), invoked by the operator via SSH. Architecture docs edited on the Mac and committed normally.

**Project Type**: Single project — Python helpers in `scripts/vikunja/`, tests in `tests/vikunja/`, runbook in `docs/runbooks/`.

**Performance Goals**:
- Side-channel validation (FR-004) completes in under 5 minutes (NFR-001)
- Total downtime window from swap to first successful Felix cron is under 30 minutes (NFR-002)
- Rollback executes in under 5 minutes when triggered (NFR-003)
- All 12 project shares apply in a single batch (NFR-005)

**Constraints**:
- Tier 2 change-risk protocol (Restic snapshot required pre-rotation per `pre-flight-checklist.md`)
- Must use the existing `/data/services/openclaw/secrets/vikunja-api` file path (Vikunja API skill references this path; changing it is out of scope)
- Vikunja v0.24.6 API contract (changes to that version are out of scope)
- felix-bot receives R/W permission only on shared projects (not admin) per ADR-0002 Q3
- No code changes to any Felix agent — only secrets file contents + documentation change
- No migration of existing tasks, comments, labels, or project ownership

**Scale/Scope**:
- 12 Vikunja projects in scope (one project share grant per project)
- 4 Python helpers, ~150-300 lines each (smaller than `felix-file-issue.py`'s 700 lines because the scope per helper is tighter)
- ~30-40 pytest tests across the four helpers
- 4 documentation files updated (`credential-manifest.json`, `credentials-and-secrets.md`, `identity-model.md`, `service-inventory.json`)
- 1 new runbook (`docs/runbooks/felix-bot-vikunja-provisioning.md`)

---

## Charter Check

Charter context loaded in `compact` mode (no first-load bootstrap). No explicit governance gates apply to this mission beyond the cross-cutting tier protocol and Constitution Directive 6.

| Gate | Status | Note |
|---|---|---|
| Felix Constitution Directive 6 (deterministic detection / AI interpretation) | **PASS** | Four helpers encapsulate deterministic Vikunja API operations. Operator judgment (pre-flight conditions, validation success interpretation, soak-window observation) stays with the human. No LLM-in-the-loop logic in this mission. |
| Tier 2 protocol (per `docs/design/architecture/data/change-risk-taxonomy.json`) | **PASS** (gated at execution) | Restic snapshot must be confirmed pre-rotation per `pre-flight-checklist.md`. Captured as an execution-time check in the runbook, not a code-time gate. |
| Documentation standards (machine-readable wins over narrative) | **PASS** | `credential-manifest.json` is authoritative; `credentials-and-secrets.md` is narrative view. Both updated in the same commit per Constraint C-003 to prevent drift. |
| No regression in WhatsApp UX | **PASS** | NFR-005 (7-day soak with zero auth failures across all crons) is the explicit acceptance signal. Soak window encoded as a hard gate before issue closure. |

No charter violations identified. No items in the Complexity Tracking table.

---

## Architecture

### Helper decomposition

Four phase-aligned helpers in `scripts/vikunja/` (new directory). Each is independently testable and re-runnable.

| Helper | Phase | Authenticates as | What it does |
|---|---|---|---|
| `provision_felix_bot.py` | Pre-swap setup | kent (existing token) | (1) Register felix-bot user via `POST /api/v1/register`. (2) For each of 12 real projects, share with felix-bot at R/W via `PUT /api/v1/projects/{id}/users`. (3) Operator-driven token generation via Vikunja UI (helper instructs operator). Helper accepts the generated token via stdin or `--token-file` argument and stores it ephemerally for the validation phase. |
| `validate_felix_bot.py` | Side-channel validation (FR-004) | felix-bot (new token) | (1) Authenticate using felix-bot token (not via secrets file). (2) `GET /api/v1/projects` confirms felix-bot sees all 12 expected projects. (3) Write a `[Felix-Validation]` sample comment on a single low-impact task. (4) Read the comment back and assert `created_by.username == felix-bot`. (5) Delete the validation comment to avoid pollution. (6) Optional: rollback smoke test (FR-015) — exercise the rollback path symbolically without touching production. |
| `swap_vikunja_secrets.py` | Cutover | felix-bot (new token) | (1) Backup `/data/services/openclaw/secrets/vikunja-api` to `vikunja-api.kent-pre-felix-bot.bak` with mode 600 + claude:claude. (2) Atomic-write felix-bot's token to `/data/services/openclaw/secrets/vikunja-api`. (3) `systemctl --user restart openclaw-gateway`. (4) Wait for gateway healthy. (5) Invoke a sample Felix agent comment write through the gateway, verify `created_by.username == felix-bot`. (6) On any step failure, automatically restore from `.bak` and exit nonzero. |
| `revoke_kent_tokens.py` | Post-soak cleanup | kent UI session (via password manager, OR felix-bot if Vikunja allows admin-via-share — TBD) | (1) Enumerate kent-owned API tokens via the Vikunja API. (2) Delete each one. (3) Optionally remove the `.bak` file after the 7-day soak passes. |

### Validation harness design

The `validate_felix_bot.py` helper writes its sample comment to a **single low-impact target task**. The task identity is:

- An existing habit task that already accumulates daily `[Felix]` comments (e.g., task #13's child or any current habit). The validation comment uses the `[Felix-Validation] <timestamp>` prefix to distinguish it from real Felix writes and is deleted at the end of validation. **OR**
- A fresh throwaway task created at validation start (`title="felix-bot validation probe <iso8601>"`) and deleted entirely after read-back.

Default: throwaway task in the Habits project. Cleanest, no pollution risk on real task histories. Configurable via `--target-project-id` flag (defaults to 13 = Habits).

### Runbook structure

New file: `docs/runbooks/felix-bot-vikunja-provisioning.md` (operator-driven; not auto-orchestrated).

Structure:
1. **Pre-flight** — Restic snapshot confirmation, dependent services baseline check, kent presence
2. **Phase 1: provision** — invoke `provision_felix_bot.py`, capture token, confirm SUMMARY
3. **Phase 2: validate** — invoke `validate_felix_bot.py`, confirm exit 0 + attribution
4. **Phase 3: swap** — invoke `swap_vikunja_secrets.py`, confirm SUMMARY + first cron tick passes
5. **Phase 4: doc updates** — edit 4 docs locally, commit, push
6. **Phase 5: soak** — 7 days monitoring; daily ack required at the start of each day (operator looks at journalctl + cron outcomes)
7. **Phase 6: revoke** — invoke `revoke_kent_tokens.py`, remove `.bak`, close issue

Each phase has explicit GO / NO-GO criteria the operator can verify before proceeding.

### Doc update sequencing

Per Q3 of Engineering Alignment: docs are updated and committed **after** `swap_vikunja_secrets.py` succeeds (FR-008 verified) but **before** the 7-day soak completes. Rationale:

- The swap is the moment-of-truth; docs reflect intended state once that succeeds
- Waiting for the full soak would leave the JSON manifest stale for a week
- If rollback is needed during soak, docs would be reverted as part of the rollback commit

All 4 doc updates batch into a single commit per Constraint C-003.

### Operator-driven not auto-orchestrated

There is intentionally no orchestrator that runs all four helpers in sequence. The operator runs each helper individually, confirms SUMMARY output, and makes the explicit decision to proceed to the next phase. This matches D6 — each helper encapsulates deterministic work; the operator owns judgment / interpretation between phases.

---

## Project Structure

### Documentation (this mission)

```
kitty-specs/felix-bot-vikunja-provisioning-01KRT3N4/
├── plan.md              # This file
├── research.md          # Phase 0 output — Vikunja capabilities (already mostly resolved by 2026-05-17 probe)
├── data-model.md        # Phase 1 output — entities and their relationships
├── quickstart.md        # Phase 1 output — operator quick reference
├── contracts/           # Phase 1 output — Vikunja API endpoints consumed
├── spec.md              # From /spec-kitty.specify
├── meta.json            # Mission identity
├── checklists/
│   └── requirements.md  # Quality checklist from spec phase
└── tasks/               # Empty — populated by /spec-kitty.tasks
```

### Source code (repository root)

```
scripts/
└── vikunja/                                # NEW directory
    ├── provision_felix_bot.py              # Phase 1: register + share + capture token
    ├── validate_felix_bot.py               # Phase 2: side-channel validation
    ├── swap_vikunja_secrets.py             # Phase 3: cutover with automatic rollback on failure
    └── revoke_kent_tokens.py               # Phase 6: post-soak cleanup

tests/
└── vikunja/                                # NEW directory
    ├── __init__.py
    ├── test_provision_felix_bot.py         # ~10 unit tests with mocked HTTP
    ├── test_validate_felix_bot.py          # ~10 unit tests
    ├── test_swap_vikunja_secrets.py        # ~10 unit tests (mock systemctl + HTTP)
    └── test_revoke_kent_tokens.py          # ~5 unit tests

docs/
├── runbooks/
│   └── felix-bot-vikunja-provisioning.md   # NEW: operator runbook
└── design/architecture/
    ├── credentials-and-secrets.md          # Modified: update vikunja-api ownership
    ├── identity-model.md                   # Modified: add felix-bot Agent Service Account
    └── data/
        ├── credential-manifest.json        # Modified: vikunja-api entry ownership
        └── service-inventory.json          # Modified: if vikunja entry tracks users
```

**Structure Decision**: Single-project Python layout (Option 1 from the plan template). All helpers in one `scripts/vikunja/` directory; all tests in one parallel `tests/vikunja/` directory. Matches the existing `scripts/habits/`, `scripts/openclaw/agents/main/` patterns in this repo.

---

## Implement-Review workflow (per Kent's instruction 2026-05-17)

When this mission reaches `/spec-kitty.implement`, the orchestrator dispatches:

- **Implementation** to **Claude** (matches the existing helper-implementation pattern, e.g., `felix-file-issue.py`)
- **Review** to **Codex** (per the `spec-kitty-implement-review` skill — separate-agent review is the project's quality gate)

This is the configured agent pairing for this mission. Captured here so the implement command picks it up cleanly. Aligned with the project's existing `.kittify/config.yaml` defaults if those name Claude as implementer and Codex as reviewer; otherwise the implement step will use explicit `--agent` flags.

---

## Complexity Tracking

No charter violations. No complexity-tracking entries.

---

## References

- [Spec](./spec.md)
- [ADR-0002 — Felix ↔ Vikunja task model](../../docs/design/architecture/adr/0002-felix-vikunja-task-model.md)
- [Issue #304](https://github.com/kentonium3/kg-automation/issues/304)
- [Issue #311 — umbrella tracker](https://github.com/kentonium3/kg-automation/issues/311)
- [Research: Vikunja task model](../../docs/design/research/vikunja-task-model-research.md)
- [Research: Vikunja RRULE upstream state](../../docs/design/research/vikunja-rrule-upstream-state.md)
- [Pre-flight checklist (Tier 2 protocol)](../../docs/runbooks/governance/pre-flight-checklist.md)
- [Change risk taxonomy](../../docs/design/architecture/data/change-risk-taxonomy.json)
- [Felix Constitution Directive 6](../../docs/constitution/FELIX-CONSTITUTION.md)
- Existing helper precedent: `scripts/openclaw/agents/main/felix-file-issue.py` + `tests/openclaw/agents/main/test_felix_file_issue.py`
