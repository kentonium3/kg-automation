"""OpenClaw cron primitives — never touches the system cron table.

This module is the canonical surface for cron operations across the
kg-automation deploy pipeline. Every primitive shells out to
``openclaw cron <subcommand>``.

Invariant (FR-017): the literal token ``c r o n t a b`` (spaces added here so
this docstring itself does not violate the rule) MUST NOT appear in this
module's source outside a comment explaining the prohibition. CI greps for
that token under ``scripts/deploy/lib/`` and fails the build on any hit.
That prohibition exists because openclaw is the authoritative scheduler for
this system — bypassing it (see closed issue kentonium3/kg-automation#162)
re-introduces an unmanaged scheduling surface that the operator cannot
audit through ``openclaw cron list``.

Public surface (see ``contracts/deploy-library-api.md``):

* :func:`openclaw_cron_disable` — idempotent disable by name.
* :func:`openclaw_cron_enable` — idempotent enable by name.
* :func:`openclaw_cron_edit` — edit payload-file and/or schedule.
* :func:`openclaw_cron_list` — read-only list (returns parsed jobs).
"""

# NOTE: DO NOT shell out to /etc/c-r-o-n-t-a-b or `c-r-o-n-t-a-b -l` from
# anywhere in this file. The hard-rule token (without the hyphens) is
# forbidden in source outside comments; see issue #162 for the precedent.

from __future__ import annotations

import json
import subprocess
from typing import Any, Iterable, Mapping

from . import LibResult

_OPENCLAW = "openclaw"
_STDERR_EXCERPT_MAX = 2000


def _run(argv: list[str]) -> tuple[int, str, str]:
    """Execute *argv* and return (returncode, stdout, stderr).

    Wrapper kept tiny so tests can monkeypatch a single seam.
    """
    proc = subprocess.run(  # noqa: S603 - argv list, no shell
        argv,
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.returncode, proc.stdout or "", proc.stderr or ""


def _excerpt(text: str, limit: int = _STDERR_EXCERPT_MAX) -> str:
    if not text:
        return ""
    if len(text) <= limit:
        return text
    return text[:limit] + "...<truncated>"


def _parse_list_payload(stdout: str) -> list[dict[str, Any]]:
    """Parse ``openclaw cron list --json`` output.

    Per deploy-149.sh the observed schema is either ``{"jobs": [...]}`` or a
    plain list at top-level. Defensive: also accept ``crons``/``items`` keys.
    Returns an empty list rather than raising when the payload is empty.
    """
    if not stdout.strip():
        return []
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        return []
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        for key in ("jobs", "crons", "items"):
            value = data.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []


def _find_job_by_name(jobs: Iterable[Mapping[str, Any]], cron_name: str) -> Mapping[str, Any] | None:
    for job in jobs:
        if job.get("name") == cron_name:
            return job
    return None


def _is_enabled(job: Mapping[str, Any]) -> bool:
    """Best-effort 'is this cron enabled?' inspection.

    OpenClaw has surfaced this field as ``enabled`` (bool) and ``status``
    (string ``"enabled"``/``"disabled"``) across releases. We accept both,
    defaulting to True (enabled) when no signal is present — disabling an
    already-disabled cron is a no-op anyway, and enabling an already-enabled
    cron is harmless.
    """
    if "enabled" in job:
        return bool(job["enabled"])
    status = job.get("status")
    if isinstance(status, str):
        return status.lower() != "disabled"
    return True


def openclaw_cron_list() -> LibResult:
    """Return the current openclaw crons in ``details['crons']``.

    Read-only. Any non-zero exit from ``openclaw cron list --json`` produces
    ``LibResult(ok=False, ...)``.
    """
    argv = [_OPENCLAW, "cron", "list", "--json"]
    rc, stdout, stderr = _run(argv)
    if rc != 0:
        return LibResult(
            ok=False,
            summary=f"openclaw cron list failed (rc={rc})",
            details={
                "argv": argv,
                "returncode": rc,
                "stderr_excerpt": _excerpt(stderr),
            },
        )
    jobs = _parse_list_payload(stdout)
    return LibResult(
        ok=True,
        summary=f"openclaw cron list returned {len(jobs)} job(s)",
        details={"argv": argv, "crons": jobs},
    )


def openclaw_cron_disable(cron_name: str) -> LibResult:
    """Disable a named openclaw cron. Idempotent: no-op if already disabled."""
    if not cron_name:
        return LibResult(
            ok=False,
            summary="openclaw_cron_disable requires a non-empty cron_name",
            details={"error_code": "INVALID_ARGUMENT"},
        )

    listing = openclaw_cron_list()
    if not listing.ok:
        return LibResult(
            ok=False,
            summary=f"cannot disable {cron_name!r}: failed to list openclaw crons",
            details={**listing.details, "error_code": "LIST_FAILED"},
        )
    jobs = list(listing.details.get("crons", []))
    job = _find_job_by_name(jobs, cron_name)
    if job is None:
        return LibResult(
            ok=False,
            summary=f"openclaw cron {cron_name!r} not found",
            details={"error_code": "NOT_FOUND", "available": [j.get("name") for j in jobs]},
        )
    if not _is_enabled(job):
        return LibResult(
            ok=True,
            summary=f"openclaw cron {cron_name!r} already disabled (no-op)",
            details={"idempotent": True, "name": cron_name},
        )

    argv = [_OPENCLAW, "cron", "disable", "--name", cron_name]
    rc, stdout, stderr = _run(argv)
    if rc != 0:
        return LibResult(
            ok=False,
            summary=f"openclaw cron disable failed for {cron_name!r} (rc={rc})",
            details={
                "argv": argv,
                "returncode": rc,
                "stderr_excerpt": _excerpt(stderr),
            },
        )
    return LibResult(
        ok=True,
        summary=f"openclaw cron {cron_name!r} disabled",
        details={"argv": argv, "stdout": _excerpt(stdout)},
    )


def openclaw_cron_enable(cron_name: str) -> LibResult:
    """Enable a named openclaw cron. Idempotent: no-op if already enabled."""
    if not cron_name:
        return LibResult(
            ok=False,
            summary="openclaw_cron_enable requires a non-empty cron_name",
            details={"error_code": "INVALID_ARGUMENT"},
        )

    listing = openclaw_cron_list()
    if not listing.ok:
        return LibResult(
            ok=False,
            summary=f"cannot enable {cron_name!r}: failed to list openclaw crons",
            details={**listing.details, "error_code": "LIST_FAILED"},
        )
    jobs = list(listing.details.get("crons", []))
    job = _find_job_by_name(jobs, cron_name)
    if job is None:
        return LibResult(
            ok=False,
            summary=f"openclaw cron {cron_name!r} not found",
            details={"error_code": "NOT_FOUND", "available": [j.get("name") for j in jobs]},
        )
    if _is_enabled(job):
        return LibResult(
            ok=True,
            summary=f"openclaw cron {cron_name!r} already enabled (no-op)",
            details={"idempotent": True, "name": cron_name},
        )

    argv = [_OPENCLAW, "cron", "enable", "--name", cron_name]
    rc, stdout, stderr = _run(argv)
    if rc != 0:
        return LibResult(
            ok=False,
            summary=f"openclaw cron enable failed for {cron_name!r} (rc={rc})",
            details={
                "argv": argv,
                "returncode": rc,
                "stderr_excerpt": _excerpt(stderr),
            },
        )
    return LibResult(
        ok=True,
        summary=f"openclaw cron {cron_name!r} enabled",
        details={"argv": argv, "stdout": _excerpt(stdout)},
    )


def openclaw_cron_edit(
    cron_name: str,
    payload_path: str | None = None,
    schedule: str | None = None,
) -> LibResult:
    """Edit a cron's payload-file and/or schedule.

    One or both of *payload_path* and *schedule* must be set. Refuses to
    touch a cron not registered with openclaw.
    """
    if not cron_name:
        return LibResult(
            ok=False,
            summary="openclaw_cron_edit requires a non-empty cron_name",
            details={"error_code": "INVALID_ARGUMENT"},
        )
    if payload_path is None and schedule is None:
        return LibResult(
            ok=False,
            summary="openclaw_cron_edit requires payload_path and/or schedule",
            details={"error_code": "INVALID_ARGUMENT"},
        )

    listing = openclaw_cron_list()
    if not listing.ok:
        return LibResult(
            ok=False,
            summary=f"cannot edit {cron_name!r}: failed to list openclaw crons",
            details={**listing.details, "error_code": "LIST_FAILED"},
        )
    jobs = list(listing.details.get("crons", []))
    if _find_job_by_name(jobs, cron_name) is None:
        return LibResult(
            ok=False,
            summary=f"openclaw cron {cron_name!r} not registered; refusing to edit",
            details={"error_code": "NOT_FOUND", "available": [j.get("name") for j in jobs]},
        )

    argv: list[str] = [_OPENCLAW, "cron", "edit", "--name", cron_name]
    if payload_path is not None:
        argv.extend(["--payload-file", payload_path])
    if schedule is not None:
        argv.extend(["--schedule", schedule])

    rc, stdout, stderr = _run(argv)
    if rc != 0:
        return LibResult(
            ok=False,
            summary=f"openclaw cron edit failed for {cron_name!r} (rc={rc})",
            details={
                "argv": argv,
                "returncode": rc,
                "stderr_excerpt": _excerpt(stderr),
            },
        )
    return LibResult(
        ok=True,
        summary=f"openclaw cron {cron_name!r} edited",
        details={
            "argv": argv,
            "payload_path": payload_path,
            "schedule": schedule,
            "stdout": _excerpt(stdout),
        },
    )


__all__ = [
    "openclaw_cron_disable",
    "openclaw_cron_enable",
    "openclaw_cron_edit",
    "openclaw_cron_list",
]


# ---------------------------------------------------------------------------
# Module-as-CLI surface for bash callers:
#   python3 -m scripts.deploy.lib.cron openclaw_cron_disable felix-vikunja-sync-driver
# ---------------------------------------------------------------------------

_CLI_FUNCS = {
    "openclaw_cron_disable": openclaw_cron_disable,
    "openclaw_cron_enable": openclaw_cron_enable,
    "openclaw_cron_edit": openclaw_cron_edit,
    "openclaw_cron_list": openclaw_cron_list,
}


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    import sys as _sys

    from ._cli import run as _run

    _sys.exit(_run(_CLI_FUNCS, _sys.argv[1:], prog="scripts.deploy.lib.cron"))
