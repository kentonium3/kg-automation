"""Vikunja task writer for cadence-based credential alerts.

See kitty-specs/credential-expiry-health-check-01KRCF92/contracts/vikunja-task-writer.md
for the authoritative contract.

HTTP conventions (WP06, mission retire-vikunja-felix-bot-01KY829X, #860)
-------------------------------------------------------------------------
This module used to hand-roll its own ``urllib``-based request helper. It
now issues its single write (task create) through the shared
:class:`~scripts.common.vikunja_client.VikunjaClient` (``create_task_in_project``,
the same ``PUT /projects/{id}/tasks`` verb this module always used). This is
Phase 1 (behavior-preserving consolidation) — the module's public contract
(``VikunjaWriteError``, ``load_token``, ``create_task``) is unchanged;
:func:`_adapt_vikunja_error` translates the client's typed exceptions into
this module's pre-existing :class:`VikunjaWriteError` with an equivalent
message, per the "Return/error semantics" note in the ``vikunja_client``
module docstring.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

from scripts.common import vikunja_refs
from scripts.common.vikunja_client import VikunjaClient
from scripts.common.vikunja_client import VikunjaError as _ClientVikunjaError
from scripts.common.vikunja_config import (
    VikunjaConfigError,
    get_vikunja_base_url,
    get_vikunja_token_path,
)
from .manifest import Credential


#: Sentinel; resolved at call-time via get_vikunja_base_url().
VIKUNJA_API_BASE: str = ""
#: The token path is resolved at call-time via get_vikunja_token_path() (the
#: single config seam, WP01 / FR-001) — the felix-bot ``vikunja-api`` literal
#: deliberately no longer lives in this runtime surface (SC-001).
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


def load_token(path: Optional[Path] = None) -> str:
    """Read the vikunja-api bearer token from disk. Never log this value.

    When ``path`` is omitted the token path is resolved through the single
    config seam (:func:`get_vikunja_token_path` — its ``VIKUNJA_TOKEN_PATH``
    override or the kent-owned module default), so the credential-health writer
    follows the same one-lever runtime identity as every other consumer
    (FR-001). An explicit ``path`` (used by tests) bypasses the seam. A seam
    resolution failure fails loud as :class:`VikunjaConfigError`; it is adapted
    into this module's pre-existing :class:`VikunjaWriteError` contract, and the
    token value is never logged (redaction preserved).
    """
    if path is None:
        try:
            path = get_vikunja_token_path()
        except VikunjaConfigError as e:
            raise VikunjaWriteError(
                f"Could not resolve vikunja-api token path: {e}"
            ) from e
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError as e:
        raise VikunjaWriteError(f"Could not read vikunja-api token at {path}: {e}") from e


def _adapt_vikunja_error(
    method: str, url: str, exc: _ClientVikunjaError
) -> VikunjaWriteError:
    """Translate a ``VikunjaClient`` exception into this module's ``VikunjaWriteError``.

    Preserves the pre-migration message shape (``"Vikunja {method} {url}
    failed: HTTP {code} — {body}"`` for HTTP-status failures; a network/
    timeout-flavored message otherwise) using the client's typed
    ``exc.status``/``exc.body`` rather than raw ``urllib`` exception text —
    see the ``vikunja_client`` module docstring "Return/error semantics".
    """
    if exc.status is not None:
        body = (exc.body or "")[:200]
        return VikunjaWriteError(
            f"Vikunja {method} {url} failed: HTTP {exc.status} — {body}"
        )
    return VikunjaWriteError(
        f"Vikunja {method} {url} network error: {exc.verbose_message()}"
    )


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
    across credentials in a single cycle. When ``inbox_project_id`` is not
    supplied it is resolved through the reference seam
    (``vikunja_refs.project_id("inbox")`` → registry, network-free, targets
    Inbox id 1); a deleted/unprovisioned "inbox" ref fails loud with
    :class:`~scripts.common.vikunja_refs.VikunjaRefError` (#748/#745).
    """
    if token is None:
        token = load_token()
    if inbox_project_id is None:
        inbox_project_id = vikunja_refs.project_id("inbox")
    payload = {
        "title": task_title(credential),
        "description": task_description(credential, boundary, github_issue_number),
        "due_date": render_due_date_iso(due_date_for_boundary(boundary)),
    }
    url = f"{get_vikunja_base_url()}projects/{inbox_project_id}/tasks"
    try:
        client = VikunjaClient(base_url=get_vikunja_base_url(), token=token, timeout=15)
        body = client.create_task_in_project(inbox_project_id, payload)
    except (_ClientVikunjaError, ValueError) as exc:
        if isinstance(exc, _ClientVikunjaError):
            raise _adapt_vikunja_error("PUT", url, exc) from exc
        raise VikunjaWriteError(f"Vikunja {url} client configuration error: {exc}") from exc
    if not isinstance(body, dict) or "id" not in body:
        raise VikunjaWriteError(
            f"Vikunja task create response missing 'id': {str(body)[:200]}"
        )
    return int(body["id"])
