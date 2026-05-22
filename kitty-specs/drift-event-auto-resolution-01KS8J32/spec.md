# Spec: Drift event auto-resolution via LLM judgment

**Mission**: `drift-event-auto-resolution-01KS8J32`
**Mission ID**: `01KS8J321F8KE7369R3DA02329`
**Source**: GitHub issue [kentonium3/kg-automation#362](https://github.com/kentonium3/kg-automation/issues/362)
**Risk tier**: Tier 3 — Logic / Workflow (standard)
**Generated**: 2026-05-22

## Overview

The post-#343 doc-audit pipeline detects system state changes via `audit.sh` and routes them to documentation surfaces. Today, drift-derived events file `[doc-audit]` GitHub issues unconditionally and require operator triage. This feature adds an LLM-judgment step ("Moment 0") that classifies each drift event as `PROPOSED_EDIT`, `JUDGMENT_REQUIRED`, or `NO_CHANGE_NEEDED` and routes accordingly. The goal: reduce operator triage burden so that the operator spends time on judgment-only cases, not "review the diff and decide".

The architecture mirrors the existing `handle_audit_routing.py` (commit-derived) LLM-judgment surface — same `JudgmentClient`, same cache-aware prompt pattern, same defense-in-depth schema validation — but operates on drift events instead of commit-derived audit issues. PROPOSED_EDIT verdicts flow into the existing `tier_classification` surface so safety gates are preserved.

## User Scenarios & Testing

### Primary user

**Kent (operator)** runs the doc-audit pipeline on office2 via a systemd user timer. His current cost per drift event is several minutes of triage. With ~3-10 drift events/day across 3 baselines, the backlog grows faster than he can process it (10+ unhandled `[doc-audit]` P3 issues as of 2026-05-22). He wants triage limited to genuine judgment calls.

### Acceptance scenarios

#### Scenario A — Auto-applied edit (Tier A path)

- **Given**: `audit.sh` detects a drift event mapped by `signal-to-doc-map.json`
- **When**: the drift_interpretation judgment evaluates the diff against the current doc state
- **Then**: if verdict is `PROPOSED_EDIT` with confidence ≥0.80, the proposed edit flows through existing `tier_classification` → Tier A → auto-commit with descriptive message
- **And**: an audit ledger entry is appended with `verdict=PROPOSED_EDIT`, `confidence`, doc paths affected, and commit hash

#### Scenario B — Escalation with specific question (judgment path)

- **Given**: a drift event where the LLM cannot determine the doc change with high confidence
- **When**: the verdict is `JUDGMENT_REQUIRED` or confidence is <0.80 on a `PROPOSED_EDIT`
- **Then**: a `[doc-audit]` issue is filed with the LLM's specific question (not "review the diff")
- **And**: the operator can answer the question directly to resolve

#### Scenario C — Auto-closed event (no change needed)

- **Given**: a drift event whose verdict is `NO_CHANGE_NEEDED` with confidence ≥0.80
- **When**: the drift was for a field/state not tracked in the target docs
- **Then**: the event is auto-closed with a one-line summary in the audit ledger
- **And**: no GitHub issue is filed; no operator burden is created

#### Scenario D — LLM unavailable (retry policy)

- **Given**: a drift event where the Anthropic API is unreachable, rate-limited, or returns malformed JSON
- **When**: the LLM call fails
- **Then**: the system retries with exponential backoff at 30s, 60s, 120s
- **And**: if all 3 retries fail, the event is escalated to the operator via the pre-#362 `[doc-audit]` issue path with retry diagnostics in the issue body

#### Scenario E — Backlog replay on first run

- **Given**: 10+ existing `[doc-audit]` P3 issues filed before this feature (#351-#360, #368-#370)
- **When**: the new pipeline runs for the first time after deploy
- **Then**: existing pre-#362 `[doc-audit]` issues are closed; the cursor is reset to allow reprocessing
- **And**: originating drift events are reprocessed via Moment 0

#### Scenario F — Rollback via config flag

- **Given**: a defect surfaces post-deploy (e.g., spurious PROPOSED_EDIT verdicts on a baseline)
- **When**: the operator sets `drift_interpretation.enabled = false` in `scripts/doc_audit/config.toml`
- **Then**: the pipeline immediately reverts to pre-#362 deterministic-only behavior on the next run
- **And**: in-flight audit ledger entries remain intact; no data loss

### Edge cases

- Malformed LLM JSON response → demote to `JUDGMENT_REQUIRED` with diagnostic message
- LLM returns `confidence` outside `[0.0, 1.0]` → demote to `JUDGMENT_REQUIRED`
- Drift event maps to a guardrailed doc path (per SKILL.md §4.3) → `tier_classification` short-circuits to `JUDGMENT` regardless of LLM verdict (defense-in-depth)
- LLM proposes an edit to a doc path NOT in the mapping's `doc_targets` list → reject as out-of-scope; demote to `JUDGMENT_REQUIRED`
- Multiple drift events fire in rapid succession (cron run) → each processed independently; no cross-event dependencies
- Same baseline keeps drifting day-over-day → Moment 0 invoked for each event (no dedup in v1; existing behavior preserved)
- Anthropic SDK changes signature mid-deploy → schema validation defense-in-depth catches it; demote to `JUDGMENT_REQUIRED`

## Functional Requirements

| ID | Description | Status |
|---|---|---|
| FR-001 | The system shall invoke a new "drift interpretation" LLM judgment moment for every mapped drift event before issue filing | Planned |
| FR-002 | The drift_interpretation judgment shall return one of three verdicts: `PROPOSED_EDIT`, `JUDGMENT_REQUIRED`, `NO_CHANGE_NEEDED` | Planned |
| FR-003 | The drift_interpretation judgment shall return an explicit `confidence` value in `[0.0, 1.0]` alongside its verdict | Planned |
| FR-004 | `PROPOSED_EDIT` verdicts with confidence ≥0.80 shall be routed through the existing `tier_classification` surface | Planned |
| FR-005 | `PROPOSED_EDIT` verdicts with confidence <0.80 shall be demoted to `JUDGMENT_REQUIRED` with the proposed edit attached as context | Planned |
| FR-006 | `JUDGMENT_REQUIRED` verdicts shall produce a `[doc-audit]` GitHub issue containing the LLM's specific question, not a generic "review the diff" prompt | Planned |
| FR-007 | `NO_CHANGE_NEEDED` verdicts with confidence ≥0.80 shall auto-close the drift event with a one-line summary in the audit ledger; no GitHub issue is filed | Planned |
| FR-008 | When the LLM call fails (timeout, network, malformed response, schema violation), the system shall retry with exponential backoff at 30s, 60s, 120s | Planned |
| FR-009 | After 3 failed retries, the system shall escalate to the operator via the pre-#362 `[doc-audit]` issue path, with retry diagnostics in the issue body | Planned |
| FR-010 | The audit ledger shall capture `verdict`, `confidence`, doc paths affected, and `outcome` per drift event | Planned |
| FR-011 | Constitutional guardrails (per SKILL.md §4.3) shall apply unchanged — guardrailed doc paths are never auto-edited even if the LLM proposes an edit to them | Planned |
| FR-012 | A configuration flag `drift_interpretation.enabled` in `scripts/doc_audit/config.toml` shall toggle the new judgment moment on/off without code changes | Planned |
| FR-013 | When `drift_interpretation.enabled = false`, the system shall behave identically to the pre-#362 deterministic-only pipeline | Planned |
| FR-014 | On first run after deploy, the cursor shall be reset to allow reprocessing of the existing piled-up drift events from `drift-events.jsonl` | Planned |
| FR-015 | The 10+ pre-existing `[doc-audit]` P3 issues (#351-#360, #368-#370) shall be closed as part of cutover, with a comment noting the new pipeline will reprocess them | Planned |
| FR-016 | Existing `Doc audit:` (commit-derived) issue processing in `handle_audit_routing.py` shall remain unchanged and continue to function | Planned |
| FR-017 | The LLM prompt shall be cache-aware (stable system prompt + dynamic user content), matching the existing pattern in `scripts/doc_audit/prompts/tier_classification.prompt.md` | Planned |

## Non-Functional Requirements

| ID | Description | Threshold | Status |
|---|---|---|---|
| NFR-001 | Operator-triage rate over the 7-day window post-deploy: `count(verdict='JUDGMENT_REQUIRED') / count(*)` per audit ledger | ≤30% | Planned |
| NFR-002 | LLM call latency per drift event (P95, single attempt, excluding retries) | ≤15 seconds | Planned |
| NFR-003 | LLM token cost per drift event (input + output, single attempt, average) | ≤2,000 tokens | Planned |
| NFR-004 | Test coverage on new `drift_interpretation.py` module | ≥85% | Planned |
| NFR-005 | Successful event processing rate end-to-end (no errors propagating past retry policy) | ≥98% | Planned |
| NFR-006 | Time from drift event detection to final verdict (P95, including any retries) | ≤90 seconds | Planned |
| NFR-007 | Rollback time via config flag (`drift_interpretation.enabled = false` to next clean run) | ≤60 seconds | Planned |

## Constraints

| ID | Description | Status |
|---|---|---|
| C-001 | The existing `Doc audit:` (commit-derived) issue processing path shall not be modified | Locked |
| C-002 | The auto-detection layer (`audit.sh`) shall not be modified | Locked |
| C-003 | The existing `tier_classification`, `cross_file_implication`, `debt_body_generation` judgment surfaces shall not be modified | Locked |
| C-004 | No new third-party dependencies; the existing Anthropic SDK and `JudgmentClient` are reused | Locked |
| C-005 | The new judgment module shall mirror the structure of the existing `tier_classification.py` (cache-aware prompt, `JudgmentClient` reuse, schema validation defense-in-depth) | Locked |
| C-006 | LLM output shall be strict JSON; malformed responses demote to `JUDGMENT_REQUIRED` (per `tier_classification.py` precedent) | Locked |
| C-007 | The feature is Tier 3 (Logic/Workflow) — no Restic snapshot required; rollback is via config flag + redeploy of prior commit | Locked |
| C-008 | Backlog replay shall handle the 10+ current `[doc-audit]` P3 issues without manual operator triage of each | Locked |
| C-009 | The LLM model shall be `claude-haiku-4-5-20251001` (same as existing `JudgmentClient` default) | Locked |
| C-010 | Shadow-mode rollout was explicitly rejected during spec-readiness; cut-over is immediate, relying on existing Tier A/B/judgment guardrails | Locked |

## Success Criteria

1. **Operator-triage rate**: ≤30% of detected drift events require operator triage over the 7-day post-deploy window (measured via audit ledger).
2. **Pipeline reliability**: ≥98% of drift events produce a clean verdict (`PROPOSED_EDIT` / `JUDGMENT_REQUIRED` / `NO_CHANGE_NEEDED`) without manual intervention.
3. **Latency**: 95th percentile time from drift event detection to verdict is ≤90 seconds (including any retries).
4. **No regression**: existing `Doc audit:` path continues to function correctly; no spurious Tier A auto-commits on guardrailed paths.
5. **Backlog cleared**: the 10+ existing `[doc-audit]` P3 issues are closed and reprocessed via the new pipeline on first run.
6. **Rollback verified**: `drift_interpretation.enabled = false` reverts to pre-#362 behavior in ≤60 seconds with no data loss.

## Key Entities

### DriftVerdict

Structured LLM output. Three valid `verdict` values: `PROPOSED_EDIT`, `JUDGMENT_REQUIRED`, `NO_CHANGE_NEEDED`. `confidence` ∈ [0.0, 1.0]. `proposed_edit` present only when verdict is PROPOSED_EDIT; `question` present only when verdict is JUDGMENT_REQUIRED; `rationale` always present.

### DriftInterpretationContext

The input to the LLM judgment:
- Drift event metadata (id, baseline, signal source, timestamp)
- The diff (unified format from `drift-events.jsonl`)
- The signal mapping config (mapping id, rationale, doc_targets)
- Current doc state for each doc_target (full file contents — drift-event doc targets are bounded by mapping)

### AuditLedgerEntry (extended)

Existing audit ledger row, extended with:
- `verdict`: `PROPOSED_EDIT` | `JUDGMENT_REQUIRED` | `NO_CHANGE_NEEDED` | `RETRY_EXHAUSTED`
- `confidence`: float in [0.0, 1.0]
- `outcome`: `auto_committed` | `pr_filed` | `issue_filed` | `auto_closed` | `retry_exhausted`

### DriftInterpretationError

Exception class raised on unrecoverable failures (JSON parse error, schema violation, API error after all retries exhausted). Carries diagnostic context for inclusion in the escalation issue body.

## Assumptions

1. The current drift-event volume (~3-10 per day across 3 baselines) means LLM call cost is negligible at Haiku 4.5 rates.
2. The existing audit ledger format supports schema extension (additional columns) without breaking downstream consumers.
3. The 30s/60s/120s backoff policy is sufficient for transient API issues; this is the established pattern in deployed tasker code (per `/data/services/openclaw/tasker-agent/AGENTS.md` error handling table).
4. Operator review will catch any LLM false-positive Tier A auto-commits via existing git/PR review channels.
5. The full file contents of each `doc_target` fit within the LLM context window at Haiku 4.5; if not, the plan phase will introduce truncation/summarization.

## Out of Scope

- Replacing or modifying `audit.sh`
- Changing the existing `Doc audit:` commit-derived issue processing
- Adding new baselines or new signal mappings (purely adding judgment to the existing flow)
- De-duplication of repeat-drift across cron runs (existing behavior preserved; future enhancement noted in `handle_drift_events.py` docstring)
- Shadow-mode rollout (explicitly rejected during spec-readiness)
- Per-mapping or per-signal exclusion lists (defense relies on existing SKILL.md §4.3 guardrails at the tier_classification layer)

## Dependencies

- #343 (architectural rework: the scripts-first driver pattern this builds on)
- #278 (signal-driven doc-audit pipeline epic — parent)
- Existing modules: `scripts/doc_audit/judgment/{client.py, tier_classification.py}` (reused unchanged)
- Existing prompts: `scripts/doc_audit/prompts/tier_classification.prompt.md` (referenced for cache-aware pattern)

## Cross-References

- GitHub issue: kentonium3/kg-automation#362
- Issues in scope for backlog replay: #351, #352, #353, #354, #355, #356, #357, #358, #359, #360, #368, #369, #370
- Risk tier protocol: `docs/design/architecture/data/change-risk-taxonomy.json` (Tier 3)
- Memory: `feedback_scripts_vs_llm.md` (operator pattern being applied)
