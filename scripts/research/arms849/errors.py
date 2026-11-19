"""The exceptions every arm and the harness share, and the one context-limit check (WP02 T007).

contracts/arm-registration.md (C13) items 3, 5, 6, 8; contracts/before-send.md items 3, 4, 7;
research.md D-2, D-3, D-4, D-9. One module, so that terminality is decided by IDENTITY in one place
and the three arms can no longer diverge:

* :class:`ArmRefusal` — the ONE configuration-defect class. Terminal for the cell on the first
  attempt, never retried (arm-registration item 3). ``arm_d.ArmRefusal`` and ``arm_r.ArmRefusal``
  are aliases of it.
* :class:`PremiseViolated` — a broken premise of the whole run (G's no-LLM tripwire firing, or
  retrieval crossing the per-question graph boundary). NOT an ``ArmRefusal``: the Session stops the
  run and records ``premise_violated`` (item 5; ledger-deltas item 5).
* :class:`CeilingBreached` / :class:`CeilingUnreadable` — raised by the harness's ``before_send``
  callback (before-send items 3 and 7). Neither subclasses ``ContextExceeded`` nor ``ArmRefusal``,
  so no arm's handler catches them and they reach the Session unaltered (item 4).
* :class:`GCancellationUnacknowledged` — G's cancelled coroutine did not acknowledge termination
  within :data:`G_CANCEL_GRACE_S`. A ``BaseException`` and deliberately NOT an ``Exception``, so no
  ordinary ``except Exception`` can absorb it (item 8).
* :func:`check_limit` — the D/R context-limit check, moved here unchanged in substance, reading the
  configuration ONLY from ``ctx.config`` (item 6: the ``ctx.serving.config`` fallback is gone).

This module imports no graph stack: the harness imports it eagerly to classify outcomes, and
importing the harness must never import ``graphiti_core`` (arm-registration item 1).
"""

from __future__ import annotations

import math
from typing import Any

from scripts.research.arms849 import serving
from scripts.research.arms849.ledger import PREMISE_REASONS

__all__ = ["G_CANCEL_GRACE_S", "LIMIT_NAMES", "ArmRefusal", "CeilingBreached", "CeilingUnreadable",
           "GCancellationUnacknowledged", "PremiseViolated", "check_limit"]

#: How long a cancelled G coroutine has to acknowledge its own termination (research D-2;
#: arm-registration item 8). The session records it as ``session_stopped.grace_s``.
G_CANCEL_GRACE_S = 10.0
LIMIT_NAMES = ("trained", "permitted")


class ArmRefusal(RuntimeError):
    """A configuration defect: terminal for the cell on the first attempt, never retried — the retry
    ladder is for infrastructure failures (contracts/arm-interface.md @42056e57; C13 item 3).

    D: loader links handed to the flat arm, cache_prompt off, an empty view. R: the same, plus no
    usable calibration record or an index built for another view. G: a foreign item in its own graph,
    a graph not built. All three: an incoherent context limit (:func:`check_limit`)."""


class PremiseViolated(Exception):
    """A premise of the whole run is broken, so already-recorded cells are suspect (research D-3).

    ``reason`` is one of the ledger's ``PREMISE_REASONS`` (``tripwire`` | ``cross_group_leak``), the
    same vocabulary the ``premise_violated`` event validates. NOT an :class:`ArmRefusal`: a refusal
    ends one cell, this ends the run (C13 item 5)."""

    def __init__(self, reason: str, message: str) -> None:
        if reason not in PREMISE_REASONS:
            raise ValueError(f"premise violation reason must be one of {PREMISE_REASONS}, got {reason!r}")
        self.reason = reason
        super().__init__(f"premise violated ({reason}): {message}")


def _gib(name: str, value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise ValueError(f"{name} must be a finite non-negative number of GiB, got {value!r}")
    return float(value)


class CeilingBreached(Exception):
    """The live GTT reading at send is strictly above the ceiling (before-send item 3; NFR-004).

    Zero bytes are sent; the Session records ``exceeds_memory_ceiling`` with ``memory_ceiling =
    {measured_gib, ceiling_gib, stage}`` and stops (ledger-deltas item 1). ``measured_gib`` must be
    strictly greater than ``ceiling_gib`` — a reading at the ceiling is compliant, as the ledger
    rules — so a breach that the ledger would refuse can never be raised."""

    def __init__(self, measured_gib: float, ceiling_gib: float) -> None:
        self.measured_gib = _gib("measured_gib", measured_gib)
        self.ceiling_gib = _gib("ceiling_gib", ceiling_gib)
        if not self.measured_gib > self.ceiling_gib:
            raise ValueError(f"a breach needs measured_gib > ceiling_gib; {self.measured_gib} <= {self.ceiling_gib}")
        super().__init__(f"GTT {self.measured_gib} GiB is above the {self.ceiling_gib} GiB ceiling at send; "
                         f"nothing was sent")


class CeilingUnreadable(Exception):
    """The live GTT reading FAILED at send (before-send item 7): could-not-check, never a breach.
    Nothing is sent; the Session records ``sampler_unreadable_at_send`` and refuses the cell."""


class GCancellationUnacknowledged(BaseException):
    """G's cancelled coroutine did not acknowledge termination within ``grace_s`` (research D-2).

    Deliberately a ``BaseException`` and NOT an ``Exception``: no ordinary handler may absorb it.
    The Session records ``session_stopped{reason: "g_cancellation_unacknowledged", grace_s}``, issues
    no further graph query, and the process exits; resume happens in a fresh process."""

    def __init__(self, grace_s: float) -> None:
        if isinstance(grace_s, bool) or not isinstance(grace_s, (int, float)) or not math.isfinite(grace_s) \
                or grace_s <= 0:
            raise ValueError(f"grace_s must be a finite positive number of seconds, got {grace_s!r}")
        self.grace_s = float(grace_s)
        super().__init__(f"G's cancelled work did not acknowledge termination within {self.grace_s} s")


def check_limit(ctx: Any) -> serving.ServingConfiguration:
    """The active configuration, after checking ``ctx``'s applied limit pair against it.

    Reads ONLY ``ctx.config`` (C13 item 6). ``ctx.limit_applied`` and ``ctx.limit`` must BOTH be what
    ``config.limit_applied()`` says: a well-formed pair that is not the configuration's —
    ``("trained", 1)`` under the primary, the secondary's pair under the primary — would otherwise
    turn a configuration defect into a measured ``exceeds_model_context`` outcome and move the
    registered six-of-eight split (Codex c4). Every failure is :class:`ArmRefusal`, raised before
    anything is counted. Returns the configuration so a caller can read its limits."""
    config = getattr(ctx, "config", None)
    if not isinstance(config, serving.ServingConfiguration):
        raise ArmRefusal(f"ctx.config is not a ServingConfiguration ({type(config).__name__}); the context limit "
                         f"cannot be checked against the configuration (D-11), and ctx.config is the only place "
                         f"an arm reads it (C13 item 6)")
    if ctx.limit_applied not in LIMIT_NAMES or type(ctx.limit) is not int or ctx.limit <= 0:
        raise ArmRefusal(f"incoherent context limit in ctx: {ctx.limit_applied!r} = {ctx.limit!r} "
                         f"(D-11: one of {LIMIT_NAMES}, a positive int, from ServingConfiguration.limit_applied())")
    name, limit = config.limit_applied()
    if (ctx.limit_applied, ctx.limit) != (name, limit):
        raise ArmRefusal(f"ctx applies the {ctx.limit_applied} limit {ctx.limit}, but the {config.kind} configuration "
                         f"applies the {name} limit {limit} (ServingConfiguration.limit_applied(), D-11) — "
                         f"a configuration defect, not an experimental outcome")
    return config
