"""Anti-drift tests for openclaw-auth-verifier runbook anchors.

These tests assert that the operator-facing runbook sections introduced by
kentonium3/kg-automation#597 (openclaw-auth-verifier) are present in the
runbooks. They are structural-only — they guard section anchors and the
``anthropic-verify`` keyword, not specific wording. If a future PR removes
those sections, this test catches it at CI time so the discoverability of
the verifier is not silently dropped.

Behavioral coverage of the verifier itself lives in WP01-WP03 tests.
"""

import pathlib

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]

ANCHORS = [
    (REPO_ROOT / "docs/runbooks/openclaw-ops.md", "### Per-agent auth-row shadow"),
    (REPO_ROOT / "docs/runbooks/openclaw-ops.md", "### Plaintext / SQLite drift"),
    (
        REPO_ROOT / "docs/runbooks/openclaw-ops.md",
        "### Post-`doctor --fix` and post-rotation gate",
    ),
    (
        REPO_ROOT / "docs/runbooks/credential-rotation-ops.md",
        "### Post-rotation verification",
    ),
]


@pytest.mark.parametrize("path,anchor", ANCHORS)
def test_runbook_anchor_present(path: pathlib.Path, anchor: str) -> None:
    assert path.exists(), f"runbook missing: {path}"
    content = path.read_text()
    assert anchor in content, (
        f"Runbook anchor missing in {path.name}: {anchor!r}. "
        f"This section documents the openclaw-auth-verifier remediation flow "
        f"(see kentonium3/kg-automation#597). Do not delete without updating the test."
    )


def test_verifier_referenced_in_both_runbooks() -> None:
    """Both runbooks must reference anthropic-verify by name."""
    for runbook in [
        REPO_ROOT / "docs/runbooks/openclaw-ops.md",
        REPO_ROOT / "docs/runbooks/credential-rotation-ops.md",
    ]:
        assert "anthropic-verify" in runbook.read_text(), (
            f"{runbook.name} does not reference anthropic-verify; "
            f"see kentonium3/kg-automation#597 for context."
        )
