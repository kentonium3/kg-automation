#!/usr/bin/env python3
"""Shared loader for the document-status taxonomy.

`docs/design/standards/allowed-values.json` is the single enforced source for
document frontmatter vocabularies. Two other files describe the same status
vocabulary — `frontmatter.schema.json` and `doc-standards.md` — and both are
*generated* from this one (see `generate_doc_standards.py`). Nothing else may
parse the JSON directly; go through this module, which exposes **every**
vocabulary in the file (`status`, `doc_type`, `level`, `audience`) so no consumer
has a reason to reach past it.

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
from types import MappingProxyType

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
#: Vocabularies whose entries may legitimately be non-string (`level` carries
#: both "1" and 1 today), validated separately from the string vocabularies.
_MIXED_KEYS = ("level",)


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict:
    """`object_pairs_hook` that refuses repeated keys.

    Python's JSON parser is last-value-wins on duplicates, so a file with two
    `status` keys loads silently and the one a human reads first is not the one
    enforced (review finding F2).
    """
    seen: set[str] = set()
    for key, _ in pairs:
        if key in seen:
            raise ValueError(f"duplicate key {key!r}")
        seen.add(key)
    return dict(pairs)


def _reject_constant(name: str) -> object:
    """Refuse NaN/Infinity, which Python accepts but JSON does not define."""
    raise ValueError(f"non-standard JSON constant {name}")


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
        if item != item.strip():
            # "draft " is a distinct value that no document can ever match, and
            # it evades duplicate detection against "draft" (review finding F5).
            raise TaxonomyError(
                f"{source}: '{key}' entry {item!r} has leading or trailing whitespace"
            )
        values.append(item)

    seen: set[str] = set()
    duplicates: set[str] = set()
    for v in values:
        (duplicates if v in seen else seen).add(v)
    if duplicates:
        raise TaxonomyError(
            f"{source}: '{key}' contains duplicate entries: {', '.join(sorted(duplicates))}"
        )

    return tuple(values)


class Taxonomy:
    """Immutable validated view over the taxonomy source.

    Frozen after construction: a caller that could clear ``scoped_statuses``
    could bypass every invariant this module enforces (review finding F6).
    """

    __slots__ = ("default_statuses", "doc_types", "scoped_statuses", "vocabularies", "source")

    def __init__(
        self,
        *,
        default_statuses: tuple[str, ...],
        doc_types: tuple[str, ...],
        scoped_statuses: dict[str, tuple[str, ...]],
        vocabularies: dict[str, tuple],
        source: Path,
    ) -> None:
        object.__setattr__(self, "default_statuses", default_statuses)
        object.__setattr__(self, "doc_types", doc_types)
        object.__setattr__(self, "scoped_statuses", MappingProxyType(dict(scoped_statuses)))
        object.__setattr__(self, "vocabularies", MappingProxyType(dict(vocabularies)))
        object.__setattr__(self, "source", source)

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError(f"{type(self).__name__} is immutable")

    def __delattr__(self, name: str) -> None:
        raise AttributeError(f"{type(self).__name__} is immutable")

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

    def allowed(self, key: str) -> tuple:
        """Permitted values for any ordinary vocabulary (`level`, `audience`, ...).

        Exposed so no consumer needs to parse the source file itself
        (review finding F7).
        """
        try:
            return self.vocabularies[key]
        except KeyError:
            raise TaxonomyError(f"{self.source}: no vocabulary named {key!r}") from None


def load_taxonomy(path: Path | str | None = None) -> Taxonomy:
    """Load and validate the taxonomy. Raises ``TaxonomyError`` on any defect."""
    source = Path(path) if path is not None else DEFAULT_TAXONOMY_PATH

    try:
        text = source.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise TaxonomyError(f"{source}: taxonomy source not found") from exc
    except UnicodeError as exc:
        # UnicodeDecodeError is a ValueError, not an OSError, so it would
        # otherwise escape as a raw decode error (review finding F4).
        raise TaxonomyError(f"{source}: taxonomy source is not valid UTF-8: {exc}") from exc
    except OSError as exc:
        raise TaxonomyError(f"{source}: cannot read taxonomy source: {exc}") from exc

    try:
        data = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_constant,
        )
    except json.JSONDecodeError as exc:
        raise TaxonomyError(f"{source}: invalid JSON at line {exc.lineno}: {exc.msg}") from exc
    except ValueError as exc:  # raised by the two hooks above
        raise TaxonomyError(f"{source}: invalid JSON: {exc}") from exc

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

    # Every other top-level list is an ordinary vocabulary. `level` carries
    # mixed str/int entries today, so it is validated for shape only.
    vocabularies: dict[str, tuple] = {_DEFAULT_KEY: default_statuses, _DOC_TYPE_KEY: doc_types}
    for key, raw in data.items():
        if key in (_DEFAULT_KEY, _DOC_TYPE_KEY, _SCOPED_KEY):
            continue
        if not isinstance(raw, list):
            raise TaxonomyError(f"{source}: '{key}' must be a list, got {type(raw).__name__}")
        if not raw:
            raise TaxonomyError(f"{source}: '{key}' must not be empty")
        if key in _MIXED_KEYS:
            vocabularies[key] = tuple(raw)
        else:
            vocabularies[key] = _require_vocabulary(raw, key=key, source=source)

    return Taxonomy(
        default_statuses=default_statuses,
        doc_types=doc_types,
        scoped_statuses=scoped,
        vocabularies=vocabularies,
        source=source,
    )
