"""Unit tests for the deterministic compact-shorthand parser + resolver (WP03).

Covers T010 (sparse grammar), T011 (seam + alias resolution), T012 (constrained
fallback), and T013 (NFR-002 100%-taxonomy coverage). The #748 reference seam is
injected network-free via ``vikunja_refs.set_registry_for_test`` — no live HTTP,
no dependency on the real registry file. The alias table maps tokens to canonical
*names* only; ids are never asserted here (WP03 stores names, WP04 resolves ids).
"""
from __future__ import annotations

import pytest

from scripts.common import vikunja_refs
from scripts.intake import shorthand
from scripts.intake.shorthand import (
    FallbackItemError,
    parse_line,
    parse_reply,
    resolve_line,
    resolve_with_fallback,
)


# ---------------------------------------------------------------------------
# Injected seam registry (network-free) — mirrors vikunja_refs.json shape.
# Declares every documented project (except ``intentional``, which the seam does
# not yet provision — it resolves via the alias table alone) + the full label
# taxonomy (f:/q:/loe:/t:habit).
# ---------------------------------------------------------------------------


def _project(name: str, value: int) -> dict:
    return {
        "name": name,
        "selector": {"kind": "project_id", "value": value},
        "title": name.replace("_", " ").title(),
        "owner": "kent",
        "provisioned": True,
    }


def _label(name: str, value: int) -> dict:
    return {
        "name": name,
        "selector": {"kind": "label", "value": value},
        "title": name,
        "owner_token": "kent",
    }


_TEST_REGISTRY = {
    "schema_version": 1,
    "source_of_truth": "test",
    "last_verified_utc": "2026-07-17T00:00:00Z",
    "projects": [
        _project("inbox", 1),
        _project("personal", 20),
        _project("felix_kg_automation", 16),
        _project("clients", 30),
        _project("pointerhealth", 31),
        _project("spec_kitty", 32),
        _project("habits", 13),
    ],
    "labels": [
        _label("f:1-flow", 18),
        _label("f:2-growth", 19),
        _label("f:3-edge", 20),
        _label("f:4-overload", 21),
        _label("q:do", 22),
        _label("q:schedule", 23),
        _label("q:delegate", 24),
        _label("q:eliminate", 25),
        _label("t:habit", 26),
        _label("loe:s", 27),
        _label("loe:m", 28),
        _label("loe:l", 29),
    ],
    "private_projects": [],
}


@pytest.fixture(autouse=True)
def _inject_registry():
    vikunja_refs.set_registry_for_test(_TEST_REGISTRY)
    yield
    vikunja_refs.set_registry_for_test(None)


def _only(lines):
    """Return the single ParsedLine from a one-line reply."""
    assert len(lines) == 1
    return lines[0]


# ---------------------------------------------------------------------------
# T010 — sparse line grammar
# ---------------------------------------------------------------------------


def test_full_form_line_parses_all_fields():
    line = _only(parse_reply("3 clients f3 do due:fri habit loe:m"))
    assert line.n == 3
    assert line.project == "clients"
    assert line.friction == "f:3-edge"
    assert line.quadrant == "q:do"
    assert line.due == "fri"
    assert line.habit is True
    assert line.loe == "loe:m"
    assert line.unresolved_tokens == []


def test_sparse_project_only():
    line = _only(parse_reply("1 personal"))
    assert line.n == 1
    assert line.project == "personal"
    assert line.friction is None
    assert line.quadrant is None
    assert line.unresolved_tokens == []


def test_sparse_labels_only():
    line = _only(parse_reply("2 f2 schedule"))
    assert line.n == 2
    assert line.project is None
    assert line.friction == "f:2-growth"
    assert line.quadrant == "q:schedule"
    assert line.unresolved_tokens == []


def test_sparse_mixed_line_with_due():
    line = _only(parse_reply("3 clients f3 do due:fri"))
    assert line.n == 3
    assert line.project == "clients"
    assert line.friction == "f:3-edge"
    assert line.quadrant == "q:do"
    assert line.due == "fri"
    assert line.unresolved_tokens == []


def test_tokens_are_order_tolerant():
    line = _only(parse_reply("5 do f1 personal"))
    assert line.project == "personal"
    assert line.friction == "f:1-flow"
    assert line.quadrant == "q:do"
    assert line.unresolved_tokens == []


def test_lines_are_independent_one_bad_does_not_break_others():
    lines = parse_reply("1 personal\n2 wat\n3 f3 do")
    assert lines[0].project == "personal"
    assert lines[0].unresolved_tokens == []
    assert lines[1].project is None
    assert lines[1].unresolved_tokens == ["wat"]
    assert lines[2].friction == "f:3-edge"
    assert lines[2].quadrant == "q:do"
    assert lines[2].unresolved_tokens == []


def test_blank_lines_skipped():
    lines = parse_reply("1 personal\n\n   \n2 f2 do")
    assert len(lines) == 2
    assert lines[0].n == 1
    assert lines[1].n == 2


def test_line_without_leading_number_captures_stray_token():
    line = parse_line("personal f2")
    assert line.n is None
    assert "personal" in line.unresolved_tokens
    # remaining tokens still classified
    assert line.friction == "f:2-growth"


def test_raw_is_preserved():
    line = _only(parse_reply("  7 personal  "))
    assert line.raw == "7 personal"


# ---------------------------------------------------------------------------
# T010 — malformed tokens captured, not fatal
# ---------------------------------------------------------------------------


def test_malformed_loe_captured():
    line = _only(parse_reply("1 personal loe:x"))
    assert line.project == "personal"
    assert line.loe is None
    assert line.unresolved_tokens == ["loe:x"]


def test_malformed_friction_captured():
    line = _only(parse_reply("1 personal f5"))
    assert line.project == "personal"
    assert line.friction is None
    assert line.unresolved_tokens == ["f5"]


def test_empty_due_captured():
    line = _only(parse_reply("1 personal due:"))
    assert line.due is None
    assert line.unresolved_tokens == ["due:"]


def test_duplicate_field_is_conflict_not_overwrite():
    line = _only(parse_reply("1 f1 f2"))
    assert line.friction == "f:1-flow"  # first wins
    assert line.unresolved_tokens == ["f2"]


def test_second_project_candidate_captured():
    line = _only(parse_reply("1 personal clients"))
    assert line.project == "personal"
    assert line.unresolved_tokens == ["clients"]


# ---------------------------------------------------------------------------
# T011 — resolution + unknown tokens
# ---------------------------------------------------------------------------


def test_unknown_token_goes_to_unresolved():
    line = _only(parse_reply("4 flibberdegibbet"))
    assert line.project is None
    assert line.unresolved_tokens == ["flibberdegibbet"]


def test_resolution_is_case_insensitive():
    line = _only(parse_reply("1 PERSONAL F2 SCHEDULE HABIT LOE:M"))
    assert line.project == "personal"
    assert line.friction == "f:2-growth"
    assert line.quadrant == "q:schedule"
    assert line.habit is True
    assert line.loe == "loe:m"
    assert line.unresolved_tokens == []


def test_bare_seam_declared_name_resolves_without_alias():
    # ``felix_kg_automation`` is not an alias key but is a seam-declared name.
    line = _only(parse_reply("1 felix_kg_automation"))
    assert line.project == "felix_kg_automation"
    assert line.unresolved_tokens == []


def test_alias_only_project_resolves_even_when_unprovisioned():
    # ``intentional`` is a documented short-name but not declared in the seam;
    # it still resolves deterministically via the alias table (NFR-002).
    line = _only(parse_reply("1 intentional"))
    assert line.project == "intentional"
    assert line.unresolved_tokens == []


def test_label_not_declared_in_seam_is_demoted(monkeypatch):
    # Drift guard: if the seam stops declaring a label, resolution demotes it.
    registry = {**_TEST_REGISTRY, "labels": [_label("q:do", 22)]}
    vikunja_refs.set_registry_for_test(registry)
    line = _only(parse_reply("1 f2 do"))
    assert line.quadrant == "q:do"  # still declared
    assert line.friction is None  # f:2-growth no longer declared → demoted
    assert "f:2-growth" in line.unresolved_tokens


# ---------------------------------------------------------------------------
# T013 / NFR-002 — the deterministic grammar covers the full documented taxonomy
# (100% of documented projects + f:/q:/t:/loe: tokens + aliases, no fallback)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("short_name", sorted(shorthand.PROJECT_ALIASES))
def test_nfr002_every_documented_project_resolves_without_fallback(short_name):
    line = _only(parse_reply(f"1 {short_name}"))
    assert line.project == shorthand.PROJECT_ALIASES[short_name]
    assert line.unresolved_tokens == []


@pytest.mark.parametrize(
    ("token", "expected"),
    sorted(shorthand.FRICTION_ALIASES.items()),
)
def test_nfr002_every_friction_alias_resolves(token, expected):
    line = _only(parse_reply(f"1 {token}"))
    assert line.friction == expected
    assert line.unresolved_tokens == []


@pytest.mark.parametrize(
    ("token", "expected"),
    sorted(shorthand.QUADRANT_ALIASES.items()),
)
def test_nfr002_every_quadrant_alias_resolves(token, expected):
    line = _only(parse_reply(f"1 {token}"))
    assert line.quadrant == expected
    assert line.unresolved_tokens == []


@pytest.mark.parametrize(
    ("token", "expected"),
    sorted(shorthand.LOE_ALIASES.items()),
)
def test_nfr002_every_loe_alias_resolves(token, expected):
    line = _only(parse_reply(f"1 {token}"))
    assert line.loe == expected
    assert line.unresolved_tokens == []


@pytest.mark.parametrize("token", sorted(shorthand.HABIT_TOKENS))
def test_nfr002_habit_tokens_resolve(token):
    line = _only(parse_reply(f"1 {token}"))
    assert line.habit is True
    assert line.unresolved_tokens == []


def test_nfr002_eliminate_alias_maps_to_q_eliminate():
    for token in ("elim", "eliminate"):
        line = _only(parse_reply(f"1 {token}"))
        assert line.quadrant == "q:eliminate"


# ---------------------------------------------------------------------------
# T012 — constrained LLM-fallback re-resolution
# ---------------------------------------------------------------------------


def _unresolved_line(text="1 foobar"):
    lines = parse_reply(text)
    line = _only(lines)
    assert line.project is None
    assert line.unresolved_tokens == ["foobar"]
    return lines


def test_fallback_accepts_canonical_project_name():
    lines = _unresolved_line()
    resolve_with_fallback(
        lines,
        [{"line": 1, "token": "foobar", "position": 1, "canonical_name": "felix_kg_automation"}],
    )
    assert lines[0].project == "felix_kg_automation"
    assert lines[0].unresolved_tokens == []


def test_fallback_accepts_canonical_label_name_and_places_by_family():
    lines = _unresolved_line("1 foobar")
    resolve_with_fallback(
        lines,
        [{"line": 1, "token": "foobar", "position": 1, "canonical_name": "q:schedule"}],
    )
    assert lines[0].quadrant == "q:schedule"
    assert lines[0].unresolved_tokens == []


def test_fallback_rejects_raw_id():
    lines = _unresolved_line()
    resolve_with_fallback(
        lines,
        [{"line": 1, "token": "foobar", "position": 1, "canonical_name": "16"}],
    )
    # rejected: no id injected, token stays echo-back-bound
    assert lines[0].project is None
    assert lines[0].unresolved_tokens == ["foobar"]


def test_fallback_rejects_free_form_value():
    lines = _unresolved_line()
    resolve_with_fallback(
        lines,
        [{"line": 1, "token": "foobar", "position": 1, "canonical_name": "Some Made Up Project"}],
    )
    assert lines[0].project is None
    assert lines[0].unresolved_tokens == ["foobar"]


def test_fallback_rejects_short_name_alias_must_be_true_canonical():
    # The LLM must propose the seam's canonical name, not a short-name alias.
    lines = _unresolved_line()
    resolve_with_fallback(
        lines,
        [{"line": 1, "token": "foobar", "position": 1, "canonical_name": "felix"}],
    )
    assert lines[0].project is None
    assert lines[0].unresolved_tokens == ["foobar"]


def test_fallback_habit_placement():
    lines = _unresolved_line()
    resolve_with_fallback(
        lines,
        [{"line": 1, "token": "foobar", "position": 1, "canonical_name": "t:habit"}],
    )
    assert lines[0].habit is True
    assert lines[0].unresolved_tokens == []


def test_fallback_ignores_item_for_missing_line():
    lines = _unresolved_line()
    resolve_with_fallback(
        lines,
        [{"line": 99, "token": "foobar", "position": 1, "canonical_name": "personal"}],
    )
    assert lines[0].project is None
    assert lines[0].unresolved_tokens == ["foobar"]


@pytest.mark.parametrize(
    "bad_item",
    [
        {"line": 1, "token": "x", "position": 1},  # missing canonical_name
        {"line": 1, "token": "x", "position": 1, "canonical_name": "p", "extra": "leak"},
        {"line": 1, "token": "x", "position": 1, "project_id": 16},  # id-smuggling shape
        {"line": "1", "token": "x", "position": 1, "canonical_name": "p"},  # line not int
        {"line": 1, "token": 5, "position": 1, "canonical_name": "p"},  # token not str
        "not-a-dict",
    ],
)
def test_fallback_rejects_malformed_item_shape(bad_item):
    lines = _unresolved_line()
    with pytest.raises(FallbackItemError):
        resolve_with_fallback(lines, [bad_item])


# ---------------------------------------------------------------------------
# resolve_line is idempotent w.r.t. an already-canonical line
# ---------------------------------------------------------------------------


def test_resolve_line_returns_same_instance():
    parsed = parse_line("1 personal")
    resolved = resolve_line(parsed)
    assert resolved is parsed
