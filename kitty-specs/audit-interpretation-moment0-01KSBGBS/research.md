# Research: Audit interpretation Moment 0

3 decisions:

## D1 — Separate audit-events-ledger.jsonl

**Decision**: new file `/data/services/openclaw/state/doc_audit/audit-events-ledger.jsonl`, separate from drift-events-ledger.

**Rationale**: audit verdicts carry `audit_issue_number` (an int referencing the originating GH issue); drift verdicts carry `event_id` (a cursor-position composite). Schema would diverge. Keeping separate avoids a schema-version-2 migration on drift ledger.

## D2 — Per-doc verdicts (not whole-audit)

**Decision**: `interpret_audit` returns a list of AuditVerdict, one per in-scope doc.

**Rationale**: real audits have partial dirt — typical case is 3 of 5 docs need no change, 1 needs a question, 1 needs an edit. Per-doc preserves that granularity. Aggregation (auto-close-when-all-clean) happens in the caller (handle_audit_routing).

## D3 — Single consolidated comment for JUDGMENT_REQUIRED

**Decision**: ONE comment per audit listing all JUDGMENT_REQUIRED docs + their questions.

**Rationale**: spam avoidance (an audit with 3 questions shouldn't produce 3 comments). Format:

```
**Driver: 3 of 5 docs need your judgment**

- `docs/runbooks/foo.md`: <question>
- `docs/runbooks/bar.md`: <question>
- `docs/design/architecture/baz.md`: <question>

Other docs evaluated as no change needed: `docs/runbooks/clean1.md`, `docs/runbooks/clean2.md`.
```

Auto-applied edits (Tier A) and filed PRs (Tier B) get separate notifications via the existing pipeline.
