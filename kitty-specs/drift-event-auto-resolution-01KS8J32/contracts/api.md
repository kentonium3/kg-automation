# Contract: Python API surface

**Mission**: `drift-event-auto-resolution-01KS8J32`

The public Python API surface introduced by this mission. Importable from `scripts/doc_audit/` with `PYTHONPATH=scripts/`.

---

## `drift_interpretation.interpret(...)`

```python
def interpret(
    client: JudgmentClient,
    context: DriftInterpretationContext,
    *,
    model: str = DEFAULT_MODEL,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
    no_retry: bool = False,
) -> DriftVerdict:
    """Moment 0 LLM judgment for a single drift event.

    Builds the cache-aware prompt, calls the Anthropic API via the
    shared JudgmentClient, parses + validates the response, and
    returns a DriftVerdict. Raises DriftInterpretationError on
    unrecoverable failures (after retry policy exhausted).

    Args:
        client: shared JudgmentClient instance (no SDK creation here)
        context: drift event input package (E2)
        model: Anthropic model identifier (default haiku-4-5)
        timeout: per-attempt timeout in seconds (NFR-002 budget)
        confidence_threshold: gate for PROPOSED_EDIT / NO_CHANGE_NEEDED demotion (default 0.80)
        no_retry: skip retry policy (testing only)

    Returns:
        DriftVerdict (E1) — verdict guaranteed to satisfy E1 invariants

    Raises:
        DriftInterpretationError: after retry exhaustion or unrecoverable schema violation
    """
```

**Caching contract**: the system-prompt portion of the call MUST be marked with `cache_control: ephemeral` per existing `tier_classification.py` pattern. Cache prefix MUST be ≥80% of prompt by tokens.

**Confidence demotion**: if returned verdict is PROPOSED_EDIT or NO_CHANGE_NEEDED and confidence < `confidence_threshold`, `interpret()` returns a NEW DriftVerdict with `verdict="JUDGMENT_REQUIRED"` and the original proposed edit/rationale folded into the `rationale` field. Caller does NOT need to re-check.

---

## `drift_to_proposed_edit.build(...)`

```python
def build(
    verdict: DriftVerdict,
    context: DriftInterpretationContext,
) -> ProposedEdit:
    """Translate a PROPOSED_EDIT DriftVerdict into a ProposedEdit.

    Pre-conditions:
        - verdict.verdict == "PROPOSED_EDIT"
        - verdict.confidence >= 0.80 (caller already gated)
        - verdict.proposed_edit is not None

    Returns:
        ProposedEdit with change_type="drift_derived" and evidence_source
        derived from the drift event's baseline + event_id.

    Raises:
        ValueError: if pre-conditions not met OR proposed_edit.doc_path
            is not in context.doc_targets (out-of-set rejection)
    """
```

---

## `drift_ledger.append(...)`

```python
def append(
    entry: AuditLedgerEntry,
    *,
    ledger_path: Path = DEFAULT_LEDGER_PATH,
) -> None:
    """Append one ledger entry to the drift-events JSONL ledger.

    Write is atomic (tempfile + rename); the ledger file may grow
    indefinitely (no rotation in v1).

    Args:
        entry: AuditLedgerEntry to serialize (E3)
        ledger_path: target JSONL file

    Raises:
        OSError: if write fails (caller's exit 1 path)
    """


def read_window(
    *,
    ledger_path: Path = DEFAULT_LEDGER_PATH,
    days: int = 7,
) -> list[AuditLedgerEntry]:
    """Read ledger entries within the trailing N-day window.

    Used by drift_ledger CLI subcommands. Does NOT parse the entire
    ledger if file is huge — implementation tails from end-of-file
    forward until older-than-window entries.
    """


def compute_triage_rate(
    *,
    ledger_path: Path = DEFAULT_LEDGER_PATH,
    days: int = 7,
) -> float:
    """Compute count(JUDGMENT_REQUIRED) / count(*) over trailing window.

    The NFR-001 success criterion metric. Returns 0.0 if no entries.
    """
```

---

## `handle_drift_events.process_events(...)` (existing, EXTENDED)

The existing library entry point keeps its signature. Internal behavior is extended to invoke Moment 0 when the config flag is enabled.

```python
def process_events(...) -> ProcessResult:
    """Process drift-events.jsonl from cursor; invoke Moment 0 per event.

    Existing contract preserved (per C-002). New behavior:
    - If `[drift_interpretation].enabled == true` in config.toml, each
      mapped event is passed to drift_interpretation.interpret() and
      routed by verdict.
    - On retry exhaustion: ledger writes RETRY_EXHAUSTED, then falls
      back to pre-#362 issue-filing behavior (FR-009).
    - ProcessResult gains the existing fields plus aggregate counts of
      verdict outcomes (PROPOSED_EDIT_routed, JUDGMENT_REQUIRED_filed,
      NO_CHANGE_NEEDED_closed, RETRY_EXHAUSTED).
    """
```

---

## `cutover_362.run(...)`

```python
def run(*, dry_run: bool = False, force: bool = False) -> CutoverResult:
    """Idempotent one-shot cutover script.

    Closes the 13 known pre-#362 [doc-audit] P3 issues and resets the
    drift-events cursor. Writes ~/.config/doc-audit/cutover-362.done
    on success.

    Args:
        dry_run: print what would happen; no mutations
        force: ignore marker check; re-run anyway

    Returns:
        CutoverResult: {issues_closed: list[int], cursor_reset: bool,
                         marker_written: bool, dry_run: bool}
    """
```

---

## Pre-conditions / post-conditions

### `interpret()`

**Pre**:
- `client` is a valid `JudgmentClient` instance with API key loaded
- `context.doc_targets` is non-empty
- `context.diff` is non-empty
- API key file exists and is readable

**Post**:
- Returns a valid `DriftVerdict` satisfying all E1 invariants
- May have written to driver's activity log via existing pattern
- Does NOT write to the drift-events ledger (caller's responsibility)

### `build()` (translator)

**Pre**:
- `verdict.verdict == "PROPOSED_EDIT"`
- `verdict.confidence >= 0.80`
- `verdict.proposed_edit["doc_path"]` ∈ {t.path for t in context.doc_targets}

**Post**:
- Returns `ProposedEdit` with `change_type == "drift_derived"`, `tier == "tier_b"` (placeholder), `confidence == "high"`

### `append()` (ledger)

**Pre**:
- `entry` satisfies E3 invariants
- `ledger_path.parent` exists and is writable

**Post**:
- Ledger file has one new line at the end
- File is left in a consistent state (no partial writes)

---

## Module structure summary

| Module | Public surface |
|---|---|
| `scripts/doc_audit/judgment/drift_interpretation.py` | `interpret()`, `DriftVerdict`, `DriftInterpretationContext`, `DocTarget`, `DriftInterpretationError`, CLI `main()` |
| `scripts/doc_audit/routing/drift_to_proposed_edit.py` | `build()` |
| `scripts/doc_audit/output/drift_ledger.py` | `append()`, `read_window()`, `compute_triage_rate()`, `AuditLedgerEntry`, CLI `main()` |
| `scripts/doc_audit/helpers/cutover_362.py` | `run()`, `CutoverResult`, CLI `main()` |
| `scripts/doc_audit/helpers/handle_drift_events.py` (modified) | existing public surface; new Moment 0 invocation behind config flag |
| `scripts/doc_audit/data_model.py` (modified) | `ProposedEdit` docstring extended to list `drift_derived` as 8th `change_type` value |
