"""felix-health-check systemd entrypoint (WP03, #676; alert-bus migration #701).

Runs the existing bash health check
(``/home/claude/helper-scripts/health-check.sh``) via ``subprocess.run``
(never ``exec`` — an ``exec`` would replace this process and make
classification impossible, Codex finding #1), classifies the result with
failure-wins precedence, stamps a signal file for observability, and
pushes an alert on any non-healthy outcome via the unified ``felix-alert``
bus (``scripts.common.alert_bus.emit`` — no local curl/ntfy code; #701).

Invoked by ``scripts/office2/felix-health-check.service`` via::

    python3 -m scripts.office2.felix_health_check.run

See ``kitty-specs/deterministic-monitoring-checks-01KX1XNW/contracts/
health-check-runner.contract.md`` for the authoritative behavior contract
this module implements.

Exit code
---------
Always ``0`` on a completed run — a health *failure* is data, not a
runner error (per contract). Non-zero only if the wrapper itself cannot
run at all (an unhandled exception escapes ``main``), which surfaces via
systemd ``status=failed``.
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

from scripts.common.alert_bus import Alert, AlertResult, Severity, emit

logger = logging.getLogger("felix_health_check")

# --- Constants -------------------------------------------------------------

HEALTH_CHECK_SCRIPT = Path("/home/claude/helper-scripts/health-check.sh")
SIGNAL_FILE = Path("/data/services/openclaw/felix-health-check/last-run.json")

# Bash subprocess timeout. The check itself is expected to run in seconds;
# this is a generous ceiling so a hung dependency can't wedge the timer tick.
SUBPROCESS_TIMEOUT_SECONDS = 300

# Alert delivery (via the unified felix-alert bus, #701). The bus resolves
# the single ``FELIX_ALERT_NTFY_TOPIC`` and owns all ntfy I/O; this module
# no longer reads ``NTFY_TOPIC`` or POSTs directly (SC-006). Priority/tags are
# derived by the bus from ``Severity``, so they are no longer set here.
ALERT_SOURCE = "felix-health-check/run"
ALERT_TITLE = "Felix Health Check — office2"

# Raw output is truncated before being folded into the alert (contract: ~4 KB).
# The bus renderer additionally truncates/redacts, so this is a defensive
# first bound that keeps the signal-file body compact.
OUTPUT_TRUNCATE_BYTES = 4096
TRUNCATION_MARKER = "\n... (truncated)"

# Status classification enum (closed set).
STATUS_ALL_HEALTHY = "ALL_HEALTHY"
STATUS_FAILURES_DETECTED = "FAILURES_DETECTED"
STATUS_UNKNOWN = "UNKNOWN"
STATUS_SCRIPT_MISSING = "SCRIPT_MISSING"

# Tokens emitted by health-check.sh (unchanged, FR-010 — reused as-is).
TOKEN_ALL_HEALTHY = "ALL_HEALTHY"
TOKEN_FAILURES_DETECTED = "FAILURES_DETECTED"

# Statuses that trigger an ntfy push (everything except a clean healthy run).
ALERTING_STATUSES = frozenset(
    {STATUS_FAILURES_DETECTED, STATUS_UNKNOWN, STATUS_SCRIPT_MISSING}
)


def _utc_now_iso() -> str:
    return _dt.datetime.now(tz=_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


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
    """Classify a completed run with failure-wins precedence (Codex #9).

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


def send_alert(status: str, body: str) -> dict:
    """Emit an alert for a non-healthy outcome via the felix-alert bus.

    Delivery I/O (topic resolution, ntfy POST, truncation/redaction) is
    owned entirely by ``scripts.common.alert_bus.emit`` — this module holds
    no curl/ntfy code (SC-006, #701). ``emit()`` never raises (NFR-001), so
    this function is non-fatal for all routine delivery failure modes.

    Returns the legacy delivery-record dict
    ``{"attempted": bool, "sent": bool, "detail": str}`` (via the adapter)
    so ``last-run.json`` stays byte-compatible with the pre-migration shape.
    """
    result = emit(
        Alert(
            source=ALERT_SOURCE,
            severity=Severity.ERROR,
            title=ALERT_TITLE,
            description=f"Felix health check on office2 reported: {status}.",
            details={"status": status, "output": body},
        )
    )
    delivery = _delivery_record(result)
    if delivery["sent"]:
        logger.info("felix-alert delivered (status=%s)", status)
    elif delivery["attempted"]:
        logger.error(
            "felix-alert send failed (non-fatal): %s", delivery["detail"]
        )
    else:
        logger.warning("felix-alert skipped: %s", delivery["detail"])
    return delivery


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ran_at_utc = _utc_now_iso()

    if not HEALTH_CHECK_SCRIPT.is_file() or not os.access(HEALTH_CHECK_SCRIPT, os.X_OK):
        status = STATUS_SCRIPT_MISSING
        logger.error(
            "health-check script missing or non-executable: %s", HEALTH_CHECK_SCRIPT
        )
        body = _truncate(f"Health-check script not found or not executable: {HEALTH_CHECK_SCRIPT}")
        delivery: dict = send_alert(status, body)
        _atomic_write_json(
            SIGNAL_FILE,
            {
                "status": status,
                "ran_at_utc": ran_at_utc,
                "exit_code": None,
                "delivery": delivery,
            },
        )
        return 0

    try:
        completed = run_health_check_script()
    except subprocess.TimeoutExpired as exc:
        status = STATUS_UNKNOWN
        logger.error("health-check.sh timed out: %s", exc)
        body = _truncate(f"health-check.sh timed out after {SUBPROCESS_TIMEOUT_SECONDS}s")
        delivery = send_alert(status, body)
        _atomic_write_json(
            SIGNAL_FILE,
            {
                "status": status,
                "ran_at_utc": ran_at_utc,
                "exit_code": None,
                "delivery": delivery,
            },
        )
        return 0

    status = classify(completed.stdout, completed.stderr, completed.returncode)
    logger.info("health-check classified as %s (rc=%s)", status, completed.returncode)

    delivery = {"attempted": False, "sent": False, "detail": "no alert (healthy)"}
    if status in ALERTING_STATUSES:
        raw_output = f"{completed.stdout}{completed.stderr}"
        body = _truncate(raw_output)
        delivery = send_alert(status, body)

    _atomic_write_json(
        SIGNAL_FILE,
        {
            "status": status,
            "ran_at_utc": ran_at_utc,
            "exit_code": completed.returncode,
            "delivery": delivery,
        },
    )
    return 0


if __name__ == "__main__":  # pragma: no cover - systemd entrypoint
    sys.exit(main(sys.argv[1:]))
