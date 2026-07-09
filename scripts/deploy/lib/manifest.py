"""Deploy-manifest loading, schema validation, and applied-sequence math.

Schema-of-record lives at ``deploys/schema/manifest-v1.schema.json``
(JSON Schema 2020-12). We pin the validator to
:class:`jsonschema.Draft202012Validator` explicitly because the schema relies
on ``allOf`` + ``if`` / ``then`` clauses to enforce Tier-1/2 verification
requirements — the library's default validator (Draft 7) silently ignores
those clauses, which would let an invalid manifest pass validation.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator, ValidationError

from . import LibResult

# ---------------------------------------------------------------------------
# Tooling-scripts path bootstrap so ``audited_surfaces`` resolves.
#
# ``tooling/scripts/audited_surfaces.py`` is not a package (no __init__.py);
# we replicate the sibling pattern (check_audited_surface_drift.py,
# felix-deployer/rebaseline.py): insert the directory on sys.path and import
# by module name. We import the *module* (not the names) so a test that
# monkeypatches ``audited_surfaces.AUDITED_SURFACES_PATH`` is honoured, and so
# validation reads the registry through the **non-exiting** helper only.
# ---------------------------------------------------------------------------

_TOOLING_SCRIPTS = Path(__file__).resolve().parents[3] / "tooling" / "scripts"
if str(_TOOLING_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_TOOLING_SCRIPTS))

import audited_surfaces  # noqa: E402  # type: ignore[import-not-found]

# Default locations relative to the repo root. Callers may override either
# via the explicit *schema_path* argument or by passing a *root* hint to
# :func:`next_applied_seq` (mainly useful for tests).
_DEFAULT_SCHEMA_REL = Path("deploys/schema/manifest-v1.schema.json")
_DEFAULT_APPLIED_REL = Path("deploys/applied")

_APPLIED_NAME_RE = re.compile(r"^(\d+)-[A-Za-z0-9._-]+\.yaml$")


def _repo_root() -> Path:
    """Repo root for this checkout.

    ``scripts/deploy/lib/manifest.py`` -> ``parents[3]`` is the repo root.
    Kept as a function (not a module-level constant) so monkeypatching
    ``Path`` in tests is straightforward and so each call resolves against
    the current working tree (lane worktrees included).
    """
    return Path(__file__).resolve().parents[3]


def _default_schema_path() -> Path:
    return _repo_root() / _DEFAULT_SCHEMA_REL


def _default_applied_dir() -> Path:
    return _repo_root() / _DEFAULT_APPLIED_REL


def load_manifest(path: str | os.PathLike[str]) -> dict[str, Any]:
    """Load a YAML manifest and return it as a dict.

    Uses :func:`yaml.safe_load` (never :func:`yaml.load`) for security and
    determinism. Raises :class:`ValueError` on parse failure or when the
    YAML root is not a mapping. Raises :class:`FileNotFoundError` when the
    path does not exist.
    """
    target = Path(path)
    if not target.exists():
        raise FileNotFoundError(f"manifest not found: {target}")
    try:
        raw = target.read_text(encoding="utf-8")
        data = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise ValueError(f"failed to parse manifest {target}: {exc}") from exc
    if data is None:
        raise ValueError(f"manifest {target} is empty")
    if not isinstance(data, dict):
        raise ValueError(
            f"manifest {target} root must be a mapping; got {type(data).__name__}"
        )
    return data


def _validate_expected_baselines(
    data: dict[str, Any],
    schema_path_resolved: Path,
) -> LibResult | None:
    """Validate the optional ``expected_baselines`` field.

    Returns ``None`` when the field is absent (unchanged behaviour, FR-009) or
    when the declaration is valid. Returns an invalid :class:`LibResult` when:

    * the registry cannot be read — via the **non-exiting** reader, so a
      malformed registry fails the *manifest*, never the deployer tick (a
      ``SystemExit`` in the tick queue loop would crash felix-deployer; NFR-001);
    * a declared name is not in the registry's known-baseline set (message
      names the offender(s), FR-007);
    * ``audited_surface`` is not ``true`` (the R2 coupling rule, FR-007).
    """
    declared = data.get("expected_baselines")
    if declared is None:
        return None

    if data.get("audited_surface") is not True:
        return LibResult(
            ok=False,
            summary="expected_baselines requires audited_surface: true",
            details={
                "error_code": "EXPECTED_BASELINES_COUPLING",
                "schema_path": str(schema_path_resolved),
            },
        )

    # NON-exiting read only — never audited_surfaces.load_audited_surfaces().
    registry, reason = audited_surfaces.load_audited_surfaces_or_error()
    if registry is None:
        return LibResult(
            ok=False,
            summary=f"expected_baselines: registry could not be read: {reason}",
            details={
                "error_code": "REGISTRY_UNREADABLE",
                "error": reason,
                "schema_path": str(schema_path_resolved),
            },
        )

    known = audited_surfaces.known_baselines(registry)
    unknown = [name for name in declared if name not in known]
    if unknown:
        return LibResult(
            ok=False,
            summary=(
                "expected_baselines contains unknown baseline(s) "
                f"(validated against the registry's known set): {', '.join(unknown)}"
            ),
            details={
                "error_code": "EXPECTED_BASELINES_UNKNOWN",
                "unknown": unknown,
                "known": sorted(known),
                "schema_path": str(schema_path_resolved),
            },
        )
    return None


def validate_expected_baselines_only(
    data: dict[str, Any],
    schema_path: str | os.PathLike[str] | None = None,
) -> LibResult:
    """Validate ONLY the ``expected_baselines`` rules (no JSON-Schema pass).

    The felix-deployer tick calls this BEFORE ``dry_run_then_apply_gate`` so a
    bogus/decoupled ``expected_baselines`` declaration rejects the manifest with
    office2 state untouched (Codex HIGH-2). Running the full ``validate_manifest``
    pre-apply is deliberately avoided: the pull-based pipeline does not
    JSON-Schema-validate before applying today, so tightening that here would
    change apply behaviour for every manifest. This checks purely the R2 rules:

    * ``expected_baselines`` absent → ``ok=True`` (FR-009, unchanged behaviour);
    * ``expected_baselines`` present but ``audited_surface`` not ``true`` →
      invalid (coupling rule);
    * a declared name not in the registry's known-baseline set → invalid.

    Reuses :func:`_validate_expected_baselines` so the rule stays single-sourced
    with :func:`validate_manifest`.
    """
    schema_path_resolved = Path(schema_path) if schema_path else _default_schema_path()
    result = _validate_expected_baselines(data, schema_path_resolved)
    if result is not None:
        return result
    return LibResult(
        ok=True,
        summary="expected_baselines valid",
        details={"schema_path": str(schema_path_resolved)},
    )


def validate_manifest(
    data: dict[str, Any],
    schema_path: str | os.PathLike[str] | None = None,
) -> LibResult:
    """Validate *data* against the v1 manifest schema.

    Uses :class:`jsonschema.Draft202012Validator` explicitly. Returns
    ``ok=True`` when the manifest is well-formed; otherwise ``ok=False``
    with ``details['errors']`` listing each violation's path + message.
    """
    schema_path_resolved = Path(schema_path) if schema_path else _default_schema_path()
    if not schema_path_resolved.exists():
        return LibResult(
            ok=False,
            summary=f"schema file missing: {schema_path_resolved}",
            details={
                "error_code": "SCHEMA_MISSING",
                "schema_path": str(schema_path_resolved),
            },
        )
    try:
        schema = json.loads(schema_path_resolved.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return LibResult(
            ok=False,
            summary=f"failed to load schema {schema_path_resolved}: {exc}",
            details={
                "error_code": "SCHEMA_LOAD_FAILED",
                "schema_path": str(schema_path_resolved),
                "error": str(exc),
            },
        )

    try:
        Draft202012Validator.check_schema(schema)
    except Exception as exc:  # pragma: no cover - schema is committed
        return LibResult(
            ok=False,
            summary=f"schema invalid: {exc}",
            details={"error_code": "SCHEMA_INVALID", "error": str(exc)},
        )

    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(data), key=lambda e: list(e.absolute_path))
    if not errors:
        baselines_result = _validate_expected_baselines(data, schema_path_resolved)
        if baselines_result is not None:
            return baselines_result
        return LibResult(
            ok=True,
            summary=f"manifest valid against {schema_path_resolved.name}",
            details={"schema_path": str(schema_path_resolved)},
        )
    return LibResult(
        ok=False,
        summary=f"manifest invalid: {len(errors)} error(s)",
        details={
            "error_code": "SCHEMA_VIOLATION",
            "errors": [
                {
                    "path": list(err.absolute_path),
                    "message": err.message,
                }
                for err in errors
            ],
            "schema_path": str(schema_path_resolved),
        },
    )


def next_applied_seq(applied_dir: str | os.PathLike[str] | None = None) -> int:
    """Return the next sequential prefix for ``deploys/applied/<NNNN>-...``.

    Scans *applied_dir* (default: ``deploys/applied/`` under the repo root)
    for files matching ``<digits>-<name>.yaml``. Returns ``max(prefix) + 1``,
    or ``1`` when no matching files exist.

    Note: there is a TOCTOU window between this scan and the subsequent
    write. The applier is ``Type=oneshot`` per the WP04 design, so concurrent
    execution is not expected in production; callers that need stronger
    guarantees should hold an external lock.
    """
    target = Path(applied_dir) if applied_dir else _default_applied_dir()
    if not target.exists():
        return 1
    max_seq = 0
    try:
        entries = list(target.iterdir())
    except OSError:
        return 1
    for entry in entries:
        if not entry.is_file():
            continue
        match = _APPLIED_NAME_RE.match(entry.name)
        if not match:
            continue
        try:
            seq = int(match.group(1))
        except ValueError:  # pragma: no cover - regex guarantees digits
            continue
        if seq > max_seq:
            max_seq = seq
    return max_seq + 1


def validate_manifest_file(
    path: str | os.PathLike[str],
    schema_path: str | os.PathLike[str] | None = None,
) -> LibResult:
    """Convenience: ``load_manifest`` + ``validate_manifest`` in one call.

    Returns ``ok=False`` on either load failure or schema violation.
    """
    try:
        data = load_manifest(path)
    except (FileNotFoundError, ValueError) as exc:
        return LibResult(
            ok=False,
            summary=f"manifest load failed: {exc}",
            details={"error_code": "LOAD_FAILED", "error": str(exc)},
        )
    return validate_manifest(data, schema_path=schema_path)


__all__ = [
    "load_manifest",
    "validate_manifest",
    "validate_expected_baselines_only",
    "validate_manifest_file",
    "next_applied_seq",
]


# ---------------------------------------------------------------------------
# Module-as-CLI surface for bash callers:
#   python3 -m scripts.deploy.lib.manifest validate_manifest_file <path> [<schema>]
# ---------------------------------------------------------------------------


def _cli_validate_manifest_file(*args: str) -> LibResult:
    if not args:
        return LibResult(
            ok=False,
            summary="validate_manifest_file: missing manifest path",
            details={"error_code": "INVALID_ARGUMENT"},
        )
    schema = args[1] if len(args) >= 2 and args[1] else None
    return validate_manifest_file(args[0], schema_path=schema)


def _cli_next_applied_seq(*args: str) -> LibResult:
    target = args[0] if args else None
    seq = next_applied_seq(applied_dir=target)
    return LibResult(
        ok=True,
        summary=f"next applied seq: {seq}",
        details={"seq": seq, "applied_dir": target},
    )


_CLI_FUNCS = {
    "validate_manifest_file": _cli_validate_manifest_file,
    "next_applied_seq": _cli_next_applied_seq,
}


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    import sys as _sys

    from ._cli import run as _run

    _sys.exit(_run(_CLI_FUNCS, _sys.argv[1:], prog="scripts.deploy.lib.manifest"))
