"""Manifest reader: parse credential-manifest.json into Credential records.

See kitty-specs/credential-expiry-health-check-01KRCF92/contracts/manifest-reader.md
for the authoritative contract.

# Mission WP01 cycle-3 marker — workflow-state cleanup (no code change)
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from typing import Optional


ALLOWED_REVIEW_CADENCES = {
    "annual",
    "monitor-activity",
    "on-revocation",
    "n/a",
    "session",
}

# Cadences for which last_reviewed (or created_date) drives boundary math.
FIXED_INTERVAL_CADENCES = {"annual"}


class ManifestUnreadableError(Exception):
    """The manifest file could not be parsed at all (I/O, JSON, or top-level shape).

    Per FR-011, the auditor exits non-zero in this state and files no alerts.
    """


class ManifestQualityError(Exception):
    """A credential entry has a structural validation error that prevents safe parsing.

    Raised (not collected) for conditions that must halt processing: e.g.,
    liveness_probe.enabled is true but required fields are missing, or the
    liveness_probe block contains unknown keys. See
    kitty-specs/credential-liveness-probe-01KTP9M8/contracts/manifest-liveness-probe-block.md.
    """


@dataclass(frozen=True)
class LivenessProbeConfig:
    """Per-credential liveness probe configuration (generic, command-based).

    A credential opts into liveness probing by declaring the argv `command` to
    run and the `dead_exit_codes` that mean "this credential is dead / needs
    re-auth". Any exit code 0 = alive; a code in `dead_exit_codes` = dead;
    anything else (or a failure to execute) = probe-error. This lets any
    credential type (Google OAuth, Vikunja token, GitHub PAT, …) supply its own
    cheap authenticated probe — e.g. `calendar_helper --self-check` for the
    Google calendar credential (exit 0 = ok, 3 = auth-dead).

    When `enabled is True`, `command` (non-empty argv, absolute `command[0]`),
    `dead_exit_codes` (non-empty list of ints), and `recovery_command` MUST be
    set. `timeout_seconds` defaults to 20. Introduced generic in #845 (replacing
    the gog-specific gog_account/keyring_file shape, which had no live subject
    after #819).
    """

    enabled: bool
    command: tuple[str, ...] = ()
    dead_exit_codes: tuple[int, ...] = ()
    recovery_command: Optional[str] = None
    timeout_seconds: int = 20


@dataclass(frozen=True)
class Credential:
    """One well-formed credential entry from the manifest."""

    name: str
    review_cadence: str
    storage: str
    expiry_notes: str
    type: Optional[str] = None
    scope: Optional[str] = None
    used_by: tuple[str, ...] = ()
    expiry_policy: Optional[str] = None
    host: Optional[str] = None
    last_reviewed: Optional[date] = None
    created_date: Optional[date] = None
    expires_at: Optional[date] = None
    liveness_probe: Optional[LivenessProbeConfig] = None


@dataclass(frozen=True)
class ManifestQualityIssue:
    """One credential entry that failed validation."""

    credential_name: str  # or "<index N>" if name itself is missing
    reason: str


def _parse_iso_date(value: object) -> Optional[date]:
    if value is None:
        return None
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _validate_and_construct(
    entry: dict, index: int
) -> tuple[Optional[Credential], Optional[ManifestQualityIssue]]:
    """Return (well_formed, malformed) — exactly one of the two is non-None."""
    raw_name = entry.get("name")
    name = raw_name if isinstance(raw_name, str) and raw_name else None
    fallback_label = name or f"<index {index}>"

    if name is None:
        return None, ManifestQualityIssue(
            credential_name=fallback_label,
            reason="missing or empty 'name' field",
        )

    cadence = entry.get("review_cadence")
    if cadence not in ALLOWED_REVIEW_CADENCES:
        return None, ManifestQualityIssue(
            credential_name=name,
            reason=f"unrecognised review_cadence value: {cadence!r} "
                   f"(allowed: {sorted(ALLOWED_REVIEW_CADENCES)})",
        )

    last_reviewed_raw = entry.get("last_reviewed")
    last_reviewed = _parse_iso_date(last_reviewed_raw)
    if last_reviewed_raw is not None and last_reviewed is None:
        return None, ManifestQualityIssue(
            credential_name=name,
            reason=f"last_reviewed is not a parseable ISO-8601 date: {last_reviewed_raw!r}",
        )

    created_date = _parse_iso_date(entry.get("created_date"))

    # expires_at is the credential's REAL hard-expiry date (#852). It is
    # optional; when present it must be a parseable ISO-8601 date. Unlike
    # last_reviewed it drives no anchor requirement — it only tightens the
    # warning boundary (see cadence.compute_effective_boundary).
    expires_at_raw = entry.get("expires_at")
    expires_at = _parse_iso_date(expires_at_raw)
    if expires_at_raw is not None and expires_at is None:
        return None, ManifestQualityIssue(
            credential_name=name,
            reason=f"expires_at is not a parseable ISO-8601 date: {expires_at_raw!r}",
        )

    if cadence in FIXED_INTERVAL_CADENCES:
        # Need an anchor for boundary computation.
        if last_reviewed is None and created_date is None:
            return None, ManifestQualityIssue(
                credential_name=name,
                reason="missing last_reviewed (and no created_date fallback) for "
                       f"fixed-interval cadence {cadence!r}",
            )

    storage = entry.get("storage")
    if not isinstance(storage, str) or not storage:
        return None, ManifestQualityIssue(
            credential_name=name,
            reason="missing or empty 'storage' field",
        )

    expiry_notes = entry.get("expiry_notes")
    if not isinstance(expiry_notes, str):
        return None, ManifestQualityIssue(
            credential_name=name,
            reason="missing 'expiry_notes' field",
        )

    used_by_raw = entry.get("used_by") or []
    if not isinstance(used_by_raw, list):
        used_by: tuple[str, ...] = ()
    else:
        used_by = tuple(str(x) for x in used_by_raw)

    liveness_probe_raw = entry.get("liveness_probe")
    if liveness_probe_raw is None:
        liveness_probe = None
    else:
        if not isinstance(liveness_probe_raw, dict):
            raise ManifestQualityError(
                f"credential {name!r}: liveness_probe must be an object "
                f"(got {type(liveness_probe_raw).__name__})"
            )
        # Validate unknown subkeys. (The `liveness_probe_removed` breadcrumb is a
        # SIBLING key on the credential entry, not inside this block, so it is
        # untouched here.)
        allowed_keys = {
            "enabled",
            "command",
            "dead_exit_codes",
            "recovery_command",
            "timeout_seconds",
        }
        unknown = set(liveness_probe_raw.keys()) - allowed_keys
        if unknown:
            raise ManifestQualityError(
                f"credential {name!r}: liveness_probe contains "
                f"unknown keys: {sorted(unknown)}"
            )
        enabled = liveness_probe_raw.get("enabled", False)
        if not isinstance(enabled, bool):
            raise ManifestQualityError(
                f"credential {name!r}: liveness_probe.enabled must be a "
                f"boolean (got {type(enabled).__name__})"
            )
        command_raw = liveness_probe_raw.get("command")
        dead_codes_raw = liveness_probe_raw.get("dead_exit_codes")
        recovery_command = liveness_probe_raw.get("recovery_command")
        timeout_raw = liveness_probe_raw.get("timeout_seconds", 20)
        if enabled:
            # command: non-empty list of non-empty strings; command[0] absolute
            # (the probe runs argv with shell=False — an absolute executable
            # avoids PATH ambiguity in the systemd service context).
            if (
                not isinstance(command_raw, list)
                or not command_raw
                or not all(isinstance(x, str) and x for x in command_raw)
            ):
                raise ManifestQualityError(
                    f"credential {name!r}: liveness_probe.command must be a "
                    f"non-empty list of non-empty strings"
                )
            if not command_raw[0].startswith("/"):
                raise ManifestQualityError(
                    f"credential {name!r}: liveness_probe.command[0] must be an "
                    f"absolute executable path (got {command_raw[0]!r})"
                )
            # dead_exit_codes: non-empty list of ints. bool is an int subclass,
            # so reject True/False explicitly.
            if (
                not isinstance(dead_codes_raw, list)
                or not dead_codes_raw
                or not all(
                    isinstance(x, int) and not isinstance(x, bool)
                    for x in dead_codes_raw
                )
            ):
                raise ManifestQualityError(
                    f"credential {name!r}: liveness_probe.dead_exit_codes must "
                    f"be a non-empty list of integers"
                )
            if not recovery_command:
                raise ManifestQualityError(
                    f"credential {name!r}: liveness_probe.enabled is true but "
                    f"'recovery_command' is missing or empty"
                )
            if (
                not isinstance(timeout_raw, int)
                or isinstance(timeout_raw, bool)
                or timeout_raw <= 0
            ):
                raise ManifestQualityError(
                    f"credential {name!r}: liveness_probe.timeout_seconds must "
                    f"be a positive integer (got {timeout_raw!r})"
                )
        liveness_probe = LivenessProbeConfig(
            enabled=enabled,
            command=tuple(command_raw) if isinstance(command_raw, list) else (),
            dead_exit_codes=(
                tuple(dead_codes_raw) if isinstance(dead_codes_raw, list) else ()
            ),
            recovery_command=recovery_command,
            timeout_seconds=(
                timeout_raw
                if isinstance(timeout_raw, int) and not isinstance(timeout_raw, bool)
                else 20
            ),
        )

    cred = Credential(
        name=name,
        review_cadence=cadence,
        storage=storage,
        expiry_notes=expiry_notes,
        type=entry.get("type") if isinstance(entry.get("type"), str) else None,
        scope=entry.get("scope") if isinstance(entry.get("scope"), str) else None,
        used_by=used_by,
        expiry_policy=entry.get("expiry_policy") if isinstance(entry.get("expiry_policy"), str) else None,
        host=entry.get("host") if isinstance(entry.get("host"), str) else None,
        last_reviewed=last_reviewed,
        created_date=created_date,
        expires_at=expires_at,
        liveness_probe=liveness_probe,
    )
    return cred, None


def read_manifest(
    path: str,
) -> tuple[list[Credential], list[ManifestQualityIssue]]:
    """Read and validate the manifest. Returns (well_formed, malformed).

    Raises ManifestUnreadableError when the file cannot be opened or parsed at
    all, or when the top-level shape is wrong (not a dict with a 'credentials'
    list). Per-credential validation failures populate the 'malformed' list.
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError as e:
        raise ManifestUnreadableError(f"Manifest not found: {path}") from e
    except json.JSONDecodeError as e:
        raise ManifestUnreadableError(f"Manifest not valid JSON: {path}: {e}") from e
    except OSError as e:
        raise ManifestUnreadableError(f"Could not read manifest {path}: {e}") from e

    if not isinstance(data, dict):
        raise ManifestUnreadableError(
            f"Manifest top-level is not a dict (got {type(data).__name__}): {path}"
        )
    credentials_raw = data.get("credentials")
    if not isinstance(credentials_raw, list):
        raise ManifestUnreadableError(
            f"Manifest 'credentials' is not a list (got {type(credentials_raw).__name__}): {path}"
        )

    well_formed: list[Credential] = []
    malformed: list[ManifestQualityIssue] = []
    for i, entry in enumerate(credentials_raw):
        if not isinstance(entry, dict):
            malformed.append(
                ManifestQualityIssue(
                    credential_name=f"<index {i}>",
                    reason=f"entry is not a dict (got {type(entry).__name__})",
                )
            )
            continue
        cred, issue = _validate_and_construct(entry, i)
        if cred is not None:
            well_formed.append(cred)
        elif issue is not None:
            malformed.append(issue)
    return well_formed, malformed
