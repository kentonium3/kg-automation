"""Tests for the doc-standards generator (#987 FR-005, NFR-001).

The generator exists because two hand-maintained copies of the status
vocabulary had silently drifted from the enforced source. So the properties
under test are: the derived output is *correct*, *idempotent*, and *refuses to
guess* when a target file is not in a writable state.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tooling" / "scripts"))

from doc_taxonomy import load_taxonomy  # noqa: E402
import generate_doc_standards as gen  # noqa: E402


@pytest.fixture
def tax():
    return load_taxonomy()


# ------------------------------------------------------------------ schema --


def _validator(tax):
    schema = gen.render_schema(tax, json.loads(gen.SCHEMA_PATH.read_text(encoding="utf-8")))
    return Draft202012Validator(schema), schema


def _doc(**kw):
    base = {
        "title": "t",
        "doc_type": "runbook",
        "status": "draft",
        "owners": ["@x"],
        "last_updated": "2026-09-18",
        "version": "v1",
        "audience": "agents",
    }
    base.update(kw)
    return base


def test_decision_accepts_superseded(tax):
    """A flat union enum would be wrong in the other direction; this is the
    value that only decision documents may carry."""
    v, _ = _validator(tax)
    assert v.is_valid(_doc(doc_type="decision", status="superseded"))


def test_decision_rejects_active(tax):
    """The leakage FR-004 exists to prevent: `active` is meaningless for a
    decision record."""
    v, _ = _validator(tax)
    assert not v.is_valid(_doc(doc_type="decision", status="active"))


def test_decision_rejects_in_review(tax):
    v, _ = _validator(tax)
    assert not v.is_valid(_doc(doc_type="decision", status="in_review"))


def test_non_decision_rejects_superseded(tax):
    """The other half: a runbook may not borrow a decision-only status."""
    v, _ = _validator(tax)
    assert not v.is_valid(_doc(doc_type="runbook", status="superseded"))


def test_non_decision_accepts_its_own_set(tax):
    v, _ = _validator(tax)
    for status in ("draft", "in_review", "approved", "archived", "active"):
        assert v.is_valid(_doc(doc_type="runbook", status=status)), status


def test_a_flat_union_would_have_passed_both(tax):
    """Guards the *reason* the schema is conditional: a union of both sets
    would accept every case above, making the scoping meaningless."""
    union = set(tax.default_statuses) | set(tax.scoped_statuses["decision"])
    assert {"active", "superseded"} <= union
    v, _ = _validator(tax)
    assert not v.is_valid(_doc(doc_type="decision", status="active"))


def test_unrelated_schema_content_is_preserved(tax):
    """Deep comparison: everything except the generator-owned status constraint
    and its marked allOf clause must survive byte-for-byte."""
    before = json.loads(gen.SCHEMA_PATH.read_text(encoding="utf-8"))
    after = gen.render_schema(tax, before)

    def strip_owned(schema):
        s = json.loads(json.dumps(schema))
        s.setdefault("properties", {}).pop("status", None)
        s["allOf"] = [
            c for c in s.get("allOf", [])
            if not (isinstance(c, dict) and c.get("$comment") == gen._SCHEMA_CLAUSE_MARKER)
        ]
        if not s["allOf"]:
            s.pop("allOf")
        return s

    assert strip_owned(after) == strip_owned(before)


def test_foreign_allof_clauses_are_preserved(tax):
    """M1: replacing the whole allOf would silently delete unrelated
    constraints added to the schema later."""
    foreign = {"$comment": "someone-elses-rule", "required": ["title"]}
    before = json.loads(gen.SCHEMA_PATH.read_text(encoding="utf-8"))
    before["allOf"] = [foreign]
    after = gen.render_schema(tax, before)
    assert foreign in after["allOf"]
    assert sum(
        1 for c in after["allOf"] if c.get("$comment") == gen._SCHEMA_CLAUSE_MARKER
    ) == 1


def test_regenerating_does_not_accumulate_owned_clauses(tax):
    """Running twice must not leave two generated clauses behind."""
    schema = json.loads(gen.SCHEMA_PATH.read_text(encoding="utf-8"))
    once = gen.render_schema(tax, schema)
    twice = gen.render_schema(tax, once)
    assert twice == once


def test_document_without_doc_type_uses_the_default_set(tax):
    """The subtlest branch: with doc_type absent the inner `required` fails, so
    `not` succeeds and the default set applies."""
    v, _ = _validator(tax)
    doc = _doc()
    doc.pop("doc_type")
    # status from the default set satisfies the conditional clause...
    errs = [e for e in v.iter_errors({**doc, "status": "active"}) if "status" in str(e.path) or e.validator == "allOf"]
    assert not errs
    # ...and a decision-only status does not.
    assert any(
        e.validator == "allOf" or "status" in str(e.path)
        for e in v.iter_errors({**doc, "status": "superseded"})
    )


# --------------------------------------------------------------- sentinels --


def test_missing_sentinels_raise_without_writing(tax, tmp_path):
    p = tmp_path / "doc.md"
    p.write_text("no sentinels here\n", encoding="utf-8")
    with pytest.raises(gen.GeneratorError, match="no GENERATED:status-list sentinels"):
        gen.render_narrative(tax, p.read_text(), p)
    assert p.read_text() == "no sentinels here\n"


def test_duplicate_sentinel_pair_raises(tax, tmp_path):
    p = tmp_path / "doc.md"
    p.write_text(f"{gen.START}\na\n{gen.END}\n{gen.START}\nb\n{gen.END}\n", encoding="utf-8")
    with pytest.raises(gen.GeneratorError, match="expected exactly one sentinel pair"):
        gen.render_narrative(tax, p.read_text(), p)


def test_partial_sentinel_pair_raises(tax, tmp_path):
    p = tmp_path / "doc.md"
    p.write_text(f"{gen.START}\nunclosed\n", encoding="utf-8")
    with pytest.raises(gen.GeneratorError, match="expected exactly one sentinel pair"):
        gen.render_narrative(tax, p.read_text(), p)


def test_reversed_sentinels_raise(tax, tmp_path):
    p = tmp_path / "doc.md"
    p.write_text(f"{gen.END}\nbackwards\n{gen.START}\n", encoding="utf-8")
    with pytest.raises(gen.GeneratorError, match="END sentinel precedes START"):
        gen.render_narrative(tax, p.read_text(), p)


def test_bootstrap_refuses_when_sentinels_exist(tax, tmp_path):
    p = tmp_path / "doc.md"
    p.write_text(f"### status\n{gen.START}\n{gen.END}\n", encoding="utf-8")
    with pytest.raises(gen.GeneratorError, match="one-time operation"):
        gen.bootstrap_narrative(tax, p.read_text(), p)


# ------------------------------------------------------- region discipline --


def test_prose_outside_the_region_survives(tax):
    """doc-standards.md is part generated, part hand-written. Writing outside
    the region is a defect."""
    text = gen.NARRATIVE_PATH.read_text(encoding="utf-8")
    rendered = gen.render_narrative(tax, text, gen.NARRATIVE_PATH)
    head_before, tail_before = gen._split_on_sentinels(text, gen.NARRATIVE_PATH)
    head_after, tail_after = gen._split_on_sentinels(rendered, gen.NARRATIVE_PATH)
    assert head_before == head_after
    assert tail_before == tail_after
    # The specific prose Kent authored must still be there.
    assert "one step ahead of `in_review`" in rendered


def test_generated_region_is_deterministic(tax):
    assert gen.render_narrative_region(tax) == gen.render_narrative_region(tax)


def test_status_order_follows_source_not_sorted(tax):
    """Sorting would make every diff unreadable (contract invariant 5)."""
    region = gen.render_narrative_region(tax)
    assert "`draft`, `proposed`, `approved`, `superseded`, `deprecated`" in region


# -------------------------------------------------------------- CLI modes --


def test_check_passes_when_fresh(capsys):
    assert gen.main(["--check"]) == 0


def test_check_fails_and_names_a_stale_file(tmp_path, monkeypatch, capsys):
    stale = tmp_path / "frontmatter.schema.json"
    stale.write_text(json.dumps({"properties": {"status": {"enum": ["wrong"]}}}), encoding="utf-8")
    monkeypatch.setattr(gen, "SCHEMA_PATH", stale)
    assert gen.main(["--check"]) == 1
    assert "STALE" in capsys.readouterr().err


def test_write_then_check_is_clean(tmp_path, monkeypatch):
    """NFR-001: a second run stages no diff."""
    schema = tmp_path / "frontmatter.schema.json"
    schema.write_text(gen.SCHEMA_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    narrative = tmp_path / "doc-standards.md"
    narrative.write_text(gen.NARRATIVE_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.setattr(gen, "SCHEMA_PATH", schema)
    monkeypatch.setattr(gen, "NARRATIVE_PATH", narrative)

    assert gen.main([]) == 0
    first = (schema.read_text(), narrative.read_text())
    assert gen.main([]) == 0
    assert (schema.read_text(), narrative.read_text()) == first
    assert gen.main(["--check"]) == 0


def test_malformed_taxonomy_fails_closed(tmp_path, monkeypatch, capsys):
    """A broken source must stop the generator, not produce output from
    fallbacks."""
    bad = tmp_path / "allowed-values.json"
    bad.write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(gen, "load_taxonomy", lambda *a, **k: (_ for _ in ()).throw(
        __import__("doc_taxonomy").TaxonomyError(f"{bad}: invalid JSON")
    ))
    assert gen.main([]) == 2
    assert "invalid JSON" in capsys.readouterr().err


# ------------------------------------------------------ bootstrap precision --


def test_bootstrap_replaces_only_the_status_list_line(tax, tmp_path):
    """Regression: an earlier bootstrap filtered the section by dropping lines
    that begin with a backtick, which deleted a line of authored prose opening
    with an inline code span and left an orphaned sentence fragment."""
    target = ", ".join(f"`{s}`" for s in tax.default_statuses)
    prose = "`proposed` sits one step ahead of `in_review`: the artifact is complete."
    p = tmp_path / "doc.md"
    p.write_text(f"# Doc\n\n### status\n\n{target}\n\n{prose}\n\n### level\n\n`overview`\n", encoding="utf-8")

    out = gen.bootstrap_narrative(tax, p.read_text(), p)

    assert prose in out, "authored prose starting with a code span must survive"
    assert "### level" in out and "`overview`" in out
    assert out.count(gen.START) == 1 and out.count(gen.END) == 1
    # Purely additive: nothing but the one list line is removed.
    assert target not in out.split(gen.START)[0]


def test_bootstrap_refuses_an_ambiguous_target(tax, tmp_path):
    """Two identical status lines means the generator cannot know which is the
    real one — refuse rather than guess."""
    target = ", ".join(f"`{s}`" for s in tax.default_statuses)
    p = tmp_path / "doc.md"
    p.write_text(f"### status\n\n{target}\n\nlater:\n\n{target}\n", encoding="utf-8")
    with pytest.raises(gen.GeneratorError, match="expected exactly one line"):
        gen.bootstrap_narrative(tax, p.read_text(), p)


def test_bootstrap_refuses_when_no_status_line_matches(tax, tmp_path):
    p = tmp_path / "doc.md"
    p.write_text("### status\n\n`something`, `else`\n", encoding="utf-8")
    with pytest.raises(gen.GeneratorError, match="expected exactly one line"):
        gen.bootstrap_narrative(tax, p.read_text(), p)


def test_sentinel_must_be_a_standalone_line(tax, tmp_path):
    """M3: substring matching made content sharing a line with a marker
    destroyable, and a fenced example a writable region."""
    p = tmp_path / "doc.md"
    p.write_text(f"before {gen.START} KEEP-HEAD\ninside\n{gen.END} KEEP-TAIL\nafter\n", encoding="utf-8")
    with pytest.raises(gen.GeneratorError, match="other than as a standalone line"):
        gen.render_narrative(tax, p.read_text(), p)


def test_bootstrap_will_not_target_a_line_outside_the_status_section(tax, tmp_path):
    """M2: demonstrated — with the status section stale, the region was
    inserted into an unrelated appendix."""
    target = ", ".join(f"`{s}`" for s in tax.default_statuses)
    p = tmp_path / "doc.md"
    p.write_text(f"### status\n\nstale, no list here\n\n### appendix\n\n{target}\n", encoding="utf-8")
    with pytest.raises(gen.GeneratorError, match="inside the '### status' section"):
        gen.bootstrap_narrative(tax, p.read_text(), p)


def test_bootstrap_requires_exactly_one_status_heading(tax, tmp_path):
    target = ", ".join(f"`{s}`" for s in tax.default_statuses)
    p = tmp_path / "doc.md"
    p.write_text(f"### status\n\n{target}\n\n### status\n\nagain\n", encoding="utf-8")
    with pytest.raises(gen.GeneratorError, match="exactly one '### status' heading"):
        gen.bootstrap_narrative(tax, p.read_text(), p)


# ------------------------------------------------- review cycle 2 regressions --


def test_legacy_unmarked_status_clause_is_refused(tax):
    """M1: a pre-marker generated clause would survive as 'foreign' and produce
    two active status rules."""
    before = json.loads(gen.SCHEMA_PATH.read_text(encoding="utf-8"))
    before["allOf"] = [{"if": {}, "then": {"properties": {"status": {"enum": ["legacy"]}}}}]
    with pytest.raises(gen.GeneratorError, match="unmarked allOf clause constrains"):
        gen.render_schema(tax, before)


@pytest.mark.parametrize("heading", ["## appendix", "# appendix", "   ### appendix", "###\tappendix"])
def test_bootstrap_section_ends_at_any_heading(tax, tmp_path, heading):
    """M2: matching only an unindented '### ' let these be crossed."""
    target = ", ".join(f"`{s}`" for s in tax.default_statuses)
    p = tmp_path / "doc.md"
    p.write_text(f"### status\n\nstale\n\n{heading}\n\n{target}\n", encoding="utf-8")
    with pytest.raises(gen.GeneratorError, match="inside the '### status' section"):
        gen.bootstrap_narrative(tax, p.read_text(), p)


def test_sentinels_inside_a_fenced_block_are_not_boundaries(tax, tmp_path):
    """M3: documentation about this generator legitimately shows the markers."""
    p = tmp_path / "doc.md"
    p.write_text(
        f"prose\n\n```md\n{gen.START}\nexample\n{gen.END}\n```\n\nmore prose\n", encoding="utf-8"
    )
    with pytest.raises(gen.GeneratorError, match="no GENERATED:status-list sentinels"):
        gen.render_narrative(tax, p.read_text(), p)


def test_real_sentinels_still_found_alongside_a_fenced_example(tax, tmp_path):
    p = tmp_path / "doc.md"
    p.write_text(
        f"```md\n{gen.START}\nexample\n{gen.END}\n```\n\n{gen.START}\nold\n{gen.END}\ntail\n",
        encoding="utf-8",
    )
    out = gen.render_narrative(tax, p.read_text(), p)
    assert "example" in out and "tail" in out
    assert "`superseded`" in out


def test_trailing_newline_state_is_preserved(tax, tmp_path):
    """New defect from cycle 1's fix: a file ending directly after END must not
    gain a newline."""
    no_nl = f"head\n{gen.START}\nold\n{gen.END}"
    assert not gen.render_narrative(tax, no_nl, tmp_path / "d.md").endswith("\n")
    with_nl = f"head\n{gen.START}\nold\n{gen.END}\n"
    assert gen.render_narrative(tax, with_nl, tmp_path / "d.md").endswith("\n")


# ------------------------------------------------- review cycle 3 regressions --


def test_mismatched_fence_does_not_close_the_block(tax, tmp_path):
    """CommonMark: a closer must use the same char. Treating any fence as a
    closer reopened the document and exposed fenced sentinels as writable."""
    p = tmp_path / "doc.md"
    p.write_text(
        f"```md\n{gen.START}\nexample\n{gen.END}\n~~~\nstill inside\n```\n\nprose\n",
        encoding="utf-8",
    )
    with pytest.raises(gen.GeneratorError, match="no GENERATED:status-list sentinels"):
        gen.render_narrative(tax, p.read_text(), p)


def test_shorter_fence_does_not_close_a_longer_opener(tax, tmp_path):
    """A closer must be at least as long as the opener."""
    p = tmp_path / "doc.md"
    p.write_text(
        f"````md\n{gen.START}\nexample\n{gen.END}\n```\nstill inside\n````\n", encoding="utf-8"
    )
    with pytest.raises(gen.GeneratorError, match="no GENERATED:status-list sentinels"):
        gen.render_narrative(tax, p.read_text(), p)


def test_longer_closer_does_close(tax, tmp_path):
    """The converse must still work, or real content becomes unreachable."""
    p = tmp_path / "doc.md"
    p.write_text(
        f"```md\nexample\n``````\n\n{gen.START}\nold\n{gen.END}\ntail\n", encoding="utf-8"
    )
    out = gen.render_narrative(tax, p.read_text(), p)
    assert "example" in out and "tail" in out and "`superseded`" in out


def test_foreign_clause_merely_annotating_status_is_allowed(tax):
    """The narrowed guard must not reject a legitimate foreign clause. The
    earlier 'mentions status anywhere' version did."""
    before = json.loads(gen.SCHEMA_PATH.read_text(encoding="utf-8"))
    annotation = {"$comment": "someone else", "properties": {"status": {"description": "note"}}}
    before["allOf"] = [annotation]
    after = gen.render_schema(tax, before)
    assert annotation in after["allOf"]


def test_legacy_enum_clause_is_still_refused(tax):
    """...while the actual hazard — our own pre-marker shape — still is."""
    before = json.loads(gen.SCHEMA_PATH.read_text(encoding="utf-8"))
    before["allOf"] = [
        {"if": {"properties": {"doc_type": {"const": "decision"}}},
         "then": {"properties": {"status": {"enum": ["legacy"]}}}}
    ]
    with pytest.raises(gen.GeneratorError, match="unmarked allOf clause constrains"):
        gen.render_schema(tax, before)
