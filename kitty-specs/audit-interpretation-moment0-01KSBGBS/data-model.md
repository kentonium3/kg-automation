# Data Model

## E1 — AuditVerdict (frozen dataclass)

```python
@dataclass(frozen=True)
class AuditVerdict:
    doc_path: str
    verdict: str            # "PROPOSED_EDIT" | "JUDGMENT_REQUIRED" | "NO_CHANGE_NEEDED"
    confidence: float       # [0.0, 1.0]
    rationale: str
    proposed_edit: dict | None = None
    question: str | None = None
```

## E2 — AuditInterpretationContext

```python
@dataclass(frozen=True)
class AuditInterpretationContext:
    audit_issue: int        # GH issue number
    commit_sha: str
    diff: str               # full diff text
    in_scope_docs: list[DocTarget]  # reuse drift_interpretation.DocTarget
```

## E3 — AuditLedgerEntry (JSONL row)

```python
@dataclass(frozen=True)
class AuditLedgerEntry:
    audit_issue: int
    doc_path: str
    timestamp_utc: str
    commit_sha: str
    verdict: str
    confidence: float | None
    outcome: str             # "auto_committed" | "pr_filed" | "issue_filed" | "auto_closed" | "judgment_required_posted" | "retry_exhausted"
    schema_version: int = 1
```

`outcome` differs from drift ledger: `judgment_required_posted` is unique to audit ledger (drift uses `issue_filed` for JUDGMENT_REQUIRED because drift creates a new issue; audit just adds a comment to the existing audit issue).
