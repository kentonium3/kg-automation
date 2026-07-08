"""felix-health-check systemd entrypoint (WP03, #676).

Runs the existing bash health check
(``/home/claude/helper-scripts/health-check.sh``) via ``subprocess.run``
(never ``exec`` — an ``exec`` would replace this process and make
classification impossible, Codex finding #1), classifies the result with
failure-wins precedence, stamps a signal file for observability, and
pushes an ntfy alert on any non-healthy outcome.

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

logger = logging.getLogger("felix_health_check")

# --- Constants -------------------------------------------------------------

HEALTH_CHECK_SCRIPT = Path("/home/claude/helper-scripts/health-check.sh")
SIGNAL_FILE = Path("/data/services/openclaw/felix-health-check/last-run.json")

# Bash subprocess timeout. The check itself is expected to run in seconds;
# this is a generous ceiling so a hung dependency can't wedge the timer tick.
SUBPROCESS_TIMEOUT_SECONDS = 300

# ntfy delivery.
NTFY_TOPIC_ENV = "NTFY_TOPIC"
NTFY_BASE_URL = "https://ntfy.sh"
NTFY_TITLE = "Felix Health Check — office2"
NTFY_PRIORITY = "high"
NTFY_TAGS = "warning,rotating_light"
NTFY_CURL_MAX_TIME_SECONDS = 10

# Raw output is truncated before being pushed to ntfy (contract: ~4 KB).
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


def send_ntfy_alert(status: str, body: str) -> dict:
    """POST an ntfy alert for a non-healthy outcome.

    Returns a small delivery-record dict (never raises for routine
    failure modes): ``{"attempted": bool, "sent": bool, "detail": str}``.
    Mirrors the non-fatal-on-failure pattern in
    ``scripts/office2/security-monitor/audit.sh:243-255`` and
    ``scripts/deploy/felix-deployer/notify.py``: the topic is read from
    an environment variable (``NTFY_TOPIC``) and is never hard-coded or
    committed here.
    """
    topic = os.environ.get(NTFY_TOPIC_ENV, "").strip()
    if not topic:
        detail = f"ntfy skipped: {NTFY_TOPIC_ENV} not configured"
        logger.warning(detail)
        return {"attempted": False, "sent": False, "detail": detail}

    try:
        result = subprocess.run(  # noqa: S603 - argv list, no shell
            [
                "curl",
                "--silent",
                "--show-error",
                "--max-time",
                str(NTFY_CURL_MAX_TIME_SECONDS),
                "-H",
                f"Title: {NTFY_TITLE}",
                "-H",
                f"Priority: {NTFY_PRIORITY}",
                "-H",
                f"Tags: {NTFY_TAGS}",
                "-X",
                "POST",
                "--data-binary",
                "@-",
                f"{NTFY_BASE_URL}/{topic}",
            ],
            input=body,
            capture_output=True,
            text=True,
            timeout=NTFY_CURL_MAX_TIME_SECONDS + 5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        detail = f"ntfy send failed (non-fatal): {exc}"
        logger.error(detail)
        return {"attempted": True, "sent": False, "detail": detail}

    if result.returncode == 0:
        logger.info("ntfy notification sent (status=%s)", status)
        return {"attempted": True, "sent": True, "detail": "ntfy notification sent"}

    detail = f"ntfy send failed (non-fatal): curl rc={result.returncode}"
    logger.error(detail)
    return {"attempted": True, "sent": False, "detail": detail}


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ran_at_utc = _utc_now_iso()

    if not HEALTH_CHECK_SCRIPT.is_file() or not os.access(HEALTH_CHECK_SCRIPT, os.X_OK):
        status = STATUS_SCRIPT_MISSING
        logger.error(
            "health-check script missing or non-executable: %s", HEALTH_CHECK_SCRIPT
        )
        body = _truncate(f"Health-check script not found or not executable: {HEALTH_CHECK_SCRIPT}")
        delivery: dict = send_ntfy_alert(status, body)
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
        delivery = send_ntfy_alert(status, body)
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
        delivery = send_ntfy_alert(status, body)

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
