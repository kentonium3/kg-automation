# Contract: `SignalSource` Protocol

**Mission**: refactor-doc-auditor-to-scripts-first-driver-01KS2XNX
**Realizes**: spec FR-001, FR-003, FR-004; research.md D4
**Implementations (initial)**: `GHIssueSignalSource`, `DriftEventSignalSource`

## Purpose

The driver consumes change signals from multiple producers (commit triggers, weekly cron, drift-event detection, future sources). `SignalSource` is the Protocol that uniforms them, so the driver's orchestration loop is signal-source-agnostic.

## Protocol

```python
from typing import Protocol, Iterable
from doc_audit.data_model import Signal

class SignalSource(Protocol):
    name: str  # e.g., "gh_issue", "drift_event"

    def pending(self) -> Iterable[Signal]:
        """
        Return all signals from this source that need processing this tick.

        - MUST be idempotent: repeated calls within a tick return the same set
          (caller may iterate twice).
        - MUST NOT mutate external state. Cursors and other forward-progress
          state are advanced ONLY when the driver explicitly calls `commit`.
        - MAY return an empty iterable if there is no pending work.
        - MUST raise on credential / connectivity errors (propagate, not swallow).
        """
        ...

    def commit(self, signal: Signal, outcome: str) -> None:
        """
        Mark a signal as processed.

        - For source-specific bookkeeping (e.g., advancing a cursor file).
        - `outcome` is one of "success", "partial", "failure".
        - For source kinds where the GitHub issue itself records the outcome
          (e.g., closed audits, applied decisions), this method MAY be a no-op.
        """
        ...
```

## Initial adapters

### `GHIssueSignalSource`

**Reads**: GitHub via `gh issue list`. Returns signals for:
- Open `Doc audit:` issues without `status:in-progress` (priority 20)
- Open `Weekly doc audit —` issues without `status:in-progress` (priority 30)
- Open `audit-pending-approval` issues with a decision label applied (priority 10)

**Commit**: no-op (the GitHub issue state IS the persistent record of outcome).

**Filtering**: skip issues with `status:in-progress` UNLESS they're recoverable per stale-lock detection rules (data-model E-002 state transitions).

### `DriftEventSignalSource`

**Reads**: `/data/services/security-monitor/logs/drift-events.jsonl`, starting at the cursor in `/data/services/security-monitor/.drift-events.cursor`.

**Returns**: one `Signal` per drift event with priority 40.

**Commit**: advance the cursor file atomically (write `cursor.tmp`, rename) after a signal has been processed (mapped → audit issue filed, or unmapped → appended to `unmapped-events.jsonl`).

**Wraps**: the existing `handle_drift_events.py` helper. Implementation may import `handle_drift_events` module's functions (per research.md D3 hybrid approach) or invoke as subprocess. Library-import path is preferred for testability.

## Driver orchestration contract

```python
def run_tick(sources: list[SignalSource], ...) -> TickResult:
    all_pending = []
    for source in sources:
        all_pending.extend(source.pending())

    # Sort by priority ascending; ties broken by created_utc.
    all_pending.sort(key=lambda s: (s.priority, s.created_utc))

    for signal in all_pending:
        try:
            outcome = process_signal(signal)  # dispatch by signal.kind
            source_of(signal).commit(signal, outcome)
        except Exception as e:
            record_error(e)
            # Do not commit on unhandled error; signal will be re-attempted next tick.
    ...
```

The driver does NOT interleave processing of one source with another within a tick except via priority ordering. Pending-approvals are always processed first (priority 10), then new audits, then drift events.

## Test expectations

- Unit tests for each adapter MUST mock the external surface (`gh` subprocess for `GHIssueSignalSource`, `drift-events.jsonl` fixture for `DriftEventSignalSource`).
- Tests MUST cover the empty case, the single-signal case, and the multi-signal mixed-source case.
- Tests MUST verify that `commit` is only called after `process_signal` returns successfully.

## Extension expectations

Adding a new signal source (e.g., `FileWatchSignalSource` for new files in `docs/`) requires:

1. Implementing the Protocol in `scripts/doc_audit/signals/<name>.py`.
2. Registering it in the driver's config (the driver's startup builds the `sources` list from config).
3. Picking an unused priority value.
4. Adding adapter-specific tests.

No change required to the driver's orchestration loop.

## Anti-patterns (forbidden)

- A signal source MUST NOT directly file GH issues or mutate the GH-issue surface. Issue filing belongs to the routing layer (post-judgment) or to upstream producers (e.g., `handle_drift_events.py`'s own issue-filing — which the `DriftEventSignalSource` exposes via the resulting GH issue being picked up by `GHIssueSignalSource` on a subsequent tick).
- A signal source MUST NOT swallow credential errors and pretend `pending()` is empty. Empty MUST mean "no work to do," not "couldn't talk to the API."
- A signal source MUST NOT have hidden inter-tick state. All persistence is via the cursor file or the GH issue state itself.
