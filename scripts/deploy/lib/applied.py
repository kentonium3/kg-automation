"""Applied-entry writer for the deploy pipeline.

The applier (WP04) and the bootstrap wrapper (WP05) both record successful
deploys here. The on-disk artefact is
``deploys/applied/<NNNN>-<name>.yaml`` per ``data-model.md``.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import sys
from pathlib import Path
from typing import Any

import yaml

from . import LibResult
from .manifest import (
    _default_applied_dir,
    load_manifest,
    next_applied_seq,
    validate_manifest,
)

_VALID_APPLY_MODES = ("manifest", "bootstrap")
_SEQ_WIDTH = 4


def _utc_now_iso() -> str:
    return _dt.datetime.now(tz=_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_applied(
    manifest: dict[str, Any],
    apply_mode: str,
    applied_at: str | None = None,
    applied_dir: str | os.PathLike[str] | None = None,
    schema_path: str | os.PathLike[str] | None = None,
) -> LibResult:
    """Write *manifest* to the applied directory and return its location.

    Augments *manifest* with ``apply_mode`` and ``applied_at`` (defaulting to
    the current UTC time), validates the result against the v1 schema, then
    writes ``<applied_dir>/<NNNN>-<name>.yaml`` where ``NNNN`` comes from
    :func:`next_applied_seq`.

    On success, ``details`` includes the resolved ``path``, ``seq``,
    ``apply_mode``, and ``applied_at`` for downstream callers.
    """
    if apply_mode not in _VALID_APPLY_MODES:
        return LibResult(
            ok=False,
            summary=f"invalid apply_mode {apply_mode!r}; expected one of {_VALID_APPLY_MODES}",
            details={"error_code": "INVALID_ARGUMENT"},
        )
    if not isinstance(manifest, dict):
        return LibResult(
            ok=False,
            summary=f"manifest must be a dict; got {type(manifest).__name__}",
            details={"error_code": "INVALID_ARGUMENT"},
        )

    augmented = dict(manifest)
    # ``rebaseline`` is a deployer-owned field stamped post-hoc by
    # stamp_rebaseline (#688) — never author-supplied. Strip any value carried in
    # from the queued manifest so an operator cannot pre-seed a false outcome.
    augmented.pop("rebaseline", None)
    augmented["apply_mode"] = apply_mode
    augmented["applied_at"] = applied_at or _utc_now_iso()

    validation = validate_manifest(augmented, schema_path=schema_path)
    if not validation.ok:
        return LibResult(
            ok=False,
            summary=f"refusing to write applied entry: {validation.summary}",
            details={
                "error_code": validation.details.get("error_code", "SCHEMA_VIOLATION"),
                "errors": validation.details.get("errors"),
                "schema_path": validation.details.get("schema_path"),
            },
        )

    name = augmented.get("name")
    if not isinstance(name, str) or not name:
        # Should be impossible after schema validation, but defend anyway.
        return LibResult(
            ok=False,
            summary="manifest missing required 'name' field after validation",
            details={"error_code": "INVALID_MANIFEST"},
        )

    target_dir = Path(applied_dir) if applied_dir else _default_applied_dir()
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return LibResult(
            ok=False,
            summary=f"failed to create applied directory {target_dir}: {exc}",
            details={"error_code": "MKDIR_FAILED", "error": str(exc)},
        )

    seq = next_applied_seq(applied_dir=target_dir)
    filename = f"{seq:0{_SEQ_WIDTH}d}-{name}.yaml"
    out_path = target_dir / filename
    if out_path.exists():
        return LibResult(
            ok=False,
            summary=f"refusing to overwrite existing applied entry {out_path}",
            details={"error_code": "ALREADY_EXISTS", "path": str(out_path)},
        )

    try:
        serialised = yaml.safe_dump(augmented, sort_keys=False, default_flow_style=False)
        out_path.write_text(serialised, encoding="utf-8")
    except (OSError, yaml.YAMLError) as exc:
        return LibResult(
            ok=False,
            summary=f"failed to write applied entry {out_path}: {exc}",
            details={"error_code": "WRITE_FAILED", "error": str(exc)},
        )

    return LibResult(
        ok=True,
        summary=f"wrote applied entry {out_path.name} (seq={seq})",
        details={
            "path": str(out_path),
            "seq": seq,
            "name": name,
            "apply_mode": apply_mode,
            "applied_at": augmented["applied_at"],
        },
    )


def stamp_rebaseline(
    applied_path: str | os.PathLike[str],
    annotation: dict[str, Any],
    schema_path: str | os.PathLike[str] | None = None,
) -> LibResult:
    """Write the ``rebaseline`` annotation onto an existing applied record (#688).

    Reads the applied YAML at *applied_path*, sets its ``rebaseline`` field to
    *annotation*, re-validates against the v1 schema (so a malformed annotation
    is refused, never silently written), and writes the file back.

    Idempotent: re-stamping overwrites the field. Never raises — all failures
    are returned as a non-ok ``LibResult`` so the felix-deployer tick can log
    and continue (NFR-001).
    """
    path = Path(applied_path)
    try:
        record = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        return LibResult(
            ok=False,
            summary=f"failed to read applied record {path}: {exc}",
            details={"error_code": "READ_FAILED", "error": str(exc)},
        )
    if not isinstance(record, dict):
        return LibResult(
            ok=False,
            summary=f"applied record {path} is not a mapping",
            details={"error_code": "INVALID_RECORD"},
        )

    augmented = dict(record)
    augmented["rebaseline"] = annotation

    validation = validate_manifest(augmented, schema_path=schema_path)
    if not validation.ok:
        return LibResult(
            ok=False,
            summary=f"refusing to stamp invalid rebaseline annotation: {validation.summary}",
            details={
                "error_code": validation.details.get("error_code", "SCHEMA_VIOLATION"),
                "errors": validation.details.get("errors"),
            },
        )

    try:
        serialised = yaml.safe_dump(augmented, sort_keys=False, default_flow_style=False)
        path.write_text(serialised, encoding="utf-8")
    except (OSError, yaml.YAMLError) as exc:
        return LibResult(
            ok=False,
            summary=f"failed to write stamped applied record {path}: {exc}",
            details={"error_code": "WRITE_FAILED", "error": str(exc)},
        )

    return LibResult(
        ok=True,
        summary=f"stamped rebaseline outcome {annotation.get('outcome')!r} onto {path.name}",
        details={"path": str(path), "outcome": annotation.get("outcome")},
    )


def _cli_write_applied(argv: list[str]) -> int:
    """``python3 -m scripts.deploy.lib.applied write_applied --name ... --apply-mode ...``

    Used by the bootstrap wrapper in WP05. The manifest body is loaded from
    ``--manifest <path>`` (an existing YAML file under ``deploys/queued/``).
    Prints the LibResult summary to stdout and ``details`` as JSON when
    ``--json`` is set. Exits 0 on success, 1 on failure.
    """
    parser = argparse.ArgumentParser(
        prog="python3 -m scripts.deploy.lib.applied write_applied",
        description="Write a manifest to deploys/applied/ as a sequenced entry.",
    )
    parser.add_argument(
        "--manifest",
        required=True,
        help="Path to the source manifest YAML (typically under deploys/queued/).",
    )
    parser.add_argument(
        "--apply-mode",
        required=True,
        choices=list(_VALID_APPLY_MODES),
        help="Apply mode recorded in the entry.",
    )
    parser.add_argument(
        "--applied-at",
        default=None,
        help="ISO 8601 UTC timestamp; defaults to now.",
    )
    parser.add_argument(
        "--applied-dir",
        default=None,
        help="Override applied directory (default: deploys/applied/).",
    )
    parser.add_argument(
        "--schema-path",
        default=None,
        help="Override schema path (default: deploys/schema/manifest-v1.schema.json).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print LibResult.details as JSON on stdout.",
    )
    args = parser.parse_args(argv)

    try:
        manifest = load_manifest(args.manifest)
    except (FileNotFoundError, ValueError) as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 1

    result = write_applied(
        manifest,
        apply_mode=args.apply_mode,
        applied_at=args.applied_at,
        applied_dir=args.applied_dir,
        schema_path=args.schema_path,
    )
    if args.json:
        sys.stdout.write(json.dumps(dict(result.details), default=str) + "\n")
    else:
        sys.stdout.write(result.summary + "\n")
    return 0 if result.ok else 1


def _main(argv: list[str] | None = None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    if not args or args[0] in ("-h", "--help"):
        sys.stdout.write(
            "usage: python3 -m scripts.deploy.lib.applied write_applied [options]\n"
        )
        return 0 if args else 2
    command, *rest = args
    if command == "write_applied":
        return _cli_write_applied(rest)
    sys.stderr.write(f"unknown command: {command}\n")
    return 2


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    sys.exit(_main())


__all__ = ["write_applied", "stamp_rebaseline"]
