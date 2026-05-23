# Implementation Plan: Audit interpretation Moment 0

**Branch**: `main` | **Date**: 2026-05-23 | **Spec**: [spec.md](spec.md)
**Mission ID**: `01KSBGBS9BBDWV2Z28FESVJ9KQ`

## Summary

Mirror `drift_interpretation.py` (#362 / #391) for commit-derived audits. New module `audit_interpretation.py` + cache-aware prompt. Wire into `handle_audit_routing.py`'s no-proposals branch. Per in-scope doc, LLM produces a verdict; route per verdict. Existing lock-release fallback (today's commit `bf17c3cf`) runs when audit_interpretation is disabled or retries exhaust.

## Technical Context

**Language/Version**: Python 3.13
**Primary Dependencies**: existing `anthropic` SDK + JudgmentClient
**Storage**: new JSONL at `/data/services/openclaw/state/doc_audit/audit-events-ledger.jsonl`
**Testing**: pytest with mocked JudgmentClient + subprocess; ≥85% coverage on new modules
**Constraints**: mirror drift_interpretation API surface; no changes to existing modules; preserve weekly-audit path unchanged

## Phase 0 — Research (3 decisions)

- **D1 — Separate ledger vs extend drift ledger**: separate `audit-events-ledger.jsonl`. Cleaner query semantics; audit verdicts carry `audit_issue_number` field that drift ledger doesn't have.
- **D2 — Per-doc verdict vs whole-audit verdict**: per-doc. The audit signals an audit can be "partially clean" — 3 of 5 docs need no change, 1 needs a question, 1 needs an edit. Per-doc verdicts preserve granularity.
- **D3 — Question posting**: SINGLE consolidated comment per audit listing all JUDGMENT_REQUIRED docs + their questions. Avoids comment noise; operator reads one comment to see all questions.

## Phase 1 — Design

**Entities**: AuditVerdict (per spec); AuditInterpretationContext (input package). Both frozen dataclasses.

**Contract**: standalone module CLI (`python3 -m scripts.doc_audit.judgment.audit_interpretation --input-file <ctx.json>`); library API `interpret_audit(client, context) -> list[AuditVerdict]`.

## Project Structure

```
scripts/doc_audit/
├── judgment/
│   ├── audit_interpretation.py     # NEW
│   └── (existing modules unchanged)
├── prompts/
│   ├── audit_interpretation.prompt.md  # NEW
├── output/
│   ├── audit_ledger.py             # NEW
├── helpers/
│   └── handle_audit_routing.py     # MODIFIED (no-proposals branch)
└── config.toml                     # MODIFIED — [audit_interpretation] block

tests/doc_audit/
├── judgment/test_audit_interpretation.py  # NEW
├── output/test_audit_ledger.py            # NEW
└── helpers/test_handle_audit_routing.py   # MODIFIED — new branch coverage
```

## Branch Strategy

Planning base: `main`; merge target: `main`. Tier 3 — no Restic snapshot required.

## Open Decisions

None.
