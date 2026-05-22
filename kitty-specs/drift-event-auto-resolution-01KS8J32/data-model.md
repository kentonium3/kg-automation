# Data Model: Drift event auto-resolution via LLM judgment

**Mission**: `drift-event-auto-resolution-01KS8J32`
**Spec**: [spec.md](spec.md)
**Plan**: [plan.md](plan.md)
**Generated**: 2026-05-22

Six entities. Five are new (E1, E2, E3, E5, E6). One is an existing dataclass extended in place (E4).

---

## E1 — DriftVerdict

**Purpose**: Structured output of the Moment 0 drift_interpretation LLM call.

**Location**: `scripts/doc_audit/judgment/drift_interpretation.py`

```python
@dataclass(frozen=True)
class DriftVerdict:
    """LLM-produced verdict on a drift event.

    Three valid `verdict` values produce three distinct downstream behaviors:
    - PROPOSED_EDIT (conf ≥0.80) → translate to ProposedEdit, run tier_classification
    - PROPOSED_EDIT (conf <0.80) → demote to JUDGMENT_REQUIRED, file issue with proposed edit as context
    - JUDGMENT_REQUIRED → file [doc-audit] issue with LLM's specific question
    - NO_CHANGE_NEEDED (conf ≥0.80) → auto-close drift event with summary
    - NO_CHANGE_NEEDED (conf <0.80) → demote to JUDGMENT_REQUIRED
    """

    verdict: str            # "PROPOSED_EDIT" | "JUDGMENT_REQUIRED" | "NO_CHANGE_NEEDED"
    confidence: float       # [0.0, 1.0]
    rationale: str          # always present
    proposed_edit: dict | None = None  # only when verdict == "PROPOSED_EDIT"
    question: str | None = None        # only when verdict == "JUDGMENT_REQUIRED"
```

### Invariants

- `verdict` ∈ `{"PROPOSED_EDIT", "JUDGMENT_REQUIRED", "NO_CHANGE_NEEDED"}` (case-sensitive)
- `confidence` ∈ [0.0, 1.0]
- `rationale` is always a non-empty string
- `proposed_edit` MUST be present iff `verdict == "PROPOSED_EDIT"`
- `question` MUST be present iff `verdict == "JUDGMENT_REQUIRED"`
- The `proposed_edit` dict (when present) MUST contain keys: `doc_path`, `current_value`, `proposed_value`. Plus optional `rationale_detail` for richer downstream context.

### Schema violations

Any invariant violation raises `DriftInterpretationError` and triggers the retry policy (D6). After all retries exhausted, the event is escalated as `RETRY_EXHAUSTED` per FR-008/FR-009.

---

## E2 — DriftInterpretationContext

**Purpose**: Input package assembled by `handle_drift_events.py` and passed to `drift_interpretation.interpret()`.

**Location**: `scripts/doc_audit/judgment/drift_interpretation.py`

```python
@dataclass(frozen=True)
class DriftInterpretationContext:
    """Input to Moment 0 LLM judgment.

    Assembled from a single drift-events.jsonl row + its matching
    Mapping (loaded from signal-to-doc-map.json) + the current
    contents of each target doc (truncated per D2 if needed).
    """

    event_id: str             # cursor-line:timestamp composite, e.g., "47:2026-05-22T03:00:07Z"
    timestamp_utc: str        # ISO 8601
    baseline: str             # e.g., "openclaw-cron"
    mapping_id: str           # e.g., "openclaw-cron-drift"
    mapping_rationale: str    # copied verbatim from signal-to-doc-map.json
    diff: str                 # unified diff text
    doc_targets: list[DocTarget]


@dataclass(frozen=True)
class DocTarget:
    """One target doc with its current state (truncated per D2)."""

    path: str                 # relative to repo root
    contents: str             # full file or truncated per D2 strategy
    truncated: bool           # True if D2 truncation applied
    truncation_strategy: str  # "full" | "head_region_tail" | "region_only"
```

### Invariants

- `doc_targets` is non-empty (an event without targets shouldn't reach Moment 0)
- `event_id` is unique per drift event (used for idempotency on ledger writes)
- `timestamp_utc` ends with `Z`

---

## E3 — AuditLedgerEntry

**Purpose**: One row appended to `/data/services/security-monitor/logs/drift-events-ledger.jsonl` per processed drift event.

**Location**: `scripts/doc_audit/output/drift_ledger.py`

```python
@dataclass(frozen=True)
class AuditLedgerEntry:
    """One JSONL row in the drift-events ledger.

    Append-only. Serialized as a single line of JSON with the field
    order below for deterministic diffing.
    """

    event_id: str
    timestamp_utc: str
    baseline: str
    mapping_id: str
    verdict: str                  # see E1.verdict + "RETRY_EXHAUSTED"
    confidence: float | None      # None when verdict == "RETRY_EXHAUSTED"
    outcome: str                  # see below
    doc_paths: list[str]
    retry_count: int              # 0..3
    latency_ms: int               # end-to-end including retries
    tier_classification_outcome: str | None  # "tier_a" | "tier_b" | "judgment" | None
    github_issue_number: int | None          # set when outcome includes issue/PR
    schema_version: int = 1
```

### `outcome` enum

- `auto_committed` — Tier A path completed, commit landed
- `pr_filed` — Tier B path completed, PR opened
- `issue_filed` — JUDGMENT_REQUIRED path completed, `[doc-audit]` issue filed
- `auto_closed` — NO_CHANGE_NEEDED path completed, no GitHub artifact
- `retry_exhausted` — all retries failed; pre-#362 fallback path used

### Append semantics

Each ledger write is atomic (tempfile + rename). Re-running the pipeline against an already-processed event_id is a no-op at the cursor layer (cursor advances only on success). If a duplicate event_id reaches the ledger writer (e.g., manual replay), it appends a second row — downstream consumers MUST handle this (latest-wins-by-timestamp).

---

## E4 — ProposedEdit (existing, EXTENDED)

**Purpose**: Existing dataclass at `scripts/doc_audit/data_model.py` (E-004). Used by `tier_classification.py` and `handle_audit_routing.py`. Extended in place to accept a new `change_type` value.

### Change

Add `drift_derived` to the documented set of `change_type` values. The dataclass shape itself is unchanged:

```python
@dataclass(frozen=True)
class ProposedEdit:
    doc_path: str
    change_type: str         # now includes "drift_derived" as the 8th value
    current_value: str
    proposed_value: str
    evidence_source: str
    tier: str                # "tier_a" | "tier_b" — set by translator before tier_classification
    confidence: str          # "high" — always high for ProposedEdit; judgment edits become DebtIssue
```

### Translator semantics

`scripts/doc_audit/routing/drift_to_proposed_edit.py` builds a `ProposedEdit` from a `DriftVerdict` (verdict=PROPOSED_EDIT, confidence ≥0.80):

| ProposedEdit field | Source |
|---|---|
| `doc_path` | `DriftVerdict.proposed_edit["doc_path"]` |
| `change_type` | `"drift_derived"` (constant) |
| `current_value` | `DriftVerdict.proposed_edit["current_value"]` |
| `proposed_value` | `DriftVerdict.proposed_edit["proposed_value"]` |
| `evidence_source` | f-string: `"drift-event:{baseline}:{event_id}"` |
| `tier` | `"tier_b"` (default; tier_classification reassigns if applicable) |
| `confidence` | `"high"` |

The initial `tier = "tier_b"` is a placeholder; tier_classification (Moment 1) reads the proposed edit and assigns the actual tier per SKILL.md §4.1.

### Tier classification behavior on `drift_derived`

The existing `tier_classification.prompt.md` does not enumerate `drift_derived` in its rules. The expected behavior:
- Examine `current_value` / `proposed_value` / `doc_path`
- If the edit fits an existing Tier A category (frontmatter date bump, etc.) → return `tier_a`
- If it fits Tier B (service version, file rename) → return `tier_b`
- Otherwise → return `judgment` (defense-in-depth: drift_derived edits the LLM can't confidently tier go to the operator for review)

This means `drift_derived` edits will largely flow through tier_b or judgment — both safe outcomes. Tier_a auto-commits are still gated by tier_classification's own conservative rules.

---

## E5 — DriftInterpretationError

**Purpose**: Exception raised on unrecoverable failures from the drift_interpretation judgment.

**Location**: `scripts/doc_audit/judgment/drift_interpretation.py`

```python
class DriftInterpretationError(Exception):
    """Raised on unrecoverable failures.

    Carries diagnostic context for inclusion in the escalation
    [doc-audit] issue body when all retries are exhausted (FR-009).
    """

    def __init__(self, message: str, *, cause: Exception | None = None, attempts: int = 0):
        super().__init__(message)
        self.cause = cause
        self.attempts = attempts

    def to_diagnostic_block(self) -> str:
        """Markdown block for inclusion in [doc-audit] issue body."""
        ...
```

### When raised

- Anthropic API error (5xx, network failure, timeout) after all 3 retries exhausted
- JSON parse failure after all 3 retries (LLM keeps producing malformed JSON)
- Schema validation failure after all 3 retries (LLM keeps violating the E1 invariants)
- Out-of-set `chosen_task_id` (analog from habits disambiguator) — but for drift, this maps to: `proposed_edit.doc_path` not in mapping's `doc_targets` list

### Handling

`handle_drift_events.py` catches `DriftInterpretationError` and:
1. Logs to driver activity log (existing pattern)
2. Writes ledger entry with `verdict=RETRY_EXHAUSTED`, `outcome=retry_exhausted`
3. Files a `[doc-audit]` issue via the pre-#362 path with the diagnostic block in the body

---

## E6 — CutoverState

**Purpose**: One-shot sentinel marker preventing re-run of the backlog cutover script.

**Location**: `~/.config/doc-audit/cutover-362.done` (filesystem; not a Python entity)

### File contents

```
mission: drift-event-auto-resolution-01KS8J32
mission_id: 01KS8J321F8KE7369R3DA02329
run_at_utc: <ISO 8601 timestamp of successful run>
closed_issues: [351, 352, 353, 354, 355, 356, 357, 358, 359, 360, 368, 369, 370]
cursor_reset_to: 0
```

### Lifecycle

- Absent on a fresh deploy
- Written by `cutover_362.py` on successful completion
- Read by `cutover_362.py` at start: if present, exit 0 (idempotent no-op)
- Operator can delete to force re-run; `cutover_362.py --force` skips marker check

---

## State transitions

```
drift-events.jsonl row
  ↓ (cursor advance + read)
DriftInterpretationContext (E2)
  ↓ (LLM call — Moment 0)
DriftVerdict (E1)
  ↓ branch on verdict:
  ├── PROPOSED_EDIT + conf ≥0.80
  │     ↓ (translator)
  │   ProposedEdit (E4, drift_derived)
  │     ↓ (tier_classification — Moment 1)
  │   Tier A → auto-commit
  │   Tier B → file PR
  │   Judgment → DebtIssue
  ├── PROPOSED_EDIT + conf <0.80 → demote → file [doc-audit] issue
  ├── JUDGMENT_REQUIRED → file [doc-audit] issue with LLM's question
  ├── NO_CHANGE_NEEDED + conf ≥0.80 → auto-close (ledger entry only)
  └── NO_CHANGE_NEEDED + conf <0.80 → demote → file [doc-audit] issue

ALL paths converge to:
  ↓ AuditLedgerEntry (E3) written
  ↓ Cursor advances
```

---

## Validation

The translator and Moment 0 caller MUST validate:
- E1 schema invariants before proceeding
- E2 has non-empty `doc_targets`
- E3 row serializes cleanly to a single JSONL line (no embedded newlines except as `\n` escapes)
- E4 (drift_derived) builds with all required fields populated
- E6 marker writes are atomic (tempfile + rename)
