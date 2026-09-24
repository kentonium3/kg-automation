"""Tests for the #849 hidden-oracle contract checker (rubric §3.1).

The rule this checker exists for — an oracle point with empty traceability
fails — is the mechanical form of a defect found three times by hand during
synthesis. Each test below injects a specific violation and requires rejection,
because a checker that only ever passes would be worse than none: it would
create the impression the contract is enforced.
"""

from __future__ import annotations

import pathlib
import sys

import pytest
import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
SYNTH = REPO_ROOT / "docs" / "design" / "research" / "849-synthesis"
ORACLE_DIR = SYNTH / "oracle"
SEED_DIR = SYNTH / "seed"
sys.path.insert(0, str(REPO_ROOT))

from scripts.research.check_849_oracle import (  # noqa: E402
    _seed_ids,
    check_file,
    strip_comments,
)

GOOD = """
question: B1
ask_time: 2026-08-17T09:00:00-04:00
question_text: "Am I on track?"
must_identify:
  - id: B1-1
    statement: "no"
    required_values: ["no"]
    traceability: [OUT_5K]
"""


def _write(tmp_path: pathlib.Path, text: str, name: str = "B1.yaml") -> pathlib.Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


# --------------------------------------------------------------------------
# The committed artifacts must conform
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path", sorted(ORACLE_DIR.glob("*.yaml")), ids=lambda p: p.name
)
def test_committed_oracle_files_conform(path):
    assert check_file(path, _seed_ids()) == []


def test_there_is_at_least_one_oracle_file():
    """Guards the vacuous case — an empty glob makes the test above pass."""
    assert list(ORACLE_DIR.glob("*.yaml"))


def test_every_committed_oracle_point_has_traceability():
    """The rule, asserted against the real files rather than a fixture."""
    for path in ORACLE_DIR.glob("*.yaml"):
        if path.name.endswith("-appendix.yaml"):
            continue
        doc = yaml.safe_load(strip_comments(path.read_text(encoding="utf-8")))
        for point in doc["must_identify"]:
            assert point["traceability"], (path.name, point["id"])


# --------------------------------------------------------------------------
# Injected violations
# --------------------------------------------------------------------------


def test_empty_traceability_is_rejected(tmp_path):
    text = GOOD.replace("traceability: [OUT_5K]", "traceability: []")
    problems = check_file(_write(tmp_path, text), {"OUT_5K"})
    assert any("EMPTY traceability" in p for p in problems), problems


def test_traceability_naming_an_unknown_id_is_rejected(tmp_path):
    """A typo is indistinguishable from a real reference by eye."""
    text = GOOD.replace("traceability: [OUT_5K]", "traceability: [OUT_5KK]")
    problems = check_file(_write(tmp_path, text), {"OUT_5K"})
    assert any("not found in any seed" in p for p in problems), problems


@pytest.mark.parametrize("key", ["question", "ask_time", "question_text", "must_identify"])
def test_a_missing_top_level_key_is_rejected(tmp_path, key):
    doc = yaml.safe_load(GOOD)
    doc.pop(key)
    problems = check_file(_write(tmp_path, yaml.safe_dump(doc)), {"OUT_5K"})
    assert any("missing required key" in p for p in problems), (key, problems)


@pytest.mark.parametrize("key", ["id", "statement", "required_values", "traceability"])
def test_a_missing_point_key_is_rejected(tmp_path, key):
    doc = yaml.safe_load(GOOD)
    doc["must_identify"][0].pop(key)
    problems = check_file(_write(tmp_path, yaml.safe_dump(doc)), {"OUT_5K"})
    assert any("missing key" in p for p in problems), (key, problems)


def test_a_non_iso_ask_time_is_rejected(tmp_path):
    """The ask_time is the time cut; ambiguity changes what every arm sees."""
    text = GOOD.replace("ask_time: 2026-08-17T09:00:00-04:00", 'ask_time: "mid-August"')
    problems = check_file(_write(tmp_path, text), {"OUT_5K"})
    assert any("ISO instant" in p for p in problems), problems


def test_duplicate_point_ids_are_rejected(tmp_path):
    doc = yaml.safe_load(GOOD)
    doc["must_identify"].append(dict(doc["must_identify"][0]))
    problems = check_file(_write(tmp_path, yaml.safe_dump(doc)), {"OUT_5K"})
    assert any("duplicate oracle point id" in p for p in problems), problems


def test_an_empty_must_identify_is_rejected(tmp_path):
    doc = yaml.safe_load(GOOD)
    doc["must_identify"] = []
    problems = check_file(_write(tmp_path, yaml.safe_dump(doc)), {"OUT_5K"})
    assert any("nothing would be scored" in p for p in problems), problems


def test_an_oracle_file_in_the_seed_directory_is_rejected(tmp_path, monkeypatch):
    import scripts.research.check_849_oracle as mod

    monkeypatch.setattr(mod, "SEED_DIR", tmp_path)
    problems = mod.check_file(_write(tmp_path, GOOD), {"OUT_5K"})
    assert any("must not live in the seed directory" in p for p in problems), problems


def test_an_appendix_is_exempt_from_the_question_contract(tmp_path):
    text = "meta: {arc: B, appendix_for: [B1, B2]}\ncounted_misses: []\n"
    assert check_file(_write(tmp_path, text, "arc-b-appendix.yaml"), set()) == []


# --------------------------------------------------------------------------
# The seed/emits contract that makes traceability checkable
# --------------------------------------------------------------------------


def test_declared_emits_are_treated_as_known_ids():
    """A seed declares the rendered-event ids its generator must produce.

    Without this, every traceability entry naming a generated event would fail
    until the renderer exists — and the pressure would be to drop the check.
    """
    ids = _seed_ids()
    assert "GEN_B_SESSIONS" in ids
    assert "SHARED_LATE_NIGHTS" in ids


def test_every_emitted_id_referenced_by_an_oracle_is_declared_by_some_seed():
    """The two-way contract: the renderer is bound to produce exactly these."""
    declared = _seed_ids()
    for path in ORACLE_DIR.glob("*.yaml"):
        if path.name.endswith("-appendix.yaml"):
            continue
        doc = yaml.safe_load(strip_comments(path.read_text(encoding="utf-8")))
        for point in doc["must_identify"]:
            for ref in point["traceability"]:
                assert ref in declared, (path.name, point["id"], ref)


# --------------------------------------------------------------------------
# required_values must be honest literals, not verdict words
# --------------------------------------------------------------------------


@pytest.mark.parametrize("token", ["no", "yes", "three", "five", "never", "first"])
def test_a_brittle_required_value_is_rejected(tmp_path, token):
    """A verdict word or spelled-out number marks a correct answer wrong.

    "not on track" is a hit that lacks "no"; "3x" is a hit that lacks "three".
    B1-1 was written this way and the design lead caught it.
    """
    text = GOOD.replace('required_values: ["no"]', f'required_values: ["{token}"]')
    problems = check_file(_write(tmp_path, text), {"OUT_5K"})
    assert any("brittle required_value" in p for p in problems), (token, problems)


@pytest.mark.parametrize("token", ["2026-08-09", "07:30", "29", "32:50", "Fred Okafor"])
def test_an_honest_literal_is_accepted(tmp_path, token):
    text = GOOD.replace('required_values: ["no"]', f'required_values: ["{token}"]')
    assert check_file(_write(tmp_path, text), {"OUT_5K"}) == []


def test_committed_oracles_carry_no_brittle_required_values():
    import yaml as _yaml

    from scripts.research.check_849_oracle import _brittle

    for path in ORACLE_DIR.glob("*.yaml"):
        if path.name.endswith("-appendix.yaml"):
            continue
        doc = _yaml.safe_load(strip_comments(path.read_text(encoding="utf-8")))
        for point in doc["must_identify"]:
            assert not _brittle(point["required_values"]), (path.name, point["id"])


# --------------------------------------------------------------------------
# Completeness — every question in the rubric has an oracle
# --------------------------------------------------------------------------

#: The eight questions rubric §3 defines. An arc with no oracle cannot be
#: scored, and the failure would surface only when the run produced no number
#: for it — after the corpus was frozen.
EXPECTED_QUESTIONS = {"A", "B1", "B2", "C1", "E1", "E2", "F1", "F2"}


def test_every_rubric_question_has_an_oracle():
    present = {
        yaml.safe_load(strip_comments(p.read_text(encoding="utf-8")))["question"]
        for p in ORACLE_DIR.glob("*.yaml")
        if not p.name.endswith("-appendix.yaml")
    }
    assert present == EXPECTED_QUESTIONS, {
        "missing": sorted(EXPECTED_QUESTIONS - present),
        "unexpected": sorted(present - EXPECTED_QUESTIONS),
    }


def test_each_oracle_declares_wrong_answers_and_grader_notes():
    """Precision scoring needs wrong answers; a bare must_identify is half a test."""
    for path in ORACLE_DIR.glob("*.yaml"):
        if path.name.endswith("-appendix.yaml"):
            continue
        doc = yaml.safe_load(strip_comments(path.read_text(encoding="utf-8")))
        assert doc.get("wrong_answers"), path.name
        assert doc.get("grader_notes"), path.name


def test_ask_times_are_ordered_within_each_arc():
    """A retrospective question must not be asked before its mid-journey one."""
    docs = {}
    for path in ORACLE_DIR.glob("*.yaml"):
        if path.name.endswith("-appendix.yaml"):
            continue
        d = yaml.safe_load(strip_comments(path.read_text(encoding="utf-8")))
        docs[d["question"]] = str(d["ask_time"])

    assert docs["B1"] < docs["B2"], (docs["B1"], docs["B2"])
    assert docs["F1"] < docs["F2"], (docs["F1"], docs["F2"])
