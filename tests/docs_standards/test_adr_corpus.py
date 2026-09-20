"""SC-001: every decision document states its own standing and history.

This is the whole point of #987. The defect was that state *about* a document
lived *somewhere else*, so a reader of the document was misled. It happened
three times, and the third was observed live on 2026-09-18 when an agent read
ADR-0008, hit reasoning that had been corrected three weeks earlier in
ADR-0004's log, and reported it as a new finding.

So these tests assert the property directly: for each ADR, standing and
complete amendment history are derivable from THAT FILE ALONE.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
ADR_DIR = REPO / "docs" / "design" / "architecture" / "adr"
sys.path.insert(0, str(REPO / "tooling" / "scripts"))

from doc_taxonomy import load_taxonomy  # noqa: E402

ADRS = sorted(ADR_DIR.glob("0*.md"))


def fm(path: Path) -> dict:
    m = re.match(r"^---\n(.*?)\n---", path.read_text(encoding="utf-8"), re.S)
    assert m, f"{path.name} has no frontmatter"
    return yaml.safe_load(m.group(1))


def test_the_corpus_is_not_empty():
    assert len(ADRS) >= 9, "expected the nine live ADRs"


@pytest.mark.parametrize("adr", ADRS, ids=lambda p: p.name[:4])
def test_every_adr_is_typed_decision(adr):
    assert fm(adr)["doc_type"] == "decision"


#: The migration matrix, transcribed — the state at MIGRATION TIME.
#:
#: These are NOT current-state assertions. The whole point of the feature is
#: that an ADR's standing changes and its log grows, so freezing either would
#: forbid the evolution this exists to enable: a legitimate status transition
#: would fail, an appended row would fail, and ADR-0010 would raise KeyError
#: against a matrix that stops at 0009 (#987 post-merge review F2).
#:
#: What IS durable: the log is append-only, so the seeded rows must remain an
#: ordered PREFIX of it forever. That is what these assert.
MIGRATION_SEED = {
    "0001": [],
    "0002": [("2026-07-23", "amendment")],
    "0003": [("2026-06-09", "amendment")],
    "0004": [("2026-06-09", "amendment"),
             ("2026-08-29", "amendment"),
             ("2026-08-29", "context")],
    "0005": [],
    "0006": [],
    "0007": [],
    "0008": [("2026-08-29", "erratum")],
    "0009": [],
}

#: ADRs that existed at migration time. Ones added later are covered by the
#: generic invariants only — they were never migrated, so there is nothing to
#: check them against.
MIGRATED = sorted(MIGRATION_SEED)


def log_rows(path: Path):
    """(date, type) for each data row in the decision log."""
    tail = path.read_text(encoding="utf-8").split("\n## Decision log\n", 1)[1]
    rows = [ln for ln in tail.splitlines() if ln.lstrip().startswith("|")]
    out = []
    for row in rows[2:]:
        cells = [c.strip() for c in row.strip().strip("|").split("|")]
        if len(cells) >= 2:
            out.append((cells[0], cells[1]))
    return out


# ---- generic invariants: every ADR, now and in future --------------------


@pytest.mark.parametrize("adr", ADRS, ids=lambda p: p.name[:4])
def test_status_is_valid_for_a_decision(adr):
    """Valid, not frozen. Which status an ADR currently holds is mutable."""
    assert fm(adr)["status"] in load_taxonomy().statuses_for("decision")


@pytest.mark.parametrize("adr", ADRS, ids=lambda p: p.name[:4])
def test_superseded_status_pairs_with_a_superseded_by_row(adr):
    """The pairing rule, checked as an invariant rather than a fixed value."""
    rows = log_rows(adr)
    has_row = any(kind == "superseded-by" for _, kind in rows)
    assert (fm(adr)["status"] == "superseded") == has_row, adr.name


# ---- migration fidelity: only the ADRs that were migrated ----------------


@pytest.mark.parametrize("num", MIGRATED)
def test_seeded_rows_remain_an_ordered_prefix(num):
    """Append-only: the migration's rows stay at the front, in order, forever.

    Later entries are expected and must not fail this.
    """
    adr = next(p for p in ADRS if p.name.startswith(num))
    seeded = MIGRATION_SEED[num]
    assert log_rows(adr)[: len(seeded)] == seeded


@pytest.mark.parametrize("num", MIGRATED)
def test_migrated_adrs_use_the_empty_form_only_when_they_have_no_rows(num):
    adr = next(p for p in ADRS if p.name.startswith(num))
    tail = adr.read_text(encoding="utf-8").split("\n## Decision log\n", 1)[1]
    if not log_rows(adr):
        assert "*No entries.*" in tail, f"{adr.name}: no rows, so expected the empty form"


def test_a_future_adr_needs_no_matrix_entry():
    """Guards the KeyError this suite used to raise: an ADR added after the
    migration is covered by the generic invariants and nothing else."""
    unmigrated = [p for p in ADRS if p.name[:4] not in MIGRATION_SEED]
    for adr in unmigrated:
        assert fm(adr)["doc_type"] == "decision"
        assert fm(adr)["status"] in load_taxonomy().statuses_for("decision")


# ----------------------------------------- the three documented cases -------


def _log(name: str) -> str:
    path = next(p for p in ADRS if p.name.startswith(name))
    return path.read_text(encoding="utf-8").split("\n## Decision log\n", 1)[1]


def test_adr0002_surfaces_its_own_dead_decision():
    """Was: 'approved (Q6 superseded by 0007)' in a different file."""
    log = _log("0002")
    assert "Q6" in log and "ADR-0007" in log
    assert "| amendment |" in log, "not superseded as a whole — amendment, not superseded-by"


def test_adr0003_surfaces_its_own_promotion():
    """Its frontmatter said draft while both indexes said approved."""
    log = _log("0003")
    assert "#508" in log and "Approved" in log
    assert fm(next(p for p in ADRS if p.name.startswith("0003")))["status"] == "approved"


def test_adr0008_surfaces_its_own_erratum():
    """THE originating defect: this erratum lived in ADR-0004's log, so a
    reader of ADR-0008 never saw it."""
    log = _log("0008")
    assert "erratum" in log
    assert "RunSSH" in log and "backwards" in log


def test_adr0004_keeps_its_legacy_log_and_gains_the_canonical_one():
    """The legacy section is frozen history, preserved verbatim; the canonical
    log is appended after it and is where new entries go."""
    text = next(p for p in ADRS if p.name.startswith("0004")).read_text(encoding="utf-8")
    assert "## ACL changes log" in text, "frozen legacy section must be preserved"
    assert "## Decision log" in text
    assert text.index("## ACL changes log") < text.index("## Decision log")


def test_the_relocated_erratum_is_not_duplicated_as_a_canonical_row():
    """Relocated, not copied. Structural rather than a substring search, which
    would pass if the row were copied without the literal string 'ADR-0008'.

    Scoped to the migration-era rows: a later erratum about ADR-0004 ITSELF is
    legitimate and must not fail this, so only the seeded prefix is checked.
    """
    path = next(p for p in ADRS if p.name.startswith("0004"))
    seeded = MIGRATION_SEED["0004"]
    prefix = log_rows(path)[: len(seeded)]
    assert prefix == seeded
    assert not any(kind == "erratum" for _, kind in prefix)


def test_adr0004_legacy_log_is_preserved_verbatim():
    """The frozen section must be byte-identical to its pre-migration state."""
    import subprocess as sp
    path = next(p for p in ADRS if p.name.startswith("0004"))
    rel = path.relative_to(REPO).as_posix()
    before = sp.run(["git", "show", f"HEAD~1:{rel}"], cwd=REPO,
                    capture_output=True, text=True)
    if before.returncode != 0:
        pytest.skip("pre-migration revision not reachable from here")

    def legacy(text):
        seg = text.split("## ACL changes log", 1)[1]
        # up to the next H2, which is now the canonical log
        return seg.split("\n## ", 1)[0]

    assert legacy(path.read_text(encoding="utf-8")) == legacy(before.stdout)


# ------------------------------------------------- no smuggled state --------


def test_indexes_carry_no_parenthetical_state():
    """The smuggling this mission removes: standing discoverable only from
    prose in another file."""
    for path in (REPO / "docs" / "INDEX.md", ADR_DIR / "README.md"):
        text = path.read_text(encoding="utf-8")
        for bad in ("Q6 superseded", "erratum in"):
            assert bad not in text, f"{path.name} still smuggles state: {bad}"


def _decision_log_check_available() -> bool:
    src = (REPO / "tooling" / "scripts" / "validate_docs.py").read_text(encoding="utf-8")
    return "def check_decision_log(" in src


def test_whole_corpus_passes_the_validator_with_the_check_promoted(tmp_path):
    """The migration is only done if the switch WP06 throws already passes.

    SKIPPED, loudly, while WP03's check is on another lane. The first version of
    this test promoted a check that did not exist in this checkout and passed —
    proving nothing. A vacuous pass is worse than a skip, because it reads as
    evidence. Once the lanes merge this runs for real.
    """
    if not _decision_log_check_available():
        pytest.skip(
            "validate_docs.py here has no decision-log check (WP03 lands it on lane-c); "
            "promoting a non-existent check would be vacuous"
        )
    shutil.copytree(REPO / "docs", tmp_path / "docs")
    shutil.copytree(REPO / "tooling", tmp_path / "tooling")
    policy = tmp_path / "docs" / "design" / "standards" / "validator-policy.json"
    d = json.loads(policy.read_text())
    d["blockers"] = sorted(set(d["blockers"]) | {"decision_log"})
    policy.write_text(json.dumps(d, indent=2) + "\n")
    r = subprocess.run(
        [sys.executable, "tooling/scripts/validate_docs.py"],
        cwd=tmp_path, capture_output=True, text=True,
    )
    assert r.returncode == 0, f"stdout={r.stdout}\nstderr={r.stderr}"
