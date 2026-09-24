"""Tests for the #849 renderer.

The renderer is the last artifact before freeze and the first one an arm
actually sees, so its failure modes are the expensive ones: a leaked comment
solves an arc outright, a missing emit makes an oracle point unverifiable, and
a non-deterministic corpus makes 3-repeats-per-arm meaningless.

Every test here asserts a property of the REAL rendered output rather than a
fixture, because the whole lesson of this synthesis has been that checks which
run against fixtures pass while the real artifacts are wrong.
"""

from __future__ import annotations

import json
import pathlib
import sys

import pytest
import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
SEED_DIR = REPO_ROOT / "docs" / "design" / "research" / "849-synthesis" / "seed"
sys.path.insert(0, str(REPO_ROOT))

from scripts.research.render_849_corpus import (  # noqa: E402
    load_all,
    render,
    rendered_view,
    strip_comments,
)

SCALE = 20  # keep the suite fast; the full-scale properties are asserted below


@pytest.fixture(scope="module")
def rendered():
    corpus, problems = render(scale=SCALE)
    return corpus, problems


def _text(corpus) -> str:
    return json.dumps(corpus.events, default=str) + json.dumps(corpus.entities, default=str)


# --------------------------------------------------------------------------
# The emits contract
# --------------------------------------------------------------------------


def test_every_declared_emit_is_produced(rendered):
    """A declared emit that is never produced leaves an oracle point unverifiable."""
    _, problems = rendered
    assert problems == []


def test_the_contract_actually_fails_when_an_emit_is_missing(monkeypatch):
    """Guards the vacuous case: prove the check can fail.

    Without this, a renderer that silently produced nothing would still pass
    the test above if the declared set were also empty.
    """
    import scripts.research.render_849_corpus as mod

    real = mod.load_all

    def _with_phantom_emit():
        seeds = real()
        seeds["arc-a"]["meta"]["emits"] = list(
            seeds["arc-a"]["meta"]["emits"]) + ["GEN_A_PHANTOM"]
        return seeds

    monkeypatch.setattr(mod, "load_all", _with_phantom_emit)
    _, problems = mod.render(scale=SCALE)
    assert any("GEN_A_PHANTOM" in p for p in problems), problems


# --------------------------------------------------------------------------
# Nothing that would solve an arc may reach the output
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "phrase",
    [
        "14:00-15:45",        # Arc A: the true footprint, solves it outright
        "true footprint",
        "travel_missing",
        "point of no return",  # Arc B
        "then_silent",
        "triage session",     # Arc E
        "the same five",
        "near-miss",          # every arc
        "near_miss",
        "sporadic",           # Arc F phase label
    ],
)
def test_oracle_phrases_never_reach_the_rendered_corpus(rendered, phrase):
    corpus, _ = rendered
    assert phrase.lower() not in _text(corpus).lower()


@pytest.mark.parametrize(
    "key",
    ["generator_input", "shared_late_nights", "email_first_mornings",
     "near_miss_rules", "e2_sample_week", "scored_items", "non_drifting_control"],
)
def test_declared_non_rendered_blocks_never_reach_the_corpus(rendered, key):
    corpus, _ = rendered
    assert key not in _text(corpus)


def test_rendered_view_drops_exactly_the_declared_blocks():
    for name, doc in load_all().items():
        declared = set((doc.get("meta") or {}).get("non_rendered") or [])
        view = rendered_view(doc)
        assert not (declared & set(view)), (name, declared & set(view))
        assert "meta" not in view, name


def test_seed_comments_are_stripped_before_parsing():
    """Seed comments quote oracle content; anything derived must use DATA."""
    raw = (SEED_DIR / "arc-a.yaml").read_text(encoding="utf-8")
    assert "True footprint" in raw, "the comment this test is about has moved"
    assert "True footprint" not in strip_comments(raw)


# --------------------------------------------------------------------------
# Determinism
# --------------------------------------------------------------------------


def test_two_renders_are_identical():
    """3 repeats per arm are meaningless on a corpus that varies between runs."""
    a, _ = render(scale=SCALE)
    b, _ = render(scale=SCALE)
    assert json.dumps(a.events, default=str) == json.dumps(b.events, default=str)
    assert json.dumps(a.entities, default=str) == json.dumps(b.entities, default=str)


# --------------------------------------------------------------------------
# Cross-arc constraints the corpus must satisfy
# --------------------------------------------------------------------------


def test_the_wednesday_counter_offer_slot_is_free(rendered):
    """Arc A's answer is only unique if nothing else occupies that hour.

    Scoped to CALENDAR events: an email arriving at 14:25 does not occupy a
    meeting slot, and the first version of this check counted it.
    """
    corpus, _ = rendered
    clash = [
        e for e in corpus.events
        if e.get("channel") == "calendar"
        and str(e.get("start") or e.get("at") or "").startswith("2026-06-10")
        and str(e.get("start") or e.get("at") or "") < "2026-06-10T15:00"
        and str(e.get("end") or e.get("start") or e.get("at") or "") > "2026-06-10T14:00"
    ]
    assert clash == [], clash


def test_the_shared_late_nights_are_one_event_set(rendered):
    """Arc F owns them and Arc B consumes them (R5).

    Two parallel fabrications that merely agreed would let an arm "find" a
    shared cause the corpus does not actually share — and F2-4, the
    highest-value point, scores exactly that.
    """
    corpus, _ = rendered

    # Identified by TIME, not by a `week` field. The field was programme-
    # relative and the stream allowlist now strips it (freeze finding L5): a
    # real git commit has no programme week, and carrying one would align the
    # arm to the oracle's frame for free.
    #
    # This test previously leaned on that field — a test resting on a leak.
    late = [
        e for e in corpus.events
        if e.get("direction") == "outbound"
        and e.get("channel") in {"git", "email", "slack"}
        and "23:" <= str(e["at"])[11:16] <= "23:59"
    ]
    assert late, "no shared late-night events were rendered"

    # They must fall in the window both arcs draw on, which is what makes the
    # shared cause shared rather than two agreeing fabrications.
    months = {str(e["at"])[:7] for e in late}
    assert months & {"2026-05", "2026-06", "2026-07"}, months


def test_silent_misses_produce_no_event(rendered):
    """Completions-only: a silent miss is an ABSENCE, not a record.

    This is the interaction that the emits contract surfaced — two rules each
    correct alone ("completions only" and "every declared emit is produced")
    collided, and three ids were declared for events that cannot exist.
    """
    doc = load_all()["arc-b"]
    # `cause` replaced `reason` when L1 turned reasons into primitive TYPES.
    # A silent miss has no cause at all: nothing happened that an adapter
    # could have recorded, which is exactly what makes it silent.
    silent = [
        (w["wk"], m["day"])
        for w in doc["generator_input"]["weeks"]
        for m in (w.get("missed") or [])
        if not m.get("cause")
    ]
    assert silent, "the seed no longer has silent misses — this test is stale"
    declared = set(doc["meta"]["emits"])
    for wk, day in silent:
        assert f"GEN_B_WK{wk}_{day.upper()}" not in declared, (wk, day)


def test_the_manifest_marks_a_scaled_corpus_invalid_for_a_run(tmp_path):
    import scripts.research.render_849_corpus as mod

    mod.main(["render", "--out", str(tmp_path), "--scale", "20"])
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    assert manifest["scale"] == 20
    assert manifest["valid_for_run"] is False


# --------------------------------------------------------------------------
# Emit families and traceability of every emitted id (R-c)
# --------------------------------------------------------------------------


def test_every_emitted_id_is_declared_or_a_seed_id(rendered):
    """An id the renderer invented cannot be traced by any oracle point."""
    _, problems = rendered
    assert not [p for p in problems if "neither a declared emit" in p], problems


def test_an_invented_emit_id_is_rejected(monkeypatch):
    import scripts.research.render_849_corpus as mod

    real_gen = mod.generate_arc_b

    def _with_invented(corpus, doc, scale):
        real_gen(corpus, doc, scale)
        corpus.event("GEN_INVENTED_BY_RENDERER", "2026-06-01T09:00", "note", {})

    monkeypatch.setitem(mod.GENERATORS, "arc-b", _with_invented)
    _, problems = mod.render(scale=SCALE)
    assert any("GEN_INVENTED_BY_RENDERER" in p for p in problems), problems


def test_a_declared_family_with_no_members_is_rejected(monkeypatch):
    """A family declared but empty is as defective as an unproduced literal."""
    import scripts.research.render_849_corpus as mod

    real = mod.load_all

    def _with_empty_family():
        seeds = real()
        seeds["arc-a"]["meta"]["emits"] = list(
            seeds["arc-a"]["meta"]["emits"]) + ["GEN_A_NOTHING_*"]
        return seeds

    monkeypatch.setattr(mod, "load_all", _with_empty_family)
    _, problems = mod.render(scale=SCALE)
    assert any("produced no members" in p for p in problems), problems


def test_arc_b_states_no_reason_for_a_miss(rendered):
    """L1: a reason sentence states the finding instead of showing it."""
    corpus, _ = rendered
    blob = _text(corpus).lower()
    for phrase in ["booked into the slot", "then not run", "meeting series",
                   "favour after work", "moved to evening, then"]:
        assert phrase not in blob, phrase


def test_arc_b_renders_the_collision_as_a_recurring_series(rendered):
    """The 07:30 meeting must exist as a real calendar series the arm can see
    colliding with the quality-run slot — not as a sentence saying it did."""
    corpus, _ = rendered
    series = [e for e in corpus.events
              if e.get("channel") == "calendar"
              and e.get("title") == "Weekly pipeline review"]
    assert len(series) >= 3, len(series)
    assert all(str(e.get("start", ""))[11:16] == "07:30" for e in series)


# --------------------------------------------------------------------------
# Reproducibility beyond this process
# --------------------------------------------------------------------------


def test_the_render_path_has_no_wall_clock_dependency():
    """A corpus that changes tomorrow breaks 3-repeats-per-arm as badly as one
    that changes between processes.

    Determinism within a run is already asserted above; this is the other half.
    Verified separately that a clean clone renders byte-identically — this
    static check is what keeps it true when someone adds a timestamp later.
    """
    import re as _re

    watched = [
        REPO_ROOT / "scripts" / "research" / "render_849_corpus.py",
        REPO_ROOT / "scripts" / "research" / "check_849_freeze.py",
    ]
    banned = _re.compile(r"\b(datetime\.now|date\.today|utcnow|time\.time)\b")
    for path in watched:
        src = "\n".join(
            line for line in path.read_text(encoding="utf-8").splitlines()
            if not line.strip().startswith("#")
        )
        assert not banned.search(src), f"{path.name} reads the wall clock"


def test_every_generator_rng_is_seeded_from_a_stable_label():
    """An unseeded Random would make the corpus differ per process."""
    import re as _re

    src = (REPO_ROOT / "scripts" / "research" / "render_849_corpus.py").read_text(
        encoding="utf-8")
    # The only construction site is the _rng helper, which always takes a label.
    constructions = _re.findall(r"random\.Random\(([^)]*)\)", src)
    assert constructions, "no Random construction found — has the helper moved?"
    assert all(arg.strip() for arg in constructions), constructions
