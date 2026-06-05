"""Vikunja task writer for cadence-based credential alerts.

See kitty-specs/credential-expiry-health-check-01KRCF92/contracts/vikunja-task-writer.md
for the authoritative contract.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

from scripts.common.vikunja_config import get_vikunja_base_url
from .manifest import Credential


#: Sentinel; resolved at call-time via get_vikunja_base_url().
VIKUNJA_API_BASE: str = ""
VIKUNJA_TOKEN_PATH = Path("/data/services/openclaw/secrets/vikunja-api")
INBOX_PROJECT_TITLE = "Inbox"
DUE_DATE_TIMEZONE = "America/New_York"
DUE_DATE_DAYS_BEFORE_BOUNDARY = 7


class VikunjaWriteError(Exception):
    """The check could not file the requested artefact in Vikunja."""


# ---------- Pure helpers ----------


def task_title(credential: Credential) -> str:
    return f"Rotate credential: {credential.name}"


def task_description(
    credential: Credential, boundary: date, github_issue_number: int
) -> str:
    url = f"https://github.com/kentonium3/kg-automation/issues/{github_issue_number}"
    return (
        "Rotate this credential, then close the linked GitHub issue and mark this "
        "task done.\n\n"
        f"GitHub issue: {url}\n\n"
        f"Cadence boundary (the actual deadline): {boundary.isoformat()}\n"
        "This task is due one week earlier so the escalation engine pings before "
        "the boundary.\n\n"
        f"Stored at: {credential.storage}\n"
        "Rotation procedure (full text in the GitHub issue body): see expiry_notes "
        "in credential-manifest.json."
    )


def due_date_for_boundary(boundary: date) -> date:
    return boundary - timedelta(days=DUE_DATE_DAYS_BEFORE_BOUNDARY)


def render_due_date_iso(due: date) -> str:
    """Render due_date as ET end-of-day ISO-8601 (matches #112 timezone fix)."""
    et_eod = datetime(
        due.year, due.month, due.day, 23, 59, 59, tzinfo=ZoneInfo(DUE_DATE_TIMEZONE)
    )
    return et_eod.isoformat()


# ---------- Token + API ----------


def load_token(path: Path = VIKUNJA_TOKEN_PATH) -> str:
    """Read the vikunja-api bearer token from disk. Never log this value."""
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError as e:
        raise VikunjaWriteError(f"Could not read vikunja-api token at {path}: {e}") from e


def _request_json(
    method: str,
    url: str,
    token: str,
    payload: Optional[dict] = None,
    timeout: int = 15,
) -> dict | list:
    headers = {"Authorization": f"Bearer {token}"}
    data: Optional[bytes] = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
        return json.loads(body) if body else {}
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", "ignore") if hasattr(e, "read") else ""
        raise VikunjaWriteError(
            f"Vikunja {method} {url} failed: HTTP {e.code} — {err_body[:200]}"
        ) from e
    except urllib.error.URLError as e:
        raise VikunjaWriteError(f"Vikunja {method} {url} network error: {e}") from e
    except json.JSONDecodeError as e:
        raise VikunjaWriteError(f"Vikunja {method} {url} returned non-JSON: {e}") from e


def lookup_inbox_project_id(token: str) -> int:
    """Find the Inbox project by title. Returns the smallest matching ID if multiple."""
    projects = _request_json("GET", f"{get_vikunja_base_url()}projects", token, timeout=10)
    if not isinstance(projects, list):
        raise VikunjaWriteError(
            f"Vikunja /projects did not return a list (got {type(projects).__name__})"
        )
    matches = [p for p in projects if isinstance(p, dict) and p.get("title") == INBOX_PROJECT_TITLE]
    if not matches:
        raise VikunjaWriteError(
            f"Vikunja project titled {INBOX_PROJECT_TITLE!r} not found."
        )
    return min(int(p["id"]) for p in matches)


def create_task(
    credential: Credential,
    boundary: date,
    github_issue_number: int,
    *,
    token: Optional[str] = None,
    inbox_project_id: Optional[int] = None,
) -> int:
    """Create the Vikunja task and return its ID.

    Optional token/inbox_project_id allow the orchestrator to cache them
    across credentials in a single cycle.
    """
    if token is None:
        token = load_token()
    if inbox_project_id is None:
        inbox_project_id = lookup_inbox_project_id(token)
    payload = {
        "title": task_title(credential),
        "description": task_description(credential, boundary, github_issue_number),
        "due_date": render_due_date_iso(due_date_for_boundary(boundary)),
    }
    body = _request_json(
        "PUT",
        f"{get_vikunja_base_url()}projects/{inbox_project_id}/tasks",
        token,
        payload=payload,
        timeout=15,
    )
    if not isinstance(body, dict) or "id" not in body:
        raise VikunjaWriteError(
            f"Vikunja task create response missing 'id': {str(body)[:200]}"
        )
    return int(body["id"])
