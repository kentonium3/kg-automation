"""Heartbeat gate package (WP-03 of mission #490).

The Haiku-fronted heartbeat gate that fronts Felix's expensive-tier
heartbeat per FR-007..FR-011 of
``kitty-specs/signal-driven-monitoring-haiku-gate-01KT22PC/spec.md``.

Modules
-------
- ``context``  -- assemble per-tick inputs (last-tick.json + HEARTBEAT.md).
- ``gate``     -- Anthropic SDK wrapper that runs the routing prompt.
- ``escalator``-- shells out to ``openclaw system event --mode now``.
- ``ledger``   -- atomic ``last-gate-decision.json`` + JSONL ledger writer.
- ``run``      -- systemd entrypoint composing all modules + fallback.

The ``gate`` module is the only LLM-touching code. The other modules
have no network dependencies and are pure deterministic logic, so
fallback behavior (FR-011) is enforced regardless of API availability.

See ``contracts/gate-decision.contract.md`` for the JSON wire shape and
``data-model.md`` E4 for entity definitions.
"""
