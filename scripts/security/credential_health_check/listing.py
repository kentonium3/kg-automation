"""Terminal-friendly listing of credentials from the manifest.

Used by `python3 -m credential_health_check --list`. Read-only: never writes
to GitHub, Vikunja, or any external surface. Skips the orchestrator entirely.

See kitty-specs/credential-expiry-health-check-01KRCF92/ for the underlying
credential health-check design (this module is a small post-deploy addition).
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import IO, Iterable, Optional

from .cadence import WARNING_WINDOW_DAYS, compute_boundary, is_fixed_interval_cadence
from .manifest import Credential, ManifestQualityIssue, read_manifest


@dataclass(frozen=True)
class CredentialListing:
    """One row in the --list table."""

    name: str
    type: str
    review_cadence: str
    last_reviewed: Optional[date]
    boundary: Optional[date]
    status: str


def _status_for(cred: Credential, boundary: Optional[date], today: date) -> str:
    """Classify a credential's current state for the Status column."""
    if not is_fixed_interval_cadence(cred.review_cadence):
        if cred.review_cadence == "monitor-activity":
            return "activity-tracked"
        return f"skip ({cred.review_cadence})"
    if boundary is None:
        return "skip (no anchor)"
    delta = (boundary - today).days
    if delta < 0:
        return f"OVERDUE ({-delta}d ago)"
    if delta <= WARNING_WINDOW_DAYS:
        return f"WARNING ({delta}d)"
    return f"within ({delta}d)"


def build_listings(
    credentials: Iterable[Credential], today: date
) -> list[CredentialListing]:
    """Build CredentialListing entries from well-formed credentials."""
    rows: list[CredentialListing] = []
    for cred in credentials:
        boundary = compute_boundary(cred)
        rows.append(
            CredentialListing(
                name=cred.name,
                type=cred.type or "—",
                review_cadence=cred.review_cadence,
                last_reviewed=cred.last_reviewed,
                boundary=boundary,
                status=_status_for(cred, boundary, today),
            )
        )
    return rows


def render_table(listings: list[CredentialListing]) -> str:
    """Render as aligned plain text (no ANSI/color)."""
    headers = ["Name", "Type", "Cadence", "Last reviewed", "Boundary", "Status"]

    def _row(row: CredentialListing) -> list[str]:
        return [
            row.name,
            row.type,
            row.review_cadence,
            row.last_reviewed.isoformat() if row.last_reviewed else "—",
            row.boundary.isoformat() if row.boundary else "—",
            row.status,
        ]

    data_rows = [_row(r) for r in listings]
    widths = [
        max(len(headers[i]), max((len(r[i]) for r in data_rows), default=0))
        for i in range(len(headers))
    ]

    lines: list[str] = []
    lines.append("  ".join(h.ljust(widths[i]) for i, h in enumerate(headers)))
    lines.append("  ".join("-" * widths[i] for i in range(len(headers))))
    for r in data_rows:
        lines.append("  ".join(r[i].ljust(widths[i]) for i in range(len(headers))))
    return "\n".join(lines)


def render_malformed(malformed: list[ManifestQualityIssue]) -> str:
    """Render the malformed-entries footer (returns empty string if none)."""
    if not malformed:
        return ""
    lines = ["", f"WARNING: {len(malformed)} malformed entries skipped:"]
    for issue in malformed:
        lines.append(f"  - {issue.credential_name}: {issue.reason}")
    return "\n".join(lines)


def _format_age(seconds: float) -> str:
    """Format a duration in seconds as 'Xd Yh'."""
    total_hours = int(seconds // 3600)
    days = total_hours // 24
    hours = total_hours % 24
    return f"{days}d {hours}h"


@dataclass(frozen=True)
class LivenessListing:
    """One row in the --list --liveness table."""

    name: str
    enabled: str
    gog_account: str
    keyring_mtime_age: str
    recovery_command: str


def build_liveness_listings(
    credentials: Iterable[Credential],
) -> list[LivenessListing]:
    """Build LivenessListing entries for oauth2 credentials."""
    now = datetime.now(timezone.utc)
    rows: list[LivenessListing] = []
    for cred in credentials:
        if cred.type != "oauth2":
            continue
        lp = cred.liveness_probe
        if lp is None:
            rows.append(LivenessListing(
                name=cred.name,
                enabled="—",
                gog_account="—",
                keyring_mtime_age="—",
                recovery_command="—",
            ))
            continue

        enabled_str = "yes" if lp.enabled else "no"
        gog_account = lp.gog_account or "—"
        recovery_command = lp.recovery_command or "—"

        # Compute keyring mtime age.
        keyring_mtime_age = "—"
        if lp.keyring_file:
            keyring_path = Path(lp.keyring_file)
            try:
                mtime_ts = keyring_path.stat().st_mtime
                mtime = datetime.fromtimestamp(mtime_ts, tz=timezone.utc)
                age_seconds = (now - mtime).total_seconds()
                keyring_mtime_age = _format_age(age_seconds)
            except (FileNotFoundError, OSError):
                keyring_mtime_age = "—"

        rows.append(LivenessListing(
            name=cred.name,
            enabled=enabled_str,
            gog_account=gog_account,
            keyring_mtime_age=keyring_mtime_age,
            recovery_command=recovery_command,
        ))
    return rows


def render_liveness_table(listings: list[LivenessListing]) -> str:
    """Render liveness listings as aligned plain text."""
    headers = [
        "Name", "Enabled", "gog_account",
        "keyring_mtime_age", "recovery_command",
    ]

    def _row(r: LivenessListing) -> list[str]:
        return [
            r.name, r.enabled, r.gog_account,
            r.keyring_mtime_age, r.recovery_command,
        ]

    data_rows = [_row(r) for r in listings]
    widths = [
        max(len(headers[i]), max((len(r[i]) for r in data_rows), default=0))
        for i in range(len(headers))
    ]

    lines: list[str] = []
    lines.append("  ".join(h.ljust(widths[i]) for i, h in enumerate(headers)))
    lines.append("  ".join("-" * widths[i] for i in range(len(headers))))
    for r in data_rows:
        lines.append("  ".join(r[i].ljust(widths[i]) for i in range(len(headers))))
    return "\n".join(lines)


def list_credentials(
    manifest_path: str,
    today: date,
    *,
    stream: IO[str],
    liveness: bool = False,
) -> int:
    """Read the manifest and write the table to stream.

    Returns 0 on success, propagates ManifestUnreadableError to the caller.
    When ``liveness`` is True, also prints the per-oauth2-credential liveness
    summary table (read-only; no probes issued).
    """
    well_formed, malformed = read_manifest(manifest_path)
    listings = build_listings(well_formed, today)
    print(render_table(listings), file=stream)
    footer = render_malformed(malformed)
    if footer:
        print(footer, file=stream)
    if liveness:
        liveness_listings = build_liveness_listings(well_formed)
        if liveness_listings:
            print("", file=stream)
            print("OAuth2 liveness state (read-only; run --dry-run --liveness-only for fresh classification):", file=stream)
            print(render_liveness_table(liveness_listings), file=stream)
        else:
            print("", file=stream)
            print("No oauth2 credentials with liveness_probe configuration found.", file=stream)
    return 0
