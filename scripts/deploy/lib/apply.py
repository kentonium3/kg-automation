"""Canonical apply orchestrator for the felix-deployer applier.

``dry_run_then_apply_gate`` is the single composition point for a deploy
manifest's lifecycle. It mirrors the state-transition diagram in
``kitty-specs/pull-based-deploy-pipeline-01KTYQQS/data-model.md`` and the
phase enum documented in ``contracts/dm-payload-v1.md``.

Phase strings (kept here as module-level constants so they cannot drift
from the contract):

* ``tier_guard`` — :func:`scripts.deploy.lib.tier.tier_guard` failed.
* ``snapshot`` — :func:`scripts.deploy.lib.snapshot.ensure_recent_backup`
  failed (Tier 2 only): the backup was stale/failed and the trigger or
  re-verify did not produce a fresh successful snapshot.
* ``verification_pre`` — a ``manifest.verification.pre[*]`` command failed.
* ``entrypoint_dry_run`` — ``<entrypoint> --dry-run`` failed; apply is
  aborted and the entrypoint is not re-invoked with ``--apply``.
* ``entrypoint_apply`` — ``<entrypoint> --apply`` failed.
* ``verification_post`` — a ``manifest.verification.post[*]`` command failed.
* ``complete`` — all phases passed; deploy is considered applied.

The orchestrator never writes the applied entry itself; callers (the
applier in WP04) record success or failure based on the LibResult.

Installed-file report (#1072): ``--apply`` alone runs with
:data:`scripts.deploy.lib.installed_report.ENV_VAR` pointing at a fresh
temporary file, and every other command runs with that variable removed. After
``--apply`` (success or failure) the report is read back and every result
returned from then on carries ``details["installed_report"]`` and
``details["installed_report_write_failed"]``. Results returned before
``--apply`` ran never carry them.
"""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import tempfile
from typing import Any, Mapping, Sequence

from . import LibResult
from . import installed_report, snapshot, tier

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


def _run_shell(cmd: str | Sequence[str], *, env: Mapping[str, str] | None = None) -> LibResult:
    """Run *cmd* as a subprocess and return a LibResult.

    ``env`` exists for the installed-file report channel (#1072), not as
    general plumbing: the gate passes an environment without
    :data:`installed_report.ENV_VAR` to every command, and one with it to
    ``--apply``. When ``env`` carries that variable, the *complete* stderr is
    scanned for :data:`installed_report.WRITE_FAILED_MARKER` before any
    truncation, and ``details["installed_report_write_failed"]`` is set.

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
                env=env,
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
                env=env,
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

    channel: dict[str, Any] = {}
    if env is not None and installed_report.ENV_VAR in env:
        channel["installed_report_write_failed"] = (
            installed_report.WRITE_FAILED_MARKER in (proc.stderr or "")
        )
    if proc.returncode == 0:
        return LibResult(
            ok=True,
            summary=f"shell ok: {argv_for_log}",
            details={
                "argv": argv_for_log,
                "returncode": 0,
                "stdout_excerpt": _excerpt(proc.stdout),
                **channel,
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
            **channel,
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
    2. ``snapshot`` — Restic recency (``ensure_recent_backup``: verify, and if
       stale trigger a backup + re-verify), only when ``tier == 2``.
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

    # 2. snapshot (Tier 2 only). #784: don't merely verify — ensure. If the
    # backup is stale/failed, trigger the sanctioned backup.sh, wait, and
    # re-verify before applying. If the trigger or re-verify fails, this returns
    # ok=False → the manifest is NOT applied and the caller's failure path emits
    # one ntfy alert and leaves it queued.
    if tier_value == _SNAPSHOT_REQUIRED_TIER:
        r = snapshot.ensure_recent_backup()
        if not r.ok:
            return _with_phase(
                LibResult(
                    ok=False,
                    summary=r.summary,
                    details={**r.details, **context},
                ),
                PHASE_SNAPSHOT,
            )

    # Every command runs without the report variable, whatever the parent
    # environment holds; only --apply gets one, pointing at a fresh file.
    base_env = {k: v for k, v in os.environ.items() if k != installed_report.ENV_VAR}

    # 3. verification.pre
    verification = manifest.get("verification") or {}
    for cmd in verification.get("pre", []) or []:
        r = _run_shell(cmd, env=base_env)
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
    r = _run_shell([entrypoint, "--dry-run"], env=base_env)
    if not r.ok:
        return _with_phase(
            LibResult(
                ok=False,
                summary="dry-run failed; not applying",
                details={**r.details, **context},
            ),
            PHASE_ENTRYPOINT_DRY_RUN,
        )

    # 5. entrypoint --apply, reporting what it installed (#1072)
    r, report = _apply_with_report(entrypoint, base_env)
    context = {**context, **report}
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
        r = _run_shell(cmd, env=base_env)
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


def _apply_with_report(entrypoint: Any, base_env: Mapping[str, str]) -> tuple[LibResult, dict[str, Any]]:
    """Run ``<entrypoint> --apply`` with a fresh report file and read it back.

    Returns the run's LibResult and the two channel keys to merge into every
    later result. Setup, read and cleanup problems become warnings in the
    report; none of them raises or changes the apply outcome.
    """
    warnings: list[str] = []
    tmpdir: str | None = None
    env = dict(base_env)
    try:
        tmpdir = tempfile.mkdtemp(prefix="felix-installed-report-")
        report_path = os.path.join(tmpdir, "installed.jsonl")
        env[installed_report.ENV_VAR] = report_path
    except OSError as exc:
        report_path = None
        warnings.append(f"could not create the report file: {exc}")

    r = _run_shell([entrypoint, "--apply"], env=env)
    write_failed = bool(r.details.get("installed_report_write_failed", False))
    details = {k: v for k, v in r.details.items() if k != "installed_report_write_failed"}
    r = LibResult(ok=r.ok, summary=r.summary, details=details)

    if report_path is not None:
        try:
            report = installed_report.read_report(report_path)
        except Exception as exc:  # noqa: BLE001 - read_report never raises; belt and braces
            report = {"entries": [], "rejected": True, "missing": False,
                      "warnings": [f"reading the report failed: {exc}"]}
    else:
        report = {"entries": [], "rejected": False, "missing": True, "warnings": []}
    if tmpdir is not None:
        shutil.rmtree(tmpdir, ignore_errors=True)
        if os.path.exists(tmpdir):
            warnings.append(f"could not remove {tmpdir}")
    report = {**report, "warnings": [*report.get("warnings", []), *warnings]}
    return r, {"installed_report": report, "installed_report_write_failed": write_failed}


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
