"""felix-health-check systemd entrypoint (WP03, #676; alert-bus migration #701;
coverage checks #1063).

Each run:

1. evaluates two **coverage checks** (:mod:`.coverage`): the dead-man's
   switch on ``felix-canary`` and an independent ``restic-backup`` check,
   both decided by the canary's own evaluator on their inventory
   declarations. From 2026-09-27 to 2026-10-14 the canary was dark and every
   backup failed while this check reported ``ALL_HEALTHY`` 34 times (#1063);
2. runs the version-controlled bash service checks, ``health-check.sh`` next
   to this module, via ``subprocess.run`` (never ``exec``: an ``exec`` would
   replace this process and make classification impossible, Codex finding #1);
3. combines both into one status with precedence ``FAILURES_DETECTED`` >
   ``SCRIPT_MISSING`` > ``UNKNOWN`` > ``ALL_HEALTHY``, so ``ALL_HEALTHY`` is
   only issued when every check affirmatively passed;
4. stamps a signal file and pushes one alert on any non-healthy outcome via
   the unified ``felix-alert`` bus (``scripts.common.alert_bus.emit``; #701).

Invoked by ``scripts/office2/felix-health-check.service`` via::

    python3 -m scripts.office2.felix_health_check.run

Contracts: ``kitty-specs/deterministic-monitoring-checks-01KX1XNW/contracts/
health-check-runner.contract.md`` (runner) and ``kitty-specs/
canary-deadman-backup-coverage-01M4XVY3/contracts/health-check-run-record.md``
(the run record the canary reads, and the alert details).

Exit code
---------
Always ``0`` on a completed run — a health *failure* is data, not a runner
error. Coverage, shell-script and alert-delivery faults are contained and
reported in the record (the unit has no ``OnFailure=``, so an escaping
exception would be a silent systemd failure until the canary's 13 h
freshness probe noticed). The one fault that cannot be contained is failing
to write the record itself; that is exactly what the canary's probe sees.
"""

from __future__ import annotations

import datetime as _dt
import json
import logging
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Sequence

from scripts.common.alert_bus import Alert, AlertResult, Severity, emit

logger = logging.getLogger("felix_health_check")

# --- Constants -------------------------------------------------------------

# Version-controlled since #1063 (previously an untracked host-only copy at
# /home/claude/helper-scripts/health-check.sh). Runs from the deployed checkout.
HEALTH_CHECK_SCRIPT = Path(__file__).resolve().with_name("health-check.sh")
SIGNAL_FILE = Path("/data/services/openclaw/felix-health-check/last-run.json")

# Bash subprocess timeout. The check itself is expected to run in seconds;
# this is a generous ceiling so a hung dependency can't wedge the timer tick.
SUBPROCESS_TIMEOUT_SECONDS = 300

ALERT_SOURCE = "felix-health-check/run"
ALERT_TITLE = "Felix Health Check — office2"

# Raw output is truncated before being folded into the alert (contract: ~4 KB).
# The bus renderer additionally truncates every detail value to 500 chars, which
# is why coverage findings travel as their own details ahead of the output.
OUTPUT_TRUNCATE_BYTES = 4096
TRUNCATION_MARKER = "\n... (truncated)"

# Status classification enum (closed set; the canary's probe of the run record
# allow-lists ALL_HEALTHY and FAILURES_DETECTED, so no new words, ever).
STATUS_ALL_HEALTHY = "ALL_HEALTHY"
STATUS_FAILURES_DETECTED = "FAILURES_DETECTED"
STATUS_UNKNOWN = "UNKNOWN"
STATUS_SCRIPT_MISSING = "SCRIPT_MISSING"

# Tokens emitted by health-check.sh (unchanged, FR-010 — reused as-is).
TOKEN_ALL_HEALTHY = "ALL_HEALTHY"
TOKEN_FAILURES_DETECTED = "FAILURES_DETECTED"

ALERTING_STATUSES = frozenset(
    {STATUS_FAILURES_DETECTED, STATUS_UNKNOWN, STATUS_SCRIPT_MISSING}
)

# Coverage components, in report order. Duplicated from coverage.py on purpose:
# when that module cannot even be imported, the record must still carry one
# unknown entry per component (contract invariant 4).
_COVERAGE_COMPONENTS: tuple[str, ...] = ("felix-canary", "restic-backup")


def _utc_now() -> _dt.datetime:
    return _dt.datetime.now(tz=_dt.timezone.utc)


def _iso(ts: _dt.datetime) -> str:
    return ts.strftime("%Y-%m-%dT%H:%M:%SZ")


def _truncate(text: str, limit: int = OUTPUT_TRUNCATE_BYTES) -> str:
    """Bound ``text`` to ``limit`` bytes, appending a truncation marker.

    Truncates on the encoded byte length (not character count) so the
    ~4 KB ceiling in the contract is honored even for multi-byte output,
    then decodes leniently to avoid splitting a multi-byte sequence.
    """
    encoded = text.encode("utf-8", errors="replace")
    if len(encoded) <= limit:
        return text
    head = encoded[:limit].decode("utf-8", errors="ignore")
    return head + TRUNCATION_MARKER


def classify(stdout: str, stderr: str, returncode: int) -> str:
    """Classify a completed shell run with failure-wins precedence (Codex #9).

    1. ``FAILURES_DETECTED`` present in stdout OR stderr wins outright,
       even if ``ALL_HEALTHY`` also appears in the combined output.
    2. Else ``ALL_HEALTHY`` present AND ``returncode == 0`` -> healthy.
    3. Else -> ``UNKNOWN`` (neither token, or a non-zero exit without a
       clear failure token).
    """
    combined = f"{stdout}\n{stderr}"
    if TOKEN_FAILURES_DETECTED in combined:
        return STATUS_FAILURES_DETECTED
    if TOKEN_ALL_HEALTHY in combined and returncode == 0:
        return STATUS_ALL_HEALTHY
    return STATUS_UNKNOWN


def combine(script_status: str, findings: Sequence[Any]) -> str:
    """The run's single status (data-model.md "Run verdict").

    A failure anywhere wins, so a fault is never hidden behind an inability
    to check something else. Then a missing script, then any unknown. Only
    a shell ``ALL_HEALTHY`` with every coverage finding ``ok`` is healthy.
    """
    kinds = {getattr(f, "finding", "unknown") for f in findings}
    if script_status == STATUS_FAILURES_DETECTED or "failure" in kinds:
        return STATUS_FAILURES_DETECTED
    if script_status == STATUS_SCRIPT_MISSING:
        return STATUS_SCRIPT_MISSING
    if script_status != STATUS_ALL_HEALTHY or kinds != {"ok"}:
        return STATUS_UNKNOWN
    return STATUS_ALL_HEALTHY


def _atomic_write_json(target: Path, payload: dict) -> None:
    """Atomically overwrite ``target`` with ``payload`` as JSON.

    Writes a tempfile in the same directory (so ``os.rename`` is
    POSIX-atomic), fsyncs, renames, and cleans up on failure. Mirrors
    ``scripts/openclaw/heartbeat_gate/ledger.py::atomic_write_json``.
    """
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            dir=str(target.parent),
            prefix=target.name + ".",
            suffix=".tmp",
            delete=False,
            encoding="utf-8",
        ) as fp:
            json.dump(payload, fp, indent=2)
            fp.flush()
            os.fsync(fp.fileno())
            tmp_path = Path(fp.name)
        os.rename(tmp_path, target)
        tmp_path = None
    finally:
        if tmp_path is not None:
            try:
                tmp_path.unlink()
            except OSError:  # pragma: no cover - best-effort cleanup
                pass


def run_health_check_script(
    script_path: Path = HEALTH_CHECK_SCRIPT,
) -> subprocess.CompletedProcess[str]:
    """Run the bash health-check script via ``subprocess.run`` (NOT ``exec``).

    Using ``subprocess.run`` (rather than ``os.exec*``) is load-bearing:
    an ``exec`` call would replace this Python process image with bash,
    making it impossible for this function to return and for the caller
    to classify the output (Codex finding #1).
    """
    return subprocess.run(  # noqa: S603 - fixed argv, no shell
        ["bash", str(script_path)],
        capture_output=True,
        text=True,
        timeout=SUBPROCESS_TIMEOUT_SECONDS,
        check=False,
    )


class _Unavailable:
    """A coverage finding for when the coverage module itself is unusable."""

    def __init__(self, component: str, evidence: str) -> None:
        self.component = component
        self.outcome = "unavailable"
        self.finding = "unknown"
        self.evidence = evidence

    def to_record(self) -> dict:
        return {"component": self.component, "outcome": self.outcome,
                "finding": self.finding, "evidence": self.evidence}


def _evaluate_coverage_guarded(now: _dt.datetime) -> list:
    """Coverage findings, or one unknown per component if coverage cannot
    run at all. Never raises (research R5)."""
    try:
        from scripts.office2.felix_health_check import coverage

        findings = list(coverage.evaluate_coverage(now))
        if [f.component for f in findings] != list(_COVERAGE_COMPONENTS):
            raise RuntimeError(f"unexpected coverage result {[f.component for f in findings]}")
        return findings
    except Exception as exc:  # noqa: BLE001 - fail closed (NFR-003)
        evidence = f"coverage unavailable: {type(exc).__name__}: {exc}"
        logger.error(evidence)
        return [_Unavailable(c, evidence) for c in _COVERAGE_COMPONENTS]


def _run_script_guarded() -> tuple[str, int | None, str, str | None]:
    """``(script_status, exit_code, raw_output, script_note)``. Never raises.

    ``script_note`` is set when the script did not produce a classifiable run
    (missing, timed out, failed to launch or decode); it leads the alert.
    """
    if not HEALTH_CHECK_SCRIPT.is_file() or not os.access(HEALTH_CHECK_SCRIPT, os.X_OK):
        note = f"Health-check script not found or not executable: {HEALTH_CHECK_SCRIPT}"
        logger.error(note)
        return STATUS_SCRIPT_MISSING, None, note, note
    try:
        completed = run_health_check_script()
    except subprocess.TimeoutExpired as exc:
        note = f"health-check.sh timed out after {SUBPROCESS_TIMEOUT_SECONDS}s"
        logger.error("%s: %s", note, exc)
        return STATUS_UNKNOWN, None, note, note
    except Exception as exc:  # noqa: BLE001 - launch/decoding faults (Codex-6)
        note = f"health-check.sh did not run: {type(exc).__name__}: {exc}"
        logger.error(note)
        return STATUS_UNKNOWN, None, note, note
    stdout = completed.stdout or ""
    stderr = completed.stderr or ""
    status = classify(stdout, stderr, completed.returncode)
    logger.info("health-check.sh classified as %s (rc=%s)", status, completed.returncode)
    return status, completed.returncode, f"{stdout}{stderr}", None


def _delivery_record(result: AlertResult) -> dict:
    """Adapt an ``AlertResult`` to the legacy ``last-run.json`` delivery shape.

    The pre-migration signal file records
    ``{"attempted": bool, "sent": bool, "detail": str}`` and downstream
    consumers depend on that exact shape (NFR-004). Map the bus result onto
    it (migration contract §5):

    - ``attempted`` = ``result.topic_configured`` — a blank topic means the
      bus made no POST attempt, exactly like the old "topic not configured"
      short-circuit (``attempted=False``).
    - ``sent`` = ``result.ok`` — delivery succeeded.
    - ``detail`` = ``result.reason or "delivered"`` — the bus's failure
      reason on failure, or the literal ``"delivered"`` on success.
    """
    return {
        "attempted": result.topic_configured,
        "sent": result.ok,
        "detail": result.reason or "delivered",
    }


def alert_details(status: str, body: str, findings: Sequence[Any] = (),
                  script_note: str | None = None) -> dict[str, str]:
    """The alert's ``details``, in render order (run-record contract).

    The bus truncates each value to 500 characters, so every coverage
    finding is its own entry and all of them precede the shell output:
    appended to the output, they were cut off (Codex post-plan finding 3).
    A script that did not run is listed first.
    """
    details: dict[str, str] = {}
    if script_note:
        details["script"] = script_note
    for f in findings:
        if getattr(f, "finding", "unknown") != "ok":
            details[f"coverage:{f.component}"] = f"{f.finding.upper()} ({f.outcome}): {f.evidence}"
    details["status"] = status
    details["output"] = body
    return details


def send_alert(status: str, body: str, *, findings: Sequence[Any] = (),
               script_note: str | None = None) -> dict:
    """Emit one alert for a non-healthy outcome via the felix-alert bus.

    Delivery I/O (topic resolution, ntfy POST, truncation/redaction) is
    owned entirely by ``scripts.common.alert_bus.emit`` — this module holds
    no curl/ntfy code (SC-006, #701). ``emit()`` never raises (NFR-001).

    Returns the legacy delivery-record dict
    ``{"attempted": bool, "sent": bool, "detail": str}``.
    """
    description = f"Felix health check on office2 reported: {status}."
    bad = [f.component for f in findings if getattr(f, "finding", "unknown") != "ok"]
    if bad:
        description += f" Coverage: {', '.join(bad)}."
    result = emit(
        Alert(
            source=ALERT_SOURCE,
            severity=Severity.ERROR,
            title=ALERT_TITLE,
            description=description,
            details=alert_details(status, body, findings, script_note),
        )
    )
    delivery = _delivery_record(result)
    if delivery["sent"]:
        logger.info("felix-alert delivered (status=%s)", status)
    elif delivery["attempted"]:
        logger.error("felix-alert send failed (non-fatal): %s", delivery["detail"])
    else:
        logger.warning("felix-alert skipped: %s", delivery["detail"])
    return delivery


def _coverage_records(findings: Sequence[Any]) -> list[dict]:
    """Serialize findings; a finding that cannot serialize becomes unknown."""
    records = []
    for component, f in zip(_COVERAGE_COMPONENTS, findings):
        try:
            records.append(f.to_record())
        except Exception as exc:  # noqa: BLE001 - the record must still be written
            records.append(_Unavailable(component, f"{type(exc).__name__}: {exc}").to_record())
    return records


def _send_alert_guarded(status: str, body: str, findings: Sequence[Any],
                        script_note: str | None) -> dict:
    """``send_alert`` never raises today (the bus's ``emit`` is total), but the
    record must be written even if that ever changes: a missing record is
    silent for up to 13 h, until the canary's freshness probe notices."""
    try:
        return send_alert(status, body, findings=findings, script_note=script_note)
    except Exception as exc:  # noqa: BLE001 - contain; record the failure
        logger.error("felix-alert send raised (non-fatal): %s", exc)
        return {"attempted": True, "sent": False, "detail": f"send_alert raised {type(exc).__name__}: {exc}"}


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    now = _utc_now()

    # Coverage first and independently of the shell script: a missing or
    # broken script must not also blind the dead-man's switch (research R5).
    findings = _evaluate_coverage_guarded(now)
    coverage_records = _coverage_records(findings)
    for rec in coverage_records:
        logger.info("coverage %s: %s (%s) %s", rec["component"], rec["finding"], rec["outcome"], rec["evidence"])

    script_status, exit_code, raw_output, script_note = _run_script_guarded()
    status = combine(script_status, findings)
    logger.info("health-check classified as %s (script=%s, rc=%s)", status, script_status, exit_code)

    delivery = {"attempted": False, "sent": False, "detail": "no alert (healthy)"}
    if status in ALERTING_STATUSES:
        delivery = _send_alert_guarded(status, _truncate(raw_output), findings, script_note)

    # Key set pinned by the run-record contract: nothing here may be in the
    # canary's explicit-error vocabulary or outrank ran_at_utc as a timestamp.
    # A failure to write the record itself is the one fault not contained:
    # it surfaces as a failed unit and a stale record, which the canary's
    # freshness probe on this component reports.
    _atomic_write_json(
        SIGNAL_FILE,
        {
            "status": status,
            "ran_at_utc": _iso(now),
            "exit_code": exit_code,
            "delivery": delivery,
            "script_status": script_status,
            "script_path": str(HEALTH_CHECK_SCRIPT),
            "coverage_checks": coverage_records,
        },
    )
    return 0


if __name__ == "__main__":  # pragma: no cover - systemd entrypoint
    sys.exit(main(sys.argv[1:]))
