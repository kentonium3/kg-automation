"""Canary probe evaluators — method → probe dispatch (WP03).

Pure with respect to injected effects. Every probe receives its effect
callables (``http_get`` / ``run_cmd`` / ``read_state``) as keyword arguments so
the whole module is deterministic and offline-testable — no network, no
subprocess, no real filesystem, and **no LLM anywhere** (INV-E).

Dispatch (contracts §2, research R3). The real ``service-inventory.json``
declares a heterogeneous ``health_check.method`` vocabulary that is NOT
normalized in the data; this module owns that heterogeneity via a
method → handler map:

* liveness — ``http`` / ``shell`` / ``systemd-status`` /
  ``self-check-command`` / ``self-test``
* freshness pointer — ``tick-signal-file`` / ``signal-file`` / ``state-file``
* log-scan — ``log-tail`` / ``journal``

Anything else (``none``, missing, or an unhandled string) was already
classified as a coverage gap by WP02's loader, so :func:`run_probe` should
never see it — but it defends anyway and returns ``evaluable=False`` rather
than guessing (INV-002, no silent fallback).

Fail-safe (INV-D): every handler is wrapped so that a raised exception becomes
``ProbeResult(ok=False, stale=False, evaluable=False, evidence="<Error>: ...")``.
A probe never raises out of :func:`run_probe`.

Freshness timestamp resolution — the design callout (T012)
----------------------------------------------------------
The freshness pointer is a JSON document whose authoritative timestamp field
name **differs per component**, and there is no inventory schema field naming
it (``max_age_seconds`` is the only permitted schema addition). Rather than
special-casing component names, the freshness probe resolves the timestamp by
trying an ordered list of candidate top-level keys, :data:`TIMESTAMP_KEYS`, and
taking the first present ISO-8601 value. It also honors an explicit error signal
when present — :func:`_explicit_error` recognizes the real success/failure field
conventions across the inventory's freshness pointers (``restic_exit_code``
outside ``{0, 3}``; a non-zero ``exit_code``; a non-success ``exit_status``; a
``status`` holding an explicit failure value; a truthy ``errors`` / ``error``
field → ``failed``), all as generic field-convention detection, never keyed on a
component name.

If the pointer is a shape the probe cannot interpret — a bare map with no
candidate timestamp key (a fingerprint map) or a JSONL audit log surfaced as a
non-dict — the probe returns ``evaluable=False`` → the caller maps it to
``unknown`` with evidence naming why. This is deliberately honest: a persistent
``unknown`` WARN is correct behavior, better than a false ``healthy``.

The probe stays generic on purpose: rather than teach it to parse every
component's private state shape, the fix for a shape-unevaluable component is
**service-side** — the component emits a small flat ``last-tick.json`` pointer
with a :data:`TIMESTAMP_KEYS` timestamp and its ``health_check.endpoint`` is
repointed at it. ``felix-trust-scan`` (whose ``seen-findings.json`` is a bare
fingerprint map) and ``agent-prompt-sync`` (whose audit log is JSONL) were both
migrated this way in #721; ``felix-deployer`` / ``felix-habit-sweeper`` in #720.
A component that still reads ``unknown`` is one that has not yet grown such a
pointer — expected (INV-002), not a bug.

``restic`` note: restic's ``last-backup.json`` uses ``snapshot_timestamp_utc``
(in :data:`TIMESTAMP_KEYS`) and a ``restic_exit_code`` in ``{0, 3}`` as the
"good" signal; WP05 converted restic to a ``state-file`` freshness check that
relies on exactly this probe.
"""
from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from scripts.canary.ledger import FreshnessObligation
from scripts.canary.ledger import evaluate as _ledger_evaluate

# --------------------------------------------------------------------------- #
# Freshness timestamp candidate keys (the T012 design callout).
#
# Ordered: the first present, parseable ISO-8601 value wins. Do NOT special-case
# component names — resolution is key-list + explicit-error only. Extend this
# list (not the call sites) when a new pointer shape appears.
# --------------------------------------------------------------------------- #
TIMESTAMP_KEYS: tuple[str, ...] = (
    # Completion-type anchors first (when the tick FINISHED), then start-type
    # fallbacks. Ordered because the first present key wins. Field names audited
    # against the real office2 freshness pointers (2026-07-11).
    "completed_at_utc",        # canary runner's own last-tick.json (WP04)
    "snapshot_timestamp_utc",  # restic last-backup.json (WP05 state-file)
    "script_finished_at_utc",  # restic script-finished witness
    "ran_at_utc",              # felix-health-check last-run pointer
    "timestamp_utc",           # felix-doc-auditor tick pointer
    "timestamp",
    "last_tick_utc",
    # start-type fallback: felix-core-digest / felix-heartbeat-gate record only a
    # tick-start time; it is ms-scale earlier than completion — negligible vs the
    # minutes-to-hours max_age_seconds bounds, so it is a sound freshness anchor.
    "started_at_utc",
    "at",
    "ts",
)

# restic exit codes that are NOT a backup failure: 0 = success, 3 = "some
# source files could not be read" (partial but the snapshot completed).
_RESTIC_OK_EXIT_CODES: frozenset[int] = frozenset({0, 3})

#: Prune success is ``{0}`` ONLY -- deliberately narrower than
#: :data:`_RESTIC_OK_EXIT_CODES`. Backup accepts 3 because a restic *backup*
#: exiting 3 completed with warnings but still produced a snapshot. ``forget``
#: exiting 3 carries no such guarantee, and ``restic-backup.sh`` already agrees:
#: it treats only ``PRUNE_RC == 0`` as success. Reusing the backup's set here
#: would accept a prune that never applied retention -- the exact #902 failure.
#: Do not "tidy up" this duplication.
_PRUNE_OK_EXIT_CODES: frozenset[int] = frozenset({0})

# --------------------------------------------------------------------------- #
# Explicit-failure field conventions (the freshness-pointer analogue of the
# TIMESTAMP_KEYS candidate list). Audited against the real freshness pointers in
# service-inventory.json — do NOT special-case component names, recognize field
# conventions only.
#
# Two vocabularies are handled differently on purpose:
#
# * ``exit_status`` — a CLOSED enum across the inventory's tick-signals
#   (``{"success", "partial", "failure"}`` per the tick-signal / sweeper-tick
#   contracts; canary's own is ``success``). Health is defined as
#   ``exit_status == "success"``, so anything present-and-not-in the success set
#   (``partial`` / ``failure``) is an explicit failure.
#
# * ``status`` — an OPEN vocabulary. Some pointers use ``success``/``error``
#   (canary, agent-prompt-sync tick-signals) but ``felix-health-check`` uses
#   ``{ALL_HEALTHY, FAILURES_DETECTED, UNKNOWN, SCRIPT_MISSING}`` where
#   ``FAILURES_DETECTED`` means the *monitored system* had failures while the
#   runner itself ran fine ("a health failure is data, not a runner error").
#   Using "not success" here would false-fail ``ALL_HEALTHY``. So by default
#   ``status`` is matched against an explicit failure-VALUE set only — a
#   fail-OPEN deny-list. A health_check may instead declare
#   ``success_status_values``, which inverts this to a fail-closed allow-list
#   (#891); prefer that for new pointers.
_EXIT_STATUS_SUCCESS: frozenset[str] = frozenset({"success", "ok"})
_STATUS_FAILURE_VALUES: frozenset[str] = frozenset(
    {"error", "failed", "fail", "failure"}
)

# Method groups (kept aligned with WP02's HANDLED_METHODS / contracts §2).
_LIVENESS_CMD_METHODS: frozenset[str] = frozenset(
    {"shell", "self-check-command", "self-test"}
)
_FRESHNESS_METHODS: frozenset[str] = frozenset(
    {"tick-signal-file", "signal-file", "state-file"}
)
_LOG_SCAN_METHODS: frozenset[str] = frozenset({"log-tail", "journal"})

# OpenClaw cron-state probe (#722). Reads `openclaw cron list --json` (the
# ``endpoint`` command) and evaluates the service's mapped crons (``crons``) for
# presence+enabled, last-run status, and schedule-aware freshness. Named
# distinctly from the ``openclaw-cron`` service *type* to keep the type and
# method vocabularies separate.
_OPENCLAW_CRON_METHOD = "openclaw-cron-state"

# Default grace past ``nextRunAtMs`` before a cron is judged overdue/stale. Must
# absorb the canary tick granularity (~15 min), a run's own duration (agent
# timeouts run to ~240–600s), and clock skew — so a cron that is merely mid-run
# at its scheduled instant is not falsely flagged. Overridable per health_check
# via ``grace_seconds``.
_DEFAULT_CRON_GRACE_SECONDS: float = 900.0

# Future-dating bound for a resolved freshness timestamp (T022,
# pointer-key-ledger-01M189P6/WP04). Deliberately the SAME value as
# ``_FUTURE_SKEW_TOLERANCE`` in ``scripts/deploy/lib/snapshot.py`` -- that
# module guards this exact same field (``snapshot_timestamp_utc``) on this
# exact same document (the restic ``last-backup.json`` pointer) for the
# Tier-2 deploy pre-flight gate, and two consumers of one file must not
# silently disagree about when it is trustworthy. Reference it by name
# (``_FUTURE_SKEW_TOLERANCE``) if this value ever needs to change so the
# sibling gets updated in the same change.
#
# Independently sound regardless of the sibling: the tightest
# ``max_age_seconds`` across the inventory today is 600s (agent-prompt-sync,
# felix-deployer, felix-vikunja-sync-driver), so this tolerance must stay
# well below that or the guard is defeated for those components -- 5 minutes
# (300s) clears that with room to spare. Without this bound, ``age = now -
# ts`` for a future-dated timestamp is negative, never exceeds any budget,
# and a skewed clock pins the component fresh forever.
_FUTURE_SKEW_TOLERANCE: timedelta = timedelta(minutes=5)


@dataclass(frozen=True)
class ProbeResult:
    """Raw output of a single probe evaluator.

    * ``ok`` — the probe's raw pass/fail signal.
    * ``stale`` — freshness/recency bound exceeded (freshness + log-scan only).
    * ``evaluable`` — ``False`` ⇒ the probe could not run conclusively; the
      caller maps this to ``unknown``.
    * ``evidence`` — human-readable detail (status code, exit code, age, missing
      marker, or error text).
    * ``signal`` — optional **run-identity fingerprint** for a bad result whose
      cause is a *frozen past event* rather than a continuously-observed live
      condition (#871). When set, the dedup layer re-alerts only when this value
      *changes* (a new event), not on the fixed 6h re-remind window — so a cron
      that errored on a past run and cannot change until it next runs is paged
      once, not every 6h. ``None`` (the default) means "no run identity" →
      dedup's normal window-based re-remind applies (live conditions:
      missing/disabled/overdue crons, service-down, freshness).
    """

    ok: bool
    stale: bool
    evaluable: bool
    evidence: str
    signal: str | None = None


# Injected-effect callable signatures (documentation only; not enforced).
HttpGet = Callable[..., int]
RunCmd = Callable[..., tuple[int, str, str]]
ReadState = Callable[[str], dict[str, Any]]


def _unevaluable(evidence: str) -> ProbeResult:
    """A conclusive-failure-to-evaluate result → maps to ``unknown``."""
    return ProbeResult(ok=False, stale=False, evaluable=False, evidence=evidence)


def _parse_iso(value: Any) -> datetime | None:
    """Parse an ISO-8601 string into an aware UTC-comparable datetime.

    Returns ``None`` for non-strings or unparseable values. A trailing ``Z`` is
    normalized to ``+00:00`` (``datetime.fromisoformat`` rejects ``Z`` before
    3.11 and the inventory pointers use ``Z``).
    """
    if not isinstance(value, str):
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _resolve_timestamp(pointer: dict[str, Any]) -> tuple[str, datetime] | None:
    """Return ``(key, datetime)`` for the first parseable candidate key, else None."""
    for key in TIMESTAMP_KEYS:
        if key in pointer:
            parsed = _parse_iso(pointer[key])
            if parsed is not None:
                return key, parsed
    return None


def _explicit_error(
    pointer: dict[str, Any],
    success_status_values: frozenset[str] | None = None,
) -> str | None:
    """Return an evidence string if the pointer explicitly signals failure.

    Recognizes the real success/failure field conventions used across the
    inventory's freshness pointers (tick-signal / signal-file / state-file). The
    detection is generic field-convention matching only — never keyed on a
    component name (same philosophy as :data:`TIMESTAMP_KEYS`). Recognized
    conventions, checked in order:

    * ``restic_exit_code`` — an int outside ``{0, 3}`` is a backup failure
      (0 = success, 3 = some source files unreadable but the snapshot
      completed). restic-backup's ``last-backup.json``.
    * ``exit_code`` — present and a non-zero int is a failure. agent-prompt-sync,
      felix-doc-auditor, felix-deployer tick-signals (``exit_code=0`` is the good
      signal).
    * ``exit_status`` — present and NOT in the success set
      (:data:`_EXIT_STATUS_SUCCESS`) is a failure. A closed enum
      (``success``/``partial``/``failure``) so "not success" is safe here; covers
      felix-core-digest, felix-habit-sweeper, and any tick-signal using
      ``exit_status``.
    * ``status`` — two modes. When the health_check declares
      ``success_status_values``, that allow-list is authoritative and anything
      outside it is a failure (fail-closed; #891). Otherwise the legacy
      deny-list :data:`_STATUS_FAILURE_VALUES` applies (fail-open) — a component
      that invents a new status word reads healthy, which is the defect the
      allow-list exists to retire. Prefer declaring the allow-list.
      An OPEN vocabulary, so it is matched against explicit failure values only
      — a legitimate non-failure ``status`` such as felix-health-check's
      ``ALL_HEALTHY`` / ``FAILURES_DETECTED`` (monitored-system data, not a
      runner fault) must NOT be flipped to failed.
    * ``errors`` — a truthy (non-empty) value is a failure.
    * ``error`` — a truthy value is a failure.
    * ``cycle_error`` — a truthy value is a failure. felix-vikunja-sync-driver's
      ``last-tick.json`` (#891); ``null`` on a clean cycle.

    Returns ``None`` when no explicit failure signal is present. Be conservative:
    a pointer with ``status: success`` / ``exit_code: 0`` / ``exit_status:
    success`` and a fresh timestamp must stay healthy; only an explicit failure
    signal here flips it.
    """
    if "restic_exit_code" in pointer:
        code = pointer["restic_exit_code"]
        if isinstance(code, int) and code not in _RESTIC_OK_EXIT_CODES:
            return f"restic_exit_code={code}"
    # A restic pointer that reports an exit code but no snapshot timestamp must
    # not fall through to another TIMESTAMP_KEYS candidate and read fresh
    # (#902/FR-009). Before this, ``script_finished_at_utc`` would satisfy the
    # freshness probe for a run that produced no snapshot at all, while the
    # inventory asserted the snapshot timestamp must be non-null. Scoped to
    # restic pointers (gated on ``restic_exit_code`` presence, same as before)
    # so no other component is affected. "Usable" means PARSEABLE, not merely
    # non-empty. A truthy but malformed value (e.g. "not-a-date") would
    # otherwise pass a bare-truthiness guard and then fall through
    # TIMESTAMP_KEYS to script_finished_at_utc, reopening the very hole this
    # closes -- verified against the real probe before fixing.
    #
    # (pointer-key-ledger-01M189P6/WP04, T019) This rule used to be NESTED
    # inside the ``restic_exit_code`` branch above, immediately after the
    # exit-code check. It has been lifted out to stand on its own, still
    # gated on the same ``"restic_exit_code" in pointer`` condition so
    # behaviour is unchanged. Reason: a rule that lives inside another rule's
    # presence test cannot be reasoned about, suppressed, or overridden
    # per-key -- and the ledger-authoritative wiring this WP adds is exactly a
    # per-key precedence model. Nesting it meant "suppress the legacy
    # restic_exit_code check because the ledger declares that key" would
    # silently delete this snapshot-timestamp guard too, reopening
    # #902/FR-009 for a component that carries a ledger. Standing alone, the
    # ledger-authoritative branch can skip only the key it actually declares.
    if "restic_exit_code" in pointer:
        snapshot_ts = pointer.get("snapshot_timestamp_utc")
        if _parse_iso(snapshot_ts) is None:
            return "restic pointer has no usable snapshot_timestamp_utc"
    if "prune_exit_code" in pointer:
        code = pointer["prune_exit_code"]
        if isinstance(code, int) and code not in _PRUNE_OK_EXIT_CODES:
            # 127 is the script's "never attempted" sentinel: the run exited
            # before reaching the prune, so retention did not happen.
            return f"prune_exit_code={code}"
    if "exit_code" in pointer:
        code = pointer["exit_code"]
        if isinstance(code, int) and code != 0:
            return f"exit_code={code}"
    exit_status = pointer.get("exit_status")
    if isinstance(exit_status, str) and exit_status.lower() not in _EXIT_STATUS_SUCCESS:
        return f"exit_status={exit_status!r}"
    status = pointer.get("status")
    if isinstance(status, str):
        if success_status_values is not None:
            # Declared allow-list (#891): health is affirmative. Any value the
            # component invents that is not declared healthy is a failure, so a
            # new status word defaults to paging rather than to silence.
            if status.lower() not in success_status_values:
                return (
                    f"status={status!r} not in declared success set "
                    f"{sorted(success_status_values)}"
                )
        elif status.lower() in _STATUS_FAILURE_VALUES:
            return f"status={status!r}"
    errors = pointer.get("errors")
    if errors:
        return f"errors={errors!r}"
    error = pointer.get("error")
    if error:
        return f"error={error!r}"
    cycle_error = pointer.get("cycle_error")
    if cycle_error:
        return f"cycle_error={cycle_error!r}"
    return None


# --------------------------------------------------------------------------- #
# Probe handlers. Each takes the ``health_check`` dict, ``now``, and the
# injected effects; each returns a ProbeResult. Exceptions are caught by the
# dispatcher wrapper, not here.
# --------------------------------------------------------------------------- #


def _probe_http(
    health_check: dict[str, Any],
    now: datetime,
    *,
    http_get: HttpGet,
    run_cmd: RunCmd,
    read_state: ReadState,
) -> ProbeResult:
    endpoint = health_check.get("endpoint")
    expected = health_check.get("expected")
    timeout = health_check.get("timeout_seconds")
    status = http_get(endpoint, timeout=timeout)
    if status == expected:
        return ProbeResult(
            ok=True, stale=False, evaluable=True,
            evidence=f"HTTP {status} == expected {expected}",
        )
    return ProbeResult(
        ok=False, stale=False, evaluable=True,
        evidence=f"HTTP {status} != expected {expected}",
    )


def _probe_command(
    health_check: dict[str, Any],
    now: datetime,
    *,
    http_get: HttpGet,
    run_cmd: RunCmd,
    read_state: ReadState,
) -> ProbeResult:
    """Liveness via exit code: shell / self-check-command / self-test."""
    endpoint = health_check.get("endpoint")
    timeout = health_check.get("timeout_seconds")
    exit_code, stdout, stderr = run_cmd(endpoint, timeout=timeout)
    if exit_code == 0:
        return ProbeResult(
            ok=True, stale=False, evaluable=True,
            evidence=f"exit 0: {stdout.strip()[:120]}",
        )
    return ProbeResult(
        ok=False, stale=False, evaluable=True,
        evidence=f"exit {exit_code}: {(stderr or stdout).strip()[:120]}",
    )


def _probe_systemd_status(
    health_check: dict[str, Any],
    now: datetime,
    *,
    http_get: HttpGet,
    run_cmd: RunCmd,
    read_state: ReadState,
) -> ProbeResult:
    """`systemctl [--user] status …`: active/running → healthy, else failed."""
    endpoint = health_check.get("endpoint")
    timeout = health_check.get("timeout_seconds")
    exit_code, stdout, stderr = run_cmd(endpoint, timeout=timeout)
    text = f"{stdout}\n{stderr}".lower()
    if exit_code == 0 and ("active (running)" in text or "active: active" in text
                           or "active" in text):
        return ProbeResult(
            ok=True, stale=False, evaluable=True,
            evidence=f"systemd active (exit {exit_code})",
        )
    # systemctl returns non-zero for inactive/failed units, which is a real
    # "not ok" — not an inability to evaluate. Only a genuine spawn failure
    # (raised by run_cmd) surfaces as unknown, via the dispatcher wrapper.
    return ProbeResult(
        ok=False, stale=False, evaluable=True,
        evidence=f"systemd not active (exit {exit_code}): {text.strip()[:120]}",
    )


def _freshness_verdict(
    key: str, ts: datetime, max_age: float | None, now: datetime
) -> ProbeResult:
    """Decide the final ``ProbeResult`` for one resolved ``(key, ts)``
    freshness pair.

    Shared tail for both the legacy :data:`TIMESTAMP_KEYS` path and the
    ledger-anchor path (T020/T021), so the future-skew guard (T022) and the
    ``max_age_seconds`` bound are judged identically everywhere a probe
    resolves a timestamp to *the* freshness anchor. A non-anchor ledger
    ``freshness`` key does NOT go through this helper — see
    :func:`_ledger_freshness_result`, which folds its non-conformance into
    ``unhealthy`` rather than the ``stale`` bucket used here.

    Future-skew guard checked FIRST, before the ``max_age is None``
    liveness-only branch and before the bound comparison: without this,
    ``now - ts`` for a future-dated ``ts`` is negative and never exceeds any
    budget, so a corrupted/skewed timestamp reads fresh forever — including
    in the liveness-only case, which has no budget to defeat but still
    benefits from flagging an impossible timestamp. See
    :data:`_FUTURE_SKEW_TOLERANCE` for the value and why it matches
    ``scripts/deploy/lib/snapshot.py``.

    NOTE (T018): ``ts`` may be a NAIVE datetime — an ISO-8601 string with no
    UTC offset parses that way (see :func:`_parse_iso`). ``ts - now`` (or
    ``now - ts`` below) then raises ``TypeError`` (naive vs aware
    comparison), exactly as the pre-existing bound check always has. This is
    deliberate, not an oversight introduced by the guard: the dispatcher
    (:func:`run_probe`) catches any exception a handler raises and maps it
    to ``unknown`` (INV-D). A first-seen ``unknown`` does not alert, so this
    function does not attempt to rescue a naive timestamp — it only must not
    introduce a NEW way to reach that surface silently, and letting the
    comparison raise here (same as before) satisfies that.
    """
    skew = ts - now
    if skew > _FUTURE_SKEW_TOLERANCE:
        return ProbeResult(
            ok=True, stale=True, evaluable=True,
            evidence=(
                f"ts {key}={ts.isoformat()} is future-dated by "
                f"{skew.total_seconds():.0f}s (> "
                f"{int(_FUTURE_SKEW_TOLERANCE.total_seconds())}s tolerance)"
            ),
        )
    if max_age is None:
        # Freshness cannot be judged (WP01's validator warns on the omission).
        # Fall back to liveness-only: the pointer read and parsed, so ok.
        return ProbeResult(
            ok=True, stale=False, evaluable=True,
            evidence=f"pointer readable, ts {key}={ts.isoformat()} "
                     "(no max_age_seconds → liveness only)",
        )

    age = now - ts
    stale = age > timedelta(seconds=max_age)
    return ProbeResult(
        ok=True, stale=stale, evaluable=True,
        evidence=(
            f"ts {key}={ts.isoformat()}, age {age.total_seconds():.0f}s "
            f"vs max_age {max_age}s → {'stale' if stale else 'fresh'}"
        ),
    )


def _ledger_freshness_result(
    freshness_pending: tuple[FreshnessObligation, ...],
    health_check: dict[str, Any],
    now: datetime,
) -> ProbeResult:
    """Resolve every ``freshness`` obligation WP03's evaluator deferred.

    Contract §"Freshness: the anchor, and other bounded keys":

    * The declared **anchor** (contract rule 7: at most one per ledger) is
      resolved specifically via :func:`_freshness_verdict` and drives the
      component's staleness verdict (``stale=True``/``False``) — never a
      fall-through to :data:`TIMESTAMP_KEYS` (T021; #902's general form: an
      absent or unparseable anchor is unhealthy, full stop).
    * A **non-anchor** ``freshness`` key (e.g. ``last_integrity_check_utc``)
      is adjudicated against its own bound but folds ANY non-conformance
      (unparseable, exceeded bound, future-dated) into ``unhealthy`` — there
      is no separate "stale" bucket for it: "a stale verification makes the
      component unhealthy while the component's freshness is still measured
      from the backup timestamp."
    * No declared anchor → nothing left to adjudicate here; the caller's
      adjudicated-keys pass (:func:`_probe_freshness_with_ledger`) already
      decided health.

    Iterates ``freshness_pending`` in the order WP03 collected it (the
    ledger's ``adjudicated`` map's declaration order).
    """
    anchor: FreshnessObligation | None = None
    for obligation in freshness_pending:
        if obligation.anchor:
            anchor = obligation
            continue

        bound = (
            obligation.max_age_seconds
            if obligation.max_age_seconds is not None
            else health_check.get("max_age_seconds")
        )
        ts = _parse_iso(obligation.value)
        if ts is None:
            return ProbeResult(
                ok=False, stale=False, evaluable=True,
                evidence=(
                    f"{obligation.key}={obligation.value!r} is not a "
                    "usable timestamp"
                ),
            )
        skew = ts - now
        if skew > _FUTURE_SKEW_TOLERANCE:
            return ProbeResult(
                ok=False, stale=False, evaluable=True,
                evidence=(
                    f"{obligation.key}={ts.isoformat()} is future-dated by "
                    f"{skew.total_seconds():.0f}s"
                ),
            )
        if bound is not None and (now - ts) > timedelta(seconds=bound):
            return ProbeResult(
                ok=False, stale=False, evaluable=True,
                evidence=(
                    f"{obligation.key}={ts.isoformat()}, age "
                    f"{(now - ts).total_seconds():.0f}s exceeds max_age "
                    f"{bound}s"
                ),
            )

    if anchor is None:
        return ProbeResult(
            ok=True, stale=False, evaluable=True,
            evidence="ledger adjudicated keys satisfied; "
                     "no freshness anchor declared",
        )

    anchor_ts = _parse_iso(anchor.value)
    if anchor_ts is None:
        # T021: an adjudicated key ABSENT from the document is already
        # unhealthy via WP03's evaluator, before this function ever runs. An
        # anchor PRESENT but unparseable gets the same unhealthy verdict for
        # the same reason, and must never fall through to another
        # TIMESTAMP_KEYS candidate — that fall-through is #902's general
        # form, which is the exact defect this whole WP exists to close.
        return ProbeResult(
            ok=False, stale=False, evaluable=True,
            evidence=(
                f"ledger anchor {anchor.key}={anchor.value!r} is not a "
                "usable timestamp"
            ),
        )

    anchor_bound = (
        anchor.max_age_seconds
        if anchor.max_age_seconds is not None
        else health_check.get("max_age_seconds")
    )
    return _freshness_verdict(anchor.key, anchor_ts, anchor_bound, now)


def _probe_freshness_with_ledger(
    pointer: dict[str, Any],
    ledger: dict[str, Any],
    health_check: dict[str, Any],
    now: datetime,
) -> ProbeResult:
    """Adjudicate ``pointer`` against a declared ``key_ledger`` (WP03's
    evaluator), then resolve freshness for the declared anchor (T020/T021).

    The evaluator's verdict is authoritative for **every key it declares**
    (contract Obligation 1) — legacy :func:`_explicit_error` conventions
    apply only to keys the ledger does **not** declare (neither adjudicated
    nor diagnostic_only). Never lets the evaluator's result raise or bypass:
    WP03's :func:`~scripts.canary.ledger.evaluate` is total (NFR-006) and
    this function reads only :class:`~scripts.canary.ledger.LedgerResult`'s
    own dataclass fields — no ``[...]`` indexing into predicate dicts, no
    assumed shapes.
    """
    result = _ledger_evaluate(pointer, ledger, now=now)

    if result.outcome == "unhealthy":
        return ProbeResult(
            ok=False, stale=False, evaluable=True, evidence=result.evidence,
        )
    if result.outcome == "unknown":
        return _unevaluable(result.evidence)

    # result.outcome == "ok": every ADJUDICATED key satisfied its predicate.
    # Legacy field-convention checks apply only to keys the ledger declares
    # nowhere at all (contract Obligation 1 step 3, "not per key" — a
    # well-formed ledger's reconciliation harness (Obligation 2) already
    # guarantees every real producer key is either adjudicated or
    # diagnostic_only, so this is a defensive no-op for a conforming ledger,
    # not a live carve-out).
    adjudicated = ledger.get("adjudicated")
    diagnostic_only = ledger.get("diagnostic_only")
    declared_keys = (
        (set(adjudicated) if isinstance(adjudicated, dict) else set())
        | (set(diagnostic_only) if isinstance(diagnostic_only, dict) else set())
    )
    undeclared = {k: v for k, v in pointer.items() if k not in declared_keys}

    declared_success = health_check.get("success_status_values")
    success_values = (
        frozenset(v.lower() for v in declared_success if isinstance(v, str))
        if isinstance(declared_success, list) and declared_success
        else None
    )
    err = _explicit_error(undeclared, success_values)
    if err is not None:
        return ProbeResult(
            ok=False, stale=False, evaluable=True,
            evidence=f"explicit error in pointer: {err}",
        )

    return _ledger_freshness_result(result.freshness_pending, health_check, now)


def _probe_freshness_legacy(
    pointer: dict[str, Any],
    health_check: dict[str, Any],
    now: datetime,
) -> ProbeResult:
    """The ledger-free freshness path — byte-for-byte the pre-WP04 behaviour
    (T020 step 3), except that both this path and the ledger path now run
    through the shared :func:`_freshness_verdict` tail, which adds the
    future-skew guard (T022; deliberately applies to every freshness-probed
    component, ledgered or not) but reproduces every prior evidence string
    verbatim for a non-future-dated timestamp. 16 components depend on this
    staying unchanged.
    """
    declared = health_check.get("success_status_values")
    success_values = (
        frozenset(v.lower() for v in declared if isinstance(v, str))
        if isinstance(declared, list) and declared
        else None
    )
    err = _explicit_error(pointer, success_values)
    if err is not None:
        return ProbeResult(
            ok=False, stale=False, evaluable=True,
            evidence=f"explicit error in pointer: {err}",
        )

    resolved = _resolve_timestamp(pointer)
    if resolved is None:
        # Bare map (e.g. trust-scan seen-findings) with no candidate timestamp
        # key — uninterpretable shape → honest unknown, never a false healthy.
        return _unevaluable(
            "no interpretable timestamp key "
            f"(tried {', '.join(TIMESTAMP_KEYS)})"
        )

    key, ts = resolved
    max_age = health_check.get("max_age_seconds")
    return _freshness_verdict(key, ts, max_age, now)


def _probe_freshness(
    health_check: dict[str, Any],
    now: datetime,
    *,
    http_get: HttpGet,
    run_cmd: RunCmd,
    read_state: ReadState,
) -> ProbeResult:
    """Freshness pointer probe (the T012 design callout; ledger-aware since
    T020).

    Reads the pointer JSON via ``read_state``. When ``health_check`` declares
    a ``key_ledger`` (mirrors how ``success_status_values`` is already read
    and passed down), dispatches to :func:`_probe_freshness_with_ledger` —
    WP03's evaluator is authoritative for every key it declares, and the
    declared freshness anchor (if any) is resolved specifically rather than
    via :data:`TIMESTAMP_KEYS`. Otherwise resolves the authoritative
    timestamp via :data:`TIMESTAMP_KEYS`, honors explicit error fields, and
    judges staleness against ``max_age_seconds`` when present — unchanged
    for the 16 components with no ledger.
    """
    # Pointer path resolved WP02-style: state_path first, else endpoint.
    path = health_check.get("state_path") or health_check.get("endpoint")
    if not path:
        return _unevaluable("freshness pointer has no state_path/endpoint")

    pointer = read_state(path)

    if not isinstance(pointer, dict):
        # A JSONL log or non-object payload — cannot interpret as a flat
        # pointer. Honest unknown (agent-prompt-sync reads this way by design).
        return _unevaluable(
            f"freshness pointer is not a JSON object ({type(pointer).__name__})"
        )

    ledger = health_check.get("key_ledger")
    if isinstance(ledger, dict):
        return _probe_freshness_with_ledger(pointer, ledger, health_check, now)

    return _probe_freshness_legacy(pointer, health_check, now)


def _probe_log_scan(
    health_check: dict[str, Any],
    now: datetime,
    *,
    http_get: HttpGet,
    run_cmd: RunCmd,
    read_state: ReadState,
) -> ProbeResult:
    """Log-scan probe (log-tail / journal).

    Runs the ``endpoint`` (a ``tail`` / ``journalctl [| grep]`` / ``cat | jq``
    command). For these methods **the command itself does the marker
    filtering** — the real inventory endpoints already embed the grep/tail/jq
    that selects the marker (e.g. ``journalctl … | grep -E
    'credential_alive|credential_dead|…'``). The ``expected`` field is human
    PROSE describing the health condition (e.g. "At least one credential_alive
    within the last window"), NOT a literal substring to match. So healthiness
    is driven by the COMMAND RESULT, never by an ``expected``-substring test:

    * exit 0 + non-empty stdout ⇒ a matching line exists ⇒ marker present ⇒
      healthy (grep exit 0 means a match; a bare ``tail`` returning content
      likewise means the log window is non-empty).
    * exit 0 + empty stdout ⇒ the command ran cleanly but selected NO matching
      lines (grep exit 1 is normalized by a trailing ``|| true`` in some
      endpoints, or the window is simply empty) ⇒ marker absent ⇒ failed.
    * a command that ran but returned non-zero WITH output/stderr ⇒ a real
      command-level failure ⇒ failed; a truly failed spawn raises and is caught
      by the dispatcher wrapper ⇒ unknown.

    When ``max_age_seconds`` is declared and a parseable ISO-8601 timestamp
    leads the most-recent matching line, an older line is ``stale``; otherwise
    the probe is liveness-only. Kept deterministic via the injected ``run_cmd``.
    """
    endpoint = health_check.get("endpoint")
    timeout = health_check.get("timeout_seconds")
    exit_code, stdout, stderr = run_cmd(endpoint, timeout=timeout)
    output = stdout.strip()

    if exit_code != 0:
        # A command error that still produced output is a real failure signal;
        # a truly failed spawn raises and is caught → unknown by the wrapper.
        if output or stderr.strip():
            return ProbeResult(
                ok=False, stale=False, evaluable=True,
                evidence=f"log command exit {exit_code}: "
                         f"{(stderr or stdout).strip()[:120]}",
            )
        return _unevaluable(f"log command exit {exit_code}, no output")

    # Command result — NOT an expected-prose substring — is the marker signal.
    if not output:
        # Clean run, but the endpoint's own grep/tail/jq selected nothing: the
        # marker is absent in the window (stale/dark), not a false healthy.
        return ProbeResult(
            ok=False, stale=False, evaluable=True,
            evidence="log command ran clean but returned no matching lines "
                     "(marker absent in window)",
        )

    max_age = health_check.get("max_age_seconds")
    if max_age is not None:
        # Try to read a leading ISO-8601 timestamp from the last matching line.
        last_line = output.splitlines()[-1]
        ts = _parse_iso(last_line.split()[0]) if last_line.split() else None
        if ts is not None:
            age = now - ts
            if age > timedelta(seconds=max_age):
                return ProbeResult(
                    ok=True, stale=True, evaluable=True,
                    evidence=f"marker present but age {age.total_seconds():.0f}s "
                             f"> max_age {max_age}s",
                )
    return ProbeResult(
        ok=True, stale=False, evaluable=True,
        evidence=f"marker present in log window: {output.splitlines()[-1][:120]}",
    )


def _evaluate_openclaw_crons(
    jobs: list[Any],
    crons: list[str],
    now: datetime,
    grace_seconds: float,
) -> ProbeResult:
    """Aggregate the health of a service's mapped OpenClaw crons (pure, #722).

    ``jobs`` is the ``jobs`` array from ``openclaw cron list --json``; ``crons``
    is the list of cron names this service owns. Precedence — **failed > stale >
    healthy** — worst cron wins:

    * a mapped cron **missing** from ``jobs`` or **disabled** → ``failed`` (real
      config drift: the cron this service depends on is gone).
    * a mapped cron whose most-recent run **errored**
      (``lastRunStatus``/``lastStatus`` in :data:`_STATUS_FAILURE_VALUES`) →
      ``failed`` (single-error trigger; evidence carries ``lastError``).
    * a mapped cron the scheduler **stopped firing** — ``now`` is past its
      ``nextRunAtMs`` by more than ``grace_seconds`` → ``stale``. Schedule-aware:
      a healthy cron always has ``now < nextRunAtMs``, and ``nextRunAtMs``
      advances after every run (incl. errored ones), so this needs no per-cron
      ``max_age`` and copes with heterogeneous cadences (a daily + a weekly cron
      under one service) automatically. A cron that has never run but is not yet
      due (``nextRunAtMs`` in the future) is healthy — nothing is wrong yet.

    Never raises; the caller's dispatcher wrapper is the fail-safe boundary.
    """
    by_name = {
        job.get("name"): job for job in jobs if isinstance(job, dict)
    }
    now_ms = now.timestamp() * 1000.0
    grace_ms = grace_seconds * 1000.0

    failures: list[str] = []
    stale: list[str] = []
    indeterminate: list[str] = []
    # #871 run-identity fingerprint: a cron whose most-recent run errored is a
    # *frozen* failure — it cannot change until the cron next runs, so re-nagging
    # every 6h is noise. We fingerprint each run-error by its ``nextRunAtMs``
    # (stable while frozen; advances on the next run), and only when EVERY failure
    # is a run-error (no live config-drift like missing/disabled) do we hand the
    # signal to dedup for run-identity re-alerting. Any live condition present →
    # signal stays None → normal window re-remind (nag until fixed).
    run_error_signals: list[str] = []
    all_failures_are_run_errors = True

    for name in crons:
        job = by_name.get(name)
        if job is None:
            failures.append(f"{name}: not present in cron list")
            all_failures_are_run_errors = False
            continue
        # Strict boolean check: anything that is not literally ``True`` (missing,
        # ``False``, or a drifted string like ``"disabled"``) fails loud rather
        # than silently healing a not-enabled cron. OpenClaw emits a boolean
        # ``enabled`` today (verified live); if that ever drifts, "not True" is
        # the safe direction — page, never false-heal.
        if job.get("enabled") is not True:
            failures.append(f"{name}: not enabled (enabled={job.get('enabled')!r})")
            all_failures_are_run_errors = False
            continue

        state = job.get("state") if isinstance(job.get("state"), dict) else {}
        status = state.get("lastRunStatus") or state.get("lastStatus")
        if isinstance(status, str) and status.lower() in _STATUS_FAILURE_VALUES:
            last_err = (
                state.get("lastError")
                or state.get("lastDiagnosticSummary")
                or ""
            )
            failures.append(
                f"{name}: lastRunStatus={status} ({str(last_err).strip()[:80]})"
            )
            # Fingerprint this frozen run-error by its next-run anchor (advances
            # only when the cron actually runs again) so dedup re-alerts on a new
            # run, not on the same frozen one (#871).
            run_error_signals.append(f"{name}@{state.get('nextRunAtMs')!r}")
            continue

        next_run = state.get("nextRunAtMs")
        if not isinstance(next_run, (int, float)):
            # The freshness anchor is missing/malformed on an enabled, non-errored
            # cron — the one signal this probe exists to check. Do NOT fall through
            # to healthy (that would be a false-healthy on freshness); record it as
            # indeterminate so the service resolves to unknown with named evidence.
            indeterminate.append(f"{name}: missing/invalid nextRunAtMs ({next_run!r})")
            continue
        if now_ms > next_run + grace_ms:
            overdue_s = (now_ms - next_run) / 1000.0
            stale.append(f"{name}: overdue {overdue_s:.0f}s past nextRunAtMs")
            continue

    # Precedence: a concrete failure or overdue signal outranks an indeterminate
    # freshness anchor; only when nothing is failed/stale does an indeterminate
    # cron make the whole service unknown (honest, never a false healthy).
    if failures:
        # Hand dedup a run-identity signal ONLY when every failure is a frozen
        # run-error (#871). If any live config-drift failure is present, signal
        # stays None so that condition re-nags on the normal window until fixed.
        signal = (
            "|".join(sorted(run_error_signals))
            if all_failures_are_run_errors and run_error_signals
            else None
        )
        return ProbeResult(
            ok=False, stale=False, evaluable=True,
            evidence="cron failure(s): " + "; ".join(failures),
            signal=signal,
        )
    if stale:
        return ProbeResult(
            ok=True, stale=True, evaluable=True,
            evidence="cron(s) overdue: " + "; ".join(stale),
        )
    if indeterminate:
        return _unevaluable("cron freshness indeterminate: " + "; ".join(indeterminate))
    return ProbeResult(
        ok=True, stale=False, evaluable=True,
        evidence=(
            f"{len(crons)} cron(s) enabled, ok, and on schedule: "
            f"{', '.join(crons)}"
        ),
    )


def _probe_openclaw_cron(
    health_check: dict[str, Any],
    now: datetime,
    *,
    http_get: HttpGet,
    run_cmd: RunCmd,
    read_state: ReadState,
) -> ProbeResult:
    """OpenClaw cron-state probe (#722).

    Runs the ``endpoint`` command (an absolute ``openclaw cron list --json`` —
    the endpoint string carries the absolute path from service-inventory.json
    because the canary's systemd unit has no ``PATH``; see the seam exception in
    scripts/common/openclaw_bin.py), parses its JSON, and delegates to
    :func:`_evaluate_openclaw_crons` for the service's mapped ``crons``.

    Fail-open (INV-D): a non-zero exit (gateway unreachable / CLI error) or
    unparseable output returns ``evaluable=False`` → the caller maps it to
    ``unknown``, never a false ``failed``. A missing ``endpoint``/``crons`` is a
    config error surfaced the same honest way.
    """
    endpoint = health_check.get("endpoint")
    if not endpoint:
        return _unevaluable("openclaw-cron-state: no endpoint command configured")
    crons = health_check.get("crons")
    if not isinstance(crons, list) or not crons:
        return _unevaluable("openclaw-cron-state: no crons configured")

    grace = health_check.get("grace_seconds", _DEFAULT_CRON_GRACE_SECONDS)
    timeout = health_check.get("timeout_seconds")
    exit_code, stdout, stderr = run_cmd(endpoint, timeout=timeout)
    if exit_code != 0:
        return _unevaluable(
            f"openclaw cron list exit {exit_code}: "
            f"{(stderr or stdout).strip()[:120]}"
        )

    try:
        payload = json.loads(stdout)
    except (ValueError, TypeError) as exc:
        return _unevaluable(f"openclaw cron list output not JSON: {exc}")

    jobs = payload.get("jobs") if isinstance(payload, dict) else None
    if not isinstance(jobs, list):
        return _unevaluable("openclaw cron list JSON has no 'jobs' array")

    return _evaluate_openclaw_crons(jobs, crons, now, grace)


# method → handler map. Keys mirror WP02's HANDLED_METHODS (contracts §2).
_DISPATCH: dict[
    str,
    Callable[..., ProbeResult],
] = {
    "http": _probe_http,
    "shell": _probe_command,
    "self-check-command": _probe_command,
    "self-test": _probe_command,
    "systemd-status": _probe_systemd_status,
    "tick-signal-file": _probe_freshness,
    "signal-file": _probe_freshness,
    "state-file": _probe_freshness,
    "log-tail": _probe_log_scan,
    "journal": _probe_log_scan,
    _OPENCLAW_CRON_METHOD: _probe_openclaw_cron,
}


def run_probe(
    health_check: dict[str, Any],
    now: datetime,
    *,
    http_get: HttpGet,
    run_cmd: RunCmd,
    read_state: ReadState,
) -> ProbeResult:
    """Dispatch a ``health_check`` to its probe and return a :class:`ProbeResult`.

    Dispatches on ``health_check["method"]`` via :data:`_DISPATCH`. An unhandled
    or ``none`` method (which WP02 already classifies as a coverage gap, so this
    is purely defensive) returns ``evaluable=False``. Any exception raised by a
    handler or an injected effect is caught and turned into an unevaluable
    result — :func:`run_probe` never raises for a component-level fault (INV-D).
    """
    method = (health_check or {}).get("method")
    handler = _DISPATCH.get(method) if method else None
    if handler is None:
        return _unevaluable(f"unhandled or missing method: {method!r}")
    try:
        return handler(
            health_check,
            now,
            http_get=http_get,
            run_cmd=run_cmd,
            read_state=read_state,
        )
    except Exception as exc:  # noqa: BLE001 — fail-safe boundary (INV-D)
        return _unevaluable(f"{type(exc).__name__}: {exc}")
