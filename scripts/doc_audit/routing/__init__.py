"""Routing layer for the felix-doc-auditor scripts-first driver.

Wraps the import surface of
``scripts/doc_audit/helpers/handle_audit_routing.py`` (lifted in
mission #343 WP01) so the driver can dispatch a fully-judged audit
into the existing apply / commit / gate / summary-post pipeline
without re-implementing those legs.

Public entry points
-------------------
- :func:`apply` (re-exported via :mod:`doc_audit.routing.apply_decisions`):
  constructs the audit-state JSON shape ``route_audit_decision`` expects,
  writes it to a tempfile, and invokes the library entry point. The
  :class:`RoutingResult` dataclass from the helper is re-exported for
  the driver's convenience.
- :func:`build` (re-exported via
  :mod:`doc_audit.routing.drift_to_proposed_edit`, added in mission
  drift-event-auto-resolution-01KS8J32): translates a Moment 0
  ``DriftVerdict (PROPOSED_EDIT, conf ≥0.80)`` into a ``ProposedEdit``
  that ``tier_classification`` (Moment 1) consumes unchanged (C-003).
"""

from doc_audit.routing.apply_decisions import RoutingResult, apply
from doc_audit.routing.drift_to_proposed_edit import build

__all__ = ["RoutingResult", "apply", "build"]
