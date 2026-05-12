"""GitHub issue writer + dedup for credential health alerts.

See kitty-specs/credential-expiry-health-check-01KRCF92/contracts/github-issue-writer.md
for the authoritative contract.
"""
from __future__ import annotations

import json
import subprocess
from datetime import date
from typing import Optional

from .manifest import Credential, ManifestQualityIssue
from .signals import ActivitySignalFailure


REPO = "kentonium3/kg-automation"
DEFAULT_LABELS = ("area/security",)
DEFAULT_ASSIGNEES = ("kentonium3",)


class GitHubWriteError(Exception):
    """The check could not file the requested artefact on GitHub."""


# ---------- Title helpers ----------


def cadence_alert_title(credential: Credential, boundary: date) -> str:
    return f"Credential review: {credential.name} due {boundary.isoformat()}"


def cadence_alert_title_prefix(credential: Credential) -> str:
    """Prefix used for dedup; intentionally drops the boundary date."""
    return f"Credential review: {credential.name}"


def staleness_alert_title(credential: Credential) -> str:
    return f"Credential staleness: {credential.name}"


def staleness_alert_title_prefix(credential: Credential) -> str:
    return f"Credential staleness: {credential.name}"


def manifest_quality_title(issue_count: int, cycle_date: date) -> str:
    return (
        f"Credential manifest quality: {issue_count} entries with issues — "
        f"{cycle_date.isoformat()}"
    )


MANIFEST_QUALITY_TITLE_PREFIX = "Credential manifest quality"


# ---------- Body helpers ----------


def _used_by_str(credential: Credential) -> str:
    return ", ".join(credential.used_by) if credential.used_by else "—"


def cadence_alert_body(
    credential: Credential,
    boundary: date,
    vikunja_task_id: int,
    cycle_date: date,
) -> str:
    days_remaining = (boundary - cycle_date).days
    return (
        f"**Credential**: `{credential.name}` (`{credential.type or 'unspecified'}`)\n"
        f"**Scope**: {credential.scope or '—'}\n"
        f"**Stored at**: `{credential.storage}`\n"
        f"**Used by**: {_used_by_str(credential)}\n\n"
        f"**Review cadence**: `{credential.review_cadence}` — last reviewed "
        f"**{credential.last_reviewed.isoformat() if credential.last_reviewed else '—'}**\n"
        f"**Cadence boundary**: **{boundary.isoformat()}** (in {days_remaining} days)\n"
        f"**Vikunja task**: #{vikunja_task_id} (due {(boundary - _timedelta_days(7)).isoformat()})\n\n"
        "---\n\n"
        "### Rotation procedure\n\n"
        f"{credential.expiry_notes}\n\n"
        "---\n\n"
        f"*Filed by `credential-health-check.service` on office2 on "
        f"{cycle_date.isoformat()}. Filed via `kg-felix-bot`.*\n\n"
        "*Close this issue after rotating + updating `last_reviewed` in "
        "`docs/design/architecture/data/credential-manifest.json`.*\n"
    )


def _timedelta_days(n: int):
    # Local import keeps the module dependency surface minimal.
    from datetime import timedelta
    return timedelta(days=n)


def staleness_alert_body(
    credential: Credential,
    signal_failure: ActivitySignalFailure,
    cycle_date: date,
) -> str:
    return (
        f"**Credential**: `{credential.name}` (`{credential.type or 'unspecified'}`)\n"
        f"**Scope**: {credential.scope or '—'}\n"
        f"**Stored at**: `{credential.storage}`\n"
        f"**Used by**: {_used_by_str(credential)}\n\n"
        f"**Review cadence**: `{credential.review_cadence}`\n\n"
        "---\n\n"
        "### Signal that triggered this alert\n\n"
        f"{signal_failure.reason}\n\n"
        "---\n\n"
        "### What to do\n\n"
        f"{credential.expiry_notes}\n\n"
        "---\n\n"
        f"*Filed by `credential-health-check.service` on office2 on "
        f"{cycle_date.isoformat()}. No Vikunja task is created for activity-staleness "
        "alerts (one-way notification).*\n\n"
        "*Close this issue after acting on it.*\n"
    )


def manifest_quality_body(
    issues: list[ManifestQualityIssue],
    cycle_date: date,
) -> str:
    rows = "\n".join(
        f"| `{issue.credential_name}` | {issue.reason} |" for issue in issues
    )
    return (
        f"The credential-health-check cycle on {cycle_date.isoformat()} found "
        f"{len(issues)} entries in `credential-manifest.json` with field-quality "
        "issues. These entries were skipped for cadence-based processing.\n\n"
        "| Entry | Issue |\n"
        "|---|---|\n"
        f"{rows}\n\n"
        "Fix these entries and bump `last_updated` in `credential-manifest.json`.\n\n"
        "*Filed by `credential-health-check.service` on office2.*\n"
    )


# ---------- gh CLI wrappers ----------


def dedup_check(title_prefix: str) -> list[int]:
    """Return list of open issue numbers whose title starts with the prefix.

    Empty list means no dedup match. Raises GitHubWriteError on `gh` failure.
    """
    try:
        result = subprocess.run(
            [
                "gh",
                "issue",
                "list",
                "--repo",
                REPO,
                "--search",
                f'in:title "{title_prefix}"',
                "--state",
                "open",
                "--json",
                "number,title",
                "--limit",
                "50",
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except subprocess.TimeoutExpired as e:
        raise GitHubWriteError(f"gh issue list timed out: {e}") from e
    except FileNotFoundError as e:
        raise GitHubWriteError("gh binary not found on PATH") from e
    if result.returncode != 0:
        raise GitHubWriteError(
            f"gh issue list failed (exit {result.returncode}): "
            f"{result.stderr.strip()[:200]}"
        )
    try:
        data = json.loads(result.stdout) if result.stdout.strip() else []
    except json.JSONDecodeError as e:
        raise GitHubWriteError(f"gh issue list returned non-JSON: {e}") from e
    # `in:title` search is fuzzy; filter to true prefix matches.
    return [item["number"] for item in data if item.get("title", "").startswith(title_prefix)]


def create_issue(
    title: str,
    body: str,
    labels: tuple[str, ...] = DEFAULT_LABELS,
    assignees: tuple[str, ...] = DEFAULT_ASSIGNEES,
) -> int:
    """File a GitHub issue and return the new issue number."""
    cmd: list[str] = [
        "gh",
        "issue",
        "create",
        "--repo",
        REPO,
        "--title",
        title,
        "--body",
        body,
    ]
    for label in labels:
        cmd += ["--label", label]
    for assignee in assignees:
        cmd += ["--assignee", assignee]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except subprocess.TimeoutExpired as e:
        raise GitHubWriteError(f"gh issue create timed out: {e}") from e
    except FileNotFoundError as e:
        raise GitHubWriteError("gh binary not found on PATH") from e
    if result.returncode != 0:
        raise GitHubWriteError(
            f"gh issue create failed (exit {result.returncode}): "
            f"{result.stderr.strip()[:200]}"
        )
    url = result.stdout.strip()
    # Expected: https://github.com/kentonium3/kg-automation/issues/<N>
    try:
        return int(url.rsplit("/", 1)[-1])
    except (ValueError, IndexError) as e:
        raise GitHubWriteError(
            f"gh issue create stdout was not a parseable URL: {url!r}"
        ) from e
