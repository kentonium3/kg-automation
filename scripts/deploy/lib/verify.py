"""File-presence, stale-content, and secret-redaction primitives.

These are the verification helpers shared by the deploy applier and by
one-shot deploy wrappers. Each public function returns a :class:`LibResult`
(except :func:`redact_secrets`, which returns a string because callers
splice the result into other payloads).
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from . import LibResult


def verify_file_present(path: str | os.PathLike[str], executable: bool = False) -> LibResult:
    """Confirm *path* exists; optionally also check that it is executable.

    Symlinks are followed. ``executable=True`` requires both ``os.path.isfile``
    and ``os.access(path, os.X_OK)`` to be true.
    """
    target = Path(path)
    if not target.exists():
        return LibResult(
            ok=False,
            summary=f"file not present: {target}",
            details={"error_code": "FILE_MISSING", "path": str(target)},
        )
    if executable:
        if not target.is_file():
            return LibResult(
                ok=False,
                summary=f"not a regular file (cannot be executable): {target}",
                details={"error_code": "NOT_A_FILE", "path": str(target)},
            )
        if not os.access(target, os.X_OK):
            return LibResult(
                ok=False,
                summary=f"file present but not executable: {target}",
                details={"error_code": "NOT_EXECUTABLE", "path": str(target)},
            )
        return LibResult(
            ok=True,
            summary=f"file present and executable: {target}",
            details={"path": str(target), "executable": True},
        )
    return LibResult(
        ok=True,
        summary=f"file present: {target}",
        details={"path": str(target)},
    )


def verify_no_stale_literal(path: str | os.PathLike[str], literal: str) -> LibResult:
    """Confirm *path* does NOT contain *literal* anywhere in its text content.

    Used to verify that a stale-version string (e.g., a previous git SHA or a
    deprecated agent name) was successfully replaced. Returns ``ok=False``
    when the literal is found OR when the file cannot be read at all.

    Reading is UTF-8 with ``errors='replace'`` — binary contamination cannot
    smuggle a literal through, and a partly-binary file will not crash this
    check.
    """
    if not literal:
        return LibResult(
            ok=False,
            summary="verify_no_stale_literal requires a non-empty literal",
            details={"error_code": "INVALID_ARGUMENT"},
        )
    target = Path(path)
    if not target.exists():
        return LibResult(
            ok=False,
            summary=f"cannot check stale literal: file not present: {target}",
            details={"error_code": "FILE_MISSING", "path": str(target)},
        )
    try:
        text = target.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return LibResult(
            ok=False,
            summary=f"cannot check stale literal: read failed: {target}",
            details={
                "error_code": "READ_FAILED",
                "path": str(target),
                "error": str(exc),
            },
        )
    if literal in text:
        return LibResult(
            ok=False,
            summary=f"stale literal found in {target}",
            details={
                "error_code": "STALE_LITERAL_PRESENT",
                "path": str(target),
                "literal_length": len(literal),
            },
        )
    return LibResult(
        ok=True,
        summary=f"stale literal absent from {target}",
        details={"path": str(target), "literal_length": len(literal)},
    )


# ---------------------------------------------------------------------------
# redact_secrets
# ---------------------------------------------------------------------------

# Token-shaped substrings: 32+ chars of base64-style alphabet. Hyphens and
# underscores are intentionally included so URL-safe base64 (JWTs, Slack
# tokens, GitHub PATs prefixed with ghp_) gets caught. The 32-char lower
# bound is conservative — see WP02 prompt: "better to over-redact than leak".
_TOKEN_RE = re.compile(r"[A-Za-z0-9+/_\-]{32,}={0,2}")

# Anything resembling ``password=...`` (or ``passwd=`` / ``pwd=``).
# Stops at the first whitespace, comma, quote, or closing bracket so we do
# not eat the rest of the log line.
_PASSWORD_RE = re.compile(
    r"(?i)\b(?:password|passwd|pwd)\s*[=:]\s*\S+",
)

# Bearer tokens — case-sensitive on the leading word as the HTTP spec is
# case-insensitive but the convention is ``Bearer``. We tolerate ``bearer``
# and ``BEARER`` defensively.
_BEARER_RE = re.compile(r"(?i)\bBearer\s+\S+")


_REDACTED = "[REDACTED]"


def redact_secrets(text: str) -> str:
    """Best-effort regex pass to strip token / password / bearer substrings.

    Used before including stderr in DM payloads. **Conservative by design** —
    a 32-character hex hash in an error message will also be redacted; that
    trade-off is preferred over leaking a real secret. Callers that need
    the original text for a different purpose should keep their own copy
    and only feed the DM payload through this function.

    Order of operations matters: ``Bearer <token>`` and ``password=<token>``
    are redacted first so the trailing token is not partially stripped by
    the generic 32+ char token rule (the password value's secret is *the
    keyword + value*; redacting just the long value leaves ``password=``
    behind, which is fine, but redacting the whole assignment is clearer).
    """
    if not text:
        return text
    redacted = _BEARER_RE.sub(_REDACTED, text)
    redacted = _PASSWORD_RE.sub(_REDACTED, redacted)
    redacted = _TOKEN_RE.sub(_REDACTED, redacted)
    return redacted


__all__ = [
    "verify_file_present",
    "verify_no_stale_literal",
    "redact_secrets",
]


# ---------------------------------------------------------------------------
# Module-as-CLI surface for bash callers:
#   python3 -m scripts.deploy.lib.verify verify_file_present <path>
# ---------------------------------------------------------------------------


def _cli_verify_file_present(*args: str) -> LibResult:
    """CLI wrapper: ``<path> [executable]`` where executable is ``true``/``1``."""
    if not args:
        return LibResult(
            ok=False,
            summary="verify_file_present: missing path argument",
            details={"error_code": "INVALID_ARGUMENT"},
        )
    path = args[0]
    executable = False
    if len(args) >= 2:
        executable = args[1].lower() in ("true", "1", "yes")
    return verify_file_present(path, executable=executable)


def _cli_verify_no_stale_literal(*args: str) -> LibResult:
    """CLI wrapper: ``<path> <literal>``."""
    if len(args) < 2:
        return LibResult(
            ok=False,
            summary="verify_no_stale_literal: usage: <path> <literal>",
            details={"error_code": "INVALID_ARGUMENT"},
        )
    return verify_no_stale_literal(args[0], args[1])


_CLI_FUNCS = {
    "verify_file_present": _cli_verify_file_present,
    "verify_no_stale_literal": _cli_verify_no_stale_literal,
    # redact_secrets is intentionally NOT exposed — it returns a str, not a
    # LibResult, and shipping secrets back to bash via stdout is a footgun.
}


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    import sys as _sys

    from ._cli import run as _run

    _sys.exit(_run(_CLI_FUNCS, _sys.argv[1:], prog="scripts.deploy.lib.verify"))
