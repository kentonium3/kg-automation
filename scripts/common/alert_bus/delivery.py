"""ntfy delivery, topic resolution, and the fail-safe contract.

Resolves the single canonical topic from ``FELIX_ALERT_NTFY_TOPIC``, POSTs to
ntfy via ``curl`` (no new dependency — every existing emitter already uses
curl), and guarantees best-effort delivery: :func:`deliver` **never raises**,
never hangs beyond the curl timeout, and returns a structured
:class:`AlertResult`. No auth header — ntfy topics are public-subscribe and
security is topic secrecy (FR-005).
"""

from __future__ import annotations

import os
import subprocess

from .model import Alert, AlertResult, SEVERITY_MAP
from .render import render_body, render_title

# Base URL is a module constant (default matches existing emitters), overridable
# via env for tests so they never touch the real endpoint.
_DEFAULT_BASE_URL = "https://ntfy.sh"

# Wall-clock ceiling for the whole subprocess call; a hair over curl's own
# --max-time so a hung curl is still reaped by subprocess.
_CURL_MAX_TIME = 10
_SUBPROCESS_TIMEOUT = 15


def base_url() -> str:
    """Return the ntfy base URL (env ``FELIX_ALERT_NTFY_BASE_URL`` overrides)."""
    return os.environ.get("FELIX_ALERT_NTFY_BASE_URL", "").strip() or _DEFAULT_BASE_URL


def resolve_topic() -> str:
    """Return the configured ntfy topic (stripped); blank when unset."""
    return os.environ.get("FELIX_ALERT_NTFY_TOPIC", "").strip()


def _curl_argv(url: str, title: str, priority: str, tags: str) -> list[str]:
    return [
        "curl",
        "--silent",
        "--show-error",
        "--fail",
        "--max-time",
        str(_CURL_MAX_TIME),
        "--data-binary",
        "@-",
        "-H",
        f"Title: {title}",
        "-H",
        f"Priority: {priority}",
        "-H",
        f"Tags: {tags}",
        url,
    ]


def deliver(alert: Alert) -> AlertResult:
    """POST *alert* to ntfy; never raise.

    Blank topic → :class:`AlertResult` ``(ok=False, reason="NTFY_MISSING_TOPIC",
    topic_configured=False)`` with no POST attempted. Otherwise curl the
    rendered body to ``<base_url>/<topic>`` with the mapped Priority/Tags
    headers. curl failures map to a reason code; ``TimeoutExpired`` and
    ``OSError`` are caught and returned as results.
    """
    topic = resolve_topic()
    if not topic:
        return AlertResult(
            ok=False,
            reason="NTFY_MISSING_TOPIC",
            topic_configured=False,
        )

    priority, tags = SEVERITY_MAP[alert.severity]
    title = render_title(alert)
    body = render_body(alert)
    url = f"{base_url()}/{topic}"
    argv = _curl_argv(url, title, priority, tags)

    try:
        proc = subprocess.run(
            argv,
            input=body,
            text=True,
            capture_output=True,
            timeout=_SUBPROCESS_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return AlertResult(ok=False, reason="CURL_TIMEOUT", topic_configured=True)
    except OSError as exc:
        return AlertResult(
            ok=False,
            reason=f"CURL_EXEC_ERROR:{exc.__class__.__name__}",
            topic_configured=True,
        )

    if proc.returncode == 0:
        return AlertResult(ok=True, reason=None, topic_configured=True)

    return AlertResult(
        ok=False,
        reason=_reason_for_returncode(proc.returncode),
        topic_configured=True,
    )


def _reason_for_returncode(returncode: int) -> str:
    """Map a curl exit code to a stable reason string.

    curl exit codes: 6 = couldn't resolve host, 7 = couldn't connect,
    22 = HTTP error (from ``--fail``), 28 = operation timeout. Anything else
    is reported with its numeric code so the reason is always actionable.
    """
    mapping = {
        6: "CURL_CONNECT",
        7: "CURL_CONNECT",
        22: "CURL_HTTP",
        28: "CURL_TIMEOUT",
    }
    return mapping.get(returncode, f"CURL_ERROR:{returncode}")


__all__ = ["resolve_topic", "deliver", "base_url"]
