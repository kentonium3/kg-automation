"""Validate Felix OpenClaw agent workspaces against the shared-invariant contract.

Deterministic checker for the OpenClaw Workspace Authoring Standard
(``docs/design/openclaw-workspace-authoring-standard.md``, #587). For each active
agent workspace it verifies the two shared invariants that must be present per
workspace (they are intentionally per-agent, not inherited — see #553):

* **Invariant A — Privacy boundary**: the enforceable ``04-Growth/_private/``
  never-touch rule is present in the workspace's enforceable home (``AGENTS.md`` or
  ``TOOLS.md``). A SOUL-only stance does not satisfy it.
* **Invariant B — Output Discipline**: an agent that emits user-facing WhatsApp
  carries the Output Discipline block in ``AGENTS.md``; an agent that does not
  carries the explicit ``no user-facing WhatsApp`` annotation. Presence-or-annotation.

This is a repo/CI artifact — read-only, no deploy, no side effects.

Run:

    python3 -m scripts.openclaw.agents.validate_workspace --json

Exit code 0 when every active workspace passes, 1 when any active workspace fails,
2 on a usage/IO error.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

# --- Contract constants (source of truth: the authoring standard) --------------

#: Substring identifying the enforceable privacy boundary rule.
PRIVACY_TOKEN = "04-Growth/_private"

#: Case-insensitive marker for the Output Discipline block heading.
OUTPUT_DISCIPLINE_TOKEN = "output discipline"

#: Case-insensitive annotation an agent uses to declare it emits no user-facing WhatsApp.
NO_WHATSAPP_ANNOTATION = "no user-facing whatsapp"

#: Files that carry the enforceable privacy rule (Invariant A owner set).
PRIVACY_OWNER_FILES = ("AGENTS.md", "TOOLS.md")

#: Workspaces retained on disk but not active — excluded from validation.
#: felix-doc-auditor was refactored to a scripts-first driver (#343); no live agent.
#: Disposition (#658): with no live agent prompt it carries no deployed invocation to
#: convert — excluded here by design, not left unaudited.
SUSPENDED_WORKSPACES = frozenset({"felix-doc-auditor"})

#: Directories under the agents root that are not agent workspaces.
NON_WORKSPACE_DIRS = frozenset({"tests", "__pycache__"})


@dataclass
class CheckResult:
    """Outcome of one invariant check on one workspace."""

    name: str
    ok: bool
    detail: str


@dataclass
class WorkspaceReport:
    """Aggregate result for a single workspace."""

    workspace: str
    ok: bool
    checks: list[CheckResult] = field(default_factory=list)


def _read(path: Path) -> str:
    """Return file text, or empty string if the file is absent."""
    try:
        return path.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError):
        return ""


def check_privacy_boundary(workspace_dir: Path) -> CheckResult:
    """Invariant A: enforceable privacy rule present in an owner file."""
    hits = [f for f in PRIVACY_OWNER_FILES if PRIVACY_TOKEN in _read(workspace_dir / f)]
    if hits:
        return CheckResult("privacy_boundary", True, f"present in {', '.join(hits)}")
    # Distinguish a SOUL-only stance (authoring mistake) from total absence.
    if PRIVACY_TOKEN in _read(workspace_dir / "SOUL.md"):
        return CheckResult(
            "privacy_boundary",
            False,
            f"only in SOUL.md — enforceable rule must live in {' or '.join(PRIVACY_OWNER_FILES)}",
        )
    return CheckResult(
        "privacy_boundary",
        False,
        f"missing — no '{PRIVACY_TOKEN}' rule in {' or '.join(PRIVACY_OWNER_FILES)}",
    )


def check_output_discipline(workspace_dir: Path) -> CheckResult:
    """Invariant B: Output Discipline block present, or no-WhatsApp annotation present."""
    agents_text = _read(workspace_dir / "AGENTS.md").lower()
    if OUTPUT_DISCIPLINE_TOKEN in agents_text:
        return CheckResult("output_discipline", True, "Output Discipline block present in AGENTS.md")
    # Presence-or-annotation: an explicit no-WhatsApp declaration satisfies the invariant.
    for md in sorted(workspace_dir.glob("*.md")):
        if NO_WHATSAPP_ANNOTATION in _read(md).lower():
            return CheckResult("output_discipline", True, f"'{NO_WHATSAPP_ANNOTATION}' annotation in {md.name}")
    return CheckResult(
        "output_discipline",
        False,
        f"missing — no Output Discipline block in AGENTS.md and no '{NO_WHATSAPP_ANNOTATION}' annotation",
    )


def check_runtime_env_assumptions(workspace_dir: Path) -> CheckResult:
    """Invariant C (#658): no unstated runtime-env assumptions in the workspace prompts.

    Reuses the shared env-assumption checker so #167-authored workspaces inherit the
    guardrail at validation time. Imported lazily to avoid an import cycle
    (``env_assumptions`` imports the exclusion sets from this module).
    """
    from scripts.openclaw.agents.env_assumptions import scan_file  # noqa: PLC0415 (cycle-break)

    findings = [
        f
        for name in ("AGENTS.md", "AGENTS.md.tmpl")
        for f in scan_file(workspace_dir / name)
    ]
    if not findings:
        return CheckResult("runtime_env_assumptions", True, "ok")
    detail = "; ".join(f"{Path(f.path).name}:{f.line} {f.kind.value}" for f in findings)
    return CheckResult("runtime_env_assumptions", False, detail)


def validate_workspace(workspace_dir: Path) -> WorkspaceReport:
    """Run all invariant checks against one workspace directory."""
    checks = [
        check_privacy_boundary(workspace_dir),
        check_output_discipline(workspace_dir),
        check_runtime_env_assumptions(workspace_dir),
    ]
    return WorkspaceReport(
        workspace=workspace_dir.name,
        ok=all(c.ok for c in checks),
        checks=checks,
    )


def discover_workspaces(root: Path) -> list[Path]:
    """Return active workspace dirs under ``root`` (contain AGENTS.md, not suspended)."""
    return sorted(
        d
        for d in root.iterdir()
        if d.is_dir()
        and d.name not in NON_WORKSPACE_DIRS
        and d.name not in SUSPENDED_WORKSPACES
        and (d / "AGENTS.md").is_file()
    )


def validate_all(root: Path) -> list[WorkspaceReport]:
    """Validate every active workspace under ``root``."""
    return [validate_workspace(d) for d in discover_workspaces(root)]


def _default_root() -> Path:
    """The agents directory this module lives in."""
    return Path(__file__).resolve().parent


def _render_human(reports: list[WorkspaceReport]) -> str:
    lines: list[str] = []
    for r in reports:
        lines.append(f"{'PASS' if r.ok else 'FAIL'}  {r.workspace}")
        for c in r.checks:
            lines.append(f"    {'✓' if c.ok else '✗'} {c.name}: {c.detail}")
    passed = sum(1 for r in reports if r.ok)
    lines.append(f"\n{passed}/{len(reports)} workspaces pass")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="Agents directory to scan (default: this module's directory).",
    )
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    args = parser.parse_args(argv)

    root = args.root or _default_root()
    if not root.is_dir():
        print(f"error: root is not a directory: {root}", file=sys.stderr)
        return 2

    reports = validate_all(root)
    all_ok = all(r.ok for r in reports)

    if args.json:
        payload = {
            "ok": all_ok,
            "workspace_count": len(reports),
            "pass_count": sum(1 for r in reports if r.ok),
            "workspaces": [asdict(r) for r in reports],
        }
        print(json.dumps(payload, indent=2))
    else:
        print(_render_human(reports))

    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
