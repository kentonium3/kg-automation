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


@pytest.mark.parametrize("adr", ADRS, ids=lambda p: p.name[:4])
def test_every_adr_status_is_valid_for_a_decision(adr):
    assert fm(adr)["status"] in load_taxonomy().statuses_for("decision")


@pytest.mark.parametrize("adr", ADRS, ids=lambda p: p.name[:4])
def test_every_adr_has_a_decision_log_and_it_is_last(adr):
    text = adr.read_text(encoding="utf-8")
    assert text.count("\n## Decision log\n") == 1, adr.name
    tail = text.split("\n## Decision log\n", 1)[1]
    assert not re.search(r"^#{1,6}\s", tail, re.M), f"{adr.name}: heading after the log"


@pytest.mark.parametrize("adr", ADRS, ids=lambda p: p.name[:4])
def test_no_adr_carries_partially_superseded(adr):
    """C-004. It must never exist, in frontmatter or as prose in the index."""
    assert "partially_superseded" not in adr.read_text(encoding="utf-8")


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
    """Relocated, not copied: ADR-0004's canonical log must not carry the entry
    that belongs to ADR-0008."""
    log = _log("0004")
    assert "ADR-0008" not in log.split("| Date |")[1]


# ------------------------------------------------- no smuggled state --------


def test_indexes_carry_no_parenthetical_state():
    """The smuggling this mission removes: standing discoverable only from
    prose in another file."""
    for path in (REPO / "docs" / "INDEX.md", ADR_DIR / "README.md"):
        text = path.read_text(encoding="utf-8")
        for bad in ("Q6 superseded", "erratum in"):
            assert bad not in text, f"{path.name} still smuggles state: {bad}"


def test_whole_corpus_passes_the_validator_with_the_check_promoted(tmp_path):
    """The migration is only done if the enforcement WP06 will switch on
    already passes today."""
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
