"""Off-host dead-man pings for the on-host watchers (#1077, RFC #1069).

felix-canary and felix-health-check watch each other (#1063) but share one
host, one ``claude`` user manager, one checkout and one ntfy alert topic, so
losing any of those silences both. Each therefore pings its own hosted
healthchecks.io check after it runs; the service emails Kent when pings stop
or a ``/fail`` ping arrives -- never through ntfy.

Two calls, both total (they never raise) and bounded:

* :func:`ping` sends one ``success`` or ``fail`` ping. The ping URL is a
  capability secret: it is read only from :data:`ENV_FILE` into a private
  mapping, never placed in ``os.environ``, never in a child's argv or
  environment (it reaches curl on stdin via ``-K -``), and never logged.
* :func:`channel_ok` judges, freshly every run and with no persisted state,
  whether the felix-alert channel could deliver: the topic is configured, a
  read-only ntfy health probe answers healthy, and this run's own deliveries
  succeeded. The probe runs in the SAME transport context as real alert
  delivery (inherited environment, curl's default config), so a broken proxy
  cannot pass the probe while delivery fails (post-plan Codex round 4).

Operator test (prints no URL)::

    python3 -m scripts.common.deadman --label canary --outcome fail
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.parse import urlsplit, urlunsplit

#: Fixed path, never derived from $HOME (engineering principle 15); the same
#: convention as scripts/common/alert_bus.sh. Mode 0600, claude-owned.
ENV_FILE = Path("/home/claude/.config/felix/deadman/env")
#: Test-only override naming a different FILE PATH (never a URL).
ENV_FILE_OVERRIDE_VAR = "FELIX_DEADMAN_ENV_FILE"

LABEL_VARS: dict[str, str] = {
    "canary": "FELIX_DEADMAN_CANARY_URL",
    "healthcheck": "FELIX_DEADMAN_HEALTHCHECK_URL",
}
OUTCOMES = ("success", "fail")

MAX_URL_LENGTH = 512
#: healthchecks.io action suffixes; a configured base ending in one of these
#: would invert or corrupt the outcome when "/fail" is appended.
_ACTION_SEGMENTS = frozenset({"fail", "start", "log"})

#: Hardened ping transport. ``-q`` MUST be first (it only works as the first
#: argument) so ~/.curlrc and $CURL_HOME/.curlrc are ignored; the URL arrives
#: on stdin through ``-K -``.
PING_ARGV: tuple[str, ...] = (
    "curl", "-q", "--silent", "--show-error", "--fail", "--globoff",
    "--proto", "=https", "--proto-redir", "=https", "--max-redirs", "0",
    "--max-time", "5", "--retry", "0", "--output", "/dev/null", "-K", "-",
)
#: The only environment the ping's curl sees: no HOME, no proxy variables.
PING_ENV: dict[str, str] = {"PATH": "/usr/bin:/bin", "LANG": "C"}

SUBPROCESS_TIMEOUT_SECONDS = 8
MAX_ATTEMPTS = 2
RETRY_DELAY_SECONDS = 2

#: Mirrors scripts/common/alert_bus/delivery.py.
NTFY_TOPIC_VAR = "FELIX_ALERT_NTFY_TOPIC"
NTFY_BASE_URL_VAR = "FELIX_ALERT_NTFY_BASE_URL"
NTFY_DEFAULT_BASE_URL = "https://ntfy.sh"

Runner = Callable[..., Any]
Sleeper = Callable[[float], None]


@dataclass(frozen=True)
class PingResult:
    sent: bool
    reason: str


def _log(message: str) -> None:
    try:
        print(message, file=sys.stderr)
    except Exception:  # noqa: BLE001 -- logging must never break a watcher
        pass


def _load(path: Path) -> dict[str, str]:
    """Read the two ping-URL keys from ``path``. Never raises; never touches os.environ."""
    wanted = set(LABEL_VARS.values())
    found: dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:  # noqa: BLE001 -- missing/unreadable == unconfigured
        return found
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if key not in wanted:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        found[key] = value
    return found


def _env_file(env_file: Path | str | None) -> Path:
    if env_file is not None:
        return Path(env_file)
    override = os.environ.get(ENV_FILE_OVERRIDE_VAR, "").strip()
    return Path(override) if override else ENV_FILE


def _canonical(url: str) -> tuple[str, str] | None:
    """Return ``(success_url, fail_url)`` for a canonical ping URL, else None."""
    if not isinstance(url, str) or not url or len(url) > MAX_URL_LENGTH:
        return None
    # ASCII only: an IDN would otherwise fail later at stdin encoding (WP01
    # review). '%' is rejected so no encoded form (e.g. %66ail) can reach an
    # action endpoint after the server decodes it.
    if not url.isascii():
        return None
    if any(ch.isspace() or ord(ch) < 0x20 or ord(ch) == 0x7F or ch in '"\\%' for ch in url):
        return None
    try:
        parts = urlsplit(url)
        parts.port  # noqa: B018 -- raises ValueError on a malformed port
    except ValueError:
        return None
    if parts.scheme != "https" or not parts.hostname:
        return None
    if parts.query or parts.fragment or "@" in parts.netloc:
        return None
    path = parts.path[:-1] if parts.path.endswith("/") else parts.path
    # Every segment after the leading "/" must be a plain name: no empty
    # segments ("//"), no "." or ".." (curl would normalise them to a path we
    # never validated), so the final segment checked below is the one curl
    # actually requests (WP01 review: "/u/fail//" inverted a success ping).
    segments = path.split("/")[1:] if path else []
    if any(seg in ("", ".", "..") for seg in segments):
        return None
    last = segments[-1].lower() if segments else ""
    if last in _ACTION_SEGMENTS or (last and last.isdigit()):
        return None
    success = urlunsplit((parts.scheme, parts.netloc, path, "", ""))
    fail = urlunsplit((parts.scheme, parts.netloc, path + "/fail", "", ""))
    return success, fail


def _reason_for_exit(code: int) -> str:
    if code == 0:
        return "ok"
    if code == 22:
        return "http_error"
    if code == 28:
        return "timeout"
    if code in (6, 7):
        return "unreachable"
    return f"curl_exit:{code}"


def _send_once(url: str, run: Runner) -> str:
    try:
        proc = run(
            list(PING_ARGV),
            input=f'url = "{url}"\n',
            capture_output=True,  # discarded: curl's stderr may echo the URL
            text=True,
            env=dict(PING_ENV),
            timeout=SUBPROCESS_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return "timeout"
    except FileNotFoundError:
        return "curl_missing"
    except Exception as exc:  # noqa: BLE001 -- total
        return f"error:{exc.__class__.__name__}"
    return _reason_for_exit(getattr(proc, "returncode", -1))


def ping(
    label: str,
    outcome: str,
    *,
    env_file: Path | str | None = None,
    run: Runner | None = None,
    sleep: Sleeper | None = None,
) -> PingResult:
    """Send one dead-man ping for ``label``. Never raises; never logs the URL."""
    # Resolved at call time, not definition time, so the seams stay patchable.
    run = run or subprocess.run
    sleep = sleep or time.sleep
    try:
        if label not in LABEL_VARS or outcome not in OUTCOMES:
            result = PingResult(False, "invalid")
        else:
            url = _load(_env_file(env_file)).get(LABEL_VARS[label], "")
            if not url:
                result = PingResult(False, "unconfigured")
            else:
                endpoints = _canonical(url)
                if endpoints is None:
                    result = PingResult(False, "invalid")
                else:
                    target = endpoints[0] if outcome == "success" else endpoints[1]
                    reason = "error:unknown"
                    for attempt in range(MAX_ATTEMPTS):
                        if attempt:
                            sleep(RETRY_DELAY_SECONDS)
                        reason = _send_once(target, run)
                        if reason == "ok":
                            break
                    result = PingResult(reason == "ok", reason)
    except Exception as exc:  # noqa: BLE001 -- total
        result = PingResult(False, f"error:{exc.__class__.__name__}")
    _log(f"deadman {label} {outcome}: {result.reason}")
    return result


def _probe_ntfy(env: Mapping[str, str], run: Runner, sleep: Sleeper) -> str:
    base = (env.get(NTFY_BASE_URL_VAR, "") or "").strip() or NTFY_DEFAULT_BASE_URL
    url = base.rstrip("/") + "/v1/health"
    reason = "probe_error"
    for attempt in range(MAX_ATTEMPTS):
        if attempt:
            sleep(RETRY_DELAY_SECONDS)
        try:
            # Same transport context as alert_bus/delivery.py: inherited
            # environment, and NO -q, so curl's default config and any proxy
            # variables apply exactly as they do for real delivery.
            proc = run(
                ["curl", "--silent", "--show-error", "--max-time", "5", url],
                capture_output=True,
                text=True,
                env=dict(env),
                timeout=SUBPROCESS_TIMEOUT_SECONDS,
                check=False,
            )
        except Exception:  # noqa: BLE001 -- includes TimeoutExpired / missing curl
            reason = "probe_error"
            continue
        if getattr(proc, "returncode", -1) != 0:
            reason = "probe_error"
            continue
        try:
            body = json.loads(getattr(proc, "stdout", "") or "")
        except (ValueError, TypeError):
            reason = "probe_error"
            continue
        if isinstance(body, dict) and body.get("healthy") is True:
            return "ok"
        reason = "ntfy_unhealthy"
    return reason


def channel_ok(
    env: Mapping[str, str],
    delivered_ok: bool,
    *,
    run: Runner | None = None,
    sleep: Sleeper | None = None,
) -> tuple[bool, str]:
    """Could the felix-alert channel deliver, judged freshly this run? Never raises."""
    run = run or subprocess.run
    sleep = sleep or time.sleep
    try:
        if not (env.get(NTFY_TOPIC_VAR, "") or "").strip():
            return False, "topic_missing"
        probe = _probe_ntfy(env, run, sleep)
        if probe != "ok":
            return False, probe
        if not delivered_ok:
            return False, "undelivered"
        return True, "ok"
    except Exception as exc:  # noqa: BLE001 -- total; fail closed
        return False, f"error:{exc.__class__.__name__}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python3 -m scripts.common.deadman",
        description="Send one dead-man ping (operator test). Prints no URL.",
    )
    parser.add_argument("--label", required=True, choices=sorted(LABEL_VARS))
    parser.add_argument("--outcome", required=True, choices=OUTCOMES)
    args = parser.parse_args(argv)
    result = ping(args.label, args.outcome)
    print(f"sent={result.sent} reason={result.reason}")
    return 0 if result.sent else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
