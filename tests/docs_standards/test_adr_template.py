"""The ADR authoring template must emit a CONFORMING document (#987 FR-007).

A new ADR should satisfy the decision-log contract at creation rather than
being migrated later. This template was missed entirely in the first
decomposition: it emitted `doc_type: guide`, carried no decision log, and — the
defect a reviewer caught — kept a frontmatter block of its own.

That last one mattered most. Templater writes the whole parsed file, so a
template-file frontmatter lands in the rendered note and SHADOWS the intended
one: the note would have been `doc_type: reference`, the intended block would
have become body text, and the validator would have passed it for the wrong
reason while skipping decision-log validation entirely. The repo's own working
templates (runbook.md, handbook.md, base.md) all start straight at the
Templater block; decision.md was the outlier.

So these tests do not inspect the template's text and hope. They RENDER it —
substituting the Templater expressions the way Templater would — and run the
real validator over the result with the decision-log check promoted to a
blocker. That is the only claim worth making.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
TEMPLATE = REPO / "docs" / "_templates" / "decision.md"
STANDARDS = REPO / "docs" / "design" / "standards"
sys.path.insert(0, str(REPO / "tooling" / "scripts"))

from doc_taxonomy import load_taxonomy  # noqa: E402

STRICT_POLICY = json.dumps({"blockers": ["required_keys", "enum_membership", "decision_log"]})


def render(text: str) -> str:
    """Approximate Templater: run the `<%* ... %>` blocks away.

    Templater emits the whole parsed file, so whatever survives here is what a
    new ADR actually contains.
    """
    text = re.sub(r"<%\*\s*tR \+= id\s*%>", "my-decision", text)
    text = re.sub(r"<%\*\s*tR \+= title\s*%>", "My Decision", text)
    text = re.sub(r"<%\*\s*tR \+= today\s*%>", "2026-09-18", text)
    # The setup block emits nothing.
    text = re.sub(r"<%\*.*?_%>\n?", "", text, flags=re.S)
    return text


@pytest.fixture(scope="module")
def rendered() -> str:
    return render(TEMPLATE.read_text(encoding="utf-8"))


@pytest.fixture
def repo(tmp_path):
    (tmp_path / "tooling" / "scripts").mkdir(parents=True)
    for name in ("validate_docs.py", "doc_taxonomy.py"):
        shutil.copy(REPO / "tooling" / "scripts" / name, tmp_path / "tooling" / "scripts" / name)
    std = tmp_path / "docs" / "design" / "standards"
    std.mkdir(parents=True)
    shutil.copy(STANDARDS / "allowed-values.json", std / "allowed-values.json")
    (std / "validator-policy.json").write_text(STRICT_POLICY, encoding="utf-8")
    return tmp_path


def test_template_exists():
    assert TEMPLATE.exists(), "the ADR authoring template must not be renamed silently"


def test_no_templater_syntax_survives_rendering(rendered):
    assert "<%" not in rendered, rendered[:200]


def test_rendered_adr_passes_the_real_validator(repo, rendered):
    """The claim that matters: a document made from this template conforms,
    checked by the validator itself with decision_log PROMOTED."""
    (repo / "docs" / "adr.md").write_text(rendered, encoding="utf-8")
    r = subprocess.run(
        [sys.executable, "tooling/scripts/validate_docs.py"],
        cwd=repo, capture_output=True, text=True,
    )
    assert r.returncode == 0, f"stdout={r.stdout}\nstderr={r.stderr}"
    assert "WARN" not in r.stdout, r.stdout


def test_rendered_frontmatter_is_the_only_one(rendered):
    """The shadowing defect: two frontmatter blocks means the first wins and
    the intended one becomes body text."""
    blocks = re.findall(r"^---\n(.*?)\n---", rendered, re.S | re.M)
    assert len(blocks) == 1, f"expected exactly one frontmatter block, got {len(blocks)}"
    assert re.search(r"^doc_type:\s*decision\s*$", blocks[0], re.M), blocks[0]


def test_rendered_status_is_valid_for_a_decision(rendered):
    fm = re.findall(r"^---\n(.*?)\n---", rendered, re.S | re.M)[0]
    status = re.search(r"^status:\s*(\S+)\s*$", fm, re.M).group(1)
    assert status in load_taxonomy().statuses_for("decision")


def test_rendered_log_is_last_and_is_the_empty_form(rendered):
    tail = rendered.split("## Decision log", 1)[1]
    assert "*No entries.*" in tail
    assert not re.search(r"^#{1,6}\s", tail, re.M), f"heading after the log: {tail[:80]}"


def test_rendered_body_has_no_status_line(rendered):
    body = rendered.split("---", 2)[-1]
    assert not re.search(r"^\*\*Status\*\*:", body, re.M)


def test_template_teaches_the_type_vocabulary(rendered):
    for kind in ("erratum", "amendment", "superseded-by", "context"):
        assert kind in rendered, kind


def test_template_teaches_the_pipe_escape(rendered):
    assert r"\|" in rendered
