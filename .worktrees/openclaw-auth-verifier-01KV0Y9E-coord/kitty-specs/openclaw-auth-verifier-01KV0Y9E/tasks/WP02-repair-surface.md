---
work_package_id: WP02
title: Repair surface
dependencies:
- WP01
requirement_refs:
- FR-007
- FR-008
- FR-009
- FR-010
- NFR-004
- C-003
- C-005
tracker_refs:
- kentonium3/kg-automation#597
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this mission were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks:
- T008
- T009
- T010
agent: "claude:sonnet:reviewer-rachel:reviewer"
history: []
agent_profile: implementer-ivan
authoritative_surface: scripts/security/anthropic_verify/
execution_mode: code_change
mission_slug: openclaw-auth-verifier-01KV0Y9E
owned_files:
- scripts/security/anthropic_verify/repair.py
- tests/security/test_anthropic_verify_repair.py
role: implementer
tags: []
shell_pid: "87097"
---

## ⚡ Do This First: Load Agent Profile

Invoke `/ad-hoc-profile-load implementer-ivan` (or load the profile referenced in this WP's `agent_profile` frontmatter) BEFORE reading anything else in this prompt. The profile sets your identity, governance scope, boundaries, and initialization declaration. Without it, your behavior is unscoped and reviewable defects are likely.

## Objective

Land the `--repair` mode of `anthropic-verify`. When the detection core (WP01) flags a `shadow` or `drift` finding, `--repair` mutates state behind a backup invariant: a `.pre-repair.<unix-ts>.bak` sibling is written before any DELETE or rewrite. Shadow rows are cleared with two SQL DELETEs (`auth_profile_store` + `auth_profile_state`); on success, the operator is told to run `systemctl --user restart openclaw-gateway.service` (the verifier never restarts the gateway itself). Plaintext drift is repaired by atomically rewriting the file from `main`'s SQLite value via tmp-rename. Mutations are gated behind the explicit `--repair` flag; there is no interactive prompt, no `--dry-run` (`--check` is the dry-run surface).

## Context

Per the `#596` post-mortem and the spec:

- **Shadow** is detectable by row presence alone (WP01's `Finding` of type `shadow` carries `agent_id` + paths). Repairing it means deleting the per-agent rows so the read-through inheritance from `main` is restored. The runtime needs a gateway restart to drop any cached auth lookup — but the verifier explicitly does NOT restart the gateway (FR-009 prints the command for the operator).
- **Drift** between the plaintext file and `main`'s SQLite is detected when their sha256[:8] values differ. Repair writes `main`'s canonical key value into the plaintext file via an atomic rename (`<file>.tmp` → `<file>`), preserving mode 0600 and owner. The consumers (`felix-doc-auditor-driver`, `felix-heartbeat-gate`) re-read the file on their next tick — no service restart needed.

`--repair` reads the key value from `main`'s SQLite only to write it to the plaintext file. The value is never printed or logged. The sanitization invariant from WP01's `findings.py` still applies (Finding rejects key-shaped substrings).

## Branch Strategy

- planning_base_branch: `main`
- merge_target_branch: `main`
- Depends on WP01 — this WP branches from WP01's tip (after WP01 merges) per the spec-kitty lane allocator. Spec-kitty's `next` flow directs you to the correct worktree path.

## Subtask guidance

### T008 — Author `repair.py`: backup + shadow clear + plaintext atomic rewrite

`scripts/security/anthropic_verify/repair.py`:

```python
import sqlite3, json, hashlib, shutil, os, pathlib, time
from .findings import Finding
from .core import (
    discover_agents, read_plaintext_state, evaluate_topology,
    PLAINTEXT_FILE, SHA_FINGERPRINT_LEN,
)

def run_repair() -> int:
    """Run check first; for each repairable finding, mutate + print summary. Exit code matches post-repair --check."""
    states = discover_agents()
    plaintext = read_plaintext_state()
    findings = evaluate_topology(states, plaintext)

    if not findings:
        print("==> anthropic-verify --repair")
        print("==> nothing to repair (run --check first to confirm)")
        return 0

    print("==> anthropic-verify --repair")
    print(f"==> agents: {len(states)} discovered")

    for f in findings:
        if f.type == "shadow":
            _repair_shadow(f, states)
        elif f.type == "drift":
            _repair_drift(f, states)
        else:
            # main_empty / plaintext_missing / anthropic_rejected / network — not repairable here
            print(f"FIND  {f.type} {f.target}: NOT REPAIRABLE — operator action required")
            print(f"      suggested_action: {f.suggested_action}")

    # Re-evaluate after repair
    return _post_repair_check()

def _repair_shadow(f: Finding, states: list) -> None:
    sqlite_path = pathlib.Path(f.evidence["sqlite_path"])
    backup = sqlite_path.with_suffix(sqlite_path.suffix + f".pre-repair.{int(time.time())}.bak")
    print(f"==> REPAIR shadow {f.target}")
    shutil.copy2(sqlite_path, backup)
    os.chmod(backup, 0o600)
    print(f"      backup: {backup}")

    con = sqlite3.connect(sqlite_path)
    try:
        n1 = con.execute("DELETE FROM auth_profile_store").rowcount
        n2 = con.execute("DELETE FROM auth_profile_state").rowcount
        con.commit()
    finally:
        con.close()
    print(f"      DELETE FROM auth_profile_store  ({n1} row{'s' if n1 != 1 else ''})")
    print(f"      DELETE FROM auth_profile_state  ({n2} row{'s' if n2 != 1 else ''})")
    print("      done.")
    print("==> Next: systemctl --user restart openclaw-gateway.service")

def _repair_drift(f: Finding, states: list) -> None:
    main_state = next(s for s in states if s.agent_id == "main")
    # Re-read the canonical key from SQLite — held in local var, never printed
    con = sqlite3.connect(main_state.sqlite_path)
    try:
        row = con.execute(
            "SELECT store_json FROM auth_profile_store WHERE store_key='primary'"
        ).fetchone()
    finally:
        con.close()
    key = json.loads(row[0])["profiles"]["anthropic:default"]["key"]

    plaintext_path = pathlib.Path(f.evidence["plaintext_path"])
    backup = plaintext_path.with_suffix(plaintext_path.suffix + f".pre-repair.{int(time.time())}.bak")
    print(f"==> REPAIR drift {plaintext_path}")
    shutil.copy2(plaintext_path, backup)
    os.chmod(backup, 0o600)
    print(f"      backup: {backup}")

    tmp = plaintext_path.with_suffix(plaintext_path.suffix + ".tmp")
    tmp.write_text(key)
    os.chmod(tmp, 0o600)
    # Match owner from the original file (in case current uid differs)
    try:
        st = plaintext_path.stat()
        os.chown(tmp, st.st_uid, st.st_gid)
    except (PermissionError, OSError):
        pass  # Best effort; the chmod above is the hard invariant
    os.rename(tmp, plaintext_path)
    # Verify by re-fingerprint
    new_sha8 = hashlib.sha256(pathlib.Path(plaintext_path).read_bytes().strip()).hexdigest()[:SHA_FINGERPRINT_LEN]
    print(f"      atomic rename: {tmp.name} -> {plaintext_path.name}  new_sha8={new_sha8}")
    if new_sha8 != main_state.canonical_key_sha8:
        raise RuntimeError(f"REPAIR INTEGRITY FAILURE: post-write sha8={new_sha8} != main_sha8={main_state.canonical_key_sha8}")
    print("      done.")

def _post_repair_check() -> int:
    """Re-run evaluate_topology; return spec-mapped exit code."""
    states = discover_agents()
    plaintext = read_plaintext_state()
    remaining = evaluate_topology(states, plaintext)
    if not remaining:
        print("==> repair result: green (exit 0)")
        return 0
    # Some findings remain — re-emit and return appropriate exit
    print(f"==> repair result: {len(remaining)} finding(s) remain (exit non-zero)")
    return 1  # generic non-zero; --check is the canonical re-evaluation surface
```

Key invariants:

- **Backup-before-mutate (FR-008)**: every mutation path opens `shutil.copy2` first. If the copy fails, no mutation is attempted.
- **Atomic rename (FR-010 / NFR-004)**: write to `.tmp`, chmod, chown if possible, then `os.rename`. `os.rename` is atomic on POSIX same-filesystem moves; `/data/services/openclaw/secrets/` is on the `/data` mount which is the same filesystem as `/data/services/openclaw/secrets/anthropic.tmp`.
- **No key printed (C-005)**: the `key` local variable lives only inside `_repair_drift`. It is written to a file via `Path.write_text(key)`; never printed or logged. The post-write verification uses sha8, not the value.
- **Owner preservation (FR-010 spec note)**: `os.chown` is best-effort; if the verifier runs as `claude` and the file is owned by `claude`, no chown is needed. The `try/except PermissionError` is defensive.

### T009 — Wire repair dispatch via lazy import (already in WP01's `__init__.py`)

WP01's `__init__.py` already has:

```python
if argv == ["--repair"]:
    from . import repair
    return repair.run_repair()
```

T009 is a verification subtask: confirm the lazy import works by running `python3 -m anthropic_verify --repair` against the shadow fixture and observing the expected output. No file changes; just smoke-test the integration.

If WP01's import path needs adjustment (e.g., the implementer chose a slightly different structure), the WP02 implementer makes the minimum edit in `__init__.py` with a one-line ownership-boundary rationale in the commit message. Memory `feedback_speckitty_split_code_and_deploy_missions` covers this; the spec-kitty `#1766` workaround applies.

### T010 — Tests for repair

`tests/security/test_anthropic_verify_repair.py`:

- **Shadow repair against fixture**: build a shadow fixture; invoke `run_repair`; assert (a) backup file exists with `.pre-repair.<ts>.bak` suffix at mode 0600; (b) post-repair, `evaluate_topology` returns no findings for the previously-shadowed agent; (c) stdout contains the `systemctl --user restart` instruction.
- **Drift repair against fixture**: build a drift fixture; invoke `run_repair`; assert (a) backup file exists; (b) plaintext file's sha8 now matches main's; (c) plaintext file mode is 0600; (d) no `.tmp` sibling remains (atomic rename completed).
- **Backup-before-mutate**: monkey-patch `sqlite3.connect` to raise after the backup is written; assert backup file exists; assert SQLite store is UNCHANGED (rollback at the test boundary).
- **No key in repair output**: capture `capsys` during a successful drift repair; assert the test sentinel value never appears in stdout/stderr.
- **Repair integrity check**: monkey-patch `Path.read_bytes` after the rename to return a different value; assert `RuntimeError` is raised with "REPAIR INTEGRITY FAILURE" in the message; assert the error message itself does not contain the key value.
- **No-op repair when green**: build a healthy fixture; invoke `run_repair`; assert "nothing to repair" line and exit 0; assert no backup files created.
- **Not-repairable findings pass through**: build a fixture where `main_empty` would be flagged; invoke `run_repair`; assert the NOT REPAIRABLE message is emitted; no mutation attempted.

### Files touched (final list)

- `scripts/security/anthropic_verify/repair.py` (NEW, ~150 lines)
- `tests/security/test_anthropic_verify_repair.py` (NEW, ~200 lines)

T009's smoke verification doesn't add files; it's a manual run-and-observe step plus an integration test in `test_anthropic_verify_repair.py` that subprocess-invokes `python3 -m anthropic_verify --repair` against the fixture root.

## Test strategy

Test-first per DIRECTIVE_034. Author T010 against the spec contracts (FR-008 backup invariant, FR-009 systemctl print, FR-010 atomic rename) before T008 implementation. Mock filesystem boundaries via the `tmp_office2_root` fixture from WP01's conftest. No live Anthropic calls.

## Definition of Done

- All 3 subtasks completed; all tests pass; ruff + mypy clean.
- Against a fixture shadow, `anthropic-verify.sh --repair` clears the rows, leaves a `.pre-repair.<ts>.bak` sibling, and prints the systemctl restart command.
- Against a fixture drift, the plaintext file is atomically rewritten and its sha8 matches main's afterward.
- The sentinel-grep test from WP01 still passes (no key leak in repair output).
- WP03 can invoke the verifier as a fail-closed gate from `anthropic-rotate.sh` without further changes to WP02-owned files.

## Risks

- **Atomic rename semantics on `/data/`**: assumes the tmp and target are on the same filesystem. They are (`/data` is a single mount); document the assumption inline.
- **Owner mismatch** if some future deploy changes the owner of the plaintext file. The best-effort chown + chmod-0600 invariant is the defensive surface.
- **Repair integrity check** must verify post-write parity; without it, a partially-failed write would leave the file with garbage and the verifier would not catch it until the next `--check`.

## Reviewer guidance

- Verify the backup is written BEFORE any mutation. Add a deliberate failure between backup and mutation; confirm SQLite is unchanged.
- Verify the atomic rename — interrupt between tmp-write and rename; confirm the original file is unmodified.
- Verify the post-rename sha8 verification catches a tampered tmp file.
- Verify no key value appears in any output path. Add a temporary `print(key)` to `_repair_drift`; the sentinel-grep test must fail; revert.
- Verify the gateway-restart command is printed verbatim (spec FR-009 wording: `systemctl --user restart openclaw-gateway.service`).

## Commands

When `spec-kitty next` directs you here:

```bash
spec-kitty agent action implement WP02 --agent claude
```

When ready for review:

```bash
spec-kitty agent action review WP02 --agent claude
```

## Activity Log

- 2026-06-13T18:19:51Z – claude:sonnet:implementer-ivan:implementer – shell_pid=85198 – Assigned agent via action command
- 2026-06-13T18:26:04Z – claude:sonnet:implementer-ivan:implementer – shell_pid=85198 – Ready for review — 3 subtasks done, 10 new tests passing, full security suite 208 passing, integration smoke OK
- 2026-06-13T18:26:47Z – claude:sonnet:reviewer-rachel:reviewer – shell_pid=87097 – Started review via action command
- 2026-06-13T18:29:49Z – user – shell_pid=87097 – Review passed: backup-before-mutate verified (FR-008), verbatim systemctl line present (FR-009), atomic tmp-rename + post-write integrity check (FR-010/NFR-004), zero sentinel leaks in repair output (C-005), no subprocess/systemctl auto-restart, 208/208 tests pass including 10 new repair tests; documented ownership exception on test_anthropic_verify_output.py is minimal and replaces WP01's stale 'absent module' test with the equivalent positive dispatch test.
