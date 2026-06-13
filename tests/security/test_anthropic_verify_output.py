"""C-005 / FR-006 / NFR-003 / SC-007 invariant tests for anthropic-verify.

Three classes of assertion:
  * **Sentinel grep** — no test sentinel ever appears in stdout / stderr,
    across all five fixture scenarios.
  * **Finding sanitization** — constructing a ``Finding`` with a key-shaped
    evidence value (or suggested_action) raises ``ValueError``.
  * **Filesystem snapshot** — ``--check`` mode is read-only; the office2
    mock layout's stat tree is identical before and after ``run_check``.

The scrub helper is also unit-tested here.
"""

from __future__ import annotations

import io
import json
import os
import urllib.error
from pathlib import Path
from unittest.mock import patch

import pytest

from anthropic_verify import core
from anthropic_verify.findings import Finding
from tests.security.fixtures import build_fixtures as bf
from tests.security.test_anthropic_verify_core import (
    _ok_urlopen,
    _http_401_urlopen,
    _network_urlopen,
)


SENTINELS = (
    bf.SENTINEL_CANONICAL,
    bf.SENTINEL_SHADOW,
    bf.SENTINEL_PLAINTEXT_DRIFT,
)


# --------------------------------------------------------------------------- #
# Sentinel grep — SC-007 / FR-006 / C-005
# --------------------------------------------------------------------------- #


def _grep_for_sentinels(text: str) -> list[str]:
    """Return list of sentinels found in ``text`` (empty == no leak)."""
    found: list[str] = []
    for s in SENTINELS:
        if s in text:
            found.append(s)
    return found


def test_no_sentinel_in_output_healthy(tmp_office2_root, capsys):
    agents_dir, plaintext_path = tmp_office2_root
    bf.build_healthy(agents_dir, plaintext_path)
    with patch("anthropic_verify.core.urllib.request.urlopen", _ok_urlopen):
        core.run_check()
    captured = capsys.readouterr()
    assert _grep_for_sentinels(captured.out) == []
    assert _grep_for_sentinels(captured.err) == []


def test_no_sentinel_in_output_shadow(tmp_office2_root, capsys):
    agents_dir, plaintext_path = tmp_office2_root
    bf.build_shadow(agents_dir, plaintext_path)
    with patch("anthropic_verify.core.urllib.request.urlopen", _ok_urlopen):
        core.run_check()
    captured = capsys.readouterr()
    assert _grep_for_sentinels(captured.out) == []
    assert _grep_for_sentinels(captured.err) == []


def test_no_sentinel_in_output_drift(tmp_office2_root, capsys):
    agents_dir, plaintext_path = tmp_office2_root
    bf.build_drift(agents_dir, plaintext_path)
    with patch("anthropic_verify.core.urllib.request.urlopen", _ok_urlopen):
        core.run_check()
    captured = capsys.readouterr()
    assert _grep_for_sentinels(captured.out) == []
    assert _grep_for_sentinels(captured.err) == []


def test_no_sentinel_in_output_main_empty(tmp_office2_root, capsys):
    agents_dir, plaintext_path = tmp_office2_root
    bf.build_main_empty(agents_dir, plaintext_path)
    with patch("anthropic_verify.core.urllib.request.urlopen", _ok_urlopen):
        core.run_check()
    captured = capsys.readouterr()
    assert _grep_for_sentinels(captured.out) == []
    assert _grep_for_sentinels(captured.err) == []


def test_no_sentinel_in_output_plaintext_missing(tmp_office2_root, capsys):
    agents_dir, plaintext_path = tmp_office2_root
    bf.build_plaintext_missing(agents_dir, plaintext_path)
    with patch("anthropic_verify.core.urllib.request.urlopen", _ok_urlopen):
        core.run_check()
    captured = capsys.readouterr()
    assert _grep_for_sentinels(captured.out) == []
    assert _grep_for_sentinels(captured.err) == []


# --------------------------------------------------------------------------- #
# Finding sanitization — C-005 backbone
# --------------------------------------------------------------------------- #


def test_finding_rejects_key_shape_in_evidence():
    with pytest.raises(ValueError, match="key-shaped"):
        Finding(
            type="shadow",
            target="x",
            evidence={"leaked_key": bf.SENTINEL_CANONICAL},
            suggested_action="ok",
        )


def test_finding_rejects_key_shape_in_suggested_action():
    with pytest.raises(ValueError, match="key-shaped"):
        Finding(
            type="drift",
            target="x",
            evidence={"x": 1},
            suggested_action=f"use {bf.SENTINEL_CANONICAL}",
        )


def test_finding_rejects_key_shape_in_target():
    with pytest.raises(ValueError, match="key-shaped"):
        Finding(
            type="shadow",
            target=bf.SENTINEL_CANONICAL,
            evidence={"x": 1},
            suggested_action="ok",
        )


def test_finding_rejects_empty_target():
    with pytest.raises(ValueError, match="target"):
        Finding(
            type="shadow",
            target="",
            evidence={"x": 1},
            suggested_action="ok",
        )


def test_finding_accepts_short_sk_ant_substring():
    """A 'sk-ant-' literal under the 90-char minimum is NOT key-shaped."""
    f = Finding(
        type="drift",
        target="x",
        evidence={"hint": "sk-ant-prefix-only-short"},
        suggested_action="ok",
    )
    assert f.evidence["hint"] == "sk-ant-prefix-only-short"


def test_finding_accepts_long_string_with_whitespace_break():
    """Whitespace breaks the key shape — should not raise."""
    text = "sk-ant- " + "x" * 200  # space immediately breaks shape
    f = Finding(
        type="drift",
        target="x",
        evidence={"hint": text},
        suggested_action="ok",
    )
    assert "sk-ant-" in f.evidence["hint"]


# --------------------------------------------------------------------------- #
# _scrub helper
# --------------------------------------------------------------------------- #


def test_scrub_redacts_full_key_shape():
    text = f"error: {bf.SENTINEL_CANONICAL} suffix"
    scrubbed = core._scrub(text)
    assert bf.SENTINEL_CANONICAL not in scrubbed
    assert "[REDACTED]" in scrubbed


def test_scrub_passes_through_clean_text():
    assert core._scrub("hello world") == "hello world"


def test_scrub_multiple_occurrences():
    text = f"{bf.SENTINEL_CANONICAL} and {bf.SENTINEL_SHADOW}"
    scrubbed = core._scrub(text)
    assert bf.SENTINEL_CANONICAL not in scrubbed
    assert bf.SENTINEL_SHADOW not in scrubbed


def test_ping_anthropic_error_body_containing_key_is_scrubbed():
    """If Anthropic ever echoed the key back, _scrub would catch it."""

    def _bad_urlopen(*_args, **_kwargs):
        raise urllib.error.HTTPError(
            url="https://api.anthropic.com/v1/messages",
            code=401,
            msg="Unauthorized",
            hdrs=None,  # type: ignore[arg-type]
            fp=io.BytesIO(
                f"echoed key {bf.SENTINEL_CANONICAL}".encode()
            ),
        )

    with patch("anthropic_verify.core.urllib.request.urlopen", _bad_urlopen):
        r = core.ping_anthropic("dummy")
    assert bf.SENTINEL_CANONICAL not in (r.error_summary or "")


# --------------------------------------------------------------------------- #
# Filesystem read-only invariant — NFR-003
# --------------------------------------------------------------------------- #


def _snapshot_tree(root: Path) -> dict[str, tuple[int, int, float]]:
    """Map relative path -> (size, mode, mtime_ns). Excludes mtime drift on
    directories themselves (they tick on enumeration) by only snapshotting
    files. Symlinks and special files are out of scope."""
    snap: dict[str, tuple[int, int, float]] = {}
    for dirpath, _dirnames, filenames in os.walk(root):
        for fn in filenames:
            p = Path(dirpath) / fn
            try:
                st = p.stat()
            except OSError:
                continue
            key = str(p.relative_to(root))
            snap[key] = (st.st_size, st.st_mode, st.st_mtime_ns)
    return snap


def test_check_mode_does_not_mutate_filesystem(tmp_office2_root):
    """Snapshot tmp_path tree before and after run_check; assert equality."""
    agents_dir, plaintext_path = tmp_office2_root
    bf.build_healthy(agents_dir, plaintext_path)
    root = agents_dir.parent  # tmp_path
    before = _snapshot_tree(root)
    with patch("anthropic_verify.core.urllib.request.urlopen", _ok_urlopen):
        core.run_check()
    after = _snapshot_tree(root)
    assert before == after, (
        "run_check mutated the filesystem (NFR-003 violated). "
        f"diff: {set(before.items()) ^ set(after.items())}"
    )


def test_check_mode_does_not_mutate_filesystem_on_shadow(tmp_office2_root):
    """Even when a finding is emitted, --check stays read-only."""
    agents_dir, plaintext_path = tmp_office2_root
    bf.build_shadow(agents_dir, plaintext_path)
    root = agents_dir.parent
    before = _snapshot_tree(root)
    with patch("anthropic_verify.core.urllib.request.urlopen", _ok_urlopen):
        core.run_check()
    after = _snapshot_tree(root)
    assert before == after


# --------------------------------------------------------------------------- #
# Bash entry — --repair dispatch
# --------------------------------------------------------------------------- #


def test_main_dispatches_repair_to_repair_module(tmp_office2_root, capsys):
    """With repair.py landed (WP02), ``main(['--repair'])`` invokes run_repair().

    Originally a WP01 test asserted that --repair surfaced a "WP02 lands
    repair.py" error message — that contract was valid only until WP02
    shipped. Now repair.py is present; the test asserts the dispatch path
    works against the no-op (healthy) fixture so we exercise the lazy
    import + dispatch without relying on real office2 paths.
    """
    import anthropic_verify

    agents_dir, plaintext_path = tmp_office2_root
    bf.build_healthy(agents_dir, plaintext_path)

    rc = anthropic_verify.main(["--repair"])
    captured = capsys.readouterr()
    assert rc == 0
    assert "nothing to repair" in captured.out


def test_main_rejects_unknown_args(capsys):
    import anthropic_verify

    rc = anthropic_verify.main(["--bogus"])
    captured = capsys.readouterr()
    assert rc == 1
    assert "usage" in captured.err.lower()
