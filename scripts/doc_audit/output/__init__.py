"""Output layer for the felix-doc-auditor scripts-first driver.

Two side-effect surfaces the driver invokes at end-of-tick:

- :mod:`tick_signal` writes ``last-tick.json`` per
  ``kitty-specs/refactor-doc-auditor-to-scripts-first-driver-01KS2XNX/
  contracts/tick-signal.contract.md``. Atomic
  tempfile-then-``os.rename`` semantics; always written (even on
  driver crash, via the driver's ``try/finally``).
- :mod:`activity_log` appends one entry per audit to
  ``/home/kgale/second-brain/agents/logs/doc-auditor-YYYY-MM-DD.md``
  (preserved location per spec C-005). Format is byte-for-byte
  compatible with entries the previous openclaw-agent path produced
  — Kent reads these manually, so format drift is operator-visible.

The module-level functions are the only public surfaces; internal
formatters and dict builders are leading-underscore helpers.
"""

from doc_audit.output.activity_log import append_audit_entry
from doc_audit.output.tick_signal import print_summary_line, write_tick_signal

__all__ = ["append_audit_entry", "print_summary_line", "write_tick_signal"]
