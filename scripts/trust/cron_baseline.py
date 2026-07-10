"""Approved-cron baseline loader (WP02, felix-truthful-reporting-01KX6MN5).

Loads and validates the committed allowlist of legitimate OpenClaw crons
(``docs/design/architecture/data/approved-crons.json``) into typed
``ApprovedCron`` value objects, and exposes a deterministic, order-independent
content hash (:func:`baseline_hash`) that WP04 folds into finding
fingerprints so a baseline edit re-evaluates findings rather than letting
stale seen-state suppress them (data-model.md "State & idempotency").

Fail-safe posture (NFR-001): a missing, unreadable, or malformed baseline
raises :class:`BaselineError` — it never silently degrades to an empty
list. An empty ``crons`` list is not a valid state for this repo's baseline
(the repo always has at least the 7 seeded crons), but more importantly the
caller must be able to distinguish "no baseline could be loaded" from "the
baseline says there are no crons" (see contract C1 / C3 in
``kitty-specs/felix-truthful-reporting-01KX6MN5/contracts/detector-cli.md``).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, fields
from pathlib import Path

# Default location of the committed baseline (canonical operational-state
# JSON per repo convention — docs/design/architecture/data/).
DEFAULT_BASELINE_PATH = Path("docs/design/architecture/data/approved-crons.json")

# The exact set of required, non-empty string fields on every baseline entry.
# NOTE: ``tz`` is intentionally NOT required — the live OpenClaw payload omits
# ``schedule.tz`` for crons that run in the host's default timezone, so the
# baseline must be able to record an empty tz to match (a non-empty sentinel
# like "Etc/UTC" would produce a spurious ``schedule_mismatch`` — caught at the
# #683 deploy). ``tz`` is read separately below and defaults to "".
_REQUIRED_ENTRY_FIELDS = (
    "name",
    "agent_id",
    "schedule_expr",
    "purpose",
    "approved_by",
    "approved_at",
)


class BaselineError(Exception):
    """Raised when the approved-cron baseline is missing or malformed.

    Deliberately distinct from a plain ``ValueError``/``OSError`` so callers
    can catch precisely this failure mode and fail safe (NFR-001): a
    ``BaselineError`` must never be interpreted as "there are no approved
    crons" — that would silently suppress every live cron as
    ``unapproved_present``.
    """


@dataclass(frozen=True)
class ApprovedCron:
    """One entry in the committed approved-cron baseline (data-model.md).

    Mirrors the JSON schema of ``approved-crons.json`` exactly — field names
    are the same on both sides so no renaming/mapping step can silently drop
    or mismatch a value.
    """

    name: str
    agent_id: str
    schedule_expr: str
    tz: str
    purpose: str
    approved_by: str
    approved_at: str


def _fail(message: str) -> "BaselineError":
    return BaselineError(message)


def load_baseline(path: Path | str = DEFAULT_BASELINE_PATH) -> list[ApprovedCron]:
    """Load, validate, and return the approved-cron baseline.

    Raises :class:`BaselineError` on any of: missing file, invalid JSON,
    missing/malformed top-level shape (``schema_version`` + ``crons`` list),
    a missing/blank required field on any entry, or a duplicate ``name``
    (the uniqueness invariant in data-model.md). Never returns an empty list
    as a substitute for a real failure — a genuinely empty ``crons: []``
    baseline (if one ever existed) would return ``[]`` cleanly, but a
    *broken* baseline always raises.
    """
    path = Path(path)

    try:
        raw_text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise _fail(f"approved-cron baseline not found: {path}") from exc
    except OSError as exc:
        raise _fail(f"approved-cron baseline unreadable: {path} ({exc})") from exc

    try:
        document = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise _fail(f"approved-cron baseline is not valid JSON: {path} ({exc})") from exc

    if not isinstance(document, dict):
        raise _fail(f"approved-cron baseline must be a JSON object: {path}")
    if "schema_version" not in document:
        raise _fail(f"approved-cron baseline missing 'schema_version': {path}")

    crons_raw = document.get("crons")
    if not isinstance(crons_raw, list):
        raise _fail(f"approved-cron baseline 'crons' must be a list: {path}")

    entries: list[ApprovedCron] = []
    seen_names: set[str] = set()
    for index, entry in enumerate(crons_raw):
        if not isinstance(entry, dict):
            raise _fail(f"approved-cron baseline entry {index} is not an object")

        values: dict[str, str] = {}
        for field_name in _REQUIRED_ENTRY_FIELDS:
            value = entry.get(field_name)
            if not isinstance(value, str) or not value.strip():
                raise _fail(
                    f"approved-cron baseline entry {index} missing/blank "
                    f"required field {field_name!r}"
                )
            values[field_name] = value

        # tz is optional: an absent or non-string tz normalizes to "" (the host
        # default-timezone case, matching a live payload that omits schedule.tz).
        tz_value = entry.get("tz")
        values["tz"] = tz_value if isinstance(tz_value, str) else ""

        name = values["name"]
        if name in seen_names:
            raise _fail(f"approved-cron baseline has duplicate name: {name!r}")
        seen_names.add(name)

        entries.append(ApprovedCron(**values))

    return entries


def baseline_hash(entries: list[ApprovedCron]) -> str:
    """Return a deterministic, order-independent content hash of ``entries``.

    Used by WP04 to fold into finding fingerprints so a baseline edit
    invalidates stale seen-state rather than letting it suppress a
    now-legitimate (or newly-illegitimate) cron finding (data-model.md
    "State & idempotency", "Baseline-versioned fingerprints").

    Order-independence is achieved by sorting entries on their canonical
    tuple representation before serializing, so reordering the ``crons``
    array in the JSON file does not change the hash; changing any field
    value does.
    """
    field_names = [f.name for f in fields(ApprovedCron)]
    canonical = sorted(
        [{name: getattr(entry, name) for name in field_names} for entry in entries],
        key=lambda d: tuple(d[name] for name in field_names),
    )
    canonical_json = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


__all__ = [
    "ApprovedCron",
    "BaselineError",
    "DEFAULT_BASELINE_PATH",
    "baseline_hash",
    "load_baseline",
]
