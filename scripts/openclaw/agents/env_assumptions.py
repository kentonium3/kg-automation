"""Env-assumption checker for OpenClaw agent prompts (kentonium3/kg-automation#658).

Detects invocations in agent prompts that assume an unstated runtime environment
(cwd / PYTHONPATH / hardcoded checkout path) or write to a HOME-relative path, and
distinguishes them from the canonical, gateway-independent form.

Canonical (compliant) form — reuse the gateway-declared PYTHONPATH as the repo root,
fail-loud, no hardcoded checkout::

    cd "${PYTHONPATH:?<msg>}" && python3 -m scripts.<pkg>.<mod> [absolute args]
    cd "${PYTHONPATH:?<msg>}" && python3 scripts/<path>.py [absolute args]
    python  "${PYTHONPATH:?<msg>}/scripts/<path>.py" [absolute args]

Shared by the Test-CI fleet guard (tests/test_env_assumptions_guard.py) and the
workspace validator (validate_workspace.check_runtime_env_assumptions). Pure and
deterministic: no network, no subprocess, no environment reads, no clock. Python
3.11-compatible, standard library only.
"""

from __future__ import annotations

import argparse
import enum
import re
import sys
from dataclasses import dataclass
from pathlib import Path

# Reuse the validator's exclusion sets so the two consumers agree on scope.
from scripts.openclaw.agents.validate_workspace import (
    NON_WORKSPACE_DIRS,
    SUSPENDED_WORKSPACES,
)

# --- Model --------------------------------------------------------------------


class ViolationKind(enum.Enum):
    """The classes of runtime-environment assumption this checker detects."""

    BARE_M_SCRIPTS = "bare_m_scripts"
    HARDCODED_CD = "hardcoded_cd"
    HARDCODED_ABS_PATH = "hardcoded_abs_path"
    HOME_RELATIVE_WRITE = "home_relative_write"


#: Per-kind remediation guidance surfaced in each Finding (NFR-004).
_REMEDIATION = {
    ViolationKind.BARE_M_SCRIPTS: (
        'anchor with cd "${PYTHONPATH:?...}" && python3 -m scripts....'
    ),
    ViolationKind.HARDCODED_CD: (
        'replace the hardcoded checkout with cd "${PYTHONPATH:?...}"'
    ),
    ViolationKind.HARDCODED_ABS_PATH: (
        'use cd "${PYTHONPATH:?...}" && python3 scripts/....py (or "${PYTHONPATH:?...}/scripts/....py")'
    ),
    ViolationKind.HOME_RELATIVE_WRITE: (
        "write to a canonical absolute path, not a ~/$HOME-relative one"
    ),
}


@dataclass(frozen=True)
class Finding:
    """One detected runtime-environment assumption in an agent prompt."""

    path: str
    line: int  # 1-based; the STARTING line of the logical command
    kind: ViolationKind
    snippet: str
    remediation: str


# --- Patterns -----------------------------------------------------------------

# A concrete `python[3] -m scripts.<module>` invocation (module token stops at
# whitespace, backtick, or quote). A `<placeholder>` in the module marks docs.
_M_SCRIPTS_RE = re.compile(r"python3?\s+-m\s+scripts\.(?P<mod>[^\s`\"']+)")

# A literal absolute-path script invocation: `python[3] /abs/.../scripts/x.py`.
# The compliant `python3 "${PYTHONPATH:?}/scripts/x.py"` form starts with a quote
# or `$`, never a bare `/`, so it is not matched here.
_ABS_PATH_RE = re.compile(r"python3?\s+(?P<path>/[^\s`\"']*/scripts/[^\s`\"']+\.py)")

# A `cd` into a hardcoded checkout (path literal containing kg-automation). The
# compliant `cd "${PYTHONPATH:?}"` starts with a quote/`$`, not `/`.
_HARDCODED_CD_RE = re.compile(r"cd\s+[\"']?(?P<path>/[^\s`\"']*kg-automation[^\s`\"']*)")

# The fail-loud PYTHONPATH anchor that makes an invocation compliant.
_PYTHONPATH_ANCHOR_RE = re.compile(r"\$\{PYTHONPATH:\?")

# A write (redirect or tee) to a ~/$HOME-relative destination — the stray-dir class.
# Reads of ~/.openclaw/... have no redirect and are never matched.
_HOME_WRITE_RE = re.compile(
    r"(?:>>?|\btee\b)\s+[\"']?(?P<dest>(?:~|\$HOME|\$\{HOME\})/[^\s`\"']*)"
)

# A waiver marker: `# env-guard: waive <KIND> — <reason>` on the same/previous line.
_WAIVER_RE = re.compile(r"#\s*env-guard:\s*waive\s+(?P<kind>[a-z_]+)", re.IGNORECASE)

# The hardcoded checkout literal(s) we treat as a checkout-path assumption.
_HARDCODED_CHECKOUT_RE = re.compile(r"/home/[^/\s]+/(?:repos/)?kg-automation")


# --- Recognizer ---------------------------------------------------------------


def _logical_lines(text: str) -> list[tuple[int, str]]:
    """Yield (start_line, joined_text) logical commands.

    Joins backslash-continued lines into one logical command (reporting the
    starting line), and drops HTML comment blocks (``<!-- ... -->``) so the
    ``<!-- helper at .../prescan.py -->`` documentation lines are never flagged.
    """
    raw = text.split("\n")
    out: list[tuple[int, str]] = []
    in_comment = False
    i = 0
    n = len(raw)
    while i < n:
        line = raw[i]
        start = i + 1  # 1-based

        # HTML comment handling (single- or multi-line).
        if in_comment:
            if "-->" in line:
                in_comment = False
            i += 1
            continue
        # Strip a self-contained comment; enter comment state on an unterminated one.
        if "<!--" in line:
            before, _, after = line.partition("<!--")
            if "-->" in after:
                line = before + after.split("-->", 1)[1]
            else:
                in_comment = True
                line = before

        # Join backslash continuations.
        buf = line
        while buf.rstrip().endswith("\\") and i + 1 < n:
            buf = buf.rstrip()[:-1] + " " + raw[i + 1]
            i += 1
        out.append((start, buf))
        i += 1
    return out


def _waived_kinds(logical: list[tuple[int, str]], idx: int) -> set[str]:
    """ViolationKind values waived for logical line ``idx`` (same or previous line)."""
    kinds: set[str] = set()
    for j in (idx - 1, idx):
        if 0 <= j < len(logical):
            m = _WAIVER_RE.search(logical[j][1])
            if m:
                kinds.add(m.group("kind").lower())
    return kinds


# --- Classification -----------------------------------------------------------


def _classify(start: int, text: str, path: str) -> list[Finding]:
    """Classify one logical command; return its findings (may be empty)."""
    findings: list[Finding] = []
    anchored = bool(_PYTHONPATH_ANCHOR_RE.search(text))
    snippet = text.strip()

    hardcoded_cd = _HARDCODED_CD_RE.search(text)
    if hardcoded_cd:
        findings.append(
            Finding(path, start, ViolationKind.HARDCODED_CD, snippet,
                    _REMEDIATION[ViolationKind.HARDCODED_CD])
        )

    # Bare -m scripts. — only when NOT anchored and NOT already governed by a
    # hardcoded cd on the same logical line (fixing the cd fixes the -m).
    if not hardcoded_cd:
        for m in _M_SCRIPTS_RE.finditer(text):
            if "<" in m.group("mod"):  # placeholder like scripts.inbox.<helper>
                continue
            if not anchored:
                findings.append(
                    Finding(path, start, ViolationKind.BARE_M_SCRIPTS, snippet,
                            _REMEDIATION[ViolationKind.BARE_M_SCRIPTS])
                )
                break

    # Hardcoded absolute-path script invocations (python or python3).
    for m in _ABS_PATH_RE.finditer(text):
        if _HARDCODED_CHECKOUT_RE.search(m.group("path")):
            findings.append(
                Finding(path, start, ViolationKind.HARDCODED_ABS_PATH, snippet,
                        _REMEDIATION[ViolationKind.HARDCODED_ABS_PATH])
            )
            break

    # HOME-relative writes.
    if _HOME_WRITE_RE.search(text):
        findings.append(
            Finding(path, start, ViolationKind.HOME_RELATIVE_WRITE, snippet,
                    _REMEDIATION[ViolationKind.HOME_RELATIVE_WRITE])
        )

    return findings


# --- Public API ---------------------------------------------------------------


def scan_text(text: str, path: str = "<memory>") -> list[Finding]:
    """Classify every invocation in ``text``; honor inline waiver markers."""
    logical = _logical_lines(text)
    findings: list[Finding] = []
    for idx, (start, line_text) in enumerate(logical):
        waived = _waived_kinds(logical, idx)
        for f in _classify(start, line_text, path):
            if f.kind.value not in waived:
                findings.append(f)
    return findings


def scan_file(path: Path) -> list[Finding]:
    """Read ``path`` (UTF-8) and scan its contents. Missing file → no findings."""
    try:
        text = path.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError):
        return []
    return scan_text(text, str(path))


def _prompt_files(workspace_dir: Path) -> list[Path]:
    """AGENTS.md and AGENTS.md.tmpl under a single workspace, if present."""
    return [
        p
        for name in ("AGENTS.md", "AGENTS.md.tmpl")
        for p in (workspace_dir / name,)
        if p.is_file()
    ]


def scan_agents_root(root: Path) -> list[Finding]:
    """Scan every active workspace's AGENTS.md/.tmpl under ``root``.

    Excludes the retired felix-doc-auditor workspace and non-workspace dirs,
    reusing validate_workspace's sets so scope stays in sync.
    """
    findings: list[Finding] = []
    for d in sorted(p for p in root.iterdir() if p.is_dir()):
        if d.name in NON_WORKSPACE_DIRS or d.name in SUSPENDED_WORKSPACES:
            continue
        for f in _prompt_files(d):
            findings.extend(scan_file(f))
    return findings


def _default_root() -> Path:
    """The agents directory this module lives in."""
    return Path(__file__).resolve().parent


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=None,
                        help="Agents directory to scan (default: this module's dir).")
    args = parser.parse_args(argv)
    root = args.root or _default_root()
    if not root.is_dir():
        print(f"error: root is not a directory: {root}", file=sys.stderr)
        return 2
    findings = scan_agents_root(root)
    for f in findings:
        print(f"{f.path}:{f.line} {f.kind.value} — {f.remediation}")
    if findings:
        print(f"\n{len(findings)} env-assumption finding(s)", file=sys.stderr)
        return 1
    print("ok: no env-assumption findings")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
