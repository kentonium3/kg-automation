"""Repair surface for anthropic-verify (WP02).

This module implements the ``--repair`` mode dispatched by ``__init__.main``.
It is filesystem-mutating but every mutation is gated behind two invariants:

  * **Backup-before-mutate (FR-008 / NFR-004)** — every mutation path opens
    ``shutil.copy2`` to a ``.pre-repair.<unix-ts>.bak`` sibling BEFORE any
    DELETE or rename. If the backup fails, no mutation is attempted; if the
    mutation fails AFTER the backup is written, the backup is the recovery
    surface and the SQLite store remains in its pre-mutation state.

  * **No key value in output (C-005 / FR-006)** — the canonical key value
    is read from main's SQLite into a single local variable and written to
    the plaintext file in one operation. It is never printed, logged, or
    interpolated into any error message. The post-write verification uses
    sha256[:8] fingerprints only.

Two repair classes are implemented:

  * **Shadow** — clears ``auth_profile_store`` and ``auth_profile_state``
    in the sub-agent's SQLite, then prints the operator's next-action line
    (``systemctl --user restart openclaw-gateway.service`` — verbatim per
    FR-009; the verifier never restarts the gateway itself).

  * **Drift** — atomically rewrites the plaintext credential file from
    ``main``'s SQLite value via tmp-rename (``<file>.tmp`` → ``<file>``;
    FR-010). Mode 0600 is enforced; owner is preserved best-effort via
    ``os.chown``. Post-rename re-fingerprint must match main's sha8 or a
    ``RuntimeError`` is raised — the error message contains only fingerprints,
    never the key value.

Not-repairable findings (``main_empty``, ``plaintext_missing``,
``anthropic_rejected``, ``network``) pass through with a clear NOT
REPAIRABLE line so the operator knows to take action elsewhere (rotation
script for substrate gaps; network retry for transient failures).
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import shutil
import sqlite3
import time
from typing import List

from .core import (
    SHA_FINGERPRINT_LEN,
    AgentAuthState,
    discover_agents,
    evaluate_topology,
    read_plaintext_state,
)
from .findings import Finding


def run_repair() -> int:
    """Run the topology check, then mutate for each repairable finding.

    Returns
    -------
    int
        Exit code reflecting the post-repair state. ``0`` when the repair
        cleared everything; non-zero when findings remain (either because
        the finding was not auto-repairable or the post-repair re-check
        still surfaces a residual condition).
    """
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
            # main_empty / plaintext_missing / anthropic_rejected / network
            # are not in the verifier's repair surface (the rotation script
            # is the operator's tool for substrate-rebuild; network is a
            # transient retry case).
            print(
                f"FIND  {f.type} {f.target}: NOT REPAIRABLE — operator action required"
            )
            print(f"      suggested_action: {f.suggested_action}")

    return _post_repair_check()


def _backup_path(target: pathlib.Path, now_ts: int) -> pathlib.Path:
    """Return ``<target>.pre-repair.<now_ts>.bak`` regardless of target's suffix.

    ``Path.with_suffix`` is used so the new name is well-formed for both
    suffixed paths (``openclaw-agent.sqlite`` → ``openclaw-agent.sqlite.pre-repair.<ts>.bak``)
    and bare paths (``anthropic`` → ``anthropic.pre-repair.<ts>.bak``).
    """
    return target.with_suffix(target.suffix + f".pre-repair.{now_ts}.bak")


def _repair_shadow(f: Finding, states: List[AgentAuthState]) -> None:
    """Clear the sub-agent's auth rows after writing a SQLite backup.

    Order of operations (the backup-before-mutate invariant):
      1. ``shutil.copy2`` the SQLite file to ``.pre-repair.<ts>.bak``.
      2. ``chmod 0600`` the backup (same secrecy posture as the original).
      3. Open a write connection and execute the two DELETEs.
      4. Print the operator's next-action line per FR-009 (VERBATIM wording).
    """
    sqlite_path = pathlib.Path(f.evidence["sqlite_path"])
    now_ts = int(time.time())
    backup = _backup_path(sqlite_path, now_ts)

    print(f"==> REPAIR shadow {f.target}")
    # 1) Backup BEFORE mutation. If copy2 fails this raises out and no
    #    mutation is attempted.
    shutil.copy2(sqlite_path, backup)
    try:
        os.chmod(backup, 0o600)
    except OSError:
        # Best effort; on tmpfs / some FS chmod may fail. The contents
        # are already on disk and the secrecy posture is the same as the
        # original sqlite (which the operator already trusts).
        pass
    print(f"      backup: {backup}")

    # 2) Mutation. If this raises, the backup is the recovery surface.
    con = sqlite3.connect(str(sqlite_path))
    try:
        n1 = con.execute("DELETE FROM auth_profile_store").rowcount
        n2 = con.execute("DELETE FROM auth_profile_state").rowcount
        con.commit()
    finally:
        con.close()
    print(
        f"      DELETE FROM auth_profile_store  "
        f"({n1} row{'s' if n1 != 1 else ''})"
    )
    print(
        f"      DELETE FROM auth_profile_state  "
        f"({n2} row{'s' if n2 != 1 else ''})"
    )
    print("      done.")
    # FR-009: VERBATIM systemctl line. The verifier never restarts the
    # gateway itself; it tells the operator to.
    print("==> Next: systemctl --user restart openclaw-gateway.service")


def _repair_drift(f: Finding, states: List[AgentAuthState]) -> None:
    """Atomically rewrite the plaintext file from main's SQLite value.

    Order of operations:
      1. Read the canonical key value from main's SQLite into a local var.
      2. ``shutil.copy2`` the plaintext file to ``.pre-repair.<ts>.bak``.
      3. Write the value to ``<file>.tmp`` at mode 0600.
      4. Best-effort chown to match the original owner.
      5. ``os.rename`` ``<file>.tmp`` → ``<file>`` (atomic on POSIX
         same-filesystem moves; ``/data`` is a single mount on office2).
      6. Re-fingerprint the post-rename file and compare to main's sha8;
         raise on mismatch with a fingerprints-only message.

    The ``key`` local is never printed, logged, or interpolated. The
    sentinel-grep test exercised in WP01's output suite catches any
    regression that introduces a leak via this path.
    """
    main_state = next(s for s in states if s.agent_id == "main")

    # 1) Re-read the canonical key from main's SQLite. This value lives
    #    only in the local ``key`` variable and is written to the
    #    plaintext file in one operation. It is never printed.
    con = sqlite3.connect(str(main_state.sqlite_path))
    try:
        row = con.execute(
            "SELECT store_json FROM auth_profile_store WHERE store_key='primary'"
        ).fetchone()
    finally:
        con.close()
    key = json.loads(row[0])["profiles"]["anthropic:default"]["key"]

    plaintext_path = pathlib.Path(f.evidence["plaintext_path"])
    now_ts = int(time.time())
    backup = _backup_path(plaintext_path, now_ts)

    print(f"==> REPAIR drift {plaintext_path}")

    # 2) Backup BEFORE mutation.
    shutil.copy2(plaintext_path, backup)
    try:
        os.chmod(backup, 0o600)
    except OSError:
        pass
    print(f"      backup: {backup}")

    # 3) Write to .tmp then 4) chown best-effort then 5) atomic rename.
    tmp = plaintext_path.with_suffix(plaintext_path.suffix + ".tmp")
    tmp.write_text(key)
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    try:
        st = plaintext_path.stat()
        os.chown(tmp, st.st_uid, st.st_gid)
    except (PermissionError, OSError):
        # Best effort; the chmod above is the hard invariant. If the
        # verifier runs as ``claude`` and the file is owned by
        # ``claude``, no chown is needed.
        pass

    os.rename(tmp, plaintext_path)

    # 6) Re-fingerprint and verify. Use Path.read_bytes (not the local
    #    ``key`` variable) so we are reading the actual on-disk state.
    new_sha8 = hashlib.sha256(
        pathlib.Path(plaintext_path).read_bytes().strip()
    ).hexdigest()[:SHA_FINGERPRINT_LEN]
    print(
        f"      atomic rename: {tmp.name} -> {plaintext_path.name}  "
        f"new_sha8={new_sha8}"
    )
    if new_sha8 != main_state.canonical_key_sha8:
        # Error message contains fingerprints only — NEVER the key value.
        raise RuntimeError(
            f"REPAIR INTEGRITY FAILURE: post-write sha8={new_sha8} "
            f"!= main_sha8={main_state.canonical_key_sha8}"
        )
    print("      done.")


def _post_repair_check() -> int:
    """Re-evaluate topology after the repair attempt.

    Returns ``0`` when no findings remain, non-zero otherwise. The
    canonical re-evaluation surface is ``--check``; this is a coarse
    "did we clear it" signal rather than a full priority-order classifier.
    """
    states = discover_agents()
    plaintext = read_plaintext_state()
    remaining = evaluate_topology(states, plaintext)
    if not remaining:
        print("==> repair result: green (exit 0)")
        return 0
    print(
        f"==> repair result: {len(remaining)} finding(s) remain (exit non-zero)"
    )
    return 1
