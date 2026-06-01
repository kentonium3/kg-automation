"""Signal-extraction package for the observation pipeline.

Concrete signal extractors live in sibling modules
(``creds_restore.py``, ``watchdog_reconnect.py``,
``unhandled_error.py``); shared primitives live in
``openclaw_log.py``, ``config_loader.py``, and ``types.py``.

Mission: ``signal-driven-monitoring-haiku-gate-01KT22PC`` (#490). See
``kitty-specs/signal-driven-monitoring-haiku-gate-01KT22PC/spec.md``
§3 (FR-001, FR-005, FR-006) for the design contract.
"""
