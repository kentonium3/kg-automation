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


def scan(directory: Path) -> list[tuple[str, str]]:
    """Check a plain (non-git) directory.

    The fixtures below are tmp dirs, not git work trees, so they enumerate by
    walking. Stating that here keeps it out of `broken_links`, which would
    otherwise have to infer the mode from whether `directory` sits inside a work
    tree -- and would then flip with $TMPDIR, silently emptying these fixtures
    while most of them still asserted `== []`.
    """
    return checker.broken_links(directory, checker.walk_markdown_files(directory))


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
    broken = checker.broken_links(REPO_ROOT, checker.repo_markdown_files(REPO_ROOT))
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
    assert scan(tmp_path) == []


def test_inline_code_is_not_scanned(tmp_path):
    md = tmp_path / "inline.md"
    md.write_text("Use `[text](./nope.md)` for a relative link.\n")
    assert scan(tmp_path) == []


def test_angle_bracket_link_form_is_understood(tmp_path):
    """`[t](<path>)` is used widely in this repo.

    A checker that only handles the bare form captures a lone `<` as the target and
    reports every angle-bracket link in the repo as broken.
    """
    (tmp_path / "target.md").write_text("hi\n")
    good = tmp_path / "good.md"
    good.write_text("See [target](<./target.md>).\n")
    assert scan(tmp_path) == []

    bad = tmp_path / "bad.md"
    bad.write_text("See [missing](<./missing.md>).\n")
    found = scan(tmp_path)
    assert [t for _, t in found] == ["./missing.md"]


def test_urls_and_anchors_are_ignored(tmp_path):
    md = tmp_path / "links.md"
    md.write_text(
        "[web](https://example.com) [mail](mailto:a@b.c) [anchor](#section)\n"
    )
    assert scan(tmp_path) == []


def test_anchor_suffix_does_not_break_resolution(tmp_path):
    (tmp_path / "target.md").write_text("hi\n")
    md = tmp_path / "src.md"
    md.write_text("See [target](<./target.md#some-heading>).\n")
    assert scan(tmp_path) == []


# --------------------------------------------------------------------------- #
# ...and it must not under-report either.
# --------------------------------------------------------------------------- #


def test_a_genuinely_broken_link_is_caught(tmp_path):
    md = tmp_path / "src.md"
    md.write_text("See [gone](./gone.md).\n")
    assert scan(tmp_path) == [("src.md", "./gone.md")]


def test_the_depth_error_class_is_caught(tmp_path):
    """The specific mistake behind eleven of the fourteen in #944."""
    (tmp_path / "docs" / "runbooks").mkdir(parents=True)
    (tmp_path / "docs" / "runbooks" / "ops.md").write_text("hi\n")
    deep = tmp_path / "docs" / "design" / "architecture"
    deep.mkdir(parents=True)
    # one level too shallow: resolves to docs/design/runbooks/, which does not exist
    (deep / "README.md").write_text("See [ops](<../runbooks/ops.md>).\n")
    found = scan(tmp_path)
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
    assert scan(tmp_path) == [], f"should be excluded: {why}"


def test_ordinary_docs_are_still_scanned(tmp_path):
    """Guard against an exclusion pattern that is too broad."""
    md = tmp_path / "docs" / "runbooks" / "real.md"
    md.parent.mkdir(parents=True)
    md.write_text("See [missing](./missing.md).\n")
    assert scan(tmp_path) == [("docs/runbooks/real.md", "./missing.md")]


# --------------------------------------------------------------------------- #
# Enumeration: what the repo owns is git's answer, not a hand-maintained list.
# --------------------------------------------------------------------------- #


def _git_repo(root: Path) -> None:
    """A real work tree; enumeration is not mocked because the drift being fixed
    lived in the difference between git's answer and our copy of it."""
    import subprocess

    def git(*args):
        subprocess.run(["git", *args], cwd=root, check=True,
                       capture_output=True)

    git("init", "-q")
    git("config", "user.email", "t@example.com")
    git("config", "user.name", "t")


def test_gitignored_scratch_is_not_scanned(tmp_path):
    """#959: the checker reported 52 broken links that CI could not see.

    The hand-maintained `_SKIP_DIRS` named neither of the two directories that
    actually held them, so the gate's result depended on which scratch trees a
    given machine happened to have. Both real shapes are covered here: a
    gitignored tool directory (`.codex-tmp-home/`, 39 findings) and a gitignored
    dotted state directory (`.kittify/`, 13) -- a single-shape test would have
    passed while leaving the second class live.
    """
    _git_repo(tmp_path)
    (tmp_path / ".gitignore").write_text(".codex-tmp-home/\n.kittify/\n")

    for scratch in (".codex-tmp-home", ".kittify/missions"):
        d = tmp_path / scratch
        d.mkdir(parents=True)
        (d / "template.md").write_text("See [x](../nowhere/{link}).\n")

    tracked = tmp_path / "docs"
    tracked.mkdir()
    (tracked / "real.md").write_text("See [gone](./missing.md).\n")

    import subprocess
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True, capture_output=True)

    files = checker.repo_markdown_files(tmp_path)
    assert [f.as_posix() for f in files] == ["docs/real.md"], (
        "enumeration must return only what git owns"
    )
    # ...and the tracked doc's genuinely broken link is still reported, so this
    # is not passing merely by scanning nothing.
    assert checker.broken_links(tmp_path, files) == [("docs/real.md", "./missing.md")]


def test_enumeration_failure_raises_rather_than_reporting_clean(tmp_path):
    """A gate that cannot enumerate must not be indistinguishable from a clean one.

    Returning [] here would make `broken_links` report success on a repo it never
    read, and falling back to walking would silently restore the phantom findings
    this change removes. Both are the could-not-check/verified-clean conflation
    (Engineering Principle 14), so the failure is loud.
    """
    # Holds whether or not $TMPDIR sits inside a git work tree: outside one, git
    # exits non-zero; inside one, it exits 0 with an empty index match, and the
    # empty-result guard raises for that case too. An earlier version of this test
    # only covered the first branch and would have flipped with $TMPDIR -- the very
    # dependency scan()'s docstring warns about.
    with pytest.raises(RuntimeError):
        checker.repo_markdown_files(tmp_path)
