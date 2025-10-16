# tooling/scripts/handoff_runner.py
# Minimal, safe handoff runner:
# - Reads ai-agents/shared/handoffs/*-request.json on the current branch checkout
# - Applies file_edits with a denylist (blocks .github/workflows/** unless explicitly allowed)
# - Writes a ...-github-runner-response.json next to each request
# - Idempotent: only writes files when content changes

import json
import glob
import pathlib
from typing import List, Tuple, Dict, Any

REQ_GLOB = "ai-agents/shared/handoffs/*-request.json"
RESP_SUFFIX = "-github-runner-response.json"

# ---- Denylist (default block) ----
# Paths starting with any of these prefixes will be skipped unless the request sets:
#   inputs.allow_workflow_edit = true
DENY_PREFIXES = [
    ".github/workflows/",
]

def _ensure_parent(p: pathlib.Path) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)

def _respond_path(req_path: pathlib.Path) -> pathlib.Path:
    name = req_path.name
    if name.endswith("-request.json"):
        name = name[:-len("-request.json")]
    return req_path.with_name(f"{name}{RESP_SUFFIX}")

def _status(applied: List[str], skipped: List[Dict[str, str]], had_edits_key: bool) -> str:
    if not had_edits_key:
        return "planned"   # no inputs.file_edits provided
    if applied:
        return "completed" # wrote at least one file
    # had file_edits key but nothing changed or all skipped
    return "noop" if not skipped else "completed"

def _apply_file_edits(req: Dict[str, Any]) -> Tuple[List[str], List[Dict[str, str]], str]:
    """Apply file edits from a single request. Returns (applied_paths, skipped_info, notes)."""
    inputs = req.get("inputs") or {}
    edits = inputs.get("file_edits") or []
    allow_workflow_edit = bool(inputs.get("allow_workflow_edit", False))

    applied: List[str] = []
    skipped: List[Dict[str, str]] = []

    for e in edits:
        path = (e or {}).get("path")
        content = (e or {}).get("content", "")
        if not path:
            skipped.append({"path": str(path), "reason": "missing path"})
            continue

        # Enforce denylist
        if any(path.startswith(prefix) for prefix in DENY_PREFIXES) and not allow_workflow_edit:
            skipped.append({
                "path": path,
                "reason": "blocked by denylist (.github/workflows/**); set inputs.allow_workflow_edit=true to override"
            })
            continue

        p = pathlib.Path(path)
        _ensure_parent(p)

        # Idempotent write: only write if content actually changes
        prev = None
        if p.exists():
            try:
                prev = p.read_text(encoding="utf-8")
            except Exception:
                prev = None

        if prev == content:
            # No change; skip noisy commits
            continue

        p.write_text(content, encoding="utf-8")
        applied.append(path)

    notes = "Some edits were skipped by denylist or validation." if skipped else ""
    return applied, skipped, notes

def _process_request(req_path: pathlib.Path) -> None:
    try:
        raw = req_path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except Exception as e:
        # Write an error response and continue
        resp = {
            "type": "handoff.response",
            "handoff_id": None,
            "from_agent": "handoff-runner",
            "to_agent": "unknown",
            "status": "error",
            "error": f"parse_error: {e}",
        }
        resp_path = _respond_path(req_path)
        _ensure_parent(resp_path)
        resp_path.write_text(json.dumps(resp, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"[handoff-runner] JSON parse error for {req_path}: {e}")
        print(f"[handoff-runner] Wrote response: {resp_path}")
        return

    had_edits_key = "file_edits" in (data.get("inputs") or {})
    applied, skipped, notes = _apply_file_edits(data)

    resp = {
        "type": "handoff.response",
        "handoff_id": data.get("handoff_id"),
        "from_agent": "handoff-runner",
        "to_agent": data.get("from_agent"),
        "status": _status(applied, skipped, had_edits_key),
        "edited_files": applied,
        "skipped_files": skipped,
        "notes": notes,
    }
    resp_path = _respond_path(req_path)
    _ensure_parent(resp_path)
    resp_path.write_text(json.dumps(resp, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[handoff-runner] Wrote response: {resp_path}")

def main() -> None:
    matched = sorted(glob.glob(REQ_GLOB))
    if not matched:
        print("[handoff-runner] No new handoff requests to process.")
        return
    for path in matched:
        _process_request(pathlib.Path(path))

if __name__ == "__main__":
    main()
