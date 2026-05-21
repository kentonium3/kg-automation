"""Signal-source adapters for the felix-doc-auditor driver.

This package exposes the :class:`SignalSource` Protocol plus the
concrete adapters that the driver uses to discover work each tick.

The canonical contract lives in
``kitty-specs/refactor-doc-auditor-to-scripts-first-driver-01KS2XNX/
contracts/signal-source.contract.md``. Each adapter normalizes its
source's native data into ``Signal`` instances (data-model E-001) so
the driver's orchestration loop is signal-source-agnostic.

Adapters MUST be idempotent within a tick: calling ``.pending()``
twice in a row returns the same set. ``commit()`` semantics differ
between adapters; see the individual modules for details.
"""

from doc_audit.signals.base import Outcome, SignalSource
from doc_audit.signals.drift_event import DriftEventSignalSource
from doc_audit.signals.gh_issue import GHIssueSignalSource

__all__ = [
    "Outcome",
    "SignalSource",
    "GHIssueSignalSource",
    "DriftEventSignalSource",
]
