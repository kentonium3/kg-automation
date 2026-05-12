"""Manifest reader: parse credential-manifest.json into Credential records.

See kitty-specs/credential-expiry-health-check-01KRCF92/contracts/manifest-reader.md
for the authoritative contract.
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
