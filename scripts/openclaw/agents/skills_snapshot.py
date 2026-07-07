#!/usr/bin/env python3
"""Snapshot which OpenClaw skills are visible to each agent — a deterministic
pre/post oracle for Foundation-0 skill-scoping (see docs/design/felix-openclaw-boundary.md).

For every agent it runs `openclaw skills check --agent <id>` and extracts:
  - the set of skills "Ready and visible to model" (the instruction packs the
    model can see — this is what per-agent `skills` scoping controls), and
  - the summary counts (visible / excluded-by-agent-allowlist / disabled).

Emit a stable, diffable report so a scoping change can be verified as a clean
before/after diff. The boundary-critical check is surfaced explicitly: which
agents can see `gog` (must be calendar-only after scoping).

Runs on office2 (needs the `openclaw` CLI on PATH). Self-contained — no
scripts.* imports, so it is safe to run by script path or `-m`.

Usage:
  python3 scripts/openclaw/agents/skills_snapshot.py            # human report, all agents
  python3 scripts/openclaw/agents/skills_snapshot.py --json     # machine-readable
  python3 scripts/openclaw/agents/skills_snapshot.py main calendar   # specific agents
  python3 scripts/openclaw/agents/skills_snapshot.py --watch gog     # highlight a skill (default: gog)

Exit code: 0 on success; 2 if any agent could not be queried.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys

DEFAULT_CONFIG = os.path.expanduser("~/.openclaw/openclaw.json")
SKILL_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]+$")
COUNT_RE = re.compile(r"^[^A-Za-z]*([A-Za-z][A-Za-z ]+?):\s*(\d+)\s*$")
SECTION_HEADER = "Ready and visible to model:"


def discover_agents(config_path: str) -> list[str]:
    """Authoritative agent list from the live openclaw.json (agents.list[].id)."""
    with open(config_path) as fh:
        cfg = json.load(fh)
    ids = [a["id"] for a in cfg.get("agents", {}).get("list", []) if a.get("id")]
    if not ids:
        raise ValueError(f"no agents found in {config_path}")
    return ids


def query_agent(agent_id: str) -> dict:
    """Run `openclaw skills check --agent <id>` and parse visible skills + counts."""
    proc = subprocess.run(
        ["openclaw", "skills", "check", "--agent", agent_id],
        capture_output=True,
        text=True,
    )
    out = proc.stdout + "\n" + proc.stderr
    counts: dict[str, int] = {}
    visible: list[str] = []
    in_section = False
    for raw in out.splitlines():
        line = raw.rstrip()
        # summary counts (e.g. "✓ Visible to model: 26", "Excluded by agent allowlist: 0")
        m = COUNT_RE.match(line.strip())
        if m and not in_section:
            counts[m.group(1).strip().lower()] = int(m.group(2))
            continue
        if line.strip() == SECTION_HEADER:
            in_section = True
            continue
        if in_section:
            stripped = line.strip()
            if not stripped or stripped.startswith("Tip:"):
                in_section = False
                continue
            # last whitespace token is the skill name (strips any leading emoji)
            token = stripped.split()[-1]
            if SKILL_NAME_RE.match(token):
                visible.append(token)
    return {
        "agent": agent_id,
        "ok": bool(visible) or proc.returncode == 0,
        "visible_count": counts.get("visible to model"),
        "excluded_by_agent_allowlist": counts.get("excluded by agent allowlist"),
        "disabled": counts.get("disabled"),
        "skills": sorted(set(visible)),
    }


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("agents", nargs="*", help="agent ids (default: discover from openclaw.json)")
    ap.add_argument("--config", default=DEFAULT_CONFIG, help="path to openclaw.json for agent discovery")
    ap.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    ap.add_argument("--watch", default="gog", help="skill to highlight in the boundary matrix (default: gog)")
    args = ap.parse_args(argv)

    agents = args.agents or discover_agents(args.config)
    results = [query_agent(a) for a in agents]
    any_fail = any(not r["ok"] for r in results)

    if args.json:
        json.dump({"agents": results, "watch": args.watch}, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
        return 2 if any_fail else 0

    watch = args.watch
    print(f"# OpenClaw skills-visibility snapshot  (watch skill: {watch!r})\n")
    for r in results:
        flag = "" if r["ok"] else "  [QUERY FAILED]"
        print(f"[{r['agent']}] visible={r['visible_count']} "
              f"excluded_by_agent_allowlist={r['excluded_by_agent_allowlist']}{flag}")
        for s in r["skills"]:
            mark = "  <-- watch" if s == watch else ""
            print(f"    {s}{mark}")
        print()

    print(f"## {watch}-visibility matrix (boundary-critical)")
    for r in results:
        seen = watch in r["skills"]
        print(f"  {'SEES ' + watch if seen else 'no ' + watch:<10}  {r['agent']}")
    return 2 if any_fail else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
