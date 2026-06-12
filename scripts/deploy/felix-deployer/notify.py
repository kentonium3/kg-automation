"""felix-deployer DM-notify surface.

Synthesises the WhatsApp DM payload per
``kitty-specs/pull-based-deploy-pipeline-01KTYQQS/contracts/dm-payload-v1.md``
and dispatches it through the existing ``openclaw cron`` surface.

The DM is best-effort: a dispatch failure is recorded but never
crashes the tick. The applier's job is to record the failure on
disk (in ``deploys/failed/``) so the operator has the durable
artefact; the DM is escalation, not the source of truth.

Invariants enforced here:

* ``payload_version`` is always ``"v1"``.
* ``error_summary`` is run through
  :func:`scripts.deploy.lib.verify.redact_secrets` BEFORE truncation
  to ≤500 chars.
* The 4-value ``phase`` enum is the one in dm-payload-v1.md
  (``tier_guard``, ``verification_pre``, ``entrypoint``,
  ``verification_post``). Callers pass either that or a lib.apply
  7-value phase; the mapping in :mod:`_tick` collapses it.
* Temp payload files are unlinked even when dispatch fails.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import pathlib
import subprocess
import tempfile
from typing import Any, Mapping

from scripts.deploy.lib import LibResult
from scripts.deploy.lib import verify as _verify

PAYLOAD_VERSION = "v1"
CRON_NAME = "felix-deployer-alert"

# Maximum length of error_summary in the payload (contract: ≤500 chars).
ERROR_SUMMARY_MAX = 500

# Phase strings accepted in the v1 payload. The applier may pass any of
# lib.apply's 7 phase constants; _tick.PHASE_TO_DM_PHASE collapses them
# before reaching this function. If a caller bypasses that mapping and
# passes an unknown phase string, we pass it through verbatim so the
# operator at least sees the raw signal — but it will fail validation
# under the receiving openclaw cron's schema.
DM_PHASES = ("tier_guard", "verification_pre", "entrypoint", "verification_post")


def _utc_now_iso() -> str:
    return _dt.datetime.now(tz=_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_payload(
    manifest: Mapping[str, Any],
    phase: str,
    error_summary: str,
    head_sha: str,
    failed_at: str | None = None,
) -> dict[str, Any]:
    """Synthesise the v1 DM payload.

    See ``contracts/dm-payload-v1.md`` for the canonical field shape.
    The ``error_summary`` is redacted then truncated to
    :data:`ERROR_SUMMARY_MAX` chars.
    """
    redacted = _verify.redact_secrets(error_summary or "")
    if len(redacted) > ERROR_SUMMARY_MAX:
        redacted = redacted[:ERROR_SUMMARY_MAX]
    return {
        "payload_version": PAYLOAD_VERSION,
        "manifest_name": manifest.get("name", "<unknown>"),
        "tier": manifest.get("tier"),
        "phase": phase,
        "error_summary": redacted,
        "head_sha": head_sha or "",
        "failed_at": failed_at or _utc_now_iso(),
    }


def _safe_unlink(path: str | pathlib.Path) -> None:
    """Unlink *path*, swallowing OSError. Used for temp-file cleanup."""
    try:
        os.unlink(path)
    except OSError:
        pass


def dispatch_failure_dm(
    manifest: Mapping[str, Any],
    phase: str,
    error_summary: str,
    head_sha: str,
    failed_at: str | None = None,
) -> LibResult:
    """Build payload and invoke ``openclaw cron run felix-deployer-alert``.

    Returns a :class:`LibResult` so the caller can record the dispatch
    outcome in the tick log. The function never raises for routine
    subprocess failures — only a genuine programmer error (e.g.,
    payload JSON serialisation crash) would surface as an exception,
    and even those are caught in :func:`scripts.deploy.felix_deployer._tick.run_tick`.

    The temp payload file is unlinked even when dispatch fails.
    """
    payload = build_payload(
        manifest=manifest,
        phase=phase,
        error_summary=error_summary,
        head_sha=head_sha,
        failed_at=failed_at,
    )

    # Write the payload to a temp file. ``delete=False`` so the child
    # process can read it after we close the handle.
    tmp_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".json",
            prefix="felix-deployer-alert-",
            delete=False,
            encoding="utf-8",
        ) as fh:
            json.dump(payload, fh)
            tmp_path = fh.name
    except OSError as exc:
        return LibResult(
            ok=False,
            summary=f"failed to write DM payload temp file: {exc}",
            details={"error_code": "TMPFILE_WRITE_FAILED", "error": str(exc)},
        )

    try:
        proc = subprocess.run(  # noqa: S603 - argv list, no shell
            [
                "openclaw",
                "cron",
                "run",
                CRON_NAME,
                "--payload-file",
                tmp_path,
                "--wait",
                "--json",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as exc:
        # openclaw binary not on PATH. Operator visibility, not crash.
        _safe_unlink(tmp_path)
        return LibResult(
            ok=False,
            summary=f"openclaw not found on PATH: {exc}",
            details={"error_code": "OPENCLAW_MISSING", "error": str(exc)},
        )
    except OSError as exc:
        _safe_unlink(tmp_path)
        return LibResult(
            ok=False,
            summary=f"failed to spawn openclaw: {exc}",
            details={"error_code": "SPAWN_FAILED", "error": str(exc)},
        )

    _safe_unlink(tmp_path)

    if proc.returncode == 0:
        return LibResult(
            ok=True,
            summary=f"DM dispatched via {CRON_NAME}",
            details={
                "payload": payload,
                "stdout_excerpt": (proc.stdout or "")[:200],
            },
        )
    return LibResult(
        ok=False,
        summary=f"openclaw cron run {CRON_NAME} failed (rc={proc.returncode})",
        details={
            "error_code": "DISPATCH_FAILED",
            "returncode": proc.returncode,
            "stderr_excerpt": (proc.stderr or "")[:200],
            "payload": payload,
        },
    )


__all__ = [
    "PAYLOAD_VERSION",
    "CRON_NAME",
    "ERROR_SUMMARY_MAX",
    "DM_PHASES",
    "build_payload",
    "dispatch_failure_dm",
]
