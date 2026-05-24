---
work_package_id: WP03
title: Config + arch docs + cutover replay
dependencies:
- WP02
requirement_refs:
- FR-013
- NFR-001
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
created_at: '2026-05-23T22:50:00+00:00'
subtasks:
- T006
- T007
history: []
authoritative_surface: docs/
execution_mode: code_change
mission_id: 01KSBGBS9BBDWV2Z28FESVJ9KQ
mission_slug: audit-interpretation-moment0-01KSBGBS
owned_files:
- scripts/doc_audit/config.toml
- scripts/doc_audit/config.py
- docs/design/architecture/data/service-inventory.json
- docs/design/architecture/data/data-flows.json
- docs/design/architecture/service-inventory.md
- docs/design/architecture/data-flows.md
- docs/runbooks/doc-auditor-driver-ops.md
tags: []
agent: "claude:opus:python-implementer:implementer"
shell_pid: "75937"
---

# WP03 — Config + arch docs + cutover replay

## Subtask T006 — Config + arch docs + runbook

- `scripts/doc_audit/config.toml`: add `[audit_interpretation]` block:
  ```
  [audit_interpretation]
  enabled = true
  ledger_path = "/data/services/openclaw/state/doc_audit/audit-events-ledger.jsonl"
  model = "claude-haiku-4-5-20251001"
  api_key_path = "/data/services/openclaw/secrets/anthropic"
  timeout_seconds = 30
  confidence_threshold = 0.80
  ```
- `scripts/doc_audit/config.py`: add `AuditInterpretationConfig` dataclass mirroring `DriftInterpretationConfig`. Loader extends Config to include the new section (default `enabled=False` for graceful fallback if config doesn't have the block).
- Arch docs: register `audit_interpretation.py`, `audit_ledger.py`, new ledger file, new LLM flow. Update markdown views to match. `updated_by: "#400"` on touched entries.
- Runbook: add new section in `docs/runbooks/doc-auditor-driver-ops.md` describing the commit-derived Moment 0 path; cross-reference the existing drift-event Moment 0 section.

## Subtask T007 — Cutover replay for currently-stuck audits

- After WP02 merges, the 11 currently-stuck audits (`#350`, `#363`, `#364`, `#365`, `#373`, `#377`, `#395`, `#396`, `#397`, `#398`, `#399`) are eligible for re-processing
- Operator runs a manual tick: `systemctl --user start felix-doc-auditor.service`
- The driver should pick each up as a `doc_audit` signal (they have `doc-audit` label per today's CI fix); run the deterministic-pattern path (no proposals expected); fall through to the NEW audit_interpretation path; each audit gets per-doc LLM evaluation
- Expected outcome:
  - Some audits auto-close (NO_CHANGE_NEEDED across all docs)
  - Some get specific JUDGMENT_REQUIRED comments
  - Some auto-commit Tier A or file Tier B PRs if PROPOSED_EDIT
- No new arch docs needed for this subtask — just runbook addition noting the replay sequence

## Definition of Done

- Config block deployed
- Arch docs updated; JSONs parse
- Runbook documents the new path
- 11 currently-stuck audits re-processed; operator queue measurably shrinks (or has actionable comments)

## Implementation Command

```bash
spec-kitty agent action implement WP03 --mission audit-interpretation-moment0-01KSBGBS --agent claude:opus:python-implementer:implementer
```

## Activity Log

- 2026-05-24T03:47:25Z – claude:opus:python-implementer:implementer – shell_pid=75937 – Started implementation via action command
- 2026-05-24T04:06:18Z – claude:opus:python-implementer:implementer – shell_pid=75937 – Ready for review: config block + arch docs + runbook + cutover-replay section
