"""Tier-policy guard for deploy manifests.

Two modes:

* ``mode='ci'`` — used by ``.github/workflows/deploy-manifest-validate.yml``
  before a manifest can merge. Pure metadata checks against the manifest
  dict; no filesystem access.
* ``mode='runtime'`` — used by the felix-deployer applier at execute time.
  Re-runs every CI check (defense in depth) and additionally rejects
  manifests whose ``entrypoint`` does not exist on disk.

The Tier 0 ban exists because Tier 0 changes (UFW, iptables, sshd_config,
sudoers, kernel parameters, etc.) MUST stay manual via
``ssh office2-kgale`` per the Felix charter "Change-Risk Taxonomy". The
schema also rejects ``tier: 0`` at validation time, but the runtime guard
remains as belt-and-braces: an operator who hand-edits a queued manifest
to bypass schema check still gets caught here.

Error codes returned via ``LibResult.details['error_code']``:

* ``TIER_0_REJECTED`` — manifest declares ``tier == 0``.
* ``VERIFICATION_BLOCK_REQUIRED`` — Tier 1/2 manifest missing
  ``verification`` block (both modes; CI rejects pre-merge,
  runtime rejects at execute time).
* ``ENTRYPOINT_NOT_FOUND`` — runtime only; the entrypoint path declared
  in the manifest does not exist in the current working tree.
* ``INVALID_MODE`` — caller passed an unrecognised ``mode`` string.
* ``INVALID_MANIFEST`` — manifest is not a mapping or missing the
  ``tier`` field entirely.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Mapping

from . import LibResult

# ---------------------------------------------------------------------------
# Mode constants. Hardcoded here (and grep-friendly) so callers can import
# them rather than passing magic strings.
# ---------------------------------------------------------------------------

MODE_CI = "ci"
MODE_RUNTIME = "runtime"
_VALID_MODES = (MODE_CI, MODE_RUNTIME)

# Tiers that require a verification block per data-model.md invariant #2.
_VERIFICATION_REQUIRED_TIERS = frozenset({1, 2})


def _bad_mode(mode: str) -> LibResult:
    return LibResult(
        ok=False,
        summary=f"tier_guard: unknown mode {mode!r}; expected one of {_VALID_MODES}",
        details={"error_code": "INVALID_MODE", "mode": mode},
    )


def _bad_manifest(reason: str) -> LibResult:
    return LibResult(
        ok=False,
        summary=f"tier_guard: {reason}",
        details={"error_code": "INVALID_MANIFEST"},
    )


def _check_tier_zero(manifest: Mapping[str, Any]) -> LibResult | None:
    if manifest.get("tier") == 0:
        return LibResult(
            ok=False,
            summary="Tier 0 deploys must be manual via ssh office2-kgale",
            details={
                "error_code": "TIER_0_REJECTED",
                "tier": 0,
                "manifest_name": manifest.get("name"),
            },
        )
    return None


def _check_verification_block(manifest: Mapping[str, Any]) -> LibResult | None:
    tier = manifest.get("tier")
    if tier in _VERIFICATION_REQUIRED_TIERS and "verification" not in manifest:
        return LibResult(
            ok=False,
            summary=f"Tier {tier} requires verification block",
            details={
                "error_code": "VERIFICATION_BLOCK_REQUIRED",
                "tier": tier,
                "manifest_name": manifest.get("name"),
            },
        )
    return None


def _check_entrypoint_exists(manifest: Mapping[str, Any]) -> LibResult | None:
    entrypoint = manifest.get("entrypoint")
    if not isinstance(entrypoint, str) or not entrypoint:
        return LibResult(
            ok=False,
            summary="tier_guard(runtime): manifest missing entrypoint",
            details={
                "error_code": "ENTRYPOINT_NOT_FOUND",
                "entrypoint": entrypoint,
                "manifest_name": manifest.get("name"),
            },
        )
    if not os.path.exists(entrypoint):
        return LibResult(
            ok=False,
            summary=f"tier_guard(runtime): entrypoint not found on disk: {entrypoint}",
            details={
                "error_code": "ENTRYPOINT_NOT_FOUND",
                "entrypoint": entrypoint,
                "manifest_name": manifest.get("name"),
            },
        )
    return None


def tier_guard(manifest: Mapping[str, Any], mode: str = MODE_CI) -> LibResult:
    """Validate *manifest* against the tier policy.

    See module docstring for the full list of error codes and the
    distinction between ``mode='ci'`` and ``mode='runtime'``.
    """
    if mode not in _VALID_MODES:
        return _bad_mode(mode)
    if not isinstance(manifest, Mapping):
        return _bad_manifest(
            f"manifest must be a mapping; got {type(manifest).__name__}"
        )
    if "tier" not in manifest:
        return _bad_manifest("manifest missing required 'tier' field")

    # 1. Tier 0 is rejected in both modes.
    fail = _check_tier_zero(manifest)
    if fail is not None:
        return fail

    # 2. Tier 1/2 manifests need a verification block (both modes).
    fail = _check_verification_block(manifest)
    if fail is not None:
        return fail

    # 3. Runtime mode additionally checks the entrypoint exists on disk.
    if mode == MODE_RUNTIME:
        fail = _check_entrypoint_exists(manifest)
        if fail is not None:
            return fail

    return LibResult(
        ok=True,
        summary=f"Tier policy: pass (tier={manifest.get('tier')}, mode={mode})",
        details={
            "tier": manifest.get("tier"),
            "mode": mode,
            "manifest_name": manifest.get("name"),
        },
    )


__all__ = ["tier_guard", "MODE_CI", "MODE_RUNTIME"]


# ---------------------------------------------------------------------------
# Module-as-CLI surface for bash callers:
#   python3 -m scripts.deploy.lib.tier tier_guard <manifest-path> [ci|runtime]
# ---------------------------------------------------------------------------


def _cli_tier_guard(*args: str) -> LibResult:
    """CLI wrapper: ``<manifest-path> [mode]``. Mode defaults to ``ci``."""
    if not args:
        return LibResult(
            ok=False,
            summary="tier_guard: missing manifest path",
            details={"error_code": "INVALID_ARGUMENT"},
        )
    from .manifest import load_manifest

    mode = args[1] if len(args) >= 2 and args[1] else MODE_CI
    try:
        manifest_data = load_manifest(args[0])
    except (FileNotFoundError, ValueError) as exc:
        return LibResult(
            ok=False,
            summary=f"tier_guard: failed to load manifest {args[0]}: {exc}",
            details={"error_code": "LOAD_FAILED", "error": str(exc)},
        )
    return tier_guard(manifest_data, mode=mode)


_CLI_FUNCS = {
    "tier_guard": _cli_tier_guard,
}


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    import sys as _sys

    from ._cli import run as _run

    _sys.exit(_run(_CLI_FUNCS, _sys.argv[1:], prog="scripts.deploy.lib.tier"))
