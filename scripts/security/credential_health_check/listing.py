"""Terminal-friendly listing of credentials from the manifest.

Used by `python3 -m credential_health_check --list`. Read-only: never writes
to GitHub, Vikunja, or any external surface. Skips the orchestrator entirely.

See kitty-specs/credential-expiry-health-check-01KRCF92/ for the underlying
credential health-check design (this module is a small post-deploy addition).
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from typing import IO, Iterable, Optional

from .cadence import (
    WARNING_WINDOW_DAYS,
    compute_effective_boundary,
    is_fixed_interval_cadence,
)
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
    """Classify a credential's current state for the Status column.

    Keyed off the (effective) boundary first (#852): any credential with a
    boundary — cadence-driven or `expires_at`-driven — is classified by its
    days-to-boundary, so the --list view agrees with what the alerter fires on.
    Only when there is no boundary do we fall back to a cadence-type label.
    """
    if boundary is not None:
        delta = (boundary - today).days
        if delta < 0:
            return f"OVERDUE ({-delta}d ago)"
        if delta <= WARNING_WINDOW_DAYS:
            return f"WARNING ({delta}d)"
        return f"within ({delta}d)"
    # No boundary: classify by cadence type.
    if cred.review_cadence == "monitor-activity":
        return "activity-tracked"
    if is_fixed_interval_cadence(cred.review_cadence):
        return "skip (no anchor)"
    return f"skip ({cred.review_cadence})"


def build_listings(
    credentials: Iterable[Credential], today: date
) -> list[CredentialListing]:
    """Build CredentialListing entries from well-formed credentials."""
    rows: list[CredentialListing] = []
    for cred in credentials:
        boundary = compute_effective_boundary(cred)
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


@dataclass(frozen=True)
class LivenessListing:
    """One row in the --list --liveness table."""

    name: str
    enabled: str
    command: str
    dead_exit_codes: str
    recovery_command: str


def build_liveness_listings(
    credentials: Iterable[Credential],
) -> list[LivenessListing]:
    """Build LivenessListing entries for every credential that declares a
    liveness_probe block (any credential type — the probe is generic)."""
    rows: list[LivenessListing] = []
    for cred in credentials:
        lp = cred.liveness_probe
        if lp is None:
            continue

        rows.append(LivenessListing(
            name=cred.name,
            enabled="yes" if lp.enabled else "no",
            command=" ".join(lp.command) if lp.command else "—",
            dead_exit_codes=(
                ",".join(str(c) for c in lp.dead_exit_codes)
                if lp.dead_exit_codes else "—"
            ),
            recovery_command=lp.recovery_command or "—",
        ))
    return rows


def render_liveness_table(listings: list[LivenessListing]) -> str:
    """Render liveness listings as aligned plain text."""
    headers = [
        "Name", "Enabled", "command",
        "dead_exit_codes", "recovery_command",
    ]

    def _row(r: LivenessListing) -> list[str]:
        return [
            r.name, r.enabled, r.command,
            r.dead_exit_codes, r.recovery_command,
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
    When ``liveness`` is True, also prints the per-credential liveness_probe
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
            print("Liveness-probe state (read-only; run --dry-run --liveness-only for fresh classification):", file=stream)
            print(render_liveness_table(liveness_listings), file=stream)
        else:
            print("", file=stream)
            print("No credentials with a liveness_probe configuration found.", file=stream)
    return 0
