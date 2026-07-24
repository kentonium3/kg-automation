"""SC-002 single-point-flip proof (mission ``vikunja-token-seam-kent-cutover-01KY8XQ0``).

The mission's whole thesis is that after the seam lands, the runtime Vikunja
identity is a **one-lever** change: moving the single resolution point
(:func:`scripts.common.vikunja_config.get_vikunja_token_path` — via its
``VIKUNJA_TOKEN_PATH`` override or its module default) moves **every** runtime
consumer that routes through the shared default, with no per-consumer edit.

This module proves that property at the seam boundary:

- Setting ``VIKUNJA_TOKEN_PATH`` changes what ``get_vikunja_token_path()``
  resolves **and** what a default-constructed ``VikunjaClient()`` loads — one
  lever, both move (and the wider 13-module consumer set inherits this because
  they route through exactly these two, per FR-001).
- **The documented exception (SC-002 rationale):** ``intake/apply_reply.py`` is
  deliberately kent-pinned with a felix-bot **refusal** guard (#750/#715). It
  does *not* participate in the flip: its ``DEFAULT_KENT_TOKEN_FILE`` constant
  stays the kent path and does **not** follow the ``VIKUNJA_TOKEN_PATH``
  override. This test asserts that intentional non-participation so a future
  edit that accidentally wires apply_reply onto the shared lever is caught.
"""
from __future__ import annotations

import os
from pathlib import Path

from scripts.common.vikunja_client import VikunjaClient
from scripts.common.vikunja_config import get_vikunja_token_path
from scripts.intake import apply_reply

# A base_url that satisfies the client's ^https?://<host>/api/v1$ pattern; no
# request is issued (construction only), and conftest's _block_live_http would
# raise on any unmocked urlopen anyway.
_TEST_BASE_URL = "https://vikunja.test/api/v1"
_KENT_TOKEN_PATH = "/data/services/openclaw/secrets/vikunja-api-kent"


def _write_token(dir_path: Path, name: str, value: str) -> Path:
    token_file = dir_path / name
    token_file.write_text(value + "\n", encoding="utf-8")
    return token_file


def test_one_lever_moves_helper_and_client(monkeypatch, tmp_path) -> None:
    """Setting VIKUNJA_TOKEN_PATH moves BOTH the helper and a default client."""
    token_a = _write_token(tmp_path, "token-a", "identity-a")
    monkeypatch.setenv("VIKUNJA_TOKEN_PATH", str(token_a))

    assert get_vikunja_token_path() == token_a
    client_a = VikunjaClient(base_url=_TEST_BASE_URL)
    assert client_a.token == "identity-a"


def test_moving_the_lever_again_moves_everything_again(monkeypatch, tmp_path) -> None:
    """The lever is live: a second override value re-points helper + client with
    no code change — this is the property Phase 1 failed to deliver."""
    token_a = _write_token(tmp_path, "token-a", "identity-a")
    token_b = _write_token(tmp_path, "token-b", "identity-b")

    monkeypatch.setenv("VIKUNJA_TOKEN_PATH", str(token_a))
    assert get_vikunja_token_path() == token_a
    assert VikunjaClient(base_url=_TEST_BASE_URL).token == "identity-a"

    monkeypatch.setenv("VIKUNJA_TOKEN_PATH", str(token_b))
    assert get_vikunja_token_path() == token_b
    assert VikunjaClient(base_url=_TEST_BASE_URL).token == "identity-b"


def test_resolution_is_call_time_not_import_time(monkeypatch, tmp_path) -> None:
    """A client constructed AFTER the env changes sees the new value — proving
    resolution happens at call time, not frozen at import time."""
    token_a = _write_token(tmp_path, "token-a", "identity-a")
    token_b = _write_token(tmp_path, "token-b", "identity-b")

    monkeypatch.setenv("VIKUNJA_TOKEN_PATH", str(token_a))
    first = VikunjaClient(base_url=_TEST_BASE_URL)
    assert first.token == "identity-a"

    # Flip the lever, then construct again — the new client must follow.
    monkeypatch.setenv("VIKUNJA_TOKEN_PATH", str(token_b))
    second = VikunjaClient(base_url=_TEST_BASE_URL)
    assert second.token == "identity-b"
    # The already-constructed client keeps its captured token (stateless per
    # instance) — proving each construction is an independent resolution.
    assert first.token == "identity-a"


# ---------------------------------------------------------------------------
# Documented exception: apply_reply stays kent-pinned and does NOT follow the
# shared lever (SC-002 rationale; #750/#715 felix-bot refusal).
# ---------------------------------------------------------------------------


def test_apply_reply_kent_constant_is_the_kent_path() -> None:
    assert (
        os.path.abspath(apply_reply.DEFAULT_KENT_TOKEN_FILE)
        == os.path.abspath(_KENT_TOKEN_PATH)
    )


def test_apply_reply_does_not_follow_the_shared_override(monkeypatch, tmp_path) -> None:
    # Point the shared lever at an arbitrary path; the seam follows it, but
    # apply_reply's deliberately-pinned kent constant does NOT.
    other = _write_token(tmp_path, "not-kent", "some-token")
    monkeypatch.setenv("VIKUNJA_TOKEN_PATH", str(other))

    assert get_vikunja_token_path() == other  # the seam moved
    # apply_reply stayed pinned to kent — it is not on the shared lever.
    assert os.path.abspath(apply_reply.DEFAULT_KENT_TOKEN_FILE) == os.path.abspath(
        _KENT_TOKEN_PATH
    )
    assert os.path.abspath(apply_reply.DEFAULT_KENT_TOKEN_FILE) != os.path.abspath(
        str(other)
    )
