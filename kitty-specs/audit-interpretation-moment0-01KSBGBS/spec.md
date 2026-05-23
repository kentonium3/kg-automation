# Spec: Audit interpretation Moment 0 (commit-derived path)

**Mission**: `audit-interpretation-moment0-01KSBGBS`
**Mission ID**: `01KSBGBS9BBDWV2Z28FESVJ9KQ`
**Source**: GitHub issue [#400](https://github.com/kentonium3/kg-automation/issues/400)
**Risk tier**: Tier 3 — Logic / Workflow
**Generated**: 2026-05-23

## Overview

Apply the #362/#391 Moment 0 architecture to commit-derived `Doc audit:` issues. Today's `handle_audit_routing.py` only runs deterministic pattern matching; if no patterns fire, it exits with "no proposals" and leaves the operator to manually triage a generic 14-item checklist. This mission adds an LLM judgment surface that evaluates each in-scope doc against the commit diff and routes per verdict (PROPOSED_EDIT → tier_classification → auto-commit/PR; JUDGMENT_REQUIRED → specific question posted; NO_CHANGE_NEEDED → auto-close when all docs clean).

Mirrors `drift_interpretation.py` 1:1 structurally — same JudgmentClient, cache-aware prompt, defense-in-depth schema validation, ≥0.80 confidence threshold.

## User Scenarios & Testing

### Primary user

Kent operates the doc-audit pipeline. Today, 11 stuck `Doc audit:` issues sit open with no actionable LLM analysis. Post-fix, each audit's in-scope docs are individually evaluated; auto-resolution rate should mirror #362's target (≤30% operator triage).

### Acceptance scenarios

#### Scenario A — Auto-close when all docs clean

- **Given**: a `Doc audit:` issue with 5 in-scope docs and a commit diff
- **When**: `audit_interpretation` evaluates each doc → all 5 return NO_CHANGE_NEEDED (conf ≥0.80)
- **Then**: the audit is auto-closed with a summary comment listing the 5 docs as "clean per LLM check"
- **And**: one ledger entry per doc records the verdict

#### Scenario B — Mixed verdicts (some need updating)

- **Given**: same audit with 5 in-scope docs
- **When**: evaluation returns 3 NO_CHANGE_NEEDED + 1 JUDGMENT_REQUIRED + 1 PROPOSED_EDIT (conf 0.85)
- **Then**: PROPOSED_EDIT routes through existing tier_classification (may yield Tier A auto-commit, Tier B PR, or judgment debt-issue)
- **And**: JUDGMENT_REQUIRED appends a specific question to the audit issue body
- **And**: audit stays open (because of the unresolved JUDGMENT_REQUIRED)
- **And**: the issue body now shows specific actionable questions, not a generic checklist

#### Scenario C — Config disabled (rollback)

- **Given**: `[audit_interpretation].enabled = false`
- **When**: cron tick processes a `Doc audit:` signal
- **Then**: behavior is identical to today's no-proposals exit (lock released + "no automatable edits" comment from the recently-deployed handle_audit_routing fix)

#### Scenario D — LLM unavailable

- **Given**: Anthropic API errors during evaluation
- **When**: retry policy (30/60/120s) exhausts
- **Then**: fall back to today's no-proposals path (lock released + operator-review comment)
- **And**: ledger row written with verdict=RETRY_EXHAUSTED

### Edge cases

- Audit body's in-scope docs list includes paths that don't exist → skip (log warning)
- Doc file is huge (>32KB) → apply truncation strategy from drift_interpretation D2
- LLM proposes edit to a path NOT in the in-scope list → semantic violation → demote to JUDGMENT_REQUIRED
- Mixed verdicts where the PROPOSED_EDIT path raises (Tier A fails) → keep audit open with what was posted; don't half-close
- Weekly audit (no triggering SHA) → no diff to evaluate → skip Moment 0 entirely; existing weekly behavior preserved

## Functional Requirements

| ID | Description | Status |
|---|---|---|
| FR-001 | New `scripts/doc_audit/judgment/audit_interpretation.py` shall expose `interpret_audit(client, audit, diff, in_scope_docs, repo_root) -> list[AuditVerdict]` | Planned |
| FR-002 | Each `AuditVerdict` shall contain `doc_path`, `verdict`, `confidence`, optional `proposed_edit` / `question`, `rationale` | Planned |
| FR-003 | Verdict values: `PROPOSED_EDIT`, `JUDGMENT_REQUIRED`, `NO_CHANGE_NEEDED` (mirror drift_interpretation) | Planned |
| FR-004 | PROPOSED_EDIT with confidence ≥0.80 shall route through existing `tier_classification` (build ProposedEdit; tier_classification assigns Tier A/B/judgment) | Planned |
| FR-005 | PROPOSED_EDIT with confidence <0.80 shall demote to JUDGMENT_REQUIRED | Planned |
| FR-006 | JUDGMENT_REQUIRED shall result in a comment posted to the audit issue with the LLM's specific question (one comment per JUDGMENT_REQUIRED doc, OR consolidated single comment listing all — plan decides) | Planned |
| FR-007 | NO_CHANGE_NEEDED with confidence ≥0.80 shall produce only a ledger entry | Planned |
| FR-008 | If ALL in-scope docs are NO_CHANGE_NEEDED, the audit issue shall be auto-closed with a summary comment | Planned |
| FR-009 | If ANY doc is JUDGMENT_REQUIRED (after demotion), audit stays open | Planned |
| FR-010 | LLM failures shall retry with exponential backoff (30s/60s/120s) per #362 D6 pattern | Planned |
| FR-011 | After all retries fail, fall back to today's no-proposals handler (lock release + operator-review comment) | Planned |
| FR-012 | New ledger entries shall be appended to `/data/services/openclaw/state/doc_audit/audit-events-ledger.jsonl` (separate from drift-events-ledger to keep query semantics simple) | Planned |
| FR-013 | A configuration flag `[audit_interpretation].enabled` shall toggle the new path on/off; when off, behavior is identical to today's no-proposals exit | Planned |
| FR-014 | The system prompt shall be cache-aware (stable system prompt + dynamic per-doc user content) matching the `drift_interpretation.prompt.md` pattern | Planned |
| FR-015 | Existing drift-event Moment 0 path shall not be modified | Planned |

## Non-Functional Requirements

| ID | Description | Threshold | Status |
|---|---|---|---|
| NFR-001 | Operator-triage rate over 7-day post-deploy window | ≤30% | Planned |
| NFR-002 | LLM call latency per doc (P95, single attempt) | ≤15 seconds | Planned |
| NFR-003 | Test coverage on new `audit_interpretation.py` module | ≥85% | Planned |
| NFR-004 | Full doc_audit + escalation + habits + enrichment test suite regression | 100% pass | Planned |
| NFR-005 | Per-audit total latency (P95, all in-scope docs processed) | ≤120 seconds for ≤10 docs | Planned |

## Constraints

| ID | Description | Status |
|---|---|---|
| C-001 | The existing `tier_classification`, `cross_file_implication`, `debt_body_generation`, `drift_interpretation` modules shall not be modified | Locked |
| C-002 | The deterministic pattern-matching path in handle_audit_routing.py (when proposals IS non-empty) shall not be modified | Locked |
| C-003 | The today-merged no-proposals fix (release lock + post comment) shall serve as the fallback when audit_interpretation is disabled OR retries exhaust | Locked |
| C-004 | Mirror drift_interpretation.py structure (cache-aware prompt, JudgmentClient reuse, defense-in-depth schema validation) | Locked |
| C-005 | No new third-party dependencies | Locked |
| C-006 | Weekly audits (no triggering SHA, empty diff) shall skip Moment 0 entirely | Locked |
| C-007 | Rollback: config flag flip + redeploy prior commit | Locked |

## Success Criteria

1. Currently-stuck 11 audits (#350, #363-365, #373, #377, #395-399) re-processed; majority auto-resolve OR have specific operator-visible questions
2. Triage rate ≤30% over 7-day window (NFR-001)
3. No regression on existing audit-routing tests
4. Rollback verified via config flag

## Key Entities

### AuditVerdict (per-doc, frozen dataclass)

```python
@dataclass(frozen=True)
class AuditVerdict:
    doc_path: str
    verdict: str            # "PROPOSED_EDIT" | "JUDGMENT_REQUIRED" | "NO_CHANGE_NEEDED"
    confidence: float       # [0.0, 1.0]
    rationale: str
    proposed_edit: dict | None = None  # {current_value, proposed_value, change_summary}
    question: str | None = None
```

### AuditInterpretationContext

Input package: `{audit_issue, commit_sha, diff, in_scope_doc_paths, doc_contents_map}`. Built by handle_audit_routing.py before invoking interpret_audit.

## Assumptions

1. The `cross_file_implication` LLM helper (existing) is NOT a substitute for this — it operates on a different schema and doesn't produce per-doc verdicts
2. Most commit-derived audits will have 3-15 in-scope docs → reasonable per-audit LLM call volume
3. Same doc-truncation strategy from drift_interpretation D2 applies (full ≤8KB; head+region+tail for ≤32KB; region-only >32KB)

## Out of Scope

- Refactoring drift_interpretation + audit_interpretation into a single generalized module (defer to a v2 follow-on if maintenance burden grows)
- Removing the deterministic pattern-matching path (preserved unchanged per C-002)
- Changes to gh_issue.py signal source

## Dependencies

- #362 (drift Moment 0 — pattern source)
- #391 (drift Moment 0 wiring fix — caller-pattern precedent)
- #343 (post-refactor driver introduced the gap this fixes)
- Just-merged bug fix (commit `bf17c3cf` — no-proposals lock release) serves as the fallback path

## Cross-References

- Issue: kentonium3/kg-automation#400
- Pattern source: `scripts/doc_audit/judgment/drift_interpretation.py` + `scripts/doc_audit/routing/drift_moment0.py`
- Today's stuck audits validating the gap: #350, #363, #364, #365, #373, #377, #395, #396, #397, #398, #399
