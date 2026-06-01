"""Deterministic filer for signal-driven threshold trips (WP-02 T008/T009).

Stateless subprocess invoker. Given a signal that has tripped its
threshold, the filer:

1. Builds a deterministic title + problem-statement + observed-context
   from the extraction result and signal definition.
2. Writes the problem-statement and observed-context to two tempfiles
   (one each, ``delete=False`` so we control cleanup explicitly).
3. Shells out to
   ``scripts/openclaw/agents/main/felix-file-issue.py`` per the contract
   in ``contracts/filer-invocation.contract.md``.
4. Parses the helper's JSON line from stdout to return the issue number
   and URL.
5. Cleans up the tempfiles in a ``finally`` block — even on success,
   timeout, or unexpected exception.

The filer NEVER raises into the cycle orchestrator's main path. Every
failure mode returns a :class:`FilingResult` whose ``error`` field is
populated with a :class:`FilingError` carrying a stable
``error_type`` taxonomy (per the contract).

The dedup-on-open-issue check (T009) lives here too — it's a thin
``gh issue view`` wrapper that the orchestrator (``tick.py``) calls
BEFORE invoking :func:`file_threshold_trip`. The check is fail-open:
when ``gh`` errors or times out, the filer reports "not open" so the
orchestrator proceeds with filing. The operator can then manually
close duplicates if a stale ``last_filed_issue_ref`` was actually
still open. This mirrors the felix-doc-auditor convention.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Sequence

from scripts.openclaw.observation.signals.config_loader import (
    SignalDefinition,
)
from scripts.openclaw.observation.signals.types import SignalExtraction
from scripts.openclaw.observation.state import SignalState

__all__ = [
    "DEFAULT_FELIX_FILE_ISSUE_PATH",
    "FILER_SUBPROCESS_TIMEOUT_SEC",
    "GH_ISSUE_VIEW_TIMEOUT_SEC",
    "FilingError",
    "FilingResult",
    "build_observed_context",
    "build_problem_statement",
    "build_title",
    "check_existing_issue_open",
    "file_threshold_trip",
]


# Repo-root relative path to the existing felix-file-issue helper.
# Resolved at module import time so the orchestrator can swap it via
# the optional ``felix_file_issue_path`` arg on the public entrypoints
# (useful for tests that want to dry-run against the local checkout).
_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_FELIX_FILE_ISSUE_PATH = (
    _REPO_ROOT / "scripts" / "openclaw" / "agents" / "main" / "felix-file-issue.py"
)


# Per the contract: 60-second timeout for the filer subprocess.
FILER_SUBPROCESS_TIMEOUT_SEC = 60
# Shorter timeout for ``gh issue view`` — a read against an existing
# issue should respond in well under 10s on a healthy network.
GH_ISSUE_VIEW_TIMEOUT_SEC = 10

# Repo identifier the helper expects. The deterministic filer never
# overrides this — it's pinned for traceability of all signal-driven
# filings.
DEFAULT_REPO = "kentonium3/kg-automation"


@dataclass(frozen=True)
class FilingError:
    """Structured error record returned in :class:`FilingResult.error`.

    ``error_type`` is one of the values enumerated in the contract:

    - ``filer_subprocess_failed`` — non-zero exit from felix-file-issue.py
    - ``filer_timeout`` — subprocess timed out (60s).
    - ``filer_output_unparseable`` — stdout had no JSON line we could parse.
    - ``filer_identity_mismatch`` — helper rejected the active gh identity.
    - ``filer_invocation_error`` — pre-subprocess error (e.g., FileNotFoundError
      on ``python3`` itself). Defensive; not in the original contract
      but kept so the taxonomy is exhaustive.
    """

    error_type: str
    error_message: str


@dataclass(frozen=True)
class FilingResult:
    """Return value from :func:`file_threshold_trip`.

    Exactly one of ``(issue_number, error)`` is populated on a normal
    return. Callers test ``result.error is None`` to branch on success.
    """

    issue_number: Optional[int]
    issue_url: Optional[str]
    error: Optional[FilingError]


# ---------------------------------------------------------------------------
# Title / body construction
# ---------------------------------------------------------------------------


# Mapping from signal_id to a human-readable short name used in the
# issue title. Falls back to the signal_id with underscores → spaces
# when a signal isn't enumerated here.
_SIGNAL_HUMAN_NAME = {
    "whatsapp_creds_restore": "WhatsApp creds.json corruption",
    "web_watchdog_reconnect": "Web-channel watchdog reconnect storm",
    "openclaw_unhandled_error": "OpenClaw unhandled-error burst",
}


def _human_name(signal_id: str) -> str:
    """Return a short human-readable label for a signal_id."""
    return _SIGNAL_HUMAN_NAME.get(
        signal_id, signal_id.replace("_", " ")
    )


def build_title(
    signal_def: SignalDefinition, extraction: SignalExtraction
) -> str:
    """Build the deterministic title for a threshold trip.

    The title is the same every time for a given (signal, count_cycle,
    count_rolling) triple so two cycles that observe the same numbers
    file titles that differ only in counts — easy to scan in the issue
    list. The helper strips the type prefix; we don't include "Bug:"
    here.
    """
    name = _human_name(signal_def.signal_id)
    return (
        f"{name} detected ({extraction.count_cycle} events in 15-min "
        f"cycle, {extraction.count_rolling} in rolling "
        f"{signal_def.rolling_window_minutes}-min window)"
    )


def build_problem_statement(
    signal_def: SignalDefinition,
    extraction: SignalExtraction,
    state: SignalState,
    now_utc: datetime,
) -> str:
    """Build the one-paragraph problem statement for the issue body.

    The paragraph names the signal, the observed counts, the cycle
    window, and references the source log glob. Operators reading the
    issue should understand WHAT was detected and WHERE without
    clicking through to the observed-context section.
    """
    name = _human_name(signal_def.signal_id)
    last_event = (
        extraction.last_event_at_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
        if extraction.last_event_at_utc is not None
        else "unknown"
    )
    cycle_end = now_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
    return (
        f"The signal-extraction pipeline detected {name.lower()} in the "
        f"most recent observation cycle ending at {cycle_end}. The "
        f"signal counted {extraction.count_cycle} matching events in "
        f"the 15-minute cycle and {extraction.count_rolling} events in "
        f"the rolling {signal_def.rolling_window_minutes}-minute "
        f"window — both at or above the configured thresholds "
        f"(cycle={signal_def.cycle_threshold}, "
        f"rolling={signal_def.rolling_threshold}). The most recent "
        f"matching event occurred at {last_event}. Source: "
        f"{signal_def.source_path_pattern} "
        f"(match_pattern={signal_def.match_pattern!r}, "
        f"signal_id={signal_def.signal_id!r}). This issue was filed "
        f"deterministically by the signal-extraction loop (no LLM "
        f"involvement); please triage per the issue area + tier "
        f"hypothesis. Prior filed reference for this signal: "
        f"{state.last_filed_issue_ref!r}."
    )


def build_observed_context(
    signal_def: SignalDefinition, extraction: SignalExtraction
) -> str:
    """Build the observed-context body section (representative excerpts).

    The extractor already capped the excerpt list at
    ``signal_def.excerpt_lines`` and redacted long values per spec
    C-005. We just join them with blank lines so the markdown reads
    nicely as a fenced code block. The helper will wrap us in a
    ``Observed Context`` heading on its end.
    """
    if not extraction.excerpts:
        return (
            "No representative excerpts were captured during the "
            "extraction (extractor returned an empty list)."
        )
    capped = extraction.excerpts[: signal_def.excerpt_lines]
    return "\n\n".join(capped)


# ---------------------------------------------------------------------------
# Tempfile helpers
# ---------------------------------------------------------------------------


def _write_tempfile(content: str, suffix: str) -> Path:
    """Write ``content`` to a ``NamedTemporaryFile(delete=False)``.

    Returns the path. Caller is responsible for cleanup. Uses UTF-8;
    ``flush()`` + ``close()`` before returning so the subprocess sees
    a fully-written file.
    """
    fp = tempfile.NamedTemporaryFile(
        mode="w",
        suffix=suffix,
        delete=False,
        encoding="utf-8",
    )
    try:
        fp.write(content)
        fp.flush()
    finally:
        fp.close()
    return Path(fp.name)


def _cleanup(*paths: Optional[Path]) -> None:
    """Best-effort delete of tempfiles in a ``finally`` block."""
    for path in paths:
        if path is None:
            continue
        try:
            path.unlink()
        except FileNotFoundError:
            continue
        except OSError as exc:  # pragma: no cover — best-effort
            print(
                f"WARN: filer: failed to delete tempfile {path}: {exc}",
                file=sys.stderr,
            )


# ---------------------------------------------------------------------------
# Output parsing
# ---------------------------------------------------------------------------


def _parse_helper_output(stdout: str) -> Optional[dict]:
    """Extract the helper's JSON-line output from ``stdout``.

    The helper writes one JSON line (e.g.,
    ``{"issue_number": 491, ...}``) followed by a ``SUMMARY:`` line.
    We search bottom-up for the first JSON-shaped line — robust to
    extra debug lines the helper might add in the future.
    """
    for line in reversed(stdout.splitlines()):
        stripped = line.strip()
        if stripped.startswith("{") and stripped.endswith("}"):
            try:
                parsed = json.loads(stripped)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict) and "issue_number" in parsed:
                return parsed
    return None


def _classify_stderr(stderr: str) -> Optional[str]:
    """Return a stable ``error_type`` when stderr matches a known shape.

    The identity-mismatch check is the load-bearing one — the helper
    surfaces it with the verbatim string "Expected gh identity
    'kg-felix-bot' but found ..." and the operator needs to know.
    """
    if "Expected gh identity 'kg-felix-bot'" in stderr:
        return "filer_identity_mismatch"
    return None


# ---------------------------------------------------------------------------
# Main entrypoints
# ---------------------------------------------------------------------------


def _build_subprocess_args(
    signal_def: SignalDefinition,
    title: str,
    problem_statement_path: Path,
    observed_context_path: Path,
    felix_file_issue_path: Path,
) -> list[str]:
    """Assemble the argv list for ``subprocess.run``.

    Exposed at module scope so the contract test in test_filer.py can
    invoke ``felix-file-issue.py --dry-run`` with the same args the
    filer constructs (catches argument-schema drift between the
    deterministic filer and the helper).
    """
    return [
        sys.executable or "python3",
        str(felix_file_issue_path),
        "--type",
        "bug",
        "--title",
        title,
        "--problem-statement-file",
        str(problem_statement_path),
        "--observed-context-file",
        str(observed_context_path),
        "--tier-hypothesis",
        signal_def.tier_hypothesis,
        "--area",
        signal_def.area_label,
        "--priority",
        signal_def.priority,
        "--spec-ready-eval",
        "brief",
    ]


def file_threshold_trip(
    signal_def: SignalDefinition,
    extraction: SignalExtraction,
    state: SignalState,
    now_utc: datetime,
    *,
    felix_file_issue_path: Path = DEFAULT_FELIX_FILE_ISSUE_PATH,
    timeout_sec: int = FILER_SUBPROCESS_TIMEOUT_SEC,
) -> FilingResult:
    """File a threshold-trip issue via the existing helper.

    Args:
        signal_def: Signal definition that tripped.
        extraction: The extractor's per-cycle result (count, excerpts).
        state: Current state record (used for the problem statement's
            prior-filed reference).
        now_utc: Cycle clock — timezone-aware UTC. Used for the
            "cycle ended at" timestamp in the problem statement.
        felix_file_issue_path: Override for the helper path. Tests use
            this to point at the local checkout instead of resolving
            via the repo-root parent walk.
        timeout_sec: Subprocess timeout (default 60s per contract).

    Returns:
        A :class:`FilingResult`. On success ``issue_number`` and
        ``issue_url`` are populated and ``error is None``. On any
        failure mode (subprocess error, timeout, parse failure,
        identity mismatch) ``error`` carries a :class:`FilingError`
        and the issue fields are ``None``. The filer never raises.
    """
    if now_utc.tzinfo is None:
        # Defensive: every caller already passes tz-aware UTC, but
        # encode the precondition so a future caller can't slip a
        # naive datetime through and silently break the timestamp in
        # the problem statement.
        return FilingResult(
            issue_number=None,
            issue_url=None,
            error=FilingError(
                error_type="filer_invocation_error",
                error_message=(
                    "file_threshold_trip: now_utc must be tz-aware"
                ),
            ),
        )

    title = build_title(signal_def, extraction)
    problem_statement = build_problem_statement(
        signal_def, extraction, state, now_utc
    )
    observed_context = build_observed_context(signal_def, extraction)

    ps_path: Optional[Path] = None
    ctx_path: Optional[Path] = None
    try:
        ps_path = _write_tempfile(problem_statement, suffix=".ps.md")
        ctx_path = _write_tempfile(observed_context, suffix=".ctx.md")
        argv = _build_subprocess_args(
            signal_def=signal_def,
            title=title,
            problem_statement_path=ps_path,
            observed_context_path=ctx_path,
            felix_file_issue_path=felix_file_issue_path,
        )

        try:
            result = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                timeout=timeout_sec,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            return FilingResult(
                issue_number=None,
                issue_url=None,
                error=FilingError(
                    error_type="filer_timeout",
                    error_message=(
                        f"felix-file-issue.py exceeded {timeout_sec}s: "
                        f"{exc}"
                    ),
                ),
            )
        except (FileNotFoundError, OSError) as exc:
            return FilingResult(
                issue_number=None,
                issue_url=None,
                error=FilingError(
                    error_type="filer_invocation_error",
                    error_message=(
                        f"Could not invoke felix-file-issue.py: {exc}"
                    ),
                ),
            )

        if result.returncode != 0:
            # Identity mismatch takes precedence — the helper exits 1
            # for many reasons, but only the identity case carries
            # this exact stderr shape and only it is operator-actionable.
            classified = _classify_stderr(result.stderr or "")
            err_type = classified or "filer_subprocess_failed"
            return FilingResult(
                issue_number=None,
                issue_url=None,
                error=FilingError(
                    error_type=err_type,
                    error_message=(
                        f"felix-file-issue.py exit "
                        f"{result.returncode}: "
                        f"{(result.stderr or '').strip()[:500]}"
                    ),
                ),
            )

        parsed = _parse_helper_output(result.stdout or "")
        if parsed is None:
            return FilingResult(
                issue_number=None,
                issue_url=None,
                error=FilingError(
                    error_type="filer_output_unparseable",
                    error_message=(
                        "felix-file-issue.py stdout had no parseable "
                        f"JSON line: {(result.stdout or '')[:500]!r}"
                    ),
                ),
            )

        try:
            issue_number = int(parsed["issue_number"])
        except (TypeError, ValueError, KeyError) as exc:
            return FilingResult(
                issue_number=None,
                issue_url=None,
                error=FilingError(
                    error_type="filer_output_unparseable",
                    error_message=(
                        f"helper JSON has invalid issue_number: {exc}"
                    ),
                ),
            )
        issue_url = parsed.get("issue_url")
        if not isinstance(issue_url, str):
            issue_url = None

        return FilingResult(
            issue_number=issue_number,
            issue_url=issue_url,
            error=None,
        )
    finally:
        _cleanup(ps_path, ctx_path)


def check_existing_issue_open(
    issue_number: int,
    *,
    repo: str = DEFAULT_REPO,
    timeout_sec: int = GH_ISSUE_VIEW_TIMEOUT_SEC,
) -> bool:
    """Return ``True`` iff GitHub reports the issue is still OPEN.

    Fail-open semantics (per spec §dedup): on any error — gh missing,
    network timeout, non-zero exit, unparseable JSON — we return
    ``False`` so the orchestrator proceeds with filing. An operator
    can manually close duplicates if a stale ref was actually still
    open. The alternative (fail-closed) would silently suppress
    legitimate filings whenever ``gh`` flaked, which is worse.

    The function logs errors to stderr but never raises.
    """
    try:
        result = subprocess.run(
            [
                "gh",
                "issue",
                "view",
                str(issue_number),
                "--repo",
                repo,
                "--json",
                "state",
            ],
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        print(
            f"WARN: filer: gh issue view #{issue_number} timed out: {exc}",
            file=sys.stderr,
        )
        return False
    except (FileNotFoundError, OSError) as exc:
        print(
            f"WARN: filer: gh CLI unavailable: {exc}",
            file=sys.stderr,
        )
        return False

    if result.returncode != 0:
        print(
            f"WARN: filer: gh issue view #{issue_number} exit "
            f"{result.returncode}: "
            f"{(result.stderr or '').strip()[:200]}",
            file=sys.stderr,
        )
        return False

    try:
        payload = json.loads(result.stdout or "")
    except json.JSONDecodeError as exc:
        print(
            f"WARN: filer: gh issue view #{issue_number} stdout not "
            f"JSON: {exc}",
            file=sys.stderr,
        )
        return False

    state = payload.get("state") if isinstance(payload, dict) else None
    return state == "OPEN"
