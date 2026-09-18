#!/usr/bin/env python3
"""Shared loader for the document-status taxonomy.

`docs/design/standards/allowed-values.json` is the single enforced source for
document frontmatter vocabularies. Two other files describe the same status
vocabulary — `frontmatter.schema.json` and `doc-standards.md` — and both are
*generated* from this one (see `generate_doc_standards.py`). Nothing else may
parse the JSON directly; go through this module.

**Fail-closed by design.** Every malformed shape raises `TaxonomyError`. The
previous behaviour — warn on malformed JSON and continue on built-in fallback
values — is deliberately removed: once this file is authoritative, silently
substituting different rules than the ones on disk means the repo is enforcing
a contract nobody can read. See kentonium3/kg-automation#987 (FR-005) and the
post-plan review finding #7.
"""

from __future__ import annotations

import json
from pathlib import Path

__all__ = ["TaxonomyError", "Taxonomy", "load_taxonomy", "DEFAULT_TAXONOMY_PATH"]

DEFAULT_TAXONOMY_PATH = (
    Path(__file__).resolve().parents[2] / "docs" / "design" / "standards" / "allowed-values.json"
)

#: Key holding the status set applied to any doc_type without an override.
_DEFAULT_KEY = "status"
#: Key holding per-doc_type status overrides.
_SCOPED_KEY = "status_by_doc_type"
#: Key holding the permitted doc_type vocabulary.
_DOC_TYPE_KEY = "doc_type"


class TaxonomyError(Exception):
    """The taxonomy source is missing, unreadable, or structurally invalid."""


def _require_vocabulary(raw: object, *, key: str, source: Path) -> tuple[str, ...]:
    """Return ``raw`` as a validated vocabulary tuple, or raise.

    A vocabulary must be a non-empty list of unique, non-blank strings. Anything
    else is a defect in the source file, not something to work around.
    """
    if not isinstance(raw, list):
        raise TaxonomyError(f"{source}: '{key}' must be a list, got {type(raw).__name__}")
    if not raw:
        raise TaxonomyError(f"{source}: '{key}' must not be empty")

    values: list[str] = []
    for item in raw:
        # int/bool entries have appeared in this file before (the `level` key
        # carries both "1" and 1), so type-check every element rather than the
        # list as a whole.
        if not isinstance(item, str):
            raise TaxonomyError(
                f"{source}: '{key}' contains a non-string entry {item!r} ({type(item).__name__})"
            )
        if not item.strip():
            raise TaxonomyError(f"{source}: '{key}' contains a blank entry")
        values.append(item)

    duplicates = sorted({v for v in values if values.count(v) > 1})
    if duplicates:
        raise TaxonomyError(f"{source}: '{key}' contains duplicate entries: {', '.join(duplicates)}")

    return tuple(values)


class Taxonomy:
    """Validated view over the taxonomy source."""

    def __init__(
        self,
        *,
        default_statuses: tuple[str, ...],
        doc_types: tuple[str, ...],
        scoped_statuses: dict[str, tuple[str, ...]],
        source: Path,
    ) -> None:
        self.default_statuses = default_statuses
        self.doc_types = doc_types
        self.scoped_statuses = scoped_statuses
        self.source = source

    def statuses_for(self, doc_type: str | None) -> tuple[str, ...]:
        """Permitted statuses for ``doc_type``.

        An unknown or absent doc_type falls back to the default set. Validating
        the doc_type itself is a separate check with its own error message —
        reporting it here would blame the status field for a doc_type defect.
        """
        if doc_type is None:
            return self.default_statuses
        return self.scoped_statuses.get(doc_type, self.default_statuses)

    def is_scoped(self, doc_type: str | None) -> bool:
        """True when ``doc_type`` has its own status set rather than the default."""
        return doc_type is not None and doc_type in self.scoped_statuses


def load_taxonomy(path: Path | str | None = None) -> Taxonomy:
    """Load and validate the taxonomy. Raises ``TaxonomyError`` on any defect."""
    source = Path(path) if path is not None else DEFAULT_TAXONOMY_PATH

    try:
        text = source.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise TaxonomyError(f"{source}: taxonomy source not found") from exc
    except OSError as exc:
        raise TaxonomyError(f"{source}: cannot read taxonomy source: {exc}") from exc

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise TaxonomyError(f"{source}: invalid JSON at line {exc.lineno}: {exc.msg}") from exc

    if not isinstance(data, dict):
        raise TaxonomyError(f"{source}: top level must be an object, got {type(data).__name__}")

    for key in (_DEFAULT_KEY, _DOC_TYPE_KEY):
        if key not in data:
            raise TaxonomyError(f"{source}: required key '{key}' is missing")

    default_statuses = _require_vocabulary(data[_DEFAULT_KEY], key=_DEFAULT_KEY, source=source)
    doc_types = _require_vocabulary(data[_DOC_TYPE_KEY], key=_DOC_TYPE_KEY, source=source)

    scoped_raw = data.get(_SCOPED_KEY, {})
    if not isinstance(scoped_raw, dict):
        raise TaxonomyError(
            f"{source}: '{_SCOPED_KEY}' must be an object, got {type(scoped_raw).__name__}"
        )

    scoped: dict[str, tuple[str, ...]] = {}
    for doc_type, statuses in scoped_raw.items():
        if doc_type not in doc_types:
            # A scope keyed on an unknown doc_type can never match a real
            # document, so it is silently dead config — exactly the class of
            # drift this module exists to prevent.
            raise TaxonomyError(
                f"{source}: '{_SCOPED_KEY}' key {doc_type!r} is not a permitted doc_type"
            )
        scoped[doc_type] = _require_vocabulary(
            statuses, key=f"{_SCOPED_KEY}.{doc_type}", source=source
        )

    return Taxonomy(
        default_statuses=default_statuses,
        doc_types=doc_types,
        scoped_statuses=scoped,
        source=source,
    )
