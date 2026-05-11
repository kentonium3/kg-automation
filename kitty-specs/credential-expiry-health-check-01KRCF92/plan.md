# Implementation Plan: Credential Expiry Health Check

**Branch**: `main` (direct-to-main per kg-automation convention) | **Date**: 2026-05-11 | **Spec**: [spec.md](./spec.md)
**Mission**: `credential-expiry-health-check-01KRCF92`

---

## Summary

Build a daily, deterministic credential-health checker on office2 that reads `credential-manifest.json`, detects credentials inside the 30-day warning window or with failing activity signals, and files paired alerts: a **GitHub issue** in `kentonium3/kg-automation` (audit trail, email-notified) plus, for cadence-based alerts only, a **Vikunja task** with `due_date = boundary − 7 days` (drives the existing escalation engine's WhatsApp pressure).

Architecturally: a single Python script, a systemd user timer + oneshot service following the `felix-doc-auditor.{timer,service}` pattern, fully stateless across cycles (GitHub issue state is the dedup state).

Closes risk-register item **R-003**.

---

## Technical Context

**Language/Version**: Python 3.12+ (matches the system Python on office2 Ubuntu 24.04 LTS; no virtualenv needed for stdlib-only check).
**Primary Dependencies**: stdlib only (`json`, `subprocess`, `datetime`, `argparse`, `logging`, `re`). External CLI tooling: `gh` (GitHub CLI), `tailscale`, `openclaw`, plus direct HTTP to Vikunja API (`urllib.request` from stdlib).
**Storage**: none (system is stateless; GitHub issue state is the dedup substrate).
**Testing**: `pytest` for unit + contract tests; fixture-driven; integration smoke is a canary procedure (per `quickstart.md`).
**Target Platform**: Linux server (Ubuntu 24.04 LTS on office2), executed as the `claude` user under a systemd user session.
**Project Type**: single (one Python script + supporting unit files in `scripts/`).
**Performance Goals**: < 10 seconds wall-clock per cycle on the current ~9-entry manifest (NFR-001). Daily cadence keeps API-call volume trivial against both GitHub rate limits and Vikunja.
**Constraints**: no sudo (C-001); manifest is read-only from the check's perspective (C-002); single repo + single Vikunja instance (C-003); systemd-user-timer scheduling pattern (C-004); `kg-felix-bot` GitHub identity (C-005); existing `vikunja-api` token (C-006); same-change architecture-doc updates (C-007).
**Scale/Scope**: 9 credentials today, expected to remain under 25 in any foreseeable horizon. The check's complexity is O(N credentials) — runtime stays well under the budget even at 10× scale.

---

## Charter Check

The charter context resolver returned `mode: compact` with `Governance: unresolved` (charter references `pytest` and `python` tools not registered in the runtime tool registry). No charter-derived gates are enforceable in this state.

**Action**: Skip Charter Check; note governance is unresolved at plan time. Re-evaluate post-design if a charter is registered before tasks.

---

## Project Structure

### Documentation (this feature)

```
kitty-specs/credential-expiry-health-check-01KRCF92/
├── plan.md                            # This file
├── spec.md                            # Requirements (specify phase)
├── meta.json                          # Mission metadata
├── research.md                        # Phase 0: plan-phase decisions (R-001..R-010)
├── data-model.md                      # Phase 1: entities, state model, transitions
├── quickstart.md                      # Phase 1: deploy + day-2 ops procedures
├── contracts/                         # Phase 1: external-surface interfaces
│   ├── manifest-reader.md
│   ├── github-issue-writer.md
│   ├── vikunja-task-writer.md
│   └── activity-signal-readers.md
├── checklists/
│   └── requirements.md                # Spec-quality validation
└── tasks/                             # Populated by /spec-kitty.tasks
```

### Source Code (repository root)

```
scripts/
├── security/
│   └── credential-health-check.py     # The check (single-file Python script)
└── office2/
    ├── credential-health-check.timer     # systemd user timer source
    ├── credential-health-check.service   # systemd user oneshot service source
    └── deploy/
        └── credential-health-check.sh    # Deploy script (claude user, no sudo)

tests/
└── security/
    ├── test_manifest_reader.py
    ├── test_cadence_math.py
    ├── test_dedup_key.py
    ├── test_tailscale_signal.py
    ├── test_whatsapp_signal.py
    ├── test_issue_writer.py
    ├── test_task_writer.py
    └── fixtures/
        ├── manifest-valid.json
        ├── manifest-near-expiry.json
        ├── manifest-missing-last-reviewed.json
        ├── manifest-bad-review-cadence.json
        ├── manifest-invalid-json.txt
        ├── manifest-not-a-dict.json
        ├── tailscale-status-running.json
        ├── tailscale-status-needs-login.json
        ├── tailscale-status-stopped.json
        ├── openclaw-channels-status-healthy.txt
        ├── openclaw-channels-status-not-connected.txt
        └── openclaw-channels-status-stale.txt

docs/design/architecture/
├── data/
│   ├── credential-manifest.json       # Add `kentonium3-pat` entry (FR-013)
│   └── service-inventory.json         # Add credential-health-check service entry (C-007)
├── service-inventory.md               # Match JSON
└── credentials-and-secrets.md         # Cross-reference the auditor in §Security Posture
```

**Structure Decision**: Single-project layout. Script + tests + units co-located with similar Felix runners (`scripts/openclaw/observation/`, `scripts/obsidian/`). Tests under `tests/security/` create a new sibling to existing test trees but match the script's directory.

---

## Phases

### Phase 0 — Research (this command)

Output: `research.md` (10 decisions R-001..R-010). All open spec-level ambiguities resolved:

- **A-004 resolved**: `monitor-activity` signals are programmatic; include in scope.
- All implementation-detail defaults documented (log destination, manifest path resolution, module structure, dedup mechanism, test strategy, scheduling time, naming).

### Phase 1 — Design + contracts (this command)

Outputs: `data-model.md`, `contracts/{manifest-reader,github-issue-writer,vikunja-task-writer,activity-signal-readers}.md`, `quickstart.md`. All four external-surface contracts have test-coverage requirements documented. Data model formalizes the stateless-across-cycles property.

### Phase 2 — Tasks (next command, `/spec-kitty.tasks`)

Not started by this command. Will decompose the work into work packages (WPs) along these likely lines:

1. **Foundation**: add `kentonium3-pat` to `credential-manifest.json` (FR-013 prerequisite); add fixtures.
2. **Manifest reader + cadence math** (unit-testable core).
3. **Activity-signal readers** (parsers + fixtures).
4. **GitHub issue writer + dedup**.
5. **Vikunja task writer**.
6. **Orchestrator + CLI + logging**.
7. **Deploy bundle**: systemd units, deploy script.
8. **Architecture docs**: service-inventory + credentials-and-secrets cross-reference.

The exact WP boundaries are `/spec-kitty.tasks`' job.

### Phase 3 — Implement + review + merge

Per the standard spec-kitty workflow. Acceptance gates per spec §6 (SC-001..SC-007).

---

## Complexity Tracking

No charter violations identified (charter is unresolved; no gates to fail). No complexity exceptions claimed beyond the scoped decisions in `research.md`.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| *(none)* | — | — |

---

## Risk register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| `kg-felix-bot-pat` expires before the auditor can alert on itself | low | high (auditor can't file the alert that would have prevented this) | The auditor is itself a forecast tool — Kent gets 30 days of warning; PAT rotation is fast (5 minutes). 30-day window dominates the failure mode. |
| `openclaw channels status` output format changes | low | medium (WhatsApp staleness check breaks) | Captured fixtures + dedicated parser unit tests will fail loudly on format drift; fix is one parser update. |
| `tailscale status --json` output schema changes | very low | medium (Tailscale state check breaks) | Same mitigation pattern. |
| Vikunja API call ordering creates orphaned tasks (issue creation fails after task creation succeeds) | low | low (one orphan task per failure; visible; recoverable) | Documented in `contracts/vikunja-task-writer.md` §Ordering and in spec §6 edge case; no automated recovery in v1, manual cleanup acceptable. |
| First-run firing all alerts simultaneously if many credentials are near boundaries at deploy time | low | low (volume capped at N≤9 today) | Current manifest has zero credentials inside the 30-day window. Even at full saturation, 9 issues + 9 tasks is comfortably below rate limits and operator attention budget. |

---

## Branch contract (2nd of 2 mandatory restatements)

Per `/spec-kitty.plan` contract:

- **Current branch at plan start**: `main`
- **Planning/base branch**: `main`
- **Final merge target for completed changes**: `main`
- **`branch_matches_target`**: true

This matches the standard kg-automation direct-to-main workflow. No deviation.

---

## ⛔ Plan phase mandatory stop

Per `/spec-kitty.plan` command contract: planning artifacts (plan.md, research.md, data-model.md, contracts/, quickstart.md) are complete. Tasks generation requires `/spec-kitty.tasks` as a separate invocation.

Generated artefacts:

| File | Path |
|---|---|
| Plan | `kitty-specs/credential-expiry-health-check-01KRCF92/plan.md` |
| Research | `kitty-specs/credential-expiry-health-check-01KRCF92/research.md` |
| Data model | `kitty-specs/credential-expiry-health-check-01KRCF92/data-model.md` |
| Manifest reader contract | `kitty-specs/credential-expiry-health-check-01KRCF92/contracts/manifest-reader.md` |
| GitHub issue writer contract | `kitty-specs/credential-expiry-health-check-01KRCF92/contracts/github-issue-writer.md` |
| Vikunja task writer contract | `kitty-specs/credential-expiry-health-check-01KRCF92/contracts/vikunja-task-writer.md` |
| Activity signal readers contract | `kitty-specs/credential-expiry-health-check-01KRCF92/contracts/activity-signal-readers.md` |
| Quickstart | `kitty-specs/credential-expiry-health-check-01KRCF92/quickstart.md` |

Next: `/spec-kitty.tasks`.
