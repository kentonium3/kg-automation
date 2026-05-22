# Research: Fix Moment 0 wiring — integrate at signals adapter

**Mission**: `moment0-integration-fix-01KS8XRM`
**Spec**: [spec.md](spec.md)
**Plan**: [plan.md](plan.md)
**Generated**: 2026-05-22

Phase 0 research. This mission inherits #362's research (D1-D10 in `kitty-specs/drift-event-auto-resolution-01KS8J32/research.md`). Five new decisions specific to the integration relocation.

---

## D1 — Shared helper module path

**Decision**: `scripts/doc_audit/routing/drift_moment0.py` — joins the existing routing package alongside `drift_to_proposed_edit.py` and `apply_decisions.py`.

**Rationale**:
- The `routing/` package was introduced in #362 to hold the verdict-to-action layer (WP03 added `drift_to_proposed_edit.py`)
- Conceptually, Moment 0 + verdict routing is "what to do with this drift event" — squarely in the routing layer's purview
- Existing pattern: routing/ contains pure-Python orchestration; signals/ contains adapters that call routing/

**Alternatives considered**:
- `scripts/doc_audit/orchestration/drift_moment0.py` (new package) — rejected: routing/ is the right home
- `scripts/doc_audit/helpers/drift_moment0.py` — rejected: helpers/ is for thin glue between modules, not orchestration

---

## D2 — JudgmentClient lifecycle in the signals adapter

**Decision**: Lazy construction on first need; held as `self._judgment_client: JudgmentClient | None = None`; one client per tick (per adapter instance lifetime).

```python
def _get_judgment_client(self) -> JudgmentClient:
    if self._judgment_client is None:
        api_key_path = self.config.drift_interpretation.api_key_path
        self._judgment_client = JudgmentClient(api_key_path=api_key_path)
    return self._judgment_client
```

**FR-010 compliance**: if `[drift_interpretation].enabled = false`, the cron-path branch short-circuits BEFORE `_get_judgment_client()` is called. No API key file read, no SDK construction.

**Rationale**:
- Eager construction in `__init__` would read the API key file even when disabled (FR-010 violation)
- One client per tick avoids repeated TLS handshakes for back-to-back events in a single drift sweep

**Alternatives considered**:
- Eager in `__init__`: rejected (FR-010)
- Per-event construction: rejected (wasteful)
- Module-level singleton: rejected (test isolation problems)

---

## D3 — Shared helper signature

**Decision**: Keyword-only parameters; returns `RoutingOutcome`; raises `DriftInterpretationError` on retry exhaustion:

```python
def route_drift_event(
    *,
    event: dict[str, Any],
    mapping: Mapping,
    config: Config,
    client: JudgmentClient,
    ledger_path: Path,
    repo: str,
    event_id: str,
    timestamp_utc: str,
    cursor_line: int,
    repo_root: Path,
) -> RoutingOutcome:
    ...
```

**Side effects** (in order):
1. Build `DriftInterpretationContext` (loads doc_targets per mapping)
2. Call `drift_interpretation.interpret(client, context, ...)` — may invoke retry policy internally
3. Route per verdict (PROPOSED_EDIT → translator → tier_classification → tier dispatch; JUDGMENT_REQUIRED → file_doc_audit_issue with question; NO_CHANGE_NEEDED → ledger only)
4. Append ledger row via `drift_ledger.append(...)`
5. Return RoutingOutcome

**Returns**: `RoutingOutcome(outcome, tier_classification_outcome, github_issue_number, retry_count, latency_ms)` — caller uses these for logging/diagnostics.

**Raises**: `DriftInterpretationError` propagates up from `interpret()` when retries exhaust. Caller (`signals/drift_event.py::commit()` or `handle_drift_events.py::process_events()`) catches it, writes a `RETRY_EXHAUSTED` ledger row, and falls through to `file_doc_audit_issue()`.

**Rationale**:
- Keyword-only enforces explicit call sites
- Returning vs raising matches existing #362 idioms
- All side effects encapsulated; caller doesn't need to know order

---

## D4 — Cleanup script for #378-390

**Decision**: `scripts/doc_audit/helpers/cleanup_391.py` — thin analog of `cutover_362.py`. Idempotent marker at `~/.config/doc-audit/cleanup-391.done`. Closes the exact list `[378,379,380,381,382,383,384,385,386,387,388,389,390]` with a comment referencing #391 + this mission's commit.

```python
ISSUE_NUMBERS = [378, 379, 380, 381, 382, 383, 384, 385, 386, 387, 388, 389, 390]
COMMENT_BODY = (
    "Closing as part of mission {mission_slug} (#391). "
    "This issue was filed by the broken #362 pipeline replay on "
    "2026-05-22T22:28 UTC. The fixed pipeline (Moment 0 wired at "
    "signals/drift_event.py) will process subsequent drift events "
    "via the LLM judgment path. See commit {commit_sha}."
)
```

**Rationale**: pattern reuse from cutover_362 minimizes risk + reviewer cognitive load. Static issue list (no `gh search` query) — these are exact known issues from a known incident; no fuzzy matching.

**Alternatives considered**:
- Inline `gh` commands in quickstart: rejected — 13 issues + repeating comments is error-prone for the operator
- Generic "close all P3-candidate drift-derived" search: rejected — could pick up real new drift events filed by the post-fix pipeline if there's any timing overlap

---

## D5 — Test strategy

**Decision**: split coverage across the 3 WPs:

| WP | Coverage focus | Coverage budget |
|---|---|---|
| WP01 (shared helper) | All 6 verdict paths from #362 + retry exhaustion + ledger append + RoutingOutcome shape. Mocked JudgmentClient, mocked tier_classification, mocked subprocess (gh) | ≥85% on `routing/drift_moment0.py` |
| WP02 (signals integration) | `commit()` Moment 0 path: config-enabled invokes route_drift_event; config-disabled bypasses; retry exhausted → fallback to file_doc_audit_issue; cursor/drain idempotency preserved | ≥85% on the new code paths in `signals/drift_event.py` (treat the existing untouched paths as baseline) |
| WP03 (cleanup script + docs) | cleanup_391 script: happy path, dry-run, idempotent no-op, partial failure tolerance | ≥85% on cleanup_391.py |

Existing `tests/doc_audit/helpers/test_handle_drift_events.py` updated (not rewritten) — assert that process_events calls `route_drift_event(...)` and produces equivalent outcomes; remove tests that mock the now-removed inline helpers.

**Rationale**: each WP has a tight test scope; no test-rewrite cascade across files outside the WP's owned set.

---

## Open questions / deferred items

None. The architecture is settled; implementation is mechanical relocation + new tests + cleanup script.
