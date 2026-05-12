"""Activity signal readers for monitor-activity credentials.

Each reader queries an external tool and returns either None (signal healthy)
or an ActivitySignalFailure (alert should fire). See
kitty-specs/credential-expiry-health-check-01KRCF92/contracts/activity-signal-readers.md
for the authoritative contract.
"""
from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from datetime import timedelta
from typing import Callable, Optional

from .manifest import Credential


@dataclass(frozen=True)
class ActivitySignalFailure:
    """Returned by a signal reader when an alert should fire."""

    credential_name: str
    reason: str   # Human-readable; used in issue body.
    summary: str  # Short; used in log lines.


SignalReader = Callable[[Credential], Optional[ActivitySignalFailure]]


# ---------- Duration parser (used by whatsapp_session_signal) ----------

_DURATION_PATTERN = re.compile(
    r"^\s*(?:(\d+)w)?\s*(?:(\d+)d)?\s*(?:(\d+)h)?\s*(?:(\d+)m)?\s*(?:(\d+)s)?\s*$"
)


def parse_duration(s: str) -> Optional[timedelta]:
    """Parse '38m', '2h 14m', '3d 5h', '2w', '38m ago' into timedelta.

    Strips a trailing 'ago' if present. Returns None on parse failure or
    a fully-empty match (e.g. 'bogus' or empty string).
    """
    s = s.strip()
    if s.endswith("ago"):
        s = s[:-3].strip()
    if not s:
        return None
    m = _DURATION_PATTERN.match(s)
    if not m or not any(m.groups()):
        return None
    weeks, days, hours, minutes, seconds = (int(x) if x else 0 for x in m.groups())
    return timedelta(
        weeks=weeks, days=days, hours=hours, minutes=minutes, seconds=seconds
    )


# ---------- Tailscale ----------


def tailscale_auth_signal(credential: Credential) -> Optional[ActivitySignalFailure]:
    """Detect 'Tailscale backend not Running'."""
    try:
        result = subprocess.run(
            ["tailscale", "status", "--json"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except subprocess.TimeoutExpired:
        return ActivitySignalFailure(
            credential_name=credential.name,
            reason="`tailscale status --json` timed out after 5 seconds.",
            summary="tailscale: command timeout",
        )
    except FileNotFoundError:
        return ActivitySignalFailure(
            credential_name=credential.name,
            reason="`tailscale` binary not found on PATH.",
            summary="tailscale: binary missing",
        )
    if result.returncode != 0:
        return ActivitySignalFailure(
            credential_name=credential.name,
            reason=(
                f"`tailscale status --json` exited {result.returncode}: "
                f"{result.stderr.strip()[:200]}"
            ),
            summary=f"tailscale: exit {result.returncode}",
        )
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        return ActivitySignalFailure(
            credential_name=credential.name,
            reason=f"`tailscale status --json` output was not valid JSON: {e}",
            summary="tailscale: malformed JSON",
        )
    backend_state = data.get("BackendState", "<missing>")
    if backend_state != "Running":
        return ActivitySignalFailure(
            credential_name=credential.name,
            reason=(
                f"Tailscale BackendState is `{backend_state}`, expected `Running`. "
                "Inspect with: tailscale status"
            ),
            summary=f"tailscale: BackendState={backend_state}",
        )
    return None


# ---------- WhatsApp ----------

WHATSAPP_STALENESS_THRESHOLD = timedelta(days=14)


def whatsapp_session_signal(
    credential: Credential,
) -> Optional[ActivitySignalFailure]:
    """Detect not-connected or stale WhatsApp session."""
    try:
        result = subprocess.run(
            ["openclaw", "channels", "status"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except subprocess.TimeoutExpired:
        return ActivitySignalFailure(
            credential_name=credential.name,
            reason="`openclaw channels status` timed out after 10 seconds.",
            summary="whatsapp: command timeout",
        )
    except FileNotFoundError:
        return ActivitySignalFailure(
            credential_name=credential.name,
            reason="`openclaw` binary not found on PATH.",
            summary="whatsapp: binary missing",
        )
    if result.returncode != 0:
        return ActivitySignalFailure(
            credential_name=credential.name,
            reason=(
                f"`openclaw channels status` exited {result.returncode}: "
                f"{result.stderr.strip()[:200]}"
            ),
            summary=f"whatsapp: exit {result.returncode}",
        )

    channel_line = next(
        (line for line in result.stdout.splitlines() if "WhatsApp default" in line),
        None,
    )
    if channel_line is None:
        return ActivitySignalFailure(
            credential_name=credential.name,
            reason=(
                "`openclaw channels status` did not include a 'WhatsApp default' "
                "channel line."
            ),
            summary="whatsapp: channel missing from status",
        )

    # Split on commas after the 'WhatsApp default:' prefix.
    # Expected shape: '- WhatsApp default: enabled, configured, linked, running, connected, in:38m ago, out:38m ago, dm:allowlist, allow:+...'
    parts = [p.strip() for p in channel_line.split(",")]
    # Drop the prefix piece(s) before/including the colon.
    flag_tokens = parts[0].split(":", 1)[-1].strip()
    parts[0] = flag_tokens

    flags = {p for p in parts if ":" not in p}

    for required_flag in ("linked", "running", "connected"):
        if required_flag not in flags:
            return ActivitySignalFailure(
                credential_name=credential.name,
                reason=(
                    f"WhatsApp default channel is `{required_flag}` flag is missing "
                    f"in `openclaw channels status` output. Full line: {channel_line!r}"
                ),
                summary=f"whatsapp: flag `{required_flag}` missing",
            )

    # Check in:/out: durations.
    for direction in ("in", "out"):
        prefix = f"{direction}:"
        token = next((p for p in parts if p.startswith(prefix)), None)
        if token is None:
            return ActivitySignalFailure(
                credential_name=credential.name,
                reason=(
                    f"WhatsApp default channel `{prefix}<duration>` token missing in "
                    f"openclaw status output. Full line: {channel_line!r}"
                ),
                summary=f"whatsapp: {prefix} token missing",
            )
        duration_str = token[len(prefix):].strip()
        duration = parse_duration(duration_str)
        if duration is None:
            return ActivitySignalFailure(
                credential_name=credential.name,
                reason=(
                    f"Could not parse WhatsApp default channel `{prefix}{duration_str}` "
                    f"as a duration. Full line: {channel_line!r}"
                ),
                summary=f"whatsapp: {prefix} unparseable",
            )
        if duration > WHATSAPP_STALENESS_THRESHOLD:
            return ActivitySignalFailure(
                credential_name=credential.name,
                reason=(
                    f"WhatsApp default channel last `{prefix.rstrip(':')}` activity "
                    f"was {duration_str} ago, exceeding the {WHATSAPP_STALENESS_THRESHOLD.days}-"
                    f"day session-expiry threshold (per whatsapp-session.expiry_notes)."
                ),
                summary=f"whatsapp: {prefix}{duration_str} (stale)",
            )

    return None


# ---------- Registry ----------

MONITOR_ACTIVITY_READERS: dict[str, SignalReader] = {
    "tailscale-auth": tailscale_auth_signal,
    "whatsapp-session": whatsapp_session_signal,
}
