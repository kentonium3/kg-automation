"""Contract tests for ``scripts.common.vikunja_refs`` (WP01, mission
``vikunja-reference-seam-01KXK68Z``, kentonium3/kg-automation#748/#745).

These lock the behavior described in
``kitty-specs/vikunja-reference-seam-01KXK68Z/contracts/vikunja-refs.contract.md``
and ``data-model.md`` — not the implementation. Every test drives the accessor
through an **injected in-memory registry** (never the real file, never the
network), and the no-network guard tests prove the hot path performs zero file
or network I/O (NFR-001).

The repo-wide ``tests/conftest.py`` already blocks ``urllib.request.urlopen``
globally, so any accidental live HTTP would fail loudly regardless.
"""
from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

import pytest

from scripts.common import vikunja_refs
from scripts.common.vikunja_refs import VikunjaRefError, VikunjaRefUnprovisioned


def _registry(**overrides: Any) -> dict[str, Any]:
    """Build a well-formed in-memory registry with representative entries.

    Includes a provisioned project (``inbox``/``habits``), an unprovisioned
    project (``personal``, ``value: null``), a project carrying a *label*
    selector (``habit_label`` — the post-#717 migration shape, used to prove
    the wrong-accessor guard), a provisioned label (``felix:ignore``,
    ``q:schedule``) and an unprovisioned label (``orphan:label``).
    """
    base: dict[str, Any] = {
        "schema_version": 1,
        "source_of_truth": "docs/design/vikunja-configuration-design.md",
        "last_verified_utc": "2026-07-15T00:00:00Z",
        "projects": [
            {"name": "inbox", "selector": {"kind": "project_id", "value": 1},
             "title": "Inbox", "owner": "kent", "provisioned": True},
            {"name": "habits", "selector": {"kind": "project_id", "value": 13},
             "title": "Habits", "owner": "kent", "provisioned": True},
            {"name": "personal", "selector": {"kind": "project_id", "value": None},
             "title": "Personal", "owner": "kent", "provisioned": False},
            {"name": "habit_label", "selector": {"kind": "label", "value": 26},
             "title": "t:habit", "owner": "kent", "provisioned": True},
        ],
        "labels": [
            {"name": "felix:ignore", "selector": {"kind": "label", "value": 99},
             "title": "felix:ignore", "owner_token": "kent"},
            {"name": "q:schedule", "selector": {"kind": "label", "value": 23},
             "title": "q:schedule", "owner_token": "kent"},
            {"name": "orphan:label", "selector": {"kind": "label", "value": None},
             "title": "orphan", "owner_token": "kent"},
        ],
        "private_projects": [],
    }
    base.update(overrides)
    return base


@pytest.fixture(autouse=True)
def _inject_default_registry() -> Any:
    """Install the default in-memory registry before each test; clear after.

    Guarantees isolation from the real file and from cross-test leakage.
    """
    vikunja_refs.set_registry_for_test(_registry())
    yield
    vikunja_refs.set_registry_for_test(None)


# ---------------------------------------------------------------------------
# Project accessors — success (T003)
# ---------------------------------------------------------------------------


def test_project_id_returns_seeded_int() -> None:
    assert vikunja_refs.project_id("inbox") == 1
    assert vikunja_refs.project_id("habits") == 13


def test_project_id_returns_int_not_bool() -> None:
    result = vikunja_refs.project_id("inbox")
    assert isinstance(result, int)


def test_project_title_returns_declared_title() -> None:
    assert vikunja_refs.project_title("inbox") == "Inbox"
    assert vikunja_refs.project_title("habits") == "Habits"


def test_project_title_returns_title_even_when_unprovisioned() -> None:
    # Title is declared regardless of provisioning (validator/reporting use).
    assert vikunja_refs.project_title("personal") == "Personal"


def test_selector_returns_raw_kind_value() -> None:
    assert vikunja_refs.selector("habits") == {"kind": "project_id", "value": 13}


def test_selector_returns_a_copy_no_state_leak() -> None:
    sel = vikunja_refs.selector("habits")
    sel["value"] = 999
    sel["kind"] = "label"
    # Mutating the returned dict must not corrupt module state.
    assert vikunja_refs.selector("habits") == {"kind": "project_id", "value": 13}


# ---------------------------------------------------------------------------
# Project accessors — fail-loud (T003, FR-003/FR-009)
# ---------------------------------------------------------------------------


def test_project_id_undeclared_raises() -> None:
    with pytest.raises(VikunjaRefError, match="Undeclared project"):
        vikunja_refs.project_id("nonexistent")


def test_project_title_undeclared_raises() -> None:
    with pytest.raises(VikunjaRefError, match="Undeclared project"):
        vikunja_refs.project_title("nonexistent")


def test_selector_undeclared_raises() -> None:
    with pytest.raises(VikunjaRefError, match="Undeclared project"):
        vikunja_refs.selector("nonexistent")


def test_project_id_unprovisioned_raises_distinct_message() -> None:
    # Declared but value:null must raise a *distinct* "unprovisioned" error,
    # never return None/0 (FR-009 — the #743 loud-not-silent guard).
    with pytest.raises(VikunjaRefError, match="unprovisioned"):
        vikunja_refs.project_id("personal")


def test_project_id_on_label_selector_raises_wrong_accessor() -> None:
    # A project whose identity migrated to a label selector must not resolve
    # through project_id — it is the wrong accessor for that kind.
    with pytest.raises(VikunjaRefError, match="selector"):
        vikunja_refs.project_id("habit_label")


def test_project_id_never_returns_falsy_sentinel() -> None:
    # Belt-and-suspenders: the failure path raises; it does not return 0/None.
    for bad in ("nonexistent", "personal", "habit_label"):
        with pytest.raises(VikunjaRefError):
            vikunja_refs.project_id(bad)


def test_project_id_zero_value_raises_invalid_not_sentinel() -> None:
    # A provisioned entry whose value is 0 must fail loud with a *distinct*
    # "invalid id" message — never return the forbidden 0 sentinel, and never
    # be conflated with the unprovisioned (value:null) case.
    reg = _registry()
    reg["projects"] = [
        {"name": "zero", "selector": {"kind": "project_id", "value": 0},
         "title": "Zero", "owner": "kent", "provisioned": True}
    ]
    vikunja_refs.set_registry_for_test(reg)
    with pytest.raises(VikunjaRefError, match="invalid id value") as exc:
        vikunja_refs.project_id("zero")
    assert "zero" in str(exc.value)
    assert "unprovisioned" not in str(exc.value)


def test_project_id_negative_value_raises_invalid() -> None:
    reg = _registry()
    reg["projects"] = [
        {"name": "neg", "selector": {"kind": "project_id", "value": -5},
         "title": "Neg", "owner": "kent", "provisioned": True}
    ]
    vikunja_refs.set_registry_for_test(reg)
    with pytest.raises(VikunjaRefError, match="positive integer"):
        vikunja_refs.project_id("neg")


def test_project_id_non_int_string_value_raises_vikunjareferror_not_valueerror() -> None:
    # A non-numeric string value must raise VikunjaRefError, not leak a raw
    # ValueError from int(...).
    reg = _registry()
    reg["projects"] = [
        {"name": "strval", "selector": {"kind": "project_id", "value": "zero"},
         "title": "StrVal", "owner": "kent", "provisioned": True}
    ]
    vikunja_refs.set_registry_for_test(reg)
    with pytest.raises(VikunjaRefError, match="invalid id value"):
        vikunja_refs.project_id("strval")


# ---------------------------------------------------------------------------
# Label accessors (T004)
# ---------------------------------------------------------------------------


def test_label_id_resolves_in_owner_token_namespace() -> None:
    assert vikunja_refs.label_id("felix:ignore", "kent") == 99
    assert vikunja_refs.label_id("q:schedule", "kent") == 23


def test_label_id_wrong_owner_token_raises() -> None:
    with pytest.raises(VikunjaRefError, match="per-token"):
        vikunja_refs.label_id("felix:ignore", "felix-bot")


def test_label_id_undeclared_raises() -> None:
    with pytest.raises(VikunjaRefError, match="Undeclared label"):
        vikunja_refs.label_id("no:such:label", "kent")


def test_label_id_unprovisioned_raises_distinct_message() -> None:
    with pytest.raises(VikunjaRefError, match="unprovisioned"):
        vikunja_refs.label_id("orphan:label", "kent")


def test_label_id_zero_value_raises_invalid_not_sentinel() -> None:
    reg = _registry()
    reg["labels"] = [
        {"name": "zero:label", "selector": {"kind": "label", "value": 0},
         "title": "zero", "owner_token": "kent"}
    ]
    vikunja_refs.set_registry_for_test(reg)
    with pytest.raises(VikunjaRefError, match="invalid id value") as exc:
        vikunja_refs.label_id("zero:label", "kent")
    assert "zero:label" in str(exc.value)
    assert "unprovisioned" not in str(exc.value)


def test_label_id_negative_value_raises_invalid() -> None:
    reg = _registry()
    reg["labels"] = [
        {"name": "neg:label", "selector": {"kind": "label", "value": -3},
         "title": "neg", "owner_token": "kent"}
    ]
    vikunja_refs.set_registry_for_test(reg)
    with pytest.raises(VikunjaRefError, match="positive integer"):
        vikunja_refs.label_id("neg:label", "kent")


def test_label_id_non_int_string_value_raises_vikunjareferror_not_valueerror() -> None:
    reg = _registry()
    reg["labels"] = [
        {"name": "str:label", "selector": {"kind": "label", "value": "nope"},
         "title": "str", "owner_token": "kent"}
    ]
    vikunja_refs.set_registry_for_test(reg)
    with pytest.raises(VikunjaRefError, match="invalid id value"):
        vikunja_refs.label_id("str:label", "kent")


# ---------------------------------------------------------------------------
# Private-project set (T004, finding #4)
# ---------------------------------------------------------------------------


def test_private_project_ids_empty_by_default() -> None:
    result = vikunja_refs.private_project_ids()
    assert result == frozenset()
    assert isinstance(result, frozenset)


def test_private_project_ids_resolves_seeded_names() -> None:
    vikunja_refs.set_registry_for_test(_registry(private_projects=["inbox", "habits"]))
    result = vikunja_refs.private_project_ids()
    assert result == frozenset({1, 13})
    assert isinstance(result, frozenset)


def test_private_project_ids_undeclared_name_raises() -> None:
    vikunja_refs.set_registry_for_test(_registry(private_projects=["ghost"]))
    with pytest.raises(VikunjaRefError, match="Undeclared project"):
        vikunja_refs.private_project_ids()


def test_private_project_ids_unprovisioned_name_raises() -> None:
    vikunja_refs.set_registry_for_test(_registry(private_projects=["personal"]))
    with pytest.raises(VikunjaRefError, match="unprovisioned"):
        vikunja_refs.private_project_ids()


# ---------------------------------------------------------------------------
# VikunjaRefUnprovisioned — distinguishes "not yet provisioned" from broken
# ---------------------------------------------------------------------------


def test_unprovisioned_is_subclass_of_vikunjareferror() -> None:
    # A subclass, so every existing `except VikunjaRefError` still catches it.
    assert issubclass(VikunjaRefUnprovisioned, VikunjaRefError)


def test_project_id_unprovisioned_raises_unprovisioned_type() -> None:
    with pytest.raises(VikunjaRefUnprovisioned, match="unprovisioned"):
        vikunja_refs.project_id("personal")


def test_label_id_unprovisioned_raises_unprovisioned_type() -> None:
    with pytest.raises(VikunjaRefUnprovisioned, match="unprovisioned"):
        vikunja_refs.label_id("orphan:label", "kent")


def test_project_id_unprovisioned_still_caught_by_base_vikunjareferror() -> None:
    # Backward-compat: a pre-existing `except VikunjaRefError` handler must still
    # catch the unprovisioned case now that it raises the subclass.
    caught = False
    try:
        vikunja_refs.project_id("personal")
    except VikunjaRefError:
        caught = True
    assert caught


def test_label_id_unprovisioned_still_caught_by_base_vikunjareferror() -> None:
    caught = False
    try:
        vikunja_refs.label_id("orphan:label", "kent")
    except VikunjaRefError:
        caught = True
    assert caught


def test_project_id_invalid_provisioned_id_is_base_error_not_unprovisioned() -> None:
    # A broken provisioned id (value:0) is NOT "unprovisioned" — it stays the
    # base VikunjaRefError and must not be catchable as VikunjaRefUnprovisioned.
    reg = _registry()
    reg["projects"] = [
        {"name": "zero", "selector": {"kind": "project_id", "value": 0},
         "title": "Zero", "owner": "kent", "provisioned": True}
    ]
    vikunja_refs.set_registry_for_test(reg)
    with pytest.raises(VikunjaRefError) as exc:
        vikunja_refs.project_id("zero")
    assert not isinstance(exc.value, VikunjaRefUnprovisioned)


def test_project_id_undeclared_is_base_error_not_unprovisioned() -> None:
    # An undeclared ref is a broken reference, not an unprovisioned one.
    with pytest.raises(VikunjaRefError) as exc:
        vikunja_refs.project_id("nonexistent")
    assert not isinstance(exc.value, VikunjaRefUnprovisioned)


# ---------------------------------------------------------------------------
# declared_projects / declared_labels — public "list what's declared" accessors
# ---------------------------------------------------------------------------


def test_declared_projects_returns_all_declared_entries() -> None:
    projects = vikunja_refs.declared_projects()
    by_name = {p["name"]: p for p in projects}
    assert set(by_name) == {"inbox", "habits", "personal", "habit_label"}
    assert by_name["inbox"]["selector"] == {"kind": "project_id", "value": 1}
    assert by_name["inbox"]["title"] == "Inbox"
    assert by_name["inbox"]["owner"] == "kent"
    assert by_name["inbox"]["provisioned"] is True
    assert by_name["personal"]["provisioned"] is False


def test_declared_labels_returns_all_declared_entries() -> None:
    labels = vikunja_refs.declared_labels()
    by_name = {lbl["name"]: lbl for lbl in labels}
    assert set(by_name) == {"felix:ignore", "q:schedule", "orphan:label"}
    assert by_name["q:schedule"]["selector"] == {"kind": "label", "value": 23}
    assert by_name["q:schedule"]["title"] == "q:schedule"
    assert by_name["q:schedule"]["owner_token"] == "kent"
    assert by_name["orphan:label"]["selector"]["value"] is None


def test_declared_projects_returns_deep_copies_no_state_leak() -> None:
    first = vikunja_refs.declared_projects()
    for entry in first:
        entry["title"] = "MUTATED"
        entry["selector"]["value"] = 999
    first.append({"name": "injected"})
    # A subsequent call must be pristine — no mutation leaked into module state.
    second = vikunja_refs.declared_projects()
    by_name = {p["name"]: p for p in second}
    assert "injected" not in by_name
    assert by_name["inbox"]["title"] == "Inbox"
    assert by_name["inbox"]["selector"] == {"kind": "project_id", "value": 1}


def test_declared_labels_returns_deep_copies_no_state_leak() -> None:
    first = vikunja_refs.declared_labels()
    first.clear()
    second = vikunja_refs.declared_labels()
    assert {lbl["name"] for lbl in second} == {"felix:ignore", "q:schedule", "orphan:label"}
    mutate = vikunja_refs.declared_labels()
    for entry in mutate:
        entry["selector"]["value"] = -1
    fresh = {lbl["name"]: lbl for lbl in vikunja_refs.declared_labels()}
    assert fresh["q:schedule"]["selector"]["value"] == 23


def test_declared_accessors_work_under_set_registry_for_test() -> None:
    vikunja_refs.set_registry_for_test(
        _registry(
            projects=[
                {"name": "only", "selector": {"kind": "project_id", "value": 7},
                 "title": "Only", "owner": "kent", "provisioned": True}
            ],
            labels=[],
        )
    )
    assert [p["name"] for p in vikunja_refs.declared_projects()] == ["only"]
    assert vikunja_refs.declared_labels() == []


# ---------------------------------------------------------------------------
# No network / no file read on the hot path (T005, NFR-001)
# ---------------------------------------------------------------------------


def test_accessors_never_invoke_the_file_loader(monkeypatch: pytest.MonkeyPatch) -> None:
    # With an injected registry installed, no accessor may call the file
    # loader. Monkeypatch the loader to record + explode; if any accessor
    # reaches it, the test fails.
    calls: list[str] = []

    def _boom(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        calls.append("loader")
        raise RuntimeError("hot path attempted a file/JSON load")

    monkeypatch.setattr(vikunja_refs, "_load_registry_file", _boom)

    assert vikunja_refs.project_id("inbox") == 1
    assert vikunja_refs.project_title("habits") == "Habits"
    assert vikunja_refs.selector("inbox") == {"kind": "project_id", "value": 1}
    assert vikunja_refs.label_id("q:schedule", "kent") == 23
    assert vikunja_refs.private_project_ids() == frozenset()
    assert len(vikunja_refs.declared_projects()) == 4
    assert len(vikunja_refs.declared_labels()) == 3
    assert calls == []  # loader never invoked while an override is installed


#: Modules that would introduce network I/O into the accessor's import graph.
#: NFR-001/NFR-003: the module must resolve refs from a stdlib file+JSON load
#: only, never reaching for a live Vikunja client or an HTTP stack.
_FORBIDDEN_IMPORT_ROOTS = frozenset({"vikunja_client", "requests", "urllib"})


def _forbidden_imports_in(source: str) -> set[str]:
    """Return the forbidden import names reachable from ``source``.

    Walks the AST so the check is import-order-independent and does not depend
    on the module having been imported a particular way. Every import's **full
    dotted path** is decomposed into components and matched against
    ``_FORBIDDEN_IMPORT_ROOTS`` — so a deep import like
    ``import scripts.common.vikunja_client`` or
    ``from scripts.common.vikunja_client import VikunjaClient`` is caught on the
    ``vikunja_client`` component, not silently reduced to a harmless ``scripts``
    root. For ``from a.b import c`` the imported name ``c`` is also checked, so
    ``from scripts.common import vikunja_client`` trips on the ``vikunja_client``
    binding.
    """
    forbidden = _FORBIDDEN_IMPORT_ROOTS
    found: set[str] = set()

    def _record(dotted: str) -> None:
        found.update(forbidden.intersection(dotted.split(".")))

    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            for alias in node.names:
                _record(alias.name)  # full dotted path, aliases irrelevant
        elif isinstance(node, ast.ImportFrom):
            # Ignore relative imports (node.level > 0); they carry no network risk.
            if node.level != 0:
                continue
            if node.module:
                _record(node.module)
            for alias in node.names:
                # `from a.b import c` binds `c`; catch `from pkg import urllib`.
                _record(alias.name)
    return found


def test_module_import_graph_excludes_network_modules() -> None:
    # NFR-001/NFR-003 contract: parse the accessor module's own source and fail
    # if it imports any network module. Source/AST inspection is robust and
    # import-order-independent (does not depend on sys.modules state).
    source = Path(vikunja_refs.__file__).read_text(encoding="utf-8")
    leaked = _forbidden_imports_in(source)
    assert not leaked, (
        f"scripts.common.vikunja_refs must not import network modules, "
        f"but its import graph includes: {sorted(leaked)}"
    )


def test_import_guard_catches_fully_qualified_network_import() -> None:
    # Regression for review cycle 2: the guard must trip on a *fully qualified*
    # network import, not just a bare top-level root. A prior version recorded
    # only the first path segment, so `scripts.common.vikunja_client` reduced to
    # a harmless `scripts` and slipped through. Run the same AST scan against an
    # inline fixture and assert both dotted forms are flagged.
    fixture = (
        "from scripts.common.vikunja_client import VikunjaClient\n"
        "import scripts.common.vikunja_client\n"
    )
    assert _forbidden_imports_in(fixture) == {"vikunja_client"}

    # And the `from pkg import <forbidden-name>` binding form is caught too.
    assert "vikunja_client" in _forbidden_imports_in(
        "from scripts.common import vikunja_client\n"
    )


def test_module_dict_exposes_no_network_module_attributes() -> None:
    # Belt-and-suspenders on the AST check: after import, none of the forbidden
    # roots may be bound as a module attribute (which a top-level `import x`
    # would create). Catches a network dependency however it was introduced.
    for forbidden in _FORBIDDEN_IMPORT_ROOTS:
        bound = getattr(vikunja_refs, forbidden, None)
        assert not isinstance(bound, type(ast)), (
            f"scripts.common.vikunja_refs unexpectedly binds module {forbidden!r}"
        )


def test_file_loader_is_the_only_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    # Prove the injection seam is real: with the override cleared, resolution
    # must fall through to _load_registry_file (here stubbed to raise), so a
    # sentinel error surfaces — confirming the file loader is what tests bypass.
    def _boom(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise RuntimeError("sentinel-loader-reached")

    monkeypatch.setattr(vikunja_refs, "_load_registry_file", _boom)
    vikunja_refs.set_registry_for_test(None)  # clear override -> use the loader

    with pytest.raises(RuntimeError, match="sentinel-loader-reached"):
        vikunja_refs.project_id("inbox")


# ---------------------------------------------------------------------------
# Registry validation — fail-loud at load (T002)
# ---------------------------------------------------------------------------


def test_missing_top_level_key_raises_at_load() -> None:
    with pytest.raises(VikunjaRefError, match="missing required top-level keys"):
        vikunja_refs.set_registry_for_test({"schema_version": 1})


def test_non_object_registry_raises() -> None:
    with pytest.raises(VikunjaRefError, match="must be a JSON object"):
        vikunja_refs.set_registry_for_test([])  # type: ignore[arg-type]


def test_invalid_selector_kind_raises_at_load() -> None:
    bad = _registry()
    bad["projects"] = [
        {"name": "x", "selector": {"kind": "bogus", "value": 1},
         "title": "X", "owner": "kent"}
    ]
    with pytest.raises(VikunjaRefError, match="selector kind"):
        vikunja_refs.set_registry_for_test(bad)


def test_duplicate_project_name_raises_at_load() -> None:
    bad = _registry()
    bad["projects"] = bad["projects"] + [
        {"name": "inbox", "selector": {"kind": "project_id", "value": 2},
         "title": "Dup", "owner": "kent", "provisioned": True}
    ]
    with pytest.raises(VikunjaRefError, match="Duplicate project"):
        vikunja_refs.set_registry_for_test(bad)


def test_label_with_project_id_selector_kind_raises() -> None:
    bad = _registry()
    bad["labels"] = [
        {"name": "bad:label", "selector": {"kind": "project_id", "value": 5},
         "title": "bad", "owner_token": "kent"}
    ]
    with pytest.raises(VikunjaRefError, match="selector kind must be 'label'"):
        vikunja_refs.set_registry_for_test(bad)


def test_provisioned_defaults_to_true_when_omitted() -> None:
    reg = _registry()
    reg["projects"] = [
        {"name": "nodefault", "selector": {"kind": "project_id", "value": 5},
         "title": "N", "owner": "kent"}
    ]
    vikunja_refs.set_registry_for_test(reg)
    assert vikunja_refs.project_id("nodefault") == 5


def test_boolean_selector_value_rejected() -> None:
    bad = _registry()
    bad["projects"] = [
        {"name": "x", "selector": {"kind": "project_id", "value": True},
         "title": "X", "owner": "kent"}
    ]
    with pytest.raises(VikunjaRefError, match="selector value must be"):
        vikunja_refs.set_registry_for_test(bad)


# ---------------------------------------------------------------------------
# Shipped registry file — loads clean, matches live-probed seeds (integration)
# ---------------------------------------------------------------------------


def test_shipped_registry_file_loads_and_matches_live_seeds() -> None:
    # Exercise the real vikunja_refs.json (file read only, no network): confirm
    # it is well-formed and pins the live-confirmed ids from the 2026-07-15
    # office2 probe. This is the only test that reads the shipped file.
    vikunja_refs.set_registry_for_test(None)

    assert vikunja_refs.project_id("inbox") == 1
    assert vikunja_refs.project_id("habits") == 13
    assert vikunja_refs.project_id("personal") == 20
    assert vikunja_refs.project_id("felix_kg_automation") == 16
    assert vikunja_refs.project_id("clients") == 17
    assert vikunja_refs.project_id("pointerhealth") == 18
    assert vikunja_refs.project_id("spec_kitty") == 19
    assert vikunja_refs.project_id("metal_casework") == 10
    assert vikunja_refs.project_id("ct_90day") == 7

    assert vikunja_refs.project_title("felix_kg_automation") == "Felix / kg-automation"
    assert vikunja_refs.selector("habits") == {"kind": "project_id", "value": 13}

    # q:schedule is live-confirmed (id 23); felix:ignore is declared but not
    # yet provisioned live (value:null) and must fail loud.
    assert vikunja_refs.label_id("q:schedule", "kent") == 23
    with pytest.raises(VikunjaRefError, match="unprovisioned"):
        vikunja_refs.label_id("felix:ignore", "kent")

    # No private project exists today (finding #4).
    assert vikunja_refs.private_project_ids() == frozenset()


def test_public_surface_is_stable() -> None:
    for name in (
        "VikunjaRefError",
        "VikunjaRefUnprovisioned",
        "project_id",
        "project_title",
        "selector",
        "label_id",
        "private_project_ids",
        "declared_projects",
        "declared_labels",
    ):
        assert name in vikunja_refs.__all__
        assert hasattr(vikunja_refs, name)
    assert issubclass(vikunja_refs.VikunjaRefError, Exception)
    assert issubclass(vikunja_refs.VikunjaRefUnprovisioned, vikunja_refs.VikunjaRefError)
