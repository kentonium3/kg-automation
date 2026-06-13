"""Deterministic detection core for anthropic-verify.

This module is filesystem read-only end-to-end (NFR-003). The only side
effects are network I/O (the Anthropic liveness ping) and stdout writes.

Layout:
  * Module-level constants — paths, timeouts, model name.
  * Read-only dataclasses — :class:`AgentAuthState`, :class:`PlaintextFileState`,
    :class:`AnthropicPingResult`.
  * Discovery + evaluation — :func:`discover_agents`, :func:`_read_agent_state`,
    :func:`read_plaintext_state`, :func:`evaluate_topology`.
  * Live ping — :func:`ping_anthropic` (uses stdlib ``urllib.request``).
  * Orchestrator — :func:`run_check`, returning the spec-FR-011 exit code.

The exit-code priority order is:
  ``substrate-gap (6) > network (5) > anthropic_rejected (4) > shadow (2) > drift (3)``
i.e. when multiple findings coexist, emit the most foundational failure.
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import List, Literal, Optional

from .findings import Finding, KEY_SHAPE_PREFIX, KEY_SHAPE_MIN_LEN


# --------------------------------------------------------------------------- #
# Constants (data-model.md)
# --------------------------------------------------------------------------- #

# Default canonical paths on office2. Tests override these via env vars set
# by the ``tmp_office2_root`` conftest fixture.
OPENCLAW_AGENTS_DIR = pathlib.Path("~/.openclaw/agents").expanduser()
PLAINTEXT_FILE = pathlib.Path("/data/services/openclaw/secrets/anthropic")

# Test override env-vars. Setting these redirects the verifier to a sandbox
# layout without changing the production constants. Production code never
# sets them; conftest does.
ENV_AGENTS_DIR = "ANTHROPIC_VERIFY_AGENTS_DIR"
ENV_PLAINTEXT_FILE = "ANTHROPIC_VERIFY_PLAINTEXT_FILE"

ANTHROPIC_BASE_URL = "https://api.anthropic.com"
ANTHROPIC_PING_MODEL = "claude-haiku-4-5"
ANTHROPIC_PING_MAX_TOKENS = 8
URLLIB_TOTAL_TIMEOUT_SEC = 15
SHA_FINGERPRINT_LEN = 8

# Exit codes — spec FR-011 / contracts/cli.md.
EXIT_GREEN = 0
EXIT_ERROR = 1
EXIT_SHADOW = 2
EXIT_DRIFT = 3
EXIT_ANTHROPIC_REJECTED = 4
EXIT_NETWORK = 5
EXIT_SUBSTRATE_GAP = 6


# --------------------------------------------------------------------------- #
# Data shapes
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class AgentAuthState:
    """One sub-agent's auth-row topology + (for main) canonical key fingerprint."""

    agent_id: str
    sqlite_path: pathlib.Path
    store_rows: int
    state_rows: int
    last_update_ms: int
    canonical_key_sha8: Optional[str]


@dataclass(frozen=True)
class PlaintextFileState:
    """The plaintext credential file's fingerprint + stat() snapshot."""

    path: pathlib.Path
    exists: bool
    size_bytes: int
    sha8: Optional[str]
    mode: int
    uid: int
    gid: int


@dataclass(frozen=True)
class AnthropicPingResult:
    """Single API call result. Never carries the key value, even in error_summary."""

    status: Literal["ok", "rejected", "network_error"]
    http_status: Optional[int]
    model_echoed: Optional[str]
    error_summary: Optional[str]


# --------------------------------------------------------------------------- #
# Path resolution
# --------------------------------------------------------------------------- #


def _agents_dir() -> pathlib.Path:
    override = os.environ.get(ENV_AGENTS_DIR)
    if override:
        return pathlib.Path(override).expanduser()
    return OPENCLAW_AGENTS_DIR


def _plaintext_file() -> pathlib.Path:
    override = os.environ.get(ENV_PLAINTEXT_FILE)
    if override:
        return pathlib.Path(override).expanduser()
    return PLAINTEXT_FILE


# --------------------------------------------------------------------------- #
# Discovery + topology
# --------------------------------------------------------------------------- #


def discover_agents(root: Optional[pathlib.Path] = None) -> List[AgentAuthState]:
    """Glob ``<root>/*/agent/openclaw-agent.sqlite`` and return one state per agent.

    Sub-agent IDs are derived from the directory name two levels up from the
    SQLite file. Sorted alphabetically for deterministic output.
    """
    root = root if root is not None else _agents_dir()
    states: List[AgentAuthState] = []
    if not root.exists():
        return states
    for agent_dir in sorted(root.glob("*/agent")):
        sqlite_path = agent_dir / "openclaw-agent.sqlite"
        if not sqlite_path.exists():
            continue
        agent_id = agent_dir.parent.name
        states.append(_read_agent_state(agent_id, sqlite_path))
    return states


def _read_agent_state(agent_id: str, sqlite_path: pathlib.Path) -> AgentAuthState:
    """SELECT counts + (for main only) the canonical key sha256[:8].

    Never returns the key value. Closes the SQLite connection on every path.
    """
    con = sqlite3.connect(str(sqlite_path))
    try:
        store_rows = con.execute(
            "SELECT COUNT(*) FROM auth_profile_store"
        ).fetchone()[0]
        state_rows = con.execute(
            "SELECT COUNT(*) FROM auth_profile_state"
        ).fetchone()[0]
        last_store = con.execute(
            "SELECT COALESCE(MAX(updated_at), 0) FROM auth_profile_store"
        ).fetchone()[0]
        last_state = con.execute(
            "SELECT COALESCE(MAX(updated_at), 0) FROM auth_profile_state"
        ).fetchone()[0]
        last_update = max(int(last_store), int(last_state))

        canonical_sha8: Optional[str] = None
        if agent_id == "main" and store_rows > 0:
            row = con.execute(
                "SELECT store_json FROM auth_profile_store WHERE store_key='primary'"
            ).fetchone()
            if row is not None:
                try:
                    payload = json.loads(row[0])
                    key = (
                        payload.get("profiles", {})
                        .get("anthropic:default", {})
                        .get("key")
                    )
                    if isinstance(key, str) and key:
                        canonical_sha8 = hashlib.sha256(
                            key.encode("utf-8")
                        ).hexdigest()[:SHA_FINGERPRINT_LEN]
                except (json.JSONDecodeError, AttributeError, TypeError):
                    canonical_sha8 = None
        return AgentAuthState(
            agent_id=agent_id,
            sqlite_path=sqlite_path,
            store_rows=int(store_rows),
            state_rows=int(state_rows),
            last_update_ms=last_update,
            canonical_key_sha8=canonical_sha8,
        )
    finally:
        con.close()


def _read_main_canonical_key(sqlite_path: pathlib.Path) -> Optional[str]:
    """Return the canonical key VALUE (not fingerprint) from main's SQLite.

    Used by :func:`ping_anthropic` only. Caller must never let this value
    escape into stdout / stderr / a Finding. Returns ``None`` when main has
    no primary row or the JSON shape is unexpected.
    """
    con = sqlite3.connect(str(sqlite_path))
    try:
        row = con.execute(
            "SELECT store_json FROM auth_profile_store WHERE store_key='primary'"
        ).fetchone()
        if row is None:
            return None
        try:
            payload = json.loads(row[0])
            key = (
                payload.get("profiles", {})
                .get("anthropic:default", {})
                .get("key")
            )
            if isinstance(key, str) and key:
                return key
        except (json.JSONDecodeError, AttributeError, TypeError):
            return None
        return None
    finally:
        con.close()


def read_plaintext_state(
    path: Optional[pathlib.Path] = None,
) -> PlaintextFileState:
    """Read the plaintext file's fingerprint without ever returning its value."""
    path = path if path is not None else _plaintext_file()
    if not path.exists():
        return PlaintextFileState(
            path=path,
            exists=False,
            size_bytes=0,
            sha8=None,
            mode=0,
            uid=0,
            gid=0,
        )
    st = path.stat()
    raw = path.read_bytes().strip()
    sha8 = hashlib.sha256(raw).hexdigest()[:SHA_FINGERPRINT_LEN]
    return PlaintextFileState(
        path=path,
        exists=True,
        size_bytes=len(raw),
        sha8=sha8,
        mode=st.st_mode & 0o777,
        uid=st.st_uid,
        gid=st.st_gid,
    )


def _read_plaintext_value(path: pathlib.Path) -> Optional[str]:
    """Return the plaintext file's raw string value for the ping.

    Caller must never let this escape into stdout / stderr / a Finding.
    """
    if not path.exists():
        return None
    raw = path.read_bytes().strip()
    if not raw:
        return None
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return None


def evaluate_topology(
    states: List[AgentAuthState],
    plaintext: PlaintextFileState,
) -> List[Finding]:
    """Produce findings for shadow / main_empty / drift / plaintext_missing.

    Order: main_empty short-circuits everything else (without a canonical key
    the drift comparison is meaningless). Otherwise: shadow findings (one per
    sub-agent), then plaintext_missing OR drift (one or the other, never both).
    """
    findings: List[Finding] = []
    main_state = next((s for s in states if s.agent_id == "main"), None)

    if main_state is None or main_state.store_rows == 0:
        findings.append(
            Finding(
                type="main_empty",
                target="main",
                evidence={
                    "agent": "main",
                    "sqlite_path": (
                        str(main_state.sqlite_path)
                        if main_state is not None
                        else "missing"
                    ),
                },
                suggested_action=(
                    "Run anthropic-rotate.sh to establish the canonical key."
                ),
            )
        )
        return findings

    for s in states:
        if s.agent_id == "main":
            continue
        if s.store_rows > 0 or s.state_rows > 0:
            findings.append(
                Finding(
                    type="shadow",
                    target=s.agent_id,
                    evidence={
                        "agent": s.agent_id,
                        "store_rows": s.store_rows,
                        "state_rows": s.state_rows,
                        "last_update_ms": s.last_update_ms,
                        "sqlite_path": str(s.sqlite_path),
                    },
                    suggested_action=(
                        "anthropic-verify --repair  "
                        "(clears per-agent rows; restart gateway afterward)"
                    ),
                )
            )

    if not plaintext.exists:
        findings.append(
            Finding(
                type="plaintext_missing",
                target=str(plaintext.path),
                evidence={"plaintext_path": str(plaintext.path)},
                suggested_action=(
                    "Run anthropic-rotate.sh to write the plaintext file."
                ),
            )
        )
    elif plaintext.sha8 != main_state.canonical_key_sha8:
        findings.append(
            Finding(
                type="drift",
                target=str(plaintext.path),
                evidence={
                    "plaintext_sha8": plaintext.sha8 or "",
                    "sqlite_sha8": main_state.canonical_key_sha8 or "",
                    "plaintext_path": str(plaintext.path),
                    "sqlite_path": str(main_state.sqlite_path),
                },
                suggested_action=(
                    "anthropic-verify --repair  "
                    "(rewrites plaintext from main SQLite, atomic)"
                ),
            )
        )

    return findings


# --------------------------------------------------------------------------- #
# Anthropic liveness ping
# --------------------------------------------------------------------------- #


def _scrub(text: str) -> str:
    """Defensive: redact any ``sk-ant-`` substring before returning.

    Anthropic's API never echoes the key back, but if it ever did this
    stops it from reaching stdout / stderr / a Finding. The redaction
    replaces the prefix + 108 trailing chars (typical real-key length)
    with ``[REDACTED]``; shorter shapes are still scrubbed at the prefix.
    """
    out = text
    while True:
        idx = out.find(KEY_SHAPE_PREFIX)
        if idx == -1:
            return out
        # Replace prefix + up to (KEY_SHAPE_MIN_LEN + 30) trailing chars so we
        # over-scrub rather than under-scrub. Subsequent loop iterations clean
        # any residue.
        end = idx + KEY_SHAPE_MIN_LEN + 30
        out = out[:idx] + "[REDACTED]" + out[end:]


def ping_anthropic(key: str) -> AnthropicPingResult:
    """POST /v1/messages with a tiny payload; classify the outcome.

    Never logs or returns the key. Errors are scrubbed of any key-shape
    substring before returning.
    """
    payload = json.dumps(
        {
            "model": ANTHROPIC_PING_MODEL,
            "max_tokens": ANTHROPIC_PING_MAX_TOKENS,
            "messages": [{"role": "user", "content": "ping"}],
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        f"{ANTHROPIC_BASE_URL}/v1/messages",
        data=payload,
        headers={
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=URLLIB_TOTAL_TIMEOUT_SEC) as resp:
            body_raw = resp.read()
            try:
                body = json.loads(body_raw)
                model_echoed = body.get("model") if isinstance(body, dict) else None
            except (json.JSONDecodeError, AttributeError, TypeError):
                model_echoed = None
            return AnthropicPingResult(
                status="ok",
                http_status=int(getattr(resp, "status", 200)),
                model_echoed=model_echoed,
                error_summary=None,
            )
    except urllib.error.HTTPError as e:
        try:
            snippet_raw = e.read().decode("utf-8", errors="replace")[:80]
        except Exception:  # pragma: no cover - defensive
            snippet_raw = ""
        return AnthropicPingResult(
            status="rejected",
            http_status=int(e.code),
            model_echoed=None,
            error_summary=_scrub(snippet_raw),
        )
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        return AnthropicPingResult(
            status="network_error",
            http_status=None,
            model_echoed=None,
            error_summary=_scrub(f"{type(e).__name__}: {e}"),
        )


# --------------------------------------------------------------------------- #
# Exit-code priority
# --------------------------------------------------------------------------- #


def _exit_code_from_findings(
    findings: List[Finding], ping: AnthropicPingResult
) -> int:
    """Apply spec FR-011 priority order.

    substrate-gap (6) > network (5) > anthropic_rejected (4) > shadow (2) > drift (3).
    """
    types = {f.type for f in findings}
    if "main_empty" in types or "plaintext_missing" in types:
        return EXIT_SUBSTRATE_GAP
    if ping.status == "network_error":
        return EXIT_NETWORK
    if ping.status == "rejected":
        return EXIT_ANTHROPIC_REJECTED
    if "shadow" in types:
        return EXIT_SHADOW
    if "drift" in types:
        return EXIT_DRIFT
    return EXIT_GREEN


# --------------------------------------------------------------------------- #
# Orchestrator
# --------------------------------------------------------------------------- #


def _format_green_agent_line(s: AgentAuthState, is_main: bool) -> str:
    if is_main:
        sha = s.canonical_key_sha8 or ""
        return (
            f"ok    {s.agent_id:<25} "
            f"auth_profile_store={s.store_rows} "
            f"auth_profile_state={s.state_rows} "
            f"sha8={sha}"
        )
    return (
        f"ok    {s.agent_id:<25} "
        f"auth_profile_store={s.store_rows} "
        f"auth_profile_state={s.state_rows} "
        f"(inherits main)"
    )


def run_check() -> int:
    """Detect topology + drift + Anthropic liveness; emit report; return exit code.

    Filesystem read-only (NFR-003). Stdout-only output (NFR-002 / stderr is
    reserved for unexpected errors → exit 1).
    """
    start = time.monotonic()
    try:
        states = discover_agents()
        plaintext = read_plaintext_state()
        findings = evaluate_topology(states, plaintext)

        # Decide whether to ping. Skip the live call when substrate is
        # broken — ping_anthropic needs the plaintext key, and on
        # plaintext_missing / main_empty there's nothing to ping with.
        # That keeps --check from spending a live API call on a known-bad
        # substrate.
        ping: AnthropicPingResult
        skip_ping = False
        if not plaintext.exists:
            skip_ping = True
        else:
            main_state = next((s for s in states if s.agent_id == "main"), None)
            if main_state is None or main_state.store_rows == 0:
                skip_ping = True
        if skip_ping:
            ping = AnthropicPingResult(
                status="ok",  # not used; substrate-gap dominates exit code
                http_status=None,
                model_echoed=None,
                error_summary=None,
            )
        else:
            key = _read_plaintext_value(plaintext.path)
            if key is None:
                ping = AnthropicPingResult(
                    status="network_error",
                    http_status=None,
                    model_echoed=None,
                    error_summary="plaintext-read-failed",
                )
            else:
                ping = ping_anthropic(key)

        # Classify ping into a Finding if non-ok and substrate is OK.
        substrate_broken = any(
            f.type in ("main_empty", "plaintext_missing") for f in findings
        )
        if not substrate_broken:
            if ping.status == "rejected":
                findings.append(
                    Finding(
                        type="anthropic_rejected",
                        target="anthropic",
                        evidence={
                            "http_status": ping.http_status or 0,
                            "response_summary": ping.error_summary or "",
                        },
                        suggested_action=(
                            "anthropic-rotate.sh  "
                            "(key was revoked or rotated upstream; "
                            "full rotation required)"
                        ),
                    )
                )
            elif ping.status == "network_error":
                findings.append(
                    Finding(
                        type="network",
                        target="anthropic",
                        evidence={
                            "error_class": (ping.error_summary or "").split(":")[0],
                            "error_message": ping.error_summary or "",
                        },
                        suggested_action=(
                            "retry anthropic-verify --check after "
                            "network connectivity restored"
                        ),
                    )
                )

        # ---- Emit human-readable report (NFR-002) ----
        print("==> anthropic-verify --check")
        print(f"==> agents: {len(states)} discovered")

        main_state = next((s for s in states if s.agent_id == "main"), None)
        # main first, then sub-agents alphabetically — discover_agents already sorts.
        if main_state is not None:
            print(_format_green_agent_line(main_state, is_main=True))

        sub_findings_by_agent = {
            f.target: f for f in findings if f.type == "shadow"
        }
        for s in states:
            if s.agent_id == "main":
                continue
            if s.agent_id in sub_findings_by_agent:
                print(sub_findings_by_agent[s.agent_id].fmt_line())
            else:
                print(_format_green_agent_line(s, is_main=False))

        # Plaintext + ping lines (or their finding equivalents).
        substrate_findings = [
            f for f in findings if f.type in ("main_empty", "plaintext_missing")
        ]
        drift_finding = next((f for f in findings if f.type == "drift"), None)
        rejected_finding = next(
            (f for f in findings if f.type == "anthropic_rejected"), None
        )
        network_finding = next((f for f in findings if f.type == "network"), None)

        for f in substrate_findings:
            print(f.fmt_line())

        if drift_finding is not None:
            print(drift_finding.fmt_line())
        elif plaintext.exists and not substrate_broken:
            print(
                f"ok    plaintext-file            "
                f"sha8={plaintext.sha8 or ''} (matches main)"
            )

        if rejected_finding is not None:
            print(rejected_finding.fmt_line())
        elif network_finding is not None:
            print(network_finding.fmt_line())
        elif not substrate_broken and ping.status == "ok":
            print(
                "ok    anthropic-ping            "
                f"HTTP {ping.http_status or 200} "
                f"model={ping.model_echoed or ANTHROPIC_PING_MODEL}"
            )

        # ---- Verdict line + exit code ----
        exit_code = _exit_code_from_findings(findings, ping)
        elapsed = time.monotonic() - start
        verdict = _verdict_label(exit_code)
        print(f"==> verify result: {verdict} (exit {exit_code}) in {elapsed:.1f}s")
        return exit_code
    except Exception as e:  # pragma: no cover - defensive top-level
        # Per CLI contract: unexpected errors go to stderr, exit 1.
        # Scrub the message defensively even though no Finding constructor ran.
        print(f"anthropic-verify: unexpected error: {_scrub(repr(e))}", file=sys.stderr)
        return EXIT_ERROR


def _verdict_label(exit_code: int) -> str:
    return {
        EXIT_GREEN: "green",
        EXIT_ERROR: "error",
        EXIT_SHADOW: "shadow detected",
        EXIT_DRIFT: "drift detected",
        EXIT_ANTHROPIC_REJECTED: "anthropic rejected",
        EXIT_NETWORK: "network failure",
        EXIT_SUBSTRATE_GAP: "substrate gap",
    }.get(exit_code, "error")
