"""Repo-wide guard: no bare no-argument ``dt.astimezone()`` in ``scripts/`` (#761).

On office2 the host TZ is ``Etc/UTC``, so a bare ``dt.astimezone()`` (no zone
argument) silently converts to UTC instead of the intended local/Eastern zone
— the #759 shape, where the alert bus rendered "local" == UTC. Every real
conversion must pass an explicit zone (``timezone.utc`` or an
``America/New_York`` ``ZoneInfo``); the canonical utilities in
``scripts/common/et_datetime.py`` do.

This is the durable regression guard for that rule. It is a pytest test (not a
tooling script) so it runs automatically under ``make test`` / test-ci with no
hook wiring, mirroring the SC-001 gate (``tests/common/test_sc001_grep.py``).
It ``ast``-walks every ``scripts/**/*.py`` and fails, naming each ``file:line``,
on any ``x.astimezone()`` call with no positional and no keyword arguments.
Positive/negative controls below keep it fails-closed.
"""
from __future__ import annotations

import ast
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_SCRIPTS_ROOT = _REPO_ROOT / "scripts"


def _bare_astimezone_findings(rel_posix: str, source: str) -> list[str]:
    """Return ``file:line`` findings for bare no-arg ``.astimezone()`` calls."""
    findings: list[str] = []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        # A synthetic control *fragment* may not parse as a module; real
        # runtime files always do.
        return findings
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if (
            isinstance(func, ast.Attribute)
            and func.attr == "astimezone"
            and not node.args
            and not node.keywords
        ):
            findings.append(
                f"{rel_posix}:{node.lineno}: bare astimezone() — pass an "
                f"explicit zone (timezone.utc or scripts.common.et_datetime.ET_ZONE)"
            )
    return findings


def _scan_files() -> list[Path]:
    return sorted(_SCRIPTS_ROOT.rglob("*.py"))


def _scan_all() -> list[str]:
    findings: list[str] = []
    for path in _scan_files():
        rel_posix = path.relative_to(_REPO_ROOT).as_posix()
        findings.extend(
            _bare_astimezone_findings(rel_posix, path.read_text(encoding="utf-8"))
        )
    return findings


# ---------------------------------------------------------------------------
# The gate
# ---------------------------------------------------------------------------


def test_no_bare_astimezone_in_scripts():
    """No ``scripts/`` code may call ``dt.astimezone()`` without a zone (#759)."""
    findings = _scan_all()
    assert not findings, (
        "Bare no-argument astimezone() found — on office2 (host TZ Etc/UTC) it "
        "silently yields UTC, not Eastern (#759). Pass an explicit zone or use "
        "scripts.common.et_datetime:\n  " + "\n  ".join(findings)
    )


def test_scan_actually_covers_files():
    """Guard the guard: a broken glob that scanned nothing would be vacuously
    green. Assert the scan sees known date-handling consumers."""
    rels = {p.relative_to(_REPO_ROOT).as_posix() for p in _scan_files()}
    assert "scripts/common/et_datetime.py" in rels
    assert "scripts/common/alert_bus/render.py" in rels
    assert "scripts/escalation/record_completion.py" in rels


def test_guard_fires_on_bare_call():
    """Positive control: a reintroduced bare ``astimezone()`` MUST be caught,
    otherwise the gate is a no-op."""
    for snippet in (
        "x = ts.astimezone()",
        "return dt.astimezone()",
        "value = some.nested.ts.astimezone()",
    ):
        hits = _bare_astimezone_findings("synthetic.py", snippet)
        assert hits, f"guard failed to fire on bare call {snippet!r}"


def test_guard_ignores_explicit_zone_calls():
    """Negative control: an ``astimezone(...)`` with an explicit zone (positional
    or keyword) must NOT flag — precision, no false positives."""
    for snippet in (
        "x = ts.astimezone(timezone.utc)",
        "local = ts.astimezone(ET_ZONE)",
        "d = ts.astimezone(ZoneInfo('America/New_York'))",
        "x = ts.astimezone(tz=timezone.utc)",
    ):
        hits = _bare_astimezone_findings("synthetic.py", snippet)
        assert hits == [], f"false positive on explicit-zone call {snippet!r}: {hits}"
