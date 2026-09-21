"""The gate surfaces must actually invoke the freshness check (#987 FR-006).

Review finding: nothing asserted the wiring, so deleting both `--check`
invocations would have left the whole suite green. A gate nobody tests is a
gate that silently stops existing — which is the failure mode this mission was
written to remove, one layer up.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
HOOK = REPO / ".githooks" / "pre-commit"
CI = REPO / ".github" / "workflows" / "docs-ci.yml"
MAKEFILE = REPO / "Makefile"
CHECK = "generate_doc_standards.py --check"


def test_pre_commit_hook_runs_the_freshness_check():
    assert CHECK in HOOK.read_text(encoding="utf-8")


def test_pre_commit_hook_fails_the_commit_when_the_check_fails():
    """Present but not wired into `fail` would be worse than absent."""
    text = HOOK.read_text(encoding="utf-8")
    line = next(ln for ln in text.splitlines() if CHECK in ln and not ln.strip().startswith("#"))
    assert "fail=1" in line, line


def test_ci_runs_the_freshness_check():
    wf = yaml.safe_load(CI.read_text(encoding="utf-8"))
    runs = [s.get("run", "") for j in wf["jobs"].values() for s in j.get("steps", [])]
    assert any(CHECK in r for r in runs), runs


def test_ci_triggers_cover_push_to_main():
    """spec-kitty merges land as merge commits and never fire a pull_request
    event, so a pull_request-only gate would silently never run on a mission
    merge. Asserted rather than assumed."""
    wf = yaml.safe_load(CI.read_text(encoding="utf-8"))
    on = wf.get("on") or wf.get(True)  # YAML 1.1 parses bare `on:` as True
    assert "main" in on["push"]["branches"]
    assert "main" in on["pull_request"]["branches"]


def test_make_docs_check_mirrors_the_gate():
    """The target advertises itself as the local mirror of Docs CI; if it omits
    a validator it teaches a false all-clear."""
    text = MAKEFILE.read_text(encoding="utf-8")
    target = text.split("docs-check:", 1)[1].split("\n\n", 1)[0]
    for script in ("validate_docs.py", "validate_architecture_data.py", CHECK):
        assert script in target, f"docs-check omits {script}"


def test_decision_log_is_promoted_in_the_shipped_policy():
    import json
    policy = json.loads(
        (REPO / "docs" / "design" / "standards" / "validator-policy.json").read_text()
    )
    assert "decision_log" in policy["blockers"]
