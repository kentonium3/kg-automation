#!/usr/bin/env python3
import json, os, sys, glob, pathlib, datetime

REQUEST_GLOB = "ai-agents/shared/handoffs/*-request.json"
RESPONSE_SUFFIX = "-github-runner-response.json"

def is_main_branch() -> bool:
    # In Actions, GITHUB_REF is like 'refs/heads/<branch>'
    ref = os.environ.get("GITHUB_REF", "")
    return ref.endswith("/main")

def load_json(path: pathlib.Path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)

def write_file(root: pathlib.Path, relpath: str, content: str):
    p = root / relpath
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")

def write_response(req_path: pathlib.Path, data: dict):
    ts = datetime.datetime.utcnow().strftime("%Y%m%d-%H%M")
    resp_name = req_path.name.replace("-request.json", f"-{RESPONSE_SUFFIX}")
    # Keep original timestamp prefix if present, append current run ts as first segment
    resp_name = f"{ts}-{resp_name}"
    resp_path = req_path.parent / resp_name
    resp = {
        "type": "handoff.response",
        "ok": True,
        "handled_request": req_path.name,
        "branch": os.environ.get("GITHUB_REF", ""),
        "runner": "handoff-runner",
        "created_at": datetime.datetime.utcnow().isoformat() + "Z",
        "summary": {
            "files_written": [e.get("path") for e in data.get("inputs", {}).get("file_edits", [])]
        }
    }
    resp_path.write_text(json.dumps(resp, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[handoff-runner] Wrote response: {resp_path}")
    return resp_path

def process_request(repo_root: pathlib.Path, req_path: pathlib.Path) -> bool:
    data = load_json(req_path)

    edits = (data.get("inputs") or {}).get("file_edits", [])
    if not edits:
        print(f"[handoff-runner] No file_edits in {req_path.name}; skipping.")
        return False

    for edit in edits:
        rel = edit["path"]
        content = edit["content"]
        write_file(repo_root, rel, content)
        print(f"[handoff-runner] Wrote file: {rel}")

    write_response(req_path, data)
    return True

def main():
    repo_root = pathlib.Path(".").resolve()

    if is_main_branch():
        print("Refusing to run on 'main' — create a feature branch.")
        sys.exit(1)

    requests = sorted(glob.glob(REQUEST_GLOB))
    if not requests:
        print("[handoff-runner] No handoff requests found.")
        return 0

    any_processed = False
    for req in requests:
        req_path = pathlib.Path(req)
        print(f"[handoff-runner] Processing {req_path}")
        try:
            if process_request(repo_root, req_path):
                any_processed = True
        except Exception as e:
            print(f"[handoff-runner] ERROR while processing {req_path.name}: {e}")
            return 1

    if not any_processed:
        print("[handoff-runner] No applicable requests processed.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
