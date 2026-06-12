"""Canonical apply orchestrator for the felix-deployer applier.

``dry_run_then_apply_gate`` is the single composition point for a deploy
manifest's lifecycle. It mirrors the state-transition diagram in
``kitty-specs/pull-based-deploy-pipeline-01KTYQQS/data-model.md`` and the
phase enum documented in ``contracts/dm-payload-v1.md``.

Phase strings (kept here as module-level constants so they cannot drift
from the contract):

* ``tier_guard`` — :func:`scripts.deploy.lib.tier.tier_guard` failed.
* ``snapshot`` — :func:`scripts.deploy.lib.snapshot.verify_restic_recent`
  failed (Tier 2 only).
* ``verification_pre`` — a ``manifest.verification.pre[*]`` command failed.
* ``entrypoint_dry_run`` — ``<entrypoint> --dry-run`` failed; apply is
  aborted and the entrypoint is not re-invoked with ``--apply``.
* ``entrypoint_apply`` — ``<entrypoint> --apply`` failed.
* ``verification_post`` — a ``manifest.verification.post[*]`` command failed.
* ``complete`` — all phases passed; deploy is considered applied.

The orchestrator never writes the applied entry itself; callers (the
applier in WP04) record success or failure based on the LibResult.
"""

from __future__ import annotations

import shlex
import subprocess
from typing import Any, Mapping, Sequence

from . import LibResult
from . import snapshot, tier

# ---------------------------------------------------------------------------
# Phase constants — MUST match contracts/dm-payload-v1.md and data-model.md.
# These are imported by tests so drift between the contract and code is
# caught by review rather than silent in production.
# ---------------------------------------------------------------------------

PHASE_TIER_GUARD = "tier_guard"
PHASE_SNAPSHOT = "snapshot"
PHASE_VERIFICATION_PRE = "verification_pre"
PHASE_ENTRYPOINT_DRY_RUN = "entrypoint_dry_run"
PHASE_ENTRYPOINT_APPLY = "entrypoint_apply"
PHASE_VERIFICATION_POST = "verification_post"
PHASE_COMPLETE = "complete"

PHASES = (
    PHASE_TIER_GUARD,
    PHASE_SNAPSHOT,
    PHASE_VERIFICATION_PRE,
    PHASE_ENTRYPOINT_DRY_RUN,
    PHASE_ENTRYPOINT_APPLY,
    PHASE_VERIFICATION_POST,
    PHASE_COMPLETE,
)

# Tier that requires a recent Restic snapshot before apply.
_SNAPSHOT_REQUIRED_TIER = 2

# How many chars of stdout/stderr to keep in LibResult.details.
_STDERR_EXCERPT_MAX = 2000


def _excerpt(text: str | None, limit: int = _STDERR_EXCERPT_MAX) -> str:
    if not text:
        return ""
    if len(text) <= limit:
        return text
    return text[:limit] + "...<truncated>"


def _run_shell(cmd: str | Sequence[str]) -> LibResult:
    """Run *cmd* as a subprocess and return a LibResult.

    * ``str`` → ``shell=True`` (verification commands may use pipes, env
      expansion, etc.). Shell injection risk is acknowledged in the
      module-level risks note: manifests are operator-authored and
      PR-reviewed before they ever reach this code path.
    * ``Sequence[str]`` → ``shell=False`` (entrypoint invocations and any
      caller that wants to skip shell parsing).

    Returns ``ok=True`` iff the process exits with code 0.
    """
    if not cmd:
        return LibResult(
            ok=False,
            summary="_run_shell: empty command",
            details={"error_code": "EMPTY_COMMAND"},
        )

    if isinstance(cmd, str):
        argv_for_log = cmd
        try:
            proc = subprocess.run(  # noqa: S602 - PR-reviewed manifest content
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError as exc:
            return LibResult(
                ok=False,
                summary=f"_run_shell: failed to spawn {cmd!r}: {exc}",
                details={
                    "error_code": "SPAWN_FAILED",
                    "argv": cmd,
                    "error": str(exc),
                },
            )
    else:
        argv = list(cmd)
        argv_for_log = " ".join(shlex.quote(p) for p in argv)
        try:
            proc = subprocess.run(  # noqa: S603 - argv list, no shell
                argv,
                shell=False,
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError as exc:
            return LibResult(
                ok=False,
                summary=f"_run_shell: failed to spawn {argv!r}: {exc}",
                details={
                    "error_code": "SPAWN_FAILED",
                    "argv": argv,
                    "error": str(exc),
                },
            )

    if proc.returncode == 0:
        return LibResult(
            ok=True,
            summary=f"shell ok: {argv_for_log}",
            details={
                "argv": argv_for_log,
                "returncode": 0,
                "stdout_excerpt": _excerpt(proc.stdout),
            },
        )
    return LibResult(
        ok=False,
        summary=f"shell failed (rc={proc.returncode}): {argv_for_log}",
        details={
            "argv": argv_for_log,
            "returncode": proc.returncode,
            "stdout_excerpt": _excerpt(proc.stdout),
            "stderr_excerpt": _excerpt(proc.stderr),
        },
    )


def _with_phase(result: LibResult, phase: str, *, summary: str | None = None) -> LibResult:
    """Return a new LibResult with ``phase`` injected into ``details``.

    LibResult is frozen, so this constructs a fresh instance. Optionally
    overrides the summary string when the caller wants a phase-flavoured
    message rather than the raw subprocess summary.
    """
    merged: dict[str, Any] = dict(result.details)
    merged["phase"] = phase
    return LibResult(
        ok=result.ok,
        summary=summary if summary is not None else result.summary,
        details=merged,
    )


def dry_run_then_apply_gate(
    manifest: Mapping[str, Any],
    manifest_path: str,
) -> LibResult:
    """Canonical apply sequence per ``data-model.md`` state-transitions.

    The phases (in order) are:

    1. ``tier_guard`` — tier policy, mode=runtime.
    2. ``snapshot`` — Restic recency, only when ``tier == 2``.
    3. ``verification_pre`` — every ``verification.pre[]`` command must
       exit 0.
    4. ``entrypoint_dry_run`` — ``<entrypoint> --dry-run`` must exit 0;
       if not, apply is NOT invoked.
    5. ``entrypoint_apply`` — ``<entrypoint> --apply`` must exit 0.
    6. ``verification_post`` — every ``verification.post[]`` command must
       exit 0.

    On full success, returns ``LibResult(ok=True, summary='applied',
    details={'phase': 'complete', 'manifest_path': ..., 'manifest_name':
    ..., 'tier': ...})``.

    On any failure, returns ``ok=False`` with ``details['phase']`` set to
    the phase that stopped execution. The ``manifest_path`` and
    ``manifest_name`` are echoed in details for the failure record writer.
    """
    name = manifest.get("name") if isinstance(manifest, Mapping) else None
    tier_value = manifest.get("tier") if isinstance(manifest, Mapping) else None
    context = {
        "manifest_name": name,
        "manifest_path": manifest_path,
        "tier": tier_value,
    }

    # 1. tier_guard
    r = tier.tier_guard(manifest, mode=tier.MODE_RUNTIME)
    if not r.ok:
        return _with_phase(
            LibResult(
                ok=False,
                summary=r.summary,
                details={**r.details, **context},
            ),
            PHASE_TIER_GUARD,
        )

    # 2. snapshot (Tier 2 only)
    if tier_value == _SNAPSHOT_REQUIRED_TIER:
        r = snapshot.verify_restic_recent()
        if not r.ok:
            return _with_phase(
                LibResult(
                    ok=False,
                    summary=r.summary,
                    details={**r.details, **context},
                ),
                PHASE_SNAPSHOT,
            )

    # 3. verification.pre
    verification = manifest.get("verification") or {}
    for cmd in verification.get("pre", []) or []:
        r = _run_shell(cmd)
        if not r.ok:
            return _with_phase(
                LibResult(
                    ok=False,
                    summary=f"verification.pre failed: {cmd}",
                    details={**r.details, **context, "failed_command": cmd},
                ),
                PHASE_VERIFICATION_PRE,
            )

    entrypoint = manifest.get("entrypoint")

    # 4. entrypoint --dry-run
    r = _run_shell([entrypoint, "--dry-run"])
    if not r.ok:
        return _with_phase(
            LibResult(
                ok=False,
                summary="dry-run failed; not applying",
                details={**r.details, **context},
            ),
            PHASE_ENTRYPOINT_DRY_RUN,
        )

    # 5. entrypoint --apply
    r = _run_shell([entrypoint, "--apply"])
    if not r.ok:
        return _with_phase(
            LibResult(
                ok=False,
                summary="apply failed",
                details={**r.details, **context},
            ),
            PHASE_ENTRYPOINT_APPLY,
        )

    # 6. verification.post
    for cmd in verification.get("post", []) or []:
        r = _run_shell(cmd)
        if not r.ok:
            return _with_phase(
                LibResult(
                    ok=False,
                    summary=f"verification.post failed: {cmd}",
                    details={**r.details, **context, "failed_command": cmd},
                ),
                PHASE_VERIFICATION_POST,
            )

    return LibResult(
        ok=True,
        summary="applied",
        details={**context, "phase": PHASE_COMPLETE},
    )


__all__ = [
    "dry_run_then_apply_gate",
    "PHASES",
    "PHASE_TIER_GUARD",
    "PHASE_SNAPSHOT",
    "PHASE_VERIFICATION_PRE",
    "PHASE_ENTRYPOINT_DRY_RUN",
    "PHASE_ENTRYPOINT_APPLY",
    "PHASE_VERIFICATION_POST",
    "PHASE_COMPLETE",
]


# ---------------------------------------------------------------------------
# Module-as-CLI surface for bash callers:
#   python3 -m scripts.deploy.lib.apply dry_run_then_apply_gate <manifest-path>
# ---------------------------------------------------------------------------


def _cli_dry_run_then_apply_gate(*args: str) -> LibResult:
    if not args:
        return LibResult(
            ok=False,
            summary="dry_run_then_apply_gate: missing manifest path",
            details={"error_code": "INVALID_ARGUMENT"},
        )
    from .manifest import load_manifest

    manifest_path = args[0]
    try:
        manifest_data = load_manifest(manifest_path)
    except (FileNotFoundError, ValueError) as exc:
        return LibResult(
            ok=False,
            summary=f"dry_run_then_apply_gate: failed to load {manifest_path}: {exc}",
            details={"error_code": "LOAD_FAILED", "error": str(exc)},
        )
    return dry_run_then_apply_gate(manifest_data, manifest_path)


_CLI_FUNCS = {
    "dry_run_then_apply_gate": _cli_dry_run_then_apply_gate,
}


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    import sys as _sys

    from ._cli import run as _run

    _sys.exit(_run(_CLI_FUNCS, _sys.argv[1:], prog="scripts.deploy.lib.apply"))
