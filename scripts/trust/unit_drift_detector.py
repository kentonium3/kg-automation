"""Deployed-unit-vs-repo systemd drift detector (#817).

Detects the #816 class: a systemd-user unit **deployed** on office2 whose content
has fallen behind its **repo canonical** (a stale ``ExecStart`` / ``Environment`` /
``PYTHONPATH``). That drift fails silently every run until the unit's next
invocation — #816's ``credential-health-check.service`` was dead for ~6 weeks. The
daily security audit hashes unit *names*, not content, so this drift is otherwise
invisible.

Lean v1 (glob-based, #817): the repo canonical for each managed unit is globbed
from the four known source dirs; every deployed unit that has a repo source is
compared (whitespace-normalized). A content difference → a :class:`UnitDriftFinding`.
``openclaw-gateway.service`` is deployed but OpenClaw-managed (no repo canonical)
and is excluded. **Deferred to a follow-up:** a declared unit registry and
missing-deployment detection (a repo unit that was never deployed).

The split mirrors :mod:`scripts.trust.cron_drift_detector`: a pure, I/O-free
:func:`detect_unit_drift` diff plus an :func:`enumerate_unit_pairs` collector that
performs the filesystem reads. Coverage is reported explicitly (:class:`UnitCoverage`)
so nothing is silently skipped.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

#: Repo dirs holding canonical systemd unit sources, in precedence order. Felix
#: units are authored across four trees; the detector globs all of them so a unit
#: is matched to its canonical regardless of which subsystem owns it.
REPO_UNIT_SOURCE_DIRS = (
    "scripts/office2",
    "scripts/openclaw/deploy",
    "scripts/sync/systemd",
    "scripts/deploy/felix-deployer",
)

#: The deployed systemd-user unit directory (claude user on office2).
DEPLOYED_UNIT_DIR = Path.home() / ".config" / "systemd" / "user"

#: Deployed units excluded from the diff by design (documented reason). The repo
#: copy under ``scripts/openclaw/`` is not the deployed source — OpenClaw manages
#: this unit itself and is not under a globbed source dir — so there is nothing to
#: diff the deployed unit against.
EXCLUDED_DEPLOYED_UNITS = {
    "openclaw-gateway.service": "OpenClaw-managed; repo copy under scripts/openclaw/ is not the deployed source",
}

_UNIT_SUFFIXES = (".service", ".timer")


class UnitEnumerationError(Exception):
    """Raised when the deployed-unit dir or repo source tree cannot be read, or a
    unit basename collides across source dirs (an ambiguous canonical)."""


@dataclass
class UnitDriftFinding:
    """A single deployed-vs-repo unit drift finding.

    ``kind`` is ``"content_drift"`` in v1 (the #816 class). ``name`` is the unit
    basename (e.g. ``felix-trust-scan.service``); ``repo_source`` is its
    repo-relative canonical path.
    """

    kind: str
    name: str
    repo_source: str
    detail: str = ""


@dataclass
class UnitCoverage:
    """Transparent coverage record — no silent gaps (#817).

    ``compared``: deployed units diffed against a repo canonical.
    ``excluded``: deployed units in :data:`EXCLUDED_DEPLOYED_UNITS` (documented).
    ``deployed_no_repo_source``: deployed units with no repo canonical and NOT
    excluded — an unmanaged unit whose source is not in the repo. ``repo_only``:
    repo units not currently deployed. Both are **reported in the tick summary
    only** (visibility, no silent gaps); alerting on them is a deferred v1
    limitation — only ``content_drift`` on a compared unit emits an alert.
    """

    compared: list[str] = field(default_factory=list)
    excluded: list[str] = field(default_factory=list)
    deployed_no_repo_source: list[str] = field(default_factory=list)
    repo_only: list[str] = field(default_factory=list)


def _normalize(text: str) -> str:
    """Reduce a unit file to its **functional** content for comparison: drop
    full-line comments and blank lines, strip trailing whitespace, and collapse to
    a single trailing newline.

    The canary targets the #816 class — a stale ``ExecStart`` / ``Environment`` /
    ``PYTHONPATH`` (a *functional* directive). The repo unit files carry large,
    frequently-edited operator/rationale comment blocks; a comment-only repo edit
    against a not-yet-redeployed unit is NOT functional drift, so normalizing
    comments out avoids alert-fatigue noise that would bury a real #816. This is
    safe: a systemd unit's behaviour is entirely its ``Key=Value`` directives, and
    a directive line never begins with ``#`` or ``;`` — so stripping comment lines
    can never mask a real directive change (no false-clean)."""
    kept: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped[0] in "#;":  # blank or a full-line comment
            continue
        kept.append(line.rstrip())
    return "\n".join(kept).rstrip("\n") + "\n"


def build_repo_index(repo_root: Path) -> dict[str, Path]:
    """Map unit-basename → repo canonical path, globbing the known source dirs in
    precedence order. A genuine basename collision across dirs is an ambiguous
    canonical and is surfaced via :class:`UnitEnumerationError` rather than
    silently resolved to one arbitrary source."""
    index: dict[str, Path] = {}
    collisions: dict[str, list[str]] = {}
    for rel in REPO_UNIT_SOURCE_DIRS:
        directory = repo_root / rel
        if not directory.is_dir():
            continue
        for suffix in _UNIT_SUFFIXES:
            for path in sorted(directory.glob(f"*{suffix}")):
                base = path.name
                if base in index:
                    collisions.setdefault(base, [str(index[base].relative_to(repo_root))]).append(
                        str(path.relative_to(repo_root))
                    )
                    continue
                index[base] = path
    if collisions:
        detail = "; ".join(f"{b}={paths}" for b, paths in sorted(collisions.items()))
        raise UnitEnumerationError(f"duplicate unit basenames across source dirs: {detail}")
    return index


def enumerate_deployed(deployed_dir: Path) -> dict[str, Path]:
    """Map unit-basename → deployed path for every ``*.service`` / ``*.timer`` in
    the deployed-unit dir."""
    if not deployed_dir.is_dir():
        raise UnitEnumerationError(f"deployed unit dir not found: {deployed_dir}")
    out: dict[str, Path] = {}
    for suffix in _UNIT_SUFFIXES:
        for path in sorted(deployed_dir.glob(f"*{suffix}")):
            out[path.name] = path
    return out


def enumerate_unit_pairs(
    repo_root: Path, deployed_dir: Path | None = None
) -> tuple[list[tuple[str, str, str, str]], UnitCoverage]:
    """Collect ``(unit, repo_source_rel, repo_content, deployed_content)`` tuples
    for comparable units plus a :class:`UnitCoverage` record. This is the I/O
    boundary; the pure diff is :func:`detect_unit_drift`."""
    deployed_dir = deployed_dir if deployed_dir is not None else DEPLOYED_UNIT_DIR
    repo_index = build_repo_index(repo_root)
    deployed_index = enumerate_deployed(deployed_dir)

    pairs: list[tuple[str, str, str, str]] = []
    coverage = UnitCoverage()
    for unit, deployed_path in sorted(deployed_index.items()):
        if unit in EXCLUDED_DEPLOYED_UNITS:
            coverage.excluded.append(unit)
            continue
        repo_path = repo_index.get(unit)
        if repo_path is None:
            coverage.deployed_no_repo_source.append(unit)
            continue
        pairs.append(
            (
                unit,
                str(repo_path.relative_to(repo_root)),
                repo_path.read_text(encoding="utf-8"),
                deployed_path.read_text(encoding="utf-8"),
            )
        )
        coverage.compared.append(unit)
    coverage.repo_only = sorted(u for u in repo_index if u not in deployed_index)
    return pairs, coverage


def detect_unit_drift(pairs: list[tuple[str, str, str, str]]) -> list[UnitDriftFinding]:
    """Pure, I/O-free diff: for each ``(unit, repo_source, repo_content,
    deployed_content)``, emit a ``content_drift`` finding when the normalized
    contents differ. Findings are sorted ``(kind, name)`` for stable output."""
    findings: list[UnitDriftFinding] = []
    for unit, repo_source, repo_content, deployed_content in pairs:
        if _normalize(repo_content) != _normalize(deployed_content):
            findings.append(
                UnitDriftFinding(
                    kind="content_drift",
                    name=unit,
                    repo_source=repo_source,
                    detail="deployed unit content differs from repo canonical (whitespace-normalized)",
                )
            )
    return sorted(findings, key=lambda f: (f.kind, f.name))
