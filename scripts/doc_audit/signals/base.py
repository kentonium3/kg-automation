"""``SignalSource`` Protocol — the abstract surface adapters implement.

Mirrors ``kitty-specs/refactor-doc-auditor-to-scripts-first-driver-01KS2XNX/
contracts/signal-source.contract.md``. Read that file for the
authoritative semantics and anti-patterns. This module defines the
typing surface only — concrete adapters live in sibling modules
(``gh_issue.py``, ``drift_event.py``).

Two public names:

- :class:`SignalSource` — the ``typing.Protocol`` adapters satisfy
  structurally. The driver's orchestration loop type-hints against
  this surface and never imports concrete adapter classes.
- :data:`Outcome` — the ``Literal`` of legal ``outcome`` values
  passed to ``commit()``. Aligned with :class:`TickResult.status`
  (E-008) so the same vocabulary flows through the system.
"""

from __future__ import annotations

from typing import Iterable, Literal, Protocol

from doc_audit.data_model import Signal


# ---------------------------------------------------------------------------
# Outcome literal
# ---------------------------------------------------------------------------


Outcome = Literal["success", "partial", "failure"]
"""Legal values for the ``outcome`` argument to :meth:`SignalSource.commit`.

Matches the ``status`` field on ``TickResult`` (data-model E-008) so
the driver propagates the same vocabulary all the way through to the
``last-tick.json`` ``TickSignal`` artifact.
"""


# ---------------------------------------------------------------------------
# SignalSource Protocol
# ---------------------------------------------------------------------------


class SignalSource(Protocol):
    """Adapter surface for producing :class:`Signal` instances.

    Concrete implementations live in sibling modules and satisfy this
    Protocol structurally (no inheritance required).

    Attributes:
        name: Stable adapter identifier (e.g., ``"gh_issue"``,
            ``"drift_event"``). Used in error reporting and in the
            ``Signal.source`` field.
    """

    name: str

    def pending(self) -> Iterable[Signal]:
        """Return all signals from this source that need processing this tick.

        Contract:
        - MUST be idempotent: repeated calls within a tick return the
          same set (caller may iterate twice).
        - MUST NOT mutate external state. Cursors and other
          forward-progress state advance ONLY when the driver
          explicitly calls :meth:`commit`.
        - MAY return an empty iterable if there is no pending work.
        - MUST raise on credential / connectivity errors (propagate,
          do not swallow). An empty return value MUST mean "no work
          to do," not "could not reach the source."
        """
        ...

    def commit(self, signal: Signal, outcome: Outcome) -> None:
        """Mark ``signal`` as processed with the given ``outcome``.

        Contract:
        - For source-specific bookkeeping (e.g., advancing a cursor
          file).
        - ``outcome`` is one of ``"success"``, ``"partial"``,
          ``"failure"``.
        - For source kinds where the GitHub issue itself records the
          outcome (e.g., closed audits, applied decisions), this
          method MAY be a no-op.
        """
        ...


__all__ = ["Outcome", "SignalSource"]
