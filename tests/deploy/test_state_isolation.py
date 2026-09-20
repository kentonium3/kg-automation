"""Regression tests for #989: the tick's host-state paths are isolated.

These assert BEHAVIOUR, not the isolation fixture's own output.  A test that
read back the constants ``tests/deploy/conftest.py`` had just set would pass
by construction — it could only fail if the fixture were deleted, and would
say nothing about *which* of the several live ``rebaseline`` instances were
actually patched, which is where the original fix attempt went wrong.

So the tests below drive ``run_tick`` and assert that the observe-range base
tracks the watermark the test itself seeded — i.e. that the classification
the tick performs is reading the isolated path rather than ambient host
state.  The complementary filesystem-level assertion lives in the
``_guard_host_state`` session fixture in ``conftest.py``, which blocks and
records mutations under ``/data`` made through the ``pathlib`` and ``os``
entry points.  It is not total: a subprocess, a C extension that bypasses
those entry points, or a session-scoped finalizer running after the last
item's protocol all fall outside it.

The defect these guard against: ``rebaseline``'s path constants default to
the real ``/data/services/felix-deployer/state``, ``_tick`` calls
``read_observed_head()`` / ``write_observed_head()`` with no path argument,
and ``write_observed_head`` mkdirs its parent.  Any deploy test that ran
``run_tick`` therefore wrote its own fixture SHA to the real host path, and
the next test module to run read it back.  On office2 — which actually runs
felix-deployer out of that directory — this would clobber live state.
"""

from __future__ import annotations

import os
import pathlib

import pytest

# Reuse the sibling module's loaded copies rather than loading our own: a
# fresh importlib load would create yet another pair of ``_tick`` /
# ``rebaseline`` instances, which is exactly the multiplicity that made this
# defect hard to isolate in the first place.
#
# This import is safe only because ``tests/__init__.py`` and
# ``tests/deploy/__init__.py`` both exist: pytest's prepend import mode then
# names the sibling ``tests.deploy.test_tick_rebaseline``, so there is exactly
# one copy and its module-level ``spec_from_file_location`` loads run once.
# Without those two files pytest would import it as bare
# ``test_tick_rebaseline`` and re-run those loads under a second name.
#
# ``_wp04_seams`` is imported rather than hand-copied.  It is an autouse
# fixture, and autouse travels with the definition, so importing the name
# activates it here too — and it cannot drift out of sync with the original
# the way a copy silently would.
from tests.deploy.test_tick_rebaseline import (  # noqa: F401 - autouse fixture
    _git_mock,
    _read_log,
    _wp04_seams,
    rebaseline,
    tick,
)

PRE = "aabbccdd" * 5
POST = "11223344" * 5
SEEDED = "cafe1234" * 5


@pytest.fixture()
def repo(tmp_path: pathlib.Path) -> pathlib.Path:
    for sub in ("queued", "applied", "failed"):
        (tmp_path / "deploys" / sub).mkdir(parents=True, exist_ok=True)
    return tmp_path


@pytest.fixture()
def logs(tmp_path: pathlib.Path) -> pathlib.Path:
    d = tmp_path / "isolation-logs"
    d.mkdir()
    return d


def _run_and_capture(monkeypatch, repo, logs, **git_kwargs) -> tuple[str, dict]:
    """Drive one tick; return the observe base and the ``rebaseline_observe`` entry.

    The log entry carries ``range_source``, which is what distinguishes the
    four watermark classifications.  The base alone does not: SELF_HEAL and
    TRANSIENT both select ``post_pull_head``, so a test asserting only the
    base would pass on a regression from one to the other.
    """
    monkeypatch.setattr(tick, "_git", _git_mock(pre_sha=PRE, post_sha=POST, **git_kwargs))

    seen: list[tuple] = []

    def _fake_observe(pre, post, **kwargs):
        seen.append((pre, post))
        return {"outcome": "not_required"}

    monkeypatch.setattr(rebaseline, "observe", _fake_observe)
    monkeypatch.setattr(rebaseline, "reconcile", lambda **kw: {"outcome": "not_required"})

    assert tick.run_tick(repo_root=repo, log_dir=logs) == 0
    assert len(seen) == 1, f"expected exactly one observe() call, got {len(seen)}"

    entries = [e for e in _read_log(logs) if e.get("event") == "rebaseline_observe"]
    assert len(entries) == 1, f"expected one rebaseline_observe entry, got {entries}"
    return seen[0][0], entries[0]


def test_absent_watermark_selects_pre_pull_head(monkeypatch, repo, logs):
    """No watermark -> WATERMARK_FALLBACK -> the base is ``pre_pull_head``.

    This is the contract ``test_observe_called_with_pulled_range`` relies on.
    It only holds if the watermark path is isolated: before #989 an earlier
    test module had already written its own SHA to the shared real path, so
    this branch was not the one taken.
    """
    assert not rebaseline.DEFAULT_OBSERVED_HEAD_PATH.exists()
    base, entry = _run_and_capture(monkeypatch, repo, logs)
    assert base == PRE
    assert entry["range_source"] == "fallback"


def test_seeded_watermark_is_read_from_the_isolated_path(monkeypatch, repo, logs):
    """A watermark this test wrote is the one the tick classifies.

    Discriminating: if the fixture patched a different ``rebaseline`` instance
    than the one ``run_tick`` reaches, the tick would read the real host path
    (or an unpatched default) and the base would not be ``SEEDED``.
    """
    rebaseline.write_observed_head(SEEDED, rebaseline.DEFAULT_OBSERVED_HEAD_PATH)
    assert rebaseline.DEFAULT_OBSERVED_HEAD_PATH.exists()

    # cat-file rc=0 and merge-base --is-ancestor rc=0 -> WATERMARK_VALID.
    base, entry = _run_and_capture(monkeypatch, repo, logs)
    assert base == SEEDED
    assert entry["range_source"] == "watermark"


def test_unknown_watermark_self_heals_to_post_pull_head(monkeypatch, repo, logs):
    """The SELF_HEAL branch is reachable and also reads the isolated path.

    ``cat_file_rc=1`` makes the seeded watermark provably unknown to the repo,
    so ``classify_watermark`` returns ``(WATERMARK_SELF_HEAL, post_pull_head)``.
    Covered because SELF_HEAL and VALID are two of the four classifications and
    produce indistinguishable assertion diffs — a regression that only
    exercised VALID would leave this path unguarded.
    """
    rebaseline.write_observed_head(SEEDED, rebaseline.DEFAULT_OBSERVED_HEAD_PATH)

    base, entry = _run_and_capture(monkeypatch, repo, logs, cat_file_rc=1)
    assert base == POST
    # The base alone cannot tell SELF_HEAL from TRANSIENT — both select
    # post_pull_head — so assert the classification the tick actually took.
    assert entry["range_source"] == "self_heal"


def test_the_watermark_write_lands_in_tmp_not_on_the_host(monkeypatch, repo, logs):
    """The tick's own watermark advance is captured by the isolation.

    ``_tick`` calls ``write_observed_head(new_watermark)`` with no path, so
    this is the write that escaped to ``/data`` before #989.
    """
    _run_and_capture(monkeypatch, repo, logs)

    written = rebaseline.DEFAULT_OBSERVED_HEAD_PATH
    assert written.exists(), "the tick should have advanced the watermark"
    assert pathlib.Path("/data") not in written.resolve().parents
    assert rebaseline.read_observed_head(written) == POST


# ---------------------------------------------------------------------------
# The guard itself: prove the wrappers fire, rather than trusting the list
# ---------------------------------------------------------------------------
#
# Both probes are chosen so that a FAILURE of the guard mutates nothing: they
# target a path under /data that does not exist, so an unguarded call raises
# FileNotFoundError instead of creating anything. A guard regression shows up
# as the wrong exception type, never as a real write to host state.


@pytest.fixture()
def blocked_probe():
    """Let a test trip the guard deliberately without failing the session.

    The guard records every blocked attempt and asserts the record is empty at
    session teardown.  These tests trip it on purpose, so they roll the record
    back to its prior length.
    """
    from tests.deploy import conftest as guard

    start = len(guard._ESCAPES)
    yield guard
    del guard._ESCAPES[start:]


def test_guard_blocks_chmod_on_host_state(blocked_probe):
    """chmod mutates real state as surely as a write does.

    It is used in this package (``test_migrate_inbox_state.py``), so an
    unredirected call must not slip through the way it did before the
    mutator list was widened.
    """
    with pytest.raises(blocked_probe.HostStateWriteBlocked):
        pathlib.Path("/data/does-not-exist-989-probe").chmod(0o644)


def test_guard_blocks_a_dir_fd_relative_mutation(blocked_probe):
    """A relative path anchored at a /data descriptor must not walk past.

    ``os.*`` resolves a relative path against ``dir_fd``, not the process CWD,
    so a CWD-only check would wave this through.  The guard resolves the
    anchor via ``/proc/self/fd``.
    """
    if not pathlib.Path("/data").is_dir():
        pytest.skip("/data does not exist on this host")

    fd = os.open("/data", os.O_RDONLY)
    try:
        with pytest.raises(blocked_probe.HostStateWriteBlocked):
            os.unlink("does-not-exist-989-probe", dir_fd=fd)
    finally:
        os.close(fd)


def test_guard_ignores_paths_outside_host_state(tmp_path):
    """The guard must not fire on ordinary tmp work — it runs on every test."""
    target = tmp_path / "ordinary.txt"
    target.write_text("fine", encoding="utf-8")
    target.chmod(0o600)
    assert target.read_text(encoding="utf-8") == "fine"


def test_guard_blocks_a_symlink_created_inside_host_state(blocked_probe):
    """The link being CREATED is the mutation, anchored by ``dir_fd``.

    ``os.symlink``'s first argument is the link target — a string that is
    merely stored and need not exist — so only the second is a path being
    written.  Routing it through the two-ended move wrapper got this wrong in
    both directions: it missed ``dir_fd`` (which ``os.symlink`` spells
    without the ``src_``/``dst_`` prefixes) and falsely blocked a link made
    outside ``/data`` that merely pointed into it.
    """
    if not pathlib.Path("/data").is_dir():
        pytest.skip("/data does not exist on this host")

    fd = os.open("/data", os.O_RDONLY)
    try:
        with pytest.raises(blocked_probe.HostStateWriteBlocked):
            os.symlink("/tmp/whatever", "does-not-exist-989-link", dir_fd=fd)
    finally:
        os.close(fd)
        # Self-cleaning: if the guard ever regresses, this probe would leave a
        # real symlink in /data that poisons the next run — which is exactly
        # what happened while developing it.  The removal is itself a /data
        # mutation, so it runs with the guard suspended.
        with blocked_probe.unguarded():
            pathlib.Path("/data/does-not-exist-989-link").unlink(missing_ok=True)


def test_guard_allows_a_symlink_outside_host_state_pointing_into_it(tmp_path):
    """Pointing AT /data is not mutating it — this must not be blocked."""
    link = tmp_path / "points-into-data"
    os.symlink("/data/whatever", link)
    assert link.is_symlink()
    assert os.readlink(link) == "/data/whatever"


def test_guard_blocks_an_fd_valued_path(blocked_probe):
    """``os.chmod`` and friends accept a descriptor in place of a path.

    A read-only descriptor on a real ``/data`` file would otherwise be a way
    to mutate live state without the guard seeing a path at all.
    """
    if not pathlib.Path("/data").is_dir():
        pytest.skip("/data does not exist on this host")

    fd = os.open("/data", os.O_RDONLY)
    try:
        with pytest.raises(blocked_probe.HostStateWriteBlocked):
            os.chmod(fd, 0o755)
    finally:
        os.close(fd)
