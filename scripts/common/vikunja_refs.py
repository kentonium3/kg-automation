"""Declared Vikunja reference registry + typed fail-loud accessor (WP01,
mission ``vikunja-reference-seam-01KXK68Z``, kentonium3/kg-automation#748/#745).

This module is the **single source of truth** that resolves logical Vikunja
project/label names (``"inbox"``, ``"habits"``, ``"felix:ignore"`` …) to their
concrete live identities. It is the foundation every other WP in the seam
imports.

Two hard contracts (see
``kitty-specs/vikunja-reference-seam-01KXK68Z/contracts/vikunja-refs.contract.md``
and ``data-model.md``):

- **Zero network I/O (NFR-001).** Every accessor reads only a memoized, pure
  file/JSON load of ``vikunja_refs.json`` (resolved relative to this module).
  The import graph is free of ``vikunja_client`` / ``requests`` / ``urllib`` —
  loading is stdlib file + JSON only (NFR-003).
- **Fail-loud (FR-003/FR-009).** Resolution NEVER returns ``None``/``0``/empty
  to signal "not found". Every failure raises :class:`VikunjaRefError` with a
  message naming the logical name and the reason, so a caller log is
  actionable (this is the #743 regression guard: a deleted or unprovisioned
  reference fails loud, never silently mis-routes). Three distinct failure
  classes are surfaced with distinct messages:

  1. **undeclared** — the logical name is not in the registry;
  2. **wrong accessor** — a ``project_id`` selector queried via a label
     accessor (or vice versa);
  3. **declared but unprovisioned** — the ref is declared with ``value: null``
     (the identity does not yet exist live).

The registry preserves a ``{kind, value}`` *selector* shape rather than a bare
int so an identity can migrate representation (e.g. Habits moving from
``project_id: 13`` to ``label: "t:habit"`` under #717/FR-008) without touching
consumers.

Per Felix Constitution Directive 6 / ``docs/design/helper-script-conventions.md``
this is a library-tier module: pure, importable, no I/O on the hot path, typed
errors.

Public surface
--------------
Exceptions: ``VikunjaRefError``, ``VikunjaRefUnprovisioned``
Functions: ``project_id``, ``project_title``, ``selector``, ``label_id``,
    ``private_project_ids``, ``declared_projects``, ``declared_labels``
Test seam: ``set_registry_for_test`` (inject an in-memory registry; never
    used on the runtime path).
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

__all__ = [
    "VikunjaRefError",
    "VikunjaRefUnprovisioned",
    "project_id",
    "project_title",
    "selector",
    "label_id",
    "private_project_ids",
    "declared_projects",
    "declared_labels",
    "set_registry_for_test",
]

#: The registry data file, resolved relative to this module (never the CWD).
_REGISTRY_PATH = Path(__file__).with_name("vikunja_refs.json")

#: Valid selector kinds. A project identity may be represented by either a
#: ``project_id`` or (post-#717) a ``label`` selector; a label ref is always a
#: ``label`` selector.
_VALID_SELECTOR_KINDS = frozenset({"project_id", "label"})

_REQUIRED_TOP_LEVEL_KEYS = frozenset(
    {
        "schema_version",
        "source_of_truth",
        "last_verified_utc",
        "projects",
        "labels",
        "private_projects",
    }
)

#: Memoized normalized registry (populated lazily on first accessor call).
_CACHED_REGISTRY: dict[str, Any] | None = None

#: Test-injected override. When not ``None`` it short-circuits the file load
#: entirely — the runtime path never sets this.
_TEST_OVERRIDE: dict[str, Any] | None = None


class VikunjaRefError(Exception):
    """The single typed failure surface for Vikunja reference resolution.

    Raised for an undeclared logical name, a wrong-accessor selector-kind
    mismatch, a declared-but-unprovisioned ref (``value: null``), an
    owner-token mismatch on a label, or a malformed registry at load time.
    Resolution never returns ``None``/``0``/empty to signal failure — it
    raises this instead (FR-003).
    """


class VikunjaRefUnprovisioned(VikunjaRefError):
    """A declared reference that has no live identity yet (``value: null``).

    Raised by :func:`project_id` / :func:`label_id` for a ref that IS declared
    in the registry but is not yet provisioned in Vikunja. This is a **subclass**
    of :class:`VikunjaRefError`, so every ``except VikunjaRefError`` (and every
    existing test) still catches it — backward-compatible. The distinct type
    lets a downstream consumer (e.g. the WP04 sync classifier) treat an
    *unprovisioned* ref as "skip this feature gracefully" while a genuinely
    *broken* reference (undeclared, wrong-kind, wrong-owner, or an invalid
    provisioned id) still surfaces as a plain :class:`VikunjaRefError` and
    fails loud.
    """


# ---------------------------------------------------------------------------
# Loading + memoization + injectable seam (T002)
# ---------------------------------------------------------------------------


def _require_str(container: Any, key: str, ctx: str) -> str:
    if not isinstance(container, dict):
        raise VikunjaRefError(f"{ctx} entry must be a JSON object")
    value = container.get(key)
    if not isinstance(value, str):
        raise VikunjaRefError(f"{ctx} is missing required string field {key!r}")
    return value


def _require_list(value: Any, ctx: str) -> list[Any]:
    if not isinstance(value, list):
        raise VikunjaRefError(f"Registry field {ctx!r} must be a list")
    return value


def _normalize_selector(entry: dict[str, Any], name: str, ref_kind: str) -> dict[str, Any]:
    sel = entry.get("selector")
    if not isinstance(sel, dict):
        raise VikunjaRefError(f"{ref_kind} {name!r} is missing a 'selector' object")
    kind = sel.get("kind")
    if kind not in _VALID_SELECTOR_KINDS:
        raise VikunjaRefError(
            f"{ref_kind} {name!r} selector kind {kind!r} is invalid; "
            f"expected one of {sorted(_VALID_SELECTOR_KINDS)}"
        )
    if "value" not in sel:
        raise VikunjaRefError(f"{ref_kind} {name!r} selector is missing 'value'")
    value = sel["value"]
    if isinstance(value, bool) or (value is not None and not isinstance(value, (int, str))):
        raise VikunjaRefError(
            f"{ref_kind} {name!r} selector value must be an int, str, or null; "
            f"got {type(value).__name__}"
        )
    return {"kind": kind, "value": value}


def _normalize(raw: Any) -> dict[str, Any]:
    """Validate + normalize a raw registry mapping into fast-lookup form.

    Fail-loud at load (not at call): a malformed registry raises
    :class:`VikunjaRefError` here so an operator sees the problem immediately.
    """
    if not isinstance(raw, dict):
        raise VikunjaRefError("Vikunja reference registry must be a JSON object")
    missing = _REQUIRED_TOP_LEVEL_KEYS - raw.keys()
    if missing:
        raise VikunjaRefError(
            f"Vikunja reference registry is missing required top-level keys: {sorted(missing)}"
        )

    projects_by_name: dict[str, dict[str, Any]] = {}
    for entry in _require_list(raw["projects"], "projects"):
        name = _require_str(entry, "name", "project")
        if name in projects_by_name:
            raise VikunjaRefError(f"Duplicate project name {name!r} in registry")
        sel = _normalize_selector(entry, name, "project")
        title = _require_str(entry, "title", f"project {name!r}")
        owner = _require_str(entry, "owner", f"project {name!r}")
        provisioned = entry.get("provisioned", True)
        if not isinstance(provisioned, bool):
            raise VikunjaRefError(f"project {name!r} 'provisioned' must be a bool")
        projects_by_name[name] = {
            "selector": sel,
            "title": title,
            "owner": owner,
            "provisioned": provisioned,
        }

    labels_by_name: dict[str, dict[str, Any]] = {}
    for entry in _require_list(raw["labels"], "labels"):
        name = _require_str(entry, "name", "label")
        if name in labels_by_name:
            raise VikunjaRefError(f"Duplicate label name {name!r} in registry")
        sel = _normalize_selector(entry, name, "label")
        if sel["kind"] != "label":
            raise VikunjaRefError(
                f"label {name!r} selector kind must be 'label', got {sel['kind']!r}"
            )
        title = _require_str(entry, "title", f"label {name!r}")
        owner_token = _require_str(entry, "owner_token", f"label {name!r}")
        labels_by_name[name] = {
            "selector": sel,
            "title": title,
            "owner_token": owner_token,
        }

    private_names: list[str] = []
    for item in _require_list(raw["private_projects"], "private_projects"):
        if not isinstance(item, str):
            raise VikunjaRefError(
                "private_projects entries must be strings (logical project names)"
            )
        private_names.append(item)

    return {
        "schema_version": raw["schema_version"],
        "source_of_truth": raw["source_of_truth"],
        "last_verified_utc": raw["last_verified_utc"],
        "projects_by_name": projects_by_name,
        "labels_by_name": labels_by_name,
        "private_projects": private_names,
    }


def _load_registry_file(path: Path = _REGISTRY_PATH) -> dict[str, Any]:
    """Read, parse, and normalize the registry JSON. File + JSON only — no
    network, no ``vikunja_client``.
    """
    try:
        raw_text = path.read_text(encoding="utf-8")
    except OSError as exc:  # pragma: no cover - defensive; file ships with module
        raise VikunjaRefError(
            f"Cannot read Vikunja reference registry at {path}: {exc}"
        ) from exc
    try:
        raw = json.loads(raw_text)
    except json.JSONDecodeError as exc:  # pragma: no cover - defensive
        raise VikunjaRefError(
            f"Malformed Vikunja reference registry JSON at {path}: {exc}"
        ) from exc
    return _normalize(raw)


def _get_registry() -> dict[str, Any]:
    """Return the memoized normalized registry.

    A test override (if installed) short-circuits the file load entirely, so
    unit tests never read the real file and never touch the network.
    """
    global _CACHED_REGISTRY
    if _TEST_OVERRIDE is not None:
        return _TEST_OVERRIDE
    if _CACHED_REGISTRY is None:
        _CACHED_REGISTRY = _load_registry_file()
    return _CACHED_REGISTRY


def set_registry_for_test(raw: dict[str, Any] | None) -> None:
    """Inject an in-memory registry for unit tests (bypasses file + network).

    Pass a raw registry mapping (same shape as ``vikunja_refs.json``) to
    install it as the override; the mapping is validated/normalized exactly as
    the file loader would validate it. Pass ``None`` to clear the override and
    restore file-backed loading. Either call also resets the file cache so no
    stale state leaks across tests. **Not** part of the runtime surface.
    """
    global _TEST_OVERRIDE, _CACHED_REGISTRY
    _TEST_OVERRIDE = None if raw is None else _normalize(raw)
    _CACHED_REGISTRY = None


# ---------------------------------------------------------------------------
# Project accessors (T003)
# ---------------------------------------------------------------------------


def _require_positive_int_id(value: Any, name: str, ref_kind: str) -> int:
    """Return ``value`` if it is a positive integer id, else fail loud.

    A provisioned selector value must be a real Vikunja id: a plain ``int``
    (never ``bool``) strictly greater than zero. ``0`` is the forbidden
    "falsy sentinel" a fail-loud accessor must never return, and a
    non-numeric registry value (e.g. a string) must not leak a raw
    ``ValueError`` from ``int(...)``. Both become :class:`VikunjaRefError`
    naming the logical ``name`` (FR-003).

    This is deliberately *distinct* from the "declared but unprovisioned"
    (``value: null``) failure, which the callers check first with its own
    message — the two are not conflated.
    """
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise VikunjaRefError(
            f"{ref_kind} reference {name!r} has an invalid id value {value!r} "
            f"(type {type(value).__name__}); a provisioned id must be a "
            f"positive integer"
        )
    return value


def _project_entry(name: str) -> dict[str, Any]:
    entry = _get_registry()["projects_by_name"].get(name)
    if entry is None:
        raise VikunjaRefError(
            f"Undeclared project reference {name!r}: not in the Vikunja reference "
            f"registry ({_REGISTRY_PATH.name})"
        )
    return entry


def project_id(name: str) -> int:
    """Resolve a logical project ``name`` to its pinned integer id.

    Raises :class:`VikunjaRefError` if ``name`` is undeclared or if its selector
    is a ``label`` (wrong accessor for a label selector). Raises
    :class:`VikunjaRefUnprovisioned` (a ``VikunjaRefError`` subclass) if it is
    declared-but-unprovisioned (``value: null``, FR-009), so a consumer can skip
    an unprovisioned feature gracefully while a broken reference still fails
    loud. Never returns ``None``/``0`` to signal absence.
    """
    entry = _project_entry(name)
    sel = entry["selector"]
    if sel["kind"] != "project_id":
        raise VikunjaRefError(
            f"Project reference {name!r} has a {sel['kind']!r} selector, not "
            f"'project_id'; use the accessor that matches its kind"
        )
    if not entry["provisioned"] or sel["value"] is None:
        raise VikunjaRefUnprovisioned(
            f"Project reference {name!r} is declared but unprovisioned "
            f"(value is null); it has no live Vikunja id yet"
        )
    return _require_positive_int_id(sel["value"], name, "Project")


def project_title(name: str) -> str:
    """Return the declared human title for a logical project ``name``.

    Used by the validator/reporting layer (drift detection). Raises
    :class:`VikunjaRefError` if ``name`` is undeclared. The title is declared
    regardless of provisioning, so this does not raise on an unprovisioned ref.
    """
    return _project_entry(name)["title"]


def selector(name: str) -> dict[str, Any]:
    """Return a copy of the raw ``{kind, value}`` selector for a project ``name``.

    For the ``vikunja_scope`` selector layer and any consumer that dispatches
    on ``kind`` (e.g. a future label-based habit identity). Returns a fresh
    copy so callers cannot mutate module state. Raises
    :class:`VikunjaRefError` if ``name`` is undeclared.
    """
    return dict(_project_entry(name)["selector"])


# ---------------------------------------------------------------------------
# Label + private-project accessors (T004)
# ---------------------------------------------------------------------------


def label_id(name: str, owner_token: str) -> int:
    """Resolve a label ``name`` to its pinned id within ``owner_token``'s namespace.

    Labels are per-token (#715): the id is only valid inside the namespace of
    the token that owns it. Raises :class:`VikunjaRefError` if ``name`` is
    undeclared or if ``owner_token`` does not match the declared owning token.
    Raises :class:`VikunjaRefUnprovisioned` (a ``VikunjaRefError`` subclass) if
    the label is declared-but-unprovisioned (``value: null``) for that token, so
    a consumer can skip an unprovisioned label gracefully while a broken
    reference still fails loud.
    """
    entry = _get_registry()["labels_by_name"].get(name)
    if entry is None:
        raise VikunjaRefError(
            f"Undeclared label reference {name!r}: not in the Vikunja reference "
            f"registry ({_REGISTRY_PATH.name})"
        )
    declared_owner = entry["owner_token"]
    if declared_owner != owner_token:
        raise VikunjaRefError(
            f"Label {name!r} is owned by token {declared_owner!r}, not "
            f"{owner_token!r}; label ids are per-token (#715)"
        )
    value = entry["selector"]["value"]
    if value is None:
        raise VikunjaRefUnprovisioned(
            f"Label {name!r} is declared but unprovisioned for token "
            f"{owner_token!r} (value is null); it has no live Vikunja id yet"
        )
    return _require_positive_int_id(value, name, "Label")


def private_project_ids() -> frozenset[int]:
    """Resolve the ``private_projects`` logical names to a frozenset of ids.

    Each listed name is resolved via :func:`project_id`, so a listed name that
    is undeclared or unprovisioned raises :class:`VikunjaRefError` (fail-loud).
    Returns an empty frozenset when the list is empty (the case today —
    finding #4: the mechanism lives here for when a private project exists).
    """
    names = _get_registry()["private_projects"]
    return frozenset(project_id(name) for name in names)


# ---------------------------------------------------------------------------
# Enumeration accessors — public "list what's declared" front door
# ---------------------------------------------------------------------------


def declared_projects() -> list[dict[str, Any]]:
    """Return every declared project entry as a list of deep-copied dicts.

    The public front door for the validator (WP02) and any consumer that needs
    to enumerate declared refs without reaching for the private ``_get_registry``
    loader. Each dict carries the logical ``name`` plus the declared
    ``selector`` (a ``{kind, value}`` copy), ``title``, ``owner``, and
    ``provisioned`` flag. Entries are **deep copies**, so a caller may freely
    read or mutate the returned list/dicts without affecting module state or a
    subsequent call. Network-free, memoized-load-backed like the other accessors.
    """
    projects = _get_registry()["projects_by_name"]
    return [{"name": name, **copy.deepcopy(entry)} for name, entry in projects.items()]


def declared_labels() -> list[dict[str, Any]]:
    """Return every declared label entry as a list of deep-copied dicts.

    Companion to :func:`declared_projects`. Each dict carries the logical
    ``name`` plus the declared ``selector`` (a ``{kind, value}`` copy),
    ``title``, and ``owner_token``. Entries are **deep copies**, so a caller may
    freely read or mutate the returned list/dicts without affecting module state
    or a subsequent call. Network-free, memoized-load-backed like the other
    accessors.
    """
    labels = _get_registry()["labels_by_name"]
    return [{"name": name, **copy.deepcopy(entry)} for name, entry in labels.items()]
