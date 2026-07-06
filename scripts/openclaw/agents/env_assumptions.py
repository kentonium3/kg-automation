"""Env-assumption checker for OpenClaw agent prompts (kentonium3/kg-automation#662,
corrects #658).

Detects helper invocations in agent prompts that assume an unstated runtime
environment (cwd / an inherited ``PYTHONPATH`` / a hardcoded absolute checkout path)
or write to a HOME-relative path, and distinguishes them from the canonical,
self-contained form.

Canonical (compliant) form — the invocation ``cd``s into the exact OpenClaw checkout
first, so it depends on neither the deployed cwd nor an inherited env var::

    cd /home/claude/kg-automation && python3 -m scripts.<pkg>.<mod> [absolute args]
    cd /home/claude/kg-automation && python3 scripts/<path>.py [absolute args]

NOTE: this checker validates the invocation *shape*, not whether the target script
is runnable by path. The file-path form is correct ONLY for a self-contained script;
any helper that does ``import scripts.…`` must use the ``-m scripts.<pkg>.<mod>`` form
(running by path does not put the repo root on ``sys.path``). Prefer ``-m`` for every
repo helper. (Standing rule; strengthening the checker to resolve the target's imports
is a tracked follow-up.)

Rationale: OpenClaw's ``exec`` tool runs commands in a sanitized subshell that
STRIPS ``PYTHONPATH``, so the old #658 ``cd "${PYTHONPATH:?…}"`` anchor exits 127 on
every cron run — the exact checkout-``cd`` is the only form that works (research D1).

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

#: The one-and-only OpenClaw checkout path on office2. The compliant anchor is an
#: EXACT match of this literal — a ``cd /home/kgale/repos/kg-automation`` or a
#: ``cd /tmp/kg-automation`` must NOT satisfy the anchor (Codex MED-4).
CANONICAL_CHECKOUT = "/home/claude/kg-automation"

# --- Model --------------------------------------------------------------------


class ViolationKind(enum.Enum):
    """The classes of runtime-environment assumption this checker detects."""

    BARE_M_SCRIPTS = "bare_m_scripts"
    RELATIVE_SCRIPT = "relative_script"
    PYTHONPATH_ANCHOR = "pythonpath_anchor"
    HARDCODED_ABS_PATH = "hardcoded_abs_path"
    HOME_RELATIVE_WRITE = "home_relative_write"


#: Per-kind remediation guidance surfaced in each Finding (NFR-004). Every kind now
#: steers to the self-contained checkout-``cd`` form (#662, corrects #658).
_REMEDIATION = {
    ViolationKind.BARE_M_SCRIPTS: (
        "anchor with cd /home/claude/kg-automation && python3 -m scripts...."
    ),
    ViolationKind.RELATIVE_SCRIPT: (
        "anchor with cd /home/claude/kg-automation && python3 scripts/....py"
    ),
    ViolationKind.PYTHONPATH_ANCHOR: (
        "${PYTHONPATH:?...} fails under OpenClaw exec — use "
        "cd /home/claude/kg-automation && python3 -m scripts...."
    ),
    ViolationKind.HARDCODED_ABS_PATH: (
        "use cd /home/claude/kg-automation && python3 scripts/....py"
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

# A relative-script reference: `python[3] scripts/<path>.py` OR a bare imperative
# `scripts/<path>.py` (e.g. prose "invoke `scripts/openclaw/.../felix-file-issue.py`").
# The lookbehind rejects an absolute-path `/…/scripts/x.py` (leading `/`) and the
# `-m scripts.<mod>` dotted form (`scripts.` not `scripts/`) — those are handled by
# _ABS_PATH_RE and _M_SCRIPTS_RE respectively.
_REL_SCRIPT_RE = re.compile(r"(?<![\w/.])scripts/(?P<path>[^\s`\"']+\.py)")

# A literal absolute-path script invocation: `python[3] /abs/.../scripts/x.py`,
# including a quoted variant `python3 "/abs/.../scripts/x.py"` (the opening quote is
# consumed by `["']?`). The compliant relative `python3 scripts/x.py` form has no
# leading `/` after the interpreter, so it is not matched here.
_ABS_PATH_RE = re.compile(r"python3?\s+[\"']?(?P<path>/[^\s`\"']*/scripts/[^\s`\"']+\.py)")

# The EXACT checkout-`cd` that makes a relative invocation compliant. Built from
# CANONICAL_CHECKOUT and terminated by a boundary lookahead so a longer path such as
# `/home/claude/kg-automation-fork` (or `/home/kgale/repos/kg-automation`) does NOT
# satisfy it — the anchor is an exact-match, not "contains kg-automation" (Codex MED-4).
_CHECKOUT_CD_RE = re.compile(
    r"cd\s+[\"']?" + re.escape(CANONICAL_CHECKOUT) + r"(?=[\"'\s;&]|$)"
)

# The `${PYTHONPATH:?…}` anchor #658 taught. It now FAILS under OpenClaw exec
# (which strips PYTHONPATH), so its presence is itself a violation.
_PYTHONPATH_RE = re.compile(r"\$\{PYTHONPATH:\?")

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


def _governing_anchor(prefix: str) -> str | None:
    """Classify the anchor (if any) that precedes an invocation.

    Returns ``"checkout"`` if an exact checkout-``cd`` governs the invocation
    (compliant), ``"pythonpath"`` if a ``${PYTHONPATH:?…}`` cd governs it (already
    reported once as PYTHONPATH_ANCHOR — don't double-report the invocation), or
    ``None`` if the invocation is genuinely unanchored.
    """
    if _CHECKOUT_CD_RE.search(prefix):
        return "checkout"
    if _PYTHONPATH_RE.search(prefix):
        return "pythonpath"
    return None


def _classify(start: int, text: str, path: str) -> list[Finding]:
    """Classify one logical command; return its findings (may be empty)."""
    findings: list[Finding] = []
    snippet = text.strip()

    # PYTHONPATH anchor — now a violation: it exits 127 under OpenClaw exec's
    # PYTHONPATH sanitization (research D1). Reported once per logical line.
    if _PYTHONPATH_RE.search(text):
        findings.append(
            Finding(path, start, ViolationKind.PYTHONPATH_ANCHOR, snippet,
                    _REMEDIATION[ViolationKind.PYTHONPATH_ANCHOR])
        )

    # Bare -m scripts. — flag when the invocation is NOT preceded by the EXACT
    # checkout-`cd` anchor in the same logical line. The anchor must appear BEFORE
    # the invocation (a `cd /home/claude/kg-automation &&` prefix), so a
    # `python3 -m scripts.bad` that precedes the cd is still flagged (Codex MED-1).
    # An invocation governed by a `${PYTHONPATH:?}` cd is suppressed here — that cd
    # is already reported above as PYTHONPATH_ANCHOR.
    for m in _M_SCRIPTS_RE.finditer(text):
        if "<" in m.group("mod"):  # placeholder like scripts.inbox.<helper>
            continue
        if _governing_anchor(text[: m.start()]) is None:
            findings.append(
                Finding(path, start, ViolationKind.BARE_M_SCRIPTS, snippet,
                        _REMEDIATION[ViolationKind.BARE_M_SCRIPTS])
            )
            break

    # Relative-script invocations (`python3 scripts/x.py`) and bare imperative
    # `scripts/x.py` references — same anchor rule as the -m form (Codex HIGH-2).
    for m in _REL_SCRIPT_RE.finditer(text):
        if "<" in m.group("path"):  # placeholder like scripts/<pkg>/x.py
            continue
        if _governing_anchor(text[: m.start()]) is None:
            findings.append(
                Finding(path, start, ViolationKind.RELATIVE_SCRIPT, snippet,
                        _REMEDIATION[ViolationKind.RELATIVE_SCRIPT])
            )
            break

    # Hardcoded absolute-path script invocations (python or python3) — always a
    # violation, checkout-`cd` or not: steer to the relative `python3 scripts/x.py`.
    for m in _ABS_PATH_RE.finditer(text):
        if _HARDCODED_CHECKOUT_RE.search(m.group("path")):
            findings.append(
                Finding(path, start, ViolationKind.HARDCODED_ABS_PATH, snippet,
                        _REMEDIATION[ViolationKind.HARDCODED_ABS_PATH])
            )
            break

    # HOME-relative writes (UNCHANGED, #659).
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
