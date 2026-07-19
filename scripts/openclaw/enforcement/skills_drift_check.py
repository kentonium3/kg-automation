"""Independent OpenClaw skills drift check (#775, WP02).

An INDEPENDENT observer of repo↔office2 skill drift — deliberately NOT the
sync's (`deploy_agent_skills`) code path. Because the sync overwrites office2
every tick, a dry-run of the sync would be circular and could be masked by the
next remediating tick (research D-4 / Codex #1 HIGH-3). This standalone
comparator MD5-compares each repo `SKILL.md` against its deployed copy and
reports:

  * drift  — repo and deployed differ (or the deployed file is missing);
  * orphan — a deployed skill dir with no repo counterpart (a repo-removed
             skill whose deployed copy lingers; copy-only never prunes it —
             FR-014). Reported, never deleted.

``*.backup*`` sidecars are ignored on both sides (FR-010). Alert-only — this
check never remediates (NFR-003); the sync is the remediation path.

Wiring: registered as a **canary** probe via a ``self-check-command``
``health_check`` in ``service-inventory.json`` (authored in WP04) whose endpoint
runs this module. The canary turns a non-zero exit into a deduped alert; it
inherits the canary's cadence + dedup, so this module carries no scheduler.

Exit contract:
    0  — all repo skills match their deployed copy AND no orphans
    1  — one or more drift and/or orphan states detected
    2  — the repo skills dir or deployed base is unreadable (cannot evaluate)

Invocation (the `-m` form; the module has no scripts.* imports but stays
consistent with the sync's convention):
    python3 -m scripts.openclaw.enforcement.skills_drift_check [--json]
        [--repo-root PATH] [--deployed-base PATH]

Deterministic, stdlib-only, no LLM (NFR-006).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

SKILL_FILENAME = "SKILL.md"
BACKUP_MARKER = ".backup"

REPO_ROOT_DEFAULT = Path("/home/claude/kg-automation")
SKILLS_SOURCE_RELATIVE = Path("scripts/openclaw/skills")
DEPLOYED_BASE_DEFAULT = Path("/home/claude/.openclaw/skills")

STATE_MATCH = "match"
STATE_DRIFT = "drift"
STATE_ORPHAN = "orphan"

EXIT_CLEAN = 0
EXIT_DRIFT = 1
EXIT_UNREADABLE = 2


@dataclass(frozen=True)
class SkillDriftRow:
    skill: str
    state: str
    repo_md5: Optional[str]
    deployed_md5: Optional[str]


def _is_backup(name: str) -> bool:
    return BACKUP_MARKER in name


def _md5(path: Path) -> Optional[str]:
    """Hex MD5 of *path*, or None if it does not exist. Independent of the sync's
    compute_md5 (the whole point is a separate implementation)."""
    if not path.is_file():
        return None
    h = hashlib.md5()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _repo_skill_names(skills_root: Path) -> List[str]:
    return sorted(
        d.name
        for d in skills_root.iterdir()
        if d.is_dir() and (d / SKILL_FILENAME).is_file()
    )


def _deployed_skill_names(deployed_base: Path) -> List[str]:
    if not deployed_base.is_dir():
        return []
    names = []
    for d in deployed_base.iterdir():
        if not d.is_dir():
            continue
        # A deployed skill dir counts if it holds a real SKILL.md (ignore a dir
        # that only contains a *.backup* sidecar).
        if (d / SKILL_FILENAME).is_file() and not _is_backup(SKILL_FILENAME):
            names.append(d.name)
    return sorted(names)


def evaluate(
    repo_root: Path = REPO_ROOT_DEFAULT,
    deployed_base: Path = DEPLOYED_BASE_DEFAULT,
) -> List[SkillDriftRow]:
    """Return one row per repo skill (match|drift) plus one per orphan.

    Raises FileNotFoundError if the repo skills dir is unreadable (exit 2 upstream).
    """
    skills_root = repo_root / SKILLS_SOURCE_RELATIVE
    if not skills_root.is_dir():
        raise FileNotFoundError(f"repo skills dir not found: {skills_root}")

    rows: List[SkillDriftRow] = []
    repo_names = _repo_skill_names(skills_root)
    for skill in repo_names:
        repo_md5 = _md5(skills_root / skill / SKILL_FILENAME)
        deployed_md5 = _md5(deployed_base / skill / SKILL_FILENAME)
        state = STATE_MATCH if repo_md5 == deployed_md5 and deployed_md5 is not None else STATE_DRIFT
        rows.append(SkillDriftRow(skill, state, repo_md5, deployed_md5))

    repo_set = set(repo_names)
    for skill in _deployed_skill_names(deployed_base):
        if skill not in repo_set:
            rows.append(
                SkillDriftRow(
                    skill,
                    STATE_ORPHAN,
                    repo_md5=None,
                    deployed_md5=_md5(deployed_base / skill / SKILL_FILENAME),
                )
            )
    return rows


def parse_args(argv: List[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="skills_drift_check",
        description="Independent repo↔office2 OpenClaw skills drift + orphan check (alert-only).",
    )
    parser.add_argument("--json", action="store_true", help="Emit per-skill JSON rows.")
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT_DEFAULT)
    parser.add_argument("--deployed-base", type=Path, default=DEPLOYED_BASE_DEFAULT)
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    args = parse_args(argv)
    try:
        rows = evaluate(repo_root=args.repo_root, deployed_base=args.deployed_base)
    except FileNotFoundError as exc:
        sys.stderr.write(str(exc) + "\n")
        return EXIT_UNREADABLE

    problems = [r for r in rows if r.state != STATE_MATCH]

    if args.json:
        sys.stdout.write(
            json.dumps(
                [
                    {
                        "skill": r.skill,
                        "state": r.state,
                        "repo_md5": r.repo_md5,
                        "deployed_md5": r.deployed_md5,
                    }
                    for r in rows
                ]
            )
            + "\n"
        )
    else:
        if problems:
            for r in problems:
                sys.stdout.write(
                    f"{r.state.upper()} {r.skill} "
                    f"repo_md5={r.repo_md5 or 'absent'} "
                    f"deployed_md5={r.deployed_md5 or 'absent'}\n"
                )
        else:
            sys.stdout.write(f"OK {len(rows)} skills in sync, 0 orphans\n")

    return EXIT_DRIFT if problems else EXIT_CLEAN


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
