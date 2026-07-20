"""Unit tests for the OpenClaw binary-path seam (#811).

Covers the resolution contract: env override wins when non-blank, the absolute
default otherwise, a blank/whitespace override falls through, and the
``openclaw_argv`` convenience shape. The seam is pure (no I/O, no network), so
these are plain in-process assertions with ``monkeypatch`` on the environment.
"""
from __future__ import annotations

from scripts.common import openclaw_bin as ob


def test_default_when_env_unset(monkeypatch):
    monkeypatch.delenv(ob.OPENCLAW_BIN_ENV, raising=False)
    assert ob.openclaw_bin() == ob.DEFAULT_OPENCLAW_BIN
    assert ob.DEFAULT_OPENCLAW_BIN == "/home/claude/.local/bin/openclaw"


def test_env_override_wins(monkeypatch):
    monkeypatch.setenv(ob.OPENCLAW_BIN_ENV, "/opt/openclaw/bin/openclaw")
    assert ob.openclaw_bin() == "/opt/openclaw/bin/openclaw"


def test_blank_override_falls_through_to_default(monkeypatch):
    for blank in ("", "   ", "\t"):
        monkeypatch.setenv(ob.OPENCLAW_BIN_ENV, blank)
        assert ob.openclaw_bin() == ob.DEFAULT_OPENCLAW_BIN


def test_openclaw_argv_prepends_resolved_bin(monkeypatch):
    monkeypatch.delenv(ob.OPENCLAW_BIN_ENV, raising=False)
    assert ob.openclaw_argv("cron", "list", "--json") == [
        ob.DEFAULT_OPENCLAW_BIN,
        "cron",
        "list",
        "--json",
    ]


def test_openclaw_argv_no_args(monkeypatch):
    monkeypatch.delenv(ob.OPENCLAW_BIN_ENV, raising=False)
    assert ob.openclaw_argv() == [ob.DEFAULT_OPENCLAW_BIN]


def test_openclaw_argv_honors_override(monkeypatch):
    monkeypatch.setenv(ob.OPENCLAW_BIN_ENV, "/usr/local/bin/openclaw")
    assert ob.openclaw_argv("channels", "status") == [
        "/usr/local/bin/openclaw",
        "channels",
        "status",
    ]


def test_seam_imports_are_stdlib_only():
    """The seam must stay library-tier: it imports only ``os`` (+ __future__)."""
    import ast
    from pathlib import Path

    tree = ast.parse(Path(ob.__file__).read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            modules.add(node.module or "")
    assert modules == {"os", "__future__"}, f"unexpected seam imports: {modules}"
