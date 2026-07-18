"""Deterministic compact-shorthand parser + seam-backed token resolution.

Mission ``task-intake-validation-loop-01KXS06W`` WP03 (FR-005/FR-006, NFR-002).

Kent answers the intake digest with a **compact-shorthand** reply — one line per
task, keyed by the digest number, supplying only the fields the digest reported
missing. This module turns each line into a structured :class:`ParsedLine` and
resolves its tokens to **canonical Vikunja names** (project logical names and
``f:``/``q:``/``loe:``/``t:habit`` label names) using a fixed alias table and the
#748 reference seam (:mod:`scripts.common.vikunja_refs`).

Two hard design constraints (Felix Constitution Directive 6):

- **No LLM in this module.** Resolution is purely deterministic: an alias table
  plus the seam's declared-name enumeration. The LLM is a *fallback* the apply
  engine (WP04) invokes out-of-band; its only channel back in is
  :func:`resolve_with_fallback`, which re-resolves a proposed **canonical name**
  through the seam and rejects any raw id / free-form value. The LLM can never
  inject an id.
- **Never hardcode ids.** The alias table maps token → canonical *name* (a
  string); every id ultimately comes from ``vikunja_refs`` at write time (WP04).
  This module stores names, not ids, so a migration of a name→id mapping in the
  registry never touches this code.

Grammar (deterministic, sparse — FR-005). Every token after ``<n>`` is optional::

    <n> [project-token] [f<1-4>] [quadrant-token] [due:<date>] [habit] [loe:<s|m|l>]

Lines are independent; a malformed token is *captured* in
:attr:`ParsedLine.unresolved_tokens`, never fatal (FR-012 echo-back).

Public surface
--------------
Data: :class:`ParsedLine`
Parsing: :func:`parse_line`, :func:`resolve_line`, :func:`parse_reply`
Fallback: :func:`resolve_with_fallback`, :exc:`FallbackItemError`
Alias tables: :data:`FRICTION_ALIASES`, :data:`QUADRANT_ALIASES`,
    :data:`LOE_ALIASES`, :data:`PROJECT_ALIASES`, :data:`HABIT_TOKENS`
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from scripts.common import vikunja_refs

__all__ = [
    "ParsedLine",
    "FallbackItemError",
    "parse_line",
    "resolve_line",
    "parse_reply",
    "resolve_with_fallback",
    "FRICTION_ALIASES",
    "QUADRANT_ALIASES",
    "LOE_ALIASES",
    "PROJECT_ALIASES",
    "HABIT_TOKENS",
]

# ---------------------------------------------------------------------------
# Alias tables (seed; the documented taxonomy NFR-002 measures for 100% cover)
# ---------------------------------------------------------------------------
# Each table maps a documented token (matched case-insensitively) to a canonical
# Vikunja *name* — never an id. Friction/quadrant/loe canonicalize to the label
# names declared in the seam registry; project short-names canonicalize to the
# logical project names the seam declares.

#: Friction shorthand ``f1``–``f4`` → canonical ``f:*`` label names.
FRICTION_ALIASES: dict[str, str] = {
    "f1": "f:1-flow",
    "f2": "f:2-growth",
    "f3": "f:3-edge",
    "f4": "f:4-overload",
}

#: Eisenhower quadrant tokens (and their short forms) → canonical ``q:*`` names.
QUADRANT_ALIASES: dict[str, str] = {
    "do": "q:do",
    "sched": "q:schedule",
    "schedule": "q:schedule",
    "deleg": "q:delegate",
    "delegate": "q:delegate",
    "elim": "q:eliminate",
    "eliminate": "q:eliminate",
}

#: Level-of-effort tokens → canonical ``loe:*`` label names.
LOE_ALIASES: dict[str, str] = {
    "loe:s": "loe:s",
    "loe:m": "loe:m",
    "loe:l": "loe:l",
}

#: Documented project short-names → canonical logical project names. The values
#: are the names the #748 seam registry declares (snake_case for multi-word
#: projects). Provisioning of any given name is the seam's responsibility — an
#: alias hit resolves deterministically here regardless (that is what makes the
#: LLM a true fallback under NFR-002).
PROJECT_ALIASES: dict[str, str] = {
    "personal": "personal",
    "felix": "felix_kg_automation",
    "clients": "clients",
    "pointerhealth": "pointerhealth",
    "spec-kitty": "spec_kitty",
    "spec_kitty": "spec_kitty",
    "intentional": "intentional",
    "habits": "habits",
}

#: Literal tokens that request the ``t:habit`` type label.
HABIT_TOKENS: frozenset[str] = frozenset({"habit", "t:habit"})

#: The strict, exhaustive key set of a constrained fallback item (FR-006).
_FALLBACK_ITEM_KEYS: frozenset[str] = frozenset(
    {"line", "token", "position", "canonical_name"}
)

_INT_RE = re.compile(r"^\d+$")

#: Leading digest-number token, tolerant of the punctuation the digest itself
#: prints ("1. Title") and other common list forms — ``1``, ``1.``, ``1)``,
#: ``1:`` all mean digest number 1 (#758). Only the LEADING token; does not relax
#: :data:`_INT_RE` (which still rejects raw ids in the fallback path).
_LEADING_NUM_RE = re.compile(r"^(\d+)[.):]?$")
#: An ``f`` followed by digits that is *not* a valid ``f1``–``f4`` — a malformed
#: friction token (e.g. ``f5``, ``f0``) that must be captured, not treated as a
#: project candidate.
_FRICTION_SHAPE_RE = re.compile(r"^f\d+$")


class FallbackItemError(ValueError):
    """A constrained-fallback item violated the ``{line, token, position,
    canonical_name}`` contract (extra/missing key or wrong scalar type).

    Raised by :func:`resolve_with_fallback` so a malformed fallback payload
    fails loud rather than silently smuggling an unexpected field (the
    Directive-6 leak guard).
    """


@dataclass
class ParsedLine:
    """One parsed compact-shorthand reply line.

    After :func:`parse_line` the fixed-vocabulary fields (``friction``,
    ``quadrant``, ``loe``, ``habit``) already hold canonical values, ``due``
    holds the raw date string (Tier-2/WP04 normalizes it), and ``project`` holds
    the **raw** project-candidate token. After :func:`resolve_line` (or via
    :func:`parse_reply`) ``project`` holds the canonical project name, or is
    ``None`` with the raw token moved to :attr:`unresolved_tokens`.

    ``unresolved_tokens`` collects every token that could not be resolved
    (malformed, unknown, or a duplicate field) so the caller can echo it back
    (FR-012). A malformed token never aborts the line.
    """

    n: int | None = None
    project: str | None = None
    friction: str | None = None
    quadrant: str | None = None
    due: str | None = None
    habit: bool = False
    loe: str | None = None
    raw: str = ""
    unresolved_tokens: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# T010 — sparse line grammar parser
# ---------------------------------------------------------------------------


def _set_or_conflict(line: ParsedLine, attr: str, value: str, raw_token: str) -> None:
    """Assign ``value`` to ``line.<attr>`` unless that field is already set.

    A second token targeting the same sparse field is a conflict — captured in
    ``unresolved_tokens`` (not fatal) rather than silently overwriting.
    """
    if getattr(line, attr) is not None:
        line.unresolved_tokens.append(raw_token)
        return
    setattr(line, attr, value)


def _classify_token(line: ParsedLine, raw_token: str) -> None:
    """Classify one non-numeric token by shape/vocabulary into ``line``.

    Fixed-vocabulary tokens (friction, quadrant, loe, habit) are canonicalized
    immediately (no seam needed). ``due:`` captures its raw value. A leftover
    word is a *project candidate* stored raw in ``project`` for
    :func:`resolve_line` to resolve against the seam; malformed tokens land in
    ``unresolved_tokens``.
    """
    key = raw_token.lower()

    if key in FRICTION_ALIASES:
        _set_or_conflict(line, "friction", FRICTION_ALIASES[key], raw_token)
        return
    if key in QUADRANT_ALIASES:
        _set_or_conflict(line, "quadrant", QUADRANT_ALIASES[key], raw_token)
        return
    if key in HABIT_TOKENS:
        if line.habit:
            line.unresolved_tokens.append(raw_token)
        else:
            line.habit = True
        return
    if key.startswith("loe:"):
        canonical = LOE_ALIASES.get(key)
        if canonical is None:
            line.unresolved_tokens.append(raw_token)  # malformed loe (e.g. loe:x)
        else:
            _set_or_conflict(line, "loe", canonical, raw_token)
        return
    if key.startswith("due:"):
        value = raw_token.split(":", 1)[1]
        if not value:
            line.unresolved_tokens.append(raw_token)  # empty due:
        elif line.due is not None:
            line.unresolved_tokens.append(raw_token)  # duplicate due
        else:
            line.due = value  # raw date; Tier-2/WP04 does ET-EOD normalization
        return
    if _FRICTION_SHAPE_RE.match(key):
        line.unresolved_tokens.append(raw_token)  # malformed friction (e.g. f5)
        return

    # Anything else is a project candidate (resolved against the seam later).
    if line.project is None:
        line.project = raw_token
    else:
        line.unresolved_tokens.append(raw_token)


def parse_line(raw: str) -> ParsedLine:
    """Parse one sparse shorthand line into a :class:`ParsedLine` (T010).

    The first whitespace token is the digest number ``<n>``; every remaining
    token is optional and order-tolerant. A line with no leading integer keeps
    ``n = None`` and captures the stray leading token in ``unresolved_tokens``.
    ``project`` holds the raw candidate token after parsing — call
    :func:`resolve_line` (or use :func:`parse_reply`) to canonicalize it.
    """
    line = ParsedLine(raw=raw.strip())
    tokens = raw.split()
    if not tokens:
        return line

    start = 1
    leading = _LEADING_NUM_RE.match(tokens[0])
    if leading:
        line.n = int(leading.group(1))
    else:
        line.unresolved_tokens.append(tokens[0])

    for token in tokens[start:]:
        _classify_token(line, token)
    return line


# ---------------------------------------------------------------------------
# T011 — token resolution against the seam + alias table
# ---------------------------------------------------------------------------


def _declared_project_name(token: str) -> str | None:
    """Return the canonical seam-declared project name matching ``token``
    case-insensitively, else ``None``. Goes through ``vikunja_refs`` — never a
    hardcoded list.
    """
    key = token.lower()
    for entry in vikunja_refs.declared_projects():
        if entry["name"].lower() == key:
            return entry["name"]
    return None


def _declared_label_name(token: str) -> str | None:
    """Return the canonical seam-declared label name matching ``token``
    case-insensitively, else ``None``.
    """
    key = token.lower()
    for entry in vikunja_refs.declared_labels():
        if entry["name"].lower() == key:
            return entry["name"]
    return None


def _resolve_project(token: str) -> str | None:
    """Resolve a raw project token to a canonical name (T011).

    A token resolves if it is in :data:`PROJECT_ALIASES` (the documented
    short-names) **or** is itself a seam-declared project name — matching the
    FR-006 rule: "not in the alias table *and* not a seam-declared name →
    unresolved". Returns the canonical name, or ``None`` if unresolved.
    """
    key = token.lower()
    if key in PROJECT_ALIASES:
        return PROJECT_ALIASES[key]
    return _declared_project_name(token)


def resolve_line(line: ParsedLine) -> ParsedLine:
    """Resolve a parsed line's tokens against the seam (T011); mutates + returns.

    - ``project``: the raw candidate is canonicalized via :func:`_resolve_project`;
      on failure it is moved to ``unresolved_tokens`` and ``project`` is cleared.
    - ``friction`` / ``quadrant`` / ``loe`` / ``habit``: the alias-derived
      canonical label name is confirmed against the seam's declared labels. A
      canonical name the seam does not declare is demoted to ``unresolved_tokens``
      (guards against drift between this table and the registry).
    """
    if line.project is not None:
        canonical = _resolve_project(line.project)
        if canonical is None:
            line.unresolved_tokens.append(line.project)
            line.project = None
        else:
            line.project = canonical

    for attr in ("friction", "quadrant", "loe"):
        value = getattr(line, attr)
        if value is not None and _declared_label_name(value) is None:
            setattr(line, attr, None)
            line.unresolved_tokens.append(value)

    if line.habit and _declared_label_name("t:habit") is None:
        line.habit = False
        line.unresolved_tokens.append("t:habit")

    return line


def parse_reply(text: str) -> list[ParsedLine]:
    """Parse + resolve a full multi-line reply (FR-005/FR-006).

    Blank lines are skipped. Each non-blank line is parsed and resolved
    independently, so one malformed line never affects another.
    """
    lines: list[ParsedLine] = []
    for raw in text.splitlines():
        if not raw.strip():
            continue
        lines.append(resolve_line(parse_line(raw)))
    return lines


# ---------------------------------------------------------------------------
# T012 — constrained LLM-fallback re-resolution
# ---------------------------------------------------------------------------


def _validate_fallback_item(item: Any) -> tuple[int, str, str]:
    """Validate one fallback item's strict shape; return ``(line, token,
    canonical_name)``.

    The item must be a mapping with **exactly** the keys ``{line, token,
    position, canonical_name}`` (FR-006). ``line``/``position`` must be ints and
    ``token``/``canonical_name`` strings. Any deviation raises
    :exc:`FallbackItemError` — the LLM cannot smuggle an extra field.
    """
    if not isinstance(item, dict):
        raise FallbackItemError(f"fallback item must be an object, got {type(item).__name__}")
    keys = set(item.keys())
    if keys != _FALLBACK_ITEM_KEYS:
        raise FallbackItemError(
            f"fallback item keys must be exactly {sorted(_FALLBACK_ITEM_KEYS)}; got {sorted(keys)}"
        )
    line_no, position = item["line"], item["position"]
    token, canonical = item["token"], item["canonical_name"]
    if isinstance(line_no, bool) or not isinstance(line_no, int):
        raise FallbackItemError("fallback item 'line' must be an int")
    if isinstance(position, bool) or not isinstance(position, int):
        raise FallbackItemError("fallback item 'position' must be an int")
    if not isinstance(token, str):
        raise FallbackItemError("fallback item 'token' must be a string")
    if not isinstance(canonical, str):
        raise FallbackItemError("fallback item 'canonical_name' must be a string")
    return line_no, token, canonical


def _seam_reresolve(canonical_name: str) -> tuple[str, object] | None:
    """Re-resolve a proposed canonical name through the seam (T012).

    Returns ``(field, value)`` naming the :class:`ParsedLine` field to fill, or
    ``None`` if the proposal is **rejected**. Rejection covers a raw id (a bare
    numeric string) and any free-form value that is not a seam-declared project
    or label name. The alias table is deliberately *not* consulted here — the
    LLM must propose the true canonical name the seam knows, never a short-name
    or an id.
    """
    name = canonical_name.strip()
    if not name or _INT_RE.match(name):  # empty or raw id → reject
        return None

    project = _declared_project_name(name)
    if project is not None:
        return ("project", project)

    label = _declared_label_name(name)
    if label is not None:
        if label.startswith("f:"):
            return ("friction", label)
        if label.startswith("q:"):
            return ("quadrant", label)
        if label.startswith("loe:"):
            return ("loe", label)
        if label == "t:habit":
            return ("habit", True)
    return None


def resolve_with_fallback(
    parsed: list[ParsedLine],
    unresolved_map: list[dict[str, Any]],
) -> list[ParsedLine]:
    """Apply a constrained LLM-fallback map to already-parsed lines (T012).

    ``unresolved_map`` is a list of strict ``{line, token, position,
    canonical_name}`` items (see :func:`_validate_fallback_item`). For each item
    whose ``line`` matches a parsed line's ``n``, the ``canonical_name`` is
    re-resolved through the seam (:func:`_seam_reresolve`); on success the
    corresponding field is filled and the original ``token`` is cleared from
    that line's ``unresolved_tokens``. A rejected proposal (raw id or free-form
    value) leaves the token echo-back-bound.

    Mutates and returns ``parsed`` (in place) for caller convenience.
    """
    by_number: dict[int, ParsedLine] = {ln.n: ln for ln in parsed if ln.n is not None}

    for item in unresolved_map:
        line_no, token, canonical = _validate_fallback_item(item)
        line = by_number.get(line_no)
        if line is None:
            continue  # no such line in this reply — nothing to fill

        placement = _seam_reresolve(canonical)
        if placement is None:
            continue  # rejected → token stays echo-back-bound

        attr, value = placement
        setattr(line, attr, value)
        if token in line.unresolved_tokens:
            line.unresolved_tokens.remove(token)

    return parsed
