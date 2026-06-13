"""Idempotent SQLite + plaintext-file fixture builder for anthropic-verify tests.

Each builder writes an office2-shaped layout under a given root:

    <agents_dir>/<agent_id>/agent/openclaw-agent.sqlite

plus a plaintext file at ``<plaintext_path>``.

Three scenarios are supported:
  * :func:`build_healthy` — main has a populated row, all sub-agents empty,
    plaintext sha8 matches main's canonical sha8.
  * :func:`build_shadow` — like healthy plus the named sub-agent has rows in
    both ``auth_profile_store`` and ``auth_profile_state``.
  * :func:`build_drift` — like healthy but the plaintext file holds a
    different sentinel (sha8 mismatch).

Builders rebuild from scratch (delete then create) so they are idempotent
across repeated calls in the same test.

Sentinels are TEST values only. Real Anthropic keys are ~108 chars; these
match that length so the C-005 sanitization check is exercised by realistic
shapes. The sentinels never appear in stdout / stderr / Finding fields —
verified by ``test_anthropic_verify_output.py``.
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Optional


# 108-char sentinels (matches typical Anthropic key length so the
# ``__post_init__`` key-shape check applies in realistic conditions).
SENTINEL_CANONICAL = (
    "sk-ant-FIXTURE-SENTINEL-DO-NOT-USE-REAL-KEY-"
    "aB3xQ7zR9pL4mN8jK2vH5cF1gT0wEsdfg"
    "xY7vN3qK9wA2bP5tR8dG4fH1jL6cM0s"
)
SENTINEL_SHADOW = (
    "sk-ant-FIXTURE-SHADOW-DO-NOT-USE-REAL-KEY-"
    "zX9rT4kP2nA7vM1qB6jH3cD8fG5sL0wYabc"
    "mN3pQ7vR2bL5kT8dG4hJ6kL9zX1cV2b"
)
SENTINEL_PLAINTEXT_DRIFT = (
    "sk-ant-FIXTURE-PLAIN-DO-NOT-USE-REAL-KEY-"
    "qW4eR7tY1uI8oP2aS5dF3gH6jK9lZ0xCNbm"
    "aA1bB2cC3dD4eE5fF6gG7hH8iI9jJ0kK"
)


def _create_schema(con: sqlite3.Connection) -> None:
    """Create the two auth tables the verifier reads from."""
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS auth_profile_store (
            store_key TEXT PRIMARY KEY,
            store_json TEXT,
            updated_at INTEGER
        )
        """
    )
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS auth_profile_state (
            state_key TEXT PRIMARY KEY,
            state_json TEXT,
            updated_at INTEGER
        )
        """
    )


def _build_agent_sqlite(
    agents_dir: Path,
    agent_id: str,
    *,
    key_value: Optional[str],
    state_value: Optional[str] = None,
    updated_at: Optional[int] = None,
) -> Path:
    """Create ``<agents_dir>/<agent_id>/agent/openclaw-agent.sqlite``.

    If ``key_value`` is None and ``state_value`` is None, the SQLite file
    is created with empty tables (the healthy state for a sub-agent).
    """
    agent_dir = agents_dir / agent_id / "agent"
    agent_dir.mkdir(parents=True, exist_ok=True)
    sqlite_path = agent_dir / "openclaw-agent.sqlite"
    if sqlite_path.exists():
        sqlite_path.unlink()
    ts = updated_at if updated_at is not None else int(time.time() * 1000)
    con = sqlite3.connect(str(sqlite_path))
    try:
        _create_schema(con)
        if key_value is not None:
            store_json = json.dumps(
                {"profiles": {"anthropic:default": {"key": key_value}}}
            )
            con.execute(
                "INSERT INTO auth_profile_store(store_key, store_json, updated_at) "
                "VALUES(?, ?, ?)",
                ("primary", store_json, ts),
            )
        if state_value is not None:
            state_json = json.dumps({"primary": {"value": state_value}})
            con.execute(
                "INSERT INTO auth_profile_state(state_key, state_json, updated_at) "
                "VALUES(?, ?, ?)",
                ("primary", state_json, ts),
            )
        con.commit()
    finally:
        con.close()
    return sqlite_path


def _write_plaintext(path: Path, value: str) -> None:
    """Write ``value`` to ``path`` at mode 0600 (best effort)."""
    path.write_text(value, encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:  # pragma: no cover - tmpfs may reject chmod
        pass


# --------------------------------------------------------------------------- #
# Scenario builders
# --------------------------------------------------------------------------- #


# Six sub-agents mirroring the canonical office2 fleet (per contracts/cli.md).
SUB_AGENT_IDS = [
    "felix-admin-capture",
    "felix-admin-habits",
    "felix-admin-escalation",
    "felix-admin-tasker",
    "felix-admin-calendar",
]


def build_healthy(agents_dir: Path, plaintext_path: Path) -> None:
    """main populated; all sub-agents empty; plaintext sha matches main sha."""
    _build_agent_sqlite(
        agents_dir,
        "main",
        key_value=SENTINEL_CANONICAL,
        state_value=SENTINEL_CANONICAL,
    )
    for sub in SUB_AGENT_IDS:
        _build_agent_sqlite(
            agents_dir, sub, key_value=None, state_value=None
        )
    _write_plaintext(plaintext_path, SENTINEL_CANONICAL)


def build_shadow(
    agents_dir: Path,
    plaintext_path: Path,
    agent_id: str = "felix-admin-capture",
) -> None:
    """Healthy layout plus one shadow row on ``agent_id``."""
    build_healthy(agents_dir, plaintext_path)
    if agent_id not in SUB_AGENT_IDS and agent_id != "main":
        # Allow tests to specify a novel sub-agent; create its dir too.
        pass
    _build_agent_sqlite(
        agents_dir,
        agent_id,
        key_value=SENTINEL_SHADOW,
        state_value=SENTINEL_SHADOW,
    )


def build_drift(agents_dir: Path, plaintext_path: Path) -> None:
    """Healthy layout but plaintext holds a different sentinel."""
    build_healthy(agents_dir, plaintext_path)
    _write_plaintext(plaintext_path, SENTINEL_PLAINTEXT_DRIFT)


def build_main_empty(agents_dir: Path, plaintext_path: Path) -> None:
    """main exists but has zero rows in auth_profile_store."""
    _build_agent_sqlite(agents_dir, "main", key_value=None, state_value=None)
    for sub in SUB_AGENT_IDS:
        _build_agent_sqlite(
            agents_dir, sub, key_value=None, state_value=None
        )
    _write_plaintext(plaintext_path, SENTINEL_CANONICAL)


def build_plaintext_missing(agents_dir: Path, plaintext_path: Path) -> None:
    """Healthy main+sub-agents, but plaintext file is absent."""
    _build_agent_sqlite(
        agents_dir,
        "main",
        key_value=SENTINEL_CANONICAL,
        state_value=SENTINEL_CANONICAL,
    )
    for sub in SUB_AGENT_IDS:
        _build_agent_sqlite(
            agents_dir, sub, key_value=None, state_value=None
        )
    if plaintext_path.exists():
        plaintext_path.unlink()
