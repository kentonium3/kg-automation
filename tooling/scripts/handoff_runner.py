#!/usr/bin/env python3
"""
Handoff Runner
- Reads handoff request JSON files from ai-agents/shared/handoffs/*-request.json
- Applies file edits to the current branch (never main)
- Writes a matching *-github-runner-response.json
- Honors a simple denylist (e.g., blocks .github/workflows/** by default)
"""

from __future__ import annotations
import json
import os
from pathlib import Path
from typing import List, Dict, Any
import subprocess
import sys
import datetime

ROOT = Path(__file__).resolve().parents[2]   # repo root
HANDOFF_DIR = ROOT / "ai-agents" / "shared" / "handoffs"

# ---- runner policy ----------------------------------------------------------

DENYLIST_PREFIXES = [
    ".github/workflows/",   # don't let the runner edit workflows
]

def is_denied(path: Path, allow_workflow_edit: bool) -> bool:
    p = path.as_posix()
    if not allow_workflow_edit:
        for pref in DENYLIST_PREFIXES:
            if p.startswith(pref):
                return True
    return False

def current_branch() -> str:
    try:
        out = subprocess.check_output(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=ROOT)
        return out.decode().strip()
    except Exception:
        return ""

def git_add_commit_if_changed(message: str) -> bool:
    # Return True if a commit was created
    changed = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True)
    if changed.returncode != 0:
        return False
    if not changed.stdout.strip():
        return False
    subprocess.check_call(["git", "config", "user.name", "handoff-runner[bot]"], cwd=ROOT)
    subprocess.check_call(["git", "config", "user.email", "handoff-runner@local"], cwd=ROOT)
    subprocess.check_call(["git", "add", "-A"], cwd=ROOT)
    subprocess.check_call(["git", "commit", "-m", message], cwd=ROOT)
    return True

# ---- core -------------------------------------------------------------------

def find_requests() -> List[Path]:
    if not HANDOFF_DIR.exists():
        return []
    return sorted(HANDOFF_DIR.glob("*-request.json"))

def load_json(p: Path) -> Dict[str, Any]:
    with p.open("r", encoding="utf-8") as f:
        return json.load(f)

def write_json(p: Path, data: Dict[str, Any]) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def apply_file_edits(edits: List[Dict[str, Any]], allow_workflow_edit: bool) -> Dict[str, Any]:
    written = []
    denied = []
    for e in edits:
        rel = Path(e["path"]).as_posix().lstrip("/")           # normalize
        tgt = ROOT / rel
        if is_denied(Path(rel), allow_workflow_edit):
            denied.append(rel)
            continue
        tgt.parent.mkdir(parents=True, exist_ok=True)
        content = e.get("content", "")
        # If caller provided "mode": "append", support it lightly
        mode = e.get("mode", "write")
        if mode == "append" and tgt.exists():
            existing = tgt.read_text(encoding="utf-8")
            tgt.write_text(existing + ("\n" if not existing.endswith("\n") else "") + content, encoding="utf-8")
        else:
            tgt.write_text(content, encoding="utf-8")
        written.append(rel)
    return {"written": written, "denied": denied}

def process_request(req_path: Path) -> Path:
    req = load_json(req_path)

    # Inputs
    inputs = req.get("inputs", {})
    edits = inputs.get("file_edits", [])
    allow_workflow_edit = bool(inputs.get("allow_workflow_edit", False))

    # Safety: never on main
    branch = current_branch()
    if branch in ("main", "origin/main"):
        raise SystemExit("Refusing to run on 'main' — create a feature branch.")

    result = apply_file_edits(edits, allow_workflow_edit=allow_workflow_edit)

    # Compose response JSON
    ts = datetime.datetime.utcnow().strftime("%Y%m%d-%H%M")
    base = req_path.stem.replace("-request", "")
    resp_name = f"{ts}-{base}-github-runner-response.json"
    resp_path = HANDOFF_DIR / resp_name
    response = {
        "type": "handoff.response",
        "from_agent": "handoff-runner",
        "request_file": str(req_path.relative_to(ROOT)),
        "branch": branch,
        "timestamp_utc": ts,
        "result": result,
        "notes": "Committed if any files changed; see Git history for this branch."
    }
    write_json(resp_path, response)

    # Stage + commit if anything changed (files or response)
    # We ensure the response is committed too.
    git_add_commit_if_changed("handoff: automated response by handoff-runner")

    return resp_path

def main() -> None:
    reqs = find_requests()
    if not reqs:
        print("[handoff-runner] No handoff requests found.")
        return

    processed = 0
    for rp in reqs:
        try:
            print(f"[handoff-runner] Processing {rp.relative_to(ROOT)}")
            out = process_request(rp)
            print(f"[handoff-runner] Wrote response: {out.relative_to(ROOT)}")
            processed += 1
        except Exception as e:
            # Always try to surface a response even on error
            ts = datetime.datetime.utcnow().strftime("%Y%m%d-%H%M")
            base = rp.stem.replace("-request", "")
            resp_name = f"{ts}-{base}-github-runner-response.json"
            resp_path = HANDOFF_DIR / resp_name
            write_json(resp_path, {
                "type": "handoff.response",
                "from_agent": "handoff-runner",
                "request_file": str(rp.relative_to(ROOT)),
                "error": str(e),
            })
            git_add_commit_if_changed("handoff: automated response by handoff-runner (error)")
            print(f"[handoff-runner] ERROR on {rp.name}: {e}", file=sys.stderr)

    if processed == 0:
        print("[handoff-runner] No new handoff requests to process.")

if __name__ == "__main__":
    main()
