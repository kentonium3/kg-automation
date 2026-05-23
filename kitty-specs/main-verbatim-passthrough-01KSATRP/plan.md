# Implementation Plan: Enforce verbatim pass-through for main-agent delegations

**Branch**: `main` | **Date**: 2026-05-23 | **Spec**: [spec.md](spec.md)
**Mission ID**: `01KSATRP0S0TDA5HV995Y558JK`
**Parent issue**: [#374](https://github.com/kentonium3/kg-automation/issues/374) — P1-bug

## Summary

Two coupled changes, low overall complexity:

1. **Prompt-only fix**: harden `/data/services/openclaw/data/AGENTS.md` (deployed `main` agent standing orders) with a HARD verbatim-forward rule + worked FORBIDDEN-paraphrase examples in the habits/escalation/tasker delegation sections. The current 15,458-char file is over the ~14K openclaw effective budget (per memory `reference_openclaw_gotchas.md`); trim alongside the addition.
2. **Session-rotation helper**: filesystem-rename active `main` session jsonl files to `.jsonl.reset.<timestamp>` (mirroring the existing pattern observed on office2). One-shot script, idempotent, dry-run + force flags. Operator invokes during cutover so the next WhatsApp reply hits a fresh session with updated AGENTS.md.

Plus the operator-facing cutover sequence + smoke test.

## Technical Context

**Language/Version**: Python 3.13 (helper script) + Markdown (AGENTS.md)
**Primary Dependencies**: stdlib only for the helper; no SDK calls
**Storage**: filesystem renames in `/home/claude/.openclaw/agents/main/sessions/` (mirrors auto-rotation pattern)
**Testing**: pytest with mocked `Path.rename` + tmp_path fixtures
**Target Platform**: office2 (Ubuntu 24.04 LTS); helper invoked by operator via `ssh office2-claude`
**Project Type**: single project (additive)
**Performance Goals**: helper ≤30s (NFR-002)
**Constraints**: no sudo; preserve session jsonl history (rename not delete); no third-party deps; AGENTS.md ≤14K source chars
**Scale/Scope**: ~6 active main sessions today; helper iterates over them

## Charter Check

Skipped (charter absent / governance unresolved — pre-existing tool-registry issue, not a blocker).

## Project Structure

### Documentation (this feature)

```
kitty-specs/main-verbatim-passthrough-01KSATRP/
├── plan.md            # This file
├── spec.md            # Mission spec
├── research.md        # Phase 0 — D1..D4 decisions
├── data-model.md      # (skipped — no new dataclasses)
├── contracts/
│   └── rotation-helper.md  # CLI + behavior contract for the rotation helper
└── checklists/requirements.md
```

### Source Code (repository root)

```
scripts/openclaw/agents/main/AGENTS.md  # MODIFIED — hardened delegation rules + trim
scripts/openclaw/helpers/
└── rotate_main_session.py              # NEW — session rotation helper

tests/openclaw/helpers/
└── test_rotate_main_session.py         # NEW

docs/runbooks/
└── openclaw-agent-setup.md             # MODIFIED — add cutover section for session rotation
```

The deployed `AGENTS.md` lives at `/data/services/openclaw/data/AGENTS.md` on office2. The repo-side source is at `scripts/openclaw/agents/main/AGENTS.md` (per memory `reference_office2_agent_deploy_paths.md`: deploy paths differ from repo paths). The deploy is via the operator pulling the repo + the openclaw gateway re-reading from the deployed copy.

**Structure Decision**: minimal additive change. One new script + tests + AGENTS.md edits + runbook update.

## Phase 0 — Research (4 decisions)

- **D1 — Session rotation mechanism**: filesystem rename `.jsonl` → `.jsonl.reset.<timestamp>`. Mirrors the auto-rotation pattern observed at `/home/claude/.openclaw/agents/main/sessions/` (multiple `.jsonl.reset.*` files exist already; the gateway treats them as archived). Alternative considered: an `openclaw session reset` CLI command — but `openclaw --help` doesn't expose one. Filesystem approach is operationally simple and matches the deployed convention.
- **D2 — Trim strategy for AGENTS.md (15,458 → ≤14,000 chars)**: targeted reductions in low-value sections. Candidates per current file: redundant explanatory prose in §"Tools" (~500 chars), example outputs in §"Error handling" (~300 chars), the multi-line "What this system is" intro can compress (~400 chars). Net delta target: ~-1500 chars (trim) + ~+300 (new verbatim rule + examples) = net ~-1200 chars below budget. Plan phase locks specific cuts.
- **D3 — Verbatim-rule placement**: introduce a new top-level §"Verbatim pass-through (ABSOLUTE)" section near the top of AGENTS.md (before §"Habit tracking delegation"). Cross-referenced from each of the habits/escalation/tasker sections. This avoids duplication across the three sections + makes the rule easy for the LLM to find while reading start-to-end.
- **D4 — Rotation helper scope**: rotate ONLY `main` agent sessions (not all agents). Sub-agent sessions (felix-admin-habits, etc.) are also cached but they're not the bug source. Out-of-scope rotation could be added in a follow-on if needed. Marker file at `~/.config/openclaw/main-rotation-<timestamp>.done` so operator can audit when rotations were performed.

See [research.md](research.md) for full rationale.

## Phase 1 — Design & Contracts

### Entities

None new. The rotation helper is a thin operational script; no entity dataclasses needed.

### Contract

[contracts/rotation-helper.md](contracts/rotation-helper.md) — CLI + behavior contract for `rotate_main_session.py`.

### Quickstart

Cutover sequence (in `docs/runbooks/openclaw-agent-setup.md` update):
1. Pull latest on office2
2. Verify AGENTS.md size: `wc -c scripts/openclaw/agents/main/AGENTS.md` ≤14000
3. Copy to deployed path: `cp scripts/openclaw/agents/main/AGENTS.md /data/services/openclaw/data/AGENTS.md`
4. Run rotation helper: `python3 scripts/openclaw/helpers/rotate_main_session.py`
5. Smoke test: send a known WhatsApp message; verify verbatim in sub-agent session jsonl
6. 7-day observation: confirm `habits-history.jsonl` gains rows on Kent's reply days

## Branch Strategy

- Planning base: `main`
- Merge target: `main`
- branch_matches_target: true

## Open Decisions

None. All architectural questions resolved during pre-spec probe.
