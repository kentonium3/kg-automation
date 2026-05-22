# Research: Drift event auto-resolution via LLM judgment

**Mission**: `drift-event-auto-resolution-01KS8J32`
**Spec**: [spec.md](spec.md)
**Plan**: [plan.md](plan.md)
**Generated**: 2026-05-22

Phase 0 research decisions. Each decision captures: chosen approach, rationale, alternatives considered.

---

## D1 — Drift interpretation prompt structure

**Decision**: Cache-aware split. Stable system prompt (≥80% of total) carries the rules, output schema, examples, and constitutional guardrails reference. Dynamic user prompt carries the drift event diff, mapping config, and doc-target current state.

Structure:

```
[SYSTEM — cache_control: ephemeral]
You are the felix-doc-auditor drift interpreter. You receive a system
drift event and the documentation surfaces mapped to that drift. Decide
whether the docs need updating to reflect the new system state.

Return STRICT JSON in one of three shapes:
  (1) {verdict: "PROPOSED_EDIT", confidence, proposed_edit, rationale}
  (2) {verdict: "JUDGMENT_REQUIRED", confidence, question, rationale}
  (3) {verdict: "NO_CHANGE_NEEDED", confidence, rationale}

[Rules + examples + output schema + guardrails]

[USER]
Drift event:
  baseline: <name>
  mapping_id: <id>
  rationale: <from mapping>
  diff: |
    <unified diff>

Doc target(s):
  - path: <path>
    contents: |
      <full file or truncated per D2>
```

**Rationale**: matches the existing `tier_classification.prompt.md` cache pattern (per `scripts/doc_audit/prompts/tier_classification.prompt.md`). Cache prefix is ~80-90% of prompt by tokens, dynamic user portion is small.

**Alternatives considered**:
- Single non-cached prompt: rejected — Anthropic prompt-caching is established pattern in this codebase
- Two-stage prompting (first classify intent, then extract edit): rejected — adds latency and complexity; one call can do both

---

## D2 — Doc state truncation for large files

**Decision**: Tiered strategy by file size:
- ≤8KB: include full file
- >8KB and ≤32KB: include head (first 30 lines) + relevant region (extracted via diff context lines ±20) + tail (last 10 lines), separated by `...truncated...` markers
- >32KB: same as 8-32KB strategy but with stricter relevant-region bounds (±10 lines around diff)

**Rationale**:
- `service-inventory.json` (the most common target) is currently ~25KB — falls into the 8-32KB tier
- Full file is preferable when feasible (LLM reasons better with complete context)
- Diff-context bounds are deterministic and reproducible; not LLM-determined

**Alternatives considered**:
- Always full file: rejected — service-inventory.json could grow; future-proofing
- Always diff-context only: rejected — loses too much context; LLM may miss related sections
- LLM-driven summarization: rejected — adds another LLM call, defeats cache

**Implementation note**: the truncator is a pure helper function in `scripts/doc_audit/judgment/drift_interpretation.py` (no external dependencies). Tested independently.

---

## D3 — change_type enum extension

**Decision**: Add a single new value `drift_derived` to the `change_type` set in `scripts/doc_audit/data_model.py` (E-004 ProposedEdit docstring already lists 7 values; we add an 8th).

The translator (`scripts/doc_audit/routing/drift_to_proposed_edit.py`) sets `change_type = "drift_derived"` on every ProposedEdit built from a drift-interpretation verdict.

`tier_classification.py` does not need to know about `drift_derived` semantically — it reads `current_value` / `proposed_value` / `doc_path` to make its decision. The prompt in `tier_classification.prompt.md` may not have explicit handling for `drift_derived`; if tier_classification cannot confidently classify (it returns `JUDGMENT`), the existing escalation flow (debt_body_generation → DebtIssue) handles it correctly.

**Rationale**:
- Minimal change to data_model.py (single enum-string addition)
- Preserves C-003 (tier_classification surface unchanged)
- Defense-in-depth: even if tier_classification mis-handles a drift_derived edit, the JUDGMENT path is safe

**Alternatives considered**:
- Use one of the existing 7 values (e.g., `frontmatter_field_bump`): rejected — semantically wrong, hides drift origin
- Don't extend; have translator pick the closest existing value: rejected — same semantic-wrong problem
- Introduce a parallel `DriftDerivedEdit` dataclass: rejected — would force tier_classification to be modified or duplicated

---

## D4 — Audit ledger schema (JSONL)

**Decision**: New JSONL file `/data/services/security-monitor/logs/drift-events-ledger.jsonl`. One row per processed drift event. Schema:

```json
{
  "event_id": "string — drift-events.jsonl line cursor + timestamp",
  "timestamp_utc": "ISO 8601",
  "baseline": "string — e.g., openclaw-cron",
  "mapping_id": "string — e.g., openclaw-cron-drift",
  "verdict": "PROPOSED_EDIT | JUDGMENT_REQUIRED | NO_CHANGE_NEEDED | RETRY_EXHAUSTED",
  "confidence": "float in [0.0, 1.0]",
  "outcome": "auto_committed | pr_filed | issue_filed | auto_closed | retry_exhausted",
  "doc_paths": ["string"],
  "retry_count": "int",
  "latency_ms": "int — total end-to-end including retries",
  "tier_classification_outcome": "tier_a | tier_b | judgment | null — null when Moment 1 not invoked",
  "github_issue_number": "int | null"
}
```

The existing markdown activity log at `~/second-brain/agents/logs/doc-auditor-YYYY-MM-DD.md` is preserved unchanged per #343 C-005.

**Rationale**:
- JSONL is queryable for the NFR-001 triage rate metric
- Co-located with `drift-events.jsonl` for operator convenience
- Preserves the operator-readable markdown log (per #343)

**Alternatives considered**:
- Extend markdown log with new bullets: rejected — markdown isn't queryable
- Replace markdown log with JSONL: rejected — breaks operator workflow (#343 C-005)
- Sqlite ledger: rejected — JSONL is simpler, append-only-safe, no migration burden

---

## D5 — Backlog cutover script design

**Decision**: Single one-shot Python script `scripts/doc_audit/helpers/cutover_362.py` with these steps:

1. Read marker file `~/.config/doc-audit/cutover-362.done` — if exists, exit 0 (idempotent no-op)
2. Query GitHub for open `[doc-audit]` P3-candidate issues (search: `is:issue is:open label:P3-candidate "[doc-audit]" in:title repo:kentonium3/kg-automation`)
3. For each issue: post a comment "Closing as part of #362 cutover; the new pipeline will reprocess this drift event"; close issue
4. Reset cursor: `scripts/doc_audit/helpers/handle_drift_events.py --reset-cursor` (new flag) — sets cursor to 0
5. Write marker file
6. Exit 0

CLI flags: `--dry-run` (show what would happen), `--force` (override marker check).

**Rationale**:
- Idempotent marker prevents accidental re-run
- Single script keeps the cutover atomic and reviewable
- Dry-run mode allows verification before destructive action

**Alternatives considered**:
- Manual operator runbook: rejected — too error-prone for 10+ issues
- Bulk-close without comments: rejected — operator needs trail of why issues were closed
- Don't reset cursor; let new pipeline naturally lag: rejected — would leave a permanent backlog gap

---

## D6 — Retry/backoff implementation

**Decision**: Reuse the established pattern from `/data/services/openclaw/tasker-agent/AGENTS.md` error handling table:

```python
RETRY_DELAYS_SECONDS = (30, 60, 120)  # 3 attempts total

def call_with_retry(fn, *args, **kwargs):
    last_exc = None
    for delay in (0, *RETRY_DELAYS_SECONDS):
        if delay:
            time.sleep(delay)
        try:
            return fn(*args, **kwargs)
        except (APIError, TimeoutError, json.JSONDecodeError, SchemaError) as exc:
            last_exc = exc
            continue
    raise DriftInterpretationError("retry exhausted", cause=last_exc)
```

Retryable error classes: Anthropic API errors (5xx, rate-limit, timeout), JSON parse failures, schema validation failures.

**Rationale**:
- 30/60/120s pattern is documented across deployed tasker code; consistent operator mental model
- Total max wait: 30+60+120 = 210s (matches NFR-006 of ≤90s P95 — most calls won't retry)
- Schema validation failures retry: the LLM might produce malformed JSON once and clean JSON next call

**Alternatives considered**:
- Exponential backoff with jitter: rejected — slight benefit, breaks pattern parity
- 3s/6s/12s (fast retry): rejected — Anthropic rate-limit windows are seconds-to-minutes; longer waits more reliable
- No retry, immediate escalation: rejected — defeats automation goal; transient errors common

---

## D7 — Cost budget per drift event

**Decision**: Budget ≤2,000 tokens per call (NFR-003). Estimated actuals:

| Component | Tokens (estimated) |
|---|---|
| System prompt (cached) | ~1,200 |
| Diff (typical drift event) | ~150 |
| Mapping config + doc paths | ~50 |
| Doc target contents (8KB file) | ~2,000 |
| **Total input (worst case)** | **~3,400** |
| Output JSON | ~200 |

Worst-case is over the budget. **Mitigation**: D2 truncation strategy keeps doc target ≤8KB worth (~2,000 tokens). For pathological files >32KB, the relevant-region-only strategy reduces this to ~500 tokens.

At Haiku 4.5 pricing (input $0.001/1K, output $0.005/1K), worst-case per-call: ~$0.005. At 10 drift events/day with 2 LLM calls per PROPOSED_EDIT path: ~$0.10/day. Annualized ~$36. **Cost is not a concern.**

**Rationale**: budget covers worst case; D2 truncation prevents pathological blowup; total spend is trivial.

---

## D8 — Test fixture strategy

**Decision**: Synthetic drift-event fixtures derived from the 3 real piling-up baselines, plus mocked `JudgmentClient` (no live Anthropic calls in unit tests):

Fixture files (in `tests/doc_audit/fixtures/`):

| Fixture | Source | Expected verdict |
|---|---|---|
| `drift_event_openclaw_cron.json` | #351, #353 etc. (`deliveryMode "none" → "announce"`) | NO_CHANGE_NEEDED (service-inventory.json doesn't track that field) |
| `drift_event_openclaw_json_hash.json` | #352, #354 etc. (hash change) | JUDGMENT_REQUIRED (hash drift needs human interpretation of what changed) |
| `drift_event_systemd_dropins.json` | #368 (new dropin file) | PROPOSED_EDIT (add new entry to service-inventory.json) |

Plus mocked Anthropic responses for each verdict shape (golden JSON files).

E2E test: one real drift event flows through the full pipeline with mocked LLM responses. Asserts: audit ledger entry written, correct routing decision, no GitHub side effects (issue filing mocked).

**Rationale**:
- Real baselines give realistic prompt content
- Three baselines cover all three verdict types
- Mocked SDK keeps tests fast, deterministic, and free

**Alternatives considered**:
- Live Anthropic calls in integration tests: rejected — flaky, slow, costly, and Kent's memory `feedback_live_integration_tests.md` rejects this class of test
- Property-based fuzz testing of the JSON parser: deferred — possible v2 hardening; out of scope for v1
- Recording-replay (VCR) of real Anthropic responses: rejected — adds dependency, fixture management; mocked SDK is simpler

---

## D9 — config.toml flag mechanism

**Decision**: Read the config per-tick (no file watcher). The flag lives in:

```toml
[drift_interpretation]
enabled = true
```

`handle_drift_events.py` reads `config.toml` at the start of each invocation. If `[drift_interpretation].enabled = false`, the module skips Moment 0 entirely and falls back to the pre-#362 behavior (file `[doc-audit]` issues without judgment).

**Rationale**:
- Cron-tick cadence makes per-invocation read sufficient (no need for real-time toggle)
- Operator can flip the flag and the next tick honors it (≤15 min latency for cron sweeps; ≤60s if manually triggered)
- No file-watcher = no new daemon dependency

**Alternatives considered**:
- Environment variable: rejected — harder to discover/document; persists awkwardly
- systemd drop-in: rejected — heavier change, requires systemd reload
- In-memory toggle via signal: rejected — overkill

---

## D10 — CLI surface for drift_interpretation

**Decision**: Standalone CLI mirroring `scripts/doc_audit/judgment/tier_classification.py` invocation pattern:

```
python3 -m scripts.doc_audit.judgment.drift_interpretation \
  --input-file /tmp/drift_context.json \
  --output-file /tmp/verdict.json \
  --model claude-haiku-4-5-20251001 \
  --api-key-path /data/services/openclaw/secrets/anthropic
```

Stdin JSON in / stdout JSON out when `--input-file` / `--output-file` omitted. Exit codes per `contracts/cli.md`: 0/1/3/5.

**Rationale**:
- Consistency with existing `tier_classification` CLI shape
- Enables manual replay, dry-run testing, single-event debugging
- Required by FR-012 (config-toggle scenario testing) and quickstart pre-flight steps

**Alternatives considered**:
- No standalone CLI (library only): rejected — operator can't dry-run; debugging is painful
- argparse-only without --input-file: rejected — large JSON on argv is awkward

---

## Open questions / deferred items

- None for v1. All planning questions resolved.
- v2 candidate: per-mapping confidence threshold override (currently global 0.80) — defer until operator usage data informs whether some mappings need different thresholds.
- v2 candidate: drift event de-duplication across cron runs — exists in handle_drift_events.py docstring as future enhancement; out of scope for #362.
