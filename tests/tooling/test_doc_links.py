"""The repo's markdown links resolve, and the checker that says so is itself trustworthy.

Wired in as a test rather than a CI workflow step deliberately: `.github/workflows/`
is not modified without explicit instruction, and Test CI already runs this suite —
so a broken link reddens CI either way, without touching a workflow file.

The second half of this module matters as much as the first. A link checker that
over-reports is worse than none: the first version of this scan claimed 68 broken
links when the true figure was 18, because it counted teaching examples inside code
fences and mis-parsed the repo's `[text](<path>)` form. Somebody acting on that
number would have "fixed" working documentation. So the false-positive guards are
pinned by tests, not left to the docstring.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
_MODULE_PATH = REPO_ROOT / "tooling" / "scripts" / "check_doc_links.py"


def _load():
    spec = importlib.util.spec_from_file_location("check_doc_links", _MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


checker = _load()


# --------------------------------------------------------------------------- #
# The actual gate
# --------------------------------------------------------------------------- #


def test_no_broken_relative_links_in_repo_docs():
    """Every repo-owned relative markdown link resolves.

    #927 fixed three of these and #944 the remaining fourteen. Eleven of those
    fourteen were the same error — a path one or two levels too shallow — which is
    invisible on GitHub's rendered view until clicked. Both batches were found by
    manual sweeps months apart, which is why this is now mechanical.
    """
    broken = checker.broken_links(REPO_ROOT)
    assert broken == [], "broken relative links:\n" + "\n".join(
        f"  {f} -> {t}" for f, t in broken
    )


# --------------------------------------------------------------------------- #
# The checker must not over-report — these are the false positives that made the
# first scan claim 68 instead of 18.
# --------------------------------------------------------------------------- #


def test_fenced_code_is_not_scanned(tmp_path):
    """Teaching examples inside fences are documentation, not links.

    `docs/runbooks/doc-maintenance.md` is a document about writing docs and
    legitimately contains `[text](./bar.md)` as an example. Counting it is a
    measurement artifact.
    """
    md = tmp_path / "teaching.md"
    md.write_text("Write links like this:\n\n```\n[text](./does-not-exist.md)\n```\n")
    assert checker.broken_links(tmp_path) == []


def test_inline_code_is_not_scanned(tmp_path):
    md = tmp_path / "inline.md"
    md.write_text("Use `[text](./nope.md)` for a relative link.\n")
    assert checker.broken_links(tmp_path) == []


def test_angle_bracket_link_form_is_understood(tmp_path):
    """`[t](<path>)` is used widely in this repo.

    A checker that only handles the bare form captures a lone `<` as the target and
    reports every angle-bracket link in the repo as broken.
    """
    (tmp_path / "target.md").write_text("hi\n")
    good = tmp_path / "good.md"
    good.write_text("See [target](<./target.md>).\n")
    assert checker.broken_links(tmp_path) == []

    bad = tmp_path / "bad.md"
    bad.write_text("See [missing](<./missing.md>).\n")
    found = checker.broken_links(tmp_path)
    assert [t for _, t in found] == ["./missing.md"]


def test_urls_and_anchors_are_ignored(tmp_path):
    md = tmp_path / "links.md"
    md.write_text(
        "[web](https://example.com) [mail](mailto:a@b.c) [anchor](#section)\n"
    )
    assert checker.broken_links(tmp_path) == []


def test_anchor_suffix_does_not_break_resolution(tmp_path):
    (tmp_path / "target.md").write_text("hi\n")
    md = tmp_path / "src.md"
    md.write_text("See [target](<./target.md#some-heading>).\n")
    assert checker.broken_links(tmp_path) == []


# --------------------------------------------------------------------------- #
# ...and it must not under-report either.
# --------------------------------------------------------------------------- #


def test_a_genuinely_broken_link_is_caught(tmp_path):
    md = tmp_path / "src.md"
    md.write_text("See [gone](./gone.md).\n")
    assert checker.broken_links(tmp_path) == [("src.md", "./gone.md")]


def test_the_depth_error_class_is_caught(tmp_path):
    """The specific mistake behind eleven of the fourteen in #944."""
    (tmp_path / "docs" / "runbooks").mkdir(parents=True)
    (tmp_path / "docs" / "runbooks" / "ops.md").write_text("hi\n")
    deep = tmp_path / "docs" / "design" / "architecture"
    deep.mkdir(parents=True)
    # one level too shallow: resolves to docs/design/runbooks/, which does not exist
    (deep / "README.md").write_text("See [ops](<../runbooks/ops.md>).\n")
    found = checker.broken_links(tmp_path)
    assert found == [("docs/design/architecture/README.md", "../runbooks/ops.md")]


# --------------------------------------------------------------------------- #
# Exclusions are deliberate and must stay that way.
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "excluded, why",
    [
        ("docs/archive/old.md", "frozen history — its links describe the world as it was"),
        ("kitty-specs/m/spec.md", "spec-kitty-owned mission artifacts, not repo docs"),
        (".agents/skills/x/SKILL.md", "vendored skill referencing spec-kitty's own docs"),
        (".claude/skills/x/SKILL.md", "same vendored skill, second install location"),
    ],
)
def test_excluded_paths_are_not_scanned(tmp_path, excluded, why):
    target = tmp_path / excluded
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("See [missing](./definitely-missing.md).\n")
    assert checker.broken_links(tmp_path) == [], f"should be excluded: {why}"


def test_ordinary_docs_are_still_scanned(tmp_path):
    """Guard against an exclusion pattern that is too broad."""
    md = tmp_path / "docs" / "runbooks" / "real.md"
    md.parent.mkdir(parents=True)
    md.write_text("See [missing](./missing.md).\n")
    assert checker.broken_links(tmp_path) == [("docs/runbooks/real.md", "./missing.md")]
