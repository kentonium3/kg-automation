"""Per-actor git-advance health watermark (#667, WP03).

Makes a silent multi-week deploy stall impossible. Each actor
(``agent-prompt-sync`` / ``felix-deployer``) records the outcome of every
:func:`scripts.deploy.lib.gitsync.advance_checkout` into a tiny per-actor JSON
watermark. When ``consecutive_failures`` crosses a threshold on *confirmed*
failures, exactly one ntfy alert fires per streak; a success resets the streak
so a later stall re-alerts.

Key correctness rules (research D3, data-model "Health watermark"):

* Only ``diverged | fetch_failed | merge_failed`` count toward the streak.
* ``lock_unavailable`` is a **benign defer** — the other actor simply held the
  shared lock — and MUST NOT increment the streak or alert. Otherwise a long
  felix tick would trip false alerts while the checkout is perfectly current.
* The alert throttle is anchored on ``failure_streak_started_ts`` so exactly one
  alert fires per streak; ``last_alert_ts`` is cleared on success so the next
  streak can alert again.
* ``last_alert_ts`` is stamped (and the crossing reported as ``alerted=True``)
  **only when the notifier actually DELIVERED the alert** — the notifier returns
  a ``bool`` (True iff delivered). A misconfigured/undeliverable notifier (e.g.
  no ntfy topic → dispatch returns False) or a notifier that raises does NOT burn
  the stamp: the crossing is re-attempted on the next failing tick so the alert
  is never silently lost. The notifier is called best-effort inside a
  ``try/except`` so it can never crash the tick.

The state file is written atomically (temp file in the same directory +
``os.replace``) so a crash mid-write never leaves a torn watermark. A clock is
injectable for deterministic tests — there is no untestable bare
``datetime.now()`` in the record path.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

from scripts.deploy.lib.gitsync import AdvanceResult

# Reasons that count as CONFIRMED failures for the streak. Everything else
# (notably ``lock_unavailable``) is a benign defer and leaves the streak alone.
CONFIRMED_FAILURE_REASONS = frozenset({"diverged", "fetch_failed", "merge_failed"})

DEFAULT_THRESHOLD = 3

# Injected-clock seam: returns an ISO-8601 UTC "Z" timestamp string.
Clock = Callable[[], str]

# Notifier seam: called with (title, body) at most once per streak crossing.
# Returns True iff the alert was ACTUALLY DELIVERED (e.g. ntfy POST succeeded).
# A False return (or a raised exception) means "not delivered" — the crossing
# is NOT stamped so it re-attempts on the next failing tick.
Notifier = Callable[[str, str], bool]


def utc_now_iso() -> str:
    """Default clock: current time as ISO-8601 UTC with a trailing ``Z``."""
    return _dt.datetime.now(tz=_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class HealthWatermark:
    """Per-actor advance-health state (data-model "Health watermark").

    ``consecutive_failures`` counts only CONFIRMED failures. A fresh (missing)
    watermark is the zero-state below.
    """

    actor: str
    consecutive_failures: int = 0
    failure_streak_started_ts: str | None = None
    last_success_head: str = ""
    last_success_ts: str | None = None
    last_alert_ts: str | None = None
    updated_ts: str | None = None

    @classmethod
    def fresh(cls, actor: str) -> "HealthWatermark":
        """Zero-state watermark for *actor* (used when the file is missing)."""
        return cls(actor=actor)

    @classmethod
    def from_dict(cls, actor: str, data: dict) -> "HealthWatermark":
        """Load a watermark, tolerating a missing/partial file → zero-state.

        Unknown keys are ignored; missing keys fall back to the zero-state.
        The ``actor`` argument always wins over any stale ``actor`` in the file.
        """
        return cls(
            actor=actor,
            consecutive_failures=int(data.get("consecutive_failures", 0) or 0),
            failure_streak_started_ts=data.get("failure_streak_started_ts"),
            last_success_head=data.get("last_success_head", "") or "",
            last_success_ts=data.get("last_success_ts"),
            last_alert_ts=data.get("last_alert_ts"),
            updated_ts=data.get("updated_ts"),
        )

    def to_dict(self) -> dict:
        return asdict(self)


def read_watermark(actor: str, state_path: Path) -> HealthWatermark:
    """Read *actor*'s watermark from *state_path*; missing/corrupt → zero-state."""
    try:
        raw = state_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return HealthWatermark.fresh(actor)
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        # A corrupt watermark is treated as a fresh zero-state rather than
        # crashing a tick — the health signal is escalation, not a source of truth.
        return HealthWatermark.fresh(actor)
    if not isinstance(data, dict):
        return HealthWatermark.fresh(actor)
    return HealthWatermark.from_dict(actor, data)


def write_watermark(state: HealthWatermark, state_path: Path) -> None:
    """Atomically write *state* to *state_path* (temp file + ``os.replace``)."""
    state_path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(state.to_dict(), indent=2, sort_keys=True) + "\n"
    fd, tmp_name = tempfile.mkstemp(
        dir=str(state_path.parent),
        prefix=f".{state_path.name}.",
        suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, state_path)
    except BaseException:
        # Never leave a stray temp file behind on failure.
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def record(
    actor: str,
    result: AdvanceResult,
    *,
    state_path: Path,
    threshold: int = DEFAULT_THRESHOLD,
    notifier: Notifier | None = None,
    clock: Clock = utc_now_iso,
) -> bool:
    """Update *actor*'s watermark from *result*; return True iff an alert fired.

    Semantics (contract ``lib-api.md`` + data-model alert rule):

    * ``result.ok`` (success or clean no-op) → reset ``consecutive_failures=0``,
      clear ``failure_streak_started_ts`` and ``last_alert_ts``, update
      ``last_success_head``/``last_success_ts``.
    * ``result.reason == "lock_unavailable"`` → NO-OP for the streak (benign
      defer): do not increment, do not alert. State is still persisted with a
      fresh ``updated_ts``.
    * ``result.reason in {diverged, fetch_failed, merge_failed}`` → increment
      ``consecutive_failures``; set ``failure_streak_started_ts`` if this begins
      a new streak.
    * Alert (via *notifier*) at most once per streak when
      ``consecutive_failures >= threshold`` AND (``last_alert_ts`` is None OR
      ``last_alert_ts < failure_streak_started_ts``). The notifier returns a
      ``bool`` reporting DELIVERY. ``last_alert_ts`` is stamped and the return
      value is ``alerted=True`` **only when delivery succeeded** — an
      undeliverable notifier (returns False), a raising notifier, or
      ``notifier is None`` all leave the crossing UNSTAMPED so it re-attempts on
      the next failing tick. The alert is never silently burned.

    *clock* is injectable (default :func:`utc_now_iso`) so tests control every
    timestamp. *notifier* is injectable (called with ``(title, body)`` and
    returning a delivery ``bool``); it is invoked best-effort inside a
    ``try/except`` so a misconfigured/raising notifier can never crash the tick.
    Returns True iff an alert was actually delivered this call.
    """
    state = read_watermark(actor, state_path)
    now = clock()
    alerted = False

    if result.ok:
        # Success or clean no-op: reset the streak entirely.
        state.consecutive_failures = 0
        state.failure_streak_started_ts = None
        state.last_alert_ts = None
        if result.post_head:
            state.last_success_head = result.post_head
        state.last_success_ts = now
    elif result.reason == "lock_unavailable":
        # Benign defer — leave the streak untouched. Just re-stamp updated_ts.
        pass
    elif result.reason in CONFIRMED_FAILURE_REASONS:
        if state.consecutive_failures == 0 or state.failure_streak_started_ts is None:
            # Starting a new streak: anchor the throttle timestamp.
            state.failure_streak_started_ts = now
        state.consecutive_failures += 1

        crossed = state.consecutive_failures >= threshold
        not_yet_alerted = (
            state.last_alert_ts is None
            or state.last_alert_ts < state.failure_streak_started_ts
        )
        if crossed and not_yet_alerted:
            # Best-effort delivery: only stamp last_alert_ts (and report
            # alerted=True) when the notifier ACTUALLY delivered the alert. A
            # None notifier, a False return (e.g. no ntfy topic configured), or
            # a raising notifier all count as "not delivered" — leave the
            # crossing unstamped so the next failing tick re-attempts. This is
            # what makes the anti-silent-stall guarantee real: a burned stamp on
            # an undelivered alert would suppress every future alert for the
            # streak.
            delivered = False
            if notifier is not None:
                title, body = _render_alert(state, result, threshold)
                try:
                    delivered = bool(notifier(title, body))
                except Exception as exc:  # noqa: BLE001 - never crash the tick
                    # A misconfigured/raising notifier must not crash the tick
                    # and must be treated as "not delivered".
                    delivered = False
                    print(
                        f"health_notifier_error: {type(exc).__name__}: "
                        f"{str(exc)[:200]}"
                    )
            if delivered:
                state.last_alert_ts = now
                alerted = True
    # Any other (unexpected) non-ok reason: treat conservatively as a no-op on
    # the streak. This should not happen given the AdvanceResult contract, but
    # we never want an unknown reason to spam or crash a tick.

    state.updated_ts = now
    write_watermark(state, state_path)
    return alerted


def _render_alert(
    state: HealthWatermark, result: AdvanceResult, threshold: int
) -> tuple[str, str]:
    """Build (title, body) for a behind-N health alert."""
    title = f"{state.actor}: git advance stalled ({state.consecutive_failures}x)"
    body = (
        f"Actor: {state.actor}\n"
        f"Consecutive failed advances: {state.consecutive_failures} "
        f"(threshold {threshold})\n"
        f"Latest reason: {result.reason}\n"
        f"Streak started: {state.failure_streak_started_ts}\n"
        f"Local head: {result.pre_head or '(unknown)'}\n"
        f"Origin head: {result.origin_head or '(unknown)'}\n"
        f"behind={result.behind} ahead={result.ahead}"
    )
    return title, body


__all__ = [
    "CONFIRMED_FAILURE_REASONS",
    "DEFAULT_THRESHOLD",
    "HealthWatermark",
    "read_watermark",
    "write_watermark",
    "record",
    "utc_now_iso",
]
