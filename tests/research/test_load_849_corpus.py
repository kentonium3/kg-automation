"""Tests for the #849 loader and its structural pass.

The per-ask_time checks all pass against the real corpus, which is the result
you cannot distinguish from a check that is not running. Every check here is
therefore paired with an injected defect proving it discriminates — the lesson
from the synthesis, where two checks passed because the thing they examined was
empty rather than clean.
"""

from __future__ import annotations

import json
import pathlib
import sys
from datetime import datetime

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from scripts.research import check_849_loader as chk  # noqa: E402
from scripts.research import load_849_corpus as ldr  # noqa: E402

CORPUS = ldr.DEFAULT_CORPUS
F1 = datetime.fromisoformat("2026-08-10T09:00:00-04:00")
B2 = datetime.fromisoformat("2026-10-16T09:00:00-04:00")

pytestmark = pytest.mark.skipif(
    not (CORPUS / "entities.json").exists(),
    reason="rendered corpus absent; run render_849_corpus first")


# --------------------------------------------------------------------------
# The fingerprint gate
# --------------------------------------------------------------------------


def test_gate_accepts_the_registered_corpus():
    assert ldr.verify_registration(CORPUS)


def test_gate_refuses_a_modified_corpus(tmp_path):
    """The gate is the whole reason a run's numbers mean anything."""
    for name in ("stream.jsonl", "entities.json", "manifest.json"):
        (tmp_path / name).write_bytes((CORPUS / name).read_bytes())
    with (tmp_path / "stream.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"ref": "e99999", "at": "2026-01-01", "channel": "note"}) + "\n")

    with pytest.raises(ldr.UnfrozenCorpus) as exc:
        ldr.verify_registration(tmp_path)
    assert "stream.jsonl" in str(exc.value)
    assert ldr.REGISTRATION["files"]["stream.jsonl"] in str(exc.value)


def test_gate_refuses_a_scaled_corpus(tmp_path):
    """A scaled corpus is for a fast loop and must never reach a run."""
    import scripts.research.render_849_corpus as renderer
    renderer.main(["render", "--out", str(tmp_path), "--scale", "20"])
    with pytest.raises(ldr.UnfrozenCorpus):
        ldr.verify_registration(tmp_path)


# --------------------------------------------------------------------------
# Replay — the leak this was built to close
# --------------------------------------------------------------------------


def test_f1_cannot_see_the_september_restart():
    """DEC_F_RESTART is decided six weeks AFTER F1 asks whether the
    non-negotiables are being kept. Presenting it hands F1 its answer."""
    loaded = ldr.replay(CORPUS, F1, verify=False)
    assert "DEC_F_RESTART" not in loaded.by_id
    assert "DEC_F_RESTART" in loaded.withheld["entities"]


def test_decided_edges_inherit_their_decision_timestamp():
    """The edges out of a Decision carry made_at: None.

    Without inheritance they survive a filter that removed their own source
    node, leaving an edge that names the withheld decision and states its
    disposition while pointing at an id the arm cannot resolve.
    """
    loaded = ldr.replay(CORPUS, F1, verify=False)
    assert not [e for e in loaded.edges if e["from"] == "DEC_F_RESTART"]
    assert chk.check_no_dangling_edges(loaded) == []


def test_the_last_question_sees_everything():
    """Guards the vacuous case: a replay that withheld everything would pass
    every leak test above."""
    loaded = ldr.replay(CORPUS, B2, verify=False)
    entities = json.loads((CORPUS / "entities.json").read_text(encoding="utf-8"))
    assert len(loaded.entities) + len(loaded.edges) == len(entities)
    assert loaded.withheld.get("entities") is None
    assert len(loaded.events) > 5000


def test_a_person_is_not_created_by_a_meeting_being_scheduled():
    """The first visibility rule applied to every definitional kind and made
    PER_FRED invisible until the commitment naming him was made."""
    early = ldr.replay(CORPUS, datetime.fromisoformat("2026-01-05T09:00:00-05:00"),
                       verify=False)
    assert "PER_FRED" in early.by_id


# --------------------------------------------------------------------------
# Each structural check discriminates
# --------------------------------------------------------------------------


def test_dangling_edge_check_fires_when_an_endpoint_is_removed():
    loaded = ldr.replay(CORPUS, B2, verify=False)
    assert chk.check_no_dangling_edges(loaded) == []
    loaded.entities = [e for e in loaded.entities if e.get("id") != "PER_MARCUS"]
    assert chk.check_no_dangling_edges(loaded)


def test_future_material_check_fires_on_a_late_event():
    loaded = ldr.replay(CORPUS, F1, verify=False)
    assert chk.check_no_future_material(loaded, F1) == []
    loaded.events.append({"ref": "e99999", "at": "2026-12-25T09:00:00-05:00"})
    assert chk.check_no_future_material(loaded, F1)


def test_absence_check_fires_when_something_points_at_the_design_review():
    loaded = ldr.replay(CORPUS, B2, verify=False)
    assert chk.check_structural_absences(loaded, "test") == []
    loaded.edges.append({"kind": "Edge", "from": "PER_MARCUS", "type": "GATED_ON",
                         "to": "COM_DESIGN_REVIEW"})
    assert chk.check_structural_absences(loaded, "test")


def test_absence_check_fires_when_the_launch_carries_completion():
    loaded = ldr.replay(CORPUS, B2, verify=False)
    for entity in loaded.entities:
        if entity.get("id") == "OUT_LAUNCH":
            entity["status"] = "shipped"
            break
    else:
        pytest.fail("OUT_LAUNCH is not in the corpus — this test is stale")
    assert chk.check_structural_absences(loaded, "test")


def test_vocabulary_check_fires_on_a_forbidden_token():
    loaded = ldr.replay(CORPUS, B2, verify=False)
    assert chk.check_no_forbidden_vocabulary(loaded) == []
    loaded.entities.append({"kind": "Task", "id": "T_X", "description": "near_miss"})
    assert chk.check_no_forbidden_vocabulary(loaded)


def test_entity_allowlist_is_default_deny(tmp_path):
    """The gap `arcs` walked through: the renderer's allowlist covers events
    only, so a field added to a seed reaches every arm untouched."""
    entities = [{"kind": "Task", "id": "T_X", "description": "ok",
                 "internal_label": "arc-A-decoy"}]
    (tmp_path / "entities.json").write_text(json.dumps(entities), encoding="utf-8")
    problems = chk.check_entity_properties(tmp_path)
    assert any("internal_label" in p for p in problems), problems


def test_edge_type_set_is_closed(tmp_path):
    entities = [{"kind": "Edge", "from": "A", "to": "B", "type": "INVENTED"}]
    (tmp_path / "entities.json").write_text(json.dumps(entities), encoding="utf-8")
    assert chk.check_edge_types(tmp_path)


def test_loader_links_check_fires_when_the_file_is_absent(tmp_path):
    assert chk.check_loader_links_exist(tmp_path)


def test_loader_links_check_passes_when_present(tmp_path):
    (tmp_path / "loader_links.jsonl").write_text(
        json.dumps({"ref": "e00009", "mentions": ["PER_MARCUS"]}) + "\n", encoding="utf-8")
    assert chk.check_loader_links_exist(tmp_path) == []
