"""Tests for the fail-closed document-status taxonomy loader (#987 FR-005).

The point of every negative case here is that the loader **raises** rather than
falling back. The behaviour being replaced warned and continued on built-in
defaults, which meant the repo could enforce rules that differed from the ones
on disk with nothing to indicate it.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tooling" / "scripts"))

from doc_taxonomy import (  # noqa: E402
    DEFAULT_TAXONOMY_PATH,
    Taxonomy,
    TaxonomyError,
    load_taxonomy,
)

VALID = {
    "doc_type": ["runbook", "reference", "decision"],
    "status": ["draft", "approved", "archived"],
    "status_by_doc_type": {"decision": ["draft", "proposed", "approved", "superseded"]},
}


def _write(tmp_path: Path, payload, *, raw: str | None = None) -> Path:
    p = tmp_path / "allowed-values.json"
    p.write_text(raw if raw is not None else json.dumps(payload), encoding="utf-8")
    return p


# --------------------------------------------------------------------------
# Positive path
# --------------------------------------------------------------------------


def test_loads_valid_taxonomy(tmp_path):
    t = load_taxonomy(_write(tmp_path, VALID))
    assert isinstance(t, Taxonomy)
    assert t.default_statuses == ("draft", "approved", "archived")
    assert t.statuses_for("decision") == ("draft", "proposed", "approved", "superseded")


def test_unscoped_doc_type_gets_the_default_set(tmp_path):
    t = load_taxonomy(_write(tmp_path, VALID))
    assert t.statuses_for("runbook") == t.default_statuses
    assert t.is_scoped("runbook") is False
    assert t.is_scoped("decision") is True


def test_absent_doc_type_gets_the_default_set(tmp_path):
    """A document with no doc_type is a separate defect; don't blame status."""
    t = load_taxonomy(_write(tmp_path, VALID))
    assert t.statuses_for(None) == t.default_statuses


def test_scoped_and_default_sets_may_differ(tmp_path):
    """`superseded` is decision-only; `archived` is not valid for a decision."""
    t = load_taxonomy(_write(tmp_path, VALID))
    assert "superseded" in t.statuses_for("decision")
    assert "superseded" not in t.default_statuses
    assert "archived" not in t.statuses_for("decision")


def test_the_real_repo_taxonomy_loads(tmp_path):
    """Guards against shipping a source file this loader cannot read."""
    t = load_taxonomy(DEFAULT_TAXONOMY_PATH)
    assert "decision" in t.doc_types
    assert t.statuses_for("decision") == (
        "draft",
        "proposed",
        "approved",
        "superseded",
        "deprecated",
    )


# --------------------------------------------------------------------------
# Fail-closed: every malformed shape raises
# --------------------------------------------------------------------------


def test_missing_file_raises(tmp_path):
    with pytest.raises(TaxonomyError, match="not found"):
        load_taxonomy(tmp_path / "absent.json")


def test_malformed_json_raises_and_does_not_fall_back(tmp_path):
    with pytest.raises(TaxonomyError, match="invalid JSON"):
        load_taxonomy(_write(tmp_path, None, raw="{not json"))


def test_non_object_top_level_raises(tmp_path):
    with pytest.raises(TaxonomyError, match="top level must be an object"):
        load_taxonomy(_write(tmp_path, ["draft"]))


@pytest.mark.parametrize("missing", ["status", "doc_type"])
def test_missing_required_key_raises(tmp_path, missing):
    payload = {k: v for k, v in VALID.items() if k != missing}
    with pytest.raises(TaxonomyError, match=f"required key '{missing}' is missing"):
        load_taxonomy(_write(tmp_path, payload))


def test_non_list_status_raises(tmp_path):
    with pytest.raises(TaxonomyError, match="must be a list"):
        load_taxonomy(_write(tmp_path, {**VALID, "status": "draft"}))


def test_empty_status_raises(tmp_path):
    with pytest.raises(TaxonomyError, match="must not be empty"):
        load_taxonomy(_write(tmp_path, {**VALID, "status": []}))


def test_non_string_entry_raises(tmp_path):
    with pytest.raises(TaxonomyError, match="non-string entry"):
        load_taxonomy(_write(tmp_path, {**VALID, "status": ["draft", 1]}))


def test_blank_entry_raises(tmp_path):
    with pytest.raises(TaxonomyError, match="blank entry"):
        load_taxonomy(_write(tmp_path, {**VALID, "status": ["draft", "  "]}))


def test_duplicate_entries_raise(tmp_path):
    with pytest.raises(TaxonomyError, match="duplicate entries: draft"):
        load_taxonomy(_write(tmp_path, {**VALID, "status": ["draft", "approved", "draft"]}))


def test_non_object_scope_raises(tmp_path):
    with pytest.raises(TaxonomyError, match="must be an object"):
        load_taxonomy(_write(tmp_path, {**VALID, "status_by_doc_type": ["decision"]}))


def test_scope_keyed_on_unknown_doc_type_raises(tmp_path):
    """Dead config: a scope that can never match any real document."""
    payload = {**VALID, "status_by_doc_type": {"nonesuch": ["draft"]}}
    with pytest.raises(TaxonomyError, match="is not a permitted doc_type"):
        load_taxonomy(_write(tmp_path, payload))


def test_malformed_scoped_value_raises(tmp_path):
    payload = {**VALID, "status_by_doc_type": {"decision": []}}
    with pytest.raises(TaxonomyError, match=r"status_by_doc_type\.decision.*must not be empty"):
        load_taxonomy(_write(tmp_path, payload))


def test_scoped_value_duplicates_raise(tmp_path):
    payload = {**VALID, "status_by_doc_type": {"decision": ["draft", "draft"]}}
    with pytest.raises(TaxonomyError, match="duplicate entries"):
        load_taxonomy(_write(tmp_path, payload))


# --------------------------------------------------------------------------
# Regressions from review feedback #1 (Codex, 2026-09-18)
# --------------------------------------------------------------------------


def test_duplicate_top_level_keys_raise(tmp_path):
    """F2: json.loads is last-value-wins; the key a human reads first would not
    be the one enforced."""
    raw = '{"doc_type": ["runbook"], "status": ["draft"], "status": ["approved"]}'
    with pytest.raises(TaxonomyError, match="duplicate key 'status'"):
        load_taxonomy(_write(tmp_path, None, raw=raw))


def test_duplicate_nested_keys_raise(tmp_path):
    """F2: the hook must apply at every nesting level, not just the top."""
    raw = (
        '{"doc_type": ["decision"], "status": ["draft"], '
        '"status_by_doc_type": {"decision": ["draft"], "decision": ["approved"]}}'
    )
    with pytest.raises(TaxonomyError, match="duplicate key 'decision'"):
        load_taxonomy(_write(tmp_path, None, raw=raw))


@pytest.mark.parametrize("constant", ["NaN", "Infinity", "-Infinity"])
def test_non_standard_json_constants_raise(tmp_path, constant):
    """F3: Python accepts these; JSON does not define them."""
    raw = '{"doc_type": ["runbook"], "status": ["draft"], "level": [%s]}' % constant
    with pytest.raises(TaxonomyError, match="non-standard JSON constant"):
        load_taxonomy(_write(tmp_path, None, raw=raw))


def test_invalid_utf8_raises_taxonomy_error(tmp_path):
    """F4: UnicodeDecodeError is a ValueError, so it escaped the OSError handler."""
    p = tmp_path / "allowed-values.json"
    p.write_bytes(b'{"status": ["dr\xff\xfeaft"], "doc_type": ["runbook"]}')
    with pytest.raises(TaxonomyError, match="not valid UTF-8"):
        load_taxonomy(p)


@pytest.mark.parametrize("token", ["draft ", " draft", "draft\t"])
def test_non_canonical_token_raises(tmp_path, token):
    """F5: a whitespace variant no document can match, and it evades dedup."""
    with pytest.raises(TaxonomyError, match="leading or trailing whitespace"):
        load_taxonomy(_write(tmp_path, {**VALID, "status": ["approved", token]}))


def test_taxonomy_is_immutable(tmp_path):
    """F6: a caller able to mutate this bypasses every invariant above."""
    t = load_taxonomy(_write(tmp_path, VALID))
    with pytest.raises(AttributeError):
        t.default_statuses = ()
    with pytest.raises(AttributeError):
        del t.doc_types
    with pytest.raises(AttributeError):
        t.scoped_statuses.clear()


def test_all_vocabularies_are_exposed(tmp_path):
    """F7: consumers must never need to parse the source file themselves."""
    payload = {**VALID, "audience": ["agents", "humans"], "level": ["overview", 1]}
    t = load_taxonomy(_write(tmp_path, payload))
    assert t.allowed("audience") == ("agents", "humans")
    assert t.allowed("level") == ("overview", 1)  # mixed types tolerated by design
    assert t.allowed("status") == t.default_statuses
    with pytest.raises(TaxonomyError, match="no vocabulary named"):
        t.allowed("nonesuch")


def test_errors_name_the_source_file(tmp_path):
    """F8: an error that does not say which file is nearly useless in a hook."""
    p = _write(tmp_path, {**VALID, "status": []})
    with pytest.raises(TaxonomyError) as exc:
        load_taxonomy(p)
    assert str(p) in str(exc.value)


def test_absent_scope_map_is_valid_shape(tmp_path):
    """F1 (downgraded): absence is valid *shape*. Which doc_types carry
    overrides is content policy, guarded by test_the_real_repo_taxonomy_loads,
    not by structural validation here."""
    payload = {k: v for k, v in VALID.items() if k != "status_by_doc_type"}
    t = load_taxonomy(_write(tmp_path, payload))
    assert t.statuses_for("decision") == t.default_statuses
    assert t.is_scoped("decision") is False
