"""Routing layer for the felix-doc-auditor scripts-first driver.

Wraps the import surface of
``scripts/doc_audit/helpers/handle_audit_routing.py`` (lifted in
mission #343 WP01) so the driver can dispatch a fully-judged audit
into the existing apply / commit / gate / summary-post pipeline
without re-implementing those legs.

The single public entry point is :func:`apply` (re-exported via
:mod:`doc_audit.routing.apply_decisions`), which constructs the
audit-state JSON shape ``route_audit_decision`` expects, writes it
to a tempfile, and invokes the library entry point. The
:class:`RoutingResult` dataclass from the helper is re-exported for
the driver's convenience so it can be imported as
``from doc_audit.routing.apply_decisions import RoutingResult``.
"""

from doc_audit.routing.apply_decisions import RoutingResult, apply

__all__ = ["RoutingResult", "apply"]
