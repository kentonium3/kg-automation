"""Regression tests for #989: the tick's host-state paths are isolated.

These assert BEHAVIOUR, not the isolation fixture's own output.  A test that
read back the constants ``tests/deploy/conftest.py`` had just set would pass
by construction — it could only fail if the fixture were deleted, and would
say nothing about *which* of the several live ``rebaseline`` instances were
actually patched, which is where the original fix attempt went wrong.

So the tests below drive ``run_tick`` and assert that the observe-range base
tracks the watermark the test itself seeded — i.e. that the classification
the tick performs is reading the isolated path rather than ambient host
state.  The complementary filesystem-level assertion (no writes under
``/data`` anywhere in this package) lives in the ``_forbid_data_writes``
session fixture in ``conftest.py``.

The defect these guard against: ``rebaseline``'s path constants default to
the real ``/data/services/felix-deployer/state``, ``_tick`` calls
``read_observed_head()`` / ``write_observed_head()`` with no path argument,
and ``write_observed_head`` mkdirs its parent.  Any deploy test that ran
``run_tick`` therefore wrote its own fixture SHA to the real host path, and
the next test module to run read it back.  On office2 — which actually runs
felix-deployer out of that directory — this would clobber live state.
"""

from __future__ import annotations

import pathlib

import pytest

# Reuse the sibling module's loaded copies rather than loading our own: a
# fresh importlib load would create yet another pair of ``_tick`` /
# ``rebaseline`` instances, which is exactly the multiplicity that made
# this defect hard to isolate in the first place.
from tests.deploy.test_tick_rebaseline import (
    _clean_advance_from_git,
    _git_mock,
    rebaseline,
    tick,
)

PRE = "aabbccdd" * 5
POST = "11223344" * 5
SEEDED = "cafe1234" * 5


@pytest.fixture(autouse=True)
def _wp04_seams(monkeypatch, tmp_path):
    """Mirror of ``test_tick_rebaseline``'s autouse harness.

    That fixture is module-scoped to its own file, so this module does not
    inherit it.  Without it the tick takes the real ``advance_checkout`` path
    and the real ``deploylock``, which reaches further host state — the
    ``_forbid_data_writes`` observer catches that, which is how the omission
    surfaced here.
    """
    monkeypatch.setenv("DEPLOY_CHECKOUT_LOCK", str(tmp_path / "checkout.lock"))
    monkeypatch.setattr(tick, "DEFAULT_STATE_DIR", tmp_path / "tick-state")
    monkeypatch.setattr(tick, "advance_checkout", _clean_advance_from_git)
    yield


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


def _run_and_capture_observe_base(monkeypatch, repo, logs, **git_kwargs) -> str:
    """Drive one tick and return the base ``observe()`` was called with."""
    monkeypatch.setattr(tick, "_git", _git_mock(pre_sha=PRE, post_sha=POST, **git_kwargs))

    seen: list[tuple] = []

    def _fake_observe(pre, post, **kwargs):
        seen.append((pre, post))
        return {"outcome": "not_required"}

    monkeypatch.setattr(rebaseline, "observe", _fake_observe)
    monkeypatch.setattr(rebaseline, "reconcile", lambda **kw: {"outcome": "not_required"})

    assert tick.run_tick(repo_root=repo, log_dir=logs) == 0
    assert len(seen) == 1, f"expected exactly one observe() call, got {len(seen)}"
    return seen[0][0]


def test_absent_watermark_selects_pre_pull_head(monkeypatch, repo, logs):
    """No watermark -> WATERMARK_FALLBACK -> the base is ``pre_pull_head``.

    This is the contract ``test_observe_called_with_pulled_range`` relies on.
    It only holds if the watermark path is isolated: before #989 an earlier
    test module had already written its own SHA to the shared real path, so
    this branch was not the one taken.
    """
    assert not rebaseline.DEFAULT_OBSERVED_HEAD_PATH.exists()
    assert _run_and_capture_observe_base(monkeypatch, repo, logs) == PRE


def test_seeded_watermark_is_read_from_the_isolated_path(monkeypatch, repo, logs):
    """A watermark this test wrote is the one the tick classifies.

    Discriminating: if the fixture patched a different ``rebaseline`` instance
    than the one ``run_tick`` reaches, the tick would read the real host path
    (or an unpatched default) and the base would not be ``SEEDED``.
    """
    rebaseline.write_observed_head(SEEDED, rebaseline.DEFAULT_OBSERVED_HEAD_PATH)
    assert rebaseline.DEFAULT_OBSERVED_HEAD_PATH.exists()

    # cat-file rc=0 and merge-base --is-ancestor rc=0 -> WATERMARK_VALID.
    base = _run_and_capture_observe_base(monkeypatch, repo, logs)
    assert base == SEEDED


def test_unknown_watermark_self_heals_to_post_pull_head(monkeypatch, repo, logs):
    """The SELF_HEAL branch is reachable and also reads the isolated path.

    ``cat_file_rc=1`` makes the seeded watermark provably unknown to the repo,
    so ``classify_watermark`` returns ``(WATERMARK_SELF_HEAL, post_pull_head)``.
    Covered because SELF_HEAL and VALID are two of the four classifications and
    produce indistinguishable assertion diffs — a regression that only
    exercised VALID would leave this path unguarded.
    """
    rebaseline.write_observed_head(SEEDED, rebaseline.DEFAULT_OBSERVED_HEAD_PATH)

    base = _run_and_capture_observe_base(monkeypatch, repo, logs, cat_file_rc=1)
    assert base == POST


def test_the_watermark_write_lands_in_tmp_not_on_the_host(monkeypatch, repo, logs):
    """The tick's own watermark advance is captured by the isolation.

    ``_tick`` calls ``write_observed_head(new_watermark)`` with no path, so
    this is the write that escaped to ``/data`` before #989.
    """
    _run_and_capture_observe_base(monkeypatch, repo, logs)

    written = rebaseline.DEFAULT_OBSERVED_HEAD_PATH
    assert written.exists(), "the tick should have advanced the watermark"
    assert pathlib.Path("/data") not in written.resolve().parents
    assert rebaseline.read_observed_head(written) == POST
