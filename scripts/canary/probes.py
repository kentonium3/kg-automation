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
candidate timestamp key (e.g. ``felix-trust-scan``'s ``seen-findings.json``
fingerprint map) or a JSONL audit log (e.g. ``agent-prompt-sync``) surfaced as
a non-dict — the probe returns ``evaluable=False`` → the caller maps it to
``unknown`` with evidence naming why. This is deliberately honest: a persistent
``unknown`` WARN is correct behavior, better than a false ``healthy``. Such
components read as persistent-unknown by design until a future pass extends the
probe; that is expected (INV-002), not a bug.

``restic`` note: restic's ``last-backup.json`` uses ``snapshot_timestamp_utc``
(in :data:`TIMESTAMP_KEYS`) and a ``restic_exit_code`` in ``{0, 3}`` as the
"good" signal; WP05 converted restic to a ``state-file`` freshness check that
relies on exactly this probe.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

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
#   Using "not success" here would false-fail ``ALL_HEALTHY``. So ``status`` is
#   matched against an explicit failure-VALUE set only.
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


@dataclass(frozen=True)
class ProbeResult:
    """Raw output of a single probe evaluator.

    * ``ok`` — the probe's raw pass/fail signal.
    * ``stale`` — freshness/recency bound exceeded (freshness + log-scan only).
    * ``evaluable`` — ``False`` ⇒ the probe could not run conclusively; the
      caller maps this to ``unknown``.
    * ``evidence`` — human-readable detail (status code, exit code, age, missing
      marker, or error text).
    """

    ok: bool
    stale: bool
    evaluable: bool
    evidence: str


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


def _explicit_error(pointer: dict[str, Any]) -> str | None:
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
    * ``status`` — present and holding an explicit failure VALUE
      (:data:`_STATUS_FAILURE_VALUES`, e.g. ``error``/``failed``) is a failure.
      An OPEN vocabulary, so it is matched against explicit failure values only
      — a legitimate non-failure ``status`` such as felix-health-check's
      ``ALL_HEALTHY`` / ``FAILURES_DETECTED`` (monitored-system data, not a
      runner fault) must NOT be flipped to failed.
    * ``errors`` — a truthy (non-empty) value is a failure.
    * ``error`` — a truthy value is a failure.

    Returns ``None`` when no explicit failure signal is present. Be conservative:
    a pointer with ``status: success`` / ``exit_code: 0`` / ``exit_status:
    success`` and a fresh timestamp must stay healthy; only an explicit failure
    signal here flips it.
    """
    if "restic_exit_code" in pointer:
        code = pointer["restic_exit_code"]
        if isinstance(code, int) and code not in _RESTIC_OK_EXIT_CODES:
            return f"restic_exit_code={code}"
    if "exit_code" in pointer:
        code = pointer["exit_code"]
        if isinstance(code, int) and code != 0:
            return f"exit_code={code}"
    exit_status = pointer.get("exit_status")
    if isinstance(exit_status, str) and exit_status.lower() not in _EXIT_STATUS_SUCCESS:
        return f"exit_status={exit_status!r}"
    status = pointer.get("status")
    if isinstance(status, str) and status.lower() in _STATUS_FAILURE_VALUES:
        return f"status={status!r}"
    errors = pointer.get("errors")
    if errors:
        return f"errors={errors!r}"
    error = pointer.get("error")
    if error:
        return f"error={error!r}"
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


def _probe_freshness(
    health_check: dict[str, Any],
    now: datetime,
    *,
    http_get: HttpGet,
    run_cmd: RunCmd,
    read_state: ReadState,
) -> ProbeResult:
    """Freshness pointer probe (the T012 design callout).

    Reads the pointer JSON via ``read_state``, resolves its authoritative
    timestamp via :data:`TIMESTAMP_KEYS`, honors explicit error fields, and
    judges staleness against ``max_age_seconds`` when present.
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

    # Explicit error signal wins over freshness (restic_exit_code / errors).
    err = _explicit_error(pointer)
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
